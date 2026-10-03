# -*- coding: utf-8 -*-
"""从内置包注册表（package_catalog.json）生成可检索知识页 knowledge/devflow/builtin-packages.md。

为什么需要它：系统内置了一整套依赖包（16 个包键 / 182 个唯一包名），MCP 有收录并提供了
`flythings_list_packages` / `flythings_query_package` / `flythings_get_package_api` 等 op——
但**"有哪些内置包、大概什么版本"这份知识只在 json 里，AI 检索不到**，选型时不知道能直接用现成包。
本页把生态摊开成可检索的一张图：先看有什么 → 再用 op 查精确版本与 API。

派生关系：package_catalog.json（真源） → 本页（派生产物）。改包 = 改注册表 + 重跑本脚本。
包键**口径**（含别名）不在这里重定义，以 `platforms.py` 的 PACKAGE_KEYS / PACKAGE_KEY_ALIASES 为准。

用法：
    python scripts/gen_package_catalog_doc.py            # 写回知识页
    python scripts/gen_package_catalog_doc.py --check    # 只比对漂移（门禁用）
"""
import argparse
import collections
import datetime
import io
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import derived_md                                  # noqa: E402

CATALOG = os.path.join(BASE, 'package_catalog.json')
DOC = os.path.join(BASE, 'knowledge', 'devflow', 'builtin-packages.md')
SRC = os.path.join(BASE, 'package_catalog.json')


# 分层阈值：跨多少个包键算「通用 / 常见 / 个别」
TIER_COMMON = 8
TIER_FREQ = 3

FM = """---
id: devflow-builtin-packages
title: 内置依赖包总览（包键 / 通用包 / 包名索引）
category: devflow
status: review
confidence: manual
verified_at: {today}
stale_days: 180
origin: derived
source: 由 package_catalog.json 派生（scripts/gen_package_catalog_doc.py）；包名与版本逐字取自注册表
needs_evidence: false
platforms: [{platforms}]
tags: [内置包, 依赖包, 有哪些包, 包清单, package 包, 版本, 加包, 依赖, MQTT 包, openssl 版本,
       curl, zlib, poco, easyui 版本, 包键, PACKAGE_KEYS, 选型 现成包]
evidence:
  - cmd: python scripts/gen_package_catalog_doc.py --check
    expect: rc=0（本页与 package_catalog.json 一致）
---

# 内置依赖包总览

> 检索导引：问「有没有现成的 XXX 包 / 内置了哪些包 / openssl·curl·zlib·MQTT 是什么版本 /
> 这平台上能用哪些包 / 怎么加包」→ 本文（生态总览）；
> 精确查询走 op：`flythings_list_packages`（列包）/ `flythings_query_package`（查单包版本）
> / `flythings_get_package_api`（看包内 API）/ `flythings_add_package`（加进工程 Manifest）。
> 用法与解析顺序（本地 registry → 离线 catalog → 在线 semver）见
> `knowledge/devflow/dependency-package-docs.md`。
>
> ⚠️ **本页是派生物，不要手改**（由 `package_catalog.json` 派生，`--check` 进闸门）。
> 包键含平台变体与别名（`f136`→F135、`v85xemmc`→V85X），查询时自动折算，不用自己换算。
"""


def load_catalog():
    with io.open(CATALOG, encoding='utf-8') as f:
        return json.load(f)


def aggregate(cat):
    """包名 → {包键: 版本}；包名 → 说明集合。"""
    ver = collections.defaultdict(dict)
    desc = collections.defaultdict(set)
    for key, ent in cat.items():
        for p in ent.get('packages') or []:
            ver[p['name']][key] = p.get('version') or ''
            d = (p.get('description') or '').strip()
            if d:
                desc[p['name']].add(d)
    return ver, desc


def keys_table(cat):
    """包键 → 芯片 / 包数（含规范化平台）。"""
    import platforms as pl
    lines = ['## 1. 包键 → 芯片 / 包数', '',
             '| 包键 | 芯片 | 平台（规范化） | 包数 |', '|---|---|---|---|']
    for key in sorted(cat):
        ent = cat[key]
        chips = ent.get('chips')
        chips_s = ' / '.join(chips) if chips else '—'
        try:
            plat = pl.resolve(key).get('canonical') or '—'
        except Exception:
            plat = '—'
        lines.append('| `%s` | %s | %s | %d |'
                     % (key, chips_s, plat, ent.get('packageCount') or len(ent.get('packages') or [])))
    lines += ['', '> 包键按 SoC 变体分（`v85x` vs `v85xemmc`、`f133` vs `f133emmc`…），'
                  '**与平台规范名不是简单大小写关系**；别名折算见 `platforms.py`。']
    return lines


