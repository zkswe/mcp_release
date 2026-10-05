#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 规格指针（DESIGN_SPEC 第 1.1 条）：本文件的转换口径实现 `ui_schema.json.renderContract` 的
# `pic-scale` / `progress-clip` / `thumb-size` / `alpha-compose` / `edge-aa` / `stroke-aa` /
# `nine-patch` / `rounding` / `no-root-bg`。改贴图语义或 AA 口径前先看那几条。
"""受限 HTML → FlyThings JSON 布局转换器（通用工具 v1，不随项目复制）

用途：HTML 交互原型（首版界面）→ 直接转成 ui/*.json 布局，
再 fui pack 生成 ftu 交付设备端。替代每个项目手写 Builder/JSON。

用法：
    python html2json.py <input.html> [output.json|输出目录] [--res WxH] [--merge-windows]

多屏（HTML 内多个 div.screen）默认口径（2026-09-21 口径，见 knowledge/devflow/page-architecture-spec.md）：
**一个 .screen = 一个页面 = 一个 Activity = 一个独立 json（-> 一个独立 ftu）**；
N 屏 -> N 个 json，文件名取 data-page（缺省 page_k），输出目录 = 输出参数所写目录。
同屏内部的 window / dialog（弹窗）不是页，直接写在 .screen 里（div.window / div.modal）。
- --merge-windows：N 屏合成同一 json 内的 N 个整屏 window（键 window__1..window__N 连续编号，
首屏 visible:true、其余 visible:false，切页走 showWnd/hideWnd）—— **仅当这些屏同属一个 Activity
  （同 ftu 内整屏 window）**时才用。工具不主动把多个 .screen 合成多窗口。
**页数 = 屏数**：screensDetected != pagesProduced 一律 success:false + error（不静默丢页）。

受限 HTML 规范见 HTML_SUBSET.md（元素/class → FlyThings 控件映射表）。
核心规则自动内建：
- 控件键 `类型__N` 全局递增；ID 按类型分区；颜色十进制
- 多屏 .screen：缺省每屏一个 json（一页一 Activity 一 ftu）；--merge-windows 才合并成多整屏 window
- window 子控件嵌套其内（相对坐标）；弹窗 modal:true + visible:false
- Z 序 = HTML 文档顺序（后定义在上层，弹窗最后）
- 空文本不写 text 字段；edittext 自动 beepEnable/hintTextColor
- ✅ 纯黑 #000000 按「属性出现性」判定（A2 修，2026-09-27）：data-color/data-color2/data-bg/
  data-text-bg/data-hint-color 全走 `_color_explicit()`，不再被 `or 默认值` 吞掉；老工程
  「纯黑写 #010101」的绕过写法继续有效（#010101 也是纯黑，不必回改）
- ✅ 支持 `data-visible`（A5 修）：任意控件/容器（含 subItem、window）初始隐藏，直通 json 的 visible
- ✅ 转换期静默改动一律进返回体 warnings（A1/A8 修）：丢字符（emoji/黑名单字）、有图控件
无圆角外底色、文本最小宽超出容器等不再靠真机反推
- ✅ 有图控件的圆角外底色（A6 修）：data-bg > 最近祖先容器底色 > 引擎缺省（无底色时告警）
- ✅ **最小 CSS 层叠**（2026-10-04）：读 `<style>` 块的 tag/.class/#id/后代/逗号分组选择器，
  按 inline > specificity > 靠后规则折进元素 style 属性 → 位置/渐变/圆角/阴影才有得读
  （此前 CSS 写在 `<style>` 里一律读不到：控件位置全丢成 (0,0,100×40) 且**零警告**）
- ✅ **进度条三件套自动出图**（2026-10-04，真机归因实测）：`.bar/.progress` + `.fill` 子元素 +
  `.thumb` 子元素 → 轨道/有效/滑块三张切图，尺寸规则**各不相同**（详见 `_seekbar_css_assets` 注释）；
  进度值可取自 CSS（`--value:60%` / `.fill` 的 `width:60%`）；`<input type=range>` 认成 seekbar；
  `html/body` 的 background 传播到 json 根（不写根底色 = 真机不擦屏、残留上一帧）
- ✅ 不可实现项一律点名（不许硬转、也不许假声明）：伪元素 `::-webkit-slider-thumb`、
  有效图右端圆角（引擎硬切）、`.fill` 自身宽度的渐变、`inset` 内阴影、底色与轨道同色会把圆角补平

⚠️ 设备端渲染路径差异（不是转换器问题，见 references/kb/image-gen-standard.md）：运行时 setBackgroundPic 不保留 alpha（透明底 PNG 会变白块）—— 运行时换图那套素材需烘不透明底。
"""
import html as html_lib
import json
import os
import re
import sys
from html.parser import HTMLParser

# 自动转图：CSS 效果（渐变/圆角/阴影/图标/loading）→ PNG/.9.png/序列帧（gen_res.py）
try:
    import gen_res as gr
    _HAS_GEN_RES = True
except Exception:
    gr = None
    _HAS_GEN_RES = False

# CSS 效果自动出图档位（2026-09-16 拍板）：**一律走 SS**，不再保留 1x + α 羽化那条路。
# SS_DEFAULT = 4 = 每像素 16 子采样（SS mask / SS 圆角 / SS 阴影层全部走这个档）。
# 手写调用（gen_res.rounded_rect / ss=0 默认）行为不变 —— 这里只影响 html2json 出的图。
_CSS_SS = getattr(gr, 'SS_DEFAULT', 4) if _HAS_GEN_RES else 4

# ---------- ID 分区（SKILL §2.3 需求方版） ----------
# ⚠️ **两条硬约束带**（`ui_tools/check_all.py` #5 是按 id 段推断回调的，不是口味问题）：
#   · `20000 <= id < 30000` ⇒ 必须有 `onButtonClick_<caption>`；
#   · `51000 <= id < 52000` ⇒ 必须有 `onEditTextChanged_<caption>`。
# 所以**非 button / 非 edittext 类型一律不许落在上面两条带里** —— 否则静态全检会要求一个
# 语义错误的回调（checkbox 的语义回调是 onCheckedChanged）。2026-10-05 修正三处（实测驱动）：
#   · checkbox   21000 → **94500**（仓内实测 94502；`templates/ui_blocks/compose.py` 也取 94500）
#   · radiobutton 22000 → **94100**（同上；落在 button 带里会被 #5 当成按钮）
#   · slidetext   51000 → **98000**（落在 edittext 带里会被 #5 要求 onEditTextChanged）
# `subitem = 24000` 虽在 button 带内但**无害**：check_all 的 `by_caption` 只递归 dict、不遍历数组，
# 数组子项（subItem/radiobuttons）根本不进 #5。
ID_BASE = {
    'textview': 50000, 'button': 20000, 'edittext': 51000,
    'seekbar': 91000, 'window': 110000, 'listview': 80000,
    'checkbox': 94500, 'radiogroup': 94000, 'radiobutton': 94100,
    'subitem': 24000, 'imageanim': 160000,
    'circlebar': 130000, 'diagram': 60000, 'digitalclock': 93000,
    'slidewindow': 30000, 'scrollwindow': 32000, 'pagewindow': 31000,
    'slidetext': 98000, 'cameraview': 97000, 'painter': 52000,
    'pointer': 90000, 'qrcode': 92000, 'videoview': 95000,
}

# HTML class 关键字 → FlyThings 控件类型
CLASS_MAP = {
    'textview': ('text', 'tv', 'label', 'txt'),
    'button': ('btn', 'button', 'b'),
    'edittext': ('input', 'edit', 'edittext'),
    'seekbar': ('bar', 'seekbar', 'progress', 'slider', 'range'),
    'window': ('card', 'window', 'win', 'panel'),
    'modal': ('modal', 'dialog', 'popup'),
    'listview': ('list', 'listview', 'lv'),
    'checkbox': ('checkbox', 'check', 'cb'),
    'radiogroup': ('radio', 'radiogroup', 'rg'),
    'icon': ('icon', 'img', 'image', 'pic', 'iconfont'),
    'circlebar': ('circlebar', 'circular', 'ring'),
    'diagram': ('diagram', 'wave', 'chart'),
    'digitalclock': ('digitalclock', 'clock', 'time'),
    'imageanim': ('imageanim', 'anim', 'gif'),
    'slidewindow': ('slidewindow', 'slide', 'launcher'),
    'scrollwindow': ('scrollwindow', 'scrollwin', 'scroll'),
    'pagewindow': ('pagewindow', 'page', 'pager'),
    'slidetext': ('slidetext', 'candidate', 'cand'),
    'cameraview': ('cameraview', 'camera'),
    'painter': ('painter', 'canvas', 'draw'),
    'pointer': ('pointer', 'gauge', 'dial'),
    'qrcode': ('qrcode', 'qr'),
    'videoview': ('videoview', 'video'),
}

# 全部「控件 class」的并集（判「这个 div 写的是控件还是图标项/纯装饰」用；见 slidewindow 子项判据）
_CTRL_CLASSES = frozenset(c for keys in CLASS_MAP.values() for c in keys)
# 绝对定位键（写了它 = 作者以为在摆控件；slidewindow 内会被丢弃 → 不静默）
_POS_ATTRS = ('data-x', 'data-y', 'data-w', 'data-h')

# 对齐：left/center/right → alignment（36 左中 / 37 居中 / 38 右中）
ALIGN = {'left': 36, 'center': 37, 'right': 38, 'l': 36, 'c': 37, 'r': 38}

# 自动 caption 前缀（缺 data-caption 时）
AUTO_NAME = {
    'textview': 'TextView', 'button': 'Button', 'edittext': 'EditText',
    'seekbar': 'SeekBar', 'window': 'Window', 'listview': 'ListView',
    'checkbox': 'CheckBox', 'radiogroup': 'RadioGroup', 'icon': 'ImageView',
}


def to_dec(color):
    """'#RRGGBB' / '0xRRGGBB' / 'RRGGBB' / 十进制 → 十进制 int；失败返回 None。"""
    if color is None:
        return None
    s = str(color).strip()
    if not s:
        return None
    try:
        if s.startswith('#'):
            return int(s[1:], 16)
        if s.lower().startswith('0x'):
            return int(s, 16)
        return int(s)
    except Exception:
        return None


def parse_px(v):
    # 兼容裸数字（data-x="16"）与带单位（data-x="16px"）两种写法
    m = re.match(r'^([\d.]+)(?:px?)?$', str(v).strip())
    return int(float(m.group(1))) if m else None


def _num(v, default=0):
    """数值属性（可带 px/小数/负数）：data-step="10" / "10.0" / "5px" / "-120"；整数返回 int，小数返回 float。"""
    if v is None:
        return default
    try:
        s = str(v).strip()
        m = re.match(r'^(-?[\d.]+)(?:px?)?$', s)
        if not m:
            return default
        f = float(m.group(1))
        return int(f) if f == int(f) else f
    except Exception:
        return default


def _style_pos(style):
    """从 style="left:10px;top:20px;width:100px;height:30px" 提取 position。"""
    pos = {}
    for k in ('left', 'top', 'width', 'height'):
        m = re.search(r'(?:^|;)\s*%s\s*:\s*([^;]+)' % k, style or '')
        if m:
            v = parse_px(m.group(1))
            if v is not None:
                pos[k] = v
    return pos


def _attr(attrs, name, default=None):
    for k, v in attrs:
        if k.lower() == name.lower():
            return v
    return default


def _classes(attrs):
    return set((_attr(attrs, 'class') or '').split())


# iconfont 图标语义提取（2026-09-03 需求方定规：图标优先）
# HTML 写法：data-icon="play" 或 class="iconfont icon-play" / class="icon icon-play"
_ICON_CLASS_RE = re.compile(r'^icon-(.+)$')


def _glyph_from_attrs(attrs):
    """从 data-icon 或 icon-xxx class 提取图标语义名；无则返回 None。
规范：返回/播放/暂停/设置/搜索/删除等常用操作必须用图标（data-icon），
禁止纯文字按钮糊弄；图标名与中文别名映射见 gen_res（back/返回/play/播放...）。"""
    v = _attr(attrs, 'data-icon')
    if v:
        v = str(v).strip()
        if v:
            return v
    for k in _classes(attrs):
        m = _ICON_CLASS_RE.match(k)
        if m and m.group(1):
            return m.group(1)
    return None


def _px_num(v):
    """CSS 长度 → 数值：'4px'/'4'/'4.5em'/'50%' → float；非法返回 None。
    ⚠️ 2026-09-10 修 bug：原先 int(float('4px')) 抛 ValueError，被 except 静默吞掉，
导致「标准 CSS 写 px 的 box-shadow 一律转图失败、且报误导性提示」。"""
    m = re.match(r'^\s*(-?\d+(?:\.\d+)?)\s*(?:px|em|rem|pt|%)?\s*$', str(v))
    return float(m.group(1)) if m else None


def _shadow_spec(style):
    """box-shadow → (ox, oy, blur, (r,g,b,a))；解析不了返回 None。
兼容 px/em/rem/%/无单位、inset/outset、4 值 spread、色值写在任意位置。"""
    m = re.search(r'box-shadow\s*:\s*([^;]+)', style or '')
    if not m:
        return None
    raw = m.group(1).strip()
    if not raw or raw.lower().startswith('none'):
        return None
    toks = [t for t in raw.split() if t.lower() not in ('inset', 'outset')]
    nums = []
    for t in toks:
        if len(nums) >= 3:
            break
        v = _px_num(t)
        if v is None:
            break
        nums.append(v)
    if len(nums) < 3:
        return None
    col = None
    for t in toks[len(nums):]:
        c = _css_color(t)
        if c:
            col = c
            break
    return (int(nums[0]), int(nums[1]), int(abs(nums[2])), col or (0, 0, 0, 80))


def _radius_px(style, w, h, default=0):
    """CSS border-radius → 圆角像素（单一 radius，按 min(w,h)//2 钳制 → 药丸/正圆自动生效）。

支持 px / 无单位 / **%（50% → 正圆/药丸）**；`8px 8px 0 0` 这类多值取第一段；
解析不到返回 default（渐变分支 0 / 阴影分支 8，历史默认不变）。
    ⚠️ 2026-09-16（v0.27.76）：旧实现只认「数字+px」正则 → `border-radius:50%` / 无单位
一律认不出 → 该出圆的地方出方角（SS 也就无从生效）。与「CSS 效果出图一律 SS」同批收口。
    """
    m = re.search(r'border-radius\s*:\s*([^;]+)', style or '')
    raw = m.group(1).strip().split()[0] if (m and m.group(1).strip()) else ''
    if not raw:
        v = default
    elif raw.endswith('%'):
        try:
            v = float(raw[:-1]) / 100.0 * min(w, h)
        except ValueError:
            v = default
    else:
        num = _px_num(raw)
        v = default if num is None else num
    return max(0, min(int(round(v)), min(w, h) // 2))


def _shadow_pad(ox, oy, blur):
    """阴影画布外扩量（必须与 gen_res.gen_shadow_card 内部 pad 公式一致）。"""
    return max(2, int(blur) + max(abs(int(ox)), abs(int(oy))))


def _grow(pos, pad):
    """控件盒按阴影溢出量 pad 外扩：left/top 前移、宽高各 +2*pad。
这样「图片尺寸 == 控件尺寸」（check_all #11），且可见卡片主体仍落在作者给定坐标。"""
    pad = int(pad)
    pos['left'] = pos.get('left', 0) - pad
    pos['top'] = pos.get('top', 0) - pad
    pos['width'] = pos.get('width', 100) + pad * 2
    pos['height'] = pos.get('height', 40) + pad * 2


def _color_int_rgba(cint, default=None):
    """十进制颜色 int → (r,g,b,255)；失败返回 default。"""
    if cint is None:
        return default
    try:
        cint = int(cint)
        if 0 <= cint <= 0xFFFFFF:
            return ((cint >> 16) & 0xFF, (cint >> 8) & 0xFF, cint & 0xFF, 255)
    except Exception:
        pass
    return default


def _detect_type(tag, classes, attrs=None):
    """HTML 标签 + class → FlyThings 控件类型。
    2026-09-03 扩展：btn/button 类 + data-icon/iconfont → button（图标按钮，生成两态图）；
纯 iconfont/icon-xxx → icon（图标 textview）。
    2026-10-04 扩展：`<input type="range">` → seekbar（AI 写滑条最常用的原生控件；
此前一律当 edittext —— 那是个"点不动的输入框"，而且 `::-webkit-slider-thumb` 的样式全丢）。"""
    has_btn = bool(classes & set(CLASS_MAP['button'])) or tag == 'button'
    has_icon = bool(classes & set(CLASS_MAP['icon'])) or any(k.startswith('icon-') for k in classes)
    if attrs is not None and _glyph_from_attrs(attrs):
        if has_btn:
            return 'button'
        if has_icon:
            return 'icon'
    for typ, keys in CLASS_MAP.items():
        for k in keys:
            if k in classes:
                return typ
    if tag == 'button':
        return 'button'
    if tag == 'input':
        if (_attr(attrs or [], 'type') or '').strip().lower() == 'range':
            return 'seekbar'
        return 'edittext'
    if tag == 'img':
        return 'icon'
    if tag in ('p', 'span', 'h1', 'h2', 'h3', 'label', 'div', 'i'):
        return 'textview'
    if tag in ('ul', 'ol'):
        return 'listview'
    return 'textview'


# ---------- CSS 效果解析（自动转图）----------
_CSS_COLOR_NAMES = {
    'black': (0, 0, 0), 'white': (255, 255, 255), 'red': (255, 0, 0),
    'green': (0, 128, 0), 'lime': (0, 255, 0), 'blue': (0, 0, 255),
    'yellow': (255, 255, 0), 'orange': (255, 165, 0), 'gray': (128, 128, 128),
    'grey': (128, 128, 128), 'transparent': None,
}


def _css_color(s):
    """CSS 颜色 → (r,g,b,a)；#RGB/#RRGGBB/rgb()/rgba()/颜色名。失败返回 None。"""
    s = (s or '').strip().lower()
    if not s:
        return None
    if s.startswith('#'):
        h = s[1:]
        try:
            if len(h) == 3:
                h = ''.join(c * 2 for c in h)
            if len(h) == 6:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
            if len(h) == 8:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))
        except Exception:
            return None
    m = re.match(r'rgba?\(([^)]+)\)', s)
    if m:
        parts = [p.strip() for p in m.group(1).split(',')]
        try:
            r, g, b = (int(float(p)) for p in parts[:3])
            a = int(float(parts[3]) * 255) if len(parts) > 3 else 255
            return (r, g, b, a)
        except Exception:
            return None
    return _CSS_COLOR_NAMES.get(s)


def _parse_gradient(expr):
    """linear-gradient(...) 内部表达式 → (horizontal, [(pos, color), ...])。
支持 to right/left/top/bottom、角度(0/90/180/270deg)、多色标（含百分比）。"""
    expr = (expr or '').strip()
    horizontal = False
    m = re.match(r'^\s*(to\s+\w+|\d+deg)\s*,\s*(.*)$', expr, re.S)
    if m:
        direction = m.group(1)
        expr = m.group(2)
        if 'right' in direction or direction.startswith('90'):
            horizontal = True
        elif 'left' in direction or direction.startswith('270'):
            horizontal = True
        elif direction.startswith('0') or 'top' in direction:
            horizontal = False
        else:
            horizontal = False
    stops = []
    for part in re.split(r',(?![^(]*\))', expr):
        part = part.strip()
        if not part:
            continue
        pm = re.match(r'^(.*?)\s*(\d+(?:\.\d+)?)%\s*$', part)
        if pm:
            color = _css_color(pm.group(1).strip())
            if color:
                stops.append((float(pm.group(2)) / 100.0, color))
        else:
            color = _css_color(part)
            if color:
                stops.append((None, color))
    # 无百分比色标：均匀分布
    colors = [c for _, c in stops]
    if len(colors) >= 2:
        if all(p is None for p, _ in stops):
            return horizontal, [(i / (len(colors) - 1), c) for i, c in enumerate(colors)]
    return horizontal, stops


# ---------- 最小 CSS 层叠（<style> 块 + 类选择器 → 元素 style 属性）----------
# 为什么必须补（2026-10-04 真机归因实测）：`_style_pos` / `_effect_assets` / `_warn_css_effects`
# **全部只读元素上的 style 属性**，而 AI 写的 HTML 常规是把布局与效果放在 <style> 块 + 类选择器里
# → 转换器读不到：控件位置全丢成 (0,0,100×40)、渐变/圆角一个都不出图，而且**零警告**
#（连"CSS 效果"检测也只读 style 属性）。本段把这层按最小层叠折进 style 属性，
# 既有消费方（位置/渐变/阴影/圆角）无需改动即可生效。
_CSS_COMMENT_RE = re.compile(r'/\*.*?\*/', re.S)
_CSS_SEL_UNSUPPORTED_RE = re.compile(r'[\[\]>+~]')
_CSS_TOK_RE = re.compile(r'^(\*|[A-Za-z][\w-]*)?((?:[.#][\w-]+)*)((?:::{1,2}[\w-]+)*)$')
# 认得的**伪元素**（双冒号，或 CSS2.1 的单冒号 before/after 写法）。
# `::-webkit-slider-thumb` 这类是「正常 HTML 滑条」的标准写法 —— 引擎没有伪元素，
# 但它们承载的**信息**（滑块尺寸/底色/描边、轨道高度/底色）正是 seekbar 的三张切图，
# 所以必须解析出来交给 `_seekbar_css_assets` 消费，而不是像伪类那样直接丢掉。
_CSS_PSEUDO_ELEMENTS = frozenset((
    'before', 'after', 'marker', 'placeholder', 'selection', 'backdrop', 'file-selector-button',
    'webkit-slider-thumb', 'webkit-slider-runnable-track', 'webkit-slider-container',
    'moz-range-thumb', 'moz-range-track', 'moz-range-progress',
))


def _parse_css_rules(css_text):
    """极简 CSS 解析 → [(parts, decls, spec)]。

    parts = [(tag, frozenset(classes), id, pseudo), ...]（后代选择器链，由外到内；
    pseudo = 该段挂的伪元素名，普通段为 None）；
    spec  = (ids, classes, tags, order) —— 层叠排序用（order 保证同优先级时后写的胜）。
    只支持：tag / `.class` / `#id` / `tag.class` / 多类 / 后代（空格）/ 逗号分组 / **伪元素** / `*`。
    带伪**类**（`:hover`/`:focus`/`:checked`/`:disabled`）的选择器整条忽略 —— 那是运行期状态，
    FlyThings 靠 picTab 多态图表达，不是静态布局。
    `*` 认成通配段（层叠优先级 0）—— 因为 `* { box-sizing: border-box }` 这种 reset 极常见，
    不认它就会把滑块的盒模型算错（2026-10-04 实测：content-box 与 border-box 的外框差 2×border）。
    """
    out = []
    if not css_text:
        return out
    text = _CSS_COMMENT_RE.sub(' ', css_text)
    order = 0
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', text):
        sel_raw, body = m.group(1).strip(), m.group(2).strip()
        if not body or not sel_raw or sel_raw.startswith('@'):
            continue
        order += 1
        for sel in sel_raw.split(','):
            if not sel.strip():
                continue
            parts, ok = [], True
            for tok in sel.split():
                if _CSS_SEL_UNSUPPORTED_RE.search(tok):
                    ok = False
                    break
                mm = _CSS_TOK_RE.match(tok)
                if not mm or not (mm.group(1) or mm.group(2)):
                    ok = False
                    break
                pseudo = None
                for piece in re.findall(r'::?[\w-]+', mm.group(3) or ''):
                    # ⚠️ 必须同时去掉前导 `-`：`::-webkit-slider-thumb` 的名字是
                    # `webkit-slider-thumb`，只 lstrip(':') 会留下 `-webkit-…`（对不上 _PS_* 候选表）。
                    name = piece.lstrip(':-')
                    if piece.startswith('::') or name in _CSS_PSEUDO_ELEMENTS:
                        pseudo = name          # 取最后一个伪元素
                    else:
                        ok = False             # 单冒号伪类（:hover/:focus/:checked…）不支持
                        break
                if not ok:
                    break
                classes, cid = set(), ''
                for piece in re.findall(r'[.#][\w-]+', mm.group(2) or ''):
                    if piece[0] == '.':
                        classes.add(piece[1:])
                    else:
                        cid = piece[1:]
                parts.append(((mm.group(1) or '').lower(), frozenset(classes), cid, pseudo))
            # 末段必须有 tag/class/id：否则 `::-webkit-slider-thumb{…}` 这种裸伪元素规则
            # 会匹配到**所有**节点（把滑块样式糊到每个控件上）。
            if ok and parts and (parts[-1][0] or parts[-1][1] or parts[-1][2]):
                out.append((parts, body,
                            (sum(1 for p in parts if p[2]),
                             sum(len(p[1]) for p in parts),
                             sum(1 for p in parts if p[0] or p[3]), order)))
    return out


def _css_part_match(part, node):
    tag, classes, cid = part[0], part[1], part[2]
    if tag and tag != '*' and node.tag != tag:
        return False
    if classes and not classes <= _classes(node.attrs):
        return False
    if cid and (_attr(node.attrs, 'id') or '') != cid:
        return False
    return True


def _css_matches(parts, node, ancestors):
    """后代选择器匹配：node 合最后一段，ancestors（由外到内）依次合前面的段。"""
    if not _css_part_match(parts[-1], node):
        return False
    need = list(parts[:-1])
    i = len(ancestors) - 1
    while need and i >= 0:
        if _css_part_match(need[-1], ancestors[i]):
            need.pop()
        i -= 1
    return not need


