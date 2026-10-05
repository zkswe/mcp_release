#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 规格指针（DESIGN_SPEC 第 1.1 条）：本文件是 `ui_schema.json` 的**消费方**，不新增规范。
# 它实现/引用的注册表条目（改判据 = 改规格，先改 ui_schema.json 再改这里）：
#   · page.rootFields            → 根页必填（SCH002）与 ROOT001（backgroundColor 必写）
#   · page.controlKeyPattern     → PAGE001（控件键形如 <type>__<n>）
#   · controls[].children         → TREE001/TREE002/TREE003（叶子不许装子控件；结构容器子内容只许走
#     结构键；容器 only 限定子控件类型）—— 与 check_all #2 **同一真源**。2026-10-05 实测教训：此前本文件
#     按 controls[].container 放行，同一份「slidewindow 平铺子按钮」的 json check_all 判 FAIL、本文件判
#     「通过」（假绿）；`container: true` 只说「装子内容」，没说子内容**走哪条路**，那半句现在由
#     `children` 声明。
#   · controls / subStructures   → PAGE001 的类型注册表、SCH002 的 required_fields
#   · controls[].fields[].type / sharedTypes → SCH003/SCH004（类型唯一实现 = ui_schema_loader.type_check）
#   · sharedTypes + valueRules.subboxType    → SCH001（子盒写成标量 = 真机 ftu 加载无声挂死）
#   · sharedTypes.position       → GEOM001（left/top/width/height 四整数）
#   · valueRules.missingImage    → ASSET001 / ASSET002（引用相对 resources；"" = 不设该图）
#   · renderContract `no-root-bg` → ROOT001（引擎靠根底色擦屏）
#   · renderContract `pic-scale` / `progress-clip` / `thumb-size` / `alpha-compose` /
#     `edge-aa` / `stroke-aa` / `nine-patch` / `rounding` / `family-consistency`
#     → **本文件不实现**（v1 不重复造第二份实现），在报告 `delegated` 里点名由
#     `ui_tools/check_all.py`（委派 `tools/qa/*`）负责 —— 也就是 T1.4 的接口点。
"""编译器式 json 合理性验收（通用工具 v1，不随项目复制）。

用途（需求方原话）：「用一个工具类似 C 程序编译一样验收 json 合理性，减少上机调试来回掰扯问题。」
→ 像编译器一样**一次跑完、给诊断（规则号 + 路径 + 原因 + 修法）、用退出码表达成败**：
把「这个 json 能不能被设备正常加载 / 字段对不对」在**离线**判完（落盘前 / 上机前）。

用法：
    python ui_tools/ui_compile.py <json|工程根|目录> [--res WxH] [--strict]
                                  [--rule R1,R2] [--json <报告落盘路径>] [--max-diag N] [--quiet]

退出码：0 = 无 fatal/error（`--strict` 下还要求无 warn）；1 = 有 fatal/error（`--strict` 下有 warn）；
        2 = 用法错 / 内部异常（目标不存在、`--res` 形态错、`--rule` 名字错、注册表读不到…）。

输入形态（自动判别）：
    ① 单个 `.json` 页面文件；
    ② 一个工程根（自动扫 `<root>/ui/*.json`，另下探一层 `ui/<分辨率>/*.json`，与 check_all 同口径）；
    ③ 一个目录（扫该目录 `*.json`，不下探）。
`project_root` 未显式给时按「json 是否位于 `<root>/ui/` 且 `<root>` 有 resources/ 或 Manifest.xml」**探测**；
探测不到 → ASSET001 不执行，并把这件事写进报告 `delegated`（不静默）。

规则集 v1（诊断里恒带规则号；级别由本表钉死）：

    | 规则号   | 判据                                                     | 级别  |
    |----------|----------------------------------------------------------|-------|
    | PARSE001 | JSON 语法错 / UTF-8 BOM / 非 UTF-8 编码                   | error |
    | PARSE002 | 根不是对象                                                | error |
    | PAGE001  | 控件 key 不符合 page.controlKeyPattern，或 <type> 未注册   | error |
    | SCH001   | 子盒对象字段写成标量（thumb/position/colorTab/picTab…）    | fatal |
    | SCH002   | 缺必填键（required_fields(type)；`id` 归 ID001，不重复报） | error |
    | SCH003   | 字段类型不符（ui_schema_loader.type_check 的 error）       | error |
    | SCH004   | 注册表外未知键（type_check 的 warn）                       | warn  |
    | NAME001  | caption 不是合法 C 标识符                                 | error |
    | NAME002  | caption 同页重复                                          | error |
    | ID001    | id 同页重复；或注册表 required 的 id 缺失                  | error |
    | ID002    | id 不在建议分区段（html2json.ID_BASE；仅提示）             | warn  |
    | TREE001  | 叶子控件装了子控件（controls[].children 未声明 = 叶子）    | error |
    | TREE002  | 结构容器的子内容平铺成子控件键（只许走结构键 item/items/…）| error |
    | TREE003  | 容器只装某类子控件却装了别的（pagewindow/scrollwindow）    | error |
    | TREE004  | 数组子结构键出现在错的容器里（items/infos/radiobuttons/subItem）| error |
    | ROOT001  | 根页缺 backgroundColor（renderContract no-root-bg）        | error |
    | CHAR001  | 文本字段含黑名单字符（字符集与 check_all.BLACKLIST 同源）  | error |
    | ASSET001 | 图片引用指向的文件不存在（仅当给了 project_root）          | error |
    | ASSET002 | 图片路径是绝对路径 / 带 resources/ 前缀 / 含反斜杠         | error |
    | GEOM001  | position 缺 left/top/width/height 或非整数                | error |
    | RES001   | 页面 resolution 与 `--res WxH` 声明不符（v1 附加规则）      | error |
    | SCAN001  | 目标下没有可编译的页面 json（v1 附加规则，防假阴性）       | error |

    说明：RES001 / SCAN001 不在整改方案 §WS-1 的规则表里，是**附加**规则 —— RES001 服务于 CLI 的
    `--res`（防「给错屏的页」上机）；SCAN001 防「0 页却报 ok」的静默假阴性（判 **error** 而不是 warn：
    「什么都没校验」不能算通过，check_all 的 `_ui_pages` 注释里有同类实测教训）。两条都在报告
    `rules` 里登记。

去重口径（同一条问题只报一次，规则归属唯一）：
    · `id` 缺键 → ID001（不再报 SCH002）；位置缺键 → GEOM001（不再报 SCH003）；
    · 子盒写成标量 → SCH001（不再报 GEOM001/ASSET*）；
    · 控件内「疑似控件键」写错 → PAGE001（不再报 SCH004）；
    · 根页位置的**子键**类型（left/top/…）归 GEOM001；
    · 子结构条目（item/subItem/items/radiobuttons/infos 的元素）的**类型**只报一次（由逐条校验负责，
      父控件那次 type_check 的递归结果被过滤掉）。

范围（诚实声明，别当它查过）：
    · 叶子级检查（ASSET001/002 图片、CHAR001 文本、GEOM001 位置）**只走注册表声明过的字段** ——
      未声明键由 SCH004 提示「先登记进 ui_schema.json」；登记前它们的图片路径不会被核存在性
      （`check_all` 的 #11/#4 用的是硬编码字段表，两边口径本就不完全重合，T1.4 去重时要对齐）。
    · 图片尺寸 == 控件盒 / AA / 倒角 / 透明底**不在本工具**（见报告 `delegated`）。

唯一真源：控件字段/类型/必填/默认/子盒结构一律来自 `ui_tools/ui_schema_loader.py`（读
`ui_tools/ui_schema.json`）；本文件**不抄第二份字段表**。字符黑名单取 `ui_tools/check_all.py:BLACKLIST`
（延迟 import，同源）；ID 分区段取 `ui_tools/html2json.py:ID_BASE`（延迟 import，同源）。
两处取不到 → 该条规则跳过并在报告 `delegated` 记账（绝不静默，也绝不内嵌副本）。

只读：本工具不写盘、不改用户的 json、不联网；唯一的写盘是**用户显式**用 `--json <路径>` 要求落报告
（且拒绝把报告写到某个输入 json 上，防覆盖）。

确定性：同一输入永远同一报告（诊断排序 = 先 file、再 path、再 rule、再 msg）。

库 API（生成器出口可直接调，T1.3 的接口）：
    compile_json(target, res=None, project_root=None, strict=False, rules=None, max_diag=None) -> dict
    compile_project(project_root, res=None, strict=False, rules=None, max_diag=None) -> dict
报告结构（稳定、可机读）：
    {"ok": true, "tool": "ui_compile", "version": "...", "schemaVersion": "...", "target": "...",
     "counts": {"pages": 1, "controls": 12, "items": 0, "byType": {"textview": 5}},
     "summary": {"fatal": 0, "error": 0, "warn": 2},
     "diagnostics": [{"severity": "error", "rule": "SCH002", "path": "/textview__1/fontSize",
                      "msg": "...", "hint": "...", "file": "ui/main.json"}],
     "delegated": ["图片尺寸 vs 控件盒 / AA / 倒角 / 透明底 → 由 ui_tools/check_all.py（委派 tools/qa/*）负责"]}
    `ok` = 无 fatal/error（strict 时也要求 warn=0）。多页目标时每条诊断带 `file`（相对标签），
    `path` 是**页内** JSON Pointer 风格路径；`summary` 统计的是**过滤后**的全部诊断，
    `diagnostics` 可能被 `--max-diag` 截断（截断条数记在 `truncated`，且写进 `delegated`）。

T1.4（去重）接口点 —— **未完成，如实登记**：`check_all.py` 的 json 侧检查项**尚未**改为调用
`compile_json`。现状 = 两份实现（本文件 TREE001-003、check_all #2）各自从**同一份注册表**
（`ui_schema.json#controls[].children`）派生层级判据 —— 判据的**数据**只有一个来源（2026-10-05 起），
但仍是两份代码。本文件只负责「静态可判」的部分，几何+资产（图 == 盒 / AA / 倒角 / 透明底）
仍归 check_all（委派 `tools/qa/*`），见报告 `delegated`。
"""
import argparse
import glob
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import ui_schema_loader as _us          # noqa: E402  字段/类型/必填/默认/子盒的唯一真源

