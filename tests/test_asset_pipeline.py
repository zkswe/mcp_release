# -*- coding: utf-8 -*-
"""资源产物契约：html2json 黄金样例（v0.27.30 阴影三连 bug 防回归）+ verify_assets 真/假阳性。

为什么要有（检讨报告 §3.5）：
  - v0.27.30 的三连 bug（box-shadow 单位解析静默失败 / 图未 1:1 / alpha 被 mask 覆盖）
    靠人肉目测漏了整整一轮；这里把 ui_tools/examples/effects_test.html 当**黄金样例**钉死：
    渐变/圆角/阴影/emoji/loading 六类效果必须真的出图、且 PNG 尺寸 == 控件盒。
  - verify_assets 是「产物核对」守则的机器化（铁律 #11）；本用例同时验证它能报出真问题
    （自动生成图尺寸不符 → mismatch），以及不误报（手绘图被引擎拉伸 → 只算 stretched）。
"""
import glob
import io
import json
import os
import shutil
import unittest

import _util as U

try:
    from PIL import Image
    HAS_PIL = True
except Exception:
    HAS_PIL = False


class TestHtmlToJsonGolden(unittest.TestCase):
    """effects_test.html：六类 CSS 效果 → 真出图 + 1:1 + JSON 已引用。"""

    def setUp(self):
        self.tmp = U.project()
        self.html = os.path.join(self.tmp, 'ui', 'main.html')
        shutil.copy(U.fixture('effects_test.html'), self.html)
        self.out_json = os.path.join(self.tmp, 'ui', 'main.json')

    def tearDown(self):
        U.cleanup(self.tmp)

    def _convert(self):
        r = U.jcall('flythings_html_to_json',
                    {'input_html': self.html, 'output_json': self.out_json, 'res': '480x272'})
        self.assertTrue(r['ok'], r)
        return r, json.loads(io.open(self.out_json, encoding='utf-8').read())

    def test_controls_and_assets_generated(self):
        r, d = self._convert()
        self.assertGreaterEqual(r.get('generatedAssets', 0), 5, r.get('warnings'))
        names = [os.path.basename(p) for p in glob.glob(
            os.path.join(self.tmp, 'resources', 'images', '*'))]
        joined = ' '.join(names)
        for token in ('grad_GradTitle', 'grad_GradCard', 'gradshadow_GradCard',
                      'grad_BtnGrad', 'emoji_IconEmoji', 'loading_ImgLoading'):
            self.assertIn(token, joined, '缺自动转图产物: %s（names=%s）' % (token, names))

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_generated_images_are_1to1_with_controls(self):
        _, d = self._convert()
        bad = []
        for key, v in d.items():
            if not isinstance(v, dict) or 'position' not in v:
                continue
            pos = v['position']
            refs = [v.get('backgroundPic')] + [x for x in (v.get('picTab') or {}).values()]
            for ref in [x for x in refs if isinstance(x, str) and x]:
                cands = glob.glob(os.path.join(self.tmp, '**', os.path.basename(ref)),
                                  recursive=True)
                if not cands:
                    bad.append('%s %s 文件缺失' % (key, ref))
                    continue
                with Image.open(cands[0]) as im:
                    if im.size != (pos['width'], pos['height']):
                        bad.append('%s %s %s != 控件盒 %s'
                                   % (key, ref, im.size, (pos['width'], pos['height'])))
        self.assertEqual(bad, [])

    def test_shadow_warning_is_not_misleading(self):
        """v0.27.33：已自动转图的效果不许再喊「请切图」（实测会让 AI 白做一轮手工切图）。"""
        r, _ = self._convert()
        others = [w for w in r.get('warnings', []) if '阴影' in w or '渐变' in w]
        self.assertTrue(others, '缺少效果说明 warning')
        for w in others:
            if '已自动转成图片' in w:
                self.assertNotIn('请切图', w)
            else:
                self.assertIn('请切图', w)

    def test_verify_assets_clean_on_golden(self):
        self._convert()
        r = U.jcall('flythings_verify_assets', {'project_root': self.tmp})
        self.assertEqual(r['missing'], [], r['missing'])
        self.assertEqual(r['mismatch'], [], r['mismatch'])
        self.assertGreater(r['refCount'], 0, 'refCount=0 说明页面没被扫到（分层布局漏页回归）')


