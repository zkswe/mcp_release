# -*- coding: utf-8 -*-
"""检索契约：BM25 中文切词（字级 bigram）+ 返回值质量标记。

为什么要有（检讨报告 §3.7）：BM25 兜底原是「子串计数」级——中文无分词，
整段连续中文被当成一个 token，只有正文原样出现才命中，模型不可用时召回明显掉。
这里用一批真实问法钉住 top-3 命中，并把「低置信/未收录」标记钉住。
"""
import json
import unittest

import _util as U


def _load_check_retrieval():
    """按路径加载检索回归脚本（它不是包成员），只取常量与判据函数。

    脚本 import 时会 `sys.stdout.reconfigure(encoding='utf-8')`（CLI 需要，见该文件 :44）——
    在测试进程里照做会改掉整个进程的 stdout 编码。这里用一次性 sink 顶掉，取完即还原：
    不产生副作用，也不改被测脚本。
    """
    import importlib.util
    import os
    import sys

    class _Sink(object):
        def write(self, s):
            return len(s)

        def flush(self):
            pass

        def reconfigure(self, **kw):
            pass

    path = os.path.join(U.BASE, 'scripts', 'check_retrieval.py')
    spec = importlib.util.spec_from_file_location('cr_for_test', path)
    mod = importlib.util.module_from_spec(spec)
    old = sys.stdout
    try:
        sys.stdout = _Sink()
        spec.loader.exec_module(mod)
    finally:
        sys.stdout = old
    return mod


CR = _load_check_retrieval()


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


class TestGlobalTop1Gate(unittest.TestCase):
    """`scripts/check_retrieval.py` 的**全局 top-1 比例判据**（TODO §B2，2026-10-05 加）。

    为什么需要它：每组的 `min_top1` 是按实测 −1 登记的，比对时又放宽 `DRIFT_SLACK_TOP1`
    一条 —— 「单组不回退」有保证，**整体召回却能悄悄下滑**（很多组各掉一两条，全绿）。
    本用例只钉**结构性质**，不钉任何数字（数字的真源是实跑结果，写进用例就是第二份真源）：
      ① 判据存在、阈值已登记成模块常量且取值合理；
      ② 默认走的就是那个常量（恰好在阈值上算通过，低一条就不通过）；
      ③ 分子/分母**由传入的 summary 现算** —— 同一份 summary 拆分/合并比例不变、
         命中数相同而分母翻倍时结论必须翻面（分母若被写死就翻不动）；
      ④ 结论文本里必须打出分子/分母/百分比/组数（否则"整体滑坡"没法定位）；
      ⑤ `main()` 真的调用它、失败真的进 `bad`（防"阈值在、判据空转"）。
    """

    def test_threshold_registered_and_sane(self):
        r = CR.GLOBAL_TOP1_MIN_RATIO
        self.assertIsInstance(r, float, '阈值要是浮点比例（不是百分数或字符串）')
        self.assertGreater(r, 0.0, '阈值必须为正，否则判据恒绿')
        self.assertLess(r, 1.0, '阈值必须严格小于 1，否则判据恒红')

    def test_default_threshold_is_the_registered_constant(self):
        """默认值 = 模块常量：恰好在阈值上通过（`>=`），低一条就必须失败。"""
        import math
        r = CR.GLOBAL_TOP1_MIN_RATIO
        n = 10000
        on = int(math.ceil(r * n))            # on/n >= r
        ok, line = CR.global_top1_verdict([{'n': n, 'top1': on}])
        self.assertTrue(ok, '恰好在登记阈值上必须算通过：%s' % line)
        off = int(math.floor(r * n)) - 1      # off/n < r
        ok2, line2 = CR.global_top1_verdict([{'n': n, 'top1': off}])
        self.assertFalse(ok2, '低于登记阈值必须判失败：%s' % line2)

    def test_numerator_and_denominator_are_computed_from_summary(self):
        # 拆分/合并不改变结论：分母是现算的（不是写死的组数）
        a = [{'n': 6, 'top1': 3}, {'n': 2, 'top1': 1}]      # 4/8 = 50%
        b = [{'n': 8, 'top1': 4}]                           # 4/8 = 50%
        oa, la = CR.global_top1_verdict(a, 0.72)
        ob, lb = CR.global_top1_verdict(b, 0.72)
        self.assertEqual((oa, ob), (False, False))
        self.assertIn('4/8', la)
        self.assertIn('4/8', lb)
        # 命中数相同、分母翻倍 → 结论必须翻面（分母被写死就翻不动）
        o1, _ = CR.global_top1_verdict([{'n': 4, 'top1': 3}], 0.72)   # 75%
        o2, _ = CR.global_top1_verdict([{'n': 8, 'top1': 3}], 0.72)   # 37.5%
        self.assertTrue(o1)
        self.assertFalse(o2)

    def test_line_prints_numbers_for_localization(self):
        ok, line = CR.global_top1_verdict([{'n': 4, 'top1': 3}], 0.72)
        self.assertTrue(ok)
        for frag in ('3/4', '75.0%', '72%', '1 组'):
            self.assertIn(frag, line, '判据行里缺 %r → 出问题无法定位：%s' % (frag, line))

    def test_denominator_matches_real_groups(self):
        """分母的来处：summary 的 `n` 必须是该组**真实问法数**（≥5），组数取自真实分组。"""
        gs = CR._all_groups()
        self.assertTrue(gs, '一组都没读到 → 后面的判据全是空转')
        summary = [{'n': len(g['queries']), 'top1': 0} for g in gs]
        num, den = CR.global_top1_counts(summary)
        self.assertEqual(num, 0)
        self.assertEqual(den, sum(len(g['queries']) for g in gs))
        self.assertGreaterEqual(den, len(gs) * CR.MIN_QUERIES_PER_GROUP,
                                '分母应 ≥ 组数 × 每组最小问法数（即分母是问法数，不是组数）')
        ok, line = CR.global_top1_verdict(summary)
        self.assertFalse(ok, '一条都没命中却判通过：%s' % line)
        self.assertIn('%d 组' % len(gs), line)

    def test_main_actually_gates_on_it(self):
        """结构性质：`main()` 调用了判据，且失败进 `bad`（否则退出码仍 0 = 没判）。"""
        import ast
        import io
        import os
        with io.open(os.path.join(U.BASE, 'scripts', 'check_retrieval.py'),
                     encoding='utf-8') as f:
            src = f.read()
        tree = ast.parse(src)
        mains = [n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == 'main']
        self.assertEqual(len(mains), 1, '没找到唯一的 main()')
        calls = [n for n in ast.walk(mains[0]) if isinstance(n, ast.Call)
                 and getattr(n.func, 'id', '') == 'global_top1_verdict']
        self.assertTrue(calls, 'main() 没调用 global_top1_verdict → 判据空转（阈值在、没人用）')
        guards = [n for n in ast.walk(mains[0]) if isinstance(n, ast.If)
                  and isinstance(n.test, ast.Name) and n.test.id == 'ok_glob']
        self.assertEqual(len(guards), 1, '没找到 `if ok_glob:` 这一处判据分支')
        tail = '\n'.join(ast.get_source_segment(src, s) or '' for s in guards[0].orelse)
        self.assertIn('bad.append', tail,
                      '全局判据判失败时没进 bad → rc 仍为 0（等于没判）')


if __name__ == '__main__':
    unittest.main(verbosity=2)
