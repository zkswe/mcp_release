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


def _bm25_search(q, k):
    """关键词检索兜底（本地模型不可用时）：词频 + 长度加权打分。"""
    tokens = [t for t in re.findall(r'[\w\u4e00-\u9fff]+', q.lower()) if len(t) > 1]
    if not tokens:
        return []
    scored = []
    for c in CHUNKS:
        text_l = c['text'].lower()
        score = 0.0
        for t in set(tokens):
            score += text_l.count(t) * (1.0 + math.log1p(len(t)))
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