def _set_style_attr(node, value):
    """把合并后的声明写回 style 属性（替换第一个同名属性、丢弃多余的同名属性）。"""
    out, done = [], False
    for k, v in node.attrs:
        if k.lower() == 'style':
            if not done:
                out.append((k, value))
                done = True
            continue
        out.append((k, v))
    if not done:
        out.append(('style', value))
    node.attrs = out


def _apply_css(root, css_text, pseudo_out=None):
    """把 <style> 声明按最小层叠折进各节点的 style 属性；返回写入的节点数。

    排序口径：inline > specificity 高 > 靠后的规则。消费者（`_style_pos` / `_radius_px` /
    `_shadow_spec` / 渐变与背景正则）一律用 `re.search` 取**第一个**匹配，所以优先级高的必须排在
    **前面** → inline 声明排最前（原行为 = inline 生效，不许变）。

    pseudo_out：可选 dict，收 `{id(node): {伪元素名: 声明串}}` —— 伪元素的声明**不能**并进节点的
    style（`::-webkit-slider-thumb{height:32px}` 混进去会把控件本身写成 32 高），
    必须单独存，由 `_seekbar_css_assets`（`_pseudo_style`）按名字取。
    """
    rules = _parse_css_rules(css_text)
    if not rules:
        return 0
    n = 0

    def walk(node, ancestors):
        nonlocal n
        hit, ps = [], {}
        for parts, body, spec in rules:
            if not _css_matches(parts, node, ancestors):
                continue
            name = parts[-1][3]
            if name:
                ps.setdefault(name, []).append((spec, body))
            else:
                hit.append((spec, body))
        if hit:
            hit.sort(key=lambda t: t[0], reverse=True)
            merged = ';'.join(b.strip().rstrip(';') for _, b in hit if b.strip())
            inline = (_attr(node.attrs, 'style') or '').strip().rstrip(';')
            if merged:
                _set_style_attr(node, (inline + ';' + merged) if inline else merged)
                n += 1
        if ps and pseudo_out is not None:
            bucket = pseudo_out.setdefault(id(node), {})
            for name, lst in ps.items():
                lst.sort(key=lambda t: t[0], reverse=True)
                txt = ';'.join(b.strip().rstrip(';') for _, b in lst if b.strip())
                if txt:
                    old = bucket.get(name) or ''
                    bucket[name] = (old + ';' + txt) if old else txt
        for ch in node.children:
            walk(ch, ancestors + [node])

    walk(root, [])
    return n


# ---------- CSS 背景 / 边框 / 圆角 / 进度值（进度条出图用）----------
_COV_SS_LOCAL = getattr(gr, '_COV_SS', 16) if _HAS_GEN_RES else 16


def _style_len(style, key):
    """style 里 key 的**绝对像素**长度 → int 或 None。`%` / auto / inherit 一律 None
    （引擎只吃绝对像素；`width:50%` 认成 50 会是灾难性误读）。"""
    m = re.search(r'(?:^|;)\s*%s\s*:\s*([^;]+)' % key, style or '')
    if not m:
        return None
    raw = m.group(1).strip()
    if raw.endswith('%') or raw.lower() in ('auto', 'inherit', 'initial', 'unset'):
        return None
    v = _px_num(raw)
    return int(round(v)) if v is not None else None


def _style_len_ref(style, key, ref):
    """同 `_style_len`，但 `%` 按 ref 解析 —— 进度条最常见的写法就是 `width:100%`。

    没有布局引擎，只能拿**最近容器**（这里是 .screen 的分辨率）当参照，并按此告警说明。
    """
    m = re.search(r'(?:^|;)\s*%s\s*:\s*([^;]+)' % key, style or '')
    if not m:
        return None
    raw = m.group(1).strip()
    if raw.lower() in ('auto', 'inherit', 'initial', 'unset'):
        return None
    if raw.endswith('%'):
        try:
            return int(round(float(raw[:-1]) / 100.0 * ref))
        except ValueError:
            return None
    v = _px_num(raw)
    return int(round(v)) if v is not None else None


def _parse_gradient_dual(expr):
    """linear-gradient 内部表达式 → (horizontal, [(pos|None, rgba), ...])。

    比 `_parse_gradient` 多认 **CSS Color 4 双位置色标**（`#F00 0 60%` = 两个色标），
    这是「一条硬停靠渐变表达已有进度」的关键写法：
        background: linear-gradient(to right, #2E8BFF 0 60%, #242F49 60% 100%);
    逐个 part 展开，`color A% B%` → [(A, c), (B, c)]。
    """
    expr = (expr or '').strip()
    horizontal = False
    m = re.match(r'^\s*(to\s+\w+|\d+deg)\s*,\s*(.*)$', expr, re.S)
    if m:
        d, expr = m.group(1), m.group(2)
        horizontal = ('right' in d) or ('left' in d) or d.startswith('90') or d.startswith('270')
    stops = []
    for part in re.split(r',(?![^(]*\))', expr):
        part = part.strip()
        if not part:
            continue
        nums = []
        col = None
        for tok in re.split(r'\s+', part):
            if not tok:
                continue
            if col is None:
                c = _css_color(tok)
                if c is not None:
                    col = c
                    continue
            m = re.match(r'^(-?\d+(?:\.\d+)?)\s*(%?)$', tok)
            if m:
                nums.append(float(m.group(1)) / 100.0 if m.group(2) else float(m.group(1)))
        if not col:
            continue
        if len(nums) >= 2:
            stops.append((nums[0], col))
            stops.append((nums[1], col))
        elif len(nums) == 1:
            stops.append((nums[0], col))
        else:
            stops.append((None, col))
    if stops and all(p is None for p, _ in stops) and len(stops) >= 2:
        stops = [(i / (len(stops) - 1.0), c) for i, (_, c) in enumerate(stops)]
    return horizontal, stops


def _seg_style(stops, renorm):
    """一段色标 → 可直接喂给 `_bar_pic` 的 style 串（同色 → 纯色；否则 linear-gradient）。

    renorm=False 保留原位置：有效图会被引擎按进度裁剪，**保留原位置才对得上浏览器**
    （浏览器里那段渐变就是画在 0..p 上的）。
    renorm=True 归一化到 0..1：轨道图**不裁剪**，必须让整张图都是「停靠点之后」的颜色。
    """
    cols = {tuple(c[:3]) for _, c in stops}
    if len(cols) == 1:
        r, g, b = next(iter(cols))
        return 'background:#%02X%02X%02X' % (r, g, b)
    pos = [p for p, _ in stops if p is not None]
    if renorm and pos:
        lo, hi = min(pos), max(pos)
        span = max(1e-6, hi - lo)
        stops = [((p - lo) / span if p is not None else None, c) for p, c in stops]
    body = ', '.join('#%02X%02X%02X%s' % (c[0], c[1], c[2],
                                         (' %.4f' % p) if p is not None else '')
                     for p, c in stops)
    return 'background:linear-gradient(to right, %s)' % body


def _replace_bg(style, bg):
    """把 style 里的 `background`/`background-color`/`background-image` 换成 bg，**其余声明保留**
    （圆角 / 高度 / 边框都在其余声明里 —— 早期版本直接拿拆分结果当整条 style，把 `border-radius`
    丢了，真机上药丸轨道变成方头，2026-10-04 真机比对抓到）。"""
    rest = re.sub(r'(?:^|;)\s*background(?:-color|-image)?\s*:\s*[^;]+', '', style or '')
    rest = re.sub(r';{2,}', ';', rest).strip('; ')
    return (bg + ';' + rest) if rest else bg


def _split_fill_track(style):
    """轨道上的**硬停靠渐变** → (fill_bg, track_bg, frac) 或 None（只回背景声明，不碰其它字段）。

    为什么必须有（2026-10-04）：Chrome 里 `input[type=range]` **没有**填充伪元素
    （那是 Firefox 的 `::-moz-range-progress`），所以「已有进度」的常规画法就是把填充做成
    轨道背景上一段硬停靠渐变。不拆它，正常 HTML 转出来的进度条**只有轨道、没有填充**。
    """
    m = re.search(r'linear-gradient\(([^)]+)\)', style or '')
    if not m:
        return None
    hz, stops = _parse_gradient_dual(m.group(1))
    if len(stops) < 2 or not hz:
        return None
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        if (p0 is not None and p1 is not None and abs(p0 - p1) < 1e-6
                and tuple(c0[:3]) != tuple(c1[:3]) and 0.0 < p0 < 1.0):
            return (_seg_style(stops[:i + 1], False),
                    _seg_style(stops[i + 1:], True), p0)
    return None


def _bg_spec(style):
    """style 的背景 → ('gradient', (horizontal, stops)) / ('color', (r,g,b,a)) / None。

    优先级与 CSS 一致：能解析的 linear-gradient 优先，否则退回 background(-color) 的第一个颜色。
    """
    m = re.search(r'linear-gradient\(([^)]+)\)', style or '')
    if m:
        hz, stops = _parse_gradient(m.group(1))
        if len(stops) >= 2:
            return ('gradient', (hz, stops))
    m = re.search(r'background(?:-color)?\s*:\s*([^;]+)', style or '')
    if m:
        for tok in m.group(1).strip().split():
            c = _css_color(tok)
            if c:
                return ('color', c)
    return None


def _box_sizing(style, default):
    """`box-sizing` → 'content-box' / 'border-box'；没写用 default。

    ⚠️ 为什么必须读（2026-10-04 实测，Chrome 无头截图对照）：
      - **普通元素**（`.thumb` div）CSS 默认 `content-box` → `width:32px;height:32px;border:3px`
        的真实外框是 **38×38**、白芯 32（实测）；
      - **滑条伪元素** `::-webkit-slider-thumb` Chrome 按 **border-box** 画 → 外框 32、白芯 24（实测）。
    所以我按「来源」给不同默认值：伪元素 border-box、子元素 content-box；作者显式写了就以作者为准。
    """
    m = re.search(r'box-sizing\s*:\s*([a-z-]+)', style or '')
    v = m.group(1).strip().lower() if m else ''
    return v if v in ('content-box', 'border-box') else default


def _thumb_outer_size(style, tw, th, default_box='border-box'):
    """滑块**外框**（border box）尺寸 → (W, H, border_w)。

    真机按 PNG 原尺寸画滑块，所以 PNG 就是这个外框；`thumb.size` 也要写这个值。
    """
    bw, _ = _border_spec(style) or (0, None)
    if bw and _box_sizing(style, default_box) == 'content-box':
        return tw + 2 * bw, th + 2 * bw, bw
    return tw, th, bw


def _border_spec(style):
    """`border: 3px solid #2A3550` → (3, (r,g,b,a))；没有宽度/颜色 → None。"""
    m = re.search(r'(?:^|;)\s*border\s*:\s*([^;]+)', style or '')
    if not m:
        return None
    w, col = None, None
    for tok in m.group(1).split():
        v = _px_num(tok)
        if w is None and v is not None:
            w = int(round(v))
            continue
        if col is None:
            col = _css_color(tok)
    if not w or w <= 0:
        return None
    return (w, col or (0, 0, 0, 255))


def _radius_corners(style, w, h):
    """`border-radius` → 四角像素 (tl, tr, br, bl)，按 CSS 语法展开（1/2/3/4 值，取斜杠前的水平半径）。

    与 `_radius_px` 分开实现（那个只取第一段、返回单一半径，供渐变/阴影分支用，行为不许变）：
    `border-radius: 8px 8px 0 0`（AI 写"只圆上面两角"的常态）在单一 radius 口径下会被误当成四角 8。
    """
    m = re.search(r'border-radius\s*:\s*([^;]+)', style or '')
    if not m:
        return (0.0, 0.0, 0.0, 0.0)
    ref = min(w, h)

    def one(t):
        if t.endswith('%'):
            try:
                return float(t[:-1]) / 100.0 * ref
            except ValueError:
                return 0.0
        v = _px_num(t)
        return 0.0 if v is None else float(v)

    vals = [one(t) for t in m.group(1).split('/')[0].split()] or [0.0]
    if len(vals) == 1:
        tl = tr = br = bl = vals[0]
    elif len(vals) == 2:
        tl = br = vals[0]
        tr = bl = vals[1]
    elif len(vals) == 3:
        tl, tr, br, bl = vals[0], vals[1], vals[2], vals[1]
    else:
        tl, tr, br, bl = vals[:4]
    lim = min(w, h) / 2.0
    return tuple(max(0.0, min(v, lim)) for v in (tl, tr, br, bl))


def _corners_mask_local(w, h, radii, ss=None):
    """四角半径**各不相同**时的覆盖率 mask：SS 二值画布 → `Image.BOX` 面积平均缩回
    （与 gen_res 覆盖率口径同一套，无负瓣）。

    `gen_res.coverage_mask` / PIL 的 `rounded_rectangle` 都只吃**单一** radius，所以四角不同只能自己拼。
    画法刻意与 PIL 的 `rounded_rectangle` 同构：每个角 = 「2r×2r 角方块清零 + **圆心在该方块中点**
    的 1/4 圆盘（pieslice）填回」。
    ⚠️ 圆心必须在内侧（方块中点），不是画布角点 —— 早期版本把圆心放在角点上，等于把「圆内」和
    「圆外」画反，四角会变成全实心（测试 test_four_corner_radius_is_per_corner 抓到）。
    """
    from PIL import Image as _I
    from PIL import ImageDraw as _D
    ss = int(ss or _COV_SS_LOCAL) or 1
    W, H = max(1, w * ss), max(1, h * ss)
    m = _I.new('L', (W, H), 0)
    d = _D.Draw(m)
    d.rectangle([0, 0, W - 1, H - 1], fill=255)
    corners = ((0, 0, 1, 1, 180, 270),            # 左上
               (W - 1, 0, -1, 1, 270, 360),       # 右上
               (W - 1, H - 1, -1, -1, 0, 90),     # 右下
               (0, H - 1, 1, -1, 90, 180))        # 左下
    for (ax, ay, sx, sy, a0, a1), r in zip(corners, radii):
        rr = int(round(float(r) * ss))
        if rr <= 0:
            continue
        x0, x1 = sorted((ax, ax + sx * 2 * rr))
        y0, y1 = sorted((ay, ay + sy * 2 * rr))
        box = [x0, y0, x1, y1]        # 2r×2r：圆心 = 方块中点
        d.rectangle(box, fill=0)
        d.pieslice(box, a0, a1, fill=255)
    return m.resize((w, h), _I.BOX)


def _corners_mask(w, h, radii, ss=None, band=None):
    """四角半径统一 → 直接走 `gen_res.coverage_mask`（与全项目同一份 AA 口径）；否则自己拼。

    band=(y0, bh)：**可见条只占盒子的一段高度**（`::-webkit-slider-runnable-track{height:12px}`
    但控件盒 32 高 —— 正常 HTML 滑条就是这个形态）。此时先把条按 bh 做出来，再贴进
    (w,h) 的透明画布，上下留真透明 —— 这正是 `seekbar-fields.md` §3 的「可见条居中、上下透明」口径。
    """
    y0, bh = band if band else (0, h)
    if y0 == 0 and bh >= h:
        lo, hi = min(radii), max(radii)
        if hi - lo < 1e-6 and _HAS_GEN_RES:
            return gr.coverage_mask(w, h, radii[0])
        return _corners_mask_local(w, h, radii, ss)
    from PIL import Image as _I
    inner = (gr.coverage_mask(w, bh, radii[0]) if (_HAS_GEN_RES and max(radii) - min(radii) < 1e-6)
             else _corners_mask_local(w, bh, radii, ss))
    out = _I.new('L', (w, h), 0)
    out.paste(inner, (0, max(0, min(int(y0), h - bh))))
    return out


def _bar_pic(out_dir, name, w, h, style, default_color=None, band=None):
    """CSS 背景（纯色/linear-gradient）+ `border-radius` → 一张 **w×h** 切图。轨道图与有效图共用。

    ⚠️ 尺寸为什么恒等于控件盒（2026-10-04 真机实测，两条引擎行为相反）：
      - **轨道图** `backgroundPic`：引擎把它**拉伸填满控件盒**（实测 224×32 的图放进 448×32 盒 → 段宽 ×2）；
      - **有效图** `progressPic`：引擎**1:1 原样贴 + 按进度横向裁剪，不缩放**（实测三色段图 100×32
        在 60% 进度下只显示源图前 100 列，多出来的 168px 直接露轨道）。
        → 所以有效图也必须出成控件盒宽，否则进度一超过图片宽度，那一段就是空的。
    band=(y0, bh)：可见条居中那套（见 `_corners_mask`）。
    """
    if not _HAS_GEN_RES:
        return None
    spec = _bg_spec(style)
    if spec is None:
        if default_color is None:
            return None
        spec = ('color', default_color)
    radii = _radius_corners(style, w, h if not band else band[1])
    if spec[0] == 'gradient':
        hz, stops = spec[1]
        # 渐变 RGB 逐列插值直接复用 gen_res（同一份实现，别抄第二份）；只把 alpha 换成四角 mask
        p = gr.gen_gradient_stops(out_dir, name, w, h, stops, horizontal=hz, radius=0, ss=_CSS_SS)
        if not p:
            return None
        from PIL import Image as _I
        im = _I.open(p).convert('RGBA')
        im.putalpha(_corners_mask(w, h, radii, band=band))
        return _save_css_png(im, out_dir, name)
    fill = spec[1]
    from PIL import Image as _I
    im = _I.new('RGBA', (w, h), (fill[0], fill[1], fill[2], 255))
    im.putalpha(_corners_mask(w, h, radii, band=band))
    return _save_css_png(im, out_dir, name)


# css 导出切图的编码记录（`_save_css_png` 写、`convert()` 汇总成一条 warning 后清空）。
_PNG_LOG = []


def _I_new_rgba(w, h, rgba):
    """新建一张 RGBA 图（半透明热区切图用；RGB 写**背后底色**而不是黑，
    这样万一设备端贴图把透明区的 RGB 带出来，漏出来的也是底色而不是黑边）。"""
    from PIL import Image as _I
    return _I.new('RGBA', (max(1, int(w)), max(1, int(h))), tuple(rgba))


def _I_open(path):
    """打开图片（.9.png 出图后要重新编码成 8bit 索引色时用）。"""
    from PIL import Image as _I
    return _I.open(path)


def _trim_png_palette(path):
    """把 PNG 的 PLTE / tRNS 裁到「实际用到的最大索引 + 1」项 —— 省存储的关键一步。

    PNG 允许调色板短于 256 项（PLTE 长度只要是 3 的倍数且索引不越界即可），
    但 PIL 保存 P 图时**固定写满 768B 调色板** → 小图索引化反而比 RGBA 更大
    （实测 32x32 滑块：P8 1081B vs RGBA 842B）。裁掉未使用的尾部项后同一张图 ≈ 380B。
    只重写 PLTE/tRNS 两块的字节与 CRC，IDAT 原样搬（索引没变，安全）。
    返回裁掉多少字节（0 = 没裁/不适用）。
    """
    import struct
    try:
        with open(path, 'rb') as f:
            raw = f.read()
    except OSError:
        return 0
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        return 0
    from PIL import Image as _I
    try:
        with _I.open(path) as im:
            if im.mode != 'P':
                return 0
            maxidx = max(im.tobytes()) if im.width * im.height else 0
    except Exception:
        return 0
    keep = min(256, int(maxidx) + 1)
    out, i, before, after = [raw[:8]], 8, len(raw), 0
    while i + 8 <= len(raw):
        ln = struct.unpack('>I', raw[i:i + 4])[0]
        typ = raw[i + 4:i + 8]
        data = raw[i + 8:i + 8 + ln]
        if typ == b'PLTE' and ln > keep * 3:
            data = data[:keep * 3]
        elif typ == b'tRNS' and ln > keep:
            data = data[:keep]
        elif typ == b'IHDR':
            if len(data) >= 9 and data[8] != 8:      # 非 8bit 位深不动（避免越界）
                return 0
        chunk = struct.pack('>I', len(data)) + typ + data
        out.append(chunk + struct.pack('>I', __import__('zlib').crc32(typ + data) & 0xffffffff))
        i += 12 + ln
        if typ == b'IEND':
            break
    blob = b''.join(out)
    if len(blob) >= before:
        return 0
    with open(path, 'wb') as f:
        f.write(blob)
    after = len(blob)
    return before - after


def _save_css_png(img, out_dir, name):
    """把一张 RGBA 图存成 **8bit 索引色 PNG**（省存储）—— 精确调色板 + tRNS 逐档 alpha。

    口径（2026-10-04 需求方要求「这些 css 导出的 png 全部采用 8bit png 减少存储空间」）：
      - **索引色 = 8 bit/像素**（PIL mode `P`），用色数 ≤256 时按**实际颜色逐个建调色板 →
        完全无损**（AA 的灰阶与 alpha 档一个字节都不丢）；
      - 调色板按实际用色数写（PIL 默认固定 768B 表 + 256B tRNS，小图反而更大 ——
        实测 448x32 纯色图：RGBA 607B → 全表 P8 **1293B**；裁剪后 **337B，−44%**）；
        tRNS 尾部全不透明的项也裁掉；
      - 用色数 > 256（真渐变）→ 只能量化，**与 RGBA 比体积谁小用谁**，并把数字记账回报（不静默）。
        实测 448x32 两色渐变 170 色：P8 1016B > RGBA 688B → 保留 RGBA。

    返回 PNG 绝对路径；过程写进 `_PNG_LOG` 供 `convert()` 汇总。
    """
    from PIL import Image as _I
    os.makedirs(out_dir, exist_ok=True)
    p8 = os.path.join(out_dir, name)
    rgba_probe = os.path.join(out_dir, '.__rgba_probe_' + name)
    img.save(rgba_probe, optimize=True)
    n_rgba = os.path.getsize(rgba_probe)
    n_p8 = 0
    ndist = 0
    try:
        cols = img.getcolors(256)              # None = 用色数 >256（真渐变）
        if cols:
            ndist = len(cols)
            cols.sort(key=lambda t: t[1])
            idx = {c: i for i, (_, c) in enumerate(cols)}
            pal, trns = [], []
            for _, c in cols:
                pal += [c[0], c[1], c[2]]
                trns.append(c[3])
            while len(trns) > 1 and trns[-1] == 255:
                trns.pop()                     # 尾部不透明的项不必写进 tRNS
            q = _I.new('P', img.size)
            q.putpalette(pal + [0] * (768 - len(pal)))
            src = img.load()
            q.putdata([idx[src[x, y]] for y in range(img.height) for x in range(img.width)])
            q.save(p8, optimize=True, transparency=bytes(trns))
            _trim_png_palette(p8)              # PLTE/tRNS 裁到实际用色数（否则小图反而更大）
            n_p8 = os.path.getsize(p8)
    except Exception:
        n_p8 = 0
    if n_p8 and n_p8 <= n_rgba:
        try:
            os.remove(rgba_probe)
        except OSError:
            pass
        _PNG_LOG.append((name, 'p8', n_rgba, n_p8, ndist))
        return p8
    # 索引化不可用 / 不划算 → 保留 RGBA（并记账，不静默）
    os.replace(rgba_probe, p8)
    _PNG_LOG.append((name, 'rgba', n_rgba, n_rgba, ndist))
    return p8


def _bordered_thumb(w, h, radius, fill, border, border_w):
    """描边 + 填充的圆/圆角块 —— 覆盖率抗锯齿 + **透明区颜色外溢（alpha bleed）**。
    为什么不用 `gen_res.bordered_cov`（2026-10-04 真机 + 浏览器对照实测）：
    那个用的是「整像素描边带」（阈值化 mask：`a_out≥1` 且 `a_in≤254`）→ 描边内边界是**硬边**。
    实测我生成的滑块 PNG 中行像素是 `#2A3550 ×4 → #E8F1FF`（**一个过渡像素都没有**），
    而浏览器同一个滑块有 `(224,234,249)` 这类混合像素 → 真机上圆钮**明显锯齿**。

    为什么**底色铺描边色、只有内区填填充色**（2026-10-04 需求方报「设备端 thumb 倒角处有白边」）：
    引擎贴图时 α 与 RGB **都**取自 PNG。若整幅铺填充色（本例是白 #E8F1FF）：
      - 圆外透明区 RGB = 白 → 引擎合成不完美时**漏白边**；
      - 更实质的是：圆外 AA 像素的 RGB 被算成 `描边×环覆盖率 + 白×(1−环覆盖率)`（偏亮），
        而 α 只有一点点 → 实测真机该像素 = 填充色里混进 ~12% 白（`(68,149,251)` vs 填充 `(46,139,255)`），
        肉眼就是**倒角白边**。
    正确构造（直通 α 贴图的标准做法）：
      - **RGB = 该像素「不透明时应有的颜色」**：描边区=描边色，内区=填充色（内边界仍按覆盖率在 RGB 里抗锯齿）；
      - **α = 外轮廓覆盖率**（圆外 0、圆内 1）。
      圆外底色即描边色 = **alpha bleed**：漏出来的是与描边同色的深色（看不出来），
      外边缘像素 RGB=描边色 + α=覆盖率 → 引擎混合结果与浏览器一致。
    """
    from PIL import Image as _I
    outer = gr.coverage_mask(w, h, radius)
    bw = int(border_w)
    base = border if (bw > 0 and border is not None) else fill
    img = _I.new('RGBA', (w, h), (base[0], base[1], base[2], 255))
    if bw > 0 and border is not None:
        inner = gr.coverage_mask(w, h, max(0.0, radius - bw),
                                 rect=(bw, bw, max(bw, w - 1 - bw), max(bw, h - 1 - bw)))
        img.paste(_I.new('RGBA', (w, h), (fill[0], fill[1], fill[2], 255)), (0, 0), inner)
    img.putalpha(outer)
    return img


