# -*- coding: utf-8 -*-
"""`json2img` 的 circlebar：**扇形裁剪 + 起始角 + 中心文字/单位**。

2026-10-05 需求方口径：「progress 页面里面的圆形进度条默认渲染的时候需要给个角度确认效果；
另外属性里面是带了中间显示的文字和单位的信息」。

改前三个缺陷（都在本文件钉住）：
  ① 只画**整圈**、且 arc 的 bbox 少了 1px（实测左边多出一段实心）—— 没有扇形裁剪；
  ② **起始角写死 −90**，没读 json 的 `startAngle`，也没读 `maxAngle`；
  ③ 环宽用「4% 直径」近似（实测 `pb_ring.png` 是 **外半径 100 / 环宽 14** = 7% 直径），
     且 **中心文字完全没画**（`textType`/`unit`/`textSize`/`textColor` 全部忽略）。
"""
import io
import json
import math
import os
import sys
import unittest

import _util as U

sys.path.insert(0, U.BASE)
sys.path.insert(0, os.path.join(U.BASE, 'ui_tools'))
import json2img as J  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

BOX = (140, 240, 200, 200)          # left, top, w, h
RING = (77, 166, 255, 255)          # pb_ring 主色
RING_BG = (36, 48, 74, 255)         # pb_ring_bg 主色


class CircleBarBase(unittest.TestCase):
    def setUp(self):
        self.tmp = U.project()
        self.imgdir = os.path.join(self.tmp, 'resources', 'images')
        os.makedirs(self.imgdir, exist_ok=True)

    def tearDown(self):
        U.cleanup(self.tmp)

    def ring(self, name, color, r_out=100, r_in=86):
        """造一张与 pb_ring 同构的环图：外沿顶到图片边界、无 AA（便于按像素判角度）。"""
        size = r_out * 2
        im = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse([0, 0, size - 1, size - 1], fill=color)
        inner = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(inner).ellipse([r_out - r_in, r_out - r_in,
                                       size - 1 - (r_out - r_in), size - 1 - (r_out - r_in)],
                                      fill=color)
        # 用内圆"挖洞"：先把外圆贴上，再把内圆区域清成透明
        mask = Image.new('L', (size, size), 255)
        ImageDraw.Draw(mask).ellipse([r_out - r_in, r_out - r_in,
                                      size - 1 - (r_out - r_in), size - 1 - (r_out - r_in)],
                                     fill=0)
        im.putalpha(mask)
        p = os.path.join(self.imgdir, name)
        im.save(p)
        return 'images/' + name

    def render(self, node, logic=None):
        left, top, w, h = BOX
        doc = {'resolution': {'width': 480, 'height': 800},
               'position': {'left': 0, 'top': 0, 'width': 480, 'height': 800},
               'backgroundColor': -1,
               'circlebar__1': dict(node, position={'left': left, 'top': top,
                                                    'width': w, 'height': h})}
        jp = os.path.join(self.tmp, 'ui', 'main.json')
        os.makedirs(os.path.dirname(jp), exist_ok=True)
        with io.open(jp, 'w', encoding='utf-8') as f:
            json.dump(doc, f, ensure_ascii=False)
        # ⚠️ `logic=None` = **本工程没有页面逻辑**（要真的没有，不是"这一次不传"）：
        # 同一临时工程里上一次写的 `mainLogic.cc` 必须清掉，否则后续用例会读到它。
        # **删除只能走 `U.rm_in_temp`**（它会先校验目录确实是 `mcp_test_*` 临时工程）——
        # 用例里的"造缺文件场景"绝不允许落到真工程上，那是删历史业务代码（需求方 2026-10-05 提醒）。
        U.rm_in_temp(self.tmp, os.path.join('src', 'logic', 'mainLogic.cc'))
        if logic is not None:
            lf = os.path.join(self.tmp, 'src', 'logic', 'mainLogic.cc')
            os.makedirs(os.path.dirname(lf), exist_ok=True)
            with io.open(lf, 'w', encoding='utf-8') as f:
                f.write(logic)
        out = os.path.join(self.tmp, 'ui', 'main.render.png')
        J.render_one(self.tmp, jp, out, verbose=False)
        with Image.open(out) as im:
            return im.convert('RGBA')

    @staticmethod
    def _is(p, c, tol=16):
        return all(abs(a - b) <= tol for a, b in zip(p[:3], c[:3]))

    def ring_hit(self, im, deg):
        """在环带中线上按屏幕角采样（0=右/90=下/180=左/270=上）→ 是否命中有效环色。"""
        left, top, w, h = BOX
        cx, cy, r = left + w / 2.0, top + h / 2.0, 93.0
        a = math.radians(deg)
        return self._is(im.getpixel((int(cx + r * math.cos(a)), int(cy + r * math.sin(a)))), RING)


