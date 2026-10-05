# -*- coding: utf-8 -*-
"""`json2img` 的**覆盖矩阵**（T2.1）：矩阵必须与 `renderContract` 逐行对账，且**缺/多/非法即判红**。

为什么单独钉一组（2026-10-05 需求方口径）：
> 「现在离线可以用 json2img 来判定。这个可以作为判定依据，如果后期有差异我们来完善 json2img。
>   各个功能模块各司其职，各自保证输入输出正确完整并且有标准。」

`json2img` 是**无设备时唯一的视觉验收手段**，所以"它能判什么、哪些只是近似、哪些根本没覆盖"
必须是**数据**而不是口碑：行集合的唯一真源是 `ui_schema.json#renderContract.rows`（10 条），
实现状态住在 `ui_tools/json2img_coverage.json`，两边由 `--coverage --check` 对账。

本文件钉三件事：
  ① 忠实：矩阵每条都能落到真源的行上（id 恰好一次），且状态取值合法、blindSpot 必带说明、
     evidence 指向的文件真的存在；
  ② 可判红（**自证**）：把某条 id 删掉 / status 改成非法值 / blindSpot 不带 note /
     evidence 写个不存在的文件 / 多出一条真源没有的 id → `--coverage --check` **必须红**（rc=1）；
  ③ 假绿防线：`--coverage`（不带 --check）不许判红、也不许静默——它要明确说"校验有几处问题、
     加 --check 才判红"。
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import _util as U

sys.path.insert(0, U.BASE)
sys.path.insert(0, os.path.join(U.BASE, 'ui_tools'))
import json2img as J  # noqa: E402

CLI = os.path.join(U.BASE, 'ui_tools', 'json2img.py')
MATRIX = os.path.join(U.BASE, 'ui_tools', 'json2img_coverage.json')
SCHEMA = os.path.join(U.BASE, 'ui_tools', 'ui_schema.json')
ALLOW = os.path.join(U.BASE, 'ui_tools', 'json2img_blindspot_allow.json')


def run_cli(*args):
    """子进程跑**真 CLI**（退出码 + 输出全文）——判据要在调用方能看到的那一层成立。"""
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    p = subprocess.run([sys.executable, CLI] + list(args), capture_output=True, text=True,
                       encoding='utf-8', errors='replace', env=env)
    return p.returncode, (p.stdout or '') + (p.stderr or '')


def load_matrix():
    with io.open(MATRIX, encoding='utf-8') as f:
        return json.load(f)


class MatrixFixture(unittest.TestCase):
    """临时目录里放**改过的矩阵副本**（绝不动仓里的数据文件）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='mcp_test_')
        self.doc = load_matrix()
        self.contract = J.load_contract_rows()

    def tearDown(self):
        U.cleanup(self.tmp)

    def matrix(self, mutate=None):
        """把矩阵写进临时目录（可先按 mutate(doc) 改）→ 返回路径。"""
        doc = json.loads(json.dumps(self.doc))          # 深拷贝
        if mutate:
            mutate(doc)
        p = os.path.join(self.tmp, 'matrix.json')
        with io.open(p, 'w', encoding='utf-8') as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        return p

    def row(self, doc, rid):
        for r in doc['rows']:
            if r.get('id') == rid:
                return r
        raise AssertionError('矩阵里没有 %s' % rid)


