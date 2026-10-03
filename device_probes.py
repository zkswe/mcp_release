"""设备侧只读探针（launch 活性 / 运行时指纹 / 面板信息 / fb 可读性）。

为什么单独一个模块：`project_tools.flythings_build_ui_flow`（工程侧）与
`ui_tools/device_screenshot.py`（抓屏侧）都要用同一批判据——所以**探针只此一份**，
不各写一遍（见 skill `flythings-domain-registry` 的「唯一真源」纪律）。

探针的接口事实（2026-10-02，Zkswe_SSD20X_SPINOR / flythingsV2.1 / Z20）：

1. **GUI 进程名就是 `zkgui`**（comm `zkgui_ui`）。设备 shell 是裁剪版——**没有 grep / head / sleep**，
   所以一律把原文取回来**在 Python 侧过滤**，不在设备上跑管道（管道会 `sh: grep: not found`）。
2. **`getprop ro.easyui.version` 是固化在固件里的版本**，而 `fun launch` 推的是
   `/tmp/lib/libzkgui.so`——两者**可以不同**，所以对账必须**分开报**，不能合成一个"版本"。
3. **所有探针一律带硬超时**：设备读在异常情况下可能长时间不返回 → 超时即判「不可读」并
   立即放弃、不再重试（fb 相关动作的时间预算见 `FB_OPEN_TIMEOUT`）。
   `/dev/sstarfb`、`/dev/mi_disp` 是以 ioctl 为主的节点，`dd` 读会 `Invalid argument`，不是 fb0 的替代。
"""

import os
import re
import time

# 探针默认硬超时（秒）。设备 shell 单次往返在 WiFi 上约 0.2~0.4s，12s 足够；
# fb 相关的预检刻意压到 8s：先定生死，不让一次抓屏把时间耗在等待上。
PROBE_TIMEOUT = 12
FB_OPEN_TIMEOUT = 8

# GUI（渲染进程）候选名。`zkgui` 是 FlyThings 运行时，`zkswe` 是 init 托管的服务名。
GUI_PROC_NAMES = ('zkgui', 'zkswe')

# launch 活性的 logcat 标记（**按实际日志原文**，2026-10-02 真机采样，Z20/SSD20X）：
#
#   强（= UI 真起来了）：
#     `onUI_show` / `onUI_init`                          —— 应用/框架钩子（**该框架默认不打印**，
#                                                           应用自己 LOGD 才会有；有则最直接）
#     `D/zkgui: registerActivity name: mainActivity OK!`  —— ftu/Activity 注册成功（实测会打）
#   弱（= 框架起来了，但不等于界面出来了）：
#     `E/zkgui: initEasyUICfg ok!`、`D/zkgui: register control: zk_`
#
# 为什么要分档：黑屏事件的形态是「推送成功 + 框架起来了 + 界面没出来」，
# 只验弱证据会漏，只认 onUI_show 又会全假红（框架根本不打）。
STRONG_LAUNCH_MARKERS = ('onUI_show', 'onUI_init', 'registerActivity name:')
WEAK_LAUNCH_MARKERS = ('initEasyUICfg ok', 'register control: zk_')
DEFAULT_LAUNCH_MARKERS = STRONG_LAUNCH_MARKERS + WEAK_LAUNCH_MARKERS


_ANSI = re.compile(r'\x1b\[[0-9;]*m')


def _strip_ansi(text):
    """去设备终端颜色转义（该设备 `ls` 会给文件名套 ANSI，会污染节点名解析）。"""
    return _ANSI.sub('', text or '')


def _adb():
    """仓库根 adb_tools（本模块在仓库根，直接 import；失败回 None 不抛）。"""
    try:
        import adb_tools
        return adb_tools
    except Exception:
        return None


def sh(serial, cmd, timeout=PROBE_TIMEOUT):
    """`adb shell <cmd>` → 文本（adb 不可用回 ''）。"""
    a = _adb()
    if not a:
        return ''
    return a.sh('', serial, cmd, timeout=timeout)


def busybox(serial, platform=''):
    """确保设备上有 busybox（`/tmp/busybox`），返回路径或 ''（失败不抛）。"""
    a = _adb()
    if not a:
        return ''
    try:
        return a.ensure_busybox('', serial, platform) or ''
    except Exception:
        return ''


