# -*- coding: utf-8 -*-
"""上机前体检的**判据实现**（域⑨ `preflight_spec.json` 的消费方）。

`preflight_loader` 只管"读规格"，本模块管"用规格做判断"。三项体检：

1. **分辨率**：设计分辨率（启动窗口）vs 面板分辨率（/dev/fb0）→ 三分支
   （屏 ≥ 设计 → 直接推 / 屏 < 设计 → 必须问用户 / 读不出设计 → 按面板重适配）
2. **字库**：设备内置字库 < 200KB 判不支持中文 → 按**工程实际用到的汉字集**匹配最小够用档
3. **体积**：`resources/` + 工程字体 + `libzkgui.so` 对比 /res 上限（默认 8MB）

设计原则（与全仓一致）：**判据只有一份**、**读数不确定就如实报冲突，不猜**、
**不静默降级**（读不到说读不到）。本模块不碰设备写入，落盘只发生在 `scale_project()`
（且只做等比换算，比例不同时**拒绝**改盘、只出 plan —— 那是重排布局，走 skill）。
"""

import io
import json
import os
import sys
import re

import preflight_loader as P

BASE = os.path.dirname(os.path.abspath(__file__))

# 汉字范围：扩展 A + 基本区 + 兼容区（覆盖项目文案里可能出现的全部 CJK 表意字）
_CJK_RE = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')
# 启动窗口：src/Main.cpp 的 onStartupApp 返回 "<name>Activity"
_STARTUP_RE = re.compile(r'onStartupApp\s*\([^)]*\)\s*\{(.*?)\}', re.S)
_RETURN_STR_RE = re.compile(r'return\s*"([^"]+)"')

# 从工程 json 里取"给人看的文案"的键（不是所有字符串都算 —— 路径/颜色值里的字符不算文案）
_TEXT_KEYS = ('text', 'caption', 'title', 'hint')
_FONT_EXTS = ('.ttf', '.ttc', '.otf')
_FONT_SIZE_KEYS = ('fontSize',)
_SIZE_SUBKEYS = ('left', 'top', 'width', 'height')


class PreflightError(RuntimeError):
    """判据无法给出结论时的显式错误（不返回半成品让人误读）。"""


# ────────────────────────────── 分辨率 ──────────────────────────────

def parse_res(text):
    """`'800x480'` / `'800 X 480'` → (800, 480)；解析不出回 (0, 0)。"""
    m = re.search(r'(\d+)\s*[xX*]\s*(\d+)', str(text or ''))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def fmt_res(w, h):
    return '%dx%d' % (w, h) if w and h else ''


def panel_label(probe):
    """面板读数的展示口径：`WxH` / `Wx?`（**高未判定**）/ `''`（没读到）。

    为什么要 `Wx?` 这种形态：`/dev/fb0` 的宽度（stride/bpp）一定读得到，而高度在有双缓冲的
    设备上要靠 `modes` 或硬件层目标才切得出来 —— 只有宽度时**不许**拿 `virtual_size` 的高凑数
    （那是页数 × 屏高），所以如实标个问号交给人核。
    """
    if not probe:
        return ''
    w, h = probe.get('width'), probe.get('height')
    if w and h:
        return fmt_res(w, h)
    return '%sx?' % w if w else ''


def startup_window(root):
    """**启动窗口**（= 用户指定的设计分辨率所在）→ {'activity','json','design','source','errors'}。

    判据（2026-10-03 定）：`src/Main.cpp` 的 `onStartupApp` 返回 `"<name>Activity"`，
    对应 `ui/<name>.json` 的**根窗口**尺寸 —— 这个尺寸就是用户指定的设计分辨率。
    读不到启动窗口名 → 退 `ui/main.json`（工程约定名）。
    """
    out = {'activity': '', 'json': '', 'design': '', 'source': '', 'errors': []}
    ui = os.path.join(root, 'ui')
    name = ''
    main_cpp = os.path.join(root, 'src', 'Main.cpp')
    if os.path.isfile(main_cpp):
        try:
            with io.open(main_cpp, encoding='utf-8', errors='replace') as fh:
                txt = fh.read()
        except OSError as e:
            txt = ''
            out['errors'].append('读 src/Main.cpp 失败：%s' % type(e).__name__)
        m = _STARTUP_RE.search(txt)
        if m:
            r = _RETURN_STR_RE.search(m.group(1))
            if r:
                name = r.group(1).strip()
                out['activity'] = name
            else:
                out['errors'].append('onStartupApp 里没找到 return "<名>"')
        else:
            out['errors'].append('src/Main.cpp 里没有 onStartupApp（旧骨架？）')
    else:
        out['errors'].append('没有 src/Main.cpp（不是 fun 工程骨架？）')

    cands = []
    if name:
        cands.append(name[:-len('Activity')] if name.endswith('Activity') else name)
    cands.append('main')
    for base in cands:
        fp = os.path.join(ui, base + '.json')
        if os.path.isfile(fp):
            out['json'] = fp
            break
    if out['json']:
        try:
            with io.open(out['json'], encoding='utf-8-sig') as fh:
                data = json.loads(fh.read())
        except Exception as e:
            out['errors'].append('读 %s 失败：%s: %s'
                                 % (os.path.basename(out['json']), type(e).__name__, e))
            data = None
        if isinstance(data, dict):
            r = data.get('resolution') or {}
            w, h = r.get('width'), r.get('height')
            src = 'resolution'
            if not (w and h):
                p = data.get('position') or {}
                w, h, src = p.get('width'), p.get('height'), 'position（resolution 缺）'
            if w and h:
                out['design'] = fmt_res(w, h)
                out['source'] = '%s 的根 %s' % (os.path.basename(out['json']), src)
            else:
                out['errors'].append('%s 里没有可用的 resolution/position'
                                     % os.path.basename(out['json']))
    else:
        out['errors'].append('ui/ 下找不到启动窗口 json（找过：%s）'
                             % '、'.join('%s.json' % c for c in cands))
    return out


