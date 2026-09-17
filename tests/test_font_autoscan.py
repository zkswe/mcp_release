# -*- coding: utf-8 -*-
"""字体自动扫描 + 缺中文自动投递契约（v0.27.86，钟工 2026-09-17「现在做」）。

为什么要有（事故背景）：
  `components/fonts/scripts/device_font_check.py` 2026-09-13 就实现了「扫设备字体 + 缺中文投递
  思源黑体」，但**没有任何 op 包它、也没接进 build/deploy** → 等于没做：客户撞到「界面汉字全是
  方块」时才知道要手动跑脚本。v0.27.86 把它接成**自动动作**。

钉住五件事：
  ① **默认自动投递**：判定缺中文（设备最大字体 < 200 KB / 设备没字体 / 工程侧也没字库）→
     `flythings_build_ui_flow` 默认就把 `common` 档投进工程 `font/` 并在返回体写清**写入了哪些文件**；
  ② **开关可关**：`font_check='off'` → **不产生任何字体 step**、不写盘、不碰 adb；
  ③ **无设备退化**：不连设备时退化为工程侧 self-scan（prefs 的 `font` 指向在不在 `font/` 里 +
     `font/` 有没有可用字体），字段必须写清「未连设备，仅工程侧检查」，且**绝不擅自探设备**；
  ④ **体检查询只报不投**：`flythings_check_project_deps` 默认只给结论 + 一键修复命令（保持只读体检；
     `font_apply=True` 才真投递），字段 `missingChinese` / `maxFontBytes` / `advisedTier` /
     `delivered` / `deviceFonts` 稳定；
  ⑤ **判定规则单一来源**：阈值/三版清单/投递动作全部来自 `device_font_check`（不复制第二套规则）。
"""
import json
import os
import shutil
import unittest
from unittest import mock

import _util as U

import font_tools as ft          # _util 已把 MCP 根目录加进 sys.path
import package_tools as pkgtools
import project_tools as pt

# 设备侧假数据（TEST-NET-1 文档地址，非真机 IP）
DEV = {'serial': '192.0.2.9:5555', 'model': 'Zkswe_SSD21X_SPINOR',
       'platform': 'Z21', 'modelConfidence': 'confirmed', 'state': 'device'}
PREFS_TXT = '{"uart"\\:"/dev/ttyS0","baud"\\:"115200","font"\\:"%s"}'


def _dfc():
    mod, err = ft.device_font_check()
    assert mod is not None, err
    return mod


def _mk(root, prefs_font='', fonts=(), props='projectName=unittest\n'):
    """最小工程骨架：ui/main.ftu + src + package.properties（可选 prefs / font/ 假字体）。"""
    os.makedirs(os.path.join(root, 'ui'), exist_ok=True)
    os.makedirs(os.path.join(root, 'src'), exist_ok=True)
    open(os.path.join(root, 'ui', 'main.ftu'), 'wb').write(b'ZKSR')
    open(os.path.join(root, 'src', 'Main.cpp'), 'w').write('int main() { return 0; }\n')
    if props is not None:
        U.write(os.path.join(root, 'package.properties'), props)
    if prefs_font:
        U.write(os.path.join(root, '.settings', 'com.zksw.flythings.easyui.prefs'),
                PREFS_TXT % prefs_font)
    if fonts:
        os.makedirs(os.path.join(root, 'font'), exist_ok=True)
        for name, kb in fonts:
            open(os.path.join(root, 'font', name), 'wb').write(b'\0' * (int(kb) * 1024))
    return root


def _no_adb_probe(testcase):
    """断言「不碰 adb」：探测被调用即失败。"""
    p = mock.patch.object(ft._adb, 'probe_devices',
                          side_effect=AssertionError('无设备分支不该探测 adb'))
    p.start()
    testcase.addCleanup(p.stop)