# ────────────────────────────── 进程 / 活性 ──────────────────────────────

def ps_table(serial):
    """设备进程表 → (rows, err)。rows = [{'pid','name','state'}]。

    设备上**没有 grep**，所以取回整表在本地过滤。state 取自 `/proc/<pid>/stat` 第 3 字段
    （进程状态字符；`D` = 不可中断睡眠，该状态下 signal 不会立刻生效）。
    """
    bb = busybox(serial)
    out = sh(serial, '%s ps' % bb) if bb else sh(serial, 'ps')
    if not out.strip():
        return [], '拿不到进程表（ps 不可用？）'
    rows = []
    for ln in out.splitlines()[1:]:
        parts = ln.split()
        if len(parts) < 2 or not parts[0].isdigit():
            continue
        pid = parts[0]
        cmdtail = ln.split(None, 2)[-1] if len(parts) >= 3 else ''
        name = ''
        if '{' in cmdtail and '}' in cmdtail:          # `{zkgui_ui} /bin/zkgui`
            name = cmdtail[cmdtail.find('{') + 1:cmdtail.find('}')]
        elif cmdtail:
            name = os.path.basename(cmdtail.split()[0])
        rows.append({'pid': pid, 'name': name, 'cmd': cmdtail, 'state': ''})
    # ps 多数裁剪版不带 STAT 列 → 逐个读 /proc/<pid>/stat 补状态（只补候选，省往返）
    for r in rows:
        if not any(n in (r['name'] or '') or n in (r['cmd'] or '')
                   for n in GUI_PROC_NAMES):
            continue
        st = sh(serial, 'cat /proc/%s/stat 2>/dev/null' % r['pid'], timeout=6)
        _tail = st.split(') ', 1)
        r['state'] = _tail[1].split()[0] if len(_tail) > 1 and _tail[1].split() else ''
    return rows, ''


def gui_liveness(serial, extra_names=()):
    """渲染进程是否在跑 + 状态 → {'verdict','procs','detail'}。

    verdict：
      `alive`   —— 有 GUI 进程且不在 D 状态（画面可信）
      `blocked` —— GUI 进程存在但处于 D 状态（**很可能不渲染**）
      `absent`  —— 没有 GUI 进程（fb/屏上内容是**上一轮的残留旧帧**）
      `unknown` —— 进程表都拿不到（不要据此断言画面真假）
    """
    names = tuple(GUI_PROC_NAMES) + tuple(extra_names or ())
    rows, err = ps_table(serial)
    hit = [r for r in rows
           if any(n and n.lower() in (r['name'] or '').lower() for n in names)]
    if err or not rows:
        return {'verdict': 'unknown', 'procs': [], 'detail': err or '无进程表'}
    if not hit:
        return {'verdict': 'absent', 'procs': [],
                'detail': '未见 GUI 进程（%s）→ 屏上内容很可能是上一轮残留的旧帧'
                          % '/'.join(names)}
    d = [r for r in hit if r.get('state') == 'D']
    if d:
        return {'verdict': 'blocked', 'procs': hit,
                'detail': 'GUI 进程处于 D 状态（pid %s）→ 大概率不渲染'
                          % ','.join(r['pid'] for r in d)}
    return {'verdict': 'alive', 'procs': hit, 'detail': 'GUI 进程在跑（%s）' % ', '.join(
        '%s:%s' % (r['name'] or '?', r['pid']) for r in hit)}


# ────────────────────────── 运行时指纹（easyui）──────────────────────────

