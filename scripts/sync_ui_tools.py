# -*- coding: utf-8 -*-
"""双份 ui_tools 同步检查/修复（单一来源 = MCP 包内 ui_tools/）。

背景（报告 P1-3.4）：同一批脚本存在两份——
  · `tools/FlyThings_mcp_open/ui_tools/` ← **源**（开发只在这边改）
  · `tools/ui_tools/`                    ← 副本（workspace 里给非 MCP 流程/人肉用）
历史上靠「人肉移植改动、不能整文件覆盖」，已经漂移过（gen_res.py emoji 功能只在 MCP 侧）。
本脚本把同步变成一条命令 + 一个可进发布前置的 --check。

用法：
    python scripts/sync_ui_tools.py --check     # 只比对（不一致退出码 1；smoke 第 8 项用它）
    python scripts/sync_ui_tools.py --apply     # 源 -> 副本，逐文件字节级复制
    python scripts/sync_ui_tools.py --json      # 机器可读结果
    python scripts/sync_ui_tools.py --to <dir>  # 指定副本目录（默认 ../ui_tools）
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, 'ui_tools')
DEFAULT_DST = os.path.join(os.path.dirname(BASE), 'ui_tools')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def sources():
    """源目录里的全部文件（排除 __pycache__ 之类）。"""
    out = []
    for name in sorted(os.listdir(SRC)):
        p = os.path.join(SRC, name)
        if os.path.isfile(p) and not name.endswith(('.pyc', '.log')):
            out.append(name)
    return out


def compare(dst):
    """返回 {file: status}，status in (same, drift, missing_in_copy, extra_in_copy)。"""
    res = {}
    src_files = sources()
    for name in src_files:
        a = os.path.join(SRC, name)
        b = os.path.join(dst, name)
        if not os.path.isfile(b):
            res[name] = 'missing_in_copy'
        elif sha256(a) != sha256(b):
            res[name] = 'drift'
        else:
            res[name] = 'same'
    if os.path.isdir(dst):
        for name in sorted(os.listdir(dst)):
            p = os.path.join(dst, name)
            if os.path.isfile(p) and name not in src_files and not name.endswith(('.pyc', '.log')):
                res[name] = 'extra_in_copy'
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='只比对（不一致退出码 1）')
    ap.add_argument('--apply', action='store_true', help='源 -> 副本，字节级复制')
    ap.add_argument('--to', default=DEFAULT_DST, help='副本目录（默认 ../ui_tools）')
    ap.add_argument('--json', action='store_true', help='输出 JSON')
    a = ap.parse_args()
    if not a.check and not a.apply:
        a.check = True
    if not os.path.isdir(SRC):
        print('[FAIL] 源目录不存在: %s' % SRC)
        return 1
    dst = os.path.abspath(a.to)
    if not os.path.isdir(dst):
        print('[FAIL] 副本目录不存在: %s（--to 指定）' % dst)
        return 1

    res = compare(dst)
    bad = {k: v for k, v in res.items() if v != 'same'}
    if a.apply:
        changed = []
        for name in sources():
            if res.get(name) != 'same':
                shutil.copy2(os.path.join(SRC, name), os.path.join(dst, name))
                changed.append(name)
        if a.json:
            print(json.dumps({'applied': changed, 'to': dst}, ensure_ascii=False))
        else:
            print('synced %d file(s) -> %s' % (len(changed), dst))
            for c in changed:
                print('   ' + c)
            if not changed:
                print('   (already in sync)')
        return 0

    if a.json:
        print(json.dumps({'src': SRC, 'dst': dst, 'files': res, 'bad': bad},
                         ensure_ascii=False, indent=2))
    else:
        print('ui_tools sync  src=%s\n               dst=%s' % (SRC, dst))
        for name, st in res.items():
            print('   [%-15s] %s' % (st, name))
    if bad:
        if not a.json:
            print('[FAIL] 双份不一致 %d 个文件：%s' % (len(bad), ', '.join(bad)))
            print('       fix: python scripts/sync_ui_tools.py --apply')
        return 1
    if not a.json:
        print('[PASS] 双份一致（%d 个文件）' % len(res))
    return 0


if __name__ == '__main__':
    sys.exit(main())
