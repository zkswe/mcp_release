# -*- coding: utf-8 -*-
"""发布前置一致性校验（release preflight）——v0.27.33 起为「发布前必跑」的单一闸门。

为什么要有它（检讨报告 §2.1 / §3.4）：同一件事（版本号、工具数、篇数）原先散落在
kb_tools / mcp_server / catalog.json / README / MCP_FEATURES / CHANGELOG 六处手写，
每次改动都要人肉同步，历史上反复漂移（版本号、118 vs 129 篇、checkHint 0.3.0 等）。
本脚本把「不许漂移」的关系全部机器化，并**复用**已有单一实现（不重复造检测）：

  1. 版本号四方一致：kb_tools.MCP_VERSION = pyproject [tool.flythings].mcp_version
     = "v"+pyproject.project.version+"-open"，且 README 提到当前版本
  2. 工具数六方一致：kb_tools.OP_NAMES = mcp_server docstring = README(2 处)
     = 意图闸门 catalog.json = tools_manifest.json
  3. 平台矩阵自洽：platforms.PLATFORMS 的模板目录 / bin_tools 目录真实存在；
     别名可归一；未知平台必须报错并列出支持项
  4. 知识索引新鲜度：rag_index.json 的文档集合 == 磁盘上 knowledge/(+wiki) 的 md 集合，
     且索引不早于最新源文件；README 里写的「N 篇 wiki」必须等于真实篇数
  5. tools_manifest.json 与代码/表一致（委派 scripts/gen_manifest.py --check）
  6. 冒烟与纪律（委派单一实现）：scripts/smoke.py（隐私扫描 / 静默 except / 双份 ui_tools 哈希
     / 闸门 catalog 参数同步）、scripts/sync_ui_tools.py --check
  7. 交付纪律文件齐备：pyproject.toml / requirements.lock / install.bat / tests/ 存在
     （--with-tests 时进一步真跑 tests/）

用法（在 MCP 根目录或任意位置）：
    python scripts/check_consistency.py                 # 全量校验（离线）
    python scripts/check_consistency.py --skip-smoke    # 跳过委派的 smoke（快速自查）
    python scripts/check_consistency.py --with-tests    # 额外真跑 tests/ 契约用例
退出口：0 = 全通过；1 = 有 FAIL。
输出纯 ASCII 安全（Windows 控制台 GBK 不乱码）。
"""
import argparse
import ast
import io
import json
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUB = os.path.join(BASE, 'scripts')
if BASE not in sys.path:
    sys.path.insert(0, BASE)

RESULT = []
WIKI_ROOT = os.path.join(os.path.expanduser('~'), '.openclaw', 'workspace', 'wiki', 'flythings')


def check(ok, name, detail=''):
    RESULT.append((bool(ok), name, detail))
    print('%s %-44s %s' % ('[PASS]' if ok else '[FAIL]', name, detail))
    return bool(ok)


def _read(p):
    return io.open(p, encoding='utf-8', errors='ignore').read()


def _ast_const(src_path, name):
    tree = ast.parse(_read(src_path))
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in n.targets):
            try:
                return ast.literal_eval(n.value)
            except (ValueError, SyntaxError):
                return None
    return None


def _pyproject():
    """读 pyproject.toml（tomllib 优先，3.10 退化正则）。返回 (project_version, mcp_version)。"""
    p = os.path.join(BASE, 'pyproject.toml')
    txt = _read(p) if os.path.isfile(p) else ''
    try:
        import tomllib
        d = tomllib.loads(txt)
        return d.get('project', {}).get('version', ''), \
            d.get('tool', {}).get('flythings', {}).get('mcp_version', '')
    except Exception:
        pv = re.search(r'^version\s*=\s*"([^"]+)"', txt, re.M)
        mv = re.search(r'^mcp_version\s*=\s*"([^"]+)"', txt, re.M)
        return (pv.group(1) if pv else ''), (mv.group(1) if mv else '')


def _run(args):
    try:
        r = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           cwd=BASE, timeout=900)
        return r.returncode, r.stdout.decode('utf-8', 'replace')
    except Exception as e:                      # 解释器/脚本缺失 → 视为失败并回显
        return 1, repr(e)


