# -*- coding: utf-8 -*-
"""「哪些文档进检索索引」的唯一机器可读真源。

为什么要有它（2026-10-02）：这条口径原本被抄在两处——`rebuild_index_local.py` 里走一遍
`knowledge/`，`scripts/check_consistency.py` 的 `_expected_md_sets()` 又照着"同口径"再走一遍。
于是"给检索加一类文档"要改两处、漏一处就漂移。现在两处都从这里派生。

同时它修掉一个**检索黑洞**：`components/*/platforms.md`（16 篇 / 1779 行：组件在各平台的
可用性、前置条件、已知限制、真机验收方法）是 AI 选型与验收必须用的知识，但它在 `knowledge/`
之外——**不索引就等于 AI 检索不到**（实测：问「Z20 上能跑哪些组件」返回全不相干文档）。

消费方：
  - `rebuild_index_local.py`          → 建 `rag_index.json`（真正被检索的东西）
  - `scripts/check_consistency.py`    → `stage_index` 覆盖度门禁（索引集合 == 磁盘集合）

用法：
    import kb_index_roots as bir
    bir.iter_repo_docs(BASE)     # → [(仓库相对路径, 绝对路径, 根规格)]，**进索引**的文档
    bir.repo_rel_docs(BASE)      # → {仓库相对路径}（覆盖度门禁算期望集用）
"""
import fnmatch
import os

SCHEMA_VERSION = '1.0'
UPDATED = '2026-10-02'
AUTHORITY = (
    '「哪些仓库内文档进检索索引」的唯一真源。rebuild_index_local.py 与 '
    'scripts/check_consistency.py 的覆盖度门禁都从这里派生——**不要在两处各写一遍遍历口径**。'
    '只写「仓库内随包分发」的文档；本机 wiki（官方镜像，不进仓库）仍由 rebuild_index_local '
    '单独处理（它不在仓库里）。')

# 每个根：dir 相对仓库根；include 是文件名 glob；skipDirs 是相对 dir 的路径段黑名单。
ROOTS = [
    {
        'id': 'knowledge',
        'dir': 'knowledge',
        'include': ('*.md',),
        'skipDirs': ('inbox', '_reports', '_logs'),
        'why': ('随仓库分发的实践知识。inbox/_reports/_logs 是候选区/日志/报告——'
                '可见但不当依据，不进索引（见 knowledge/devflow/kb-growth.md）。'
                'draft/deprecated 由 front-matter 状态门禁另行挡掉。'),
    },
    {
        'id': 'components-platforms',
        'dir': 'components',
        'include': ('platforms.md',),
        'skipDirs': ('example', '__pycache__'),
        'why': ('组件「平台可用性 / 前置条件 / 已知限制 / 真机验收」——AI 选型与验收必须用。'
                '它原本只在 components/ 下，knowledge/ 之外检索不到 = 黑洞；'
                '只收 platforms.md 这一个文件名（组件 README 等仍留给维护者，不进 AI 语料）。'),
    },
]


def _skip(spec, root_abs, dir_abs):
    """目录是否命中该根的 skipDirs 黑名单。"""
    rel = os.path.relpath(dir_abs, root_abs).replace('\\', '/')
    if rel in ('.', ''):
        return False
    parts = rel.split('/')
    return any(p in spec['skipDirs'] for p in parts)


def iter_repo_docs(base):
    """产出进索引的文档：[(仓库相对路径（'/' 分隔）, 绝对路径, 根规格)]（按路径排序）。"""
    out = []
    for spec in ROOTS:
        root_abs = os.path.join(base, spec['dir'])
        if not os.path.isdir(root_abs):
            continue
        for r, dirs, fnames in os.walk(root_abs):
            dirs[:] = [d for d in dirs if not _skip(spec, root_abs, os.path.join(r, d))]
            if _skip(spec, root_abs, r):
                continue
            for fn in fnames:
                if not any(fnmatch.fnmatch(fn, pat) for pat in spec['include']):
                    continue
                abs_path = os.path.join(r, fn)
                base_rel = os.path.relpath(abs_path, base).replace('\\', '/')
                out.append((base_rel, abs_path, spec))
    seen, uniq = set(), []
    for base_rel, abs_path, spec in sorted(out):
        if base_rel in seen:
            continue
        seen.add(base_rel)
        uniq.append((base_rel, abs_path, spec))
    return uniq


def repo_rel_docs(base):
    """进索引的仓库相对路径集合（覆盖度门禁算期望集用）。"""
    return {rel for rel, _abs, _spec in iter_repo_docs(base)}


def root_of_rel(base, base_rel):
    """给一个仓库相对路径，回它属于哪个根（不在任何根里 → None）。"""
    for spec in ROOTS:
        if base_rel == spec['dir'] or base_rel.startswith(spec['dir'] + '/'):
            for _rel, _abs, s in iter_repo_docs(base):
                if _rel == base_rel:
                    return s
    return None


if __name__ == '__main__':
    import sys
    b = os.path.dirname(os.path.abspath(__file__))
    docs = iter_repo_docs(b)
    per = {}
    for rel, _a, spec in docs:
        per.setdefault(spec['id'], []).append(rel)
    print('进检索索引的文档：%d 篇' % len(docs))
    for spec in ROOTS:
        items = per.get(spec['id'], [])
        print('  %-20s %4d 篇  （%s）' % (spec['id'], len(items), spec['dir']))
        for x in items[:3]:
            print('      %s' % x)
    sys.exit(0)
