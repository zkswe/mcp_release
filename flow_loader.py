"""「开发流程」的唯一消费入口（域⑩）。

纪律与 `op_spec_loader` / `preflight_loader` / `platform_cap_loader` 一致：
- 真源只有 `flow_spec.json`；**缺失/损坏/查不存在的键一律抛错**，绝不静默退回内嵌副本；
- 渲染只有这里一份实现 —— 场景流程 → `render_skill()`（给 `scripts/gen_flow_skills.py`），
  动作流程 → `render_prompt()`（给 `mcp_extras.py` 运行时用），全部 → `render_doc()`。

两条正交轴（这是本域存在的理由）：
- `kind=scenario` = 用户**带着什么进来**（只有想法 / 有稿子 / 从别框架搬 / 改已有 / 分辨率不合）
- `kind=action`   = 用户**要做哪件事**（新建 / 原型转 UI / 验收 / 部署 / 依赖）
两者穿过**同一批 `steps` 原子** —— 所以步骤正文只写一份，两条轴各自引用。

`cross_check()` 与 op 契约对账（步骤引用的 op 必须存在；声明了闸门的步骤，
其 op 契约里必须有铁律 —— 否则闸门只活在流程页里，AI 不拉契约就丢了）。
"""

import io
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(BASE, 'flow_spec.json')

_CACHE = {}

GATE_CN = {
    'precondition': '前置条件',
    'user-confirm': '需用户确认',
    'irreversible': '不可逆操作',
}

# `step.verify` 的三个必填键：**通过判据 / 不通过判据 / 怎么验证**。
# 为什么要有它（2026-10-04）：流程步骤此前只有 `how`（怎么做）与 `gate`（什么时候不许做），
# **没有"做完了算不算过"** —— 于是 AI 只能凭感觉说"好了"，用户也拿不到可核对的判据。
# 口径与 DESIGN_SPEC 一致：只写判据（ok/notOk/evidence），不写故事。
VERIFY_FIELDS = ('ok', 'notOk', 'evidence')


class FlowSpecError(RuntimeError):
    """注册表缺失/损坏/查不到时的显式错误（不静默降级）。"""


def load(force=False):
    """读注册表（带缓存）。缺失或不是合法 JSON 或缺段 → 抛 FlowSpecError。"""
    if not force and 'spec' in _CACHE:
        return _CACHE['spec']
    if not os.path.isfile(SPEC):
        raise FlowSpecError('流程注册表缺失: %s' % SPEC)
    try:
        with io.open(SPEC, encoding='utf-8') as fh:
            spec = json.loads(fh.read())
    except ValueError as e:
        raise FlowSpecError('流程注册表不是合法 JSON: %s: %s' % (SPEC, e))
    for seg in ('steps', 'flows', 'invariants', 'stateSlots'):
        if not isinstance(spec.get(seg), dict):
            raise FlowSpecError('流程注册表结构异常（缺 %s 段）: %s' % (seg, SPEC))
    _CACHE['spec'] = spec
    return spec


# ───────────────────────────── 取数 ─────────────────────────────

def steps():
    return dict(load()['steps'])


def step(sid):
    s = steps().get(sid)
    if s is None:
        raise FlowSpecError('未登记的步骤: %r（已登记：%s）'
                            % (sid, '、'.join(sorted(steps()))))
    return dict(s)


def step_verify(sid):
    """步骤的**验收判据** → {'ok','notOk','evidence'}。

    独立成函数（而不是让调用方 `s.get('verify')`）：注册表里"哪些 step 该有 verify"
    由 `validate()` 保证，消费方拿到的一定是三字段齐全的对象 —— 缺了就在这里抛错，
    不要静默退回空串（那样渲染出来是"✅ 通过： ｜ ⛔ 不通过： "，比不渲染更误导）。
    """
    s = step(sid)
    v = s.get('verify')
    if not isinstance(v, dict):
        raise FlowSpecError('步骤 %s 缺 verify（验收判据）：%s' % (sid, SPEC))
    miss = [f for f in VERIFY_FIELDS if not str(v.get(f) or '').strip()]
    if miss:
        raise FlowSpecError('步骤 %s 的 verify 缺 %s' % (sid, '、'.join(miss)))
    return {f: v[f] for f in VERIFY_FIELDS}


