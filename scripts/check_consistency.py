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
import struct
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUB = os.path.join(BASE, 'scripts')
if BASE not in sys.path:
    sys.path.insert(0, BASE)

RESULT = []
WIKI_ROOT = (os.path.join(BASE, 'wiki', 'flythings')          # 随仓 wiki（open 版自带）
             if os.path.isdir(os.path.join(BASE, 'wiki', 'flythings'))
             else os.path.join(os.path.expanduser('~'), '.openclaw', 'workspace', 'wiki', 'flythings'))
# 公开版口径（2026-09-15 起）：release 分支带 scripts/release_scope.json 与 release_gate.py，
# 本闸门据此切两处口径（master 没有该文件 → 行为完全不变）：
#   ① rag 索引只收 knowledge/（公开版不带本机 wiki）；
#   ② 额外委派 release_gate.py 做公开边界校验（剔除路径 / demo 黑名单 / 词表 / 隐私）。
RELEASE_SCOPE = os.path.isfile(os.path.join(SUB, 'release_scope.json'))

# Windows 控制台默认 GBK：被委派脚本的回显里若带 GBK 编不出的字符（实测 U+022B，来自
# 某处乱码文案），`print` 会抛 UnicodeEncodeError **把失败本身藏掉**（2026-10-04 实测：
# 门禁在第一条 FAIL 处崩，后面 60+ 条判据一条都没跑到）。errors='replace' 保住报告，
# 不改变其它平台行为（那里本来就编得出）。
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')


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


def _run(args, timeout=900):
    try:
        r = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           cwd=BASE, timeout=timeout)
        return r.returncode, r.stdout.decode('utf-8', 'replace')
    except subprocess.TimeoutExpired as e:      # 超时要说清"跑了多久"，否则只看到一句 TimeoutExpired
        out = (e.stdout or b'').decode('utf-8', 'replace') if e.stdout else ''
        return 124, '%s\n[TIMEOUT] %s 超过 %ss 未结束' % (out, ' '.join(args[:3]), timeout)
    except Exception as e:                      # 解释器/脚本缺失 → 视为失败并回显
        return 1, repr(e)


def _git_tracked(relpath):
    """`relpath` 是否已登记进 git 索引（= fresh clone / CI 上会不会有它）。

    为什么门禁要问这个（2026-10-03 实测）：门禁与 CI 跑的是**公开仓库形态**。一个文件
    只在工作区存在、没进 git，就等于"这套闸门只在这台机器上成立"——本轮
    `scripts/run_tests.py` / `audit_design_spec.py` / `gen_unverified_report.py` /
    `fun_capabilities.json` 都处于这个状态（被门禁调用/引用却没入库）。
    查不到 git（无 git / 不是仓库 / 超时）时返回 None，调用方**跳过该判据**并提示，
    不把"查不到版本控制"伪造成"没入库"。
    """
    try:
        r = subprocess.run(['git', 'ls-files', '--error-unmatch', '--', relpath],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           cwd=BASE, timeout=20)
        return r.returncode == 0
    except Exception:
        return None


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
    # v0.27.77（现场反馈：README 精简为「一键安装 + 功能说明」）起：不再要求 README 里保留
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
    # 2026-10-05（本批实测抓到）：`knowledge/**` 才是**用户与 AI 实际读的那一面**，却在
    # 「N 个工具」这个数字上一直没人对账 —— 工具面本批 48 → 42，README / pyproject 描述 /
    # manifest / 意图目录五方都改了，只有 `knowledge/devflow/quickstart.md` 还写着 48（已改）。
    # 归档类（CHANGELOG / VERSION_HISTORY / features_recent / REVIEW-* / TODO）**不在 knowledge/ 下**，
    # 它们是**带日期的历史快照**，保留旧数字是对的 → 本判据只扫 `knowledge/**/*.md`，不碰历史。
    kb_bad = []
    for root, dirs, files in os.walk(os.path.join(BASE, 'knowledge')):
        dirs[:] = [d for d in dirs if not d.startswith('_')]
        for fn in sorted(files):
            if not fn.endswith('.md'):
                continue
            p = os.path.join(root, fn)
            hit = sorted({int(x) for x in re.findall(r'(\d+)\s*个工具', _read(p))}
                         - {len(names)})
            if hit:
                kb_bad.append('%s=%s' % (os.path.relpath(p, BASE).replace('\\', '/'),
                                         ','.join(str(h) for h in hit)))
    check(not kb_bad, 'knowledge 页工具数（所有「N 个工具」提法）',
          'ok' if not kb_bad else ('%s vs %d' % ('; '.join(kb_bad), len(names))))
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

    # pyproject.description 里的「N 个 op」也要机器化（v0.27.173 实测：它写着 44，而真值是 48）。
    # 它是包元数据 / 市场首屏文案，漂移会直接被搜到 —— 属于「必须派生」的数字，不是文案自由。
    pp = os.path.join(BASE, 'pyproject.toml')
    desc = ''
    try:
        import tomllib
        desc = tomllib.loads(_read(pp)).get('project', {}).get('description', '')
    except Exception:
        m2 = re.search(r'^description\s*=\s*"(.*?)"', _read(pp), re.M)
        desc = m2.group(1) if m2 else ''
    md = re.search(r'(\d+)\s*个\s*op', desc)
    check(bool(md) and int(md.group(1)) == len(names), 'pyproject description op count',
          '"%s 个 op" vs %d' % (md.group(1) if md else '未写', len(names)))


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


# 架构 → ELF (class, e_machine) 期望值（v0.27.179，B4）。
# 用 ELF 头判定「这个二进制是不是这个平台的」，而不是靠目录名或人记得。
ELF_CLASS = {1: 'ELF32', 2: 'ELF64'}
ELF_MACHINE = {40: 'ARM', 243: 'RISC-V', 183: 'AARCH64', 8: 'MIPS', 3: 'x86'}
ARCH_ELF = {'arm': (1, 40), 'riscv64': (2, 243)}


def _elf_head(path):
    """读 ELF 头 → (class, e_machine, endian)；不是 ELF 回 None。"""
    with open(path, 'rb') as fh:
        b = fh.read(64)
    if len(b) < 52 or b[:4] != b'\x7fELF':
        return None
    fmt = '<' if b[5] == 1 else '>'
    return (b[4], struct.unpack(fmt + 'H', b[18:20])[0], b[5])


def stage_bin_tools():
    """`bin_tools/<平台>/<工具>` 必须是**该平台架构**的 ELF（B4 防错配）。

    为什么：设备端 ELF 架构不对会**静默失败**（push 上去跑不起来、或打崩应用），
    而目录名看不出来。`bin_tools/z235x/README.md` 早写着「禁止拿其它平台的 ELF 顶替」——
    这道门就是那句话的机器化。同时钉住「按平台放二进制」这个设计：
    相同内容由 git 天然去重（同一 blob），**不需要**再做一份「二进制 + 平台映射」的间接层。
    """
    import platforms as pl
    root = os.path.join(BASE, 'bin_tools')
    bad, checked = [], {}
    for plat, meta in pl.PLATFORMS.items():
        d = os.path.join(root, meta.get('binTool', ''))
        if not os.path.isdir(d):
            continue                                   # 目录缺失由 stage_platforms 管
        want = ARCH_ELF.get(meta.get('arch'))
        for f in sorted(os.listdir(d)):
            fp = os.path.join(d, f)
            if not os.path.isfile(fp) or f.endswith('.md'):
                continue                               # 说明文件不算工具
            head = _elf_head(fp)
            rel = 'bin_tools/%s/%s' % (meta['binTool'], f)
            if head is None:
                bad.append('%s(非 ELF)' % rel)
                continue
            cls, mach, endian = head
            checked.setdefault(meta['arch'], 0)
            checked[meta['arch']] += 1
            if want and (cls, mach) != want:
                bad.append('%s(%s/%s，期望 %s/%s)' % (
                    rel, ELF_CLASS.get(cls, cls), ELF_MACHINE.get(mach, mach),
                    ELF_CLASS[want[0]], ELF_MACHINE[want[1]]))
            if endian != 1:
                bad.append('%s(非小端)' % rel)
    check(not bad, 'bin_tools 各平台 ELF 架构匹配',
          'ok（%s）' % '，'.join('%s×%d' % (k, v) for k, v in sorted(checked.items()))
          if not bad else '；'.join(bad[:4]))


# 平台 arch 白名单（v0.27.178）。新增架构必须显式加进来——这就是这道门的全部意义。
PLATFORM_ARCHES = ('arm', 'riscv64')


def stage_platform_arch():
    """平台 `arch` 只允许白名单值（v0.27.178）。

为什么加：`platforms.py` 的 `arch` 是**人工维护、原先零校验**的字段，实测写错过两处——
    `F135` 写成 `arm`（实际与 F133 同核 C906，工具链 `riscv64-unknown-linux-musl-g++`）、
    `F133` 写成 `riscv32`（工具链与 isa `rv64imafdcvu` 都是 64 位）。
这个错会经 `tools_manifest.json` 原样传给 AI（它据此判架构兼容性：ARM 的 .so 在 RISC-V 上
根本加载不了），所以按「白名单 + 显式登记」拦，而不是靠人记得。
    """
    try:
        sys.path.insert(0, BASE)
        import platforms as pl
    except Exception as e:
        check(False, 'platforms 可加载', '%s: %s' % (type(e).__name__, e))
        return
    bad = sorted('%s=%r' % (k, v.get('arch')) for k, v in pl.PLATFORMS.items()
                 if v.get('arch') not in PLATFORM_ARCHES)
    check(not bad, 'platforms.arch 白名单（%s）' % ', '.join(PLATFORM_ARCHES),
          'ok（%d 平台）' % len(pl.PLATFORMS) if not bad else '异常值: %s' % '; '.join(bad))


