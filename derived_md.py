# -*- coding: utf-8 -*-
"""派生 markdown 的比较口径：抹掉**纯格式差异**，只比语义。

为什么要有它（2026-10-02 实测教训）：派生文档（如
`knowledge/devflow/platform-capability-matrix.md`）是给人看的，人自然会用编辑器打开、
顺手跑一次 markdown 格式化——于是引入表格对齐空格、行尾空白、`---` → `\\---` 转义等。
这些都不该让 `--check` 变红（那是纯噪音，会逼着人去"修"一个本来就正确的东西）；
但**内容漂移必须照旧抓到**，否则派生门禁就废了。

所以口径：比较前两侧都过一遍 `normalize()`——
  · 统一行尾、去掉行尾空白
  · 表格行按单元格重建（对齐填充不算差异）
  · `\\---` 与 `---` 等价（格式化器会转义 front-matter 分隔符）
  · 折叠行尾连续空白与文末空行

用法：
    import derived_md
    if derived_md.normalize(current) != derived_md.normalize(want):
        ...  # 真漂移
"""
import re

_ESCAPED = (('\\---', '---'), ('\\-', '-'))


def normalize(text):
    """把 markdown 规范化到"只比语义"的形态。"""
    t = (text or '').replace('\r\n', '\n')
    for a, b in _ESCAPED:
        t = t.replace(a, b)
    out = []
    for ln in t.split('\n'):
        s = ln.rstrip().rstrip('\u00a0')
        st = s.lstrip()
        if st.startswith('|') and s.count('|') >= 2:
            cells = [c.strip() for c in s.strip().strip('|').split('|')]
            s = '| ' + ' | '.join(cells) + ' |'
        out.append(s)
    return '\n'.join(out).strip()


def same(a, b):
    """两份派生文本在语义上是否一致。"""
    return normalize(a) == normalize(b)
