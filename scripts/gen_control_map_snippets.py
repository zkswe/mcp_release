# -*- coding: utf-8 -*-
"""mcp_control_map.json 的 json 片段重生成（注册表驱动，唯一真源 = ui_tools/ui_schema.json）。

背景：映射表片段历史上手抄，thumb 曾写成字符串（真机 ftu 加载无声挂死的真凶形态）。
本脚本把「片段字段/类型」对齐到注册表：
  · 缺**必填**字段 → 按注册表 defaults() 补（int 0 / bool false / string '' / color -1 /
    path '' / 对象类型按 sharedTypes 递归零值）；
  · 子盒对象字段（thumb/position/colorTab/picTab/size/point/range/iconBox）必须是 dict ——
    thumb 字符串旧式 → 转 {size, normalPic, pressedPic}（尺寸从文件名 NxM 猜，猜不到 24）；
  · colorTab/bgColorTab 补足五槽（已有值保留，缺槽 -1）；thumb 缺 requiredKeys 补零值；
  · 标量类型不符 → 回退注册表默认值；array 必须是 list；
  · **不动业务值**：caption/position/图片路径/已有色值一律保留；未知键保留（注册表外字段不删）。

用法：
    python scripts/gen_control_map_snippets.py            # 写回 mcp_control_map.json
    python scripts/gen_control_map_snippets.py --check    # 只报告会有哪些改动（退出码 1 = 有漂移）
"""
import copy
import io
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, 'ui_tools'))
import ui_schema_loader as us                     # noqa: E402

MAP_PATH = os.path.join(BASE, 'mcp_control_map.json')
_SIZE_IN_NAME = re.compile(r'(\d{2,5})x(\d{2,5})')


def _thumb_from_string(s):
    """thumb 字符串旧式 → 子盒对象（translate_tools 同口径：尺寸猜自文件名，缺省 24）。"""
    if not s:
        return us.type_zero('thumb')
    m = _SIZE_IN_NAME.search(os.path.basename(s))
    sz = int(m.group(1)) if m else 24
    return {'size': {'width': sz, 'height': sz}, 'normalPic': s, 'pressedPic': s}


def _fix_shared(ftype, value, changes, loc):
    """sharedTypes 对象字段修正（原地改 dict / 整体替换错误类型）。"""
    st = us.shared_types()[ftype]
    if not isinstance(value, dict):
        if ftype == 'thumb' and isinstance(value, str):
            changes.append('%s: thumb 字符串 → 子盒对象' % loc)
            return _thumb_from_string(value)
        changes.append('%s: %s 非对象（%s）→ 注册表零值' % (loc, ftype, type(value).__name__))
        return us.type_zero(ftype)
    for kk in (st.get('requiredKeys') or []):
        if kk not in value:
            expect = (st.get('fields') or {}).get(kk)
            value[kk] = us.type_zero(expect) if expect else None
            changes.append('%s: %s 缺 requiredKey %s → 补零值' % (loc, ftype, kk))
    for kk, expect in (st.get('fields') or {}).items():
        if kk not in value:
            dflt = (st.get('defaults') or {}).get(kk)
            if dflt is not None:                  # colorTab 五槽：缺槽补 -1（picTab 无 defaults 不补）
                value[kk] = copy.deepcopy(dflt)
                changes.append('%s: %s 缺槽 %s → 补 %r' % (loc, ftype, kk, dflt))
            continue
        v = value[kk]
        if expect in us.shared_types():           # 子盒套子盒（thumb.size）
            value[kk] = _fix_shared(expect, v, changes, '%s.%s' % (loc, kk))
        else:
            ok = (isinstance(v, int) and not isinstance(v, bool)) if expect in ('int', 'color') \
                else isinstance(v, str) if expect in ('string', 'path') else True
            if not ok:
                value[kk] = us.type_zero(expect)
                changes.append('%s: %s.%s 类型应为 %s（实际 %s）→ 零值'
                               % (loc, ftype, kk, expect, type(v).__name__))
    return value