# MCP 依赖的外部 CLI 必须随包（v0.27.199）。
# 起因（现场反馈 2026-10-06）：公开版把 `toolchain/fun.exe`（38 MB）当「二进制命中词表」删掉了。
# 客户端机器上没有 `C:\zkswe\fun`、也没有 `FLYTHINGS_FUN_DIR`，`project_tools._tool_dir()`
# 只能命中包内 `toolchain/`（只剩 fui.exe）→ `fun.exe` 退化成裸名 → 构建流程直接回
# 「fun.exe 未找到」，AI 复述成「缺少 fun，编译不了」。
# 判据：`toolchain/fui.exe`（json↔ftu）与 `toolchain/fun.exe`（依赖/编译/推送/出包）两者都要在，
# 且**必须已入库**（只在工作树里 = 客户 clone 拿不到，等于没有）。
# ⚠️ 二进制**不参与内容词表扫描**（偶然字节、不可编辑）——只做路径级存在性检查，
#    遇到词表命中要豁免并登记理由，**不许再靠删文件过闸**（PUBLISH.md §5）。
REQUIRED_CLI_PRODUCTS = (
    ('toolchain/fui.exe', 'json↔ftu（fui pack / unpack）'),
    ('toolchain/fun.exe', '依赖/编译/推送/出包（fun install|build|launch|pack）'),
)


def stage_cli_products():
    """随包 CLI 产物存在且已入库（v0.27.199）。"""
    missing, untracked = [], []
    for rel, why in REQUIRED_CLI_PRODUCTS:
        if not os.path.isfile(os.path.join(BASE, rel)):
            missing.append('%s（%s）' % (rel, why))
            continue
        rc, _ = _run(['git', 'ls-files', '--error-unmatch', rel])
        if rc != 0:
            untracked.append(rel)
    bad = missing or untracked
    detail = []
    if missing:
        detail.append('缺失: %s' % '；'.join(missing))
    if untracked:
        detail.append('未入库（客户 clone 拿不到）: %s' % '、'.join(untracked))
    check(not bad, '随包 CLI 产物齐备且已入库（%s）'
          % '、'.join(r for r, _ in REQUIRED_CLI_PRODUCTS),
          'ok' if not bad else '；'.join(detail) + ' —— 客户机会直接报「缺少 fun/fui，编译不了」')


# 资料里不得出现的内部人名（v0.27.178）。
# 口径（2026-10-02）：资料的价值是「结论 + 依据 + 日期」，不是「谁说的」——
# 「<人名> 2026-09-12 确认」这类口语会让 AI 把口头确认当成权威依据，对外也不专业。
# 换成中性主语（需求方 / 现场反馈）即可，日期与结论照留。
# ⚠️ 名单**写成 unicode 转义**：本文件也在扫描范围内，写明文会被自己命中（自指）。
FORBIDDEN_NAMES = ('\u6c9b\u54e5', '\u949f\u5de5')
SCAN_EXT = ('.md', '.json', '.py', '.txt', '.cmd', '.bat', '.cpp', '.h', '.cc')
SCAN_SKIP_DIR = {'__pycache__', '.git', 'temp', 'models', 'node_modules'}


def stage_no_people_names():
    """资料里不得出现内部人名口语（v0.27.178）。"""
    hits = []
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in SCAN_SKIP_DIR]
        for f in files:
            if not f.endswith(SCAN_EXT):
                continue
            p = os.path.join(root, f)
            if os.path.getsize(p) > 4_000_000:
                continue
            rel = os.path.relpath(p, BASE).replace('\\', '/')
            try:
                t = io.open(p, encoding='utf-8', errors='replace').read()
            except OSError as e:
                hits.append('%s(读失败:%s)' % (rel, type(e).__name__))
                continue
            n = sum(t.count(x) for x in FORBIDDEN_NAMES)
            if n:
                hits.append('%s(%d)' % (rel, n))
    check(not hits, '资料不含内部人名',
          'ok' if not hits else '；'.join(hits[:4]))


# IDE 本地状态 / 工具生成物：不得入库（v0.27.179，B6 出库）。
# 判据：带本机信息（language.settings.xml 的 env-hash、core.runtime.prefs 的 line.separator）
# 或由工具重新生成（.deps.lock 由 fun install 解析）。工程必需的三件**保留**：
# .project / .cproject（IDE 打开与编译）、.settings/{com.zksw.flythings.easyui.prefs,
# org.eclipse.core.resources.prefs}（resolution 来源 / UTF-8 编码）。
IDE_LOCAL_BASENAMES = ('language.settings.xml', 'org.eclipse.core.runtime.prefs', '.deps.lock')
# 编辑器 / 本机产物（按**路径段或后缀**判，不按文件名）：这类不只是噪音 ——
# 发布裁剪分支 `git rm` 目录时，已跟踪的隐藏文件会残留并跟着发布包走（PUBLISH.md §6.1）。
IDE_LOCAL_DIRS = ('.vscode', '.idea', '__pycache__')
IDE_LOCAL_SUFFIX = ('.pyc', '.swp', '.swo', '.iml')


def stage_no_ide_local_files():
    """IDE 本地状态、编辑器与本机产物不得入库（B6 出库后防回退）。"""
    rc, out = _run(['git', 'ls-files'])
    if rc != 0:
        check(False, 'IDE 本地状态文件未入库', 'git ls-files 失败（rc=%d）' % rc)
        return
    files = [f.strip() for f in out.splitlines() if f.strip()]
    hits = [f for f in files if os.path.basename(f) in IDE_LOCAL_BASENAMES]
    check(not hits, 'IDE 本地状态文件未入库（%s）' % '、'.join(IDE_LOCAL_BASENAMES),
          'ok' if not hits else '；'.join(hits[:4]))
    bad = [f for f in files
           if any('/%s/' % d in '/' + f for d in IDE_LOCAL_DIRS)
           or f.endswith(IDE_LOCAL_SUFFIX)]
    check(not bad, '编辑器/本机产物未入库（%s）'
          % '、'.join(['%s/' % d for d in IDE_LOCAL_DIRS] + list(IDE_LOCAL_SUFFIX)),
          'ok（%d 文件已核）' % len(files) if not bad else '；'.join(bad[:4]))


def _expected_md_sets():
    """按 `kb_index_roots.py`（索引范围唯一真源）推导索引应包含的**仓库真源**文档集合。

    这里**不再自己写遍历口径**——以前是照着 rebuild_index_local.py "同口径"抄一遍，
    给检索加一类文档要改两处、漏一处就漂移（2026-10-02 收编）。

    ⚠️ **wiki 不进这个集合**（2026-10-05 需求方口径）：wiki 是**维护期用的源数据**
    （让 `knowledge/` 整理页有更精准的依据），**不是给 AI 检索的用户面**。它进了
    `rag_index` 有两个后果，都已实测：
      ① **污染检索回归这个量具**：语料里多出 122~129 篇镜像页后，全局 top-1 从 76.5%
         掉到 ~69%，而且**不是排序退化** —— 把 wiki 裁掉重测仍是 69.4%（没回升）；
      ② AI 拿到的是镜像页而非我们整理过的页（`multimedia/video.md` vs
         `knowledge/media/media-capability-index.md`），与"整理页才是权威"相冲突。
    所以本函数只返回**仓库真源**文档；`stage_index` 据此把"索引里混进 wiki 页"判成 stale。
    """
    sys.path.insert(0, BASE)
    import kb_index_roots as bir
    expected = set(bir.repo_rel_docs(BASE))
    wiki_count = 0
    if os.path.isdir(WIKI_ROOT) and not RELEASE_SCOPE:
        for r, _, fs in os.walk(WIKI_ROOT):
            for f in fs:
                if f.endswith('.md'):
                    wiki_count += 1          # 只统计篇数，**不并入 expected**（见函数说明）
    return expected, wiki_count, os.path.isdir(WIKI_ROOT) and not RELEASE_SCOPE


def stage_index():
    idxp = os.path.join(BASE, 'rag_index.json')
    if not os.path.isfile(idxp):
        check(False, 'rag_index.json exists', idxp)
        return
    idx = json.loads(_read(idxp))
    have = {c.get('path', '').replace('\\', '/') for c in idx.get('chunks', [])}
    exp, wiki_count, has_wiki = _expected_md_sets()
    missing = sorted(exp - have)
    # `stale` = 索引里有、但不在「仓库真源」里的东西。**wiki 页混进来也会落在这里** ——
    # 那正是要拦的（镜像不该被索引，见 `_expected_md_sets` 的说明）。
    stale = sorted(have - exp)
    hint = ''
    if has_wiki and any(not p.startswith(('knowledge/', 'components/', 'packages/', 'kb_local/'))
                        for p in stale):
        hint = '；**stale 里是 wiki 页 = 镜像被索引了 → 跑 `rebuild_index_local.py --repo-only`**'
    check(not missing and not stale, 'rag index covers disk docs',
          'missing=%d stale=%d (rebuild: python rebuild_index_local.py%s)'
          % (len(missing), len(stale), hint))
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



def stage_package_manifest():
    """打包清单完整性：`pyproject.toml` 的 py-modules **== 根目录所有 .py**（v0.27.177）。

为什么（B5 实测 2026-10-02）：根目录平铺了 25 个模块，而 py-modules 只手写了 10 个——
漏掉 `mcp_extras`（mcp_server 直接 import）、`mcp_server_flat`（文档里的另一个入口）、
    `platforms` 等 15 个。`pip install .` 出来的包会缺模块、运行时 ImportError。
根因是「清单靠人维护」；本阶段把它变成比对，漏一个直接红。
    """
    pp = os.path.join(BASE, 'pyproject.toml')
    if not os.path.isfile(pp):
        check(False, 'has pyproject.toml', pp)
        return
    src = _read(pp)
    m = re.search(r'py-modules\s*=\s*\[(.*?)\]', src, re.S)
    if not m:
        check(False, 'pyproject py-modules 存在', '没找到 py-modules 表')
        return
    declared = set(re.findall(r'"([A-Za-z0-9_]+)"', m.group(1)))
    on_disk = {f[:-3] for f in os.listdir(BASE)
               if f.endswith('.py') and os.path.isfile(os.path.join(BASE, f))}
    missing = sorted(on_disk - declared)
    extra = sorted(declared - on_disk)
    check(not missing and not extra, 'py-modules == 根目录 .py 集合',
          ('漏登记: %s' % ', '.join(missing[:5])) if missing
          else (('多登记（文件已不在）: %s' % ', '.join(extra[:5])) if extra
                else '%d 个模块全部登记' % len(on_disk)))


