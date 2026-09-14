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
第 18 项 = **设计令牌漂移检测**（沛哥 2026-09-12）：DESIGN.md 是冻结的视觉真相，json 里的颜色/字号
应当来自令牌；出现令牌外的值 = 漂移。无 DESIGN.md 或令牌表未填全 → NOTE 跳过（不 FAIL，兼容存量工程）。
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
    """json 引用 → 真实文件路径。

    先按 ref 原样相对 resources 找（支持 audio/xxx.png 这类带子目录的引用，
    ui-layout-verify.md §图片引用），再退化到按 basename 在 resources/images 或
    ui/images 里找（历史作品常只写 images/xxx.png）。
    """
    if not ref:
        return None
    exact = os.path.join(root, 'resources', ref.replace('/', os.sep))
    if os.path.isfile(exact):
        return exact
    base = os.path.basename(ref)
    for d in ('resources', 'ui'):
        p = os.path.join(root, d, 'images', base)
        if os.path.isfile(p):
            return p
    return None


def _ui_pages(root):
    """ui 布局 json 清单：同时支持两种真实工程布局 ui/*.json 与 ui/<分辨率>/*.json。

    为什么两种都收：FlyThings 工程布局不一致——扁平 ui/main.json 与分层
    ui/1024x600/main.json 都常见（基准工程 SampleUI-New 就是分层 42 个）。
    原先只 glob 扁平一层，导致分层工程「0 页却报 ok」= **静默假阴性**
    （v0.27.33 实测：SampleUI-New / ShowcaseAlbum-F133 / WebViewDemo 三个真实工程
    全部 pages=0 且 ok=true），产物核对形同虚设。
    返回按相对路径排序的绝对路径列表（只下探一层分辨率目录，不再无限递归）。
    """
    ui = os.path.join(root, 'ui')
    found = set(glob.glob(os.path.join(ui, '*.json')))
    for sub in sorted(glob.glob(os.path.join(ui, '*'))):
        if os.path.isdir(sub):
            found.update(glob.glob(os.path.join(sub, '*.json')))
    return sorted(found)


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


# ---------------- 资源产物核对（json 声明 → 文件存在 + PNG 尺寸 == 控件 position）----------------
# 「产物 vs 声明」机器化（原为 temp/verify_demo_assets.py 人肉脚本，v0.27.32 固化）：
# 单一实现，check_all #17 与 MCP op flythings_verify_assets 共用，禁止再各写一份。
_PIC_REF_FIELDS = ('backgroundPic', 'progressPic', 'secondaryProgressPic', 'thumbPic')

# 自动生成图统一放 <项目>/resources/images/（MEMORY 铁律 #9），json 引用写 images/xxx.png
_AUTO_ASSET_DIR = 'images'


def _is_auto_generated(ref):
    """引用是否为「流水线自动生成图」——这类图**必须**与控件盒 1:1（唯一强制严格核对的情形）。

    为什么区分（v0.27.33 实测修正，回应「产物核对形同虚设」）：
      ① 自动生成图（html2json/gen_res 出的渐变/圆角/阴影/图标）几何信息烘在像素里，
         尺寸 != 控件盒 → 圆角错位/阴影断边，这是 v0.27.30 事故的本质 → 必须 FAIL。
      ② 手绘图（navi/fh.png 44x26 放在 72x40 按钮里、charge/bg.jpg 800x430 放 1024x550
         window 里）是官方基准工程 SampleUI-New 就有的正常写法，引擎会拉伸到控件盒
         → 尺寸不等属正常，只能 WARN，不能 FAIL。
    判别：按铁律 #9，自动生成图一律在 resources/images/ 下（引用首段 = images）；
    手绘图可放任意子目录（navi/、charge/、InputBox/ ...）。
    """
    p = (ref or '').replace('\\', '/').lstrip('./')
    return p.split('/')[0].lower() == _AUTO_ASSET_DIR


def _ctrl_pic_refs(v):
    """控件内全部图片引用 [(字段名, 引用)]：backgroundPic / seekbar 四图 / picTab.pic0~picN。"""
    out = []
    for fld in _PIC_REF_FIELDS:
        pv = v.get(fld)
        if isinstance(pv, str) and pv:
            out.append((fld, pv))
    pt_ = v.get('picTab')
    if isinstance(pt_, dict):
        for fld, pv in pt_.items():
            if isinstance(pv, str) and pv:
                out.append(('picTab.%s' % fld, pv))
    return out


