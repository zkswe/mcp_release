# -*- coding: utf-8 -*-
"""FlyThings MCP **op 契约注册表加载器（唯一消费入口）**。

真源 = 与本文件同目录的 op_spec.json（机器可读注册表：每个 op 的
summary / 触发别名 / flow / params / returns / rules / keywords / docRef / seeAlso /
risk / category / stage）。

设计原则（与 ui_tools/ui_schema_loader.py 同一条纪律）：
  **消费方一律从注册表派生，禁止再抄一份硬编码。**
  改动前：同一个 op 的契约散落在 5 处——kb_tools.py 的 docstring（散文，受 12000 字符硬
  预算约束）、tools_manifest.json、gate_catalog.json、op_seealso.json、knowledge 文档；
  每次加 op / 加参数都要人肉同步，且预算一顶就只能去打磨散文。
  改动后：结构化契约只写一次（op_spec.json），其余全部**派生**。

消费方：
  - scripts/gen_op_docs.py      → kb_tools.py 的 docstring（= MCP 工具 description）
  - scripts/gen_manifest.py     → tools_manifest.json（brief/args/risk/category/stage）
  - scripts/gen_gate_catalog.py → gate_catalog.json（brief/args/stage）
  - scripts/gen_seealso.py      → op_seealso.json（seeAlso）
  - scripts/check_consistency.py→ 预算门禁（口径 = 渲染产物字符数）

容错口径：注册表文件缺失 / 解析失败 / 查询了不存在的 op → 抛 OpSpecError（消息里带明确
路径或 op 名），**不静默**——消费方拿不到契约就必须响，不许退回任何内嵌副本。

用法：
    import op_spec_loader as osl
    osl.load()                       # 注册表 dict（带缓存）
    osl.registered()                 # 已登记的 op 名列表（排序）
    osl.spec('flythings_pack_upgrade')  # 该 op 的 spec（未登记 → OpSpecError）
    osl.render('flythings_pack_upgrade')  # 渲染后的 description 文本（唯一实现）
    osl.budget_report()              # {total, per_op:[(n, chars)], over:[]}
"""
import io
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
SPEC_PATH = os.path.join(BASE, 'op_spec.json')

RISK_VALUES = ('read', 'write', 'device')
STAGE_VALUES = ('design', 'build', 'other')
CATEGORY_VALUES = ('kbase', 'layout', 'project', 'build', 'assets', 'i18n',
                   'package', 'device', 'ui-visual')

_CACHE = None


class OpSpecError(RuntimeError):
    """注册表缺失 / 损坏 / 查询不存在的 op。消息里永远带路径或 op 名。"""


def load():
    """加载 op_spec.json（带缓存）。文件缺失/解析失败 → OpSpecError（含路径）。"""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not os.path.isfile(SPEC_PATH):
        raise OpSpecError('op 契约注册表缺失: %s（op_spec.json 必须随包分发）' % SPEC_PATH)
    try:
        with io.open(SPEC_PATH, encoding='utf-8') as f:
            reg = json.load(f)
    except Exception as e:
        raise OpSpecError('op 契约注册表解析失败: %s（%s: %s）'
                          % (SPEC_PATH, type(e).__name__, e))
    if not isinstance(reg.get('ops'), dict):
        raise OpSpecError('op 契约注册表缺少 ops 段: %s' % SPEC_PATH)
    _CACHE = reg
    return reg


def registered():
    """已登记的 op 名（排序）。"""
    return sorted(load()['ops'].keys())


def spec(op):
    """取单个 op 的 spec；未登记 → OpSpecError。"""
    entry = load()['ops'].get(op)
    if not isinstance(entry, dict):
        raise OpSpecError('%s 未登记进 op_spec.json（改 op 契约请改注册表，勿只改 docstring）' % op)
    return entry


def _field(op, key, default=None):
    return spec(op).get(key, default)


def summary(op):
    return _field(op, 'summary', '')


def risk(op):
    return _field(op, 'risk')


def category(op):
    return _field(op, 'category')


def stage(op):
    return _field(op, 'stage')


def doc_ref(op):
    return _field(op, 'docRef')


def seealso(op):
    """op 的「去哪找」列表；未登记 seeAlso → []。"""
    v = _field(op, 'seeAlso') or []
    return [str(x) for x in v]


