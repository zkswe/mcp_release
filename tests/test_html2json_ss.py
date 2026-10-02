# -*- coding: utf-8 -*-
"""html2json CSS 出图口径：**一律走 SS**（v0.27.76，2026-09-16 拍板）。

为什么钉死：
  - 需求方拍板：html2json 处理 CSS 效果（渐变/圆角/阴影）出图**一律 SS**（ss=4 = 每像素 16 子采样），
    **不再保留 1x + α 羽化那条路**（这是固定本地脚本的工作，不额外耗 token）；
  - `gen_res.rounded_rect` 的默认行为（FT-008：1x 直画 + α 羽化）**保持不变**—— SS 只在
    ①html2json 自动出图 ②调用方显式 `rounded_rect_ss` / `ss>0` 时生效；
  - 同批收口：旧 `border-radius` 解析只认「数字+px」→ `border-radius:50%` / 无单位认不出 →
该出圆的地方出方角（实测 corner alpha 255，而 `50%` 是设计稿最常见写法）。
参考真值 = 16x 超采样覆盖率（**Image.BOX 面积平均**缩回，与 `test_gen_res_aa.py` 同口径，只用 PIL）。
"""
import os
import shutil
import sys
import tempfile
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
    import html2json as H

# 强曲率（药丸）+ 大半径卡片：html2json 两条 CSS 出图分支的代表形状
PILL = (80, 40, 20)
CARD = (120, 80, 16)
STOPS = [(0.0, (0x2F, 0x6D, 0xF6, 255)), (1.0, (0x42, 0xC9, 0xFF, 255))]


def _ref_alpha(w, h, radius, ss=16):
    """理想覆盖率：16x 超采样二值 mask → **Image.BOX（面积平均）**缩回（与 FT-010 口径一致）。"""
    big = Image.new('L', (w * ss, h * ss), 0)
    ImageDraw.Draw(big).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1],
                                          radius=radius * ss, fill=255)
    return list(big.resize((w, h), Image.BOX).tobytes())


def _rgba_bytes(path):
    """PNG → RGBA 扁平字节（避开 Pillow 14 起弃用的 getdata）。"""
    with Image.open(path) as im:
        return im.convert('RGBA').tobytes()


def _alpha(path):
    raw = _rgba_bytes(path)
    return list(raw[3::4])


def _pix(raw, w, x, y):
    i = (y * w + x) * 4
    return raw[i], raw[i + 1], raw[i + 2], raw[i + 3]


def _edge_err(path, w, h, radius):
    """边界带（理想 α 4~251）的 |Δα| 统计 → (mean, p95, max)。"""
    ref = _ref_alpha(w, h, radius)
    got = _alpha(path)
    d = sorted(abs(g - r) for g, r in zip(got, ref) if 4 < r < 251)
    if not d:
        return 0.0, 0.0, 0.0
    return sum(d) / float(len(d)), d[int(len(d) * 0.95)], d[-1]


def _rgb_dark_max(path, w, h, radius):
    """边界像素的 RGB 必须等于同列内部（不透明）像素的 RGB。

渐变按列恒定 → 偏差只可能来自「边界被透明黑稀释」= 暗边（halo）。0~3 为正常。
    """
    ref = _ref_alpha(w, h, radius)
    raw = _rgba_bytes(path)
    base = {}
    for x in range(w):
        for y in range(h):
            if _pix(raw, w, x, y)[3] == 255:
                base[x] = _pix(raw, w, x, y)[:3]
                break
    worst = 0
    for y in range(h):
        for x in range(w):
            if 4 < ref[y * w + x] < 251 and x in base:
                r, g, b, a = _pix(raw, w, x, y)
                worst = max(worst, abs(r - base[x][0]), abs(g - base[x][1]), abs(b - base[x][2]))
    return worst


