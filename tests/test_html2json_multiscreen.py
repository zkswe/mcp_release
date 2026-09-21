# -*- coding: utf-8 -*-
"""多屏设计稿契约（v0.27.99）：**页数 = 屏数，一屏不许丢**。

为什么要有（2026-09-21 钟工「现在改」的实际事故）：`html2json` 的旧实现
`_find_screen()` 递归找到**第一个** `div.screen` 就 return，`convert()` 只遍历该屏的子节点
→ 用户按 `prototype-flow.md` 写法交的多屏原型（每屏一个 `.screen` + `data-page`）**只落成第一页**，
且返回体里**零提示**（实测 2 屏 → controls=2，warnings 不提第二屏）。

本用例钉住四条行为（防回归）：
  1. 单屏 HTML：产物逐字段与改动前一致（黄金样例），且返回体带 screensDetected/pagesProduced=1，
     不多加任何多屏 warning；
  2. 多屏默认口径 = 同一个 json 内 N 个整屏 window（window__1..window__N 连续编号，
     首屏 visible:true、其余 false），warnings 逐条列「识别到的页」；
  3. split_per_page=True（CLI --split-per-page）= 每屏一个 json，文件名取 data-page，
     且每份是普通单屏 json（无整屏 window 包裹）；
  4. 反例：屏数 != 产出页数（嵌套 .screen / split 页名重复）**必须 success:false**（禁止再静默丢页）。
"""
import io
import json
import os
import unittest

import _util as U

import html2json as H

SINGLE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>.screen { position: relative; }</style></head><body>
<!-- ===== PAGE: home ===== -->
<div class="screen" data-page="home" data-page-name="home_page" data-res="800x480" data-bg="#808080">
  <div class="text" data-caption="TitleBar" data-x="0" data-y="0" data-w="800" data-h="48">HOME</div>
  <div class="btn" data-caption="BtnGo" data-x="40" data-y="120" data-w="320" data-h="80">GO_DETAIL</div>
</div>
</body></html>
"""

# 单屏黄金样例：v0.27.98 前（改动前）转换器的逐字段产物，本次改动必须零差异
SINGLE_GOLDEN = {
    'beepEnable': True, 'id': 0,
    'resolution': {'height': 480, 'width': 800}, 'topmost': False,
    'backgroundColor': 8421504,
    'position': {'height': 480, 'left': 0, 'top': 0, 'width': 800},
    'textview__1': {'alignment': 36, 'caption': 'TitleBar', 'colorTab': {'color0': 15659766},
                    'fontSize': 16, 'id': 50001,
                    'position': {'height': 48, 'left': 0, 'top': 0, 'width': 800},
                    'touchable': False, 'text': 'HOME'},
    'button__2': {'alignment': 37, 'caption': 'BtnGo', 'colorTab': {'color0': 15659766},
                  'id': 20001,
                  'position': {'height': 80, 'left': 40, 'top': 120, 'width': 320},
                  'touchable': True, 'bgColorTab': {'color0': 3621975},
                  'text': 'GO_DETAIL', 'picTab': {}},
}

TWO_SCREEN_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>.screen { position: relative; }</style></head><body>
<!-- ===== PAGE: home ===== -->
<div class="screen" data-page="home" data-page-name="home_page" data-res="800x480" data-bg="#808080">
  <div class="text" data-caption="TitleBar" data-x="0" data-y="0" data-w="800" data-h="48">HOME</div>
  <div class="btn" data-caption="BtnGo" data-x="40" data-y="120" data-w="320" data-h="80">GO_DETAIL</div>
</div>
<!-- ===== PAGE: detail ===== -->
<div class="screen" data-page="detail" data-page-name="detail_page" data-res="800x480" data-bg="#A0A0A0">
  <div class="text" data-caption="DetailTitle" data-x="0" data-y="0" data-w="800" data-h="48">DETAIL</div>
  <div class="btn" data-caption="BtnBack" data-x="40" data-y="380" data-w="200" data-h="80">BACK</div>
</div>
</body></html>
"""

NESTED_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"></head><body>
<div class="screen" data-page="home" data-res="800x480" data-bg="#808080">
  <div class="text" data-caption="A" data-x="0" data-y="0" data-w="100" data-h="40">A</div>
  <div class="screen" data-page="oops" data-res="800x480">
    <div class="text" data-caption="B" data-x="0" data-y="0" data-w="100" data-h="40">B</div>
  </div>
