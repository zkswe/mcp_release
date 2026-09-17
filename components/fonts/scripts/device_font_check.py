#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
device_font_check.py —— 设备字体自检（判定是否有中文字库，必要时投递思源黑体）

思路（沛哥 2026-09-13 定；v0.27.87 起主判据升级为 **cmap 覆盖率硬判据**）：
  ① `getprop` 拿平台信息（型号/系统/模组）；
  ② 读设备上的 `/etc/font`、`/res/font`（以及 `/system/font`）里字体文件大小 → 挑最大的那个；
  ③ **硬判据（钟工 2026-09-17 拍板）**：把最大的字体**拉回 PC**，用 `fontTools.ttLib` 读它的
     **cmap**，以 **GB2312 一级 3755 字** 为基准算覆盖率 `cmapCoverageGB2312L1`：
       ≥ 90% → `ok`（不投递）／ 50–90% → `low`（投递 + 说明覆盖率）／ < 50% → `missing`（投递）
     —— 比体积判据准：体积像中文的字体也可能 cmap 里只有拉丁（反过来也一样）；
  ④ **兜底（绝不静默）**：字体体积超过 `PROBE_MAX_BYTES`（12 MB）或 `fontTools` 不可用
     / cmap 解析失败 / 拉取失败 → **退回体积判据**（`source="size"`，原因写进 warnings）；
  ⑤ 缺就默认把我们裁好的**思源黑体**放进去（默认用 `常用中文` 版，海外/多语种场景用 `多国语言` 版）。

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
import shutil
import subprocess
import sys
import tempfile

# 控制台编码随系统（Windows 下常为 GBK）→ 输出里不用 emoji，避免 UnicodeEncodeError
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')   # busybox ls 可能带颜色转义码

MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')

# v0.27.84：没有显式指定时，adb 优先走仓库的 adb_tools.resolve_adb()
# （环境变量 ADB/FLYTHINGS_ADB → 随包 tools/adb/adb.exe → PATH），本文件不再写死候选路径。
ADB_CANDIDATES = [
    os.path.join('tools', 'adb', 'adb.exe'),
    'adb',
]
BUSYBOX_LOCAL = os.path.join('tools', 'busybox', 'bin', 'v85x', 'busybox')
BUSYBOX_REMOTE = '/tmp/busybox_devfontcheck'

# 字体目录候选（按平台差异都扫一遍）
FONT_DIRS = ['/etc/font', '/res/font', '/system/font', '/usr/share/fonts']

# 判定阈值（KB）：小于这个体积的字体，基本只有拉丁字母 —— **只作兜底判据**（v0.27.87 起）
CJK_SIZE_MIN_KB = 200

# ---------------- 硬判据：cmap 覆盖率（v0.27.87，钟工 2026-09-17 拍板）----------------
# 基准 = GB2312 一级汉字 3755 个（0xB0A1–0xD7FE，含 5 个未定义码位被 codec 剔除）
CMAP_TOTAL_CHARS = 3755
CMAP_OK_MIN_PCT = 90.0        # ≥ 90% → ok（设备中文字库可用，不投递）
CMAP_LOW_MIN_PCT = 50.0       # 50–90% → low（投递）；< 50% → missing（投递）
PROBE_MAX_BYTES = 12 * 1024 * 1024   # 拉取上限 12 MB：超了就不拉，直接退回体积判据

_CACHE = {}

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
    """adb 路径：显式参数 > adb_tools.resolve_adb()（环境变量 > 随包 > PATH）> 候选表 > 'adb'。"""
    if explicit:
        return explicit
    cur = HERE
    for _ in range(6):                      # 向上找仓库根的 adb_tools.py
        if os.path.isfile(os.path.join(cur, 'adb_tools.py')):
            if cur not in sys.path:
                sys.path.insert(0, cur)
            try:
                import adb_tools as _at
                p = _at.resolve_adb()
                if p:
                    return p
            except Exception:
                break
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
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
            si = None
            for i, t in enumerate(toks):
                if t[:3] in MONTHS and i >= 1 and toks[i - 1].isdigit():
                    size = int(toks[i - 1])
                    si = i - 1
                    break
            if size is None:
                continue
            # mtime 文本（月份+日期+时刻/年份）→ 只作缓存键的一部分（v0.27.87）：
            # 设备侧字体被换过（体积一样但时间变了）也能让缓存失效，**不做语义解析**（格式随 ls 变）
            mtime_text = ' '.join(toks[si + 1:-1]) if si is not None else ''
            info['fonts'].append({'dir': d, 'name': name, 'sizeBytes': size,
                                  'mtimeText': mtime_text})
    return info


