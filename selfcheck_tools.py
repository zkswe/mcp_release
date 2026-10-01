# -*- coding: utf-8 -*-
"""整机自检快照（selfcheck）与缺陷单生成（bugreport）的实现层。

为什么单列一个模块：`kb_tools.py` 只放「MCP 工具面」的薄封装（统一 envelope + docstring
预算），采集 / 渲染这类长逻辑放这里，改实现不动工具签名。

口径要点（2026-09-29，钟工「1-3 按顺序做」第 3 项 = 审查报告 P2-⑧⑨）：
  · **selfcheck 十一分区**，每分区给 `{ok, hint, data}`；**「读不到」本身是结论** ——
    读不到就 `ok=false` + `hint` 写清「需要什么条件 / 去哪查」，绝不静默吞掉。
  · 命令一律**容忍设备缺工具**：优先用随仓 `bin_tools/<平台>/busybox`（`adb_tools.ensure_busybox`
    会复用设备上已有的 `/tmp/busybox` 或推一份过去），没有就退化成纯 `adb shell` + `getprop` / `cat`。
  · **bugreport** 把「AI 产出的缺陷清单 + 真机判据」落成可提交的 markdown，
    格式对齐 2026-09-27 html2json A1~A8 那批缺陷单（标题 / 元信息 / 现象 / 复现步骤 /
    期望 vs 实际 / 真机判据 / 证据 / 影响面）。

⚠️ 隐私纪律：本模块只输出**设备侧**读数；不带本机绝对路径、不带内网真机 IP（示例统一写
`<serial|IP>:5555`）。测试与文档同理（scripts/smoke.py 的隐私扫描会扫本文件）。
"""
import io
import json
import os
import re
import time

MCP_ROOT = os.path.dirname(os.path.abspath(__file__))

try:
    import adb_tools as _adb
    _ADB_ERR = ''
except Exception as _e:          # adb_tools 缺失：设备类分区全部 ok=false + hint（不抛）
    _adb = None
    _ADB_ERR = repr(_e)

# 设备端没有 md5sum/grep/head 这类工具（裁剪 rootfs），能用的就 getprop / cat / ls
_PROBE_RAW_CAP = 200
_PROBE_CMD_TIMEOUT = 25


# ────────────────────────────────────────────────────────── 小工具
def _as_int(txt):
    """'123' / '123\\n' → 123；非数字回 None（不抛）。"""
    m = re.search(r'-?\d+', str(txt or ''))
    if not m:
        return None
    try:
        return int(m.group(0))
    except ValueError:
        return None


_ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
_ERR_LINE = re.compile(r'(No such file or directory|cannot open|Permission denied'
                       r'|^\s*(ls|cat|sh|test|df|grep):|not found)')


def _clean(txt):
    """设备命令输出 → 读数：去掉 ANSI 转义与**报错行**。

    ⚠️ 必须有这一步：`ls /dev/hci*` 打不出文件时回的是 `ls: ...: No such file`，
    当成读数会让「没插模组」的蓝牙分区变成 ok=true（假阳性，真机抽查抓到过）。
    """
    t = _ANSI.sub('', str(txt or ''))
    keep = []
    for line in t.splitlines():
        s = line.strip()
        if s and not _ERR_LINE.search(s):
            keep.append(s)
    return '\n'.join(keep)


def _cap(txt, n=_PROBE_RAW_CAP):
    t = str(txt or '').strip()
    return t if len(t) <= n else t[:n] + '…'


def _first_line(txt):
    for line in str(txt or '').splitlines():
        if line.strip():
            return line.strip()
    return ''


class _Dev(object):
    """一台设备 + adb 路径 + 可选 busybox 远端路径（自检的采集上下文）。"""

    def __init__(self, adb, serial, model='', platform=''):
        self.adb = adb
        self.serial = serial
        self.model = model
        self.platform = platform
        self.busybox = ''
        self.busyboxNote = ''

    def sh(self, cmd, timeout=_PROBE_CMD_TIMEOUT):
        return _adb.sh(self.adb, self.serial, cmd, timeout=timeout) or ''

    def sh_bb(self, cmd, timeout=_PROBE_CMD_TIMEOUT):
        """优先走 busybox（`/tmp/busybox <cmd>`）；没有 busybox 回 ''（调用方给 note）。"""
        if not self.busybox:
            return ''
        return self.sh('%s %s' % (self.busybox, cmd), timeout=timeout)

    def ensure_busybox(self):
        """复用设备上已有的 /tmp/busybox，没有就把随仓 bin_tools/<平台>/busybox 推上去。"""
        try:
            self.busybox = _adb.ensure_busybox(self.adb, self.serial, self.platform) or ''
        except Exception as e:               # 推失败不阻断（分区降级为纯 adb shell）
            self.busybox = ''
            self.busyboxNote = 'busybox 投递异常: %r' % e
            return self.busybox
        if not self.busybox:
            self.busyboxNote = ('设备上无 /tmp/busybox 且随仓 bin_tools 没有可用副本 → '
                                '需要 busybox 的采集项降级（push bin_tools/<平台>/busybox 后重跑）')
        return self.busybox


def _probe(name, cmd, bb=False, cap=_PROBE_RAW_CAP):
    """一个采集项：name = 数据键；cmd = 设备侧命令；bb = 必须经 busybox 执行。"""
    return {'name': name, 'cmd': cmd, 'bb': bool(bb), 'cap': cap}


