# -*- coding: utf-8 -*-
"""层级判据（容器 → 子内容）**唯一真源**契约：`ui_schema.json#controls[].children`。

背景（2026-10-05 实测，本文件就是那次事故的判据）：同一份「`slidewindow` 平铺子按钮」的 json，
`check_all` #2 判 **FAIL**、`ui_compile` 判 **「编译式验收通过」**（假绿）——因为后者按
`controls[].container` 放行，而 `container: true` 只说了「能装子内容」、**没说子内容走哪条路**。
真机出处：`templates/DemoControls_V85X/ui/main.json`（7 个磁贴按钮直挂 slidewindow 下）。

本文件钉住三件事：
  ① 注册表 children 段派生出的层级表 == 文档口径（结构键矩阵 / 数组归属 / 叶子集）
     —— 口径散文见 `knowledge/uicontrols/json-layer-rules.md`；
  ② `check_all` #2 与 `ui_compile` TREE001-004 **同判**（同批 fixture 一起红、一起绿）；
  ③ 错法注回去必须变红（自证：坏例报、修法不报）。
"""
import json
import os
import sys
import unittest

# 让 `python -m unittest tests.test_layer_rules` 这一形态也能跑：同目录其它模块都依赖
# `discover -s tests` / `scripts/run_tests.py` 把 tests/ 加进 sys.path（裸点号导入时不会加）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _util as U                            # noqa: E402

BASE = U.BASE
sys.path.insert(0, os.path.join(BASE, 'ui_tools'))
import check_all as C                        # noqa: E402
import ui_compile as UC                      # noqa: E402
import ui_schema_loader as us                # noqa: E402

# 文档口径（json-layer-rules.md 第 2/3/4 条 + 第 5 条）——**故意写死在这里当基准**：
# 注册表若被改成另一套矩阵，本文件必须红（否则「真源」可以被人悄悄改掉口径）。
DOC_STRUCTURAL = {'listview': 'item', 'slidewindow': 'items',
                  'radiogroup': 'radiobuttons', 'diagram': 'infos'}
DOC_ARRAY_OWNER = {'items': 'slidewindow', 'infos': 'diagram',
                   'radiobuttons': 'radiogroup', 'subItem': 'listview'}
DOC_ONLY_WINDOW = ('pagewindow', 'scrollwindow')
# 2026-10-05 起叶子集由注册表派生（比旧硬编码 14 类多 radiobutton —— 它本来就不该有子控件）
LEGACY_LEAF_14 = {'textview', 'button', 'edittext', 'seekbar', 'circlebar', 'checkbox',
                  'slidetext', 'cameraview', 'painter', 'pointer', 'digitalclock', 'qrcode',
                  'videoview', 'imageanim'}


def ctrl(t, caption, cid, **over):
    """必填键全集控件（字段来自注册表 defaults()，本文件不抄字段表）。"""
    d = us.defaults(t)
    d.update({'id': cid, 'caption': caption,
              'position': {'left': 0, 'top': 0, 'width': 100, 'height': 40}})
    d.update(over)
    return d


def page(**ctrls):
    p = {'id': 0, 'resolution': {'width': 1024, 'height': 600},
         'position': {'left': 0, 'top': 0, 'width': 1024, 'height': 600},
         'backgroundColor': 8421504}
    p.update(ctrls)
    return p


def slideitem(text='i'):
    return {'colorTab': {'color0': 0xFFFFFF, 'color1': -1, 'color2': -1,
                         'color3': -1, 'color4': -1}, 'picTab': {}, 'text': text}


