# -*- coding: utf-8 -*-
"""LVGL → FlyThings ui json 翻译器契约（v0.27.171，op flythings_translate_ui v1）。

钉住五件事：
  ① 树/json 映射：lv_label→textview(L1)、lv_slider→seekbar(L1)、容器 lv_obj→window 嵌套
  ② D-xx 降级登记：L3（lv_chart）/L4（字号抬档、圆角出图）/未收录控件必登记，含源行+reason+action
  ③ 未识别调用进 unrecognized（不静默丢）；事件回调进 events
  ④ dry_run 不落盘；写盘模式产物可解析；同输入两跑产物逐字节一致（确定性）
  ⑤ 走真实分发路径（mcp_server.flythings_kb）：op 可路由、BAD_PARAMS/NO_SOURCE 形状正确
"""
import io
import json
import os
import tempfile
import unittest

import _util as U

FIXTURE = '''#include "lvgl.h"

static void build_panel(void) {
    lv_obj_t * scr = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(scr, lv_color_hex(0x17171B), 0);

    lv_obj_t * title = lv_label_create(scr);
    lv_label_set_text(title, "Thermostat");
    lv_obj_set_pos(title, 40, 24);
    lv_obj_set_size(title, 300, 32);
    lv_obj_set_style_text_color(title, lv_color_hex(0xECECF0), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_14, 0);

    lv_obj_t * card = lv_obj_create(scr);
    lv_obj_set_pos(card, 24, 80);
    lv_obj_set_size(card, 560, 200);
    lv_obj_set_style_radius(card, 12, 0);

    lv_obj_t * temp = lv_slider_create(card);
    lv_obj_set_size(temp, 400, 40);
    lv_obj_align(temp, LV_ALIGN_CENTER, 0, 0);
    lv_slider_set_range(temp, 16, 30);
    lv_slider_set_value(temp, 22, LV_ANIM_OFF);
    lv_obj_add_event_cb(temp, on_temp_change, LV_EVENT_VALUE_CHANGED, NULL);

    lv_obj_t * chart = lv_chart_create(scr);
    lv_obj_set_pos(chart, 40, 320);
    lv_obj_set_size(chart, 600, 240);
    lv_obj_set_style_shadow_width(chart, 20, 0);

    lv_obj_t * strange = lv_list_create(scr);
    lv_obj_set_pos(strange, 660, 24);
}
'''


def _run(args=None):
    a = {'source': FIXTURE, 'res': '800x480'}
    a.update(args or {})
    return U.jcall('flythings_translate_ui', a)


class TestTranslateMapping(unittest.TestCase):
    def setUp(self):
        self.r = _run()
        self.assertTrue(self.r['ok'], self.r)
        self.page = json.loads(self.r['uiJson'])

    def test_label_maps_textview_l1(self):
        tv = self.page['textview__1']
        self.assertEqual(tv['text'], 'Thermostat')
        self.assertEqual(tv['position'], {'left': 40, 'top': 24, 'width': 300, 'height': 32})
        self.assertEqual(tv['colorTab']['color0'], 0xECECF0)
        w = [x for x in self.r['widgets'] if x['var'] == 'title'][0]
        self.assertEqual(w['target'], 'textview')
        self.assertEqual(w['level'], 'L1')

    def test_font_floor_18_registers_downgrade(self):
        self.assertEqual(self.page['textview__1']['fontSize'], 18)   # 源 14px → 抬 18
        d = [x for x in self.r['downgrades'] if x['widget'] == 'title']
        self.assertTrue(d and '18px' in d[0]['reason'], self.r['downgrades'])
        self.assertEqual(d[0]['level'], 'L4')

    def test_container_nested_and_radius_downgrade(self):
        win = self.page['window__1']
        self.assertEqual(win['position']['left'], 24)
        self.assertIn('seekbar__1', win)                              # slider 挂进容器
        self.assertEqual(win['seekbar__1']['position']['left'], 80)   # align CENTER: (560-400)/2
        self.assertEqual(win['seekbar__1']['max'], 30)
        self.assertEqual(win['seekbar__1']['defProgress'], 22)
        d = [x for x in self.r['downgrades'] if x['widget'] == 'card']
        self.assertTrue(d and '圆角' in d[0]['reason'], self.r['downgrades'])

    def test_screen_bg_goes_to_page_root(self):
        self.assertEqual(self.page['backgroundColor'], 0x17171B)
        self.assertEqual(self.page['resolution'], {'width': 800, 'height': 480})

    def test_chart_l3_and_unrecognized_and_unknown_widget(self):
        d3 = [x for x in self.r['downgrades'] if x['lvType'] == 'lv_chart']
        self.assertTrue(d3 and d3[0]['level'] == 'L3' and d3[0]['line'] > 0)
        self.assertTrue(d3[0]['reason'] and d3[0]['action'])
        dq = [x for x in self.r['downgrades'] if x['lvType'] == 'lv_list']
        self.assertTrue(dq and dq[0]['level'] == 'L?', self.r['downgrades'])
        un = [x for x in self.r['unrecognized'] if 'shadow' in x['call']]
        self.assertTrue(un and un[0]['line'] > 0, self.r['unrecognized'])
        ids = [x['id'] for x in self.r['downgrades']]
        self.assertEqual(ids, ['D-%02d' % (i + 1) for i in range(len(ids))])   # 连续编号

    def test_events_recorded_not_dropped(self):
        ev = [x for x in self.r['events'] if x['callback'] == 'on_temp_change']
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]['event'], 'LV_EVENT_VALUE_CHANGED')
        self.assertIn('SkTemp', ev[0]['flythings'])

    def test_deterministic_same_input_same_json(self):
        r2 = _run()
        self.assertEqual(self.r['uiJson'], r2['uiJson'])
        self.assertEqual(self.r['downgrades'], r2['downgrades'])


