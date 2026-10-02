# -*- coding: utf-8 -*-
"""LVGL → FlyThings ui json 迁移翻译器（v1，实现层）。

口径来源（不在这里重复造）：
  - 映射表：仓库根 mcp_control_map.json 的 sources.lvgl（32 条，L1~L5 + 可粘贴 json 片段）
  - 视觉换算铁律 / D-xx 降级登记制 / 四阶段路线：knowledge/devflow/platform-translate.md
  - 本文档化的 v1 边界：knowledge/devflow/translate-ui-lvgl.md

设计原则（v1）：
  - **确定性**：同一份输入永远产出同一份 json（无随机、无时间戳、无网络、stdlib only）。
  - **宁缺毋滥**：识别不了的调用一律进 unrecognized 清单，L3/L4/L5 与未收录控件
    一律进 D-xx 降级登记，**绝不静默丢**。
  - **行/正则解析**（不是 C 编译器）：只认文档里列出的调用形态，多行调用会先拼成单条语句。

坐标口径：LVGL 子控件坐标相对父对象，FlyThings 子控件坐标同样相对父容器 → 直接平移；
LVGL align 在「父几何已知」时换算成绝对坐标（见 _ALIGN），否则登记 D-xx。
"""
import copy
import io
import json
import os
import re
import struct
import sys
import zlib

BASE = os.path.dirname(os.path.abspath(__file__))
_MAP_PATH = os.path.join(BASE, 'mcp_control_map.json')
_UI_TOOLS = os.path.join(BASE, 'ui_tools')
if getattr(sys, 'frozen', False):  # PyInstaller 打包：ui_tools 随包进 _MEIPASS
    _UI_TOOLS = os.path.join(sys._MEIPASS, 'ui_tools')
if _UI_TOOLS not in sys.path:
    sys.path.insert(0, _UI_TOOLS)
import ui_schema_loader as _uischema   # noqa: E402 字段/子盒结构唯一真源（ui_schema.json）
if getattr(sys, 'frozen', False):  # PyInstaller 打包：随包进 _MEIPASS
    _MAP_PATH = os.path.join(sys._MEIPASS, 'mcp_control_map.json')

OP = 'flythings_translate_ui'
KNOWLEDGE_DOC = 'knowledge/devflow/translate-ui-lvgl.md'
DOCTRINE_DOC = 'knowledge/devflow/platform-translate.md'

# 系统级 / 与 UI 布局无关的 LVGL 调用前缀：不识别也不上报（不是 UI 语义丢失）
_IGNORE_PREFIX = ('lv_init', 'lv_deinit', 'lv_tick_', 'lv_timer_', 'lv_task_',
                  'lv_disp_', 'lv_display_', 'lv_fs_', 'lv_indev_', 'lv_group_',
                  'lv_event_send', 'lv_refr_', 'lv_mem_', 'lv_log_', 'lv_anim_del',
                  'lv_style_init', 'lv_style_reset')

# 对齐换算表：LV_ALIGN_x → (x 基准, y 基准)；基准 ∈ left/center/right × top/center/bottom
_ALIGN = {
    'LV_ALIGN_TOP_LEFT': ('left', 'top'), 'LV_ALIGN_TOP_MID': ('center', 'top'),
    'LV_ALIGN_TOP_RIGHT': ('right', 'top'), 'LV_ALIGN_LEFT_MID': ('left', 'center'),
    'LV_ALIGN_CENTER': ('center', 'center'), 'LV_ALIGN_RIGHT_MID': ('right', 'center'),
    'LV_ALIGN_BOTTOM_LEFT': ('left', 'bottom'), 'LV_ALIGN_BOTTOM_MID': ('center', 'bottom'),
    'LV_ALIGN_BOTTOM_RIGHT': ('right', 'bottom'),
    'LV_ALIGN_DEFAULT': ('left', 'top'),
}

_INT_EXPR = re.compile(r'^-?\d+$')
_SIMPLE_EXPR = re.compile(r'^(-?\d+)\s*([-+])\s*(-?\d+)$')
_CREATE_RE = re.compile(
    r'(?:lv_obj_t\s*\*\s*)?(\w+)\s*=\s*(lv_\w+?)_create\s*\(\s*([\w()]*)\s*\)')
_FUNC_RE = re.compile(r'(lv_\w+)\s*\((.*)\)\s*;?\s*$')
_COLOR_HEX = re.compile(r'lv_color_hex\s*\(\s*0x([0-9a-fA-F]{6})\s*\)')
_COLOR_HEX3 = re.compile(r'lv_color_hex3\s*\(\s*0x([0-9a-fA-F]{3})\s*\)')
_FONT_SIZE = re.compile(r'(\d+)\s*$')

# ---------------------------------------------------------------------------
# schema 完整字段集（落地 json-field-mandatory.md「字段全集显式化」铁律）
# 取值基准：demos ftu 反解的 IDE 全量序列化（hw-relay-verify-z20 等）+
# templates/ui_blocks/examples 权威工程（seekbar.thumb 子盒结构）。
# ⚠️ 映射表 mcp_control_map.json 的 json 片段是「最小示例」，不是完整 schema——
#    textview 缺 bgColorTab/bold/italic/visible/roll*、button 缺 visible/longClick*。
#    发射层在此补齐，不动映射表（片段同时服务 map_control 的「最小可粘贴」口径）。
#    （thumb 字符串形态曾是挂死真凶，2026-10-02 A/B 终裁后映射表已修为子盒对象。）
# ---------------------------------------------------------------------------

# ⚠️ A/B 终裁（2026-10-02，V85X iMirror 固件，temp/abtest_a/b 对照）：
#    致命的是「子盒对象字段写成字符串」（典型 seekbar.thumb）→ ftu 加载无声挂死
#    （无 onUI_init/onUI_show、无报错日志）。thumb 对象+缺图 = 正常；thumb 字符串+有图 = 挂死。
#    缺图本身不致命：引用不存在文件或置 '' → 控件不可见（framework 容错），但属验收缺陷，
#    故仍默认剥除/出占位图，保证「该显示的都能看到」。
IMG_HANG_RULE = ('缺图不致命（控件不可见，framework 容错）但属验收缺陷，故剥除/出占位图；'
                 '真正致命的是 thumb 等子盒字段写成字符串 = ftu 加载无声挂死'
                 '（A/B 实测 V85X iMirror 固件 2026-10-02）')

