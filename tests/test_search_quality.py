# -*- coding: utf-8 -*-
"""检索契约：BM25 中文切词（字级 bigram）+ 返回值质量标记。

为什么要有（检讨报告 §3.7）：BM25 兜底原是「子串计数」级——中文无分词，
整段连续中文被当成一个 token，只有正文原样出现才命中，模型不可用时召回明显掉。
这里用一批真实问法钉住 top-3 命中，并把「低置信/未收录」标记钉住。
"""
import json
import unittest

import _util as U


class TestBM25Tokenizer(unittest.TestCase):
    def test_cjk_is_bigram_not_whole_run(self):
        import rag_search as rs
        toks = rs.query_tokens('Z20 屏幕截图怎么抓')
        self.assertIn('z20', toks)
        self.assertIn('屏幕', toks)
        self.assertIn('截图', toks)
        self.assertNotIn('屏幕截图怎么抓', toks, '整段中文不应成为一个 token')

    def test_ascii_words_kept(self):
        import rag_search as rs
        toks = rs.query_tokens('setTouchPass 怎么用')
        self.assertIn('settouchpass', toks)

    def test_kb_and_rag_share_tokenizer(self):
        import kb_tools
        import rag_search as rs
        self.assertEqual(kb_tools._query_tokens('抓屏 双缓冲 pan'),
                         rs.query_tokens('抓屏 双缓冲 pan'),
                         '覆盖率判定与 BM25 必须共用同一套切词（否则质量标记会失真）')


class TestBM25Recall(unittest.TestCase):
    CASES = [
        ('HTML_SUBSET 控件映射 data-icon 图标', 'html-subset-quickref.md'),
        ('Z20 屏幕截图怎么抓', 'device-screenshot.md'),
        ('抓屏 双缓冲 pan 抓到旧画面', 'device-screenshot.md'),
        ('图片生成锯齿 只走三条路', 'ui-asset-rules.md'),
        ('可视化编辑器 拖完怎么回写 json', 'ui-editor-usage.md'),
        ('按钮长按 循环重复 怎么配', 'button-fields.md'),
        ('listview setSelection 没刷新', 'listview-fields.md'),
        ('json 字段必须全写 缺省漂移', 'json-field-mandatory.md'),
    ]

    def test_expected_doc_in_top3(self):
        import rag_search as rs
        miss = []
        for q, want in self.CASES:
            paths = [(c.get('path') or '') for _, c in rs._bm25_search(q, 3)]
            if not any(want in p for p in paths):
                miss.append('%s -> %s' % (q, paths[:2]))
        self.assertEqual(miss, [], 'BM25 top-3 未命中（%d/%d）：%s'
                         % (len(miss), len(self.CASES), '; '.join(miss)))


class TestSearchResultQuality(unittest.TestCase):
    def test_hits_carry_source_and_retrieval(self):
        r = U.jcall('flythings_knowledge_search', {'query': '抓屏 双缓冲 pan 抓到旧画面', 'k': 3})
        self.assertTrue(r['ok'], r)
        self.assertIn(r.get('retrieval'), ('bm25', 'vector+bm25(RRF)'))
        self.assertIn('degraded', r)
        for h in r['hits']:
            self.assertIn('（', h['source'])
            self.assertTrue(h['path'])
        self.assertIn(r.get('quality'), ('ok', 'low_confidence', 'no_hit'))

    def test_unrelated_query_not_silently_passed(self):
        """未收录/不沾边的 query 必须带「检索边界」提醒（不能只回一堆沾边片段）。"""
        r = U.jcall('flythings_knowledge_search', {'query': 'zzzqqq 完全不存在的主题 xxyy', 'k': 3})
        self.assertTrue(r['ok'])
        self.assertIn(r.get('quality'), ('no_hit', 'low_confidence'))
        self.assertIn('developer.flythings.cn', r.get('notice', ''))

    def test_pure_nonsense_is_no_hit(self):
        r = U.jcall('flythings_knowledge_search', {'query': 'zzzqqq xxyy wwvv', 'k': 3})
        self.assertTrue(r['ok'])
        self.assertEqual(r.get('quality'), 'no_hit')
        self.assertIn('developer.flythings.cn', r.get('notice', ''))

    def test_k_is_clamped(self):
        r = U.jcall('flythings_knowledge_search', {'query': '抓屏', 'k': 99})
        self.assertTrue(r['ok'])
        self.assertLessEqual(len(r['hits']), 8)


class TestSourceLabel(unittest.TestCase):
    """`hits[].source` 必须按**索引根真源**派生（2026-10-03 修）。

    修前的口径是 `path.startswith('knowledge/')` 二选一 → **仓库内**的
    `components/**/platforms.md`（16 篇）与 `packages/**`（25 篇）全被标成
    「wiki（官方镜像）」：AI 会以为那是外部镜像、不是本仓实践知识 —— 可信度判错、出处指错，
    而这是它读检索结果时最先看到的字段之一。
    """

    def test_knowledge_and_packages_and_components_labels(self):
        import kb_tools
        self.assertEqual(kb_tools._kb_source_label('knowledge/devflow/ftu-json-pipeline.md'),
                         'knowledge（实践）')
        self.assertEqual(kb_tools._kb_source_label('packages/zkhardware/README.md'),
                         'packages（包用法）')
        self.assertEqual(kb_tools._kb_source_label('components/ble/platforms.md'),
                         'components（组件平台页）')
        self.assertEqual(kb_tools._kb_source_label('kb_local/local/x.md'),
                         'kb_local（用户本地层）')

    def test_wiki_path_still_labeled_as_mirror(self):
        """真正的外部镜像（wiki 相对路径，不在任何仓库根里）仍应是「wiki（官方镜像）」。"""
        import kb_tools
        self.assertEqual(kb_tools._kb_source_label('devflow/some-official-page.md'),
                         'wiki（官方镜像）')

    def test_repo_roots_are_not_labeled_wiki(self):
        """回归钉子：仓库真源声明的任何一篇，都不许再被判成 wiki。"""
        import kb_index_roots as bir
        import kb_tools
        bad = [rel for rel in bir.repo_rel_docs(U.BASE)
               if kb_tools._kb_source_label(rel) == 'wiki（官方镜像）']
        self.assertEqual(bad, [], '仓库内文档被误标成 wiki：%s' % bad[:5])


if __name__ == '__main__':
    unittest.main(verbosity=2)
