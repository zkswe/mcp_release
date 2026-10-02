# -*- coding: utf-8 -*-
"""设备侧探针的契约用例（**离线**，不接真机：把设备返回文本喂进去，验解析与判定）。

设备返回样本（2026-10-02，Zkswe_SSD20X_SPINOR）都固化在这里当样本：
- `/proc` 里 GUI 进程 comm 是 `zkgui_ui`，命令行是 `/bin/zkgui`
- 设备 shell 是裁剪版：**没有 grep / head / sleep**，`ls` 输出还带 ANSI 颜色
- fb 读取超时回 rc=124；`/dev/sstarfb`、`/dev/mi_disp` 读会 `Invalid argument`；
  `/proc/mi_modules/mi_disp/mi_disp0` 有 `IrqCnt` 显示中断计数
- 框架**不打印 `onUI_show`**，但会打 `registerActivity name: mainActivity OK!`
"""
import io
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import device_probes as dp                                     # noqa: E402


PS_SAMPLE = """PID   USER     TIME  COMMAND
    1 0         0:00 /sbin/init
  860 0         0:10 /bin/adbd
 1187 0         1h00 {zkgui_ui} /bin/zkgui
 2478 0         0:00 /tmp/busybox dd if /dev/fb0 bs 1920 count 4
"""

STAT_SAMPLE = ("1187 (zkgui_ui) S 1 1187 0 0 -1 4194560 18663 0 3458 0 279653 84677 "
               "0 0 20 0 19 0 924558 203415552 3234 4294967295")


class TestStripAnsi(unittest.TestCase):
    def test_ls_color_is_stripped(self):
        raw = '\x1b[1;35mfb0\x1b[m \x1b[1;35msstarfb\x1b[m'
        self.assertEqual(dp._strip_ansi(raw).split(), ['fb0', 'sstarfb'])


class FakeAdb:
    """假 adb：shell_rc 按命令前缀回预设值；用于验 fb_probe 的三条分支。"""

    def __init__(self, rc=0, out='', err='', size=0, md5=''):
        self._rc, self._out, self._err = rc, out, err
        self._size, self._md5 = size, md5

    def resolve_adb(self):
        return 'adb'

    def shell_rc(self, _adb, _serial, cmd, timeout=None):
        if 'wc -c' in cmd:
            return self._rc, self._out, self._err
        return 1, '', ''

    def remote_file_info(self, _adb, _serial, path, platform='', timeout=None):
        return {'size': self._size, 'md5': self._md5, 'error': ''}

    def ensure_busybox(self, *_a, **_k):
        return '/tmp/busybox'

    def raw(self, *_a, **_k):
        return 0, '', ''


class TestFbProbe(unittest.TestCase):
    """fb 探针的核心契约：**有界**、且能把三条失败形态分开。"""

    def setUp(self):
        self._orig = dp._adb
        self._orig_bb = dp.busybox
        dp.busybox = lambda *_a, **_k: '/tmp/busybox'

    def tearDown(self):
        dp._adb = self._orig
        dp.busybox = self._orig_bb

    def test_readable_node_reports_bytes(self):
        dp._adb = lambda: FakeAdb(out='16\n')
        r = dp.fb_probe('dev:5555')
        self.assertTrue(r['ok'])
        self.assertEqual(r['bytes'], 16)
        self.assertFalse(r['blocked'])

    def test_blocked_node_is_reported_not_raised(self):
        dp._adb = lambda: FakeAdb(rc=124)          # _run 的超时约定
        r = dp.fb_probe('dev:5555')
        self.assertTrue(r['blocked'])
        self.assertFalse(r['ok'])
        self.assertIn('无响应', r['error'])

    def test_error_text_is_not_counted_as_bytes(self):
        """**踩过的坑**：把 dd 的 stderr 并进 `wc -c`，错误信息长度会被当成「读到了」。"""
        dp._adb = lambda: FakeAdb(rc=0, out='', err='dd: /dev/sstarfb: Invalid argument')
        r = dp.fb_probe('dev:5555')
        self.assertFalse(r['ok'])
        self.assertEqual(r['bytes'], 0)

    def test_probe_timeout_is_small_and_passed_through(self):
        """fb 探针必须**短超时**（先定生死，不把时间耗在等待上）。"""
        self.assertLessEqual(dp.FB_OPEN_TIMEOUT, 10)
        seen = {}

        class Spy(FakeAdb):
            def shell_rc(self, _a, _s, cmd, timeout=None):
                seen['timeout'] = timeout
                return 0, '0\n', ''

        dp._adb = lambda: Spy()
        dp.fb_probe('dev:5555', timeout=3)
        self.assertEqual(seen['timeout'], 3)


