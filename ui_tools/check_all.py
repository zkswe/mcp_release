# -*- coding: utf-8 -*-
"""
通用一键全检（通用工具 v1，不随项目复制）：python tools/ui_tools/check_all.py <项目根目录>
依次执行：根节点 / 嵌套深度 / 特殊字符 / 图片引用 / 回调 / 指针 / 定时器表 / 括号 /
开发者修改检测（ftu 比 json 新>30s 自动同步）+ fui pack 成功。
全部 PASS 才允许交付。任何 FAIL 都会给出具体文件与原因。
第 15/16 项为 **WARN（需人工审批，不影响 PASS/FAIL）**：装饰件压在可触摸控件之上、
setTouchable(false) 未配套 setTouchPass(true)（沛哥 2026-09-10，见 knowledge/uicontrols/touch-events.md）。
WARN 分两类意图：#15 会先评估「可能故意遮挡」（modal / 容器遮罩 / 整屏 / 完全覆盖 → 本就有意，忽略），
其余才是「疑似误压」；WARN 永远只是给人工审批的清单，不自动修。
"""
import glob
import json
import os
import re
import subprocess
import sys
import shutil
import tempfile
import time as _t

BASE = os.path.dirname(os.path.abspath(__file__))
# fui.exe 优先用项目内（ui/fui.exe），否则 workspace/projects/fui.exe，否则 PATH
FUI = None
for cand in (
    os.path.join(BASE, '..', '..', 'projects', 'fui.exe'),
    'fui',
):
    if os.path.exists(cand):
        FUI = cand
        break
if not FUI:
    FUI = 'fui'

BLACKLIST = set('⌫℃■●‹－＋–…→★◆▶▷①')
failures = []
warnings = []

try:
    from PIL import Image as _Image
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


_CTRL_KEY_RE = re.compile(r'^([a-z]+)__\d+$')
# 层级矩阵实证（SampleUI 1024x600 + basedemo-new_z20_1024_600，86 json 无越界）：
# pagewindow/scrollwindow → 只装 window；window → 万能容器（可嵌 window 深嵌套，实证嵌 textview/button/
# edittext/listview/seekbar/window/qrcode/digitalclock/slidetext/slidewindow）；叶子无子键；数组子结构归属固定
_LEAF_CTRL = {'textview', 'button', 'edittext', 'seekbar', 'circlebar', 'checkbox', 'slidetext',
              'cameraview', 'painter', 'pointer', 'digitalclock', 'qrcode', 'videoview', 'imageanim'}
_ARR_OWNER = {'radiobuttons': 'radiogroup', 'items': 'slidewindow', 'infos': 'diagram', 'subItem': 'listview'}
# 结构容器：子内容只能走结构键（item/radiobuttons/items/infos），禁止直接平铺 __N 控件键
_STRUCT_ONLY = {'listview': 'item', 'radiogroup': 'radiobuttons', 'slidewindow': 'items', 'diagram': 'infos'}


def _layer_problems(d):
    """控件层级合法性检查：返回问题列表（空=合法）。"""
    problems = []

    def scan(node, path=''):
        if not isinstance(node, dict):
            return
        for k, v in node.items():
            if not isinstance(v, dict):
                continue
            m = _CTRL_KEY_RE.match(k)
            if not m:
                continue
            t = m.group(1)
            sub = [ck for ck in v if _CTRL_KEY_RE.match(ck)]
            if t in ('pagewindow', 'scrollwindow'):
                if not any(ck.startswith('window__') for ck in sub):
                    problems.append('%s.%s 缺 window 子内容（pagewindow/scrollwindow 必须嵌套 window）' % (path, k))
                elif any(not ck.startswith('window__') for ck in sub):
                    problems.append('%s.%s 含非 window 子键（pagewindow/scrollwindow 只装 window）' % (path, k))
            if t in _STRUCT_ONLY:
                # listview/radiogroup/slidewindow/diagram 子内容只能走结构键，平铺控件键非法
                if sub:
                    problems.append('%s.%s 平铺子控件键 %s（%s 子内容只能放 %s 内）'
                                    % (path, k, sub[:3], t, _STRUCT_ONLY[t]))
            if t in _LEAF_CTRL and sub:
                problems.append('%s.%s 叶子控件含子控件键 %s' % (path, k, sub[:3]))
            for ak, owner in _ARR_OWNER.items():
                if ak in v and t != owner:
                    problems.append('%s.%s 数组 %s 只能出现在 %s 内' % (path, k, ak, owner))
            scan(v, path + '/' + k)

    scan(d)
    return problems


