# -*- coding: utf-8 -*-
"""`ui_tools/ui_compile.py` 契约（T1.1 编译器式验收 + T1.2 库化 API）。

判据（本文件钉住的东西）：
  ① 一个**合法最小页面**（textview + 合法 colorTab/position + 根四件套）→ `ok=True` 且 CLI rc=0；
  ② **每条规则至少一个坏例**，断言命中的**规则号**（不是只看 rc≠0），并且「把错法改回正确写法」
     必须不再报该规则（`_selfproof`：判据被写松 / 用例被改成恒真时当场变红）；
  ③ ASSET001 只在给了 `project_root` 时才判（缺图 → 红），且「有图 → 绿」；
  ④ `--strict` 把 warn 变红（非 strict 下 warn 不影响 ok —— 例如 ID002 只提示）；
  ⑤ 工程根形态能扫多页，诊断带 `file` 标签、报告有逐页 counts/summary；
  ⑥ 报告字段完整（counts/summary/diagnostics/delegated）且**同输入同报告**（确定性）；
  ⑦ CLI 契约：退出码 0/1/2、`--rule` 过滤、`--max-diag` 截断（summary 不被截断）、
     `--json` 落报告、`--quiet`、人类可读行形如 `路径: 级别 [规则号] 说明 → 修法`；
  ⑧ 只读：编译不改用户的 json、不往工程里写文件（唯一写盘 = 显式 `--json`）。

自证纪律（AGENTS.md §4「改行为就补判据」）：每条坏例都写成「坏例 → 必须报该规则；修好 → 必须转绿」，
所以「把错法注回去」时本文件必然变红；反过来，若有人把判据放宽到抓不到坏例，红的是 `assertIn`。
夹具一律建在系统临时目录（`_util.project()`），删文件只走守卫 `_util.rm_in_temp`（绝不碰真工程）。
"""
import glob
import json
import os
import re
import subprocess
import sys
import unittest

# 让 `python -m unittest tests.test_ui_compile -v` 这一形态也能跑：同目录其它模块都依赖
# `discover -s tests` / `scripts/run_tests.py` 把 tests/ 加进 sys.path（裸点号导入时不会加）。
# 这里显式补一次，两种跑法等价、可重复（insert 幂等，discover 下无副作用）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _util as U                            # noqa: E402

sys.path.insert(0, os.path.join(U.BASE, 'ui_tools'))
import ui_compile as C                            # noqa: E402
import ui_schema_loader as us                     # noqa: E402

CLI = os.path.join(U.BASE, 'ui_tools', 'ui_compile.py')
DELEGATED_PHRASE = ('图片尺寸 vs 控件盒 / AA / 倒角 / 透明底 → 由 ui_tools/check_all.py'
                    '（委派 tools/qa/*）负责')
REPORT_KEYS = ('ok', 'tool', 'version', 'schemaVersion', 'target', 'counts', 'summary',
               'diagnostics', 'delegated')
# 一条合法 colorTab/position/thum 的值（用注册表零值派生，不抄表）
THUMB_OK = {'size': {'width': 24, 'height': 24}, 'normalPic': '', 'pressedPic': ''}


def ctrl(t, caption, cid, left=0, top=0, w=100, h=40, **over):
    """一个「必填键全集」控件：**必填字段由注册表 defaults() 派生**（本文件不抄字段表）。"""
    d = us.defaults(t)
    d.update({'id': cid, 'caption': caption,
              'position': {'left': left, 'top': top, 'width': w, 'height': h}})
    d.update(over)
    return d