def brief(op, limit=90):
    """工具目录用的一行摘要（与 tools_manifest / gate_catalog 同源）。"""
    return summary(op)[:limit]


# --------------------------------------------------------------------------
# 渲染：**唯一实现**。kb_tools.py 的 docstring、未来可能的运行时注入，都走这里。
# --------------------------------------------------------------------------

def _line_triggers(v):
    return '触发：%s' % ' / '.join(str(x) for x in v) if v else ''


def _line_params(v):
    """紧凑单行：`参数：name→说明；name→说明`。

    只渲染注册表里登记了说明的参数；参数的**存在与顺序**一律以函数签名为准（注册表不复制签名）。
    """
    parts = []
    for p in v or []:
        name = (p or {}).get('name')
        desc = (p or {}).get('desc')
        if name and desc:
            parts.append('%s→%s' % (name, desc))
    return '参数：%s' % '；'.join(parts) if parts else ''


def _line_list(label, v, sep='；'):
    items = [str(x) for x in (v or []) if str(x).strip()]
    return '%s：%s' % (label, sep.join(items)) if items else ''


def _lines_prefix(prefix, v):
    return '\n'.join('%s %s' % (prefix, str(x)) for x in (v or []) if str(x).strip())


def _render_fields(op, order):
    """按给定字段顺序渲染（`render` 与 `render_contract` 的唯一实现）。"""
    s = spec(op)
    body = []
    for key in order:
        if key == 'summary':
            continue
        v = s.get(key)
        if key == 'triggers':
            t = _line_triggers(v)
        elif key == 'params':
            t = _line_params(v)
        elif key == 'returns':
            t = _line_list('返回', v)
        elif key == 'hardRules':
            t = _lines_prefix('\u26a0\ufe0f\u26a0\ufe0f', v)
        elif key == 'rules':
            t = _lines_prefix('\u26a0\ufe0f', v)
        elif key == 'keywords':
            t = _line_list('检索词', v, ' / ')
        elif key == 'docRef':
            t = ('细节见 %s' % v) if v else ''
        else:
            # flow / notes 允许是字符串或字符串数组（数组按行拼，便于注册表按段落维护）
            if isinstance(v, list):
                t = '\n'.join(str(x) for x in v if str(x).strip())
            else:
                t = (str(v) if v else '')
        if t and t.strip():
            body.append(t.strip())
    return (summary(op).strip() + '\n\n' + '\n'.join(body)).strip()


def render(op):
    """**常驻面**（tool description）文本：只渲染 `renderOrder` 里的字段。

    工具面分三层（真源 `tiers`）：常驻 = 「选不选 + 怎么调 + 安全铁律」；
    完整契约（flow/rules/keywords/notes…）走 `render_contract()` 按需拉。
    所以本函数是**预算敏感**的 —— 加字段前先想清楚它属不属于常驻面。
    """
    order = load().get('renderOrder') or ['summary', 'triggers', 'params', 'hardRules']
    return _render_fields(op, order)


def render_contract(op):
    """**完整契约**文本（按需：`op='describe:<名>'` / 资源 `flythings://ops/<名>`）。

    比常驻面多出 flow / returns / rules / keywords / notes —— 这些**只在选中之后**才需要，
    放进常驻面就是把每次会话的上下文预算花在"可能用不到"的细节上（2026-10-03 架构调整）。
    """
    order = load().get('contractOrder') or (
        load().get('renderOrder') or ['summary', 'triggers', 'params', 'hardRules']
    ) + ['flow', 'returns', 'rules', 'keywords', 'notes']
    return _render_fields(op, order)


# --------------------------------------------------------------------------
# 预算与自检（供门禁消费）
# --------------------------------------------------------------------------

def budget_report():
    """常驻面预算 → {per_op, total, perOpMax, totalMax, over, contract_over, contractPerOpMax}。

    `per_op` 量的是**常驻面**（`render` = tool description），不是完整契约 ——
    完整契约走按需、不进常驻，只受 `contractPerOpMax` 单条约束（合计不设限）。
    """
    b = load().get('budget') or {}
    per_op_max = int(b.get('perOpMax', 360))
    total_max = int(b.get('totalMax', 6000))
    c_max = int(b.get('contractPerOpMax', 900))
    rows = [(op, len(render(op))) for op in registered()]
    rows.sort(key=lambda r: -r[1])
    crows = [(op, len(render_contract(op))) for op in registered()]
    crows.sort(key=lambda r: -r[1])
    return {'per_op': rows, 'total': sum(c for _, c in rows),
            'perOpMax': per_op_max, 'totalMax': total_max,
            'over': [r for r in rows if r[1] > per_op_max],
            'contract_per_op': crows, 'contractPerOpMax': c_max,
            'contract_over': [r for r in crows if r[1] > c_max]}


