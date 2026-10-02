# -*- coding: utf-8 -*-
"""adb 单一入口（PC 端 adb 解析 + 设备探测 + 型号→平台匹配）——v0.27.84 起。

为什么要单独一个文件（2026-09-17：「adb 工具随包入库，客户不必另装 SDK」）：
  v0.27.83 之前，仓库里 **6 处各写一份**adb 定位逻辑（project_tools / ui_tools/
  device_screenshot / i18n_tools / components/fonts/scripts/device_font_check /
  components/ui_v1/WheelPicker/example/tools/deploy ——该自绘包 2026-09-19 已移除，
历史事实保留），且都写死 `'adb'` 字面量或
只认本机装 SDK 的路径 → 客户机没装 Android SDK 就「找不到 adb」，报错各写各的。
现在**只有这里**知道 adb 在哪，其余模块一律 `resolve_adb()`。

解析优先级（resolve_adb）：
  ① 环境变量 `ADB` / `FLYTHINGS_ADB`（兼容旧名 `ADB_PATH`）—— 显式指定永远优先
  ② **随包**`tools/adb/adb.exe`（Windows）/ `tools/adb/adb`（非 Windows）
     —— 随 MCP 分发，客户开箱可用（含 AdbWinApi.dll / AdbWinUsbApi.dll）
  ③ PATH 里的 `adb`
找不到回 `''`（调用方决定怎么提示；本模块给现成文案 `adb_missing_hint()`）。

⚠️ 不要把本机绝对路径写进本文件/任何文档（隐私闸门 scripts/smoke.py 会拦）。
⚠️ 设备型号表只放**型号字符串**（`ro.product.model`），不放内网 IP：数据在 `device_models.json`，来源=本仓实测记录；不确定的留空并标 `todo`。

CLI（排查用，零副作用）：
    python adb_tools.py              # 打印解析结果 + 设备列表
    python adb_tools.py devices      # 只列设备
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLED_DIR = os.path.join(HERE, 'tools', 'adb')
MODELS_JSON = os.path.join(HERE, 'device_models.json')

# 显式指定 adb 的环境变量（按优先级）
ENV_VARS = ('ADB', 'FLYTHINGS_ADB', 'ADB_PATH')

DEFAULT_TIMEOUT = 15


# ------------------------------------------------------------------ 定位 adb
def bundled_adb_dir():
    """随包 adb 目录（可能不存在——老版本/裁剪分发）。"""
    return BUNDLED_DIR


def bundled_adb():
    """随包 adb 可执行文件路径；不存在回 ''。Windows 用 adb.exe，其余平台用 adb。"""
    names = ('adb.exe', 'adb') if os.name == 'nt' else ('adb', 'adb.exe')
    for n in names:
        p = os.path.join(BUNDLED_DIR, n)
        if os.path.isfile(p):
            return p
    return ''


def resolve_adb():
    """返回可用的 adb 路径（'' = 没找到）。优先级见模块 docstring。"""
    return resolve_adb_info()['path']


def resolve_adb_info():
    """返回 {'path', 'source', 'envVar'}；source ∈ env / bundled / path / none。"""
    for var in ENV_VARS:
        p = (os.environ.get(var) or '').strip()
        if p and os.path.isfile(p):
            return {'path': p, 'source': 'env', 'envVar': var}
    b = bundled_adb()
    if b:
        return {'path': b, 'source': 'bundled', 'envVar': ''}
    import shutil
    w = shutil.which('adb')
    if w:
        return {'path': w, 'source': 'path', 'envVar': ''}
    return {'path': '', 'source': 'none', 'envVar': ''}


def adb_missing_hint():
    """找不到 adb 时的可执行提示（各调用方共用一套文案）。"""
    return ('找不到 adb：① 本包自带 tools/adb/adb.exe（Windows）应随包分发——'
            '若被删，从完整包拷回；② 或设环境变量 ADB=<adb 完整路径>；'
            '③ 或装 Android platform-tools 并放进 PATH。'
            '（本机 adb 不可用时，fun launch/build 仍可工作：fun 自带 adb 客户端）')


def adb_version(adb='', timeout=DEFAULT_TIMEOUT):
    """adb version 第二行（版本号）+ 路径；失败回 ('', error)。"""
    a = adb or resolve_adb()
    if not a:
        return '', adb_missing_hint()
    rc, out, err = _run([a, 'version'], timeout=timeout)
    if rc != 0:
        return '', (err or out or 'adb version 失败').strip()[:200]
    lines = [l.strip() for l in (out or '').splitlines() if l.strip()]
    ver = ''
    for l in lines:
        if l.lower().startswith('version '):
            ver = l.split(' ', 1)[1].strip()
    return ver, ''


# ------------------------------------------------------------------ 跑 adb
def _run(args, timeout=DEFAULT_TIMEOUT):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, encoding='utf-8', errors='replace')
        return r.returncode, (r.stdout or ''), (r.stderr or '')
    except subprocess.TimeoutExpired:
        return 124, '', 'adb 执行超时（>%ss）' % timeout
    except Exception as e:
        return 1, '', str(e)


def sh(adb, serial, cmd, timeout=DEFAULT_TIMEOUT):
    """`adb [-s serial] shell <cmd>`，返回 stdout 文本（失败回 ''）。"""
    a = adb or resolve_adb()
    if not a:
        return ''
    args = [a] + (['-s', serial] if serial else []) + ['shell', cmd]
    rc, out, err = _run(args, timeout=timeout)
    return (out or '') if rc == 0 else (out or '')


def shell_rc(adb, serial, cmd, timeout=DEFAULT_TIMEOUT):
    """`adb [-s serial] shell <cmd>`，返回 (rc, stdout, stderr)。

    `sh()` 只回文本（rc 非 0 时也回文本，调用方判不出失败）；
