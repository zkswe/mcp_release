# -*- coding: utf-8 -*-
"""UI schema 注册表契约（ui_tools/ui_schema.json + ui_schema_loader.py）。

钉住六件事：
  ① 注册表可加载；控件 + 4 子结构齐全（与 check_all #14 的 26 类型键集合一致）
  ② 每个控件都有 id/caption/position 必填（listitem 无 id 为例外）
  ③ 所有 thumb 字段类型都是 thumb（对象型）；全注册表不存在「子盒字段类型=string」
     （thumb 写成字符串 = 真机 ftu 加载无声挂死，A/B 实测 V85X iMirror 2026-10-02）
  ④ defaults() 产物过 type_check 零违规（每个控件/子结构都测）
  ⑤ check_all 4b：temp/abtest_b（thumb 字符串）报 FAIL 含 thumb；
     temp/abtest_a（thumb 对象+缺图）类型检查通过
  ⑥ op flythings_ui_schema 走真实分发路径可路由（清单/指定控件/未知类型三形态）
"""
import json
import os
import subprocess
import sys
import unittest

import _util as U

BASE = U.BASE
sys.path.insert(0, os.path.join(BASE, 'ui_tools'))
import ui_schema_loader as us                     # noqa: E402

EXPECTED_CONTROLS = {
    'textview', 'button', 'window', 'edittext', 'seekbar', 'listview', 'circlebar',
    'slidewindow', 'digitalclock', 'qrcode', 'videoview', 'cameraview', 'painter',
    'pointer', 'diagram', 'pagewindow', 'scrollwindow', 'radiogroup', 'radiobutton',
    'checkbox', 'imageanim', 'slidetext',
}
EXPECTED_SUBS = {'listitem', 'subitem', 'wave', 'slideitem'}


class TestRegistryLoad(unittest.TestCase):
    def test_loads_and_caches(self):
        reg = us.load()
        self.assertIs(reg, us.load())              # 缓存：同一对象
        for key in ('page', 'sharedTypes', 'controls', 'subStructures', 'valueRules'):
            self.assertIn(key, reg, key)

    def test_all_types_present(self):
        self.assertEqual(set(us.control_types()), EXPECTED_CONTROLS)
        self.assertEqual(set(us.sub_structure_types()), EXPECTED_SUBS)
        # 与 check_all #14 的 26 类型键集合一一对应（21+1 控件 radiobutton + 4 子结构）
        self.assertEqual(len(us.known_types()), 26)

    def test_missing_file_raises_with_path(self):
        # 容错口径：文件缺失 → 带路径的异常，不静默
        real = us.SCHEMA_PATH
        try:
            us.SCHEMA_PATH = os.path.join(BASE, 'ui_tools', 'no_such_schema_zzz.json')
            us.reload()
            self.fail('缺失注册表必须抛异常')
        except us.SchemaRegistryError as e:
            self.assertIn('no_such_schema_zzz.json', str(e))
        finally:
            us.SCHEMA_PATH = real
            us.reload()


class TestFieldSanity(unittest.TestCase):
    def test_every_control_has_id_caption_position(self):
        for t in us.control_types():
            req = set(us.required_fields(t))
            for k in ('id', 'caption', 'position'):
                self.assertIn(k, req, '%s 缺必填 %s' % (t, k))

    def test_listitem_exception_no_id(self):
        self.assertNotIn('id', us.required_fields('listitem'))
        self.assertIn('position', us.required_fields('listitem'))

    def test_thumb_fields_are_object_type(self):
        reg = us.load()
        n_thumb = 0
        for section in ('controls', 'subStructures'):
            for tname, entry in reg[section].items():
                for fname, spec in (entry.get('fields') or {}).items():
                    if fname == 'thumb':
                        n_thumb += 1
                        self.assertEqual(spec['type'], 'thumb',
                                         '%s.thumb 类型必须是 thumb（对象型）' % tname)
                    # ⛔ 子盒字段（sharedTypes 对象型）绝不许声明成 string —— 历史挂死真凶
                    if fname in ('thumb', 'position', 'size', 'point', 'range',
                                 'colorTab', 'picTab', 'bgColorTab', 'iconBox',
                                 'iconPosition', 'textPosition', 'fixedPoint',
                                 'pointerSize', 'rotationPoint', 'region',
                                 'xAxisRange', 'yAxisRange'):
                        self.assertNotEqual(spec['type'], 'string',
                                            '%s.%s 子盒字段不许声明成 string' % (tname, fname))
        self.assertGreaterEqual(n_thumb, 2)        # seekbar + circlebar


