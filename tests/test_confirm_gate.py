# -*- coding: utf-8 -*-
"""确认稿硬闸门契约（T3.1/T3.2，2026-10-05 需求方拍板「确认稿硬闸门要上」）。

钉住四件事：
  ① **无稿 / 过期稿 → 拒绝**（`CONFIRM_REQUIRED`），且**根本不调用下游 pack**（不产生副作用）；
  ② **更新且指纹相符的稿 → 放行**；
  ③ **指纹不符 → 拒绝**（mtime 更新也救不了：确认的不是这一版）；
  ④ **`force_confirm=True` → 放行且留痕**（`confirmOverridden` + warnings 一条）。

自证纪律：把任一条断言里的「拒绝」改回放行（或反过来），对应用例必须变红。
"""
import io
import json
import os
import shutil
import sys
import tempfile
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

PAGE_NAME = 'main.json'
PAGE = {
    "id": 0,
    "resolution": {"width": 480, "height": 272},
    "position": {"left": 0, "top": 0, "width": 480, "height": 272},
    "backgroundColor": 16777215,
    "textview__1": {
        "id": 50001, "caption": "TvTitle",
        "position": {"left": 20, "top": 20, "width": 200, "height": 40},
        "alignment": 36, "colorTab": {"color0": 0, "color1": -1, "color2": -1,
                                      "color3": -1, "color4": -1},
        "fontSize": 18, "text": "Hello", "touchable": False, "visible": True,
    },
}

T0 = 1700000000.0          # 固定基准时间（避免依赖真实时钟/文件系统精度）


class _Base(unittest.TestCase):

    def setUp(self):
        self.root = U.project()
        self.addCleanup(U.cleanup, self.root)
        self.json = os.path.join(self.root, 'ui', PAGE_NAME)
        self._write_json(PAGE)
        self.draft = os.path.join(self.root, 'ui', 'main.confirm.html')

    def _write_json(self, page):
        U.write(self.json, json.dumps(page, ensure_ascii=False, indent=1))
        os.utime(self.json, (T0, T0))

    def _write_draft(self, newer_than_json=True, fingerprint=True, body='<html>draft</html>'):
        U.write(self.draft, body)
        os.utime(self.draft, (T0 + (10 if newer_than_json else -10),) * 2)
        if fingerprint:
            err = K.write_confirm_fingerprint(self.json, self.draft, True)
            self.assertEqual(err, '', '指纹应写入成功：%s' % err)

    def _gate(self):
        return K._confirm_gate(self.root)


class TestDraftKinds(_Base):
    """**哪些稿算「需求方确认」**（2026-10-05 需求方口径）：confirm / preview 算，edit **不算**。

    `.preview.html` 是可转发的预览稿（需求确认载体）；`_edit/*.edit.html` 是"用户自己改坐标/规格参数"
    的在线编辑器 —— 拿它当确认稿等于把工具当确认动作。
    """

    def test_preview_html_counts_as_confirmation(self):
        self.draft = os.path.join(self.root, 'ui', 'main.preview.html')
        self._write_draft(newer_than_json=True, fingerprint=True)
        g = self._gate()
        self.assertFalse(g['confirmBlocked'], '可转发的预览稿应算确认稿：%s' % g)
        self.assertEqual(os.path.basename(g['confirmDraft']), 'main.preview.html')

    def test_edit_html_does_not_count_as_confirmation(self):
        ed = os.path.join(self.root, 'ui', '_edit', 'main.edit.html')
        U.write(ed, '<html>editor</html>')
        os.utime(ed, (T0 + 60,) * 2)
        g = self._gate()
        self.assertTrue(g['confirmBlocked'], '编辑器产物被当成确认稿了：%s' % g)
        self.assertEqual(g['confirmReason'], 'no_draft')
        self.assertNotIn('edit.html', g.get('confirmDraft') or '')


