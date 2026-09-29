# -*- coding: utf-8 -*-
"""契约用例：知识库生长机制 P1（front-matter / 本地层捕获 / 未命中记账 / 脱敏导出 / 复验）。

**离线**（零真机、零网络）。钉住的是"闸门与真相"：
  · front-matter 缺字段 / 非法状态 / **verified 却没证据** → 必须报错（不许口头结论当已验证）
  · capture 写**用户本地层**（绝不写 MCP 安装目录）+ 指纹去重 → 回 duplicateOf 而非新建
  · 未命中落盘 → gaps 聚合可复现；导出**强制脱敏**（IP/本机路径/凭据/主机名/手机号）
  · 复验：offline 跑了才算过；manual 不算通过；real-device 无设备 → 显式 skipped
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, 'scripts'))
import kb_local as kbl          # noqa: E402


class _KBBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='kb_')
        self._old = os.environ.get('FLYTHINGS_KB_DIR')
        os.environ['FLYTHINGS_KB_DIR'] = os.path.join(self.tmp, 'kb_local')

    def tearDown(self):
        if self._old is None:
            os.environ.pop('FLYTHINGS_KB_DIR', None)
        else:
            os.environ['FLYTHINGS_KB_DIR'] = self._old
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestFrontMatter(_KBBase):
    def test_roundtrip_keeps_fields_and_evidence(self):
        meta = {'id': 'devflow-x', 'title': '标题: 带冒号', 'category': 'devflow',
                'platforms': ['Z20', 'Z21'], 'tags': ['a', 'b'], 'status': 'verified',
                'confidence': 'offline', 'verified_at': '2026-09-29', 'stale_days': 180,
                'origin': 'total', 'source': 'unit-test', 'needs_evidence': False,
                'evidence': [{'kind': 'offline', 'cmd': 'echo ok', 'expect_rc': 0}]}
        text = kbl.dump_front_matter(meta, '# 标题\n\n正文\n')
        got, body, err = kbl.parse_front_matter(text)
        self.assertEqual(err, '')
        self.assertEqual(got['id'], 'devflow-x')
        self.assertEqual(got['platforms'], ['Z20', 'Z21'])
        self.assertEqual(got['evidence'][0]['cmd'], 'echo ok')
        self.assertEqual(got['evidence'][0]['expect_rc'], 0)
        self.assertFalse(got['needs_evidence'])
        self.assertIn('正文', body)

    def test_validate_meta_rules(self):
        good = {'id': 'a', 'title': 't', 'category': 'devflow', 'status': 'verified',
                'confidence': 'offline', 'verified_at': '2026-09-29', 'stale_days': 180,
                'origin': 'total', 'source': 's',
                'evidence': [{'kind': 'offline', 'cmd': 'echo'}]}
        self.assertEqual(kbl.validate_meta(good), [])
        no_ev = dict(good, evidence=[])
        self.assertTrue(any('needs_evidence' in e for e in kbl.validate_meta(no_ev)),
                        'verified 无证据必须报错')
        ok2 = dict(no_ev, needs_evidence=True)
        self.assertEqual(kbl.validate_meta(ok2), [])
        bad_status = dict(good, status='done')
        self.assertTrue(any('status' in e for e in kbl.validate_meta(bad_status)))
        missing = dict(good)
        missing.pop('source')
        self.assertTrue(any('source' in e for e in kbl.validate_meta(missing)))

    def test_fingerprint_stable_and_sensitive(self):
        m1 = {'title': 'Z20 注入工具落点回退', 'platforms': ['Z20'],
              'evidence': [{'cmd': 'adb push x /data/x'}]}
        m2 = dict(m1)
        self.assertEqual(kbl.fingerprint(m1), kbl.fingerprint(m2))
        m3 = dict(m1, title='Z20 注入工具落点回退（另一个说法）')
        self.assertNotEqual(kbl.fingerprint(m1), kbl.fingerprint(m3))


class TestCapture(_KBBase):
    def test_capture_writes_local_layer_only(self):
        r = kbl.capture('注入工具落点回退', body='现象/根因', category='devflow',
                        platforms=['Z20'], source='unit-test')
        self.assertTrue(r['success'], r)
        self.assertEqual(r['layer'], 'local')
        self.assertTrue(r['path'].startswith(os.environ['FLYTHINGS_KB_DIR']))
        self.assertNotIn(BASE.lower(), r['path'].lower().replace('\\', '/') + '/x')  # 不在安装目录
        self.assertTrue(os.path.isfile(r['path']))
        meta, _b, _e = kbl.parse_front_matter(io.open(r['path'], encoding='utf-8').read())
        self.assertEqual(meta['status'], 'draft')
        self.assertTrue(meta['needs_evidence'])
        rows = kbl.read_jsonl(os.path.join(os.environ['FLYTHINGS_KB_DIR'],
                                          'kb_candidates.jsonl'))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], meta['id'])

    def test_capture_dedupes_by_fingerprint(self):
        kbl.capture('同一件事', evidence='[{"kind":"offline","cmd":"adb push a /data/a"}]')
        r2 = kbl.capture('同一件事', evidence='[{"kind":"offline","cmd":"adb push a /data/a"}]')
        self.assertTrue(r2['duplicate'], r2)
        self.assertIn('duplicateOf', r2)
        self.assertIn('合并', r2['hint'])
        self.assertFalse(os.path.isdir(os.path.join(os.environ['FLYTHINGS_KB_DIR'], 'inbox')) and
                         len([f for f in os.listdir(os.path.join(
                             os.environ['FLYTHINGS_KB_DIR'], 'inbox'))]) > 1,
                         '重复条目不许再写一篇')

    def test_capture_project_layer(self):
        proj = os.path.join(self.tmp, 'proj')
        os.makedirs(proj)
        r = kbl.capture('项目专属坑', layer='project', project_root=proj)
        self.assertTrue(r['success'], r)
        self.assertIn(os.path.join('docs', 'kb'), r['path'])
        self.assertEqual(r['layer'], 'project')

    def test_capture_requires_title(self):
        r = kbl.capture('   ')
        self.assertFalse(r['success'])
        self.assertIn('title', r['error'])


class TestNoHitAndGaps(_KBBase):
    def test_no_hit_logged_and_aggregated(self):
        for _ in range(3):
            kbl.log_no_hit('某个查不到的问题', 'no_hit', ['a.md'], 3)
        kbl.log_no_hit('另一个查不到的问题', 'low_confidence')
        g = kbl.gaps(limit=10)
        self.assertEqual(g['totalLogged'], 4)
        self.assertEqual(g['uniqueGaps'], 2)
        self.assertEqual(g['items'][0]['count'], 3)

    def test_gaps_markdown_has_writing_checklist(self):
        kbl.log_no_hit('缺的知识', 'no_hit')
        md = kbl.gaps_markdown(kbl.gaps())
        self.assertIn('知识缺口清单', md)
        self.assertIn('flythings_knowledge_capture', md)


class TestAnonymizeAndExport(_KBBase):
    def test_anonymize_scrubs(self):
        host = 'DESKTOP-' + 'ABCD1234'      # 拆开拼，避免仓库文件里出现真实主机名模式
        raw = ('设备 203.0.113.9:5555 与 198.51.100.7\n'
               '路径 Z:\\builds\\proj 与 /srv/data/app\n'
               'password = hunter2\ntoken: abc123\n主机名 ' + host + '\n'
               '手机 13800001111\n')
        clean, n = kbl.anonymize(raw)
        self.assertGreaterEqual(n, 6)
        for leak in ('203.0.113.9', '198.51.100.7', 'Z:\\builds', '/srv/data',
                     'hunter2', 'abc123', host, '13800001111'):
            self.assertNotIn(leak, clean)

    def test_export_pack_writes_checksum(self):
        kbl.capture('待回流的结论', evidence='[{"kind":"offline","cmd":"echo x"}]')
        r = kbl.export_pack()
        self.assertTrue(r['success'], r)
        self.assertTrue(r['anonymized'])
        self.assertEqual(r['entries'], 1)
        self.assertTrue(os.path.isfile(r['pack']))
        pack = json.load(io.open(r['pack'], encoding='utf-8'))
        self.assertEqual(pack['schema'], kbl.SCHEMA_VERSION)
        self.assertEqual(pack['kind'], 'kb-contrib')
        self.assertTrue(pack.get('checksum'))
        self.assertEqual(pack['entryCount'], 1)

    def test_export_without_entries_errors(self):
        r = kbl.export_pack()
        self.assertFalse(r['success'])
        self.assertIn('没有可导出', r['error'])


class TestKbVerify(_KBBase):
    def _run(self, **kw):
        sys.path.insert(0, os.path.join(BASE, 'scripts'))
        import kb_verify
        return kb_verify

    def test_offline_evidence_pass_and_fail(self):
        kv = self._run()
        doc = {'id': 'x', 'path': '', 'evidence': [
            {'kind': 'offline', 'cmd': 'python -c "print(123)"', 'expect_contains': '123'}]}
        r = kv.verify_entry(doc)
        self.assertEqual(r['status'], 'pass', r)
        bad = {'id': 'x', 'path': '', 'evidence': [
            {'kind': 'offline', 'cmd': 'python -c "print(1)"', 'expect_contains': 'nope'}]}
        r2 = kv.verify_entry(bad)
        self.assertEqual(r2['status'], 'fail', r2)

    def test_manual_evidence_is_not_a_pass(self):
        kv = self._run()
        doc = {'id': 'x', 'path': '', 'evidence': [{'kind': 'manual', 'cmd': '人眼看'}]}
        r = kv.verify_entry(doc)
        self.assertEqual(r['status'], 'manual', r)
        self.assertNotEqual(r['status'], 'pass')

    def test_real_device_without_device_is_explicit_skip(self):
        kv = self._run()
        doc = {'id': 'x', 'path': '', 'evidence': [
            {'kind': 'real-device', 'cmd': 'adb -s %DEVICE% shell echo ok'}]}
        r = kv.verify_entry(doc, device='', allow_device=False)
        self.assertEqual(r['status'], 'skipped', r)
        self.assertIn('--device', r['checks'][0]['detail'])


class TestKbToolsOps(_KBBase):
    def test_capture_op_returns_json_and_local_path(self):
        import kb_tools as k
        r = json.loads(k.flythings_knowledge_capture('AI 现场结论一条',
                                                    evidence='cmd: echo hi'))
        self.assertTrue(r['success'], r)
        self.assertEqual(r['layer'], 'local')
        self.assertTrue(r['path'].startswith(os.environ['FLYTHINGS_KB_DIR']))

    def test_export_op_and_op_names(self):
        import kb_tools as k
        self.assertIn('flythings_knowledge_capture', k.OP_NAMES)
        self.assertIn('flythings_knowledge_export', k.OP_NAMES)
        k.flythings_knowledge_capture('导出用例', evidence='cmd: echo')
        r = json.loads(k.flythings_knowledge_export(scope='inbox'))
        self.assertTrue(r['success'], r)
        self.assertTrue(r['anonymized'])

    def test_search_no_hit_is_logged_for_growth(self):
        import kb_tools as k
        out = json.loads(k.flythings_knowledge_search('zzzqqq 完全无关的胡话 xyzzy', k=3))
        self.assertIn(out['quality'], ('no_hit', 'low_confidence'), out.get('quality'))
        self.assertTrue(out.get('gapLogged'), out)
        self.assertIn('kb_gaps', out.get('gapHint', ''))


if __name__ == '__main__':
    unittest.main(verbosity=2)
