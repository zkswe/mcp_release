# -*- coding: utf-8 -*-
"""编译式验收闸门契约（T1.3，2026-10-05）。

需求方原话：「用一个工具类似 C 程序编译一样验收 json 合理性，减少上机调试来回掰扯问题。」
判据：`fui pack` **自己不校验字段**（写错照样 pack「成功」，真机加载才无声挂死）→
pack / build_ui_flow 之前必须先跑 `ui_compile`，有 fatal/error **拒绝**（`UI_JSON_INVALID`），
确需强制继续传 `allow_unvalidated=True`（放行但留痕）。

自证纪律：把任一断言里的「拒绝」改回放行（或删掉闸门调用），对应用例必须变红。
"""
import json
import os
import sys
import unittest
from unittest import mock

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
for _p in (BASE, TESTS):          # tests/ 进 sys.path：与全仓 52 个用例统一 `import _util`
    if _p not in sys.path:
        sys.path.insert(0, _p)

import kb_tools as K                                        # noqa: E402
# ⚠️ 必须 `import _util`（**不要** `import tests._util`）：后者会造出第二份模块实例，
# 离线守卫的 `_ADB_GUARD` 计数器分家 → tests/test_offline_guard.py 全量跑时假红（实测 2026-10-05）。
import _util as U                                           # noqa: E402

T0 = 1700000000.0


def _page(bad=False):
    tv = {
        "id": 50001, "caption": "TvTitle",
        "position": {"left": 20, "top": 20, "width": 200, "height": 40},
        "alignment": 36, "colorTab": {"color0": 0, "color1": -1, "color2": -1,
                                      "color3": -1, "color4": -1},
        "fontSize": 18, "text": "Hello", "touchable": False, "visible": True,
    }
    if bad:
        # 子盒对象字段写成字符串 = 真机 ftu 加载无声挂死（ui_schema.json valueRules.subboxType）
        tv["position"] = "20,20,200,40"
    return {"id": 0,
            "resolution": {"width": 480, "height": 272},
            "position": {"left": 0, "top": 0, "width": 480, "height": 272},
            "backgroundColor": 16777215,
            "textview__1": tv}


class _Base(unittest.TestCase):

    def setUp(self):
        self.root = U.project()
        self.addCleanup(U.cleanup, self.root)
        self.json = os.path.join(self.root, 'ui', 'main.json')
        self.bad = False
        self._write()

    def _write(self, bad=None):
        if bad is not None:
            self.bad = bad
        U.write(self.json, json.dumps(_page(self.bad), ensure_ascii=False, indent=1))
        os.utime(self.json, (T0, T0))

    def _fresh_draft(self):
        """出一份"更新且指纹相符"的确认稿，让确认闸门不参与（本文件只测编译闸门）。"""
        draft = os.path.join(self.root, 'ui', 'main.confirm.html')
        U.write(draft, '<html>draft</html>')
        os.utime(draft, (T0 + 10,) * 2)
        err = K.write_confirm_fingerprint(self.json, draft, True)
        self.assertEqual(err, '', err)


