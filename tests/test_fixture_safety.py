# -*- coding: utf-8 -*-
"""夹具安全：**用例里的删除只允许落在临时工程内**（需求方 2026-10-05 提醒后加的守卫）。

背景：用例为了造"缺文件"的场景会删夹具里的文件（例：`src/logic/<页面>Logic.cc` 用来验
"逻辑文件缺失要报错"）。这类删除一旦作用到**真工程**，就是把**历史业务代码删掉**、不可恢复。
所以删除收口到 `_util.rm_in_temp(path, rel)`：**先校验目录确实是 `mcp_test_*` 临时工程，
再删**；不像就当场 `ValueError`，绝不"先删再说"。

本文件钉三件事：
  ① 守卫的判据正确（认临时工程、拒真工程/相对路径/系统目录）；
  ② 仓内所有"删夹具文件"的调用都走它（没有漏网的裸 `os.remove(...logic...)`）；
  ③ 渲染器本身**只读** logic（它绝不写/删业务代码）。
"""
import io
import os
import re
import sys
import unittest

import _util as U

sys.path.insert(0, U.BASE)


class TestTempGuard(unittest.TestCase):
    """① 守卫判据：临时工程认得出、其它一律拒。"""

    def setUp(self):
        self.tmp = U.project()

    def tearDown(self):
        U.cleanup(self.tmp)

    def test_accepts_temp_project(self):
        self.assertTrue(U.is_temp_project(self.tmp), '自建临时工程应被认作临时工程')

    def test_rejects_real_repo_paths(self):
        for bad in (U.BASE, 'templates', 'templates/DemoControls_V85X', '.', '',
                    'C:/Windows', os.path.join(U.BASE, 'templates', 'DemoControls_V85X')):
            self.assertFalse(U.is_temp_project(bad), '不该把真工程当临时目录：%r' % bad)

    def test_rejects_sibling_dir_without_prefix(self):
        """仓外但**不在系统临时目录**下的一律拒；临时目录下的合法夹具要接受
        （判据只看"在不在 %TEMP% 下"，不看前缀 —— 实测存在 `stub_test_*` 等多个前缀）。"""
        import tempfile
        p = os.path.join(os.path.expanduser('~'), 'not_a_test_project')
        os.makedirs(p, exist_ok=True)
        try:
            self.assertFalse(U.is_temp_project(p),
                             '不在系统临时目录下的目录应被拒（%s）' % p)
        finally:
            os.rmdir(p)
        q = os.path.join(tempfile.gettempdir(), 'stub_test_demo')
        os.makedirs(q, exist_ok=True)
        try:
            self.assertTrue(U.is_temp_project(q),
                            '系统临时目录下的夹具应被接受（前缀不限）')
        finally:
            os.rmdir(q)

    def test_rm_in_temp_refuses_outside_and_does_not_delete(self):
        """对非临时目录：**必须报错且不动文件**（这是本守卫存在的唯一理由）。"""
        target = os.path.join(U.BASE, 'templates', 'DemoControls_V85X',
                              'src', 'logic', 'mainLogic.cc')
        self.assertTrue(os.path.isfile(target), '前提：真工程里有这个业务逻辑文件')
        before = os.stat(target).st_mtime, os.path.getsize(target)
        with self.assertRaises(ValueError):
            U.rm_in_temp(os.path.join(U.BASE, 'templates', 'DemoControls_V85X'),
                         os.path.join('src', 'logic', 'mainLogic.cc'))
        after = os.stat(target).st_mtime, os.path.getsize(target)
        self.assertEqual(before, after, '守卫报错后真工程的文件必须原样（mtime/大小都不许变）')
        self.assertTrue(os.path.isfile(target), '真工程的业务逻辑文件绝不能被删')

    def test_rm_in_temp_deletes_inside(self):
        lf = U.rm_in_temp_check if False else None      # noqa: F841  （占位，保持风格一致）
        os.makedirs(os.path.join(self.tmp, 'src', 'logic'), exist_ok=True)
        p = os.path.join(self.tmp, 'src', 'logic', 'mainLogic.cc')
        io.open(p, 'w', encoding='utf-8').write('// fixture\n')
        U.rm_in_temp(self.tmp, os.path.join('src', 'logic', 'mainLogic.cc'))
        self.assertFalse(os.path.isfile(p), '临时工程内应真删掉')

    def test_rm_in_temp_is_idempotent(self):
        """删不存在的文件不报错（用例会重复调用）。"""
        U.rm_in_temp(self.tmp, os.path.join('src', 'logic', 'nope.cc'))