# ────────────────────────────────────────────────────────── 设备定位
def resolve_target(device=''):
    """定位目标设备（selfcheck / bugreport 共用）。

    `device` 传 `<serial|IP>:5555`；留空则按 adb 在线列表解析 —— **多台绝不猜**
    （fun 在多设备下会静默取第一个 → 可能量到别的机器上）。
    返回 {'ok','adb','serial','model','platform','connectNote','devices','offline','error','hint'}
    """
    out = {'ok': False, 'adb': '', 'serial': '', 'model': '', 'platform': '',
           'connectNote': '', 'devices': [], 'offline': [], 'error': '', 'hint': ''}
    if _adb is None:
        out['error'] = 'adb 子系统不可用（adb_tools 导入失败：%s）' % _ADB_ERR
        out['hint'] = '把 MCP 包的 adb_tools.py 恢复，或设环境变量 ADB 指向 adb 可执行文件'
        return out
    adb = _adb.resolve_adb()
    if not adb:
        out['error'] = _adb.adb_missing_hint()
        out['hint'] = ('装 platform-tools 或把 adb.exe 放到随包 tools/adb/；'
                       '网络设备也可先手工 `adb connect <IP>:5555` 再重试')
        return out
    out['adb'] = adb
    pr = _adb.probe_devices(adb=adb)
    if not pr.get('ok'):
        out['error'] = '设备探测失败：%s' % (pr.get('error') or '未知原因')
        out['hint'] = _adb.install_hint('', pr.get('offline') or [], pr.get('error') or '')
        return out
    # 网络接入：给了 <ip>:5555 但不在列表里 → 先 connect 一次再探
    if device and ':' in str(device) and \
            not any(d.get('serial') == device for d in pr.get('online') or []):
        try:
            ok, txt = _adb.connect(device, adb=adb)
            out['connectNote'] = 'adb connect %s → %s' % (device, txt or ('ok' if ok else 'failed'))
            if ok:
                pr = _adb.probe_devices(adb=adb)
        except Exception as e:             # connect 自身异常也回显（不静默）
            out['connectNote'] = 'adb connect %s 异常: %r' % (device, e)
    online = list(pr.get('online') or [])
    out['devices'] = online
    out['offline'] = list(pr.get('offline') or [])
    if device:
        hit = [d for d in online if d.get('serial') == str(device)]
        if not hit:
            out['error'] = ('指定设备 %r 不在 adb 在线列表（当前在线：%s）'
                            % (device, [d.get('serial') for d in online] or '无'))
            out['hint'] = ('网络设备先 `adb connect <IP>:5555`（或用 device="<IP>:5555" 让工具自动连）；'
                           'USB 设备确认已插好并在设备上授权调试')
            return out
        chosen = hit[0]
    else:
        if not online:
            out['error'] = '未检测到可用设备（adb devices 里没有 state=device 的机器）'
            out['hint'] = _adb.install_hint('', out['offline'])
            return out
        if len(online) > 1:
            out['error'] = ('检测到 %d 台在线设备，**不自动选择**（可能量到别的机器上）' % len(online))
            out['hint'] = ('显式传 device="<serial|IP>:5555" 重试；当前在线：%s'
                           % ', '.join('%s(%s)' % (d.get('serial'), d.get('model') or '?')
                                       for d in online))
            return out
        chosen = online[0]
    out['serial'] = chosen.get('serial') or ''
    out['model'] = chosen.get('model') or ''
    out['platform'] = chosen.get('platform') or ''
    out['ok'] = True
    return out


def _dev_from_target(t):
    d = _Dev(t['adb'], t['serial'], t.get('model') or '', t.get('platform') or '')
    d.ensure_busybox()
    return d


# ────────────────────────────────────────────────────────── 九分区定义
def _post_device(raw, dev):
    """设备信息：型号 / 平台（型号表反查）/ 内核 / EasyUI 版本。"""
    model = _first_line(raw.get('model'))
    data = {'model': model,
            'platform': '',
            'platformConfidence': '',
            'kernel': _cap(_first_line(raw.get('kernel')), 120),
            'easyuiVersion': _first_line(raw.get('easyuiVersion')),
            'buildFingerprint': _cap(raw.get('buildFingerprint'), 120)}
    notes = []
    if model and _adb is not None:
        hit = _adb.lookup_model(model)
        data['platform'] = hit.get('platform') or ''
        data['platformConfidence'] = hit.get('confidence') or ''
        if not data['platform']:
            notes.append('型号 %r 未在 device_models.json 命中 → platform 留空（不猜）；'
                         '用 flythings_hardware_info 查硬件规格' % model)
    if not model:
        notes.append('设备未回报 ro.product.model（裁剪 rootfs 可能没有该属性）')
    return data, notes


def _post_app(raw, dev):
    """应用状态：init 服务 / 应用状态属性 / zkgui pid / 开机时长。"""
    data = {'initService': _first_line(raw.get('initService')),
            'appState': _first_line(raw.get('appState')),
            'appDbg': _first_line(raw.get('appDbg')),
            'zkguiPid': _first_line(raw.get('pid')),
            'uptimeSeconds': None}
    notes = []
    if not data['zkguiPid']:
        if dev.busybox:
            notes.append('pidof 没回 zkgui（应用没起？或进程名不同）→ '
                         '重启应用用 `setprop ctl.restart zkswe`，不要 kill')
        else:
            notes.append('读 pid 需要 busybox（%s）' % (dev.busyboxNote or '设备无 /tmp/busybox'))
    up = str(raw.get('uptime') or '').split()
    if up and up[0]:
        try:
            data['uptimeSeconds'] = round(float(up[0]), 1)
        except ValueError:
            notes.append('无法解析 /proc/uptime: %r' % _cap(raw.get('uptime'), 60))
    return data, notes


def _post_display(raw, dev):
    """显示：fb0 几何/像素格式/双缓冲 pan + EasyUI.cfg 的旋转口径。"""
    data = {'virtualSize': _first_line(raw.get('virtualSize')),
            'bitsPerPixel': _as_int(raw.get('bitsPerPixel')),
            'stride': _as_int(raw.get('stride')),
            'pan': _first_line(raw.get('pan')),
            'rotate': {}}
    notes = []
    cfg = str(raw.get('easyuiCfg') or '')
    for k, v in re.findall(r'(rotateScreen|rotateTouch)\s*[:=]\s*([^\s,;}]+)', cfg):
        data['rotate'][k] = v.strip('"\'')
    if not data['rotate']:
        notes.append('未从 EasyUI.cfg 读到 rotateScreen/rotateTouch'
                     '（按 /tmp > /mnt/extsd > /res/etc 顺序找过；三者都可能不存在）')
    if data['virtualSize'] and data['stride'] and data['bitsPerPixel']:
        notes.append('抓屏口径：可见高≠fb 文件行数，须按 stride 逐行取 + 读 pan 的 yoffset '
                     '（flythings_device_screenshot 已内置）')
    return data, notes


def _post_storage(raw, dev):
    """存储：/res 与 /data 挂载只读性 + /mnt/* + /tmp、/data 空间 + /res/ui 清单。"""
    want = ('/res', '/data', '/tmp', '/mnt/extsd', '/mnt/sdnand', '/mnt/sd')
    mounts = {}
    for line in str(raw.get('mounts') or '').splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] in want:
            opts = parts[3]
            mounts[parts[1]] = {'device': parts[0], 'fstype': parts[2],
                                'options': opts, 'readOnly': 'ro' in opts.split(',')}
    data = {'mounts': mounts,
            'mnt': str(raw.get('mnt') or '').split(),
            'tmpSpace': _df(raw.get('tmpSpace')),
            'dataSpace': _df(raw.get('dataSpace')),
            'resUi': str(raw.get('resList') or '').split()}
    notes = []
    if not mounts:
        notes.append('/proc/mounts 里没匹配到 /res、/data 等挂载点（挂载布局可能不同）')
    if '/res' in mounts and mounts['/res']['readOnly']:
        notes.append('/res 是**只读**的（squashfs 常态）→ 调试推送落 /tmp，'
                     '掉电保留要出 update.img 固化（flythings_pack_upgrade）')
    if not data['tmpSpace']:
        notes.append('读 /tmp 空间需要 busybox df（%s）' % (dev.busyboxNote or '有 busybox 但 df 失败'))
    return data, notes


def _df(txt):
    """`df -k` 输出第 2 行 → {'totalKB','usedKB','availKB','usePct','mount'}（解析不到回 {}）。"""
    lines = [l for l in str(txt or '').splitlines() if l.strip()]
    if len(lines) < 2:
        return {}
    parts = lines[-1].split()
    if len(parts) < 6:
        return {}
    return {'filesystem': parts[0], 'totalKB': _as_int(parts[1]), 'usedKB': _as_int(parts[2]),
            'availKB': _as_int(parts[3]), 'usePct': parts[4], 'mount': parts[5]}


