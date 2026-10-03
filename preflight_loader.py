"""上机前体检判据的唯一消费入口（域⑨）。

纪律与 `op_spec_loader` / `platform_cap_loader` / `lifecycle_loader` 一致：
- 真源只有 `preflight_spec.json`；**缺失/损坏/查不存在的键一律抛错**，绝不静默退回内嵌副本；
- 渲染只有这里一份实现（`render_doc()` 给 `scripts/gen_preflight_doc.py` 用）；
- 阈值不许在调用方再写一遍（字库那部分与 `components/fonts` 做**跨来源对账**，
  见 `cross_check()`，由门禁调用）。

判据实现（要碰设备/工程的那些）在 `preflight.py`，本模块只管"读规格"。
"""

import io
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(BASE, 'preflight_spec.json')
# 字库档位的实际体积按这个目录算（不把体积抄进真源 —— 抄了就会与文件分叉）
FONT_DIR = os.path.join(BASE, 'components', 'fonts', 'fonts')

_CACHE = {}


class PreflightSpecError(RuntimeError):
    """注册表缺失/损坏/查不到时的显式错误（不静默降级）。"""


def load(force=False):
    """读注册表（带缓存）。缺失或不是合法 JSON 或缺段 → 抛 PreflightSpecError。"""
    if not force and 'spec' in _CACHE:
        return _CACHE['spec']
    if not os.path.isfile(SPEC):
        raise PreflightSpecError('体检规格注册表缺失: %s' % SPEC)
    try:
        with io.open(SPEC, encoding='utf-8') as fh:
            spec = json.loads(fh.read())
    except ValueError as e:
        raise PreflightSpecError('体检规格注册表不是合法 JSON: %s: %s' % (SPEC, e))
    for seg in ('resolution', 'font', 'budget'):
        if not isinstance(spec.get(seg), dict):
            raise PreflightSpecError('体检规格注册表结构异常（缺 %s 段）: %s' % (seg, SPEC))
    _CACHE['spec'] = spec
    return spec


# ───────────────────────────── 分辨率 ─────────────────────────────

def decisions():
    """分辨率三分支判据（顺序即优先级）。"""
    return list(load()['resolution'].get('decisions') or [])


def decision(did):
    """按 id 取分支；查不到抛错（不返回 None，免得调用方忘了判空）。"""
    for d in decisions():
        if d.get('id') == did:
            return d
    raise PreflightSpecError('未登记的分辨率分支: %r（已登记：%s）'
                             % (did, ', '.join(str(d.get('id')) for d in decisions())))


def aspect_tolerance_pct():
    return float(load()['resolution'].get('aspectTolerancePct') or 0)


def adapt_rule(kind):
    """`sameAspect` / `diffAspect` 的处置规则；kind 非法抛错。"""
    a = load()['resolution'].get('adapt') or {}
    if kind not in ('sameAspect', 'diffAspect'):
        raise PreflightSpecError('未知的适配分支: %r（可选 sameAspect / diffAspect）' % kind)
    return dict(a.get(kind) or {})


def adapt_invariants():
    return list((load()['resolution'].get('adapt') or {}).get('invariants') or [])


def rotate_is_same_screen():
    return bool(load()['resolution'].get('rotateIsSameScreen'))


def design_source():
    return dict(load()['resolution'].get('design') or {})


def device_source():
    return dict(load()['resolution'].get('device') or {})


# ───────────────────────────── 字库 ─────────────────────────────

def builtin_font():
    """设备内置字库判据 → {'path','cjkMinKB','rule'}。"""
    return dict(load()['font'].get('builtinFont') or {})


def cjk_min_kb():
    """内置字库体积下限（KB）：小于它 = 不支持中文。"""
    v = builtin_font().get('cjkMinKB')
    if not v:
        raise PreflightSpecError('font.builtinFont.cjkMinKB 缺失')
    return float(v)


def tier_order():
    """档位由小到大（选档时从最小档起试）。"""
    order = list(load()['font'].get('tierOrder') or [])
    if not order:
        raise PreflightSpecError('font.tierOrder 缺失')
    return order


def tiers():
    return dict(load()['font'].get('tiers') or {})


