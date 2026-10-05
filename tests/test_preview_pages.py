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
        r = U.jcall('flythings_ui_preview', {'target': self.tmp})
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
        r = U.jcall('flythings_ui_visual', {'action': 'editor', 'project_root': self.tmp})
        self.assertTrue(r['ok'], r)
        self.assertTrue(r['files'], r)
        hp = r['files'][0]['html']
        self.assertTrue(os.path.isfile(hp), r)
        html = io.open(hp, encoding='utf-8').read()
        self.assertNotIn('pgnav', html, '编辑器不该被塞入预览页切换条')
        self.assertIn('ed-ghost', html, '编辑器自带 ghost 行为')


class TestPreviewImages(PreviewBase):
    """`with_images=True`：同一批 json 出**引擎等价 PNG 展示图**（2026-10-05 加）。

    口径：HTML 仍是**确认稿身份**（硬闸门只认 `.confirm.html`/`.preview.html`），
    PNG 是"给人看效果"的展示层 —— 走同一个 `json2img` 渲染器（设备引擎语义），
    比 HTML/CSS 近似渲染更贴真机。**默认关**（AI 自检不付渲染成本）。
    """

    def _mk(self):
        return self.preview('main.json', {'window__1': win(1, '第一页'),
                                          'window__2': win(2, '第二页', vis=False)})

    def test_default_has_no_images_key(self):
        """默认不产图：返回体不许出现 images 键（行为与加该参数之前逐字节一致）。"""
        self._mk()
        r = U.jcall('flythings_ui_preview', {'target': self.tmp})
        self.assertTrue(r['ok'], r)
        self.assertNotIn('images', r)
        self.assertFalse(os.path.isdir(os.path.join(self.ui, '_preview')),
                         '默认关时不该建展示图目录')

    def test_with_images_renders_png_per_page(self):
        """开 with_images：每页一张真 PNG，尺寸 = 工程分辨率。"""
        self._mk()
        r = U.jcall('flythings_ui_preview', {'target': self.tmp, 'with_images': True})
        self.assertTrue(r['ok'], r)
        img = r.get('images') or {}
        self.assertIsNone(img.get('error'), img)
        files = img.get('files') or []
        self.assertEqual(len(files), 1, '只有 main.json 一页 → 一张图：%s' % files)
        png = files[0]['png']
        self.assertTrue(os.path.isfile(png), png)
        self.assertEqual(files[0]['size'], [self.W, self.H])
        with open(png, 'rb') as f:
            self.assertEqual(f.read(8), b'\x89PNG\r\n\x1a\n', '不是有效 PNG')
        self.assertIn(os.path.join('ui', '_preview'), img['dir'],
                      '展示图落点应为 <项目>/ui/_preview（与 ui_visual render 的 _render 分开）')

    def test_html_draft_identity_unchanged(self):
        """开图不影响确认稿身份：HTML 照出、指纹照落、闸门判定不变。"""
        self._mk()
        r = U.jcall('flythings_ui_preview', {'target': self.tmp, 'for_customer': True,
                                            'with_images': True})
        self.assertTrue(r['ok'], r)
        self.assertTrue(r.get('confirmDraft'), r)
        self.assertEqual(r.get('confirmReason'), '', r)
        self.assertTrue(os.path.isfile(r['confirmDraft']))
        self.assertIn('.confirm.html', r['confirmDraft'])

    def test_render_failure_is_not_silent(self):
        """渲染失败要如实报（images.error + hint），不许返回空 files 当成功。"""
        self._mk()
        import kb_tools as K
        orig = K._ui_render
        try:
            K._ui_render = lambda *a, **kw: json.dumps(
                {'success': False, 'error': 'json2img 失败 rc=2', 'stdout': 'boom'})
            r = U.jcall('flythings_ui_preview', {'target': self.tmp, 'with_images': True})
            img = r.get('images') or {}
            self.assertTrue(img.get('error'), '渲染失败必须带 error：%s' % r)
            self.assertEqual(img.get('files'), [])
            self.assertTrue(img.get('hint'), '失败要给可执行下一步')
        finally:
            K._ui_render = orig


if __name__ == '__main__':
    unittest.main(verbosity=2)
