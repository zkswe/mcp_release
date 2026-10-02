# -*- coding: utf-8 -*-
"""工程骨架同步的契约（scripts/sync_project_skeleton.py）。

为什么要有它：骨架（`Main.cpp` + `src/uart/*`）在仓库里有 18 份副本，改一处要改 18 处。
同步器的价值是「唯一来源 + 副本 + 门禁」，所以用例要钉住三件事：
  ① **绝不碰业务与 IDE 生成目录**（`src/logic/*`、`src/activity/*`）—— 这是安全底线；
  ② 唯一来源自身不被当成副本（否则 --apply 会自我复制崩）；
  ③ 副本与唯一来源逐字节一致；不带骨架的工程被**报告出来**而不是静默跳过。
"""
import os
import subprocess
import sys
import unittest

import _util as U

BASE = U.BASE
SCRIPTS = os.path.join(BASE, 'scripts')
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import sync_project_skeleton as sps              # noqa: E402


class TestProjectSkeleton(unittest.TestCase):

    def test_01_唯一来源齐备(self):
        """① 骨架唯一来源在 templates 里，9 个文件都在。"""
        self.assertTrue(os.path.isdir(sps.CANON_DIR), sps.CANON_DIR)
        for rel in sps.SKELETON:
            with self.subTest(f=rel):
                self.assertTrue(os.path.isfile(os.path.join(sps.CANON_DIR, rel)),
                                '唯一来源缺 %s' % rel)

    def test_02_不碰业务与IDE生成目录(self):
        """② 安全底线：同步范围里不许出现逻辑代码与 IDE 生成目录。"""
        for rel in sps.SKELETON:
            self.assertNotIn('logic', rel, '骨架不该包含 src/logic：%s' % rel)
            self.assertNotIn('activity', rel, '骨架不该包含 src/activity（禁手改）：%s' % rel)
        self.assertIn('Main.cpp', sps.SKELETON)
        self.assertIn('uart/UartContext.cpp', sps.SKELETON)

    def test_03_唯一来源不被当副本(self):
        """③ is_canonical 判定：唯一来源自己不算副本（--apply 才不会自我复制）。"""
        self.assertTrue(sps.is_canonical(sps.CANON_DIR))
        self.assertFalse(sps.is_canonical(os.path.join(BASE, 'components', 'blend2d',
                                                       'example', 'src')))

    def test_04_当前无漂移(self):
        """④ 现状：副本与唯一来源一致（有漂移说明骨架改过没同步）。"""
        bad, _custom = sps.drift()
        self.assertEqual(bad, [], '骨架漂移：%s' % bad[:5])

    def test_05_覆盖度(self):
        """⑤ 覆盖到全部带骨架的工程（不静默漏），且自带骨架的工程被报出来。"""
        carried = [p for p in sps.projects() if p['carries']]
        self.assertGreaterEqual(len(carried), 15, '带骨架的工程数异常：%d' % len(carried))
        _bad, custom = sps.drift()
        self.assertTrue(custom, '应至少有一个「自带骨架」的工程被报告（而非静默跳过）')
        for name in custom:
            self.assertTrue(os.path.isdir(os.path.join(BASE, name)), name)

    def test_06_门禁口径可跑(self):
        """⑥ --check 退出码可用（门禁就靠它）。"""
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, 'sync_project_skeleton.py'),
                            '--check'], capture_output=True, cwd=BASE)
        out = (r.stdout + r.stderr).decode('utf-8', 'replace')
        self.assertEqual(r.returncode, 0, out[:200])
        self.assertIn('[PASS]', out)


if __name__ == '__main__':
    unittest.main()