# ---------------------------------------------------------------- ① 注册表 → 层级表
class TestRegistryDerivedMatrix(unittest.TestCase):
    def test_structural_keys_match_documented_matrix(self):
        """结构键矩阵（哪个容器子内容走哪个结构键）必须等于文档口径。"""
        self.assertEqual(us.structural_containers(), DOC_STRUCTURAL)

    def test_array_owners_match_documented_matrix(self):
        """数组子结构归属（items/infos/radiobuttons/subItem）必须等于文档口径。"""
        self.assertEqual(us.structural_array_keys(), DOC_ARRAY_OWNER)

    def test_only_window_containers(self):
        """pagewindow/scrollwindow 只装 window（其它容器不受限或走结构键）。"""
        for t in DOC_ONLY_WINDOW:
            self.assertEqual(us.child_control_types(t), ('window',), t)
        self.assertIsNone(us.child_control_types('window'))       # 万能容器：不限
        for t in DOC_STRUCTURAL:
            self.assertEqual(us.child_control_types(t), (), '%s 应不许子控件键' % t)

    def test_container_flag_and_children_spec_agree(self):
        """`container: true` 与 `children` 声明不许各说一套（两份真源就是这次事故的根因）。"""
        reg = us.load()['controls']
        bad = [(t, bool(e.get('container')), bool(e.get('children')))
               for t, e in reg.items() if bool(e.get('container')) != bool(e.get('children'))]
        self.assertEqual(bad, [], '这些控件的 container 与 children 不一致：%s' % bad)

    def test_leaf_types_is_registry_derived(self):
        """叶子集 = 无 children 声明的已注册控件；旧硬编码 14 类是其子集（新增 radiobutton）。"""
        leaves = set(us.leaf_types())
        self.assertTrue(LEGACY_LEAF_14 <= leaves, LEGACY_LEAF_14 - leaves)
        self.assertIn('radiobutton', leaves)
        self.assertEqual(leaves, {t for t, e in us.load()['controls'].items() if not e.get('children')})

    def test_unknown_type_has_no_children_spec(self):
        """注册表外类型（自研控件）没有 children 声明、也不抛异常（层级判据跳过它）。"""
        self.assertIsNone(us.children_spec('mywidget'))
        self.assertIsNone(us.structural_key('mywidget'))

    def test_malformed_children_spec_raises(self):
        """声明本身坏了必须响（不静默降级成「叶子」或「不限」）。"""
        reg = us.load()
        saved = reg['controls']['window'].get('children')
        try:
            reg['controls']['window']['children'] = {'mode': 'bogus'}
            with self.assertRaises(us.SchemaRegistryError):
                us.children_spec('window')
            reg['controls']['window']['children'] = {'mode': 'substructure'}   # 缺 key
            with self.assertRaises(us.SchemaRegistryError):
                us.children_spec('window')
        finally:
            reg['controls']['window']['children'] = saved
        self.assertEqual(us.structural_key('window'), None)      # 复原


