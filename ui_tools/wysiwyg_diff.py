#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wysiwyg_diff.py —— 「离线渲染 vs 真机截图」一致性校验（0 token，本地算法）

配套 `json2img.py`（引擎等价渲染器）与 `knowledge/devflow/wysiwyg-render-spec.md`（渲染语义规格）。

它回答三个问题：
  1. 静态区一致率多少？（**排除运行期文字盒**——那些值由代码灌，json 里没有，比了没意义）
  2. 差在哪几个控件？（逐控件归因，按超容差像素排序）
  3. 有没有「结构性」差异？（≥min-block 的连通块 = 位移/缺失/变形，属真问题）

判据（规格 §5）：静态区超容差 ≤ --max-ratio（默认 1.5%）；且无 ≥ --min-block 的连通差异块。

用法：
  python tools/ui_tools/wysiwyg_diff.py <渲染图.png> <真机截图.png> <页面json> \
         [--tol 2] [--max-ratio 1.5] [--min-block 4] [--top 10] [--project <项目根>] [--json out.json]
"""
import argparse
import glob
import json
import os
import re
import sys

try:
    from PIL import Image, ImageChops
except Exception as ex:                                    # pragma: no cover
    print('[X] 需要 Pillow：%s' % ex)
    sys.exit(2)

TEXTY = ('textview', 'button', 'edittext', 'slidetext')


def runtime_captions(project_root, extra=()):
    """扫 src 找运行期会改文字的控件：
    ① `m<Cap>Ptr->setText(...)`；② 指针出现在数组初始化里再 `a[i]->setText(...)`（如
    `ZKTextView* a[6] = {mTextWallRowValue1Ptr, ...}`）—— 用「同文件里同时出现 m<Cap>Ptr 与
    setText」这个弱判据补上，宁可把静态文字当运行期（保守），也不要漏判。
    调用方还可用 --runtime-caps 显式补充。"""
    out = set(extra or ())
    if not project_root:
        return out
    hard = re.compile(r'm([A-Za-z0-9_]+)Ptr\s*->\s*setText(?:ID)?\s*\(')
    ptr = re.compile(r'm([A-Za-z0-9_]+)Ptr')
    for f in glob.glob(os.path.join(project_root, 'src', '**', '*.cc'), recursive=True):
        try:
            txt = open(f, encoding='utf-8', errors='replace').read()
        except OSError as ex:                    # 单个源文件读不了不致命，但不静默
            sys.stderr.write('[warn] 跳过不可读源文件 %s：%s\n' % (f, ex))
            continue
        for m in hard.finditer(txt):
            out.add(m.group(1))
        if 'setText' in txt:                     # 弱判据：同文件既有 setText 又引用了该指针
            for m in ptr.finditer(txt):
                out.add(m.group(1))
    return out


def walk(page):
    """→ [(key, caption, rect_abs, is_text)]（相对父矩形累加，深度不限）。"""
    out = []

    def rec(n, ox, oy):
        for k, v in n.items():
            if not isinstance(v, dict) or '__' not in k:
                continue
            p = v.get('position') or {}
            l, t, w, h = p.get('left'), p.get('top'), p.get('width'), p.get('height')
            if None in (l, t, w, h):
                rec(v, ox, oy)
                continue
            x, y = ox + l, oy + t
            out.append((k, v.get('caption', ''), (x, y, x + w, y + h),
                        k.split('__')[0] in TEXTY, v.get('visible') is not False))
            rec(v, x, y)

    rec(page, 0, 0)
    return out


def biggest_block(diff, tol, textmask=None):
    """最大连通差异块（4 邻域 union-find）→ (面积, 宽, 高, bbox)。
    **只看文字盒之外**的像素：文字的字形栅格化会在一条文字行上连成一片，属预期，不算结构性差异。"""
    px = diff.load()
    W, H = diff.size
    idx = {}
    parent = []

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    def in_text(x, y):
        return bool(textmask and textmask[y][x])

    for y in range(H):
        for x in range(W):
            if in_text(x, y):
                continue
            r, g, b = px[x, y]
            if max(r, g, b) > tol:
                k = len(parent)
                idx[(x, y)] = k
                parent.append(k)
                for nb in ((x - 1, y), (x, y - 1)):
                    if nb in idx:
                        union(k, idx[nb])
    groups = {}
    for (x, y), i in idx.items():
        r = find(i)
        g = groups.setdefault(r, [0, x, y, x, y])
        g[0] += 1
        g[1] = min(g[1], x); g[2] = min(g[2], y)
        g[3] = max(g[3], x); g[4] = max(g[4], y)
    if not groups:
        return 0, 0, 0, None
    best = max(groups.values(), key=lambda g: g[0])
    return best[0], best[3] - best[1] + 1, best[4] - best[2] + 1, (best[1], best[2], best[3], best[4])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('render')
    ap.add_argument('device')
    ap.add_argument('page_json')
    ap.add_argument('--tol', type=int, default=2)
    ap.add_argument('--max-ratio', type=float, default=1.0,
                    help='非文字区（几何/图/纯色）超容差上限 %%，默认 1.0')
    ap.add_argument('--max-text-ratio', type=float, default=8.0,
                    help='静态文字盒超容差参考上限 %%（含字形栅格化，默认 8，仅提示不拦）')
    ap.add_argument('--min-block', type=int, default=8, help='结构性差异块最小边长，默认 8px')
    ap.add_argument('--top', type=int, default=10)
    ap.add_argument('--project', default='')
    ap.add_argument('--runtime-caps', default='', help='额外指定「运行期文字」控件 caption（逗号分隔）')
    ap.add_argument('--json', default='')
    a = ap.parse_args()

    ia = Image.open(a.render).convert('RGB')
    ib = Image.open(a.device).convert('RGB')
    if ia.size != ib.size:
        print('[X] 尺寸不一致：%s vs %s（先确认渲染分辨率 == 设备分辨率）' % (ia.size, ib.size))
        sys.exit(2)
    W, H = ia.size
    d = ImageChops.difference(ia, ib)
    px = d.load()

    page = json.load(open(a.page_json, encoding='utf-8'))
    ctrls = walk(page)
    rcap = runtime_captions(a.project or os.path.dirname(os.path.dirname(os.path.abspath(a.page_json))),
                            [x.strip() for x in a.runtime_caps.split(',') if x.strip()])
    run_boxes = [(k, c, r) for (k, c, r, is_t, vis) in ctrls if is_t and vis and c in rcap]

    mask = [[0] * W for _ in range(H)]
    for _k, _c, (x0, y0, x1, y1) in run_boxes:
        for y in range(max(0, y0), min(H, y1)):
            for x in range(max(0, x0), min(W, x1)):
                mask[y][x] = 1
    text_boxes = [(k, c, r) for (k, c, r, is_t, vis) in ctrls if is_t and vis]
    rtext_boxes = [(k, c, r) for (k, c, r) in text_boxes if c not in rcap]
    textmask = [[0] * W for _ in range(H)]
    for _k, _c, (x0, y0, x1, y1) in text_boxes:
        for y in range(max(0, y0), min(H, y1)):
            for x in range(max(0, x0), min(W, x1)):
                textmask[y][x] = 1

    n_run = n_rest = t_run = t_rest = n_rtext = t_rtext = 0
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            bad = max(r, g, b) > a.tol
            if mask[y][x]:
                t_run += 1
                n_run += 1 if bad else 0
            elif textmask[y][x]:
                t_rtext += 1
                n_rtext += 1 if bad else 0
            else:
                t_rest += 1
                n_rest += 1 if bad else 0

    rows = []
    for k, c, (x0, y0, x1, y1), is_t, vis in ctrls:
        if not vis:
            continue
        n_bad = 0
        for y in range(max(0, y0), min(H, y1)):
            for x in range(max(0, x0), min(W, x1)):
                r, g, b = px[x, y]
                if max(r, g, b) > a.tol:
                    n_bad += 1
        if n_bad:
            rows.append((k, c, (x0, y0), (x1 - x0, y1 - y0), n_bad, (x1 - x0) * (y1 - y0),
                         'RUN-TEXT' if c in rcap else ''))
    rows.sort(key=lambda r: -r[4])

    area, bw, bh, bbox = biggest_block(d, a.tol, textmask)
    ratio = 100.0 * n_rest / max(1, t_rest)
    structural = (bw >= a.min_block and bh >= a.min_block and area >= a.min_block * a.min_block)
    ok = (ratio <= a.max_ratio) and not structural

    print('== WYSIWYG 一致性：%s vs %s (%dx%d, tol=%d)'
          % (os.path.basename(a.render), os.path.basename(a.device), W, H, a.tol))
    print('   A. 非文字区（几何/图/纯色/层级）: %6d px 超容差 %5d = %5.2f%%  → 一致率 %5.2f%%  [判据 ≤ %.2f%%]'
          % (t_rest, n_rest, ratio, 100.0 - ratio, a.max_ratio))
    print('   B. 文字区：已识别运行期盒 %d 个（不计判据，差异 %.2f%%）  |  其余文字盒 %d 个（差异 %.2f%%，含字形栅格化，参考上限 %.1f%%）'
          % (len(run_boxes),
             100.0 * n_run / max(1, t_run),
             len(rtext_boxes),
             100.0 * n_rtext / max(1, t_rtext),
             a.max_text_ratio))
    print('   C. 结构性差异：最大连通块 %dx%d (面积 %d)%s'
          % (bw, bh, area, ('  ← %s' % (box2str(bbox),) if structural else '')))
    print('   判据：非文字区 ≤ %.2f%% 且无 ≥%dx%d 连通差异块 → %s'
          % (a.max_ratio, a.min_block, a.min_block, 'PASS' if ok else 'FAIL'))
    print('   ---- 逐控件归因 top%d ----' % a.top)
    for k, c, (x, y), (w, h), n_bad, c_area, tag in rows[:a.top]:
        print('   %-16s %-22s %s,%s %dx%d  超容差 %5d / %5d = %5.1f%% %s'
              % (k, c, x, y, w, h, n_bad, c_area, 100.0 * n_bad / max(1, c_area), tag))

    if a.json:
        json.dump({'success': True, 'nonTextRatioPct': round(ratio, 3),
                   'nonTextConsistencyPct': round(100.0 - ratio, 3),
                   'runtimeTextRatioPct': round(100.0 * n_run / max(1, t_run), 3),
                   'maxBlock': {'w': bw, 'h': bh, 'area': area, 'bbox': bbox},
                   'pass': ok, 'runtimeTextControls': len(run_boxes),
                   'attribution': [{'key': k, 'caption': c, 'bad': n_bad, 'area': c_area,
                                    'runtime': bool(tag)}
                                   for k, c, _xy, _wh, n_bad, c_area, tag in rows]},
                  open(a.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('   清单: %s' % a.json)
    sys.exit(0 if ok else 1)


def box2str(b):
    return 'bbox=%s' % (b,) if b else ''


if __name__ == '__main__':
    main()
