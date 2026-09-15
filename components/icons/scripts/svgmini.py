# -*- coding: utf-8 -*-
"""svgmini —— 极简 SVG 子集解析 + 光栅化（只依赖 Pillow + numpy，禁止联网）

为什么自己写：FlyThings 图标是**单色烘焙 PNG**，需要"矢量源 → 任意分辨率的干净边缘"，
但环境里不能装 cairosvg（禁网）。所以这里实现一个**受控子集**的 SVG 光栅器。

**支持的范围（按 vendor/tabler 的真实文件实测口径写，不猜）**：
  · 元素：``<path>`` ``<circle>`` ``<rect>`` ``<ellipse>`` ``<line>``
  · path 指令：``M L H V C S Q T A Z``（大小写=绝对/相对，含隐式重复）
  · 属性：``fill`` ``fill-rule`` ``stroke`` ``stroke-width`` ``stroke-linecap``
         ``stroke-linejoin``；**根元素属性会被子元素继承**（Tabler 就是把
         ``stroke="currentColor" stroke-width="2"`` 写在 <svg> 上的）
  · 自动跳过不可见元素：``fill="none" stroke="none"``（Tabler 每个文件第一个 path
    是 ``M0 0h24v24H0z`` 的透明包围盒，就是这个要被跳过）
  · 本模块扩展：``data-cut="1"`` → 该元素作为**挖空**（负空间），只减掉它**之前**画的内容

**两种填充规则（都实现了）**：
  · ``fill-rule="nonzero"``（SVG 默认）：真·扫描线 + **绕序累加**，所以
    "同一 d 内多个子路径、反向绕序挖孔"的实心图标（Tabler filled 全是这个画法）能正确出孔；
  · ``fill-rule="evenodd"``：子路径异或（自绘图标的月牙/环用）。

渲染管线（与 ``temp/gen_wx_icons2.py`` 同思路，但输入是矢量而非位图遮罩）：
  设计网格用户单位 → 放大 ss 倍画布做**几何级**光栅化 → BOX 面积平均降采样（=精确覆盖率）
  → α 对比度整形 + 去雀斑 → 按 ``--color`` 烘焙纯色（RGB 恒等于该颜色，只有 alpha 变化）。
"""
import math
import re
import numpy as np
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw

# --------------------------------------------------------------------------- #
# 1. path 解析
# --------------------------------------------------------------------------- #
_TOK = re.compile(r'[MmZzLlHhVvCcSsQqTtAa]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?')
_CUBIC_STEPS = 24      # 三次贝塞尔采样段数（8x 超采样下足够平滑，弧长自适应再加密）
_QUAD_STEPS = 16
_ARC_STEPS_PER_RAD = 16.0

SNAP_LO, SNAP_HI = 0.40, 0.60     # α 对比度整形的过渡带（见 _snap_alpha）


def _n_steps(pts, base):
    """按弦长自适应顶点数（大圆弧采样密一点，短线段不浪费）。"""
    L = 0.0
    for a, b in zip(pts, pts[1:]):
        L += abs(b[0] - a[0]) + abs(b[1] - a[1])
    return max(6, min(base * 3, int(base + L * 1.6)))


def _cubic(p0, p1, p2, p3, n=None):
    n = n or _n_steps([p0, p1, p2, p3], _CUBIC_STEPS)
    out = []
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        x = (mt ** 3) * p0[0] + 3 * (mt ** 2) * t * p1[0] + 3 * mt * (t ** 2) * p2[0] + (t ** 3) * p3[0]
        y = (mt ** 3) * p0[1] + 3 * (mt ** 2) * t * p1[1] + 3 * mt * (t ** 2) * p2[1] + (t ** 3) * p3[1]
        out.append((x, y))
    return out


def _quad(p0, p1, p2, n=None):
    n = n or _n_steps([p0, p1, p2], _QUAD_STEPS)
    out = []
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        x = (mt ** 2) * p0[0] + 2 * mt * t * p1[0] + (t ** 2) * p2[0]
        y = (mt ** 2) * p0[1] + 2 * mt * t * p1[1] + (t ** 2) * p2[1]
        out.append((x, y))
    return out


