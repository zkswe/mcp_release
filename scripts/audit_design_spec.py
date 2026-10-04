# -*- coding: utf-8 -*-
"""设计规范全检（派生报告）：见根目录 DESIGN_SPEC.md 第 0–4 条。

三类检查（**提示不判决**，每条都要读上下文再决定）：
  ① 通用内容：疑似"AI 原生能力"（语言/风格/模式/教程）混进了知识页
  ② 踩坑叙述：应归约为规范的"故事"（踩坑/血泪/教训…）
  ③ 可实测却硬编码：分区容量、屏参、字库体积之类的静态数字

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
     re.compile(r'命名规范|代码风格|缩进|变量命名|什么是 C\+\+|指针是什么|如何写函数|'
                r'设计模式入门|算法入门|语法教程|从零学')),
    ('② 踩坑叙述（应归约为规范条目）',
     re.compile(r'踩坑|坑位|血泪|教训|踩过|踩了|亲测踩')),
    ('③ 可实测却硬编码的静态值',
     re.compile(r'(分区|MISC|boot_logo|res)\D{0,24}(\d[\d,]{3,}\s*B|0x[0-9A-Fa-f]{4,})|'
                r'\d{3,4}\s*[x×]\s*\d{3,4}\s*(屏|面板|分辨率)')),
]


def scan():
    out = []
    for root, dirs, files in os.walk(os.path.join(BASE, 'knowledge')):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in sorted(files):
            if not f.endswith('.md'):
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, BASE).replace(os.sep, '/')
            lines = io.open(p, encoding='utf-8', errors='replace').read().splitlines()
            for i, ln in enumerate(lines, 1):
                if ln.startswith('#') or not ln.strip():
                    continue
                if 'design-spec:evidence' in ln:
                    continue          # 已写明理由的历史实测记录（DESIGN_SPEC.md 第 5 条）
                for label, rx in CHECKS:
                    if rx.search(ln):
                        out.append({'kind': label, 'doc': rel, 'line': i, 'text': ln.strip()[:200]})
                        break
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
    for label, _rx in [(c[0], c[1]) for c in CHECKS]:
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
