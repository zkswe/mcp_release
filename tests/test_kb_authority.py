# -*- coding: utf-8 -*-
"""权威口径注册表契约（knowledge/authority_map.json + kb_authority.py）。

为什么要有它：一条铁律常被十几到三十篇文档各自复述（措辞不同、**没有逐字重复可删**），
真正缺的是「哪一篇才算权威」。本表把概念指定到权威文档，检索命中时把 authority 附在返回体里。
用例钉住：canonical 必须在**检索范围内**（存在但不在索引里 = AI 拿到也搜不到）、别名不撞车、
匹配能容忍插词、无关查询不误报、以及端到端真的注入了返回体。

钉住八件事：
  ① 注册表可加载且声明 authority
  ② 自检干净（canonical 在检索范围内 / aliases 非空不撞车 / ops 存在）
  ③ canonical 全部落在 kb_index_roots 的检索范围内（显式再钉一次）
  ④ 子串命中
  ⑤ 插词容错（『有没有现成的包』对上『有没有现成的 MQTT 包』）
  ⑥ 无关查询不误报（不返回 authority）
  ⑦ 命中数有上限（≤3）
  ⑧ 端到端：走分发器 knowledge_search，返回体带 authority
"""
import json
import os
import sys
import unittest

import _util as U

BASE = U.BASE
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import kb_authority as au                          # noqa: E402
import kb_index_roots as bir                       # noqa: E402


class TestAuthorityMap(unittest.TestCase):

    def test_loads_and_declares_authority(self):
        reg = au.load()
        self.assertTrue(str(reg.get('authority') or '').strip(), '必须声明 authority')
        self.assertTrue(au.concepts(), 'concepts 不能为空')

    def test_selfcheck_clean(self):
        self.assertEqual(au.validate(), [], 'authority_map.json 自检不通过')

    def test_canonical_in_index_scope(self):
        """硬约束：权威文档必须可被检索到（在索引范围内）。"""
        scope = bir.repo_rel_docs(BASE)
        for name in au.concepts():
            c = au.spec(name)
            self.assertIn(c['canonical'], scope,
                          '%s 的 canonical 不在检索范围：%s' % (name, c['canonical']))

    def test_substring_hit(self):
        hits = au.for_query('图片尺寸和控件盒对不上')
        self.assertIn('image-box-size', [h['concept'] for h in hits])

    def test_insertion_tolerant(self):
        """中间插词也要命中（这是真实问法的常态）。"""
        hits = au.for_query('有没有现成的 MQTT 包')
        self.assertIn('builtin-packages', [h['concept'] for h in hits])

    def test_unrelated_query_no_hit(self):
        self.assertEqual(au.for_query('随便聊聊天气怎么样'), [])
        self.assertEqual(au.for_query(''), [])

    def test_max_hits_cap(self):
        hits = au.for_query('控件盒 图片尺寸 onUI_show glibc 升级包 内置包 对比度 findControlByID')
        self.assertLessEqual(len(hits), 3)

    def test_end_to_end_injected_into_result(self):
        """走真实分发路径：返回体必须带 authority 且指向权威文档。"""
        r = json.loads(U.call('flythings_knowledge_search',
                              {'query': '图片尺寸和控件盒对不上', 'k': 2}))
        self.assertTrue(r.get('ok'))
        auth = r.get('authority') or []
        self.assertTrue(auth, '命中已登记概念时应带 authority')
        self.assertEqual(auth[0]['canonical'], 'knowledge/devflow/ui-asset-rules.md')

    def test_unknown_concept_raises(self):
        with self.assertRaises(au.AuthorityError):
            au.spec('not_a_concept')


if __name__ == '__main__':
    unittest.main()
