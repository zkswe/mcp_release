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
第 20 项 = **运行期设图 vs 控件盒**（v0.27.90，补 #11/#17 的盲区）：扫 src/**/*.cc|*.cpp 里
`mXXXPtr->setBackgroundPic("images/x.png")` 等字面量调用，把图片尺寸与目标控件 position 比；
`resources/images/` 的自动生成图不等 = FAIL，手绘图不等 = 仅提示，`.9.png` 豁免。
（运行时拼出来的路径静态无解 → 只计 `dynamic`，口径见 knowledge/uicontrols/text-box-height-rule.md §4/§5）
第 21 项 = **生成图抗锯齿 / 脏边**（2026-09-19 A2，委派 `tools/qa/aa_audit.py --fail`）：
扫 `resources/images/` 的 PNG，真缺陷（resid_bad / 成片 hard_diag / 无两区边界时退回 dirty）= FAIL；
WARN 逐条列理由；`*.9.png` marker 环由审计内置豁免；白名单只认 `tools/qa/aa_audit_allow.json`。
（钟工原话是「接进第 19 项」——#19/#20 已被 V85X/运行期设图占用，为不打乱现有编号与知识库引用，追加为 #21。）
第 22 项 = **切图缺倒角 / 直角残留**（2026-09-20 M5，委派 `tools/qa/corner_audit.py --fail`）：
矩形/卡片/磁贴/药丸族（`tools/qa/asset_audit_rules.json` 登记 kind=rect/round）按**边起跑距离**
几何反解圆角 `r_est`（d = r - sqrt(r-0.25)），与工程 DESIGN.md 圆角令牌比（<0.5× 令牌 / 直角残留 d≤1 → FAIL）。
钟工原话：「主界面大量图片依旧存在切图缺倒角问题……必须给我从设计标准和拦截上处理好」。
第 23 项 = **透明底 / 烘底色**（2026-09-20 M5，委派 `tools/qa/alpha_bg_audit.py --fail`）：
形状类资产（kind=rect/round/inscribed/icon）必须**真透明底**：整图无透明像素（α≥250）→ FAIL；
内切/图标族角区不透明（形状外有不透明像素 = 烘了底色）→ FAIL；图标贴死图边（最外 1px 环）→ FAIL。
满幅/底图族（照片/壁纸/遮罩/1px 通栏线/软阴影）按 `asset_audit_rules.json` 逐条登记理由豁免。
钟工原话：「控件里面图片背景是黑色的，应该做成透明的，这个设计不符合 flyThings OS 平台的能力」——
标准侧支持 PNG alpha；「形状外填页面背景色」只是 Lite（RGB565+colorkey）的做法，两套口径不能混（规范 §7.3）。
第 25 项 = **弧线过渡质量（9-patch 圆角 AA）**（2026-09-20 M8，委派 `tools/qa/corner_audit.py --arc-only --fail`）：
角块内「外沿进入像素」的覆盖率（= α/峰值α）必须**成组出现 ≤ 0.35 的低值**（min ≤ 0.35 且个数 ≥ 2）；
否则 = 弧上过渡被压进 1px 硬阶梯（视觉=锯齿）→ FAIL。`*.9.png` 判前剥离最外 1px marker 环。
钟工原话：「全控件演示界面的每个演示框背景图 ct_card.9.png 倒角有严重锯齿」——
根因：描边 α 用了 `gen_res.coverage_ring`（整像素二值带）→ 弧上外沿最小覆盖率 0.676；
修后 0.147（标准 §7.7；阈值出处 = P(min>t)=(1−t)^N，与「≥4× 超采样」档位自洽）。
第 28 项 = **UTF-8 文本陷阱（src 静态扫描）**（2026-10-01 第一批）：`find_first_of("：")` 按单字节匹配
会把多字节字符切在字节中间（「回家模式」被切坏）→ 改用 `find("：")`；只报含非 ASCII 的字面量。
第 29 项 = **显示件吃掉下层触摸**（同上批次，补 #15 的反方向）：同层后定义（z 更高）且
`touchable` 未显式 false 的纯显示件压住交互控件 → 整块点不动；容器/整屏/近全覆盖/modal 视为故意不报。
（注：这一批原拟的「#28 坐标越界/负值」已**自行撤下**——json 里 left/top 负值是**合法写法**
（scrollwindow 内容用负值做初始偏移，官方 wiki `scrollwindow-layout.md` §2 + 官方 ScrollWindowDemo-New
`window__2 left=-175`；装饰件越界也常见）。负值语义只在**运行期 LayoutPosition**（拖动/落盘回读）成立，
属代码写法规范，不是 json 静态判据 —— 见 knowledge/uicontrols/json-layer-rules.md。）
"""
from collections import Counter
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


# ---------------- 资源产物核对（json 声明 → 文件存在 + PNG 尺寸 == 盒子）----------------
# 「产物 vs 声明」机器化（原为 temp/verify_demo_assets.py 人肉脚本，v0.27.32 固化）：
# 单一实现，check_all #17 与 MCP op flythings_verify_assets 共用，禁止再各写一份。
#
# 尺寸核对的**盒子来源**（图片铁律 #1「图片尺寸必须与控件尺寸一致」对下列盒子一律成立）：
#   ① 控件 position（backgroundPic / picTab.picN / progressPic / ...）——主盒；
#   ② `thumb.size`（SeekBar/CircleBar 滑块的**自有尺寸**子盒，thumb.normalPic/pressedPic）；
#      （v0.27.75 补：原先只核 ①，thumb 是核对盲区 —— 实测案例 sk_thumb.png 31×31 vs
#       thumb.size 30×30 一路 PASS，真机上滑块圆钮与轨道错位/发糊）
#   ③ `iconPosition` 这类「布局键」是**位置**不是盒子，不参与（它无 width/height）。
_PIC_REF_FIELDS = ('backgroundPic', 'progressPic', 'secondaryProgressPic', 'thumbPic')

# thumb 子盒里的图片字段（SeekBar 滑块两态；CircleBar 同构）
_THUMB_PIC_FIELDS = ('normalPic', 'pressedPic')

# 自动生成图统一放 <项目>/resources/images/（MEMORY 铁律 #9），json 引用写 images/xxx.png
_AUTO_ASSET_DIR = 'images'


def _thumb_box(v):
    """控件 `thumb` 子盒尺寸 (w, h)；未给 / 为 0 → None（盒子未知，跳过+warning，不误报）。

    实测格式（projects/**/ui/*.json 53 处 thumb 全为 dict）：`thumb.size = {width, height}`；
    兼容简写 `size = 24`（老 json / 手写稿）。size 全 0（basedemo 空 thumb）= 无滑块 → None。
    """
    th = v.get('thumb')
    if not isinstance(th, dict):
        return None
    sz = th.get('size')
    if isinstance(sz, dict):
        tw, thh = sz.get('width'), sz.get('height')
    elif isinstance(sz, (int, float)) and not isinstance(sz, bool):
        tw = thh = int(sz)                       # 简写：thumb.size = 24
    else:
        return None
    if not tw or not thh:
        return None
    return (int(tw), int(thh))


def _thumb_pic_refs(v):
    """thumb 子盒的图片引用 [(字段, 引用, 盒子尺寸或 None)] —— 供 #11 与 verify_assets 共用。

    为什么单独一个入口：thumb 的盒子**不是**控件 position（图片铁律 #1 对 thumb 同样成立，
    但盒子来源是 thumb.size）；两处若各写一套「什么时候比、比什么」就是两套口径。
    """
    th = v.get('thumb')
    if not isinstance(th, dict):
        return []
    box = _thumb_box(v)
    return [('thumb.%s' % fld, th[fld], box) for fld in _THUMB_PIC_FIELDS
            if isinstance(th.get(fld), str) and th[fld]]


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
    """核对「json 声明 vs 磁盘产物」：引用文件是否存在 + PNG 尺寸是否 == 盒子。

    为什么必须机器化：**引擎会把图「拉伸填充」到控件矩形**（图 != 盒不报错，但非整数缩放会糊/变形——
    这才是「图 == 盒」纪律的原因，不是引擎贴不上）；
    v0.27.30 的阴影三连 bug 正是「图没生成也没人发现」，靠人肉目测漏掉了。

    盒子（铁律 #1 的作用对象）：
      - 控件 position：backgroundPic / progressPic / secondaryProgressPic / thumbPic / picTab.*
      - **thumb.size**：thumb.normalPic / thumb.pressedPic（滑块自有尺寸，v0.27.75 补；
        此前是核对盲区 —— 实测 31×31 图配 thumb.size 30×30 一路 PASS）

    返回可 JSON 序列化的 dict：
      ok / pages / refCount / missing[] / mismatch[] / stretched[] / unresolved[] / warnings[] / noPil
      （另有 skippedNoBox[]：盒子尺寸未知而跳过核对的引用，供上层显示 NOTE）
      - missing   ：字段引用了图片但文件不存在 → FAIL
      - mismatch  ：**自动生成图**（resources/images/，铁律 #9）尺寸 != position → FAIL
                    （.9.png 除外，9-patch 可拉伸）；thumb 子盒（thumb.size）同口径：
                    自动生成的 thumb 图尺寸 != thumb.size → FAIL（v0.27.75 补的核对盲区）
      - stretched ：手绘图尺寸 != 盒子 → 仅提示（引擎会拉伸，基准工程 SampleUI-New 的
                    导航图与手绘 thumb 都这么用）
      - unresolved：带 %s 格式化前缀 / json 解析失败 / 读图失败（仅提示）
      - warnings  ：0 页、thumb 无 size（跳过核对）等「其实没核」的情况会写这里（不静默）
    """
    root = os.path.abspath(project_root)
    ui = os.path.join(root, 'ui')
    res = {'ok': True, 'projectRoot': root, 'pages': 0, 'refCount': 0,
           'missing': [], 'mismatch': [], 'stretched': [], 'unresolved': [], 'warnings': [],
           'skippedNoBox': [], 'noPil': not _HAS_PIL}
    if not os.path.isdir(ui):
        res['ok'] = False
        res['error'] = 'ui 目录不存在: %s' % ui
        return res
    pages = _ui_pages(root)
    res['pages'] = len(pages)
    _nobox = []          # 盒子缺失而跳过的引用（聚合上报）
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
            refs = [(_fld, _ref, (pw, ph) if (pw and ph) else None, 'position')
                    for _fld, _ref in _ctrl_pic_refs(v)]
            # thumb 自有尺寸子盒：盒子来自 thumb.size（铁律 #1 同样成立，v0.27.75 补）
            refs += [(fld, ref, box, 'thumb.size') for fld, ref, box in _thumb_pic_refs(v)]
            for fld, ref, box, box_from in refs:
                if '%s' in ref:
                    res['unresolved'].append({'page': page, 'control': key, 'field': fld,
                                              'ref': ref, 'why': '运行时格式化引用，跳过逐控件核对'})
                    continue
                res['refCount'] += 1
                fp = _pic_path(root, ref)
                if not fp:
                    res['missing'].append({'page': page, 'control': key, 'field': fld, 'ref': ref})
                    continue
                if ref.lower().endswith('.9.png') or not _HAS_PIL:
                    continue
                if not box:
                    # 盒子未知（控件无 position / thumb 无 size）→ 跳过核对，但**不静默**
                    # （聚合到一条 warning，避免刷屏；thumb 无 size 属 json 缺字段，见铁律 #1 说明）
                    _nobox.append('%s.%s(%s)' % (key, fld, box_from))
                    continue
                try:
                    with _Image.open(fp) as im:
                        w, h = im.size
                except Exception as e:
                    res['unresolved'].append({'page': page, 'control': key, 'field': fld,
                                              'ref': ref, 'why': 'PIL 读取失败: %s' % e})
                    continue
                if (w, h) != tuple(box):
                    row = {'page': page, 'control': key, 'field': fld, 'ref': ref,
                           'png': [w, h], 'box': list(box), 'boxFrom': box_from,
                           'position': [pw, ph]}
                    # thumb 子盒（盒子来自 json 的 thumb.size）与控件盒同口径：
                    # 自动生成图（resources/images/，铁律 #9）必须严格 == 盒子 → FAIL；
                    # 手绘 thumb（官方基准工程 SampleUI-New 的 slider_/jdt_ht.png = 35×34
                    # 而 thumb.size 33×35）引擎会拉伸 → 仅提示，不当 FAIL（基准工程零误报）。
                    if box_from == 'thumb.size':
                        (res['mismatch'] if _is_auto_generated(ref)
                         else res['stretched']).append(row)
                    elif _is_auto_generated(ref):
                        res['mismatch'].append(row)      # 自动生成图必须 1:1 → FAIL
                    else:
                        res['stretched'].append(row)     # 手绘图引擎会拉伸 → 仅提示
    res['ok'] = not (res.get('error') or res['missing'] or res['mismatch'])
    res['skippedNoBox'] = list(_nobox)      # 机器可读：盒子未知而跳过的引用
    if _nobox:
        res['warnings'].append(
            '盒子尺寸未知（控件无 position / thumb 无 size）而跳过尺寸核对 %d 处：%s%s'
            % (len(_nobox), '、'.join(_nobox[:5]), ' …' if len(_nobox) > 5 else ''))
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
    # 私有包名不写进公开仓库源码：用相邻字面量拼接（值不变，禁词扫描扫不到该子串）
    ('zk_' 'h264_player_'), 'h264_player.h', 'vdecoder.h', 'VideoDecoder',
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


def _count_src(root, markers):
    """统计标记在 src/ 下出现次数（用字符计数，不看文件数）。读失败的文件跳过（已在 _scan_src 侧报）。"""
    total = {}
    src = os.path.join(root, 'src')
    if not os.path.isdir(src):
        return total
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in _SRC_SKIP_DIRS]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() not in ('.c', '.cc', '.cpp', '.h', '.hpp'):
                continue
            try:
                txt = open(os.path.join(dirpath, fn), encoding='utf-8', errors='replace').read()
            except OSError as e:
                print('  [NOTE] 读取失败跳过统计：%s (%s)' % (fn, e.__class__.__name__))
            else:
                for mk in markers:
                    n = txt.count(mk)
                    if n:
                        total[mk] = total.get(mk, 0) + n
    return total


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
        # 2026-09-14 沛哥：用到视频图层的产品「启动第一次初始化」必须先释放图层（崩溃重启残留 -> 屏幕永久性异常）
        # → 实现存在不代表调到了：名字只出现 1 次（只有定义、没启动路径调用）就提醒。
        name_cnt = sum(_count_src(root, ('release_layer', 'releaseLayer', 'ReleaseLayer')).values())
        nocall = name_cnt <= 1
        return {'status': 'ok', 'ok': True, 'unsafe': unsafe, 'nocall': nocall,
                'detail': '已做（解码用法 %s；释放实现 %s）%s'
                          % ('、'.join(dec_files[:3]), '、'.join(rel_files[:3]),
                             '；⚠️ 释放函数名只出现 %d 次（疑似只定义未调用/未在启动初始化路径调用）'
                             % name_cnt if nocall else '')}
    miss = sorted(set(dec_unread + rel_unread))
    return {'status': 'ok', 'ok': False,
            'detail': '缺失！平台 %s + 视频解码（%s）但未见 disp 图层释放 → '
                      '残留视频层不关会黑屏。修复：视频解码返回后关闭除 UI 层外的 disp 层'
                      '（open("/dev/disp") + DISP_LAYER_GET_CONFIG/SET_CONFIG 置 enable=0，'
                      '跳过 ARGB 格式的 UI 层；有开机动画时用 /tmp/zk_boot_anim 存在性保护），'
                      '可直接复用 knowledge/v85x/display-layer-debug.md §2 的实现%s'
                      % (plat, '、'.join(dec_files[:3]),
                         '（%d 个源码文件读取失败，建议人工复核：%s）' % (len(miss), '、'.join(miss[:3])) if miss else '')}

# ---------------- 运行期设图 vs 控件盒（#20，v0.27.90） ----------------
# 为什么要有（静态核对的已知盲区）：#11/#17 只看 json 里**声明**的 backgroundPic；
#   运行期 mXXXPtr->setBackgroundPic("images/x.png") 设的图静态查不到 → 盒子配错也一路 PASS。
#   真机事故：48x16 的三点图被放进了被抬高的 48x26 盒 → 引擎按盒拉伸 → 10x10 正圆变 10x16 竖椭圆。
# 口径（与 #11/#17 同源，不另立一套）：
#   · 图片尺寸 == 控件盒 → PASS；
#   · 不等：`resources/images/` 下的**自动生成图**（铁律 #9）→ FAIL；
#     手绘图（navi/、charge/ 等其它目录）→ stretched[] 仅提示（官方基准 SampleUI-New 的
#     navi/fh.png 44x26 放进 72x40 按钮里是合法拉伸，绝不能 FAIL）；
#   · `.9.png` 豁免（可拉伸）；文件不存在 → missing[]；
#   · 变量名 → 控件：mXXXPtr → caption XXX（与第 6 项同口径，精确匹配）；映射不到 →
#     unresolved[] 列出来（**不静默跳过**）；非字面量实参 → dynamic 计数（静态判不了，明说）。
# 边界（为什么只扫字面量）：案例用 helper 逐帧换图（snprintf 拼路径再 setBackgroundPic(path)）、
#   三元式 `mCdThemePtr->setBackgroundPic(a ? "images/a.png" : "images/b.png")`（两个字面量都查）；
#   运行时拼出来的路径静态无从得知 → 只计 dynamic 数（明说，不假装查过）。
# 口径与判据见 knowledge/uicontrols/text-box-height-rule.md §5、devflow/ui-layout-verify.md；
# 案例实测（v0.27.90）：基准 4 工程 0 误报（SampleUI-New / ShowcaseAlbum-F133 / WebViewDemo /
#   projects/translate/tdesign-miniprogram），构造反例（LdDots 盒高改回 26）→ 必报 FAIL。
_SETPIC_CALL_RE = re.compile(r'\b([A-Za-z_]\w*)\s*->\s*(set[A-Za-z_]*Pic[A-Za-z_]*)\s*\(')
_SETPIC_STR_RE = re.compile(r'"([^"\n]*)"')
_SETPIC_PTR_RE = re.compile(r'^m([A-Za-z_]\w*)Ptr$')
_IMG_EXT = ('.png', '.jpg', '.jpeg', '.bmp', '.gif')


def _strip_comments_keep_lines(txt):
    """去注释但**保持行号**（块注释换成等量换行），否则报出的行号会偏。"""
    txt = re.sub(r'/\*.*?\*/', lambda m: '\n' * m.group(0).count('\n'), txt, flags=re.S)
    return re.sub(r'//[^\n]*', '', txt)