# 已不在当前工具链的历史命令名（清空处理，v0.27.178）。
# 判据：仓库里找不到任何实体（可执行 / 模块 / 目录），只剩名字。
DEPRECATED_CLI = ('fyx', 'fuse')


def stage_cli_names():
    """旧 CLI 名不得出现在**常驻契约面**（v0.27.178）。

口径（2026-10-02）：名字只有指向**真实存在**的东西才该留。\u0060fyx\u0060 在本仓库没有任何
实体（\u0060find -iname \'*fyx*\'\u0060 为空），却被登记进 \u0060tools_manifest.json\u0060 的名词表、并当作
    op 参数名 \u0060with_fyx\u0060——AI 读到会以为还有这条命令可调。

范围只限「会被 AI 当命令用」的两处：manifest 名词表、op 签名参数名。**不含知识文档**——
    \u0060knowledge/devflow/cli-fun-toolchain.md\u0060 里的 fuse 痕迹是**兼容识别知识**（老工程为什么
带 \u0060.fuse/\u0060 产物目录、\u0060FUSE_BUILD\u0060 宏、\u0060~/.fuse\u0060 注册表），删了反而无法诊断。
区别是：**要认识的老形态**保留，**可调的命令**清空。
    """
    man = json.loads(_read(os.path.join(BASE, 'tools_manifest.json')) or '{}')
    cli = set((man.get('cli') or {}).keys())
    bad = sorted(cli & set(DEPRECATED_CLI))
    check(not bad, 'cliNames 不登记已废弃命令名',
          ('ok（%s）' % ', '.join(sorted(cli))) if not bad
          else '登记了旧名: %s' % ', '.join(bad))
    tree = ast.parse(_read(os.path.join(BASE, 'kb_tools.py')))
    hits = []
    for n in tree.body:
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        a = n.args
        names = [x.arg for x in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)]
        for nm in names:
            if any(d in nm.lower() for d in DEPRECATED_CLI):
                hits.append('%s(%s)' % (n.name, nm))
    check(not hits, 'op 签名参数名不含已废弃 CLI 名',
          'ok（%d 个 op）' % sum(1 for n in tree.body
                                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                                and n.name.startswith('flythings_')) if not hits
          else '；'.join(hits[:3]))


def stage_kb_authority():
    """权威口径注册表（knowledge/authority_map.json）自检（v0.27.177）。

钉住最要紧的一条：canonical 必须**落在检索范围内**—— 存在但不在索引里等于没有
    （AI 拿到指针也搜不到）。另外查别名撞车与 ops 存在性。
    """
    try:
        sys.path.insert(0, BASE)
        import kb_authority as au
    except Exception as e:
        check(False, 'kb_authority 可加载', '%s: %s' % (type(e).__name__, e))
        return
    try:
        errs = au.validate()
        n = len(au.concepts())
    except Exception as e:
        check(False, 'op 权威口径注册表自检', '%s: %s' % (type(e).__name__, e))
        return
    check(not errs, 'op 权威口径注册表自检（canonical 在检索范围内 / 别名不撞车 / ops 存在）',
          '%d 概念 ok' % n if not errs else '; '.join(errs[:3]))


# ── selfcheck 分区份数必须**派生**（2026-10-03）──────────────────────────────
# 为什么单列：分区从 9 加到 10、11，但 README / selfcheck_tools 的文案 / tests/README /
# 知识页一直写「九分区」—— 根因是**没有一处派生**，加分区时没人会想起散文也要跟着改。
# 手法与 stage_tool_count（工具数六方一致）相同：**只认数字与真源一致，不管措辞**。
# 真源 = selfcheck_tools.SECTIONS（返回体 summary.total 也是由它派生）。
_SELFCHECK_COUNT_FILES = (
    'README.md',
    'tests/README.md',
    'selfcheck_tools.py',
    'knowledge/devflow/selfcheck-and-bugreport.md',
)
# 命中行含本标记则跳过 —— 给「历史实测记录」留的出口（那时真值就是 9，改它等于篡改证据）。
# 用 HTML 注释写在证据行上：人看不见，门禁看得见，grep 得到。
_SELFCHECK_COUNT_EXEMPT = '分区数豁免'
_CN_NUM = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7,
           '八': 8, '九': 9, '十': 10, '十一': 11, '十二': 12, '十三': 13}
_SELFCHECK_COUNT_RE = re.compile(r'(\d+|[一二三四五六七八九十]+)\s*个?\s*分区')


def stage_selfcheck_sections():
    """活文档里的「N 个分区」必须等于 len(SECTIONS) —— 份数不许手写漂移。"""
    try:
        import selfcheck_tools as _sc
        real = len(_sc.SECTIONS)
    except Exception as e:                      # 真源不可用 = 这条对账做不了，不许静默放过
        check(False, 'selfcheck 分区份数（SECTIONS 可加载）', '%s: %s' % (type(e).__name__, e))
        return
    bad, seen = [], 0
    for rel in _SELFCHECK_COUNT_FILES:
        p = os.path.join(BASE, rel)
        if not os.path.isfile(p):
            bad.append('%s(文件不存在)' % rel)
            continue
        for i, line in enumerate(_read(p).splitlines(), 1):
            if _SELFCHECK_COUNT_EXEMPT in line:
                continue
            for m in _SELFCHECK_COUNT_RE.finditer(line):
                tok = m.group(1)
                n = int(tok) if tok.isdigit() else _CN_NUM.get(tok)
                # 只认 ≥2：「(采集)一个分区」「下一个分区」这类是**单数习惯用法**，不是份数声明
                # （selfcheck 只有一个分区也没有意义）。这条收窄写在门禁里，不靠人记。
                if n is None or n < 2:
                    continue
                seen += 1
                if n != real:
                    bad.append('%s:%d 写「%s」而真值 %d' % (rel, i, m.group(0).strip(), real))
    check(not bad,
          'selfcheck 分区份数与 SECTIONS 一致（真值 %d / 命中 %d 处）' % (real, seen),
          '；'.join(bad[:4]) if bad else 'ok')


# 字库字节数的唯一真源 = 仓库里的字体文件本身；活文档里报的数必须等于它。
# 为什么单独钉（2026-10-03 实测）：`device-deploy-budget.md` 把**同一个**
# `zkswe-hans-full.ttf` 一处写 7.5MB、另一处写 7.4MB（真实 7,567,300 B），且 KB/MiB 单位混用 ——
# 而"字库是不是最大头"正是这条部署预算结论的支点。数字漂了，结论看着还成立，最难发现。
_FONT_FILES = ('zkswe-hans-common.ttf', 'zkswe-hans-full.ttf', 'zkswe-hans-multi.ttf')
# 两处都声明字库体积（2026-10-03 实测两页各写一套、且其中一页是上一版字库的旧值）
_FONT_DOCS = ('knowledge/devflow/device-deploy-budget.md',
              'knowledge/devflow/custom-font-config.md')


def stage_font_sizes():
    """活文档里声明的字库字节数 == 字体文件实际大小。"""
    bad, seen = [], 0
    for name in _FONT_FILES:
        fp = os.path.join(BASE, 'components', 'fonts', 'fonts', name)
        if not os.path.isfile(fp):
            bad.append('%s(字体文件不存在)' % name)
            continue
        real = os.path.getsize(fp)
        hit = False
        for rel in _FONT_DOCS:
            p = os.path.join(BASE, rel)
            if not os.path.isfile(p):
                bad.append('%s(文件不存在)' % rel)
                continue
            # 允许「名字 → 数字」之间夹着表格分隔符/加粗/括号（正文式 `**N B**` 与
            # 表格式 `| **N B**（…）` 都要能匹配）；惰性 + 上限，避免吃到后面别的数字。
            m = re.search(r'`%s`[^0-9\n]{0,24}?(\d+)\s*B' % re.escape(name), _read(p))
            if not m:
                bad.append('%s 未在 %s 里给出字节数（改了措辞请同步本门禁的匹配式）' % (name, rel))
                continue
            hit = True
            if int(m.group(1)) != real:
                bad.append('%s 在 %s 写 %s B 而实际 %d B' % (name, rel, m.group(1), real))
        if hit:
            seen += 1
    check(not bad, '字库字节数与字体文件一致（两页 / 命中 %d 处）' % seen,
          '；'.join(bad[:3]) if bad else 'ok')