class TestPsParsing(unittest.TestCase):
    def setUp(self):
        self._orig_sh = dp.sh
        self._orig_bb = dp.busybox
        dp.busybox = lambda *_a, **_k: '/tmp/busybox'
        dp.sh = lambda serial, cmd, timeout=None: (
            STAT_SAMPLE if cmd.startswith('cat /proc/1187/stat') else PS_SAMPLE)

    def tearDown(self):
        dp.sh = self._orig_sh
        dp.busybox = self._orig_bb

    def test_gui_name_and_state(self):
        rows, err = dp.ps_table('dev:5555')
        self.assertEqual(err, '')
        hit = [r for r in rows if r['name'] == 'zkgui_ui']
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0]['state'], 'S')

    def test_liveness_alive(self):
        self.assertEqual(dp.gui_liveness('dev:5555')['verdict'], 'alive')


class TestLaunchEvidence(unittest.TestCase):
    """launch 活性：实测框架**不打印 onUI_show**，强判据要用 registerActivity。"""

    def setUp(self):
        self._orig_sh = dp.sh

    def tearDown(self):
        dp.sh = self._orig_sh

    def _feed(self, text):
        dp.sh = lambda serial, cmd, timeout=None: text

    def test_strong_marker_register_activity(self):
        self._feed('D/zkgui   ( 1187): registerActivity name: mainActivity OK!\n')
        r = dp.launch_evidence('dev:5555', wait=0)
        self.assertEqual(r['tier'], 'strong')
        self.assertTrue(r['ok'])
        self.assertEqual(r['marker'], 'registerActivity name:')

    def test_weak_only_marks_weak(self):
        self._feed('E/zkgui   ( 1187): initEasyUICfg ok!\n')
        r = dp.launch_evidence('dev:5555', wait=0)
        self.assertEqual(r['tier'], 'weak')

    def test_nothing_seen_is_none(self):
        self._feed('D/zknet whatever\n')
        r = dp.launch_evidence('dev:5555', wait=0)
        self.assertEqual(r['tier'], 'none')
        self.assertFalse(r['ok'])


class TestPanelAndTarget(unittest.TestCase):
    def setUp(self):
        self._orig_sh = dp.sh
        self._orig_bb = dp.busybox
        dp.busybox = lambda *_a, **_k: '/tmp/busybox'

    def tearDown(self):
        dp.sh = self._orig_sh
        dp.busybox = self._orig_bb

    def test_panel_info_splits_digits_and_width(self):
        def fake(serial, cmd, timeout=None):
            if 'virtual_size' in cmd:
                return '480,1440'
            if 'stride' in cmd:
                return '1920'
            if 'bits_per_pixel' in cmd:
                return '32'
            if 'name' in cmd:
                return 'SStar FB0'
            if 'ls /dev' in cmd:
                return '\x1b[1;35mfb0\x1b[m mdisp sstarfb'
            if 'mi_disp0' in cmd:
                return (' DevStatus         IrqNum         IrqCnt        BgColor\n'
                        '         0             56        2715822         800080\n')
            return ''
        dp.sh = fake
        pi = dp.panel_info('dev:5555')
        self.assertEqual(pi['visibleWidth'], 480)
        self.assertEqual(pi['virtualHeight'], 1440)     # 缓冲区高，不是面板高
        self.assertEqual(pi['dispIrq'], 2715822)
        self.assertIn('fb0', pi['nodes'])

    def test_hw_target_uses_fb_width_to_split(self):
        dp.sh = lambda serial, cmd, timeout=None: 'D/zkhardware( 1187): para target: RGB_LCD480480\n'
        self.assertEqual(dp.hw_panel_target('dev:5555', 480)['resolution'], '480x480')

    def test_hw_target_without_width_does_not_guess(self):
        dp.sh = lambda serial, cmd, timeout=None: 'D/zkhardware( 1187): para target: RGB_LCD480480\n'
        self.assertEqual(dp.hw_panel_target('dev:5555', None)['resolution'], '')