def _post_network(raw, dev):
    """网络：wlan0 mac/ip + 默认路由 + DNS + wpa_supplicant 配置是否在。"""
    data = {'wlanMac': _first_line(raw.get('wlanMac')),
            'wlan0': {},
            'defaultRoute': {},
            'dns': [l.strip() for l in str(raw.get('dns') or '').splitlines()
                    if l.strip() and not l.strip().startswith('#')],
            'wpaSupplicantConf': _first_line(raw.get('wpaConf'))}
    ifc = str(raw.get('wlanIf') or '')
    ip = re.search(r'(?:inet addr|inet)\s*:?\s*(\d+\.\d+\.\d+\.\d+)', ifc)
    mac = re.search(r'(?:HWaddr|ether)\s*([0-9a-fA-F:]{17})', ifc)
    if ip:
        data['wlan0']['ip'] = ip.group(1)
    if mac:
        data['wlan0']['mac'] = mac.group(1)
    data['wlan0']['up'] = ('UP' in ifc) if ifc else None
    for line in str(raw.get('route') or '').splitlines()[1:]:
        f = line.split()
        if len(f) >= 8 and f[1] == '00000000':
            data['defaultRoute'] = {'iface': f[0], 'gateway': _hex_ip(f[2]),
                                    'mask': _hex_ip(f[7])}
            break
    notes = []
    if not data['wlanMac'] and not data['wlan0']:
        notes.append('读不到 wlan0（设备可能没有 WiFi 模组，或网口叫别的名字：'
                     '看 /proc/net/dev 的接口列表）')
    if not data['defaultRoute']:
        notes.append('/proc/net/route 里没有默认路由（Destination=00000000）→ 没联网')
    return data, notes


def _hex_ip(h):
    """`/proc/net/route` 的小端十六进制 → 点分十进制（解析不了回原串）。"""
    try:
        v = int(str(h), 16)
    except ValueError:
        return str(h)
    return '%d.%d.%d.%d' % (v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF)


def _post_bluetooth(raw, dev):
    """蓝牙：只认设备侧真实可读的 RF 状态（属性 / rfkill / hci 节点）。"""
    props = {}
    for line in str(raw.get('props') or '').splitlines():
        m = re.match(r'^\[([^\]]+)\]:\s*\[(.*)\]\s*$', line.strip())
        if m and re.search(r'(^|[._-])(bt|bluetooth|bluez)', m.group(1), re.I):
            props[m.group(1)] = m.group(2)
    data = {'props': props,
            'rfkillName': _first_line(raw.get('rfkillName')),
            'rfkillState': _first_line(raw.get('rfkillState')),
            'hciNodes': str(raw.get('hciNodes') or '').split()}
    notes = []
    if not (props or data['rfkillState'] or data['hciNodes']):
        notes.append('三项都空：本机没有 BT 相关系统属性 / rfkill / hci 节点 '
                     '→ 板子可能没插 AIC USB BT 模组（或模组未起 hci）')
    return data, notes


def _post_input(raw, dev):
    """输入：/dev/input 节点 + /proc/bus/input/devices 的触摸设备名。"""
    devices = []
    cur = None
    for line in str(raw.get('devices') or '').splitlines():
        line = line.strip()
        m = re.match(r'^N:\s*Name="?([^"]*)"?\s*$', line)
        if m:
            cur = {'name': m.group(1).strip(), 'handlers': ''}
            continue
        m = re.match(r'^H:\s*Handlers=(.*)$', line)
        if m and cur is not None:
            cur['handlers'] = m.group(1).strip()
            devices.append(cur)
            cur = None
    touch = [d for d in devices
             if re.search(r'touch|ts$|gt9|axs|ft5|goodix|ftsc', d['name'], re.I)]
    data = {'nodes': str(raw.get('nodes') or '').split(),
            'devices': devices,
            'touchDevices': touch,
            'touchTool': str(raw.get('touchTool') or '').strip()}
    notes = []
    if not data['touchDevices']:
        notes.append('没从 /proc/bus/input/devices 认出触摸设备（名字不含 touch/ts/gt9/axs 等）')
    notes.append('注入触摸用随仓 bin_tools/<平台>/touch（先 `touch list` 看节点与协议；'
                 'busybox 只是让你能看 /dev/input）')
    return data, notes


def _post_peripheral(raw, dev):
    """外设：/data/preferences.json 里的继电器/过零 IO 等状态（没写过就没有）。"""
    txt = str(raw.get('prefs') or '') or str(raw.get('prefsAlt') or '')
    parsed = None
    if txt.strip():
        try:
            parsed = json.loads(txt)
        except ValueError:
            parsed = None
    relay = {}
    if isinstance(parsed, dict):
        relay = {k: v for k, v in parsed.items() if re.search(r'relay|zero|io', k, re.I)}
    data = {'preferencesPath': _first_line(raw.get('prefsPath')),
            'preferencesRead': isinstance(parsed, dict),
            'relayKeys': relay,
            'keys': sorted(parsed.keys())[:20] if isinstance(parsed, dict) else []}
    notes = []
    if parsed is None:
        notes.append('/data/preferences.json 读不到或不是 JSON —— 应用没写过偏好时**本来就没有**，'
                     'ok=false 是结论本身')
    elif not relay:
        notes.append('偏好里没有 relay/zero/io 相关键（本板可能没接继电器）')
    return data, notes


def _post_time(raw, dev):
    """时间：date / epoch / 时区 / 与宿主（本机）的偏差 —— NTP 是否可用不替你判断。"""
    epoch = _as_int(raw.get('epoch'))
    dateRaw = _first_line(raw.get('dateRaw'))
    if epoch is None and dev.busybox:
        epoch = _as_int(dev.sh_bb('date +%s'))
        if epoch is not None:
            dateRaw = dateRaw or dev.sh_bb('date')
    drift = None
    if epoch is not None:
        drift = int(epoch - time.time())
    data = {'date': dateRaw,
            'epoch': epoch,
            'timezone': _first_line(raw.get('timezone')),
            'hostEpoch': int(time.time()),
            'driftSeconds': drift,
            'ntpTool': str(raw.get('ntpTool') or '').strip()}
    notes = []
    if epoch is None:
        notes.append('设备侧 date/date +%s 都取不到（裁剪 rootfs）→ 试 busybox date')
    elif abs(drift) >= 300:
        notes.append('与宿主时间偏差 %ds（≥5min）：**先校时再做带证书校验的 HTTPS**，'
                     '否则会报 certificate validity starts in the future' % drift)
    return data, notes