def tier(name):
    t = tiers().get(name)
    if t is None:
        raise PreflightSpecError('未登记的字库档位: %r（已登记：%s）'
                                 % (name, '、'.join(sorted(tiers()))))
    return dict(t)


def tier_file(name):
    return os.path.join(FONT_DIR, tier(name)['file'])


def tier_bytes(name):
    """档位字体的**实际字节数**（读不到回 None —— 不猜、不写死）。"""
    p = tier_file(name)
    try:
        return os.path.getsize(p)
    except OSError:
        return None


def level_match():
    return dict(load()['font'].get('levelMatch') or {})


# ───────────────────────────── 体积预算 ─────────────────────────────

def budget_limit_mb(platform=''):
    """某平台的 /res 体积上限（MB）：perPlatform 覆盖 > 缺省 limitMB。

    platform 走 `platforms.resolve()` 归一再查（别名：F136 == F135），
    查不到或平台为空 → 缺省值。
    """
    b = load()['budget']
    key = ''
    if platform:
        try:
            import platforms as _pl
            key = _pl.resolve(platform).get('canonical') or str(platform)
        except Exception:
            key = str(platform)
    over = (b.get('perPlatform') or {}).get(key)
    if over:
        return float(over)
    v = b.get('limitMB')
    if not v:
        raise PreflightSpecError('budget.limitMB 缺失')
    return float(v)


def budget_near_pct():
    return float(load()['budget'].get('nearPct') or 100)


def budget_parts():
    return list(load()['budget'].get('parts') or [])


def budget_levels():
    return list(load()['budget'].get('levels') or [])


# ───────────────────────────── 跨来源对账 ─────────────────────────────

def cross_check():
    """与实现方对账 → 错误列表（空 = 通过）。由门禁调用。

    对账两件事（任何一处分叉都会让"判定"与"投递"用不同阈值）：
      ① `font.builtinFont.cjkMinKB` == `device_font_check.CJK_SIZE_MIN_KB`
      ② `font.tiers` 的档位键与文件名 == `device_font_check.TIERS`，且字体文件真实存在
    """
    errs = []
    try:
        import font_tools
        dfc, err = font_tools.device_font_check()
    except Exception as e:                                    # 组件脚本缺失 = 对账无法进行
        return ['无法加载 components/fonts/scripts/device_font_check.py：%s: %s'
                % (type(e).__name__, e)]
    if dfc is None:
        return ['device_font_check 不可用：%s' % err]
    theirs = float(getattr(dfc, 'CJK_SIZE_MIN_KB', 0) or 0)
    mine = cjk_min_kb()
    if theirs != mine:
        errs.append('字库体积阈值分叉：preflight_spec.json=%s KB，'
                    'device_font_check.CJK_SIZE_MIN_KB=%s KB' % (mine, theirs))
    dtiers = dict(getattr(dfc, 'TIERS', {}) or {})
    for name in tier_order():
        f = tier(name).get('file')
        if dtiers.get(name) != f:
            errs.append('档位 %s 分叉：spec=%r，device_font_check.TIERS=%r'
                        % (name, f, dtiers.get(name)))
        if not os.path.isfile(tier_file(name)):
            errs.append('档位 %s 的字体文件不存在：%s' % (name, tier_file(name)))
    for name in dtiers:
        if name not in tiers():
            errs.append('device_font_check 有档位 %r 而 spec 未登记' % name)
    return errs


# ───────────────────────────── 渲染（唯一实现）─────────────────────────────

def _kb(n):
    return '—' if n is None else '%.1f KB' % (n / 1024.0)


