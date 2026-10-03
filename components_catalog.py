# -*- coding: utf-8 -*-
"""可复用组件目录（域⑦）的**唯一消费入口**：扫描 `components/`，把「四件套」规则机器化。

为什么是"扫描"而不是新造一份注册表：组件的信息本来就分散在**树本身**里 ——
- 形状（源码型/二进制型/资产工具型）由目录结构决定；
- 依赖包在各自的 `Manifest.xml`（机器可读）；
- 平台可用性真源是 `platform_capabilities.json`（不在本模块重写）；
- 用途/限制在人写的 `README.md` / `platforms.md`。

再造一份 JSON 只会是"第二份真相"。所以这里做的是：
① **判定形态** + ② **核对 `components/README.md` 那条「四件套缺一不收」**（原来纯靠人自觉）+
③ 给 AI 一个可查的目录（有哪些组件、怎么用、示例在哪、缺什么）。

用法：python components_catalog.py          # 自检 + 概览
"""
import io
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

ROOT = 'components'
DOC_PATH = 'knowledge/components/components-catalog.md'

# 三种形态（components/README.md §1 定义）与各自的「四件套」要求（缺一不收）
FORM_SOURCE = 'source'
FORM_BINARY = 'binary'
FORM_ASSET = 'asset'
FORM_NAMES = {FORM_SOURCE: '源码型', FORM_BINARY: '二进制型', FORM_ASSET: '资产/工具型'}
REQUIRED = {
    FORM_SOURCE: ('README.md', 'platforms.md', 'Manifest.xml', 'include', 'src', 'example'),
    FORM_BINARY: ('README.md', 'platforms.md', 'Manifest.xml', 'include', 'lib',
                  'lib/BUILD_INFO.md', 'example', 'scripts'),
    FORM_ASSET: ('README.md', 'platforms.md', 'scripts'),
}
# 不进去找模块的目录：产物目录 + **example/**（示例工程不是模块 —— 它有 README 和 src，
# 按形状会被误判成源码型组件，然后报一堆「缺 platforms.md/include/example」的假缺件）。
_SKIP_DIRS = {'out', 'assets', 'example'}


# 显式登记的缺口：门禁只放行**登记过的** —— 目的是让"缺件"变成一条看得见的账，
# 而不是靠人记得、或悄悄通过。每条必须写清原因与日期；新增缺口会被直接抓出来。
DECLARED_GAPS = {
    'mp_transfer': {
        'missing': ['include'],
        'why': '公开头就在 src/mp_transfer/*.h —— 本模块的用法是「拷源文件」（README §怎么用、'
               'Manifest 注释），没有做 include/ + lib/ 的库化封装。属**已登记的形态变体**。',
        'date': '2026-10-03',
    },
    'fonts': {
        'noPlatformRow': True,
        'why': '平台可用性写在 platforms.md 的逐平台正文里（V85X 已实测、其余未验证），没有'
               '「平台 × 能力」矩阵表，所以不进 platform_capabilities.json（资产/工具型，'
               '用法是"一条命令体检/投递"）。',
        'date': '2026-10-03',
    },
}


class CatalogError(Exception):
    """目录结构不合法 / 查不到组件时抛（调用方据此报错，不静默）。"""


def _abs(rel):
    return os.path.join(BASE, rel.replace('/', os.sep))


def _has(d, name):
    return os.path.exists(os.path.join(d, name))


def _read(p):
    with io.open(p, encoding='utf-8', errors='replace') as fh:
        return fh.read()


def _summary(readme_path, mod_id=''):
    """一句话用途：优先取 README 的 **H1 标题描述段**。

    实测（2026-10-03）：这些 README 的 H1 就是"这是什么"（`fonts —— 字库模块：…`、
    `icons —— 图标资产库（…）`），而正文第一段往往是"第一条要点/需求描述"（`msg 全是人话…`、
    `需求：切歌时算一次…`），拿它当用途会答非所问。所以：
      H1 有 `——` / `—` 分隔 → 取分隔符后的描述段（去掉路径/模块名前缀）；
      否则 → 用 H1 本身；再兜底正文第一段。
    """
    try:
        text = _read(readme_path)
    except OSError as e:
        return '(读不到 README：%s)' % type(e).__name__
    h1 = ''
    for ln in text.splitlines():
        if ln.strip().startswith('# '):
            h1 = ln.strip().lstrip('#').strip()
            break
    if h1:
        for sep in ('——', '—', '–'):
            if sep in h1:
                tail = h1.partition(sep)[2].strip()
                if tail:
                    return re.sub(r'[*`]', '', tail)[:120]
                break
        return re.sub(r'[*`]', '', h1)[:120]
    # 兜底：第一个正文段落行
    in_fence = False
    for ln in text.splitlines():
        t = ln.strip()
        if t.startswith('```'):
            in_fence = not in_fence
            continue
        if in_fence or not t:
            continue
        if t.startswith(('#', '>', '|', '---', '-', '*', '+', '·')):
            continue
        if re.match(r'^\d+[.、)]\s', t):
            continue
        return re.sub(r'[*`]', '', t)[:120]
    return ''