# ---------------- 硬判据实现（cmap 覆盖率）----------------
def gb2312_level1():
    """GB2312 一级汉字 3755 字（0xB0A1–0xD7FE）。

    不依赖外部数据文件：用标准库 `gb2312` codec 逐码位解码，解不出的（5 个未定义码位）跳过
    → 结果恰好 3755 个。这是覆盖率判据的**基准集合**，与是否装有中文码表无关。
    """
    if 'L1' not in _CACHE:
        chars = []
        for hi in range(0xB0, 0xD8):
            for lo in range(0xA1, 0xFF):
                # errors='ignore'：0xD7FA–0xD7FE 这 5 个码位在 GB2312 里未定义，解出来是空串
                # （不用 try/except 卡控制流；总数恰好 3755 由契约用例钉死）
                ch = bytes([hi, lo]).decode('gb2312', 'ignore')
                if ch:
                    chars.append(ch)
        _CACHE['L1'] = chars
    return _CACHE['L1']


def fonttools_error():
    """`fontTools` 是否可用；不可用回原因（调用方据此退回体积判据，不静默）。"""
    try:
        import fontTools.ttLib                     # noqa: F401
        return ''
    except Exception as e:
        return '%s: %s' % (type(e).__name__, e)


def font_cmap_coverage(path):
    """读字体 cmap → GB2312 一级覆盖率。返回 (pct, covered, total, error)。

    `.ttc` 取第 0 号字体（设备上多为单字体 ttc）；只统计 Unicode cmap 子表。
    解析失败 / 一个 Unicode cmap 子表都没读到 → 回 (None, 0, 3755, 原因)，由调用方退回体积判据。
    """
    chars = gb2312_level1()
    bad_tables = []
    try:
        from fontTools.ttLib import TTFont
        tt = TTFont(path, fontNumber=0, lazy=True)
        try:
            codes = set()
            for tb in tt['cmap'].tables:
                # 非 Unicode 子表（平台专有编码）直接跳过；子表读不出来时记下原因（不当成「没有中文」）
                try:
                    is_uni, sub = tb.isUnicode(), tb.cmap
                except Exception as e:
                    bad_tables.append('%s: %s' % (type(e).__name__, e))
                    continue
                if is_uni and sub:
                    codes |= set(sub.keys())
        finally:
            tt.close()
    except Exception as e:
        return None, 0, len(chars), '%s: %s' % (type(e).__name__, e)
    if not codes:
        return None, 0, len(chars), ('字体没有可读的 Unicode cmap 子表（跳过 %d 个：%s）'
                                     % (len(bad_tables), '；'.join(bad_tables[:2]) or '无'))
    covered = 0
    for ch in chars:
        if ord(ch) in codes:
            covered += 1
    return round(covered * 100.0 / len(chars), 1), covered, len(chars), ''


def judge_cmap(pct):
    """硬判据：≥90% ok（不投递）／50–90% low（投递）／<50% missing（投递）。"""
    if pct >= CMAP_OK_MIN_PCT:
        verdict, need, rec = 'ok', False, None
    elif pct >= CMAP_LOW_MIN_PCT:
        verdict, need, rec = 'low', True, 'common'
    else:
        verdict, need, rec = 'missing', True, 'common'
    return {'verdict': verdict, 'needFont': need, 'recommendTier': rec, 'source': 'cmap',
            'coveragePct': pct, 'reason': ''}


def pre_pull_block(size_bytes):
    """拉取前的**本地闸门**（不碰设备）：① 体积超限 ② fontTools 不可用。

    返回原因字符串（'' = 可以拉）。判定规则的唯一来源就在这里 —— 调用方（font_tools 的
    缓存/拉取接线、本模块 CLI）不再各自写一遍阈值与文案。
    """
    size = int(size_bytes or 0)
    if size > PROBE_MAX_BYTES:
        return ('字体 %d B 超过拉取上限 %d B（PROBE_MAX_BYTES）→ 不拉取，退回体积判据'
                % (size, PROBE_MAX_BYTES))
    err = fonttools_error()
    if err:
        return ('fontTools 不可用（%s）→ 无法算 cmap 覆盖率，退回体积判据' % err)
    return ''