def easyui_runtime(serial, platform=''):
    """设备运行时 easyui 指纹 → {'firmwareVersion','osVersion','runningLib',...}。

    **固件版本与运行库分开报**（见模块 docstring 第 2 条）：
      firmwareVersion ← `getprop ro.easyui.version`（固化在固件里）
      runningLib      ← `/tmp/lib/libzkgui.so`（fun launch 推的**实际在跑**的那份）
      factoryLib      ← `/lib/libeasyui.so`（出厂）
    对账要拿 runningLib（有）优先，其次 factoryLib。
    """
    a = _adb()
    out = {'firmwareVersion': '', 'osVersion': '', 'model': '',
           'runningLib': None, 'factoryLib': None, 'sources': {}}
    txt = sh(serial, 'getprop ro.easyui.version; getprop ro.build.version.release; '
                     'getprop ro.product.model')
    vals = [x.strip() for x in (txt or '').splitlines() if x.strip()]
    if vals:
        out['firmwareVersion'] = vals[0]
        out['sources']['firmwareVersion'] = 'getprop ro.easyui.version'
    if len(vals) > 1:
        out['osVersion'] = vals[1]
    if len(vals) > 2:
        out['model'] = vals[2]
    if a is None:
        out['error'] = 'adb 子系统不可用'
        return out
    for key, path in (('runningLib', '/tmp/lib/libzkgui.so'),
                      ('factoryLib', '/lib/libeasyui.so')):
        try:
            info = a.remote_file_info('', serial, path, platform=platform)
        except Exception as e:
            info = {'error': '%s: %s' % (type(e).__name__, e)}
        if info.get('size') or info.get('md5'):
            info['path'] = path
            out[key] = info
    return out


# ──────────────────────────── 面板 / 显示 ────────────────────────────

def hw_panel_target(serial, fb_width=None):
    """应用硬件层报的面板目标 → {'raw','resolution','source'}。

    实测原文：`D/zkhardware: para target: RGB_LCD480480`（= 480×480）。
    形如 `RGB_LCD<W><H>` **没有分隔符**，单看切不开（`480|480` 还是 `4|80480`）——
    所以用 **fb 的可见宽度**把 W 切出来，剩下的就是 H（拿不到宽度就只回 raw，不猜）。
    """
    out = {'raw': '', 'resolution': '', 'source': ''}
    txt = sh(serial, 'logcat -d', timeout=20)
    for ln in (txt or '').splitlines():
        i = ln.find('para target:')
        if i < 0:
            continue
        tok = ln[i + len('para target:'):].strip().split()[0] if ln[i:].split() else ''
        if not tok:
            continue
        out['raw'] = tok
        out['source'] = 'logcat zkhardware para target'
        digits = ''.join(ch for ch in tok if ch.isdigit())
        w = int(fb_width) if fb_width else 0
        if digits and w:
            ws = str(w)
            if digits.startswith(ws) and len(digits) > len(ws):
                out['resolution'] = '%sx%s' % (ws, digits[len(ws):])
            elif digits == ws * 2:                    # 方形屏且被合在一起（480480）
                out['resolution'] = '%sx%s' % (ws, ws)
        break
    return out

