# -*- coding: utf-8 -*-
"""界面产物管线口径的判据（T0.1 / T0.2 / T0.3，REMEDIATION-UI-PIPELINE §WS-0）。

钉住四件事：
  (a) 废止短语黑名单：`唯一手写源` / `单一手写源` / `HTML 是唯一源` / `HTML 是唯一手写源`
      在 `*.md` / `*.py` / `*.json` 里出现即判红（口径见 `knowledge/devflow/ui-pipeline-spec.md`；
      需求方 2026-10-05 拍板：**去掉「HTML 是唯一手写源」**，排他性从输入端移到输出端）。
  (b) 入口登记真源 `ui_entrypoints.json` 的结构完整性（tier/status 取值合法、active 必须有
      `validator_chain` 与 `evidence`、id 不重复）。
  (c) 口径唯一出处 `knowledge/devflow/ui-pipeline-spec.md` 存在且四节标题逐字齐全。
  (d) 派生页不漂移：`python scripts/gen_entrypoints_doc.py --check` rc=0。

**自证（把废止句注回去 → (a) 必须变红）**：`test_selfproof_*` 两条。为什么必须自证：
黑名单最容易的失效方式是"扫描面写错/白名单吃掉一切"——那样它永远绿，等于没有这道闸门。
所以这里把废止句真的写进仓内临时文件，断言扫描器**真的抓得到**，再删掉。

⚠️ 白名单（命中不算）只有四类，且都有理由：
  · `CHANGELOG.md` / `VERSION_HISTORY.md` —— 历史记录，写的是"当年"的说法，不做回溯修正；
  · `REMEDIATION-UI-PIPELINE.md` —— 整改方案本身要引用被废止的旧句（否则说不清改什么）；
  · 本测试文件 —— 黑名单字面量必须写在这里；
  · `tests/` 下的负例 —— 故意构造的命中样例。
另有一条**限时豁免**见 `TIME_BOXED_EXEMPT`：它命中的那份文件不在本任务允许改动的范围内，
登记待改而不是就地改（AGENTS.md「不要删/改他人的业务代码」+ 任务书的改动面约束）。

跑法：`python -m unittest tests.test_ui_pipeline_spec -v`
"""
import io
import json
import os
import re
import subprocess
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
if TESTS not in sys.path:            # 支持 `python -m unittest tests.test_ui_pipeline_spec`
    sys.path.insert(0, TESTS)
import _util as U                    # noqa: E402

BASE = U.BASE
if BASE not in sys.path:
    sys.path.insert(0, BASE)

# ── (a) 废止短语黑名单 ────────────────────────────────────────────────────────
BANNED = ('唯一手写源', '单一手写源', 'HTML 是唯一源', 'HTML 是唯一手写源')

SCAN_EXTS = ('.md', '.py', '.json')
SKIP_DIRS = {'.git', '__pycache__', 'temp', 'models', '_reports', 'node_modules', '.workbuddy'}
# 生成物（内容是别人正文的切片/向量）：它命中只说明**被索引的源**命中了，扫它等于同一件事报两遍。
# 而且改知识页之后它会重生成 —— 扫生成物会产生"改真源也要顺手改索引文件"的假要求。
SKIP_FILES = {
    'rag_index.json': '检索索引（生成物）：正文切片 + 向量，改知识页后由 rebuild_index_local.py 重建',
    'knowledge/kb_index.json': 'kb 机读清单（生成物）：只含 front-matter 字段',
    'tools_manifest.json': '工具面快照（生成物）',
}
WHITELIST_FILES = {
    'CHANGELOG.md': '历史版本记录：写的是当年的说法，不做回溯修正',
    'VERSION_HISTORY.md': '版本史，同上',
    'REMEDIATION-UI-PIPELINE.md': '整改方案本身要引用被废止的旧句（否则说不清改的是什么）',
    os.path.relpath(os.path.abspath(__file__), BASE).replace(os.sep, '/'):
        '本测试文件：黑名单字面量就在下面 BANNED 里',
}
WHITELIST_PREFIX = {'tests/': '负例（故意构造的命中样例）'}
# 限时豁免：本任务**不允许改**这些文件（改动面由任务书钉死），但里面确实有废止句。
# 处置 = 登记 + 指向应改成什么，而不是就地扩大改动面。复查条件：下一次口径收口时清零本表。
TIME_BOXED_EXEMPT = {
    # 当前**为空**：`components/ui_v1/platforms.md` 那处已在 2026-10-05 本批改净（口径改写收尾）。
    # 机制保留：将来确有不许改的文件里带废止句，在这里登记 + 写清「应改成什么」+ 复查条件，不静默。
}


def read_text(path, errors='strict'):
    """读文本（用完即关：`io.open(...).read()` 会留 ResourceWarning，本仓跑 `-W error` 时会变红）。"""
    with io.open(path, encoding='utf-8', errors=errors) as f:
        return f.read()


