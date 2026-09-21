# -*- coding: utf-8 -*-
"""多屏设计稿契约（v0.27.100，钟工 2026-09-21 口径）：**一个 .screen = 一个页面 = 一个 Activity
= 一个 json（-> 一个 ftu）**；**页数 = 屏数，一屏不许丢**。

口径沿革（防止再漂移）：
  - v0.27.99：多屏默认**合成同一个 json 的 N 个整屏 window**（只修掉「只落第一屏」的静默丢页）；
  - v0.27.100：钟工纠正「不是的……按照客户的设计需求，其实目前已经可以准确的做好了不同的 html
    页面分页了。哪些属于不同的 activity、哪些属于 windows/dialog 其实前期 AI 可以分清楚。分清楚的
    情况下不同的 activity 做好不同的 json 布局就好了」-> **默认改成每屏一个 json**；
    合成多整屏 window 变成**显式开关** `--merge-windows`（仅当这些屏同属一个 Activity 时用）；
    嵌套 `.screen` 从 error 降为 warning（按最外层算页 + 点名），避免既有输入突然跑不过。

本用例钉住六条行为（防回归）：
  1. 单屏 HTML：产物逐字段 + 键序与改动前黄金样例一致（回归），返回体 1/1 + jsonsProduced=1；
  2. 2 屏 HTML（缺省）：**产出 2 个 json**（文件名取 data-page），pagesProduced==2，pages 逐页列出，
     且每份 json 与「把那一屏单独拿出来转」**逐字段一致**（页之间不串味）；
  3. --merge-windows（MCP merge_windows=true）：**1 个 json** + 2 个整屏 window（首屏 visible:true、
     其余 false、caption=data-page），pages 逐页列出且多页指向同一个 json，warnings 回显「本次按
     merge-windows 合成」；
  4. 嵌套 `.screen`：**不失败**（warning + 只取最外层 + 点名嵌套屏）；
  5. 反例：屏数 != 产出页数（data-page 重复）**必须 success:false**（禁止静默丢页）；
  6. op/CLI 面：`merge_windows` 参数暴露；`--merge-windows` 与 API 等价；退役的
     `--split-per-page` 明确报错（不许静默当成默认口径）。
"""
import io
import json
import os
import subprocess
import sys
import unittest

import _util as U

import html2json as H

_HEAD = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>.screen { position: relative; }</style></head><body>
"""
_TAIL = """</body></html>
"""

HOME_SCREEN = """<!-- ===== PAGE: home ===== -->
<div class="screen" data-page="home" data-page-name="home_page" data-res="800x480" data-bg="#808080">
  <div class="text" data-caption="TitleBar" data-x="0" data-y="0" data-w="800" data-h="48">HOME</div>
  <div class="btn" data-caption="BtnGo" data-x="40" data-y="120" data-w="320" data-h="80">GO_DETAIL</div>
</div>
"""

DETAIL_SCREEN = """<!-- ===== PAGE: detail ===== -->
<div class="screen" data-page="detail" data-page-name="detail_page" data-res="800x480" data-bg="#A0A0A0">
  <div class="text" data-caption="DetailTitle" data-x="0" data-y="0" data-w="800" data-h="48">DETAIL</div>
  <div class="btn" data-caption="BtnBack" data-x="40" data-y="380" data-w="200" data-h="80">BACK</div>
