# -*- coding: utf-8 -*-
"""知识缺口清单（kb_gaps）：把「检索未命中日志」聚合成下一批写作清单。

用法：
    python scripts/kb_gaps.py                          # 默认读本地层日志，写本地层 _reports/kb_gaps.md
    python scripts/kb_gaps.py --kb-dir <dir>           # 指定本地层目录
    python scripts/kb_gaps.py --project <项目根>        # 额外合并项目层日志
    python scripts/kb_gaps.py --out kb_gaps.md --limit 30

口径：**用户真的问不到的东西**才驱动写作 —— 不是让 AI 自由发挥写文档。
     未命中日志只存用户本机（`<本地层>/_logs/no_hit.jsonl`），不外发；回流只带哈希（P3）。
"""
import argparse
import io
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import kb_local as kbl          # noqa: E402


def collect(kb_override='', project_root=''):
    dirs = [kbl.kb_dir(kb_override)]
    pd = kbl.project_dir(project_root) if project_root else ''
    if pd:
        dirs.append(pd)
    total, agg = 0, {}
    for d in dirs:
        rows = kbl.read_jsonl(os.path.join(d, '_logs', 'no_hit.jsonl'))
        for r in rows:
            total += 1
            key = r.get('qnorm') or kbl.normalize_symptom(r.get('query'))
            if not key:
                continue
            a = agg.setdefault(key, {'query': r.get('query', ''), 'count': 0,
                                     'first': r.get('ts', ''), 'last': r.get('ts', ''),
                                     'quality': r.get('quality', '')})
            a['count'] += 1
            a['last'] = r.get('ts', '') or a['last']
    return total, agg, dirs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--kb-dir', default='')
    ap.add_argument('--project', default='')
    ap.add_argument('--limit', type=int, default=20)
    ap.add_argument('--out', default='')
    a = ap.parse_args()
    total, agg, dirs = collect(a.kb_dir, a.project)
    items = sorted(agg.values(), key=lambda x: (-x['count'], x['query']))[:a.limit]
    g = {'success': True, 'totalLogged': total, 'uniqueGaps': len(agg), 'items': items,
         'logDirs': dirs}
    md = kbl.gaps_markdown(g)
    out = a.out or os.path.join(kbl._ensure(kbl.kb_dir(a.kb_dir)), '_reports', 'kb_gaps.md')
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with io.open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(md)
    print('未命中累计 %d 次 / 去重 %d 条 ｜ 日志目录: %s' % (total, len(agg), ', '.join(dirs)))
    for i, it in enumerate(items[:10], 1):
        print('  %2d. x%-3d %s' % (i, it['count'], it['query'][:70]))
    print('清单 ->', out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
