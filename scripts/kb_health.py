# -*- coding: utf-8 -*-
"""知识体检看板（P2）：把「知识库现在什么样」聚成一份机读 + 人读报告。

用法：
    python scripts/kb_health.py            # 生成 knowledge/_reports/kb_health.{json,md}
    python scripts/kb_health.py --check    # 只校验看板是否滞后（kb_index 源哈希），进 CI
    python scripts/kb_health.py --json out.json

看板内容（一次看全）：
  规模与状态 / 证据覆盖 / 时效（stale·aging）/ 冲突与重复 / 检索问法登记 / 未命中缺口 top-N /
  待补判据队列（backlog，按"无问法优先"排序）/ 上次复验结果 / 本地层规模
"""
import argparse
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, 'scripts'))
import kb_local as kbl          # noqa: E402

REPORT_DIR = os.path.join(kbl.TOTAL_KB, '_reports')


def _retrieval_stats():
    p = os.path.join(BASE, 'scripts', 'check_retrieval.py')
    try:
        src = io.open(p, encoding='utf-8').read()
    except OSError as e:
        return {'error': str(e)}
    groups = re.findall(r"'doc':\s*'([^']+)'", src)
    q = re.findall(r"'([^']{2,60})',\s*\n", src)
    return {'groups': len(groups), 'docsRegistered': sorted(set(groups)),
            'queriesApprox': len(q)}


def build():
    idx = kbl.load_json(os.path.join(kbl.TOTAL_KB, 'kb_index.json'))
    s = idx.get('summary') or {}
    docs = idx.get('docs') or []
    ver = kbl.load_json(os.path.join(REPORT_DIR, 'kb_verify.json'))
    conf = kbl.load_json(os.path.join(REPORT_DIR, 'kb_conflict.json'))
    gaps = kbl.gaps(20)
    backlog = sorted([{'path': d.get('path'), 'id': d.get('id'),
                       'category': d.get('category'),
                       'hasQueries': d.get('hasQueries'),
                       'freshness': d.get('freshness')}
                      for d in docs if d.get('needsEvidence')],
                     key=lambda x: (x['hasQueries'], x['path'] or ''))
    stale = [d.get('path') for d in docs if d.get('stale')]
    aging = [d.get('path') for d in docs if d.get('freshness') == 'aging']
    by_cat = {}
    for d in docs:
        c = by_cat.setdefault(d.get('category') or '?', {'total': 0, 'verified': 0,
                                                         'review': 0, 'withEvidence': 0})
        c['total'] += 1
        c[d.get('status') or '?'] = c.get(d.get('status') or '?', 0) + 1
        if d.get('evidenceLevel') == 'has-evidence':
            c['withEvidence'] += 1
    return {
        'generatedAt': kbl._now(),
        'indexMeta': idx.get('meta') or {},
        'scale': {'total': s.get('total'), 'byStatus': s.get('byStatus') or {},
                  'byCategory': by_cat, 'inbox': s.get('inbox')},
        'evidence': {'withEvidence': s.get('withEvidence'), 'needsEvidence': s.get('needsEvidence'),
                     'manualOnly': s.get('manualOnly', s.get('needsEvidence'))},
        'freshness': {'stale': stale, 'aging': aging, 'staleCount': len(stale),
                      'agingCount': len(aging)},
        'quality': {'conflictCount': conf.get('conflictCount', 0),
                    'duplicateCount': conf.get('duplicateCount', 0),
                    'conflicts': [c.get('subject') for c in (conf.get('polarity') or [])][:10],
                    'conflictReportAt': conf.get('scannedAt', '')},
        'retrieval': {'registeredDocs': s.get('total', 0) - (s.get('noQueries') or 0),
                      'noQueries': s.get('noQueries'), **(  _retrieval_stats())},
        'gaps': {'totalLogged': gaps.get('totalLogged'), 'uniqueGaps': gaps.get('uniqueGaps'),
                 'top': [{'query': i['query'], 'count': i['count']} for i in
                         (gaps.get('items') or [])[:10]]},
        'lastVerify': {'at': ver.get('verifiedAt'), 'summary': ver.get('summary')},
        'backlog': backlog[:40], 'backlogCount': len(backlog),
        'localLayer': {'dir': kbl.kb_dir(),
                       'index': kbl.load_json(kbl.local_index_path(kbl.kb_dir())).get('summary', {})},
    }


