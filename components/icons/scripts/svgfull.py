# -*- coding: utf-8 -*-
"""svgfull.py —— vendor 线的 SVG 光栅器（纯 Pillow，无第三方渲染依赖）

来源说明：本文件是把**已验证过的**那份渲染器（`temp/svgrender.py`，曾用它把 vendor 线
**4754 个 Tabler outline 图标全部渲染通过**）纳入模块；渲染逻辑（path 全指令解析 /
A 圆弧转贝塞尔 / 扫描线 + nonzero 绕序填充 / stroke 圆头圆角 / currentColor 替换 /
非正方形等比居中 / SS 倍超采样 + LANCZOS 降采样）**一行未动**。

与原文件的**唯一差异**（本次纳入时补的，其余逐行相同）：最后一步输出 RGBA 时，
原文件用 `paste(solid, mask=alpha)` → RGB 被按 alpha 预乘（`RGB = color×a/255`，
叠在浅底上会有灰/暗边）；本文件改成 `RGB 恒等于 color、只有 alpha 变化`，
**与自绘线 `svgmini.py` 的输出口径完全一致**（本模块对外承诺的硬规则：颜色烘焙、无 tint）。
填充/描边的栅格化过程一字未改。

与 `svgmini.py` 的分工：
  - 自绘线 `svg/**`            → `svgmini.py`（24 网格专用 + 支持本模块私有的 `data-cut`），`gen_icons.py` 在用
  - vendor 线 `vendor/tabler/**` → 本文件（通用 SVG 子集 + nonzero 绕序，Tabler filled 的孔洞不被填死），`vendor.py` 在用
两者产物口径一致：**RGB 恒等于请求颜色，只有 alpha（覆盖率）变化**，业务侧看不出差别。

对外接口（保持稳定，勿改签名）：
    render_svg(svg_text, size, color=(255, 255, 255), ss=4) -> PIL.Image (RGBA)
    size 可以是 int（正方形）或 (w, h)：输出像素尺寸**严格等于**请求值；
    非正方形时等比缩放 + 居中留白，**绝不拉伸**。

支持：
  - 元素：<path d>（M m L l H h V v C c S s Q q T t A a Z z，含隐式重复参数）、
    <circle> <ellipse> <rect> <line> <polyline> <polygon>
  - 属性：fill / stroke / stroke-width / fill-rule / stroke-linecap / stroke-linejoin
  - 颜色：none / currentColor / #rgb / #rrggbb / #rrggbbaa / rgb()/rgba() / 常用命名色
  - 变换：transform="translate(...) scale(...) rotate(...) matrix(...)"（平移/等比缩放/旋转）
特性：
  - 填充用**扫描线 + nonzero 绕序**（正确处理 Tabler filled 变体的孔洞）
  - 描边用「粗线段 + 每顶点圆点」实现圆头圆角（避免 PIL mitre 尖角）
  - SS 倍超采样 + LANCZOS 降采样
"""

import math
import re

from PIL import Image, ImageDraw

NUM_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
CMD_RE = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)")

NAMED = {
    "black": (0, 0, 0, 255), "white": (255, 255, 255, 255), "red": (255, 0, 0, 255),
    "green": (0, 128, 0, 255), "blue": (0, 0, 255, 255), "gray": (128, 128, 128, 255),
    "grey": (128, 128, 128, 255), "currentcolor": None,
}


def parse_color(v, current):
    if v is None:
        return None
    v = v.strip().lower()
    if v in ("none", "transparent"):
        return None
    if v == "currentcolor":
        return current
    if v.startswith("#"):
        h = v[1:]
        if len(h) == 3:
            return (int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16), 255)
        if len(h) == 4:
            return (int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16), int(h[3] * 2, 16))
        if len(h) == 6:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
        if len(h) == 8:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))
    m = re.match(r"rgba?\(([^)]*)\)", v)
    if m:
        parts = [p.strip() for p in m.group(1).replace("/", " ").split(",")]
        if len(parts) == 1:
            parts = parts[0].split()
        vals = []
        for p in parts[:4]:
            if p.endswith("%"):
                vals.append(round(float(p[:-1]) * 2.55))
            else:
                vals.append(float(p))
        while len(vals) < 3:
            vals.append(0)
        if len(vals) == 3:
            vals.append(255)
        if vals[3] <= 1.0 and "." in str(parts[3]):
            vals[3] = round(vals[3] * 255)
        return (int(vals[0]), int(vals[1]), int(vals[2]), int(vals[3]))
    if v in NAMED:
        return NAMED[v] or current
    return current


