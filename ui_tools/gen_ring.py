# -*- coding: utf-8 -*-
"""圆形进度条（`circlebar`）的两张 UI 图生成器 —— **产出即最终资产，可直接放进 FlyThings 工程**。

`circlebar` 本身就是**两张图**：
  · `backgroundPic` = 背景环（**整圈、不裁剪**，垫底表示"满量程"）
  · `progressPic`  = 有效环（引擎按 `progress/max × maxAngle` **扇形裁剪**后上屏）
所以这两张图的尺寸/环宽/配色**就是 UI 的效果本身** —— 生成质量没有"后面再修"的余地。

口径（与全仓 `renderContract.edge-aa` 同源，复用 `gen_res` 的覆盖率实现，不另起一套）：
  · **≥4× 超采样 + 面积平均**，`α = 覆盖率`（连续多档）→ 斜边/圆弧无阶梯；
  · 透明区 RGB 写**实色**（不是黑）：避免 `0,0,0` 落到下游 bbox / 主色统计里（与 `rounded_rect_cov` 一致）；
  · **环 = 外圆覆盖率 − 内圆覆盖率**（相减仍连续），不做"描边带"近似。

⚠️ 为什么不用 `.9.png`：9-patch 是**分区拉伸**——对圆环会让圆弧变直段/椭圆；而本生成器按目标尺寸
现算覆盖率，**任意尺寸/DPI 都是正确几何**，所以"换尺寸"应当**重新生成**而不是拉伸（见 `--help` 的示例）。

用法：
    python ui_tools/gen_ring.py --out <工程>/resources/images --size 200 --width 14 \
        --color 4DA6FF --bg-color 24304A --name pb_ring --bg-name pb_ring_bg
    # 只算几何不落盘（给 json 的 progressPicPos 用）：
    python ui_tools/gen_ring.py --geom --size 200 --width 14
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gen_res as gr                     # noqa: E402
from PIL import Image, ImageChops        # noqa: E402

__version__ = '1.0'


def _rgb(v):
    """`4DA6FF` / `0x4DA6FF` / `(77,166,255)` → (r,g,b)。"""
    if isinstance(v, (tuple, list)):
        return tuple(int(x) for x in v[:3])
    s = str(v).strip().lstrip('#')
    if s.lower().startswith('0x'):
        s = s[2:]
    if len(s) != 6 or any(c not in '0123456789abcdefABCDEF' for c in s):
        raise ValueError('颜色要写 6 位十六进制（如 4DA6FF），实得 %r' % (v,))
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def ring_image(size, width, color, ss=8):
    """生成一张**环**（正圆、外径 == size、环宽 == width）。

    返回 `(RGBA 图, 几何 dict)`；几何里的量直接可用于 json 的 `progressPicPos` 与规格说明。
    """
    size = int(size)
    width = int(width)
    if size <= 0 or width <= 0:
        raise ValueError('size / width 必须是正整数（实得 %r / %r）' % (size, width))
    if width * 2 >= size:
        raise ValueError('环宽 %d 太大（外径 %d）：内径会 <= 0' % (width, size))
    r_out, r_in = size // 2, size // 2 - width
    cov_out = gr.coverage_mask(size, size, size // 2, ss=ss)          # 外圆（内切 = 正圆）
    inner_d = r_in * 2
    cov_in = Image.new('L', (size, size), 0)
    pad = (size - inner_d) // 2
    cov_in.paste(gr.coverage_mask(inner_d, inner_d, inner_d // 2, ss=ss), (pad, pad))
    cov = ImageChops.subtract(cov_out, cov_in)                        # 环（相减仍为覆盖率）
    rgb = _rgb(color)
    img = Image.new('RGBA', (size, size), (rgb[0], rgb[1], rgb[2], 255))
    img.putalpha(cov)
    geom = {
        'size': [size, size],
        'outerRadius': r_out,
        'innerRadius': r_in,
        'ringWidth': width,
        'color': '#%02X%02X%02X' % rgb,
        'note': ('progressPicPos 用 {left:0,top:0,width:%d,height:%d}（== 图尺寸）；'
                 '换尺寸请**重新生成**，不要拉伸' % (size, size)),
    }
    return img, geom


def _quality(path_or_img):
    """质量自检：过渡档位（覆盖率证据）+ 是否有浅色像素（环上只有一种实色）。"""
    img = path_or_img
    if isinstance(path_or_img, str):
        img = Image.open(path_or_img)
    im = img.convert('RGBA')
    h = im.getchannel('A').histogram()
    partial = sum(h[1:255])
    light = [p for p in im.getdata() if p[3] > 40 and min(p[:3]) > 140]
    return {'partialAlpha': partial, 'opaque': h[255], 'transparent': h[0],
            'lightOpaquePixels': len(light)}


def main(argv=None):
    ap = argparse.ArgumentParser(description='圆形进度条的两张 UI 图（背景环 + 有效环）')
    ap.add_argument('--out', default='', help='输出目录（= 工程的 resources/images）')
    ap.add_argument('--name', default='pb_ring', help='有效环文件名（自动补 .png）')
    ap.add_argument('--bg-name', default='pb_ring_bg', help='背景环文件名（自动补 .png）')
    ap.add_argument('--bg-color', default='24304A', help='背景环颜色（6 位十六进制）')
    ap.add_argument('--size', type=int, default=200, help='外径（= 控件盒边长），默认 200')
    ap.add_argument('--width', type=int, default=14, help='环宽，默认 14')
    ap.add_argument('--color', default='4DA6FF', help='有效环颜色（6 位十六进制）')
    ap.add_argument('--ss', type=int, default=8, help='超采样倍数（默认 8，≥4 才够覆盖率口径）')
    ap.add_argument('--geom', action='store_true', help='只打印几何，不生成文件')
    ap.add_argument('--json', default='', help='把几何写成 json（给消费方读）')
    a = ap.parse_args(argv)

    if a.geom:
        _, geom = ring_image(a.size, a.width, a.color, ss=a.ss)
        print(json.dumps(geom, ensure_ascii=False, indent=1))
        return 0

    if not a.out:
        print('[FATAL] 需要 --out <工程>/resources/images（或 --geom 只看几何）')
        return 2
    os.makedirs(a.out, exist_ok=True)
    result = {}
    for nm, col, role in ((a.name, a.color, 'progressPic'), (a.bg_name, a.bg_color, 'backgroundPic')):
        img, geom = ring_image(a.size, a.width, col, ss=a.ss)
        fp = os.path.join(a.out, nm if nm.endswith('.png') else nm + '.png')
        img.save(fp)
        q = _quality(img)
        result[role] = {'file': fp, 'bytes': os.path.getsize(fp), 'geom': geom, 'quality': q}
        print('写入 %s  %dx%d  %d B  半透明像素 %d  浅色像素 %d'
              % (fp, a.size, a.size, os.path.getsize(fp), q['partialAlpha'],
                 q['lightOpaquePixels']))
    if a.json:
        io.open(a.json, 'w', encoding='utf-8').write(
            json.dumps(result, ensure_ascii=False, indent=1) + '\n')
        print('几何 -> %s' % a.json)
    # 失败即非 0 退出（可直接被门禁/脚本消费，不静默）
    bad = [r for r, v in result.items() if v['quality']['partialAlpha'] < 3
           or v['quality']['lightOpaquePixels']]
    if bad:
        print('[FAIL] 质量自检不通过：%s' % '、'.join(bad))
        return 1
    print('[OK] 两张环图已生成（覆盖率口径；可直接作为 circlebar 的 backgroundPic / progressPic）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