def verify_line(sid):
    """一行式验收判据（给 skill / 派生页用）。"""
    v = step_verify(sid)
    return '✅ %s ｜ ⛔ %s ｜ 证据：%s' % (v['ok'], v['notOk'], v['evidence'])


def flows():
    """全部流程（scenario / action 两条轴）。"""
    return dict(load()['flows'])


def flows_of(kind):
    """按 kind 取流程（scenario / action）；kind 非法抛错。"""
    if kind not in ('scenario', 'action'):
        raise FlowSpecError('未知的流程类型: %r（可选 scenario / action）' % kind)
    return {k: dict(v) for k, v in flows().items() if v.get('kind') == kind}


def flow(fid):
    f = flows().get(fid)
    if f is None:
        raise FlowSpecError('未登记的流程: %r（已登记：%s）'
                            % (fid, '、'.join(sorted(flows()))))
    return dict(f)


def invariants():
    return dict(load()['invariants'])


def invariant(iid):
    v = invariants().get(iid)
    if v is None:
        raise FlowSpecError('未登记的不变量: %r（已登记：%s）'
                            % (iid, '、'.join(sorted(invariants()))))
    return dict(v)


def state_slots():
    return dict(load()['stateSlots'].get('slots') or {})


def safety():
    return load().get('safety') or ''


def retrieval_hints():
    return list(load().get('retrievalHints') or [])


# ───────────────────────────── 步骤项（带编号）─────────────────────────────

_STEP_NO = re.compile(r'第\s*(\d+)\s*步')


def flow_items(fid):
    """流程的有序步骤 → [{'label','id','title','step'}]。

    编号规则：标签里带「第 N 步」的就以它为准（并让后续自动续号），
    没给标签的自动 +1 —— 这样「第 0 步」开头、或「第 2 步 A / 第 2 步 B」二选一
    这类原稿写法都能原样还原。
    """
    f = flow(fid)
    out = []
    counter = 0
    for it in f.get('steps') or []:
        if isinstance(it, str):
            item = {'id': it}
        elif isinstance(it, dict):
            item = dict(it)
        else:
            raise FlowSpecError('流程 %s 的步骤项必须是字符串或对象：%r' % (fid, it))
        sid = item.get('id')
        if not sid:
            raise FlowSpecError('流程 %s 有步骤项缺 id：%r' % (fid, it))
        s = step(sid)
        label = item.get('label') or ''
        m = _STEP_NO.match(label)
        if m:
            counter = int(m.group(1))
        else:
            counter += 1
            label = '第 %d 步' % counter
        out.append({'label': label, 'id': sid,
                    'title': item.get('title') or s.get('title') or sid,
                    'step': s})
    return out


# ───────────────────────────── 渲染：动作流程 → prompt ─────────────────────────────

def render_prompt(fid):
    """动作流程 → {'title','description','args','body'}（`mcp_extras.PROMPTS` 的形状）。

    ⚠️ **`how` 全部渲染**（2026-10-05 起）：此前只渲染 `how[0]`，于是「桩生成完，再往
    `src/logic/*.cc` 里填业务」这类**关键下一步**写在 `how[1]` 就永远进不了常驻面 ——
    AI 只按 prompt 走时看不到「还要写页面逻辑」，交付就停在空桩上。
    """
    f = flow(fid)
    if f.get('kind') != 'action':
        raise FlowSpecError('流程 %s 的 kind=%r 不是 action，不能渲染成 prompt'
                            % (fid, f.get('kind')))
    lines = [f.get('oneLine') or '']
    for i, item in enumerate(flow_items(fid), 1):
        s = item['step']
        op = s.get('op')
        seg = '%d. ' % i
        seg += ('`%s`（%s）' % (op, item['title'])) if op else item['title']
        if s.get('gate') and s.get('gateHow'):
            seg += ' —— ⚠️ %s' % s['gateHow']
        lines.append(seg)
        for h in (s.get('how') or []):
            lines.append('   - %s' % h)
    for n in (f.get('notes') or []):
        lines.append('- %s' % n)
    body = '\n\n'.join(['\n'.join(lines[:1]) + '\n\n' + '\n'.join(lines[1:]), safety()]).strip()
    return {'title': f.get('title') or fid,
            'description': f.get('desc') or '',
            'args': list(f.get('inputs') or []),
            'body': body}


