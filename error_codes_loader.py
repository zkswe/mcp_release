# -*- coding: utf-8 -*-
"""错误码表的唯一消费入口（域⑫）。

纪律与其它域一致：真源只有 `error_codes.json`；缺失/损坏/查不到 → 抛错，不静默退回内嵌表。

两个消费方：
- `kb_tools.normalize_result()` 用它给 `error` 补 `action` 与默认 `retryable`
  —— 所以**调用点只写 code + msg**，处置建议不必在每个构造点各写一遍；
- `flythings://errors` 资源（给 AI 一张全表）。

`scan_source()` / `validate()` 做**跨来源对账**：源码里出现的码必须已登记，
登记的码必须真的有人抛（孤儿码 = 要么写错、要么该删），`raisedBy` 指的文件必须存在。
"""
import io
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(BASE, 'error_codes.json')

_CACHE = {}

# 源码里 code 字面量的写法（错误体的每个构造入口都要在这里 —— 漏一个入口，
# 那个入口抛的码就会「看起来没人抛」，对账就会误判成孤儿）
_PATTERNS = (
    re.compile(r"_err_obj\(\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    re.compile(r"_env_err\(\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    re.compile(r"_err_json\(\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    re.compile(r"['\"]code['\"]\s*:\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
)
# 扫源码找错误码时的跳过目录：构建产物目录**两代都跳**（09-28 起 `.fun/` 改名 `.fsc/`；
# 本扫描只看 .py，所以影响面小，但口径要与全仓一致 —— 别只认一代）。
_SKIP_DIRS = {'.git', '.fsc', '.fun', 'node_modules', '__pycache__', 'Release', '.workbuddy',
              'tests', 'knowledge', 'demos', 'templates', 'components', 'bin_tools'}


class ErrorCodeError(RuntimeError):
    """错误码表缺失/损坏/查不到时的显式错误（不静默降级）。"""


def load(force=False):
    if not force and 'spec' in _CACHE:
        return _CACHE['spec']
    if not os.path.isfile(SPEC):
        raise ErrorCodeError('错误码表缺失: %s' % SPEC)
    try:
        with io.open(SPEC, encoding='utf-8') as fh:
            spec = json.loads(fh.read())
    except ValueError as e:
        raise ErrorCodeError('错误码表不是合法 JSON: %s: %s' % (SPEC, e))
    if not isinstance(spec.get('codes'), dict):
        raise ErrorCodeError('错误码表结构异常（缺 codes 段）: %s' % SPEC)
    _CACHE['spec'] = spec
    return spec


def codes():
    return dict(load()['codes'])


def code(name):
    """按名取码；查不到（或表不可用）返回 None（**不抛** —— 错误路径上不该再抛错）。

    调用点可以写一个还没登记的码（比如新加的），这时 enrich() 只原样放过。
    这种「漏登记」由 validate() 在门禁上抓，不在运行时炸 —— 失败返回本身**必须**能出去。
    """
    try:
        return codes().get(name)
    except ErrorCodeError:
        return None


def describe(name):
    c = code(name)
    return dict(c) if c else {}


def enrich(err):
    """给一个 error 对象补 `action` / 默认 `retryable`（就地改并返回；查不到的码原样放过）。

    只补**缺的**：调用点显式写的 retryable 优先于表里的默认值。
    """
    if not isinstance(err, dict):
        return err
    c = code(err.get('code') or '')
    if not c:
        return err
    # ⚠️ 用 `is None` 判「未表态」，不能用 falsy —— `retryable=False` 是**明确的否决**
    # （「这次别重试」），被表里的默认值翻成 True 就丢了调用点的判断。
    if err.get('retryable') is None and c.get('retryable') is not None:
        err['retryable'] = c['retryable']
    if not err.get('action') and c.get('action'):
        err['action'] = c['action']
    if not err.get('who') and c.get('who'):
        err['who'] = c['who']
    return err


# ───────────────────────── 跨来源对账 ─────────────────────────

def scan_source(unreadable=None):
    """扫源码里出现的 code 字面量 → {code: {相对路径}}。

    `unreadable` 传一个 list 时，读不了的文件会记进去（**不静默跳过** —— 少扫一个文件
    可能让「漏登记」被漏报，对账就假绿了）。
    """
    found = {}
    for dirpath, dirnames, filenames in os.walk(BASE):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith('.py') or fn.startswith('test_'):
                continue
            p = os.path.join(dirpath, fn)
            try:
                with io.open(p, encoding='utf-8') as fh:
                    text = fh.read()
            except OSError as e:
                if unreadable is not None:
                    unreadable.append('%s（%s: %s）'
                                      % (os.path.relpath(p, BASE).replace(os.sep, '/'),
                                         type(e).__name__, e))
                continue
            rel = os.path.relpath(p, BASE).replace(os.sep, '/')
            for pat in _PATTERNS:
                for m in pat.finditer(text):
                    found.setdefault(m.group(1), set()).add(rel)
    return found


def validate():
    """自检 + 对账 → 错误列表（空 = 通过）。给门禁/用例用。"""
    errs = []
    try:
        load(force=True)
    except ErrorCodeError as e:
        return [str(e)]
    known = codes()
    for name, c in known.items():
        for k in ('meaning', 'who', 'action'):
            if not c.get(k):
                errs.append('错误码 %s 缺字段 %s' % (name, k))
        if c.get('who') not in ('caller', 'env', 'device', 'bug'):
            errs.append('错误码 %s 的 who=%r 不在 caller/env/device/bug'
                        % (name, c.get('who')))
        if 'retryable' not in c:
            errs.append('错误码 %s 缺 retryable 默认值' % name)
        for f in (c.get('raisedBy') or []):
            if not os.path.isfile(os.path.join(BASE, f)):
                errs.append('错误码 %s 的 raisedBy 指向不存在的文件：%s' % (name, f))
    unreadable = []
    found = scan_source(unreadable)
    for f in unreadable:
        errs.append('对账扫不到的源文件（会让漏登记被漏报）：%s' % f)
    for name in sorted(set(found) - set(known)):
        errs.append('源码里出现的错误码未登记：%s（%s）'
                    % (name, '、'.join(sorted(found[name]))))
    for name in sorted(set(known) - set(found)):
        if known[name].get('framework'):
            continue        # 框架兜底码：由 fallback 产生，不该在源码里被找到
        errs.append('错误码 %s 登记了但源码里没人抛（孤儿）' % name)
    return errs


# ───────────────────────── 渲染（给资源用）─────────────────────────

WHO_CN = {'caller': '改调用（AI 自己能修）', 'env': '改环境/工程（用户能修）',
          'device': '设备侧（没连/型号不符）', 'bug': '本仓缺陷（报官方）'}


def render_table():
    """整张码表（markdown，给 `flythings://errors` 资源）。"""
    spec = load()
    L = ['# FlyThings MCP 错误码表（由 error_codes.json 派生）', '',
         '> 所有 op 失败一律返回 `{ok:false, op, error:{code,msg,hint,retryable,action}, warnings[]}`。',
         '> 本表是 `code` 的语义；`action` 与默认 `retryable` 会被自动补进每次失败的返回里 ——',
         '> 所以**多数情况不用查这张表，直接读返回体的 error.action 即可**。', '']
    L.append('| code | 什么意思 | 该谁动手 | 可重试 | 下一步 |')
    L.append('|---|---|---|---|---|')
    for name, c in codes().items():
        L.append('| `%s` | %s | %s | %s | %s |'
                 % (name, c.get('meaning'), WHO_CN.get(c.get('who'), c.get('who')),
                    '是' if c.get('retryable') else '否', c.get('action')))
    L.append('')
    return '\n'.join(L) + '\n'