</div>
</body></html>
"""

DUP_PAGE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"></head><body>
<div class="screen" data-page="home" data-res="800x480" data-bg="#808080">
  <div class="text" data-caption="A" data-x="0" data-y="0" data-w="100" data-h="40">A</div>
</div>
<div class="screen" data-page="home" data-res="800x480" data-bg="#808080">
  <div class="text" data-caption="B" data-x="0" data-y="0" data-w="100" data-h="40">B</div>
</div>
</body></html>
"""


class MultiScreenBase(unittest.TestCase):
    def setUp(self):
        self.tmp = U.project()

    def tearDown(self):
        U.cleanup(self.tmp)

    def html(self, name, text):
        p = os.path.join(self.tmp, 'ui', name)
        U.write(p, text)
        return p

    def conv(self, name, text, **kw):
        """直接走 html2json()（不经 MCP 分发器）→ (返回体, json 数据)。"""
        src = self.html(name, text)
        dst = os.path.join(self.tmp, 'ui', os.path.splitext(name)[0] + '.json')
        r = H.html2json(src, dst, **kw)
        data = None
        if r.get('success') and os.path.isfile(r.get('jsonPath') or ''):
            with io.open(r['jsonPath'], encoding='utf-8') as f:
                data = json.load(f)
        return r, data


class TestSingleScreenNoRegression(MultiScreenBase):
    def test_single_screen_json_is_field_identical(self):
        """改动前逐字段一致（含键序）：多屏支持不得动单屏产物。"""
        r, data = self.conv('single.html', SINGLE_HTML)
        self.assertTrue(r['success'], r)
        self.assertEqual(list(data), list(SINGLE_GOLDEN), '顶层键序变了（单屏回归）')
        self.assertEqual(data, SINGLE_GOLDEN, '单屏产物与改动前不一致')

    def test_single_screen_return_fields(self):
        r, _ = self.conv('single.html', SINGLE_HTML)
        self.assertEqual((r['screensDetected'], r['pagesProduced']), (1, 1), r)
        self.assertEqual(r['mode'], 'single-screen', r)
        self.assertNotIn('window__1', json.dumps(r['warnings'], ensure_ascii=False),
                         '单屏不该出现多屏相关 warning')

    def test_no_screen_still_reports_zero(self):
        """完全没有 .screen → success:false 且带 0/0 屏数（不静默）。"""
        src = self.html('none.html', '<html><body><div class="text">x</div></body></html>')
        r = H.html2json(src, os.path.join(self.tmp, 'ui', 'none.json'))
        self.assertFalse(r['success'], r)
        self.assertEqual((r['screensDetected'], r['pagesProduced']), (0, 0), r)


class TestMultiScreenDefault(MultiScreenBase):
    def test_two_screens_become_two_fullscreen_windows(self):
        r, data = self.conv('multi.html', TWO_SCREEN_HTML)
        self.assertTrue(r['success'], r)
        self.assertEqual(r['screensDetected'], 2, r)
        self.assertEqual(r['pagesProduced'], 2, '屏数 != 页数（多屏被压成一页的回归）')
        self.assertEqual(r['mode'], 'multi-window', r)
        wins = [k for k in data if k.startswith('window__')]
        self.assertEqual(wins, ['window__1', 'window__2'], '整屏 window 编号不连续/缺失')
        full = {'height': 480, 'left': 0, 'top': 0, 'width': 800}
        for k in wins:
            self.assertEqual(data[k]['position'], full, '%s 不是整屏' % k)
            self.assertEqual(data[k]['modal'], False, k)
        self.assertEqual([data[k]['caption'] for k in wins], ['home', 'detail'])
        self.assertTrue(data['window__1']['visible'], '首屏必须 visible:true')
        self.assertFalse(data['window__2']['visible'], '其余屏必须 visible:false')
        # 每屏的颜色 = 自己 .screen 的 data-bg；控件落在自己的窗口内
        self.assertEqual(data['window__1']['backgroundColor'], 8421504)
        self.assertEqual(data['window__2']['backgroundColor'], 10526880)
        self.assertEqual(sorted(k for k in data['window__1'] if k.endswith('__2')
                                or k.startswith(('textview__', 'button__'))),
                         ['button__4', 'textview__3'], '第一屏控件没挂在自己窗口里')

    def test_warnings_list_every_page(self):
        r, _ = self.conv('multi.html', TWO_SCREEN_HTML)
        txt = '\n'.join(r['warnings'])
        self.assertIn('识别到 2 个 .screen', txt)
        self.assertIn('home(home_page)', txt)
        self.assertIn('detail(detail_page)', txt)
        self.assertIn('window__1', txt)
        self.assertIn('window__2', txt)
        self.assertIn('split-per-page', txt, '没提示跨业务域可改用每屏一个 json')