# 字符串图片字段（值为 '' 即无图）；picTab/thumb 子盒单独处理
_PIC_STR_FIELDS = ('backgroundPic', 'progressPic', 'secondaryProgressPic',
                   'thumbPic', 'pointerPic', 'playFile')
_SIZE_IN_NAME = re.compile(r'(\d{2,5})x(\d{2,5})')


def _color_tab(c0, c1=-1):
    """五色态表：槽位结构与未用槽 -1 从注册表 sharedTypes.colorTab 派生（唯一真源），
    这里只填业务色。未用色态恒写 -1（显式值，非噪音；json-field-mandatory.md）。"""
    tab = _uischema.type_zero('colorTab')
    tab['color0'] = c0
    tab['color1'] = c1
    return tab


def _tab5(tab):
    """任意 colorTab/bgColorTab → 五槽（已有值保留，缺槽 -1；槽位来自注册表）。"""
    out = _color_tab(-1)
    for i in range(5):
        k = 'color%d' % i
        if isinstance(tab, dict) and k in tab:
            out[k] = tab[k]
    return out


# 子盒零值从注册表派生（唯一真源 ui_schema.json），不再手抄结构：
_THUMB_EMPTY = _uischema.type_zero('thumb')   # {'size': {'width': 0, 'height': 0}, 'normalPic': '', 'pressedPic': ''}
_POINT_ZERO = _uischema.type_zero('point')    # {'x': 0, 'y': 0}
_SIZE_ZERO = _uischema.type_zero('size')      # {'width': 0, 'height': 0}

# 每类型「缺键补齐」表（只补片段里没有的键；已有的键不动）。
# 取值分两层（2026-10-02 注册表化）：
#   · 子盒/色表结构（thumb/colorTab/bgColorTab/point/size）= 注册表派生（见上方 _color_tab/_THUMB_EMPTY）；
#   · 标量 = 发射层口径（demos ftu 反解的 IDE 全量序列化 + hw-relay 真源），与注册表 default
#     存在**刻意差异**的已逐条标注「发射层口径」（如 textview alignment 0 vs 注册表默认 36、
#     button fontSize 18 vs 注册表 16 —— 差异清单见 ui_schema.json 维护记录，勿在此静默对齐）。
_SCHEMA_FILL = {
    'textview': {'alignment': 0, 'colorTab': _color_tab(0xFFFFFF), 'fontSize': 16,
                 'touchable': False, 'bold': False, 'italic': False, 'visible': True,
                 'rollEnable': False, 'rollDirection': 1, 'rollIntervalTime': 150,
                 'rollStep': 5, 'bgColorTab': _color_tab(-1)},
    'button': {'alignment': 5, 'colorTab': _color_tab(0xFFFFFF), 'text': '',
               'touchable': True, 'visible': True, 'picTab': {},
               'longClickTimeOut': -1, 'longClickIntervalTime': -1,
               'bgColorTab': _color_tab(-1), 'fontSize': 18},
    'window': {'backgroundColor': -1, 'hideTimeOut': -1, 'modal': False,
               'touchable': False, 'visible': True},
    'seekbar': {'backgroundColor': -1, 'backgroundPic': '', 'defProgress': 0, 'max': 100,
                'orientation': 0, 'progressPic': '', 'secondaryProgressPic': '',
                'thumb': _THUMB_EMPTY, 'touchable': True, 'visible': True},
    'painter': {'backgroundColor': 0xFFFFFF, 'touchable': False, 'visible': True},
    'edittext': {'alignment': 36, 'bgColorTab': _color_tab(0xFFFFFF), 'bold': False,
                 'colorTab': _color_tab(0x212121), 'fontSize': 16,
                 'hintTextColor': 0x808080, 'text': '', 'textType': 0},
    'circlebar': {'backgroundColor': -1, 'clockwise': True, 'max': 100, 'maxAngle': 360,
                  'progressPic': '', 'progressPicPos': 0, 'startAngle': 0,
                  'textColor': 0x212121, 'textSize': 24, 'textType': 0,
                  'thumb': _THUMB_EMPTY, 'touchRange': 0, 'touchable': False,
                  'unit': '', 'visible': True},
    'pointer': {'animatable': True, 'backgroundColor': -1, 'backgroundPic': '',
                'clockwise': True, 'fixedPoint': copy.deepcopy(_POINT_ZERO), 'pointerPic': '',
                'pointerSize': copy.deepcopy(_SIZE_ZERO), 'rotateSpeed': 1,
                'rotationPoint': copy.deepcopy(_POINT_ZERO), 'startAngle': 0,
                'touchable': False, 'visible': True},
    'qrcode': {'backgroundColor': 0xFFFFFF, 'padding': 10, 'touchable': True,
               'visible': True},
    'imageanim': {'loopCount': 0},
}

# IDE 全量序列化的键序（textview/button 有 hw-relay-verify-z20 反解真源）
_KEY_ORDER = {
    'textview': ['id', 'caption', 'position', 'alignment', 'colorTab', 'fontSize',
                 'touchable', 'bold', 'italic', 'text', 'visible', 'rollEnable',
                 'rollDirection', 'rollIntervalTime', 'rollStep', 'bgColorTab'],
    'button': ['id', 'caption', 'position', 'alignment', 'colorTab', 'text',
               'touchable', 'visible', 'picTab', 'longClickTimeOut',
               'longClickIntervalTime', 'bgColorTab', 'fontSize'],
}


