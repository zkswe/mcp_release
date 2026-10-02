# -*- coding: utf-8 -*-
"""把开机 logo（`boot_logo.JPG`）推到设备并触发升级 —— **默认 dry-run，只打印不动作**。

机制（2026-09-17 口径，与 `update.img` **完全同一套**）：
    adb push <jpg> <dir>/boot_logo.JPG
    setprop sys.zkupgrade.flag 255      # 该目录里有升级物
    setprop sys.zkupgrade.dir  <dir>    # 目录
    setprop ctl.restart zkswe           # 触发升级（重启，**重启后 logo 才生效**）
落点是设备 **MISC 分区**（不是 logo 分区、也不是 `/res`），所以**体积必须 ≤ MISC 分区大小**。

⚠️ 两个现场铁律：
  ① 本板实测 `adb reboot` 后**整板掉网**（只能现场断电重启）→ 触发升级前先确认现场有人能断电；
  ② 升级后**及时拔卡**（TF 卡路线），否则每次重启反复升级。

安全默认：**不加 `--yes` 就一步真命令都不发**（只做只读校验 + 打印将执行的命令清单）。
校验（dry-run 也做）：文件存在 / 是 JPG（`FF D8 FF`）/ 体积 ≤ MISC 上限
（设备在线时会 `cat /proc/mtd` 读**真实**上限，覆盖默认 512 KB）/ 设备在线（adb 走
`adb_tools.resolve_adb()` 单一入口：env `ADB`/`FLYTHINGS_ADB` → 随包 `tools/adb/` → PATH）。

用法（在 MCP 根目录）：
    python tools/set_boot_logo.py --image boot_logo.JPG --device <serial|IP:5555>
    python tools/set_boot_logo.py --image boot_logo.JPG --device <IP>:5555 --dir /tmp --yes
    python tools/set_boot_logo.py --image boot_logo.JPG --device <serial> --no-connect

退出码：0 = 校验通过（dry-run 或已执行）；2 = 校验失败（没碰设备）。
细节与待验证项见 knowledge/devflow/upgrade-pack-image.md §三。
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import adb_tools                                  # noqa: E402  （全仓 adb 单一入口）

DEFAULT_DIR = '/tmp'
DEFAULT_LIMIT_KB = 512        # 本板 MISC = 512 KB；设备在线时用 cat /proc/mtd 覆盖
MISC_RE = re.compile(r'^mtd\d+:\s+([0-9a-fA-F]+)\s+[0-9a-fA-F]+\s+"?([^"]*)"?\s*$')


def is_jpg(path):
    """文件头 `FF D8 FF` = JPEG（比看后缀名靠谱）。"""
    with open(path, 'rb') as f:
        return f.read(3) == b'\xff\xd8\xff'


def parse_mtd(text):
    """`cat /proc/mtd` → {'MISC': KB, ...}（名字大小写归一）。"""
    out = {}
    for line in (text or '').splitlines():
        m = MISC_RE.match(line.strip())
        if not m:
            continue
        try:
            kb = int(m.group(1), 16) // 1024
        except ValueError as e:            # 非十六进制（内核格式变了）→ 记一笔不静默
            print('[warn] /proc/mtd 大小字段解析失败：%r (%s)' % (m.group(1), e))
            continue
        out[m.group(2).strip().upper() or 'MTD%d' % len(out)] = kb
    return out


def device_state(devices, serial):
    """目标设备当前状态（不在列表里回 ''）。"""
    for d in devices:
        if d.get('serial') == serial:
            return d.get('state', '')
    return ''


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='推送 boot_logo.JPG 到设备并触发升级（默认 dry-run）')
    ap.add_argument('--image', required=True, help='本地 JPG 路径')
    ap.add_argument('--device', required=True, help='设备 serial 或 IP:5555（网络接入会自动 connect）')
    ap.add_argument('--dir', default=DEFAULT_DIR, help='设备侧目录（默认 %s）' % DEFAULT_DIR)
    ap.add_argument('--name', default='boot_logo.JPG', help='设备侧文件名（默认 boot_logo.JPG）')
    ap.add_argument('--limit-kb', type=int, default=DEFAULT_LIMIT_KB,
                    help='MISC 体积上限 KB（默认 %d；设备在线时以 cat /proc/mtd 为准）'
                         % DEFAULT_LIMIT_KB)
    ap.add_argument('--no-connect', action='store_true', help='不要 adb connect（USB 直连场景）')
    ap.add_argument('--yes', action='store_true',
                    help='真执行（默认 dry-run：只做只读校验并打印命令清单）')
    a = ap.parse_args(argv)

    plan, fails = [], []
    print('=' * 68)
    print('boot_logo -> MISC   (%s)' % ('真执行' if a.yes else 'DRY-RUN（默认，不动作）'))
    print('=' * 68)

    # ---- 1) 本地文件校验
    img = os.path.abspath(a.image)
    kb = 0.0
    if not os.path.isfile(img):
        fails.append('图片不存在：%s' % img)
    else:
        kb = os.path.getsize(img) / 1024.0
        try:
            jpg = is_jpg(img)
        except OSError as e:
            jpg = False
            fails.append('读图片失败：%s' % e)
        if not jpg:
            fails.append('不是 JPEG（文件头非 FF D8 FF）：%s' % img)
        print('image   : %s' % img)
        print('bytes   : %d  (%.1f KB)' % (os.path.getsize(img), kb))

    adb = adb_tools.resolve_adb()
    src = adb_tools.resolve_adb_info()
    if not adb:
        fails.append(adb_tools.adb_missing_hint())
        print('adb     : 未找到（--image 校验已做，设备侧步骤无法进行）')
    else:
        print('adb     : %s  (source=%s)' % (adb, src['source']))

    # ---- 2) 设备在线校验（只读）
    dev_ok, dev_model, limit_kb = False, '', a.limit_kb
    mtd = {}
    if adb:
        if ':' in a.device and not a.no_connect:
            ok, txt = adb_tools.connect(a.device, adb=adb)
            print('connect : %s -> %s' % (a.device, txt or ('ok' if ok else 'failed')))
            if not ok:
                fails.append('adb connect %s 失败：%s' % (a.device, txt))
        devices, err = adb_tools.list_devices_l(adb)
        if err:
            fails.append('adb devices 失败：%s' % err)
        state = device_state(devices, a.device)
        dev_ok = state == 'device'
        print('device  : %s  state=%s' % (a.device, state or '不在列表里'))
        if not dev_ok:
            fails.append('设备 %s 不在线（state=%s）；在线的：%s'
                         % (a.device, state or '缺失',
                            ', '.join(d['serial'] for d in devices) or '无'))
        else:
            dev_model = adb_tools.getprop_model(adb, a.device)
            print('model   : %s' % (dev_model or '设备未回报 ro.product.model'))
            hit = adb_tools.lookup_model(dev_model) if dev_model else {}
            if hit.get('platform'):
                print('platform: %s (%s)' % (hit['platform'], hit.get('confidence', '')))
            mtd = parse_mtd(adb_tools.sh(adb, a.device, 'cat /proc/mtd'))
            if mtd:
                print('mtd     : %s' % ', '.join('%s=%dKB' % (k, v) for k, v in sorted(mtd.items())))
            if mtd.get('MISC'):
                limit_kb = mtd['MISC']
                print('MISC    : %d KB（实机分区表，用它当上限）' % limit_kb)
            else:
                print('MISC    : 分区表里没读到 MISC 行 → 暂用 --limit-kb=%d 兜底' % a.limit_kb)

    # ---- 3) 体积闸门
    if kb and kb > limit_kb:
        fails.append('图片 %.1f KB 超过上限 %d KB（MISC 分区大小）' % (kb, limit_kb))
    print('limit   : %d KB  (%s)' % (limit_kb, 'ok' if kb <= limit_kb else 'EXCEEDED'))

    remote = a.dir.rstrip('/') + '/' + a.name
    plan = [
        [adb or 'adb', '-s', a.device, 'push', img, remote],
        [adb or 'adb', '-s', a.device, 'shell', 'setprop sys.zkupgrade.flag 255'],
        [adb or 'adb', '-s', a.device, 'shell', 'setprop sys.zkupgrade.dir %s' % a.dir],
        [adb or 'adb', '-s', a.device, 'shell', 'setprop ctl.restart zkswe'],
    ]

    # ---- 4) 执行 / 打印
    if not a.yes:
        print('-' * 68)
        print('将执行（**dry-run：一条都没发**；确认真要触发再加 --yes）：')
        for c in plan:
            print('  ' + ' '.join(c))
        print('重启后生效；本板 adb reboot 会整板掉网 → 需现场断电重启（先定好时机）')
    else:
        if fails:
            print('-' * 68)
            print('[FAIL] 校验没过，**未发任何命令**：')
            for f in fails:
                print('  - %s' % f)
            return 2
        print('-' * 68)
        print('开始执行（触发后设备会重启升级）：')
        for c in plan:
            rc, out, err = adb_tools._run(c, timeout=120)
            print('  $ %s' % ' '.join(c))
            print('    rc=%d %s' % (rc, (out or err or '').strip()[:200]))
            if rc != 0:
                print('[FAIL] 上一条失败，已中止（后续步骤未执行）')
                return 2
        print('[OK] 已触发升级；重启后 logo 生效（TF 卡路线记得拔卡）')

    print('-' * 68)
    for f in fails:
        print('[FAIL] %s' % f)
    if fails and not a.yes:
        print('校验有问题（见上）；dry-run 命令清单仅供参考，别急着 --yes')
        return 2
    print('device online=%s  model=%s  checks=%s' % (dev_ok, dev_model or '-',
                                                    'ok' if not fails else 'fail'))
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
