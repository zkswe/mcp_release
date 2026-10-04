# -*- coding: utf-8 -*-
"""视觉保真契约（`ui_schema.json.renderContract`）的结构性质与可获取性。

为什么单独钉一组（2026-10-05 用户口径「通过前期规格约定，禁止让设计迁就实现」）：

同一类视觉症状（锯齿 / 硬阶梯 / 发虚 / 变粗 / 扁 / 尺寸对不上）在 `VERSION_HISTORY.md` 里
**整改过 8 次**，其中 2026-09-27 的现场原话是「这个问题**以前 MCP 应该修复过的**」。
根因不是"哪次修错了"，而是**保真口径从未集中成为规格**：它散在知识页铁律、生成器实现注释、
用例判据、模板 README 四处，于是"何时允许整像素描边带"这条**边界**只有读过四个地方的人才知道。

所以本文件钉三件事：
  ① 规格**存在且完整**（每条都有 id/scope/rule/consequence —— consequence 是"判错出什么缺陷"，
     AI 靠它从症状反查该守哪条）；
  ② 规格**能被拿到**（不是躺在注册表里没人读：`flythings_ui_schema` 的返回体必须带它）；
  ③ **禁止的两类手段**有机器判据（`⛔EXCUSE` ⑧ / `⛔TWEAK` ⑨），且当前是 0 命中。
"""
import io
import json
import os
import subprocess
import sys
import unittest

import _util as U

sys.path.insert(0, U.BASE)
BASE = U.BASE

SPEC = os.path.join(BASE, 'ui_tools', 'ui_schema.json')


def _reg():
    with io.open(SPEC, encoding='utf-8') as f:
        return json.load(f)


class TestRenderContractIntegrity(unittest.TestCase):
    """① 规格存在且每条都有 consequence（症状→该守哪条 的可反查性）。"""

    def test_contract_exists_and_rows_complete(self):
        rows = (_reg().get('renderContract') or {}).get('rows') or []
        self.assertTrue(rows, '缺 renderContract（视觉保真的唯一口径表）')
        ids = [r.get('id') for r in rows]
        self.assertEqual(len(ids), len(set(ids)), 'renderContract.id 不许重复')
        for r in rows:
            for k in ('id', 'scope', 'rule', 'consequence'):
                self.assertTrue(str(r.get(k) or '').strip(),
                                'renderContract 条目 %r 缺 %s' % (r.get('id'), k))

    def test_contract_covers_the_incident_classes(self):
        """8 次复发涉及的关键条目必须在册（少一条就等于那条还会复发）。

        只钉 id 的存在性，**不钉措辞** —— 措辞可以改，覆盖不能少。
        """
        ids = {r.get('id') for r in (_reg().get('renderContract') or {}).get('rows') or []}
        for need in ('pic-scale', 'progress-clip', 'thumb-size', 'alpha-compose',
                     'edge-aa', 'stroke-aa', 'nine-patch', 'rounding'):
            self.assertIn(need, ids, 'renderContract 缺条目 %s' % need)

    def test_authority_states_the_two_forbidden_means(self):
        """规格自己的 authority 必须把两类禁止手段写明（否则读表的人不知道边界）。"""
        auth = str((_reg().get('renderContract') or {}).get('authority') or '')
        self.assertIn('DESIGN_SPEC', auth, 'authority 要指到设计源规范')
        self.assertTrue('禁止' in auth, 'authority 要写明禁止事项')


