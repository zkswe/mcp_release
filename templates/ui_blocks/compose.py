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
  · **图标来源 = `components/icons` 图标资产库**（禁自绘/禁 emoji 字体兜底；按盒尺寸选档
    56/24/22，图严格 == 控件盒；库里没有该语义名才回退 gen_res 线框并**明说**）
    → 钟工 2026-10-01；实现见同目录 `iconlib.py`
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
import iconlib                                                 # noqa: E402  图标唯一来源（components/icons）

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
    # ── 第 2 批（交互类，2026-10-01）──
    'slider_row': 'SliderRow',
    'progress_row': 'ProgressRow',
    'input_row': 'InputRow',
    'checkbox_row': 'CheckboxRow',
    'radio_row': 'RadioRow',
    'list_item': 'ListItem',
    'wheel_picker': 'WheelPicker',
    # ── 第 3 批（结构 / 导航 / 提示类，2026-10-01）──
    'tabs': 'Tabs',
    'bottom_nav': 'BottomNav',
    'banner': 'Banner',
    'toast': 'Toast',
    'status_pill': 'StatusPill',
    'divider_label': 'DividerLabel',
    'grid_icons': 'GridIcons',
}

# 根层块（第 3 批）：不进卡（卡内只收行块/列表块），带高自成一带
STRUCT3_TYPES = ('tabs', 'banner', 'divider_label', 'grid_icons', 'status_pill')

# 控件 id 分区（与 tools/ui_tools/html2json.py 的 ID_BASE 同源，只有 checkbox/radiobutton 例外）
#   · checkbox 本库取 **94500** 段（html2json 旧口径是 21000）：check_all #5 按「20000 ≤ id < 30000」
#     推断「这是 button，必须有 onButtonClick_<caption>」——而 checkbox 的语义回调是 onCheckedChanged，
#     给它编一个 onButtonClick 是错的。避开该段即可两不误（真机 id 段无语义，只要求页内唯一）。
#   · radiobutton 取 94100 段（html2json 用 22000，会落进上面那段；且 radiobuttons 是数组子项，
#     #5 的 by_caption 递归不到数组元素，这里取 94100 只为口径统一 + 与 radiogroup 94000 相邻）。
#   · subitem 24000 段：同样是数组子项，与既有工程一致。
ID_BASE = {
    'textview': 50000,
    'button': 20000,
    'window': 110000,
    'scrollwindow': 120000,
    'edittext': 51000,
    'seekbar': 91000,
    'listview': 80000,
    'checkbox': 94500,
    'radiogroup': 94000,
}
SUBITEM_ID_BASE = 24000
RADIOBUTTON_ID_BASE = 94100

# 交互字段行（文本带 + 控件带 两带式；2026-10-01 第 2 批）
FIELD_TYPES = ('slider_row', 'progress_row', 'input_row', 'checkbox_row', 'radio_row')
# 列表/滚轮块（listview 组合，自带块高）
WIDGET_TYPES = ('list_item', 'wheel_picker')


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


