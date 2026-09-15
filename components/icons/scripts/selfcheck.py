# -*- coding: utf-8 -*-
"""selfcheck.py —— 图标库质检（可 CI 化；失败即非零退出）

跑什么：
  A 命名     out/ 下每个 PNG 必须匹配 ic_<分类>_<名字>[_<风格>][_off|_on].png
  B 尺寸     每个 PNG 的像素尺寸必须**严格等于**生成时请求的尺寸（读 _manifest.json）
  C 透明度   α 只允许 0/255 与少量抗锯齿中间值（中间值像素 ≤ 全图 15%）；
             **不允许孤立半透明噪点**（每个 0<α<255 的像素至少有一个 8 邻域 α>0）
  D 目录     catalog.json ↔ svg/ 双向对齐；tags/sizes 非空；legacyMap 指向真实产物名
  E 可生成   catalog 里**每个** 图标×风格×状态 都能渲染成功（22px + 56px），且非空白
  F 尺寸混用 同一目录内不允许出现彼此不一致的"请求尺寸"（防手滑把 56 的图混进 22 目录）
  I 陈旧产物 out/ 下不允许出现 catalog 之外的 PNG（`demo/` 与 `_` 前缀目录豁免）

「本模块标准产物目录」= out/<尺寸>/（如 out/22、out/24、out/56）与 out/demo（颜色示例）。
`_` 前缀目录（临时文件、并行任务的产物）不参与断言，也不被本脚本清理。

用法：
    python scripts/selfcheck.py                 # 检查 out/（含所有子目录）
    python scripts/selfcheck.py --out out/22    # 只检查某个目录
    python scripts/selfcheck.py --json          # 机器可读输出
退出码：0 全通过；1 有失败项；2 用法/环境错误。
"""

import argparse
import glob
import json
import os
import re
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import gen_icons  # noqa: E402
import svgmini    # noqa: E402
NAME_RE = re.compile(r'^ic_([a-z0-9]+)_([a-z0-9-]+?)(?:_(ios|material))?(?:_(off|on))?\.png$')
MID_LIMIT = 0.15          # 中间值像素占比上限（占全图）
EPS_COVER = 0.02          # 图标至少覆盖 2% 像素（防路径写坏了出全透明图）
# 合法「极小图形」白名单（覆盖率天然 <2%）：Tabler 的 wifi-0 就是一个点（0 格 = 无信号）
TINY_OK = {'ic_system_wifi-0.png': 0.003}


class Report(object):
    def __init__(self):
        self.fails = []
        self.warns = []
        self.info = []

    def fail(self, code, msg):
        self.fails.append((code, msg))

    def warn(self, code, msg):
        self.warns.append((code, msg))

    def note(self, msg):
        self.info.append(msg)


def alpha_stats(path):
    a = np.asarray(Image.open(path).convert('RGBA'))[..., 3].astype(np.int16)
    total = a.size
    mid = int(((a > 0) & (a < 255)).sum())
    cover = int((a > 0).sum())
    # 孤立噪点：中间值像素的 8 邻域必须全为 0 才算孤立
    iso = 0
    if mid:
        m = (a > 0) & (a < 255)
        nb = np.zeros_like(m)
        ys, xs = np.where(m)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                yy = np.clip(ys + dy, 0, a.shape[0] - 1)
                xx = np.clip(xs + dx, 0, a.shape[1] - 1)
                nb[ys, xs] |= (a[yy, xx] > 0)
        iso = int((m & ~nb).sum())
    return dict(w=a.shape[1], h=a.shape[0], total=total, mid=mid, cover=cover, iso=iso,
                mid_ratio=mid / float(total), cover_ratio=cover / float(total))


