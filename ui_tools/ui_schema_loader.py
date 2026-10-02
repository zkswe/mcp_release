# -*- coding: utf-8 -*-
"""FlyThings UI json 布局规范注册表加载器（唯一消费入口）。

真源 = 与本文件同目录的 ui_schema.json（机器可读注册表：page.rootFields /
sharedTypes / controls / subStructures / valueRules）。设计原则：**消费方一律从
注册表派生，禁止再抄一份硬编码**——thumb 写成字符串导致真机 ftu 无声挂死，
根因就是规范散落多处互相矛盾（check_all 模板只有键名没有类型、translate_tools
_SCHEMA_FILL 硬编码、mcp_control_map.json 片段旧式字符串 thumb）。

消费方：
  - check_all.py      #14 必写键校验 + 4b 全控件类型检查
  - translate_tools.py 发射层缺键补齐（thumb/colorTab 等子盒结构）
  - scripts/gen_control_map_snippets.py / scripts/gen_ui_schema_docs.py
  - kb_tools.flythings_ui_schema（op）

容错口径：注册表文件缺失 / 解析失败 → 抛 SchemaRegistryError（带明确路径），
**不静默**——消费方拿不到规范就必须响，不许退回任何内嵌副本。

用法：
    import ui_schema_loader as us
    reg = us.load()                       # 注册表 dict（带缓存）
    us.required_fields('seekbar')         # 必填键列表
    us.field_type('seekbar', 'thumb')     # 'thumb'
    us.defaults('seekbar')                # {field: default}（含类型零值）
    us.type_zero('colorTab')              # 单个 sharedType 的零值对象
    us.is_interactive('seekbar')          # True
    us.type_check('seekbar', ctl_dict)    # 违规列表（fatal/error/warn）
"""
import copy
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(BASE, 'ui_schema.json')

# 标量类型零值（defaults() 对「无 default 的必填字段」用；type_check 的类型判据也在这）
_SCALAR_ZERO = {'int': 0, 'bool': False, 'string': '', 'color': -1, 'path': '', 'array': []}
# 子盒对象类型（sharedTypes 里 shape=object 的键；写成字符串 = 真机 ftu 无声挂死，见 valueRules.subboxType）
_SUBBOX_FATAL = ('写成字符串（或其他非对象类型）= 真机 ftu 加载无声挂死'
                 '（无 onUI_init/onUI_show、无报错日志；A/B 实测 V85X iMirror 2026-10-02）')

_CACHE = None


class SchemaRegistryError(RuntimeError):
    """注册表缺失 / 损坏 / 查询了不存在的类型。消息里永远带路径或类型名。"""


def load():
    """加载 ui_schema.json（带缓存）。文件缺失/解析失败 → SchemaRegistryError（含路径）。"""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not os.path.isfile(SCHEMA_PATH):
        raise SchemaRegistryError(
            'UI schema 注册表缺失: %s（ui_schema.json 必须与 ui_schema_loader.py 同目录分发）'
            % SCHEMA_PATH)
    try:
        with open(SCHEMA_PATH, encoding='utf-8') as f:
            reg = json.load(f)
    except Exception as e:
        raise SchemaRegistryError(
            'UI schema 注册表解析失败: %s（%s: %s）' % (SCHEMA_PATH, type(e).__name__, e))
    for key in ('sharedTypes', 'controls', 'subStructures', 'valueRules'):
        if key not in reg:
            raise SchemaRegistryError(
                'UI schema 注册表缺顶层键 %r: %s' % (key, SCHEMA_PATH))
    _CACHE = reg
    return reg


def reload():
    """清缓存重载（测试 / 注册表热更新用）。"""
    global _CACHE
    _CACHE = None
    return load()


def _entry(control_type):
    """控件或子结构条目。check_all 历史别名 listitem/subitem/wave/slideitem 即注册表 subStructures 键。"""
    reg = load()
    e = reg['controls'].get(control_type)
    if e is None:
        e = reg['subStructures'].get(control_type)
    if e is None:
        raise SchemaRegistryError(
            '未知控件/子结构类型: %r（注册表 %s 中既不在 controls 也不在 subStructures）'
            % (control_type, SCHEMA_PATH))
    return e


def known_types():
    """全部可校验类型（控件 + 子结构），排序后返回。"""
    reg = load()
    return sorted(list(reg['controls']) + list(reg['subStructures']))


def control_types():
    return sorted(load()['controls'])


def sub_structure_types():
    return sorted(load()['subStructures'])


def shared_types():
    return load()['sharedTypes']


def value_rules():
    return load()['valueRules']


