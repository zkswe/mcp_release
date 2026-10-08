# -*- coding: utf-8 -*-
"""由 components/ 树 + 已有注册表生成知识页 knowledge/components/components-catalog.md。

用法：
    python scripts/gen_components_catalog.py            # 生成/更新
    python scripts/gen_components_catalog.py --check    # 只比对（门禁口径；漂移退出码 1）

为什么是"生成"而不是"另写一份清单"：组件信息本来就在树里（形状/依赖/示例）+ 已有注册表
（平台可用性在 platform_capabilities.json；文档在各自 README.md）。本页只是把它们摊成
AI 可检索的一页，顺手把 `components/README.md` 那条「**四件套缺一不收**」跑成可执行校验。
"""
import io
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import components_catalog as cc                    # noqa: E402
import derived_md                                  # noqa: E402

DOC = os.path.join(BASE, cc.DOC_PATH)
SRC = os.path.join(BASE, 'components')             # 真源是这棵树（取它的最后提交日做 verified_at）

# 16 个上限（kb_local.MAX_TAGS）：留通用词 + 中文别名，组件名靠正文命中
TAGS = ['可复用组件', '组件目录', '有没有现成的', '复用库', '字体', '图标', '图表', '日历',
        '蓝牙', '传图', '高斯模糊', '缓存', '多屏同步', 'ui_v1', 'ble', 'fonts']


def _fm():
    return [
        '---',
        'id: components-components-catalog',
        'title: 可复用组件目录（components/ 树派生：形态 / 四件套 / 平台 / 依赖 / 示例）',
        'category: components',
        'status: review',
        'confidence: manual',
        'verified_at: %s' % derived_md.verified_day(SRC),
        'stale_days: 180',
        'origin: derived',
        'source: 由 components/ 树扫描派生（scripts/gen_components_catalog.py）；'
        '平台可用性取自 platform_capabilities.json，依赖取自各组件 Manifest.xml',
        'needs_evidence: false',
        'platforms: []',
        'tags: [%s]' % ', '.join(TAGS),
        'evidence:',
        '  - cmd: python scripts/gen_components_catalog.py --check',
        '    expect: rc=0（本页与 components/ 树及各注册表一致）',
        '---',
        '',
    ]


