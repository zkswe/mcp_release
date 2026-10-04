# -*- coding: utf-8 -*-
"""契约用例：知识库 P2（时效 freshness/降权、冲突检测、体检看板、缺口 op、backlog/stale 范围）。

**离线**（零真机、零网络）。钉住的是"会不会误导人"：
  · 过期知识必须**带标注**且**被降权**（不许静默当新的用）
  · 同主题一正一反必须**报冲突**（不许两条各说各话）；同篇内的"不要 A，要 B"**不许**误报
  · 体检看板不许滞后（比对 kb_index 源哈希）
  · backlog / stale 范围能真筛出该补判据的条目
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


class TestFreshness(unittest.TestCase):
    def test_age_and_freshness_transitions(self):
        today = kbl.today()
        self.assertEqual(kbl.age_days({'verified_at': today}), 0)
        self.assertEqual(kbl.freshness({'verified_at': today, 'stale_days': 180})[0], 'fresh')
        # 30 天前 + 阈值 30 → 超期
        import datetime
        d30 = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
        f, a = kbl.freshness({'verified_at': d30, 'stale_days': 20})
        self.assertEqual((f, a), ('stale', 30))
        d25 = (datetime.date.today() - datetime.timedelta(days=25)).isoformat()
        self.assertEqual(kbl.freshness({'verified_at': d25, 'stale_days': 30})[0], 'aging')
        self.assertEqual(kbl.freshness({'verified_at': '不是日期'})[0], 'unknown')

    def test_annotate_hits_marks_stale_and_demotes(self):
        import kb_tools as k
        old_cache = k._KB_INDEX_CACHE.copy()
        k._KB_INDEX_CACHE['map'] = {
            'knowledge/a.md': {'status': 'verified', 'evidenceLevel': 'has-evidence',
                               'origin': 'total', 'verified_at': '2026-01-01',
                               'stale': True, 'ageDays': 271, 'staleDays': 90},
            'knowledge/b.md': {'status': 'review', 'evidenceLevel': 'manual-only',
                               'origin': 'total', 'verified_at': kbl.today()},
        }
        try:
            hits = k._annotate_kb_hits([{'path': 'knowledge/a.md'}, {'path': 'knowledge/b.md'},
                                        {'path': 'wiki/x.md'}])
        finally:
            k._KB_INDEX_CACHE.clear()
            k._KB_INDEX_CACHE.update(old_cache)
        self.assertTrue(hits[0].get('stale'))
        self.assertIn('过期', hits[0]['advisory'])
        self.assertIn('review', hits[1]['advisory'])          # 未完全验证也要标
        self.assertIsNone(hits[2].get('advisory'))            # 不在索引里的不猜

    def test_stale_penalty_smaller_than_local_boost(self):
        import kb_tools as k
        self.assertLess(k._STALE_PENALTY, 1.0)
        self.assertGreater(k._LOCAL_BOOST, 1.0)


class TestConflict(unittest.TestCase):
    def _detect(self, docs):
        import kb_conflict as kc
        return kc.detect(docs)

    def test_polarity_conflict_detected_across_docs(self):
        docs = [('knowledge/devflow/a.md', 'Z20 上必须用 setprop 重启应用，不要 kill'),
                ('knowledge/devflow/b.md', 'Z20 上不能用 setprop 重启应用，会黑屏')]
        r = self._detect(docs)
        self.assertGreaterEqual(r['conflictCount'] if 'conflictCount' in r else len(r['polarity']), 1)

    def test_same_doc_pos_neg_is_not_conflict(self):
        docs = [('a.md', '不要连续 restart，要单次 restart 并等新 pid')]
        r = self._detect(docs)
        self.assertEqual(r['polarity'], [])

    def test_duplicate_fingerprint_reported(self):
        fm = ('---\nid: x\nstatus: review\nconfidence: manual\nverified_at: 2026-09-29\n'
              'stale_days: 180\norigin: total\nsource: t\ntags: []\nevidence: []\n---\n# T\n')
        docs = [('a.md', fm), ('b.md', fm.replace('id: x', 'id: y'))]
        r = self._detect(docs)
        self.assertEqual(len(r['duplicate']), 1)


class TestHealthAndScopes(unittest.TestCase):
    def test_health_build_has_all_sections(self):
        import kb_health as kh
        h = kh.build()
        for key in ('generatedAt', 'indexMeta', 'scale', 'evidence', 'freshness', 'quality',
                    'retrieval', 'gaps', 'lastVerify', 'backlog', 'localLayer'):
            self.assertIn(key, h, key)
        md = kh.markdown(h)
        self.assertIn('知识库体检', md)
        self.assertIn('待补判据队列', md)

    def test_health_check_reacts_to_lag(self):
        import kb_health as kh
        jp = os.path.join(kh.REPORT_DIR, 'kb_health.json')
        backup = None
        if os.path.isfile(jp):
            backup = io.open(jp, encoding='utf-8').read()
        try:
            os.makedirs(kh.REPORT_DIR, exist_ok=True)
            with io.open(jp, 'w', encoding='utf-8') as f:
                json.dump({'indexMeta': {'source_hash': 'deadbeef'}}, f)
            import subprocess
            rc = subprocess.run([sys.executable, os.path.join(BASE, 'scripts', 'kb_health.py'),
                                 '--check'], capture_output=True, text=True,
                                encoding='utf-8', errors='replace').returncode
            self.assertEqual(rc, 1, '看板与 kb_index 不一致时必须 FAIL')
        finally:
            if backup is not None:
                with io.open(jp, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(backup)
            else:
                os.remove(jp)

    def test_verify_backlog_scope_lists_queue(self):
        import kb_verify as kv
        payload, _report = kv.run('backlog')
        self.assertEqual(payload['scope'], 'backlog')
        self.assertIn('backlog', payload)
        self.assertGreaterEqual(len(payload['backlog']), 1, '应当有待补判据条目')
        self.assertTrue(all(('hasQueries' in b) for b in payload['backlog']))
        # 无问法的排前面（写作/补证据优先）
        hq = [b['hasQueries'] for b in payload['backlog']]
        self.assertEqual(hq, sorted(hq))

    def test_gaps_op_returns_actions(self):
        import kb_tools as k
        self.assertIn('flythings_knowledge_gaps', k.OP_NAMES)
        old = os.environ.get('FLYTHINGS_KB_DIR')
        tmp = tempfile.mkdtemp(prefix='p2kb_')
        os.environ['FLYTHINGS_KB_DIR'] = tmp
        try:
            kbl.log_no_hit('P2 用例：某个查不到的怪问题', 'no_hit')
            r = json.loads(k.flythings_knowledge_gaps(limit=5))
            self.assertTrue(r['success'], r)
            self.assertGreaterEqual(r['totalLogged'], 1)
            self.assertIn('nextActions', r)
            self.assertTrue(any('capture' in a for a in r['nextActions']))
        finally:
            if old is None:
                os.environ.pop('FLYTHINGS_KB_DIR', None)
            else:
                os.environ['FLYTHINGS_KB_DIR'] = old
            shutil.rmtree(tmp, ignore_errors=True)


class TestIndexFreshnessFields(unittest.TestCase):
    def test_kb_index_docs_carry_freshness(self):
        import gen_kb_index as gki
        idx = gki.build()
        self.assertTrue(idx['docs'], '索引不该为空')
        d = idx['docs'][0]
        for key in ('freshness', 'stale', 'staleDays', 'ageDays', 'evidenceLevel'):
            self.assertIn(key, d, key)
        self.assertIn(idx['docs'][0]['freshness'],
                      ('fresh', 'aging', 'stale', 'unknown'))


class TestIndexCoverageAndEvidence(unittest.TestCase):
    """kb_index 的**覆盖度**与**证据口径**（2026-10-03 修的两处系统性缺口）。

    为什么要有：类别名单原先被手抄在两处（gen_kb_index / kb_frontmatter），新增
    `knowledge/media`、`knowledge/components` 时两边都漏补 —— 那两篇派生页「在磁盘上、
    也在 rag 索引里，却不在 kb_index 里」：拿不到 freshness/advisory 标注、不受 front-matter
    门禁约束。同时 `evidenceLevel` 有两套口径（本文件与 kb_local），只有人工判据的文档
    被算成「带可执行证据」，检索侧据此不再加 advisory。两条都用契约钉住。
    """

    def _disk_docs(self):
        import kb_local as kbl
        import os
        out = set()
        for cat in kbl.categories():
            d = os.path.join(kbl.TOTAL_KB, cat)
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                if f.endswith('.md') and f != 'README.md':
                    out.add('knowledge/%s/%s' % (cat, f))
        return out

    def test_kb_index_covers_every_category_doc(self):
        """磁盘上分类目录里的每篇 .md 都必须进 kb_index（不许再有"漏收一类"）。"""
        import gen_kb_index as gki
        have = {d['path'] for d in gki.build()['docs']}
        missing = sorted(self._disk_docs() - have)
        self.assertEqual(missing, [], '这些文档在磁盘上但不在 kb_index（漏收分类？）：%s'
                         % missing[:5])

    def test_categories_derived_from_disk(self):
        """类别名单必须从磁盘派生 —— knowledge/ 下的每个一级目录（除候选区/报告/日志）都要在内。"""
        import kb_local as kbl
        import os
        disk = {d for d in os.listdir(kbl.TOTAL_KB)
                if os.path.isdir(os.path.join(kbl.TOTAL_KB, d))
                and not d.startswith(('.', '_')) and d not in kbl.KB_SKIP_DIRS}
        self.assertEqual(disk - set(kbl.categories()), set(),
                         '有分类目录没被 categories() 覆盖（名单又被写死了？）')

    def test_evidence_level_matches_kb_local(self):
        """kb_index 的 `evidenceLevel` 必须等于 `kb_local.evidence_level()`（口径只许有一份）。"""
        import io
        import os
        import gen_kb_index as gki
        import kb_local as kbl
        bad = []
        for d in gki.build()['docs']:
            p = os.path.join(BASE, d['path'])
            meta, _b, _e = kbl.parse_front_matter(io.open(p, encoding='utf-8').read())
            if d['evidenceLevel'] != kbl.evidence_level(meta):
                bad.append('%s: %s ≠ %s' % (d['path'], d['evidenceLevel'],
                                            kbl.evidence_level(meta)))
        self.assertEqual(bad, [], 'kb_index 与 kb_local 的证据口径分叉：%s' % bad[:3])

    def test_manual_only_evidence_is_not_has_evidence(self):
        """只有人工判据（无 cmd/artifact）的 evidence **不算** has-evidence。"""
        import kb_local as kbl
        self.assertEqual(kbl.evidence_level({'evidence': [{'kind': 'manual', 'note': 'x'}]}),
                         'manual-only')
        self.assertEqual(kbl.evidence_level({'evidence': [{'cmd': 'echo hi'}]}),
                         'has-evidence')
        self.assertEqual(kbl.evidence_level({'evidence': [{'artifact': 'a.png'}]}),
                         'has-evidence')


if __name__ == '__main__':
    unittest.main(verbosity=2)
