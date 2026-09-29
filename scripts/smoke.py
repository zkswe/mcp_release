# -*- coding: utf-8 -*-
"""MCP 自检 / 冒烟（离线，零副作用）——发布前必跑。

用法（在 MCP 根目录或任意位置）：
    python scripts/smoke.py            # 离线自检（默认）
    python scripts/smoke.py --screenshot   # 额外真机抓屏冒烟（需 adb + 设备）
    python scripts/smoke.py --json out.json
    python scripts/smoke.py --update-silent-baseline   # 重刷静默 except 基线

检查项：
  1. 版本号 / build / 工具数（kb_tools.MCP_VERSION）
  2. register_all 注册的工具：存在、可调用、签名可解析
  3. 关键模块依赖：ui_editor/ui_edit_apply/ui_diff/device_screenshot 等是否可用
  4. 入口一致性：mcp_server 入口 docstring 工具数
  5. 文档漂移：README 的版本号/工具数是否等于真实值
     （v0.27.77 起 README 精简为「一键安装 + 功能说明」，工具数改为**扫全部「N 个工具」提法对齐**，
      不再要求固定的 FAQ / 项目结构句位；用例数/知识规模的承载处见 check_consistency.py）
     （CHANGELOG.md 自 v0.27.31 起**冻结为历史归档**，不再维护、不再校验——沛哥 2026-09-11 定）
  6. catalog.json（本地意图闸门）ops 数是否等于真实工具数
  7. 双份 ui_tools 副本 sha256 一致（tools/ui_tools/ ↔ tools/FlyThings_mcp_open/ui_tools/）
  8. 隐私/路径泄露扫描：本机绝对路径 / 内网真机 IP / DESKTOP 主机名 / 真实 accessKey
     （v0.27.77 起只扫「可能被发布的内容」= git 的已跟踪 + 未忽略新文件；
      `.fsc/`/`.fun/` 这类 .gitignore 忽略的构建产物（含本机绝对路径）不再误报；无 git 时回退全量扫）
  9. 静默 except lint（调用 scripts/lint_silent_except.py，v0.27.32 起单一实现）
 10. 意图闸门 catalog 参数漂移（调 scripts/gen_gate_catalog.py --check）
退出码：0 = 全通过；1 = 有 FAIL。
输出为纯 ASCII（Windows 控制台 GBK 安全）。
"""
import argparse
import ast
import hashlib
import io
import json
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, 'ui_tools'))

RESULT = []


def check(ok, name, detail=''):
    RESULT.append((bool(ok), name, detail))
    print('%s %-46s %s' % ('[PASS]' if ok else '[FAIL]', name, detail))
    return bool(ok)


SILENT_LINT = os.path.join(BASE, 'scripts', 'lint_silent_except.py')
# 扫描范围：本仓库 .py/.md/.txt/.bat/.json（排除二进制；rag_index.json 单独提示）
_SCAN_EXT = ('.py', '.md', '.txt', '.bat', '.json')
_SCAN_SKIP_DIRS = ('__pycache__', '.git', '.vscode', 'node_modules')
_LEAK_PATTERNS = [
    ('本机绝对路径 C:/Users', re.compile(r'C:[\\/]Users[\\/]')),
    ('主机名 DESKTOP-', re.compile(r'DESKTOP-[A-Z0-9]{4,}')),
    ('内网 IP', re.compile(r'\b192\.168\.\d+\.\d+')),
]
_LEAK_ALLOW = [
    re.compile(r'C:[\\/]Users[\\/]<'),          # README 里的占位示例
    re.compile(r'192\.168\.1\.(100|1)\b'),      # 通用示例地址
]


# 静默 except 检测已抽成单一实现 scripts/lint_silent_except.py（v0.27.32）：
# 基线/白名单/违规判定全部在那里，smoke 只负责调用它（避免两处各写一套规则漂移）。


def _scan_files():
    """待扫描文件清单 [(相对路径, 绝对路径)]

    v0.27.77：优先用 git 的「已跟踪 + 未忽略的新文件」清单（`git ls-files -z --cached
    --others --exclude-standard`）= **可能被发布的内容**；否则 `.fsc/`/`.fun/` 这类构建产物
    （.gitignore 已忽略，却带本机绝对路径/CMakeCache 主机信息）会把隐私扫描一路扫红。
    git 不可用（无 git / 非仓库）时回退到 os.walk 全量扫描（保守，不漏）。
    """
    rels = None
    try:
        r = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others',
                            '--exclude-standard'], cwd=BASE,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
        if r.returncode == 0:
            rels = [x.decode('utf-8', 'replace') for x in r.stdout.split(b'\0') if x]
    except Exception:
        rels = None                 # 交给 os.walk 兜底
    if rels is None:
        rels = []
        for root, dirs, files in os.walk(BASE):
            dirs[:] = [d for d in dirs if d not in _SCAN_SKIP_DIRS]
            for f in files:
                rels.append(os.path.relpath(os.path.join(root, f), BASE))
    out = []
    for rel in rels:
        rel = rel.replace('\\', '/')
        parts = rel.split('/')
        if any(d in _SCAN_SKIP_DIRS for d in parts[:-1]):
            continue
        f = parts[-1]
        if not f.endswith(_SCAN_EXT) or f in ('rag_index.json', 'smoke.py'):
            continue
        p = os.path.join(BASE, rel)
        if not os.path.isfile(p) or os.path.getsize(p) > 30 * 1024 * 1024:
            continue
        out.append((rel, p))
    return out


