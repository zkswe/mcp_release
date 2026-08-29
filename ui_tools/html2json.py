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
    'icon': ('icon', 'img', 'image', 'pic'),
    'circlebar': ('circlebar', 'circular', 'ring'),
    'diagram': ('diagram', 'wave', 'chart'),
    'digitalclock': ('digitalclock', 'clock', 'time'),
    'imageanim': ('imageanim', 'anim', 'gif'),
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
    """数值属性（可带 px/小数）：data-step="10" / "10.0" / "5px"；整数返回 int，小数返回 float。"""
    if v is None:
        return default
    try:
        s = str(v).strip()
        m = re.match(r'^([\d.]+)(?:px?)?$', s)
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


def _detect_type(tag, classes):
    """HTML 标签 + class → FlyThings 控件类型。"""
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
    if tag in ('p', 'span', 'h1', 'h2', 'h3', 'label', 'div'):
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
    """粗略判断字符是否 emoji（补充平面/符号区）。"""
    o = ord(ch)
    return (o >= 0x1F000 and o <= 0x1FAFF) or (o >= 0x2600 and o <= 0x27BF) or o in (0x2B50, 0x2B55, 0x2764, 0xFE0F)


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
            # ⛔ FlyThings textview 不支持 \n 多行：<br> 折叠为空格（避免文字粘连）
            self.stack[-1].text += ' '

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
            self.stack[-1].text += data


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
        sm = re.search(r'box-shadow\s*:\s*([^;]+)', style)
        if sm:
            parts = sm.group(1).strip().split()
            if len(parts) >= 4:
                try:
                    ox, oy, blur = int(float(parts[0])), int(float(parts[1])), int(float(parts[2]))
                    sc = _css_color(parts[3]) or (0, 0, 0, 80)
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
                            return gr.gen_shadow_card(d, _n, _w, _h, _r, _f, shadow=_sh)

                        pic = self._gen_asset(_s)
                        if pic:
                            out['backgroundPic'] = pic
                except Exception:
                    pass

        # 3. emoji 图标 → PNG（文本含 emoji，转图标 textview）
        text = re.sub(r'\s+', ' ', node.text).strip()
        if text and any(_is_emoji(ch) for ch in text):
            emoji_ch = next((ch for ch in text if _is_emoji(ch)), '\u2b50')
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
        return ctx.root, ctx.warnings

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
        style = _attr(node.attrs, 'style') or ''
        if not style:
            return
        hit = [name for pat, name in self._CSS_EFFECT_PATTERNS if pat in style]
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

        typ = _detect_type(tag, classes)

        # 在 diagram 容器内：子 div.wave 收进父容器 infos（每条波形配置）
        if ctx.stack and ctx.stack[-1].get('__diagram') and typ == 'diagram':
            self._append_wave(ctx, node)
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
        # 背景色：data-background 与 data-bg 互为别名
        bg = to_dec(_attr(attrs, 'data-background'))
        if bg is None:
            bg = to_dec(_attr(attrs, 'data-bg'))
        if bg is None:
            bg = 0x0E131A
        ctx.root = {
            'backgroundColor': bg, 'beepEnable': True, 'id': 0,
            'resolution': {'height': H, 'width': W}, 'topmost': False,
            'position': {'height': H, 'left': 0, 'top': 0, 'width': W},
        }

    # ---------- 容器 ----------
    def _open_window(self, ctx, node, modal):
        attrs = node.attrs
        cap = self._caption(ctx, 'window', attrs)
        c = {'beepEnable': True, 'caption': cap,
             'id': ctx.nid('window'),
             'position': self._pos(attrs)}
        if modal:
            c['modal'] = True
            c['visible'] = False
        pic = _attr(attrs, 'data-pic')
        if pic:
            c['backgroundPic'] = pic if '/' in pic else 'images/' + pic
        else:
            # 自动转图：CSS 效果（渐变/阴影/emoji）→ 背景图
            pos = c['position']
            eff = self._effect_assets(ctx, node, pos.get('width', 100), pos.get('height', 40), cap)
            if eff.get('backgroundPic'):
                c['backgroundPic'] = eff['backgroundPic']
        c['__container'] = True
        key = ctx.key('window')
        ctx.root[key] = c
        ctx.stack.append(c)

    def _open_listview(self, ctx, node):
        attrs = node.attrs
        cap = self._caption(ctx, 'listview', attrs)
        c = {'beepEnable': True, 'caption': cap, 'cols': 1, 'rows': 5,
             'id': ctx.nid('listview'),
             'position': self._pos(attrs),
             'colSpacing': 0, 'rowSpacing': 1, 'orientation': 1,
             'item': {'text': 'ListItem', 'subItem': []},
             '__container': True, '__listview': True}
        cols = parse_px(_attr(attrs, 'data-cols'))
        rows = parse_px(_attr(attrs, 'data-rows'))
        if cols:
            c['cols'] = cols
        if rows:
            c['rows'] = rows
        key = ctx.key('listview')
        ctx.root[key] = c
        ctx.stack.append(c)

    def _open_diagram(self, ctx, node):
        """波形图：backgroundPic 背景图 + xAxisRange/yAxisRange 坐标范围 + region 绘图区 + infos[] 波形配置。
        子 div.wave 每条收进 infos（penColor/penWidth/step/style/antialias/eraseSpace/xScale/yScale）。
        style: 0=折线 1=曲线（UIlayoutDemo/diagram.ftu 校准）；eraseSpace=刷新间距。
        """
        attrs = node.attrs
        cap = self._caption(ctx, 'diagram', attrs)
        pos = self._pos(attrs)
        c = {'caption': cap, 'id': ctx.nid('diagram'),
             'touchable': False, 'position': pos,
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
        key = ctx.key('diagram')
        ctx.root[key] = c
        ctx.stack.append(c)

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
                'xScale': _num(_attr(attrs, 'data-x-scale'), 1.0),
                'yScale': _num(_attr(attrs, 'data-y-scale'), 1.0)}
        ctx.stack[-1]['infos'].append(info)

    def _open_radiogroup(self, ctx, node):
        attrs = node.attrs
        cap = self._caption(ctx, 'radiogroup', attrs)
        c = {'caption': cap, 'id': ctx.nid('radiogroup'),
             'position': self._pos(attrs),
             '__container': True, '__radiogroup': True, 'radiobuttons': []}
        key = ctx.key('radiogroup')
        ctx.root[key] = c
        ctx.stack.append(c)

    # ---------- 叶子 ----------
    def _leaf(self, ctx, node, typ):
        attrs = node.attrs
        cap = self._caption(ctx, typ, attrs)
        pos = self._pos(attrs)
        text = re.sub(r'\s+', ' ', node.text).strip()

        # 在 listview 内 → subItem
        if ctx.stack and ctx.stack[-1].get('__listview'):
            si = {'alignment': 37, 'caption': cap, 'id': ctx.nid('subitem'),
                  'colorTab': {'color0': to_dec(_attr(attrs, 'data-color')) or 0xEEF2F6},
                  'position': pos}
            fs = self._font_size(attrs)
            if fs:
                si['fontSize'] = fs
            if text:
                si['text'] = text
            ctx.stack[-1]['item']['subItem'].append(si)
            return

        # 在 radiogroup 内 → radiobutton
        if ctx.stack and ctx.stack[-1].get('__radiogroup'):
            rb = {'alignment': 38, 'caption': cap, 'checked': False,
                  'bgColorTab': {'color0': to_dec(_attr(attrs, 'data-bg')) or 0x9FA05F,
                                 'color2': to_dec(_attr(attrs, 'data-bg2')) or 0x55736C},
                  'colorTab': {'color0': to_dec(_attr(attrs, 'data-color')) or 0xEEF2F6},
                  'id': ctx.nid('radiobutton'),
                  'position': pos}
            if text:
                rb['text'] = text
            if str(_attr(attrs, 'data-checked') or '').strip() in ('1', 'true'):
                rb['checked'] = True
            ctx.stack[-1]['radiobuttons'].append(rb)
            return

        # 普通叶子控件
        if typ == 'textview':
            c = {'alignment': ALIGN.get((_attr(attrs, 'data-align') or 'left').lower(), 36),
                 'caption': cap,
                 'colorTab': {'color0': to_dec(_attr(attrs, 'data-color')) or 0xEEF2F6},
                 'id': ctx.nid('textview'),
                 'position': pos, 'touchable': False}
            fs = self._font_size(attrs)
            if fs:
                c['fontSize'] = fs
            bgc = self._bg_color(attrs)
            if bgc:
                c['bgColorTab'] = {'color0': bgc}
            if text:
                c['text'] = text
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
            c = {'alignment': ALIGN.get((_attr(attrs, 'data-align') or 'center').lower(), 37),
                 'caption': cap,
                 'bgColorTab': {'color0': self._bg_color(attrs) or 0x374457},
                 'colorTab': {'color0': to_dec(_attr(attrs, 'data-color')) or 0xEEF2F6},
                 'id': ctx.nid('button'),
                 'position': pos}
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
            if pics:
                c['picTab'] = pics
            else:
                # 背景图按钮：backgroundPic 单图（BtnBgPic demo），有图也去底色
                bgpic = _attr(attrs, 'data-bgpic') or _attr(attrs, 'data-background-pic')
                if bgpic:
                    c['backgroundPic'] = bgpic if '/' in bgpic else 'images/' + bgpic
                else:
                    # 自动转图：渐变/阴影 → 按钮背景图（picTab 单态，无 pressed 时用同一张）
                    eff = self._effect_assets(ctx, node, pos.get('width', 100), pos.get('height', 40), cap)
                    if eff.get('backgroundPic'):
                        c['picTab'] = {'pic0': eff['backgroundPic'], 'pic1': eff['backgroundPic']}
            if 'picTab' in c or 'backgroundPic' in c:
                c.pop('bgColorTab', None)   # 图片按钮不放底色（透明角会透出底色，图片叠色效果错乱）
            # 图标按钮 padding（Button1 demo）：data-icon-w/h 图标尺寸 + data-pad 间隙 → iconPosition
            if _attr(attrs, 'data-icon-w') or _attr(attrs, 'data-icon-h'):
                cw, ch = pos.get('width', 100), pos.get('height', 40)
                iw = int(_attr(attrs, 'data-icon-w') or ch)
                ih = int(_attr(attrs, 'data-icon-h') or ch)
                c['iconPosition'] = {'left': 0, 'top': 0, 'width': iw, 'height': ih}
        elif typ == 'edittext':
            c = {'alignment': 37, 'beepEnable': True, 'caption': cap,
                 'bgColorTab': {'color0': self._bg_color(attrs) or 0xFFFFFF},
                 'colorTab': {'color0': to_dec(_attr(attrs, 'data-color')) or 0},
                 'hintTextColor': 0, 'id': ctx.nid('edittext'),
                 'position': pos}
            fs = self._font_size(attrs)
            if fs:
                c['fontSize'] = fs
            if str(_attr(attrs, 'data-num') or '').strip() in ('1', 'true'):
                c['textType'] = 1
            if str(_attr(attrs, 'data-password') or '').strip() in ('1', 'true'):
                c['isPassword'] = True
            hint = _attr(attrs, 'data-hint')
            if hint:
                c['hintText'] = hint
            hc = to_dec(_attr(attrs, 'data-hint-color'))
            if hc:
                c['hintTextColor'] = hc
            if text:
                c['text'] = text
        elif typ == 'seekbar':
            c = {'caption': cap, 'defProgress': 0, 'id': ctx.nid('seekbar'),
                 'max': 100, 'orientation': 0, 'touchable': False,
                 'position': pos}
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
            c = {'alignment': 36, 'caption': cap, 'checked': False,
                 'bgColorTab': {'color0': to_dec(_attr(attrs, 'data-bg')) or 0x607A84,
                                'color2': to_dec(_attr(attrs, 'data-bg2')) or 0x55736C},
                 'colorTab': {'color0': to_dec(_attr(attrs, 'data-color')) or 0xEEF2F6,
                              'color2': to_dec(_attr(attrs, 'data-color2')) or 0xFFFFFF},
                 'iconPosition': {'left': 0, 'top': 0, 'width': iw, 'height': ih},
                 'id': ctx.nid('checkbox'),
                 'position': pos,
                 'textPosition': {'left': iw + pad, 'top': 0,
                                  'width': max(cw - iw - pad, 10), 'height': ch}}
            # 两态图（优先）：pic0=未选中 pic2=选中；data-pic/data-pic2 或 data-src/data-src2
            pic0 = _attr(attrs, 'data-pic') or _attr(attrs, 'data-pic0') or _attr(attrs, 'data-src')
            pic2 = _attr(attrs, 'data-pic2') or _attr(attrs, 'data-src2')
            if pic0:
                c['picTab'] = {'pic0': pic0 if '/' in pic0 else 'images/' + pic0,
                               'pic2': (pic2 if '/' in pic2 else 'images/' + pic2) if pic2 else (pic0 if '/' in pic0 else 'images/' + pic0)}
                c.pop('bgColorTab', None)  # 有图不用底色
            if text:
                c['text'] = text
            if str(_attr(attrs, 'data-checked') or '').strip() in ('1', 'true'):
                c['checked'] = True
        elif typ == 'circlebar':
            # 圆形进度条（UIlayoutDemo/circlebar.ftu 校准）：backgroundPic 背景图（不裁剪）+
            #   progressPic 有效图（按进度裁剪扇形）+ progressPicPos 有效图位置 + max/maxAngle/startAngle + clockwise
            # ⚠️ clockwise: false = 逆时针（demo 曾反，沛哥 17:17 确认）
            cw, ch = pos.get('width', 200), pos.get('height', 200)
            c = {'beepEnable': True, 'caption': cap,
                 'id': ctx.nid('circlebar'), 'max': 100, 'maxAngle': 360,
                 'position': pos}
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
        elif typ == 'digitalclock':
            # 数字时钟（UIlayoutDemo/digitalclock.ftu 校准）：format 时间格式 + beat 冒号闪烁，自动实时刷新系统时间
            # format 大小写含义：HH=24小时制 hh=12小时制 MM=分钟 SS=秒 yyyy-MM-dd=日期 EEEE=星期
            c = {'caption': cap, 'id': ctx.nid('digitalclock'),
                 'touchable': False, 'position': pos}
            fs = self._font_size(attrs)
            if fs:
                c['fontSize'] = fs
            fmt = _attr(attrs, 'data-format')
            if fmt:
                c['format'] = fmt
            beat = _attr(attrs, 'data-beat')
            if beat is not None:
                c['beat'] = str(beat).strip() in ('1', 'true')
            col = to_dec(_attr(attrs, 'data-color'))
            if col:
                c['colorTab'] = {'color0': col}
            bgc = self._bg_color(attrs)
            if bgc:
                c['bgColorTab'] = {'color0': bgc}
        elif typ == 'icon':
            c = {'alignment': 36, 'caption': cap,
                 'colorTab': {'color0': to_dec(_attr(attrs, 'data-color')) or 0xEEF2F6},
                 'id': ctx.nid('textview'), 'position': pos, 'touchable': False}
            pic = _attr(attrs, 'data-pic') or _attr(attrs, 'src')
            if pic:
                c['backgroundPic'] = pic if '/' in pic else 'images/' + pic
            typ = 'textview'
        else:
            c = {'caption': cap, 'id': ctx.nid('textview'), 'position': pos}
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