def panel_info(serial, fb='/dev/fb0'):
    """面板与显示通路信息 → {'nodes','fbName','virtualSize','stride','bpp','dispIrq',...}。

    `virtualSize` 的**第二维常常是「缓冲区高度」= 页数 × 屏高**（实测 480,1440 = 3 页 × 480），
    所以**不能**把它当面板分辨率；可见高度要 `stride/bpp*8` 之外再按 pan 判（抓屏侧已做）。
    这里只如实回原始值 + 由 stride 推出的**行宽像素**。
    """
    out = {'nodes': [], 'fbName': '', 'virtualSize': '', 'virtualHeight': None,
           'stride': None, 'bpp': None, 'visibleWidth': None, 'dispIrq': None,
           'modes': '', 'pan': '', 'errors': []}
    bb = busybox(serial)
    names = sh(serial, '%s ls /dev' % bb) if bb else sh(serial, 'ls /dev')
    if names:
        clean = _strip_ansi(names)
        out['nodes'] = sorted({n for n in clean.split() if 'fb' in n or 'disp' in n})
    fbname = os.path.basename(fb)
    for key, path, cast in (('fbName', '/sys/class/graphics/%s/name' % fbname, str),
                            ('virtualSize', '/sys/class/graphics/%s/virtual_size' % fbname, str),
                            ('stride', '/sys/class/graphics/%s/stride' % fbname, int),
                            ('bpp', '/sys/class/graphics/%s/bits_per_pixel' % fbname, int),
                            ('modes', '/sys/class/graphics/%s/modes' % fbname, str),
                            ('pan', '/sys/class/graphics/%s/pan' % fbname, str)):
        v = sh(serial, 'cat %s 2>/dev/null' % path, timeout=8).strip()
        if not v:
            out['errors'].append('%s 读不到' % path)
            continue
        try:
            out[key] = cast(v)
        except Exception:
            out[key] = v
    # virtualSize 的两段都是数字才算数：`480,1440`（第二段常是**缓冲区高度** = 页数×屏高，
    # 不是面板高，所以只回原值 + 推出来的行宽像素，不拿它当分辨率）。
    _vs = out.get('virtualSize')
    if isinstance(_vs, str) and ',' in _vs:
        _h = _vs.split(',')[1].strip()
        if _h.lstrip('-').isdigit():
            out['virtualHeight'] = int(_h)
    if out.get('stride') and out.get('bpp'):
        _bpp8 = int(out['bpp']) // 8
        if _bpp8:
            out['visibleWidth'] = int(out['stride']) // _bpp8
    # SigmaStar MI 显示：`DevStatus IrqNum IrqCnt BgColor` 表头，**下一行**才是数值。
    # （两个读数在涨 = 显示通路在刷；它不等于「应用在画」，但能排除「显示关了」。）
    # 没有该 proc 的平台留 None —— 不代表异常。
    irq = _strip_ansi(sh(serial, 'cat /proc/mi_modules/mi_disp/mi_disp0 2>/dev/null',
                         timeout=10))
    lines = (irq or '').splitlines()
    for i, ln in enumerate(lines):
        if 'IrqCnt' in ln:
            for j in (i + 1, i + 2):               # 表头可能占一行，数值在下一行
                if j >= len(lines):
                    break
                row = lines[j].split()
                if len(row) >= 3 and row[0].lstrip('-').isdigit() \
                        and row[2].lstrip('-').isdigit():
                    out['dispIrq'] = int(row[2])
                    break
            if out['dispIrq'] is not None:
                break
    return out


_MODES_RE = re.compile(r'(\d+)\s*x\s*(\d+)')