def render_doc():
    """把注册表渲染成可检索的知识页（markdown）。"""
    spec = load()
    L = []
    L.append('---')
    L.append('id: devflow-device-preflight-spec')
    L.append('title: 上机前体检判据（分辨率适配 / 字库 / res 体积预算，唯一真源派生）')
    L.append('category: devflow')
    L.append('status: review')
    L.append('confidence: manual')
    L.append('verified_at: %s' % (spec.get('updated') or '2026-10-03'))
    L.append('stale_days: 180')
    L.append('origin: derived')
    L.append('source: 由 preflight_spec.json 派生（scripts/gen_preflight_doc.py）；'
             '字库阈值与档位与 components/fonts 跨来源对账')
    L.append('needs_evidence: false')
    L.append('platforms: []')
    # ⚠️ tags 上限 16（kb_local.MAX_TAGS）——只放**检索词**；整句问法走 retrievalHints 渲染的正文
    L.append('tags: [上机前体检, 分辨率适配, 设计分辨率, 面板分辨率, fb0, 等比缩放, 重排布局, '
             '中文字库, fzcircle, 字库档位, res 分区, 体积预算, 打包超限]')
    L.append('evidence:')
    L.append('  - cmd: python scripts/gen_preflight_doc.py --check')
    L.append('    expect: rc=0（本页与 preflight_spec.json 一致，且字库阈值/档位与组件对账通过）')
    L.append('---')
    L.append('# 上机前体检判据（由 preflight_spec.json 派生）')
    L.append('')
    L.append('> ⚙️ **本页是派生物**：内容由 `preflight_spec.json`（唯一真源）经 '
             '`scripts/gen_preflight_doc.py` 生成，**不要手改**（改了下次生成会覆盖，'
             '门禁 `gen_preflight_doc --check` 会红）。')
    hints = spec.get('retrievalHints') or []
    if hints:
        L.append('> 检索导引（**口语问法直达**）：' + ' / '.join(hints) + ' → 本文。')
    L.append('')
    L.append('上机前跑 `flythings_device_preflight`（launch 流程里也会自动跑一遍），'
             '三项体检：**分辨率**、**字库**、**体积**。判据如下。')
    L.append('')

    # 1. 分辨率
    r = spec['resolution']
    L.append('## 1. 分辨率：设计 vs 面板')
    L.append('')
    L.append('- **面板分辨率**（设备侧真值）：%s —— 实现 `%s`。'
             % (r['device'].get('how'), r['device'].get('impl')))
    L.append('- **设计分辨率**（工程侧真值）：%s —— 实现 `%s`。'
             % (r['design'].get('how'), r['design'].get('impl')))
    fb = r['design'].get('fallback') or []
    if fb:
        L.append('- 设计分辨率读不到时的退路（按顺序）：%s' % '；'.join(fb))
    L.append('- 转屏不算不一致：%s' % r.get('rotateIsSameScreen'))
    L.append('- 比例"接近"的容差：相对差 ≤ **%s%%**（超过就按不同比例处理）'
             % r.get('aspectTolerancePct'))
    L.append('')
    L.append('### 1.1 三分支（按顺序命中即停）')
    L.append('')
    L.append('| id | 条件 | 动作 | 级别 | 为什么 |')
    L.append('|---|---|---|---|---|')
    for d in decisions():
        L.append('| `%s` | %s | `%s` | %s | %s |'
                 % (d.get('id'), d.get('when'), d.get('action'),
                    d.get('level'), d.get('why')))
    L.append('')
    L.append('### 1.2 需要适配时怎么改')
    L.append('')
    A = r.get('adapt') or {}
    for kind, label in (('sameAspect', '比例相同或接近'), ('diffAspect', '比例不同')):
        a = A.get(kind) or {}
        L.append('- **%s** → `%s`（%s）' % (label, a.get('action'), a.get('when')))
        L.append('  - 怎么做：%s' % a.get('how'))
        if a.get('skill'):
            L.append('  - 工作流（重排这类需要判断的活）：skill `%s`' % a.get('skill'))
        L.append('  - 工具：`%s`' % a.get('impl'))
    inv = A.get('invariants') or []
    if inv:
        L.append('')
        L.append('**三条不变式**：')
        for x in inv:
            L.append('- %s' % x)
    L.append('')

    # 2. 字库
    f = spec['font']
    bf = f['builtinFont']
    L.append('## 2. 字库：设备认不认中文')
    L.append('')
    L.append('- 系统内置字库：`%s`；**%s**。判定：%s'
             % (bf.get('path'), _kb((bf.get('cjkMinKB') or 0) * 1024), bf.get('rule')))
    if bf.get('impl'):
        L.append('- 实现：`%s`' % bf.get('impl'))
    L.append('- 档位清单与体积的真源：%s' % f.get('tiersSource'))
    L.append('')
    L.append('| 档位 | 文件 | 体积 | 级别 | 什么时候用 |')
    L.append('|---|---|---|---|---|')
    for name in tier_order():
        t = tier(name)
        L.append('| `%s` | `%s` | %s | %s | %s |'
                 % (name, t.get('file'), _kb(tier_bytes(name)), t.get('level'), t.get('when')))
    L.append('')
    lm = f.get('levelMatch') or {}
    L.append('**按工程中文级别选档**：%s' % lm.get('how'))
    L.append('')
    L.append('- 实现：`%s`；投递：`%s`' % (lm.get('impl'), lm.get('deliverImpl')))
    L.append('- %s' % lm.get('noCjk'))
    L.append('')

    # 3. 体积
    b = spec['budget']
    L.append('## 3. 体积：会不会撑爆 /res 分区')
    L.append('')
    L.append('- 上限：**默认 %s MB**（`perPlatform` 可按平台覆盖）；接近阈值 = 用量的 %s%%。'
             % (b.get('limitMB'), b.get('nearPct')))
    L.append('- 计入体积的三部分：')
    for p in budget_parts():
        L.append('  - `%s` —— %s' % (p.get('path'), p.get('what')))
    ex = b.get('excluded') or []
    if ex:
        L.append('- **不计入**（但会在报告里附参考字节数）：%s' % '、'.join('`%s`' % x for x in ex))
    L.append('')
    L.append('| 级别 | 触发 | 动作 | 为什么 |')
    L.append('|---|---|---|---|')
    for lv in budget_levels():
        L.append('| `%s` | %s | `%s` | %s |'
                 % (lv.get('level'), lv.get('when'), lv.get('action'), lv.get('why')))
    if b.get('note'):
        L.append('')
        L.append('> %s' % b['note'])
    L.append('')
    return '\n'.join(L) + '\n'


