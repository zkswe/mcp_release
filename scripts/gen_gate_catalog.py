# -*- coding: utf-8 -*-
"""重新生成意图闸门 catalog.json（单一来源 = kb_tools.py 的函数与签名）。

背景（v0.27.31）：catalog.json 原先是手工/临时脚本产物，工具名与参数一改就漂移。
本脚本用 AST 离线生成（不导入 kb_tools，无需 mcp/onnx 依赖），并支持 --check 做漂移检测。

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
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(os.path.dirname(BASE), 'flythings_intent_gate', 'catalog.json')


def collect():
    """按 register_all 的注册名单收集 op + 首行简介 + 参数名（顺序与实现一致）。"""
    src = io.open(os.path.join(BASE, 'kb_tools.py'), encoding='utf-8').read()
    tree = ast.parse(src)
    registered = set(re.findall(r'mcp\.tool\(\)\((\w+)\)', src))
    ops = []
    for n in tree.body:
        if not isinstance(n, ast.FunctionDef) or n.name not in registered:
            continue
        doc = (ast.get_docstring(n) or '').strip().splitlines()
        brief = (doc[0] if doc else '')[:90]
        args = [a.arg for a in n.args.args if a.arg not in ('ctx', 'self')]
        ops.append({'op': n.name, 'brief': brief, 'args': args})
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