def stage_json_registries():
    """根目录所有 `*.json` 必须能解析 —— 报**文件 + 行列**，不报含糊的"空"。

    为什么单列（2026-10-03）：`features_recent.json` 被写坏过**三次**（字符串里用了未转义的
    ASCII 双引号），而每次都是在 smoke 的 `MCP_FEATURES[0] mentions version` 那条上暴露的 ——
    那条检查的本意是"版本写没写"，只能间接看出"读取失败"，还得另写脚本定位。
    根目录这些 .json 都是**唯一真源或派生快照**，坏一个就是某项能力静默失效
    （`op_spec.json` 坏 → 契约全拉不到；`error_codes.json` 坏 → 失败返回体没有 action）。
    一次把语法钉住，代价是几百毫秒。

    2026-10-03 加两条**同源的性质**（都是本轮实测踩出来的，见 REVIEW-2026-10-03.md）：
      ① **必须受版本控制**：门禁/CI 跑的是「fresh clone / checkout」形态，一个 untracked 的
         注册表+只引用它的代码，等于**只在这台机器上成立**（本轮 `fun_capabilities.json`
         被 `op_spec.json` 引用却没入库）。判据用 `git ls-files`，不靠人记。
      ② **注册表里反引号引用的 .json 必须存在**（反引号包起来的 `x.json` 是**指针**，
         删了文件就该红）——只认反引号，避免把散文里的泛称（"xxx.json"）误判成指针。
    """
    skip = ('rag_index.json',)          # 4MB 生成物（内容由 rebuild 保证），跳过省时间
    bad, n, untracked, root_jsons = [], 0, [], []
    try:
        names = sorted(os.listdir(BASE))
    except OSError as e:
        check(False, 'root *.json registries parse', '列目录失败：%s' % e)
        return
    for f in names:
        if not f.endswith('.json') or f in skip:
            continue
        p = os.path.join(BASE, f)
        if not os.path.isfile(p):
            continue
        n += 1
        root_jsons.append(f)
        if not _git_tracked(f):
            untracked.append(f)
        try:
            json.loads(_read(p))
        except ValueError as e:                 # json.JSONDecodeError ⊂ ValueError
            # 附修复提示：根目录这几个 JSON 里装的是中文散文，**最容易的错**是正文里混进
            # ASCII 双引号（作者实测栽过 6 次）。只说 "Expecting ',' delimiter" 定位得到、
            # 但不知道为什么，所以把处置写在这儿。
            bad.append('%s → %s（提示：这些 JSON 里是中文散文，正文的引号要写「」而不是 ASCII 双引号；'
                       '`` ` `` 里的英文键名不受影响）' % (f, e))
        except Exception as e:
            bad.append('%s → 读失败 %s: %s' % (f, type(e).__name__, e))
    check(not bad, 'root *.json registries parse（%d 个）' % n,
          '；'.join(bad[:3]) if bad else 'ok')
    # ① 版本控制（fresh clone 上还在不在）
    tstate = _git_tracked(root_jsons[0]) if root_jsons else False
    if tstate is None:
        print('       (git 不可用 → 跳过「注册表是否已入库」判据)')
    else:
        check(not untracked, 'root *.json registries 已入库（%d 个）' % len(root_jsons),
              'ok' if not untracked else
              '未登记进 git：%s（fresh clone / CI 上会缺失，跑 git add）' % '、'.join(untracked))
    # ② 反引号指针：注册表里 `` `x.json` `` 必须指向真实文件。
    # ⚠️ 只认**无歧义的指针写法**（2026-10-03 实测教训）：`features_recent.json` 是变更史，
    # 满篇反引号里点的是**用户工程里的文件名**（`ui/main.json`、`SampleUI-New/…/ad.json`）与
    # 仓内别处的文件（`authority_map.json` 真身是 `knowledge/authority_map.json`）——
    # 一律当指针会造出十几条假红。所以判据收窄成两条：
    #   · 含 `/` 的路径 → 按仓根相对解析；
    #   · 不含 `/` 的裸文件名 → **只有当它是仓根注册表**时才判（写全路径是那条约定的写法）。
    # 真正的护栏其实是上面那条"已入库"检查（本轮 `fun_capabilities.json` 正是被它抓到）。
    # 另：变更史/流程里会出现**用户工程相对**的路径（`ui/main.json`、`SampleUI-New/…/ad.json`、
    # `blocks/_tokens.json`）——它们不是仓内指针，按前缀放行（与 check_doc_refs 的 ALLOW 同性质，
    # 都要写明理由；这里一次说清是"工程内相对路径"这一类）。
    PROJ_REL = ('ui/', 'blocks/', 'SampleUI-New/', 'projects/', 'workspace/')
    # 发布分支才带的文件：master 上本就没有，引用它是**对的**（拿 master 跑时不当死指针；
    # 与 check_doc_refs 的 `scripts/release_scope.json` 白名单同一条理由）。
    BRANCH_ONLY = ('scripts/release_scope.json',)
    ref_missing = []
    for f in root_jsons:
        try:
            refs = set(re.findall(r'`([A-Za-z0-9_][A-Za-z0-9_./-]*\.json)`', _read(os.path.join(BASE, f))))
        except Exception as e:
            ref_missing.append('%s 读失败 %s' % (f, type(e).__name__))
            continue
        for r in sorted(refs):
            if r in root_jsons or '/' not in r or r in BRANCH_ONLY:
                continue                        # 仓根注册表 / 裸文件名 / 发布分支专有 → 不当指针
            if r.startswith(PROJ_REL):
                continue                        # 工程内相对路径，不是仓内指针
            if not os.path.isfile(os.path.join(BASE, r.replace('/', os.sep))):
                ref_missing.append('%s 引用了不存在的 %s' % (f, r))
    check(not ref_missing, 'root registries 的反引号路径指针可解析',
          'ok' if not ref_missing else '；'.join(ref_missing[:3]))


def stage_referenced_files_tracked():
    """**被文字引用的仓内文件，必须已入库**（门禁/CI 跑的是 fresh clone / checkout 形态）。

    为什么单列一条（2026-10-03 实测踩到）：本轮 `scripts/run_tests.py` /
    `audit_design_spec.py` / `gen_unverified_report.py` / `fun_capabilities.json` 都
    **被门禁调用或被注册表引用，却没进 git** —— 一旦按当时状态发布，
    `check_consistency.py --with-tests` 在 fresh clone 上会一口气红 4 项
    （`has scripts/run_tests.py`、`delegated: tests/ unittest` 脚本缺失、两条新委派项），
    也就是"上一轮 P0-1 的成果只存在于作者机器上"。判据来自 `git ls-files`，不靠人记。

    写法（与 DESIGN_SPEC 第 4 条同精神）：扫全仓文本里提到的 `*.json` 等文件名，
    只对**真实存在**的那些问"入库了吗"；`.gitignore` 覆盖的派生目录（报告/临时/模型）
    按设计就是不入库的，跳过。查不到 git 时**跳过并提示**，不伪造成失败。
    """
    skip_dirs = {'.git', '__pycache__', 'node_modules', 'temp', 'models', '.workbuddy'}
    skip_prefix = ('knowledge/_reports/', 'knowledge/_logs/', 'temp/', 'models/', 'workspace/')
    exts = ('.json', '.py', '.md')
    try:
        tracked = set(l.replace('/', os.sep) for l in subprocess.run(
            ['git', 'ls-files'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            cwd=BASE, timeout=120).stdout.decode('utf-8', 'replace').split())
    except Exception as e:
        print('       (git 不可用 → 跳过「被引用的文件是否已入库」判据：%s)' % type(e).__name__)
        return
    # 大小写：Windows/macOS 文件系统不区分，git 索引区分（实测 `readme.md` 会解析到 `README.md`
    # 而被误判成"未入库"）→ 在**不区分大小写**的平台上把索引也按小写比对，避免假红。
    ci = os.path.normcase('A') == os.path.normcase('a')
    tracked_ci = set(t.lower() for t in tracked) if ci else None
    rx = re.compile(r'(?<![\w/.-])([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:%s))(?![\w-])'
                    % '|'.join(x.lstrip('.') for x in exts))
    hits, missing, seen, unreadable, scanned = 0, [], set(), [], 0
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fn in files:
            if not fn.endswith(('.py', '.json', '.md', '.yml', '.sh', '.bat', '.txt')):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, BASE).replace(os.sep, '/')
            if rel.startswith(skip_prefix):
                continue
            try:
                txt = io.open(p, encoding='utf-8', errors='replace').read()
            except OSError as e:
                # **不静默**（DESIGN_SPEC 第 3 条 / 静默 except lint 的要求）：读不了就记下来，
                # 由下面一条 check 如实报出"少扫了哪些文件"，而不是当作它不存在。
                unreadable.append('%s（%s）' % (rel, e.strerror or type(e).__name__))
                continue
            scanned += 1
            for r in rx.findall(txt):
                r = r.lstrip('./')
                if '..' in r:                              # `knowledge/../components/x.md` 这类
                    r = os.path.normpath(r).replace(os.sep, '/')   # 归一后再判（否则永远对不上）
                if r.replace('/', os.sep) in tracked:      # 已入库 → 不是问题
                    continue
                if tracked_ci is not None and r.lower() in tracked_ci:
                    continue                                # 已入库（仅大小写不同，见上）
                if r.startswith(skip_prefix):
                    continue                                # 派生/生成目录：按设计不入库
                if not os.path.isfile(os.path.join(BASE, r.replace('/', os.sep))):
                    continue                                # 不存在 → 归 check_doc_refs 管（这里只看"存在但没入库"）
                hits += 1                                   # 存在但没入库 = 有问题
                if r not in seen:
                    seen.add(r)
                    missing.append('%s（被 %s 引用）' % (r, rel))
    check(not missing, '被引用的仓内文件都已入库（扫 %d 篇，%d 处未入库）' % (scanned, hits),
          'ok' if not missing else
          '未登记进 git：%s —— 跑 git add（否则 fresh clone / CI 上会缺文件）' % '；'.join(missing[:3]))
    check(not unreadable, '扫描时无读不了的文件',
          'ok' if not unreadable else '读不了（已跳过，故本次扫描不完整）：%s' % '；'.join(unreadable[:3]))


