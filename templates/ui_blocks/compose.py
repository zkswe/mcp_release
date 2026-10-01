#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""界面块片段库组装器（MVP）——「选块 + 填值 + 排序」→ 可交付的 UI 产物。

一句话：像用 Bootstrap 那样拼界面。输入一份 spec（分辨率 + 页面标题 + 块列表），
按块定义里的**相对约束**换算成绝对坐标，产出：
  1. ui/<res>/<page>.json   （字段全集显式、id 连续编号、根节点 id:0）
  2. resources/images/*.png （只给需要的块出图；**图 == 控件盒**，走 ui_tools/gen_res.py）
  3. --render 时出渲染图（走 ui_tools/json2img.py）
  4. --check  时跑全检（走 ui_tools/check_all.py）

设计铁律（照抄，不自创）：
  · 字段全集显式化  → knowledge/uicontrols/json-field-mandatory.md
  · 相对约束/设置行形态 → knowledge/uicontrols/scrollwindow-layout-checklist.md §2.1
  · dragMaxDis = 越界拖拽上限（不是行程） → knowledge/uicontrols/scroll-drag-interaction-spec.md
  · 切图「图 == 盒」+ 抗锯齿/倒角口径 → knowledge/devflow/ui-asset-rules.md
  · 设计令牌/相对尺度 → projects/UISpec-Demo/docs/SPEC-CHECK.md §7/§8 + blocks/_tokens.json
  · caption 全页唯一（块序号**全页全局递增** + 块类型前缀；同名 caption ⇒ onButtonClick_ 重定义 ⇒
    C++ 编译失败）→ 见本文件 BLOCK_PREFIX / assert_caption_unique（修前按卡内序号分配 = 跨卡重名）

用法：
  python templates/ui_blocks/compose.py spec.json --project <项目根> [--page main] [--render] [--check]

本文件**只调用现有工具做单一实现**（gen_res / json2img / check_all），不复制它们的逻辑。
"""
import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))                 # tools/FlyThings_mcp_open
UI_TOOLS = os.path.join(os.path.dirname(REPO), 'ui_tools')     # tools/ui_tools（现有工具的家）
BLOCKS_DIR = os.path.join(HERE, 'blocks')
sys.path.insert(0, UI_TOOLS)
import gen_res                                                 # noqa: E402  唯一出图实现

sys.stdout.reconfigure(encoding='utf-8')

# ─────────────────────── caption 命名口径（全页唯一，2026-10-01 修正）───────────────────────
# 缺陷（修前）：块名按「卡内序号」分配（每张卡从 1 重数）→ 跨卡重名；caption 前缀又不区分块类型
#   ⇒ 同页出现 ButtonRowSettingRow1 / ImageRowSettingRow1Chevron / TextRowSettingRow1Label /
#     TextRowSettingRow1Value / RowSep1 等重名 caption
#   ⇒ 生成的 src/logic/<page>Logic.cc 里 onButtonClick_ButtonRowSettingRow1 **定义两次**（C++ 重定义，
#     编译必失败；check_all #5 只查「回调是否存在」不查唯一，所以一路 PASS）。
# 口径（修后）：
#   · 块序号 = **全页全局递增**（1,2,3…，跨卡不重置；卡内行接着本卡的序号往下数）
#   · 块名   = <块类型前缀><序号>（setting_row→SettingRow4 / icon_row→IconRow5 /
#              toggle_row→ToggleRow6 / device_card→DeviceCard7 / card→Card2 / …）
#   · 行族子控件 = <角色><块名>（ImageRowSettingRow4 / ImageRowSettingRow4Chevron /
#              TextRowSettingRow4Label / TextRowSettingRow4Value / ButtonRowSettingRow4）
#   · 分隔线     = RowSep<上一行块的序号>（RowSep4）
#   · 容器/页面级子控件 = <角色><该块序号>（Card2 / CardBg2 / SectionHeader2 / EmptyStateBg3 /
#              ButtonPrimary9 / DialogWindow13 …）
#   · compose 出产物前 `assert_caption_unique`：任何重名 → 报错退出（不许静默出产物）
BLOCK_PREFIX = {
    'page_title': 'Title',
    'section_header': 'SectionHeader',
    'card': 'Card',
    'setting_row': 'SettingRow',
    'icon_row': 'IconRow',
    'toggle_row': 'ToggleRow',
    'device_card': 'DeviceCard',
    'empty_state': 'EmptyState',
    'bottom_actions': 'Action',
    'dialog': 'Dialog',
}


def duplicate_captions(doc):
    """doc 内 caption 重名清单 {caption: [控件 key, ...]}（只返回重复项；空 caption 不计）。"""
    seen = defaultdict(list)

    def walk(o):
        for k, v in o.items():
            if isinstance(v, dict) and '__' in k:
                cap = v.get('caption')
                if cap:
                    seen[cap].append(k)
                walk(v)
    walk(doc)
    return {c: keys for c, keys in seen.items() if len(keys) > 1}


def assert_caption_unique(doc, page_name=''):
    """自检：任一 caption 重名 → 报错退出。

    重名的直接后果：src/logic/<page>Logic.cc 会生成两份 onButtonClick_<caption> → C++ 重定义报错；
    业务代码按 caption 取控件（m<caption>Ptr / getControl）也会取到错的那个。
    """
    dups = duplicate_captions(doc)
    if not dups:
        return
    lines = ['[X] caption 重名 %d 个（页面 %s）：重名 ⇒ onButtonClick_<caption> 重定义 ⇒ C++ 编译必失败'
             % (len(dups), page_name)]
    for cap, keys in sorted(dups.items()):
        lines.append('    - %s 出现 %d 次：%s' % (cap, len(keys), ', '.join(keys)))
    raise SystemExit('\n'.join(lines))


# ─────────────────────────── 基础工具 ───────────────────────────


def r4(v):
    """4px 栅格（令牌体系里所有几何值都落在 4 的倍数上）。"""
    return max(4, int(round(float(v) / 4.0)) * 4)


def pick(target, lo, hi, ladder):
    """按屏缩放后落到字号档位（不线性放大）——SPEC-CHECK §8「按屏选档」。"""
    return max(lo, min(hi, min(ladder, key=lambda x: abs(x - target))))


def hex2int(s):
    """'#RRGGBB' / '#RRGGBBAA' → int（FlyThings 色值是 0xRRGGBB 或含 alpha 的整型）。"""
    s = str(s).lstrip('#')
    if len(s) == 8:                                            # RRGGBBAA → AA 放高字节
        r, g, b, a = (int(s[i:i + 2], 16) for i in (0, 2, 4, 6))
        return (a << 24) | (r << 16) | (g << 8) | b
    return int(s[:6], 16)


def rgba(s, default_a=255):
    """'#RRGGBB' → (r,g,b,a) 元组，供 gen_res 出图用。"""
    s = str(s).lstrip('#')
    r, g, b = (int(s[i:i + 2], 16) for i in (0, 2, 4))
    a = int(s[6:8], 16) if len(s) >= 8 else default_a
    return (r, g, b, a)


def text_min_size(text, font_size, align):
    """FT-009 最小尺寸公式（防文本截断）——与 check_all #13 同一口径。
    中文/全角=1.0，英数括号=0.55，其它符号=0.6；×1.1 余量 + 16；居中再 +8；高 = 字号×1.25。"""
    if not text:
        return 0, 0
    wsum = 0.0
    for ch in text:
        if ord(ch) > 0x2E7F:
            wsum += 1.0
        elif ch.isalnum() or ch in '()[]{}':
            wsum += 0.55
        else:
            wsum += 0.6
    mw = int(wsum * font_size * 1.1) + 16
    if align in (37, 36):                                      # CENTER 补余量
        mw += 8
    return mw, int(font_size * 1.25)


# ─────────────────────────── 箭头（行尾 Chevron） ───────────────────────────


def chevron_image(w, h, color, ss=8):
    """箭头贴图：45° 圆头描边，笔画 ≈ 盒宽 12% 且 ≥2px，SS≥8 + 面积平均（Image.BOX）缩回。

    口径来源：projects/UISpec-Demo/docs/SPEC-CHECK.md §7（箭头 glyph 规则）——
    该口径是为「小盒（≥12×16）」现场定的；gen_res 的 iconfont 比例在 12px 盒上只有 1px 笔画。
    """
    from PIL import Image, ImageDraw
    ss = max(8, int(ss))
    stroke = max(2, int(round(w * 0.12)))
    span = max(4, min(h - stroke, w - stroke))
    big = Image.new('RGBA', (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    x0, cy = (w - span) // 2, h // 2
    y0, y1 = cy - span // 2, cy + span // 2
    pts = [(x0 * ss, y0 * ss), ((x0 + span) * ss, cy * ss), (x0 * ss, y1 * ss)]
    d.line(pts, fill=color, width=stroke * ss, joint='curve')
    r = stroke * ss / 2.0                                   # 圆头端点（去毛刺）
    for p in pts:
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color)
    return big.resize((w, h), Image.BOX)                    # 面积平均：带直通 α 的边界禁用负瓣算子


# ─────────────────────────── 令牌 → 本屏度量 ───────────────────────────


def build_metrics(W, H, tok):
    """把令牌/比例换算成本屏绝对度量。这里只做「比例 → 数值」，形态由各块 builder 决定。"""
    s = tok['size']
    sh = tok['shape']
    sp = tok['spacer']
    ladder = tok['ladder']
    m = {'W': W, 'H': H, 'tok': tok, 'spacer': sp}
    for kk, vv in sp.items():
        m[kk] = vv                                          # spacer / spacer1 / spacer2 / spacer3
    m['compact'] = H < tok['compact_when_h_lt']
    k = H / float(tok['base_screen']['height'])

    if m['compact']:
        m['fs'] = dict(tok['compact_font'])
    else:
        m['fs'] = {n: pick(cfg['base'] * k, cfg['min'], cfg['max'], ladder)
                   for n, cfg in tok['font'].items()}
    for n in ('h1', 'h2', 'b1', 'b2'):
        m['h_' + n] = r4(m['fs'][n] * s['text_h_of_fs'])

    m['pad_l'] = sp[s['pad_l_compact']] if m['compact'] else sp[s['pad_l_wide']]
    m['pad_r'] = m['pad_l']
    m['margin'] = sp[s['card_inset']]
    m['group_gap'] = sp[s['group_gap']]
    m['row_gap'] = s['row_gap_px']
    m['content_w'] = W - 2 * m['margin']                        # 内容区宽（≈ 卡容器宽）
    m['radius'] = max(sh['container_radius_min'],
                      min(sh['container_radius_px'], int(round(0))))
    # 容器圆角：min(TDesign radius-default, 行高×0.18) 且 ≥ 4（行高依赖下面，故延后）
    m['line_w'] = sh['line_px']
    m['chev_w'] = max(s['chev_w_min'], r4(W * s['chev_w_of_w']))
    m['chev_h'] = max(s['chev_h_min'], r4(H * s['chev_h_of_h']))
    # 文本×右端控件间隙：**按屏高比例 + 上下限**（token 只给基准，避免小屏上绝对像素显得过大）
    m['text_chev_gap'] = max(s['text_chev_gap_min'],
                             min(s['text_chev_gap_max'], r4(H * s['text_chev_gap_of_h'])))
    m['text_vpad'] = s['text_vpad']

    # 行高：屏高比例 与 文本可读性 取大（SPEC-CHECK §3 B4「可读性优先」）
    text_need = (m['h_b1'] + m['h_b2'] + 8) if not m['compact'] else (m['h_b1'] + 8)
    m['two_line'] = (not m['compact']) and text_need <= r4(H * 0.14)
    if not m['two_line']:
        text_need = m['h_b1'] + 8
    ratio = s['row_h_of_h_compact'] if m['compact'] else s['row_h_of_h']
    m['row_h'] = max(r4(H * ratio), r4(text_need))
    m['radius'] = max(sh['container_radius_min'],
                      min(sh['container_radius_px'],
                          int(round(m['row_h'] * sh['container_radius_of_row_h']))))
    m['line_w'] = sh['line_px_thick_below_row_h'] and \
        (2 if m['row_h'] < sh['line_px_thick_below_row_h'] else sh['line_px'])
    m['icon_bg'] = r4(m['row_h'] * s['icon_bg_of_row_h'])
    m['icon'] = max(s['icon_min'], r4(m['row_h'] * s['icon_of_row_h']))
    m['icon_left'] = int(round(m['pad_l'] * s['icon_pad_of_pad_l']))
    # line_w：容器描边的可选路径（§8「描边降级为可选」；当前所有底图都素面，仅登记规则）

    # 顶栏 / 底栏
    m['bar_top'] = max(r4(H * s['bar_top_of_h']),
                       m['h_h1'] + (m['h_b2'] + 4 if not m['compact'] else 0) + s['bar_min_pad'])
    m['bar_bot'] = max(r4(H * s['bar_bot_of_h']), r4(H * 0.07) + 2 * 12)
    m['btn_h'] = min(m['bar_bot'] - 2 * 12, r4(H * 0.07))
    m['btn_w'] = max(64, r4(W * 0.16))
    m['viewport'] = H - m['bar_top'] - m['bar_bot']
    m['drag_max'] = max(tok['scroll']['drag_max_dis_min'],
                        r4(W * tok['scroll']['drag_max_dis_of_w']))
    return m


# ─────────────────────────── 控件节点 ───────────────────────────


class Node(object):
    """一个控件节点：type + caption + position + 类型化 payload + 子节点。"""

    def __init__(self, type_, caption, pos, payload=None, children=None):
        self.type = type_
        self.caption = caption
        self.pos = pos
        self.payload = payload or {}
        self.children = children if children is not None else []

    def shift(self, dy):
        """整棵子树纵向平移（就地）。"""
        self.pos['top'] += dy
        for c in self.children:
            c.shift(dy)

    def to_ctrl(self, key, n):
        """字段全集显式化（json-field-mandatory.md v2.1）：本类型必写键一个不缺。"""
        t = self.type
        c = {}
        if t == 'textview':
            c = {'id': 50000 + n, 'caption': self.caption, 'position': dict(self.pos),
                 'alignment': 0, 'colorTab': {'color0': 16777215, 'color1': -1, 'color2': -1,
                                              'color3': -1, 'color4': -1},
                 'fontSize': 16, 'touchable': False}
            c.update({'backgroundColor': -1, 'bgColorTab': {'color0': -1, 'color1': -1,
                                                           'color2': -1, 'color3': -1,
                                                           'color4': -1},
                      'bold': False, 'italic': False, 'fontFamily': 0, 'text': '',
                      'visible': True, 'rollEnable': False, 'rollDirection': 1,
                      'rollIntervalTime': 150, 'rollStep': 5})
            if 'textPosition' in self.payload:
                c['textPosition'] = self.payload.pop('textPosition')
            elif self.payload.get('backgroundPic'):
                # 纯色/纯图装饰件：文本盒 == 控件盒（与 IDE 全量序列化一致）
                c['textPosition'] = dict(self.pos)
        elif t == 'button':
            c = {'id': 20000 + n, 'caption': self.caption, 'position': dict(self.pos),
                 'alignment': 37, 'colorTab': {'color0': 16777215, 'color1': 16777215,
                                              'color2': -1, 'color3': -1, 'color4': -1},
                 'picTab': {}, 'text': '', 'touchable': True}
            c.update({'backgroundColor': -1, 'bgColorTab': {'color0': -1, 'color1': -1,
                                                           'color2': -1, 'color3': -1,
                                                           'color4': -1},
                      'bold': False, 'italic': False, 'fontFamily': 0, 'fontSize': 16,
                      'visible': True, 'longClickIntervalTime': -1, 'longClickTimeOut': -1,
                      'rollEnable': False, 'rollDirection': 1, 'rollIntervalTime': 150,
                      'rollStep': 5})
            if self.payload.get('backgroundPic') or self.payload.get('picTab'):
                c['iconPosition'] = dict(self.pos)
                c['textPosition'] = dict(self.pos)
        elif t == 'window':
            c = {'id': 110000 + n, 'caption': self.caption, 'position': dict(self.pos),
                 'backgroundColor': -1, 'hideTimeOut': -1, 'modal': False,
                 'touchable': False, 'visible': True}
        elif t == 'scrollwindow':
            c = {'id': 120000 + n, 'caption': self.caption, 'position': dict(self.pos),
                 'dragMaxDis': 200, 'orientation': 1, 'edgeEffect': 1, 'touchable': True}
        elif t == 'separator':                                  # 内部用它，序列化时变 textview
            raise AssertionError('separator 不应直接序列化')
        c.update(self.payload)
        self.payload = {}
        return c


def serialize(nodes):
    """按定义顺序连续编号（textview__1..N / button__1..N / window__1..N / scrollwindow__1..N）。"""
    counts = defaultdict(int)
    out = {}

    def one(n):
        counts[n.type] += 1
        key = '%s__%d' % (n.type, counts[n.type])
        ctrl = n.to_ctrl(key, counts[n.type])
        for ch in n.children:
            ck, cc = one(ch)
            ctrl[ck] = cc
        return key, ctrl

    for n in nodes:
        k, c = one(n)
        out[k] = c
    return out


# ─────────────────────────── 组装器 ───────────────────────────


class Composer(object):
    def __init__(self, spec, page_name):
        self.spec = spec
        self.page = spec.get('page') or {}
        self.page_name = page_name
        self.tok = self._load(os.path.join(BLOCKS_DIR, '_tokens.json'))
        res = spec.get('resolution') or {}
        self.W, self.H = int(res['width']), int(res['height'])
        self.m = build_metrics(self.W, self.H, self.tok)
        self.blocks = self._load_blocks()
        self._seq = 0             # 全页全局块序号（caption 唯一性来源；跨卡不重置）
        self.assets = {}          # 文件名 → ('shape'|'glyph', 参数)
        self.notes = []           # 自检提示（不进 json）
        self.root = []            # 根层节点（定义顺序 = z 顺序）
        self.content = []         # 页面中部内容（可能被 scrollwindow 包起来）
        self.y = 0                # 内容当前纵向位置（内容空间，y 从 0 起）
        self.origin = (0, 0)      # 当前容器原点（内容空间）→ 子控件坐标 = 绝对 − origin
        self.title_done = False

    # ---- 载入 ----
    @staticmethod
    def _load(p):
        with open(p, encoding='utf-8') as f:
            return json.load(f)

    def _load_blocks(self):
        out = {}
        for fn in sorted(os.listdir(BLOCKS_DIR)):
            if fn.endswith('.json') and not fn.startswith('_'):
                b = self._load(os.path.join(BLOCKS_DIR, fn))
                out[b['type']] = b
        return out

    # ---- 出图登记（去重；实际出图在 emit_assets）----
    def shape(self, name, w, h, radius, fill, border=None, border_w=1):
        self.assets[name] = ('shape', dict(w=int(w), h=int(h), radius=int(radius),
                                           fill=fill, border=border, border_w=border_w))
        return 'images/' + name

    def glyph(self, name, g, size, color, canvas=None):
        self.assets[name] = ('glyph', dict(g=g, size=int(size), color=color, canvas=canvas))
        return 'images/' + name

    def chevron(self, name, w, h, color):
        """箭头（行尾 Chevron）：按 SPEC-CHECK §7 的箭头专属口径画。

        为什么不直接用 gen_res.glyph_icon('forward')：iconfont 描边比例是「盒宽 2/24 ≈ 8%」
        → 在 12px 盒上退化成 1px 硬斜边（aa_audit 报 hard_diag）；§7 定的箭头规则是
        「45° + 圆头 + 笔画 ≈ 盒宽 12% 且 ≥2px」，小盒才立得住。这里按该口径实现。
        """
        self.assets[name] = ('chevron', dict(w=int(w), h=int(h), color=color))
        return 'images/' + name

    def emit_assets(self, project_root):
        """交给 ui_tools/gen_res.py 出图（抗锯齿/倒角/透明底口径由它统一负责）。"""
        out = os.path.join(project_root, 'resources', 'images')
        os.makedirs(out, exist_ok=True)
        made = []
        for name, (kind, prm) in sorted(self.assets.items()):
            if kind == 'shape':
                if prm['border']:
                    img = gen_res.rounded_rect_ss(prm['w'], prm['h'], prm['radius'],
                                                  prm['fill'], prm['border'],
                                                  prm['border_w'], ss=8)
                else:
                    img = gen_res.rounded_rect_ss(prm['w'], prm['h'], prm['radius'],
                                                  prm['fill'], ss=8)
                gen_res.save(img, out, name)
            elif kind == 'chevron':
                gen_res.save(chevron_image(prm['w'], prm['h'], prm['color']), out, name)
            else:
                gen_res.glyph_icon(out, name, prm['g'], size=prm['size'],
                                   color=prm['color'], canvas=prm['canvas'])
            made.append(name)
        return made

    # ---- 命名（caption 唯一性：全页全局序号 + 块类型前缀）----
    def next_seq(self):
        """全页全局块序号（跨卡不重置）——caption 唯一性的唯一来源。"""
        self._seq += 1
        return self._seq

    def name_block(self, blk):
        """给一个块分配 _seq / _name（行族与页面级块同一口径；显式 name 优先）。"""
        blk['_seq'] = self.next_seq()
        blk['_name'] = blk.get('name') or \
            (BLOCK_PREFIX.get(blk.get('type'), 'Block') + str(blk['_seq']))
        return blk

    def name_tree(self, blocks):
        """按「页顺序」给块树命名：卡 → 卡内行（行接着本卡的序号往下数，不再按卡内下标重数）。"""
        for b in blocks or []:
            self.name_block(b)
            if b.get('type') == 'card':
                self.name_tree(b.get('blocks'))

    # ---- 坐标换算 ----
    def xy(self, x, y):
        """内容空间绝对坐标 → 当前父容器坐标。"""
        return {'left': int(round(x - self.origin[0])), 'top': int(round(y - self.origin[1]))}

    def box(self, x, y, w, h):
        p = self.xy(x, y)
        p.update({'width': int(round(w)), 'height': int(round(h))})
        return {'left': p['left'], 'top': p['top'], 'width': p['width'], 'height': p['height']}

    def collect_controls(self, nodes, out=None):
        """把整棵树的控件（含嵌套）拉平，供自检。"""
        out = [] if out is None else out
        for n in nodes:
            out.append(n)
            self.collect_controls(n.children, out)
        return out

    # ---- 文本控件工厂 ----
    def text(self, caption, pos, fs, color, txt='', bg=None, align=36, bold=False,
             touchable=False):
        if bg:
            bg = 'images/' + bg if not bg.startswith('images/') else bg
        n = Node('textview', caption, pos,
                 {'fontSize': fs, 'text': txt, 'alignment': align,
                  'colorTab': {'color0': color, 'color1': -1, 'color2': -1, 'color3': -1,
                               'color4': -1},
                  'touchable': bool(touchable), 'bold': bool(bold)})
        if bg:
            n.payload['backgroundPic'] = bg
        return n

    def button(self, caption, pos, bg=None, fs=None, color=None, align=37, txt='',
               touchable=True):
        n = Node('button', caption, pos, {'alignment': align, 'touchable': bool(touchable)})
        if bg:
            n.payload['backgroundPic'] = bg if bg.startswith('images/') else 'images/' + bg
        if fs:
            n.payload['fontSize'] = fs
        if color is not None:
            n.payload['colorTab'] = {'color0': color, 'color1': color, 'color2': -1,
                                     'color3': -1, 'color4': -1}
        if txt:
            n.payload['text'] = txt
        return n

    def sep_node(self, x, y, w, seq):
        """1px 分割线（轴线，直线不需要 AA）→ 出图 + textview 装饰件。

        caption = RowSep<上一行块的全局序号>。旧实现用「当前控件数 + 1」计数 → 跨卡重数，
        修前示例里 RowSep1 重复 5 次（5 张卡内分割线全叫 RowSep1）。
        """
        m = self.m
        name = 'sep_%dx%d.png' % (w, 1)
        p = self.shape(name, w, 1, 0, rgba(self.tok['color']['line']))
        return self.text('RowSep%d' % seq,
                         self.box(x, y, w, 1), m['fs']['b2'], hex2int(self.tok['color']['line']),
                         '', bg=p, align=37, touchable=False)

    def check_text_fit(self, caption, txt, fs, box_w, box_h, where):
        """#13 口径自检：文本盒必须装得下（装不下 → 记 note，提示换短文案/降字号）。"""
        mw, mh = text_min_size(txt, fs, 0)
        if mw > box_w or mh > box_h:
            self.notes.append('%s(%s) 文本「%s」需 ≥%dx%d，盒 %dx%d → 文案过长，'
                              '请用 value_short 或缩短文案（%s）'
                              % (caption, where, txt[:12], mw, mh, box_w, box_h, self.page_name))
            return False
        return True

    # ─────── 块 builder：行族（setting_row / icon_row / toggle_row / device_card）───────
    ROW_TYPES = ('setting_row', 'icon_row', 'toggle_row', 'device_card')

    def plan_row_reserve(self, rows):
        """一行族口径（同页全局，越卡也一致）：右端预留宽 + 是否给图标列留位。

        为什么按「页」而不是按「卡」：check_all #27 按容器递归取族，跨卡的同行会互相比；
        且 §2.1 要求“同一页里重复出现的行，其一切口径只能照抄”。所以全页取同一组值。
        """
        m = self.m
        reserve = 0
        for b in rows:
            if b['type'] == 'toggle_row':
                reserve = max(reserve, r4(m['row_h'] * 1.30))
            elif b.get('chevron', True):
                reserve = max(reserve, m['chev_w'])
        return reserve

    def scan_row_family(self):
        """全页行族扫描：右端预留、图标列、图标盒（供所有行共用同一文本左缘）。"""
        m = self.m
        rows = []

        def walk(blocks):
            for b in blocks or []:
                if b.get('type') == 'card':
                    walk(b.get('blocks'))
                elif b.get('type') in self.ROW_TYPES:
                    rows.append(b)
        walk(self.page.get('blocks'))
        self.fam_reserve = self.plan_row_reserve(rows)
        self.fam_icon = any(b.get('icon') for b in rows) and not m['compact']

    def build_row(self, blk, parent, x0, y0, w, reserve, has_icon):
        """一行 = 透明 button（命中区，touchable true）+ 装饰件（touchable false 显式写）。"""
        m = self.m
        col = {k: hex2int(v) for k, v in self.tok['color'].items() if v.startswith('#')}
        btype = blk['type']
        # 行族 caption 一律 = <角色><块名>；块名已含「类型前缀 + 全页全局序号」（见 BLOCK_PREFIX）
        row = []
        # 1) 命中区（整行透明按钮）—— value_row 类纯显示不交互
        interactive = btype != 'value_row'
        # z 顺序口径：装饰件先定义（z 低），整行命中按钮**最后**定义（z 最高）
        # → check_all #15「装饰件压住交互控件」不会误报（按钮在上，不会被装饰件挡住）
        # 2) 图标底 + 图标
        glyph = blk.get('icon') or ''
        if has_icon and glyph:
            s = m['icon_bg']
            ix = x0 + m['icon_left']
            iy = y0 + (m['row_h'] - s) // 2
            p_bg = self.shape('icbg_%d.png' % s, s, s, s // 2, rgba(self.tok['color']['brand1']))
            row.append(self.text('ImageRow%sIconBg' % blk['_name'], self.box(ix, iy, s, s),
                                 m['fs']['b2'], col['brand1'], '', bg=p_bg, align=37))
            ic = m['icon']
            p_ic = self.glyph('ic_%s_%d.png' % (glyph, ic), glyph, ic, rgba(self.tok['color']['brand']),
                              canvas=(ic, ic))
            row.append(self.text('ImageRow%sIcon' % blk['_name'],
                                 self.box(ix + (s - ic) // 2, iy + (s - ic) // 2, ic, ic),
                                 m['fs']['b2'], col['brand'], '', bg=p_ic, align=37))
        # 文本区（全页统一口径：只要页内有任一行带图标，**所有行**都给图标列留位）
        text_left = x0 + (m['icon_left'] + m['icon_bg'] + m['spacer']
                          if getattr(self, 'fam_icon', False) else m['pad_l'])
        # 右端控件左缘 = 本行**实际**有的那个（箭头 / 开关；两者都有取更靠左者）
        rt_edge = None
        if reserve and btype != 'toggle_row' and blk.get('chevron', True):
            rt_edge = x0 + w - m['pad_r'] - m['chev_w']
        if btype == 'toggle_row':
            sw_left = x0 + w - m['pad_r'] - r4(m['row_h'] * 1.30)
            rt_edge = sw_left if rt_edge is None else min(rt_edge, sw_left)
        # 值文本右缘 = 本行右端控件左缘 − 间隙（旧实现用「全页最宽预留」→ 只有箭头的行多留死区）
        right_edge = (rt_edge - m['text_chev_gap']) if rt_edge is not None \
            else (x0 + w - m['pad_r'])
        text_w = right_edge - text_left
        self.note_row_gaps('TextRow%s' % blk['_name'], right_edge, rt_edge)
        label = blk.get('label') or blk.get('text') or ''
        value = blk.get('value') or ''
        if m['compact'] and blk.get('value_short'):
            value = blk['value_short']
        if m['two_line']:
            row.append(self.text('TextRow%sLabel' % blk['_name'],
                                 self.box(text_left, y0 + m['text_vpad'], text_w, m['h_b1']),
                                 m['fs']['b1'], col['fg1'], label))
            self.check_text_fit('TextRow%sLabel' % blk['_name'], label, m['fs']['b1'],
                                text_w, m['h_b1'], 'label')
            if value:
                row.append(self.text('TextRow%sValue' % blk['_name'],
                                     self.box(text_left, y0 + m['text_vpad'] + m['h_b1'],
                                              text_w, m['h_b2']),
                                     m['fs']['b2'], col['fg2'], value))
                self.check_text_fit('TextRow%sValue' % blk['_name'], value, m['fs']['b2'],
                                    text_w, m['h_b2'], 'value')
        else:                                                   # 极小屏单行式（整页一致）
            lw = r4(text_w * 0.42) - m['spacer']
            ty = y0 + (m['row_h'] - m['h_b1']) // 2
            row.append(self.text('TextRow%sLabel' % blk['_name'], self.box(text_left, ty, lw, m['h_b1']),
                                 m['fs']['b1'], col['fg1'], label))
            self.check_text_fit('TextRow%sLabel' % blk['_name'], label, m['fs']['b1'],
                                lw, m['h_b1'], 'label')
            if value:
                row.append(self.text('TextRow%sValue' % blk['_name'],
                                     self.box(text_left + lw + m['spacer'], ty,
                                              text_w - lw - m['spacer'], m['h_b1']),
                                     m['fs']['b2'], col['fg2'], value, align=38))
                self.check_text_fit('TextRow%sValue' % blk['_name'], value, m['fs']['b2'],
                                    text_w - lw - m['spacer'], m['h_b1'], 'value')
        # 4) 右端：箭头 / 开关
        if reserve and btype != 'toggle_row' and blk.get('chevron', True):
            rx = x0 + w - m['pad_r'] - m['chev_w']
            ry = y0 + (m['row_h'] - m['chev_h']) // 2
            p = self.chevron('chev_%dx%d.png' % (m['chev_w'], m['chev_h']),
                             m['chev_w'], m['chev_h'], rgba(self.tok['color']['chevron']))
            row.append(self.text('ImageRow%sChevron' % blk['_name'],
                                 self.box(rx, ry, m['chev_w'], m['chev_h']),
                                 m['fs']['b2'], col['chevron'], '', bg=p, align=37))
        if btype == 'toggle_row':
            on = bool(blk.get('on', True))
            sw = r4(m['row_h'] * 1.30)
            sh_ = r4(m['row_h'] * 0.72)
            sx = x0 + w - m['pad_r'] - sw
            sy = y0 + (m['row_h'] - sh_) // 2
            c_sw = self.tok['color']['brand'] if on else self.tok['color']['switchOff']
            p1 = self.shape('sw_%dx%d_%s.png' % (sw, sh_, 'on' if on else 'off'),
                            sw, sh_, sh_ // 2, rgba(c_sw))
            row.append(self.text('ToggleRow%sTrack' % blk['_name'], self.box(sx, sy, sw, sh_),
                                 m['fs']['b2'], hex2int(c_sw), '', bg=p1, align=37))
            k = sh_ - 4
            kx = sx + (sw - k - 2) if on else sx + 2
            p2 = self.shape('swk_%d.png' % k, k, k, k // 2, rgba(self.tok['color']['surface']))
            row.append(self.text('ToggleRow%sKnob' % blk['_name'],
                                 self.box(kx, sy + 2, k, k), m['fs']['b2'],
                                 hex2int(self.tok['color']['surface']), '', bg=p2, align=37))
        if btype == 'device_card':
            # 状态点（装饰件）：贴值盒左缘前，极小块跳过
            d = max(4, int(round(m['icon'] * 0.28)))
            if not m['compact']:
                p = self.shape('dot_%d.png' % d, d, d, d // 2,
                               rgba(self.tok['color']['brand'] if blk.get('online', True)
                                    else self.tok['color']['switchOff']))
                row.append(self.text('DeviceRow%sDot' % blk['_name'],
                                     self.box(text_left - m['spacer'] - d,
                                              y0 + m['row_h'] - m['text_vpad'] - m['h_b2']
                                              + (m['h_b2'] - d) // 2, d, d),
                                     m['fs']['b2'], col['brand'], '', bg=p, align=37))
        if interactive:
            row.append(self.button('ButtonRow' + blk['_name'], self.box(x0, y0, w, m['row_h'])))
        parent.extend(row)
        return m['row_h']

    def note_row_gaps(self, caption, right_edge, rt_edge):
        """记录每行「值文本右缘 → 本行右端控件左缘」的实际间隙，供同页一致性自检。"""
        if rt_edge is None:
            return
        gaps = getattr(self, '_row_gaps', None)
        if gaps is None:
            gaps = self._row_gaps = []
        gaps.append((caption, rt_edge - right_edge))

    def assert_row_gaps(self):
        """同页行族：上述间隙必须一致（防「有的行贴箭头、有的行留死区」）。"""
        vals = sorted({g for _c, g in getattr(self, '_row_gaps', [])})
        if len(vals) > 1:
            raise SystemExit('[X] 行族「值→右端控件」间隙不一致：%s'
                             % '；'.join('%s=%d' % (c, g) for c, g in self._row_gaps))

    def assert_children_fit(self, win, cw, ch_, where):
        """自检：容器子节点盒必须落在容器盒内（子节点坐标是**相对父容器**的）。

        为什么加（2026-10-01 实测缺陷）：卡底图节点误用「卡的绝对 x/y」当子节点坐标 →
        父子双计 → 白框底色整体右下各偏一个 margin、右侧溢出屏外（症状=「白框底色与文本列表区错位」）。
        同类事故在 SmartPanel 也出现过（卡片底图/装饰件用绝对坐标）。
        """
        bad = []
        for c in getattr(win, 'children', []) or []:
            p = c.pos or {}
            l, tp, w, h = p.get('left'), p.get('top'), p.get('width'), p.get('height')
            if None in (l, tp, w, h):
                continue
            if l < 0 or tp < 0 or l + w > cw or tp + h > ch_:
                bad.append('%s(%s) %d,%d %dx%d 超出容器 %dx%d'
                           % (c.caption, c.type, l, tp, w, h, cw, ch_))
        if bad:
            raise SystemExit('[X] %s 子节点越界（子节点坐标应为相对父容器）：%s' % (where, '；'.join(bad)))

    def build_card(self, blk, parent, x, y):
        """卡片 = window__N 容器（touchable false）+ 卡底装饰 + 行 + 行间分割线。"""
        m = self.m
        rows = blk.get('blocks') or []
        if blk.get('title'):
            y = self.build_section({'text': blk['title'], '_seq': blk['_seq']}, parent, x, y)
        n = len(rows)
        cw, ch_ = m['content_w'], n * m['row_h']
        win = Node('window', 'Card%d' % blk['_seq'], self.box(x, y, cw, ch_))
        bg = self.shape('card_%dx%d.png' % (cw, ch_), cw, ch_, m['radius'],
                        rgba(self.tok['color']['surface']))
        win.children.append(self.text('CardBg%d' % blk['_seq'], self.box(0, 0, cw, ch_),
                                      m['fs']['b2'], hex2int(self.tok['color']['surface']),
                                      '', bg=bg, align=37))

        reserve = self.fam_reserve
        old_origin = self.origin
        self.origin = (0, 0)                                    # 卡内子控件用「卡局部坐标」
        row_nodes, sep_nodes = [], []
        top = 0
        for i, b in enumerate(rows):
            # 行名/序号已在 name_tree 预分配（全页全局递增，跨卡不重置）→ 此处不再按卡内下标重数
            has_icon = self.fam_icon and bool(b.get('icon')) and \
                (not m['compact'] or b['type'] != 'icon_row')
            self.build_row(b, row_nodes, 0, top, cw, reserve, has_icon)
            top += m['row_h']
            if i < n - 1:
                sep_nodes.append(self.sep_node(m['pad_l'], top, cw - 2 * m['pad_l'], b['_seq']))
        self.origin = old_origin
        # z 顺序：卡底 → 分割线（纯装饰，先铺）→ 行（装饰件 + 整行命中按钮放最后）→ 无装饰件压住按钮
        win.children.extend(sep_nodes)
        win.children.extend(row_nodes)
        self.assert_children_fit(win, cw, ch_, 'Card%s' % blk['_seq'])
        parent.append(win)
        return y + ch_

    def build_section(self, blk, parent, x, y):
        """分组小标题带（card.title 也复用它 → 同页口径一致）。间距由调用方（run）加。"""
        m = self.m
        txt = blk.get('text') or ''
        p = self.box(x, y, m['content_w'], m['h_h2'])
        parent.append(self.text('SectionHeader%d' % blk['_seq'], p,
                                m['fs']['h2'], hex2int(self.tok['color']['fg2']), txt, bold=True))
        return y + max(self.tok['spacer']['spacer3'], m['h_h2'])

    def build_title(self, blk, parent, x, y):
        m = self.m
        col = {k: hex2int(v) for k, v in self.tok['color'].items() if v.startswith('#')}
        p = self.box(x, (m['bar_top'] - m['h_h1'] - (m['h_b2'] + 4 if blk.get('subtitle') else 0)) // 2,
                     self.W - 2 * m['margin'], m['h_h1'])
        parent.append(self.text('TextTitle', p, m['fs']['h1'], col['fg1'],
                                blk.get('title') or '', bold=True))
        if blk.get('subtitle') and not m['compact']:
            parent.append(self.text('TextSubtitle', self.box(x, p['top'] + m['h_h1'] + 4,
                                                             self.W - 2 * m['margin'], m['h_b2']),
                                    m['fs']['b2'], col['fg2'], blk['subtitle']))
        return m['bar_top']

    def build_empty(self, blk, parent, x, y):
        m = self.m
        col = {k: hex2int(v) for k, v in self.tok['color'].items() if v.startswith('#')}
        s_ = blk['_seq']                                  # 空态块序号（多空态同页也不重名）
        band = r4(self.H * 0.30)
        s = r4(m['icon_bg'] * 2)
        cx = x + (m['content_w'] - s) // 2
        top = y + (band - s) // 2 - m['h_b1']
        p_bg = self.shape('icbg_%d.png' % s, s, s, s // 2, rgba(self.tok['color']['brand1']))
        parent.append(self.text('EmptyStateBg%d' % s_, self.box(cx, top, s, s), m['fs']['b2'],
                                col['brand1'], '', bg=p_bg, align=37))
        ic = s // 2
        p_ic = self.glyph('ic_%s_%d.png' % (blk.get('icon') or 'info', ic),
                          blk.get('icon') or 'info', ic, rgba(self.tok['color']['brand']),
                          canvas=(ic, ic))
        parent.append(self.text('EmptyStateIcon%d' % s_, self.box(cx + (s - ic) // 2,
                                                                  top + (s - ic) // 2, ic, ic),
                                m['fs']['b2'], col['brand'], '', bg=p_ic, align=37))
        tw = r4(m['content_w'] * 0.8)
        tx = x + (m['content_w'] - tw) // 2
        ty = top + s + m['spacer2']
        parent.append(self.text('EmptyStateText%d' % s_, self.box(tx, ty, tw, m['h_b1']),
                                m['fs']['b1'], col['fg2'], blk.get('text') or '', align=37))
        self.check_text_fit('EmptyStateText%d' % s_, blk.get('text') or '', m['fs']['b1'],
                            tw, m['h_b1'], 'empty')
        if blk.get('sub'):
            parent.append(self.text('EmptyStateSub%d' % s_,
                                    self.box(tx, ty + m['h_b1'] + 4, tw, m['h_b2']),
                                    m['fs']['b2'], col['fg2'], blk['sub'], align=37))
        return y + band

    def build_actions(self, blk, parent, x, y):
        """底部操作条（固定件，永远放 scrollwindow 外面）。"""
        m = self.m
        col = {k: hex2int(v) for k, v in self.tok['color'].items() if v.startswith('#')}
        sq = blk['_seq']                                     # 底栏块序号（多个底栏同页也不重名）
        bar_y = self.H - m['bar_bot']
        bg = self.shape('footbg_%dx%d.png' % (self.W, m['bar_bot']), self.W, m['bar_bot'], 0,
                        rgba(self.tok['color']['surface']))
        parent.append(self.text('FooterBg%d' % sq, self.box(0, bar_y, self.W, m['bar_bot']),
                                m['fs']['b2'], col['surface'], '', bg=bg, align=37))
        bw, bh = m['btn_w'], m['btn_h']
        by = bar_y + (m['bar_bot'] - bh) // 2
        px_primary = self.W - m['margin'] - bw            # 主按钮永远贴右缘
        if blk.get('secondary'):
            # 次按钮 = TDesign「light」变体（浅底实心）：白色底上白按钮看不见，
            # 而描边环会让 AA 审计的弧线过渡退回硬阶梯（§7.1 实测）→ 用浅品牌底代替描边
            sbg = self.shape('btn_secondary_%dx%d.png' % (bw, bh), bw, bh, m['radius'] // 2 + 2,
                             rgba(self.tok['color']['brand1']))
            parent.append(self.button('ButtonSecondary%d' % sq,
                                      self.box(px_primary - m['spacer'] - bw, by, bw, bh),
                                      bg=sbg, fs=m['fs']['b2'], color=col['brand'],
                                      align=37, txt=blk['secondary']))
        pbg = self.shape('btn_primary_%dx%d.png' % (bw, bh), bw, bh, m['radius'] // 2 + 2,
                         rgba(self.tok['color']['brand']))
        parent.append(self.button('ButtonPrimary%d' % sq, self.box(px_primary, by, bw, bh),
                                  bg=pbg, fs=m['fs']['b2'], color=col['onBrand'], align=37,
                                  txt=blk.get('primary') or '确定'))
        if blk.get('status'):
            sw = r4(m['content_w'] * 0.40)
            parent.append(self.text('ActionStatus%d' % sq,
                                    self.box(m['margin'], by + (bh - m['h_b2']) // 2,
                                             sw, m['h_b2']),
                                    m['fs']['b2'], col['fg2'], blk['status']))
            self.check_text_fit('ActionStatus%d' % sq, blk['status'], m['fs']['b2'], sw,
                                m['h_b2'], 'footer')
        return self.H

    def build_dialog(self, blk, parent):
        """弹窗：根层整屏 window（modal + visible:false）+ 遮罩 + 面板。"""
        m = self.m
        col = {k: hex2int(v) for k, v in self.tok['color'].items() if v.startswith('#')}
        q = blk['_seq']                                       # 弹窗块序号（多弹窗同页也不重名）
        win = Node('window', 'DialogWindow%d' % q, {'left': 0, 'top': 0, 'width': self.W,
                                                    'height': self.H},
                   {'modal': True, 'visible': bool(blk.get('visible', False)),
                    'touchable': False})
        scrim = self.shape('cc_scrim_%dx%d.png' % (self.W, self.H), self.W, self.H, 0,
                           rgba(self.tok['color']['scrim'], 0x66))
        win.children.append(self.text('DialogScrim%d' % q, self.box(0, 0, self.W, self.H),
                                      m['fs']['b2'], hex2int(self.tok['color']['surface']),
                                      '', bg=scrim, align=37, touchable=False))
        pw = max(200, r4(self.W * (0.80 if m['compact'] else 0.60)))
        title_h, body_h = m['h_h2'], m['h_b1']
        lines = 1 if m['compact'] else 2
        ph = (2 * m['spacer2'] + title_h + m['spacer'] + body_h * lines + m['spacer2'] + m['btn_h'])
        px_ = (self.W - pw) // 2
        py_ = (self.H - ph) // 2
        panel = Node('window', 'DialogPanel%d' % q, {'left': px_, 'top': py_, 'width': pw,
                                                     'height': ph})
        pbg = self.shape('panel_%dx%d.png' % (pw, ph), pw, ph, m['radius'],
                         rgba(self.tok['color']['surface']))
        panel.children.append(self.text('DialogPanelBg%d' % q,
                                        {'left': 0, 'top': 0, 'width': pw, 'height': ph},
                                        m['fs']['b2'], col['surface'], '', bg=pbg, align=37))
        panel.children.append(self.text('DialogTitle%d' % q,
                                        {'left': m['spacer2'], 'top': m['spacer2'],
                                         'width': pw - 2 * m['spacer2'], 'height': title_h},
                                        m['fs']['h2'], col['fg1'], blk.get('title') or '', bold=True))
        panel.children.append(self.text('DialogBody%d' % q,
                                        {'left': m['spacer2'],
                                         'top': m['spacer2'] + title_h + m['spacer'],
                                         'width': pw - 2 * m['spacer2'],
                                         'height': body_h * lines},
                                        m['fs']['b1'], col['fg2'], blk.get('body') or ''))
        bw = (pw - 3 * m['spacer2']) // 2
        bh, by = m['btn_h'], ph - m['spacer2'] - m['btn_h']
        sbg = self.shape('btn_secondary_%dx%d.png' % (bw, bh), bw, bh, m['radius'] // 2 + 2,
                         rgba(self.tok['color']['brand1']))
        panel.children.append(self.button('DialogButtonSecondary%d' % q,
                                          {'left': m['spacer2'], 'top': by, 'width': bw,
                                           'height': bh}, bg=sbg, fs=m['fs']['b2'],
                                          color=col['brand'], align=37,
                                          txt=blk.get('secondary') or '取消'))
        pbg2 = self.shape('btn_primary_%dx%d.png' % (bw, bh), bw, bh, m['radius'] // 2 + 2,
                          rgba(self.tok['color']['brand']))
        panel.children.append(self.button('DialogButtonPrimary%d' % q,
                                          {'left': 2 * m['spacer2'] + bw, 'top': by,
                                           'width': bw, 'height': bh}, bg=pbg2,
                                          fs=m['fs']['b2'], color=col['onBrand'], align=37,
                                          txt=blk.get('primary') or '确定'))
        win.children.append(panel)
        parent.append(win)
        return self.H

    # ─────── 主流程 ───────
    def run(self):
        m = self.m
        self.root = []
        content, footer, dialogs = [], [], []
        seen_title = False
        self._seq = 0
        self.name_tree(self.page.get('blocks'))      # 先全页统一编号（caption 唯一性来源）
        self.scan_row_family()
        for blk in self.page.get('blocks') or []:
            t = blk.get('type')
            if t not in self.blocks:
                raise SystemExit('[X] 未知块类型：%s（可用：%s）'
                                 % (t, ', '.join(sorted(self.blocks))))
            if t == 'page_title':
                if seen_title:
                    raise SystemExit('[X] page_title 只能出现一次')
                seen_title = True
                continue                                    # 标题在下面统一摆（用 bar_top）
            if t == 'bottom_actions':
                footer.append(blk)
            elif t == 'dialog':
                dialogs.append(blk)
            elif t == 'card':
                if self.y > 0:
                    self.y += m['group_gap']
                self.y = self.build_card(blk, content, m['margin'], self.y)
            elif t == 'section_header':
                if self.y > 0:
                    self.y += m['group_gap']
                self.y = self.build_section(blk, content, m['margin'], self.y)
            elif t == 'empty_state':
                self.y = self.build_empty(blk, content, m['margin'], self.y)
            elif t in self.ROW_TYPES:
                has_icon = self.fam_icon and bool(blk.get('icon')) and not m['compact']
                self.build_row(blk, content, m['margin'], self.y, m['content_w'],
                               self.fam_reserve, has_icon)
                self.y += m['row_h']
            else:
                raise SystemExit('[X] 块 %s 没有 builder' % t)
        content_h = max(0, self.y)

        # 标题带：优先用显式 page_title 块，否则用 page.title/page.subtitle（spec 常见写法）
        title_blk = next((b for b in (self.page.get('blocks') or [])
                          if b.get('type') == 'page_title'), None)
        if title_blk is None and self.page.get('title'):
            title_blk = self.name_block({'type': 'page_title', 'title': self.page.get('title'),
                                         'subtitle': self.page.get('subtitle')})
        if not title_blk:
            raise SystemExit('[X] 缺标题：给 page.title（+ page.subtitle）或一个 page_title 块——'
                             '顶部固定带高靠它定')
        if not footer and self.page.get('footer'):
            footer = [self.name_block(dict(self.page['footer'], type='bottom_actions'))]
        if not footer:
            raise SystemExit('[X] 缺 bottom_actions（底部固定带必须有，否则视口高度没法定）')
        title_nodes = []
        self.build_title(title_blk, title_nodes, m['margin'], 0)

        # 内容放得下就直接摆；放不下才上滑动窗口（§2.1 流程第 1 步）
        if content_h > m['viewport']:
            view = Node('scrollwindow', 'Scroll' + self.page_name.title(),
                        {'left': 0, 'top': m['bar_top'], 'width': self.W,
                         'height': m['viewport']},
                        {'dragMaxDis': m['drag_max'],
                         'orientation': self.tok['scroll']['orientation'],
                         'edgeEffect': self.tok['scroll']['edge_effect'],
                         'touchable': True})
            inner = Node('window', 'Window' + self.page_name.title(),
                         {'left': 0, 'top': 0, 'width': self.W, 'height': content_h},
                         {'backgroundColor': -1, 'hideTimeOut': -1, 'modal': False,
                          'touchable': False, 'visible': True})
            inner.children = content
            view.children = [inner]
            body = [view]
            self.notes.append('内容总高 %d > 视口 %d → 自动上滑动窗口（行程 %d px，dragMaxDis=%d）'
                              % (content_h, m['viewport'], content_h - m['viewport'], m['drag_max']))
        else:
            for nd in content:
                nd.shift(m['bar_top'])
            body = content
            self.notes.append('内容总高 %d ≤ 视口 %d → 不上滑动窗口（白放一层没意义，§2.1 第 1 步）'
                              % (content_h, m['viewport']))

        for blk in footer:
            self.build_actions(blk, self.root, m['margin'], 0)
        for blk in dialogs:
            self.build_dialog(blk, self.root)
        # 顺序 = z 顺序：标题 → 内容 → 底栏 → 弹窗（弹窗永远最上层）
        self.root = title_nodes + body + self.root
        self.content_h = content_h
        self._nodes = self.root                                 # 幂等：document() 不再重跑
        self.control_count = len(self.collect_controls(self.root))
        return self.root

    def document(self):
        nodes = self._nodes if getattr(self, '_nodes', None) is not None else self.run()
        body = serialize(nodes)
        doc = {'id': 0,
               'position': {'left': 0, 'top': 0, 'width': self.W, 'height': self.H},
               'resolution': {'width': self.W, 'height': self.H},
               'backgroundColor': hex2int(self.tok['color']['page']),
               'touchable': False, 'topmost': False}
        doc.update(body)
        assert_caption_unique(doc, self.page_name)     # 自检：重名 → 报错退出（不出产物）
        self.assert_row_gaps()                          # 自检：同页行族「值→右端控件」间隙一致
        return doc


# ─────────────────────────── logic 骨架生成 ───────────────────────────

LOGIC_HEAD = '''/*
 * 本文件由 templates/ui_blocks/compose.py 生成：界面块片段库的 logic 骨架。
 * 回调命名口径：onButtonClick_控件caption（返回 false = 放行系统默认处理，true = 拦截）。
 * 编译前按项目模板补齐 include（HelloWord 模板为 #include "uart/ProtocolSender.h"）。
 * 行块的口令：整行就是一个透明 button，命中区 = 行条。
 */

