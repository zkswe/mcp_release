# -*- coding: utf-8 -*-
"""分发器契约：op 清单 / 未知 op / 参数错误 / envelope 形状 / 版本输出 / manifest 新鲜度。

为什么要有（检讨报告 §2.2、§3.5）：35+ 个 op 此前**零契约测试**，
参数名写错、envelope 变形、清单漂移都只能等用户在真机上撞到。
本文件只测「外部契约」，不测业务结果（业务在 test_layout_flow / test_asset_pipeline）。
"""
import json
import os
import subprocess
import sys
import unittest

import _util as U


class TestOpCatalog(unittest.TestCase):
    def test_list_matches_manifest_and_module(self):
        import kb_tools
        cat = U.jcall('list')
        names = [o['op'] for o in cat['ops']]
        self.assertEqual(cat['count'], len(kb_tools.OP_NAMES))
        self.assertEqual(sorted(names), sorted(kb_tools.OP_NAMES))
        self.assertEqual(sorted(names), sorted(o['op'] for o in U.manifest()['ops']))
        for o in cat['ops']:
            self.assertTrue(o['brief'], '%s 缺一行简介' % o['op'])
            self.assertIsInstance(o['args'], list)

    def test_every_op_has_risk_and_category(self):
        for o in U.manifest()['ops']:
            self.assertIn(o['risk'], ('read', 'write', 'device'), o['op'])
            self.assertTrue(o['category'], o['op'])


class TestDispatcherErrors(unittest.TestCase):
    def test_unknown_op(self):
        r = U.jcall('flythings_not_an_op')
        self.assertFalse(r['ok'])
        self.assertEqual(r['error']['code'], 'UNKNOWN_OP')
        self.assertFalse(r['error']['retryable'])

    def test_unknown_op_candidates(self):
        r = U.jcall('flythings_searc')
        self.assertIn('flythings_search', r.get('candidates', []))

    def test_bad_json_args(self):
        r = json.loads(U.call('flythings_get_version', None))
        self.assertTrue(r['ok'])                      # 空 args 合法
        for raw in ('{oops', '{oops'):
            r = json.loads(U.call('flythings_search', raw))
            self.assertFalse(r['ok'])
            self.assertEqual(r['error']['code'], 'BAD_ARGS')

    def test_non_object_args(self):
        raw = U.call('flythings_search', json.dumps([1, 2]))
        r = json.loads(raw)
        self.assertFalse(r['ok'])
        self.assertEqual(r['error']['code'], 'BAD_ARGS')

    def test_wrong_param_name(self):
        r = U.jcall('flythings_read_json', {'nope': 1})
        self.assertFalse(r['ok'])
        self.assertEqual(r['error']['code'], 'BAD_PARAMS')
        self.assertIn('json_path', r['error']['hint'])   # 回正确签名，AI 可直接改


class TestEnvelopeForEveryOp(unittest.TestCase):
    """每个（非真机）op 用空参数调用都必须回可解析 envelope，且不许抛异常。"""

    def test_empty_args_never_raises(self):
        bad = []
        for o in U.manifest()['ops']:
            if o['risk'] == 'device':        # 会连真机/adb，跳过（另由 --screenshot 冒烟覆盖）
                continue
            try:
                r = json.loads(U.call(o['op']))
            except Exception as e:
                bad.append('%s raised %r' % (o['op'], e))
                continue
            if not isinstance(r, dict) or not isinstance(r.get('ok'), bool):
                bad.append('%s bad envelope: %s' % (o['op'], str(r)[:80]))
                continue
            if r.get('op') != o['op']:
                bad.append('%s op field = %s' % (o['op'], r.get('op')))
            if r['ok'] is False and not isinstance(r.get('error'), dict):
                bad.append('%s ok=false 但 error 不是对象' % o['op'])
        self.assertEqual(bad, [])


class TestVersionTool(unittest.TestCase):
    def test_compact_default(self):
        import kb_tools
        r = U.jcall('flythings_get_version')
        self.assertTrue(r['ok'])
        self.assertEqual(r['version'], kb_tools.MCP_VERSION)
        self.assertEqual(r['toolCount'], len(kb_tools.OP_NAMES))
        self.assertLess(len(json.dumps(r, ensure_ascii=False)), 6000,
                        'compact 默认不该把整部变更史塞回来（token 炸弹回归）')
        self.assertNotIn('features', [k for k in r if k == 'features'] or [])

    def test_full_history_on_request(self):
        r = U.jcall('flythings_get_version', {'compact': False})
        self.assertTrue(r.get('features'))


class TestManifestFreshness(unittest.TestCase):
    def test_gen_manifest_check(self):
        rc = subprocess.call([sys.executable, os.path.join(U.BASE, 'scripts', 'gen_manifest.py'),
                              '--check'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertEqual(rc, 0, 'tools_manifest.json 与代码/风险表不一致：python scripts/gen_manifest.py')


if __name__ == '__main__':
    unittest.main(verbosity=2)