class TestDefaultsPassTypeCheck(unittest.TestCase):
    def test_defaults_zero_violations(self):
        for t in us.known_types():
            d = us.defaults(t)
            vios = [v for v in us.type_check(t, d) if v['level'] != 'warn']
            self.assertEqual(vios, [], '%s: %s' % (t, vios[:3]))

    def test_type_check_levels(self):
        # fatal：thumb 写成字符串
        v = us.type_check('seekbar', {'thumb': 'images/x.png'})
        self.assertEqual([x['level'] for x in v], ['fatal'])
        self.assertIn('挂死', v[0]['msg'])
        # error：thumb 是 dict 但缺 requiredKeys
        v = us.type_check('seekbar', {'thumb': {'size': {'width': 1, 'height': 1}}})
        self.assertTrue(v and all(x['level'] == 'error' for x in v))
        # error：标量类型不符（bool 不许混 int）
        v = us.type_check('textview', {'fontSize': True})
        self.assertEqual([x['level'] for x in v], ['error'])
        # warn：未知键不报错只收集
        v = us.type_check('textview', {'someFutureKey': 1})
        self.assertEqual([x['level'] for x in v], ['warn'])


class TestCheckAll4b(unittest.TestCase):
    """直接子进程跑 ui_tools/check_all.py <dir>，断 4b 节输出（其它节 FAIL 与本契约无关）。"""

    def _run_4b(self, proj):
        r = subprocess.run([sys.executable, os.path.join(BASE, 'ui_tools', 'check_all.py'),
                            os.path.join(BASE, proj)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
        out = r.stdout.decode('utf-8', 'replace')
        self.assertIn('== 4b.', out, '4b 节必须存在: %s' % out[-500:])
        sec = out.split('== 4b.', 1)[1].split('== 5.', 1)[0]
        return r.returncode, sec

    def test_abtest_b_thumb_string_fails(self):
        rc, sec = self._run_4b('temp/abtest_b')
        self.assertNotEqual(rc, 0, 'thumb 字符串必须让 check_all 整体 FAIL')
        self.assertIn('[FAIL]', sec)
        self.assertIn('thumb', sec)
        self.assertIn('fatal', sec)

    def test_abtest_a_thumb_object_passes(self):
        rc, sec = self._run_4b('temp/abtest_a')
        self.assertIn('[PASS]', sec)
        self.assertNotIn('[FAIL]', sec, sec)
        self.assertIn('全部合规', sec)


class TestUiSchemaOp(unittest.TestCase):
    def test_dispatcher_routes(self):
        import kb_tools
        self.assertIn('flythings_ui_schema', kb_tools.OP_NAMES)
        cat = U.jcall('list')
        self.assertIn('flythings_ui_schema', [o['op'] for o in cat['ops']])

    def test_list_and_detail(self):
        r = U.jcall('flythings_ui_schema', {})
        self.assertTrue(r['ok'], r)
        types = {c['type']: c for c in r['controlTypes']}
        self.assertEqual(set(types), EXPECTED_CONTROLS)
        self.assertTrue(types['seekbar']['interactive'])
        self.assertFalse(types['textview']['interactive'])
        self.assertTrue(types['window']['container'])
        r2 = U.jcall('flythings_ui_schema', {'control_type': 'seekbar'})
        self.assertTrue(r2['ok'], r2)
        self.assertEqual(r2['fields']['thumb']['type'], 'thumb')
        self.assertIn('thumb', r2['requiredFields'])
        self.assertIn('thumb', r2['sharedTypes'])          # 适用 sharedTypes 定义
        self.assertIn('subboxType', r2['valueRules'])      # valueRules 随行
        self.assertEqual(r2['defaults']['thumb'],
                         {'size': {'width': 0, 'height': 0}, 'normalPic': '', 'pressedPic': ''})
        r3 = U.jcall('flythings_ui_schema', {'control_type': 'nope_zzz'})
        self.assertFalse(r3['ok'])
        self.assertEqual(r3['error']['code'], 'NO_HIT')


if __name__ == '__main__':
    unittest.main()
