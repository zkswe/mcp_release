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
# 仓库自带字体（当「设备上的字体」用 —— 离线，不联网）：common/full/multi 均覆盖 GB2312 一级 100%
REPO_FONT_DIR = os.path.join(U.BASE, 'components', 'fonts', 'fonts')
REPO_COMMON = os.path.join(REPO_FONT_DIR, 'zkswe-hans-common.ttf')


def _dfc():
    mod, err = ft.device_font_check()
    assert mod is not None, err
    return mod


def _fake_pull_from(src_path, calls=None):
    """替掉 device_font_check.pull_font：把 `src_path` 当成「刚从设备拉回来的字体」。

    只换 adb 那一步（网络边界），后面的 cmap 解析/判定/缓存/临时目录清理跑的是**真实现**。
    """
    def f(adb, serial, remote_path, dest_path, timeout=180):
        if calls is not None:
            calls.append(remote_path)
        os.makedirs(os.path.dirname(dest_path) or '.', exist_ok=True)
        shutil.copyfile(src_path, dest_path)
        return True, 'unittest pull %s' % remote_path
    return f


def _synth_font(path, chars):
    """用 fontTools 现场造一个「只含指定字符」的字体（离线；仓库没带拉丁字体故必须自己造）。"""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(['.notdef', 'A'])
    fb.setupCharacterMap({ord(c): 'A' for c in chars})
    fb.setupGlyf({'.notdef': TTGlyphPen(None).glyph(), 'A': TTGlyphPen(None).glyph()})
    fb.setupHorizontalMetrics({'.notdef': (500, 0), 'A': (500, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({'familyName': 'ZkTest', 'styleName': 'Regular'})
    fb.setupOS2()
    fb.setupPost()
    fb.save(path)
    return path


def _device_font_dict(path, name='devfont.ttf', dir_='/etc/font'):
    """构造一条「设备 ls 到的字体」记录（体积用真实文件体积，免得与拉回来的对不上）。"""
    return {'dir': dir_, 'name': name, 'sizeBytes': os.path.getsize(path),
            'mtimeText': 'Jan 1 2026'}


def _locale_testcase(testcase):
    """把探测缓存指到临时文件（测试不许写用户真实 ~/.fun，也不许靠上一次跑的结果）。"""
    import tempfile
    cache = os.path.join(tempfile.mkdtemp(prefix='fontcache_'), 'font-probe.json')
    old = os.environ.get('FLYTHINGS_FONT_CACHE')
    os.environ['FLYTHINGS_FONT_CACHE'] = cache

    def _restore():
        if old is None:
            os.environ.pop('FLYTHINGS_FONT_CACHE', None)
        else:
            os.environ['FLYTHINGS_FONT_CACHE'] = old
        shutil.rmtree(os.path.dirname(cache), ignore_errors=True)
    testcase.addCleanup(_restore)
    return cache


def _mk(root, prefs_font='', fonts=(), props='projectName=unittest\n'):
    """最小工程骨架：ui/main.ftu + src + package.properties（可选 prefs / font/ 假字体）。"""
    os.makedirs(os.path.join(root, 'ui'), exist_ok=True)
    os.makedirs(os.path.join(root, 'src'), exist_ok=True)
    open(os.path.join(root, 'ui', 'main.ftu'), 'wb').write(U.ftu_bytes() or b'ZKSR')
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
        mock.patch.object(ft._adb, 'ensure_busybox', lambda *a, **k: '/tmp/busybox_unittest'),
        mock.patch.object(_dfc(), 'collect',
                          lambda adb, serial, use_busybox:
                              {'props': {'ro.product.model': DEV['model']},
                               'fonts': list(collect_fonts), 'raw_dirs': {}}),
    ]
    return patches


def _fake_device_branch(testcase, src_font, name='fzcircle.ttf', dir_='/etc/font'):
    """设备分支全套假体：探测 / collect / **拉取** —— 离线，但 cmap 判定链走真实现。

    返回 (calls, record)：calls = 拉取过的设备路径列表（用来证明缓存命中/超限不拉）。
    """
    calls = []
    rec = _device_font_dict(src_font, name=name, dir_=dir_)
    for p in _fake_device([rec]):
        p.start()
        testcase.addCleanup(p.stop)
    pm = mock.patch.object(_dfc(), 'pull_font', _fake_pull_from(src_font, calls))
    pm.start()
    testcase.addCleanup(pm.stop)
    _locale_testcase(testcase)
    return calls, rec


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

    def test_device_branch_cmap_missing_delivers(self):
        """① 设备分支（**硬判据**）：设备最大字体只有拉丁 → cmap 覆盖率 0% → missing + 投递 common。

        （仓库未带拉丁字体：用 fontTools 现场造一个——离线、不联网、不连真机。）
        """
        _mk(self.tmp, prefs_font='/res/font/old.ttf', fonts=[('old.ttf', 20)])
        latin = _synth_font(os.path.join(self.tmp, 'latin_only.ttf'), 'ABCabc0123')
        calls, _rec = _fake_device_branch(self, latin)
        r = U.jcall('flythings_check_project_deps',
                    {'project_root': self.tmp, 'device': DEV['serial']})
        fc = r['fontCheck']
        self.assertEqual(fc['mode'], 'device')
        self.assertEqual(fc['device'], DEV['serial'])
        self.assertEqual(fc['source'], 'cmap', fc)
        self.assertEqual(fc['cmapCoverageGB2312L1'], 0.0)
        self.assertEqual(fc['cmapCoveredChars'], 0)
        self.assertEqual(fc['cmapTotalChars'], 3755)
        self.assertEqual(fc['verdict'], 'missing')
        self.assertTrue(fc['missingChinese'])
        self.assertEqual(fc['checkedFont']['name'], 'fzcircle.ttf')
        self.assertTrue(fc['checkedFont']['sizeBytes'] > 0)
        self.assertEqual(len(calls), 1, calls)
        msg = r['fontIssues'][0]['msg']
        self.assertIn('设备侧扫描', msg)
        self.assertIn('missing', msg)
        self.assertIn('GB2312 一级覆盖率', msg)


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
        """正例：工程已有 1.5 MB 中文字体 → 无字体 warning、不投递（正常路径零噪音）。

        ⚠️ v0.27.101 起：「设计先行」软闸门会给无设计产物的工程附一条
        `未检测到设计确认稿…`（不是字体噪音），本用例先剔除它再断言。
        """
        r, _ = self._flow(fonts=[('big.ttf', 1536)])
        self.assertTrue(r['ok'], r)
        noise = [w for w in (r.get('warnings') or []) if '未检测到设计确认稿' not in w]
        self.assertFalse(noise, noise)
        self.assertFalse(r['fontCheck']['missingChinese'])
        step = [s for s in r['steps'] if s['step'] == 'check_font'][0]
        self.assertEqual(step['verdict'], 'project_has_cjk')

    def test_tier_override_in_flow(self):
        """`font_tier='full'` 覆盖默认档（生僻字场景）。"""
        r, _ = self._flow(prefs_font='/res/font/old.ttf', extra={'font_tier': 'full'})
        self.assertIn('font/zkswe-hans-full.ttf', r['fontCheck']['delivered']['files'])
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, 'font', 'zkswe-hans-full.ttf')))

    def test_device_branch_uses_gate_device(self):
        """① 有设备（设备门已探到一台）→ 硬判据拉字体算覆盖率 → 在 build 前投递；不重复探 adb。

        同时钉住 v0.27.87 的**部署后复查**口子：deviceAfterDeploy 回答「字库要不要固化」。
        """
        _mk(self.tmp, prefs_font='/res/font/old.ttf', fonts=[('old.ttf', 20)])
        latin = _synth_font(os.path.join(self.tmp, 'latin_only.ttf'), 'ABCabc0123')
        calls = []
        gate = {'needDeviceInput': False, 'serial': DEV['serial'], 'model': DEV['model'],
                'platformMatch': 'match', 'installHint': '', 'message': '',
                'devices': [DEV], 'offline': [], 'adb': 'adb', 'adbSource': 'unittest',
                'explicit': True, 'connectNote': '', 'count': 1}
        probes = {'n': 0}

        def counting_probe(*a, **k):
            probes['n'] += 1
            return {'ok': True, 'online': [DEV], 'offline': [], 'adb': 'adb',
                    'adbSource': 'unittest', 'count': 1}

        rec = _device_font_dict(latin, name='fzcircle.ttf')
        patches = [mock.patch.object(pt, '_launch_gate', lambda p, d: gate),
                   mock.patch.object(pt, '_device_sync_check',
                                     lambda root, s, p: {'checked': True, 'allMatch': True,
                                                         'stale': [], 'ftu': [], 'so': [],
                                                         'reason': ''}),
                   mock.patch.object(ft._adb, 'probe_devices', counting_probe),
                   mock.patch.object(ft._adb, 'ensure_busybox', lambda *a, **k: '/tmp/busybox_unittest'),
                   mock.patch.object(_dfc(), 'pull_font', _fake_pull_from(latin, calls))]
        patches += _fake_device([rec])[2:3]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        _locale_testcase(self)
        fn, seen = self._fake_fun()
        with mock.patch.object(pt, '_run_fun', fn):
            r = U.jcall('flythings_build_ui_flow', {'project_root': self.tmp})
        self.assertTrue(r['ok'], r)
        fc = r['fontCheck']
        self.assertEqual(fc['mode'], 'device')
        self.assertEqual(fc['deviceFonts'][0]['name'], 'fzcircle.ttf')
        self.assertEqual(fc['source'], 'cmap')
        self.assertEqual(fc['cmapCoverageGB2312L1'], 0.0)
        self.assertEqual(fc['verdict'], 'missing')
        self.assertTrue(fc['missingChinese'])
        self.assertIn('font/zkswe-hans-common.ttf', fc['delivered']['files'])
        self.assertEqual(probes['n'], 0, '设备门已探过 → 字体体检不该再探一次 adb')
        self.assertIn('launch', seen)
        # 部署后复查：设备上还是没有该字体 → 必须说清「要 pack_upgrade 固化」
        after = fc['deviceAfterDeploy']
        self.assertTrue(after['checked'], after)
        self.assertFalse(after['consistent'])
        self.assertIn('pack_upgrade', after['note'])
        self.assertTrue(any('固化' in w for w in r.get('warnings', [])), r.get('warnings'))
        step = [s for s in r['steps'] if s['step'] == 'check_font'][0]
        self.assertEqual(step['source'], 'cmap')
        self.assertEqual(step['cmapCoverageGB2312L1'], 0.0)
        self.assertEqual(step['checkedFont']['name'], 'fzcircle.ttf')
        self.assertEqual(calls, ['/etc/font/fzcircle.ttf'], calls)