</div>
"""

SINGLE_HTML = _HEAD + HOME_SCREEN + _TAIL
TWO_SCREEN_HTML = _HEAD + HOME_SCREEN + DETAIL_SCREEN + _TAIL

# 单屏黄金样例：改动前转换器的逐字段产物，本次改动必须零差异（键序也在内）
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
        """直接走 html2json()（不经 MCP 分发器）-> (返回体, 首页 json 数据, 全部 json 数据)。"""
        src = self.html(name, text)
        dst = os.path.join(self.tmp, 'ui', os.path.splitext(name)[0] + '.json')
        r = H.html2json(src, dst, **kw)
        datas = []
        if r.get('success'):
            for p in (r.get('jsonPaths') or []):
                if os.path.isfile(p):
                    with io.open(p, encoding='utf-8') as f:
                        datas.append(json.load(f))
        return r, (datas[0] if datas else None), datas

    def jsons_in_ui(self):
        d = os.path.join(self.tmp, 'ui')
        return sorted(f for f in os.listdir(d) if f.endswith('.json'))

    def load(self, name):
        with io.open(os.path.join(self.tmp, 'ui', name), encoding='utf-8') as f:
            return json.load(f)


class TestSingleScreenNoRegression(MultiScreenBase):
    def test_single_screen_json_is_field_identical(self):
        """改动前逐字段一致（含键序）：多屏口径调整不得动单屏产物。"""
        r, data, _ = self.conv('single.html', SINGLE_HTML)
        self.assertTrue(r['success'], r)
        self.assertEqual(list(data), list(SINGLE_GOLDEN), '顶层键序变了（单屏回归）')
        self.assertEqual(data, SINGLE_GOLDEN, '单屏产物与改动前不一致')

    def test_single_screen_return_fields(self):
        r, _d, _all = self.conv('single.html', SINGLE_HTML)
        self.assertEqual((r['screensDetected'], r['pagesProduced']), (1, 1), r)
        self.assertEqual(r['mode'], 'single-screen', r)
        self.assertEqual(r['jsonsProduced'], 1, r)
        self.assertEqual(r['pages'], [{'page': 'home', 'json': r['jsonPath']}], r)
        self.assertTrue(r['jsonPath'].endswith('single.json'),
                        '单页仍写 output_json 指定的文件名: %s' % r['jsonPath'])
        self.assertEqual(self.jsons_in_ui(), ['single.json'], '单页不该多写文件')
        txt = '\n'.join(r['warnings'])
        self.assertNotIn('merge-windows', txt)
        self.assertNotIn('每屏一个 json', txt, '单屏不该出现多屏相关 warning')

    def test_no_screen_still_reports_zero(self):
        """完全没有 .screen -> success:false 且带 0/0 屏数（不静默）。"""
        src = self.html('none.html', '<html><body><div class="text">x</div></body></html>')
        r = H.html2json(src, os.path.join(self.tmp, 'ui', 'none.json'))
        self.assertFalse(r['success'], r)
        self.assertEqual((r['screensDetected'], r['pagesProduced']), (0, 0), r)


class TestPerScreenDefault(MultiScreenBase):
    """缺省口径：N 个 .screen -> N 个 json（一个页面 = 一个 Activity = 一个 ftu）。"""

    def test_two_screens_become_two_jsons(self):
        r, _d, datas = self.conv('multi.html', TWO_SCREEN_HTML)
        self.assertTrue(r['success'], r)
        self.assertEqual(r['screensDetected'], 2, r)
        self.assertEqual(r['pagesProduced'], 2, '屏数 != 页数（多屏被压成一页的回归）')
        self.assertEqual(r['mode'], 'per-screen', r)
        self.assertEqual(self.jsons_in_ui(), ['detail.json', 'home.json'], self.jsons_in_ui())
        self.assertEqual(r['jsonsProduced'], 2, r)
        self.assertEqual(len(datas), 2, r)
        # 禁止默认合成多整屏 window
        for d in datas:
            self.assertFalse([k for k in d if k.startswith('window__')],
                             '缺省口径不许出现整屏 window 包裹')

    def test_pages_lists_every_page_with_its_json(self):
        r, _d, _all = self.conv('multi.html', TWO_SCREEN_HTML)
        self.assertEqual([p['page'] for p in r['pages']], ['home', 'detail'], r['pages'])
        paths = [p['json'] for p in r['pages']]
        self.assertEqual([os.path.basename(p) for p in paths], ['home.json', 'detail.json'],
                         'pages 必须逐页给出自己的 json 路径（不是只列 1 条）')
        self.assertEqual(sorted(paths), sorted(r['jsonPaths']), r['jsonPaths'])
        for p in paths:
            self.assertTrue(os.path.isfile(p), p)

    def test_each_page_equals_that_screen_alone(self):
        """页之间不串味：每份 json 与「把该屏单独拿出来转」逐字段一致。"""
        _r, _d, datas = self.conv('multi.html', TWO_SCREEN_HTML)
        r1, alone1, _ = self.conv('only_home.html', SINGLE_HTML)
        self.assertTrue(r1['success'], r1)
        self.assertEqual(datas[0], alone1, 'home.json 与单独转该屏不一致')
        r2, alone2, _ = self.conv('only_detail.html', _HEAD + DETAIL_SCREEN + _TAIL)
        self.assertTrue(r2['success'], r2)
        self.assertEqual(datas[1], alone2, 'detail.json 与单独转该屏不一致')

    def test_warnings_say_per_screen_json(self):
        r, _d, _all = self.conv('multi.html', TWO_SCREEN_HTML)
        txt = '\n'.join(r['warnings'])
        self.assertIn('识别到 2 个 .screen', txt)
        self.assertIn('home(home_page)', txt)
        self.assertIn('detail(detail_page)', txt)
        self.assertIn('每屏一个 json', txt)
        self.assertIn('home.json / detail.json', txt)
        self.assertIn('window / dialog', txt, '要讲清 window/dialog 属于屏内部')
        self.assertNotIn('本次按 merge-windows 合成', txt)

    def test_output_dir_and_default_names(self):
        """output_json 写目录 / 缺省 page_k：每屏一个 json 的落点口径。"""
        src = self.html('multi.html', TWO_SCREEN_HTML.replace('data-page="detail"', ''))
        outd = os.path.join(self.tmp, 'ui2')
        r = H.html2json(src, outd)
        self.assertTrue(r['success'], r)
        self.assertEqual(sorted(os.path.basename(p) for p in r['jsonPaths']),
                         ['home.json', 'page_2.json'], r['jsonPaths'])


class TestMergeWindows(MultiScreenBase):
    """显式开关：把 N 个 .screen 合成同一 json 内的 N 个整屏 window。"""

    def test_merge_windows_one_json_two_fullscreen_windows(self):
        r, data, _all = self.conv('multi.html', TWO_SCREEN_HTML, merge_windows=True)
        self.assertTrue(r['success'], r)
        self.assertEqual(r['mode'], 'merge-windows', r)
        self.assertEqual((r['screensDetected'], r['pagesProduced']), (2, 2), r)
        self.assertEqual(r['jsonsProduced'], 1, 'merge-windows 只许写一个 json')
        self.assertEqual(self.jsons_in_ui(), ['multi.json'], self.jsons_in_ui())
        wins = [k for k in data if k.startswith('window__')]
        self.assertEqual(wins, ['window__1', 'window__2'], '整屏 window 编号不连续/缺失')
        full = {'height': 480, 'left': 0, 'top': 0, 'width': 800}
        for k in wins:
            self.assertEqual(data[k]['position'], full, '%s 不是整屏' % k)
            self.assertEqual(data[k]['modal'], False, k)
        self.assertEqual([data[k]['caption'] for k in wins], ['home', 'detail'])
        self.assertTrue(data['window__1']['visible'], '首屏必须 visible:true')
        self.assertFalse(data['window__2']['visible'], '其余屏必须 visible:false')
        self.assertEqual(data['window__1']['backgroundColor'], 8421504)
        self.assertEqual(data['window__2']['backgroundColor'], 10526880)
        self.assertEqual(sorted(k for k in data['window__1']
                                if k.startswith(('textview__', 'button__'))),
                         ['button__4', 'textview__3'], '第一屏控件没挂在自己窗口里')

    def test_pages_point_to_the_single_json(self):
        """上一版瑕疵：多窗口模式下 pages 只列 1 条 —— 现在必须逐页列全。"""
        r, _d, _all = self.conv('multi.html', TWO_SCREEN_HTML, merge_windows=True)
        self.assertEqual([p['page'] for p in r['pages']], ['home', 'detail'], r['pages'])
        self.assertEqual(len(set(p['json'] for p in r['pages'])), 1,
                         'merge-windows 下多页应指向同一个 json')

    def test_warnings_echo_merge_mode(self):
        r, _d, _all = self.conv('multi.html', TWO_SCREEN_HTML, merge_windows=True)
        txt = '\n'.join(r['warnings'])
        self.assertIn('本次按 merge-windows 合成', txt, '必须回显本次是 merge-windows 合成')
        self.assertIn('window__1', txt)
        self.assertIn('window__2', txt)
        self.assertIn('同属一个 Activity', txt)

    def test_duplicate_data_page_is_not_lost_in_merge_mode(self):
        """merge-windows 走同一道屏数闸门：重名只是两屏 caption 一样，页不许少。"""
        r, data, _all = self.conv('dup2.html', DUP_PAGE_HTML, merge_windows=True)
        self.assertTrue(r['success'], r)
        self.assertEqual((r['screensDetected'], r['pagesProduced']), (2, 2), r)
        self.assertEqual([k for k in data if k.startswith('window__')],
                         ['window__1', 'window__2'], data.keys())

    def test_merge_needs_nothing_for_single_screen(self):
        """单屏带 merge_windows 开关 = 与单屏产物逐字段一致（不白包一层 window）。"""
        r1, d1, _ = self.conv('single.html', SINGLE_HTML, merge_windows=True)
        self.assertTrue(r1['success'], r1)
        self.assertEqual(r1['mode'], 'single-screen', r1)
        self.assertEqual(d1, SINGLE_GOLDEN)


class TestNestedScreenIsWarning(MultiScreenBase):
    """嵌套 .screen：v0.27.100 起降为 warning（既有输入不许突然跑不过），但必须点名。"""

    def test_nested_is_warning_outer_only(self):
        r, data, _all = self.conv('nested.html', NESTED_HTML)
        self.assertTrue(r['success'], r)
        self.assertIsNone(r.get('error'), r)
        self.assertEqual(r['screensDetected'], 1, '只算最外层屏')
        self.assertEqual(r['pagesProduced'], 1, r)
        self.assertEqual(self.jsons_in_ui(), ['nested.json'], self.jsons_in_ui())
        self.assertFalse([k for k in data if k.startswith('window__')], data.keys())
        txt = '\n'.join(r['warnings'])
        self.assertIn('嵌套', txt)
        self.assertIn('oops', txt, '嵌套屏必须被点名（不许静默）')
        self.assertIn('最外层', txt)
        # 嵌套屏的**容器**被忽略，但屏内控件仍属于最外层页（内容不许一起丢）
        self.assertEqual(sorted(k for k in data if k.startswith('textview__')),
                         ['textview__1', 'textview__2'], data.keys())


class TestScreenCountGate(MultiScreenBase):
    """反例：屏数 != 产出页数 -> 必须 success:false（证明不再静默丢页）。"""

    def test_duplicate_data_page_is_error(self):
        r, _d, _all = self.conv('dup.html', DUP_PAGE_HTML)
        self.assertFalse(r['success'], r)
        self.assertIn('屏数核对失败', r['error'])
        self.assertEqual((r['screensDetected'], r['pagesProduced']), (2, 1), r)
        self.assertIn('data-page 重复', r['error'])
        self.assertEqual(self.jsons_in_ui(), [], '报错了却还写出 json = 静默丢页')




class TestOpAndCliWiring(MultiScreenBase):
    """MCP op 面 / CLI 面（客户端拿到的东西）。"""

    def test_op_exposes_merge_windows(self):
        args = [o for o in U.manifest()['ops'] if o['op'] == 'flythings_html_to_json'][0]['args']
        self.assertIn('merge_windows', args, args)
        self.assertNotIn('split_per_page', args, '退役参数不该还在签名里: %s' % args)

    def test_op_default_is_per_screen(self):
        src = self.html('multi.html', TWO_SCREEN_HTML)
        r = U.jcall('flythings_html_to_json', {
            'input_html': src, 'output_json': os.path.join(self.tmp, 'ui', 'multi.json')})
        self.assertTrue(r['success'], r)
        self.assertEqual((r['screensDetected'], r['pagesProduced']), (2, 2), r)
        self.assertEqual(r['mode'], 'per-screen', r)
        self.assertEqual(sorted(os.path.basename(p) for p in r['jsonPaths']),
                         ['detail.json', 'home.json'])

    def test_op_merge_windows(self):
        src = self.html('multi.html', TWO_SCREEN_HTML)
        r = U.jcall('flythings_html_to_json', {
            'input_html': src, 'output_json': os.path.join(self.tmp, 'ui', 'm.json'),
            'merge_windows': True})
        self.assertTrue(r['success'], r)
        self.assertEqual(r['mode'], 'merge-windows', r)
        self.assertEqual(r['jsonsProduced'], 1, r)
        self.assertEqual([p['page'] for p in r['pages']], ['home', 'detail'], r['pages'])

    def test_cli_merge_windows_equivalent(self):
        src = self.html('multi.html', TWO_SCREEN_HTML)
        outd = os.path.join(self.tmp, 'cli')
        os.makedirs(outd, exist_ok=True)
        script = os.path.join(U.BASE, 'ui_tools', 'html2json.py')
        p = subprocess.run([sys.executable, script, src, outd, '--merge-windows'],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = p.stdout.decode('utf-8', 'replace')
        self.assertEqual(p.returncode, 0, out)
        r = json.loads(out[out.find('{'):])
        self.assertEqual((r['screensDetected'], r['pagesProduced'], r['jsonsProduced']), (2, 2, 1), r)
        # 只给目录：merge-windows 用**首屏 data-page** 命名（同一 json，不是多份）
        self.assertEqual(os.listdir(outd), ['home.json'], os.listdir(outd))

    def test_cli_split_per_page_is_retired_with_clear_error(self):
        """退役参数不许被静默当成默认口径（会让人以为还在走旧形态）。"""
        src = self.html('multi.html', TWO_SCREEN_HTML)
        script = os.path.join(U.BASE, 'ui_tools', 'html2json.py')
        p = subprocess.run([sys.executable, script, src,
                            os.path.join(self.tmp, 'ui', 'x.json'), '--split-per-page'],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = p.stdout.decode('utf-8', 'replace')
        self.assertNotEqual(p.returncode, 0, out)
        self.assertIn('--split-per-page', out)
        self.assertIn('退役', out)


if __name__ == '__main__':
    unittest.main(verbosity=2)
