# -*- coding: utf-8 -*-
"""域⑩「开发流程」注册表（flow_spec.json）的用例。

钉住的是**结构本身**，不是文案：
  · 两条正交轴各自完整（场景 5 / 动作 5），且 kind 与派生物对应（skillName / promptName）
  · 两条轴**共用步骤原子**（否则又变回三份副本）
  · 铁律**只在 invariants 里一份**（各流程只引用、不重写）
  · prompts 由注册表派生 —— 签名参数必须与注册表 inputs 一致（FastMCP 靠签名生成 schema）
  · 派生页与真源一致；步骤引用的 op 真实存在
"""
import ast
import inspect
import io
import os
import subprocess
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import flow_loader as F                                  # noqa: E402

MCP_EXTRAS = os.path.join(BASE, 'mcp_extras.py')


class TestRegistry(unittest.TestCase):

    def test_self_check(self):
        errs = F.validate(include_doc=True)
        self.assertEqual(errs, [], '流程注册表自检未过：\n  - %s' % '\n  - '.join(errs))

    def test_two_axes_are_complete(self):
        sc = F.flows_of('scenario')
        ac = F.flows_of('action')
        self.assertEqual(len(sc), 5, '场景轴应有 5 条：%s' % sorted(sc))
        self.assertEqual(len(ac), 5, '动作轴应有 5 条：%s' % sorted(ac))
        for fid, f in sc.items():
            self.assertTrue(f.get('skillName'), '%s 缺 skillName' % fid)
            self.assertFalse(f.get('promptName'), '%s 不该有 promptName' % fid)
        for fid, f in ac.items():
            self.assertTrue(f.get('promptName'), '%s 缺 promptName' % fid)
            self.assertFalse(f.get('skillName'), '%s 不该有 skillName' % fid)

    def test_axes_share_step_atoms(self):
        """两条轴必须**共用**步骤 —— 否则这次归集白做（还是各写一份）。"""
        by_scenario, by_action = {}, {}
        for fid, f in F.flows().items():
            bucket = by_scenario if f['kind'] == 'scenario' else by_action
            for it in f['steps']:
                bucket.setdefault(it if isinstance(it, str) else it['id'], []).append(fid)
        shared = set(by_scenario) & set(by_action)
        self.assertGreaterEqual(len(shared), 8,
                                '场景与动作共用的步骤太少（%d）：%s' % (len(shared), sorted(shared)))
        # 且真有跨场景复用（同一段步骤被多条场景引用），否则「原子」是名义上的
        reused = [s for s, fs in by_scenario.items() if len(fs) >= 3]
        self.assertGreaterEqual(len(reused), 5,
                                '被 ≥3 条场景复用的步骤太少：%s' % reused)

    def test_invariants_are_single_source(self):
        """铁律只在 invariants 里写一份；流程只引用 id（原来「图片尺寸==控件盒」在 3 个 skill 各写一遍）。"""
        inv = F.invariants()
        self.assertIn('image-size-eq-box', inv)
        for fid, f in F.flows().items():
            for iid in (f.get('invariants') or []):
                self.assertIn(iid, inv, '%s 引用了未登记的不变量 %s' % (fid, iid))
        # 规则正文不许出现在流程的其它字段里（那意味着又一处分叉）
        rule = inv['image-size-eq-box']['rule']
        for fid, f in F.flows().items():
            self.assertNotIn(rule, str(f.get('desc') or ''),
                             '%s 的 desc 里又写了一遍不变量正文' % fid)

    def test_step_numbering_restores_original(self):
        """编号还原：「第 0 步」开头、「第 2 步 A / B」二选一都要能表达。"""
        a = [i['label'] for i in F.flow_items('idea-to-app')]
        self.assertEqual(a[0], '第 0 步')
        self.assertEqual(a[1], '第 1 步')
        b = [i['label'] for i in F.flow_items('resolution-adapt')]
        self.assertEqual(b[0], '第 1 步')
        self.assertEqual(b[1], '第 2 步 A')
        self.assertEqual(b[2], '第 2 步 B')
        self.assertEqual(b[3], '第 3 步')

    def test_steps_op_exists_in_contract(self):
        """步骤引用的 op 必须在 op 契约里 —— op 改名后流程会静默跑偏。"""
        import op_spec_loader as osl
        known = set(osl.registered())
        for sid, s in F.steps().items():
            if s.get('op'):
                self.assertIn(s['op'], known, '步骤 %s 引用的 op 未登记：%s' % (sid, s['op']))

    def test_gated_steps_have_iron_rule(self):
        """闸门必须落在 op 契约的常驻面上 —— 否则只活在流程页里，AI 不拉契约就丢。"""
        self.assertEqual(F.cross_check(), [])


