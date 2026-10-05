# -*- coding: utf-8 -*-
"""T4.1：renderContract 覆盖声明 —— 数据文件 + 校验器（`--check`）。

为什么要它（REMEDIATION §WS-4）：`ui_schema.json#renderContract` 是「视觉保真的唯一口径表」（10 条），
但**谁实现哪条、哪条没人实现**此前只散在注释里（`ui_tools/*.py` 头部写一句"本文件实现 xxx"）——
机器不可验，改代码也不会红。本文件把它变成**数据**：每条 row 在某实现里是
`implements / partial / delegated / not-applicable`，且 `implements|partial` 必须给出**代码事实锚点**
（该文件里真实存在的函数/常量名，AST 校验）——函数被删/改名 → 门禁当场红。

`json2img` 不在这里重复声明：它有更细的独立矩阵（`ui_tools/json2img_coverage.json`，含
implemented/approximate/unsupported + blindSpot），本文件只登记"它的真源在哪"，并校验两边行集合一致。
"""
import ast
import io
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(BASE, 'ui_tools', 'render_contract_coverage.json')

STATUSES = ('implements', 'partial', 'delegated', 'not-applicable')


def load():
    with io.open(SPEC, encoding='utf-8') as f:
        return json.load(f)


def contract_rows():
    """renderContract 的 10 条 row id（唯一真源 = ui_schema.json）。"""
    sys.path.insert(0, os.path.join(BASE, 'ui_tools'))
    import ui_schema_loader as us
    rows = (us.load().get('renderContract') or {}).get('rows') or []
    return [r.get('id') for r in rows]


def _symbols(path):
    """文件里定义/赋值的顶层名字（函数、类、常量）——AST，不执行代码。"""
    try:
        tree = ast.parse(io.open(path, encoding='utf-8').read())
    except (OSError, SyntaxError):
        return None
    out = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
    return out


def check():
    """返回问题列表（空 = 通过）。"""
    errs = []
    try:
        data = load()
    except (OSError, ValueError) as e:
        return ['覆盖声明读不了：%s: %s' % (type(e).__name__, e)]
    rows = contract_rows()
    if not rows:
        return ['renderContract.rows 取不到（ui_schema.json 结构变了？）']
    impls = data.get('implementations') or {}
    if not impls:
        return ['覆盖声明缺 implementations 段']
    seen_any = set()
    for rel, spec in sorted(impls.items()):
        p = os.path.join(BASE, rel.replace('/', os.sep))
        if not os.path.isfile(p):
            errs.append('声明里的实现文件不存在：%s' % rel)
            continue
        if spec.get('matrix'):
            mp = os.path.join(BASE, str(spec['matrix']).replace('/', os.sep))
            if not os.path.isfile(mp):
                errs.append('%s 的矩阵文件不存在：%s' % (rel, spec['matrix']))
                continue
            try:
                with io.open(mp, encoding='utf-8') as f:
                    md = json.load(f)
            except ValueError as e:
                errs.append('%s 的矩阵不是合法 JSON：%s' % (rel, e))
                continue
            mrows = [r.get('id') for r in (md.get('rows') or [])]
            if sorted(mrows) != sorted(rows):
                errs.append('%s 的矩阵行集合与 renderContract 不一致（缺 %s / 多 %s）'
                            % (rel, sorted(set(rows) - set(mrows)), sorted(set(mrows) - set(rows))))
            seen_any.update(mrows)
            continue
        syms = _symbols(p)
        if syms is None:
            errs.append('%s 读不了（AST 解析失败）' % rel)
            continue
        declared = spec.get('rows') or {}
        missing = sorted(set(rows) - set(declared))
        extra = sorted(set(declared) - set(rows))
        if missing:
            errs.append('%s 未声明这些 row：%s' % (rel, missing))
        if extra:
            errs.append('%s 声明了 renderContract 里没有的 row：%s' % (rel, extra))
        for rid, ent in sorted(declared.items()):
            st = ent.get('status')
            if st not in STATUSES:
                errs.append('%s/%s 的 status=%r 非法（合法：%s）' % (rel, rid, st, '/'.join(STATUSES)))
                continue
            seen_any.add(rid)
            if st in ('implements', 'partial'):
                ev = ent.get('evidence') or []
                if not ev:
                    errs.append('%s/%s 声明 %s，但没有 evidence（代码事实锚点）' % (rel, rid, st))
                for name in ev:
                    if name not in syms:
                        errs.append('%s/%s 的 evidence %r 在该文件里不存在（函数/常量被删或改名？）'
                                    % (rel, rid, name))
            if st in ('delegated', 'not-applicable') and not ent.get('note'):
                errs.append('%s/%s 是 %s，必须写 note 说明归谁/为什么' % (rel, rid, st))
    unseen = sorted(set(rows) - seen_any)
    if unseen:
        errs.append('这些 row 没有任何实现声明（谁管？）：%s' % unseen)
    return errs


def main():
    argv = sys.argv[1:]
    errs = check()
    print('renderContract 覆盖声明（真源 = ui_tools/render_contract_coverage.json；'
          'row 集合真源 = ui_schema.json#renderContract.rows）')
    try:
        data = load()
        for rel, spec in sorted((data.get('implementations') or {}).items()):
            if spec.get('matrix'):
                print('  %-28s → 独立矩阵 %s' % (rel, spec['matrix']))
                continue
            rows = spec.get('rows') or {}
            cnt = {}
            for ent in rows.values():
                cnt[ent.get('status')] = cnt.get(ent.get('status'), 0) + 1
            print('  %-28s %s' % (rel, ' '.join('%s=%d' % kv for kv in sorted(cnt.items()))))
    except (OSError, ValueError) as e:
        # **不静默**（DESIGN_SPEC 第 3 条）：统计打不出来要说清原因，别让人以为"声明是空的"
        print('  （逐文件统计打不出来：%s: %s —— 明细见上面的 [FAIL] 列表）'
              % (type(e).__name__, e))
        errs = list(errs) + ['覆盖声明读不了（统计阶段）：%s: %s' % (type(e).__name__, e)]
    if errs:
        print('[FAIL] renderContract 覆盖声明 %d 项：' % len(errs))
        for e in errs[:12]:
            print('   ' + e)
        return 1
    if '--check' in argv:
        print('[PASS] 覆盖声明与 10 条 row 一一对应，且 evidence 锚点都在代码里')
    return 0


if __name__ == '__main__':
    sys.exit(main())