def _arc(p0, rx, ry, phi_deg, large, sweep, p1):
    """SVG 端点参数化椭圆弧 → 采样点（含终点）。"""
    x1, y1 = p0
    x2, y2 = p1
    rx, ry = abs(rx), abs(ry)
    if rx < 1e-12 or ry < 1e-12 or (abs(x1 - x2) < 1e-12 and abs(y1 - y2) < 1e-12):
        return [p1]
    phi = math.radians(phi_deg)
    cosp, sinp = math.cos(phi), math.sin(phi)
    dx2, dy2 = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    x1p = cosp * dx2 + sinp * dy2
    y1p = -sinp * dx2 + cosp * dy2
    lam = (x1p / rx) ** 2 + (y1p / ry) ** 2
    if lam > 1:
        s = math.sqrt(lam)
        rx *= s
        ry *= s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(0.0, num / den)) * (-1 if large == sweep else 1)
    cxp = co * rx * y1p / ry
    cyp = -co * ry * x1p / rx
    cx = cosp * cxp - sinp * cyp + (x1 + x2) / 2.0
    cy = sinp * cxp + cosp * cyp + (y1 + y2) / 2.0

    def angle(ux, uy, vx, vy):
        d = (ux * vx + uy * vy) / (math.hypot(ux, uy) * math.hypot(vx, vy))
        a = math.acos(max(-1.0, min(1.0, d)))
        if ux * vy - uy * vx < 0:
            a = -a
        return a

    th1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dth = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dth > 0:
        dth -= 2 * math.pi
    elif sweep and dth < 0:
        dth += 2 * math.pi
    n = max(8, min(180, int(abs(dth) * _ARC_STEPS_PER_RAD)))
    pts = []
    for i in range(1, n + 1):
        t = th1 + dth * i / n
        ex = cosp * rx * math.cos(t) - sinp * ry * math.sin(t) + cx
        ey = sinp * rx * math.cos(t) + cosp * ry * math.sin(t) + cy
        pts.append((ex, ey))
    return pts


def parse_path(d):
    """SVG path d → 子路径列表 ``[ (points, closed), ... ]``（曲线/弧已采样成折线）。"""
    toks = _TOK.findall(d or '')
    pos = 0
    last = None
    last_ctrl = None
    subs = []
    cur = None
    x = y = 0.0
    sx = sy = 0.0

    def need(n):
        nonlocal pos
        if pos + n > len(toks):
            raise ValueError('path 参数不足: %s' % d[:80])
        vals = [float(v) for v in toks[pos:pos + n]]
        pos += n
        return vals

    def start_sub(px, py):
        nonlocal cur
        cur = [[(px, py)], False]
        subs.append(cur)

    def add(p):
        if cur is None:
            start_sub(p[0], p[1])
        else:
            cur[0].append(p)

    while pos < len(toks):
        t = toks[pos]
        if len(t) == 1 and t.isalpha():
            cmd = t
            pos += 1
        else:
            if last is None:
                raise ValueError('path 必须以命令字母开头')
            cmd = 'L' if last == 'M' else ('l' if last == 'm' else last)
        last = cmd
        cu = cmd.upper()
        rel = cmd.islower()
        if cu == 'M':
            nx, ny = need(2)
            if rel:
                nx += x
                ny += y
            x, y = nx, ny
            sx, sy = x, y
            start_sub(x, y)
            last_ctrl = None
        elif cu == 'L':
            nx, ny = need(2)
            if rel:
                nx += x
                ny += y
            x, y = nx, ny
            add((x, y))
            last_ctrl = None
        elif cu == 'H':
            (nx,) = need(1)
            x = x + nx if rel else nx
            add((x, y))
            last_ctrl = None
        elif cu == 'V':
            (ny,) = need(1)
            y = y + ny if rel else ny
            add((x, y))
            last_ctrl = None
        elif cu in ('C', 'S'):
            if cu == 'C':
                a = need(6)
                p1 = (a[0] + x, a[1] + y) if rel else (a[0], a[1])
                p2 = (a[2] + x, a[3] + y) if rel else (a[2], a[3])
                p3 = (a[4] + x, a[5] + y) if rel else (a[4], a[5])
            else:                                   # S：第一控制点 = 上一点的镜像
                a = need(4)
                if last_ctrl is not None and last in 'CcSs':
                    p1 = (2 * x - last_ctrl[0], 2 * y - last_ctrl[1])
                else:
                    p1 = (x, y)
                p2 = (a[0] + x, a[1] + y) if rel else (a[0], a[1])
                p3 = (a[2] + x, a[3] + y) if rel else (a[2], a[3])
            for pt in _cubic((x, y), p1, p2, p3):
                add(pt)
            last_ctrl = p2
            x, y = p3
        elif cu in ('Q', 'T'):
            if cu == 'Q':
                a = need(4)
                p1 = (a[0] + x, a[1] + y) if rel else (a[0], a[1])
                p2 = (a[2] + x, a[3] + y) if rel else (a[2], a[3])
            else:
                a = need(2)
                if last_ctrl is not None and last in 'QqTt':
                    p1 = (2 * x - last_ctrl[0], 2 * y - last_ctrl[1])
                else:
                    p1 = (x, y)
                p2 = (a[0] + x, a[1] + y) if rel else (a[0], a[1])
            for pt in _quad((x, y), p1, p2):
                add(pt)
            last_ctrl = p1
            x, y = p2
        elif cu == 'A':
            a = need(7)
            ex, ey = a[5], a[6]
            if rel:
                ex += x
                ey += y
            for pt in _arc((x, y), a[0], a[1], a[2], int(a[3]) != 0, int(a[4]) != 0, (ex, ey)):
                add(pt)
            x, y = ex, ey
            last_ctrl = None
        elif cu == 'Z':
            if cur is not None:
                cur[1] = True
            x, y = sx, sy
            last_ctrl = None
        else:
            raise ValueError('不支持的 path 指令 %r' % cu)
    return subs