# ───────────────────────────── 渲染：场景流程 → SKILL.md ─────────────────────────────

def render_skill(fid):
    """场景流程 → 一份完整的 SKILL.md（含 front-matter）。"""
    f = flow(fid)
    if f.get('kind') != 'scenario':
        raise FlowSpecError('流程 %s 的 kind=%r 不是 scenario，不能渲染成 skill'
                            % (fid, f.get('kind')))
    name = f.get('skillName')
    if not name:
        raise FlowSpecError('场景流程 %s 缺 skillName' % fid)
    L = ['---', 'name: %s' % name, 'description: %s' % (f.get('desc') or ''),
         'agent_created: true', '---', '']
    label = f.get('label') or ''
    L.append('# FlyThings · %s %s' % (label, f.get('title') or fid) if label
             else '# FlyThings · %s' % (f.get('title') or fid))
    L.append('')
    L.append('## 何时用')
    for a in (f.get('audience') or []):
        L.append('- %s' % a)
    if f.get('routing'):
        L.append('- %s' % f['routing'])
    L.append('')

    for item in flow_items(fid):
        L.append('## %s：%s' % (item['label'], item['title']))
        s = item['step']
        for h in (s.get('how') or []):
            L.append(h)
        for g in (s.get('gotchas') or []):
            L.append('- %s' % g)
        if s.get('gate'):
            L.append('- ⚠️ **%s**：%s' % (GATE_CN.get(s['gate'], s['gate']),
                                         s.get('gateHow') or '必须满足后再继续'))
        L.append('- **验收判据**：%s' % verify_line(item['id']))
        if s.get('docRef'):
            L.append('- 细节：`%s`' % s['docRef'])
        L.append('')

    wu = f.get('wrapUp') or {}
    if wu.get('steps'):
        L.append('## %s' % (wu.get('title') or '收尾'))
        for sid in wu['steps']:
            s = step(sid)
            op = s.get('op')
            L.append('- %s%s' % ((('`%s`' % op) + ' —— ') if op else '',
                                 s.get('title') or sid))
        L.append('')

    chk = f.get('checks') or {}
    if chk.get('items'):
        L.append('## %s' % (chk.get('title') or '常见落差（照这个顺序查）'))
        for i, x in enumerate(chk['items'], 1):
            L.append('%d. %s' % (i, x))
        L.append('')

    invs = f.get('invariants') or []
    if invs:
        L.append('## 铁律速查')
        for i, iid in enumerate(invs, 1):
            L.append('%d. %s' % (i, invariant(iid).get('rule')))
        L.append('')
    return '\n'.join(L).rstrip('\n') + '\n'


# ───────────────────────────── 渲染：派生知识页 ─────────────────────────────

