# -*- coding: utf-8 -*-
"""ui_emit.py —— FlyThings `ui/*.json` 的**唯一发射层**（T5.2）。

口径（为什么只有这一份）：
  · `ui_schema.json` 是**唯一产物规范**；本模块是"把控件对象补成字段全集 + 定键序"的**唯一实现**；
  · 子盒/色表结构（`thumb`/`colorTab`/`bgColorTab`/`point`/`size`）一律**从注册表派生**
    （`ui_schema_loader.type_zero`），不手抄结构；
  · 标量默认值是**发射层口径**（demos ftu 反解的 IDE 全量序列化 + hw-relay 真源），
    与注册表 `default` 的**刻意差异**逐条标注（如 `textview alignment 0` vs 注册表默认 36、
    `button fontSize 18` vs 注册表 16）——**别在这里静默对齐注册表**；
  · 生产史：本文件由 `translate_tools.py` 的 `_SCHEMA_FILL`/`_schema_complete` **整块搬出**
    （2026-10-05，T5.2），搬出前后对同一批 LVGL 夹具产出**逐字节一致**（见
    `REMEDIATION-UI-PIPELINE.md` §9 的 A/B 记录）。

消费方：
  · `translate_tools.py`（LVGL → json）——以别名方式调用本模块，实现唯一；
  · 新前端（Qt/.ui、Android XML、Vue…）**必须**用 `new_control()` / `schema_complete()` 产控件，
    不要再写第三份"字段补全"。
"""
import copy
import os
import re

import ui_schema_loader as _uischema     # 唯一真源：ui_schema.json

__all__ = ['DEFAULT_BY_TYPE', 'KEY_ORDER', 'SIZE_IN_NAME', 'THUMB_EMPTY', 'POINT_ZERO',
           'SIZE_ZERO', 'color_tab', 'tab5', 'schema_complete', 'new_control',
           'required_keys', 'known_types', 'fill_required']


def known_types():
    return _uischema.known_types()


def required_keys(tname):
    return _uischema.required_fields(tname)


SIZE_IN_NAME = re.compile(r'(\d{2,5})x(\d{2,5})')


def color_tab(c0, c1=-1):
    """五色态表：槽位结构与未用槽 -1 从注册表 sharedTypes.colorTab 派生（唯一真源），
    这里只填业务色。未用色态恒写 -1（显式值，非噪音；json-field-mandatory.md）。"""
    tab = _uischema.type_zero('colorTab')
    tab['color0'] = c0
    tab['color1'] = c1
    return tab


def tab5(tab):
    """任意 colorTab/bgColorTab → 五槽（已有值保留，缺槽 -1；槽位来自注册表）。"""
    out = color_tab(-1)
    for i in range(5):
        k = 'color%d' % i
        if isinstance(tab, dict) and k in tab:
            out[k] = tab[k]
    return out


# 子盒零值从注册表派生（唯一真源 ui_schema.json），不再手抄结构：
THUMB_EMPTY = _uischema.type_zero('thumb')   # {'size': {'width': 0, 'height': 0}, 'normalPic': '', 'pressedPic': ''}
POINT_ZERO = _uischema.type_zero('point')    # {'x': 0, 'y': 0}
SIZE_ZERO = _uischema.type_zero('size')      # {'width': 0, 'height': 0}