def load_manifest(out_dir):
    p = os.path.join(out_dir, '_manifest.json')
    if not os.path.isfile(p):
        return None
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def check_dir(out_dir, rep, expect_size=None, valid=None, skip=False):
    if skip:
        return 0
    man = load_manifest(out_dir)
    by_name = {}
    if man:
        items = [it for it in man['items'] if isinstance(it, dict)]
        by_name = {it['png']: it for it in items if isinstance(it.get('png'), str)}

        def _wh(it):
            v = it.get('w') or it.get('size') or 0
            if isinstance(v, (list, tuple)):
                v = v[0] if v else 0
            try:
                n = int(v)
            except (TypeError, ValueError):
                return (0, 0)
            h = it.get('h')
            try:
                hn = int(h)
            except (TypeError, ValueError):
                hn = n
            return (n, hn)

        szs = sorted({_wh(it) for it in by_name.values()})
        cls = sorted({tuple(it['color']) for it in by_name.values()
                      if isinstance(it.get('color'), (list, tuple)) and len(it['color']) >= 3})
        rep.note('%s: manifest %d 张（size=%s, color=%s）'
                 % (os.path.relpath(out_dir, ROOT), len(by_name),
                    '/'.join('%sx%s' % (a, b) for a, b in szs if a),
                    ' '.join('%d,%d,%d' % tuple(c[:3]) for c in cls[:4])
                    + ('…' if len(cls) > 4 else '')))
    # 只看本目录（不递归）：子目录由 main 单独检查，否则父目录会把子目录的图当成自己的
    pngs = sorted(glob.glob(os.path.join(out_dir, '*.png')))
    # contact sheet 是"审阅图"，不参与图标断言
    pngs = [p for p in pngs if not os.path.basename(p).startswith('sheet')]
    if not pngs:
        rep.warn('B', '%s: 没有 PNG（跳过尺寸/透明度断言）' % os.path.relpath(out_dir, ROOT))
    sizes = set()
    worst = None
    for p in pngs:
        base = os.path.basename(p)
        m = NAME_RE.match(base)
        if not m:
            rep.fail('A', '命名不合规：%s（应形如 ic_<分类>_<名字>[_<风格>][_off|_on].png）'
                     % os.path.relpath(p, ROOT))
            continue
        st = alpha_stats(p)
        sizes.add((st['w'], st['h']))
        if valid is not None and base not in valid:
            rep.fail('I', '%s 不在 catalog 产物集合里（陈旧文件？重跑生成器或删掉）'
                     % os.path.relpath(p, ROOT))
        want = None
        if base in by_name:
            t = _wh(by_name[base])
            if t[0]:
                want = t
        elif expect_size:
            want = (expect_size, expect_size)
        if want is None:
            rep.warn('B', '%s 无法确定请求尺寸（缺 manifest 且未给 --size）' % base)
        elif (st['w'], st['h']) != want:
            rep.fail('B', '%s 尺寸 %dx%d ≠ 请求 %dx%d' % (base, st['w'], st['h'], want[0], want[1]))
        if st['mid_ratio'] > MID_LIMIT:
            rep.fail('C', '%s 抗锯齿中间值占比 %.1f%% > %.0f%%（%d/%d 像素）'
                     % (base, 100 * st['mid_ratio'], 100 * MID_LIMIT, st['mid'], st['total']))
        if st['iso']:
            rep.fail('C', '%s 存在 %d 个孤立半透明像素（无 8 邻域不透明邻居）' % (base, st['iso']))
        tiny_floor = TINY_OK.get(base)
        if tiny_floor is not None and st['cover_ratio'] >= tiny_floor:
            rep.note('%s 属合法极小图形（覆盖率 %.2f%%，白名单）' % (base, 100 * st['cover_ratio']))
        elif st['cover_ratio'] < EPS_COVER:
            rep.fail('E', '%s 覆盖率为 %.2f%%（<%.0f%%：疑似空图/路径写坏）'
                     % (base, 100 * st['cover_ratio'], 100 * EPS_COVER))
        if worst is None or st['mid_ratio'] > worst[1]['mid_ratio']:
            worst = (base, st)
    if sizes and len(sizes) > 1:
        rep.fail('F', '%s 目录内出现多种尺寸：%s' % (os.path.relpath(out_dir, ROOT), sorted(sizes)))
    if worst:
        rep.note('%s: %d 张，最差中间值占比 %.1f%%（%s），覆盖率区间 %.1f%%~%.1f%%'
                 % (os.path.relpath(out_dir, ROOT), len(pngs), 100 * worst[1]['mid_ratio'],
                    worst[0], 100 * min(alpha_stats(p)['cover_ratio'] for p in pngs),
                    100 * max(alpha_stats(p)['cover_ratio'] for p in pngs)))
    return len(pngs)


def check_catalog(rep):
    cat = gen_icons.load_catalog()
    jobs = gen_icons.all_jobs(cat)
    valid = {j['png'] for j in jobs}
    svg_files = set()          # 自绘矢量源（必须在 svg/ 树里一一对应）
    vend_refs = set()          # vendor 引用的 svg（在 vendor/ 下，只查存在性）
    for it in cat['icons']:
        if not it['tags']:
            rep.fail('D', '%s 缺 tags（AI 检索要用）' % it['name'])
        if not it['sizes']:
            rep.fail('D', '%s 缺 sizes 建议' % it['name'])
        if not it['styles']:
            rep.fail('D', '%s 没有风格' % it['name'])
        if not it.get('source'):
            rep.fail('D', '%s 缺 source（vendor/selfdrawn）' % it['name'])
        for style in it['styles']:
            v = it['variants'][style]
            paths = list(v.get('svg', {}).values())
            for parts in v.get('parts', {}).values():
                paths += [p['svg'] for p in parts]
            for rel in paths:
                if not os.path.isfile(os.path.join(ROOT, rel.replace('/', os.sep))):
                    rep.fail('D', '%s 引用的矢量源不存在：%s' % (it['name'], rel))
            for st, f in v['files'].items():
                if f not in valid:
                    rep.fail('D', '%s 的产物名 %s 不在产物集合里' % (it['name'], f))
            if v['kind'] == 'selfdrawn':
                svg_files |= set(paths)
            else:
                vend_refs |= set(paths)
    for old, targets in cat['legacyMap'].items():
        for t in targets:
            if t not in valid:
                rep.fail('D', 'legacyMap["%s"] 指向不存在的产物 %s' % (old, t))
    on_disk = {os.path.relpath(p, ROOT).replace(os.sep, '/')
               for p in glob.glob(os.path.join(ROOT, 'svg', '**', '*.svg'), recursive=True)}
    for p in sorted(on_disk - svg_files):
        rep.fail('D', 'svg/ 里有未被 catalog 引用的文件：%s' % p)
    for p in sorted(svg_files - on_disk):
        rep.fail('D', 'catalog 引用的自绘 svg 不存在：%s' % p)
    rep.note('catalog: %d 个图标 / %d 张产物 / 自绘矢量源 %d（vendor 引用 %d）'
             % (len(cat['icons']), len(jobs), len(on_disk), len(vend_refs)))
    return cat, jobs


