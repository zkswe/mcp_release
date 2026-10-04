# -*- coding: utf-8 -*-
"""设计先行软闸门契约（v0.27.101 / 需求方口径 A）。

为什么要有：用户提「新项目/新需求」却没给设计流程与界面时，AI 必须先走原型设计、界面设计，
再建工程。硬约束在意图闸门（tools/flythings_intent_gate，见其 test.mjs）；MCP 侧这一层只做
**软闸门**：建工程 / 编译部署时若工程目录内找不到设计产物，就在返回体附 warnings 指引——
**只提示，不改 success 语义、不阻断**（这是本文件要钉住的边界）。

用例分三组：
  A 检测口径：design/ 目录、*.html、*.preview.html 算设计产物；空工程不算
  B op 集成：create_project / build_ui_flow 的返回值带/不带该 warning，且 success 不变
  C 文档可检索性：create_project / get_project_spec 的 docstring 必须点出「先出设计稿」，
且 docstring 预算（单 op ≤900 / 全体 ≤12000）不被撑破
"""
import ast
import io
import json
import os
import unittest
from unittest import mock

import _util as U

import kb_tools
import project_tools as pt

HINT_KEY = '未检测到设计确认稿'


class TestDesignArtifactDetection(unittest.TestCase):
    """A：检测口径（只读、零副作用）。"""

    def setUp(self):
        self.tmp = U.project()

    def tearDown(self):
        U.cleanup(self.tmp)

    def test_empty_project_has_no_design(self):
        self.assertFalse(kb_tools._has_design_artifacts(self.tmp))

    def test_html_counts(self):
        U.write(os.path.join(self.tmp, 'wireframe.html'), '<div class="screen"></div>')
        self.assertTrue(kb_tools._has_design_artifacts(self.tmp))

    def test_preview_html_counts(self):
        U.write(os.path.join(self.tmp, 'ui', 'main.preview.html'), '<html></html>')
        self.assertTrue(kb_tools._has_design_artifacts(self.tmp))

    def test_design_dir_counts_without_files(self):
        os.makedirs(os.path.join(self.tmp, 'design', 'v2'), exist_ok=True)
        self.assertTrue(kb_tools._has_design_artifacts(self.tmp))

    def test_missing_dir_is_not_a_warning_site(self):
        """目录还不存在（工具自己会报错）→ 不提示，避免叠一层噪音。"""
        self.assertTrue(kb_tools._has_design_artifacts(os.path.join(self.tmp, 'nope')))

    def test_build_output_ignored(self):
        """构建产物目录（.fun/Release）不算设计产物。"""
        U.write(os.path.join(self.tmp, '.fun', 'z21', 'Release', 'x.html'), 'x')
        self.assertFalse(kb_tools._has_design_artifacts(self.tmp))

    def test_build_output_ignored_fsc(self):
        """同上，但**新一代产物目录** `.fsc/`（09-28 起 fun 的产物家）。

        漏跳 `.fsc` 等于对新工具链工程完全没跳构建产物 → `.fsc/**` 里的 html 会被当成
        设计产物 → 静默抑制设计先行提示（2026-10-03 定位）。
        """
        U.write(os.path.join(self.tmp, '.fsc', 'z21', 'Release', 'x.html'), 'x')
        self.assertFalse(kb_tools._has_design_artifacts(self.tmp))


