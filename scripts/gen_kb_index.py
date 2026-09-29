# -*- coding: utf-8 -*-
"""生成 / 校验 `knowledge/kb_index.json`（机读清单：看板、CI、检索过滤都靠它）。

用法：
    python scripts/gen_kb_index.py            # 生成（改知识/改 front-matter 后必跑）
    python scripts/gen_kb_index.py --check    # 校验磁盘与索引一致（门禁委派项）

索引内容：
  meta   {schema, built_at, mcp_version, doc_count, source_hash}   ← 源哈希，不靠 mtime 判新鲜
  summary{total, byCategory, byStatus, withEvidence, needsEvidence, noQueries, stale}
  docs[] {id, path, title, category, platforms, tags, status, confidence, verified_at,
          stale_days, origin, evidenceCount, needsEvidence, hasQueries, bytes, sha256,
          fingerprint, ageDays}
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import kb_local as kbl          # noqa: E402

INDEX_PATH = os.path.join(kbl.TOTAL_KB, 'kb_index.json')
CATEGORIES = ('devflow', 'uicontrols', 'hardware', 'esl', 't113-car', 'v85x')


def _queries_registered():
    """从 check_retrieval.py 的 GROUPS 读已登记问法的文档（单一来源，不手抄）。"""
    p = os.path.join(BASE, 'scripts', 'check_retrieval.py')
    src = io.open(p, encoding='utf-8').read()
    return set(re.findall(r"'doc':\s*'([^']+)'", src))


def _version():
    try:
        import kb_tools
        return kb_tools.MCP_VERSION
    except Exception as e:                      # 环形导入/环境异常时如实标
        return 'unknown(%s)' % type(e).__name__


def build():
    docs, hasher = [], hashlib.sha256()
    registered = _queries_registered()
    counts = {'total': 0, 'byCategory': {}, 'byStatus': {}, 'withEvidence': 0,
              'needsEvidence': 0, 'noQueries': 0, 'stale': 0, 'inbox': 0, 'aging': 0}
    for cat in CATEGORIES:
        d = os.path.join(kbl.TOTAL_KB, cat)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith('.md') or f == 'README.md':
                continue
            p = os.path.join(d, f)
            raw = io.open(p, encoding='utf-8').read()
            meta, _body, ferr = kbl.parse_front_matter(raw)
            rel = os.path.relpath(p, BASE).replace(os.sep, '/')
            sha = hashlib.sha256(raw.encode('utf-8')).hexdigest()
            hasher.update(('%s|%s\n' % (rel, sha)).encode('utf-8'))
            age = None
            vd = str(meta.get('verified_at') or '')
            if len(vd) >= 10:
                try:
                    age = int((time.mktime(time.strptime(time.strftime('%Y-%m-%d'), '%Y-%m-%d'))
                               - time.mktime(time.strptime(vd[:10], '%Y-%m-%d'))) // 86400)
                except ValueError:
                    age = None
            fr, age = kbl.freshness(meta)
            ev = meta.get('evidence') or []
            ev_level = ('has-evidence' if ev else
                        ('manual-only' if meta.get('needs_evidence') else 'none'))
            row = {'id': meta.get('id'), 'path': rel, 'title': meta.get('title'),
                   'category': meta.get('category') or cat,
                   'platforms': meta.get('platforms') or [], 'tags': meta.get('tags') or [],
                   'status': meta.get('status') or 'draft',
                   'confidence': meta.get('confidence') or 'unverified',
                   'verified_at': vd, 'stale_days': meta.get('stale_days'),
                   'origin': meta.get('origin') or 'total',
                   'evidenceCount': len(ev), 'evidence': ev,
                   'evidenceLevel': ev_level,
                   'needsEvidence': bool(meta.get('needs_evidence')),
                   'hasQueries': rel in registered, 'bytes': len(raw.encode('utf-8')),
                   'sha256': sha, 'fingerprint': kbl.fingerprint(meta),
                   'ageDays': age, 'freshness': fr, 'stale': (fr == 'stale'),
                   'staleDays': int(meta.get('stale_days') or 180),
                   'frontMatterError': ferr}
            docs.append(row)
            counts['total'] += 1
            counts['byCategory'][cat] = counts['byCategory'].get(cat, 0) + 1
            counts['byStatus'][row['status']] = counts['byStatus'].get(row['status'], 0) + 1
            if ev:
                counts['withEvidence'] += 1
            if ev_level == 'manual-only':
                counts['manualOnly'] = counts.get('manualOnly', 0) + 1
            if row['needsEvidence']:
                counts['needsEvidence'] += 1
            if not row['hasQueries']:
                counts['noQueries'] += 1
            if isinstance(age, int) and meta.get('stale_days') and age > int(meta['stale_days']):
                counts['stale'] += 1
            elif fr == 'aging':
                counts['aging'] = counts.get('aging', 0) + 1
    inbox = os.path.join(kbl.TOTAL_KB, 'inbox')
    if os.path.isdir(inbox):
        counts['inbox'] = len([f for f in os.listdir(inbox)
                               if f.endswith('.md') and f != 'README.md'])
    return {'meta': {'schema': kbl.SCHEMA_VERSION, 'built_at': kbl._now(),
                     'mcp_version': _version(), 'doc_count': counts['total'],
                     'source_hash': hasher.hexdigest()[:32]},
            'summary': counts, 'docs': docs}


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    new = build()
    if a.check:
        if not os.path.isfile(INDEX_PATH):
            print('[FAIL] 缺 %s（生成：python scripts/gen_kb_index.py）' % INDEX_PATH)
            return 1
        old = json.load(io.open(INDEX_PATH, encoding='utf-8'))
        if old.get('meta', {}).get('source_hash') != new['meta']['source_hash'] or \
                old.get('meta', {}).get('doc_count') != new['meta']['doc_count']:
            print('[FAIL] kb_index.json 与知识文档不一致（源哈希 %s ≠ %s）—— 重跑 gen_kb_index.py'
                  % (old.get('meta', {}).get('source_hash'), new['meta']['source_hash']))
            return 1
        print('[PASS] kb_index.json in sync（%s, %d 篇）'
              % (new['meta']['source_hash'][:12], new['meta']['doc_count']))
        return 0
    with io.open(INDEX_PATH, 'w', encoding='utf-8', newline='\n') as f:
        f.write(dumps(new))
    s = new['summary']
    print('kb_index -> %s（%d 篇 ｜ verified %d ｜ 带证据 %d ｜ 待补证据 %d ｜ 无问法登记 %d ｜ 超期 %d ｜ inbox %d）'
          % (INDEX_PATH, s['total'], s['byStatus'].get('verified', 0), s['withEvidence'],
             s['needsEvidence'], s['noQueries'], s['stale'], s['inbox']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