def verify_assets(project_root):
    """核对「json 声明 vs 磁盘产物」：引用文件是否存在 + PNG 尺寸是否 == 控件 position。

    为什么必须机器化：FlyThings 不缩放普通 PNG，图与控件盒不等即错位/裁切；
    v0.27.30 的阴影三连 bug 正是「图没生成也没人发现」，靠人肉目测漏掉了。

    返回可 JSON 序列化的 dict：
      ok / pages / refCount / missing[] / mismatch[] / stretched[] / unresolved[] / warnings[] / noPil
      - missing   ：字段引用了图片但文件不存在 → FAIL
      - mismatch  ：**自动生成图**（resources/images/，铁律 #9）尺寸 != position → FAIL
                    （.9.png 除外，9-patch 可拉伸）
      - stretched ：手绘图尺寸 != 控件盒 → 仅提示（引擎会拉伸，基准工程 SampleUI-New 也这么用）
      - unresolved：带 %s 格式化前缀 / json 解析失败 / 读图失败（仅提示）
      - warnings  ：0 页等「其实什么都没核」的情况会写这里（不静默）
    """
    root = os.path.abspath(project_root)
    ui = os.path.join(root, 'ui')
    res = {'ok': True, 'projectRoot': root, 'pages': 0, 'refCount': 0,
           'missing': [], 'mismatch': [], 'stretched': [], 'unresolved': [], 'warnings': [],
           'noPil': not _HAS_PIL}
    if not os.path.isdir(ui):
        res['ok'] = False
        res['error'] = 'ui 目录不存在: %s' % ui
        return res
    pages = _ui_pages(root)
    res['pages'] = len(pages)
    if not pages:
        # 不静默：0 页时 ok=true 会让人以为「核对过了」——其实什么都没看
        res['warnings'].append('ui/ 下没找到布局 json（支持 ui/*.json 与 ui/<分辨率>/*.json），'
                               '本次未核对任何产物')
    for p in pages:
        page = os.path.relpath(p, root).replace('\\', '/')
        try:
            d = json.load(open(p, encoding='utf-8'))
        except Exception as e:
            res['unresolved'].append({'page': page, 'ref': '-', 'why': 'json 解析失败: %s' % e})
            continue
        for key, v in _all_controls(d):
            pos = v.get('position') or {}
            pw, ph = pos.get('width'), pos.get('height')
            for fld, ref in _ctrl_pic_refs(v):
                if '%s' in ref:
                    res['unresolved'].append({'page': page, 'control': key, 'field': fld,
                                              'ref': ref, 'why': '运行时格式化引用，跳过逐控件核对'})
                    continue
                res['refCount'] += 1
                fp = _pic_path(root, ref)
                if not fp:
                    res['missing'].append({'page': page, 'control': key, 'field': fld, 'ref': ref})
                    continue
                if ref.lower().endswith('.9.png') or not _HAS_PIL or not pw or not ph:
                    continue
                try:
                    with _Image.open(fp) as im:
                        w, h = im.size
                except Exception as e:
                    res['unresolved'].append({'page': page, 'control': key, 'field': fld,
                                              'ref': ref, 'why': 'PIL 读取失败: %s' % e})
                    continue
                if (w, h) != (pw, ph):
                    row = {'page': page, 'control': key, 'field': fld, 'ref': ref,
                           'png': [w, h], 'position': [pw, ph]}
                    if _is_auto_generated(ref):
                        res['mismatch'].append(row)      # 自动生成图必须 1:1 → FAIL
                    else:
                        res['stretched'].append(row)     # 手绘图引擎会拉伸 → 仅提示
    res['ok'] = not (res.get('error') or res['missing'] or res['mismatch'])
    if res['stretched']:
        res['warnings'].append(
            '%d 处手绘图尺寸 != 控件盒（引擎会拉伸，通常正常，仅供确认；'
            '自动生成图才必须 1:1）：%s'
            % (len(res['stretched']),
               '；'.join('%s %s %dx%d!=%dx%d' % (r['control'], r['field'], r['png'][0], r['png'][1],
                                                 r['position'][0], r['position'][1])
                         for r in res['stretched'][:4])))
    return res


