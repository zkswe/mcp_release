#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 规格指针（DESIGN_SPEC 第 1.1 条）：本文件是**离线渲染器**，必须复现
# `ui_schema.json.renderContract` 的引擎语义（`pic-scale` 拉伸填盒 / `progress-clip`
# 1:1 贴 + `floor` 裁剪 / `thumb-size` 按 PNG 原尺寸 / `rounding` 用 floor）。
# 2026-10-05：`draw_seekbar` 那四条偏差已按规格重写（见该方法 docstring 与
# `tests/test_json2img_engine_model.py`），此前"仍在用 NEAREST + round、不要用它的输出做
# 视觉验收"那句已作废。**但近似点没有消失**，逐条记在 `ui_tools/json2img_coverage.json`
# （`--coverage` 打印）：能画但语义近似的写 `approximate`，真没实现的写 `unsupported` 且
# `blindSpot: true`；`--judge` 下未登记豁免的渲染盲区一律**判红**（盲区不许当通过）。
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

判定层（2026-10-05 加，T2.1/T2.2）：
     python ui_tools/json2img.py --coverage                  # 人读覆盖矩阵（无须 target）
     python ui_tools/json2img.py --coverage --check          # 校验矩阵：[PASS]/[FAIL] + 退出码
     python ui_tools/json2img.py <项目根> --judge            # 判定模式：未豁免的渲染盲区 → rc=1
     python ui_tools/json2img.py <项目根> --judge --coverage-json rep.json
   · 「覆盖矩阵」= `ui_schema.json#renderContract.rows`（行集合唯一真源，10 条）× 实现状态，
     状态数据住在 `ui_tools/json2img_coverage.json`；`--coverage` 只读不写。
   · 「盲区」= 渲染时走到 `Report.unsupported(...)` 的项（**如实记账**的原始素材），
     豁免登记表 = `ui_tools/json2img_blindspot_allow.json`（每条必须写 reason）。
   · `--judge` **默认关闭**；不带它时输出与退出码与本层加入前一致（渲染行为零改动）。

纪律：本文件是只读渲染器，不改任何工程文件（不 pack、不写 json）。
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import math
import os
import re
import sys
from collections import Counter, OrderedDict

try:  # Windows 控制台默认 GBK：保持控制台自身编码，仅把不可编码字符替换掉（不炸）
    sys.stdout.reconfigure(errors='replace')
    sys.stderr.reconfigure(errors='replace')
except Exception as ex:                     # 控制台重配失败不致命，但不静默
    sys.stderr.write('[warn] stdout reconfigure failed: %s\n' % ex)

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont
except Exception as exc:  # pragma: no cover
    print('[FATAL] 需要 Pillow：pip install pillow  (%s)' % exc)
    raise

__version__ = '0.1.1'      # 0.1.1（2026-10-05）：颜色语义修正 —— 只有 -1 是不填充，其它负数按 0xAARRGGBB

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
    """json 颜色 int → RGBA。

    语义（真源 = `ui_schema.json#valueRules.colorZero` + 本文件头「颜色约定」）：
      · `-1` / `0xFFFFFFFF` = **未用 / 框架跳过该绘制** → `None`（唯一的不填充标记）；
      · `0` = **不透明黑**（0xFF000000），**不是**"未设置"；
      · 其它负数 = int32 补码写的 `0xAARRGGBB`（例：`-16777216` = 0xFF000000 = 不透明黑）
        → `& 0xFFFFFF` 取 RGB；引擎不把高 8 位当该控件的透明度（透明度由 -1 或 PNG α 表达）。

    ⚠️ 2026-10-05 修：旧实现是 `if v < 0`（**所有**负数都当不填充）—— 与真源冲突，
    且让 `-16777216` 这类"不透明黑"完全不画（实测夹具踩到）。
    """
    if v is None:
        return None
    try:
        v = int(v)
    except Exception:
        return None
    if v in (-1, 0xFFFFFFFF):
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
        self.items = OrderedDict()      # (page,type,field,note) → {count, examples[], captions[]}
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
        # caption 单独留档（判定模式要按 **page/type/caption/field/note** 逐条报盲区）。
        # ⚠️ 只进内部条目、**不进 `as_dict()`** —— `--json-report` 的字节必须与本层加入前一致。
        if caption:
            caps = self.items[(page, ctype, field, note)].setdefault('captions', [])
            if caption not in caps and len(caps) < 4:
                caps.append(str(caption))

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


# C/C++ **数值字面量**（含后缀）：`42` / `42u` / `0x2E8BFF` / `24.0f` / `.5F` / `1e3` / `134`。
# ⚠️ 后缀必须认（2026-10-05 实测）：`SZKPoint thinLine[2] = {{24.0f, 380.0f}, …}` 里的 `24.0f`
# 曾被当成"变量实参"→ 整条 `drawLines` 被跳过 → **两条直线静默不画**（painter 页少了内容却没人知道）。
# 加 `f/F/l/L/u/U` 与 C++14 的 `'` 分隔符（`1'000`）。
_NUM_LITERAL = re.compile(
    r"^[-+]?(?:0[xX][0-9a-fA-F']+|(?:\d[\d']*\.?[\d']*|\.\d[\d']*)(?:[eE][-+]?\d+)?)[fFlLuU]*$")