测试跑批这类**必须判 rc**的场景用本函数。
    """
    a = adb or resolve_adb()
    if not a:
        return 1, '', 'adb 不可用'
    args = [a] + (['-s', serial] if serial else []) + ['shell', cmd]
    return _run(args, timeout=timeout)


def push(adb, serial, local, remote, timeout=120):
    """`adb [-s serial] push <local> <remote>`，返回 (rc, stdout, stderr)。"""
    a = adb or resolve_adb()
    if not a:
        return 1, '', 'adb 不可用'
    if not os.path.isfile(local):
        return 1, '', '本地文件不存在: %s' % local
    args = [a] + (['-s', serial] if serial else []) + ['push', local, remote]
    return _run(args, timeout=timeout)


def start_server(adb='', timeout=DEFAULT_TIMEOUT):
    """确保 adb host server 在跑（fun 也走 127.0.0.1:5037，起一次对双方都有利）。"""
    a = adb or resolve_adb()
    if not a:
        return False
    rc, _, _ = _run([a, 'start-server'], timeout=timeout)
    return rc == 0


# 应用由 init（类 init 服务）托管：**不能用 kill 重启**，只能让 init 回收再拉起
RESTART_PROP = 'ctl.restart %s'


def restart_app(adb, serial, name='zkgui', service='zkswe', extra_path='/tmp/busybox',
                wait=6.0, poll_interval=0.5, allow_kill=False):
    """重启应用进程 —— **setprop 控制（框架口径），默认不 kill**。

框架事实（2026-09-28 需求方定：应用由类 init 服务托管，不允许 kill）：
      · 应用进程不是普通进程，`kill` 它（哪怕 -TERM）都不是框架认可的重启方式；
正确姿势 = 让 init 回收再拉起 → `setprop ctl.restart zkswe`
        （`/etc/init.rc`：`service zkswe /bin/zkgui`）。
      · 厂商 CLI `fun launch` 内部同样走 `ctl.restart`（二进制里可见 `ctl.restart`+`zkswe`
        +`setprop`，无 kill）；手动部署（推 `/tmp` + `EasyUI.cfg`）之后也用同一句让它生效。
      · 历史教训：脚本里反复 `kill -9 zkgui` / `busybox killall zkgui` 之后，现场出现过
        「触摸注入命令成功、应用不响应」「整板掉网」等现象（当时因果未确证，现按框架口径统一
