# -*- coding: utf-8 -*-
"""域⑪「工程状态」用例。

钉住的是**口径来自流程真源**这件事，以及几条会让 AI 判断错误的边界：
  · 状态位定义 == flow_spec.stateSlots（本模块不另立一份）
  · op → 状态位是**反查**出来的（不维护第二张映射表）
  · 隐含完成规则（后面那步做了 ⇒ 前面那步必然做过）
  · 失败不回写（「跑过」不等于「做成了」）
  · 状态文件损坏要**抛**，不许当空状态
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import flow_loader as F                                    # noqa: E402
import kb_tools                                            # noqa: E402
import project_state as ps                                 # noqa: E402


class TestSlotsComeFromFlowSpec(unittest.TestCase):

    def test_slots_are_flow_spec_slots(self):
        self.assertEqual(ps.slots(), F.state_slots(),
                         '状态位定义必须与 flow_spec.stateSlots 完全一致（不许另立一份）')

    def test_every_slot_points_at_real_step(self):
        for name, v in ps.slots().items():
            self.assertIn(v['setBy'], F.steps(), '%s 的 setBy 指向不存在的步骤' % name)
            if v.get('blocks'):
                self.assertIn(v['blocks'], F.steps(), '%s 的 blocks 指向不存在的步骤' % name)

    def test_op_to_slot_is_reverse_lookup(self):
        """op→状态位必须来自反查（steps[*].op + setsState），不是手写映射表。"""
        self.assertEqual(ps.slots_of_op('flythings_fui_pack'), ['packed'])
        self.assertEqual(ps.slots_of_op('flythings_build_ui_flow'), ['launched'])
        self.assertEqual(ps.slots_of_op('flythings_knowledge_search'), [])
        # 交叉验证：反查结果必须等于「扫 steps 得到的」答案
        manual = []
        for sid, s in F.steps().items():
            if s.get('op') == 'flythings_create_project':
                manual.extend(s.get('setsState') or [])
        self.assertEqual(ps.slots_of_op('flythings_create_project'), manual)

    def test_unknown_slot_raises(self):
        with self.assertRaises(ps.ProjectStateError):
            ps.slot('not_a_slot')


class _TempState(unittest.TestCase):
    """把状态家目录指到临时目录（不碰用户真实的 ~/.flythings）。"""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix='sth_')
        self._old = os.environ.get('FLYTHINGS_STATE_HOME')
        os.environ['FLYTHINGS_STATE_HOME'] = self.home
        self.addCleanup(self._restore_env)
        self.addCleanup(shutil.rmtree, self.home, True)
        self.root = tempfile.mkdtemp(prefix='proj_')
        os.makedirs(os.path.join(self.root, 'ui'))
        self.addCleanup(shutil.rmtree, self.root, True)

    def _restore_env(self):
        if self._old is None:
            os.environ.pop('FLYTHINGS_STATE_HOME', None)
        else:
            os.environ['FLYTHINGS_STATE_HOME'] = self._old


class TestStateFile(_TempState):

    def test_mark_then_show(self):
        ps.mark(self.root, 'projectCreated', note='建了')
        v = ps.show(self.root)
        self.assertEqual([d['slot'] for d in v['done']], ['projectCreated'])
        self.assertEqual(v['done'][0]['note'], '建了')
        self.assertTrue(os.path.isfile(v['stateFile']))

    def test_mark_is_idempotent(self):
        ps.mark(self.root, 'packed')
        ps.mark(self.root, 'packed', note='第二次')
        v = ps.show(self.root)
        self.assertEqual(len(v['done']), 1)
        self.assertEqual(v['done'][0]['note'], '第二次')

    def test_implicit_done_for_earlier_slots(self):
        """流程是顺序的：打了靠后的状态位，前面的一律视为已过（否则 next 会倒退）。"""
        ps.mark(self.root, 'projectCreated')
        ps.mark(self.root, 'designConfirmed')
        v = ps.show(self.root)
        self.assertIn('paramsDecided', v['implicit'])
        self.assertNotIn('paramsDecided', [p['slot'] for p in v['pending']])

    def test_next_is_first_pending(self):
        ps.mark(self.root, 'projectCreated')
        ps.mark(self.root, 'designConfirmed')
        v = ps.show(self.root)
        self.assertEqual(v['next']['step'], 'write-ui-json')
        self.assertEqual(v['next']['op'], 'flythings_ui_schema')

    def test_next_carries_gate(self):
        v = ps.show(self.root)                       # 空状态 → 第 0 步（前置条件闸门）
        self.assertEqual(v['next']['step'], 'clarify-params')
        self.assertEqual(v['next']['gate'], 'precondition')
        self.assertTrue(v['next']['gateHow'])

    def test_corrupt_state_raises(self):
        ps.save(self.root, {'slots': {}})
        with io.open(ps.state_file(self.root), 'w', encoding='utf-8') as fh:
            fh.write('{ 这不是 json')
        with self.assertRaises(ps.ProjectStateError):
            ps.load(self.root)

    def test_reset_clears_all(self):
        ps.mark(self.root, 'packed')
        ps.reset(self.root)
        self.assertEqual(ps.load(self.root)['slots'], {})

    def test_unmark(self):
        ps.mark(self.root, 'packed')
        self.assertTrue(ps.unmark(self.root, 'packed'))
        self.assertFalse(ps.unmark(self.root, 'packed'))

    def test_resolve_defaults_to_recent(self):
        ps.mark(self.root, 'packed')
        self.assertEqual(ps.resolve(''), os.path.abspath(self.root))
        self.assertEqual(ps.resolve(self.root), os.path.abspath(self.root))

    def test_dead_project_pruned_from_recent(self):
        dead = tempfile.mkdtemp(prefix='dead_')
        ps.touch(dead)
        shutil.rmtree(dead)
        self.assertNotIn(dead, [r['root'] for r in ps.recent()])


class TestAutoMark(_TempState):

    def _raw(self, ok=True):
        return json.dumps({'ok': ok, 'op': 'flythings_fui_pack'})

    def test_success_marks(self):
        out = json.loads(kb_tools._state_auto_mark('flythings_fui_pack',
                                                   {'project_root': self.root}, self._raw(True)))
        self.assertEqual(out.get('stateMarked'), ['packed'])
        self.assertIn('packed', ps.load(self.root)['slots'])

    def test_failure_does_not_mark(self):
        """失败不许回写 —— 否则「跑过一次没成功」会被当成「做成了」。"""
        out = json.loads(kb_tools._state_auto_mark('flythings_fui_pack',
                                                   {'project_root': self.root}, self._raw(False)))
        self.assertNotIn('stateMarked', out)
        self.assertEqual(ps.load(self.root)['slots'], {})

    def test_op_without_slots_is_untouched(self):
        raw = json.dumps({'ok': True, 'op': 'flythings_knowledge_search'})
        out = kb_tools._state_auto_mark('flythings_knowledge_search',
                                        {'query': 'x'}, raw)
        self.assertEqual(out, raw, '没有状态位的 op 不该被改写返回体')

    def test_non_project_path_is_skipped(self):
        out = kb_tools._state_auto_mark('flythings_fui_pack',
                                        {'project_root': 'D:/definitely/not/here'},
                                        self._raw(True))
        self.assertNotIn('stateMarked', json.loads(out))

    def test_path_kwarg_derives_root(self):
        """只给了 path（如 ui/main.json）也要能推出工程根。"""
        p = os.path.join(self.root, 'ui', 'main.json')
        with io.open(p, 'w', encoding='utf-8') as fh:
            fh.write('{}')
        self.assertEqual(ps._root_from_kwargs({'path': p}), os.path.abspath(self.root))


class TestOp(_TempState):

    def test_show_via_op(self):
        r = json.loads(kb_tools.flythings_project_state(project_root=self.root))
        self.assertTrue(r['ok'])
        self.assertEqual(r['action'], 'show')

    def test_mark_then_show_via_op(self):
        json.loads(kb_tools.flythings_project_state(project_root=self.root,
                                                    action='mark', slot='packed'))
        r = json.loads(kb_tools.flythings_project_state(project_root=self.root))
        self.assertEqual([d['slot'] for d in r['done']], ['packed'])

    def test_bad_slot_returns_envelope_with_action(self):
        """坏参数要回统一 envelope，并且带码表补出来的 action（域⑫）。"""
        r = json.loads(kb_tools.flythings_project_state(project_root=self.root,
                                                        action='mark', slot='nope'))
        self.assertFalse(r['ok'])
        self.assertEqual(r['error']['code'], 'BAD_PARAMS')
        self.assertTrue(r['error'].get('action'), 'error.action 应由错误码表补上')

    def test_reset_requires_explicit_root(self):
        r = json.loads(kb_tools.flythings_project_state(action='reset'))
        self.assertFalse(r['ok'])

    def test_reset_via_op(self):
        json.loads(kb_tools.flythings_project_state(project_root=self.root,
                                                    action='mark', slot='packed'))
        json.loads(kb_tools.flythings_project_state(project_root=self.root, action='reset'))
        r = json.loads(kb_tools.flythings_project_state(project_root=self.root))
        self.assertEqual(r['done'], [])

    def test_no_project_gives_hint_not_error(self):
        r = json.loads(kb_tools.flythings_project_state())
        self.assertTrue(r['ok'], '没工程记录是「还没有」，不是错误')
        self.assertIn('hint', r)


if __name__ == '__main__':
    unittest.main()