def design_resolution(root):
    """设计分辨率 → (design, source)。启动窗口读不到时退工程 prefs（并注明是退路）。"""
    w = startup_window(root)
    if w['design']:
        return w['design'], w['source']
    try:                                    # 延迟 import：project_tools 是上游消费方，避免循环
        import project_tools
        r = project_tools.read_resolution(root)
    except Exception as e:
        return '', '退路也失败（%s: %s）' % (type(e).__name__, e)
    return (r or ''), ('退路：.settings/ui json（启动窗口读不到）' if r else '读不出')


def aspect_kind(design, panel):
    """两屏宽高比是"相同或接近"还是"不同" → 'same' | 'diff'（拿不到数回 ''）。"""
    dw, dh = parse_res(design)
    pw, ph = parse_res(panel)
    if not (dw and dh and pw and ph):
        return ''
    tol = P.aspect_tolerance_pct()
    a, b = float(dw) / dh, float(pw) / ph
    return 'same' if abs(a - b) / a * 100.0 <= tol else 'diff'


def resolution_decision(design, design_source, panel):
    """三分支判据（判据文本在 `preflight_spec.json.resolution.decisions`）→ dict。

    返回 {'id','action','level','why','design','panel','aspect','plan'}。
    `plan` 只在需要适配时有：{'sx','sy','kind'}。
    """
    out = {'id': '', 'action': '', 'level': '', 'why': '',
           'design': design or '', 'panel': panel or '', 'designSource': design_source or '',
           'aspect': '', 'plan': None}
    dw, dh = parse_res(design)
    pw, ph = parse_res(panel)
    if not (dw and dh):
        d = P.decision('design_unknown')
        out.update(id=d['id'], action=d['action'], level=d['level'], why=d['why'])
        if pw and ph:                        # 读不出设计 → 按面板重适配
            out['aspect'] = 'same'           # 无设计可比 → 视为"比例可对齐"（就是照面板改）
            out['plan'] = {'sx': 1.0, 'sy': 1.0, 'kind': 'same',
                           'note': '工程无设计分辨率 → 直接用面板分辨率 %s 作为目标'
                                   % fmt_res(pw, ph)}
        return out
    if not (pw and ph):
        m = re.match(r'^(\d+)\s*[xX]\s*\?', str(panel or ''))
        if m:
            out.update(id='panel_height_unknown', action='warn', level='warn',
                       why='面板宽度是 %s，**高度没能自动判定**（有双缓冲时 virtual_size 的'
                           '高是页数 × 屏高，不能当屏高）→ 请人工核对面板高度后再判是否要适配'
                           % m.group(1))
            return out
        out.update(id='panel_unknown', action='warn', level='warn',
                   why='设备面板分辨率读不出来（/dev/fb0 modes 与硬件层都没给）→ 无法比对，'
                       '先人工确认面板型号/分辨率')
        return out
    # 转屏（W/H 互换）算同一块屏 —— 角度由工程 EasyUI.cfg 的 rotateScreen 决定
    if (dw, dh) == (ph, pw):
        d = P.decision('screen_ge_design')
        out.update(id=d['id'] + '_rotated', action=d['action'], level=d['level'],
                   why='设计 %s 与面板 %s 互为转置（同一块屏，转屏角度由 rotateScreen 决定）'
                       % (design, panel), aspect=aspect_kind(design, panel))
        return out
    if dw <= pw and dh <= ph:
        d = P.decision('screen_ge_design')
        out.update(id=d['id'], action=d['action'], level=d['level'], why=d['why'],
                   aspect=aspect_kind(design, panel))
        return out
    d = P.decision('screen_lt_design')
    out.update(id=d['id'], action=d['action'], level=d['level'],
               why='%s（设计 %s，面板 %s）' % (d['why'], design, panel),
               aspect=aspect_kind(design, panel))
    out['plan'] = {'sx': float(pw) / dw, 'sy': float(ph) / dh,
                   'kind': aspect_kind(design, panel) or 'diff'}
    return out