def stage_versions():
    ver = _ast_const(os.path.join(BASE, 'kb_tools.py'), 'MCP_VERSION') or ''
    pv, mv = _pyproject()
    check(bool(re.match(r'^\d+\.\d+\.\d+-open$', str(ver))), 'MCP_VERSION format', str(ver))
    check(mv == ver, 'pyproject [tool.flythings].mcp_version', '%s vs %s' % (mv, ver))
    want_pv = re.sub(r'-open$', '', str(ver))
    check(pv == want_pv, 'pyproject project.version', '%s vs %s' % (pv, want_pv))
    rd = _read(os.path.join(BASE, 'README.md'))
    check(str(ver) in rd, 'README mentions current version', str(ver))
    check(('pip install -r' in rd or 'requirements.lock' in rd),
          'README installs via requirements.lock', '')


def stage_tool_count():
    names = _ast_const(os.path.join(BASE, 'kb_tools.py'), 'OP_NAMES') or ()
    srv = _read(os.path.join(BASE, 'mcp_server.py'))
    m = re.search(r'(\d+)\s*(?:个能力合一|个能力)', srv)
    check(bool(m) and int(m.group(1)) == len(names), 'mcp_server docstring count',
          '%s vs %d' % (m.group(1) if m else '?', len(names)))
    rd = _read(os.path.join(BASE, 'README.md'))
    m = re.search(r'\*\*(\d+)\s*个工具\*\*', rd)
    check(bool(m) and int(m.group(1)) == len(names), 'README tool count',
          '%s vs %d' % (m.group(1) if m else '?', len(names)))
    m = re.search(r'\|\s*工具列表\s*<\s*(\d+)', rd)
    check(bool(m) and int(m.group(1)) == len(names), 'README FAQ count',
          '%s vs %d' % (m.group(1) if m else '?', len(names)))
    m = re.search(r'#\s*工具定义与注册（(\d+)\s*个）', rd)
    check(bool(m) and int(m.group(1)) == len(names), 'README project-tree count',
          '%s vs %d' % (m.group(1) if m else '?', len(names)))
    gp = os.path.join(os.path.dirname(BASE), 'flythings_intent_gate', 'catalog.json')
    if os.path.isfile(gp):
        cnt = json.loads(_read(gp)).get('count')
        check(cnt == len(names), 'gate catalog count', '%s vs %d' % (cnt, len(names)))
    else:
        check(False, 'gate catalog.json exists', gp)
    mp = os.path.join(BASE, 'tools_manifest.json')
    if os.path.isfile(mp):
        d = json.loads(_read(mp))
        check(d.get('toolCount') == len(names) and len(d.get('ops', [])) == len(names),
              'tools_manifest count', '%s vs %d' % (d.get('toolCount'), len(names)))
        check(d.get('version') == _ast_const(os.path.join(BASE, 'kb_tools.py'), 'MCP_VERSION'),
              'tools_manifest version', str(d.get('version')))
    else:
        check(False, 'tools_manifest.json exists', mp)


def stage_platforms():
    import platforms as pl
    tpl_root = os.path.join(BASE, 'templates')
    bin_root = os.path.join(BASE, 'bin_tools')
    ide = {}
    try:
        import project_tools as pt                     # 需要 mcp 之外的标准库，安全
        ide = getattr(pt, 'IDE_TEMPLATES', {}) or {}
    except Exception:
        ide = {}
    bad = []
    for name, meta in pl.PLATFORMS.items():
        tpl = meta.get('template', '')
        ok_tpl = os.path.isdir(os.path.join(tpl_root, tpl)) or (
            tpl in set(ide.values()) and any(
                os.path.isdir(os.path.join(d, tpl)) for d in set(ide.values()) if os.path.isabs(d)))
        if not ok_tpl:
            bad.append('%s:template(%s)' % (name, tpl))
        bt = meta.get('binTool', '')
        if not os.path.isdir(os.path.join(bin_root, bt)):
            bad.append('%s:bin_tools/%s' % (name, bt))
    check(not bad, 'platforms meta -> real dirs', ','.join(bad) if bad else
          '%d platforms ok' % len(pl.PLATFORMS))
    try:
        norm = [pl.validate('z21'), pl.validate('f133emmc'), pl.validate('t113emmc'),
                pl.validate('v85xemmc'), pl.normalize('Z-21')]
        check(norm[:4] == ['Z21', 'F133', 'T113', 'V85X'],
              'platforms validate aliases', ','.join(str(x) for x in norm))
    except Exception as e:
        check(False, 'platforms validate aliases', repr(e))
    try:
        pl.validate('NOT_A_PLATFORM')
        check(False, 'unknown platform rejected', 'no error raised')
    except ValueError as e:
        check('支持' in str(e) or 'F133' in str(e), 'unknown platform rejected', str(e)[:60])
    except Exception as e:
        check(False, 'unknown platform rejected', repr(e))
    check(pl.DEFAULT_PLATFORM in pl.PLATFORMS, 'default platform defined',
          str(pl.DEFAULT_PLATFORM))