def validate():
    """注册表自检：返回问题列表（空 = 合规）。供 gen_op_docs.py --check 消费。"""
    errs = []
    reg = load()
    if not str(reg.get('authority') or '').strip():
        errs.append('缺少 authority 声明（注册表必须声明唯一真源与消费方）')
    for op, s in sorted(reg['ops'].items()):
        if not str(s.get('summary') or '').strip():
            errs.append('%s: 缺 summary（唯一必填字段）' % op)
        if s.get('risk') not in RISK_VALUES:
            errs.append('%s: risk=%r 非法（应为 %s）' % (op, s.get('risk'), '/'.join(RISK_VALUES)))
        if s.get('stage') not in STAGE_VALUES:
            errs.append('%s: stage=%r 非法（应为 %s）' % (op, s.get('stage'), '/'.join(STAGE_VALUES)))
        if s.get('category') not in CATEGORY_VALUES:
            errs.append('%s: category=%r 非法（应为 %s）'
                        % (op, s.get('category'), '/'.join(CATEGORY_VALUES)))
        for p in s.get('params') or []:
            if not p.get('name') or not p.get('desc'):
                errs.append('%s: params 项缺 name/desc: %r' % (op, p))
        for what in ('seeAlso',):
            for path in s.get(what) or []:
                if not os.path.isfile(os.path.join(BASE, str(path))):
                    errs.append('%s: %s 指向不存在的文件: %s' % (op, what, path))
        d = s.get('docRef')
        if d and not os.path.isfile(os.path.join(BASE, str(d))):
            errs.append('%s: docRef 指向不存在的文件: %s' % (op, d))

    # 三层架构（tiers）+ 预算口径必须齐备 —— 否则消费方会各写一份渲染顺序
    tiers = reg.get('tiers') or {}
    for seg in ('resident', 'onDemand', 'deep'):
        if not (tiers.get(seg) or {}).get('what'):
            errs.append('tiers.%s 缺说明（三层架构是渲染口径的来源）' % seg)
    if list(reg.get('renderOrder') or []) != list((tiers.get('resident') or {}).get('fields') or []):
        errs.append('renderOrder 与 tiers.resident.fields 不一致（常驻面归属只能有一处口径）')
    if not set(reg.get('renderOrder') or []) <= set(reg.get('contractOrder') or []):
        errs.append('renderOrder 必须是 contractOrder 的子集（常驻 ⊆ 完整契约）')
    for k in ('perOpMax', 'totalMax', 'contractPerOpMax'):
        if not (reg.get('budget') or {}).get(k):
            errs.append('budget.%s 缺失' % k)

    # notes 债基线：**只减不增**（见 op_spec.json.notesDebt 的口径）
    debt = (reg.get('notesDebt') or {}).get('items') or {}
    for op, s in sorted(reg['ops'].items()):
        v = s.get('notes')
        if not v:
            continue
        n = len(v if isinstance(v, str) else '\n'.join(str(x) for x in v))
        if op not in debt:
            errs.append('%s: 新增了 notes —— notes 是迁移兜底桶，请写进 flow/params/rules/keywords'
                        '（常驻/按需字段），别往兜底桶里加' % op)
        elif n > int(debt[op]):
            errs.append('%s: notes 从登记的 %d 字符涨到 %d —— 这个桶只许减，请拆进结构化字段'
                        % (op, int(debt[op]), n))
    for op in debt:
        if op not in reg['ops']:
            errs.append('notesDebt 登记了不存在的 op: %s' % op)
    return errs


if __name__ == '__main__':
    rep = budget_report()
    print('已登记 op: %d' % len(registered()))
    for op, c in rep['per_op']:
        print('  %-38s %4d' % (op, c))
    print('渲染合计 %d 字符（上限 %d，单条上限 %d）'
          % (rep['total'], rep['totalMax'], rep['perOpMax']))
    print('超限：%s' % (rep['over'] or '无'))
    errs = validate()
    print('自检：%s' % ('\n  '.join([''] + errs) if errs else '通过'))