def parse_modes(text):
    """`/sys/class/graphics/fb0/modes` 的原文 → (w, h)。

    实测原文形如 `U:600x1600p-50`（前缀/后缀都是 fb 的模式描述，不是分辨率的一部分）。
    解析不出回 (0, 0) —— 不猜。
    """
    m = _MODES_RE.search(text or '')
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def panel_resolution(serial, fb='/dev/fb0'):
    """**设备面板可见分辨率**的唯一判据 → {'ok','width','height','source','raw','conflicts'}。

    为什么要有它：分辨率体检（`preflight.py`）要拿一个数跟工程的设计分辨率比，
    而这个数有**三条不同来源**、彼此会不一致，混用会得出相反的结论：

      | 来源 | 取自 | 什么时候可信 |
      |---|---|---|
      | `fbmode` | `/sys/class/graphics/fb0/modes`（如 `U:600x1600p-50`） | fb 自己的显示模式，**首选** |
      | `hwtarget` | logcat `zkhardware: para target: RGB_LCD4801600` | 面板目标；高度靠它才能切出来（原文无分隔符） |
      | `stride` | `stride / (bpp/8)` | 只有**宽度**可信；高度可能含缓冲区（`virtual_size` 是页数×屏高） |

    高度这一维只靠 `fbmode` 常有（`U:600x1600p-50` 带高度），拿不到才退 hwtarget；
    **两者都有且不一致时如实进 `conflicts`**（不替调用方选，也不静默取其一）。
    `virtual_size` 只回原值，绝不当事分辨率（双缓冲时它是 页数 × 屏高）。
    """
    out = {'ok': False, 'width': 0, 'height': 0, 'source': '', 'raw': {},
           'pages': None, 'conflicts': [], 'errors': []}
    if _adb() is None:
        out['errors'].append('adb 子系统不可用')
        return out
    try:
        info = panel_info(serial, fb)
    except Exception as e:
        out['errors'].append('panel_info 异常: %s: %s' % (type(e).__name__, e))
        return out
    out['raw'] = {k: info.get(k) for k in ('modes', 'virtualSize', 'stride', 'bpp', 'pan',
                                           'visibleWidth', 'virtualHeight', 'fbName')}
    for e in info.get('errors') or []:
        out['errors'].append(e)
    mw, mh = parse_modes(info.get('modes'))
    hw = {'raw': '', 'resolution': ''}
    try:
        hw = hw_panel_target(serial, info.get('visibleWidth'))
    except Exception as e:
        out['errors'].append('hw_panel_target 异常: %s: %s' % (type(e).__name__, e))
    out['raw']['hwTarget'] = hw.get('raw') or ''
    hw_res = hw.get('resolution') or ''
    hww, hwh = (0, 0)
    if 'x' in hw_res:
        try:
            hww, hwh = (int(x) for x in hw_res.split('x')[:2])
        except Exception:
            hww, hwh = 0, 0

    if mw and mh:
        out.update(width=mw, height=mh, source='fb modes')
    elif hww and hwh:
        out.update(width=hww, height=hwh, source='logcat hw target')
    elif info.get('visibleWidth') and info.get('virtualHeight'):
        # 只有宽度可信 + virtual_height 可能是页数倍 → **不据此定高**，只报宽度
        out.update(width=int(info['visibleWidth']), height=0,
                   source='fb stride(仅宽度)')
    if mw and mh and hww and hwh and (mw, mh) != (hww, hwh):
        rot = (mw, mh) == (hwh, hww)
        out['conflicts'].append(
            'fb modes 报 %dx%d，而硬件层报 %dx%d%s —— 两者不一致，'
            '按 fb modes 取（要精确到面板请人核一次）'
            % (mw, mh, hww, hwh, '（互为转置，通常是转屏）' if rot else ''))
    # 交叉自检：`virtual_size` 的高应当是可见高的**整数倍**（双/三缓冲。实测 480,1600 + modes
    # 480x800 → 2 页）。不是整数倍说明"可见高"这一维可能读错（模态名里带缩放/裁切），如实报。
    vh = info.get('virtualHeight')
    if out['height'] and vh and vh % out['height'] == 0:
        out['pages'] = vh // out['height']
    elif out['height'] and vh:
        out['conflicts'].append(
            'virtual_size 高 %s 不是可见高 %s 的整数倍 → 可见高这一维存疑，请人工核一次'
            % (vh, out['height']))
    out['ok'] = bool(out['width'])
    return out



def fb_probe(serial, node='/dev/fb0', timeout=FB_OPEN_TIMEOUT):
    """**有界**探测 fb 节点能不能读 → {'node','ok','blocked','bytes','error','tried'}。

    **硬超时**定生死：超时就判 `blocked` 并让调用方**立刻放弃**（别再试别的节点、别再重试）。
    读得到的节点回 `ok=True` 与实读字节数；节点不支持 read 会把设备端报错原样带回。
    """
    a = _adb()
    out = {'node': node, 'ok': False, 'blocked': False, 'bytes': 0,
           'error': '', 'tried': [node], 'timeout': timeout}
    if a is None:
        out['error'] = 'adb 子系统不可用'
        return out
    bb = busybox(serial) or 'busybox'
    # 读 1 块 16 字节：拿到数据 = 通道可用；报 Invalid argument = 节点不支持 read；超时 = 无响应。
    # ⚠️ 字节数用 stdout（`2>/dev/null`），报错单独取——混在一起会把"错误信息的长度"
    #    当成"读到了字节"（dd 的报错文本会长达几十字节）。
    rc, o, e = a.shell_rc('', serial,
                          '%s dd if=%s bs=16 count=1 2>/dev/null | %s wc -c' % (bb, node, bb),
                          timeout=timeout)
    if rc == 124:                                  # subprocess 超时（_run 的约定）
        out['blocked'] = True
        out['error'] = ('读 %s 在 %s 秒内无响应（超时）→ 该节点本次不可读'
                        % (node, timeout))
        return out
    for ln in (o or '').splitlines():
        if ln.strip().isdigit():
            out['bytes'] = int(ln.strip())
    if not out['ok'] and out['bytes'] == 0:
        rc2, _o2, e2 = a.shell_rc('', serial,
                                  '%s dd if=%s bs=16 count=1 2>&1 >/dev/null' % (bb, node),
                                  timeout=timeout)
        msg = (e2 or '').strip().splitlines()
        out['error'] = (msg[0] if msg else '读到 0 字节（%s）' % node)[:160]
    out['ok'] = out['bytes'] > 0
    return out


