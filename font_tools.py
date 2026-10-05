# -*- coding: utf-8 -*-
"""font_tools.py —— 字体自动扫描接线（设备侧优先，退化到工程侧）+ 缺中文自动投递。

为什么有（2026-09-17「现在做」）：
  `components/fonts/scripts/device_font_check.py` 早就实现了「扫设备字体 + 缺中文投递思源黑体」，
但**没有任何 op 包它、也没接进 build/deploy 流程**→ 等于没做：客户撞到「界面汉字全变方块」
时才知道要手动跑脚本。本模块把这一步接成**自动动作**（与 build_ui_flow 的依赖/install 体检同一套思路）。

单一事实来源（不许两套判定规则）：判定阈值 / 字体目录 / 三版字体清单 / 投递动作（copy→font/ + 改 easyui prefs）
  **全部 import `device_font_check`**（`judge()` / `TIERS` / `collect()` / `apply_to_project()`）；
本模块只负责接线：设备探测（`adb_tools.resolve_adb()` / `probe_devices()` / `ensure_busybox()`）
  → 判定 → 需要就投递 → 组织成体检字段（missingChinese / maxFontBytes / advisedTier / delivered /
  deviceFonts），失败一律进 warnings，**不新增静默 except**。

两条分支：
  ① **有设备**：扫 `/etc/font`、`/res/font`、`/system/font`、`/usr/share/fonts` 里字体体积，
挑出最大者；**v0.27.87 起优先「硬判据」**——把最大字体拉回 PC（临时目录，用完即删），
用 fontTools 读 cmap 算 **GB2312 一级 3755 字覆盖率**：≥90% → ok（不投递）/ 50–90% → low
     （投递 + 写明覆盖率）/ <50% → missing（投递）；拉取超 12 MB、fontTools 不可用、拉取或解析
失败 → **退回体积判据**（source='size'，原因进 warnings，绝不静默）。结论按
     `serial+目录/文件名+体积+ls 时间` 缓存到 `~/.fsc/font-probe.json`（09-28 起；旧 `~/.fun/`）（否则每次 build 都拉一遍）。
缺 → 默认投递 `common`（872 KB）进工程 `font/`；
  ② **无设备**：退化为工程侧 self-scan（prefs 的 `font` 指向的文件在不在工程 `font/`；
工程 `font/` 里有没有可用字体）→ 缺就同样投递，并在 `note` 写清「未连设备，仅工程侧检查」。

部署后复查（v0.27.87）：`fun launch` 成功后且本次投递过字体 → `recheck_after_deploy()` 回看
设备侧字体清单与工程投递是否一致，回答「设备侧中文字库现在可用吗 / 要不要固化」
  （与应用侧的 `staleOnDevice` 合成闭环：app 陈旧 vs 字库待固化分开报）。

开关：`font_check='auto'`（默认）/ `'off'`（完全不碰字体，零 step）；`font_tier='common'|'full'|'multi'`。
默认 common；要生僻字换 full；多语言/日韩换 multi；**只有要更小体积/自定义字符集才需要自己裁字库**。
"""
import importlib.util
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    import adb_tools as _adb
    _ADB_ERR = ''
except Exception as e:                                   # adb 子系统不可用 → 只做工程侧检查
    _adb = None
    _ADB_ERR = '%s: %s' % (type(e).__name__, e)

DFC_PATH = os.path.join(HERE, 'components', 'fonts', 'scripts', 'device_font_check.py')
FONT_EXTS = ('.ttf', '.ttc', '.otf')
PREFS_REL = os.path.join('.settings', 'com.zksw.flythings.easyui.prefs')
# 硬判据缓存（v0.27.87）：避免每次 build 都把同一个字体从设备拉一遍（慢、烧流量、伤 flash 寿命）
PROBE_CACHE_NAME = 'font-probe.json'
PROBE_CACHE_VERSION = 1
# 判定阈值只从 device_font_check 读（这里不复制数字）：CJK_SIZE_MIN_KB 等
_DFC = {'mod': None, 'error': ''}

# 关掉字体的写法（都当 'off'）：既要人性化，也要防 AI 传 False/0
OFF_VALUES = ('off', 'false', '0', 'no', 'none', 'disable', 'disabled', '')