# ---------------- 设计令牌漂移检测（DESIGN.md 令牌 vs json 实际值，沛哥 2026-09-12）----------------
# 口径：DESIGN.md 是「冻结的视觉真相」——json 里的颜色/字号应当来自令牌，不应当出现模板外的值。
# 结构值例外（不经令牌）：0（透明）/ -1（未设）/ 16777215（纯白，平台默认文本色）；
# 显式豁免：在 DESIGN.md 里写一行「漂移豁免: #RRGGBB 18 24」即视为已批准（便于单点例外留痕）。
_HEX_RE = re.compile(r'#[0-9A-Fa-f]{6}\b')
_NUM_RE = re.compile(r'(?<![\w.])-?\d+(?![\w.])')
_COLOR_SEC_HINT = ('色彩令牌', '色彩', 'color token')
_FONT_SEC_HINT = ('字号阶梯', '字号')
_SPACE_SEC_HINT = ('间距梯度', '间距')
_HERO_HINT = ('hero', 'Hero', 'HERO')
_EXEMPT_HINT = ('漂移豁免', '令牌豁免')
_STRUCT_COLORS = {0, -1, 16777215}
_COLOR_FIELDS = ('backgroundColor', 'textColor', 'clockColor', 'penColor', 'hintTextColor',
                 'borderColor', 'progressColor')


def _hexstr(v):
    return '#%06X' % (v & 0xFFFFFF)


def _md_sections(text):
    """按 '## ' 标题切分 DESIGN.md → {标题: 正文}。"""
    out = {}
    cur = ''
    buf = []
    for line in text.splitlines():
        if line.startswith('## '):
            if cur:
                out[cur] = '\n'.join(buf)
            cur = line[3:].strip()
            buf = []
        else:
            buf.append(line)
    if cur:
        out[cur] = '\n'.join(buf)
    return out


def _parse_design_tokens(text):
    """解析 DESIGN.md → (colors, fonts, spacing, exempt)，空集合表示该项未填。"""
    secs = _md_sections(text)
    colors, fonts, spacing, exempt = set(), set(), set(), set()
    for title, body in secs.items():
        if any(h in title for h in _COLOR_SEC_HINT):
            for m in _HEX_RE.finditer(body):
                colors.add(int(m.group(0)[1:], 16))
        if any(h in title for h in _FONT_SEC_HINT):
            for row in body.splitlines():
                if not row.strip().startswith('|'):
                    continue
                for n in _NUM_RE.findall(row):
                    v = int(n)
                    if 8 <= v <= 400:
                        fonts.add(v)
        if any(h in title for h in _SPACE_SEC_HINT):
            for row in body.splitlines():
                for n in _NUM_RE.findall(row):
                    v = int(n)
                    if 0 < v <= 400:
                        spacing.add(v)
    for line in text.splitlines():
        if any(h in line for h in _HERO_HINT):
            for n in _NUM_RE.findall(line):
                v = int(n)
                if 8 <= v <= 400:
                    fonts.add(v)
        if any(h in line for h in _EXEMPT_HINT):
            for m in _HEX_RE.finditer(line):
                colors.add(int(m.group(0)[1:], 16))
            for n in _NUM_RE.findall(line):
                exempt.add(int(n))
    return colors | exempt, fonts | exempt, spacing, exempt


def _collect_json_colors_fonts(node, out_colors, out_fonts, path=''):
    """递归收集 json 里的颜色字段与字号（控件键下的 color* / fontSize / textSize）。"""
    if isinstance(node, dict):
        for k, v in node.items():
            p = ('%s.%s' % (path, k)) if path else k
            if isinstance(v, dict):
                _collect_json_colors_fonts(v, out_colors, out_fonts, p)
            elif isinstance(v, list):
                for i, it in enumerate(v):
                    _collect_json_colors_fonts(it, out_colors, out_fonts, '%s[%d]' % (p, i))
            elif isinstance(v, int) and not isinstance(v, bool):
                if k in _COLOR_FIELDS or (k.startswith('color') and k[5:].isdigit()):
                    out_colors.append((_ctrl_path(p), k, v))
                elif k in ('fontSize', 'textSize'):
                    out_fonts.append((_ctrl_path(p), k, v))
    return out_colors, out_fonts


def _ctrl_path(p):
    """把 'tv位置.子键.字段' 压成 '控件键.字段'，便于报错定位。"""
    parts = p.split('.')
    for i in range(len(parts) - 1):
        if _CTRL_KEY_RE.match(parts[i]):
            return '%s.%s' % (parts[i], parts[-1])
    return p


