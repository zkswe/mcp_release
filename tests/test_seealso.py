# -*- coding: utf-8 -*-
"""契约：op → 知识「去哪找」（seeAlso）覆盖率与注入。

为什么要有（2026-09-30：「12 做了」）：docstring 预算已顶格（12000/12000），
43 个 op 里原先只有 12 处 docstring 指到知识文档 → AI 选到工具后还得自己二次检索。
现在改为**返回体注入 seeAlso**（不占 docstring 预算），由 op_seealso.json 驱动：每个 op 要么有 seeAlso、要么显式登记 none + 理由（scripts/gen_seealso.py --check 进闸门）。
"""
import json
import os
import subprocess
import sys
import unittest

import _util as U


class TestSeeAlsoTable(unittest.TestCase):
    def test_gate_passes(self):
        """覆盖度闸门：OP_NAMES 全覆盖 + seeAlso 路径都存在。"""
        base = U.SRC_DIR if hasattr(U, 'SRC_DIR') else None
        root = base or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        rc = subprocess.run([sys.executable, os.path.join(root, 'scripts', 'gen_seealso.py'), '--check'],
                            cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(rc.returncode, 0, rc.stdout.decode('utf-8', 'replace')[-400:])

    def test_paths_are_repo_relative_knowledge(self):
        import kb_tools  # noqa: F401
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data = json.load(open(os.path.join(root, 'op_seealso.json'), encoding='utf-8'))
        for op, ent in (data.get('ops') or {}).items():
            for r in (ent.get('seeAlso') or []):
                self.assertTrue(r.startswith('knowledge/'),
                                '%s: seeAlso 必须指向仓库内 knowledge/（随包分发）→ %s' % (op, r))


class TestSeeAlsoInjection(unittest.TestCase):
    def test_op_with_seealso_carries_it(self):
        r = U.jcall('flythings_list_packages', {})
        self.assertTrue(r['ok'], r)
        self.assertIn('seeAlso', r, '有 seeAlso 登记的 op 必须在返回体里带上')
        self.assertTrue(any('dependency-package-docs.md' in x for x in r['seeAlso']), r['seeAlso'])

    def test_none_op_has_no_seealso(self):
        r = U.jcall('flythings_get_version', {'compact': True})
        self.assertTrue(r['ok'], r)
        self.assertNotIn('seeAlso', r, '登记为 none 的 op 不应注入 seeAlso')

    def test_injection_is_idempotent(self):
        import kb_tools
        raw = kb_tools.flythings_list_packages()
        once = json.loads(kb_tools.normalize_result('flythings_list_packages', raw))
        twice = json.loads(kb_tools.normalize_result('flythings_list_packages', once))
        self.assertEqual(once.get('seeAlso'), twice.get('seeAlso'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
