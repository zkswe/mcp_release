# -*- coding: utf-8 -*-
"""跨框架控件映射能力契约（v0.27.73）：

口径（钟工 2026-09-16）：**有一一映射的控件走「映射能力」（机读索引 + op），不写散文；
平台真缺的能力才做自定义控件包 components/ui_v1/<源控件名>/**。本文件钉住三件事：
  ① 数据文件 mcp_control_map.json 的完整性（六个源框架 / 条数 / 级别取值 / 片段可解析 / L3 必须给 ref）
  ② op flythings_map_control 的外部契约（命中形状 / 模糊匹配 / source 限定 / NO_HIT / BAD_SOURCE / BAD_PARAMS）
  ③ tab 类映射指向 _mapping/TabView（有平台对应控件 → 不算控件包）
"""
import io
import json
import os
import sys
import unittest

import _util as U

SRC_DIR = U.BASE
MAPS = ('lvgl', 'qt', 'android', 'miniprogram', 'emwin', 'mfc')
LEVELS = ('L1', 'L2', 'L3', 'L4', 'L5')


def _data():
    with io.open(os.path.join(SRC_DIR, 'mcp_control_map.json'), encoding='utf-8') as f:
        return json.load(f)


class TestControlMapData(unittest.TestCase):
    def test_six_sources_and_min_size(self):
        d = _data()
        self.assertEqual(sorted(d['sources'].keys()), sorted(MAPS))
        for s, arr in d['sources'].items():
            self.assertGreaterEqual(len(arr), 15, '%s 条数太少（要求 15~30+）' % s)
            self.assertLessEqual(len(arr), 60, '%s 条数异常' % s)
        total = sum(len(a) for a in d['sources'].values())
        self.assertGreaterEqual(total, 100, '合计不足 100 条（当前 %d）' % total)

    def test_entry_shape_and_levels(self):
        d = _data()
        targets = d['targets']
        for s, arr in d['sources'].items():
            for e in arr:
                tag = '%s/%s' % (s, e['name'])
                self.assertTrue(e['name'], tag)
                self.assertIsInstance(e['aliases'], list, tag)
                self.assertIn(e['level'], LEVELS, tag)
                self.assertIn(e['target'], targets, tag + ' 的 target 未在 targets 登记')
                self.assertIsInstance(e['notes'], str, tag)
                self.assertIsInstance(e['json'], str, tag)
                # L1/L2 的片段必须可直接粘（能解析）；L3 必须给 ref 指向 ui_v1
                if e['json']:
                    json.loads(e['json'])
                if e['level'] in ('L1', 'L2') and targets[e['target']]['json']:
                    self.assertTrue(e['json'], tag + ' 的 L1/L2 缺可粘贴 json 片段')
                if e['level'] in ('L3', 'L4', 'L5'):
                    self.assertTrue(e['notes'], tag + ' 的 L3/L4/L5 必须写替代建议/降级点')
                if e['level'] == 'L3':
                    self.assertIn('components/ui_v1/', e['ref'], tag + ' 的 L3 必须给 ref 指向 ui_v1 包')

    def test_every_target_snippet_parses_and_captions(self):
        d = _data()
        for k, v in d['targets'].items():
            self.assertIn('caption', v, k)
            self.assertIn('ptr', v, k)
            if v['json']:
                obj = json.loads(v['json'])
                self.assertTrue(any(str(x).startswith(('window', 'button', 'textview', 'edittext',
                                                        'listview', 'seekbar', 'radiogroup',
                                                        'scrollwindow', 'pagewindow', 'slidewindow',
                                                        'painter', 'diagram', 'circlebar', 'pointer',
                                                        'digitalclock', 'imageanim', 'qrcode',
                                                        'videoview', 'cameraview', 'slidetext'))
                                    for x in obj.keys()),
                                '%s 的片段键名不像控件键' % k)

    def test_json_snippets_follow_mandatory_fields(self):
        """关键几类控件的必写字段必须出现在片段里（对齐 knowledge/uicontrols/json-field-mandatory.md）。"""
        need = {
            'seekbar': ('id', 'caption', 'position', 'backgroundColor', 'defProgress', 'max',
                        'orientation', 'thumb', 'touchable', 'visible'),
            'listview': ('id', 'caption', 'position', 'cols', 'rows', 'cols', 'item',
                         'hasScrollbar', 'dragMaxDis', 'edgeEffect', 'touchable'),
            'pagewindow': ('dragMaxDis', 'orientation', 'edgeEffect', 'rollSpeed'),
            'edittext': ('id', 'caption', 'position', 'bgColorTab', 'bold', 'colorTab', 'fontSize',
                         'textType'),
        }
        d = _data()
        for t, keys in need.items():
            js = d['targets'][t]['json']
            for k in keys:
                self.assertIn('"%s"' % k, js, 'targets.%s 片段缺必写字段 %s' % (t, k))