class TestGateDecision(_Base):

    def test_no_draft_blocks(self):
        g = self._gate()
        self.assertTrue(g['confirmBlocked'], '没有确认稿时必须拦')
        self.assertEqual(g['confirmReason'], 'no_draft')
        self.assertIn('for_customer=True', g['confirmHint'])

    def test_stale_draft_blocks(self):
        self._write_draft(newer_than_json=False)
        g = self._gate()
        self.assertTrue(g['confirmBlocked'], '确认稿比 json 旧时必须拦')
        self.assertEqual(g['confirmReason'], 'stale_draft')

    def test_fresh_legacy_draft_allows_but_flags(self):
        """更新但**没有指纹**的历史稿：放行，但如实标 legacy（不假装核对过版本）。"""
        self._write_draft(fingerprint=False)
        g = self._gate()
        self.assertFalse(g['confirmBlocked'], '更新的稿子不该拦')
        self.assertTrue(g['confirmLegacy'])
        self.assertTrue(any('指纹' in w for w in g['confirmWarnings']),
                        '历史稿必须在 warnings 里说清「未核对内容版本」')

    def test_fresh_draft_with_matching_fingerprint_allows(self):
        self._write_draft()
        g = self._gate()
        self.assertFalse(g['confirmBlocked'])
        self.assertFalse(g['confirmLegacy'])
        self.assertEqual(g['confirmFingerprint']['checked'], 1)
        self.assertEqual(g['confirmFingerprint']['mismatched'], [])

    def test_fingerprint_mismatch_blocks_even_if_draft_newer(self):
        """确认后又改了 json（稿仍比 json 新）→ 必须拦：确认的不是这一版。"""
        self._write_draft()
        page = json.loads(json.dumps(PAGE))
        page['textview__1']['text'] = '改过了'
        self._write_json(page)                      # json 内容变了（mtime 仍是 T0）
        g = self._gate()
        self.assertTrue(g['confirmBlocked'], '指纹不符必须拦（mtime 更新救不了）')
        self.assertEqual(g['confirmReason'], 'fingerprint_mismatch')
        self.assertTrue(g['confirmFingerprint']['mismatched'])