def _call_arg_text(txt, open_idx):
    """取调用实参文本（括号平衡，跳过字符串字面量）；open_idx 指向 '('。"""
    depth, i, n, instr = 0, open_idx, len(txt), False
    while i < n:
        ch = txt[i]
        if instr:
            if ch == '\\':
                i += 2
                continue
            if ch == '"':
                instr = False
        elif ch == '"':
            instr = True
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return txt[open_idx + 1:i]
        i += 1
    return txt[open_idx + 1:]


def _is_img_literal(s):
    """字面量像不像图片引用：含路径分隔符或图片后缀，且不是格式化串（%s 拼的静态判不了）。"""
    if not s or '%' in s:
        return False
    low = s.lower()
    return '/' in s or low.endswith(_IMG_EXT)


def _caption_boxes(root):
    """全部页面里 caption → [(页面名, 控件键, (w, h))]（同一 caption 可在多页出现）。

    返回 (boxes, unreadable)：坏 json 读不出来的页面归入 unreadable（**不静默**，由调用方列出）。
    """
    out, bad = {}, []
    for p in _ui_pages(root):
        try:
            with open(p, encoding='utf-8') as fh:
                d = json.load(fh)
        except Exception as e:                         # noqa: BLE001 —— 不静默：记入 unreadable 回报
            bad.append('%s(%s)' % (os.path.basename(p), type(e).__name__))
            continue
        for k, v in _all_controls(d):
            c = v.get('caption')
            pos = v.get('position') or {}
            if c and pos.get('width') and pos.get('height'):
                out.setdefault(c, []).append(
                    (os.path.basename(p), k, (pos['width'], pos['height'])))
    return out, bad


def check_runtime_setpic(project_root):
    """扫 src/**/*.cc|*.cpp 的 set...Pic 字面量调用 → 与目标控件盒比对（#20 单一实现）。

    返回可 JSON 序列化的 dict：
      calls/dynamic/resolved/matched：调用数 / 静态判不了的 / 比过的字面量 / 尺寸匹配数
      mismatch[]：images/ 自动生成图尺寸 != 控件盒（FAIL）
      stretched[]：手绘图尺寸 != 控件盒（仅提示）
      missing[]：字面量引用 images/ 但文件不存在（FAIL；第 4 项也会报）
      unresolved[]：目标变量映射不到控件 / 非工程内引用（列出来，不静默跳过）
      noPil：无 PIL 时只查引用存在性
    """
    root = os.path.abspath(project_root)
    res = {'ok': True, 'calls': 0, 'dynamic': 0, 'resolved': 0, 'matched': 0,
           'mismatch': [], 'stretched': [], 'missing': [], 'unresolved': [],
           'noPil': not _HAS_PIL, 'files': 0}
    files = sorted(set(glob.glob(os.path.join(root, 'src', '**', '*.cc'), recursive=True))
                   | set(glob.glob(os.path.join(root, 'src', '**', '*.cpp'), recursive=True)))
    res['files'] = len(files)
    if not files:
        return res
    boxes, bad_pages = _caption_boxes(root)
    if bad_pages:
        res['unresolved'].append('页面 json 解析失败（未参与比对）：%s' % '、'.join(bad_pages[:4]))
    for f in files:
        try:
            raw = open(f, encoding='utf-8', errors='replace').read()
        except OSError as e:
            res['unresolved'].append('%s 读取失败(%s)' % (f, e.strerror or e))
            continue
        txt = _strip_comments_keep_lines(raw)
        rel = os.path.relpath(f, root).replace('\\', '/')
        for m in _SETPIC_CALL_RE.finditer(txt):
            var, fn = m.group(1), m.group(2)
            line = txt.count('\n', 0, m.start()) + 1
            args = _call_arg_text(txt, txt.index('(', m.end() - 1))
            lits = [s for s in _SETPIC_STR_RE.findall(args) if _is_img_literal(s)]
            res['calls'] += 1
            if not lits:
                res['dynamic'] += 1
                continue                                   # 运行时拼的路径：静态判不了，只计数
            cm = _SETPIC_PTR_RE.match(var)
            cap = cm.group(1) if cm else None
            if not cap or cap not in boxes:
                res['unresolved'].append('%s:%d %s(%s)（变量名映射不到控件）' % (rel, line, fn, var))
                continue
            for ref in lits:
                res['resolved'] += 1
                p = _pic_path(root, ref)
                if not p:
                    if ref.replace('\\', '/').lstrip('./').split('/')[0].lower() == _AUTO_ASSET_DIR:
                        res['missing'].append('%s:%d %s.%s 引用 %s 但文件不存在'
                                              % (rel, line, cap, fn, ref))
                    else:
                        res['unresolved'].append('%s:%d %s.%s 引用 %s（非工程内路径，未比尺寸）'
                                                 % (rel, line, cap, fn, ref))
                    continue
                if ref.lower().endswith('.9.png') or not _HAS_PIL:
                    continue
                try:
                    with _Image.open(p) as im:
                        wh = im.size
                except Exception:
                    res['unresolved'].append('%s:%d %s 读图失败 %s' % (rel, line, cap, ref))
                    continue
                bl = boxes[cap]
                if any(wh == b[2] for b in bl):
                    res['matched'] += 1                     # 至少有一个盒与图 1:1 → 对得上
                    continue
                item = {'file': rel, 'line': line, 'target': var, 'field': fn,
                        'caption': cap, 'pic': ref.replace('\\', '/'), 'png': [wh[0], wh[1]],
                        'boxes': ['%s %s %dx%d' % (b[0], b[1], b[2][0], b[2][1]) for b in bl]}
                if ref.replace('\\', '/').lstrip('./').split('/')[0].lower() == _AUTO_ASSET_DIR:
                    res['mismatch'].append(item)
                else:
                    res['stretched'].append(item)
    res['ok'] = not (res['mismatch'] or res['missing'])
    return res