class TestFontCmapHardProbe(unittest.TestCase):
    """A. **硬判据（cmap 覆盖率）**（v0.27.87，钟工拍板：比体积判据好）

    钉住：① 基准集 = GB2312 一级 3755 字；② 三档阈值 90/50；③ 三条 verdict + 投递与否；
    ④ 缓存命中不重复拉；⑤ 超限 / fontTools 不可用 / 拉取失败 → **退回体积判据且写明原因**；
    ⑥ 临时文件用完即删；⑦ 部署后复查（consistent / 要固化）；⑧ 仓库自带字体当真机字体的证据。
    全程离线（不联网、不连真机）：只把 adb pull 那一步换成拷贝。
    """

    def setUp(self):
        self.tmp = U.project()

    def tearDown(self):
        U.cleanup(self.tmp)

    # ---- 基准集与阈值 ----
    def test_gb2312_level1_basis_is_3755(self):
        """基准集必须是 GB2312 一级 3755 字（不靠外部文件，用 codec 现场推）。"""
        chars = _dfc().gb2312_level1()
        self.assertEqual(len(chars), 3755)
        self.assertEqual(len(set(chars)), 3755)
        self.assertEqual(_dfc().CMAP_TOTAL_CHARS, 3755)
        self.assertIn('一', chars)
        self.assertIn('汉', chars)

    def test_judge_cmap_thresholds(self):
        """≥90% ok / 50–90% low / <50% missing（边界值逐条钉死）。"""
        j = _dfc().judge_cmap
        self.assertEqual(j(100.0)['verdict'], 'ok')
        self.assertEqual(j(90.0)['verdict'], 'ok')
        self.assertFalse(j(90.0)['needFont'])
        self.assertIsNone(j(90.0)['recommendTier'])
        self.assertEqual(j(89.9)['verdict'], 'low')
        self.assertTrue(j(89.9)['needFont'])
        self.assertEqual(j(50.0)['verdict'], 'low')
        self.assertEqual(j(50.0)['recommendTier'], 'common')
        self.assertEqual(j(49.9)['verdict'], 'missing')
        self.assertEqual(j(0.0)['verdict'], 'missing')
        self.assertTrue(j(0.0)['needFont'])
        self.assertEqual(_dfc().CMAP_OK_MIN_PCT, 90.0)
        self.assertEqual(_dfc().CMAP_LOW_MIN_PCT, 50.0)
        self.assertEqual(_dfc().PROBE_MAX_BYTES, 12 * 1024 * 1024)

    def test_repo_common_font_covers_basis(self):
        """仓库自带三版字体都覆盖 GB2312 一级 100% → 投递 common 够用（阈值 90%）。"""
        for tier in ('common', 'full', 'multi'):
            p = os.path.join(REPO_FONT_DIR, 'zkswe-hans-%s.ttf' % tier)
            pct, covered, total, err = _dfc().font_cmap_coverage(p)
            self.assertEqual(err, '', err)
            self.assertEqual(total, 3755)
            self.assertEqual(covered, 3755, tier)
            self.assertGreaterEqual(pct, 90.0)

    def test_probe_font_direct_reasons(self):
        """probe_font 的退回信号：文件不存在 / 超限 —— 必须带 reason，且 verdict=None。"""
        miss = _dfc().probe_font(os.path.join(self.tmp, 'nope.ttf'))
        self.assertEqual(miss['source'], 'size')
        self.assertIsNone(miss['verdict'])
        self.assertIn('不存在', miss['reason'])
        big = _dfc().probe_font(REPO_COMMON, size_bytes=13 * 1024 * 1024)
        self.assertEqual(big['source'], 'size')
        self.assertIsNone(big['verdict'])
        self.assertIn('PROBE_MAX_BYTES', big['reason'])

    # ---- 三条 verdict（走 font_preflight 全链）----
    def _preflight(self, src_font, name='devfont.ttf', platform='Z21', **kw):
        _mk(self.tmp, prefs_font='/res/font/old.ttf')     # 投递要改 prefs：没它投不了（见 deliver）
        calls, rec = _fake_device_branch(self, src_font, name=name)
        st = ft.font_preflight(self.tmp, platform, device=DEV['serial'], **kw)
        return st, calls, rec

    def test_device_font_ok_no_delivery(self):
        """仓库 common 字体当设备字体 → 覆盖率 100% → verdict=ok、**不投递**、零 warning。"""
        st, calls, _rec = self._preflight(REPO_COMMON, name='source-han.ttf')
        self.assertEqual(st['source'], 'cmap')
        self.assertEqual(st['verdict'], 'ok')
        self.assertEqual(st['cmapCoverageGB2312L1'], 100.0)
        self.assertEqual(st['cmapCoveredChars'], 3755)
        self.assertFalse(st['missingChinese'])
        self.assertFalse(st['delivered']['applied'])
        self.assertEqual(st['warnings'], [], st['warnings'])
        self.assertIn('无需投递', st.get('info', ''))
        self.assertEqual(st['checkedFont']['name'], 'source-han.ttf')
        self.assertEqual(st['probe']['source'], 'cmap')
        self.assertEqual(st['probe']['cacheHit'], False)
        self.assertEqual(len(calls), 1, calls)
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, 'font')))

    def test_device_font_low_delivers_with_coverage(self):
        """50–90% → verdict=low：投递 + warning 写明覆盖率（不靠体积猜）。"""
        mid = _synth_font(os.path.join(self.tmp, 'mid.ttf'), _dfc().gb2312_level1()[:2000])
        st, _calls, _rec = self._preflight(mid, name='partial-hans.ttf',
                                           font_check='auto')
        self.assertEqual(st['source'], 'cmap')
        self.assertEqual(st['verdict'], 'low')
        self.assertAlmostEqual(st['cmapCoverageGB2312L1'], 53.3, places=1)
        self.assertTrue(st['missingChinese'])
        self.assertTrue(st['delivered']['applied'], st['delivered'])
        self.assertEqual(st['tier'], 'common')
        w = ' '.join(st['warnings'])
        self.assertIn('low', w)
        self.assertIn('53.3%', w)
        self.assertIn('font/zkswe-hans-common.ttf', w)

    def test_device_font_missing_delivers(self):
        """<50%（只有拉丁）→ verdict=missing：投递 + warning 写明覆盖率 0%。"""
        latin = _synth_font(os.path.join(self.tmp, 'latin.ttf'), 'ABCabc0123')
        st, _calls, _rec = self._preflight(latin, name='latin-only.ttf')
        self.assertEqual(st['source'], 'cmap')
        self.assertEqual(st['verdict'], 'missing')
        self.assertEqual(st['cmapCoverageGB2312L1'], 0.0)
        self.assertTrue(st['delivered']['applied'], st['delivered'])
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, 'font',
                                                    'zkswe-hans-common.ttf')))
        w = ' '.join(st['warnings'])
        self.assertIn('missing', w)
        self.assertIn('0.0%', w)

    # ---- 缓存 / 超限 / 降级 / 临时文件 ----
    def test_probe_cache_hit_avoids_second_pull(self):
        """第二次探测命中缓存：**不再拉取**、结论一致、缓存文件真存在（成本控制）。"""
        cache = _locale_testcase(self)
        calls = []
        rec = _device_font_dict(REPO_COMMON, name='source-han.ttf')
        with mock.patch.object(_dfc(), 'pull_font', _fake_pull_from(REPO_COMMON, calls)):
            first = ft.hard_probe(DEV['serial'], [rec], 'Z21')
            second = ft.hard_probe(DEV['serial'], [rec], 'Z21')
        self.assertEqual(len(calls), 1, calls)
        self.assertFalse(first['cacheHit'])
        self.assertTrue(second['cacheHit'], second)
        self.assertEqual(first['verdict'], second['verdict'])
        self.assertEqual(second['cmapCoverageGB2312L1'], 100.0)
        self.assertTrue(os.path.isfile(cache), cache)
        data = json.load(open(cache, encoding='utf-8'))
        self.assertEqual(data['version'], ft.PROBE_CACHE_VERSION)
        self.assertEqual(len(data['entries']), 1)
        entry = list(data['entries'].values())[0]
        self.assertEqual(entry['verdict'], 'ok')
        self.assertTrue(entry['localMd5'], entry)
        self.assertEqual(cache, ft.probe_cache_path())
        # 换个体积（设备侧字体被换过）→ 缓存键变 → 重新拉
        calls2 = []
        rec2 = dict(rec, sizeBytes=rec['sizeBytes'] + 1)
        with mock.patch.object(_dfc(), 'pull_font', _fake_pull_from(REPO_COMMON, calls2)):
            third = ft.hard_probe(DEV['serial'], [rec2], 'Z21')
        self.assertEqual(len(calls2), 1, calls2)
        self.assertFalse(third['cacheHit'])

    def test_oversize_font_never_pulled_falls_back_to_size(self):
        """拉取上限 12 MB：超了就**不拉**，退回体积判据（source=size + warning 写清原因）。"""
        calls = []
        rec = {'dir': '/res/font', 'name': 'huge.ttf', 'sizeBytes': 13 * 1024 * 1024,
               'mtimeText': 'Jan 1 2026'}
        with mock.patch.object(_dfc(), 'pull_font', _fake_pull_from(REPO_COMMON, calls)):
            hp = ft.hard_probe(DEV['serial'], [rec], 'Z21')
        self.assertEqual(calls, [], '超限不许拉（13MB 拖回来没意义）')
        self.assertEqual(hp['source'], 'size')
        self.assertIsNone(hp['verdict'])
        self.assertIsNone(hp['cmapCoverageGB2312L1'])
        self.assertIn('PROBE_MAX_BYTES', hp['reason'])
        self.assertTrue(any('体积判据' in w for w in hp['warnings']), hp['warnings'])
        self.assertEqual(hp['checkedFont']['name'], 'huge.ttf')

    def test_oversize_in_preflight_keeps_size_verdict(self):
        """端到端：超限时 fontCheck 的 verdict 仍是体积判据的结论（13MB → has_cjk）。"""
        rec = {'dir': '/res/font', 'name': 'huge.ttf', 'sizeBytes': 13 * 1024 * 1024,
               'mtimeText': 'Jan 1 2026'}
        calls = []
        for p in _fake_device([rec]):
            p.start()
            self.addCleanup(p.stop)
        with mock.patch.object(_dfc(), 'pull_font', _fake_pull_from(REPO_COMMON, calls)):
            st = ft.font_preflight(self.tmp, 'Z21', device=DEV['serial'])
        self.assertEqual(st['source'], 'size')
        self.assertEqual(st['verdict'], 'has_cjk')
        self.assertFalse(st['missingChinese'])
        self.assertEqual(st['cmapCoverageGB2312L1'], None)
        self.assertTrue(any('退回' in w for w in st['warnings']), st['warnings'])
        self.assertEqual(calls, [])

    def test_fonttools_unavailable_falls_back_to_size(self):
        """fontTools 不可用 → 退回体积判据，warning 必须点名 fontTools（绝不静默退）。"""
        calls = []
        rec = _device_font_dict(REPO_COMMON, name='source-han.ttf')
        with mock.patch.object(_dfc(), 'pull_font', _fake_pull_from(REPO_COMMON, calls)), \
                mock.patch.object(_dfc(), 'fonttools_error',
                                  lambda: 'ImportError: no module named fontTools'):
            hp = ft.hard_probe(DEV['serial'], [rec], 'Z21')
        self.assertEqual(len(calls), 0, calls)
        self.assertEqual(hp['source'], 'size')
        self.assertIn('fontTools', hp['reason'])
        self.assertTrue(any('fontTools' in w for w in hp['warnings']), hp['warnings'])

    def test_pull_failure_falls_back_to_size(self):
        """拉取失败（设备掉线/路径不对）→ 退回体积判据 + warning 写明拉取失败。"""
        rec = _device_font_dict(REPO_COMMON, name='source-han.ttf')
        with mock.patch.object(_dfc(), 'pull_font',
                               lambda *a, **k: (False, 'error: device offline')):
            hp = ft.hard_probe(DEV['serial'], [rec], 'Z21')
        self.assertEqual(hp['source'], 'size')
        self.assertIsNone(hp['verdict'])
        self.assertIn('拉取失败', hp['reason'])
        self.assertTrue(any('退回' in w for w in hp['warnings']), hp['warnings'])

    def test_probe_temp_file_removed(self):
        """临时目录用完即删：拉回来的字体不在临时目录里留存。"""
        seen = {}

        def spy(adb, serial, remote_path, dest_path, timeout=180):
            seen['dest'] = dest_path
            seen['dir'] = os.path.dirname(dest_path)
            shutil.copyfile(REPO_COMMON, dest_path)
            return True, 'spy'
        _locale_testcase(self)
        rec = _device_font_dict(REPO_COMMON, name='source-han.ttf')
        with mock.patch.object(_dfc(), 'pull_font', spy):
            ft.hard_probe(DEV['serial'], [rec], 'Z21')
        self.assertIn('dest', seen)
        self.assertFalse(os.path.exists(seen['dest']), seen['dest'])
        self.assertFalse(os.path.isdir(seen['dir']), seen['dir'])
        self.assertIn('font_probe_', seen['dir'])

    def test_empty_device_scan_is_flagged_uncertain(self):
        """扫描结果为空时**不要把结论说得像板上真的没字库**（v0.27.87 真机实测补）。

        （实测背景：busybox 未就绪 + 设备自带 ls 解析不出来时，列表也是空的 → 会误报「无字库」
        并触发投递；这里钉住「必须把存疑写进 scanNote/warnings」。）
        """
        _mk(self.tmp, prefs_font='/res/font/old.ttf')
        calls, _rec = _fake_device_branch(self, REPO_COMMON)
        for p in _fake_device([]):                    # 设备 ls 什么都没解析到
            p.start()
            self.addCleanup(p.stop)
        st = ft.font_preflight(self.tmp, 'Z21', device=DEV['serial'])
        self.assertEqual(st['source'], 'size')        # 没字体可探 → 硬判据无从下手
        self.assertIn('没解析出任何字体', st.get('scanNote', ''))
        self.assertTrue(any('没解析出任何字体' in w for w in st['warnings']), st['warnings'])
        self.assertEqual(calls, [], calls)

    def test_probe_uses_biggest_device_font(self):
        """多个字体时只探最大的那个（成本控制：一次只拉一个文件）。"""
        small = _synth_font(os.path.join(self.tmp, 'small.ttf'), 'ABC')
        calls = []
        fonts = [dict(_device_font_dict(small, name='small.ttf'), sizeBytes=10000),
                 dict(_device_font_dict(REPO_COMMON, name='big.ttf'))]
        _locale_testcase(self)
        with mock.patch.object(_dfc(), 'pull_font', _fake_pull_from(REPO_COMMON, calls)):
            hp = ft.hard_probe(DEV['serial'], fonts, 'Z21')
        self.assertEqual(calls, ['/etc/font/big.ttf'], calls)
        self.assertEqual(hp['checkedFont']['name'], 'big.ttf')
        self.assertEqual(hp['verdict'], 'ok')

    # ---- 部署后复查（与应用侧 staleOnDevice 凑闭环）----
    def test_after_deploy_recheck_mismatch_needs_pack_upgrade(self):
        """投递过字体但设备侧还是没有 → consistent=False + 明说「要 pack_upgrade 固化」。"""
        _mk(self.tmp, prefs_font='/res/font/old.ttf')
        delivered = {'applied': True, 'tier': 'common', 'file': 'zkswe-hans-common.ttf',
                     'files': ['font/zkswe-hans-common.ttf', 'package.properties']}
        scan = {'verdict': 'no_cjk', 'maxFontKB': 20.7,
                'deviceFonts': [{'name': 'fzcircle.ttf', 'sizeBytes': 21200}]}
        with mock.patch.object(ft, 'device_scan', lambda s, p='': (scan, '')):
            out = ft.recheck_after_deploy(DEV['serial'], 'Z21', self.tmp, delivered)
        self.assertTrue(out['checked'])
        self.assertFalse(out['consistent'])
        self.assertIn('pack_upgrade', out['note'])
        self.assertEqual(out['deviceMaxFontKB'], 20.7)
        self.assertEqual(out['projectFont'], 'zkswe-hans-common.ttf')
        self.assertTrue(out['warnings'], out)

    def test_after_deploy_recheck_consistent_after_flash(self):
        """固化生效（设备侧字体名字+体积与工程投递一致）→ consistent=True、无 warning。"""
        _mk(self.tmp, prefs_font='/res/font/old.ttf')
        os.makedirs(os.path.join(self.tmp, 'font'), exist_ok=True)
        shutil.copyfile(REPO_COMMON, os.path.join(self.tmp, 'font',
                                                  'zkswe-hans-common.ttf'))
        size = os.path.getsize(os.path.join(self.tmp, 'font', 'zkswe-hans-common.ttf'))
        delivered = {'applied': True, 'tier': 'common', 'file': 'zkswe-hans-common.ttf',
                     'files': ['font/zkswe-hans-common.ttf']}
        scan = {'verdict': 'has_cjk', 'maxFontKB': round(size / 1024.0, 1),
                'deviceFonts': [{'name': 'zkswe-hans-common.ttf', 'sizeBytes': size}]}
        with mock.patch.object(ft, 'device_scan', lambda s, p='': (scan, '')):
            out = ft.recheck_after_deploy(DEV['serial'], 'Z21', self.tmp, delivered)
        self.assertTrue(out['consistent'])
        self.assertEqual(out['warnings'], [])
        self.assertIn('生效', out['note'])

    def test_after_deploy_recheck_skipped_without_delivery(self):
        """没投递过字体 → 不查设备（零动作，不白花一次扫描）。"""
        out = ft.recheck_after_deploy(DEV['serial'], 'Z21', self.tmp,
                                      {'applied': False, 'files': []})
        self.assertFalse(out['checked'])
        self.assertIn('无需复查', out['note'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