def html2json(input_html, output_json=None, res=None, asset_dir=None):
    """受限 HTML → json 布局。返回 {success, jsonPath, resolution, controls, warnings}。

    asset_dir：CSS 效果（渐变/阴影/emoji/loading）自动转图输出目录；
    缺省 = output_json 同目录 images/（即 ui/images/，json 引用 images/xxx.png）。
    不传 output_json 且不传 asset_dir 时不做自动转图（纯布局转换）。"""
    if not os.path.isfile(input_html):
        return {'success': False, 'error': f'html 文件不存在: {input_html}'}
    with open(input_html, encoding='utf-8-sig') as f:
        text = f.read()
    if asset_dir is None and output_json:
        asset_dir = os.path.join(os.path.dirname(os.path.abspath(output_json)), 'images')
    conv = HtmlToJson(res=res, asset_dir=asset_dir)
    data, warnings = conv.convert(text)
    if data is None:
        return {'success': False, 'error': '未找到 <div class="screen"> 根节点（受限 HTML 必须从 screen 容器开始）'}

    if output_json:
        os.makedirs(os.path.dirname(os.path.abspath(output_json)), exist_ok=True)
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    resv = data.get('resolution', {})
    count = sum(1 for k, v in data.items() if isinstance(v, dict) and '__' in k)
    return {'success': True, 'jsonPath': output_json,
            'resolution': f"{resv.get('width')}x{resv.get('height')}",
            'controls': count, 'warnings': warnings,
            'generatedAssets': conv.gen_count}

    if output_json:
        os.makedirs(os.path.dirname(os.path.abspath(output_json)), exist_ok=True)
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    resv = data.get('resolution', {})
    count = sum(1 for k, v in data.items() if isinstance(v, dict) and '__' in k)
    return {'success': True, 'jsonPath': output_json,
            'resolution': f"{resv.get('width')}x{resv.get('height')}",
            'controls': count, 'warnings': warnings}


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