class TestMatrixIsFaithful(MatrixFixture):
    """① 忠实：矩阵 ⊇/== 真源的行，且每条都有说明与依据。"""

    def test_contract_rows_come_from_the_schema(self):
        """行集合的唯一真源 = `ui_schema.json#renderContract.rows`（不在别处重抄）。"""
        with io.open(SCHEMA, encoding='utf-8') as f:
            schema = json.load(f)
        want = [r['id'] for r in (schema.get('renderContract') or {}).get('rows') or []]
        self.assertEqual([r['id'] for r in self.contract], want,
                         'json2img 读到的行集合必须**逐条等于**注册表的 renderContract.rows')
        self.assertEqual(len(want), len(set(want)), '真源 id 不许重复')
        self.assertGreaterEqual(len(want), 8, '保真契约不该只有零星几条')

    def test_shipped_matrix_passes_check(self):
        """仓里的矩阵数据本身通过（否则任何人都没法用它当判据）。"""
        fails = J.check_coverage(MATRIX, SCHEMA, ALLOW)
        self.assertEqual(fails, [], '仓里的覆盖矩阵没通过 --check：\n  ' + '\n  '.join(fails))

    def test_every_row_has_status_note_and_evidence(self):
        for r in self.doc['rows']:
            self.assertIn(r['status'], J.STATUS_VALUES, r['id'])
            self.assertTrue(str(r.get('note') or '').strip(), '%s 缺 note' % r['id'])
            self.assertIsInstance(r.get('blindSpot'), bool, '%s 缺 blindSpot' % r['id'])
            ev = r.get('evidence') or {}
            self.assertIsInstance(ev.get('tests'), list, '%s evidence.tests' % r['id'])
            self.assertIsInstance(ev.get('device'), list, '%s evidence.device' % r['id'])

    def test_blindspot_rows_say_why(self):
        """`blindSpot: true` = 离线渲染判不了它 → 必须写清哪里没被覆盖。"""
        blind = [r for r in self.doc['rows'] if r.get('blindSpot') is True]
        self.assertTrue(blind, '至少有一条真盲区（stroke-aa / family-consistency 这类出图侧/集合性质）'
                               '—— 一条都没有说明矩阵在自吹')
        for r in blind:
            self.assertTrue(str(r.get('note') or '').strip(),
                            '%s：blindSpot=true 必须带非空 note' % r['id'])

    def test_evidence_tests_point_to_real_files(self):
        """evidence 里写出来的用例文件必须真的在（不许写理想中的文件名）。"""
        n = 0
        for r in self.doc['rows']:
            for t in (r.get('evidence') or {}).get('tests') or []:
                p = os.path.join(U.BASE, t.replace('/', os.sep))
                self.assertTrue(os.path.isfile(p), '%s 的 evidence.tests 指向不存在的文件：%s'
                                % (r['id'], t))
                n += 1
        self.assertGreater(n, 0, '一条 evidence 都没有 = 状态没有依据')

    def test_matrix_is_not_a_second_source_of_truth(self):
        """矩阵**只填状态**：不许自带一份"行清单真源"（那会变成第二份真相）。"""
        for key in ('ids', 'contract_rows', 'renderContract'):
            self.assertNotIn(key, self.doc,
                             '矩阵里出现了 %r —— 行集合真源只有 ui_schema.json 一处' % key)
        rc, out = run_cli('--coverage', '--check')
        self.assertEqual(rc, 0, out[-800:])
        self.assertIn('ui_schema.json#renderContract.rows', out,
                      '人读输出要写明"行集合的真源是哪一份"，否则矩阵会被当成真源')


class TestCoverageCli(MatrixFixture):
    """`--coverage`（人读矩阵）/ `--coverage --check`（判红）两条出口。"""

    def test_coverage_without_check_prints_all_rows_and_passes(self):
        rc, out = run_cli('--coverage')
        self.assertEqual(rc, 0, '--coverage 不带 --check 时不该判红：\n' + out[-800:])
        for r in self.contract:
            self.assertIn(r['id'], out, '人读矩阵缺行 %s' % r['id'])
        self.assertIn('implemented', out)
        self.assertIn('approximate', out)
        self.assertIn('unsupported', out)
        self.assertIn('统计：', out, '要给出状态分布（各几 implemented/approximate/unsupported）')

    def test_coverage_check_passes_on_shipped_data(self):
        rc, out = run_cli('--coverage', '--check')
        self.assertEqual(rc, 0, out[-800:])
        self.assertIn('[PASS]', out)

    def test_check_without_coverage_still_works(self):
        """`--check` 单独给也要判（等价于 --coverage --check），不留半开的开关。"""
        rc, out = run_cli('--check')
        self.assertEqual(rc, 0, out[-800:])
        self.assertIn('[PASS]', out)

    def test_coverage_json_is_machine_readable(self):
        """`--coverage-json`：机读产物要能落到**真源的行**上（10 行、逐条带状态与 note）。"""
        out_p = os.path.join(self.tmp, 'cov.json')
        rc, out = run_cli('--coverage', '--check', '--coverage-json', out_p)
        self.assertEqual(rc, 0, out[-800:])
        with io.open(out_p, encoding='utf-8') as f:
            d = json.load(f)
        self.assertEqual([r['id'] for r in d['coverage']],
                         [r['id'] for r in self.contract], '机读覆盖表必须逐条等于真源行序')
        for r in d['coverage']:
            self.assertIn(r['status'], J.STATUS_VALUES)
            self.assertTrue(str(r.get('note') or '').strip())
        self.assertTrue(d['check']['ok'], '机读产物要带上校验结论')
        self.assertEqual(d['check']['failures'], [])