class TestMapControlOp(unittest.TestCase):
    def test_hit_shape(self):
        r = U.jcall('flythings_map_control', {'query': 'lv_slider'})
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['source'], 'lvgl')
        self.assertEqual(r['name'], 'lv_slider')
        self.assertEqual(r['target'], 'seekbar')
        self.assertEqual(r['level'], 'L1')
        self.assertTrue(r['levelName'])
        json.loads(r['json'])                       # 片段可直接粘
        self.assertIn('ptr', r['control'])
        self.assertEqual(r['warnings'], [])

    def test_fuzzy_and_case_insensitive(self):
        for q, want in (('LV_SLIDER', 'seekbar'), ('lv-slider', 'seekbar'),
                        ('RecyclerView', 'listview'), ('recyclerview', 'listview')):
            r = U.jcall('flythings_map_control', {'query': q})
            self.assertTrue(r['ok'], q)
            self.assertEqual(r['target'], want, q)

    def test_source_filter(self):
        r = U.jcall('flythings_map_control', {'query': 'slider', 'source': 'qt'})
        self.assertTrue(r['ok'])
        self.assertEqual(r['source'], 'qt')
        self.assertEqual(r['name'], 'QSlider')
        bad = U.jcall('flythings_map_control', {'query': 'slider', 'source': 'wx'})
        self.assertFalse(bad['ok'])
        self.assertEqual(bad['error']['code'], 'BAD_SOURCE')
        self.assertIn('lvgl', bad['sources'])

    def test_tabview_maps_to_pagewindow_mapping_not_package(self):
        r = U.jcall('flythings_map_control', {'query': 'lv_tabview'})
        self.assertEqual(r['target'], 'pagewindow')
        self.assertEqual(r['level'], 'L1')
        self.assertIn('_mapping/TabView', r['ref'])

    def test_l3_points_to_ui_v1_package(self):
        r = U.jcall('flythings_map_control', {'query': 'lv_chart'})
        self.assertEqual(r['level'], 'L3')
        self.assertIn('components/ui_v1/Chart', r['ref'])

    def test_no_hit_and_bad_params(self):
        r = U.jcall('flythings_map_control', {'query': 'zzz_not_a_control'})
        self.assertFalse(r['ok'])
        self.assertEqual(r['error']['code'], 'NO_HIT')
        self.assertIn('components/ui_v1', r['error']['hint'])
        self.assertTrue(r['gapPolicy']['levels'])
        empty = U.jcall('flythings_map_control', {'query': '   '})
        self.assertFalse(empty['ok'])
        self.assertEqual(empty['error']['code'], 'BAD_PARAMS')

    def test_still_34_plus_ops_and_registered(self):
        import kb_tools
        self.assertIn('flythings_map_control', kb_tools.OP_NAMES)
        cat = U.jcall('list')
        self.assertIn('flythings_map_control', [o['op'] for o in cat['ops']])
