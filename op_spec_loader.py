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
import re

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


def excludes(op):
    """本 op 的**出局词** → {'why':…, 'phrases':[…]}；未登记 → {'why':'','phrases':[]}。

    语义（2026-10-04，用户口径）：用户原话里出现 `phrases` 任一片段时，本 op 在 `_find`
    里**直接出局**（不是降权）—— 用来治「同名词不同动作」：比如「给客户看下效果」里的
    「看效果」说明要的是**预览稿**，`create_project` 就不该抢答（实测它靠「项目」这个词
    拿到 6 分居首，把 ui_preview 压到第 3）。

    与 `triggers` 的关系：triggers 是**选它**的正向词，excludes 是**排除它**的反向词。
    两者不许重叠（`validate()` 会红）—— 同一句既触发又排除，行为就没法解释了。
    """
    v = _field(op, 'excludes') or {}
    if not isinstance(v, dict):
        return {'why': '', 'phrases': []}
    return {'why': str(v.get('why') or ''),
            'phrases': [str(x) for x in (v.get('phrases') or [])]}


def exclude_hit(op, query):
    """用户原话是否命中本 op 的出局词 → 命中的片段（'' = 没命中）。

    匹配器复用 `kb_authority.alias_hit`（与 triggers/keywords 同一份实现）——
    不另造第二套匹配，否则「什么算命中」会有两种口径。

    ⚠️ 一个必须守的例外（2026-10-04 实测）：**纯 ASCII 短片段要求词边界**。
    中文没有词边界，子串匹配是对的；但拉丁词有 —— `qt` 会命中 `mqtt`，
    `xml` 会命中 `xmlhttp`。出局词写错方向的代价是「该出的候选被吃掉」，
    比多给候选危险得多，所以这里收紧：`[a-z0-9_.]{1,3}` 的片段只有作为**整词**
    出现才算命中（`加个 mqtt 包` → `qt` 不算；`qt 的按钮` → `qt` 算）。
    """
    q = (query or '').strip()
    if not q:
        return ''
    try:
        import kb_authority as ka
    except Exception:                      # 匹配器不可用 → 不排除（宁可多给候选，不可错杀）
        return ''
    for ph in excludes(op)['phrases']:
        ph = str(ph).strip()
        if not ph:
            continue
        if re.fullmatch(r'[A-Za-z0-9_.]{1,3}', ph):
            if re.search(r'(?<![A-Za-z0-9_.])%s(?![A-Za-z0-9_.])' % re.escape(ph),
                         q, re.I):
                return ph
            continue
        if ka.alias_hit(ph, q):
            return ph
    return ''


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


def _field_text(op, key):
    """单个字段渲染成一行/一段文本（**唯一实现**，`render` 与 `render_section` 共用）。

    ⚠️ 这段为什么被抽出来（2026-10-05 B1 分层）：分层要保证「各段按 contractOrder 顺序拼接
    == 完整契约」**逐字节**成立。原来 `_render_fields` 是「summary + '\\n\\n' + '\\n'.join(正文)」，
    分隔符绑在函数里 —— 一旦按段分别渲染，每段各带一个 summary、分隔符也对不上，等式就不成立。
    拆成"逐字段渲染 + 统一的 `_render_parts` 拼接"之后，分段只是**取字段的子集**，拼接规则唯一。
    """
    s = spec(op)
    v = s.get(key)
    if key == 'summary':
        return summary(op).strip()
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
    elif key == 'excludes':
        # 出局词：渲染成一行「别把它用在这儿」，让 AI 在 describe 阶段就看得到
        # 为什么"这句话不该找我"。空/未登记不渲染。
        ph = excludes(op)['phrases']
        t = ('不适用（问法里出现这些就先看别的 op）：%s' % ' / '.join(ph)) if ph else ''
    elif key == 'docRef':
        t = ('细节见 %s' % v) if v else ''
    else:
        # flow / notes 允许是字符串或字符串数组（数组按行拼，便于注册表按段落维护）
        if isinstance(v, list):
            t = '\n'.join(str(x) for x in v if str(x).strip())
        else:
            t = (str(v) if v else '')
    return t.strip() if t else ''


def _render_parts(op, order):
    """按给定字段顺序渲染成**非空片段列表**（拼接规则见函数尾，唯一）。

    'summary' 是骨架里的第一段，且它与正文之间用空行 —— 这就是**分隔符的唯一归属**。
    """
    parts = []
    for key in order:
        t = _field_text(op, key)
        if t:
            parts.append(t)
    return parts


