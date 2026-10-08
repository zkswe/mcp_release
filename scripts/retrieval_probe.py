# -*- coding: utf-8 -*-
"""单文档检索探针：给一篇文档 + 一批问法，报告它在 top-k 里排第几。

为什么要有它（2026-10-04）：给 61 篇「未登记问法」的文档补问法时，必须**先探再登记** ——
写一条用户真会说的话，然后用真实检索看它到底命中不命中那篇文档。
没有这个探针就只能"写完跑全量回归"（37 组跑一轮要分钟级），一篇一篇地迭代代价太高。

用法：
    python scripts/retrieval_probe.py knowledge/devflow/cli-fsc-toolchain.md "fun 怎么编译" "依赖怎么装"
    python scripts/retrieval_probe.py --doc <路径> --queries-file q.txt     # 一行一条问法
    python scripts/retrieval_probe.py --doc <路径> --k 5 "问法1" "问法2"

输出：每条问法一行 `rank=N  top3=[...]  <问法>`；rank=0 = top-k 未命中。
退出码：全命中 0（rank>=1 且 <=3）；有未进 top-3 的 → 1（便于脚本化筛选，不当门禁用）。
"""
import argparse
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)


def probe(doc, queries, k=5):
    import kb_tools
    out = []
    for q in queries:
        r = json.loads(kb_tools.flythings_knowledge_search(q, k=k))
        paths = [h['path'] for h in r.get('hits', [])]
        rank = paths.index(doc) + 1 if doc in paths else 0
        out.append((q, rank, paths[:3], r.get('quality')))
    return out


def main():
    ap = argparse.ArgumentParser()
    # ⚠️ `doc` 只做 `--doc` 选项（2026-10-04）：早先还挂了个同名位置参数，
    # argparse 会把多出来的位置参数**先填给 doc**，导致 `--doc X "问法"` 里的问法被吃掉
    # （子代理与本机各踩一次）。同一个东西只留一种写法。
    ap.add_argument('--doc', dest='doc2', required=True, help='仓库相对路径（如 knowledge/devflow/cli-fsc-toolchain.md）')
    ap.add_argument('--queries-file', default='', help='问法文件，一行一条')
    ap.add_argument('--k', type=int, default=5)
    ap.add_argument('queries', nargs='*')
    a = ap.parse_args()
    doc = a.doc2
    qs = list(a.queries)
    if a.queries_file:
        qs += [l.strip() for l in io.open(a.queries_file, encoding='utf-8') if l.strip()]
    if not doc or not qs:
        ap.error('需要 --doc <路径> 和至少一条问法')
    rows = probe(doc, qs, a.k)
    bad = 0
    for q, rank, top3, quality in rows:
        mark = 'OK ' if 1 <= rank <= 3 else '!! '
        if not (1 <= rank <= 3):
            bad += 1
        print('%srank=%d  %-28s %s' % (mark, rank, q[:26], [p.split('/')[-1] for p in top3]))
    print('-' * 60)
    print('%s：%d/%d 进 top-3（k=%d）' % (doc, len(rows) - bad, len(rows), a.k))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