class TestThumbBoxSize(unittest.TestCase):
    """thumb 子盒（滑块自有尺寸）：盒子 = thumb.size，铁律 #1 对它同样成立。

    为什么钉死（v0.27.75，钟工 2026-09-16 反馈「滑块圆钮有锯齿、图片和控件尺寸对不上」）：
    案例 projects/translate/lvgl-widgets-uiv1 的 sk_thumb.png 曾 31×31 而 json 写 thumb.size
    30×30，verify_assets / check_all #11 #17 一律 PASS（thumb 是核对盲区）→ 真机上滑块错位。
    """

    def setUp(self):
        self.tmp = U.project()
        self.pages = os.path.join(self.tmp, 'ui', '1024x600')
        os.makedirs(self.pages, exist_ok=True)

    def tearDown(self):
        U.cleanup(self.tmp)

    def _page(self, thumb, pngs=None):
        """thumb：写进 seekbar 的 thumb 子结构；pngs：{相对路径: (w,h)} 实际产物。"""
        page = {'id': 0, 'title': 'x', 'resolution': {'width': 480, 'height': 272},
                'position': {'left': 0, 'top': 0, 'width': 480, 'height': 272},
                'seekbar__1': {'type': 'seekbar', 'caption': 'S', 'id': 50002,
                               'position': {'left': 10, 'top': 40, 'width': 200, 'height': 37},
                               'thumb': thumb, 'touchable': True}}
        U.write(os.path.join(self.pages, 'main.json'), json.dumps(page, ensure_ascii=False))
        for rel, size in (pngs or {}).items():
            full = os.path.join(self.tmp, 'resources', rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            if HAS_PIL:
                Image.new('RGBA', size, (255, 255, 255, 255)).save(full)

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_thumb_size_match_is_ok(self):
        self._page({'size': {'width': 30, 'height': 30}, 'normalPic': 'images/sk_thumb.png'},
                   {'images/sk_thumb.png': (30, 30)})
        r = U.jcall('flythings_verify_assets', {'project_root': self.tmp})
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['mismatch'], [])
        self.assertEqual(r['refCount'], 1, 'thumb 引用没被计入核对（漏核回归）')

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_thumb_size_mismatch_is_fail(self):
        """31×31 图 vs thumb.size 30×30 → mismatch（案例原 bug 的回归钉子）。"""
        self._page({'size': {'width': 30, 'height': 30}, 'normalPic': 'images/sk_thumb.png'},
                   {'images/sk_thumb.png': (31, 31)})
        r = U.jcall('flythings_verify_assets', {'project_root': self.tmp})
        self.assertFalse(r['ok'])
        self.assertEqual(len(r['mismatch']), 1, r)
        m = r['mismatch'][0]
        self.assertEqual(m['field'], 'thumb.normalPic')
        self.assertEqual(m['png'], [31, 31])
        self.assertEqual(m['box'], [30, 30])
        self.assertEqual(m['boxFrom'], 'thumb.size')

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_thumb_pressed_pic_checked_too(self):
        self._page({'size': {'width': 24, 'height': 24},
                    'normalPic': 'images/knob.png', 'pressedPic': 'images/knob_p.png'},
                   {'images/knob.png': (24, 24), 'images/knob_p.png': (26, 26)})
        r = U.jcall('flythings_verify_assets', {'project_root': self.tmp})
        self.assertEqual([m['field'] for m in r['mismatch']], ['thumb.pressedPic'], r)

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_thumb_hand_drawn_only_stretched(self):
        """手绘 thumb（官方基准工程 SampleUI-New 的 slider_/jdt_ht.png 就是 35×34 vs
        thumb.size 33×35）引擎会拉伸 → 只记 stretched，不 FAIL（基准工程零误报）。"""
        self._page({'size': {'width': 30, 'height': 30}, 'normalPic': 'knob/knob.png'},
                   {'knob/knob.png': (44, 26)})
        r = U.jcall('flythings_verify_assets', {'project_root': self.tmp})
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['mismatch'], [])
        self.assertEqual(len(r['stretched']), 1, r)
        self.assertEqual(r['stretched'][0]['boxFrom'], 'thumb.size')
        self.assertEqual(r['stretched'][0]['box'], [30, 30])

    def test_thumb_without_size_warns_not_fails(self):
        """无 size 字段（盒子未知）→ 跳过 + 上报，不许误报 FAIL。"""
        self._page({'normalPic': 'images/sk_thumb.png'}, {'images/sk_thumb.png': (31, 31)})
        r = U.jcall('flythings_verify_assets', {'project_root': self.tmp})
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['mismatch'], [])
        self.assertEqual(len(r.get('skippedNoBox', [])), 1, r)
        self.assertTrue(any('thumb' in w or '盒子尺寸未知' in w for w in r.get('warnings', [])), r)


