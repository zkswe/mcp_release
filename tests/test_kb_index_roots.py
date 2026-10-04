# -*- coding: utf-8 -*-
"""「哪些文档进检索索引」唯一真源的契约（kb_index_roots.py）。

为什么要有它：这条口径原本被抄在两处——`rebuild_index_local.py` 走一遍 `knowledge/`，
`scripts/check_consistency.py` 的 `_expected_md_sets()` 又"同口径"再走一遍。加一类文档要改两处、
漏一处就漂移。同时它承载一个**反黑洞**的显式决定：`components/*/platforms.md` 必须进检索
（那 16 篇讲组件在各平台的可用性/前置/限制/验收，AI 选型与验收要用；不进索引就等于检索不到）。

钉住八件事：
  ① knowledge/**/*.md 进索引，但 inbox/_reports/_logs 不进
  ② components/**/platforms.md 进索引（黑洞修复不许被回退）
  ③ components 的其它 md（README 等）**不进**（那是维护者视角，不属于 AI 语料）
  ④ packages/**/README.md 与 platforms.md 进索引（**第 3 例黑洞修复，同②同构，也不许被回退**）
  ⑤ packages 的 example/evidence/lib 与其它 md **不进**（示例自带件/取证/构建凭据）
  ⑥ 索引范围确定、去重、有 authority 声明（用 AST 取值，不依赖 import 副作用）
  ⑦ rag_index.json 的实际 chunk 路径 ⊇ 真源声明的范围（切片覆盖，不是只看篇名）
  ⑧ 两个消费方（rebuild_index_local / check_consistency）确实都从真源取，没有各写一遍
"""
import ast
import io
import json
import os
import sys
import unittest

import _util as U

BASE = U.BASE
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import kb_index_roots as bir                       # noqa: E402


def _packages_expected():
    """包级用法页的期望集合（**唯一口径**，下面两个用例共用，避免各写一遍）。

    只收两层：`packages/README.md` 与 `packages/<包>/{README.md,platforms.md}`。
    `example/`（最小示例工程自带件）、`evidence/`（截图与日志）、`lib/`（构建凭据）
    是维护者/工程视角，不进 AI 语料。
    """
    import glob
    out = set()
    if os.path.isfile(os.path.join(BASE, 'packages', 'README.md')):
        out.add('packages/README.md')
    for name in ('README.md', 'platforms.md'):
        for p in glob.glob(os.path.join(BASE, 'packages', '*', name)):
            out.add(os.path.relpath(p, BASE).replace('\\', '/'))
    return out


class TestIndexRoots(unittest.TestCase):

    def test_authority_declared(self):
        self.assertTrue(str(bir.AUTHORITY).strip(), '必须声明 authority')

    def test_knowledge_included_excluded(self):
        docs = bir.repo_rel_docs(BASE)
        for sub in ('inbox', '_reports', '_logs'):
            bad = [d for d in docs if d.startswith('knowledge/%s/' % sub)]
            self.assertEqual(bad, [], '%s 不该进索引' % sub)
        self.assertIn('knowledge/README.md', docs)
        self.assertTrue(any(d.startswith('knowledge/devflow/') for d in docs))

    def test_components_platforms_included(self):
        """黑洞修复：组件平台页必须进检索。"""
        docs = bir.repo_rel_docs(BASE)
        import glob
        want = {os.path.relpath(p, BASE).replace('\\', '/')
                for p in glob.glob(os.path.join(BASE, 'components', '**', 'platforms.md'),
                                   recursive=True)}
        self.assertTrue(want, '仓库里应有 components/**/platforms.md')
        self.assertTrue(want <= docs, '未进索引的组件平台页：%s' % sorted(want - docs))

    def test_other_component_docs_excluded(self):
        """只收 platforms.md，不收组件 README 等维护者视角文档。"""
        docs = bir.repo_rel_docs(BASE)
        extra = [d for d in docs
                 if d.startswith('components/') and not d.endswith('/platforms.md')]
        self.assertEqual(extra, [], 'components 下只应收 platforms.md：%s' % extra[:5])

    def test_packages_usage_docs_included(self):
        """黑洞修复第 3 例（与 components/platforms.md 同构）：包用法页必须进检索。

        为什么：`packages/<包>/README.md`（装法 / API 速查 / 最小示例 / 真机实测 / 坑）与
        `platforms.md`（逐平台结论与证据）正是 plan.md 根因④「硬件外设 API」与
        根因⑥「组件包」的答案载体。**修前 `rag_index.json` 里 `packages/` 的 chunk 数 = 0**
        （40 篇 md 一篇都搜不到），问「zkhardware 怎么用 / 继电器怎么写」命中的全是别的文档。
        """
        docs = bir.repo_rel_docs(BASE)
        want = _packages_expected()
        self.assertTrue(want, '仓库里应有 packages 的包级 README.md / platforms.md')
        self.assertTrue(want <= docs, '未进索引的包用法页：%s' % sorted(want - docs))

    def test_packages_non_usage_docs_excluded(self):
        """只收包级 README.md / platforms.md：example/ evidence/ lib/ 不进（维护者/工程视角）。"""
        docs = bir.repo_rel_docs(BASE)
        allowed = _packages_expected()
        extra = sorted(d for d in docs if d.startswith('packages/') and d not in allowed)
        self.assertEqual(extra, [],
                         'packages 下只应收包级 README.md / platforms.md：%s' % extra[:5])

    def test_deterministic_and_unique(self):
        a = [r for r, _p, _s in bir.iter_repo_docs(BASE)]
        b = [r for r, _p, _s in bir.iter_repo_docs(BASE)]
        self.assertEqual(a, b, '产出应确定')
        self.assertEqual(len(a), len(set(a)), '不应有重复路径')

    def test_rag_index_covers_declared_scope(self):
        idx = json.load(io.open(os.path.join(BASE, 'rag_index.json'), encoding='utf-8'))
        have = {c.get('path', '').replace('\\', '/') for c in idx.get('chunks', [])}
        missing = sorted(bir.repo_rel_docs(BASE) - have)
        self.assertEqual(missing, [],
                         '真源声明的文档没进索引（跑 python rebuild_index_local.py）：%s'
                         % missing[:5])

    def test_no_second_copy_of_walk_logic(self):
        """两个消费方都不许自己写遍历口径（只允许出现 kb_index_roots 引用）。"""
        for rel in ('rebuild_index_local.py', os.path.join('scripts', 'check_consistency.py')):
            src = io.open(os.path.join(BASE, rel), encoding='utf-8').read()
            self.assertIn('kb_index_roots', src,
                          '%s 应从 kb_index_roots 取索引范围，而不是自己 walk' % rel)


if __name__ == '__main__':
    unittest.main()