# docstring 预算（v0.27.34 起进门禁）：工具 schema 每次会话都进上下文，膨胀 = 持续燃烧 token。
# 口径：单个 op ≤ 900 字符；全体合计 ≤ 12000 字符。长尾细节要求搬进 knowledge/（可检索）。
# ⚠️ 这三个 900/360/900 是**三个不同的东西**，别混：本处 900 = 单个 op 的 **docstring** 上限；
#   `op_spec.budget.perOpMax = 360` = 常驻面单条渲染上限；`contractPerOpMax = 900` = 按需契约单条上限。
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
    # 常驻预算的**口径文字**也是数字载体：`budget.basis` 手写的「常驻合计 N」必须 == 实测。
    # 为什么必须进闸门（2026-10-03 实测）：`params` 移出常驻后 basis 写着 4730 / 78.8% / 余约 14 op，
    # 而本轮改了几条 hardRules 后**实测已是 5080 / 84.7%** —— 于是 WORK_PLAN 与设计说明一起
    # 拿"余量还够 14 个 op"去排期，实际只剩 8 个左右。**同一事实写两遍，第二遍必然漂**：
    # 这里把"第二遍"钉成派生的（真值 = gen_op_docs 渲染产物，本函数刚算出的 total）。
    try:
        import op_spec_loader as _osl
        b = (_osl.load().get('budget') or {})
        m = re.search(r'常驻合计\s*\**\s*(\d+)', str(b.get('basis') or ''))
        if b.get('basis') and not m:
            check(False, 'budget.basis 常驻数字可解析',
                  'basis 里没有「常驻合计 N」这种写法 → 闸门无法对账（请保持该写法）')
        elif m:
            said = int(m.group(1))
            check(said == total, 'budget.basis 常驻数字（op_spec.json）',
                  '%d vs 实测 %d' % (said, total) if said != total else '%d = 实测' % total)
    except Exception as e:                      # 注册表读不了 → 如实报，不静默
        check(False, 'budget.basis 常驻数字可解析', '%s: %s' % (type(e).__name__, e))

    # 按需面的**口径文字**同样是数字载体：`budget.note` 里手写的「最长 `flythings_x` 已 N/上限」
    # 必须 == 实测。加这条是因为它**真的漂过**（2026-10-05 实测）：note 写「最长 build_ui_flow 757」
    # 而实际最长是 `i18n_to_json` 805 —— 错的数字活在 note / TODO / 评审报告三处，
    # 于是"按需面还剩 143 字符"这个判断从一开始就是错的（实际余 95，分层做完只剩 8）。
    # 口径：note 必须保持「最长 `<op 名>` 已 **N/上限**」这种**可解析**写法，否则闸门当场红。
    try:
        import op_spec_loader as _osl
        b = (_osl.load().get('budget') or {})
        note = str(b.get('note') or '')
        m = re.search(r'最长\s*`?(flythings_\w+)`?\s*已\s*\**\s*(\d+)\s*/\s*(\d+)', note)
        # ⚠️ 只按长度降序 —— 别用 `sorted((len, name))`：长度相同时会退化成**按名字**比较，
        # 于是"最长"取到的是名字最大的那个（2026-10-05 实测：所有 op 都短于 337 时，
        # 取到 `flythings_layout_audit` 而非真正的首条）。这条 bug 是判据自己抓出来的。
        live = sorted(((len(_osl.render_contract(o)), o) for o in _osl.registered()),
                      key=lambda t: -t[0])
        top_n, top_op = live[0]
        if not m:
            check(False, 'budget.note 最长 op 数字可解析',
                  'note 里没有「最长 `flythings_x` 已 N/上限」这种写法 → 闸门无法对账（请保持该写法）')
        else:
            said_op, said_n, said_cap = m.group(1), int(m.group(2)), int(m.group(3))
            cap = int(b.get('contractPerOpMax', 900))
            ok = (said_op == top_op and said_n == top_n and said_cap == cap)
            check(ok, 'budget.note 最长 op 数字（op_spec.json）',
                  '%s %d/%d vs 实测 %s %d/%d' % (said_op, said_n, said_cap, top_op, top_n, cap)
                  if not ok else '%s %d/%d = 实测' % (top_op, top_n, cap))
    except Exception as e:                      # 注册表读不了 → 如实报，不静默
        check(False, 'budget.note 最长 op 数字可解析', '%s: %s' % (type(e).__name__, e))

    # 2026-10-05 检讨补：note 里还有**两处**手写数字，此前没有任何判据盯着 —— 实测已经漂了：
    # 原文写「除 all 外最长单段 645（`flythings_i18n_to_json:rules`）」，而 `flythings_i18n_to_json`
    # 在本批已并入 `flythings_i18n`（**引用了不存在的 op**），实测最长单段是 731
    # （`flythings_i18n:skeleton`）。同一句话里两个数字都错 = 典型的"第二遍必然漂"。
    try:
        import op_spec_loader as _osl
        b = (_osl.load().get('budget') or {})
        note = str(b.get('note') or '')
        reg = list(_osl.registered())
        dflt = sorted(((len(_osl.render_default(o)), o) for o in reg), key=lambda t: -t[0])
        md = re.search(r'默认形态最长\s*\**\s*(\d+)', note)
        if md:
            said = int(md.group(1))
            check(said == dflt[0][0], 'budget.note 默认形态最长（op_spec.json）',
                  '%d vs 实测 %d（%s）' % (said, dflt[0][0], dflt[0][1]) if said != dflt[0][0]
                  else '%d（%s）= 实测' % (dflt[0][0], dflt[0][1]))
        best = ('', 0)
        sec_err = []                            # 段渲染失败要能被看见（不静默吞）
        for o in reg:
            for s in _osl.section_ids():
                if s == 'all':
                    continue
                try:
                    n = len(_osl.render_section(o, s) or '')
                except Exception as e:          # noqa: PERF203 —— 记进 sec_err，下面进 detail
                    sec_err.append('%s:%s(%s)' % (o, s, type(e).__name__))
                    continue
                if n > best[1]:
                    best = ('%s:%s' % (o, s), n)
        ms = re.search(r'除\s*all\s*外最长单段\s*\**\s*(\d+)\s*[（(]\s*`?([\w:.]+)`?\s*[）)]', note)
        if not ms:
            check(False, 'budget.note 最长单段数字可解析',
                  'note 里没有「除 all 外最长单段 N（<op>:<段>）」这种写法 → 闸门无法对账')
        else:
            ok = (int(ms.group(1)) == best[1] and ms.group(2) == best[0])
            check(ok, 'budget.note 最长单段（op_spec.json）',
                  '%s %s vs 实测 %s %d' % (ms.group(1), ms.group(2), best[0], best[1])
                  if not ok else '%s %d = 实测' % (best[0], best[1]))
    except Exception as e:                      # 注册表读不了 → 如实报，不静默
        check(False, 'budget.note 单段/默认形态数字可解析', '%s: %s' % (type(e).__name__, e))


# ⚠️ 白名单：确有必要引用仓外/临时路径的用例，在此登记并写理由（默认应为空）。
# 格式：(相对路径前缀, 字面量片段, 理由)
TEST_HERMETIC_ALLOW = [
    ('tests/test_selfcheck_bugreport.py', 'temp/bugreports/',
     'bugreport op 的**输出**目录（写到仓库根 temp，属于被测行为，不是夹具）'),
]


