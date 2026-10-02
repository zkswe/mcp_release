#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
device_screenshot.py — 从设备真机抓屏，转成 PNG / JPG / BMP 交给 AI 分析

【为什么不能用 screencap】（2026-09-10 真机实测）
- FlyThings 设备 rootfs 是裁剪版：**没有 screencap / dd / head / uname**，只有 cat/ls/echo；
- `adb exec-out cat /dev/fb0` 也**不可用**（patched adbd 无 shell v2 → "error: closed"）。
- 所以唯一可靠链路：设备侧 `cat /dev/fb0 > /tmp/fb.raw` → `adb pull` → 本地解析。

【fb 参数必须问 sysfs，不能猜】
    /sys/class/graphics/fb0/modes          → "U:600x1600p-50"   可见分辨率（真正要用的）
    /sys/class/graphics/fb0/virtual_size   → "600,3200"         可能是 2 倍（FBDEV_OVERALLOC=200）
    /sys/class/graphics/fb0/bits_per_pixel → 32
    /sys/class/graphics/fb0/stride         → 2400               每行字节数

【两个坑】
1) 可见高 ≠ 文件行数：raw 是 600x3200x4=7.68MB，可见只有 600x1600 —— 必须按 stride 逐行取，
   直接按文件大小当分辨率会把下半截脏数据画进图里（本模块按模式建 (stride/4, height) 图再 crop）。
2) 通道序：32bpp 内存布局是小端 ARGB8888 = 字节序 B G R A；搞反 → 红蓝互换。
   本模块按 alpha 字节位置自动判别（末字节≈0xFF → BGRA；首字节≈0xFF → RGBA），也可 pixel= 强制。

用法（CLI）：
    python device_screenshot.py                            # 抓当前屏 → screenshots/device_600x1600_*.png
    python device_screenshot.py --scale 0.5 --fmt jpg      # 缩小一半存 JPG（省 token）
    python device_screenshot.py --out D:/shot.png --pixel rgba
    python device_screenshot.py --info                     # 只打印屏幕参数，不抓图
    python device_screenshot.py --device <设备IP>:5555 --name main_page

视频层（SigmaStar Z20/Z21，layer='video'，走 zkshot 从 vdec 输出口取帧）：
    python device_screenshot.py --layer video                    # vdec chn 0（默认）
    python device_screenshot.py --layer video --vdec-chn 1       # 拼墙/多路播放器（Z20 拼墙在 chn 1）
     ⚠️ **通道选错 = 抓不到帧**（这是该工具最常见的失败原因，2026-09-27 实测）：
     工具默认 chn 0（单路/历史口径）；**SmartPanel 拼墙播放器在 chn 1**（多屏拼接）。
     ⚠️ Z20 屏保 zkmedia/ssdvideoplayer 是 **FFmpeg 软解、不建 MI VDEC 通道** → chn 0 抽不到帧
        不一定是工具问题（详见 knowledge/devflow/device-screenshot.md §4.1.1）。
  失败返回体带 `vdecChn`（实际用的通道号）+ `zkshotCmd` + `hint`（怎么换），不会静默返回空。
  手工等价命令：`zkshot <out.raw> vdec <chn> 0`。
