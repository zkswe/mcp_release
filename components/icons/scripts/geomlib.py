# -*- coding: utf-8 -*-
"""geomlib —— 图标几何助手（纯几何，无第三方依赖）

本模块只做两件事：
  1. 把"设计单位"（默认 24 网格，天气图标用 100 网格）的坐标拼成 **SVG 元素字符串**；
  2. 提供常用图元（太阳/云/水滴/雪花/月牙/星/闪电/箭头/齿轮/心形…）的参数化构造。

约定（与 README §3 对齐）：
  - 角度：屏幕坐标系（y 向下）。``a=0°`` 指向右，``a=90°`` 指向**下**，``a=-90°`` 指向上。
  - 填充：闭合图形默认 ``fill``；线框用 ``stroke``（``currentColor`` 由渲染器换成 --color）。
  - 元素顺序即绘制顺序；``cut=True`` 表示该元素**挖空**（负空间），只影响它之前画的内容。
"""

import math

# --------------------------------------------------------------------------- #
# 基础：属性拼装 / 元素输出
# --------------------------------------------------------------------------- #
def fmt(v):
    if isinstance(v, str):
        return v
    s = ('%.3f' % float(v)).rstrip('0').rstrip('.')
    if s in ('-0', ''):
        s = '0'
    return s


def _attr_str(extra):
    out = []
    for k, v in extra.items():
        if v is None:
            continue
        out.append('%s="%s"' % (k, fmt(v)))
    return (' ' + ' '.join(out)) if out else ''


def _el(tag, base, kw, cut):
    a = dict(base or {})
    a.update(kw)
    if cut:
        a['data-cut'] = '1'
    return '<%s%s/>' % (tag, _attr_str(a))


def P(d, a=None, cut=False, **kw):
    """<path>"""
    base = {'d': d}
    if a:
        base.update(a)
    return _el('path', base, kw, cut)


def C(cx, cy, r, a=None, cut=False, **kw):
    """<circle>"""
    base = {'cx': cx, 'cy': cy, 'r': r}
    if a:
        base.update(a)
    return _el('circle', base, kw, cut)


def R(x, y, w, h, rx=0, a=None, cut=False, **kw):
    """<rect>"""
    base = {'x': x, 'y': y, 'width': w, 'height': h}
    if rx:
        base['rx'] = rx
    if a:
        base.update(a)
    return _el('rect', base, kw, cut)


def LN(x1, y1, x2, y2, a=None, cut=False, **kw):
    """<line>"""
    base = {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2}
    if a:
        base.update(a)
    return _el('line', base, kw, cut)


def ST(w=1.75, cap='round', join='round'):
    """线框样式（stroke=currentColor 由渲染器按 --color 烘焙）"""
    return {'stroke': 'currentColor', 'stroke-width': w,
            'stroke-linecap': cap, 'stroke-linejoin': join}


def FL(rule='nonzero'):
    """填充样式"""
    d = {'fill': 'currentColor'}
    if rule != 'nonzero':
        d['fill-rule'] = rule
    return d


NONE = {'fill': 'none'}


# --------------------------------------------------------------------------- #
# 路径构造
# --------------------------------------------------------------------------- #
def poly_d(pts, close=True):
    d = 'M' + ' '.join('%s,%s' % (fmt(x), fmt(y)) for x, y in pts[:1])
    if len(pts) > 1:
        d += ' L' + ' '.join('%s,%s' % (fmt(x), fmt(y)) for x, y in pts[1:])
    return d + (' Z' if close else '')


def arc_pts(cx, cy, r, a0, a1, steps=None):
    """圆弧采样点（角度制，屏幕坐标；a0→a1 递增 = 屏幕顺时针）。"""
    if steps is None:
        steps = max(4, int(abs(a1 - a0) / 4.0))
    pts = []
    for i in range(steps + 1):
        a = math.radians(a0 + (a1 - a0) * i / float(steps))
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def arc_d(cx, cy, r, a0, a1, steps=None):
    """圆弧 → path d（开放折线，用 stroke 画就是圆弧线）。"""
    return poly_d(arc_pts(cx, cy, r, a0, a1, steps), close=False)


