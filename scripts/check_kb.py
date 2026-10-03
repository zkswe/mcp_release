# -*- coding: utf-8 -*-
"""知识库门禁（P1）：front-matter 合规 / kb_index 新鲜 / inbox 不进索引 / 状态与证据一致。

用法：python scripts/check_kb.py        # 退出码 0 = 全过；1 = 有 FAIL（进 check_consistency）
"""
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
system_path = os.path.join(BASE, 'scripts')
if system_path not in sys.path:
    sys.path.insert(0, system_path)
import kb_local as kbl          # noqa: E402
import gen_kb_index as gki      # noqa: E402

CATEGORIES = gki.CATEGORIES


def main():
    fails, notes = [], []
    total = verified = withev = needsev = 0
    st, signed = {}, 0
    # ① front-matter 合规（含 verified 必须有证据或显式 needs_evidence）
    for cat in CATEGORIES:
        d = os.path.join(kbl.TOTAL_KB, cat)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith('.md') or f == 'README.md':
                continue
            p = os.path.join(d, f)
            rel = os.path.relpath(p, BASE).replace(os.sep, '/')
            meta, body, ferr = kbl.parse_front_matter(io.open(p, encoding='utf-8').read())
            total += 1
            if not meta:
                fails.append('%s 缺 front-matter' % rel)
                continue
            errs = kbl.validate_meta(meta, rel)
            if ferr:
                errs.append(ferr)
            if errs:
                fails.append('%s → %s' % (rel, '；'.join(errs)))
            # ⑥ 派生页的「本页是派生物」声明：读者是 AI，只留"别手改 + 从哪派生"这一句
            #   （口径见 skill `flythings-domain-registry`「判据页是给 AI 的，不是给维护者的」）
            #   实测踩过的写法：把生成器脚本、门禁对账口径（`::`）、真源路径全写进声明块，
            #   正文一行没瘦、头部先胖了五行的都有 —— 那些信息页头 `source:` 与门禁本身已经承接。
            if meta.get('origin') == 'derived':
                # 声明块 = **从「派生物/不要手改」那行起**的连续引用行（空引用行 `>` 视为段落分隔）
                head, started = [], False
                for ln in body.splitlines():
                    if not started:
                        if ln.startswith('>') and ('派生物' in ln or '不要手改' in ln):
                            started = True
                            head.append(ln)
                        continue
                    if ln.startswith('>') and ln.strip() != '>':
                        head.append(ln)
                    else:
                        break
                if not head:
                    fails.append('%s 是派生页但缺「本页是派生物」声明（读者会以为能手改）' % rel)
                elif len(head) > 3:
                    fails.append('%s 的派生物声明占了 %d 行（>3）—— 派生物读者是 AI，'
                                 '一句「别手改 + 从哪派生」就够' % (rel, len(head)))
                for ln in head:
                    for bad in ('scripts/', '::'):
                        if bad in ln:
                            fails.append('%s 的派生物声明里出现 %r（生成器路径/对账口径是维护者信息，'
                                         '别进 AI 语料）' % (rel, bad))
            if meta.get('status') == 'draft':
                fails.append('%s 在分类目录下是 draft —— 候选请放 knowledge/inbox/'
                             '（draft 不进索引/检索）' % rel)
            st[meta.get('status') or '?'] = st.get(meta.get('status') or '?', 0) + 1
            if meta.get('status') == 'verified':
                verified += 1
            if meta.get('evidence'):
                withev += 1
            if meta.get('needs_evidence'):
                needsev += 1
            if meta.get('status') == 'verified' and (meta.get('reviewed_by')
                                                     or meta.get('machine_verified_at')):
                signed += 1
    # ② kb_index 新鲜（源哈希 + 篇数）
    idx_path = os.path.join(kbl.TOTAL_KB, 'kb_index.json')
    if not os.path.isfile(idx_path):
        fails.append('缺 knowledge/kb_index.json（生成：python scripts/gen_kb_index.py）')
    else:
        old = json.load(io.open(idx_path, encoding='utf-8'))
        fresh = gki.build()
        if old.get('meta', {}).get('source_hash') != fresh['meta']['source_hash']:
            fails.append('kb_index.json 与磁盘不一致（源哈希 %s ≠ %s）→ 重跑 gen_kb_index.py'
                         % (old.get('meta', {}).get('source_hash'), fresh['meta']['source_hash']))
        # ③ inbox 不进索引（候选区可见但不入索引/检索）
        in_inbox = [d.get('path') for d in (old.get('docs') or [])
                    if '/inbox/' in (d.get('path') or '')]
        if in_inbox:
            fails.append('knowledge/inbox/ 的候选条目混进了 kb_index（%d 条）：%s'
                         % (len(in_inbox), ', '.join(in_inbox[:3])))
        # ④ 索引里不应有不可索引状态（draft/deprecated）的文档
        bad_status = [d.get('path') for d in (old.get('docs') or [])
                      if (d.get('status') or '') not in kbl.INDEXABLE_STATUS]
        if bad_status:
            fails.append('索引含不可索引状态（draft/deprecated）的文档 %d 篇：%s'
                         % (len(bad_status), ', '.join(bad_status[:3])))
        # ⑤ 只报数：无问法登记篇数（P2 起 verified 新条目强制 ≥5 问法）
        s = old.get('summary') or {}
        notes.append('篇数 %s ｜ verified %s ｜ 带证据 %s ｜ 待补证据 %s ｜ 无问法登记 %s ｜ inbox 候选 %s'
                     % (s.get('total'), s.get('byStatus', {}).get('verified'),
                        s.get('withEvidence'), s.get('needsEvidence'), s.get('noQueries'),
                        s.get('inbox')))
    # ⑤ 候选区（inbox）的 front-matter 也必须合规（这是能晋升的最低要求），但**不许进索引**
    inbox = os.path.join(kbl.TOTAL_KB, 'inbox')
    cand = 0
    if os.path.isdir(inbox):
        for f in sorted(os.listdir(inbox)):
            if not f.endswith('.md') or f == 'README.md':
                continue
            cand += 1
            p = os.path.join(inbox, f)
            rel = os.path.relpath(p, BASE).replace(os.sep, '/')
            meta, _b, ferr = kbl.parse_front_matter(io.open(p, encoding='utf-8').read())
            if not meta:
                fails.append('%s 缺 front-matter（候选也要带元数据才能晋升）' % rel)
                continue
            errs = kbl.validate_meta(meta, rel)
            if ferr:
                errs.append(ferr)
            if meta.get('status') not in ('draft', 'review'):
                fails.append('%s 在候选区但 status=%s（候选只能是 draft/review；要发布请移出 inbox 走晋升）'
                             % (rel, meta.get('status')))
            if errs:
                fails.append('%s → %s' % (rel, '；'.join(errs)))
        notes.append('候选区（inbox）: %d 篇（可见但不进索引/检索）' % cand)
    print('=' * 72)
    print('知识库门禁（check_kb）')
    for n in notes:
        print('  [INFO]', n)
    print('  本地层目录:', kbl.kb_dir())
    for f in fails:
        print('  [FAIL]', f)
    print('  统计：篇数 %d ｜ verified %d ｜ 带可执行证据 %d ｜ 显式待补证据 %d ｜ 已签字/机验 %d'
          % (total, verified, withev, needsev, signed))
    print('  状态分布：%s' % ', '.join('%s=%d' % kv for kv in sorted(st.items())))
    if fails:
        print('[FAIL] 知识库门禁 %d 项' % len(fails))
        return 1
    print('[PASS] 知识库门禁全过（front-matter 合规 + kb_index 新鲜 + inbox 未入索引）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