"""

import argparse
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import time

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

# ---------------------------------------------------------------- adb 定位

_ADB_CANDIDATES = [
    r'tools\adb\adb.exe',                  # 随包 adb（v0.27.84 起）
    r'tools\FlyThingsIDE\sdk\platform-tools\adb\adb.exe',
    r'sim\tools\adb.exe',
    r'sim\tools\platform-tools\adb.exe',
    r'qemu-openwrt\tools\platform-tools\adb.exe',
]


# ---------------------------------------------------------------- adb 定位（v0.27.84 收口）
# ⚠️ 本模块不再自己写死 adb 路径：统一走仓库根 `adb_tools.resolve_adb()`，
#    优先级 = 环境变量 ADB/FLYTHINGS_ADB → **随包 tools/adb/adb.exe** → PATH。
#    （旧候选表里 sim/、qemu-openwrt/ 那几条本机路径已删；隐私闸门不看这类相对路径，
#     但它们跟「随包分发」的口径不一致，留着只会漂移）。

_ADB_TOOLS = None


_MISSING = object()
_DEVICE_PROBES = _MISSING


def _repo_probes():
    """向上逐级找仓库根的 device_probes.py（抓屏也用同一批判据，不另写一套）。"""
    global _DEVICE_PROBES
    if _DEVICE_PROBES is not _MISSING:
        return _DEVICE_PROBES or None
    cur = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        if os.path.isfile(os.path.join(cur, 'device_probes.py')):
            if cur not in sys.path:
                sys.path.insert(0, cur)
            try:
                import importlib
                _DEVICE_PROBES = importlib.import_module('device_probes')
            except Exception:
                _DEVICE_PROBES = False
            return _DEVICE_PROBES or None
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    _DEVICE_PROBES = False
    return None


def fb_precheck(dev, fb, adb, timeout=None):
    """**有界**预检 fb 是否可读 → {'ok','blocked','error','strays','hint'}。

    为什么必须先探：fb 读取在异常情况下可能长时间不返回，直接 `dd|gzip` 会把时间全耗在等待上
    （默认上限 180s），而且设备侧会留下没收敛的读取进程。所以先花 ≤8s 探一次，不通就立刻给结论。
    """
    out = {'ok': True, 'blocked': False, 'error': '', 'strays': [], 'hint': ''}
    dp = _repo_probes()
    if dp is None:
        return out                                  # 探针缺失 → 不拦（保持旧行为）
    try:
        strays = dp.fb_strays(dev)
    except Exception:
        strays = []
    out['strays'] = strays
    pr = dp.fb_probe(dev, fb, timeout=timeout or 8)
    out['ok'] = bool(pr.get('ok'))
    out['blocked'] = bool(pr.get('blocked'))
    out['error'] = pr.get('error') or ''
    if not out['ok']:
        out['hint'] = (
            '设备端 %s **读不了**：%s。'
            '处置建议：① 看有没有没收敛的读取进程（本次探到 %d 个仍在等 fb 的 dd）——'
            '有的话先别反复重试；② 视频层抓帧可试 layer="video"（SigmaStar 专用，走 zkshot，不碰 fb）；'
            '③ 需要继续排查时按现场设备情况定，别照搬历史结论。'
            % (fb, out['error'] or '未知', len(strays)))
    return out


def stale_frame_info(dev, adb, screen, fb='/dev/fb0'):
    """判断「这一屏可信吗」（任务 6）→ {'verdict','gui','dispIrqDelta','detail'}。

    为什么要有：**应用不渲染时 fb 上留着上一帧**，看起来像正常运行 —— 这是黑屏事件里
    误诊的元凶之一。判据（都走只读探针，不碰 fb 数据）：
      ① GUI 进程不在 → 屏上就是**残留旧帧**（`stale-no-gui`，硬结论）
      ② GUI 进程卡在 D 状态 → 大概率不渲染（`gui-blocked`）
      ③ 显示中断计数在涨（SigmaStar MI）→ 显示通路在刷（`live`）——它**不等于**应用在画，
         所以仍提示「要确认画面内容请在界面上做一次已知动作再抓」。
    """
    out = {'verdict': 'unknown', 'gui': '', 'dispIrqDelta': None, 'detail': ''}
    dp = _repo_probes()
    if dp is None:
        return out
    try:
        lv = dp.gui_liveness(dev)
    except Exception as e:
        out['detail'] = '%s: %s' % (type(e).__name__, e)
        return out
    out['gui'] = lv.get('verdict') or 'unknown'
    irq1 = (screen or {}).get('dispIrq')
    if irq1 is None:
        try:
            irq1 = dp.panel_info(dev, fb).get('dispIrq')
        except Exception:
            irq1 = None
    if out['gui'] == 'absent':
        out['verdict'] = 'stale-no-gui'
        out['detail'] = lv.get('detail') or 'GUI 进程不在'
    elif out['gui'] == 'blocked':
        out['verdict'] = 'gui-blocked'
        out['detail'] = lv.get('detail') or 'GUI 进程处于 D 状态（很可能不渲染）'
    elif irq1 is not None:
        try:
            time.sleep(0.4)
            irq2 = dp.panel_info(dev, fb).get('dispIrq')
        except Exception:
            irq2 = None
        if irq2 is not None:
            out['dispIrqDelta'] = irq2 - irq1
            out['verdict'] = 'live' if irq2 != irq1 else 'display-idle'
            out['detail'] = ('显示中断计数 %s→%s（%+d）' % (irq1, irq2, irq2 - irq1))
    else:
        out['verdict'] = 'live'
        out['detail'] = '无显示中断计数可读，仅凭 GUI 进程判定'
    return out


def _repo_adb_tools():
    """向上逐级找仓库根的 adb_tools.py（本文件在 <repo>/ui_tools/ 下）。"""
    global _ADB_TOOLS
    if _ADB_TOOLS is not None:
        return _ADB_TOOLS or None
    cur = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        p = os.path.join(cur, 'adb_tools.py')
        if os.path.isfile(p):
            if cur not in sys.path:
                sys.path.insert(0, cur)
            try:
                import importlib
                _ADB_TOOLS = importlib.import_module('adb_tools')
            except Exception:
                _ADB_TOOLS = False
            return _ADB_TOOLS or None
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    _ADB_TOOLS = False
    return None


def find_adb():
    """找 adb：adb_tools.resolve_adb()（环境变量 ADB/FLYTHINGS_ADB > 随包 tools/adb/ > PATH）。

    保留旧返回约定（路径或 None），所以调用方与用例（monkeypatch find_adb）无需改。
    找不到仓库 adb_tools 时（单独拷走本文件用）退化到旧候选表，保证独立可用。
    """
    at = _repo_adb_tools()
    if at is not None:
        p = at.resolve_adb()
        return p or None
    env = os.environ.get('ADB') or os.environ.get('FLYTHINGS_ADB') or os.environ.get('ADB_PATH')
    if env and os.path.isfile(env):
        return env
    w = shutil.which('adb')
    if w:
        return w
    base = os.getcwd()
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        here = base
    for root in (base, here):
        cur = root
        for _ in range(6):
            for rel in _ADB_CANDIDATES:
                p = os.path.join(cur, rel)
                if os.path.isfile(p):
                    return p
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    return None


def adb_missing_msg():
    """找不到 adb 的统一文案（优先用仓库 adb_tools 的口径，保证全仓一句话）。"""
    at = _repo_adb_tools()
    if at is not None:
        return at.adb_missing_hint()
    return ('找不到 adb：设环境变量 ADB=<adb 完整路径>，或把 adb 放进 PATH，'
            '或把随包 tools/adb/adb.exe 拷到能找到的位置。')


def _run(args, timeout=60, binary=False):
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout)
        if binary:
            return r.returncode, r.stdout, r.stderr.decode('utf-8', 'replace')
        return (r.returncode,
                r.stdout.decode('utf-8', 'replace') if r.stdout else '',
                r.stderr.decode('utf-8', 'replace') if r.stderr else '')
    except FileNotFoundError:
        return 127, b'' if binary else '', 'adb 不在 PATH'
    except subprocess.TimeoutExpired:
        return 124, b'' if binary else '', f'命令超时（{timeout}s）'
    except Exception as e:
        return 1, b'' if binary else '', str(e)


def list_devices(adb):
    rc, out, err = _run([adb, 'devices'], timeout=20)
    if rc != 0:
        return [], err
    devs = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line or '\t' not in line:
            continue
        name, st = line.split('\t', 1)
        if st.strip() == 'device':
            devs.append(name.strip())
    return devs, ''


def pick_device(adb, device=''):
    devs, err = list_devices(adb)
    if not devs:
        return '', ('adb 看不到设备（adb devices 为空）。检查：① USB/网络已连 '
                    '`adb connect <设备IP>:5555` ② 开发者选项调试已开。' + ((' adb 报错: ' + err) if err else ''))
    if device:
        if device in devs:
            return device, ''
        return '', f'指定设备 {device} 不在 adb 列表：{devs}'
    if len(devs) == 1:
        return devs[0], ''
    return '', f'检测到多台设备 {devs}，请显式传 device=<IP/序列号>'


# ---------------------------------------------------------------- sysfs 读屏参

def _sh(adb, device, cmd, timeout=30):
    a = [adb] + (['-s', device] if device else []) + ['shell', cmd]
    rc, out, err = _run(a, timeout=timeout)
    return out.strip() if rc == 0 else ''


def _parse_modes(text):
    """'U:600x1600p-50' → (600, 1600)"""
    m = re.search(r'(\d+)\s*x\s*(\d+)', text or '')
    if m:
        return int(m.group(1)), int(m.group(2))
    return 0, 0


def _parse_dispsys(text):
    """从 /sys/class/disp/disp/attr/sys 解析各图层几何。

    每层：{'fb': (w, h), 'crop': (x, y, w, h), 'frame': (x, y, w, h)}
    权威信息源：**UI 图层的 fb 尺寸 = 本项目逻辑分辨率**，frame = 它在面板上的位置
    （不用猜设备几何，sysfs 里就有）。
    """
    def nums(s):
        return [int(v) for v in re.findall(r'-?\d+', s or '')]
    layers = []
    for m in re.finditer(r'fb\[\s*([\d,;\s]+?)\]\s*crop\[\s*([\d,;\s]+?)\]\s*frame\[\s*([\d,;\s]+?)\]',
                         text or ''):
        fbn, crn, frn = nums(m.group(1)), nums(m.group(2)), nums(m.group(3))
        if len(fbn) >= 2 and len(crn) >= 4 and len(frn) >= 4:
            layers.append({'fb': tuple(fbn[:2]), 'crop': tuple(crn[:4]),
                           'frame': tuple(frn[:4])})
    return layers


def _parse_easyui_cfg(text):
    """解析**项目工程**的 EasyUI.cfg（设备上 /res/etc/EasyUI.cfg）。

    工程内位置：<项目>/.fun/<平台>/launch/EasyUI.cfg —— 这是取图方向的
    权威来源，**不用猜、不要从 fb0/rotate 或图层几何反推**：
      rotateScreen : 屏幕/取图角度（0/90/180/270）
      rotateTouch  : 触摸角度（**可以与之不同**，注入触摸测试时要按它换算）
    """
    out = {}
    for k in ('rotateScreen', 'rotateTouch', 'resPath', 'startupLibPath',
              'languageCode', 'font'):
        m = re.search(r'"%s"\s*:\s*"([^"]*)"|\"%s\"\s*:\s*([-\w./]+)' % (k, k), text or '')
        if m:
            out[k] = (m.group(1) or m.group(2) or '').strip()
    for k in ('rotateScreen', 'rotateTouch'):
        try:
            out[k] = int(out[k])
        except Exception:
            pass
    return out


def screen_info(device='', fb='/dev/fb0', adb=''):
    """读 sysfs 得到可见分辨率 / bpp / stride / virtual。返回 dict（含 raw 每行字节、可见字节数）。"""
    adb = adb or find_adb()
    if not adb:
        return {'success': False, 'error': adb_missing_msg()}
    dev, err = pick_device(adb, device)
    if not dev:
        return {'success': False, 'error': err}
    g = '/sys/class/graphics/' + os.path.basename(fb)
    cmd = (f'cat {g}/modes 2>/dev/null; echo "|"; '
           f'cat {g}/virtual_size 2>/dev/null; echo "|"; '
           f'cat {g}/bits_per_pixel 2>/dev/null; echo "|"; '
           f'cat {g}/stride 2>/dev/null; echo "|"; '
           f'cat {g}/name 2>/dev/null; echo "|"; '
           f'cat {g}/pan 2>/dev/null; echo "|"; '
           f'cat {g}/rotate 2>/dev/null; echo "|"; '
           f'cat /sys/class/disp/disp/attr/sys 2>/dev/null; echo "|"; '
           f'cat /res/etc/EasyUI.cfg 2>/dev/null; echo "|"; '
           f'cat /etc/EasyUI.cfg 2>/dev/null')
    out = _sh(adb, dev, cmd)
    parts = (out.split('|') + [''] * 10)[:10]
    (modes, vsize, bpp_s, stride_s, name, pan, rot_s, disp_sys,
     cfg_res_etc, cfg_etc) = [p.strip() for p in parts]
    cfg_txt = cfg_res_etc or cfg_etc
    cfg = _parse_easyui_cfg(cfg_txt)
    cfg_src = '/res/etc/EasyUI.cfg' if cfg_res_etc else ('/etc/EasyUI.cfg' if cfg_etc else '')
    try:
        rotate = int(rot_s)
    except Exception:
        rotate = 0
    ox = oy = 0
    if ',' in pan:
        try:
            ox, oy = [int(v) for v in pan.split(',')[:2]]
        except Exception:
            pass
    vw, vh = (0, 0)
    if ',' in vsize:
        try:
            a, b = vsize.split(',')[:2]
            vw, vh = int(a), int(b)
        except Exception:
            pass
    try:
        bpp = int(bpp_s)
    except Exception:
        bpp = 32
    try:
        stride = int(stride_s)
    except Exception:
        stride = 0
    w, h = _parse_modes(modes)
    if not w or not h:                       # modes 缺 → 退回 virtual_size
        w, h = vw, vh
    if not stride:
        stride = w * bpp // 8
    size = _sh(adb, dev, f'cat {g}/virtual_size >/dev/null 2>&1; echo 0')
    layers = _parse_dispsys(disp_sys)
    cands = [L for L in layers if L['fb'] != (w, h)] if w and h else []
    ui_layer = cands[0] if len(cands) == 1 else None
    return {
        'success': True, 'device': dev, 'fb': fb, 'fbName': name,
        'width': w, 'height': h,               # 可见分辨率（要用的）
        'virtualWidth': vw, 'virtualHeight': vh,
        'bpp': bpp, 'stride': stride,
        'offsetX': ox, 'offsetY': oy, 'pan': pan,
        'rotate': rotate,                      # fb0/rotate（可能为 0，**不是**取图角度的首选）
        'rotateScreen': cfg.get('rotateScreen'),   # 项目工程 EasyUI.cfg：取图角度的权威来源
        'rotateTouch': cfg.get('rotateTouch'),     # 触摸角度（可与 rotateScreen 不同）
        'easyuiCfg': cfg, 'cfgSource': cfg_src,
        'layers': layers,                      # disp attr sys 各图层几何（参考，不是角度来源）
        'uiLayer': ui_layer,                   # 唯一“非全屏尺寸”图层 = 项目 UI 层
        'visibleBytes': stride * h,
        'modes': modes,
        'note': ('virtualHeight 是 height 的 %d 倍（FBDEV_OVERALLOC）——**双缓冲**：'
                 '当前显示的是 yoffset=%d 那一帧（sysfs 的 pan 值），'
                 '抓屏必须带 skip=%d，否则抓到的是上一帧（旧画面）'
                 % (round(vh / h) if h else 0, oy, oy)) if vh and h and vh > h else '',
    }


# ---------------------------------------------------------------- raw → image

# 通道序：内存每像素字节 → (R,G,B) 在字节里的下标
#  32bpp 小端 ARGB8888 内存布局 = B G R A → 'bgra'
_PIXEL_CHANNELS = {
    'bgra': (2, 1, 0), 'rgba': (0, 1, 2), 'argb': (1, 2, 3), 'abgr': (3, 2, 1),
    'bgrx': (2, 1, 0), 'xrgb': (1, 2, 3),
    'rgb888': (0, 1, 2), 'bgr888': (2, 1, 0),
}


def _np():
    try:
        import numpy
        return numpy
    except Exception:
        return None


def detect_pixel_order(data, width, height, stride, bpp, sample=2000):
    """按 alpha 字节位置猜通道序：末字节≈0xFF → BGRA（小端 ARGB8888）；首字节≈0xFF → RGBA。"""
    if bpp != 32:
        return 'bgr565' if bpp == 16 else 'rgb888'
    n = width * height
    step = max(1, n // sample)
    last_hi = first_hi = tot = 0
    for i in range(0, n, step):
        row, col = divmod(i, width)
        off = row * stride + col * 4
        if off + 4 > len(data):
            break
        tot += 1
        if data[off + 3] > 240:
            last_hi += 1
        if data[off] > 240:
            first_hi += 1
    if not tot:
        return 'bgra'
    if last_hi / tot > 0.5 or last_hi >= first_hi:
        return 'bgra'
    return 'rgba'


def decode_raw(data, width, height, stride, bpp, pixel='auto'):
    """fb raw → PIL.Image(RGB)。按 stride 逐行取可见区，避免把 virtual 的脏行画进来。

    注意：新 Pillow（实测 12.x）不再支持 'BGRA'/'BGRX' 等 raw mode，
    所以这里自己做通道置换（numpy 优先，无 numpy 走 bytearray 行循环）。
    """
    if Image is None:
        raise RuntimeError('缺 Pillow（pip install Pillow）')
    if not width or not height:
        raise ValueError('分辨率未知：先确认 /sys/class/graphics/fb0/modes')
    if bpp not in (16, 24, 32):
        raise ValueError(f'不支持的 bpp={bpp}（支持 16/24/32）')
    bpp8 = bpp // 8
    need = stride * height
    if len(data) < need:
        raise ValueError(f'raw 数据不足：需要 {need} 字节（{width}x{height} stride={stride}），'
                         f'实际 {len(data)} 字节')
    if pixel in ('auto', '', None):
        pixel = detect_pixel_order(data, width, height, stride, bpp)
    rowbytes = width * bpp8
    if rowbytes > stride:
        raise ValueError(f'width({width}) x {bpp8}字节/像素 > stride({stride})，尺寸对不上')

    np = _np()
    if np is not None:
        arr = np.frombuffer(data, dtype=np.uint8, count=need).reshape(height, stride)[:, :rowbytes]
        if bpp in (24, 32):
            ch = _PIXEL_CHANNELS.get(pixel, (2, 1, 0))
            rgb = arr.reshape(height, width, bpp8)[:, :, list(ch)]
        else:                                   # 16bpp RGB565（小端 16 位）
            a16 = arr.reshape(height, width, 2)
            v = a16[:, :, 0].astype(np.uint16) | (a16[:, :, 1].astype(np.uint16) << 8)
            hi, lo = (1, 0) if pixel == 'bgr565' else (0, 1)   # 哪个端点占高 5 位
            r5 = ((v >> 11) & 0x1F) if hi else (v & 0x1F)
            g6 = (v >> 5) & 0x3F
            b5 = (v & 0x1F) if hi else ((v >> 11) & 0x1F)
            rgb = np.stack([(r5 * 255 // 31), (g6 * 255 // 63), (b5 * 255 // 31)], axis=2).astype(np.uint8)
        return Image.fromarray(np.ascontiguousarray(rgb), 'RGB'), pixel

    # ---- 无 numpy 的兜底（行循环，慢但正确）
    out = bytearray(width * height * 3)
    if bpp in (24, 32):
        ch = _PIXEL_CHANNELS.get(pixel, (2, 1, 0))
        for y in range(height):
            row = data[y * stride: y * stride + rowbytes]
            base = y * width * 3
            for k, c in enumerate(ch):
                out[base + k::3] = row[c::bpp8]
    else:
        for y in range(height):
            row = data[y * stride: y * stride + rowbytes]
            base = y * width * 3
            for x in range(width):
                v = row[x * 2] | (row[x * 2 + 1] << 8)
                if pixel == 'bgr565':
                    r, g, b = (v >> 11) & 0x1F, (v >> 5) & 0x3F, v & 0x1F
                else:
                    b, g, r = (v >> 11) & 0x1F, (v >> 5) & 0x3F, v & 0x1F
                out[base + x * 3: base + x * 3 + 3] = bytes(
                    (r * 255 // 31, g * 255 // 63, b * 255 // 31))
    return Image.frombytes('RGB', (width, height), bytes(out)), pixel


# ---------------------------------------------------------------- busybox 选取/推送

MONTHS3 = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def _local_busybox_candidates():
    """本仓自带的 busybox（随 MCP 发布在 bin_tools/；工作区另有一份 tools/busybox/bin/）"""
    import glob
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # MCP 根
    pats = [os.path.join(root, 'bin_tools', '*', 'busybox'),
            os.path.join(root, '..', 'busybox', 'bin', '*', 'busybox'),
            os.path.join(root, '..', 'tools', 'busybox', 'bin', '*', 'busybox')]
    found = []
    for p in pats:
        found.extend(sorted(glob.glob(p)))
    return [p for p in found if os.path.isfile(p)]


def _remote_size(adb, dev, path):
    """远程文件体积（多种设备实际格式都要能解）：
      · wc -c / stat -c %s（最准，但设备常缺 applet）
      · ls -l 两种日期格式：`Sep 13 04:01`（英文月）与 `1970-01-01 01:10`（ISO）
    回归：V85X 的 ls 打 ISO 日期，旧版“月份锤点”会解成 0 → 误判压缩失败（真机踩到）。
    """
    for cmd in (f'wc -c < {path} 2>/dev/null', f'stat -c %s {path} 2>/dev/null'):
        out = _sh(adb, dev, cmd)
        try:
            n = int(out.strip())
            if n >= 0:
                return n
        except Exception:
            pass
    out = _sh(adb, dev, f'ls -l {path} 2>/dev/null')
    # ① 体积后面紧跟“英文月”或“ISO 日期”或“HH:MM”
    m = re.search(r'(\d+)\s+(?:[A-Z][a-z]{2}\s+\d|\d{4}-\d{2}-\d{2}|\d{2}:\d{2})', out)
    if m:
        return int(m.group(1))
    # ② 兜底：文件名前面的最后一个纯数字字段
    toks = out.split()
    for t in reversed(toks[:-1]):
        if t.isdigit():
            return int(t)
    return 0


def _has_gzip(adb, dev, cand):
    """探测：这个 busybox 能不能真压缩。

    设备自带 busybox 常是裁剪版（有 echo、没 gzip）——旧版只测 `echo ok` 就选中它，
    结果 `gzip: applet not found` → 远程文件 0 字节（SSD20X/21X 真机踩到）。
    """
    out = _sh(adb, dev, f'{cand} gzip -1 </dev/null >/dev/null 2>&1; echo rc=$?')
    return 'rc=0' in out


def _pick_busybox(adb, dev, notes):
    """选一个**真带 gzip** 的 busybox；设备上没有就自动从本仓推一个到 /tmp/busybox"""
    for cand in ('/tmp/busybox', 'busybox', '/data/busybox', '/bin/busybox', '/usr/bin/busybox'):
        if _has_gzip(adb, dev, cand):
            return cand
    pushed = []
    for local in _local_busybox_candidates():
        a = [adb] + (['-s', dev] if dev else []) + ['push', local, '/tmp/busybox']
        rc, _, _ = _run(a, timeout=120)
        if rc != 0:
            continue
        plate = os.path.basename(os.path.dirname(local))
        pushed.append(plate)
        _sh(adb, dev, 'chmod 777 /tmp/busybox')
        if _has_gzip(adb, dev, '/tmp/busybox'):
            notes.append('设备上没有带 gzip 的 busybox（自带的是裁剪版），已自动推送本仓 %s 版到 /tmp/busybox' % plate)
            return '/tmp/busybox'
    notes.append('设备上没有带 gzip 的 busybox（自带 busybox 缺 gzip applet），本仓 busybox 也没能推上去'
                 '（试过: %s）。可手动 `adb push tools/busybox/bin/<平台>/busybox /tmp/` 后重试。'
                 % (','.join(pushed) or '无可用文件'))
    return ''


# ---------------------------------------------------------------- SigmaStar MI：视频层抓帧（zkshot）

# E_MI_SYS_PixelFormat_e → 名称（设备侧 zkshot 会回报 fmt 值）
MI_FMT = {
    0: 'yuyv422', 1: 'argb8888', 2: 'abgr8888', 3: 'bgra8888',
    4: 'rgb565', 5: 'argb1555', 6: 'argb4444',
    10: 'yuv422sp', 11: 'yuv420sp',
}


def _local_zkshot_candidates():
    """本仓自带的 zkshot 成品（MCP bin_tools/ 与工作区 tools/zkshot/bin/）"""
    import glob
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # MCP 根
    pats = [os.path.join(root, 'bin_tools', '*', 'zkshot'),
            os.path.join(root, '..', 'zkshot', 'bin', '*', 'zkshot'),
            os.path.join(root, '..', 'tools', 'zkshot', 'bin', '*', 'zkshot')]
    found = []
    for p in pats:
        found.extend(sorted(glob.glob(p)))
    return [p for p in found if os.path.isfile(p)]


def _ensure_zkshot(adb, dev, notes):
    """设备上有 zkshot 就用；没有就推一个（z20/z21 成品同 ABI，可混用）"""
    for cand in ('/tmp/zkshot', '/data/zkshot'):
        if _sh(adb, dev, f'test -x {cand} && echo yes') == 'yes':
            return cand
    for local in _local_zkshot_candidates():
        a = [adb] + (['-s', dev] if dev else []) + ['push', local, '/tmp/zkshot']
        rc, _, _ = _run(a, timeout=120)
        if rc != 0:
            continue
        plate = os.path.basename(os.path.dirname(local))
        _sh(adb, dev, 'chmod 777 /tmp/zkshot')
        if 'usage' in _sh(adb, dev, '/tmp/zkshot 2>&1 | head -1'):
            notes.append('设备上没有 zkshot，已推送本仓 %s 成品到 /tmp/zkshot' % plate)
            return '/tmp/zkshot'
    notes.append('设备上没有 zkshot，本仓也没有可用的成品（tools/zkshot/bin/<平台>/zkshot）；'
                 '或跑 tools/zkshot/build/build_all.sh 重新生成')
    return ''


def decode_frame(raw, w, h, stride, fmt):
    """按 MI 帧格式解成 PIL Image（fmt 见 MI_FMT）。不支持的格式明确报错，不静默。"""
    name = MI_FMT.get(int(fmt))
    if name is None:
        raise ValueError('暂不支持的 MI 帧格式 fmt=%s（已知：%s）' % (fmt, sorted(MI_FMT)))

    if name == 'yuv420sp':                                   # NV12：Y 平面 + 交错 UV
        n = W_ = w
        y = raw[:w * h]
        uv = raw[w * h:w * h * 3 // 2]
        buf = bytearray(w * h * 3)
        for j in range(h):
            row = j * stride
            for i in range(w):
                k = j * w + i
                q = ((j // 2) * (w // 2) + (i // 2)) * 2
                buf[k * 3] = y[j * stride + i] if (j * stride + i) < len(y) else 0
                buf[k * 3 + 1] = uv[q] if q < len(uv) else 128
                buf[k * 3 + 2] = uv[q + 1] if q + 1 < len(uv) else 128
        return Image.frombytes('YCbCr', (w, h), bytes(buf)).convert('RGB'), 'yuv420sp->rgb'

    if name == 'yuyv422':                                    # YUYV：每2像素共享 U/V
        buf = bytearray(w * h * 3)
        for j in range(h):
            base = j * stride
            for i in range(0, w - 1, 2):
                p = base + i * 2
                if p + 3 >= len(raw):
                    break
                y0, u, y1, v = raw[p], raw[p + 1], raw[p + 2], raw[p + 3]
                for k, Y in ((i, y0), (i + 1, y1)):
                    o = (j * w + k) * 3
                    buf[o], buf[o + 1], buf[o + 2] = Y, u, v
        return Image.frombytes('YCbCr', (w, h), bytes(buf)).convert('RGB'), 'yuyv422->rgb'

    if name in ('bgra8888', 'argb8888', 'abgr8888'):          # 32bit：按 stride 逐行取
        order = {'bgra8888': 'BGRA', 'argb8888': 'ARGB', 'abgr8888': 'ABGR'}[name]
        rows = b''.join(raw[j * stride:j * stride + w * 4] for j in range(h))
        return Image.frombytes('RGBA' if order in ('BGRA', 'ARGB') else 'RGBA', (w, h),
                               _to_rgba(rows, order)), '%s->rgb' % name

    # rgb565
    buf = bytearray(w * h * 3)
    for j in range(h):
        base = j * stride
        for i in range(w):
            p = base + i * 2
            if p + 1 >= len(raw):
                break
            v = raw[p] | (raw[p + 1] << 8)
            o = (j * w + i) * 3
            buf[o] = ((v >> 11) & 0x1F) * 255 // 31
            buf[o + 1] = ((v >> 5) & 0x3F) * 255 // 63
            buf[o + 2] = (v & 0x1F) * 255 // 31
    return Image.frombytes('RGB', (w, h), bytes(buf)), 'rgb565->rgb'


def _to_rgba(rows, order):
    """32bit 通道序 → RGBA 字节序（PIL 的 RGBA 字节序是 R,G,B,A）"""
    out = bytearray(len(rows))
    for i in range(0, len(rows), 4):
        b0, b1, b2, b3 = rows[i], rows[i + 1], rows[i + 2], rows[i + 3]
        if order == 'BGRA':
            out[i], out[i + 1], out[i + 2], out[i + 3] = b2, b1, b0, b3
        elif order == 'ARGB':
            out[i], out[i + 1], out[i + 2], out[i + 3] = b1, b2, b3, b0
        else:                                                # ABGR
            out[i], out[i + 1], out[i + 2], out[i + 3] = b3, b2, b1, b0
    return bytes(out)


# vdec 通道选错的统一指路文案（视频层抓帧失败时的头号原因）
VDEC_CHN_HINT = ('vdec 通道选错是多路场景「抓不到视频帧」的头号原因：工具默认 chn 0（单路/历史口径），'
                 'SmartPanel 拼墙播放器（多屏拼接 h264_player）在 chn 1。换通道重试 vdec_chn=1 / 0；'
                 '手工等价命令 `zkshot <out.raw> vdec <chn> 0`。注意：Z20 屏保 zkmedia 走 FFmpeg 软解、'
                 '不建 MI VDEC 通道（chn 0 抽不到帧不一定是工具问题，见 knowledge/devflow/device-screenshot.md §4.1.1）。')


def capture_mi_video(device='', out='', fmt='png', scale=1.0, quality=90,
                     timeout=180, name='', adb='', vdec_chn=0):
    """SigmaStar（Z20/Z21）视频层抓帧：zkshot 从**指定 vdec 通道**输出口取一帧 → 本地解码落盘。

    vdec_chn：vdec 通道号（默认 0 —— 与历史行为一致，单路/历史口径）。多路/拼墙必须指定：
      **chn 1 = SmartPanel 拼墙播放器**（多屏拼接 h264_player）。
    注：Z20 屏保 zkmedia 走 FFmpeg 软解、**不建 MI VDEC 通道** → chn 0 抽不到帧未必是工具问题。
    """
    if Image is None:
        return {'success': False, 'error': '缺 Pillow（pip install Pillow），无法解码帧'}
    adb = adb or find_adb()
    dev, err = pick_device(adb, device)
    if not dev:
        return {'success': False, 'error': err}
    notes = []
    remote = '/tmp/.fyshot_video.raw'
    local_raw = os.path.join(os.environ.get('TEMP', os.getcwd()), f'.fyshotvideo_{os.getpid()}.raw')

    zk = _ensure_zkshot(adb, dev, notes)
    if not zk:
        return {'success': False, 'method': 'zkshot-vdec', 'warnings': notes,
                'error': '拿不到 zkshot（设备与本仓都没有可用成品）'}
    try:
        chn = int(vdec_chn or 0)
    except Exception:
        return {'success': False, 'method': 'zkshot-vdec', 'vdecChn': None,
                'warnings': notes, 'error': 'vdec_chn 必须是整数（收到 %r）' % (vdec_chn,),
                'hint': VDEC_CHN_HINT}
    zk_cmd = f'{zk} {remote} vdec {chn} 0'
    outp = _sh(adb, dev, zk_cmd + ' 2>&1', timeout=timeout)
    m = re.search(r'W=(\d+)\s+H=(\d+)\s+fmt=(-?\d+)\s+stride0=(\d+)', outp or '')
    if not m:
        notes.append('zkshot 调用: %s' % zk_cmd)
        notes.append('zkshot 输出无法解析: %s' % (outp or '').replace('\n', ' ')[:200])
        return {'success': False, 'method': 'zkshot-vdec', 'vdecChn': chn, 'warnings': notes,
                'device': dev, 'zkshotCmd': zk_cmd,
                'error': 'zkshot 取帧失败（vdec chn=%d，见 warnings）' % chn,
                'hint': VDEC_CHN_HINT}
    w, h, fmtv, stride = (int(x) for x in m.groups())
    if w <= 0 or h <= 0:
        return {'success': False, 'method': 'zkshot-vdec', 'vdecChn': chn, 'warnings': notes,
                'device': dev, 'zkshotCmd': zk_cmd,
                'error': 'zkshot 在 vdec chn=%d 取到空帧（该通道当前可能没在解码/播放）' % chn,
                'hint': VDEC_CHN_HINT}
    rc, _, errs = _run([adb] + (['-s', dev] if dev else []) + ['pull', remote, local_raw], timeout=timeout)
    if rc != 0 or not os.path.isfile(local_raw):
        return {'success': False, 'method': 'zkshot-vdec', 'vdecChn': chn, 'warnings': notes,
                'device': dev, 'zkshotCmd': zk_cmd,
                'error': 'pull 视频帧失败: %s' % (errs or '')[:200]}
    raw = open(local_raw, 'rb').read()
    try:
        img, conv = decode_frame(raw, w, h, stride, fmtv)
    except Exception as e:
        return {'success': False, 'method': 'zkshot-vdec', 'vdecChn': chn, 'warnings': notes,
                'device': dev, 'zkshotCmd': zk_cmd,
                'error': '解码失败: %s' % e, 'rawBytes': len(raw),
                'frame': {'width': w, 'height': h, 'fmt': fmtv, 'stride': stride}}
    if scale and float(scale) != 1.0:
        img = img.resize((max(1, int(w * float(scale))), max(1, int(h * float(scale)))))
    if not out:
        out = os.path.join('screenshots', 'video_%s_%dx%d.%s' % (name or time.strftime('%H%M%S'),
                                                                  img.width, img.height, fmt))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if fmt == 'jpg':
        img.convert('RGB').save(out, quality=quality)
    elif fmt == 'bmp':
        img.save(out)
    else:
        img.save(out)
    try:
        os.remove(local_raw)
        _sh(adb, dev, f'rm -f {remote}')
    except Exception:
        pass
    return {'success': True, 'path': out, 'width': img.width, 'height': img.height,
            'method': 'zkshot-vdec', 'vdecChn': chn, 'device': dev, 'zkshotCmd': zk_cmd,
            'frame': {'width': w, 'height': h, 'fmt': fmtv,
                      'fmtName': MI_FMT.get(fmtv, str(fmtv)), 'stride': stride},
            'pixelOrder': conv, 'rawBytes': len(raw), 'warnings': notes,
            'note': '视频层帧（非整屏）：想叠回 UI 需要读 mi_disp input port attr 拿屏上位置'}


# ---------------------------------------------------------------- 抓屏主流程

def capture(device='', out='', fmt='png', scale=1.0, quality=90, fb='/dev/fb0',
            width=0, height=0, pixel='auto', flip='', rotate='auto', offset_y=-1,
            crop='', layer='ui', timeout=180, keep_raw=False, name='', adb='',
            vdec_chn=0, _retry=False):
    """抓设备当前屏 → 本地图片。返回 dict（success/path/尺寸/来源/参数…）。

    out      : 输出文件全路径；缺省 screenshots/device_<W>x<H>_<名>_<时间>.<fmt>
    fmt      : png / jpg / bmp
    scale    : 缩放系数（0.5 = 长宽各半，省 AI token）
    fb       : framebuffer 节点（默认 /dev/fb0，部分平台 /dev/disp/fb0、/dev/graphics/fb0）
    pixel    : auto / bgra / rgba / argb / abgr / rgb565 / bgr565 / rgb888 / bgr888（红蓝反了就换）
    offset_y : 抓第几行开始的可见窗口；-1=自动读 sysfs 的 pan（双缓冲时必须看它，否则抓到旧帧）
    flip     : '' / v / h / both
    rotate   : 'auto'（缺省）= 读 /sys/class/graphics/fb0/rotate 按**设备实际角度**转；也可显式 0/90/180/270
               —— 方向以设备自己声明的角度为准，不猜、不写死某台设备
    crop     : '' / 'auto' / 'x,y,w,h'。'auto' = 按 /sys/class/disp/disp/attr/sys 里 UI 图层的 frame
               裁出**项目逻辑分辨率**（只对唯一“非全屏尺寸”图层生效，否则不裁并说明）
    vdec_chn : 仅 layer='video'（SigmaStar）生效：vdec 通道号，**默认 0（向后兼容）**。
               多路/拼墙必须指定——SmartPanel 拼墙播放器在 **chn 1**（默认 chn 0 = 单路/历史口径）；
               选错 = 取不到帧（返回体带 vdecChn/zkshotCmd/hint）。
    """
    if Image is None:
        return {'success': False, 'error': '缺 Pillow（pip install Pillow），无法解码 framebuffer'}
    # 视频层（SigmaStar MI：走 zkshot 从 vdec 输出口取帧；vdec_chn 指定通道）
    if str(layer).lower() in ('video', 'mi', 'vdec'):
        return capture_mi_video(device=device, out=out, fmt=fmt, scale=scale, quality=quality,
                                timeout=timeout, name=name, adb=adb, vdec_chn=vdec_chn)
    t0 = time.time()
    adb = adb or find_adb()
    if not adb:
        return {'success': False, 'error': adb_missing_msg()}
    dev, err = pick_device(adb, device)
    if not dev:
        return {'success': False, 'error': err}

    info = screen_info(dev, fb, adb)
    if not info.get('success'):
        return info
    w = int(width) or info['width']
    h = int(height) or info['height']
    stride = info['stride'] or (w * info['bpp'] // 8)
    bpp = info['bpp']
    oy = int(info.get('offsetY', 0)) if int(offset_y) < 0 else int(offset_y)
    # 旋转角度：缺省 'auto' → **优先读项目工程 EasyUI.cfg 的 rotateScreen**（设备上 /res/etc/EasyUI.cfg），
    #          拿不到才退化用 fb0/rotate。方向以项目自己声明的角度为准，不猜、不写死设备几何。
    rot_src = 'explicit'
    if str(rotate).lower() in ('auto', ''):
        rs = info.get('rotateScreen')
        if isinstance(rs, int):
            rot, rot_src = rs, 'EasyUI.cfg rotateScreen'
        else:
            rot, rot_src = int(info.get('rotate', 0) or 0), 'fb0/rotate(fallback)'
    else:
        try:
            rot = int(rotate)
        except Exception:
            rot, rot_src = 0, 'bad(%s)' % rotate

    # ---- 0) fb **有界**预检（v0.27.179，任务 6）----
    #  先花 ≤8s 定生死：读不通就立刻给结论，不让一次抓屏把时间耗在等待上（默认上限 180s）。
    pre = fb_precheck(dev, fb, adb)
    if not pre['ok']:
        return {'success': False, 'device': dev, 'source': 'framebuffer(' + fb + ')',
                'staleFrame': stale_frame_info(dev, adb, info, fb),
                'blocked': pre['blocked'], 'fbStrays': pre['strays'],
                'error': 'framebuffer 不可读（%s）：%s' % (fb, pre['error'] or '未知'),
                'hint': pre['hint']}

    # ---- 1) 设备侧导出（必须压缩 + 必须按 pan 偏移读！实测裸 raw 7.7MB 经 WiFi pull 要 4 分钟+，
    #         busybox dd(skip=oy) + gzip 后只剩 ~37KB，0.3 秒传完）
    remote = '/tmp/.fyshot.bin'
    local_raw = os.path.join(os.environ.get('TEMP', os.getcwd()),
                             f'.fyshot_{os.getpid()}.bin')
    need = stride * h
    notes = []
    # ★ busybox 必须**真带 gzip** 才算可用（旧版只测 echo，选到裁剪版 busybox → 0 字节）
    bb = _pick_busybox(adb, dev, notes)
    method = ''
    if bb:
        _sh(adb, dev, f'{bb} dd if={fb} bs={stride} skip={oy} count={h} 2>/dev/null | '
                      f'{bb} gzip -1 > {remote} 2>&1', timeout=180)
        fsz = _remote_size(adb, dev, remote)
        if 0 < fsz < need / 2:               # 压缩成功（压缩后必远小于裸帧）
            method = 'busybox-dd-gzip'
        else:
            notes.append('%s dd|gzip 未产出压缩流（%d 字节）' % (bb, fsz))
    pull_timeout = timeout
    if not method:
        # 无压缩通道 → 退化：只读「可见那一帧」的裸数据（慢一点但必成，不依赖 gzip）
        dd = f'dd if={fb} bs={stride} skip={oy} count={h} 2>/dev/null > {remote}'
        _sh(adb, dev, (f'{bb} ' + dd) if bb else dd, timeout=300)
        fsz = _remote_size(adb, dev, remote)
        method = 'raw-visible-frame'
        if fsz < need:
            notes.append('裸帧只读到 %d/%d 字节' % (fsz, need))
        pull_timeout = max(timeout, 30 + need // 20000)   # 裸数据大 → 按体积放宽 pull 超时
    a = [adb] + (['-s', dev] if dev else []) + ['pull', remote, local_raw]
    rc, outp, errs = _run(a, timeout=pull_timeout)
    if rc != 0 or not os.path.isfile(local_raw):
        return {'success': False, 'method': method, 'warnings': notes,
                'error': f'adb pull 失败: {(errs or outp).strip()[:300]}',
                'hint': ('确认设备可达、/tmp 可写。裸 framebuffer 很大（800x1280x4≈4MB/帧），'
                         'WiFi 上 pull 较慢；**设备上放个带 gzip 的 busybox** 可走 dd+gzip 压缩通道。')}

    with open(local_raw, 'rb') as f:
        data = f.read()
    if method.endswith('gzip') or data[:2] == b'\x1f\x8b':
        try:
            data = gzip.decompress(data)
        except Exception as e:
            return {'success': False, 'method': method,
                    'error': f'设备侧 gzip 解压失败: {e}', 'rawBytes': len(data)}
    if not keep_raw:
        try:
            os.remove(local_raw)
            _sh(adb, dev, f'rm -f {remote}')
        except Exception:
            pass
    if oy and len(data) >= (oy + h) * stride:
        data = data[oy * stride:(oy + h) * stride]      # 非 dd 路径：本地按 pan 偏移切

    # pan 二次确认：抓图期间若发生翻页（双缓冲），抓到的是旧帧 → 重抓一次
    if int(offset_y) < 0 and not _retry:
        pan2 = _sh(adb, dev, f'cat /sys/class/graphics/{os.path.basename(fb)}/pan 2>/dev/null')
        try:
            oy2 = int(pan2.split(',')[1]) if ',' in pan2 else None
        except Exception:
            oy2 = None
        if oy2 is not None and oy2 != oy:
            # ⚠️ 重抓必须**原样带上 crop / layer**（2026-09-20 M6 实测缺陷修复）：
            # 旧实现漏传 crop → 抓到的是整屏，而返回体里 crop 字段为空，调用方
            # 以为是「工具不支持/批定无效」，实测复现为「同一参数时而裁时而整屏」
            # （双缓冲 pan 每次翻页都会触发一次重抓，命中率≈50%）。
            return capture(device=device, out=out, fmt=fmt, scale=scale, quality=quality,
                           fb=fb, width=width, height=height, pixel=pixel, flip=flip,
                           rotate=rotate, offset_y=-1, timeout=timeout, crop=crop,
                           layer=layer, keep_raw=keep_raw, name=name, adb=adb,
                           vdec_chn=vdec_chn, _retry=True)

    # ---- 2) 解码
    try:
        img, used_pixel = decode_raw(data, w, h, stride, bpp, pixel)
    except Exception as e:
        return {'success': False, 'method': method, 'screenInfo': info,
                'error': f'解码失败: {e}', 'rawBytes': len(data),
                'hint': f'raw {len(data)} 字节 / 期望 {stride*h}；若不符请显式传 width/height，'
                        f'或检查 bpp={bpp}（16/24/32）'}

    if flip in ('v', 'vertical', 'both'):
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    if flip in ('h', 'horizontal', 'both'):
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    crop_used = ''
    if str(crop).lower() == 'auto':                       # 按 UI 图层裁出项目逻辑分辨率
        L = info.get('uiLayer')
        if L:
            fx, fy, fw, fh = L['frame']
            fx = max(0, fx + int(info.get('offsetX', 0)))  # frame = 面板坐标；本图已按 pan 切过
            fy = max(0, fy - oy)
            img = img.crop((fx, fy, fx + fw, fy + fh))
            crop_used = '%d,%d,%d,%d(uiLayer %dx%d)' % (fx, fy, fw, fh, L['fb'][0], L['fb'][1])
        else:
            crop_used = 'auto-未裁切(disp sys 未找到唯一非全屏图层，请显式传 crop=x,y,w,h)'
    elif crop:
        try:
            cx, cy, cw, ch = [int(v) for v in str(crop).replace(' ', '').split(',')[:4]]
            img = img.crop((cx, cy, cx + cw, cy + ch))
            crop_used = '%d,%d,%d,%d' % (cx, cy, cw, ch)
        except Exception:
            crop_used = 'bad(%s)' % crop
    if rot in (90, 180, 270):
        img = img.rotate(-rot, expand=True)
    if scale and float(scale) != 1.0:
        nw, nh = max(1, int(img.width * float(scale))), max(1, int(img.height * float(scale)))
        img = img.resize((nw, nh), Image.LANCZOS)

    # ---- 3) 存盘
    fmt = (fmt or 'png').lower().lstrip('.')
    if fmt == 'jpeg':
        fmt = 'jpg'
    if out:
        path = out
    else:
        ts = time.strftime('%Y%m%d_%H%M%S')
        tag = f'_{name}' if name else ''
        path = os.path.join(os.getcwd(), 'screenshots',
                            f'device_{img.width}x{img.height}{tag}_{ts}.{fmt}')
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if fmt == 'jpg':
        img.save(path, 'JPEG', quality=int(quality))
    elif fmt == 'bmp':
        img.save(path, 'BMP')
    else:
        img.save(path, 'PNG')

    sf = stale_frame_info(dev, adb, info, fb)
    warn = []
    if sf['verdict'] == 'stale-no-gui':
        warn.append('⚠️ 屏上很可能是**残留旧帧**：%s —— 画面不可信，别据此判断应用状态（黑屏事件同型）'
                    % (sf.get('detail') or ''))
    elif sf['verdict'] == 'gui-blocked':
        warn.append('⚠️ GUI 进程处于 D 状态，大概率不渲染：%s' % (sf.get('detail') or ''))
    elif sf['verdict'] == 'display-idle':
        warn.append('显示中断计数没变（%s）：可能是静态界面，也可能应用没在画 —— '
                    '要确认内容请在界面上做一次已知动作（点击/切页）再抓一张对比'
                    % (sf.get('detail') or ''))

    return {
        'success': True,
        'path': os.path.abspath(path),
        'width': img.width, 'height': img.height,
        'format': fmt, 'sizeBytes': os.path.getsize(path),
        'device': dev, 'source': 'framebuffer(' + fb + ')', 'method': method,
        'screenInfo': {k: info[k] for k in ('width', 'height', 'virtualHeight', 'bpp', 'stride',
                                            'modes', 'offsetY', 'pan', 'rotate', 'rotateScreen',
                                            'rotateTouch')},
        'uiLayer': info.get('uiLayer'),
        'pixelOrder': used_pixel,
        'rotateDeg': rot, 'rotateSource': rot_src, 'crop': crop_used,
        'scale': scale, 'elapsedSec': round(time.time() - t0, 2),
        'staleFrame': sf,
        'warnings': warn,
        'readHint': ('把该文件路径交给视觉模型/看图工具分析（不要把 raw 丢给模型）；'
                     '两张截图对比用 flythings_ui_visual(action="diff")（0 token 出差异清单）。'
                     '颜色红蓝互换 → 重抓时传 pixel=rgba（或 bgra）。'),
    }


def main():
    ap = argparse.ArgumentParser(description='设备真机抓屏 → png/jpg/bmp')
    ap.add_argument('--device', default='', help='设备 IP/序列号（多设备必填）')
    ap.add_argument('--out', default='', help='输出文件全路径')
    ap.add_argument('--name', default='', help='文件名标记（如 main_page）')
    ap.add_argument('--fmt', default='png', choices=['png', 'jpg', 'bmp'])
    ap.add_argument('--scale', type=float, default=1.0)
    ap.add_argument('--quality', type=int, default=90)
    ap.add_argument('--fb', default='/dev/fb0')
    ap.add_argument('--width', type=int, default=0)
    ap.add_argument('--height', type=int, default=0)
    ap.add_argument('--pixel', default='auto')
    ap.add_argument('--offset-y', type=int, default=-1,
                    help='可见窗口起始行；-1=自动读 sysfs 的 pan（双缓冲设备必用，否则抓到旧帧）')
    ap.add_argument('--flip', default='', choices=['', 'v', 'h', 'both'])
    ap.add_argument('--rotate', default='auto',
                    help="缺省 auto=读 /sys/class/graphics/fb0/rotate 按设备实际角度转；也可 0/90/180/270")
    ap.add_argument('--crop', default='',
                    help="'' / auto / x,y,w,h；auto=按 disp attr sys 的 UI 图层 frame 裁出项目逻辑分辨率")
    ap.add_argument('--layer', default='ui',
                    help="ui（默认，fb0）/ video（SigmaStar 视频层，见 --vdec-chn）")
    ap.add_argument('--vdec-chn', type=int, default=0,
                    help="layer=video 时的 vdec 通道号（默认 0；Z20 拼墙在 chn 1、屏保 zkmedia 在 chn 0）")
    ap.add_argument('--keep-raw', action='store_true')
    ap.add_argument('--info', action='store_true', help='只打印屏幕参数，不抓图')
    ap.add_argument('--timeout', type=int, default=180)
    args = ap.parse_args()

    if args.info:
        print(json.dumps(screen_info(args.device, args.fb), ensure_ascii=False, indent=2))
        return 0
    r = capture(device=args.device, out=args.out, fmt=args.fmt, scale=args.scale,
                quality=args.quality, fb=args.fb, width=args.width, height=args.height,
                pixel=args.pixel, flip=args.flip, rotate=args.rotate, offset_y=args.offset_y,
                crop=args.crop, timeout=args.timeout, keep_raw=args.keep_raw, name=args.name,
                layer=args.layer, vdec_chn=args.vdec_chn)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get('success') else 1


if __name__ == '__main__':
    sys.exit(main())
