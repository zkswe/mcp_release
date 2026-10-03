# -*- coding: utf-8 -*-
"""派生页比较口径（derived_md）：`verified_at` 的取值与"只差一天"的免疫。

钉住三件事：
  ① `split_fm()` 能把 front-matter 与正文切开（没有 front-matter 时不吞正文）
  ② `carry_day()` —— **正文一致就沿用旧日期**。这是目录型/无 `updated` 真源的必需件：
     改真源与重生成派生页常是同一笔提交，生成器跑在提交前，日期永远落后一笔；
     没有它 `--check` 提交一次红一次（2026-10-03 实测：components 目录页就是这么红的）
  ③ 正文**有**变化时不许沿用旧日期 —— 否则真漂移会被"日期照抄"糊过去，门禁就废了
"""
import os
import sys
import unittest

import _util as U

BASE = U.BASE
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import derived_md  # noqa: E402

CUR = ('---\nid: x\ntitle: t\nverified_at: 2026-10-02\nstale_days: 180\n---\n\n'
       '# 标题\n\n正文 A\n')


class TestSplitFm(unittest.TestCase):
    def test_splits_front_matter_from_body(self):
        fm, body = derived_md.split_fm(CUR)
        self.assertIn('verified_at: 2026-10-02', fm)
        self.assertNotIn('---', body)
        self.assertTrue(body.lstrip().startswith('# 标题'))

    def test_no_front_matter_keeps_text(self):
        fm, body = derived_md.split_fm('# 只有正文\n')
        self.assertEqual(fm, '')
        self.assertEqual(body, '# 只有正文\n')

    def test_crlf_still_splits(self):
        fm, _ = derived_md.split_fm(CUR.replace('\n', '\r\n'))
        self.assertIn('verified_at', fm)


class TestCarryDay(unittest.TestCase):
    def test_carries_when_body_identical(self):
        want = CUR.replace('2026-10-02', '2026-10-03')
        self.assertEqual(derived_md.split_fm(derived_md.carry_day(CUR, want))[0],
                         'id: x\ntitle: t\nverified_at: 2026-10-02\nstale_days: 180')

    def test_does_not_carry_when_body_changed(self):
        want = CUR.replace('正文 A', '正文 B').replace('2026-10-02', '2026-10-03')
        out = derived_md.carry_day(CUR, want)
        self.assertIn('verified_at: 2026-10-03', out)
        self.assertIn('正文 B', out)

    def test_does_not_carry_when_body_changed_but_date_same(self):
        # 真漂移：正文变了却没人重生成 —— 比对必须仍然是"不一致"
        want = CUR.replace('正文 A', '正文 B')
        self.assertFalse(derived_md.same(CUR, derived_md.carry_day(CUR, want)))

    def test_no_cur_is_noop(self):
        want = CUR.replace('2026-10-02', '2026-10-03')
        self.assertEqual(derived_md.carry_day('', want), want)

    def test_missing_key_is_noop(self):
        cur = CUR.replace('verified_at: 2026-10-02\n', '')
        want = CUR.replace('2026-10-02', '2026-10-03')
        self.assertEqual(derived_md.carry_day(cur, want), want)

    def test_format_only_noise_still_carries(self):
        # 人用编辑器格式化过（表格对齐/行尾转义）→ 不算正文变化，日期照旧
        cur = CUR + '\n| a | b |\n|---|---|\n| 1 | 2 |\n'
        want = (CUR.replace('2026-10-02', '2026-10-03')
                + '\n| a | b |\n| --- | --- |\n| 1   | 2   |\n')
        self.assertIn('2026-10-02', derived_md.carry_day(cur, want))

    def test_real_generator_is_green(self):
        """端到端：组件目录页当前落盘件与重生成件一致（这条红的代价最高）。"""
        import subprocess
        p = subprocess.run([sys.executable, os.path.join(BASE, 'scripts', 'gen_components_catalog.py'),
                            '--check'], capture_output=True, cwd=BASE, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout.decode('utf-8', 'replace')
                         + p.stderr.decode('utf-8', 'replace'))


if __name__ == '__main__':
    unittest.main()
