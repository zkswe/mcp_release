# -*- coding: utf-8 -*-
"""双份 ui_tools 同步检查/修复（单一来源 = MCP 包内 ui_tools/）。

背景（报告 P1-3.4）：同一批脚本存在两份——
  · `tools/FlyThings_mcp_open/ui_tools/` ← **源**（开发只在这边改）
  · `tools/ui_tools/`                    ← 副本（workspace 里给非 MCP 流程/人肉用）
历史上靠「人肉移植改动、不能整文件覆盖」，已经漂移过（gen_res.py emoji 功能只在 MCP 侧）。
本脚本把同步变成一条命令 + 一个可进发布前置的 --check。

用法：
    python scripts/sync_ui_tools.py --check     # 只比对（不一致退出码 1；smoke 第 8 项用它）
    python scripts/sync_ui_tools.py --apply     # 源 -> 副本，整文件复制（行尾随源；--check 比内容不比行尾）
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


def _read(path):
    with open(path, 'rb') as f:
        return f.read()


def _is_text(data):
    """无 NUL 字节即按文本处理（与 git 的 `text` 判定同精神）。"""
    return b'\0' not in data


def _norm(data):
    """文本 → 换行归一成 LF 再比；二进制 → 原样。

    为什么必须归一（2026-10-04 实测）：本仓没有 `.gitattributes`，而本机 `core.autocrlf=true`
    —— 同一个提交在不同检出里落盘换行可以不同（实测：主树 `ui_tools/*.py` 是 LF、另建的
    `git worktree` 检出是 CRLF，同一文件 161531 vs 164496 字节）。按原始字节比哈希，于是
    「同一份提交」在另一棵树里被判**双份漂移**（假红，且只在换行策略不同的机器/检出上出现）。
    归一只影响**行尾**，内容差异照样抓得到。
    """
    if not _is_text(data):
        return data
    return data.replace(b'\r\n', b'\n').replace(b'\r', b'\n')


def compare(dst):
    """返回 {file: status}，status in (same, drift, missing_in_copy, extra_in_copy)。

    「same」= **内容一致**（文本已按换行归一，见 `_norm`），不是字节一致 —— 跨检出/跨平台
    的换行差异不是漂移。
    """
    res = {}
    src_files = sources()
    for name in src_files:
        a = os.path.join(SRC, name)
        b = os.path.join(dst, name)
        if not os.path.isfile(b):
            res[name] = 'missing_in_copy'
        elif _norm(_read(a)) != _norm(_read(b)):
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
    ap.add_argument('--apply', action='store_true', help='源 -> 副本，整文件复制（行尾按源）')
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
        # 副本目录在**仓库之外**（workspace 布局：tools/FlyThings_mcp_open/ui_tools ↔ tools/ui_tools）。
        # 公开仓库形态（fresh clone / CI 只 checkout 本仓库）下它必然不存在 —— 那是「本机没有副本」，
        # 不是「双份漂移」。所以用**专用退出码 2 = skip**，让消费方（smoke / check_consistency）
        # 统一按「跳过并提示」处理，而不是一个容错、一个硬红（2026-10-03 评审：同一口径两个消费方不一致）。
        print('[SKIP] 副本目录不存在: %s（--to 指定）；本机无副本 → 跳过比对（不是漂移）' % dst)
        return 2

    # 发布版形态（引擎收进 bin/zkuitool，ui_tools/*.py 是转发薄壳）：本脚本比的是
    # 「两份源码副本」，薄壳 ≠ 源码是**设计如此**，不是漂移 → 统一 rc=2（skip）。
    if os.path.isfile(os.path.join(SRC, '_zktool.py')):
        print('[SKIP] 薄壳形态（发布版）：ui_tools/*.py 为实现体在 bin/zkuitool 的转发薄壳 → 不比对')
        return 2

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
