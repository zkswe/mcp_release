# -*- coding: utf-8 -*-
"""多媒体能力注册表（media_capabilities.json）的**唯一消费入口**。

纪律（与 op_spec_loader / platform_cap_loader / lifecycle_loader 同构）：
- 缺失、损坏、查不存在的条目 → 抛 `MediaCapError`，**不静默退回内嵌副本**；
- 包的可用性/版本**不在这里**：本模块在查询时与 `package_catalog.json` 联接
  （包的可用性真源是 package_catalog，本表只登记「能力 → 用哪个包/库/入口 + 限制 + 出处」）；
- 平台名走 `platforms.resolve()`（与全仓同一套归一，不另写一份词表）。

用法：python media_cap_loader.py            # 自检 + 概览
"""
import io
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

SPEC = os.path.join(BASE, 'media_capabilities.json')
DOC_PATH = 'knowledge/media/media-capability-index.md'
REQUIRED = ('id', 'title', 'kind', 'summary')


class MediaCapError(Exception):
    """注册表缺失/损坏/查不到时抛（调用方据此报错，不要吞）。"""


_cache = {}


def _read_json(path, what):
    if not os.path.isfile(path):
        raise MediaCapError('%s 不存在：%s' % (what, path))
    try:
        with io.open(path, encoding='utf-8') as fh:
            return json.loads(fh.read())
    except ValueError as e:
        raise MediaCapError('%s 不是合法 JSON：%s（%s）' % (what, path, e))


def load():
    """读注册表（带缓存）。损坏即抛 MediaCapError。"""
    if 'spec' not in _cache:
        d = _read_json(SPEC, '多媒体能力注册表')
        if not (d.get('capabilities') or []):
            raise MediaCapError('注册表里 capabilities 为空：%s' % SPEC)
        _cache['spec'] = d
    return _cache['spec']


def _catalog():
    """package_catalog.json → {包名: {平台键: 版本}}（包的可用性真源，只读）。"""
    if 'cat' not in _cache:
        d = _read_json(os.path.join(BASE, 'package_catalog.json'), '包目录')
        out = {}
        for pk, v in d.items():
            for p in (v.get('packages') or []):
                out.setdefault(p.get('name'), {})[pk] = p.get('version')
        _cache['cat'] = out
    return _cache['cat']


def doc_path():
    return DOC_PATH


def kinds():
    """能力大类 → {key: 中文名}。"""
    return dict(load().get('kinds') or {})


def layers():
    """图层清单（UI/OSD、视频层、独立硬件图层）。"""
    return list(load().get('layers') or [])


def capabilities(kind=None):
    """全部能力（可按 kind 过滤）。"""
    caps = list(load().get('capabilities') or [])
    if not kind:
        return caps
    return [c for c in caps if c.get('kind') == kind]


def cap(cap_id):
    """按 id 取一条能力；不存在 → 抛（并给相近 id 提示）。"""
    for c in capabilities():
        if c.get('id') == cap_id:
            return c
    near = [c['id'] for c in capabilities()
            if cap_id and (cap_id[:4] in c['id'] or c['id'][:4] in (cap_id or ''))]
    raise MediaCapError('没有这条多媒体能力：%r%s'
                        % (cap_id, ('；相近：' + ', '.join(near[:4])) if near else ''))


def packages_of(cap_id):
    """该能力涉及的包名（真源是注册表的 packages 字段；可用性去 catalog 查）。"""
    return list(cap(cap_id).get('packages') or [])


def hints_of(cap_id):
    """该能力的口语问法（口语检索用；每条能力必须至少 1 条，门禁会查）。"""
    return list(cap(cap_id).get('hints') or [])


def libs_of(cap_id):
    """该能力涉及的设备预装/系统库（免编译那类）。"""
    return list(cap(cap_id).get('libs') or [])


def availability(cap_id):
    """该能力的**平台可用性**：与 package_catalog 联接 → {规范平台名: {包名: 版本}}。

    这是本模块的主要价值：注册表只写「用哪个包」，可用性由 catalog 派生 ——
    两边一旦对不上（注册表引用了 catalog 里没有的包），`validate()` 会直接报出来。
    """
    cat = _catalog()
    out = {}
    for name in packages_of(cap_id):
        for pkg_key, ver in (cat.get(name) or {}).items():
            plat = _canon(pkg_key)
            out.setdefault(plat, {})[name] = ver
    return out


def platforms_of(cap_id):
    """该能力覆盖的规范平台名（排序）。仅由包派生；libs-only 的能力回空表。"""
    return sorted(availability(cap_id).keys())


def caps_for_package(package):
    """某个包被哪些能力用到（反向索引）。"""
    return [c['id'] for c in capabilities() if package in (c.get('packages') or [])]