TOOL = 'ui_compile'
VERSION = '0.1.0'
__version__ = VERSION

# ---------------- 委派声明（不实现的东西必须点名，不许静默） ----------------
DELEGATED_GEOM_ASSET = ('图片尺寸 vs 控件盒 / AA / 倒角 / 透明底 → 由 ui_tools/check_all.py'
                        '（委派 tools/qa/*）负责')
DELEGATED = (
    DELEGATED_GEOM_ASSET,
    'T1.4 接口点（未完成，如实登记）：check_all.py 的 json 侧检查项尚未改为调用'
    'ui_compile.compile_json —— 现状是两份实现从同一份注册表（ui_schema.json#controls[].children）'
    '派生层级判据（数据单一来源、代码尚未合并）；renderContract 的 pic-scale / progress-clip / '
    'thumb-size / alpha-compose / edge-aa / stroke-aa / nine-patch / rounding / family-consistency '
    '归 check_all（几何+资产）',
)

# 规则表（级别在这里钉死；诊断只带规则号，级别由本表派生，避免两处写级别）
RULES = {
    'PARSE001': ('error', 'JSON 语法错 / UTF-8 BOM / 非 UTF-8 编码',
                 '用「UTF-8 无 BOM」保存；先把 json 语法修到能解析（fui/easyui 都按严格 json 解析）'),
    'PARSE002': ('error', '页面根不是对象',
                 '根必须是对象（{...}），至少含 id / resolution / position / backgroundColor'),
    'PAGE001': ('error', '控件 key 非法或 <type> 未注册',
                '键名写成 <type>__<n>（type 取注册表 controls/subStructures 里的名字），如 textview__1'),
    'SCH001': ('fatal', '子盒对象字段写成了标量',
               '按 sharedTypes 把它写成对象（缺键用 ui_schema_loader.defaults(type) 补）——'
               '写成字符串/数字 = 真机 ftu 加载无声挂死'),
    'SCH002': ('error', '缺必填键',
               '用 ui_schema_loader.defaults(type) 补齐必填键全集（值等于默认值也要显式写，防版本漂移）'),
    'SCH003': ('error', '字段类型不符',
               '按注册表 controls[].fields[].type 改类型（bool 与 int 不通用；-1/0 也要按整数写）'),
    'SCH004': ('warn', '注册表外未知键',
               '先确认拼写；确实是字段就先登记进 ui_tools/ui_schema.json（注册表是唯一真源），再写进 json'),
    'NAME001': ('error', 'caption 不是合法 C 标识符',
                'caption 只能 [A-Za-z_][A-Za-z0-9_]*（要生成 m<caption>Ptr / ID_MAIN_<caption>）；'
                '显示文字写 text，不写 caption'),
    'NAME002': ('error', 'caption 同页重复',
                '同一页 caption 必须唯一（否则指针宏/ID 撞名）；改其中一个的名字'),
    'ID001': ('error', 'id 同页重复或缺失',
              '同页 id 唯一（按类型分区取号，见 ID002）；注册表 required 的 id 必写'),
    'ID002': ('warn', 'id 不在建议分区段',
              '按 html2json.ID_BASE 给该类型的分区段取号（仅提示，不影响加载；段宽 = 段基准的最小间隔）'),
    'TREE001': ('error', '叶子控件装了子控件',
                '叶子（controls[].children 未声明）不许有子控件键；子控件只能挂容器 —— '
                'window 万能容器，pagewindow/scrollwindow 只装 window，listview/slidewindow/'
                'radiogroup/diagram 的内容走结构键'),
    'TREE002': ('error', '结构容器的子内容平铺成子控件键',
                '结构容器（listview→item / slidewindow→items / radiogroup→radiobuttons / '
                'diagram→infos）子内容只能放结构键内，不能平铺 <type>__<n> 控件键'
                '（json-layer-rules 第 3 条：结构容器不平铺）'),
    'TREE003': ('error', '容器只装某类子控件，却装了别的',
                'pagewindow/scrollwindow 只装 window（内容必须进内层 window）；装别的控件 = '
                '那部分不显示（json-layer-rules 第 4 条）'),
    'TREE004': ('error', '数组子结构键出现在错的容器里',
                '数组子结构归属固定：items→slidewindow / infos→diagram / radiobuttons→radiogroup / '
                'subItem→listview（json-layer-rules 第 2 条）；放错容器 = 不生效'),
    'ROOT001': ('error', '根页缺 backgroundColor',
                '根必须写 backgroundColor（renderContract no-root-bg：引擎靠它擦屏，缺了真机残留上一帧/屏保）'),
    'CHAR001': ('error', '文本含裁剪字库外的字符',
                '换 ASCII 或字库内字符（字符集与 check_all.BLACKLIST 同源；emoji/特殊符号真机不显示）'),
    'ASSET001': ('error', '图片引用指向的文件不存在',
                 '把图放到 <工程根>/resources/<引用路径>，引用写相对 resources 的路径（如 images/x.png）；'
                 '缺图 = 控件不可见'),
    'ASSET002': ('error', '图片路径形态非法',
                 '去掉绝对路径 / resources/ 前缀 / 反斜杠，写成相对 resources 的 images/x.png'),
    'GEOM001': ('error', 'position 缺键或非整数',
                'position 必须 {left,top,width,height} 四个整数（相对父容器；负值合法）'),
    'RES001': ('error', '页面 resolution 与 --res 声明不符',
               '确认这页是不是给这块屏的：改 resolution 或换 --res（给错屏的页上机必返工）'),
    'SCAN001': ('error', '目标下没有可编译的页面 json',
                '确认路径：工程根要含 ui/*.json（或 ui/<分辨率>/*.json）；也可以直接指向具体 json'
                '（0 页 = 什么都没校验，不是通过）'),
}
_V1_RULES = ('PARSE001', 'PARSE002', 'PAGE001', 'SCH001', 'SCH002', 'SCH003', 'SCH004',
             'NAME001', 'NAME002', 'ID001', 'ID002', 'TREE001', 'TREE002', 'TREE003',
             'TREE004', 'ROOT001', 'CHAR001', 'ASSET001', 'ASSET002', 'GEOM001')