def _alpha_diff(a_path, b_path):
    """两图 alpha 的全图 |Δ| → (mean, max)；同算法不同 ss 档的「离理想多远」用。"""
    a, b = _alpha(a_path), _alpha(b_path)
    if len(a) != len(b):
        return 999.0, 999
    d = [abs(x - y) for x, y in zip(a, b)]
    return sum(d) / float(len(d)), max(d)


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class TestSsIsTheOnlyCssPath(unittest.TestCase):
    """html2json 出图档位：SS_DEFAULT / _CSS_SS == 4，且产物必须显著优于老路。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='mcp_ss_')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_ss_is_4(self):
        self.assertEqual(GR.SS_DEFAULT, 4, 'html2json 出图档位应是 4（每像素 16 子采样）')
        self.assertEqual(getattr(H, '_CSS_SS', None), 4, 'html2json 必须透传 SS=4 给 gen_res')

    def test_gradient_pill_goes_through_ss(self):
        w, h, r = PILL
        old = GR.gen_gradient_stops(os.path.join(self.tmp, 'a'), 'old.png', w, h, STOPS,
                                    radius=r, ss=0)          # 老路：1x + α 羽化
        new = GR.gen_gradient_stops(os.path.join(self.tmp, 'b'), 'new.png', w, h, STOPS,
                                    radius=r, ss=GR.SS_DEFAULT)
        e_old = _edge_err(old, w, h, r)
        e_new = _edge_err(new, w, h, r)
        self.assertGreater(e_old[0], 20.0, 'FT-008 口径变了？老路本该 mean>20：%.1f' % e_old[0])
        self.assertLess(e_new[0], 10.0, 'SS 出图误差过高 mean=%.1f p95=%.1f' % e_new[:2])
        self.assertLess(e_new[1], 30.0, 'SS 出图 p95 过高：%.1f' % e_new[1])
        self.assertLess(e_new[0] * 3, e_old[0], 'SS 没比老路好三倍：%.1f vs %.1f' % (e_new[0], e_old[0]))
        # 暗边（halo）回归：边界 RGB 不许被透明黑稀释（列内基准对比）
        self.assertLessEqual(_rgb_dark_max(new, w, h, r), 4,
                             'SS mask 引入了暗边：边界 RGB 偏离列内基准')

    def test_shadow_card_goes_through_ss(self):
        """阴影片（box-shadow → gen_shadow_card）：SS 必须比老路更贴理想（同算法 ss=16 当参照）。"""
        w, h, r = 140, 60, 14
        kw = dict(shadow=(0, 6, 12, (0, 0, 0, 115)), crop=False)
        fill = (0x1E, 0x27, 0x35, 255)
        ref = GR.gen_shadow_card(os.path.join(self.tmp, 'r'), 'ref.png', w, h, r, fill, ss=16, **kw)
        old = GR.gen_shadow_card(os.path.join(self.tmp, 'c'), 'old.png', w, h, r, fill, ss=0, **kw)
        new = GR.gen_shadow_card(os.path.join(self.tmp, 'd'), 'new.png', w, h, r, fill,
                                 ss=GR.SS_DEFAULT, **kw)
        d_old = _alpha_diff(old, ref)
        d_new = _alpha_diff(new, ref)
        self.assertGreater(d_old[1], 100, '老路口径变了？本该有明显边界阶跃 max=%s' % d_old[1])
        self.assertLess(d_new[0], d_old[0], '阴影片 SS 没更准：%.2f vs %.2f' % (d_new[0], d_old[0]))
        self.assertLess(d_new[1], d_old[1], '阴影片 SS 最差像素没变好：%s vs %s' % (d_new[1], d_old[1]))

    def test_shadow_card_size_is_stable(self):
        """crop=False 的「图 == 控件盒」契约不受 SS 影响（调用方按 pad 外扩控件盒）。"""
        kw = dict(shadow=(2, 4, 8, (0, 0, 0, 100)), crop=False)
        a = GR.gen_shadow_card(os.path.join(self.tmp, 'e'), 'a.png', 96, 48, 12,
                               (0x12, 0x1A, 0x29, 255), ss=0, **kw)
        b = GR.gen_shadow_card(os.path.join(self.tmp, 'f'), 'b.png', 96, 48, 12,
                               (0x12, 0x1A, 0x29, 255), ss=4, **kw)
        with Image.open(a) as ia, Image.open(b) as ib:
            self.assertEqual(ia.size, ib.size)
            self.assertEqual(ia.size, (96 + 24, 48 + 24))


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class TestRadiusParsing(unittest.TestCase):
    """border-radius 解析：px / 无单位 / %（50% → 正圆）都要认；认不出才是历史方形 bug。"""

    def test_radius_forms(self):
        self.assertEqual(H._radius_px('border-radius: 50%;', 48, 48), 24, '50% 必须成正圆')
        self.assertEqual(H._radius_px('border-radius:999px;', 80, 40), 20, '药丸：按 min(w,h)/2 钳制')
        self.assertEqual(H._radius_px('border-radius: 12;', 80, 40), 12, '无单位要认（HTML 原型常见）')
        self.assertEqual(H._radius_px('border-radius: 8px 8px 0 0;', 80, 40), 8, '多值取第一段')
        self.assertEqual(H._radius_px('', 80, 40, 0), 0, '无声明 → default')
        self.assertEqual(H._radius_px('background: #fff;', 80, 40, 8), 8, '无 border-radius → default')
        self.assertEqual(H._radius_px('border-radius: 40px;', 30, 30), 15, '超限钳到 min/2')

    def test_percent_circle_really_round(self):
        """端到端：带 50% 的渐变圆角片，四角必须真透明（旧实现只认 px → 方形不透）。"""
        tmp = U.project()
        try:
            html = os.path.join(tmp, 'ui', 'c.html')
            U.write(html, '<div class="screen" data-res="480x272">\n'
                          '  <div class="text" data-caption="C" data-x="10" data-y="10"'
                          ' data-w="48" data-h="48" style="background:'
                          ' linear-gradient(180deg,#22D3EE,#0EA5E9); border-radius: 50%;"></div>\n'
                          '</div>\n')
            r = H.html2json(html, os.path.join(tmp, 'ui', 'c.json'), res='480x272')
            self.assertTrue(r['success'], r)
            png = os.path.join(tmp, 'resources', 'images', 'grad_C_0.png')
            self.assertTrue(os.path.isfile(png), os.listdir(os.path.join(tmp, 'resources', 'images')))
            with Image.open(png).convert('RGBA') as im:
                self.assertEqual(im.size, (48, 48))
                self.assertEqual(im.getpixel((0, 0))[3], 0, '50% 必须是正圆（四角透明）')
                self.assertEqual(im.getpixel((47, 47))[3], 0, '四角都该在圆外')
                self.assertEqual(im.getpixel((24, 24))[3], 255)
                # 覆盖率 ≈ π/4 = 0.785（正圆在方盒内）；方形 bug 时会是 1.0
                opaque = sum(1 for a in _alpha(png) if a >= 128)
                self.assertLess(opaque / float(48 * 48), 0.83, '不是正圆（覆盖率太高）')
                self.assertGreater(opaque / float(48 * 48), 0.74, '圆被削多了（覆盖率太低）')
        finally:
            U.cleanup(tmp)


if __name__ == '__main__':
    unittest.main(verbosity=2)
