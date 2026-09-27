# -*- coding: utf-8 -*-
"""device_screenshot 的 busybox 能力探测 + 远程体积解析（离线，monkeypatch 掉 adb）

回归背景（2026-09-13 真机 SSD20X / SSD21X 踩到）：
  设备自带 `/bin/busybox` 是裁剪版——**有 echo、没有 gzip**。旧版探测只测 `echo ok`
  → 选中系统 busybox → `gzip: applet not found` → 远程文件 0 字节 → 抓屏报
  「raw 数据不足 … 实际 0 字节」（把真因吞了，误导排查方向）。
  修法：探测必须验证 **gzip 真的能用**；设备上没有就从本仓 bin_tools 自动推一个；
  实在没有压缩通道就退化为「只读可见帧的裸数据」。
"""
import os
import unittest

import _util  # noqa: F401  （设置 sys.path：BASE + ui_tools + tests）
import device_screenshot as ds


def _fake_sh(rules):
    """按子串匹配返回预设结果，模拟 adb shell"""
    def _sh(adb, dev, cmd, timeout=30):
        for key, val in rules.items():
            if key in cmd:
                return val
        return ''
    return _sh


class PickBusybox(unittest.TestCase):
    def setUp(self):
        self.orig_sh = ds._sh
        self.orig_cands = ds._local_busybox_candidates

    def tearDown(self):
        ds._sh = self.orig_sh
        ds._local_busybox_candidates = self.orig_cands

    def test_skip_busybox_without_gzip(self):
        """系统 busybox 有 echo 没 gzip → 不能选中；没有候选就如实返回空 + 写明原因"""
        ds._local_busybox_candidates = lambda: []      # 模拟「本仓 busybox 也推不上去」
        ds._sh = _fake_sh({'/tmp/busybox gzip': 'sh: not found',
                           'busybox gzip': 'gzip: applet not found'})
        notes = []
        self.assertEqual(ds._pick_busybox('adb', 'dev', notes), '')
        self.assertTrue(any('gzip' in n for n in notes), notes)

    def test_pick_tmp_busybox_with_gzip(self):
        """/tmp/busybox（我们推的完整版）gzip 可用 → 选中它，且不再探测后面的候选"""
        ds._sh = _fake_sh({'/tmp/busybox gzip': 'rc=0'})
        notes = []
        self.assertEqual(ds._pick_busybox('adb', 'dev', notes), '/tmp/busybox')


class RemoteSize(unittest.TestCase):
    def setUp(self):
        self.orig_sh = ds._sh

    def tearDown(self):
        ds._sh = self.orig_sh

    def test_wc_c(self):
        ds._sh = _fake_sh({'wc -c': '37000'})
        self.assertEqual(ds._remote_size('adb', 'dev', '/tmp/x'), 37000)

    def test_ls_busybox_format(self):
        """busybox ls -l：perms links owner group size month day time name"""
        ds._sh = _fake_sh({'wc -c': '',
                           'ls -l': '-rw-rw-rw-    1 0        0            37000 Sep 13 04:01 /tmp/x'})
        self.assertEqual(ds._remote_size('adb', 'dev', '/tmp/x'), 37000)

    def test_ls_device_format(self):
        """设备自带 ls -l：perms owner group size date time name（字段数不同）"""
        ds._sh = _fake_sh({'wc -c': '',
                           'ls -l': '-rwx------ 1000     1000      2581836 Sep 13  2026 /tmp/x'})
        self.assertEqual(ds._remote_size('adb', 'dev', '/tmp/x'), 2581836)

    def test_ls_iso_date_format(self):
        """V85X 实测：ls -l 打 ISO 日期（无英文月）→ 旧“月份锤点”会解成 0，
        导致“gzip 已压到 69KB”被误判为未压缩 → 白退化成裸帧。"""
        ds._sh = _fake_sh({'wc -c': '', 'stat -c': '',
                           'ls -l': '-rw-rw-rw- 0        0           69416 1970-01-01 01:10 /tmp/x'})
        self.assertEqual(ds._remote_size('adb', 'dev', '/tmp/x'), 69416)

    def test_stat_fallback(self):
        """wc 不可用时走 stat -c %s"""
        ds._sh = _fake_sh({'wc -c': '', 'stat -c': '12345'})
        self.assertEqual(ds._remote_size('adb', 'dev', '/tmp/x'), 12345)


