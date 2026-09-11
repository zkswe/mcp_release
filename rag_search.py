# -*- coding: utf-8 -*-
"""FlyThings_mcp_open: RAG 检索（完全本地，零 Key 零远程）。

检索策略（自动降级）：
1. 内置 bge-small-zh 本地模型可用 → 向量检索（推荐，免任何 Key）
2. 模型缺失/加载失败 → BM25 关键词检索兜底

知识库索引（rag_index.json）由本地模型预计算，完全离线。
"""
import json, math, os, re, sys

# PyInstaller 打包后数据文件在 _MEIPASS；正常运行时在脚本同目录
_BASE = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
IDX = os.path.join(_BASE, 'rag_index.json')
WIKI_ROOT = os.path.join(_BASE, 'wiki', 'flythings')

data = json.load(open(IDX, encoding='utf-8'))
CHUNKS = data['chunks']
_BY_ID = {c['id']: c for c in CHUNKS}  # RRF 融合用 id 映射（模块级建一次）

_embedder = None  # None=未尝试加载, False=不可用, 模块=可用


def _get_embedder():
    """延迟加载本地 embedding 模型；不可用返回 None（走 BM25 兜底）。"""
    global _embedder
    if _embedder is None:
        try:
            import embed_local
            if embed_local.available():
                _embedder = embed_local
            else:
                _embedder = False
        except Exception:
            _embedder = False
    return _embedder if _embedder else None


def cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b)) + 1e-12)


_ASCII_RE = re.compile(r'[a-z0-9_#+.\-]{2,}')
_CJK_RE = re.compile(r'[\u3400-\u9fff]+')


def query_tokens(q):
    """查询切词（**单一实现**：BM25 与 kb_tools 的覆盖率判定共用）。

    ASCII 词取 ≥2 字符；中文用**字级 bigram**。
    为何必须 bigram（检讨报告 §3.7）：原 BM25 把整段连续中文当一个 token，
    『Z20 屏幕截图怎么抓』会切出 '屏幕截图怎么抓' 这种超长 token，
    只有正文原样出现才命中 → 模型不可用降级 BM25 时召回明显掉。
    """
    ql = (q or '').lower()
    toks = set(_ASCII_RE.findall(ql))
    for run in _CJK_RE.findall(ql):
        if len(run) == 1:
            toks.add(run)
        else:
            toks.update(run[i:i + 2] for i in range(len(run) - 1))
    return toks


_BM25_K1 = 1.5
_BM25_B = 0.75
_DF = {}      # token -> 文档频次缓存（索引在进程内不变，可长期复用）


def _df_of(t):
    v = _DF.get(t)
    if v is None:
        v = sum(1 for c in CHUNKS if t in c['text'].lower())
        _DF[t] = v
    return v


def _bm25_search(q, k):
    """BM25 关键词检索：字级 bigram + IDF + 长度归一 + 路径/标题加权。

    相比原实现（裸词频计数，无 IDF/长度归一），评分口径向标准 BM25 靠齐，
    并对「命中文件名/目录名」与「命中首段标题」加权——实践中这两个信号的
    准确率远高于正文里偶然出现一次。
    """
    toks = sorted(query_tokens(q))
    if not toks:
        return []
    n = len(CHUNKS)
    avgdl = sum(len(c['text']) for c in CHUNKS) / float(max(1, n))
    scored = []
    for c in CHUNKS:
        tl = c['text'].lower()
        dl = len(tl)
        head = tl[:120]
        path = (c.get('path') or '').lower()
        score = 0.0
        for t in toks:
            tf = tl.count(t)
            if not tf:
                continue
            df = _df_of(t)
            idf = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
            score += idf * (tf * (_BM25_K1 + 1)) / \
                (tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * dl / avgdl))
            if t in path:
                score += idf * 2.0
            if t in head:
                score += idf * 0.5
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:k]


def search(q, k=3):
    """检索：向量 + BM25 混合融合（RRF），模型不可用时自动降级纯 BM25。

    2026-09-07 修改：原纯向量模式对「自然语言 + 缩写/专名混合查询」偏弱
    （如『V85x 如何切换 USB OTG』——向量命中 Z21 通用文档，BM25 才能命中
    v85x/usb-gadget-storage）。现改为两路 top-N 经 RRF 融合，双向互补：
    向量抓语义近邻、BM25 抓关键词精确命中，专名/缩写查询命中率显著提升。
    """
    emb = _get_embedder()
    if emb is not None:
        try:
            qv = emb.embed(q)
            vec = sorted(((cos(qv, c['embedding']), c) for c in CHUNKS),
                         key=lambda x: x[0], reverse=True)[:_TOPN]
            kw = _bm25_search(q, _TOPN)
            if not kw:
                return vec[:k]
            return _rrf_fuse(vec, kw, k)
        except Exception:
            pass  # 模型推理失败 → BM25 兜底
    return _bm25_search(q, k)


_TOPN = 40  # 混合融合：两路各取前 40 再 RRF
_K = 60  # RRF 平滑常数


def _rrf_fuse(vec, kw, k):
    """Reciprocal Rank Fusion：两路 (score, chunk) 列表按 chunk id 合并重排。
    返回 (融合分, chunk)，分数为 RRF 分（非相似度，仅用于排序展示）。"""
    rank = {}
    for lst in (vec, kw):
        for i, (_, c) in enumerate(lst):
            rank[c['id']] = rank.get(c['id'], 0.0) + 1.0 / (_K + i + 1)
    ids = sorted(rank, key=lambda x: rank[x], reverse=True)[:k]
    return [(rank[i], _BY_ID[i]) for i in ids]