class TestSectorClipping(CircleBarBase):
    def test_only_progress_sector_is_drawn(self):
        """进度 25% + maxAngle 360 + startAngle 0 → 只画 0°..90°（顺时针，0 = 3 点钟）。"""
        bg = self.ring('bg.png', RING_BG)
        fg = self.ring('ring.png', RING)
        im = self.render({'backgroundPic': bg, 'progressPic': fg, 'max': 100,
                          'progress': 25, 'maxAngle': 360, 'startAngle': 0,
                          'clockwise': True, 'textType': 0, 'touchRange': {'lower': 0, 'upper': 100},
                          'thumb': {'size': {'width': 0, 'height': 0}, 'normalPic': '',
                                    'pressedPic': ''},
                          'progressPicPos': {'left': 0, 'top': 0, 'width': 0, 'height': 0}})
        self.assertTrue(self.ring_hit(im, 45), '45°（第一象限）应是有效环')
        self.assertFalse(self.ring_hit(im, 135), '135° 超出 25% 扇形，应是背景环')
        self.assertTrue(self._is(im.getpixel((int(BOX[0] + BOX[2] / 2 + 93 * math.cos(math.radians(180))),
                                              int(BOX[1] + BOX[3] / 2))), RING_BG),
                        '180° 应是背景环色')

    def test_start_angle_moves_the_sector(self):
        """`startAngle=-90`（从正上方起）→ 扇形落在 270°(上) 顺时针方向；这是"给个角度确认效果"的依据。

        ⚠️ 采样点要**落在扇形内部**而不是起点那条半径线上：PIL 的 `arc` 在起止角上是零宽线段，
        精确采 270° 会取不到（实测踩到）。
        """
        bg = self.ring('bg.png', RING_BG)
        fg = self.ring('ring.png', RING)
        im = self.render({'backgroundPic': bg, 'progressPic': fg, 'max': 100,
                          'progress': 25, 'maxAngle': 360, 'startAngle': -90,
                          'clockwise': True, 'textType': 0, 'touchRange': {'lower': 0, 'upper': 100},
                          'thumb': {'size': {'width': 0, 'height': 0}, 'normalPic': '',
                                    'pressedPic': ''},
                          'progressPicPos': {'left': 0, 'top': 0, 'width': 0, 'height': 0}})
        self.assertTrue(self.ring_hit(im, 280), '起点（正上方 270°）顺时针 10° 应在扇形内')
        self.assertTrue(self.ring_hit(im, 315), '顺时针 45° 处仍在扇形内')
        self.assertFalse(self.ring_hit(im, 180), '逆时针方向不该被画')

    def test_max_angle_under_360_is_an_open_ring(self):
        """`maxAngle=270` 开口环：进度 100% 也只扫 270°，留出 90° 缺口。"""
        bg = self.ring('bg.png', RING_BG)
        fg = self.ring('ring.png', RING)
        im = self.render({'backgroundPic': bg, 'progressPic': fg, 'max': 100,
                          'progress': 100, 'maxAngle': 270, 'startAngle': -90,
                          'clockwise': True, 'textType': 0, 'touchRange': {'lower': 0, 'upper': 100},
                          'thumb': {'size': {'width': 0, 'height': 0}, 'normalPic': '',
                                    'pressedPic': ''},
                          'progressPicPos': {'left': 0, 'top': 0, 'width': 0, 'height': 0}})
        self.assertTrue(self.ring_hit(im, 280), '起点顺时针 10° 在环内')
        self.assertTrue(self.ring_hit(im, 90), '扫过 270° 应盖到 180°(左) 附近')  # 起点 270 + 270 = 180
        self.assertFalse(self.ring_hit(im, 225), '缺口区（起点的逆时针 45°）不该有有效环')


