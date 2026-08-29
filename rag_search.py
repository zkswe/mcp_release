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
    """检索：本地模型向量优先，模型不可用自动降级 BM25 关键词。"""
    emb = _get_embedder()
    if emb is not None:
        try:
            qv = emb.embed(q)
            scored = sorted(((cos(qv, c['embedding']), c) for c in CHUNKS),
                            key=lambda x: x[0], reverse=True)
            return scored[:k]
        except Exception:
            pass  # 模型推理失败 → BM25 兜底
    return _bm25_search(q, k)