def _test_hermetic_hits(path, base=None):
    """扫一个 .py 的**字符串字面量**（跳过 docstring），返回 [(行号, 片段, 类别)]。

    只判「**会被当成路径去用**」的四种情形，不碰测试里用来断言行为的假值
    （`C:/fake/adb.exe`、`/tmp/busybox`、`D:/nope.json` 这类**故意不存在**的串）：
      ① `temp/…`       仓库根 temp 已 .gitignore（设计上不入库，fresh clone 必无）
      ② 存在但**未入库**：字面量能落到仓内一个**真实存在**的路径，而 git 不跟踪它
         —— 这正是 `temp/abtest_a` 那一类（本机有、别人没有）
      ③ 存在但在**仓外**：解析后落在仓库之外（如 `../ui_tools`）—— 依赖作者的多仓布局
      ④ 直接写死了本仓库绝对路径（换机器即无效）
    抽成独立函数是为了**能被用例直接调**（否则「门禁没命中」无法与「门禁是空转」区分）。

    判据边界（2026-10-05 补齐 ②③④ 时写清，避免"看起来扫了其实没扫"或"一口气假红"）：
      · ②③ 要求目标**存在且是文件**才算 —— 不存在的串归 check_doc_refs（死指针），不是这里的事；
        只判文件更关键：`'/'`、`'..'`、`'C:'` 这类**相对片段**在 Windows 上也能解析到仓外
        目录（实测 `.replace('\\\\','/')` 里的 `'\\\\'`、`os.path.join(…,'..')` 里的 `'..'`
        都会被解析出来），一律当引用判定会一口气假红 **22 处**（见 tests/test_hermetic_paths.py
        的契约用例）；
      · ③ 只判**相对**字面量（`../…`）：系统绝对路径（`/dev/null`、`/tmp/x`、`C:/Windows/…`）
        不是"本仓夹具"问题，而且 `/tmp/busybox`、`C:/fake/adb.exe` 这类假值已被契约用例
        钉成"不许假红"；
      · ② 只判**未被 .gitignore 覆盖**的（ignore 区按设计不入库，由 ①/`gitignored-path` 表达）；
        文件系统不区分大小写时按小写比对索引（实测 `readme.md` 会解析到 `README.md`）；
      · ④ 只看**字面量形态**（绝对路径 + 落在仓内），不要求存在：写死本身就是病；
      · git 索引取不到（git 不可用 / base 不是仓）时 ② **不判**，只报 ①③④ 与 ignore
        —— 宁可不判，也不能把全部夹具判成"未入库"。
    """
    base = base or BASE
    try:
        tree = ast.parse(io.open(path, encoding='utf-8', errors='replace').read())
    except SyntaxError as e:
        return [(e.lineno or 0, 'SyntaxError: %s' % e.msg, 'unparsable')]
    doc = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) \
                and n.body and isinstance(n.body[0], ast.Expr) \
                and isinstance(n.body[0].value, ast.Constant) \
                and isinstance(n.body[0].value.value, str):
            doc.add(id(n.body[0].value))
    try:
        _ls = subprocess.run(['git', 'ls-files'], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, cwd=base, timeout=120)
        tracked = set(l.replace('/', os.sep)
                      for l in _ls.stdout.decode('utf-8', 'replace').split())
        have_index = _ls.returncode == 0
    except Exception:
        tracked, have_index = set(), False
    # 大小写：Windows/macOS 文件系统不区分、git 索引区分 → 在不区分大小写的平台上按小写比对
    tracked_ci = (set(t.lower() for t in tracked)
                  if os.path.normcase('A') == os.path.normcase('a') else None)

    def _is_tracked(rel):
        return (rel.replace('/', os.sep) in tracked
                or (tracked_ci is not None and rel.lower() in tracked_ci))

    try:
        rel_self = os.path.relpath(path, base).replace(os.sep, '/')
    except ValueError:
        # Windows 跨盘（如用例用 tempfile 把合成样本建在 C: 而仓库在 D:）——
        # relpath 会抛 ValueError，而本变量**只用于白名单前缀比较**（见下），
        # 退成绝对路径即可：它不会匹配 `tests/…` 之类的相对前缀，等于「这个文件不在白名单里」，
        # 正是跨盘样本该有的判定。别让门禁因为「文件不在同一个盘」而崩（2026-10-04 实测
        # 两条用例因此报 ValueError: path is on mount 'C:', start on mount 'D:'）。
        rel_self = os.path.normpath(path).replace(os.sep, '/')

    def _cands(s):
        """字面量可能指向的地方（根 / tests 下各试一次）。"""
        out = []
        if re.match(r'^[A-Za-z]:/', s) or s.startswith('/'):
            out.append(os.path.normpath(s))
        else:
            out.append(os.path.normpath(os.path.join(base, s)))
            out.append(os.path.normpath(os.path.join(base, 'tests', s)))
        return out

    lits = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Constant) or not isinstance(n.value, str) or id(n) in doc:
            continue
        s = n.value.replace('\\', '/')
        if len(s) > 240 or '\n' in s:
            continue                          # 散文/命令行串不判
        lits.append((n.lineno, s))

    # 「被 .gitignore 覆盖」用 git check-ignore 实测（而不是"未跟踪"）：
    # 开发机上未跟踪的构建产物（toolchain/、tools/adb/）遍地都是，拿未跟踪当判据会满屏假红。
    probe, ignored = [], set()
    for ln, s in lits:
        for c in _cands(s):
            if os.path.exists(c):
                probe.append(c)
    if probe:
        try:
            r = subprocess.run(['git', 'check-ignore', '--stdin'], cwd=base, timeout=120,
                               input=('\n'.join(probe)).encode('utf-8'),
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            ignored = set(l.replace('/', os.sep) for l in
                          r.stdout.decode('utf-8', 'replace').split('\n') if l.strip())
        except Exception:
            ignored = set()

    def _inside(c):
        """c 是否落在 base 之内（Windows 跨盘会抛 ValueError → 判"不在"）。"""
        try:
            return os.path.commonpath([os.path.abspath(c), base]) == base
        except ValueError:
            return False

    hits = []
    for ln, s in lits:
        kind = None
        absolute = bool(re.match(r'^[A-Za-z]:/', s)) or s.startswith('/')
        if re.match(r'^temp/', s):
            kind = 'repo-temp'                # 仓库根临时区：设计上不入库，fresh clone 必无
        elif absolute and _inside(_cands(s)[0]):
            kind = 'repo-abs-path'            # ④ 写死本仓绝对路径（不判存在与否）
        else:
            for c in _cands(s):
                if not os.path.exists(c):
                    continue                  # 不存在 → 归 check_doc_refs 管（死指针）
                if c in ignored:
                    kind = 'gitignored-path'  # 字面量落在 .gitignore 区（夹具放错地方）
                    break
                if not _inside(c):
                    # ③ 仓外依赖：只认**相对**字面量 + 真实文件（系统绝对路径/目录片段不算）
                    if absolute or not os.path.isfile(c):
                        continue
                    kind = 'outside-repo'
                    break
                rel = os.path.relpath(os.path.abspath(c), base).replace(os.sep, '/')
                if os.path.isfile(c) and have_index and not _is_tracked(rel):
                    kind = 'untracked-path'   # ② 本机有、别人没有（fresh clone 上必缺）
                    break
        if not kind:
            continue
        if any(rel_self.startswith(a[0]) and a[1] in s for a in TEST_HERMETIC_ALLOW):
            continue
        hits.append((ln, s[:70], kind))
    return hits


def stage_test_hermetic():
    """契约用例只许引用**仓内、已入库**的路径（hermetic 夹具）。

    为什么单列（2026-10-04 实测）：`tests/test_ui_schema.py` 的两个 4b 用例读
    `temp/abtest_a|b`，而仓库根 `temp/` 在 `.gitignore` 里 —— **fresh clone 上必挂**
    （同步后实跑 failures=3，其中 2 条就是它）。同类还有绝对路径与 `../` 越界：
    它们在作者机器上绿、在别人机器上红，属**验证层的不可复现**。
    夹具要随仓走：放 `tests/fixtures/<名>/`（已入库）。

    四类命中（细则见 `_test_hermetic_hits` 的 docstring）：`repo-temp`（`temp/…` 字面量）、
    `gitignored-path`（落在 .gitignore 区）、`untracked-path`（存在但没 `git add`）、
    `outside-repo`（解析到仓外）、`repo-abs-path`（写死本仓绝对路径）。
    ②③④ 三类 2026-10-05 补齐：此前 docstring 承诺了、代码只实现了 ①+ignore，
    `git ls-files` 的结果是**死代码** —— 实测当时"未入库的 .ftu 夹具 / `../ui_tools/x.py` /
    写死本仓绝对路径"三种反例都能静默通过（TODO §B6）。
    """
    tdir = os.path.join(BASE, 'tests')
    bad, scanned = [], 0
    for root, dirs, files in os.walk(tdir):
        dirs[:] = [d for d in dirs if d not in ('__pycache__',)]
        for fn in sorted(files):
            if not fn.endswith('.py'):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, BASE).replace(os.sep, '/')
            scanned += 1
            for ln, frag, kind in _test_hermetic_hits(p):
                bad.append('%s:%d [%s] %s' % (rel, ln, kind, frag))
    check(not bad, 'tests/ 路径随仓（hermetic 夹具；扫 %d 个 .py）' % scanned,
          '；'.join(bad[:3]) + (' …共 %d 处' % len(bad) if len(bad) > 3 else '') if bad else 'ok')


def stage_deliverables(with_tests):
    for f in ('pyproject.toml', 'requirements.lock', 'install.bat', 'LICENSE',
              'scripts/smoke.py', 'scripts/sync_ui_tools.py', 'scripts/gen_manifest.py',
              'scripts/run_tests.py', 'scripts/lint_silent_except.py'):
        check(os.path.isfile(os.path.join(BASE, f)), 'has %s' % f, '')
    tdir = os.path.join(BASE, 'tests')
    checks = sorted(f for f in os.listdir(tdir)) if os.path.isdir(tdir) else []
    check(bool([f for f in checks if f.startswith('test_') and f.endswith('.py')]),
          'tests/ contract cases present', ','.join(checks[:6]))


def _kb_report_normalize(gen, text):
    """把派生报告的**稳定核**取出来做比对 —— 让"陈旧"只表示「与真源不一致」。

    为什么必须归一（2026-10-04 实测）：这些报告里混了两类东西 ——
      · **稳定核**（随仓真源决定）：源哈希、篇数、分类表、证据/时效、backlog、检索登记数；
      · **本机态/时间戳**：`generatedAt`、`indexMeta.built_at`、`lastVerify`（本机复验轨迹）、
        `gaps`（本机未命中日志，`kb_local.gaps()` 每次调用都在累加）、`localLayer.dir`（绝对路径）。
    直接逐字节比 → 报告**永远**判陈旧（实测：同一份代码生成两次的 `gaps.totalLogged` 就不同），
    也就是一条永远红的判据。归一后保留上面那半，它才真能抓到"知识页改了但看板没重生成"。
    """
    if gen.endswith('kb_health.json'):
        try:
            h = json.loads(text)
        except ValueError:
            return text
        h.pop('generatedAt', None)
        h.pop('lastVerify', None)
        h.pop('gaps', None)
        h['indexMeta'] = {k: v for k, v in (h.get('indexMeta') or {}).items() if k != 'built_at'}
        if isinstance(h.get('localLayer'), dict):
            h['localLayer'] = {k: v for k, v in h['localLayer'].items() if k != 'dir'}
        return json.dumps(h, ensure_ascii=False, indent=1, sort_keys=True)
    if gen.endswith('kb_health.md'):
        keep, cut = [], False
        for ln in text.splitlines():
            if ln.startswith('> 生成时间：'):
                continue
            if ln.startswith('- 上次复验：') or ln.startswith('- 未命中累计 '):
                continue
            if ln.startswith('- 候选区（inbox）'):
                # 该行的「本地层」是本机层统计（含绝对路径），只留随仓那半
                ln = ln.split('｜ 本地层：')[0]
            if ln.startswith('## 六、未命中缺口 top 10'):
                cut = True                     # 本节完全来自本机未命中日志
            if not cut:
                keep.append(ln)
        return '\n'.join(keep) + '\n'
    return text


def _bootstrap_kb_reports():
    """知识类派生报告（`knowledge/_reports/`）：**内容比对**真源；缺失才生成。

    为什么必须有这一步（2026-10-04 干净检出实测）：这些报告在 `.gitignore` 里（与 kb_index
    同性质，属派生物），但门禁的 3 条委派项（kb_health / audit_design_spec /
    gen_unverified_report）会拿**报告 vs 真源**比对 —— fresh clone 上报告根本不存在，
    于是这 3 项**必然红**（实测：干净检出 74 项 / 5 红，其中 3 项是"缺报告"）。
    这与本项目反复治的病同源：**门禁依赖一个未入库、又没人负责生成的产物**。

    修法选"生成 + 比对"而不是"缺了就跳过"：
      · 跳过 = 该判据在 CI 上永不生效（假绿）；
      · 生成 + 比对 = CI 上照样能抓到"报告与真源不一致"（真漂移），"本机没生成过"不再是失败。
    ⚠️ 必须**先生成到内存/临时、再与磁盘比**，不能"先重生成再让委派项比对"——那样委派项
    永远比对的是刚生成的文件，陈旧永远查不出来（这是个假绿陷阱，故在此一处判完）。
    生成器的输入只有仓内 `knowledge/`（实测三者互不依赖），所以这步确定、可重复。
    """
    for label, gen, outs in (
            ('kb_health', 'kb_health.py', ('knowledge/_reports/kb_health.json',
                                           'knowledge/_reports/kb_health.md')),
            ('design_spec_audit', 'audit_design_spec.py',
             ('knowledge/_reports/design_spec_audit.md',
              'knowledge/_reports/design_spec_audit.json')),
            ('unverified', 'gen_unverified_report.py',
             ('knowledge/_reports/unverified.md',
              'knowledge/_reports/unverified.json'))):
        paths = [os.path.join(BASE, n.replace('/', os.sep)) for n in outs]
        on_disk = {}
        for p in paths:
            try:
                on_disk[p] = _kb_report_normalize(
                    p.replace(os.sep, '/').split('/')[-1],
                    io.open(p, encoding='utf-8', newline='').read())
            except OSError:
                on_disk[p] = None
        if gen == 'kb_health.py':       # 看板依赖 kb_index.json（另一产物）：缺了先如实报，不代跑
            if not os.path.isfile(os.path.join(BASE, 'knowledge', 'kb_index.json')):
                check(False, 'kb 报告: %s' % label,
                      '缺 knowledge/kb_index.json（先跑 python scripts/gen_kb_index.py）')
                continue
        rc, _out = _run([sys.executable, os.path.join(SUB, gen)])
        if rc != 0:
            check(False, 'kb 报告: %s' % label, '生成失败 rc=%d' % rc)
            continue
        missing = [os.path.basename(p) for p in paths if on_disk[p] is None]
        if missing:
            check(True, 'kb 报告: %s' % label,
                  '本机无报告 → 已按需生成（%s）' % '、'.join(missing))
            continue
        diff = [os.path.basename(p) for p in paths
                if _kb_report_normalize(p.replace(os.sep, '/').split('/')[-1],
                                        io.open(p, encoding='utf-8', newline='').read())
                != on_disk[p]]
        check(not diff, 'kb 报告: %s' % label,
              'ok（与真源一致）' if not diff else
              '陈旧：%s 与真源不一致（已重生成，请复核差异）' % '、'.join(diff))