def _form(d):
    if os.path.isdir(os.path.join(d, 'src')):
        return FORM_SOURCE
    if os.path.isdir(os.path.join(d, 'lib')):
        return FORM_BINARY
    return FORM_ASSET


def _subdirs(d):
    try:
        return sorted(n for n in os.listdir(d) if os.path.isdir(os.path.join(d, n)))
    except OSError:
        return []


def _is_readme_dir(d):
    return _has(d, 'README.md')


def _is_module(d):
    """模块判据：有 README，且不止有 README（有 platforms.md 或实件目录）。"""
    if not _is_readme_dir(d):
        return False
    return (_has(d, 'platforms.md')
            or any(_has(d, x) for x in ('include', 'src', 'lib', 'scripts', 'example')))


def _deps(d):
    """从组件自己的 Manifest.xml 抽依赖包（机器可读，不抄进别处）。

    ⚠️ **先剥注释**：这些 Manifest 的注释里常放「将来注册进包仓库时这样写」的示例
    （如 blur 注释里的 `<package id="blur">`），不剥就会把示例当成真依赖。
    """
    mf = os.path.join(d, 'Manifest.xml')
    if not os.path.isfile(mf):
        return []
    body = re.sub(r'<!--.*?-->', '', _read(mf), flags=re.S)
    out = []
    for name in re.findall(r'<package\s+id="([^"]+)"', body):
        if name not in out:
            out.append(name)
    kind = os.path.basename(d) if os.path.basename(d) != '' else d
    return [n for n in out if n != kind]        # 自引用（本组件自己）不算依赖


def _platforms_of(comp_id):
    """平台可用性真源 = platform_capabilities.json（不在本模块重写）。"""
    try:
        import json
        with io.open(_abs('platform_capabilities.json'), encoding='utf-8') as fh:
            caps = (json.loads(fh.read()).get('components') or {})
    except (OSError, ValueError) as e:
        raise CatalogError('读不到 platform_capabilities.json（%s）' % type(e).__name__)
    key = comp_id if comp_id in caps else os.path.basename(comp_id)
    if key not in caps:
        return []
    out = []
    for r in caps[key].get('rows') or []:
        for p in (r.get('canonical') or r.get('platforms') or []):
            if p and p not in out:
                out.append(p)
    return sorted(out)


def _walk_modules(rel_dir, depth=0):
    """递归找模块（返回 (modules, groups)）。含模块子目录的目录算「分组」，不是模块。"""
    d = _abs(rel_dir)
    if not os.path.isdir(d):
        return [], []
    mods, groups = [], []
    sub = [s for s in _subdirs(d) if s not in _SKIP_DIRS]
    child_mods, child_groups = [], []
    for s in sub:
        m, g = _walk_modules('%s/%s' % (rel_dir, s), depth + 1)
        child_mods += m
        child_groups += g
    if child_mods:
        if rel_dir != ROOT:                       # 根目录自己不算分组
            groups.append({'id': os.path.basename(rel_dir), 'dir': rel_dir,
                           'children': [m['id'] for m in child_mods]})
            if _is_readme_dir(d):                 # 分组自己也带索引 README
                groups[-1]['readme'] = '%s/README.md' % rel_dir
        return child_mods, groups + child_groups
    if _is_module(d):
        mid = rel_dir[len(ROOT) + 1:]
        pieces = {x: _has(d, x) for x in
                  ('README.md', 'platforms.md', 'Manifest.xml', 'include', 'src',
                   'lib', 'example', 'scripts')}
        pieces['lib/BUILD_INFO.md'] = _has(os.path.join(d, 'lib'), 'BUILD_INFO.md')
        form = _form(d)
        lib_plats = _subdirs(os.path.join(d, 'lib')) if pieces['lib'] else []
        examples = ['%s/example' % rel_dir] if pieces['example'] else []
        for s in sub:                             # 兼容其它示例目录名
            if s != 'example' and _has(os.path.join(d, s), 'Manifest.xml'):
                examples.append('%s/%s' % (rel_dir, s))
        mods.append({
            'id': mid, 'dir': rel_dir, 'form': form, 'formName': FORM_NAMES[form],
            'summary': _summary(os.path.join(d, 'README.md'), mid),
            'pieces': pieces,
            'missing': [x for x in REQUIRED[form] if not pieces.get(x)],
            'deps': _deps(d),
            'libPlatforms': lib_plats,
            'examples': examples,
            'verify': [p for p in ('scripts/verify_lib_symbols.py',) if _has(d, p)],
            'docRef': '%s/README.md' % rel_dir,
            'platformDoc': ('%s/platforms.md' % rel_dir) if pieces['platforms.md'] else '',
        })
    elif _is_readme_dir(d):                       # 只有 README：索引/资产说明页，不是模块
        groups.append({'id': os.path.basename(rel_dir), 'dir': rel_dir,
                       'readme': '%s/README.md' % rel_dir, 'children': []})
    return mods, groups


_cache = {}


def scan():
    """{modules, groups, indexPages}（带缓存）。"""
    if 'scan' not in _cache:
        mods, groups = _walk_modules(ROOT)
        ids = [m['id'] for m in mods]
        if len(ids) != len(set(ids)):
            raise CatalogError('组件 id 重复：%s' % ids)
        _cache['scan'] = {'modules': mods, 'groups': groups}
    return _cache['scan']


