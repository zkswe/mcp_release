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
    files = []
    for root, _, fnames in os.walk(WIKI_ROOT):
        for fn in fnames:
            if fn.endswith('.md'):
                files.append(os.path.join(root, fn))
    print(f'{len(files)} md files', flush=True)
    chunks = []
    for f in sorted(files):
        rel = os.path.relpath(f, WIKI_ROOT).replace('\\', '/')
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