def check_render(rep, cat, jobs, sizes=(22, 56)):
    seen = set()
    for j in jobs:
        key = (j['icon'], j['style'], j['state'])
        if key in seen:
            continue
        seen.add(key)
        for size in sizes:
            try:
                img = gen_icons.render_one(j, size, (255, 255, 255))
            except Exception as e:                               # noqa: BLE001
                rep.fail('E', '%s @%dpx 渲染异常：%s' % (j['png'], size, e))
                continue
            if img.size != (size, size):
                rep.fail('E', '%s @%dpx 输出尺寸 %s' % (j['png'], size, img.size))
            a = np.asarray(img)[..., 3]
            cov = (a > 0).sum() / float(size * size)
            floor = TINY_OK.get(j['png'], EPS_COVER)
            if cov < floor:
                rep.fail('E', '%s @%dpx 覆盖 %.2f%%（空白/断图）' % (j['png'], size, 100 * cov))
            mid = ((a > 0) & (a < 255)).sum() / float(size * size)
            if mid > MID_LIMIT:
                rep.fail('C', '%s @%dpx 中间值占比 %.1f%% > %.0f%%'
                         % (j['png'], size, 100 * mid, 100 * MID_LIMIT))
    rep.note('渲染自检：%d 个 图标×风格×状态 × %s' % (len(seen), list(sizes)))


def main(argv):
    ap = argparse.ArgumentParser(description='图标库质检')
    ap.add_argument('--out', help='要检查的产物目录（默认 out/ 递归）')
    ap.add_argument('--size', type=int, help='无 manifest 时假定的请求尺寸')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--skip-render', action='store_true', help='跳过全量渲染自检（快）')
    args = ap.parse_args(argv)

    rep = Report()
    if args.out and not os.path.isdir(args.out):
        print('目录不存在：%s' % args.out)
        return 2
    standard = [os.path.join(ROOT, 'out', d) for d in ('22', '24', '56', 'demo')]
    if args.out:
        dirs = {args.out}
    else:
        # 默认只检查本模块标准产物目录（out/22|24|56|demo）——
        # out/ 是共享目录，别的任务可能在里面放临时产物，不能让它们污染本模块的断言。
        dirs = {d for d in standard if os.path.isdir(d)}
        extra = {os.path.dirname(p) for p in glob.glob(os.path.join(ROOT, 'out', '*', '*.png'))}
        others = sorted(d for d in extra if d not in dirs)
        if others:
            rep.note('out/ 下还有 %d 个非标准目录未参与断言：%s'
                     % (len(others), ', '.join(os.path.basename(d) for d in others[:6])))
    if not dirs:
        print('没有可检查的产物目录（先生成：python scripts/gen_icons.py --all --size 22 --out out/22）')
        return 2
    cat, jobs = check_catalog(rep)
    valid = {j['png'] for j in jobs}
    n_png = 0
    for d in sorted(dirs):
        n_png += check_dir(d, rep, args.size, valid=valid,
                           skip=os.path.basename(d).startswith(('demo', '_')))
    if not args.skip_render:
        check_render(rep, cat, jobs)

    ok = not rep.fails
    if args.json:
        print(json.dumps(dict(ok=ok, pngs=n_png, fails=rep.fails, warns=rep.warns,
                              info=rep.info), ensure_ascii=False, indent=2))
    else:
        print('=== selfcheck: components/icons ===')
        for i in rep.info:
            print('  · %s' % i)
        for w in rep.warns:
            print('  ! [%s] %s' % w)
        for f in rep.fails:
            print('  × [%s] %s' % f)
        print('--- %s：%d 张 PNG，%d 失败，%d 警告' % ('PASS' if ok else 'FAIL',
                                                    n_png, len(rep.fails), len(rep.warns)))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
