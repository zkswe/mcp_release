#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 `fun build` 生成的 `<page>Logic.cc` 头部（IDE 编译 / FUN 编译 框架差异）。

## 问题（2026-10-06 需求方报，已用两个模板文件对死）

对比 `templates/DemoControls_V85X/src/logic/` 两份头部：

| | `buttonLogic.cc`（正确） | `canvasLogic.cc`（fun 生成，有 bug） |
|---|---|---|
| `REGISTER_ACTIVITY_TIMER_TAB` | 在 `#ifdef FUN_BUILD … #endif` **外面** | 在守卫**里面** |
| `#include "base/log.h"` | **有** | **没有** |

后果各坏一种编译：
  · **IDE 编译**（不定义 `FUN_BUILD`）→ canvas 形态下定时器表整个消失，
    而 IDE 生成的 `src/activity/<page>Activity.cpp` 里
    `sizeof(REGISTER_ACTIVITY_TIMER_TAB)/sizeof(S_ACTIVITY_TIMEER)` 引用它 → **未声明报错**；
  · **FUN 编译**（定义 `FUN_BUILD`）→ 缺 `base/log.h`，`LOGD_TRACE`/`LOGD` 未声明 → **报错**。

正确形态 = 定时器表与 `base/log.h` 都在守卫**外面**（`buttonLogic.cc` 那样），两种编译都能过。

## 用法

    python scripts/fix_fun_logic_cc.py <项目根 | 单个 .cc | 目录> [--check] [--dry-run] [--quiet]
      --check     只报告哪些文件需要修（rc=1 = 有需要修的，0 = 全都已 OK）
      --dry-run   打印将要做的改动，不写盘
      --quiet     只在有改动/需要修时打印

幂等：已经正确的文件不会被再改一次。
"""
import argparse
import io
import os
import re
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception as e:                            # noqa: BLE001 —— 不静默：说明控制台不支持重配
        sys.stderr.write('[NOTE] stdout 不支持 UTF-8 重配（不影响修复结果）：%s\n' % e)

GUARD_RE = re.compile(r'^[ \t]*#\s*ifdef[ \t]+(\w+_BUILD)\b')
ENDIF_RE = re.compile(r'^[ \t]*#\s*endif\b[^\n]*')
TABLE_RE = re.compile(r'^[ \t]*static[ \t]+S_ACTIVITY_TIMEER[ \t]+'
                      r'REGISTER_ACTIVITY_TIMER_TAB\s*\[\s*\]\s*=\s*\{')
LOG_RE = re.compile(r'\b(LOGD_TRACE|LOGD|LOGI|LOGE|LOGW)\s*\(')
LOG_INCLUDE = '#include "base/log.h"'


def _guard_span(lines):
    """返回 (guard 名, #ifdef 行号, #endif 行号)；找不到返回 None。"""
    start = None
    for i, l in enumerate(lines[:12]):                        # 守卫必在文件最前面
        m = GUARD_RE.match(l)
        if m:
            start, name = i, m.group(1)
            break
    if start is None:
        return None
    for j in range(start + 1, len(lines)):
        if ENDIF_RE.match(lines[j]) and name in lines[j]:
            return name, start, j
        if ENDIF_RE.match(lines[j]) and '//' not in lines[j]:
            return name, start, j                             # 无注释的 #endif 兜底
    return name, start, None


def analyze(text):
    """返回 (需要修吗, 说明, 新文本)。"""
    lines = text.splitlines(True)
    span = _guard_span(lines)
    if not span:
        return False, '无 *_BUILD 守卫（不是 fun 生成形态）', text
    name, s, e = span
    if e is None:
        return False, '守卫没有配对的 #endif（不猜，跳过）', text

    body = lines[s + 1:e]
    tbl = [k for k, l in enumerate(body) if TABLE_RE.match(l)]
    if not tbl:
        # 没有定时器表：只可能缺 log.h
        if LOG_RE.search(text) and LOG_INCLUDE not in text:
            new = ''.join(lines[:e + 1]) + '\n' + LOG_INCLUDE + '\n' + ''.join(lines[e + 1:])
            return True, '补 %s' % LOG_INCLUDE, new
        return False, 'OK（守卫里无定时器表、log.h 也在）', text

    k = tbl[0]
    # 连同紧邻上方的一段注释（/** … */）一起搬
    top = k
    if top > 0:
        back = top - 1
        if body[back].strip().endswith('*/'):
            j = back
            while j >= 0 and '/**' not in body[j]:
                j -= 1
            if j >= 0:
                top = j
    if k == len(body) - 1:
        bot = k + 1
    else:
        bot = k + 1
        while bot < len(body) and body[bot].strip() and not body[bot].lstrip().startswith('}'):
            bot += 1
        while bot < len(body) and '}' not in body[bot]:
            bot += 1
        bot += 1
    block = body[top:bot]
    rest = body[:top] + body[bot:]
    tail = ''.join(lines[e + 1:])
    need_log = bool(LOG_RE.search(text)) and LOG_INCLUDE not in text
    # 组装：守卫块（已去掉表）→ #endif → 空行 → 表 →（log.h 若缺）→ 其余
    parts = [''.join(lines[:s + 1]), ''.join(rest)]
    if parts[-1] and not parts[-1].endswith('\n'):
        parts.append('\n')
    parts.append(lines[e])
    parts.append('\n')
    parts.append(''.join(block))
    if need_log:
        parts.append('\n' + LOG_INCLUDE + '\n')
    parts.append(tail)
    return True, ('把定时器表移出 #ifdef %s + %s'
                  % (name, '补 ' + LOG_INCLUDE if need_log else 'log.h 已在')), ''.join(parts)


def targets(root):
    if os.path.isfile(root) and root.endswith(('.cc', '.cpp')):
        return [root]
    out = []
    for dirpath, dirnames, files in os.walk(root):
        if 'logic' not in dirpath.replace(os.sep, '/'):
            continue
        for f in sorted(files):
            if f.endswith(('.cc', '.cpp')):
                out.append(os.path.join(dirpath, f))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('target', help='项目根 / 目录 / 单个 .cc')
    ap.add_argument('--check', action='store_true', help='只报告（rc=1=有需修的）')
    ap.add_argument('--dry-run', action='store_true', help='不写盘')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()
    files = targets(os.path.abspath(a.target))
    if not files:
        print('[NOTE] 没有找到 src/logic/*.cc（target=%s）' % a.target)
        return 0
    need, fixed, skipped = [], [], 0
    for p in files:
        text = io.open(p, encoding='utf-8', errors='replace').read()
        changed, why, new = analyze(text)
        rel = os.path.relpath(p)
        if changed:
            need.append((rel, why))
            if not a.check:
                if not a.dry_run:
                    io.open(p, 'w', encoding='utf-8', newline='').write(new)
                print('[%s] %s —— %s' % ('dry-run' if a.dry_run else '已修', rel, why))
                fixed.append(rel)
        else:
            skipped += 1
            if not a.quiet and not a.check:
                print('[OK] %s —— %s' % (rel, why))
    print('--- 扫描 %d 个文件：%s%d 个、OK %d 个' %
          (len(files), '需修 ' if a.check else '已修 ', len(need), skipped))
    if not a.check and fixed:
        print('    建议随项目一起提交（fun build 会重生成 logic.cc → 每次 build 后再跑一遍本脚本）')
    return 1 if (a.check and need) else 0


if __name__ == '__main__':
    sys.exit(main())
