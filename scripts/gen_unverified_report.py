# -*- coding: utf-8 -*-
"""派生一份「未核 / 待验证」清单 —— **只读知识页，不新增第二份真源**。

为什么用"派生"而不是"手抄一张登记表"：各页本来就有自己的「待确认/未验证」小节，
再手抄一张集中表 = 同一事实写两遍 → 迟早分叉。

判据（启发式，报告里写明是"提示不是判决"）：
  · 标记词：待确认 / 待验证 / 待真机 / 未核 / 未验证 / 存疑 / 尚未实测 / 不作为结论 / 需真机 …
  · 跳过：front-matter 块、标题行、纯 tag 行
  · 三种去向：
      有方法  —— 行内含命令/实测/复验/自证/按 §/判据/先量/核对 …（**补一句复验方法比补结论有用**）
      无需方法 —— 行内含「无需复验方法：<理由>」（状态标记/口径声明/厂商信息这类非可验项）
      缺方法  —— 其余（本表的行动项）

用法：
    python scripts/gen_unverified_report.py            # 写 knowledge/_reports/unverified.{md,json}
    python scripts/gen_unverified_report.py --check    # 只比对（漂移退出码 1），供门禁委派
"""
import argparse
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_MD = os.path.join(BASE, 'knowledge', '_reports', 'unverified.md')
OUT_JSON = os.path.join(BASE, 'knowledge', '_reports', 'unverified.json')

MARK = re.compile(r'待确认|待验证|待真机|未核|未验证|存疑|尚未实测|不作为结论|需真机|留待验证')
CLUE = re.compile(r'`[^`]+`|实测|复验|跑一次|命令|adb |cat /proc|df -|getprop|md5|截图|上机'
                  r'|自证|按 §|见 §|先量|先测|重做|核对|判据')
NA = re.compile(r'无需复验方法|无需方法|非可验项')
SKIP_DIRS = {'_reports', '_logs', 'inbox', '__pycache__'}
# 派生页：内容由注册表生成（`--check` 门禁盯着），其「待测/未验证」是**注册表投影**、
# 不是待办 —— 手写标注也会被下次重生成抹掉，所以这里整体跳过（改要去改注册表/生成器）。
SKIP_DOCS = {'knowledge/devflow/platform-capability-matrix.md',
             'knowledge/devflow/builtin-packages.md',
             'knowledge/hardware/hardware-models.md',
             'knowledge/media/media-capability-index.md',
             'knowledge/components/components-catalog.md',
             'knowledge/devflow/flow-index.md'}


def scan():
    docs = []
    for root, dirs, files in os.walk(os.path.join(BASE, 'knowledge')):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in sorted(files):
            if not fn.endswith('.md'):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, BASE).replace(os.sep, '/')
            if rel in SKIP_DOCS:
                continue
            lines = io.open(p, encoding='utf-8', errors='replace').read().splitlines()
            start = 0
            if lines and lines[0].strip() == '---':
                for i in range(1, len(lines)):
                    if lines[i].strip() == '---':
                        start = i + 1
                        break
            section, rows = '(文首)', []
            for i in range(start, len(lines)):
                ln = lines[i]
                if ln.startswith('#'):
                    section = ln.strip('# ').strip()
                    continue
                if MARK.search(ln) and ln.strip():
                    rows.append({'line': i + 1, 'section': section, 'text': ln.strip()[:200],
                                 'na': bool(NA.search(ln)), 'hasHow': bool(CLUE.search(ln))})
            if rows:
                docs.append({'doc': rel, 'items': rows})
    return docs


def render(docs):
    tot = sum(len(d['items']) for d in docs)
    nohow_rows = [(d['doc'], it) for d in docs for it in d['items']
                  if not it['hasHow'] and not it.get('na')]
    na_rows = [(d['doc'], it) for d in docs for it in d['items'] if it.get('na')]
    L = ['# 未核 / 待验证清单（派生视图 —— 别在这里手改）', '',
         '> 本文件由 `scripts/gen_unverified_report.py` **扫描知识页派生**，不是真源。',
         '> 每条结论的**真源在它自己那一页**（改内容请改那一页，然后重跑本脚本）。', '',
         '合计 **%d 处**，分布在 **%d 篇**：**%d 处没给"怎么复验"**（见文末），'
         '**%d 处已明确去向（无需复验方法）**。' % (tot, len(docs), len(nohow_rows), len(na_rows)), '',
         '> ⚠️ 标记行是**提示不是判决**：本表只按关键词聚合，是否真的未核要读它所在那一节。', '']
    for d in docs:
        L.append('## %s（%d 处）' % (d['doc'], len(d['items'])))
        L.append('')
        L.append('| 行 | 所在小节 | 内容 | 去向 |')
        L.append('|---|---|---|---|')
        for it in d['items']:
            way = '无需方法' if it.get('na') else ('有方法' if it['hasHow'] else '**缺方法**')
            L.append('| %d | %s | %s | %s |' % (it['line'], it['section'].replace('|', '\\|')[:40],
                                                it['text'].replace('|', '\\|')[:150], way))
        L.append('')
    L += ['## 没给"怎么复验"的（%d 处 —— 补一句复验方法比补一句结论更有用）' % len(nohow_rows), '']
    for doc, it in nohow_rows:
        L.append('- `%s:%d`  %s' % (doc.replace('knowledge/', ''), it['line'], it['text'][:140]))
    L += ['', '## 已明确去向：无需复验方法（%d 处）' % len(na_rows), '']
    for doc, it in na_rows:
        L.append('- `%s:%d`  %s' % (doc.replace('knowledge/', ''), it['line'], it['text'][:140]))
    return '\n'.join(L) + '\n', tot, len(nohow_rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    docs = scan()
    md, tot, nohow = render(docs)
    blob = json.dumps({'total': tot, 'docs': len(docs), 'withoutHow': nohow, 'items': docs},
                      ensure_ascii=False, indent=1) + '\n'
    if a.check:
        old_md = io.open(OUT_MD, encoding='utf-8').read() if os.path.isfile(OUT_MD) else ''
        old_js = io.open(OUT_JSON, encoding='utf-8').read() if os.path.isfile(OUT_JSON) else ''
        if old_md != md or old_js != blob:
            print('[FAIL] 未核清单已滞后（跑 python scripts/gen_unverified_report.py 重生成）')
            return 1
        print('[PASS] 未核清单与知识页一致（%d 处 / %d 篇 / 缺方法 %d）' % (tot, len(docs), nohow))
        return 0
    if not os.path.isdir(os.path.dirname(OUT_MD)):
        os.makedirs(os.path.dirname(OUT_MD))
    io.open(OUT_MD, 'w', encoding='utf-8', newline='\n').write(md)
    io.open(OUT_JSON, 'w', encoding='utf-8', newline='\n').write(blob)
    print('报告 -> %s / %s（%d 处 / %d 篇 / 缺复验方法 %d）'
          % (os.path.relpath(OUT_MD, BASE), os.path.relpath(OUT_JSON, BASE), tot, len(docs), nohow))
    return 0


if __name__ == '__main__':
    sys.exit(main())
