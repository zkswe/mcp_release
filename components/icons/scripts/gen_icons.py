# -*- coding: utf-8 -*-
"""gen_icons.py —— 图标生成器（**唯一入口**）

把矢量源（vendor 收录的 Tabler SVG + 少量自绘图标）按需渲染成任意分辨率的**单色烘焙 PNG**
（RGB 恒等于 --color，alpha = 覆盖率；8× 超采样 + BOX 面积平均降采样 + α 整形 = 边缘干净）。

图标源是**按需加载**的（2026-09-17 起）：vendor 的 SVG 不再是 5777 个散件，而是打成
`vendor/tabler-3.46.0.pack.tgz`（见 `scripts/make_pack.py`）。`--vendor-name` / `--svg` /
`--set` / `--sheet` 的**用法与输出完全不变**——读取层自己决定从哪儿取（散件 / 缓存 /
归档按需解 / 可选远端），细节见本文件「图标来源解析」一节与模块 `README.md` §2。

用法：
    # 0) 看有哪些图标（含 vendor 与自绘）
    python scripts/gen_icons.py --list
    python scripts/gen_icons.py --list-tabler           # Tabler 原生名全量（index.json）
    python scripts/gen_icons.py --pack-info             # 图标来源/cache/pack 状态
    python scripts/gen_icons.py --list-tabler wifi      # 子串过滤（不依赖散件）

    # 1) 按语义名出图（**最常用**：不用记 tabler 文件名）
    python scripts/gen_icons.py --vendor-name wifi --size 22 --color 255,255,255 --out out/22
    python scripts/gen_icons.py --name weather.clear --size 56 --color 255,175,40 --out out/56

    # 2) 直接渲染任意 SVG 文件（vendor 里没收录的也能用）
    python scripts/gen_icons.py --svg vendor/tabler/icons/rocket.svg --size 48 --out out/tmp

    # 3) 批量：分类 / 风格 / vendor / all
    python scripts/gen_icons.py --set weather --size 22 --out out/22
    python scripts/gen_icons.py --set vendor --size 24 --out out/24
    python scripts/gen_icons.py --all --size 56 --out out/56

    # 4) contact sheet（审阅）
    python scripts/gen_icons.py --sheet out/sheet_vendor_22.png --size 22 --set vendor

    # 5) 非正方形（等比居中留白，绝不拉伸）
    python scripts/gen_icons.py --name control.arrow-left --size 22x16 --out out/misc

约定：
    --size N | WxH   产出图**像素尺寸严格 == 请求值**（WxH 时按 min 边等比缩放 + 居中留白）
    --color R,G,B    生成时烘焙（FlyThings 无 tint API，不能运行时染色）
    --state off|on   只出某个状态（两态图标才有）
    --set X          X = 分类(weather/control/system/device/vehicle) / 风格(ios/material/tabler) / vendor / all
    输出命名         ic_<分类>_<名字>[_<风格>][_off|_on].png；同时写 `_manifest.json`

依赖：Python3 + Pillow + numpy（本仓库已有）；**不联网**。
"""

import argparse
import glob
import hashlib
import json
import os
import re
import sys
import tarfile
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import svgmini  # noqa: E402

CATEGORIES = ('weather', 'control', 'system', 'device', 'vehicle')
STYLES = ('tabler', 'ios', 'material')
NAME_RE = re.compile(r'^ic_([a-z0-9]+)_([a-z0-9-]+?)(?:_(ios|material|tabler))?(?:_(off|on))?\.png$')


# --------------------------------------------------------------------------- #
# catalog 访问
# --------------------------------------------------------------------------- #
def load_catalog(path=None):
    p = path or os.path.join(ROOT, 'catalog.json')
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def out_name(cat, name, style=None, state=None):
    parts = ['ic', cat, name]
    if style:
        parts.append(style)
    if state:
        parts.append(state)
    return '_'.join(parts) + '.png'


def all_jobs(cat=None):
    """把 catalog 展开成渲染任务：每条 = (图标, 风格, 状态, variant, 产物名)。"""
    cat = cat or load_catalog()
    jobs = []
    for it in cat['icons']:
        multi = len(it['styles']) > 1
        for style in it['styles']:
            v = it['variants'][style]
            suffix = style if (multi or style == 'material') else None
            states = v['states'] or ['']
            for state in states:
                jobs.append(dict(icon=it['name'], iconShort=it['icon'], category=it['category'],
                                 style=style, state=state, variant=v,
                                 png=v['files'][state],
                                 source=it.get('source', 'selfdrawn')))
    return jobs