class TestCheckIsRed(MatrixFixture):
    """② **自证**：把错法注回去，`--coverage --check` 必须红（否则判据是装饰）。"""

    def test_missing_row_is_red(self):
        """删掉一条 id → rc=1 且指名道姓说缺哪条。"""
        gone = self.contract[2]['id']
        p = self.matrix(lambda d: d['rows'].pop(2))
        rc, out = run_cli('--coverage', '--check', '--coverage-matrix', p)
        self.assertEqual(rc, 1, '删掉 %s 后仍判过：\n%s' % (gone, out[-800:]))
        self.assertIn('[FAIL]', out)
        self.assertIn(gone, out, '失败信息要点名是哪条 id')
        # 同一结论在 API 层也成立（便于失败定位）
        fails = J.check_coverage(p, SCHEMA, ALLOW)
        self.assertTrue(any('缺 renderContract 行' in f and gone in f for f in fails), fails)

    def test_illegal_status_is_red(self):
        """status 改成非法值 → rc=1 且点名。"""
        rid = self.contract[0]['id']
        p = self.matrix(lambda d: self.row(d, rid).update({'status': 'probably'}))
        rc, out = run_cli('--coverage', '--check', '--coverage-matrix', p)
        self.assertEqual(rc, 1, '非法 status 没判红：\n' + out[-800:])
        self.assertIn(rid, out)
        fails = J.check_coverage(p, SCHEMA, ALLOW)
        self.assertTrue(any('status' in f and rid in f for f in fails), fails)

    def test_duplicate_row_is_red(self):
        """同一条 id 出现两次（"多"的一半）→ rc=1。"""
        rid = self.contract[1]['id']
        p = self.matrix(lambda d: d['rows'].append(dict(self.row(d, rid))))
        rc, out = run_cli('--coverage', '--check', '--coverage-matrix', p)
        self.assertEqual(rc, 1, out[-800:])
        self.assertIn('重复', out)

    def test_unknown_id_is_red(self):
        """矩阵里多出一条真源没有的 id → rc=1（防"矩阵自己长行"）。"""
        p = self.matrix(lambda d: d['rows'].append(
            {'id': 'not-a-contract-row', 'status': 'implemented', 'note': '凭空多出来的一条',
             'evidence': {'tests': [], 'device': []}, 'blindSpot': False}))
        rc, out = run_cli('--coverage', '--check', '--coverage-matrix', p)
        self.assertEqual(rc, 1, out[-800:])
        self.assertIn('not-a-contract-row', out)

    def test_blindspot_without_note_is_red(self):
        rid = self.contract[0]['id']
        p = self.matrix(lambda d: self.row(d, rid).update({'blindSpot': True, 'note': ''}))
        rc, out = run_cli('--coverage', '--check', '--coverage-matrix', p)
        self.assertEqual(rc, 1, 'blindSpot=true 却不写 note 也放过了：\n' + out[-800:])
        self.assertIn(rid, out)

    def test_missing_evidence_file_is_red(self):
        """evidence 指向不存在的文件 → rc=1（不许拿理想文件名充当证据）。"""
        rid = self.contract[0]['id']
        p = self.matrix(lambda d: self.row(d, rid).update(
            {'evidence': {'tests': ['tests/test_no_such_thing_xyz.py'], 'device': []}}))
        rc, out = run_cli('--coverage', '--check', '--coverage-matrix', p)
        self.assertEqual(rc, 1, out[-800:])
        self.assertIn('test_no_such_thing_xyz.py', out)

    def test_unreadable_matrix_is_red_not_crash(self):
        """矩阵文件不存在 → 退出码 1 + 说清原因（不是 traceback）。"""
        rc, out = run_cli('--coverage', '--check', '--coverage-matrix',
                          os.path.join(self.tmp, 'nope.json'))
        self.assertEqual(rc, 1, out[-800:])
        self.assertNotIn('Traceback', out, '读不到要判红并说原因，不该抛栈')