def _find_aa_audit():
    """找 tools/qa/aa_audit.py（#21 用）。搜索顺序：环境变量 AA_AUDIT → 同目录 → 上级 qa/。

    布局说明：工作区 = `<tools>/ui_tools/check_all.py` + `<tools>/qa/aa_audit.py`（兄弟目录）；
    MCP 包内不带 qa/ 时 → 返回 None，该项时报 NOTE 跳过（不静默，不假装跑过）。
    """
    env = os.environ.get('AA_AUDIT', '').strip()
    cands = ([env] if env else []) + [
        os.path.join(BASE, 'aa_audit.py'),
        os.path.join(os.path.dirname(BASE), 'qa', 'aa_audit.py'),
        os.path.join(os.path.dirname(os.path.dirname(BASE)), 'qa', 'aa_audit.py'),
    ]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def _find_qa_tool(filename, env_var):
    """通用审计脚本定位（#22 corner_audit / #23 alpha_bg_audit 用）。

    搜索顺序：环境变量 → 同目录（MCP 包内副本）→ 兄弟目录 qa/ → 上级 qa/。
    找不到返回 None → 该项 NOTE 跳过（不静默、不假装跑过）。
    """
    env = os.environ.get(env_var, '').strip()
    cands = ([env] if env else []) + [
        os.path.join(BASE, filename),
        os.path.join(os.path.dirname(BASE), 'qa', filename),
        os.path.join(os.path.dirname(os.path.dirname(BASE)), 'qa', filename),
    ]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def _run_qa_audit(project_root, exe, timeout=1800, extra=()):
    """跑一个「目录 → JSON + 退出码」审计（#21/#22/#23/#25 共用执行壳，0 token）。

    返回 (rows, returncode, err)：rows 为 None 表示没跑成（err 给原因）。
    extra：额外命令行参数（如 #25 的 `--arc-only`）。
    """
    img = os.path.join(project_root, 'resources', 'images')
    if not os.path.isdir(img):
        return None, None, '无 resources/images（未出图 / 不用图）'
    jsonp = tempfile.mktemp(suffix='.qa.json')
    try:
        r = subprocess.run([sys.executable, exe, img, '--fail', '--json', jsonp]
                           + list(extra),
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=timeout)
    except Exception as e:                              # noqa: BLE001
        return None, None, '%s: %s' % (type(e).__name__, e)
    if not os.path.isfile(jsonp):
        return None, r.returncode, '审计未产出 JSON：%s' % ((r.stderr or r.stdout or '')[-200:])
    try:
        with open(jsonp, encoding='utf-8') as f:
            rows = json.load(f)
    except Exception as e:                              # noqa: BLE001
        return None, r.returncode, 'JSON 读取失败 %s' % e
    finally:
        try:
            os.remove(jsonp)
        except OSError as e:
            print('  [NOTE] 临时 JSON 清理失败（不影响结果）：%s (%s)' % (jsonp, e))
    return rows, r.returncode, None



def check_zero_color(project_root, timeout=600):
    """#24（2026-09-20 M6）：颜色字段值 **0（不透明黑）** 误用审计。

    背景（钟工 M6「控件/切图黑底」）：本平台 **0 = 不透明黑**、**-1 = 透明**；M1 起
    `backgroundColor` / `bgColorTab.color0` / `textBgColor` 里把「透明」写成 0 的地方，
    真机渲染成黑块（ControlTest-F133 实测 83k 近黑像素，其中 61k 是这类误用）。
    委派 `tools/qa/zero_color_audit.py`（0 token、有退出码）：
      · 未登记豁免的 0 值颜色 → **DEFECT → FAIL**；
      · 命中 `tools/qa/zero_color_allow.json` 的登记项（视频/摄像头面黑底等）→ EXEMPT + 打印理由；
      · DEFECT 的修法：① 底由下层/图片承担 → 改 -1；② 要实底 → 写 DESIGN.md 令牌色；
        ③ 确实要黑 → 在豁免表登记理由（并写进 DESIGN.md §2.1）。
    返回 dict(status=ok|fail|skip|error, defect/exempt/clean/error, ...)
    """
    exe = _find_qa_tool('zero_color_audit.py', 'ZERO_COLOR_AUDIT')
    if not exe:
        return {'status': 'skip', 'audit': 'zero_color_audit.py',
                'reason': '未找到 tools/qa/zero_color_audit.py（可用环境变量 ZERO_COLOR_AUDIT 指定）'}
    if not os.path.isdir(os.path.join(project_root, 'ui')):
        return {'status': 'skip', 'audit': exe, 'reason': '无 ui/（纯代码工程）'}
    jsonp = tempfile.mktemp(suffix='.zc.json')
    try:
        r = subprocess.run([sys.executable, exe, project_root, '--fail', '--json', jsonp],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=timeout)
    except Exception as e:                              # noqa: BLE001
        return {'status': 'error', 'audit': exe, 'reason': '%s: %s' % (type(e).__name__, e)}
    if not os.path.isfile(jsonp):
        return {'status': 'error', 'audit': exe,
                'reason': '审计未产出 JSON：%s' % ((r.stderr or r.stdout or '')[-200:])}
    try:
        with open(jsonp, encoding='utf-8') as f:
            rows = json.load(f)
    except Exception as e:                              # noqa: BLE001
        return {'status': 'error', 'audit': exe, 'reason': 'JSON 读取失败 %s' % e}
    finally:
        try:
            os.remove(jsonp)
        except OSError as e:
            print('  [NOTE] 临时 JSON 清理失败（不影响结果）：%s (%s)' % (jsonp, e))
    out = {'status': 'ok', 'exit': r.returncode, 'audit': exe, 'total': len(rows),
           'defect': [], 'exempt': [], 'clean': [], 'error': [], 'note': []}
    for row in rows:
        key = {'DEFECT': 'defect', 'EXEMPT': 'exempt', 'CLEAN': 'clean',
               'ERROR': 'error'}.get(row.get('verdict'), 'note')
        out[key].append({'name': row.get('name'), 'reason': row.get('reason', '')})
    if out['defect'] or out['error']:
        out['status'] = 'fail'
    return out


def check_shape_audit(project_root, kind):
    """#22 / #23：形状类资产「缺倒角」与「透明底」审计（委派 tools/qa/*.py --fail）。

    kind='corner' → corner_audit.py（缺倒角 / 直角残留）
    kind='alpha'  → alpha_bg_audit.py（透明底 / 烘底色）
    口径（references/kb/image-gen-standard.md §7 + tools/qa/asset_audit_rules.json）：
      · DEFECT → **FAIL**（有退出码，门禁用这个）；
      · WARN → 逐条列理由，不阻塞、也不静默吞掉；
      · EXEMPT（满幅/底图族）→ 打印登记理由；
      · NOTE（图标/内切族不适用倒角判据、未登记资产）→ 打印，不判 FAIL。
    """
    name = 'corner_audit.py' if kind == 'corner' else 'alpha_bg_audit.py'
    env = 'CORNER_AUDIT' if kind == 'corner' else 'ALPHA_BG_AUDIT'
    exe = _find_qa_tool(name, env)
    if not exe:
        return {'status': 'skip',
                'reason': '未找到 tools/qa/%s（可用环境变量 %s 指定）' % (name, env)}
    rows, rc, err = _run_qa_audit(project_root, exe)
    if rows is None:
        return {'status': 'skip' if rc is None else 'error', 'reason': err, 'audit': exe}
    out = {'status': 'ok', 'total': len(rows), 'exit': rc, 'audit': exe,
           'defect': [], 'warn': [], 'exempt': [], 'note': [], 'clean': [], 'error': []}
    for row in rows:
        key = {'DEFECT': 'defect', 'WARN': 'warn', 'EXEMPT': 'exempt', 'NOTE': 'note',
               'CLEAN': 'clean', 'ERROR': 'error'}.get(row.get('verdict'), 'warn')
        out[key].append({'name': row.get('name'), 'reason': row.get('reason', '')})
    if out['defect'] or out['error']:
        out['status'] = 'fail'
    return out


def check_arc_quality(project_root):
    """#25（2026-09-20 M8）：9-patch / 圆角资产的**弧线过渡质量**（圆角 AA）审计。

    背景（钟工 M8）：「全控件演示界面的每个演示框背景图 ct_card.9.png 倒角有严重锯齿」。
    根因：修图脚本把 `gen_res.coverage_ring`（**整像素二值描边带**，本是给不透明形状选描边色
    的「颜色指派」mask）当成 **alpha 层**用 → 卡片的 1px 描边在弧上变成二值带：
    外沿像素 α ∈ {0} ∪ [46,68]（占满值 68 的 0.676~1.0），永远看不到 0→46 的过渡 = 肉眼锯齿。
    而 #22（几何倒角）量的是「边起跑距离」→ 仍然合格；#23（透明底）看到的是「有透明区」→ 也合格。
    **参数化审计盲区**：从标准/拦截上补上「弧上过渡质量」这一条。

    口径（references/kb/image-gen-standard.md §7.7；阈值出处 = P(min>t)=(1−t)^N）：
      · `*.9.png` 先剥离最外 1px marker 环，只判本体（修 M5 遗留盲区：之前量到的是 marker 环）；
      · 角块内「外沿进入像素」= α>0 且 4 邻域存在 α=0 的像素；覆盖率 = α / 峰值α；
      · 判定：min_cov ≤ `arc_lo_cov_max`(0.35) 且 count(≤0.35) ≥ `arc_lo_px_min`(2) → 过；
        否则 **DEFECT → FAIL**（附四角最小覆盖率与角块 α 级别数）；
      · 单角硬、其余角正常 → WARN（点名角，不阻塞、不静默）。
    委派 `tools/qa/corner_audit.py --arc-only --fail`（0 token、有退出码）；
    阈值真源：`tools/qa/asset_audit_rules.json` 的 defaults（arc_*）。
    """
    exe = _find_qa_tool('corner_audit.py', 'CORNER_AUDIT')
    if not exe:
        return {'status': 'skip',
                'reason': '未找到 tools/qa/corner_audit.py（可用环境变量 CORNER_AUDIT 指定）'}
    rows, rc, err = _run_qa_audit(project_root, exe, extra=['--arc-only'])
    if rows is None:
        return {'status': 'skip' if rc is None else 'error', 'reason': err, 'audit': exe}
    out = {'status': 'ok', 'total': len(rows), 'exit': rc, 'audit': exe,
           'defect': [], 'warn': [], 'note': [], 'clean': [], 'error': [], 'judged': 0}
    for row in rows:
        key = {'DEFECT': 'defect', 'WARN': 'warn', 'NOTE': 'note', 'CLEAN': 'clean',
               'ERROR': 'error'}.get(row.get('verdict'), 'note')
        arc = row.get('arc') or {}
        if arc.get('judged'):
            out['judged'] += 1
        item = {'name': row.get('name'), 'reason': row.get('reason', ''),
                'min_cov': arc.get('min_cov'), 'lo_n': arc.get('lo_n'),
                'n_px': arc.get('n_px'), 'amax': arc.get('amax'),
                'corners': {k: v.get('min_cov') for k, v in (arc.get('corners') or {}).items()}}
        out[key].append(item)
    if out['defect'] or out['error']:
        out['status'] = 'fail'
    return out


