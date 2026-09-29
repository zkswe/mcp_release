# -*- coding: utf-8 -*-
"""契约用例：像素基线库（ui_baseline）+ 多设备测试跑批（flythings_test_run）。

**离线**（零真机依赖）：设备相关部分靠 monkeypatch / 注入假模块，钉住的是「判据与口径」——
尤其这几条（都是「不许静默」类）：
  · 比不到基线 → `no-baseline`（**不是** pass）；尺寸不一致 → `size-mismatch`（不硬比）
  · 注入命令 rc != 0 → `error`（不是「跑完了就算过」）
  · 多台在线时 devices="auto" **不猜**；plan 写错必须回可用 action 清单
  · JUnit XML 结构（tests/failures/errors/skipped 计数与 testcase），能进 CI
"""
import json
import os
import shutil
import sys
import tempfile
import types
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import ui_baseline as ubl          # noqa: E402
import test_tools as tt            # noqa: E402

try:
    from PIL import Image
    HAS_PIL = True
except Exception:
    HAS_PIL = False


def _mkimg(path, size=(120, 80), color=(0, 0, 0, 255), patch=None):
    im = Image.new('RGBA', size, color)
    if patch:
        px = im.load()
        x0, y0, x1, y1, c = patch
        for x in range(x0, x1):
            for y in range(y0, y1):
                px[x, y] = c
    im.save(path)
    return path


@unittest.skipUnless(HAS_PIL, 'need Pillow')
class TestBaselineStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='ubl_')
        self.proj = os.path.join(self.tmp, 'proj')
        os.makedirs(self.proj)
        self.a = _mkimg(os.path.join(self.tmp, 'home.png'))
        self.b = _mkimg(os.path.join(self.tmp, 'home_b.png'), patch=(10, 10, 60, 50,
                                                                  (255, 0, 0, 255)))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_records_entry_profile_and_size(self):
        r = ubl.save(self.proj, self.a, key='home', name='首页')
        self.assertTrue(r['success'], r)
        idx = ubl.load_index(self.proj)
        e = idx['entries']['home']
        self.assertEqual(e['width'], 120)
        self.assertEqual(e['height'], 80)
        self.assertEqual(e['profile'], ubl.DEFAULT_PROFILE)      # 容差档案随基线存
        self.assertTrue(os.path.isfile(os.path.join(ubl.store_dir(self.proj), e['file'])))
        self.assertEqual(e['revision'], 1)

    def test_same_image_passes(self):
        ubl.save(self.proj, self.a, key='home')
        r = ubl.compare(self.proj, self.a, key='home')
        self.assertEqual(r['status'], 'pass', r)
        self.assertTrue(r['success'])

    def test_changed_image_fails_with_regions(self):
        ubl.save(self.proj, self.a, key='home')
        r = ubl.compare(self.proj, self.b, key='home')
        self.assertEqual(r['status'], 'fail', r)
        self.assertFalse(r['success'])
        self.assertGreaterEqual(r['regionCount'], 1)
        self.assertIn('差异', r.get('error', ''))

    def test_no_baseline_is_explicit_not_pass(self):
        r = ubl.compare(self.proj, self.a, key='never_saved')
        self.assertEqual(r['status'], 'no-baseline', r)
        self.assertFalse(r['success'])
        self.assertIn('mode=save', r.get('hint', ''))

    def test_size_mismatch_not_hard_compared(self):
        ubl.save(self.proj, self.a, key='home')
        big = _mkimg(os.path.join(self.tmp, 'home2.png'), size=(240, 160))
        r = ubl.compare(self.proj, big, key='home')
        self.assertEqual(r['status'], 'size-mismatch', r)
        self.assertIn('尺寸', r.get('error', ''))

    def test_replace_false_refuses_to_overwrite(self):
        ubl.save(self.proj, self.a, key='home')
        r = ubl.save(self.proj, self.b, key='home', replace=False)
        self.assertFalse(r['success'])
        self.assertTrue(r.get('exists'))
        self.assertEqual(ubl.load_index(self.proj)['entries']['home']['revision'], 1)

    def test_update_bumps_revision(self):
        ubl.save(self.proj, self.a, key='home')
        r = ubl.update(self.proj, self.b, key='home')
        self.assertTrue(r['success'], r)
        self.assertEqual(r['revision'], 2)
        self.assertEqual(ubl.compare(self.proj, self.b, key='home')['status'], 'pass')

    def test_allow_regions_relaxes_verdict(self):
        ubl.save(self.proj, self.a, key='home', allow_regions=1)
        r = ubl.compare(self.proj, self.b, key='home')
        self.assertEqual(r['status'], 'pass', r)          # 1 处差异在允许范围内
        r2 = ubl.compare(self.proj, self.b, key='home', allow_regions=0)
        self.assertEqual(r2['status'], 'fail', r2)        # 显式覆盖为 0 → 卡住

    def test_listing_and_missing_detection(self):
        ubl.save(self.proj, self.a, key='home')
        os.remove(os.path.join(ubl.store_dir(self.proj), 'home.png'))
        r = ubl.listing(self.proj)
        self.assertEqual(r['count'], 1)
        self.assertEqual(r['missingCount'], 1)            # 索引在、文件丢 → 显式报
        self.assertTrue(r['entries'][0]['missing'])

    def test_corrupt_index_reported(self):
        os.makedirs(ubl.store_dir(self.proj), exist_ok=True)
        with open(ubl.index_path(self.proj), 'w', encoding='utf-8') as f:
            f.write('{ not json')
        self.assertIn('indexError', ubl.load_index(self.proj))
        r = ubl.compare(self.proj, self.a, key='home')
        self.assertEqual(r['status'], 'error', r)

    def test_key_defaults_to_image_name(self):
        self.assertEqual(ubl.key_of('/x/y/首页-1.png'), '首页-1')
        self.assertEqual(ubl.key_of('/x/y/a.png', key='custom'), 'custom')