def scale_plan(design, panel):
    """等比换算方案 → {'sx','sy','kind','allowed','rule'}。

    `allowed=False` = 比例不同，**不许**等比缩放（会变形）—— 这时只出方案，落盘要重排布局。
    工程读不出设计分辨率时不缩放控件盒（`sx=sy=1`），只把口径改成面板分辨率。
    """
    dw, dh = parse_res(design)
    pw, ph = parse_res(panel)
    if not (pw and ph):
        raise PreflightError('换算方案需要面板分辨率给得出宽高（拿到的是 %r）' % (panel,))
    if not (dw and dh):
        return {'sx': 1.0, 'sy': 1.0, 'kind': 'same', 'allowed': True,
                'rule': '工程无设计分辨率 → 只把口径（prefs / ui json / ftu）改成面板 %s，'
                        '控件盒按原坐标保留' % fmt_res(pw, ph), 'skill': '',
                'design': '', 'panel': fmt_res(pw, ph)}
    kind = aspect_kind(design, panel)
    rule = P.adapt_rule('sameAspect' if kind == 'same' else 'diffAspect')
    return {'sx': round(float(pw) / dw, 6), 'sy': round(float(ph) / dh, 6),
            'kind': kind, 'allowed': kind == 'same',
            'rule': rule.get('how') or '', 'skill': rule.get('skill') or '',
            'design': design, 'panel': fmt_res(pw, ph)}


# ───────────────────────── 控件盒等比换算（落盘）─────────────────────────

def _scale_node(node, sx, sy, stat, _depth=0):
    """递归换算一个节点的 position / iconPosition / fontSize（原地改）。

    ⚠️ ui json 的**控件是根节点的平铺键**（`textview__2` / `button__3`…），不是 `children` 数组
    （实测 demos/*/ui/*.json 全是这个形态；`children` 只在控件自己内嵌子件时出现）。
    所以这里遍历**所有 dict / list 值**，只跳过已当几何处理掉的 position/iconPosition，
    否则平铺的控件会被整体漏掉（只改分辨率不改控件 = 界面全部跑位）。
    """
    if not isinstance(node, dict):
        return
    for key in ('position', 'iconPosition'):
        pos = node.get(key)
        if isinstance(pos, dict):
            for k in _SIZE_SUBKEYS:
                if isinstance(pos.get(k), (int, float)) and not isinstance(pos.get(k), bool):
                    pos[k] = int(round(pos[k] * (sx if k in ('left', 'width') else sy)))
                    if k in ('width', 'height'):
                        pos[k] = max(1, pos[k])
            stat['boxes'] += 1
    for k in _FONT_SIZE_KEYS:
        if isinstance(node.get(k), (int, float)) and not isinstance(node.get(k), bool):
            node[k] = max(1, int(round(node[k] * sy)))
            stat['fonts'] += 1
    for k, v in node.items():
        if k in ('position', 'iconPosition'):
            continue
        if isinstance(v, dict):
            _scale_node(v, sx, sy, stat, _depth + 1)
        elif isinstance(v, list):
            for x in v:
                _scale_node(x, sx, sy, stat, _depth + 1)


def scale_project(root, design, panel, apply=True):
    """把工程布局**等比**换算到面板分辨率 → {'applied','files','plan','skipped'}。

    只处理"比例相同或接近"的情形（`scale_plan()['allowed']`）；比例不同必须重排布局，
    这里**拒绝改盘**并把 plan 交出去（`skipped` 写清原因）—— 悄悄做个等比缩放会把界面拉变形。
    """
    plan = scale_plan(design, panel)
    out = {'applied': False, 'plan': plan, 'files': [], 'boxes': 0, 'fonts': 0,
           'skipped': '', 'rule': plan['rule']}
    if not plan['allowed']:
        out['skipped'] = ('设计 %s 与面板 %s 比例不同（相对差 > %s%%）→ 等比缩放会变形，'
                          '必须重排布局：%s' % (design, panel, P.aspect_tolerance_pct(),
                                                plan.get('skill') or '见体检判据页'))
        return out
    ui = os.path.join(root, 'ui')
    if not os.path.isdir(ui):
        out['skipped'] = '没有 ui/ 目录'
        return out
    pw, ph = parse_res(panel)
    stat = {'boxes': 0, 'fonts': 0}
    for fn in sorted(os.listdir(ui)):
        if not fn.endswith('.json'):
            continue
        fp = os.path.join(ui, fn)
        try:
            with io.open(fp, encoding='utf-8-sig') as fh:
                data = json.loads(fh.read())
        except Exception as e:
            out['skipped'] = '读 %s 失败：%s: %s' % (fn, type(e).__name__, e)
            return out
        if not isinstance(data, dict):
            continue
        _scale_node(data, plan['sx'], plan['sy'], stat)
        data['resolution'] = {'width': pw, 'height': ph}
        pos = data.get('position') or {}
        pos['width'], pos['height'] = pw, ph
        pos.setdefault('left', 0)
        pos.setdefault('top', 0)
        data['position'] = pos
        if apply:
            try:
                with io.open(fp, 'w', encoding='utf-8') as fh:
                    fh.write(json.dumps(data, ensure_ascii=False, indent=2))
            except OSError as e:
                out['skipped'] = '写 %s 失败：%s' % (fn, type(e).__name__)
                return out
        out['files'].append(os.path.join('ui', fn).replace('\\', '/'))
    out['boxes'], out['fonts'] = stat['boxes'], stat['fonts']
    out['applied'] = bool(apply and out['files'])
    return out


