"""生命周期与代码接口契约的唯一消费入口（域②）。

纪律与 `op_spec_loader` / `platform_cap_loader` 一致：
- 真源只有 `lifecycle_spec.json`；**缺失/损坏/查不存在的键一律抛错**，绝不静默退回内嵌副本；
- 渲染只有这里一份实现（`render_doc()` 给 `scripts/gen_lifecycle_doc.py` 用）。

`lifecycle_spec.json` 与 `knowledge/devflow/activity-code-skeleton.md` 的分工：
spec 是**机器可读的规格**（钩子名/签名/导航语义/铁律/控件 API 索引），
md 是**原理与实证过程**（为什么这样、踩过什么）。改规格改 spec，写故事写 md。
"""

import io
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(BASE, 'lifecycle_spec.json')

_CACHE = {}


class LifecycleSpecError(RuntimeError):
    """注册表缺失/损坏/查不到时的显式错误（不静默降级）。"""


def load(force=False):
    """读注册表（带缓存）。缺失或不是合法 JSON → 抛 LifecycleSpecError。"""
    if not force and 'spec' in _CACHE:
        return _CACHE['spec']
    if not os.path.isfile(SPEC):
        raise LifecycleSpecError('生命周期注册表缺失: %s' % SPEC)
    try:
        with io.open(SPEC, encoding='utf-8') as fh:
            spec = json.loads(fh.read())
    except ValueError as e:
        raise LifecycleSpecError('生命周期注册表不是合法 JSON: %s: %s' % (SPEC, e))
    if not isinstance(spec, dict) or 'activity' not in spec:
        raise LifecycleSpecError('生命周期注册表结构异常（缺 activity 段）: %s' % SPEC)
    _CACHE['spec'] = spec
    return spec


def hooks():
    """activity 钩子表（顺序即 onCreate/析构相关顺序，渲染照此）。"""
    return list(load()['activity'].get('hooks') or [])


def hook_names():
    return [h.get('name') for h in hooks()]


def hook(name):
    """按名取钩子；查不到抛错（不返回 None，免得调用方忘了判空）。"""
    for h in hooks():
        if h.get('name') == name:
            return h
    raise LifecycleSpecError('未登记的钩子: %r（已登记：%s）'
                             % (name, ', '.join(str(x) for x in hook_names())))


def navigation():
    return list(load().get('navigation') or [])


def rules():
    return list(load().get('rules') or [])


def rule(rid):
    for r in rules():
        if r.get('id') == rid:
            return r
    raise LifecycleSpecError('未登记的铁律: %r' % rid)


def check_all_gotchas():
    return list(load().get('checkAllGotchas') or [])


def controls():
    """控件 → 关键代码 API 索引（详情在 knowledge/uicontrols/widget-code-api.md）。"""
    return dict(load().get('controls') or {})


def control(name):
    c = controls().get(name)
    if c is None:
        raise LifecycleSpecError('未登记的控件: %r（已登记：%s）'
                                 % (name, '、'.join(sorted(controls()))))
    return c


def timer_table():
    return dict(load()['activity'].get('timerTable') or {})


def sequences():
    a = load()['activity']
    return list(a.get('onCreateSequence') or []), list(a.get('onDestroySequence') or [])


# ───────────────────────────── 渲染（唯一实现）─────────────────────────────