def _fake_device(collect_fonts):
    """把 adb 探测 + device_font_check.collect 都替换掉（不碰真机，但仍在跑真实判定/解析链）。"""
    patches = [
        mock.patch.object(ft._adb, 'probe_devices',
                          lambda *a, **k: {'ok': True, 'online': [DEV], 'offline': [],
                                           'adb': 'adb', 'adbSource': 'unittest', 'count': 1}),
        mock.patch.object(ft._adb, 'ensure_busybox', lambda *a, **k: ''),
        mock.patch.object(_dfc(), 'collect',
                          lambda adb, serial, use_busybox:
                              {'props': {'ro.product.model': DEV['model']},
                               'fonts': list(collect_fonts), 'raw_dirs': {}}),
    ]
    return patches


class TestCheckProjectDepsFontCheck(unittest.TestCase):
    """④ 体检字段：check_project_deps 的 fontCheck / fontIssues。"""

    def setUp(self):
        self.tmp = U.project()

    def tearDown(self):
        U.cleanup(self.tmp)

    def test_no_device_falls_back_to_project_scan(self):
        """③ 无设备 → 工程侧 self-scan；字段写清「未连设备，仅工程侧检查」，且不探 adb。"""
        _mk(self.tmp)
        _no_adb_probe(self)
        r = U.jcall('flythings_check_project_deps', {'project_root': self.tmp})
        fc = r['fontCheck']
        self.assertTrue(fc['enabled'], fc)
        self.assertEqual(fc['mode'], 'project')
        self.assertIn('未连设备，仅工程侧检查', fc['note'])
        self.assertEqual(fc['deviceFonts'], [])
        self.assertTrue(fc['missingChinese'], fc)
        self.assertEqual(fc['maxFontBytes'], 0)
        self.assertEqual(fc['advisedTier'], 'common')
        self.assertEqual(fc['verdict'], 'project_no_font')
        # 默认只报不投（只读体检不许偷偷写盘）
        self.assertFalse(fc['delivered'].get('applied'))
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, 'font')))
        issues = [i for i in r['fontIssues'] if i['kind'] == 'font']
        self.assertTrue(issues, r['fontIssues'])
        self.assertIn('工程侧检查（未连设备）', issues[0]['msg'])
        self.assertIn('device_font_check.py', issues[0]['hint'])

    def test_prefs_points_to_missing_font_warns(self):
        """① prefs 的 font 指向 `font/xxx.ttf` 但文件缺失 → 必须报「引用是断的」+ 判定需投递。"""
        _mk(self.tmp, prefs_font='/res/font/ghost.ttf')
        _no_adb_probe(self)
        r = U.jcall('flythings_check_project_deps', {'project_root': self.tmp})
        fc = r['fontCheck']
        self.assertEqual(fc['verdict'], 'prefs_font_missing')
        self.assertTrue(fc['missingChinese'])
        self.assertEqual(fc['prefs']['key'], '/res/font/ghost.ttf')
        self.assertFalse(fc['prefs']['existsInProject'])
        self.assertTrue(any('字体引用是断的' in w for w in fc['warnings']), fc['warnings'])
        self.assertTrue(fc.get('repair'), fc)

    def test_prefs_font_present_is_not_flagged(self):
        """正例：prefs 指向的字确实在 `font/` 里 + 体积够 → 不报（不制造误报）。"""
        _mk(self.tmp, prefs_font='/res/font/my.ttf', fonts=[('my.ttf', 1536)])
        _no_adb_probe(self)
        r = U.jcall('flythings_check_project_deps', {'project_root': self.tmp})
        fc = r['fontCheck']
        self.assertEqual(fc['verdict'], 'project_has_cjk')
        self.assertFalse(fc['missingChinese'])
        self.assertTrue(fc['prefs']['existsInProject'])
        self.assertEqual([i for i in r['fontIssues'] if i['kind'] == 'font'], [])
        self.assertEqual(fc['warnings'], [])

    def test_threshold_comes_from_device_font_check(self):
        """⑤ 判定阈值单一来源：改 `device_font_check.CJK_SIZE_MIN_KB` 同时改结论（没有第二套数字）。"""
        _mk(self.tmp, fonts=[('mid.ttf', 300)])          # 300 KB：默认口径 = 常用字级（不算缺）
        _no_adb_probe(self)
        r = U.jcall('flythings_check_project_deps', {'project_root': self.tmp})
        self.assertEqual(r['fontCheck']['verdict'], 'project_partial_cjk')   # 200 < 300 < 1024
        self.assertFalse(r['fontCheck']['missingChinese'])
        dfc = _dfc()
        with mock.patch.object(dfc, 'CJK_SIZE_MIN_KB', 512):                 # 阈值调到 512 KB
            r2 = U.jcall('flythings_check_project_deps', {'project_root': self.tmp})
        self.assertEqual(r2['fontCheck']['verdict'], 'project_no_cjk')
        self.assertTrue(r2['fontCheck']['missingChinese'])

    def test_off_switch_disables_font_check(self):
        """② font_check='off' → 不做字体动作：enabled=false、零 warning、不写盘、不探 adb。"""
        _mk(self.tmp)
        _no_adb_probe(self)
        r = U.jcall('flythings_check_project_deps',
                    {'project_root': self.tmp, 'font_check': 'off'})
        fc = r['fontCheck']
        self.assertFalse(fc['enabled'])
        self.assertEqual(fc['warnings'], [])
        self.assertEqual(r['fontIssues'], [])
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, 'font')))

    def test_font_apply_delivers_and_lists_files(self):
        """`font_apply=True`（显式opt-in）→ 真投递：字体进 font/ + prefs 改指 + 补齐 enable.font.location。"""
        _mk(self.tmp, prefs_font='/res/font/old.ttf')
        _no_adb_probe(self)
        r = U.jcall('flythings_check_project_deps',
                    {'project_root': self.tmp, 'font_apply': True})
        fc = r['fontCheck']
        de = fc['delivered']
        self.assertTrue(de['applied'], de)
        self.assertEqual(de['tier'], 'common')
        self.assertIn('font/zkswe-hans-common.ttf', de['files'])
        self.assertIn('.settings/com.zksw.flythings.easyui.prefs', de['files'])
        self.assertIn('package.properties', de['files'])
        dst = os.path.join(self.tmp, 'font', 'zkswe-hans-common.ttf')
        src = os.path.join(os.path.dirname(ft.DFC_PATH), '..', 'fonts', 'zkswe-hans-common.ttf')
        self.assertEqual(os.path.getsize(dst), os.path.getsize(os.path.normpath(src)),
                         '投递的必须是 device_font_check.TIERS 里那一份（单一来源）')
        prefs = open(os.path.join(self.tmp, '.settings',
                                  'com.zksw.flythings.easyui.prefs'), encoding='utf-8').read()
        self.assertIn('zkswe-hans-common.ttf', prefs)
        props = open(os.path.join(self.tmp, 'package.properties'), encoding='utf-8').read()
        self.assertIn('enable.font.location=true', props)

    def test_tier_override_chooses_other_variant(self):
        """`font_tier='multi'` → 投的是多语言版（文件名来自 TIERS，不是硬编码）。"""
        _mk(self.tmp, prefs_font='/res/font/old.ttf')
        _no_adb_probe(self)
        r = U.jcall('flythings_check_project_deps',
                    {'project_root': self.tmp, 'font_apply': True, 'font_tier': 'multi'})
        de = r['fontCheck']['delivered']
        self.assertEqual(de['tier'], 'multi')
        self.assertIn('font/zkswe-hans-multi.ttf', de['files'])
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, 'font', 'zkswe-hans-multi.ttf')))

    def test_device_branch_scans_device_fonts(self):
        """① 传 device= 时扫设备字体：deviceFonts 带路径+体积，缺中文 → 默认档 common。"""
        _mk(self.tmp, prefs_font='/res/font/old.ttf', fonts=[('old.ttf', 20)])
        for p in _fake_device([{'dir': '/etc/font', 'name': 'fzcircle.ttf', 'sizeBytes': 21200}]):
            p.start()
            self.addCleanup(p.stop)
        r = U.jcall('flythings_check_project_deps',
                    {'project_root': self.tmp, 'device': DEV['serial']})
        fc = r['fontCheck']
        self.assertEqual(fc['mode'], 'device')
        self.assertEqual(fc['device'], DEV['serial'])
        self.assertEqual(fc['deviceFonts'][0]['name'], 'fzcircle.ttf')
        self.assertEqual(fc['deviceFonts'][0]['sizeKB'], 20.7)
        self.assertTrue(fc['missingChinese'])
        self.assertEqual(fc['verdict'], 'no_cjk')
        msg = r['fontIssues'][0]['msg']
        self.assertIn('设备侧扫描', msg)
        self.assertIn('no_cjk', msg)