# ────────────────────────────── 字库 ──────────────────────────────

def project_cjk(root):
    """工程文案里**实际用到的** CJK 字集 → {'chars','files','totalChars','l1','l2','outside'}。

    取数范围（只算"给人看的文案"，不算路径/颜色/ID）：
      `ui/*.json` 的 text/caption/title/hint（含嵌套 children）+ `tr/*.json` 的全部字符串值。
    分级用**编解码器**判（零依赖、可复核），三档与字库档位一一对应：
      `gb2312`（常用字，编得进 GB2312）→ common 档够用
      `gbk`（次常用/扩展 A，GB2312 编不进、GBK 编得进）→ 需要 full 档
      `beyond`（GBK 都没有，只有 GB18030 有）→ 需要 multi 档
    ⚠️ 这是**没有 fontTools 时的兜底判据**；有 fontTools 时按字体 cmap 逐字实测（更准）。
    """
    chars = set()
    files = []
    unreadable = []
    ui = os.path.join(root, 'ui')
    tr = os.path.join(root, 'tr')

    def _sip(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in _TEXT_KEYS and isinstance(v, str):
                    chars.update(_CJK_RE.findall(v))
                else:
                    _sip(v)
        elif isinstance(node, list):
            for x in node:
                _sip(x)

    for d in (ui, tr):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.json'):
                continue
            fp = os.path.join(d, fn)
            rel = os.path.relpath(fp, root).replace('\\', '/')
            try:
                with io.open(fp, encoding='utf-8-sig') as fh:
                    data = json.loads(fh.read())
            except (OSError, ValueError) as e:
                # 解析不了的文件不能被静默跳过：它可能带文案，漏了会让选档偏小 → 记进 unreadable
                unreadable.append('%s（%s: %s）' % (rel, type(e).__name__, e))
                continue
            # ui/ 只认文案键（路径/颜色/ID 里的字符不是文案）；tr/ 整份都是文案
            if d == ui:
                _sip(data)
            else:
                _sip_strings(data, chars)
            files.append(rel)
    gb2312 = gbk = beyond = 0
    for ch in chars:
        if _encodable(ch, 'gb2312'):
            gb2312 += 1
        elif _encodable(ch, 'gbk'):
            gbk += 1
        else:
            beyond += 1
    return {'chars': chars, 'files': files, 'totalChars': len(chars),
            'gb2312': gb2312, 'gbk': gbk, 'beyond': beyond, 'unreadable': unreadable}


def _encodable(ch, enc):
    try:
        ch.encode(enc)
    except UnicodeEncodeError:
        return False
    return True


def _sip_strings(node, chars):
    """把任意 json 里的字符串值里的 CJK 收进集合（tr/ 用：整份都是文案）。"""
    if isinstance(node, str):
        chars.update(_CJK_RE.findall(node))
    elif isinstance(node, dict):
        for v in node.values():
            _sip_strings(v, chars)
    elif isinstance(node, list):
        for v in node:
            _sip_strings(v, chars)


_CMAP_CACHE = {}


def _cmap_chars(font_path):
    """字体 cmap 覆盖的码位集合 → set（fontTools 不可用/读失败回 None —— 不猜）。"""
    if font_path in _CMAP_CACHE:
        return _CMAP_CACHE[font_path]
    got = None
    try:
        from fontTools.ttLib import TTFont
        f = TTFont(font_path, lazy=True)
        got = set()
        for t in f['cmap'].tables:
            got.update(t.cmap.keys())
        f.close()
    except Exception:
        got = None
    _CMAP_CACHE[font_path] = got
    return got


def pick_font_tier(root):
    """按工程实际用到的汉字集，选**够用的最小档** → {'tier','why','evidence','chars',...}。

    判据（`preflight_spec.json.font.levelMatch`）：从最小档起，谁的 cmap 覆盖得住就用谁。
    fontTools 可用时按**实际 cmap** 判（可复核）；不可用时退**编解码器分级**
    （全部 GB2312 一级 → common；二级及以内 → full；有扩展字 → multi），并在 `evidence` 写明
    是用哪种判的 —— 不退化成"默认 common"。
    """
    cj = project_cjk(root)
    out = {'tier': '', 'why': '', 'evidence': '', 'totalChars': cj['totalChars'],
           'gb2312': cj['gb2312'], 'gbk': cj['gbk'], 'beyond': cj['beyond'],
           'files': cj['files'], 'tierBytes': None,
           'unreadable': cj.get('unreadable') or []}
    if not cj['chars']:
        out['tier'] = 'none'
        out['why'] = '工程文案里 0 个汉字 → 不投递（设备内置拉丁字库够用）'
        out['evidence'] = P.level_match().get('noCjk') or ''
        return out
    for name in P.tier_order():
        path = P.tier_file(name)
        cov = _cmap_chars(path)
        if cov is None:
            break
        missing = [c for c in cj['chars'] if ord(c) not in cov]
        if not missing:
            out.update(tier=name, tierBytes=P.tier_bytes(name),
                       why='%s 的 cmap 覆盖了工程全部 %d 个汉字'
                           % (P.tier(name).get('file'), cj['totalChars']),
                       evidence='fontTools 读 cmap 实测（逐字比对，缺字 0）')
            return out
        out['evidence'] = ('%s 缺 %d 个字（如 %s）→ 升档'
                           % (name, len(missing), ''.join(sorted(missing)[:5])))
    # fontTools 不可用（或所有档都覆盖不住）→ 退编解码器分级，如实写明判据
    if cj['beyond']:
        tier = 'multi'
    elif cj['gbk']:
        tier = 'full'
    else:
        tier = 'common'
    out.update(tier=tier, tierBytes=P.tier_bytes(tier),
               why=('工程汉字 %d 个（GB2312 %d / 仅 GBK %d / 更外 %d）→ 按字形分级选 %s'
                    % (cj['totalChars'], cj['gb2312'], cj['gbk'], cj['beyond'], tier)),
               evidence=(out['evidence'] + '；' if out['evidence'] else '')
                        + 'fontTools 不可用或全部档均缺字 → 退**编解码器分级**判（判据见 '
                          'preflight_spec.json.font.levelMatch）')
    return out


def font_verdict(device_fonts, builtin_path=None):
    """设备内置字库判定 → {'path','found','sizeBytes','sizeKB','verdict','rule'}。

    `verdict`：`no_cjk`（< 200KB，不支持中文）/ `cjk_ok` / `not_found`（设备上没这个文件 ——
    不代表设备没中文，只说明这条判据给不出结论）/ `unknown`（拿不到体积）。
    """
    bf = P.builtin_font()
    path = builtin_path or bf.get('path') or ''
    min_kb = P.cjk_min_kb()
    out = {'path': path, 'found': False, 'sizeBytes': 0, 'sizeKB': 0.0,
           'verdict': 'not_found', 'minKB': min_kb, 'rule': bf.get('rule') or ''}
    for f in (device_fonts or []):
        full = '%s/%s' % ((f.get('dir') or '').rstrip('/'), f.get('name') or '')
        if full == path or (f.get('name') and path.endswith(f['name'])):
            out['found'] = True
            out['sizeBytes'] = int(f.get('sizeBytes') or 0)
            out['sizeKB'] = round(out['sizeBytes'] / 1024.0, 1)
            if not out['sizeBytes']:
                out['verdict'] = 'unknown'
            else:
                out['verdict'] = 'no_cjk' if out['sizeKB'] < min_kb else 'cjk_ok'
            break
    return out


# ────────────────────────────── 体积 ──────────────────────────────

def _tree_bytes(path, exts=None, unreadable=None):
    """目录总字节数。读不到大小的文件**不静默跳过**：记进 `unreadable`（少算 = 预算假绿）。"""
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d not in ('.git',)]
        for fn in filenames:
            if exts and not fn.lower().endswith(exts):
                continue
            fp = os.path.join(dirpath, fn)
            try:
                total += os.path.getsize(fp)
            except OSError as e:
                if unreadable is not None:
                    unreadable.append('%s（%s）'
                                      % (os.path.relpath(fp, os.path.dirname(path) or '.')
                                         .replace('\\', '/'), type(e).__name__))
                continue
    return total