class JudgeFixture(unittest.TestCase):
    """判定模式（T2.2）的夹具：一页用了**渲染器没覆盖的字段**（`textview.rollEnable`）的 json。

    为什么挑 `rollEnable`：滚动文字在静止态渲染里只画首屏，渲染器会走
    `Report.unsupported('textview', caption, 'rollEnable', …)` —— 这是"没有渲染器覆盖"的典型，
    而且它**不影响画面结构**，所以判定模式若把它放过，就等于"没覆盖也算通过"。
    """

    PAGE = {
        # 颜色写正数只是省事；语义上 `-1` 才是不填充、其它负数按 0xAARRGGBB
        # （2026-10-05 修，见 tests/test_json2img_color_semantics.py）
        'resolution': {'width': 240, 'height': 120},
        'position': {'left': 0, 'top': 0, 'width': 240, 'height': 120},
        'backgroundColor': 0x101418,
        'textview__1': {'text': 'hello', 'fontSize': 16, 'alignment': 36,
                        'colorTab': {'color0': 0xFFFFFF}, 'rollEnable': True,
                        'position': {'left': 8, 'top': 8, 'width': 120, 'height': 24}},
    }

    def setUp(self):
        self.tmp = U.project()
        self.jp = os.path.join(self.tmp, 'ui', 'main.json')
        with io.open(self.jp, 'w', encoding='utf-8') as f:
            json.dump(self.PAGE, f, ensure_ascii=False)

    def tearDown(self):
        U.cleanup(self.tmp)

    def allow_file(self, entries, name='allow.json'):
        p = os.path.join(self.tmp, name)
        with io.open(p, 'w', encoding='utf-8') as f:
            json.dump({'entries': entries}, f, ensure_ascii=False)
        return p

    def run_page(self, *args):
        return run_cli(self.tmp, '--out', os.path.join(self.tmp, 'out.png'), *args)

    @staticmethod
    def blindspots(out):
        """从判定报告里解析未豁免盲区 → [(page, type, caption, field)]。"""
        rows = []
        for ln in out.splitlines():
            s = ln.strip()
            if not s or not s[0].isdigit() or 'page=' not in s:
                continue
            kv = dict(part.split('=', 1) for part in s.split('. ', 1)[1].split() if '=' in part)
            rows.append((kv.get('page'), kv.get('type'), kv.get('caption'), kv.get('field')))
        return rows