class TestPlanParsing(unittest.TestCase):
    def test_empty_plan_gives_doc(self):
        p, err = tt._load_plan('')
        self.assertIsNone(p)
        self.assertIn('steps', err)
        self.assertIn('action', tt._PLAN_DOC)

    def test_bad_action_lists_available(self):
        p, err = tt._load_plan(json.dumps({'steps': [{'action': 'blink'}]}))
        self.assertIsNone(p)
        for a in ('tap', 'shot', 'log', 'monkey'):
            self.assertIn(a, err)

    def test_plan_from_file_and_default_name(self):
        tmp = tempfile.mkdtemp(prefix='plan_')
        try:
            fp = os.path.join(tmp, 'p.json')
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump({'steps': [{'action': 'wait', 'ms': 1}]}, f)
            p, err = tt._load_plan(fp)
            self.assertIsNone(err, err)
            self.assertEqual(p['name'], 'ui-test')
            self.assertEqual(p['steps'][0]['action'], 'wait')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestDeviceSelection(unittest.TestCase):
    def setUp(self):
        self._orig = tt._adb.probe_devices
        self.online = [
            {'serial': '198.51.100.1:5555', 'model': 'Zkswe_SSD20X_SPINOR', 'platform': 'Z20',
             'state': 'device'},
            {'serial': '198.51.100.2:5555', 'model': 'Zkswe_F133_SPINOR', 'platform': 'F133',
             'state': 'device'},
        ]

    def tearDown(self):
        tt._adb.probe_devices = self._orig

    def _fake(self, online):
        tt._adb.probe_devices = lambda adb='', timeout=15, with_model=True: {
            'ok': True, 'online': online}

    def test_auto_does_not_guess_when_multiple(self):
        self._fake(self.online)
        devs, err = tt._select_devices('auto', 'adb')
        self.assertIsNone(devs)
        self.assertIn('不猜', err['error'])
        self.assertEqual(len(err['online']), 2)

    def test_auto_ok_with_single(self):
        self._fake(self.online[:1])
        devs, err = tt._select_devices('auto', 'adb')
        self.assertIsNone(err)
        self.assertEqual(len(devs), 1)

    def test_all_returns_every_online(self):
        self._fake(self.online)
        devs, err = tt._select_devices('all', 'adb')
        self.assertIsNone(err)
        self.assertEqual([d['serial'] for d in devs], ['198.51.100.1:5555', '198.51.100.2:5555'])

    def test_explicit_list_and_bare_ip(self):
        self._fake(self.online)
        devs, err = tt._select_devices('198.51.100.2,198.51.100.1:5555', 'adb')
        self.assertIsNone(err)
        self.assertEqual([d['serial'] for d in devs], ['198.51.100.2:5555', '198.51.100.1:5555'])

    def test_unknown_serial_reported(self):
        self._fake(self.online)
        devs, err = tt._select_devices('198.51.100.9:5555', 'adb')
        self.assertIsNone(devs)
        self.assertIn('不在线', err['error'])

    def test_no_device_gives_install_hint(self):
        self._fake([])
        devs, err = tt._select_devices('all', 'adb')
        self.assertIsNone(devs)
        self.assertIn('installHint', err)


