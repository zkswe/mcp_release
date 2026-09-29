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
            {'serial': '10.0.0.1:5555', 'model': 'Zkswe_SSD20X_SPINOR', 'platform': 'Z20',
             'state': 'device'},
            {'serial': '10.0.0.2:5555', 'model': 'Zkswe_F133_SPINOR', 'platform': 'F133',
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
        self.assertEqual([d['serial'] for d in devs], ['10.0.0.1:5555', '10.0.0.2:5555'])

    def test_explicit_list_and_bare_ip(self):
        self._fake(self.online)
        devs, err = tt._select_devices('10.0.0.2,10.0.0.1:5555', 'adb')
        self.assertIsNone(err)
        self.assertEqual([d['serial'] for d in devs], ['10.0.0.2:5555', '10.0.0.1:5555'])

    def test_unknown_serial_reported(self):
        self._fake(self.online)
        devs, err = tt._select_devices('10.0.0.9:5555', 'adb')
        self.assertIsNone(devs)
        self.assertIn('不在线', err['error'])

    def test_no_device_gives_install_hint(self):
        self._fake([])
        devs, err = tt._select_devices('all', 'adb')
        self.assertIsNone(devs)
        self.assertIn('installHint', err)


class TestJunitAndSteps(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