def _fix_control(tname, ctl, changes, loc, fill_missing=True):
    """单控件 dict：补必填缺键 + 修正字段类型（原地改；业务值保留）。

    fill_missing=False（嵌套子结构/数组元素）：只修**已存在字段**的类型，不补新键——
    片段里嵌套结构的键取舍是业务决策（典型：listview-wheel-picker 行模板**故意无 subItem**，
    tests/test_control_map.py 钉死），生成器不替它做主；该例外已在注册表维护记录备案。
    """
    entry = us.load()['controls'].get(tname) or us.load()['subStructures'].get(tname)
    if entry is None:
        return                                     # 注册表外类型：不动
    fields = entry.get('fields') or {}
    dflts = None
    if fill_missing:
        for k, spec in fields.items():
            if k not in ctl and spec.get('required'):
                if dflts is None:
                    dflts = us.defaults(tname)
                ctl[k] = copy.deepcopy(dflts[k])
                changes.append('%s: 缺必填 %s → 补默认值' % (loc, k))
    for k, v in list(ctl.items()):
        spec = fields.get(k)
        if spec is None:
            continue                               # 未知键保留
        ftype = spec.get('type')
        if ftype in us.shared_types():
            ctl[k] = _fix_shared(ftype, v, changes, '%s.%s' % (loc, k))
        elif ftype in us.load()['subStructures']:
            items = v if isinstance(v, list) else [v]
            if not isinstance(v, (dict, list)):
                ctl[k] = us.type_zero(ftype)
                changes.append('%s.%s: 子结构非对象 → 注册表零值' % (loc, k))
                continue
            for item in items:
                if isinstance(item, dict):
                    _fix_control(ftype, item, changes, '%s.%s' % (loc, k), fill_missing=False)
        elif ftype == 'array':
            if not isinstance(v, list):
                ctl[k] = []
                changes.append('%s.%s: 应为数组（实际 %s）→ []' % (loc, k, type(v).__name__))
            elif spec.get('itemType') in us.load()['subStructures'] \
                    or spec.get('itemType') in us.load()['controls']:
                for item in v:
                    if isinstance(item, dict):
                        _fix_control(spec['itemType'], item, changes, '%s.%s[]' % (loc, k),
                                     fill_missing=False)
        else:
            ok = (isinstance(v, int) and not isinstance(v, bool)) if ftype in ('int', 'color') \
                else isinstance(v, bool) if ftype == 'bool' \
                else isinstance(v, str) if ftype in ('string', 'path') else True
            if not ok:
                if dflts is None:
                    dflts = us.defaults(tname)
                ctl[k] = copy.deepcopy(dflts.get(k, us.type_zero(ftype)))
                changes.append('%s.%s: 类型应为 %s（实际 %s）→ 默认值'
                               % (loc, k, ftype, type(v).__name__))


def regen(data):
    """遍历映射表，重生成所有 json 片段。返回 (改动条目数, 改动说明列表)。"""
    n_entries, changes = 0, []
    for sname, arr in (data.get('sources') or {}).items():
        for e in arr or []:
            j = e.get('json')
            if not j:
                continue
            try:
                obj = json.loads(j)
            except Exception as ex:
                changes.append('%s/%s: 片段本身不是合法 json（%s），跳过'
                               % (sname, e.get('name'), ex))
                continue
            loc0 = '%s/%s' % (sname, e.get('name'))
            before = len(changes)
            for key, ctl in obj.items():
                tname = key.split('__')[0]
                if isinstance(ctl, dict):
                    _fix_control(tname, ctl, changes, '%s:%s' % (loc0, key))
            if len(changes) > before:
                e['json'] = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
                n_entries += 1
    return n_entries, changes


def main():
    check = '--check' in sys.argv
    data = json.loads(io.open(MAP_PATH, encoding='utf-8').read())
    n, changes = regen(data)
    print('scanned json snippets; %d entries need regeneration' % n)
    for c in changes[:40]:
        print('   ' + c)
    if len(changes) > 40:
        print('   ... (+%d more)' % (len(changes) - 40))
    if check:
        print('[FAIL] 片段与注册表漂移 %d 条（跑 gen_control_map_snippets.py 重生成）' % n
              if n else '[PASS] 全部片段与注册表一致')
        return 1 if n else 0
    if n:
        io.open(MAP_PATH, 'w', encoding='utf-8', newline='\n').write(
            json.dumps(data, ensure_ascii=False, indent=1) + '\n')
        print('written: %s（%d 条片段已重生成）' % (MAP_PATH, n))
    else:
        print('no changes; file untouched')
    return 0


if __name__ == '__main__':
    sys.exit(main())
