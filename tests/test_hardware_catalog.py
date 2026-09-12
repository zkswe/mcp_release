# -*- coding: utf-8 -*-
"""硬件型号库契约：hardware_catalog.json 是唯一事实来源，工具只读它，文档是它的派生。

为什么要有（沛哥 2026-09-12 需求：硬件文档模块）：型号 → 分辨率/按键值 一旦查错，
建工程分辨率与按键分发会全线错；而「查不到就按同系列外推」是这类库最危险的失败模式。
本用例钉住：命中/宽松匹配/别名、未收录只给候选不猜规格、未知平台报错、文档与 json 同步。
"""
import io
import json
import os
import unittest

import _util as U
import hardware_tools as hw
import platforms as pl


class TestHardwareCatalog(unittest.TestCase):
    def setUp(self):
        hw.load(force=True)
        self.cat, _ = hw.load()

    def test_catalog_json_valid_and_platforms_known(self):
        """catalog 里的平台名必须是 platforms.py 规范名（防写出 'v85x'/'Z21X' 这类幽灵平台）。"""
        cats = self.cat.get('platforms') or {}
        self.assertTrue(cats, 'hardware_catalog.json 里一个平台都没有')
        for name in cats:
            self.assertEqual(pl.normalize(name), name,
                             '平台名非规范名: %r' % name)

    def test_catalog_files_and_doc_exist(self):
        self.assertTrue(os.path.isfile(os.path.join(U.BASE, 'hardware_catalog.json')))
        self.assertTrue(os.path.isfile(os.path.join(U.BASE, 'knowledge', 'hardware',
                                                    'hardware-models.md')))

    def test_doc_matches_catalog(self):
        """派生文档必须与 json 一致（否则检索到的是旧型号表）→ 跑 gen_hardware_doc.py。"""
        p = os.path.join(U.BASE, 'knowledge', 'hardware', 'hardware-models.md')
        want = hw.build_markdown(self.cat)
        got = io.open(p, encoding='utf-8').read()
        self.assertEqual(got, want,
                         'hardware-models.md 与 hardware_catalog.json 漂移：'
                         'python scripts/gen_hardware_doc.py')

    # ---- op 契约（走分发器，与客户端同一条路径）----

    def test_op_no_args_lists_platforms(self):
        r = U.jcall('flythings_hardware_info', {})
        self.assertTrue(r['ok'])
        self.assertEqual(r['mode'], 'overview')
        names = [p['platform'] for p in r['platforms']]
        self.assertIn('V85X', names)
        self.assertIn('Z21', names)
        self.assertTrue(r['modelCount'] >= 3)
        # 无具体型号时的一句话准则必须在（防 AI 把「未收录」当阻塞）
        self.assertIn('分辨率', r['whenNoModel'])

    def test_op_platform_filter(self):
        r = U.jcall('flythings_hardware_info', {'platform': 'z21'})
        self.assertTrue(r['ok'])
        self.assertEqual([p['platform'] for p in r['platforms']], ['Z21'])

    def test_op_model_hit_returns_spec(self):
        r = U.jcall('flythings_hardware_info', {'model': 'PocketDisplay4'})
        self.assertTrue(r['ok'])
        self.assertEqual(r['mode'], 'model')
        self.assertEqual(r['platform'], 'V85X')
        hw_ = r['hardware']
        self.assertEqual(hw_['resolution'], '480x800')
        self.assertEqual(hw_['screen']['width'], 480)
        self.assertEqual(hw_['screen']['height'], 800)
        self.assertEqual(hw_['keys']['values'], [105, 103, 108])
        self.assertTrue(r['nextSteps']), '命中后必须给出落地建议'
        # 预设参数：开工直接照抄（平台/分辨率/方向/按键），省掉后续反复核对
        self.assertEqual(r['preset']['platform'], 'V85X')
        self.assertEqual(r['preset']['resolution'], '480x800')
        self.assertEqual(r['preset']['keys'], [105, 103, 108])

    def test_op_model_match_is_loose_and_alias_aware(self):
        """忽略大小写/连字符/下划线 + 别名（SW80480070D_C == sw80480070dc）。"""
        for q in ('sw80480070d_c', 'SW80480070D-C', 'SW80480070DC'):
            r = U.jcall('flythings_hardware_info', {'model': q})
            self.assertTrue(r['ok'], q)
            self.assertEqual(r['model'], 'SW80480070D_C')
        r = U.jcall('flythings_hardware_info', {'model': 'pd4'})
        self.assertTrue(r['ok'])
        self.assertEqual(r['model'], 'PocketDisplay4')

    def test_op_unknown_model_never_invents_spec(self):
        """未收录型号：回 not_found + 候选清单，**不得**给出任何规格字段。"""
        r = U.jcall('flythings_hardware_info', {'model': 'SW99999999Z_X'})
        self.assertFalse(r['ok'])
        self.assertEqual(r['mode'], 'not_found')
        self.assertEqual(r['error']['code'], 'MODEL_NOT_FOUND')
        self.assertNotIn('hardware', r)
        self.assertIn('available', r)
        self.assertIn('Z21', r['available'])
        # 定位（沛哥 2026-09-12）：没型号不卡流程——必须给「平台 + 分辨率就能开工」的 fallback
        self.assertEqual(r['fallback']['need'], ['平台', '分辨率'])
        self.assertTrue(r['fallback']['advice'])

    def test_op_unknown_platform_rejected(self):
        r = U.jcall('flythings_hardware_info', {'platform': 'NOPE'})
        self.assertFalse(r['ok'])
        self.assertEqual(r['error']['code'], 'BAD_PLATFORM')
        blob = json.dumps(r, ensure_ascii=False)
        for n in pl.supported():
            self.assertIn(n, blob)

    def test_op_ambiguous_needs_platform(self):
        """近似命中多个时必须要求消歧，而不是挑一个返回。"""
        r = U.jcall('flythings_hardware_info', {'model': 'SW8001280101D'})
        self.assertTrue(r['ok'])
        self.assertEqual(r['mode'], 'ambiguous')
        self.assertTrue(len(r['candidates']) >= 1)

    def test_entry_in_manifest_and_gate_catalog(self):
        m = U.manifest()
        ops = {o['op'] for o in m['ops']}
        self.assertIn('flythings_hardware_info', ops)
        by = {o['op']: o for o in m['ops']}
        self.assertEqual(by['flythings_hardware_info']['risk'], 'read')
        self.assertIn(by['flythings_hardware_info']['category'], ('kbase', 'hardware'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