def common_table(cat, ver, desc):
    lines = ['## 2. 通用包（跨 ≥%d 个包键，选型优先看这批）' % TIER_COMMON, '',
             '| 包 | 说明 | 版本 | 覆盖 |', '|---|---|---|---|']
    rows = sorted(((n, k) for n, k in ver.items() if len(k) >= TIER_COMMON),
                  key=lambda t: (-len(t[1]), t[0]))
    for name, keys in rows:
        vers = sorted(set(keys.values()) - {''})
        if len(vers) == 1:
            v = vers[0]
        elif not vers:
            v = '—'
        else:
            v = '%s（各键不同：%s）' % (vers[-1], '、'.join(
                '%s %s' % (k, keys[k]) for k in sorted(keys)[:3]))
        d = sorted(desc[name])[0] if desc[name] else '—'
        lines.append('| `%s` | %s | %s | %d 键 |' % (name, d, v, len(keys)))
    lines += ['', '> 版本逐字取自注册表；同一包在不同包键上版本可能不同（上表差异只列前 3 个键），'
                  '**要精确版本请用 `flythings_query_package`**。']
    return lines


def index_section(cat, ver, desc):
    """包名索引：按覆盖度分层列全（保证任何一个内置包都能被"发现"）。"""
    common = sorted(n for n, k in ver.items() if len(k) >= TIER_COMMON)
    freq = sorted(n for n, k in ver.items() if TIER_FREQ <= len(k) < TIER_COMMON)
    rare = sorted(n for n, k in ver.items() if len(k) < TIER_FREQ)
    lines = ['## 3. 包名索引（全 %d 个，按覆盖度分层）' % len(ver), '',
             '**通用（≥%d 键，%d 个）**：%s' % (TIER_COMMON, len(common), '、'.join('`%s`' % x for x in common)),
             '',
             '**常见（%d~%d 键，%d 个）**：%s'
             % (TIER_FREQ, TIER_COMMON - 1, len(freq), '、'.join('`%s`' % x for x in freq)),
             '',
             '**个别包键独有（<%d 键，%d 个）**：%s'
             % (TIER_FREQ, len(rare), '、'.join('`%s`' % x for x in rare)),
             '',
             '> 这批里 %d 个包在注册表里**没有一句话说明**（多为示例工程/内部件）。'
             '要确认某个包能干什么，用 `flythings_get_package_api` 看它导出的 API。'
             % sum(1 for n in ver if not desc[n])]
    return lines


def howto():
    return [
        '## 4. 怎么用（选型 → 加包 → 看 API）', '',
        '1. **先看有没有**：本页 §2/§3，或 `flythings_list_packages(platform=...)`（列该平台全部包）。',
        '2. **确认版本与依赖**：`flythings_query_package(name, platform)`；版本解析顺序 = '
        '本地 registry → 离线 catalog → 在线 semver。',
        '3. **看包内 API**：`flythings_get_package_api(name)`——**不要凭记忆写包内 API**。',
        '4. **加进工程**：`flythings_add_package(project_root, id, version)`（自动改 Manifest + `fun install`）；'
        '只想要推荐清单不动盘就用 `flythings_manifest(features=...)`。',
        '',
        '> ⚠️ 常见坑：Manifest 里漏声明传递依赖（例：用 `mqtt-cxx` 要连 `paho-mqtt3as` + `openssl` 一起声明，'
        '否则链接报 `BIO_read / RAND_bytes / SHA1_*` undefined）。踩坑口径见 '
        '`knowledge/devflow/dependency-package-docs.md`。',
    ]


def build():
    cat = load_catalog()
    ver, desc = aggregate(cat)
    import platforms as pl
    plats = sorted({pl.resolve(k).get('canonical') or k for k in cat if _resolvable(pl, k)})
    parts = [FM.format(today=derived_md.verified_day(SRC), platforms=', '.join(plats)),
             '\n'.join(keys_table(cat)),
             '\n'.join(common_table(cat, ver, desc)),
             '\n'.join(index_section(cat, ver, desc)),
             '\n'.join(howto())]
    return '\n\n'.join(p.rstrip('\n') for p in parts) + '\n'


def _resolvable(pl, key):
    try:
        return bool(pl.resolve(key).get('canonical'))
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    if not os.path.isfile(CATALOG):
        print('[FAIL] 找不到内置包注册表：%s' % CATALOG)
        return 1
    want = build()
    cur = io.open(DOC, encoding='utf-8').read() if os.path.isfile(DOC) else ''
    want = derived_md.carry_day(cur, want)      # 注册表无 updated 字段 → 日期只能退到 git，靠这个免掉"差一天"
    if a.check:
        if not derived_md.same(cur, want):
            print('[FAIL] builtin-packages.md 与 package_catalog.json 漂移'
                  '（跑 scripts/gen_package_catalog_doc.py 重生成）')
            return 1
        cat = load_catalog()
        ver, _d = aggregate(cat)
        print('[PASS] 内置包知识页与注册表一致（%d 包键 / %d 唯一包名）' % (len(cat), len(ver)))
        return 0
    if derived_md.same(cur, want):
        print('[PASS] 已一致，无需更新')
        return 0
    io.open(DOC, 'w', encoding='utf-8', newline='\n').write(want)
    print('updated: %s' % os.path.relpath(DOC, BASE))
    return 0


if __name__ == '__main__':
    sys.exit(main())