不用 kill）→ 这也是本函数默认 `allow_kill=False` 的原因。
      · 仅当个别板子 `setprop` 静默失败、且调用方显式传 `allow_kill=True` 时，才回退
        `kill -TERM`（仍然不用 -9）。

返回可取证 dict：{found, oldPid, newPid, method, restarted, detail}
    method ∈ {'setprop', 'kill -TERM', 'none'}；restarted=True 表示 pid 确实换了。
    """
    res = {'found': False, 'oldPid': '', 'newPid': '', 'method': 'none',
           'restarted': False, 'detail': ''}
    bb = ''
    if extra_path:
        bb = (extra_path.rstrip('/') + '/') if sh(adb, serial, 'test -x %s && echo 1' % extra_path).strip() else ''
    pid_cmd = ('%spidof %s' % (bb, name)) if bb else ('pidof %s' % name)

    def _pids():
        out = sh(adb, serial, pid_cmd)
        return [p for p in (out or '').replace('\n', ' ').split() if p.isdigit()]

    before = _pids()
    res['found'] = bool(before)
    res['oldPid'] = before[0] if before else ''

    prop = RESTART_PROP % service
    sh(adb, serial, 'setprop %s' % prop)
    waited = 0.0
    while waited < wait:
        time.sleep(poll_interval)
        waited += poll_interval
        now = _pids()
        if now and (not res['oldPid'] or now[0] != res['oldPid']):
            res['method'] = 'setprop'
            res['newPid'] = now[0]
            res['restarted'] = True
            break
    if res['restarted']:
        res['detail'] = ('setprop %s → 新 pid %s（旧 %s）' % (prop, res['newPid'], res['oldPid'] or '-'))
        return res

    # —— 兜底（仅显式要求）：个别板子 setprop 通道不可用时才 kill（不用 -9）
    if allow_kill and res['oldPid']:
        sh(adb, serial, 'kill -TERM %s' % res['oldPid'])
        waited = 0.0
        while waited < wait:
            time.sleep(poll_interval)
            waited += poll_interval
            now = _pids()
            if now and now[0] != res['oldPid']:
                res['method'] = 'kill -TERM'
                res['newPid'] = now[0]
                res['restarted'] = True
                break

    res['detail'] = ('setprop %s 后 %.1fs 内未观察到新 pid（旧 %s）；'
                     '%s请现场断电重上电，别用 kill（应用由 init 托管）'
                     % (prop, wait, res['oldPid'] or '无',
                        '' if allow_kill else 'allow_kill=True 可试 kill -TERM 兜底；'))
    return res


def connect(target, adb='', timeout=DEFAULT_TIMEOUT):
    """`adb connect <host:port>`（网络接入）。返回 (ok, 输出文本)。

窄带设备走 WiFi 时不插 USB：先 connect 才进 devices 列表。
    ⚠️ 不在这里 `adb reboot` / kill-server —— 现场板子多，动作只做必要的。
    """
    a = adb or resolve_adb()
    if not a:
        return False, adb_missing_hint()
    rc, out, err = _run([a, 'connect', str(target)], timeout=timeout)
    txt = ((out or '') + (err or '')).strip()
    ok = rc == 0 and 'cannot' not in txt.lower() and 'failed' not in txt.lower()
    return ok, txt[:300]


# ------------------------------------------------------------------ 设备探测
def parse_devices_l(text):
    """解析 `adb devices -l` 输出 → [{serial,state,model,product,device}]。