# ---------------------------------------------------------------- ② 两份 check 同判
class TestTwoCheckersAgree(unittest.TestCase):
    """同一批 fixture：check_all #2 与 ui_compile TREE* 必须一起红 / 一起绿。"""

    def setUp(self):
        self.tmp = U.project()
        os.makedirs(os.path.join(self.tmp, 'resources', 'images'), exist_ok=True)

    def tearDown(self):
        U.cleanup(self.tmp)

    def both(self, name, obj):
        """→ (check_all 问题列表, ui_compile 的 TREE 诊断列表)。"""
        fp = os.path.join(self.tmp, 'ui', name)
        U.write(fp, json.dumps(obj, ensure_ascii=False, indent=1))
        layer = C._layer_problems(obj)
        rep = UC.compile_json(fp, project_root=self.tmp)
        trees = [d for d in rep['diagnostics'] if d['rule'].startswith('TREE')]
        return layer, trees

    def assert_agree(self, name, obj, expect_red):
        layer, trees = self.both(name, obj)
        self.assertEqual(bool(layer), bool(trees),
                         '%s：check_all=%s 而 ui_compile=%s' % (name, layer, trees))
        self.assertEqual(bool(layer), expect_red,
                         '%s：期望 %s，实际 check_all=%s' % (name, '红' if expect_red else '绿', layer))
        return layer, trees

    def test_flat_children_in_structural_container(self):
        """真机事故形态：slidewindow 平铺 button（改前 check_all 红 / ui_compile 绿）。"""
        obj = page(slidewindow__1=ctrl('slidewindow', 'menu', 30001,
                                       button__100=ctrl('button', 'b1', 20001, text='x')))
        layer, trees = self.assert_agree('flat.json', obj, True)
        self.assertIn('TREE002', [d['rule'] for d in trees])
        self.assertTrue(any('平铺子控件键' in p for p in layer), layer)

    def test_legal_forms_are_green(self):
        """合法形态：window 装 button / slidewindow 走 items / pagewindow 装 window。"""
        obj = page(window__1=ctrl('window', 'w', 110001, button__2=ctrl('button', 'b', 20002, text='x')),
                   slidewindow__1=ctrl('slidewindow', 'sw', 30001, items=[slideitem()]),
                   pagewindow__2=ctrl('pagewindow', 'pw', 31002,
                                      window__3=ctrl('window', 'w3', 110003)))
        self.assert_agree('legal.json', obj, False)

    def test_leaf_with_child(self):
        obj = page(button__1=ctrl('button', 'b', 20001, text='x',
                                  textview__2=ctrl('textview', 't', 50002, text='y')))
        layer, trees = self.assert_agree('leaf.json', obj, True)
        self.assertIn('TREE001', [d['rule'] for d in trees])
        self.assertTrue(any('叶子控件含子控件键' in p for p in layer), layer)

    def test_only_window_violation(self):
        """pagewindow/scrollwindow 只装 window：两个分支（缺 / 混进别的）都要两边同措辞。"""
        for t in DOC_ONLY_WINDOW:
            # ① 没有 window 子、只有别的控件 → 两边都报「缺 window 子内容」
            obj = page(**{t + '__1': ctrl(t, 'c', 31001,
                                          textview__2=ctrl('textview', 't', 50002, text='y'))})
            layer, trees = self.assert_agree('%s.json' % t, obj, True)
            self.assertIn('TREE003', [d['rule'] for d in trees], t)
            self.assertTrue(any('缺 window 子内容' in p for p in layer), layer)
            self.assertTrue(any('缺 window 子内容' in d['msg'] for d in trees), trees)
            # ② 有 window 子、但又混进别的类型 → 两边都报「含非 window 子键」
            obj2 = page(**{t + '__1': ctrl(t, 'c', 31002,
                                           window__2=ctrl('window', 'w', 110002),
                                           textview__3=ctrl('textview', 't2', 50003, text='z'))})
            layer2, trees2 = self.assert_agree('%s_mix.json' % t, obj2, True)
            self.assertTrue(any('含非 window 子键' in p for p in layer2), layer2)
            self.assertTrue(any('含非 window 子键' in d['msg'] for d in trees2), trees2)

    def test_missing_window_child(self):
        for t in DOC_ONLY_WINDOW:
            obj = page(**{t + '__1': ctrl(t, 'c', 31001)})
            layer, trees = self.assert_agree('empty_%s.json' % t, obj, True)
            self.assertIn('TREE003', [d['rule'] for d in trees], t)

    def test_array_key_in_wrong_container(self):
        obj = page(window__1=ctrl('window', 'w', 110001, items=[slideitem()]))
        layer, trees = self.assert_agree('arr.json', obj, True)
        self.assertIn('TREE004', [d['rule'] for d in trees])
        self.assertTrue(any('数组' in p and '只能出现在' in p for p in layer), layer)

    def test_selfproof_inject_the_wrong_way(self):
        """自证：把错法注回去 → 两边必须同时变红；改回正确写法 → 两边同时变绿。

        （判据被写松时本用例会失败：这是「用例能抓住该 bug」的最小证明。）
        """
        bad = page(slidewindow__1=ctrl('slidewindow', 'menu', 30001,
                                       button__100=ctrl('button', 'b1', 20001, text='x')))
        good = page(window__1=ctrl('window', 'menu', 110001,
                                   button__100=ctrl('button', 'b1', 20001, text='x')))
        self.assert_agree('inject_bad.json', bad, True)
        self.assert_agree('inject_good.json', good, False)


# ---------------------------------------------------------------- ③ 判据文本（下游会引用）
class TestLayerMessages(unittest.TestCase):
    def test_flat_children_message_is_stable(self):
        """平铺子控件那句话是「读日志就能定位」的契约，别悄悄改口径。"""
        obj = page(slidewindow__1=ctrl('slidewindow', 'menu', 30001,
                                       button__100=ctrl('button', 'b1', 20001, text='x')))
        probs = C._layer_problems(obj)
        self.assertIn(".slidewindow__1 平铺子控件键 ['button__100']"
                      "（slidewindow 子内容只能放 items 内）", probs)


if __name__ == '__main__':
    unittest.main()
