#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
device_font_check.py —— 设备字体自检（判定是否有中文字库，必要时投递思源黑体）

思路（沛哥 2026-09-13 定）：
  ① `getprop` 拿平台信息（型号/系统/模组）；
  ② 读设备上的 `/etc/font`、`/res/font`（以及 `/system/font`）里字体文件大小；
  ③ **字体只有几十 K / 100 多 K ⇒ 大概率只带英文、没有中文** → 判定"缺中文字库"；
  ④ 缺就默认把我们裁好的**思源黑体**放进去（默认用 `常用中文` 版，海外/多语种场景用 `多国语言` 版）。

用法（Windows 侧直接跑）：
  # 只体检
  python components/fonts/scripts/device_font_check.py
  # 体检 + 自动把字体塞进项目（改 font/ 与 .settings 里的 easyui prefs）
  python components/fonts/scripts/device_font_check.py --apply \
      --project projects/ZkBlePanel --tier common
  # 机器可读
  python components/fonts/scripts/device_font_check.py --json

退出码：0 = 设备已有中文字库；1 = 缺中文字库（需要投递）；2 = 出错。
"""
import argparse
import json
import os
import re
import subprocess
import sys

# 控制台编码随系统（Windows 下常为 GBK）→ 输出里不用 emoji，避免 UnicodeEncodeError
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')   # busybox ls 可能带颜色转义码

MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')

ADB_CANDIDATES = [
    os.path.join('tools', 'FlyThingsIDE', 'sdk', 'platform-tools', 'adb', 'adb.exe'),
    'adb',
]
BUSYBOX_LOCAL = os.path.join('tools', 'busybox', 'bin', 'v85x', 'busybox')
BUSYBOX_REMOTE = '/tmp/busybox_devfontcheck'

# 字体目录候选（按平台差异都扫一遍）
FONT_DIRS = ['/etc/font', '/res/font', '/system/font', '/usr/share/fonts']

# 判定阈值（KB）：小于这个体积的字体，基本只有拉丁字母
CJK_SIZE_MIN_KB = 200

PROPS = ['ro.product.model', 'ro.product.name', 'ro.build.version.release',
         'persist.wifi.module', 'ro.app.name', 'ro.app.version']

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.normpath(os.path.join(HERE, '..', 'fonts'))
TIERS = {
    'common': 'zkswe-hans-common.ttf',   # 常用中文 872KB —— 默认
    'full': 'zkswe-hans-full.ttf',       # 全中文 7.4MB
    'multi': 'zkswe-hans-multi.ttf',     # 多国语言 10.5MB
}


def find_adb(explicit=None):
    if explicit:
        return explicit
    for c in ADB_CANDIDATES:
        if os.path.sep in c and os.path.isfile(c):
            return c
    return 'adb'


def sh(adb, cmd, serial=None):
    args = [adb]
    if serial:
        args += ['-s', serial]
    args += ['shell', cmd]
    try:
        out = subprocess.run(args, capture_output=True, timeout=40)
        return out.stdout.decode('utf-8', 'replace') + out.stderr.decode('utf-8', 'replace')
    except Exception as e:
        return ''


def push_busybox(adb, serial=None):
    if not os.path.isfile(BUSYBOX_LOCAL):
        return False
    args = [adb] + (['-s', serial] if serial else []) + ['push', BUSYBOX_LOCAL, BUSYBOX_REMOTE]
    try:
        subprocess.run(args, capture_output=True, timeout=60)
        sh(adb, 'chmod 777 ' + BUSYBOX_REMOTE, serial)
        return True
    except Exception:
        return False


def collect(adb, serial, use_busybox):
    info = {'props': {}, 'fonts': [], 'raw_dirs': {}}
    for p in PROPS:
        v = sh(adb, 'getprop %s' % p, serial).strip()
        info['props'][p] = v

    # 字体目录清单：优先 busybox（设备自带 ls 常缺 -l 细节/无 du）
    ls = (BUSYBOX_REMOTE + ' ls -l ') if use_busybox else 'ls -l '
    for d in FONT_DIRS:
        out = sh(adb, ls + d + ' 2>/dev/null', serial)
        # ★ 必须剥 ANSI 颜色码：busybox ls 会把文件名包成 \x1b[1;32mname\x1b[m
        lines = [ANSI_RE.sub('', l).strip() for l in out.splitlines()]
        lines = [l for l in lines if l]
        info['raw_dirs'][d] = lines
        for l in lines:
            if not l or l[0] not in '-dl':
                continue
            toks = l.split()
            if len(toks) < 5:
                continue
            name = toks[-1].strip()
            if name in ('.', '..'):
                continue
            if not re.search(r'\.(ttf|ttc|otf)$', name, re.I):
                continue
            # 设备自带 ls 与 busybox ls 字段数不同 → 用“月份”做锚点，体积=月份前一个字段
            size = None
            for i, t in enumerate(toks):
                if t[:3] in MONTHS and i >= 1 and toks[i - 1].isdigit():
                    size = int(toks[i - 1])
                    break
            if size is None:
                continue
            info['fonts'].append({'dir': d, 'name': name, 'sizeBytes': size})
    return info


def judge(info):
    """按"体积"判定是否带中文字库（沛哥口径：几十K/100多K 大概率只有英文）"""
    fonts = sorted(info['fonts'], key=lambda f: -f['sizeBytes'])
    biggest = fonts[0] if fonts else None
    biggest_kb = (biggest['sizeBytes'] / 1024.0) if biggest else 0.0

    verdict = 'no_font'
    if biggest:
        if biggest_kb < CJK_SIZE_MIN_KB:
            verdict = 'no_cjk'          # 只有拉丁
        elif biggest_kb < 1024:
            verdict = 'partial_cjk'     # 像"常用字"级别
        else:
            verdict = 'has_cjk'         # 完整/较大中文字库

    need = verdict in ('no_font', 'no_cjk')
    rec = None
    if need:
        rec = 'common'                  # 默认投递常用中文版
    elif verdict == 'partial_cjk':
        rec = 'full'                    # 已有常用字，缺生僻字时才升级
    return {'verdict': verdict, 'biggest': biggest, 'biggestKB': round(biggest_kb, 1),
            'needFont': need, 'recommendTier': rec}


def apply_to_project(project, tier, font_name, dry_run=False):
    """把选定的思源黑体塞进项目：font/ + .settings easyui prefs 的 font 路径"""
    src = os.path.join(FONT_DIR, font_name)
    if not os.path.isfile(src):
        return False, '字体产物不存在: %s（先跑 gen_font_subset.py）' % src
    font_dir = os.path.join(project, 'font')
    dst = os.path.join(font_dir, font_name)
    prefs = os.path.join(project, '.settings', 'com.zksw.flythings.easyui.prefs')
    changed = []

    if dry_run:
        return True, '(dry-run) 将复制 %s → %s；并改 %s 的 font 键' % (src, dst, prefs)

    os.makedirs(font_dir, exist_ok=True)
    with open(src, 'rb') as f:
        data = f.read()
    with open(dst, 'wb') as f:
        f.write(data)
    changed.append(dst)

    if os.path.isfile(prefs):
        with open(prefs, 'r', encoding='utf-8') as f:
            text = f.read()
        new = re.sub(r'"font"\:"[^"]*"', '"font"\\:"/res/font/%s"' % font_name, text)
        if new == text and '"font"' not in text:
            # 没有 font 键 → 挂在 uart 后面；没有 uart 就挂在 baud 后面
            for anchor in ('"uart"\\:"[^"]*"', '"baud"\\:"[^"]*"'):
                n2 = re.sub(anchor, lambda m: m.group(0) + ',"font"\\:"/res/font/%s"' % font_name, text)
                if n2 != text:
                    new = n2
                    break
        if new != text:
            with open(prefs, 'w', encoding='utf-8') as f:
                f.write(new)
            changed.append(prefs)
    else:
        return False, '项目的 easyui prefs 不存在: %s' % prefs

    return True, '已应用：' + '，'.join(changed) + '（之后 fun build → pack_upgrade → 固化）'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--adb', default=None, help='adb 路径（默认自动找）')
    ap.add_argument('--serial', default=None, help='多设备时指定')
    ap.add_argument('--json', action='store_true', help='只输出 JSON')
    ap.add_argument('--apply', action='store_true', help='缺中文字库时自动投递字体到项目')
    ap.add_argument('--project', default=None, help='要投递字体进去的 app 工程根目录')
    ap.add_argument('--tier', default=None, choices=sorted(TIERS.keys()),
                    help='强制指定版本（默认按体检结果推荐）')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--debug', action='store_true', help='打印原始 ls 输出（解析异常时用）')
    args = ap.parse_args()

    adb = find_adb(args.adb)
    use_busybox = os.path.isfile(BUSYBOX_LOCAL)
    if use_busybox:
        push_busybox(adb, args.serial)

    info = collect(adb, args.serial, use_busybox)
    if args.debug and not args.json:
        for d, lines in info['raw_dirs'].items():
            print('--- %s ---' % d)
            for l in lines:
                print('  ' + l)
    verdict = judge(info)
    tier = args.tier or verdict['recommendTier'] or 'common'
    if tier not in TIERS:
        tier = 'common'

    result = {'platform': info['props'], 'fonts': info['fonts'],
              'verdict': verdict['verdict'], 'biggestKB': verdict['biggestKB'],
              'needFont': verdict['needFont'], 'tier': tier,
              'tierFile': TIERS[tier]}

    if args.apply and verdict['needFont'] and args.project:
        ok, msg = apply_to_project(args.project, tier, TIERS[tier], args.dry_run)
        result['apply'] = {'ok': ok, 'msg': msg}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        p = info['props']
        print('=== 设备字体自检 ===')
        print('型号     : %s' % (p.get('ro.product.model') or '?'))
        print('系统     : %s' % (p.get('ro.build.version.release') or '?'))
        print('BT 模组  : %s' % (p.get('persist.wifi.module') or '?'))
        print('应用     : %s %s' % (p.get('ro.app.name') or '-', p.get('ro.app.version') or ''))
        print('字体清单 :')
        if not info['fonts']:
            print('  （一个字体文件都没找到）')
        for f in sorted(info['fonts'], key=lambda x: -x['sizeBytes']):
            print('  %-8s %10.1f KB  %s' % (f['dir'], f['sizeBytes'] / 1024.0, f['name']))
        if verdict['biggest']:
            print('最大字体 : %.1f KB（阈值 %d KB）' % (verdict['biggestKB'], CJK_SIZE_MIN_KB))
        v = verdict['verdict']
        if v == 'has_cjk':
            print('判定     : [OK] 设备自带中文字库，无需投递')
        elif v == 'partial_cjk':
            print('判定     : [WARN] 像“常用字”级别字库；有生僻字需求建议换 full 版')
        elif v == 'no_cjk':
            print('判定     : [X] 字体只有 %.1f KB，大概率只带英文 -> 需要投递思源黑体' % verdict['biggestKB'])
        else:
            print('判定     : [X] 设备上没有字体 -> 需要投递思源黑体')
        if verdict['needFont'] or v == 'partial_cjk':
            print('建议版本 : %s（%s）' % (tier, TIERS[tier]))
            if args.project:
                print('投递命令 : python %s --apply --project %s --tier %s' %
                      (os.path.relpath(__file__), args.project, tier))
        if 'apply' in result:
            print('投递结果 : %s %s' % ('OK' if result['apply']['ok'] else 'FAIL', result['apply']['msg']))

    return 0 if not verdict['needFont'] else 1


if __name__ == '__main__':
    sys.exit(main())
