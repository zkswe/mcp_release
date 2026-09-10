#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
device_screenshot.py — 从设备真机抓屏，转成 PNG / JPG / BMP 交给 AI 分析

【为什么不能用 screencap】（2026-09-10 真机实测 192.168.0.117）
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
    python device_screenshot.py --device 192.168.0.117:5555 --name main_page
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
    r'tools\FlyThingsIDE\sdk\platform-tools\adb\adb.exe',
    r'sim\tools\adb.exe',
    r'sim\tools\platform-tools\adb.exe',
    r'qemu-openwrt\tools\platform-tools\adb.exe',
]


def find_adb():
    """找 adb：环境变量 ADB > PATH > workspace 常见位置（向上逐级找）。返回路径或 None。"""
    env = os.environ.get('ADB') or os.environ.get('ADB_PATH')
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
    for k in ('rotateScreen', 'rotateTouch', 'resPath', 'startupLibPath', 'touchDev',
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
        return {'success': False, 'error': '找不到 adb（设环境变量 ADB 或装 Android platform-tools）'}
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


# ---------------------------------------------------------------- 抓屏主流程

def capture(device='', out='', fmt='png', scale=1.0, quality=90, fb='/dev/fb0',
            width=0, height=0, pixel='auto', flip='', rotate='auto', offset_y=-1,
            crop='', timeout=180, keep_raw=False, name='', adb='', _retry=False):
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
    """
    if Image is None:
        return {'success': False, 'error': '缺 Pillow（pip install Pillow），无法解码 framebuffer'}
    t0 = time.time()
    adb = adb or find_adb()
    if not adb:
        return {'success': False, 'error': '找不到 adb（设环境变量 ADB 或装 Android platform-tools）'}
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

    # ---- 1) 设备侧导出（必须压缩 + 必须按 pan 偏移读！实测裸 raw 7.7MB 经 WiFi pull 要 4 分钟+，
    #         busybox dd(skip=oy) + gzip 后只剩 ~37KB，0.3 秒传完）
    remote = '/tmp/.fyshot.bin'
    local_raw = os.path.join(os.environ.get('TEMP', os.getcwd()),
                             f'.fyshot_{os.getpid()}.bin')
    bb = ''
    for cand in ('busybox', '/tmp/busybox', '/data/busybox', '/usr/bin/busybox'):
        if 'ok' in _sh(adb, dev, f'{cand} echo ok 2>/dev/null'):
            bb = cand
            break
    method = 'cat-full'
    need = stride * h
    if bb:
        _sh(adb, dev, f'{bb} dd if={fb} bs={stride} skip={oy} count={h} 2>/dev/null | '
                      f'{bb} gzip -1 > {remote}', timeout=120)
        sz = _sh(adb, dev, f'{bb} ls -l {remote}')
        try:
            fsz = int(sz.split()[4]) if sz else 0
        except Exception:
            fsz = 0
        if 0 < fsz < need / 2:              # 压缩过了才算成功（未压缩的 raw 更大）
            method = 'busybox-dd-gzip'
        else:                                # 没压成功 → 整片 gzip（本地再按 oy 切）
            _sh(adb, dev, f'{bb} cat {fb} | {bb} gzip -1 > {remote}', timeout=120)
            method = 'busybox-cat-gzip'
    if method == 'cat-full':
        _sh(adb, dev, f'cat {fb} > {remote}; ls -l {remote}', timeout=120)
    a = [adb] + (['-s', dev] if dev else []) + ['pull', remote, local_raw]
    rc, outp, errs = _run(a, timeout=timeout)
    if rc != 0 or not os.path.isfile(local_raw):
        return {'success': False, 'method': method,
                'error': f'adb pull 失败: {(errs or outp).strip()[:300]}',
                'hint': ('确认设备可达、/tmp 可写。裸 framebuffer 很大（600x1600x4≈7.7MB），'
                         'WiFi 上 pull 要几分钟；**设备上放个 busybox**（tools/busybox/bin/<平台>/busybox）'
                         '可走 dd+gzip 压缩通道，实测 37KB/0.3s。')}

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
            return capture(device=device, out=out, fmt=fmt, scale=scale, quality=quality,
                           fb=fb, width=width, height=height, pixel=pixel, flip=flip,
                           rotate=rotate, offset_y=-1, timeout=timeout,
                           keep_raw=keep_raw, name=name, adb=adb, _retry=True)

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
        'readHint': ('把该文件路径交给视觉模型/看图工具分析（不要把 raw 丢给模型）；'
                     '两张截图对比用 flythings_ui_diff（0 token 出差异清单）。'
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
                crop=args.crop, timeout=args.timeout, keep_raw=args.keep_raw, name=args.name)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get('success') else 1


if __name__ == '__main__':
    sys.exit(main())