def _schema_complete(tname, ctl):
    """片段控件 → schema 完整字段集（缺键补默认、色表补五槽、thumb 转子盒）。

    alignment 口径：button 恒 5（居中，IDE 新编码，位模型 ≡37）；textview 片段的
    旧默认 36（靠左+垂直居中）归一到 0（靠左+顶，hw-relay IDE 真源），
    其余值（33/37/38 等模板装饰件的刻意取值）不动。
    """
    fill = _SCHEMA_FILL.get(tname) or {}
    for k, v in fill.items():
        if k not in ctl:
            ctl[k] = copy.deepcopy(v)
    if isinstance(ctl.get('colorTab'), dict):
        ctl['colorTab'] = _tab5(ctl['colorTab'])
    if isinstance(ctl.get('bgColorTab'), dict):
        ctl['bgColorTab'] = _tab5(ctl['bgColorTab'])
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
                m = _SIZE_IN_NAME.search(os.path.basename(th))
                s = int(m.group(1)) if m else 24
                ctl['thumb'] = {'size': {'width': s, 'height': s},
                                'normalPic': th, 'pressedPic': th}
            else:
                ctl['thumb'] = copy.deepcopy(_THUMB_EMPTY)
        elif th is None:
            ctl['thumb'] = copy.deepcopy(_THUMB_EMPTY)
    if tname == 'button':
        ctl['alignment'] = 5
    elif tname == 'textview' and ctl.get('alignment') == 36:
        ctl['alignment'] = 0
    if tname == 'textview' and not ctl.get('text'):
        ctl.pop('text', None)                        # textview：text 非空才写
    order = _KEY_ORDER.get(tname)
    if order:
        ctl = {k: ctl[k] for k in order if k in ctl} | \
              {k: v for k, v in ctl.items() if k not in order}
    return ctl


def _solid_png(path, w, h, rgba):
    """stdlib 纯色 PNG（无 PIL 依赖；供 gen_placeholders 出占位图）。"""
    def chunk(typ, data):
        return struct.pack('>I', len(data)) + typ + data + \
            struct.pack('>I', zlib.crc32(typ + data) & 0xFFFFFFFF)
    raw = (b'\x00' + bytes(rgba) * w) * h
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
    io.open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
                              + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


# 1x1 透明 GIF（imageanim playFile 占位；PNG 救不了 .gif 引用）
_TINY_GIF = (b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\x00\x00\x00'
             b'!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00'
             b'\x02\x02D\x01\x00;')

# 占位图配色（仅离线确认稿用，正式图走 flythings_generate_ui_assets）
_PLACEHOLDER_COLORS = {'backgroundPic': (0x55, 0x55, 0x5E, 0xFF),
                       'progressPic': (0x2E, 0x6B, 0xE6, 0xFF),
                       'secondaryProgressPic': (0x9A, 0x9A, 0xA2, 0xFF),
                       'thumbPic': (0xCC, 0xCC, 0xCC, 0xFF),
                       'pointerPic': (0xCC, 0xCC, 0xCC, 0xFF)}


def _img_exists(proj, ref):
    """引用是否已落盘（ui/images 或 resources/images，按 basename 兜底）。"""
    if not proj:
        return False
    base = os.path.basename(ref.replace('\\', '/'))
    for d in (os.path.join(proj, 'ui', 'images'), os.path.join(proj, 'resources', 'images')):
        if os.path.isfile(os.path.join(d, base)):
            return True
    return False


def _gen_placeholder(proj, ref, field, box):
    """gen_placeholders=True：往 <项目>/ui/images/ 出一张占位图（尺寸 = 控件盒，图==盒铁律）。

    文件名里的 WxH 是映射片段模板屏（1024x600）的尺寸，不是本页控件盒——按盒出图，
    否则 check_all #11（自动生成图尺寸必须 == 盒）必 FAIL。返回落盘的绝对路径。
    """
    base = os.path.basename(ref.replace('\\', '/'))
    img_dir = os.path.join(proj, 'ui', 'images')
    if not os.path.isdir(img_dir):
        os.makedirs(img_dir)
    ap = os.path.join(img_dir, base)
    if base.lower().endswith('.gif'):
        io.open(ap, 'wb').write(_TINY_GIF)
        return ap
    m = _SIZE_IN_NAME.search(base)
    if box and box[0] and box[1]:
        w, h = int(box[0]), int(box[1])
    elif m:
        w, h = int(m.group(1)), int(m.group(2))
    else:
        w = h = 24
    w = max(1, min(w, 2048))
    h = max(1, min(h, 2048))
    rgba = _PLACEHOLDER_COLORS.get(field, (0x88, 0x88, 0x88, 0xFF))
    _solid_png(ap, w, h, rgba)
    return ap


def _image_policy(w, ctl, proj, gen_assets, write_mode):
    """缺图引用处置（硬规则见 IMG_HANG_RULE）。返回 [(field, ref, action, path_or_None)]。

    优先级：已落盘 → 保留（kept）；gen_placeholders 且写盘模式 → 出占位图（generated）；
    其余 → 剥除（stripped：字符串字段置 ''、picTab 删条、thumb 子盒清空），
    控件「隐形但无害」，正式图由 flythings_generate_ui_assets 补回后引用再写回。
    dry_run 下 gen_placeholders 不落盘，按「将生成」保留引用（pending），写盘时才真出图。
    """
    acts = []

    def decide(field, ref, box):
        if _img_exists(proj, ref):
            return 'kept', None
        if gen_assets:
            if write_mode and proj:
                return 'generated', _gen_placeholder(proj, ref, field, box)
            return 'pending', None                    # dry_run：保留引用，写盘时出图
        return 'stripped', None

    box = None
    pos = ctl.get('position') or {}
    if pos.get('width') and pos.get('height'):
        box = (pos['width'], pos['height'])
    for fld in _PIC_STR_FIELDS:
        ref = ctl.get(fld)
        if not (isinstance(ref, str) and ref):
            continue
        action, ap = decide(fld, ref, box)
        if action == 'stripped':
            ctl[fld] = ''
        acts.append((fld, ref, action, ap))
    pt = ctl.get('picTab')
    if isinstance(pt, dict):
        for fld in sorted(pt.keys()):
            ref = pt[fld]
            if not (isinstance(ref, str) and ref):
                continue
            action, ap = decide('picTab.' + fld, ref, box)
            if action == 'stripped':
                del pt[fld]
            acts.append(('picTab.' + fld, ref, action, ap))
    th = ctl.get('thumb')
    if isinstance(th, dict):
        tbox = None
        sz = th.get('size') or {}
        if sz.get('width') and sz.get('height'):
            tbox = (sz['width'], sz['height'])
        stripped_thumb = False
        for fld in ('normalPic', 'pressedPic'):
            ref = th.get(fld)
            if not (isinstance(ref, str) and ref):
                continue
            action, ap = decide('thumb.' + fld, ref, tbox)
            if action == 'stripped':
                th[fld] = ''
                stripped_thumb = True
            acts.append(('thumb.' + fld, ref, action, ap))
        if stripped_thumb:
            th['size'] = {'width': 0, 'height': 0}   # 无图滑块按只读形态清零
    return acts