def _thumb_pic(out_dir, name, tw, th, style, default_box='border-box'):
    """CSS 滑块 → 一张切图，尺寸 = **按 CSS 盒模型算出的外框**（真机按 PNG 原尺寸画）。

    三条口径都按「HTML 实际情况」来（2026-10-04 实测对照）：
      ① **盒模型**：`width/height` + `border` 的真实外框由 `box-sizing` 决定 ——
         `content-box`（CSS 默认，普通元素）→ 外框 = w+2bw × h+2bw（实测 32+3px → **38×38**，白芯 32）；
         `border-box` → 外框 = w×h（实测 Chrome 的 `::-webkit-slider-thumb` 就是这种：32 外框、白芯 24）。
         默认值按来源给：**伪元素 = border-box、普通子元素 = content-box**；作者写了 `box-sizing` 以作者为准。
      ② **描边抗锯齿**：走 `_bordered_thumb` 的覆盖率混合（`gen_res.bordered_cov` 的整像素带会出锯齿）。
      ③ **圆角**：`border-radius:50%` 按**外框**取 `min(W,H)/2`（正圆）。
    """
    if not _HAS_GEN_RES:
        return None
    W, H, bw = _thumb_outer_size(style, tw, th, default_box)
    radii = _radius_corners(style, W, H)
    r = min(radii)                       # 滑块是强曲率形状；四角不同时取最小（保守，不出方角）
    _, bcol = _border_spec(style) or (0, None)
    spec = _bg_spec(style)
    fill = None
    if spec and spec[0] == 'color':
        fill = spec[1]
    elif spec and spec[0] == 'gradient':
        fill = spec[1][1][0][1]          # 渐变取首色标（圆钮上画渐变意义不大）
    if fill is None:
        fill = (0xE8, 0xF1, 0xFF, 255)   # CSS 没给 background 时的默认浅色圆钮
    img = (_bordered_thumb(W, H, r, fill, bcol, bw) if bw
           else gr.rounded_rect_cov(W, H, r, fill))
    return _save_css_png(img, out_dir, name)


def _css_progress(style, maxv):
    """CSS 推断进度 → (defProgress, 来源说明) 或 (None, None)。

    支持：`--value:60%` / `--value:60` > `width:60%`（填充元素自身的宽度百分比，进度条最自然的写法）。
    """
    m = re.search(r'--value\s*:\s*([\d.]+)\s*(%?)', style or '')
    if m:
        v = float(m.group(1))
        if m.group(2) == '%':
            return int(round(v / 100.0 * maxv)), '--value:%s%%' % m.group(1)
        return int(round(v)), '--value:%s' % m.group(1)
    m = re.search(r'(?:^|;)\s*width\s*:\s*([\d.]+)\s*%', style or '')
    if m:
        return int(round(float(m.group(1)) / 100.0 * maxv)), 'width:%s%%' % m.group(1)
    return None, None


def _canvas_bg(root):
    """html/body 的 background → 十进制颜色（0xRRGGBB）或 None。

    为什么需要（2026-10-04 真机实测）：CSS 的背景会从 `body`/`html` **传播到画布**，
    而 AI 写的 HTML 正是把页面底色写在 `body` 上（`.screen`/容器自己不写）。
    FlyThings 的 json 根**不继承任何东西** → 不写 `backgroundColor` 就是「透明、不擦屏」，
    真机上会**残留上一页 / 屏保画面**（实测：CSS 里 `body{background:#10151F}` 时，
    设备上整屏盖着上一帧的屏保）。这里按 CSS 传播语义把 body/html 的底色捞到根上。
    """
    def find(n, tag):
        if n.tag == tag:
            return n
        for ch in n.children:
            r = find(ch, tag)
            if r is not None:
                return r
        return None

    if root is None:
        return None
    for tag in ('body', 'html'):
        n = find(root, tag)
        if n is None:
            continue
        spec = _bg_spec(_attr(n.attrs, 'style') or '')
        if spec and spec[0] == 'color' and spec[1][3] > 0:
            c = spec[1]
            return (c[0] << 16) | (c[1] << 8) | c[2]
    return None


def _is_emoji(ch):
    """判断字符是否 emoji/特殊符号（设备裁剪字库不支持，全范围覆盖）：表情物品 1F000-1FAFF / 杂项符号 2600-27BF / 技术符号 2300-23FF /
箭头 2190-21FF / 几何图形 25A0-25FF / 带圈数字 2460-24FF /
字母符号 2100-214F / 杂项箭头 2B00-2BFF / 变体选择符 FE0F / ZWJ 200D"""
    o = ord(ch)
    return (0x1F000 <= o <= 0x1FAFF) or (0x2600 <= o <= 0x27BF) or \
        (0x2300 <= o <= 0x23FF) or (0x2190 <= o <= 0x21FF) or \
        (0x25A0 <= o <= 0x25FF) or (0x2460 <= o <= 0x24FF) or \
        (0x2100 <= o <= 0x214F) or (0x2B00 <= o <= 0x2BFF) or \
        o in (0xFE0F, 0x200D)


# 设备裁剪字库黑名单（铁律 1：禁 emoji/特殊符号，文本只用汉字+ASCII+基础符号 / % # - _ 空格）
_TEXT_BLACKLIST = set('⌫℃■●‹－＋–…→★◆▶▷①')


def _clean_text(s, ctx=None, where=''):
    """剥离 emoji 与黑名单特殊符号，只保留汉字+ASCII+基础符号（/ % # - _ 空格）。

    A1 修（2026-09-27）：命中黑名单/emoji 的字符**必须记账**。旧版直接 `continue` 静默丢弃，
真机表现为「整字消失」（不是方框），调用方查无实据；现在统一写进 ctx.warnings。
    """
    if not s:
        return s
    out = []
    dropped = []
    for ch in s:
        if ch in _TEXT_BLACKLIST or _is_emoji(ch):
            if ch not in dropped:
                dropped.append(ch)
            continue
        out.append(ch)
    if dropped and ctx is not None and hasattr(ctx, 'warn'):
        kind = 'emoji' if all(_is_emoji(c) for c in dropped) else '黑名单特殊符号'
        ctx.warn('文本字符被丢弃（%s）：%s（设备裁剪字库无该字形 → 整字消失）%s —— '
                 '改用图片素材或换字符（铁律 1）'
                 % (kind, ' '.join(repr(c) for c in dropped),
                    ('  @%s' % where) if where else ''),
                 key='drop:%s:%s' % (kind, ''.join(sorted(dropped))))
    # \n（来自 <br>）保留为换行；其余空白折叠为单空格
    return re.sub(r'[ \t\r\f\v]+', ' ', ''.join(out)).strip()


def _color_explicit(attrs, names, default):
    """颜色取值（A2 修，2026-09-27）：**按「属性是否出现」判未设置**，不按「值是否为 0」。

纯黑 `#000000` 解析出来就是 0（合法颜色）；旧写法 `to_dec(...) or 默认` 把 0 当 falsy
    → 纯黑被换成默认色（实测绿按钮落地成「绿底白字」，对比度 1.44:1）。
    names 可传单个属性名或候选列表，按顺序取第一个「出现且可解析」；都没有 → default。
    """
    for n in (names if isinstance(names, (list, tuple)) else [names]):
        raw = _attr(attrs, n)
        if raw is None or str(raw).strip() == '':
            continue
        v = to_dec(raw)
        if v is not None:
            return v
    return default


def _bool_attr(attrs, name):
    """三态布尔属性：出现且真值 → True；出现且 false/0/no/off → False；未出现 → None。

    A5 修（2026-09-27）：`data-visible` 是 HTML 侧给「某控件初始就该隐藏」的唯一口
    （旧版 html2json 不认该属性 → 只能靠运行时代码 patch，两处同步漏一处即静默失败）。
    """
    raw = _attr(attrs, name)
    if raw is None:
        return None
    v = str(raw).strip().lower()
    if v in ('false', '0', 'no', 'off', 'n'):
        return False
    return True


# ---------- DOM 树节点 ----------
VOID_TAGS = {'meta', 'img', 'input', 'br', 'hr', 'link'}


class Node:
    __slots__ = ('tag', 'attrs', 'children', 'text')

    def __init__(self, tag, attrs):
        self.tag = tag
        self.attrs = attrs
        self.children = []
        self.text = ''


class _DomParser(HTMLParser):
    """把受限 HTML 解析为 DOM 树（处理嵌套的正确方式）。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = None
        self.stack = []
        self.css_chunks = []      # <style> 里的 CSS 原文（最小层叠用，见 _apply_css）

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        if self.stack:
            self.stack[-1].children.append(node)
        elif self.root is None:
            self.root = node
        if tag not in VOID_TAGS:
            self.stack.append(node)
        elif tag == 'br' and self.stack:
            # <br> → '\n' 换行（textview 支持 \n 多行，2026-09-03 纠正 FT-024）
            self.stack[-1].text += '\n'

    def handle_startendtag(self, tag, attrs):
        # 自闭合 <xxx/>：挂到当前父节点，不入栈
        node = Node(tag, attrs)
        if self.stack:
            self.stack[-1].children.append(node)
        elif self.root is None:
            self.root = node

    def handle_endtag(self, tag):
        # 找到最近的同名节点弹出（受限 HTML 必须标签配对）
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return
        if self.stack:
            self.stack.pop()

    def handle_data(self, data):
        if not self.stack:
            return
        if self.stack[-1].tag == 'style':
            # <style> 里的 CSS 原文单独收集（最小层叠要读它）。
            # 仍**不**写进节点 text：否则 <style> 落进 .screen 时会被当文本控件把 CSS 源码画上屏。
            self.css_chunks.append(data)
            return
        if self.stack[-1].tag != 'script':
            # HTML 文本节点空白折叠（源码换行/缩进 → 单空格）；<br> 已在 handle_starttag 转 '\n'，不受影响
            self.stack[-1].text += re.sub(r'\s+', ' ', data)


# ---------- 转换上下文 ----------
class _Ctx:
    def __init__(self):
        self.n = 0
        self.ids = dict(ID_BASE)
        self.counter = {}
        self.root = None
        self.stack = []          # 打开的容器栈（window/listview/radiogroup dict）
        self.warnings = []
        self.warned = set()      # 去重键（A8：同一类丢弃/替默认值只报一次，不刷屏）

    def warn(self, msg, key=None):
        """转换期警告统一入口（去重）。

        A8 修（2026-09-27）：「丢字符 / 纯黑被替默认值 / data-visible 无效 / 圆角无底色」
这类**静默失败**必须回传到返回体 warnings，不再靠真机反推。
        """
        k = key or msg[:80]
        if k in self.warned:
            return
        self.warned.add(k)
        self.warnings.append(msg)

    def key(self, typ):
        self.n += 1
        return '%s__%d' % (typ, self.n)

    def nid(self, typ):
        self.ids[typ] += 1
        return self.ids[typ]

    def name(self, typ):
        self.counter[typ] = self.counter.get(typ, 0) + 1
        return '%s%d' % (AUTO_NAME.get(typ, typ.capitalize()), self.counter[typ])

    def add(self, typ, ctrl):
        """写入当前容器（有 window 嵌套则进栈顶），返回 key。

        T5.3（2026-10-05）：**字段补全走唯一发射层** `ui_emit.schema_complete(..., normalize=False)`
        ——对账（`ui_tools/emit_conformance.json`）实测本前端原先的 seekbar 产物缺 2 个必填键
        （backgroundPic/progressPic）、colorTab 只写单槽；这里统一补上。
        `normalize=False`：**不动本前端自己的 alignment 编码**（36/37 vs 发射层 0/5 的等价性未真机核实，
        差异仍登记在对账快照里，不擅自统一）。
        """
        try:
            import ui_emit as _emit
            # 只补**注册表必填键**（真缺口：对账实测 seekbar 缺 backgroundPic/progressPic）。
            # 不整表补全：热区按钮等**有意省略**的可选字段（bgColorTab）补回去会盖住下层画布。
            ctrl, _unfilled = _emit.fill_required(typ, ctrl)
            if _unfilled:
                self.warn('字段补全：%s 的必填键 %s 在发射层默认表里没有取值 → 未补（需在 '
                          'ui_tools/ui_emit.py 登记）' % (typ, _unfilled), key='emit_unfilled')
        except Exception as _e:                              # noqa: BLE001
            self.warn('必填键补全未走共享发射层（ui_emit 不可用：%s）→ 本页可能缺必填键' % _e,
                      key='emit_missing')
        key = self.key(typ)
        if self.stack:
            self.stack[-1][key] = ctrl
        else:
            self.root[key] = ctrl
        return key


# ---------- 转换器 ----------
class HtmlToJson:
    def __init__(self, res=None, asset_dir=None):
        self.res = res
        self.asset_dir = asset_dir   # CSS 效果自动转图输出目录（默认 output_json 同目录 images/）
        self.gen_count = 0

    def _gen_asset(self, fn):
        """调用 gen_res 生成图片；返回 json 引用路径（images/xxx.png）或 None。"""
        if not (_HAS_GEN_RES and self.asset_dir):
            return None
        try:
            p = fn(self.asset_dir)
            self.gen_count += 1
            return 'images/' + os.path.basename(p)
        except Exception as e:
            self.ctx.warnings.append(f'自动转图失败: {e}')
            return None

    # ---------- iconfont 图标自动落图（2026-09-03 需求方定规：图标优先）----------
    def _icon_png(self, ctx, glyph, cw, ch, color_int=None, pressed=False):
        """data-icon 语义图标 → PNG（iconfont 风格矢量线框，居中于控件画布）。
        glyph: 英文/中文名（back/返回...）；cw/ch: 控件尺寸（PNG 同尺寸，图标居中不变形）；
        color_int: 十进制描边色或 None(默认浅色)；pressed=True 生成按下态（按钮 picTab pic1）。
未收录/不可用返回 None 并 warning。"""
        cw, ch = max(1, int(cw or 0)), max(1, int(ch or 0))
        size = min(cw, ch)
        if not (_HAS_GEN_RES and self.asset_dir):
            ctx.warnings.append(
                f'data-icon="{glyph}" 自动转图不可用（缺 gen_res/Pillow 或未指定 asset_dir），请给 data-pic 自备图')
            return None
        gname = gr.glyph_canonical(glyph)
        if not gname:
            avail = ', '.join(gr.glyph_list())
            ctx.warnings.append(
                f'图标 "{glyph}" 未收录（可用：{avail}）；给 data-pic 自备图或换用列表内名字')
            return None
        col = _color_int_rgba(color_int, (0xD8, 0xE2, 0xF0, 255))
        hexs = '%02X%02X%02X' % tuple(int(v) for v in col[:3])
        name = 'icon_%s_%dx%d_%s%s.png' % (gname, cw, ch, hexs,
                                           '_p' if pressed else '')

        def _g(d, _n=name, _g2=gname, _s=size, _c=col, _p=pressed, _cv=(cw, ch)):
            return gr.glyph_icon(d, _n, _g2, size=int(_s), color=_c, pressed=_p, canvas=_cv)

        return self._gen_asset(_g)

    def _icon_color(self, attrs):
        """图标描边色：data-color → 十进制 int；缺省 None（gen_res 用默认浅色）。"""
        return to_dec(_attr(attrs, 'data-color'))

    def _effect_assets(self, ctx, node, w, h, cap):
        """检测 style/data 里的 CSS 效果并自动生成图片资源。
