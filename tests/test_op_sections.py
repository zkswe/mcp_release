# -*- coding: utf-8 -*-
"""按需面**分段取用**（`describe(section=…)`）的结构性质（B1，2026-10-05）。

为什么单独一组用例：按需面单条上限 900 字符，而最长的一条已到 **892（余 8）** ——
「往契约里加东西」这条路事实上到顶了（加一次 `excludes` 吃掉 47 字符、加一条规则吃掉 411）。
分层把计费单位从"整条 op"换成"一次取用"：实测单段最大 645、默认形态最大 = 全文 805。

本文件只钉**结构性质**，不写死任何数字（段长、上限都从 `op_spec_loader` 派生）——
否则就是第二份真源。
"""
import asyncio
import io
import json
import os
import sys
import unittest

import _util as U  # noqa: F401  （与其他用例一致：统一 sys.path 与离线守卫）

sys.path.insert(0, U.BASE)
import op_spec_loader as osl  # noqa: E402

BASE = U.BASE


class TestSectionsPartition(unittest.TestCase):
    """段划分必须是 `contractOrder` 的**精确划分**：不重排、不新增、不遗漏、不重叠。"""

    def test_partition_is_exact(self):
        reg = osl.load()
        secs = osl.sections()
        self.assertTrue(secs, '没有段划分（tiers.onDemand.sections）')
        order = list(reg.get('contractOrder') or [])
        flat = [f for s in secs for f in s['fields']]
        self.assertEqual(sorted(flat), sorted(order), '段并集必须 == contractOrder')
        self.assertEqual(len(flat), len(set(flat)), '同一字段不许被两个段覆盖')
        ids = [s['id'] for s in secs]
        self.assertEqual(len(ids), len(set(ids)), '段 id 不许重复')

    def test_field_order_matches_contract_order(self):
        """分段只能**划分**、不能重排 —— 否则拼接回不去完整契约。"""
        order = list(osl.load().get('contractOrder') or [])
        for s in osl.sections():
            flds = [str(f) for f in s['fields']]
            self.assertEqual([f for f in order if f in flds], [f for f in flds if f in order],
                             '段 %s 的字段顺序与 contractOrder 不一致' % s['id'])

    def test_skeleton_covers_resident_face(self):
        """三级包含链：常驻面 ⊆ `skeleton` ⊆ 全文（分层不许把常驻面拆散）。"""
        reg = osl.load()
        sk = next(s for s in osl.sections() if s['id'] == 'skeleton')
        self.assertTrue(set(reg.get('renderOrder') or []) <= set(sk['fields']),
                        'skeleton 必须覆盖 renderOrder 的全部字段')

    def test_registry_validate_accepts_sections(self):
        """注册表自检必须认这套划分（validate 里加了同源判据）。"""
        self.assertEqual([e for e in osl.validate() if '段' in e or 'skeleton' in e], [],
                         'validate 对段划分有意见：%s' % osl.validate()[:3])


class TestSectionsRender(unittest.TestCase):
    """渲染恒等与预算：分段取用不许改内容、不许超上限。"""

    def test_joining_sections_equals_full_contract(self):
        """各段按段序拼接 == `render_contract`（**逐字节**）—— "信息只增不减"的可机判形态。

        这条抓的是**分隔符归属**：第一次实现时把所有片段都用空行拼，与旧输出差了字符，
        靠"与完整契约逐字节比"当场发现（`_join_parts` 的注释里记了这次）。
        """
        secs = osl.sections()
        for op in osl.registered():
            parts = [x for s in secs for x in osl._render_parts(op, s['fields'])]
            self.assertEqual(osl._join_parts(parts), osl.render_contract(op),
                             '%s：各段拼接与完整契约不一致' % op)

    def test_all_section_equals_full_contract(self):
        """`all` 是逃生门：必须逐字节等于完整契约，不能悄悄变成另一套。"""
        for op in osl.registered():
            self.assertEqual(osl.render_section(op, 'all'), osl.render_contract(op))

    def test_every_section_within_budget(self):
        cap = int((osl.load().get('budget') or {}).get('contractPerOpMax', 900))
        worst = (0, '')
        for op in osl.registered():
            for s in osl.sections():
                n = len(osl.render_section(op, s['id']))
                if n > worst[0]:
                    worst = (n, '%s:%s' % (op, s['id']))
                self.assertLessEqual(n, cap, '%s 的 %s 段 %d 字符超上限 %d'
                                     % (op, s['id'], n, cap))
        self.assertLess(worst[0], cap, '（顺带记录：最长的段是 %s = %d）' % (worst[1], worst[0]))

    def test_skeleton_extends_resident_face(self):
        for op in osl.registered():
            self.assertTrue(osl.render_section(op, 'skeleton').startswith(osl.render(op)),
                            '%s：常驻面必须是 skeleton 段的前缀' % op)

    def test_unknown_section_raises_with_valid_list(self):
        """未登记的段**不静默回落**：报错里必须带合法段清单。"""
        try:
            osl.render_section(osl.registered()[0], 'nope')
        except osl.OpSpecError as e:
            for sid in osl.section_ids():
                self.assertIn(sid, str(e), '报错要给合法段清单')
        else:
            self.fail('未知段没有报错（静默回落了）')