def _build_dir_names():
    """构建产物目录名（**两代**）→ `(names, note)`；note 非空表示口径退化了，要如实上报。

    唯一真源 = `project_tools.BUILD_DIR_NAMES`（`('.fsc', '.fun')`，`.fsc` 优先）。
    ⚠️ 为什么必须两代都认：09-28 版 fun 起产物目录从 `.fun/<平台>/` 改名到 `.fsc/<平台>/`，
    `project_tools._find_build_artifact` / `_find_update_img` 早已两代都认，**本模块漏改**：
    只找 `.fun/` → **新工具链工程的 `libzkgui.so` 体积一律计 0** → `usedMB` 偏小、
    `level` 可能假绿（2026-10-03 定位）。同一处漏改还让字体 walk 只排 `.fun`，
    `.fsc/` 里的东西会被当成"工程内字体"重复计入。

    `project_tools` 在模块级 `import preflight`（它要用 resolution_decision），
    所以这里**只能函数内延迟导入**（模块级会成环）。导入失败**不静默**：退回两代硬编码口径，
    并把原因交给调用方写进 `warnings`。
    """
    try:
        import project_tools as _pt
        names = tuple(_pt.BUILD_DIR_NAMES or ())
        if names:
            return names, ''
        return ('.fsc', '.fun'), 'BUILD_DIR_NAMES 为空，体积口径已退回 .fsc/.fun 硬编码'
    except Exception as e:
        return ('.fsc', '.fun'), ('BUILD_DIR_NAMES 不可用（%s: %s），体积口径已退回 '
                                 '.fsc/.fun 硬编码（构建产物体积可能不准）'
                                 % (type(e).__name__, e))



