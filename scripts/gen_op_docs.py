# -*- coding: utf-8 -*-
"""从 op 契约注册表（op_spec.json）生成 kb_tools.py 里各 op 的 docstring。

为什么（回应「不要靠人工打磨散文压预算，要从源头设计标准化」）：
  kb_tools.py 的 docstring 就是 MCP 工具 description——它既承载「契约」（参数/返回/铁律）
  又承载「叙述」，于是被 12000 字符硬预算逼着手工逐字删，每次加 op 都要重来一遍。
  现在契约结构化进了 op_spec.json，docstring 降级为**派生产物**：
  预算 = 渲染产物的字符数，可以精确度量；要压就改注册表的结构化字段（或删冗余字段），
  而不是去打磨散文。

派生成什么形状：summary 首行 + 空行 + 各块（触发别名 / flow / 参数 / 返回 / ⚠️ 铁律 /
检索词 / 细节指针），版式由注册表 renderOrder 决定，渲染实现只有 op_spec_loader.render 一份。

用法：
    python scripts/gen_op_docs.py                 # 写回 kb_tools.py（仅已登记的 op）
    python scripts/gen_op_docs.py --check         # 只比对漂移（未登记 op 仅提示）
    python scripts/gen_op_docs.py --check --strict# 未登记 op 也当失败（迁移完成后收紧）
    python scripts/gen_op_docs.py --show          # 打印全部已登记 op 的渲染结果（人工审阅用）
    python scripts/gen_op_docs.py --report        # 只报预算
"""
import argparse
import ast
import io
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import op_spec_loader as osl                     # noqa: E402

KB = os.path.join(BASE, 'kb_tools.py')
INDENT = ' ' * 4


def _ops_in_source():
    """kb_tools.py 里所有 op 函数名（与门禁同一口径：flythings_* 去掉分发器 + flythings_kb）。"""
    tree = ast.parse(io.open(KB, encoding='utf-8').read())
    names = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name.startswith('flythings_') \
                and n.name != 'flythings_kb':
            names.append(n.name)
        elif isinstance(n, ast.AsyncFunctionDef) and n.name == 'flythings_kb':
            names.append(n.name)
    return names


def _docstring_spans(src):
    """{op: (L1,C1,L2,C2)}（ast 的偏移是 UTF-8 字节偏移，见 docstring 里 KB_SLIM_NOTE）。"""
    tree = ast.parse(src)
    out = {}
    for n in tree.body:
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not (n.name == 'flythings_kb' or n.name.startswith('flythings_')):
            continue
        for b in n.body:
            if (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant)
                    and isinstance(b.value.value, str)):
                d = b.value
                out[n.name] = (d.lineno, d.col_offset, d.end_lineno, d.end_col_offset)
                break
    return out


def _iter_lines_with_offsets(raw):
    """按字节累积各行的起始偏移（UTF-8 字节，含行尾）。"""
    acc = [0]
    for ln in raw.splitlines(keepends=True):
        acc.append(acc[-1] + len(ln))
    return acc


def _render_literal(text, eol):
    """渲染成 docstring 字面量：首行与引号同行，续行补 4 空格缩进。"""
    body = [ln for ln in text.split('\n')]
    out = '"""' + body[0] + '\n'
    for ln in body[1:]:
        out += (INDENT + ln if ln.strip() else '') + '\n'
    out += INDENT + '"""'
    return out.replace('\n', eol)


def _current_docstrings(src):
    """{op: 实际 docstring 文本}（inspect.cleandoc 口径，与 ast.get_docstring 一致）。"""
    tree = ast.parse(src)
    out = {}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if n.name == 'flythings_kb' or n.name.startswith('flythings_'):
                out[n.name] = ast.get_docstring(n) or ''
    return out


def collect():
    """返回 (drift, unregistered, brief_drift)。

    drift         : [(op, 现状字符, 渲染字符)]  —— docstring 与注册表渲染不同
    unregistered  : 源码里存在但注册表未登记的 op
    brief_drift   : [(op, 现首行, 注册表 summary)] —— 首行变了（会影响派生 brief）
    """
    src = io.open(KB, encoding='utf-8').read()
    cur = _current_docstrings(src)
    reg = set(osl.registered())
    drift, brief_drift = [], []
    for op in osl.registered():
        if op not in cur:
            continue
        want = osl.render(op)
        have = cur[op].strip()
        if have != want:
            drift.append((op, len(have), len(want)))
        have_first = have.splitlines()[0] if have else ''
        want_first = want.splitlines()[0] if want else ''
        if have_first != want_first:
            brief_drift.append((op, have_first, want_first))
    unregistered = [n for n in _ops_in_source() if n not in reg]
    return drift, unregistered, brief_drift