def is_container(control_type):
    reg = load()
    e = reg['controls'].get(control_type)
    return bool(e and e.get('container'))


def is_interactive(control_type):
    """控件是否可交互（子结构一律 False；未知类型抛 SchemaRegistryError）。"""
    reg = load()
    if control_type in reg['subStructures']:
        return False
    return bool(_entry(control_type).get('interactive'))


def required_fields(control_type):
    """必填键列表（注册表声明顺序；未知类型抛 SchemaRegistryError）。"""
    e = _entry(control_type)
    return [k for k, spec in (e.get('fields') or {}).items() if spec.get('required')]


def field_type(control_type, field):
    """字段类型名（int/bool/string/color/path/array 或 sharedTypes 键）；未知字段返回 None。"""
    e = _entry(control_type)
    spec = (e.get('fields') or {}).get(field)
    return spec.get('type') if spec else None


def callbacks(control_type):
    """该控件可生成的回调桩（schema `callbacks` 字段；没有则空表）。

    每条 = {name, sig, when, stub, note}；`name`/`sig` 里的 `{Caption}` 是占位，
    生成时替换为 json 里该控件的 `caption` 值（**不是** key 里的数字）。
    """
    return list(_entry(control_type).get('callbacks') or [])


def field_spec(control_type, field):
    """字段完整声明（type/required/default/note/itemType）；未知字段返回 None。"""
    e = _entry(control_type)
    return (e.get('fields') or {}).get(field)


def type_zero(type_name, _depth=0):
    """单个类型的零值：标量取 _SCALAR_ZERO；sharedTypes 对象按键递归生成（含表内 defaults 覆盖）；
    subStructures 类型（listitem/subitem）按必填键递归生成。

    colorTab → 五槽（color1..4 恒 -1 来自注册表 defaults；color0 零值 -1）
    thumb    → {'size': {'width': 0, 'height': 0}, 'normalPic': '', 'pressedPic': ''}
    """
    if _depth > 8:
        raise SchemaRegistryError('类型递归过深（疑似循环引用）: %r' % type_name)
    if type_name in _SCALAR_ZERO:
        return copy.deepcopy(_SCALAR_ZERO[type_name])
    reg = load()
    sub_struct = reg['subStructures'].get(type_name)
    if sub_struct is not None:
        return {k: type_zero(spec['type'], _depth + 1)
                for k, spec in (sub_struct.get('fields') or {}).items()
                if spec.get('required')}
    st = reg['sharedTypes'].get(type_name)
    if st is None:
        raise SchemaRegistryError(
            '未知类型: %r（不是标量，也不在 %s 的 sharedTypes 里）' % (type_name, SCHEMA_PATH))
    if st.get('shape') != 'object':
        raise SchemaRegistryError(
            'sharedTypes.%s 的 shape 不是 object: %s' % (type_name, SCHEMA_PATH))
    out = {k: type_zero(t) for k, t in (st.get('fields') or {}).items()}
    for k, v in (st.get('defaults') or {}).items():
        out[k] = copy.deepcopy(v)
    return out


def defaults(control_type):
    """{field: default}：有 default 用 default；无 default 的**必填**字段给类型零值
    （int 0 / bool false / string '' / color -1 / path '' / array [] / 对象类型按 sharedTypes 递归）。
    非必填且无 default 的字段不产出（条件字段不强加）。"""
    e = _entry(control_type)
    out = {}
    for k, spec in (e.get('fields') or {}).items():
        if 'default' in spec:
            out[k] = copy.deepcopy(spec['default'])
        elif spec.get('required'):
            out[k] = type_zero(spec['type'])
    return out


def _check_scalar(ftype, value):
    """标量类型判据。bool 是 int 子类，必须显式排除反向误判。"""
    if ftype in ('int', 'color'):
        return isinstance(value, int) and not isinstance(value, bool)
    if ftype == 'bool':
        return isinstance(value, bool)
    if ftype in ('string', 'path'):
        return isinstance(value, str)
    if ftype == 'array':
        return isinstance(value, list)
    return None                                   # 非标量（sharedTypes 对象）