class TestJudgeMode(JudgeFixture):
    """T2.2：判定模式下**未豁免的盲区判红**；登记豁免后放行；不开 --judge 一切照旧。"""

    def test_judge_is_off_by_default(self):
        """③ 不加 --judge：rc 不受盲区影响（默认行为不变），但**记账照旧**（不静默）。"""
        rc, out = self.run_page()
        self.assertEqual(rc, 0, '默认调用被盲区影响了：\n' + out[-800:])
        self.assertNotIn('[判定模式 --judge]', out, '默认不该进判定模式')
        self.assertIn('[unsupported/降级]', out, '默认仍要如实打出 unsupported 清单')
        self.assertIn('rollEnable', out, '用了没覆盖的字段必须记账')

    def test_uncovered_field_makes_judge_red(self):
        """① 用了未覆盖字段 → `--judge` rc=1，且报告逐条给 page/type/caption/field/note。"""
        rc, out = self.run_page('--judge')
        self.assertEqual(rc, 1, '有未豁免盲区却判过了：\n' + out[-800:])
        self.assertIn('[FAIL]', out)
        spots = self.blindspots(out)
        self.assertTrue(spots, '报告里没有逐条列出盲区：\n' + out[-800:])
        tv = [s for s in spots if s[1] == 'textview' and s[3] == 'rollEnable']
        self.assertTrue(tv, 'textview.rollEnable 没被列为盲区：%r' % (spots,))
        self.assertEqual(tv[0][0], 'main', '盲区要带 page')
        self.assertIn('note x', out, '盲区要带 note（说清"这块没被渲染器覆盖"）')
        self.assertIn('判定不算通过', out)
        self.assertIn('已豁免 0 条', out, '豁免数要显式打出来（不静默）')

    def test_registered_field_is_exempt_and_passes(self):
        """② 把报告里那些盲区登记进白名单 → 同输入 rc=0，且输出注明豁免（带理由）。"""
        rc1, out1 = self.run_page('--judge')
        self.assertEqual(rc1, 1, out1[-800:])
        entries = []
        for _page, ctype, caption, field in self.blindspots(out1):
            e = {'type': ctype, 'field': field, 'allow': True,
                 'reason': '用例登记：%s.%s 属静止态口径/环境差异，本次判定接受'
                           '（理由必须写清才能豁免）' % (ctype, field)}
            if caption and caption != '(无':
                e['caption'] = caption
            entries.append(e)
        p = self.allow_file(entries)
        rc2, out2 = self.run_page('--judge', '--blindspot-allow', p)
        self.assertEqual(rc2, 0, '登记豁免后仍判红：\n' + out2[-1200:])
        self.assertIn('[PASS]', out2)
        self.assertIn('已豁免 %d 条' % len(entries), out2)
        self.assertIn('rollEnable', out2, '被豁免的字段要出现在输出里')
        self.assertIn('用例登记', out2, '豁免要连**理由**一起打出来（不静默）')

    def test_partial_exemption_is_still_red(self):
        """豁免是**逐条精确**的：只登记一条，另一条盲区照样判红。"""
        rc1, out1 = self.run_page('--judge')
        spots = self.blindspots(out1)
        self.assertGreaterEqual(len(spots), 2,
                                '夹具应至少有两个盲区（textview.rollEnable + 字体兜底），实测 %r'
                                % (spots,))
        others = [s for s in spots if not (s[1] == 'textview' and s[3] == 'rollEnable')]
        self.assertTrue(others, '夹具里应有 rollEnable 之外的盲区，实测 %r' % (spots,))
        p = self.allow_file([{'type': 'textview', 'field': 'rollEnable', 'allow': True,
                              'reason': '只登记这一条，用于验证豁免是精确匹配'}])
        rc2, out2 = self.run_page('--judge', '--blindspot-allow', p)
        self.assertEqual(rc2, 1, '只登记一条就把其它盲区一起放过了：\n' + out2[-1200:])
        self.assertIn('已豁免 1 条', out2)
        left = self.blindspots(out2)
        self.assertTrue(left, '剩下的盲区要照旧列出来')
        self.assertFalse([s for s in left if s[1] == 'textview' and s[3] == 'rollEnable'],
                         '已登记的字段不该再算盲区')

    def test_missing_allow_file_is_not_silent(self):
        """白名单文件不在 → 仍要判（视为 0 条豁免），并把"文件不存在"打出来。"""
        rc, out = self.run_page('--judge', '--blindspot-allow',
                                os.path.join(self.tmp, 'no-such-allow.json'))
        self.assertEqual(rc, 1, out[-800:])
        self.assertIn('文件不存在', out)
        self.assertIn('0 条豁免', out)

    def test_judge_report_is_machine_readable(self):
        """`--coverage-json` 里判定结果要能机读（盲区逐条带 page/type/caption/field/note）。"""
        out_p = os.path.join(self.tmp, 'judge.json')
        rc, out = self.run_page('--judge', '--coverage-json', out_p)
        self.assertEqual(rc, 1, out[-800:])
        with io.open(out_p, encoding='utf-8') as f:
            d = json.load(f)
        self.assertTrue(d['judge']['ran'])
        self.assertEqual(d['judge']['unexemptedCount'], len(d['judge']['blindSpots']))
        self.assertGreater(d['judge']['unexemptedCount'], 0)
        for b in d['judge']['blindSpots']:
            for k in ('page', 'type', 'caption', 'field', 'note'):
                self.assertIn(k, b, '机读盲区条目缺 %s：%r' % (k, b))
        self.assertEqual([r['id'] for r in d['coverage']],
                         [r['id'] for r in J.load_contract_rows()],
                         '带 --coverage-json 时也要给出与真源逐条对齐的覆盖表')