# 每类型「缺键补齐」表（只补片段里没有的键；已有的键不动）。
# 取值分两层（2026-10-02 注册表化）：
#   · 子盒/色表结构（thumb/colorTab/bgColorTab/point/size）= 注册表派生（见上方 _color_tab/THUMB_EMPTY）；
#   · 标量 = 发射层口径（demos ftu 反解的 IDE 全量序列化 + hw-relay 真源），与注册表 default
#     存在**刻意差异**的已逐条标注「发射层口径」（如 textview alignment 0 vs 注册表默认 36、
#     button fontSize 18 vs 注册表 16 —— 差异清单见 ui_schema.json 维护记录，勿在此静默对齐）。
DEFAULT_BY_TYPE = {
    'textview': {'alignment': 0, 'colorTab': color_tab(0xFFFFFF), 'fontSize': 16,
                 'touchable': False, 'bold': False, 'italic': False, 'visible': True,
                 'rollEnable': False, 'rollDirection': 1, 'rollIntervalTime': 150,
                 'rollStep': 5, 'bgColorTab': color_tab(-1),
                 # 2026-10-03 补齐（真源登记后对账发现 fill 落后；值取实测众数，与真源默认一致）
                 # ⚠️ 故意**不补 backgroundPic**：valueRules.missingImage 说「图片字段置 '' → 控件不可见」，
                 #    而真实 IDE 序列化里 backgroundPic 从不空（全仓 333 处只有 1 处空、且来自我们自己的产物）
                 #    → 空串是否被容忍**未核**，不擅自往 fill 里加（见 CONSOLIDATION §30）。
                 'backgroundColor': -1, 'fontFamily': 0},
    'button': {'alignment': 5, 'colorTab': color_tab(0xFFFFFF), 'text': '',
               'touchable': True, 'visible': True, 'picTab': {},
               'longClickTimeOut': -1, 'longClickIntervalTime': -1,
               'bgColorTab': color_tab(-1), 'fontSize': 18,
               # 2026-10-03 补齐（button-fields.md 实测这些键出现率 97.8%/89% —— 正是本表的同一来源）
               # 同 textview：**不补 backgroundPic**（空串安全性未核）。
               'backgroundColor': -1, 'bold': False, 'italic': False,
               'fontFamily': 0, 'rollEnable': False, 'rollDirection': 1,
               'rollIntervalTime': 150, 'rollStep': 5},
    'window': {'backgroundColor': -1, 'hideTimeOut': -1, 'modal': False,
               'touchable': False, 'visible': True},
    'seekbar': {'backgroundColor': -1, 'backgroundPic': '', 'defProgress': 0, 'max': 100,
                'orientation': 0, 'progressPic': '', 'secondaryProgressPic': '',
                'thumb': THUMB_EMPTY, 'touchable': True, 'visible': True},
    'painter': {'backgroundColor': 0xFFFFFF, 'touchable': False, 'visible': True},
    'edittext': {'alignment': 36, 'bgColorTab': color_tab(0xFFFFFF), 'bold': False,
                 'colorTab': color_tab(0x212121), 'fontSize': 16,
                 'hintTextColor': 0x808080, 'text': '', 'textType': 0,
                 # 2026-10-03 补齐：touchable=True 是硬要求（漏写则输入框点不动、IME 不弹）
                 'touchable': True, 'visible': True, 'italic': False, 'fontFamily': 0,
                 'hintText': '', 'isPassword': False, 'passwordChar': '*',
                 'beepEnable': True, 'rollEnable': False, 'rollDirection': 1,
                 'rollIntervalTime': 150, 'rollStep': 5},
    'circlebar': {'backgroundColor': -1, 'clockwise': True, 'max': 100, 'maxAngle': 360,
                  # ⛔ progressPicPos / touchRange 必须是对象（子盒类型）：写成 int 会让真机
                  #    页面构造时主线程 100% 空转、无日志（V85X 实测 2026-10-04；注册表 v1.1 已改类型）
                  'progressPic': '',
                  'progressPicPos': {'left': 0, 'top': 0, 'width': 0, 'height': 0},
                  'startAngle': 0,
                  'textColor': 0x212121, 'textSize': 24, 'textType': 0,
                  'thumb': THUMB_EMPTY, 'touchRange': {'lower': 0, 'upper': 100},
                  'touchable': False,
                  'unit': '', 'visible': True},
    'pointer': {'animatable': True, 'backgroundColor': -1, 'backgroundPic': '',
                'clockwise': True, 'fixedPoint': copy.deepcopy(POINT_ZERO), 'pointerPic': '',
                'pointerSize': copy.deepcopy(SIZE_ZERO), 'rotateSpeed': 1,
                'rotationPoint': copy.deepcopy(POINT_ZERO), 'startAngle': 0,
                'touchable': False, 'visible': True},
    'qrcode': {'backgroundColor': 0xFFFFFF, 'padding': 10, 'touchable': True,
               'visible': True},
    # 2026-10-05（T5.1 用例抓到的缺口）：注册表里 imageanim.playFile 是**必填**（path），
    # 而本表原先只补 loopCount → 发射层自己就不满足「字段全集」。空串 = 无动图（不是挂死路径）。
    'imageanim': {'loopCount': 0, 'playFile': ''},
}

# IDE 全量序列化的键序（textview/button 有 hw-relay-verify-z20 反解真源）
KEY_ORDER = {
    'textview': ['id', 'caption', 'position', 'alignment', 'colorTab', 'fontSize',
                 'touchable', 'bold', 'italic', 'text', 'visible', 'rollEnable',
                 'rollDirection', 'rollIntervalTime', 'rollStep', 'bgColorTab'],
    'button': ['id', 'caption', 'position', 'alignment', 'colorTab', 'text',
               'touchable', 'visible', 'picTab', 'longClickTimeOut',
               'longClickIntervalTime', 'bgColorTab', 'fontSize'],
}