_EXTRA_RULES = ('RES001', 'SCAN001')
ALL_RULES = tuple(sorted(RULES))
_RULE_BY_LEVEL = {'fatal': 'SCH001', 'error': 'SCH003', 'warn': 'SCH004'}

_C_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_POS_KEYS = ('left', 'top', 'width', 'height')       # sharedTypes.position 的键（注册表同序）
_ABS_WIN_RE = re.compile(r'^[A-Za-z]:[\\/]')


def _is_int(v):
    """整数判据：bool 是 int 子类，必须显式排除（与 ui_schema_loader._check_scalar 同口径）。"""
    return isinstance(v, int) and not isinstance(v, bool)


# ---------------- 同源依赖（延迟 import；取不到 → 报告记账，绝不内嵌副本） ----------------
_CK = {'tried': False, 'mod': None, 'err': ''}


def _check_all():
    """ui_tools/check_all.py（同目录兄弟模块）：BLACKLIST / _is_bad_char / _pic_path / _ui_pages。"""
    if not _CK['tried']:
        _CK['tried'] = True
        try:
            import check_all as _ca
            _CK['mod'] = _ca
        except Exception as e:                     # noqa: BLE001 —— 不静默：错误进报告
            _CK['err'] = '%s: %s' % (type(e).__name__, e)
    return _CK['mod']


_H2J = {'tried': False, 'base': None, 'span': None, 'err': ''}


def _id_base():
    """ui_tools/html2json.py:ID_BASE（ID 分区段的唯一真源）+ 段宽（= 相邻段基准的最小间隔）。"""
    if not _H2J['tried']:
        _H2J['tried'] = True
        try:
            import html2json as _h
            base = dict(getattr(_h, 'ID_BASE', None) or {})
            if base:
                vals = sorted(set(v for v in base.values() if _is_int(v)))
                gaps = [b - a for a, b in zip(vals, vals[1:]) if b > a]
                _H2J['base'] = base
                _H2J['span'] = min(gaps) if gaps else 1000
            else:
                _H2J['err'] = 'html2json.ID_BASE 为空'
        except Exception as e:                     # noqa: BLE001 —— 不静默
            _H2J['err'] = '%s: %s' % (type(e).__name__, e)
    return _H2J['base'], _H2J['span']


def _resolve_charset():
    """字符黑名单判据（唯一来源 = check_all.BLACKLIST / _is_bad_char）。

    返回 (fn, note)：fn(c)->bool；note 非空 = 降级说明（写进报告 delegated）。
    fn is None = 本轮不执行 CHAR001（同样写 note，绝不静默返回成功）。
    """
    ca = _check_all()
    if ca is None:
        return None, ('CHAR001 未执行：取不到 ui_tools/check_all.py（%s）——'
                      '本工具不内嵌字符黑名单副本，请修好 import 后重跑' % (_CK['err'] or '原因未知'))
    fn = getattr(ca, '_is_bad_char', None)
    if fn is not None:
        return fn, ''
    black = getattr(ca, 'BLACKLIST', None)
    if black is not None:
        return (lambda c: c in black), ('CHAR001 降级：check_all._is_bad_char 取不到，'
                                        '只用同源的 BLACKLIST 单字集（emoji 区间未查）')
    return None, 'CHAR001 未执行：check_all 里既无 _is_bad_char 也无 BLACKLIST（判据缺失，不猜）'


def _scalar_ok(ftype, value):
    """标量类型判据 = ui_schema_loader._check_scalar（唯一实现，本文件不抄一份类型表）。

    返回 True/False；None = 判不了（非标量类型，或 loader 里取不到该判据 → 跳过并记账）。
    """
    fn = getattr(_us, '_check_scalar', None)
    if fn is None:
        return None
    return fn(ftype, value)


# ---------------- 路径工具 ----------------
def _slash(p):
    return str(p).replace('\\', '/')


def _looks_like_control_body(v):
    """疑似「控件对象」：含子控件键，或含 caption/position（写错的控件键要报 PAGE001 而不是未知键）。"""
    if not isinstance(v, dict) or not v:
        return False
    if 'caption' in v or 'position' in v:
        return True
    return False


def _guess_project_root(path):
    """从 json 路径（或目录）向上探测工程根：`<root>/ui[/<分辨率>]/x.json` 且 <root> 有 resources/ 或 Manifest.xml。"""
    d = os.path.abspath(path)
    if os.path.isfile(d):
        d = os.path.dirname(d)
    for _ in range(3):
        if os.path.basename(d).lower() == 'ui':
            root = os.path.dirname(d)
            if os.path.isdir(os.path.join(root, 'resources')) or \
                    os.path.isfile(os.path.join(root, 'Manifest.xml')):
                return root
            return None
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return None


def _ui_pages(root):
    """`<root>/ui/*.json` + 一层 `ui/<分辨率>/*.json`（口径与 check_all._ui_pages 一致，优先直接用它）。"""
    ca = _check_all()
    if ca is not None and hasattr(ca, '_ui_pages'):
        return [_slash(p) for p in ca._ui_pages(root)]
    ui = os.path.join(root, 'ui')
    found = set(glob.glob(os.path.join(ui, '*.json')))
    for sub in sorted(glob.glob(os.path.join(ui, '*'))):
        if os.path.isdir(sub):
            found.update(glob.glob(os.path.join(sub, '*.json')))
    return sorted(_slash(p) for p in found)


def _pic_exists(root, ref):
    """图片引用是否存在（口径与 check_all 同源：优先 check_all._pic_path，再退 resources/ + ui/）。"""
    ca = _check_all()
    if ca is not None and hasattr(ca, '_pic_path'):
        return bool(ca._pic_path(root, ref))
    rel = _slash(ref).replace('/', os.sep)
    return any(os.path.isfile(os.path.join(root, base, rel)) for base in ('resources', 'ui'))


