# -*- coding: utf-8 -*-
"""旧框架（json + Eclipse）创建工程时，**工程名改写**的回归契约。

背景（为什么钉这条）：MCP 只承担**老框架 json + Eclipse** 这套结构方案
（`fun create` 出来的 fv 新框架不在服务范围内——其格式与细节我们没有资料，
开放出去只会让别的 AI 按猜的写，问题更多）。

而"拷模板建工程"这条路上，`.project` / `.cproject` 里的工程名**必须**跟着改成新工程名，
历史上有两个真坑：

  ① 只按**目录名**替换是不够的 —— 模板文件里的真实工程名常与目录名不一致
     （`HelloWord_T113` 目录里写的是 `HelloWord_T113Nor`）→ 会剩下 `Nor` 尾巴；
  ② `.project` 的 `<buildSpec>` 里装的是 **Eclipse Builder ID**，不是工程名；
     一旦被当旧名替换掉，IDE 编译**没有任何输出**（CDT Build Console 空白）。
"""
import io
import os
import re
import sys
import unittest

import _util as U

sys.path.insert(0, U.BASE)
import project_tools as P  # noqa: E402

BUILDER_IDS = ('com.flythings.managedbuild.core.builder',
               'org.eclipse.cdt.managedbuilder.core.genmakebuilder',
               'org.eclipse.cdt.managedbuilder.core.ScannerConfigBuilder')
TPL_PLATFORMS = [p for p in ('V85X', 'T113', 'Z21', 'F133', 'Z20', 'Z235X', 'F135')]


def _tpl_names(tpl):
    """模板文件里**真实**的工程名（用实现侧的同一函数取，避免测试自己另写一套）。"""
    return P._project_names_in_files(tpl)


class TestCreateProjectNaming(unittest.TestCase):
    def setUp(self):
        self.tmp = U.project()

    def tearDown(self):
        U.cleanup(self.tmp)

    def _create(self, plat, app_name):
        root = os.path.join(self.tmp, app_name or ('dir_%s' % plat))
        r = P.flythings_create_project(root, platform=plat, resolution='800x480',
                                       app_name=app_name, with_cli=False)
        self.assertTrue(r.get('success'), '创建失败：%s' % r.get('error'))
        return root, r

    def test_project_name_and_builders_for_every_template(self):
        """7 个模板逐个：新名写进 `.project`/`.cproject`、旧名不残留、Builder ID 保住。"""
        tested = 0
        supported = set(P._platforms.supported())
        for plat in TPL_PLATFORMS:
            if plat not in supported:
                continue                      # 显式跳过不支持项（不吞异常：异常要暴露）
            tpl = P._template_dir(P._platforms.validate(plat))
            if not tpl or not os.path.isdir(tpl):
                continue
            old_names = _tpl_names(tpl) | {os.path.basename(tpl)}
            new = 'NewName%s' % plat
            with self.subTest(platform=plat):
                root, _ = self._create(plat, new)
                pj_p, cj_p = os.path.join(root, '.project'), os.path.join(root, '.cproject')
                self.assertTrue(os.path.isfile(pj_p), '模板没带 .project？')
                pj = io.open(pj_p, encoding='utf-8', errors='replace').read()
                # ① 新工程名必须出现在 <projectDescription><name> 里
                m = re.search(r'<projectDescription>\s*<name>\s*([^<]+?)\s*</name>', pj)
                self.assertIsNotNone(m, '.project 结构不对（取不到工程名）')
                self.assertEqual(m.group(1).strip(), new,
                                 '.project 的工程名没改成新名（实得 %r）' % m.group(1))
                # ② 旧名不许残留（这是 T113 那种"带尾巴"的判据）
                #    ⚠️ 只在**工程名语义的位置**判：buildSpec 里的 Builder ID 与旧名无关
                head = pj.split('<buildSpec>')[0]
                for old in old_names:
                    self.assertNotIn(old, head,
                                     '.project 里还残留模板旧名 %r（只按目录名替换会这样）' % old)
                # ③ Builder ID 必须保住
                for b in BUILDER_IDS:
                    self.assertIn(b, pj, 'Builder ID 丢了：%s（IDE 会编译无输出）' % b)
                if os.path.isfile(cj_p):
                    cj = io.open(cj_p, encoding='utf-8', errors='replace').read()
                    for old in old_names:
                        self.assertNotIn(old, cj, '.cproject 里还残留模板旧名 %r' % old)
                    self.assertIn(new, cj, '.cproject 里没写上新工程名')
                tested += 1
        if not tested:
            self.skipTest('本仓没有可用的 HelloWord 模板')

    def test_app_name_overrides_directory_name(self):
        """`app_name` 优先于目录名（目录叫什么，工程名由 app_name 说了算）。"""
        root = os.path.join(self.tmp, 'SomeDirName')
        r = P.flythings_create_project(root, platform='V85X', resolution='800x480',
                                       app_name='RealProjectName', with_cli=False)
        self.assertTrue(r.get('success'), r.get('error'))
        pj = io.open(os.path.join(root, '.project'), encoding='utf-8', errors='replace').read()
        m = re.search(r'<projectDescription>\s*<name>\s*([^<]+?)\s*</name>', pj)
        self.assertEqual(m.group(1).strip(), 'RealProjectName')

    def test_app_name_defaults_to_directory_name(self):
        root = os.path.join(self.tmp, 'DirNameProject')
        r = P.flythings_create_project(root, platform='V85X', resolution='800x480',
                                       app_name='', with_cli=False)
        self.assertTrue(r.get('success'), r.get('error'))
        pj = io.open(os.path.join(root, '.project'), encoding='utf-8', errors='replace').read()
        m = re.search(r'<projectDescription>\s*<name>\s*([^<]+?)\s*</name>', pj)
        self.assertEqual(m.group(1).strip(), 'DirNameProject')