def probe_font(path, size_bytes=None):
    """**单个本地字体**（一般是刚从设备拉回来的）→ 硬判据结论。

    返回 dict：source='cmap'（含 coveragePct/coveredChars/totalChars）或 source='size'
    （含 reason：超限 / fontTools 不可用 / 解析失败），verdict 在 source='size' 时为 None
    （由调用方保留体积判据的结论，并**必须**把 reason 写进 warnings）。
    """
    size = int(size_bytes) if size_bytes is not None else (os.path.getsize(path)
                                                           if os.path.isfile(path) else 0)
    if not os.path.isfile(path):
        return {'source': 'size', 'verdict': None, 'needFont': None, 'recommendTier': None,
                'coveragePct': None, 'reason': '字体文件不存在: %s' % path}
    block = pre_pull_block(size)
    if block:
        return {'source': 'size', 'verdict': None, 'needFont': None, 'recommendTier': None,
                'coveragePct': None, 'reason': block}
    pct, covered, total, cerr = font_cmap_coverage(path)
    if pct is None:
        return {'source': 'size', 'verdict': None, 'needFont': None, 'recommendTier': None,
                'coveragePct': None,
                'reason': ('字体 cmap 解析失败（%s）→ 退回体积判据' % cerr)}
    out = judge_cmap(pct)
    out.update({'coveredChars': covered, 'totalChars': total, 'thresholds':
                {'okMinPct': CMAP_OK_MIN_PCT, 'lowMinPct': CMAP_LOW_MIN_PCT}})
    return out


def pull_font(adb, serial, remote_path, dest_path, timeout=180):
    """`adb pull` 设备上的单个字体文件 → (ok, msg)。

    ⚠️ 只拉一个文件（调用方已按体积限过）；失败**不静默**，由调用方退回体积判据并写 warnings。
    """
    a = adb or find_adb()
    args = [a] + (['-s', serial] if serial else []) + ['pull', remote_path, dest_path]
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout)
    except Exception as e:
        return False, 'adb pull 异常: %s: %s' % (type(e).__name__, e)
    out = ((r.stdout or b'').decode('utf-8', 'replace')
           + (r.stderr or b'').decode('utf-8', 'replace')).strip()
    ok = (r.returncode == 0 and os.path.isfile(dest_path)
          and os.path.getsize(dest_path) > 0)
    return ok, out.replace('\n', ' ')[:300]


def md5_of(path):
    """文件 md5（空串 = 读不到）——缓存记录/回报用，不参与判定。"""
    import hashlib
    try:
        h = hashlib.md5()
        with open(path, 'rb') as f:
            for blk in iter(lambda: f.read(1 << 20), b''):
                h.update(blk)
        return h.hexdigest()
    except Exception:
        return ''