class TestDefaultShape(unittest.TestCase):
    """默认形态：今天必须**逐字节等于全文**（对旧消费方无感）；超限时自动软着陆。"""

    def test_default_equals_full_when_within_budget(self):
        cap = int((osl.load().get('budget') or {}).get('contractPerOpMax', 900))
        for op in osl.registered():
            full, dflt = osl.render_contract(op), osl.render_default(op)
            self.assertLessEqual(len(dflt), cap, '%s：默认形态超上限' % op)
            if len(full) <= cap:
                self.assertEqual(dflt, full, '%s：未超限时默认形态必须等于全文' % op)

    def test_degrades_when_over_budget(self):
        """超限 → skeleton + 段目录（各段长度由**实测派生**，不手写）。

        用**构造 spec** 验证（临时往缓存里塞一个超长 op）：不落盘、不改注册表。
        """
        cap = int((osl.load().get('budget') or {}).get('contractPerOpMax', 900))
        reg = osl.load()
        probe = '__b1_probe__'
        saved = osl._CACHE
        try:
            reg['ops'][probe] = {'summary': '探针 op（用例内构造，不落盘）', 'risk': 'read',
                                 'category': osl.CATEGORY_VALUES[0],
                                 'stage': osl.STAGE_VALUES[0],
                                 'rules': ['⚠️ ' + '长' * (cap + 50)]}
            osl._CACHE = reg
            d = osl.render_default(probe)
            self.assertGreater(len(osl.render_contract(probe)), cap, '（前提：探针确实超限）')
            self.assertLessEqual(len(d), cap, '退化形态本身也必须 ≤ 上限')
            self.assertTrue(d.startswith(osl.render_section(probe, 'skeleton')),
                            '退化形态必须以 skeleton 开头')
            for s in osl.sections():
                self.assertIn(s['id'], d, '段目录要列出每一段，否则 AI 不知道能取什么')
            self.assertIn('all', d, '段目录必须给出 all')
        finally:
            reg['ops'].pop(probe, None)
            osl._CACHE = saved


class TestDescribeSectionParam(unittest.TestCase):
    """`describe(section=…)` 的四种取值：段名 / `all` / 不传 / 未知段。"""

    def _call(self, op, args):
        import mcp_server as M
        return json.loads(asyncio.run(M.flythings_kb(op='describe:%s' % op,
                                                     args=json.dumps(args))))

    def test_default_form(self):
        op = osl.registered()[0]
        r = self._call(op, {})
        self.assertTrue(r.get('ok'), r)
        self.assertEqual(r.get('section'), '', '不传 section 时回显应为空串')
        self.assertEqual(r.get('contract'), osl.render_default(op), '默认形态口径')
        self.assertEqual(r.get('chars'), len(r.get('contract') or ''),
                         'chars 必须等于实际返回的字符数（让 AI 看得见预算）')

    def test_named_section_and_all(self):
        op = osl.registered()[0]
        one = self._call(op, {'section': 'rules'})
        self.assertTrue(one.get('ok'), one)
        self.assertEqual(one.get('contract'), osl.render_section(op, 'rules'))
        self.assertEqual(self._call(op, {'section': 'all'}).get('contract'),
                         osl.render_contract(op), 'section=all == 全文')

    def test_unknown_section_reports_choices(self):
        """未知段必须 `UNKNOWN_SECTION` + 合法段清单（照 `UNKNOWN_OP` 的既有形态）。"""
        op = osl.registered()[0]
        bad = self._call(op, {'section': 'nope'})
        self.assertFalse(bad.get('ok'), '未知段必须报错而不是回落成整条契约')
        self.assertEqual(bad['error']['code'], 'UNKNOWN_SECTION')
        for sid in osl.section_ids():
            self.assertIn(sid, bad['error']['hint'], '报错要给合法段清单')


class TestSectionResources(unittest.TestCase):
    """资源侧：`flythings://ops/<名>` 走默认形态，且**新增**了 `<名>/<段>` 模板。"""

    def test_resource_templates_exist(self):
        src = io.open(os.path.join(BASE, 'mcp_extras.py'), encoding='utf-8').read()
        self.assertIn('flythings://ops/{name}', src)
        self.assertIn('flythings://ops/{name}/{section}', src, '缺"按段取"的资源模板')
        self.assertIn('render_default', src, '单个 op 的资源必须走默认形态（否则超限时仍会灌爆）')
        self.assertIn('render_section', src, '按段取的资源必须走 render_section')


if __name__ == '__main__':
    unittest.main()
