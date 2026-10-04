# -*- coding: utf-8 -*-
"""契约用例运行器：带**逐用例看门狗**的 `unittest discover`。

为什么需要它（2026-10-03 实测）：
  `check_consistency.py --with-tests` 原来的守法是「给整个 unittest 进程一个墙钟超时」
  （先是 900s，改成 1800s 后**同机同代码**仍然一次 1036s 跑完、一次 >1800s 超时）。
  这说明：全套是**分钟级、且随机器负载大幅漂移**的真实离线工作，
  用**一个全局超时**去守它，会把「机器慢」误判成「挂死」—— 反过来也照样漏掉真挂死。

真正要抓的从来是**某一条用例挂住**（历史事故：mock 漏一条设备调用 → 真 adb 阻塞，全套 >900s）。
所以这里把守的对象换成**逐用例**的看门狗：

  · 每条用例起跑时重置计时；超过 `--per-test-timeout` 秒 → dump 全线程栈并**立即结束进程**（非 0 退出）。
    栈里会带 `tests/<文件>.py:<行> in <用例名>`，一眼看出是谁挂的。
  · 对整套**不设**内部墙钟上限（外层由发布闸门给一个很宽的上限兜底）。

用法：
    python scripts/run_tests.py                          # 默认逐用例 120s
    python scripts/run_tests.py --per-test-timeout 300    # 放宽单条
    python scripts/run_tests.py --per-test-timeout 0      # 关掉看门狗（等价于裸 unittest）
    python scripts/run_tests.py -p test_op_spec.py        # 只跑某个文件（等价 discover -p）
"""
import argparse
import faulthandler
import functools
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, 'tests'))


class WatchdogResult(unittest.TextTestResult):
    """在每条用例的边界重置看门狗 —— 于是超时 = 这一条挂住，而不是这一套太慢。"""

    def __init__(self, *a, per_test=120, **kw):
        super().__init__(*a, **kw)
        self.per_test = per_test

    def startTest(self, test):
        super().startTest(test)
        if self.per_test:
            faulthandler.cancel_dump_traceback_later()
            # exit=True：超时直接结束进程（比抛异常可靠 —— 挂住的线程唤不醒）
            faulthandler.dump_traceback_later(self.per_test, exit=True)

    def stopTest(self, test):
        if self.per_test:
            faulthandler.cancel_dump_traceback_later()
        super().stopTest(test)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--per-test-timeout', type=int, default=120,
                    help='单条用例上限（秒）；0 = 关闭看门狗。实测最贵的一条 ~11s，120s 很宽松')
    ap.add_argument('-p', '--pattern', default='test_*.py', help='用例文件匹配（discover -p）')
    a = ap.parse_args(argv)

    suite = unittest.TestLoader().discover(os.path.join(BASE, 'tests'), pattern=a.pattern)
    # ⚠️ TextTestRunner 不把自定义 kwarg 透传给 result 类（只按 (stream, descriptions, verbosity)
    # 构造），所以用 partial 把 per_test 绑进 resultclass。
    runner = unittest.TextTestRunner(
        verbosity=0,
        resultclass=functools.partial(WatchdogResult, per_test=a.per_test_timeout))
    res = runner.run(suite)
    return 0 if res.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
