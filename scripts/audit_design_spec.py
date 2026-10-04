# -*- coding: utf-8 -*-
"""设计规范全检（派生报告）：见根目录 DESIGN_SPEC.md 第 0–4 条。

三类检查（**提示不判决**，每条都要读上下文再决定）：
  ① 通用内容：疑似"AI 原生能力"（语言/风格/模式/教程）混进了知识页
  ② 踩坑叙述：应归约为规范的"故事"（踩坑/血泪/教训…）
  ③ 可实测却硬编码：分区容量、屏参、字库体积之类的静态数字
  ④ 事故句式：**规范里混进了"当初怎么发现的"**（症状词 × 归因标记 × 日期/版本号）。

扫描范围 = `knowledge/**/*.md` + 注册表/判据 json（`knowledge/authority_map.json`、
`ui_tools/ui_schema.json`、根目录 `*_spec.json`）—— 第 ④ 类恰恰最容易藏在注册表的 note/rule 里，
而那里是**渲染给 AI 的原话**（`knowledge/` 之外）。

用法：
    python scripts/audit_design_spec.py            # 写 knowledge/_reports/design_spec_audit.md
    python scripts/audit_design_spec.py --check    # 只比对（漂移退出码 1），供门禁委派
"""
import argparse
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_MD = os.path.join(BASE, 'knowledge', '_reports', 'design_spec_audit.md')
OUT_JSON = os.path.join(BASE, 'knowledge', '_reports', 'design_spec_audit.json')
SKIP = {'_reports', '_logs', 'inbox', '__pycache__'}

CHECKS = [
    ('① 通用内容（AI 原生能力，不属本仓）',
     # 「缩进」单独出现常是**字符名**（"tab 缩进 + 冒号后无空格" 是格式要求），
     # 只有与规范/风格/约定连用时才是"通用编程规范"（实测该收紧消掉 1 处假阳性）
     re.compile(r'命名规范|代码风格|变量命名|变量名规范|什么是 C\+\+|指针是什么|如何写函数|'
                r'设计模式入门|算法入门|语法教程|从零学|'
                r'缩进\s*(规范|风格|规则|约定|要求)')),
    ('② 踩坑叙述（应归约为规范条目）',
     re.compile(r'踩坑|坑位|血泪|教训|踩过|踩了|亲测踩')),
    ('③ 可实测却硬编码的静态值',
     re.compile(r'(分区|MISC|boot_logo|res)\D{0,24}(\d[\d,]{3,}\s*B|0x[0-9A-Fa-f]{4,})|'
                r'\d{3,4}\s*[x×]\s*\d{3,4}\s*(屏|面板|分辨率)')),
]
# ④ 是**子串三连**判定（症状 × 归因 × 日期/版本），不放这里：不适用正则（见下）
KIND4 = '④ 事故句式（规范里混进了"当初怎么发现的"）'
# ⑤⑥ 两条**结构性**判据（2026-10-05 新增，见 scan() 里的口径说明）：真实残留是"句子级沉积"，
# 住在标题行与括号尾注里 —— 比扩词表有效得多，且不会误伤"只写症状 = 规范"的正文。
KIND5 = '⑤ 标题后缀叙事（"（踩过）/（实测教训）/（返工反推）"这类后缀）'
KIND6 = '⑥ 括号尾注来路（"（2026-xx-xx 更正/修正/推翻）"这类括号）'
ID_SUFFIX = re.compile(r'^#{1,6}\s+.*[（(][^）)]*(踩过|踩坑|教训|复盘|返工|事故|血泪)[^）)]*[）)]\s*$')
# ⚠️ 只认**修订动词**（更正/修正/勘正/订正/改判/复核/推翻/补录/收拢/移除/误写/失效），
# **不认** `确认 / 实测 / 口径 / 拍板` —— 那三类是**正当的出处标注**（"2026-09-17 真机复核"
# 是证据链，"2026-09-21 口径"是生效范围），第一版把它们也算上，48 处里大半是假阳性。
ID_TAIL = re.compile(
    r'[（(]\s*(?:19|20)\d\d[-/年.]\d{1,2}(?:[-/.]\d{1,2})?\s*[^）)]*'
    r'(更正|修正|勘正|订正|改判|复核|推翻|补录|收拢|移除|误写|失效|误标)')
