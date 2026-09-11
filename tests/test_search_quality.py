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
        r = U.jcall('flythings_search', {'query': '抓屏 双缓冲 pan 抓到旧画面', 'k': 3})
        self.assertTrue(r['ok'], r)
        self.assertIn(r.get('retrieval'), ('bm25', 'vector+bm25(RRF)'))
        self.assertIn('degraded', r)
        for h in r['hits']:
            self.assertIn('（', h['source'])
            self.assertTrue(h['path'])
        self.assertIn(r.get('quality'), ('ok', 'low_confidence', 'no_hit'))

    def test_unrelated_query_not_silently_passed(self):
        """未收录/不沾边的 query 必须带「检索边界」提醒（不能只回一堆沾边片段）。"""
        r = U.jcall('flythings_search', {'query': 'zzzqqq 完全不存在的主题 xxyy', 'k': 3})
        self.assertTrue(r['ok'])
        self.assertIn(r.get('quality'), ('no_hit', 'low_confidence'))
        self.assertIn('developer.flythings.cn', r.get('notice', ''))

    def test_pure_nonsense_is_no_hit(self):
        r = U.jcall('flythings_search', {'query': 'zzzqqq xxyy wwvv', 'k': 3})
        self.assertTrue(r['ok'])
        self.assertEqual(r.get('quality'), 'no_hit')
        self.assertIn('developer.flythings.cn', r.get('notice', ''))

    def test_k_is_clamped(self):
        r = U.jcall('flythings_search', {'query': '抓屏', 'k': 99})
        self.assertTrue(r['ok'])
        self.assertLessEqual(len(r['hits']), 8)


if __name__ == '__main__':
    unittest.main(verbosity=2)
