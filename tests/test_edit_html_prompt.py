# -*- coding: utf-8 -*-
"""edit.html「复制 AI 指令」闭环契约用例（离线，走分发器同一条路径）。

背景（2026-09-12 钟工反馈）：edit.html 是本地静态文件，**没有回传通道**，
用户改完只能复制粘贴给 AI。所以页面必须：
  ① 有「复制 AI 指令」按钮，且说明文案写清「复制粘贴给 AI」这条落地方式；
  ② 复制出来的指令要自带 **工程路径 + 目标 json + 变更 JSON**（AI 拿到即可 flythings_ui_edit_apply）；
  ③ 没有改动时不给空指令（按钮提示「暂无改动」）；
  ④ 工具返回的 note 同步更新这条口径。
DOM 级实跑（拖动→点按钮→读剪贴板/文本框）在 temp/al_test/probe3.py，这里只钉住产物内容。
"""
import io
import json
import os
import unittest

import _util


MIN_JSON = {
    "id": 0,
    "resolution": {"width": 480, "height": 320},
    "position": {"left": 0, "top": 0, "width": 480, "height": 320},
    "window__1": {
        "id": 1,
        "type": "window",
        "caption": "main",
        "position": {"left": 0, "top": 0, "width": 480, "height": 320},
        "visible": True,
        "textview__1": {
            "id": 2, "type": "textview", "caption": "title", "text": "hello",
            "alignment": 37, "fontSize": 20, "color": {"red": 255, "green": 255, "blue": 255},
            "position": {"left": 10, "top": 10, "width": 200, "height": 40},
        },
    },
}


class EditHtmlAiPrompt(unittest.TestCase):
    def setUp(self):
        self.tmp = _util.project()
        _util.write(os.path.join(self.tmp, 'ui', 'main.json'),
                    json.dumps(MIN_JSON, ensure_ascii=False, indent=1))

    def tearDown(self):
        _util.cleanup(self.tmp)

    def _gen(self):
        r = _util.jcall('flythings_ui_editor', {'project_root': self.tmp})
        self.assertTrue(r.get('success'), r)
        html = r['files'][0]['html']
        with io.open(html, encoding='utf-8') as f:
            return r, f.read()

    def test_button_and_hint_present(self):
        _r, doc = self._gen()
        self.assertIn('data-a="copyai"', doc)
        self.assertIn('复制 AI 指令', doc)
        self.assertIn('flythings_ui_edit_apply', doc)
        self.assertIn('回传通道', doc)          # 明说「必须复制粘贴」
        self.assertIn('__edAiPrompt', doc)     # 可被测/被自动化取用

    def test_prompt_carries_project_path_and_json(self):
        _r, doc = self._gen()
        os.environ['NO_PROBE'] = '1'
        # 直接从源码里取 aiPrompt 的模板行，确认字段齐全（DOM 实跑见 probe3.py）
        self.assertIn('projectRoot', doc)
        self.assertIn('jsonRel', doc)
        for needle in ('项目根目录', '目标 json', '变更 JSON', 'flythings_ui_edit_apply'):
            self.assertIn(needle, doc)
        # META 里必须真的带上工程根（否则指令里的路径是空的）
        self.assertIn('C:', doc) if os.name == 'nt' else self.assertIn('/tmp', doc)

    def test_meta_has_project_root_and_rel_json(self):
        _r, doc = self._gen()
        m = doc.split('var META = ')[1].split(';\n')[0]
        meta = json.loads(m)
        self.assertEqual(os.path.abspath(meta['projectRoot']), os.path.abspath(self.tmp))
        self.assertEqual(meta['jsonRel'], 'ui/main.json')

    def test_tool_note_mentions_copy_ai(self):
        r = _util.jcall('flythings_ui_editor', {'project_root': self.tmp})
        self.assertIn('复制 AI 指令', r.get('note', ''))


if __name__ == '__main__':
    unittest.main()