def _post_libs(raw, dev):
    """库清单：/lib 与 /res/lib 的 .so 盘点 —— 借库先看这里，别急着自己编。"""
    focus = ('nanovg', 'libpng', 'freetype', 'jpeg', 'mad', 'libz.so',
             'libgomp', 'libstdc++')
    libs, res = [], []
    for key, bucket in (('libList', libs), ('resLibList', res)):
        for line in str(raw.get(key) or '').splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            path = parts[-1]
            if '.so' not in path:
                continue
            name = path.rsplit('/', 1)[-1]
            try:
                size = int(parts[4])
            except (ValueError, IndexError):
                size = None
            bucket.append({'name': name, 'size': size, 'path': path})
    found = {k: any(k in it['name'] for it in libs) for k in focus}
    data = {'libs': libs, 'libCount': len(libs),
            'resLib': res, 'resLibCount': len(res), 'focus': found,
            'borrowable': [k for k, v in found.items() if v]}
    notes = []
    if not libs:
        notes.append('读不到 /lib 清单：确认 busybox 在位（本模块会自动推）')
    else:
        notes.append('可借库（dlopen 免编译）：%s；`libmi_*` 属框架内部，应用不需关注'
                     % (', '.join(data['borrowable']) or '未命中重点库'))
    return data, notes


def _cfg_field(txt, key):
    """从 EasyUI.cfg 文本里取字符串字段（读不到回空串，不猜）。"""
    m = re.search(r'"%s"\s*:\s*"([^"]*)"' % re.escape(key), txt or '')
    return m.group(1) if m else ''


def _md5_lines(txt):
    """busybox `md5sum` 输出 → {路径: md5}（格式不对的行直接跳过，不当成读数）。"""
    out = {}
    for line in str(txt or '').splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 32 and '/' in parts[1]:
            out[parts[1]] = parts[0]
    return out


def _post_deploy(raw, dev):
    """部署一致性：生效 cfg 是哪一份 / resPath 与 startupLibPath 是否同源 / lib 与 ui 是否同代。

    2026-10-01 真机发现（192.168.x.x）：面板上 `startupLibPath=/tmp/lib/libzkgui.so`（新）
    而 `resPath=/res/ui/`（旧）→ **跑的是「新库 + 旧界面」**，症状就是「改了像没改 / 布局不对劲」。
    """
    srcs = (('/tmp/EasyUI.cfg', raw.get('cfgTmp')),
            ('/mnt/extsd/EasyUI.cfg', raw.get('cfgSd')),
            ('/res/etc/EasyUI.cfg', raw.get('cfgRes')))
    cfg_src, cfg_text = '', ''
    for name, txt in srcs:
        if str(txt or '').lstrip().startswith('{'):
            cfg_src, cfg_text = name, str(txt)
            break                      # 优先级 /tmp > /mnt/extsd > /res/etc
    res_path = _cfg_field(cfg_text, 'resPath')
    lib_path = _cfg_field(cfg_text, 'startupLibPath')

    def _root(p):
        for r in ('/tmp', '/mnt/extsd', '/res'):
            if str(p).startswith(r):
                return r
        return ''

    root_same = bool(res_path and lib_path and _root(res_path) == _root(lib_path))
    found_cfg = [n for n, t in srcs if str(t or '').lstrip().startswith('{')]
    md5_lib = _md5_lines(raw.get('libMd5'))
    tmp_lib = next((v for k, v in md5_lib.items() if k.startswith('/tmp/')), '')
    res_lib = next((v for k, v in md5_lib.items() if k.startswith('/res/')), '')
    ui_tmp, ui_res = _md5_lines(raw.get('uiTmpMd5')), _md5_lines(raw.get('uiResMd5'))
    common = sorted(set(k.rsplit('/', 1)[-1] for k in ui_tmp) & set(k.rsplit('/', 1)[-1] for k in ui_res))
    same_pages = diff_pages = 0
    for name in common:
        t = ui_tmp.get('/tmp/ui/' + name)
        r = ui_res.get('/res/ui/' + name)
        if t and r:
            if t == r:
                same_pages += 1
            else:
                diff_pages += 1
    lib_same_generation = bool(tmp_lib and res_lib and tmp_lib == res_lib)
    data = {'effectiveCfg': cfg_src, 'cfgFound': found_cfg,
            'resPath': res_path, 'startupLibPath': lib_path,
            'overlay': bool(_root(res_path) == '/tmp' or _root(lib_path) == '/tmp'),
            'rootSame': root_same, 'mixed': bool(res_path and lib_path and not root_same),
            'libMd5Tmp': tmp_lib, 'libMd5Res': res_lib,
            'libSameGeneration': lib_same_generation,
            'uiPages': {'tmp': len(ui_tmp), 'res': len(ui_res),
                        'common': len(common), 'same': same_pages, 'diff': diff_pages},
            'uiDiffPages': [n for n in common
                            if ui_tmp.get('/tmp/ui/' + n) != ui_res.get('/res/ui/' + n)][:12]}
    notes = []
    if not cfg_src:
        notes.append('三处 cfg 都没读到（/tmp > /mnt/extsd > /res/etc）：设备可能没有 EasyUI.cfg 或读取受限')
    else:
        notes.append('生效配置 = %s；resPath=%s / startupLibPath=%s'
                     % (cfg_src, res_path or '-', lib_path or '-'))
    if data['mixed']:
        notes.append('⚠️ **混搭**：resPath 与 startupLibPath 不在同一个根（%s vs %s）→ '
                     '跑的是「新库旧界面」或反之；把两者**成对更新**'
                     % (_root(res_path) or '?', _root(lib_path) or '?'))
    if common and diff_pages:
        notes.append('/tmp/ui 与 /res/ui 有 %d 页 ftu md5 不同（同 %d 页）→ 两个版本并存，'
                     '界面到底用哪一代由 resPath 决定' % (diff_pages, same_pages))
    if tmp_lib and res_lib and not lib_same_generation:
        notes.append('/tmp/lib 与 /res/lib 的 libzkgui.so **不是同一份** → 当前生效的是 resPath/'
                     'startupLibPath 指向的那代，别拿另一份当基线')
    return data, notes


def _any(*vals):
    """ok 判据：任一值非空。"""
    for v in vals:
        if isinstance(v, (dict, list, tuple, set)):
            if len(v):
                return True
        elif v not in (None, '', 0, False):
            return True
    return False