def schema_complete(tname, ctl, normalize=True):
    """片段控件 → schema 完整字段集（缺键补默认、色表补五槽、thumb 转子盒）。

    `normalize=True`（默认，**迁移/翻译**路径）：再把对齐口径归一 ——
    button 恒 5（居中，IDE 新编码，位模型 ≡37）；textview 片段的旧默认 36（靠左+垂直居中）
    归一到 0（靠左+顶，hw-relay IDE 真源），其余刻意取值（33/37/38 等）不动；textview 空 text 不写。

    `normalize=False`（**前端自带编码**路径，如 `html2json`）：只做**字段补全与结构规范化**
    （缺键、colorTab 五槽、thumb 字符串→子盒），不动调用方自己的 alignment 取值 ——
    因为 36/37 与 0/5 的等价性**尚未真机核实**（登记在 `ui_tools/emit_conformance.json`），
    不擅自统一编码。
    """
    fill = DEFAULT_BY_TYPE.get(tname) or {}
    for k, v in fill.items():
        if k not in ctl:
            ctl[k] = copy.deepcopy(v)
    if isinstance(ctl.get('colorTab'), dict):
        ctl['colorTab'] = tab5(ctl['colorTab'])
    if isinstance(ctl.get('bgColorTab'), dict):
        ctl['bgColorTab'] = tab5(ctl['bgColorTab'])
    if tname == 'button':
        # 按钮按下态（color1）无源信息 → 跟正常态同色（hw-relay 真源同口径）
        for tab in ('colorTab', 'bgColorTab'):
            t = ctl.get(tab)
            if isinstance(t, dict) and t.get('color0', -1) != -1 and t.get('color1') == -1:
                t['color1'] = t['color0']
    if tname in ('seekbar', 'circlebar'):
        th = ctl.get('thumb')
        if isinstance(th, str):                      # 映射片段的字符串旧式 → 子盒
            if th:
                m = SIZE_IN_NAME.search(os.path.basename(th))
                s = int(m.group(1)) if m else 24
                ctl['thumb'] = {'size': {'width': s, 'height': s},
                                'normalPic': th, 'pressedPic': th}
            else:
                ctl['thumb'] = copy.deepcopy(THUMB_EMPTY)
        elif th is None:
            ctl['thumb'] = copy.deepcopy(THUMB_EMPTY)
    if normalize:
        if tname == 'button':
            ctl['alignment'] = 5
        elif tname == 'textview' and ctl.get('alignment') == 36:
            ctl['alignment'] = 0
        if tname == 'textview' and not ctl.get('text'):
            ctl.pop('text', None)                    # textview：text 非空才写
    order = KEY_ORDER.get(tname)
    if order:
        ctl = {k: ctl[k] for k in order if k in ctl} | \
              {k: v for k, v in ctl.items() if k not in order}
    return ctl


def new_control(tname, caption, pos, cid=None, **overrides):
    """**新前端唯一入口**：产一个字段齐全、键序规范的控件对象。

    tname 控件类型；caption 控件名（C 标识符）；pos {left,top,width,height}；
    cid 缺省按 `html2json.ID_BASE` 的段位提示调用方自己给（本函数不猜 id，避免两处段位口径）。
    """
    ctl = {'caption': caption, 'position': dict(pos)}
    if cid is not None:
        ctl['id'] = cid
    ctl.update({k: copy.deepcopy(v) for k, v in overrides.items()})
    return schema_complete(tname, ctl)


def fill_required(tname, ctl):
    """**只补注册表必填键**（缺则用发射层默认值）→ (ctl, 未补上的键列表)。

    与 `schema_complete` 的分工：
      · `schema_complete` = 迁移/翻译路径的「字段全集」（含可选字段、槽位归一、键序）；
      · `fill_required`   = **前端自带编码**路径的最小合规补全 —— 前端有意省略的可选字段
        （例：热区按钮故意不写 `bgColorTab`，写了会盖住下层画布）**不许被强行补回**。
    """
    ctl = ctl if isinstance(ctl, dict) else {}
    dflt = DEFAULT_BY_TYPE.get(tname) or {}
    unfilled = []
    for k in required_keys(tname):
        if k in ('caption', 'position', 'id') or k in ctl:
            continue
        if k in dflt:
            ctl[k] = copy.deepcopy(dflt[k])
        else:
            unfilled.append(k)
    return ctl, unfilled