def circle_pts(cx, cy, r, n=72):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
            for i in range(n)] + [(cx + r, cy)]


def ellipse_pts(cx, cy, rx, ry, rot_deg=0.0, n=32):
    """可旋转椭圆（transform 支持不了时用采样点代替）。"""
    c, s = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        pts.append((cx + x * c - y * s, cy + x * s + y * c))
    pts.append(pts[0])
    return pts


def circle_circle(c0, r0, c1, r1):
    """两圆交点（0/1/2 个），返回按 y 升序。"""
    dx, dy = c1[0] - c0[0], c1[1] - c0[1]
    d = math.hypot(dx, dy)
    if d < 1e-9 or d > r0 + r1 or d < abs(r0 - r1):
        return []
    a = (r0 * r0 - r1 * r1 + d * d) / (2 * d)
    h2 = r0 * r0 - a * a
    h = math.sqrt(max(0.0, h2))
    px, py = c0[0] + a * dx / d, c0[1] + a * dy / d
    nx, ny = -dy / d, dx / d
    pts = [(px + h * nx, py + h * ny), (px - h * nx, py - h * ny)]
    return sorted(pts, key=lambda p: p[1])


def cloud_d(circles, yb):
    """云：若干圆 + 平底。circles=[(cx,cy,r),...] 从左到右；yb=底线 y。

    轮廓 = 左圆左缘 → 左圆弧 → 相邻圆上交点 → … → 右圆右缘 → 底线闭合。
    最左/最右圆必须与底线相切（cy+r == yb），这样两侧是竖直线（与设计稿一致）。
    """
    cs = sorted(circles, key=lambda c: c[0])
    x0 = cs[0][0] - cs[0][2]
    x1 = cs[-1][0] + cs[-1][2]
    d = 'M%s,%s L%s,%s' % (fmt(x0), fmt(yb), fmt(x0), fmt(cs[0][1]))
    for i in range(len(cs) - 1):
        a, b = cs[i], cs[i + 1]
        pts = circle_circle((a[0], a[1]), a[2], (b[0], b[1]), b[2])
        if not pts:                      # 不相交（外部相切）→ 直接连线
            d += ' L%s,%s' % (fmt(b[0]), fmt(b[1]))
            continue
        ix, iy = pts[0]                  # 上交点
        d += ' A%s %s 0 0 1 %s,%s' % (fmt(a[2]), fmt(a[2]), fmt(ix), fmt(iy))
    d += ' A%s %s 0 0 1 %s,%s' % (fmt(cs[-1][2]), fmt(cs[-1][2]), fmt(x1), fmt(cs[-1][1]))
    d += ' L%s,%s Z' % (fmt(x1), fmt(yb))
    return d


def crescent_d(cout, rout, ccut, rcut):
    """月牙（外圆减内圆）的**轮廓路径**（可 stroke 成线框月牙，也可 fill 成实心月牙）。"""
    pts = circle_circle(cout, rout, ccut, rcut)
    if len(pts) < 2:
        return poly_d(circle_pts(cout[0], cout[1], rout), close=True)
    p_hi, p_lo = pts[1], pts[0]          # pts[0] y 更小（上交点）
    a_hi = math.degrees(math.atan2(p_hi[1] - cout[1], p_hi[0] - cout[0]))
    a_lo = math.degrees(math.atan2(p_lo[1] - cout[1], p_lo[0] - cout[0]))
    b_hi = math.degrees(math.atan2(p_hi[1] - ccut[1], p_hi[0] - ccut[0]))
    b_lo = math.degrees(math.atan2(p_lo[1] - ccut[1], p_lo[0] - ccut[0]))
    # 外圆：从上交点向"减角度"方向走长弧到下交点（经过左侧）；
    # 内圆：反向（从下交点向"减角度"方向走到上交点，经过左侧）—— 两头相接合成月牙轮廓
    outer = arc_pts(cout[0], cout[1], rout, a_hi, a_lo - 360, None)
    inner = arc_pts(ccut[0], ccut[1], rcut, b_lo, b_hi - 360, None)
    return poly_d(outer + inner, close=True)