class TestEasyuiRuntime(unittest.TestCase):
    def test_firmware_and_running_lib_are_separate(self):
        """固件版本与**实际在跑**的库必须分开报（launch 推的是 app 侧库，不改固件）。"""
        orig_sh, orig_adb = dp.sh, dp._adb
        dp.sh = lambda serial, cmd, timeout=None: '2.2.0\nflythingsV2.1\nZkswe_SSD20X_SPINOR'
        dp._adb = lambda: FakeAdb(size=2621364, md5='C34F0BB2F8D7D1A3F697AEBB621066F3')
        try:
            r = dp.easyui_runtime('dev:5555', 'Z20')
            self.assertEqual(r['firmwareVersion'], '2.2.0')
            self.assertEqual(r['model'], 'Zkswe_SSD20X_SPINOR')
            self.assertEqual(r['runningLib']['path'], '/tmp/lib/libzkgui.so')
        finally:
            dp.sh, dp._adb = orig_sh, orig_adb


class TestProjectEasyuiRevision(unittest.TestCase):
    """工程侧 easyui 版本的来源顺序（`.fsc-lock.json` → 旧锁名 → `.deps.lock` → Manifest 范围）。"""

    def _mk(self, files):
        import tempfile
        d = tempfile.mkdtemp(prefix='fyproj_')
        for name, text in files.items():
            with io.open(os.path.join(d, name), 'w', encoding='utf-8') as fh:
                fh.write(text)
        return d

    def test_fsc_lock_wins(self):
        import project_tools as pt
        d = self._mk({'.fsc-lock.json':
                      '{"dependencies": {"Z20": {"easyui": {"version": "^2.2.0",'
                      ' "revision": "2.6.0"}}}}'})
        self.assertEqual(pt._project_easyui_revision(d), ('2.6.0', '.fsc-lock.json'))

    def test_deps_lock_fallback(self):
        import project_tools as pt
        d = self._mk({'.deps.lock': '{"dependencies": [{"id": "easyui", "version": "^2.2.0",'
                                    ' "revision": "2.4.0"}]}'})
        self.assertEqual(pt._project_easyui_revision(d), ('2.4.0', '.deps.lock'))

    def test_nothing_found_returns_empty_not_guess(self):
        import project_tools as pt
        d = self._mk({})
        self.assertEqual(pt._project_easyui_revision(d), ('', ''))


class TestReadResolutionSingleSource(unittest.TestCase):
    """分辨率解析**唯一实现**在 project_tools.read_resolution，translate_tools 只转调。"""

    def test_prefs_wins_over_ui_json(self):
        import json
        import tempfile
        import project_tools as pt
        d = tempfile.mkdtemp(prefix='fyres_')
        os.makedirs(os.path.join(d, '.settings'))
        os.makedirs(os.path.join(d, 'ui'))
        with io.open(os.path.join(d, '.settings', 'com.zksw.flythings.easyui.prefs'), 'w',
                     encoding='utf-8') as fh:
            fh.write('resolution=480x480\n')
        with io.open(os.path.join(d, 'ui', 'main.json'), 'w', encoding='utf-8') as fh:
            fh.write(json.dumps({'resolution': {'width': 1024, 'height': 600}}))
        self.assertEqual(pt.read_resolution(d), '480x480')

    def test_translate_tools_delegates(self):
        import tempfile
        import translate_tools as tt
        self.assertEqual(tt._project_resolution(''), '')
        self.assertEqual(tt._project_resolution(tempfile.mkdtemp(prefix='fyempty_')), '')


if __name__ == '__main__':
    unittest.main(verbosity=2)