def resolve_target(cat, token):
    """--name / --vendor-name 解析：支持 语义名 / tabler 名 / 别名 / 旧工程名 / 产物文件名。"""
    t = token.strip()
    m = NAME_RE.match(t.lower())
    if m:
        t = '%s.%s' % (m.group(1), m.group(2))
        if m.group(3):
            t += '#' + m.group(3)
    if '#' in t:
        t, style = t.split('#', 1)
    else:
        style = None
    t = t.lower().replace('_', '-')
    hits = []
    for it in cat['icons']:
        keys = {it['name'].lower(), it['icon'].lower(), it['name'].lower().replace('.', '-')}
        keys |= {a.lower() for a in it.get('aliases', [])}
        keys |= {a.lower().replace('_', '-') for a in it.get('aliases', [])}
        keys |= {a.lower() for a in it.get('legacyNames', [])}
        if t in keys:
            hits.append(it)
    if not hits:
        for it in cat['icons']:
            if it['name'].split('.')[1].lower() == t:
                hits.append(it)
    if not hits:
        ad = vendor_adhoc(t)
        if ad:
            return ad, style
        raise SystemExit('未找到图标 %r（用 --list / --list-vendor 看全部名字；'
                         'Tabler 原生名也可直接传，如 weather.sun / cloud-rain）' % token)
    if len(hits) > 1:
        # 同名多义（如 wifi 既指 system.wifi，也是 system.wifi-full 的别名）时，
        # **精确名优先**：icon 同名 > 语义全名同名 > 仍分不消才报错（文档里的
        # `--vendor-name wifi` 就靠这条命中 system.wifi）。
        for key in ('icon', 'name'):
            exact = [h for h in hits if str(h.get(key, '')).lower() == t]
            if len(exact) == 1:
                return exact[0], style
        raise SystemExit('%r 匹配到多个：%s' % (token, [h['name'] for h in hits]))
    return hits[0], style


# --------------------------------------------------------------------------- #
# 图标来源解析（按需加载）——2026-09-17 方案 A「单归档 + 按需解，离线优先」
#
# 背景：vendor(tabler) 的 5777 个 SVG 原先作为散件入库（3.95 MB / 5777 文件，git 里噪音
# 极大），而 99% 的用法只用到其中几个 glyph。现在它们打成一份归档
# `vendor/tabler-3.46.0.pack.tgz`（`scripts/make_pack.py` 生成，内容 = icons/*.svg +
# icons-filled/*.svg + map.json；index.json / LICENSE / VERSION.txt 仍在归档外）。
#
# 读取层把**逻辑路径**（catalog.json / map.json 里写的
# 'vendor/tabler/icons/<glyph>.svg'）解析成一个真实文件，优先级：
#   ① 本地缓存目录：默认 out/.icons-cache/（env FLYTHINGS_ICONS_CACHE 覆盖；该目录
#      已进 .gitignore），命中即用；
#   ② pack 归档：tarfile 随机读，**只解出这次真正用到的那几个** SVG，解出的写进 ①；
#   ③ 远端 npm tarball：**默认关闭**，需显式 --fetch-remote（或 env
#      FLYTHINGS_ICONS_FETCH_REMOTE=1）才按 catalog.json 的 sources.vendor.url 拉取、
#      按登记的 sha256 校验后缓存（env FLYTHINGS_ICONS_PACK 可指定别的归档）。
# 自绘线（svg/）与任何磁盘上真实存在的路径，行为与改动前完全一致（散件优先）。
# --------------------------------------------------------------------------- #
VENDOR_DIR = os.path.join(ROOT, 'vendor', 'tabler')
PACK_PREFIX = 'vendor/tabler/'                 # 逻辑前缀 → 归档内相对名
PACK_GLOB = 'tabler-*.pack.tgz'
_VENDOR_INDEX = None
_CACHE_DIR = None
_PACK = None
_REMOTE = {'flag': False}      # --fetch-remote 开关（默认关闭）


def _cache_candidates():
    """缓存目录候选：env 覆盖 → out/.icons-cache → 临时目录（装目录不可写时兜底）。"""
    d = os.environ.get('FLYTHINGS_ICONS_CACHE') or os.path.join(ROOT, 'out', '.icons-cache')
    return [os.path.abspath(d), os.path.join(tempfile.gettempdir(), 'flythings-icons-cache')]


def cache_dir(create=True):
    """本地缓存根（解出来的 SVG 落在这里，路径与归档内一致）。

    目录不可写时不静默降级：所有候选都不可写就把失败原因带进报错。
    """
    global _CACHE_DIR
    if _CACHE_DIR and (os.path.isdir(_CACHE_DIR) or not create):
        return _CACHE_DIR
    cands = _cache_candidates()
    if not create:
        return cands[0]
    errs = []
    for d in cands:
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, '.write-probe')
            with open(probe, 'w') as f:
                f.write('1')
            os.remove(probe)
        except OSError as e:
            errs.append('%s(%s)' % (d, e.strerror or e))
            continue
        _CACHE_DIR = d
        return d
    raise SystemExit('图标缓存目录都不可写（FLYTHINGS_ICONS_CACHE 可指定别的目录）：%s'
                     % '；'.join(errs))