SEEKBAR_PIC_FIELDS = ('progressPic', 'secondaryProgressPic', 'backgroundPic', 'thumbPic')

# ⚠️ 控件必写字段全集模板（沛哥 2026-09-08 定规 v2）
# 口径：以 projects/SampleUI-New/ui/1024x600（42 json、新 IDE 全量序列化）为准——
#   扫描每类型所有控件 100% 共有的字段 = 必选；值含默认(-1/0/false/字号16)也显式写，不做缺省省略（防版本漂移）。
# 补充口径（沛哥）：beepEnable 不强制（交互控件默认支持）；交互控件 touchable 显式 true（button/listview/seekbar 可拖/
#   qrcode/videoview/diagram/slidewindow/subitem），容器/纯显示显式 false（window/painter/cameraview）；qrcode 恒写 padding:10；
#   videoview 按 SampleUI。生成器产出必须全部满足；手写 json 缺键时按模板补默认值。
# ⚠️ 例外：条件字段 text/图片路径等按设计（无值可写空串/缺省）；SampleUI 无样例类型（pagewindow/scrollwindow/checkbox/
#   radiogroup/slidetext/imageanim）暂沿用 demo 基准或从宽。
CTRL_FIELD_TEMPLATES = {
    'textview':     ['id', 'caption', 'position', 'alignment', 'colorTab', 'fontSize', 'touchable'],
    'button':       ['id', 'caption', 'position', 'alignment', 'colorTab', 'picTab', 'text', 'touchable'],
    'window':       ['id', 'caption', 'position', 'backgroundColor', 'hideTimeOut', 'modal', 'touchable', 'visible'],
    'edittext':     ['id', 'caption', 'position', 'alignment', 'bgColorTab', 'bold', 'colorTab',
                     'fontSize', 'hintTextColor', 'text', 'textType'],
    'seekbar':      ['id', 'caption', 'position', 'backgroundColor', 'backgroundPic', 'defProgress', 'max',
                     'orientation', 'progressPic', 'thumb', 'touchable', 'visible'],
    'listview':     ['id', 'caption', 'position', 'autoRollback', 'backgroundColor', 'cols', 'cycleEnable',
                     'dragMaxDis', 'edgeEffect', 'hasScrollbar', 'rows', 'touchable', 'visible',
                     'orientation', 'colSpacing', 'rowSpacing', 'item'],
    'circlebar':    ['id', 'caption', 'position', 'backgroundColor', 'clockwise', 'max', 'maxAngle',
                     'progressPic', 'progressPicPos', 'startAngle', 'textColor', 'textSize', 'textType',
                     'thumb', 'touchRange', 'touchable', 'unit', 'visible'],
    'slidewindow':  ['id', 'caption', 'position', 'backgroundColor', 'cols', 'fontSize', 'iconSize', 'items',
                     'padding', 'rollSpeed', 'rows', 'touchable', 'visible'],
    'digitalclock': ['id', 'caption', 'position', 'backgroundColor', 'beat', 'clockColor', 'fontSize',
                     'format', 'touchable', 'visible'],
    'qrcode':       ['id', 'caption', 'position', 'backgroundColor', 'codeStr', 'touchable', 'visible', 'padding'],
    'videoview':    ['id', 'caption', 'position', 'backgroundColor', 'defaultVolume', 'loopPlayback',
                     'rotation', 'touchable', 'visible'],
    'cameraview':   ['id', 'caption', 'position', 'autoPreview', 'backgroundColor', 'cvbs', 'formatSize',
                     'mirror', 'touchable', 'visible'],
    'painter':      ['id', 'caption', 'position', 'backgroundColor', 'touchable', 'visible'],
    'pointer':      ['id', 'caption', 'position', 'animatable', 'backgroundColor', 'backgroundPic', 'clockwise',
                     'fixedPoint', 'pointerPic', 'pointerSize', 'rotateSpeed', 'rotationPoint', 'startAngle',
                     'touchable', 'visible'],
    'diagram':      ['id', 'caption', 'position', 'backgroundColor', 'infos', 'touchable', 'visible',
                     'xAxisRange', 'yAxisRange', 'region'],
    'pagewindow':   ['id', 'caption', 'position', 'dragMaxDis', 'orientation', 'edgeEffect', 'rollSpeed'],
    'scrollwindow': ['id', 'caption', 'position', 'dragMaxDis', 'orientation', 'edgeEffect'],
    'radiogroup':   ['id', 'caption', 'position', 'backgroundColor', 'touchable', 'visible', 'radiobuttons'],
    'radiobutton':  ['id', 'caption', 'position', 'alignment', 'checked', 'colorTab', 'bgColorTab',
                     'backgroundColor', 'bold', 'fontSize', 'italic', 'text', 'touchable', 'visible'],
    'checkbox':     ['id', 'caption', 'position', 'alignment', 'checked', 'colorTab', 'bgColorTab',
                     'backgroundColor', 'bold', 'fontSize', 'iconPosition', 'italic', 'text',
                     'touchable', 'textPosition', 'visible'],
    'imageanim':    ['id', 'caption', 'position', 'loopCount', 'playFile'],
    'slidetext':    ['id', 'caption', 'position', 'touchable'],
    # ---- 带子内容的子结构模板（SampleUI + basedemo-new_z20_1024_600 双源验证，2026-09-08）----
    # item.position 必写（沛哥）：行高 = lv高/rows - rowSpacing（html2json 已自动算）；iconPosition/textPosition 布局键条件写
    'listitem':     ['caption', 'alignment', 'backgroundColor', 'bgColorTab', 'bold', 'colorTab',
                     'fontSize', 'italic', 'longClickIntervalTime', 'longClickTimeOut', 'picTab',
                     'position', 'text', 'touchable', 'visible', 'subItem'],
    'subitem':      ['id', 'caption', 'position', 'alignment', 'backgroundColor', 'bgColorTab',
                     'bold', 'colorTab', 'fontFamily', 'fontSize', 'italic',
                     'longClickIntervalTime', 'longClickTimeOut', 'picTab', 'text',
                     'touchable', 'visible'],
    'wave':         ['caption', 'penColor', 'penWidth', 'step', 'style', 'eraseSpace',
                     'antialias', 'visible', 'xScale', 'yScale'],
    'slideitem':    ['colorTab', 'picTab', 'text'],
}
_CTRL_KEY_RE = re.compile(r'^([a-z]+)__\d+$')