class TestVerifyAssetsSemantics(unittest.TestCase):
    """verify_assets 的三种判定：missing=Fail、自动生成图 mismatch=Fail、手绘图 stretched=Note。"""

    def setUp(self):
        self.tmp = U.project()
        self.pages = os.path.join(self.tmp, 'ui', '1024x600')     # 分层布局（真机工程常态）
        os.makedirs(self.pages, exist_ok=True)

    def tearDown(self):
        U.cleanup(self.tmp)

    def _page(self, png_rel, png_size, pos_size):
        page = {'id': 0, 'title': 'x', 'resolution': {'width': 480, 'height': 272},
                'position': {'left': 0, 'top': 0, 'width': 480, 'height': 272},
                'textview__1': {'type': 'textview', 'caption': 'T', 'id': 50001,
                                'position': {'left': 0, 'top': 0, 'width': pos_size[0],
                                             'height': pos_size[1]},
                                'backgroundPic': png_rel, 'touchable': False}}
        U.write(os.path.join(self.pages, 'main.json'), json.dumps(page, ensure_ascii=False))
        full = os.path.join(self.tmp, 'resources', png_rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if HAS_PIL:
            Image.new('RGBA', png_size, (10, 20, 30, 255)).save(full)

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_finds_pages_in_resolution_subdir(self):
        self._page('images/gen.png', (48, 48), (48, 48))
        r = U.jcall('flythings_verify_assets', {'project_root': self.tmp})
        self.assertEqual(r['pages'], 1, '分层 ui/<res>/*.json 没被扫到（漏页回归）')
        self.assertEqual(r['refCount'], 1)
        self.assertEqual(r['missing'], [])
        self.assertEqual(r['mismatch'], [])
        self.assertTrue(r['ok'])

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_auto_generated_mismatch_is_reported(self):
        self._page('images/gen.png', (7, 9), (48, 48))     # 自动生成图 ≠ 控件盒 → 真问题
        r = U.jcall('flythings_verify_assets', {'project_root': self.tmp})
        self.assertFalse(r['ok'])
        self.assertEqual(len(r['mismatch']), 1, r)
        self.assertEqual(r['mismatch'][0]['png'], [7, 9])
        self.assertEqual(r['mismatch'][0]['position'], [48, 48])

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_hand_drawn_asset_only_warns_stretched(self):
        self._page('navi/fh.png', (44, 26), (72, 40))      # 官方基准工程写法 → 不该 FAIL
        r = U.jcall('flythings_verify_assets', {'project_root': self.tmp})
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['mismatch'], [])
        self.assertEqual(len(r['stretched']), 1)
        self.assertTrue(any('拉伸' in w for w in r.get('warnings', [])))

    def test_missing_file_is_reported(self):
        self._page('images/absent.png', (48, 48), (48, 48))
        if HAS_PIL:
            os.remove(os.path.join(self.tmp, 'resources', 'images', 'absent.png'))
        r = U.jcall('flythings_verify_assets', {'project_root': self.tmp})
        self.assertFalse(r['ok'])
        self.assertEqual(len(r['missing']), 1, r)

    def test_empty_project_warns_instead_of_silent_ok(self):
        r = U.jcall('flythings_verify_assets', {'project_root': self.tmp})
        self.assertGreaterEqual(r['pages'], 0)
        if r['pages'] == 0:
            self.assertTrue(any('没找到布局 json' in w for w in r.get('warnings', [])),
                            '0 页时必须有 warning，不能静默 ok')