def pack_path():
    """要用的归档：env FLYTHINGS_ICONS_PACK 优先，否则 vendor/ 下最新的 *.pack.tgz。"""
    p = os.environ.get('FLYTHINGS_ICONS_PACK')
    if p:
        return os.path.abspath(p) if os.path.isfile(p) else None
    cands = sorted(glob.glob(os.path.join(ROOT, 'vendor', PACK_GLOB)))
    return cands[-1] if cands else None


def pack_info():
    """→ {'path':..,'members':{归档内名: 字节}}；无归档时 path=None。"""
    global _PACK
    if _PACK is None:
        p = pack_path()
        if not p:
            _PACK = {'path': None, 'members': {}}
        else:
            with tarfile.open(p, 'r:gz') as tar:
                _PACK = {'path': p,
                         'members': {m.name: m.size for m in tar.getmembers() if m.isfile()}}
    return _PACK


def _pack_member(rel):
    rel = str(rel).replace('\\', '/')
    return rel[len(PACK_PREFIX):] if rel.startswith(PACK_PREFIX) else None


def is_loose(rel):
    return os.path.isfile(os.path.join(ROOT, str(rel).replace('\\', '/').replace('/', os.sep)))


def source_available(rel):
    """逻辑路径能不能拿到（磁盘散件 或 缓存 或 归档）——不触发解包写盘。"""
    rel = str(rel).replace('\\', '/')
    if is_loose(rel):
        return True
    m = _pack_member(rel)
    if not m:
        return False
    if os.path.isfile(os.path.join(cache_dir(create=False), m.replace('/', os.sep))):
        return True
    return m in pack_info()['members']


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def _vendor_source_meta():
    """catalog.json 里登记的 vendor 来源（url / sha256），供远端拉取用。"""
    try:
        v = load_catalog()['sources']['vendor']
        return v.get('url'), v.get('sha256')
    except Exception:                                             # noqa: BLE001
        return None, None


def remote_enabled(fetch=False):
    return bool(fetch or _REMOTE['flag']
                or os.environ.get('FLYTHINGS_ICONS_FETCH_REMOTE') not in (None, '', '0'))


def ensure_remote_tarball(force=False):
    """③ 远端：拉 npm tarball 到缓存并校验 sha256（离线优先；命中缓存不重复下载）。"""
    url, sha = _vendor_source_meta()
    if not url:
        raise SystemExit('catalog.json 里没有 sources.vendor.url，无法远端拉取')
    d = os.path.join(cache_dir(), '_remote')
    os.makedirs(d, exist_ok=True)
    name = os.path.basename(url.split('?')[0]) or 'icons.tgz'
    dst = os.path.join(d, name)
    if os.path.isfile(dst) and os.path.getsize(dst) > 0 and not force:
        if not sha or _sha256(dst) == sha:
            return dst
        print('  缓存 tarball 的 sha256 与 catalog 登记不符 → 重新下载')
    print('  拉取 %s' % url)
    try:
        with urllib.request.urlopen(url, timeout=180) as r, open(dst, 'wb') as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
    except Exception as e:                               # noqa: BLE001
        raise SystemExit('远端拉取失败（%s）：%s' % (url, e))
    if sha and _sha256(dst) != sha:
        raise SystemExit('npm tarball sha256 与 catalog 登记不符（%s ≠ %s）' % (_sha256(dst), sha))
    return dst


def _extract_member(archive, member, dst, prefix=''):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + '.part'
    with tarfile.open(archive, 'r:gz') as tar:
        try:
            f = tar.extractfile(prefix + member)
        except KeyError:
            f = None
        if f is None:
            raise SystemExit('归档里没有 %s：%s' % (prefix + member, archive))
        with f, open(tmp, 'wb') as w:
            while True:
                b = f.read(1 << 16)
                if not b:
                    break
                w.write(b)
    os.replace(tmp, dst)
    return dst