返回 {"backgroundPic": .., "picTab": {..}, "codeStr": .., "imageanim": bool, "use_emoji": ..}。"""
        attrs = node.attrs
        style = _attr(attrs, 'style') or ''
        classes = _classes(attrs)
        out = {}
        if not (_HAS_GEN_RES and self.asset_dir):
            return out

        # 1. 线性渐变背景 → 渐变 PNG（可选圆角 .9.png）
        gm = re.search(r'linear-gradient\(([^)]+)\)', style)
        if gm:
            horizontal, stops = _parse_gradient(gm.group(1))
            if len(stops) >= 2:
                # border-radius：px / 无单位 / %（50% → 正圆/药丸）；无声明 = 0（不裁剪）
                radius = _radius_px(style, w, h, 0)
                name = f'grad_{cap or ctx.n}_{self.gen_count}.png'

                def _g(d, _n=name, _w=w, _h=h, _st=stops, _hz=horizontal, _r=radius):
                    # 圆角裁剪一律走 SS（_CSS_SS=4；不再用 1x + α 羽化）
                    return gr.gen_gradient_stops(d, _n, _w, _h, _st, horizontal=_hz, radius=_r,
                                                 ss=_CSS_SS)

                pic = self._gen_asset(_g)
                if pic:
                    out['backgroundPic'] = pic

        # 2. box-shadow → 阴影卡片图（圆角 + 阴影；已有渐变底则阴影叠加到渐变图上）
        sh_spec = _shadow_spec(style)
        if sh_spec:
            if True:   # 保住原缩进层级（历史上这里 try 的缩进=16）
                try:
                    ox, oy, blur, sc = sh_spec
                    pad = _shadow_pad(ox, oy, blur)
                    # border-radius：px / 无单位 / %（50% → 正圆）；无声明时沿用历史默认 8
                    radius = _radius_px(style, w, h, 8)
                    fill = _css_color(re.search(r'background(?:-color)?\s*:\s*([^;]+)', style).group(1).strip()) \
                        if re.search(r'background(?:-color)?\s*:\s*([^;]+)', style) else (0x1E, 0x27, 0x35, 255)
                    # 渐变+阴影：阴影叠加到渐变底上（渐变优先，保留视觉层次）
                    if 'backgroundPic' in out:
                        name = f'gradshadow_{cap or ctx.n}_{self.gen_count}.png'

                        def _gs(d, _n=name, _w=w, _h=h, _r=radius, _sh=(ox, oy, blur, sc),
                                _gm=gm):
                            # 重画渐变底 + 阴影合成（SS：底 mask 与阴影层 alpha 都走超采样）
                            _hz, _st = _parse_gradient(_gm.group(1))
                            base = gr.gen_gradient_stops(d, _n, _w, _h, _st, horizontal=_hz,
                                                         radius=_r, ss=_CSS_SS)
                            # 在渐变图上叠加阴影（从 grad 图复制合成）
                            from PIL import Image as _Image
                            from PIL import ImageChops as _ImageChops
                            img = _Image.open(base).convert('RGBA')
                            sh = _Image.new('RGBA', img.size, sc)
                            # SS 版圆角 mask，只缩放 alpha（不能用 paste(color, mask)：
                            # RGB 会被一起按 mask 缩小 → 边界发黑（暗边 halo）
                            _m = gr.ss_shape_mask(img.size[0], img.size[1], _r, _CSS_SS)
                            sh.putalpha(_ImageChops.multiply(sh.getchannel('A'), _m))
                            if blur > 0:
                                from PIL import ImageFilter as _F
                                sh = sh.filter(_F.GaussianBlur(blur))
                            img.alpha_composite(sh)
                            img.save(base)
                            return base

                        self._gen_asset(_gs)  # 覆盖 grad 图，引用路径不变
                    else:
                        name = f'shadow_{cap or ctx.n}_{self.gen_count}.png'

                        def _s(d, _n=name, _w=w, _h=h, _r=radius, _f=fill, _sh=(ox, oy, blur, sc)):
                            # crop=False：保留完整画布 → 尺寸恒为 (w+2pad)x(h+2pad)，
                            # 主体卡落在 (pad, pad)，调用方 _grow 后「图==控件」精确对位
                            # ss=_CSS_SS：阴影层/主体圆角层/二次裁剪 mask 全走 SS
                            return gr.gen_shadow_card(d, _n, _w, _h, _r, _f, shadow=_sh,
                                                      crop=False, ss=_CSS_SS)

                        pic = self._gen_asset(_s)
                        if pic:
                            out['backgroundPic'] = pic
                            out['pad'] = pad   # 图比控件大 2*pad → 调用方必须 _grow 控件盒
                except Exception as e:
                    # 不静默：转图失败要说清原因（2026-09-10 前这里是 except: pass，极难排查）
                    ctx.warnings.append(
                        f'{cap or ctx.n}: box-shadow 转图失败（{type(e).__name__}: {e}），已忽略该阴影')

        # 3. emoji 图标 → PNG（仅纯 emoji 文本转图标 textview；混合文本由 _leaf/_clean_text 剥离 emoji 保留文字）
        raw_text = re.sub(r'[ \t\r\f\v]+', ' ', node.text).strip()
        if raw_text and not _clean_text(raw_text) and any(_is_emoji(ch) for ch in raw_text):
            emoji_ch = next((ch for ch in raw_text if _is_emoji(ch)), '\u2b50')
            name = f'emoji_{cap or ctx.n}_{self.gen_count}.png'

            # [!] 2026-09-18：按**控件盒 (w,h)**出图（不再 max(w,h) 出方图）——图 != 盒会把字形压扁/切掉
            def _e(d, _n=name, _w=w, _h=h, _c=emoji_ch):
                return gr.emoji_icon_box(d, _n, _w, _h, _c)

            pic = self._gen_asset(_e)
            if pic:
                out['backgroundPic'] = pic
                out['use_emoji'] = True

        # 4. loading/旋转动画 → GIF（imageanim 动图控件 play(file) 加载）+ 序列帧 PNG 备用
        if ('loading' in classes or 'spinner' in classes or
                re.search(r'animation\s*:', style) and ('spin' in style or 'rotate' in style or 'loading' in style)):
            size = max(w, h)
            color = _css_color(re.search(r'color\s*:\s*([^;]+)', style).group(1).strip()) \
                if re.search(r'color\s*:\s*([^;]+)', style) else (0x42, 0xC9, 0xFF, 255)
            base = f'loading_{cap or ctx.n}'

            def _g(d, _b=base, _s=size, _c=color):
                return gr.frames_loading_gif(d, _b + '.gif', _s, _c, n=12)

            gif = self._gen_asset(_g)
            # 序列帧 PNG（备用，供 ZKImageView 逐帧或调试）
            try:
                gr.frames_loading(self.asset_dir, base, size, color, n=12)
            except Exception:
                pass
            out['imageanim'] = True
            if gif:
                out['anim_file'] = gif  # images/loading_xxx.gif

        return out

    # ---------- 进度条（seekbar）：CSS 三件套 → 3 张切图 ----------
    # 为什么单独一段（2026-10-04 真机归因实测）：进度条在引擎里是「3 张图 + 3 套不同的尺寸语义」，
    # 而 `_effect_assets` 的模型是「一个控件 = 一张皮」，表达不了：
    #   ① 轨道 backgroundPic：引擎**拉伸填满控件盒**                → 图 == 控件盒 (W×H)
    #   ② 有效 progressPic  ：引擎**1:1 贴 + 按 floor(W·p/max) 裁剪**（不缩放）→ 图也必须 == 控件盒
    #   ③ 滑块 thumb.normalPic：引擎**按 PNG 原尺寸画**（thumb.size 实测被忽略）→ 图 == CSS 滑块尺寸
    # 另外引擎不认伪元素，AI 的 `::-webkit-slider-thumb` 必须落到 `.thumb` 子元素或 data-thumb。
    _SEEKBAR_FILL_CLASSES = ('fill', 'progress', 'bar-fill', 'barfill', 'value',
                             'bar-inner', 'barinner', 'inner', 'indicator')
    _SEEKBAR_THUMB_CLASSES = ('thumb', 'knob', 'handle', 'slider-thumb', 'sliderthumb')
    # 滑条伪元素（正常 HTML 的标准写法；`input[type=range]` 的滑块/轨道只能这么写）
    _PS_TRACK = ('webkit-slider-runnable-track', 'moz-range-track')
    _PS_THUMB = ('webkit-slider-thumb', 'moz-range-thumb')
    _PS_FILL = ('moz-range-progress', 'webkit-slider-progress')
    _css_text = ''        # <style> 原文（convert() 里填；供"伪元素写法"告警判断，缺省空串防 AttributeError）
    _pseudo_css = None    # {id(node): {伪元素名: 声明串}}（convert() 里填）

    @staticmethod
    def _child_by_class(node, names):
        """取第一个 class 命中 names 的直接子节点（进度条的 .fill / .thumb 子元素）。"""
        for ch in node.children:
            if _classes(ch.attrs) & set(names):
                return ch
        return None

    def _pseudo_style(self, node, names):
        """取节点某个**伪元素**的声明串（`::-webkit-slider-thumb` 等）；没有则 ''。

        为什么要读伪元素（2026-10-04）：`<input type=range>` 的滑块/轨道在正常 HTML 里**只能**
        用 `::-webkit-slider-thumb` / `::-webkit-slider-runnable-track` 写 —— 引擎与 json 都没有
        伪元素，但它们承载的信息正好是 seekbar 的三张切图规格，所以必须翻译而不是丢掉。
        """
        bucket = (getattr(self, '_pseudo_css', None) or {}).get(id(node)) or {}
        for n in names:
            if bucket.get(n):
                return bucket[n]
        return ''

    def _seekbar_css_assets(self, ctx, node, c, pos, cap):
        """CSS 结构化的进度条 → 轨道/有效/滑块三张切图 + 进度值 + 不可实现项告警。

    三套写法都认（优先级由高到低，作者显式给的永远优先）：
      ① `data-track/data-fill/data-thumb*`（本函数不接管，行为与改动前一致）；
      ② **伪元素**（正常 HTML 的标准写法）：
         `::-webkit-slider-runnable-track` → 轨道；`::-webkit-slider-thumb` / `::-moz-range-thumb`
         → 滑块；`::-moz-range-progress` → 填充；
      ③ 真实子元素 `.fill` / `.thumb`。
    Chrome 的 `input[type=range]` **没有**填充伪元素，所以「已有进度」的常规画法是把填充做成
    轨道背景上的**硬停靠渐变** → 由 `_split_fill_track` 拆成填充 + 轨道 + 进度值。
        返回 True = 本次确实产出了切图或进度值（调用方据此决定是否补引擎口径说明）。
        """
        if not (_HAS_GEN_RES and self.asset_dir):
            return False
        style = _attr(node.attrs, 'style') or ''
        fill_node = self._child_by_class(node, self._SEEKBAR_FILL_CLASSES)
        thumb_node = self._child_by_class(node, self._SEEKBAR_THUMB_CLASSES)
        ps_track = self._pseudo_style(node, self._PS_TRACK)
        ps_thumb = self._pseudo_style(node, self._PS_THUMB)
        ps_fill = self._pseudo_style(node, self._PS_FILL)
        has_radius = bool(re.search(r'border-radius\s*:', style))
        pseudo_seen = bool(ps_track or ps_thumb or ps_fill)
        if not (fill_node is not None or thumb_node is not None or pseudo_seen or
                _bg_spec(style) or has_radius):
            return False

        # 盒子几何：先按 CSS 修正（`width:100%` 在 AI 写法里极常见 —— 没有布局引擎，
        # 按最近容器（.screen 分辨率）解析，并在告警里说明这是近似）。
        res = (ctx.root or {}).get('resolution') or {}
        for key, ref in (('width', res.get('width', 480)), ('height', res.get('height', 800))):
            v = _style_len_ref(style, key, ref)
            if v and v != pos.get(key):
                if re.search(r'(?:^|;)\s*%s\s*:\s*[\d.]+%%' % key, style):
                    ctx.warn('%s：CSS 的 %s 是百分比 → 按最近容器（%s=%dpx）解析成 %dpx'
                             '（没有布局引擎，百分比只能这样近似；建议改写成绝对像素）'
                             % (cap, key, '屏幕宽' if key == 'width' else '屏幕高', ref, v),
                             key='seekbar-pct-%s' % key)
                pos[key] = v
        W = int(pos.get('width', 100) or 100)
        H = int(pos.get('height', 32) or 32)
        made = []

        # `--max:200` 这种 CSS 变量形式的量程（作者不写 data-max 时用）
        if not _attr(node.attrs, 'data-max'):
            mm = re.search(r'--max\s*:\s*([\d.]+)', style)
            if mm:
                c['max'] = max(1, int(round(float(mm.group(1)))))

        # ① 轨道 / 有效 / 进度值：三条来源依次是 伪元素 → 子元素 → 轨道硬停靠渐变
        track_style = ps_track if ps_track else style
        fstyle, frac, from_grad = '', None, False
        if ps_fill:
            fstyle = ps_fill
        elif fill_node is not None:
            fstyle = _attr(fill_node.attrs, 'style') or ''
        else:
            split = _split_fill_track(track_style)
            if split:
                fbg, tbg, frac = split
                # ⚠️ 只换背景声明：圆角/高度/边框必须留在各自 style 里（否则药丸轨道变方头）
                fstyle = _replace_bg(track_style, fbg)
                track_style = _replace_bg(track_style, tbg)
                from_grad = True
        if frac is not None and not _attr(node.attrs, 'data-value'):
            mx = int(c.get('max') or 100)
            c['defProgress'] = max(0, min(mx, int(round(frac * mx))))
            made.append('value')
            ctx.warn('%s：进度取自轨道背景的**硬停靠渐变**（停靠点 %.1f%% → defProgress=%d/max=%d）。'
                     'Chrome 的 input[type=range] 没有填充伪元素，「已有进度」就是这么画的 —— '
                     '已拆成 填充图 + 轨道图 两张；要运行期改值用代码 setProgress()'
                     % (cap, frac * 100.0, c['defProgress'], mx), key='seekbar-hardstop')

        # ② 滑块：伪元素优先，其次 .thumb 子元素（真机按 PNG 原尺寸画 → 图 == CSS 滑块**外框**）
        tstyle = ps_thumb if ps_thumb else (
            (_attr(thumb_node.attrs, 'style') or '') if thumb_node is not None else '')
        tsrc = '伪元素' if ps_thumb else ('.thumb 子元素' if thumb_node is not None else '')
        # 盒模型默认值按来源：伪元素 = border-box（Chrome 实测）、子元素 = content-box（CSS 默认）
        tbox = 'border-box' if ps_thumb else 'content-box'
        tw = th = None
        if tstyle:
            ts = parse_px(_attr(thumb_node.attrs, 'data-thumb-size')) if thumb_node is not None else None
            cw = (_style_len(tstyle, 'width') or ts)
            ch = (_style_len(tstyle, 'height') or ts)
            if not (cw and ch):
                ctx.warn('%s：%s 里读不到绝对像素宽高（缺 width/height 或写了 %% / auto）—— '
                         '滑块图未生成；请写 width:32px;height:32px（或 data-thumb-size="32"）'
                         % (cap, tsrc), key='seekbar-thumb-size')
            else:
                # 外框（border box）= 真机实际画出来的尺寸；`thumb.size` 也写这个
                tw, th, _bw = _thumb_outer_size(tstyle, cw, ch, tbox)
                if tw != cw or th != ch:
                    ctx.warn('%s：滑块 CSS 写的是 %dx%d + border %dpx，按 `box-sizing:%s` 的**外框**是 %dx%d '
                             '（CSS 默认 content-box 时 border 加在尺寸之外）—— 切图与 thumb.size 都按外框 %dx%d 出'
                             % (cap, cw, ch, _bw, _box_sizing(tstyle, tbox), tw, th, tw, th),
                             key='seekbar-thumb-box')

        # ③ 真机按**盒高居中裁**滑块 → 盒高 < 图高时圆钮会被切掉上下（`seekbar-fields.md` §2 的
        #    「滑块被压扁」就是这个）。正常 HTML 常把 input 高度写成轨道高度、滑块更大 →
        #    这里把控件盒**居中抬到**滑块高度（可见条中线不变），并明确告警几何已改。
        if th and th > H:
            grow = th - H
            pos['top'] = int(pos.get('top', 0)) - grow // 2
            pos['height'] = H = th
            c['position'] = pos
            ctx.warn('%s：滑块 %dx%d 比控件盒高 %d 大 → 已把控件盒**居中抬到** %d 高'
                     '（top %+d），否则真机按盒高居中裁、圆钮上下被切（实测：24×24 图 + 12 高盒 → '
                     '24×12 扁椭圆）' % (cap, tw, th, int(pos.get('height', 0)), th, -grow // 2),
                     key='seekbar-box-grown')

        # ④ 可见条高度：CSS 轨道高度 < 盒高时，条**居中**画在盒里、上下真透明
        #    （`::-webkit-slider-runnable-track{height:12px}` + input 32 高 = 正常 HTML 滑条形态）
        band = None
        bh = _style_len(track_style, 'height')
        if bh and 0 < bh < H:
            band = (max(0, (H - bh) // 2), bh)
        elif bh and bh > H:
            ctx.warn('%s：轨道高 %d 比控件盒高 %d 还大 → 真机会按盒裁掉上下；'
                     '已把 position.height 抬到 %d' % (cap, bh, H, bh), key='seekbar-track-taller')
            pos['height'] = H = bh
            c['position'] = pos

        # ⑤ 出图：轨道 / 有效（尺寸都 == 控件盒）
        if not c.get('backgroundPic'):
            pic = self._gen_asset(lambda d: _bar_pic(d, 'bar_%s_track.png' % (cap or ctx.n),
                                                     W, H, track_style, band=band))
            if pic:
                c['backgroundPic'] = pic
                made.append('track')
        if fstyle and not c.get('progressPic'):
            pic = self._gen_asset(lambda d: _bar_pic(d, 'bar_%s_fill.png' % (cap or ctx.n),
                                                     W, H, fstyle, band=band))
            if pic:
                c['progressPic'] = pic
                made.append('fill')
        if fstyle and not _attr(node.attrs, 'data-value'):
            val, how = _css_progress(fstyle, int(c.get('max') or 100))
            if val is not None:
                c['defProgress'] = max(0, min(int(c.get('max') or 100), val))
                if 'value' not in made:
                    made.append('value')
                    ctx.warn('进度值取自 CSS（%s → defProgress=%d/max=%d）；'
                             '要运行期改值用代码 setProgress()，json 字段只管初值'
                             % (how, c['defProgress'], c.get('max') or 100),
                             key='seekbar-value')
        if tw and th and not (c.get('thumb') or {}).get('normalPic'):
            pic = self._gen_asset(lambda d: _thumb_pic(d, 'bar_%s_thumb.png' % (cap or ctx.n),
                                                       _style_len(tstyle, 'width') or tw,
                                                       _style_len(tstyle, 'height') or th,
                                                       tstyle, tbox))
            if pic:
                c['thumb'] = {'size': {'width': tw, 'height': th},
                              'normalPic': pic, 'pressedPic': ''}
                c['touchable'] = True
                made.append('thumb')
                if ps_thumb:
                    ctx.warn('%s：滑块样式取自伪元素 `::-webkit-slider-thumb`（或 -moz-）—— '
                             '已翻译成 thumb 切图 %dx%d（thumb.size 同步写 %d）；'
                             '`margin-top` 之类的伪元素垂直微调无对应，真机一律**盒内居中**'
                             % (cap, tw, th, tw), key='seekbar-pseudo-thumb-ok')

        # ⑥ 伪元素写法残留（滑块尺寸读不出来）→ 点名，否则真机上没有滑块
        if (not (c.get('thumb') or {}).get('normalPic')
                and re.search(r'slider-(?:thumb|runnable)', self._css_text or '')):
            ctx.warn('%s：文档里用了 `::-webkit-slider-thumb` / `::-webkit-slider-runnable-track`，'
                     '但本节点没解析出可用的滑块尺寸（缺 width/height 或写了 %% / auto）→ '
                     '真机上**没有滑块**；请给 `::-webkit-slider-thumb` 写绝对像素 width/height'
                     % cap, key='seekbar-pseudo')

        # ⑦ 真机口径下不可实现的部分：逐条说清，不让下一轮再靠真机反推
        if 'progressPic' in c and re.search(r'border-radius\s*:', fstyle):
            ctx.warn('%s：有效图带 border-radius，但引擎对有效图**只裁剪不缩放** → '
                     '0<p<max 时右端永远是**硬切**（实测：药丸端头一点没被压，右端直接切断）；'
                     '「按进度伸长的圆头填充」在真机上无法实现，圆头只能靠滑块盖住（需切图确认外观）'
                     % cap, key='seekbar-fill-radius')
        if (not from_grad) and re.search(r'linear-gradient', fstyle):
            ctx.warn('%s：填充图的 linear-gradient 是按**填充自身宽度**定义的，而真机有效图宽度固定 '
                     '== 控件盒、再按进度裁剪 → 进度越小看到的那段渐变越短（渐变被"压缩"）。'
                     '要进度无关的固定配色，请把渐变定义在**轨道空间**（宽度 = 控件盒）'
                     '（需切图确认外观）' % cap, key='seekbar-fill-gradient')
        if re.search(r'box-shadow\s*:[^;]*inset', style):
            ctx.warn('%s：轨道用了 `box-shadow: inset …`（内阴影）—— FlyThings 没有内阴影，'
                     '转换器只识别**外**阴影（inset 会被当外阴影，方向相反）→ 想要凹陷感请把'
                     '内阴影烘进轨道切图（需切图确认外观）' % cap, key='seekbar-inset')
        if tstyle and re.search(r'box-shadow\s*:', tstyle):
            ctx.warn('%s：滑块用了 box-shadow —— 引擎按 PNG 原尺寸贴图、没有阴影层 → '
                     '请把投影烘进滑块切图（需切图确认外观）' % cap, key='seekbar-thumb-shadow')

        # ⑧ 底色会把轨道图的圆角"补平"（实测：底色与轨道同色时 r=4 视觉上完全消失）
        bgv = to_dec(_attr(node.attrs, 'data-bg'))
        spec = _bg_spec(track_style)
        if bgv is not None and spec and spec[0] == 'color' and bgv >= 0:
            tr = spec[1]
            if (bgv >> 16 & 255, bgv >> 8 & 255, bgv & 255) == (tr[0], tr[1], tr[2]):
                ctx.warn('%s：seekbar 的 backgroundColor（data-bg）与轨道图**同色** —— '
                         '真机先铺满底色再贴图，轨道图的透明圆角会被底色补满、视觉上变直角'
                         '（2026-10-04 实测：同色时四角 = 轨道色，改成 -1 后四角 = 页面底色、圆角立刻可见）'
                         '→ 去掉 data-bg（保持 backgroundColor:-1）或改成页面底色'
                         % cap, key='seekbar-bg-erases-radius')

        # ⑨ 引擎口径说明（一页一次，避免下一轮又靠真机反推）
        if made:
            ctx.warn('进度条真机口径（2026-10-04 实测，出图/改图前先看这条）：'
                     '① 轨道图 backgroundPic 会被**拉伸填满控件盒**；'
                     '② 有效图 progressPic 是**1:1 原样贴 + 按 floor(盒宽×进度/max) 横向裁剪**'
                     '（不是拉伸！右端永远硬切）；'
                     '③ 滑块按 **PNG 原尺寸**画（thumb.size 只作声明，实测真机忽略它），'
                     '左沿 = position.left + floor((盒宽−图宽)×进度/max)，盒高 < 图高时滑块被居中裁。'
                     '本次自动出图：%s' % '、'.join(made), key='seekbar-engine-model')
        return bool(made)

    def convert(self, text, merge_windows=False):
        """受限 HTML -> (pages, warnings, meta)。

        pages = [(page_id, data), ...]（失败/屏数核对不过时为 None）：
          - 单屏（1 个 .screen）：len==1，产物与旧版逐字段一致（回归保护）；
          - **缺省口径（2026-09-21）：每屏一个 json**—— 一个 .screen = 一个页面 =
一个 Activity = 一个独立 ftu；len==N，data 是普通单屏 json 的根
            （同屏内部的 window/dialog 不是页，写在 .screen 里即可）；
          - merge_windows=True（CLI --merge-windows）：N 屏合成**同一 json**内的 N 个整屏
            window（键 window__1..window__N 连续编号，首屏 visible:true、其余 visible:false，
切页走 showWnd/hideWnd）—— **仅当这些屏同属一个 Activity**时才用；
此时 len==N（逐页列出，都指向同一个 json），**页数 = 屏数，一屏不许丢**。
        meta = {screensDetected, pagesProduced, mode, failed[], error?}；
        mode in (single-screen / per-screen / merge-windows)；
        screensDetected != pagesProduced 一律写 meta['error']（禁止再静默丢页）。
        """
        p = _DomParser()
        p.feed(text)
        p.close()
        if p.root is None:
            return None, ['空 HTML'], None
        # 最小 CSS 层叠（2026-10-04）：把 <style> 块的声明折进各节点的 style 属性，
        # 位置/渐变/圆角/阴影才有得读。放在 _find_screens 之前 —— .screen 的 style 里可能写分辨率。
        self._css_text = ' '.join(p.css_chunks)
        # 伪元素声明单独收（不能并进节点 style：`::-webkit-slider-thumb{height:32}` 混进去
        # 会把控件本身写成 32 高）；由 `_seekbar_css_assets` 按名字取。
        self._pseudo_css = {}
        self._rad_glue = []          # RadButton 胶水代码（纯色倒角按键；见 _try_radbutton）
        self._css_applied = _apply_css(p.root, self._css_text, self._pseudo_css)
        # CSS 背景传播：html/body 的 background 铺满画布（不写根底色 = 真机不擦屏、残留上一帧）
        self._page_bg = _canvas_bg(p.root)
        screens, nested = self._find_screens(p.root)
        if not screens:
            return None, ['未找到 <div class="screen"> 根节点（受限 HTML 必须从 screen 容器开始）'], None
        mode = ('merge-windows' if (merge_windows and len(screens) > 1)
                else ('single-screen' if len(screens) == 1 else 'per-screen'))
        meta = {'screensDetected': len(screens), 'pagesProduced': 0, 'failed': [], 'mode': mode}
        warnings = []
        # 嵌套 .screen：从 error 降为 warning（既有输入不许突然跑不过），但必须点名（不许静默）
        if nested:
            warnings.append('检测到 %d 个嵌套 .screen（位于另一个 .screen 内部）：%s —— '
                            '按**最外层**算页，这些嵌套屏的容器被忽略（屏内控件仍属于最外层页）；'
                            '规范写法是并列 .screen（每屏一个、data-page 区分）'
                            % (len(nested), ' / '.join(self._nest_label(n, i)
                                                       for i, n in enumerate(nested, 1))))
        if mode == 'merge-windows':
            warnings.append('识别到 %d 个 .screen（多屏设计稿）：%s'
                            % (len(screens),
                               ' / '.join(self._page_label(n, i)
                                          for i, n in enumerate(screens, 1))))
            warnings.append('本次按 merge-windows 合成：已把 %d 个 .screen 合成到同一个 json 的 %d 个'
                            '整屏 window（window__1..window__%d 连续编号，首屏 visible:true、'
                            '其余 visible:false，切页走 showWnd/hideWnd）—— 只在**这些屏同属一个 '
                            'Activity（同 ftu 内整屏 window）**时用；跨业务域 / 需独立返回栈请去掉'
                            '这个开关（缺省口径 = 每屏一个 json = 每屏一个 Activity 各自独立 ftu）'
                            % (len(screens), len(screens), len(screens)))
            data, w, made_ids = self._compose_windows(screens, meta)
            warnings += w
            pages = [(pid, data) for pid in made_ids] if data is not None else []
        elif mode == 'single-screen':
            data, w = self._convert_one(screens[0])
            warnings += w
            pages = [(self._page_id(screens[0], 1), data)]
            meta['pagesProduced'] = 1
        else:
            warnings.append('识别到 %d 个 .screen（多屏设计稿）：%s'
                            % (len(screens),
                               ' / '.join(self._page_label(n, i)
                                          for i, n in enumerate(screens, 1))))
            warnings.append('缺省口径：**每屏一个 json**（一个 .screen = 一个页面 = 一个 Activity = '
                            '一个独立 ftu），文件名取 data-page：%s。同一 Activity 内的 '
                            'window / dialog（弹窗）属于该屏**内部**，直接写在 .screen 里'
                            '（div.window / div.modal），不另算一页、工具也不会把多个 .screen 合并；'
                            '哪些屏属于不同 Activity、哪些属于同屏内 window/dialog，由 AI 在设计阶段'
                            '（HTML 原型）判定。只有**同属一个 Activity 的多个整屏 window**才用 '
                            '--merge-windows（MCP: merge_windows=true）合成一个 json'
                            % ' / '.join('%s.json' % self._page_id(n, i)
                                         for i, n in enumerate(screens, 1)))
            pages, seen = [], set()
            for k, node in enumerate(screens, 1):
                pid = self._page_id(node, k)
                if pid in seen:
                    meta['failed'].append('%s（第 %d 屏：data-page 重复，每屏一个 json 会互相覆盖）'
                                          % (pid, k))
                    continue
                seen.add(pid)
                try:
                    data, w = self._convert_one(node)
                except Exception as e:
                    meta['failed'].append('%s（第 %d 屏转换失败: %s: %s）'
                                          % (pid, k, type(e).__name__, e))
                    continue
                warnings += w
                pages.append((pid, data))
            meta['pagesProduced'] = len(pages)
        # CSS 导出切图的编码汇总（8bit 索引色 vs RGBA）——不静默：哪张用了哪种、省了多少
        if _PNG_LOG:
            p8 = [r for r in _PNG_LOG if r[1] == 'p8']
            rg = [r for r in _PNG_LOG if r[1] != 'p8']
            saved = sum(r[2] - r[3] for r in p8)
            msg = ('CSS 导出切图编码：%d 张走 **8bit 索引色 PNG**（调色板裁剪 + tRNS 逐档 alpha，'
                   '省 %d B%s）；%d 张保留 RGBA'
                   % (len(p8), saved,
                      ('，平均 −%.0f%%' % (100.0 * saved / max(1, sum(r[2] for r in p8))))
                      if p8 else '', len(rg)))
            if rg:
                msg += ('（索引化不划算/掉色：%s —— 用色数 >256 的真渐变索引化后反而更大，'
                        '需要更小请把渐变收敛成几个色标）'
                        % '、'.join('%s %dB→%dB/%d色' % (r[0], r[2], r[3], r[4]) for r in rg[:4]))
            warnings.append(msg)
            del _PNG_LOG[:]
        if meta['pagesProduced'] != meta['screensDetected']:
            meta['error'] = ('屏数核对失败：识别到 %d 个 .screen，仅产出 %d 页%s。'
                             '禁止静默丢页 —— 请修正 HTML（每屏一个并列 .screen，'
                             'data-page 唯一）后重转'
                             % (meta['screensDetected'], meta['pagesProduced'],
                                ('，失败：' + '；'.join(meta['failed']))
                                if meta['failed'] else ''))
            return None, warnings, meta
        return pages, warnings, meta

    def _page_id(self, node, k):
        """页 id = .screen 的 data-page（缺失则 page_k）；去掉文件名不安全字符（保留汉字）。"""
        pid = str(_attr(node.attrs, 'data-page') or '').strip()
        if not pid:
            return 'page_%d' % k
        return re.sub(r'[\\/:*?"<>|\s]+', '_', pid) or ('page_%d' % k)

    def _page_label(self, node, k):
        """warnings 里的页名：id（data-page-name 有则带中文名）。"""
        pid = self._page_id(node, k)
        nm = str(_attr(node.attrs, 'data-page-name') or '').strip()
        return '%s(%s)' % (pid, nm) if nm else pid
    def _nest_label(self, node, k):
        """warnings 里嵌套 .screen 的名字：data-page 有则用它，否则「嵌套屏k」。"""
        pid = str(_attr(node.attrs, 'data-page') or '').strip()
        return pid if pid else ('嵌套屏%d' % k)


    @staticmethod
    def _strip_markers(d):
        """清理转换期内部标记（__ 前缀键）；递归。"""
        for k in [k for k in d if k.startswith('__')]:
            del d[k]
        for v in d.values():
            if isinstance(v, dict):
                HtmlToJson._strip_markers(v)
            elif isinstance(v, list):
                for x in v:
                    if isinstance(x, dict):
                        HtmlToJson._strip_markers(x)

    def _convert_one(self, node):
        """单屏转换（一个 .screen -> 一个独立 json 的根）；返回 (data, warnings)。"""
        ctx = _Ctx()
        self.ctx = ctx
        self._open_screen(ctx, node)
        for ch in node.children:
            self._walk(ctx, ch)
        if ctx.root:
            self._strip_markers(ctx.root)
            self._fix_slidewindow_icon_size(ctx.root)
        return ctx.root, ctx.warnings

    def _compose_windows(self, screens, meta):
        """N 屏 -> 同一 json 内 N 个整屏 window（**merge-windows 口径**，页数 = 屏数）。

只在「这些屏同属一个 Activity（同 ftu 内整屏 window）」时用；缺省口径是每屏一个 json。
键先占号（window__1..window__N 连续），再逐屏把子控件写进对应 window，
避免页内嵌套 window 抢占页号。某屏转换失败 -> 记 failed 并跳过（上层据此报错，
不静默丢页）。返回 (data, warnings, made_ids)：made_ids = 成功合成的页 id 列表。
        """
        first = screens[0]
        W, H = self._screen_size(first)
        ctx = _Ctx()
        self.ctx = ctx
        self._open_screen(ctx, first)          # 根：分辨率/背景/根 position 取首屏
        keys = [ctx.key('window') for _ in screens]
        made = 0
        made_ids = []
        for k, (key, node) in enumerate(zip(keys, screens), 1):
            attrs = node.attrs
            page = self._page_id(node, k)
            c = {'backgroundColor': -1, 'caption': page,
                 'hideTimeOut': -1, 'id': ctx.nid('window'),
                 'modal': False,
                 'position': {'height': H, 'left': 0, 'top': 0, 'width': W},
                 'touchable': False, 'visible': (k == 1)}
            bg = to_dec(_attr(attrs, 'data-background'))
            if bg is None:
                bg = to_dec(_attr(attrs, 'data-bg'))
            if bg is not None:
                c['backgroundColor'] = bg
            hto = parse_px(_attr(attrs, 'data-hide-timeout'))
            if hto is not None:
                c['hideTimeOut'] = hto
            pic = _attr(attrs, 'data-pic')
            if pic:
                c['backgroundPic'] = pic if '/' in pic else 'images/' + pic
            try:
                ctx.root[key] = c
                ctx.stack.append(c)
                for ch in node.children:
                    self._walk(ctx, ch)
                ctx.stack.pop()
            except Exception as e:
                ctx.stack = []
                ctx.root.pop(key, None)
                meta['failed'].append('%s（第 %d 屏转换失败: %s: %s）'
                                      % (page, k, type(e).__name__, e))
                continue
            made += 1
            made_ids.append(page)
            ctx.warnings.append('第 %d 屏 %s -> %s（caption=%s，visible=%s）'
                                % (k, self._page_label(node, k), key, page,
                                   'true' if k == 1 else 'false'))
        if ctx.root:
            self._strip_markers(ctx.root)
            # 多屏合成：slidewindow 落在整屏 window 内，必须递归才不漏回填 iconSize
            self._fix_slidewindow_icon_size(ctx.root, recursive=True)
        meta['pagesProduced'] = made
        return ctx.root, ctx.warnings, made_ids

    def _fix_slidewindow_icon_size(self, root, recursive=False):
        """SlideWindow 图标布局铁律（2026-09-01）：iconSize 必须按实际图片尺寸，
不是控件平分格子大小（默认 128 会导致图标位置不对/拉伸）。
        HTML 未显式指定 data-icon-w/h 时，尝试从 items 首张图片读实际尺寸回填；
