# -*- coding: utf-8 -*-
"""由 `ui_entrypoints.json`（入口登记唯一真源）派生 `knowledge/devflow/ui-entrypoints.md`。

为什么要有它（2026-10-05，REMEDIATION-UI-PIPELINE §WS-0 / T0.3）：入口清单原本只在对话与
知识页里"说"着，加了入口没人知道、某入口其实没实现也没人拦。现在**真源是一份 JSON**，
人读页由本脚本生成；改真源不重生成 → `--check` 判红（DESIGN_SPEC 第 4 条：只派生不抄）。

写法照 `scripts/gen_gate_catalog.py`：读 JSON → 生成 → 写入 / 比对 → 打印 `[PASS]`/`[FAIL]`，
**不导入重依赖**（stdlib only，不 import kb_tools / mcp / onnx；离线可跑）。

生成物里**不写任何数字以外的当日值**：`verified_at` 取真源的 `updated`（不是 `time.time()`），
所以同一份真源任何时候生成都字节一致（否则 `--check` 会天天红）。

用法（在 MCP 根目录或任意位置）：
    python scripts/gen_entrypoints_doc.py            # 写入 knowledge/devflow/ui-entrypoints.md
    python scripts/gen_entrypoints_doc.py --check    # 只比对，漂移退出码 1（进闸门）
    python scripts/gen_entrypoints_doc.py --out X    # 指定输出路径（自证用）
"""
import argparse
import io
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, 'ui_entrypoints.json')
DEFAULT_OUT = os.path.join(BASE, 'knowledge', 'devflow', 'ui-entrypoints.md')

TIERS = ('default', 'allowed', 'migration')
STATUSES = ('active', 'planned', 'unsupported')

TIER_LABEL = {'default': 'default（缺省）', 'allowed': 'allowed（允许）', 'migration': 'migration（迁移）'}
STATUS_LABEL = {'active': 'active（可用）', 'planned': 'planned（未实现）', 'unsupported': 'unsupported（不支持）'}


def load(path=SRC):
    """读真源；结构不合规直接报错退出（派生物不许在坏真源上生成）。"""
    with io.open(path, encoding='utf-8') as f:
        data = json.load(f)
    problems = []
    if not isinstance(data, dict):
        raise SystemExit('[FAIL] %s 顶层必须是对象' % path)
    for k in ('schema', 'version', 'updated', 'authority', 'tiers', 'entrypoints'):
        if not data.get(k):
            problems.append('缺字段 %s' % k)
    tiers = data.get('tiers') or {}
    for t in TIERS:
        if not str(tiers.get(t) or '').strip():
            problems.append('tiers 缺 %s 的约束说明' % t)
    ids, eps = set(), data.get('entrypoints') or []
    for e in eps:
        eid = str(e.get('id') or '?')
        if not e.get('id'):
            problems.append('有入口缺 id')
        if eid in ids:
            problems.append('入口 id 重复：%s' % eid)
        ids.add(eid)
        if e.get('tier') not in TIERS:
            problems.append('%s 的 tier=%r 不合法' % (eid, e.get('tier')))
        if e.get('status') not in STATUSES:
            problems.append('%s 的 status=%r 不合法' % (eid, e.get('status')))
        if e.get('status') == 'active':
            if not (e.get('validator_chain') or []):
                problems.append('%s 是 active 但没有 validator_chain' % eid)
            ev = e.get('evidence') or {}
            if not any(ev.get(k) for k in ('tests', 'artifacts', 'on_device')):
                problems.append('%s 是 active 但没有 evidence' % eid)
    if problems:
        raise SystemExit('[FAIL] 真源 %s 不合规（%d 项）：\n   ' % (os.path.basename(path), len(problems))
                         + '\n   '.join(problems))
    return data


def _join(items):
    return '、'.join('`%s`' % i for i in items) if items else '—'


