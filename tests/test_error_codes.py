# -*- coding: utf-8 -*-
"""域⑫「错误码表」用例。

钉住两件事：
  · 码表与源码**一一对应**（漏登记 / 孤儿码都在门禁上红）
  · `normalize_result` 会把 action / who / 默认 retryable **注入每次失败返回**
    —— 这样调用点只写 code+msg，处置建议不必在每个构造点各写一遍
"""
import json
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import error_codes_loader as E                             # noqa: E402
import kb_tools                                            # noqa: E402


class TestRegistry(unittest.TestCase):

    def test_self_check(self):
        errs = E.validate()
        self.assertEqual(errs, [], '错误码表自检未过：\n  - %s' % '\n  - '.join(errs))

    def test_scan_actually_sees_codes(self):
        """防止「扫不到任何码」这种假绿（正则坏了会一条错都不报）。"""
        found = E.scan_source()
        self.assertGreaterEqual(len(found), 15, '扫到的码太少，正则可能失效：%s' % sorted(found))
        self.assertIn('BAD_PARAMS', found)

    def test_field_domains(self):
        for name, c in E.codes().items():
            self.assertIn(c.get('who'), ('caller', 'env', 'device', 'bug'), name)
            self.assertIsInstance(c.get('retryable'), bool, name)

    def test_action_is_imperative(self):
        """action 要是「下一步做什么」，不能只是把 meaning 抄一遍。"""
        for name, c in E.codes().items():
            self.assertNotEqual(c.get('action'), c.get('meaning'), name)

    def test_render_covers_all_codes(self):
        md = E.render_table()
        for name in E.codes():
            self.assertIn('`%s`' % name, md, '码表渲染漏了 %s' % name)


class TestEnrich(unittest.TestCase):

    def test_fills_action_and_who(self):
        err = E.enrich({'code': 'NO_DEVICE', 'msg': 'x'})
        self.assertTrue(err['retryable'])
        self.assertEqual(err['who'], 'device')
        self.assertTrue(err['action'])

    def test_explicit_retryable_wins(self):
        """显式写的 retryable 优先于表里的默认值（调用点比表更懂这一次的情况）。"""
        err = E.enrich({'code': 'BAD_PARAMS', 'msg': 'x', 'retryable': False})
        self.assertFalse(err['retryable'])

    def test_unknown_code_passes_through(self):
        err = {'code': 'NOT_REGISTERED_YET', 'msg': 'x'}
        self.assertEqual(E.enrich(dict(err)), err)

    def test_code_lookup_never_raises(self):
        self.assertIsNone(E.code('TOTALLY_UNKNOWN'))
        self.assertEqual(E.describe('TOTALLY_UNKNOWN'), {})


class TestNormalizeInjectsAction(unittest.TestCase):
    """端到端：真实 op 失败时，返回体里必须带码表补出来的 action。"""

    def test_tool_raised_and_bad_params(self):
        r = json.loads(kb_tools.flythings_read_json(json_path='D:/no/such/file.json'))
        self.assertFalse(r['ok'])
        self.assertIn(r['error']['code'], ('DATA_MISSING', 'BAD_SOURCE'))
        self.assertTrue(r['error'].get('action'), '失败返回必须自带处置建议')
        self.assertIn(r['error'].get('who'), ('caller', 'env', 'device', 'bug'))

    def test_unknown_op_env_err_has_action(self):
        import mcp_server as s
        r = json.loads(s._env_err('BAD_ARGS', 'x', 'y', True))
        self.assertFalse(r['ok'])
        self.assertTrue(r['error'].get('action'), '_env_err 走的是手工构造，也要补 action')

    def test_envelope_shape_is_uniform(self):
        """所有失败返回同一形状：ok/op/error{code,msg,hint,retryable,action}/warnings。"""
        import mcp_server as srv
        for call in (lambda: kb_tools.flythings_read_json(json_path='D:/nope.json'),
                     lambda: kb_tools.flythings_project_state(action='bogus'),
                     lambda: srv._env_err('BAD_ARGS', 'x', 'y', True)):
            o = json.loads(call())
            self.assertIn('ok', o)
            self.assertIn('warnings', o)
            err = o.get('error') or {}
            for k in ('code', 'msg', 'retryable'):
                self.assertIn(k, err, '失败返回缺 %s：%s' % (k, o))


if __name__ == '__main__':
    unittest.main()
