# -*- coding: utf-8 -*-
"""从平台能力注册表生成可检索知识页 knowledge/devflow/platform-capability-matrix.md。

为什么需要它（2026-10-02 实测发现）：RAG 索引只覆盖 `knowledge/`（102 篇），而「某组件在某平台
能不能用」这份知识原本只存在于 `components/*/platforms.md`（15 篇 / 1779 行）——**不在检索范围内**，
对 AI 是知识黑洞：问「Z20 上能跑什么组件」时 knowledge_search 找不到任何东西。
本脚本把注册表派生进 knowledge/，让这份知识重新可检索；同时 docstring/工具面**不用新增 op**。

派生关系：platform_capabilities.json（真源） → 本页（派生产物）。
改能力 = 改注册表 + 重跑本脚本；**不要手改本页**（--check 会红）。

用法：
    python scripts/gen_platform_cap_doc.py            # 写回知识页
    python scripts/gen_platform_cap_doc.py --check    # 只比对漂移（门禁用）
"""
import argparse
import io
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import platform_cap_loader as pc                   # noqa: E402
import derived_md                                   # noqa: E402

DOC = os.path.join(BASE, 'knowledge', 'devflow', 'platform-capability-matrix.md')

PLATFORM_ORDER = ['Z20', 'Z21', 'F133', 'F135', 'T113', 'V85X', 'Z235X', 'ALL']

FM = """---
id: devflow-platform-capability-matrix
title: 平台能力矩阵（组件 × 平台 可用性，唯一真源派生）
category: devflow
status: review
confidence: manual
verified_at: {today}
stale_days: 180
origin: derived
source: 由 platform_capabilities.json 派生（scripts/gen_platform_cap_doc.py）；表格内容与注册表逐字节一致
needs_evidence: false
platforms: [{platforms}]
tags: [平台支持, 组件可用性, 能不能用, 选型, Z20, Z21, F133, F135, T113, V85X, Z235X, 跨平台移植,
       蓝牙 BLE 平台, 图标库平台, 双缓冲 blend2d, 视频层, 组件矩阵, capability matrix]
evidence:
  - cmd: python scripts/gen_platform_cap_doc.py --check
    expect: rc=0（本页与 platform_capabilities.json 一致）
---

# 平台能力矩阵（组件 × 平台 可用性）

> 检索导引：问「这组件在 Z20 / F133 / V85X / T113 上能不能用」「某设备上能跑哪些组件」
> 「跨平台移植前要查什么」→ 本文。
> 检索词：平台支持 / 组件可用性 / 能不能用 / 选型 / Z20 / Z21 / F133 / F135 / T113 / V85X / Z235X /
> 跨平台 / 能力矩阵 / capability matrix。
>
> ⚠️ **本页是派生产物**：唯一真源 = `platform_capabilities.json`，由 `scripts/gen_platform_cap_doc.py`
> 生成，`--check` 进发布闸门。改能力请改注册表；各组件 `components/*/platforms.md` 那张矩阵表同样是
> 派生的（`scripts/gen_component_platforms.py`），它们保留的是原理、坑与验收方法。
> 平台**身份**（arch / 模板 / 包键）以 `platforms.py` 为准；平台别名（F136→F135、T113EMMC→T113）
> 同样只在 `platforms.py` 登记，查询时自动折算。
"""


def platform_components_table():
    lines = ['## 1. 平台 → 可用组件（答「这台设备上能跑什么」）', '',
             '| 平台 | 组件数 | 组件 |', '|---|---|---|']
    for p in PLATFORM_ORDER:
        comps = pc.components_for_platform(p)
        if not comps:
            continue
        lines.append('| **%s** | %d | %s |' % (p, len(comps), ' / '.join(comps)))
    note = pc.load().get('note')
    if note:
        lines += ['', '> %s' % note]
    lines += ['', '> `ALL` = 该组件声明「全平台通用」（如图标库）。别名查询等价：查 `F136` = 查 `F135`。']
    return lines


def component_index_table():
    lines = ['## 2. 组件 → 覆盖平台（答「这组件能上哪些平台」）', '',
             '| 组件 | 覆盖平台 |', '|---|---|']
    for comp in pc.components():
        lines.append('| `%s` | %s |' % (comp, ' / '.join(pc.platforms_of(comp))))
    return lines


def component_details():
    lines = ['## 3. 逐组件能力矩阵（原样引用注册表，各组件 `platforms.md` 同源）', '']
    for comp in pc.components():
        c = pc.spec(comp)
        lines += ['### %s' % comp, '',
                  '> 文件：`%s`' % c['file']]
        if c.get('note'):
            lines += ['> 口径：%s' % c['note']]
        lines += ['']
        lines += pc.render_table(comp)
        lines += ['']
    return lines


def howto():
    return [
        '## 4. 怎么用 / 怎么改', '',
        '**查**：',
        '```python',
        'import platform_cap_loader as pc',
        "pc.components_for_platform('Z20')      # Z20 上声明支持的组件",
        "pc.cell('ble', 'Z20', '可用性')         # ble 在 Z20 的可用性原话",
        "pc.platforms_of('ble')                 # ble 覆盖哪些平台",
        '```', '',
        '**改**：① 改 `platform_capabilities.json` 对应组件的行 ② 跑 '
        '`python scripts/gen_platform_cap_doc.py` 与本页同步 ③ 跑 '
        '`python scripts/gen_component_platforms.py` 与各组件 `platforms.md` 同步。',
        '',
        '**判定口径**：状态词沿用各组件原话（可用 / 支持 / 未验证 / 不可用），本页**不改写**结论；'
        '「未验证」就是没实测，选型前必须按该组件的 `platforms.md` §验收 真机跑一遍。',
        '',
        '> 本页只覆盖「能力矩阵」这一层。各平台的前置条件、已知限制、真机验收命令在'
        '各组件的 `components/*/platforms.md` 正文里。',
    ]


def build():
    import datetime
    platforms = sorted({p for comp in pc.components() for p in pc.platforms_of(comp)} - {'ALL'})
    parts = [FM.format(today=datetime.date.today().isoformat(),
                       platforms=', '.join(platforms))]
    parts.append('\n'.join(platform_components_table()))
    parts.append('\n'.join(component_index_table()))
    parts.append('\n'.join(component_details()))
    parts.append('\n'.join(howto()))
    return '\n\n'.join(p.rstrip('\n') for p in parts) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    errs = pc.validate()
    if errs:
        print('[FAIL] platform_capabilities.json 自检不通过：')
        for e in errs:
            print('  - %s' % e)
        return 1
    want = build()
    cur = io.open(DOC, encoding='utf-8').read() if os.path.isfile(DOC) else ''
    # 比较口径：抹掉纯格式差异（人用编辑器/格式化器重排过不算漂移），语义漂移照旧算红
    if a.check:
        if not derived_md.same(cur, want):
            print('[FAIL] %s 与注册表漂移（跑 scripts/gen_platform_cap_doc.py 重生成）'
                  % os.path.relpath(DOC, BASE))
            return 1
        print('[PASS] 平台能力知识页与注册表一致（%d 组件 / %d 行）'
              % (len(pc.components()), sum(len(pc.rows(c)) for c in pc.components())))
        return 0
    if derived_md.same(cur, want):
        print('[PASS] 已一致，无需更新')
        return 0
    io.open(DOC, 'w', encoding='utf-8', newline='\n').write(want)
    print('updated: %s' % os.path.relpath(DOC, BASE))
    return 0


if __name__ == '__main__':
    sys.exit(main())
