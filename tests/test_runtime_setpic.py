# -*- coding: utf-8 -*-
"""运行期设图 vs 控件盒（check_all 第 20 项，v0.27.90）：真阳性 / 假阳性两条都要钉死。

为什么要有（2026-09-17 真机踩到）：静态核对（#11/#17）只看 json 里声明的 backgroundPic；
运行期 `mXXXPtr->setBackgroundPic("images/x.png")` 设的图静态查不到 → 盒高被抬高/图没重出
也一路 PASS。案例实测：48x16 的三点图进了被抬高的 48x26 盒 → 引擎按盒拉伸 → 10x10 正圆
变成 10x16 竖椭圆（人眼才看得出）。

口径（与 #11/#17 铁律同源）：
  · 图尺寸 == 控件盒 → PASS；
  · `resources/images/` 的自动生成图不等 → mismatch（FAIL）；手绘图（navi/ 等）不等 → stretched 仅提示；
  · `.9.png` 豁免；文件不存在 → missing；
  · 变量名映射不到控件 / 非工程内路径 → unresolved（列出来，**不静默跳过**）；
  · 实参是变量/拼接 → 只计 dynamic（静态判不了，不假装查过）。
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

import check_all as CA   # noqa: E402  （_util 已把 ui_tools 加进 sys.path）


def _png(path, size):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if HAS_PIL:
        Image.new('RGBA', size, (200, 200, 200, 255)).save(path)


class TestRuntimeSetPic(unittest.TestCase):
    """check_all #20：运行期 set...Pic 的字面量图 vs 目标控件盒。"""

    def setUp(self):
        self.tmp = U.project()
        self.cc = os.path.join(self.tmp, 'src', 'logic', 'mainLogic.cc')

    def tearDown(self):
        U.cleanup(self.tmp)

    def _page(self, box, caption='LdDots', page='main.json'):
        page_d = {'id': 0, 'title': 'x', 'resolution': {'width': 1024, 'height': 600},
                  'position': {'left': 0, 'top': 0, 'width': 1024, 'height': 600},
                  'textview__235': {'type': 'textview', 'caption': caption, 'id': 50001,
                                    'position': {'left': 28, 'top': 130, 'width': box[0],
                                                 'height': box[1]}, 'touchable': False}}
        U.write(os.path.join(self.tmp, 'ui', page), json.dumps(page_d, ensure_ascii=False))

    def _cc(self, body):
        U.write(self.cc, '#include "ui_main.h"\n\n%s\n' % body)

    def _run(self):
        return CA.check_runtime_setpic(self.tmp)

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_size_match_is_ok(self):
        self._page((48, 16))
        self._cc('static void f(ZKTextView *mLdDotsPtr) {\n'
                 '    mLdDotsPtr->setBackgroundPic("images/ld_dots_00.png");\n}')
        _png(os.path.join(self.tmp, 'resources', 'images', 'ld_dots_00.png'), (48, 16))
        r = self._run()
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['mismatch'], [])
        self.assertEqual(r['matched'], 1, '字面量调用没被比过（漏检回归）')

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_stretched_auto_asset_is_fail(self):
        """复现真机事故：48x16 的图放进被抬高的 48x26 盒 → 必须报（真阳性）。"""
        self._page((48, 26))
        self._cc('static void f(ZKTextView *mLdDotsPtr) {\n'
                 '    mLdDotsPtr->setBackgroundPic("images/ld_dots_00.png");\n}')
        _png(os.path.join(self.tmp, 'resources', 'images', 'ld_dots_00.png'), (48, 16))
        r = self._run()
        self.assertFalse(r['ok'])
        self.assertEqual(len(r['mismatch']), 1, r)
        self.assertEqual(r['mismatch'][0]['png'], [48, 16])
        self.assertEqual(r['mismatch'][0]['boxes'][0].endswith('48x26'), True)

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_hand_drawn_stretch_is_only_note(self):
        """官方基准写法（navi/fh.png 44x26 放进 72x40 按钮）绝不能 FAIL。"""
        self._page((72, 40), caption='BtnBack')
        self._cc('static void f(ZKButton *mBtnBackPtr) {\n'
                 '    mBtnBackPtr->setBackgroundPic("navi/fh.png");\n}')
        _png(os.path.join(self.tmp, 'resources', 'navi', 'fh.png'), (44, 26))
        r = self._run()
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['mismatch'], [])
        self.assertEqual(len(r['stretched']), 1, r)

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_nine_patch_is_exempt(self):
        self._page((200, 48))
        self._cc('static void f(ZKTextView *mPillPtr) {\n'
                 '    mPillPtr->setBackgroundPic("images/pill.9.png");\n}')
        _png(os.path.join(self.tmp, 'resources', 'images', 'pill.9.png'), (12, 12))
        r = self._run()
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['mismatch'], [])
        self.assertEqual(r['stretched'], [])

    def test_missing_auto_asset_is_fail(self):
        self._page((48, 16))
        self._cc('mLdDotsPtr->setBackgroundPic("images/gone.png");')
        r = self._run()
        self.assertFalse(r['ok'])
        self.assertEqual(len(r['missing']), 1, r)

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_unmapped_variable_is_listed_not_silent(self):
        """映射不到控件 → unresolved 列表（不静默跳过）；不许当成 PASS 混过去。"""
        self._page((48, 16))
        self._cc('mLdDotsPtr->setBackgroundPic("images/x.png");\n'
                 'pLocal->setBackgroundPic("images/y.png");')
        _png(os.path.join(self.tmp, 'resources', 'images', 'x.png'), (48, 16))
        r = self._run()
        self.assertTrue(any('pLocal' in u for u in r['unresolved']), r)
        self.assertEqual(r['ok'], True, r)      # 报的是「没比成」，不是「图配错」

    def test_dynamic_arg_counted_not_judged(self):
        """案例的真实形态：helper 拼路径（snprintf）→ 静态判不了，只计数，不许瞎报。"""
        self._page((48, 16))
        self._cc('static void ldFrame(ZKTextView *tv, const char *prefix) {\n'
                 '    char path[64];\n'
                 '    snprintf(path, sizeof(path), "images/%s_00.png", prefix);\n'
                 '    tv->setBackgroundPic(path);\n}\n'
                 'mLdDotsPtr->setBackgroundPic(s_pic[i]);')
        r = self._run()
        self.assertGreaterEqual(r['dynamic'], 2, r)
        self.assertEqual(r['mismatch'], [])

    def test_commented_out_call_is_ignored(self):
        self._page((48, 26))
        self._cc('// mLdDotsPtr->setBackgroundPic("images/ld_dots_00.png");\n'
                 '/* mX->setProgressPic("images/big.png"); */')
        r = self._run()
        self.assertEqual(r['calls'], 0, '注释里的调用不该被算（会误报）')
        self.assertTrue(r['ok'])

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_ternary_two_literals_both_checked(self):
        """三元式两个字面量都要比（案例 mCdThemePtr 的写法）；错的那个要报出来。"""
        self._page((260, 44), caption='CdTheme')
        self._cc('static void f(ZKTextView *mCdThemePtr) {\n'
                 '    mCdThemePtr->setBackgroundPic(\n'
                 '        s_cdRound ? "images/cd_pill_round.png" : "images/cd_pill_wrong.png");\n}')
        _png(os.path.join(self.tmp, 'resources', 'images', 'cd_pill_round.png'), (260, 44))
        _png(os.path.join(self.tmp, 'resources', 'images', 'cd_pill_wrong.png'), (260, 30))
        r = self._run()
        self.assertEqual(r['resolved'], 2, r)
        self.assertEqual(r['matched'], 1, r)
        self.assertEqual(len(r['mismatch']), 1, r)
        self.assertIn('wrong', r['mismatch'][0]['pic'])

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_multi_page_caption_matching_any_box_passes(self):
        """同一 caption 在多页有不同盒子时：图与**任一**盒子 1:1 就算对得上（防误报）。"""
        self._page((48, 16), page='main.json')
        self._page((64, 16), page='other.json')
        self._cc('mLdDotsPtr->setBackgroundPic("images/ld_dots_00.png");')
        _png(os.path.join(self.tmp, 'resources', 'images', 'ld_dots_00.png'), (48, 16))
        r = self._run()
        self.assertEqual(r['mismatch'], [], r)

    def test_no_src_files_returns_empty(self):
        r = self._run()
        self.assertEqual(r['calls'], 0)
        self.assertTrue(r['ok'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