class TestSplitPerPage(MultiScreenBase):
    def test_split_writes_one_json_per_page_named_by_data_page(self):
        r, _ = self.conv('multi.html', TWO_SCREEN_HTML, split_per_page=True)
        self.assertTrue(r['success'], r)
        self.assertEqual(r['mode'], 'split-per-page', r)
        self.assertEqual((r['screensDetected'], r['pagesProduced']), (2, 2), r)
        files = sorted(f for f in os.listdir(os.path.join(self.tmp, 'ui'))
                       if f.endswith('.json'))
        self.assertEqual(files, ['detail.json', 'home.json'], files)
        self.assertEqual(sorted(os.path.basename(p) for p in r['jsonPaths']),
                         ['detail.json', 'home.json'])
        for pid in ('home', 'detail'):
            with io.open(os.path.join(self.tmp, 'ui', pid + '.json'), encoding='utf-8') as f:
                d = json.load(f)
            self.assertFalse([k for k in d if k.startswith('window__')],
                             '%s.json 不该有整屏 window 包裹' % pid)
            self.assertIn('textview__1', d, '%s.json 是空页' % pid)

    def test_cli_flag_equivalent(self):
        """CLI --split-per-page 与 API 等价（同一实现，不两套口径）。"""
        src = self.html('multi.html', TWO_SCREEN_HTML)
        out = os.path.join(self.tmp, 'ui2', 'multi.json')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        import subprocess
        import sys
        script = os.path.join(U.BASE, 'ui_tools', 'html2json.py')
        p = subprocess.run([sys.executable, script, src, out, '--split-per-page'],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(p.returncode, 0, p.stdout.decode('utf-8', 'replace'))
        r = json.loads(p.stdout.decode('utf-8', 'replace'))
        self.assertEqual((r['screensDetected'], r['pagesProduced']), (2, 2), r)
        self.assertEqual(sorted(os.listdir(os.path.dirname(out))),
                         ['detail.json', 'home.json'], os.listdir(os.path.dirname(out)))


class TestScreenCountGate(MultiScreenBase):
    """反例：屏数 != 产出页数 → 必须 success:false（证明不再静默丢页）。"""

    def test_nested_screen_is_error_not_silent(self):
        r, data = self.conv('nested.html', NESTED_HTML)
        self.assertFalse(r['success'], r)
        self.assertIn('嵌套', r['error'])
        self.assertEqual(r['screensDetected'], 2, r)
        self.assertLess(r['pagesProduced'], r['screensDetected'], r)
        self.assertIsNone(data, '报错了却还写出 json = 静默丢页')

    def test_duplicate_data_page_in_split_is_error(self):
        r, _ = self.conv('dup.html', DUP_PAGE_HTML, split_per_page=True)
        self.assertFalse(r['success'], r)
        self.assertIn('屏数核对失败', r['error'])
        self.assertEqual((r['screensDetected'], r['pagesProduced']), (2, 1), r)
        self.assertIn('data-page 重复', r['error'])


class TestOpWiring(MultiScreenBase):
    """MCP op 面：split_per_page 参数与返回字段（客户端拿到的东西）。"""

    def test_op_exposes_split_and_counts(self):
        src = self.html('multi.html', TWO_SCREEN_HTML)
        r = U.jcall('flythings_html_to_json', {
            'input_html': src, 'output_json': os.path.join(self.tmp, 'ui', 'multi.json')})
        self.assertTrue(r['success'], r)
        self.assertEqual((r['screensDetected'], r['pagesProduced']), (2, 2), r)
        self.assertEqual(r['mode'], 'multi-window', r)

        r2 = U.jcall('flythings_html_to_json', {
            'input_html': src, 'output_json': os.path.join(self.tmp, 'sp', 'multi.json'),
            'split_per_page': True})
        self.assertTrue(r2['success'], r2)
        self.assertEqual((r2['screensDetected'], r2['pagesProduced']), (2, 2), r2)
        self.assertEqual(r2['mode'], 'split-per-page', r2)
        self.assertEqual(sorted(os.path.basename(p) for p in r2['jsonPaths']),
                         ['detail.json', 'home.json'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
