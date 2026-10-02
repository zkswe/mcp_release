# -*- coding: utf-8 -*-
"""adb 单一入口 + 「launch 默认推设备」契约（v0.27.84，2026-09-17 三项要求）。

为什么要有（事故背景）：
  ① adb 定位原先在仓库里**抄了 6 份**（各写死 `'adb'` 字面量/本机 SDK 路径）→ 客户机
没装 Android SDK 就到处「找不到 adb」；现在只有 `adb_tools.resolve_adb()` 知道 adb 在哪。
  ② `build_ui_flow` 以前默认**不推设备**（with_launch=False），客户以为「编译好了」其实
设备上什么都没变；现在默认 build → 探测 → 推送/运行，只编译要显式关掉。
  ③ 探测必须**不猜**：0 台给 needDeviceInput+installHint，多台要显式 device=，
恰好 1 台且平台匹配才自动推；推完要比对设备侧产物并给 staleOnDevice。

本文件**离线**（全程 monkeypatch，不碰真机、不需要 adb 在 PATH）。
"""
import inspect
import os
import unittest
from unittest import mock

import _util as U

import adb_tools as at          # _util 已把 MCP 根目录加进 sys.path
import kb_tools
import project_tools as pt


# ----------------------------------------------------------------- adb 解析
class TestResolveAdb(unittest.TestCase):
    def test_env_var_wins(self):
        """① 环境变量 ADB 显式指定 > 其它一切（随包/ PATH 都不看）。"""
        tmp = os.path.join(U.BASE, 'tools', 'adb', 'adb.exe')
        with mock.patch.dict(os.environ, {'ADB': tmp}, clear=False):
            info = at.resolve_adb_info()
        self.assertEqual(info['path'], tmp)
        self.assertEqual(info['source'], 'env')
        self.assertEqual(info['envVar'], 'ADB')

    def test_flythings_adb_alias(self):
        """FLYTHINGS_ADB 与 ADB 等价（经需求方口径里两个都认）。"""
        tmp = os.path.join(U.BASE, 'tools', 'adb', 'adb.exe')
        env = {k: v for k, v in os.environ.items() if k not in ('ADB', 'ADB_PATH')}
        env['FLYTHINGS_ADB'] = tmp
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(at.resolve_adb(), tmp)

    def test_bundled_used_when_no_env(self):
        """② 没有环境变量时用**随包**tools/adb/adb.exe（客户不必另装 SDK）。"""
        env = {k: v for k, v in os.environ.items()
               if k not in ('ADB', 'FLYTHINGS_ADB', 'ADB_PATH')}
        with mock.patch.dict(os.environ, env, clear=True):
            info = at.resolve_adb_info()
        self.assertTrue(info['path'].replace('\\', '/').endswith('/tools/adb/adb.exe')
                        or info['path'].replace('\\', '/').endswith('/tools/adb/adb'),
                        info)
        self.assertEqual(info['source'], 'bundled')

    def test_bundled_present_in_repo(self):
        """随包三件必须在（分发完整性；别把 adb 删了还以为能用）。"""
        d = at.bundled_adb_dir()
        for f in ('adb.exe', 'AdbWinApi.dll', 'AdbWinUsbApi.dll'):
            self.assertTrue(os.path.isfile(os.path.join(d, f)), os.path.join(d, f))
        self.assertTrue(os.path.isfile(os.path.join(d, 'README.md')))

    def test_path_fallback_and_none(self):
        """③ 随包不在 → PATH；PATH 也没有 → 空串 + 可执行提示（不抛）。"""
        with mock.patch.object(at, 'bundled_adb', lambda: ''), \
                mock.patch('shutil.which', lambda n: 'C:/fake/adb.exe'):
            self.assertEqual(at.resolve_adb(), 'C:/fake/adb.exe')
        with mock.patch.object(at, 'bundled_adb', lambda: ''), \
                mock.patch('shutil.which', lambda n: None):
            self.assertEqual(at.resolve_adb(), '')
            self.assertIn('tools/adb', at.adb_missing_hint())


