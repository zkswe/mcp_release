# -*- coding: utf-8 -*-
"""json2img 颜色语义契约（2026-10-05 修：只有 -1 是不填充）。

真源两处（互相一致，本用例只钉实现与它们一致）：
  · `ui_tools/ui_schema.json#valueRules.colorZero`：`0` = **不透明黑**；透明写 `-1`；
  · `ui_tools/json2img.py` 文件头「颜色约定」：`-1` = 不填充；`0` = 不透明黑；**其它按 0xRRGGBB**。

修前缺陷（实测）：实现是 `if v < 0` → 所有负数都不画；`backgroundColor: -16777216`
（= int32 补码的 0xFF000000 = 不透明黑）**底色整块丢失**。本文件把这条语义钉死：
  · 自证：把判据改回 `v < 0` → `test_negative_colors_are_not_unset` 必须变红。
"""
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (BASE, os.path.join(BASE, 'ui_tools')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import json2img as J                                        # noqa: E402


class TestColorSemantics(unittest.TestCase):

    def test_unset_is_only_minus_one(self):
        """不填充标记只有 -1 / 0xFFFFFFFF（其余一律是真颜色）。"""
        self.assertIsNone(J.color_rgba(None))
        self.assertIsNone(J.color_rgba(-1))
        self.assertIsNone(J.color_rgba(0xFFFFFFFF))

    def test_zero_is_opaque_black(self):
        """`0` = 不透明黑（valueRules.colorZero）——**不是**"未设置"。"""
        self.assertEqual(J.color_rgba(0), (0, 0, 0, 255))

    def test_negative_colors_are_not_unset(self):
        """其它负数 = int32 补码的 0xAARRGGBB → 按 RGB 画（修前这里返回 None）。"""
        self.assertEqual(J.color_rgba(-16777216), (0, 0, 0, 255), '0xFF000000 = 不透明黑')
        self.assertEqual(J.color_rgba(0xFF000000), (0, 0, 0, 255))
        self.assertEqual(J.color_rgba(-65536), (255, 0, 0, 255), '0xFFFF0000 = 红')

    def test_positive_rgb_unchanged(self):
        self.assertEqual(J.color_rgba(0xFFFFFF), (255, 255, 255, 255))
        self.assertEqual(J.color_rgba(0x123456), (0x12, 0x34, 0x56, 255))
        self.assertEqual(J.color_rgba(16711680), (255, 0, 0, 255))

    def test_alpha_argument_applies(self):
        self.assertEqual(J.color_rgba(0x010203, alpha=128), (1, 2, 3, 128))

    def test_garbage_is_not_unset_but_none(self):
        """非数值：返回 None（与 -1 不填充同形）——调用方按"不画"处理，不抛。"""
        self.assertIsNone(J.color_rgba('nonsense'))

    def test_renderer_version_bumped_for_this_change(self):
        """改渲染行为必须 bump 版本（基线绑定它，见 test_json2img_determinism）。"""
        self.assertGreaterEqual(J.__version__, '0.1.1')


if __name__ == '__main__':
    unittest.main()