def star_pts(cx, cy, r_out, r_in, n=5, rot=-90):
    pts = []
    for i in range(n * 2):
        a = math.radians(rot + i * 180.0 / n)
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def heart_pts(cx, cy, size, n=120):
    """经典心形解析曲线（无拼接断点），归一化到 size 见方并居中于 (cx,cy)。"""
    raw = []
    for i in range(n + 1):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        raw.append((x, y))
    xs = [p[0] for p in raw]
    ys = [p[1] for p in raw]
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    k = size / max(w, h)
    mx = (max(xs) + min(xs)) / 2.0
    my = (max(ys) + min(ys)) / 2.0
    return [(cx + (x - mx) * k, cy - (y - my) * k) for x, y in raw]


# --------------------------------------------------------------------------- #
# 常用图元（返回元素列表）
# --------------------------------------------------------------------------- #
def sun_els(cx, cy, r, n=8, rin=1.45, rout=2.15, sw=2.6, solid=True):
    """太阳：实心圆 + n 根放射线（round cap）。"""
    els = [C(cx, cy, r, FL() if solid else ST(sw))]
    for i in range(n):
        a = math.radians(-90 + i * 360.0 / n)
        els.append(LN(cx + math.cos(a) * r * rin, cy + math.sin(a) * r * rin,
                      cx + math.cos(a) * r * rout, cy + math.sin(a) * r * rout, ST(sw)))
    return els


def drop_els(cx, cy, r, scale=1.0):
    """水滴（设计稿同构：下部实心圆 + 上部三角尖；尖长 2.05r，太长在小尺寸下会变成"气球"）。"""
    rr = r * scale
    return [
        C(cx, cy, rr, FL()),
        P(poly_d([(cx, cy - rr * 2.05), (cx - rr * 0.99, cy - rr * 0.02),
                  (cx + rr * 0.99, cy - rr * 0.02)], close=True), FL()),
    ]


def snow_els(cx, cy, r, arms=6, sw=5.5, tick_at=0.55, tick_len=0.34, tick_ang=52):
    """雪花：n 根主轴 + 每轴两根小叉（小尺寸下比花瓣更清晰）。"""
    els = []
    for i in range(arms):
        a = -90 + i * 360.0 / arms
        ax, ay = math.radians(a), math.radians(a)
        ex, ey = cx + r * math.cos(ax), cy + r * math.sin(ay)
        els.append(LN(cx, cy, ex, ey, ST(sw)))
        bx, by = cx + r * tick_at * math.cos(ax), cy + r * tick_at * math.sin(ay)
        for s in (-1, 1):
            ba = math.radians(a + s * tick_ang)
            els.append(LN(bx, by, bx + r * tick_len * math.cos(ba),
                          by + r * tick_len * math.sin(ba), ST(sw)))
    return els


def bolt_els(x0, y0, size, sw=None):
    """闪电（Feather zap 同构，等比缩放到 size 高）。"""
    k = size / 20.0
    pts = [(13, 2), (3, 14), (12, 14), (11, 22), (21, 10), (12, 10)]
    return [P(poly_d([(x0 + (x - 12) * k, y0 + (y - 12) * k) for x, y in pts], close=True), FL())]