# ----------------------------------------------------------------- 型号/设备
class TestDeviceModelTable(unittest.TestCase):
    def test_confirmed_models_map_to_platforms(self):
        """本仓实测三个型号 → 平台（数据来源=仓库资料/实测，见 device_models.json source）。"""
        for model, plat in (('Zkswe_SSD21X_SPINOR', 'Z21'),
                            ('Zkswe_SSD20X_SPINOR', 'Z20'),
                            ('Zkswe_V85X_SPINOR', 'V85X')):
            hit = at.lookup_model(model)
            self.assertEqual(hit['platform'], plat, model)
            self.assertEqual(hit['confidence'], 'confirmed', model)
            self.assertTrue(hit['source'], '%s 缺 source（数据来源必须可追溯）' % model)

    def test_todo_models_not_guessed(self):
        """没实测的型号**不许猜**：platform 留空 + todo（F133/F136 串本仓无实测记录）。"""
        for model in ('Zkswe_F133_SPINOR', 'Zkswe_F136_SPINOR'):
            hit = at.lookup_model(model)
            self.assertEqual(hit['platform'], '', model)
            self.assertEqual(hit['confidence'], 'todo', model)

    def test_unknown_and_empty_model(self):
        self.assertEqual(at.lookup_model('SomeRandomBoard')['confidence'], 'unknown')
        self.assertEqual(at.lookup_model('')['confidence'], 'unknown')

    def test_match_platform_semantics(self):
        """match / mismatch / unknown（未知 ≠ 不匹配：fun 自己会做平台校验）。"""
        self.assertEqual(at.match_platform('Zkswe_SSD21X_SPINOR', 'Z21'), 'match')
        self.assertEqual(at.match_platform('Zkswe_SSD21X_SPINOR', 'Z20'), 'mismatch')
        self.assertEqual(at.match_platform('Zkswe_SSD20X_SPINOR', 'z20'), 'match')
        self.assertEqual(at.match_platform('Zkswe_F133_SPINOR', 'F133'), 'unknown')
        self.assertEqual(at.match_platform('', 'Z21'), 'unknown')

    def test_no_ip_in_model_table(self):
        """型号表只放型号串——不许带内网 IP/序列号（隐私闸门同口径）。"""
        import io
        import json
        import re
        d = json.load(io.open(at.MODELS_JSON, encoding='utf-8'))
        blob = json.dumps(d, ensure_ascii=False)
        self.assertFalse(re.search(r'\b\d{1,3}(\.\d{1,3}){3}\b', blob), '型号表里出现了 IP')

    def test_parse_devices_l(self):
        """`adb devices -l` 解析：USB（带 model）/ 网络（不带）/ offline 都要认。"""
        txt = ('List of devices attached\n'
               '20080411\tdevice product:swaio model:Zkswe_V85X_SPINOR device:swaio transport_id:4\n'
               '<IP>:5555\tdevice transport_id:31\n'
               'ABCDEF\tunauthorized\n'
               '\n')
        devs = at.parse_devices_l(txt)
        self.assertEqual(len(devs), 3)
        self.assertEqual(devs[0]['model'], 'Zkswe_V85X_SPINOR')
        self.assertEqual(devs[1]['serial'], '<IP>:5555')
        self.assertEqual(devs[1]['model'], '')
        self.assertEqual(devs[2]['state'], 'unauthorized')


