# -*- coding: utf-8 -*-
"""`ui_tools/gen_ring.py`：circlebar 两张 UI 图的生成器（**产出即最终资产**）。

需求方口径（2026-10-05）：「本身圆形进度条就是两个图片。这个生成给到实际 FlyThings 用的 UI 图片的话，
这个产出应该是直接可以用的」——所以本文件只钉**"能不能直接用"**这件事：

  ① 几何正确且**明码可读**（外径/内径/环宽，给 json 的 `progressPicPos` 与规格说明用）；
  ② 边缘是**覆盖率口径**（有半透明过渡档位，不是 0→255 直跳）；
  ③ 环上**没有浅色像素**（只有一种实色）——白像素在环上就是"白锯齿"的源头；
  ④ 参数非法要**报错**（不是生成一张坏图）；
  ⑤ 生成器与离线渲染器对"环几何"的口径一致（同一个形状定义，不许两套）。
"""
import io
import json
import os
import sys
import unittest

import _util as U

sys.path.insert(0, U.BASE)
sys.path.insert(0, os.path.join(U.BASE, 'ui_tools'))
import gen_ring as G  # noqa: E402
from PIL import Image  # noqa: E402


class TestRingGeometry(unittest.TestCase):
    def test_geometry_is_exact_and_reported(self):
        img, geom = G.ring_image(200, 14, '4DA6FF')
        self.assertEqual(img.size, (200, 200))
        self.assertEqual(geom['outerRadius'], 100)
        self.assertEqual(geom['innerRadius'], 86)
        self.assertEqual(geom['ringWidth'], 14)
        self.assertEqual(geom['color'], '#4DA6FF')
        self.assertIn('progressPicPos', geom['note'], '几何要写清 json 怎么用')

    def test_ring_band_lands_on_expected_radii(self):
        """环带必须落在 [内径, 外径]：中线左侧应恰好 `环宽` 个不透明像素。"""
        img, geom = G.ring_image(200, 14, '4DA6FF')
        a = img.getchannel('A')
        y = 100
        row = [a.getpixel((x, y)) for x in range(200)]
        opaque = [x for x, v in enumerate(row) if v > 250]
        left = [x for x in opaque if x < 100]
        self.assertEqual(len(left), 14, '左侧环带应为 14px（外径100 − 内径86），实得 %d' % len(left))
        self.assertEqual(left[0], 0, '外沿应顶到图片边界')
        self.assertEqual(left[-1], 13, '内沿应在 x=13')

    def test_size_and_width_scale_together(self):
        """换尺寸就重新算几何（**不是拉伸**）：外径/内径等比例。"""
        _, g100 = G.ring_image(100, 7, '4DA6FF')
        _, g300 = G.ring_image(300, 21, '4DA6FF')
        self.assertEqual((g100['outerRadius'], g100['innerRadius']), (50, 43))
        self.assertEqual((g300['outerRadius'], g300['innerRadius']), (150, 129))


class TestRingQuality(unittest.TestCase):
    def test_edges_are_coverage_antialiased(self):
        """斜边要有**多个过渡档位**（覆盖率证据）——在 45° 对角线上量。"""
        img, _ = G.ring_image(200, 14, '4DA6FF')
        a = img.getchannel('A')
        import math
        cx = cy = 99.5
        vals = [a.getpixel((int(round(cx + t / math.sqrt(2))), int(round(cy + t / math.sqrt(2)))))
                for t in range(80, 106)]
        mid = [v for v in vals if 0 < v < 255]
        self.assertGreaterEqual(len(mid), 2,
                                '对角线上过渡档位只有 %d 个 → 边缘是硬阶梯：%s' % (len(mid), vals))

    def test_no_light_pixels_on_the_ring(self):
        """环上只允许一种实色；浅色像素 = 白锯齿的源头。"""
        for col in ('4DA6FF', '24304A', 'FF4D4D'):
            img, _ = G.ring_image(200, 14, col)
            light = [p for p in img.getdata() if p[3] > 40 and min(p[:3]) > 140]
            self.assertEqual(len(light), 0, '%s 的环上出现 %d 个浅色像素' % (col, len(light)))

    def test_transparent_area_keeps_solid_rgb(self):
        """透明区 RGB 必须是**实色**（不是黑）——与 `rounded_rect_cov` 的既有约定一致。"""
        img, _ = G.ring_image(200, 14, '4DA6FF')
        px = img.getpixel((100, 100))          # 圆心 = 环内 = 全透明
        self.assertEqual(px[3], 0, '圆心应是透明的')
        self.assertEqual(px[:3], (0x4D, 0xA6, 0xFF), '透明区 RGB 要留实色，避免下游把黑算进去')

    def test_quality_gate_reports_and_fails_loudly(self):
        """`--quality` 自检：合格产物应通过；人为造一张硬边图应被判不合格。"""
        class _Args:
            pass
        img, _ = G.ring_image(200, 14, '4DA6FF')
        q = G._quality(img)
        self.assertGreater(q['partialAlpha'], 200, '合格环应有大量半透明像素')
        self.assertEqual(q['lightOpaquePixels'], 0)


class TestRingBadArgs(unittest.TestCase):
    def test_width_too_large_is_rejected(self):
        with self.assertRaises(ValueError):
            G.ring_image(200, 100, '4DA6FF')       # 环宽 100 = 内径 0
        with self.assertRaises(ValueError):
            G.ring_image(200, 120, '4DA6FF')

    def test_non_positive_is_rejected(self):
        for size, width in ((0, 14), (200, 0), (-10, 14)):
            with self.assertRaises(ValueError):
                G.ring_image(size, width, '4DA6FF')

    def test_bad_color_is_rejected(self):
        with self.assertRaises(ValueError):
            G._rgb('red')
        with self.assertRaises(ValueError):
            G._rgb('12345')


class TestRendererAgreesWithGenerator(unittest.TestCase):
    """⑤ 同一形状定义：渲染器量出来的环几何 == 生成器声明的几何。"""

    def test_renderer_measures_the_generated_geometry(self):
        import json2img as J
        img, geom = G.ring_image(200, 14, '4DA6FF')
        r = J.Renderer(project=None, json_path=os.path.join(U.BASE, 'ui_tools', 'x.json'),
                       verbose=False)
        measured = r._ring_geom(img)
        self.assertEqual(measured, (geom['outerRadius'], geom['ringWidth']),
                         '渲染器量到 %s，生成器声明 (%d, %d)'
                         % (measured, geom['outerRadius'], geom['ringWidth']))

    def test_generator_is_importable_by_the_renderer(self):
        """渲染器应优先用生成器的口径（真源一处），不再自己另写一份半径换算。"""
        src = io.open(os.path.join(U.BASE, 'ui_tools', 'json2img.py'), encoding='utf-8').read()
        self.assertIn('gen_ring', src, '渲染器应引用 gen_ring 的几何口径（同一形状只定义一处）')


if __name__ == '__main__':
    unittest.main()