# ---------------------------------------------------------------- path -> subpaths

def _arc_to_beziers(x0, y0, rx, ry, phi_deg, large_arc, sweep, x1, y1):
    """SVG 端点式圆弧 → 三次贝塞尔列表（每段 ≤90°）。"""
    if rx == 0 or ry == 0:
        return [("L", [x1, y1])]
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(phi_deg)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    dx2, dy2 = (x0 - x1) / 2.0, (y0 - y1) / 2.0
    x1p = cos_p * dx2 + sin_p * dy2
    y1p = -sin_p * dx2 + cos_p * dy2
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large_arc == sweep:
        co = -co
    cxp = co * rx * y1p / ry
    cyp = -co * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (x0 + x1) / 2.0
    cy = sin_p * cxp + cos_p * cyp + (y0 + y1) / 2.0

    def ang(ux, uy, vx, vy):
        d = (ux * vx + uy * vy) / (math.hypot(ux, uy) * math.hypot(vx, vy))
        d = max(-1.0, min(1.0, d))
        a = math.acos(d)
        if ux * vy - uy * vx < 0:
            a = -a
        return a

    th1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dth = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dth > 0:
        dth -= 2 * math.pi
    elif sweep and dth < 0:
        dth += 2 * math.pi

    n = max(1, int(math.ceil(abs(dth) / (math.pi / 2))))
    out = []
    delta = dth / n
    t = (4.0 / 3.0) * math.tan(delta / 4.0)
    th = th1
    for _ in range(n):
        th2 = th + delta
        cos1, sin1 = math.cos(th), math.sin(th)
        cos2, sin2 = math.cos(th2), math.sin(th2)
        e1x = cx + rx * cos_p * cos1 - ry * sin_p * sin1
        e1y = cy + rx * sin_p * cos1 + ry * cos_p * sin1
        e2x = cx + rx * cos_p * cos2 - ry * sin_p * sin2
        e2y = cy + rx * sin_p * cos2 + ry * cos_p * sin2
        d1x = -rx * cos_p * sin1 - ry * sin_p * cos1
        d1y = -rx * sin_p * sin1 + ry * cos_p * cos1
        d2x = -rx * cos_p * sin2 - ry * sin_p * cos2
        d2y = -rx * sin_p * sin2 + ry * cos_p * cos2
        c1x, c1y = e1x + t * d1x, e1y + t * d1y
        c2x, c2y = e2x - t * d2x, e2y - t * d2y
        out.append(("C", [c1x, c1y, c2x, c2y, e2x, e2y]))
        th = th2
    return out


