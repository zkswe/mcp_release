#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""受限 HTML → FlyThings JSON 布局转换器（通用工具 v1，不随项目复制）

用途：HTML 交互原型（首版界面）→ 直接转成 ui/*.json 布局，
再 fui pack 生成 ftu 交付设备端。替代每个项目手写 Builder/JSON。

用法：
    python html2json.py <input.html> [output.json] [--res WxH]

受限 HTML 规范见 HTML_SUBSET.md（元素/class → FlyThings 控件映射表）。
核心规则自动内建：
- 控件键 `类型__N` 全局递增；ID 按类型分区；颜色十进制
- window 子控件嵌套其内（相对坐标）；弹窗 modal:true + visible:false
- Z 序 = HTML 文档顺序（后定义在上层，弹窗最后）
- 空文本不写 text 字段；edittext 自动 beepEnable/hintTextColor
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

# ---------- ID 分区（SKILL §2.3 沛哥版） ----------
ID_BASE = {
    'textview': 50000, 'button': 20000, 'edittext': 51000,
    'seekbar': 91000, 'window': 110000, 'listview': 80000,
    'checkbox': 21000, 'radiogroup': 94000, 'radiobutton': 22000,
    'subitem': 24000, 'imageanim': 160000,
    'circlebar': 130000, 'diagram': 60000, 'digitalclock': 93000,
    'slidewindow': 30000, 'scrollwindow': 32000, 'pagewindow': 31000,
    'slidetext': 51000, 'cameraview': 97000, 'painter': 52000,
    'pointer': 90000, 'qrcode': 92000, 'videoview': 95000,
}

# HTML class 关键字 → FlyThings 控件类型
CLASS_MAP = {
    'textview': ('text', 'tv', 'label', 'txt'),
    'button': ('btn', 'button', 'b'),
    'edittext': ('input', 'edit', 'edittext'),
    'seekbar': ('bar', 'seekbar', 'progress'),
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


# iconfont 图标语义提取（2026-09-03 沛哥定规：图标优先）
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
    纯 iconfont/icon-xxx → icon（图标 textview）。"""
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


def _is_emoji(ch):
    """判断字符是否 emoji/特殊符号（设备裁剪字库不支持，全范围覆盖）：
    表情物品 1F000-1FAFF / 杂项符号 2600-27BF / 技术符号 2300-23FF /
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


def _clean_text(s):
    """剥离 emoji 与黑名单特殊符号，只保留汉字+ASCII+基础符号（/ % # - _ 空格）。"""
    if not s:
        return s
    out = []
    for ch in s:
        if ch in _TEXT_BLACKLIST or _is_emoji(ch):
            continue
        out.append(ch)
    # \n（来自 <br>）保留为换行；其余空白折叠为单空格
    return re.sub(r'[ \t\r\f\v]+', ' ', ''.join(out)).strip()


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

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        if self.stack:
            self.stack[-1].children.append(node)
        elif self.root is None:
            self.root = node
        if tag not in VOID_TAGS:
            self.stack.append(node)
        elif tag == 'br' and self.stack:
            # <br> → '\n' 换行（textview 支持 \n 多行，沛哥 2026-09-03 纠正 FT-024）
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
        if self.stack and self.stack[-1].tag not in ('style', 'script'):
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
        """写入当前容器（有 window 嵌套则进栈顶），返回 key。"""
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

    # ---------- iconfont 图标自动落图（2026-09-03 沛哥定规：图标优先）----------
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
                radius = 0
                rm = re.search(r'border-radius\s*:\s*(\d+)px', style)
                if rm:
                    radius = min(int(rm.group(1)), min(w, h) // 2)
                name = f'grad_{cap or ctx.n}_{self.gen_count}.png'

                def _g(d, _n=name, _w=w, _h=h, _st=stops, _hz=horizontal, _r=radius):
                    return gr.gen_gradient_stops(d, _n, _w, _h, _st, horizontal=_hz, radius=_r)

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
                    rm = re.search(r'border-radius\s*:\s*(\d+)px', style)
                    radius = int(rm.group(1)) if rm else 8
                    radius = min(radius, min(w, h) // 2)
                    fill = _css_color(re.search(r'background(?:-color)?\s*:\s*([^;]+)', style).group(1).strip()) \
                        if re.search(r'background(?:-color)?\s*:\s*([^;]+)', style) else (0x1E, 0x27, 0x35, 255)
                    # 渐变+阴影：阴影叠加到渐变底上（渐变优先，保留视觉层次）
                    if 'backgroundPic' in out:
                        name = f'gradshadow_{cap or ctx.n}_{self.gen_count}.png'

                        def _gs(d, _n=name, _w=w, _h=h, _r=radius, _sh=(ox, oy, blur, sc),
                                _gm=gm):
                            # 重画渐变底 + 阴影合成
                            _hz, _st = _parse_gradient(_gm.group(1))
                            base = gr.gen_gradient_stops(d, _n, _w, _h, _st, horizontal=_hz, radius=_r)
                            # 在渐变图上叠加阴影（从 grad 图复制合成）
                            from PIL import Image as _Image, ImageDraw as _Draw
                            img = _Image.open(base).convert('RGBA')
                            sh = _Image.new('RGBA', img.size, (0, 0, 0, 0))
                            _Draw.Draw(sh).rounded_rectangle(
                                [0, 0, img.size[0] - 1, img.size[1] - 1], radius=_r, fill=sc)
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
                            return gr.gen_shadow_card(d, _n, _w, _h, _r, _f, shadow=_sh, crop=False)

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
            size = max(w, h)
            name = f'emoji_{cap or ctx.n}_{self.gen_count}.png'

            def _e(d, _n=name, _s=size, _c=emoji_ch):
                return gr.emoji_icon(d, _n, _s, _c)

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

    def convert(self, text):
        p = _DomParser()
        p.feed(text)
        p.close()
        if p.root is None:
            return None, ['空 HTML']
        screen = self._find_screen(p.root)
        if screen is None:
            return None, ['未找到 <div class="screen"> 根节点（受限 HTML 必须从 screen 容器开始）']
        ctx = _Ctx()
        self.ctx = ctx
        self._open_screen(ctx, screen)
        for ch in screen.children:
            self._walk(ctx, ch)
        # 清理内部标记
        def _clean(d):
            for k in [k for k in d if k.startswith('__')]:
                del d[k]
            for v in d.values():
                if isinstance(v, dict):
                    _clean(v)
                elif isinstance(v, list):
                    for x in v:
                        if isinstance(x, dict):
                            _clean(x)
        if ctx.root:
            _clean(ctx.root)
            self._fix_slidewindow_icon_size(ctx.root)
        return ctx.root, ctx.warnings

    def _fix_slidewindow_icon_size(self, root):
        """SlideWindow 图标布局铁律（沛哥 2026-09-01）：iconSize 必须按实际图片尺寸，
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

        for key, val in list(root.items()):
            if not (isinstance(val, dict) and key.startswith('slidewindow__')):
                continue
            items = val.get('items') or []
            if not items:
                continue
            # 用户显式指定过 data-icon-w/h 则跳过
            if val.get('__icon_explicit'):
                continue
            # 读全部图标图实际尺寸（沛哥 2026-09-01：同一 slidewindow 所有图标尺寸必须一致）
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

    @staticmethod
    def _find_screen(node):
        if node.tag == 'div' and 'screen' in _classes(node.attrs):
            return node
        for ch in node.children:
            r = HtmlToJson._find_screen(ch)
            if r is not None:
                return r
        return None

    # ---------- 遍历 ----------
    _CSS_EFFECT_PATTERNS = (
        ('linear-gradient', '线性渐变'), ('radial-gradient', '径向渐变'),
        ('box-shadow', '阴影'), ('text-shadow', '文字阴影'),
        ('border-radius', '圆角'), ('animation', '动画'), ('transition', '过渡'),
        ('transform', '变换/旋转'), ('filter', '滤镜'), ('opacity', '透明度'),
    )

    def _warn_css_effects(self, ctx, node):
        """检测 style 里的 CSS 效果属性：FlyThings 无 CSS 引擎，不硬转，
        提示转图片（PNG/.9.png/序列帧/GIF）后用 data-pic 引用（转图 + 控件）。"""
        if _attr(node.attrs, 'data-pic'):
            return   # 作者已按规范切图（data-pic）引用，效果就在图里，不必再提示
        style = _attr(node.attrs, 'style') or ''
        if not style:
            return
        hit = [name for pat, name in self._CSS_EFFECT_PATTERNS if pat in style]
        # 自动转图能力可用时，box-shadow 是**能转**的（阴影+圆角一并烘焙成 PNG）→ 不再误报
        if hit and _HAS_GEN_RES and getattr(self, 'asset_dir', None) and _shadow_spec(style):
            if 'text-shadow' not in style:
                hit = [h for h in hit if h != '阴影']
            hit = [h for h in hit if h != '圆角']
        if hit:
            cls = _attr(node.attrs, 'class') or ''
            ctx.warnings.append(
                f'<{node.tag} class="{cls}"> 含 CSS 效果（{"、".join(hit)}）：'
                f'FlyThings 不支持 CSS，无法硬转；请切图（PNG/.9.png/序列帧/GIF）后 '
                f'用 data-pic 引用（效果转图片 + 控件组合实现）')

    def _walk(self, ctx, node):
        classes = _classes(node.attrs)
        tag = node.tag

        # ⚠️ CSS 效果检测（不硬转，提示转图片）
        self._warn_css_effects(ctx, node)

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

        typ = _detect_type(tag, classes, node.attrs)

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
    def _open_screen(self, ctx, node):
        attrs = node.attrs
        # 分辨率优先级：res 参数 > data-res > data-width+data-height（.screen 上直接写宽高）> 默认 480x272
        res = self.res or _attr(attrs, 'data-res')
        W, H = 480, 272
        if res:
            m = re.match(r'^\s*(\d+)\s*[xX]\s*(\d+)\s*$', str(res))
            if m:
                W, H = int(m.group(1)), int(m.group(2))
        else:
            w_attr = parse_px(_attr(attrs, 'data-width'))
            h_attr = parse_px(_attr(attrs, 'data-height'))
            if w_attr and h_attr:
                W, H = w_attr, h_attr
            else:
                style_pos = _style_pos(_attr(attrs, 'style') or '')
                if style_pos.get('width') and style_pos.get('height'):
                    W, H = style_pos['width'], style_pos['height']
        # 背景色：data-background 与 data-bg 互为别名；不写则透明（不设 backgroundColor，navibar/statusbar 校准）
        bg = to_dec(_attr(attrs, 'data-background'))
        if bg is None:
            bg = to_dec(_attr(attrs, 'data-bg'))
        root = {
            'beepEnable': True, 'id': 0,
            'resolution': {'height': H, 'width': W},
            'topmost': str(_attr(attrs, 'data-topmost') or '').strip() in ('1', 'true'),
        }
        if bg is not None:
            root['backgroundColor'] = bg
        # 根 position：默认全屏；只有显式写 data-x/y/w/h（或 data-left/top/width/height / style 定位）
        # 才作为局部悬浮块（statusbar/navibar 校准），否则强制全屏（PageWindowDemo 回归验证）
        def _has_pos_attr(a):
            for k in ('data-x', 'data-y', 'data-w', 'data-h',
                      'data-left', 'data-top', 'data-width', 'data-height'):
                if _attr(a, k):
                    return True
            st = _attr(a, 'style') or ''
            return bool(re.search(r'(?:^|;)\s*(left|top|width|height)\s*:', st))
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
        #   backgroundColor/hideTimeOut/modal/touchable/visible 含默认也显式（-1/false）；beepEnable 不强制（沛哥）
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
        if bgc:
            c['backgroundColor'] = bgc
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
                    # ⚠️ 2026-09-11：阴影图带透明外扩边，控件底色必须取**页面底色** ——
                    # 否则整块外扩区被控件底色（本例白）填满 → 阴影渐变/圆角都看不出来。
                    # 卡体填充色已烘焙进阴影图，不需要控件再填一次。
                    root_bg = (ctx.root or {}).get('backgroundColor')
                    if root_bg is not None:
                        c['backgroundColor'] = root_bg
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
        # ⚠️ position 必写（沛哥 2026-09-08）：行高 = lv高/rows - rowSpacing（公式见函数尾）；iconPosition/textPosition 布局键条件写
        item = {'alignment': 37, 'backgroundColor': -1, 'bgColorTab': {'color0': -1},
                'bold': False, 'caption': 'item',
                'colorTab': {'color0': 16777215}, 'fontSize': 16,
                'italic': False, 'longClickIntervalTime': -1, 'longClickTimeOut': -1,
                'picTab': {}, 'text': 'ListItem',
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
        # ⚠️ item.position 必写（沛哥 2026-09-08）
        # 行高公式 = lv高/rows 均分 - rowSpacing（basedemo-new_z20_1024_600 验证：164/4-5=36✓ 437/3-5≈140✓ 424/5-0=84✓；
        # SampleUI 216x275 rows5→55 同吻合）；item 宽 = lv 宽
        _lvp = c['position']
        _ih = int(_lvp.get('height', 0) / max(c.get('rows') or 5, 1)) - (c.get('rowSpacing') or 0)
        item['position'] = {'left': 0, 'top': 0,
                            'width': _lvp.get('width', 100),
                            'height': max(_ih, 1)}
        key = ctx.add('listview', c)   # 支持嵌套（listview 在 window 内）
        ctx.stack.append(c)

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
        dragMaxDis 最大拖动距离 + orientation 滑动方向（垂直/水平） + edgeEffect 边界效果（拖拽/无/循环）。
        滚动内容 = 内嵌的普通 window（尺寸=dragMaxDis，如 ScrollWin 2400），window 内再嵌面板。
        """
        attrs = node.attrs
        cap = self._caption(ctx, 'scrollwindow', attrs)
        c = {'caption': cap,
             'dragMaxDis': 200, 'edgeEffect': 1,
             'id': ctx.nid('scrollwindow'),
             'orientation': 0,
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
        item = {'colorTab': {'color0': to_dec(_attr(attrs, 'data-color')) or 0xFFFFFF},
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
                'penColor': to_dec(_attr(attrs, 'data-color')) or 0xFFFFFF,
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
        # touchable 必须 True（沛哥 2026-09-10 修正）：radiogroup 是「容器显式 false」口径的例外——
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
        text = _clean_text(node.text)

        # 在 listview 内 → subItem
        if ctx.stack and ctx.stack[-1].get('__listview'):
            # subItem 子项（UIlayoutDemo/listview.ftu 校准）：支持背景图（头像等图片子项）+ 对齐 + 字号/颜色
            # subItem v2（SampleUI subitem 19 键 100%）：补安全默认键；iconPosition/textPosition/backgroundPic 条件写
            # （引擎缺省 icon/text 区 = position/控件区，历史验证 OK；有 backgroundPic 时用 backgroundPic 显示）
            si = {'alignment': ALIGN.get((_attr(attrs, 'data-align') or 'center').lower(), 37),
                  'backgroundColor': -1, 'bgColorTab': {'color0': -1},
                  'bold': False, 'caption': cap,
                  'colorTab': {'color0': to_dec(_attr(attrs, 'data-color')) or 0xEEF2F6},
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
                  'bgColorTab': {'color0': to_dec(_attr(attrs, 'data-bg')) or 0x9FA05F,
                                 'color2': to_dec(_attr(attrs, 'data-bg2')) or 0x55736C},
                  'colorTab': {'color0': to_dec(_attr(attrs, 'data-color')) or 0xEEF2F6},
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
                 'colorTab': {'color0': to_dec(_attr(attrs, 'data-color')) or 0xEEF2F6},
                 'fontSize': self._font_size(attrs) or 16,   # SampleUI textview fontSize 100% 必写（默认 16）
                 'id': ctx.nid('textview'),
                 'position': pos, 'touchable': False}
            bgc = self._bg_color(attrs)
            if bgc:
                c['bgColorTab'] = {'color0': bgc}
            if text:
                c['text'] = text
            self._text_extra(c, attrs)
            # 自动转图：CSS 效果（渐变/阴影/emoji/loading）→ backgroundPic
            eff = self._effect_assets(ctx, node, pos.get('width', 100), pos.get('height', 40), cap)
            if eff.get('use_emoji'):
                # emoji 文本 → 图标 textview（清除文本，避免设备字库不支持）
                c.pop('text', None)
                c.pop('bgColorTab', None)
                c['touchable'] = False
            if eff.get('backgroundPic'):
                c['backgroundPic'] = eff['backgroundPic']
                c.pop('bgColorTab', None)   # 有图不用底色（透明角图会透底色）
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
            #  否则图片叠在颜色上效果与预想不同；仅纯文字按钮才用 bgColorTab/colorTab 多态色
            # ⚠️ 2026-09-05 修正：无底色且无文字的按钮（透明热区，覆盖卡片/图片上当点击区）不写 bgColorTab，
            #    避免默认底色 0x374457 遮住下层内容；有 data-bg 或纯文字按钮才设底色（text 由 _leaf 预先解析）
            bgc = self._bg_color(attrs)
            c = {'alignment': ALIGN.get((_attr(attrs, 'data-align') or 'center').lower(), 37),
                 'caption': cap,
                 'colorTab': {'color0': to_dec(_attr(attrs, 'data-color')) or 0xEEF2F6},
                 'id': ctx.nid('button'),
                 'position': pos, 'touchable': True}   # SampleUI button touchable 恒 true（沛哥：交互控件显式 true）
            if bgc or text:
                c['bgColorTab'] = {'color0': bgc or 0x374457}
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
            # iconfont 图标按钮（2026-09-03 沛哥定规：图标优先）：
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
                c.pop('bgColorTab', None)   # 图片按钮不放底色（透明角会透出底色，图片叠色效果错乱）
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
            c = {'alignment': 37, 'bold': False, 'caption': cap,   # SampleUI edittext 必写 bold（去 beepEnable，沛哥）
                 'bgColorTab': {'color0': self._bg_color(attrs) or 0xFFFFFF},
                 'colorTab': {'color0': to_dec(_attr(attrs, 'data-color')) or 0},
                 'fontSize': self._font_size(attrs) or 16,   # SampleUI edittext fontSize 100% 必写（默认 16）
                 'hintTextColor': 0, 'id': ctx.nid('edittext'),
                 'position': pos}
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
                c['hintText'] = _clean_text(hint)
            hc = to_dec(_attr(attrs, 'data-hint-color'))
            if hc:
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
            c.setdefault('thumb', {'size': {'width': 0, 'height': 0}})   # SampleUI seekbar 必写 thumb（空=无滑块）
        elif typ == 'checkbox':
            # padding 配置（UIlayoutDemo/checkbox.ftu 校准）：
            #  iconPosition = 图标锚点（控件内 left:0 top:0，尺寸默认=控件高，可用 data-icon-w/h 指定）
            #  textPosition = 文本区（left = 图标宽 + padding(6~8)，top:0，宽=控件宽-图标宽-padding）
            #  有图两态：picTab{pic0: 未选中, pic2: 选中}（注意选中是 pic2 不是 pic1！）
            #  无图变色：bgColorTab{color0,color2} + colorTab{color0,color2}（color2=选中态）
            cw, ch = pos.get('width', 100), pos.get('height', 40)
            iw = int(_attr(attrs, 'data-icon-w') or ch)
            ih = int(_attr(attrs, 'data-icon-h') or ch)
            pad = int(_attr(attrs, 'data-pad') or 6)
            # basedemo checkbox 全字段（23 键 100%）：补安全默认键（fontFamily/roll* 从宽不写）
            c = {'alignment': 36, 'backgroundColor': -1,
                 'bold': False, 'caption': cap, 'checked': False,
                 'fontSize': self._font_size(attrs) or 16,
                 'italic': False, 'touchable': True,
                 'bgColorTab': {'color0': to_dec(_attr(attrs, 'data-bg')) or 0x607A84,
                                'color2': to_dec(_attr(attrs, 'data-bg2')) or 0x55736C},
                 'colorTab': {'color0': to_dec(_attr(attrs, 'data-color')) or 0xEEF2F6,
                              'color2': to_dec(_attr(attrs, 'data-color2')) or 0xFFFFFF},
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
                c.pop('bgColorTab', None)  # 有图不用底色
            # basedemo checkbox/radiobutton 均 100% 写 text → 恒写（空串合法）
            c['text'] = text if text else ''
            if str(_attr(attrs, 'data-checked') or '').strip() in ('1', 'true'):
                c['checked'] = True
            self._text_extra(c, attrs)
        elif typ == 'circlebar':
            # 圆形进度条（UIlayoutDemo/circlebar.ftu 校准）：backgroundPic 背景图（不裁剪）+
            #   progressPic 有效图（按进度裁剪扇形）+ progressPicPos 有效图位置 + max/maxAngle/startAngle + clockwise
            # ⚠️ clockwise: false = 逆时针（demo 曾反，沛哥 17:17 确认）
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
            col = to_dec(_attr(attrs, 'data-color')) or to_dec(_attr(attrs, 'data-clock-color'))
            if col:
                c['clockColor'] = col
            bgc = self._bg_color(attrs)
            if bgc:
                c['bgColorTab'] = {'color0': bgc}
        elif typ == 'slidetext':
            # 候选字滑动条（ImeDemo/UserIme 校准）：textBgColor 文字背景色，输入法候选词用
            c = {'caption': cap, 'id': ctx.nid('slidetext'),
                 'touchable': False, 'position': pos}
            fs = self._font_size(attrs)
            if fs:
                c['fontSize'] = fs
            tbg = to_dec(_attr(attrs, 'data-text-bg'))
            if tbg:
                c['textBgColor'] = tbg
            col = to_dec(_attr(attrs, 'data-color'))
            if col:
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
            # SampleUI qrcode touchable:true + 沛哥口径 padding 默认各边 10
            c = {'backgroundColor': 16777215, 'caption': cap,
                 'id': ctx.nid('qrcode'), 'padding': 10,
                 'touchable': True, 'visible': True,
                 'position': pos}
            cs = _attr(attrs, 'data-code')
            if cs:
                c['codeStr'] = cs
            bgc = to_dec(_attr(attrs, 'data-bg'))
            if bgc:
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
                 'colorTab': {'color0': to_dec(_attr(attrs, 'data-color')) or 0xEEF2F6},
                 'fontSize': self._font_size(attrs) or 16,
                 'id': ctx.nid('textview'), 'position': pos, 'touchable': False}
            pic = _attr(attrs, 'data-pic') or _attr(attrs, 'src')
            if pic:
                c['backgroundPic'] = pic if '/' in pic else 'images/' + pic
            else:
                # iconfont 图标自动生成（2026-09-03 沛哥定规：图标优先）：
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
    - FT-006：顶层多个互斥全屏 window → 告警（页面级应拆多 Activity）
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

    # ---- FT-006 页面级多全屏 window（互斥页面应拆多 Activity，不堆单 json）----
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
            warnings.append(f'检测到页面级互斥全屏 Window（{names}）：页面级页面应拆多个 Activity '
                            f'用 Intent 跳转（onUI_intent / openActivity），不要单 json 堆全屏 Window '
                            f'做 visible 状态机；功能窗口内的局部内容才用 Window 嵌套')
    return data


def html2json(input_html, output_json=None, res=None, asset_dir=None):
    """受限 HTML → json 布局。返回 {success, jsonPath, resolution, controls, warnings}。

    asset_dir：CSS 效果（渐变/阴影/emoji/loading）自动转图输出目录；
    缺省自动定位到项目 resources/images/（json 引用 images/xxx.png 相对 resources 目录，与设备加载一致）：
      - output_json 位于 <项目>/ui/ 下 → asset_dir = <项目>/resources/images/
      - 其它位置 → 回退 json 同目录 images/ 并警告（提示手动挪图或显式传 asset_dir）
    不传 output_json 且不传 asset_dir 时不做自动转图（纯布局转换）。"""
    if not os.path.isfile(input_html):
        return {'success': False, 'error': f'html 文件不存在: {input_html}'}
    with open(input_html, encoding='utf-8-sig') as f:
        text = f.read()
    warnings = []
    if asset_dir is None and output_json:
        out_dir = os.path.dirname(os.path.abspath(output_json))
        if os.path.basename(out_dir) == 'ui':
            # <项目>/ui/main.json → 图片输出到 <项目>/resources/images/
            asset_dir = os.path.join(os.path.dirname(out_dir), 'resources', 'images')
        else:
            asset_dir = os.path.join(out_dir, 'images')
            warnings.append('output_json 不在 <项目>/ui/ 目录下，自动转图输出到 json 同目录 images/；'
                            '建议把图片移到项目 resources/images/ 后 json 引用 images/xxx.png（相对 resources）')
    conv = HtmlToJson(res=res, asset_dir=asset_dir)
    data, w2 = conv.convert(text)
    warnings += w2
    if data is None:
        return {'success': False, 'error': '未找到 <div class="screen"> 根节点（受限 HTML 必须从 screen 容器开始）'}
    _finalize_layout(data, warnings)  # 收尾规范：FT-009 最小尺寸 / FT-006 多全屏 window 告警

    if output_json:
        os.makedirs(os.path.dirname(os.path.abspath(output_json)), exist_ok=True)
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    resv = data.get('resolution', {})
    count = sum(1 for k, v in data.items() if isinstance(v, dict) and '__' in k)
    return {'success': True, 'jsonPath': output_json,
            'resolution': f"{resv.get('width')}x{resv.get('height')}",
            'controls': count, 'warnings': warnings,
            'generatedAssets': conv.gen_count,
            'assetDir': asset_dir}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    res = None
    for a in sys.argv[1:]:
        if a.startswith('--res='):
            res = a.split('=', 1)[1]
    if len(args) < 1:
        print('用法: python html2json.py <input.html> [output.json] [--res WxH]')
        sys.exit(1)
    src = args[0]
    dst = args[1] if len(args) > 1 else os.path.splitext(src)[0] + '.json'
    r = html2json(src, dst, res=res)
    if not r['success']:
        print('[X]', r['error'])
        sys.exit(1)
    print(json.dumps(r, ensure_ascii=False, indent=1))