def _expected_md_sets():
    """按 rebuild_index_local.py 的口径推导索引应包含的文档集合（相对路径，'/' 分隔）。"""
    kb_dir = os.path.join(BASE, 'knowledge')
    known, expected = set(), set()
    if os.path.isdir(kb_dir):
        for r, _, fs in os.walk(kb_dir):
            for f in fs:
                if f.endswith('.md'):
                    rel = os.path.relpath(os.path.join(r, f), kb_dir).replace('\\', '/')
                    known.add(rel)
                    expected.add('knowledge/' + rel)
    wiki_count = 0
    if os.path.isdir(WIKI_ROOT):
        for r, _, fs in os.walk(WIKI_ROOT):
            for f in fs:
                if f.endswith('.md'):
                    rel = os.path.relpath(os.path.join(r, f), WIKI_ROOT).replace('\\', '/')
                    if rel in known:
                        continue
                    expected.add(rel)
                    wiki_count += 1
    return expected, wiki_count, os.path.isdir(WIKI_ROOT)


def stage_index():
    idxp = os.path.join(BASE, 'rag_index.json')
    if not os.path.isfile(idxp):
        check(False, 'rag_index.json exists', idxp)
        return
    idx = json.loads(_read(idxp))
    have = {c.get('path', '').replace('\\', '/') for c in idx.get('chunks', [])}
    exp, wiki_count, has_wiki = _expected_md_sets()
    if has_wiki:
        missing = sorted(exp - have)
        stale = sorted(have - exp)
        detail = 'missing=%d stale=%d (rebuild: python rebuild_index_local.py)'
    else:
        # 无本地完整 wiki 的机器（fresh clone / CI）：只能验「仓库内 knowledge/ 都被索引到了」，
        # 索引里多出来的 wiki 文档不当地漂移（那是发布时在本机建的）
        kb_only = {p for p in exp if p.startswith('knowledge/')}
        missing = sorted(kb_only - have)
        stale = []
        detail = 'missing=%d (wiki 不在本机，跳过 stale 对比)'
    check(not missing and not stale, 'rag index covers disk docs', detail % (len(missing), len(stale)))
    if missing:
        print('       missing: %s' % ', '.join(missing[:5]))
    if stale:
        print('       stale:   %s' % ', '.join(stale[:5]))
    # 新鲜度：索引不能早于最新源文件（文档改了没重建索引 = 检索给旧知识）
    newest, newest_f, unreadable = 0, '', []
    for rel in sorted(exp):
        ap = os.path.join(BASE, 'knowledge', rel[len('knowledge/'):]) \
            if rel.startswith('knowledge/') else os.path.join(WIKI_ROOT, rel)
        if not os.path.isfile(ap):
            continue                       # 仅索引里有 → 上一步已按 stale 报出
        try:
            mt = os.path.getmtime(ap)
        except OSError as e:
            unreadable.append('%s(%s)' % (rel, e.strerror or e))   # 不静默：记下来回显
            continue
        if mt > newest:
            newest, newest_f = mt, rel
    if unreadable:
        print('       unreadable sources: %s' % ', '.join(unreadable[:3]))
    idx_mt = os.path.getmtime(idxp)
    if has_wiki:
        check(idx_mt >= newest, 'rag index not older than sources',
              'index=%s newest_src=%s%s'
              % (time.strftime('%m-%d %H:%M', time.localtime(idx_mt)),
                 time.strftime('%m-%d %H:%M', time.localtime(newest)),
                 ' (%s)' % newest_f if newest_f else ''))
    else:
        print('       (skip freshness check: %s not present)' % WIKI_ROOT)
    if has_wiki:
        rd = _read(os.path.join(BASE, 'README.md'))
        m = re.search(r'(\d+)\s*篇\s*wiki', rd)
        check(bool(m) and int(m.group(1)) == wiki_count, 'README wiki page count',
              '%s vs %d' % (m.group(1) if m else '?', wiki_count))
    else:
        print('       (skip README wiki count: %s not present)' % WIKI_ROOT)


