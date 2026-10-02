#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""像素 diff 校验工具（0 token，纯本地算法）

用途：UI 验收/回归对比。输入两张同尺寸截图（或预览渲染图），输出
「差异清单」（区域坐标/面积/最大色差）+ 可选标注图，而不是把图丢给模型。

两种典型用法：
  1) 回归对比（最强）：改布局前截图 vs 改后截图 —— 同渲染器、零噪声，
专治「改 A 碰坏 B」。
  2) 预览 vs 设备截图：只当骨架参考，跨渲染器会有字体磨边噪声，
靠 --tol / --shift / --min-area 压掉。

抑制假报警的三道闸（2026-09-10 定：容差 ±2 起步）：
  --tol N单通道容差（默认 2）：|ΔR|,|ΔG|,|ΔB|,|ΔA| 全部 <= N 视为相同
  --shift N抖动补偿（默认 1）：每像素在 ±N 邻域内找最优匹配，
消除 1px 整体/局部位移这类"看着像差异其实只是抖动"
  --min-area N 连通块面积过滤（默认 4）：干掉抗锯齿孤立点
  --open N形态学开运算核（默认 3，0=关闭）：削掉 1px 细边
  --blur N对比前高斯模糊（默认 0.7）：跨渲染器比时抹掉字体抗锯齿噪声（实数，与布局改动无关）
  --noise-bbox N 小碎块判为噪声的上限（默认 10）：bbox 宽高都 ≤N 的差异块进 noise 列表，
不进主清单、不画框（文字磨边典型 3~6px），要看得加 --show-noise

用法：
    python ui_diff.py a.png b.png                     # 只看结论
    python ui_diff.py a.png b.png --out diff.png      # 出标注图
    python ui_diff.py a.png b.png --json out.json     # 出差异清单
    python ui_diff.py a.png b.png --tol 4 --shift 2 --blur 1.2
    python ui_diff.py a.png b.png --show-noise     # 连小碎块也画框
