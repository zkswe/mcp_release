# -*- coding: utf-8 -*-
"""font_tools.py —— 字体自动扫描接线（设备侧优先，退化到工程侧）+ 缺中文自动投递。

为什么有（钟工 2026-09-17「现在做」）：
  `components/fonts/scripts/device_font_check.py` 早就实现了「扫设备字体 + 缺中文投递思源黑体」，
  但**没有任何 op 包它、也没接进 build/deploy 流程** → 等于没做：客户撞到「界面汉字全变方块」
  时才知道要手动跑脚本。本模块把这一步接成**自动动作**（与 build_ui_flow 的依赖/install 体检同一套思路）。

单一事实来源（不许两套判定规则）：
  判定阈值 / 字体目录 / 三版字体清单 / 投递动作（copy→font/ + 改 easyui prefs）
  **全部 import `device_font_check`**（`judge()` / `TIERS` / `collect()` / `apply_to_project()`）；
  本模块只负责接线：设备探测（`adb_tools.resolve_adb()` / `probe_devices()` / `ensure_busybox()`）
  → 判定 → 需要就投递 → 组织成体检字段（missingChinese / maxFontBytes / advisedTier / delivered /
  deviceFonts），失败一律进 warnings，**不新增静默 except**。

两条分支：
  ① **有设备**：扫 `/etc/font`、`/res/font`、`/system/font`、`/usr/share/fonts` 里字体体积，
     判定缺中文（无字体 / 最大 < 200 KB）→ 默认投递 `common`（872 KB）进工程 `font/`；
  ② **无设备**：退化为工程侧 self-scan（prefs 的 `font` 指向的文件在不在工程 `font/`；
     工程 `font/` 里有没有可用字体）→ 缺就同样投递，并在 `note` 写清「未连设备，仅工程侧检查」。

开关：`font_check='auto'`（默认）/ `'off'`（完全不碰字体，零 step）；`font_tier='common'|'full'|'multi'`。
  默认 common；要生僻字换 full；多语言/日韩换 multi；**只有要更小体积/自定义字符集才需要自己裁字库**。
"""
import importlib.util
import os
import re
import sys

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
    v = dfc.judge(info)
    fonts = [{'dir': f['dir'], 'name': f['name'], 'sizeBytes': f['sizeBytes'],
              'sizeKB': round(f['sizeBytes'] / 1024.0, 1)} for f in info['fonts']]
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
                   font_tier='', apply=True, allow_device=True, known_online=None):
    """字体体检（构建/部署前置）→ 机读字段 + warnings。

    font_check='off' → {'enabled': False, ...}（零动作、零 step，调用方据此不加 step）；
    allow_device=False（如 with_launch=False 且未指定 device）→ 不碰 adb，只做工程侧 self-scan；
    known_online=<调用方已探到的在线设备> → 不再重复 adb devices（build_ui_flow 复用设备门）。
    """
    res = {'enabled': True, 'mode': '', 'missingChinese': False, 'maxFontBytes': 0,
           'advisedTier': '', 'delivered': {'applied': False, 'files': []},
           'deviceFonts': [], 'projectFonts': [], 'warnings': [], 'note': '',
           'deviceScanned': False, 'device': '', 'verdict': '', 'tier': ''}
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
            where = ('设备最大字体 %s KB（阈值 %s KB）'
                     % (res.get('maxFontKB'), res.get('thresholdKB')))
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
        res['warnings'].append('缺中文字库（判定=%s）但 apply=False（只报不投）；修复：%s'
                               % (res['verdict'], repair_command(project_root, res['tier'])))
    elif res['verdict'] in ('partial_cjk', 'project_partial_cjk'):
        # 已有「常用字」级字库 = 推荐的 common 档 → **只作 info 不作 warning**（防默认档每次构建都刷噪音）
        res['info'] = ('字体 %s KB（%s）：默认档够用；有生僻字人名/地名换 full、多语言/日韩换 multi'
                       % (res.get('maxFontKB'), res['verdict']))
    return res


def repair_command(project_root, tier='common'):
    """一键修复命令（给人/AI 直接照抄）。"""
    rel = os.path.join('components', 'fonts', 'scripts', 'device_font_check.py').replace('\\', '/')
    return ('python %s --apply --project "%s" --tier %s' % (rel, project_root, tier or 'common'))


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
           'verdict': status.get('verdict')}
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
