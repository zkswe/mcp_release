# -*- coding: utf-8 -*-
"""进度条（seekbar）HTML/CSS → 真机一致：CSS 层叠 + 伪元素 + 三件套自动出图（2026-10-04 新增能力）。

为什么单独钉一组用例（真机归因实测，见 `_html2ui_probe/REPORT.md` §1/§2）：
  1. **CSS 写在 `<style>` 块里此前完全读不到** → 控件位置全丢成 (0,0,100×40)、渐变/圆角一个都不出图，
     而且**零警告**（连 CSS 效果检测也只读元素上的 style 属性）。AI 写的 HTML 恰恰是这种写法。
  2. 进度条在引擎里是「**3 张图 + 3 套不同的尺寸语义**」：轨道 `backgroundPic` 被**拉伸填满控件盒**、
     有效图 `progressPic` 是 **1:1 原样贴 + 按 floor(盒宽×进度/max) 横向裁剪（不缩放）**、
     滑块按 **PNG 原尺寸**画（`thumb.size` 实测真机忽略）。`_effect_assets` 的「一个控件 = 一张皮」
     模型表达不了，必须单独一条分支。
  3. **正常 HTML 的滑条只能写伪元素**：`input[type=range]` 的滑块/轨道就是
     `::-webkit-slider-thumb` / `::-webkit-slider-runnable-track`，而 Chrome **没有**填充伪元素
     （那是 Firefox 的 `::-moz-range-progress`）→ 「已有进度」的常规画法是把填充做成轨道背景上的
     **硬停靠渐变**。这三条都必须翻译成切图，只告警等于不支持。
  4. 真机**按盒高居中裁滑块** → 正常 HTML 常把 input 高度写成轨道高度（8~12px）、滑块 24px，
     不抬高控件盒就会「滑块被压扁」（`knowledge/uicontrols/seekbar-fields.md` §2 的实测坑）。
  5. `html/body` 的 background 会**传播到画布**；转换器不写根底色 = 真机**不擦屏**、
     残留上一页/屏保（实测：body 带背景时整屏盖着屏保帧）。
  6. 已知不可实现项必须**出警告**而不是硬转：有效图右端圆角（引擎硬切）、
     填充自身宽度定义的渐变、`inset` 内阴影。

本组用例只钉「转换器产物」，不碰真机；真机侧像素结论见 `_html2ui_probe/REPORT.md`。
"""
import io
import json
import os
import unittest

import _util as U

try:
    from PIL import Image
    HAS_PIL = True
except Exception:
    HAS_PIL = False

import html2json as H