# ---------------- 报告器 ----------------
class _Ctx(object):
    """一次编译的上下文：诊断、计数、委派、选项。"""

    def __init__(self, target, res=None, strict=False, rules=None, project_root=None,
                 label_base=None):
        reg = _us.load()
        pat = (reg.get('page') or {}).get('controlKeyPattern')
        if not pat:
            raise _us.SchemaRegistryError(
                'ui_schema.json 缺 page.controlKeyPattern: %s' % _us.SCHEMA_PATH)
        self.reg = reg
        self.ck_re = re.compile(pat)
        self.ck_pattern = pat
        # 2026-10-05 检讨修：原来是 `... .get('rootFields') or {}` —— 注册表一旦缺这一段，
        # `rootFields` 静默变空 → **ROOT001 永不触发、delegated 里也不记**，编译式验收假装通过
        # （实测：删掉 page.rootFields 后仍回 ok=True / fatal=0 / error=0）。与上面
        # `controlKeyPattern` 同口径：**注册表缺段 = 停手报错**，不静默降级。
        self.root_fields = (reg.get('page') or {}).get('rootFields') or {}
        if not self.root_fields:
            raise _us.SchemaRegistryError(
                'ui_schema.json 缺 page.rootFields: %s（根页必填判据 SCH002/ROOT001 无从执行）'
                % _us.SCHEMA_PATH)
        self.shared = set(reg.get('sharedTypes') or {})
        self.subs = set(reg.get('subStructures') or {})
        self.controls = set(reg.get('controls') or {})
        self.known = self.controls | self.subs
        self.arr_owners = _us.structural_array_keys()   # {数组子结构键: 归属控件}（children 段派生）
        self.target = target
        self.res = res
        self.strict = bool(strict)
        self.rule_filter = _norm_rules(rules) if rules else None
        self.project_root = project_root
        self.label_base = label_base or (os.path.dirname(target) if os.path.isfile(target) else target)
        self.file = ''
        self.diags = []
        self.delegated = list(DELEGATED)
        self.counts = {'pages': 0, 'controls': 0, 'items': 0, 'byType': {}}
        self.pages = []
        self.files = []
        # 字符黑名单判据（同源；降级/取不到 → 记账）
        self.bad_char, note = _resolve_charset()
        if note:
            self.delegate(note)
        if getattr(_us, '_check_scalar', None) is None:
            self.delegate('SCH003（根字段/子盒子键的标量类型）未执行：ui_schema_loader._check_scalar '
                          '取不到 —— 本工具不内嵌第二份标量类型表（控件内字段仍由 type_check 校验）')
        if self.project_root is None:
            self.delegate('ASSET001 未执行：未给 / 探测不到 project_root —— 图片存在性没核'
                          '（引用口径是相对 <工程根>/resources/）；传 project_root 或把 json 放进 '
                          '<root>/ui/ 再跑')

    # ---- 记账 ----
    def delegate(self, msg):
        if msg not in self.delegated:
            self.delegated.append(msg)

    def add(self, rule, path, msg, hint=None):
        sev, _title, rule_hint = RULES[rule]
        self.diags.append({'severity': sev, 'rule': rule,
                           'path': path if path.startswith('/') else '/' + path,
                           'msg': msg, 'hint': hint or rule_hint, 'file': self.file})

    # ---- 注册表查询（唯一真源 ui_schema.json） ----
    def fields_of(self, tname):
        """{字段: 类型名}：controls/subStructures 的 fields 是 spec dict；sharedTypes 的 fields 直接是类型名。"""
        e = self.reg['controls'].get(tname) or self.reg['subStructures'].get(tname)
        if e is not None:
            return dict((k, (v or {}).get('type')) for k, v in (e.get('fields') or {}).items())
        st = self.reg['sharedTypes'].get(tname)
        if st is not None:
            return dict(st.get('fields') or {})
        return {}

    def spec_of(self, tname, field):
        e = self.reg['controls'].get(tname) or self.reg['subStructures'].get(tname)
        if e is None:
            return None
        return (e.get('fields') or {}).get(field)

    def children_spec(self, tname):
        """子内容声明（注册表 controls[].children / ui_schema_loader.children_spec）；叶子 → None。

        ⚠️ 不要用 `controls[].container` 判「子控件键合不合法」——那半个真源正是 2026-10-05
        假绿的根因（container=true 的 slidewindow 子控件键其实非法）。唯一判据 = 本方法。
        """
        return _us.children_spec(tname)

    # ---- 页级状态 ----
    def start_page(self, label):
        self.file = label
        self.files.append(label)
        self.counts['pages'] += 1
        self._caps = {}
        self._ids = {}

    def end_page(self):
        for cap in sorted(self._caps):
            paths = sorted(set(self._caps[cap]))
            if len(paths) < 2:
                continue
            for p in paths:
                others = [q for q in paths if q != p]
                self.add('NAME002', p + '/caption',
                         'caption %r 同页重复 %d 次（另有 %s）'
                         % (cap, len(paths), '、'.join(others[:3])))
        for cid in sorted(self._ids):
            paths = sorted(set(self._ids[cid]))
            if len(paths) < 2:
                continue
            for p in paths:
                others = [q for q in paths if q != p]
                self.add('ID001', p + '/id',
                         'id %s 同页重复 %d 次（另有 %s）'
                         % (cid, len(paths), '、'.join(others[:3])))

    # ---- 页面级检查 ----
    def compile_raw(self, label, data, errs):
        """一页的完整编译（start_page/end_page 收口：页级重复键检查一定会跑）。"""
        self.start_page(label)
        if data is None:                                # PARSE001（读不到/编码/BOM/语法）
            for rule, path, msg in errs:
                self.add(rule, path, msg)
        elif not isinstance(data, dict):                # PARSE002
            self.add('PARSE002', '/', '页面根是 %s，不是对象' % type(data).__name__)
        else:
            self.compile_page(data)
        self.end_page()

    def compile_page(self, data):
        """校验一页（data 已解析成对象）。"""
        for k in self.root_fields:                      # 注册表声明顺序
            spec = self.root_fields[k]
            if k not in data:
                if not spec.get('required'):
                    continue
                if k == 'backgroundColor':
                    self.add('ROOT001', '/backgroundColor',
                             '根页缺 backgroundColor（renderContract no-root-bg：引擎靠它擦屏，'
                             '缺了真机残留上一帧/屏保）')
                else:
                    self.add('SCH002', '/' + k,
                             '根页缺必填键 %s（page.rootFields.%s.required）' % (k, k))
                continue
            self.check_root_field(k, spec, data[k], '/' + k)
        if self.res:
            got = data.get('resolution')
            if isinstance(got, dict) and _is_int(got.get('width')) and _is_int(got.get('height')):
                if (got['width'], got['height']) != tuple(self.res):
                    self.add('RES001', '/resolution',
                             '页面 resolution %dx%d 与 --res 声明的 %dx%d 不符'
                             % (got['width'], got['height'], self.res[0], self.res[1]))
        self.walk_children(None, data, '')

    def check_root_field(self, key, spec, value, path):
        """根字段：position → GEOM001；sharedTypes 对象 → 对象校验；标量 → 类型校验。"""
        ftype = spec.get('type')
        if ftype == 'position':
            self.check_position(value, path, report_non_dict=True)
            return
        if ftype in self.shared:
            self.check_shared_object(ftype, value, path)
            return
        if _scalar_ok(ftype, value) is False:
            self.add('SCH003', path, '%s 类型应为 %s，实际是 %s(%r)'
                     % (key, ftype, type(value).__name__, value))

    def check_shared_object(self, tname, value, path):
        """sharedTypes 对象（根 resolution 等）：本体必是对象 + requiredKeys + 子键标量类型。"""
        if not isinstance(value, dict):
            self.add('SCH001', path, '%s 必须是对象（%s），实际是 %s —— 子盒写成标量 = 真机 ftu 加载无声挂死'
                     % (path.rsplit('/', 1)[-1], tname, type(value).__name__))
            return
        st = self.reg['sharedTypes'].get(tname) or {}
        fmap = dict(st.get('fields') or {})
        for kk in (st.get('requiredKeys') or []):
            if kk not in value:
                self.add('SCH003', path + '/' + kk, '缺 %s（%s 子结构 requiredKeys）' % (kk, tname))
        for kk, vv in value.items():
            expect = fmap.get(kk)
            if expect is None:
                continue                                # 子盒内的额外键不管（与 type_check 同口径）
            if expect in self.shared:
                self.check_shared_object(expect, vv, path + '.' + kk)
            elif _scalar_ok(expect, vv) is False:
                self.add('SCH003', path + '.' + kk, '%s.%s 类型应为 %s，实际是 %s(%r)'
                         % (path.rsplit('/', 1)[-1], kk, expect, type(vv).__name__, vv))

    def check_position(self, value, path, report_non_dict=False):
        """GEOM001：position 必须是 {left,top,width,height} 四整数（负值合法）。

        子键路径用点号（`/textview__1/position.width`）—— 与 ui_schema_loader.type_check 对子盒
        字段的写法一致（`thumb.size.width`），免得同一层字段出现两种分隔符。
        """
        if not isinstance(value, dict):
            if report_non_dict:
                self.add('SCH001', path, 'position 必须是对象（position），实际是 %s ——'
                                         '子盒写成标量 = 真机 ftu 加载无声挂死' % type(value).__name__)
            return                                      # 控件内：type_check 已报 SCH001，不重复
        for k in _POS_KEYS:
            if k not in value:
                self.add('GEOM001', path + '.' + k, 'position 缺 %s' % k)
            elif not _is_int(value[k]):
                self.add('GEOM001', path + '.' + k, 'position.%s 必须是整数，实际是 %s(%r)'
                         % (k, type(value[k]).__name__, value[k]))

    def _is_nested_entry(self, spec):
        """该字段是不是「装注册表条目」的字段（子结构 / itemType 已注册的数组）。"""
        ftype = spec.get('type')
        if ftype in self.subs:
            return True
        if ftype == 'array' and spec.get('itemType') in self.known:
            return True
        return False

    # ---- 控件树 ----
    def _check_child_keys(self, key, t, kids, path):
        """子控件键合法性：唯一真源 = 注册表 `controls[].children`（与 check_all #2 同源）。

        TREE001 叶子（无 children 声明）装了子控件；
        TREE002 结构容器把子内容平铺成子控件键（只许走结构键）；
        TREE003 容器声明了 only：缺 only 子内容，或装了别的类型（pagewindow/scrollwindow 只装 window）。
        """
        spec = self.children_spec(t)
        joined = '、'.join(kids[:3])
        if spec is None:
            if not kids:
                return                              # 叶子且没子控件：合法
            self.add('TREE001', path,
                     '%s（%s）是叶子控件，却装了子控件 %s（注册表 controls[].children 未声明 = 叶子）'
                     % (key, t, joined))
            return
        if spec.get('mode') == 'substructure':
            if not kids:
                return                              # 结构容器的子内容走结构键（本项不管键内内容）
            self.add('TREE002', path,
                     '%s（%s）是结构容器：子内容只能放 %s（%s），平铺子控件键 %s 非法'
                     % (key, t, spec.get('key'), _us.field_type(t, spec.get('key')) or '子结构', joined))
            return
        only = spec.get('only')
        if not only:
            return                                  # 不限制（window 万能容器）
        nested = '、'.join(only)
        # 与 check_all #2 同口径同措辞：先判「一个 only 类型都没有」→ 缺；否则再判「混进了别的类型」。
        if not any(ck.split('__', 1)[0] in only for ck in kids):
            self.add('TREE003', path,
                     '%s（%s）缺 %s 子内容（%s 必须嵌套 %s）' % (key, t, nested, t, nested))
            return
        bad = [ck for ck in kids if ck.split('__', 1)[0] not in only]
        if bad:
            self.add('TREE003', path,
                     '%s（%s）含非 %s 子键（%s 只装 %s）'
                     % (key, t, nested, t, nested))

    def _check_array_owner(self, key, t, ctrl, path):
        """数组子结构归属固定（唯一真源 = 注册表 children 段派生的 structural_array_keys()）。

        `items`→slidewindow / `infos`→diagram / `radiobuttons`→radiogroup / `subItem`→listview；
        出现在别的控件里 = 不生效（json-layer-rules 第 2 条）。与 check_all #2 同源同判。
        """
        if not isinstance(ctrl, dict):
            return
        for ak, owner in self.arr_owners.items():
            if ak in ctrl and t != owner:
                self.add('TREE004', path,
                         '%s（%s）里有数组 %s：只能出现在 %s 内'
                         '（json-layer-rules 第 2 条：数组子结构归属固定）' % (key, t, ak, owner))

    def walk_children(self, owner_type, node, path):
        """node 内可能装子控件；owner_type=None 表示页面根（根字段见 page.rootFields）。"""
        if not isinstance(node, dict):
            return
        fields = self.root_fields if owner_type is None else self.fields_of(owner_type)
        for k, v in node.items():
            if k in fields:
                continue                                # 声明字段，不是子控件
            cpath = '%s/%s' % (path, k)
            m = self.ck_re.match(k)
            if m:
                # <type> = key 里第一段（控制键形如 <type>__<n>；注册表的 pattern 没有捕获组，
                # 形状由 page.controlKeyPattern 判，类型名从键名切出来）
                t = k.split('__', 1)[0]
                if t not in self.known:
                    self.add('PAGE001', cpath,
                             '%s: <type> %r 不在注册表（controls/subStructures）—— 键名必须是 '
                             '<注册类型>__<n>' % (k, t))
                    continue
                kids = [ck for ck in v if self.ck_re.match(ck)] if isinstance(v, dict) else []
                self._check_child_keys(k, t, kids, cpath)
                self._check_array_owner(k, t, v, cpath)
                self.check_control(k, v, cpath, t)
                continue
            if '__' in k or _looks_like_control_body(v):
                self.add('PAGE001', cpath, '%s: key 不符合 page.controlKeyPattern %s'
                                           '（控件键形如 <type>__<n>，如 textview__1）'
                         % (k, self.ck_pattern))
                continue
            if owner_type is None:
                self.add('SCH004', cpath, '根页未知键（page.rootFields 未声明，不报错仅提示）')
            # 控件内的未知键交给 ui_schema_loader.type_check 的 warn（同一条 SCH004，不重复报）

    def check_control(self, key, ctrl, path, t):
        self.counts['controls'] += 1
        self.counts['byType'][t] = self.counts['byType'].get(t, 0) + 1
        if not isinstance(ctrl, dict):
            for vio in _us.type_check(t, ctrl):        # 本体不是对象 → 单条 SCH003（不逐字段刷屏）
                self.add(_RULE_BY_LEVEL[vio['level']], path, vio['msg'])
            return
        self.check_entry(t, ctrl, path)

    def check_entry(self, t, data, path):
        """控件 / 子结构条目（item/subItem/items/radiobuttons/infos 的元素）的通用校验。"""
        fields = self.fields_of(t)
        typed = {}
        nested = set()                                  # 子结构/数组字段：由 walk_nested_entries 逐条校验
        for k, v in data.items():
            if self.ck_re.match(k):
                continue                                # 子控件键：走 walk_children
            if k not in fields and ('__' in k or _looks_like_control_body(v)):
                continue                                # 疑似控件键 → PAGE001，不进类型检查
            spec = self.spec_of(t, k)
            if spec and self._is_nested_entry(spec):
                nested.add(k)
            typed[k] = v
        pos_fields = set(k for k in fields if fields.get(k) == 'position')
        for vio in _us.type_check(t, typed, '/'):
            head = str(vio['field']).lstrip('/').split('.')[0].split('[')[0]
            if head in nested:
                continue            # 递归条目：由本函数逐条校验（否则同一字段会出两份诊断）
            if head in pos_fields and '.' in str(vio['field']):
                continue            # position 子键（left/top/width/height）归 GEOM001，级别/归属唯一
            self.add(_RULE_BY_LEVEL[vio['level']],
                     path + '/' + str(vio['field']).lstrip('/'), vio['msg'])
        for f in _us.required_fields(t):
            if f in data:
                continue
            if f == 'id':
                self.add('ID001', path + '/id', '缺 id（%s 注册表声明 required）' % t)
            else:
                self.add('SCH002', path + '/' + f, '缺必填键 %s（%s.fields.%s.required）' % (f, t, f))
        cap = data.get('caption')
        if isinstance(cap, str):
            if _C_IDENT_RE.match(cap):
                self._caps.setdefault(cap, []).append(path)
            else:
                self.add('NAME001', path + '/caption',
                         'caption %r 不是合法 C 标识符（要 ^[A-Za-z_][A-Za-z0-9_]*$；'
                         '显示文字写 text）' % cap)
        cid = data.get('id')
        if _is_int(cid):
            self._ids.setdefault(cid, []).append(path)
            self.check_id_band(t, cid, path + '/id')
        for lp, ftype, val in self.iter_leaves(t, data, path, '/'):
            self.check_leaf(ftype, val, lp)
        self.walk_children(t, data, path)
        self.walk_nested_entries(t, data, path)

    def walk_nested_entries(self, t, data, path):
        """子结构条目（listview.item / item.subItem / slidewindow.items / radiogroup.radiobuttons /
        diagram.infos）也要按注册表校验：它们同样有必填键与 caption（生成 C++ 标识符）。"""
        for k, v in data.items():
            spec = self.spec_of(t, k)
            if not spec or not self._is_nested_entry(spec):
                continue
            if spec.get('type') == 'array':
                if not isinstance(v, list):
                    continue                            # 标量/对象交给 type_check 的 fatal
                it = spec.get('itemType')
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        self.counts['items'] += 1
                        self.check_entry(it, item, '%s/%s[%d]' % (path, k, i))
            else:
                if not isinstance(v, (dict, list)):
                    continue                            # 标量交给 type_check 的 fatal
                items = v if isinstance(v, list) else [v]
                for i, item in enumerate(items):
                    if isinstance(item, dict):
                        self.counts['items'] += 1
                        self.check_entry(spec.get('type'), item,
                                         '%s/%s' % (path, k) if isinstance(v, dict)
                                         else '%s/%s[%d]' % (path, k, i))

    def iter_leaves(self, owner_type, node, path, sep):
        """按注册表展开标量叶子（含 sharedTypes 子盒内的键）。

        只走**声明过的**字段：未声明键归 SCH004（type_check），子结构/数组归 walk_nested_entries，
        子盒写成标量归 SCH001（type_check）—— 各报一次，互不重复。
        """
        if not isinstance(node, dict):
            return
        fmap = self.fields_of(owner_type)
        for k, v in node.items():
            ft = fmap.get(k)
            if ft is None:
                continue
            p = path + sep + k
            if ft in self.shared:
                yield (p, ft, v)
                if isinstance(v, dict):
                    for x in self.iter_leaves(ft, v, p, '.'):
                        yield x
            elif ft in self.subs or ft == 'array':
                continue
            else:
                yield (p, ft, v)

    # ---- 叶子级检查 ----
    def check_leaf(self, ftype, val, path):
        name = path.rsplit('/', 1)[-1].rsplit('.', 1)[-1].split('[')[0]
        if ftype == 'string' and isinstance(val, str) and val:
            self.check_text(path, val)
        if (ftype == 'path' or name.endswith('Pic')) and isinstance(val, str) and val.strip():
            self.check_pic(path, val)
        if ftype == 'position':
            self.check_position(val, path)

    def check_text(self, path, txt):
        if self.bad_char is None:
            return
        bad = sorted(set(c for c in txt if self.bad_char(c)))
        if bad:
            self.add('CHAR001', path, '文本含字库外/黑名单字符 %s（共 %d 处）'
                     % (' '.join(repr(c) for c in bad[:6]), len(bad)))

    def check_pic(self, path, ref):
        norm = _slash(ref.strip())
        why = None
        if norm.startswith('/') or _ABS_WIN_RE.match(norm):
            why = '是绝对路径'
        elif '\\' in ref:
            why = '含反斜杠（设备端按 / 分隔）'
        elif norm.startswith('resources/') or norm.startswith('./resources/') \
                or '/resources/' in norm:
            why = '带了 resources/ 前缀（引用本身就是相对 resources 的）'
        if why:
            self.add('ASSET002', path, '图片引用 %r %s' % (ref, why))
            return
        if self.project_root is None:
            return
        if '%s' in norm:
            prefix = norm.split('%s')[0]
            if glob.glob(os.path.join(self.project_root, 'resources', prefix + '*')):
                return
            self.add('ASSET001', path, '图片引用 %r 是运行时格式化串，但 %s 前缀在 '
                     '<root>/resources/ 下没有任何匹配文件' % (ref, prefix))
            return
        if not _pic_exists(self.project_root, norm):
            self.add('ASSET001', path, '图片引用 %r 不存在（在 <工程根>/resources/ 与 <工程根>/ui/ 下都找不到）'
                     % ref)

    def check_id_band(self, t, cid, path):
        base, span = _id_base()
        if not base:
            self.delegate('ID002 未执行：取不到 ui_tools/html2json.py:ID_BASE（%s）——'
                          '本工具不内嵌 ID 分区表副本' % (_H2J['err'] or '原因未知'))
            return
        if t not in base or not span:
            return
        b = base[t]
        if not (b <= cid < b + span):
            self.add('ID002', path, 'id %d 不在 %s 的建议分区段 %d~%d（html2json.ID_BASE；仅提示）'
                     % (cid, t, b, b + span - 1))