def _sibling_gaps(node, out, path='root'):
    """同容器内相邻同级控件的纵向间距（用于间距梯度核对），返回 [(gap, 容器路径)]。"""
    if not isinstance(node, dict):
        return out
    items = []
    for k, v in node.items():
        if isinstance(v, dict) and _CTRL_KEY_RE.match(k):
            r = _rect(v)
            if r:
                items.append((r[1], r[3], k))
    items.sort()
    for i in range(1, len(items)):
        gap = items[i][0] - items[i - 1][1]
        if gap > 0:
            out.append((gap, path))
    for k, v in node.items():
        if isinstance(v, dict) and '__' in k:
            _sibling_gaps(v, out, k)
    return out


def verify_design_tokens(project_root):
    """DESIGN.md 令牌 vs json 实际值（漂移检测）。返回 {status, note, colors, fonts, gaps, scanned, tokens, ok}。"""
    res = {'status': 'ok', 'note': '', 'colors': [], 'fonts': [], 'gaps': {},
           'scanned': 0, 'tokens': {}, 'ok': True}
    md = os.path.join(project_root, 'DESIGN.md')
    if not os.path.isfile(md):
        res['status'] = 'skip'
        res['note'] = ('未见 DESIGN.md（新项目第一版视觉应当有：见 skill flythings-ui-dev / '
                       'templates/DESIGN.md）；存量工程可忽略')
        return res
    text = open(md, encoding='utf-8').read()
    colors, fonts, spacing, _exempt = _parse_design_tokens(text)
    if len(colors) < 2 or not fonts:
        res['status'] = 'incomplete'
        res['note'] = ('DESIGN.md 令牌表未填全（解析到 颜色 %d 个 / 字号 %d 个），跳过漂移检测；'
                       '按 templates/DESIGN.md 填「色彩令牌 + 字号阶梯」后再跑' % (len(colors), len(fonts)))
        return res
    allowed_c = colors | _STRUCT_COLORS
    ui = os.path.join(project_root, 'ui')
    for f in _ui_pages(project_root):
        rel = 'ui/' + os.path.relpath(f, ui).replace('\\', '/')
        d = json.load(open(f, encoding='utf-8'))
        got_c, got_f = _collect_json_colors_fonts(d, [], [])
        for ctrl, fld, v in got_c:
            if v not in allowed_c:
                res['colors'].append((rel, ctrl, fld, v))
        for ctrl, fld, v in got_f:
            if v not in fonts:
                res['fonts'].append((rel, ctrl, fld, v))
        if spacing:
            for gap, where in _sibling_gaps(d, []):
                res['gaps'][gap] = res['gaps'].get(gap, 0) + 1
        res['scanned'] += 1
    res['gaps'] = dict(sorted((g, c) for g, c in res['gaps'].items() if g not in spacing))
    res['tokens'] = {'colors': sorted(colors), 'fonts': sorted(fonts), 'spacing': sorted(spacing)}
    res['ok'] = not res['colors'] and not res['fonts']
    return res


# ---------------- 19. V85X：视频解码返回后必须 releaseLayer（防黑屏）----------------
# 沛哥 2026-09-14 定：平台匹配（V85X 系 disp 分层平台）时，视频解码返回后必须释放残留 disp 层，
# 否则残留视频层不关 → 屏幕黑屏；**开发与 check 验收都必须做这个**。
# 参考实现：knowledge/v85x/display-layer-debug.md §2（/dev/disp + DISP_LAYER_GET/SET_CONFIG，
# 只关非 UI 层（跳过 ARGB 格式层），有开机动画时用 /tmp/zk_boot_anim 存在性保护）。
_VIDEO_DECODE_MARKERS = (
    'zk_h264_player_', 'h264_player.h', 'vdecoder.h', 'VideoDecoder',
    'mi_vdec', 'CedarX', 'sunxi_display2',
)
_LAYER_RELEASE_MARKERS = (
    'DISP_LAYER_SET_CONFIG', 'DISP_LAYER_GET_CONFIG', '/dev/disp',
    'release_layer', 'releaseLayer', 'ReleaseLayer', 'hwdisplay.h',
)
_SRC_SKIP_DIRS = ('dependencies', 'lib-no-link', '.fun', '.fuse', 'Release', 'build')


def _manifest_platform(root):
    """读 Manifest.xml 的 platform 属性（找不到返回空串）。"""
    p = os.path.join(root, 'Manifest.xml')
    if not os.path.isfile(p):
        return ''
    try:
        m = re.search(r'<manifest\b[^>]*\bplatform\s*=\s*"([^"]+)"',
                      open(p, encoding='utf-8', errors='replace').read())
        return m.group(1).strip().upper() if m else ''
    except Exception:
        return ''


