# -*- coding: utf-8 -*-
"""公开版边界校验（release gate）——只在 release 分支存在的闸门。

为什么单独一个脚本：check_consistency.py 是两侧共用的通用闸门（版本/工具数/平台矩阵/
索引/隐私/静默 except），而「哪些内容不许进公开版」是**发布侧独有**的口径，
写在 release_scope.json 里（机器可读），由本脚本逐条核验。

用法：python scripts/release_gate.py            # 0 = 通过；1 = 有 FAIL
口径来源：scripts/release_scope.json
"""
import io
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCOPE = os.path.join(BASE, 'scripts', 'release_scope.json')

RESULT = []
SCAN_EXT = ('.py', '.md', '.txt', '.bat', '.json', '.xml', '.cc', '.cpp', '.h',
            '.properties', '.c', '.sh', '.toml', '.cfg', '.yml', '.lock')
SKIP_DIRS = ('__pycache__', '.git', '.vscode', 'node_modules', '.fun', 'models')
SKIP_FILES = ('rag_index.json', 'release_scope.json', 'release_gate.py')


def check(ok, name, detail=''):
    RESULT.append((bool(ok), name, detail))
    print('%s %-44s %s' % ('[PASS]' if ok else '[FAIL]', name, detail))
    return bool(ok)


def load_scope():
    if not os.path.isfile(SCOPE):
        print('[FAIL] release_scope.json 不存在：%s' % SCOPE)
        sys.exit(1)
    return json.loads(io.open(SCOPE, encoding='utf-8').read())


def stage_paths(scope):
    bad = []
    for rel in scope.get('forbiddenPaths', []):
        if os.path.exists(os.path.join(BASE, rel.replace('/', os.sep))):
            bad.append(rel)
    check(not bad, 'forbidden paths absent', ','.join(bad) if bad else
          '%d 条全部不存在' % len(scope.get('forbiddenPaths', [])))
    bad = []
    for rel in scope.get('demoBlacklist', []):
        if os.path.isdir(os.path.join(BASE, rel.replace('/', os.sep))):
            bad.append(rel)
    check(not bad, 'demo blacklist absent', ','.join(bad) if bad else
          '%d 条全部不存在' % len(scope.get('demoBlacklist', [])))


def stage_words(scope):
    words = scope.get('forbiddenWords', [])
    allow = [re.compile(p) for p in scope.get('allowedPatterns', [])]
    hits, unreadable = [], []
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if not f.endswith(SCAN_EXT) or f in SKIP_FILES:
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, BASE).replace('\\', '/')
            try:
                if os.path.getsize(p) > 30 * 1024 * 1024:
                    continue
                txt = io.open(p, encoding='utf-8', errors='ignore').read()
            except OSError as e:                    # 不静默：读不到的源要能看见
                unreadable.append('%s(%s)' % (rel, e.strerror or e))
                continue
            for i, line in enumerate(txt.splitlines(), 1):
                if any(a.search(line) for a in allow):
                    continue
                for w in words:
                    if w in line:
                        hits.append('%s:%d %s' % (rel, i, w))
    check(not hits, 'forbidden words absent', '0 命中' if not hits else '; '.join(hits[:6]))
    if hits:
        print('       (%d 处命中，全量见上；先清再发布)' % len(hits))
    if unreadable:
        print('       unreadable: %s' % ', '.join(unreadable[:3]))


def stage_privacy():
    pats = [('本机绝对路径', re.compile(r'C:[\\/]Users[\\/](?!<)')),
            ('主机名', re.compile(r'DESKTOP-[A-Z0-9]{4,}')),
            ('内网 IP', re.compile(r'\b192\.168\.\d+\.\d+'))]
    allow = [re.compile(r'192\.168\.1\.(1|100)\b')]
    leaks, unreadable = [], []
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if not f.endswith(SCAN_EXT) or f in SKIP_FILES:
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, BASE).replace('\\', '/')
            try:
                txt = io.open(p, encoding='utf-8', errors='ignore').read()
            except OSError as e:                    # 不静默：读不到的源要能看见
                unreadable.append('%s(%s)' % (rel, e.strerror or e))
                continue
            for i, line in enumerate(txt.splitlines(), 1):
                for nm, pat in pats:
                    if pat.search(line) and not any(a.search(line) for a in allow):
                        leaks.append('%s:%d %s' % (rel, i, nm))
                if re.search(r'accessKey|access_key', line, re.I):
                    m = re.search(r'\b[0-9a-fA-F]{40}\b', line)
                    if m and set(m.group(0).lower()) != {'0'}:
                        leaks.append('%s:%d 真实 accessKey' % (rel, i))
    check(not leaks, 'privacy scan', '0 命中' if not leaks else '; '.join(leaks[:5]))
    if unreadable:
        print('       unreadable: %s' % ', '.join(unreadable[:3]))


def stage_package_catalog(scope):
    p = os.path.join(BASE, 'package_catalog.json')
    if not os.path.isfile(p):
        check(False, 'package_catalog.json exists', p)
        return
    d = json.loads(io.open(p, encoding='utf-8').read())
    banned = set(scope.get('packageCatalogExcluded', []))
    bad = []
    for plat, meta in d.items():
        for pkg in meta.get('packages', []):
            nm = pkg.get('name', '')
            if nm in banned or nm.startswith('aw-') or nm.startswith('lylink'):
                bad.append('%s/%s' % (plat, nm))
        if meta.get('packageCount') != len(meta.get('packages', [])):
            bad.append('%s:packageCount 与 packages 数不符' % plat)
    check(not bad, 'package_catalog 私有包已剔除', ','.join(bad[:5]) if bad else 'ok')


def stage_index_scope():
    p = os.path.join(BASE, 'rag_index.json')
    if not os.path.isfile(p):
        check(False, 'rag_index.json exists', p)
        return
    d = json.loads(io.open(p, encoding='utf-8').read())
    paths = {c.get('path', '').replace('\\', '/') for c in d.get('chunks', [])}
    # 允许的索引根 = kb_index_roots.ROOTS：knowledge/ + components/*/platforms.md + packages/**（2026-10-03 起
    # components/packages 也是索引根，见 kb_index_roots.py）。仍然要拦的是
    # **本机 wiki 镜像页**（路径形如 `about/README.md`、`uicontrols/*.md` 不带 knowledge/ 前缀）。
    allowed_prefixes = ('knowledge/', 'components/', 'packages/')
    out = sorted(pp for pp in paths if not pp.startswith(allowed_prefixes))
    check(not out, 'rag 索引只含随仓真源文档（knowledge/ + components/ + packages/，不含本机 wiki）',
          'ok' if not out else '越界: %s' % ','.join(out[:4]))


def main():
    scope = load_scope()
    print('=' * 72)
    print('FlyThings MCP release gate  (BASE=%s)' % BASE)
    print('=' * 72)
    stage_paths(scope)
    stage_words(scope)
    stage_privacy()
    stage_package_catalog(scope)
    stage_index_scope()
    fails = [r for r in RESULT if not r[0]]
    print('-' * 72)
    print('total=%d  fail=%d  %s' % (len(RESULT), len(fails), 'OK' if not fails else 'FAILED'))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