def scan_banned(root=None, extra_files=None, unreadable=None):
    """→ {相对路径: [(行号, 命中的短语, 该行原文)]}；`extra_files` 可临时追加扫描对象。

    判据 = **把行内空白压成单空格后做子串匹配**（不是正则分词）：
    `HTML 是唯一手写源` 被换行/多空格拆开时仍要抓到（口径句常常跨行排版），
    而 `唯一手写源` 这类直接子串也必须命中。**别在这里"智能"分词** —— 分词会把
    `…唯一手写源。其余由脚本生成` 这类带后接标点的命中吃掉（首版就踩过：
    按标点切词后 `components/ui_v1/platforms.md` 那行被切成两段，黑名单静默漏报）。

    ⚠️ **不静默**（DESIGN_SPEC 第 3 条）：读不了的文件**不吞** —— 传 `unreadable` 列表进来，
    本函数把 `'相对路径（原因）'` 追加进去，由调用方断言/打印。吞掉它等于
    「扫不到」被当成「没问题」（`scripts/check_consistency.py` 的 referenced-files 检查、
    `error_codes_loader.scan_source(unreadable=...)` 都是这个口径）。
    """
    root = root or BASE
    hits = {}
    targets = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(SCAN_EXTS):
                targets.append(os.path.join(dirpath, fn))
    targets.extend(extra_files or [])
    for path in targets:
        rel = os.path.relpath(path, root).replace(os.sep, '/')
        if rel in SKIP_FILES or rel in WHITELIST_FILES or any(rel.startswith(p) for p in WHITELIST_PREFIX):
            continue
        try:
            text = read_text(path, errors='replace')
        except OSError as e:                       # 读不了 → 记下来，由调用方断言（不静默跳过）
            if unreadable is not None:
                unreadable.append('%s（%s）' % (rel, e.strerror or type(e).__name__))
            continue
        for i, line in enumerate(text.split('\n'), 1):
            flat = re.sub(r'\s+', ' ', line)
            for phrase in BANNED:
                if phrase in flat:
                    hits.setdefault(rel, []).append((i, phrase, line.strip()[:110]))
    return hits


_SCAN_CACHE = {}


def scan_banned_cached():
    """跑一次全仓扫描并在用例间复用 → `(hits, unreadable)`。

    为什么要缓存：本模块多个用例都要看同一份扫描结果（命中、(a) 的"读不了"清单）。
    各跑一遍全仓 walk 会让"读不了的清单"在某个用例里被漏报，也白烧 I/O。
    """
    if 'r' not in _SCAN_CACHE:
        unreadable = []
        _SCAN_CACHE['r'] = (scan_banned(unreadable=unreadable), unreadable)
    return _SCAN_CACHE['r']


class TestBannedPhrases(unittest.TestCase):
    """(a) 全仓扫废止短语：命中即红（白名单见模块 docstring）。"""

    def test_no_deprecated_claim_anywhere(self):
        hits, unreadable = scan_banned_cached()
        # 限时豁免的文件单独摘出来：它们**仍然是命中**，只是本任务改不了 → 报告里如实列出。
        exempt = {k: v for k, v in hits.items() if k in TIME_BOXED_EXEMPT}
        real = {k: v for k, v in hits.items() if k not in TIME_BOXED_EXEMPT}
        self.assertEqual(real, {}, '出现废止短语（口径见 knowledge/devflow/ui-pipeline-spec.md）：\n'
                         + '\n'.join('  %s:%d  %s' % (f, ln, t) for f, rows in sorted(real.items())
                                     for ln, _p, t in rows))
        if exempt:
            # 不静默（DESIGN_SPEC 第 3 条）：豁免要**打印出来**，且豁免表本身必须写清改法
            sys.stderr.write('[note] 限时豁免 %d 个文件仍含废止短语（见 TIME_BOXED_EXEMPT）：%s\n'
                             % (len(exempt), ', '.join(sorted(exempt))))

    def test_unreadable_files_reported_not_swallowed(self):
        """**读不了的文件也要判红**：否则"扫不到"会被当成"没问题"（不静默口径）。"""
        _hits, unreadable = scan_banned_cached()
        self.assertEqual(unreadable, [], '扫描器读不了这些文件（没扫到 ≠ 没问题）：%s'
                         % '；'.join(unreadable))

    def test_whitelist_entries_all_have_reasons(self):
        for f, why in list(WHITELIST_FILES.items()) + list(WHITELIST_PREFIX.items()) \
                + list(TIME_BOXED_EXEMPT.items()):
            self.assertTrue(str(why).strip(), '白名单 %s 必须写理由' % f)

    def test_selfproof_injected_phrase_turns_red(self):
        """**自证**：把废止句注回一个仓内文档 → (a) 必须变红；删掉 → 必须转绿。

        做法：临时负例文件不能建在 `tests/` 下（`tests/` 前缀在白名单里 → 证明不了什么），
        所以建在**仓根**（`_banned_selfproof_<pid>.md`），扫完立即删。
        注意：这条用**不缓存**的 `scan_banned()` —— 缓存会把注入的临时文件缓存进去，
        后面的用例就会看到一个已经被删掉的文件。
        """
        probe = os.path.join(BASE, '_banned_selfproof_%d.md' % os.getpid())
        try:
            U.write(probe, '# 自证样例\n\n本项目 HTML 是唯一手写源，其余由脚本生成。\n')
            self.assertIn(os.path.basename(probe), scan_banned(),
                          '注回废止句后扫描器没抓到 → 黑名单失效（这道闸门等于没有）')
        finally:
            if os.path.isfile(probe):
                os.remove(probe)
        self.assertNotIn(os.path.basename(probe), scan_banned(), '自证文件没删干净')

    def test_selfproof_green_when_no_injection(self):
        """自证的另一半：仓内**当前**不含废止句（除了登记在案的限时豁免）→ 绿。"""
        hits, unreadable = scan_banned_cached()
        self.assertEqual(unreadable, [], '扫描器读不了这些文件：%s' % '；'.join(unreadable))
        real = {k: v for k, v in hits.items() if k not in TIME_BOXED_EXEMPT}
        self.assertEqual(sorted(real), [])


