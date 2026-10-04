# -*- coding: utf-8 -*-
"""hermetic 夹具门禁的契约用例（`scripts/check_consistency.py::stage_test_hermetic`）。

背景（2026-10-04 实测）：`tests/test_ui_schema.py` 的两个 4b 用例读 `temp/abtest_a|b`，
而仓库根 `temp/` 在 `.gitignore` 里 —— **fresh clone 上必挂**（同步后实跑 failures=3 里的 2 条）。
所以加了一条门禁：契约用例只许引用**仓内、已入库**的路径。

这类门禁最怕两件事，用例各钉一条：
  ① **空转**（规则写错，什么都没扫到却报绿）→ 用合成样本断言"该抓的抓到了"；
  ② **假红**（把测试里故意的假值当违规）→ 断言 `C:/fake/adb.exe`、`/tmp/busybox` 这类**不报**。
"""
import importlib.util
import os
import sys
import unittest

import _util as U

BASE = U.BASE


def _load_cc():
    """按路径加载门禁脚本（它不是包成员）。"""
    path = os.path.join(BASE, 'scripts', 'check_consistency.py')
    spec = importlib.util.spec_from_file_location('cc_for_test', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CC = _load_cc()


class TestHermeticPaths(unittest.TestCase):
    def test_real_tests_dir_is_clean(self):
        """本仓 tests/ 下不得有引用 gitignore 区（temp/ 等）的字面量。"""
        bad = []
        tdir = os.path.join(BASE, 'tests')
        for root, dirs, files in os.walk(tdir):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for fn in sorted(files):
                if not fn.endswith('.py'):
                    continue
                p = os.path.join(root, fn)
                rel = os.path.relpath(p, BASE).replace(os.sep, '/')
                for ln, frag, kind in CC._test_hermetic_hits(p):
                    bad.append('%s:%d [%s] %s' % (rel, ln, kind, frag))
        self.assertEqual(bad, [], '用例引用了 gitignore 区/仓外路径：%s' % bad[:5])

    def test_scanner_flags_repo_temp_fixture(self):
        """合成样本：夹具写 `temp/xxx` 时必须被抓（防门禁空转）。"""
        import tempfile
        tmp = tempfile.mkdtemp(prefix='mcp_hermetic_')
        try:
            p = os.path.join(tmp, 'fake_case.py')
            with open(p, 'w', encoding='utf-8') as f:
                f.write("import os\nFIX = 'temp/abtest_a'\n")
            hits = CC._test_hermetic_hits(p)
            self.assertTrue(hits, '`temp/...` 夹具没被抓到')
            self.assertEqual(hits[0][2], 'repo-temp')
        finally:
            U.cleanup(tmp)

    def test_fake_input_paths_are_not_flagged(self):
        """测试里**故意不存在**的假值不许假红（它们是断言素材，不是夹具）。"""
        import tempfile
        tmp = tempfile.mkdtemp(prefix='mcp_hermetic_')
        try:
            p = os.path.join(tmp, 'fake_case2.py')
            with open(p, 'w', encoding='utf-8') as f:
                f.write("FAKE = ['C:/fake/adb.exe', '/tmp/busybox', 'D:/nope.json']\n")
            self.assertEqual(CC._test_hermetic_hits(p), [])
        finally:
            U.cleanup(tmp)

    def test_scanner_survives_other_drive_path(self):
        """扫描目标在**另一个盘**时不许崩（Windows 实测：relpath 抛 ValueError）。

        2026-10-04 实测：用例用 `tempfile` 把合成样本建在 C:，而仓库在 D:，
        `_test_hermetic_hits` 里的 `os.path.relpath(path, BASE)` 直接抛
        `ValueError: path is on mount 'C:', start on mount 'D:'` —— 两条用例因此 ERROR。
        """
        import tempfile
        tmp = tempfile.mkdtemp(prefix='mcp_hermetic_')
        try:
            p = os.path.join(tmp, 'fake_case3.py')
            with open(p, 'w', encoding='utf-8') as f:
                f.write("X = 1\n")
            self.assertEqual(CC._test_hermetic_hits(p), [])
        finally:
            U.cleanup(tmp)


class TestDualCopyCompare(unittest.TestCase):
    """`sync_ui_tools.compare` 判「内容一致」而不是「字节一致」。

    2026-10-04 实测的假红：同一份提交在两个 `git worktree` 里落盘换行可以不同
    （本机 `core.autocrlf=true`，仓库又没有 `.gitattributes`）：主树 LF、另一棵 CRLF
    —— 按原始字节比哈希就把「同一份提交」判成**双份漂移**。
    """

    def _load(self):
        import importlib.util
        path = os.path.join(BASE, 'scripts', 'sync_ui_tools.py')
        spec = importlib.util.spec_from_file_location('sync_ui_for_test', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_line_endings_are_not_drift(self):
        mod = self._load()
        self.assertEqual(mod._norm(b'a\r\nb\r\n'), mod._norm(b'a\nb\n'),
                         'CRLF 与 LF 必须归一成同一份内容')
        self.assertNotEqual(mod._norm(b'a\nb\n'), mod._norm(b'a\nc\n'),
                            '归一化不得把真实内容差异也抹掉')

    def test_binary_is_byte_compared(self):
        mod = self._load()
        png = b'\x89PNG\r\n\x1a\n\x00\x00'
        self.assertEqual(mod._norm(png), png, '二进制必须原样比（含 NUL 则不归一）')


if __name__ == '__main__':
    unittest.main()