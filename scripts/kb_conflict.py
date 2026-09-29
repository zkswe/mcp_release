# -*- coding: utf-8 -*-
"""知识冲突检测（P2）：同主题出现**互斥结论**时报出来，等人裁决，绝不允许两条各说各话。

用法：
    python scripts/kb_conflict.py                # 扫总账 + 本地层，出报告（只报告，不阻塞）
    python scripts/kb_conflict.py --fail         # 有候选冲突则退出码 1（给 CI 用）
    python scripts/kb_conflict.py --json out.json

判据（保守，宁少勿滥；每条候选都要人工裁决）：
  ① **极性冲突**：同一「主语窗口」（关键词前 10 字，归一化后 ≥6 字）下，
     一条说正向（必须/支持/推荐/要…）、另一条说负向（不能/不要/禁止/不支持/别…），
     且来自**不同文档** ⇒ 候选冲突
  ② **同主题重复**：指纹（标题+命令+平台）相同但 id 不同 ⇒ 候选重复（该合并）

输出：knowledge/_reports/kb_conflict.{json,md}（gitignore）；`kb_health` 会引用它的计数。
"""
import argparse
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import kb_local as kbl          # noqa: E402

REPORT_DIR = os.path.join(kbl.TOTAL_KB, '_reports')
NEG = ('不能', '不要', '禁止', '不支持', '别用', '不可', '勿', '不允许', '避免', '失效')
POS = ('必须', '要', '支持', '推荐', '应当', '需要', '允许', '保证', '可以')
_ALL = re.compile('|'.join(re.escape(k) for k in (NEG + POS)))
_PUNCT = re.compile(r'[\s`*#>\-—:：,，。;；!！?？"\'()（）\[\]【】「」/\\|]+')
_MAX_LINE = 140


def _subject(line, idx, span=12, min_len=3):
    """关键词前的「主语窗口」：归一化后取前 span 字（太短则丢，避免噪声）。

    min_len=3：`Z20 上必须…` 这种短主语（归一化后 `Z20上`）也要能配对，否则真冲突抓不到。
    """
    head = _PUNCT.sub('', line[:idx])
    if len(head) < min_len:
        return ''
    return head[-span:]


def detect(docs):
    """docs: [(path, text)] → {'polarity': [...], 'duplicate': [...]}（纯函数，便于用例）。"""
    groups = {}
    for path, text in docs:
        for raw in str(text or '').splitlines():
            line = raw.strip()
            if not line or len(line) > _MAX_LINE or line.startswith('|'):
                continue
            m = _ALL.search(line)
            if not m:
                continue
            key = _subject(line, m.start())
            if not key:
                continue
            kind = 'neg' if m.group(0) in NEG else 'pos'
            g = groups.setdefault(key, {'subject': key, 'pos': [], 'neg': []})
            g[kind].append({'doc': path, 'line': line[:120]})
    cands = []
    for key, g in sorted(groups.items()):
        if not (g['pos'] and g['neg']):
            continue
        if {x['doc'] for x in g['pos']} & {x['doc'] for x in g['neg']}:
            continue                        # 同一篇里的正反句（如"不要 A，要 B"）不算冲突
        cands.append({'subject': key, 'positive': g['pos'][:3], 'negative': g['neg'][:3],
                      'docs': sorted({x['doc'] for x in g['pos'] + g['neg']}),
                      'action': '人工裁决：确认哪个结论对，错的标 status=deprecated 并在对的条目标 supersedes'})
    dup = {}
    for path, text in docs:
        meta, _b, _e = kbl.parse_front_matter(text)
        if not meta:
            continue
        fp = kbl.fingerprint(meta)
        dup.setdefault(fp, []).append({'path': path, 'id': meta.get('id')})
    dups = [{'fingerprint': fp, 'entries': v,
             'action': '同主题重复：合并进一条（追加平台矩阵/新证据），保留一条 verified'}
            for fp, v in dup.items() if len({x['id'] for x in v}) > 1]
    return {'polarity': cands, 'duplicate': dups}


def _collect():
    docs = []
    for sub in ('devflow', 'uicontrols', 'hardware', 'esl', 't113-car', 'v85x'):
        d = os.path.join(kbl.TOTAL_KB, sub)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith('.md') and f != 'README.md':
                p = os.path.join(d, f)
                try:
                    docs.append((os.path.relpath(p, BASE).replace('\\', '/'),
                                 io.open(p, encoding='utf-8').read()))
                except OSError as e:
                    print('  [warn] %s 读不了: %s' % (p, e))
    for d in kbl.local_docs():
        try:
            docs.append((d['path'], io.open(d['abs'], encoding='utf-8').read()))
        except OSError as e:
            print('  [warn] %s 读不了: %s' % (d.get('abs'), e))
    return docs


def build():
    res = detect(_collect())
    res['scannedAt'] = kbl._now()
    res['conflictCount'] = len(res['polarity'])
    res['duplicateCount'] = len(res['duplicate'])
    return res


def markdown(r):
    lines = ['# 知识冲突报告（kb_conflict）', '',
             '> 生成时间：%s ｜ 极性冲突 %d ｜ 疑似重复 %d' % (r.get('scannedAt'),
                                                             r['conflictCount'],
                                                             r['duplicateCount']),
             '', '## 一、极性冲突（同主题一正一反，需人工裁决）', '']
    if not r['polarity']:
        lines.append('（无）')
    for i, c in enumerate(r['polarity'], 1):
        lines.append('### %d. 主语「%s」' % (i, c['subject']))
        for x in c['positive']:
            lines.append('- ✅ %s：`%s`' % (x['doc'], x['line']))
        for x in c['negative']:
            lines.append('- ❌ %s：`%s`' % (x['doc'], x['line']))
        lines.append('- 处置：%s' % c['action'])
        lines.append('')
    lines += ['## 二、疑似重复（同指纹不同 id，应合并）', '']
    if not r['duplicate']:
        lines.append('（无）')
    for d in r['duplicate']:
        lines.append('- 指纹 `%s`：%s → %s' % (d['fingerprint'],
                                              ', '.join(x['path'] for x in d['entries']),
                                              d['action']))
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default='')
    ap.add_argument('--md', default='')
    ap.add_argument('--fail', action='store_true', help='有候选冲突则退出码 1')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()
    r = build()
    os.makedirs(REPORT_DIR, exist_ok=True)
    jp = a.json or os.path.join(REPORT_DIR, 'kb_conflict.json')
    mp = a.md or os.path.join(REPORT_DIR, 'kb_conflict.md')
    with io.open(jp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    with io.open(mp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(markdown(r))
    if not a.quiet:
        print('冲突检测：极性冲突 %d ｜ 疑似重复 %d' % (r['conflictCount'], r['duplicateCount']))
        for c in r['polarity'][:5]:
            print('  [冲突] 主语「%s」%s' % (c['subject'], ' vs '.join(c['docs'][:3])))
        for d in r['duplicate'][:3]:
            print('  [重复] %s' % ', '.join(x['path'] for x in d['entries']))
        print('报告 ->', jp, '/', mp)
    return 1 if (a.fail and (r['conflictCount'] or r['duplicateCount'])) else 0


if __name__ == '__main__':
    sys.exit(main())