class TestEntrypointRegistry(unittest.TestCase):
    """(b) `ui_entrypoints.json` 结构完整性（入口登记唯一真源）。"""

    @classmethod
    def setUpClass(cls):
        cls.path = os.path.join(BASE, 'ui_entrypoints.json')
        with io.open(cls.path, encoding='utf-8') as f:
            cls.data = json.load(f)

    def test_file_and_top_level_fields(self):
        for k in ('schema', 'version', 'updated', 'authority', 'tiers', 'entrypoints'):
            self.assertIn(k, self.data, '真源缺顶层字段 %s' % k)
        self.assertTrue(str(self.data['authority']).strip(), 'authority 不许空（要一句话说清它是谁的真源）')
        for t in ('default', 'allowed', 'migration'):
            self.assertTrue(str((self.data['tiers'] or {}).get(t) or '').strip(),
                            'tiers 缺 %s 的约束说明' % t)

    def test_ids_unique_and_required_keys(self):
        seen = set()
        for e in self.data['entrypoints']:
            for k in ('id', 'name', 'kind', 'status', 'language', 'tier', 'ops',
                      'validator_chain', 'evidence', 'limits'):
                self.assertIn(k, e, '入口 %s 缺字段 %s' % (e.get('id'), k))
            self.assertNotIn(e['id'], seen, '入口 id 重复：%s' % e['id'])
            seen.add(e['id'])
            self.assertIn(e['kind'], ('authoring', 'migration'), '%s 的 kind 非法' % e['id'])

    def test_tier_and_status_domains(self):
        for e in self.data['entrypoints']:
            self.assertIn(e['tier'], ('default', 'allowed', 'migration'),
                          '%s 的 tier=%r 不在 {default,allowed,migration}' % (e['id'], e['tier']))
            self.assertIn(e['status'], ('active', 'planned', 'unsupported'),
                          '%s 的 status=%r 不在 {active,planned,unsupported}' % (e['id'], e['status']))

    def test_active_entries_have_chain_and_evidence(self):
        active = [e for e in self.data['entrypoints'] if e['status'] == 'active']
        self.assertTrue(active, '至少要有一个 active 入口（否则这张表没意义）')
        for e in active:
            self.assertTrue(e['validator_chain'], '%s 是 active 但没有 validator_chain' % e['id'])
            ev = e['evidence'] or {}
            self.assertTrue(any(ev.get(k) for k in ('tests', 'artifacts', 'on_device')),
                            '%s 是 active 但没有 evidence（用例/产物/真机至少一项）' % e['id'])

    def test_declared_paths_exist(self):
        """登记的证据/产物路径必须真实存在（指向不存在的东西 = 假证据）。"""
        for e in self.data['entrypoints']:
            ev = e['evidence'] or {}
            for p in (ev.get('tests') or []) + (ev.get('artifacts') or []):
                self.assertTrue(os.path.exists(os.path.join(BASE, p.replace('/', os.sep))),
                                '%s 登记的路径不存在：%s' % (e['id'], p))

    def test_required_entrypoints_registered(self):
        """任务书点名的入口一个都不能少，且未实现的按现状如实标 planned。"""
        want = {
            'html-prototype': 'active', 'ui-blocks-spec': 'active',
            'ui-json-schema-first': 'active', 'lvgl-c': 'active', 'figma-html': 'active',
            'qt-ui': 'planned', 'qml': 'planned', 'android-xml': 'planned',
            'miniprogram-wxml': 'planned', 'vue': 'planned',
        }
        got = {e['id']: e['status'] for e in self.data['entrypoints']}
        for eid, status in want.items():
            self.assertIn(eid, got, '入口登记表缺 %s' % eid)
            self.assertEqual(got[eid], status, '%s 的状态与现状不符（应为 %s）' % (eid, status))
        for eid in ('qml', 'vue', 'qt-ui', 'android-xml', 'miniprogram-wxml'):
            entry = next(e for e in self.data['entrypoints'] if e['id'] == eid)
            limits = ' '.join(entry['limits'] or [])
            self.assertIn('flythings_map_control', limits,
                          '%s 必须写明"当前只能逐控件走 flythings_map_control + 手工搭 json"' % eid)