行形如：`192.168.x.x:5555  device product:swaio model:Zkswe_V85X_SPINOR device:swaio`
    （网络设备常常**没有**-l 附加字段，此时 model/product 为空 → 需另问 getprop）
    """
    out = []
    for line in (text or '').splitlines():
        line = line.strip()
        if not line or line.lower().startswith('list of devices'):
            continue
        if line.startswith('*'):                     # `* daemon started successfully *`
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        if state not in ('device', 'offline', 'unauthorized', 'no', 'recovery', 'sideload'):
            continue
        d = {'serial': serial, 'state': state, 'model': '', 'product': '', 'device': ''}
        for kv in parts[2:]:
            if ':' not in kv:
                continue
            k, v = kv.split(':', 1)
            if k in ('model', 'product', 'device'):
                d[k] = v
        out.append(d)
    return out


def list_devices_l(adb='', timeout=DEFAULT_TIMEOUT):
    """跑 `adb devices -l`。返回 (devices, error)。"""
    a = adb or resolve_adb()
    if not a:
        return [], adb_missing_hint()
    rc, out, err = _run([a, 'devices', '-l'], timeout=timeout)
    if rc != 0:
        return [], (err or out or 'adb devices 失败').strip()[:300]
    return parse_devices_l(out), ''


def getprop_model(adb, serial, timeout=DEFAULT_TIMEOUT):
    """问设备 `getprop ro.product.model`（网络设备 `devices -l` 常不带 model）。"""
    txt = (sh(adb, serial, 'getprop ro.product.model', timeout=timeout) or '').strip()
    return txt.splitlines()[0].strip() if txt else ''


def probe_devices(adb='', timeout=DEFAULT_TIMEOUT, with_model=True):
    """设备探测（build_ui_flow / 部署类工具的**统一入口**）。

返回：
      {'ok':bool, 'adb':路径, 'adbSource':env|bundled|path|none, 'adbVersion':...,
       'count':int, 'online':[dev...], 'offline':[...], 'error':''}
每个在线 dev 额外带：'platform'（型号表命中的平台规范名，未命中回 '')、
      'modelSource'（devices-l / getprop / ''）、'modelConfidence'（confirmed/todo/unknown）
    """
    a = adb or resolve_adb()
    info = {'ok': False, 'adb': a, 'adbSource': resolve_adb_info()['source'],
            'adbVersion': '', 'count': 0, 'online': [], 'offline': [], 'error': ''}
    if not a:
        info['error'] = adb_missing_hint()
        return info
    ver, verr = adb_version(a, timeout=timeout)
    info['adbVersion'] = ver
    try:
        start_server(a, timeout=timeout)
    except Exception as e:                            # 起 server 失败不阻断（可能已有）
        info['serverError'] = str(e)[:200]             # 不静默：失败原因回传给调用方
    devs, err = list_devices_l(a, timeout=timeout)
    if err and not devs:
        info['error'] = err
        return info
    for d in devs:
        if d['state'] == 'device':
            if with_model:
                if not d['model']:
                    m = getprop_model(a, d['serial'], timeout=timeout)
                    if m:
                        d['model'] = m
                        d['modelSource'] = 'getprop'
                else:
                    d['modelSource'] = 'devices-l'
            d.setdefault('modelSource', '')
            hit = lookup_model(d['model'])
            d['platform'] = hit['platform']
            d['modelConfidence'] = hit['confidence']
            d['modelNote'] = hit['note']
            info['online'].append(d)
        else:
            info['offline'].append(d)
    info['count'] = len(info['online'])
    info['ok'] = True
    return info


def device_string(d):
    """设备的一行人话（serial + model + 平台匹配情况）。"""
    bits = [d.get('serial', '?')]
    if d.get('model'):
        bits.append('model=%s' % d['model'])
    else:
        bits.append('model=未知（设备未回报 ro.product.model）')
    if d.get('platform'):
        bits.append('→ 平台 %s' % d['platform'])
    elif d.get('modelConfidence') == 'todo':
        bits.append('→ 平台待确认（型号表登记为 todo）')
    else:
        bits.append('→ 平台未知（型号表没这条）')
    return ' '.join(bits)


# ------------------------------------------------------------------ 型号 → 平台
def load_models():
    """读 device_models.json（缺失/损坏回空表，不抛）。"""
    try:
        d = json.load(io.open(MODELS_JSON, encoding='utf-8'))
        return (d.get('models') or {}), d
    except Exception:
        return {}, {}


def lookup_model(model):
    """型号字符串 → {'platform', 'confidence', 'note'}。

    confidence：confirmed（本仓实测记录）/ todo（登记但待确认）/ unknown（没登记）