class TestRenderContractReachable(unittest.TestCase):
    """② 规格必须**能被拿到**：躺在注册表里没人读 = 等于没立。"""

    def _call(self, **kw):
        import kb_tools as K
        return json.loads(K.flythings_ui_schema(**kw))

    def test_list_response_carries_contract(self):
        r = self._call()
        rows = r.get('renderContract') or []
        self.assertEqual(len(rows), len((_reg().get('renderContract') or {}).get('rows') or []),
                         '控件清单响应必须带全部保真条目')
        for row in rows:
            self.assertTrue(row.get('rule') and row.get('consequence'),
                            '清单响应里的条目至少要带 rule + consequence（设计前要看的就这两项）')

    def test_control_response_carries_contract_with_scope(self):
        r = self._call(control_type='seekbar')
        rows = r.get('renderContract') or []
        self.assertTrue(rows, '按控件查询也要带保真契约（"哪几条管这个控件"）')
        self.assertIn('scope', rows[0], '按控件查询应带 scope（全字段）')

    def test_op_contract_points_to_the_spec(self):
        """op 契约要指到真源 —— 否则 AI 只看到字段表、不知道还有保真契约这回事。"""
        import op_spec_loader as osl
        c = osl.render_contract('flythings_ui_schema')
        self.assertIn('renderContract', c, 'op 契约必须指向 renderContract 真源')


class TestForbiddenMeansAudited(unittest.TestCase):
    """③ 两类禁止手段要有**机器判据**且当前 0 命中（DESIGN_SPEC 第 1.2 条）。"""

    def _audit(self):
        src = io.open(os.path.join(BASE, 'scripts', 'audit_design_spec.py'),
                      encoding='utf-8').read()
        return src

    def test_audit_knows_both_kinds(self):
        src = self._audit()
        self.assertIn('KIND8', src, '缺 ⑧ ⛔EXCUSE 判据')
        self.assertIn('KIND9', src, '缺 ⑨ ⛔TWEAK 判据')
        self.assertIn('EXCUSE_PHRASE', src)
        self.assertIn('GUARD_SYMBOLS', src)
        # 两条都要进 CHECKS_ALL，否则报告里不显示、--check 也不覆盖
        self.assertIn('(KIND8, None)', src, '⑧ 未进 CHECKS_ALL')
        self.assertIn('(KIND9, None)', src, '⑨ 未进 CHECKS_ALL')

    def test_audit_is_currently_clean(self):
        """当前 0 命中：规格立好的同时就把已有豁免话术清掉了（否则规则一进闸门就是红的）。"""
        p = subprocess.run([sys.executable,
                            os.path.join(BASE, 'scripts', 'audit_design_spec.py'), '--check'],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        self.assertEqual(p.returncode, 0, '审计不通过：\n%s\n%s'
                         % ((p.stdout or '')[-600:], (p.stderr or '')[-300:]))

    def test_design_spec_states_the_rule(self):
        """设计源规范必须有第 1.1（规格先行）与 1.2（两类禁止手段）两节。"""
        t = io.open(os.path.join(BASE, 'DESIGN_SPEC.md'), encoding='utf-8').read()
        self.assertIn('## 1.1 规格先行', t)
        self.assertIn('## 1.2 禁止的两类', t)
        self.assertIn('⛔EXCUSE', t)
        self.assertIn('⛔TWEAK', t)

    def test_guard_files_cite_the_spec(self):
        """⑨ 的判据要能持续成立：保真相关实现文件必须带着规格引用。"""
        for rel in ('ui_tools/gen_res.py', 'ui_tools/html2json.py',
                    'ui_tools/json2img.py', 'ui_tools/check_all.py'):
            t = io.open(os.path.join(BASE, rel.replace('/', os.sep)), encoding='utf-8').read()
            self.assertIn('renderContract', t,
                          '%s 改了保真实现却没引用规格（⛔TWEAK 的口子）' % rel)


class TestReviewRecordIsSeparate(unittest.TestCase):
    """④ 检讨记录与规范分开：复盘写进 `CONSOLIDATION_VISUAL.md`，**不进规范文本**。"""

    def test_review_doc_exists_and_is_marked_as_record(self):
        p = os.path.join(BASE, 'CONSOLIDATION_VISUAL.md')
        self.assertTrue(os.path.isfile(p), '缺复盘记录 CONSOLIDATION_VISUAL.md')
        t = io.open(p, encoding='utf-8').read()
        self.assertIn('不是规范', t, '复盘文档要显式声明自己不是规范')
        for k in ('8 次', '以前 MCP 应该修复过的'):
            self.assertIn(k, t, '复盘要留下复发次数与现场原话（这是判据的来源）')


if __name__ == '__main__':
    unittest.main()