def _norm_rules(rules):
    """规则过滤：None / 'SCH001,SCH002' / ['SCH001'] → 规则号列表（大写归一，校验合法性）。"""
    if rules is None:
        return None
    if isinstance(rules, str):
        items = [x.strip().upper() for x in rules.split(',')]
    else:
        items = [str(x).strip().upper() for x in rules]
    items = [x for x in items if x]
    bad = [x for x in items if x not in RULES]
    if bad:
        raise ValueError('未知规则号 %s；可用：%s' % ('、'.join(bad), '、'.join(ALL_RULES)))
    return sorted(set(items))


# ---------------- 编译入口 ----------------
def _read_page(path):
    """读 + 解析一页。返回 (data|None, [(rule, path, msg)])。"""
    try:
        with open(path, 'rb') as fh:
            raw = fh.read()
    except OSError as e:
        return None, [('PARSE001', '/', '文件读取失败：%s' % e)]
    if raw.startswith(b'\xef\xbb\xbf'):
        return None, [('PARSE001', '/', '文件带 UTF-8 BOM（严格 json 解析会失败；请存成「UTF-8 无 BOM」）')]
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as e:
        return None, [('PARSE001', '/', '不是 UTF-8 编码（%s）；老工程 GBK 文件请转存 UTF-8 无 BOM' % e)]
    try:
        return json.loads(text), []
    except ValueError as e:
        return None, [('PARSE001', '/', 'JSON 语法错：%s' % e)]