def render_doc():
    """全部流程摊成可检索的一页（`knowledge/devflow/flow-index.md`）。"""
    spec = load()
    L = ['---', 'id: devflow-flow-index',
         'title: 开发流程索引（场景 × 动作两条轴，由 flow_spec.json 派生）',
         'category: devflow', 'status: review', 'confidence: manual',
         'verified_at: %s' % (spec.get('updated') or '2026-10-03'),
         'stale_days: 180', 'origin: derived',
         'source: 由 flow_spec.json 派生（scripts/gen_flow_doc.py）',
         'needs_evidence: false', 'platforms: []',
         'tags: [开发流程, 场景, 从零做界面, 设计稿转界面, 框架迁移, 改已有工程, 分辨率适配, '
         '编译部署, UI 验收, 依赖包, 步骤顺序, 铁律]',
         'evidence:',
         '  - cmd: python scripts/gen_flow_doc.py --check',
         '    expect: rc=0（本页与 flow_spec.json 一致）',
         '---',
         '# 开发流程索引（由 flow_spec.json 派生）', '',
         '> ⚙️ **本页是派生物，不要手改**（由 `flow_spec.json` 派生，`--check` 进闸门）。']
    hints = retrieval_hints()
    if hints:
        L.append('> 口语问法直达：' + ' / '.join(hints) + '。')
    L.append('')
    L.append('「该走哪条流程」有两个入口：**按场景**（用户带了什么来）和**按动作**（要做哪件事）。'
             '两条轴穿过同一批步骤 —— 所以下面步骤库里的一段，几条流程都会引用。')
    L.append('')

    L.append('## 1. 场景轴（用户带着什么进来）')
    L.append('')
    for fid, f in flows_of('scenario').items():
        L.append('### %s %s' % (f.get('label') or '', f.get('title')))
        L.append('')
        L.append('- **什么时候用**：%s' % (f.get('when') or f.get('desc') or ''))
        L.append('- **走哪些步**：%s' % ' → '.join(item['title'] for item in flow_items(fid)))
        L.append('- **口语触发**：%s' % (' / '.join(f.get('triggers') or []) or '—'))
        L.append('- **做完的标志**：%s' % (f.get('exit') or '—'))
        L.append('')

    L.append('## 2. 动作轴（要做哪件事）')
    L.append('')
    L.append('| 动作 | 走哪些步 | 口语触发 |')
    L.append('|---|---|---|')
    for fid, f in flows_of('action').items():
        path = ' → '.join(item['title'] for item in flow_items(fid))
        L.append('| **%s** | %s | %s |'
                 % (f.get('title'), path, ' / '.join(f.get('triggers') or []) or '—'))
    L.append('')

    L.append('## 3. 步骤库（两条轴共用）')
    L.append('')
    L.append('| 步骤 | 主要 op | 闸门 | 做什么 | 通过判据 |')
    L.append('|---|---|---|---|---|')
    for sid, s in steps().items():
        gate = GATE_CN.get(s['gate'], s['gate']) if s.get('gate') else '—'
        L.append('| %s | %s | %s | %s | %s |'
                 % (s.get('title') or sid,
                    ('`%s`' % s['op']) if s.get('op') else '（人判断）',
                    gate, (s.get('how') or [''])[0],
                    (s.get('verify') or {}).get('ok') or '—'))
    L.append('')

    L.append('## 4. 验收判据（每步「做完了算不算过」；`verify` 真源在 flow_spec.json）')
    L.append('')
    L.append('| 步骤 | ✅ 通过 | ⛔ 不通过（继续会返工/出错） | 证据 / 怎么验 |')
    L.append('|---|---|---|---|')
    for sid, s in steps().items():
        v = s.get('verify') or {}
        L.append('| %s | %s | %s | %s |'
                 % (s.get('title') or sid, v.get('ok') or '—', v.get('notOk') or '—',
                    v.get('evidence') or '—'))
    L.append('')

    L.append('## 5. 跨流程铁律（去重后只此一份）')
    L.append('')
    L.append('| 不变量 | 规则 | 违反的后果 |')
    L.append('|---|---|---|')
    for iid, v in invariants().items():
        L.append('| `%s` | %s | %s |' % (iid, v.get('rule'), v.get('why')))
    L.append('')

    sv = spec['stateSlots']
    L.append('## 6. 工程状态位（跨会话「做到哪了」）')
    L.append('')
    L.append('| 状态位 | 由哪步写入 | 挡住哪步 | 含义 |')
    L.append('|---|---|---|---|')
    for name, v in state_slots().items():
        L.append('| `%s` | %s | %s | %s |'
                 % (name, v.get('setBy'), v.get('blocks') or '—', v.get('meaning')))
    L.append('')
    return '\n'.join(L) + '\n'


def doc_path():
    """派生知识页的落点（相对仓库根）。"""
    return 'knowledge/devflow/flow-index.md'


# ───────────────────────────── 与 op 契约对账 ─────────────────────────────

_CALL_RE = re.compile(r'`(flythings_[a-z_]+)\(([^`]*)\)`')
_KW_RE = re.compile(r'([a-z_][a-z0-9_]*)\s*=')


def _signatures():
    """op 名 → 参数名集合，**从 kb_tools.py 源码 AST 取**（不导入 kb_tools：那会连带加载检索栈，
    让门禁慢一大截）。取不到就返回空字典，由调用方跳过该条检查。
    """
    import ast
    path = os.path.join(BASE, 'kb_tools.py')
    try:
        with io.open(path, encoding='utf-8') as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError):
        return {}
    out = {}
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name.startswith('flythings_'):
            out[n.name] = [a.arg for a in n.args.args if a.arg not in ('self', 'ctx')]
    return out


