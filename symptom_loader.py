# -*- coding: utf-8 -*-
"""现场症状注册表（`symptom_spec.json`）的**单一 loader** —— 域⑭。

为什么单立一个域（2026-10-04，需求方口径「上面很多口语是踩坑后的记录，能不能从设计端解决」）：

  用户描述现场问题时用的是**症状语言**（"切一下才显示""拖不动""界面文件打开是乱码"），
  而文档用的是**机制语言**（"window 切换走重绘""触摸只发给 touchable 控件"）。
  两者天然错位 → 检索要么查不到，要么把 AI 引到沾边的页。

  过去（以及 2026-10-04 上半场）的补救是**把口语撒进各篇正文**——那是"记录踩坑"，
  违反 `DESIGN_SPEC.md` §1（只留规范、不累积故事），而且散在多处必然漂移。

  设计端的解法：把"症状 → 机制 → 规范 → 权威文档 → 复验方法"收成**一个注册表**，
  与人侧的 `error_codes.json` 同构；派生出一页可检索的症状索引（`gen_symptom_doc.py`）。
  口语只进本表，正文文档保持机制语言。

约定（与其它域一致）：
  - 唯一真源 = `symptom_spec.json`；本模块是唯一读取入口，缺失/不合规**抛错不静默**
  - 派生页 `knowledge/devflow/symptom-index.md`（`--check` 进闸门）
  - `validate()` 的每条报错都要能指出是哪个 id 的哪个字段
"""
import io
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(BASE, 'symptom_spec.json')
DOC_REL = 'knowledge/devflow/symptom-index.md'


def doc_path():
    return DOC_REL


def load():
    """读注册表（不存在 = 抛错，不静默兜底）。"""
    if not os.path.isfile(SPEC):
        raise RuntimeError('症状注册表缺失：%s' % SPEC)
    with io.open(SPEC, encoding='utf-8') as f:
        d = json.load(f)
    if 'entries' not in d:
        raise RuntimeError('症状注册表缺少 entries 字段')
    return d


def validate(include_doc=True):
    """自检；返回错误列表（空 = 合规）。"""
    errs = []
    try:
        d = load()
    except Exception as e:
        return ['注册表不可读：%s' % e]
    seen = set()
    for i, e in enumerate(d['entries']):
        tag = e.get('id') or '#%d' % i
        if not e.get('id'):
            errs.append('#%d 缺 id' % i)
        elif e['id'] in seen:
            errs.append('%s: id 重复' % tag)
        seen.add(e.get('id'))
        if len(e.get('symptom') or []) < 2:
            errs.append('%s: symptom 至少 2 条用户原话（1 条说明还没提炼出共性）' % tag)
        for k in ('mechanism', 'rule', 'doc', 'verify'):
            if not (e.get(k) or '').strip():
                errs.append('%s: 缺 %s' % (tag, k))
        if e.get('doc') and not os.path.isfile(os.path.join(BASE, e['doc'])):
            errs.append('%s: doc 不存在（%s）' % (tag, e['doc']))
        if e.get('doc', '').endswith('symptom-index.md'):
            errs.append('%s: doc 不许指向派生页自己（要指向权威文档）' % tag)
    return errs


def render_doc():
    """渲染派生页（含 front-matter；症状原话**逐字进页**——那正是检索的锚点）。"""
    d = load()
    ents = d['entries']
    # ⚠️ 知识库门禁：tags 只允许**检索词**、且 ≤16 个（禁 markdown 碎片）——
    # 优先用注册表里显式维护的 tags，没有才从症状原话里取前 16 条。
    tags = list(d.get('tags') or [])
    for e in ents:
        for s in e['symptom']:
            if len(tags) >= 16:
                break
            if s not in tags:
                tags.append(s)
    tags = tags[:16]
    lines = [
        '---',
        'id: devflow-symptom-index',
        'title: 现场症状索引（用户原话 → 机制/规范 → 权威文档，由 symptom_spec.json 派生）',
        'category: devflow',
        'status: review',
        'confidence: manual',
        'verified_at: %s' % d.get('updated', ''),
        'stale_days: 180',
        'origin: derived',
        'source: 由 symptom_spec.json 派生（scripts/gen_symptom_doc.py）',
        'needs_evidence: false',
        'platforms: []',
        'tags: [%s]' % ', '.join(tags),
        'evidence:',
        '  - cmd: python scripts/gen_symptom_doc.py --check',
        '    expect: rc=0（本页与 symptom_spec.json 一致）',
        '---',
        '# 现场症状索引（用户原话 → 机制 → 规范 → 权威文档）',
        '',
        '> ⚠️ **本页是派生物，不要手改**（由 `symptom_spec.json` 派生，`--check` 进闸门）。',
        '> 新增症状请改注册表：`symptom_spec.json`。',
        '> ',
        '> 用法：用户描述的是**症状**，本页把症状落到**机制与规范**，并给权威文档。',
        '> 先按「能不能从设计端消灭」判断：能在判据/工具/模板层消灭的坑，不该只留记录。',
        '',
    ]
    for e in ents:
        lines.append('## %s' % ' / '.join(e['symptom']))
        lines.append('')
        lines.append('- **机制**：%s' % e['mechanism'])
        lines.append('- **规范**：%s' % e['rule'])
        lines.append('- **权威文档**：`%s`' % e['doc'])
        lines.append('- **怎么复验**：%s' % e['verify'])
        if e.get('platforms'):
            lines.append('- **平台**：%s' % ' / '.join(e['platforms']))
        lines.append('')
    return '\n'.join(lines) + '\n'