SECTIONS = (
    {'key': 'device', 'title': '① 设备信息', 'post': _post_device,
     'ok': lambda d: _any(d.get('model'), d.get('kernel')),
     'hint': '读不到型号：确认设备在线（adb devices 有 state=device）且未被裁剪掉 '
             'ro.product.model；平台靠 device_models.json 反查，未命中时留空由你按硬件查 '
             'flythings_hardware_info（检索：整机自检/设备信息/型号）',
     'probes': (_probe('model', 'getprop ro.product.model'),
                _probe('kernel', 'cat /proc/version'),
                _probe('easyuiVersion', 'getprop ro.easyui.version'),
                _probe('buildFingerprint', 'getprop ro.build.fingerprint'))},
    {'key': 'app', 'title': '② 应用状态', 'post': _post_app,
     'ok': lambda d: _any(d.get('initService'), d.get('appState'), d.get('zkguiPid')),
     'hint': '读不到 init.svc.zkswe / sys.zkapp.state / pid：应用可能没起，或该板属性名不同；'
             '重启应用一律 `setprop ctl.restart zkswe`（**不要 kill**，应用由类 init 服务托管）。'
             '检索：应用状态/重启应用/setprop（见 knowledge/devflow/device-deploy-budget.md）',
     'probes': (_probe('initService', 'getprop init.svc.zkswe'),
                _probe('appState', 'getprop sys.zkapp.state'),
                _probe('appDbg', 'getprop sys.zkapp.dbg'),
                _probe('pid', 'pidof zkgui', bb=True),
                _probe('uptime', 'cat /proc/uptime'))},
    {'key': 'display', 'title': '③ 显示', 'post': _post_display,
     'ok': lambda d: _any(d.get('virtualSize'), d.get('bitsPerPixel'), d.get('stride')),
     'hint': '读不到 /sys/class/graphics/fb0/*：板子可能没有 fb0（走 MI 显示通道）或路径不同；'
             '旋转口径看 EasyUI.cfg 的 rotateScreen/rotateTouch（/tmp > /mnt/extsd > /res/etc）。'
             '检索：显示/fb0/pan/双缓冲/旋转（knowledge/devflow/device-screenshot.md）',
     'probes': (_probe('virtualSize', 'cat /sys/class/graphics/fb0/virtual_size'),
                _probe('bitsPerPixel', 'cat /sys/class/graphics/fb0/bits_per_pixel'),
                _probe('stride', 'cat /sys/class/graphics/fb0/stride'),
                _probe('pan', 'cat /sys/class/graphics/fb0/pan'),
                _probe('easyuiCfg',
                       'cat /tmp/EasyUI.cfg 2>/dev/null; cat /mnt/extsd/EasyUI.cfg 2>/dev/null; '
                       'cat /res/etc/EasyUI.cfg 2>/dev/null', cap=400))},
    {'key': 'storage', 'title': '④ 存储', 'post': _post_storage,
     'ok': lambda d: _any(d.get('mounts')),
     'hint': '读不到挂载表：至少 `cat /proc/mounts` 一定在（不依赖 busybox）；'
             '/res 多为只读 squashfs，调试态看 /tmp/ui、固化态看 /res/ui；'
             '/tmp 是 tmpfs（吃内存，撑爆会 OOM 杀 zkgui）。读 /mnt/* 与 df 需要 busybox。'
             '检索：存储挂载/只读/update.img（knowledge/devflow/upgrade-pack-image.md）',
     'probes': (_probe('mounts', 'cat /proc/mounts', cap=400),
                _probe('mnt', 'ls /mnt', bb=True),
                _probe('tmpSpace', 'df -k /tmp', bb=True, cap=300),
                _probe('dataSpace', 'df -k /data', bb=True, cap=300),
                _probe('resList', 'ls /res/ui', bb=True, cap=300))},
    {'key': 'network', 'title': '⑤ 网络', 'post': _post_network,
     'ok': lambda d: _any(d.get('wlanMac'), d.get('wlan0'), d.get('defaultRoute'), d.get('dns')),
     'hint': '读不到 wlan0：设备可能无 WiFi 模组（接口名不同，先看 /proc/net/dev）；'
             '/proc/net/route 与 /etc/resolv.conf 不依赖 busybox，一定读得到。'
             'wpa_supplicant.conf 只在配过网时存在。'
             '检索：网络/wlan0/默认路由（knowledge/devflow/package-verify-playbook.md）',
     'probes': (_probe('wlanMac', 'cat /sys/class/net/wlan0/address'),
                _probe('wlanIf', 'ifconfig wlan0', bb=True, cap=400),
                _probe('route', 'cat /proc/net/route', cap=400),
                _probe('dns', 'cat /etc/resolv.conf'),
                _probe('wpaConf', 'ls -l /data/misc/wifi/wpa_supplicant.conf', bb=True))},
    {'key': 'bluetooth', 'title': '⑥ 蓝牙', 'post': _post_bluetooth,
     'ok': lambda d: _any(d.get('props'), d.get('rfkillState'), d.get('hciNodes')),
     'hint': '**本分区 ok=false 常常就是结论**：设备侧没有 BT 属性/rfkill/hci 节点 = 没插模组'
             '（AIC USB BT，需 aic_btusb.ko）；真要用蓝牙请查 components/ble 的 BLE 门面 + '
             'gatt 包（hciconfig/hcitool 手工验证）。检索：蓝牙/ble/gatt/hciconfig',
     'probes': (_probe('props', 'getprop', cap=300),
                _probe('rfkillName', 'cat /sys/class/rfkill/rfkill0/name 2>/dev/null'),
                _probe('rfkillState', 'cat /sys/class/rfkill/rfkill0/state 2>/dev/null'),
                _probe('hciNodes', 'ls /dev/hci* 2>/dev/null', bb=True))},
    {'key': 'input', 'title': '⑦ 输入', 'post': _post_input,
     'ok': lambda d: _any(d.get('nodes'), d.get('devices')),
     'hint': '读 /dev/input 节点需要 busybox（推 bin_tools/<平台>/busybox 到 /tmp/busybox）；'
             '/proc/bus/input/devices 不依赖 busybox。注入测试用随仓 touch 工具 + '
             'flythings_gen_ui_test。检索：触摸注入/输入节点（knowledge/devflow/touch-inject-autotest.md）',
     'probes': (_probe('nodes', 'ls /dev/input', bb=True, cap=300),
                _probe('devices', 'cat /proc/bus/input/devices', cap=400),
                _probe('touchTool', 'ls -l /data/touch /tmp/touch 2>/dev/null', bb=True))},
    {'key': 'peripheral', 'title': '⑧ 外设', 'post': _post_peripheral,
     'ok': lambda d: _any(d.get('relayKeys'), d.get('keys')) if d.get('preferencesRead') else False,
     'hint': '/data/preferences.json 读不到属常态（应用没写过偏好就没有该文件）；'
             '继电器/过零 IO 走 zkhardware 包（zeroOutput / 背光），值只在工程写过偏好后可见。'
             '检索：外设/继电器/relay/过零/zkhardware',
     'probes': (_probe('prefs', 'cat /data/preferences.json', cap=400),
                _probe('prefsPath', 'ls -l /data/preferences.json', bb=True),
                _probe('prefsAlt', 'cat /data/data/preferences.json 2>/dev/null', cap=300))},
    {'key': 'time', 'title': '⑨ 时间', 'post': _post_time,
     'ok': lambda d: _any(d.get('date'), d.get('epoch')),
     'hint': '取不到时间：设备 date 被裁剪 → 用 busybox date（本模块会自动试）；'
             'driftSeconds = 设备 - 宿主，**NTP 可用性不替你判断**（有 ntpd 才校时，'
             '无则每块板上电时间可能回到 1970）。检索：时间/NTP/校时',
     'probes': (_probe('dateRaw', 'date 2>/dev/null'),
                _probe('epoch', 'date +%s 2>/dev/null'),
                _probe('timezone', 'getprop persist.sys.timezone'),
                _probe('ntpTool', 'ls /bin/ntpd /usr/sbin/ntpd /system/bin/ntpd /bin/ntpdate',
                       bb=True))},
    {'key': 'libs', 'title': '⑩ 库清单', 'post': _post_libs,
     'ok': lambda d: _any(d.get('libs')),
     'hint': '要借哪个库 → 先 `readelf -d <lib>` 看 NEEDED/SONAME，再用 `--dyn-syms` 对照头文件核签名；'
             '**注册表没有 ≠ 平台没有**（设备 /lib 自带 nanovg/libpng/freetype/jpeg/mad/zlib，可 dlopen 免编译）；'
             '清单与三条纪律见 knowledge/devflow/device-preinstalled-libs.md（libmi_* 属框架内部，不要用）',
     'probes': (_probe('libList', 'ls -l /lib', bb=True, cap=6000),
                _probe('resLibList', 'ls -l /res/lib', bb=True, cap=2000))},
    {'key': 'deploy', 'title': '⑪ 部署一致性', 'post': _post_deploy,
     'ok': lambda d: bool(d.get('effectiveCfg')) and not d.get('mixed'),
     'hint': 'cfg 三处都没读到 → 读不到配置：确认固化态 /res/etc/EasyUI.cfg 存在，或本次用了 /tmp、'
             '/mnt/extsd 覆盖（优先级 /tmp > /mnt/extsd > /res/etc）。**resPath 与 startupLibPath 必须同源'
             '（同一次部署成对改）**：最常见坑是只换了 lib（startupLibPath=/tmp/lib/…）却把 resPath 留在 '
             '/res/ui/ → 跑的是「新库 + 旧界面」，症状正是「改了像没改 / 布局不对劲」。修法：两条一起指到'
             '同一次部署的产物，或 `rm -rf /tmp/lib /tmp/EasyUI.cfg /tmp/ui` 退回固化态后 '
             '`setprop ctl.restart zkswe`。检索：部署一致性/新库旧界面/resPath 混搭'
             '（knowledge/devflow/deploy-consistency-check.md）',
     'probes': (_probe('cfgTmp', 'cat /tmp/EasyUI.cfg 2>/dev/null', cap=500),
                _probe('cfgSd', 'cat /mnt/extsd/EasyUI.cfg 2>/dev/null', cap=500),
                _probe('cfgRes', 'cat /res/etc/EasyUI.cfg 2>/dev/null', cap=500),
                _probe('libMd5', 'md5sum /tmp/lib/libzkgui.so /res/lib/libzkgui.so 2>/dev/null',
                       bb=True, cap=400),
                _probe('uiTmpMd5', 'md5sum /tmp/ui/*.ftu 2>/dev/null', bb=True, cap=4000),
                _probe('uiResMd5', 'md5sum /res/ui/*.ftu 2>/dev/null', bb=True, cap=4000),
                _probe('dirs', 'ls -l /tmp/lib /tmp/ui 2>/dev/null', bb=True, cap=600))},
)