class TestBuildFlowFontStep(unittest.TestCase):
    """①②③ 构建流程接线：默认投递 / 可关 / 投递在 build 之前。"""

    def setUp(self):
        self.tmp = U.project()

    def tearDown(self):
        U.cleanup(self.tmp)

    def _fake_fun(self):
        seen = []

        def f(cmd, project_dir, **kw):
            seen.append(cmd)
            return {'success': True, 'returncode': 0, 'stdout': '%s ok' % cmd, 'stderr': ''}
        return f, seen

    def _flow(self, prefs_font='', fonts=(), extra=None):
        _mk(self.tmp, prefs_font=prefs_font, fonts=fonts)
        U.write(os.path.join(self.tmp, 'Manifest.xml'),
                '<manifest platform="Z21"><dependencies>'
                '<package id="base-utility" version="^10.0.0"/></dependencies></manifest>')
        page = os.path.join(self.tmp, 'ui', 'main.json')
        U.write(page, '{}')
        ftu = os.path.join(self.tmp, 'ui', 'main.ftu')
        os.utime(ftu, (os.path.getmtime(page) + 1,) * 2)      # json/ftu 时间戳一致 → 不 pack
        args = {'project_root': self.tmp, 'with_launch': False}
        args.update(extra or {})
        fn, seen = self._fake_fun()
        with mock.patch.object(pt, '_run_fun', fn):
            r = U.jcall('flythings_build_ui_flow', args)
        return r, seen

    def test_off_switch_produces_no_font_step(self):
        """② font_check='off' → 没有任何字体 step（也不写盘）。"""
        r, seen = self._flow(prefs_font='/res/font/old.ttf', extra={'font_check': 'off'})
        self.assertTrue(r['ok'], r)
        self.assertEqual([s for s in r['steps'] if s['step'] == 'check_font'], [])
        self.assertFalse(r['fontCheck']['enabled'], r['fontCheck'])
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, 'font')))

    def test_default_auto_delivers_before_build(self):
        """① 默认（auto）：缺中文 → 自动投递 common，step 在 fun build **之前**，返回体写清写入文件。"""
        r, seen = self._flow(prefs_font='/res/font/old.ttf')
        self.assertTrue(r['ok'], r)
        self.assertEqual(seen, ['install', 'build'])
        names = [s['step'] for s in r['steps']]
        self.assertIn('check_font', names)
        self.assertLess(names.index('check_font'), names.index('fun build'),
                        '字体必须在编译前投递，否则本次构建/推送的产物里没有它')
        fc = r['fontCheck']
        self.assertTrue(fc['delivered']['applied'], fc['delivered'])
        self.assertIn('font/zkswe-hans-common.ttf', fc['delivered']['files'])
        self.assertEqual(fc['mode'], 'project')
        self.assertIn('未连设备，仅工程侧检查', fc['note'])
        w = ' '.join(r.get('warnings', []))
        self.assertIn('已自动投递', w)
        self.assertIn('font/zkswe-hans-common.ttf', w)
        step = [s for s in r['steps'] if s['step'] == 'check_font'][0]
        self.assertIn('font/zkswe-hans-common.ttf', step['detail'])

    def test_delivery_failure_reports_fix_command(self):
        """投递没法完成（工程没有 easyui prefs）→ 不给假成功：step.success=false + 一键修复命令。"""
        _mk(self.tmp, props=None)                     # 连 package.properties 都没有
        U.write(os.path.join(self.tmp, 'Manifest.xml'),
                '<manifest platform="Z21"><dependencies>'
                '<package id="base-utility" version="^10.0.0"/></dependencies></manifest>')
        page = os.path.join(self.tmp, 'ui', 'main.json')
        U.write(page, '{}')
        os.utime(os.path.join(self.tmp, 'ui', 'main.ftu'),
                 (os.path.getmtime(page) + 1,) * 2)
        fn, _ = self._fake_fun()
        with mock.patch.object(pt, '_run_fun', fn):
            r = U.jcall('flythings_build_ui_flow',
                        {'project_root': self.tmp, 'with_launch': False})
        self.assertTrue(r['ok'], r)
        step = [s for s in r['steps'] if s['step'] == 'check_font'][0]
        self.assertFalse(step['success'], step)
        w = ' '.join(r.get('warnings', []))
        self.assertIn('未完成', w)
        self.assertIn('device_font_check.py --apply', w)

    def test_clean_project_zero_font_noise(self):
        """正例：工程已有 1.5 MB 中文字体 → 无字体 warning、不投递（正常路径零噪音）。"""
        r, _ = self._flow(fonts=[('big.ttf', 1536)])
        self.assertTrue(r['ok'], r)
        self.assertFalse(r.get('warnings'), r.get('warnings'))
        self.assertFalse(r['fontCheck']['missingChinese'])
        step = [s for s in r['steps'] if s['step'] == 'check_font'][0]
        self.assertEqual(step['verdict'], 'project_has_cjk')

    def test_tier_override_in_flow(self):
        """`font_tier='full'` 覆盖默认档（生僻字场景）。"""
        r, _ = self._flow(prefs_font='/res/font/old.ttf', extra={'font_tier': 'full'})
        self.assertIn('font/zkswe-hans-full.ttf', r['fontCheck']['delivered']['files'])
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, 'font', 'zkswe-hans-full.ttf')))

    def test_device_branch_uses_gate_device(self):
        """① 有设备（设备门已探到一台）→ 扫设备字体并在 build 前投递；不重复探 adb。"""
        _mk(self.tmp, prefs_font='/res/font/old.ttf', fonts=[('old.ttf', 20)])
        gate = {'needDeviceInput': False, 'serial': DEV['serial'], 'model': DEV['model'],
                'platformMatch': 'match', 'installHint': '', 'message': '',
                'devices': [DEV], 'offline': [], 'adb': 'adb', 'adbSource': 'unittest',
                'explicit': True, 'connectNote': '', 'count': 1}
        probes = {'n': 0}

        def counting_probe(*a, **k):
            probes['n'] += 1
            return {'ok': True, 'online': [DEV], 'offline': [], 'adb': 'adb',
                    'adbSource': 'unittest', 'count': 1}

        patches = [mock.patch.object(pt, '_launch_gate', lambda p, d: gate),
                   mock.patch.object(pt, '_device_sync_check',
                                     lambda root, s, p: {'checked': True, 'allMatch': True,
                                                         'stale': [], 'ftu': [], 'so': [],
                                                         'reason': ''}),
                   mock.patch.object(ft._adb, 'probe_devices', counting_probe),
                   mock.patch.object(ft._adb, 'ensure_busybox', lambda *a, **k: '')]
        patches += _fake_device([{'dir': '/etc/font', 'name': 'fzcircle.ttf',
                                  'sizeBytes': 21200}])[2:3]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        fn, seen = self._fake_fun()
        with mock.patch.object(pt, '_run_fun', fn):
            r = U.jcall('flythings_build_ui_flow', {'project_root': self.tmp})
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['fontCheck']['mode'], 'device')
        self.assertEqual(r['fontCheck']['deviceFonts'][0]['name'], 'fzcircle.ttf')
        self.assertTrue(r['fontCheck']['missingChinese'])
        self.assertIn('font/zkswe-hans-common.ttf', r['fontCheck']['delivered']['files'])
        self.assertEqual(probes['n'], 0, '设备门已探过 → 字体体检不该再探一次 adb')
        self.assertIn('launch', seen)


if __name__ == '__main__':
    unittest.main(verbosity=2)
