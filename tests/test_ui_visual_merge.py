# -*- coding: utf-8 -*-
"""ui-visual 三合一入口契约（v0.27.37，沛哥：ui-visual 做个 action 入口）。

合并：flythings_ui_editor + flythings_ui_edit_apply + flythings_ui_diff → flythings_ui_visual(action)。
钉住：
  ① action="list" 回三个动作与各自必填参数（AI 不用猜）
  ② 未知 action / 缺必填参数 → BAD_PARAMS + 本 action 正确参数（可机读，不执行内层）
  ③ action 路由到正确实现（editor 出编辑页 / edit_apply 写回 / diff 出差异清单）
  ④ 传了别家参数 → visualNote 明说已忽略（不静默忽略）
  ⑤ 三个旧名调进分发器 → OP_RENAMED，且 hint 里带该用哪个 action
"""
import io
import json
import os
import unittest

import _util as U

try:
    from PIL import Image
    HAS_PIL = True
except Exception:
    HAS_PIL = False

MIN_JSON = {'id': 0, 'resolution': {'width': 480, 'height': 320},
            'position': {'left': 0, 'top': 0, 'width': 480, 'height': 320},
            'textview__1': {'type': 'textview', 'caption': 'T', 'id': 50001,
                            'position': {'left': 10, 'top': 20, 'width': 100, 'height': 30},
                            'text': 'hello', 'touchable': False}}


class VisualBase(unittest.TestCase):
    def setUp(self):
        self.tmp = U.project()
        self.page = os.path.join(self.tmp, 'ui', 'main.json')
        U.write(self.page, json.dumps(MIN_JSON, ensure_ascii=False, indent=2))
        self.changes = json.dumps(
            {'file': 'main.json', 'resolution': '480x320',
             'changes': {'textview__1': {'left': 33, 'top': 44}}}, ensure_ascii=False)

    def tearDown(self):
        U.cleanup(self.tmp)


class TestActionDirectory(unittest.TestCase):
    def test_list_returns_all_actions_and_required(self):
        r = U.jcall('flythings_ui_visual')          # 不传 action = 目录
        self.assertTrue(r.get('success'), r)
        acts = r['actions']
        self.assertEqual(sorted(acts), ['diff', 'edit_apply', 'editor'])
        self.assertEqual(acts['editor']['required'], ['project_root'])
        self.assertEqual(acts['edit_apply']['required'], ['project_root', 'changes'])
        self.assertEqual(acts['diff']['required'], ['image_a', 'image_b'])
        self.assertIn('dry_run', acts['edit_apply']['args'])
        self.assertIn('out_png', acts['diff']['args'])

    def test_list_alias(self):
        self.assertTrue(U.jcall('flythings_ui_visual', {'action': 'list'}).get('success'))

    def test_unknown_action_is_bad_params(self):
        r = U.jcall('flythings_ui_visual', {'action': 'diffs'})
        self.assertFalse(r['ok'], r)
        self.assertEqual(r['error']['code'], 'BAD_PARAMS')
        for act in ('editor', 'edit_apply', 'diff'):
            self.assertIn(act, r['error']['hint'])


class TestRequiredArgs(VisualBase):
    def test_editor_needs_project_root(self):
        r = U.jcall('flythings_ui_visual', {'action': 'editor', 'output_dir': self.tmp})
        self.assertFalse(r['ok'], r)
        self.assertEqual(r['error']['code'], 'BAD_PARAMS')
        self.assertIn('project_root', r['error']['msg'])

    def test_edit_apply_needs_changes(self):
        r = U.jcall('flythings_ui_visual', {'action': 'edit_apply', 'project_root': self.tmp})
        self.assertFalse(r['ok'], r)
        self.assertIn('changes', r['error']['msg'])

    def test_diff_needs_two_images(self):
        r = U.jcall('flythings_ui_visual', {'action': 'diff', 'image_a': 'a.png'})
        self.assertFalse(r['ok'], r)
        self.assertIn('image_b', r['error']['msg'])