def _collect_section(dev, sec):
    """采集一个分区 → {'ok','hint','data','items','notes'}（items 是逐项取证）。"""
    raw, items = {}, []
    for p in sec['probes']:
        if p['bb'] and not dev.busybox:
            items.append({'name': p['name'], 'cmd': p['cmd'], 'ok': False, 'raw': '',
                          'note': dev.busyboxNote or '需要 busybox'})
            raw[p['name']] = ''
            continue
        cmd = ('%s %s' % (dev.busybox, p['cmd'])) if p['bb'] else p['cmd']
        txt = _clean(dev.sh(cmd))
        raw[p['name']] = txt
        items.append({'name': p['name'], 'cmd': cmd, 'ok': bool(str(txt).strip()),
                      'raw': _cap(txt, p['cap']), 'note': ''})
    data, notes = sec['post'](raw, dev)
    ok = bool(sec['ok'](data))
    return {'ok': ok, 'hint': '' if ok else sec['hint'], 'data': data,
            'items': items, 'notes': notes}


def _snapshot(dev, target):
    """十个分区快照（selfcheck 的正文）。"""
    sections = {}
    for sec in SECTIONS:
        try:
            sections[sec['key']] = _collect_section(dev, sec)
        except Exception as e:               # 单分区失败不拖垮整机快照（写明原因）
            sections[sec['key']] = {'ok': False, 'hint': sec['hint'], 'data': {},
                                    'items': [], 'notes': ['采集异常: %r' % e]}
    failed = [k for k, v in sections.items() if not v['ok']]
    return {
        'generatedAt': time.strftime('%Y-%m-%d %H:%M:%S'),
        'device': {'serial': target.get('serial'), 'model': target.get('model'),
                   'platform': target.get('platform'), 'adb': target.get('adb'),
                   'busybox': dev.busybox, 'connectNote': target.get('connectNote') or '',
                   'busyboxNote': dev.busyboxNote},
        'sections': sections,
        'summary': {'total': len(SECTIONS), 'ok': len(SECTIONS) - len(failed),
                    'failed': len(failed), 'failedSections': failed},
    }


# ────────────────────────────────────────────────────────── diff
# 天然会变的读数（两次快照之间必然不同）：不参与 changed 判定，单独列出来．
# 扩充唯一入口就在这里（真机抽查补入 `probe.wlanIf`：ifconfig 带收发包计数；
# `probe.*Space` / `data.*Space`：df 的 Used/Available 随进程运行变）。
_VOLATILE_KEYS = ('data.uptimeSeconds', 'data.date', 'data.epoch', 'data.hostEpoch',
                  'data.driftSeconds', 'data.tmpSpace', 'data.dataSpace',
                  'probe.uptime', 'probe.epoch', 'probe.dateRaw',
                  'probe.wlanIf', 'probe.tmpSpace', 'probe.dataSpace')


def _item_values(sec):
    """把分区压成可比对的扁平 {键: 值}（data + 每项 ok/raw）。"""
    flat = {'__ok': bool(sec.get('ok'))}
    data = sec.get('data') or {}
    for k in sorted(data):
        flat['data.%s' % k] = data[k]
    for it in sec.get('items') or []:
        flat['probe.%s' % it.get('name')] = it.get('raw') if it.get('ok') else None
    return flat


