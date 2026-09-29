# -*- coding: utf-8 -*-
"""整机自检（selfcheck）与缺陷单（bugreport）契约用例（v0.27.123-open）。

为什么要有：这两个 op 一个会连真机、一个会把「缺陷清单」写成要提交给人的文件 ——
一旦变成"读不到就静默、证据不存在也照写"，现场会拿到假的体检结论和假的缺陷单。
本文件把人肉口径钉成机器判据（离线，不连真机：设备侧读数用假设备注入）。

钉住的东西：
  ① `selfcheck` 分区结构（九个分区、每区 ≥2 个采集项、`{ok,hint,data}` 齐备、
     **读不到必须给 hint**）；
  ② 无设备时优雅报错（`NO_DEVICE` + hint，不抛栈）；
  ③ `diff_against` 分支（同快照 → 全 same；基线缺失 → `DIFF_BASE_MISSING` 且不丢本次快照）；
  ④ `bugreport` 产出文件 + 各段落齐备 + 真机判据自动附 + 落盘位置默认值；
  ⑤ evidence 文件不存在 → `EVIDENCE_MISSING` 明确失败（不静默跳过、不写半真半假的单子）；
  ⑥ 六方登记（manifest 的 risk/category/stage）+ 知识文档检索导引存在。
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

import _util as U

import selfcheck_tools as st

# 假设备的读数表（键 = 设备侧命令，值 = 原始输出）——模仿一块 Z21 板
FAKE = {
    'getprop ro.product.model': 'Zkswe_SSD21X_SPINOR',
    'cat /proc/version': 'Linux version 5.10.0 (gcc 8.3.0) #1 SMP',
    'getprop ro.easyui.version': '3.0.0',
    'getprop ro.build.fingerprint': 'flythings/z21/z21:9',
    'getprop init.svc.zkswe': 'running',
    'getprop sys.zkapp.state': 'running',
    'getprop sys.zkapp.dbg': '0',
    '/tmp/busybox pidof zkgui': '1234',
    'cat /proc/uptime': '1234.56 900.00',
    'cat /sys/class/graphics/fb0/virtual_size': '1024,1200',
    'cat /sys/class/graphics/fb0/bits_per_pixel': '32',
    'cat /sys/class/graphics/fb0/stride': '4096',
    'cat /sys/class/graphics/fb0/pan': '0,600',
    'cat /tmp/EasyUI.cfg 2>/dev/null; cat /mnt/extsd/EasyUI.cfg 2>/dev/null; '
    'cat /res/etc/EasyUI.cfg 2>/dev/null': '{"rotateScreen": 0, "rotateTouch": 0}',
    'cat /proc/mounts': ('/dev/block/mtdblock3 /res squashfs ro,relatime 0 0\n'
                         '/dev/block/mmcblk0p2 /data ext4 rw,relatime 0 0\n'
                         'tmpfs /tmp tmpfs rw 0 0'),
    '/tmp/busybox ls /mnt': 'extsd\nsdnand',
    '/tmp/busybox df -k /tmp': ('Filesystem 1K-blocks Used Available Use% Mounted on\n'
                                '/dev/root 36864 2048 34816 6% /tmp'),
    '/tmp/busybox df -k /data': ('Filesystem 1K-blocks Used Available Use% Mounted on\n'
                                 '/dev/block/mmcblk0p2 262144 40960 221184 16% /data'),
    '/tmp/busybox ls /res/ui': 'main.ftu\nmain.json',
    'cat /sys/class/net/wlan0/address': '02:00:00:11:22:33',
    '/tmp/busybox ifconfig wlan0': 'wlan0  Link encap:Ethernet  HWaddr 02:00:00:11:22:33\n'
                                   '          inet addr:192.0.2.10  Mask:255.255.255.0\n'
                                   '          UP BROADCAST RUNNING MULTICAST',
    'cat /proc/net/route': ('Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\n'
                            'wlan0\t00000000\t0A020001\t0003\t0\t0\t0\t00000000'),
    'cat /etc/resolv.conf': 'nameserver 192.0.2.1',
    '/tmp/busybox ls -l /data/misc/wifi/wpa_supplicant.conf': '-rw-rw-rw- 1 0 0 812 /data/misc/wifi/wpa_supplicant.conf',
    'getprop': '[persist.sys.timezone]: [Asia/Shanghai]\n[ro.product.model]: [Zkswe_SSD21X_SPINOR]',
    'cat /sys/class/rfkill/rfkill0/name': '',
    'cat /sys/class/rfkill/rfkill0/state': '',
    '/tmp/busybox ls /dev/hci*': '',
    '/tmp/busybox ls /dev/input': 'event0\nevent1',
    'cat /proc/bus/input/devices': ('N: Name="axs_ts"\nP: Phys=\nH: Handlers=event1\n\n'
                                    'N: Name="gpio-keys"\nH: Handlers=event0\n'),
    '/tmp/busybox ls -l /data/touch /tmp/touch': '',
    'cat /data/preferences.json': '{"sp_relay_state": "0,0,0", "sp_brightness": "80"}',
    '/tmp/busybox ls -l /data/preferences.json': '-rw-rw-rw- 1 0 0 92 /data/preferences.json',
    'cat /data/data/preferences.json': '',
    'date': 'Mon Sep 29 13:20:00 CST 2026',
    'date +%s': '1786000000',
    'getprop persist.sys.timezone': 'Asia/Shanghai',
    '/tmp/busybox ls /bin/ntpd /usr/sbin/ntpd /system/bin/ntpd /bin/ntpdate': '',
}


class _FakeDev(st._Dev):
    """假设备：只回读数表里的命令，其他一律空（模拟裁剪 rootfs）。

    overrides 合并到基准表上（改一个键就能造 diff）；base={} 表示"什么都不回"。
    """

    def __init__(self, overrides=None, base=None, busybox=True):
        st._Dev.__init__(self, 'adb', 'FAKE-SERIAL', 'Zkswe_SSD21X_SPINOR', 'Z21')
        self.busybox = '/tmp/busybox' if busybox else ''
        self.table = dict(base if base is not None else FAKE)
        self.table.update(overrides or {})

    def sh(self, cmd, timeout=25):
        return self.table.get(cmd, '')


def _patch_device(testcase, overrides=None, base=None, busybox=True):
    """把 selfcheck_tools 的设备定位换成假设备（离线、不碰 adb），tearDown 还原。"""
    testcase._orig = (st.resolve_target, st._dev_from_target)
    target = {'ok': True, 'adb': 'adb', 'serial': 'FAKE-SERIAL', 'model': 'Zkswe_SSD21X_SPINOR',
              'platform': 'Z21', 'connectNote': '', 'devices': [], 'offline': [],
              'error': '', 'hint': ''}
    st.resolve_target = lambda device='': dict(target)
    st._dev_from_target = lambda t: _FakeDev(overrides, base, busybox)


def _unpatch(testcase):
    st.resolve_target, st._dev_from_target = testcase._orig


class TestSelfcheckNoDevice(unittest.TestCase):
    """无设备/多设备：优雅报错 + hint，不抛栈。"""

    def setUp(self):
        self._orig = (st.resolve_target, st._dev_from_target)

    def tearDown(self):
        _unpatch(self)

    def test_no_device_is_graceful(self):
        st.resolve_target = lambda device='': {
            'ok': False, 'adb': '', 'serial': '', 'model': '', 'platform': '',
            'connectNote': '', 'devices': [], 'offline': [],
            'error': '未检测到可用设备（adb devices 里没有 state=device 的机器）',
            'hint': '装 ADB 驱动 / 开 USB 调试授权 / 网络设备用 device="<IP>:5555"'}
        r = U.jcall('flythings_selfcheck')
        self.assertFalse(r['ok'])
        self.assertEqual(r['error']['code'], 'NO_DEVICE')
        self.assertTrue(r['error']['hint'], '无设备时必须给 hint（不许只有一句错）')
        self.assertTrue(r['error']['retryable'])
        self.assertEqual(r.get('sections'), {}, '无设备时不该伪造分区数据')

    def test_multi_device_not_guessed(self):
        """多台在线不猜：resolve_target 自己决定 → 这里钉住「不猜」的返回契约。"""
        st.resolve_target = lambda device='': {
            'ok': False, 'adb': 'adb', 'serial': '', 'model': '', 'platform': '',
            'connectNote': '', 'devices': [{'serial': 'A'}, {'serial': 'B'}], 'offline': [],
            'error': '检测到 2 台在线设备，**不自动选择**',
            'hint': '显式传 device="<serial|IP>:5555" 重试'}
        r = U.jcall('flythings_selfcheck', {'device': ''})
        self.assertFalse(r['ok'])
        self.assertIn('不自动选择', r['error']['msg'])
        self.assertIn('device=', r['error']['hint'])


class TestSelfcheckSections(unittest.TestCase):
    """分区结构 + 读不到必须给 hint + diff 分支（假设备）。"""

    def setUp(self):
        _patch_device(self)

    def tearDown(self):
        _unpatch(self)
        if getattr(self, '_tmp', ''):
            shutil.rmtree(self._tmp, ignore_errors=True)

    def test_nine_sections_shaped(self):
        r = U.jcall('flythings_selfcheck')
        self.assertTrue(r['ok'], r.get('error'))
        want = [s['key'] for s in st.SECTIONS]
        self.assertEqual(len(want), 9, '九分区口径被改了？')
        self.assertEqual(sorted(r['sections']), sorted(want))
        for key, sec in r['sections'].items():
            self.assertIsInstance(sec['ok'], bool, key)
            self.assertIsInstance(sec['hint'], str, key)
            self.assertIsInstance(sec['data'], dict, key)
            self.assertGreaterEqual(len(sec.get('items') or []), 2,
                                    '%s 采集项少于 2 个（每区至少 2~4 项）' % key)
            for it in sec['items']:
                self.assertTrue(it.get('cmd'), '%s 的采集项缺 cmd（无法复现）' % key)
                self.assertIn('ok', it)
            if not sec['ok']:
                self.assertTrue(sec['hint'], '%s ok=false 必须给 hint（读不到是结论）' % key)
        self.assertEqual(r['summary']['total'], 9)
        self.assertEqual(r['summary']['ok'] + r['summary']['failed'], 9)

    def test_busybox_free_probes_report_why(self):
        """设备没有 busybox 时：需要 busybox 的采集项要写明原因，而不是静默空着。"""
        _unpatch(self)
        _patch_device(self, base={}, busybox=False)
        r = U.jcall('flythings_selfcheck')
        self.assertTrue(r['ok'])
        items = [it for sec in r['sections'].values() for it in sec['items']]
        self.assertTrue(any('busybox' in (it.get('note') or '') for it in items),
                        '缺 busybox 的采集项必须带 note 说明')
        self.assertFalse(r['sections']['storage']['ok'], '没有任何读数时 storage 不该判 ok')

    def test_diff_same_and_missing_base(self):
        self._tmp = tempfile.mkdtemp(prefix='mcp_selfcheck_')
        snap = os.path.join(self._tmp, 'snap.json')
        first = U.jcall('flythings_selfcheck', {'out': snap})
        self.assertTrue(first['ok'])
        self.assertTrue(os.path.isfile(snap), first.get('outPath'))
        self.assertIn(snap, first['affectedFiles'])
        same = U.jcall('flythings_selfcheck', {'diff_against': snap})
        self.assertTrue(same['ok'])
        self.assertEqual(same['diff']['summary']['changed'], 0)
        self.assertEqual(same['diff']['summary']['same'], 9)
        self.assertEqual([s['status'] for s in same['diff']['sections']][0], 'same')
        # 改了设备读数 → diff 必须报 changed + 给出 before/after
        _unpatch(self)
        _patch_device(self, {'getprop ro.product.model': 'Zkswe_F136_SPINOR'})
        chg = U.jcall('flythings_selfcheck', {'diff_against': snap})
        self.assertTrue(chg['ok'])
        self.assertEqual(chg['diff']['summary']['changed'], 1)
        sec = [s for s in chg['diff']['sections'] if s['status'] == 'changed'][0]
        self.assertEqual(sec['key'], 'device')
        keys = [i['key'] for i in sec['items']]
        self.assertIn('data.model', keys)
        # 天然会变的读数（uptime/时间）不计入 changed，只进 volatileItems（否则每次 diff 都说"变了"）
        _unpatch(self)
        _patch_device(self, {'cat /proc/uptime': '9999.99 8000.00', 'date +%s': '1786000999'})
        vol = U.jcall('flythings_selfcheck', {'diff_against': snap})
        self.assertTrue(vol['ok'])
        self.assertEqual(vol['diff']['summary']['changed'], 0,
                         'uptime/时间属天然波动，不该报 changed')
        self.assertGreaterEqual(vol['diff']['summary']['volatileItems'], 1)
        vkeys = [i['key'] for s in vol['diff']['sections']
                 for i in (s.get('volatileItems') or [])]
        self.assertIn('data.uptimeSeconds', vkeys)
        # 基线缺失 → 明确报错，且不丢本次快照
        miss = U.jcall('flythings_selfcheck',
                       {'diff_against': os.path.join(self._tmp, 'nope.json')})
        self.assertFalse(miss['ok'])
        self.assertEqual(miss['error']['code'], 'DIFF_BASE_MISSING')
        self.assertTrue(miss.get('sections'), '基线缺失不该把本次快照也丢掉')


class TestBugreport(unittest.TestCase):
    """缺陷单：段落齐备 / 真机判据 / 证据缺失必须明确失败。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix='mcp_bugreport_')
        self._orig_j = st.collect_judgement
        st.collect_judgement = lambda device='', project_root='': {
            'ok': True,
            'device': {'serial': 'FAKE-SERIAL', 'model': 'Zkswe_SSD21X_SPINOR',
                       'platform': 'Z21', 'busybox': '/tmp/busybox'},
            'items': {'model': 'Zkswe_SSD21X_SPINOR', 'firmware': '3.0.0',
                      'buildFingerprint': 'flythings/z21/z21:9', 'initService': 'running',
                      'appState': 'running', 'zkguiPid': '1234', 'uptime': '1234.56'},
            'logcat': ['09-29 13:20:00.123  1234  1234 I zkgui: page switch -> main',
                       '09-29 13:20:01.200  1234  1234 E zkgui: touch ignored'],
            'note': ''}

    def tearDown(self):
        st.collect_judgement = self._orig_j
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_render_markdown_sections(self):
        ev = os.path.join(self._tmp, 'shot.png')
        io.open(ev, 'wb').write(b'\x89PNG\r\n')
        out = os.path.join(self._tmp, 'bug.md')
        r = U.jcall('flythings_bugreport', {
            'title': 'html2json 纯黑 #000000 被当未设置（绿底白字对比度 1.44:1）',
            'symptom': '同一页面按钮底色与设计稿不一致',
            'steps': '打开案例页\n点第 3 个按钮',
            'expected': '纯黑底 #000000', 'actual': '引擎默认色', 'evidence': [ev],
            'severity': 'major', 'out': out})
        self.assertTrue(r['ok'], r.get('error'))
        self.assertEqual(r['path'], out)
        md = io.open(out, encoding='utf-8').read()
        for seg in ('# html2json 纯黑', '- 日期：', '- 平台：Z21', '- 设备：FAKE-SERIAL',
                    '- 严重级：major', '## 现象', '## 复现步骤', '1. 打开案例页',
                    '2. 点第 3 个按钮', '## 期望 vs 实际', '## 真机判据', '## 证据',
                    '## 影响面 / 建议'):
            self.assertIn(seg, md, '缺段落/字段：%s' % seg)
        self.assertIn('Zkswe_SSD21X_SPINOR', md)
        self.assertIn('logcat', md)
        self.assertIn('touch ignored', md)                 # 最近 logcat 摘要真的进来了
        self.assertIn(ev, md)
        self.assertEqual(len(r['preview']), 20, '返回前 20 行预览')
        self.assertLessEqual(len(r['preview']), len(md.splitlines()))
        self.assertIn(r['path'], r['affectedFiles'])

    def test_default_out_path_under_project_temp(self):
        r = U.jcall('flythings_bugreport',
                    {'title': '布局重叠：按钮被整屏层吞触摸', 'project_root': self._tmp})
        self.assertTrue(r['ok'], r.get('error'))
        rel = os.path.relpath(r['path'], self._tmp).replace('\\', '/')
        self.assertTrue(rel.startswith('temp/bugreports/'), rel)
        self.assertTrue(os.path.isfile(r['path']))
        self.assertEqual(len(r['preview']), 20)
        # 没传 device 时真机判据要走 stub（本文件里 patch 成 ok=True）——只钉住落盘位置口径
        self.assertIn('- 严重级：major', io.open(r['path'], encoding='utf-8').read())

    def test_evidence_missing_fails_loudly(self):
        out = os.path.join(self._tmp, 'never.md')
        r = U.jcall('flythings_bugreport', {
            'title': 'x', 'evidence': os.path.join(self._tmp, 'nope.png'), 'out': out})
        self.assertFalse(r['ok'])
        self.assertEqual(r['error']['code'], 'EVIDENCE_MISSING')
        self.assertIn('nope.png', r['error']['msg'])
        self.assertFalse(os.path.isfile(out), '证据缺失时不该产出单子')

    def test_title_required(self):
        r = U.jcall('flythings_bugreport', {})
        self.assertFalse(r['ok'])
        self.assertEqual(r['error']['code'], 'BAD_PARAMS')
        self.assertIn('title', r['error']['hint'])

    def test_no_device_writes_note_not_fake_data(self):
        st.collect_judgement = lambda device='', project_root='': {
            'ok': False, 'device': {}, 'items': {}, 'logcat': [],
            'note': '未连设备或设备不可定位：未检测到可用设备'}
        out = os.path.join(self._tmp, 'nod.md')
        r = U.jcall('flythings_bugreport', {'title': '空设备单子', 'out': out})
        self.assertTrue(r['ok'])
        md = io.open(out, encoding='utf-8').read()
        self.assertIn('未采集到真机数据', md)
        self.assertIn('未检测到可用设备', md)
        self.assertTrue(any('未连设备' in w for w in r['warnings']))