def report():
    rep = osl.budget_report()
    print('已登记 op：%d' % len(osl.registered()))
    for op, c in rep['per_op']:
        flag = '  ← 超单条上限 %d' % rep['perOpMax'] if c > rep['perOpMax'] else ''
        print('  %-38s %4d%s' % (op, c, flag))
    print('已登记 op 渲染合计 %d 字符（总上限 %d）' % (rep['total'], rep['totalMax']))
    drifts, unregistered, briefs = collect()
    print('docstring 漂移（需重生成）：%d 条%s'
          % (len(drifts), '' if not drifts else ' ' + str([d[0] for d in drifts])))
    print('未登记进注册表的 op：%d 个（迁移中，仍是手写 docstring）' % len(unregistered))
    return rep, unregistered


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='只比对，不写入（漂移即退出码 1）')
    ap.add_argument('--apply', action='store_true', help='写回 kb_tools.py（默认动作，显式写出亦可）')
    ap.add_argument('--strict', action='store_true', help='--check 时把「未登记 op」也当失败')
    ap.add_argument('--show', action='store_true', help='打印已登记 op 的渲染结果')
    ap.add_argument('--report', action='store_true', help='只打印预算与漂移报告')
    a = ap.parse_args()

    errs = osl.validate()
    if errs:
        print('[FAIL] op_spec.json 自检不通过：')
        for e in errs:
            print('  - %s' % e)
        return 1

    if a.show:
        for op in osl.registered():
            print('=' * 72)
            print('## %s   [%s/%s/%s]  %d chars'
                  % (op, osl.risk(op), osl.category(op), osl.stage(op), len(osl.render(op))))
            print('-' * 72)
            print(osl.render(op))
        return 0

    if a.report or a.check:
        rep, unregistered = report()

    if not a.check and not a.report:
        return apply_all()

    if a.check:
        drifts, unregistered, briefs = collect()
        if briefs:
            print('[WARN] 首行将变化（需连带重生成 tools_manifest.json / gate_catalog.json）：')
            for op, old, new in briefs:
                print('  - %s\n      现: %s\n      新: %s' % (op, old, new))
        if drifts:
            print('[FAIL] docstring 与 op_spec.json 漂移：%s'
                  % ', '.join('%s(%d→%d)' % d for d in drifts))
            return 1
        if a.strict and unregistered:
            print('[FAIL] 未登记进 op_spec.json 的 op：%s' % ', '.join(unregistered))
            return 1
        if unregistered:
            print('[PASS] 已登记 op 的 docstring 与注册表一致（未登记 %d 个，迁移中）'
                  % len(unregistered))
        else:
            print('[PASS] 全部 %d 个 op 的 docstring 与注册表一致' % len(osl.registered()))
        if rep['over']:
            print('[FAIL] 单条渲染超 %d 字符：%s' % (rep['perOpMax'], rep['over']))
            return 1
    return 0


def apply_all():
    """把已登记 op 的 docstring 重写为注册表渲染结果（字节偏移安全，保留原行尾）。"""
    raw = io.open(KB, 'rb').read()
    eol = '\r\n' if b'\r\n' in raw else '\n'
    src = raw.decode('utf-8')
    spans = _docstring_spans(src)
    acc = _iter_lines_with_offsets(raw)

    edits = []
    for op in osl.registered():
        if op not in spans:
            print('[WARN] %s 在 kb_tools.py 里找不到，跳过' % op)
            continue
        L1, C1, L2, C2 = spans[op]
        edits.append((L1, C1, L2, C2, _render_literal(osl.render(op), eol), op))

    edits.sort(key=lambda e: (e[0], e[1]), reverse=True)
    out = raw
    for L1, C1, L2, C2, seg, op in edits:
        off1 = acc[L1 - 1] + C1
        off2 = acc[L2 - 1] + C2
        out = out[:off1] + seg.encode('utf-8') + out[off2:]

    if out == raw:
        print('[PASS] kb_tools.py 无需改动（已与注册表一致）')
        return 0
    io.open(KB, 'wb').write(out)
    print('updated: %s（重写 %d 个 op 的 docstring）' % (KB, len(edits)))
    print('⚠️ 首行若变化，请连带重生成：'
          'python scripts/gen_manifest.py && python scripts/gen_gate_catalog.py')
    return 0


if __name__ == '__main__':
    sys.exit(main())
