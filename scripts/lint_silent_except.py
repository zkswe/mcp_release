# -*- coding: utf-8 -*-
"""静默异常 lint：AST 扫描 `except ...: pass`（只吞不处理，连 warnings 都不留）。

背景（v0.27.32，单一实现）：v0.27.30 的「阴影转图三连 bug」根因就是
`float('4px')` 抛错被 `except Exception: pass` 静默吞掉 → 阴影图一张不生成，
还只甩一句误导提示「含 CSS 效果请自己切图」。人肉审计发现，机器必须先拦住。

三层口径（同一份检测逻辑，smoke.py 第 9 项直接调本脚本，不再各写一套）：
  1. 历史基线 scripts/silent_except_baseline.txt
     —— 已登记的存量债务（键 = 相对路径#代码片段哈希，行号漂移不影响）
  2. 白名单 scripts/silent_except_whitelist.txt
     —— 显式豁免，**每条必须写理由**，格式（`::` 分隔）：
         <相对路径#片段哈希>  ::  <为什么可以吞>
     理由要写清「吞掉它的代价已被评估过」（例：可选依赖缺失，已有显式降级提示）
  3. 其余站点 = 违规 → 退出码 1
     —— 要么改成把失败写进 warnings[]/返回体（调用方能看见），要么登记豁免并写理由

用法（MCP 根目录或任意位置）：
    python scripts/lint_silent_except.py                  # 检查
    python scripts/lint_silent_except.py --list           # 只列当前站点（含键，便于抄进白名单）
    python scripts/lint_silent_except.py --no-baseline    # 严格模式：忽略基线，报告全部站点
    python scripts/lint_silent_except.py --update-baseline # 把当前站点全量登记为基线（清债后重建）
    python scripts/lint_silent_except.py --json out.json  # 附机器可读结果
"""
import argparse
import ast
import hashlib
import io
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(BASE, 'scripts', 'silent_except_baseline.txt')
WHITELIST = os.path.join(BASE, 'scripts', 'silent_except_whitelist.txt')
SKIP_DIRS = ('__pycache__', '.git', '.vscode', 'node_modules', 'build', 'dist',
                  '.venv', 'venv', '.fsc', '.fun', 'toolchain')


def sites(path):
    """返回文件里「静默吞异常」的站点：[(行号, 键, 片段)]。键用片段哈希，不用行号。"""
    try:
        src = io.open(path, encoding='utf-8').read()
        tree = ast.parse(src)
    except Exception:
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        body = [b for b in node.body
                if not (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant))]
        if len(body) == 1 and isinstance(body[0], (ast.Pass, ast.Continue)):
            seg = re.sub(r'\s+', ' ', (ast.get_source_segment(src, node) or '')).strip()
            out.append((node.lineno, hashlib.sha1(seg.encode('utf-8')).hexdigest()[:10], seg[:100]))
    return out


def scan():
    """全仓扫描 → {键: {'path','line','snippet'}}。"""
    hits = {}
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in sorted(files):
            if not f.endswith('.py'):
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, BASE).replace('\\', '/')
            for ln, key, seg in sites(p):
                hits['%s#%s' % (rel, key)] = {'path': rel, 'line': ln, 'snippet': seg}
    return hits


def _keys(path):
    """读基线/白名单的键（忽略注释与空行）。"""
    if not os.path.isfile(path):
        return set()
    out = set()
    for line in io.open(path, encoding='utf-8'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        out.add(line.split('  # ')[0].split('  :: ')[0].strip())
    return out


def _whitelist(path):
    """读白名单 → {键: 理由}；理由为空即 None（报告里单独判 FAIL）。"""
    out = {}
    if not os.path.isfile(path):
        return out
    for line in io.open(path, encoding='utf-8'):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        key, _, reason = s.partition('::')
        out[key.strip()] = reason.strip()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default='', help='把结果写成 JSON')
    ap.add_argument('--list', action='store_true', help='只列当前站点')
    ap.add_argument('--no-baseline', action='store_true', help='严格模式：忽略基线')
    ap.add_argument('--update-baseline', action='store_true', help='把当前站点全量写为基线')
    a = ap.parse_args()

    cur = scan()
    if a.list:
        for k in sorted(cur):
            v = cur[k]
            print('%s  # %s:%d | %s' % (k, v['path'], v['line'], v['snippet']))
        print('total=%d' % len(cur))
        return 0

    if a.update_baseline:
        lines = ['# 静默 except 基线（except 体只剩 pass/continue）。键 = 相对路径#片段哈希。',
                 '# 新增站点即 FAIL；要么改代码把失败写进 warnings[]，要么在 '
                 'scripts/silent_except_whitelist.txt 登记并写理由。',
                 '# 重建：python scripts/lint_silent_except.py --update-baseline']
        for k in sorted(cur):
            v = cur[k]
            lines.append('%s  # %s:%d | %s' % (k, v['path'], v['line'], v['snippet']))
        io.open(BASELINE, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
        print('baseline updated: %s (%d sites)' % (os.path.relpath(BASELINE, BASE), len(cur)))
        return 0

    base = set() if a.no_baseline else _keys(BASELINE)
    wl = _whitelist(WHITELIST)
    new = sorted(k for k in cur if k not in base and k not in wl)
    no_reason = sorted(k for k, r in wl.items() if not r and k in cur)
    stale_wl = sorted(k for k in wl if k not in cur)

    print('=' * 72)
    print('silent-except lint  (BASE=%s)' % BASE)
    print('=' * 72)
    print('sites=%d  baseline=%d  whitelist=%d  new=%d'
          % (len(cur), len(base), len(wl), len(new)))
    for k in new:
        v = cur[k]
        print('  [FAIL] new silent except: %s:%d | %s' % (v['path'], v['line'], v['snippet']))
    for k in no_reason:
        v = cur.get(k, {})
        print('  [FAIL] whitelist entry without reason: %s | %s'
              % (k, v.get('snippet', '')))
    for k in stale_wl:
        print('  [WARN] whitelist entry no longer matches any site: %s' % k)
    if not new and not no_reason:
        print('  [PASS] no new silent except (baselined debt: %d)' % len(base & set(cur)))
    fails = len(new) + len(no_reason)
    print('-' * 72)
    print('total=%d  fail=%d  %s' % (len(cur), fails, 'OK' if not fails else 'FAILED'))
    if a.json:
        io.open(a.json, 'w', encoding='utf-8').write(json.dumps(
            {'sites': len(cur), 'baseline': len(base), 'whitelist': len(wl),
             'new': [{'key': k, **cur[k]} for k in new],
             'whitelistWithoutReason': no_reason,
             'whitelistStale': stale_wl}, ensure_ascii=False, indent=2))
        print('json -> %s' % a.json)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