def r4up(v):
    """4px 栅格**向上**取整（文本盒宽专用：必须 ≥ 估算宽 × 余量系数，见 check_all #36）。"""
    return max(4, int(-(-float(v) // 4)) * 4)


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


def mark_image(prm):
    """勾选/单选标记图（第 2 批交互块）：底形状（gen_res 覆盖率口径）+ 可选符号。

    为什么要一个「合成」入口：checkbox 的选中态 = 品牌实底 + 白勾，单选选中态 = 品牌实圆 + 白内点。
    底形状与符号都能用 gen_res 现成函数（bordered_cov / rounded_rect_cov / glyph_icon），
    这里只做「同一张画布上叠一次」——不是重写画形状的逻辑。
    """
    from PIL import Image
    w, h = int(prm['w']), int(prm['h'])
    if prm.get('border'):
        img = gen_res.bordered_cov(w, h, prm['radius'], prm['fill'], prm['border'],
                                   prm['border_w'], ss=8)
    else:
        img = gen_res.rounded_rect_cov(w, h, prm['radius'], prm['fill'], ss=8)
    mark = prm.get('mark') or ''
    if mark == 'check':
        # 勾选符号也走图标资产库（control.check 的 _on 实心勾）；库不可用才退回 gen_res 线框
        ms = int(prm['mark_size'])
        mc = tuple(prm['mark_color'])
        if iconlib.lookup('check'):
            g, _meta = iconlib.produce('check', ms, mc, state='on')
        else:
            import contextlib
            import io as _io
            import tempfile
            print('  [回退线框] 勾选符号 check 未走图标库（库不可用）→ gen_res 线框')
            d = tempfile.mkdtemp(prefix='uiblocks_mark_')
            with contextlib.redirect_stdout(_io.StringIO()):      # 静音 gen_res.save 的打印
                p = gen_res.glyph_icon(d, 'uc_mark_check.png', 'check', size=ms, color=mc)
            g = Image.open(p).convert('RGBA')
        img.alpha_composite(g, ((w - g.width) // 2, (h - g.height) // 2))
    elif mark == 'dot':
        d = int(prm['mark_size'])
        dot = gen_res.rounded_rect_cov(d, d, d // 2, prm['mark_color'], ss=8)
        img.alpha_composite(dot, ((w - d) // 2, (h - d) // 2))
    return img


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

    # —— 第 2 批：交互块度量（比例 / 内容反算，两版分辨率同一套公式）——
    m['thumb'] = m['icon']                                    # 滑块边长 = 图标档（≥12）
    m['seek_h'] = max(m['thumb'], r4(m['row_h'] * 0.60))      # 滑块控件盒高 ≥ thumb.size.height（否则真机滑块被压扁）
    m['edit_h'] = max(m['h_b1'] + m['spacer'], r4(m['row_h'] * 0.70))   # 输入框盒高（装得下文本）
    m['opt_h'] = m['edit_h']                                  # 单选每项高（与输入框同档）
    m['cb'] = max(m['icon'], r4(m['row_h'] * 0.50))           # 复选/单选标记盒（正方）
    m['widget_pad'] = m['spacer']                             # 控件带上下呼吸
    # list_item / wheel_picker（listview 族）
    m['li_rows'] = 4
    m['li_h'] = max(m['h_b1'] + m['spacer'], r4(m['row_h'] * 0.70))   # 列表模板行高
    m['li_peek'] = 2                                          # 行高公式除不尽的余数 = 有意的可滑动提示（#37 NOTE）
    m['wheel_rows'] = 5                                       # 可见行数（奇数：正中行 = 选中行）
    m['wheel_h'] = max(m['h_b1'] + m['spacer'], r4(m['row_h'] * 0.60))  # 滚轮模板行高
    m['wheel_col_w'] = r4(m['content_w'] * 0.20)              # 滚轮列宽

    # —— 第 3 批：结构 / 导航 / 提示类度量（比例 + 内容反算，两版分辨率同一套公式）——
    m['tab_h'] = max(r4(H * 0.09), m['h_b1'] + 2 * m['spacer'])      # 顶部分段控件带高
    m['ind_h'] = max(2, int(round(H * 0.005)))                       # 指示条高（1024→3 / 320→2）
    m['pill_h'] = max(r4(H * 0.07), m['h_b2'] + m['spacer'])         # 状态胶囊高
    m['pill_pad'] = r4(m['h_b2'] * 0.75)                             # 胶囊左右内边距
    m['banner_h'] = max(r4(H * 0.08), m['h_b1'] + 2 * m['spacer'])   # 提示条带高
    m['divider_h'] = max(r4(H * 0.05), m['h_b2'])                    # 带文字分割线带高
    # 块内图标尺寸下限（第 3 批实测）：aa_audit 对 <20px 的弧线类 glyph 判真缺陷
    # （wifi@12 / home@16 / settings@16 FAIL，bell@20 FAIL，home@20 / wifi@16 已是 WARN 边界）——
    # 图标不像字号可以降档（降了就退化成硬阶梯），所以第 3 批块内图标一律保尺寸；极小屏宁可省图标。
    m['ic_min'] = max(m['icon'], s.get('glyph_min_px', 24))
    m['nav_gap'] = m['row_gap']                                      # 底导图标×文字间距
    m['nav_ic'] = m['ic_min']                                        # 底导图标档（= 块内图标下限）
    m['nav_h'] = max(r4(H * 0.10),
                     m['nav_ic'] + m['nav_gap'] + m['h_b2'] + 2 * m['spacer'])  # 底导固定带高
    m['toast_h'] = m['h_b1'] + 2 * m['spacer2']                      # 浮层提示盒高（单行）
    m['toast_top_of_h'] = 0.60                                       # 浮层垂直位置（居中偏下）
    m['grid_ic'] = m['ic_min']                                       # 宫格图标档
    m['grid_ib'] = max(m['icon_bg'], r4(m['grid_ic'] * 1.5))         # 宫格图标底（≥ 图标 × 1.5）
    m['grid_tile_h'] = 2 * m['spacer'] + m['grid_ib'] + m['h_b2']    # 宫格格高（图标底 + 文字）
    m['grid_gap'] = m['spacer2']                                     # 宫格横向间隙（格 → 格）
    m['grid_row_gap'] = m['spacer']                                  # 宫格纵向间隙（行 → 行）

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
            c = {'id': ID_BASE['textview'] + n, 'caption': self.caption, 'position': dict(self.pos),
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
            c = {'id': ID_BASE['button'] + n, 'caption': self.caption, 'position': dict(self.pos),
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
            c = {'id': ID_BASE['window'] + n, 'caption': self.caption, 'position': dict(self.pos),
                 'backgroundColor': -1, 'hideTimeOut': -1, 'modal': False,
                 'touchable': False, 'visible': True}
        elif t == 'scrollwindow':
            c = {'id': ID_BASE['scrollwindow'] + n, 'caption': self.caption,
                 'position': dict(self.pos), 'dragMaxDis': 200, 'orientation': 1,
                 'edgeEffect': 1, 'touchable': True}
        elif t == 'edittext':
            # 字段全集 = check_all CTRL_FIELD_TEMPLATES['edittext']（id 51000 段 → #5 会核 onEditTextChanged_）
            c = {'id': ID_BASE['edittext'] + n, 'caption': self.caption, 'position': dict(self.pos),
                 'alignment': 36,
                 'bgColorTab': {'color0': 16777215, 'color1': -1, 'color2': -1, 'color3': -1,
                                'color4': -1},
                 'bold': False, 'beepEnable': True,
                 'colorTab': {'color0': 16777215, 'color1': -1, 'color2': -1, 'color3': -1,
                              'color4': -1},
                 'fontFamily': 0, 'fontSize': 16, 'hintText': '', 'hintTextColor': 8947848,
                 'isPassword': False, 'italic': False, 'passwordChar': '*', 'text': '',
                 'textType': 0, 'touchable': True, 'visible': True,
                 'rollEnable': False, 'rollDirection': 1, 'rollIntervalTime': 150, 'rollStep': 5}
        elif t == 'seekbar':
            # 字段全集 = CTRL_FIELD_TEMPLATES['seekbar']；thumb 子盒 == 图（#11/#17 铁律 #1）
            c = {'id': ID_BASE['seekbar'] + n, 'caption': self.caption, 'position': dict(self.pos),
                 'backgroundColor': -1, 'backgroundPic': '', 'defProgress': 0, 'max': 100,
                 'orientation': 0, 'progressPic': '', 'secondaryProgressPic': '',
                 'thumb': {'size': {'width': 0, 'height': 0}, 'normalPic': '', 'pressedPic': ''},
                 'touchable': True, 'visible': True}
        elif t == 'checkbox':
            # 字段全集 = CTRL_FIELD_TEMPLATES['checkbox']（id 94500 段见 ID_BASE 注释）
            c = {'id': ID_BASE['checkbox'] + n, 'caption': self.caption, 'position': dict(self.pos),
                 'alignment': 37, 'backgroundColor': -1, 'bold': False, 'checked': False,
                 'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                                'color4': -1},
                 'colorTab': {'color0': 16777215, 'color1': -1, 'color2': -1, 'color3': -1,
                              'color4': -1},
                 'fontFamily': 0, 'fontSize': 16, 'italic': False,
                 'iconPosition': {'left': 0, 'top': 0, 'width': 0, 'height': 0},
                 'text': '', 'textPosition': {'left': 0, 'top': 0, 'width': 0, 'height': 0},
                 'touchable': True, 'visible': True}
        elif t == 'radiogroup':
            # 容器 touchable **必须 true**（写 false 整组点不动，radiogroup-checkbox-fields.md 铁律 5）
            c = {'id': ID_BASE['radiogroup'] + n, 'caption': self.caption,
                 'position': dict(self.pos), 'backgroundColor': -1, 'touchable': True,
                 'visible': True, 'radiobuttons': []}
        elif t == 'listview':
            # 字段全集 = CTRL_FIELD_TEMPLATES['listview']；item 模板高由 itemH 公式反算（#37）
            c = {'id': ID_BASE['listview'] + n, 'caption': self.caption, 'position': dict(self.pos),
                 'autoRollback': True, 'backgroundColor': -1, 'cols': 1, 'cycleEnable': False,
                 'dragMaxDis': 50, 'edgeEffect': 1, 'hasScrollbar': False, 'rows': 1,
                 'touchable': True, 'visible': True, 'orientation': 1, 'colSpacing': 0,
                 'rowSpacing': 0, 'item': {}}
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
        self.assets = {}          # 文件名 → ('shape'|'glyph'|'libicon'|…, 参数)
        self.notes = []           # 自检提示（不进 json）
        self.icon_uses = []       # 图标用点清单（语义名 → 库名/档位/状态），供交付报告
        self.icon_fallbacks = []  # 回退 gen_res 线框的图标（目标 0；非 0 时 compose 明说）
        self.root = []            # 根层节点（定义顺序 = z 顺序）
        self.content = []         # 页面中部内容（可能被 scrollwindow 包起来）
        self.y = 0                # 内容当前纵向位置（内容空间，y 从 0 起）
        self.origin = (0, 0)      # 当前容器原点（内容空间）→ 子控件坐标 = 绝对 − origin
        self.title_done = False
        self._sub = 0            # subitem/radiobutton 共用 id 计数器（24000 / 94100 段）

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

    def glyph(self, name, g, size, color, canvas=None, state=None):
        """块内图标：**唯一来源 = `components/icons` 图标资产库**（Tabler 单色烘焙图）。

        钟工 2026-10-01：「这些网络/设备的 icon 来源？效果差异和实际差异太大」——
        库里查得到该语义名 → 走 `iconlib`（按盒尺寸选档，产物图严格 == 控件盒）；
        **库里确实没有**才回退 `gen_res` 线框，并在输出里**明说「回退线框」**（不静默）。

        state：库里的两态图标（_off 描边 / _on 实心）——底导的选中/未选中直接对上；
        单态图标忽略该参数。
        """
        size = int(size)
        info = iconlib.lookup(g) if iconlib.available() else None
        if info is not None:
            self.assets[name] = ('libicon', dict(g=g, size=size, color=color, canvas=canvas,
                                                 state=state))
            self.icon_uses.append(dict(token=g, name=info['name'], icon=info['icon'],
                                       category=info['category'], style=info['style'],
                                       states=info['states'], size=size,
                                       tier=iconlib.tier_of(size), state=state,
                                       asset=name))
        else:
            self.assets[name] = ('glyph', dict(g=g, size=size, color=color, canvas=canvas))
            self.icon_fallbacks.append(dict(token=g, size=size, asset=name,
                                            page=self.page_name))
            print('  [回退线框] 图标 %r 在 components/icons 里没有对应语义名 → 用 gen_res 线框'
                  '（%s；目标 0 处，请改用库里已有语义名）' % (g, name))
        return 'images/' + name

    def chevron(self, name, w, h, color):
        """箭头（行尾 Chevron）：按 SPEC-CHECK §7 的箭头专属口径画。

        为什么不直接用 gen_res.glyph_icon('forward')：iconfont 描边比例是「盒宽 2/24 ≈ 8%」
        → 在 12px 盒上退化成 1px 硬斜边（aa_audit 报 hard_diag）；§7 定的箭头规则是
        「45° + 圆头 + 笔画 ≈ 盒宽 12% 且 ≥2px」，小盒才立得住。这里按该口径实现。
        """
        self.assets[name] = ('chevron', dict(w=int(w), h=int(h), color=color))
        return 'images/' + name

    def bar(self, name, w, h, bar_h, fill):
        """滑轨/有效条：透明画布 w×h + 居中药丸条（可见条高 bar_h）——滑轨图高 == 控件盒高（seekbar-fields.md §3）。"""
        self.assets[name] = ('bar', dict(w=int(w), h=int(h), bar_h=int(bar_h), fill=fill))
        return 'images/' + name

    def mark(self, name, w, h, radius, fill, mark='', mark_size=0, mark_color=None,
             border=None, border_w=1):
        """勾选/单选标记图（底形状 + 可选符号 check/dot）；图 == 控件盒（铁律 #1）。"""
        self.assets[name] = ('mark', dict(w=int(w), h=int(h), radius=int(radius), fill=fill,
                                          mark=mark, mark_size=int(mark_size),
                                          mark_color=mark_color, border=border,
                                          border_w=border_w))
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
            elif kind == 'bar':
                from PIL import Image as _Im
                img = _Im.new('RGBA', (prm['w'], prm['h']), (0, 0, 0, 0))
                bar = gen_res.rounded_rect_cov(prm['w'], prm['bar_h'],
                                               max(1, prm['bar_h'] // 2), prm['fill'], ss=8)
                img.alpha_composite(bar, (0, (prm['h'] - prm['bar_h']) // 2))
                gen_res.save(img, out, name)
            elif kind == 'mark':
                gen_res.save(mark_image(prm), out, name)
            elif kind == 'libicon':
                # 图标资产库出图：按盒尺寸取档/现出，图严格 == 控件盒（铁律 #11/#17）
                img, _meta = iconlib.produce(prm['g'], prm['size'], prm['color'],
                                             prm['state'])
                cv = prm.get('canvas')
                if cv and (int(cv[0]), int(cv[1])) != img.size:
                    from PIL import Image as _Im
                    base = _Im.new('RGBA', (int(cv[0]), int(cv[1])), (0, 0, 0, 0))
                    base.alpha_composite(img, ((int(cv[0]) - img.width) // 2,
                                               (int(cv[1]) - img.height) // 2))
                    img = base
                img.save(os.path.join(out, name))
                print('  %-40s %dx%d  [components/icons %s · %s档 · %s]'
                      % (name, img.width, img.height, _meta['name'], _meta['tier'],
                         _meta['render']))
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
    # 行族扫描范围 = 老行块 + 第 2 批字段行（字段行的文本带必须跟老行同一左缘/同宽）
    FAMILY_TYPES = ROW_TYPES + FIELD_TYPES

    def plan_row_reserve(self, rows):
        """一行族口径（同页全局，越卡也一致）：右端预留宽 + 是否给图标列留位。

        为什么按「页」而不是按「卡」：check_all #27 按容器递归取族，跨卡的同行会互相比；
        且 §2.1 要求“同一页里重复出现的行，其一切口径只能照抄”。所以全页取同一组值。
        2026-10-01 第 2 批修正：文本盒宽也按这个**全页族预留**算（不再按「本行自己有什么右端控件」）
        —— 否则「只有箭头的行」与「有开关的行」文本盒宽不同，#27 会报「口径偏离同族」
        （旧两版示例各有 2 条 WARN 就是这么来的）。
        """
        m = self.m
        reserve = 0
        for b in rows:
            if b['type'] in FIELD_TYPES:
                # 字段行的控件在**独立带**上（不在文本带右端）——只有 checkbox_row 占右端槽
                if b['type'] == 'checkbox_row':
                    reserve = max(reserve, m['cb'])
                continue
            if b['type'] == 'toggle_row':
                reserve = max(reserve, r4(m['row_h'] * 1.30))
            elif b.get('chevron', True):
                reserve = max(reserve, m['chev_w'])
        return reserve

    def assert_icon_uniform(self):
        """自检（钟工 2026-10-01 口径「同一页面统一设计」）：同一页行族，图标要么都有、要么都没有。

        为什么：图标列一旦被某行占用，所有行的文本左缘都会右移一个列宽（全页对齐）；
        此时只有个别行真画图标 → 观感上像「那几行多长了一块」，不统一（实测 1024 版只有
        多屏拼接/客厅面板两行有图标）。
        """
        m = self.m
        rows = []

        def walk(blocks):
            for b in blocks or []:
                if b.get('type') == 'card':
                    walk(b.get('blocks'))
                elif b.get('type') in self.ROW_TYPES:
                    rows.append(b)
        walk(self.page.get('blocks'))
        if not rows:
            return
        with_icon = [b for b in rows if b.get('icon')]
        if with_icon and len(with_icon) != len(rows):
            raise SystemExit(
                '[X] 同页行族图标不统一（%d/%d 行有图标）：%s\n'
                '    口径：同一页面行族图标「要么都有、要么都没有」；'
                '缺图标的行请补 icon，或去掉所有 icon（钟工 2026-10-01）'
                % (len(with_icon), len(rows),
                   '；'.join(b.get('label') or b.get('_name') for b in with_icon)))

    def scan_row_family(self):
        """全页行族扫描：右端预留、图标列、图标盒（供所有行共用同一文本左缘）。"""
        m = self.m
        rows = []

        def walk(blocks):
            for b in blocks or []:
                if b.get('type') == 'card':
                    walk(b.get('blocks'))
                elif b.get('type') in self.FAMILY_TYPES:
                    rows.append(b)
        walk(self.page.get('blocks'))
        self.assert_icon_uniform()          # 自检：同页行族图标统一（全有 / 全无；只看老行块）
        self.fam_reserve = self.plan_row_reserve(rows)
        self.fam_icon = any(b.get('icon') for b in rows) and not m['compact']

    def row_boxes(self, x0, y0, w):
        """行族文本盒统一口径（全页一份）：(text_left, text_w, right_edge)。

        右缘取 **全页族预留**（fam_reserve）而不是「本行自己有什么右端控件」：
        同一页行族只能有一套口径（check_all #27 按族取众数比 left/width/height/alignment，
        按「本行自己的右端控件」算会让只有箭头的行与有开关的行宽度不同 → 报「口径偏离同族」）。
        代价：只有箭头的行会多留一段死区；文本左对齐且短，观感无影响。
        """
        m = self.m
        text_left = x0 + (m['icon_left'] + m['icon_bg'] + m['spacer']
                          if getattr(self, 'fam_icon', False) else m['pad_l'])
        reserve = getattr(self, 'fam_reserve', 0)
        right_edge = x0 + w - m['pad_r'] - (reserve + m['text_chev_gap'] if reserve else 0)
        return text_left, max(1, right_edge - text_left), right_edge

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
        text_left, text_w, right_edge = self.row_boxes(x0, y0, w)
        # 右端槽左缘（全页族预留）：供「值文本右缘 → 右端控件」间隙自检（同页必须一致）
        rt_edge = (x0 + w - m['pad_r'] - reserve) if reserve else None
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

    def row_height(self, blk):
        """一行块占的高度（第 2 批）：字段行 = 文本带 + 控件带；列表/滚轮自带块高。

        必须与各 builder 实际占的高度一致（卡容器高靠它先算出来，子控件坐标是卡局部坐标）。
        """
        m = self.m
        t = blk.get('type')
        if t in ('slider_row', 'progress_row'):
            return m['row_h'] + m['seek_h'] + 2 * m['widget_pad']
        if t == 'input_row':
            return m['row_h'] + m['edit_h'] + 2 * m['widget_pad']
        if t == 'radio_row':
            return m['row_h'] + len(blk.get('options') or []) * m['opt_h'] \
                + 2 * m['widget_pad']
        if t == 'list_item':
            rows = max(1, int(blk.get('rows') or m['li_rows']))
            rs = max(0, int(blk.get('rowSpacing') or 0))
            h = rows * (m['li_h'] + rs) + min(m['li_peek'], rows - 1)
            return h + (m['h_b2'] + m['spacer'] if blk.get('label') else 0)
        if t == 'wheel_picker':
            rows = max(3, int(blk.get('rows') or m['wheel_rows']))
            h = rows * m['wheel_h']
            return h + (m['h_b2'] + m['spacer'] if blk.get('label') else 0)
        return m['row_h']

    def build_card(self, blk, parent, x, y):
        """卡片 = window__N 容器（touchable false）+ 卡底装饰 + 行 + 行间分割线。"""
        m = self.m
        rows = blk.get('blocks') or []
        if blk.get('title'):
            y = self.build_section({'text': blk['title'], '_seq': blk['_seq']}, parent, x, y)
        n = len(rows)
        heights = [self.row_height(b) for b in rows]
        cw, ch_ = m['content_w'], sum(heights)
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
            t = b.get('type')
            if t in FIELD_TYPES:
                self.build_field_row(b, row_nodes, 0, top, cw)
            elif t == 'list_item':
                self.build_list(b, row_nodes, 0, top, cw)
            elif t == 'wheel_picker':
                self.build_wheel(b, row_nodes, 0, top, cw)
            elif t in self.ROW_TYPES:
                has_icon = self.fam_icon and bool(b.get('icon')) and \
                    (not m['compact'] or b['type'] != 'icon_row')
                self.build_row(b, row_nodes, 0, top, cw, reserve, has_icon)
            else:
                raise SystemExit('[X] 卡内不支持的块类型：%s（卡内只能是行块/列表块；'
                                 'tabs/banner/toast/status_pill/divider_label/grid_icons/'
                                 'bottom_nav 是根层块）' % t)
            top += heights[i]
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

    # ─────── 第 2 批 builder：字段行（slider/progress/input/checkbox/radio）───────

    def make_seekbar(self, caption, box, progress, readonly=False):
        """seekbar 控件：轨道/有效图 == 控件盒，thumb 子盒 == 滑块图（seekbar-fields.md）。

        盒高 ≥ thumb.size.height 是硬要求：矮盒会真机把滑块压成扁椭圆（只改图/只改盒都没用）。
        readonly=True（progress_row）：不给滑块图 + thumb.size 写 0（引擎不画滑块；给图会被当成可拖滑块）。
        """
        m = self.m
        th = m['thumb']
        # 可见条高 ≥ 10（AA 审计：条太矮时药丸端的弧线过渡会退化成硬阶梯 → #21 真缺陷），
        # 且 ≈ 盒高 43%（滑轨图高 == 控件盒高，上下透明）
        bar_h = min(box['height'], max(10, r4(box['height'] * 0.43)))
        p_track = self.bar('sk_track_%dx%d.png' % (box['width'], box['height']),
                           box['width'], box['height'], bar_h, rgba(self.tok['color']['line']))
        p_fill = self.bar('sk_fill_%dx%d.png' % (box['width'], box['height']),
                          box['width'], box['height'], bar_h, rgba(self.tok['color']['brand']))
        thumb = {'size': {'width': 0, 'height': 0}, 'normalPic': '', 'pressedPic': ''}
        if not readonly:
            p_thumb = self.shape('sk_thumb_%d.png' % th, th, th, th // 2,
                                 rgba(self.tok['color']['brand']))
            thumb = {'size': {'width': th, 'height': th}, 'normalPic': p_thumb,
                     'pressedPic': p_thumb}
        return Node('seekbar', caption, box,
                    {'backgroundPic': p_track, 'progressPic': p_fill,
                     'secondaryProgressPic': '', 'defProgress': int(progress), 'max': 100,
                     'orientation': 0, 'thumb': thumb, 'touchable': True})

    def make_edittext(self, caption, box, blk):
        """edittext 控件：底色用 bgColorTab 浅灰（白卡上白输入框看不见），不用图（避免描边环 AA 问题）。"""
        m = self.m
        col = {k: hex2int(v) for k, v in self.tok['color'].items() if v.startswith('#')}
        payload = {'alignment': 36, 'fontSize': m['fs']['b1'],
                   'bgColorTab': {'color0': hex2int(self.tok['color']['page']), 'color1': -1,
                                  'color2': -1, 'color3': -1, 'color4': -1},
                   'colorTab': {'color0': col['fg1'], 'color1': -1, 'color2': -1, 'color3': -1,
                                'color4': -1},
                   'hintTextColor': 8947848,          # #888888（edittext-fields.md 实测值）
                   'hintText': blk.get('hintText') or '', 'text': blk.get('text') or '',
                   'textType': int(blk.get('textType') or 0),
                   'isPassword': bool(blk.get('isPassword', False)),
                   'passwordChar': blk.get('passwordChar') or '*',
                   'beepEnable': True, 'touchable': True}
        return Node('edittext', caption, box, payload)

    def make_checkbox(self, caption, box, checked):
        """checkbox 控件（正方盒；pic0 未选 / pic2 选中，两张图 == 盒）。"""
        m = self.m
        s = int(box['width'])
        col = {k: hex2int(v) for k, v in self.tok['color'].items() if v.startswith('#')}
        r = max(2, int(round(s * 0.25)))
        # 关态用 switchOff 实底（不用 1px 环）：小盒上的 1px 环会让 AA 审计退回「成片直通 α」
        off = self.mark('cb_%d_off.png' % s, s, s, r, rgba(self.tok['color']['switchOff']))
        on = self.mark('cb_%d_on.png' % s, s, s, r, rgba(self.tok['color']['brand']),
                       mark='check', mark_size=max(8, int(round(s * 0.58))),
                        mark_color=rgba(self.tok['color']['onBrand']))
        icon_pos = {'left': 0, 'top': 0, 'width': s, 'height': s}
        return Node('checkbox', caption, box,
                    {'alignment': 37, 'checked': bool(checked), 'bold': False,
                     'fontSize': m['fs']['b1'], 'italic': False, 'text': '',
                     'colorTab': {'color0': col['fg1'], 'color1': -1, 'color2': -1, 'color3': -1,
                                  'color4': -1},
                     'backgroundColor': -1, 'touchable': True,
                     'iconPosition': dict(icon_pos), 'textPosition': dict(icon_pos),
                     'picTab': {'pic0': off, 'pic1': off, 'pic2': on}})

    def make_radiogroup(self, caption, box, opts, selected, name):
        """radiogroup + radiobuttons（竖排）：子项坐标相对 radiogroup；组 touchable 必须 true。"""
        m = self.m
        col = {k: hex2int(v) for k, v in self.tok['color'].items() if v.startswith('#')}
        s = m['cb']
        rbs = []
        off = self.mark('rd_%d_off.png' % s, s, s, s // 2, rgba(self.tok['color']['switchOff']))
        # 内点只在标记盒 ≥ 24px 时给：7px 内点的弧线在 aa_audit 里会退化成硬阶梯（#21 真缺陷）
        # → 极小屏（16px）改用「实底色区分态」（品牌实底 = 选中 / switchOff 实底 = 未选）
        if s >= 24:
            on = self.mark('rd_%d_on.png' % s, s, s, s // 2, rgba(self.tok['color']['brand']),
                           mark='dot', mark_size=max(6, int(round(s * 0.42))),
                           mark_color=rgba(self.tok['color']['onBrand']))
        else:
            on = self.mark('rd_%d_on.png' % s, s, s, s // 2, rgba(self.tok['color']['brand']))
        gw, oh = int(box['width']), m['opt_h']
        for i, txt in enumerate(opts):
            self._sub += 1
            rbs.append({'id': RADIOBUTTON_ID_BASE + self._sub,
                        'caption': '%sOpt%d' % (name, i + 1),
                        'position': {'left': 0, 'top': i * oh, 'width': gw, 'height': oh},
                        'alignment': 36, 'backgroundColor': -1, 'bold': False,
                        'checked': bool(i == int(selected)),
                        'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                                       'color4': -1},
                        'colorTab': {'color0': col['fg1'], 'color1': -1, 'color2': col['brand'],
                                     'color3': -1, 'color4': -1},
                        'fontFamily': 0, 'fontSize': m['fs']['b1'], 'italic': False,
                        'iconPosition': {'left': m['spacer'], 'top': (oh - s) // 2,
                                         'width': s, 'height': s},
                        'textPosition': {'left': 2 * m['spacer'] + s,
                                         'top': (oh - m['h_b1']) // 2,
                                         'width': gw - (3 * m['spacer'] + s),
                                         'height': m['h_b1']},
                        'picTab': {'pic0': off, 'pic1': off, 'pic2': on},
                        'text': str(txt), 'touchable': True, 'visible': True,
                        'beepEnable': True})
        return Node('radiogroup', caption, box, {'touchable': True, 'radiobuttons': rbs})

    def build_field_row(self, blk, parent, x0, y0, w):
        """字段行 = 文本带（行高，**逐字节照抄行族口径**）+ 控件带（控件单独占一带）。

        为什么控件单独占一带（而不是塞进行条右端）：
          · seekbar/edittext 需要「盒高 ≥ 滑块高 / 文本高」才不被压扁（seekbar-fields.md §2）；
          · 塞进行条右端会与值文本盒几何相交 → #27 文本×控件重叠 / 观感上文字外凸；
          · 独立带在极小屏（320×240）也放得下，不必另设一套形态。
        返回本行占的高度（供卡容器 / 内容流累加）。
        """
        m = self.m
        col = {k: hex2int(v) for k, v in self.tok['color'].items() if v.startswith('#')}
        t = blk['type']
        text_left, text_w, _re_ = self.row_boxes(x0, y0, w)
        label = blk.get('label') or ''
        value = blk.get('value') or ''
        if m['compact'] and blk.get('value_short'):
            value = blk['value_short']
        row = []
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
            row.append(self.text('TextRow%sLabel' % blk['_name'],
                                 self.box(text_left, ty, lw, m['h_b1']),
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
        band_y = y0 + m['row_h']
        band_h = 0
        bx = x0 + m['pad_l']
        bw = w - 2 * m['pad_l']
        if t in ('slider_row', 'progress_row'):
            band_h = m['seek_h'] + 2 * m['widget_pad']
            row.append(self.make_seekbar('SeekRow%sBar' % blk['_name'],
                                         self.box(bx, band_y + m['widget_pad'], bw, m['seek_h']),
                                         blk.get('progress') or 0,
                                         readonly=(t == 'progress_row')))
        elif t == 'input_row':
            band_h = m['edit_h'] + 2 * m['widget_pad']
            row.append(self.make_edittext('EditRow%sBox' % blk['_name'],
                                          self.box(bx, band_y + m['widget_pad'], bw, m['edit_h']),
                                          blk))
        elif t == 'checkbox_row':
            s = m['cb']                                        # 复选框在文本带右端槽（同 toggle_row 形态）
            row.append(self.make_checkbox('CheckRow%sBox' % blk['_name'],
                                          self.box(x0 + w - m['pad_r'] - s,
                                                   y0 + (m['row_h'] - s) // 2, s, s),
                                          blk.get('checked', False)))
        elif t == 'radio_row':
            band_h = len(blk.get('options') or []) * m['opt_h'] + 2 * m['widget_pad']
            row.append(self.make_radiogroup('RadioRow%sGroup' % blk['_name'],
                                            self.box(bx, band_y + m['widget_pad'], bw, band_h - 2 * m['widget_pad']),
                                            blk.get('options') or [], blk.get('selected', 0),
                                            'RadioRow%s' % blk['_name']))
        else:
            raise SystemExit('[X] 字段行未知类型：%s' % t)
        parent.extend(row)
        return m['row_h'] + band_h

    # ─────── 第 2 批 builder：list_item / wheel_picker（listview 族）───────

    def subitem(self, caption, pos, fs, color, txt='', pic=None, align=36):
        """listview 行内子项（字段全集 = CTRL_FIELD_TEMPLATES['subitem']；id 24000 段）。"""
        self._sub += 1
        return {'id': SUBITEM_ID_BASE + self._sub, 'caption': caption, 'position': pos,
                'alignment': align, 'backgroundColor': -1,
                'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                               'color4': -1},
                'bold': False,
                'colorTab': {'color0': color, 'color1': -1, 'color2': -1, 'color3': -1,
                             'color4': -1},
                'fontFamily': 0, 'fontSize': fs, 'italic': False,
                'longClickIntervalTime': -1, 'longClickTimeOut': -1,
                'picTab': {'pic0': pic or ''}, 'text': txt, 'touchable': True, 'visible': True}

    def list_item_template(self, caption, w, ih, chevron=True):
        """listview 行模板：item.text 空串 + 内容走 subItem（绝不平铺子控件）。"""
        m = self.m
        col = {k: hex2int(v) for k, v in self.tok['color'].items() if v.startswith('#')}
        sub = []
        right = m['pad_l'] + (m['chev_w'] + m['spacer'] if chevron else 0)
        sub.append(self.subitem(caption + 'SubTitle',
                                {'left': m['pad_l'], 'top': (ih - m['h_b1']) // 2,
                                 'width': w - m['pad_l'] - right, 'height': m['h_b1']},
                                m['fs']['b1'], col['fg1']))
        if chevron:
            p = self.chevron('chev_%dx%d.png' % (m['chev_w'], m['chev_h']),
                             m['chev_w'], m['chev_h'], rgba(self.tok['color']['chevron']))
            sub.append(self.subitem(caption + 'SubChevron',
                                    {'left': w - m['pad_l'] - m['chev_w'],
                                     'top': (ih - m['chev_h']) // 2,
                                     'width': m['chev_w'], 'height': m['chev_h']},
                                    m['fs']['b2'], col['chevron'], pic=p, align=37))
        return {'caption': caption, 'position': {'left': 0, 'top': 0, 'width': w, 'height': ih},
                'alignment': 36, 'backgroundColor': -1, 'bold': False,
                'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                               'color4': -1},
                'colorTab': {'color0': col['fg1'], 'color1': col['fg1'], 'color2': col['fg1'],
                             'color3': col['fg1'], 'color4': -1},
                'fontSize': m['fs']['b1'], 'italic': False, 'picTab': {}, 'text': '',
                'touchable': True, 'visible': True,
                'longClickIntervalTime': -1, 'longClickTimeOut': -1, 'subItem': sub}

    def build_list(self, blk, parent, x, y, w):
        """list_item：listview + subItem 行模板。

        itemH = int(lv高 / rows) − rowSpacing（引擎口径）——模板高必须 == 它（check_all #37）；
        余数（= lv高 mod rows）**是有意的可滑动提示**（底部露出下一项一小块），不是缺陷。
        返回本块占的高度。
        """
        m = self.m
        col = {k: hex2int(v) for k, v in self.tok['color'].items() if v.startswith('#')}
        rows = max(1, int(blk.get('rows') or m['li_rows']))
        rs = max(0, int(blk.get('rowSpacing') or 0))
        ih = m['li_h']
        peek = min(m['li_peek'], rows - 1)
        lv_w = w - 2 * m['pad_l']
        lv_h = rows * (ih + rs) + peek
        cur = y
        if blk.get('label'):
            parent.append(self.text('Label%s' % blk['_name'],
                                    self.box(x + m['pad_l'], cur, lv_w, m['h_b2']),
                                    m['fs']['b2'], col['fg2'], blk['label']))
            cur += m['h_b2'] + m['spacer']
        item = self.list_item_template(blk['_name'] + 'Item', lv_w, ih,
                                       blk.get('chevron', True))
        parent.append(Node('listview', 'List' + blk['_name'],
                           self.box(x + m['pad_l'], cur, lv_w, lv_h),
                           {'rows': rows, 'rowSpacing': rs, 'cols': 1, 'cycleEnable': False,
                            'edgeEffect': 1, 'autoRollback': True, 'hasScrollbar': False,
                            'dragMaxDis': m['drag_max'], 'orientation': 1, 'item': item}))
        return cur + lv_h - y

    def build_wheel(self, blk, parent, x, y, w):
        """wheel_picker：一列 = 一个 listview；选中条挂**静态层**且写在 listview 之前。

        口径（knowledge/uicontrols/listview-wheel-picker.md）：
          · 正中行 = 选中行（rows 必须奇数；运行时用「数据侧平移」把值摆到正中）；
          · 选中条必须是**先定义的静态 textview**（z 更低）—— 挂行背景图会跟着行滚；
          · lv 高 = rows × 模板高（滚轮要刚好一屏窗口，不留余数）。
        返回本块占的高度。
        """
        m = self.m
        col = {k: hex2int(v) for k, v in self.tok['color'].items() if v.startswith('#')}
        cols = blk.get('columns')
        if isinstance(cols, int):
            cols = [{} for _ in range(max(1, cols))]
        cols = list(cols or [{}])
        rows = max(3, int(blk.get('rows') or m['wheel_rows']))
        if rows % 2 == 0:
            raise SystemExit('[X] wheel_picker.rows 必须为奇数（正中行 = 选中行），得到 %d' % rows)
        ih = m['wheel_h']
        lv_h = rows * ih
        gap = m['spacer2']
        n = len(cols)
        col_w = min(m['wheel_col_w'], max(m['cb'] * 2, (w - (n - 1) * gap - 2 * m['pad_l']) // n))
        col_w = r4(col_w)
        cur = y
        if blk.get('label'):
            parent.append(self.text('Label%s' % blk['_name'],
                                    self.box(x + m['pad_l'], cur, w - 2 * m['pad_l'], m['h_b2']),
                                    m['fs']['b2'], col['fg2'], blk['label']))
            cur += m['h_b2'] + m['spacer']
        total = n * col_w + (n - 1) * gap
        cx0 = x + max(0, (w - total) // 2)
        band_r = max(4, min(m['tok']['shape']['container_radius_px'], int(round(ih * 0.18))))
        bands, lists = [], []
        for i in range(n):
            cx = cx0 + i * (col_w + gap)
            cap = '%sCol%d' % (blk['_name'], i + 1)
            p = self.shape('wband_%dx%d.png' % (col_w, ih), col_w, ih, band_r,
                           rgba(self.tok['color']['brand1']))
            bands.append(self.text('Band' + cap,
                                   self.box(cx, cur + (rows // 2) * ih, col_w, ih),
                                   m['fs']['b2'], col['brand1'], '', bg=p, align=37))
            item = self.list_item_template('Text' + cap, col_w, ih, chevron=False)
            item['alignment'] = 37
            for si in item['subItem']:
                si['alignment'] = 37
            lists.append(Node('listview', 'List' + cap, self.box(cx, cur, col_w, lv_h),
                              {'rows': rows, 'rowSpacing': 0, 'cols': 1, 'cycleEnable': True,
                               'edgeEffect': 1, 'autoRollback': True, 'hasScrollbar': False,
                               'dragMaxDis': m['drag_max'], 'orientation': 1, 'item': item}))
        parent.extend(bands)                # 条先定义 = z 更低（滚动时条一个像素不动）
        parent.extend(lists)
        return cur + lv_h - y

    # ─────── 第 3 批 builder：结构 / 导航 / 提示类 ───────
    #   统一形态（照抄行族口径）：**装饰件先定义（z 低 + touchable 显式 false）→ 命中 button 最后定义（z 高）**；
    #   容器一律过 assert_children_fit；文本一律过 check_text_fit（#13）；
    #   「文本右缘 → 右端控件左缘」间隙过 note_row_gaps（同页一致 → assert_row_gaps）。
    #   这批块都是**根层块**：卡内只收行块 / 列表块（build_card 的类型校验会拒绝，不静默兜底）。

    def text_box_w(self, txt, fs, align=37, slack=1.10):
        """文本盒宽 = FT-009 估算宽 × slack，再**向上**取 4px 栅格。

        为什么向上取整：check_all #36 文本余量要求「盒宽 ≥ 估算宽 × 1.05」，
        而 r4 是四舍五入（可能把余量吃掉）→ 这里用 r4up（例：42 → 44 而不是 40）。
        """
        mw, _h = text_min_size(txt, fs, align)
        return r4up(max(4, mw) * slack)

    def sem_color(self, state):
        """语义状态 → (前景令牌名, 浅底令牌名)。状态非法 → 报错（不静默兜底）。

        表里同时收 banner 的 4 态（info/success/warn/danger）与胶囊的 4 态（ok/warn/danger/off）。
        """
        table = {'info': ('info', 'info1'), 'success': ('success', 'success1'),
                 'warn': ('warn', 'warn1'), 'danger': ('danger', 'danger1'),
                 'ok': ('success', 'success1'), 'off': ('fg2', 'page')}
        if state not in table:
            raise SystemExit('[X] 未知语义状态：%s（可用：%s）'
                             % (state, '、'.join(sorted(table))))
        return table[state]

    def col_int(self):
        """令牌色名 → FlyThings 整型色值。"""
        return {k: hex2int(v) for k, v in self.tok['color'].items() if v.startswith('#')}

    def build_tabs(self, blk, parent, x, y):
        """顶部分段控件：容器（window）+ 指示条 + 选中底 + N 个 tab（透明 button 自带文字）。

        z 顺序（本块内）：容器底 → **指示条（先于所有 tab 定义：静态件放最前）** → 选中底 → tab 按钮。
        指示条与选中底**几何不重叠**（选中底高度让出 ind_h）→ 谁先定义都不互相遮挡；
        两者都写在 tab 按钮之前（装饰件 z 低、touchable 显式 false）→ #15/#29 不误报。
        """
        m = self.m
        col = self.col_int()
        items = [str(s) for s in (blk.get('items') or [])]
        if len(items) < 2:
            raise SystemExit('[X] tabs.items 至少 2 个（分段控件），得到 %d' % len(items))
        n = len(items)
        sel = int(blk.get('selected') or 0)
        if not 0 <= sel < n:
            raise SystemExit('[X] tabs.selected=%d 越界（可选 0~%d）' % (sel, n - 1))
        w, h = m['content_w'], m['tab_h']
        win = Node('window', 'Tabs%d' % blk['_seq'], self.box(x, y, w, h))
        p_bg = self.shape('tabsbg_%dx%d.png' % (w, h), w, h, h // 2,
                          rgba(self.tok['color']['surface']))
        win.children.append(self.text('TabsBg%d' % blk['_seq'], self.box(0, 0, w, h),
                                      m['fs']['b2'], col['surface'], '', bg=p_bg, align=37))
        base = w // n
        widths = [base] * n
        widths[-1] = w - base * (n - 1)
        lefts, cur = [], 0
        for i in range(n):
            lefts.append(cur)
            cur += widths[i]
        # ① 指示条：静态件放最前；水平两侧内缩 m['radius']（避开容器圆角，见反面清单 #11/#22）
        ind_w = max(4, widths[sel] - 2 * m['radius'])
        p_ind = self.shape('ind_%dx%d.png' % (ind_w, m['ind_h']), ind_w, m['ind_h'], 0,
                           rgba(self.tok['color']['brand']))
        win.children.append(self.text('TabsIndicator%d' % blk['_seq'],
                                      self.box(lefts[sel] + m['radius'], h - m['ind_h'],
                                               ind_w, m['ind_h']),
                                      m['fs']['b2'], col['brand'], '', bg=p_ind, align=37))
        # ② 选中 tab 的底色（高度让出指示条 → 与①不重叠）
        on_w, on_h = widths[sel], h - m['ind_h']
        p_on = self.shape('tab_on_%dx%d.png' % (on_w, on_h), on_w, on_h, m['radius'],
                          rgba(self.tok['color']['brand1']))
        win.children.append(self.text('TabsOnBg%d' % blk['_seq'],
                                      self.box(lefts[sel], 0, on_w, on_h),
                                      m['fs']['b2'], col['brand1'], '', bg=p_on, align=37))
        # ③ tab：透明 button（文字自带、命中区 = 整个 tab 盒）；caption 唯一 → logic 骨架自动出回调
        for i, txt in enumerate(items):
            cap = 'Tabs%dItem%d' % (blk['_seq'], i + 1)
            win.children.append(self.button(cap, self.box(lefts[i], 0, widths[i], h),
                                            fs=m['fs']['b1'],
                                            color=col['brand'] if i == sel else col['fg2'],
                                            align=37, txt=txt))
            self.check_text_fit(cap, txt, m['fs']['b1'], widths[i], h, 'tab')
        self.assert_children_fit(win, w, h, 'Tabs%d' % blk['_seq'])
        parent.append(win)
        return y + h

    def build_nav(self, blk, parent):
        """底部导航（固定带，贴底栏上沿）：满宽白面 + 每项 图标 + 文字 + 整项命中按钮。

        与 bottom_actions 的区别：**固定高**（nav_h 只跟屏高/图标档有关，与项数无关）、**无主次按钮**。
        底导带与底栏带**不重叠**（nav 贴 bar_bot 上沿），视口在 run() 里扣掉 nav_h。
        """
        m = self.m
        col = self.col_int()
        items = blk.get('items') or []
        n = len(items)
        if not 2 <= n <= 6:
            raise SystemExit('[X] bottom_nav.items 应为 3~5 项（允许 2~6），得到 %d' % n)
        sel = int(blk.get('selected') or 0)
        if not 0 <= sel < n:
            raise SystemExit('[X] bottom_nav.selected=%d 越界（可选 0~%d）' % (sel, n - 1))
        w, h = self.W, m['nav_h']
        ny = self.H - m['bar_bot'] - h
        win = Node('window', 'BottomNav%d' % blk['_seq'],
                   {'left': 0, 'top': ny, 'width': w, 'height': h})
        p_bg = self.shape('navbg_%dx%d.png' % (w, h), w, h, 0,
                          rgba(self.tok['color']['surface']))
        win.children.append(self.text('NavBg%d' % blk['_seq'], self.box(0, 0, w, h),
                                      m['fs']['b2'], col['surface'], '', bg=p_bg, align=37))
        base = w // n
        widths = [base] * n
        widths[-1] = w - base * (n - 1)
        ic = m['nav_ic']
        top_ic = max(4, (h - (ic + m['nav_gap'] + m['h_b2'])) // 2)
        lefts, cur = [], 0
        for i in range(n):
            lefts.append(cur)
            cur += widths[i]
        deco = []                       # 装饰件（先定义）
        btns = []                       # 命中区（最后定义）
        for i, it in enumerate(items):
            it = it if isinstance(it, dict) else {'text': str(it)}
            on = (i == sel)
            glyph = it.get('icon') or 'info'
            iw, ix0 = widths[i], lefts[i]
            p_ic = self.glyph('nav_%s_%d_%s.png' % (glyph, ic, 'on' if on else 'off'), glyph, ic,
                              rgba(self.tok['color']['brand'] if on
                                   else self.tok['color']['fg2']), canvas=(ic, ic),
                              state='on' if on else 'off')      # 库里两态图标直接对上选中态
            deco.append(self.text('Nav%dItem%dIcon' % (blk['_seq'], i + 1),
                                  self.box(ix0 + (iw - ic) // 2, top_ic, ic, ic),
                                  m['fs']['b2'], col['brand'] if on else col['fg2'],
                                  '', bg=p_ic, align=37))
            lbl = it.get('text') or ''
            deco.append(self.text('Nav%dItem%dLabel' % (blk['_seq'], i + 1),
                                  self.box(ix0, top_ic + ic + m['nav_gap'], iw, m['h_b2']),
                                  m['fs']['b2'], col['brand'] if on else col['fg2'],
                                  lbl, align=37))
            self.check_text_fit('Nav%dItem%dLabel' % (blk['_seq'], i + 1), lbl, m['fs']['b2'],
                                iw, m['h_b2'], 'nav')
            btns.append(self.button('Nav%dItem%d' % (blk['_seq'], i + 1),
                                    self.box(ix0, 0, iw, h)))
        win.children.extend(deco)
        win.children.extend(btns)
        self.assert_children_fit(win, w, h, 'BottomNav%d' % blk['_seq'])
        parent.append(win)
        return ny + h

    def build_banner(self, blk, parent, x, y):
        """提示 / 告警条：浅语义底 + 图标 + 一行文案 + 可选关闭按钮（4 种语义色走令牌）。"""
        m = self.m
        col = self.col_int()
        state = str(blk.get('state') or 'info')
        fg_name, bg_name = self.sem_color(state)
        w, h = m['content_w'], m['banner_h']
        win = Node('window', 'Banner%d' % blk['_seq'], self.box(x, y, w, h))
        p_bg = self.shape('bnr_%s_%dx%d.png' % (state, w, h), w, h, m['radius'],
                          rgba(self.tok['color'][bg_name]))
        win.children.append(self.text('BannerBg%d' % blk['_seq'], self.box(0, 0, w, h),
                                      m['fs']['b2'], col[fg_name], '', bg=p_bg, align=37))
        glyph = blk.get('icon') or {'info': 'info', 'success': 'check', 'warn': 'warning',
                                    'danger': 'warning', 'ok': 'check',
                                    'off': 'info'}[state]
        ic = m['ic_min']
        p_ic = self.glyph('ic_%s_%d_%s.png' % (glyph, ic, state), glyph, ic,
                          rgba(self.tok['color'][fg_name]), canvas=(ic, ic))
        win.children.append(self.text('Banner%dIcon' % blk['_seq'],
                                      self.box(m['pad_l'], (h - ic) // 2, ic, ic),
                                      m['fs']['b2'], col[fg_name], '', bg=p_ic, align=37))
        close = bool(blk.get('close', True))
        cw = max(16, ic)                                     # 命中盒下限 16（手指点得到）
        gj = m['text_chev_gap']                              # 与行族同一间隙口径（assert_row_gaps 同页一致）
        text_left = m['pad_l'] + ic + m['spacer']
        text_right = w - m['pad_r'] - (cw + gj if close else 0)
        label = blk.get('text') or ''
        win.children.append(self.text('Banner%dText' % blk['_seq'],
                                      self.box(text_left, (h - m['h_b1']) // 2,
                                               text_right - text_left, m['h_b1']),
                                      m['fs']['b1'], col[fg_name], label, align=36))
        self.check_text_fit('Banner%dText' % blk['_seq'], label, m['fs']['b1'],
                            text_right - text_left, m['h_b1'], 'banner')
        if close:
            self.note_row_gaps('Banner%dText' % blk['_seq'], text_right,
                               w - m['pad_r'] - cw)          # 与分割线同口径（间隙 = spacer）
            p_cl = self.glyph('ic_close_%d_%s.png' % (cw, state), 'close', cw,
                              rgba(self.tok['color']['fg2']), canvas=(cw, cw))
            win.children.append(self.button('Banner%dClose' % blk['_seq'],
                                            self.box(w - m['pad_r'] - cw, (h - cw) // 2,
                                                     cw, cw), bg=p_cl))
        self.assert_children_fit(win, w, h, 'Banner%d' % blk['_seq'])
        parent.append(win)
        return y + h

    def build_pill(self, blk, parent, x, y):
        """状态胶囊：圆角药丸（浅语义底）+ 彩色文字；state: ok / warn / danger / off。"""
        m = self.m
        col = self.col_int()
        state = str(blk.get('state') or 'ok')
        fg_name, bg_name = self.sem_color(state)
        txt = blk.get('text') or ''
        h = m['pill_h']
        fs = m['fs']['b2']
        w = min(m['content_w'], self.text_box_w(txt, fs, 37) + 2 * m['pill_pad'])
        win = Node('window', 'StatusPill%d' % blk['_seq'], self.box(x, y, w, h))
        p_bg = self.shape('pill_%s_%dx%d.png' % (state, w, h), w, h, h // 2,
                          rgba(self.tok['color'][bg_name]))
        win.children.append(self.text('StatusPill%dBg' % blk['_seq'], self.box(0, 0, w, h),
                                      fs, col[bg_name], '', bg=p_bg, align=37))
        win.children.append(self.text('StatusPill%dText' % blk['_seq'], self.box(0, 0, w, h),
                                      fs, col[fg_name], txt, align=37))
        self.check_text_fit('StatusPill%dText' % blk['_seq'], txt, fs, w, h, 'pill')
        self.assert_children_fit(win, w, h, 'StatusPill%d' % blk['_seq'])
        parent.append(win)
        return y + h

    def build_divider_label(self, blk, parent, x, y):
        """带文字分割线：左右 1px 线 + 中间小字；线长 = 容器剩余空间对半分（随容器比例伸缩）。"""
        m = self.m
        col = self.col_int()
        txt = blk.get('text') or ''
        h = m['divider_h']
        fs = m['fs']['b2']
        tw = min(self.text_box_w(txt, fs, 37), m['content_w'] - 2 * (m['spacer'] + 4))
        gj = m['text_chev_gap']                              # 与行族同一间隙口径（assert_row_gaps 同页一致）
        line = max(4, (m['content_w'] - tw) // 2 - gj)
        p_line = self.shape('sep_%dx1.png' % line, line, 1, 0, rgba(self.tok['color']['line']))
        ly = y + (h - 1) // 2
        parent.append(self.text('DividerLabel%dLineL' % blk['_seq'],
                                self.box(x, ly, line, 1), fs, col['line'], '',
                                bg=p_line, align=37))
        parent.append(self.text('DividerLabel%dLineR' % blk['_seq'],
                                self.box(x + m['content_w'] - line, ly, line, 1), fs,
                                col['line'], '', bg=p_line, align=37))
        tx = x + (m['content_w'] - tw) // 2
        parent.append(self.text('DividerLabel%dText' % blk['_seq'],
                                self.box(tx, y + (h - m['h_b2']) // 2, tw, m['h_b2']),
                                fs, col['fg2'], txt, align=37))
        self.note_row_gaps('DividerLabel%dText' % blk['_seq'], x + line, tx)
        return y + h

    def build_grid(self, blk, parent, x, y):
        """图标宫格：N×M 等距格，每格 = 格底（图 == 格盒）+ 图标底 + 图标 + 文字（格数由 spec 决定）。"""
        m = self.m
        col = self.col_int()
        items = blk.get('items') or []
        if not items:
            raise SystemExit('[X] grid_icons.items 不能为空')
        cols = int(blk.get('cols') or 4)
        if not 1 <= cols <= 6:
            raise SystemExit('[X] grid_icons.cols 应在 1~6，得到 %d' % cols)
        n = len(items)
        rows = (n + cols - 1) // cols
        tile_h, gap, rgap = m['grid_tile_h'], m['grid_gap'], m['grid_row_gap']
        gh = rows * tile_h + (rows - 1) * rgap
        win = Node('window', 'GridIcons%d' % blk['_seq'], self.box(x, y, m['content_w'], gh))
        base = m['content_w'] // cols
        widths = [base] * cols
        widths[-1] = m['content_w'] - base * (cols - 1)
        lefts, cur = [], 0
        for i in range(cols):
            lefts.append(cur)
            cur += widths[i]
        tappable = bool(blk.get('tappable', False))
        ib, ic = m['grid_ib'], m['grid_ic']
        deco, btns = [], []
        for i, it in enumerate(items):
            it = it if isinstance(it, dict) else {'text': str(it)}
            r, c = divmod(i, cols)
            cap = 'GridIcons%dCell%d' % (blk['_seq'], i + 1)
            tw = max(8, widths[c] - gap)                     # 格盒（== 格底图尺寸）
            tx = lefts[c] + (widths[c] - tw) // 2
            ty = r * (tile_h + rgap)
            p_tile = self.shape('gtile_%dx%d.png' % (tw, tile_h), tw, tile_h, m['radius'],
                                rgba(self.tok['color']['surface']))
            deco.append(self.text(cap + 'Bg', self.box(tx, ty, tw, tile_h), m['fs']['b2'],
                                  col['surface'], '', bg=p_tile, align=37))
            p_ib = self.shape('icbg_%d.png' % ib, ib, ib, ib // 2,
                              rgba(self.tok['color']['brand1']))
            deco.append(self.text(cap + 'IconBg',
                                  self.box(tx + (tw - ib) // 2, ty + m['spacer'], ib, ib),
                                  m['fs']['b2'], col['brand1'], '', bg=p_ib, align=37))
            glyph = it.get('icon') or 'info'
            p_ic = self.glyph('ic_%s_%d.png' % (glyph, ic), glyph, ic,
                              rgba(self.tok['color']['brand']), canvas=(ic, ic),
                              state=it.get('state'))       # 可选态：'off' 描边 / 'on' 实心（库两态）
            deco.append(self.text(cap + 'Icon',
                                  self.box(tx + (tw - ic) // 2,
                                           ty + m['spacer'] + (ib - ic) // 2, ic, ic),
                                  m['fs']['b2'], col['brand'], '', bg=p_ic, align=37))
            lbl = it.get('text') or ''
            deco.append(self.text(cap + 'Label',
                                  self.box(tx, ty + m['spacer'] + ib + m['spacer'], tw,
                                           m['h_b2']),
                                  m['fs']['b2'], col['fg1'], lbl, align=37))
            self.check_text_fit(cap + 'Label', lbl, m['fs']['b2'], tw, m['h_b2'], 'grid')
            if tappable:
                btns.append(self.button(cap, self.box(tx, ty, tw, tile_h)))
        win.children.extend(deco)
        win.children.extend(btns)
        self.assert_children_fit(win, m['content_w'], gh, 'GridIcons%d' % blk['_seq'])
        parent.append(win)
        return y + gh

    def build_toast(self, blk, parent):
        """浮层提示（根层整屏 window + 半透明圆角底 + 文案）：**visible=false 默认、最后定义 = 最上层**。

        为什么根层整屏 window：与 dialog 同构（业务用 showWnd()/hideWnd() 控制），
        但 modal=false + touchable=false（提示不该拦住操作）；visible=false 时 #15/#29 自然不报。
        """
        m = self.m
        col = self.col_int()
        txt = blk.get('text') or ''
        fs = m['fs']['b1']
        h = m['toast_h']
        w = min(r4(m['content_w'] * 0.70), self.text_box_w(txt, fs, 37) + 2 * m['spacer3'])
        win = Node('window', 'ToastWindow%d' % blk['_seq'],
                   {'left': 0, 'top': 0, 'width': self.W, 'height': self.H},
                   {'modal': False, 'touchable': False,
                    'visible': bool(blk.get('visible', False))})
        tx = (self.W - w) // 2
        ty = int((self.H - h) * m['toast_top_of_h'])
        ty = max(0, min(self.H - h, ty))
        p_bg = self.shape('toast_bg_%dx%d.png' % (w, h), w, h, m['radius'],
                          rgba(self.tok['color']['mask'], 0x99))
        win.children.append(self.text('ToastBg%d' % blk['_seq'], self.box(tx, ty, w, h),
                                      fs, col['onBrand'], '', bg=p_bg, align=37))
        win.children.append(self.text('ToastText%d' % blk['_seq'], self.box(tx, ty, w, h),
                                      fs, col['onBrand'], txt, align=37))
        self.check_text_fit('ToastText%d' % blk['_seq'], txt, fs, w, h, 'toast')
        parent.append(win)
        return self.H

    # ─────── 主流程 ───────
    def run(self):
        m = self.m
        self.root = []
        content, footer, dialogs = [], [], []
        navs, toasts = [], []
        seen_title = False
        self._seq = 0
        self.name_tree(self.page.get('blocks'))      # 先全页统一编号（caption 唯一性来源）
        self.scan_row_family()
        # bottom_nav 是**固定带**（贴底栏上沿）：它不出现在内容流里，但占视口高度
        for b in self.page.get('blocks') or []:
            if b.get('type') == 'bottom_nav':
                navs.append(b)
        if navs:
            m['viewport'] = max(40, m['viewport'] - m['nav_h'])
            self.notes.append('bottom_nav 固定带 %d px 贴底栏上沿 → 视口缩至 %d'
                              % (m['nav_h'], m['viewport']))
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
            elif t in FIELD_TYPES:
                self.y += self.build_field_row(blk, content, m['margin'], self.y,
                                               m['content_w'])
            elif t in WIDGET_TYPES:
                if self.y > 0:
                    self.y += m['group_gap']
                if t == 'list_item':
                    self.y += self.build_list(blk, content, m['margin'], self.y,
                                              m['content_w'])
                else:
                    self.y += self.build_wheel(blk, content, m['margin'], self.y,
                                               m['content_w'])
            elif t in STRUCT3_TYPES:
                if self.y > 0:
                    self.y += m['group_gap']
                if t == 'tabs':
                    self.y = self.build_tabs(blk, content, m['margin'], self.y)
                elif t == 'banner':
                    self.y = self.build_banner(blk, content, m['margin'], self.y)
                elif t == 'status_pill':
                    self.y = self.build_pill(blk, content, m['margin'], self.y)
                elif t == 'divider_label':
                    self.y = self.build_divider_label(blk, content, m['margin'], self.y)
                else:
                    self.y = self.build_grid(blk, content, m['margin'], self.y)
            elif t == 'bottom_nav':
                pass                                    # 固定带：下面统一摆（不进内容流）
            elif t == 'toast':
                toasts.append(blk)
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

        for blk in navs:
            self.build_nav(blk, self.root)              # 固定带（贴底栏上沿，不进滑动区）
        for blk in footer:
            self.build_actions(blk, self.root, m['margin'], 0)
        for blk in dialogs:
            self.build_dialog(blk, self.root)
        for blk in toasts:
            self.build_toast(blk, self.root)            # 浮层提示：**最后定义 = 最上层**
        # 顺序 = z 顺序：标题 → 内容 → 底导 → 底栏 → 弹窗 → 提示浮层（越往后越上）
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

/*
 * 第 2 批交互块（slider_row / progress_row / input_row / checkbox_row / radio_row /
 * list_item / wheel_picker）的运行期回调——签名出自 knowledge/uicontrols/*.md，未在骨架里
 * 展开（避免签名漂移），需要时把下面注释打开并按业务补实现：
 *
 *   static void onProgressChanged_SeekRowSliderRow1Bar(ZKSeekBar *pSeekBar, int progress) {}
 *   static void onCheckedChanged_CheckRowCheckboxRow2Box(ZKCheckBox *pCheckBox, bool isChecked) {}
 *   static void onCheckedChanged_RadioRowRadioRow3Group(ZKRadioGroup *pGroup, int checkedID) {}
 *   static int  getListItemCount_ListListItem4(const ZKListView *pListView) { return 0; }
 *   static void obtainListItemData_ListListItem4(ZKListView *p, ZKListView::ZKListItem *item, int index) {}
 *   static void onListItemClick_ListListItem4(ZKListView *p, int index, int id) {}
 *   // 滚轮：正中行回读 fi + (h/2 − off)/ih；程序化定位用数据侧平移（见 listview-wheel-picker.md）
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


def collect_edittext_caps(node, out=None):
    """edittext caption 清单（id 51000 段）——check_all #5 要求 onEditTextChanged_<caption> 存在。"""
    out = [] if out is None else out
    for k, v in node.items():
        if isinstance(v, dict) and '__' in k:
            if 51000 <= int(v.get('id', 0)) < 52000 and v.get('caption'):
                out.append(v['caption'])
            collect_edittext_caps(v, out)
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
    edit_caps = collect_edittext_caps(doc)
    if edit_caps:
        body.append('\n// ---- 输入框回调（check_all #5 核对：edittext 必须有 onEditTextChanged_<caption>）----\n')
    for cap in edit_caps:
        body.append('static void onEditTextChanged_%s(const std::string &text) {\n'
                    '    // TODO: %s 输入内容 = text\n}\n' % (cap, cap))
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
    # 图标来源（钟工 2026-10-01：块库图标 = components/icons 资产库，不自绘、不走 emoji 兜底）
    if cmp_.icon_uses:
        tiers = defaultdict(int)
        for u in cmp_.icon_uses:
            tiers[u['tier']] += 1
        pairs = sorted({(u['token'], u['name'], u['size'], u['tier'], u['state'] or '-')
                        for u in cmp_.icon_uses})
        print('  图标来源：components/icons（%d 处 ｜ 档位 %s ｜ %d 种 名×尺寸×态 组合）'
              % (len(cmp_.icon_uses), '、'.join('%d 档 ×%d' % (t, tiers[t])
                                                for t in sorted(tiers)), len(pairs)))
        for tok, nm, sz, tr, st in pairs:
            print('      %-12s → %-24s %dpx（%d 档）state=%s' % (tok, nm, sz, tr, st))
    if cmp_.icon_fallbacks:
        print('  [X] 回退线框 %d 处（目标 0）—— 图标字面量不在 components/icons 里：%s'
              % (len(cmp_.icon_fallbacks),
                 '、'.join('%s@%dpx' % (f['token'], f['size']) for f in cmp_.icon_fallbacks)))
    else:
        print('  回退线框 0 处（全部图标来自 components/icons ✓）')
    for n in cmp_.notes:
        print('  [NOTE] %s' % n)

    if not a.json_only:
        made = cmp_.emit_assets(project)
        print('  出图 %d 张 → %s' % (len(made), os.path.join(project, 'resources', 'images')))
        if not a.no_logic:
            lp = emit_logic(project, a.page, doc)
            print('  logic 骨架 → %s（%d 个按钮回调 + %d 个输入框回调）'
                  % (lp, len(collect_button_caps(doc)), len(collect_edittext_caps(doc))))
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
        # 完整打印（含 unsupported/降级清单）：旧版只打尾部 1500 字，交互块多了之后会把清单头部截掉
        # （表现＝日志里看不到 radiogroup/checkbox 的降级项）。超长时只截中段，头尾都保留。
        if len(rep) > 6000:
            print(rep[:2500] + '\n  ...[中略 %d 字；完整清单请直接跑 json2img --report]...\n' %
                  (len(rep) - 5000) + rep[-2500:])
        else:
            print(rep)
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