def _compute_diff(prev, cur):
    """与上次快照逐分区/逐项比对。"""
    ps = (prev or {}).get('sections') or {}
    cs = (cur or {}).get('sections') or {}
    sections, changed, added, removed = [], 0, 0, 0
    for key in [s['key'] for s in SECTIONS] or sorted(set(ps) | set(cs)):
        p, c = ps.get(key), cs.get(key)
        if p is None and c is not None:
            sections.append({'key': key, 'status': 'added', 'items': []})
            added += 1
            continue
        if c is None and p is not None:
            sections.append({'key': key, 'status': 'removed', 'items': []})
            removed += 1
            continue
        pv, cv = _item_values(p), _item_values(c)
        items, volatile = [], []
        for k in sorted(set(pv) | set(cv)):
            b, a = pv.get(k), cv.get(k)
            if b == a:
                continue
            row = {'key': k,
                   'before': _cap(json.dumps(b, ensure_ascii=False), 160),
                   'after': _cap(json.dumps(a, ensure_ascii=False), 160)}
            if k in _VOLATILE_KEYS:          # uptime/时间：天然会变，不算"状态变了"
                volatile.append(row)
                continue
            items.append(row)
        sec_out = {'key': key, 'status': 'changed' if items else 'same', 'items': items}
        if volatile:
            sec_out['volatileItems'] = volatile   # 仍然逐条给你，只是不当差异
        if items:
            changed += 1
        sections.append(sec_out)
    volatiles = sum(len(s.get('volatileItems') or []) for s in sections)
    return {'against': prev.get('generatedAt') if isinstance(prev, dict) else '',
            'sections': sections,
            'summary': {'changed': changed, 'added': added, 'removed': removed,
                        'same': len(sections) - changed - added - removed,
                        'volatileItems': volatiles,
                        'volatileNote': ('volatileItems = 天然会变的读数（uptime/时间/时差/df 空间/'
                                         'ifconfig），已逐条列出但不计入 changed')}}


def run_selfcheck(device='', diff_against='', out=''):
    """整机快照（十分区）+ 可选 diff + 可选落盘。返回 dict（kb_tools 只做 JSON 包装）。"""
    target = resolve_target(device)
    if not target['ok']:
        return {'ok': False, 'op': 'flythings_selfcheck',
                'error': {'code': 'NO_DEVICE', 'msg': target['error'],
                          'hint': target['hint'], 'retryable': True},
                'warnings': [], 'sections': {}, 'outPath': ''}
    dev = _dev_from_target(target)
    snap = _snapshot(dev, target)
    warnings = []
    if dev.busyboxNote:
        warnings.append(dev.busyboxNote)
    if snap['summary']['failed']:
        warnings.append('九个分区里有 %d 个 ok=false（读不到本身是结论，逐区看 hint）：%s'
                        % (snap['summary']['failed'],
                           ', '.join(snap['summary']['failedSections'])))
    out_path = ''
    if out:
        out_path = os.path.abspath(out)
        parent = os.path.dirname(out_path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        io.open(out_path, 'w', encoding='utf-8', newline='\n').write(
            json.dumps(snap, ensure_ascii=False, indent=2) + '\n')
    result = dict(snap)
    result.update({'ok': True, 'op': 'flythings_selfcheck', 'warnings': warnings,
                   'outPath': out_path, 'deviceParam': device,
                   'hint': '每分区给 {ok,hint,data}：ok=false 不是错误而是「读不到」，'
                           'hint 写明需要什么条件 / 去哪查'})
    if diff_against:
        base = os.path.abspath(diff_against)
        if not os.path.isfile(base):
            return {'ok': False, 'op': 'flythings_selfcheck',
                    'error': {'code': 'DIFF_BASE_MISSING',
                              'msg': 'diff_against 指向的快照文件不存在: %s' % base,
                              'hint': '先跑一次 selfcheck(out="<快照.json>") 再拿它做基线',
                              'retryable': True},
                    'warnings': warnings, 'sections': snap['sections'],
                    'device': snap['device'], 'outPath': out_path}
        try:
            prev = json.load(io.open(base, encoding='utf-8'))
        except ValueError as e:
            return {'ok': False, 'op': 'flythings_selfcheck',
                    'error': {'code': 'DIFF_BASE_BAD', 'msg': '基线快照不是合法 JSON: %s' % e,
                              'hint': 'diff_against 要用本 op 的 out 落盘的快照文件',
                              'retryable': True},
                    'warnings': warnings, 'sections': snap['sections'],
                    'device': snap['device'], 'outPath': out_path}
        result['diff'] = _compute_diff(prev, snap)
        result['diff']['basePath'] = base
        if not result['diff']['summary']['changed'] and not result['diff']['summary']['added'] \
                and not result['diff']['summary']['removed']:
            result['warnings'].append('与基线快照逐项一致（整机状态没变）')
    if out_path:
        result['affectedFiles'] = [out_path]
    return result


# ────────────────────────────────────────────────────────── bugreport
_SEVERITY = ('blocker', 'critical', 'major', 'minor', 'trivial')
# 平台推断过程中的跳过原因（不为空 = 有目录名不是平台名；留证不静默）
_PLAT_HIT_ERRORS = []


def _as_list(v):
    """steps / evidence 入参 → 列表：JSON 数组优先，否则按换行 / 分号 / 逗号切。"""
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v or '').strip()
    if not s:
        return []
    if s[:1] in ('[', '{'):
        try:
            d = json.loads(s)
        except ValueError:
            d = None
        if isinstance(d, list):
            return [str(x).strip() for x in d if str(x).strip()]
        if d is not None:
            return [s]
    return [p.strip() for p in re.split(r'[\n;,]', s) if p.strip()]


def _slug(title, limit=40):
    s = re.sub(r'[\\/:*?"<>|\s]+', '-', str(title or '').strip())
    s = re.sub(r'-{2,}', '-', s).strip('-')
    return (s[:limit] or 'bugreport')


def collect_judgement(device='', project_root=''):
    """真机判据（bugreport 自动附）：型号 / 固件 / 应用状态 / 最近 logcat 摘要。

    采不到就写明原因（未连设备 / 设备缺工具），**不静默**。
    """
    out = {'ok': False, 'device': {}, 'items': {}, 'logcat': [], 'note': ''}
    target = resolve_target(device)
    if not target['ok']:
        out['note'] = '未连设备或设备不可定位：%s（hint: %s）' % (target['error'], target['hint'])
        return out
    dev = _dev_from_target(target)
    out['device'] = {'serial': target['serial'], 'model': target['model'],
                     'platform': target['platform'], 'busybox': dev.busybox}
    items = {}
    items['model'] = dev.sh('getprop ro.product.model').strip()
    items['firmware'] = dev.sh('getprop ro.easyui.version').strip() or \
        _first_line(dev.sh('cat /proc/version'))
    items['buildFingerprint'] = dev.sh('getprop ro.build.fingerprint').strip()
    items['initService'] = dev.sh('getprop init.svc.zkswe').strip()
    items['appState'] = dev.sh('getprop sys.zkapp.state').strip()
    items['zkguiPid'] = dev.sh('pidof zkgui').strip() if not dev.busybox \
        else dev.sh_bb('pidof zkgui').strip()
    items['uptime'] = _first_line(dev.sh('cat /proc/uptime'))
    tail = dev.sh('logcat -d -s zkgui', timeout=30)
    lines = [l for l in str(tail or '').splitlines() if l.strip()]
    out['logcat'] = [_cap(l, 200) for l in lines[-40:]]
    if not out['logcat']:
        out['note'] = ('logcat -d -s zkgui 没有输出：设备可能没 logcat，或 zkgui 还没打过日志'
                       '（取证口径见 knowledge/devflow/device-deploy-budget.md）')
    out['items'] = items
    out['ok'] = True
    return out


