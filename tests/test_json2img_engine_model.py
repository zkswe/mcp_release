# -*- coding: utf-8 -*-
"""`json2img` 的 seekbar 必须复现**引擎语义**（`ui_schema.json.renderContract`）。

为什么单独钉一组（2026-10-05）：`json2img` 是**无设备时唯一的视觉验收手段**，但它原先的
`draw_seekbar` 用的是与真机不符的模型 —— 实测四条差异（见 `CONSOLIDATION_VISUAL.md` §3 P4）：

| 维度 | 改前（错） | 引擎（对） | 规格条目 |
|---|---|---|---|
| 填充宽 | `round(w·frac)` | **`floor(w·frac)`** | `rounding` |
| 填充图 | `resize(..., NEAREST)` 拉伸 | **1:1 原样贴 + 裁剪** | `progress-clip` |
| 滑块尺寸 | 用 `thumb.size` 缩放 | **按 PNG 原尺寸** | `thumb-size` |
| 滑块左沿 | `round(w·frac) − tw/2` | **`floor((w−tw)·frac)`** | `thumb-size` |

后果最重的是第 2 条：NEAREST 下采样会把切图圆角**抽掉**（10% 进度时圆角 100% 消失），
于是"离线看着对、真机不对"—— 拿它的输出做验收会**掩盖**真问题。
"""
import io
import json
import os
import sys
import unittest

import _util as U

sys.path.insert(0, U.BASE)
sys.path.insert(0, os.path.join(U.BASE, 'ui_tools'))
import json2img as J  # noqa: E402
from PIL import Image  # noqa: E402

BOX = (16, 120, 448, 32)          # left, top, w, h
FILL = (46, 139, 255, 255)        # 填充色
TRACK = (36, 47, 73, 255)         # 轨道色
THUMB = (232, 241, 255, 255)      # 滑块色


class SeekbarRenderBase(unittest.TestCase):
    """造一个最小工程（ui/*.json + resources/images/*），只渲染、不联网、不碰设备。"""

    def setUp(self):
        self.tmp = U.project()
        self.imgdir = os.path.join(self.tmp, 'resources', 'images')
        os.makedirs(self.imgdir, exist_ok=True)

    def tearDown(self):
        U.cleanup(self.tmp)

    def asset(self, name, size, color, radius=0):
        """写一张纯色图；`radius>0` 时四角透明（模拟切图自带的圆角）。"""
        from PIL import ImageDraw
        im = Image.new('RGBA', size, color)
        if radius > 0:
            mask = Image.new('L', size, 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1],
                                                   radius=radius, fill=255)
            im.putalpha(mask)
        p = os.path.join(self.imgdir, name)
        im.save(p)
        return 'images/' + name

    def render(self, node, page='main'):
        """把单个控件放进一页并渲染 → PIL 图。"""
        left, top, w, h = BOX
        doc = {
            'resolution': {'width': 480, 'height': 800},
            'position': {'left': 0, 'top': 0, 'width': 480, 'height': 800},
            'backgroundColor': -16777216,                  # 0xFF000000 不透明黑（保证底色可读）
            'seekbar__1': dict(node, position={'left': left, 'top': top, 'width': w, 'height': h}),
        }
        jp = os.path.join(self.tmp, 'ui', '%s.json' % page)
        os.makedirs(os.path.dirname(jp), exist_ok=True)
        with io.open(jp, 'w', encoding='utf-8') as f:
            json.dump(doc, f, ensure_ascii=False)
        out = os.path.join(self.tmp, 'ui', '%s.render.png' % page)
        J.render_one(self.tmp, jp, out, verbose=False)
        with Image.open(out) as im:
            return im.convert('RGBA')

    def px(self, im, x, y):
        return im.getpixel((x, y))

    def is_fill(self, p):
        return all(abs(a - b) <= 2 for a, b in zip(p[:3], FILL[:3])) and p[3] > 250

    def is_track(self, p):
        return all(abs(a - b) <= 2 for a, b in zip(p[:3], TRACK[:3])) and p[3] > 250


