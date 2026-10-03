# -*- coding: utf-8 -*-
"""工程状态（跨会话「做到哪了」）的唯一实现。

真源分工（这是本模块存在的理由 —— 状态位**不是**在这里新定的）：
- **状态位定义** = `flow_spec.json` 的 `stateSlots`（域⑩ 流程真源）；本模块只读它，不另立一份。
  所以「哪个 op 成功后该打哪个状态位」是从流程注册表**反查**出来的，不是手写映射表。
- **状态实例** = `<项目>/.flythings/state.json`（每工程一份；运行时数据，不是知识真源，不入库）。
- **最近工程表** = `~/.flythings/projects.json`（给「新会话不记得路径」兜底）。

为什么需要：以前 AI 判断进度只能**反向读工程文件**猜（有没有 ui/*.json、ftu 比 json 新不新…），
换个会话就得重新摸一遍；闸门（比如「设计稿确认了没」）更是完全无处可查。
"""
import io
import json
import os
import time

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_REL = os.path.join('.flythings', 'state.json')


def registry_path():
    """最近工程表的位置（`FLYTHINGS_STATE_HOME` 可覆盖 —— 测试与非默认家目录用）。"""
    home = (os.environ.get('FLYTHINGS_STATE_HOME')
            or os.path.join(os.path.expanduser('~'), '.flythings'))
    return os.path.join(home, 'projects.json')


class ProjectStateError(RuntimeError):
    """状态文件损坏 / 工程不可解析时的显式错误（不静默当空）。"""


# ───────────────────────── 状态位定义（来自流程真源）─────────────────────────

def _flows_loader():
    import flow_loader
    return flow_loader


def slots():
    """状态位定义（`flow_spec.json.stateSlots.slots`）→ {name: {...}}。"""
    return _flows_loader().state_slots()


def slot(name):
    s = slots().get(name)
    if s is None:
        raise ProjectStateError('未登记的状态位: %r（已登记：%s）'
                                % (name, '、'.join(sorted(slots()))))
    return dict(s)


def slots_of_op(op_name):
    """反查：这个 op 成功后该打哪些状态位。

    路径：`flow_spec.steps[*].op == op_name` 且该步骤声明了 `setsState`。
    —— 所以「自动回写」不需要在代码里再维护一张 op→状态位 的表。
    """
    out = []
    for sid, s in _flows_loader().steps().items():
        if s.get('op') == op_name:
            for name in (s.get('setsState') or []):
                if name not in out:
                    out.append(name)
    return out


def step_of_slot(name):
    """状态位由哪一步写入 → step id（不在流程里 → None）。"""
    return slot(name).get('setBy')


# ───────────────────────── 实例读写 ─────────────────────────

def state_file(root):
    return os.path.join(os.path.abspath(root), STATE_REL)


def load(root):
    """读工程状态 → {'slots': {...}, 'updated': ...}；文件不存在回空壳（不是错误）。"""
    p = state_file(root)
    if not os.path.isfile(p):
        return {'slots': {}, 'updated': ''}
    try:
        with io.open(p, encoding='utf-8') as fh:
            data = json.loads(fh.read())
    except (OSError, ValueError) as e:
        raise ProjectStateError('状态文件损坏（%s）：%s: %s' % (p, type(e).__name__, e))
    if not isinstance(data, dict):
        raise ProjectStateError('状态文件结构异常（应是对象）：%s' % p)
    data.setdefault('slots', {})
    data.setdefault('updated', '')
    return data


def save(root, data):
    p = state_file(root)
    d = os.path.dirname(p)
    if not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    data['updated'] = _now()
    with io.open(p, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    return p


def _now():
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())


def mark(root, name, note='', source=''):
    """打一个状态位（幂等；重复打只更新时间与 note）。返回写入的状态位名。"""
    slot(name)                                   # 未登记的状态位直接抛错，不静默写进去
    data = load(root)
    data['slots'][name] = {'at': _now(), 'note': note, 'source': source}
    save(root, data)
    touch(root)
    return name


def unmark(root, name):
    data = load(root)
    if name in data['slots']:
        del data['slots'][name]
        save(root, data)
        return True
    return False


def reset(root):
    """清空全部状态位（**不可逆**，只在用户明确要求重来时用）。"""
    save(root, {'slots': {}})
    return True


# ───────────────────────── 最近工程表（跨会话兜底）─────────────────────────

def _read_registry():
    REGISTRY = registry_path()
    if not os.path.isfile(REGISTRY):
        return []
    try:
        with io.open(REGISTRY, encoding='utf-8') as fh:
            data = json.loads(fh.read())
    except (OSError, ValueError):
        return []                                 # 注册表损坏 → 当空；调用方本就有别的手段拿路径
    return data if isinstance(data, list) else []