def probe_device_font(adb, serial, font):
    """把设备上**某个**字体拉回临时目录 → `probe_font()` 硬判据 → **用完即删**（自建临时目录）。

    `font` = collect() 给的 {'dir','name','sizeBytes',...}。返回 probe_font 的字段 + ：
      localBytes / md5 / pulled（有没有真拉）/ reason（退回体积判据的原因，写进 warnings）。
    超限（> PROBE_MAX_BYTES）时**不拉取**（先看体积再看拉取，别把 12MB+ 拖回来）。
    """
    out = {'pulled': False, 'localBytes': 0, 'md5': '', 'localPath': '', 'reason': ''}
    size = int(font.get('sizeBytes') or 0)
    block = pre_pull_block(size)
    if block:
        out.update({'source': 'size', 'verdict': None, 'needFont': None,
                    'recommendTier': None, 'coveragePct': None, 'reason': block})
        return out
    tmp = tempfile.mkdtemp(prefix='font_probe_')
    local = os.path.join(tmp, os.path.basename(font.get('name') or 'device.ttf'))
    try:
        ok, msg = pull_font(adb, serial, (font.get('dir') or '') + '/' + (font.get('name') or ''),
                            local)
        if not ok:
            out.update({'source': 'size', 'verdict': None, 'needFont': None,
                        'recommendTier': None, 'coveragePct': None,
                        'reason': ('字体拉取失败（%s）→ 退回体积判据' % (msg or '无输出'))})
            return out
        out['pulled'] = True
        out['localPath'] = local
        out['localBytes'] = os.path.getsize(local)
        out['md5'] = md5_of(local)
        got = probe_font(local, out['localBytes'])
        out.update(got)
        return out
    finally:                       # 临时目录一律自建自删（不往工作区/系统临时目录留垃圾）
        shutil.rmtree(tmp, ignore_errors=True)


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
        # ★ v0.27.86 修：兼容 prefs 里转义（"font"\:"x"）与非转义（"font":"x"）两种写法 ——
        #   原正则只认未转义，而真 prefs 是转义，导致「改 prefs」实际没改成
        new = re.sub(r'"font"\s*\\?\s*:\s*"[^"]*"', '"font"\\:"/res/font/%s"' % font_name,
                     text)
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
    ap.add_argument('--no-probe', dest='probe', action='store_false',
                    help='不做 cmap 硬判据（不拉字体回本机），只用体积判据')
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
    # 硬判据（v0.27.87）：挑最大字体拉回本机算 cmap 覆盖率；
    # 超限 / fontTools 不可用 / 拉取失败 / 解析失败 → 退回体积判据（原因进 reason，不静默）
    probe = None
    if args.probe and info['fonts']:
        biggest = sorted(info['fonts'], key=lambda f: -f['sizeBytes'])[0]
        probe = probe_device_font(adb, args.serial, biggest)
    hard = bool(probe and probe.get('source') == 'cmap')
    need = probe['needFont'] if hard else verdict['needFont']
    tier = args.tier or (probe['recommendTier'] if hard else verdict['recommendTier']) or 'common'
    if tier not in TIERS:
        tier = 'common'

    result = {'platform': info['props'], 'fonts': info['fonts'],
              'verdict': (probe['verdict'] if hard else verdict['verdict']),
              'source': 'cmap' if hard else 'size',
              'cmapCoverageGB2312L1': (probe or {}).get('coveragePct'),
              'biggestKB': verdict['biggestKB'],
              'needFont': need, 'tier': tier,
              'tierFile': TIERS[tier]}
    if probe:
        result['probe'] = {k: probe.get(k) for k in
                           ('source', 'reason', 'coveredChars', 'totalChars', 'pulled',
                            'localBytes', 'md5')}

    if args.apply and result['needFont'] and args.project:
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
            print('最大字体 : %.1f KB（体积阈值 %d KB）' % (verdict['biggestKB'], CJK_SIZE_MIN_KB))
        if probe:
            if hard:
                print('判定依据 : cmap 覆盖率 %.1f%%（GB2312 一级 %s/%s 字）'
                      % (probe['coveragePct'], probe.get('coveredChars'), probe.get('totalChars')))
            else:
                print('判定依据 : 退回体积判据 —— %s' % (probe.get('reason') or ''))
        v = result['verdict']
        if v in ('ok', 'has_cjk'):
            print('判定     : [OK] 设备自带中文字库（判定=%s），无需投递' % v)
        elif v in ('low', 'partial_cjk'):
            print('判定     : [WARN] 中文字库不全（判定=%s）；默认投 %s 档补齐'
                  % (v, tier))
        elif v == 'no_cjk':
            print('判定     : [X] 字体只有 %.1f KB，大概率只带英文 -> 需要投递思源黑体' % verdict['biggestKB'])
        elif v in ('missing', 'no_font'):
            print('判定     : [X] 设备上没有可用中文字库 -> 需要投递思源黑体')
        if need or v == 'partial_cjk':
            print('建议版本 : %s（%s）' % (tier, TIERS[tier]))
            if args.project:
                print('投递命令 : python %s --apply --project %s --tier %s' %
                      (os.path.relpath(__file__), args.project, tier))
        if 'apply' in result:
            print('投递结果 : %s %s' % ('OK' if result['apply']['ok'] else 'FAIL', result['apply']['msg']))

    return 0 if not need else 1


if __name__ == '__main__':
    sys.exit(main())