def doc_path():
    """派生知识页的落点（相对仓库根）。"""
    return 'knowledge/devflow/device-preflight-spec.md'


def validate(include_doc=True):
    """自检 → 错误列表（空 = 通过）。给门禁/用例用。"""
    errs = []
    try:
        load(force=True)
    except PreflightSpecError as e:
        return [str(e)]
    ids = [d.get('id') for d in decisions()]
    if not ids:
        errs.append('resolution.decisions 为空')
    if len(set(ids)) != len(ids):
        errs.append('resolution.decisions 有重复 id')
    for d in decisions():
        for k in ('id', 'when', 'action', 'level', 'why'):
            if not d.get(k):
                errs.append('分辨率分支 %s 缺字段 %s' % (d.get('id'), k))
    acts = {d.get('action') for d in decisions()}
    if not {'push', 'warn', 'adapt_device'} <= acts:
        errs.append('resolution.decisions 缺关键分支（需要 push / warn / adapt_device，实为 %s）'
                    % sorted(acts))
    for kind in ('sameAspect', 'diffAspect'):
        a = adapt_rule(kind)
        for k in ('action', 'when', 'how'):
            if not a.get(k):
                errs.append('adapt.%s 缺字段 %s' % (kind, k))
    if float(load()['resolution'].get('aspectTolerancePct') or 0) <= 0:
        errs.append('resolution.aspectTolerancePct 必须 > 0')
    if not builtin_font().get('path'):
        errs.append('font.builtinFont.path 缺失')
    if cjk_min_kb() <= 0:
        errs.append('font.builtinFont.cjkMinKB 必须 > 0')
    if not tier_order():
        errs.append('font.tierOrder 为空')
    for name in tier_order():
        t = tier(name)
        if not t.get('file'):
            errs.append('档位 %s 缺 file' % name)
        if not t.get('when'):
            errs.append('档位 %s 缺 when' % name)
        if tier_bytes(name) is None:
            errs.append('档位 %s 的字体文件读不到：%s' % (name, tier_file(name)))
    if not level_match().get('how'):
        errs.append('font.levelMatch.how 缺失')
    if float(load()['budget'].get('limitMB') or 0) <= 0:
        errs.append('budget.limitMB 必须 > 0')
    if not (0 < budget_near_pct() <= 100):
        errs.append('budget.nearPct 必须在 (0,100]')
    if not budget_parts():
        errs.append('budget.parts 为空')
    errs.extend(cross_check())
    if include_doc and not os.path.isfile(os.path.join(BASE, doc_path())):
        errs.append('派生知识页不存在：%s（跑 scripts/gen_preflight_doc.py）' % doc_path())
    return errs