class TestRegistrationAndDocs(unittest.TestCase):
    """六方登记与文档可检索性。"""

    def test_manifest_registers_both_ops(self):
        ops = {o['op']: o for o in U.manifest()['ops']}
        for name, risk in (('flythings_selfcheck', 'device'),
                           ('flythings_bugreport', 'write')):
            self.assertIn(name, ops, 'tools_manifest.json 没登记 %s' % name)
            self.assertEqual(ops[name]['risk'], risk, name)
            self.assertEqual(ops[name]['category'], 'device', name)
            self.assertEqual(ops[name]['stage'], 'build', name)
            self.assertTrue(ops[name]['brief'], name)

    def test_catalog_signatures(self):
        cat = {o['op']: o for o in U.jcall('list')['ops']}
        self.assertEqual(cat['flythings_selfcheck']['args'],
                         ['device', 'diff_against', 'out'])
        self.assertEqual(cat['flythings_bugreport']['args'],
                         ['title', 'project_root', 'device', 'symptom', 'steps', 'expected',
                          'actual', 'evidence', 'severity', 'out'])

    def test_knowledge_doc_has_retrieval_guide(self):
        p = os.path.join(U.BASE, 'knowledge', 'devflow', 'selfcheck-and-bugreport.md')
        head = io.open(p, encoding='utf-8').read()
        for kw in ('检索导引', '整机自检', '缺陷单', '读不到', '九分区',
                   'EVIDENCE_MISSING', 'logcat'):
            self.assertIn(kw, head, '文档缺关键词：%s' % kw)
        self.assertIn('check_retrieval.py', head)


if __name__ == '__main__':
    sys.exit(unittest.main(verbosity=2))