读不到则保留默认并 warning 提示。padding 语义：padding=图标相对平分格子边界，
        iconTextPadding=配套文字 padding（文档：knowledge/uicontrols/slidewindow-fields.md）。"""
        try:
            from PIL import Image as _PImage
        except Exception:
            _PImage = None

        def _img_size(pic_ref):
            """json 引用 images/xxx.png（相对 resources）→ asset_dir 下真实文件 → (w,h)。"""
            if not pic_ref:
                return None
            base = os.path.basename(str(pic_ref).replace('\\', '/'))
            cands = []
            if self.asset_dir:
                cands.append(os.path.join(self.asset_dir, base))
                cands.append(os.path.join(self.asset_dir, 'images', base))
            if not cands:
                return None
            for p in cands:
                if os.path.isfile(p) and _PImage:
                    try:
                        with _PImage.open(p) as im:
                            return im.size
                    except Exception:
                        continue
            return None

        for key, val in HtmlToJson._slidewindow_dicts(root, recursive=recursive):
            items = val.get('items') or []
            if not items:
                continue
            # 用户显式指定过 data-icon-w/h 则跳过
            if val.get('__icon_explicit'):
                continue
            # 读全部图标图实际尺寸（2026-09-01：同一 slidewindow 所有图标尺寸必须一致）
            sizes = []
            for it in items:
                pt = it.get('picTab') or {}
                if pt.get('pic0'):
                    sz = _img_size(pt['pic0'])
                    if sz:
                        sizes.append(sz)
            if not sizes:
                self.ctx.warnings.append(
                    f'slidewindow {val.get("caption", key)}: iconSize 未指定且读不到图片实际尺寸'
                    f'（items 无图或文件缺失），默认 128 可能导致图标位置不对；请按实际图片尺寸填 data-icon-w/h')
                continue
            # 一致性检查：所有图标尺寸应一致（不一致 → 生成时按最大/统一尺寸出图，否则位置错乱）
            uniq = sorted(set(sizes))
            if len(uniq) > 1:
                self.ctx.warnings.append(
                    f'slidewindow {val.get("caption", key)}: items 图标尺寸不一致 '
                    f'{["%dx%d" % s for s in uniq]}——同一滑动窗口所有图标必须同尺寸'
                    f'（iconSize 按实际图片尺寸，图标位置按平分格子计算）；请统一图标图片尺寸后重转')
            # 用首张图尺寸回填 iconSize（一致场景 = 唯一尺寸）
            w0, h0 = uniq[0]
            val['iconSize'] = {'width': w0, 'height': h0}
            if len(uniq) == 1:
                self.ctx.warnings.append(
                    f'slidewindow {val.get("caption", key)}: iconSize 未显式指定，已按实际图片尺寸 '
                    f'{w0}x{h0} 回填（SlideWindow 铁律：iconSize=图片实际尺寸，非平分格子大小；'
                    f'可显式 data-icon-w/h 指定）')
            else:
                self.ctx.warnings.append(
                    f'slidewindow {val.get("caption", key)}: 暂按首图尺寸 {w0}x{h0} 回填 iconSize，'
                    f'请统一图标尺寸后重转')

    @classmethod
    def _find_screens(cls, root):
        """收集全部 div.screen（文档顺序）。返回 (screens[], nested_nodes[])。

        screens = **最外层**.screen（= 页）：嵌套在另一个 .screen 内部的**不计页**，
其容器被忽略、屏内控件仍按最外层页处理（v0.27.100 起嵌套由 error 降为 warning）。
        nested_nodes = 被忽略的嵌套 .screen 节点（上层在 warnings 里点名列出，不许静默）。
旧版 _find_screen() 只取第一个 .screen 就 return，多屏设计稿因此被静默压成一页
        （2026-09-21 修：页数 = 屏数，一屏不许丢）。
        """
        screens, nested = [], []

        def walk(node, inside):
            if node.tag == 'div' and 'screen' in _classes(node.attrs):
                if inside:
                    nested.append(node)
                else:
                    screens.append(node)
                    inside = True
            for ch in node.children:
                walk(ch, inside)

        walk(root, False)
        return screens, nested

    @classmethod
    def _slidewindow_dicts(cls, d, out=None, recursive=True):
        """取 slidewindow 控件 dict（recursive=True 时递归到嵌套 window 内）。

单屏旧路径保持**不递归**（与改动前逐字段一致，不多出回填）；
多屏合成后 slidewindow 落在整屏 window 内，用 recursive=True 才不会漏回填 iconSize。
        """
        if out is None:
            out = []
        for key, val in d.items():
            if not isinstance(val, dict) or '__' not in key:
                continue
            if key.startswith('slidewindow__'):
                out.append((key, val))
            if recursive:
                cls._slidewindow_dicts(val, out, recursive)
        return out

    # ---------- 遍历 ----------
    _CSS_EFFECT_PATTERNS = (
        ('linear-gradient', '线性渐变'), ('radial-gradient', '径向渐变'),
        ('box-shadow', '阴影'), ('text-shadow', '文字阴影'),
        ('border-radius', '圆角'), ('animation', '动画'), ('transition', '过渡'),
        ('transform', '变换/旋转'), ('filter', '滤镜'), ('opacity', '透明度'),
    )
    # 真的会调 `_effect_assets` 出图的控件类型（2026-10-04 补，防"假声明"）：
    #   window/modal → `_open_window`；textview/button → `_leaf` 对应分支；seekbar → `_seekbar_css_assets`
    # 其余类型（icon/circlebar/checkbox/radiogroup/listview/…）的分支**从不**调 `_effect_assets`
    # （icon 只走自己的 iconfont/emoji 出图）→ 不许再说「已自动转成图片」，一律走「请切图」那一条。
    _EFFECT_CONSUMERS = ('window', 'modal', 'textview', 'button', 'seekbar')

    def _convertible_effects(self, node, style, hit, typ=None):
        """本次会被 gen_res 自动烘焙成图的效果名（与 `_effect_assets` 同一套条件 + **消费方口径**）。

为什么要算（v0.27.33 修「误导提示」）：转图能力可用时，线性渐变/阴影+圆角/loading 动画
本来就会自动出图并写进 json（实测 grad_/shadow_/loading_*.png + backgroundPic/playFile），
旧文案却一律喊「无法硬转，请切图」——让 AI 以为转图失败了、白做一轮手工切图。

⚠️ 2026-10-04 修**假声明**（实测）：本函数原先只看「效果种类」，不看**该控件类型的分支有没有
调用 `_effect_assets`** → 对 seekbar/circlebar/checkbox… 这些分支从不调用它的类型，
会输出「…的 CSS 效果**已自动转成图片**（json 已引用 images/*.png）」，而实际 `generatedAssets: 0`、
输出目录连 images/ 都没有。现在按 `_EFFECT_CONSUMERS` 只在真有消费路径时才认。
        """
        if not (_HAS_GEN_RES and getattr(self, 'asset_dir', None)):
            return set()
        if typ is not None and typ not in self._EFFECT_CONSUMERS:
            return set()
        cls = _classes(node.attrs)
        out = set()
        # seekbar 走 `_seekbar_css_assets`（把背景+圆角烘进轨道图），**不**走 _effect_assets：
        # 只认「真的烘进轨道图」的那两项（圆角 / 轨道自身的渐变），阴影仍归"请切图"。
        if typ == 'seekbar':
            spec = _bg_spec(style)
            if spec is not None:
                out.add('圆角')
                if spec[0] == 'gradient':
                    out.add('线性渐变')
            return {h for h in hit if h in out}
        # 线性渐变 → gen_res 渐变图（径向渐变不支持，实测不转）
        if 'linear-gradient' in style and 'radial-gradient' not in style:
            out.add('线性渐变')
        # 卡片阴影 + 圆角 → 一并烘焙成带外描的 PNG（文字阴影不在其中）
        if _shadow_spec(style):
            out.add('圆角')
            if 'text-shadow' not in style:
                out.add('阴影')
        # loading/spinner 式动画 → 序列帧 GIF（imageanim）
        if ('loading' in cls or 'spinner' in cls or
                (re.search(r'animation\s*:', style) and
                 ('spin' in style or 'rotate' in style or 'loading' in style))):
            out.add('动画')
        return {h for h in hit if h in out}

    def _warn_css_effects(self, ctx, node, typ=None):
        """检测 style 里的 CSS 效果属性：能自动转图的说明「已转图」，转不了的提示切图。

两类分开说：
          - 已转图（渐变/阴影+圆角/loading 动画）→ 信息提示，避免 AI 白做手工切图
          - 转不了（径向渐变/文字阴影/变换/滤镜/透明度/过渡）→ 保留「请切图 + data-pic」指引
        typ：节点将被转成的控件类型（决定该类型的分支是否真的会出图，见 `_convertible_effects`）。
        """
        if _attr(node.attrs, 'data-pic'):
            return   # 作者已按规范切图（data-pic）引用，效果就在图里，不必再提示
        style = _attr(node.attrs, 'style') or ''
        if not style:
            return
        hit = [name for pat, name in self._CSS_EFFECT_PATTERNS if pat in style]
        if not hit:
            return
        conv = self._convertible_effects(node, style, hit, typ)
        rest = [h for h in hit if h not in conv]
        cls = _attr(node.attrs, 'class') or ''
        if conv:
            ctx.warnings.append(
                f'<{node.tag} class="{cls}"> 的 CSS 效果（{"、".join(sorted(conv))}）**已自动转成图片**'
                f'（PNG/序列帧，尺寸 == 控件盒，json 已引用 images/*.png）；FlyThings 没有 CSS 引擎，'
                f'改外观请改图或控件属性，不要指望写 CSS 生效。'
                f'（若该控件类型没生成对应图，再用 data-pic 自备图（PNG，尺寸 == 控件盒））')
        if rest:
            ctx.warnings.append(
                f'<{node.tag} class="{cls}"> 含 CSS 效果（{"、".join(rest)}）：'
                f'FlyThings 不支持 CSS，无法硬转；请切图（PNG/.9.png/序列帧/GIF）后 '
                f'用 data-pic 引用（效果转图片 + 控件组合实现）')

    def _walk(self, ctx, node):
        classes = _classes(node.attrs)
        tag = node.tag

        # 控件类型（提前算：CSS 效果告警要说清「这个类型到底会不会出图」，
        # 免得对 seekbar/checkbox 之类从不调用 _effect_assets 的分支发假声明）
        typ = _detect_type(tag, classes, node.attrs)

        # ⚠️ CSS 效果检测（不硬转，提示转图片）
        self._warn_css_effects(ctx, node, typ)

        # 弹窗（modal）
        if tag == 'div' and any(k in classes for k in CLASS_MAP['modal']):
            self._open_window(ctx, node, modal=True)
            for ch in node.children:
                self._walk(ctx, ch)
            ctx.stack.pop()
            return

        # 容器窗口（card/window/panel）
        if tag == 'div' and any(k in classes for k in CLASS_MAP['window']):
            self._open_window(ctx, node, modal=False)
            for ch in node.children:
                self._walk(ctx, ch)
            ctx.stack.pop()
            return

        # typ 已在函数开头算过（供 CSS 效果告警判定消费方），这里不再重复 _detect_type

        # 在 radiogroup 容器内：子 div.radio 收进父容器 radiobuttons（RadioGroupDemo 校准）
        if ctx.stack and ctx.stack[-1].get('__radiogroup') and typ == 'radiogroup':
            self._leaf(ctx, node, 'radiobutton')
            return

        # 在 diagram 容器内：子 div.wave 收进父容器 infos（每条波形配置）
        if ctx.stack and ctx.stack[-1].get('__diagram') and typ == 'diagram':
            self._append_wave(ctx, node)
            return

        # 在 slidewindow 容器内：子 div.item 收进父容器 items（每个图标项）
        if ctx.stack and ctx.stack[-1].get('__slidewindow') and tag == 'div':
            # 不静默（2026-10-05）：slidewindow 的子内容**只能是图标项**。写了控件 class 或绝对定位时，
            # 以前是静默当图标项（位置尺寸/控件行为全丢，warnings 里只有 iconSize 那条）——
            # 生成侧的结构因此「安全但会吃掉意图」，必须说出来。
            # 判据只认**显式控件 class** 或**定位键**：`div.item` 是合法写法（不能见 slidewindow 就报）。
            matched = sorted(classes & _CTRL_CLASSES)
            if matched or any(a in node.attrs for a in _POS_ATTRS):
                ctx.warn('slidewindow 的子内容只能是图标项（div.item）：%s 已按图标项处理'
                         '（只取 data-pic/data-pic1/text），data-x/y/w/h 与控件行为全部丢弃 —— '
                         '要放真控件 / 要绝对定位请改用 window 容器（万能容器）；要图标宫格请写 div.item'
                         % (('class="%s"' % matched[0]) if matched else '这个 div'),
                         key='slidewindow-child-not-item')
            self._append_slideitem(ctx, node)
            return

        # listview/radiogroup 内的纯容器 div（.item/.subitem/.row 或无任何控件 class）：
        # 展开其子节点逐个生成 subItem/radiobutton，不把包裹层本身当控件吞掉内部内容
        if ctx.stack and ctx.stack[-1].get('__listview') and tag == 'div':
            ctrl_classes = set()
            for keys in CLASS_MAP.values():
                ctrl_classes.update(keys)
            if not (classes & ctrl_classes):
                for ch in node.children:
                    self._walk(ctx, ch)
                return

        # 列表（listview）
        if typ == 'listview':
            self._open_listview(ctx, node)
            for ch in node.children:
                self._walk(ctx, ch)
            ctx.stack.pop()
            return

        # 单选组（radiogroup）
        if typ == 'radiogroup':
            self._open_radiogroup(ctx, node)
            for ch in node.children:
                self._walk(ctx, ch)
            ctx.stack.pop()
            return

        # 波形图（diagram）容器：子 div.wave 收进 infos 数组（UIlayoutDemo/diagram.ftu 校准）
        if typ == 'diagram':
            self._open_diagram(ctx, node)
            for ch in node.children:
                self._walk(ctx, ch)
            ctx.stack.pop()
            return

        # 波形图（diagram）容器：子 div.wave 收进 infos 数组（UIlayoutDemo/diagram.ftu 校准）
        if typ == 'diagram':
            self._open_diagram(ctx, node)
            for ch in node.children:
                self._walk(ctx, ch)
            ctx.stack.pop()
            return

        # 滑动窗口（slidewindow）容器：Android 主页式，子 div.item 收进 items 数组（UIlayoutDemo/main.ftu 校准）
        if typ == 'slidewindow':
            self._open_slidewindow(ctx, node)
            for ch in node.children:
                self._walk(ctx, ch)
            ctx.stack.pop()
            return

        # 滚动窗口（scrollwindow）容器：滚动内容 window 嵌套其内（UIlayoutDemo/setting.ftu 校准）
        if typ == 'scrollwindow':
            self._open_scrollwindow(ctx, node)
            for ch in node.children:
                self._walk(ctx, ch)
            ctx.stack.pop()
            return

        # 翻页窗口（pagewindow）容器：页面 window 嵌套其内（PageWindowDemo-New/main.ftu 校准）
        if typ == 'pagewindow':
            self._open_pagewindow(ctx, node)
            for ch in node.children:
                self._walk(ctx, ch)
            ctx.stack.pop()
            return

        # 叶子控件
        self._leaf(ctx, node, typ)

    # ---------- 根节点 ----------
    def _screen_size(self, node):
        """.screen 分辨率：res 参数 > data-res > data-width+data-height（.screen 上直接写宽高）
        > style 里的 width/height > 默认 480x272。

        （res 参数给了但不合法时保持默认 480x272，与旧版行为一致。）"""
        attrs = node.attrs
        res = self.res or _attr(attrs, 'data-res')
        W, H = 480, 272
        if res:
            m = re.match(r'^\s*(\d+)\s*[xX]\s*(\d+)\s*$', str(res))
            if m:
                return int(m.group(1)), int(m.group(2))
            return W, H
        w_attr = parse_px(_attr(attrs, 'data-width'))
        h_attr = parse_px(_attr(attrs, 'data-height'))
        if w_attr and h_attr:
            return w_attr, h_attr
        style_pos = _style_pos(_attr(attrs, 'style') or '')
        if style_pos.get('width') and style_pos.get('height'):
            return style_pos['width'], style_pos['height']
        return W, H

    def _open_screen(self, ctx, node):
        attrs = node.attrs
        W, H = self._screen_size(node)
        # 背景色：data-background 与 data-bg 互为别名；不写则透明（不设 backgroundColor，navibar/statusbar 校准）
        bg = to_dec(_attr(attrs, 'data-background'))
        if bg is None:
            bg = to_dec(_attr(attrs, 'data-bg'))
        if bg is None:
            # CSS 背景传播（2026-10-04 真机实测补）：html/body 的 background 铺满画布。
            # 不写根底色 = 真机**不擦屏** → 会残留上一页/屏保（实测：body 带 background 时整屏盖着屏保）。
            bg = getattr(self, '_page_bg', None)
            if bg is not None:
                ctx.warn('页面底色取自 CSS 的 html/body background（#%06X）—— 已写进 json 根 '
                         'backgroundColor（.screen 自己没有 data-bg）' % bg, key='screen-bg-from-body')
        else:
            # 纯黑也会走到这里：`_color_explicit` 那套"按属性出现性判定"在根上同样适用
            pass
        root = {
            'beepEnable': True, 'id': 0,
            'resolution': {'height': H, 'width': W},
            'topmost': str(_attr(attrs, 'data-topmost') or '').strip() in ('1', 'true'),
        }
        if bg is not None:
            root['backgroundColor'] = bg
        else:
            ctx.warn('页面根没有底色（.screen 无 data-bg，html/body 也没写 background）→ 真机**不擦屏**，'
                     '会露出上一页/屏保的残留画面（2026-10-04 实机验证：CSS 的 background 只写在 body 上时'
                     '整屏残留旧帧）→ 给 .screen 加 data-bg 或给 body 写 background'
                     '（需切图确认外观）', key='screen-bg-missing')
        # 根 position：默认全屏；只有显式写 data-x/y/w/h（或 data-left/top/width/height / style 定位）
        # 才作为局部悬浮块（statusbar/navibar 校准），否则强制全屏（PageWindowDemo 回归验证）
        # ⚠️ 2026-10-04：值必须是**可解析的绝对像素**才算"写定位"。最小 CSS 层叠上线后，
        # `<style>` 里极常见的 `.screen{width:100%;height:100%}` 会进 style 属性 ——
        # 若只按"键出现过"判定，整个屏会被缩成 100×40 的小块（`_pos` 解析不了 % → 落默认值）。
        def _has_pos_attr(a):
            for k in ('data-x', 'data-y', 'data-w', 'data-h',
                      'data-left', 'data-top', 'data-width', 'data-height'):
                if parse_px(_attr(a, k)) is not None:
                    return True
            st = _attr(a, 'style') or ''
            return any(_style_len(st, k) is not None for k in ('left', 'top', 'width', 'height'))
        if _has_pos_attr(attrs):
            root['position'] = self._pos(attrs)
        else:
            root['position'] = {'height': H, 'left': 0, 'top': 0, 'width': W}
        ctx.root = root

    # ---------- 容器 ----------
    def _open_window(self, ctx, node, modal):
        attrs = node.attrs
        cap = self._caption(ctx, 'window', attrs)
        pos = self._pos(attrs)
        # 字段全集 v2（SampleUI-New 基准 2026-09-08）：window 必写
        #   backgroundColor/hideTimeOut/modal/touchable/visible 含默认也显式（-1/false）；beepEnable 不强制（）
        c = {'backgroundColor': -1, 'caption': cap,
             'hideTimeOut': -1, 'id': ctx.nid('window'),
             'modal': False,
             'position': pos,
             'touchable': False, 'visible': True}
        # 弹窗（modal）默认隐藏；普通卡片/容器窗口默认可见
        if modal:
            c['visible'] = False
            c['modal'] = True
        # hideTimeOut：模态自动隐藏秒数（模态 8 秒实测；-1 不自动隐藏）
        hto = parse_px(_attr(attrs, 'data-hide-timeout'))
        if hto is not None:
            c['hideTimeOut'] = hto
        # 纯色背景（WindowDrag 无背景图用 backgroundColor 6323852 实测）
        bgc = self._bg_color(attrs)
        if bgc is not None:
            c['backgroundColor'] = bgc
        c['__bg'] = bgc          # A6：子控件圆角外底色取「最近祖先」（__ 前缀键在收尾时被剥离）
        # ⭐ 2026-10-04（需求方改口径）：纯色 + 倒角的卡片 → **出 `.9.png` 背景图**（不是 painter）。
        #   window 没有 radius 字段，纯色倒角此前**静默丢失**；.9.png 的九宫格保证任意尺寸四角不变形，
        #   且不需要任何代码。本控件自己的方角底色必须让位给「背后底色」（A6 口径）。
        _pic_ahead = _attr(attrs, 'data-pic') or _attr(attrs, 'data-bgpic')
        if not _pic_ahead and not re.search(r'linear-gradient|box-shadow', _attr(attrs, 'style') or ''):
            _pic9, _info9 = self._radbox_9pic(ctx, node, pos, cap, kind='window')
            if _pic9:
                c['backgroundPic'] = _pic9
                c['backgroundColor'] = _info9['behind']   # 圆角外透出背后底色（不能留 -1：引擎缺省是黑）
        # A5 修：data-visible 直通（容器初始隐藏；模态默认 visible=false，作者显式写则以其为准）
        _dv = _bool_attr(attrs, 'data-visible')
        if _dv is not None:
            c['visible'] = _dv
        pic = _attr(attrs, 'data-pic')
        if pic:
            c['backgroundPic'] = pic if '/' in pic else 'images/' + pic
        else:
            # 自动转图：CSS 效果（渐变/阴影/emoji）→ 背景图
            eff = self._effect_assets(ctx, node, pos.get('width', 100), pos.get('height', 40), cap)
            if eff.get('backgroundPic'):
                c['backgroundPic'] = eff['backgroundPic']
                if eff.get('pad'):
                    # 阴影图画布比控件大 2*pad：控件盒同步外扩 + 子控件坐标由 _pos() 补偿 +pad
                    # → 图==控件 1:1（check_all #11），可见卡片主体仍落在作者给定坐标
                    _grow(pos, eff['pad'])
                    c['__pad'] = eff['pad']
                    # ⚠️ 2026-09-11：阴影图带透明外扩边，控件底色必须取**页面底色**——
                    # 否则整块外扩区被控件底色（本例白）填满 → 阴影渐变/圆角都看不出来。
                    # 卡体填充色已烘焙进阴影图，不需要控件再填一次。
                    root_bg = (ctx.root or {}).get('backgroundColor')
                    if root_bg is not None:
                        c['backgroundColor'] = root_bg
                        c['__bg'] = root_bg
                    ctx.warnings.append(
                        f'{cap}: box-shadow → 阴影图 {pos["width"]}x{pos["height"]}'
                        f'（含 {eff["pad"]}px 阴影外扩）；控件盒已外扩、子控件已补偿，无需手工调整')
        c['__container'] = True
        key = ctx.add('window', c)   # 支持嵌套（scrollwindow 内嵌 window、window 内嵌 window）
        ctx.stack.append(c)

    def _open_listview(self, ctx, node):
        attrs = node.attrs
        cap = self._caption(ctx, 'listview', attrs)
        # listview.item 子结构 v2.1（SampleUI item 17 键 100%，不含 id）：补安全默认键；
        # ⚠️ position 必写（2026-09-08）：行高 = lv高/rows - rowSpacing（公式见函数尾）；iconPosition/textPosition 布局键条件写
        item = {'alignment': 37, 'backgroundColor': -1, 'bgColorTab': {'color0': -1},
                'bold': False, 'caption': 'item',
                'colorTab': {'color0': 16777215}, 'fontSize': 16,
                'italic': False, 'longClickIntervalTime': -1, 'longClickTimeOut': -1,
                'picTab': {}, 'text': '',
                # ⚠️ 2026-09-16：item.text 默认留空（原来是 'ListItem'，会导致列表每行常显一个 "ListItem"）
                'touchable': True, 'visible': True, 'subItem': []}
        c = {'autoRollback': False, 'backgroundColor': -1, 'caption': cap,   # SampleUI listview 必写键（去 beepEnable）
             'cols': 1, 'cycleEnable': False, 'dragMaxDis': 0, 'edgeEffect': 0,
             'hasScrollbar': True, 'id': ctx.nid('listview'),
             'rows': 5, 'position': self._pos(attrs),
             'colSpacing': 0, 'rowSpacing': 1, 'orientation': 1,
             'touchable': True, 'visible': True,
             'item': item,
             '__container': True, '__listview': True}
        cols = parse_px(_attr(attrs, 'data-cols'))
        rows = parse_px(_attr(attrs, 'data-rows'))
        if cols:
            c['cols'] = cols
        if rows:
            c['rows'] = rows
        rs = parse_px(_attr(attrs, 'data-row-spacing'))
        cs = parse_px(_attr(attrs, 'data-col-spacing'))
        if rs is not None:
            c['rowSpacing'] = rs
        if cs is not None:
            c['colSpacing'] = cs
        # 滚动/循环属性（listViewDemo 校准）：autoRollback 自动回滚 + cycleEnable 循环 + dragMaxDis/edgeEffect + hasScrollbar
        ar = _attr(attrs, 'data-auto-rollback')
        if ar is not None:
            c['autoRollback'] = str(ar).strip() in ('1', 'true')
        cy = _attr(attrs, 'data-cycle')
        if cy is not None:
            c['cycleEnable'] = str(cy).strip() in ('1', 'true')
        dmd = parse_px(_attr(attrs, 'data-drag-max'))
        if dmd is not None:
            c['dragMaxDis'] = dmd
        ee = parse_px(_attr(attrs, 'data-edge-effect'))
        if ee is not None:
            c['edgeEffect'] = ee
        sb = _attr(attrs, 'data-scrollbar')
        if sb is not None:
            c['hasScrollbar'] = str(sb).strip() in ('1', 'true')
        # ⚠️ item.position 必写（2026-09-08）
        # 行高公式 = lv高/rows 均分 - rowSpacing（basedemo-new_z20_1024_600 验证：164/4-5=36✓ 437/3-5≈140✓ 424/5-0=84✓；
        # SampleUI 216x275 rows5→55 同吻合）；item 宽 = lv 宽
        _lvp = c['position']
        _ih = int(_lvp.get('height', 0) / max(c.get('rows') or 5, 1)) - (c.get('rowSpacing') or 0)
        item['position'] = {'left': 0, 'top': 0,
                            'width': _lvp.get('width', 100),
                            'height': max(_ih, 1)}
        key = ctx.add('listview', c)   # 支持嵌套（listview 在 window 内）
        ctx.stack.append(c)

    # ---------- 纯色倒角 → zk::ui_v1::RadButton（2026-10-04 需求方决策）----------
    # 决策：**纯色 + border-radius 的普通按键 → RadButton**（painter 自绘 AA 倒角，无资产）；
    #       **带渐变 / 背景图的 → ZKButton + 生成切图**（倒角烘进图）。二选一。
    # 为什么必须出代码：RadButton 是「一个 painter + 一份代码」——json 里只是 `painter__N`，
    #   真正的倒角由 `RadButton::attach/setStyle/refresh` 在设备上画（painter 不自动重绘，
    #   不调 refresh 则**什么都不显示**）。所以本函数同时产出**可直接粘贴的胶水代码**，
    #   放进返回体的 `radButtonGlue` 字段（不写工程里的 Logic.cc —— 那是业务文件，不许覆盖）。
    _RAD_GLUE_TMPL = """/* ---- %(cap)s: zk::ui_v1::RadButton（由 html2json 生成，粘进 src/logic/<page>Logic.cc）----
   组件源码：把 components/ui_v1/RadButton/src/zk/zk_radbutton.{h,cpp} 拷进工程 src/zk/（一次性）
   必须 3 步：setStyle + attach + refresh；`st.bg` 必须是按钮背后的**真实底色**（AA 混色基准） */
