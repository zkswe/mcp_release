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

    ⚠️ 落到 ② 的真源（**目录型**如 `components/`、**无 `updated` 字段**的注册表）还有个坑：
    "改真源"和"重生成派生页"通常是**同一笔提交**，而生成器在提交前跑 —— 算出来的是上一笔
    提交的日期；一提交，真源的最后提交日就变成今天，`--check` 立刻报漂移，**永远差一天**。
    这类真源要配 `carry_day()` 用（正文没变就沿用已落盘那份的日期），见其 docstring。
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


_FM_RE = re.compile(r'^---\r?\n(.*?)\r?\n---\r?\n', re.S)


def split_fm(text):
    """把 `---` front-matter 与正文分开。没有 front-matter 则返回 `('', 全文)`。"""
    t = (text or '').lstrip('\ufeff')
    m = _FM_RE.match(t)
    if not m:
        return '', t
    return m.group(1), t[m.end():]


def carry_day(cur, want, key='verified_at'):
    """正文没变、只有日期在飘 → 沿用已落盘那份的 `key`。

    为什么：`verified_day()` 落到 git 提交日时，"改真源"与"重生成派生页"往往是同一笔提交，
    生成器跑在提交之前 —— 日期永远落后一笔（见 `verified_day()` 的说明）。口径改成：
      · 正文**有**真变化 → 用本次算出的日期（门禁照旧会报红，真漂移不会被放过）；
      · 正文一致     → 日期原样沿用，跨天 / 跨机器 / 新克隆都稳定。
    调用位置：生成器 `main()` 里 `build()` 之后、比对之前，`want = carry_day(cur, want)`。
    """
    if not cur:
        return want
    cur_fm, cur_body = split_fm(cur)
    want_fm, want_body = split_fm(want)
    if not want_fm or normalize(cur_body) != normalize(want_body):
        return want
    day = None
    for ln in cur_fm.splitlines():
        if ln.strip().startswith(key + ':'):
            day = ln.split(':', 1)[1].strip()
            break
    if not day:
        return want
    out = []
    for ln in want_fm.splitlines():
        out.append('%s: %s' % (key, day) if ln.strip().startswith(key + ':') else ln)
    return '---\n' + '\n'.join(out) + '\n---\n' + want_body


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