def resolve_source(rel, fetch=False):
    """逻辑路径 → 磁盘真实路径（按需从缓存/归档取；远端默认关闭）。"""
    rel = str(rel).replace('\\', '/').strip('/')
    p = os.path.join(ROOT, rel.replace('/', os.sep))
    if os.path.isfile(p):                       # 散件优先（自绘线 / 尚未归档的路径）
        return p
    m = _pack_member(rel)
    cached = os.path.join(cache_dir(create=False), m.replace('/', os.sep)) if m else None
    if cached and os.path.isfile(cached):       # ① 缓存
        return cached
    if m:                                       # ② 归档按需解
        if m in pack_info()['members']:
            return _extract_member(pack_info()['path'], m, cached)
        if remote_enabled(fetch):               # ③ 远端（默认关闭）
            tgz = ensure_remote_tarball()
            return _extract_member(tgz, m, cached, prefix='package/')
    raise SystemExit('拿不到矢量源：%s（磁盘散件/缓存/归档都没有；'
                     '用 --pack-info 看来源，或 --fetch-remote 显式联网拉取）' % rel)


def source_text(rel):
    """读逻辑路径的文本（index.json / map.json 这类清单也走这里）。"""
    with open(resolve_source(rel), encoding='utf-8') as f:
        return f.read()


def source_json(rel):
    return json.loads(source_text(rel))


def list_svgs(rel_dir):
    """列出某逻辑目录下的 .svg（磁盘散件优先；否则从归档/缓存列名，不整包解）。"""
    rel_dir = str(rel_dir).replace('\\', '/').strip('/')
    d = os.path.join(ROOT, rel_dir.replace('/', os.sep))
    if os.path.isdir(d):
        return ['%s/%s' % (rel_dir, f) for f in sorted(os.listdir(d))
                if f.lower().endswith('.svg')]
    m0 = _pack_member(rel_dir + '/')
    if m0 is None:
        return []
    names = set(k for k in pack_info()['members']
                if k.startswith(m0) and k.lower().endswith('.svg'))
    cdir = os.path.join(cache_dir(create=False), m0.replace('/', os.sep))
    if os.path.isdir(cdir):
        names |= {m0 + f for f in os.listdir(cdir) if f.lower().endswith('.svg')}
    return ['%s%s' % (PACK_PREFIX, n) for n in sorted(names)]


def vendor_index():
    global _VENDOR_INDEX
    if _VENDOR_INDEX is None:
        _VENDOR_INDEX = source_json('vendor/tabler/index.json')['icons']
    return _VENDOR_INDEX


# --------------------------------------------------------------------------- #
# Tabler 原生名兜底（不在语义表里也能出图）
# --------------------------------------------------------------------------- #
def vendor_entry(tabler, category='vendor'):
    """按 Tabler 原生名造一个条目（outline→_off；有 filled 则 filled→_on）。"""
    idx = vendor_index()
    if tabler not in idx:
        return None
    states = ['off']
    svg = {'off': 'vendor/tabler/icons/%s.svg' % tabler}
    files = {'off': 'ic_%s_%s_off.png' % (category, tabler)}
    if idx[tabler].get('filled'):
        states.append('on')
        svg['on'] = 'vendor/tabler/icons-filled/%s.svg' % tabler
        files['on'] = 'ic_%s_%s_on.png' % (category, tabler)
    return dict(name='%s.%s' % (category, tabler), category=category, icon=tabler,
                source='vendor:tabler(adhoc)', styles=['tabler'], states=states, tags=[],
                defaultColor=[255, 255, 255], sizes=[16, 20, 22, 24, 32, 44, 56],
                variants={'tabler': dict(kind='vendor', states=states, svg=svg, files=files)})


def vendor_adhoc(token):
    """解析 '<分类>.<Tabler名>' | '<Tabler名>' | '<分类>.<语义名>'；解析不出返回 None。"""
    t = str(token or '').strip().lower().replace('_', '-')
    if not t:
        return None
    head, tail = ('', t)
    if '.' in t:
        head, tail = t.split('.', 1)
    if tail in vendor_index():
        return vendor_entry(tail, head or 'vendor')
    for it in source_json('vendor/tabler/map.json').get('icons', []):
        if it.get('name') == tail and (not head or it.get('category') == head):
            return vendor_entry(it['tabler'], it.get('category') or head or 'vendor')
    return None


def vendor_jobs_all():
    """Tabler 全量（4754）展开成任务。"""
    out = []
    for k in sorted(vendor_index()):
        it = vendor_entry(k, 'vendor')
        v = it['variants']['tabler']
        for st in v['states']:
            out.append(dict(icon=it['name'], iconShort=k, category='vendor', style='tabler',
                            state=st, variant=v, png=v['files'][st], source=it['source']))
    return out


def list_vendor(flt=None):
    """打印 vendor 语义名（来自 catalog 的 vendor 条目），可按分类过滤。"""
    cat = load_catalog()
    flt = (flt or '').strip().lower()
    n = 0
    for it in cat['icons']:
        if not str(it.get('source', '')).startswith('vendor'):
            continue
        if flt and it['category'] != flt:
            continue
        v = it['variants'][list(it['variants'])[0]]
        print('%-30s %-9s %-26s %s' % (it['name'], it['category'], it.get('tabler', '-'),
                                       '/'.join(v['states']) or 'single'))
        n += 1
    print('共 %d 个 vendor 语义名（+ 任意 Tabler 原生名可直接传给 --tabler / --vendor-name）' % n)
    return 0