#include "zk/zk_radbutton.h"
static zk::ui_v1::RadButton s_%(cap)s;

/* onUI_init() 里： */
    zk::ui_v1::RadButton::Style st_%(cap)s = zk::ui_v1::RadButton::defaultStyle();
    st_%(cap)s.radius = %(radius)d;              /* CSS border-radius */
    st_%(cap)s.bg     = %(bg)s;   /* ★ 按钮背后的真实底色（AA 混色基准，取自 CSS/祖先容器） */
    st_%(cap)s.normal = %(normal)s;              /* CSS background-color */
%(extra)s    s_%(cap)s.setStyle(st_%(cap)s);
    s_%(cap)s.attach(m%(cap)sPtr);               /* json 里的 painter__N */
    s_%(cap)s.refresh();                         /* ★ 不调什么都不显示；切页回来要再调一次 */
"""

    # 2026-10-04 需求方口径：卡片/文本块的纯色倒角**不走 RadButton**（那是给按键的），
    #   改出 `.9.png` 背景图（`_radbox_9pic`）—— 静态底不需要四态/触摸语义，也就不用往 Logic.cc 粘胶水。
    #   所以这里只剩按键那一种胶水模板（`_RAD_GLUE_TMPL`）。

    def _rad_button_of(self, ctx, node, pos, cap, fill_int=None, behind=None):
        """公共部分：算「纯色 + 倒角」判据、背后底色，并登记一段胶水。返回 dict 或 None。

        判据（三条都满足才走 RadButton 路线，否则交回出图那套）：
          ① `border-radius` > 0；
          ② 背景是**纯色**（有 linear/radial-gradient、box-shadow、data-pic/data-bgpic 的一律不接）；
          ③ 有底色可读（spec 的纯色 或 data-bg）。
        """
        attrs = node.attrs
        style = _attr(attrs, 'style') or ''
        radii = _radius_corners(style, pos.get('width', 100), pos.get('height', 40))
        r = int(round(max(radii)))
        if r <= 0:
            return None
        if (re.search(r'linear-gradient|radial-gradient|box-shadow', style)
                or _attr(attrs, 'data-pic') or _attr(attrs, 'data-pic0')
                or _attr(attrs, 'data-bgpic') or _attr(attrs, 'data-background-pic')
                or _glyph_from_attrs(attrs)):
            return None
        spec = _bg_spec(style)
        bgc_int = self._bg_color(attrs)
        if not (spec and spec[0] == 'color') and bgc_int is None:
            return None
        fill = spec[1] if (spec and spec[0] == 'color') else None
        fill_int = ((fill[0] << 16) | (fill[1] << 8) | fill[2]) if fill else bgc_int
        if behind is None:
            for v in reversed(list(ctx.stack)):
                if isinstance(v, dict) and (v.get('__bg') is not None
                                            or v.get('backgroundColor') not in (None, -1)):
                    behind = v.get('__bg') if v.get('__bg') is not None else v.get('backgroundColor')
                    break
        if behind is None or behind < 0:
            behind = (ctx.root or {}).get('backgroundColor')
        if behind is None or behind < 0:
            behind = 0xFFFFFF
            ctx.warn('%s：走 RadButton（纯色倒角）路线，但**背后底色**取不到（祖先容器与页面根都没底色）'
                     '→ 胶水里先按白 0xFFFFFF 兜底，请改成实际底色，否则倒角边缘会有一圈颜色不对的边'
                     '（components/ui_v1/RadButton/README.md §8）' % cap, key='radbutton-bg')
        return {'radius': r, 'radii': radii, 'fill': fill_int, 'behind': behind}

    def _try_radbutton(self, ctx, node, pos, cap, text):
        """纯色 + 倒角的普通按键 → `painter__N`(RadButton 画布) + 透明热区 `button__N` + 胶水代码。

        2026-10-04 需求方决策：**纯色倒角走 zk::ui_v1::RadButton，带渐变/背景图的走 ZKButton+切图**。
        背景：`button__N`/ZKButton 的 json 里**没有 radius 字段**（RadButton README §0），
        所以纯色倒角若走 ZKButton 只能靠切图；RadButton 是「一个 painter + 一份代码」。
        返回 True = 已产出（调用方直接 return）。
        """
        info = self._rad_button_of(ctx, node, pos, cap)
        if not info:
            return False
        attrs = node.attrs
        W = int(pos.get('width', 100) or 100)
        H = int(pos.get('height', 40) or 40)
        rcap = cap + 'Rad'
        # ① painter（RadButton 画布）：z 更低，先加
        pk = ctx.add('painter', {'backgroundColor': -1, 'caption': rcap,
                                 'id': ctx.nid('painter'), 'position': pos,
                                 'touchable': False, 'visible': True})
        # ② 热区按钮（文字 + 触摸）：**不带底色**，用全透明切图保证不遮住下层 painter
        c = {'alignment': ALIGN.get((_attr(attrs, 'data-align') or 'center').lower(), 37),
             'caption': cap,
             'colorTab': {'color0': _color_explicit(attrs, 'data-color', 0xEEF2F6)},
             'id': ctx.nid('button'), 'position': pos, 'touchable': True}
        hit = self._gen_asset(lambda d: _save_css_png(
            _I_new_rgba(W, H, self._rgba_of(info['behind'])), d, 'btn_%s_hit.png' % cap))
        c['picTab'] = {'pic0': hit or '', 'pic1': hit or ''}
        fs = self._font_size(attrs)
        if fs:
            c['fontSize'] = fs
        if text:
            c['text'] = text
        ctx.add('button', c)
        extra = ''
        if len(set(info['radii'])) > 1:
            extra = ('    /* ⚠️ CSS 是四角不同半径（%s）；RadButton 只有单一半径，已取最大 %d */\n'
                     % ('/'.join('%g' % v for v in info['radii']), info['radius']))
        code = self._RAD_GLUE_TMPL % {'cap': rcap, 'radius': info['radius'],
                                      'bg': '0x%06X' % info['behind'],
                                      'normal': '0x%06X' % info['fill'], 'extra': extra}
        self._rad_glue.append({'caption': rcap, 'kind': 'RadButton', 'radius': info['radius'],
                               'bg': '0x%06X' % info['behind'], 'fill': '0x%06X' % info['fill'],
                               'code': code})
        ctx.warn('%s：纯色 + border-radius=%dpx → 按**需求方决策**走 `zk::ui_v1::RadButton`'
                 '（painter 自绘 AA 倒角，不出切图）：json 已出 `%s`（RadButton 画布，z 更低）+ 透明热区 '
                 '`button__N`（文字/触摸，picTab 是全透明图 → 不遮画布）。'
                 '**倒角由代码画**：把返回体 radButtonGlue 里那段粘进 src/logic/<page>Logic.cc'
                 '（setStyle+attach+refresh 三步；缺 refresh 什么都不显示），并把 '
                 'components/ui_v1/RadButton/src/zk/zk_radbutton.{h,cpp} 拷进工程 src/zk/'
                 % (cap, info['radius'], pk), key='radbutton:%s' % cap)
        return True

    def _radbox_9pic(self, ctx, node, pos, cap, kind):
        """卡片(window)/文本块(textview) 的**纯色 + 倒角** → 出一张 **`.9.png` 背景图**（需求方决策）。

        为什么不是 painter（2026-10-04 需求方改口径）：「卡片文本直接出 .9.png 背景图」——
        纯色倒角按键才走 RadButton（要四态/触摸语义），卡片/文本块只是**静态底**，
        .9.png 一次出图就够：**九宫格保证任意尺寸下四角不被拉伸**（角切片不参与缩放），
        比 painter+代码省事（不需要往 Logic.cc 粘胶水）。

        口径（A6 同款）：出图后本控件自己的方角底色必须让位 ——
          · window：`backgroundColor` 换成**最近祖先/页面底色**（不是 -1：引擎缺省是黑，会露黑角）；
          · textview：`bgColorTab` 由 `_corner_bg` 按「祖先底色」写。
        返回 (pic_ref, info) 或 (None, None)。
        """
        info = self._rad_button_of(ctx, node, pos, cap)
        if not info:
            return None, None
        W = int(pos.get('width', 100) or 100)
        H = int(pos.get('height', 40) or 40)
        r = info['radius']
        fill = info['fill']
        rgba = ((fill >> 16) & 0xFF, (fill >> 8) & 0xFF, fill & 0xFF, 255)
        name = '%s_%s.9.png' % ('card' if kind == 'window' else 'pill', cap or ctx.n)

        def _g(d, _n=name, _w=W, _h=H, _r=r, _c=rgba):
            # 圆角底图（覆盖率口径 AA）→ 打九宫格引导线；再按 8bit 索引色落盘省存储
            img = gr.rounded_rect_cov(_w, _h, _r, _c)
            p = gr.to_9patch(img, _r, d, _n)
            try:
                with _I_open(p) as im:
                    _save_css_png(im.convert('RGBA'), d, _n)
            except Exception:
                pass
            return p

        pic = self._gen_asset(_g)
        if not pic:
            return None, None
        anc = self._ancestor_bg(ctx)
        if anc is None or anc < 0:
            anc = 0xFFFFFF
            ctx.warn('%s：出 .9.png 倒角底图，但**背后底色**取不到（祖先容器与页面根都没底色）→ '
                     '圆角外的方角会按引擎缺省（常是黑）渲染；请给页面/容器补底色（A6 口径）'
                     % cap, key='rad9-bg:%s' % cap)
        ctx.warn('%s：纯色 + border-radius=%dpx 的%s（%s 没有 radius 字段）→ 已出 **`.9.png` 背景图** '
                 '`%s`（九宫格：四角不参与拉伸，任意尺寸都不变形；8bit 索引色省存储）。'
                 '本控件的方角底色已让位（改用背后底色 0x%06X）—— 无需任何代码'
                 % (cap, r, '卡片' if kind == 'window' else '文本块',
                    'window' if kind == 'window' else 'textview', pic, anc),
                 key='rad9:%s' % cap)
        return pic, {'radius': r, 'fill': fill, 'behind': anc}

    def _rgba_of(self, cint):
        return ((cint >> 16) & 0xFF, (cint >> 8) & 0xFF, cint & 0xFF, 0)

    def _open_diagram(self, ctx, node):
        """波形图：backgroundPic 背景图 + xAxisRange/yAxisRange 坐标范围 + region 绘图区 + infos[] 波形配置。
子 div.wave 每条收进 infos（penColor/penWidth/step/style/antialias/eraseSpace/xScale/yScale）。
        style: 0=折线 1=曲线（UIlayoutDemo/diagram.ftu 校准）；eraseSpace=刷新间距。
        """
        attrs = node.attrs
        cap = self._caption(ctx, 'diagram', attrs)
        pos = self._pos(attrs)
        c = {'backgroundColor': -1, 'caption': cap, 'id': ctx.nid('diagram'),
             'touchable': True, 'visible': True,   # SampleUI diagram touchable 主 true
             'position': pos,
             'xAxisRange': {'lower': _num(_attr(attrs, 'data-x-min'), 0),
                            'upper': _num(_attr(attrs, 'data-x-max'), 100)},
             'yAxisRange': {'lower': _num(_attr(attrs, 'data-y-min'), 0),
                            'upper': _num(_attr(attrs, 'data-y-max'), 100)},
             'region': {'left': 0, 'top': 0, 'width': pos.get('width', 300),
                        'height': pos.get('height', 300)},
             '__container': True, '__diagram': True, 'infos': []}
        bg = _attr(attrs, 'data-bgpic') or _attr(attrs, 'data-background-pic') or _attr(attrs, 'data-bg')
        if bg and not bg.startswith('#'):
            c['backgroundPic'] = bg if '/' in bg else 'images/' + bg
        key = ctx.add('diagram', c)   # 支持嵌套
        ctx.stack.append(c)

    def _open_slidewindow(self, ctx, node):
        """滑动窗口（Android 主页式，UIlayoutDemo/main.ftu 校准）：
        cols/rows 每页行列 + iconSize 图标尺寸 + iconTextAlignment 文字对齐 + iconTextPadding/padding 间距 +
        dragMaxDis 最大拖动距离 + edgeEffect 边缘效果 + orientation 方向 + rollSpeed 滚动速度 + items[] 图标项数组。
子 div.item 每条收进 items（picTab 两态图 + text 文字）。
        """
        attrs = node.attrs
        cap = self._caption(ctx, 'slidewindow', attrs)
        pos = self._pos(attrs)
        c = {'caption': cap,
             'cols': int(_num(_attr(attrs, 'data-cols'), 4)),
             'rows': int(_num(_attr(attrs, 'data-rows'), 2)),
             'dragMaxDis': int(_num(_attr(attrs, 'data-drag-max'), 200)),
             'edgeEffect': int(_num(_attr(attrs, 'data-edge-effect'), 1)),
             'iconSize': {'width': int(_num(_attr(attrs, 'data-icon-w'), 128)),
                          'height': int(_num(_attr(attrs, 'data-icon-h'), 128))},
             'iconTextAlignment': int(_num(_attr(attrs, 'data-icon-align'), 41)),
             'iconTextPadding': {'bottom': int(_num(_attr(attrs, 'data-icon-pad-b'), 5)),
                                 'left': 0, 'right': 0, 'top': 0},
             'id': ctx.nid('slidewindow'),
             'orientation': int(_num(_attr(attrs, 'data-orientation'), 0)),
             'padding': {'paddingBottom': int(_num(_attr(attrs, 'data-pad-b'), 8)),
                         'paddingLeft': 0, 'paddingRight': 0, 'paddingTop': 0},
             'position': pos,
             'rollSpeed': int(_num(_attr(attrs, 'data-roll-speed'), 999)),
             'fontSize': 22, 'backgroundColor': -1,
             'touchable': True, 'visible': True,
             '__container': True, '__slidewindow': True, 'items': []}
        # 用户显式指定过图标尺寸 → 后处理不覆盖（_fix_slidewindow_icon_size 用）
        if _attr(attrs, 'data-icon-w') or _attr(attrs, 'data-icon-h'):
            c['__icon_explicit'] = True
        fs = self._font_size(attrs)
        if fs:
            c['fontSize'] = fs
        # 背景图 + 图标最大尺寸（SlideWindowDemo 校准）
        bgp = _attr(attrs, 'data-bgpic') or _attr(attrs, 'data-background-pic')
        if bgp:
            c['backgroundPic'] = bgp if '/' in bgp else 'images/' + bgp
        imx = parse_px(_attr(attrs, 'data-icon-max'))
        if imx:
            c['iconMaxSize'] = {'width': imx, 'height': imx}
        key = ctx.add('slidewindow', c)   # 支持嵌套
        ctx.stack.append(c)

    def _open_scrollwindow(self, ctx, node):
        """滚动窗口（UIlayoutDemo/setting.ftu 校准）：
        dragMaxDis **越界拖拽上限**（overscroll，不是行程） + orientation 滑动方向（垂直/水平） + edgeEffect 边界效果（拖拽/无/循环）。
滚动内容 = 内嵌的普通 window（如 ScrollWin 2400）——**它的尺寸才是行程**（行程 = 内层 window 尺寸 − 视口）。
口径（2026-10-01 需求方修正）：别拿 dragMaxDis 算行程/判滚没滚到底，见 knowledge/uicontrols/scroll-drag-interaction-spec.md。
        """
        attrs = node.attrs
        cap = self._caption(ctx, 'scrollwindow', attrs)
        c = {'caption': cap,
             'dragMaxDis': 200, 'edgeEffect': 1,
             'id': ctx.nid('scrollwindow'),
             'orientation': 0,
             'position': self._pos(attrs)}  # dragMaxDis = 越界拖拽上限（不是行程；行程由内层 window 尺寸定，见 scroll-drag-interaction-spec.md §0）
        dmd = parse_px(_attr(attrs, 'data-drag-max'))
        if dmd is not None:
            c['dragMaxDis'] = dmd
        ori = parse_px(_attr(attrs, 'data-orientation'))
        if ori is not None:
            c['orientation'] = ori
        ee = parse_px(_attr(attrs, 'data-edge-effect'))
        if ee is not None:
            c['edgeEffect'] = ee
        c['__container'] = True
        key = ctx.add('scrollwindow', c)   # 支持嵌套（滚动内容 window 嵌进来）
        ctx.stack.append(c)

    def _open_pagewindow(self, ctx, node):
        """翻页窗口（PageWindowDemo-New/main.ftu 校准）：
        dragMaxDis 最大拖动距离 + orientation 滑动方向 + edgeEffect 边界效果 + rollSpeed 滚动速度。