def chevron_els(direction, style='ios', span=6.6, cy=12, cx=12):
    """箭头尖（head）：ios=圆头线框；material=实心填充（厚度 2.4）。"""
    rot = {'up': -90, 'down': 90, 'left': 180, 'right': 0}[direction]
    if style == 'ios':
        tip = (cx + span * math.cos(math.radians(rot)), cy + span * math.sin(math.radians(rot)))
        e1 = (cx + span * math.cos(math.radians(rot + 135)), cy + span * math.sin(math.radians(rot + 135)))
        e2 = (cx + span * math.cos(math.radians(rot - 135)), cy + span * math.sin(math.radians(rot - 135)))
        return [P(d='M%s,%s L%s,%s L%s,%s' % (fmt(e1[0]), fmt(e1[1]), fmt(tip[0]), fmt(tip[1]),
                                              fmt(e2[0]), fmt(e2[1])), a=ST())]
    # material：实心 V（外折线 - 内折线）
    t = 2.4
    r = math.radians(rot)
    def pt(dx, dy):
        return (cx + dx * math.cos(r) - dy * math.sin(r), cy + dx * math.sin(r) + dy * math.cos(r))
    pts = [pt(0, -span), pt(span, 0), pt(0, -span + t * 1.42), pt(-span, 0)]
    return [P(poly_d(pts, close=True), FL())]


def arrow_els(direction, style='ios', length=15.0, cx=12, cy=12, head=5.2):
    """整支箭头（含杆）。ios=线框圆头；material=实心（粗杆 + 实心三角头）。"""
    rot = math.radians({'up': -90, 'down': 90, 'left': 180, 'right': 0}[direction])
    def pt(x, y):
        return (cx + x * math.cos(rot) - y * math.sin(rot), cy + x * math.sin(rot) + y * math.cos(rot))
    L = length / 2.0
    if style == 'ios':
        return [P(d='M%s,%s L%s,%s' % (fmt(pt(-L, 0)[0]), fmt(pt(-L, 0)[1]),
                                       fmt(pt(L, 0)[0]), fmt(pt(L, 0)[1])), a=ST()),
                P(d='M%s,%s L%s,%s L%s,%s' % (
                    fmt(pt(L - head, -head)[0]), fmt(pt(L - head, -head)[1]),
                    fmt(pt(L, 0)[0]), fmt(pt(L, 0)[1]),
                    fmt(pt(L - head, head)[0]), fmt(pt(L - head, head)[1])), a=ST())]
    # material：粗杆（圆角矩形）+ 实心三角头
    sw, hw, hl = 3.0, 5.6, 6.4
    body = [pt(-L, -sw / 2), pt(L - hl, -sw / 2), pt(L - hl, sw / 2), pt(-L, sw / 2)]
    tri = [pt(L, 0), pt(L - hl, -hw / 2), pt(L - hl, hw / 2)]
    return [P(poly_d(body, close=True), FL()), P(poly_d(tri, close=True), FL())]


def _cog_pts(cx, cy, r_out=9.2, r_ring=6.9, teeth=8, tooth_w=11.0):
    """齿轮齿形（梯形齿，角度以度为单位：齿顶宽 tooth_w，齿根宽 1.7×tooth_w）。"""
    pts = []
    for i in range(teeth):
        a = -90 + i * 360.0 / teeth
        for da, rr in ((-tooth_w * 0.85, r_ring - 0.25), (-tooth_w / 2, r_out),
                       (tooth_w / 2, r_out), (tooth_w * 0.85, r_ring - 0.25)):
            ar = math.radians(a + da)
            pts.append((cx + rr * math.cos(ar), cy + rr * math.sin(ar)))
    return pts


def gear_els(cx, cy, r_out=9.2, r_ring=6.9, r_hole=3.3, teeth=8, tooth_w=11.0, solid=False):
    """齿轮：material=实心齿盘 + 中心挖孔（负空间）；ios=同齿形的**轮廓线**（线稿齿轮）。"""
    pts = _cog_pts(cx, cy, r_out, r_ring, teeth, tooth_w)
    if not solid:
        return [P(poly_d(pts, close=True), a=ST()), C(cx, cy, r_hole, ST())]
    return [P(poly_d(pts, close=True), FL()), C(cx, cy, r_ring - 0.25, FL()),
            C(cx, cy, r_hole, cut=True, fill='currentColor')]


def bolt_round_els(x0, y0, size):
    return bolt_els(x0, y0, size)
