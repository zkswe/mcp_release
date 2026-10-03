# -*- coding: utf-8 -*-
"""域⑨ 上机前体检判据（preflight_spec.json + preflight_loader.py + preflight.py）。

这套判据的价值全在**边界**上：屏比设计大 1 像素要不要动布局、比例差 3% 算不算不同、
面板高度读不出时敢不敢拿 virtual_size 凑、比例不同时会不会偷偷等比缩放出个变形的界面。
所以用例钉的是这些边界，而不是"能跑通"。

钉住十件事：
  ① 注册表可加载、自检通过；三分支（push / warn / adapt_device）齐全且顺序对
  ② 设计分辨率 = **启动窗口**（Main.cpp onStartupApp → ui/<name>.json 根窗口），不是 prefs 里随便一个数
  ③ 屏 ≥ 设计 → push（**屏大是正常的，不许去缩放**）；屏 < 设计 → warn（且要问用户）
  ④ 互为转置（设计 800x480 / 面板 480x800）算同一块屏 → 不当不一致
  ⑤ 读不出设计 → adapt_device；面板高度读不出 → 如实报 warn（不拿 virtual_size 凑）
  ⑥ 比例接近（≤3%）→ 允许等比；比例不同 → `scale_project` **拒绝改盘**（只出 plan）
  ⑦ 等比改盘是**自封闭**的：改完 json 的 resolution 就是面板 → 再跑一次落回 push（不会反复放大）
  ⑧ 字库：内置字库 < 200KB → no_cjk；档位阈值/文件名与 components/fonts **跨来源一致**
  ⑨ 体积：接近上限 → near、超上限 → over；`resources/` + 工程字体 + libzkgui.so 的计数口径
  ⑩ 派生页与注册表一致（手改 md 会红）；新 op 已进分发器清单
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import _util as U

BASE = U.BASE
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import preflight as pf            # noqa: E402
import preflight_loader as P      # noqa: E402

TPL = os.path.join(BASE, 'templates', 'HelloWord_Z20')


class TestRegistry(unittest.TestCase):
    def test_loads_and_validates(self):
        self.assertEqual(P.validate(include_doc=True), [])

    def test_three_schools_in_order(self):
        acts = [d['action'] for d in P.decisions()]
        self.assertEqual(acts, ['push', 'warn', 'adapt_device'])

    def test_unknown_branch_raises(self):
        with self.assertRaises(P.PreflightSpecError):
            P.decision('no_such_branch')

    def test_font_thresholds_cross_checked(self):
        """字库阈值/档位只有一份：注册表说 200KB，组件实现就得是 200KB。"""
        self.assertEqual(P.cross_check(), [])
        self.assertEqual(pf.P.cjk_min_kb(), 200.0)
        for name in P.tier_order():
            self.assertTrue(os.path.isfile(P.tier_file(name)))
            self.assertGreater(P.tier_bytes(name), 0)


class TestStartupWindow(unittest.TestCase):
    def test_reads_activity_then_json_root(self):
        w = pf.startup_window(TPL)
        self.assertEqual(w['activity'], 'mainActivity')
        self.assertTrue(w['json'].endswith(os.path.join('ui', 'main.json')))
        self.assertEqual(w['design'], '1024x600')          # 模板根窗口尺寸
        self.assertIn('resolution', w['source'])

    def test_missing_project_reports_not_raises(self):
        w = pf.startup_window(os.path.join(BASE, 'no_such_project'))
        self.assertEqual(w['design'], '')
        self.assertTrue(w['errors'])


class TestResolutionDecision(unittest.TestCase):
    def dec(self, design, panel):
        return pf.resolution_decision(design, 't', panel)

    def test_panel_bigger_pushes(self):
        d = self.dec('800x480', '1024x600')
        self.assertEqual((d['id'], d['action']), ('screen_ge_design', 'push'))
        self.assertIsNone(d['plan'])

    def test_panel_smaller_warns(self):
        d = self.dec('1600x600', '480x800')
        self.assertEqual((d['id'], d['action']), ('screen_lt_design', 'warn'))
        self.assertEqual(d['aspect'], 'diff')              # 1.667 vs 0.6 → 必须重排，不是缩放

    def test_one_dim_smaller_warns(self):
        d = self.dec('1024x600', '1024x480')               # 宽够、高不够
        self.assertEqual(d['action'], 'warn')

    def test_transposed_is_same_screen(self):
        d = self.dec('800x480', '480x800')
        self.assertEqual(d['action'], 'push')
        self.assertIn('转置', d['id'] + d['why'])

    def test_design_unknown_adapts_to_panel(self):
        d = self.dec('', '480x800')
        self.assertEqual(d['action'], 'adapt_device')
        self.assertEqual(d['plan']['kind'], 'same')        # 无设计可比 → 直接照面板

    def test_panel_unknown_warns_instead_of_guessing(self):
        d = self.dec('800x480', '')
        self.assertEqual(d['id'], 'panel_unknown')
        self.assertEqual(d['action'], 'warn')

    def test_panel_width_only_does_not_borrow_virtual_height(self):
        d = self.dec('800x480', '480x?')
        self.assertEqual(d['id'], 'panel_height_unknown')
        self.assertIn('页数', d['why'])

    def test_aspect_near_is_same(self):
        self.assertEqual(pf.aspect_kind('800x480', '1024x600'), 'same')   # 差 2.4%
        self.assertEqual(pf.aspect_kind('800x480', '1280x720'), 'diff')   # 差 20%


class TestScale(unittest.TestCase):
    def test_diff_aspect_refuses_to_write(self):
        tmp = tempfile.mkdtemp(prefix='pfproj_')
        self.addCleanup(shutil.rmtree, tmp, True)
        shutil.copytree(TPL, tmp, dirs_exist_ok=True)
        before = io.open(os.path.join(tmp, 'ui', 'main.json'), encoding='utf-8-sig').read()
        r = pf.scale_project(tmp, '1600x600', '480x800')
        self.assertFalse(r['applied'])
        self.assertIn('比例不同', r['skipped'])
        self.assertEqual(io.open(os.path.join(tmp, 'ui', 'main.json'),
                                 encoding='utf-8-sig').read(), before)

    def test_scale_boxes_and_shrinks_resolution(self):
        tmp = tempfile.mkdtemp(prefix='pfproj_')
        self.addCleanup(shutil.rmtree, tmp, True)
        shutil.copytree(TPL, tmp, dirs_exist_ok=True)
        # 造一个控件盒，验证等比换算（模板 main.json 没有控件）
        jp = os.path.join(tmp, 'ui', 'main.json')
        data = json.load(io.open(jp, encoding='utf-8-sig'))
        data['textview__1'] = {'position': {'left': 100, 'top': 50, 'width': 200, 'height': 40},
                               'fontSize': 24, 'text': '甲'}
        io.open(jp, 'w', encoding='utf-8').write(json.dumps(data, ensure_ascii=False))
        r = pf.scale_project(tmp, '1024x600', '512x300')      # 正好 0.5 倍、比例相同
        self.assertTrue(r['applied'], r.get('skipped'))
        # 2 个盒子 = 根窗口 position + 那个控件；1 处字号
        self.assertEqual((r['boxes'], r['fonts']), (2, 1))
        out = json.load(io.open(jp, encoding='utf-8-sig'))
        self.assertEqual(out['resolution'], {'width': 512, 'height': 300})
        self.assertEqual(out['textview__1']['position'],
                         {'left': 50, 'top': 25, 'width': 100, 'height': 20})
        self.assertEqual(out['textview__1']['fontSize'], 12)

    def test_scale_is_self_closing(self):
        """改完 design 就等于面板了 → 再判一次是 push，不会二次放大。"""
        tmp = tempfile.mkdtemp(prefix='pfproj_')
        self.addCleanup(shutil.rmtree, tmp, True)
        shutil.copytree(TPL, tmp, dirs_exist_ok=True)
        pf.scale_project(tmp, '1024x600', '512x300')
        design, _src = pf.design_resolution(tmp)
        self.assertEqual(design, '512x300')
        dec = pf.resolution_decision(design, 't', '512x300')
        self.assertEqual(dec['action'], 'push')

    def test_scale_plan_raises_without_panel(self):
        with self.assertRaises(pf.PreflightError):
            pf.scale_plan('800x480', '')


class TestFont(unittest.TestCase):
    def test_builtin_font_below_threshold_is_no_cjk(self):
        fonts = [{'dir': '/etc/font', 'name': 'fzcircle.ttf', 'sizeBytes': 21 * 1024}]
        v = pf.font_verdict(fonts)
        self.assertEqual(v['verdict'], 'no_cjk')
        self.assertAlmostEqual(v['sizeKB'], 21.0, places=1)

    def test_builtin_font_above_threshold_is_ok(self):
        fonts = [{'dir': '/etc/font', 'name': 'fzcircle.ttf', 'sizeBytes': 900 * 1024}]
        self.assertEqual(pf.font_verdict(fonts)['verdict'], 'cjk_ok')

    def test_builtin_font_absent_is_not_found(self):
        v = pf.font_verdict([])
        self.assertEqual(v['verdict'], 'not_found')
        self.assertIn('fzcircle', v['path'])

    def test_project_cjk_classification(self):
        tmp = tempfile.mkdtemp(prefix='pfproj_')
        self.addCleanup(shutil.rmtree, tmp, True)
        os.makedirs(os.path.join(tmp, 'ui'))
        # 常用字（GB2312）/ 仅 GBK / 仅 GB18030 各一个
        data = {'textview__1': {'text': '温'},          # GB2312（常用）
                'textview__2': {'text': '垚'},          # 仅 GBK
                'textview__3': {'caption': '㐀'},        # GBK 也没有 → 更外
                'image__4': {'backgroundPic': 'images/中文图.png'}}   # 不是文案键 → 不该计入
        io.open(os.path.join(tmp, 'ui', 'main.json'), 'w', encoding='utf-8').write(
            json.dumps(data, ensure_ascii=False))
        cj = pf.project_cjk(tmp)
        self.assertEqual(cj['totalChars'], 3)
        self.assertEqual((cj['gb2312'], cj['gbk'], cj['beyond']), (1, 1, 1))

    def test_pick_tier_returns_valid_tier(self):
        r = pf.pick_font_tier(TPL)
        self.assertIn(r['tier'], P.tier_order() + ['none'])
        self.assertTrue(r['evidence'])

    def test_rare_char_escalates_tier(self):
        tmp = tempfile.mkdtemp(prefix='pfproj_')
        self.addCleanup(shutil.rmtree, tmp, True)
        os.makedirs(os.path.join(tmp, 'ui'))
        io.open(os.path.join(tmp, 'ui', 'main.json'), 'w', encoding='utf-8').write(
            json.dumps({'textview__1': {'text': '㐀'}}, ensure_ascii=False))
        r = pf.pick_font_tier(tmp)                    # 扩展字 → 最小档不够
        self.assertIn(r['tier'], ('full', 'multi'))
        self.assertGreater(r['tierBytes'] or 0, 0)


class TestBudget(unittest.TestCase):
    def _proj(self, res_bytes=0, lib_bytes=0):
        tmp = tempfile.mkdtemp(prefix='pfbud_')
        self.addCleanup(shutil.rmtree, tmp, True)
        if res_bytes:
            os.makedirs(os.path.join(tmp, 'resources'))
            with io.open(os.path.join(tmp, 'resources', 'blob.bin'), 'wb') as fh:
                fh.write(b'\0' * res_bytes)
        if lib_bytes:
            os.makedirs(os.path.join(tmp, '.fun', 'v85x'))
            with io.open(os.path.join(tmp, '.fun', 'v85x', 'libzkgui.so'), 'wb') as fh:
                fh.write(b'\0' * lib_bytes)
        return tmp

    def test_small_project_is_ok(self):
        b = pf.budget_usage(self._proj(1024), 'V85X')
        self.assertEqual(b['level'], 'ok')
        self.assertEqual(b['limitMB'], 8.0)

    def test_near_and_over_thresholds(self):
        near = pf.budget_usage(self._proj(int(7.5 * 1048576)), 'V85X')
        self.assertEqual(near['level'], 'near')
        over = pf.budget_usage(self._proj(int(8.5 * 1048576)), 'V85X')
        self.assertEqual(over['level'], 'over')
        self.assertTrue(over['warnings'])

    def test_lib_counts_toward_budget(self):
        b = pf.budget_usage(self._proj(1024, 4 * 1048576), 'V85X')
        self.assertAlmostEqual(b['usedMB'], 4.0, places=1)
        self.assertTrue(any(p['path'].endswith('libzkgui.so') for p in b['parts']))

    def test_unknown_platform_falls_back_to_default(self):
        self.assertEqual(P.budget_limit_mb('不存在的平台'), 8.0)


class TestDerived(unittest.TestCase):
    def test_page_matches_registry(self):
        p = subprocess.run([sys.executable, os.path.join(BASE, 'scripts', 'gen_preflight_doc.py'),
                            '--check'], capture_output=True, cwd=BASE, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout.decode('utf-8', 'replace'))

    def test_op_is_registered(self):
        import kb_tools
        self.assertIn('flythings_device_preflight', kb_tools.OP_NAMES)
        self.assertTrue(callable(getattr(kb_tools, 'flythings_device_preflight', None)))


if __name__ == '__main__':
    unittest.main()