class TestBlindspotAllowShape(MatrixFixture):
    """③ 豁免登记表的结构也是判据（`reason` 必填；结构坏了不能悄悄放行）。"""
    def test_shipped_allow_is_valid(self):
        entries, fails = J.load_blindspot_allow(ALLOW)
        self.assertEqual(fails, [], '仓里的豁免登记表不合法：\n  ' + '\n  '.join(fails))
        self.assertIsInstance(entries, list)
        for e in entries:
            self.assertTrue(str(e.get('reason') or '').strip(), '豁免必须写理由：%r' % (e,))

    def test_entry_without_reason_is_red(self):
        p = os.path.join(self.tmp, 'allow.json')
        with io.open(p, 'w', encoding='utf-8') as f:
            json.dump({'entries': [{'type': 'textview', 'field': 'rollEnable', 'allow': True,
                                    'reason': ''}]}, f, ensure_ascii=False)
        rc, out = run_cli('--coverage', '--check', '--blindspot-allow', p)
        self.assertEqual(rc, 1, '不写理由的豁免被放过：\n' + out[-800:])
        self.assertIn('reason', out)

    def test_entry_without_allow_flag_is_red(self):
        p = os.path.join(self.tmp, 'allow2.json')
        with io.open(p, 'w', encoding='utf-8') as f:
            json.dump({'entries': [{'type': 'textview', 'field': 'rollEnable',
                                    'reason': '只说理由但没表态 allow'}]}, f, ensure_ascii=False)
        rc, out = run_cli('--coverage', '--check', '--blindspot-allow', p)
        self.assertEqual(rc, 1, out[-800:])
        self.assertIn('allow', out)

    def test_bom_file_is_still_readable(self):
        """Windows 上手写这个文件会带 BOM（记事本 / `Set-Content -Encoding utf8`）→ 必须照读。

        为什么钉：豁免登记是**人**的动作，编码细节把人挡在门外就会逼人绕过判据；
        实测（2026-10-05）PowerShell 生成的 BOM 文件在 `encoding='utf-8'` 下报
        "Unexpected UTF-8 BOM"，于是"我明明登记了"却判红。
        """
        for name, payload in (('matrix_bom.json', self.doc), ('allow_bom.json', {'entries': []})):
            with io.open(os.path.join(self.tmp, name), 'w', encoding='utf-8-sig') as f:
                json.dump(payload, f, ensure_ascii=False)
        rc, out = run_cli('--coverage', '--check',
                          '--coverage-matrix', os.path.join(self.tmp, 'matrix_bom.json'),
                          '--blindspot-allow', os.path.join(self.tmp, 'allow_bom.json'))
        self.assertEqual(rc, 0, '带 BOM 的矩阵/豁免表被拒了：\n' + out[-800:])
        self.assertIn('[PASS]', out)

    def test_missing_allow_file_is_red_for_check(self):
        """`--coverage --check` 要求豁免表在位（判定层的地基缺一块就该红）。"""
        rc, out = run_cli('--coverage', '--check', '--blindspot-allow',
                          os.path.join(self.tmp, 'no-allow.json'))
        self.assertEqual(rc, 1, out[-800:])
        self.assertIn('不存在', out)


if __name__ == '__main__':
    unittest.main()
