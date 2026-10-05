# -*- coding: utf-8 -*-
"""UI schema 注册表契约（ui_tools/ui_schema.json + ui_schema_loader.py）。

钉住六件事：
  ① 注册表可加载；控件 + 4 子结构齐全（与 check_all #14 的 26 类型键集合一致）
  ② 每个控件都有 id/caption/position 必填（listitem 无 id 为例外）
  ③ 所有 thumb 字段类型都是 thumb（对象型）；全注册表不存在「子盒字段类型=string」
     （子盒字段写成字符串 = 真机 ftu 加载无声挂死）
  ④ defaults() 产物过 type_check 零违规（每个控件/子结构都测）
  ⑤ check_all 4b：thumb 写成字符串必须 FAIL 且带 thumb；thumb 是对象但缺图必须通过
  ⑥ op flythings_ui_schema 走真实分发路径可路由（清单/指定控件/未知类型三形态）
"""
import io
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
        # 夹具必须随仓走（曾放在 gitignore 的 temp/，fresh clone 必挂 —— 违背 hermetic 判据）
        rc, sec = self._run_4b('tests/fixtures/abtest_b')
        self.assertNotEqual(rc, 0, 'thumb 字符串必须让 check_all 整体 FAIL')
        self.assertIn('[FAIL]', sec)
        self.assertIn('thumb', sec)
        self.assertIn('fatal', sec)

    def test_abtest_a_thumb_object_passes(self):
        rc, sec = self._run_4b('tests/fixtures/abtest_a')
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

    def test_child_rule_is_surfaced(self):
        """容器「子内容走哪条路」必须由 op 回出去。

        2026-10-05：本 op 以前只回 `container: true` —— 那半个真源正是「slidewindow 平铺子控件」
        假绿的来源（check_all #2 判 FAIL 而 ui_compile 判通过）。AI 查 schema 时就该看到口径。
        """
        r = U.jcall('flythings_ui_schema', {})
        types = {c['type']: c for c in r['controlTypes']}
        self.assertIn('items', types['slidewindow']['childRule'])
        self.assertIn('平铺', types['slidewindow']['childRule'])
        self.assertIn('window', types['pagewindow']['childRule'])
        self.assertIn('叶子', types['button']['childRule'])
        self.assertIn('不限', types['window']['childRule'])
        d = U.jcall('flythings_ui_schema', {'control_type': 'slidewindow'})
        self.assertEqual(d['children']['mode'], 'substructure')
        self.assertEqual(d['children']['key'], 'items')
        # include='fields' 档（生成器出口按它取）也要带上，否则那档又只剩 container:true
        f = U.jcall('flythings_ui_schema', {'control_type': 'slidewindow', 'include': 'fields'})
        self.assertIn('childRule', f)
        self.assertEqual(f['children']['key'], 'items')


class TestGeneratorFieldsAreRegistered(unittest.TestCase):
    """**我们自己发出去的字段，注册表必须认识**（2026-10-03 全仓对账后钉住）。

    背景：`ui_tools/html2json.py` 的 edittext 分支在 HTML 带 `data-password` /
    `data-password-char` 时会写 `isPassword` / `passwordChar`，
    `templates/ui_blocks/compose.py` 的 edittext 模板也恒写这两个；
    **但注册表（字段唯一真源）当时完全没有它们** → 后果是"生成器写了真源不知道的字段"：
    按需契约与派生表都不会提密码能力，AI 也就不知道 edittext 能配密码。

    第二批：把**全仓 ui json 实测用到的字段**按控件类型汇总后与注册表对账，
    又发现 22 个同样的缺口（`textview.backgroundColor` 实测 509 处、`button.fontSize` 290 处…），
    且 `ui_tools/json2img.py`（与真机截图对齐过 100% 的离线渲染器）也在读它们。
    这条用例把「生成器会写的键 ⊆ 注册表认识」钉住（同类缺口下次直接红）。
    """

    # 生成器会写、且必须被注册表认识的键 → {控件类型: {键: 值类型}}
    # 2026-10-03 第二批：按**全仓 ui json 实测对账**（`temp` 探针扫 52 个 ui json，
    # 按控件类型汇总"工程在用的字段"，与注册表比对）补进来的 22 个字段名 ——
    # button 13→24、textview 17→20、edittext 16→23、scrollwindow 6→7。
    EMITTED = {
        'edittext': {'isPassword': bool, 'passwordChar': str, 'beepEnable': bool,
                     'fontFamily': int, 'hintText': str, 'touchable': bool,
                     'rollEnable': bool, 'rollDirection': int,
                     'rollIntervalTime': int, 'rollStep': int},
        'button': {'fontSize': int, 'backgroundColor': int, 'backgroundPic': str,
                   'bold': bool, 'italic': bool, 'fontFamily': int,
                   'rollEnable': bool, 'rollDirection': int, 'rollIntervalTime': int,
                   'rollStep': int, 'textPosition': dict},
        'textview': {'backgroundColor': int, 'backgroundPic': str, 'textPosition': dict},
        'scrollwindow': {'touchable': bool},
    }

    def test_emitted_keys_exist_in_registry(self):
        import ui_schema_loader as us
        reg = us.load()
        for ctype, keys in self.EMITTED.items():
            fields = reg['controls'][ctype]['fields']
            for k in keys:
                self.assertIn(k, fields,
                              '%s 的 %s 是生成器会写的键，但注册表没有它（生成器写了真源不知道的字段）'
                              % (ctype, k))

    def test_password_fields_shape(self):
        import ui_schema_loader as us
        f = us.load()['controls']['edittext']['fields']
        self.assertEqual(f['isPassword']['type'], 'bool')
        self.assertFalse(f['isPassword']['required'], '密码框是可选字段')
        self.assertEqual(f['passwordChar']['type'], 'string')
        self.assertFalse(f['passwordChar']['required'])
        # 派生表要能带上它们：默认值要点列取自「显式 default 的标量字段」
        self.assertIn('default', f['isPassword'])
        self.assertIn('default', f['passwordChar'])

    def test_derived_table_mentions_password(self):
        """派生表（json-field-mandatory.md）必须把它们列出来 —— 否则 AI 读不到密码能力。"""
        p = os.path.join(U.BASE, 'knowledge', 'uicontrols', 'json-field-mandatory.md')
        txt = io.open(p, encoding='utf-8').read()
        row = [ln for ln in txt.splitlines() if ln.startswith('| edittext ')][0]
        self.assertIn('isPassword', row)
        self.assertIn('passwordChar', row)