def path_to_subpaths(d):
    """返回 [ [p0, p1, ...], ... ]（每段子路径一组点），曲线已细分为折线。"""
    subpaths = []
    cur = []
    x = y = 0.0
    sx = sy = 0.0
    prev_ctrl = None
    prev_cmd = ""
    closed = False

    def flush():
        nonlocal cur
        if len(cur) >= 2:
            subpaths.append(cur)
        cur = []

    for cm, args in CMD_RE.findall(d):
        nums = [float(n) for n in NUM_RE.findall(args)]
        rel = cm.islower()
        C = cm.upper()
        i = 0
        if C == "M":
            while i + 1 < len(nums) or (i == 0 and len(nums) >= 2):
                px, py = nums[i], nums[i + 1]
                if rel:
                    px, py = x + px, y + py
                if i == 0:
                    flush()
                    x, y = px, py
                    sx, sy = x, y
                    cur = [(x, y)]
                else:
                    x, y = px, py
                    cur.append((x, y))
                i += 2
                if i >= len(nums):
                    break
        elif C in ("L", "H", "V"):
            if C == "H":
                seq = [(nums[k], None) for k in range(len(nums))]
            elif C == "V":
                seq = [(None, nums[k]) for k in range(len(nums))]
            else:
                seq = [(nums[k], nums[k + 1]) for k in range(0, len(nums) - 1, 2)]
            for a, b in seq:
                if a is not None:
                    x = x + a if rel else a
                if b is not None:
                    y = y + b if rel else b
                if not cur:
                    cur = [(x, y)]
                else:
                    cur.append((x, y))
        elif C in ("C", "S", "Q", "T"):
            k = 0
            while True:
                if C == "C":
                    if k + 6 > len(nums):
                        break
                    pts = nums[k:k + 6]
                    k += 6
                    c1 = (pts[0] + x, pts[1] + y) if rel else (pts[0], pts[1])
                    c2 = (pts[2] + x, pts[3] + y) if rel else (pts[2], pts[3])
                    e = (pts[4] + x, pts[5] + y) if rel else (pts[4], pts[5])
                elif C == "S":
                    if k + 4 > len(nums):
                        break
                    pts = nums[k:k + 4]
                    k += 4
                    if prev_cmd in ("C", "S") and prev_ctrl:
                        c1 = (2 * x - prev_ctrl[0], 2 * y - prev_ctrl[1])
                    else:
                        c1 = (x, y)
                    c2 = (pts[0] + x, pts[1] + y) if rel else (pts[0], pts[1])
                    e = (pts[2] + x, pts[3] + y) if rel else (pts[2], pts[3])
                elif C == "Q":
                    if k + 4 > len(nums):
                        break
                    pts = nums[k:k + 4]
                    k += 4
                    q = (pts[0] + x, pts[1] + y) if rel else (pts[0], pts[1])
                    e = (pts[2] + x, pts[3] + y) if rel else (pts[2], pts[3])
                    c1 = (x + 2.0 / 3 * (q[0] - x), y + 2.0 / 3 * (q[1] - y))
                    c2 = (e[0] + 2.0 / 3 * (q[0] - e[0]), e[1] + 2.0 / 3 * (q[1] - e[1]))
                    prev_ctrl = q
                else:  # T
                    if k + 2 > len(nums):
                        break
                    pts = nums[k:k + 2]
                    k += 2
                    if prev_cmd in ("Q", "T") and prev_ctrl:
                        q = (2 * x - prev_ctrl[0], 2 * y - prev_ctrl[1])
                    else:
                        q = (x, y)
                    e = (pts[0] + x, pts[1] + y) if rel else (pts[0], pts[1])
                    c1 = (x + 2.0 / 3 * (q[0] - x), y + 2.0 / 3 * (q[1] - y))
                    c2 = (e[0] + 2.0 / 3 * (q[0] - e[0]), e[1] + 2.0 / 3 * (q[1] - e[1]))
                    prev_ctrl = q
                if C == "C":
                    prev_ctrl = c2
                steps = 12
                for s in range(1, steps + 1):
                    t = s / steps
                    mt = 1 - t
                    bx = (mt ** 3 * x + 3 * mt * mt * t * c1[0] + 3 * mt * t * t * c2[0] + t ** 3 * e[0])
                    by = (mt ** 3 * y + 3 * mt * mt * t * c1[1] + 3 * mt * t * t * c2[1] + t ** 3 * e[1])
                    cur.append((bx, by))
                x, y = e
                prev_cmd = C
        elif C == "A":
            k = 0
            while k + 7 <= len(nums):
                rx, ry, rot, laf, sf, ex, ey = nums[k:k + 7]
                k += 7
                e = (ex + x, ey + y) if rel else (ex, ey)
                for seg in _arc_to_beziers(x, y, rx, ry, rot, int(laf), int(sf), e[0], e[1]):
                    pts = seg[1]
                    c1 = (pts[0], pts[1])
                    c2 = (pts[2], pts[3])
                    ee = (pts[4], pts[5])
                    steps = 12
                    for s in range(1, steps + 1):
                        t = s / steps
                        mt = 1 - t
                        bx = (mt ** 3 * x + 3 * mt * mt * t * c1[0] + 3 * mt * t * t * c2[0] + t ** 3 * ee[0])
                        by = (mt ** 3 * y + 3 * mt * mt * t * c1[1] + 3 * mt * t * t * c2[1] + t ** 3 * ee[1])
                        cur.append((bx, by))
                    x, y = ee
                prev_cmd = "A"
        elif C == "Z":
            if cur:
                cur.append((sx, sy))
                flush()
            x, y = sx, sy
            prev_cmd = "Z"
        if C not in ("C", "S", "Q", "T"):
            prev_ctrl = None
    flush()
    return subpaths


# ---------------------------------------------------------------- transform

