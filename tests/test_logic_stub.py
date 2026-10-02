# -*- coding: utf-8 -*-
"""logic 回调桩生成（`flythings_gen_logic_stub`）的契约用例（v0.27.178）。

钉住四件事：
① schema 的 `callbacks` 真源条目齐备（name/sig/when/stub，且带 `{Caption}` 占位）；
② 每类可交互控件都能生成，listview 的 3 条**成组**给全；
③ **只补不改 + 幂等**（再跑一次不重复追加，已有函数绝不覆盖）；
④ 生成物不踩 check_all 的字符级口径（注释里不出现孤立括号）。
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (BASE, os.path.join(BASE, 'ui_tools')):
    if p not in sys.path:
        sys.path.insert(0, p)
import logic_tools as lt                      # noqa: E402
import ui_schema_loader as usl                # noqa: E402

INTERACTIVE_WITH_CB = ('button', 'listview', 'seekbar', 'checkbox',
                       'radiogroup', 'edittext', 'slidewindow')


def _mk_project(ctrls, stub_body='static void onUI_init(){\n}\n'):
    root = tempfile.mkdtemp(prefix='stub_test_')
    os.makedirs(os.path.join(root, 'ui'))
    os.makedirs(os.path.join(root, 'src', 'logic'))
    page = {'id': 1, 'resolution': {'width': 1024, 'height': 600},
            'position': {'left': 0, 'top': 0, 'width': 1024, 'height': 600},
            'backgroundColor': -1}
    for n, (t, cap) in enumerate(ctrls, 1):
        page['%s__%d' % (t, n)] = {'id': 1000 + n, 'caption': cap,
                                   'position': {'left': 0, 'top': 0, 'width': 10, 'height': 10}}
    with io.open(os.path.join(root, 'ui', 'main.json'), 'w', encoding='utf-8') as fh:
        fh.write(json.dumps(page, ensure_ascii=False))
    with io.open(os.path.join(root, 'src', 'logic', 'mainLogic.cc'), 'w', encoding='utf-8') as fh:
        fh.write(stub_body)
    return root


def _read(root):
    with io.open(os.path.join(root, 'src', 'logic', 'mainLogic.cc'), encoding='utf-8') as fh:
        return fh.read()


class TestSchemaCallbacks(unittest.TestCase):

    def test_entries_wellformed(self):
        for t in INTERACTIVE_WITH_CB:
            cbs = usl.callbacks(t)
            self.assertTrue(cbs, '%s 没有回调条目' % t)
            for cb in cbs:
                for k in ('name', 'sig', 'when', 'stub'):
                    self.assertIn(k, cb, '%s 的 %r 缺 %s' % (t, cb.get('name'), k))
                self.assertIn('{Caption}', cb['name'], '%s 的 name 缺 {Caption}' % t)
                self.assertIn('{Caption}', cb['sig'], '%s 的 sig 缺 {Caption}' % t)

    def test_non_interactive_has_no_callbacks(self):
        """纯显示控件不该有生成回调（textview / window / painter 等）。"""
        for t in ('textview', 'window', 'painter', 'digitalclock'):
            self.assertEqual(usl.callbacks(t), [], '%s 不该有回调桩' % t)


class TestGenerate(unittest.TestCase):

    def setUp(self):
        self.roots = []

    def tearDown(self):
        for r in self.roots:
            shutil.rmtree(r, ignore_errors=True)

    def _mk(self, ctrls, body=None):
        r = _mk_project(ctrls) if body is None else _mk_project(ctrls, body)
        self.roots.append(r)
        return r

    def test_generates_all_interactive_types(self):
        r = self._mk([(t, 'Cap' + t.title()) for t in INTERACTIVE_WITH_CB])
        out = lt.gen_logic_stub(r)
        self.assertTrue(out['ok'], out)
        # button1 + listview3 + 其余各 1 = 9
        self.assertEqual(out['generatedCount'], 9, out['pages'][0]['generated'])
        src = _read(r)
        for fn in ('onButtonClick_CapButton', 'getListItemCount_CapListview',
                   'obtainListItemData_CapListview', 'onListItemClick_CapListview',
                   'onProgressChanged_CapSeekbar', 'onCheckedChanged_CapCheckbox',
                   'onCheckedChanged_CapRadiogroup', 'onEditTextChanged_CapEdittext',
                   'onSlideItemClick_CapSlidewindow'):
            self.assertIn(fn, src, '缺 %s' % fn)

    def test_callback_name_uses_caption_not_key_index(self):
        r = self._mk([('button', 'BtnSubmit')])
        lt.gen_logic_stub(r)
        self.assertIn('onButtonClick_BtnSubmit', _read(r))
        self.assertNotIn('onButtonClick_button__1', _read(r))

    def test_idempotent(self):
        """★ 再跑一次必须全 skip（否则会重复追加）。"""
        r = self._mk([('button', 'B'), ('listview', 'L')])
        first = lt.gen_logic_stub(r)
        second = lt.gen_logic_stub(r)
        self.assertEqual(first['generatedCount'], 4)
        self.assertEqual(second['generatedCount'], 0, second['pages'][0]['generated'])
        self.assertEqual(second['writtenCount'], 0)
        src = _read(r)
        self.assertEqual(src.count('onButtonClick_B'), 1, '出现重复桩')

    def test_does_not_touch_existing_business_code(self):
        """只补不改：已有函数体原样保留。"""
        body = 'static void onUI_init(){\n}\n\nstatic bool onButtonClick_B(ZKButton *p){\n    return true;  // 业务\n}\n'
        r = self._mk([('button', 'B')], body)
        out = lt.gen_logic_stub(r)
        self.assertEqual(out['generatedCount'], 0)
        self.assertIn('// 业务', _read(r))

    def test_dry_run_writes_nothing(self):
        r = self._mk([('button', 'B')])
        before = _read(r)
        out = lt.gen_logic_stub(r, dry_run=True)
        self.assertEqual(out['generatedCount'], 1)
        self.assertEqual(out['writtenCount'], 0)
        self.assertEqual(_read(r), before, 'dry_run 不该落盘')

    def test_no_stray_parens_in_generated_comments(self):
        """check_all #8：注释里的括号也计数 → 生成物必须括号平衡。"""
        r = self._mk([(t, 'Cap') for t in INTERACTIVE_WITH_CB])
        lt.gen_logic_stub(r)
        src = _read(r)
        self.assertEqual(src.count('('), src.count(')'), '生成物括号不平衡')

    def test_missing_logic_file_reports_error(self):
        r = self._mk([('button', 'B')])
        os.remove(os.path.join(r, 'src', 'logic', 'mainLogic.cc'))
        out = lt.gen_logic_stub(r)
        self.assertTrue(out['ok'])
        self.assertIn('error', out['pages'][0])

    def test_unknown_page_and_no_ui(self):
        r = self._mk([('button', 'B')])
        out = lt.gen_logic_stub(r, page='nope')
        self.assertFalse(out['ok'])
        self.assertEqual(out['error']['code'], 'NO_PAGE')

    def test_missing_project(self):
        out = lt.gen_logic_stub(os.path.join(tempfile.gettempdir(), 'no_such_proj_xyz'))
        self.assertFalse(out['ok'])
        self.assertEqual(out['error']['code'], 'NO_PROJECT')


if __name__ == '__main__':
    unittest.main()