def scan_leaks():
    """返回 [(相对路径, 行号, 触发模式)]。

    跳过：
      - rag_index.json（发布前由 rebuild 重建，内容随 knowledge 同步）
      - smoke.py（本文件自身就写着识别用正则）
      - git 忽略的文件（构建产物；见 _scan_files 说明）
    ⚠️ CHANGELOG.md 自 v0.27.32 起重新纳入扫描（已脱敏真机 IP；冻结归档也不能带设备信息）。
    """
    leaks = []
    for rel, p in _scan_files():
        try:
            txt = io.open(p, encoding='utf-8', errors='ignore').read()
        except Exception:
            continue
        for i, line in enumerate(txt.splitlines(), 1):
            for name, pat in _LEAK_PATTERNS:
                if pat.search(line) and not any(a.search(line) for a in _LEAK_ALLOW):
                    leaks.append((rel, i, name))
            if re.search(r'accessKey|access_key', line, re.I):
                m = re.search(r'\b[0-9a-fA-F]{40}\b', line)
                if m and set(m.group(0).lower()) != {'0'}:
                    leaks.append((rel, i, '真实 accessKey'))
    return leaks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--screenshot', action='store_true', help='extra: real device screenshot smoke')
    ap.add_argument('--device', default='', help='device serial for --screenshot')
    ap.add_argument('--json', default='', help='write result JSON here')
    ap.add_argument('--update-silent-baseline', action='store_true',
                    help='把当前静默 except 站点写为基线（仅清理历史债务时用）')
    a = ap.parse_args()

    print('=' * 72)
    print('FlyThings MCP smoke  (BASE=%s)' % BASE)
    print('=' * 72)

    # ---- 1) import + 版本
    try:
        import kb_tools as k
    except Exception as e:
        check(False, 'import kb_tools', repr(e))
        return finish(a)
    check(True, 'import kb_tools', '')
    ver = getattr(k, 'MCP_VERSION', '?')
    build = getattr(k, 'MCP_BUILD', '?')
    check(bool(re.match(r'^\d+\.\d+\.\d+-open$', str(ver))), 'MCP_VERSION format', str(ver))
    print('       version=%s build=%s' % (ver, build))

    # ---- 2) 注册工具（清单唯一来源 = kb_tools.OP_NAMES，避免手写列表漂移）
    names = list(getattr(k, 'OP_NAMES', []))
    dyn = list(k._tool_names())
    same_as_module = sorted(names) == dyn
    check(bool(names) and same_as_module, 'register_all tool count',
          '%d  (OP_NAMES == 模块内 flythings_* 函数: %s)' % (len(names), same_as_module))
    bad = []
    for n in names:
        f = getattr(k, n, None)
        if f is None or not callable(f):
            bad.append(n + ':missing')
            continue
        try:
            import inspect
            inspect.signature(f)
        except Exception as e:
            bad.append('%s:%s' % (n, e))
    check(not bad, 'tool functions callable', ','.join(bad) if bad else 'all ok')

    # ---- 3) 依赖模块
    for mod in ('uied', 'uia', 'udf', 'dss', 'h2j', 'j2h', 'h2j_genres', 'itx', 'tt', 'rs', 'pt', 'pkgtools'):
        if hasattr(k, mod):
            check(getattr(k, mod) is not None, 'module %s' % mod, '')
    for f in ('device_screenshot.py', 'ui_editor.py', 'ui_edit_apply.py', 'ui_diff.py'):
        check(os.path.isfile(os.path.join(BASE, 'ui_tools', f)), 'ui_tools/%s' % f, '')

    # ---- 4) 入口一致性
    srv = io.open(os.path.join(BASE, 'mcp_server.py'), encoding='utf-8').read()
    m = re.search(r'(\d+)\s*个能力合一', srv)
    check(bool(m) and int(m.group(1)) == len(names), 'mcp_server docstring count',
          '%s vs %d' % (m.group(1) if m else '?', len(names)))

    # ---- 5) 文档漂移
    rd = io.open(os.path.join(BASE, 'README.md'), encoding='utf-8').read()
    # v0.27.77（README 精简为「一键安装 + 功能说明」）：不再要求固定的
    # 「FAQ 工具列表 < N」句位，改为**扫全部「N 个工具」提法并全部对齐**（少写不报、写错必报）。
    mentions = re.findall(r'(\d+)\s*个工具', rd)
    bad = sorted({int(x) for x in mentions} - {len(names)})
    check(bool(mentions) and not bad, 'README tool count (all mentions)',
          'README=%s vs %d（%d 处提及）'
          % (','.join(str(b) for b in bad) if bad else (mentions[0] if mentions else '?'),
             len(names), len(mentions)))
    check(ver in rd, 'README mentions current version', str(ver))
    # CHANGELOG.md 自 v0.27.31 起冻结为历史归档（不再维护/不提交），版本史唯一来源 = MCP_FEATURES + README
    feats = getattr(k, 'MCP_FEATURES', [])
    check(bool(feats) and str(ver) in feats[0], 'MCP_FEATURES[0] mentions version',
          feats[0][:40] if feats else 'empty')

    # ---- 6) 意图闸门 catalog
    catp = os.path.join(os.path.dirname(BASE), 'flythings_intent_gate', 'catalog.json')
    if os.path.isfile(catp):
        cat = json.load(io.open(catp, encoding='utf-8'))
        cnt = cat.get('count', len(cat.get('ops', [])))
        check(cnt == len(names), 'gate catalog ops count', '%s vs %d (regenerate: python scripts/gen_gate_catalog.py)' % (cnt, len(names)))
    else:
        check(True, 'gate catalog.json (未分发 → skip)',
              '%s 不存在；闸门不在本仓库内，跳过 count 校验（仅提示）' % catp)

    # ---- 7) 双份 ui_tools 副本一致性（v0.27.31）
    twin = os.path.join(os.path.dirname(BASE), 'ui_tools')
    fdiff = []
    mine = os.path.join(BASE, 'ui_tools')
    if os.path.isdir(twin) and os.path.isdir(mine):
        for f in sorted(os.listdir(mine)):
            if not f.endswith(('.py', '.md')):
                continue
            p1, p2 = os.path.join(mine, f), os.path.join(twin, f)
            if not os.path.isfile(p2):
                fdiff.append(f + ':missing-in-tools/ui_tools')
                continue
            h1 = hashlib.sha256(io.open(p1, 'rb').read()).hexdigest()
            h2 = hashlib.sha256(io.open(p2, 'rb').read()).hexdigest()
            if h1 != h2:
                fdiff.append(f + ':hash-mismatch')
        check(not fdiff, 'ui_tools dual copy hash sync',
              ','.join(fdiff) if fdiff else 'both copies identical')
    else:
        check(True, 'ui_tools dual copy hash sync (副本不在本机 → skip)',
              'missing dir: %s（发布前的双份同步检查需要该副本目录，缺失不算失败）' % twin)

    # ---- 8) 隐私 / 路径泄露（v0.27.31）
    leaks = scan_leaks()
    check(not leaks, 'privacy/path leak scan',
          'clean' if not leaks else '%d hits: %s' % (leaks.__len__(), '; '.join(
              '%s:%d(%s)' % t for t in leaks[:6])))

    # ---- 9) 静默 except lint（v0.27.32：单一实现 = scripts/lint_silent_except.py）
    if a.update_silent_baseline:
        try:
            rc = subprocess.call([sys.executable, SILENT_LINT, '--update-baseline'])
            print('       silent-except baseline updated (rc=%d)' % rc)
        except Exception as e:
            check(False, 'silent except baseline update', repr(e))
    if os.path.isfile(SILENT_LINT):
        try:
            rc = subprocess.call([sys.executable, SILENT_LINT],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            check(rc == 0, 'silent except lint',
                  'no new silent except' if rc == 0
                  else 'see: python scripts/lint_silent_except.py')
        except Exception as e:
            check(False, 'silent except lint', repr(e))
    else:
        check(False, 'silent except lint script', SILENT_LINT)

    # ---- 10) 意图闸门 catalog 参数漂移（v0.27.31）
    gen = os.path.join(BASE, 'scripts', 'gen_gate_catalog.py')
    if os.path.isfile(gen):
        try:
            rc = subprocess.call([sys.executable, gen, '--check'],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            check(rc == 0, 'gate catalog args in sync', 'see gen_gate_catalog.py --check')
        except Exception as e:
            check(False, 'gate catalog args in sync', repr(e))

    # ---- 11) 可选：真机抓屏冒烟
    if a.screenshot:
        try:
            r = json.loads(k.flythings_device_screenshot(device=a.device, scale=0.25, timeout=120))
            check(bool(r.get('success')), 'device screenshot', str(r.get('path', r.get('error')))[:90])
            if r.get('success'):
                check(os.path.isfile(r['path']), 'screenshot file exists', r['path'])
        except Exception as e:
            check(False, 'device screenshot', repr(e))

    return finish(a)


def finish(a):
    fails = [r for r in RESULT if not r[0]]
    print('-' * 72)
    print('total=%d  fail=%d  %s' % (len(RESULT), len(fails), 'OK' if not fails else 'FAILED'))
    for _, n, d in fails:
        print('  FAIL %s %s' % (n, d))
    if a.json:
        io.open(a.json, 'w', encoding='utf-8').write(json.dumps(
            [{'ok': o, 'name': n, 'detail': d} for o, n, d in RESULT], ensure_ascii=False, indent=2))
        print('json -> %s' % a.json)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