def _resolve_target(target, project_root):
    """目标 → (页面 json 绝对路径列表, project_root, 形态, 标签基准目录)。"""
    t = os.path.abspath(str(target))
    if os.path.isfile(t):
        proj = project_root or _guess_project_root(t)
        return [t], proj, 'file', (proj or os.path.dirname(t))
    if os.path.isdir(t):
        if os.path.isdir(os.path.join(t, 'ui')):
            proj = project_root or t
            return _ui_pages(t), proj, 'project', proj
        proj = project_root or _guess_project_root(t)
        pages = sorted(_slash(p) for p in glob.glob(os.path.join(t, '*.json')))
        return pages, proj, 'dir', (proj or t)
    raise ValueError('目标不存在：%s（要 <json 文件> / <工程根> / <目录>）' % target)


def _compile_files(ctx, pages, not_found_msg=None):
    """逐页编译（页级 counts/summary 逐页留痕，供报告 pages[] 用）。"""
    if not pages:
        ctx.add('SCAN001', '/', not_found_msg or
                '目标 %s 下没有扫到任何页面 json（0 页 = 什么都没校验，不是通过）' % ctx.target)
    for p in pages:
        label = _slash(os.path.relpath(p, ctx.label_base)) if ctx.label_base else os.path.basename(p)
        i0 = len(ctx.diags)
        c0 = dict(ctx.counts)
        data, errs = _read_page(p)
        ctx.compile_raw(label, data, errs)
        slice_ = ctx.diags[i0:]
        bad = any(d['severity'] in ('fatal', 'error') for d in slice_) or \
            (ctx.strict and any(d['severity'] == 'warn' for d in slice_))
        by_type = {}
        for k, v in ctx.counts['byType'].items():
            n = v - c0['byType'].get(k, 0)
            if n:
                by_type[k] = n
        ctx.pages.append({
            'file': label,
            'ok': not bad,
            'counts': {'controls': ctx.counts['controls'] - c0['controls'],
                       'items': ctx.counts['items'] - c0['items'],
                       'byType': dict(sorted(by_type.items()))},
            'summary': _page_slice_summary(slice_),
        })
    return ctx