def type_check(control_type, data, _path=''):
    """对控件 dict 逐字段校验类型，返回违规列表 [{field, level, msg}]。

    level:
      - fatal：子盒对象字段（thumb/position/colorTab/picTab/size/point/range/iconBox 等
        sharedTypes 对象型）写成字符串或其他非 dict —— 真机 ftu 加载无声挂死（A/B 实测）
      - error：标量类型不符 / array 不是 list / 对象缺 requiredKeys / 数组元素不是 dict
      - warn ：注册表外的未知键（不报错，只收集）
    只校验**存在**的字段；缺必填键是 check_all #14 的职责（required_fields）。
    """
    e = _entry(control_type)
    fields = e.get('fields') or {}
    reg = load()
    st = reg['sharedTypes']
    sst = reg['subStructures']
    out = []
    if not isinstance(data, dict):
        return [{'field': _path or control_type, 'level': 'error',
                 'msg': '控件本体不是对象（是 %s）' % type(data).__name__}]
    for k, v in data.items():
        spec = fields.get(k)
        loc = '%s%s' % (_path, k)
        if spec is None:
            out.append({'field': loc, 'level': 'warn',
                        'msg': '未知键（%s 注册表未声明，不报错仅提示）' % control_type})
            continue
        ftype = spec.get('type')
        if ftype in sst:                          # 子结构类型（listitem/subitem）
            # 注册表把 listview.item 声明成单个 listitem、item.subItem 声明成单个 subitem；
            # 真机 json 里 subItem 实际是**数组**——dict 按单结构校、list 逐元素校，两种都收。
            items = v if isinstance(v, list) else [v]
            if not isinstance(v, (dict, list)):
                out.append({'field': loc, 'level': 'fatal',
                            'msg': '%s 必须是对象（%s），实际是 %s —— %s'
                                   % (k, ftype, type(v).__name__, _SUBBOX_FATAL)})
                continue
            for i, item in enumerate(items):
                ploc = loc if isinstance(v, dict) else '%s[%d]' % (loc, i)
                if not isinstance(item, dict):
                    out.append({'field': ploc, 'level': 'error',
                                'msg': '%s 必须是对象（%s），实际是 %s'
                                       % (ploc, ftype, type(item).__name__)})
                    continue
                for vio in type_check(ftype, item, ploc + '.'):
                    if vio['level'] != 'warn':
                        out.append(vio)
        elif ftype in st:                         # 子盒对象类型
            if not isinstance(v, dict):
                fatal = st[ftype].get('fatal') or _SUBBOX_FATAL
                out.append({'field': loc, 'level': 'fatal',
                            'msg': '%s 必须是对象（%s），实际是 %s —— %s'
                                   % (k, ftype, type(v).__name__, fatal)})
                continue
            sub = st[ftype]
            for kk in (sub.get('requiredKeys') or []):
                if kk not in v:
                    out.append({'field': loc, 'level': 'error',
                                'msg': '%s 缺 %s（%s 子结构 requiredKeys）' % (k, kk, ftype)})
            for kk, vv in v.items():
                expect = (sub.get('fields') or {}).get(kk)
                if expect is None:
                    continue                      # 子盒内的额外键不管（picTab 键可不全）
                r = _check_scalar(expect, vv)
                if r is None:                     # 子盒里再嵌对象（如 thumb.size）
                    if not isinstance(vv, dict):
                        out.append({'field': '%s.%s' % (loc, kk), 'level': 'fatal',
                                    'msg': '%s.%s 必须是对象（%s），实际是 %s —— %s'
                                           % (k, kk, expect, type(vv).__name__, _SUBBOX_FATAL)})
                elif not r:
                    out.append({'field': '%s.%s' % (loc, kk), 'level': 'error',
                                'msg': '%s.%s 类型应为 %s，实际是 %s(%r)'
                                       % (k, kk, expect, type(vv).__name__, vv)})
        elif ftype == 'array':
            if not isinstance(v, list):
                out.append({'field': loc, 'level': 'error',
                            'msg': '%s 必须是数组，实际是 %s' % (k, type(v).__name__)})
                continue
            it = spec.get('itemType')
            if it:
                # itemType 非注册表类型 → 只查「元素是 dict」，不做字段级校验（显式分支，不吞异常）
                it_known = it in reg['controls'] or it in reg['subStructures']
                for i, item in enumerate(v):
                    if not isinstance(item, dict):
                        out.append({'field': '%s[%d]' % (loc, i), 'level': 'error',
                                    'msg': '%s[%d] 必须是对象（%s），实际是 %s'
                                           % (k, i, it, type(item).__name__)})
                        continue
                    if it_known:
                        for vio in type_check(it, item, '%s[%d].' % (loc, i)):
                            if vio['level'] != 'warn':     # 子项未知键不刷屏
                                out.append(vio)
        else:
            r = _check_scalar(ftype, v)
            if r is False:
                out.append({'field': loc, 'level': 'error',
                            'msg': '%s 类型应为 %s，实际是 %s(%r)'
                                   % (k, ftype, type(v).__name__, v)})
    return out
