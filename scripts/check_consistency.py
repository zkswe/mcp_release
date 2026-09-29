# -*- coding: utf-8 -*-
"""发布前置一致性校验（release preflight）——v0.27.33 起为「发布前必跑」的单一闸门。

为什么要有它（检讨报告 §2.1 / §3.4）：同一件事（版本号、工具数、篇数）原先散落在
kb_tools / mcp_server / catalog.json / README / MCP_FEATURES / CHANGELOG 六处手写，
每次改动都要人肉同步，历史上反复漂移（版本号、118 vs 129 篇、checkHint 0.3.0 等）。
本脚本把「不许漂移」的关系全部机器化，并**复用**已有单一实现（不重复造检测）：

  1. 版本号四方一致：kb_tools.MCP_VERSION = pyproject [tool.flythings].mcp_version
     = "v"+pyproject.project.version+"-open"，且 README 提到当前版本
  2. 工具数六方一致：kb_tools.OP_NAMES = mcp_server docstring = README(所有「N 个工具」提法)
     = 意图闸门 catalog.json = tools_manifest.json
     （v0.27.77 起 README 精简为「一键安装 + 功能说明」，不再按固定句位查，改为扫全部提法对齐）
  3. 平台矩阵自洽：platforms.PLATFORMS 的模板目录 / bin_tools 目录真实存在；
     别名可归一；未知平台必须报错并列出支持项
  4. 知识索引新鲜度：rag_index.json 的文档集合 == 磁盘上 knowledge/(+wiki) 的 md 集合，
     且索引不早于最新源文件；wiki 篇数对着 tools_manifest.json 的 docs.wikiFiles 核
     （README 精简后不再写该数字；若又写了则两处须一致）
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
# 公开版口径（2026-09-15 起）：release 分支带 scripts/release_scope.json 与 release_gate.py，
# 本闸门据此切两处口径（master 没有该文件 → 行为完全不变）：
#   ① rag 索引只收 knowledge/（公开版不带本机 wiki）；
#   ② 额外委派 release_gate.py 做公开边界校验（剔除路径 / demo 黑名单 / 词表 / 隐私）。
RELEASE_SCOPE = os.path.isfile(os.path.join(SUB, 'release_scope.json'))


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
    # v0.27.77（钟工：README 精简为「一键安装 + 功能说明」）起：不再要求 README 里保留
    # 「FAQ 工具列表 < N」与「# 工具定义与注册（N 个）」这两处固定句位（已随精简章节删除），
    # 改为**扫出 README 里所有「N 个工具」提法并全部对齐**——少写不报警、写错任何一处必报警；
    # 工具数的唯一真源仍是 kb_tools.OP_NAMES / tools_manifest.json。
    rd = _read(os.path.join(BASE, 'README.md'))
    mentions = re.findall(r'(\d+)\s*个工具', rd)
    bad = sorted({int(x) for x in mentions} - {len(names)})
    check(bool(mentions) and not bad, 'README tool count (all mentions)',
          'README=%s vs %d（%d 处提及）'
          % (','.join(str(b) for b in bad) if bad else (mentions[0] if mentions else '?'),
             len(names), len(mentions)))
    gp = os.path.join(os.path.dirname(BASE), 'flythings_intent_gate', 'catalog.json')
    if os.path.isfile(gp):
        cnt = json.loads(_read(gp)).get('count')
        check(cnt == len(names), 'gate catalog count', '%s vs %d' % (cnt, len(names)))
    else:
        # v0.27.122：意图闸门目录不随 MCP 仓库分发（兄弟目录形态），缺失时降级为 skip + 提示，
        # 不再误报红（审查报告 §2.1 ②）。存在但漂移仍会 FAIL（上面的 count 校验）。
        check(True, 'gate catalog.json (未分发 → skip)',
              '%s 不存在；闸门不在本仓库内，跳过 count 校验（仅提示）' % gp)
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


def stage_platform_single_source():
    """平台单一来源防回归（v0.27.41 起）。

    背景：platforms.py 自称「唯一真相」，但 package_tools / test_tools 各留了一份平台表
    （前者只认 v85x 家族，不认 F133EMMC/F136/T113STDCXX；后者手抄小写元组），
    且 package_catalog.json 里 16 个平台键有 5 个在 platforms.py 里根本不存在
    → 「同一个平台名，包查询认、建工程不认」。这道闸门盯住四件事：
      1. 副本必须是**引用**而不是再抄一份（对象身份级校验，不是值相等）；
      2. package_catalog.json 的每个平台键都能被 platforms 解析（不再有“无主”平台名）；
      3. 源码里不许再出现字面量平台表（PLATFORMS/SUPPORTED_PLATFORMS/... = {...}）；
      4. 工具签名里的平台默认值不许写死字面量（要走 DEFAULT_PLATFORM / DEFAULT_BIN_PLATFORM）。
    """
    import platforms as pl
    fails = []

    # 1) 副本身份
    try:
        import package_tools as pk
        if getattr(pk, 'PLATFORM_ALIAS', None) is not pl.PACKAGE_ALIASES:
            fails.append('package_tools.PLATFORM_ALIAS 不是 platforms.PACKAGE_ALIASES（又被抄了一份）')
    except Exception as e:
        fails.append('import package_tools: %r' % e)
    try:
        import test_tools as tt
        want = tuple(p.lower() for p in pl.supported())
        if tuple(getattr(tt, 'SUPPORTED_PLATFORMS', ())) != want:
            fails.append('test_tools.SUPPORTED_PLATFORMS != platforms.supported() 小写化')
    except Exception as e:
        fails.append('import test_tools: %r' % e)
    check(not fails, 'platform single source (identity)', '; '.join(fails) if fails else 'ok')

    # 2) 包生态键全覆盖
    catp = os.path.join(BASE, 'package_catalog.json')
    if not os.path.isfile(catp):
        check(False, 'package_catalog.json exists', catp)
    else:
        unres, total = [], 0
        try:
            keys = sorted(json.loads(_read(catp)).keys())
            total = len(keys)
            for k in keys:
                if not pl.resolve(k):
                    unres.append(k)
        except Exception as e:
            unres.append('parse:%r' % e)
        check(not unres, 'package_catalog keys resolvable',
              ('未登记: %s' % ','.join(unres)) if unres else '%d keys ok' % total)

    # 3) 源码里的字面量平台表（推导式从 platforms.py 派生是合法的，不算副本）
    kw = ('PLATFORMS', 'SUPPORTED_PLATFORMS', 'PLATFORM_ALIAS', 'PLATFORM_ALIASES',
          'PACKAGE_ALIASES', 'PACKAGE_KEYS')
    lit = re.compile(r'^\s*(?:%s)\s*=\s*[\[({]' % '|'.join(kw))
    pnames = set(pl.PLATFORMS) | set(pl.PACKAGE_ONLY) | set(pl.package_keys()) \
        | set(pl.PACKAGE_ALIASES)
    quoted = ["'%s'" % n for n in pnames] + ['"%s"' % n for n in pnames]
    hits = []
    for fn in sorted(os.listdir(BASE)):
        if not fn.endswith('.py') or fn == 'platforms.py':
            continue
        lines = _read(os.path.join(BASE, fn)).splitlines()
        for i, line in enumerate(lines, 1):
            if not lit.match(line) or ' for ' in line:
                continue
            blk = '\n'.join(lines[i - 1:i + 15])
            if any(q in blk for q in quoted):
                hits.append('%s:%d' % (fn, i))
    check(not hits, 'no literal platform table in .py',
          ('重抄了平台表: %s' % ','.join(hits[:5])) if hits else 'ok')

    # 4) 工具签名里的平台默认值必须走 platforms.py 常量
    #    （位置参数默认值只能对齐到参数表末尾那几个，不能把全部 defaults 混着看）
    hard = []
    tree = ast.parse(_read(os.path.join(BASE, 'kb_tools.py')))

    def _is_literal_platform(node):
        return (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and bool(node.value.strip()))

    for n in tree.body:
        if not isinstance(n, ast.FunctionDef):
            continue
        args, defs = n.args.args, n.args.defaults
        for a, d in zip(args[len(args) - len(defs):], defs) if defs else []:
            if a.arg == 'platform' and _is_literal_platform(d):
                hard.append('%s(platform=%r)' % (n.name, d.value))
        for a, d in zip(n.args.kwonlyargs, n.args.kw_defaults):
            if a.arg == 'platform' and _is_literal_platform(d):
                hard.append('%s(platform=%r)' % (n.name, d.value))
    check(not hard, 'platform defaults via platforms.py',
          ('写死默认平台: %s' % ','.join(hard[:5])) if hard else 'ok')

    # 5) 关键语义（真实平台不再被判为“不存在”）
    sem = []
    try:
        if pl.package_key('F135') != 'f136':
            sem.append('package_key(F135)!=f136')
        if pl.package_key('F133EMMC') != 'f133emmc':
            sem.append('package_key(F133EMMC)!=f133emmc')
        r = pl.resolve('z6s')
        if not (r and r.get('packageOnly') and not r.get('buildable')):
            sem.append('resolve(z6s) 未标 packageOnly')
        try:
            pl.validate('z6s')
            sem.append("validate('z6s') 未报错")
        except ValueError as e:
            if '模板' not in str(e):
                sem.append('validate(z6s) 未说明缺模板')
    except Exception as e:
        sem.append('exc %r' % e)
    check(not sem, 'platform semantics (alias/package-only)',
          ','.join(sem) if sem else 'ok')


def _expected_md_sets():
    """按 rebuild_index_local.py 的口径推导索引应包含的文档集合（相对路径，'/' 分隔）。"""
    kb_dir = os.path.join(BASE, 'knowledge')
    known, expected = set(), set()
    if os.path.isdir(kb_dir):
        for r, _, fs in os.walk(kb_dir):
            # 与 rebuild_index_local.py 同口径：inbox/_reports/_logs 不入索引
            _parts = os.path.relpath(r, kb_dir).replace('\\', '/').split('/')
            if any(p in ('inbox', '_reports', '_logs') for p in _parts):
                continue
            for f in fs:
                if f.endswith('.md'):
                    rel = os.path.relpath(os.path.join(r, f), kb_dir).replace('\\', '/')
                    known.add(rel)
                    expected.add('knowledge/' + rel)
    wiki_count = 0
    if os.path.isdir(WIKI_ROOT) and not RELEASE_SCOPE:
        for r, _, fs in os.walk(WIKI_ROOT):
            for f in fs:
                if f.endswith('.md'):
                    rel = os.path.relpath(os.path.join(r, f), WIKI_ROOT).replace('\\', '/')
                    if rel in known:
                        continue
                    expected.add(rel)
                    wiki_count += 1
    return expected, wiki_count, os.path.isdir(WIKI_ROOT) and not RELEASE_SCOPE


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
        detail_args = (len(missing), len(stale))
    else:
        # 无本地完整 wiki 的机器（fresh clone / CI / 公开版）：只能验「仓库内 knowledge/ 都被索引到了」，
        # 索引里多出来的 wiki 文档不当地漂移（那是发布时在本机建的）
        kb_only = {p for p in exp if p.startswith('knowledge/')}
        missing = sorted(kb_only - have)
        stale = []
        if RELEASE_SCOPE:
            detail = 'missing=%d（公开版口径：索引只收 knowledge/，不含本机 wiki）'
        else:
            detail = 'missing=%d (wiki 不在本机，跳过 stale 对比)'
        detail_args = (len(missing),)
    check(not missing and not stale, 'rag index covers disk docs', detail % detail_args)
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
        # v0.27.77 起 README 精简，不再写「N 篇 wiki」：该事实改为对着
        # tools_manifest.json（gen_manifest.py 生成的机器可读快照）的 docs.wikiFiles 核；
        # README 若又重新写了该数字，两处口径必须一致（防再次手写漂移）。
        rd = _read(os.path.join(BASE, 'README.md'))
        m = re.search(r'(\d+)\s*篇\s*wiki', rd)
        mp = os.path.join(BASE, 'tools_manifest.json')
        man = json.loads(_read(mp)).get('docs', {}).get('wikiFiles') \
            if os.path.isfile(mp) else None
        check(man == wiki_count and (not m or int(m.group(1)) == wiki_count),
              'wiki page count (manifest/docs; README 若写则须一致)',
              'manifest=%s README=%s real=%d'
              % (man, m.group(1) if m else '（未写）', wiki_count))
    else:
        print('       (skip wiki count: %s not present)' % WIKI_ROOT)


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
    gate = os.path.join(SUB, 'release_gate.py')
    if RELEASE_SCOPE and os.path.isfile(gate):
        rc, out = _run([sys.executable, gate])
        tail = [l for l in out.strip().splitlines() if l.startswith('total=')]
        check(rc == 0, 'delegated: release_gate.py (公开边界)',
              tail[0] if tail else 'rc=%d' % rc)
    rc, out = _run([sys.executable, os.path.join(SUB, 'sync_ui_tools.py'), '--check'])
    check(rc == 0, 'delegated: sync_ui_tools --check',
          'ok' if rc == 0 else out.strip().splitlines()[-1][:70])
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_manifest.py'), '--check'])
    check(rc == 0, 'delegated: gen_manifest --check',
          'ok' if rc == 0 else out.strip().splitlines()[-1][:70])
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_hardware_doc.py'), '--check'])
    check(rc == 0, 'delegated: gen_hardware_doc --check',
          'ok' if rc == 0 else out.strip().splitlines()[-1][:70])
    # 知识库门禁（v0.27.125 起）：front-matter 合规 / kb_index 新鲜（源哈希）/ inbox 不进索引 /
    # verified 必须有证据或显式 needs_evidence —— 「自动生长」没有门禁就会自动腐化。
    rc, out = _run([sys.executable, os.path.join(SUB, 'check_kb.py')])
    kb_tail = [l for l in out.strip().splitlines()
               if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: check_kb.py (知识库门禁)',
          (kb_tail[0] if kb_tail else 'rc=%d' % rc)[:70])
    if not skip_smoke:
        rc, out = _run([sys.executable, os.path.join(SUB, 'smoke.py')])
        last = [l for l in out.strip().splitlines() if l.startswith('total=')]
        check(rc == 0, 'delegated: smoke.py', last[0] if last else 'rc=%d' % rc)
    # 检索质量回归（v0.27.94 起进门禁）：16 条真实问法必须一次命中权威文档 + 11 条对照组防调参副作用。
    # 无需向量模型也能跑（自动降级 BM25，实测同样 16/16），耗时 ~4s。
    rc, out = _run([sys.executable, os.path.join(SUB, 'check_retrieval.py')])
    last = [l for l in out.strip().splitlines()
            if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: check_retrieval.py',
          (last[0] if last else 'rc=%d' % rc)[:70])
    if with_tests:
        rc, out = _run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-q'])
        tail = [l for l in out.strip().splitlines() if l.strip()][-1:]
        check(rc == 0, 'delegated: tests/ unittest', (tail[0] if tail else 'rc=%d' % rc)[:70])
        # 用例数不许手写漂移（README 写 95 而实跳 122 过就不对了）
        # v0.27.77 起主 README 精简（不再写用例数）：用例数的承载处改为 tests/README.md
        # （它写「当前规模：**N 项**」）；主 README 若又写了该数量也一并核对。
        m = re.search(r'^Ran (\d+) tests', out, re.M)
        real = int(m.group(1)) if m else -1
        nt = re.search(r'当前规模：\*\*(\d+)\s*项\*\*',
                       _read(os.path.join(BASE, 'tests', 'README.md')))
        nr = re.search(r'(\d+)\s*项契约用例', _read(os.path.join(BASE, 'README.md')))
        check(bool(nt) and int(nt.group(1)) == real and (not nr or int(nr.group(1)) == real),
              'test count matches real run（tests/README.md）',
              'tests/README=%s README=%s real=%s'
              % (nt.group(1) if nt else '?', nr.group(1) if nr else '（未写）',
                 m.group(1) if m else '?'))


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
    stage_platform_single_source()
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