CHECKS_ALL = CHECKS + [(KIND4, None), (KIND5, None), (KIND6, None)]

# ④ 用子串而不是大正则：长行（rag_index 的 base64 blob）上正则回溯会炸（实测卡死）。
# 判据 = 同时出现「症状词 + 归因标记 + 日期/版本号」。三者齐备才算"事故叙述"：
#   · 只写症状（"写成字符串 = 挂死"）= 规范，**要留**；
#   · 只写日期（"2026-09-07 学习"）= 出处声明，**要留**；
#   · 三者齐备 = "某年某月某次 A/B 实测发现…" → 应归约为规范条目。
INCIDENT_SYM = ('挂死', '黑屏', '无声', '空转', '真凶', '错归因', '错误归因', '根因',
                '曾把', '曾经', '历史上', '旧式', '终裁', '坑位', '误声明')
INCIDENT_ATTR = ('A/B', 'abtest', 'bisect', '二分', '实测', '对照', '定位', '沉淀', '终裁',
                 '真凶', '错归因')
INCIDENT_DATE = ('2024-', '2025-', '2026-', '2024年', '2025年', '2026年', '09-', '10-0',
                 'v0.27', 'v0.3.')
# 注册表/判据 json 里的 note/rule 是**渲染给 AI 的原话**，第 ④ 类的重灾区（`knowledge/` 之外）
EXTRA_FILES = ('ui_tools/ui_schema.json', 'knowledge/authority_map.json')
EXTRA_GLOB = ('_spec.json', 'capabilities.json', 'catalog.json')



def _targets():
    """扫描目标：knowledge 下 .md + 注册表/判据 json（第 ④ 类最容易藏在后者的 note/rule 里）。"""
    seen, files = set(), []
    for root, dirs, fs in os.walk(os.path.join(BASE, 'knowledge')):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in sorted(fs):
            if f.endswith('.md'):
                p = os.path.join(root, f)
                rel = os.path.relpath(p, BASE).replace(os.sep, '/')
                if rel not in seen:                 # 派生页整体跳过（内容由注册表生成）
                    seen.add(rel)
                    files.append(rel)
    for rel in EXTRA_FILES:
        if rel not in seen and os.path.isfile(os.path.join(BASE, rel.replace('/', os.sep))):
            seen.add(rel)
            files.append(rel)
    for f in sorted(os.listdir(BASE)):              # 根目录注册表（op_spec / preflight_spec / …）
        if f.endswith('.json') and any(f.endswith(g) for g in EXTRA_GLOB):
            if f not in seen:
                seen.add(f)
                files.append(f)
    return files