class TestProbeAndHints(unittest.TestCase):
    def _fake_run(self, out, rc=0):
        def f(args, timeout=15):
            if args[1:2] == ['version']:
                return 0, 'Android Debug Bridge version 1.0.41\nVersion 31.0.3-7562133\n', ''
            if args[1:3] == ['devices', '-l']:
                return rc, out, ''
            if args[1:3] == ['start-server'] or args[1:2] == ['start-server']:
                return 0, '', ''
            if 'shell' in args:                       # getprop ro.product.model
                return 0, 'Zkswe_SSD21X_SPINOR\n', ''
            return 0, '', ''
        return f

    def test_probe_fills_model_via_getprop_and_maps_platform(self):
        """网络设备 `devices -l` 不带 model → 用 getprop 补，并给出平台判定。"""
        out = ('List of devices attached\n<IP>:5555\tdevice transport_id:31\n')
        with mock.patch.object(at, '_run', self._fake_run(out)):
            pr = at.probe_devices()
        self.assertTrue(pr['ok'], pr)
        self.assertEqual(pr['count'], 1)
        self.assertEqual(pr['online'][0]['model'], 'Zkswe_SSD21X_SPINOR')
        self.assertEqual(pr['online'][0]['modelSource'], 'getprop')
        self.assertEqual(pr['online'][0]['platform'], 'Z21')

    def test_install_hint_covers_three_things(self):
        """installHint 必须覆盖三件事：ADB 驱动 / USB 调试授权 / 网络接入（要求）。"""
        txt = at.install_hint('Z21')
        self.assertIn('ADB 驱动', txt)
        self.assertIn('USB', txt)
        self.assertIn('device=', txt)
        self.assertIn('Z21', txt)

    def test_multi_device_hint_lists_and_refuses_to_guess(self):
        devs = [{'serial': 'A', 'model': 'Zkswe_SSD21X_SPINOR', 'platform': 'Z21'},
                {'serial': 'B', 'model': 'Zkswe_SSD20X_SPINOR', 'platform': 'Z20'}]
        txt = at.multi_device_hint(devs, 'Z21')
        self.assertIn('A', txt)
        self.assertIn('B', txt)
        self.assertIn('不自动选择', txt)
        self.assertIn('device=', txt)

    def test_stale_hint_names_both_causes(self):
        txt = at.stale_hint([{'name': 'main.ftu', 'devicePath': '/tmp/ui/main.ftu',
                              'localBytes': 10, 'deviceBytes': 20, 'localMd5': 'A' * 32,
                              'deviceMd5': 'B' * 32, 'reason': 'md5 不一致'}])
        self.assertIn('旧版', txt)
        self.assertIn('pack', txt)

    def test_remote_file_info_uses_ls_l_column5(self):
        """设备侧取数（真机踩到的 bug）：`ls -l` 第 1 个数字是硬链接数（恒为 1），
第 5 列才是字节数；且裁剪 rootfs 的 `wc -c` 返回空、没有 md5sum。"""
        txt = ('-rw-rw-rw-    1 0        0              186 Sep 17  2026 main.ftu\n')
        with mock.patch.object(at, 'sh', lambda a, s, cmd, timeout=15: txt), \
                mock.patch.object(at, 'ensure_busybox', lambda a, s, p='', timeout=15: ''):
            got = at.remote_file_info('', 'dev', '/tmp/ui/main.ftu')
        self.assertEqual(got['size'], 186, got)          # 不是 1（硬链接数）
        self.assertEqual(got['md5'], '')

    def test_remote_file_info_wc_and_md5(self):
        """有 wc/md5sum 的设备：裸数字 = 尺寸，32 位 hex = md5（两边都有时优先比 md5）。"""
        md5 = 'A' * 32
        txt = '186\n%s  main.ftu\n' % md5
        with mock.patch.object(at, 'sh', lambda a, s, cmd, timeout=15: txt):
            got = at.remote_file_info('', 'dev', '/tmp/ui/main.ftu')
        self.assertEqual(got['size'], 186)
        self.assertEqual(got['md5'], md5)

    def test_fun_multi_device_error_recognized(self):
        """fun 多设备硬失败的识别（2026-09-17 报文级实测）：要给出可照做的处置，不是笼统「掉线」。"""
        out = ('font: \nFATAL "host:transport <serial>" FAIL: more than one device/emulator\n')
        hint = at.fun_multi_device_error(out)
        self.assertIn('disconnect', hint)
        self.assertIn('host:transport', hint)
        self.assertEqual(at.fun_multi_device_error('FATAL platform not match'), '')

    def test_compare_with_device_md5_and_size(self):
        """能拿 md5 比 md5；设备端没有 md5sum 时退化为比字节数（不假装一致）。"""
        import tempfile
        tmp = tempfile.mkdtemp(prefix='mcp_adb_test_')
        p = os.path.join(tmp, 'main.ftu')
        U.write(p, 'x' * 32)
        md5 = at.local_md5(p)
        with mock.patch.object(at, 'remote_file_info',
                               lambda a, s, path, platform='', timeout=15: {'size': 32, 'md5': md5, 'error': ''}):
            r = at.compare_with_device('', 'dev', p, '/tmp/ui/main.ftu')
        self.assertTrue(r['same'], r)
        with mock.patch.object(at, 'remote_file_info',
                               lambda a, s, path, platform='', timeout=15: {'size': 31, 'md5': '', 'error': ''}):
            r = at.compare_with_device('', 'dev', p, '/tmp/ui/main.ftu')
        self.assertFalse(r['same'])
        self.assertIn('字节', r['reason'])
        U.cleanup(tmp)