class TestJunitAndSteps(unittest.TestCase):
    def test_junit_xml_escapes_quotes_in_messages(self):
        """复检 #2 抓到的真缺陷：message 里带双引号（严格模式的提示语就有）
        会把属性截断 → XML 非法（消息含 baseline="compare"）。必须转义且可被解析。"""
        devs = [{'serial': '198.51.100.7:5555', 'ok': False, 'steps': [
            {'action': 'shot', 'name': 'panel', 'status': 'no-baseline', 'ms': 3,
             'detail': {'baseline': {'strict': True},
                        'error': '基线库里没有 key=panel（baseline="compare" 为严格模式）'}},
        ], 'errors': []}]
        xml = tt._junit_xml('strict-plan', devs, {'steps': 1})
        self.assertNotIn('baseline="compare"', xml)      # 未转义的裸引号不许出现
        self.assertIn('&quot;compare&quot;', xml)
        import xml.dom.minidom as minidom
        doc = minidom.parseString(xml)                     # 能解析才是真过
        ts = doc.getElementsByTagName('testsuite')[0]
        self.assertEqual(ts.getAttribute('failures'), '1')  # 严格模式缺基线记 failure

    def test_junit_xml_counts_and_escaping(self):
        devs = [{'serial': '1.2.3.4:5555', 'ok': False, 'steps': [
            {'action': 'tap', 'name': '点按钮 <A>', 'status': 'pass', 'ms': 10},
            {'action': 'shot', 'name': '截图', 'status': 'fail', 'ms': 20,
             'detail': {'error': '与基线有 3 处差异'}},
            {'action': 'log', 'name': '日志', 'status': 'no-baseline', 'ms': 5, 'detail': {}},
        ], 'errors': []}]
        summary = {'steps': 3}
        xml = tt._junit_xml('用例 <x>', devs, summary)
        self.assertIn('tests="3"', xml)
        self.assertIn('failures="1"', xml)
        self.assertIn('skipped="1"', xml)
        self.assertIn('&lt;A&gt;', xml)                 # 必须转义
        self.assertIn('<skipped message=', xml)
        self.assertIn('<failure message=', xml)
        self.assertNotIn('<A>', xml)

    def _ctx(self):
        return {'adb': 'adb', 'serial': 'S', 'touch': '/data/touch', 'res': [480, 480],
                'shotDir': tempfile.mkdtemp(prefix='shot_'), 'baselineRoot': '',
                'baselineMode': 'off', 'allowRegions': 0}

    def tearDown(self):
        pass

    def test_injection_rc_nonzero_is_error(self):
        orig = tt._adb.shell_rc
        tt._adb.shell_rc = lambda adb, serial, cmd, timeout=15: (1, '', 'permission denied')
        try:
            r = tt._one_step({'action': 'tap', 'x': 10, 'y': 10}, 0, self._ctx())
        finally:
            tt._adb.shell_rc = orig
        self.assertEqual(r['status'], 'error', r)
        self.assertIn('注入命令失败', r['detail']['error'])

    def test_log_assertion_failure_is_fail(self):
        orig = tt._adb.shell_rc
        tt._adb.shell_rc = lambda adb, serial, cmd, timeout=15: (0, 'I/zkgui: hello', '')
        try:
            r = tt._one_step({'action': 'log', 'expectLog': ['onClick']}, 0, self._ctx())
            self.assertEqual(r['status'], 'fail', r)
            self.assertIn('没出现', r['detail']['error'])
            r2 = tt._one_step({'action': 'log', 'lines': 50, 'expectNoLog': ['FATAL']}, 1,
                              self._ctx())
            self.assertEqual(r2['status'], 'pass', r2)
        finally:
            tt._adb.shell_rc = orig

    def test_shot_without_device_screenshot_is_error(self):
        fake = types.ModuleType('device_screenshot')
        fake.capture = lambda **kw: {'success': False, 'error': '抓屏失败(测试假件)'}
        old = sys.modules.get('device_screenshot')
        sys.modules['device_screenshot'] = fake
        try:
            r = tt._one_step({'action': 'shot', 'shot': 'home'}, 0, self._ctx())
        finally:
            if old is not None:
                sys.modules['device_screenshot'] = old
            else:
                sys.modules.pop('device_screenshot', None)
        self.assertEqual(r['status'], 'error', r)
        self.assertIn('抓屏失败', r['detail']['error'])

    def test_run_step_without_script_errors(self):
        r = tt._one_step({'action': 'run'}, 0, self._ctx())
        self.assertEqual(r['status'], 'error', r)
        self.assertIn('script', r['detail']['error'])


