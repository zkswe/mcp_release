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

# ---- 中文口语 → 文档里的英文专名（只为 BM25 的「文件名/目录名加权」服务）----
# 为何要它（2026-09-19 实测）：目标文档叫 listview-wheel-picker.md，而用户只会说「滚轮/转盘」；
# BM25 对「命中路径」权重是 idf×2，但没有 token 就永远拿不到这份权重。
# 只作用在 _bm25_search 内，**不动 query_tokens**（覆盖率判定与 BM25 必须共用同一套切词，
# 否则 kb_tools 的 quality 标记会失真）。
_ALIAS = {
    '滚轮': ('wheel', 'roller'), '转盘': ('wheel',), '轮子': ('wheel',),
    '轮选': ('wheel',), '选择器': ('picker',), '选择条': ('picker',),
    '时钟盘': ('timepicker', 'dial'), '时间选择': ('timepicker', 'timeedit'),
    '日期时间选择': ('timepicker', 'timeedit'),
}


def _alias_tokens(q):
    ql = (q or '').lower()
    out = set()
    for k, vs in _ALIAS.items():
        if k in ql:
            out.update(vs)
    return out


# ---- 专名（rare term）优先：bge-small-zh 对英文控件名不敏感，靠 BM25 精确命中兜底 ----
_RARE_MINLEN = 4          # 专名最短长度（z20/t113 这类 3 字符平台名太短，不参与）
_RARE_DF_RATIO = 0.02     # 在 ≤2% 的 chunk 中出现 → 视为判别性专名


def _rare_terms(q):
    """查询里的判别性专名（如 qtimeedit / listwheel / numberpicker / pickerview）。

    为何要它（2026-09-19 实测）：向量路把「英文控件名 + 中文问法」当普通语义，
    常把通用文档排前（『QTimeEdit 怎么做』向量路 top3 全是 devflow 通用文档，
    目标文档压根不在 top-40），BM25 路却能精确命中第 1；两路 RRF 融合后目标文档被挤到 #4。
    → 在融合结果上把「含专名的片段」提前（**重排，不丢弃**，无召回损失）。
    """
    n = len(CHUNKS) or 1
    out = []
    for t in query_tokens(q):
        if len(t) >= _RARE_MINLEN and t.isascii() and _df_of(t) <= _RARE_DF_RATIO * n:
            out.append(t)
    return out


def _prefer_rare(fused, q):
    """含专名的片段提前；无专名 / 专名无命中 → 原样返回（不改变原行为）。"""
    rare = _rare_terms(q)
    if not rare or not fused:
        return fused

    def _has(c):
        t = (c.get('text') or '').lower()
        return any(r in t or r in (c.get('path') or '').lower() for r in rare)

    yes = [x for x in fused if _has(x[1])]
    if not yes:
        return fused
    return yes + [x for x in fused if not _has(x[1])]


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
    toks = sorted(set(query_tokens(q)) | _alias_tokens(q))
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

    2026-09-19 补充（钟工「检索质量优化」）：融合后再做一次**专名优先重排**
    （见 `_prefer_rare`）—— 英文控件名这类判别性专名在向量路几乎不起作用，
    必须在融合结果里把「含该专名的片段」提前；BM25 另加中文口语别名扩展
    （`_alias_tokens`，如 滚轮→wheel/roller）以吃到「命中文件名」那份额外权重。
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
            return _prefer_rare(_rrf_fuse(vec, kw, _TOPN), q)[:k]
        except Exception:
            pass  # 模型推理失败 → BM25 兜底
    # 降级路同样做专名优先（两路行为一致，便于回归用例在无模型机器上也全绿）
    return _prefer_rare(_bm25_search(q, _TOPN), q)[:k]


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