class TestCenterText(CircleBarBase):
    def _im(self, **extra):
        bg = self.ring('bg.png', RING_BG)
        fg = self.ring('ring.png', RING)
        node = {'backgroundPic': bg, 'progressPic': fg, 'max': 100, 'progress': 70,
                'maxAngle': 360, 'startAngle': -90, 'clockwise': True,
                'textColor': 0xFFFFFF, 'textSize': 24, 'unit': '%',
                'touchRange': {'lower': 0, 'upper': 100},
                'thumb': {'size': {'width': 0, 'height': 0}, 'normalPic': '', 'pressedPic': ''},
                'progressPicPos': {'left': 0, 'top': 0, 'width': 0, 'height': 0}}
        node.update(extra)
        return self.render(node)

    def _center_bright_px(self, im):
        left, top, w, h = BOX
        n = 0
        for yy in range(top + 40, top + h - 40):
            for xx in range(left + 40, left + w - 40):
                r, g, b, a = im.getpixel((xx, yy))
                if r > 180 and g > 180 and b > 180:
                    n += 1
        return n

    def test_text_type_1_draws_number_only(self):
        self.assertGreater(self._center_bright_px(self._im(textType=1)), 20,
                           'textType=1 应在环心画数字')

    def test_text_type_2_draws_number_plus_unit(self):
        """`textType=2` 要多画 `unit` → 亮像素明显多于 textType=1（同字号同进度）。"""
        n1 = self._center_bright_px(self._im(textType=1))
        n2 = self._center_bright_px(self._im(textType=2))
        self.assertGreater(n2, n1 + 5, 'unit 没画出来（textType=2 的亮像素应多于 1：%d vs %d）'
                           % (n2, n1))

    def test_text_type_0_draws_nothing(self):
        self.assertEqual(self._center_bright_px(self._im(textType=0)), 0,
                         'textType=0 不该画中心文字')

    def test_progress_comes_from_logic(self):
        """进度优先取 logic 的 `setProgress()`（json 的 progress 常不是真机初值）。

        判据用**中心文字内容**：json 写 0 + logic 写 70 → 应画 "70%"；两者都读 json → 画 "0%"。
        ⚠️ 两次渲染必须**各自独立的临时工程**（实测踩到：共用目录时上一次写的
        `mainLogic.cc` 会被下一次读走，"无 logic"那次也画成 70%）。
        """
        node = {'caption': 'CbA',            # ⚠️ 必需：logic 的匹配靠 `m<caption>Ptr`
                'id': 20, 'backgroundPic': None, 'progressPic': None,
                'max': 100, 'maxAngle': 360, 'startAngle': -90, 'clockwise': True,
                'textColor': 0xFFFFFF, 'textSize': 24, 'unit': '%', 'textType': 2,
                'touchRange': {'lower': 0, 'upper': 100},
                'thumb': {'size': {'width': 0, 'height': 0}, 'normalPic': '', 'pressedPic': ''},
                'progressPicPos': {'left': 0, 'top': 0, 'width': 0, 'height': 0}}

        def run(logic):
            keep, self.tmp = self.tmp, U.project()      # 换一个干净工程
            try:
                bg = self.ring('bg.png', RING_BG)       # 注意：在新工程里造图
                fg = self.ring('ring.png', RING)
                node2 = dict(node, backgroundPic=bg, progressPic=fg, progress=0)
                jp = os.path.join(self.tmp, 'ui', 'main.json')
                with io.open(jp, 'w', encoding='utf-8') as f:
                    json.dump({'resolution': {'width': 480, 'height': 800},
                               'position': {'left': 0, 'top': 0, 'width': 480, 'height': 800},
                               'backgroundColor': -1,
                               'circlebar__1': dict(node2, position={'left': BOX[0], 'top': BOX[1],
                                                                     'width': BOX[2],
                                                                     'height': BOX[3]})},
                              f, ensure_ascii=False)
                lf = os.path.join(self.tmp, 'src', 'logic', 'mainLogic.cc')
                if logic:
                    os.makedirs(os.path.dirname(lf), exist_ok=True)
                    with io.open(lf, 'w', encoding='utf-8') as f:
                        f.write(logic)
                im = self.render(node2, logic=logic)
                return self._center_bright_px(self.render(node2, logic=logic))
            finally:
                U.cleanup(self.tmp)
                self.tmp = keep

        n_json0 = run(None)
        n_logic = run('static void onUI_init() {\n  if (mCbAPtr) mCbAPtr->setProgress(70);\n}\n')
        self.assertGreater(n_json0, 5, 'json 写 0 → 至少要画 "0%"')
        self.assertNotEqual(n_logic, n_json0,
                            'json 写 0 时应以 logic 的 setProgress(70) 为准（"70%%" 与 "0%%" 应不同）：'
                            '%d vs %d' % (n_logic, n_json0))


