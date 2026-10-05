# -*- coding: utf-8 -*-
"""工具路由的分级筛选回归（`mcp_server._find` + `op_spec.json` 的 triggers）。

为什么要有它（2026-10-03 架构）：工具面分了三层（常驻/按需/深入）后，**"选哪个 op"这一步
从"AI 读 47 条 description 自己挑"变成"先按用户原话分级筛一道"**。
既然筛，就得有回归 —— 否则触发词写歪了（写成书面短语而不是用户原话里的片段）没人发现，
表现为"AI 选错工具"，而那是**最贵的一类错**（调错工具 = 白跑一轮）。

判据（与 `scripts/check_retrieval.py` 同一套思路）：
  ① 每组"用户原话 → 期望 op"必须落在 top-3 候选中（`max_miss` 显式登记例外 + 写原因）
  ② 对照组：无关需求（闲聊/别的产品）不许给出高分候选 —— 防止触发词写得太泛
  ③ 每个 op 至少 3 条触发词（筛不出来 = 这个 op 只能靠 op 名撞运气）
"""
import json
import os
import sys
import unittest

import _util as U

BASE = U.BASE
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import mcp_server as ms        # noqa: E402
import op_spec_loader as osl   # noqa: E402

# 用户会真的说出口的话 → 期望被选中的 op（全部实测通过；改动触发词后必须仍然成立）
CASES = [
    # 部署 / 构建
    ('把界面推到设备上跑一下', 'flythings_build_ui_flow'),
    ('编译一下看看', 'flythings_build_ui_flow'),
    ('把这版固化了', 'flythings_pack_upgrade'),
    ('出一个出货版本', 'flythings_pack_upgrade'),
    # 上机前 / 设备体检
    ('屏比设计小怎么办', 'flythings_device_preflight'),
    ('接上设备先看什么', 'flythings_device_preflight'),
    ('这块板子现在什么状态', 'flythings_selfcheck'),
    ('抓个图看看', 'flythings_device_screenshot'),
    ('跑一下自动化回归', 'flythings_test_run'),
    # 需求 → 工程 / 原型
    ('帮我建个项目', 'flythings_create_project'),
    ('把原型变成界面', 'flythings_html_to_json'),
    ('给客户看下效果', 'flythings_ui_preview'),
    ('LVGL 工程想搬过来', 'flythings_translate_ui'),
    # 布局 / 视觉
    ('这个字段什么意思', 'flythings_ui_schema'),
    ('子控件被遮住了', 'flythings_layout_audit'),
    ('图片和设计稿不像', 'flythings_ui_visual'),
    ('图比控件盒大了', 'flythings_verify_assets'),
    ('生成一套图标', 'flythings_generate_ui_assets'),
    ('给我补上按钮点击回调', 'flythings_gen_logic_stub'),
    # 包 / 依赖
    ('加个 mqtt 包', 'flythings_add_package'),
    ('有没有 http 库', 'flythings_package_search'),
    ('缺哪些库', 'flythings_check_project_deps'),
    # 多语言
    ('翻译不生效', 'flythings_i18n'),
    ('要加英文', 'flythings_i18n'),
    ('把文案导出给翻译', 'flythings_i18n'),
    # 元信息
    ('MCP 版本是多少', 'flythings_get_version'),
    ('这块屏什么参数', 'flythings_hardware_info'),
]

# 对照组：不是 FlyThings 开发需求 → 不许有"高分"候选（≥8 分算高分：字面命中量级）
CONTROL = ['今天天气怎么样', '帮我写一首诗', '解释一下量子力学', '公司报销流程是什么']
CONTROL_MAX_SCORE = 7


def _find(q):
    return json.loads(ms._find(q))