class TestTextViewBgPic(unittest.TestCase):
    """`div.text` 上的 `data-bgpic` 必须落成该节点的 backgroundPic（v0.27.90）。

    为什么钉死（2026-09-17 真机定位，案例 projects/translate/tdesign-miniprogram）：
    textview 分支原**不读** data-bgpic → json 里没有 backgroundPic（弹窗白卡/药丸/图标
    在真机上压根没画出来），案例只能用 patch_json 反查 HTML 兜底。
    同时钉住「反例」：无 bgpic 的 text 产出不变（不许顺手给所有 textview 塞 backgroundPic）。
    """

    def setUp(self):
        self.tmp = U.project()
        self.html = os.path.join(self.tmp, 'ui', 'main.html')
        self.out_json = os.path.join(self.tmp, 'ui', 'main.json')

    def tearDown(self):
        U.cleanup(self.tmp)

    def _convert(self, body):
        U.write(self.html, '<div class="screen" data-res="480x272">\n%s\n</div>\n' % body)
        r = U.jcall('flythings_html_to_json',
                    {'input_html': self.html, 'output_json': self.out_json, 'res': '480x272'})
        self.assertTrue(r['ok'], r)
        d = json.loads(io.open(self.out_json, encoding='utf-8').read())
        return dict((v.get('caption'), v) for k, v in _walk(d))

    def test_bgpic_lands_on_textview(self):
        caps = self._convert(
            '<div class="text" data-caption="CardA" data-x="10" data-y="10" data-w="60"'
            ' data-h="40" data-bgpic="images/card_a.png"></div>')
        self.assertEqual(caps['CardA'].get('backgroundPic'), 'images/card_a.png',
                         'div.text 的 data-bgpic 又丢了（案例白卡不显示的老 bug）')

    def test_bgpic_bare_name_gets_images_prefix(self):
        caps = self._convert(
            '<div class="text" data-caption="PillA" data-x="10" data-y="10" data-w="60"'
            ' data-h="40" data-bgpic="pill_a.png"></div>')
        self.assertEqual(caps['PillA'].get('backgroundPic'), 'images/pill_a.png',
                         '裸文件名必须补 images/ 前缀（与其它类型同口径）')

    def test_text_without_bgpic_unchanged(self):
        """反例：没有 data-bgpic 的 text 产出与改前一致（不许无条件塞 backgroundPic）。"""
        caps = self._convert(
            '<div class="text" data-caption="Plain" data-x="10" data-y="10" data-w="60"'
            ' data-h="40">hello</div>\n'
            '<div class="text" data-caption="BgcOnly" data-x="10" data-y="60" data-w="60"'
            ' data-h="40" data-bg="#123456">hi</div>')
        self.assertNotIn('backgroundPic', caps['Plain'], '无 bgpic 的 text 被塞了底图')
        self.assertNotIn('backgroundPic', caps['BgcOnly'], '只有 data-bg（底色）不该出底图')
        self.assertEqual(caps['BgcOnly'].get('bgColorTab'), {'color0': 0x123456},
                         'data-bg 仍要落成 bgColorTab')

    def test_bgpic_wins_over_bg_color(self):
        """A6（2026-09-27）口径：有图控件的 `bgColorTab` 不再是「控件底色」而是**圆角外底色**——

        ① 作者显式写 `data-bg` → 用它（四角透出的是这个色，不再是引擎缺省黑底）；
        ② 没写 data-bg、也没祖先底色 → 保持 pop（退引擎缺省，与旧行为一致）；
        ③ 没写 data-bg、但坐在有色 window 里 → 取**最近祖先容器底色**。
        （旧断言「有图必不留 bgColorTab」正是 P4「图标角落都是黑的」的根因，已废）
        """
        caps = self._convert(
            '<div class="text" data-caption="Both" data-x="10" data-y="10" data-w="60"'
            ' data-h="40" data-bg="#123456" data-bgpic="images/both.png">x</div>')
        self.assertEqual(caps['Both'].get('backgroundPic'), 'images/both.png')
        self.assertEqual(caps['Both'].get('bgColorTab'), {'color0': 0x123456},
                         '显式 data-bg 必须作为圆角外底色留下（A6）')

        caps = self._convert(
            '<div class="text" data-caption="NoBg" data-x="10" data-y="10" data-w="60"'
            ' data-h="40" data-bgpic="images/nobg.png">x</div>')
        self.assertNotIn('bgColorTab', caps['NoBg'],
                         '既无 data-bg 也无祖先底色 → 保持 pop（与旧行为一致）')

        caps = self._convert(
            '<div class="window card" data-x="0" data-y="0" data-w="200" data-h="120"'
            ' data-bg="#1C1C1E">'
            '<div class="text" data-caption="InCard" data-x="10" data-y="10" data-w="60"'
            ' data-h="40" data-bgpic="images/incard.png">y</div></div>')
        self.assertEqual(caps['InCard'].get('bgColorTab'), {'color0': 0x1C1C1E},
                         '无 data-bg 的有图控件要取最近祖先容器底色（A6 ③）')

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_bgpic_text_image_must_be_1to1(self):
        """新落地的 backgroundPic 直接进「图尺寸 == 控件盒」核对（铁律 #11）：
        60x40 的图配 60x40 盒 → ok；盒被抬到 46（图没重出）→ 立刻 FAIL。"""
        body = ('<div class="text" data-caption="CardB" data-x="10" data-y="10" data-w="60"'
                ' data-h="40" data-bgpic="images/card_b.png"></div>')
        self._convert(body)
        png = os.path.join(self.tmp, 'resources', 'images', 'card_b.png')
        Image.new('RGBA', (60, 40), (255, 255, 255, 255)).save(png)
        r = U.jcall('flythings_verify_assets', {'project_root': self.tmp})
        self.assertEqual(r['mismatch'], [], r)
        Image.new('RGBA', (60, 46), (255, 255, 255, 255)).save(png)   # 盒被抬高、图没重出
        r = U.jcall('flythings_verify_assets', {'project_root': self.tmp})
        self.assertFalse(r['ok'], '自动生成图与控件盒不等必须 FAIL')
        self.assertEqual(len(r['mismatch']), 1, r)


def _walk(node, out=None):
    if out is None:
        out = []
    for k, v in node.items():
        if isinstance(v, dict) and '__' in k:
            out.append((k, v))
            _walk(v, out)
    return out


if __name__ == '__main__':
    unittest.main(verbosity=2)