class TestProgressClip(SeekbarRenderBase):
    """`rounding` + `progress-clip`：填充宽 = `floor(w×frac)`，且是**裁剪**不是拉伸。"""

    def test_width_uses_floor_not_round(self):
        """48×32 盒、进度 50% → `floor(24)` = 24；用 `round` 也会得 24，所以要看 60%："""
        left, top, w, h = BOX
        track = self.asset('t.png', (w, h), TRACK)
        fill = self.asset('f.png', (w, h), FILL)
        im = self.render({'backgroundPic': track, 'progressPic': fill,
                          'defProgress': 60, 'max': 100,
                          'thumb': {'size': {'width': 0, 'height': 0}}})
        y = top + h // 2
        # floor(448×0.6) = 268 → 可见填充是 rel 0..267，rel 268 起是轨道
        self.assertTrue(self.is_fill(self.px(im, left + 267, y)), 'rel 267 应为填充')
        self.assertTrue(self.is_track(self.px(im, left + 268, y)), 'rel 268 应为轨道（= floor 的证据）')

    def test_source_pixels_are_one_to_one_not_resized(self):
        """把有效图做成 4 段色带：1:1 贴 → 各段边界位置不变；拉伸 → 边界会按比例挪。

        NEAREST 拉伸还会把圆角抽掉，所以这里同时验"色带边界"与"圆角保留"。
        """
        left, top, w, h = BOX
        from PIL import ImageDraw
        band = Image.new('RGBA', (w, h), FILL)
        d = ImageDraw.Draw(band)
        d.rectangle([0, 0, 99, h - 1], fill=(255, 0, 0, 255))
        d.rectangle([100, 0, 199, h - 1], fill=(0, 255, 0, 255))
        d.rectangle([200, 0, 299, h - 1], fill=(0, 0, 255, 255))
        p = os.path.join(self.imgdir, 'band.png')
        band.save(p)
        track = self.asset('t.png', (w, h), TRACK)
        im = self.render({'backgroundPic': track, 'progressPic': 'images/band.png',
                          'defProgress': 100, 'max': 100,
                          'thumb': {'size': {'width': 0, 'height': 0}}})
        y = top + h // 2
        self.assertEqual(self.px(im, left + 50, y)[:3], (255, 0, 0), '第 1 段')
        self.assertEqual(self.px(im, left + 150, y)[:3], (0, 255, 0), '第 2 段')
        self.assertEqual(self.px(im, left + 250, y)[:3], (0, 0, 255), '第 3 段')
        # 1:1：色带边界必须落在原图位置（拉伸会把 100 挪到 112）
        self.assertEqual(self.px(im, left + 99, y)[:3], (255, 0, 0), 'rel 99 仍是红（1:1 未被拉伸）')
        self.assertEqual(self.px(im, left + 100, y)[:3], (0, 255, 0), 'rel 100 起是绿')

    def test_rounded_fill_keeps_its_corner_at_low_progress(self):
        """NEAREST 拉伸会把圆角抽掉（10% 时完全消失）—— 1:1 裁剪必须保留它。"""
        left, top, w, h = BOX
        track = self.asset('t.png', (w, h), TRACK)
        fill = self.asset('f.png', (w, h), FILL, radius=16)
        im = self.render({'backgroundPic': track, 'progressPic': fill,
                          'defProgress': 10, 'max': 100,
                          'thumb': {'size': {'width': 0, 'height': 0}}})
        # 圆角处（rel 0,0）应仍是透明 → 露出轨道色；若是 NEAREST 拉伸会变成不透明填充色
        self.assertTrue(self.is_track(self.px(im, left, top)), '左端圆角应露出轨道（圆角未被抽掉）')

    def test_fill_narrower_than_box_is_not_scaled_up(self):
        """图比盒窄：引擎 1:1 贴（露轨道），**不许**缩放撑满。"""
        left, top, w, h = BOX
        track = self.asset('t.png', (w, h), TRACK)
        narrow = self.asset('n.png', (100, h), FILL)
        im = self.render({'backgroundPic': track, 'progressPic': narrow,
                          'defProgress': 100, 'max': 100,
                          'thumb': {'size': {'width': 0, 'height': 0}}})
        y = top + h // 2
        self.assertTrue(self.is_fill(self.px(im, left + 99, y)), '图内 99 应为填充')
        self.assertTrue(self.is_track(self.px(im, left + 120, y)),
                        '超出图宽的部分应露轨道（1:1 贴，不放大）')


