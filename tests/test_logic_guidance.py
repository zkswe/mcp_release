# -*- coding: utf-8 -*-
"""「页面逻辑写在 src/logic/<页>Logic.cc」这条**引导链**的回归用例（2026-10-05）。

背景（真发生过）：`flythings_gen_logic_stub` 只补空桩、描述里还写着「不写业务」，
而**唯一**那句「桩生成完，再往 src/logic/*.cc 里填业务」住在 flow_spec 的 `how[1]` ——
`render_prompt` 只渲染 `how[0]`，于是动作 prompt 与工程状态里都看不到它，
AI 交付就停在空桩上（评估方据此判「业务逻辑半缺」，而 `fun build` 早就把桩生成好了）。

钉四件事：
 ① 流程里有 `write-logic` 步骤 + `logicWritten` 状态位（定义只来自 flow_spec）；
 ② 该步骤进了主要流程，且**排在 pack 之前**（顺序错了引导就落空）；
 ③ **prompt 与 next 必须带 `how` 的全部行** —— 回退成 `how[0]` 立刻红；
 ④ stub op 的契约 / 返回体 / 缺文件提示都指向「逻辑写在 logic」，而不是把它当终点。
"""
import ast
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (BASE, os.path.join(BASE, 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

import flow_loader as F                                    # noqa: E402
import kb_tools                                            # noqa: E402
import logic_tools as lt                                   # noqa: E402
import op_spec_loader as osl                               # noqa: E402
import project_state as ps                                 # noqa: E402

FLOWS_WITH_WRITE_LOGIC = ('idea-to-app', 'migrate', 'reskin',
                          'new-project', 'ui-from-prototype')


def _flow_step_ids(fid):
    return [it['id'] for it in F.flow_items(fid)]


class TestWriteLogicStep(unittest.TestCase):
    """① 步骤与状态位都在真源里，且验收判据齐备。"""

    def test_step_registered(self):
        s = F.step('write-logic')
        self.assertTrue(s.get('how'), 'write-logic 缺 how')
        self.assertIn('logicWritten', s.get('setsState') or [],
                      'write-logic 必须写入 logicWritten 状态位')
        v = F.step_verify('write-logic')       # 缺字段会抛 FlowSpecError
        for k in ('ok', 'notOk', 'evidence'):
            self.assertTrue(v[k].strip())

    def test_gate_says_fill_stubs_first(self):
        s = F.step('write-logic')
        self.assertEqual(s.get('gate'), 'precondition')
        self.assertIn('桩', s.get('gateHow') or '', '闸门要说清「先补桩再写逻辑」')

    def test_slot_points_at_step(self):
        slot = F.state_slots().get('logicWritten')
        self.assertIsNotNone(slot, 'flow_spec 缺 logicWritten 状态位')
        self.assertEqual(slot['setBy'], 'write-logic')
        self.assertEqual(slot.get('blocks'), 'pack', 'logicWritten 应挡住 pack（先写逻辑再打包）')

    def test_how_names_the_logic_file_and_code_side_wiring(self):
        how = '\n'.join(F.step('write-logic')['how'])
        self.assertIn('src/logic/', how, 'how 必须点名落点文件')
        self.assertIn('findControlByID', how,
                      '容器/显示类控件没有回调桩，必须给出代码侧接线口径')
        self.assertIn('.cpp', how, '复杂功能的落点（src/<业务域>/*.cpp）要写明')


class TestFlowsWireIt(unittest.TestCase):
    """② 主要流程都带上它，且不晚于 pack。"""

    def test_present_in_main_flows(self):
        for fid in FLOWS_WITH_WRITE_LOGIC:
            ids = _flow_step_ids(fid)
            self.assertIn('write-logic', ids, '%s 缺 write-logic' % fid)

    def test_before_pack(self):
        for fid in FLOWS_WITH_WRITE_LOGIC:
            ids = _flow_step_ids(fid)
            self.assertLess(ids.index('write-logic'), ids.index('pack'),
                            '%s 里 write-logic 排在 pack 之后 —— 引导会落空' % fid)

    def test_after_stub_step_where_present(self):
        for fid in ('idea-to-app', 'migrate', 'reskin'):
            ids = _flow_step_ids(fid)
            self.assertLess(ids.index('gen-logic-stub'), ids.index('write-logic'),
                            '%s 里补桩应排在写逻辑之前' % fid)


class TestPromptCarriesAllHow(unittest.TestCase):
    """③ 回退守卫：`how` 的每一行都要进 prompt / next（曾经只渲染 how[0]）。"""

    def test_prompt_has_every_how_line(self):
        body = F.render_prompt('new-project')['body']
        item = [i for i in F.flow_items('new-project') if i['id'] == 'write-logic'][0]
        how = item['step']['how']
        self.assertGreater(len(how), 1, 'write-logic 的 how 至少两行，本用例才有意义')
        for h in how:
            self.assertIn(h, body, 'prompt 吞了 how 行：%s' % h[:40])

    def test_prompt_has_second_line_of_stub_step(self):
        """通用回退守卫：动作流程里每一步的**每一行** how 都要进 prompt。

        （历史 bug：`render_prompt` 只渲染 `how[0]`，于是补桩那步的
        「生成归 fun build」与「桩生成完再填业务」永远进不了 prompt。）
        """
        checked = 0
        for fid in F.flows_of('action'):
            body = F.render_prompt(fid)['body']
            for item in F.flow_items(fid):
                how = item['step'].get('how') or []
                if len(how) < 2:
                    continue
                for h in how:
                    self.assertIn(h, body, '%s / %s 吞了 how 行：%s'
                                  % (fid, item['id'], h[:40]))
                checked += 1
        self.assertGreater(checked, 0, '没有任何动作流程步骤有多行 how —— 本用例会静默失效')


class _TempState(unittest.TestCase):
    """把状态家目录指到临时目录（不碰用户真实的 ~/.flythings）。"""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix='lg_home_')
        self._old = os.environ.get('FLYTHINGS_STATE_HOME')
        os.environ['FLYTHINGS_STATE_HOME'] = self.home
        self.addCleanup(self._restore_env)
        self.addCleanup(shutil.rmtree, self.home, True)
        self.root = tempfile.mkdtemp(prefix='lg_proj_')
        os.makedirs(os.path.join(self.root, 'ui'))
        self.addCleanup(shutil.rmtree, self.root, True)

    def _restore_env(self):
        if self._old is None:
            os.environ.pop('FLYTHINGS_STATE_HOME', None)
        else:
            os.environ['FLYTHINGS_STATE_HOME'] = self._old


class TestProjectStateNext(_TempState):
    """③ 续：补完桩之后，「下一步」必须是写页面逻辑。"""

    def test_next_after_stubs_is_write_logic(self):
        ps.mark(self.root, 'stubsGenerated')
        v = ps.show(self.root)
        self.assertEqual(v['next']['step'], 'write-logic',
                         '补完桩的下一步应当报「在 logic 里写页面逻辑」，实为 %r'
                         % (v['next'] or {}).get('step'))
        how = v['next'].get('how') or []
        self.assertEqual(how, list(F.step('write-logic')['how']),
                         'next.how 必须给全部 how 行（只给 how[0] 会吞掉引导）')


class TestStubOpPointsToLogic(unittest.TestCase):
    """④ op 被降级成「体检/兜底」，并且明说逻辑写在 logic 里。"""

    def test_description_carries_logic_pointer(self):
        doc = kb_tools.flythings_gen_logic_stub.__doc__ or ''
        first = doc.strip().splitlines()[0]
        self.assertIn('体检', first, '工具描述首行要表明「体检/兜底」定位')
        self.assertIn('src/logic', doc, '工具描述必须点名页面逻辑的落点')
        self.assertIn('fun build', doc, '工具描述要说明生成归 fun build')

    def test_contract_rules_point_to_write_logic(self):
        s = osl.spec('flythings_gen_logic_stub')
        text = '\n'.join((s.get('rules') or []) + (s.get('hardRules') or [])
                         + [s.get('summary') or ''])
        self.assertIn('页面逻辑写在', text)
        self.assertIn('fun build', text)

    def _mk(self, with_logic):
        root = tempfile.mkdtemp(prefix='lg_stub_')
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, 'ui'))
        os.makedirs(os.path.join(root, 'src', 'logic'))
        page = {'id': 1, 'resolution': {'width': 1024, 'height': 600},
                'position': {'left': 0, 'top': 0, 'width': 1024, 'height': 600},
                'backgroundColor': -1,
                'button__1': {'id': 20001, 'caption': 'BtnA',
                              'position': {'left': 0, 'top': 0, 'width': 10, 'height': 10}}}
        with io.open(os.path.join(root, 'ui', 'main.json'), 'w', encoding='utf-8') as fh:
            fh.write(json.dumps(page, ensure_ascii=False))
        if with_logic:
            with io.open(os.path.join(root, 'src', 'logic', 'mainLogic.cc'),
                         'w', encoding='utf-8') as fh:
                fh.write('static void onUI_init(){\n}\n')
        return root

    def test_notes_tell_where_logic_goes(self):
        out = lt.gen_logic_stub(self._mk(True), dry_run=True)
        notes = '\n'.join(out['notes'])
        self.assertIn('页面逻辑写在同一个', notes)
        self.assertIn('setXxxListener', notes,
                      'notes 要给容器/显示类控件的代码侧接线口径')
        self.assertIn('fun build', notes, 'notes 要说明生成归 fun build')

    def test_missing_logic_file_points_to_toolchain(self):
        out = lt.gen_logic_stub(self._mk(False))
        err = out['pages'][0].get('error') or ''
        self.assertIn('fun build', err, '缺 logic 文件时应指向工具链生成，而不是「手工建页」')
        self.assertNotIn('手工建页', err, '手工建页会漏 INIT_UI_EVENT_BINDINGS')


class TestSymptomEntry(unittest.TestCase):
    """④ 续：「只补桩没写逻辑」进症状索引，且指向的文档真实存在。"""

    def test_entry_registered_and_doc_exists(self):
        with io.open(os.path.join(BASE, 'symptom_spec.json'), encoding='utf-8') as fh:
            spec = json.load(fh)
        e = [x for x in spec['entries'] if x.get('id') == 'stub-only-no-logic']
        self.assertEqual(len(e), 1, 'symptom_spec 缺 stub-only-no-logic 条目')
        e = e[0]
        self.assertTrue(e.get('symptom') and e.get('rule') and e.get('verify'))
        self.assertTrue(os.path.isfile(os.path.join(BASE, e['doc'])),
                        'doc 指向不存在的文件：%s' % e['doc'])


if __name__ == '__main__':
    unittest.main()