def render_bugreport(title, symptom='', steps='', expected='', actual='', evidence='',
                     severity='major', judgement=None, project_root='', device='',
                     mcp_version='', generated_at=''):
    """缺陷单 markdown（格式对齐 2026-09-27 html2json A1~A8 那批）。"""
    j = judgement or {}
    dev = (j.get('device') or {})
    items = (j.get('items') or {})
    steps_l = _as_list(steps)
    ev_l = _as_list(evidence)
    platform = dev.get('platform') or _infer_platform(project_root) or '（未采集）'
    lines = ['# %s' % title, '',
             '- 日期：%s' % (generated_at or time.strftime('%Y-%m-%d %H:%M')),
             '- 平台：%s' % platform,
             '- 项目：%s' % (os.path.abspath(project_root) if project_root else '（未提供）'),
             '- 设备：%s' % (dev.get('serial') or device or '（未连设备）'),
             '- 严重级：%s' % severity,
             '- 生成：flythings_bugreport（MCP %s）；格式对齐 2026-09-27 html2json A1~A8 缺陷批'
             % (mcp_version or '?'), '',
             '## 现象', '', symptom.strip() or '（待补：一句话说清用户看到什么）', '',
             '## 复现步骤', '']
    if steps_l:
        lines += ['%d. %s' % (i, s) for i, s in enumerate(steps_l, 1)]
    else:
        lines.append('（待补：1. 上电/进入某页 2. 点哪个控件 3. 期望看到什么）')
    lines += ['', '## 期望 vs 实际', '',
              '- **期望**：%s' % (expected.strip() or '（待补）'),
              '- **实际**：%s' % (actual.strip() or '（待补）'), '',
              '## 真机判据', '']
    if j.get('ok'):
        lines += ['| 项 | 值 |', '|----|----|',
                  '| 型号 | %s |' % (items.get('model') or '（空）'),
                  '| 固件 / 内核 | %s |' % (items.get('firmware') or '（空）'),
                  '| build.fingerprint | %s |' % (items.get('buildFingerprint') or '（空）'),
                  '| 应用服务 init.svc.zkswe | %s |' % (items.get('initService') or '（空）'),
                  '| 应用状态 sys.zkapp.state | %s |' % (items.get('appState') or '（空）'),
                  '| zkgui pid | %s |' % (items.get('zkguiPid') or '（空，应用没起？）'),
                  '| /proc/uptime | %s |' % (items.get('uptime') or '（空）'),
                  '| busybox（取证用） | %s |' % (dev.get('busybox') or '（无）'), '']
        if j.get('logcat'):
            lines += ['最近 logcat（`logcat -d -s zkgui` 末 %d 行）：' % len(j['logcat']), '',
                      '```']
            lines += j['logcat']
            lines += ['```', '']
        else:
            lines += ['最近 logcat：%s' % (j.get('note') or '（无输出）'), '']
    else:
        lines += ['> 未采集到真机数据：%s' % (j.get('note') or '（未连设备 / 设备不可定位）'), '',
                  '> 补采：连上设备后重跑 `flythings_bugreport`（或先 `flythings_selfcheck` 看九分区），',
                  '> 采不到的分区在快照里是 `ok=false` + `hint`，不是没检查。', '']
    lines += ['## 证据', '']
    if ev_l:
        for p in ev_l:
            ok = os.path.isfile(p)
            lines.append('- `%s` —— %s' % (p, '文件存在' if ok else '**文件不存在**'))
    else:
        lines.append('（未提供证据文件：截图用 flythings_device_screenshot，抓屏/日志落盘后传路径）')
    lines += ['', '## 影响面 / 建议', '',
              '- 影响面：（待补：哪些页面 / 机型 / 场景受影响；是否阻塞出货）',
              '- 建议：（待补：根因方向 + 下一步动作；能静态判的先 flythings_layout_audit / '
              'check_all，能像素判的用 flythings_ui_visual(action="diff")）', '']
    return '\n'.join(lines)


def _infer_platform(project_root):
    """从工程构建产物目录名反查平台（.fsc/<平台> 或 .fun/<平台>）；查不到回 ''。"""
    if not project_root:
        return ''
    try:
        import platforms as pl
    except Exception as e:                    # platforms 不可用不算错误（只是推不出平台）
        return ''
    for d in ('.fsc', '.fun'):
        base = os.path.join(project_root, d)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            try:
                hit = pl.resolve(name) or ''
            except Exception as e:            # 目录名不是平台名 → 视为没推出
                hit = ''
                _PLAT_HIT_ERRORS.append('%s/%s: %r' % (d, name, e))
            if hit:
                return hit
    return ''


def build_bugreport(title='', project_root='', device='', symptom='', steps='',
                    expected='', actual='', evidence='', severity='', out='',
                    mcp_version=''):
    """缺陷单生成（写 markdown 到 temp/bugreports/）。返回 dict。"""
    if not str(title or '').strip():
        return {'ok': False, 'op': 'flythings_bugreport',
                'error': {'code': 'BAD_PARAMS', 'msg': 'title 必填（缺陷单标题）',
                          'hint': 'flythings_bugreport(title="<一句话现象>")；'
                                  '其余参数有默认值，可只给 title',
                          'retryable': True},
                'warnings': []}
    sev = str(severity or 'major').strip().lower()
    warnings = []
    if sev not in _SEVERITY:
        warnings.append('severity=%r 不在 %s 里，按 major 记' % (severity, '/'.join(_SEVERITY)))
        sev = 'major'
    ev_l = _as_list(evidence)
    missing = [p for p in ev_l if not os.path.isfile(p)]
    if missing:
        return {'ok': False, 'op': 'flythings_bugreport',
                'error': {'code': 'EVIDENCE_MISSING',
                          'msg': '证据文件不存在: %s' % ', '.join(missing),
                          'hint': '先落盘证据（flythings_device_screenshot 出图 / 日志重定向到文件）'
                                  '再把真实路径传进来；也可以先不传 evidence 生成框架稿',
                          'retryable': True},
                'warnings': warnings}
    judgement = collect_judgement(device, project_root)
    if not judgement['ok']:
        warnings.append(judgement['note'])
    if not project_root:
        warnings.append('未传 project_root → 平台只能靠设备反查；产物落 MCP 仓库 temp/bugreports/')
    root = os.path.abspath(project_root) if project_root else MCP_ROOT
    stamp = time.strftime('%Y%m%d-%H%M')
    out_path = os.path.abspath(out) if out else os.path.join(
        root, 'temp', 'bugreports', '%s-%s.md' % (stamp, _slug(title)))
    parent = os.path.dirname(out_path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    md = render_bugreport(title, symptom, steps, expected, actual, evidence, sev,
                          judgement, project_root, device, mcp_version)
    io.open(out_path, 'w', encoding='utf-8', newline='\n').write(md)
    preview = md.splitlines()[:20]
    return {'ok': True, 'op': 'flythings_bugreport', 'path': out_path,
            'preview': preview, 'lines': len(md.splitlines()),
            'severity': sev, 'judgement': judgement,
            'affectedFiles': [out_path], 'warnings': warnings,
            'hint': '缺陷单已落盘：把 path 交给用户评审/提交；补齐「（待补）」处即可提交'}