def touch(root):
    """把工程记进最近表（没有则插，有则更新时间并挪到最前）。"""
    root = os.path.abspath(root)
    rows = [r for r in _read_registry() if isinstance(r, dict) and r.get('root') != root]
    rows.insert(0, {'root': root, 'name': os.path.basename(root.rstrip('/\\')),
                    'at': _now()})
    d = os.path.dirname(registry_path())
    if not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    with io.open(registry_path(), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(json.dumps(rows[:20], ensure_ascii=False, indent=2) + '\n')
    return root


def recent(limit=5):
    """最近活动过的工程（最新在前）。

    顺手剔除**已经不在磁盘上**的（临时目录、删掉的工程）—— 否则新会话第一眼就看到
    一堆死路径，还以为是有效状态。
    """
    rows = [r for r in _read_registry() if os.path.isdir(r.get('root') or '')]
    return rows[:max(1, int(limit))]


def resolve(root=''):
    """project_root 为空 → 取最近活动的那个（没有则空串）。"""
    if root:
        return os.path.abspath(root)
    rows = recent(1)
    return rows[0]['root'] if rows else ''


# ───────────────────────── 进度视图 ─────────────────────────

def show(root=''):
    """把一个工程的进度摊平 → 给 AI 看「做到哪、下一步做什么、闸门过没过」。

    含 `next`：按流程步骤顺序找出**第一个还没打上的状态位**，把它 setBy 那一步
    报成「下一步」—— 状态位与步骤的对应关系全部来自流程真源。
    """
    root = resolve(root)
    if not root:
        return {'projectRoot': '', 'exists': False, 'recent': recent(),
                'hint': '没有活动工程记录：传 project_root，或先建工程（flythings_create_project）'}
    if not os.path.isdir(root):
        raise ProjectStateError('工程目录不存在：%s' % root)
    st = load(root)
    done_names = set(st['slots'])
    defs = slots()
    steps = _flows_loader().steps()

    done = []
    for name, rec in st['slots'].items():
        d = defs.get(name)
        done.append({'slot': name,
                     'meaning': (d or {}).get('meaning') or '（注册表里删了这个状态位）',
                     'at': rec.get('at'), 'note': rec.get('note') or '',
                     'source': rec.get('source') or ''})
    done.sort(key=lambda x: x.get('at') or '')

    # **隐含完成**：流程是顺序的 —— 后面那步都做了，前面那步必然做过。
    # 例：已打 projectCreated 却没打 paramsDecided（用户没逐个 mark），
    # 这时说「下一步：定平台/分辨率」是错的。规则 = 位置最靠后的已打槽位，它之前的一律视为已过。
    order = _step_order()

    def _pos(name):
        return order.get((defs.get(name) or {}).get('setBy'), 10 ** 6)

    marked_max = max([_pos(n) for n in done_names if n in defs] or [-1])
    effective = set(done_names)
    implicit = []
    for name in defs:
        if name not in done_names and _pos(name) <= marked_max:
            effective.add(name)
            implicit.append(name)

    pending = []
    for name, d in defs.items():
        if name in effective:
            continue
        sid = d.get('setBy')
        s = steps.get(sid) or {}
        pending.append({'slot': name, 'meaning': d.get('meaning') or '',
                        'step': sid, 'stepTitle': s.get('title') or sid,
                        'op': s.get('op') or '', 'blocks': d.get('blocks') or ''})

    # 下一步 = 按步骤在各流程里的最早出现位置排序
    pending.sort(key=lambda x: order.get(x.get('step'), 10 ** 6))
    nxt = pending[0] if pending else None
    if nxt:
        s = steps.get(nxt['step']) or {}
        nxt['gate'] = s.get('gate') or ''
        nxt['gateHow'] = s.get('gateHow') or ''
        nxt['how'] = (s.get('how') or [])[:1]

    return {'projectRoot': root, 'exists': True,
            'stateFile': state_file(root), 'updated': st.get('updated') or '',
            'done': done, 'implicit': implicit, 'pending': pending, 'next': nxt,
            'invariantsPending': _flow_invariants()}


def _step_order():
    """步骤的**规范次序**：按流程先后 + 步骤先后取首次出现的位置。

    `flow_spec.json` 的 flows 顺序有意把场景轴放前面（idea-to-app 覆盖主链），
    所以 `setdefault` 留下的就是主链次序；收尾步骤也一并编号。
    """
    order = {}
    for fid in _flows_loader().flows():
        seq = [it for it in _flows_loader().flow_items(fid)]
        seq += [{'id': sid} for sid in
                ((_flows_loader().flow(fid).get('wrapUp') or {}).get('steps') or [])]
        for i, item in enumerate(seq):
            order.setdefault(item['id'], i)
    return order


def _flow_invariants():
    """跨流程铁律（去重后）—— 状态视图里附上，省得 AI 再拉一次契约。"""
    inv = _flows_loader().invariants()
    return [{'id': k, 'rule': v.get('rule')} for k, v in inv.items()]


# ───────────────────────── 自动回写 ─────────────────────────

def auto_mark(op_name, kwargs, result_obj):
    """dispatcher 层调用：某个 op 成功后就地打它声明的状态位。

    - 只认**成功**（result.ok 为真）——失败不打，否则「跑过」会被当成「做成了」；
    - 工程路径从调用参数里取（`project_root` / `path` 的父目录）；
    - 任何异常都不许影响主流程，但要**如实回报**（由调用方收进 warnings）。
    返回 (已打的槽位列表, 错误说明或 '')。
    """
    try:
        if not isinstance(result_obj, dict) or not result_obj.get('ok'):
            return [], ''
        targets = slots_of_op(op_name)
        if not targets:
            return [], ''
        root = _root_from_kwargs(kwargs)
        if not root or not os.path.isdir(root):
            return [], ''
        done = []
        for name in targets:
            mark(root, name, source=op_name)
            done.append(name)
        return done, ''
    except Exception as e:                        # 状态是附加价值，不许拖垮主流程
        return [], '%s: %s' % (type(e).__name__, e)


def _root_from_kwargs(kwargs):
    """从调用参数猜工程根：优先 project_root，其次 path 往上找含 ui/ 或 .settings/ 的目录。"""
    if not isinstance(kwargs, dict):
        return ''
    root = kwargs.get('project_root') or kwargs.get('root') or ''
    if root and os.path.isdir(root):
        return os.path.abspath(root)
    p = kwargs.get('path') or ''
    if p:
        d = os.path.dirname(os.path.abspath(p))
        for _ in range(4):
            if os.path.isdir(os.path.join(d, 'ui')) or os.path.isdir(os.path.join(d, '.settings')):
                return d
            nd = os.path.dirname(d)
            if nd == d:
                break
            d = nd
    return ''