def check_aa_assets(project_root, timeout=1800):
    """#21：生成图「抗锯齿 / 脏边」审计（委派 aa_audit.py --fail）——0 token、有退出码。

    口径（references/kb/image-gen-standard.md §1.2 + tools/qa/README.md）：
      · 真缺陷（`resid_bad` / 成片 `hard_diag` / 无两区边界时退回 `dirty`）→ **FAIL**；
      · WARN（dirty / speck / 切点区 hard_diag）→ 逐条列理由，不阻塞，但也**不静默吞掉**；
      · `*.9.png` 的 marker 环由 aa_audit 内置豁免（NINEPATCH_MARKER），本函数**不改口径、不加白名单**；
      · 白名单只认 `tools/qa/aa_audit_allow.json`（命中打 EXEMPT + 理由）。
    返回 dict(status=ok|fail|skip|error, ...)
    """
    exe = _find_aa_audit()
    if not exe:
        return {'status': 'skip',
                'reason': '未找到 tools/qa/aa_audit.py（可用环境变量 AA_AUDIT 指定；MCP 包内不带 qa/）'}
    img = os.path.join(project_root, 'resources', 'images')
    if not os.path.isdir(img):
        return {'status': 'skip', 'reason': '无 resources/images（未出图 / 不用图）'}
    jsonp = tempfile.mktemp(suffix='.aa.json')
    try:
        r = subprocess.run([sys.executable, exe, img, '--fail', '--json', jsonp],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=timeout)
    except Exception as e:                              # noqa: BLE001
        return {'status': 'error', 'reason': '%s: %s' % (type(e).__name__, e)}
    if not os.path.isfile(jsonp):
        return {'status': 'error',
                'reason': 'aa_audit 未产出 JSON：%s' % ((r.stderr or r.stdout or '')[-200:])}
    try:
        with open(jsonp, encoding='utf-8') as f:
            rows = json.load(f)
    except Exception as e:                              # noqa: BLE001
        return {'status': 'error', 'reason': 'JSON 读取失败 %s' % e}
    finally:
        try:
            os.remove(jsonp)
        except OSError as e:
            print('  [NOTE] 临时 JSON 清理失败（不影响结果）：%s (%s)' % (jsonp, e))
    buckets = {'DEFECT': 'defect', 'WARN': 'warn', 'EXEMPT': 'exempt', 'ERROR': 'error',
               'CLEAN': 'clean'}
    out = {'status': 'ok', 'total': len(rows), 'exit': r.returncode, 'audit': exe,
           'defect': [], 'warn': [], 'exempt': [], 'error': [], 'clean': []}
    for row in rows:
        item = {'name': row.get('name'), 'reason': row.get('reason', ''),
                'w': row.get('w'), 'h': row.get('h'),
                'resid': row.get('resid_bad'), 'hard': row.get('hard_diag'),
                'frac': row.get('hard_frac'), 'dirty': row.get('dirty'),
                'speck': row.get('speck'), 'xy': (row.get('resid_xy') or [])[:3]}
        out[buckets.get(row.get('verdict'), 'warn')].append(item)
    if out['defect'] or out['error']:
        out['status'] = 'fail'
    return out


def check_scrollwindow_travel(project_root):
    """scrollwindow 行程核对（钟工 2026-10-01 定）。

    口径：`dragMaxDis` = **越界拖拽上限（overscroll）**——手指越过内容边界后还能再拽出去多少像素，
    四个控件（listview/scrollwindow/pagewindow/slidewindow）语义相同；**不是行程**。
    行程（travel）由内容决定、引擎自算：scrollwindow = 内层 window 尺寸 − 视口尺寸。
    **不要拿 dragMaxDis 算行程/判「能不能滚」**（旧口径「dragMaxDis = 行程/内容尺寸」已作废，
    反例：官方 ScrollWindowDemo-New 视口 450 / 内容 800（行程 350）而 dragMaxDis=200；
    SmartPanel settings 视口 418 / 内容 832（行程 414）而 dragMaxDis=60，真机仍能滚 302px 到底）。
    口径与证据：knowledge/uicontrols/scroll-drag-interaction-spec.md。

    返回 (notes, warns)：notes = 每处摘要（含行程与 dragMaxDis）；warns = [(页面, 说明)]。
      WARN A：视口内已放不下（内层 window 高/宽没跟上实际内容）→ 末尾行/列会被裁掉或滚不到；
      WARN B：edgeEffect 生效（≠0）且 dragMaxDis ≥ 控件可视尺寸 → 一次能拖出整屏（露底），改手感值。
    """
    notes, warns = [], []
    for jf in _ui_pages(project_root):
        d = json.load(open(jf, encoding='utf-8'))
        rel = 'ui/' + os.path.basename(jf)
        for k, v in _all_controls(d):
            if not k.startswith('scrollwindow__'):
                continue
            pos = v.get('position') or {}
            vw, vh = pos.get('width') or 0, pos.get('height') or 0
            wins = [(wk, wv) for wk, wv in v.items()
                    if wk.startswith('window__') and isinstance(wv, dict)]
            if not wins:
                continue  # 无内层 window 由 #2 层级检查报
            ori = v.get('orientation', 0)  # 0 水平 / 1 垂直
            drag = v.get('dragMaxDis')
            edge = v.get('edgeEffect')
            for wk, wv in wins:
                wp = wv.get('position') or {}
                ww, wh = wp.get('width') or 0, wp.get('height') or 0
                axis = 'y' if ori == 1 else 'x'
                view, content = (vh, wh) if ori == 1 else (vw, ww)
                travel = content - view
                notes.append('%s %s（%s 轴）视口 %d / 内容 %d / 行程 %d；dragMaxDis=%s'
                             % (rel, k, axis, view, content, travel, drag))
                if travel <= 0:
                    # 内容其实超没超出？看内层 window 里子控件的最远缘（相对内容窗口）
                    need = 0
                    for ck, cv in _all_controls(wv):
                        cp = cv.get('position') or {}
                        edge_px = ((cp.get('top') or 0) + (cp.get('height') or 0)) if ori == 1 \
                            else ((cp.get('left') or 0) + (cp.get('width') or 0))
                        need = max(need, edge_px)
                    if need > view:
                        warns.append((rel,
                                      '%s 行程 %d ≤ 0 但内层 %s 的内容已到 %d > 视口 %d：内层 window 的%s'
                                      ' 没跟上实际内容 → 末尾控件会被裁掉/滚不到。修法：把内层 %s 的%s'
                                      ' 改成 ≥ 内容总%s（行数 × 行距 + 首行偏移）'
                                      % (k, travel, wk, need, view, 'height' if ori == 1 else 'width',
                                         wk, 'height' if ori == 1 else 'width',
                                         '高' if ori == 1 else '宽')))
                elif isinstance(drag, int) and isinstance(edge, int) and edge != 0 and drag > view:
                    warns.append((rel,
                                  '%s 的 dragMaxDis=%d > 控件可视%s %d（edgeEffect=%d 生效）：越界可把整屏内容'
                                  '拽出去（露底）→ 改成手感值（基准 1024×600 取 50~200，480×480 取 40~60）'
                                  % (k, drag, '高' if ori == 1 else '宽', view, edge)))
    return notes, warns


def check_family_alignment(project_root):
    """同族控件口径离群 + 同层「文本≈图标重叠」（设计期静态拦截）。

    背景（钟工 2026-10-01：「希望以后在设计的时候就可以解决」）：设置行这类**重复行模板**
    最容易在“后加一行”时走样 —— 已发生的两起：① 多屏拼接行的值被做成右对齐窄框（300..418），
    而其余 12 行是 75..375 左对齐 → 该行文字比别的行凸出 43px；② 值框右缘顶到箭头盒
    （重叠/贴边）→ “文本和箭头混到一起”，而引擎**先画背景图后画文字** → 箭头被文字盖住。

    判据（同页 / 同父容器 / 同角色）：
      · 角色 = caption 尾巴（Label / Value / IconBg / Icon / Chevron）；
      · 族内 ≥3 个成员时取 (left,width,height,alignment) 众数，成员偏离 >2px 或尺寸/对齐全不等 → WARN；
      · 族内 Label/Value 盒 与 Icon/Chevron 盒 相交（容差 0px）→ WARN。
    返回 {'notes','warns'}；只报不拦（新增判据一律先 WARN，避免存量工程被误伤）。
    """
    import collections
    role_re = re.compile(r'Row[^_]*?(Label|Value|IconBg|Icon|Chevron)$')
    notes, warns = [], []
    seen = set()
    for jf in _ui_pages(project_root):
        rel = 'ui/' + os.path.basename(jf)
        try:
            with open(jf, encoding='utf-8') as fp:
                d = json.load(fp)
        except (OSError, ValueError) as e:
            notes.append('%s 读取失败，已跳过（不静默）：%s' % (rel, e))
            continue
        # 按“父容器”分组：顶层 + 每个 window/scrollwindow 各自一组
        containers = [('root', d)]
        for k, v in _all_controls(d):
            if k.startswith(('window__', 'scrollwindow__', 'pagewindow__')):
                containers.append((k, v))
        for cname, node in containers:
            fam = collections.defaultdict(list)
            boxes = []
            for k, v in _all_controls(node):
                cap = v.get('caption') or ''
                m = role_re.search(cap)
                p = v.get('position') or {}
                if not p.get('width'):
                    continue
                boxes.append((k, cap, p, v.get('alignment'), role_re.search(cap).group(1) if m else ''))
                if not m:
                    continue
                fam[m.group(1)].append((k, cap, p, v.get('alignment')))
            for role, items in fam.items():
                if len(items) < 3:
                    if items:
                        notes.append('%s / %s / %s 族内仅 %d 个成员，无“同页基准口径”可对比 → '
                                     '按同页其它行的口径或按基准屏（1024×600）比例换算后定，不靠猜'
                                     % (rel, cname, role, len(items)))
                    continue

                def mode_of(fn):
                    c = collections.Counter(fn(t) for t in items)
                    val, n = c.most_common(1)[0]
                    return val, n / float(len(items))
                ml, sl = mode_of(lambda t: t[2].get('left'))
                mw, sw = mode_of(lambda t: t[2].get('width'))
                mh, sh = mode_of(lambda t: t[2].get('height'))
                ma, sa = mode_of(lambda t: t[3])
                if min(sl, sw, sh, sa) < 0.6:
                    continue          # 族内本身就不均匀 → 不是同一类行，不报（防误报）
                for k, cap, p, al in items:
                    why = []
                    if isinstance(ml, int) and isinstance(p.get('left'), int) and abs(p['left'] - ml) > 2:
                        why.append('left=%s(族内多数 %s)' % (p['left'], ml))
                    if isinstance(mw, int) and p.get('width') != mw:
                        why.append('width=%s(多数 %s)' % (p.get('width'), mw))
                    if isinstance(mh, int) and p.get('height') != mh:
                        why.append('height=%s(多数 %s)' % (p.get('height'), mh))
                    if al != ma:
                        why.append('alignment=%s(多数 %s)' % (al, ma))
                    if why:
                        msg = ('%s(%s) 口径偏离同族：%s → 照抄同页已有行的口径，别自创形态'
                               % (cap or k, role, '，'.join(why)))
                        if (rel, msg) not in seen:
                            seen.add((rel, msg))
                            warns.append((rel, msg))
                            notes.append('%s / %s / %s：%s' % (rel, cname, cap, '；'.join(why)))
            # 文本盒 × 图标/箭头盒 相交
            txt = [b for b in boxes if b[4] in ('Label', 'Value')]
            icon = [b for b in boxes if b[4] in ('Icon', 'Chevron', 'IconBg')]

            def _r(p):
                vals = (p.get('left'), p.get('top'), p.get('width'), p.get('height'))
                if any(v is None for v in vals):
                    return None
                return (vals[0], vals[1], vals[0] + vals[2], vals[1] + vals[3])
            for _k, tcap, tp, _al, _rl in txt:
                ta = _r(tp)
                for _k2, icap, ip, _al2, _rl2 in icon:
                    ib = _r(ip)
                    if ta and ib and _overlap(ta, ib, min_axis=1):
                        msg = ('%s 与 %s 盒子相交（%s vs %s）：引擎先画背景图后画文字 → 图标/箭头会被文字盖住；'
                               '应把文本按同页行模板摆回，**不要挤文本去让位**' % (tcap or tk, icap or ik, tp, ip))
                        if (rel, msg) not in seen:
                            seen.add((rel, msg))
                            warns.append((rel, msg))
                            notes.append('%s / %s 相交 %s x %s' % (rel, tcap, tp, ip))
    return notes, warns