def _join_parts(parts):
    """片段列表 → 最终文本。**分隔符只在这里定义一处**。

    规则（必须与原实现逐字节一致，2026-10-05 重构时用 48/48 op 的快照比对验证过）：
      · `summary` 与正文之间是**空行**（`'\\n\\n'`）；
      · 正文各字段之间是**单换行**（`'\\n'`）—— 不是空行。
    我第一次写成"所有片段都空行"就与旧输出差了 1 个字符，靠基线快照当场抓到。
    """
    if not parts:
        return ''
    head, body = parts[0], parts[1:]
    return (head + '\n\n' + '\n'.join(body)) if body else head


def _render_fields(op, order):
    """按给定字段顺序渲染（`render` / `render_contract` / `render_section` 的唯一实现）。"""
    return _join_parts(_render_parts(op, order))


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
# 按需面**分段取用**（`describe(section=…)` / 资源 `flythings://ops/<名>/<段>`）
#
# 为什么要它（2026-10-05 实测）：按需面单条上限 900 字符，而 `flythings_get_package_api`
# 已到 **892（余 8）**、`i18n_to_json` 805、`build_ui_flow` 804 —— 「往契约里加东西」这条路
# 事实上已经到顶（加 `excludes` 一次就吃掉 47 字符、加一条规则吃掉 411）。分层把计费单位
# 从"整条 op"换成"一次取用"：实测单段最大 **645**（rules）、默认形态最大 = 全文 805。
# 段划分是**对 contractOrder 的精确划分**（不重排、不新增字段），所以常驻面与全文逐字节不变。
# --------------------------------------------------------------------------

def sections():
    """按需面的段划分 → `[{'id', 'fields', 'what'}]`（真源 `tiers.onDemand.sections`）。

    老注册表没有该键时回落成单段 `all`（= contractOrder），所以本函数可以无条件调用。
    """
    secs = (load().get('tiers') or {}).get('onDemand', {}).get('sections') or []
    out = []
    for s in secs:
        if isinstance(s, dict) and s.get('id') and s.get('fields'):
            out.append({'id': str(s['id']), 'fields': [str(f) for f in s['fields']],
                        'what': str(s.get('what') or '')})
    if not out:
        order = load().get('contractOrder') or (
            load().get('renderOrder') or ['summary', 'triggers', 'params', 'hardRules'])
        return [{'id': 'all', 'fields': list(order), 'what': '未分段注册表：整条契约'}]
    return out


def section_ids():
    """合法段 id 列表（含 `all`）—— 报错文案与用例都从这里取，别再手写一份。"""
    return [s['id'] for s in sections()] + ['all']


def render_section(op, section):
    """**单段**渲染（`section` 为段 id；`'all'` == `render_contract`，逐字节等价）。

    未登记的段 → `OpSpecError`（消息里带合法段清单，**不静默回落**：让 AI 知道自己问错了，
    而不是拿到一段它没要的内容）。
    """
    if section == 'all':
        return render_contract(op)
    for s in sections():
        if s['id'] == section:
            return _render_fields(op, s['fields'])
    raise OpSpecError('未登记的段 %r（合法段：%s）' % (section, ' / '.join(section_ids())))


def render_default(op):
    """**默认形态**：`describe` 不传 `section` 时给什么。

    规则（只加不破）：全文 ≤ `budget.contractPerOpMax` 时**逐字节等于 `render_contract`**
    （今天 48/48 都如此，所以默认形态与改动前无差异）；一旦某条 op 涨过上限，就退化为
    「skeleton + 段目录」——**自动软着陆**，不需要人工重排预算。
    """
    full = render_contract(op)
    cap = int((load().get('budget') or {}).get('contractPerOpMax', 900))
    if len(full) <= cap:
        return full
    sk = render_section(op, 'skeleton')
    # 段目录：各段长度**由实测派生**（不手写），让 AI 自己决定下一跳取哪段
    items = ['%s %d' % (s['id'], len(render_section(op, s['id']))) for s in sections()]
    return '%s\n\n分段（args={"section":"段名"}）：%s / all %d' % (sk, ' / '.join(items), len(full))


# --------------------------------------------------------------------------
# 预算与自检（供门禁消费）
# --------------------------------------------------------------------------

