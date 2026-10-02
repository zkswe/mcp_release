# -*- coding: utf-8 -*-
"""op 契约注册表契约（op_spec.json + op_spec_loader.py + scripts/gen_op_docs.py）。

为什么要这一条：docstring 就是 MCP 工具 description，以前它同时承载「契约」和「叙述」，
于是被 12000 字符硬预算逼着手工逐字删；同一份契约还散落在 tools_manifest / gate_catalog /
op_seealso / knowledge 文档里人肉同步。改成注册表单一真源后，钉住这几件事：

  ① 注册表可加载，且 --strict 语义可用（未登记 op 能被列出来）
  ② 已登记 op 的 docstring == 注册表渲染结果（**手改 docstring 会立刻红**）
  ③ 首行 == summary（tools_manifest / gate_catalog 的 brief 同源，防止两边漂移）
  ④ 渲染预算：单条 ≤ perOpMax、全体 ≤ totalMax
  ⑤ 注册表自检：risk/category/stage 合法、params 有 name+desc、seeAlso/docRef 指向真实文件
  ⑥ 渲染确定性：同一 spec 渲染两次逐字节相同（否则门禁会假红）
  ⑦ 契约级断言保持：create_project 必须点出「先出设计稿」+「prototype-flow」
     （tests/test_design_first_gate.py 的检索性要求由派生链继续满足）
  ⑧ 端到端：走真实分发路径取 flythings_pack_upgrade 的 docstring，确认与注册表一致
"""
import ast
import io
import os
import sys
import unittest

import _util as U

BASE = U.BASE
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import op_spec_loader as osl                      # noqa: E402

KB = os.path.join(BASE, 'kb_tools.py')


def _source_docstrings():
    with io.open(KB, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    out = {}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if n.name == 'flythings_kb' or n.name.startswith('flythings_'):
                out[n.name] = ast.get_docstring(n) or ''
    return out


class TestOpSpecRegistry(unittest.TestCase):

    def test_registry_loads_and_declares_authority(self):
        reg = osl.load()
        self.assertTrue(str(reg.get('authority') or '').strip(),
                        '注册表必须声明 authority（唯一真源 + 消费方）')
        self.assertIn('budget', reg)
        self.assertTrue(osl.registered(), '注册表 ops 不能为空')

    def test_strict_lists_unregistered(self):
        """未登记的 op 必须能被列出来（迁移进度可见 + 迁移完可收紧）。"""
        import subprocess
        p = subprocess.run([sys.executable, os.path.join(BASE, 'scripts', 'gen_op_docs.py'),
                            '--check', '--strict'], capture_output=True, text=True)
        registered = set(osl.registered())
        docstrings = _source_docstrings()
        unregistered = [n for n in docstrings if n not in registered]
        if unregistered:
            self.assertEqual(p.returncode, 1, '迁移中：--strict 应因未登记 op 报失败')
            self.assertIn('未登记', p.stdout + p.stderr)
        else:
            self.assertEqual(p.returncode, 0, '全部登记后 --strict 应通过')

    def test_docstring_is_derived_from_registry(self):
        """已登记 op 的 docstring 必须等于注册表渲染结果——手改 docstring 立刻红。"""
        docstrings = _source_docstrings()
        for op in osl.registered():
            self.assertIn(op, docstrings, '%s 在 kb_tools.py 里找不到' % op)
            self.assertEqual(docstrings[op].strip(), osl.render(op),
                             '%s 的 docstring 与 op_spec.json 漂移；跑 '
                             'python scripts/gen_op_docs.py 重生成' % op)

    def test_first_line_equals_summary(self):
        """首行 == summary：tools_manifest / gate_catalog 的 brief 都取首行，必须同源。"""
        docstrings = _source_docstrings()
        for op in osl.registered():
            first = (docstrings[op].strip().splitlines() or [''])[0]
            self.assertEqual(first, osl.summary(op).strip(),
                             '%s 的 docstring 首行 != summary（brief 会漂移）' % op)

    def test_render_is_deterministic(self):
        for op in osl.registered():
            self.assertEqual(osl.render(op), osl.render(op))

    def test_budget(self):
        rep = osl.budget_report()
        self.assertEqual(rep['over'], [], '单条渲染超 %d 字符：%s'
                         % (rep['perOpMax'], rep['over']))
        self.assertLessEqual(rep['total'], rep['totalMax'],
                             '已登记 op 渲染合计超 %d' % rep['totalMax'])

    def test_registry_selfcheck(self):
        self.assertEqual(osl.validate(), [], 'op_spec.json 自检不通过')

    def test_seealso_and_docref_exist(self):
        for op in osl.registered():
            for path in osl.seealso(op):
                self.assertTrue(os.path.isfile(os.path.join(BASE, path)),
                                '%s seeAlso 指向不存在的文件：%s' % (op, path))
            d = osl.doc_ref(op)
            if d:
                self.assertTrue(os.path.isfile(os.path.join(BASE, d)),
                                '%s docRef 指向不存在的文件：%s' % (op, d))

    def test_create_project_keeps_design_first_contract(self):
        """检索性契约不能因为改成派生就丢：设计先行口径必须还在。"""
        doc = osl.render('flythings_create_project')
        for kw in ('先出设计稿', 'prototype-flow'):
            self.assertIn(kw, doc)

    def test_derived_doc_reaches_dispatcher(self):
        """端到端：分发器给出的 brief 就是注册表 summary（同一份派生链）。"""
        import mcp_server
        brief = mcp_server._brief(mcp_server.OPS['flythings_pack_upgrade'])
        self.assertEqual(brief, osl.brief('flythings_pack_upgrade'))

    def test_unknown_op_raises(self):
        with self.assertRaises(osl.OpSpecError):
            osl.spec('flythings_not_an_op')


if __name__ == '__main__':
    unittest.main()