CSS_BAR_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  html, body { margin: 0; padding: 0; background: #10151F; }
  .progress { position: absolute; left: 16px; top: 120px; width: 448px; height: 32px;
              background: #242F49; border-radius: 16px; overflow: hidden;
              box-shadow: inset 0 2px 4px rgba(0,0,0,.55); }
  .progress .fill { height: 100%; width: 60%; border-radius: 16px;
              background: linear-gradient(90deg, #2E8BFF 0%, #6FC3FF 100%); }
</style></head><body>
  <div class="screen" data-page="p" data-res="480x800">
    <div class="progress"><div class="fill"></div></div>
  </div>
</body></html>
"""

THUMB_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body { background: #10151F; }
  .bar { left: 16px; top: 40px; width: 448px; height: 32px; background: #24304A; border-radius: 16px; }
  .bar .fill { width: 25%; background: #4DA6FF; border-radius: 16px; }
  .bar .thumb { width: 32px; height: 32px; border-radius: 50%;
                background: #E8F1FF; border: 3px solid #2A3550; }
</style></head><body>
  <div class="screen" data-page="p" data-res="480x800">
    <div class="bar"><div class="fill"></div><div class="thumb"></div></div>
  </div>
</body></html>
"""

# 正常 HTML 的标准滑条写法：轨道/滑块全在伪元素里，进度靠轨道背景的硬停靠渐变表达
PSEUDO_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body { background: #10151F; }
  .range { left: 16px; top: 40px; width: 448px; height: 32px;
           -webkit-appearance: none; appearance: none; }
  .range::-webkit-slider-runnable-track {
      height: 32px; border-radius: 16px;
      background: linear-gradient(to right, #2E8BFF 0 60%, #242F49 60% 100%); }
  .range::-webkit-slider-thumb {
      -webkit-appearance: none; width: 32px; height: 32px; border-radius: 50%;
      background: #E8F1FF; border: 3px solid #2A3550; }
</style></head><body>
  <div class="screen" data-page="p" data-res="480x800">
    <input class="range" type="range" min="0" max="100" value="60">
  </div>
</body></html>
"""

# 细轨道 + 大滑块（input 只写轨道高度）：真机会把滑块居中裁扁 → 必须自动抬高控件盒
THIN_TRACK_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body { background: #10151F; }
  .range { left: 16px; top: 100px; width: 448px; height: 8px; }
  .range::-webkit-slider-runnable-track { height: 8px; border-radius: 4px; background: #242F49; }
  .range::-webkit-slider-thumb { width: 24px; height: 24px; border-radius: 50%;
      background: #E8F1FF; border: 3px solid #2A3550; }
</style></head><body>
  <div class="screen" data-page="p" data-res="480x800">
    <input class="range" type="range" min="0" max="100" value="40">
  </div>
</body></html>
"""

# 粗盒子 + 细轨道：可见条要居中画在盒子里、上下真透明
BAND_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body { background: #10151F; }
  .range { left: 16px; top: 100px; width: 448px; height: 32px; }
  .range::-webkit-slider-runnable-track { height: 8px; border-radius: 4px; background: #242F49; }
  .range::-webkit-slider-thumb { width: 24px; height: 24px; border-radius: 50%;
      background: #E8F1FF; border: 3px solid #2A3550; }
</style></head><body>
  <div class="screen" data-page="p" data-res="480x800">
    <input class="range" type="range" min="0" max="100" value="40">
  </div>
</body></html>
"""

# 伪元素写了但尺寸是百分比 → 解析不出，必须点名（否则真机上没有滑块）
PSEUDO_BAD_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body { background: #10151F; }
  .range { left: 16px; top: 40px; width: 448px; height: 32px; }
  .range::-webkit-slider-runnable-track { height: 32px; background: #242F49; }
  .range::-webkit-slider-thumb { width: 5%; height: 32px; background: #E8F1FF; }
</style></head><body>
  <div class="screen" data-page="p" data-res="480x800">
    <input class="range" type="range">
  </div>
</body></html>
"""


class SeekbarCssBase(unittest.TestCase):
    def setUp(self):
        self.tmp = U.project()

    def tearDown(self):
        U.cleanup(self.tmp)

    def conv(self, html):
        src = os.path.join(self.tmp, 'ui', 'p.html')
        U.write(src, html)
        dst = os.path.join(self.tmp, 'ui', 'p.json')
        r = H.html2json(src, dst, res='480x800')
        self.assertTrue(r['success'], r)
        with io.open(dst, encoding='utf-8') as f:
            return r, json.load(f)

    def seekbar(self, d):
        keys = [k for k in d if k.startswith('seekbar__')]
        self.assertTrue(keys, '没有产出 seekbar：%s' % list(d))
        return d[keys[0]]

    def asset(self, ref):
        base = os.path.join(self.tmp, 'resources')
        p = os.path.join(base, 'images', os.path.basename(ref))
        if not os.path.isfile(p):
            p = os.path.join(base, os.path.basename(ref))
        self.assertTrue(os.path.isfile(p), '缺切片 %s（已有：%s）' % (
            ref, os.listdir(os.path.join(base, 'images'))))
        return p

    def png_size(self, ref):
        with Image.open(self.asset(ref)) as im:
            return im.size

    def alpha_rows(self, ref):
        """每行中点的 alpha → 用来验「可见条居中、上下真透明」那套。"""
        with Image.open(self.asset(ref)).convert('RGBA') as im:
            return [im.getpixel((im.width // 2, y))[3] for y in range(im.height)]


class TestCssCascade(SeekbarCssBase):
    """`<style>` 块的定位必须生效（此前全丢成 (0,0,100×40) 且零警告）。"""

    def test_style_block_geometry_reaches_json(self):
        _, d = self.conv(CSS_BAR_HTML)
        self.assertEqual(self.seekbar(d)['position'],
                         {'left': 16, 'top': 120, 'width': 448, 'height': 32},
                         'CSS 里的 left/top/width/height 没进 position')

    def test_body_background_propagates_to_root(self):
        """html/body 的 background 要落到根 backgroundColor；否则真机不擦屏、残留上一帧。"""
        _, d = self.conv(CSS_BAR_HTML)
        self.assertEqual(d.get('backgroundColor'), 0x10151F,
                         'body 的 background 没传播到 json 根（真机会残留上一页）')

    def test_percent_screen_size_does_not_shrink_root(self):
        """`.screen{width:100%;height:100%}` 不许把整屏缩成 100×40（百分比解析不了 → 应按全屏）。"""
        html = ('<html><head><style>.screen { width: 100%; height: 100%; }</style></head><body>'
                '<div class="screen" data-page="p" data-res="480x800">'
                '<div class="text" data-caption="T" data-x="0" data-y="0" data-w="10" data-h="10">x</div>'
                '</div></body></html>')
        _, d = self.conv(html)
        self.assertEqual(d['position'],
                         {'left': 0, 'top': 0, 'width': 480, 'height': 800}, d['position'])

    def test_specificity_and_inline_priority(self):
        """层叠：inline > 高 specificity > 靠后的规则（消费者取第一个匹配，谁在前谁生效）。"""
        html = ('<html><head><style>'
                '.screen{left:1px;top:1px;width:10px;height:10px}'
                '#s{left:2px}'
                '</style></head><body>'
                '<div class="screen" id="s" data-page="p" data-res="480x800" style="left:9px">'
                '<div class="text" data-caption="T" data-x="0" data-y="0" data-w="10" data-h="10">x</div>'
                '</div></body></html>')
        _, d = self.conv(html)
        # .screen 有 inline left:9px → 整屏按局部块处理，left 取 9（inline 优先于 #s 的 2px）
        self.assertEqual(d['position']['left'], 9, d['position'])
        self.assertEqual(d['position']['top'], 1, d['position'])

    def test_slider_percent_width_resolves_against_screen(self):
        """滑条 `width:100%` 要按最近容器解析（正常 HTML 极常见），并明说这是近似。"""
        html = ('<html><head><style>body{background:#000}'
                '.range{left:0;top:0;width:100%;height:32px;background:#242F49}'
                '</style></head><body><div class="screen" data-page="p" data-res="480x800">'
                '<div class="range"></div></div></body></html>')
        r, d = self.conv(html)
        self.assertEqual(self.seekbar(d)['position']['width'], 480, self.seekbar(d)['position'])
        self.assertIn('百分比', ' '.join(r.get('warnings') or []))


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class TestSeekbarCssAssets(SeekbarCssBase):
    """CSS 结构化的进度条 → 轨道/有效/滑块三张切图（尺寸规则三套各不相同）。"""

    def test_track_and_fill_generated_at_box_size(self):
        r, d = self.conv(CSS_BAR_HTML)
        sk = self.seekbar(d)
        self.assertGreaterEqual(r['generatedAssets'], 2, r)
        self.assertTrue(sk['backgroundPic'].startswith('images/'), sk)
        self.assertTrue(sk['progressPic'].startswith('images/'), sk)
        # 轨道：引擎会拉伸填满控件盒 → 图必须 == 盒
        self.assertEqual(self.png_size(sk['backgroundPic']), (448, 32))
        # 有效图：引擎只裁剪不缩放 → 图也必须 == 盒（窄了高进度段会露轨道）
        self.assertEqual(self.png_size(sk['progressPic']), (448, 32))
        # 底色不许写成轨道色（实测：同色会把轨道图的圆角补满、视觉上变直角）
        self.assertEqual(sk['backgroundColor'], -1)

    def test_progress_value_from_css_width_percent(self):
        _, d = self.conv(CSS_BAR_HTML)
        sk = self.seekbar(d)
        self.assertEqual((sk['defProgress'], sk['max']), (60, 100),
                         'CSS width:60% 没被换算成 defProgress')

    def test_thumb_png_size_equals_thumb_size_and_all_keys_present(self):
        _, d = self.conv(THUMB_HTML)
        sk = self.seekbar(d)
        th = sk['thumb']
        self.assertEqual(sorted(th), ['normalPic', 'pressedPic', 'size'],
                         'thumb 三键必须齐全（ui_schema requiredKeys）')
        self.assertEqual((th['size']['width'], th['size']['height']), (32, 32))
        self.assertEqual(self.png_size(th['normalPic']), (32, 32),
                         'thumb.size 与 PNG 尺寸必须一致（check_all #11）')
        self.assertTrue(sk['touchable'], '有滑块 = 可拖')

    def test_pill_radius_baked_into_png(self):
        """border-radius:16px 必须烘进图（四角真透明）——这是 CSS 唯一能表达圆角的地方。"""
        _, d = self.conv(CSS_BAR_HTML)
        sk = self.seekbar(d)
        with Image.open(self.asset(sk['backgroundPic'])).convert('RGBA') as im:
            self.assertEqual(im.getpixel((0, 0))[3], 0, '轨道左上角不透明 → 圆角没生效')
            self.assertEqual(im.getpixel((15, 16))[3], 255, '药丸左端中部该是实心')
            self.assertEqual(im.getpixel((447, 0))[3], 0, '轨道右上角不透明 → 圆角没生效')

    def test_four_corner_radius_is_per_corner(self):
        """`border-radius: 8px 8px 0 0` 必须只圆上面两角（旧口径只取第一段 → 四角全 8，视觉错）。"""
        self.assertEqual(H._radius_corners('border-radius: 8px 8px 0 0;', 100, 40),
                         (8.0, 8.0, 0.0, 0.0))
        self.assertEqual(H._radius_corners('border-radius: 50%;', 32, 32), (16.0, 16.0, 16.0, 16.0))
        self.assertEqual(H._radius_corners('border-radius: 4px 8px 12px 16px;', 100, 40),
                         (4.0, 8.0, 12.0, 16.0))
        html = ('<html><head><style>body{background:#000}'
                '.bar{left:0;top:0;width:100px;height:40px;background:#4DA6FF;'
                'border-radius:8px 8px 0 0}</style></head><body>'
                '<div class="screen" data-page="p" data-res="480x800">'
                '<div class="bar"></div></div></body></html>')
        _, d = self.conv(html)
        with Image.open(self.asset(self.seekbar(d)['backgroundPic'])).convert('RGBA') as im:
            self.assertEqual(im.getpixel((0, 0))[3], 0, '左上角该被圆掉')
            self.assertEqual(im.getpixel((0, 39))[3], 255, '左下角不该被圆掉（0 0 只圆上面两角）')


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class TestSliderPseudoElements(SeekbarCssBase):
    """**正常 HTML 的滑条写法**（`::-webkit-slider-thumb` / `-runnable-track` / 硬停靠渐变）。"""

    def test_input_range_is_seekbar_not_edittext(self):
        _, d = self.conv(PSEUDO_HTML)
        self.assertFalse([k for k in d if k.startswith('edittext__')],
                         '<input type=range> 又被当成 edittext 了')
        self.assertTrue([k for k in d if k.startswith('seekbar__')])

    def test_thumb_pseudo_element_becomes_thumb_pic(self):
        r, d = self.conv(PSEUDO_HTML)
        sk = self.seekbar(d)
        th = sk['thumb']
        self.assertEqual(sorted(th), ['normalPic', 'pressedPic', 'size'])
        self.assertTrue(th['normalPic'], '::-webkit-slider-thumb 没被翻译成滑块切图')
        self.assertEqual((th['size']['width'], th['size']['height']), (32, 32))
        self.assertEqual(self.png_size(th['normalPic']), (32, 32))
        self.assertTrue(sk['touchable'])
        # 伪元素里的描边必须烘进图（圆钮 = 白芯 + 3px 深环）
        with Image.open(self.asset(th['normalPic'])).convert('RGBA') as im:
            self.assertEqual(im.getpixel((0, 0))[3], 0, '滑块四角不透明 → border-radius:50% 没生效')
            self.assertEqual(im.getpixel((16, 16))[:3], (0xE8, 0xF1, 0xFF), '滑块底色不是 #E8F1FF')
            self.assertEqual(im.getpixel((1, 16))[:3], (0x2A, 0x35, 0x50), '3px 描边没烘进图')
        self.assertIn('伪元素', ' '.join(r.get('warnings') or []))

    def test_hard_stop_gradient_splits_into_fill_and_track(self):
        """Chrome 没有填充伪元素 → 进度靠轨道硬停靠渐变；必须拆成 填充图 + 轨道图 + defProgress。"""
        _, d = self.conv(PSEUDO_HTML)
        sk = self.seekbar(d)
        self.assertEqual(sk['defProgress'], 60, '硬停靠点 60% 没变成 defProgress')
        self.assertTrue(sk['progressPic'], '硬停靠渐变没拆出填充图')
        self.assertEqual(self.png_size(sk['progressPic']), (448, 32))
        self.assertEqual(self.png_size(sk['backgroundPic']), (448, 32))
        with Image.open(self.asset(sk['progressPic'])).convert('RGBA') as im:
            self.assertEqual(im.getpixel((5, 16))[:3], (0x2E, 0x8B, 0xFF), '填充图不是停靠点之前的颜色')
        with Image.open(self.asset(sk['backgroundPic'])).convert('RGBA') as im:
            self.assertEqual(im.getpixel((5, 16))[:3], (0x24, 0x2F, 0x49),
                             '轨道图整张都该是停靠点之后的颜色（轨道图不会被裁剪）')
            # 拆分只许换背景：轨道/填充的 border-radius 必须还在（否则真机上药丸变方头 ——
            # 2026-10-04 真机比对抓到过一次）
            self.assertEqual(im.getpixel((0, 0))[3], 0, '拆分后轨道圆角丢了（应仍是药丸）')
            self.assertEqual(im.getpixel((447, 0))[3], 0, '拆分后轨道右端圆角丢了')
        with Image.open(self.asset(sk['progressPic'])).convert('RGBA') as im:
            self.assertEqual(im.getpixel((0, 0))[3], 0, '拆分后填充左端圆角丢了')

    def test_thin_track_and_big_thumb_grows_control_box(self):
        """input 只写轨道高 8px、滑块 24px：真机按盒高居中裁滑块 → 控件盒必须抬到 24 高。"""
        r, d = self.conv(THIN_TRACK_HTML)
        sk = self.seekbar(d)
        self.assertEqual(sk['position']['height'], 24, sk['position'])
        self.assertEqual(sk['position']['top'], 100 - 8, '抬高盒子时要保持可见条中线不动')
        self.assertEqual(self.png_size(sk['backgroundPic']), (448, 24), '轨道图要跟着盒高一起出')
        self.assertTrue(any('抬到' in w for w in r.get('warnings') or []), r.get('warnings'))

    def test_visible_band_is_centred_with_transparent_margins(self):
        """盒 32 高 + 轨道 8 高 → 可见条居中、上下真透明（seekbar-fields.md §3 口径）。"""
        _, d = self.conv(BAND_HTML)
        sk = self.seekbar(d)
        self.assertEqual(self.png_size(sk['backgroundPic']), (448, 32))
        rows = self.alpha_rows(sk['backgroundPic'])
        self.assertEqual(rows[:12], [0] * 12, '可见条上方该是真透明（0..11）')
        self.assertEqual(rows[12:20], [255] * 8, '可见条该落在 12..19（居中）')
        self.assertEqual(rows[20:], [0] * 12, '可见条下方该是真透明（20..31）')

    def test_pseudo_thumb_with_percent_size_is_called_out(self):
        """伪元素写了但尺寸是百分比 → 解析不出，必须点名（否则真机上没有滑块）。"""
        r, d = self.conv(PSEUDO_BAD_HTML)
        self.assertFalse(self.seekbar(d)['thumb']['normalPic'])
        self.assertIn('没有滑块', ' '.join(r.get('warnings') or []))


class TestHonestWarnings(SeekbarCssBase):
    """已知不可实现项必须点名告警（不许硬转、也不许假声明）。"""

    def _warnings(self, html):
        r, _ = self.conv(html)
        return ' || '.join(r.get('warnings') or [])

    def test_fill_right_cap_and_gradient_are_called_out(self):
        w = self._warnings(CSS_BAR_HTML)
        self.assertIn('右端', w)
        self.assertIn('只裁剪不缩放', w)
        self.assertIn('inset', w)
        self.assertIn('真机口径', w, '引擎口径说明没输出')

    def test_engine_model_is_stated(self):
        w = self._warnings(CSS_BAR_HTML)
        self.assertIn('floor', w, '填充长度算法（floor(盒宽×进度/max)）没写进告警')

    def test_non_consumer_type_does_not_claim_generated_assets(self):
        """circlebar 分支从不调 _effect_assets → 不许再说「已自动转成图片」（实测假声明）。"""
        html = ('<html><head><style>body{background:#000}'
                '.circlebar{left:0;top:0;width:200px;height:200px;'
                'background:linear-gradient(90deg,#123456,#654321);border-radius:50%}'
                '</style></head><body><div class="screen" data-page="p" data-res="480x800">'
                '<div class="circlebar"></div></div></body></html>')
        w = self._warnings(html)
        self.assertNotIn('已自动转成图片', w, '对不出图的控件类型发了假声明')
        self.assertIn('请切图', w)

    def test_missing_page_background_warns(self):
        html = ('<html><head></head><body><div class="screen" data-page="p" data-res="480x800">'
                '<div class="text" data-caption="T" data-x="0" data-y="0" data-w="10" data-h="10">x</div>'
                '</div></body></html>')
        w = self._warnings(html)
        self.assertIn('不擦屏', w)


if __name__ == '__main__':
    unittest.main(verbosity=2)