def probe_res_partition(device=''):
    """实测连接设备的 `res` 分区容量（字节）。探不到返回 (None, 原因)。

    复用 `tools/set_boot_logo.py::parse_mtd`（它已是"设备在线时读 /proc/mtd 真实上限"的同一套实现），
    不另写解析器。规范优先级见 `preflight_spec.json` 的 `budget.limitPriority`。
    """
    try:
        import adb_tools as _at
        tools_dir = os.path.join(BASE, 'tools')
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        import set_boot_logo as _sbl                     # 复用其 parse_mtd（唯一实现）
    except Exception as e:                               # 依赖不可用 → 显式降级
        return None, '解析器不可用(%s: %s)' % (type(e).__name__, e)
    try:
        adb = _at.find_adb() if hasattr(_at, 'find_adb') else 'adb'
        out = _at.sh(adb, device, 'cat /proc/mtd')
    except Exception as e:
        return None, '设备读取失败(%s: %s)' % (type(e).__name__, e)
    mtd = _sbl.parse_mtd(out or '')
    if not mtd:
        return None, '设备无 /proc/mtd 或解析为空'
    # 名字归一后找 res：真机上可能是 'res'（V85X/Z20/Z21）；找不到就如实报
    for name, kb in mtd.items():
        if name.lower() == 'res':
            return int(kb) * 1024, 'device:/proc/mtd res'
    return None, '设备分区表里没有叫 res 的分区（有: %s）' % ', '.join(sorted(mtd))