# ------------------------------------------- build_ui_flow 默认推设备（端点）
MF_OK = ('<?xml version="1.0" encoding="UTF-8"?>\n'
         '<manifest platform="Z21">\n'
         '    <dependencies enableOnPlatforms="Z21">\n'
         '        <package id="base-utility" version="^10.0.0"/>\n'
         '    </dependencies>\n'
         '</manifest>\n')


def _fake_fun(cmd, project_dir, **kw):
    return {'success': True, 'returncode': 0, 'stdout': '%s ok' % cmd, 'stderr': ''}


def _gate(need=False, serial='', model='', match='', hint=''):
    return {'needDeviceInput': need, 'serial': serial, 'model': model,
            'platformMatch': match, 'installHint': hint, 'message': 'msg',
            'devices': ([{'serial': serial, 'model': model, 'platform': 'Z21',
                          'modelConfidence': 'confirmed', 'state': 'device'}] if serial else []),
            'offline': [], 'adb': 'tools/adb/adb.exe', 'adbSource': 'bundled',
            'explicit': False, 'connectNote': '', 'count': 1 if serial else 0}


def _sync(stale=False):
    c = {'name': 'main.ftu', 'kind': 'ftu', 'localPath': 'a', 'devicePath': '/tmp/ui/main.ftu',
         'localBytes': 100, 'deviceBytes': 200 if stale else 100,
         'localMd5': 'A' * 32, 'deviceMd5': 'B' * 32 if stale else 'A' * 32,
         'same': not stale, 'reason': 'md5 不一致' if stale else ''}
    return {'checked': True, 'allMatch': not stale, 'stale': ([c] if stale else []),
            'ftu': [c], 'so': [], 'reason': ''}