class TestThumbGeometry(SeekbarRenderBase):
    """`thumb-size`：尺寸由 **PNG** 决定，左沿 = `floor((盒宽−图宽)×进度/max)`。"""

    def _im(self, frac):
        left, top, w, h = BOX
        track = self.asset('t.png', (w, h), TRACK)
        fill = self.asset('f.png', (w, h), FILL)
        thumb = self.asset('th.png', (32, 32), THUMB, radius=16)
        return self.render({'backgroundPic': track, 'progressPic': fill,
                            'defProgress': frac, 'max': 100,
                            'thumb': {'size': {'width': 32, 'height': 32},
                                      'normalPic': thumb, 'pressedPic': ''}})

    def test_left_edge_is_floor_of_box_minus_thumb_times_frac(self):
        """60% → `floor((448−32)×0.6)` = `floor(249.6)` = 249。"""
        left, top, w, h = BOX
        im = self._im(60)
        y = top + h // 2
        # 滑块亮芯（圆钮中心行）应覆盖 rel 249..280
        self.assertTrue(self.px(im, left + 249, y)[:3] == THUMB[:3], 'rel 249 应为滑块')
        self.assertTrue(self.px(im, left + 280, y)[:3] == THUMB[:3], 'rel 280 应为滑块')
        self.assertFalse(self.px(im, left + 248, y)[:3] == THUMB[:3], 'rel 248 不该是滑块')

    def test_zero_and_full_stay_inside_the_box(self):
        left, top, w, h = BOX
        y = top + h // 2
        im0 = self._im(0)
        self.assertTrue(self.px(im0, left, y)[:3] == THUMB[:3], '0% 时滑块左沿贴盒左')
        im1 = self._im(100)
        # 100% → floor((448−32)×1) = 416 → 右沿 447，**完整不出界**（旧模型会半出界）
        self.assertTrue(self.px(im1, left + 416, y)[:3] == THUMB[:3], '100% 时 rel 416 应为滑块')
        self.assertTrue(self.px(im1, left + 447, y)[:3] == THUMB[:3], '100% 时 rel 447 应为滑块（不出界）')

    def test_thumb_size_declared_but_png_wins(self):
        """声明 16 而 PNG 是 32 → 按 **PNG** 画（真机忽略 thumb.size），并如实记账。"""
        left, top, w, h = BOX
        track = self.asset('t.png', (w, h), TRACK)
        fill = self.asset('f.png', (w, h), FILL)
        thumb = self.asset('th.png', (32, 32), THUMB, radius=16)
        rep = J.Report()
        jp = os.path.join(self.tmp, 'ui', 'main.json')
        os.makedirs(os.path.dirname(jp), exist_ok=True)
        with io.open(jp, 'w', encoding='utf-8') as f:
            json.dump({'resolution': {'width': 480, 'height': 800},
                       'position': {'left': 0, 'top': 0, 'width': 480, 'height': 800},
                       'backgroundColor': -16777216,
                       'seekbar__1': {'backgroundPic': track, 'progressPic': fill,
                                      'defProgress': 0, 'max': 100,
                                      'thumb': {'size': {'width': 16, 'height': 16},
                                                'normalPic': thumb, 'pressedPic': ''},
                                      'position': {'left': left, 'top': top,
                                                   'width': w, 'height': h}}}, f)
        out = os.path.join(self.tmp, 'ui', 'main.render.png')
        J.render_one(self.tmp, jp, out, report=rep, verbose=False)
        with Image.open(out) as im:
            im = im.convert('RGBA')
        y = top + h // 2
        # 声明 16 但 PNG 32 → 滑块仍应是 32 宽：rel 0 与 rel 31 都是滑块色
        self.assertTrue(self.px(im, left + 31, y)[:3] == THUMB[:3],
                        '应按 PNG 原尺寸（32）画，而不是声明的 16')
        notes = json.dumps(rep.as_dict(), ensure_ascii=False)
        self.assertIn('thumb.size', notes, '声明与 PNG 不一致要如实记账（不静默）')

    def test_tall_thumb_in_short_box_is_centred_and_cropped(self):
        """盒 32 高、图 48 高 → 居中裁（引擎行为），不该被压扁。"""
        left, top, w, h = BOX
        track = self.asset('t.png', (w, h), TRACK)
        fill = self.asset('f.png', (w, h), FILL)
        big = self.asset('big.png', (48, 48), THUMB, radius=24)
        im = self.render({'backgroundPic': track, 'progressPic': fill,
                          'defProgress': 0, 'max': 100,
                          'thumb': {'size': {'width': 48, 'height': 48},
                                    'normalPic': big, 'pressedPic': ''}})
        y = top + h // 2
        # 左沿 floor((448−48)×0) = 0；48 宽的图在 32 高的盒里居中 → 上下各裁 8px
        self.assertTrue(self.px(im, left + 24, top)[:3] == THUMB[:3],
                        '盒顶应是滑块（图被居中裁，不是压扁）')
        self.assertTrue(self.px(im, left + 24, top + h - 1)[:3] == THUMB[:3], '盒底同理')