class TestNoUnguardedFixtureDeletion(unittest.TestCase):
    """② 仓内**删除工程业务文件**（`src/logic/*` 等）必须走守卫。

    只钉这一类（而不是所有 `os.remove`）：删自己造的临时文件（png/json/scratch）是用例的常规操作，
    不属于"可能删掉历史业务代码"的风险面；**删 `src/logic/` 下的东西才是**。
    """

    def test_no_raw_remove_of_logic_files(self):
        """用 **AST** 找真实调用（跳过字符串/注释/文档 —— 否则本文件的反例说明会自己命中）。"""
        import ast
        bad = []
        names = ('remove', 'unlink', 'rmtree')
        for root, dirs, fs in os.walk(os.path.join(U.BASE, 'tests')):
            dirs[:] = [d for d in dirs if d not in ('__pycache__', 'fixtures')]
            for fn in fs:
                if not fn.endswith('.py'):
                    continue
                p = os.path.join(root, fn)
                rel = os.path.relpath(p, U.BASE).replace(os.sep, '/')
                if rel.endswith('_util.py'):
                    continue                      # 守卫自己的实现
                src = io.open(p, encoding='utf-8', errors='replace').read()
                try:
                    tree = ast.parse(src)
                except SyntaxError as e:
                    bad.append('%s 解析失败：%s' % (rel, e))
                    continue
                lines = src.splitlines()
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    fn_node = node.func
                    fname = getattr(fn_node, 'attr', None) or getattr(fn_node, 'id', None)
                    if fname not in names:
                        continue
                    seg = ast.get_source_segment(src, node) or ''
                    # 只看**这次调用本身**的源码片段里有没有 logic（不含周围的注释/文档）
                    if 'logic' in seg and 'rm_in_temp' not in seg:
                        bad.append('%s:%d  %s' % (rel, node.lineno,
                                                  lines[node.lineno - 1].strip()[:90]))
        self.assertEqual(bad, [], '删工程逻辑文件必须走守卫 U.rm_in_temp：\n  ' + '\n  '.join(bad))

    def test_logic_stub_deletion_goes_through_guard(self):
        t = io.open(os.path.join(U.BASE, 'tests', 'test_logic_stub.py'), encoding='utf-8').read()
        self.assertIn('U.rm_in_temp(', t, '缺文件场景的删除必须走守卫')
        self.assertNotIn("os.remove(os.path.join(r, 'src', 'logic'", t, '还有裸删除没换掉')

    def test_circlebar_fixture_deletion_goes_through_guard(self):
        t = io.open(os.path.join(U.BASE, 'tests', 'test_json2img_circlebar.py'),
                    encoding='utf-8').read()
        self.assertIn('U.rm_in_temp(', t, 'circlebar 用例的夹具删除必须走守卫')
        self.assertNotIn('os.remove(lf)', t, '还有裸删除没换掉')


class TestRendererIsReadOnly(unittest.TestCase):
    """③ 渲染器绝不写/删业务代码：`json2img.py` 里不许有对 logic 的写/删。"""

    def test_json2img_never_writes_or_deletes_logic(self):
        src = io.open(os.path.join(U.BASE, 'ui_tools', 'json2img.py'), encoding='utf-8').read()
        for pat in (r'os\.remove\([^)]*logic', r'os\.unlink\([^)]*logic',
                    r'open\([^)]*logic[^)]*[\'"]w', r'\.write\([^)]*logic'):
            self.assertIsNone(re.search(pat, src),
                              '渲染器里出现了对 logic 的写/删（必须只读）：%s' % pat)
        # 正面判据：读 logic 用的是不带 'w' 的 open
        self.assertIn("io.open(p, encoding='utf-8', errors='replace')", src,
                      'logic 应只以只读方式打开')

    def test_rendering_a_real_project_does_not_touch_its_logic(self):
        """端到端：渲染真工程的一页后，它的 logic 文件 mtime/大小不变（渲染是只读行为）。"""
        proj = os.path.join(U.BASE, 'templates', 'DemoControls_V85X')
        lf = os.path.join(proj, 'src', 'logic', 'canvasLogic.cc')
        if not os.path.isfile(lf):
            self.skipTest('本仓没有该模板工程')
        before = os.stat(lf).st_mtime_ns, os.path.getsize(lf)
        out = os.path.join(U.project(), 'canvas.png')
        import json2img as J
        J.render_one(proj, os.path.join(proj, 'ui', 'canvas.json'), out, verbose=False)
        after = os.stat(lf).st_mtime_ns, os.path.getsize(lf)
        self.assertEqual(before, after, '渲染动了业务逻辑文件（必须只读）')
        self.assertTrue(os.path.isfile(out), '渲染应产出 PNG')


if __name__ == '__main__':
    unittest.main()