# --------------------------------------------------------------------------- #
# 2. 光栅化（全部在 ss 倍超采样画布上做**几何级**栅格化）
# --------------------------------------------------------------------------- #
def _circle_pts(cx, cy, rx, ry=0.0, n=72):
    ry = ry or rx
    pts = [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n))
           for i in range(n)]
    pts.append(pts[0])
    return pts


def _rect_pts(x, y, w, h, r):
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    if r <= 0:
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
    pts = []
    for cx, cy, a0, a1 in [(x + w - r, y + r, -90, 0), (x + w - r, y + h - r, 0, 90),
                           (x + r, y + h - r, 90, 180), (x + r, y + r, 180, 270)]:
        for i in range(0, 9):
            a = math.radians(a0 + (a1 - a0) * i / 8.0)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    pts.append(pts[0])
    return pts


def _elem_subpaths(el):
    tag = el.tag.split('}')[-1].lower()
    g = el.get
    if tag == 'path':
        return parse_path(g('d'))
    if tag == 'circle':
        return [(_circle_pts(float(g('cx', 0)), float(g('cy', 0)), float(g('r', 0))), True)]
    if tag == 'ellipse':
        return [(_circle_pts(float(g('cx', 0)), float(g('cy', 0)),
                             float(g('rx', 0)), float(g('ry', 0))), True)]
    if tag == 'rect':
        return [(_rect_pts(float(g('x', 0)), float(g('y', 0)),
                           float(g('width', 0)), float(g('height', 0)),
                           float(g('rx', 0) or 0)), True)]
    if tag == 'line':
        return [([(float(g('x1', 0)), float(g('y1', 0))),
                  (float(g('x2', 0)), float(g('y2', 0)))], False)]
    raise ValueError('不支持的 SVG 元素 <%s>' % tag)


def _fill_evenodd(subpaths, S):
    from PIL import ImageChops
    acc = None
    for pts, _c in subpaths:
        if len(pts) < 3:
            continue
        m = Image.new('1', (S, S), 0)
        ImageDraw.Draw(m).polygon(pts, fill=1)
        acc = m if acc is None else ImageChops.logical_xor(acc, m)
    if acc is None:
        return np.zeros((S, S), dtype=bool)
    return np.asarray(acc.convert('L')) > 0