匹配忽略大小写与首尾空白（不做模糊猜测——猜错会把工程推到别的机器上）。
    """
    key = (model or '').strip()
    none = {'platform': '', 'confidence': 'unknown', 'note': '型号表未登记', 'source': ''}
    if not key:
        return dict(none, note='设备未回报 ro.product.model')
    models, _ = load_models()
    if key in models:
        m = models[key]
        return {'platform': m.get('platform') or '',
                'confidence': m.get('confidence') or 'unknown',
                'note': m.get('note') or '',
                'source': m.get('source') or ''}
    low = {k.lower(): v for k, v in models.items()}
    if key.lower() in low:
        m = low[key.lower()]
        return {'platform': m.get('platform') or '',
                'confidence': m.get('confidence') or 'unknown',
                'note': m.get('note') or '',
                'source': m.get('source') or ''}
    return none


def match_platform(model, platform):
    """设备型号 vs 工程平台：返回 'match' / 'mismatch' / 'unknown'。

    unknown（型号没登记 / 设备没回报）**不等于**mismatch：fun 自己会在 launch 时
做平台校验并 FATAL，所以这里不拦，只如实说明。
    """
    hit = lookup_model(model)
    if not hit['platform']:
        return 'unknown'
    import platforms as pl
    want = pl.normalize(platform or '')
    got = pl.normalize(hit['platform'])
    if not want or not got:
        return 'unknown'
    return 'match' if want == got else 'mismatch'


# ------------------------------------------------------------------ 设备侧文件
def local_md5(path):
    try:
        h = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
        return h.hexdigest().upper()
    except Exception:
        return ''


def local_size(path):
    try:
        return os.path.getsize(path)
    except Exception:
        return None


# 本会话已给哪些设备推过 busybox（避免每次比对都重推 1 MB）
_BUSYBOX_PUSHED = set()


def bundled_busybox(platform=''):
    """随仓的设备端 busybox（bin_tools/<平台小写键>/busybox）；没有回 ''。

设备 rootfs 是裁剪版（无 wc/md5sum/ls -l 不齐）→ 拿它当“取 md5”的兜底。
    """
    try:
        import platforms as pl
        key = pl.bin_tool_dir(platform) if platform else ''
    except Exception:
        key = ''
    cands = []
    if key:
        cands.append(os.path.join(HERE, 'bin_tools', key, 'busybox'))
    if not cands:
        root = os.path.join(HERE, 'bin_tools')
        if os.path.isdir(root):
            for d in sorted(os.listdir(root)):
                p = os.path.join(root, d, 'busybox')
                if os.path.isfile(p):
                    cands.append(p)
    for p in cands:
        if os.path.isfile(p):
            return p
    return ''


def ensure_busybox(adb, serial, platform='', timeout=DEFAULT_TIMEOUT):
    """把随仓 busybox 推到设备 `/tmp/busybox`（已推过/本来就有则直接复用）。

返回远端路径（'' = 不可用）。失败不抛（调用方降级为比字节数），但会带回来。
    """
    a = adb or resolve_adb()
    if not a or not serial:
        return ''
    key = (serial, platform or '')
    if key in _BUSYBOX_PUSHED:
        return '/tmp/busybox'
    if '1' == (sh(a, serial, 'test -x /tmp/busybox && echo 1', timeout=timeout) or '').strip()[:1]:
        _BUSYBOX_PUSHED.add(key)
        return '/tmp/busybox'
    local = bundled_busybox(platform)
    if not local:
        return ''
    rc, out, err = _run([a] + (['-s', serial] if serial else []) +
                        ['push', local, '/tmp/busybox'], timeout=90)
    if rc != 0:
        return ''
    sh(a, serial, 'chmod 777 /tmp/busybox', timeout=timeout)
    if (sh(a, serial, 'test -x /tmp/busybox && echo 1', timeout=timeout) or '').strip()[:1] == '1':
        _BUSYBOX_PUSHED.add(key)
        return '/tmp/busybox'
    return ''


def remote_file_info(adb, serial, path, platform='', timeout=DEFAULT_TIMEOUT):
    """设备侧文件的 {'size': int|None, 'md5': str}。

    ⚠️ 本机实测（2026-09-17，Z21 真机）三个坑，都在这里修完了：
      ① `wc -c < file` 返回**空**（裁剪 rootfs 没 wc）→ 尺寸只能靠 `ls -l`；
      ② `md5sum` / `busybox md5sum` 都没有（busybox 不在 PATH）→ 用**随仓**
         `bin_tools/<平台>/busybox`（先试设备上已有的 `/tmp/busybox`）拿 md5；
      ③ `ls -l` 的**第 1 个数字是硬链接数（1）不是字节数**→ 必须按列取第 5 列，
