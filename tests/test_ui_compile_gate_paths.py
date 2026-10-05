# -*- coding: utf-8 -*-
"""编译式验收接到**生成/落盘出口**（T1.3 第二批）的契约。

三条路径同一个口径（fatal 不落盘 / error 默认只记 / `allow_unvalidated` 强制 / `strict_ui` 加严）：
  ① `flythings_html_to_json`：生成到临时目录 → 编译 → 通过才搬到目标位置；
  ② `flythings_translate_ui`：落盘前先写临时文件 → 编译 → 通过才搬；
  ③ `flythings_ui_visual(action="edit_apply")`：写完 json 后编译，fatal → 从 `.bak` **回滚**。

自证纪律：把任一断言里的「不落盘」改回「落盘」，对应用例必须变红。
"""
import io
import json
import os
import sys
import unittest
from unittest import mock

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
for _p in (BASE, TESTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import kb_tools as K                                        # noqa: E402
import _util as U                                           # noqa: E402

HTML = os.path.join(BASE, 'ui_tools', 'examples', 'effects_test.html')
LVGL = '''
lv_obj_t *scr = lv_obj_create(NULL);
lv_obj_set_style_bg_color(scr, lv_color_hex(0x101418), 0);
lv_obj_t *lbl = lv_label_create(scr);
lv_label_set_text(lbl, "Temp");
lv_obj_set_pos(lbl, 24, 20);
lv_obj_t *bar = lv_slider_create(scr);
lv_obj_set_pos(bar, 24, 80);
lv_obj_set_size(bar, 200, 24);
lv_slider_set_range(bar, 0, 100);
lv_slider_set_value(bar, 40, LV_ANIM_OFF);
'''

PAGE = {
    "id": 0,
    "resolution": {"width": 480, "height": 272},
    "position": {"left": 0, "top": 0, "width": 480, "height": 272},
    "backgroundColor": 16777215,
    "textview__1": {
        "id": 50001, "caption": "TvTitle",
        "position": {"left": 20, "top": 20, "width": 200, "height": 40},
        "alignment": 36, "colorTab": {"color0": 0, "color1": -1, "color2": -1,
                                      "color3": -1, "color4": -1},
        "fontSize": 18, "text": "Hello", "touchable": False, "visible": True,
    },
}

FATAL_REPORT = {
    'ok': False, 'summary': {'fatal': 1, 'error': 0, 'warn': 0},
    'diagnostics': [{'severity': 'fatal', 'rule': 'SCH001', 'path': '/textview__1/position',
                     'msg': 'position 必须是对象（position），实际是 str', 'hint': '子盒对象字段必须是对象'}],
    'counts': {'pages': 1, 'controls': 1},
}


class _Base(unittest.TestCase):

    def setUp(self):
        self.root = U.project()
        self.addCleanup(U.cleanup, self.root)


class TestHtmlToJsonGate(_Base):

    def test_fatal_does_not_land(self):
        dst = os.path.join(self.root, 'ui', 'main.json')
        with mock.patch.object(K.uic, 'compile_json', return_value=dict(FATAL_REPORT)):
            r = json.loads(K.flythings_html_to_json(HTML, output_json=dst, res='480x272'))
        self.assertFalse(r['ok'], r)
        self.assertEqual(r['error']['code'], 'UI_JSON_INVALID')
        self.assertFalse(os.path.isfile(dst), 'fatal 的产物**不许**留在目标位置')
        self.assertTrue(r.get('withdrawn'), '生成期写出的 json 要撤回（并如实登记）：%s' % r)
        self.assertTrue(all(not os.path.isfile(p.split('（')[0]) for p in r['withdrawn']),
                        '撤回后不该还留文件：%s' % r['withdrawn'])
        self.assertTrue(r['uiDiagnostics'])

    def test_allow_unvalidated_lands_with_marker(self):
        dst = os.path.join(self.root, 'ui', 'main.json')
        with mock.patch.object(K.uic, 'compile_json', return_value=dict(FATAL_REPORT)):
            r = json.loads(K.flythings_html_to_json(HTML, output_json=dst, res='480x272',
                                                    allow_unvalidated=True))
        self.assertTrue(r.get('success'), r)
        self.assertTrue(r.get('uiUnvalidated'))
        self.assertTrue(os.path.isfile(r['jsonPath']), '强制放行时产物要真的落盘')
        self.assertTrue(any('allow_unvalidated' in w for w in (r.get('warnings') or [])))

    def test_clean_output_lands_and_reports_uicheck(self):
        dst = os.path.join(self.root, 'ui', 'main.json')
        r = json.loads(K.flythings_html_to_json(HTML, output_json=dst, res='480x272'))
        self.assertTrue(r.get('success'), r)
        self.assertTrue(os.path.isfile(r['jsonPath']), '合规产物要落盘：%s' % r.get('jsonPath'))
        self.assertIn('uiCheck', r)
        self.assertEqual(r['uiCheck']['fatal'], 0)
        self.assertFalse(r.get('uiUnvalidated'))
        self.assertTrue(all(os.path.isfile(p) for p in r['jsonPaths']))


class TestTranslateUiGate(_Base):

    def test_fatal_does_not_land(self):
        dst = os.path.join(self.root, 'ui', 'main.json')
        with mock.patch.object(K.uic, 'compile_json', return_value=dict(FATAL_REPORT)):
            r = json.loads(K.flythings_translate_ui(LVGL, out=dst, res='480x272'))
        self.assertFalse(r['ok'], r)
        self.assertEqual(r['error']['code'], 'UI_JSON_INVALID')
        self.assertFalse(os.path.isfile(dst), 'fatal 的迁移产物**不许**落盘')
        self.assertIsNone(r.get('jsonPath'))

    def test_allow_unvalidated_lands(self):
        dst = os.path.join(self.root, 'ui', 'main.json')
        with mock.patch.object(K.uic, 'compile_json', return_value=dict(FATAL_REPORT)):
            r = json.loads(K.flythings_translate_ui(LVGL, out=dst, res='480x272',
                                                    allow_unvalidated=True))
        # ⚠️ translate 成功时没有 `success` 键（实测）→ 判据落在 jsonPath/文件上
        self.assertEqual(r.get('jsonPath'), os.path.abspath(dst), r.get('jsonPath'))
        self.assertTrue(os.path.isfile(dst))
        self.assertTrue(r.get('uiUnvalidated'))

    def test_clean_output_lands(self):
        dst = os.path.join(self.root, 'ui', 'main.json')
        r = json.loads(K.flythings_translate_ui(LVGL, out=dst, res='480x272'))
        self.assertEqual(r.get('jsonPath'), os.path.abspath(dst), r)
        self.assertTrue(os.path.isfile(dst))
        self.assertIn('uiCheck', r)

    def test_dry_run_untouched(self):
        r = json.loads(K.flythings_translate_ui(LVGL, res='480x272', dry_run=True))
        self.assertEqual(r.get('dryRun'), True, r.get('dryRun'))
        self.assertIn('uiJson', r)
        self.assertIsNone(r.get('jsonPath'), 'dry_run 不许落盘')


class TestEditApplyGate(_Base):

    def setUp(self):
        super().setUp()
        self.json = os.path.join(self.root, 'ui', 'main.json')
        # ⚠️ 必须 indent=2：`ui_edit_apply` 有「标准缩进(2)」自检，indent=1 会被它拒绝写入
        U.write(self.json, json.dumps(PAGE, ensure_ascii=False, indent=2))
        self.before = io.open(self.json, encoding='utf-8').read()

    def _changes(self):
        return json.dumps({'file': 'main.json',
                           'props': {'textview__1': {'text': '改过了'}}})

    def test_fatal_rolls_back(self):
        with mock.patch.object(K.uic, 'compile_json', return_value=dict(FATAL_REPORT)):
            r = json.loads(K.flythings_ui_visual(action='edit_apply', project_root=self.root,
                                                 changes=self._changes(), pack=False))
        self.assertFalse(r['ok'], r)
        self.assertEqual(r['error']['code'], 'UI_JSON_INVALID')
        self.assertTrue(r.get('rolledBack'), '有 .bak 时必须回滚')
        self.assertEqual(io.open(self.json, encoding='utf-8').read(), self.before,
                         '回滚后 json 必须与改动前逐字节一致')

    def test_clean_edit_passes_with_uicheck(self):
        r = json.loads(K.flythings_ui_visual(action='edit_apply', project_root=self.root,
                                             changes=self._changes(), pack=False))
        self.assertNotEqual((r.get('error') or {}).get('code'), 'UI_JSON_INVALID')
        self.assertIn('uiCheck', r, r)
        self.assertNotEqual(io.open(self.json, encoding='utf-8').read(), self.before,
                            '正常改动要生效')

    def test_allow_unvalidated_keeps_edit(self):
        with mock.patch.object(K.uic, 'compile_json', return_value=dict(FATAL_REPORT)):
            r = json.loads(K.flythings_ui_visual(action='edit_apply', project_root=self.root,
                                                 changes=self._changes(), pack=False,
                                                 allow_unvalidated=True))
        self.assertNotEqual((r.get('error') or {}).get('code'), 'UI_JSON_INVALID')
        self.assertTrue(r.get('uiUnvalidated'))
        self.assertNotEqual(io.open(self.json, encoding='utf-8').read(), self.before)


if __name__ == '__main__':
    unittest.main()