def _check_calls(text, where, errs, known, sigs):
    """文档里写的 op 调用，参数名必须与**真实签名**一致。

    为什么值得查：`fui_pack` 的真实签名是 `json_path`，而流程页写的是 `project_root=`
    —— AI 照文档调用会拿 BAD_PARAMS，而文档看起来"很权威"。这类错人眼扫不出来
    （名字都合理），只有跟签名对账才现形。
    """
    if not text or not sigs:
        return
    for op, args in _CALL_RE.findall(text):
        if op not in known or op not in sigs:
            continue
        for kw in _KW_RE.findall(args):
            if kw not in sigs[op]:
                errs.append('%s：写成 `%s(%s=…)`，但真实签名是 `%s(%s)`'
                            % (where, op, kw, op, ', '.join(sigs[op]) or '无参数'))


def cross_check():
    """与 `op_spec.json` / `kb_tools` 真实签名对账 → 错误列表（空 = 通过）。由门禁调用。

    三件事：
      ① 步骤引用的 op 必须存在（op 改名后流程会静默跑偏）
      ② 声明了闸门的步骤，其 op 契约里必须有铁律 —— 否则闸门只活在流程页里，
         AI 不主动拉契约就看不到（上一轮 `create_project` 的「设计先行」正是这类）
      ③ 文档里写的调用**参数名**必须与真实签名一致（AI 照文档调错参数 = 白跑一轮）
    """
    errs = []
    try:
        import op_spec_loader as osl
        known = set(osl.registered())
    except Exception as e:
        return ['无法加载 op_spec_loader：%s: %s' % (type(e).__name__, e)]
    for sid, s in steps().items():
        op = s.get('op')
        if not op:
            continue
        if op not in known:
            errs.append('步骤 %s 引用的 op 未登记：%s' % (sid, op))
            continue
        if s.get('gate'):
            sp = osl.spec(op)
            if not (sp.get('hardRules') or sp.get('rules')):
                errs.append('步骤 %s 声明了闸门（%s），但 op %s 的契约里没有任何铁律'
                            '（hardRules/rules）—— 闸门在常驻面不可见'
                            % (sid, s['gate'], op))
    sigs = _signatures()
    for sid, s in steps().items():
        for line in (s.get('how') or []) + (s.get('gotchas') or []):
            _check_calls(line, '步骤 %s' % sid, errs, known, sigs)
    for fid, f in flows().items():
        for key in ('desc', 'oneLine', 'routing', 'exit'):
            _check_calls(f.get(key), '流程 %s 的 %s' % (fid, key), errs, known, sigs)
    return errs


# ───────────────────────────── 自检 ─────────────────────────────