def budget_usage(root, platform='', device=''):
    """体积预算 → {'usedBytes','limitBytes','pct','level','parts','excluded','warnings'}。

    计入（口径见 `preflight_spec.json.budget.parts`）：`resources/` 全量 + 工程内字体
    （`resources/` 之外的按绝对路径去重）+ 构建产物 `libzkgui.so`
    （**两代都认、`.fsc` 优先**：09-28 起 fun 把产物从 `.fun/<平台>/` 改到 `.fsc/<平台>/`，
    目录名唯一真源 = `project_tools.BUILD_DIR_NAMES`，见 `_build_dir_names()`）。
    `ui/*.ftu` 与 `tr/` **不计入**，但会附在 `excluded` 里供参考（它们是同一个 /res 的邻居）。
    """
    build_dirs, build_note = _build_dir_names()
    parts = []
    unreadable = []
    res_dir = os.path.join(root, 'resources')
    res_bytes = _tree_bytes(res_dir, unreadable=unreadable) if os.path.isdir(res_dir) else 0
    parts.append({'path': 'resources/', 'bytes': res_bytes, 'exists': os.path.isdir(res_dir)})
    # 工程内字体：resources/ 之外单独放的才算（放 resources/ 里的已在上一行计过）
    font_bytes = 0
    font_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in build_dirs and d not in ('.git', 'Release') and
                       os.path.abspath(os.path.join(dirpath, d)) != os.path.abspath(res_dir)]
        for fn in filenames:
            if not fn.lower().endswith(_FONT_EXTS):
                continue
            fp = os.path.join(dirpath, fn)
            try:
                font_bytes += os.path.getsize(fp)
            except OSError as e:
                # 体积算不出来的字体不许静默漏算（少算 = 预算体检假绿）→ 记下来上报
                unreadable.append('%s（%s）'
                                  % (os.path.relpath(fp, root).replace('\\', '/'),
                                     type(e).__name__))
                continue
            font_files.append(os.path.relpath(fp, root).replace('\\', '/'))
    parts.append({'path': '**/*.ttf|*.ttc（resources/ 之外）', 'bytes': font_bytes,
                  'files': font_files})
    lib_bytes, lib_path = 0, ''
    try:
        import platforms as _pl
        key = _pl.package_key(platform) if platform else ''
    except Exception:
        key = ''
    cands = []
    # 两代构建目录都找，`.fsc` 优先（与 project_tools._find_build_artifact 同口径）
    for bd in build_dirs:
        bd_abs = os.path.join(root, bd)
        if key and os.path.join(bd_abs, key, 'libzkgui.so') not in cands:
            cands.append(os.path.join(bd_abs, key, 'libzkgui.so'))
        if os.path.isdir(bd_abs):
            for d in sorted(os.listdir(bd_abs)):
                p = os.path.join(bd_abs, d, 'libzkgui.so')
                if p not in cands:
                    cands.append(p)
    for p in cands:
        if os.path.isfile(p):
            try:
                lib_bytes = os.path.getsize(p)
            except OSError:
                lib_bytes = 0
            lib_path = os.path.relpath(p, root).replace('\\', '/')
            break
    parts.append({'path': '.fsc|.fun/<平台>/libzkgui.so', 'bytes': lib_bytes, 'file': lib_path,
                  'buildDirs': list(build_dirs)})

    used = sum(p['bytes'] for p in parts)
    # 规范优先级：实测设备 res 分区 > perPlatform 静态值 > 缺省 limitMB
    _res_bytes, _res_why = (None, '未探测（未给 device）')
    if device:
        _res_bytes, _res_why = probe_res_partition(device)
    if _res_bytes:
        limit_mb = round(_res_bytes / 1048576.0, 2)
        _limit_src = _res_why
    else:
        limit_mb = P.budget_limit_mb(platform)
        _limit_src = ('perPlatform' if (P.load().get('budget', {}).get('perPlatform') or {}).get(platform)
                      else 'default') + ('（实测未取得：%s）' % _res_why if device else '')
    limit = int(limit_mb * 1024 * 1024)
    pct = (used / float(limit) * 100.0) if limit else 0.0
    near = P.budget_near_pct()
    level = 'over' if pct >= 100 else ('near' if pct >= near else 'ok')
    warnings = []
    if build_note:                      # 口径退化不许静默（少算 = 预算体检假绿）
        warnings.append(build_note)
    for lv in P.budget_levels():
        if lv.get('level') == level and lv.get('action') == 'warn':
            warnings.append('%s（用量 %.2f MB / 上限 %s MB = %.0f%%）'
                            % (lv.get('why'), used / 1048576.0, limit_mb, pct))
    ui_dir = os.path.join(root, 'ui')
    excluded = []
    if os.path.isdir(ui_dir):
        excluded.append({'path': 'ui/*.ftu', 'bytes': _tree_bytes(ui_dir, ('.ftu',))})
    tr_dir = os.path.join(root, 'tr')
    if os.path.isdir(tr_dir):
        excluded.append({'path': 'tr/', 'bytes': _tree_bytes(tr_dir)})
    return {'usedBytes': used, 'limitBytes': limit,
            'usedMB': round(used / 1048576.0, 2), 'limitMB': limit_mb,
        'limitSource': _limit_src,
            'pct': round(pct, 1), 'level': level, 'parts': parts,
            'excluded': excluded, 'warnings': warnings,
            'platform': platform or '', 'fontFiles': font_files,
            'unreadable': unreadable}


# ────────────────────────── 三项合成一次体检 ──────────────────────────