class TestTestRunEntry(unittest.TestCase):
    def test_bad_plan_returns_plandoc(self):
        r = tt.flythings_test_run('{')
        self.assertIsInstance(r, dict)
        self.assertFalse(r.get('success'))
        self.assertIn('planDoc', r)

    def test_baseline_mode_requires_project_root(self):
        r = tt.flythings_test_run(json.dumps({'steps': [{'action': 'wait', 'ms': 1}]}),
                                  baseline='compare')
        self.assertFalse(r['success'])
        self.assertIn('project_root', r['error'])

    def test_bad_baseline_mode_rejected(self):
        r = tt.flythings_test_run(json.dumps({'steps': [{'action': 'wait', 'ms': 1}]}),
                                  baseline='whatever')
        self.assertFalse(r['success'])
        self.assertIn('auto', r['error'])


@unittest.skipUnless(HAS_PIL, 'need Pillow')
class TestPerDeviceKeysAndTolerance(unittest.TestCase):
    """复检 #2 抓到并修掉的两件事：按设备区分基线 key、按步骤放宽容差。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='pdk_')
        self.proj = os.path.join(self.tmp, 'proj')
        os.makedirs(self.proj)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake_capture(self, color=(0, 0, 0, 255), patch=None):
        mod = types.ModuleType('device_screenshot')

        def capture(**kw):
            p = kw['out']
            os.makedirs(os.path.dirname(p), exist_ok=True)
            _mkimg(p, size=(480, 480), color=color, patch=patch)
            return {'success': True}
        mod.capture = capture
        return mod

    def _ctx(self, **over):
        c = {'adb': 'adb', 'serial': '198.51.100.108:5555', 'touch': '/data/touch',
             'res': [480, 480], 'shotDir': os.path.join(self.tmp, 'shots'),
             'baselineRoot': self.proj, 'baselineMode': 'compare', 'allowRegions': 0,
             'allowSpecified': False, 'keySuffix': ''}
        c.update(over)
        return c

    def _with_fake(self, mod, fn):
        old = sys.modules.get('device_screenshot')
        sys.modules['device_screenshot'] = mod
        try:
            return fn()
        finally:
            if old is not None:
                sys.modules['device_screenshot'] = old
            else:
                sys.modules.pop('device_screenshot', None)

    def test_per_device_on_logic(self):
        self.assertTrue(tt._per_device_on('auto', 2))     # 多台 → 自动按设备区分
        self.assertFalse(tt._per_device_on('auto', 1))
        self.assertTrue(tt._per_device_on('on', 1))
        self.assertFalse(tt._per_device_on('off', 3))
        self.assertTrue(tt._per_device_on('', 3))     # 空值 = auto（多台 → 开）

    def test_dev_key_short_form(self):
        self.assertEqual(tt._dev_key('198.51.100.108:5555'), '108')
        self.assertEqual(tt._dev_key('198.51.100.71'), '71')
        self.assertTrue(tt._dev_key('ABCDEF012345'))       # USB serial → 清洗成安全 key

    def test_shot_key_includes_device_suffix(self):
        black = os.path.join(self.tmp, 'b.png')
        _mkimg(black, size=(480, 480))
        ubl.save(self.proj, black, key='panel@108')        # 基线按设备存
        mod = self._fake_capture()                         # 抓到的也是全黑
        r = self._with_fake(mod, lambda: tt._one_step({'action': 'shot', 'shot': 'panel'}, 0,
                                                     self._ctx(keySuffix='108')))
        self.assertEqual(r['status'], 'pass', r)
        self.assertEqual(r['detail']['baseline']['key'], 'panel@108')
        # 不带设备后缀 + 严格 compare → 仍然明说 no-baseline（且标 strict）
        r2 = self._with_fake(mod, lambda: tt._one_step({'action': 'shot', 'shot': 'panel'}, 0,
                                                      self._ctx(keySuffix='')))
        self.assertEqual(r2['status'], 'no-baseline', r2)
        self.assertTrue(r2['detail']['baseline']['strict'])

    def test_step_allow_regions_override(self):
        black = os.path.join(self.tmp, 'b.png')
        _mkimg(black, size=(480, 480))
        ubl.save(self.proj, black, key='k')
        mod = self._fake_capture(patch=(100, 100, 160, 160, (255, 0, 0, 255)))   # 一处差异
        r_fail = self._with_fake(mod, lambda: tt._one_step({'action': 'shot', 'shot': 'k'}, 0,
                                                          self._ctx()))
        self.assertEqual(r_fail['status'], 'fail', r_fail)
        # 活页面（时钟/温度等会自己变）→ 按步骤放宽容差
        r_ok = self._with_fake(mod, lambda: tt._one_step(
            {'action': 'shot', 'shot': 'k', 'allowRegions': 1}, 0, self._ctx()))
        self.assertEqual(r_ok['status'], 'pass', r_ok)

    def test_compare_inherits_baseline_tolerance_when_unspecified(self):
        """复检 #2 抓到的第二个真缺陷：运行级没指定容差时，**必须用基线里登记的档案**
        （以前总把 0 显式传下去，把基线里的容差覆盖掉了）。"""
        black = os.path.join(self.tmp, 'b.png')
        _mkimg(black, size=(480, 480))
        ubl.save(self.proj, black, key='k', allow_regions=1)
        mod = self._fake_capture(patch=(100, 100, 160, 160, (255, 0, 0, 255)))
        # 未指定（allowSpecified=False）→ 继承基线档案 1 → pass
        r = self._with_fake(mod, lambda: tt._one_step(
            {'action': 'shot', 'shot': 'k'}, 0,
            self._ctx(allowRegions=0, allowSpecified=False)))
        self.assertEqual(r['status'], 'pass', r)
        self.assertEqual(r['detail']['baseline']['allowRegions'], 1)
        self.assertEqual(r['detail']['baseline']['toleranceFrom'], 'baseline')
        # 显式指定 0（严格）→ fail
        r2 = self._with_fake(mod, lambda: tt._one_step(
            {'action': 'shot', 'shot': 'k'}, 0,
            self._ctx(allowRegions=0, allowSpecified=True)))
        self.assertEqual(r2['status'], 'fail', r2)
        self.assertEqual(r2['detail']['baseline']['toleranceFrom'], 'run')

    def test_report_exposes_per_device_keys_flag(self):
        orig_sel, orig_run = tt._select_devices, tt._run_on_device
        tt._select_devices = lambda devices, adb, platform='': (
            [{'serial': '1.1.1.1:5555', 'platform': 'Z20'},
             {'serial': '1.1.1.2:5555', 'platform': 'Z20'}], None)

        def _fake_run(dev, plan, adb, out_root, platform, baseline, allow, resolution,
                      dev_count=1, per_device='auto'):
            return {'serial': dev['serial'], 'ok': True, 'notes': [], 'errors': [], 'ms': 1,
                    'steps': [{'index': 1, 'name': 'w', 'action': 'wait', 'status': 'pass',
                               'ms': 1, 'detail': {}}]}
        tt._run_on_device = _fake_run
        try:
            r = tt.flythings_test_run(json.dumps({'steps': [{'action': 'wait', 'ms': 1}]}),
                                      devices='all', baseline='off',
                                      out=os.path.join(self.tmp, 'o'))
        finally:
            tt._select_devices, tt._run_on_device = orig_sel, orig_run
        self.assertTrue(r['perDeviceKeys'])
        self.assertEqual(r['summary']['devices'], 2)
        self.assertEqual(r['summary']['pass'], 2)


class TestTouchFallback(unittest.TestCase):
    """真机实测教训（Z20 /data 写满 → 注入工具推不上去）：落点必须逐级回退并自证。"""

    def test_deploy_falls_back_when_data_is_full(self):
        calls = []
        orig_push, orig_sh = tt._adb.push, tt._adb.shell_rc
        orig_elf = tt._platform_elf
        tt._platform_elf = lambda p: os.path.join(BASE, 'bin_tools', 'z20', 'touch') \
            if os.path.isfile(os.path.join(BASE, 'bin_tools', 'z20', 'touch')) else 'touch_dummy'

        def _push(adb, serial, local, remote, timeout=120):
            calls.append(remote)
            if remote.startswith('/data'):
                return 1, '', 'adb: error: failed to copy: remote No space left on device'
            return 0, '1 file pushed', ''
        tt._adb.push = _push
        tt._adb.shell_rc = lambda adb, serial, cmd, timeout=15: (0, 'proto=MT-B /dev/input/event0', '')
        try:
            notes = []
            remote, err = tt._deploy_touch('198.51.100.9:5555', 'adb', 'Z20', notes)
        finally:
            tt._adb.push, tt._adb.shell_rc = orig_push, orig_sh
            tt._platform_elf = orig_elf
        self.assertEqual(err, '', err)
        self.assertTrue(remote.startswith('/tmp'), remote)      # 回退到 tmpfs
        self.assertIn('/data', calls[0])
        self.assertTrue(any('回退' in n or '/tmp' in n for n in notes), notes)

    def test_deploy_reports_when_all_paths_fail(self):
        orig_push, orig_sh = tt._adb.push, tt._adb.shell_rc
        orig_elf = tt._platform_elf
        tt._platform_elf = lambda p: os.path.join(BASE, 'bin_tools', 'z20', 'touch') \
            if os.path.isfile(os.path.join(BASE, 'bin_tools', 'z20', 'touch')) else 'touch_dummy'
        tt._adb.push = lambda *a, **kw: (1, '', 'No space left on device')
        tt._adb.shell_rc = lambda *a, **kw: (1, '', 'x')
        try:
            remote, err = tt._deploy_touch('198.51.100.9:5555', 'adb', 'Z20', [])
        finally:
            tt._adb.push, tt._adb.shell_rc = orig_push, orig_sh
            tt._platform_elf = orig_elf
        self.assertIsNone(remote)
        self.assertIn('No space left', err)                     # 明说原因，不静默
        self.assertIn('hint', err)


if __name__ == '__main__':
    unittest.main(verbosity=2)
