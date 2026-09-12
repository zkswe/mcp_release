# -*- coding: utf-8 -*-
"""预览页多整屏窗口契约（v0.27.35）：整屏 window + showWnd() 架构下 .preview.html
必须能切页 / hash 直达 / 用幽灵框看到隐藏窗口。

为什么要有：AI 反馈复现 —— 旧预览把所有 visible=false 的窗口 `display:none`，
「整屏 window + showWnd() 切页」这种官方推荐架构下客户确认稿只能看到首页，等于失效。
这里钉住四条行为（含一个真实踩过的注入 bug），防回归。
"""
import io
import json
import os
import unittest

import _util as U


def win(i, cap, vis=True, w=800, h=480):
    """整屏 window 骨架（position 覆盖全屏 → 会被判定为「页面」）。"""
    return {
        'id': i, 'caption': cap, 'visible': vis, 'touchable': False,
        'position': {'left': 0, 'top': 0, 'width': w, 'height': h},
        'backgroundColor': 3355443,
        'textview__%d' % (i + 1): {
            'id': i + 1, 'caption': 'tip', 'text': '%s 内容' % cap, 'visible': True,
            'touchable': False,
            'position': {'left': 20, 'top': 20, 'width': 300, 'height': 40},
            'fontSize': 24, 'colorTab': {'color0': 16777215},
        },
    }


class PreviewBase(unittest.TestCase):
    W, H = 800, 480

    def setUp(self):
        self.tmp = U.project()
        self.ui = os.path.join(self.tmp, 'ui')

    def tearDown(self):
        U.cleanup(self.tmp)

    def preview(self, name, controls):
        doc = {'id': 0, 'position': {'left': 0, 'top': 0},
               'resolution': {'width': self.W, 'height': self.H},
               'backgroundColor': 3355443}
        doc.update(controls)
        jp = os.path.join(self.ui, name)
        U.write(jp, json.dumps(doc, ensure_ascii=False, indent=2))
        r = U.jcall('flythings_json_to_html', {'target': self.tmp})
        self.assertTrue(r['ok'], r)
        hp = jp[:-5] + '.preview.html'
        self.assertTrue(os.path.isfile(hp), '预览稿未生成: %s' % r)
        return io.open(hp, encoding='utf-8').read()


class TestMultiWindowPreview(PreviewBase):
    def _three_pages(self):
        return self.preview('main.json', {
            'window__1': win(1, '第一页'),
            'window__2': win(2, '第二页', vis=False),
            'window__3': win(3, '第三页', vis=False, w=400, h=200),   # 非整屏 → 不算页面
        })

    def test_page_bar_lists_screen_windows_only(self):
        html = self._three_pages()
        self.assertIn('id="pg-nav"', html, '多整屏 window 必须出页面切换条')
        self.assertIn('data-win="window__1"', html)
        self.assertIn('data-win="window__2"', html)
        self.assertNotIn('data-win="window__3"', html, '非整屏窗口不该进页签')
        self.assertIn('data-topwin="1"', html, '顶层窗口要带页面标记')

    def test_default_page_is_first_visible_literal(self):
        """默认页注入必须是合法 JS 字面量——曾误用 json.dumps 写出 '"window__1"'（带引号），
        导致 active 匹配不上、所有窗口被隐藏（默认页空白）。"""
        html = self._three_pages()
        self.assertIn('active=fromHash() || "window__1";', html)
        self.assertNotIn('|| \'"window__1"\'', html, '默认页被注入成带引号字符串')

    def test_hash_jump_supported(self):
        html = self._three_pages()
        self.assertIn('location.hash', html)
        self.assertIn('hashchange', html)
        self.assertIn('window__', html.split('fromHash')[1][:400], 'hash 要认 window__N')

    def test_ghost_toggle_present(self):
        html = self._three_pages()
        self.assertIn('id="pg-ghost"', html, '缺「显示隐藏」幽灵框开关')
        self.assertIn('pg-ghost', html)


class TestSingleWindowNoRegression(PreviewBase):
    def test_single_page_without_hidden_has_no_bar(self):
        html = self.preview('single.json', {'window__1': win(1, '唯一页')})
        self.assertNotIn('pgnav', html, '单页且无隐藏控件 → 不该多出切换条')

    def test_hidden_dialog_gets_ghost_toggle_only(self):
        html = self.preview('dialog.json', {
            'window__1': win(1, '主页'),
            'window__9': win(9, '弹窗', vis=False, w=400, h=200),
        })
        self.assertIn('id="pg-ghost"', html)
        self.assertNotIn('data-win=', html, '只有一个整屏窗口 → 不该出页签')


class TestEditorUnaffected(PreviewBase):
    def test_ui_editor_keeps_its_own_ghost_and_no_page_bar(self):
        # 先有 json（编辑器默认输出到 <ui>/_edit/，故断言用返回体里的真实路径）
        self.preview('main.json', {'window__1': win(1, '第一页'),
                                   'window__2': win(2, '第二页', vis=False)})
        r = U.jcall('flythings_ui_editor', {'project_root': self.tmp})
        self.assertTrue(r['ok'], r)
        self.assertTrue(r['files'], r)
        hp = r['files'][0]['html']
        self.assertTrue(os.path.isfile(hp), r)
        html = io.open(hp, encoding='utf-8').read()
        self.assertNotIn('pgnav', html, '编辑器不该被塞入预览页切换条')
        self.assertIn('ed-ghost', html, '编辑器自带 ghost 行为')


if __name__ == '__main__':
    unittest.main(verbosity=2)