class TestEditorAndApplyRouting(VisualBase):
    def test_editor_makes_edit_html(self):
        r = U.jcall('flythings_ui_visual', {'action': 'editor', 'project_root': self.tmp})
        self.assertTrue(r['ok'], r)
        self.assertTrue(r['files'], r)
        self.assertTrue(os.path.isfile(r['files'][0]['html']), r)
        self.assertTrue(os.path.basename(r['files'][0]['html']).endswith('.edit.html'))

    def test_edit_apply_dry_run_then_write(self):
        before = io.open(self.page, encoding='utf-8').read()
        r = U.jcall('flythings_ui_visual', {'action': 'edit_apply', 'project_root': self.tmp,
                                           'changes': self.changes, 'dry_run': True})
        self.assertTrue(r['ok'], r)
        self.assertEqual(io.open(self.page, encoding='utf-8').read(), before, 'dry_run 写盘了')
        r = U.jcall('flythings_ui_visual', {'action': 'edit_apply', 'project_root': self.tmp,
                                           'changes': self.changes})
        self.assertTrue(r['ok'], r)
        self.assertTrue(os.path.isfile(self.page + '.bak'), '写回必须留 .bak')
        d = json.loads(io.open(self.page, encoding='utf-8').read())
        self.assertEqual(d['textview__1']['position']['left'], 33)
        self.assertFalse(os.path.isfile(os.path.join(self.tmp, 'ui', 'main.ftu')),
                         '默认不该 pack')

    def test_ignored_args_are_reported(self):
        r = U.jcall('flythings_ui_visual', {'action': 'editor', 'project_root': self.tmp,
                                           'image_a': 'a.png', 'image_b': 'b.png'})
        self.assertTrue(r['ok'], r)
        self.assertIn('image_a', r.get('visualNote', ''), '别家 action 的参数必须明说被忽略')

    def test_no_note_when_args_match(self):
        r = U.jcall('flythings_ui_visual', {'action': 'editor', 'project_root': self.tmp})
        self.assertNotIn('visualNote', r, r)


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class TestDiffRouting(VisualBase):
    def _imgs(self):
        a = os.path.join(self.tmp, 'a.png')
        b = os.path.join(self.tmp, 'b.png')
        Image.new('RGB', (60, 40), (255, 255, 255)).save(a)
        im = Image.new('RGB', (60, 40), (255, 255, 255))
        for x in range(10, 20):
            for y in range(10, 20):
                im.putpixel((x, y), (0, 0, 0))
        im.save(b)
        return a, b

    def test_diff_returns_regions(self):
        a, b = self._imgs()
        r = U.jcall('flythings_ui_visual', {'action': 'diff', 'image_a': a, 'image_b': b})
        self.assertTrue(r.get('success', r.get('ok')), r)
        self.assertIsInstance(r.get('regions', []), list)
        self.assertFalse(r.get('identical', True), '有 10x10 黑块，不该判 identical')

    def test_diff_accepts_style_two_positional_name(self):
        """旧 flythings_ui_diff 的老参数名（image_a/image_b/out_png）在合并后照样能用。"""
        a, b = self._imgs()
        out = os.path.join(self.tmp, 'diff.png')
        r = U.jcall('flythings_ui_visual', {'action': 'diff', 'image_a': a, 'image_b': b,
                                           'tolerance': 0, 'shift': 0, 'out_png': out})
        self.assertTrue(r.get('success', r.get('ok')), r)
        self.assertTrue(os.path.isfile(out), 'out_png 未生成')


class TestOldNamesRenamed(unittest.TestCase):
    def test_each_old_name_points_at_its_action(self):
        want = {'flythings_ui_editor': 'editor',
                'flythings_ui_edit_apply': 'edit_apply',
                'flythings_ui_diff': 'diff'}
        for old, act in want.items():
            r = U.jcall(old, {'project_root': '/tmp/x'})
            self.assertFalse(r['ok'], old)
            self.assertEqual(r['error']['code'], 'OP_RENAMED', old)
            self.assertIn('flythings_ui_visual', r['error']['hint'], old)
            self.assertIn(act, r['error']['hint'],
                          '%s 的 hint 应告诉该用哪个 action' % old)


if __name__ == '__main__':
    unittest.main(verbosity=2)