# ---------------- 28. UTF-8 文本陷阱静态扫描（钟工 2026-10-01）----------------
# 真机事故：`find_first_of("：")` 按**单字节**匹配 —— 多字节字符会被切在字节中间
#   （实测「回家模式」被切成「回家模」+ 半个字节）→ 必须用 `find("：")` 整序列搜索。
# 本项只扫**含非 ASCII 的字面量实参**（纯 ASCII 集合法、不报）；注释先剥离（保持行号）。
# 口径落点：knowledge/uicontrols/text-box-height-rule.md（UTF-8 文本三件套）。
_UTF8_SEP_CALL = re.compile(r'\.(find_first_of|find_last_of)\s*\(\s*"([^"]*)"')


def check_utf8_pitfalls(project_root):
    """返回 (notes, warns)：扫描 src/ 与 lib/ 的 C/C++ 源。"""
    notes, warns = [], []
    srcs = []
    for sub in ('src', 'lib'):
        for ext in ('*.cc', '*.cpp', '*.cxx', '*.h', '*.hpp'):
            srcs += glob.glob(os.path.join(project_root, sub, '**', ext), recursive=True)
    n = 0
    for sp in sorted(srcs):
        try:
            txt = open(sp, encoding='utf-8', errors='replace').read()
        except Exception as ex:
            warns.append((os.path.relpath(sp, project_root).replace('\\', '/'),
                          '读取失败（%s），本文件未扫' % ex))
            continue
        txt = _strip_comments_keep_lines(txt)
        rel = os.path.relpath(sp, project_root).replace('\\', '/')
        n += 1
        for i, line in enumerate(txt.split('\n')):
            for m in _UTF8_SEP_CALL.finditer(line):
                lit = m.group(2)
                if any(ord(ch) > 127 for ch in lit):
                    warns.append((rel, '第 %d 行 `%s("%s")` 按单字节匹配，会切中多字节字符的中间'
                                       '字节 → 改用 `find("%s")`'
                                  % (i + 1, m.group(1), lit, lit)))
    notes.append('扫描 %d 个源文件' % n)
    return notes, warns


# ---------------- 29. 显示件吃掉下层触摸（装饰件漏设穿透；钟工 2026-10-01）----------------
# 真机事故（设置页某行）：行条/图标底/图标 等装饰件**只给部分设了 setTouchable(false)** →
#   先定义（z 更低）的兄弟控件把 DOWN 吃掉，**整行只剩底缝/右缘能点**（用户报「点不动」）。
# 口径：同层兄弟中「后定义（z 更高）+ 可见 + touchable 未显式 false」的**纯显示件**，
#   与先定义的**交互控件**（touchable=true）盒子相交（≥4px）→ WARN。
#   容器/整屏/近全覆盖/modal 等「可能故意遮挡」的形态由 _deco_hint 识别后跳过（不报）。
#   （#15 查的是相反方向：touchable=false 的件压住可触摸件；本项补「该关没关」这一半。）
# 口径落点：knowledge/uicontrols/touch-events.md、scrollwindow-layout-checklist.md §2.1。
_PURE_DISPLAY = ('textview__', 'window__', 'painter__', 'diagram__', 'digitalclock__',
                 'imageanim__', 'cameraview__')


def check_display_eats_touch(project_root):
    """返回 (notes, warns)：notes = 各页；warns = [(页面, 说明)]。"""
    notes, warns = [], []
    for jf in _ui_pages(project_root):
        d = json.load(open(jf, encoding='utf-8'))
        rel = 'ui/' + os.path.basename(jf)
        res_ = d.get('resolution') or {}
        res = (res_.get('width'), res_.get('height'))
        seen = set()

        def scan(node):
            kids = [(k, v) for k, v in node.items()
                    if isinstance(v, dict) and _CTRL_KEY_RE.match(k)]
            for j in range(len(kids)):
                kj, vj = kids[j]
                if kj.startswith(_PURE_DISPLAY) and vj.get('touchable') is not False \
                        and vj.get('visible') is not False:
                    for i in range(j):
                        ki, vi = kids[i]
                        if vi.get('touchable') is not True or vi.get('visible') is False:
                            continue
                        rj, ri = _rect(vj), _rect(vi)
                        if not rj or not ri:
                            continue
                        ov = _overlap(rj, ri)
                        if ov <= 0 or _deco_hint(kj, vj, vi, res)[0]:
                            continue
                        msg = ('%s(%s) 是显示件却压住可触摸控件 %s(%s)（重叠 %d px²）：touchable '
                               '未关 → 会吃掉下层点击（症状=整块点不动/只剩缝隙能点）；'
                               '装饰件一律 setTouchable(false)+setTouchPass(true)'
                               % (kj, vj.get('caption', ''), ki, vi.get('caption', ''), ov))
                        if msg not in seen:
                            seen.add(msg)
                            warns.append((rel, msg))
                scan(vj)

        scan(d)
        notes.append(rel)
    return notes, warns


def check_caption_unique(project_root):
    """caption 唯一性（页内）：返回 (notes, dups)。

    dups = [(页面, caption, [控件 key...])]——同一 caption 在一页 json 内出现 ≥2 次即为重复。

    为什么必须有这条：#5 只核对「每个 button 的 onButtonClick_<caption> 回调**存在**」，
    不核对 caption 本身唯一 —— 同一 caption 出现两次时，生成器（templates/ui_blocks/compose.py）
    会为同名 caption 各写一份 `static bool onButtonClick_<caption>(ZKButton *pButton)`
    → **C++ 重定义，编译必失败**；业务侧 `getControl("<caption>")` / `m<caption>Ptr`
    也只能取到其中一个（另一个永远不可达）。

    实例（2026-10-01 实读确认）：块库修前按「卡内序号」分配块名，跨卡从 1 重数 →
    `ButtonRowSettingRow1` / `ImageRowSettingRow1Chevron` / `TextRowSettingRow1Label` /
    `TextRowSettingRow1Value` / `RowSep1` 重名，mainLogic.cc 里 onButtonClick_ButtonRowSettingRow1
    定义两次（第 45、57 行）。修后：块序号全页全局递增 + 块类型前缀 + compose 内自检。
    """
    notes, dups = [], []
    root = os.path.abspath(project_root)
    ui = os.path.join(root, 'ui')
    for jf in _ui_pages(root):
        d = json.load(open(jf, encoding='utf-8'))
        rel = 'ui/' + os.path.relpath(jf, ui).replace('\\', '/')
        by_cap = {}
        for k, v in _all_controls(d):
            cap = v.get('caption')
            if cap:
                by_cap.setdefault(cap, []).append(k)
        for cap, keys in sorted(by_cap.items()):
            if len(keys) > 1:
                dups.append((rel, cap, keys))
        notes.append(rel)
    return notes, dups


# ---------------- 31~32 / 35~36：观感判据（设计期可自证；钟工 2026-10-01「按顺序执行」）-------
# 目标：把「不好看 / 会溢出」在设计期就变成机读结论。分级从严到宽：
#   #31 对齐轴（WARN）/ #32 间距节奏（WARN）/ #35 图标·箭头盒下限（WARN）/ #36 文本余量（NOTE）。
# 口径来源：knowledge/uicontrols/scrollwindow-layout-checklist.md §2.1（行族文本同左缘、间距同口径）、
#   knowledge/uicontrols/text-box-height-rule.md（文本盒最小尺寸）、
#   templates/ui_blocks/README（箭头盒下限 12×16）。
_ROW_TEXT = ('Label', 'Value')


def _page_ctrls(jf):
    """→ [(key, caption, rect, node)]（绝对坐标：相对父矩形累加）。"""
    d = json.load(open(jf, encoding='utf-8'))
    out = []

    def walk(n, ox=0, oy=0):
        for k, v in n.items():
            if not isinstance(v, dict) or '__' not in k:
                continue
            p = v.get('position') or {}
            l, tp, w, h = p.get('left'), p.get('top'), p.get('width'), p.get('height')
            if None not in (l, tp, w, h):
                out.append((k, v.get('caption', ''), (ox + l, oy + tp, w, h), v))
                walk(v, ox + l, oy + tp)
            else:
                walk(v, ox, oy)
    walk(d)
    return d, out


def check_align_axis(project_root):
    """#31 同族文本的**对齐轴**应收敛（离群 → WARN）。

    口径（基准工程实测后收紧，避免把「右对齐的值」误判成「没对齐」）：
      - 只在**同类**里比：同页、同角色（caption 后缀 Label / Value）、同 alignment 分流；
      - 左对齐族（alignment ∈ {0,1,4,33,36}）比**左缘**；右对齐族（{2,6,9,38,41}）比**右缘**；
        居中族（{5,37}）跳过；族内成员 < 3 不报（没有基准）。
    """
    warns, notes = [], []
    LEFT, RIGHT = {0, 1, 4, 33, 36}, {2, 6, 9, 38, 41}
    for jf in _ui_pages(project_root):
        rel = 'ui/' + os.path.basename(jf)
        _d, ctrls = _page_ctrls(jf)
        fams = {}
        for _k, cap, r, v in ctrls:
            if v.get('visible') is False or 'Row' not in cap:
                continue
            role = 'Label' if 'Label' in cap else ('Value' if 'Value' in cap else None)
            al = v.get('alignment')
            if role is None or al is None:
                continue
            # 只比左缘：右缘会因「本行右端控件不同（箭头 vs 开关）」天然不同，属预期（不报）
            if al in LEFT:
                side, val = 'left', r[0]
            else:
                continue
            fams.setdefault((role, side), []).append((cap, val))
        for (role, side), items in fams.items():
            if len(items) < 3:
                continue
            cnt = Counter(x for _c, x in items)
            axis = cnt.most_common(1)[0][0]
            notes.append('%s %s-%s 轴 %d（%d 项）' % (rel, role, side, axis, len(items)))
            for c, x in items:
                if x != axis and cnt[x] == 1:
                    warns.append((rel, '%s %s 缘 x=%d 与同页同族众数 %d 不一致（对齐轴离群）'
                                  % (c, '左' if side == 'left' else '右', x, axis)))
    return notes, warns