def fb_strays(serial):
    """列出仍在等 fb 的 `dd` 进程 → [{'pid','state','wchan'}]。

    用途：抓屏前先看一眼——**还有没收敛的读取在等 fb 时，新的一次往往也读不到**，
    这时直接给结论，比反复重试更省事。只读（不杀进程、不改设备状态）。
    """
    rows, err = ps_table(serial)
    out = []
    for r in rows:
        if 'dd' not in (r.get('cmd') or ''):
            continue
        if '/dev/fb' not in (r.get('cmd') or '') and 'fb0' not in (r.get('cmd') or ''):
            continue
        st = sh(serial, 'cat /proc/%s/stat 2>/dev/null' % r['pid'], timeout=6)
        # `/proc/<pid>/stat` 的 comm 带括号（可能含空格）→ 以 `) ` 之后为字段起点；
        # 取不到就留 '?'，不猜也不吞（调用方据此知道状态未知）。
        _tail = st.split(') ', 1)
        state = _tail[1].split()[0] if len(_tail) > 1 and _tail[1].split() else '?'
        wchan = sh(serial, 'cat /proc/%s/wchan 2>/dev/null' % r['pid'], timeout=6).strip()
        out.append({'pid': r['pid'], 'state': state, 'wchan': wchan})
    if err:
        return []
    return out


# ──────────────────────────── launch 活性 ────────────────────────────

def clear_logcat(serial):
    """清 logcat（launch 前调，好让"起来了吗"只看到本轮日志）。"""
    a = _adb()
    if a is None:
        return False
    rc, _o, _e = a.raw('', serial, ['logcat', '-c'], timeout=15)
    return rc == 0


def launch_evidence(serial, wait=6, poll=2, max_lines=800):
    """launch 后读 logcat，找「UI 真的起来了」的证据 → {'tier','ok','marker','line',...}。

    **为什么要有这道检查**：`fun launch` 返回 0 只说明**推送成功**，不说明应用起来渲染了
    （黑屏事件的教训：推送成功 → 面板黑着，却回了 launched=true）。

    ⚠️ **必须等一会儿再读**：实测 `fun launch` 刚返回时 logcat 只有 24 行（控件注册 + 配置装载），
    activity 注册要再过数秒才出现 —— 立刻判定会假红。所以这里**轮询等待** `wait` 秒。

    分档（见 STRONG/WEAK_LAUNCH_MARKERS）：
      tier=`strong` —— 看到 `registerActivity name:` / `onUI_show` / `onUI_init`
      tier=`weak`   —— 只看到 `initEasyUICfg ok` / `register control: zk_`（框架起来了）
      tier=`none`   —— 什么都没看到
    """
    out = {'tier': 'none', 'ok': False, 'marker': '', 'line': '',
           'scanned': 0, 'waited': 0,
           'strong': list(STRONG_LAUNCH_MARKERS), 'weak': list(WEAK_LAUNCH_MARKERS)}
    deadline = max(0, int(wait))
    elapsed = 0
    while True:
        txt = sh(serial, 'logcat -d', timeout=20)
        if not txt.strip():
            out['error'] = 'logcat 取不到内容（设备 logd 不可用？）'
            return out
        lines = txt.splitlines()[-max_lines:]
        out['scanned'] = len(lines)
        for tier, group in (('strong', STRONG_LAUNCH_MARKERS),
                            ('weak', WEAK_LAUNCH_MARKERS)):
            for mk in group:
                for ln in lines:
                    if mk in ln:
                        out.update(tier=tier, ok=True, marker=mk,
                                   line=ln.strip()[:200], waited=elapsed)
                        return out
        if elapsed >= deadline:
            break
        time.sleep(poll if poll > 0 else 1)
        elapsed += (poll if poll > 0 else 1)
    return out