页面 = 多个同尺寸 window 叠放（Window1/2/3 各 400×260），代码 turnToNextPage/turnToPrevPage 翻页。
        """
        attrs = node.attrs
        cap = self._caption(ctx, 'pagewindow', attrs)
        c = {'caption': cap,
             'dragMaxDis': 200, 'edgeEffect': 1,
             'id': ctx.nid('pagewindow'),
             'orientation': 0, 'rollSpeed': 60,
             'position': self._pos(attrs)}
        dmd = parse_px(_attr(attrs, 'data-drag-max'))
        if dmd is not None:
            c['dragMaxDis'] = dmd
        ori = parse_px(_attr(attrs, 'data-orientation'))
        if ori is not None:
            c['orientation'] = ori
        ee = parse_px(_attr(attrs, 'data-edge-effect'))
        if ee is not None:
            c['edgeEffect'] = ee
        rs = parse_px(_attr(attrs, 'data-roll-speed'))
        if rs is not None:
            c['rollSpeed'] = rs
        c['__container'] = True
        key = ctx.add('pagewindow', c)   # 支持嵌套（页面 window 嵌进来）
        ctx.stack.append(c)

    def _append_slideitem(self, ctx, node):
        """slidewindow 内的子 div.item → 追加一个图标项到 items（picTab 两态图 + text）。"""
        attrs = node.attrs
        item = {'colorTab': {'color0': _color_explicit(attrs, 'data-color', 0xFFFFFF)},
                'picTab': {}, 'text': ''}
        pic0 = _attr(attrs, 'data-pic') or _attr(attrs, 'data-pic0') or _attr(attrs, 'data-src')
        pic1 = _attr(attrs, 'data-pic1')
        if pic0:
            item['picTab']['pic0'] = pic0 if '/' in pic0 else 'images/' + pic0
        if pic1:
            item['picTab']['pic1'] = pic1 if '/' in pic1 else 'images/' + pic1
        elif pic0:
            item['picTab']['pic1'] = item['picTab']['pic0']
        text = _clean_text(node.text)
        if text:
            item['text'] = text
        ctx.stack[-1]['items'].append(item)

    def _append_wave(self, ctx, node):
        """diagram 内的子 div.wave → 追加一条波形配置到父容器 infos。
        style: 0=折线 1=曲线；eraseSpace=刷新间距；antialias=平滑。
        """
        attrs = node.attrs
        cap = self._caption(ctx, 'wave', attrs)
        info = {'caption': cap,
                'penColor': _color_explicit(attrs, 'data-color', 0xFFFFFF),
                'penWidth': _num(_attr(attrs, 'data-pen-width'), 2),
                'step': _num(_attr(attrs, 'data-step'), 10.0),
                'style': _num(_attr(attrs, 'data-style'), 1),
                'eraseSpace': _num(_attr(attrs, 'data-erase'), 20),
                'antialias': str(_attr(attrs, 'data-antialias') or '').strip() in ('1', 'true'),
                'visible': True,   # SampleUI diagram.infos[] 必写 visible（100% True）
                'xScale': _num(_attr(attrs, 'data-x-scale'), 1.0),
                'yScale': _num(_attr(attrs, 'data-y-scale'), 1.0)}
        ctx.stack[-1]['infos'].append(info)

    def _open_radiogroup(self, ctx, node):
        attrs = node.attrs
        cap = self._caption(ctx, 'radiogroup', attrs)
        # basedemo radiogroup 7 键 100%：backgroundColor/touchable/visible 含默认显式；radiobuttons[] 内嵌子项
        # touchable 必须 True（2026-09-10 修正）：radiogroup 是「容器显式 false」口径的例外——
        # 写 False 会让整组收不到触摸、点了没反应（单选组点不动）。详见 knowledge/uicontrols/touch-events.md
        c = {'backgroundColor': -1, 'caption': cap, 'id': ctx.nid('radiogroup'),
             'position': self._pos(attrs),
             'touchable': True, 'visible': True,
             '__container': True, '__radiogroup': True, 'radiobuttons': []}
        key = ctx.add('radiogroup', c)   # 支持嵌套（radiogroup 在 window 内）
        ctx.stack.append(c)

    # ---------- 叶子 ----------
    def _leaf(self, ctx, node, typ):
        attrs = node.attrs
        cap = self._caption(ctx, typ, attrs)
        pos = self._pos(attrs)
        text = _clean_text(node.text, ctx, cap)

        # 在 listview 内 → subItem
        if ctx.stack and ctx.stack[-1].get('__listview'):
            # subItem 子项（UIlayoutDemo/listview.ftu 校准）：支持背景图（头像等图片子项）+ 对齐 + 字号/颜色
            # subItem v2（SampleUI subitem 19 键 100%）：补安全默认键；iconPosition/textPosition/backgroundPic 条件写
            # （引擎缺省 icon/text 区 = position/控件区，历史验证 OK；有 backgroundPic 时用 backgroundPic 显示）
            # A3 修（2026-09-27）：subItem 也认 data-bg → bgColorTab（行内做「带底色的块」）
            sbg = self._bg_color(attrs)
            si = {'alignment': ALIGN.get((_attr(attrs, 'data-align') or 'center').lower(), 37),
                  'backgroundColor': -1,
                  'bgColorTab': {'color0': (-1 if sbg is None else sbg)},
                  'bold': False, 'caption': cap,
                  'colorTab': {'color0': _color_explicit(attrs, 'data-color', 0xEEF2F6)},
                  'fontFamily': 0,
                  'fontSize': self._font_size(attrs) or 16,
                  'id': ctx.nid('subitem'),
                  'italic': False, 'longClickIntervalTime': -1, 'longClickTimeOut': -1,
                  'picTab': {}, 'text': text if text else '',
                  'touchable': True, 'visible': True,
                  'position': pos}
            fs = self._font_size(attrs)
            if fs:
                si['fontSize'] = fs
            if text:
                si['text'] = text
            spic = _attr(attrs, 'data-pic') or _attr(attrs, 'data-bgpic') or _attr(attrs, 'data-src') or _attr(attrs, 'src')
            if spic:
                si['backgroundPic'] = spic if '/' in spic else 'images/' + spic
            else:
                # iconfont 图标自动生成（2026-09-03 图标优先）：subItem 里放 data-icon/icon-xxx 同样落图
                glyph = _glyph_from_attrs(attrs)
                if glyph is not None:
                    cw, ch = pos.get('width', 100), pos.get('height', 40)
                    png = self._icon_png(ctx, glyph, cw, ch, self._icon_color(attrs), pressed=False)
                    if png:
                        si['backgroundPic'] = png
            # charsetTab 字符图（NetDemo WiFi 信号档位校准）：data-charset='[{"char":48,"pic":"a.png","size":{"width":26,"height":24}},...]'
            cs = _attr(attrs, 'data-charset')
            if cs:
                try:
                    parsed = json.loads(cs)
                    if isinstance(parsed, list):
                        si['charsetTab'] = parsed
                except Exception:
                    pass
            # A5 修：data-visible 直通（subItem 初始隐藏）
            _vis = _bool_attr(attrs, 'data-visible')
            if _vis is not None:
                si['visible'] = _vis
            ctx.stack[-1]['item']['subItem'].append(si)
            return

        # 在 radiogroup 内 → radiobutton
        if ctx.stack and ctx.stack[-1].get('__radiogroup'):
            # radiobutton（RadioGroupDemo 校准）：两态圆图 picTab{pic0,pic2} + iconPosition + 选中色 color2
            # basedemo radiobutton 全字段（23 键 100%）：补安全默认键（fontFamily/roll*/iconPosition/textPosition 按需）
            rb = {'alignment': 38, 'backgroundColor': -1,
                  'bold': False, 'caption': cap, 'checked': False,
                  'fontSize': self._font_size(attrs) or 16,
                  'italic': False, 'touchable': True,
                  'bgColorTab': {'color0': _color_explicit(attrs, 'data-bg', 0x9FA05F),
                                 'color2': _color_explicit(attrs, 'data-bg2', 0x55736C)},
                  'colorTab': {'color0': _color_explicit(attrs, 'data-color', 0xEEF2F6)},
                  'id': ctx.nid('radiobutton'),
                  'position': pos,
                  'visible': True}
            rp0 = _attr(attrs, 'data-pic') or _attr(attrs, 'data-pic0') or _attr(attrs, 'data-src')
            rp2 = _attr(attrs, 'data-pic2')
            if rp0:
                rb['picTab'] = {'pic0': rp0 if '/' in rp0 else 'images/' + rp0,
                                'pic2': (rp2 if '/' in rp2 else 'images/' + rp2) if rp2 else (rp0 if '/' in rp0 else 'images/' + rp0)}
                rb['iconPosition'] = {'left': 0, 'top': 0,
                                      'width': int(_num(_attr(attrs, 'data-icon-w'), 20)),
                                      'height': int(_num(_attr(attrs, 'data-icon-h'), 20))}
            rb['text'] = text if text else ''   # basedemo radiobutton 100% 写 text（空串合法）
            if str(_attr(attrs, 'data-checked') or '').strip() in ('1', 'true'):
                rb['checked'] = True
            ctx.stack[-1]['radiobuttons'].append(rb)
            return

        # 普通叶子控件
        if typ == 'textview':
            c = {'alignment': ALIGN.get((_attr(attrs, 'data-align') or 'left').lower(), 36),
                 'caption': cap,
                 'colorTab': {'color0': _color_explicit(attrs, 'data-color', 0xEEF2F6)},
                 'fontSize': self._font_size(attrs) or 16,   # SampleUI textview fontSize 100% 必写（默认 16）
                 'id': ctx.nid('textview'),
                 'position': pos, 'touchable': False}
            bgc = self._bg_color(attrs)
            if bgc is not None:
                c['bgColorTab'] = {'color0': bgc}
            # ⭐ 2026-10-04（需求方改口径）：纯色 + 倒角的文本块（药丸标签/圆角底文本）→
            #   textview 也没有 radius 字段，纯色倒角此前**静默丢失** → 出 `.9.png` 背景图，
            #   圆角外底色交给「背后底色」（A6 口径）。无需代码。
            if not _attr(attrs, 'data-bgpic') and not re.search(
                    r'linear-gradient|radial-gradient|box-shadow', _attr(attrs, 'style') or ''):
                _pic9, _info9 = self._radbox_9pic(ctx, node, pos, cap, kind='textview')
                if _pic9:
                    c['backgroundPic'] = _pic9
                    self._corner_bg(ctx, c, attrs, None, cap)   # 四角 = 背后底色（不是本控件的填充色）
            # 静态底图 data-bgpic（v0.27.90）：textview 分支原**不读**该属性 → json 里没有
            #   backgroundPic = 「弹窗白卡/药丸/图标压根没画出来」，只能靠案例侧反查 HTML 兜底。
            #现与 button/window/seekbar/circlebar 等分支同口径落地；有图同样去底色（透明角会透底色）。
            bgp = _attr(attrs, 'data-bgpic') or _attr(attrs, 'data-background-pic')
            if bgp and not str(bgp).startswith('#'):
                c['backgroundPic'] = bgp if '/' in bgp else 'images/' + bgp
                self._corner_bg(ctx, c, attrs, bgc, cap)   # A6：圆角外底色不再一律 pop
            if text:
                c['text'] = text
            self._text_extra(c, attrs)
            # 自动转图：CSS 效果（渐变/阴影/emoji/loading）→ backgroundPic
            eff = self._effect_assets(ctx, node, pos.get('width', 100), pos.get('height', 40), cap)
            if eff.get('use_emoji'):
                # emoji 文本 → 图标 textview（清除文本，避免设备字库不支持）
                c.pop('text', None)
                self._corner_bg(ctx, c, attrs, bgc, cap)
                c['touchable'] = False
            if eff.get('backgroundPic'):
                c['backgroundPic'] = eff['backgroundPic']
                self._corner_bg(ctx, c, attrs, bgc, cap)   # A6：圆角外底色不再一律 pop
                if eff.get('pad'):
                    _grow(pos, eff['pad'])   # 叶子无子控件：只外扩自身，保证图==控件尺寸
            if eff.get('imageanim'):
                # loading → 动图控件（imageanim__N, ZKImageAnim）：demo json 用 playFile 字段（设备自动播放）
                typ = 'imageanim'
                c = {'caption': cap, 'id': ctx.nid('imageanim'),
                     'loopCount': 0, 'position': pos}
                af = eff.get('anim_file') or ''
                if af:
                    c['playFile'] = af
                    ctx.warnings.append(
                        f'<{node.tag} class="{_attr(attrs, "class") or ""}"> loading 动图已生成 '
                        f'{af}（imageanim 控件，playFile 已写入 json，设备自动播放；循环次数由 loopCount 控制，'
                        f'代码可用 m{cap}Ptr->play("{af}") 重播）')
        elif typ == 'imageanim':
            # 显式动图控件（UIlayoutDemo/imageanim.ftu 校准）：playFile GIF + loopCount（0=无限循环）
            c = {'caption': cap, 'id': ctx.nid('imageanim'),
                 'loopCount': 0, 'position': pos}
            af = _attr(attrs, 'data-src') or _attr(attrs, 'data-play-file') or _attr(attrs, 'data-gif') or _attr(attrs, 'src')
            if af:
                c['playFile'] = af if '/' in af else 'image/' + af
            lc = _num(_attr(attrs, 'data-loop'))
            if lc is not None:
                c['loopCount'] = int(lc)
            fi = _num(_attr(attrs, 'data-interval'))
            if fi:
                c['frameInterval'] = int(fi)
        elif typ == 'button':
            # 图片按钮铁律（UIlayoutDemo/button.ftu 校准）：有按键图片（picTab/backgroundPic）时不开背景色，
            #否则图片叠在颜色上效果与预想不同；仅纯文字按钮才用 bgColorTab/colorTab 多态色
            # ⚠️ 2026-09-05 修正：无底色且无文字的按钮（透明热区，覆盖卡片/图片上当点击区）不写 bgColorTab，
            #避免默认底色 0x374457 遮住下层内容；有 data-bg 或纯文字按钮才设底色（text 由 _leaf 预先解析）
            #
            # ⭐ 2026-10-04 需求方决策：**纯色 + 倒角 → `zk::ui_v1::RadButton`**（painter 自绘 AA 倒角，
            #   无资产、半径/四态色可运行时改）；**带渐变 / 背景图 → 仍走 ZKButton + 生成切图**（倒角烘进图）。
            #   背景：`button__N`/ZKButton 的 json 里**没有 radius 字段**（components/ui_v1/RadButton/README.md §0），
            #   所以纯色倒角走 ZKButton 的话倒角只能靠切图；而 RadButton 是「一个 painter + 一份代码」。
            if self._try_radbutton(ctx, node, pos, cap, text):
                return
            bgc = self._bg_color(attrs)
            c = {'alignment': ALIGN.get((_attr(attrs, 'data-align') or 'center').lower(), 37),
                 'caption': cap,
                 'colorTab': {'color0': _color_explicit(attrs, 'data-color', 0xEEF2F6)},
                 'id': ctx.nid('button'),
                 'position': pos, 'touchable': True}   # SampleUI button touchable 恒 true（现场反馈：交互控件显式 true）
            if bgc or text:
                c['bgColorTab'] = {'color0': (bgc if bgc is not None else 0x374457)}
            fs = self._font_size(attrs)
            if fs:
                c['fontSize'] = fs
            if text:
                c['text'] = text
            # 多态图（demo 五态）：pic0 正常 / pic1 按下 / pic2 选中 / pic3 选中按下 / pic4 无效
            pic0 = _attr(attrs, 'data-pic') or _attr(attrs, 'data-pic0') or _attr(attrs, 'data-src')
            pics = {}
            for k in ('pic0', 'pic1', 'pic2', 'pic3', 'pic4'):
                v = _attr(attrs, 'data-' + k)
                if v:
                    pics[k] = v if '/' in v else 'images/' + v
            if pic0:
                pics.setdefault('pic0', pic0 if '/' in pic0 else 'images/' + pic0)
            # iconfont 图标按钮（2026-09-03 需求方定规：图标优先）：
            # data-icon="play" / class="btn iconfont icon-play" / class="btn icon-play"
            # 无显式多态图时 → 自动生成 normal+pressed 两态 PNG 作 picTab（透明底线框图标按钮）
            glyph = _glyph_from_attrs(attrs)
            if not pics and glyph is not None:
                cw, ch = pos.get('width', 100), pos.get('height', 40)
                col = self._icon_color(attrs)
                p0 = self._icon_png(ctx, glyph, cw, ch, col, pressed=False)
                p1 = self._icon_png(ctx, glyph, cw, ch, col, pressed=True)
                if p0:
                    c['picTab'] = {'pic0': p0, 'pic1': p1 or p0}
                    c.pop('bgColorTab', None)
                    if text:
                        ctx.warnings.append(
                            f'<{node.tag} class="{_attr(attrs, "class") or ""}"> data-icon 图标按钮已忽略文字「{text}」'
                            f'（图标按钮纯图标；需文字说明请相邻加 div.text 或用纯文字按钮）')
                        c.pop('text', None)
            if pics:
                c['picTab'] = pics
            elif 'picTab' not in c:
                # 背景图按钮：backgroundPic 单图（BtnBgPic demo），有图也去底色
                bgpic = _attr(attrs, 'data-bgpic') or _attr(attrs, 'data-background-pic')
                if bgpic:
                    c['backgroundPic'] = bgpic if '/' in bgpic else 'images/' + bgpic
                else:
                    # 自动转图：渐变/阴影 → 按钮背景图（picTab 单态，无 pressed 时用同一张）
                    eff = self._effect_assets(ctx, node, pos.get('width', 100), pos.get('height', 40), cap)
                    if eff.get('backgroundPic'):
                        c['picTab'] = {'pic0': eff['backgroundPic'], 'pic1': eff['backgroundPic']}
                        if eff.get('pad'):
                            _grow(pos, eff['pad'])   # 叶子：只外扩自身，保证图==控件尺寸
            if 'picTab' in c or 'backgroundPic' in c:
                # A6 修（2026-09-27）：有图控件的**圆角外四角**由 bgColorTab 决定，旧版一律 pop
                #   → 四角取引擎缺省（窗口黑底），坐卡片上的圆角按钮/图标四角发黑（P4 报障）。
                #口径与工程侧 inject_rounded() 一致：data-bg 优先，否则取最近祖先容器底色。
                self._corner_bg(ctx, c, attrs, bgc, cap)
            # 图标按钮 padding（Button1 demo）：data-icon-w/h 图标尺寸 + data-pad 间隙 → iconPosition
            if _attr(attrs, 'data-icon-w') or _attr(attrs, 'data-icon-h'):
                cw, ch = pos.get('width', 100), pos.get('height', 40)
                iw = int(_attr(attrs, 'data-icon-w') or ch)
                ih = int(_attr(attrs, 'data-icon-h') or ch)
                c['iconPosition'] = {'left': 0, 'top': 0, 'width': iw, 'height': ih}
            c.setdefault('picTab', {})   # SampleUI button 必写 picTab（无图 {} 合法）
            c.setdefault('text', '')     # SampleUI button 必写 text（空串合法）
            self._text_extra(c, attrs)
        elif typ == 'edittext':
            c = {'alignment': 37, 'bold': False, 'caption': cap,   # SampleUI edittext 必写 bold（去 beepEnable）
                 'bgColorTab': {'color0': self._bg_or(attrs, 0xFFFFFF)},
                 'colorTab': {'color0': _color_explicit(attrs, 'data-color', 0)},
                 'fontSize': self._font_size(attrs) or 16,   # SampleUI edittext fontSize 100% 必写（默认 16）
                 'hintTextColor': 0, 'id': ctx.nid('edittext'),
                 'position': pos, 'touchable': True, 'visible': True}   # A4 修：漏写 touchable/visible → 输入框点不动、IME 不弹
            if str(_attr(attrs, 'data-num') or '').strip() in ('1', 'true'):
                c['textType'] = 1
            else:
                c['textType'] = 0   # SampleUI edittext textType 100% 必写（0=全文本）
            if str(_attr(attrs, 'data-password') or '').strip() in ('1', 'true'):
                c['isPassword'] = True
                pc = _attr(attrs, 'data-password-char')
                if pc:
                    c['passwordChar'] = pc
            hint = _attr(attrs, 'data-hint')
            if hint:
                c['hintText'] = _clean_text(hint, ctx, cap)
            hc = _color_explicit(attrs, 'data-hint-color', None)
            if hc is not None:
                c['hintTextColor'] = hc
            c['text'] = text if text else ''   # SampleUI edittext 必写 text（空串合法）
            self._text_extra(c, attrs)
        elif typ == 'seekbar':
            c = {'backgroundColor': -1, 'caption': cap, 'defProgress': 0,   # SampleUI seekbar 必写 backgroundColor/visible
                 'id': ctx.nid('seekbar'), 'max': 100, 'orientation': 0,
                 'position': pos, 'touchable': False, 'visible': True}
            mx = parse_px(_attr(attrs, 'data-max'))
            val = parse_px(_attr(attrs, 'data-value'))
            if mx:
                c['max'] = mx
            if val:
                c['defProgress'] = val
            track = _attr(attrs, 'data-track')
            fill = _attr(attrs, 'data-fill')
            if track:
                c['backgroundPic'] = track if '/' in track else 'images/' + track
            if fill:
                c['progressPic'] = fill if '/' in fill else 'images/' + fill
            ori = parse_px(_attr(attrs, 'data-orientation'))
            if ori is not None:
                c['orientation'] = ori
            # thumb 滑块（SeekBarDemo 校准）：normalPic + pressedPic 按下态 + size
            tn = _attr(attrs, 'data-thumb')
            tp = _attr(attrs, 'data-thumb-pressed')
            ts = parse_px(_attr(attrs, 'data-thumb-size'))
            if tn or tp or ts:
                c['touchable'] = True   # 可拖滑块（SampleUI seekbar 交互控件 touchable:true）
                thumb = {'size': {'height': ts or 24, 'width': ts or 24}}
                if tn:
                    thumb['normalPic'] = tn if '/' in tn else 'images/' + tn
                if tp:
                    thumb['pressedPic'] = tp if '/' in tp else 'images/' + tp
                c['thumb'] = thumb
            # CSS 结构化的进度条（.bar/.progress + .fill 子元素 + .thumb 子元素）→ 自动出 3 张切图
            # （2026-10-04 新增；只在没有 data-track/data-fill/data-thumb 时接管，data-* 行为不变）
            self._seekbar_css_assets(ctx, node, c, pos, cap)
            # SampleUI seekbar 必写 thumb（空=无滑块）。⚠️ 三键必须齐全：
            #   ui_schema.json 的 sharedTypes.thumb.requiredKeys = [size, normalPic, pressedPic]
            #   —— 旧写法只给 size，ui_schema_loader.type_check 会报 error（2026-10-04 实测）。
            c.setdefault('thumb', {'size': {'width': 0, 'height': 0},
                                   'normalPic': '', 'pressedPic': ''})
        elif typ == 'checkbox':
            # padding 配置（UIlayoutDemo/checkbox.ftu 校准）：
            #  iconPosition = 图标锚点（控件内 left:0 top:0，尺寸默认=控件高，可用 data-icon-w/h 指定）
            #  textPosition = 文本区（left = 图标宽 + padding(6~8)，top:0，宽=控件宽-图标宽-padding）
            #有图两态：picTab{pic0: 未选中, pic2: 选中}（注意选中是 pic2 不是 pic1！）
            #无图变色：bgColorTab{color0,color2} + colorTab{color0,color2}（color2=选中态）
            cw, ch = pos.get('width', 100), pos.get('height', 40)
            iw = int(_attr(attrs, 'data-icon-w') or ch)
            ih = int(_attr(attrs, 'data-icon-h') or ch)
            pad = int(_attr(attrs, 'data-pad') or 6)
            # basedemo checkbox 全字段（23 键 100%）：补安全默认键（fontFamily/roll* 从宽不写）
            c = {'alignment': 36, 'backgroundColor': -1,
                 'bold': False, 'caption': cap, 'checked': False,
                 'fontSize': self._font_size(attrs) or 16,
                 'italic': False, 'touchable': True,
                 'bgColorTab': {'color0': _color_explicit(attrs, 'data-bg', 0x607A84),
                                'color2': _color_explicit(attrs, 'data-bg2', 0x55736C)},
                 'colorTab': {'color0': _color_explicit(attrs, 'data-color', 0xEEF2F6),
                              'color2': _color_explicit(attrs, 'data-color2', 0xFFFFFF)},
                 'iconPosition': {'left': 0, 'top': 0, 'width': iw, 'height': ih},
                 'id': ctx.nid('checkbox'),
                 'position': pos,
                 'textPosition': {'left': iw + pad, 'top': 0,
                                  'width': max(cw - iw - pad, 10), 'height': ch},
                 'visible': True}
            # 两态图（优先）：pic0=未选中 pic2=选中；data-pic/data-pic2 或 data-src/data-src2
            pic0 = _attr(attrs, 'data-pic') or _attr(attrs, 'data-pic0') or _attr(attrs, 'data-src')
            pic2 = _attr(attrs, 'data-pic2') or _attr(attrs, 'data-src2')
            if pic0:
                c['picTab'] = {'pic0': pic0 if '/' in pic0 else 'images/' + pic0,
                               'pic2': (pic2 if '/' in pic2 else 'images/' + pic2) if pic2 else (pic0 if '/' in pic0 else 'images/' + pic0)}
                self._corner_bg(ctx, c, attrs, self._bg_color(attrs), cap)   # A6
            # basedemo checkbox/radiobutton 均 100% 写 text → 恒写（空串合法）
            c['text'] = text if text else ''
            if str(_attr(attrs, 'data-checked') or '').strip() in ('1', 'true'):
                c['checked'] = True
            self._text_extra(c, attrs)
        elif typ == 'circlebar':
            # 圆形进度条（UIlayoutDemo/circlebar.ftu 校准）：backgroundPic 背景图（不裁剪）+
            #   progressPic 有效图（按进度裁剪扇形）+ progressPicPos 有效图位置 + max/maxAngle/startAngle + clockwise
            # ⚠️ clockwise: false = 逆时针（demo 曾反 17:17 确认）
            cw, ch = pos.get('width', 200), pos.get('height', 200)
            # SampleUI circlebar 必写键（去 beepEnable）：backgroundColor/clockwise/startAngle/touchable/visible 含默认显式
            c = {'backgroundColor': -1, 'caption': cap,
                 'clockwise': True, 'id': ctx.nid('circlebar'),
                 'max': 100, 'maxAngle': 360,
                 'progressPicPos': {'left': 0, 'top': 0, 'width': 0, 'height': 0},
                 'position': pos, 'startAngle': 0,
                 'touchable': True, 'touchRange': {'lower': 0, 'upper': 0},
                 'visible': True}
            mx = _num(_attr(attrs, 'data-max'))
            if mx:
                c['max'] = int(mx)
            ma = _num(_attr(attrs, 'data-max-angle'))
            if ma:
                c['maxAngle'] = int(ma)
            sa = _num(_attr(attrs, 'data-start-angle'))
            if sa:
                c['startAngle'] = int(sa)
            cw_ = _attr(attrs, 'data-clockwise')
            if cw_ is not None:
                c['clockwise'] = str(cw_).strip() in ('1', 'true')
            bg = _attr(attrs, 'data-bgpic') or _attr(attrs, 'data-background-pic') or _attr(attrs, 'data-bg')
            fill = _attr(attrs, 'data-fill') or _attr(attrs, 'data-progress-pic')
            if bg and not bg.startswith('#'):
                c['backgroundPic'] = bg if '/' in bg else 'images/' + bg
            if fill:
                c['progressPic'] = fill if '/' in fill else 'images/' + fill
                c['progressPicPos'] = {'left': 0, 'top': 0, 'width': cw, 'height': ch}
            # 中间文字（CircleBarDemo 校准）：textColor/textSize/textType/unit
            tc = to_dec(_attr(attrs, 'data-text-color'))
            if tc:
                c['textColor'] = tc
            tsz = parse_px(_attr(attrs, 'data-text-size'))
            if tsz:
                c['textSize'] = tsz
            tt = _num(_attr(attrs, 'data-text-type'))
            if tt is not None:
                c['textType'] = int(tt)
            u = _attr(attrs, 'data-unit')
            if u:
                c['unit'] = u
            # thumb 滑块（可拖拽）+ touchRange 触摸范围（CircleBarDemo 校准）
            tn = _attr(attrs, 'data-thumb')
            ts = parse_px(_attr(attrs, 'data-thumb-size'))
            if tn or ts:
                thumb = {'size': {'width': ts or 0, 'height': ts or 0}}
                if tn:
                    thumb['normalPic'] = tn if '/' in tn else 'images/' + tn
                c['thumb'] = thumb
            tr = _attr(attrs, 'data-touch-range')  # "lower,upper"
            if tr:
                parts = str(tr).split(',')
                if len(parts) == 2 and _num(parts[0]) is not None and _num(parts[1]) is not None:
                    c['touchRange'] = {'lower': _num(parts[0]), 'upper': _num(parts[1])}
        elif typ == 'digitalclock':
            # 数字时钟（UIlayoutDemo/digitalclock.ftu 校准）：format 时间格式 + beat 冒号闪烁，自动实时刷新系统时间
            # format 大小写含义：HH=24小时制 hh=12小时制 MM=分钟 SS=秒 yyyy-MM-dd=日期 EEEE=星期
            # SampleUI digitalclock 必写键：backgroundColor/beat/clockColor/fontSize/format/touchable/visible
            c = {'backgroundColor': -1, 'beat': False, 'caption': cap,
                 'clockColor': 16777215, 'format': 'HH:MM',
                 'fontSize': self._font_size(attrs) or 32,
                 'id': ctx.nid('digitalclock'),
                 'touchable': False, 'visible': True,
                 'position': pos}
            fmt = _attr(attrs, 'data-format')
            if fmt:
                c['format'] = fmt
            beat = _attr(attrs, 'data-beat')
            if beat is not None:
                c['beat'] = str(beat).strip() in ('1', 'true')
            # clockColor 数字颜色（ScreensaverDemo 校准）；colorTab 兼容旧写法
            col = _color_explicit(attrs, ['data-color', 'data-clock-color'], None)
            if col is not None:
                c['clockColor'] = col
            bgc = self._bg_color(attrs)
            if bgc is not None:
                c['bgColorTab'] = {'color0': bgc}
        elif typ == 'slidetext':
            # 候选字滑动条（ImeDemo/UserIme 校准）：textBgColor 文字背景色，输入法候选词用
            c = {'caption': cap, 'id': ctx.nid('slidetext'),
                 'touchable': False, 'position': pos}
            fs = self._font_size(attrs)
            if fs:
                c['fontSize'] = fs
            tbg = _color_explicit(attrs, 'data-text-bg', None)
            if tbg is not None:
                c['textBgColor'] = tbg
            col = to_dec(_attr(attrs, 'data-color'))
            if col is not None:
                c['colorTab'] = {'color0': col}
            if text:
                c['text'] = text
            self._text_extra(c, attrs)
        elif typ == 'cameraview':
            # 摄像头预览（CameraDemo 校准）：autoPreview 自动预览 + formatSize 采集格式 + cvbs + mirror 镜像
            # SampleUI cameraview 必写键：backgroundColor/autoPreview/cvbs/formatSize/mirror/touchable/visible
            c = {'backgroundColor': 0, 'caption': cap, 'cvbs': False,
                 'formatSize': {'width': 640, 'height': 480},
                 'id': ctx.nid('cameraview'),
                 'mirror': 0, 'position': pos,
                 'touchable': False, 'visible': True}
            auto = str(_attr(attrs, 'data-auto-preview') or '1').strip() in ('1', 'true')
            c['autoPreview'] = auto   # 默认 true 自动预览，data-auto-preview="0" 关闭
            fw = parse_px(_attr(attrs, 'data-format-w'))
            fh = parse_px(_attr(attrs, 'data-format-h'))
            if fw and fh:
                c['formatSize'] = {'width': fw, 'height': fh}
            if str(_attr(attrs, 'data-cvbs') or '').strip() in ('1', 'true'):
                c['cvbs'] = True
            else:
                c['cvbs'] = False
            mv = _num(_attr(attrs, 'data-mirror'))
            if mv is not None:
                c['mirror'] = int(mv)
        elif typ == 'painter':
            # 画布（PainterDemo 校准）：触摸绘制，代码 paint() 刷新
            c = {'backgroundColor': -1, 'caption': cap,
                 'id': ctx.nid('painter'),
                 'position': pos, 'touchable': False, 'visible': True}
        elif typ == 'pointer':
            # 仪表盘指针（PointerDemo/clockDemo 校准）：pointerPic 指针图 + fixedPoint 固定点 + rotationPoint 旋转中心
            # SampleUI pointer 必写键含默认：rotateSpeed 1/startAngle 0/backgroundColor -1/visible（图与点位仍条件）
            c = {'backgroundColor': -1, 'caption': cap,
                 'id': ctx.nid('pointer'), 'rotateSpeed': 1,
                 'startAngle': 0, 'position': pos,
                 'touchable': False, 'visible': True}
            pp = _attr(attrs, 'data-pointer-pic')
            if pp:
                c['pointerPic'] = pp if '/' in pp else 'images/' + pp
            bg = _attr(attrs, 'data-bgpic') or _attr(attrs, 'data-background-pic')
            if bg:
                c['backgroundPic'] = bg if '/' in bg else 'images/' + bg
            psw = parse_px(_attr(attrs, 'data-pointer-w'))
            psh = parse_px(_attr(attrs, 'data-pointer-h'))
            if psw and psh:
                c['pointerSize'] = {'width': psw, 'height': psh}
            sa = _num(_attr(attrs, 'data-start-angle'))
            if sa is not None:
                c['startAngle'] = sa
            rs = _num(_attr(attrs, 'data-rotate-speed'))
            if rs is not None:
                c['rotateSpeed'] = rs
            # clockwise/animatable 恒写（SampleUI pointer 默认 true）
            c['clockwise'] = str(_attr(attrs, 'data-clockwise') or '1').strip() in ('1', 'true')
            c['animatable'] = str(_attr(attrs, 'data-animatable') or '1').strip() in ('1', 'true')
            # fixedPoint 指针固定点 / rotationPoint 旋转点（PointerDemo/clockDemo 实测：
            # 缺这两个坐标指针会绕错圆心转；格式 "x,y"，如 data-rotation-point="197,209"）
            fp = _attr(attrs, 'data-fixed-point')
            if fp:
                parts = fp.split(',')
                if len(parts) == 2 and _num(parts[0]) is not None and _num(parts[1]) is not None:
                    c['fixedPoint'] = {'x': _num(parts[0]), 'y': _num(parts[1])}
            rp = _attr(attrs, 'data-rotation-point')
            if rp:
                parts = rp.split(',')
                if len(parts) == 2 and _num(parts[0]) is not None and _num(parts[1]) is not None:
                    c['rotationPoint'] = {'x': _num(parts[0]), 'y': _num(parts[1])}
        elif typ == 'qrcode':
            # 二维码（QRCodeDemo 校准）：codeStr 初始内容，代码 loadQRCode(text) 动态生成
            # SampleUI qrcode touchable:true + 需求方口径 padding 默认各边 10
            c = {'backgroundColor': 16777215, 'caption': cap,
                 'id': ctx.nid('qrcode'), 'padding': 10,
                 'touchable': True, 'visible': True,
                 'position': pos}
            cs = _attr(attrs, 'data-code')
            if cs:
                c['codeStr'] = cs
            bgc = to_dec(_attr(attrs, 'data-bg'))
            if bgc is not None:
                c['backgroundColor'] = bgc
        elif typ == 'videoview':
            # 视频播放（VideoViewDemo/VideoPlayerDemo 校准）：defaultVolume 默认音量 + loopPlayback 循环 + rotation 旋转
            # SampleUI videoview 全键（无 beepEnable；loopPlayback 默认 false；touchable:true）
            c = {'backgroundColor': 0, 'caption': cap, 'defaultVolume': 5,
                 'id': ctx.nid('videoview'),
                 'loopPlayback': False, 'rotation': 0,
                 'position': pos, 'touchable': True, 'visible': True}
            dv = parse_px(_attr(attrs, 'data-volume'))
            if dv is not None:
                c['defaultVolume'] = dv
            lp = _attr(attrs, 'data-loop')
            if lp is not None:
                c['loopPlayback'] = str(lp).strip() in ('1', 'true')
            rot = parse_px(_attr(attrs, 'data-rotation'))
            if rot is not None:
                c['rotation'] = rot
        elif typ == 'icon':
            c = {'alignment': 36, 'caption': cap,
                 'colorTab': {'color0': _color_explicit(attrs, 'data-color', 0xEEF2F6)},
                 'fontSize': self._font_size(attrs) or 16,
                 'id': ctx.nid('textview'), 'position': pos, 'touchable': False}
            pic = _attr(attrs, 'data-pic') or _attr(attrs, 'src')
            if pic:
                c['backgroundPic'] = pic if '/' in pic else 'images/' + pic
            else:
                # iconfont 图标自动生成（2026-09-03 需求方定规：图标优先）：
                # data-icon="play" / class="iconfont icon-play" / class="icon icon-play" → PNG 图标 textview
                glyph = _glyph_from_attrs(attrs)
                if glyph is not None:
                    cw, ch = pos.get('width', 100), pos.get('height', 40)
                    png = self._icon_png(ctx, glyph, cw, ch, self._icon_color(attrs), pressed=False)
                    if png:
                        c['backgroundPic'] = png
                if 'backgroundPic' not in c:
                    # 纯 emoji 文本 → PNG 图标（设备字库不支持 emoji，转图片显示）
                    raw_text = re.sub(r'[ \t\r\f\v]+', ' ', node.text).strip()
                    if raw_text and not _clean_text(raw_text) and any(_is_emoji(ch) for ch in raw_text):
                        emoji_ch = next((ch for ch in raw_text if _is_emoji(ch)), '\u2b50')
                        size = max(pos.get('width', 100), pos.get('height', 100))
                        name = f'emoji_{cap or ctx.n}_{self.gen_count}.png'

                        def _e(d, _n=name, _s=size, _c=emoji_ch):
                            return gr.emoji_icon(d, _n, _s, _c)

                        pic2 = self._gen_asset(_e)
                        if pic2:
                            c['backgroundPic'] = pic2
            typ = 'textview'
        else:
            # 未知类型兑底 → textview 全字段（SampleUI 基准）
            c = {'alignment': 36, 'caption': cap,
                 'colorTab': {'color0': 0xEEF2F6},
                 'fontSize': self._font_size(attrs) or 16,
                 'id': ctx.nid('textview'), 'position': pos, 'touchable': False}
            typ = 'textview'

        # A5 修（2026-09-27）：data-visible 直通 visible（HTML 侧「初始隐藏」的唯一口）
        _vis = _bool_attr(attrs, 'data-visible')
        if _vis is not None:
            c['visible'] = _vis
        ctx.add(typ, c)

    # ---------- 辅助 ----------
    # data-left/top/width/height 与 HTML_SUBSET.md 规范的 data-x/y/w/h 互为别名
    _POS_ALIAS = {'left': ('left', 'x'), 'top': ('top', 'y'),
                  'width': ('width', 'w'), 'height': ('height', 'h')}

    _FS_ATTRS = ('data-fs', 'data-font-size', 'data-fontsize', 'data-fontSize')

    def _font_size(self, attrs):
        """字号：data-fs / data-font-size / data-fontSize / 内联 style font-size 都认。"""
        for k in self._FS_ATTRS:
            v = _attr(attrs, k)
            if v:
                pv = parse_px(v)
                if pv is not None:
                    return pv
        style = _attr(attrs, 'style') or ''
        m = re.search(r'(?:^|;)\s*font-size\s*:\s*([^;]+)', style)
        if m:
            pv = parse_px(m.group(1))
            if pv is not None:
                return pv
        return None

    def _text_extra(self, c, attrs):
        """文字控件通用属性（basedemo 实测）：bold/italic 粗斜体 + 文字滚动 roll* 系列。
        roll：data-roll 开关 + data-roll-direction 方向 + data-roll-step 步长 + data-roll-interval 间隔。"""
        b = _attr(attrs, 'data-bold')
        if b is not None:
            c['bold'] = str(b).strip() in ('1', 'true')
        it = _attr(attrs, 'data-italic')
        if it is not None:
            c['italic'] = str(it).strip() in ('1', 'true')
        re_ = _attr(attrs, 'data-roll')
        if re_ is not None:
            c['rollEnable'] = str(re_).strip() in ('1', 'true')
        rd = _attr(attrs, 'data-roll-direction')
        if rd is not None:
            rdv = str(rd).strip()
            c['rollDirection'] = int(rdv) if rdv.isdigit() else rdv
        rs_ = parse_px(_attr(attrs, 'data-roll-step'))
        if rs_ is not None:
            c['rollStep'] = rs_
        ri = parse_px(_attr(attrs, 'data-roll-interval'))
        if ri is not None:
            c['rollIntervalTime'] = ri
        return c

    def _bg_color(self, attrs):
        """背景色：data-bg / data-background / 内联 background 都认。"""
        c = to_dec(_attr(attrs, 'data-background'))
        if c is None:
            c = to_dec(_attr(attrs, 'data-bg'))
        if c is None:
            style = _attr(attrs, 'style') or ''
            m = re.search(r'(?:^|;)\s*background(?:-color)?\s*:\s*([^;]+)', style)
            if m:
                c = to_dec(m.group(1).strip())
        return c

    def _bg_or(self, attrs, default):
        """背景色缺省值（A2 修）：data-bg 写纯黑(#000000) 也是 0，不能被 `or` 吞掉。"""
        c = self._bg_color(attrs)
        return default if c is None else c

    def _ancestor_bg(self, ctx):
        """最近祖先底色（圆角外底色用，A6）：容器打开时记在 __bg；都没有则回退页面底色。"""
        for v in reversed(list(ctx.stack)):
            if not isinstance(v, dict) or v.get('__listview'):
                break
            b = v.get('__bg')
            if b is not None:
                return b
        root = ctx.root or {}
        return root.get('backgroundColor', None)

    def _corner_bg(self, ctx, c, attrs, given, cap=''):
        """有图控件的**圆角外底色**归属（A6 修，2026-09-27）。

有图控件的四角透出的是 `bgColorTab`；旧版「有图一律 pop(bgColorTab)」
        → 四角取引擎缺省（窗口黑底）→ 坐在卡片上的圆角按钮/图标四角发黑
        （P4 报障「图标角落都是黑的」，真机逐点：四角 (0,0,0) / 卡片 (28,28,30)）。
口径与工程侧 inject_rounded() 一致：
          ① 作者显式写 data-bg/data-background/style.background → 用它（最高优先）；
          ② 没写 → 取**最近祖先容器底色**；
          ③ 都没有 → 保持 pop（退回引擎缺省），并提示补 data-bg。
注意：bgColorTab 只管最外 1px；圆角里侧 4~5px 是图里像素，补色救不回来。
        """
        if given is not None:
            c['bgColorTab'] = {'color0': given}
            return
        anc = self._ancestor_bg(ctx)
        if anc is not None:
            c['bgColorTab'] = {'color0': anc}
            ctx.warn('%s：有图控件未写 data-bg，圆角外底色取最近祖先底色 0x%06X'
                     '（A6：四角由 bgColorTab 决定，不写会露窗口黑底）' % (cap or '控件', anc),
                     key='corner:%s' % (cap or '?'))
            return
        c.pop('bgColorTab', None)
        ctx.warn('%s：有图控件既无 data-bg 也无祖先底色 → 圆角外四角按引擎缺省渲染'
                 '（坐卡片上会发黑）；请给该控件补 data-bg=容器色' % (cap or '控件'),
                 key='corner-nobg:%s' % (cap or '?'))

    def _pos(self, attrs):
        style = _attr(attrs, 'style') or ''
        pos = _style_pos(style)
        for k, names in self._POS_ALIAS.items():
            for n in names:
                v = _attr(attrs, 'data-' + n)
                if v:
                    pv = parse_px(v)
                    if pv is not None:
                        pos[k] = pv
                        break
        # 父级阴影外扩补偿（2026-09-10）：window 因阴影图外扩了 pad，子控件是父相对坐标
        # → 必须 +pad 才能落在可见卡片体内；listview 行内 subItem 相对行坐标，不再累加。
        ctx = getattr(self, 'ctx', None)
        if ctx is not None:
            for _v in reversed(list(ctx.stack)):
                if not isinstance(_v, dict) or _v.get('__listview'):
                    break
                _p = _v.get('__pad') or 0
                if _p:
                    pos['left'] = pos.get('left', 0) + _p
                    pos['top'] = pos.get('top', 0) + _p
        return {
            'height': pos.get('height', 40), 'left': pos.get('left', 0),
            'top': pos.get('top', 0), 'width': pos.get('width', 100),
        }

    def _caption(self, ctx, typ, attrs):
        cap = _attr(attrs, 'data-caption')
        if cap:
            cap = re.sub(r'[^A-Za-z0-9_]', '_', str(cap))
            if not re.match(r'^[A-Za-z_]', cap):
                cap = '_' + cap
            return cap
        return ctx.name(typ)


def _walk_ctrls(d, top=False, out=None):
    """递归产出全部控件 (key, value)；top=True 只产出顶层（window__ 等）。"""
    if out is None:
        out = []
    for k, v in d.items():
        if isinstance(v, dict) and '__' in k:
            out.append((k, v))
            if not top:
                _walk_ctrls(v, top=False, out=out)
    return out


def _finalize_layout(data, warnings):
    """生成收尾规范（fix.log 规则前移内化，2026-09-03）：
    - FT-009：textview/button 宽高自动扩到最小尺寸公式（超容器则告警不扩）
    - FT-006：顶层多个互盖的整屏 window -> 告警，按 page-architecture-spec.md 口径
说清「同业务域就该这样放，只有跨业务域/独立返回栈/超大页面才拆新 ftu」（不误判为错误）
原地修改 data，把需人工处理的问题追加到 warnings。
    """
    res = data.get('resolution') or {}
    rw = res.get('width') or 0

    def min_size(text, fs, align):
        wsum = 0.0
        for ch in text:
            if ord(ch) > 0x2E7F:      # CJK/全角
                wsum += 1.0
            elif re.match(r'[\w\d()\[\]{}]', ch):
                wsum += 0.55
            else:
                wsum += 0.6
        mw = int(wsum * fs * 1.1) + 16
        if align == 37:               # CENTER 补余量
            mw += 8
        return mw, int(fs * 1.25)

    def parent_w(key):
        root_w = rw

        def find(dd, k, parent=None):
            for kk, vv in dd.items():
                if not isinstance(vv, dict):
                    continue
                if kk == k:
                    return parent
                if '__' in kk:
                    r = find(vv, k, vv if kk.startswith('window__') else parent)
                    if r is not None:
                        return r
            return None

        p = find(data, key)
        if p is not None and p.get('position'):
            return p['position'].get('width', root_w) or root_w
        return root_w

    # ---- FT-009 最小尺寸（防文本截断：FlyThings 按 rect 硬裁剪不 ellipsize）----
    for key, val in _walk_ctrls(data):
        if not key.startswith(('textview__', 'button__')):
            continue
        text = str(val.get('text', ''))
        fs = val.get('fontSize') or 0
        pos = val.get('position') or {}
        if not text or not fs or not pos.get('width') or not pos.get('height'):
            continue
        mw, mh = min_size(text, fs, val.get('alignment', 0))
        nw, nh = pos['width'], pos['height']
        if pos['width'] < mw:
            nw = mw
        if pos['height'] < mh:
            nh = mh
        if (nw, nh) == (pos['width'], pos['height']):
            continue
        cw = parent_w(key)
        if nw > pos['width'] and pos.get('left', 0) + nw > cw:
            warnings.append(f'{key}({val.get("caption", "")}) 文本“{text[:10]}”字号 {fs} '
                            f'需最小宽 {mw}px，但扩宽会超出容器({cw}px)——需手动调位置/字号或拆行')
            nw = pos['width']  # 宽度让位人工处理；高度不足仍自动扩（不挤占水平空间）
        pos['width'], pos['height'] = nw, nh

    # ---- FT-006 顶层多个互盖整屏 window（merge-windows 形态的提醒）----
    # 口径来源：knowledge/devflow/page-architecture-spec.md §0/§2（两者文字互引用，禁止再漂移）。
    # 2026-09-21 口径：缺省 = 一个 .screen = 一页 = 一个 Activity = 一个 json/ftu；
    # 只有「同属一个 Activity 的多个整屏 window」才合成同一个 json（html2json --merge-windows）。
    # v0.27.100 起：本告警出现在 merge-windows 产物里（同 ftu 多整屏 window 就该这么放，
    # 但**不许**因此把跨业务域的多页硬塞进一个 ftu）。
    screen_area = rw * (res.get('height') or 0)
    top_wins = [(k, v) for k, v in _walk_ctrls(data, top=True)
                if k.startswith('window__') and v.get('position')]
    if screen_area and len(top_wins) >= 2:
        pages = [(k, v) for k, v in top_wins
                 if (v['position'].get('width') or 0) * (v['position'].get('height') or 0) >= screen_area * 0.6]
        hits = []
        for i in range(len(pages)):
            for j in range(i + 1, len(pages)):
                a, b = pages[i][1]['position'], pages[j][1]['position']
                ix = max(0, min(a['left'] + a['width'], b['left'] + b['width']) - max(a['left'], b['left']))
                iy = max(0, min(a['top'] + a['height'], b['top'] + b['height']) - max(a['top'], b['top']))
                inter = ix * iy
                small = min(a['width'] * a['height'], b['width'] * b['height'])
                if small and inter / small > 0.3:
                    hits.append((pages[i][0], pages[j][0]))
        if hits:
            names = ' / '.join(sorted({k for pair in hits for k in pair}))
            warnings.append(
                f'检测到多个互相盖住的整屏 Window（{names}）：按 knowledge/devflow/'
                f'page-architecture-spec.md 的默认口径，**同一业务域**内的多页就该这么放'
                f'（同一个 ftu 内叠多个整屏 window，首屏 visible:true、其余 visible:false，'
                f'切换只走 showWnd()/hideWnd()：零切换成本、共享控件指针与状态）；'
                f'**只有跨业务域 / 需独立生命周期与返回栈 / 超大页面**才拆成独立 ftu'
                f'（新 Activity + openActivity() 跳转；html2json 缺省就是每屏一个 json /\n'
                f'一个 ftu，这个多整屏 window 形态要用 --merge-windows 才是）。'
                f'判据见该文档 §2 决策清单')
    return data


def html2json(input_html, output_json=None, res=None, asset_dir=None, merge_windows=False):
    """受限 HTML -> json 布局（缺省：每屏一个 json）。

返回 {success, jsonPath, jsonPaths, jsonsProduced, screensDetected, pagesProduced, mode,
          pages[], resolution, controls, warnings, ...}（失败时 success:false + error）。

多屏（HTML 内多个 div.screen）默认口径（2026-09-21 口径，见
    knowledge/devflow/page-architecture-spec.md）：**一个 .screen = 一个页面 = 一个 Activity
    = 一个独立 json（-> 一个独立 ftu）**；N 屏 -> N 个 json，文件名取 data-page
    （缺省 page_k）；同屏内部的 window / dialog（弹窗）不是页，直接写在 .screen 里
    （div.window / div.modal），工具**不会**把多个 .screen 合并成多窗口。

    merge_windows=True（CLI --merge-windows）：N 屏合成同一个 json 内的 N 个整屏 window
    （window__1..window__N 连续编号，首屏 visible:true、其余 visible:false，切页走
    showWnd/hideWnd）—— **仅当 AI 判定这些屏同属一个 Activity（同 ftu 内整屏 window）**时用；
返回体 warnings 里回显「本次按 merge-windows 合成」。

    **屏数核对**：screensDetected != pagesProduced 一律 success:false + error（不静默丢页）；
    pages[] 逐页列出（页名 + 对应 json 路径；merge_windows 时多页指向同一个 json）。
    controls = 控件总数（**含嵌套**，A7 修 2026-09-27；旧版只数根层）；
    controlsTopLevel / controlsNested = 顶层与嵌套分项。

输出落点：output_json 写 .json = 具体文件；写成目录（不带 .json）= 该目录；省略 = html
同目录。单页时直接写 output_json 文件（与旧版一致）；多页时写 <目录>/<data-page>.json。

    asset_dir：CSS 效果（渐变/阴影/emoji/loading）自动转图输出目录；
缺省自动定位到项目 resources/images/（json 引用 images/xxx.png 相对 resources 目录，与设备加载一致）：
      - output_json 位于 <项目>/ui/ 下 -> asset_dir = <项目>/resources/images/
      - 其它位置 -> 回退 json 同目录 images/ 并警告（提示手动挪图或显式传 asset_dir）
不传 output_json 且不传 asset_dir 时不做自动转图（纯布局转换）。"""
    if not os.path.isfile(input_html):
        return {'success': False, 'error': f'html 文件不存在: {input_html}'}
    with open(input_html, encoding='utf-8-sig') as f:
        text = f.read()
    warnings = []
    # 输出落点：output_json 是 .json -> 具体文件；否则当目录；省略 -> html 同目录
    out_file = None
    if output_json:
        if str(output_json).lower().endswith('.json'):
            out_file = os.path.abspath(output_json)
            out_dir = os.path.dirname(out_file)
        else:
            out_dir = os.path.abspath(output_json)
    else:
        out_dir = os.path.dirname(os.path.abspath(input_html))
    if asset_dir is None and output_json:
        if os.path.basename(out_dir) == 'ui':
            # <项目>/ui/main.json -> 图片输出到 <项目>/resources/images/
            asset_dir = os.path.join(os.path.dirname(out_dir), 'resources', 'images')
        else:
            asset_dir = os.path.join(out_dir, 'images')
            warnings.append('output_json 不在 <项目>/ui/ 目录下，自动转图输出到 json 同目录 images/；'
                            '建议把图片移到项目 resources/images/ 后 json 引用 images/xxx.png（相对 resources）')
    conv = HtmlToJson(res=res, asset_dir=asset_dir)
    pages, w2, meta = conv.convert(text, merge_windows=bool(merge_windows))
    warnings += w2
    if meta is None:
        return {'success': False, 'warnings': warnings, 'screensDetected': 0, 'pagesProduced': 0,
                'error': '未找到 <div class="screen"> 根节点（受限 HTML 必须从 screen 容器开始）'}
    if meta.get('error') or pages is None:
        return {'success': False, 'warnings': warnings,
                'screensDetected': meta.get('screensDetected'),
                'pagesProduced': meta.get('pagesProduced'),
                'mode': meta.get('mode'),
                'error': meta.get('error')
                         or '未找到 <div class="screen"> 根节点（受限 HTML 必须从 screen 容器开始）'}
    # 收尾规范：FT-009 最小尺寸 / FT-006 多整屏 window 提醒（每个 json 单独过一遍）
    for _pid, data in pages:
        _finalize_layout(data, warnings)

    per_page = (meta['mode'] == 'per-screen')   # merge-windows 是同一个 json，不按页写文件
    json_paths = []
    if per_page:
        for pid, data in pages:
            jp = os.path.join(out_dir, pid + '.json')
            os.makedirs(os.path.dirname(os.path.abspath(jp)), exist_ok=True)
            with open(jp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            json_paths.append(jp)
        output_json = json_paths[0]    # jsonPath 指首页（全量清单看 jsonPaths / pages）
    else:
        target = out_file or (os.path.join(out_dir, pages[0][0] + '.json') if output_json else None)
        if target:
            os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
            with open(target, 'w', encoding='utf-8') as f:
                json.dump(pages[0][1], f, ensure_ascii=False, indent=2)
            json_paths = [target]
            output_json = target
    data = pages[0][1]
    resv = data.get('resolution', {})
    # A7 修（2026-09-27）：**嵌套控件也计入**（旧版只数根层 → 50 控件页面报 controls:1，
    #键盘页/弹窗页的控件全部漏计；controls 现在是全量，另附顶层/嵌套分项）
    top_cnt = sum(1 for k, v in data.items() if isinstance(v, dict) and '__' in k)
    all_cnt = len(_walk_ctrls(data))
    count = all_cnt
    return {'success': True, 'jsonPath': output_json, 'jsonPaths': json_paths,
            'jsonsProduced': len(json_paths),
            'screensDetected': meta['screensDetected'],
            'pagesProduced': meta['pagesProduced'],
            'mode': meta['mode'],
            'pages': [{'page': pid,
                       'json': (json_paths[i] if per_page
                                else (json_paths[0] if json_paths else None))}
                      for i, (pid, _d) in enumerate(pages)],
            'resolution': f"{resv.get('width')}x{resv.get('height')}",
            'controls': count, 'controlsTopLevel': top_cnt,
            'controlsNested': max(all_cnt - top_cnt, 0), 'warnings': warnings,
            'generatedAssets': conv.gen_count,
            'radButtonGlue': conv._rad_glue,
            'assetDir': asset_dir}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    argv = sys.argv[1:]
    merge = '--merge-windows' in argv
    dead = '--split-per-page' in argv      # v0.27.100 起就是缺省口径，退役
    args = [a for a in argv if not a.startswith('--')]
    res = None
    for a in argv:
        if a.startswith('--res='):
            res = a.split('=', 1)[1]
    if len(args) < 1 or dead:
        print('用法: python html2json.py <input.html> [output.json|输出目录] [--res WxH] [--merge-windows]')
        print('  <input.html> 的每个 .screen = 一个页面 = 一个 Activity = 一个独立 json（缺省口径），')
        print('文件名取 data-page，输出目录 = output 所写目录 / html 同目录；')
        print('  --merge-windows：N 屏合成同一 json 的 N 个整屏 window（首屏 visible:true 其余 false），')
        print('仅当这些屏同属一个 Activity 时才用；同屏内 window/dialog 直接写在 .screen 里。')
        if dead:
            print('  [X] --split-per-page 已退役（v0.27.100）：每屏一个 json 就是现在的缺省口径，去掉该参数即可。')
        sys.exit(2 if dead else 1)
    src = args[0]
    dst = args[1] if len(args) > 1 else os.path.splitext(src)[0] + '.json'
    r = html2json(src, dst, res=res, merge_windows=merge)
    if not r['success']:
        print('[X]', r['error'])
        sys.exit(1)
    print(json.dumps(r, ensure_ascii=False, indent=1))