def render(data):
    """真源 → Markdown（纯函数：同一份真源产出逐字节一致）。"""
    eps = data['entrypoints']
    order = {t: i for i, t in enumerate(TIERS)}
    rows = sorted(eps, key=lambda e: (order.get(e.get('tier'), 9),
                                      {'active': 0, 'planned': 1, 'unsupported': 2}.get(e.get('status'), 9),
                                      str(e.get('id'))))
    out = []
    out.append('---')
    out.append('id: devflow-ui-entrypoints')
    out.append('title: 界面产物入口登记（有哪些入口 / 各自档位·状态·校验链·证据·已知限制）')
    out.append('category: devflow')
    out.append('status: review')
    out.append('confidence: manual')
    out.append('verified_at: %s' % data['updated'])
    out.append('stale_days: 180')
    out.append('origin: derived')
    out.append('source: 派生自仓库根 ui_entrypoints.json（v%s，updated %s）' % (data['version'], data['updated']))
    out.append('needs_evidence: true')
    out.append('platforms: []')
    out.append('tags: [入口登记, 界面入口, 多个入口怎么选, 手写入口, 迁移入口, 校验链, 入口状态, '
               'html 原型, 块库 spec, 直写 json, 入口限制]')
    out.append('evidence: []')
    out.append('---')
    out.append('')
    out.append('# 界面产物入口登记（有哪些入口 / 各自档位·状态·校验链·证据·已知限制）')
    out.append('')
    out.append('> 本文件是派生：真源 = `ui_entrypoints.json`，不要手改；改真源后重跑生成器即可。')
    out.append('')
    out.append('> 检索导引：问「**HTML 是不是唯一源** / 除了写 HTML 还有哪些入口 / 某个框架（LVGL·Qt·QML·'
               'Android XML·小程序·Vue）能不能迁 / 哪些入口能用、哪些只是计划 / 产物要过哪些校验」→ 本文；'
               '**口径（为什么、怎么判）见 `knowledge/devflow/ui-pipeline-spec.md`**。')
    out.append('')
    out.append('> 权威口径：%s' % data['authority'])
    out.append('')
    out.append('> 状态口径：`active` = %s ｜ `planned` = %s ｜ `unsupported` = %s'
               % (data.get('status_legend', {}).get('active', '可用'),
                  data.get('status_legend', {}).get('planned', '未实现'),
                  data.get('status_legend', {}).get('unsupported', '不支持')))
    out.append('')
    out.append('## 档位（三档，各自约束）')
    out.append('')
    out.append('| 档位 | 约束 |')
    out.append('|---|---|')
    for t in TIERS:
        out.append('| %s | %s |' % (TIER_LABEL[t], data['tiers'][t]))
    out.append('')
    out.append('## 入口清单（%d 个）' % len(eps))
    out.append('')
    out.append('| 入口 | 语言 | 档位 | 状态 | 转换 op | 校验链 | 证据 | 已知限制 |')
    out.append('|---|---|---|---|---|---|---|---|')
    for e in rows:
        ev = e.get('evidence') or {}
        limits = e.get('limits') or []
        ev_parts = []
        if ev.get('tests'):
            ev_parts.append('用例：%s' % _join(ev['tests']))
        if ev.get('artifacts'):
            ev_parts.append('产物：%s' % _join(ev['artifacts']))
        if ev.get('on_device'):
            ev_parts.append('真机：%s' % '、'.join(ev['on_device']))
        out.append('| `%s`（%s） | %s | %s | %s | %s | %s | %s | %s |'
                   % (e['id'], e.get('name', ''), e.get('language', '—'),
                      TIER_LABEL.get(e.get('tier'), e.get('tier', '?')),
                      STATUS_LABEL.get(e.get('status'), e.get('status', '?')),
                      _join(e.get('ops') or []), _join(e.get('validator_chain') or []),
                      '<br>'.join(ev_parts) if ev_parts else '—',
                      '<br>'.join(limits) if limits else '—'))
    out.append('')
    out.append('> 校验链里的 `ui_compile`（编译式验收）**已实现**：`ui_tools/ui_compile.py`'
               '（`python ui_tools/ui_compile.py <工程根>`；op `flythings_validate_project` 的 '
               '`ui_check` 也会跑它）。登记它 = 该入口的产物必须过它 —— **没跑过就不算验收**。')
    out.append('')
    out.append('## 相关')
    out.append('')
    out.append('- 口径唯一出处（三档判据 / 入口分级 / 模块契约 / 差异归因）→ '
               '`knowledge/devflow/ui-pipeline-spec.md`')
    out.append('- 迁移方法论（四阶段 / 降级 D-xx / 双平台）→ `knowledge/devflow/platform-translate.md`')
    out.append('- 控件级对应（带可直接粘的 json 片段）→ op `flythings_map_control`')
    out.append('')
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=SRC)
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--check', action='store_true', help='只比对，不写入（漂移退出码 1）')
    a = ap.parse_args()
    data = load(a.src)
    want = render(data)
    if a.check:
        if not os.path.isfile(a.out):
            print('[FAIL] 缺派生页 %s（生成：python scripts/gen_entrypoints_doc.py）' % a.out)
            return 1
        cur = io.open(a.out, encoding='utf-8').read()
        if cur.replace('\r\n', '\n') != want:
            print('[FAIL] 派生页与真源漂移：%s' % a.out)
            print('   真源：%s' % a.src)
            print('   fix：python scripts/gen_entrypoints_doc.py')
            return 1
        print('[PASS] 入口派生页与真源一致（%d 个入口）' % len(data['entrypoints']))
        return 0
    with io.open(a.out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(want)
    print('entrypoints doc -> %s（%d 个入口）' % (a.out, len(data['entrypoints'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
