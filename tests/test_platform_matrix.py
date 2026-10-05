# -*- coding: utf-8 -*-
"""平台矩阵契约：platforms.py 是平台名/模板/bin_tools 的唯一事实来源。

为什么要有（检讨报告 §2.4）：默认平台/大小写/别名原先散在 6 处（12 处 'F133' vs
gen_ui_test 的 'z21'），外部用户照 README 走会踩空。
"""
import json
import os
import unittest

import _util as U
import platforms as pl


class TestPlatformMatrix(unittest.TestCase):
    def test_supported_list_nonempty_and_uppercase(self):
        names = pl.supported()
        self.assertTrue(names)
        for n in names:
            self.assertEqual(n, n.upper())

    def test_templates_and_bin_tools_exist(self):
        for name, meta in pl.PLATFORMS.items():
            tpl = os.path.join(U.BASE, 'templates', meta['template'])
            self.assertTrue(os.path.isdir(tpl), '%s 模板目录缺失: %s' % (name, tpl))
            bt = os.path.join(U.BASE, 'bin_tools', meta['binTool'])
            self.assertTrue(os.path.isdir(bt), '%s bin_tools 目录缺失: %s' % (name, bt))

    def test_aliases_normalize(self):
        self.assertEqual(pl.validate('z21'), 'Z21')
        self.assertEqual(pl.validate('f133emmc'), 'F133')
        self.assertEqual(pl.validate('T113EMMC'), 'T113')
        self.assertEqual(pl.validate('F136'), 'F135')
        self.assertIsNone(pl.normalize('nothing-like-a-platform'))

    def test_unknown_platform_raises_with_hint(self):
        with self.assertRaises(ValueError) as cm:
            pl.validate('NOT_A_PLATFORM')
        msg = str(cm.exception)
        for n in pl.supported():
            self.assertIn(n, msg)

    def test_default_platform_is_valid(self):
        self.assertIn(pl.DEFAULT_PLATFORM, pl.PLATFORMS)

    def test_create_project_rejects_unknown_platform(self):
        import tempfile
        tmp = tempfile.mkdtemp(prefix='mcp_test_plat_')
        try:
            r = U.jcall('flythings_create_project',
                        {'project_root': tmp, 'platform': 'NOPE', 'resolution': '480x272'})
            self.assertFalse(r['ok'])
            self.assertIn('NOPE', json.dumps(r, ensure_ascii=False))
            for n in pl.supported():                      # 报错要列全部支持项
                self.assertIn(n, json.dumps(r, ensure_ascii=False))
        finally:
            U.cleanup(tmp)


if __name__ == '__main__':
    unittest.main(verbosity=2)