class TestChildrenSpec(unittest.TestCase):
    """容器 → 子内容矩阵（`controls[].children`）：层级判据的唯一真源。

    为什么单列一段（2026-10-05 实测）：`container: true` 只说「能装子内容」、没说「子内容走哪条路」。
    check_all #2 与 ui_compile 曾据此各判一套 —— 同一份「slidewindow 平铺子按钮」的 json 一个红一个绿。
    跨 checker 同判的契约用例见 `tests/test_layer_rules.py`。
    """

    def test_structural_key_only_for_substructure_containers(self):
        self.assertEqual(us.structural_key('slidewindow'), 'items')
        self.assertEqual(us.structural_key('listview'), 'item')
        self.assertEqual(us.structural_key('radiogroup'), 'radiobuttons')
        self.assertEqual(us.structural_key('diagram'), 'infos')
        for t in ('window', 'pagewindow', 'scrollwindow', 'button', 'textview'):
            self.assertIsNone(us.structural_key(t), t)

    def test_child_control_types_three_states(self):
        self.assertIsNone(us.child_control_types('window'))                   # 不限（万能容器）
        self.assertEqual(us.child_control_types('pagewindow'), ('window',))   # 只装 window
        self.assertEqual(us.child_control_types('scrollwindow'), ('window',))
        for t in ('slidewindow', 'listview', 'radiogroup', 'diagram'):        # 结构容器：走结构键
            self.assertEqual(us.child_control_types(t), (), t)
        for t in ('button', 'textview', 'painter'):                           # 叶子
            self.assertEqual(us.child_control_types(t), (), t)

    def test_every_container_holds_a_children_spec(self):
        """写了 `container: true` 就必须给 `children` 段（否则消费方只能自己猜）。"""
        reg = us.load()['controls']
        containers = [t for t, e in reg.items() if e.get('container')]
        self.assertTrue(containers, '注册表里应当有容器')
        for t in containers:
            self.assertIsNotNone(us.children_spec(t),
                                 '%s 声明了 container 却没有 children 段（层级判据只能靠猜）' % t)

    def test_leaf_types_are_the_registry_remainder(self):
        leaves = set(us.leaf_types())
        reg = us.load()['controls']
        self.assertEqual(leaves, {t for t, e in reg.items() if not e.get('children')})
        self.assertIn('radiobutton', leaves)      # 单一 radiobutton 也不该有子控件

    def test_unknown_type_has_no_spec_and_does_not_raise(self):
        self.assertIsNone(us.children_spec('mywidget'))
        self.assertIsNone(us.structural_key('mywidget'))
        self.assertEqual(us.child_control_types('mywidget'), ())

    def test_malformed_children_spec_raises(self):
        """声明写坏了必须响（不许静默降级成叶子/不限 —— 那正是假绿的来源）。"""
        reg = us.load()
        saved = reg['controls']['window']['children']
        try:
            reg['controls']['window']['children'] = {'mode': 'bogus'}
            self.assertRaises(us.SchemaRegistryError, us.children_spec, 'window')
            reg['controls']['window']['children'] = {'mode': 'substructure'}
            self.assertRaises(us.SchemaRegistryError, us.children_spec, 'window')
        finally:
            reg['controls']['window']['children'] = saved


if __name__ == '__main__':
    unittest.main()