class TestBuildFlowLaunchDefault(unittest.TestCase):
    """默认 with_launch=True：探测 → 推送 → 比对设备侧产物。"""

    def setUp(self):
        self.tmp = U.project()

    def tearDown(self):
        U.cleanup(self.tmp)

    def _run(self, extra=None, gate=None, sync=None, with_launch=None):
        U.write(os.path.join(self.tmp, 'Manifest.xml'), MF_OK)
        os.makedirs(os.path.join(self.tmp, 'ui'), exist_ok=True)
        page = os.path.join(self.tmp, 'ui', 'main.json')
        U.write(page, '{}')
        ftu = os.path.join(self.tmp, 'ui', 'main.ftu')
        open(ftu, 'wb').write(b'ZKSR')
        os.utime(ftu, (os.path.getmtime(page) + 1,) * 2)
        args = {'project_root': self.tmp}
        if extra:
            args.update(extra)
        if with_launch is not None:
            args['with_launch'] = with_launch
        patches = [mock.patch.object(pt, '_run_fun', _fake_fun)]
        if gate is not None:
            patches.append(mock.patch.object(pt, '_launch_gate', lambda p, d: gate))
        if sync is not None:
            patches.append(mock.patch.object(pt, '_device_sync_check',
                                             lambda root, serial, plat: sync))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return U.jcall('flythings_build_ui_flow', args)

    def test_default_is_true_in_both_signatures(self):
        """默认值口径：pt 与 kb 包装层都必须是 True（否则 AI 拿到的是旧行为）。"""
        for fn in (pt.flythings_build_ui_flow, kb_tools.flythings_build_ui_flow):
            self.assertIs(inspect.signature(fn).parameters['with_launch'].default, True,
                          fn.__module__)

    def test_no_device_returns_install_hint(self):
        """0 台设备 → needDeviceInput + installHint（覆盖驱动/USB调试/网络接入三件事）。"""
        r = self._run(gate=_gate(need=True, hint=at.install_hint('Z21')))
        self.assertFalse(r['ok'])
        self.assertTrue(r['needDeviceInput'])
        self.assertIn('ADB 驱动', r['installHint'])
        self.assertIn('device=', r['installHint'])
        self.assertEqual(r['staleOnDevice'], False)
        self.assertTrue([s for s in r['steps'] if s['step'] == 'device_probe' and not s['success']])

    def test_single_matching_device_launches_and_syncs(self):
        """1 台且平台匹配 → launch -s <serial>；返回体写清 launched/pushed/device/model。"""
        seen = {}

        def fake_fun(cmd, project_dir, **kw):
            seen.setdefault(cmd, []).append(kw.get('device'))
            return {'success': True, 'returncode': 0, 'stdout': 'ok', 'stderr': ''}

        with mock.patch.object(pt, '_run_fun', fake_fun), \
                mock.patch.object(pt, '_launch_gate',
                                  lambda p, d: _gate(serial='S1', model='Zkswe_SSD21X_SPINOR',
                                                     match='match')), \
                mock.patch.object(pt, '_device_sync_check', lambda root, s, p: _sync(False)):
            r = self._run_free()
        self.assertTrue(r['ok'], r)
        self.assertTrue(r['launched'] and r['pushed'])
        self.assertEqual(r['device'], 'S1')
        self.assertEqual(r['model'], 'Zkswe_SSD21X_SPINOR')
        self.assertEqual(r['platformMatch'], 'match')
        self.assertFalse(r['staleOnDevice'])
        self.assertEqual(seen.get('launch'), ['S1'], 'launch 必须带 -s <serial>')

    def _run_free(self):
        """同上但不预置 gate/sync patch（由调用方自己 patch）。"""
        U.write(os.path.join(self.tmp, 'Manifest.xml'), MF_OK)
        os.makedirs(os.path.join(self.tmp, 'ui'), exist_ok=True)
        page = os.path.join(self.tmp, 'ui', 'main.json')
        U.write(page, '{}')
        ftu = os.path.join(self.tmp, 'ui', 'main.ftu')
        open(ftu, 'wb').write(b'ZKSR')
        os.utime(ftu, (os.path.getmtime(page) + 1,) * 2)
        return U.jcall('flythings_build_ui_flow', {'project_root': self.tmp})

    def test_stale_on_device_flagged(self):
        """设备侧与本地不一致 → staleOnDevice=true + warnings 点明「设备上跑的还是旧版」。"""
        r = self._run(gate=_gate(serial='S1', model='Zkswe_SSD21X_SPINOR', match='match'),
                      sync=_sync(True))
        self.assertTrue(r['ok'], r)
        self.assertTrue(r['staleOnDevice'])
        self.assertFalse(r['deviceSync']['allMatch'])
        self.assertEqual(r['deviceSync']['ftu'][0]['localBytes'], 100)
        self.assertEqual(r['deviceSync']['ftu'][0]['deviceBytes'], 200)
        w = ' '.join(r.get('warnings', []))
        self.assertIn('旧版', w)

    def test_with_launch_false_does_not_touch_device(self):
        """保守开关：with_launch=False → 不探测、不 launch，返回体标明 skipped。"""
        called = {'n': 0}

        def boom(p, d):
            called['n'] += 1
            raise AssertionError('with_launch=False 时不该探测设备')

        with mock.patch.object(pt, '_launch_gate', boom):
            r = self._run(with_launch=False)
        self.assertTrue(r['ok'], r)
        self.assertFalse(r['launched'])
        self.assertFalse(r['pushed'])
        self.assertTrue(r['launchSkipped'])
        self.assertEqual(r['device'], '')
        self.assertEqual(called['n'], 0)
        self.assertTrue([s for s in r['steps'] if s['step'] == 'fun launch'
                         and s.get('skipped')])


if __name__ == '__main__':
    unittest.main(verbosity=2)