class TestSoftGateOnOps(unittest.TestCase):
    """B：op 集成——只加 warnings，不改语义。"""

    def setUp(self):
        self.tmp = U.project()

    def tearDown(self):
        U.cleanup(self.tmp)

    def _create(self, **kw):
        return U.jcall('flythings_create_project',
                       dict({'project_root': self.tmp, 'platform': 'Z21',
                             'resolution': '800x480'}, **kw))

    def test_create_project_warns_without_design(self):
        with mock.patch.object(pt, 'flythings_create_project',
                               return_value={'success': True, 'projectRoot': self.tmp}):
            r = self._create()
        self.assertTrue(r['ok'], r)
        self.assertTrue(any(HINT_KEY in w for w in r['warnings']), r['warnings'])
        self.assertIn('prototype-flow', ' '.join(r['warnings']))

    def test_create_project_silent_with_design(self):
        U.write(os.path.join(self.tmp, 'wireframe.html'), '<div class="screen"></div>')
        with mock.patch.object(pt, 'flythings_create_project',
                               return_value={'success': True, 'projectRoot': self.tmp}):
            r = self._create()
        self.assertTrue(r['ok'], r)
        self.assertEqual([w for w in r['warnings'] if HINT_KEY in w], [], r['warnings'])

    def test_create_project_failure_not_noised(self):
        """失败路径（如未知平台）不加这个提示：失败原因才是要看的。"""
        r = U.jcall('flythings_create_project',
                    {'project_root': self.tmp, 'platform': 'not_a_platform',
                     'resolution': '800x480'})
        self.assertFalse(r['ok'], r)
        self.assertEqual([w for w in r.get('warnings', []) if HINT_KEY in w], [],
                         r.get('warnings'))

    def test_build_ui_flow_warns_without_design(self):
        with mock.patch.object(pt, 'flythings_build_ui_flow',
                               return_value={'success': True, 'steps': []}):
            r = U.jcall('flythings_build_ui_flow',
                        {'project_root': self.tmp, 'with_launch': False})
        self.assertTrue(r['ok'], r)
        self.assertTrue(any(HINT_KEY in w for w in r['warnings']), r['warnings'])

    def test_build_ui_flow_silent_with_design(self):
        U.write(os.path.join(self.tmp, 'design', 'home.html'), '<div class="screen"></div>')
        with mock.patch.object(pt, 'flythings_build_ui_flow',
                               return_value={'success': True, 'steps': []}):
            r = U.jcall('flythings_build_ui_flow',
                        {'project_root': self.tmp, 'with_launch': False})
        self.assertEqual([w for w in r['warnings'] if HINT_KEY in w], [], r['warnings'])

    def test_warning_does_not_change_success_or_other_keys(self):
        """只加 warnings：success/业务键逐字段不变。"""
        payload = {'success': True, 'projectRoot': self.tmp, 'platform': 'Z21',
                   'notes': ['a']}
        with mock.patch.object(pt, 'flythings_create_project',
                               return_value=dict(payload)):
            r = self._create()
        for k, v in payload.items():
            self.assertEqual(r[k], v, '键 %s 被改动' % k)
        self.assertTrue(r['warnings'])


class TestDocRetrievability(unittest.TestCase):
    """C：docstring 要点 + 预算（docstring 每次会话都进上下文）。"""

    def _src(self):
        return io.open(os.path.join(U.BASE, 'kb_tools.py'), encoding='utf-8').read()

    def test_docstrings_point_to_design_first(self):
        tree = ast.parse(self._src())
        docs = {n.name: (ast.get_docstring(n) or '') for n in tree.body
                if isinstance(n, ast.FunctionDef)}
        self.assertIn('先出设计稿', docs['flythings_create_project'])
        self.assertIn('prototype-flow', docs['flythings_create_project'])
        self.assertIn('先出设计稿', docs['flythings_get_project_spec'])

    def test_docstring_budget(self):
        tree = ast.parse(self._src())
        sizes = [(len(ast.get_docstring(n) or ''), n.name) for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name.startswith('flythings_')
                 and n.name != 'flythings_kb']
        over = [(s, n) for s, n in sizes if s > 900]
        self.assertEqual(over, [], '单 op docstring 超 900 字：%s' % over)
        self.assertLessEqual(sum(s for s, _ in sizes), 12000,
                             'docstring 总预算超 12000 字')

    def test_knowledge_doc_has_design_first_terms(self):
        """可检索性：prototype-flow 头部必须有新需求/原型设计等检索词 + 硬口径。"""
        p = os.path.join(U.BASE, 'knowledge', 'devflow', 'prototype-flow.md')
        head = io.open(p, encoding='utf-8').read()[:1800]
        for kw in ('检索词', '新需求', '原型设计', '界面设计', '线框图', '确认稿',
                   '智能家居', 'MQTT', '情景联动'):
            self.assertIn(kw, head, '头部缺检索词 %s' % kw)
        self.assertIn('没给', head)
        self.assertIn('create_project', head)

    def test_manifest_carries_stage(self):
        """分组数据来源：tools_manifest.json 的每个 op 都要有 stage，且意图闸门 catalog 同步。"""
        ops = U.manifest()['ops']
        self.assertTrue(all(o.get('stage') in ('design', 'build', 'other') for o in ops),
                        [(o['op'], o.get('stage')) for o in ops if o.get('stage') not in
                         ('design', 'build', 'other')])
        gate = os.path.join(os.path.dirname(U.BASE), 'flythings_intent_gate', 'catalog.json')
        if os.path.isfile(gate):
            cats = json.load(io.open(gate, encoding='utf-8'))['ops']
            self.assertEqual({o['op']: o['stage'] for o in cats},
                             {o['op']: o['stage'] for o in ops},
                             'catalog.json 的 stage 与 tools_manifest.json 不同步')


if __name__ == '__main__':
    unittest.main()