def _scan_src(root, markers):
    """扫 src/ 下级源码里出现过的标记 → {marker: [相对文件...]}。
    读不了的文件不静默吞：记入返回体第二个元素（调用方可提示）。"""
    hits, unread = {}, []
    src = os.path.join(root, 'src')
    if not os.path.isdir(src):
        return hits, unread
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in _SRC_SKIP_DIRS]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() not in ('.c', '.cc', '.cpp', '.h', '.hpp'):
                continue
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, root).replace('\\', '/')
            try:
                txt = open(fp, encoding='utf-8', errors='replace').read()
            except OSError as e:
                unread.append('%s(%s)' % (rel, e.__class__.__name__))
            else:
                for mk in markers:
                    if mk in txt:
                        hits.setdefault(mk, []).append(rel)
    return hits, unread


def check_v85x_release_layer(root):
    """V85X 视频解码返回后是否做了图层释放（返回 dict: status/ok/detail/note）。"""
    plat = _manifest_platform(root)
    if not plat:
        return {'status': 'skip', 'note': 'Manifest.xml 无 platform 属性，无法判定平台'}
    if 'V85X' not in plat and 'V853' not in plat and 'V851' not in plat and 'V553' not in plat:
        return {'status': 'skip', 'note': '平台 %s 非 V85X 系（disp 分层平台不适用）' % plat}
    dec, dec_unread = _scan_src(root, _VIDEO_DECODE_MARKERS)
    rel, rel_unread = _scan_src(root, _LAYER_RELEASE_MARKERS)
    if not dec:
        extra = '（%d 个源码文件读取失败：%s）' % (len(dec_unread), '、'.join(dec_unread[:3])) if dec_unread else ''
        return {'status': 'skip', 'note': '平台 %s，但 src/ 未见视频解码用法（无需图层释放）%s' % (plat, extra)}
    dec_files = sorted(set(f for v in dec.values() for f in v))
    if rel:
        rel_files = sorted(set(f for v in rel.values() for f in v))
        # 2026-09-14 V851 真机实测：用「格式区间（ARGB_8888~BGRA_5551）判 UI 层」会漏关残留层
        # （RGB_888=0x08 落在区间内被误判；COLOR 层 fb.format 读出来就是 color 低字节）→ 提醒改 ch/lyr。
        fmt_hits = _scan_src(root, ('DISP_FORMAT_ARGB_8888', 'DISP_FORMAT_BGRA_5551'))[0]
        unsafe = sorted(set(fmt_hits.get('DISP_FORMAT_ARGB_8888', []))
                        & set(fmt_hits.get('DISP_FORMAT_BGRA_5551', [])))
        return {'status': 'ok', 'ok': True, 'unsafe': unsafe,
                'detail': '已做（解码用法 %s；释放实现 %s）'
                          % ('、'.join(dec_files[:3]), '、'.join(rel_files[:3]))}
    miss = sorted(set(dec_unread + rel_unread))
    return {'status': 'ok', 'ok': False,
            'detail': '缺失！平台 %s + 视频解码（%s）但未见 disp 图层释放 → '
                      '残留视频层不关会黑屏。修复：视频解码返回后关闭除 UI 层外的 disp 层'
                      '（open("/dev/disp") + DISP_LAYER_GET_CONFIG/SET_CONFIG 置 enable=0，'
                      '跳过 ARGB 格式的 UI 层；有开机动画时用 /tmp/zk_boot_anim 存在性保护），'
                      '可直接复用 knowledge/v85x/display-layer-debug.md §2 的实现%s'
                      % (plat, '、'.join(dec_files[:3]),
                         '（%d 个源码文件读取失败，建议人工复核：%s）' % (len(miss), '、'.join(miss[:3])) if miss else '')}