class TestNoFvSurface(unittest.TestCase):
    """**反向**契约：MCP 不暴露 fv 新框架这条路（需求方 2026-10-05 口径）。

    为什么要有这条：`fun create` 能生成 fv 新框架，但其格式与细节**我们没有资料**，
    开放出去会让别的 AI 按猜的写 → 问题更多。所以：
      · MCP 的创建工具**没有** format/template/with_build 这类 fv 开关；
      · 仓里**没有** fv 主题的知识页（免得被检索命中后照着实现）；
      · 旧框架路径（json + Eclipse）的行为不受影响。
    """

    def test_create_tool_has_no_fv_switch(self):
        import inspect
        sig = inspect.signature(P.flythings_create_project)
        for bad in ('format', 'with_build', 'template'):
            self.assertNotIn(bad, sig.parameters,
                             '创建工具冒出了 %r 参数（那是 fv 新框架的路，不在服务范围）' % bad)

    def test_no_fv_exposed_in_mcp_wrapper(self):
        import kb_tools
        import inspect
        sig = inspect.signature(kb_tools.flythings_create_project)
        for bad in ('format', 'with_build', 'template'):
            self.assertNotIn(bad, sig.parameters, 'MCP 包装层暴露了 %r' % bad)

    def test_no_fv_knowledge_page(self):
        root = os.path.join(U.BASE, 'knowledge')
        hits = []
        for r, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in ('_reports', '_logs', 'inbox')]
            for f in files:
                if f.endswith('.md') and 'fv' in f.lower():
                    hits.append(os.path.relpath(os.path.join(r, f), U.BASE))
        self.assertEqual(hits, [], '仓里出现了 fv 主题知识页（会被检索命中并照猜实现）：%s' % hits)

    def test_op_spec_has_no_fv_params(self):
        import json
        doc = json.loads(io.open(os.path.join(U.BASE, 'op_spec.json'), encoding='utf-8').read())
        spec = doc['ops']['flythings_create_project']
        names = [p['name'] for p in spec.get('params') or []]
        for bad in ('format', 'with_build', 'template'):
            self.assertNotIn(bad, names, 'op 规格里暴露了 %r' % bad)
        self.assertNotIn('fv', json.dumps(spec, ensure_ascii=False),
                         'op 规格里提到了 fv（不提供这条路就别提）')


if __name__ == '__main__':
    unittest.main()