def parse_color(s):
    s = str(s or '').strip()
    if s.startswith('#'):
        h = s[1:]
        if len(h) == 3:
            h = ''.join(c * 2 for c in h)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    parts = [p for p in re.split(r'[\s,]+', s) if p]
    if len(parts) == 1 and parts[0].isdigit() and len(parts[0]) >= 5:
        v = int(parts[0])
        return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
    if len(parts) < 3:
        raise SystemExit('--color 需要 R,G,B（或 #RRGGBB）')
    return tuple(max(0, min(255, int(float(p)))) for p in parts[:3])


def parse_size(s):
    """'56' → (56, 56)；'22x16' → (22, 16)。"""
    s = str(s).strip().lower()
    m = re.match(r'^(\d+)(?:[x*](\d+))?$', s)
    if not m:
        raise SystemExit('--size 需要 N 或 WxH（如 22 / 22x16）')
    w = int(m.group(1))
    h = int(m.group(2) or m.group(1))
    if not (4 <= w <= 2048 and 4 <= min(w, h)):
        raise SystemExit('--size 建议 4~2048（当前 %s）' % s)
    return w, h


# --------------------------------------------------------------------------- #
# 渲染
# --------------------------------------------------------------------------- #
def _paint(img, color):
    """把只有 alpha 的图染成 color（保持 alpha）。"""
    import numpy as np
    a = np.asarray(img)[..., 3]
    arr = np.zeros(a.shape + (4,), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = color[0], color[1], color[2]
    arr[..., 3] = a
    from PIL import Image
    return Image.fromarray(arr, 'RGBA')


def render_variant(variant, state, size, color, ss=8, canvas=None):
    """按 variant（vendor / compose / selfdrawn）渲染一张图。"""
    from PIL import Image
    kind = variant['kind']
    if kind == 'compose':
        canvas_img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        for part in variant['parts'][state]:
            sub = max(4, int(round(size * part['scale'])))
            img = svgmini.render_file(resolve_source(part['svg']), sub, color, ss=ss)
            dx = int(round(part['dx'] * size))
            dy = int(round(part['dy'] * size))
            canvas_img.alpha_composite(img, ((size - sub) // 2 + dx, (size - sub) // 2 + dy))
        if canvas and (canvas[0], canvas[1]) != (size, size):
            base = Image.new('RGBA', canvas, tuple(color[:3]) + (0,))
            base.alpha_composite(canvas_img, ((canvas[0] - size) // 2, (canvas[1] - size) // 2))
            return base
        return canvas_img
    rel = variant['svg'][state] if state in variant.get('svg', {}) else list(variant['svg'].values())[0]
    return svgmini.render_file(resolve_source(rel), size, color, ss=ss, canvas=canvas)


def render_one(job, size, color, ss=8, canvas=None):
    return render_variant(job['variant'], job['state'], size, color, ss=ss, canvas=canvas)


def write_png(img, out_dir, name):
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, name)
    img.save(p)
    return p


# --------------------------------------------------------------------------- #
# contact sheet（审阅用）
# --------------------------------------------------------------------------- #
def make_sheet(jobs, size, out_path, color=(255, 255, 255), ss=8, cols=None,
               cell=None, label=True):
    from PIL import Image, ImageDraw, ImageFont
    n = len(jobs)
    if not n:
        raise SystemExit('没有可出图的图标（--set/--name 过滤后为空）')
    cols = cols or max(6, min(16, int((n * 1.6) ** 0.5) + 4))
    cell = cell or (size + 26)
    lab_h = 22 if label else 0
    rows = (n + cols - 1) // cols
    pad = 10
    W = pad * 2 + cols * cell
    H = pad * 2 + rows * (cell + lab_h)
    sheet = Image.new('RGBA', (W, H), (26, 28, 34, 255))
    d = ImageDraw.Draw(sheet)
    try:
        f = ImageFont.load_default(size=max(11, min(14, cell // 5)))
    except Exception:                                            # noqa: BLE001
        f = ImageFont.load_default()
    for i, j in enumerate(jobs):
        r, c = divmod(i, cols)
        x = pad + c * cell
        y = pad + r * (cell + lab_h)
        img = render_one(j, size, color, ss=ss)
        sheet.alpha_composite(img, (x + (cell - size) // 2, y + (cell - size) // 2))
        if label:
            txt = j['png'][:-4]
            cat = j['category']
            if txt.startswith('ic_%s_' % cat):
                txt = txt[3 + len(cat) + 1:]
            tw = d.textlength(txt, font=f)
            while tw > cell - 6 and len(txt) > 8:
                txt = txt[1:]
                tw = d.textlength(txt, font=f)
            d.text((x + max(0, (cell - tw) / 2), y + cell + 4), txt, font=f, fill=(150, 158, 172))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    sheet.convert('RGB').save(out_path)
    return out_path


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def pack_status():
    """图标来源一览（人读 + --pack-info）。"""
    pk = pack_info()
    cache = cache_dir(create=False)
    n_cache = sum(len(fs) for _, _, fs in os.walk(cache)) if os.path.isdir(cache) else 0
    loose = os.path.isdir(os.path.join(VENDOR_DIR, 'icons'))
    return dict(pack=pk['path'], packEntries=len(pk['members']),
                packBytes=os.path.getsize(pk['path']) if pk['path'] else 0,
                packSha256=_sha256(pk['path']) if pk['path'] else '',
                cache=cache, cacheFiles=n_cache, looseSvgDir=loose,
                remoteEnabled=remote_enabled())


def print_pack_status():
    s = pack_status()
    print('图标来源（按需加载；① 缓存 → ② 归档 → ③ 远端）')
    print('  ① 缓存目录  %s（%d 个文件；FLYTHINGS_ICONS_CACHE 可覆盖，已 gitignore）'
          % (s['cache'], s['cacheFiles']))
    if s['pack']:
        print('  ② 归档      %s' % os.path.relpath(s['pack'], ROOT).replace(os.sep, '/'))
        print('              条目 %d，%d 字节（%.2f MB），sha256 %s'
              % (s['packEntries'], s['packBytes'], s['packBytes'] / 1048576.0, s['packSha256']))
    else:
        print('  ② 归档      无（vendor/*.pack.tgz 不存在；可跑 scripts/make_pack.py 生成）')
    print('  ③ 远端       %s（catalog.json 的 npm URL；--fetch-remote 或 '
          'FLYTHINGS_ICONS_FETCH_REMOTE=1 开启）' % ('开启' if s['remoteEnabled'] else '关闭'))
    print('  磁盘散件     %s'
          % ('存在 vendor/tabler/icons/（散件优先，会盖过归档）' if s['looseSvgDir'] else '无（已按方案 A 收进归档）'))


def list_tabler(flt=None):
    """Tabler 原生名全量（数据源 = index.json，不依赖散件）。"""
    idx = vendor_index()
    flt = (flt or '').strip().lower()
    n = 0
    for k in sorted(idx):
        if flt and flt not in k:
            continue
        print('%-40s %-14s %s' % (k, idx[k].get('category', ''),
                                  'filled' if idx[k].get('filled') else ''))
        n += 1
    print('共 %d 个 Tabler 原生名（index.json；过滤 %r）；直接传即可：'
          '--vendor-name <名> / --tabler <名> / --svg vendor/tabler/icons/<名>.svg'
          % (n, flt))
    return 0


def build_parser():
    p = argparse.ArgumentParser(description='FlyThings 图标资产库生成器')
    p.add_argument('--list', action='store_true', help='列出全部图标（名字/分类/风格/状态）')
    p.add_argument('--list-tabler', dest='list_tabler', nargs='?', const='', default=None,
                   help='列出 Tabler 原生名（全量 4754，来自 vendor/tabler/index.json；'
                        '可跟子串过滤，如 --list-tabler wifi）')
    p.add_argument('--pack-info', dest='pack_info_flag', action='store_true',
                   help='打印图标来源状态（磁盘散件 / 归档 / 缓存 / 远端）')
    p.add_argument('--fetch-remote', dest='fetch_remote', action='store_true',
                   help='允许联网：按 catalog.json 的 npm URL 拉取并缓存（默认关闭）')
    p.add_argument('--name', help='按语义名出图，如 weather.clear / wifi / wx_clear（旧名也能查）')
    p.add_argument('--vendor-name', dest='vendor_name',
                   help='按 vendor 语义名或 tabler 名出图（等价 --name，语义更明确）')
    p.add_argument('--tabler', help='按 Tabler 原生名出图，如 cloud-rain / antenna-bars-3')
    p.add_argument('--svg-dir', dest='svg_dir', help='批量渲染目录下所有 .svg（各自一张，归入 vendor 分类）')
    p.add_argument('--list-vendor', dest='list_vendor', nargs='?', const='', default=None,
                   help='列出 vendor 语义名（可跟分类，如 --list-vendor weather）')
    p.add_argument('--vendor-set', dest='vendor_set', nargs='?', const='common', default=None,
                   help='批量 vendor：common（语义表 152 条）/ all（Tabler 全量 4754）')
    p.add_argument('--svg', help='直接渲染任意 SVG 文件（相对组件根目录或绝对路径）')
    p.add_argument('--out-name', help='配合 --svg 指定产物文件名（默认 ic_svg_<文件名>.png）')
    p.add_argument('--set', dest='setname',
                   help='批量：分类(weather/control/system/device/vehicle) / 风格(ios/material/tabler) / vendor / all')
    p.add_argument('--all', action='store_true', help='全部图标')
    p.add_argument('--size', help='N 或 WxH（如 22 / 22x16）；产出像素尺寸严格等于它')
    p.add_argument('--color', default='255,255,255', help='R,G,B（默认 255,255,255）')
    p.add_argument('--out', help='输出目录')
    p.add_argument('--state', choices=['off', 'on'], help='只出某个状态（两态图标）')
    p.add_argument('--style', help='只出某个风格（tabler/ios/material）')
    p.add_argument('--sheet', help='生成 contact sheet 到该 png（配合 --size/--set/--name）')
    p.add_argument('--cols', type=int, help='sheet 列数')
    p.add_argument('--ss', type=int, default=8, help='超采样倍数（默认 8）')
    p.add_argument('--json', action='store_true', help='以 JSON 输出结果摘要')
    return p


def main(argv):
    args = build_parser().parse_args(argv)
    if args.fetch_remote:
        _REMOTE['flag'] = True                      # ③ 远端拉取：默认关闭，显式开关
        if list(argv) == ['--fetch-remote']:        # 单独用 = 预取并缓存（不进渲染流程）
            tgz = ensure_remote_tarball()
            print('远端 tarball 已缓存：%s（%d 字节）' % (tgz, os.path.getsize(tgz)))
            print_pack_status()
            return 0
    cat = load_catalog()
    jobs_all = all_jobs(cat)

    if args.pack_info_flag:                         # 来源状态
        print_pack_status()
        return 0

    if args.list_tabler is not None:                # Tabler 原生名（index.json）
        return list_tabler(args.list_tabler)

    if args.list:
        for it in cat['icons']:
            st = []
            for style in it['styles']:
                st.append('%s[%s]' % (style, '/'.join(s or 'single'
                                                      for s in (it['variants'][style]['states'] or [''])))
                          if len(it['styles']) > 1 else
                          (('/'.join(it['variants'][style]['states'])) or 'single'))
            print('%-34s %-9s %-10s %s' % (it['name'], it['category'],
                                           it.get('source', ''), ' '.join(st)))
        print('共 %d 个图标 / %d 张产物（vendor %d + 自绘 %d）'
              % (len(cat['icons']), len(jobs_all), cat.get('counts', {}).get('vendor', 0),
                 cat.get('counts', {}).get('selfdrawn', 0)))
        return 0

    if args.list_vendor is not None:                # 只列 vendor 语义名
        return list_vendor(args.list_vendor)

    jobs = []
    adhoc = None
    if args.svg_dir:                                # 批量：目录下所有 .svg（散件或归档）
        rels = list_svgs(args.svg_dir)
        if not rels:
            raise SystemExit('找不到 SVG 目录：%s（磁盘上没有；归档里也没有这个前缀 '
                             '—— --pack-info 看可用来源）' % args.svg_dir)
        for rel in rels:
            stem = re.sub(r'[^a-z0-9-]+', '-', os.path.splitext(os.path.basename(rel))[0].lower())
            jobs.append(dict(icon='vendor.%s' % stem, iconShort=stem, category='vendor',
                             style='tabler', state='',
                             variant=dict(kind='vendor', states=[''], svg={'': rel}),
                             png='ic_vendor_%s_off.png' % stem, source='vendor:tabler(svg-dir)'))
    elif args.tabler:                               # Tabler 原生名
        it = vendor_entry(args.tabler.strip().lower().replace('_', '-'))
        if not it:
            raise SystemExit('Tabler 里没有 %r（用 --list-vendor 看语义名，或查 vendor/tabler/index.json）'
                             % args.tabler)
        v = it['variants']['tabler']
        for state in v['states']:
            if args.state and state != args.state:
                continue
            jobs.append(dict(icon=it['name'], iconShort=it['icon'], category=it['category'],
                             style='tabler', state=state, variant=v, png=v['files'][state],
                             source=it['source']))
    elif args.vendor_set is not None:               # 批量 vendor：common / all
        sel = (args.vendor_set or 'common').lower()
        if sel not in ('common', 'all'):
            raise SystemExit('--vendor-set 只支持 common（语义表）或 all（Tabler 全量）')
        if sel == 'all':
            jobs = vendor_jobs_all()
            if args.state:
                jobs = [j for j in jobs if j['state'] == args.state]
        else:
            jobs = [j for j in jobs_all if str(j.get('source', '')).startswith('vendor')]
    elif args.svg:                                  # 直接渲染任意 SVG（散件或归档内）
        rel = args.svg.replace('\\', '/')
        if os.path.isabs(args.svg):
            rel = os.path.relpath(args.svg, ROOT).replace(os.sep, '/')
        if not source_available(rel):
            raise SystemExit('找不到 SVG：%s（磁盘散件/缓存/归档都没有；--pack-info 看来源）'
                             % args.svg)
        stem = re.sub(r'[^a-z0-9-]+', '-', os.path.splitext(os.path.basename(rel))[0].lower())
        adhoc = dict(variant=dict(kind='vendor', states=[''], svg={'': rel}),
                     state='', style='tabler', category='vendor', icon=stem,
                     png=args.out_name or ('ic_svg_%s.png' % stem), iconShort=stem,
                     source='vendor:tabler(adhoc)')
        jobs.append(adhoc)
    elif args.name or args.vendor_name:
        it, style0 = resolve_target(cat, args.name or args.vendor_name)
        for style in it['styles']:
            if style0 and style != style0:
                continue
            if args.style and style != args.style:
                continue
            v = it['variants'][style]
            for state in (v['states'] or ['']):
                if args.state and v['states'] and state != args.state:
                    continue
                files = v['files']
                if state in files:
                    png = files[state]
                elif args.state:                      # 单态图标强制出 _off/_on 同一张图
                    png = out_name(it['category'], it['icon'], None, args.state)
                else:
                    png = list(files.values())[0]
                jobs.append(dict(icon=it['name'], iconShort=it['icon'], category=it['category'],
                                 style=style, state=state, variant=v, png=png,
                                 source=it.get('source', '')))
    elif args.setname or args.all:
        sel = (args.setname or 'all').lower()
        if sel not in CATEGORIES + STYLES + ('vendor', 'all'):
            raise SystemExit('--set %s 无效：分类 %s / 风格 %s / vendor / all'
                             % (sel, '/'.join(CATEGORIES), '/'.join(STYLES)))
        for j in jobs_all:
            if sel in ('vendor',) and not j['source'].startswith('vendor'):
                continue
            if sel in CATEGORIES and j['category'] != sel:
                continue
            if sel in STYLES and j['style'] != sel:
                continue
            if args.style and j['style'] != args.style:
                continue
            if args.state and j['state'] != args.state:
                continue
            jobs.append(j)
    elif not args.sheet:
        build_parser().print_help()
        return 2

    if args.sheet and not jobs:
        for j in jobs_all:
            if args.style and j['style'] != args.style:
                continue
            if args.state and j['state'] != args.state:
                continue
            jobs.append(j)

    color = parse_color(args.color)
    if not args.size:
        raise SystemExit('缺 --size N（或 WxH）')
    w, h = parse_size(args.size)
    canvas = None if (w == h) else (w, h)
    size = min(w, h)

    written = []
    if args.out:
        for j in jobs:
            img = render_one(j, size, color, ss=args.ss, canvas=canvas)
            p = write_png(img, os.path.abspath(args.out), j['png'])
            written.append(dict(png=j['png'], path=p, size=args.size, w=w, h=h,
                                color=list(color), icon=j['icon'], style=j['style'],
                                state=j['state'], source=j.get('source', '')))
        man_path = os.path.join(os.path.abspath(args.out), '_manifest.json')
        items = {}
        if os.path.isfile(man_path):
            try:
                with open(man_path, encoding='utf-8') as f:
                    for it in json.load(f).get('items', []):
                        items[it['png']] = it
            except Exception:                                     # noqa: BLE001
                items = {}
        for it in written:
            items[it['png']] = it
        man = dict(generated=int(time.time()), generator='components/icons/scripts/gen_icons.py',
                   count=len(items), items=[items[k] for k in sorted(items)])
        with open(man_path, 'w', encoding='utf-8') as f:
            json.dump(man, f, ensure_ascii=False, indent=2)
            f.write('\n')

    sheet_path = None
    if args.sheet:
        sheet_path = make_sheet(jobs, size, os.path.abspath(args.sheet), color,
                                ss=args.ss, cols=args.cols)

    if args.json:
        print(json.dumps(dict(count=len(written), size=args.size, color=list(color),
                              out=args.out, sheet=sheet_path, items=written),
                         ensure_ascii=False, indent=2))
    else:
        for x in written:
            print('  %-48s %s  %s' % (x['png'], args.size if w != h else '%dx%d' % (w, h),
                                      x['path']))
        if sheet_path:
            print('  sheet -> %s（%d 格，%dpx）' % (sheet_path, len(jobs), size))
        print('done: %d 张 %s -> %s' % (len(written), args.size, args.out or '-'))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