旧写法取第一个数字会把每个文件都报成 1 字节（假 stale）。
拿不到就如实回 error（不静默）。
    """
    a = adb or resolve_adb()
    out = {'size': None, 'md5': '', 'error': '', 'busybox': ''}
    if not a:
        out['error'] = adb_missing_hint()
        return out
    txt = sh(a, serial,
             '(wc -c < %s 2>/dev/null); '
             '(md5sum %s 2>/dev/null); '
             '(busybox md5sum %s 2>/dev/null); '
             '(ls -l %s 2>/dev/null)' % ((path,) * 4), timeout=timeout)
    size_ls = None
    for line in (txt or '').splitlines():
        line = line.strip()
        if not line or line.endswith(':'):
            continue
        parts = line.split()
        if len(parts) >= 2 and _is_md5(parts[0]):
            out['md5'] = parts[0].upper()
        elif len(parts) == 1 and parts[0].isdigit():
            out['size'] = int(parts[0])                  # wc -c 的裸数字
        elif len(parts) >= 5 and len(parts[0]) >= 9 and parts[0][0] in '-bcdlps':
            # `-rw-rw-rw- 1 0 0 186 Sep 17  2026 main.ftu` → 第 5 列才是字节数
            if parts[4].isdigit():
                size_ls = int(parts[4])
    if out['md5'] == '':                                 # ② busybox 兜底拿 md5
        bb = ensure_busybox(a, serial, platform, timeout=timeout)
        if bb:
            out['busybox'] = bb
            m = sh(a, serial, '%s md5sum %s 2>/dev/null' % (bb, path), timeout=timeout)
            tok = (m or '').split()
            if tok and _is_md5(tok[0]):
                out['md5'] = tok[0].upper()
            if out['size'] is None:
                w = sh(a, serial, '%s wc -c < %s 2>/dev/null' % (bb, path), timeout=timeout)
                wt = (w or '').split()
                if wt and wt[0].isdigit():
                    out['size'] = int(wt[0])
    if out['size'] is None:
        out['size'] = size_ls
    if out['size'] is None and not out['md5']:
        out['error'] = ('设备侧读不到 %s（文件不存在？或设备 rootfs 缺 busybox）' % path)
    return out


def _is_md5(tok):
    return len(tok) == 32 and all(c in '0123456789abcdefABCDEF' for c in tok)


def compare_with_device(adb, serial, local_path, remote_path, platform='',
                        timeout=DEFAULT_TIMEOUT):
    """本地文件 vs 设备侧文件：{'localBytes','deviceBytes','localMd5','deviceMd5','same','reason'}。

    `same=True` 判定口径：能拿到两边 md5 就比 md5；拿不到 md5 时退化成比字节数；