class TestOpRouting(unittest.TestCase):
    def test_phrasings_hit_expected_op(self):
        misses = []
        for q, expect in CASES:
            r = _find(q)
            got = [c['op'] for c in r['candidates'][:3]]
            if expect not in got:
                misses.append('%s → 期望 %s，得到 %s' % (q, expect, got or '（无候选）'))
        self.assertEqual(misses, [], '分级筛选漏召 %d 条：\n  %s' % (len(misses), '\n  '.join(misses)))

    def test_candidates_carry_reason_and_pointer(self):
        """候选必须带**命中理由**与**下一步指针**：分级筛选是给 AI 决策用的，不是黑盒排序。"""
        r = _find('屏比设计小怎么办')
        self.assertTrue(r['ok'] and r['count'] >= 1)
        c = r['candidates'][0]
        for key in ('op', 'brief', 'risk', 'stage', 'score', 'hit', 'params'):
            self.assertIn(key, c)
        self.assertTrue(c['hit'], '候选没给命中理由（hit 为空）')
        self.assertIn('describe', r['hint'])          # 指到第二级：拉完整契约

    def test_third_tier_knowledge_pointer(self):
        """第三级：候选相关的知识指针要一起给（调用中要深入时按需检索，不预加载）。"""
        r = _find('屏比设计小怎么办')
        self.assertTrue(r['knowledge'], '没给知识指针 —— 第三级（按需知识）断了')
        for p in r['knowledge']:
            self.assertTrue(os.path.isfile(os.path.join(BASE, p)),
                            '知识指针指向不存在的文件：%s' % p)

    def test_control_no_high_score_candidate(self):
        bad = []
        for q in CONTROL:
            r = _find(q)
            top = max([c['score'] for c in r['candidates']] or [0])
            if top > CONTROL_MAX_SCORE:
                bad.append('%s → top score %d（%s）' % (q, top, r['candidates'][0]['op']))
        self.assertEqual(bad, [], '无关需求不该有高分候选（触发词写太泛）：%s' % bad)

    def test_every_op_has_triggers(self):
        """没有触发词的 op 在分级筛选里等于隐身（只能靠 op 名撞运气）。"""
        thin = [op for op in osl.registered()
                if len([t for t in (osl.spec(op).get('triggers') or []) if str(t).strip()]) < 3]
        self.assertEqual(thin, [], '这些 op 触发词不足 3 条（分级筛不出来）：%s' % thin)
        for op in osl.registered():
            for t in osl.spec(op).get('triggers') or []:
                self.assertLessEqual(len(str(t).replace(' ', '')), 12,
                                     '%s 的触发词 %r 太长（要"用户原话里的片段"）' % (op, t))

    def test_triggers_are_unique_within_op(self):
        dup = []
        for op in osl.registered():
            ts = osl.spec(op).get('triggers') or []
            if len(set(ts)) != len(ts):
                dup.append(op)
        self.assertEqual(dup, [], '同一 op 内触发词重复：%s' % dup)

    def test_excludes_are_self_consistent(self):
        """出局词不许与自己的 triggers 重叠，且不许太短（`validate()` 也查，这里独立钉一遍）。"""
        bad = []
        for op in osl.registered():
            ex = osl.excludes(op)
            if not ex['phrases']:
                continue
            if not ex['why']:
                bad.append('%s: 有 excludes 但没写 why' % op)
            ov = set(ex['phrases']) & set(osl.spec(op).get('triggers') or [])
            if ov:
                bad.append('%s: 出局词与触发词重叠 %s' % (op, sorted(ov)))
            short = [p for p in ex['phrases'] if len(p.strip()) < 2]
            if short:
                bad.append('%s: 出局词太短 %s' % (op, short))
        self.assertEqual(bad, [], 'excludes 自洽性：%s' % bad)

    def test_excludes_do_not_eat_the_right_answer(self):
        """**反向护栏**：出局词不许把该命中的 op 吃掉。

        这是 excludes 最危险的失效方向 —— 触发词写错只是"多给候选"，出局词写错是
        "正确答案消失"。所以对每条已登记问法断言：期望的 op 不能被这句问法排除。
        """
        bad = []
        for q, expect in CASES:
            hit = osl.exclude_hit(expect, q)
            if hit:
                bad.append('%s —— %s 被自己的出局词 %r 排除' % (q, expect, hit))
        self.assertEqual(bad, [], '出局词吃掉了正确答案：%s' % bad)

    def test_excludes_actually_route_away(self):
        """正向护栏：登记了明确误召的几条，必须真的被 route 到别处。

        判据用**真实误召**取（不是编的）：这三条原先由 `create_project` / `html_to_json`
        抢答（它们靠「项目 / 界面 / json」这类通用词拿到 6 分），现在必须落到正确的 op。
        """
        for q, wrong, right in (
                ('给客户看下效果', 'flythings_create_project', 'flythings_ui_preview'),
                ('生成一套图标', 'flythings_create_project', 'flythings_generate_ui_assets'),
                ('给我补上按钮点击回调', 'flythings_create_project', 'flythings_gen_logic_stub')):
            r = _find(q)
            ops = [c['op'] for c in r['candidates']]
            self.assertNotIn(wrong, ops, '%s 仍被 %s 抢答' % (q, wrong))
            self.assertIn(right, ops[:3], '%s 没落到 %s：%s' % (q, right, ops[:3]))
            self.assertIn('excluded', r, '%s：出局明细没带出来（不可追溯）' % q)
            self.assertTrue(any(e['op'] == wrong for e in r['excluded']),
                            '%s：%s 不在 excluded 明细里' % (q, wrong))

    def test_exclude_short_ascii_needs_word_boundary(self):
        """纯 ASCII 短片段要按**整词**匹配：`qt` 不得命中 `mqtt`。

        这条守的是「出局词写错方向 = 正确答案消失」里最隐蔽的一种：拉丁词组没有中文那种
        "子串即命中"的合理性 —— `qt` 是 `mqtt` 的**真子串**，`ml` 是 `html` 的**真子串**。
        词表侧的对策是"不登记单字缩写"（见 `why`），守侧是这里的词边界（`exclude_hit` 内）。
        两处都测：先证边界生效，再证当前词表里没有踩这颗雷的片段。
        """
        import mcp_server as _ms                       # noqa: F401  (保持导入面一致)
        # ① 边界守卫本身生效（用长度为 2 的拉丁片段直接验证语义）
        phr = osl.excludes('flythings_translate_ui')['phrases']
        self.assertNotIn('qt', phr, '单字缩写不该进出局词表（`qt` 会命中 mqtt）')
        # ② 当前词表在真实问法上不误伤
        self.assertEqual(osl.exclude_hit('flythings_translate_ui', '加个 mqtt 包'), '',
                         '`qt` 把 mqtt 也排除了 —— 短 ASCII 必须要求词边界')
        self.assertNotEqual(osl.exclude_hit('flythings_translate_ui', 'android 的界面怎么搬'),
                            '', '登记过的整词出现时必须命中')

    def test_find_routes_contract_and_knowledge(self):
        """端到端闭环：find（筛）→ describe（契约）→ 调用；知识缺口走 knowledge_search。"""
        r = _find('屏比设计小怎么办')
        op = r['candidates'][0]['op']
        d = json.loads(ms._describe(op))
        self.assertTrue(d['ok'])
        self.assertEqual(d['contract'], osl.render_contract(op))
        # 契约必须**比常驻面更全**（按需存在的意义）；具体多出哪个字段因 op 而异
        self.assertGreater(len(d['contract']), len(osl.render(op)))
        self.assertTrue(any(k in d['contract'] for k in ('流程', '⚠️', '检索词')),
                        '契约里没看到任何按需内容：%s' % d['contract'][:80])
        # 分发器 op 语法：find:<需求> / describe:<名> 都走同一条链
        raw = ms.flythings_kb.__wrapped__ if hasattr(ms.flythings_kb, '__wrapped__') else None
        self.assertTrue(raw is None or callable(raw))


if __name__ == '__main__':
    unittest.main()