def check(root, serial='', platform='', device_fonts=None, panel=None, device_probes=None):
    """上机前体检（**只读，不改盘**，也不设备侧写入）→ 结构化结论。

    `serial` 为空 = 没设备：分辨率/字库的设备侧判据给不出结论（如实标 `unknown`），
    体积预算仍可算（纯工程侧）。
    返回 {'ok','verdict','checks':{resolution,font,budget},'warnings','actions','questions'}。
    """
    root = os.path.abspath(root)
    out = {'projectRoot': root, 'device': serial or '', 'platform': platform or '',
           'ok': False, 'verdict': 'unknown', 'checks': {},
           'warnings': [], 'actions': [], 'questions': []}
    if not os.path.isdir(root):
        raise PreflightError('工程目录不存在：%s' % root)

    # ① 分辨率
    if panel is None and serial and device_probes is not None:
        try:
            panel = device_probes.panel_resolution(serial)
        except Exception as e:
            panel = {'ok': False, 'errors': ['panel_resolution 异常: %s: %s'
                                             % (type(e).__name__, e)]}
    panel_res = panel_label(panel) or fmt_res((panel or {}).get('width'),
                                              (panel or {}).get('height'))
    win = startup_window(root)
    design, src = design_resolution(root)
    dec = resolution_decision(design, src, panel_res)
    rchk = {'design': design, 'designSource': src, 'startupActivity': win.get('activity'),
            'startupJson': os.path.basename(win.get('json') or ''),
            'panel': panel_res, 'panelSource': (panel or {}).get('source') or '',
            'panelRaw': (panel or {}).get('raw') or {},
            'decision': dec, 'plan': dec.get('plan'), 'aspect': dec.get('aspect')}
    for e in (win.get('errors') or []) + ((panel or {}).get('errors') or []):
        rchk.setdefault('notes', []).append(e)
    if dec['action'] == 'warn':
        if dec['id'].startswith('screen_lt'):
            out['questions'].append(
                '面板 %s **小于**设计 %s：超出的部分在屏上看不到。'
                '要（a）按面板重做布局，还是（b）保持设计、接受画面被裁？' % (panel_res, design))
        else:
            out['questions'].append('%s' % dec['why'])
    if dec['action'] == 'adapt_device':
        out['questions'].append(
            '工程读不出设计分辨率（启动窗口判定：%s）→ 默认按面板 %s 重适配布局，确认吗？'
            % ('；'.join(win.get('errors') or []) or '未知', panel_res or '（面板也未读到时先确认面板）'))
        if dec.get('plan'):
            out['actions'].append({'kind': 'adapt', 'plan': dec['plan']})
    if dec['action'] == 'push':
        rchk['note'] = '屏 ≥ 设计 → 直接推，UI 可完整显示'
    for c in ((panel or {}).get('conflicts') or []):
        out['warnings'].append('面板分辨率来源不一致：%s' % c)
    out['checks']['resolution'] = rchk

    # ② 字库
    fchk = {'deviceFontsScanned': device_fonts is not None, 'builtin': None,
            'tierMatch': None, 'warnings': []}
    if device_fonts is not None:
        fchk['builtin'] = font_verdict(device_fonts)
        b = fchk['builtin']
        if b['verdict'] == 'no_cjk':
            out['warnings'].append(
                '设备内置字库 %s 只有 %.1f KB（< %s KB）→ **判定为不支持中文**；'
                '需要往工程投递裁剪字库' % (b['path'], b['sizeKB'], b['minKB']))
    elif serial:
        fchk['warnings'].append('拿到设备但没做设备侧字库扫描（font_check=off？）')
    try:
        fchk['tierMatch'] = pick_font_tier(root)
    except Exception as e:
        fchk['warnings'].append('工程字库匹配失败：%s: %s' % (type(e).__name__, e))
    tm = fchk['tierMatch'] or {}
    for u in (tm.get('unreadable') or []):
        fchk['warnings'].append('工程文案文件读不了 → 字库选档可能偏小：%s' % u)
    if tm.get('tier') and tm['tier'] != 'none':
        out['actions'].append({'kind': 'font', 'tier': tm['tier'],
                               'when': '设备内置字库不支持中文或覆盖率不足时投递'})
    fchk['warnings'] = list(fchk.get('warnings') or [])
    out['checks']['font'] = fchk

    # ③ 体积
    # 2026-10-04 修：这里原来写 `device=device`，而 `check()` 的形参叫 `serial` → 每次体检都
    # NameError 被上层吞成「上机前体检异常（不阻断）」warning，**体积/分区判据整块没跑**
    # （实测：V85X 部署时 warnings 里只有这一条，device_preflight step 也从不出现）。
    bchk = budget_usage(root, platform, device=serial)
    out['checks']['budget'] = bchk
    for u in (bchk.get('unreadable') or []):
        out['warnings'].append('字体体积算不出来 → 预算可能少算：%s' % u)
    if bchk['level'] == 'over':
        out['warnings'].append(
            '打包体积 %.2f MB 已超 /res 上限 %s MB（%s）→ 可能打包文件大于 /res 分区大小，'
            '升级/固化会失败或被截断；先减资源或换分区方案'
            % (bchk['usedMB'], bchk['limitMB'], bchk['platform'] or '缺省口径'))
    elif bchk['level'] == 'near':
        out['warnings'].append(
            '打包体积 %.2f MB 已到 /res 上限的 %.0f%%（上限 %s MB）→ 再加资源要小心'
            % (bchk['usedMB'], bchk['pct'], bchk['limitMB']))

    # 汇总
    if out['questions']:
        out['verdict'] = 'needs_decision'
    elif out['warnings']:
        out['verdict'] = 'warn'
    elif dec['action'] == 'push':
        out['verdict'] = 'ok'
    out['ok'] = out['verdict'] == 'ok' and not out['warnings']
    return out


def compact(report):
    """体检结论 → 返回体里的一句话摘要（给 op 用，别把整份报告塞进常驻面）。"""
    r = report.get('checks', {}).get('resolution', {})
    f = report.get('checks', {}).get('font', {})
    b = report.get('checks', {}).get('budget', {})
    bf = (f.get('builtin') or {})
    tm = (f.get('tierMatch') or {})
    bits = ['分辨率 设计%s/面板%s→%s'
            % (r.get('design') or '?', r.get('panel') or '?',
               (r.get('decision') or {}).get('action') or '?')]
    if bf.get('verdict'):
        bits.append('内置字库 %s' % bf['verdict'])
    if tm.get('tier'):
        bits.append('工程字库档 %s' % tm['tier'])
    bits.append('体积 %.2f/%sMB(%s)' % (b.get('usedMB'), b.get('limitMB'), b.get('level')))
    return '%s｜%s' % (report.get('verdict'), '；'.join(bits))