def page(**ctrls):
    """合法根页四件套（id/resolution/position/backgroundColor）+ 给定控件。"""
    p = {'id': 0, 'resolution': {'width': 1024, 'height': 600},
         'position': {'left': 0, 'top': 0, 'width': 1024, 'height': 600},
         'backgroundColor': 8421504}
    p.update(ctrls)
    return p


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = U.project()                    # 临时工程：package.properties + ui/ + resources/images/
        os.makedirs(os.path.join(self.tmp, 'resources', 'images'), exist_ok=True)

    def tearDown(self):
        U.cleanup(self.tmp)

    # ---- 夹具 ----
    def write(self, obj, name='main.json'):
        fp = os.path.join(self.tmp, 'ui', name)
        U.write(fp, obj if isinstance(obj, str) else
                json.dumps(obj, ensure_ascii=False, indent=1))
        return fp

    def png(self, rel):
        """在工程内造一个（假的）图片文件 —— 只碰临时工程。"""
        fp = os.path.join(self.tmp, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, 'wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n0')
        return fp

    # ---- 两条入口：库 API / CLI ----
    def compile(self, obj, name='main.json', project_root=None, **kw):
        if project_root is None:
            project_root = self.tmp
        return C.compile_json(self.write(obj, name), project_root=project_root, **kw)

    def cli(self, *args):
        r = subprocess.run([sys.executable, CLI] + [str(a) for a in args],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        return (r.returncode, r.stdout.decode('utf-8', 'replace'),
                r.stderr.decode('utf-8', 'replace'))

    # ---- 断言工具 ----
    @staticmethod
    def rules(report):
        return sorted(set(d['rule'] for d in report['diagnostics']))

    def severity(self, report, rule):
        return sorted(set(d['severity'] for d in report['diagnostics'] if d['rule'] == rule))

    def paths(self, report, rule):
        return sorted(d['path'] for d in report['diagnostics'] if d['rule'] == rule)

    def selfproof(self, rule, bad, fixed, **kw):
        """自证纪律：`bad` 必须报 `rule`；`fixed`（把错法改回正确写法）必须不再报该规则。

        —— 判据被写松、或「修好」其实没修好，本方法都会红（把错法注回去 = bad 变红）。
        """
        rb = self.compile(bad, name='bad.json', **kw)
        self.assertIn(rule, self.rules(rb),
                      '坏例没被抓住（%s）：%s' % (rule, rb['diagnostics']))
        rf = self.compile(fixed, name='fixed.json', **kw)
        self.assertNotIn(rule, self.rules(rf),
                         '修好后仍报 %s：%s' % (rule, rf['diagnostics']))
        return rb


# ---------------------------------------------------------------- ① 合法样例
class TestValidPage(_Base):
    def test_minimal_valid_page_is_green(self):
        """① 合法最小页面（textview + 合法 colorTab/position）→ ok=True、0 fatal/error/warn。"""
        rep = self.compile(page(textview__1=ctrl('textview', 'title', 50001, text='hi')))
        self.assertTrue(rep['ok'], rep['diagnostics'])
        self.assertEqual(rep['summary'], {'fatal': 0, 'error': 0, 'warn': 0})
        self.assertEqual(rep['counts']['pages'], 1)
        self.assertEqual(rep['counts']['controls'], 1)
        self.assertEqual(rep['counts']['byType'], {'textview': 1})
        # 合法 colorTab / position 是 defaults() 派生的（用例不手抄字段表 → 真源漂移时这里跟着变）
        self.assertIn('colorTab', us.required_fields('textview'))

    def test_root_only_page_is_green(self):
        """HelloWord 形态：只有根四件套、0 控件，也必须 ok（不能因为没控件就报错）。"""
        rep = self.compile(page())
        self.assertTrue(rep['ok'], rep['diagnostics'])
        self.assertEqual(rep['counts']['controls'], 0)

    def test_cli_rc0_on_valid_page(self):
        """① 合法样例 CLI rc=0（退出码是「能不能上机」的表达）。"""
        fp = self.write(page(textview__1=ctrl('textview', 'title', 50001, text='hi')))
        rc, out, err = self.cli(fp)
        self.assertEqual(rc, 0, out + err)
        self.assertIn('[OK] 编译式验收通过', out)
        self.assertIn('fatal=0 error=0 warn=0', out)

    def test_nested_substructure_items_are_validated_but_real_ones_pass(self):
        """注册表的子结构条目（listview.item）也要按必填键校验：合法 item → 绿。

        （口径：listitem 没有 id、但 caption/position/fontSize 等是必填 —— 与控件同源校验。）
        """
        item = dict(us.defaults('listitem'))
        item.update({'caption': 'row', 'position': {'left': 0, 'top': 0, 'width': 400, 'height': 60}})
        rep = self.compile(page(listview__1=ctrl('listview', 'list', 80001, item=item)))
        self.assertTrue(rep['ok'], rep['diagnostics'])
        self.assertEqual(rep['counts']['items'], 1)


# ---------------------------------------------------------------- ② 规则逐条
class TestParseRules(_Base):
    def test_parse001_bad_json(self):
        rep = self.compile('{"id": 0,')          # 语法错（坏例）
        self.assertEqual(self.rules(rep), ['PARSE001'])
        self.assertFalse(rep['ok'])
        fixed = self.compile(page())             # 修好 → 转绿
        self.assertNotIn('PARSE001', self.rules(fixed))

    def test_parse001_bom(self):
        """BOM：严格 json 解析会失败 —— 必须点名（不是「语法错」一句糊过去）。"""
        rep = self.compile('\ufeff' + json.dumps(page(), ensure_ascii=False))
        self.assertIn('PARSE001', self.rules(rep))
        msg = [d['msg'] for d in rep['diagnostics'] if d['rule'] == 'PARSE001'][0]
        self.assertIn('BOM', msg)

    def test_parse002_root_not_object(self):
        rep = self.compile('[1, 2, 3]')
        self.assertEqual(self.rules(rep), ['PARSE002'])
        self.assertFalse(rep['ok'])


class TestSchemaRules(_Base):
    def test_sch001_thumb_written_as_string(self):
        """SCH001 坏例：thumb 写成字符串 → 真机 ftu 加载无声挂死（fatal）。"""
        bad = page(seekbar__1=ctrl('seekbar', 'sk', 91001, thumb='images/t.png'))
        fixed = page(seekbar__1=ctrl('seekbar', 'sk', 91001, thumb=THUMB_OK))
        rep = self.selfproof('SCH001', bad, fixed)
        self.assertEqual(self.severity(rep, 'SCH001'), ['fatal'])
        self.assertEqual(self.paths(rep, 'SCH001'), ['/seekbar__1/thumb'])
        self.assertFalse(rep['ok'])

    def test_sch001_position_written_as_scalar(self):
        bad = page(textview__1=ctrl('textview', 'tv', 50001, position='0,0,100,40'))
        fixed = page(textview__1=ctrl('textview', 'tv', 50001))
        self.selfproof('SCH001', bad, fixed)

    def test_sch002_missing_required_key(self):
        """SCH002 坏例：textview 缺必填 fontSize（check_all #14 的同源判据）。"""
        good = ctrl('textview', 'tv', 50001)
        bad = page(textview__1={k: v for k, v in good.items() if k != 'fontSize'})
        fixed = page(textview__1=good)
        rep = self.selfproof('SCH002', bad, fixed)
        self.assertEqual(self.paths(rep, 'SCH002'), ['/textview__1/fontSize'])
        self.assertFalse(rep['ok'])

    def test_sch002_root_required_keys(self):
        good = page()
        bad = {k: v for k, v in good.items() if k != 'resolution'}
        self.selfproof('SCH002', bad, good)

    def test_sch003_type_mismatch(self):
        bad = page(textview__1=ctrl('textview', 'tv', 50001, fontSize='16'))
        fixed = page(textview__1=ctrl('textview', 'tv', 50001, fontSize=16))
        rep = self.selfproof('SCH003', bad, fixed)
        self.assertEqual(self.paths(rep, 'SCH003'), ['/textview__1/fontSize'])
        self.assertFalse(rep['ok'])

    def test_sch004_unknown_key_is_warn_only(self):
        """SCH004 = warn：注册表外未知键**不许判 FAIL**（不报错仅提示）。"""
        rep = self.compile(page(textview__1=ctrl('textview', 'tv', 50001, someFutureKey=1)))
        self.assertEqual(self.rules(rep), ['SCH004'])
        self.assertEqual(self.severity(rep, 'SCH004'), ['warn'])
        self.assertTrue(rep['ok'], '未知键只是提示，不该让 ok=False')
        fixed = self.compile(page(textview__1=ctrl('textview', 'tv', 50001)))
        self.assertNotIn('SCH004', self.rules(fixed))

    def test_sch003_thumb_missing_required_keys(self):
        bad = page(seekbar__1=ctrl('seekbar', 'sk', 91001,
                                   thumb={'size': {'width': 24, 'height': 24}}))
        fixed = page(seekbar__1=ctrl('seekbar', 'sk', 91001, thumb=THUMB_OK))
        rep = self.selfproof('SCH003', bad, fixed)
        self.assertEqual(self.paths(rep, 'SCH003'),
                         ['/seekbar__1/thumb', '/seekbar__1/thumb'])


class TestNameIdRules(_Base):
    def test_name001_caption_not_c_identifier(self):
        bad = page(textview__1=ctrl('textview', 'Text-View', 50001))
        fixed = page(textview__1=ctrl('textview', 'TextView', 50001))
        rep = self.selfproof('NAME001', bad, fixed)
        self.assertEqual(self.paths(rep, 'NAME001'), ['/textview__1/caption'])
        self.assertFalse(rep['ok'])

    def test_name001_empty_caption(self):
        rep = self.compile(page(textview__1=ctrl('textview', '', 50001)))
        self.assertIn('NAME001', self.rules(rep))

    def test_name002_duplicate_caption(self):
        bad = page(textview__1=ctrl('textview', 'tv', 50001),
                   textview__2=ctrl('textview', 'tv', 50002))
        fixed = page(textview__1=ctrl('textview', 'tvA', 50001),
                     textview__2=ctrl('textview', 'tvB', 50002))
        rep = self.selfproof('NAME002', bad, fixed)
        self.assertEqual(self.paths(rep, 'NAME002'),
                         ['/textview__1/caption', '/textview__2/caption'])
        self.assertFalse(rep['ok'])

    def test_id001_duplicate_id(self):
        bad = page(textview__1=ctrl('textview', 'tvA', 50001),
                   textview__2=ctrl('textview', 'tvB', 50001))
        fixed = page(textview__1=ctrl('textview', 'tvA', 50001),
                     textview__2=ctrl('textview', 'tvB', 50002))
        rep = self.selfproof('ID001', bad, fixed)
        self.assertEqual(self.paths(rep, 'ID001'), ['/textview__1/id', '/textview__2/id'])

    def test_id001_missing_id_when_registry_requires_it(self):
        """id 缺键归 ID001（不重复报 SCH002 —— 去重口径写在 ui_compile 的 docstring 里）。"""
        good = ctrl('textview', 'tv', 50001)
        bad = page(textview__1={k: v for k, v in good.items() if k != 'id'})
        rep = self.selfproof('ID001', bad, page(textview__1=good))
        self.assertEqual(self.paths(rep, 'ID001'), ['/textview__1/id'])
        self.assertNotIn('SCH002', self.rules(rep))

    def test_id002_out_of_band_is_warn_not_fail(self):
        """ID002 = warn：id 不在建议分区段**仅提示，不许 FAIL**。"""
        rep = self.compile(page(textview__1=ctrl('textview', 'tv', 1)))
        self.assertEqual(self.rules(rep), ['ID002'])
        self.assertEqual(self.severity(rep, 'ID002'), ['warn'])
        self.assertTrue(rep['ok'])
        inband = self.compile(page(textview__1=ctrl('textview', 'tv', 50001)))
        self.assertNotIn('ID002', self.rules(inband))

    def test_tree001_non_container_with_children(self):
        """TREE001 坏例：button（非容器）装了子控件；修法 = 换成容器 window。"""
        child = ctrl('textview', 'inner', 50002, w=50, h=20)
        bad = page(button__1=ctrl('button', 'btn', 20001, textview__2=child))
        fixed = page(window__1=ctrl('window', 'win', 110001, textview__2=child))
        rep = self.selfproof('TREE001', bad, fixed)
        self.assertEqual(self.paths(rep, 'TREE001'), ['/button__1'])
        self.assertFalse(rep['ok'])

    def test_container_with_children_is_green(self):
        rep = self.compile(page(window__1=ctrl('window', 'win', 110001,
                                               textview__2=ctrl('textview', 'inner', 50002))))
        self.assertTrue(rep['ok'], rep['diagnostics'])

    def test_tree002_structural_container_with_flat_children(self):
        """TREE002 坏例：结构容器（slidewindow）平铺子控件键。

        真机出处（2026-10-05）：`templates/DemoControls_V85X/ui/main.json` 把 7 个磁贴按钮
        直挂 slidewindow 下 —— check_all #2 判 FAIL，但本工具当时按 `container: true` 放行
        （**假绿**）。修法 = 子内容走结构键（items），或改用 window 容器。
        """
        bad = page(slidewindow__1=ctrl('slidewindow', 'menu', 30001,
                                       button__100=ctrl('button', 'b1', 20001, text='x')))
        fixed = page(window__1=ctrl('window', 'menu', 110001,
                                    button__100=ctrl('button', 'b1', 20001, text='x')))
        rep = self.selfproof('TREE002', bad, fixed)
        self.assertEqual(self.paths(rep, 'TREE002'), ['/slidewindow__1'])
        self.assertFalse(rep['ok'])

    def test_tree002_covers_every_structural_container(self):
        """四个结构容器都要判（表取注册表 children 段 —— 本用例不写死清单）。"""
        for t in sorted(us.structural_containers()):
            rep = self.compile(page(**{t + '__1': ctrl(t, 'c', 100001,
                                                       textview__9=ctrl('textview', 'tv', 50009,
                                                                        text='x'))}),
                               name='%s.json' % t)
            self.assertIn('TREE002', self.rules(rep),
                          '%s 没报 TREE002：%s' % (t, rep['diagnostics']))

    def test_tree003_only_window_container(self):
        """TREE003 坏例：pagewindow/scrollwindow 只装 window —— 装了 textview / 一个都没装都要报。"""
        for t in ('pagewindow', 'scrollwindow'):
            bad = page(**{t + '__1': ctrl(t, 'c', 100002,
                                          textview__2=ctrl('textview', 'tv', 50002, text='y'))})
            fixed = page(**{t + '__1': ctrl(t, 'c', 100002,
                                            window__2=ctrl('window', 'w', 110002))})
            rep = self.selfproof('TREE003', bad, fixed)
            self.assertEqual(self.paths(rep, 'TREE003'), ['/%s__1' % t])
            # 缺 window 子内容（空容器）同样要报 —— 与 check_all #2 同判
            empty = self.compile(page(**{t + '__1': ctrl(t, 'c', 100003)}), name='%s_empty.json' % t)
            self.assertIn('TREE003', self.rules(empty),
                          '空 %s 没报 TREE003：%s' % (t, empty['diagnostics']))

    def test_tree004_array_key_in_wrong_container(self):
        """TREE004 坏例：数组子结构键放错容器（items 只能出现在 slidewindow）。"""
        item = {'colorTab': {'color0': 0xFFFFFF, 'color1': -1, 'color2': -1,
                             'color3': -1, 'color4': -1}, 'picTab': {}, 'text': 'i'}
        bad = page(window__1=ctrl('window', 'w', 110003, items=[item]))
        fixed = page(slidewindow__1=ctrl('slidewindow', 'sw', 30004, items=[item]))
        rep = self.selfproof('TREE004', bad, fixed)
        self.assertEqual(self.paths(rep, 'TREE004'), ['/window__1'])


class TestStructuralRules(_Base):
    def test_page001_bad_key_shape(self):
        bad = page(**{'textview_1': ctrl('textview', 'tv', 50001)})
        fixed = page(textview__1=ctrl('textview', 'tv', 50001))
        rep = self.selfproof('PAGE001', bad, fixed)
        self.assertEqual(self.paths(rep, 'PAGE001'), ['/textview_1'])

    def test_page001_unregistered_type(self):
        bad = page(**{'mywidget__1': ctrl('textview', 'tv', 50001)})
        fixed = page(textview__1=ctrl('textview', 'tv', 50001))
        self.selfproof('PAGE001', bad, fixed)

    def test_root001_missing_background_color(self):
        """ROOT001 坏例：根缺 backgroundColor（renderContract no-root-bg：引擎靠它擦屏）。"""
        bad = {k: v for k, v in page().items() if k != 'backgroundColor'}
        fixed = page()
        rep = self.selfproof('ROOT001', bad, fixed)
        self.assertEqual(self.paths(rep, 'ROOT001'), ['/backgroundColor'])
        self.assertFalse(rep['ok'])

    def test_char001_blacklist_char(self):
        """CHAR001 坏例：文本含 ℃（check_all.BLACKLIST 同源字集）。"""
        bad = page(textview__1=ctrl('textview', 'tv', 50001, text='室内 25℃'))
        fixed = page(textview__1=ctrl('textview', 'tv', 50001, text='室内 25C'))
        rep = self.selfproof('CHAR001', bad, fixed)
        self.assertEqual(self.paths(rep, 'CHAR001'), ['/textview__1/text'])
        self.assertFalse(rep['ok'])

    def test_char001_charset_is_same_source_as_check_all(self):
        """字符集必须与 check_all.BLACKLIST 同源：本工具不内嵌副本（改那边这边跟着变）。"""
        import check_all as CA
        rep = self.compile(page(textview__1=ctrl('textview', 'tv', 50001,
                                                 text=''.join(sorted(CA.BLACKLIST)))))
        self.assertIn('CHAR001', self.rules(rep))

    def test_geom001_position_missing_key_and_bad_type(self):
        bad = page(textview__1=ctrl('textview', 'tv', 50001,
                                    position={'left': 0, 'top': 0, 'width': 'x'}))
        fixed = page(textview__1=ctrl('textview', 'tv', 50001))
        rep = self.selfproof('GEOM001', bad, fixed)
        self.assertEqual(self.paths(rep, 'GEOM001'),
                         ['/textview__1/position.height', '/textview__1/position.width'])
        # 定位唯一：position 子键不再同时报 SCH003（同一问题两份诊断）
        self.assertNotIn('SCH003', self.rules(rep))

    def test_geom001_root_position(self):
        bad = dict(page())
        bad['position'] = {'left': 0, 'top': 0, 'width': 1024}
        fixed = page()
        rep = self.selfproof('GEOM001', bad, fixed)
        self.assertIn('/position.height', self.paths(rep, 'GEOM001'))

    def test_res001_expectation_mismatch(self):
        """--res：给错屏的页必须红；对上就绿（自证：把 res 改回 1024x600 即转绿）。"""
        p = page(textview__1=ctrl('textview', 'tv', 50001))
        bad = self.compile(p, name='res.json', res='800x480')
        self.assertEqual(self.rules(bad), ['RES001'])
        self.assertEqual(self.paths(bad, 'RES001'), ['/resolution'])
        self.assertFalse(bad['ok'])
        fixed = self.compile(p, name='res.json', res='1024x600')
        self.assertNotIn('RES001', self.rules(fixed))
        self.assertTrue(fixed['ok'], fixed['diagnostics'])

    def test_scan001_no_pages_is_not_a_silent_pass(self):
        """0 页不许返回「空成功」（check_all 的 `_ui_pages` 注释里有同类实测教训）。"""
        empty = os.path.join(self.tmp, 'empty_ui')
        os.makedirs(empty, exist_ok=True)
        rep = C.compile_json(empty)
        self.assertEqual(self.rules(rep), ['SCAN001'])
        self.assertEqual(rep['counts']['pages'], 0)
        self.assertFalse(rep['ok'], '0 页 = 什么都没校验，不能算通过')


class TestAssetRules(_Base):
    def test_asset002_absolute_and_prefix_and_backslash(self):
        """ASSET002 坏例：绝对路径 / resources 前缀 / 反斜杠（三种形态都点名）。"""
        for ref in ('D:/imgs/t.png', '/opt/imgs/t.png', 'resources/images/t.png', 'images\\t.png'):
            with self.subTest(ref=ref):
                bad = page(textview__1=ctrl('textview', 'tv', 50001, backgroundPic=ref))
                fixed = page(textview__1=ctrl('textview', 'tv', 50001, backgroundPic='images/t.png'))
                self.png('resources/images/t.png')
                rep = self.selfproof('ASSET002', bad, fixed)
                self.assertEqual(self.paths(rep, 'ASSET002'), ['/textview__1/backgroundPic'])
                self.assertFalse(rep['ok'])

    def test_asset001_missing_file_red_and_existing_green(self):
        """③ ASSET001：需 project_root；文件不存在 → 红；把图放到位 → 绿。"""
        ref = 'images/only_here.png'
        p = page(textview__1=ctrl('textview', 'tv', 50001, backgroundPic=ref))
        red = self.compile(p, name='missing.json')
        self.assertIn('ASSET001', self.rules(red))
        self.assertFalse(red['ok'])
        self.png('resources/images/only_here.png')
        green = self.compile(p, name='present.json')
        self.assertNotIn('ASSET001', self.rules(green))
        self.assertTrue(green['ok'], green['diagnostics'])

    def test_asset001_needs_project_root(self):
        """给了 project_root 才判存在性：
        ① 页面不在 `<root>/ui/` 布局里、又没传 project_root → 不判 + **报告里记账**（不静默）；
        ② 页面在 `<root>/ui/` 布局里 → 自动探测到工程根，照判（少一次「我以为核过了」）。
        """
        ref = 'images/absent.png'
        loose = os.path.join(self.tmp, 'loose', 'page.json')
        U.write(loose, json.dumps(page(textview__1=ctrl('textview', 'tv', 50001,
                                                        backgroundPic=ref)), ensure_ascii=False))
        rep = C.compile_json(loose, project_root=None)
        self.assertIsNone(rep['projectRoot'], '这份夹具不在 <root>/ui/ 下，不该探测到工程根')
        self.assertNotIn('ASSET001', self.rules(rep))
        self.assertTrue(any('ASSET001 未执行' in d for d in rep['delegated']),
                        '跳过了什么/为什么必须写进 delegated：%s' % rep['delegated'])
        # ② 同一份 json 放进 <root>/ui/ → 自动探测到工程根 → 缺图判红
        under_ui = self.write(page(textview__1=ctrl('textview', 'tv', 50001, backgroundPic=ref)),
                              'auto.json')
        rep2 = C.compile_json(under_ui, project_root=None)
        self.assertEqual(rep2['projectRoot'], os.path.abspath(self.tmp))
        self.assertIn('ASSET001', self.rules(rep2))
        self.assertFalse(rep2['ok'])

    def test_asset_thumb_pics_are_checked_too(self):
        """thumb 子盒里的图片（normalPic/pressedPic，type=path）同样要核存在性。"""
        thumb = {'size': {'width': 24, 'height': 24},
                 'normalPic': 'images/knob.png', 'pressedPic': ''}
        rep = self.compile(page(seekbar__1=ctrl('seekbar', 'sk', 91001, thumb=thumb)))
        self.assertEqual(self.paths(rep, 'ASSET001'), ['/seekbar__1/thumb.normalPic'])

    def test_deleted_image_turns_red_through_temp_guard(self):
        """自证 + 守卫：先有图 → 绿；**只在临时工程内**删图 → 红（删除走 U.rm_in_temp）。"""
        ref = 'images/gone.png'
        p = page(textview__1=ctrl('textview', 'tv', 50001, backgroundPic=ref))
        self.png('resources/images/gone.png')
        self.assertTrue(self.compile(p).get('ok'))
        U.rm_in_temp(self.tmp, os.path.join('resources', 'images', 'gone.png'))
        rep = self.compile(p)
        self.assertIn('ASSET001', self.rules(rep))       # 把「图没了」注回去必须变红
        self.assertFalse(rep['ok'])


# ---------------------------------------------------------------- ④ strict / ⑤ 工程根
class TestStrictAndProjectForm(_Base):
    def test_strict_turns_warn_red(self):
        fp = self.write(page(textview__1=ctrl('textview', 'tv', 1)))   # ID002 warn（非 error）
        rc, out, _ = self.cli(fp)
        self.assertEqual(rc, 0, out)
        self.assertIn('warn=1', out)
        rc2, out2, _ = self.cli(fp, '--strict')
        self.assertEqual(rc2, 1, out2)
        self.assertIn('[X] 编译式验收未过', out2)
        # 库 API 同一语义
        self.assertTrue(C.compile_json(fp, strict=False)['ok'])
        self.assertFalse(C.compile_json(fp, strict=True)['ok'])

    def test_project_root_scans_multiple_pages(self):
        """⑤ 工程根形态：扫 ui/*.json 逐页出诊断，诊断带 file、报告有逐页留痕。"""
        self.write(page(textview__1=ctrl('textview', 'good', 50001, text='ok')), 'a.json')
        self.write(page(seekbar__1=ctrl('seekbar', 'sk', 91001, thumb='images/t.png')), 'b.json')
        rep = C.compile_project(self.tmp)
        self.assertEqual(rep['counts']['pages'], 2)
        self.assertEqual(rep['counts']['controls'], 2)
        self.assertEqual(rep['counts']['byType'], {'seekbar': 1, 'textview': 1})
        self.assertEqual(sorted(rep['files']), ['ui/a.json', 'ui/b.json'])
        self.assertEqual([p['ok'] for p in rep['pages']], [True, False])
        self.assertIn('SCH001', self.rules(rep))
        for d in rep['diagnostics']:
            self.assertIn(d['file'], ('ui/a.json', 'ui/b.json'))
        self.assertEqual([d['file'] for d in rep['diagnostics'] if d['rule'] == 'SCH001'],
                         ['ui/b.json'])

    def test_layered_resolution_dir_is_scanned(self):
        """ui/<分辨率>/*.json（SampleUI-New 那种分层布局）也要扫到（否则 0 页假阴性）。"""
        fp = os.path.join(self.tmp, 'ui', '1024x600', 'main.json')
        U.write(fp, json.dumps(page(textview__1=ctrl('textview', 'tv', 50001)), ensure_ascii=False))
        rep = C.compile_project(self.tmp)
        self.assertEqual(rep['counts']['pages'], 1)
        self.assertEqual(rep['files'], ['ui/1024x600/main.json'])

    def test_cli_project_root_rc1_and_file_labels(self):
        self.write(page(seekbar__1=ctrl('seekbar', 'sk', 91001, thumb='images/t.png')), 'bad.json')
        rc, out, _ = self.cli(self.tmp)
        self.assertEqual(rc, 1, out)
        self.assertIn('ui/bad.json: /seekbar__1/thumb: fatal [SCH001]', out)


# ---------------------------------------------------------------- ⑥ 报告契约
class TestReportContract(_Base):
    def test_report_fields_and_counts(self):
        rep = self.compile(page(textview__1=ctrl('textview', 'tv', 50001),
                                window__1=ctrl('window', 'win', 110001,
                                               button__2=ctrl('button', 'btn', 20001))))
        for k in REPORT_KEYS:
            self.assertIn(k, rep, k)
        self.assertEqual(rep['tool'], 'ui_compile')
        self.assertTrue(rep['version'])
        self.assertEqual(rep['schemaVersion'], us.load()['schemaVersion'])
        self.assertEqual(rep['counts']['pages'], 1)
        self.assertEqual(rep['counts']['controls'], 3)
        self.assertEqual(rep['counts']['byType'], {'button': 1, 'textview': 1, 'window': 1})
        self.assertEqual(rep['summary'], {'fatal': 0, 'error': 0, 'warn': 0})
        self.assertEqual(rep['diagnostics'], [])

    def test_diagnostic_shape_and_sorting(self):
        rep = self.compile(page(seekbar__1=ctrl('seekbar', 'sk', 91001, thumb='x'),
                                textview__2=ctrl('textview', 'tv', 50001,
                                                 position={'left': 0, 'top': 0, 'width': 'x'})))
        keys = sorted(rep['diagnostics'][0])
        self.assertEqual(keys, ['file', 'hint', 'msg', 'path', 'rule', 'severity'])
        order = [(d['path'], d['rule']) for d in rep['diagnostics']]
        self.assertEqual(order, sorted(order), '诊断排序必须稳定（先 path 再 rule）')
        for d in rep['diagnostics']:
            self.assertTrue(d['path'].startswith('/'), d)
            self.assertTrue(d['msg'], d)
            self.assertTrue(d['hint'], d)

    def test_delegated_declares_check_all_scope(self):
        """委派：图片尺寸 vs 控件盒 / AA / 倒角 / 透明底 → check_all（T1.4 接口点）。"""
        rep = self.compile(page())
        self.assertIn(DELEGATED_PHRASE, rep['delegated'])
        self.assertTrue(any('T1.4' in d for d in rep['delegated']), rep['delegated'])

    def test_deterministic_same_input_same_report(self):
        fp = self.write(page(seekbar__1=ctrl('seekbar', 'sk', 91001, thumb='x')))
        a = json.dumps(C.compile_json(fp, project_root=self.tmp), sort_keys=True, ensure_ascii=False)
        b = json.dumps(C.compile_json(fp, project_root=self.tmp), sort_keys=True, ensure_ascii=False)
        self.assertEqual(a, b, '同一输入必须永远同一报告')

    def test_ok_semantics(self):
        """ok = 无 fatal/error（strict 时也要求 warn=0）。"""
        warn_only = page(textview__1=ctrl('textview', 'tv', 1))
        self.assertTrue(self.compile(warn_only, name='w.json')['ok'])
        self.assertFalse(self.compile(warn_only, name='w.json', strict=True)['ok'])
        err = page(textview__1=ctrl('textview', 'tv', 50001, fontSize='16'))
        self.assertFalse(self.compile(err, name='e.json')['ok'])

    def test_compiling_does_not_touch_user_files(self):
        """⑧ 只读：编译不改 json、不往工程里写文件。"""
        fp = self.write(page(textview__1=ctrl('textview', 'tv', 50001)))
        before = (os.stat(fp).st_mtime_ns, open(fp, 'rb').read())
        tree_before = sorted(os.path.relpath(p, self.tmp).replace('\\', '/')
                             for p in glob.glob(os.path.join(self.tmp, '**', '*'), recursive=True))
        C.compile_json(fp, project_root=self.tmp)
        C.compile_project(self.tmp)
        after = (os.stat(fp).st_mtime_ns, open(fp, 'rb').read())
        self.assertEqual(before, after, '编译动了用户的 json（必须只读）')
        tree_after = sorted(os.path.relpath(p, self.tmp).replace('\\', '/')
                            for p in glob.glob(os.path.join(self.tmp, '**', '*'), recursive=True))
        self.assertEqual(tree_before, tree_after, '编译往工程里写了东西（必须只读）')


# ---------------------------------------------------------------- ⑦ CLI 契约
class TestCliContract(_Base):
    def test_exit_codes(self):
        good = self.write(page(textview__1=ctrl('textview', 'tv', 50001)), 'good.json')
        bad = self.write(page(seekbar__1=ctrl('seekbar', 'sk', 91001, thumb='x')), 'bad.json')
        self.assertEqual(self.cli(good)[0], 0)
        self.assertEqual(self.cli(bad)[0], 1)
        self.assertEqual(self.cli()[0], 2)                                  # 缺 target
        self.assertEqual(self.cli(os.path.join(self.tmp, 'nope.json'))[0], 2)
        self.assertEqual(self.cli(good, '--res', 'wide')[0], 2)             # --res 形态错
        self.assertEqual(self.cli(good, '--rule', 'SCH999')[0], 2)          # 规则号写错
        self.assertEqual(self.cli(bad, '--json', bad)[0], 2)                # 拒绝覆盖输入 json

    def test_human_line_format(self):
        bad = self.write(page(seekbar__1=ctrl('seekbar', 'sk', 91001, thumb='x')), 'bad.json')
        rc, out, _ = self.cli(bad)
        self.assertEqual(rc, 1)
        self.assertRegex(out, r'(?m)^/seekbar__1/thumb: fatal \[SCH001\] .+ → .+$')
        self.assertRegex(out, r'(?m)^fatal=1 error=0 warn=0 .+$')
        self.assertIn('上机前必过', out)

    def test_rule_filter(self):
        bad = self.write(page(seekbar__1=ctrl('seekbar', 'sk', 91001, thumb='x'),
                              textview__2=ctrl('textview', '', 50001)), 'bad.json')
        rc, out, _ = self.cli(bad, '--rule', 'SCH001')
        self.assertEqual(rc, 1)
        self.assertIn('[SCH001]', out)
        self.assertNotIn('[NAME001]', out)
        rc2, out2, _ = self.cli(bad, '--rule', 'NAME001')
        self.assertEqual(rc2, 1)
        self.assertIn('[NAME001]', out2)
        self.assertNotIn('[SCH001]', out2)

    def test_max_diag_truncates_list_but_not_summary(self):
        bad = self.write(page(seekbar__1=ctrl('seekbar', 'sk', 1, thumb='x')), 'bad.json')
        rep_path = os.path.join(self.tmp, 'report.json')
        rc, out, _ = self.cli(bad, '--max-diag', '1', '--json', rep_path)
        self.assertEqual(rc, 1)
        rep = json.load(open(rep_path, encoding='utf-8'))
        self.assertEqual(len(rep['diagnostics']), 1)
        self.assertGreaterEqual(rep['truncated'], 1)
        self.assertEqual(rep['summary']['fatal'] + rep['summary']['error'] + rep['summary']['warn'],
                         len(rep['diagnostics']) + rep['truncated'])
        self.assertTrue(any('max-diag' in d for d in rep['delegated']), rep['delegated'])
        self.assertIn('截断', out)

    def test_json_report_written_and_quiet(self):
        bad = self.write(page(seekbar__1=ctrl('seekbar', 'sk', 91001, thumb='x')), 'bad.json')
        rep_path = os.path.join(self.tmp, 'out', 'report.json')
        rc, out, _ = self.cli(bad, '--json', rep_path, '--quiet')
        self.assertEqual(rc, 1)
        self.assertTrue(os.path.isfile(rep_path))
        rep = json.load(open(rep_path, encoding='utf-8'))
        for k in REPORT_KEYS:
            self.assertIn(k, rep, k)
        self.assertFalse(rep['ok'])
        # --quiet：只给汇总，不给逐条诊断
        self.assertNotIn('→', out)
        self.assertIn('FAIL', out)


# ---------------------------------------------------------------- 规则表自身
class TestRuleTable(_Base):
    def test_rule_ids_and_levels(self):
        """规则表：整改方案 §T1.1 的 17 条必须都在，级别按表钉死。"""
        want = {'PARSE001': 'error', 'PARSE002': 'error', 'PAGE001': 'error', 'SCH001': 'fatal',
                'SCH002': 'error', 'SCH003': 'error', 'SCH004': 'warn', 'NAME001': 'error',
                'NAME002': 'error', 'ID001': 'error', 'ID002': 'warn', 'TREE001': 'error',
                'TREE002': 'error', 'TREE003': 'error', 'TREE004': 'error',
                'ROOT001': 'error', 'CHAR001': 'error', 'ASSET001': 'error', 'ASSET002': 'error',
                'GEOM001': 'error'}
        for rule, sev in want.items():
            self.assertIn(rule, C.RULES, rule)
            self.assertEqual(C.RULES[rule][0], sev, rule)
        self.assertTrue(set(want) <= set(C.ALL_RULES))

    def test_rules_are_actually_reachable(self):
        """每条规则都要有「能产生它」的判据（防规则表里挂空号）。"""
        handlers = ('PARSE001', 'PARSE002', 'PAGE001', 'SCH001', 'SCH002', 'SCH003', 'SCH004',
                    'NAME001', 'NAME002', 'ID001', 'ID002', 'TREE001', 'TREE002', 'TREE003',
                    'TREE004', 'ROOT001', 'CHAR001', 'ASSET001', 'ASSET002', 'GEOM001',
                    'RES001', 'SCAN001')
        src = open(os.path.join(U.BASE, 'ui_tools', 'ui_compile.py'),
                   encoding='utf-8').read()
        for rule in handlers:
            self.assertIn("'%s'" % rule, src, rule)
            self.assertIn(rule, C.ALL_RULES, rule)


if __name__ == '__main__':
    unittest.main()