class TestRingGeometry(CircleBarBase):
    def test_ring_width_is_measured_not_approximated(self):
        """环宽必须**从图里量**（改前用 4% 直径近似，实测参考图是 7%）。"""
        r = J.Renderer(project=self.tmp, json_path=os.path.join(self.tmp, 'ui', 'x.json'),
                       verbose=False)
        rel = self.ring('ring.png', RING)                   # 外 100 / 内 86 → 环宽 14
        with Image.open(os.path.join(self.imgdir, os.path.basename(rel))) as im:
            geom = r._ring_geom(im)
        self.assertEqual(geom, (100, 14), '量到的环几何应为 (外半径 100, 环宽 14)，实得 %s' % (geom,))


class TestNoWhiteFringeOnRingEdge(CircleBarBase):
    """2026-10-05 需求方报「圆环渲染出来有白色锯齿」—— 根因是**图层贴到自己身上**。

    `draw_circlebar` 原写法 `paste_rgba(layer, sub, 0, 0)`：把 `layer` 贴到它自己，
    而 `paste_rgba` 又拿 `layer` 自身的 α 当遮罩 → **预乘被算两次** →
    源图内沿那排半透明像素（α=48/64/92…）被推成接近纯白 → 肉眼是环内沿一溜白锯齿。
    正确做法是先把遮罩后的有效环贴进**干净的中间层**，再合成到结果图。

    判据：环内沿不许出现"明显比源色亮"的像素 —— 逐像素比对"渲染结果 vs 源图该点颜色"。
    """

    def test_ring_edge_pixels_never_brighter_than_source(self):
        from PIL import ImageChops
        bg = self.ring('bg.png', RING_BG)
        fg = self.ring('ring.png', RING)
        im = self.render({'backgroundPic': bg, 'progressPic': fg, 'max': 100,
                          'progress': 70, 'maxAngle': 360, 'startAngle': -90,
                          'clockwise': True, 'textType': 0,
                          'touchRange': {'lower': 0, 'upper': 100},
                          'thumb': {'size': {'width': 0, 'height': 0}, 'normalPic': '',
                                    'pressedPic': ''},
                          'progressPicPos': {'left': 0, 'top': 0, 'width': 0, 'height': 0}})
        left, top, w, h = BOX
        src = Image.open(os.path.join(self.imgdir, 'ring.png')).convert('RGBA')
        # 亮于"源色"的像素（源色是 RING；背景环更暗）—— 若有白锯齿必然命中
        limit = tuple(min(255, c + 40) for c in RING[:3])
        bad = []
        for yy in range(top, top + h):
            for xx in range(left, left + w):
                r, g, b, a = im.getpixel((xx, yy))
                if a > 60 and all(v > lim for v, lim in zip((r, g, b), limit)):
                    bad.append((xx - left, yy - top, (r, g, b)))
        self.assertEqual(bad[:6], [], '环上出现比源色更亮的像素（白锯齿）：%s' % bad[:6])

    def test_layer_is_not_pasted_onto_itself(self):
        """正面判据：源码里不许出现"把 layer 贴到自己"的那种写法。"""
        src = io.open(os.path.join(U.BASE, 'ui_tools', 'json2img.py'), encoding='utf-8').read()
        self.assertNotIn('paste_rgba(layer if mask is not None else img', src,
                         '又把 layer 贴到自己身上了（预乘会算两次 → 白锯齿）')
        self.assertIn('sub_layer', src, '有效环要先合成到干净中间层')