两边都拿不到 → same=False 且 reason 说明「无法判定」（不假装一致）。
    """
    r = {'localPath': local_path, 'devicePath': remote_path,
         'localBytes': local_size(local_path), 'deviceBytes': None,
         'localMd5': local_md5(local_path), 'deviceMd5': '', 'same': False, 'reason': ''}
    if not os.path.isfile(local_path):
        r['reason'] = '本地文件不存在：%s' % local_path
        return r
    rem = remote_file_info(adb, serial, remote_path, platform=platform, timeout=timeout)
    r['deviceBytes'] = rem['size']
    r['deviceMd5'] = rem['md5']
    if r['localMd5'] and rem['md5']:
        r['same'] = (r['localMd5'] == rem['md5'])
        r['reason'] = '' if r['same'] else 'md5 不一致'
    elif r['localBytes'] is not None and rem['size'] is not None:
        r['same'] = (r['localBytes'] == rem['size'])
        r['reason'] = '' if r['same'] else '字节数不一致（设备端无 md5sum，退化为比字节）'
    else:
        r['reason'] = rem['error'] or '拿不到设备侧信息，无法判定'
    return r


# ------------------------------------------------------------------ 提示文案
def install_hint(platform='', devices=None, error=''):
    """`needDeviceInput=true` 时给用户的**照做清单**（2026-09-17：运行后要提示是否需要安装）。"""
    lines = ['未检测到可用的 FlyThings 设备（adb devices 里没有 state=device 的机器）。',
             '请按顺序自查（① 最容易漏 —— 很多机器根本没装 adb 驱动）：']
    lines.append('① **ADB 驱动**：Windows 上 USB 接入需要 adb 驱动（本包已带 adb 程序本身：'
                 'tools/adb/adb.exe + AdbWinApi.dll + AdbWinUsbApi.dll；'
                 '驱动本身若未装，设备管理器里会出现带叹号的未知设备 → 装厂家 USB 驱动或用 '
                 'Zadig/WinUSB 指定 Android ADB Interface）；'
                 '装完先在本机跑 `tools/adb/adb.exe kill-server && tools/adb/adb.exe devices`。')
    lines.append('② **设备侧**：开发者选项 → 打开「USB 调试」，插上后设备会弹授权框 → 勾选「一律允许」；'
                 '没授权时 adb 会显示 unauthorized（不是没连上）。')
    lines.append('③ **网络接入（推荐给整机/板子）**：设备与电脑同一局域网时，'
                 "用 device='<设备IP>:5555' 重试（本工具会先 adb connect 再推）；"
                 '设备端需开 adb over TCP（`setprop service.adb.tcp.port 5555` 后重启 adbd）。')
    if devices:
        lines.append('④ 当前 adb 可见但**不处于 device 状态**的条目：%s'
                     % ', '.join('%s(%s)' % (d['serial'], d['state']) for d in devices[:5]))
    if error:
        lines.append('⑤ adb 侧报错原文：%s' % str(error)[:200])
    if platform:
        lines.append('（目标工程平台 = %s）' % platform)
    return '\n'.join(lines)


def multi_device_hint(devices, platform=''):
    """多台在线设备：不猜，列清楚 + 要求显式 device=。（2026-09-17 口径）

    ⚠️ 实测（2026-09-17 首测 / 09-17 复测 / **2026-09-28 三测**，platform-tools 37.0.1 与 31.0.3 一样）：多设备在线时 `fun launch` **不管有没有 `-s` 都直接 FATAL `more than one device/emulator`**
    （fun 自带 Go adb 客户端发旧式 `host:transport <serial>`（空格分隔），adb 只认
    `host:transport:<serial>`（冒号）：裸 socket 实测空格形式回 FAIL、冒号形式 OKAY）——
    **09-28 版 fun（`v0.0.2+2609281006_e09dc96`）仍未修**。
两条路：① 垫片 `scripts/adb_transport_shim.py`（5037 上把空格改写成冒号再转发给另起端口的真 adb；
实测 5 台在线时 `fun launch -s <ip>` 精确推到指定设备，设备侧 md5 与本地一致、其它设备未动）；
    ② 先让其它机器从 adb 列表里消失（`adb disconnect`）。