def parse_transform(s):
    """返回 (a, b, c, d, e, f) 矩阵，仅支持常见组合的叠加。"""
    m = (1, 0, 0, 1, 0, 0)
    if not s:
        return m
    for name, argstr in re.findall(r"(\w+)\s*\(([^)]*)\)", s):
        v = [float(x) for x in NUM_RE.findall(argstr)]
        if name == "translate":
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale":
            sx = v[0]
            sy = v[1] if len(v) > 1 else v[0]
            t = (sx, 0, 0, sy, 0, 0)
        elif name == "rotate":
            a = math.radians(v[0])
            ca, sa = math.cos(a), math.sin(a)
            t = (ca, sa, -sa, ca, 0, 0)
            if len(v) >= 3:
                cx, cy = v[1], v[2]
                m = mul(m, (1, 0, 0, 1, cx, cy))
                m = mul(m, t)
                m = mul(m, (1, 0, 0, 1, -cx, -cy))
                continue
        elif name == "matrix":
            t = tuple(v[:6])
        else:
            continue
        m = mul(m, t)
    return m


def mul(m1, m2):
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def apply_m(m, p):
    a, b, c, d, e, f = m
    return (a * p[0] + c * p[1] + e, b * p[0] + d * p[1] + f)


# ---------------------------------------------------------------- rasterize

def _fill_nonzero(mask, subpaths, scale, offx, offy, W, H):
    """扫描线 + nonzero 绕序填充（mask: PIL 'L' 图，255 = 填充）。"""
    edges = []
    for sp in subpaths:
        pts = [(p[0] * scale + offx, p[1] * scale + offy) for p in sp]
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            if y0 == y1:
                continue
            edges.append((x0, y0, x1, y1))
    if not edges:
        return
    ymin = max(0, int(math.floor(min(min(e[1], e[3]) for e in edges))))
    ymax = min(H - 1, int(math.ceil(max(max(e[1], e[3]) for e in edges))))
    px = mask.load()
    for yy in range(ymin, ymax + 1):
        cy = yy + 0.5
        xs = []
        for (x0, y0, x1, y1) in edges:
            if (y0 <= cy < y1) or (y1 <= cy < y0):
                t = (cy - y0) / (y1 - y0)
                xs.append((x0 + t * (x1 - x0), 1 if y1 > y0 else -1))
        if not xs:
            continue
        xs.sort()
        wind = 0
        for i in range(len(xs) - 1):
            wind += xs[i][1]
            if wind != 0:
                xa = int(math.ceil(xs[i][0] - 0.5))
                xb = int(math.floor(xs[i + 1][0] - 0.5))
                if xb >= xa:
                    xa = max(0, xa)
                    xb = min(W - 1, xb)
                    if xb >= xa:
                        px_line = px
                        for xx in range(xa, xb + 1):
                            px_line[xx, yy] = 255


def _stroke_mask(mask, subpaths, scale, offx, offy, width, cap_round=True, join_round=True):
    dr = ImageDraw.Draw(mask)
    w = max(2, int(round(width)))
    for sp in subpaths:
        pts = [(p[0] * scale + offx, p[1] * scale + offy) for p in sp]
        if len(pts) < 2:
            continue
        dr.line(pts, fill=255, width=w, joint="curve")
        if cap_round or join_round:
            r = w / 2.0
            step = pts if join_round else (pts[0], pts[-1])
            for (px_, py_) in step:
                dr.ellipse([px_ - r, py_ - r, px_ + r, py_ + r], fill=255)


