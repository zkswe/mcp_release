# -*- coding: utf-8 -*-
"""切图抗锯齿契约：FT-008 默认行为不变 + FT-010 强曲率必须明显更准。

为什么钉死（v0.27.75，钟工 2026-09-16 反馈「滑块圆钮 / 开关有锯齿，图片和控件尺寸对不上」）：
  - FT-008（1x 直画 + α 羽化 σ0.5）是**为了几何不漂**才选的（倒角宽度与 1x 直画一致），
    不能改它的默认行为 —— 这里用「α>=128 的轮廓 == 1x 直画」把这条契约钉死；
  - 但它的代价是**强曲率**（圆 / 圆钮 / 药丸 / 细圆条）边缘覆盖率误差大（mean 21~44/255），
    真机上肉眼可见锯齿 → 这类形状必须走 rounded_rect_ss（≥4x SS + LANCZOS）。
  参考真值 = 16x 超采样覆盖率（LANCZOS 缩回），只用 PIL，不需要 numpy。
"""
import os
import sys
import unittest

import _util as U

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except Exception:
    HAS_PIL = False

if HAS_PIL:
    sys.path.insert(0, os.path.join(U.BASE, 'ui_tools'))
    import gen_res as GR

# 强曲率代表形状：(w, h, radius)
STRONG = [(30, 30, 15), (31, 31, 15), (80, 40, 20), (200, 8, 4)]


def _ref_alpha(w, h, radius, ss=16):
    """理想覆盖率：16x 超采样二值 mask → LANCZOS 缩回，返回 [(alpha, ...)] 扁平列表。"""
    big = Image.new('L', (w * ss, h * ss), 0)
    ImageDraw.Draw(big).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1],
                                          radius=radius * ss, fill=255)
    return list(big.resize((w, h), Image.LANCZOS).tobytes())


def _alpha(img):
    return list(img.getchannel('A').tobytes())


def _edge_err(img, w, h, radius):
    """边界带（理想 α 在 4~251 之间）的平均绝对误差，单位 /255。"""
    ref = _ref_alpha(w, h, radius)
    got = _alpha(img)
    diff = [abs(g - r) for g, r in zip(got, ref) if 4 < r < 251]
    return sum(diff) / float(len(diff)), len(diff)


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class TestFt008Contract(unittest.TestCase):
    """FT-008 契约：默认 rounded_rect 的轮廓（α>=128）与 1x 直画逐像素一致（行为不许变）。"""

    def test_outline_matches_direct_1x_draw(self):
        for (w, h, r) in STRONG + [(300, 180, 16), (64, 24, 4)]:
            direct = Image.new('L', (w, h), 0)
            ImageDraw.Draw(direct).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
            got = GR.rounded_rect(w, h, r, (255, 0, 0, 255))
            a = [(x >= 128) for x in _alpha(got)]
            b = [(x >= 128) for x in direct.tobytes()]
            self.assertEqual(a, b, 'FT-008 几何轮廓漂了：%dx%d r=%d' % (w, h, r))


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class TestFt010StrongCurvature(unittest.TestCase):
    """FT-010：强曲率下 rounded_rect_ss 必须明显比 FT-008 准（阈值按实测放宽一倍余量）。"""

    def test_ss_beats_ft008_on_strong_curvature(self):
        for (w, h, r) in STRONG:
            e008, n = _edge_err(GR.rounded_rect(w, h, r, (255, 0, 0, 255)), w, h, r)
            e4, _ = _edge_err(GR.rounded_rect_ss(w, h, r, (255, 0, 0, 255), ss=4), w, h, r)
            self.assertGreater(n, 8, '边界带样本太少，用例失去意义')
            self.assertGreater(e008, 20.0, 'FT-008 在这形状上不该这么准（口径变了？）')
            self.assertLess(e4, 15.0, 'rounded_rect_ss(ss=4) 误差过高：%.1f' % e4)
            self.assertLess(e4 * 2, e008, 'ss 没比 FT-008 好一半：%.1f vs %.1f' % (e4, e008))

    def test_higher_ss_is_not_worse(self):
        for (w, h, r) in STRONG:
            e4, _ = _edge_err(GR.rounded_rect_ss(w, h, r, (255, 0, 0, 255), ss=4), w, h, r)
            e8, _ = _edge_err(GR.rounded_rect_ss(w, h, r, (255, 0, 0, 255), ss=8), w, h, r)
            self.assertLessEqual(e8, e4 + 0.5, 'ss=8 反而更差：%.1f vs %.1f' % (e8, e4))

    def test_size_corners_and_clamps(self):
        img = GR.rounded_rect_ss(31, 31, 15, (66, 201, 255, 255))
        self.assertEqual(img.size, (31, 31))
        self.assertEqual(img.getpixel((0, 0))[3], 0, '四角必须真透明')
        self.assertEqual(img.getpixel((15, 15))[3], 255)
        # 半径超限按药丸/正圆钳制；ss<2 抬到 2（不许退化成 1x）
        self.assertEqual(GR.rounded_rect_ss(40, 20, 999, (0, 0, 0, 255)).size, (40, 20))
        self.assertEqual(GR.rounded_rect_ss(20, 20, 10, (0, 0, 0, 255), ss=1).size, (20, 20))

    def test_semi_transparent_no_dark_halo(self):
        """alpha 预乘：半透明底的边界像素 RGB 不许被透明黑稀释（防暗边 halo）。"""
        img = GR.rounded_rect_ss(40, 40, 20, (255, 0, 0, 128))
        px = img.convert('RGBA').load()
        worst = 0
        for x in range(40):
            for y in range(40):
                r, g, b, a = px[x, y]
                if 4 < a < 251:
                    worst = max(worst, g, b)
        self.assertLess(worst, 8, '边界混进了透明黑（halo），alpha 预乘没生效')


if __name__ == '__main__':
    unittest.main(verbosity=2)
