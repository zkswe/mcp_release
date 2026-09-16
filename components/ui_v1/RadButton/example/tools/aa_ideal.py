# -*- coding: utf-8 -*-
"""圆角边缘「与理想覆盖率」的误差（0 token，纯像素）——RadButton 抗锯齿的客观分。

做法：把被检控件盒 + 半径还原成几何，对每个像素做 16x16 超采样求出**理想覆盖率**，
     理想色 = mix(fill, bg, 覆盖率)（与设备上的混色公式同口径 sRGB 线性混合），
     再拿设备实际像素减理想色，统计「AA 带」（0.02<覆盖率<0.98 的像素）上的误差。

用法：
    python aa_ideal.py <png> --box x,y,w,h --radius R --corner tl [--fill 2196F3] [--bg F5F7FA] [--label 名字]

输出：AA 带像素数 / 平均误差 / 最大误差 / 误差>30 的像素数（= 肉眼可见的错）+ 机器可读行。
对照口径（tools/ui_tools/gen_res.py FT-010 实测）：1x 直画 + α 羽化 平均 28~50（p95 79~150）；
≥4x 超采样 + LANCZOS 缩回 平均 6~15。
"""
import argparse
from PIL import Image

SS = 16


def parse_hex(s):
    s = s.strip().lstrip('#')
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('png')
    ap.add_argument('--box', required=True, help='x,y,w,h 控件盒（屏幕绝对坐标，连续空间 [x,x+w) x [y,y+h)）')
    ap.add_argument('--radius', type=int, required=True)
    ap.add_argument('--corner', default='tl', choices=['tl', 'tr', 'bl', 'br'])
    ap.add_argument('--fill', default='2196F3')
    ap.add_argument('--bg', default='F5F7FA')
    ap.add_argument('--label', default='')
    a = ap.parse_args()

    x, y, w, h = [int(v) for v in a.box.split(',')]
    r = a.radius
    fill, bg = parse_hex(a.fill), parse_hex(a.bg)
    cx = x + r if a.corner in ('tl', 'bl') else x + w - r
    cy = y + r if a.corner in ('tl', 'tr') else y + h - r
    sgn_x = -1 if a.corner in ('tl', 'bl') else 1
    sgn_y = -1 if a.corner in ('tl', 'tr') else 1

    im = Image.open(a.png).convert('RGB')
    px = im.load()
    x0 = cx - r if sgn_x < 0 else cx
    x1 = cx if sgn_x < 0 else cx + r
    y0 = cy - r if sgn_y < 0 else cy
    y1 = cy if sgn_y < 0 else cy + r

    inv, area = 1.0 / SS, 1.0 / (SS * SS)
    errs = []
    worst = (0, None)
    for py in range(int(y0), int(y1)):
        for pxi in range(int(x0), int(x1)):
            hit = 0
            for i in range(SS):
                fx = pxi + (i + 0.5) * inv
                if (sgn_x < 0 and fx > cx) or (sgn_x > 0 and fx < cx):
                    continue
                for j in range(SS):
                    fy = py + (j + 0.5) * inv
                    if (sgn_y < 0 and fy > cy) or (sgn_y > 0 and fy < cy):
                        continue
                    if (fx - cx) ** 2 + (fy - cy) ** 2 <= r * r:
                        hit += 1
            cov = hit * area
            if not (0.02 < cov < 0.98):
                continue                        # 只看 AA 带（纯内/纯外不参与）
            ideal = tuple(fill[k] * cov + bg[k] * (1 - cov) for k in range(3))
            act = px[pxi, py]
            e = max(abs(act[k] - ideal[k]) for k in range(3))
            errs.append(e)
            if e > worst[0]:
                worst = (e, (pxi, py, act, tuple(round(v) for v in ideal), round(cov, 3)))

    if not errs:
        print('== %s: 该角没有 AA 带像素（半径/坐标是否写错？）' % (a.label or a.png))
        return
    errs.sort()
    n = len(errs)
    mean = sum(errs) / n
    p95 = errs[int(n * 0.95)] if n > 1 else errs[0]
    over30 = sum(1 for e in errs if e > 30)
    print('== %s  corner=%s r=%d  box=%s' % (a.label or a.png, a.corner, r, a.box))
    print('   AA 带像素 = %d ；与理想覆盖率误差：平均 %.1f / p95 %d / 最大 %d ；>30 的像素 %d 个（%.0f%%）'
          % (n, mean, p95, errs[-1], over30, 100.0 * over30 / n))
    print('   最差像素：x=%d y=%d 实际#%02X%02X%02X 理想#%02X%02X%02X 覆盖率%.3f'
          % (worst[1][0], worst[1][1], worst[1][2][0], worst[1][2][1], worst[1][2][2],
             worst[1][3][0], worst[1][3][1], worst[1][3][2], worst[1][4]))
    print('IDEAL %s aa_band=%d mean=%.1f p95=%d max=%d over30=%d' %
          (a.label or a.png, n, mean, p95, errs[-1], over30))


main()