def build():
    L = _fm()
    ms = cc.modules()
    L.append('# 可复用组件目录')
    L.append('')
    L.append('> 口语问法直达：有没有现成的组件 / 组件目录 / 「%s」这些有吗 /'
             '这块平台能用哪些组件 / 怎么把组件接进工程。'
             % '、'.join([t for t in TAGS if not t.isascii()][:8]))
    L.append('>')
    L.append('> ⚠️ **本页是派生物，不要手改**（由 `components/` 这棵树扫描派生，`--check` 进闸门）。'
             '落地规范（四件套、模块形态、代码规范、新增模块 checklist）见 `components/README.md` 的 §7。')
    L.append('> 依赖读各组件 `Manifest.xml`，平台可用性读 `platform_capabilities.json` —— '
             '两处都不会在本页编一份。')
    L.append('')

    # 1. 总表
    L.append('## 1. 组件总表')
    L.append('')
    L.append('| 组件 | 形态 | 一句话 | 平台 | 依赖包 | 示例 |')
    L.append('|---|---|---|---|---|---|')
    for m in ms:
        L.append('| **%s** | %s | %s | %s | %s | %s |' % (
            m['id'], m['formName'], m['summary'] or '—',
            '、'.join(m['platforms']) or '（见 platforms.md）',
            '、'.join('`%s`' % d for d in m['deps']) or '无',
            '`%s`' % m['examples'][0] if m['examples'] else '—'))
    L.append('')

    # 2. 明细
    L.append('## 2. 组件明细（怎么接进工程）')
    L.append('')
    for form, desc in (('source', '源码型 —— 拷 `include/` + `src/` 进工程（推荐起步）'),
                       ('binary', '二进制型 —— 按目标平台取 `lib/<平台>/`，别拿别平台的头凑'),
                       ('asset', '资产/工具型 —— 不写代码，按 README 一条命令用')):
        group = cc.modules(form)
        if not group:
            continue
        L.append('### 2.%d %s' % (('source', 'binary', 'asset').index(form) + 1, desc))
        L.append('')
        for m in group:
            L.append('#### %s' % m['id'])
            L.append('')
            L.append('- **用途**：%s' % (m['summary'] or '—'))
            L.append('- **平台**：%s' % ('、'.join(m['platforms']) or '见 `%s`' % m['platformDoc']))
            L.append('- **依赖包**：%s' % ('、'.join('`%s`' % d for d in m['deps']) or '无'))
            if m['libPlatforms']:
                L.append('- **预编译库平台**：%s' % '、'.join(m['libPlatforms']))
            if m['examples']:
                L.append('- **示例工程**：%s' % '、'.join('`%s`' % e for e in m['examples']))
            if m['verify']:
                L.append('- **机器自检**：`%s`' % '`、`'.join(m['verify']))
            L.append('- **文档**：`%s`' % m['docRef'])
            L.append('')

    # 3. 分组与索引页
    gs = cc.groups()
    if gs:
        L.append('## 3. 分组与索引页')
        L.append('')
        L.append('| 目录 | 性质 | 成员 |')
        L.append('|---|---|---|')
        for g in gs:
            L.append('| `%s` | %s | %s |' % (
                g['dir'], '分组' if g['children'] else '索引页',
                '、'.join('`%s`' % c for c in g['children']) or '—'))
        L.append('')

    # 4. 已登记缺口
    L.append('## 4. 已登记的缺口（不是漏件，是登记在案的形态变体）')
    L.append('')
    gaps = cc.declared_gaps()
    if not gaps:
        L.append('无 —— 全部组件按形态满足四件套。')
    else:
        for g in gaps:
            what = ('缺 %s' % '、'.join(g['missing'])) if g.get('missing') else \
                   ('不进 platform_capabilities（无平台矩阵表）' if g.get('noPlatformRow') else '')
            L.append('- **`%s`**（%s，登记于 %s）：%s' % (g['id'], what, g.get('date'), g.get('why')))
        L.append('')
        L.append('> 口径：新增缺口**不会**被自动放行 —— `components_catalog.validate()` 只认'
                 '登记过的（`DECLARED_GAPS`，每条要写原因与日期），其余一律判失败。'
                 '所以这份缺口清单是有账可查的，不是「坏了也不报」。')
    L.append('')

    # 5. 接进工程的两条路
    L.append('## 5. 把一个组件接进工程')
    L.append('')
    L.append('1. **先查**：本页 §1/§2（有没有现成的、形态、平台、依赖、示例在哪）；')
    L.append('   要精确问「某平台能用哪些组件」用 `flythings_knowledge_search`，或直接看 '
             '`platform_capabilities.json` 派生的平台能力矩阵页。')
    L.append('2. **再看示例**：每个组件都有 `example/`（能拷进工程就跑）——先照示例跑通，再改。')
    L.append('3. **源码引入**：拷 `include/` + `src/` 进工程；**依赖包引用**（组件已注册进包仓库时）：'
             '一行 `<package id="<组件>" version="x.y.z"/>`。')
    L.append('4. **声明依赖**：把本页「依赖包」那列写进工程 `Manifest.xml`（或 `fsc.json`，其优先级更高），'
             '**改完必须重跑 `fsc install`**（否则新包的 include 路径进不了 CMake）。')
    L.append('5. **换平台先查 `platforms.md`**：没实测的写的就是 `未验证`，别当结论用。')
    L.append('')
    return '\n'.join(L)


def main(argv):
    a = set(argv[1:])
    errs = cc.validate()
    if errs:
        print('[FAIL] 四件套核对未过：')
        for e in errs[:8]:
            print('   -', e)
        return 1
    want = build()
    cur = io.open(DOC, encoding='utf-8').read() if os.path.isfile(DOC) else ''
    want = derived_md.carry_day(cur, want)      # 真源是目录 → 日期只能退到 git，靠这个免掉"差一天"
    if derived_md.same(cur, want):
        print('[PASS] 已一致，无需更新')
        return 0
    if '--check' in a:
        print('[FAIL] 组件目录页与 components/ 树不一致（跑 gen_components_catalog.py 重生成）')
        return 1
    os.makedirs(os.path.dirname(DOC), exist_ok=True)
    with io.open(DOC, 'w', encoding='utf-8', newline='') as fh:
        fh.write(want)
    print('已写入 %s（%d 行）' % (cc.DOC_PATH, len(want.splitlines())))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