class TestRingAssetsQuality(CircleBarBase):
    """两张环图**就是最终产物**（需求方 2026-10-05：「本身圆形进度条就是两个图片…产出应该直接可用」）。

    ⚠️ 这一组用**任意可用的环图**做判据，不断言"某个具体资产的像素值"——因为
    「圆环内沿白锯齿」那次**不是资产的问题**：实测旧资产的半透明像素有 1228 个（新 1272），
    AA 本来就在；真凶是渲染器把图层贴到了自己身上（见 `TestNoWhiteFringeOnRingEdge`）。
    把它写成"资产必须带 AA"是为了**锁住这条容易搞错的性质**，避免以后再有人去改资产背锅。
    """

    def test_assets_have_anti_aliased_edges(self):
        """环图边缘必须有**半透明过渡像素**（0<α<255），不是 0→255 直跳。"""
        proj = os.path.join(U.BASE, 'templates', 'DemoControls_V85X', 'resources', 'images')
        checked = 0
        for fn in ('pb_ring.png', 'pb_ring_bg.png'):
            fp = os.path.join(proj, fn)
            if not os.path.isfile(fp):
                continue
            with Image.open(fp) as im:
                a = im.convert('RGBA').getchannel('A')
                h = a.histogram()
                partial = sum(h[1:255])
            self.assertGreater(partial, 200,
                               '%s 的半透明像素只有 %d 个 —— 边缘像硬切（缺覆盖率抗锯齿）'
                               % (fn, partial))
            checked += 1
        if not checked:
            self.skipTest('本仓没有演示环图（判据依赖该资产）')

    def test_assets_have_no_white_pixels(self):
        """环图里不许有接近白色的不透明像素（那两个环只有两种实色）。

        为什么钉：白像素在环上会以"白锯齿"的形式暴露（本次现场现象）；源头若被塞进白像素，
        任何合成次序都救不回来。
        """
        proj = os.path.join(U.BASE, 'templates', 'DemoControls_V85X', 'resources', 'images')
        for fn in ('pb_ring.png', 'pb_ring_bg.png'):
            fp = os.path.join(proj, fn)
            if not os.path.isfile(fp):
                continue
            with Image.open(fp) as im:
                im = im.convert('RGBA')
                light = [p for p in im.getdata() if p[3] > 40 and min(p[:3]) > 140]
            self.assertEqual(len(light), 0, '%s 里有 %d 个浅色不透明像素：%s'
                             % (fn, len(light), light[:3]))


if __name__ == '__main__':
    unittest.main()