def _fill_nonzero(subpaths, S):
    """扫描线 + 绕序累加（nonzero winding）——实心图标的'同 d 内反向子路径挖孔'靠这个。"""
    edges = []
    for pts, closed in subpaths:
        if len(pts) < 2:
            continue
        seq = list(pts) + ([pts[0]] if closed else [])
        for a, b in zip(seq, seq[1:]):
            if a[1] != b[1]:
                edges.append((a[0], a[1], b[0], b[1]))
    mask = np.zeros((S, S), dtype=bool)
    if not edges:
        return mask
    E = np.asarray(edges, dtype=np.float64)
    y0, y1, x0, x1 = E[:, 1], E[:, 3], E[:, 0], E[:, 2]
    up = y1 > y0
    for row in range(S):
        y = row + 0.5
        cross = ((y0 <= y) & (y1 > y)) | ((y1 <= y) & (y0 > y))
        if not cross.any():
            continue
        yy0, yy1, xx0, xx1 = y0[cross], y1[cross], x0[cross], x1[cross]
        xs = xx0 + (y - yy0) * (xx1 - xx0) / (yy1 - yy0)
        w = np.where(up[cross], 1.0, -1.0)
        order = np.argsort(xs)
        xs = xs[order]
        inside = np.cumsum(w[order]) != 0
        idx = np.where(inside)[0]
        for i in idx:
            if i + 1 >= len(xs):
                break
            a = int(math.ceil(xs[i] - 0.5))
            b = int(math.floor(xs[i + 1] - 0.5))
            if b >= a:
                mask[row, max(0, a):min(S, b + 1)] = True
    return mask


def _stroke_mask(subpaths, w, S, linecap='round', linejoin='round'):
    m = Image.new('1', (S, S), 0)
    d = ImageDraw.Draw(m)
    r = max(0.5, w / 2.0)
    for pts, closed in subpaths:
        if len(pts) == 1:
            d.ellipse([pts[0][0] - r, pts[0][1] - r, pts[0][0] + r, pts[0][1] + r], fill=1)
            continue
        seq = list(pts) + ([pts[0]] if closed else [])
        for a, b in zip(seq, seq[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy)
            if L < 1e-9:
                continue
            nx, ny = -dy / L * r, dx / L * r
            d.polygon([(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny),
                       (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)], fill=1)
        # 顶点补圆 → 圆角折点；开放路径两端补圆 → 圆头（linecap=butt 时不补端点）
        verts = list(seq)
        if not closed and linecap == 'butt':
            verts = verts[1:-1]
        if verts:
            for p in verts:
                d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=1)
    return np.asarray(m.convert('L')) > 0


def _elem_mask(el, k, S, stroke_base_ss, base_units):
    """单元素 → bool 遮罩（True = 上色）。"""
    subpaths = [([(px * k, py * k) for px, py in sp[0]], sp[1]) for sp in _elem_subpaths(el)]
    stroke = el.get('stroke')
    if base_units <= 0:
        base_units = 2.0
    if stroke and stroke.strip().lower() not in ('none', ''):
        w = el.get('stroke-width')
        ratio = (float(w) / base_units) if w else 1.0
        return _stroke_mask(subpaths, max(1.0, stroke_base_ss * ratio), S,
                            el.get('stroke-linecap', 'round'),
                            el.get('stroke-linejoin', 'round'))
    rule = (el.get('fill-rule') or 'nonzero').lower()
    if rule == 'evenodd':
        return _fill_evenodd(subpaths, S)
    return _fill_nonzero(subpaths, S)


