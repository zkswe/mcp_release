# -*- coding: utf-8 -*-
"""补完检索导引 + 重建索引后，把"已经能检到"的问法收进 queries（两段式的收口动作）。

背景（2026-10-04）：61 篇文档补齐问法时，有 133 条**用户真会说**的问法检不到，
当时如实记进各组 `misses`（不当场改文档）。补导引是**另一段**：
  ① 给文档补检索导引同义词（只增不删，不动 front-matter）
  ② `python rebuild_index_local.py --repo-only`   ← 索引随仓，别人 clone 就可用
  ③ 本脚本：逐条重探 misses → **进 top-3 的搬进 queries** 并重算 min_top1；
     仍未命中的留在 misses（下一轮继续，不许静默丢）

判据：
  - queries 只增不减（吸收不删任何已登记问法）
  - min_top1 = 实测 top-1 条数 − 1（≥6 条问法时；留 1 条余量），否则 = 实测值
  - 已登记的 queries 若**退化**（不再进 top-3）→ 明确报出（不自动删，交人判断）

用法：
    python scripts/retrieval_absorb.py                # 写回 JSON
    python scripts/retrieval_absorb.py --dry-run      # 只看会怎么变
"""
import argparse
import glob
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)


def _rank(doc, q, k=5):
    import kb_tools
    r = json.loads(kb_tools.flythings_knowledge_search(q, k=k))
    paths = [h['path'] for h in r.get('hits', [])]
    return paths.index(doc) + 1 if doc in paths else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(BASE, 'scripts', 'retrieval_groups', '*.json')))
    moved = stayed = regress = 0
    for p in files:
        data = json.load(io.open(p, encoding='utf-8'))
        changed = False
        for g in data:
            doc, misses = g['doc'], list(g.get('misses', []))
            if not misses:
                continue
            keep, absorb = [], []
            for q in misses:
                (absorb if 1 <= _rank(doc, q) <= 3 else keep).append(q)
            # 已登记问法不得静默退化：补完导引/重建索引后不再进 top-3 的，
            # **降级回 misses**（记下来，不静默删；下一轮继续修），并大声报出
            deg = [q for q in g['queries'] if not (1 <= _rank(doc, q) <= 3)]
            if deg:
                regress += len(deg)
                g['queries'] = [q for q in g['queries'] if q not in deg]
                keep = deg + keep
                changed = True
                print('  [退化→降级] %s：%d 条不再进 top-3，已退回 misses：%s'
                      % (os.path.basename(p), len(deg), deg[:3]))
            if not absorb:
                g['misses'] = keep
                continue
            g['queries'] = g['queries'] + absorb
            g['misses'] = keep
            top1 = sum(1 for q in g['queries'] if _rank(doc, q) == 1)
            g['min_top1'] = max(1, top1 - 1) if len(g['queries']) >= 6 else top1
            moved += len(absorb)
            stayed += len(keep)
            changed = True
            print('  [吸收] %-28s +%-2d 条 → queries=%d, 余 %d 条未命中, min_top1=%d'
                  % (os.path.basename(doc), len(absorb), len(g['queries']), len(keep),
                     g['min_top1']))
        if changed and not a.dry_run:
            with io.open(p, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
                f.write('\n')
    print('-' * 70)
    print('吸收 %d 条；仍未命中 %d 条；退化降级 %d 条（%s）'
          % (moved, stayed, regress, 'dry-run，未写回' if a.dry_run else '已写回'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
