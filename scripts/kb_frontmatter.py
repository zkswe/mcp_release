# -*- coding: utf-8 -*-
"""给 knowledge/**/*.md 补 / 校验 front-matter（P1 迁移工具，幂等）。

用法：
    python scripts/kb_frontmatter.py            # 补 front-matter（已有序号不动）
    python scripts/kb_frontmatter.py --check     # 只校验（进 CI 门禁；不合规 exit 1）
    python scripts/kb_frontmatter.py --stats     # 出体检数字（verified / 带证据 / 待补证据）

口径（P1）：历史文档一律先认成 `status: verified` + `confidence: manual` +
`needs_evidence: true` —— 它们确实在用，但**没有可执行判据**；这次迁移第一次把这个
"含水量"显式记下来（P2 再逐条补 evidence）。新条目必须带 evidence 才允许 verified。
"""
import argparse
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import kb_local as kbl          # noqa: E402

CATEGORIES = ('devflow', 'uicontrols', 'hardware', 'esl', 't113-car', 'v85x')
SKIP_FILES = ('README.md',)
# 派生文档（生成物）：front-matter 由生成器（gen_hardware_doc.py 等）拥有 ——
# --retags / --fix-states / kb_verify --apply 都不许改它（否则与生成器输出漂移）
DERIVED_DOCS = kbl.DERIVED_DOCS
PLATFORM_TOKENS = ('F133', 'F135', 'Z20', 'Z21', 'Z235X', 'T113', 'V85X', 'V851S')
GUIDE_RE = re.compile(r'检索导引[^\n]*\n((?:>[^\n]*\n)+)', re.S)
TAG_SPLIT = re.compile(r'[・、,，/｜|；;（）()\[\]「」。.\n]+')


def _tags_from_guide(text):
    """**只**从 `> 检索导引：…` 块抽 tags，并逐个过 kb_local.clean_tag。

    2026-09-29 修（提报发现）：首轮抽取把正文碎片当 tags（`<包名` / `**` / `检索词：…`）写进 33/85 篇，
    而 tags 是**索引的一部分** ⇒ 噪声 token 会造假命中。现只从「检索导引」这一人工写的问题集合抽，
    且逐个洗（禁反引号/星号/尖括号/分号等），不合规直接丢。
    """
    g = GUIDE_RE.search(text)
    if not g:
        return []
    out = []
    for chunk in TAG_SPLIT.split(g.group(1).replace('>', ' ')):
        t = kbl.clean_tag(chunk)
        if t and t not in out:
            out.append(t)
        if len(out) >= kbl.MAX_TAGS:
            break
    return out


def _docs():
    out = []
    for cat in CATEGORIES:
        d = os.path.join(kbl.TOTAL_KB, cat)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith('.md') or f in SKIP_FILES:
                continue
            out.append((cat, os.path.join(d, f)))
    return out


def _infer(cat, path, text):
    title = ''
    m = re.search(r'^#\s+(.+)$', text, re.M)
    if m:
        title = m.group(1).strip()
    if not title:
        title = os.path.splitext(os.path.basename(path))[0]
    stem = os.path.splitext(os.path.basename(path))[0]
    tags = _tags_from_guide(text)
    plats = []
    for p in PLATFORM_TOKENS:
        if len(re.findall(re.escape(p), text, re.I)) >= 3:
            plats.append(p)
    return {
        'id': '%s-%s' % (cat, kbl.slugify(stem, 40)),
        'title': title, 'category': cat, 'platforms': plats, 'tags': tags[:6],
        'status': 'verified', 'confidence': 'manual', 'verified_at': kbl.today(),
        'stale_days': 180, 'origin': 'total',
        'source': '2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）',
        'needs_evidence': True,
    }