def _all_controls(d, out=None):
    """递归产出全部控件 (key, value)（含 window 嵌套）。"""
    if out is None:
        out = []
    for k, v in d.items():
        if isinstance(v, dict) and '__' in k:
            out.append((k, v))
            _all_controls(v, out)
    return out


def _pic_path(root, ref):
    """json 引用 images/xxx.png → 真实文件路径（resources/images 或 ui/images）。"""
    if not ref:
        return None
    base = os.path.basename(ref)
    for d in ('resources', 'ui'):
        p = os.path.join(root, d, 'images', base)
        if os.path.isfile(p):
            return p
    return None


def _text_min_size(text, font_size, align):
    """FT-009 最小尺寸公式：中文/全角=1.0，英数括号=0.55，符号=0.6，ceil+10% 余量。"""
    if not text:
        return 0, 0
    import re as _re
    wsum = 0.0
    for ch in text:
        if ord(ch) > 0x2E7F:
            wsum += 1.0
        elif _re.match(r'[\w\d()\[\]{}]', ch):
            wsum += 0.55
        else:
            wsum += 0.6
    min_w = int(wsum * font_size * 1.1) + 16
    if align == 37:  # CENTER 补余量
        min_w += 8
    min_h = int(font_size * 1.25)
    return min_w, min_h


def _is_bad_char(c):
    """设备裁剪字库外的字符：黑名单特殊符号 + emoji 范围。"""
    if c in BLACKLIST:
        return True
    o = ord(c)
    return (0x1F000 <= o <= 0x1FAFF) or (0x2600 <= o <= 0x27BF) or \
        (0x2300 <= o <= 0x23FF) or (0x2190 <= o <= 0x21FF) or \
        (0x25A0 <= o <= 0x25FF) or (0x2460 <= o <= 0x24FF) or \
        (0x2100 <= o <= 0x214F) or (0x2B00 <= o <= 0x2BFF) or \
        o in (0xFE0F, 0x200D)


def log(ok, msg):
    print(('  [PASS] ' if ok else '  [FAIL] ') + msg)
    if not ok:
        failures.append(msg)


