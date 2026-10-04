# -*- coding: utf-8 -*-
"""现场症状注册表（域⑭）的契约用例。

它钉住四件事：
  ① 注册表自检必须过（症状 ≥2 条、机制/规范/复验非空、doc 存在且不指向派生页自己）
  ② 派生页与注册表**一致**（漂移 = FAIL；派生页不许手改）
  ③ 缺失注册表要**抛错**，不许静默兜底
  ④ 派生页把症状原话**逐字**写进去（那是检索锚点，丢了就检不到）
"""
import io
import os
import shutil
import sys
import tempfile
import unittest

import _util as U

BASE = U.BASE
sys.path.insert(0, BASE)
import symptom_loader as S  # noqa: E402


class TestSymptomRegistry(unittest.TestCase):
    def test_registry_validates(self):
        errs = S.validate()
        self.assertEqual(errs, [], '症状注册表自检未过：%s' % errs[:5])

    def test_entries_have_doc_and_rule(self):
        d = S.load()
        self.assertTrue(d['entries'], '注册表为空')
        for e in d['entries']:
            self.assertTrue(os.path.isfile(os.path.join(BASE, e['doc'])),
                            '%s: doc 不存在 %s' % (e['id'], e['doc']))
            self.assertGreaterEqual(len(e['symptom']), 2)
            self.assertNotIn('symptom-index.md', e['doc'])

    def test_derived_page_in_sync(self):
        p = os.path.join(BASE, S.doc_path())
        self.assertTrue(os.path.isfile(p), '派生页不存在：%s' % S.doc_path())
        cur = io.open(p, encoding='utf-8').read()
        self.assertEqual(cur, S.render_doc(),
                         '派生页与 symptom_spec.json 漂移（跑 scripts/gen_symptom_doc.py）')

    def test_symptoms_verbatim_in_page(self):
        page = S.render_doc()
        for e in S.load()['entries']:
            for s in e['symptom']:
                self.assertIn(s, page, '症状原话没进派生页（检索锚点丢了）：%s' % s)

    def test_missing_spec_raises(self):
        """注册表缺失必须抛错（不静默返回空 → 否则检索会安静地少一整个域）。"""
        tmp = tempfile.mkdtemp(prefix='mcp_sym_')
        old = S.SPEC
        try:
            S.SPEC = os.path.join(tmp, 'nope.json')
            with self.assertRaises(RuntimeError):
                S.load()
        finally:
            S.SPEC = old
            U.cleanup(tmp)


if __name__ == '__main__':
    unittest.main()
