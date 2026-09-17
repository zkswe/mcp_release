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


class TestV85xFamilyAliases(unittest.TestCase):
    """V85x 芯片别名补齐（v0.27.87，钟工问「这几个你适配了吗」）。

    实测当时：✅ V853/V553/V552/V85X → V85X；❌ **V851 / V851S / V851S3 / V853S → None**
    （当未知平台），且 package_key() 会回 `v851s` 这种 catalog 里**不存在**的键 → 查包查空。
    本用例钉死：这 6 个芯片名（含大小写混写）全部 → V85X 平台 + `v85x` 包键，
    且 catalog 的 v85x/v85xemmc chips 已含这 5 个芯片（V851/V851S/V851S3/V853/V853S）。
    """

    FAMILY = ('V851', 'V851S', 'V851S3', 'V853S')
    FIVE = ('V851', 'V851S', 'V851S3', 'V853', 'V853S')

    def test_resolve_and_package_key(self):
        for name in self.FAMILY + ('V853', 'V553', 'V552', 'V85X'):
            for form in (name, name.lower(), name.upper(), name.title()):
                r = pl.resolve(form)
                self.assertIsNotNone(r, '%s 必须能 resolve（不能当未知平台）' % form)
                self.assertEqual(r['canonical'], 'V85X', form)
                self.assertTrue(r['buildable'], form)
                self.assertEqual(pl.package_key(form), 'v85x', form)

    def test_validate_accepts_chip_names(self):
        """建工程口径也认（validate 不再把它们判为未知平台 → 建工程不会误拒）。"""
        for form in ('V851', 'v851s', 'V851S3', 'V853S', 'V851S'):
            self.assertEqual(pl.validate(form), 'V85X', form)
            self.assertEqual(pl.template_dir_name(form), 'HelloWord_V85X', form)
            self.assertEqual(pl.bin_tool_dir(form), 'v85x', form)
            self.assertEqual(pl.arch(form), 'arm', form)

    def test_emmc_variant_still_keeps_its_own_key(self):
        """芯片名归一到 SPINOR 主键 `v85x`；显式 EMMC 变体仍保留 `v85xemmc`（保真）。"""
        self.assertEqual(pl.package_key('V851S'), 'v85x')
        self.assertEqual(pl.package_key('v85xemmc'), 'v85xemmc')
        self.assertEqual(pl.package_key('V85XEMMC'), 'v85xemmc')

    def test_chip_aliases_never_become_catalog_keys(self):
        """芯片名**不是**包键：不许把 v851s 当真实包键（那会让查包命中空目录）。"""
        for name in self.FAMILY:
            self.assertNotIn(name.lower(), pl.package_keys(), name)
            self.assertNotIn(name.lower(), pl.PACKAGE_KEY_ALIASES, name)
            self.assertEqual(pl.PACKAGE_INPUT_ALIASES[name.lower()], 'V85X')

    def test_package_catalog_chips_cover_family(self):
        """包目录 v85x / v85xemmc 的 chips 必须已含这 5 个芯片（包生态认得它们）。"""
        cat = _catalog()
        if not cat:
            self.skipTest('package_catalog.json 不在本机')
        for key in ('v85x', 'v85xemmc'):
            self.assertIn(key, cat, key)
            chips = cat[key].get('chips') or []
            for name in self.FIVE:
                self.assertIn(name, chips, '%s.chips 缺 %s' % (key, name))

    def test_hardware_catalog_chips_cover_family(self):
        """硬件库 V85X.chips 同样收齐 6 个主控，且芯片级登记在册（待确认的如实标 pending）。"""
        import hardware_tools as hw
        cat, _warn = hw.load(force=True)
        meta = (cat.get('platforms') or {}).get('V85X') or {}
        chips = meta.get('chips') or []
        for name in self.FIVE + ('V553',):
            self.assertIn(name, chips, 'hardware_catalog V85X.chips 缺 %s' % name)
        entries = meta.get('chipEntries') or {}
        self.assertTrue(entries, 'V85X 缺芯片级登记 chipEntries')
        for name in self.FIVE + ('V553',):
            self.assertIn(name, entries, 'chipEntries 缺 %s' % name)
            self.assertIn(entries[name].get('dataStatus'), ('complete', 'partial', 'pending'),
                          '%s 的 dataStatus 非法' % name)
        # 没有实测数据的两个：必须如实标 pending，不许臆造规格
        self.assertEqual(entries['V851S3']['dataStatus'], 'pending')
        self.assertEqual(entries['V853S']['dataStatus'], 'pending')
        self.assertIn('待确认', entries['V851S3']['note'])
        self.assertIn('待确认', entries['V853S']['note'])
        # 平台与包键的写死口径必须在库里（文档/工具会带出去）
        note = meta.get('chipsNote') or ''
        self.assertIn('V85X', note)
        self.assertIn('v85x', note)
        self.assertIn('v85xemmc', note)

    def test_hardware_info_exposes_chip_entries(self):
        """工具返回体里能拿到主控登记（AI/客户查 V85X 时看到「哪个芯片实测过」）。"""
        r = U.jcall('flythings_hardware_info', {'platform': 'V851S'})
        self.assertTrue(r.get('ok'), r)
        p85 = [p for p in r['platforms'] if p['platform'] == 'V85X']
        self.assertTrue(p85, r['platforms'])
        self.assertIn('V851S', p85[0]['chips'])
        self.assertEqual(p85[0]['chipEntries']['V851S']['dataStatus'], 'partial')
        self.assertIn('v85x', p85[0]['chipsNote'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