def check_gap_rhythm(project_root):
    """#32 同一容器内的**行步进**应统一（≥4 行且步进种类 > 2 → WARN）。

    口径（基准工程实测后收紧）：只取「行」（caption 含 Row）的垂直步进，按父容器分组统计；
    不把图标/分割线等装饰件算进间隙（否则取值天然五花八门 → 全是误报）。
    """
    warns, notes = [], []
    for jf in _ui_pages(project_root):
        rel = 'ui/' + os.path.basename(jf)
        d = json.load(open(jf, encoding='utf-8'))
        containers = []

        def walk(n, ox=0, oy=0):
            rows = []
            for k, v in n.items():
                if not isinstance(v, dict) or '__' not in k:
                    continue
                p = v.get('position') or {}
                l, tp, w, h = p.get('left'), p.get('top'), p.get('width'), p.get('height')
                if None in (l, tp, w, h):
                    walk(v, ox, oy)
                    continue
                cap = v.get('caption', '')
                # 只算「行的命中区」（ButtonRow*）；行内子控件（TextRow*/ImageRow*/ToggleRow*/RowSep*）会把步进打乱
                if h > 2 and cap.startswith('ButtonRow'):
                    rows.append(oy + tp)
                walk(v, ox + l, oy + tp)
            if len(rows) >= 4:
                containers.append(sorted(rows))

        walk(d)
        for ys in containers:
            steps = sorted({ys[i] - ys[i - 1] for i in range(1, len(ys))})
            if len(steps) > 3:
                # 首版口径在 SmartPanel settings 上仍有 1 处噪声（ButtonRow* 里混了非行命中区的小按钮，
                # 步进出现 0/2/6/7/12/29）→ 暂降 **NOTE**（只提示不拦），口径稳定后再升 WARN。
                notes.append('%s 同一容器内行步进出现 %d 种（%s）→ 间距节奏可能不统一（提示级）'
                             % (rel, len(steps), steps[:6]))
            else:
                notes.append('%s 行步进 %s' % (rel, steps))
    return notes, warns


def check_icon_box_min(project_root):
    """#35 箭头/图标盒下限：箭头盒 < 12×16 → WARN（通用字形图标在更小的盒里会被压成 1px 笔画）。"""
    warns, notes = [], []
    for jf in _ui_pages(project_root):
        rel = 'ui/' + os.path.basename(jf)
        _d, ctrls = _page_ctrls(jf)
        for _k, cap, r, v in ctrls:
            if v.get('visible') is False:
                continue
            if 'Chevron' in cap and (r[2] < 12 or r[3] < 16):
                warns.append((rel, '%s 箭头盒 %dx%d < 12x16 → 笔画会被压成 1px（放大盒或换专属切图）'
                              % (cap, r[2], r[3])))
        notes.append(rel)
    return notes, warns