def warn(msg):
    """WARN：不参与 PASS/FAIL 判定，输出给用户审批（沛哥 2026-09-10）。"""
    print('  [WARN] ' + msg)
    warnings.append(msg)


def walk(d, out, depth=0):
    for k, v in d.items():
        if isinstance(v, dict) and '__' in k:
            out.append((depth, k, v.get('caption', '')))
            walk(v, out, depth + 1)


def _rect(v):
    p = v.get('position') or {}
    l, t, w, h = p.get('left'), p.get('top'), p.get('width'), p.get('height')
    if None in (l, t, w, h):
        return None
    return (l, t, l + w, t + h)


def _overlap(a, b, min_axis=4):
    """相交面积；任一轴重叠 < min_axis px 视为无效（手指/鼠标实际点不到 1px 条带，降噪）。"""
    x = min(a[2], b[2]) - max(a[0], b[0])
    y = min(a[3], b[3]) - max(a[1], b[1])
    if x < min_axis or y < min_axis:
        return 0
    return x * y


def _deco_blockers(d):
    """同层兄弟中「后定义（z 更高）且 touchable=false」的控件压住 touchable=true 的控件。

    对应 touch-events.md §1：touchable=false 不等于穿透，仍会吃掉下层触摸（下层拖不动/点不响应）。
    返回 [(装饰件键, 装饰件控件, 被压控件键, 被压控件, 重叠面积)]；仅统计双方 visible。
    （是否「故意遮挡」由 _deco_hint 单独评估，本函数只找几何上的遮挡关系。）
    """
    found = []

    def scan(node):
        kids = [(k, v) for k, v in node.items()
                if isinstance(v, dict) and _CTRL_KEY_RE.match(k)]
        for j in range(len(kids)):
            kj, vj = kids[j]
            if vj.get('touchable') is not False or vj.get('visible') is False:
                continue
            for i in range(j):
                ki, vi = kids[i]
                if vi.get('touchable') is not True or vi.get('visible') is False:
                    continue
                rj, ri = _rect(vj), _rect(vi)
                if not rj or not ri:
                    continue
                ov = _overlap(rj, ri)
                if ov > 0:
                    found.append((kj, vj, ki, vi, ov))
        for k, v in kids:
            scan(v)

    scan(d)
    return found


# 容器/画布类控件：压在可触摸控件上的常见形态是「遮罩层/蒙层」（而非装饰件误压）
_DECO_CONTAINER = {'window', 'painter', 'scrollwindow', 'pagewindow'}


def _deco_hint(deco_key, deco, covered, res=None):
    """评估遮挡是否可能「故意」——返回 (possibly_intentional, [线索...])。

    故意遮挡的常见形态（沛哥 2026-09-10 提醒）：弹窗/蒙层本来就该吃掉下层触摸，不是 bug。
    线索：modal 弹窗 / 遮挡件是容器类（常见遮罩）/ 几乎完全覆盖被压控件 / 遮挡件整屏尺寸。
    """
    t = deco_key.split('__')[0]
    hints = []
    if deco.get('modal'):
        hints.append('modal=true（弹窗拦截）')
    if t in _DECO_CONTAINER:
        hints.append('%s 容器（常见遮罩/蒙层）' % t)
    d, c = _rect(deco), _rect(covered)
    if d and c:
        ov = _overlap(d, c)
        carea = max(1, (c[2] - c[0]) * (c[3] - c[1]))
        ratio = ov / carea
        if ratio >= 0.9:
            hints.append('几乎完全覆盖被压控件（%.0f%%）' % (ratio * 100))
        if res and res[0] and res[1] and (d[2] - d[0]) >= res[0] and (d[3] - d[1]) >= res[1]:
            hints.append('遮挡件为整屏尺寸（全局遮罩）')
    return (bool(hints), hints)


