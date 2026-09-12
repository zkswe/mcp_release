# -*- coding: utf-8 -*-
"""平台解析契约（v0.27.41 起）：三个命名空间收进 platforms.py，能力按真实条件判定。

为什么要有：pause-touch 那类 bug 的共性是「按代理信号（状态）判定，而不是按真实条件判定」。
平台这块的翻版是——能力按平台**名字符串白名单**拦，而不是看模板/工具链/bin_tools
到底有没有；外加平台真相散成三份（platforms.PLATFORMS / package_tools.PLATFORM_ALIAS /
test_tools.SUPPORTED_PLATFORMS），于是出现「同一个平台名，包查询认、建工程不认」：
  - package_catalog.json 里 16 个平台键，platforms.py 原本只认 6 个规范名；
  - f136emmc（49 包）、z261（60 包）、z235x/h500s/a33nor/z6s 被判成「未知平台」。

契约（改 platforms.py 后必须仍然成立）：
  1. 包生态键 ↔ 规范名双向可解析，且 F135 的包键是 f136（不是同名小写）；
  2. 已经是真实包键的输入必须保真（emmc/stdcxx 各有自己的包集，不能被抹平）；
  3. 仅包生态平台 = 真实平台 + 明确「无模板/工具链」，不是「未知平台」；
  4. package_catalog.json 的每个平台键都必须能被解析（不允许无主平台名）；
  5. 副本必须是引用（对象身份），不是再抄一份。
"""
import io
import json
import os
import unittest

import _util as U
import platforms as pl


def _catalog():
    p = os.path.join(U.BASE, 'package_catalog.json')
    if not os.path.isfile(p):
        return {}
    return json.load(io.open(p, encoding='utf-8'))


class TestPlatformNamespaces(unittest.TestCase):
    def test_supported_is_buildable_only(self):
        """supported() = 可建工程；仅包生态平台不得混进来。"""
        for n in pl.supported():
            self.assertIn(n, pl.PLATFORMS)
        for n in pl.PACKAGE_ONLY:
            self.assertNotIn(n, pl.supported())

    def test_package_key_mapping(self):
        """规范名 → 包生态主键（F135 -> f136 是硬要求，别退化成同名小写）。"""
        self.assertEqual(pl.package_key('F135'), 'f136')
        self.assertEqual(pl.package_key('F133'), 'f133')
        self.assertEqual(pl.package_key('V85X'), 'v85x')
        self.assertEqual(pl.package_key('Z21'), 'z21')

    def test_package_key_accepts_aliases_and_keeps_real_keys(self):
        """别名能归一；已经是真实包键的输入保真。"""
        self.assertEqual(pl.package_key('F133EMMC'), 'f133emmc')
        self.assertEqual(pl.package_key('T113STDCXX'), 't113stdcxx')
        self.assertEqual(pl.package_key('f136emmc'), 'f136emmc')
        # 历史写法不对应真实包键 → 必须先归一到 v85x，否则查空
        self.assertEqual(pl.package_key('v853'), 'v85x')
        self.assertEqual(pl.package_key('V553'), 'v85x')

    def test_validate_accepts_package_variants_of_buildable_platforms(self):
        self.assertEqual(pl.validate('f136emmc'), 'F135')
        self.assertEqual(pl.validate('F133EMMC'), 'F133')
        self.assertEqual(pl.validate('T113EMMC'), 'T113')
        self.assertEqual(pl.validate('v85xemmc'), 'V85X')
        self.assertEqual(pl.validate('v853'), 'V85X')

    def test_package_only_is_real_platform_not_unknown(self):
        """仅包生态平台：resolve 认它是真实平台，validate 拒绝但说清「缺模板」。"""
        for name in sorted(pl.PACKAGE_ONLY):
            r = pl.resolve(name)
            self.assertIsNotNone(r, name)
            self.assertTrue(r['packageOnly'])
            self.assertFalse(r['buildable'])
            self.assertTrue(r['known'])
            with self.assertRaises(ValueError) as cm:
                pl.validate(name)
            self.assertIn('模板', str(cm.exception))

    def test_unknown_platform_message_lists_supported(self):
        with self.assertRaises(ValueError) as cm:
            pl.validate('NOT_A_PLATFORM')
        msg = str(cm.exception)
        for n in pl.supported():
            self.assertIn(n, msg)

    def test_resolve_buildable_carries_dirs(self):
        r = pl.resolve('v85xemmc')
        self.assertEqual(r['canonical'], 'V85X')
        self.assertTrue(r['buildable'])
        self.assertEqual(r['binTool'], 'v85x')
        self.assertTrue(os.path.isdir(os.path.join(U.BASE, 'templates', r['template'])))

    def test_resolve_garbage_is_none(self):
        self.assertIsNone(pl.resolve('NOT_A_PLATFORM'))
        self.assertIsNone(pl.resolve(''))