class TestTranslateIoContract(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        tmp = tempfile.mkdtemp(prefix='mcp_translate_')
        out = os.path.join(tmp, 'ui', 'main.json')
        r = _run({'out': out, 'dry_run': True})
        self.assertTrue(r['ok'])
        self.assertTrue(r['dryRun'])
        self.assertFalse(os.path.exists(out), 'dry_run=True 不许落盘')
        U.cleanup(tmp)

    def test_write_mode_produces_parseable_json(self):
        tmp = tempfile.mkdtemp(prefix='mcp_translate_')
        out = os.path.join(tmp, 'ui', 'main.json')
        r = _run({'out': out, 'dry_run': False})
        self.assertTrue(r['ok'], r)
        self.assertEqual(os.path.abspath(out), r['jsonPath'])
        self.assertIn(os.path.abspath(out), r.get('affectedFiles', []))
        page = json.load(io.open(out, encoding='utf-8'))
        self.assertIn('textview__1', page)
        self.assertNotIn('uiJson', r)          # 写盘模式不回大字段
        U.cleanup(tmp)

    def test_write_without_out_is_bad_params(self):
        r = _run({'dry_run': False, 'out': ''})
        self.assertFalse(r['ok'])
        self.assertEqual(r['error']['code'], 'BAD_PARAMS')

    def test_missing_file_and_no_widgets(self):
        r = U.jcall('flythings_translate_ui', {'source': 'no_such_file_zzz.c'})
        self.assertFalse(r['ok'])
        self.assertEqual(r['error']['code'], 'NO_SOURCE')
        r2 = U.jcall('flythings_translate_ui', {'source': 'int main(void) { return 0; }\n// lv_'})
        self.assertFalse(r2['ok'])
        self.assertEqual(r2['error']['code'], 'NO_WIDGETS')
        r3 = U.jcall('flythings_translate_ui', {'source': FIXTURE, 'res': 'abc'})
        self.assertFalse(r3['ok'])
        self.assertEqual(r3['error']['code'], 'BAD_PARAMS')

    def test_dispatcher_routes_and_envelope(self):
        cat = U.jcall('list')
        self.assertIn('flythings_translate_ui', [o['op'] for o in cat['ops']])
        import kb_tools
        self.assertIn('flythings_translate_ui', kb_tools.OP_NAMES)
        r = _run()
        self.assertEqual(r['op'], 'flythings_translate_ui')
        self.assertIn('warnings', r)
        sa = r.get('seeAlso') or []
        self.assertIn('knowledge/devflow/translate-ui-lvgl.md', sa)
        self.assertIn('knowledge/devflow/platform-translate.md', sa)

    def test_pure_black_rewritten_to_010101(self):
        r = U.jcall('flythings_translate_ui', {
            'source': 'lv_obj_t * s = lv_obj_create(NULL);\n'
                      'lv_obj_t * b = lv_btn_create(s);\n'
                      'lv_obj_set_style_bg_color(b, lv_color_hex(0x000000), 0);\n'})
        self.assertTrue(r['ok'])
        btn = json.loads(r['uiJson'])['button__1']
        self.assertEqual(btn['bgColorTab']['color0'], 0x010101)   # 铁律：纯黑不写 0


class TestSchemaCompleteness(unittest.TestCase):
    """schema 全集显式化（v0.27.172 发射层重写；真源 = demos ftu 反解 +
    json-field-mandatory.md + ui_blocks/examples）：五槽色表 / thumb 子盒 /
    按钮文本内联 / 缺图剥除，缺一会真机 ftu 加载死循环。"""

    def test_textview_full_field_set(self):
        tv = json.loads(_run()['uiJson'])['textview__1']
        for k in ('bold', 'italic', 'visible', 'rollEnable', 'rollDirection',
                  'rollIntervalTime', 'rollStep', 'bgColorTab'):
            self.assertIn(k, tv, k)
        self.assertEqual(sorted(tv['colorTab'].keys()),
                         ['color0', 'color1', 'color2', 'color3', 'color4'])
        self.assertEqual(tv['colorTab']['color1'], -1)            # 未用色态恒 -1
        self.assertEqual(sorted(tv['bgColorTab'].keys()),
                         ['color0', 'color1', 'color2', 'color3', 'color4'])

    def test_seekbar_thumb_is_subbox_and_pics_stripped(self):
        r = _run()
        sk = json.loads(r['uiJson'])['window__1']['seekbar__1']
        self.assertIsInstance(sk['thumb'], dict)                  # 字符串旧式已废
        self.assertEqual(sk['thumb']['size'], {'width': 0, 'height': 0})
        self.assertEqual(sk['backgroundPic'], '')                 # 缺图 → 剥除（不引用）
        self.assertEqual(sk['progressPic'], '')
        acts = [(a['field'], a['action']) for a in r['imageActions']]
        self.assertIn(('backgroundPic', 'stripped'), acts)
        self.assertIn(('thumb.normalPic', 'stripped'), acts)
        self.assertTrue(all('死循环' in r['imageRule'] for _ in (0,)))
        self.assertGreater(r['summary']['imageStripped'], 0)

    def test_button_label_inlined_not_separate_textview(self):
        r = U.jcall('flythings_translate_ui', {
            'source': 'lv_obj_t * s = lv_obj_create(NULL);\n'
                      'lv_obj_t * b = lv_btn_create(s);\n'
                      'lv_obj_set_pos(b, 10, 20);\n'
                      'lv_obj_set_size(b, 120, 48);\n'
                      'lv_obj_t * t = lv_label_create(b);\n'
                      'lv_label_set_text(t, "OK");\n'
                      'lv_obj_set_style_text_color(t, lv_color_hex(0xFF0000), 0);\n'})
        self.assertTrue(r['ok'])
        page = json.loads(r['uiJson'])
        btn = page['button__1']
        self.assertEqual(btn['text'], 'OK')                       # 内联，D-03 变通废止
        self.assertEqual(btn['alignment'], 5)                     # IDE 新编码居中
        self.assertEqual(btn['longClickTimeOut'], -1)
        self.assertEqual(btn['longClickIntervalTime'], -1)
        self.assertTrue(btn['visible'])
        self.assertEqual(btn['colorTab']['color0'], 0xFF0000)     # label 文字色进 colorTab
        self.assertEqual(btn['colorTab']['color1'], 0xFF0000)     # 按下态跟色
        self.assertNotIn('textview__1', page)                     # 不再有独立 label 控件
        w = [x for x in r['widgets'] if x['var'] == 't'][0]
        self.assertEqual(w['target'], 'button.text(inline)')

    def test_switch_pictab_stripped_to_empty(self):
        r = U.jcall('flythings_translate_ui', {
            'source': 'lv_obj_t * s = lv_obj_create(NULL);\n'
                      'lv_obj_t * sw = lv_switch_create(s);\n'})
        page = json.loads(r['uiJson'])
        self.assertEqual(page['button__1']['picTab'], {})         # sw_*.png 未生成 → 剥除
        self.assertTrue(any(a['action'] == 'stripped' and 'picTab' in a['field']
                            for a in r['imageActions']))

    def test_gen_placeholders_writes_png_into_ui_images(self):
        tmp = tempfile.mkdtemp(prefix='mcp_translate_')
        out = os.path.join(tmp, 'ui', 'main.json')
        r = _run({'out': out, 'dry_run': False, 'gen_placeholders': True})
        self.assertTrue(r['ok'], r)
        page = json.load(io.open(out, encoding='utf-8'))
        sk = page['window__1']['seekbar__1']
        self.assertEqual(sk['backgroundPic'], 'images/sk_track_400x40.png')   # 引用保留
        img = os.path.join(tmp, 'ui', 'images', 'sk_track_400x40.png')
        self.assertTrue(os.path.isfile(img))
        # 图 == 盒（铁律 #1）：占位图尺寸 = 控件盒 400x40（源 set_size 400x40），不是文件名尺寸
        head = io.open(img, 'rb').read(33)
        self.assertEqual(head[:8], b'\x89PNG\r\n\x1a\n')
        w, h = int.from_bytes(head[16:20], 'big'), int.from_bytes(head[20:24], 'big')
        self.assertEqual((w, h), (400, 40))
        self.assertIn(img, r['affectedFiles'])
        self.assertGreater(r['summary']['imageGenerated'], 0)
        U.cleanup(tmp)

    def test_existing_image_ref_kept(self):
        tmp = tempfile.mkdtemp(prefix='mcp_translate_')
        os.makedirs(os.path.join(tmp, 'ui', 'images'))
        io.open(os.path.join(tmp, 'ui', 'images', 'sk_track_400x40.png'), 'wb').write(b'x')
        r = _run({'out': os.path.join(tmp, 'ui', 'main.json'), 'dry_run': False})
        page = json.load(io.open(os.path.join(tmp, 'ui', 'main.json'), encoding='utf-8'))
        sk = page['window__1']['seekbar__1']
        self.assertEqual(sk['backgroundPic'], 'images/sk_track_400x40.png')   # 已落盘 → 保留
        self.assertEqual(sk['progressPic'], '')                               # 未落盘 → 仍剥除
        U.cleanup(tmp)


if __name__ == '__main__':
    unittest.main()