def scan():
    out = []
    for rel in _targets():
        p = os.path.join(BASE, rel.replace('/', os.sep))
        # 注册表 json（非 .md）不计代码围栏：它们的 note/rule 是**渲染给 AI 的原话**
        fenced, is_json = False, not rel.endswith('.md')
        try:
            lines = io.open(p, encoding='utf-8', errors='replace').read().splitlines()
        except OSError as e:
            # 不静默（DESIGN_SPEC 第 3 条 / scripts/lint_silent_except.py）：读不了就报出来，
            # 让人知道这一轮少扫了哪个文件，而不是当作它不存在。
            print('  [NOTE] 读不了，已跳过: %s（%s）' % (rel, e.strerror or type(e).__name__))
            continue
        for i, ln in enumerate(lines, 1):
            s = ln.strip()
            # ⑤⑥ 两条**结构性**判据先跑（2026-10-05 新增）：真实残留住在标题行、表格行、
            # `（2026-xx-xx 更正）` 括号尾注里，而下面的 ①–④ 全都**跳过标题行**、④ 还要求
            # "日期词+症状词+归因词"三连 —— 等于把重灾区整片划出扫描范围（实测：④ 原始命中
            # 只有 2 处，而结构性两类各有十几个）。它测的是"行文风格"，不是"是否含历史"。
            if not s or s.startswith('//') or 'design-spec:evidence' in s:
                continue
            if ID_SUFFIX.search(s):
                out.append({'kind': KIND5, 'doc': rel, 'line': i, 'text': s[:200]})
                continue
            if s.startswith('#'):
                continue              # 标题行：①–④ 不看（⑤ 已单独判过）
            if s.startswith('```'):
                fenced = not fenced
                continue
            if s.startswith('*'):
                continue              # 代码注释：开发者读物，不在"给 AI 的规范"范围
            if fenced and not is_json:
                continue              # .md 的知识页：``` 内是**示例**，不是规范文本
            if len(s) > 400:
                continue              # 派生数据行（base64 blob）不参与
            if ID_TAIL.search(s):
                out.append({'kind': KIND6, 'doc': rel, 'line': i, 'text': s[:200]})
                continue
            # 注册表里描述**字段用途**的元数据（`"rules": "…踩坑要点…"`、`"what": "…踩过什么"`）
            # 是在定义这个域收什么，不是在写事故叙述 —— 实测会造出 3/5 的假阳性，故跳过。
            if re.match(r'^"(rules|what|note|gotchas|fields|renderSpec|renderOrder|tiers|'
                        r'contractOrder|authority|basis|migration|longOps|notesDebt)"\s*:', s):
                continue
            hit = None
            for label, rx in CHECKS:
                if rx.search(s):
                    hit = label
                    break
            if hit is None and (any(k in s for k in INCIDENT_SYM)
                                and any(k in s for k in INCIDENT_ATTR)
                                and any(k in s for k in INCIDENT_DATE)):
                hit = KIND4
            if hit:
                out.append({'kind': hit, 'doc': rel, 'line': i, 'text': s[:200]})
    return out


def render(items):
    by = {}
    for it in items:
        by.setdefault(it['kind'], []).append(it)
    L = ['# 设计规范全检（派生报告 —— 别在这里手改）',
         '',
         '> 依据 `DESIGN_SPEC.md`；由 `scripts/audit_design_spec.py` 扫描派生。',
         '> **提示不判决**：每条都要读上下文后决定「归约为规范 / 删除 / 保留并写明理由」。',
         '',
         '合计 **%d** 处命中。' % len(items), '']
    for label, _rx in CHECKS_ALL:
        rows = by.get(label, [])
        L += ['## %s（%d 处）' % (label, len(rows)), '']
        if not rows:
            L.append('（无）')
        for it in rows[:60]:
            L.append('- `%s:%d` %s' % (it['doc'].replace('knowledge/', ''), it['line'], it['text'][:150]))
        if len(rows) > 60:
            L.append('- …（其余 %d 处见 json）' % (len(rows) - 60))
        L.append('')
    return '\n'.join(L) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    items = scan()
    md = render(items)
    blob = json.dumps({'total': len(items), 'items': items}, ensure_ascii=False, indent=1) + '\n'
    if a.check:
        old_md = io.open(OUT_MD, encoding='utf-8').read() if os.path.isfile(OUT_MD) else ''
        old_js = io.open(OUT_JSON, encoding='utf-8').read() if os.path.isfile(OUT_JSON) else ''
        if old_md != md or old_js != blob:
            print('[FAIL] 设计规范全检报告已滞后（跑 python scripts/audit_design_spec.py 重生成）')
            return 1
        print('[PASS] 全检报告与知识页一致（%d 处命中）' % len(items))
        return 0
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    io.open(OUT_MD, 'w', encoding='utf-8', newline='\n').write(md)
    io.open(OUT_JSON, 'w', encoding='utf-8', newline='\n').write(blob)
    print('报告 -> %s（%d 处命中）' % (os.path.relpath(OUT_MD, BASE), len(items)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
