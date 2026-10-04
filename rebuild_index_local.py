# -*- coding: utf-8 -*-
"""用本地 bge-small-zh 模型重建 RAG 索引（离线，无需任何 API Key）。
用法：python rebuild_index_local.py <wiki根目录> [输出路径]
      python rebuild_index_local.py --repo-only [输出路径]   # 只索引随仓文档（≈发布用索引）

`--repo-only`（2026-10-04 新增）：跳过**不在仓库里**的本地 wiki，只索引
`kb_index_roots.iter_repo_docs()` 那套（knowledge/ + components/*/platforms.md + packages/**）。
为什么要它：随仓的 `rag_index.json` 必须是**别人从干净 clone 就能复现**的东西 ——
带 wiki 重建会把仓外内容写进随仓索引（10-03 已定不做）。有了这个开关，
"改了 knowledge/ 就该重建索引"才有可执行的单一动作。
"""
import base64, json, os, sys, time

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import embed_local
import kb_local as _kbl
import kb_index_roots as bir

WIKI_ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser('~'), '.openclaw', 'workspace', 'wiki', 'flythings')
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


def save_index(chunks, dim, out):
    """写紧凑索引：chunks 只存 id/path/text，向量拼接成 float16 + base64 放 `embs`。

    相比旧格式（每个 chunk 内联明文 `embedding`）体积 22 MB → 5 MB，
    加载解析 0.4s → 0.1s；读取侧兼容旧格式（rag_search._load_vecs）。
    """
    import numpy as np
    embs = []
    for c in chunks:
        e = c.pop('embedding', None)
        if e is None:
            raise SystemExit('缺少 embedding，无法写紧凑格式')
        embs.append(np.asarray(e, dtype=np.float16))
    m = np.stack(embs).astype(np.float16) if embs else np.zeros((0, dim), np.float16)
    payload = {'model': 'bge-small-zh-v1.5-local', 'dim': int(dim),
               'embFormat': 'f16+base64',
               'embs': base64.b64encode(m.tobytes()).decode('ascii'),
               'chunks': chunks}
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)
    print('saved -> %s (%.1f MB)' % (out, os.path.getsize(out) / 1024 / 1024))


def repack(src, dst=None):
    """旧索引 → 紧凑格式（不需要跑模型，纯重编码）。"""
    dst = dst or src
    d = json.load(open(src, encoding='utf-8'))
    dim = int(d.get('dim') or 512)
    if d.get('embs'):
        print('已经是紧凑格式，无需重包:', src)
        return
    chunks = d['chunks']
    before = os.path.getsize(src) / 1024 / 1024
    save_index(chunks, dim, dst)
    print('repack: %.1f MB -> %.1f MB' % (before, os.path.getsize(dst) / 1024 / 1024))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--repack':
        src = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE, 'rag_index.json')
        repack(src, sys.argv[3] if len(sys.argv) > 3 else None)
        return
    if len(sys.argv) > 1 and sys.argv[1] == '--repack-all':
        repack(os.path.join(BASE, 'rag_index.json'))
        return
    if not embed_local.available():
        print('模型不可用，请先确认 models/bge-small-zh/ 存在')
        sys.exit(1)
    files = []  # (rel_path, abs_path)
    known = set()  # knowledge 内已有相对路径（如 esl/tag-esl.md），wiki 同名文档跳过避免重复
    skipped, local_n, bad = [], 0, []
    if os.path.isdir(KNOWLEDGE_DIR):
        # 索引范围唯一真源 = kb_index_roots.py（以前这段遍历口径在本文件与 check_consistency
        # 的 _expected_md_sets() 里各写一遍，加一类文档要改两处）。
        for base_rel, abs_path, spec in bir.iter_repo_docs(BASE):
            rel = (base_rel[len(spec['dir']) + 1:]
                   if base_rel.startswith(spec['dir'] + '/') else base_rel)
            # P1.5 状态过滤：draft/deprecated **不进索引**（review 可进但检索侧带标注）；
            # 无 front-matter 的资产文档（组件 platforms.md）按 kb_local.indexable 口径照旧保留。
            try:
                raw = open(abs_path, encoding='utf-8').read()
            except OSError as e:
                bad.append('%s（%s）' % (rel, e))
                continue
            meta, _b, _e = _kbl.parse_front_matter(raw)
            if not _kbl.indexable(meta):
                skipped.append('%s(%s)' % (rel, meta.get('status') or '无元数据'))
                continue
            known.add(rel)
            files.append((base_rel, abs_path))
    # P0-2：用户本地层/项目层也进索引 —— 否则 capture 出来的知识**用户自己都搜不到**
    for d in _kbl.local_docs(os.environ.get('FLYTHINGS_KB_DIR', '')):
        if d.get('path') and d.get('abs'):
            files.append((d['path'], d['abs']))
            local_n += 1
    if local_n:
        print('  并入本地层知识: %d 篇（源：%s）' % (local_n, _kbl.kb_dir()))
    if skipped:
        print('  跳过未进索引（draft/deprecated）: %d 篇：%s'
              % (len(skipped), ', '.join(skipped[:5])))
    if bad:
        print('  ⚠️ 读不了的文档（已跳过，不静默）: %s' % '; '.join(bad[:3]))
    if '--repo-only' not in sys.argv:
        for root in [rt for rt in collect_roots() if os.path.abspath(rt) != os.path.abspath(KNOWLEDGE_DIR)]:
            for r, _, fnames in os.walk(root):
                for fn in fnames:
                    if fn.endswith('.md'):
                        rel = os.path.relpath(os.path.join(r, fn), root).replace('\\', '/')
                        if rel in known:
                            continue  # knowledge 发布版优先，跳过本地同名
                        files.append((rel, os.path.join(r, fn)))
    else:
        print('  --repo-only：只索引随仓文档（knowledge/ + components/*/platforms.md + packages/**），不含本地 wiki',
              flush=True)
    print(f'{len(files)} md files ({len(known)} knowledge, deduped)', flush=True)
    chunks = []
    for rel, f in sorted(files):
        for i, c in enumerate(chunk_md(f)):
            chunks.append({'id': f'{rel}#{i}', 'path': rel, 'text': c})
    print(f'{len(chunks)} chunks', flush=True)

    t0 = time.time()
    for i, c in enumerate(chunks):
        c['embedding'] = embed_local.embed(c['text'])
        if (i + 1) % 50 == 0 or i == len(chunks) - 1:
            el = time.time() - t0
            print(f'{i + 1}/{len(chunks)} embedded ({el:.0f}s)', flush=True)

    save_index(chunks, 512, OUT)
    # P0-2：本地层自己的机读清单（检索侧合并用；与总账 kb_index.json 同形状子集）
    lidx = _kbl.build_local_index()
    print('  本地层清单 -> %s（%d 篇，源 %s）'
          % (_kbl.local_index_path(_kbl.kb_dir()), lidx['meta']['doc_count'], _kbl.kb_dir()),
          flush=True)


if __name__ == '__main__':
    main()
