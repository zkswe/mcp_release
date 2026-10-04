# -*- coding: utf-8 -*-
"""离线守卫契约（tests/_util.py 的 `_install_adb_guard`）。

为什么单独钉一个用例文件：守卫是「契约用例必须离线」这条契约的**执行器**，
执行器自己没被钉住的话，下一个人一句 `adb_tools._run = 原实现` 就把它绕过去了 ——
于是又回到 2026-10-03 那次实测的现场：全套用例从"秒级"变成 >900s，发布闸门自己超时。

本文件钉三件事：
  ① adb 的唯一子进程出口默认被拦（语义 = 本机没 adb），且拦下次数可观测；
  ② `ui_tools/device_screenshot.py` 的 adb **执行**走 `adb_tools`（不许自带第二份 subprocess）；
  ③ `U.allow_subprocess()` 能显式开口（真需要工具链的用例才有出口）。
"""
import unittest

import _util as U

import adb_tools as at

# 一个**必然不存在**的可执行路径：用来观察"被拦"vs"被放行"，而不碰任何真设备。
_NO_SUCH_BIN = 'C:/definitely/not/a/real/adb_xyz.exe'


class TestOfflineGuard(unittest.TestCase):

    def test_adb_run_blocked_by_default(self):
        """默认：adb 调用被守卫拦下（rc=1 + 明确标记），且计数递增。"""
        before = U.adb_blocked_count()
        rc, out, err = at._run([_NO_SUCH_BIN, 'version'])
        self.assertEqual(rc, 1)
        self.assertIn('[offline-guard]', err,
                      'adb 唯一出口没被守卫拦住 —— 用例会偷偷去连真机')
        self.assertEqual(U.adb_blocked_count(), before + 1)

    def test_screenshot_module_routes_through_adb_tools(self):
        """截图模块的 adb 执行必须走单一入口（否则离线守卫漏一个洞）。"""
        import device_screenshot as ds          # _util 已把 ui_tools/ 加进 sys.path
        before = U.adb_blocked_count()
        ds._run([_NO_SUCH_BIN, 'devices'])
        self.assertEqual(U.adb_blocked_count(), before + 1,
                         'ui_tools/device_screenshot._run 绕过了 adb_tools（第二份 subprocess）')

    def test_allow_subprocess_opens_gate(self):
        """显式放行后走真实实现（用不存在的路径，立即失败，不接触设备）。"""
        before = U.adb_blocked_count()
        with U.allow_subprocess():
            rc, _out, err = at._run([_NO_SUCH_BIN, 'version'])
        self.assertNotIn('[offline-guard]', err)
        self.assertEqual(rc, 1)
        self.assertEqual(U.adb_blocked_count(), before, '放行期间不该计入拦截数')

    def test_first_site_is_recorded(self):
        """第一次被拦的调用点要留痕（下次漏 mock 时能一眼看到是谁）。"""
        self.assertGreater(U.adb_blocked_count(), 0)
        self.assertTrue(U.adb_first_site(), '未记录首个被拦调用点')
        self.assertRegex(U.adb_first_site(), r'\.py:\d+$')


if __name__ == '__main__':
    unittest.main(verbosity=2)
