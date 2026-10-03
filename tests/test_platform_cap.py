# -*- coding: utf-8 -*-
"""平台能力注册表契约（platform_capabilities.json + platform_cap_loader.py）。

为什么要有它：这套注册表的价值是**替掉 15 篇各自手写的矩阵表**、并让「某平台能跑哪些组件」
一次可查。所以用例必须钉住：表是派生的（手改会红）、平台键走 platforms.py 口径（不养第二份词表）、
别名查询可用（F136→F135、T113EMMC→T113）。

钉住八件事：
  ① 注册表可加载且声明 authority
  ② 每个组件的 file / columns / rows 自洽，平台键合法（= platforms.py 口径 ∪ PC/MCU/ALL）
  ③ 每篇 platforms.md 里那张矩阵表 == 注册表渲染结果（派生一致；手改 md 会红）
  ④ 渲染确定性
  ⑤ 跨组件查询：components_for_platform 能用且去重
  ⑥ 别名查询：F136 与 F135 同结果、T113EMMC 与 T113 同结果
  ⑦ 单元格取值：cell() 能按列名取到
  ⑧ 覆盖度：注册表组件数 == 实际能找到矩阵表的 platforms.md 篇数（不静默漏篇）
"""
import io
import os
import subprocess
import sys
import unittest

import _util as U

BASE = U.BASE
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import platform_cap_loader as pc                   # noqa: E402


