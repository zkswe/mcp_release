# -*- coding: utf-8 -*-
"""AA 边缘客观判据（0 token，纯像素）——RadButton 的「锯齿到底有没有」量化脚本。

用法：
    python aa_measure.py <图.png> --region x0,y0,x1,y1 --fill 2196F3 --bg F5F7FA [--label 名字]

判据（对一个矩形区域内的像素分类）：
    前景像素    与 fill 的每通道差 <= 2
    底色像素    与 bg   的每通道差 <= 2
    中间档像素  两边都不沾 —— 这就是「抗锯齿的中间色」（硬边图像里恒为 0）
    边界像素    4 邻域内同时存在「前景」与「底色」的像素（= 轮廓带）
输出：中间档档数（去重颜色数）、中间档占比 = 中间档像素 / 边界像素
"""
import argparse
import sys
from collections import Counter

from PIL import Image


def parse_hex(s):
    s = s.strip().lstrip('#')
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def near(c, ref, tol=2):
    return all(abs(c[i] - ref[i]) <= tol for i in range(3))


def classify(px, fill, bg, tol=2):
    if near(px, fill, tol):
        return 'F'
    if near(px, bg, tol):
        return 'B'
    return 'M'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('png')
    ap.add_argument('--region', required=True, help='x0,y0,x1,y1（半开区间，屏幕绝对坐标）')
    ap.add_argument('--fill', default='2196F3')
    ap.add_argument('--bg', default='F5F7FA')
    ap.add_argument('--tol', type=int, default=2)
    ap.add_argument('--label', default='')
    a = ap.parse_args()

    x0, y0, x1, y1 = [int(v) for v in a.region.split(',')]
    fill, bg = parse_hex(a.fill), parse_hex(a.bg)
    im = Image.open(a.png).convert('RGB')
    W, H = im.size
    x1, y1 = min(x1, W), min(y1, H)
    px = im.load()

    cls = {}
    for y in range(y0, y1):
        for x in range(x0, x1):
            cls[(x, y)] = classify(px[x, y], fill, bg, a.tol)

    cnt = Counter(cls.values())
    mid_colors = Counter()
    for (x, y), c in cls.items():
        if c == 'M':
            mid_colors[px[x, y]] += 1

    # 边界像素：4 邻域内同时有 F 和 B（只看区域内）
    boundary = 0
    for (x, y), c in cls.items():
        if c != 'M':
            continue
        nb = [cls.get((x + dx, y + dy)) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        nb = [v for v in nb if v]
        if 'F' in nb and 'B' in nb:
            boundary += 1

    total = sum(cnt.values())
    print('== %s  region=%s  size=%dx%d  fill=#%s bg=#%s' %
          (a.label or a.png, a.region, x1 - x0, y1 - y0,
           ''.join('%02X' % v for v in fill), ''.join('%02X' % v for v in bg)))
    print('   前景 %d / 底色 %d / 中间档 %d  (总 %d)' % (cnt['F'], cnt['B'], cnt['M'], total))
    print('   中间档颜色档数 = %d' % len(mid_colors))
    print('   中间档占边界像素比例 = %d/%d = %.1f%%' %
          (boundary, cnt['M'], (100.0 * boundary / cnt['M']) if cnt['M'] else 0.0))
    if mid_colors:
        top = mid_colors.most_common(6)
        print('   中间档样例（像素数降序）：' +
              ', '.join('#%02X%02X%02X x%d' % (c[0], c[1], c[2], n) for c, n in top))
    # 机器可读一行
    print('STATS %s mid=%d levels=%d boundary=%d ratio=%.1f' %
          (a.label or a.png, cnt['M'], len(mid_colors), boundary,
           (100.0 * boundary / cnt['M']) if cnt['M'] else 0.0))


main()
