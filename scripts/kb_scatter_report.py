# -*- coding: utf-8 -*-
"""知识散落明细：同一概念的表述**到底有没有重复**（只读）。

和 `audit_baggage.py` 的分工：
  · audit_baggage   —— 量"包袱总量"（文件数/重复组/同名散落/概念散落篇数）
  · 本脚本          —— 把某个高散概念**拆开看**：共几处提及、其中哪些是**近似重复的表述**、
                       哪些只是各自语境里的合理引用。归集前必须先分清这两者——
                       "多处提及"不等于"重复"，把合理复述删掉是丢知识，不是归集。

输出每个概念的「表述族」：一族的成员文本相近（9 字滑窗 Jaccard ≥ 阈值）→ 这族就是候选收敛对象，
每组保留 1 处真源、其余改指针（或删冗余从句）。

用法：
    python scripts/kb_scatter_report.py                    # 全部概念
    python scripts/kb_scatter_report.py --concept 控件盒    # 只看某个
    python scripts/kb_scatter_report.py --th 0.35 --max 40
"""
import argparse
import collections
import io
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import kb_index_roots as bir                       # noqa: E402

CONCEPTS = [
    ('图片尺寸==控件盒', ('控件盒',)),
    ('activity 禁手改', ('mainActivity', 'src/activity')),
    ('分区/升级 img', ('update.img', '升级包')),
    ('UI 生命周期', ('onUI_show', 'onUI_init')),
    ('thumb 子盒', ('thumb',)),
    ('i18n 逐字节', ('逐字节',)),
    ('libc glibc/musl', ('glibc',)),
    ('配色/对比度', ('对比度',)),
    ('staleOnDevice', ('staleOnDevice',)),
    ('findControlByID', ('findControlByID',)),
]

# 归集时的常见噪音：纯指针行、表格行、front-matter、纯链接
NOISE = re.compile(r'^\s*(\||>|---|<!--|\S+\s*[:：]\s*$)')


def paragraphs(text):
    """切成段落（连续非空行），跳过 front-matter 与纯指针/表格块。"""
    if text.startswith('---'):
        end = text.find('\n---', 3)
        if end != -1:
            text = text[end + 4:]
    out, cur = [], []
    for ln in text.split('\n'):
        s = ln.rstrip()
        if not s.strip():
            if cur:
                out.append('\n'.join(cur))
                cur = []
            continue
        cur.append(s)
    if cur:
        out.append('\n'.join(cur))
    return [p for p in out if not all(NOISE.match(x) for x in p.split('\n'))]


def shingles(text, n=9):
    t = re.sub(r'[\s，。；：、（）()\[\]`*|/>\-—→「」]+', '', text)
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def jac(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--concept', help='只分析包含该词的概念')
    ap.add_argument('--th', type=float, default=0.4, help='近似重复阈值（Jaccard）')
    ap.add_argument('--max', type=int, default=6, help='每概念最多打印几族')
    ap.add_argument('--minlen', type=int, default=24, help='段落最短长度（过短的引用不算表述）')
    a = ap.parse_args()

    docs = {}
    for rel, abs_path, _spec in bir.iter_repo_docs(BASE):
        docs[rel] = io.open(abs_path, encoding='utf-8', errors='replace').read()

    total_pairs, total_fams = 0, 0
    for label, kws in CONCEPTS:
        if a.concept and a.concept not in label:
            continue
        hits = []                       # (doc, para_index, para_text)
        for rel, text in docs.items():
            for i, p in enumerate(paragraphs(text)):
                if any(k in p for k in kws) and len(p) >= a.minlen:
                    hits.append((rel, i, p))
        if not hits:
            continue
        sh = [shingles(h[2]) for h in hits]
        seen, fams = set(), []
        for i in range(len(hits)):
            if i in seen:
                continue
            fam = [i]
            for j in range(i + 1, len(hits)):
                if j in seen:
                    continue
                if jac(sh[i], sh[j]) >= a.th:
                    fam.append(j)
                    seen.add(j)
            seen.add(i)
            if len(fam) > 1:
                fams.append(fam)
        fams.sort(key=len, reverse=True)
        dup_paras = sum(len(f) for f in fams)
        total_pairs += dup_paras
        total_fams += len(fams)
        print('=' * 78)
        print('【%s】提及 %d 处（%d 篇文档）｜近似重复族 %d 族 / 涉及 %d 处 —— %s'
              % (label, len(hits), len({h[0] for h in hits}), len(fams), dup_paras,
                 '有真重复，值得收敛' if fams else '无近似重复 → 属合理复述，不必动'))
        for fam in fams[:a.max]:
            print('  ── 族（%d 处）：' % len(fam))
            for k in fam:
                rel, _i, p = hits[k]
                first = re.sub(r'\s+', ' ', p.strip())[:96]
                print('     %-52s %s' % (rel, first))
    print('=' * 78)
    print('合计：近似重复族 %d 族，涉及 %d 处段落（阈值 %.2f）' % (total_fams, total_pairs, a.th))
    return 0


if __name__ == '__main__':
    sys.exit(main())