这条修正了 `cli-fun-toolchain.md §6` 里「多设备时 fun 静默取列表第一个」的旧结论。
    """
    lines = ['检测到 %d 台在线设备，**不自动选择**（多设备下 fun launch 会 FATAL，见下）：'
             % len(devices)]
    for d in devices:
        mp = match_platform(d.get('model'), platform) if platform else 'unknown'
        tag = {'match': '✅ 与工程平台一致', 'mismatch': '❌ 与工程平台不一致（fun 会 FATAL platform not match）',
               'unknown': '❓ 平台未知（型号未登记/未回报）'}[mp]
        lines.append('  · %s —— %s' % (device_string(d), tag))
    lines.append("① 先传 device='<serial|IP>' 让我们只对这台干活（探测/比对/续推）；"
                 '② 若仍报 `more than one device/emulator`（09-28 三测：新老 fun 都一样，fun 的 adb 客户端用旧式 '
                 '`host:transport <serial>`，platform-tools 只认 `host:transport:<serial>`）→ '
                 'ⓐ 用垫片 `scripts/adb_transport_shim.py`（把 5037 的请求改写成冒号形式再转发给另起端口的真 adb；'
                 '已实测多设备在线时能精确推到 `-s` 指定设备），或 '
                 'ⓑ 把**其它设备临时下线**再推：`adb disconnect <其它serial>`（网络设备，可逆，'
                 '推完再 `adb connect` 回去）或拔掉其它 USB。')
    return '\n'.join(lines)


def fun_multi_device_error(text):
    """从 fun 的输出里识别「多设备导致 transport 失败」这个已知机制（返回人话或 ''）。"""
    t = (text or '')
    if 'more than one device/emulator' not in t:
        return ''
    return ('设备端报 `more than one device/emulator`：实测（2026-09-17 / **09-28 三测，含 09-28 新版 fun**）**不是你的选机问题**——'
            'fun 的 adb 客户端用旧式 `host:transport <serial>`（空格分隔），platform-tools 只认 '
            '`host:transport:<serial>`，只要 adb 列表里不止一台就必失败。处置：'
            '① 用垫片 `scripts/adb_transport_shim.py`（多设备在线也能精确推到 -s 指定设备，已实测）；'
            '② 或把其它设备临时下线（`adb disconnect <其它serial>`，可逆；USB 则拔掉）后重试，推完再连回。')


def stale_hint(items):
    """`staleOnDevice=true` 的人话（把「改了 json 忘 pack / 推了没生效」两个坑堵住）。"""
    lines = ['⚠️ 设备上跑的还是**旧版**（设备侧文件与本地不一致）：']
    for it in items:
        lines.append('  · %s → 设备 %s：本地 %s 字节%s，设备 %s 字节%s（%s）'
                     % (it['name'], it['devicePath'],
                        it['localBytes'], ' / md5 %s' % it['localMd5'][:8] if it['localMd5'] else '',
                        it['deviceBytes'], ' / md5 %s' % it['deviceMd5'][:8] if it['deviceMd5'] else '',
                        it['reason'] or '不一致'))
    lines.append('常见两种原因：① 改了 ui/*.json 但没 pack（本工具第②步会按时间戳自动 pack，'
                 '时间戳没变就不会 pack → 可先 `flythings_fui_pack`）；'
                 '② launch 推送没生效/掉了（重跑本工具，或确认 device= 选对了机器）。')
    return '\n'.join(lines)


# ------------------------------------------------------------------ CLI（排查用）
def _main(argv):
    mode = (argv[1] if len(argv) > 1 else '').lower()
    info = resolve_adb_info()
    print('adb        : %s' % (info['path'] or '<未找到>'))
    print('来源       : %s%s' % (info['source'],
                               '（env %s）' % info['envVar'] if info['envVar'] else ''))
    print('随包目录   : %s%s' % (bundled_adb_dir(),
                               '' if bundled_adb() else '（里面没有 adb 可执行文件）'))
    if not info['path']:
        print('提示       : %s' % adb_missing_hint())
        return 1
    ver, err = adb_version()
    print('版本       : %s%s' % (ver or '?', '  err=%s' % err if err else ''))
    pr = probe_devices()
    print('设备       : %d 台在线%s' % (pr['count'], '' if pr['ok'] else '（探测失败：%s）' % pr['error']))
    for d in pr['online']:
        print('   · %s' % device_string(d))
    for d in pr['offline']:
        print('   · %s（state=%s）' % (d['serial'], d['state']))
    if mode == 'devices':
        return 0
    models, meta = load_models()
    print('型号表     : %d 条（%s）' % (len(models), os.path.basename(MODELS_JSON)))
    return 0


if __name__ == '__main__':
    sys.exit(_main(sys.argv))