def device_font_check():
    """加载（并缓存）`device_font_check` 模块 —— 判定/投递规则的单一来源。

返回 (mod, error)；mod 为 None 时 error 写明原因（调用方进 warnings，不静默）。
    """
    if _DFC['mod'] is not None or _DFC['error']:
        return _DFC['mod'], _DFC['error']
    if not os.path.isfile(DFC_PATH):
        _DFC['error'] = '缺字体自检脚本: %s' % DFC_PATH
        return None, _DFC['error']
    try:
        spec = importlib.util.spec_from_file_location('device_font_check', DFC_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:
        _DFC['error'] = '加载 device_font_check 失败: %s: %s' % (type(e).__name__, e)
        return None, _DFC['error']
    bb = os.path.join(HERE, 'tools', 'busybox', 'bin', 'v85x', 'busybox')
    if os.path.isfile(bb):
        mod.BUSYBOX_LOCAL = bb              # CWD 无关：候选写仓库内绝对路径
    _DFC['mod'] = mod
    return mod, ''


def is_off(font_check):
    """`font_check` 是否要跳过字体动作（'off'/False/0/'' 均视为关）。"""
    return str(font_check).strip().lower() in OFF_VALUES


def _read(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return None


def _write(path, text):
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


# ---------------- 工程侧 self-scan（无设备分支）----------------
def project_fonts(project_root):
    """工程 `font/` 下的字体文件 [{dir,name,sizeBytes}]（模块规范：字体放项目根 font/）。"""
    d = os.path.join(project_root, 'font')
    out = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            p = os.path.join(d, f)
            if os.path.isfile(p) and f.lower().endswith(FONT_EXTS):
                out.append({'dir': 'font', 'name': f, 'sizeBytes': os.path.getsize(p)})
    return out


def prefs_font(project_root):
    """easyui prefs 里的 `font` 键 → {'path','key','file','existsInProject'}。

    ⚠️ 口径：`font/` 里的字体工具链会自动写进 `EasyUI.cfg`（规范做法），prefs 的 font 键属冗余；
但**prefs 指向的文件不存在**仍是真问题（IDE 侧/easyui 会去找它）→ 必须报出来。
    """
    p = os.path.join(project_root, PREFS_REL)
    out = {'path': p, 'exists': os.path.isfile(p), 'key': '', 'file': '',
           'existsInProject': False}
    text = _read(p) if out['exists'] else None
    if not text:
        return out
    m = re.search(r'"font"\s*\\?\s*:\s*"([^"]*)"', text)      # 兼容 `"font"\:"..."`（真格式）
    if not m:
        return out
    out['key'] = m.group(1)
    out['file'] = os.path.basename(m.group(1).replace('\\', '/'))
    out['existsInProject'] = bool(out['file']) and any(
        f['name'] == out['file'] for f in project_fonts(project_root))
    return out


def _project_scan(project_root, dfc):
    """无设备分支：工程侧 self-scan（判定仍走 device_font_check.judge 的同一套阈值）。"""
    fonts = project_fonts(project_root)
    v = dfc.judge({'fonts': fonts})             # ← 复用设备的判定规则（阈值单一来源）
    prefs = prefs_font(project_root)
    dangling = bool(prefs['key']) and not prefs['existsInProject']
    verdict = v['verdict']
    if dangling:                                # prefs 指向的字体在工程里根本不存在
        verdict = 'prefs_font_missing'
    elif verdict == 'no_font':
        verdict = 'project_no_font'
    elif verdict == 'no_cjk':
        verdict = 'project_no_cjk'
    elif verdict == 'partial_cjk':
        verdict = 'project_partial_cjk'
    elif verdict == 'has_cjk':
        verdict = 'project_has_cjk'
    missing = bool(v['needFont'] or dangling)
    return {'mode': 'project', 'verdict': verdict, 'missingChinese': missing,
            'maxFontBytes': (v['biggest']['sizeBytes'] if v['biggest'] else 0),
            'maxFontKB': v['biggestKB'], 'deviceFonts': [], 'projectFonts': fonts,
            'prefs': prefs, 'advisedTier': 'common' if missing else (v['recommendTier'] or '')}


# ---------------- 设备侧扫描（有设备分支）----------------
def pick_device(device='', platform='', known_online=None):
    """选设备（**不猜**）：显式 device= > 唯一在线设备；多台/0 台都不擅自选。

    `known_online`：调用方（build_ui_flow）**已经探过**的设备列表（含 `[]` = 确实没有）→
直接用它，不再重复 `adb devices`（传 None 才自己探）。
返回 (serial, dev, warning)：serial='' 表示没选到（warning 里写明原因，空串=本来就没设备）。
    """
    if _adb is None:
        return '', {}, 'adb 子系统不可用（%s）→ 跳过设备侧字体扫描' % _ADB_ERR
    if known_online is None:
        try:
            pr = _adb.probe_devices()
        except Exception as e:
            return '', {}, '设备探测异常: %s: %s' % (type(e).__name__, e)
        online = list(pr.get('online') or [])
    else:
        online = list(known_online)
        if device:
            if ':' in str(device) and not any(d.get('serial') == str(device) for d in online):
                try:                             # 网络设备：给一次 adb connect 再探
                    ok, _txt = _adb.connect(device)
                    if ok:
                        pr = _adb.probe_devices()
                        online = list(pr.get('online') or [])
                except Exception as e:
                    return '', {}, 'adb connect %s 异常: %s: %s' % (device, type(e).__name__, e)
    if device:
        hit = [d for d in online if d.get('serial') == str(device)]
        if hit:
            return str(device), hit[0], ''
        return '', {}, ('指定设备 %r 不在 adb 在线列表（当前在线：%s）→ 跳过设备侧字体扫描'
                        % (device, [d.get('serial') for d in online] or '无'))
    if len(online) == 1:
        return (online[0].get('serial') or ''), online[0], ''
    if not online:
        return '', {}, ''
    return '', {}, ('%d 台设备在线，字体体检**不替你选机器**（要扫某台请传 device=\'<serial|IP>\'）'
                    % len(online))


def device_scan(serial, platform=''):
    """扫设备字体（复用 device_font_check.collect/judge）→ (status, error)。"""
    dfc, err = device_font_check()
    if dfc is None:
        return None, err
    adb = _adb.resolve_adb() if _adb is not None else 'adb'
    busybox = ''
    note = ''
    if _adb is not None:
        try:
            busybox = _adb.ensure_busybox(adb, serial, platform) or ''
        except Exception as e:
            note = 'busybox 推送异常（改用设备自带 ls）: %s: %s' % (type(e).__name__, e)
    if busybox:
        dfc.BUSYBOX_REMOTE = busybox
    else:
        note = note or '随仓 busybox 未就绪 → 用设备自带 ls -l 解析体积（可能取不到）'
    info = dfc.collect(adb, serial, bool(busybox))
    if not info['fonts']:
        # v0.27.87 实测补的诚实提醒：扫不到字体时**不要把「无字库」说得像板上真的没有**——
        # 设备自带 ls -l 拿不到体积或目录没读到，同样会得到一个空列表（详见 custom-font-config.md §0.2.2）。
        miss_note = ('设备侧字体目录**没解析出任何字体文件**——可能确实没字库，也可能是设备自带 '
                     'ls -l 取不到体积（busybox 未就绪）→ 本条「无字库」结论存疑，'
                     '建议重试或人工核对 /etc/font、/res/font')
        note = (note + '；') if note else ''
        note += miss_note
    v = dfc.judge(info)
    fonts = [{'dir': f['dir'], 'name': f['name'], 'sizeBytes': f['sizeBytes'],
              'sizeKB': round(f['sizeBytes'] / 1024.0, 1),
              'mtimeText': f.get('mtimeText') or ''} for f in info['fonts']]
    props = info.get('props') or {}
    return {'mode': 'device', 'device': serial,
            'deviceModel': props.get('ro.product.model') or '',
            'deviceFonts': sorted(fonts, key=lambda x: -x['sizeBytes']),
            'maxFontBytes': (v['biggest']['sizeBytes'] if v['biggest'] else 0),
            'maxFontKB': v['biggestKB'], 'verdict': v['verdict'],
            'missingChinese': bool(v['needFont']),
            'advisedTier': v['recommendTier'] or ('common' if v['needFont'] else ''),
            'thresholdKB': getattr(dfc, 'CJK_SIZE_MIN_KB', None),
            'scanNote': note}, ''


# ---------------- 硬判据（cmap 覆盖率）+ 缓存（v0.27.87）----------------
def probe_cache_path():
    """探针结论缓存位置：`~/.fsc/font-probe.json`（09-28 版 fun 的新家；没有则退回 `~/.fun/`）。

    `FLYTHINGS_FONT_CACHE` 可覆盖（测试/多用户隔离用）；空串 = 不用缓存（每次都拉）。
    """
    env = os.environ.get('FLYTHINGS_FONT_CACHE')
    if env is not None:
        return env
    home = os.path.expanduser('~')
    for _name in ('.fsc', '.fun'):
        d = os.path.join(home, _name)
        if os.path.isdir(d):
            return os.path.join(d, PROBE_CACHE_NAME)
    return os.path.join(home, '.fsc', PROBE_CACHE_NAME)


def probe_cache_key(serial, font, platform=''):
    """缓存键 = `serial + 目录/文件名 + 体积 + ls 时间文本`（与平台）。

为什么不直接拿 md5：算 md5 得先删拉（就没缓存意义了）。设备侧字体一变 ⇒ 体积或 ls 时间变。
拉回来后的 md5 仍会记进缓存条目（供人核对，不参与命中判定）。
    """
    parts = [str(serial or ''), str((font or {}).get('dir') or ''),
             str((font or {}).get('name') or ''),
             str((font or {}).get('sizeBytes') or 0),
             str((font or {}).get('mtimeText') or ''), str(platform or '')]
    return '|'.join(parts)


def _cache_read(path=None):
    """读缓存文件 → {'version','entries'}；读不到/坏了 → 空表（不报错、不静默丢结论）。"""
    p = path if path is not None else probe_cache_path()
    if not p or not os.path.isfile(p):
        return {'version': PROBE_CACHE_VERSION, 'entries': {}}
    text = _read(p)
    if not text:
        return {'version': PROBE_CACHE_VERSION, 'entries': {}}
    try:
        d = json.loads(text)
    except ValueError:
        return {'version': PROBE_CACHE_VERSION, 'entries': {}}
    if not isinstance(d, dict) or d.get('version') != PROBE_CACHE_VERSION:
        return {'version': PROBE_CACHE_VERSION, 'entries': {}}
    d.setdefault('entries', {})
    return d


def _cache_write(data, path=None):
    p = path if path is not None else probe_cache_path()
    if not p:
        return ''
    try:
        d = os.path.dirname(p)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with open(p, 'w', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=1))
        return p
    except OSError:
        return ''                     # 缓存写不了不是问题（不能因此中断体检）


def hard_probe(serial, fonts, platform='', dfc=None, use_cache=True, cache_path=None,
               adb=''):
    """**硬判据主入口**：挑设备上最大的字体 → 拉回 PC → cmap 覆盖率 → verdict。

字段（调用方直接合并进 fontCheck）：
      source='cmap' | 'size'，verdict='ok'|'low'|'missing'（cmap）或 None（size，保留体积判据），
      cmapCoverageGB2312L1（百分数，size 分支为 None）、cmapCoveredChars/TotalChars、
      checkedFont{path,name,sizeBytes,sizeKB,localMd5,mtime}、needFont、recommendedTier、
      cacheHit、reason（size 分支的原因）、warnings（本环节自己产生的问题，非静默）。
超限 / fontTools 不可用 / 拉取失败 / 解析失败 → source='size' + warnings 写明原因。
    """
    mod = dfc or device_font_check()[0]
    out = {'source': 'size', 'verdict': None, 'needFont': None, 'recommendedTier': None,
           'cmapCoverageGB2312L1': None, 'cmapCoveredChars': None, 'cmapTotalChars': None,
           'checkedFont': None, 'cacheHit': False, 'reason': '', 'warnings': [],
           'elapsedMs': 0, 'pulledBytes': 0, 'probeCache': ''}
    if mod is None:
        out['reason'] = 'device_font_check 不可用 → 无法做 cmap 硬判据'
        out['warnings'].append(out['reason'])
        return out
    flist = [f for f in (fonts or []) if f]
    if not flist:
        out['reason'] = '设备上一个字体文件都没有 → 无字体可探（保留体积判据的 no_font 结论）'
        return out
    biggest = sorted(flist, key=lambda f: -(int(f.get('sizeBytes') or 0)))[0]
    out['checkedFont'] = {'path': (biggest.get('dir') or '') + '/' + (biggest.get('name') or ''),
                          'name': biggest.get('name') or '',
                          'sizeBytes': int(biggest.get('sizeBytes') or 0),
                          'sizeKB': round((biggest.get('sizeBytes') or 0) / 1024.0, 1),
                          'mtime': biggest.get('mtimeText') or ''}
    # 拉取前的本地闸门（体积超限 / fontTools 不可用）—— 规则与文案都取自 device_font_check（单一来源）
    block = mod.pre_pull_block(out['checkedFont']['sizeBytes']) \
        if hasattr(mod, 'pre_pull_block') else ''
    if block:
        out['reason'] = block
        out['warnings'].append('cmap 硬判据不可用，已退回**体积判据**：%s（source="size"）'
                               % block)
        return out
    key = probe_cache_key(serial, biggest, platform)
    t0 = time.time()
    if use_cache:
        cache = _cache_read(cache_path)
        hit = (cache.get('entries') or {}).get(key)
        if hit and hit.get('source') == 'cmap':
            out.update({'source': 'cmap', 'verdict': hit.get('verdict'),
                        'needFont': bool(hit.get('needFont')),
                        'recommendedTier': hit.get('recommendedTier'),
                        'cmapCoverageGB2312L1': hit.get('cmapCoverageGB2312L1'),
                        'cmapCoveredChars': hit.get('cmapCoveredChars'),
                        'cmapTotalChars': hit.get('cmapTotalChars'),
                        'cacheHit': True, 'elapsedMs': int((time.time() - t0) * 1000),
                        'probeCache': cache_path or probe_cache_path(),
                        'probedAt': hit.get('probedAt')})
            out['checkedFont']['localMd5'] = hit.get('localMd5') or ''
            return out
    probe = mod.probe_device_font(adb or _adb_path(), serial, biggest)
    out['elapsedMs'] = int((time.time() - t0) * 1000)
    out['pulledBytes'] = int(probe.get('localBytes') or 0)
    out['reason'] = probe.get('reason') or ''
    if probe.get('source') == 'cmap':
        out.update({'source': 'cmap', 'verdict': probe.get('verdict'),
                    'needFont': bool(probe.get('needFont')),
                    'recommendedTier': probe.get('recommendTier'),
                    'cmapCoverageGB2312L1': probe.get('coveragePct'),
                    'cmapCoveredChars': probe.get('coveredChars'),
                    'cmapTotalChars': probe.get('totalChars')})
        out['checkedFont']['localMd5'] = probe.get('md5') or ''
        if use_cache:
            cache = _cache_read(cache_path)
            cache.setdefault('entries', {})[key] = {
                'source': 'cmap', 'verdict': probe.get('verdict'),
                'needFont': bool(probe.get('needFont')),
                'recommendedTier': probe.get('recommendTier'),
                'cmapCoverageGB2312L1': probe.get('coveragePct'),
                'cmapCoveredChars': probe.get('coveredChars'),
                'cmapTotalChars': probe.get('totalChars'),
                'localMd5': probe.get('md5') or '', 'localBytes': probe.get('localBytes'),
                'serial': serial, 'font': out['checkedFont']['path'],
                'probedAt': time.strftime('%Y-%m-%d %H:%M:%S'),
                'platform': platform or ''}
            out['probeCache'] = _cache_write(cache, cache_path)
    else:
        out['warnings'].append('cmap 硬判据不可用，已退回**体积判据**：%s（source="size"）'
                               % (out['reason'] or '原因未知'))
    return out


def _adb_path():
    """adb 可执行路径（adb 子系统不可用 → 空串，pull_font 会自己兜底找）。"""
    if _adb is None:
        return ''
    try:
        return _adb.resolve_adb() or ''
    except Exception:
        return ''


def recheck_after_deploy(serial, platform, project_root, delivered, dfc=None):
    """部署后复查（v0.27.87）：fun launch 成功后，回看「设备侧现在中文字库可用性 + 与工程是否一致」。

为什么**不**重算 cmap：字体是**资源/固件侧**的东西，`fun launch` 只推 app（`/tmp/lib`、`/tmp/ui`），
设备侧字库在 `pack_upgrade` 固化前不会变 —— 再拉一次只会白花一次传输。故这里只做轻量核验：设备字体清单（体积判据）+ 投递文件的名字/体积是否已在设备上 ⇒ 给「需固化才生效」的实话。
与已有 `staleOnDevice`（app 侧文件比对）凑成闭环：**app 陈旧**vs **字库待固化**分开报。
    """
    out = {'checked': False, 'consistent': None, 'deviceVerdict': '', 'deviceMaxFontKB': 0,
           'deviceFontNames': [], 'projectFont': (delivered or {}).get('file') or '',
           'projectFontSizeBytes': 0, 'note': '', 'warnings': []}
    mod = dfc or device_font_check()[0]
    if mod is None:
        out['note'] = 'device_font_check 不可用，未复查'
        return out
    files = [f for f in ((delivered or {}).get('files') or []) if f.startswith('font/')]
    name = files[0][len('font/'):] if files else ((delivered or {}).get('file') or '')
    if not name:
        out['note'] = '本次没有投递字体，无需复查'
        return out
    local = os.path.join(project_root, 'font', name)
    out['projectFont'] = name
    out['projectFontSizeBytes'] = os.path.getsize(local) if os.path.isfile(local) else 0
    scan, err = device_scan(serial, platform)
    if scan is None:
        out['note'] = '设备字体复查失败：%s' % err
        return out
    out.update({'checked': True, 'deviceVerdict': scan.get('verdict'),
                'deviceMaxFontKB': scan.get('maxFontKB'),
                'deviceFontNames': [f['name'] for f in (scan.get('deviceFonts') or [])]})
    same = [f for f in (scan.get('deviceFonts') or []) if f['name'] == name]
    out['consistent'] = bool(same and same[0]['sizeBytes'] == out['projectFontSizeBytes'])
    if out['consistent']:
        out['note'] = ('设备侧已有 %s（%s KB）且与工程投递的一致（名字+体积）= 固化已生效'
                       % (name, round(out['projectFontSizeBytes'] / 1024.0, 1)))
    else:
        out['note'] = ('设备侧当前字库 %s（最大 %s KB，判定=%s）：投递进的是**工程**，'
                       '`fun launch` 只推 app、不推 font/ ⇒ 需要 `fun pack_upgrade` 固化后设备才生效'
                       % ('、'.join(out['deviceFontNames']) or '无字体文件',
                          scan.get('maxFontKB'), scan.get('verdict')))
        out['warnings'].append(out['note'])
    return out


# ---------------- 投递（复用 device_font_check.apply_to_project）----------------
def deliver(project_root, tier, dfc):
    """把 tier 字体投进工程 `font/`（+ 改 prefs，+ 补 enable.font.location）→ delivered 字段。

投递动作本身复用 `device_font_check.apply_to_project`（不复制一套）；
本函数额外做两件让它**真的生效**的事，并如实回报「写入了哪些文件」：
      ① `.settings/...easyui.prefs` 的 font 键（apply_to_project 内做的，这里比对前后差异）
      ② `package.properties` 的 `enable.font.location=true`（规范流程第 2 步，缺了字体不进 EasyUI.cfg）
    """
    out = {'applied': False, 'tier': tier, 'file': dfc.TIERS.get(tier) or '',
           'files': [], 'reason': '', 'detail': ''}
    name = dfc.TIERS.get(tier)
    if not name:
        out['reason'] = '未知 font_tier=%r（可选 %s）' % (tier, sorted(dfc.TIERS))
        return out
    prefs = os.path.join(project_root, PREFS_REL)
    props = os.path.join(project_root, 'package.properties')
    prefs_before, props_before = _read(prefs), _read(props)
    ok, msg = dfc.apply_to_project(project_root, tier, name)
    out['applied'] = bool(ok)
    out['detail'] = msg
    if not ok:
        out['reason'] = msg
    dst = os.path.join(project_root, 'font', name)
    if os.path.isfile(dst):
        out['files'].append('font/' + name)
    if _read(prefs) != prefs_before:
        out['files'].append(PREFS_REL.replace('\\', '/'))
    # ② 启用工程内字库（缺这条：字体在 font/ 里也不进 EasyUI.cfg）
    if props_before is not None and 'enable.font.location' not in props_before:
        text = props_before
        if not text.endswith('\n'):
            text += '\n'
        _write(props, text + 'enable.font.location=true\n')
        out['files'].append('package.properties')
        out['detail'] = (out['detail'] or '') + '；另补 package.properties enable.font.location=true'
    elif props_before is None:
        out['propsNote'] = '工程无 package.properties → 未能补 enable.font.location=true'
    return out


# ---------------- 对外：字体前置体检 ----------------
def font_preflight(project_root, platform='', device='', font_check='auto',
                   font_tier='', apply=True, allow_device=True, known_online=None,
                   probe=True):
    """字体体检（构建/部署前置）→ 机读字段 + warnings。

    font_check='off' → {'enabled': False, ...}（零动作、零 step，调用方据此不加 step）；
    allow_device=False（如 with_launch=False 且未指定 device）→ 不碰 adb，只做工程侧 self-scan；
    known_online=<调用方已探到的在线设备> → 不再重复 adb devices（build_ui_flow 复用设备门）；
    probe=False → 不做 cmap 硬判据（只体积判据；默认 True —— 硬判据更准，且结论带缓存不重复拉）。
    """
    res = {'enabled': True, 'mode': '', 'missingChinese': False, 'maxFontBytes': 0,
           'advisedTier': '', 'delivered': {'applied': False, 'files': []},
           'deviceFonts': [], 'projectFonts': [], 'warnings': [], 'note': '',
           'deviceScanned': False, 'device': '', 'verdict': '', 'tier': '',
           # 硬判据字段（v0.27.87；未走设备分支时 source='size'，覆盖率 None）
           'source': 'size', 'cmapCoverageGB2312L1': None, 'checkedFont': None}
    if is_off(font_check):
        return {'enabled': False, 'mode': 'off', 'missingChinese': None, 'maxFontBytes': 0,
                'advisedTier': '', 'delivered': {'applied': False, 'files': []},
                'deviceFonts': [], 'projectFonts': [],
                'note': "font_check='off'：本次不做字体体检/投递（开关显式关闭）",
                'warnings': []}
    if not os.path.isdir(project_root):
        res['warnings'].append('字体体检跳过：项目目录不存在 %s' % project_root)
        res['enabled'] = False
        return res

    dfc, err = device_font_check()
    if dfc is None:                                  # 判定规则拿不到 → 明说，不猜
        res['enabled'] = False
        res['warnings'].append('字体体检不可用：%s' % err)
        return res

    res['thresholdKB'] = getattr(dfc, 'CJK_SIZE_MIN_KB', None)
    serial, dev, dwarn = ('', {}, '')
    if allow_device:
        serial, dev, dwarn = pick_device(device, platform, known_online=known_online)
    else:
        # 不是问题，只是「本次没往设备看」（不是 warning，免得正常路径刷噪音）
        res['deviceScanSkipped'] = 'with_launch=False 且未指定 device → 不探测设备，仅做工程侧检查'
    if dwarn:
        res['warnings'].append(dwarn)

    if serial:
        scan, serr = device_scan(serial, platform)
        if scan is None:
            res['warnings'].append('设备字体扫描失败：%s → 退化为工程侧检查' % serr)
        else:
            res.update({k: scan[k] for k in
                        ('mode', 'device', 'deviceFonts', 'maxFontBytes', 'maxFontKB',
                         'verdict', 'missingChinese', 'advisedTier', 'scanNote')})
            res['deviceScanned'] = True
            res['deviceModel'] = scan.get('deviceModel', '')
            if scan.get('scanNote'):
                res['warnings'].append('设备字体扫描：%s' % scan['scanNote'])
            # ★ 硬判据（v0.27.87）：拉最大字体回 PC 算 cmap 覆盖率 → 覆盖体积判据的结论；
            #超限/无 fontTools/拉取失败/解析失败 → source='size'，保留体积结论 + warnings 写清原因
            if probe:
                hp = hard_probe(serial, scan.get('deviceFonts') or [], platform, dfc=dfc)
                res['probe'] = {'source': hp['source'], 'cacheHit': hp['cacheHit'],
                                'reason': hp['reason'], 'elapsedMs': hp['elapsedMs'],
                                'pulledBytes': hp['pulledBytes'],
                                'probeCache': hp.get('probeCache') or probe_cache_path(),
                                'probedAt': hp.get('probedAt')}
                res['source'] = hp['source']
                res['checkedFont'] = hp['checkedFont']
                res['cmapCoverageGB2312L1'] = hp['cmapCoverageGB2312L1']
                res['cmapCoveredChars'] = hp['cmapCoveredChars']
                res['cmapTotalChars'] = hp['cmapTotalChars']
                res['cmapThresholds'] = {'okMinPct': getattr(dfc, 'CMAP_OK_MIN_PCT', None),
                                         'lowMinPct': getattr(dfc, 'CMAP_LOW_MIN_PCT', None),
                                         'maxProbeBytes': getattr(dfc, 'PROBE_MAX_BYTES', None)}
                for w in hp['warnings']:
                    res['warnings'].append(w)
                if hp['source'] == 'cmap':
                    res['verdict'] = hp['verdict']            # ok / low / missing
                    res['missingChinese'] = bool(hp['needFont'])
                    res['advisedTier'] = hp['recommendedTier'] or ''
    if not res['deviceScanned']:                      # 无设备 / 多台不猜 / 扫描失败 → 工程侧
        ps = _project_scan(project_root, dfc)
        res.update({'mode': ps['mode'], 'verdict': ps['verdict'],
                    'missingChinese': ps['missingChinese'],
                    'maxFontBytes': ps['maxFontBytes'], 'maxFontKB': ps['maxFontKB'],
                    'advisedTier': ps['advisedTier'],
                    'projectFonts': ps['projectFonts'], 'prefs': ps['prefs']})
        res['note'] = '未连设备，仅工程侧检查（prefs 的 font 指向 + 工程 font/ 是否有可用字体）'
        if ps['prefs']['key'] and not ps['prefs']['existsInProject']:
            res['warnings'].append(
                '工程的 easyui prefs 里 font="%s"，但 <%s> 里没有该文件 → 字体引用是断的'
                % (ps['prefs']['key'], 'font/'))

    # 投递档位：显式 font_tier 优先；否则按体检结论（缺中文 → 建议档；不缺 → 默认 common）
    res['tier'] = (font_tier if font_tier in dfc.TIERS
                   else (res['advisedTier'] if res['missingChinese'] else 'common'))
    res['tiers'] = {'common': '872KB 常用中文(默认)', 'full': '7.39MB 生僻字',
                    'multi': '10.5MB 多语言/日韩'}

    if res['missingChinese'] and apply:
        res['delivered'] = deliver(project_root, res['tier'], dfc)
        res['delivered']['file'] = dfc.TIERS.get(res['tier'], '')
        if res['deviceScanned']:
            if res.get('source') == 'cmap':
                where = ('设备最大字体 %s 的 GB2312 一级覆盖率 %s%%（≥%s%% 才算 ok）'
                         % ((res.get('checkedFont') or {}).get('name') or '?',
                            res.get('cmapCoverageGB2312L1'),
                            res.get('cmapThresholds', {}).get('okMinPct')))
            else:
                where = ('设备最大字体 %s KB（体积判据阈值 %s KB；%s）'
                         % (res.get('maxFontKB'), res.get('thresholdKB'),
                            res.get('probe', {}).get('reason') or 'cmap 硬判据未生效'))
        elif res['verdict'] == 'prefs_font_missing':
            where = '未连设备 + prefs 指向的字体在工程里不存在'
        elif res['verdict'] in ('project_no_font', 'project_no_cjk'):
            where = '未连设备，工程侧也没找到可用中文字库'
        else:
            where = '未连设备'
        if res['delivered']['applied']:
            res['warnings'].append(
                '缺中文字库（%s，判定=%s）→ 已自动投递 %s 档思源黑体：%s；'
                '需要生僻字换 full / 多语言换 multi（font_tier=）'
                % (where, res['verdict'], res['tier'],
                   '、'.join(res['delivered']['files']) or '（无文件变化）'))
        else:
            res['warnings'].append(
                '缺中文字库（%s，判定=%s），自动投递**未完成**：%s；手动修复：%s'
                % (where, res['verdict'], res['delivered']['reason'], repair_command(
                    project_root, res['tier'])))
    elif res['missingChinese']:
        res['warnings'].append('缺中文字库（判定=%s%s）但 apply=False（只报不投）；修复：%s'
                               % (res['verdict'],
                                  '，覆盖率 %s%%' % res.get('cmapCoverageGB2312L1')
                                  if res.get('source') == 'cmap' else '',
                                  repair_command(project_root, res['tier'])))
    elif res['verdict'] in ('partial_cjk', 'project_partial_cjk'):
        # 已有「常用字」级字库 = 推荐的 common 档 → **只作 info 不作 warning**（防默认档每次构建都刷噪音）
        res['info'] = ('字体 %s KB（%s）：默认档够用；有生僻字人名/地名换 full、多语言/日韩换 multi'
                       % (res.get('maxFontKB'), res['verdict']))
    if res.get('source') == 'cmap' and not res['missingChinese'] and res['deviceScanned']:
        res['info'] = ('设备中文字库可用：%s 的 GB2312 一级覆盖率 %s%%（阈值 ≥%s%%），无需投递'
                       % ((res.get('checkedFont') or {}).get('name') or '?',
                          res.get('cmapCoverageGB2312L1'),
                          res.get('cmapThresholds', {}).get('okMinPct')))
    return res


def repair_command(project_root, tier='common'):
    """一键修复命令（给人/AI 直接照抄）。"""
    rel = os.path.join('components', 'fonts', 'scripts', 'device_font_check.py').replace('\\', '/')
    return ('python %s --apply --project "%s" --tier %s' % (rel, project_root, tier or 'common'))


def font_tier_menu(project_root, dfc=None):
    """**选字库**：三档菜单 + 按本工程实际字集的推荐档 + 现工程档位 → dict。

    为什么有（2026-10-05）：字库决定只有两个口子 —— 「选档」（`font_tier=`）与「自己裁字库」。
    文档把裁剪写在处置第 1 位（`knowledge/devflow/device-deploy-budget.md` §3），实际它只该在
    **存储/内存异常**时用；日常缺中文投现成三档即可。本函数把「选档」摆上台面，让调用方
    （`flythings_check_project_deps` 的 `fontTiers` 字段）一次看到「能选什么 / 该选哪档 / 现在是什么」。

    单一真源（本函数**不抄第二份阈值或档位名**）：
      · 档位名/顺序/何时用 = `preflight_spec.json`（经 `preflight_loader`：`tier_order()` / `tier()`；
        取不到 → 退 `device_font_check.TIERS`，两处都取不到才报 error，不猜）；
      · 体积 = 字体文件**实际字节数**（`preflight_loader.tier_bytes()`，读不到回 None，不写死）；
      · 推荐档 = `preflight.pick_font_tier()`（扫工程 UI 文案的 CJK 字集 → 够用的最小档）；
      · 现工程档位 = 把工程 `font/` 里已投递的文件名**反查** `dfc.TIERS`（不硬编码文件名对照表）。

    返回体的 `recommend` 带 `nextAction`：推荐档 == 现档 → 无需动作；否则给
    `flythings_build_ui_flow(font_tier='X')` / 本 op `font_apply=True` 的**可执行下一步**；
    两者都没有 → 给 `repair_command()`（不再返回空的成功）。
    `subsetWhen` 写明「什么时候才该自己裁字库」（体积数字仍从真源文件读，不写死）。
    """
    if dfc is None:
        dfc, err = device_font_check()
        if dfc is None:
            return {'enabled': False, 'error': 'device_font_check 不可用: %s' % err}

    # ---- 档位菜单：顺序与元数据都从注册表读；注册表不可用才退组件实现 ----
    order, tiers, spec_err = [], {}, ''
    try:
        import preflight_loader as P                          # 与 preflight.py 同一份真源读取器
        order = list(P.tier_order())
        tiers = P.tiers()
    except Exception as e:                                    # noqa: BLE001
        spec_err = '%s: %s' % (type(e).__name__, e)
        order = list((dfc.TIERS or {}).keys())
        tiers = {k: {'file': v} for k, v in (dfc.TIERS or {}).items()}
    if not order:
        return {'enabled': False, 'error': '字库档位取不到（preflight_spec.json.font.tierOrder '
                                           '与 device_font_check.TIERS 都为空）'}
    try:
        import preflight as pf
    except Exception as e:                                    # noqa: BLE001
        pf = None
        spec_err = (spec_err + '；' if spec_err else '') + 'preflight 导入失败: %s' % e

    menu = []
    by_name = {}
    for pos, name in enumerate(order):
        t = dict(tiers.get(name) or {})
        fname = t.get('file') or (dfc.TIERS or {}).get(name) or ''
        raw = None
        if pf is not None:
            try:
                raw = pf.P.tier_bytes(name)                   # 字体文件实际字节（读不到 None）
            except Exception:                                 # noqa: BLE001
                raw = None
        if raw is None:
            try:
                raw = os.path.getsize(os.path.join(
                    os.path.dirname(DFC_PATH), '..', 'fonts', fname))
            except OSError:
                raw = None
        row = {'tier': name, 'file': fname, 'bytes': raw,
               'sizeKB': (round(raw / 1024.0, 1) if raw else None),
               'level': t.get('level') or '', 'when': t.get('when') or '',
               'pick': ("font_tier='%s'" % name),
               'command': ('flythings_build_ui_flow(font_tier=%r)' % name)}
        menu.append(row)
        by_name[name] = row

    # ---- 推荐档：扫工程实际字集选「够用的最小档」（唯一实现在 preflight）----
    rec = {'tier': '', 'why': '', 'evidence': '',
           'reason': 'preflight.pick_font_tier 不可用，未做推荐'}
    if pf is not None:
        try:
            rec = pf.pick_font_tier(project_root)
        except Exception as e:                                # noqa: BLE001
            rec = {'tier': '', 'why': '', 'evidence': '',
                   'reason': '推荐档计算失败: %s: %s' % (type(e).__name__, e)}

    # ---- 现工程档位：已投递文件名反查真源档位表（不硬编码文件名）----
    pfonts = project_fonts(project_root)
    name2tier = {}
    for _tn, _fn in (dfc.TIERS or {}).items():
        if _fn:
            name2tier[str(_fn).lower()] = _tn
    cur_tier, cur_files = '', []
    for f in pfonts:
        t2 = name2tier.get(str(f.get('name') or '').lower())
        if t2 and not cur_tier:
            cur_tier = t2
        cur_files.append(f.get('name'))
    current = {'tier': cur_tier, 'files': cur_files,
               'delivered': bool(cur_tier),
               'note': ('工程 font/ 下已投递 %s 档' % cur_tier if cur_tier
                        else ('工程 font/ 下有字体但不是三档之一' if cur_files
                              else '工程 font/ 下没有字体（尚未投递任何档）'))}

    # ---- 推荐档 vs 现档：给可执行下一步（不返回空的成功）----
    want = rec.get('tier') if isinstance(rec, dict) else ''
    if want == 'none':
        next_action = '工程文案 0 个汉字 → 不需要投字库（设备内置拉丁字库够用）'
    elif not want:
        next_action = ('推荐档算不出（见 recommend.reason）；可显式选档：'
                       + ' / '.join(r['command'] for r in menu))
    elif cur_tier == want:
        next_action = '已投递的档位与推荐档一致（%s）→ 无需动作' % want
    else:
        next_action = ('现工程档位 %s ≠ 推荐档 %s → 改用：%s（或本 op 传 font_apply=True；'
                       '命令行：%s）'
                       % (cur_tier or '未投递', want, by_name.get(want, {}).get('command') or want,
                          repair_command(project_root, want)))
    rec = dict(rec) if isinstance(rec, dict) else {}
    rec['matchesProject'] = bool(want and cur_tier == want)
    rec['nextAction'] = next_action

    # ---- 自己裁字库的口径（**事后口子**）：只有存储/内存异常才用 ----
    common_kb = (by_name.get('common') or {}).get('sizeKB')
    subset_when = ('**只在存储/内存异常时用**（设备 tmpfs 装不下现成档：一次 fun launch 要推 '
                   'libzkgui.so + font + ftu + EasyUI.cfg，字库是最大头）→ 先按现成档选型，'
                   '仍超预算才裁字库；日常缺中文请直接选档，不要一上来就裁')
    if common_kb:
        subset_when += '（如 common 档 %.1f KB → 裁剪后可到数十 KB）' % common_kb

    out = {'enabled': True, 'tierOrder': order, 'tiers': menu,
           'recommend': rec, 'current': current,
           'subset': {'tool': 'ui_tools/font_subset_by_project.py',
                      'when': subset_when,
                      'warning': '改完 UI 文案必须重跑：新增字不在字库里会**静默缺字**。'},
           'default': (dfc.TIERS and order[0]) or ''}
    if spec_err:
        out['specWarning'] = ('档位元数据部分降级（%s）—— 档位名/体积仍来自真源，'
                              '但 when/level 可能缺失' % spec_err)
    return out


def compact(status):
    """体检返回体里给 AI/客户看的精炼版（字段固定，防漂移）。"""
    if not status or not status.get('enabled'):
        return {'enabled': False, 'note': (status or {}).get('note', '')}
    out = {'enabled': True, 'mode': status.get('mode'),
           'missingChinese': status.get('missingChinese'),
           'maxFontBytes': status.get('maxFontBytes'),
           'maxFontKB': status.get('maxFontKB'),
           'advisedTier': status.get('advisedTier'),
           'tier': status.get('tier'),
           'delivered': status.get('delivered'),
           'deviceFonts': status.get('deviceFonts'),
           'verdict': status.get('verdict'),
           # 硬判据（v0.27.87）：source='cmap' 时覆盖率才有数；size = 退回体积判据
           'source': status.get('source', 'size'),
           'cmapCoverageGB2312L1': status.get('cmapCoverageGB2312L1'),
           'checkedFont': status.get('checkedFont')}
    if status.get('cmapThresholds'):
        out['cmapThresholds'] = status['cmapThresholds']
    if status.get('probe'):
        out['probe'] = status['probe']
    if status.get('cmapCoveredChars') is not None:
        out['cmapCoveredChars'] = status.get('cmapCoveredChars')
        out['cmapTotalChars'] = status.get('cmapTotalChars')
    if status.get('deviceScanSkipped'):
        out['deviceScanSkipped'] = status['deviceScanSkipped']
    if status.get('mode') == 'project':
        out['deviceFonts'] = []
        out['projectFonts'] = status.get('projectFonts')
        out['prefs'] = status.get('prefs')
        out['note'] = status.get('note')     # 「未连设备，仅工程侧检查」
    else:
        out['device'] = status.get('device')
        out['deviceModel'] = status.get('deviceModel', '')
    return out
