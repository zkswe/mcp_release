# -*- coding: utf-8 -*-
"""由 media_capabilities.json（唯一真源）生成知识页 knowledge/media/media-capability-index.md。

用法：
    python scripts/gen_media_cap_doc.py            # 生成/更新
    python scripts/gen_media_cap_doc.py --check    # 只比对（门禁口径；漂移退出码 1）

页面结构：能力总表 → 按大类明细 → 图层 → 平台可用性（由 package_catalog 联接派生）。
"""
import io
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import media_cap_loader as mc                    # noqa: E402
import derived_md                                # noqa: E402

DOC = os.path.join(BASE, mc.doc_path())
# 平台列顺序（只列出注册表能力实际覆盖到的平台）
PLATFORM_ORDER = ['Z20', 'Z21', 'F133', 'F135', 'T113', 'V85X', 'Z235X', 'Z261']

TAGS = ['多媒体', '视频播放', '摄像头预览', '录像', '录音', '对讲', '图层', '视频层',
        '抓帧', 'vdec', 'zkshot', 'ffmpeg', '预装库', 'DVR', '软解', '图片解码']


def _fm():
    d = mc.load()
    return [
        '---',
        'id: media-media-capability-index',
        'title: 多媒体能力索引（播放/录像/录音/图层/抓帧，唯一真源派生）',
        'category: media',
        'status: review',
        'confidence: manual',
        'verified_at: %s' % d.get('updated'),
        'stale_days: 180',
        'origin: derived',
        'source: 由 media_capabilities.json 派生（scripts/gen_media_cap_doc.py）；'
        '平台可用性由 package_catalog.json 联接派生',
        'needs_evidence: false',
        'platforms: []',
        'tags: [%s]' % ', '.join(TAGS),
        'evidence:',
        '  - cmd: python scripts/gen_media_cap_doc.py --check',
        '    expect: rc=0（本页与 media_capabilities.json 一致）',
        '---',
        '',
    ]


def build():
    d = mc.load()
    L = _fm()
    L.append('# 多媒体能力索引（播放 / 录像 / 录音 / 图层 / 抓帧）')
    L.append('')
    L.append('> **唯一真源** = `media_capabilities.json`（本页是它的派生物，手改会被门禁抓）。')
    L.append('> **包的可用性与版本不在这里**：真源 = `package_catalog.json`，本页的平台可用性列由它联接派生。')
    L.append('> 改「用哪个包/库、有什么限制、出处哪篇」→ 改注册表；改「包在哪些平台」→ 改包目录。')
    L.append('')

    # ── 1. 能力总表 ──
    L.append('## 1. 能力总表')
    L.append('')
    L.append('| 能力 | 大类 | 用什么（包 / 免编译库） | 覆盖平台 | 出处 |')
    L.append('|---|---|---|---|---|')
    kinds = mc.kinds()
    for c in mc.capabilities():
        used = []
        if c.get('packages'):
            used.append('包：' + '、'.join('`%s`' % p for p in c['packages']))
        if c.get('libs'):
            used.append('库：' + '、'.join(x.split('（')[0] for x in c['libs']))
        plats = mc.platforms_of(c['id'])
        L.append('| **%s** | %s | %s | %s | `%s` |' % (
            c['title'], kinds.get(c['kind'], c['kind']), '<br>'.join(used) or '—',
            '、'.join(plats) if plats else '免编译库（不占包）',
            os.path.basename(c.get('docRef') or '')))
    L.append('')

    # ── 2. 按大类的能力明细 ──
    L.append('## 2. 能力明细')
    L.append('')
    for k, kname in kinds.items():
        caps = mc.capabilities(k)
        if not caps:
            continue
        L.append('### 2.%d %s' % (list(kinds).index(k) + 1, kname))
        L.append('')
        for c in caps:
            L.append('#### %s' % c['title'])
            L.append('')
            L.append('- **做什么**：%s' % c['summary'])
            if c.get('packages'):
                L.append('- **用哪些包**：%s' % '、'.join('`%s`' % p for p in c['packages']))
            if c.get('libs'):
                L.append('- **可借的库**：%s' % '、'.join(c['libs']))
            if c.get('entry'):
                L.append('- **入口**：%s' % c['entry'])
            if c.get('demo'):
                L.append('- **参考工程**：`%s`' % c['demo'])
            if c.get('platforms'):
                L.append('- **平台**：%s' % '、'.join(c['platforms']))
            for r in (c.get('rules') or []):
                L.append('- ⚠️ %s' % r)
            if c.get('hints'):
                L.append('- **常被问成**：%s' % ' / '.join('「%s」' % h for h in c['hints']))
            L.append('- **出处**：`%s`' % (c.get('docRef') or '—'))
            L.append('')

    # ── 3. 图层 ──
    L.append('## 3. 画面到底在哪一层（抓帧/叠加必读）')
    L.append('')
    L.append('| 图层 | 平台 | 怎么取帧 / 入口 | 说明 |')
    L.append('|---|---|---|---|')
    for ly in mc.layers():
        L.append('| **%s** | %s | %s | %s |' % (
            ly.get('title'), '、'.join(ly.get('platforms') or ['全平台']),
            ly.get('entry') or ('读 `%s`' % ly.get('node')), ly.get('note', '')))
    L.append('')
    for ly in mc.layers():
        for r in (ly.get('rules') or []):
            L.append('> ⚠️ **%s**：%s' % (ly.get('title'), r))
    L.append('')

    # ── 4. 平台可用性（由包目录派生）──
    L.append('## 4. 平台可用性（能力 × 平台，由包目录派生）')
    L.append('')
    used_plats = sorted({p for c in mc.capabilities() for p in mc.platforms_of(c['id'])},
                        key=lambda p: PLATFORM_ORDER.index(p) if p in PLATFORM_ORDER else 99)
    L.append('| 能力 | %s |' % ' | '.join(used_plats))
    L.append('|---|%s|' % ('---|' * len(used_plats)))
    for c in mc.capabilities():
        if not c.get('packages'):
            continue
        av = mc.availability(c['id'])
        cells = ['✓' if p in av else '' for p in used_plats]
        L.append('| %s | %s |' % (c['title'], ' | '.join(cells)))
    L.append('')
    lib_only = '、'.join(c['title'] for c in mc.capabilities() if not c.get('packages'))
    L.append('`✓` = 该能力的**至少一个包**在这个平台可用（包级细节用 `flythings_query_package`）。'
             '只借免编译库的能力（%s）不在此表 —— 它不占包，按设备实有库确认。' % lib_only)
    L.append('')
    return '\n'.join(L)


def main(argv):
    a = set(argv[1:])
    errs = mc.validate(include_doc=False)   # 本脚本正要写它，缺页不算错
    if errs:
        print('[FAIL] 注册表自检未过：')
        for e in errs[:8]:
            print('   -', e)
        return 1
    want = build()
    cur = io.open(DOC, encoding='utf-8').read() if os.path.isfile(DOC) else ''
    if '--check' in a:
        if derived_md.same(cur, want):
            print('[PASS] 已一致，无需更新')
            return 0
        print('[FAIL] 知识页与 media_capabilities.json 不一致（跑 gen_media_cap_doc.py 重生成）')
        return 1
    if derived_md.same(cur, want):
        print('[PASS] 已一致，无需更新')
        return 0
    os.makedirs(os.path.dirname(DOC), exist_ok=True)
    with io.open(DOC, 'w', encoding='utf-8', newline='') as fh:
        fh.write(want)
    print('已写入 %s（%d 行）' % (mc.doc_path(), len(want.splitlines())))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