def main(project_root):
    root = os.path.abspath(project_root)
    if not os.path.isdir(root):
        print(f'[X] 项目目录不存在: {root}')
        sys.exit(1)
    ui = os.path.join(root, 'ui')
    if not os.path.isdir(ui):
        print(f'[X] ui 目录不存在: {ui}')
        sys.exit(1)

    PAGES = sorted('ui/' + os.path.relpath(f, ui).replace('\\', '/')
                   for f in _ui_pages(root))
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

    print('== 17. 资源产物核对（引用存在 + 自动生成图 PNG 尺寸 == 控件 position）==')
    va = verify_assets(root)
    if va.get('error'):
        log(False, '产物核对 %s' % va['error'])
    else:
        log(not va['missing'], '图片引用存在性（%d 个页面 / %d 处引用）%s'
            % (va['pages'], va['refCount'],
               '全部存在' if not va['missing'] else '缺 %d 个：%s'
               % (len(va['missing']), '；'.join('%s %s' % (m['control'], m['field']) for m in va['missing'][:6]))))
        log(not va['mismatch'], 'PNG 尺寸 == 控件 position（自动生成图）%s'
            % ('全部匹配' if not va['mismatch'] else '不匹配 %d 处：%s'
               % (len(va['mismatch']),
                  '；'.join('%s.%s %dx%d != %dx%d'
                            % (m['control'], m['field'], m['png'][0], m['png'][1],
                               m['position'][0], m['position'][1]) for m in va['mismatch'][:6]))))
        if va.get('stretched'):
            print('  [NOTE] %d 处手绘图尺寸 != 控件盒（引擎会拉伸，通常正常）：%s'
                  % (len(va['stretched']),
                     '；'.join('%s.%s %dx%d != %dx%d'
                               % (m['control'], m['field'], m['png'][0], m['png'][1],
                                  m['position'][0], m['position'][1])
                               for m in va['stretched'][:5])))
        if va['unresolved']:
            print('  [NOTE] %d 处跳过（运行时格式化引用/读图失败），见 flythings_verify_assets 明细'
                  % len(va['unresolved']))

    print('== 18. 设计令牌漂移检测（DESIGN.md 令牌 vs json 实际值；沛哥 2026-09-12）==\n'
          '      口径：DESIGN.md 冻结视觉真相，json 颜色/字号应来自令牌；结构值例外 0/-1/16777215；\n'
          '      单项例外写一行「漂移豁免: #RRGGBB 18」留痕。无 DESIGN.md / 令牌表未填 → NOTE 跳过。')
    dt = verify_design_tokens(root)
    if dt['status'] in ('skip', 'incomplete'):
        print('  [NOTE] 跳过：%s' % dt['note'])
    else:
        tk = dt.get('tokens') or {}
        log(dt['ok'], '令牌漂移 色值 %d 处 / 字号 %d 处（%d 页；令牌：色 %d / 字 %d）%s'
            % (len(dt['colors']), len(dt['fonts']), dt['scanned'],
               len(tk.get('colors', [])), len(tk.get('fonts', [])),
               '，全部在令牌内' if dt['ok'] else '：'
               + '；'.join('%s %s.%s=%s' % (p, c, fld, _hexstr(v))
                           for p, c, fld, v in dt['colors'][:6])
               + '；'.join('%s %s.%s=%d' % (p, c, fld, v)
                           for p, c, fld, v in dt['fonts'][:4])))
        if dt['gaps']:
            warn('间距梯度外的纵向间距 %d 种（芯距/对齐可能正常，请人工确认；间距梯度=%s）：%s'
                 % (len(dt['gaps']), ','.join(str(s) for s in tk.get('spacing', [])),
                    '、'.join('%dpx×%d' % (g, c) for g, c in list(dt['gaps'].items())[:8])))

    print('== 19. V85X 视频解码返回后必须 releaseLayer（防黑屏；沛哥 2026-09-14 定：\n'
          '      平台匹配时开发与 check 验收都必须做，参考 knowledge/v85x/display-layer-debug.md §2）==')
    rl = check_v85x_release_layer(root)
    if rl['status'] == 'skip':
        print('  [NOTE] 跳过：%s' % rl['note'])
    else:
        log(rl['ok'], 'V85X 图层释放 %s' % rl['detail'])
        if rl.get('unsafe'):
            warn('V85X 图层释放用「格式区间（DISP_FORMAT_ARGB_8888 ~ DISP_FORMAT_BGRA_5551）判定 UI 层」'
                 '（%s）→ 2026-09-14 V851 真机实测会漏关残留层：RGB_888(0x08) 落在区间内被误判为 UI 层、'
                 'COLOR 模式层读出的 fb.format 就是 color 低字节 → 黑层/残留层留在最上面 = 一直黑屏。'
                 '修复：改按 ch/layer 跳过 UI 层（if (ch == UI_LYCHN && lyl == UI_LYLAY) continue;），'
                 '要双重保险就限定 mode == LAYER_MODE_BUFFER 后才看 format。'
                 '详见 knowledge/v85x/display-layer-debug.md §2-1-1'
                 % '、'.join(rl['unsafe'][:3]))

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