def _err(code, msg, hint='', retryable=False):
    return {'ok': False, 'op': OP,
            'error': {'code': code, 'msg': str(msg), 'hint': hint,
                      'retryable': bool(retryable)},
            'warnings': []}


_MAP_CACHE = {}


def _control_map():
    """读 mcp_control_map.json（带缓存）。失败回 (None, 原因)，不静默。"""
    if 'err' in _MAP_CACHE:
        return None, _MAP_CACHE['err']
    if 'data' not in _MAP_CACHE:
        try:
            _MAP_CACHE['data'] = json.loads(io.open(_MAP_PATH, encoding='utf-8').read())
        except Exception as e:  # 文件缺失/损坏必须显式报错（门禁 lint_silent_except）
            _MAP_CACHE['err'] = 'mcp_control_map.json 读取失败（%s: %s）' % (type(e).__name__, e)
            return None, _MAP_CACHE['err']
    return _MAP_CACHE['data'], ''


def _norm(name):
    """控件名归一：小写、去 lv_ 前缀、去括号及以后、只留字母数字。"""
    s = (name or '').lower().split('(')[0].split('（')[0]
    if s.startswith('lv_'):
        s = s[3:]
    return re.sub(r'[^a-z0-9]', '', s)


def _lvgl_index(data):
    """lvgl 条目索引：norm(name)/norm(alias) → entry。名字精确条目优先（文件顺序）。"""
    idx = {}
    for e in data['sources']['lvgl']:
        for key in [e.get('name', '')] + list(e.get('aliases') or []):
            k = _norm(key)
            if k and k not in idx:
                idx[k] = e
    return idx


# ---------------------------------------------------------------------------
# 语句切分：剥注释 + 多行拼句（圆括号配平为止）
# ---------------------------------------------------------------------------

def _strip_comments(src):
    out, i, n = [], 0, len(src)
    in_str = in_chr = False
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ''
        if in_str:
            out.append(c)
            if c == '\\' and i + 1 < n:
                out.append(src[i + 1])
                i += 1
            elif c == '"':
                in_str = False
        elif in_chr:
            out.append(c)
            if c == '\\' and i + 1 < n:
                out.append(src[i + 1])
                i += 1
            elif c == "'":
                in_chr = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif c == "'":
            in_chr = True
            out.append(c)
        elif c == '/' and nxt == '*':
            j = src.find('*/', i + 2)
            seg = src[i:j if j >= 0 else n]
            out.append('\n' * seg.count('\n'))   # 保行号
            i = (j + 1) if j >= 0 else n - 1
        elif c == '/' and nxt == '/':
            j = src.find('\n', i)
            if j < 0:
                break
            i = j - 1
        else:
            out.append(c)
        i += 1
    return ''.join(out)


def _statements(src):
    """→ [(起始行号, 单条语句文本)]；按圆括号配平拼多行调用。"""
    clean = _strip_comments(src)
    stmts, buf, start, depth = [], '', 0, 0
    for ln, line in enumerate(clean.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        if not buf:
            start = ln
        buf = (buf + ' ' + s).strip() if buf else s
        depth += line.count('(') - line.count(')')
        if depth <= 0 and (';' in line or not buf.endswith((',', '('))):
            depth = 0
            stmts.append((start, buf))
            buf = ''
    if buf:
        stmts.append((start, buf))
    return stmts


# ---------------------------------------------------------------------------
# 参数小工具
# ---------------------------------------------------------------------------

def _split_args(s):
    """顶层逗号切参数（括号/字符串感知）。"""
    args, cur, depth = [], '', 0
    in_str = in_chr = False
    for c in s:
        if in_str:
            cur += c
            if c == '"':
                in_str = False
        elif in_chr:
            cur += c
            if c == "'":
                in_chr = False
        elif c == '"':
            in_str, cur = True, cur + c
        elif c == "'":
            in_chr, cur = True, cur + c
        elif c == '(':
            depth, cur = depth + 1, cur + c
        elif c == ')':
            depth, cur = depth - 1, cur + c
        elif c == ',' and depth == 0:
            args.append(cur.strip())
            cur = ''
        else:
            cur += c
    if cur.strip():
        args.append(cur.strip())
    return args


def _parse_int(expr):
    """整数字面量 / int±int → 值；其余表达式 → None（交由调用方登记）。"""
    e = (expr or '').strip().rstrip('UuLl')
    if _INT_EXPR.match(e):
        return int(e)
    m = _SIMPLE_EXPR.match(e)
    if m:
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        return a + b if op == '+' else a - b
    return None


def _parse_color(expr):
    """lv_color_hex/hex3/white/black → (int 颜色, 备注)；其余 → (None, 原因)。

    铁律（html-subset-quickref）：#000000 会被转换器当「未设置」，纯黑写 #010101。
    """
    e = (expr or '').strip()
    m = _COLOR_HEX.search(e)
    if m:
        v = int(m.group(1), 16)
        if v == 0:
            return 0x010101, '纯黑 #000000 按铁律改写为 #010101（0 会被当未设置）'
        return v, ''
    m = _COLOR_HEX3.search(e)
    if m:
        h = m.group(1)
        v = int(''.join(c * 2 for c in h), 16)
        if v == 0:
            return 0x010101, '纯黑 #000000 按铁律改写为 #010101（0 会被当未设置）'
        return v, ''
    if 'lv_color_white' in e:
        return 0xFFFFFF, ''
    if 'lv_color_black' in e:
        return 0x010101, '纯黑 #000000 按铁律改写为 #010101（0 会被当未设置）'
    return None, '颜色表达式未识别（%s）' % e[:40]


def _unquote(s):
    s = (s or '').strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1].replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
    return None


def _camel(var):
    parts = re.split(r'[^0-9A-Za-z]+', var or '')
    out = ''.join(p[:1].upper() + p[1:] for p in parts if p)
    if out and out[0].isdigit():
        out = 'N' + out
    return out


