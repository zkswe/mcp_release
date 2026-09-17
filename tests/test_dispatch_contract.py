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
        self.assertIn('flythings_knowledge_search', r.get('candidates', []))

    def test_renamed_op_reports_new_name(self):
        """v0.27.36 合并/改名的 6 个旧名：必须回 OP_RENAMED + 新名（不执行，不留隐式别名）。"""
        import kb_tools
        for old, new in kb_tools.RENAMED.items():
            r = U.jcall(old, {'query': 'x'})
            self.assertFalse(r['ok'], old)
            self.assertEqual(r['error']['code'], 'OP_RENAMED', old)
            self.assertIn(new, r['error']['hint'], old)
            self.assertNotIn(old, kb_tools.OP_NAMES, '%s 不该再留在清单里' % old)

    def test_bad_json_args(self):
        r = json.loads(U.call('flythings_get_version', None))
        self.assertTrue(r['ok'])                      # 空 args 合法
        for raw in ('{oops', '{oops'):
            r = json.loads(U.call('flythings_knowledge_search', raw))
            self.assertFalse(r['ok'])
            self.assertEqual(r['error']['code'], 'BAD_ARGS')

    def test_non_object_args(self):
        raw = U.call('flythings_knowledge_search', json.dumps([1, 2]))
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
        # v0.27.87：每条特性也要有限长（条目写长了同样会把默认返回体撑爆）
        self.assertTrue(r['recent'])
        for f in r['recent']:
            self.assertLessEqual(len(f), kb_tools.COMPACT_FEATURE_CHARS + 20, f[:60])
        long_ = [f for f in kb_tools.MCP_FEATURES if len(f) > kb_tools.COMPACT_FEATURE_CHARS]
        self.assertTrue(long_, '假定至少有一条特性超过截断长度（否则本用例没盯住东西）')
        self.assertTrue(any('compact=False' in f for f in r['recent']),
                        '截断后要指路 compact=False')

    def test_full_history_on_request(self):
        r = U.jcall('flythings_get_version', {'compact': False})
        self.assertTrue(r.get('features'))


class TestManifestFreshness(unittest.TestCase):
    def test_gen_manifest_check(self):
        rc = subprocess.call([sys.executable, os.path.join(U.BASE, 'scripts', 'gen_manifest.py'),
                              '--check'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertEqual(rc, 0, 'tools_manifest.json 与代码/风险表不一致：python scripts/gen_manifest.py')


class TestToolSurfaceModes(unittest.TestCase):
    """工具面三种模式（v0.27.34）：默认只 1 个分发器（省 token），all / flat 才注册独立工具。"""

    SNIP = ("import sys,json,asyncio;sys.path.insert(0,%r);import mcp_server as m;"
            "ts=asyncio.run(m.mcp.list_tools());"
            "print(json.dumps({'mode':m.MODE,'n':len(ts),'names':sorted(t.name for t in ts)}))")

    def _probe(self, mode=None):
        env = dict(os.environ)
        env.pop('FLYTHINGS_MCP_MODE', None)
        if mode:
            env['FLYTHINGS_MCP_MODE'] = mode
        r = subprocess.run([sys.executable, '-X', 'utf8', '-c', self.SNIP % U.BASE],
                           capture_output=True, text=True, env=env, cwd=U.BASE)
        self.assertTrue(r.stdout.strip(), '子进程无输出: %s' % (r.stderr or '')[-200:])
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_default_is_dispatcher_only(self):
        d = self._probe()
        self.assertEqual(d['mode'], 'dispatcher')
        self.assertEqual(d['names'], ['flythings_kb'],
                         '默认模式应只暴露 1 个入口（32 份 schema 常驻≈1 万 token 的回归）')

    def test_all_mode_keeps_backward_compat(self):
        import kb_tools
        d = self._probe('all')
        self.assertEqual(d['n'], len(kb_tools.OP_NAMES) + 1)
        self.assertIn('flythings_kb', d['names'])
        self.assertIn('flythings_knowledge_search', d['names'])

    def test_flat_mode_and_flat_server(self):
        import kb_tools
        d = self._probe('flat')
        self.assertEqual(sorted(d['names']), sorted(kb_tools.OP_NAMES))
        self.assertEqual(d['n'], len(kb_tools.OP_NAMES))
        r = subprocess.run([sys.executable, '-X', 'utf8', '-c',
                            ("import sys,json,asyncio;sys.path.insert(0,%r);"
                             "import mcp_server_flat as f;ts=asyncio.run(f.mcp.list_tools());"
                             "print(json.dumps(sorted(t.name for t in ts)))" % U.BASE)],
                           capture_output=True, text=True, cwd=U.BASE)
        self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1]), sorted(kb_tools.OP_NAMES),
                         'mcp_server_flat.py 必须恰好注册 32 个独立工具')

    def test_unknown_mode_falls_back_to_dispatcher(self):
        self.assertEqual(self._probe('not-a-mode')['mode'], 'dispatcher')


if __name__ == '__main__':
    unittest.main(verbosity=2)