def main(project_root):
    root = os.path.abspath(project_root)
    if not os.path.isdir(root):
        print(f'[X] 项目目录不存在: {root}')
        sys.exit(1)
    ui = os.path.join(root, 'ui')
    if not os.path.isdir(ui):
        print(f'[X] ui 目录不存在: {ui}')
        sys.exit(1)

    PAGES = sorted(['ui/' + os.path.basename(f) for f in glob.glob(os.path.join(ui, '*.json'))])
    LOGICS = sorted(['src/logic/' + os.path.basename(f)
                     for f in glob.glob(os.path.join(root, 'src', 'logic', '*.cc'))])
    if not PAGES:
        print('[X] ui/ 下没有 json 布局')
        sys.exit(1)
    if not LOGICS:
        print('[WARN] src/logic/ 下没有 logic.cc（纯 UI 交付可忽略；有交互则必须有）')

    print('== 1. 根节点（id:0 + position 全屏 + resolution 一致）==')
    for f in PAGES:
        d = json.load(open(os.path.join(root, f), encoding='utf-8'))
        ok = (d.get('id') == 0 and isinstance(d.get('position'), dict)
              and isinstance(d.get('resolution'), dict)
              and d['position'].get('left') == 0 and d['position'].get('top') == 0
              and d['position'].get('width') == d['resolution'].get('width')
              and d['position'].get('height') == d['resolution'].get('height'))
        log(ok, '%s 根节点' % f)

    print('== 2. 层级合法性（SampleUI+basedemo 双源矩阵实证，2026-09-08）==\n'
          '      pagewindow/scrollwindow 只装 window；叶子无子键；数组子结构归属固定）')
    for f in PAGES:
        d = json.load(open(os.path.join(root, f), encoding='utf-8'))
        problems = _layer_problems(d)
        log(not problems, '%s 层级 %s' % (f, '；'.join(problems[:6]) if problems else '合法'))

    print('== 3. 特殊字符（emoji/字库外字符）==')
    for f in PAGES:
        txt = open(os.path.join(root, f), encoding='utf-8').read()
        bad = sorted(set(c for c in txt if _is_bad_char(c)))
        log(not bad, '%s 特殊字符 %s' % (f, bad if bad else '无'))
    for f in LOGICS:
        txt = open(os.path.join(root, f), encoding='utf-8').read()
        bad = sorted(set(c for c in txt if _is_bad_char(c)))
        log(not bad, '%s 特殊字符 %s' % (f, bad if bad else '无'))

    print('== 4. 图片引用（json + logic.cc 引用的图片必须存在）==')
    refs = set()
    for f in PAGES + LOGICS:
        txt = open(os.path.join(root, f), encoding='utf-8').read()
        for m in re.finditer(r'"(images/[^"]+\.png)"', txt):
            refs.add(m.group(1))
    missing = []
    for r in refs:
        if '%s' in r:
            # %s 格式化前缀（如 images/dot_%s.png → images/dot_*）：去掉 %s 及其后的 .png
            prefix = r.split('%s')[0]
            if not glob.glob(os.path.join(root, 'resources', prefix + '*.png')):
                missing.append(r + '（前缀无匹配文件）')
            continue
        if not os.path.exists(os.path.join(root, 'resources', r)):
            missing.append(r)
    log(not missing, '图片引用 %s' % (missing if missing else '全部存在'))

    print('== 5. 回调核对（button → onButtonClick，edittext → onEditTextChanged）==')
    logic_map = {}
    for lf in LOGICS:
        base = os.path.splitext(os.path.basename(lf))[0].replace('Logic', '')
        logic_map[base] = lf
    for f in PAGES:
        d = json.load(open(os.path.join(root, f), encoding='utf-8'))
        caps = {}

        def by_caption(dd, out):
            for k, v in dd.items():
                if isinstance(v, dict) and '__' in k:
                    out[v.get('caption', '')] = v
                    by_caption(v, out)

        by_caption(d, caps)
        # 页面对应 logic：main.json → mainLogic.cc（模糊匹配）
        page_base = os.path.basename(f)[:-5]
        logic_file = None
        for lf in LOGICS:
            lb = os.path.basename(lf)
            if lb.startswith(page_base):
                logic_file = lf
                break
        if not logic_file:
            logic_file = logic_map.get(page_base) or (LOGICS[0] if LOGICS else None)
        if not logic_file:
            log(False, '%s 找不到对应 logic.cc' % f)
            continue
        code = open(os.path.join(root, logic_file), encoding='utf-8').read()

        def has_fn(name):
            return bool(re.search(name + r'\s*\(', code))

        bad = []
        for cap, v in caps.items():
            cid = v.get('id', 0)
            if 20000 <= cid < 30000 and not has_fn('onButtonClick_' + cap):
                bad.append('onButtonClick_' + cap)
            if 51000 <= cid < 52000 and not has_fn('onEditTextChanged_' + cap):
                bad.append('onEditTextChanged_' + cap)
        log(not bad, '%s 回调 %s' % (f, bad if bad else '齐全'))

    print('== 6. 指针核对（mXXXPtr 必须存在于 caption）==')
    for f in PAGES:
        d = json.load(open(os.path.join(root, f), encoding='utf-8'))
        ccaps = set()

        def collect(dd, out):
            for k, v in dd.items():
                if isinstance(v, dict) and '__' in k:
                    out.add(v.get('caption', ''))
                    collect(v, out)

        collect(d, ccaps)
        page_base = os.path.basename(f)[:-5]
        logic_file = None
        for lf in LOGICS:
            if os.path.basename(lf).startswith(page_base):
                logic_file = lf
                break
        if not logic_file:
            continue
        code = open(os.path.join(root, logic_file), encoding='utf-8').read()
        code2 = re.sub(r'//[^\n]*', '', code)
        used = set(re.findall(r'\bm([A-Za-z_]\w*)Ptr\b', code2))
        missing = [p for p in used if p not in ccaps]
        log(not missing, '%s 指针 %s' % (f, missing if missing else '全部有效'))

    print('== 7. REGISTER_ACTIVITY_TIMER_TAB（每个 logic.cc 必须包含）==')
    for f in LOGICS:
        txt = open(os.path.join(root, f), encoding='utf-8').read()
        log('REGISTER_ACTIVITY_TIMER_TAB' in txt, '%s 定时器表' % f)

    print('== 8. 括号平衡 ==')
    for f in LOGICS + ['src/Main.cpp']:
        p = os.path.join(root, f)
        if not os.path.isfile(p):
            continue
        code = open(p, encoding='utf-8').read()
        depth = 0
        in_str = False
        bad = 0
        for ch in code:
            if in_str:
                if ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth < 0:
                    bad += 1
                    depth = 0
        log(bad == 0 and depth == 0, '%s 括号 %s' % (f, '平衡' if bad == 0 and depth == 0 else '不平衡'))

    print('== 9. 开发者修改检测 + fui pack 成功生成 ftu ==')
    # ① ftu 比 json 新超 30 秒 → 判定开发者/IDE 直接改过 ftu → 先同步 json 再 pack
    for jf in PAGES:
        jp = os.path.join(root, jf)
        fp = os.path.join(ui, os.path.splitext(os.path.basename(jf))[0] + '.ftu')
        if os.path.isfile(fp) and os.path.isfile(jp):
            jt = os.path.getmtime(jp)
            ft = os.path.getmtime(fp)
            if ft > jt + 30:
                print('  [WARN] %s ftu 比 json 新 %.0f 秒（开发者/IDE 改过 ftu，自动以 ftu 同步 json）'
                      % (os.path.basename(jf), ft - jt))
                r = subprocess.run([FUI, 'unpack', ui], capture_output=True, text=True)
                if r.returncode == 0:
                    os.utime(jp, (ft, ft))  # json mtime 对齐 ftu（ftu 同步出的 json mtime 是 ftu 内嵌时间戳，需对齐避免误判）
                    print('  [PASS] %s ftu→json 同步 成功' % os.path.basename(jf))
                else:
                    log(False, '%s ftu→json 同步 失败' % os.path.basename(jf))
            else:
                log(True, '%s ftu 与 json 时间戳正常' % os.path.basename(jf))
    # ② pack 生成 ftu（json→ftu 已验证无损）
    r = subprocess.run([FUI, 'pack', ui], capture_output=True, text=True)
    if r.returncode != 0:
        log(False, 'fui pack 失败: %s' % ((r.stderr or r.stdout or '')[-200:]))
    else:
        for jf in PAGES:
            ftu = os.path.join(ui, os.path.splitext(os.path.basename(jf))[0] + '.ftu')
            log(os.path.isfile(ftu), '%s pack 成功 → %s' % (os.path.basename(jf), os.path.basename(ftu)))

    print('== 10. SeekBar 禁用 9-patch（ZKSeekBar 不解析 marker，会显示黑框）==')
    for f in PAGES:
        d = json.load(open(os.path.join(root, f), encoding='utf-8'))
        bad = []
        for k, v in _all_controls(d):
            if not k.startswith('seekbar__'):
                continue
            for fld in SEEKBAR_PIC_FIELDS:
                pv = v.get(fld, '')
                if isinstance(pv, str) and pv.lower().endswith('.9.png'):
                    bad.append('%s.%s 用了 %s' % (k, fld, pv))
        log(not bad, '%s SeekBar 9-patch %s' % (f, '；'.join(bad) if bad else '无'))

    print('== 11. 图片尺寸必须与控件 position 严格相等（FlyThings 不缩放普通 PNG）==')
    if not _HAS_PIL:
        log(True, '无 PIL，跳过图片尺寸核对（仅检查引用存在性）')
    for f in PAGES:
        d = json.load(open(os.path.join(root, f), encoding='utf-8'))
        bad = []
        for k, v in _all_controls(d):
            pos = v.get('position') or {}
            pw, ph = pos.get('width'), pos.get('height')
            if not pw or not ph:
                continue
            refs = []
            for fld in SEEKBAR_PIC_FIELDS:
                pv = v.get(fld)
                if isinstance(pv, str):
                    refs.append((fld, pv))
            if isinstance(v.get('backgroundPic'), str):
                refs.append(('backgroundPic', v['backgroundPic']))
            pt_ = v.get('picTab') or {}
            for fld in ('pic0', 'pic1'):
                pv = pt_.get(fld)
                if isinstance(pv, str):
                    refs.append(('picTab.%s' % fld, pv))
            for fld, ref in refs:
                if ref.lower().endswith('.9.png'):
                    continue  # 9-patch 可拉伸，尺寸不要求等于 position
                p = _pic_path(root, ref)
                if not p:
                    continue  # 缺失已在第 4 项报
                try:
                    with _Image.open(p) as im:
                        w, h = im.size
                    if (w, h) != (pw, ph):
                        bad.append('%s.%s %s %dx%d != position %dx%d' % (k, fld, os.path.basename(ref), w, h, pw, ph))
                except Exception:
                    pass
        log(not bad, '%s 图片尺寸 %s' % (f, '；'.join(bad) if bad else '全部匹配'))

    print('== 12. INIT_UI_TIMERS 不被 FYX_BUILD 保护（fun 工具链宏是 FUN_BUILD）==')
    for f in LOGICS:
        code = open(os.path.join(root, f), encoding='utf-8').read()
        idx = code.find('INIT_UI_TIMERS')
        bad = False
        if idx >= 0:
            m = re.findall(r'#if(n?def|ndef)\s+(\w+)', code[:idx])
            if m and m[-1][1] == 'FYX_BUILD':
                bad = True
        log(not bad, '%s TIMER 宏保护' % f)

    print('== 13. TextView/Button 最小尺寸（防文本截断）==')
    for f in PAGES:
        d = json.load(open(os.path.join(root, f), encoding='utf-8'))
        bad = []
        for k, v in _all_controls(d):
            if not k.startswith(('textview__', 'button__')):
                continue
            text = str(v.get('text', ''))
            fs = v.get('fontSize') or 0
            pos = v.get('position') or {}
            if not text or not fs or not pos.get('width'):
                continue
            min_w, min_h = _text_min_size(text, fs, v.get('alignment', 0))
            if pos['width'] < min_w or pos['height'] < min_h:
                bad.append('%s(%s) 文本“%s”需 >= %dx%d，当前 %dx%d'
                           % (k, v.get('caption', ''), text[:8], min_w, min_h,
                              pos['width'], pos['height']))
        log(not bad, '%s 最小尺寸 %s' % (f, '；'.join(bad) if bad else '满足'))

    print('== 14. 控件字段全集（必写键齐全，沛哥 2026-09-08：字段全显式防版本不匹配）==')
    for f in PAGES:
        d = json.load(open(os.path.join(root, f), encoding='utf-8'))
        missing = []

        def chk(ctrl_key, c, tpl_key):
            for fld in CTRL_FIELD_TEMPLATES.get(tpl_key, []):
                if fld not in c:
                    missing.append('%s.%s' % (ctrl_key, fld))

        for k, v in _all_controls(d):
            m = _CTRL_KEY_RE.match(k)
            if m:
                chk(k, v, m.group(1))
            # 数组/嵌套子结构（SampleUI 1024x600 子结构 100% 键）：
            #   radiogroup.radiobuttons / listview.item+subItem / diagram.infos / slidewindow.items
            if k.startswith('radiogroup__'):
                for rb in v.get('radiobuttons') or []:
                    chk(k + '.rb', rb, 'radiobutton')
            if k.startswith('listview__'):
                item = v.get('item')
                if isinstance(item, dict):
                    chk(k + '.item', item, 'listitem')
                    for si in item.get('subItem') or []:
                        chk(k + '.sub', si, 'subitem')
            if k.startswith('diagram__'):
                for w in v.get('infos') or []:
                    if isinstance(w, dict):
                        chk(k + '.wave', w, 'wave')
            if k.startswith('slidewindow__'):
                for it in v.get('items') or []:
                    if isinstance(it, dict):
                        chk(k + '.item', it, 'slideitem')
        log(not missing, '%s 字段全集 %s' % (f, '；'.join(missing[:15]) if missing else '齐全'))

    print('== 15. 装饰件遮挡可触摸控件（WARN 需人工审批；含「可能故意遮挡」评估）==\n'
          '      口径：同层后定义（z 更高）且 touchable=false 的控件压在 touchable=true 控件之上。\n'
          '      两类可能：① 误压（装饰件/布局失误）→ 需运行期 setTouchPass(true)；\n'
          '      ② 故意遮挡（蒙层/禁用态/防盗点：modal 弹窗、容器遮罩、整屏遮罩、完全覆盖）→ 本就有意，忽略。')
    for f in PAGES:
        d = json.load(open(os.path.join(root, f), encoding='utf-8'))
        found = _deco_blockers(d)
        if not found:
            print('  [PASS] %s 无装饰件遮挡' % f)
            continue
        _r = d.get('resolution') or {}
        res = (_r.get('width'), _r.get('height')) if _r.get('width') else None
        for kj, vj, ki, vi, ov in found[:8]:
            kdcap = vj.get('caption') or ''
            kcap = vi.get('caption') or ki
            ppt = 'm%sPtr' % kdcap if kdcap else kj
            c = _rect(vi)
            ratio = 100.0 * ov / max(1, (c[2] - c[0]) * (c[3] - c[1])) if c else 0
            detail = ('%s 装饰件 %s(%s) 压在 %s 之上（重叠 %dpx2 = 被压控件的 %.0f%%，touchable=false）'
                      % (f, kj, kdcap or '-', kcap, ov, ratio))
            probably, hints = _deco_hint(kj, vj, vi, res)
            if probably:
                warn('%s [可能有意遮挡：%s] → 若确认是故意挡（禁用态/蒙层/防盗点）忽略本条；'
                     '若确需下层可交互，再补 %s->setTouchable(false); %s->setTouchPass(true);'
                     % (detail, '、'.join(hints), ppt, ppt))
            else:
                warn('%s [疑似误压] → 修复：onUI_init 中 %s->setTouchable(false); %s->setTouchPass(true);'
                     '（否则下层拖不动/点不响应，touch-events.md 1）' % (detail, ppt, ppt))
        if len(found) > 8:
            warn('%s 另有 %d 处同类遮挡，未逐条列出' % (f, len(found) - 8))

    print('== 16. 代码层 setTouchable(false) 是否配套 setTouchPass(true)（WARN）==')
    for f in LOGICS:
        code2 = re.sub(r'//[^\n]*', '', open(os.path.join(root, f), encoding='utf-8').read())
        hits = set(re.findall(r'([A-Za-z_]\w*)\s*->\s*setTouchable\s*\(\s*false\s*\)', code2))
        miss = [v for v in sorted(hits)
                if not re.search(re.escape(v) + r'\s*->\s*setTouchPass\s*\(\s*true\s*\)', code2)]
        if miss:
            warn('%s 有 setTouchable(false) 但未见同对象 setTouchPass(true)：%s → 修复：在该控件设置处补 %s'
                 % (f, '、'.join(miss), ' ；'.join('%s->setTouchPass(true);' % v for v in miss)))
        else:
            print('  [PASS] %s 触摸穿透配套' % f)

    print()
    if warnings:
        print('[!] %d 条 WARN 需人工审批（不影响 PASS/FAIL；逐条判断是「误压」还是「故意遮挡」，'
              '故意遮挡可忽略；需交互则补 setTouchPass(true) 或调整层叠顺序）：' % len(warnings))
        for w in warnings:
            print('   -', w)
    if failures:
        print('[X] %d 项 FAIL，修复后再交付：' % len(failures))
        for f in failures:
            print('   -', f)
        sys.exit(1)
    else:
        print('[OK] 全部 PASS，可以交付。')
        sys.exit(0)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        print('用法: python tools/ui_tools/check_all.py <项目根目录>')
        sys.exit(1)
    main(sys.argv[1])