"""
import json
import os
import sys

try:
    import numpy as np
    from PIL import Image, ImageDraw
except Exception as e:  # pragma: no cover
    print(json.dumps({'success': False, 'error': f'缺依赖 numpy/Pillow: {e}'}, ensure_ascii=False))
    sys.exit(2)


# ---------- 基础 ----------
def _load(path):
    im = Image.open(path).convert('RGBA')
    return np.asarray(im, dtype=np.int16), im.size


def _delta(A, B, shift):
    """A/B: HxWx4 int16。返回每像素最大通道差（含 ±shift 抖动补偿）。"""
    def dmax(bb):
        return np.abs(A - bb).max(axis=2)

    base = dmax(B)
    if shift <= 0:
        return base
    best = base.copy()
    for dy in range(-shift, shift + 1):
        for dx in range(-shift, shift + 1):
            if dx == 0 and dy == 0:
                continue
            Bs = np.roll(np.roll(B, dy, axis=0), dx, axis=1)
            best = np.minimum(best, dmax(Bs))
    # 边界像素滚动会绕回对侧内容，可能假性压掉真差异 → 边界恢复为无补偿值
    best[:shift, :] = base[:shift, :]
    best[-shift:, :] = base[-shift:, :]
    best[:, :shift] = base[:, :shift]
    best[:, -shift:] = base[:, -shift:]
    return best


def _open_mask(mask, k):
    """形态学开运算（先腐蚀后膨胀），numpy 滑窗实现，去 1px 细边。"""
    if not k or k < 3:
        return mask
    r = k // 2
    offs = [(dy, dx) for dy in range(-r, r + 1) for dx in range(-r, r + 1)
            if not (dy == 0 and dx == 0)]

    def _erode(m):
        out = m.copy()
        for dy, dx in offs:
            out &= np.roll(np.roll(m, dy, axis=0), dx, axis=1)
        return out

    def _dilate(m):
        out = m.copy()
        for dy, dx in offs:
            out |= np.roll(np.roll(m, dy, axis=0), dx, axis=1)
        return out

    return _dilate(_erode(mask))


def _label_runs(mask):
    """行 run + 并查集连通块标注（8 邻域）。返回 (label_of_pixel, find)。"""
    h, _w = mask.shape
    parent = {}

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    labels = {}
    prev_runs = []
    idx = 0
    for y in range(h):
        row = mask[y]
        cur_runs = []
        if row.any():
            d = np.diff(np.concatenate(([0], row.view(np.int8), [0])))
            xs = np.flatnonzero(d)
            for s, e in zip(xs[0::2], xs[1::2]):
                idx += 1
                parent[idx] = idx
                cur_runs.append((int(s), int(e - 1), idx))
                for ps, pe, pl in prev_runs:
                    if ps <= e - 1 and s <= pe:
                        union(pl, idx)
            for (s, e, l) in cur_runs:
                for x in range(s, e + 1):
                    labels[(y, x)] = l
        prev_runs = cur_runs
    return labels, find


def _regions(mask, delta, min_area, ox, oy):
    if not mask.any():
        return []
    labels, find = _label_runs(mask)
    stats = {}
    for (y, x), lab in labels.items():
        r = find(lab)
        s = stats.get(r)
        if s is None:
            s = stats[r] = {'area': 0, 'x0': x, 'y0': y, 'x1': x, 'y1': y,
                            'maxd': 0, 'sumd': 0}
        s['area'] += 1
        if x < s['x0']:
            s['x0'] = x
        if y < s['y0']:
            s['y0'] = y
        if x > s['x1']:
            s['x1'] = x
        if y > s['y1']:
            s['y1'] = y
        dv = int(delta[y, x])
        if dv > s['maxd']:
            s['maxd'] = dv
        s['sumd'] += dv

    out = []
    for s in stats.values():
        if s['area'] < int(min_area):
            continue
        out.append({
            'x': s['x0'] + ox, 'y': s['y0'] + oy,
            'w': s['x1'] - s['x0'] + 1, 'h': s['y1'] - s['y0'] + 1,
            'area': int(s['area']),
            'maxDelta': int(s['maxd']),
            'meanDelta': round(s['sumd'] / max(1, s['area']), 2),
        })
    out.sort(key=lambda r: (-r['area'], r['y'], r['x']))
    return out[:80]


def _blur_arr(arr, radius):
    from PIL import ImageFilter
    im = Image.fromarray(arr.astype('uint8'), mode='RGBA').filter(
        ImageFilter.GaussianBlur(float(radius)))
    return np.asarray(im, dtype=np.int16)


def diff_images(a_path, b_path, tol=2, shift=1, min_area=4, open_k=3,
                out_png='', out_json='', box=None, blur=0.7, noise_bbox=10,
                show_noise=False):
    A, sizeA = _load(a_path)
    B, sizeB = _load(b_path)
    size_mismatch = sizeA != sizeB
    if size_mismatch:
        w = min(sizeA[0], sizeB[0])
        h = min(sizeA[1], sizeB[1])
        A = A[:h, :w]
        B = B[:h, :w]

    ox = oy = 0
    if box:
        bx, by, bw, bh = box
        A = A[by:by + bh, bx:bx + bw]
        B = B[by:by + bh, bx:bx + bw]
        ox, oy = bx, by

    if blur and float(blur) > 0:
        A = _blur_arr(A, float(blur))
        B = _blur_arr(B, float(blur))

    delta = _delta(A, B, int(shift))
    mask = _open_mask(delta > int(tol), int(open_k))
    raw = _regions(mask, delta, min_area, ox, oy)
    # 小碎块（文字磨边/抗锯齿）归一为噪声，不干扰主清单
    nb = int(noise_bbox or 0)
    noise, regions = [], []
    for r in raw:
        if nb and r['w'] <= nb and r['h'] <= nb and r['area'] <= nb * nb * 0.6:
            noise.append(r)
        else:
            regions.append(r)

    result = {
        'success': True,
        'identical': len(regions) == 0,
        'a': os.path.basename(a_path), 'b': os.path.basename(b_path),
        'sizeA': f'{sizeA[0]}x{sizeA[1]}', 'sizeB': f'{sizeB[0]}x{sizeB[1]}',
        'sizeMismatch': size_mismatch,
        'params': {'tolerance': tol, 'shiftCompensate': shift, 'minArea': min_area,
                   'openKernel': open_k, 'box': box, 'blur': blur, 'noiseBbox': nb},
        'regionCount': len(regions),
        'diffPixelsInRegions': int(sum(r['area'] for r in regions)),
        'regions': regions,
        'noiseCount': len(noise),
        'noise': noise,
    }

    if out_png:
        ann = Image.open(b_path).convert('RGB').copy()
        d = ImageDraw.Draw(ann)
        if show_noise:
            for r in noise:
                d.rectangle([r['x'], r['y'], r['x'] + r['w'], r['y'] + r['h']],
                            outline=(255, 190, 60))
        for i, r in enumerate(regions):
            x, y, w2, h2 = r['x'], r['y'], max(1, r['w']), max(1, r['h'])
            for t in range(2):
                d.rectangle([x - t, y - t, x + w2 + t, y + h2 + t], outline=(255, 40, 40))
            d.text((x + 2, max(0, y - 12)), '#%d' % (i + 1), fill=(255, 210, 0))
        ann.save(out_png)
        result['annotated'] = out_png

    if out_json:
        with open(out_json, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        result['json'] = out_json

    return result


# ---------- CLI ----------
def main(argv):
    args = argv[1:]
    if len(args) < 2:
        print(__doc__)
        return 1
    a, b = args[0], args[1]
    opt = {'tol': 2, 'shift': 1, 'min_area': 4, 'open': 3, 'out': '', 'json': '', 'box': None,
           'blur': 0.7, 'noise_bbox': 10, 'show_noise': False}
    i = 2
    while i + 1 < len(args) + 1 and i < len(args):
        k = args[i]
        v = args[i + 1] if i + 1 < len(args) else ''
        if k == '--tol':
            opt['tol'] = int(v)
        elif k == '--shift':
            opt['shift'] = int(v)
        elif k == '--min-area':
            opt['min_area'] = int(v)
        elif k == '--open':
            opt['open'] = int(v)
        elif k == '--out':
            opt['out'] = v
        elif k == '--json':
            opt['json'] = v
        elif k == '--box':
            opt['box'] = [int(t) for t in v.split(',')]
        elif k == '--blur':
            opt['blur'] = float(v)
        elif k == '--noise-bbox':
            opt['noise_bbox'] = int(v)
        elif k == '--show-noise':
            opt['show_noise'] = True
            i -= 1
        else:
            print(f'未知参数: {k}')
            return 1
        i += 2

    if not os.path.isfile(a) or not os.path.isfile(b):
        print(json.dumps({'success': False, 'error': '输入图不存在'}, ensure_ascii=False))
        return 1

    r = diff_images(a, b, tol=opt['tol'], shift=opt['shift'], min_area=opt['min_area'],
                    open_k=opt['open'], out_png=opt['out'], out_json=opt['json'],
                    box=opt['box'], blur=opt['blur'], noise_bbox=opt['noise_bbox'],
                    show_noise=opt['show_noise'])
    tail = (f"容差 ±{opt['tol']}，抖动补偿 ±{opt['shift']}px，模糊 {opt['blur']}，"
            f"噪声块 {r.get('noiseCount', 0)} 个已忽略")
    if r['identical']:
        print(f"[PASS] 无差异（{tail}）")
    else:
        print(f"[DIFF] {r['regionCount']} 处差异，共 {r['diffPixelsInRegions']} 像素（{tail}）")
        for i2, g in enumerate(r['regions'][:20], 1):
            print(f"  #{i2:<2} x={g['x']:<5} y={g['y']:<5} {g['w']}x{g['h']:<5} "
                  f"面积={g['area']:<6} 最大色差={g['maxDelta']}")
    if r.get('annotated'):
        print('标注图:', r['annotated'])
    if r.get('json'):
        print('差异清单:', r['json'])
    return 0 if r['identical'] else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main(sys.argv))