def _page_slice_summary(diags):
    out = {'fatal': 0, 'error': 0, 'warn': 0}
    for d in diags:
        out[d['severity']] = out.get(d['severity'], 0) + 1
    return out


def _finish(ctx):
    diags = sorted(ctx.diags,
                   key=lambda d: (d.get('file') or '', d['path'], d['rule'], d['msg']))
    if ctx.rule_filter:
        diags = [d for d in diags if d['rule'] in ctx.rule_filter]
    summary = _page_slice_summary(diags)
    ok = (summary['fatal'] == 0 and summary['error'] == 0
          and (not ctx.strict or summary['warn'] == 0))
    return {
        'ok': ok,
        'tool': TOOL,
        'version': VERSION,
        'schemaVersion': ctx.reg.get('schemaVersion'),
        'target': ctx.target,
        'kind': ctx.kind,
        'projectRoot': ctx.project_root,
        'res': list(ctx.res) if ctx.res else None,
        'strict': ctx.strict,
        'rules': list(ALL_RULES),
        'ruleFilter': list(ctx.rule_filter) if ctx.rule_filter else None,
        'counts': {'pages': ctx.counts['pages'], 'controls': ctx.counts['controls'],
                   'items': ctx.counts['items'],
                   'byType': dict(sorted(ctx.counts['byType'].items()))},
        'summary': summary,
        'diagnostics': diags,
        'delegated': list(ctx.delegated),
        'files': sorted(set(ctx.files)),
        'pages': ctx.pages,
        'truncated': 0,
    }


def _apply_max_diag(report, max_diag):
    if max_diag is None or max_diag < 0 or len(report['diagnostics']) <= max_diag:
        return report
    dropped = len(report['diagnostics']) - max_diag
    report['diagnostics'] = report['diagnostics'][:max_diag]
    report['truncated'] = dropped
    report['delegated'].append(
        '诊断被 --max-diag=%d 截断：本报告只列前 %d 条，另有 %d 条未列出'
        '（summary 统计的是**全部**诊断，未截断）' % (max_diag, max_diag, dropped))
    return report


def compile_json(target, res=None, project_root=None, strict=False, rules=None, max_diag=None):
    """编译式验收一个目标（单个 json / 工程根 / 目录），返回报告 dict（结构见模块 docstring）。

    target        : str 路径（文件 / 目录 / 工程根）
    res           : (w, h) 元组或 'WxH' 字符串 —— 期望分辨率；不符报 RES001
    project_root  : 工程根（ASSET001 用它把引用解析成 <root>/resources/...；None 时自动探测）
    strict        : True 时 warn 也算失败（ok=False）
    rules         : 只报这些规则（列表或 'SCH001,SCH002'）；未知规则号抛 ValueError
    max_diag      : 报告 diagnostics 最多列多少条（summary 仍按全部统计；截断记账在 truncated）
    """
    res2 = _parse_res(res)
    pages, proj, kind, label_base = _resolve_target(target, project_root)
    ctx = _Ctx(os.path.abspath(str(target)), res=res2, strict=strict, rules=rules,
               project_root=proj, label_base=label_base)
    ctx.kind = kind
    if kind == 'project':
        hint = ('工程根 %s 下没扫到页面 json：要 <root>/ui/*.json 或 <root>/ui/<分辨率>/*.json'
                '（0 页 = 什么都没校验，不是通过）' % proj)
        _compile_files(ctx, pages, hint)
    elif kind == 'dir':
        _compile_files(ctx, pages, '目录 %s 下没有 *.json（本形态不下探子目录）' % ctx.target)
    else:
        _compile_files(ctx, pages)
    report = _finish(ctx)
    report['kind'] = kind
    return _apply_max_diag(report, max_diag)


def compile_project(project_root, res=None, strict=False, rules=None, max_diag=None):
    """编译式验收一个工程根（扫 <root>/ui/*.json + 一层 <root>/ui/<分辨率>/*.json）。"""
    proj = os.path.abspath(str(project_root))
    if not os.path.isdir(proj):
        raise ValueError('工程根不是目录：%s' % project_root)
    res2 = _parse_res(res)
    pages = _ui_pages(proj)
    ctx = _Ctx(proj, res=res2, strict=strict, rules=rules, project_root=proj, label_base=proj)
    ctx.kind = 'project'
    _compile_files(ctx, pages, '工程根 %s 下没扫到页面 json：要 <root>/ui/*.json 或 '
                               '<root>/ui/<分辨率>/*.json（0 页 = 什么都没校验，不是通过）' % proj)
    report = _finish(ctx)
    report['kind'] = 'project'
    return _apply_max_diag(report, max_diag)


