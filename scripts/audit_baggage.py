# -*- coding: utf-8 -*-
"""历史包袱 / 知识散落 体检（只读，不改任何文件）。

为什么要有它：要「减少历史包袱、把重复散落的知识归集」，第一步得让包袱**可测量**——
否则每次争论都是印象。四个主指标 + 两组明细，变化趋势就是归集工作是否奏效的证据。

指标：
  files / size       总文件数与体积（目标：减）
  dup_groups / waste 完全重复的内容组数与**工作区**冗余体积（注意：git 按内容/delta 去重，
                 不等于仓库体积，也不都是可回收空间——例：bin_tools 按平台各放一份是设计）
  basename_ge3       同名文件散落处数（≥3 处的名字个数；目标：减）
  concept_scatter    同一概念出现在多少篇 md 里（目标：收敛到 1 篇真源 + 指针）

用法：
    python scripts/audit_baggage.py            # 人读报告
    python scripts/audit_baggage.py --json     # 机器可读（可存基线看趋势）
    python scripts/audit_baggage.py --top 25   # 明细条数
"""
import argparse
import hashlib
import io
import json
import os
import sys
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIR = {'__pycache__', '.git', 'node_modules', 'temp', '.workbuddy', '.vscode',
            'models', 'i18n'}
# 「实例目录」天然自带整份 src 骨架拷贝（每个 example 一份），单独归类，不与真·重复混淆
INSTANCE = ('components/', 'demos/', 'packages/', 'templates/')

# 概念 → 检索词：用来量「同一知识散落在多少篇 md 里」
CONCEPTS = [
    ('thumb 子盒', 'thumb'),
    ('staleOnDevice 判据', 'staleOnDevice'),
    ('activity 禁手改', 'mainActivity'),
    ('图片尺寸==控件盒', '控件盒'),
    ('findControlByID', 'findControlByID'),
    ('libc glibc/musl', 'glibc'),
    ('UI 生命周期', 'onUI_show'),
    ('分区/升级 img', 'update.img'),
    ('视频层 vdec', 'vdec_chn'),
    ('i18n 逐字节', '逐字节'),
    ('配色/对比度', '对比度'),
]

# IDE 冗余口径（B6 后）：只算**真正不该入库**的三类（本机状态 / 工具生成物）。
# `.project`/`.cproject`/`.settings/*.prefs` 是工程必需（IDE 编译 + op 读 resolution），**不算冗余**。
IDE_JUNK_SUFFIX = ('.pyc',)
IDE_JUNK_NAME = ('language.settings.xml', 'org.eclipse.core.runtime.prefs', '.deps.lock')


def walk():
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIR]
        for f in files:
            yield os.path.relpath(os.path.join(root, f), BASE).replace('\\', '/')


def rel(p):
    return os.path.join(BASE, p)


def read(p):
    try:
        with io.open(rel(p), encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return ''


def measure():
    files = list(walk())
    size = {}
    for p in files:
        try:
            size[p] = os.path.getsize(rel(p))
        except OSError:
            size[p] = 0

    # 完全重复
    dig = defaultdict(list)
    unreadable = []
    for p in files:
        if size[p] == 0 or size[p] > 2_000_000:
            continue
        try:
            with open(rel(p), 'rb') as f:
                dig[hashlib.sha1(f.read()).hexdigest()].append(p)
        except OSError as e:
            unreadable.append('%s (%s)' % (p, e.strerror or e))   # 不静默：读不了要报出来
    if unreadable:
        print('[warn] %d 个文件读不了，已跳过：%s' % (len(unreadable), ', '.join(unreadable[:3])))
    dups = {k: v for k, v in dig.items() if len(v) > 1}
    dup_real = [v for v in dups.values() if not all(x.startswith(INSTANCE) for x in v)]
    dup_inst = [v for v in dups.values() if all(x.startswith(INSTANCE) for x in v)]

    # 同名散落
    byname = defaultdict(list)
    for p in files:
        byname[os.path.basename(p)].append(p)
    basename_ge3 = {k: v for k, v in byname.items() if len(v) >= 3}

    docs = [p for p in files if p.endswith('.md')]
    texts = {p: read(p) for p in docs}
    scatter = []
    for label, kw in CONCEPTS:
        hits = [p for p, t in texts.items() if kw in t]
        scatter.append({'concept': label, 'files': len(hits),
                        'in_knowledge': sum(1 for p in hits if p.startswith('knowledge/')),
                        'sample': hits[:3]})
    scatter.sort(key=lambda r: -r['files'])

    junk = [p for p in files
            if p.endswith(IDE_JUNK_SUFFIX) or os.path.basename(p) in IDE_JUNK_NAME]
    top = defaultdict(lambda: [0, 0])
    for p in files:
        k = p.split('/')[0] + ('/' if '/' in p else '')
        top[k][0] += 1
        top[k][1] += size[p]

    return {
        'files': len(files),
        'size_mb': round(sum(size.values()) / 1e6, 2),
        'top_dirs': sorted(({'dir': k, 'files': v[0], 'mb': round(v[1] / 1e6, 2)}
                            for k, v in top.items()), key=lambda r: -r['files'])[:14],
        'md_total': len(docs),
        'md_knowledge': sum(1 for p in docs if p.startswith('knowledge/')),
        'md_components': sum(1 for p in docs if p.startswith('components/')),
        'dup_groups': len(dups), 'dup_files': sum(len(v) for v in dups.values()),
        'dup_waste_mb': round(sum(size[v[0]] * (len(v) - 1) for v in dups.values()) / 1e6, 2),
        'dup_real': sorted(({'bytes': size[v[0]], 'n': len(v), 'files': v[:4]}
                            for v in dup_real), key=lambda r: -r['bytes']),
        'dup_instance_groups': len(dup_inst),
        'basename_ge3': len(basename_ge3),
        'basename_detail': sorted(({'name': k, 'n': len(v), 'sample': v[:3]}
                                   for k, v in basename_ge3.items()), key=lambda r: -r['n']),
        'concept_scatter': scatter,
        'ide_junk_files': len(junk),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--top', type=int, default=12)
    a = ap.parse_args()
    m = measure()
    if a.json:
        print(json.dumps(m, ensure_ascii=False, indent=2))
        return 0
    print('文件 %d 个 / %.2f MB    md %d（knowledge/ %d、components/ %d）'
          % (m['files'], m['size_mb'], m['md_total'], m['md_knowledge'], m['md_components']))
    print('完全重复：%d 组 / %d 个文件 / 冗余 %.2f MB（其中全在实例目录里的 %d 组）'
          % (m['dup_groups'], m['dup_files'], m['dup_waste_mb'], m['dup_instance_groups']))
    print('同名散落（≥3 处）：%d 个名字        IDE 冗余文件（本机状态/工具生成物）：%d'
          % (m['basename_ge3'], m['ide_junk_files']))
    print('\n同一概念散落在多少篇 md：')
    for r in m['concept_scatter']:
        print('  %-20s %2d 篇（knowledge/ %d）%s'
              % (r['concept'], r['files'], r['in_knowledge'], ' ← 该归集' if r['files'] >= 5 else ''))
    print('\n非实例重复（前 %d，这些是真正该收编的）：' % a.top)
    for r in m['dup_real'][:a.top]:
        print('  %8d B ×%-2d %s' % (r['bytes'], r['n'], ' | '.join(r['files'][:3])))
    print('\n同名散落（前 %d）：' % a.top)
    for r in m['basename_detail'][:a.top]:
        print('  %-26s ×%-3d %s' % (r['name'], r['n'], ' | '.join(r['sample'][:2])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