def run(check=False, stats=False, retags=False, fix_states=False):
    missing, bad, added, extra = [], [], 0, []
    retagged, dropped, restated = 0, [], 0
    counts = {'total': 0, 'verified': 0, 'withEvidence': 0, 'needsEvidence': 0,
              'byCategory': {}, 'noGuide': 0}
    for cat, path in _docs():
        counts['total'] += 1
        counts['byCategory'][cat] = counts['byCategory'].get(cat, 0) + 1
        text = io.open(path, encoding='utf-8').read()
        if '检索导引' not in text:
            counts['noGuide'] += 1
        meta, body, ferr = kbl.parse_front_matter(text)
        rel = os.path.relpath(path, BASE).replace(os.sep, '/')
        if not meta:
            if check:
                missing.append(rel)
                continue
            meta = _infer(cat, path, text)
            new = kbl.dump_front_matter(meta, text)
            with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(new)
            added += 1
        elif fix_states and rel not in DERIVED_DOCS:
            # P0-1：存量“在用但无可执行判据”的文档从 verified 降为 review（verified 只留给带判据+签字的）
            hard = [e for e in (meta.get('evidence') or [])
                    if isinstance(e, dict) and (e.get('cmd') or e.get('artifact'))]
            if meta.get('status') == 'verified' and not hard:
                meta['status'] = 'review'
                meta['needs_evidence'] = True
                with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(kbl.dump_front_matter(meta, body))
                restated += 1
        elif retags and rel not in DERIVED_DOCS:
            new_tags = _tags_from_guide(body or text)
            if new_tags != (meta.get('tags') or []):
                for t in (meta.get('tags') or []):
                    if t not in new_tags:
                        dropped.append((rel, t))
                meta['tags'] = new_tags
                with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(kbl.dump_front_matter(meta, body))
                retagged += 1
        errs = kbl.validate_meta(meta, rel)
        if ferr:
            errs.append(ferr)
        if errs:
            bad.append((rel, errs))
        if meta.get('status') == 'verified':
            counts['verified'] += 1
        if meta.get('evidence'):
            counts['withEvidence'] += 1
        if meta.get('needs_evidence'):
            counts['needsEvidence'] += 1
        if meta.get('evidence') and meta.get('needs_evidence'):
            extra.append(rel)
    if stats or not check:
        print('knowledge 体检：共 %d 篇 ｜ verified %d ｜ 带可执行证据 %d ｜ 显式待补证据 %d ｜ 无检索导引 %d'
              % (counts['total'], counts['verified'], counts['withEvidence'],
                 counts['needsEvidence'], counts['noGuide']))
        print('  分类：%s' % ', '.join('%s=%d' % kv for kv in sorted(counts['byCategory'].items())))
        if added:
            print('  本次补齐 front-matter：%d 篇' % added)
        if retagged:
            print('  本次重抽 tags：%d 篇；丢掉的非检索词碎片 %d 个（例：%s）'
                  % (retagged, len(dropped),
                     '、'.join('%s' % t for _, t in dropped[:6])))
        if restated:
            print('  本次状态降级（verified→review，无判据）: %d 篇' % restated)
        if counts['noGuide']:
            print('  ⚠️ %d 篇缺「检索导引」行（tags 会为空）' % counts['noGuide'])
    fail = 0
    if missing:
        print('[FAIL] %d 篇缺 front-matter：%s' % (len(missing), ', '.join(missing[:6])))
        fail = 1
    for rel, errs in bad:
        print('[FAIL] %s → %s' % (rel, '；'.join(errs)))
        fail = 1
    if not fail:
        print('[PASS] front-matter 全合规（%d 篇）' % counts['total'])
    return fail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='只校验，不改文件（门禁用）')
    ap.add_argument('--stats', action='store_true', help='出体检数字')
    ap.add_argument('--retags', action='store_true',
                    help='重抽 tags（只从「检索导引」行；清掉历史污染）')
    ap.add_argument('--fix-states', action='store_true',
                    help='P0-1：把「无 cmd/artifact 判据」的 verified 降为 review')
    a = ap.parse_args()
    return run(check=a.check, stats=a.stats, retags=a.retags, fix_states=a.fix_states)


if __name__ == '__main__':
    sys.exit(main())
