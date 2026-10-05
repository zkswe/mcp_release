# -*- coding: utf-8 -*-
"""op_spec 瘦身（2026-10-05，用户指示）的三条判据：A triggers 移出常驻 / B 片段表 / C seeAlso 去重。

为什么要用例：这三条都是"看起来只是省字"的改动，但每一条都能**悄悄改掉语义**：
  · A 若把 triggers 从 op_spec 里删了（而不是只移出 renderOrder），路由就废了；
  · B 若片段没展开（或展开错），工具描述会显示 `@platform-positioning` 这种给 AI 看的垃圾；
  · C 若把去重做进**数据**，`op_seealso.json` / 返回体的 seeAlso 会少一条路径（丢指针）。
所以三条都要有判据，且**指向语义**而不是字数。
"""
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (BASE, os.path.join(BASE, 'tests')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import op_spec_loader as osl                                # noqa: E402


class TestResidentSlimming(unittest.TestCase):

    def test_triggers_not_in_resident_but_still_in_spec(self):
        """A：triggers 不再进常驻渲染，但**必须仍在 op_spec 里**（dispatcher/目录/manifest 靠它路由）。"""
        self.assertNotIn('triggers', osl.load().get('renderOrder') or [],
                         'triggers 又回常驻面了（每次会话都要为它付 token）')
        for op in osl.registered():
            self.assertTrue([t for t in (osl.spec(op).get('triggers') or []) if str(t).strip()],
                            '%s 的 triggers 空了 —— 路由数据不能因为瘦身被删' % op)
            self.assertNotIn('触发：', osl.render(op),
                             '%s 的常驻面里又出现触发词了' % op)

    def test_contract_still_starts_with_resident(self):
        """A 的副作用防线：契约必须以常驻面开头（信息只增不减）。"""
        for op in osl.registered():
            self.assertTrue(osl.render_contract(op).startswith(osl.render(op).strip()),
                            '%s：契约不再以常驻面开头' % op)

    def test_fragments_expand(self):
        """B：片段在载入时展开 —— 下游看到的必须是**展开后**文本，且没有未定义引用。"""
        frags = osl.load().get('fragments') or {}
        self.assertTrue(frags, '片段表没了？')
        self.assertEqual(osl._UNKNOWN_FRAGMENTS, [],
                         '有未定义片段引用：%s' % osl._UNKNOWN_FRAGMENTS)
        for op in osl.registered():
            blob = osl.render_contract(op)
            self.assertNotIn('@platform-positioning', blob,
                             '%s 的契约里还留着未展开的片段引用' % op)
        hit = [op for op in osl.registered()
               if 'platform-positioning' in ' '.join(osl.spec(op).get('hardRules') or [])]
        self.assertEqual(hit, [], 'hardRules 里应只留片段引用，展开后不该含片段名')
        expanded = [x for op in osl.registered()
                    for x in (osl.spec(op).get('hardRules') or []) if 'EasyUI' in x]
        self.assertTrue(expanded, '展开失败：没有任何 hardRule 含定位文本')

    def test_seealso_dedup_is_render_only(self):
        """C：去重只发生在**渲染**——数据里 seeAlso 仍保留 docRef（派生件/返回体要用）。

        ⚠️ 实测更正（2026-10-05）：seeAlso **不在 contractOrder 里**，所以这条去重今天
        只在该字段被取用时生效（返回体注入路径用同一份数据）。判据因此直接钉**字段渲染器**，
        并顺带钉住数据没被改（否则 op_seealso.json / 返回体会少一条路径 = 丢指针）。
        """
        dup = [op for op in osl.registered()
               if osl.spec(op).get('docRef') and osl.spec(op).get('docRef') in
               (osl.spec(op).get('seeAlso') or [])]
        self.assertTrue(dup, '数据里已无 docRef∩seeAlso —— 若是有意清过数据，请同步删掉本用例')
        for op in dup[:12]:
            dr = osl.spec(op)['docRef']
            rendered = osl._field_text(op, 'seeAlso')
            self.assertNotIn(dr, rendered,
                             '%s：渲染 seeAlso 时没去掉与 docRef 重复的那条' % op)
            self.assertIn(dr, osl.spec(op)['seeAlso'],
                          '%s：数据里的 seeAlso 被改动了（去重只许发生在渲染层）' % op)


if __name__ == '__main__':
    unittest.main()
