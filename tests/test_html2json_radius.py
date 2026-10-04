# -*- coding: utf-8 -*-
"""倒角路由契约（2026-10-04 需求方决策）：
**纯色 + border-radius → `zk::ui_v1::RadButton`（painter 自绘，无切图）；渐变/背景图 → ZKButton + 切图**。

为什么必须钉（审计实测）：`button__N`/ZKButton、`window`、`textview` 的 json **都没有 radius 字段**
（components/ui_v1/RadButton/README.md §0），旧实现只在「渐变/阴影」分支出图 →
**纯色 + border-radius 的按键/卡片/文本块倒角全部静默丢失**（审计：`.card{background:#1E2735;
border-radius:10px}` 转出来一个像素的倒角都没有）。

RadButton 是「一个 painter + 一份代码」：json 里只是 `painter__N`，
真正的倒角靠 `RadButton::attach/setStyle/refresh`（按键）或静态 `drawRoundedRect`（卡片/文本块）在设备上画
→ 所以转换器还必须把**可直接粘贴的胶水**放进返回体 `radButtonGlue`（不写工程里的 Logic.cc，那是业务文件）。

真机证据：`_html2ui_probe/j_radbutton_device.png`（纯色按钮与渐变按钮并排，两者都带 r=12 倒角）。
"""
import io
import json
import os
import unittest

import _util as U

import html2json as H

