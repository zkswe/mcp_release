# -*- coding: utf-8 -*-
"""renderContract 覆盖声明契约（T4.1）。

钉住：
  ① 真仓 `--check` rc=0（10 条 row 一一对应，evidence 锚点都在代码里）；
  ② **自证**：删一条 row / 改非法 status / evidence 指向不存在的函数 → 必须报错；
  ③ row 集合的唯一真源是 `ui_schema.json#renderContract.rows`（本模块不重抄），且 json2img
     走自己的细粒度矩阵、两边行集合必须一致。
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
for _p in (BASE, TESTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _util as U                                           # noqa: E402

SPEC = os.path.join(BASE, 'scripts', 'check_render_contract_coverage.py')


def _mod():
    spec = importlib.util.spec_from_file_location('crc_cov', SPEC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TestCoverageDeclaration(unittest.TestCase):

    def setUp(self):
        self.m = _mod()
        self.tmp = tempfile.mkdtemp(prefix='mcp_crc_')
        self.addCleanup(U.cleanup, self.tmp)

    def _variant(self, mutate):
        """把真声明改一改写到临时文件，返回 check() 的错误列表。"""
        data = self.m.load()
        mutate(data)
        p = os.path.join(self.tmp, 'cov.json')
        with io.open(p, 'w', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(data, ensure_ascii=False))
        old = self.m.SPEC
        self.m.SPEC = p
        try:
            return self.m.check()
        finally:
            self.m.SPEC = old

    def test_real_repo_passes(self):
        self.assertEqual(self.m.check(), [])
        self.assertEqual(len(self.m.contract_rows()), 10, 'renderContract 应是 10 条')

    def test_missing_row_is_red(self):
        errs = self._variant(lambda d: d['implementations']['ui_tools/gen_res.py']['rows']
                             .pop('edge-aa'))
        self.assertTrue(any('未声明这些 row' in e and 'edge-aa' in e for e in errs), errs)

    def test_unknown_evidence_symbol_is_red(self):
        def mut(d):
            d['implementations']['ui_tools/gen_res.py']['rows']['edge-aa']['evidence'] = \
                ['no_such_function_xyz']
        errs = self._variant(mut)
        self.assertTrue(any('不存在' in e for e in errs), errs)

    def test_illegal_status_is_red(self):
        def mut(d):
            d['implementations']['ui_tools/gen_res.py']['rows']['edge-aa']['status'] = 'maybe'
        errs = self._variant(mut)
        self.assertTrue(any('status' in e and '非法' in e for e in errs), errs)

    def test_delegated_without_note_is_red(self):
        def mut(d):
            d['implementations']['ui_tools/gen_res.py']['rows']['rounding'] = \
                {'status': 'delegated'}
        errs = self._variant(mut)
        self.assertTrue(any('必须写 note' in e for e in errs), errs)

    def test_implements_without_evidence_is_red(self):
        def mut(d):
            d['implementations']['ui_tools/html2json.py']['rows']['pic-scale'] = \
                {'status': 'implements'}
        errs = self._variant(mut)
        self.assertTrue(any('没有 evidence' in e for e in errs), errs)

    def test_json2img_matrix_row_mismatch_is_red(self):
        """json2img 的细矩阵行集合必须与 renderContract 一致（它自己那份是真源，但要对齐）。"""
        mrows = json.load(io.open(os.path.join(BASE, 'ui_tools', 'json2img_coverage.json'),
                                  encoding='utf-8'))['rows']
        self.assertEqual(sorted(r['id'] for r in mrows), sorted(self.m.contract_rows()))

    def test_unknown_row_in_declaration_is_red(self):
        def mut(d):
            d['implementations']['ui_tools/check_all.py']['rows']['no-such-row'] = \
                {'status': 'delegated', 'note': 'x'}
        errs = self._variant(mut)
        self.assertTrue(any('renderContract 里没有的 row' in e for e in errs), errs)


if __name__ == '__main__':
    unittest.main()