def validate(include_doc=True):
    """自检 → 错误列表（空 = 通过）。给门禁/用例用。"""
    errs = []
    try:
        load(force=True)
    except FlowSpecError as e:
        return [str(e)]

    # 步骤
    for sid, s in steps().items():
        for k in ('title', 'how'):
            if not s.get(k):
                errs.append('步骤 %s 缺字段 %s' % (sid, k))
        if s.get('gate'):
            if s['gate'] not in GATE_CN:
                errs.append('步骤 %s 的 gate=%r 不在 %s'
                            % (sid, s['gate'], '、'.join(sorted(GATE_CN))))
            if not s.get('gateHow'):
                errs.append('步骤 %s 声明了闸门却没写 gateHow（闸门没法过 = 没闸门）' % sid)
        # verify（验收判据）：**31 个 step 必须都有**，且三字段齐全。
        # 为什么要求全覆盖而不是"可选"：流程的每一步都要能回答"做完了算不算过"——
        # 可选就意味着有人会跳过，而跳过的那些恰恰是 AI 最容易含糊过去的步骤。
        v = s.get('verify')
        if not isinstance(v, dict):
            errs.append('步骤 %s 缺 verify（验收判据：ok/notOk/evidence）' % sid)
        else:
            for f in VERIFY_FIELDS:
                if not str(v.get(f) or '').strip():
                    errs.append('步骤 %s 的 verify 缺 %s' % (sid, f))
            for f in v:
                if f not in VERIFY_FIELDS:
                    errs.append('步骤 %s 的 verify 多了字段 %r（只许 %s）'
                                % (sid, f, '/'.join(VERIFY_FIELDS)))

    # 流程
    for fid, f in flows().items():
        kind = f.get('kind')
        if kind not in ('scenario', 'action'):
            errs.append('流程 %s 的 kind=%r 必须是 scenario / action' % (fid, kind))
            continue
        if kind == 'scenario':
            if not f.get('skillName'):
                errs.append('场景流程 %s 缺 skillName' % fid)
            if not f.get('when'):
                errs.append('场景流程 %s 缺 when（派生页的短句；缺了会把长 desc 灌进索引页）' % fid)
        if kind == 'action':
            if not f.get('promptName'):
                errs.append('动作流程 %s 缺 promptName' % fid)
            if not f.get('inputs'):
                errs.append('动作流程 %s 的 inputs 为空（prompt 参数表会没有参数）' % fid)
            # oneLine 里的占位符必须都在 inputs 里 —— 否则 prompt body 的 .format() 会抛
            # KeyError（或静默留个 {x} 在正文里），两者都比"当场报错"难查
            ph = set(re.findall(r'\{(\w+)\}', f.get('oneLine') or ''))
            miss = ph - set(f.get('inputs') or [])
            if miss:
                errs.append('动作流程 %s 的 oneLine 有未声明为 inputs 的占位符：%s'
                            % (fid, '、'.join(sorted(miss))))
        if not f.get('steps'):
            errs.append('流程 %s 没有步骤' % fid)
        if not f.get('triggers'):
            errs.append('流程 %s 缺 triggers（分级筛选靠它）' % fid)
        if not f.get('desc'):
            errs.append('流程 %s 缺 desc（skill 的 front-matter description 靠它）' % fid)
    # 引用完整性（不靠 flow_items 抛错来发现 —— 一次性把所有悬空引用报出来）
    for fid, f in flows().items():
        for it in (f.get('steps') or []):
            sid = it if isinstance(it, str) else (it or {}).get('id')
            if sid not in steps():
                errs.append('流程 %s 引用了不存在的步骤 %r' % (fid, sid))
        for it in ((f.get('wrapUp') or {}).get('steps') or []):
            if it not in steps():
                errs.append('流程 %s 的收尾引用了不存在的步骤 %r' % (fid, it))
        for iid in (f.get('invariants') or []):
            if iid not in invariants():
                errs.append('流程 %s 引用了不存在的不变量 %r' % (fid, iid))

    # 孤儿：写了没人用 = 要么漏引用、要么该删
    used_steps = set()
    used_inv = set()
    for f in flows().values():
        for it in (f.get('steps') or []):
            used_steps.add(it if isinstance(it, str) else (it or {}).get('id'))
        for it in ((f.get('wrapUp') or {}).get('steps') or []):
            used_steps.add(it)
        used_inv.update(f.get('invariants') or [])
    for sid in steps():
        if sid not in used_steps:
            errs.append('步骤 %s 没有被任何流程引用（孤儿）' % sid)
    for iid in invariants():
        if iid not in used_inv:
            errs.append('不变量 %s 没有被任何流程引用（孤儿）' % iid)

    # 状态位
    for name, v in state_slots().items():
        for k in ('setBy', 'meaning'):
            if not v.get(k):
                errs.append('状态位 %s 缺字段 %s' % (name, k))
        if v.get('setBy') and v['setBy'] not in steps():
            errs.append('状态位 %s 的 setBy 指向不存在的步骤 %r' % (name, v['setBy']))
        if v.get('blocks') and v['blocks'] not in steps():
            errs.append('状态位 %s 的 blocks 指向不存在的步骤 %r' % (name, v['blocks']))

    errs.extend(cross_check())
    if include_doc and not os.path.isfile(os.path.join(BASE, doc_path())):
        errs.append('派生知识页不存在：%s（跑 scripts/gen_flow_doc.py）' % doc_path())
    return errs