def _split_c_args(txt):
    """按**逗号**切 C 实参，但把 `{…}` 当成一个整体（支持嵌套一层，如 `{{a,b},{c,d}}`）。

    ⚠️ 为什么不能用正则（2026-10-05 实测）：`{{24.0f, 380.0f}, {430.0f, 380.0f}}` 里
    内层的 `,` 会被当成实参分隔符 → 切出 `{{24.0f` / `380.0f}` 这种碎片 → 判成变量实参 →
    **整条 drawLines 被跳过、两条直线静默不画**。这里按花括号深度切，顶层逗号才算分隔。
    """
    out, buf, depth = [], '', 0
    for ch in txt:
        if ch == '{':
            depth += 1
            buf += ch
        elif ch == '}':
            depth = max(0, depth - 1)
            buf += ch
        elif ch == ',' and depth == 0:
            if buf.strip():
                out.append(buf)
            buf = ''
        else:
            buf += ch
    if buf.strip():
        out.append(buf)
    # C++11 的 `{{a,b},{c,d}}` 会被当成"一个带外层花括号的实参"：外层若是纯列表就展开成多个点
    res = []
    for item in out:
        s = item.strip()
        if s.startswith('{{') and s.endswith('}}'):
            for inner in _split_c_args(s[1:-1]):
                res.append(inner.strip())
        else:
            res.append(s)
    return res


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

    # ---------- 子盒（iconPosition / textPosition） ----------
    def _pos_box(self, node, key, x, y, w, h, ctype='', caption=''):
        """`iconPosition` / `textPosition` → 屏幕矩形（**相对控件盒**的坐标，规格见 `iconBox`）。

        ⚠️ 为什么必须走子盒（2026-10-05 用户报「带图标按键的对齐不对」）：
        `textPosition` 是**文字在控件内的盒子**，文字的 `alignment` 与居中都相对它算。
        带图标的按钮靠 `textPosition.left` 让开图标区（例：控件 216 宽、`textPosition.left=68`），
        改前渲染器整条忽略了这两个字段，把文字在**整控件盒**里居中 → 文字压在左侧图标区上。
        缺 `width/height` 的容错：宽度取到控件右沿、高度取到控件下沿（比夹成 0 更接近意图），
        并**如实记账**（规格要求"控件尺寸≠图片尺寸时必须显式"写全）。
        """
        box = node.get(key) if isinstance(node.get(key), dict) else None
        if not box:
            return None
        bl = int(box.get('left') or 0)
        bt = int(box.get('top') or 0)
        bw = int(box.get('width') or 0)
        bh = int(box.get('height') or 0)
        if bw <= 0 or bh <= 0:
            self.report.unsupported(
                self.page, ctype, caption, key,
                '子盒 %s 缺宽/高（规格要求显式写全）→ 按"到控件边缘"容错渲染' % key)
            bw = bw if bw > 0 else max(1, w - bl)
            bh = bh if bh > 0 else max(1, h - bt)
        # ⚠️ **越界 = 写法可疑，如实报**（2026-10-05 实测）：`iconBox` 的坐标是**相对控件盒**的
        # （规格 `sharedTypes.iconBox` 的口径）。实测仓内 33 处 `textPosition`：**9 处落在盒内**
        # （相对写法 —— 手写模板全属此类，也就是本轮修好的那些），**24 处按相对解释会整体越出控件盒**
        # —— 那些是把 `position` 逐字拷过来的绝对写法（生成物/示例）。引擎对越界值的处置**未实测**，
        # 所以这里**只报不猜**：照相对画 + 记账，让人一眼看到"这个文件很可能写错了"。
        if bl + bw > w + 1 or bt + bh > h + 1 or bl < 0 or bt < 0:
            self.report.unsupported(
                self.page, ctype, caption, key,
                '%s 按「相对控件盒」解释会越界（控件盒 %dx%d，子盒 left=%d top=%d %dx%d）'
                '—— 疑似把 position 逐字拷贝成了绝对坐标；引擎对越界值的处置未实测，'
                '此处照相对画（要精确请给不越界的相对值）' % (key, w, h, bl, bt, bw, bh))
        return (x + bl, y + bt, bw, bh)

    # ---------- 单节点 ----------
    def draw_self(self, img, node, x, y, w, h, ctype, caption):
        """底色 → 背景图 → 文字（+ 专有控件）。"""
        if w <= 0 or h <= 0:
            self.report.unsupported(self.page, ctype, caption, 'position',
                                    '宽高 <= 0 → 跳过（%dx%d）' % (w, h))
            return
        # ① 底色
        bg = node.get('bgColorTab', {}).get('color0') if isinstance(node.get('bgColorTab'), dict) else None
        if bg is None or int(bg) == -1:          # 只有 -1（未用）才回落到 backgroundColor
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
        elif ctype == 'painter':
            # painter 的绘制内容在 logic 代码里（json 只有底色）→ 必须重放它
            self.draw_painter(img, node, x, y, w, h, caption)
        elif ctype == 'pointer':
            # 表盘 + 指针按 setTargetAngle 旋转（角度也在 logic 里）
            self.draw_pointer(img, node, x, y, w, h, caption)
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
        elif ctype in ('diagram', 'cameraview', 'slidetext'):
            self.report.unsupported(self.page, ctype, caption, ctype,
                                    'v0 未专有实现 → 通用兜底（底色+背景图+文字）')
            self._text_in_subbox(img, node, x, y, w, h, ctype, caption)
        elif ctype == 'button' and self._pos_box(node, 'textPosition', x, y, w, h):
            # 带图标按键：文字在 `textPosition` 子盒里排版（`alignment` 相对该盒）
            self._text_in_subbox(img, node, x, y, w, h, ctype, caption)
        else:
            self.draw_text(img, node, x, y, w, h, ctype, caption)

    def _text_in_subbox(self, img, node, x, y, w, h, ctype, caption):
        """文字按 `textPosition` 子盒排版（缺该字段时退回整控件盒 → 与旧行为一致）。"""
        box = self._pos_box(node, 'textPosition', x, y, w, h, ctype, caption)
        bx, by, bw, bh = box if box else (x, y, w, h)
        self._draw_label(img, node, node.get('text') or '', bx, by, bw, bh, ctype, caption)

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
        # ⚠️ 进度值优先取 **logic 的 setProgress()**（2026-10-05 实测）：json 的 `defProgress`
        # 常是 0，真机初值由 `onUI_init()` 决定（模板 progress.json 写 0、代码写 60）。
        # 不读它，离线图永远是空轨道 —— 与"painter 内容在代码里"是同一类问题。
        prog = self.logic_progress(caption)
        if prog is None:
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
        #    ⚠️ `.9.png` 走九宫格：引擎对带引导线的图按 9-patch 拉伸/裁剪（引导线避开角切片），
        #       所以这里先 nine_patch 到「盒尺寸」，再按进度裁 —— 与轨道同口径。
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
                if str(ppic).endswith('.9.png'):
                    nn = nine_patch(im, w, h)
                    if nn is not None:
                        layer_src = nn
                    else:
                        self.report.unsupported(self.page, 'seekbar', caption, 'progressPic(.9)',
                                                '九宫格引导线缺失 → 退化为整体拉伸')
                        layer_src = im.resize((max(1, w), max(1, h)), NEAREST)
                else:
                    if (iw, ih) != (w, h):
                        # 图 != 控件盒 → 按规格这是**要求错**（引擎只裁剪不缩放）：如实记账，别悄悄缩放
                        self.report.stretch(self.page, 'seekbar', ppic, im.size, (w, h))
                    layer_src = im
                # 1:1（或 9-patch 拉伸后）贴、按进度裁剪到左上角；裁剩部分透明 = 露轨道
                cw = min(layer_src.width, max(0, cut_w))
                ch = min(layer_src.height, max(0, cut_h))
                if cw > 0 and ch > 0:
                    paste_rgba(layer, layer_src.crop((0, 0, cw, ch)), x, y)
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

    def draw_painter(self, img, node, x, y, w, h, caption):
        """`ZKPainter` 的绘制指令**在页面的 logic 代码里**（json 只有底色），所以必须读它。

        为什么要做（2026-10-05 用户报「painter 没有绘制出来」）：painter 是**状态式画笔** ——
        `setSourceColor/setLineWidth` 设状态，`fillRect/drawRect/fillArc/drawArc/drawLines/
        fillTriangle/drawTriangle/erase` 按当前状态落笔。json 里没有任何绘制内容，
        所以布局等价的离线渲染只能把 `<项目>/src/logic/<页面>Logic.cc` 的 `onUI_init()`/`onUI_show()`
        里的调用按顺序重放。重放是**只读取值**，不执行任何代码。

        AA 口径：形状先画在 `SS×` 画布上再用 `Image.BOX` 面积平均缩回 —— 与规格
        `renderContract.edge-aa`「≥4× 超采样 + 面积平均，α = 覆盖率」同口径。
        """
        drawn = 0
        SS = 4
        layer = Image.new('RGBA', (max(1, w) * SS, max(1, h) * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        color, lw = 0x000000, 1
        for op, a in self.logic_cmds(caption):
            def S(v):
                # C 字面量后缀（`24.0f` / `42u` / `1'000`）先剥掉再转 —— `float('24.0f')` 会抛异常
                s = str(v).strip().replace("'", '')
                s = re.sub(r'[fFlLuU]+$', '', s)
                return float(s) * SS
            if op == 'setSourceColor':
                color = int(a[0], 0)
            elif op == 'setLineWidth':
                lw = max(1, int(float(a[0])))
            elif op in ('fillRect', 'drawRect'):
                bx, by, bw, bh = (S(a[0]), S(a[1]), S(a[2]), S(a[3]))
                rad = S(a[4]) if len(a) > 4 else 0
                box = [bx, by, bx + bw - 1, by + bh - 1]
                if op == 'fillRect':
                    if rad > 0:
                        d.rounded_rectangle(box, radius=rad, fill=color_rgba(color))
                    else:
                        d.rectangle(box, fill=color_rgba(color))
                else:
                    # 描边落在**形状内侧**（引擎口径）：圆角矩形同理用 width 由内缩
                    if rad > 0:
                        d.rounded_rectangle(box, radius=rad, outline=color_rgba(color),
                                            width=max(1, int(round(lw * SS))))
                    else:
                        d.rectangle(box, outline=color_rgba(color),
                                    width=max(1, int(round(lw * SS))))
                drawn += 1
            elif op in ('fillArc', 'drawArc'):
                cx, cy, rx, ry = (S(a[0]), S(a[1]), S(a[2]), S(a[3]))
                # ⚠️ **角度零位实测标定**（2026-10-05）：引擎的 0° 是**正上方**、顺时针为正
                # （0=上 / 90=右 / 180=下 / 270=左）；PIL 的 0° 在右侧 —— 故 **PIL 角 = 引擎角 + 270**。
                # 证据：同一调用点 `fillArc(130,250,90,90,0,270)`，用真机截图 `temp/acc_canvas.png`
                # 逐角采样测缺口 = 屏幕 181°~270°（左上），而 PIL 偏移 0/90/180/270 各画一遍，
                # **只有 270 命中**（0 → 271°~359° 右上、90 → 1°~89° 右下、180 → 91°~179° 左下）。
                st = (float(a[4]) if len(a) > 4 else 0.0) + 270.0
                sw = float(a[5]) if len(a) > 5 else 360.0
                if op == 'fillArc' and abs(sw) >= 359.9:
                    # 整圆走 ellipse 更准（PIL 的 pieslice 在 360° 上会留缝）
                    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=color_rgba(color))
                elif op == 'fillArc':
                    d.pieslice([cx - rx, cy - ry, cx + rx, cy + ry], start=st,
                               end=st + sw, fill=color_rgba(color))
                else:
                    d.arc([cx - rx, cy - ry, cx + rx, cy + ry], start=st, end=st + sw,
                          fill=color_rgba(color), width=max(1, int(round(lw * SS))))
                drawn += 1
            elif op == 'drawLines':
                vals = list(a)
                # `drawLines(pts, n)` 的最后一个实参是**点数**，不是坐标 → 丢掉
                if len(vals) % 2 == 1:
                    vals = vals[:-1]
                pts = [vals[i:i + 2] for i in range(0, len(vals) - 1, 2)]
                if len(pts) >= 2:
                    d.line([(S(px), S(py)) for px, py in pts],
                           fill=color_rgba(color), width=max(1, int(round(lw * SS))),
                           joint='curve')
                    drawn += 1
            elif op == 'drawCurve':
                pts = [a[i:i + 2] for i in range(0, len(a) - 1, 2)]
                if len(pts) >= 2:
                    # 曲线 → 折线近似（如实记账，别假装还原了贝塞尔）
                    self.report.unsupported(self.page, 'painter', caption, 'drawCurve',
                                            '曲线按折线近似（控制点语义未实测）')
                    d.line([(S(px), S(py)) for px, py in pts],
                           fill=color_rgba(color), width=max(1, int(round(lw * SS))))
                    drawn += 1
            elif op in ('fillTriangle', 'drawTriangle') and len(a) >= 6:
                tri = [(S(a[0]), S(a[1])), (S(a[2]), S(a[3])), (S(a[4]), S(a[5]))]
                if op == 'fillTriangle':
                    d.polygon(tri, fill=color_rgba(color))
                else:
                    d.line(tri + [tri[0]], fill=color_rgba(color),
                           width=max(1, int(round(lw * SS))), joint='curve')
                drawn += 1
            elif op == 'erase':
                # 擦成透明（露出 painter 自己的底色）
                d.rectangle([S(a[0]), S(a[1]), S(a[0] + a[2]) * SS, S(a[1] + a[3]) * SS],
                            fill=(0, 0, 0, 0))
                drawn += 1
        if not drawn:
            self.report.unsupported(self.page, 'painter', caption, 'logic',
                                    '未找到绘制指令（painter 内容在 src/logic/<页面>Logic.cc 里；'
                                    '该文件缺失或本页确实没画）')
            return
        layer = layer.resize((max(1, w), max(1, h)), Image.BOX)     # 面积平均 = 覆盖率 α
        paste_rgba(img, layer, x, y)

    def draw_pointer(self, img, node, x, y, w, h, caption):
        """`ZKPointer`：背景表盘 + 指针图按 `setTargetAngle()` 绕 `rotationPoint` 旋转。

        字段口径（`ui_schema.json` + 知识页 `widget-code-api.md:95`）：
          · `rotationPoint` = **控件系**圆心；
          · `fixedPoint`    = **指针图系**铰点（针的转轴在图片上的位置）；
          · 画法 = 把图片的 `fixedPoint` 对到 `rotationPoint` 上，再绕该点转
            `setTargetAngle()` 的角度（`startAngle` 为表盘零位偏移，`clockwise` 定方向）。
        角度取不到时的兜底：`logic` 里没有 `setTargetAngle` 就按 `startAngle` 画（并记账）。
        """
        # ① 表盘（背景图按控件盒贴）
        bg = node.get('backgroundPic')
        if bg:
            self.draw_pic(img, bg, x, y, w, h, 'pointer', caption)
        # ② 指针
        pic = node.get('pointerPic')
        if not pic:
            self.report.unsupported(self.page, 'pointer', caption, 'pointerPic',
                                    '未配置 pointerPic → 只画表盘')
            return
        im = self.load_pic(pic)
        if im is None:
            self.report.miss(self.page, pic, caption)
            return
        rp = node.get('rotationPoint') or {}
        fp = node.get('fixedPoint') or {}
        rpx, rpy = int(rp.get('x') or 0), int(rp.get('y') or 0)
        fpx, fpy = int(fp.get('x') or 0), int(fp.get('y') or 0)
        ang = self.logic_angle(caption)
        if ang is None:
            ang = float(node.get('startAngle') or 0)
            self.report.unsupported(self.page, 'pointer', caption, 'setTargetAngle',
                                    'logic 里没找到 setTargetAngle → 按 startAngle=%g 画'
                                    '（真机初值由代码决定）' % ang)
        else:
            self.report.unsupported(self.page, 'pointer', caption, 'setTargetAngle',
                                    '角度取自 logic 的 setTargetAngle(%g)——静止态首帧' % ang)
        self.report.unsupported(self.page, 'pointer', caption, 'animatable',
                                'rotateSpeed=%s 的**平滑动画**不还原（只画目标角静止态）'
                                % node.get('rotateSpeed'))
        # PIL `rotate(θ)` 逆时针为正；屏幕坐标里"顺时针"= 逆时针取负。
        # `clockwise:true`（本例）→ 顺时针增角 → 传 `-ang`；`clockwise:false` → 传 `+ang`。
        deg = -ang if node.get('clockwise', True) else ang
        # 绕 fixedPoint 旋转：先铺一张与控件同大的画布，把 fixedPoint 对到 rotationPoint
        canvas = Image.new('RGBA', (max(1, w), max(1, h)), (0, 0, 0, 0))
        paste_rgba(canvas, im, rpx - fpx, rpy - fpy)
        rot = canvas.rotate(deg, center=(rpx, rpy), resample=Image.BICUBIC)
        paste_rgba(img, rot, x, y)

    def _ring_geom(self, im):
        """从中线水平扫描量环几何 → `(外半径, 环宽)`（像素）。

        为什么要量（2026-10-05）：改前用"环宽 ≈ 4% 直径"近似画，而实测 `pb_ring.png`
        （200×200）是**外半径 100 / 内半径 86 / 环宽 14**（= 7% 直径），差近一倍。
        环图的外沿顶到图片边界（α[0]=255，无外侧留白），所以 arc 的 bbox 要顶满控件盒。

        ⚠️ **形状定义只有一处**：环图的生成口径在 `ui_tools/gen_ring.py`（`outerRadius`/`ringWidth`
        由 `--size`/`--width` 现算，带质量自检，**产出即最终资产**）。这里量到的值应与它一致
        （`tests/test_gen_ring.py` 有用例对账）；"量"是为了兼容**第三方画的**环图，
        不是另立一套口径 —— 改本函数前先看 gen_ring 的头注释。
        """
        W, H = im.size
        a = im.convert('RGBA').getchannel('A')
        y = H // 2
        outer_l = next((x for x in range(W) if a.getpixel((x, y)) > 0), None)
        inner_l = None
        for x in range(0, W // 2):
            if a.getpixel((x, y)) > 0:
                inner_l = x
        if outer_l is None or inner_l is None:
            return None
        r_out = (W / 2.0) - outer_l
        r_in = (W / 2.0) - inner_l - 1
        return max(1, int(round(r_out))), max(1, int(round(r_out - r_in)))

    def draw_circlebar(self, img, node, x, y, w, h, caption):
        """`ZKCircleBar`：背景环整圈 + 有效环**按进度裁剪成扇形** + 中心文字（`textType`）。

        字段口径（`ui_schema.json` + 知识页 `circlebar-fields.md`）：
          · `backgroundPic` = 背景环，**不裁剪**、完整垫底；
          · `progressPic`  = 有效环，按 `progress/max × maxAngle` **扇形裁剪**；
          · `startAngle`   = 起始角（0 = 3 点钟方向），`maxAngle` = 最大扫过角（<360 = 开口环）；
          · `textType` 0=不画 / 1=数字 / 2=数字+`unit`；`textSize`/`textColor` 定中心文字。
        ⚠️ 改前只画整圈、且在尾部截断（实测 bbox 少了 1px → 左边多出一段实心），
        中间文字完全没画、起始角写死 −90（没读 `startAngle`）—— 2026-10-05 需求方报「默认渲染要给角度 +
        属性里带了中间显示的文字和单位」。
        """
        mx = node.get('max') or 100
        # 同 seekbar：优先读 logic 的 setProgress()（json 常写 0，真机初值在代码里）
        prog = self.logic_progress(caption)
        if prog is None:
            prog = node.get('progress')
        if prog is None:
            prog = node.get('defProgress') or 0
        try:
            frac = max(0.0, min(1.0, float(prog) / float(mx or 100)))
        except Exception:
            frac = 0.0
        max_angle = float(node.get('maxAngle') or 360)
        # ① 背景环：完整显示（与 `progressPicPos` 的位置尺寸一起用）
        pp = node.get('progressPicPos') or {}
        bx, by = x + int(pp.get('left') or 0), y + int(pp.get('top') or 0)
        bw = int(pp.get('width') or 0) or w
        bh = int(pp.get('height') or 0) or h
        bgpic = node.get('backgroundPic')
        if bgpic:
            self.draw_pic(img, bgpic, bx, by, bw, bh, 'circlebar', caption)
        # ② 有效环：按进度扇形裁剪
        ppic = node.get('progressPic')
        if ppic:
            im = self.load_pic(ppic)
            if im is None:
                self.report.miss(self.page, ppic, caption)
            else:
                geom = self._ring_geom(im)
                sweep = max_angle * frac
                # `startAngle` 直接用 PIL 角（0 = 3 点钟、顺时针为正）—— 与知识页口径一致
                start = float(node.get('startAngle') or 0)
                if not node.get('clockwise', True):
                    start = start - sweep
                layer = Image.new('RGBA', (max(1, bw), max(1, bh)), (0, 0, 0, 0))
                if geom:
                    r_out, rw = geom
                    d = ImageDraw.Draw(layer)
                    box = [0, 0, bw - 1, bh - 1]
                    if sweep > 0:
                        d.arc(box, start, start + sweep, fill=(255, 255, 255, 255), width=rw)
                    mask = layer.getchannel('A')
                else:
                    self.report.unsupported(self.page, 'circlebar', caption, 'progressPic',
                                            '量不到环几何 → 退化为整图贴（不裁剪）')
                    mask = None
                sub = im if im.size == (bw, bh) else im.resize((bw, bh), NEAREST)
                if mask is not None:
                    sub = sub.copy()
                    sub.putalpha(ImageChops.multiply(sub.getchannel('A'), mask))
                    # ⚠️ **合成必须分两步、落在干净层上**（2026-10-05 修「圆环内沿白锯齿」）：
                    # 原写法是 `paste_rgba(layer, sub, 0, 0)` —— 让 layer **贴到它自己身上**，
                    # 而 paste_rgba 又拿 layer 自身的 α 当遮罩 → 预乘被算两次 →
                    # 内沿那排半透明像素（源图 α=48/64/92…）被推成接近纯白，肉眼就是**白锯齿**。
                    # 正确：先把**遮罩后的有效环**贴进干净的 sub_layer，再把它合成到结果图上。
                    sub_layer = Image.new('RGBA', (max(1, bw), max(1, bh)), (0, 0, 0, 0))
                    paste_rgba(sub_layer, sub, 0, 0)
                    paste_rgba(img, sub_layer, bx, by)
                else:
                    paste_rgba(img, sub, bx, by)
        # ③ 中心文字：textType 0=不画 / 1=数字 / 2=数字+unit
        tt = node.get('textType', 0)
        if tt:
            txt = str(int(round(prog)))
            if int(tt) >= 2:
                txt += str(node.get('unit') or '')
            size = int(node.get('textSize') or 0) or max(10, int(min(bw, bh) * 0.12))
            col = color_rgba(node.get('textColor'))
            if col is None:
                col = (255, 255, 255, 255)
                self.report.unsupported(self.page, 'circlebar', caption, 'textColor',
                                        'textColor 缺省/非法 → 用白色画中心文字')
            cx, cy = bx + bw // 2, by + bh // 2
            f = self.font(size)
            try:
                tw = f.getbbox(txt)[2] - f.getbbox(txt)[0]
                asc, desc = f.getmetrics()
            except Exception:
                tw, asc, desc = len(txt) * size * 0.6, size, 0
            lay = Image.new('RGBA', img.size, (0, 0, 0, 0))
            ImageDraw.Draw(lay).text((cx - tw / 2.0, cy - (asc + desc) / 2.0 - desc / 2.0),
                                     txt, font=f, fill=col)
            img.alpha_composite(lay)
        self.report.unsupported(self.page, 'circlebar', caption, 'progress',
                                '扇形按 %s：进度 %s/%s → 扫过 %.0f°（起始角 %s°）；'
                                '环几何由 progressPic 中线实测'
                                % ('clockwise' if node.get('clockwise', True) else 'counter-clockwise',
                                   int(round(prog)), mx, max_angle * frac,
                                   node.get('startAngle') or 0))

    # ---------- 页面 logic 代码（painter 的绘制内容 / 运行期初值都在这里） ----------
    def _logic_file(self):
        """找本页的 `<项目>/src/logic/<页面>Logic.cc`（页面名 = json 文件名）。"""
        if not self.proj:
            return None
        page = self.page or 'main'
        cands = [os.path.join(self.proj, 'src', 'logic', '%sLogic.cc' % page)]
        if self.json_dir:
            cands.append(os.path.join(self.json_dir, '..', 'src', 'logic', '%sLogic.cc' % page))
        # 页面名大小写可能与文件名不一致（button vs Button）
        d = os.path.join(self.proj, 'src', 'logic')
        if os.path.isdir(d):
            want = ('%slogic.cc' % page).lower()
            for fn in os.listdir(d):
                if fn.lower() == want:
                    return os.path.join(d, fn)
        for c in cands:
            if os.path.isfile(c):
                return c
        return None

    def _logic_text(self):
        if getattr(self, '_logic_cache', None) is not None:
            return self._logic_cache
        p = self._logic_file()
        txt = ''
        if p:
            try:
                txt = io.open(p, encoding='utf-8', errors='replace').read()
            except OSError as e:
                self.report.unsupported(self.page, 'logic', os.path.basename(p), 'read',
                                        '页面 logic 读不了（%s）' % (e.strerror or type(e).__name__))
        self._logic_cache = txt
        self._logic_path = p
        return txt

    @staticmethod
    def _strip_comments(txt):
        """去 `//` 行注释与 `/* */` 块注释 —— 注释里的调用**不算绘制**（否则会把说明当指令）。"""
        txt = re.sub(r'/\*.*?\*/', '', txt, flags=re.S)
        return '\n'.join(re.sub(r'//.*$', '', ln) for ln in txt.split('\n'))

    def logic_cmds(self, caption):
        """本页 `onUI_init()` + `onUI_show()` 里针对 `caption` 的绘制调用（按出现顺序）。

        只匹配 `m<caption>Ptr->op(...)` 形态；**只取值、不执行代码**。参数只认字面量
        （数字 / `0x…` / `{a,b}` / `{a,b},{c,d}`）—— 变量当参数时**跳过并记账**（不猜）。
        """
        txt = self._strip_comments(self._logic_text())
        if not txt or not caption:
            return []
        # 切成函数体，只保留 onUI_init / onUI_show（其余回调是运行期事件，不是初值）
        bodies = []
        for fn in ('onUI_init', 'onUI_show'):
            m = re.search(r'\b%s\s*\([^)]*\)\s*\{' % fn, txt)
            if not m:
                continue
            i, depth = m.end(), 1
            while i < len(txt) and depth:
                if txt[i] == '{':
                    depth += 1
                elif txt[i] == '}':
                    depth -= 1
                i += 1
            bodies.append(txt[m.end():i - 1])
        out = []
        # ⚠️ 实参必须按**括号平衡**取（2026-10-05 实测）：用 `\(([^;]*?)\)` 会在第一个 `)` 截断 ——
        # `setSourceColor(0xFF4D4D);` 侥幸能过，但含花括号初始化列表的调用会被切碎判成变量实参。
        # 另外 `drawLines(thinLine, 2)` 的实参是**局部数组**——数组就在同一函数体里、
        # 初值全是字面量，所以先扫出 `T name[N] = {{…},{…}}` 的取值表再代入（不猜运行值，只读字面量）。
        var_pts = {}
        for vm in re.finditer(r'\b\w+\s+(\w+)\s*\[\s*\d*\s*\]\s*=\s*\{([^;]*?)\}\s*;', txt):
            pts = []
            for raw in _split_c_args('{%s}' % vm.group(2)):
                s = raw.strip()
                if s.startswith('{') and s.endswith('}'):
                    vals = [x.strip() for x in s.strip('{}').split(',') if x.strip()]
                    if all(_NUM_LITERAL.match(v) for v in vals) and len(vals) == 2:
                        pts.append((vals[0], vals[1]))
                    else:
                        pts = []
                        break
                else:
                    pts = []
                    break
            if pts:
                var_pts[vm.group(1)] = pts
        pat = re.compile(r'm%sPtr\s*->\s*(\w+)\s*\(' % re.escape(caption))
        for body in bodies:
            for m in pat.finditer(body):
                op = m.group(1)
                i, depth = m.end(), 1
                while i < len(body) and depth:
                    if body[i] == '(':
                        depth += 1
                    elif body[i] == ')':
                        depth -= 1
                    i += 1
                argtxt = body[m.end():i - 1].strip()
                # 局部数组实参 → 展开成「逐点字面量」，个数与调用里给的数量取小
                parts = _split_c_args(argtxt)
                expanded = []
                for raw in parts:
                    nm = raw.strip()
                    if nm in var_pts:
                        expanded.extend(var_pts[nm])
                    else:
                        expanded.append(raw)
                if expanded != parts:
                    argtxt = ', '.join('{%s, %s}' % p if isinstance(p, tuple) else p
                                       for p in expanded)
                if op == 'erase' and not argtxt:
                    continue                      # erase() 无参不是真 API（规格已钉）
                args, ok = [], True
                if argtxt:
                    for raw in _split_c_args(argtxt):
                        raw = raw.strip()
                        if raw.startswith('{'):
                            vals = [x.strip() for x in raw.strip('{}').split(',') if x.strip()]
                            if not all(_NUM_LITERAL.match(v) for v in vals):
                                ok = False
                                break
                            args.extend(vals)
                        elif _NUM_LITERAL.match(raw):
                            args.append(raw)
                        else:
                            ok = False
                            break
                if not ok:
                    self.report.unsupported(self.page, 'painter', caption, op,
                                            '该调用含变量/表达式实参 → 未重放（静态渲染不猜运行值）')
                    continue
                out.append((op, args))
        return out

    def logic_angle(self, caption):
        """本页 `m<caption>Ptr->setTargetAngle(N)` 的数值（pointer 的静止角）。取不到回 None。"""
        txt = self._strip_comments(self._logic_text())
        if not txt or not caption:
            return None
        m = re.search(r'm%sPtr\s*->\s*setTargetAngle\s*\(\s*([-+]?\d+\.?\d*)\s*\)'
                      % re.escape(caption), txt)
        return float(m.group(1)) if m else None

    def logic_progress(self, caption):
        """本页 `m<caption>Ptr->setProgress(N)` 的数值（seekbar/circlebar 的运行期初值）。

        为什么必须读（2026-10-05）：json 的 `defProgress` 常是 0，真机初值由 `onUI_init()` 决定 ——
        不读它，离线图就永远画成空轨道（实测模板 `progress.json`：json 写 0、代码写 60/70）。
        ⚠️ 匹配靠 `caption`（= 引擎的控件名，生成 `m<caption>Ptr`）；`caption` 为空时**静默失效**过
        （2026-10-05 调试用例时踩到：节点没写 caption → 逻辑明明有 setProgress 也读不到）→ 这里显式记账。
        """
        txt = self._strip_comments(self._logic_text())
        if not caption:
            if txt:
                self.report.unsupported(self.page, 'progress', '(无 caption)', 'setProgress',
                                        '控件没写 caption → 无法在 logic 里定位 `m<caption>Ptr`，'
                                        '运行期初值读不到（真机 json 必写 caption）')
            return None
        if not txt:
            return None
        m = re.search(r'm%sPtr\s*->\s*setProgress\s*\(\s*([-+]?\d+)\s*\)' % re.escape(caption), txt)
        if not m:
            return None
        self.report.unsupported(self.page, 'progress', caption, 'setProgress',
                                '初值取自 logic 的 setProgress(%s)（json 的 defProgress 不是真机初值）'
                                % m.group(1))
        return int(m.group(1))

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
            if color is None or int(color) == -1:
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


# ============================================================================
# 判定层：覆盖矩阵（--coverage）与盲区判红（--judge）
# ============================================================================
# 定位（REMEDIATION-UI-PIPELINE.md §3 模块 E「渲染判定」）：
#   渲染器只负责**如实记账**（Report.unsupported）；"这块算不算通过"是**判定**，住在这一节。
#   两条判据：
#     ① 覆盖矩阵：`ui_schema.json#renderContract.rows` 的**每一行**都要有实现状态
#        （implemented / approximate / unsupported）与依据 —— 缺行、多行、状态非法、
#        blindSpot 不带说明、evidence 指向不存在的文件 → `--coverage --check` 判红。
#     ② 盲区判红：判定模式下，任何走到 `Report.unsupported(...)` 的项若未被豁免表登记
#        → 计入 `blindSpots[]` 并让退出码变 1（**盲区不许当通过**）。
#   ⚠️ 行集合的**唯一真源**是 `ui_schema.json`；本文件**不重抄**那 10 个 id，
#      矩阵数据（`json2img_coverage.json`）也只填"状态"，id 与真源逐条对账。
HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(HERE)
SCHEMA_PATH = os.path.join(HERE, 'ui_schema.json')
COVERAGE_PATH = os.path.join(HERE, 'json2img_coverage.json')
BLINDSPOT_ALLOW_PATH = os.path.join(HERE, 'json2img_blindspot_allow.json')

STATUS_VALUES = ('implemented', 'approximate', 'unsupported')
STATUS_MEANING = OrderedDict([
    ('implemented', '按 renderContract 实现，且有判据（用例）钉住'),
    ('approximate', '能画，但语义/度量与引擎**近似**（近似点写在 note 里）'),
    ('unsupported', '渲染器**没有**实现这一条（判定不算通过）'),
])


def disp_path(p):
    """展示用相对路径（跨盘符时退回绝对路径，不炸）。"""
    try:
        return os.path.relpath(p, BASE_DIR).replace(os.sep, '/')
    except ValueError:
        return p


def load_contract_rows(schema_path=SCHEMA_PATH):
    """行集合的**唯一真源**：`ui_schema.json#renderContract.rows`（返回 [{id,scope,rule}]）。

    本函数是"哪 10 条"的唯一出处 —— 其它地方（含矩阵数据、用例、报告）一律引用它，
    不许重抄 id 列表。
    """
    with io.open(schema_path, encoding='utf-8') as f:
        doc = json.load(f)
    rows = (doc.get('renderContract') or {}).get('rows') or []
    out = []
    for i, r in enumerate(rows, 1):
        # 真源自身不合法就当场抛（不许"少一条就当没有"—— 那正好是这条判据要防的静默）
        if not isinstance(r, dict) or not str(r.get('id') or '').strip():
            raise ValueError('renderContract.rows[%d] 缺 id（真源 %s 自身不合法）'
                             % (i, disp_path(schema_path)))
        out.append({'id': str(r['id']), 'scope': str(r.get('scope') or ''),
                    'rule': str(r.get('rule') or '')})
    return out


def load_coverage_matrix(path=COVERAGE_PATH):
    """读覆盖矩阵数据 → (整个文档, rows)。读不了抛 OSError/ValueError（调用方记账）。

    ⚠️ 用 `utf-8-sig` 读：矩阵/豁免表是**人手可能在 Windows 上编辑的数据文件**
    （记事本 / PowerShell `Set-Content -Encoding utf8` 都会写 BOM），带 BOM 就报
    "Unexpected UTF-8 BOM"等于把登记豁免的人挡在门外。判据不能因为编码细节变成假红。
    """
    with io.open(path, encoding='utf-8-sig') as f:
        doc = json.load(f)
    rows = doc.get('rows') if isinstance(doc, dict) else doc
    return doc, rows


def _entry_key(e):
    return (e.get('page'), e.get('type'), e.get('field'), e.get('caption'), e.get('note'))


def load_blindspot_allow(path=BLINDSPOT_ALLOW_PATH):
    """读盲区豁免登记表 → (entries, fails)。

    条目形状：`{type, field, allow, reason}`（`type`/`field` 必填，支持 `'*'`；
    `page`/`caption`/`note` 可选，写上就是**精确匹配**；`allow: false` = 显式**拒绝**豁免
    （优先于 allow 条目，防止通配把某条悄悄吃掉））。
    `reason` **必填**（豁免必须写清"为什么这块可以不覆盖"）。
    """
    fails = []
    if not os.path.isfile(path):
        return [], ['豁免登记表不存在：%s' % disp_path(path)]
    try:
        # `utf-8-sig`：Windows 上手写/用 PowerShell 生成这个文件会带 BOM（见 load_coverage_matrix）
        with io.open(path, encoding='utf-8-sig') as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        return [], ['豁免登记表读不了：%s（%s）' % (disp_path(path), e)]
    entries = doc.get('entries') if isinstance(doc, dict) else doc
    if not isinstance(entries, list):
        return [], ['豁免登记表缺 entries 列表：%s' % disp_path(path)]
    seen = set()
    for i, e in enumerate(entries, 1):
        label = '%s#entries[%d]' % (disp_path(path), i)
        if not isinstance(e, dict):
            fails.append('%s 不是对象' % label)
            continue
        if not str(e.get('type') or '').strip():
            fails.append('%s 缺 type（精确匹配的控件类型，或 "*"）' % label)
        if not str(e.get('field') or '').strip():
            fails.append('%s 缺 field（精确匹配的字段，或 "*"）' % label)
        if 'page' in e and not str(e.get('page') or '').strip():
            fails.append('%s 的 page 写了空值（要么不写 = 不限定页，要么写页名）' % label)
        if not isinstance(e.get('allow'), bool):
            fails.append('%s 缺 allow（true=豁免 / false=显式拒绝）' % label)
        if not str(e.get('reason') or '').strip():
            fails.append('%s 缺 reason（豁免**必须**写理由）' % label)
        k = _entry_key(e)
        if k in seen:
            fails.append('%s 与前面的条目重复（同一 type/field/caption/note）' % label)
        seen.add(k)
    return entries, fails


def match_blindspot_allow(entries, page, ctype, caption, field, note):
    """精确匹配豁免条目 → ('allow'|'deny', entry) 或 None（deny 优先于 allow）。

    `page`/`caption`/`note` 只在条目**写了**的时候参与匹配（不写 = 不限定），
    `type`/`field` 必填（`'*'` = 任意）。
    """
    hits = []
    for e in entries:
        if e.get('type') not in ('*', ctype):
            continue
        if e.get('field') not in ('*', field):
            continue
        if e.get('page') not in (None, '', page):
            continue
        if e.get('caption') not in (None, '', caption):
            continue
        if e.get('note') not in (None, '', note):
            continue
        hits.append(e)
    for e in hits:
        if e.get('allow') is False:
            return 'deny', e
    if hits:
        return 'allow', hits[0]
    return None


def collect_blind_spots(rep, entries):
    """`Report` 的 unsupported 项 → (未豁免盲区, 已豁免) 两组，逐条带 page/type/caption/field/note。

    caption 取 `Report` 内部留档（`Report.unsupported` 里单独收的 captions）；
    老的/外部构造的条目退回从 `examples`（`type/caption`）里拆，不静默丢字段。
    """
    unexempted, exempted = [], []
    for (page, ctype, field, note), v in rep.items.items():
        caps = [str(c) for c in (v.get('captions') or [])]
        if not caps:
            for ex in v.get('examples') or []:
                caps.append(ex.split('/', 1)[1] if '/' in ex else '')
        caption = caps[0] if caps else ''
        item = OrderedDict([('page', page), ('type', ctype), ('caption', caption),
                            ('captions', caps), ('field', field), ('note', note),
                            ('count', v.get('count', 0))])
        m = match_blindspot_allow(entries, page, ctype, caption, field, note)
        if m and m[0] == 'allow':
            item['exemptReason'] = str(m[1].get('reason') or '')
            exempted.append(item)
        else:
            if m and m[0] == 'deny':
                item['deniedReason'] = str(m[1].get('reason') or '')
            unexempted.append(item)
    return unexempted, exempted


def check_coverage(matrix_path=COVERAGE_PATH, schema_path=SCHEMA_PATH,
                   allow_path=BLINDSPOT_ALLOW_PATH, base_dir=BASE_DIR):
    """校验覆盖矩阵 → 失败项列表（空 = 通过）。判据见文件头「判定层」注。

    ① 每个 renderContract row id 在矩阵里**恰好出现一次**（缺/多/重复都红）；
    ② `status` ∈ implemented / approximate / unsupported；
    ③ `blindSpot: true` 必须带非空 `note`；
    ④ `evidence.tests` 里的文件必须存在（相对仓根解析；绝对路径另算）；
    ⑤ 豁免登记表结构合法（`reason` 必填、键不重复）—— 判定层的地基也是判据的一部分。
    """
    fails = []
    try:
        contract = load_contract_rows(schema_path)
    except (OSError, ValueError) as e:
        return ['renderContract 真源读不了：%s（%s）' % (disp_path(schema_path), e)]
    if not contract:
        return ['renderContract 真源里没有 rows：%s' % disp_path(schema_path)]
    try:
        _, rows = load_coverage_matrix(matrix_path)
    except (OSError, ValueError) as e:
        return ['覆盖矩阵读不了：%s（%s）' % (disp_path(matrix_path), e)]
    if not isinstance(rows, list):
        return ['覆盖矩阵缺 rows 列表：%s' % disp_path(matrix_path)]

    contract_ids = [r['id'] for r in contract]
    seen = OrderedDict()
    for i, row in enumerate(rows, 1):
        label = '矩阵第 %d 行' % i
        if not isinstance(row, dict):
            fails.append('%s 不是对象' % label)
            continue
        rid = str(row.get('id') or '').strip()
        if rid:
            label = rid
            seen.setdefault(rid, 0)
            seen[rid] += 1
        else:
            fails.append('%s 缺 id' % label)
        note = str(row.get('note') or '').strip()
        if not note:
            fails.append('%s 缺 note（每条都要写清实现/近似点）' % label)
        st = row.get('status')
        if st not in STATUS_VALUES:
            fails.append('%s status=%r 非法（合法值：%s）'
                         % (label, st, ' / '.join(STATUS_VALUES)))
        bs = row.get('blindSpot')
        if not isinstance(bs, bool):
            fails.append('%s 缺 blindSpot（bool：该条能否由离线渲染判定）' % label)
        elif bs and not note:
            fails.append('%s blindSpot=true 必须带非空 note（说清哪里没被覆盖）' % label)
        ev = row.get('evidence')
        if not isinstance(ev, dict):
            fails.append('%s 缺 evidence{tests:[], device:[]}' % label)
            continue
        tests = ev.get('tests')
        if not isinstance(tests, list):
            fails.append('%s evidence.tests 不是列表' % label)
        else:
            for t in tests:
                p = str(t)
                fp = p if os.path.isabs(p) else os.path.join(base_dir, p.replace('/', os.sep))
                if not os.path.isfile(fp):
                    fails.append('%s evidence.tests 里的文件不存在：%s' % (label, t))
        if not isinstance(ev.get('device'), list):
            fails.append('%s evidence.device 不是列表' % label)

    for rid in contract_ids:
        if rid not in seen:
            fails.append('矩阵缺 renderContract 行：%s（真源 %s）' % (rid, disp_path(schema_path)))
    for rid, n in seen.items():
        if n > 1:
            fails.append('矩阵里 id 重复 %d 次：%s' % (n, rid))
        if rid not in contract_ids:
            fails.append('矩阵多出 renderContract 没有的 id：%s' % rid)

    _, afails = load_blindspot_allow(allow_path)
    for f in afails:
        fails.append('豁免登记表：%s' % f)
    return fails


def render_coverage(contract, rows, matrix_path=COVERAGE_PATH, schema_path=SCHEMA_PATH):
    """人读矩阵文本（表格 + 备注全文）；行序 = renderContract 行序。"""
    by_id = {}
    for r in rows or []:
        if isinstance(r, dict) and r.get('id'):
            by_id.setdefault(str(r['id']), r)
    L = []
    L.append('=' * 78)
    L.append('json2img 覆盖矩阵 —— renderContract 十条 × 实现状态（渲染器 v%s）' % __version__)
    L.append('=' * 78)
    L.append('行集合真源：%s#renderContract.rows（%d 条，**不在别处重抄**）'
             % (disp_path(schema_path), len(contract)))
    L.append('状态数据：  %s' % disp_path(matrix_path))
    L.append('状态口径：  ' + ' / '.join('%s=%s' % (k, v) for k, v in STATUS_MEANING.items()))
    L.append('-' * 78)
    L.append('%-20s %-13s %-9s %s' % ('id', 'status', 'blindSpot', 'note（摘要）'))
    L.append('-' * 78)
    for c in contract:
        row = by_id.get(c['id']) or {}
        note = str(row.get('note') or '（矩阵里缺这一行）')
        st = str(row.get('status') or '-')
        bs = row.get('blindSpot')
        bs_disp = 'yes' if bs is True else ('no' if bs is False else '-')
        head = '%-20s %-13s %-9s ' % (c['id'], st, bs_disp)
        pad = ' ' * len(head)
        for i, seg in enumerate(_wrap(note, 60)):
            L.append((head if i == 0 else pad) + seg)
    L.append('-' * 78)
    counts = Counter(str((by_id.get(c['id']) or {}).get('status')) for c in contract)
    blind = [c['id'] for c in contract if (by_id.get(c['id']) or {}).get('blindSpot') is True]
    L.append('统计：' + ' / '.join('%s %d' % (s, counts.get(s, 0)) for s in STATUS_VALUES)
             + '；blindSpot %d 条%s' % (len(blind), ('（%s）' % ', '.join(blind)) if blind else ''))
    L.append('-' * 78)
    for c in contract:
        row = by_id.get(c['id']) or {}
        L.append('%s' % c['id'])
        L.append('    scope   : %s' % (c.get('scope') or ''))
        L.append('    status  : %s — %s' % (row.get('status', '（缺）'),
                                            STATUS_MEANING.get(row.get('status'), '非法值')))
        L.append('    note    : %s' % (row.get('note') or '（缺）'))
        ev = row.get('evidence') or {}
        L.append('    tests   : %s' % (', '.join(ev.get('tests') or []) or '（无对应用例）'))
        L.append('    device  : %s' % (', '.join(ev.get('device') or []) or '（无真机证据）'))
    return '\n'.join(L)


def _wrap(text, width):
    """按字符数折行（中英混排的粗略折行；只影响人读输出，不参与判据）。"""
    text = ' '.join(str(text).split())
    return [text[i:i + width] for i in range(0, len(text), width)] or ['']


def render_judgement(unexempted, exempted, allow_path, allow_existed, allow_count=0):
    """判定模式的盲区报告文本（逐条给 page/type/caption/field/note；豁免逐条给理由）。"""
    L = []
    L.append('-' * 78)
    L.append('[判定模式 --judge] 渲染盲区（未被渲染器覆盖的项 → 判定不算通过）')
    L.append('-' * 78)
    L.append('豁免登记表：%s（%s）'
             % (disp_path(allow_path),
                '文件里登记 %d 条' % allow_count if allow_existed
                else '**文件不存在 → 视为 0 条豁免**（不静默）'))
    if unexempted:
        L.append('盲区 %d 条（**未豁免**）：' % len(unexempted))
        for i, b in enumerate(unexempted, 1):
            L.append('  %2d. page=%s type=%s caption=%s field=%s'
                     % (i, b['page'], b['type'], b['caption'] or '(无 caption)', b['field']))
            L.append('      note x%d: %s' % (b['count'], b['note']))
            if b.get('deniedReason'):
                L.append('      被 allow:false 规则显式拒绝：%s' % b['deniedReason'])
    else:
        L.append('盲区 0 条（未豁免）')
    L.append('已豁免 %d 条：' % len(exempted))
    if not exempted:
        L.append('   （无）')
    for b in exempted:
        L.append('   - type=%s field=%s caption=%s  ← %s'
                 % (b['type'], b['field'], b['caption'] or '(无 caption)', b['exemptReason']))
    return '\n'.join(L)


def write_coverage_json(path, cov, judge, check_ran, matrix_path):
    """把覆盖矩阵 + 校验结论 + 判定结果写成**机读**产物（`--coverage-json`）。"""
    by_id = {}
    for r in cov['rows']:
        if isinstance(r, dict) and r.get('id'):
            by_id.setdefault(str(r['id']), r)
    out = OrderedDict()
    out['renderer'] = {'file': disp_path(os.path.abspath(__file__)), 'version': __version__}
    out['contractSource'] = disp_path(SCHEMA_PATH)
    out['matrixFile'] = disp_path(matrix_path)
    out['coverage'] = []
    for c in cov['contract']:
        row = by_id.get(c['id']) or {}
        out['coverage'].append(OrderedDict([
            ('id', c['id']), ('scope', c['scope']),
            ('status', row.get('status')), ('blindSpot', row.get('blindSpot')),
            ('note', row.get('note')), ('evidence', row.get('evidence'))]))
    out['check'] = {'ran': bool(check_ran), 'ok': cov['ok'] if cov['ran'] else None,
                    'failures': cov['failures']}
    out['judge'] = {'ran': judge['ran'], 'blindSpots': judge['blindSpots'],
                    'exempted': judge['exempted'],
                    'unexemptedCount': len(judge['blindSpots']),
                    'exemptedCount': len(judge['exempted']),
                    'allowFile': disp_path(judge['allowFile']),
                    'allowExists': judge['allowExists'],
                    'allowFails': judge.get('allowFails', [])}
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('[覆盖矩阵已写] %s' % path)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='FlyThings json 布局 → PNG（引擎等价离线渲染 v0，PIL 像素级）')
    # `nargs='?'`：`--coverage` 是**对渲染器自身**的判定，不需要 target。
    # 不给 target 又不进覆盖模式时，仍按"缺 target"报错 + 退出码 2（与旧行为同码）。
    ap.add_argument('target', nargs='?', default=None,
                    help='项目根目录（含 ui/）或直接给 .json 文件（--coverage 时可不给）')
    ap.add_argument('--page', default='main', help='页面名（不含 .json，默认 main）')
    ap.add_argument('--out', default=None, help='输出 PNG（默认 <json目录>/<page>.render.png）')
    ap.add_argument('--scale', type=int, default=1, help='放大倍数（NEAREST，默认 1）')
    ap.add_argument('--font', default=None, help='覆盖字体 TTF')
    ap.add_argument('--report', action='store_true', help='打印完整清单（默认打摘要）')
    ap.add_argument('--align-mode', choices=['measured', 'task36'], default='measured',
                    help='5/0/1/4/6/2 解码：measured=位模型(4≡36/5≡37/6≡38) / task36=一律当 36')
    ap.add_argument('--json-report', default=None, help='把清单同时写成 json')
    ap.add_argument('--all', action='store_true', help='渲染全部页面（--out 视作输出目录）')
    # ---- 判定层（T2.1 覆盖矩阵 / T2.2 盲区判红）----
    ap.add_argument('--coverage', action='store_true',
                    help='打印 renderContract 覆盖矩阵（人读表格；无须 target）')
    ap.add_argument('--check', action='store_true',
                    help='与 --coverage 连用：校验矩阵，[PASS]/[FAIL] + 失败退出码 1')
    ap.add_argument('--coverage-json', default=None,
                    help='把覆盖矩阵（含 --check 结论、--judge 盲区）写成 json')
    ap.add_argument('--coverage-matrix', default=COVERAGE_PATH,
                    help='覆盖矩阵数据文件（默认 ui_tools/json2img_coverage.json）')
    ap.add_argument('--judge', action='store_true',
                    help='判定模式：未登记豁免的渲染盲区 → 报告列出并 rc=1（默认关闭）')
    ap.add_argument('--blindspot-allow', default=BLINDSPOT_ALLOW_PATH,
                    help='盲区豁免登记表（默认 ui_tools/json2img_blindspot_allow.json）')
    args = ap.parse_args(argv)

    want_coverage = bool(args.coverage or args.check or args.coverage_json)
    cov = {'ran': False, 'contract': [], 'rows': [], 'failures': [], 'ok': None}
    # 判定结果容器**先建**：`--coverage-json` 在"只做覆盖、不渲染"那条出口也要能落盘。
    judge = {'ran': False, 'blindSpots': [], 'exempted': [], 'allowFails': [],
             'allowFile': args.blindspot_allow, 'allowExists': False}
    if want_coverage:
        try:
            contract = load_contract_rows(SCHEMA_PATH)
            _, rows = load_coverage_matrix(args.coverage_matrix)
            rows = rows if isinstance(rows, list) else []
        except (OSError, ValueError) as e:
            print('[FAIL] 覆盖矩阵读不了：%s' % e)
            return 1
        cov.update({'ran': True, 'contract': contract, 'rows': rows})
        print(render_coverage(contract, rows, args.coverage_matrix, SCHEMA_PATH))
        print('-' * 78)
        fails = check_coverage(args.coverage_matrix, SCHEMA_PATH, args.blindspot_allow)
        cov['failures'] = fails
        cov['ok'] = not fails
        if fails:
            for f in fails:
                print('   - %s' % f)
            if args.check:
                print('[FAIL] 覆盖矩阵校验不通过：%d 处（见上）' % len(fails))
            else:
                print('[WARN] 覆盖矩阵校验有 %d 处问题（加 --check 才判红/给退出码 1）' % len(fails))
        else:
            print('[PASS] 覆盖矩阵 %d 行 == renderContract %d 行（id 恰好一次）；status 合法；'
                  'blindSpot 带 note；evidence.tests 均存在；豁免登记表结构合法'
                  % (len(cov['rows']), len(contract)))
        if args.check and fails:
            return 1

    if args.target is None:
        if want_coverage:
            if args.coverage_json:
                write_coverage_json(args.coverage_json, cov, judge, args.check,
                                    args.coverage_matrix)
            return 0
        ap.error('the following arguments are required: target')

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

    # ---- 判定模式：未豁免的渲染盲区 → 判不通过（默认关闭，见 --judge）----
    rc = 0
    if args.judge:
        entries, afails = load_blindspot_allow(args.blindspot_allow)
        judge['allowExists'] = os.path.isfile(args.blindspot_allow)
        unexempted, exempted = collect_blind_spots(rep, entries)
        judge.update({'ran': True, 'blindSpots': unexempted, 'exempted': exempted,
                      'allowFails': afails})
        print(render_judgement(unexempted, exempted, args.blindspot_allow,
                               judge['allowExists'], len(entries)))
        if unexempted:
            print('[FAIL] 判定不通过：%d 类渲染盲区**未被覆盖也未被登记豁免**'
                  '（这几块离线渲染说了不算，不能当通过）' % len(unexempted))
            rc = 1
        else:
            print('[PASS] 判定通过：无未豁免盲区（已豁免 %d 类，理由见上）' % len(exempted))
        if afails:
            for f in afails:
                print('   [WARN] 豁免登记表：%s' % f)
            print('[WARN] 豁免登记表有 %d 处结构问题（--coverage --check 判红；'
                  '理由必填，否则豁免不算数）' % len(afails))

    if args.coverage_json:
        write_coverage_json(args.coverage_json, cov, judge, args.check, args.coverage_matrix)
    return rc


if __name__ == '__main__':
    sys.exit(main())
