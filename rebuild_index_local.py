# -*- coding: utf-8 -*-
"""用本地 bge-small-zh 模型重建 RAG 索引（离线，无需任何 API Key）。
用法：python rebuild_index_local.py <wiki根目录> [输出路径]
"""
import json, os, sys, time

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import embed_local

WIKI_ROOT = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\zkswe\.openclaw\workspace\wiki\flythings'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE, 'rag_index.json')
KNOWLEDGE_DIR = os.path.join(BASE, 'knowledge')  # 随仓库分发的实践知识文档（可公开部分）


def collect_roots():
    """索引根目录：显式参数 / 本地完整 wiki（官方文档+PDF 等内部资料，不进仓库）
    + 仓库内 knowledge/（实践知识文档，随 Gitee 分发，clone 后可重建索引）。"""
    roots = []
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        roots.append(os.path.abspath(sys.argv[1]))
    elif os.path.isdir(WIKI_ROOT):
        roots.append(WIKI_ROOT)
    if os.path.isdir(KNOWLEDGE_DIR):
        roots.append(KNOWLEDGE_DIR)
    return roots


def chunk_md(path):
    text = open(path, encoding='utf-8').read()
    lines = text.split('\n')
    chunks, cur = [], []
    for line in lines:
        if line.startswith('#') and cur:
            chunks.append('\n'.join(cur))
            cur = []
        cur.append(line)
        if sum(len(l) for l in cur) >= 800:
            chunks.append('\n'.join(cur))
            cur = []
    if cur:
        chunks.append('\n'.join(cur))
    return [c for c in chunks if len(c.strip()) > 40]


def main():
    if not embed_local.available():
        print('模型不可用，请先确认 models/bge-small-zh/ 存在')
        sys.exit(1)
    files = []  # (path, root)
    for root in collect_roots():
        for r, _, fnames in os.walk(root):
            for fn in fnames:
                if fn.endswith('.md'):
                    files.append((os.path.join(r, fn), root))
    print(f'{len(files)} md files from {len(collect_roots())} roots', flush=True)
    chunks = []
    for f, froot in sorted(files):
        rel = os.path.relpath(f, froot).replace('\\', '/')
        for i, c in enumerate(chunk_md(f)):
            chunks.append({'id': f'{rel}#{i}', 'path': rel, 'text': c})
    print(f'{len(chunks)} chunks', flush=True)

    t0 = time.time()
    for i, c in enumerate(chunks):
        c['embedding'] = embed_local.embed(c['text'])
        if (i + 1) % 50 == 0 or i == len(chunks) - 1:
            el = time.time() - t0
            print(f'{i + 1}/{len(chunks)} embedded ({el:.0f}s)', flush=True)

    json.dump({'model': 'bge-small-zh-v1.5-local', 'dim': 512, 'chunks': chunks},
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'saved -> {OUT} ({os.path.getsize(OUT) / 1024 / 1024:.1f} MB)', flush=True)


if __name__ == '__main__':
    main()