def render_doc():
    """把注册表渲染成可检索的知识页（markdown）。"""
    spec = load()
    L = []
    L.append('---')
    L.append('id: devflow-activity-lifecycle-spec')
    L.append('title: 生命周期与代码接口契约（钩子/导航语义/铁律/控件 API 索引，唯一真源派生）')
    L.append('category: devflow')
    L.append('status: review')
    L.append('confidence: manual')
    L.append('verified_at: %s' % (spec.get('updated') or '2026-10-02'))
    L.append('stale_days: 180')
    L.append('origin: derived')
    L.append('source: 由 lifecycle_spec.json 派生（scripts/gen_lifecycle_doc.py）；'
             '钩子集合与 templates/HelloWord_*/src/logic/mainLogic.cc **交叉核对**')
    L.append('needs_evidence: false')
    L.append('platforms: []')
    # ⚠️ tags 上限 16（kb_local.MAX_TAGS）——只放**检索词**；口语问法由 retrievalHints 承担
    #（那些整句已渲染进正文的「常见问法」节），别往 tags 里塞，超限会被知识库门禁判 FAIL。
    L.append('tags: [生命周期, onUI_init, onUI_show, onUI_hide, onUI_quit, onUI_Timer, '
             '回调触发, 资源释放放哪, 导航矩阵, goBack, openActivity, 隐藏页定时器, '
             '空闲超时, 按钮回调返回值, 控件 API, ZKListView 三回调]')
    L.append('evidence:')
    L.append('  - cmd: python scripts/gen_lifecycle_doc.py --check')
    L.append('    expect: rc=0（本页与 lifecycle_spec.json 一致，且注册表钩子 == 模板骨架钩子）')
    L.append('---')
    L.append('# FlyThings 生命周期与代码接口契约（由 lifecycle_spec.json 派生）')
    L.append('')
    L.append('> ⚙️ **本页是派生物**：内容由 `lifecycle_spec.json`（唯一真源）经 '
             '`scripts/gen_lifecycle_doc.py` 生成，**不要手改**（改了下次生成会覆盖，'
             '门禁 `gen_lifecycle_doc --check` 会红）。')
    L.append('> 原理与实证过程见 `knowledge/devflow/activity-code-skeleton.md`；'
             '控件逐个的代码接口详解见 `knowledge/uicontrols/widget-code-api.md`。')
    hints = spec.get('retrievalHints') or []
    if hints:
        L.append('> 检索导引（**口语问法直达**）：' + ' / '.join(hints) + ' → 本文。')
    L.append('')
    L.append('## 1. 骨架与钩子')
    L.append('')
    L.append(spec['activity'].get('entry') or '')
    L.append('')
    L.append('**onCreate 标准序列**：')
    L.append('')
    for i, s in enumerate(spec['activity'].get('onCreateSequence') or [], 1):
        L.append('%d. %s' % (i, s))
    L.append('')
    L.append('**析构对称序列**：')
    L.append('')
    for i, s in enumerate(spec['activity'].get('onDestroySequence') or [], 1):
        L.append('%d. %s' % (i, s))
    L.append('')
    tt = timer_table()
    if tt:
        L.append('**定时器表 `%s`**：`%s`' % (tt.get('name'), tt.get('sig')))
        L.append('')
        L.append('- 必须：%s' % tt.get('must'))
        L.append('- ⚠️ %s' % tt.get('pitfall'))
        L.append('')
    L.append('| 钩子 | 签名 | 何时触发 | 必须做什么 | ⚠️ 坑 |')
    L.append('|---|---|---|---|---|')
    for h in hooks():
        L.append('| `%s` | `%s` | %s | %s | %s |'
                 % (h.get('name'), h.get('sig'), h.get('when'),
                    h.get('must'), h.get('pitfall')))
    L.append('')
    L.append('## 2. 导航 × 回调触发矩阵（释放逻辑放哪？）')
    L.append('')
    L.append('| 导航事件 | 触发的回调 | 说明 |')
    L.append('|---|---|---|')
    for n in navigation():
        L.append('| %s | %s | %s |'
                 % (n.get('event'),
                    ' / '.join('`%s`' % c for c in (n.get('callbacks') or [])),
                    n.get('why')))
    L.append('')
    L.append('## 3. 铁律')
    L.append('')
    for r in rules():
        L.append('- **%s** %s' % (r.get('id'), r.get('rule')))
        L.append('  - 为什么：%s' % r.get('why'))
        L.append('  - 实证：%s' % r.get('evidence'))
    L.append('')
    L.append('## 4. `check_all` 的两个字符级扫描口径（书写前先知道，免得白查）')
    L.append('')
    for g in check_all_gotchas():
        L.append('- **%s**（%s）：%s' % (g.get('item'), g.get('kind'), g.get('gotcha')))
        L.append('  - 做法：%s' % g.get('advice'))
    L.append('')
    L.append('## 5. 控件代码 API 索引')
    L.append('')
    L.append('> 只列**关键方法名**（够查够用）；逐个控件的完整讲解、参数口径与实测坑见 '
             '`knowledge/uicontrols/widget-code-api.md`。')
    L.append('')
    L.append('| 控件 | Demo | 关键 API | ⚠️ 坑 |')
    L.append('|---|---|---|---|')
    for name in sorted(controls()):
        c = controls()[name]
        L.append('| `%s` | %s | %s | %s |'
                 % (name, c.get('demo'),
                    '、'.join('`%s`' % a for a in (c.get('api') or [])),
                    c.get('pitfall')))
    L.append('')
    return '\n'.join(L) + '\n'


def doc_path():
    """派生知识页的落点（相对仓库根）。"""
    return 'knowledge/devflow/activity-lifecycle-spec.md'


def validate():
    """自检 → 错误列表（空 = 通过）。给门禁/用例用。"""
    errs = []
    spec = load(force=True)
    names = hook_names()
    if not names:
        errs.append('hooks 为空')
    if len(set(names)) != len(names):
        errs.append('hooks 有重名')
    for h in hooks():
        for k in ('name', 'sig', 'when', 'must', 'pitfall'):
            if not h.get(k):
                errs.append('钩子 %s 缺字段 %s' % (h.get('name'), k))
    if not navigation():
        errs.append('navigation 为空')
    if not rules():
        errs.append('rules 为空')
    ids = [r.get('id') for r in rules()]
    if len(set(ids)) != len(ids):
        errs.append('rules 有重复 id')
    if not controls():
        errs.append('controls 为空')
    for name, c in controls().items():
        if not (c.get('api') or []):
            errs.append('控件 %s 没登记 api' % name)
        if not c.get('demo'):
            errs.append('控件 %s 没登记 demo' % name)
    if not (spec.get('activity') or {}).get('onCreateSequence'):
        errs.append('activity.onCreateSequence 为空')
    return errs