/**
 * 注册定时器（id 不能重复）
 */
static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    //{0,  1000}, // 定时器 id=0，间隔 1 秒
};

/**
 * 界面构造时触发
 */
static void onUI_init() {
    // TODO: 页面初始化（控件文案复位 / 监听器注册）
}

/**
 * 切换到该界面时触发
 */
static void onUI_intent(const Intent *intentPtr) {
    if (intentPtr != NULL) {
        // TODO
    }
}

static void onUI_show() {
}

static void onUI_hide() {
}

static void onUI_quit() {
    // 页面销毁：清缓存 + 反注册监听器（见 knowledge/devflow/activity-code-skeleton.md）
}

static void onUI_Timer(int id) {
}
'''


def collect_button_caps(node, out=None):
    out = [] if out is None else out
    for k, v in node.items():
        if isinstance(v, dict) and '__' in k:
            if 20000 <= int(v.get('id', 0)) < 30000 and v.get('caption'):
                out.append(v['caption'])
            collect_button_caps(v, out)
    return out


def find_render_font(project_root):
    """渲染用字体：项目自带优先（真机同族），否则用 components/fonts 的 zkswe 字体。"""
    import glob as _glob
    for pat in (os.path.join(project_root, 'resources', 'font', '*.ttf'),
                os.path.join(project_root, 'resources', 'fonts', '*.ttf'),
                os.path.join(REPO, 'components', 'fonts', 'fonts', 'zkswe-hans-common.ttf')):
        hit = sorted(_glob.glob(pat))
        if hit:
            return hit[0]
    return None


def emit_logic(project_root, page, doc):
    """生成 <project>/src/logic/<page>Logic.cc 骨架（check_all #5/#8 靠它过）。"""
    caps = collect_button_caps(doc)
    dups = sorted({c for c in caps if caps.count(c) > 1})      # 二道闸：button caption 重名
    if dups:
        raise SystemExit('[X] button caption 重名（%s）→ onButtonClick_<caption> 会重复定义，'
                         '拒绝生成 logic 骨架' % '、'.join(dups))
    body = [LOGIC_HEAD]
    body.append('\n// ---- 按钮回调 ----\n')
    for cap in caps:
        body.append('static bool onButtonClick_%s(ZKButton *pButton) {\n'
                    '    // TODO: %s\n    return false;\n}\n' % (cap, cap))
    d = os.path.join(project_root, 'src', 'logic')
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, '%sLogic.cc' % page)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(''.join(body))
    return p


# ─────────────────────────── CLI ───────────────────────────


def main():
    ap = argparse.ArgumentParser(description='界面块片段库组装器：spec → json + 切图 (+渲染/全检)')
    ap.add_argument('spec', help='spec.json（分辨率 + page.title + page.blocks）')
    ap.add_argument('--project', required=True, help='FlyThings 项目根（产物落到 ui/ 与 resources/images/）')
    ap.add_argument('--page', default='main', help='页面名（json 文件名 / 渲染图名），默认 main')
    ap.add_argument('--render', action='store_true', help='调 ui_tools/json2img.py 出渲染图')
    ap.add_argument('--check', action='store_true', help='调 ui_tools/check_all.py 全检')
    ap.add_argument('--font', default=None,
                    help='渲染字体 TTF（缺省自动找：<工项目>/resources/font/*.ttf → '
                         'components/fonts/fonts/zkswe-hans-common.ttf）；不传时渲染器无中文字体，'
                         '中文会画成方块（只影响渲染图，json/真机不受影响）')
    ap.add_argument('--json-only', action='store_true', help='只写 json（不出图 / 不写 logic 骨架）')
    ap.add_argument('--no-logic', action='store_true', help='不生成 src/logic/<page>Logic.cc 骨架')
    ap.add_argument('--ui-layout', choices=('auto', 'flat', 'res'), default='auto',
                    help='json 落点：auto（工程已有 ui/<W>x<H>/ → res，否则 flat）/ flat（ui/x.json）/ '
                         'res（ui/<W>x<H>/x.json）。⚠️ check_all #9 的 fui pack 只认扁平单分辨率布局，'
                         '多分辨率工程用 res 时 #9 会误报（既有工具的已知限制）')
    a = ap.parse_args()

    project = os.path.abspath(a.project)
    with open(a.spec, encoding='utf-8') as f:
        spec = json.load(f)
    cmp_ = Composer(spec, a.page)
    doc = cmp_.document()

    res_dir = '%dx%d' % (cmp_.W, cmp_.H)
    ui_dir = os.path.join(project, 'ui')
    if a.ui_layout == 'auto':
        # 工程已有 ui/<W>x<H>/ → 多分辨率布局；否则按单分辨率（扁平）——与 HelloWord 模板一致
        a.ui_layout = 'res' if os.path.isdir(os.path.join(ui_dir, res_dir)) else 'flat'
    if a.ui_layout == 'res':
        ui_dir = os.path.join(ui_dir, res_dir)
    os.makedirs(ui_dir, exist_ok=True)
    json_path = os.path.join(ui_dir, a.page + '.json')
    with open(json_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(doc, ensure_ascii=False, indent=2) + '\n')

    print('== compose (%dx%d) ==' % (cmp_.W, cmp_.H))
    print('  行高 %d ｜ 字号 %s ｜ 圆角 %d ｜ 图标底/图标 %d/%d ｜ 箭头 %dx%d ｜ 内容 %d → 视口 %d'
          % (cmp_.m['row_h'], cmp_.m['fs'], cmp_.m['radius'], cmp_.m['icon_bg'],
             cmp_.m['icon'], cmp_.m['chev_w'], cmp_.m['chev_h'], cmp_.content_h,
             cmp_.m['viewport']))
    for n in cmp_.notes:
        print('  [NOTE] %s' % n)

    if not a.json_only:
        made = cmp_.emit_assets(project)
        print('  出图 %d 张 → %s' % (len(made), os.path.join(project, 'resources', 'images')))
        if not a.no_logic:
            lp = emit_logic(project, a.page, doc)
            print('  logic 骨架 → %s（%d 个按钮回调）'
                  % (lp, len(collect_button_caps(doc))))
    print('  → %s' % json_path)
    print('  控件：顶层 %d 个键 ｜ 含嵌套共 %d 个控件'
          % (len([k for k in doc if '__' in k]), cmp_.control_count))
    if cmp_.notes:
        bad = [n for n in cmp_.notes if '文案过长' in n]
        if bad:
            print('  [X] %d 处文本装不下（#13 会 FAIL）→ 缩短文案或给 value_short：' % len(bad))
            for b in bad:
                print('      - %s' % b)

    if a.render:
        png = os.path.join(ui_dir, a.page + '.render.png')
        font = a.font or find_render_font(project)
        cmd = [sys.executable, os.path.join(UI_TOOLS, 'json2img.py'), json_path,
               '--page', a.page, '--out', png, '--report']
        if font:
            cmd += ['--font', font]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        rep = (r.stdout or '').strip()
        print('-- render --')
        print(rep[-1500:])
        if r.returncode != 0:
            print('  [X] json2img exit=%d\n%s' % (r.returncode, (r.stderr or '')[-800:]))
        else:
            try:
                from PIL import Image
                im = Image.open(png)
                ok = (im.size == (cmp_.W, cmp_.H))
                print('  渲染图 %s %dx%d ｜ 尺寸 == resolution: %s' % (os.path.basename(png),
                                                                      im.size[0], im.size[1], ok))
            except Exception as e:                       # noqa: BLE001
                print('  [WARN] 渲染图读取失败：%s' % e)
    if a.check:
        print('-- check_all --')
        r = subprocess.run([sys.executable, os.path.join(UI_TOOLS, 'check_all.py'), project],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        tail = [ln for ln in (r.stdout or '').splitlines()
                if ln.startswith(('[OK]', '[X]', '[!]')) or '== 2' in ln or '== 27' in ln
                or '== 26' in ln or 'FAIL' in ln or 'WARN 需' in ln]
        print('\n'.join(tail[-25:]))
        print('  check_all exit = %d' % r.returncode)
        if r.returncode != 0:
            print((r.stdout or '')[-3000:])


if __name__ == '__main__':
    main()