class TestSpecPageAndDerivedDoc(unittest.TestCase):
    """(c) 口径唯一出处存在且四节逐字齐全；(d) 派生页不漂移。"""

    SPEC = os.path.join(BASE, 'knowledge', 'devflow', 'ui-pipeline-spec.md')
    DERIVED = os.path.join(BASE, 'knowledge', 'devflow', 'ui-entrypoints.md')
    SECTIONS = ('## 1. 三档判据', '## 2. 入口分级', '## 3. 模块 I/O 契约', '## 4. 差异归因三分')

    def test_spec_page_has_four_sections_verbatim(self):
        self.assertTrue(os.path.isfile(self.SPEC), '缺口径唯一出处 knowledge/devflow/ui-pipeline-spec.md')
        text = read_text(self.SPEC)
        for h in self.SECTIONS:
            self.assertIn('\n%s\n' % h, text.replace('\r\n', '\n'),
                          '规范页缺四节之一（标题要逐字）：%s' % h)

    def test_spec_page_states_the_authoritative_wording(self):
        """口径本身（唯一产物规范 / 唯一事实源 / 入口不排他 / ui_compile）必须写在规范页里。"""
        text = read_text(self.SPEC)
        for frag in ('`ui_schema.json` 是唯一产物规范', '`ui/*.json` 是唯一事实源',
                     '手写入口不排他', '编译式验收', 'ui_compile',
                     '`DESIGN_SPEC.md` 第 1.1 条', '第 1.2 条', '⛔EXCUSE', '⛔TWEAK',
                     '只能按规格改，不能按结果改'):
            self.assertIn(frag, text, '规范页缺关键表述：%s' % frag)

    def test_spec_page_front_matter_compliant(self):
        import kb_local as kbl
        meta, _body, ferr = kbl.parse_front_matter(read_text(self.SPEC))
        self.assertEqual(ferr, '', 'front-matter 解析出错：%s' % ferr)
        self.assertEqual(meta.get('id'), 'devflow-ui-pipeline-spec')
        self.assertEqual(meta.get('verified_at'), '2026-10-05')
        self.assertTrue(meta.get('needs_evidence'))
        self.assertEqual(kbl.validate_meta(meta, 'knowledge/devflow/ui-pipeline-spec.md'), [])

    def test_derived_doc_declares_source_of_truth(self):
        self.assertTrue(os.path.isfile(self.DERIVED))
        text = read_text(self.DERIVED)
        self.assertIn('真源 = `ui_entrypoints.json`', text,
                      '派生页必须写明真源（否则读者会手改它）')
        self.assertIn('id: devflow-ui-entrypoints', text)

    def test_derived_doc_not_drifted(self):
        p = subprocess.run([sys.executable, os.path.join(BASE, 'scripts', 'gen_entrypoints_doc.py'),
                            '--check'], capture_output=True, cwd=BASE, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout.decode('utf-8', 'replace')
                         + p.stderr.decode('utf-8', 'replace'))


class TestPointerPagesReferenceTheSpec(unittest.TestCase):
    """改口径的四个知识页必须**指向**规范页（不指向就不算"改为引用"）。"""

    POINTERS = {
        'knowledge/devflow/platform-translate.md': 'ui-pipeline-spec.md',
        'knowledge/devflow/ftu-json-pipeline.md': 'ui-pipeline-spec.md',
        'knowledge/devflow/ui-layout-verify.md': 'ui-pipeline-spec.md',
        'knowledge/devflow/prototype-flow.md': 'ui-pipeline-spec.md',
    }

    def test_each_pointer_page_links_spec(self):
        for rel, needle in self.POINTERS.items():
            text = read_text(os.path.join(BASE, rel.replace('/', os.sep)))
            self.assertIn(needle, text, '%s 未指向口径规范页（%s）' % (rel, needle))


if __name__ == '__main__':
    unittest.main()