RADIUS_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  html, body { margin: 0; padding: 0; background: #10151F; }
  .btn-solid { left: 16px; top: 40px;  width: 200px; height: 56px;
               background: #2196F3; border-radius: 12px; color: #FFFFFF; }
  .btn-grad  { left: 240px; top: 40px; width: 200px; height: 56px;
               background: linear-gradient(90deg, #2E8BFF, #6FC3FF); border-radius: 12px; }
  .btn-plain { left: 16px; top: 120px; width: 200px; height: 56px; background: #374457; }
  .card { left: 16px; top: 200px; width: 448px; height: 120px;
          background: #1E2735; border-radius: 10px; }
  .pill { left: 16px; top: 340px; width: 160px; height: 36px;
          background: #24304A; border-radius: 999px; color: #EEF2F6; }
  .card-shadow { left: 16px; top: 400px; width: 448px; height: 100px;
                 background: #1E2735; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,.5); }
</style></head><body>
  <div class="screen" data-page="p" data-res="480x800">
    <div class="btn btn-solid" data-caption="BtnSolid">纯色倒角</div>
    <div class="btn btn-grad"  data-caption="BtnGrad">渐变倒角</div>
    <div class="btn btn-plain" data-caption="BtnPlain">无倒角</div>
    <div class="card" data-caption="CardPlain"></div>
    <div class="text pill" data-caption="PillLabel">药丸标签</div>
    <div class="card-shadow" data-caption="CardShadow"></div>
  </div>
</body></html>
"""


class RadiusRoutingBase(unittest.TestCase):
    def setUp(self):
        self.tmp = U.project()

    def tearDown(self):
        U.cleanup(self.tmp)

    def conv(self, html=RADIUS_HTML):
        src = os.path.join(self.tmp, 'ui', 'p.html')
        U.write(src, html)
        dst = os.path.join(self.tmp, 'ui', 'p.json')
        r = H.html2json(src, dst, res='480x800')
        self.assertTrue(r['success'], r)
        with io.open(dst, encoding='utf-8') as f:
            return r, json.load(f)

    def all_ctrls(self, d):
        """{caption: (key, dict)}（含嵌套）。"""
        out = {}

        def walk(c):
            for k, v in c.items():
                if isinstance(v, dict) and '__' in k:
                    out[v.get('caption')] = (k, v)
                    walk(v)
        walk(d)
        return out

    def glue_of(self, r, cap):
        for g in r.get('radButtonGlue') or []:
            if g['caption'] == cap:
                return g
        return None


class TestSolidRadiusGoesRadButton(RadiusRoutingBase):
    """纯色 + 倒角 → RadButton：painter 画布 + 透明热区 + 胶水。"""

    def test_button_emits_painter_and_transparent_hotzone(self):
        r, d = self.conv()
        ctrls = self.all_ctrls(d)
        self.assertIn('BtnSolidRad', ctrls, ctrls)
        pk, pv = ctrls['BtnSolidRad']
        self.assertTrue(pk.startswith('painter__'), pk)
        self.assertEqual(pv['position'], {'left': 16, 'top': 40, 'width': 200, 'height': 56})
        bk, bv = ctrls['BtnSolid']
        self.assertTrue(bk.startswith('button__'), bk)
        # 热区按钮必须是**全透明图**（否则方角底色会盖住 painter 画的倒角）
        self.assertTrue(bv.get('picTab', {}).get('pic0'), '热区按钮缺透明切图')
        self.assertNotIn('bgColorTab', bv, '热区按钮带了底色 → 会盖住 RadButton 画布')
        # 画布必须先于热区（key 顺序 = z 序）
        keys = [k for k in d if isinstance(d[k], dict) and '__' in k]
        self.assertLess(keys.index(pk), keys.index(bk), 'painter 必须在按钮之前（z 更低）')

    def test_hotzone_png_is_fully_transparent(self):
        try:
            from PIL import Image
        except Exception:
            self.skipTest('needs Pillow')
        _, d = self.conv()
        bv = self.all_ctrls(d)['BtnSolid'][1]
        p = os.path.join(self.tmp, 'resources', 'images',
                         os.path.basename(bv['picTab']['pic0']))
        with Image.open(p).convert('RGBA') as im:
            self.assertEqual(im.size, (200, 56), '热区图必须 == 控件盒')
            self.assertEqual(im.getchannel('A').getextrema(), (0, 0), '热区图必须全透明')

    def test_glue_is_complete_and_actionable(self):
        r, _ = self.conv()
        g = self.glue_of(r, 'BtnSolidRad')
        self.assertIsNotNone(g, '纯色倒角按钮没产出 RadButton 胶水')
        self.assertEqual(g['kind'], 'RadButton')
        self.assertEqual(g['radius'], 12)
        self.assertEqual(g['fill'], '0x2196F3')
        self.assertEqual(g['bg'], '0x10151F', '背后底色应取页面根底色（AA 混色基准）')
        for need in ('#include "zk/zk_radbutton.h"', 'setStyle', 'attach', 'refresh',
                     'radius = 12', '0x2196F3', '0x10151F'):
            self.assertIn(need, g['code'], '胶水缺 %s' % need)
        # 警告要点名「倒角由代码画」，否则 AI 会以为已经画好了
        joined = ' '.join(r['warnings'])
        self.assertIn('RadButton', joined)
        self.assertIn('refresh', joined)


class TestGradientOrImageKeepsZKButton(RadiusRoutingBase):
    """渐变 / 背景图 / 无倒角 → 保持 ZKButton（倒角烘进切图或本就没有）。"""

    def test_gradient_button_uses_generated_image(self):
        r, d = self.conv()
        ctrls = self.all_ctrls(d)
        bk, bv = ctrls['BtnGrad']
        self.assertTrue(bv.get('picTab', {}).get('pic0', '').startswith('images/'), bv)
        self.assertNotIn('BtnGradRad', ctrls, '渐变按钮不该走 RadButton（切图更合适）')
        self.assertIsNone(self.glue_of(r, 'BtnGradRad'))
        p = os.path.join(self.tmp, 'resources', 'images',
                         os.path.basename(bv['picTab']['pic0']))
        with __import__('PIL.Image', fromlist=['Image']).open(p).convert('RGBA') as im:
            self.assertEqual(im.size, (200, 56), '切图必须 == 控件盒')
            self.assertEqual(im.getpixel((0, 0))[3], 0, '圆角必须烘进切图（四角透明）')

    def test_no_radius_button_unchanged(self):
        r, d = self.conv()
        ctrls = self.all_ctrls(d)
        _, bv = ctrls['BtnPlain']
        self.assertIn('bgColorTab', bv, '无倒角的纯色按钮应保持 bgColorTab 老路')
        self.assertNotIn('BtnPlainRad', ctrls)
        self.assertEqual([g for g in (r.get('radButtonGlue') or [])
                          if g['caption'] == 'BtnPlainRad'], [])


class TestOtherBoxesRadius(RadiusRoutingBase):
    """卡片(window) / 文本块(textview) 的纯色倒角 → **出 `.9.png` 背景图**（需求方口径）。

    为什么不是 painter：卡片/文本块只是静态底，`.9.png` 一次出图就够（九宫格保证任意尺寸四角不变形），
    还不用往 Logic.cc 粘胶水；painter 只留给需要四态/触摸语义的按键。
    """

    def test_card_gets_9patch_background(self):
        r, d = self.conv()
        ctrls = self.all_ctrls(d)
        wk, wv = ctrls['CardPlain']
        self.assertTrue(wk.startswith('window__'), wk)
        self.assertTrue(str(wv.get('backgroundPic', '')).endswith('.9.png'),
                        '卡片该出 .9.png 背景图，实际 %r' % wv.get('backgroundPic'))
        # 圆角外不能露引擎缺省黑底 → 底色换成背后底色（页面底）
        self.assertEqual(wv.get('backgroundColor'), 0x10151F,
                         'window 的 backgroundColor 该改成背后底色（不是 -1、也不是卡片色）')
        self.assertNotIn('CardPlainRad', ctrls, '卡片不该再多一个 painter')
        self.assertIsNone(self.glue_of(r, 'CardPlainRad'))
        self.assertEqual(r['radButtonGlue'], [g for g in r['radButtonGlue']
                                              if g['caption'] == 'BtnSolidRad'],
                         '卡片/文本块不该产出胶水（.9.png 不需要代码）')

    def test_card_9patch_is_nine_patch_and_8bit(self):
        try:
            from PIL import Image
        except Exception:
            self.skipTest('needs Pillow')
        _, d = self.conv()
        ref = self.all_ctrls(d)['CardPlain'][1]['backgroundPic']
        p = os.path.join(self.tmp, 'resources', 'images', os.path.basename(ref))
        self.assertEqual(os.path.basename(ref), 'card_CardPlain.9.png')
        raw = open(p, 'rb').read()
        self.assertEqual(raw[24], 8, '9-patch 也走 8bit 索引色')
        with Image.open(p) as im:
            self.assertEqual(im.mode, 'P')
            # 9-patch = 内容图四周各扩 1px 引导边
            self.assertEqual(im.size, (448 + 2, 120 + 2), im.size)
            px = im.convert('RGBA').load()
            top = [x for x in range(im.width) if px[x, 0][:3] == (0, 0, 0) and px[x, 0][3] == 255]
            left = [y for y in range(im.height) if px[0, y][:3] == (0, 0, 0) and px[0, y][3] == 255]
            self.assertTrue(top, '缺顶边九宫格引导线')
            self.assertTrue(left, '缺左边九宫格引导线')
            # 引导线必须避开角切片（radius=10）
            self.assertGreaterEqual(min(top), 11, '顶边黑线压到左上角切片')
            self.assertLessEqual(max(top), 448 + 2 - 12, '顶边黑线压到右上角切片')

    def test_textview_pill_gets_9patch_and_corner_bg(self):
        r, d = self.conv()
        ctrls = self.all_ctrls(d)
        tk, tv = ctrls['PillLabel']
        self.assertTrue(str(tv.get('backgroundPic', '')).endswith('.9.png'), tv)
        # 圆角外四角 = **背后底色**（页面底），不是药丸自己的填充色（A6 口径）
        self.assertEqual((tv.get('bgColorTab') or {}).get('color0'), 0x10151F, tv.get('bgColorTab'))
        self.assertNotEqual((tv.get('bgColorTab') or {}).get('color0'), 0x24304A,
                            '四角不该用药丸自己的填充色')
        self.assertNotIn('PillLabelRad', ctrls)
        self.assertIsNone(self.glue_of(r, 'PillLabelRad'))

    def test_pill_radius_is_clamped_to_half_height(self):
        """`border-radius:999px` 是药丸写法 → 半径按 min(w,h)/2 夹取（36 高 → 18）。"""
        r, _ = self.conv()
        joined = ' '.join(r['warnings'])
        self.assertIn('border-radius=18px', joined, '药丸半径没夹到 min(w,h)/2')

    def test_shadow_card_unchanged(self):
        """有 box-shadow 的卡片仍走出图那条路（阴影图自带圆角），不该变成 .9.png。"""
        r, d = self.conv()
        ctrls = self.all_ctrls(d)
        _, v = ctrls['CardShadow']
        self.assertTrue(v.get('backgroundPic'), v)
        self.assertFalse(str(v['backgroundPic']).endswith('.9.png'), v['backgroundPic'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
