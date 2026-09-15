# -*- coding: utf-8 -*-
"""gen_icons.py —— 图标生成器（**唯一入口**）

把矢量源（vendor 收录的 Tabler SVG + 少量自绘图标）按需渲染成任意分辨率的**单色烘焙 PNG**
（RGB 恒等于 --color，alpha = 覆盖率；8× 超采样 + BOX 面积平均降采样 + α 整形 = 边缘干净）。

用法：
    # 0) 看有哪些图标（含 vendor 与自绘）
    python scripts/gen_icons.py --list

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
import json
import os
import re
import sys
import time

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
        raise SystemExit('%r 匹配到多个：%s' % (token, [h['name'] for h in hits]))
    return hits[0], style


# --------------------------------------------------------------------------- #
# Tabler 原生名兜底（不在语义表里也能出图）
# --------------------------------------------------------------------------- #
VENDOR_DIR = os.path.join(ROOT, 'vendor', 'tabler')
_VENDOR_INDEX = None


def vendor_index():
    global _VENDOR_INDEX
    if _VENDOR_INDEX is None:
        with open(os.path.join(VENDOR_DIR, 'index.json'), encoding='utf-8') as f:
            _VENDOR_INDEX = json.load(f)['icons']
    return _VENDOR_INDEX


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
    with open(os.path.join(VENDOR_DIR, 'map.json'), encoding='utf-8') as f:
        for it in json.load(f).get('icons', []):
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
            img = svgmini.render_file(os.path.join(ROOT, part['svg'].replace('/', os.sep)),
                                      sub, color, ss=ss)
            dx = int(round(part['dx'] * size))
            dy = int(round(part['dy'] * size))
            canvas_img.alpha_composite(img, ((size - sub) // 2 + dx, (size - sub) // 2 + dy))
        if canvas and (canvas[0], canvas[1]) != (size, size):
            base = Image.new('RGBA', canvas, tuple(color[:3]) + (0,))
            base.alpha_composite(canvas_img, ((canvas[0] - size) // 2, (canvas[1] - size) // 2))
            return base
        return canvas_img
    rel = variant['svg'][state] if state in variant.get('svg', {}) else list(variant['svg'].values())[0]
    path = os.path.join(ROOT, rel.replace('/', os.sep))
    if not os.path.isfile(path):
        raise SystemExit('缺少矢量源：%s' % rel)
    return svgmini.render_file(path, size, color, ss=ss, canvas=canvas)


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
def build_parser():
    p = argparse.ArgumentParser(description='FlyThings 图标资产库生成器')
    p.add_argument('--list', action='store_true', help='列出全部图标（名字/分类/风格/状态）')
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
    cat = load_catalog()
    jobs_all = all_jobs(cat)

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
    if args.svg_dir:                                # 批量：目录下所有 .svg
        d = args.svg_dir if os.path.isabs(args.svg_dir) else os.path.join(ROOT, args.svg_dir)
        if not os.path.isdir(d):
            raise SystemExit('找不到目录：%s' % args.svg_dir)
        for fp in sorted(f for f in os.listdir(d) if f.lower().endswith('.svg')):
            rel = os.path.relpath(os.path.join(d, fp), ROOT).replace(os.sep, '/')
            stem = re.sub(r'[^a-z0-9-]+', '-', os.path.splitext(fp)[0].lower())
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
    elif args.svg:                                  # 直接渲染任意 SVG
        rel = args.svg if os.path.isabs(args.svg) else os.path.join(ROOT, args.svg)
        if not os.path.isfile(rel):
            raise SystemExit('找不到 SVG：%s' % args.svg)
        stem = re.sub(r'[^a-z0-9-]+', '-', os.path.splitext(os.path.basename(rel))[0].lower())
        adhoc = dict(variant=dict(kind='vendor', states=[''], svg={'': os.path.relpath(
            rel, ROOT).replace(os.sep, '/')}),
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