def stage_delegated(skip_smoke, with_tests):
    _bootstrap_kb_reports()
    gate = os.path.join(SUB, 'release_gate.py')
    if RELEASE_SCOPE and os.path.isfile(gate):
        rc, out = _run([sys.executable, gate])
        tail = [l for l in out.strip().splitlines() if l.startswith('total=')]
        check(rc == 0, 'delegated: release_gate.py (公开边界)',
              tail[0] if tail else 'rc=%d' % rc)
    rc, out = _run([sys.executable, os.path.join(SUB, 'sync_ui_tools.py'), '--check'])
    # 退出码口径：0=一致 / 2=本机没有副本（skip，公开仓库与 CI 的正常形态）/ 1=真漂移。
    # 以前只认 rc==0 → 从 fresh clone 跑必然红（副本目录在仓库之外），
    # 而 smoke 对同一件事是容错 skip —— 同一口径两个消费方不一致（2026-10-03 评审）。
    check(rc in (0, 2), 'delegated: sync_ui_tools --check',
          {0: 'ok（双份一致）', 2: 'skip（本机无副本，非漂移）'}.get(
              rc, out.strip().splitlines()[-1][:70] if out.strip() else 'rc=%d' % rc))
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_manifest.py'), '--check'])
    check(rc == 0, 'delegated: gen_manifest --check',
          'ok' if rc == 0 else out.strip().splitlines()[-1][:70])
    # v0.27.174：op 契约注册表（op_spec.json）→ docstring 派生一致性 + 渲染预算。
    # 45/45 已登记 → --strict：任何 op 漏登记、docstring 与注册表漂移、渲染超预算都算失败。
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_op_docs.py'), '--check', '--strict'])
    op_tail = [l for l in out.strip().splitlines()
               if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: gen_op_docs --check (op 契约注册表)',
          (op_tail[-1] if op_tail else 'rc=%d' % rc)[:70])
    # v0.27.175：平台能力注册表（platform_capabilities.json）→ components/*/platforms.md
    # 里那张「平台 × 可用性」矩阵表的派生一致性（15 篇同源，不许各抄一份）。
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_component_platforms.py'), '--check'])
    pc_tail = [l for l in out.strip().splitlines()
               if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: gen_component_platforms --check (平台能力注册表)',
          (pc_tail[-1] if pc_tail else 'rc=%d' % rc)[:70])
    # v0.27.175：平台能力注册表 → 可检索知识页（knowledge/devflow/platform-capability-matrix.md）。
    # 该页让「某组件在某平台能不能用」进入检索范围（RAG 只覆盖 knowledge/，components/*.md 检索不到）。
    # v0.27.179：生命周期与代码接口契约（lifecycle_spec.json）→ 知识页派生一致性，
    # 顺带做「注册表钩子 == 模板骨架钩子」的交叉检查（注册表写错/模板掉钩子都会红）。
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_lifecycle_doc.py'), '--check'])
    lc_tail = [l for l in out.strip().splitlines()
               if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: gen_lifecycle_doc --check (生命周期契约)',
          (lc_tail[0] if lc_tail else 'rc=%d' % rc)[:70])
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_platform_cap_doc.py'), '--check'])
    pcd_tail = [l for l in out.strip().splitlines()
                if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: gen_platform_cap_doc --check (平台能力知识页)',
          (pcd_tail[-1] if pcd_tail else 'rc=%d' % rc)[:70])
    # v0.27.176：内置包注册表（package_catalog.json）→ 可检索知识页（builtin-packages.md）。
    # 「有哪些内置包 / 什么版本」原先只在 json 里，AI 检索不到，选型时不知道能直接用现成包。
    # v0.27.180（域⑦）：可复用组件目录 —— 「四件套缺一不收」跑成可执行校验 + 派生页一致性
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_components_catalog.py'), '--check'])
    cc_tail = [l for l in out.strip().splitlines()
               if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: gen_components_catalog --check (可复用组件目录)',
          (cc_tail[-1] if cc_tail else 'rc=%d' % rc)[:70])
    # v0.27.181（域⑨）：上机前体检判据（preflight_spec.json）→ 可检索判据页；
    # 顺带跨来源对账：字库体积阈值与档位必须与 components/fonts 的实现一致（分叉 = 判定与投递两套口径）。
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_preflight_doc.py'), '--check'])
    pf_tail = [l for l in out.strip().splitlines()
               if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: gen_preflight_doc --check (上机前体检判据)',
          (pf_tail[-1] if pf_tail else 'rc=%d' % rc)[:70])
    # v0.27.182（域⑩）：开发流程（flow_spec.json）—— 步骤原子 + 两条正交轴（场景 / 动作）；
    # 该脚本内部跑 flow_loader.validate()，含**与 op 契约的跨来源对账**：
    # 步骤引用的 op 必须存在；声明了闸门的步骤，其 op 契约里必须有铁律（否则闸门只活在流程页里）。
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_flow_doc.py'), '--check'])
    fl_tail = [l for l in out.strip().splitlines()
               if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: gen_flow_doc --check (开发流程索引)',
          (fl_tail[-1] if fl_tail else 'rc=%d' % rc)[:70])
    # 域①（2026-10-04）：现场症状注册表（symptom_spec.json）→ 可检索症状索引页。
    # 口径：用户说的是**症状**（切一下才显示/拖不动），文档写的是**机制**；把症状单列一域
    # （与人侧 error_codes.json 同构），口语只进注册表、不进正文散文（DESIGN_SPEC §1）。
    # 本项同时跑 symptom_loader.validate()：doc 必须存在且不得指向派生页自己。
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_symptom_doc.py'), '--check'])
    sy_tail = [l for l in out.strip().splitlines()
               if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: gen_symptom_doc --check (现场症状索引)',
          (sy_tail[-1] if sy_tail else 'rc=%d' % rc)[:70])
    # 域③（2026-10-05 补）：**注册表里的"未验证"必须都能在派生页里核对到**。
    # 为什么单列：全仓盘点（本轮）发现「已实测平台的组件形态未回归」「Z235X 工具全缺」
    # 「6 个包 example 待补」这类**验证债**散在 components/*/platforms.md、packages/*/platforms.md
    # 与注册表里，没有任何汇总通道 → 只能靠人记得（那 24 项漏项主要就是这么来的）。
    # 判据取"计数对账"而不是"内容一致"（后者由 gen_component_platforms --check 负责）：
    # 注册表里 cells 含「未验证/不可用/缺」的单元格数，必须 == 派生矩阵页里的出现次数。
    # 它不会替你验，但**任何新的未验证格子都会被登记页如实呈现**，不会静默躺在注册表里。
    try:
        import platform_cap_loader as _pc
        reg = _pc.load()
        pend = sum(1 for c in (reg.get('components') or {}).values()
                   for row in (c.get('rows') or [])
                   for cell in (row.get('cells') or [])
                   if isinstance(cell, str) and any(k in cell for k in ('未验证', '不可用', '缺')))
        import io as _io
        mp = os.path.join(BASE, 'knowledge', 'devflow', 'platform-capability-matrix.md')
        txt = _io.open(mp, encoding='utf-8').read() if os.path.isfile(mp) else ''
        seen = sum(txt.count(k) for k in ('未验证', '不可用', '缺'))
        check(seen >= pend, '未验证单元格都进了派生矩阵页（注册表 %d / 页面 %d）' % (pend, seen),
              'ok' if seen >= pend else
              '派生页少 %d 处 → 跑 python scripts/gen_platform_cap_doc.py' % (pend - seen))
    except Exception as e:                      # 注册表不可用不静默
        check(False, '未验证单元格都进了派生矩阵页', '%s: %s' % (type(e).__name__, e))
    # v0.27.173（域⑫）：错误码表 —— 源码里出现的 code 必须已登记（防漏登记），
    # 登记的必须真有人抛（防孤儿码）；这直接决定失败返回里的 action 能不能补出来。
    try:
        import error_codes_loader as _ec
        ec_errs = _ec.validate()
    except Exception as e:                      # 模块缺失 = 对账无法进行（不静默）
        ec_errs = ['error_codes_loader 不可用：%s: %s' % (type(e).__name__, e)]
    check(not ec_errs, '错误码表（域⑫ error_codes.json）',
          (ec_errs[0] if ec_errs else '已登记码与源码一一对应')[:70])
    # 工程状态（域⑪）：状态位的 setBy/blocks 必须指向真实步骤 —— 否则「下一步」会算错
    try:
        import project_state as _ps
        ps_bad = [n for n, v in _ps.slots().items()
                  if v.get('setBy') not in _ps._flows_loader().steps()]
    except Exception as e:
        ps_bad = ['project_state 不可用：%s: %s' % (type(e).__name__, e)]
    check(not ps_bad, '工程状态位（域⑪ 状态位 → 步骤）',
          (str(ps_bad[0]) if ps_bad else '全部状态位都指向真实步骤')[:70])
    # v0.27.180（B3）：工程骨架唯一来源 —— templates/HelloWord_Z20/src 为骨架真源，
    # 各工程的副本（实测 18 份）必须与它一致；改骨架只需改一处 + --apply。
    rc, out = _run([sys.executable, os.path.join(SUB, 'sync_project_skeleton.py'), '--check'])
    sk_tail = [l for l in out.strip().splitlines()
               if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: sync_project_skeleton --check (工程骨架唯一来源)',
          (sk_tail[-1] if sk_tail else 'rc=%d' % rc)[:70])
    # v0.27.180：多媒体能力注册表（media_capabilities.json）→ 派生页一致性 + 跨来源对账
    # （docRef 必须真实存在、引用的包必须在 package_catalog 里）
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_media_cap_doc.py'), '--check'])
    mc_tail = [l for l in out.strip().splitlines()
               if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: gen_media_cap_doc --check (多媒体能力知识页)',
          (mc_tail[-1] if mc_tail else 'rc=%d' % rc)[:70])
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_package_catalog_doc.py'), '--check'])
    pk_tail = [l for l in out.strip().splitlines()
               if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: gen_package_catalog_doc --check (内置包知识页)',
          (pk_tail[-1] if pk_tail else 'rc=%d' % rc)[:70])
    # T5.1（2026-10-05）：**发射口径对账快照**不许过期 —— 三处发射实现（ui_emit / html2json /
    # compose）之间一旦漂移，这里当场红（而不是等真机出问题）
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_emit_conformance.py'), '--check'])
    ec_tail = [l for l in out.strip().splitlines()
               if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: gen_emit_conformance --check (发射口径对账)',
          (ec_tail[-1] if ec_tail else 'rc=%d' % rc)[:70])
    # T4.1（2026-10-05）：renderContract 的实现覆盖声明 —— 「哪条规格由谁实现/谁不实现」是数据，
    # evidence 必须是代码里真实存在的函数/常量（AST 校验）；声明与代码漂移 = 红。
    rc, out = _run([sys.executable, os.path.join(SUB, 'check_render_contract_coverage.py'), '--check'])
    crc_tail = [l for l in out.strip().splitlines()
                if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: check_render_contract_coverage --check (视觉口径实现覆盖声明)',
          (crc_tail[-1] if crc_tail else 'rc=%d' % rc)[:70])
    # T0.3（2026-10-05）：界面**入口登记表**的派生页不许滞后 —— 真源 = 仓库根 ui_entrypoints.json
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_entrypoints_doc.py'), '--check'])
    ep_tail = [l for l in out.strip().splitlines()
               if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: gen_entrypoints_doc --check (界面入口登记派生页)',
          (ep_tail[-1] if ep_tail else 'rc=%d' % rc)[:70])
    # v0.27.138：op → 知识「去哪找」（op_seealso.json）覆盖度 —— 每个 op 要么有 seeAlso、要么登记 none + 理由
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_seealso.py'), '--check'])
    check(rc == 0, 'delegated: gen_seealso --check',
          'ok' if rc == 0 else out.strip().splitlines()[-1][:70])
    # v0.27.177：文档指针健康——引用的 knowledge 文档路径必须真实存在（死指针会让 AI 去搜搜不到的东西）
    rc, out = _run([sys.executable, os.path.join(SUB, 'check_doc_refs.py')])
    dr_tail = [l for l in out.strip().splitlines()
               if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: check_doc_refs (文档指针健康)',
          (dr_tail[0] if dr_tail else 'rc=%d' % rc)[:70])
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
    # P2：知识体检看板不许滞后（比对 kb_index 源哈希）——看板是决策依据，静默滞后会误导
    rc, out = _run([sys.executable, os.path.join(SUB, 'kb_health.py'), '--check'])
    tail2 = [l for l in out.strip().splitlines()
             if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: kb_health --check (看板新鲜度)',
          (tail2[0] if tail2 else 'rc=%d' % rc)[:70])
    # 「未核 / 待验证」派生清单不许滞后：它是「哪些结论还没验」的唯一视图（内容真源仍在各页）。
    # 注意 knowledge/_reports/ 是 .gitignore 的（与 kb_health 同性质）：本函数开头的
    # `_bootstrap_kb_reports()` 会在缺失时先按需生成，此处只判「报告 vs 真源」是否一致。
    # 设计规范全检（DESIGN_SPEC.md 第 0–4 条）不许滞后：它是「通用内容/踩坑叙述/静态值」的体检视图
    rc, out = _run([sys.executable, os.path.join(SUB, 'audit_design_spec.py'), '--check'])
    tail4 = [l for l in out.strip().splitlines()
             if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: audit_design_spec --check (设计规范全检)',
          (tail4[0] if tail4 else 'rc=%d' % rc)[:70])
    rc, out = _run([sys.executable, os.path.join(SUB, 'gen_unverified_report.py'), '--check'])
    tail3 = [l for l in out.strip().splitlines()
             if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: gen_unverified_report --check (未核清单新鲜度)',
          (tail3[0] if tail3 else 'rc=%d' % rc)[:70])
    if not skip_smoke:
        rc, out = _run([sys.executable, os.path.join(SUB, 'smoke.py')])
        last = [l for l in out.strip().splitlines() if l.startswith('total=')]
        check(rc == 0, 'delegated: smoke.py', last[0] if last else 'rc=%d' % rc)
    # 检索质量回归（v0.27.94 起进门禁）：16 条真实问法必须一次命中权威文档 + 11 条对照组防调参副作用。
    # 无需向量模型也能跑（自动降级 BM25，实测同样 16/16），耗时 ~4s。
    # 发布/裁剪构建（如 release 分支，PUBLISH.md §3 剔了内部文档）里，指向被剔文档的**整组**
    # 显式跳过并列名 —— 否则那几组问法全落空，会把"按发布边界剔除"误报成"检索滑坡"。
    # 判据是**构建里有没有 PUBLISH.md**（内部版必有），不是环境变量：git 切分支即生效、不会忘传。
    _rel_argv = []
    if not os.path.isfile(os.path.join(BASE, 'PUBLISH.md')):
        _rel_argv = ['--skip-missing-docs']
    rc, out = _run([sys.executable, os.path.join(SUB, 'check_retrieval.py')] + _rel_argv)
    last = [l for l in out.strip().splitlines()
            if l.startswith('[PASS]') or l.startswith('[FAIL]')]
    check(rc == 0, 'delegated: check_retrieval.py',
          (last[0] if last else 'rc=%d' % rc)[:70])
    if with_tests:
        # 守法（2026-10-03 第三次调整，最终形态）：**不用墙钟当判据**。
        #
        # 实测同机同代码，全套一次 1036s 跑完、一次 >2700s 未结束（随负载/文件系统显著漂移）——
        # 于是"能不能跑完"取决于机器快慢，那是**环境属性，不是代码属性**。用它当判据必然假红。
        #
        # 现在判"挂"的责任全部交给 scripts/run_tests.py 的**逐用例看门狗**：
        # 单条超 120s → dump 全线程栈并结束进程（退出码非 0）→ 这里如实报 FAIL 且带栈。
        # 即：**慢没关系，挂必须被逮到**。默认不设外层墙钟；CI 想兜底可设
        # FLYTHINGS_TEST_TIMEOUT（秒），例如 `FLYTHINGS_TEST_TIMEOUT=900`。
        cap = (os.environ.get('FLYTHINGS_TEST_TIMEOUT') or '').strip()
        rc, out = _run([sys.executable, os.path.join(SUB, 'run_tests.py')],
                       timeout=int(cap) if cap.isdigit() else None)
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
        # ⚠️ 「当前数字」的**全部**载体都要对实测负责，不只 tests/README（2026-10-03 补）：
        # 同一时刻仓库里曾同时存在 676 / 682 / 707 三个"用例数"（WORK_PLAN 与 tests/_util.py
        # 的散文里各手写一份），而闸门只盯 tests/README 一处 → 另外两处随意漂。
        # 判据用法：每条 (文件, 锚定正则, 该条量的是什么) —— 正则必须**恰好命中一次**。
        # 正因如此，正文里"历史读数"要写成不带数字的叙述（否则正则会把历史值也抓来对账）：
        # 这条约束本身是目的 —— **留在纸上的数只能是当前值**。
        # 「门禁 N 项」的真值 = 本次 RESULT 的最终长度 = 现在已累计的 + 本处这 1 条。
        cases = real
        gates = len(RESULT) + 1
        decl = [
            ('WORK_PLAN.md', r'用例实测\s*\*\*(\d+)\s*项\*\*', cases, '用例数'),
            ('WORK_PLAN.md', r'门禁\s*\*\*(\d+)\s*项\*\*', gates, '门禁条数'),
            (os.path.join('tests', '_util.py'), r'全套\s*(\d+)\s*条用例', cases, '用例数'),
        ]
        badc, hits_ok = [], 0
        for rel, rx, want, what in decl:
            hit = re.findall(rx, _read(os.path.join(BASE, rel.replace('/', os.sep))))
            if len(hit) != 1:
                badc.append('%s 的「%s」命中 %d 次 /%s/（要恰好 1 次：0 次=措辞改了，>1 次=有第二处手写）'
                            % (rel, what, len(hit), rx))
                continue
            hits_ok += 1
            if int(hit[0]) != want:
                badc.append('%s 的「%s」写 %s 而实测 %d' % (rel, what, hit[0], want))
        check(not badc, '当前数字各处声明 == 实测（命中 %d 处）' % hits_ok,
              '；'.join(badc[:3]) if badc else 'ok')


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
    stage_platform_arch()
    stage_bin_tools()
    stage_cli_products()
    stage_no_ide_local_files()
    stage_no_people_names()
    stage_index()
    stage_json_registries()
    stage_referenced_files_tracked()
    stage_test_hermetic()
    stage_font_sizes()
    stage_selfcheck_sections()
    stage_docstring_budget()
    stage_kb_authority()
    stage_package_manifest()
    stage_cli_names()
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