class TestFontFallback(SeekbarRenderBase):
    """工程内无字体时必须**兜底到系统中文**并如实记账（否则整页中文渲染成方框）。

    为什么钉：模板工程（`templates/DemoControls_*`）**不带字体**，改前渲染出的图"结构对但读不出字"，
    等于没法验收文案 —— 而 `json2img` 是无设备时唯一的视觉验收手段。
    """

    def test_falls_back_to_system_font_and_records_it(self):
        rep = J.Report()
        r = J.Renderer(project=self.tmp, json_path=os.path.join(self.tmp, 'ui', 'x.json'),
                       align_mode='measured', report=rep, verbose=False)
        self.assertEqual(r._font_dirs(), [], '前提：本工程的夹具里没有 font 目录')
        fp = r.resolve_font()
        if fp is None:
            self.skipTest('本机没有可用的系统中文字体（该兜底无法验证）')
        self.assertTrue(os.path.isfile(fp), '兜底字体必须是真实存在的文件')
        notes = json.dumps(rep.as_dict(), ensure_ascii=False)
        self.assertIn('系统字体', notes, '用了兜底字体必须如实记账（不静默）')
        self.assertIn('度量', notes, '记账要说明"字形度量不保证与设备一致"')


class TestSubBoxTextLayout(SeekbarRenderBase):
    """`iconPosition` / `textPosition` 子盒：文字必须按 `textPosition` 排版（2026-10-05 用户报告）。

    现象：带图标按键的文字**压在图标上**。根因是渲染器整条忽略了 `textPosition`，
    把文字在**整控件盒**里居中 —— 而带图标按键正是靠 `textPosition.left` 让开图标区。
    坐标口径：`sharedTypes.iconBox` 明说 `iconPosition/textPosition` 用该结构，故为**相对控件盒**。
    """

    def _render_button(self, node_extra, box=(16, 100, 200, 48), rep=None):
        left, top, w, h = box
        node = {'text': 'ABCD', 'fontSize': 20, 'alignment': 36,          # 36 = 靠左+垂直居中
                'colorTab': {'color0': 0xFFFFFF}, 'bgColorTab': {'color0': 0x203040}}
        node.update(node_extra)
        doc = {'resolution': {'width': 480, 'height': 800},
               'position': {'left': 0, 'top': 0, 'width': 480, 'height': 800},
               'backgroundColor': -16777216,
               'button__1': dict(node, position={'left': left, 'top': top,
                                                 'width': w, 'height': h})}
        jp = os.path.join(self.tmp, 'ui', 'main.json')
        os.makedirs(os.path.dirname(jp), exist_ok=True)
        with io.open(jp, 'w', encoding='utf-8') as f:
            json.dump(doc, f, ensure_ascii=False)
        out = os.path.join(self.tmp, 'ui', 'main.render.png')
        J.render_one(self.tmp, jp, out, report=rep or J.Report(), verbose=False)
        with Image.open(out) as im:
            return im.convert('RGBA')

    def _text_cols(self, im, box):
        """统计控件盒内「亮像素」（=文字）所在列区间。"""
        left, top, w, h = box
        cols = []
        for cx in range(left, left + w):
            for cy in range(top, top + h):
                r, g, b, a = im.getpixel((cx, cy))
                if r > 180 and g > 180 and b > 180:
                    cols.append(cx - left)
                    break
        return (min(cols), max(cols)) if cols else None

    def test_text_honours_text_position_offset(self):
        """`textPosition.left=96` → 文字必须从 rel 96 之后开始（改前会从 rel 0 附近开始）。"""
        box = (16, 100, 200, 48)
        im = self._render_button({'textPosition': {'left': 96, 'top': 12,
                                                   'width': 96, 'height': 24}}, box)
        cols = self._text_cols(im, box)
        self.assertIsNotNone(cols, '没找到文字像素')
        self.assertGreaterEqual(cols[0], 94,
                                '文字起点 %d 应 >= textPosition.left(96) 附近（被忽略时会是 ~2）'
                                % cols[0])

    def test_no_text_position_keeps_full_box_centring(self):
        """没有 `textPosition` 时退回整控件盒（与旧行为一致，不回归普通按键）。"""
        box = (16, 100, 200, 48)
        im = self._render_button({}, box)
        cols = self._text_cols(im, box)
        self.assertIsNotNone(cols)
        self.assertLess(cols[0], 60, '无 textPosition 时应仍在整盒居中（左起应靠前），实测 %d'
                        % cols[0])

    def test_out_of_box_text_position_is_reported(self):
        """越界的 `textPosition`（= 把 position 逐字拷成绝对坐标）必须**如实报**，不许静默画错。"""
        rep = J.Report()
        box = (16, 100, 200, 48)
        self._render_button({'textPosition': {'left': 168, 'top': 212,
                                              'width': 64, 'height': 16}}, box, rep)
        notes = json.dumps(rep.as_dict(), ensure_ascii=False)
        self.assertIn('越界', notes, '越界写法必须被记账（它是可疑写法，不是正常输入）')
        self.assertIn('textPosition', notes)


if __name__ == '__main__':
    unittest.main()