def _caption_prefix(caption):
    m = re.match(r'^([A-Z][a-z]*)[A-Z]', caption or '')
    return m.group(1) if m else 'Ctl'


def _align_xy(spec, pw, ph, w, h, dx, dy):
    ax, ay = spec
    left = dx if ax == 'left' else (pw - w + dx if ax == 'right' else (pw - w) // 2 + dx)
    top = dy if ay == 'top' else (ph - h + dy if ay == 'bottom' else (ph - h) // 2 + dy)
    return left, top


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

class _Widget(object):
    __slots__ = ('var', 'lv', 'entry', 'level', 'line', 'parent', 'is_screen',
                 'x', 'y', 'w', 'h', 'align', 'text', 'bg', 'fg', 'font', 'radius',
                 'hidden', 'rng_max', 'value', 'img_src', 'events', 'notes',
                 'key', 'caption', 'ctl')

    def __init__(self, var, lv, entry, line, parent, is_screen):
        self.var, self.lv, self.entry, self.line = var, lv, entry, line
        self.parent, self.is_screen = parent, is_screen
        self.key = self.caption = ''
        self.ctl = None

    def __init__(self, var, lv, entry, line, parent, is_screen):
        self.var, self.lv, self.entry, self.line = var, lv, entry, line
        self.parent, self.is_screen = parent, is_screen
        self.level = (entry or {}).get('level', 'L?')
        self.x = self.y = self.w = self.h = None
        self.align = None
        self.text = self.font = self.img_src = None
        self.bg = self.fg = None
        self.radius = None
        self.hidden = False
        self.rng_max = self.value = None
        self.events = []
        self.notes = []


def translate(source, out='', res='1024x600', dry_run=True, gen_placeholders=False):
    """LVGL C 源码 → FlyThings ui json。返回 envelope-ready dict（ok/…）。"""
    data, merr = _control_map()
    if data is None:
        return _err('DATA_MISSING', merr, '确认 mcp_control_map.json 随包分发')
    # ---- 输入：文件路径 或 内联源码 ----
    src_name = '<inline>'
    if os.path.isfile(source or ''):
        src_name = os.path.abspath(source)
        try:
            text = io.open(src_name, encoding='utf-8', errors='replace').read()
        except OSError as e:
            return _err('READ_FAILED', '%s' % e, '检查文件权限/路径', True)
    elif source and ('lv_' in source or '\n' in source):
        text = source
    else:
        return _err('NO_SOURCE', 'source 不是已存在的文件，也不像 LVGL 源码',
                    '传 LVGL .c 文件路径，或直接传内联源码字符串', True)
    # ---- 分辨率 ----
    m = re.match(r'^(\d{2,5})\s*[xX×*]\s*(\d{2,5})$', str(res or '').strip())
    if not m:
        return _err('BAD_PARAMS', 'res 无法解析: %r' % res,
                    '格式如 1024x600（迁移基准屏，见 platform-translate.md §2）', True)
    W, H = int(m.group(1)), int(m.group(2))

    idx = _lvgl_index(data)
    targets = data.get('targets') or {}

    # 项目根（out = <项目>/ui/main.json）：图片存在性核对与占位图落盘都按它定位
    proj = ''
    if out:
        proj = os.path.dirname(os.path.dirname(os.path.abspath(out)))

    widgets = {}            # var → _Widget
    order = []              # 创建顺序（z 序 = 书写顺序，必须保序）
    unrecognized = []       # [{line, call, reason}]
    downgrades = []         # D-xx 登记表
    image_actions = []      # 缺图引用处置登记（硬规则 IMG_HANG_RULE）
    warnings = []
    screens = 0

    def d_add(w, level, reason, action):
        downgrades.append({'id': 'D-%02d' % (len(downgrades) + 1),
                           'line': w.line if w else 0,
                           'widget': (w.var if w else '') or '-',
                           'lvType': (w.lv if w else '') or '-',
                           'level': level, 'reason': reason, 'action': action})

    for ln, stmt in _statements(text):
        cm = _CREATE_RE.search(stmt)
        fm = _FUNC_RE.search(stmt)
        if cm:
            var, func, parent = cm.group(1), cm.group(2), (cm.group(3) or '').strip()
            base = func[3:] if func.startswith('lv_') else func
            entry = idx.get(_norm(base))
            is_screen = base == 'obj' and (parent in ('NULL', '') or 'lv_scr_act' in parent
                                           or 'lv_screen_active' in parent)
            if entry is None:
                w = _Widget(var, func, None, ln, parent, is_screen)
                d_add(w, 'L?', '映射表（mcp_control_map.json lvgl 32 条）未收录该控件',
                      '先 flythings_map_control(query="%s") 查别名；真缺 → components/ui_v1/ 评估'
                      % func)
                warnings.append('%s（第 %d 行）未收录 → 已用占位 textview，需人工映射' % (func, ln))
            else:
                w = _Widget(var, func, entry, ln, parent, is_screen)
                if entry.get('level') in ('L3', 'L4', 'L5'):
                    d_add(w, entry['level'],
                          (entry.get('notes') or '非等价映射')[:120],
                          (entry.get('ref') and '参考 %s；' % entry['ref'] or '')
                          + '按 platform-translate.md §4 登记降级点，别现场发明')
            if is_screen:
                screens += 1
                if screens > 1:
                    d_add(w, 'L2', '多屏：平台无多 Activity 页栈，多页 = 整屏 window + showWnd/hideWnd',
                          '见 platform-translate.md §4（D-01 类）；已生成为顶层 window，visible:false')
                    w.is_screen = False      # 第二屏起 → 顶层 window
            widgets[var] = w
            order.append(w)
            continue
        if not fm:
            continue
        func, argstr = fm.group(1), fm.group(2)
        args = _split_args(argstr)
        obj = widgets.get(args[0]) if args else None

        def unrec(reason):
            unrecognized.append({'line': ln, 'call': stmt[:120], 'reason': reason})

        if obj is None:
            if func.startswith(_IGNORE_PREFIX):
                continue
            if func.endswith('_create'):
                continue     # 返回值未赋给变量的 create：已在创建正则外，报一下更诚实
            unrec('作用对象不是已识别的控件变量（或 v1 未支持的调用形态）')
            continue
        # ---- 已识别控件上的属性调用 ----
        if func in ('lv_obj_set_pos',) and len(args) >= 3:
            x, y = _parse_int(args[1]), _parse_int(args[2])
            if x is None or y is None:
                unrec('坐标表达式 v1 不求值（仅整数字面量/int±int）')
            else:
                obj.x, obj.y = x, y
        elif func == 'lv_obj_set_x' and len(args) >= 2:
            v = _parse_int(args[1])
            obj.x = v if v is not None else unrec('x 表达式不求值') or obj.x
        elif func == 'lv_obj_set_y' and len(args) >= 2:
            v = _parse_int(args[1])
            obj.y = v if v is not None else unrec('y 表达式不求值') or obj.y
        elif func == 'lv_obj_set_size' and len(args) >= 3:
            w2, h2 = _parse_int(args[1]), _parse_int(args[2])
            if w2 is None or h2 is None:
                unrec('尺寸表达式 v1 不求值（如 LV_PCT/LV_SIZE_CONTENT）')
            else:
                obj.w, obj.h = w2, h2
        elif func == 'lv_obj_set_width' and len(args) >= 2:
            v = _parse_int(args[1])
            if v is None:
                unrec('宽表达式不求值（如 LV_PCT）')
            else:
                obj.w = v
        elif func == 'lv_obj_set_height' and len(args) >= 2:
            v = _parse_int(args[1])
            if v is None:
                unrec('高表达式不求值（如 LV_PCT）')
            else:
                obj.h = v
        elif func in ('lv_obj_align', 'lv_obj_align_to') and len(args) >= 4:
            if func == 'lv_obj_align_to':
                unrec('align_to（相对兄弟控件）v1 不换算，请手工核对坐标')
                continue
            spec = _ALIGN.get(args[1].strip())
            if spec is None:
                unrec('对齐方式未收录：%s' % args[1])
            else:
                dx, dy = _parse_int(args[2]) or 0, _parse_int(args[3]) or 0
                obj.align = (spec, dx, dy)
        elif func == 'lv_obj_center':
            obj.align = (_ALIGN['LV_ALIGN_CENTER'], 0, 0)
        elif func == 'lv_obj_set_align':
            unrec('set_align（影响后续布局的对齐模式）v1 不跟踪，请核对最终坐标')
        elif func in ('lv_label_set_text', 'lv_textarea_set_text') and len(args) >= 2:
            t = _unquote(args[1])
            if t is None:
                unrec('文本不是字符串字面量（动态文本请运行期 setText）')
            else:
                obj.text = t
        elif func == 'lv_label_set_text_fmt':
            unrec('text_fmt 为动态文本：迁到运行期 setText，json 里请手填占位文本')
        elif func == 'lv_obj_set_style_bg_color' and len(args) >= 2:
            sel = args[2] if len(args) >= 3 else '0'
            if sel.strip() not in ('0',) and 'LV_PART_MAIN' not in sel:
                unrec('非主选择器的 bg_color（%s）v1 不换算' % sel.strip()[:30])
            else:
                v, note = _parse_color(args[1])
                if v is None:
                    unrec(note)
                else:
                    obj.bg = v
                    if note:
                        obj.notes.append(note)
        elif func == 'lv_obj_set_style_bg_opa' and len(args) >= 2:
            a2 = args[1].strip()
            if a2 in ('LV_OPA_0', 'LV_OPA_TRANSP', '0'):
                obj.bg = -1
                obj.notes.append('背景透明 → backgroundColor:-1')
            else:
                unrec('bg_opa 非全透明取值 v1 不换算（半透明请先合成纯色）')
        elif func == 'lv_obj_set_style_text_color' and len(args) >= 2:
            v, note = _parse_color(args[1])
            if v is None:
                unrec(note)
            else:
                obj.fg = v
                if note:
                    obj.notes.append(note)
        elif func == 'lv_obj_set_style_text_font' and len(args) >= 2:
            fsz = _FONT_SIZE.search(args[1].strip().rstrip('&'))
            if fsz:
                obj.font = int(fsz.group(1))
            else:
                unrec('字体名里读不出字号（%s）' % args[1].strip()[:40])
        elif func == 'lv_obj_set_style_radius' and len(args) >= 2:
            r = _parse_int(args[1])
            if r and r > 0:
                obj.radius = r
                d_add(obj, 'L2', '圆角/药丸平台不直接支持，一律出图（SS 超采样，图尺寸==控件盒）',
                      '按 ui-asset-rules / nine-patch-rule 出圆角底图挂 backgroundPic/picTab')
        elif func.startswith('lv_obj_set_style_pad'):
            d_add(obj, 'L4', 'padding 无对应属性，需折算进子控件几何（内边距 → 子控件位置/尺寸）',
                  '按 platform-translate.md §2 视觉换算手工核几何')
        elif func == 'lv_obj_add_event_cb' and len(args) >= 3:
            obj.events.append({'callback': args[1].strip(), 'event': args[2].strip(), 'line': ln})
        elif func == 'lv_obj_add_flag' and len(args) >= 2 and 'HIDDEN' in args[1]:
            obj.hidden = True
        elif func == 'lv_obj_clear_flag' and len(args) >= 2 and 'HIDDEN' in args[1]:
            obj.hidden = False
        elif func in ('lv_slider_set_range', 'lv_bar_set_range', 'lv_arc_set_range') \
                and len(args) >= 3:
            v = _parse_int(args[2])
            if v is not None:
                obj.rng_max = v
        elif func in ('lv_slider_set_value', 'lv_bar_set_value', 'lv_arc_set_value') \
                and len(args) >= 2:
            v = _parse_int(args[1])
            if v is not None:
                obj.value = v
        elif func == 'lv_img_set_src' and len(args) >= 2:
            t = _unquote(args[1])
            if t:
                obj.img_src = os.path.basename(t.replace('\\', '/'))
                obj.notes.append('图片源 %s → 需拷入 resources/images/ 并保持图==盒' % t)
            else:
                unrec('img src 不是字符串字面量（符号/路径变量请手工落图）')
        else:
            if func.startswith(_IGNORE_PREFIX):
                continue
            unrec('v1 未支持的调用（识别清单见 %s）' % KNOWLEDGE_DOC)

    if not order:
        return _err('NO_WIDGETS', '没有识别到任何 lv_*_create 调用',
                    '确认源码是 LVGL v8/v9 风格；识别形态见 %s' % KNOWLEDGE_DOC, True)

    # ---- 生成 FlyThings 控件（每控件一条，模板取映射条目片段的首个控件）----
    page = {'backgroundColor': 0xFFFFFF, 'beepEnable': True, 'id': 0,
            'resolution': {'height': H, 'width': W}, 'topmost': False,
            'position': {'height': H, 'left': 0, 'top': 0, 'width': W}}
    warnings.append('页底色默认 #FFFFFF（屏幕 bg_color 可覆盖）；几何单位为 px，'
                    '迁移换算口径见 platform-translate.md §2')
    type_cnt, used_ids, rep_widgets = {}, set(), []

    def template_for(w):
        frag = (w.entry or {}).get('json') or ''
        if not frag and w.entry:
            frag = (targets.get(w.entry.get('target')) or {}).get('json') or ''
        if frag:
            try:
                obj = json.loads(frag)
            except ValueError as e:
                # 片段损坏不静默：记 warning 并回退占位控件（结果仍确定）
                warnings.append('映射片段解析失败（%s）→ %s 用占位控件' % (w.lv, str(e)[:60]))
                obj = None
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(v, dict) and '__' in k:
                        return k.split('__')[0], dict(v)
        return None, None

    def emit(w):
        tname, tpl = template_for(w)
        if tname is None:                      # 无片段（L5/未收录）→ 占位 textview
            tname, tpl = 'textview', {'id': 50001, 'caption': 'TvTodo',
                                      'position': {'left': 0, 'top': 0, 'width': 200, 'height': 24},
                                      'colorTab': _color_tab(0xFF0000),
                                      'fontSize': 18,
                                      'text': '[TODO %s]' % w.lv}
            w.notes.append('无等价控件片段：红字占位，按 D-xx 登记处理')
        type_cnt[tname] = type_cnt.get(tname, 0) + 1
        key = '%s__%d' % (tname, type_cnt[tname])
        ctl = tpl
        base_id = ctl.get('id', 10000) or 10000
        nid = base_id + (type_cnt[tname] - 1)
        while nid in used_ids:
            nid += 1
        used_ids.add(nid)
        ctl['id'] = nid
        prefix = _caption_prefix(str(ctl.get('caption', '')))
        stem = _camel(w.var) or ('Auto%d' % type_cnt[tname])
        if stem.lower().endswith(prefix.lower()):       # apply_btn → BtnApply（不产 BtnApplyBtn）
            stem = stem[:-len(prefix)] or stem
        ctl['caption'] = stem if stem.lower().startswith(prefix.lower()) else prefix + stem
        # 几何：pos 优先，其次 align（父几何已知时），缺省用模板尺寸
        pos = ctl.setdefault('position', {'left': 0, 'top': 0, 'width': 100, 'height': 40})
        pw, ph = W, H
        parent_w0 = widgets.get(w.parent or '')
        _CONTAINERS = ('window', 'scrollwindow', 'pagewindow', 'slidewindow', 'window_modal')
        if parent_w0 is not None and not parent_w0.is_screen \
                and (parent_w0.entry or {}).get('target') in _CONTAINERS:
            pw = parent_w0.w if parent_w0.w is not None else W
            ph = parent_w0.h if parent_w0.h is not None else H
        if w.w is not None:
            pos['width'] = w.w
        if w.h is not None:
            pos['height'] = w.h
        if w.x is not None:
            pos['left'] = w.x
        if w.y is not None:
            pos['top'] = w.y
        if w.align and (w.x is None or w.y is None):
            (spec, dx, dy) = w.align
            l, t = _align_xy(spec, pw, ph, pos['width'], pos['height'], dx, dy)
            if w.x is None:
                pos['left'] = l
            if w.y is None:
                pos['top'] = t
        # 文本：源没写过的控件清空模板示例文本（不泄漏「提交/标题」样例字）
        if w.text is not None and 'text' in ctl:
            ctl['text'] = w.text
        elif 'text' in ctl and tname in ('button', 'textview', 'edittext'):
            ctl['text'] = ''
        if w.font is not None:
            fs = w.font
            if tname in ('textview', 'button', 'edittext') and fs < 18:
                d_add(w, 'L4', '字号下限：正文/按钮 ≥18px（源 %dpx 已抬到 18px，'
                               '小控件盒会比源稿大）' % fs,
                      '按 text-box-height-rule 复核盒高；平台换算口径 platform-translate.md §2')
                fs = 18
            if 'fontSize' in ctl:
                ctl['fontSize'] = fs
        # 颜色
        if w.bg is not None:
            if 'bgColorTab' in ctl and tname != 'window':
                ctl['bgColorTab'] = {'color0': w.bg}
            else:
                ctl['backgroundColor'] = w.bg
        if w.fg is not None and 'colorTab' in ctl:
            ctl['colorTab'] = {'color0': w.fg}
        if w.img_src and 'backgroundPic' in ctl:
            ctl['backgroundPic'] = 'images/' + w.img_src
        if w.rng_max is not None and 'max' in ctl:
            ctl['max'] = w.rng_max
        if w.value is not None and 'defProgress' in ctl:
            ctl['defProgress'] = w.value
        if w.hidden:
            ctl['visible'] = False
        # schema 完整化（缺键/五槽色表/thumb 子盒/alignment 归一）→ 缺图引用处置
        ctl = _schema_complete(tname, ctl)
        for fld, ref, action, ap in _image_policy(w, ctl, proj, gen_placeholders,
                                                  not dry_run):
            image_actions.append({'widget': w.var, 'key': key, 'field': fld,
                                  'ref': ref, 'action': action, 'path': ap})
        return key, ctl

    for w in order:
        if w.is_screen:                              # 屏幕对象 = 页面根，不生成控件
            if w.bg is not None:
                page['backgroundColor'] = w.bg
            for n in w.notes:
                warnings.append('screen(%s): %s' % (w.var, n))
            rep_widgets.append({'var': w.var, 'lvType': w.lv, 'line': w.line,
                                'target': 'page-root', 'level': w.level,
                                'key': '(页面根)', 'caption': '',
                                'notes': w.notes or None})
            continue
        parent_w0 = widgets.get(w.parent or '')
        if (w.entry or {}).get('target') == 'textview' and parent_w0 is not None \
                and not parent_w0.is_screen \
                and (parent_w0.entry or {}).get('target') in ('button', 'button_pic') \
                and parent_w0.ctl is not None:
            # LVGL 按钮的 label 子控件 → FlyThings button.text 内联：schema 本就支持
            # （hw-relay ftu 真源：text 内联 + alignment 5），旧版 D-03「按钮不能装
            # 子控件」的独立 textview 变通废止。
            pctl = parent_w0.ctl
            if w.text is not None:
                pctl['text'] = w.text
            if w.fg is not None:
                pctl['colorTab']['color0'] = pctl['colorTab']['color1'] = w.fg
            if w.font is not None:
                pctl['fontSize'] = max(18, w.font)
            parent_w0.events.extend(w.events)
            w.events = []
            parent_w0.notes.append('按钮文本已内联（label %s → button.text）' % w.var)
            rep_widgets.append({'var': w.var, 'lvType': w.lv, 'line': w.line,
                                'target': 'button.text(inline)', 'level': w.level,
                                'key': parent_w0.key, 'caption': pctl.get('caption'),
                                'notes': ['label 子控件已内联进 %s.text' % parent_w0.key]})
            continue
        key, ctl = emit(w)
        w.key, w.caption, w.ctl = key, ctl.get('caption'), ctl
        rep_widgets.append({'var': w.var, 'lvType': w.lv, 'line': w.line,
                            'target': (w.entry or {}).get('target', key.split('__')[0]),
                            'level': w.level, 'key': key, 'caption': ctl.get('caption'),
                            'notes': w.notes or None})
        host = page
        parent_w = widgets.get(w.parent or '')
        if parent_w is not None and not parent_w.is_screen:
            pkey = parent_w.key or ''
            if pkey.startswith(('window__', 'scrollwindow__')):
                host = parent_w.ctl               # 挂进容器（坐标相对父级，与 LVGL 同口径）
            else:
                d_add(w, 'L4', 'LVGL 允许任意控件当父容器；FlyThings 只有 window 系可装子控件',
                      '已挂到页面根（坐标仍是相对父级的，请手工换算成页面坐标或包一层 window）')
        host[key] = ctl

    # ---- 事件回调汇总（不丢：FlyThings 回调名按 caption 生成）----
    events = []
    for w in order:
        for ev in w.events:
            cb = re.sub(r'[^0-9A-Za-z_]', '', ev['callback']) or ev['callback']
            events.append({'widget': w.var, 'caption': getattr(w, 'caption', ''),
                           'callback': cb, 'event': ev['event'], 'line': ev['line'],
                           'flythings': ('点击类回调按 caption 生成，如 onButtonClick_%s(ZKButton*)'
                                         % getattr(w, 'caption', ''))})
    if events:
        warnings.append('%d 个事件回调仅登记名字（见 events[]），需在 src/logic/*.cc 手工接线'
                        % len(events))
    n_strip = sum(1 for a in image_actions if a['action'] == 'stripped')
    n_gen = sum(1 for a in image_actions if a['action'] == 'generated')
    if n_strip:
        warnings.append('%d 处图片引用已剥除（%s）；正式图走 flythings_generate_ui_assets 出图后写回，'
                        '明细见 imageActions[]' % (n_strip, IMG_HANG_RULE))
    if n_gen:
        warnings.append('%d 张纯色占位图已生成到 <项目>/ui/images/（仅离线确认稿用，'
                        '正式图走 flythings_generate_ui_assets），明细见 imageActions[]' % n_gen)
    if any(w.lv in ('lv_label',) and w.text for w in order):
        warnings.append('LVGL label 默认自动折行；FlyThings textview 不自动折行，'
                        '超宽文本请手工插 \\n（见 lv_label 映射 notes）')

    ui_json = json.dumps(page, ensure_ascii=False, indent=2)
    result = {'ok': True, 'op': OP, 'source': src_name, 'res': '%dx%d' % (W, H),
              'dryRun': bool(dry_run),
              'summary': {'widgets': len([w for w in order if not w.is_screen]),
                          'screens': screens,
                          'byLevel': {lv: sum(1 for w in order if w.level == lv)
                                      for lv in ('L1', 'L2', 'L3', 'L4', 'L5', 'L?')
                                      if any(w.level == lv for w in order)},
                          'downgrades': len(downgrades),
                          'unrecognized': len(unrecognized),
                          'events': len(events),
                          'imageStripped': n_strip,
                          'imageGenerated': n_gen},
              'widgets': rep_widgets,
              'downgrades': downgrades,
              'unrecognized': unrecognized,
              'events': events,
              'imageActions': image_actions,
              'imageRule': IMG_HANG_RULE,
              'warnings': warnings,
              'doctrine': DOCTRINE_DOC, 'docs': KNOWLEDGE_DOC}
    if dry_run:
        result['uiJson'] = ui_json
        result['hint'] = 'dry_run=True 未写盘；确认无误后 dry_run=False + out=<项目>/ui/main.json 落盘'
        return result
    if not out:
        return _err('BAD_PARAMS', 'dry_run=False 时必须提供 out（输出 json 路径）',
                    '如 out=<项目>/ui/main.json', True)
    ap = os.path.abspath(out)
    try:
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        io.open(ap, 'w', encoding='utf-8', newline='\n').write(ui_json + '\n')
    except OSError as e:
        return _err('WRITE_FAILED', '%s' % e, '检查输出目录权限', True)
    result['jsonPath'] = ap
    gen_files = [a['path'] for a in image_actions if a['action'] == 'generated' and a['path']]
    result['affectedFiles'] = [ap] + sorted(set(gen_files))
    result['hint'] = ('json 已落盘；下一步：补 D-xx 降级项（圆角出图/回调接线）→ '
                      'flythings_generate_ui_assets 出正式图并写回被剥除的引用'
                      '（见 imageActions[]）→ flythings_ui_preview 出确认稿 → fui pack')
    return result
