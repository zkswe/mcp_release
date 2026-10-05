# -*- coding: utf-8 -*-
"""区域级归因契约（T2.4）。

离线造四类区域差异，各自必须归到**正确的层**（这是「差异该谁修」的唯一判据）：
  ① `button__3` 缺必填键（ui_compile 报 error）        → `C/EMIT-FIELDS`（改发射层）
  ② `seekbar__4` 引用 10×10 图挂在 200×40 盒上（图≠盒） → `C/ASSET-GEOMETRY`（改资产/字段）
  ③ `textview__2` 开了 `rollEnable`（渲染器不覆盖）      → `E/RENDERER-BLINDSPOT`（离线判不了）
  ④ `window__1` 纯色容器（无任何登记）                  → `U/UNATTRIBUTED`（**不猜**）
并钉住汇总口径：`eLayerSharePct` / `attributedPct` / `pass`（有 C 或 U 的超阈值差异 → FAIL）。
"""
import io
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
for _p in (BASE, os.path.join(BASE, 'ui_tools'), TESTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _util as U                                           # noqa: E402
import region_attrib as RA                                  # noqa: E402

try:
    from PIL import Image, ImageDraw
except Exception as e:                                      # pragma: no cover
    raise unittest.SkipTest('Pillow 不可用：%s' % e)

BOXES = {                                   # 与下面 json 一致（归因只按 json 的盒来切）
    'window__1': (10, 10, 140, 60),
    'textview__2': (10, 90, 140, 40),
    'button__3': (10, 150, 140, 40),
    'seekbar__4': (10, 210, 200, 40),
}
PAINT = (255, 0, 255)                       # 造差异用的颜色（与渲染结果必然不同）


def _page():
    tv_full = {'id': 50001, 'caption': 'TvPlain',
               'position': {'left': 10, 'top': 90, 'width': 140, 'height': 40},
               'alignment': 36, 'colorTab': {'color0': 0, 'color1': -1, 'color2': -1,
                                             'color3': -1, 'color4': -1},
               'fontSize': 18, 'text': 'plain', 'touchable': False, 'visible': True}
    tv_blind = dict(tv_full)
    tv_blind.update({'id': 50002, 'caption': 'TvRoll', 'position':
                     {'left': 10, 'top': 90, 'width': 140, 'height': 40}, 'rollEnable': True})
    return {
        'id': 0, 'resolution': {'width': 320, 'height': 272},
        'position': {'left': 0, 'top': 0, 'width': 320, 'height': 272},
        'backgroundColor': 16777215,
        'window__1': {'id': 110001, 'caption': 'WinPlain', 'position':
                      {'left': 10, 'top': 10, 'width': 140, 'height': 60},
                      'backgroundColor': 0x203040, 'hideTimeOut': -1, 'modal': False,
                      'touchable': False, 'visible': True},
        # ② 盲区（渲染器不覆盖 rollEnable）
        'textview__2': tv_blind,
        # ① 缺必填键（picTab/touchable 不写）→ ui_compile error
        'button__3': {'id': 20001, 'caption': 'BtnBroken',
                      'position': {'left': 10, 'top': 150, 'width': 140, 'height': 40},
                      'alignment': 37, 'colorTab': {'color0': 0, 'color1': -1, 'color2': -1,
                                                    'color3': -1, 'color4': -1},
                      'fontSize': 18, 'text': 'broken', 'visible': True},
        # ③ 图 ≠ 盒（10×10 挂在 200×40）
        'seekbar__4': {'id': 91001, 'caption': 'SkWrong',
                       'position': {'left': 10, 'top': 210, 'width': 200, 'height': 40},
                       'backgroundColor': -1, 'backgroundPic': 'images/wrong_10x10.png',
                       'defProgress': 0, 'max': 100, 'orientation': 0,
                       'progressPic': '', 'secondaryProgressPic': '',
                       'thumb': {'size': {'width': 0, 'height': 0}, 'normalPic': '',
                                 'pressedPic': ''},
                       'touchable': True, 'visible': True},
    }


class TestRegionAttribution(unittest.TestCase):

    def setUp(self):
        self.root = U.project()
        self.addCleanup(U.cleanup, self.root)
        self.json = os.path.join(self.root, 'ui', 'main.json')
        U.write(self.json, json.dumps(_page(), ensure_ascii=False, indent=2))
        img = Image.new('RGBA', (10, 10), (0, 128, 255, 255))
        img.save(os.path.join(self.root, 'resources', 'images', 'wrong_10x10.png'))
        self.render = os.path.join(self.root, 'temp', 'render', 'main.png')
        self.report = os.path.join(self.root, 'temp', 'render', 'main.report.json')
        os.makedirs(os.path.dirname(self.render), exist_ok=True)
        cmd = [sys.executable, os.path.join(BASE, 'ui_tools', 'json2img.py'), self.root,
               '--page', 'main', '--out', self.render, '--json-report', self.report]
        p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                           errors='replace')
        if not os.path.isfile(self.render):
            self.skipTest('json2img 没出图（rc=%s）：%s' % (p.returncode, (p.stderr or '')[-200:]))

    def _device(self, boxes):
        """渲染图 + 在指定控件盒里刷一块色 → 模拟"真机与渲染不一致"。"""
        im = Image.open(self.render).convert('RGB')
        d = ImageDraw.Draw(im)
        for k in boxes:
            x, y, w, h = BOXES[k]
            d.rectangle([x + 4, y + 4, x + w - 5, y + h - 5], fill=PAINT)
        out = os.path.join(self.root, 'temp', 'render', 'device.png')
        im.save(out)
        return out

    def _attribute(self, boxes, **kw):
        dev = self._device(boxes)
        rep = json.load(io.open(self.report, encoding='utf-8')) if os.path.isfile(self.report) else None
        return RA.attribute(self.json, self.render, dev, render_report=rep,
                            project_root=self.root, **kw)

    def _layer(self, rep, key):
        for r in rep['regions']:
            if r['key'] == key:
                return r['layer'], r
        self.fail('区域里没有 %s：%s' % (key, [r['key'] for r in rep['regions']]))

    def test_each_layer(self):
        rep = self._attribute(list(BOXES))
        self.assertEqual(self._layer(rep, 'button__3')[0], 'C/EMIT-FIELDS')
        self.assertEqual(self._layer(rep, 'seekbar__4')[0], 'C/ASSET-GEOMETRY')
        self.assertEqual(self._layer(rep, 'textview__2')[0], 'E/RENDERER-BLINDSPOT')
        self.assertEqual(self._layer(rep, 'window__1')[0], 'U/UNATTRIBUTED')
        self.assertFalse(rep['pass'], '有 C 层与未归因区域 → 不许判 PASS')
        self.assertTrue(rep['blocking'])
        self.assertGreater(rep['eLayerSharePct'], 0.0)
        self.assertLess(rep['eLayerSharePct'], 100.0)
        self.assertLess(rep['attributedPct'], 100.0)     # U 层那块没归因
        self.assertTrue(self._layer(rep, 'button__3')[1]['evidence'],
                        '归因必须带证据（否则等于猜）')

    def test_all_blind_spot_passes(self):
        """只有渲染器盲区那块有差异 → PASS（离线判不了，须真机复验；不许当成真缺陷去改渲染器）。"""
        rep = self._attribute(['textview__2'])
        self.assertTrue(rep['pass'], rep)
        self.assertEqual(rep['blocking'], [])
        self.assertAlmostEqual(rep['eLayerSharePct'], 100.0, places=1)
        self.assertIn('真机', rep['hint'])

    def test_no_diff_is_clean(self):
        dev = os.path.join(self.root, 'temp', 'render', 'same.png')
        Image.open(self.render).convert('RGB').save(dev)
        rep = RA.attribute(self.json, self.render, dev, project_root=self.root)
        self.assertTrue(rep['pass'], rep)
        self.assertEqual(rep['regions'], [])
        self.assertEqual(rep['totalBadPixels'], 0)

    def test_render_check_op_carries_layer_attribution(self):
        """接线（T2.4）：`flythings_ui_visual(action="render_check")` 的返回体要带区域级层归因。

        判据（与模块同源）：`layerAttribution.blocking` 里能指到层；`pass` 仍由 wysiwyg_diff 定，
        本 op 不许因为归因把 pass 反过来（只补充信息）。
        """
        import kb_tools as K
        dev = self._device(['button__3'])
        rep = json.load(io.open(self.report, encoding='utf-8')) if os.path.isfile(self.report) else None
        with mock.patch.object(K, '_find_json2img_report', return_value=rep):
            r = json.loads(K._ui_render_check(render=self.render, device=dev,
                                              page_json=self.json, project_root=self.root))
        self.assertTrue(r.get('success'), r)
        self.assertIn('layerAttribution', r, r)
        la = r['layerAttribution']
        self.assertIn('pass', la)
        self.assertTrue(any(x.get('key') == 'button__3' for x in la['blocking']), la)
        self.assertEqual([x['layer'] for x in la['blocking'] if x['key'] == 'button__3'],
                         ['C/EMIT-FIELDS'])
        self.assertIn('attribution', r, '逐控件像素归因（原口径）不许被挤掉')

    def test_top_does_not_flip_pass(self):
        """`--top` 只该影响**展示条数**，不许影响判据（2026-10-05 检讨修）。

        原实现先截断再算 blocking/pass → `top=1` 把阻塞区域截掉就能把 FAIL 报成 PASS，
        且百分比分母与 `totalBadPixels` 脱节。
        """
        full = self._attribute(list(BOXES))
        self.assertFalse(full['pass'])
        trunc = self._attribute(list(BOXES), top=1)
        self.assertFalse(trunc['pass'], '--top 截断把 FAIL 报成了 PASS：%s' % trunc)
        self.assertTrue(trunc['blocking'], '--top 截断丢了 blocking 列表')
        self.assertEqual(trunc['regionsTotal'], full['regionsTotal'], '总数口径被截断改了')
        self.assertLessEqual(len(trunc['regions']), 1)
        self.assertAlmostEqual(trunc['attributedPct'], full['attributedPct'], places=2)

    def test_asset_layer_unavailable_is_not_silent(self):
        """没给 project_root → 「C/ASSET-GEOMETRY 没核」必须在 notes 里说清（不静默）。"""
        dev = self._device(['seekbar__4'])
        rep = json.load(io.open(self.report, encoding='utf-8')) if os.path.isfile(self.report) else None
        r = RA.attribute(self.json, self.render, dev, render_report=rep, project_root='')
        self.assertTrue(r.get('success'), r)
        self.assertIn('notes', r, '归因层没核却没有任何说明：%s' % r)
        self.assertTrue(any('ASSET-GEOMETRY' in n for n in r['notes']), r['notes'])

    def test_size_mismatch_is_reported(self):
        dev = os.path.join(self.root, 'temp', 'render', 'small.png')
        Image.new('RGB', (10, 10), (0, 0, 0)).save(dev)
        rep = RA.attribute(self.json, self.render, dev, project_root=self.root)
        self.assertFalse(rep['success'])
        self.assertIn('尺寸不一致', rep['error'])


if __name__ == '__main__':
    unittest.main()