def _parse_res(res):
    """'1024x600' / '1024X600' / (1024, 600) / [1024, 600] → (1024, 600)；None → None。"""
    if res is None or res == '':
        return None
    if isinstance(res, (tuple, list)):
        if len(res) != 2:
            raise ValueError('res 要 (宽, 高)，收到 %r' % (res,))
        w, h = res
    else:
        m = re.match(r'^(\d+)\s*[xX*×]\s*(\d+)$', str(res).strip())
        if not m:
            raise ValueError('res 形态要 WxH（如 1024x600），收到 %r' % (res,))
        w, h = m.group(1), m.group(2)
    try:
        w, h = int(w), int(h)
    except (TypeError, ValueError):
        raise ValueError('res 的宽/高必须是整数，收到 %r' % (res,))
    if w <= 0 or h <= 0:
        raise ValueError('res 的宽/高必须为正，收到 %r' % (res,))
    return (w, h)


# ---------------- CLI ----------------
def _format_diag(d, show_file):
    loc = ('%s%s' % (d['file'] + ': ' if show_file else '', d['path']))
    return '%s: %s [%s] %s → %s' % (loc, d['severity'], d['rule'], d['msg'], d['hint'])


def _print_report(report, out=None):
    """人类可读输出：`路径(JSON Pointer 风格): 级别 [规则号] 说明 → 修法` + 汇总 + 上机前必过提示。"""
    out = out or sys.stdout
    # 目录/工程形态**恒带** file 前缀（哪怕只有一页：读者要一眼知道是哪页）；
    # 单文件形态省略（target 本身就是那一页）—— 与文档里的
    # `路径(JSON Pointer 风格): 级别 [规则号] 说明 → 修法` 一致。
    multi = report.get('kind') in ('project', 'dir') or len(report['files']) > 1
    for d in report['diagnostics']:
        print(_format_diag(d, multi), file=out)
    if report['truncated']:
        print('... 另有 %d 条诊断被 --max-diag 截断（见报告 truncated）' % report['truncated'], file=out)
    for line in report['delegated']:
        print('[delegated] %s' % line, file=out)
    s = report['summary']
    c = report['counts']
    print('fatal=%d error=%d warn=%d  页面=%d 控件=%d 子结构条目=%d  按类型=%s'
          % (s['fatal'], s['error'], s['warn'], c['pages'], c['controls'], c['items'],
             json.dumps(c['byType'], ensure_ascii=False, sort_keys=True)), file=out)
    if report['ok']:
        print('[OK] 编译式验收通过（fatal=0 error=0%s）target=%s'
              % (' warn=0' if report['strict'] else '', report['target']), file=out)
    else:
        print('[X] 编译式验收未过（fatal=%d error=%d%s）target=%s'
              % (s['fatal'], s['error'],
                 ' warn=%d（--strict 把 warn 当失败）' % s['warn'] if report['strict'] else '',
                 report['target']), file=out)
    print('上机前必过：本工具 fatal=0 / error=0%s（修完重跑本工具）'
          '+ python ui_tools/check_all.py <工程根>（图片尺寸 vs 控件盒 / AA / 倒角 / 透明底由它负责）'
          % ('，--strict 时 warn=0' if report['strict'] else ''), file=out)


def _force_utf8_stdio():
    """Windows 控制台默认 GBK —— 不切 UTF-8 时中文诊断会 UnicodeEncodeError。

    切不了**不静默**（本仓 lint_silent_except 拦的就是"只吞不留痕"）：返回失败清单
    `['stdout(TypeError: ...)']`，由 `main` 写进报告的 `delegated` 并在 stderr 留一行提示。
    """
    bad = []
    for name, stream in (('stdout', sys.stdout), ('stderr', sys.stderr)):
        try:
            stream.reconfigure(encoding='utf-8')
        except Exception as e:                     # noqa: BLE001 —— 失败要留痕，不许 pass
            bad.append('%s(%s: %s)' % (name, type(e).__name__, e))
    return bad


def main(argv=None, enc_warnings=None):
    ap = argparse.ArgumentParser(
        prog='ui_compile.py',
        description='编译器式 json 合理性验收（诊断带规则号 + 路径 + 修法；退出码表达成败）',
        epilog='退出码：0 无 fatal/error（--strict 时无 warn）；1 有 fatal/error（--strict 时有 warn）；'
               '2 用法错/内部异常。\nv1 规则（整改方案 §WS-1）：%s\n附加规则：%s\n全部规则号：%s'
               % ('、'.join(_V1_RULES), '、'.join(_EXTRA_RULES), '、'.join(ALL_RULES)))
    ap.add_argument('target', help='<json 文件> | <工程根>（扫 ui/*.json）| <目录>（扫 *.json）')
    ap.add_argument('--res', default=None, metavar='WxH',
                    help='目标屏分辨率（如 1024x600）：与页面 resolution 比对，不符报 RES001')
    ap.add_argument('--strict', action='store_true', help='warn 也当失败（退出码 1）')
    ap.add_argument('--rule', default=None, metavar='R1,R2',
                    help='只报这些规则（逗号分隔），如 SCH001,SCH002')
    ap.add_argument('--json', dest='json_out', default=None, metavar='PATH',
                    help='把完整报告写入该路径（唯一会写盘的地方；拒绝写到输入 json 上）')
    ap.add_argument('--max-diag', type=int, default=None, metavar='N',
                    help='报告最多列 N 条诊断（summary 仍按全部统计；截断记账在 truncated）')
    ap.add_argument('--quiet', action='store_true', help='只打汇总，不打逐条诊断')
    args = ap.parse_args(argv)
    try:
        report = compile_json(args.target, res=args.res, project_root=None,
                              strict=args.strict, rules=args.rule, max_diag=args.max_diag)
    except ValueError as e:
        print('[用法错] %s' % e, file=sys.stderr)
        return 2
    except _us.SchemaRegistryError as e:
        print('[注册表读不到] %s' % e, file=sys.stderr)
        return 2
    except Exception as e:                          # noqa: BLE001 —— 内部异常一律 2，不假装判过
        print('[内部错误] %s: %s' % (type(e).__name__, e), file=sys.stderr)
        return 2
    if enc_warnings:
        # 控制台编码切不了（见 _force_utf8_stdio）：报告里留一条，人工能看见这件事没做成
        report['delegated'].append(
            '控制台编码切换失败（%s）：中文诊断可能显示为乱码；'
            '改用 --json <路径> 落 UTF-8 报告再读' % '、'.join(enc_warnings))
    if args.json_out:
        outp = os.path.abspath(args.json_out)
        inputs = [os.path.abspath(p) for p in
                  ([args.target] if os.path.isfile(args.target) else [])]
        if outp in inputs:
            print('[用法错] --json 报告路径不能是输入 json 本身（拒绝覆盖用户的 json）：%s' % outp,
                  file=sys.stderr)
            return 2
        if os.path.isdir(outp):
            print('[用法错] --json 指向的是目录：%s' % outp, file=sys.stderr)
            return 2
        try:
            d = os.path.dirname(outp)
            if d and not os.path.isdir(d):
                os.makedirs(d)
            with open(outp, 'w', encoding='utf-8', newline='\n') as fh:
                json.dump(report, fh, ensure_ascii=False, indent=2)
            print('[报告] %s' % outp)
        except OSError as e:
            print('[用法错] 报告写盘失败：%s' % e, file=sys.stderr)
            return 2
    if not args.quiet:
        _print_report(report)
    else:
        s, c = report['summary'], report['counts']
        print('fatal=%d error=%d warn=%d  页面=%d 控件=%d  %s'
              % (s['fatal'], s['error'], s['warn'], c['pages'], c['controls'],
                 'OK' if report['ok'] else 'FAIL'))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main(enc_warnings=_force_utf8_stdio()))