class MiVideoFrame(unittest.TestCase):
    """视频层（SigmaStar MI）解码与路由（离线）"""

    def test_fmt_map(self):
        self.assertEqual(ds.MI_FMT[11], 'yuv420sp')
        self.assertEqual(ds.MI_FMT[0], 'yuyv422')

    def test_decode_nv12_gray(self):
        """Y=100, U=V=128 → 近似中灰；尺寸与像素值要对"""
        w = h = 4
        raw = bytes([100]) * (w * h) + bytes([128]) * (w * h // 2)
        img, conv = ds.decode_frame(raw, w, h, w, 11)
        self.assertEqual(img.size, (w, h))
        self.assertIn('yuv420sp', conv)
        r, g, b = img.getpixel((0, 0))
        for v in (r, g, b):
            self.assertAlmostEqual(v, 100, delta=8)

    def test_unknown_fmt_raises(self):
        with self.assertRaises(ValueError):
            ds.decode_frame(b'\x00' * 16, 2, 2, 2, 99)

    def test_capture_mi_video_route(self):
        """layer='video' → 走 zkshot 路，解析帧信息并落盘"""
        import tempfile
        orig_sh, orig_run, orig_ensure = ds._sh, ds._run, ds._ensure_zkshot
        orig_pick, orig_adb = ds.pick_device, ds.find_adb
        tmp = tempfile.mkdtemp()
        out = os.path.join(tmp, 'v.png')

        def fake_sh(adb, dev, cmd, timeout=30):
            if 'zkshot' in cmd and 'vdec' in cmd:
                return '[vdec] W=4 H=4 fmt=11 stride0=4 stride1=4 bufsize=24 phy0=0x1000'
            return ''

        def fake_run(args, timeout=60, binary=False):
            if 'pull' in args:
                with open(args[-1], 'wb') as f:
                    f.write(bytes([100]) * 16 + bytes([128]) * 8)
                return 0, '', ''
            return 0, '', ''

        try:
            ds._sh, ds._run = fake_sh, fake_run
            ds._ensure_zkshot = lambda adb, dev, notes: '/tmp/zkshot'
            ds.pick_device = lambda adb, device='': ('dev', '')
            ds.find_adb = lambda: 'adb'
            r = ds.capture_mi_video(device='dev', out=out)
            self.assertTrue(r['success'], r)
            self.assertEqual(r['method'], 'zkshot-vdec')
            self.assertEqual((r['width'], r['height']), (4, 4))
            self.assertEqual(r['frame']['fmtName'], 'yuv420sp')
            self.assertTrue(os.path.isfile(out))
        finally:
            ds._sh, ds._run, ds._ensure_zkshot = orig_sh, orig_run, orig_ensure
            ds.pick_device, ds.find_adb = orig_pick, orig_adb

    # ---- vdec 通道号（2026-09-27 实测缺陷：拼墙在 chn 1，工具写死 chn 0 抓不到帧）----

    def _stub_capture(self, out, frame_line, chn=0):
        """把 capture_mi_video 的 adb 依赖全部换成假的；返回 (r, calls)"""
        calls = []

        def fake_sh(adb, dev, cmd, timeout=30):
            calls.append(cmd)
            if 'vdec' in cmd:
                return frame_line
            return ''

        def fake_run(args, timeout=60, binary=False):
            if 'pull' in args:
                with open(args[-1], 'wb') as f:
                    f.write(bytes([100]) * 16 + bytes([128]) * 8)
            return 0, '', ''

        self._orig = (ds._sh, ds._run, ds._ensure_zkshot, ds.pick_device, ds.find_adb)
        ds._sh, ds._run = fake_sh, fake_run
        ds._ensure_zkshot = lambda adb, dev, notes: '/tmp/zkshot'
        ds.pick_device = lambda adb, device='': ('dev', '')
        ds.find_adb = lambda: 'adb'
        r = ds.capture_mi_video(device='dev', out=out, vdec_chn=chn)
        return r, calls

    def _unstub(self):
        (ds._sh, ds._run, ds._ensure_zkshot,
         ds.pick_device, ds.find_adb) = self._orig

    def test_vdec_chn_default_is_chn0(self):
        """默认值必须是 0（不改变历史行为）：zkshot 命令行 = vdec 0 0"""
        import tempfile
        out = os.path.join(tempfile.mkdtemp(), 'v.png')
        r, calls = self._stub_capture(out, '[vdec] W=4 H=4 fmt=11 stride0=4 stride1=4 bufsize=24')
        self._unstub()
        self.assertTrue(r['success'], r)
        self.assertEqual(r['vdecChn'], 0)
        self.assertIn('vdec 0 0', ' '.join(calls))

    def test_vdec_chn_passed_to_zkshot(self):
        """显式 chn 1（拼墙）→ zkshot 收到 `vdec 1 0`，返回体回显 vdecChn=1"""
        import tempfile
        out = os.path.join(tempfile.mkdtemp(), 'v.png')
        r, calls = self._stub_capture(
            out, '[vdec] SetChnOutputPortDepth(chn=1 port=0) rc=0x0\n'
                 '[vdec] W=4 H=4 fmt=11 stride0=4 stride1=4 bufsize=24', chn=1)
        self._unstub()
        self.assertTrue(r['success'], r)
        self.assertEqual(r['vdecChn'], 1)
        self.assertIn('/tmp/zkshot /tmp/.fyshot_video.raw vdec 1 0', ' '.join(calls))
        self.assertEqual(r['zkshotCmd'], '/tmp/zkshot /tmp/.fyshot_video.raw vdec 1 0')

    def test_vdec_failure_reports_channel_and_hint(self):
        """取不到帧不许静默：返回体带实际 chn + 命令行 + 指路 hint，warnings 带 zkshot 原始输出"""
        import tempfile
        out = os.path.join(tempfile.mkdtemp(), 'v.png')
        r, calls = self._stub_capture(
            out, '[vdec] SetChnOutputPortDepth(chn=1 port=0) rc=0x0\n[vdec] GetBuf failed: 0xa00b2008', chn=1)
        self._unstub()
        self.assertFalse(r['success'])
        self.assertEqual(r['vdecChn'], 1)
        self.assertIn('vdec 1 0', r['zkshotCmd'])
        self.assertIn('chn 1', r['hint'])
        self.assertTrue(any('chn=1' in w for w in r['warnings']), r['warnings'])
        self.assertTrue(any('vdec 1 0' in c for c in calls), calls)

    def test_vdec_empty_frame_reports_channel(self):
        """空帧（W=0 H=0）也要说清是哪个通道空"""
        import tempfile
        out = os.path.join(tempfile.mkdtemp(), 'v.png')
        r, _ = self._stub_capture(out, '[vdec] W=0 H=0 fmt=-1 stride0=0 stride1=0 bufsize=0')
        self._unstub()
        self.assertFalse(r['success'])
        self.assertEqual(r['vdecChn'], 0)
        self.assertIn('chn=0', r['error'])

    def test_bad_vdec_chn_type_raises_bad_params(self):
        """vdec_chn 传垃圾 → 明确报错（含参数名），不要抛异常/静默当 0 用"""
        r, _ = self._stub_capture(os.path.join(os.environ.get('TEMP', '.'), 'v.png'), '',
                                  chn='not-an-int')
        self._unstub()
        self.assertFalse(r['success'])
        self.assertIn('vdec_chn', r['error'])

    def test_capture_layer_video_forwards_vdec_chn(self):
        """capture(layer='video') 必须把 vdec_chn 透传进 capture_mi_video（别学 crop 丢参数的旧坑）"""
        if ds.Image is None:
            self.skipTest('缺 Pillow')
        seen = {}
        orig = ds.capture_mi_video
        try:
            def fake(**kw):
                seen.update(kw)
                return {'success': True}
            ds.capture_mi_video = fake
            ds.capture(layer='video', vdec_chn=1, device='dev')
        finally:
            ds.capture_mi_video = orig
        self.assertEqual(seen.get('vdec_chn'), 1)

    def test_cli_exposes_layer_and_vdec_chn(self):
        """CLI 原来根本没有 --layer：补上 --layer video + --vdec-chn 1"""
        import io
        import sys
        seen = {}
        orig_cap = ds.capture
        orig_argv, orig_out = sys.argv, sys.stdout
        try:
            def fake(**kw):
                seen.update(kw)
                return {'success': True}
            ds.capture = fake
            sys.argv = ['device_screenshot.py', '--layer', 'video', '--vdec-chn', '1']
            sys.stdout = io.StringIO()
            ds.main()
        finally:
            ds.capture = orig_cap
            sys.argv, sys.stdout = orig_argv, orig_out
        self.assertEqual(seen.get('layer'), 'video')
        self.assertEqual(seen.get('vdec_chn'), 1)


if __name__ == '__main__':
    unittest.main()