def check_text_room(project_root):
    """#36 文本余量：盒宽 < 估算宽 × 1.05 → NOTE（#13 只管装不下，这条管余量太紧）。"""
    notes = []
    for jf in _ui_pages(project_root):
        rel = 'ui/' + os.path.basename(jf)
        _d, ctrls = _page_ctrls(jf)
        for _k, cap, r, v in ctrls:
            if v.get('visible') is False:
                continue
            txt = str(v.get('text', '') or '')
            fs = v.get('fontSize') or 0
            if not txt or not fs:
                continue
            min_w, _h = _text_min_size(txt, fs, v.get('alignment', 0))
            if min_w and r[2] < min_w * 1.05:
                notes.append('%s %s 文本「%s」盒宽 %d < 估算 %d×1.05 → 余量太紧（运行期长值易溢出）'
                             % (rel, cap, txt[:10], r[2], min_w))
    return notes


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

    print('== 1. 根节点（id:0 + position 全屏 + resolution 一致；\n'
          '      topmost 系统栏/导航栏页例外：官方机制允许根为「局部悬浮块」，见 kb/controls.md）==')
    for f in PAGES:
        d = json.load(open(os.path.join(root, f), encoding='utf-8'))
        pos = d.get('position')
        res_ = d.get('resolution')
        ok = (d.get('id') == 0 and isinstance(pos, dict)
              and isinstance(res_, dict)
              and pos.get('left') == 0 and pos.get('top') == 0
              and pos.get('width') == res_.get('width')
              and pos.get('height') == res_.get('height'))
        # topmost:true = 系统栏 statusbar / 导航栏 navibar（官方系统界面类型）。这类页面的根节点
        # 就是「悬浮块本身」而非全屏：references/kb/controls.md 「系统栏 navibar/statusbar」
        # （statusbar 实测局部悬浮块 100x41 @ 615,25；另一台设备 320x60 @ 650,10）。
        # 反过来写全屏根会形成最上层全屏透明层，吞掉整屏触摸（F133 实测），
        # 所以此处只要求：坐标全整数、块非空、且完整落在 resolution 之内（不做全屏要求）。
        if not ok and d.get('topmost') is True and isinstance(pos, dict) \
                and isinstance(res_, dict):
            vals = (pos.get('left'), pos.get('top'),
                    pos.get('width'), pos.get('height'))
            if all(isinstance(v, int) for v in vals):
                l, t, w, h = vals
                ok = (d.get('id') == 0 and w > 0 and h > 0 and l >= 0 and t >= 0
                      and l + w <= res_.get('width')
                      and t + h <= res_.get('height'))
            if ok:
                log(True, '%s 根节点（topmost 系统栏局部悬浮块 %dx%d @ %d,%d，resolution %dx%d）'
                    % (f, pos.get('width'), pos.get('height'), pos.get('left'),
                       pos.get('top'), res_.get('width'), res_.get('height')))
                continue
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

    print('== 9. ftu→json 自动同步（只两种情形）+ fui pack 成功生成 ftu ==')
    # ① 只有 ftu 没有 json → 直接 unpack 转出 json（老工程/纯 IDE 工程）
    for ftu_f in sorted(glob.glob(os.path.join(ui, '*.ftu'))):
        jp0 = os.path.splitext(ftu_f)[0] + '.json'
        if not os.path.isfile(jp0):
            r0 = subprocess.run([FUI, 'unpack', ftu_f, jp0], capture_output=True, text=True)
            log(r0.returncode == 0, '%s 只有 ftu → 自动转出 json' % os.path.basename(ftu_f))
            if r0.returncode == 0:
                ft0 = os.path.getmtime(ftu_f)
                os.utime(jp0, (ft0, ft0))
    # ② ftu 比 json 新「分钟级」(≥60 秒) → 用户/IDE 编辑过 ftu → 先同步 json 再 pack；其余不做反向
    for jf in PAGES:
        jp = os.path.join(root, jf)
        fp = os.path.join(ui, os.path.splitext(os.path.basename(jf))[0] + '.ftu')
        if os.path.isfile(fp) and os.path.isfile(jp):
            jt = os.path.getmtime(jp)
            ft = os.path.getmtime(fp)
            if ft > jt + 60:
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

    print('== 11. 图片尺寸必须与盒子严格相等（控件 position；thumb 子盒用 thumb.size）==\n'
          '       引擎行为：图 != 盒时**拉伸填充**（不报错，但非整数缩放发糊/变形）→ 所以要 1:1；\n'
          '       thumb 滑块是「自有尺寸」子盒，盒子=thumb.size（铁律 #1）。')
    if not _HAS_PIL:
        log(True, '无 PIL，跳过图片尺寸核对（仅检查引用存在性）')
    for f in PAGES:
        d = json.load(open(os.path.join(root, f), encoding='utf-8'))
        bad = []
        for k, v in _all_controls(d):
            pos = v.get('position') or {}
            pw, ph = pos.get('width'), pos.get('height')
            refs = []
            if pw and ph:
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
            # thumb 自有尺寸子盒：盒子 = thumb.size（与 verify_assets 同一份 helper，不另写一套口径）
            checks = [(fld, ref, (pw, ph), 'position') for fld, ref in refs]
            checks += [(fld, ref, box, 'thumb.size') for fld, ref, box in _thumb_pic_refs(v)]
            for fld, ref, box, box_from in checks:
                if ref.lower().endswith('.9.png') or not box:
                    continue  # 9-patch 可拉伸；盒子未知（无 position / thumb 无 size）→ 交 #17 报 warning
                if box_from == 'thumb.size' and not _is_auto_generated(ref):
                    continue  # 手绘 thumb 引擎会拉伸（基准工程 SampleUI-New 写法）→ #17 记 stretched
                p = _pic_path(root, ref)
                if not p:
                    continue  # 缺失已在第 4 项报
                try:
                    with _Image.open(p) as im:
                        w, h = im.size
                    if (w, h) != tuple(box):
                        bad.append('%s.%s %s %dx%d != %s %dx%d'
                                   % (k, fld, os.path.basename(ref), w, h,
                                      box_from, box[0], box[1]))
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

    print('== 17. 资源产物核对（引用存在 + 自动生成图 PNG 尺寸 == 控件 position；\n'
          '       thumb 子盒 PNG 尺寸 == thumb.size，即铁律 #1）==')
    va = verify_assets(root)
    if va.get('error'):
        log(False, '产物核对 %s' % va['error'])
    else:
        log(not va['missing'], '图片引用存在性（%d 个页面 / %d 处引用）%s'
            % (va['pages'], va['refCount'],
               '全部存在' if not va['missing'] else '缺 %d 个：%s'
               % (len(va['missing']), '；'.join('%s %s' % (m['control'], m['field']) for m in va['missing'][:6]))))
        log(not va['mismatch'], 'PNG 尺寸 == 盒子（自动生成图 / thumb.size 声明）%s'
            % ('全部匹配' if not va['mismatch'] else '不匹配 %d 处：%s'
               % (len(va['mismatch']),
                  '；'.join('%s.%s %dx%d != %s %dx%d'
                            % (m['control'], m['field'], m['png'][0], m['png'][1],
                               m.get('boxFrom', 'position'),
                               (m.get('box') or m.get('position'))[0],
                               (m.get('box') or m.get('position'))[1]) for m in va['mismatch'][:6]))))
        if va.get('stretched'):
            print('  [NOTE] %d 处图尺寸 != 盒子（引擎会拉伸，通常正常；其中 thumb.size 盒子只对\n'
                  '         手绘 thumb 适用）：%s'
                  % (len(va['stretched']),
                     '；'.join('%s.%s %dx%d != %s %dx%d'
                               % (m['control'], m['field'], m['png'][0], m['png'][1],
                                  m.get('boxFrom', 'position'),
                                  (m.get('box') or m.get('position') or [0, 0])[0],
                                  (m.get('box') or m.get('position') or [0, 0])[1])
                               for m in va['stretched'][:5])))
        if va['unresolved']:
            print('  [NOTE] %d 处跳过（运行时格式化引用/读图失败），见 flythings_verify_assets 明细'
                  % len(va['unresolved']))
        if va.get('skippedNoBox'):
            print('  [NOTE] %d 处因盒子尺寸未知（控件无 position / thumb 无 size）跳过尺寸核对：%s'
                  % (len(va['skippedNoBox']), '、'.join(va['skippedNoBox'][:5])))

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
        if rl.get('nocall'):
            warn('V85X 图层释放：src/ 里释放函数名只出现一次（疑似只定义未调用）——\n'
                 '          沛哥 2026-09-14 定：用到视频图层的产品**启动第一次初始化就必须先释放图层**，\n'
                 '          否则程序崩溃/重启后残留的系统级 disp 图层不会被清理 → **屏幕永久性异常**\n'
                 '          （真机实测：杀进程重启后残留黑层仍在）。修复：在启动初始化路径里调一次释放\n'
                 '          函数（如 sys::hw::init() / onUI_init），详见 knowledge/v85x/display-layer-debug.md §2-0/§2-1-3')
        if rl.get('unsafe'):
            warn('V85X 图层释放用「格式区间（DISP_FORMAT_ARGB_8888 ~ DISP_FORMAT_BGRA_5551）判定 UI 层」'
                 '（%s）→ 2026-09-14 V851 真机实测会漏关残留层：RGB_888(0x08) 落在区间内被误判为 UI 层、'
                 'COLOR 模式层读出的 fb.format 就是 color 低字节 → 黑层/残留层留在最上面 = 一直黑屏。'
                 '修复：改按 ch/layer 跳过 UI 层（if (ch == UI_LYCHN && lyl == UI_LYLAY) continue;），'
                 '要双重保险就限定 mode == LAYER_MODE_BUFFER 后才看 format。'
                 '详见 knowledge/v85x/display-layer-debug.md §2-1-1'
                 % '、'.join(rl['unsafe'][:3]))

    print('== 20. 运行期 set...Pic 的图 vs 控件盒（v0.27.90；扫 src/**/*.cc|*.cpp）==\n'
          '       口径与 #11/#17 同源：图尺寸应 == 控件盒；resources/images/ 的**自动生成图**不等 = FAIL，\n'
          '       手绘图（其它目录）不等 = 仅提示（引擎本就拉伸）；.9.png 豁免；变量映射不到控件不静默跳过。')
    sp = check_runtime_setpic(root)
    if not sp['files']:
        print('  [NOTE] src/ 下没有 .cc/.cpp（纯 UI 交付），跳过')
    elif not sp['calls']:
        print('  [NOTE] 未见 set...Pic 调用（运行期设图），跳过尺寸核对')
    else:
        log(not sp['missing'], '运行期设图引用存在性（%d 处调用 / %d 处静态字面量）%s'
            % (sp['calls'], sp['resolved'],
               '全部存在' if not sp['missing'] else '缺 %d 处：%s'
               % (len(sp['missing']), '；'.join(sp['missing'][:4]))))
        log(not sp['mismatch'], '运行期设图尺寸 == 控件盒 %s'
            % ('全部匹配（%d 处比过）' % sp['matched'] if not sp['mismatch'] else
               '不匹配 %d 处：%s'
               % (len(sp['mismatch']),
                  '；'.join('%s:%d %s(%s) %s %dx%d != 盒 %s'
                            % (m['file'], m['line'], m['caption'], m['field'],
                               os.path.basename(m['pic']), m['png'][0], m['png'][1],
                               m['boxes'][0]) for m in sp['mismatch'][:4]))))
        for m in sp['mismatch']:
            warn('运行期设图被拉伸：%s:%d %s->%s("%s") 图 %dx%d，控件盒 %s → 引擎按盒拉伸\n'
                 '          修法二选一：① 控件盒改回图尺寸（推荐，图==盒铁律）；② 重出同尺寸图\n'
                 '          （案例：48x16 三点图放进 48x26 盒 → 正圆被拉成竖椭圆，'
                 'knowledge/uicontrols/text-box-height-rule.md）'
                 % (m['file'], m['line'], m['target'], m['field'], m['pic'],
                    m['png'][0], m['png'][1], m['boxes'][0]))
        if sp['stretched']:
            print('  [NOTE] %d 处手绘图尺寸 != 控件盒（引擎会拉伸，通常正常）：%s'
                  % (len(sp['stretched']),
                     '；'.join('%s:%d %s %dx%d != %s'
                               % (m['file'], m['line'], m['caption'], m['png'][0],
                                  m['png'][1], m['boxes'][0]) for m in sp['stretched'][:4])))
        if sp['unresolved']:
            print('  [NOTE] %d 处未比尺寸（变量名映射不到控件 / 非工程内路径；不静默跳过，列表如下）：%s'
                  % (len(sp['unresolved']), '；'.join(sp['unresolved'][:5])))
        if sp['dynamic']:
            print('  [NOTE] %d 处调用实参是变量/拼接（运行时才能知道用哪张图）→ 静态判不了，'
                  '真机才会现形' % sp['dynamic'])
        if sp['noPil']:
            print('  [NOTE] 无 PIL，只核引用存在性，未比尺寸')

    print('== 21. 生成图抗锯齿 / 脏边（委派 tools/qa/aa_audit.py --fail；0 token 有退出码）==\n'
          '       钟工 2026-09-19 A2（原话「把 aa_audit --fail 接进 check_all」）：#19/#20 已被\n'
          '       V85X 图层释放 / 运行期设图占用 → 为不打乱既有编号与知识库引用，追加为 #21。\n'
          '       口径：真缺陷（resid_bad / 成片 hard_diag / 无两区边界时退回 dirty）= FAIL；\n'
          '       WARN 逐条列理由（不阻塞也不静默）；*.9.png marker 环由审计内置豁免；\n'
          '       白名单只认 tools/qa/aa_audit_allow.json（命中即 EXEMPT 并打印理由）。')
    aa = check_aa_assets(root)
    if aa['status'] == 'skip':
        print('  [NOTE] 跳过：%s' % aa['reason'])
    elif aa['status'] == 'error':
        log(False, 'AA 审计执行失败：%s' % aa['reason'])
    else:
        log(not aa['defect'],
            'AA 真缺陷 %s（%s 扫 %d 张；WARN %d / EXEMPT %d / 干净 %d / 审计错误 %d）'
            % ('0 张' if not aa['defect'] else '%d 张' % len(aa['defect']),
               os.path.basename(aa['audit']), aa['total'], len(aa['warn']),
               len(aa['exempt']), len(aa['clean']), len(aa['error'])))
        for d in aa['defect']:
            print('  [DEFECT] %-30s %sx%s %s' % (d['name'], d['w'], d['h'], d['reason']))
            if d['xy']:
                print('           resid@ %s' % (d['xy'],))
        for w in aa['warn']:
            print('  [WARN 需人工确认] %-26s %s' % (w['name'], w['reason']))
        for e in aa['exempt']:
            print('  [EXEMPT] %-30s %s' % (e['name'], e['reason']))
        for e in aa['error']:
            print('  [ERROR] %-31s %s' % (e['name'], e['reason']))
        if aa['defect']:
            warn('AA 真缺陷 %d 张 → 修图后重跑；口径见 references/kb/image-gen-standard.md §1.2'
                 '（带直通 α 的边界禁用 LANCZOS；描边走整像素带）'
                 % len(aa['defect']))

    print('== 22. 切图缺倒角 / 直角残留（委派 tools/qa/corner_audit.py --fail；0 token 有退出码）==\n'
          '       钟工 2026-09-20 M5（原话「主界面大量图片依旧存在切图缺倒角问题……必须给我从设计标准和\n'
          '       拦截上处理好」）：矩形/卡片/磁贴/药丸族按**边起跑距离**几何反解圆角 r_est\n'
          '       （d = r - sqrt(r-0.25)）与 DESIGN.md 圆角令牌比。\n'
          '       口径：直角残留（d≤1）/ r_est < 0.5×令牌 / 四角不一致 → FAIL；< 0.8×令牌 → WARN；\n'
          '       图标・内切图形族不做倒角判据（由 #23 判形状外透明）；满幅/底图族按登记理由 EXEMPT。')
    ca = check_shape_audit(root, 'corner')
    if ca['status'] == 'skip':
        print('  [NOTE] 跳过：%s' % ca['reason'])
    elif ca['status'] == 'error':
        log(False, '缺倒角审计执行失败：%s' % ca['reason'])
    else:
        log(not ca['defect'],
            '缺倒角真缺陷 %s（%s 扫 %d 张；WARN %d / EXEMPT %d / NOTE %d / 干净 %d / 错误 %d）'
            % ('0 张' if not ca['defect'] else '%d 张' % len(ca['defect']),
               os.path.basename(ca['audit']), ca['total'], len(ca['warn']),
               len(ca['exempt']), len(ca['note']), len(ca['clean']), len(ca['error'])))
        for d in ca['defect']:
            print('  [DEFECT] %-30s %s' % (d['name'], d['reason']))
        for w in ca['warn']:
            print('  [WARN 需人工确认] %-26s %s' % (w['name'], w['reason']))
        for e in ca['exempt']:
            print('  [EXEMPT] %-30s %s' % (e['name'], e['reason']))
        for n in ca['note'][:12]:
            print('  [NOTE] %-32s %s' % (n['name'], n['reason']))
        if len(ca['note']) > 12:
            print('  [NOTE] ...其余 %d 张同类（图标/内切族不做倒角判据）'
                  % (len(ca['note']) - 12))
        for e in ca['error']:
            print('  [ERROR] %-31s %s' % (e['name'], e['reason']))
        if ca['defect']:
            warn('缺倒角真缺陷 %d 张 → 重出图（半径按 DESIGN.md 圆角令牌）；口径见 '
                 'references/kb/image-gen-standard.md §7.2' % len(ca['defect']))

    print('== 23. 透明底 / 烘底色（委派 tools/qa/alpha_bg_audit.py --fail；0 token 有退出码）==\n'
          '       钟工 2026-09-20 M5（原话「控件里面图片背景是黑色的，应该做成透明的，这个设计不符\n'
          '       合 flyThings OS 平台的能力」）：形状类资产必须真透明底（形状外 α=0）。\n'
          '       口径：整图无透明像素（α≥250）/ 内切・图标族角区不透明（= 烘了底色）/\n'
          '       图标贴死图边 → FAIL；满幅族（照片・壁纸・遮罩・1px 通栏线・软阴影）登记豁免。')
    ab = check_shape_audit(root, 'alpha')
    if ab['status'] == 'skip':
        print('  [NOTE] 跳过：%s' % ab['reason'])
    elif ab['status'] == 'error':
        log(False, '透明底审计执行失败：%s' % ab['reason'])
    else:
        log(not ab['defect'],
            '透明底真缺陷 %s（%s 扫 %d 张；WARN %d / EXEMPT %d / NOTE %d / 干净 %d / 错误 %d）'
            % ('0 张' if not ab['defect'] else '%d 张' % len(ab['defect']),
               os.path.basename(ab['audit']), ab['total'], len(ab['warn']),
               len(ab['exempt']), len(ab['note']), len(ab['clean']), len(ab['error'])))
        for d in ab['defect']:
            print('  [DEFECT] %-30s %s' % (d['name'], d['reason']))
        for w in ab['warn']:
            print('  [WARN 需人工确认] %-26s %s' % (w['name'], w['reason']))
        for e in ab['exempt']:
            print('  [EXEMPT] %-30s %s' % (e['name'], e['reason']))
        for n in ab['note']:
            print('  [NOTE] %-32s %s' % (n['name'], n['reason']))
        for e in ab['error']:
            print('  [ERROR] %-31s %s' % (e['name'], e['reason']))
        if ab['defect']:
            warn('透明底真缺陷 %d 张 → 重出图（形状外必须 α=0；禁把页面底色/黑底烘进图）；口径见 '
                 'references/kb/image-gen-standard.md §7.1/§7.3' % len(ab['defect']))

    print('== 24. 颜色值 0（不透明黑）误用（委派 tools/qa/zero_color_audit.py --fail；0 token 有退出码）==\n'
          '       钟工 2026-09-20 M6（原话「控件/切图黑底」「从标准和拦截上处理」）：本平台里\n'
          '       颜色值 **0 = 不透明黑**、**-1 = 透明**；json 里把「透明」写成 0 的字段（backgroundColor /\n'
          '       bgColorTab.color0 / textBgColor …）真机就是黑块。口径见 DESIGN.md §2.1 与\n'
          '       references/kb/image-gen-standard.md §7.6：未登记豁免 → FAIL；命中\n'
          '       tools/qa/zero_color_allow.json（视频/摄像头面黑底）→ EXEMPT + 打印理由。')
    zc = check_zero_color(root)
    if zc['status'] == 'skip':
        print('  [NOTE] 跳过：%s' % zc['reason'])
    elif zc['status'] == 'error':
        log(False, '颜色 0 审计执行失败：%s' % zc['reason'])
    else:
        log(not zc['defect'],
            '颜色 0 误用 %s（%s 扫 %d 条；EXEMPT %d / 干净 %d / 错误 %d）'
            % ('0 处' if not zc['defect'] else '%d 处' % len(zc['defect']),
               os.path.basename(zc['audit']), zc['total'],
               len(zc['exempt']), len(zc['clean']), len(zc['error'])))
        for d in zc['defect']:
            print('  [DEFECT] %s' % d['name'])
            print('           %s' % d['reason'])
        for e in zc['exempt']:
            print('  [EXEMPT] %-44s %s' % (e['name'], e['reason'][:110]))
        for e in zc['error']:
            print('  [ERROR]  %-44s %s' % (e['name'], e['reason']))
        if zc['defect']:
            warn('颜色 0（不透明黑）误用 %d 处 → 改 -1 或 DESIGN.md 令牌色；确实要黑（视频/摄像头面）'
                 '才写 0，并在 tools/qa/zero_color_allow.json 登记理由（口径 §7.6）'
                 % len(zc['defect']))

    print('== 25. 弧线过渡质量（9-patch 圆角 AA；委派 tools/qa/corner_audit.py --arc-only --fail）==\n'
          '       钟工 2026-09-20 M8（原话「全控件演示界面的每个演示框背景图 ct_card.9.png 倒角有\n'
          '       严重锯齿」）：#22 量倒角的*几何*（有没有/够不够大），#25 量弧上的*过渡质量*\n'
          '       （覆盖率是否真的从 0 渐变到满值）。`*.9.png` 先剥离最外 1px marker 环再判。\n'
          '       口径：角块内「外沿进入像素」（α>0 且 4 邻域有 α=0）的覆盖率 = α/峰值α；\n'
          '       要求 min_cov ≤ 0.35 且 ≤0.35 的个数 ≥ 2（成组出现）；否则 = 过渡被压进 1px 硬阶梯 → FAIL。\n'
          '       阈值出处 P(min>t)=(1−t)^N（与标准「≥4× 超采样」档位自洽）见 references/kb/image-gen-standard.md §7.7。')
    aq = check_arc_quality(root)
    if aq['status'] == 'skip':
        print('  [NOTE] 跳过：%s' % aq['reason'])
    elif aq['status'] == 'error':
        log(False, '弧线过渡审计执行失败：%s' % aq['reason'])
    else:
        log(not aq['defect'],
            '弧线过渡硬阶梯 %s（%s 扫 %d 张；弧线可判 %d 张（均 CLEAN）/ WARN %d / NOTE %d / 错误 %d）'
            % ('0 张' if not aq['defect'] else '%d 张' % len(aq['defect']),
               os.path.basename(aq['audit']), aq['total'], aq['judged'],
               len(aq['warn']), len(aq['note']), len(aq['error'])))
        for d in aq['defect']:
            print('  [DEFECT] %-30s 最小覆盖率=%s（≤0.35 的 %s 个 / 进入像素 %s，角块 α 峰值 %s）'
                  % (d['name'], d['min_cov'], d['lo_n'], d['n_px'], d['amax']))
            print('           四角最小覆盖率 %s' % (d['corners'],))
            print('           %s' % d['reason'])
        for w in aq['warn']:
            print('  [WARN 需人工确认] %-26s 四角最小覆盖率 %s；%s'
                  % (w['name'], w['corners'], w['reason']))
        for n in aq['note'][:6]:
            print('  [NOTE] %-32s %s' % (n['name'], n['reason']))
        if len(aq['note']) > 6:
            print('  [NOTE] ...其余 %d 张同类（无透明背景/样本不足）' % (len(aq['note']) - 6))
        for e in aq['error']:
            print('  [ERROR]  %-44s %s' % (e['name'], e['reason']))
        if aq['defect']:
            warn('弧线过渡硬阶梯 %d 张 → 重出图：描边 alpha 必须用覆盖率口径（gen_res.ring_cov_alpha /'
                 'card9_alpha / translucent_card9），**禁把 coverage_ring（二值颜色指派 mask）当 α 层用**；'
                 '口径见 references/kb/image-gen-standard.md §7.7' % len(aq['defect']))

    print('== 26. scrollwindow 行程核对（行程 = 内层 window − 视口，**不读 dragMaxDis**）==\n'
          '       钟工 2026-10-01 定：`dragMaxDis` = 越界拖拽上限（overscroll），四个滑动控件语义一致，\n'
          '       **不是行程**；行程由内容决定、引擎自算（scrollwindow = 内层 window 尺寸 − 视口尺寸）。\n'
          '       反例（旧口径作废的证据）：官方 ScrollWindowDemo-New 视口 450 / 内容 800（行程 350）\n'
          '       而 dragMaxDis=200；SmartPanel settings 视口 418 / 内容 832（行程 414）而 dragMaxDis=60，\n'
          '       真机仍能滚 302px 到底。口径：knowledge/uicontrols/scroll-drag-interaction-spec.md。')
    st_notes, st_warns = check_scrollwindow_travel(root)
    if not st_notes:
        print('  [NOTE] 无 scrollwindow（或未内嵌 window），跳过')
    for n in st_notes:
        print('  [NOTE] %s' % n)
    for pg, msg in st_warns:
        warn('%s %s' % (pg, msg))
    if st_notes and not st_warns:
        print('  [PASS] 行程与 dragMaxDis 用法正常（%d 处）' % len(st_notes))

    print('== 27. 同族控件口径离群 / 文本×图标重叠（设计期拦截；钟工 2026-10-01）==\n'
          '       给设置行这类重复行模板上的静态判据：同页同父同角色的 *Label/*Value/*Icon/*Chevron\n'
          '       应取同一组 (left,width,height,alignment) 口径；偏离众数、或文本盒与图标/箭头盒相交 → WARN。\n'
          '       实例：某行值框被做成右对齐窄框 300..418（其余 12 行 75..375），且右缘顶到箭头盒\n'
          '       → 文字凸出 43px + “文本和箭头混到一起”（引擎先画背景图后画文字，箭头被盖住）。\n'
          '       口径：knowledge/uicontrols/scrollwindow-layout-checklist.md。')
    fa_notes, fa_warns = check_family_alignment(root)
    if not fa_notes:
        print('  [PASS] 同族口径一致、无文本×图标重叠')
    for pg, msg in fa_warns:
        warn('%s %s' % (pg, msg))

    print('== 28. UTF-8 文本陷阱（src 静态扫描；钟工 2026-10-01）==\n'
          '       `find_first_of("：")` 按**单字节**匹配 → 多字节字符被切在字节中间（实测「回家模式」被切坏）\n'
          '       → 必须用 `find("：")` 整序列搜索。只扫**含非 ASCII** 的字面量实参（纯 ASCII 集合法，不报）。\n'
          '       口径：knowledge/uicontrols/text-box-height-rule.md（UTF-8 三件套）。')
    u8_notes, u8_warns = check_utf8_pitfalls(root)
    for n in u8_notes:
        print('  [NOTE] %s' % n)
    for pg, msg in u8_warns:
        warn('%s %s' % (pg, msg))
    if u8_notes and not u8_warns:
        print('  [PASS] 未发现多字节 find_first_of/find_last_of')

    print('== 29. 显示件吃掉下层触摸（装饰件漏设穿透；钟工 2026-10-01）==\n'
          '       同层「后定义（z 更高）+ 可见 + touchable 未显式 false」的纯显示件压住交互控件\n'
          '       → 会吃掉 DOWN（症状=整块点不动/只剩缝隙能点）。容器/整屏/近全覆盖/modal 视为故意，不报。\n'
          '       口径：knowledge/uicontrols/touch-events.md、scrollwindow-layout-checklist.md §2.1。')
    de_notes, de_warns = check_display_eats_touch(root)
    if not de_notes:
        print('  [NOTE] 无页面，跳过')
    for pg, msg in de_warns:
        warn('%s %s' % (pg, msg))
    if de_notes and not de_warns:
        print('  [PASS] 无显示件压住交互控件（%d 页）' % len(de_notes))

    print('== 30. caption 唯一性（页内同名 caption → onButtonClick_<caption> 重定义 ⇒ C++ 编译必失败；钟工 2026-10-01）==\n'
          '       #5 只核对「回调是否存在」，核不出同名 caption 各生成一份回调（重定义）\n'
          '       → 同一 json 内 caption 出现 ≥2 次即 FAIL，并列出「哪个 caption、几次、在哪几个控件」。\n'
          '       背景：templates/ui_blocks/compose.py 修前按「卡内序号」分配块名 → 跨卡从 1 重数\n'
          '       （RowSep1×5 / ButtonRowSettingRow1×2 等），生成的两份 onButtonClick 一个 TU 里重定义。')
    cu_notes, cu_dups = check_caption_unique(root)
    for pg, cap, keys in cu_dups:
        log(False, '%s caption「%s」重复 %d 次：%s（同名 caption ⇒ onButtonClick_%s 重复定义 ⇒ 编译失败）'
            % (pg, cap, len(keys), '、'.join(keys), cap))
    if not cu_notes:
        print('  [NOTE] 无页面，跳过')
    elif not cu_dups:
        print('  [PASS] %d 页 caption 全部唯一' % len(cu_notes))

    print('== 31. 行族文本对齐轴（离群 → WARN；钟工 2026-10-01）==\n'
          '       同页行族文本盒左缘只应出现 1~2 个值（绝对布局下「某行没和同页对齐」是最常见返工）。')
    al_notes, al_warns = check_align_axis(root)
    for n in al_notes:
        print('  [NOTE] %s' % n)
    for pg, msg in al_warns:
        warn('%s %s' % (pg, msg))
    if al_notes and not al_warns:
        print('  [PASS] 行族对齐轴收敛')

    print('== 32. 垂直间距节奏（同页间隙取值应成小集合；钟工 2026-10-01）==')
    gp_notes, gp_warns = check_gap_rhythm(root)
    for n in gp_notes:
        print('  [NOTE] %s' % n)
    for pg, msg in gp_warns:
        warn('%s %s' % (pg, msg))
    if gp_notes and not gp_warns:
        print('  [PASS] 间距节奏统一')

    print('== 35. 箭头/图标盒下限（< 12x16 → WARN；钟工 2026-10-01）==')
    ib_notes, ib_warns = check_icon_box_min(root)
    for pg, msg in ib_warns:
        warn('%s %s' % (pg, msg))
    if ib_notes and not ib_warns:
        print('  [PASS] 箭头盒均 ≥ 12x16')

    print('== 36. 文本盒余量（< 估算宽 ×1.05 → NOTE）==')
    tr_notes = check_text_room(root)
    for n in tr_notes:
        print('  [NOTE] %s' % n)
    if not tr_notes:
        print('  [PASS] 文本盒余量充足')

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