class TestPackageEcosystemCoverage(unittest.TestCase):
    def test_every_catalog_key_resolvable(self):
        cat = _catalog()
        if not cat:
            self.skipTest('package_catalog.json 不在本机（分发包里才有）')
        unresolved = sorted(k for k in cat if not pl.resolve(k))
        self.assertEqual(unresolved, [], '包生态平台名无主：%s' % unresolved)

    def test_package_keys_covers_catalog(self):
        cat = _catalog()
        if not cat:
            self.skipTest('package_catalog.json 不在本机')
        missing = sorted(set(cat) - set(pl.package_keys()))
        self.assertEqual(missing, [], 'platforms.package_keys() 未登记：%s' % missing)


class TestSingleSourceOfTruth(unittest.TestCase):
    def test_package_tools_platform_alias_is_a_reference(self):
        """package_tools 的平台别名表必须是 platforms.PACKAGE_ALIASES 本体，不是副本。"""
        import package_tools as pk
        self.assertIs(getattr(pk, 'PLATFORM_ALIAS', None), pl.PACKAGE_ALIASES)

    def test_test_tools_supported_platforms_derived(self):
        import test_tools as tt
        self.assertEqual(tuple(tt.SUPPORTED_PLATFORMS),
                         tuple(p.lower() for p in pl.supported()))

    def test_no_literal_platform_table_outside_platforms(self):
        """源码里不许再出现**字面量**平台表（推导式从 platforms.py 派生是合法的）。"""
        import re
        kw = ('PLATFORMS', 'SUPPORTED_PLATFORMS', 'PLATFORM_ALIAS', 'PLATFORM_ALIASES',
              'PACKAGE_ALIASES', 'PACKAGE_KEYS')
        lit = re.compile(r'^\s*(?:%s)\s*=\s*[\[({]' % '|'.join(kw))
        names = set(pl.PLATFORMS) | set(pl.PACKAGE_ONLY) | set(pl.package_keys()) \
            | set(pl.PACKAGE_ALIASES)
        quoted = ["'%s'" % n for n in names] + ['"%s"' % n for n in names]
        hits = []
        for fn in sorted(os.listdir(U.BASE)):
            if not fn.endswith('.py') or fn == 'platforms.py':
                continue
            with io.open(os.path.join(U.BASE, fn), encoding='utf-8', errors='replace') as fh:
                lines = fh.read().splitlines()
            for i, line in enumerate(lines, 1):
                if not lit.match(line):
                    continue
                if ' for ' in line:
                    continue                       # 推导式：从 platforms.py 派生
                blk = '\n'.join(lines[i - 1:i + 15])
                if any(q in blk for q in quoted):
                    hits.append('%s:%d' % (fn, i))
        self.assertEqual(hits, [], '又抄了平台表：%s' % hits)


class TestToolsNowAgreeOnRealPlatforms(unittest.TestCase):
    """回归本体：同一平台名，包查询与建工程必须给出**一致且真实**的判定。"""

    def test_package_query_uses_real_keys(self):
        import package_tools as pk
        cat = _catalog()
        if not cat:
            self.skipTest('package_catalog.json 不在本机')
        # f136emmc / z261 原本会被当成「不认识」的键，现在必须查到
        for p, k in (('F135', 'f136'), ('f136emmc', 'f136emmc'), ('z261', 'z261')):
            self.assertEqual(pk._norm_platform(p), k, p)

    def test_create_project_rejects_package_only_with_reason(self):
        import tempfile
        tmp = tempfile.mkdtemp(prefix='mcp_test_platonly_')
        try:
            r = U.jcall('flythings_create_project',
                        {'project_root': tmp, 'platform': 'z6s', 'resolution': '480x272'})
            self.assertFalse(r['ok'])
            blob = json.dumps(r, ensure_ascii=False)
            self.assertIn('模板', blob)                 # 必须说清是缺模板
            for n in pl.supported():
                self.assertIn(n, blob)                  # 并给出可建工程清单
        finally:
            U.cleanup(tmp)

    def test_hardware_info_distinguishes_not_registered(self):
        """真实平台但硬件库没登记 → 专用错误码，不能说成「未知平台」。"""
        r = U.jcall('flythings_hardware_info', {'model': '', 'platform': 'z261'})
        blob = json.dumps(r, ensure_ascii=False)
        self.assertNotIn('BAD_PLATFORM', blob)
        self.assertIn('z261', blob.lower())


if __name__ == '__main__':
    unittest.main(verbosity=2)