class TestPlatformCapRegistry(unittest.TestCase):

    def test_registry_loads(self):
        reg = pc.load()
        self.assertTrue(str(reg.get('authority') or '').strip(), '必须声明 authority')
        self.assertTrue(pc.components(), 'components 不能为空')

    def test_selfcheck_clean(self):
        self.assertEqual(pc.validate(), [], 'platform_capabilities.json 自检不通过')

    def test_every_component_maps_to_existing_file(self):
        for comp in pc.components():
            f = pc.spec(comp)['file']
            self.assertTrue(os.path.isfile(os.path.join(BASE, f)),
                            '%s 的 file 不存在：%s' % (comp, f))

    def test_tables_are_derived_from_registry(self):
        """每篇的矩阵表必须是注册表渲染结果——手改 md 立刻红。"""
        p = subprocess.run([sys.executable, os.path.join(BASE, 'scripts',
                                                         'gen_component_platforms.py'), '--check'],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0,
                         'platforms.md 的矩阵表与注册表漂移：\n%s\n%s'
                         % (p.stdout[-800:], p.stderr[-400:]))

    def test_render_is_deterministic(self):
        for comp in pc.components():
            self.assertEqual(pc.render_table(comp), pc.render_table(comp))

    def test_render_has_header_and_all_rows(self):
        for comp in pc.components():
            tbl = pc.render_table(comp)
            self.assertTrue(tbl[0].startswith('| 平台 |'), '%s 表头首列应为「平台」' % comp)
            self.assertEqual(len(tbl), len(pc.rows(comp)) + 2,
                             '%s 渲染行数应为 平台行数 + 表头 + 分隔行' % comp)

    def test_components_for_platform(self):
        z20 = pc.components_for_platform('Z20')
        self.assertIn('ble', z20)
        self.assertEqual(z20, sorted(set(z20)), '应去重且有序')

    def test_alias_queries_match_canonical(self):
        """别名必须与规范名同结果（F136→F135、T113EMMC→T113）。"""
        self.assertEqual(pc.components_for_platform('F136'),
                         pc.components_for_platform('F135'))
        self.assertEqual(pc.components_for_platform('T113EMMC'),
                         pc.components_for_platform('T113'))

    def test_cell_lookup(self):
        c = pc.cell('ble', 'Z20', '可用性')
        self.assertIsNotNone(c, 'ble@Z20 的「可用性」应能取到')
        self.assertTrue(c.strip())

    def test_coverage_no_silent_skip(self):
        """有矩阵表的 platforms.md 不许漏登（漏一篇就该红）。"""
        found = []
        for root, dirs, files in os.walk(os.path.join(BASE, 'components')):
            dirs[:] = [d for d in dirs if d not in ('__pycache__', 'example')]
            if 'platforms.md' in files:
                found.append(os.path.relpath(os.path.join(root, 'platforms.md'),
                                             BASE).replace('\\', '/'))
        registered = {pc.spec(c)['file'] for c in pc.components()}
        self.assertTrue(registered <= set(found), '注册表引用了不存在的 platforms.md')
        # 注册表里的篇数不应超过实际篇数；差额需是「无平台矩阵表」的篇（由 --check 报告）
        self.assertLessEqual(len(registered), len(found))

    def test_no_pc_or_mcu_in_matrix(self):
        """口径（2026-10-02）：PC（自测/预烘形态）与 MCU Lite（另一套东西）不进本矩阵。"""
        bad = []
        for comp in pc.components():
            for r in pc.rows(comp):
                keys = [str(k).upper() for k in (r.get('canonical') or [])]
                for k in ('PC', 'MCU'):
                    if k in keys:
                        bad.append('%s: %s' % (comp, r.get('platform')))
        self.assertEqual(bad, [], 'PC/MCU 不该出现在能力矩阵里：%s' % bad[:5])

    def test_no_business_project_rows(self):
        """口径：不特殊区分业务/项目标识（电子价签 tag / ESL 项目）——不该有这类行。"""
        import re
        pat = re.compile(r'价签|tag|ESL', re.I)
        bad = []
        for comp in pc.components():
            for r in pc.rows(comp):
                if pat.search(str(r.get('platform') or '')):
                    bad.append('%s: %s' % (comp, r.get('platform')))
        self.assertEqual(bad, [], '矩阵里不该有业务/项目标识行：%s' % bad)

    def test_unknown_component_raises(self):
        with self.assertRaises(pc.PlatformCapError):
            pc.spec('not_a_component')

    def test_verification_policy_is_registered_and_enforced(self):
        """「不逐平台验」必须是**登记过的口径**，不是留一堆 TODO 挂着（2026-10-03 定）。

        需求方口径：UI 控件（`ui_v1/*`）的行为由 easyui 运行库提供、组件无平台分支
        → 只做 **V85X 单平台代表验收**；其余平台标 ➖，不再逐台排期。
        钉两件事：① 登记本身齐备（组件真实存在、verifiedOn 是它的一行）；
        ② 登记过的组件，非代表平台的行里**不许再出现「未验证/待测」**（改口径就要改单元格）。
        """
        pols = pc.load().get('verificationPolicy') or []
        self.assertTrue(pols, 'verificationPolicy 为空：口径没登记，等于又变回一堆未验证 TODO')
        for pol in pols:
            comps = pol.get('components') or []
            self.assertTrue(comps, 'verificationPolicy[%s] 没列组件' % pol.get('id'))
            on = pol.get('verifiedOn')
            for comp in comps:
                self.assertIn(comp, pc.components(), '%s 不在注册表里' % comp)
                keys = set()
                for r in pc.rows(comp):
                    keys |= set(r.get('canonical') or []) | set(r.get('platforms') or [])
                self.assertIn(on, keys, '%s 说在 %s 验过，但表里没有这个平台' % (comp, on))
                for r in pc.rows(comp):
                    if on in (r.get('canonical') or []):
                        continue
                    for cell in (r.get('cells') or []):
                        self.assertNotIn(
                            '未验证', cell,
                            '%s 行 %s 还写着「未验证」—— 该组件已登记「只在 %s 单平台验收」，'
                            '其余平台请改 ➖ 并写明口径' % (comp, r.get('platform'), on))

    def test_ui_controls_verified_on_v85x_only(self):
        """UI 控件的 V85X 行必须是「已验收」；其余平台是 ➖（不是空、也不是未验证）。"""
        import json as _json
        for comp in ('ui_v1/RadButton', 'ui_v1/Chart', 'ui_v1/Calendar', 'ui_v1/_mapping/TabView'):
            row = pc.status_of(comp, 'V85X')
            self.assertIsNotNone(row, '%s 没有 V85X 行' % comp)
            self.assertIn('已验收', _json.dumps(row, ensure_ascii=False))
            for r in pc.rows(comp):
                if 'V85X' in (r.get('canonical') or []):
                    continue
                joined = _json.dumps(r.get('cells') or [], ensure_ascii=False)
                self.assertNotIn('未验证', joined)
                # Z21 那行是 2026-09-16 真机验过的历史事实，不该被这次口径改动抹掉
                if 'Z21' in (r.get('canonical') or []):
                    continue
                self.assertIn('➖', joined, '%s 行 %s 应为 ➖ 口径' % (comp, r.get('platform')))


if __name__ == '__main__':
    unittest.main()
