#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 规格指针（DESIGN_SPEC 第 1.1 条）：本文件是**离线渲染器**，必须复现
# `ui_schema.json.renderContract` 的引擎语义（`pic-scale` 拉伸填盒 / `progress-clip`
# 1:1 贴 + `floor` 裁剪 / `thumb-size` 按 PNG 原尺寸 / `rounding` 用 floor）。
# ⚠️ 已知未对齐：`draw_seekbar` 仍在用 `resize(..., NEAREST)` + `round`（= ⛔TWEAK 型偏差），
# 会用 NEAREST 抽掉切图圆角、滑块位置与真机差 4px —— **不要用它的输出做视觉验收**。
"""
json2img.py — FlyThings 布局 json → PNG 离线「引擎等价」渲染器（v0，PIL 像素级）

目标：静止态「所见即所得」。几何 / 颜色 / 图片 / 文字位置按 zkgui 引擎语义还原，
用于设计期与 check 期的离线确认（动态效果：滚动位置、动画、视频 → 不还原，见下方清单）。

────────────────────────────────────────────────────────────────────────
引擎语义（2026-10-01 两条更正，本实现照此）
────────────────────────────────────────────────────────────────────────
1. 控件 = 矩形 position{left,top,width,height} + 背景图或纯色 + 文字 + 子控件；
   **绘制顺序 = json 内的树序**（父先子后；同层按出现顺序，后定义的画在上面）。
   → 实现：直接按 dict 的 key 顺序遍历（json 保持书写顺序），递归子控件。
2. **图 != 矩形时：拉伸填充**（stretch-to-fill 到矩形），不是原样贴、不是居中裁剪。
   → 实现：resize 到矩形（NEAREST）；例外 = `.9.png` 九宫格（引擎走九宫拉伸，见 §九宫格）。
3. 没有 flex / 层叠 / 继承 —— 子控件坐标相对父矩形左上角，不做任何补偿。

单节点绘制顺序（严格）：铺「底色」→ 贴「背景图」→ 画「文字」→ 递归子控件。
  （例：箭头被文字盖住 = 引擎先画背景图、后画文字，本实现同样顺序）
颜色约定：`-1` = 不填充（透明）；`0` = 不透明黑；其它按 `0xRRGGBB`。
有 `backgroundPic` 时，若 `bgColorTab.color0` 有效（≥0）先铺底色再贴图
  （贴图不透明区覆盖底色，图的透明区露出底色）—— 与 §单节点顺序一致。
窗口类用 `backgroundColor`；文本/按钮类用 `bgColorTab.color0`。

────────────────────────────────────────────────────────────────────────
裁剪
────────────────────────────────────────────────────────────────────────
`scrollwindow` / `pagewindow` / `slidewindow` 按自身 rect 裁剪子内容（超出视口裁掉）。
静止态按 json 里的坐标画（内层 window 的负 left/top = 初始偏移，照画不补偿滚动）。

────────────────────────────────────────────────────────────────────────
alignment 解码表（显式表；⚠️ 待校准项单列）
────────────────────────────────────────────────────────────────────────
实测表（真机验证，2026-10-01 提供，务必照抄）：
    36 = 靠左 + 垂直居中    37 = 水平居中 + 垂直居中    38 = 靠右 + 垂直居中
    33 = 顶部对齐           41 = 底部对齐
工程里同时大量在用 `5 / 0 / 1 / 4 / 6 / 2`（在 SmartPanel_HA 里占 91% 的文字控件）：
    TODO(待校准) —— 这 6 个值**没有**真机实测表。本文件给出两种显式解码，`--align-mode` 切换：
      * `measured`（默认）：按位模型解码（h = a & 3，v = (a >> 2) & 3），即
            4 ≡ 36（左中）  5 ≡ 37（中中）  6 ≡ 38（右中）  0 ≡ 左顶  1 ≡ 中顶  2 ≡ 右顶
依据：该位模型对**全部 5 个实测值**都成立（36/37/38/33/41 无一反例），且与项目内
设备实测记录 references/kb/controls.md（2026-08-29 真机校准）及 html2json.py 的
        ALIGN 映射（left→36 / center→37 / right→38）一致；工程里 4/5/6 与 36/37/38 混用同一
版式（同一按钮/标题/返回键既有 36 也有 4）也支持「高位是附加标志位」的解释。
      * `task36`：把这 6 个值一律当 36（靠左 + 垂直居中）—— 即需求方口头给的兜底口径。
两者都会被打印进 unsupported/校准清单，绝不静默。
    👉 待真机基线出来后的动作：对 4/5/6/0/1/2 各出一个对照图，钉死到底哪张表对，
然后把 ALIGN_TABLE 里 `uncalibrated=True` 的项改成实测值。

────────────────────────────────────────────────────────────────────────
v0 能力 / 已知降级（渲染后必打 unsupported 清单，不静默跳过）
────────────────────────────────────────────────────────────────────────
支持：window/textview/button/edittext/scrollwindow/pagewindow/slidewindow/listview/
      seekbar/qrcode/imageanim/videoview；含 .9.png 九宫格、backgroundPic、bgColorTab、
      colorTab、多行 text(\n)+rowSpace、bold/italic 字体变体、按 rect 裁剪。
      **数组子项（2026-10-01 补）：radiogroup.radiobuttons[]（逐项圆点 + 选项文字，选中态走
      pic2 + colorTab.color2）、listview.item + item.subItem[]（按 rows/rowSpacing/itemH 逐行铺，
每行画行底 + 子项图/文本）、checkbox.checked（选中走 pic2；缺 pic2 时叠 components/icons
的 control.check_on）。**
降级：circlebar（近似弧）、listview 运行期数据/滚动（模板行按 rows 铺，obtainListItemData
的数据与滚动不还原）、radiogroup/checkbox 运行期联动（按 json 的 checked 画静止态）、
      rollEnable 滚动文字（只画静止首屏）、imageanim（只画 picTab.pic0 首帧）、
      videoview（黑/底色块）、digitalclock.painter.pointer.diagram.cameraview.slidetext、
      charsetTab 字符图映射不还原。

CLI
     python tools/FlyThings_mcp_open/ui_tools/json2img.py <项目根或 json> \
         [--page main] [--out x.png] [--scale 2] [--font xxx.ttf] [--report]

纪律：本文件是只读渲染器，不改任何工程文件（不 pack、不写 json）。
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from collections import Counter, OrderedDict

try:  # Windows 控制台默认 GBK：保持控制台自身编码，仅把不可编码字符替换掉（不炸）
    sys.stdout.reconfigure(errors='replace')
    sys.stderr.reconfigure(errors='replace')
except Exception as ex:                     # 控制台重配失败不致命，但不静默
    sys.stderr.write('[warn] stdout reconfigure failed: %s\n' % ex)

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception as exc:  # pragma: no cover
    print('[FATAL] 需要 Pillow：pip install pillow  (%s)' % exc)
    raise

__version__ = '0.1.0'

NEAREST = Image.Resampling.NEAREST if hasattr(Image, 'Resampling') else Image.NEAREST

# ============================================================================
# alignment 显式解码表
# ============================================================================
# 值 → (水平, 垂直)：'l'/'c'/'r' + 't'/'c'/'b'
_HC = {0: 'l', 1: 'c', 2: 'r'}
_VC = {0: 't', 1: 'c', 2: 'b'}


def _bit_model(a):
    """位模型：bit0-1 = 水平，bit2-3 = 垂直（bit4/5 为引擎附加标志，不影响对齐）。"""
    return _HC.get(a & 3, 'l'), _VC.get((a >> 2) & 3, 't')


# 实测（真机验证，2026-10-01）—— 这 5 个值是钉死的
ALIGN_MEASURED = {
    36: ('l', 'c'),   # 靠左 + 垂直居中
    37: ('c', 'c'),   # 水平居中 + 垂直居中
    38: ('r', 'c'),   # 靠右 + 垂直居中
    33: ('c', 't'),   # 顶部对齐
    41: ('c', 'b'),   # 底部对齐
}
# TODO(待校准)：5/0/1/4/6/2 无真机实测表。列表里的值是 `measured` 模式（位模型）下的解码。
ALIGN_UNCALIBRATED = {
    4: ('l', 'c'),    # ≡36? 待真机复核
    5: ('c', 'c'),    # ≡37? 待真机复核
    6: ('r', 'c'),    # ≡38? 待真机复核
    0: ('l', 't'),    # 待真机复核
    1: ('c', 't'),    # 待真机复核
    2: ('r', 't'),    # 待真机复核
}
ALIGN_DEFAULT = (36, ('l', 'c'))   # 表外值 → 按 36 处理（左+垂直居中）


class AlignTable:
    """显式解码表 + 校准状态记账。"""

    def __init__(self, mode='measured'):
        self.mode = mode
        self.hits = Counter()          # 值 → 次数
        self.used = {}                 # (page,caption) → (值, 状态)

    def decode(self, a):
        try:
            a = int(a)
        except Exception:
            a = 36
        self.hits[a] += 1
        if a in ALIGN_MEASURED:
            return ALIGN_MEASURED[a], 'measured'
        if a in ALIGN_UNCALIBRATED:
            if self.mode == 'task36':
                return ALIGN_DEFAULT[1], 'uncalibrated(task36→36)'
            return ALIGN_UNCALIBRATED[a], 'uncalibrated(bit)'
        return ALIGN_DEFAULT[1], 'unknown→36'

    def note(self, page, caption, a, status):
        self.used.setdefault((page, caption), (a, status))

    # —— 汇总 ——
    def measured_count(self):
        return sum(n for v, n in self.hits.items() if v in ALIGN_MEASURED)

    def uncalibrated_count(self):
        return sum(n for v, n in self.hits.items() if v in ALIGN_UNCALIBRATED)

    def other_count(self):
        return sum(n for v, n in self.hits.items()
                   if v not in ALIGN_MEASURED and v not in ALIGN_UNCALIBRATED)


# ============================================================================
# 颜色
# ============================================================================
def color_rgba(v, alpha=255):
    """json 颜色 int → RGBA；`-1`(及 0xFFFFFFFF) = 不填充 → None；`0` = 不透明黑。"""
    if v is None:
        return None
    try:
        v = int(v)
    except Exception:
        return None
    if v < 0 or v == 0xFFFFFFFF:
        return None
    v &= 0xFFFFFF
    return ((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF, alpha)


# ============================================================================
# 资源定位
# ============================================================================
def find_asset(pic, proj=None, base_dir=None):
    """图片引用 → 真实文件。顺序：<项目>/resources[/images] → <json目录>[/images] →
    <项目> → <项目>/.fsc|.fun/*/imgout/ui[/images]（打包产物兜底）；再退 .9.png 变体。"""
    if not pic or str(pic).startswith(('http://', 'https://', 'data:')):
        return None
    rel = str(pic).replace('\\', '/').lstrip('/')
    base = os.path.basename(rel)
    roots = []
    if proj:
        roots += [os.path.join(proj, 'resources'), os.path.join(proj, 'resources', 'images'),
                  proj]
    if base_dir:
        roots += [base_dir, os.path.join(base_dir, 'images')]
        p2 = os.path.dirname(os.path.abspath(base_dir))
        if p2 and p2 != proj:
            roots += [os.path.join(p2, 'resources'), os.path.join(p2, 'resources', 'images')]
    if proj:  # 打包产物目录（.fsc/<平台>/imgout/ui、.fun/<平台>/imgout/ui）
        for pat in ('.fsc', '.fun', '.fuse'):
            roots += glob.glob(os.path.join(proj, pat, '*', 'imgout', 'ui')) + \
                     glob.glob(os.path.join(proj, pat, '*', 'imgout', 'ui', 'images'))
    cands = []
    for r in roots:
        cands += [os.path.join(r, rel), os.path.join(r, base)]
        if rel.startswith('images/'):
            cands.append(os.path.join(r, rel[len('images/'):]))
    for c in cands:
        if os.path.isfile(c):
            return os.path.abspath(c)
    for c in cands:  # .9.png 变体
        stem, ext = os.path.splitext(c)
        for alt in (stem.replace('.9', '') + '.9' + ext, stem + '.9' + ext):
            if os.path.isfile(alt):
                return os.path.abspath(alt)
    return None


# ============================================================================
# 九宫格（.9.png）：1px 边框黑线标出可拉伸区（top 线 = 水平，left 线 = 垂直）
# ============================================================================
def _is_guide(px, x, y):
    r, g, b, a = px[x, y]
    return a > 0 and r < 8 and g < 8 and b < 8


def nine_patch(im, W, H):
    """按 .9.png 规格拉伸到 (W,H)；不是合法九宫格 → None。"""
    w, h = im.size
    if w < 4 or h < 4:
        return None
    px = im.load()
    xs = [x for x in range(1, w - 1) if _is_guide(px, x, 0)]
    ys = [y for y in range(1, h - 1) if _is_guide(px, 0, y)]
    if not xs or not ys:
        return None
    content = im.crop((1, 1, w - 1, h - 1))
    cw, ch = content.size
    x0, x1 = max(0, min(xs) - 1), min(cw - 1, max(xs) - 1)
    y0, y1 = max(0, min(ys) - 1), min(ch - 1, max(ys) - 1)
    left, right = x0, cw - 1 - x1
    top, bottom = y0, ch - 1 - y1
    if W - left - right < 0 or H - top - bottom < 0:      # 目标比固定段还小 → 整体缩
        return content.resize((max(1, W), max(1, H)), NEAREST)
    sx = [0, x0, x1 + 1, cw]
    tx = [0, x0, W - right, W]
    sy = [0, y0, y1 + 1, ch]
    ty = [0, y0, H - bottom, H]
    out = Image.new('RGBA', (max(1, W), max(1, H)), (0, 0, 0, 0))
    for j in range(3):
        for i in range(3):
            sb = (sx[i], sy[j], sx[i + 1], sy[j + 1])
            if sb[2] <= sb[0] or sb[3] <= sb[1]:
                continue
            part = content.crop(sb)
            dw, dh = tx[i + 1] - tx[i], ty[j + 1] - ty[j]
            if dw <= 0 or dh <= 0:
                continue
            if part.size != (dw, dh):
                part = part.resize((dw, dh), NEAREST)
            out.paste(part, (tx[i], ty[j]), part)
    return out


# ============================================================================
# 报告
# ============================================================================
class Report:
    """unsupported / 降级 / 缺资源 / 拉伸 的如实记账（不静默跳过）。"""

    def __init__(self):
        self.items = OrderedDict()      # (page,type,field,note) → {count, examples[]}
        self.missing = OrderedDict()    # (page,pic) → {count, examples[]}
        self.stretches = OrderedDict()  # (page,type,pic,size) → count
        self.nines = OrderedDict()      # 九宫格命中

    def _bump(self, store, key, example):
        e = store.setdefault(key, {'count': 0, 'examples': []})
        e['count'] += 1
        if example and example not in e['examples'] and len(e['examples']) < 4:
            e['examples'].append(example)

    def unsupported(self, page, ctype, caption, field, note):
        self._bump(self.items, (page, ctype, field, note),
                   '%s%s' % (ctype, ('/' + caption) if caption else ''))

    def miss(self, page, pic, caption):
        self._bump(self.missing, (page, pic), caption or '')

    def stretch(self, page, ctype, pic, size, target):
        k = (page, ctype, pic, '%dx%d→%dx%d' % (size[0], size[1], target[0], target[1]))
        self.stretches[k] = self.stretches.get(k, 0) + 1

    def nine(self, page, pic):
        self.nines[page + '|' + pic] = self.nines.get(page + '|' + pic, 0) + 1

    def as_dict(self):
        return {
            'unsupported': [{'page': k[0], 'type': k[1], 'field': k[2], 'note': k[3],
                             'count': v['count'], 'examples': v['examples']}
                            for k, v in self.items.items()],
            'missing_assets': [{'page': k[0], 'ref': k[1], 'count': v['count'],
                                'examples': v['examples']} for k, v in self.missing.items()],
            'stretched': [{'page': k[0], 'type': k[1], 'ref': k[2], 'size': k[3], 'count': v}
                          for k, v in self.stretches.items()],
            'nine_patch': dict(self.nines),
        }


# ============================================================================
# 渲染器
# ============================================================================
CLIP_TYPES = {'scrollwindow', 'pagewindow', 'slidewindow'}
# 键名不是子控件（容器/属性块），不进树序
BLOCK_KEYS = {'position', 'resolution', 'colorTab', 'bgColorTab', 'picTab', 'thumb',
              'item', 'subItem', 'items', 'radiobuttons', 'iconSize', 'padding', 'size',
              'charsetTab', 'iconPosition', 'textPosition',
              'progressPic', 'backgroundPic', 'normalPic', 'pressedPic', 'selectedPic',
              'disabledPic', 'videoPath', 'src'}

# ─── components/icons 资产库（离线渲染的图标兜底源；与 templates/ui_blocks/iconlib.py 同一库）───
#注：json2img 有两份副本（`tools/ui_tools/` 与 `tools/FlyThings_mcp_open/ui_tools/`），
#相对位置不同 → 按候选路径逐个探（认 catalog.json 为准），避免换个副本就找不到库。
def _find_icons_lib():
    here = os.path.dirname(os.path.abspath(__file__))
    cands = []
    env = os.environ.get('FLYTHINGS_ICONS_LIB')
    if env:
        cands.append(env)
    for up in (1, 2, 3):
        base = os.path.join(here, *(['..'] * up))
        cands.append(os.path.join(base, 'components', 'icons'))
        for sib in sorted(glob.glob(os.path.join(base, '*', 'components', 'icons'))):
            cands.append(sib)
    for c in cands:
        if os.path.isfile(os.path.join(c, 'catalog.json')):
            return os.path.abspath(c)
    return os.path.abspath(cands[0] if cands else os.path.join(here, 'components', 'icons'))


ICONS_LIB = _find_icons_lib()
ICON_TIERS = (56, 24, 22)
_icon_cache = {}


def _recolor_alpha(im, rgb):
    """按 alpha 换色（components/icons 库口径：RGB 恒等于颜色、alpha = 覆盖率）。"""
    a = im.convert('RGBA').split()[3]
    out = Image.new('RGBA', im.size, (int(rgb[0]), int(rgb[1]), int(rgb[2]), 0))
    out.putalpha(a)
    return out


def icon_asset(name, state='', box=None):
    """语义名（如 control.check）+ 状态（on/off）→ components/icons 的现成产物。

命中规则：`out/<档>/ic_<分类>_<图标>[_<状态>].png`；档位优先取 ≤ 盒尺寸的最大档
    （**不放大**：宁可小一号，也不把库产图拉大）。返回 (path, tier)；查不到 → (None, None)。
    """
    key = (name, state, box)
    if key in _icon_cache:
        return _icon_cache[key]
    res = (None, None)
    if name and '.' in str(name):
        cat, icon = str(name).split('.', 1)
        fn = 'ic_%s_%s%s.png' % (cat, icon, ('_' + state) if state else '')
        tiers = list(ICON_TIERS)
        if box:
            tiers.sort(key=lambda t: (0 if t <= int(box) else 1, -t if t <= int(box) else t))
        for t in tiers:
            p = os.path.join(ICONS_LIB, 'out', str(t), fn)
            if os.path.isfile(p):
                res = (p, t)
                break
    _icon_cache[key] = res
    return res


def children_of(node):
    """按 json key 顺序取子控件（有 position 的 dict，且键名不是属性块）。"""
    out = []
    for k, v in node.items():
        if k in BLOCK_KEYS:
            continue
        if isinstance(v, dict) and isinstance(v.get('position'), dict):
            out.append((k, v))
    return out


def ctype_of(name):
    return name.split('__')[0] if '__' in name else name


class Renderer:
    def __init__(self, project=None, json_path=None, font_path=None, align_mode='measured',
                 report=None, verbose=True):
        self.proj = project
        self.json_dir = os.path.dirname(os.path.abspath(json_path)) if json_path else None
        self.font_path = font_path
        self.report = report or Report()
        self.verbose = verbose
        self.align = AlignTable(align_mode)
        self.page = os.path.splitext(os.path.basename(json_path))[0] if json_path else '?'
        self._font_cache = {}
        self._img_cache = {}
        self._asset_miss_logged = set()
        self.bold_path = self._find_bold_variant()
        self.window_fill = Counter()

    # ---------- 字体 ----------
    def _font_dirs(self):
        dirs = []
        if self.proj:
            dirs.append(os.path.join(self.proj, 'font'))
            dirs.append(os.path.join(self.proj, 'resources', 'font'))
        if self.json_dir:
            dirs.append(os.path.join(self.json_dir, 'font'))
        return [d for d in dirs if os.path.isdir(d)]

    def _easyui_font_order(self):
        """<项目>/.fsc|.fun/<平台>/launch/EasyUI.cfg 的 font 字段（冒号分隔）→ basename 列表。"""
        out = []
        if not self.proj:
            return out
        cfgs = []
        for pat in ('.fsc', '.fun', '.fuse'):
            cfgs += glob.glob(os.path.join(self.proj, pat, '*', 'launch', 'EasyUI.cfg'))
        for c in cfgs:
            try:
                d = json.load(open(c, encoding='utf-8'))
            except Exception as ex:
                sys.stderr.write('[warn] 读不到 %s（字库候选跳过）：%s\n' % (c, ex))
                continue
            for p in str(d.get('font', '')).split(':'):
                b = os.path.basename(p.strip())
                if b:
                    out.append(b)
        return out

    def resolve_font(self):
        """字体优先级：--font > EasyUI.cfg 顺序里第一个存在的 > font/ 里第一个 *.ttf > **系统中文兜底**。

        ⚠️ 最后一档是 2026-10-05 加的：模板工程（`templates/DemoControls_*`）里**不带字体**，
        于是整页中文渲染成方框 —— 离线图"结构对但读不出字"，等于没法验收文案。
        兜底只保证**可读**，不保证与设备同度量，所以会如实记一条 unsupported（不静默）。
        """
        if self.font_path:
            return os.path.abspath(self.font_path) if os.path.isfile(self.font_path) else None
        dirs = self._font_dirs()
        if not dirs:
            if self.proj:
                hits = glob.glob(os.path.join(self.proj, '**', '*.ttf'), recursive=True)
                hits = [h for h in hits if os.sep + '.git' not in h][:50]
                if hits:
                    return os.path.abspath(sorted(hits)[0])
            return self._system_font_fallback()
        for b in self._easyui_font_order():
            for d in dirs:
                p = os.path.join(d, b)
                if os.path.isfile(p):
                    return os.path.abspath(p)
        # 兜底：注意 HanSansLight.ttf 在 SmartPanel_HA 里只有 2KB（子集占位），
        # 故取「文件最大的 ttf」而不是字典序第一个，避免选到残缺字体。
        cands = []
        for d in dirs:
            cands += glob.glob(os.path.join(d, '*.ttf')) + glob.glob(os.path.join(d, '*.ttc'))
        cands = [c for c in cands if os.path.getsize(c) > 4096]
        if cands:
            return os.path.abspath(max(cands, key=os.path.getsize))
        return self._system_font_fallback()

    def _system_font_fallback(self):
        """工程无字体时的**系统中文兜底**（只保证可读，并如实记账）。"""
        for p in (r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf',
                  r'C:\Windows\Fonts\simsun.ttc',
                  '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                  '/System/Library/Fonts/PingFang.ttc'):
            if os.path.isfile(p):
                self.report.unsupported(
                    self.page, 'font', os.path.basename(p), 'font',
                    '工程内无字体 → 用**系统字体**兜底渲染（保证中文可读；'
                    '字形度量不保证与设备一致，交付前请以真机为准）')
                return os.path.abspath(p)
        self.report.unsupported(
            self.page, 'font', '', 'font',
            '工程内无字体且本机找不到系统中文字体 → 中文会渲染成方框（结构仍可验收）')
        return None

    def _find_bold_variant(self):
        for d in self._font_dirs():
            for pat in ('*Bold*.ttf', '*-Bold.ttf', '*bold*.ttf'):
                h = sorted(glob.glob(os.path.join(d, pat)))
                if h:
                    return os.path.abspath(h[0])
        return None

    def font(self, size, bold=False, italic=False):
        size = max(1, int(round(size)))
        path = self.font_path
        if bold and self.bold_path:
            path = self.bold_path
        key = (path, size)
        if key in self._font_cache:
            return self._font_cache[key]
        f = None
        if path and os.path.isfile(path):
            try:
                f = ImageFont.truetype(path, size)
            except Exception:
                f = None
        if f is None:
            try:
                f = ImageFont.load_default(size)
            except Exception:
                f = ImageFont.load_default()
        self._font_cache[key] = f
        return f

    # ---------- 图片 ----------
    def load_pic(self, pic):
        if pic in self._img_cache:
            return self._img_cache[pic]
        p = find_asset(pic, self.proj, self.json_dir)
        im = None
        if p:
            try:
                im = Image.open(p).convert('RGBA')
            except Exception:
                im = None
        self._img_cache[pic] = im
        return im

    def draw_pic(self, img, pic, x, y, w, h, ctype, caption):
        """按引擎语义把图拉伸填充到矩形（.9.png 走九宫）。"""
        im = self.load_pic(pic)
        if im is None:
            key = (self.page, pic)
            if key not in self._asset_miss_logged:
                self._asset_miss_logged.add(key)
                self.report.miss(self.page, pic, caption)
            return
        src = im
        if os.path.basename(str(pic)).lower().endswith('.9.png'):
            np = nine_patch(im, w, h)
            if np is not None:
                src = np
                self.report.nine(self.page, pic)
            else:
                self.report.unsupported(self.page, ctype, caption, 'backgroundPic(.9)',
                                        '九宫格边框线缺失 → 退化为整体拉伸')
                src = im.resize((max(1, w), max(1, h)), NEAREST)
        elif im.size != (w, h):
            if w > 0 and h > 0:
                src = im.resize((max(1, w), max(1, h)), NEAREST)
                self.report.stretch(self.page, ctype, pic, im.size, (w, h))
        paste_rgba(img, src, x, y)

    # ---------- 文字 ----------
    def draw_text(self, img, node, x, y, w, h, ctype, caption):
        text = node.get('text')
        if text is None:
            text = node.get('caption') if ctype not in ('window', 'qrcode') and False else None
        self._draw_label(img, node, node.get('text') or '', x, y, w, h, ctype, caption)

    def _draw_label(self, img, node, text, x, y, w, h, ctype, caption, color=None,
                    fontsize=None):
        text = '' if text is None else str(text)
        if not text:
            return
        if text.startswith('@'):
            self.report.unsupported(self.page, ctype, caption, 'text',
                                    'i18n 引用 %s → 未解析（渲染期不读 .tr）' % text[:24])
            return
        if '\r' in text:
            text = text.replace('\r\n', '\n').replace('\r', '\n')
        fs = fontsize if fontsize else node.get('fontSize') or 16
        col = color if color is not None else node.get('colorTab', {}).get('color0')
        rgba = color_rgba(col)
        if rgba is None:
            self.report.unsupported(self.page, ctype, caption, 'colorTab.color0',
                                    '颜色 -1/缺省 → 不画文字')
            return
        if node.get('rollEnable'):
            self.report.unsupported(self.page, ctype, caption, 'rollEnable',
                                    '滚动文字 → 静止态按首屏绘制（不回滚）')
        if node.get('charsetTab'):
            self.report.unsupported(self.page, ctype, caption, 'charsetTab',
                                    '字符图映射 → 未还原（按字体绘制）')
        if node.get('bold') and not self.bold_path:
            self.report.unsupported(self.page, ctype, caption, 'bold',
                                    '无 *Bold*.ttf 变体 → 用同字体')
        if node.get('italic'):
            self.report.unsupported(self.page, ctype, caption, 'italic',
                                    '无斜体变体 → 用同字体')
        f = self.font(fs, bool(node.get('bold')))
        a = node.get('alignment', 36)
        (ha, va), status = self.align.decode(a)
        self.align.note(self.page, caption, a, status)
        if status.startswith('uncalibrated') or status.startswith('unknown'):
            self.report.unsupported(self.page, ctype, caption, 'alignment=%s' % a, status)

        try:
            ascent, descent = f.getmetrics()
        except Exception:
            ascent, descent = int(fs), int(fs * 0.25)
        glyph_h = ascent + descent
        lines = text.split('\n')
        rs = node.get('rowSpace')
        try:
            line_h = int(rs) if rs and int(rs) > 0 else int(round(fs * 1.2))
        except Exception:
            line_h = int(round(fs * 1.2))
        block_h = line_h * (len(lines) - 1) + glyph_h
        if va == 't':
            y0 = 0
        elif va == 'c':
            y0 = int(round((h - block_h) / 2.0))
        else:
            y0 = h - block_h

        # 单独图层绘制再合成，保证抗锯齿边缘正确混合
        layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for i, ln in enumerate(lines):
            try:
                lw = d.textlength(ln, font=f)
            except Exception:
                lw = len(ln) * fs * 0.6
            if ha == 'l':
                lx = 0
            elif ha == 'c':
                lx = int(round((w - lw) / 2.0))
            else:
                lx = int(round(w - lw))
            ly = y0 + i * line_h + int(round((line_h - glyph_h) / 2.0))
            try:
                d.text((x + lx, y + ly), ln, font=f, fill=rgba, anchor='la')
            except Exception:
                d.text((x + lx, y + ly), ln, font=f, fill=rgba)
        img.alpha_composite(layer)

    # ---------- 单节点 ----------
    def draw_self(self, img, node, x, y, w, h, ctype, caption):
        """底色 → 背景图 → 文字（+ 专有控件）。"""
        if w <= 0 or h <= 0:
            self.report.unsupported(self.page, ctype, caption, 'position',
                                    '宽高 <= 0 → 跳过（%dx%d）' % (w, h))
            return
        # ① 底色
        bg = node.get('bgColorTab', {}).get('color0') if isinstance(node.get('bgColorTab'), dict) else None
        if bg is None or int(bg) < 0:
            bg = node.get('backgroundColor', -1)     # window/qrcode/videoview 用这个
        rgba = color_rgba(bg)
        if rgba:
            ImageDraw.Draw(img).rectangle([x, y, x + w - 1, y + h - 1], fill=rgba)
            self.window_fill[ctype] += 1
        # ② 背景图：backgroundPic > picTab.pic0（按钮常态图）
        #    checkbox 例外：勾选态走 _draw_marker（pic0/pic2 按 checked 切；它自己会画）
        pic = node.get('backgroundPic')
        if not pic and ctype != 'checkbox':
            ptab = node.get('picTab') if isinstance(node.get('picTab'), dict) else {}
            for k in ('pic0', 'normalPic', 'bgPic'):
                if ptab.get(k):
                    pic = ptab[k]
                    self.report.unsupported(self.page, ctype, caption, 'picTab.%s' % k,
                                            '按背景图绘制（仅常态；按下/选中态不还原）')
                    break
        if pic:
            self.draw_pic(img, pic, x, y, w, h, ctype, caption)
        # ③ 文字 / 专有控件
        if ctype == 'edittext':
            self.draw_edittext(img, node, x, y, w, h, caption)
        elif ctype == 'qrcode':
            self.draw_qrcode(img, node, x, y, w, h, caption)
        elif ctype == 'seekbar':
            self.draw_seekbar(img, node, x, y, w, h, caption)
        elif ctype == 'circlebar':
            self.draw_circlebar(img, node, x, y, w, h, caption)
        elif ctype == 'videoview':
            self.report.unsupported(self.page, ctype, caption, 'videoview',
                                    '视频画面 → 静止态只铺底色（不渲染视频帧）')
        elif ctype == 'imageanim':
            self.report.unsupported(self.page, ctype, caption, 'imageanim',
                                    '帧动画 → 只画 picTab.pic0 首帧')
        elif ctype == 'digitalclock':
            self.report.unsupported(self.page, ctype, caption, 'digitalclock',
                                    '数字时钟（运行期时间）→ 静止态不画')
        elif ctype == 'radiogroup':
            self.draw_radiogroup(img, node, x, y, w, h, caption)
        elif ctype == 'checkbox':
            self.draw_checkbox(img, node, x, y, w, h, caption)
        elif ctype in ('painter', 'pointer', 'diagram', 'cameraview', 'slidetext'):
            self.report.unsupported(self.page, ctype, caption, ctype,
                                    'v0 未专有实现 → 通用兜底（底色+背景图+文字）')
            self.draw_text(img, node, x, y, w, h, ctype, caption)
        else:
            self.draw_text(img, node, x, y, w, h, ctype, caption)

    # ---------- 专有 ----------
    def draw_edittext(self, img, node, x, y, w, h, caption):
        text = node.get('text') or ''
        hint = node.get('hintText') or ''
        if text:
            if node.get('password') or node.get('textType') in (1, 2):
                self.report.unsupported(self.page, 'edittext', caption, 'password/textType',
                                        '密码态 → 用圆点掩码（真实掩码字符未实测）')
                text = '●' * len(str(text))
            self._draw_label(img, node, text, x, y, w, h, 'edittext', caption,
                             color=node.get('colorTab', {}).get('color0') or node.get('textColor'))
        elif hint:
            self.report.unsupported(self.page, 'edittext', caption, 'hintText',
                                    '空文本 → 画 hintText（hintTextColor）')
            self._draw_label(img, node, hint, x, y, w, h, 'edittext', caption,
                             color=node.get('hintTextColor'))
        if node.get('maxLength') is not None:
            pass

    def draw_qrcode(self, img, node, x, y, w, h, caption):
        s = node.get('codeStr') or ''
        pad = node.get('padding') or 0
        try:
            pad = max(0, int(pad))
        except Exception:
            pad = 0
        tw, th = max(1, w - 2 * pad), max(1, h - 2 * pad)
        if not s:
            self.report.unsupported(self.page, 'qrcode', caption, 'codeStr',
                                    '内容为空 → 不画二维码')
            return
        qr_img = None
        try:
            import io
            import segno
            buf = io.BytesIO()
            segno.make(s, error='m').save(buf, kind='png', scale=1, border=2)
            buf.seek(0)
            qr_img = Image.open(buf).convert('RGBA')
        except Exception as exc:
            self.report.unsupported(self.page, 'qrcode', caption, 'codeStr',
                                    'segno 不可用/编码失败（%s）→ 只铺白底' % type(exc).__name__)
            ImageDraw.Draw(img).rectangle([x + pad, y + pad, x + w - pad - 1, y + h - pad - 1],
                                          fill=(255, 255, 255, 255))
            return
        qr_img = qr_img.resize((tw, th), NEAREST)   # NEAREST：避免模块糊边
        paste_rgba(img, qr_img, x + pad, y + pad)
        self.report.unsupported(self.page, 'qrcode', caption, 'codeStr',
                                'segno 现场生成（静区/白底口径未实测：按 padding 内缩、白底随图）')

    def draw_seekbar(self, img, node, x, y, w, h, caption):
        """按 `ui_schema.json.renderContract` 的引擎语义渲染（2026-10-05 按规格重写）。

        改前它用的是**与真机不符的模型**（实测归因，见 `CONSOLIDATION_VISUAL.md`）：
          · 填充宽用 `round`，而引擎是 **`floor`** → 恒差 1px；
          · 填充图走 `resize(..., NEAREST)`，而引擎是 **1:1 原样贴 + 裁剪** ——
            NEAREST 会把切图圆角**抽掉**（10% 进度时圆角 100% 消失），即"离线看着对、真机不对"；
          · 滑块用 `thumb.size` 缩放，而引擎**按 PNG 原尺寸**画（`thumb.size` 实测被忽略）；
          · 滑块左沿用 `round(w·frac) − tw/2`，而引擎是 **`floor((w−tw)·frac)`**（三套约定里第三套）。
        后果：拿它的输出做视觉验收会**掩盖真问题**（这也是它此前被列为"唯一会说谎的部件"的原因）。
        现在四条一律照规格：`pic-scale` / `progress-clip` / `thumb-size` / `rounding`。
        """
        mx = node.get('max') or 100
        prog = node.get('defProgress')
        if prog is None:
            prog = 0
        try:
            frac = max(0.0, min(1.0, float(prog) / float(mx or 100)))
        except Exception:
            frac = 0.0
        ori = node.get('orientation', 0)   # 0 = 水平（项目实测），1 = 垂直
        # ① 轨道：引擎**拉伸填满控件盒**（renderContract.pic-scale）→ 直接按盒尺寸贴
        bgpic = node.get('backgroundPic')
        if bgpic:
            self.draw_pic(img, bgpic, x, y, w, h, 'seekbar', caption)
        # ② 填充：1:1 原样贴 + 按 floor(盒宽×进度/max) 裁剪（renderContract.progress-clip）
        #    ⚠️ 不 resize：图若比盒窄，引擎也是 1:1 贴（露轨道），不许缩放着把内容撑满
        ppic = node.get('progressPic')
        layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
        if ppic:
            im = self.load_pic(ppic)
            if im is None:
                self.report.miss(self.page, ppic, caption)
            else:
                if ori == 0:
                    cut_w, cut_h = int(math.floor(w * frac)), h
                else:
                    cut_w, cut_h = w, int(math.floor(h * frac))
                iw, ih = im.size
                if (iw, ih) != (w, h):
                    # 图 != 控件盒 → 按规格这是**要求错**（引擎只裁剪不缩放）：如实记账，别悄悄缩放
                    self.report.stretch(self.page, 'seekbar', ppic, im.size, (w, h))
                if str(ppic).endswith('.9.png'):
                    nn = nine_patch(im, min(iw, max(1, cut_w)), min(ih, max(1, cut_h)))
                    if nn is not None:
                        paste_rgba(layer, nn, x, y)
                else:
                    # 1:1 贴、按进度裁剪到左上角（引擎行为）；裁剪后不足盒宽的部分保持透明 = 露轨道
                    cw, ch = min(iw, max(0, cut_w)), min(ih, max(0, cut_h))
                    if cw > 0 and ch > 0:
                        paste_rgba(layer, im.crop((0, 0, cw, ch)), x, y)
        # ③ 滑块：按 **PNG 原尺寸**画（renderContract.thumb-size）；左沿 floor((盒宽−图宽)×进度/max)
        thumb = node.get('thumb') if isinstance(node.get('thumb'), dict) else None
        if thumb and (thumb.get('normalPic') or thumb.get('pressedPic')):
            tp = thumb.get('normalPic') or thumb.get('pressedPic')
            size = thumb.get('size') or {}
            dw, dh = int(size.get('width') or 0), int(size.get('height') or 0)
            tim = self.load_pic(tp)
            if tim is None:
                self.report.miss(self.page, tp, caption)
            else:
                tw, th = tim.size                      # ★ 尺寸由 PNG 决定，不是 json
                if dw and dh and (dw, dh) != (tw, th):
                    self.report.unsupported(
                        self.page, 'seekbar', caption, 'thumb.size',
                        '声明 %dx%d 与 PNG %dx%d 不一致 → 真机按 **PNG** 画（thumb.size 被忽略）'
                        % (dw, dh, tw, th))
                if ori == 0:
                    tx = int(math.floor((w - tw) * frac))
                    ty = int((h - th) // 2)            # 盒高 < 图高 → 居中裁（负值即被裁）
                else:
                    tx = int((w - tw) // 2)
                    ty = int(math.floor((h - th) * frac))
                paste_rgba(layer, tim, x + tx, y + ty)
        img.alpha_composite(layer)
        self.report.unsupported(self.page, 'seekbar', caption, 'defProgress',
                                '进度静止态（defProgress/max=%.0f%%），拖动/动画不还原' % (frac * 100))

    def draw_circlebar(self, img, node, x, y, w, h, caption):
        mx = node.get('max') or 100
        prog = node.get('progress')
        if prog is None:
            prog = node.get('defProgress') or 0
        try:
            frac = max(0.0, min(1.0, float(prog) / float(mx or 100)))
        except Exception:
            frac = 0.0
        max_angle = node.get('maxAngle') or 360
        ring = color_rgba(node.get('bgColorTab', {}).get('color0'))
        fill = color_rgba(node.get('colorTab', {}).get('color0'))
        d = ImageDraw.Draw(img)
        pad = max(1, int(round(min(w, h) * 0.04)))     # 环宽近似：4% 直径
        box = [x + pad, y + pad, x + w - 1 - pad, y + h - 1 - pad]
        start = -90.0
        if ring:
            d.arc(box, start, start + max_angle, fill=ring, width=pad, )
        if fill:
            d.arc(box, start, start + max_angle * frac, fill=fill, width=pad)
        self.report.unsupported(self.page, 'circlebar', caption, 'progress',
                                '环宽/起始角为近似（4%%直径、-90° 起顺时针），角度按 %s*%.0f%%'
                                % (max_angle, frac * 100))

    # ---------- 状态化标记（checkbox / radiobutton 共用） ----------
    def _marker_box(self, node, x, y, w, h):
        """标记图/勾的盒 = iconPosition（缺省 → 控件盒）。"""
        box = node.get('iconPosition') if isinstance(node.get('iconPosition'), dict) else None
        if box:
            return (x + int(box.get('left') or 0), y + int(box.get('top') or 0),
                    int(box.get('width') or 0) or w, int(box.get('height') or 0) or h)
        return (x, y, w, h)

    def _draw_marker(self, img, node, bx, by, bw, bh, on, ctype, caption):
        """画状态化标记图，返回用了哪张图（引擎口径：pic0=常态 / pic2=选中态）：

        'on' = 用了 pic2（选中态图）；'off' = 只剩 pic0/pic1（常态图，选中态图形缺失）；
        None = 模板里没有任何可用图。调用方据此决定是否兜底（如 checkbox 叠白勾）。
        """
        ptab = node.get('picTab') if isinstance(node.get('picTab'), dict) else {}
        if on:
            if ptab.get('pic2'):
                self.draw_pic(img, ptab['pic2'], bx, by, bw, bh, ctype, caption)
                return 'on'
            pic = ptab.get('pic1') or ptab.get('pic0')
            if pic:
                self.draw_pic(img, pic, bx, by, bw, bh, ctype, caption)
                return 'off'
            return None
        pic = ptab.get('pic0') or ptab.get('pic1')
        if pic:
            self.draw_pic(img, pic, bx, by, bw, bh, ctype, caption)
            return 'off'
        return None

    def draw_checkbox(self, img, node, x, y, w, h, caption):
        """checkbox.checked：选中走 pic2（compose 把 `control.check` 的白勾烘在 pic2 里）；

模板缺 pic2 / 图加载不到 → 叠 `components/icons` 的 control.check_on（**只缩不放**）。
勾色按盒底亮度二选一（暗底白勾 / 亮底用 colorTab.color0）——否则白勾落在浅灰盒
上会“看不见”（fixture 实测）。两者都没有 → 记 unsupported（不静默）。
        """
        checked = bool(node.get('checked'))
        bx, by, bw, bh = self._marker_box(node, x, y, w, h)
        mark = self._draw_marker(img, node, bx, by, bw, bh, checked, 'checkbox', caption)
        if not checked:
            pass
        elif mark == 'on':
            pass                                      # pic2 自带勾（compose 口径）
        else:
            p, tier = icon_asset('control.check', 'on', bw)
            ic = None
            if p:
                try:
                    ic = Image.open(p).convert('RGBA')
                except Exception:                                     # noqa: BLE001
                    ic = None
            if ic is not None:
                if ic.size[0] > bw or ic.size[1] > bh:                # 库档比盒大 → 缩到盒（只缩不放）
                    ic = ic.resize((bw, bh), NEAREST)
                col = (node.get('colorTab') or {}).get('color0')
                luma = self._box_luma(img, bx, by, bw, bh)
                if luma is not None and luma >= 140:
                    rgb = color_rgba(col)[:3] if col is not None and int(col) >= 0 else (51, 51, 51)
                    ic = _recolor_alpha(ic, rgb)
                paste_rgba(img, ic, bx + (bw - ic.size[0]) // 2, by + (bh - ic.size[1]) // 2)
                self.report.unsupported(self.page, 'checkbox', caption, 'checked',
                                        '模板缺 pic2 → 勾用 components/icons 的 '
                                        'control.check_on（%d 档，只缩不放；勾色按底亮度）叠加'
                                        % tier)
            else:
                self.report.unsupported(self.page, 'checkbox', caption, 'checked',
                                        '选中态无图可用（pic2 缺 + 图标库无 control.check_on）')
        self.draw_text(img, node, x, y, w, h, 'checkbox', caption)

    def _box_luma(self, img, x, y, w, h):
        """盒区可见像素的平均亮度（勾色选择用；无可见像素 → None）。"""
        try:
            box = img.crop((int(x), int(y), int(x + w), int(y + h))).convert('RGBA')
        except Exception:                                             # noqa: BLE001
            return None
        px = list(box.getdata())
        vals = [(r * 299 + g * 587 + b * 114) // 1000 for r, g, b, a in px if a > 10]
        return (sum(vals) / len(vals)) if vals else None

    def draw_radiogroup(self, img, node, x, y, w, h, caption):
        """radiogroup.radiobuttons[]：逐项画圆点（pic0 常态 / pic2 选中）+ 选项文字。

选中文字色走 colorTab.color2（无则 color0）——与 compose.make_radiogroup 同口径。
        """
        rbs = node.get('radiobuttons')
        if not isinstance(rbs, list) or not rbs:
            self.report.unsupported(self.page, 'radiogroup', caption, 'radiobuttons',
                                    '无选项子项（radiobuttons 空）→ 选项区空白')
            return
        n = 0
        for rb in rbs:
            if not isinstance(rb, dict):
                continue
            p = rb.get('position') or {}
            rx, ry = x + int(p.get('left') or 0), y + int(p.get('top') or 0)
            rw, rh = int(p.get('width') or w), int(p.get('height') or h)
            on = bool(rb.get('checked'))
            bx, by, bw, bh = self._marker_box(rb, rx, ry, rw, rh)
            mark = self._draw_marker(img, rb, bx, by, bw, bh, on, 'radiobutton',
                                     rb.get('caption') or caption)
            if mark is None:
                self.report.unsupported(self.page, 'radiobutton',
                                        rb.get('caption') or caption, 'picTab',
                                        '无 pic0/pic2 → 不画圆点（只画选项文字）')
            elif on and mark != 'on':
                self.report.unsupported(self.page, 'radiobutton',
                                        rb.get('caption') or caption, 'picTab.pic2',
                                        '缺选中态图 pic2 → 选中项圆点与未选中同形（真机同）')
            col = rb.get('colorTab') if isinstance(rb.get('colorTab'), dict) else {}
            color = col.get('color2') if on else None
            if color is None or int(color) < 0:
                color = col.get('color0')
            tp = rb.get('textPosition') if isinstance(rb.get('textPosition'), dict) else None
            txt = rb.get('text') or ''
            if tp:
                self._draw_label(img, rb, txt, rx + int(tp.get('left') or 0),
                                 ry + int(tp.get('top') or 0),
                                 int(tp.get('width') or rw), int(tp.get('height') or rh),
                                 'radiobutton', rb.get('caption') or caption, color=color)
            else:
                self._draw_label(img, rb, txt, rx, ry, rw, rh, 'radiobutton',
                                 rb.get('caption') or caption, color=color)
            n += 1
        self.report.unsupported(self.page, 'radiogroup', caption, 'runtimeState',
                                '%d 个选项按 checked 画静止态（组内联动/点击态不还原）' % n)

    def draw_listview(self, img, node, x, y, w, h, caption):
        """listview：按 rows / rowSpacing / itemH(=item.position.height) 逐行铺模板。

每行 = item 自身（底色 / 背景图 / 文字）+ 其 subItem[]（各自 iconPosition /
        textPosition / picTab 的图与文本）；列数走 cols/colSpacing。
运行期数据（obtainListItemData 填行）与滚动位置不还原——模板无文本时如实记账。
        """
        item = node.get('item') if isinstance(node.get('item'), dict) else None
        if not item:
            self.report.unsupported(self.page, 'listview', caption, 'item',
                                    '无 item 模板 → 只铺底色')
            return
        ipos = item.get('position', {})
        cw = int(ipos.get('width') or w) or w
        ch = int(ipos.get('height') or h) or h                # ch == itemH（引擎口径）
        cols = int(node.get('cols') or 0) or max(1, w // max(1, cw))
        cs = int(node.get('colSpacing') or 0)
        rs = int(node.get('rowSpacing') or 0)
        rows = int(node.get('rows') or 0) or max(1, h // max(1, ch + rs))
        n, ntxt = 0, 0
        sub = Image.new('RGBA', img.size, (0, 0, 0, 0))
        for r in range(rows):
            for c in range(cols):
                cx = x + c * (cw + cs)
                cy = y + r * (ch + rs)
                if cx >= x + w or cy >= y + h:
                    continue
                n += 1
                self.draw_self(sub, item, cx, cy, cw, ch, 'item',
                               item.get('caption') or caption)
                if item.get('text'):
                    ntxt += 1
                for si in (item.get('subItem') or []):
                    if not isinstance(si, dict):
                        continue
                    sp = si.get('position', {})
                    self.draw_self(sub, si, cx + int(sp.get('left') or 0),
                                   cy + int(sp.get('top') or 0),
                                   int(sp.get('width') or cw), int(sp.get('height') or ch),
                                   'subitem', si.get('caption') or '')
                    if si.get('text'):
                        ntxt += 1
        img.alpha_composite(sub)
        if ntxt:
            note = ('模板行 %d 行 × %d 列（itemH=%d + rowSpacing=%d 铺行；%d 处文本已画）；'
                    '运行期数据/滚动不还原' % (n, cols, ch, rs, ntxt))
        else:
            note = ('模板行 %d 行 × %d 列（itemH=%d + rowSpacing=%d 铺行；行底+子项图已画）；'
                    '模板无行文本（运行期 obtainListItemData 填行）+ 滚动不还原'
                    % (n, cols, ch, rs))
        self.report.unsupported(self.page, 'listview', caption, 'runtimeRows', note)

    def draw_slidewindow(self, img, node, x, y, w, h, caption):
        items = node.get('items') or []
        cols = int(node.get('cols') or 1) or 1
        rows = int(node.get('rows') or 1) or 1
        pad = node.get('padding') if isinstance(node.get('padding'), dict) else {}
        pt, pb = int(pad.get('paddingTop') or 0), int(pad.get('paddingBottom') or 0)
        pl, pr = int(pad.get('paddingLeft') or 0), int(pad.get('paddingRight') or 0)
        iw = int((node.get('iconSize') or {}).get('width') or 40)
        ih = int((node.get('iconSize') or {}).get('height') or 40)
        fs = node.get('fontSize') or 12
        layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
        cw = (w - pl - pr) // cols
        chh = (h - pt - pb) // rows
        for idx, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            r, c = divmod(idx, cols)
            if r >= rows:
                break
            cx = x + pl + c * cw
            cy = y + pt + r * chh
            pic = (it.get('picTab') or {}).get('pic0')
            if pic:
                im = self.load_pic(pic)
                if im:
                    if im.size != (iw, ih):
                        im = im.resize((iw, ih), NEAREST)
                        self.report.stretch(self.page, 'slidewindow', pic, im.size, (iw, ih))
                    paste_rgba(layer, im, cx + (cw - iw) // 2, cy)
                else:
                    self.report.miss(self.page, pic, caption)
            txt = it.get('text') or ''
            if txt:
                fake = {'fontSize': fs, 'colorTab': it.get('colorTab') or {},
                        'alignment': 33}
                self._draw_label(layer, fake, txt, cx, cy + ih, cw,
                                 max(1, chh - ih), 'slidewindow', caption)
        img.alpha_composite(layer)
        self.report.unsupported(self.page, 'slidewindow', caption, 'items',
                                '按 %dx%d 网格画 %d 个图标项（滑动/多页不还原）'
                                % (cols, rows, len(items)))

    # ---------- 树 ----------
    def draw_node(self, img, ox, oy, name, node):
        t = ctype_of(name)
        if node.get('visible', True) is False:
            return
        p = node.get('position') or {}
        x = ox + int(p.get('left') or 0)
        y = oy + int(p.get('top') or 0)
        w = int(p.get('width') or 0)
        h = int(p.get('height') or 0)
        cap = node.get('caption') or ''
        if t in CLIP_TYPES:
            sub = Image.new('RGBA', (max(1, w), max(1, h)), (0, 0, 0, 0))
            self.draw_self(sub, node, 0, 0, w, h, t, cap)
            if t == 'listview':
                self.draw_listview(sub, node, 0, 0, w, h, cap)
            else:
                for ck, cv in children_of(node):
                    self.draw_node(sub, 0, 0, ck, cv)  # 子坐标相对容器左上角
            paste_rgba(img, sub, x, y)
        else:
            self.draw_self(img, node, x, y, w, h, t, cap)
            if t == 'listview':
                self.draw_listview(img, node, x, y, w, h, cap)
                return                                  # listview 的子内容由 item 模板展开
            if t == 'slidewindow':
                self.draw_slidewindow(img, node, x, y, w, h, cap)
                return
            for ck, cv in children_of(node):
                self.draw_node(img, x, y, ck, cv)

    def render(self, doc):
        res = doc.get('resolution') or {}
        rp = doc.get('position') or {}
        W = int(res.get('width') or rp.get('width') or 0)
        H = int(res.get('height') or rp.get('height') or 0)
        if W <= 0 or H <= 0:
            raise SystemExit('[FATAL] json 缺 resolution/position 尺寸')
        page = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        bg = color_rgba(doc.get('backgroundColor'))
        if bg:
            ImageDraw.Draw(page).rectangle([0, 0, W - 1, H - 1], fill=bg)
        else:
            self.report.unsupported(self.page, 'root', doc.get('id', ''), 'backgroundColor',
                                    '根背景 -1/缺省 → 透明（设备上为黑屏底）')
        ox = int(rp.get('left') or 0)
        oy = int(rp.get('top') or 0)
        for k, v in children_of(doc):
            self.draw_node(page, ox, oy, k, v)
        if doc.get('topmost'):
            self.report.unsupported(self.page, 'root', str(doc.get('id', '')), 'topmost',
                                    '悬浮最上层（透明底）→ 按普通窗口绘制')
        return page, (W, H)


def paste_rgba(base, layer, x, y):
    """带负坐标安全裁剪的 alpha 合成。"""
    if layer is None:
        return
    bw, bh = base.size
    lw, lh = layer.size
    sx0, sy0 = max(0, -x), max(0, -y)
    dx0, dy0 = max(0, x), max(0, y)
    w = min(lw - sx0, bw - dx0)
    h = min(lh - sy0, bh - dy0)
    if w <= 0 or h <= 0:
        return
    part = layer.crop((sx0, sy0, sx0 + w, sy0 + h)) if (sx0 or sy0 or w != lw or h != lh) else layer
    base.alpha_composite(part, (dx0, dy0))


# ============================================================================
# 目标解析
# ============================================================================
def is_project_root(p):
    return os.path.isdir(os.path.join(p, 'ui'))


def list_pages(p):
    """支持 ui/*.json 与 ui/<res>/*.json；返回 {page: json_path}（同名先到先得）。"""
    d = p
    if not os.path.isdir(os.path.join(p, 'ui')) and os.path.basename(os.path.normpath(p)) == 'ui':
        d = p
    else:
        d = os.path.join(p, 'ui')
    out = OrderedDict()
    for f in sorted(glob.glob(os.path.join(d, '*.json'))) + \
             sorted(glob.glob(os.path.join(d, '*', '*.json'))):
        name = os.path.splitext(os.path.basename(f))[0]
        if name.endswith('.bak') or '.bak_' in name:
            continue
        out.setdefault(name, os.path.abspath(f))
    return out


def resolve_project(path):
    p = os.path.abspath(path)
    if os.path.isfile(p):
        root = None
        d = os.path.dirname(p)
        while d and d != os.path.dirname(d):
            if is_project_root(d):
                root = d
                break
            if os.path.basename(d) == 'ui':
                cand = os.path.dirname(d)
                if is_project_root(cand):
                    root = cand
                    break
            d = os.path.dirname(d)
        return root, p
    return (p if is_project_root(p) else None), None


# ============================================================================
# 主流程
# ============================================================================
def render_one(project, json_path, out_path, scale=1, font=None, align_mode='measured',
               report=None, verbose=True):
    doc = json.load(open(json_path, encoding='utf-8'))
    rep = report or Report()
    r = Renderer(project=project, json_path=json_path, font_path=font,
                 align_mode=align_mode, report=rep, verbose=verbose)
    r.font_path = r.resolve_font()
    page, (W, H) = r.render(doc)
    img = page
    if scale and int(scale) != 1:
        img = page.resize((W * int(scale), H * int(scale)), NEAREST)   # 放大必须 NEAREST
    img = img.convert('RGB') if not img.mode == 'RGB' else img
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path)
    return {'page': r.page, 'json': json_path, 'out': out_path, 'size': img.size,
            'resolution': (W, H), 'scale': int(scale or 1),
            'font': r.font_path, 'align_mode': align_mode, 'align': r.align}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='FlyThings json 布局 → PNG（引擎等价离线渲染 v0，PIL 像素级）')
    ap.add_argument('target', help='项目根目录（含 ui/）或直接给 .json 文件')
    ap.add_argument('--page', default='main', help='页面名（不含 .json，默认 main）')
    ap.add_argument('--out', default=None, help='输出 PNG（默认 <json目录>/<page>.render.png）')
    ap.add_argument('--scale', type=int, default=1, help='放大倍数（NEAREST，默认 1）')
    ap.add_argument('--font', default=None, help='覆盖字体 TTF')
    ap.add_argument('--report', action='store_true', help='打印完整清单（默认打摘要）')
    ap.add_argument('--align-mode', choices=['measured', 'task36'], default='measured',
                    help='5/0/1/4/6/2 解码：measured=位模型(4≡36/5≡37/6≡38) / task36=一律当 36')
    ap.add_argument('--json-report', default=None, help='把清单同时写成 json')
    ap.add_argument('--all', action='store_true', help='渲染全部页面（--out 视作输出目录）')
    args = ap.parse_args(argv)

    project, single = resolve_project(args.target)
    if single is None and not project:
        print('[FATAL] 找不到项目根（需含 ui/ 目录）：%s' % args.target)
        return 2
    if single and not project:
        project = os.path.dirname(os.path.dirname(os.path.abspath(single)))

    if single:
        jobs = [(os.path.splitext(os.path.basename(single))[0], single)]
    else:
        pages = list_pages(project)
        if not pages:
            print('[FATAL] %s/ui 下没有 *.json' % project)
            return 2
        if args.all:
            jobs = list(pages.items())
        else:
            if args.page not in pages:
                print('[FATAL] 找不到页面 %r；可选：%s' % (args.page, ', '.join(pages.keys())))
                return 2
            jobs = [(args.page, pages[args.page])]

    rep = Report()
    infos = []
    for name, jp in jobs:
        if args.out:
            outp = os.path.join(args.out, '%s.png' % name) if args.all else args.out
        else:
            outp = os.path.join(os.path.dirname(jp), '%s.render.png' % name)
        infos.append(render_one(project, jp, outp, scale=args.scale, font=args.font,
                                align_mode=args.align_mode, report=rep))

    # ---- 打印 ----
    print('=' * 72)
    print('json2img v%s — 引擎等价离线渲染（PIL 像素级，静止态）' % __version__)
    print('=' * 72)
    for i in infos:
        try:
            json_disp = os.path.relpath(i['json'])
        except ValueError:
            # Windows 跨盘符（json 在 C:\ 而 cwd 在 D:\）时 relpath 抛错；
            # 这里仅用于展示，退回绝对路径即可，不能让它成为致命错误。
            json_disp = i['json']
        print('[render] page=%-10s json=%s' % (i['page'], json_disp))
        print('          out=%s  size=%dx%d  resolution=%dx%d  scale=%d'
              % (i['out'], i['size'][0], i['size'][1], i['resolution'][0],
                 i['resolution'][1], i['scale']))
        print('          font=%s' % i['font'])
        ok = '[OK]' if i['size'] == (i['resolution'][0] * i['scale'],
                                    i['resolution'][1] * i['scale']) else '[!!]'
        print('          %s 尺寸 == resolution × scale' % ok)

    # ---- unsupported 清单（不许静默跳过）----
    items = list(rep.items.items())
    print('-' * 72)
    print('[unsupported/降级] %d 类：' % len(items))
    if not items:
        print('   （无）')
    by_note = Counter()
    for (page, ctype, field, note), v in items:
        by_note[(ctype, field, note)] += v['count']
    for (ctype, field, note), n in sorted(by_note.items(), key=lambda x: -x[1]):
        pages = sorted({k[0] for k in rep.items if k[1] == ctype and k[2] == field and k[3] == note})
        print('   - %-14s %-22s x%-4d %s' % (ctype, field, n, note))
        if args.report:
            print('     pages: %s' % ', '.join(pages))
            key = [k for k in rep.items if k[1] == ctype and k[2] == field and k[3] == note][0]
            print('例: %s' % ', '.join(rep.items[key]['examples'][:4]))
    if not args.report and items:
        print('   （--report 看每个案例的 page/caption 明细）')

    if rep.missing:
        print('[缺失图片 %d]' % len(rep.missing))
        for (page, pic), v in list(rep.missing.items())[:20]:
            print('   - %s: %s x%d %s' % (page, pic, v['count'], ','.join(v['examples'][:3])))
        print('   ⚠ 缺图 = 渲染少一层，真机上也没有该层（打包时会报），非渲染器问题')
    if rep.stretches:
        print('[拉伸填充（图 != 矩形，引擎语义=拉伸）%d 类]' % len(rep.stretches))
        for k, v in list(rep.stretches.items())[:10]:
            print('   - %s %s %s x%d' % (k[0], k[1], k[2], v))
        if len(rep.stretches) > 10:
            print('   ...（--report 看全）')
    if rep.nines:
        print('[九宫格 .9.png] %d 处：%s' % (sum(rep.nines.values()),
                                        ', '.join(list(rep.nines)[:6])))

    # ---- alignment 校准状态（实测 5 值 vs 待校准 6 值）----
    print('-' * 72)
    print('[校准状态] alignment（模式 --align-mode %s）' % args.align_mode)
    t = AlignTable(args.align_mode)
    for i in infos:
        tbl = i.get('align')
        if tbl:
            t.hits.update(tbl.hits)
    print('实测表（真机验证）：36=靠左+垂直居中 37=居中 38=靠右+垂直居中 33=顶部 41=底部')
    for v in sorted(ALIGN_MEASURED):
        if t.hits.get(v):
            print('     [measured]     %-3d → %s   x%d' % (v, ALIGN_MEASURED[v], t.hits[v]))
    print('   TODO 待校准（无真机表）：4/5/0/1/6/2 —— 本模式解码：')
    for v in sorted(ALIGN_UNCALIBRATED):
        if t.hits.get(v):
            dec = (ALIGN_DEFAULT[1], 'task36→36') if args.align_mode == 'task36' \
                else (ALIGN_UNCALIBRATED[v], '位模型')
            print('     [UNCALIBRATED] %-3d → %s (%s)  x%d' % (v, dec[0], dec[1], t.hits[v]))
    unk = {v: n for v, n in t.hits.items()
           if v not in ALIGN_MEASURED and v not in ALIGN_UNCALIBRATED}
    if unk:
        print('     [表外值→按 %d 处理] %s' % (ALIGN_DEFAULT[0], unk))
    print('合计：实测 %d 处 / 待校准 %d 处 / 表外 %d 处'
          % (t.measured_count(), t.uncalibrated_count(), t.other_count()))

    if args.json_report:
        d = rep.as_dict()
        d['renders'] = [{k: v for k, v in i.items() if k != 'align'} for i in infos]
        d['align'] = {'mode': args.align_mode, 'hits': dict(t.hits),
                      'measured': {str(k): v for k, v in ALIGN_MEASURED.items()},
                      'uncalibrated_todo': {str(k): v for k, v in ALIGN_UNCALIBRATED.items()}}
        os.makedirs(os.path.dirname(os.path.abspath(args.json_report)), exist_ok=True)
        json.dump(d, open(args.json_report, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('[清单已写] %s' % args.json_report)
    return 0


if __name__ == '__main__':
    sys.exit(main())
