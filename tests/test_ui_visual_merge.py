# -*- coding: utf-8 -*-
"""ui-visual 三合一入口契约（v0.27.37：ui-visual 做个 action 入口）。

合并：flythings_ui_editor + flythings_ui_edit_apply + flythings_ui_diff → flythings_ui_visual(action)。
2026-10-01 加两个 action：render（json → 引擎等价 PNG，离线所见即所得）/ render_check
（渲染图 vs 真机截图 → 一致性判据；pass=false ⇒ ok=false，不静默）。
钉住：
  ① action="list" 回六个动作与各自必填参数（AI 不用猜）
  ② 未知 action / 缺必填参数 → BAD_PARAMS + 本 action 正确参数（可机读，不执行内层）
  ③ action 路由到正确实现（editor 出编辑页 / edit_apply 写回 / diff 出差异清单 / render 出 PNG）
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
        self.assertEqual(sorted(acts), ['baseline', 'diff', 'edit_apply', 'editor',
                                        'render', 'render_check'])
        self.assertEqual(acts['editor']['required'], ['project_root'])
        self.assertEqual(acts['edit_apply']['required'], ['project_root', 'changes'])
        self.assertEqual(acts['diff']['required'], ['image_a', 'image_b'])
        self.assertEqual(acts['baseline']['required'], ['project_root'])   # 2026-09-29 新 action
        self.assertEqual(acts['render']['required'], ['project_root'])      # 2026-10-01 离线所见即所得
        self.assertEqual(acts['render_check']['required'], ['device', 'json'])
        self.assertIn('dry_run', acts['edit_apply']['args'])
        self.assertIn('out_png', acts['diff']['args'])
        self.assertIn('mode', acts['baseline']['args'])
        self.assertIn('baseline_key', acts['baseline']['args'])
        for a in ('page', 'scale', 'out', 'all'):
            self.assertIn(a, acts['render']['args'])
        for a in ('render', 'device', 'json', 'tol', 'max_ratio'):
            self.assertIn(a, acts['render_check']['args'])

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

    def test_render_needs_project_root(self):
        r = U.jcall('flythings_ui_visual', {'action': 'render'})
        self.assertFalse(r['ok'], r)
        self.assertEqual(r['error']['code'], 'BAD_PARAMS')
        self.assertIn('project_root', r['error']['msg'])

    def test_render_check_needs_device_and_json(self):
        r = U.jcall('flythings_ui_visual', {'action': 'render_check'})
        self.assertFalse(r['ok'], r)
        self.assertEqual(r['error']['code'], 'BAD_PARAMS')
        self.assertIn('device', r['error']['msg'])
        self.assertIn('json', r['error']['msg'])


class TestEditApplyWriteBack(VisualBase):
    """「人用编辑器改完 → 写回 json」这条闭环的判据（2026-10-05 修）：

    ① **格式自检是语义无损口径**：真实工程里大量 json 带 EOF 尾换行（仓库 blob 侧
       31 份去重里 **24 份**如此），检出到 Windows 又普遍变 CRLF（本机 `core.autocrlf=true`
       且仓内无 `.gitattributes`）—— 旧实现按字节比对 → 两类都拒写；
    ② **写回要 byte 稳定**：行尾风格与 EOF 换行沿用源文件，diff 只落在改动的行上；
    ③ **路径写错不许静默成功**（硬纪律「不静默」）。
    """

    def test_trailing_newline_file_is_writable(self):
        """尾换行文件：能写 + 尾换行保住 + 除改动行外不变（旧实现直接拒写）。"""
        p = os.path.join(self.tmp, 'ui', 'tn.json')
        U.write(p, json.dumps(MIN_JSON, ensure_ascii=False, indent=2) + '\n')
        raw0 = open(p, 'rb').read()
        self.assertTrue(raw0.endswith(b'}\n'), '前置：夹具必须带尾换行')
        r = U.jcall('flythings_ui_visual', {'action': 'edit_apply', 'project_root': self.tmp,
                                            'changes': json.dumps(
                                                {'file': 'tn.json',
                                                 'changes': {'textview__1': {'left': 60}}},
                                                ensure_ascii=False)})
        self.assertTrue(r['ok'], r)
        raw1 = open(p, 'rb').read()
        self.assertTrue(raw1.endswith(b'}\n'), '写回把尾换行丢了（会造成整文件 diff）')
        self.assertEqual(json.loads(raw1.decode('utf-8'))['textview__1']['position']['left'], 60)
        l0 = raw0.decode('utf-8').splitlines()
        l1 = raw1.decode('utf-8').splitlines()
        self.assertEqual(len(l0), len(l1))
        self.assertLessEqual(sum(1 for a, b in zip(l0, l1) if a != b), 4,
                             '除改动行外不该有别的行变化')

    def test_crlf_file_keeps_crlf(self):
        """CRLF 文件：能写 + 行尾仍是 CRLF（旧实现拒写，且写回会整文件变 LF）。"""
        p = os.path.join(self.tmp, 'ui', 'crlf.json')
        U.write(p, json.dumps(MIN_JSON, ensure_ascii=False, indent=2).replace('\n', '\r\n'))
        raw0 = open(p, 'rb').read()
        self.assertIn(b'\r\n', raw0, '前置：夹具必须是 CRLF')
        r = U.jcall('flythings_ui_visual', {'action': 'edit_apply', 'project_root': self.tmp,
                                            'changes': json.dumps(
                                                {'file': 'crlf.json',
                                                 'changes': {'textview__1': {'top': 55}}},
                                                ensure_ascii=False)})
        self.assertTrue(r['ok'], r)
        self.assertIn(b'\r\n', open(p, 'rb').read(), '写回把 CRLF 改成了 LF（整文件 diff）')

    def test_real_reformat_is_still_refused(self):
        """真重排（缩进改成 4 空格）仍要拒 —— 放宽的只是尾换行/行尾风格，不是所有格式。"""
        p = os.path.join(self.tmp, 'ui', 'indent4.json')
        U.write(p, json.dumps(MIN_JSON, ensure_ascii=False, indent=4))
        r = U.jcall('flythings_ui_visual', {'action': 'edit_apply', 'project_root': self.tmp,
                                            'changes': json.dumps(
                                                {'file': 'indent4.json',
                                                 'changes': {'textview__1': {'left': 5}}},
                                                ensure_ascii=False)})
        self.assertFalse(r['ok'], '缩进不符必须仍然拒写')
        self.assertIn('--force', json.dumps(r, ensure_ascii=False))

    def test_wrong_path_is_not_silent_success(self):
        """路径全错：不许 success=true（旧实现回 success + skipped + exit 0）。"""
        p = os.path.join(self.tmp, 'ui', 'ghost.json')
        U.write(p, json.dumps(MIN_JSON, ensure_ascii=False, indent=2))
        before = open(p, 'rb').read()
        r = U.jcall('flythings_ui_visual', {'action': 'edit_apply', 'project_root': self.tmp,
                                            'changes': json.dumps(
                                                {'file': 'ghost.json',
                                                 'changes': {'button__999': {'left': 5}}},
                                                ensure_ascii=False)})
        self.assertFalse(r['ok'], '一条都没落地却报成功 = 静默失败')
        self.assertFalse(r.get('partiallyApplied'))
        self.assertEqual(open(p, 'rb').read(), before, '全错时不该写盘')

    def test_partial_apply_reports_partial(self):
        """部分落地：success=false + partiallyApplied=true（落地的不回滚，人要看得见哪条没成）。"""
        p = os.path.join(self.tmp, 'ui', 'part.json')
        U.write(p, json.dumps(MIN_JSON, ensure_ascii=False, indent=2))
        r = U.jcall('flythings_ui_visual', {'action': 'edit_apply', 'project_root': self.tmp,
                                            'changes': json.dumps(
                                                {'file': 'part.json',
                                                 'changes': {'textview__1': {'left': 70},
                                                             'button__999': {'left': 5}}},
                                                ensure_ascii=False)})
        self.assertFalse(r['ok'], r)
        self.assertTrue(r.get('partiallyApplied'), r)
        self.assertTrue(r.get('applied') or r.get('appliedProps'), r)
        self.assertTrue(r.get('skipped'), r)
        d = json.loads(io.open(p, encoding='utf-8').read())
        self.assertEqual(d['textview__1']['position']['left'], 70, '成的那条要真落地')


    def test_unknown_geometry_field_is_not_silent_success(self):
        """几何字段名写错（`{"x":..}`）→ 必须失败并点名，不许 success:true + fields:{}。

        旧行为（2026-10-05 实测）：`{"textview__1":{"x":999,"Left":999}}` → `success:true`、
        `applied[0].fields={}`、**文件照写盘、.bak 照留** → 调用方以为改完了。
        """
        p = os.path.join(self.tmp, 'ui', 'badgeo.json')
        U.write(p, json.dumps(MIN_JSON, ensure_ascii=False, indent=2))
        before = open(p, 'rb').read()
        r = U.jcall('flythings_ui_visual', {'action': 'edit_apply', 'project_root': self.tmp,
                                            'changes': json.dumps(
                                                {'file': 'badgeo.json',
                                                 'changes': {'textview__1': {'x': 999, 'Left': 9}}},
                                                ensure_ascii=False)})
        self.assertFalse(r['ok'], r)
        self.assertEqual(r.get('malformed'), ['textview__1'], r)
        self.assertTrue(r.get('hint'), r)
        self.assertEqual(open(p, 'rb').read(), before, '字段名不认识时不该写盘')
        self.assertFalse(os.path.isfile(p + '.bak'), '不该产生 .bak')

    def test_clamped_values_are_reported(self):
        """越界被钳制时要单列 `clamped` —— `fields` 记的是**请求值**，别让人以为落的是它。

        实测口径：480 宽的屏上把 left 设成 400（控件宽 100）→ 落盘 left 被钳到 480-100=380。
        """
        p = os.path.join(self.tmp, 'ui', 'clamp.json')
        U.write(p, json.dumps(MIN_JSON, ensure_ascii=False, indent=2))
        r = U.jcall('flythings_ui_visual', {'action': 'edit_apply', 'project_root': self.tmp,
                                            'changes': json.dumps(
                                                {'file': 'clamp.json',
                                                 'changes': {'textview__1': {'left': 400}}},
                                                ensure_ascii=False)})
        self.assertTrue(r['ok'], r)
        row = r['applied'][0]
        self.assertEqual(row['fields']['left'][1], 400, 'fields 记请求值')
        self.assertIn('clamped', row, '被钳制时必须单列 clamped：%s' % row)
        self.assertEqual(row['clamped']['left'], [400, 380], row)
        self.assertTrue(row.get('hint'))
        d = json.loads(io.open(p, encoding='utf-8').read())
        self.assertEqual(d['textview__1']['position']['left'], 380, '实际落盘值 = 钳后值')

    def test_in_bounds_edit_has_no_clamped_key(self):
        """没越界就不该出现 clamped（避免把正常改动也标成"被改过"）。"""
        r = U.jcall('flythings_ui_visual', {'action': 'edit_apply', 'project_root': self.tmp,
                                            'changes': self.changes})
        self.assertTrue(r['ok'], r)
        self.assertNotIn('clamped', r['applied'][0])

    def test_non_dict_geometry_is_reported(self):
        """`changes` 的值不是对象 → 进 skipped，不许抛栈。"""
        p = os.path.join(self.tmp, 'ui', 'scalar.json')
        U.write(p, json.dumps(MIN_JSON, ensure_ascii=False, indent=2))
        r = U.jcall('flythings_ui_visual', {'action': 'edit_apply', 'project_root': self.tmp,
                                            'changes': json.dumps(
                                                {'file': 'scalar.json',
                                                 'changes': {'textview__1': 42}},
                                                ensure_ascii=False)})
        self.assertFalse(r['ok'], r)
        self.assertTrue(r.get('skipped'), r)


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


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class TestRenderRouting(VisualBase):
    """render / render_check 路由（2026-10-01：json → 离线引擎等价图 → 与真机截图一致性）。"""

    def _render_main(self):
        return U.jcall('flythings_ui_visual', {'action': 'render', 'project_root': self.tmp,
                                              'page': 'main'})

    def test_render_outputs_png_and_unsupported_list(self):
        r = self._render_main()
        self.assertTrue(r.get('success'), r)
        self.assertEqual(len(r['pages']), 1)
        self.assertEqual(r['pages'][0]['page'], 'main')
        self.assertEqual(r['pages'][0]['size'], [480, 320])
        self.assertTrue(os.path.isfile(r['pages'][0]['png']), r)
        self.assertIsInstance(r['unsupported'], list, 'unsupported 必须原样透出（不吞）')
        self.assertTrue(r.get('report'), r)

    def test_render_scale_is_nearest_and_doubles_size(self):
        r = U.jcall('flythings_ui_visual', {'action': 'render', 'project_root': self.tmp,
                                            'page': 'main', 'scale': 2})
        self.assertTrue(r.get('success'), r)
        self.assertEqual(r['pages'][0]['size'], [960, 640])

    def test_render_check_consistent_with_its_own_render(self):
        rr = self._render_main()
        self.assertTrue(rr.get('success'), rr)
        r = U.jcall('flythings_ui_visual', {'action': 'render_check',
                                            'render': rr['pages'][0]['png'],
                                            'device': rr['pages'][0]['png'],
                                            'json': self.page})
        self.assertTrue(r.get('success'), r)
        self.assertTrue(r.get('pass'), r)
        self.assertTrue(r.get('ok'), r)
        self.assertEqual(r['nonTextConsistencyPct'], 100.0)
        self.assertIsInstance(r['attribution'], list)

    def test_render_check_self_render_path(self):
        """不给 render → 用 project_root+page 自渲染再比（与真机图一致 → pass）。"""
        rr = self._render_main()
        r = U.jcall('flythings_ui_visual', {'action': 'render_check', 'project_root': self.tmp,
                                            'page': 'main', 'device': rr['pages'][0]['png'],
                                            'json': self.page})
        self.assertTrue(r.get('success'), r)
        self.assertTrue(r.get('pass'), r)
        self.assertIn('_render', r['render'], r)

    def test_render_check_missing_device_file_is_reported(self):
        r = U.jcall('flythings_ui_visual', {'action': 'render_check', 'project_root': self.tmp,
                                            'page': 'main',
                                            'device': os.path.join(self.tmp, 'nope.png'),
                                            'json': self.page})
        self.assertFalse(r['ok'], r)          # 真机图不存在 → 明说，不静默
        self.assertIn('device/json', r['error']['msg'])

    def test_render_check_mismatch_is_reported_not_silent(self):
        """不一致 → ok=false + WYSIWYG_MISMATCH（返回体里明说，不静默）。"""
        rr = self._render_main()
        img = Image.open(rr['pages'][0]['png']).convert('RGB')
        for x in range(200, 240):                  # 文字盒之外涂一块红 → 非文字区必不一致
            for y in range(200, 240):
                img.putpixel((x, y), (255, 0, 0))
        dev = os.path.join(self.tmp, 'dev.png')
        img.save(dev)
        r = U.jcall('flythings_ui_visual', {'action': 'render_check',
                                            'render': rr['pages'][0]['png'],
                                            'device': dev, 'json': self.page})
        self.assertTrue(r.get('success'), r)
        self.assertFalse(r.get('pass'), r)
        self.assertFalse(r.get('ok'), r)
        self.assertEqual(r['error']['code'], 'WYSIWYG_MISMATCH')
        self.assertIn('不一致', r['error']['msg'])


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