class TestPackGate(_Base):

    def test_invalid_json_blocks_pack_without_calling_fui(self):
        self._write(bad=True)
        with mock.patch.object(K.pt, 'flythings_fui_pack') as m:
            r = json.loads(K.flythings_fui_pack(self.json))
        self.assertFalse(r['ok'], '字段写错的 json 不该被 pack')
        self.assertEqual(r['error']['code'], 'UI_JSON_INVALID')
        self.assertTrue(r['error'].get('action'), '失败返回必须自带下一步')
        self.assertTrue(r['uiDiagnostics'], '必须回逐条诊断（规则号/路径/修法）')
        self.assertTrue(any(d.get('rule') for d in r['uiDiagnostics']))
        m.assert_not_called()
        self.assertFalse(os.path.isfile(os.path.join(self.root, 'ui', 'main.ftu')))

    def test_allow_unvalidated_passes_with_marker(self):
        self._write(bad=True)
        self._fresh_draft()                   # 确认闸门另算：本用例只看"跳过验收"的留痕
        with mock.patch.object(K.pt, 'flythings_fui_pack',
                               return_value={'success': True, 'ftuPath': 'x.ftu'}):
            r = json.loads(K.flythings_fui_pack(self.json, allow_unvalidated=True))
        self.assertTrue(r.get('uiUnvalidated'), '强制放行必须留痕：%s' % r)
        self.assertTrue(any('allow_unvalidated' in w for w in (r.get('warnings') or [])),
                        '强制放行要在 warnings 里记一条')
        self.assertTrue(r.get('uiDiagnostics'), '强跳时诊断仍要带出来（别把问题藏起来）')

    def test_allow_unvalidated_still_respects_confirm_gate(self):
        """两个闸门互相独立：跳了验收不等于跳了确认 —— 没确认稿照样拦，但"跳过验收"要留痕。"""
        self._write(bad=True)                 # 没有确认稿
        with mock.patch.object(K.pt, 'flythings_fui_pack') as m:
            r = json.loads(K.flythings_fui_pack(self.json, allow_unvalidated=True))
        self.assertEqual(r['error']['code'], 'CONFIRM_REQUIRED')
        self.assertTrue(r.get('uiUnvalidated'), '被确认闸门拦下时也要带上"已跳过验收"的留痕')
        m.assert_not_called()

    def test_valid_json_passes_and_reports_uicheck(self):
        self._fresh_draft()
        with mock.patch.object(K.pt, 'flythings_fui_pack',
                               return_value={'success': True, 'ftuPath': 'x.ftu'}) as m:
            r = json.loads(K.flythings_fui_pack(self.json))
        self.assertEqual(m.call_count, 1, '合法 json + 新确认稿应放行：%s' % r)
        self.assertIn('uiCheck', r, '放行时也要把编译结果带出来（fatal/error/warn）')
        self.assertEqual(r['uiCheck']['fatal'], 0)
        self.assertFalse(r.get('uiUnvalidated'))

    def test_compile_gate_runs_before_confirm_gate(self):
        """两个闸门都在时：先报编译失败（先修对错，再谈确认）。"""
        self._write(bad=True)          # 没有确认稿 → 两个闸门都该拦
        with mock.patch.object(K.pt, 'flythings_fui_pack') as m:
            r = json.loads(K.flythings_fui_pack(self.json))
        self.assertEqual(r['error']['code'], 'UI_JSON_INVALID')
        m.assert_not_called()

    def test_missing_ui_compile_is_not_silent(self):
        """工具缺失时不许假装验过：放行但明确说"这次没做编译式验收"。"""
        with mock.patch.object(K, 'uic', None):
            self._fresh_draft()
            with mock.patch.object(K.pt, 'flythings_fui_pack',
                                   return_value={'success': True, 'ftuPath': 'x.ftu'}):
                r = json.loads(K.flythings_fui_pack(self.json))
        self.assertTrue(any('ui_compile' in w for w in (r.get('warnings') or [])),
                        '缺工具必须如实说明：%s' % r.get('warnings'))


class TestBuildFlowGate(_Base):

    def test_invalid_json_blocks_build_flow(self):
        self._write(bad=True)
        with mock.patch.object(K.pt, 'flythings_build_ui_flow') as m:
            r = json.loads(K.flythings_build_ui_flow(self.root, with_launch=False))
        self.assertFalse(r['ok'])
        self.assertEqual(r['error']['code'], 'UI_JSON_INVALID')
        m.assert_not_called()

    def test_invalid_json_passes_with_allow_unvalidated(self):
        self._write(bad=True)
        self._fresh_draft()
        with mock.patch.object(K.pt, 'flythings_build_ui_flow',
                               return_value={'success': True}) as m:
            r = json.loads(K.flythings_build_ui_flow(self.root, with_launch=False,
                                                     allow_unvalidated=True))
        self.assertEqual(m.call_count, 1)
        self.assertTrue(r.get('uiUnvalidated'))

    def test_valid_json_and_fresh_draft_passes(self):
        self._fresh_draft()
        with mock.patch.object(K.pt, 'flythings_build_ui_flow',
                               return_value={'success': True}) as m:
            r = json.loads(K.flythings_build_ui_flow(self.root, with_launch=False))
        self.assertEqual(m.call_count, 1, '合法 json + 新确认稿应放行：%s' % r)
        self.assertEqual((r.get('uiCheck') or {}).get('fatal'), 0)

    def test_no_pack_no_compile_gate(self):
        """布局没变（ftu 比 json 新）→ 不会 pack，就不跑编译闸门（坏 json 也不拦）。"""
        self._write(bad=True)
        self._fresh_draft()
        ftu = os.path.join(self.root, 'ui', 'main.ftu')
        U.write(ftu, 'x')
        os.utime(ftu, (T0 + 100,) * 2)
        with mock.patch.object(K.pt, 'flythings_build_ui_flow',
                               return_value={'success': True}) as m:
            r = json.loads(K.flythings_build_ui_flow(self.root, with_launch=False))
        self.assertEqual(m.call_count, 1, '这次不 pack（重推已确认布局），编译闸门不该拦：%s' % r)
        self.assertFalse(r.get('uiCheck', {}).get('ran'))


if __name__ == '__main__':
    unittest.main()