# docstring 预算（v0.27.34 起进门禁）：工具 schema 每次会话都进上下文，膨胀 = 持续燃烧 token。
# 口径：单个 op ≤ 900 字符；全体合计 ≤ 12000 字符。长尾细节要求搬进 knowledge/（可检索）。
DOC_PER_OP_MAX = 900
DOC_TOTAL_MAX = 12000


def stage_docstring_budget():
    tree = ast.parse(_read(os.path.join(BASE, 'kb_tools.py')))
    sizes = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name.startswith('flythings_') \
                and n.name != 'flythings_kb':
            sizes.append((len(ast.get_docstring(n) or ''), n.name))
        elif isinstance(n, ast.AsyncFunctionDef) and n.name == 'flythings_kb':
            sizes.append((len(ast.get_docstring(n) or ''), n.name))
    total = sum(s for s, _ in sizes)
    over = [(s, n) for s, n in sizes if s > DOC_PER_OP_MAX]
    check(not over, 'docstring per-op <= %d chars' % DOC_PER_OP_MAX,
          'ok' if not over else '; '.join('%s=%d' % (n, s) for s, n in sorted(over, reverse=True)[:5]))
    check(total <= DOC_TOTAL_MAX, 'docstring total <= %d chars' % DOC_TOTAL_MAX,
          '%d chars in %d ops' % (total, len(sizes)))
    print('       (长尾细节请放 knowledge/：docstring 只留要点 + 检索关键词)')


def stage_deliverables(with_tests):
    for f in ('pyproject.toml', 'requirements.lock', 'install.bat', 'LICENSE',
              'scripts/smoke.py', 'scripts/sync_ui_tools.py', 'scripts/gen_manifest.py',
              'scripts/lint_silent_except.py'):
        check(os.path.isfile(os.path.join(BASE, f)), 'has %s' % f, '')
    tdir = os.path.join(BASE, 'tests')
    checks = sorted(f for f in os.listdir(tdir)) if os.path.isdir(tdir) else []
    check(bool([f for f in checks if f.startswith('test_') and f.endswith('.py')]),
          'tests/ contract cases present', ','.join(checks[:6]))


def stage_delegated(skip_smoke, with_tests):
    rc, out = _run([sys.executable, os.path.join(SUB, 'sync_ui_tools.py'), '--check'])
    check(rc == 0, 'delegated: sync_ui_tools --check',
          'ok' if rc == 0 else out.strip().splitlines()[-1][:70])
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_manifest.py'), '--check'])
    check(rc == 0, 'delegated: gen_manifest --check',
          'ok' if rc == 0 else out.strip().splitlines()[-1][:70])
    if not skip_smoke:
        rc, out = _run([sys.executable, os.path.join(SUB, 'smoke.py')])
        last = [l for l in out.strip().splitlines() if l.startswith('total=')]
        check(rc == 0, 'delegated: smoke.py', last[0] if last else 'rc=%d' % rc)
    if with_tests:
        rc, out = _run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-q'])
        tail = [l for l in out.strip().splitlines() if l.strip()][-1:]
        check(rc == 0, 'delegated: tests/ unittest', (tail[0] if tail else 'rc=%d' % rc)[:70])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip-smoke', action='store_true')
    ap.add_argument('--with-tests', action='store_true')
    a = ap.parse_args()
    print('=' * 72)
    print('FlyThings MCP consistency preflight  (BASE=%s)' % BASE)
    print('=' * 72)
    print('-' * 72)
    stage_versions()
    stage_tool_count()
    stage_platforms()
    stage_index()
    stage_docstring_budget()
    stage_deliverables(a.with_tests)
    stage_delegated(a.skip_smoke, a.with_tests)
    fails = [r for r in RESULT if not r[0]]
    print('-' * 72)
    print('total=%d  fail=%d  %s' % (len(RESULT), len(fails), 'OK' if not fails else 'FAILED'))
    for _, n, d in fails:
        print('  FAIL %s %s' % (n, d))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