def long_ops():
    """长任务 op 清单（`op_spec.json.longOps`）。

    分发器据此决定要不要把这个 op 放工作线程 + 上报进度。放注册表里而不是
    写死在 mcp_server —— 否则「哪些 op 是长任务」又成了第二处口径。
    缺字段回空列表（老注册表也能跑），由 validate 负责提醒。
    """
    return list(load().get('longOps') or [])


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
    drows = [(op, len(render_default(op))) for op in registered()]
    drows.sort(key=lambda r: -r[1])
    srows = []
    for sid in section_ids():
        srows.extend((('%s:%s' % (op, sid)), len(render_section(op, sid))) for op in registered())
    srows.sort(key=lambda r: -r[1])
    return {'per_op': rows, 'total': sum(c for _, c in rows),
            'perOpMax': per_op_max, 'totalMax': total_max,
            'over': [r for r in rows if r[1] > per_op_max],
            'contract_per_op': crows, 'contractPerOpMax': c_max,
            # `contract_over`：**全文**超上限。分层之后它降级为**告警**（不再硬失败）——
            # "全文可以超 900"正是这个机制的目的（超了就默认退化成 skeleton + 段目录）。
            'contract_over': [r for r in crows if r[1] > c_max],
            # 真正的硬判据改为这两条（`tests/test_op_spec.py::test_budget` 消费）：
            #   ① 默认形态（describe 不传 section 时实际给的东西）必须 ≤ 上限；
            #   ② 任何**单段**必须 ≤ 上限（否则"取一段"也超）。
            'default_per_op': drows, 'default_over': [r for r in drows if r[1] > c_max],
            'section_per_op': srows, 'section_over': [r for r in srows if r[1] > c_max],
            'section_ids': section_ids()}


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

        # excludes（出局词）：结构与**自洽性**
        ex = s.get('excludes')
        if ex is not None:
            if not isinstance(ex, dict):
                errs.append('%s: excludes 必须是对象 {why, phrases}' % op)
                continue
            if not str(ex.get('why') or '').strip():
                errs.append('%s: excludes 缺 why（要说清"问法里有这些词时该找谁"）' % op)
            ph = ex.get('phrases')
            if not isinstance(ph, list) or not [x for x in ph if str(x).strip()]:
                errs.append('%s: excludes.phrases 必须是非空字符串数组' % op)
                continue
            tg = set(str(x) for x in (s.get('triggers') or []))
            ov = sorted(set(str(x) for x in ph) & tg)
            if ov:
                # 自相矛盾：同一句既"选它"又"排除它" —— 行为无法解释，必须当场拦
                errs.append('%s: excludes 与自己的 triggers 重叠：%s' % (op, '、'.join(ov)))
            for x in ph:
                if len(str(x).strip()) < 2:
                    errs.append('%s: excludes 片段 %r 太短（会误伤，至少 2 字）' % (op, x))

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

    # 按需面分段：必须是 contractOrder 的**精确划分**（不重排、不新增、不遗漏），
    # 且 skeleton ⊇ renderOrder（三级包含链 常驻 ⊆ skeleton ⊆ 全文 —— 分层不许把常驻面拆散）。
    secs = (tiers.get('onDemand') or {}).get('sections')
    if secs is not None:
        if not isinstance(secs, list) or not secs:
            errs.append('tiers.onDemand.sections 必须是非空数组')
        else:
            ids, flat = [], []
            for s in secs:
                if not isinstance(s, dict) or not str(s.get('id') or '').strip():
                    errs.append('tiers.onDemand.sections 每项必须含 id: %r' % (s,))
                    continue
                if not isinstance(s.get('fields'), list) or not s['fields']:
                    errs.append('段 %s 必须含非空 fields' % s.get('id'))
                    continue
                ids.append(s['id'])
                flat.extend(str(f) for f in s['fields'])
            dup = sorted(set(x for x in ids if ids.count(x) > 1))
            if dup:
                errs.append('段 id 重复：%s' % '、'.join(dup))
            known = set(reg.get('contractOrder') or [])
            unknown = sorted(set(flat) - known)
            if unknown:
                errs.append('段里出现 contractOrder 之外的字段：%s' % '、'.join(unknown))
            missing = sorted(known - set(flat))
            if missing:
                errs.append('有字段没被任何段覆盖（分段必须是精确划分）：%s' % '、'.join(missing))
            twice = sorted(set(x for x in flat if flat.count(x) > 1))
            if twice:
                errs.append('同一字段被多个段覆盖：%s' % '、'.join(twice))
            order = list(reg.get('contractOrder') or [])
            for s in secs:
                flds = [str(f) for f in (s.get('fields') or [])]
                if [f for f in order if f in flds] != [f for f in flds if f in order]:
                    errs.append('段 %s 的字段顺序与 contractOrder 不一致（分段只能划分、不能重排）'
                                % s.get('id'))
            sk = next((s for s in secs if s.get('id') == 'skeleton'), None)
            if sk is None:
                errs.append('缺少 skeleton 段（默认形态退化时给的就是它）')
            elif not set(reg.get('renderOrder') or []) <= set(str(f) for f in sk['fields']):
                errs.append('skeleton 必须覆盖 renderOrder 的全部字段（常驻 ⊆ skeleton ⊆ 全文）')

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

    # longOps：长任务清单必须都是真 op —— 多一个名字 = 分发器永远不生效（静默退化成阻塞调用）
    registered = set(reg['ops'])
    for op in long_ops():
        if op not in registered:
            errs.append('longOps 里的 %r 不是已登记的 op' % op)
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
