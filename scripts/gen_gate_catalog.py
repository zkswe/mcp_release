# -*- coding: utf-8 -*-
"""重新生成意图闸门 catalog.json（单一来源 = kb_tools.py 的函数与签名）。

背景（v0.27.31）：catalog.json 原先是手工/临时脚本产物，工具名与参数一改就漂移。
本脚本用 AST 离线生成（不导入 kb_tools，无需 mcp/onnx 依赖），并支持 --check 做漂移检测。
流程阶段 stage（design/build/other）与 brief、args 一样都是**派生**：stage ← op_spec.json 的
stage 字段，brief ← 该 op 的 docstring 首行（= 注册表 summary），args ← 函数签名。
（v0.27.174 前 stage 是从 gen_manifest.py 的 STAGE 表 AST 爬出来的，那是第二份事实来源，已收编。）

用法（在 MCP 根目录或任意位置）：
    python scripts/gen_gate_catalog.py            # 写入 ../flythings_intent_gate/catalog.json
    python scripts/gen_gate_catalog.py --check    # 只比对，不一致退出码 1（smoke.py 用）
    python scripts/gen_gate_catalog.py --out X    # 指定输出路径
"""
import argparse
import ast
import io
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(os.path.dirname(BASE), 'flythings_intent_gate', 'catalog.json')


def read_stage():
    """从 op 契约注册表读出 {op: stage}（唯一真源 = op_spec.json）。

    v0.27.174 起 stage 不再手工维护在 gen_manifest.py 里（那是第二份事实来源），
    本函数改为直接问注册表；未登记的 op 由调用方按「漏登记」报错。
    """
    if BASE not in sys.path:
        sys.path.insert(0, BASE)
    import op_spec_loader as _osl
    return {op: str(_osl.stage(op) or '') for op in _osl.registered()}


def collect():
    """按 kb_tools.OP_NAMES 收集 op + 首行简介 + 参数名（单一来源）。

    v0.27.32 起 register_all 改为遍历 OP_NAMES（不再逐行 mcp.tool()(...)），
    所以清单从 OP_NAMES 常量读，且会校验「清单 vs 模块内 flythings_* 函数定义」一致。
    """
    src = io.open(os.path.join(BASE, 'kb_tools.py'), encoding='utf-8').read()
    tree = ast.parse(src)
    registered = set()
    for n in tree.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == 'OP_NAMES':
                    registered = {e.value for e in n.value.elts}
    if not registered:
        raise SystemExit('kb_tools.OP_NAMES not found (generator relies on it as single source)')
    defined = {n.name for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name.startswith('flythings_')
               and n.name != 'flythings_kb'}
    missing = sorted(registered - defined)
    extra = sorted(defined - registered)
    if missing or extra:
        raise SystemExit('OP_NAMES vs 函数定义不一致  missing=%s extra=%s' % (missing, extra))
    STAGE = read_stage()
    unregistered = sorted(registered - set(STAGE))
    if unregistered:
        raise SystemExit('op_spec.json 未登记 stage 的 op：%s' % unregistered)
    bad = sorted(v for v in STAGE.values() if v not in ('design', 'build', 'other'))
    if bad:
        raise SystemExit('gen_manifest.STAGE 取值非法（只能 design/build/other）：%s' % bad)
    ops = []
    for n in tree.body:
        if not isinstance(n, ast.FunctionDef) or n.name not in registered:
            continue
        doc = (ast.get_docstring(n) or '').strip().splitlines()
        brief = (doc[0] if doc else '')[:90]
        args = [a.arg for a in n.args.args if a.arg not in ('ctx', 'self')]
        ops.append({'op': n.name, 'brief': brief, 'args': args,
                    'stage': STAGE.get(n.name, 'other')})
    ops.sort(key=lambda o: o['op'])
    return {'count': len(ops), 'ops': ops}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--check', action='store_true', help='只比对，不写入')
    a = ap.parse_args()
    want = collect()
    if a.check:
        if not os.path.isfile(a.out):
            print('[FAIL] catalog.json missing: %s' % a.out)
            return 1
        cur = json.load(io.open(a.out, encoding='utf-8'))
        cw = {o['op']: o for o in want['ops']}
        cc = {o['op']: o for o in cur.get('ops', [])}
        diffs = []
        for op in sorted(set(cw) | set(cc)):
            if op not in cc:
                diffs.append('missing op: %s' % op)
            elif op not in cw:
                diffs.append('stale op: %s' % op)
            else:
                if cw[op]['args'] != cc[op]['args']:
                    diffs.append('args drift %s: %s -> %s' % (op, cc[op]['args'], cw[op]['args']))
                if cw[op]['brief'] != cc[op]['brief']:
                    diffs.append('brief drift %s' % op)
                if cw[op].get('stage') != cc[op].get('stage'):
                    diffs.append('stage drift %s: %s -> %s'
                                 % (op, cc[op].get('stage'), cw[op].get('stage')))
        if diffs:
            print('[FAIL] gate catalog out of sync (%d):' % len(diffs))
            for d in diffs:
                print('   ' + d)
            print('   fix: python scripts/gen_gate_catalog.py')
            return 1
        print('[PASS] gate catalog in sync (%d ops)' % len(want['ops']))
        return 0
    io.open(a.out, 'w', encoding='utf-8').write(
        json.dumps(want, ensure_ascii=False, indent=2) + '\n')
    print('catalog -> %s (%d ops)' % (a.out, want['count']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