# --------------------------------------------------------------------------- #
# 3. α 整形
# --------------------------------------------------------------------------- #
def _snap_alpha(a, lo=None, hi=None):
    """把"覆盖率"整形成"接近二值、但保留亚像素位置"的 alpha。

    为什么：8× 超采样 + 面积平均给的是真实覆盖率，但一条细线的边缘像素大多落在 0.2~0.8，
    中间值像素占比很高（22px 图标能到 20%+）：既显得"糊"，也会触发质检噪声。
    只把 [lo,hi] 之外的覆盖率推到 0/255，[lo,hi] 内线性映射（0.5 → 0.5，边沿位置不失真），
    过渡带 ≈0.2 像素 → 中间值像素减半以上，视觉依旧平滑（不是硬阈值二值化）。
    最后去雀斑：把"8 邻域无内容"的孤立半透明像素清零。
    """
    c = np.asarray(a).astype(np.float32) / 255.0
    lo = SNAP_LO if lo is None else lo
    hi = SNAP_HI if hi is None else hi
    al = np.round(np.clip((c - lo) / (hi - lo), 0.0, 1.0) * 255.0).astype(np.uint8)
    solid = al > 0
    nb = np.zeros_like(solid)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nb |= np.roll(np.roll(solid, dy, axis=0), dx, axis=1)
    al[(al < 255) & solid & ~nb] = 0
    return al


# --------------------------------------------------------------------------- #
# 4. 对外入口
# --------------------------------------------------------------------------- #
_INHERIT = ('fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin',
            'fill-rule', 'data-cut')


def render_svg(svg_text, size, color=(255, 255, 255), ss=8, canvas=None, grid=None,
               snap=True, stroke_px=None):
    """SVG 文本 → RGBA 图。RGB 恒等于 color，alpha = 覆盖率。

    size    : 正方形边长（像素）；产出图严格 size×size
    canvas  : (w,h) 非正方形画布：按 min(w,h) 渲染后**等比居中留白**（禁止拉伸变形）
    stroke_px: 直接指定基准线宽像素（不传则按基准单位换算 + 半像素对齐）
    线宽规则：基准 = 根节点 data-base-stroke，缺省取根节点 stroke-width，再缺省 1.75；
              px = max(1, round(基准 × size / 网格 × 2) / 2)
    """
    root = ET.fromstring(svg_text)
    vb = [float(v) for v in re.split(r'[\s,]+', (root.get('viewBox') or '0 0 24 24').strip()) if v]
    gw = grid or (vb[2] if len(vb) == 4 else 24.0)
    base_attr = root.get('data-base-stroke') or root.get('stroke-width') or '1.75'
    base = float(re.sub(r'[^0-9.]', '', base_attr) or 1.75)
    S = int(size * ss)
    k = S / gw
    if stroke_px is None:
        stroke_px = max(1.0, round(base * size / gw * 2) / 2.0)
    stroke_base_ss = stroke_px * ss

    inherit = {a: root.get(a) for a in _INHERIT if root.get(a) is not None}
    acc = np.zeros((S, S), dtype=bool)
    for el in list(root):
        if not isinstance(el.tag, str):
            continue
        tag = el.tag.split('}')[-1].lower()
        if tag.startswith('#'):                      # 注释
            continue
        # 继承根属性（子元素覆盖）
        for a, v in inherit.items():
            if el.get(a) is None:
                el.set(a, v)
        fill = (el.get('fill') or '').strip().lower()
        stroke = (el.get('stroke') or '').strip().lower()
        if fill in ('none', '') and stroke in ('none', ''):
            continue                                 # 不可见元素（Tabler 的透明包围盒）
        if fill == 'none':
            el.set('fill', 'none')
        m = _elem_mask(el, k, S, stroke_base_ss, base)
        if el.get('data-cut') in ('1', 'true'):
            acc &= ~m
        else:
            acc |= m

    alpha = Image.fromarray(np.where(acc, 255, 0).astype(np.uint8), 'L').resize(
        (size, size), Image.BOX)
    if snap:
        alpha = Image.fromarray(_snap_alpha(alpha), 'L')
    if canvas:
        cw, ch = int(canvas[0]), int(canvas[1])
        if (cw, ch) != (size, size):
            base_img = Image.new('L', (cw, ch), 0)
            base_img.paste(alpha, ((cw - size) // 2, (ch - size) // 2))
            alpha = base_img

    w, h = alpha.size
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = color[0], color[1], color[2]
    arr[..., 3] = np.asarray(alpha, dtype=np.uint8)
    return Image.fromarray(arr, 'RGBA')


def render_file(path, size, color=(255, 255, 255), **kw):
    """按路径读 SVG 文件再渲染（省得调用方到处 open）。"""
    with open(path, encoding='utf-8') as f:
        return render_svg(f.read(), size, color, **kw)
