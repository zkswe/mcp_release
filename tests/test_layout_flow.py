# -*- coding: utf-8 -*-
"""布局链路契约：fui pack 确定性 / edit_ftu 默认不覆盖（v0.27.31 破坏性默认值收口）/
ui_edit_apply dry_run 不写盘 / validate_project / read_json。

为什么要有：
  - 「默认不覆盖 + 先备份」是 v0.27.31 的事故对策，必须有用例钉住，否则哪天被人「顺手」改回默认覆盖
  - fui pack 结果应确定性（同 json → 同 ftu 字节），否则 diff/回归对比无意义
"""
import glob
import io
import json
import os
import shutil
import unittest

import _util as U


class LayoutBase(unittest.TestCase):
    def setUp(self):
        self.tmp = U.project()
        self.res = os.path.join(self.tmp, 'ui', '1024x600')
        os.makedirs(self.res, exist_ok=True)
        self.json_path = os.path.join(self.res, 'main.json')
        shutil.copy(U.fixture('main.json'), self.json_path)

    def tearDown(self):
        U.cleanup(self.tmp)


class TestFuiPack(LayoutBase):
    def test_pack_ok_and_deterministic(self):
        r = U.jcall('flythings_fui_pack', U.bypass_gates({'json_path': self.json_path}))
        self.assertTrue(r['ok'], r)
        ftu = os.path.join(self.res, 'main.ftu')
        self.assertTrue(os.path.isfile(ftu))
        first = io.open(ftu, 'rb').read()
        r2 = U.jcall('flythings_fui_pack', U.bypass_gates({'json_path': self.json_path}))
        self.assertTrue(r2['ok'])
        self.assertEqual(first, io.open(ftu, 'rb').read(), 'pack 不确定（同 json 出不同 ftu）')

    def test_pack_reports_affected_files(self):
        r = U.jcall('flythings_fui_pack', U.bypass_gates({'json_path': self.json_path}))
        self.assertTrue(any('main.ftu' in f for f in r.get('affectedFiles', [])), r.get('affectedFiles'))


class TestEditFtuSafety(LayoutBase):
    def _packed(self):
        r = U.jcall('flythings_fui_pack', U.bypass_gates({'json_path': self.json_path}))
        self.assertTrue(r['ok'], r)
        ftu = os.path.join(self.res, 'main.ftu')
        return ftu, io.open(ftu, 'rb').read()

    def test_default_does_not_overwrite_original(self):
        ftu, before = self._packed()
        ops = json.dumps([{'op': 'set', 'target': 'textview__1', 'props': {'text': 'unittest'}}],
                         ensure_ascii=False)
        r = U.jcall('flythings_edit_ftu', {'ftu_path': ftu, 'operations': ops})
        self.assertTrue(r['ok'], r)
        self.assertFalse(r.get('overwriteOriginal'), '默认必须不覆盖原 ftu')
        self.assertEqual(io.open(ftu, 'rb').read(), before, '原 ftu 被改动了')
        self.assertTrue(os.path.isfile(os.path.join(self.res, 'main.edited.ftu')))
        self.assertTrue(os.path.isfile(ftu + '.bak'), '缺 .bak 备份')

    def test_json_source_updated_with_backup(self):
        ftu, _ = self._packed()
        ops = json.dumps([{'op': 'set', 'target': 'textview__1', 'props': {'text': 'unittest'}}],
                         ensure_ascii=False)
        r = U.jcall('flythings_edit_ftu', {'ftu_path': ftu, 'operations': ops})
        self.assertTrue(r['ok'], r)
        self.assertTrue(os.path.isfile(self.json_path + '.bak'))
        d = json.loads(io.open(self.json_path, encoding='utf-8').read())
        self.assertEqual(d['textview__1']['text'], 'unittest')


class TestUiEditApplySafety(unittest.TestCase):
    """v0.27.31 「写操作默认安全」契约：默认不 pack；dry_run 不写盘；写盘必留 .bak。

    注：ui_edit_apply 要求 json 是规范格式（indent=2 / ensure_ascii=False），
    否则拒写以免整文件重排——所以这里自己造规范样例，不直接拷 examples/main.json。
    """

    def setUp(self):
        self.tmp = U.project()
        self.page = os.path.join(self.tmp, 'ui', '1024x600', 'main.json')
        doc = {'id': 0, 'resolution': {'width': 480, 'height': 272},
               'position': {'left': 0, 'top': 0, 'width': 480, 'height': 272},
               'textview__1': {'type': 'textview', 'caption': 'T', 'id': 50001,
                               'position': {'left': 1, 'top': 2, 'width': 100, 'height': 30},
                               'text': 'hello', 'touchable': False}}
        U.write(self.page, json.dumps(doc, ensure_ascii=False, indent=2))
        self.changes = json.dumps(
            {'file': 'main.json', 'resolution': '480x272',
             'changes': {'textview__1': {'left': 33, 'top': 44}}}, ensure_ascii=False)

    def tearDown(self):
        U.cleanup(self.tmp)

    def test_dry_run_does_not_write(self):
        before = io.open(self.page, encoding='utf-8').read()
        r = U.jcall('flythings_ui_visual',
                    {'action': 'edit_apply', 'project_root': self.tmp,
                     'changes': self.changes, 'dry_run': True})
        self.assertTrue(r['ok'], r)
        self.assertEqual(io.open(self.page, encoding='utf-8').read(), before, 'dry_run 写盘了')
        self.assertFalse(os.path.exists(self.page + '.bak'), 'dry_run 不该留 .bak')

    def test_write_creates_backup_and_no_pack_by_default(self):
        r = U.jcall('flythings_ui_visual', {'action': 'edit_apply', 'project_root': self.tmp,
                                            'changes': self.changes})
        self.assertTrue(r['ok'], r)
        self.assertTrue(os.path.isfile(self.page + '.bak'))
        d = json.loads(io.open(self.page, encoding='utf-8').read())
        self.assertEqual(d['textview__1']['position']['left'], 33)
        self.assertFalse(os.path.isfile(os.path.join(self.tmp, 'ui', '1024x600', 'main.ftu')),
                         '默认不该 pack（要 pack 得显式传 pack=True）')


class TestReadAndValidate(LayoutBase):
    def test_read_json(self):
        r = U.jcall('flythings_read_json', {'json_path': self.json_path})
        self.assertTrue(r['ok'], r)

    def test_validate_project_on_fixture(self):
        r = U.jcall('flythings_validate_project', {'project_root': self.tmp})
        self.assertIsInstance(r.get('errors', []), list)

    def test_read_json_missing_file_reports_error(self):
        r = U.jcall('flythings_read_json', {'json_path': os.path.join(self.tmp, 'nope.json')})
        self.assertFalse(r['ok'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
