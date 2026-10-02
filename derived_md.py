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
import io
import json
import os
import re
import subprocess

_ESCAPED = (('\\---', '---'), ('\\-', '-'))


def verified_day(src_path, key='updated', why=None):
    """派生页 front-matter 的 `verified_at` = **真源的"最后变动日"**。

    ⚠️ 两条都不能用：
      · `date.today()` —— 每天 `--check` 都报漂移（内容没变却要重生成）；
      · 文件 `mtime` —— 新克隆的仓库里 mtime = 检出时间，CI/新机器上必红。
    所以取值顺序：① 真源 JSON 里的 `updated` 字段（作者显式声明的口径日）
                 ② 该文件**最后一次 git 提交的日期**（跨克隆稳定）
                 ③ 兜底才用 mtime（不在 git 仓库里时）
    """
    # `why`（可选）收集每级失败原因：不吞异常，排查时能看出实际落到哪一级
    def _note(msg):
        if why is not None:
            why.append(msg)
    try:
        with io.open(src_path, encoding='utf-8') as fh:
            day = (json.loads(fh.read()) or {}).get(key)
        if day:
            return str(day)[:10]
        _note('真源无 %s 字段 → 退到 git 提交日' % key)
    except (OSError, ValueError) as e:
        _note('读真源 %s 失败（%s）→ 退到 git 提交日' % (key, type(e).__name__))
    try:
        out = subprocess.run(['git', 'log', '-1', '--format=%ad', '--date=short', '--',
                              src_path],
                             cwd=os.path.dirname(os.path.abspath(src_path)),
                             capture_output=True, timeout=20)
        day = (out.stdout or b'').decode('utf-8', 'replace').strip()
        if day:
            return day
        _note('git 无提交记录/不在仓库 → 退到 mtime')
    except (OSError, subprocess.SubprocessError) as e:
        _note('git 调用失败（%s）→ 退到 mtime' % type(e).__name__)
    import datetime
    return datetime.date.fromtimestamp(os.path.getmtime(src_path)).isoformat()


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