class TestOpsBlocked(_Base):
    """op 层：被拦时**不许调用下游**（无副作用），返回体可机读。"""

    def test_fui_pack_blocked_without_calling_downstream(self):
        with mock.patch.object(K.pt, 'flythings_fui_pack') as m:
            r = json.loads(K.flythings_fui_pack(self.json))
        self.assertFalse(r['ok'])
        self.assertEqual(r['error']['code'], 'CONFIRM_REQUIRED')
        self.assertTrue(r['error'].get('action'), '失败返回必须自带下一步（域⑫ action）')
        self.assertTrue(r['confirmBlocked'])
        m.assert_not_called()
        self.assertFalse(os.path.isfile(os.path.join(self.root, 'ui', 'main.ftu')))

    def test_fui_pack_allowed_when_draft_fresh(self):
        self._write_draft()
        with mock.patch.object(K.pt, 'flythings_fui_pack',
                               return_value={'success': True, 'ftuPath': 'x.ftu'}) as m:
            r = json.loads(K.flythings_fui_pack(self.json))
        self.assertEqual(m.call_count, 1, '有更新的确认稿时应放行')
        self.assertFalse(r.get('confirmOverridden'))
        self.assertFalse(r.get('confirmBlocked'))

    def test_fui_pack_force_confirm_passes_with_marker(self):
        with mock.patch.object(K.pt, 'flythings_fui_pack',
                               return_value={'success': True, 'ftuPath': 'x.ftu'}):
            r = json.loads(K.flythings_fui_pack(self.json, force_confirm=True))
        self.assertTrue(r.get('confirmOverridden'), 'force_confirm 跳过必须留痕')
        self.assertTrue(any('force_confirm' in w for w in (r.get('warnings') or [])),
                        '跳过要在 warnings 里记一条')

    def test_build_ui_flow_blocks_when_new_layout_would_be_pushed(self):
        """没有 ftu（从没 pack 过）+ 无确认稿 → 拦。"""
        with mock.patch.object(K.pt, 'flythings_build_ui_flow') as m:
            r = json.loads(K.flythings_build_ui_flow(self.root, with_launch=False))
        self.assertFalse(r['ok'])
        self.assertEqual(r['error']['code'], 'CONFIRM_REQUIRED')
        self.assertTrue(r['layoutChanged'])
        m.assert_not_called()

    def test_build_ui_flow_allows_redeploy_of_confirmed_layout(self):
        """ftu 比 json 新（布局没变）+ 有确认稿 → 不拦（只是重推已确认的布局）。"""
        self._write_draft()
        ftu = os.path.join(self.root, 'ui', 'main.ftu')
        U.write(ftu, 'x')
        os.utime(ftu, (T0 + 100,) * 2)
        with mock.patch.object(K.pt, 'flythings_build_ui_flow',
                               return_value={'success': True}) as m:
            r = json.loads(K.flythings_build_ui_flow(self.root, with_launch=False))
        self.assertEqual(m.call_count, 1, 'layout 没变时不该拦（否则每次重启设备都被拦）')
        self.assertFalse(r.get('confirmBlocked'))

    def test_ui_visual_edit_apply_pack_blocked(self):
        changes = json.dumps({'file': PAGE_NAME, 'changes': {'textview__1': {'left': 30}}})
        r = json.loads(K.flythings_ui_visual(action='edit_apply', project_root=self.root,
                                             changes=changes, pack=True))
        self.assertFalse(r['ok'])
        self.assertEqual(r['error']['code'], 'CONFIRM_REQUIRED')

    def test_ui_visual_edit_apply_without_pack_not_gated(self):
        """只写 json（pack=False）不推设备 → 不该被闸门拦（否则等于禁止改布局）。"""
        changes = json.dumps({'file': PAGE_NAME, 'changes': {'textview__1': {'left': 30}}})
        with mock.patch.object(K, '_ui_edit_apply', return_value={'success': True}) as m:
            r = json.loads(K.flythings_ui_visual(action='edit_apply', project_root=self.root,
                                                 changes=changes, pack=False))
        self.assertEqual(m.call_count, 1)
        self.assertNotEqual((r.get('error') or {}).get('code'), 'CONFIRM_REQUIRED')


class TestPreviewWritesFingerprint(_Base):
    """出确认稿时落指纹（T3.2）——闸门靠它判「确认的是哪一版」。"""

    def test_preview_writes_fingerprint_with_json_hash(self):
        r = json.loads(K.flythings_ui_preview(self.root, for_customer=True))
        self.assertTrue(r.get('success'), '预览稿应生成成功：%s' % r)
        fp = K._confirm_fingerprint_path(self.draft)
        self.assertTrue(os.path.isfile(fp), '确认稿必须带指纹副文件：%s' % fp)
        payload = json.load(io.open(fp, encoding='utf-8'))
        recs = payload.get('jsons') or []
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]['sha256'], K._file_sha256(self.json),
                         '指纹必须是这份 json 的内容哈希')
        # 指纹与真实内容一致 → 闸门放行
        g = self._gate()
        self.assertFalse(g['confirmBlocked'])
        self.assertFalse(g['confirmLegacy'])

    def test_preview_warns_when_draft_outside_ui(self):
        """稿子落到 <项目>/ui 之外 → 闸门扫不到它，必须如实提示（不静默）。"""
        outside = os.path.join(self.root, 'export')
        r = json.loads(K.flythings_ui_preview(self.root, output_dir=outside,
                                              for_customer=True))
        self.assertTrue(r.get('gateWarning'), '稿不在 ui/ 下必须给 gateWarning')
        self.assertTrue(os.path.isfile(os.path.join(outside, 'main.confirm.html')))


if __name__ == '__main__':
    unittest.main()