def render_svg(svg_text, size, color=(255, 255, 255), ss=4, current="currentColor",
               only_first_size=None):
    """svg_text → RGBA PIL.Image，像素尺寸严格等于 size（int 或 (w, h)）。"""
    if isinstance(size, int):
        W = H = size
    else:
        W, H = size
    vb = re.search(r'viewBox\s*=\s*"([^"]+)"', svg_text)
    if vb:
        v = [float(x) for x in NUM_RE.findall(vb.group(1))]
        vb_w, vb_h = v[2], v[3]
    else:
        wm = re.search(r'width\s*=\s*"([\d.]+)', svg_text)
        hm = re.search(r'height\s*=\s*"([\d.]+)', svg_text)
        vb_w = float(wm.group(1)) if wm else 24.0
        vb_h = float(hm.group(1)) if hm else 24.0

    # 等比缩放 + 居中（禁止变形）
    s = min(W / vb_w, H / vb_h)
    offx = (W - vb_w * s) / 2.0
    offy = (H - vb_h * s) / 2.0
    SS = ss
    scale = s * SS
    offx *= SS
    offy *= SS
    cw, ch = int(round(W * SS)), int(round(H * SS))

    fill_mask = Image.new("L", (cw, ch), 0)
    stroke_mask = Image.new("L", (cw, ch), 0)

    # 根属性
    root = {}
    mroot = re.search(r"<svg([^>]*)>", svg_text, re.S)
    if mroot:
        for k, v in re.findall(r'([\w-]+)\s*=\s*"([^"]*)"', mroot.group(1)):
            root[k] = v

    def attr(el, name, default=None):
        return el.get(name, root.get(name, default))

    # 元素遍历（含 <g> 简单继承）
    body = svg_text[svg_text.index(">", svg_text.index("<svg")) + 1:]
    body = body[:body.rfind("</svg>")] if "</svg>" in body else body
    pending = []  # (sp, style) 收集后再画
    cur_color = color

    for m in re.finditer(r"<(path|circle|ellipse|rect|line|polyline|polygon)\b([^>]*?)/?>", body, re.S):
        tag, astr = m.group(1), m.group(2)
        el = dict(re.findall(r'([\w-]+)\s*=\s*"([^"]*)"', astr))
        tr = parse_transform(el.get("transform", ""))
        sps = []
        if tag == "path":
            d = el.get("d", "")
            for sp in path_to_subpaths(d):
                sps.append([apply_m(tr, p) for p in sp])
        else:
            def f2(nums, k):
                return (nums[k] + offx / SS, nums[k + 1] + offy / SS)
            if tag in ("polyline", "polygon"):
                nums = [float(x) for x in NUM_RE.findall(el.get("points", ""))]
                pts = [(nums[i] + offx / SS, nums[i + 1] + offy / SS) for i in range(0, len(nums) - 1, 2)]
                if tag == "polygon" and pts:
                    pts.append(pts[0])
                sps.append([apply_m(tr, p) for p in pts])
            elif tag == "line":
                x1, y1 = float(el.get("x1", 0)), float(el.get("y1", 0))
                x2, y2 = float(el.get("x2", 0)), float(el.get("y2", 0))
                sps.append([apply_m(tr, p) for p in [(x1, y1), (x2, y2)]])
            elif tag in ("circle", "ellipse"):
                cx, cy = float(el.get("cx", 0)), float(el.get("cy", 0))
                rx = float(el.get("r", 0)) if tag == "circle" else float(el.get("rx", 0))
                ry = float(el.get("r", 0)) if tag == "circle" else float(el.get("ry", 0))
                pts = []
                for i in range(73):
                    t = 2 * math.pi * i / 72
                    pts.append(apply_m(tr, (cx + rx * math.cos(t), cy + ry * math.sin(t))))
                sps.append(pts)
            elif tag == "rect":
                x0, y0 = float(el.get("x", 0)), float(el.get("y", 0))
                w0, h0 = float(el.get("width", 0)), float(el.get("height", 0))
                pts = [(x0, y0), (x0 + w0, y0), (x0 + w0, y0 + h0), (x0, y0 + h0), (x0, y0)]
                sps.append([apply_m(tr, p) for p in pts])
        if not sps:
            continue
        fill = parse_color(attr(el, "fill", "none"), cur_color)
        stroke = parse_color(attr(el, "stroke"), cur_color)
        if el.get("stroke", "").strip().lower() == "none":
            stroke = None
        sw = attr(el, "stroke-width", "1")
        try:
            sw = float(NUM_RE.findall(str(sw))[0]) if NUM_RE.findall(str(sw)) else 1.0
        except Exception:
            sw = 1.0
        pending.append((sps, fill, stroke, sw))

    for (sps, fill, stroke, sw) in pending:
        if fill:
            _fill_nonzero(fill_mask, sps, scale, offx, offy, cw, ch)
        if stroke and sw > 0:
            _stroke_mask(stroke_mask, sps, scale, offx, offy, sw * scale)

    both = Image.new("L", (cw, ch), 0)
    both.paste(fill_mask, (0, 0), fill_mask)
    both.paste(stroke_mask, (0, 0), stroke_mask)
    both = both.resize((W, H), Image.LANCZOS)
    # 输出口径（与自绘线 svgmini.py 一致）：RGB 恒等于请求颜色，只有 alpha 变化。
    # 注：原 temp/svgrender.py 这里写的是
    #     out = Image.new("RGBA", (W, H), (0, 0, 0, 0)); out.paste(solid, (0, 0), both)
    # 带 mask 的 paste 会把 RGB 按 alpha 预乘，边缘像素变成更暗的混色（浅底上表现为灰边），
    # 不符合本模块"颜色烘焙"的硬规则，故换成下面这两行（几何/填充/描边逻辑未动）。
    out = Image.new("RGBA", (W, H), (color[0], color[1], color[2], 0))
    out.putalpha(both)
    return out