def modules(form=None):
    """全部组件（可按形态过滤），带平台可用性（来自 platform_capabilities）。"""
    out = []
    for m in scan()['modules']:
        if form and m['form'] != form:
            continue
        m = dict(m)
        m['platforms'] = _platforms_of(m['id'])
        out.append(m)
    return out


def groups():
    """分组（如 ui_v1）与索引页（如 ui_v1/examples）。"""
    return list(scan()['groups'])


def get(comp_id):
    """按 id（如 `ble`、`ui_v1/Chart`）取组件；不存在 → 抛，并给相近 id。"""
    for m in modules():
        if m['id'] == comp_id:
            return m
    near = [m['id'] for m in modules()
            if comp_id and comp_id.split('/')[-1].lower() in m['id'].lower()]
    raise CatalogError('没有这个组件：%r%s'
                       % (comp_id, ('；相近：' + ', '.join(near[:4])) if near else ''))


def by_platform(platform):
    """某平台上**可用**的可复用组件（平台名走 platform_capabilities 的规范键）。"""
    key = (platform or '').strip().upper()
    return [m for m in modules() if key in (m.get('platforms') or [])]


def for_query(text):
    """按关键词找组件 → [组件]（看 id / 用途 / 依赖 / 示例路径）。"""
    q = re.sub(r'\s+', '', str(text or ''))
    if not q:
        return []
    hits = []
    for m in modules():
        blob = ''.join([m['id'], m['summary'], ''.join(m['deps']), ''.join(m['examples'])])
        n = _overlap(blob, q)
        if n:
            hits.append((n, m))
    hits.sort(key=lambda t: -t[0])
    return [m for _n, m in hits[:4]]


def _overlap(a, b):
    sa = re.sub(r'[\s，。；：/（）()、\-→]', '', str(a or ''))
    sb = re.sub(r'[\s，。；：/（）()、\-→]', '', str(b or ''))
    if len(sa) < 3 or len(sb) < 3:
        return 1 if (sa and (sa in sb or sb in sa)) else 0
    ga = {sa[i:i + 3] for i in range(len(sa) - 2)}
    gb = {sb[i:i + 3] for i in range(len(sb) - 2)}
    return len(ga & gb)


def validate():
    """核对「四件套缺一不收」→ [问题]（空 = 通过）。

    按形态判要求（components/README.md §1）；二进制型另外要求每个平台库目录非空 +
    `lib/BUILD_INFO.md`（构建凭据：工具链/依赖/符号数/sha256）。
    """
    errs = []
    for m in modules():
        gap = DECLARED_GAPS.get(m['id'], {})
        for x in m['missing']:
            if x in (gap.get('missing') or []):
                continue                          # 已登记 → 放行（见 declared_gaps()）
            errs.append('%s（%s）缺 %s' % (m['id'], m['formName'], x))
        if not m['summary']:
            errs.append('%s：README 里找不到一句话用途' % m['id'])
        if m['form'] == FORM_BINARY:
            for pl in m['libPlatforms']:
                d = os.path.join(_abs(m['dir']), 'lib', pl)
                if not any(f.endswith(('.a', '.so')) for f in os.listdir(d)):
                    errs.append('%s：lib/%s/ 里没有库文件' % (m['id'], pl))
        if not m['platforms'] and not gap.get('noPlatformRow'):
            errs.append('%s：platform_capabilities.json 里没有它的可用性行（平台无法查）' % m['id'])
    return errs


def declared_gaps():
    """已登记的缺口 → [{'id','missing'/'noPlatformRow','why','date'}]（进派生页，看得见）。"""
    out = []
    by_id = {m['id']: m for m in modules()}
    for cid, g in DECLARED_GAPS.items():
        if cid not in by_id:
            raise CatalogError('DECLARED_GAPS 里的 %r 不是现有组件（登记过期了）' % cid)
        out.append({'id': cid, **g})
    return out


if __name__ == '__main__':
    try:
        ms, gs = modules(), groups()
    except CatalogError as e:
        print('[FAIL] %s' % e)
        raise SystemExit(1)
    print('可复用组件 %d 个 / 分组与索引页 %d 个' % (len(ms), len(gs)))
    print('按形态：%s' % '，'.join('%s %d' % (FORM_NAMES[f], len(modules(f)))
                                for f in (FORM_SOURCE, FORM_BINARY, FORM_ASSET)))
    for g in gs:
        print('  分组 %-16s 成员：%s' % (g['id'], ', '.join(g['children']) or '（索引页）'))
    print()
    errs = validate()
    if errs:
        print('[FAIL] 四件套核对未过：')
        for e in errs[:12]:
            print('   -', e)
        raise SystemExit(1)
    print('[PASS] 四件套齐备（按形态核对）')
    print('  查「有没有现成的日历控件」→ %s' % [m['id'] for m in for_query('日历控件')])
    print('  V85X 上可用组件 → %s' % [m['id'] for m in by_platform('V85X')][:6])