def for_query(text):
    """按关键词找能力（检索返回体注入用）→ [能力 dict]。

    匹配面：id / title / summary / rules / retrievalHints（口语在 hints 里）。
    """
    q = re.sub(r'\s+', '', str(text or ''))
    if not q:
        return []
    hits = []
    for c in capabilities():
        hint_blob = ''.join(c.get('hints') or [])
        body_blob = ''.join([c.get('id', ''), c.get('title', ''), c.get('summary', '')] +
                            list(c.get('rules') or []) + list(c.get('libs') or []))
        # 口语问法权重更高（用户问法通常直接命中 hints，而非能力正文）
        score = max(3 * _overlap(hint_blob, q), _overlap(body_blob, q))
        if score:
            hits.append((score, c))
    hits.sort(key=lambda t: -t[0])
    return [c for _s, c in hits[:4]]


def _overlap(a, b):
    """a、b 的 4 字滑窗重合数（对"插入词"容忍）。"""
    sa = re.sub(r'[\s，。；：/（）()、\-→]', '', str(a or ''))
    sb = re.sub(r'[\s，。；：/（）()、\-→]', '', str(b or ''))
    if len(sa) < 4 or len(sb) < 4:
        return 0
    ga = {sa[i:i + 4] for i in range(len(sa) - 3)}
    gb = {sb[i:i + 4] for i in range(len(sb) - 3)}
    return len(ga & gb)


def _canon(pkg_key):
    """包键 → 规范平台名（走 platforms.resolve；不认识的键原样返回，不猜）。"""
    try:
        import platforms as pl
        r = pl.resolve(pkg_key)
        return r.get('canonical') or pkg_key
    except Exception:
        return pkg_key


def validate(include_doc=True):
    """自检 → [问题字符串]（空 = 通过）。门禁据此判。

    `include_doc=False`：生成器自己调用时用（那一刻派生页还没写，不该判它缺）。

    查四类：① 必需字段与 kind 合法、id 唯一；② `docRef` **真实存在**（死指针会让 AI 去搜不存在的东西）；
    ③ `packages` 里的每个包**在 package_catalog 里确有**（跨来源对账：注册表说"用这个包"而
    catalog 没有 = 这条能力落不了地）；④ retrievalHints 能被归属到某条能力（否则是写给自己看的死话）。
    """
    errs = []
    d = load()
    ks = set((d.get('kinds') or {}).keys())
    seen = set()
    cat = _catalog()
    for c in capabilities():
        cid = c.get('id') or '(无 id)'
        for f in REQUIRED:
            if not str(c.get(f) or '').strip():
                errs.append('%s: 缺字段 %s' % (cid, f))
        if c.get('kind') not in ks:
            errs.append('%s: kind=%r 不在 kinds 里' % (cid, c.get('kind')))
        if cid in seen:
            errs.append('%s: id 重复' % cid)
        seen.add(cid)
        dr = c.get('docRef') or ''
        if not dr:
            errs.append('%s: 缺 docRef（出处）' % cid)
        elif not os.path.isfile(os.path.join(BASE, dr)):
            errs.append('%s: docRef 指向不存在的文档 %s' % (cid, dr))
        if not (c.get('hints') or []):
            errs.append('%s: 缺 hints（口语问法；检索靠它命中）' % cid)
        for name in (c.get('packages') or []):
            if name not in cat:
                errs.append('%s: 引用了 package_catalog 里没有的包 %r' % (cid, name))
        for demo in ([c['demo']] if c.get('demo') else []):
            if not os.path.exists(os.path.join(BASE, demo)):
                errs.append('%s: demo 路径不存在 %s' % (cid, demo))
    if include_doc and DOC_PATH and not os.path.isfile(os.path.join(BASE, DOC_PATH)):
        errs.append('派生知识页不存在（跑 scripts/gen_media_cap_doc.py）：%s' % DOC_PATH)
    return errs


if __name__ == '__main__':
    errs = validate()
    if errs:
        print('[FAIL] 注册表自检未过：')
        for e in errs[:12]:
            print('   -', e)
        raise SystemExit(1)
    caps = capabilities()
    print('[PASS] 多媒体能力注册表自检通过')
    print('  能力 %d 条 / 图层 %d 个 / 大类 %s' % (
        len(caps), len(layers()), '/'.join(kinds().keys())))
    print('  按大类：%s' % '，'.join(
        '%s %d' % (kinds()[k], len(capabilities(k))) for k in kinds()))
    for cid in ('video-layer-capture', 'dvr-camera-preview', 'lib-preinstalled'):
        av = availability(cid)
        print('  %-22s → %s' % (cid, '，'.join(
            '%s(%d 包)' % (p, len(v)) for p, v in sorted(av.items()))))
    print('  查「拼墙抓不到画面」→ %s' % [c['id'] for c in for_query('拼墙抓不到画面')])
    print('  查「能不能不编译直接用设备上的库」→ %s'
          % [c['id'] for c in for_query('能不能不编译直接用设备上的库')])
