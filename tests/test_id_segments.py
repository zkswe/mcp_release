# -*- coding: utf-8 -*-
"""控件 id 分区契约（2026-10-05 立）。

为什么必须有这一组（实测背景）：
  · `ui_tools/check_all.py` #5 **按 id 段推断回调**：`20000 ≤ id < 30000` ⇒ 必须有
    `onButtonClick_<caption>`；`51000 ≤ id < 52000` ⇒ 必须有 `onEditTextChanged_<caption>`；
  · 而 `html2json.ID_BASE` 曾经把 checkbox=21000 / radiobutton=22000 / slidetext=51000
    放进这两条带 → 静态全检会给 checkbox 要一个 `onButtonClick_`（语义错的回调）；
  · 文档表（`knowledge/uicontrols/layout-audit.md` §3）还另有 3 处与实测/代码矛盾
    （listview 70000 vs 实测 80001、radiogroup 81000 vs 94001、checkbox 80000 vs 94502）——
    生成器/AI 照它写 id 就会写错。**同一事实两份表，必然漂**：现在两份都由本用例钉住。

三条判据：
  ① 硬约束带里不许有"非该语义"的类型（例外只有数组子项，它们进不了 #5）；
  ② 文档表 == 代码表（解析 md 表格逐条比）；
  ③ 仓内 `templates/**` 的实际 id 必须 ≥ 该类型段（新建工程/演示工程的 id 是给人抄的样板）。
"""
import glob
import io
import json
import os
import re
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
for _p in (BASE, os.path.join(BASE, 'ui_tools'), TESTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import html2json as H                                       # noqa: E402

DOC = os.path.join(BASE, 'knowledge', 'uicontrols', 'layout-audit.md')
# 数组子项：`check_all` 的 by_caption 只递归 dict、不遍历数组 → 不进 #5，段位可落在 button 带内
ARRAY_CHILDREN = ('subitem', 'radiobutton')
BUTTON_BAND = (20000, 30000)
EDITTEXT_BAND = (51000, 52000)
# templates/** 里允许的例外：'<相对路径>::<类型>'，每条都要写理由
TEMPLATE_ALLOW = (
    # 例：('templates/X/ui/y.json::textview', '为什么可以不在段里'),
)


def _doc_rows():
    """解析文档 §3 表：{类型: 起始 id}。"""
    txt = io.open(DOC, encoding='utf-8').read()
    sec = txt.split('## 3. 控件 id 段', 1)
    assert len(sec) == 2, '文档里找不到「## 3. 控件 id 段」小节'
    body = sec[1].split('\n## ', 1)[0]
    out = {}
    for line in body.splitlines():
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        for i in range(0, len(cells) - 1, 2):
            name, val = cells[i], cells[i + 1]
            m = re.match(r'^([a-z]+)$', name)
            mv = re.match(r'^(\d+)', val)
            if m and mv:
                out[m.group(1)] = int(mv.group(1))
    return out


class TestIdSegments(unittest.TestCase):

    def test_hard_bands_hold_only_their_own_types(self):
        """硬约束带里不许有非 button / 非 edittext 类型（数组子项例外）。"""
        bad = []
        for t, seg in sorted(H.ID_BASE.items()):
            if t == 'button':
                continue
            if BUTTON_BAND[0] <= seg < BUTTON_BAND[1] and t not in ARRAY_CHILDREN:
                bad.append('%s=%d 落在 button 带 [%d,%d) → #5 会给它要 onButtonClick_'
                           % (t, seg, BUTTON_BAND[0], BUTTON_BAND[1]))
            if t == 'edittext':
                continue
            if EDITTEXT_BAND[0] <= seg < EDITTEXT_BAND[1] and t not in ARRAY_CHILDREN:
                bad.append('%s=%d 落在 edittext 带 [%d,%d) → #5 会给它要 onEditTextChanged_'
                           % (t, seg, EDITTEXT_BAND[0], EDITTEXT_BAND[1]))
        self.assertEqual(bad, [])

    def test_segments_are_unique(self):
        """两个类型不许共用同一段起点（否则段位失去区分力）。"""
        seen = {}
        for t, seg in sorted(H.ID_BASE.items()):
            if t in ARRAY_CHILDREN:                 # 子项与其它类型共用段位是有意的
                continue
            if seg in seen:
                self.fail('段位撞车：%s 与 %s 都是 %d' % (t, seen[seg], seg))
            seen[seg] = t

    def test_doc_table_matches_code(self):
        """文档表 == 代码表（同一事实两处写，必须逐条一致）。"""
        doc = _doc_rows()
        self.assertTrue(doc, '文档 §3 表没解析出任何行')
        missing = sorted(set(H.ID_BASE) - set(doc))
        extra = sorted(set(doc) - set(H.ID_BASE))
        self.assertEqual(missing, [], '文档缺这些类型：%s' % missing)
        self.assertEqual(extra, [], '文档多了这些类型：%s' % extra)
        diff = ['%s 文档=%d 代码=%d' % (t, doc[t], H.ID_BASE[t])
                for t in sorted(doc) if doc[t] != H.ID_BASE[t]]
        self.assertEqual(diff, [], '文档与代码段位不一致：%s' % '; '.join(diff))

    def test_template_pages_respect_segments(self):
        """`templates/**` 的实际 id 必须 ≥ 该类型段（样板工程要能被人抄）。

        ⚠️ 读不了的文件**不静默跳过**（DESIGN_SPEC 第 3 条）：记进 `unreadable` 一起断言。
        """
        bad, unreadable = [], []
        for p in sorted(glob.glob(os.path.join(BASE, 'templates', '**', '*.json'),
                                  recursive=True)):
            if os.sep + 'ui' + os.sep not in p:
                continue
            rel = os.path.relpath(p, BASE).replace(os.sep, '/')
            try:
                with io.open(p, encoding='utf-8-sig') as f:
                    d = json.load(f)
            except (OSError, ValueError) as e:
                unreadable.append('%s（%s: %s）' % (rel, type(e).__name__, e))
                continue

            def walk(o):
                if isinstance(o, dict):
                    for k, v in o.items():
                        if isinstance(v, dict) and '__' in k:
                            t = k.split('__')[0]
                            i = v.get('id')
                            seg = H.ID_BASE.get(t)
                            if isinstance(i, int) and seg is not None and i < seg:
                                tag = '%s::%s' % (rel, t)
                                if not any(a == tag for a in TEMPLATE_ALLOW):
                                    bad.append('%s %s id=%d < 段 %d' % (rel, k, i, seg))
                            walk(v)
                        elif isinstance(v, list):
                            for x in v:
                                walk(x)
            walk(d)
        self.assertEqual(unreadable, [], '这些 json 读不了（等于没查）：%s' % unreadable)
        self.assertEqual(bad, [], '样板工程的 id 不在段内：\n  ' + '\n  '.join(bad[:20]))


if __name__ == '__main__':
    unittest.main()
