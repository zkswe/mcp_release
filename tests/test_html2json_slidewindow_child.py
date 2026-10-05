# -*- coding: utf-8 -*-
"""slidewindow 子内容的**生成侧**口径（2026-10-05，不静默）：

`slidewindow` 的直接子内容**只能是图标项**（进 `items[]`）。HTML 里塞了控件 class 或绝对定位时，
生成器本来也只能把它当图标项（`data-x/y/w/h` 与控件行为全丢）—— 但**以前不吭声**
（warnings 里只有 iconSize 那条），看返回体以为「控件放上去了」。

本文件钉住两件事：
  ① 说清楚：控件 class / 带定位的 div 进了 slidewindow → warnings 必须点名「已按图标项处理」+ 给修法；
  ② 结构上永远产不出「平铺子控件键」—— 那种结构会被 `check_all` #2 / `ui_compile` TREE002 判非法
     （真机出处：`templates/DemoControls_V85X/ui/main.json` 的 7 个磁贴按钮）。
"""
import io
import json
import os
import unittest

import _util as U

import html2json as H

BAD_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  html, body { margin: 0; padding: 0; background: #10151F; }
</style></head><body>
  <div class="screen" data-page="p" data-res="480x800">
    <div class="slidewindow" data-x="0" data-y="96" data-w="240" data-h="700"
         data-cols="1" data-rows="1" data-icon-w="40" data-icon-h="40">
      <div class="button" data-x="8" data-y="8" data-w="200" data-h="96">文本控件</div>
      <div class="item" data-pic="menu_text.png">合法图标项</div>
    </div>
  </div>
</body></html>
"""

GOOD_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  html, body { margin: 0; padding: 0; background: #10151F; }
</style></head><body>
  <div class="screen" data-page="p" data-res="480x800">
    <div class="slidewindow" data-x="0" data-y="96" data-w="240" data-h="700"
         data-cols="1" data-rows="1" data-icon-w="40" data-icon-h="40">
      <div class="item" data-pic="menu_text.png">合法图标项</div>
    </div>
  </div>
</body></html>
"""

NOTICE = 'slidewindow 的子内容只能是图标项'


class SlidewindowChildNotice(unittest.TestCase):
    def setUp(self):
        self.tmp = U.project()

    def tearDown(self):
        U.cleanup(self.tmp)

    def conv(self, html):
        src = os.path.join(self.tmp, 'ui', 'p.html')
        U.write(src, html)
        dst = os.path.join(self.tmp, 'ui', 'p.json')
        r = H.html2json(src, dst, res='480x800')
        self.assertTrue(r['success'], r)
        with io.open(dst, encoding='utf-8') as f:
            return r, json.load(f)

    def notices(self, report):
        return [w for w in (report.get('warnings') or []) if NOTICE in w]

    def test_control_class_inside_slidewindow_is_reported(self):
        """坏例：`div.button` 塞进 slidewindow → 必须回一条可执行的告警（不再静默吞掉）。"""
        r, d = self.conv(BAD_HTML)
        sw = d['slidewindow__1']
        self.assertEqual([k for k in sw if '__' in k], [],
                         '产出了平铺子控件键（结构性非法：check_all #2 / ui_compile TREE002 会判红）')
        self.assertTrue(sw.get('items'), '子内容应当收进 items[]')
        got = self.notices(r)
        self.assertEqual(len(got), 1, r.get('warnings'))
        self.assertIn('class="button"', got[0])
        self.assertIn('window 容器', got[0], '要说清修法（改用 window 容器 / 写 div.item）')

    def test_legal_item_does_not_warn(self):
        """好例：只写 `div.item` → 不该有这条告警（判据不能见 slidewindow 就报）。"""
        r, d = self.conv(GOOD_HTML)
        self.assertEqual(self.notices(r), [], r.get('warnings'))
        self.assertEqual(len(d['slidewindow__1']['items']), 1)

    def test_notice_wording_is_actionable(self):
        """告警必须同时说「已按什么处理」和「该怎么做」（否则等于没说）。"""
        r, _d = self.conv(BAD_HTML)
        msg = self.notices(r)[0]
        self.assertIn('已按图标项处理', msg)
        self.assertIn('div.item', msg)


if __name__ == '__main__':
    unittest.main()