class TestPromptDerivation(unittest.TestCase):

    def _prompt_signatures(self):
        """从源码 AST 取 5 个 prompt 函数的参数名（它们在 register() 内，运行时拿不到）。"""
        with io.open(MCP_EXTRAS, encoding='utf-8') as fh:
            src = fh.read()
        tree = ast.parse(src)
        out = {}
        for n in ast.walk(tree):
            if not isinstance(n, ast.FunctionDef):
                continue
            is_prompt, pname = False, None
            for d in n.decorator_list:
                if isinstance(d, ast.Call) and getattr(d.func, 'attr', '') == 'prompt':
                    is_prompt = True
                    for kw in d.keywords:
                        if kw.arg == 'name' and isinstance(kw.value, ast.Constant):
                            pname = kw.value.value
            if is_prompt and pname:
                out[pname] = [a.arg for a in n.args.args]
        return out

    def test_signature_matches_registry_inputs(self):
        sigs = self._prompt_signatures()
        self.assertEqual(len(sigs), 5, '应注册 5 个 prompt，实为 %s' % sorted(sigs))
        for fid, f in F.flows_of('action').items():
            pn = f['promptName']
            self.assertIn(pn, sigs, '注册表里的 %s 没有对应的 prompt 函数' % pn)
            self.assertEqual(sigs[pn], list(f['inputs']),
                             '%s 的函数签名 %s 与注册表 inputs %s 不一致'
                             % (pn, sigs[pn], f['inputs']))
        for pn in sigs:
            self.assertIn(pn, [f['promptName'] for f in F.flows_of('action').values()],
                          'prompt %s 在注册表里没有对应流程' % pn)

    def test_no_handwritten_prompt_bodies(self):
        """防回退：正文不许再在本文件里手写一份。"""
        import mcp_extras as me
        self.assertFalse(hasattr(me, 'PROMPTS'), 'mcp_extras 又出现了手写的 PROMPTS 常量')
        with io.open(MCP_EXTRAS, encoding='utf-8') as fh:
            src = fh.read()
        self.assertNotIn('PROMPTS = {', src)

    def test_render_matches_registry(self):
        import mcp_extras as me
        for fid, f in F.flows_of('action').items():
            spec = me._prompt_spec(fid)
            self.assertEqual(spec['title'], f['title'])
            self.assertEqual(spec['description'], f['desc'])
            self.assertEqual(spec['args'], list(f['inputs']))
            self.assertEqual(spec['body'], F.render_prompt(fid)['body'])

    def test_render_fills_placeholders(self):
        import mcp_extras as me
        vals = {k: 'X-%s' % k for k in F.flow('new-project')['inputs']}
        body = me._render('new-project', **vals)
        self.assertIn('X-platform', body)
        self.assertNotIn('{platform}', body)

    def test_render_leaves_prompt_when_missing(self):
        """没传的参数要留「先问用户」的提示，而不是静默留个 {x}。"""
        import mcp_extras as me
        body = me._render('new-project', platform='Z20')
        self.assertIn('先问用户', body)
        self.assertNotIn('{resolution}', body)


class TestCallParamsMatchSignature(unittest.TestCase):
    """流程文档里写的 op 调用，参数名必须与真实签名一致。

    真实踩到的：`fui_pack` 的真实签名是 `json_path`，而流程页写的是 `project_root=`
    —— AI 照文档调用必吃 BAD_PARAMS，而文档看起来"很权威"。
    """

    def test_no_wrong_param_names_in_docs(self):
        self.assertEqual(F.cross_check(), [])

    def test_checker_itself_works(self):
        """防『扫不到东西所以永远绿』：用已知的错例喂进去，必须报出来。"""
        sigs = F._signatures()
        self.assertTrue(sigs, '取不到 kb_tools 的函数签名 —— 该检查会静默失效')
        self.assertIn('flythings_fui_pack', sigs)
        errs = []
        F._check_calls('`flythings_fui_pack(project_root="D:/p")`', 'X', errs, set(sigs), sigs)
        self.assertEqual(len(errs), 1, '错的参数名没被抓出来')
        self.assertIn('json_path', errs[0])

    def test_checker_accepts_correct_call(self):
        sigs = F._signatures()
        errs = []
        F._check_calls('`flythings_fui_pack(json_path="D:/p/ui/main.json")`', 'X',
                       errs, set(sigs), sigs)
        self.assertEqual(errs, [])


class TestSkillDerivation(unittest.TestCase):

    def test_render_has_frontmatter_and_iron_rules(self):
        for fid, f in F.flows_of('scenario').items():
            md = F.render_skill(fid)
            self.assertTrue(md.startswith('---\nname: %s\n' % f['skillName']),
                            '%s 的 front-matter 起头不对：%r' % (fid, md[:60]))
            self.assertIn('agent_created: true', md)
            self.assertIn('## 何时用', md)
            self.assertIn('## 铁律速查', md)
            for iid in (f.get('invariants') or []):
                self.assertIn(F.invariant(iid)['rule'], md,
                              '%s 的铁律段漏了 %s' % (fid, iid))
            for item in F.flow_items(fid):
                self.assertIn(item['title'], md, '%s 漏了步骤 %s' % (fid, item['id']))

    def test_gates_are_visible_in_skill(self):
        """闸门必须在派生出的 skill 正文里可见（带 ⚠️），否则读 skill 的 AI 也不知道要停。"""
        md = F.render_skill('idea-to-app')
        self.assertIn('⚠️ **需用户确认**', md)
        self.assertIn('⚠️ **不可逆操作**', md)


class TestDerivedDoc(unittest.TestCase):

    def test_page_matches_registry(self):
        p = subprocess.run([sys.executable, os.path.join(BASE, 'scripts', 'gen_flow_doc.py'),
                            '--check'], capture_output=True, cwd=BASE, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout.decode('utf-8', 'replace'))

    def test_page_is_derived_and_lists_both_axes(self):
        md = io.open(os.path.join(BASE, F.doc_path()), encoding='utf-8').read()
        self.assertIn('origin: derived', md)
        self.assertIn('## 1. 场景轴', md)
        self.assertIn('## 2. 动作轴', md)
        self.assertIn('## 3. 步骤库', md)
        self.assertIn('## 4. 跨流程铁律', md)
        for fid, f in F.flows().items():
            self.assertIn(f['title'], md, '派生页漏了流程 %s' % fid)


if __name__ == '__main__':
    unittest.main()