def markdown(h):
    L = ['# 知识库体检（kb_health）', '',
         '> 生成时间：%s ｜ 索引源哈希：%s ｜ 篇数：%s'
         % (h['generatedAt'], (h['indexMeta'].get('source_hash') or '')[:12],
            h['scale']['total']), '']
    L += ['## 一、规模与状态', '',
          '- 状态分布：%s' % ', '.join('%s=%d' % kv for kv in
                                       sorted((h['scale']['byStatus'] or {}).items())),
          '- 候选区（inbox）：%s ｜ 本地层：%s' % (h['scale']['inbox'],
                                                 json.dumps(h['localLayer']['index'],
                                                            ensure_ascii=False)),
          '', '| 分类 | 篇数 | verified | review | 带证据 |', '|---|---|---|---|---|']
    for c, v in sorted((h['scale']['byCategory'] or {}).items()):
        L.append('| %s | %s | %s | %s | %s |' % (c, v.get('total'), v.get('verified', 0),
                                                 v.get('review', 0), v.get('withEvidence', 0)))
    L += ['', '## 二、证据与时效', '',
          '- 带可执行证据：**%s** ｜ 待补判据：**%s**' % (h['evidence']['withEvidence'],
                                                        h['evidence']['needsEvidence']),
          '- 过期（stale）：%d ｜ 接近复验（aging）：%d' % (h['freshness']['staleCount'],
                                                          h['freshness']['agingCount']),
          '- 上次复验：%s ｜ 结果 %s' % (h['lastVerify']['at'] or '（未跑）',
                                       json.dumps(h['lastVerify']['summary'] or {}, ensure_ascii=False)),
          '', '## 三、质量（冲突 / 重复）', '',
          '- 极性冲突：**%d** ｜ 疑似重复：**%d**（报告 %s）'
          % (h['quality']['conflictCount'], h['quality']['duplicateCount'],
             h['quality']['conflictReportAt'] or '未生成'),
          '- 冲突主语（前 10）：%s' % ('、'.join(h['quality']['conflicts']) or '（无）'),
          '', '## 四、检索与缺口', '',
          '- 已登记问法的文档：%s ｜ 无问法登记：%s'
          % (h['retrieval'].get('registeredDocs'), h['retrieval'].get('noQueries')),
          '- 未命中累计 %s 次 / 去重 %s 条；top 10 在下方 backlog 之后'
          % (h['gaps']['totalLogged'], h['gaps']['uniqueGaps']),
          '', '## 五、待补判据队列（backlog，前 40；无问法优先）', '']
    for b in h['backlog'][:40]:
        L.append('- `%s` ｜ %s ｜ 有问法=%s ｜ %s'
                 % (b['path'], b['category'], b['hasQueries'], b['freshness']))
    if not h['backlog']:
        L.append('（空）')
    L += ['', '## 六、未命中缺口 top 10（下一批写作清单）', '']
    for g in h['gaps']['top']:
        L.append('- x%d %s' % (g['count'], g['query']))
    if not h['gaps']['top']:
        L.append('（暂无）')
    return '\n'.join(L) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='只校验看板是否滞后（kb_index 源哈希）')
    ap.add_argument('--json', default='')
    ap.add_argument('--md', default='')
    a = ap.parse_args()
    os.makedirs(REPORT_DIR, exist_ok=True)
    h = build()
    if a.check:
        jp = os.path.join(REPORT_DIR, 'kb_health.json')
        if not os.path.isfile(jp):
            print('[FAIL] 缺 kb_health.json（生成：python scripts/kb_health.py）')
            return 1
        try:
            old = json.load(io.open(jp, encoding='utf-8'))
        except ValueError as e:
            print('[FAIL] kb_health.json 解析失败: %s' % e)
            return 1
        if (old.get('indexMeta') or {}).get('source_hash') != h['indexMeta'].get('source_hash'):
            print('[FAIL] kb_health 滞后于 kb_index（%s ≠ %s）→ 重跑 kb_health.py'
                  % ((old.get('indexMeta') or {}).get('source_hash'),
                     h['indexMeta'].get('source_hash')))
            return 1
        print('[PASS] kb_health 与当前 kb_index 一致（%s）'
              % (h['indexMeta'].get('source_hash') or '')[:12])
        return 0
    jp = a.json or os.path.join(REPORT_DIR, 'kb_health.json')
    mp = a.md or os.path.join(REPORT_DIR, 'kb_health.md')
    with io.open(jp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(h, f, ensure_ascii=False, indent=1)
    with io.open(mp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(markdown(h))
    print('体检：%s 篇 ｜ verified %s ｜ 带证据 %s ｜ 冲突 %s ｜ 过期 %s ｜ backlog %s'
          % (h['scale']['total'], (h['scale']['byStatus'] or {}).get('verified'),
             h['evidence']['withEvidence'], h['quality']['conflictCount'],
             h['freshness']['staleCount'], h['backlogCount']))
    print('报告 ->', jp, '/', mp)
    return 0


if __name__ == '__main__':
    sys.exit(main())
