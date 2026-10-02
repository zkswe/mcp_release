# -*- coding: utf-8 -*-
"""corner_audit.py — 切图「缺倒角 / 直角残留」审计（2026-09-20 M5，需求方「切图缺倒角必须从设计标准和拦截上处理好」）

为什么需要它
------------
矩形/卡片/磁贴/药丸类资产**必须有圆角**（半径按工程 `DESIGN.md` 圆角令牌），
但「形状外的透明区」在**深色底**上肉眼几乎看不出来，出图脚本一个小 bug 就能把圆角切平
（真实案例：`tile_photos.png` / `tile_place.png` —— 渐变 squircle 上再 `alpha_composite`
一张铺满底边的图形 → 图形覆盖处的 α 被顶成 255，**底部两角变直角**；
真机主屏上就是两个「方角磁贴」）。

判据（几何可复算，不拍脑袋）
----------------------------
【A】倒角几何（r_est）
对每个角，沿该角所在的**边界行/列**量「边起跑距离 d」= 从角点起第一个 α≥thr 的像素位置。
对半径 r 的圆弧，边界行 y∈[0,1) 上第一个被覆盖的 x 满足 `d = r - sqrt(r - 0.25)`
→ 反解 `r_est = (0.5 + sqrt(d))**2 + 0.25`（d=0 → 0.5px；d=31 → 37px）。

  · **thr（不透明阈值）**：默认 `alpha_opaque`=128；若整图峰值 α < 128
    （**半透明资产**：9-patch 半透卡片 / 半透明面板）→ 改用**相对阈值**
    `thr = ceil(0.5 × 峰值α)`（半个像素覆盖率，与 128 同义，只是换成相对刻度）。
没有这一条时，所有峰值 <128 的资产四角全部 d=-1 → 「不判」→ **半径判据整条失效**。
  · **`*.9.png`（9-patch）**：最外 1px 是 **marker 环**（拉伸区/内容区元数据，不是视觉内容）
    → 判前**剥离最外 1px**，只判本体；否则量到的是 marker 环的透明角，r_est 虚高（实测 19.35
把真缺陷放过去）。marker 环的其他影响由 aa_audit 的 NINEPATCH_MARKER 豁免区负责。

判定（阈值出自 `asset_audit_rules.json` 的 defaults，逐条可追溯到标准 §7.2/§7.7）：

| 指标 | 口径 | 级别 |
|---|---|---|
| `square_corner` | 该角两侧的 d 都 ≤ `corner_d_square`(=1) → 直角残留（α 铺到角点） | DEFECT |
| `radius_short` | `r_est_min < radius_ratio_min(=0.5) × radius_token` | DEFECT |
| `radius_small` | `r_est_min < radius_ratio_warn(=0.8) × radius_token` | WARN |
| `asym` | 同图四角 `r_est` 极差 > `asym_max`(=4px) 且 min/max < `asym_ratio`(=0.5) | DEFECT |
| `n/a` | 该角所在行/列整条透明（无内容）→ 不判（记 n/a，绝不瞎猜） | — |

【B】弧线过渡质量（arc_hard；2026-09-20 M8 新增，需求方「ct_card.9.png 倒角严重锯齿」）
【A】只量「倒角有没有/够不够大」，看不见「弧上过渡被压进 1px」——
半透明 9-patch 卡片的弧上一像素从背景直接跳到 0.68×满值，几何 r_est 照样合格、肉眼却是锯齿。
本判据直接量**外沿过渡**：角块内「进入像素」= α > 0 且 4 邻域存在 α = 0 的像素。
覆盖率 = α / 峰值α（相对刻度，与半透明/不透明无关）。

要求：进入像素里**成组出现**覆盖率 ≤ `arc_lo_cov_max`(=0.35) 的像素：
        `min_cov ≤ 0.35` 且 `count(cov ≤ 0.35) ≥ arc_lo_px_min`(=2)。

**背景口径 = 完全透明（α=0）**，不用相对比例阈值：0.02×峰值 会把真 AA 的低覆盖率像素
（实测 0.004~0.012）当背景吞掉 —— 实测把 10px 药丸的最小覆盖率从 0.012 抬到 0.333，
离阈值只剩 5% 余量（假阳风险）。改成 α=0 后本工程 78 张可判资产的最大值 0.153（2.3× 余量）。

**阈值出处（不是拍的）**：α = 覆盖率口径下，绕一个 90° 圆弧被边界穿过的像素数
N ≈ (π/2)·r（r=14 → 22），像素中心到边界的有符号距离的小数部分近似均匀分布
→ 覆盖率在 (0,1) 上近似均匀 → **P(最小覆盖率 > t) = (1−t)^N**：

| t | N=22 | N=8（小半径/角块裁到 8 px） |
|---|---|---|
| 0.35 | 6×10⁻⁵ | 3.2×10⁻² |
| 0.5 | 2×10⁻⁷ | 3.9×10⁻³ |

取 `t=0.35`：真 AA 的弧上「一个 ≤0.35 的进入像素都没有」的概率 ≤ 6×10⁻⁵。
再看阈值档位：`SS=4`（标准 §1 的**最低**要求）覆盖率量化 = 1/16 = 0.0625，
第一步增量期望 0.15~0.30 → 过；`SS=2`（量化 0.25）与二值带（量化 1.0）→ 命中。
**阈值与标准自己写死的「≥4× 超采样」档位自洽**。

**实测分高线（本工程 153 张，2026-09-20）**：

| 样本 | min_cov | count(≤0.35) | 判定 |
|---|---|---|---|
| 真 AA 的最佳值（home_indicator / ct_check_off / vslider_fill / tile_*） | 0.153 / 0.180 / **0.012**/ 0.047 | 8 / 2 / 12 / 88 | CLEAN（离阈值 ≥2.3×） |
| `ct_card.9.png` **修前**（二值描边带） | **0.676**（p05=p10 同值） | **0**| DEFECT |
| `ct_card.9.png` **修后**（覆盖率口径） | 0.147 | 24 | CLEAN |

| 结果 | 条件 | 级别 |
|---|---|---|
| `arc_hard` | 四角进入像素合计 ≥ `arc_min_px`(=8) 且（min_cov > 0.35 或 count(≤0.35) < `arc_lo_px_min`(=2)） | DEFECT |
| `arc_hard_corner` | 某角进入像素 ≥ `arc_corner_min_px`(=4) 且该角 min_cov > 0.35 | WARN（不阻塞） |
| `n/a` | 无完全透明背景（烘底色/满幅）/ 无进入像素 / 进入像素 < `arc_min_px` | NOTE（不猜） |

作用域：`rect` / `round` 族 + **所有 `*.9.png`**（不论登记成什么族——这是 M8 要堵的盲区）；
`icon` / `inscribed` / `fullbleed` 照旧由 `alpha_bg_audit.py` 判，但**弧线指标仍会算出来写进 JSON**
（不静默、也不误判 FAIL）。

用法
----
    python tools/qa/corner_audit.py <目录|单图> [--recursive] [--rules asset_audit_rules.json]
            [--json out.json] [--evidence-dir dir] [--zoom 8] [--fail] [--exclude "sheet_*"]
            [--arc-only]          # 只判【B】弧线过渡质量（check_all #25 用）
            [--no-arc]            # 不判【B】弧线过渡质量（排查用）
            [--verbose-arc]       # 逐张打印弧线指标（含 CLEAN）
退出码：0 = 无缺陷；`--fail` 时「有真缺陷」→ 1（门禁用这个）。
  `--list-classes` 只打印分类结果（登记表体检）。
"""
import argparse
import fnmatch
import json
import math
import os
import sys

try:
    import numpy as np
    from PIL import Image, ImageDraw
    _HAS_DEPS = True
except Exception as _e:                                   # pragma: no cover
    np = None
    _HAS_DEPS = False
    _DEP_ERR = str(_e)

RULES_NAME = 'asset_audit_rules.json'
_DEFAULTS = {
    'alpha_opaque': 128, 'corner_block': 3, 'corner_d_square': 1,
    'r_min_abs': 2.5, 'radius_ratio_min': 0.5, 'radius_ratio_warn': 0.8,
    'asym_max': 4.0, 'asym_ratio': 0.5,
    # 【B】弧线过渡质量（标准 §7.7）：阈值出处见模块头（P(min_cov>t)=(1-t)^N）
    'arc_lo_cov_max': 0.35, 'arc_min_px': 8, 'arc_corner_min_px': 4, 'arc_lo_px_min': 2,
    'arc_bg_ratio': 0.0, 'arc_bg_abs': 0, 'arc_pad': 2, 'arc_block_min': 6,
}
_NOT_CORNER_KIND = {
    'icon': '图标族不做倒角判据（图标四周透明边距由 alpha_bg_audit 判，标准 §7.1/§2.3）',
    'inscribed': '内切图形族不做倒角判据（形状外透明由 alpha_bg_audit 判）',
    'fullbleed': '满幅/底图族（登记理由见 rules.allow/规则 reason）',
    'unknown': '未登记资产（按 unknown_policy：只 NOTE、不判 FAIL）',
}


# ---------------------------------------------------------------- 规则装载
def find_rules(explicit=None):
    env = os.environ.get('ASSET_AUDIT_RULES', '').strip()
    here = os.path.dirname(os.path.abspath(__file__))
    cands = ([explicit] if explicit else []) + ([env] if env else []) + [
        os.path.join(here, RULES_NAME),
        os.path.join(here, '..', 'qa', RULES_NAME),
        os.path.join(here, '..', '..', 'qa', RULES_NAME),
    ]
    for c in cands:
        if c and os.path.isfile(c):
            return os.path.abspath(c)
    return None


def load_rules(path):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    defaults = dict(_DEFAULTS)
    defaults.update(data.get('defaults') or {})
    return data, defaults, (data.get('rules') or [])


def classify(name, rules):
    """返回 (kind, radius, rule) —— 首个匹配的 glob 生效。"""
    for r in rules:
        if fnmatch.fnmatch(name.lower(), str(r.get('glob', '')).lower()):
            return r.get('kind', 'unknown'), r.get('radius'), r
    return 'unknown', None, None


def token_of(kind, radius, w, h):
    """radius_token：数字直接用；'pill' = h/2（药丸）；round = min(w,h)/2。"""
    if kind == 'round':
        return min(w, h) / 2.0
    if radius is None:
        return None
    if isinstance(radius, str):
        if radius.strip().lower() == 'pill':
            return min(w, h) / 2.0          # 药丸：短边即直径（横条 h/2、竖条 w/2）
        try:
            return float(radius)
        except ValueError:
            return None
    return float(radius)


# ---------------------------------------------------------------- 几何
def r_est_from_d(d):
    """由边起跑距离反解圆弧半径：d = r - sqrt(r-0.25) → r = (0.5+sqrt(d))^2 + 0.25。"""
    return (0.5 + math.sqrt(max(0.0, float(d)))) **2 + 0.25


def _first_opaque(line, alpha_opaque, reverse=False):
    v = line[::-1] if reverse else line
    idx = np.where(v >= alpha_opaque / 255.0)[0]
    return int(idx[0]) if len(idx) else -1


def corner_metrics(a, alpha_opaque):
    """四角 {d_row,d_col,r_est,block_opaque}；d=-1 表示该边整条透明（不判）。"""
    h, w = a.shape
    out = {}
    specs = {
        'tl': (a[0, :], False, a[:, 0], False, 0, 0),
        'tr': (a[0, :], True, a[:, w - 1], False, 0, w - 1),
        'bl': (a[h - 1, :], False, a[:, 0], True, h - 1, 0),
        'br': (a[h - 1, :], True, a[:, w - 1], True, h - 1, w - 1),
    }
    for k, (row, rrev, col, crev, ry, cx) in specs.items():
        d_row = _first_opaque(row, alpha_opaque, rrev)
        d_col = _first_opaque(col, alpha_opaque, crev)
        judged = d_row >= 0 and d_col >= 0
        r1 = r_est_from_d(d_row) if d_row >= 0 else None
        r2 = r_est_from_d(d_col) if d_col >= 0 else None
        rr = [x for x in (r1, r2) if x is not None]
        out[k] = {'d_row': d_row, 'd_col': d_col, 'judged': judged,
                  'r_est': (min(rr) if rr else None), 'r_est_mean': (sum(rr) / len(rr) if rr else None),
                  'row': ry, 'col': cx}
    return out


# ---------------------------------------------------------------- 证据图
def corner_evidence(path, name, a, metrics, bad, out_dir, zoom=8):
    """四角放大拼图（8× 最近邻）+ 违例角红框，给人眼看。"""
    h, w = a.shape
    k = max(16, min(48, int(max(w, h) * 0.45)))
    k = min(k, w, h)
    tiles = []
    for ck in ('tl', 'tr', 'bl', 'br'):
        x0 = 0 if ck in ('tl', 'bl') else w - k
        y0 = 0 if ck in ('tl', 'tr') else h - k
        sub = a[y0:y0 + k, x0:x0 + k]
        img = Image.fromarray((np.clip(sub, 0, 1) * 255).astype('uint8'), 'L')
        tiles.append((ck, img.resize((k * zoom, k * zoom), Image.NEAREST)))
    pad, lab = 6, 22
    tw = tiles[0][1].width
    canvas = Image.new('RGB', (tw * 2 + pad * 3, tw * 2 + pad * 3 + lab * 2), (32, 32, 36))
    d = ImageDraw.Draw(canvas)
    for i, (ck, img) in enumerate(tiles):
        cx = pad + (i % 2) * (tw + pad)
        cy = pad + (i // 2) * (tw + pad + lab)
        canvas.paste(img.convert('RGB'), (cx, cy))
        d.text((cx + 2, cy + tw + 4), '%s r_est=%s' % (
            ck.upper(), ('%.1f' % metrics[ck]['r_est']) if metrics[ck]['judged'] else 'n/a'),
            fill=(230, 230, 230))
        if ck in bad:
            d.rectangle([cx - 2, cy - 2, cx + tw + 1, cy + tw + 1], outline=(255, 64, 64), width=3)
    out = os.path.join(out_dir, os.path.splitext(name)[0] + '.corner.png')
    canvas.save(out)
    return out


# ---------------------------------------------------------------- 【B】弧线过渡质量
_CORNERS = ('tl', 'tr', 'bl', 'br')


def content_alpha(name, a_full):
    """返回 (α 数组, 是否 9-patch)；`*.9.png` **剥离最外 1px marker 环**。

    9-patch 的最外 1px 是拉伸区/内容区元数据（纯黑不透明），不是视觉内容：
      · 把它当内容 → 量到的是 marker 环的透明角（r_est 虚高，实测 19.35，把真缺陷放过去）；
      · 半透明卡片还会有 marker 行 α=255 的假“不透明边界”。
故先剥离再判；marker 行本身的量化残留由 aa_audit 的豁免区负责（分工不重叠）。
    """
    ninepatch = name.lower().endswith('.9.png')
    if ninepatch and a_full.shape[0] > 2 and a_full.shape[1] > 2:
        return a_full[1:-1, 1:-1], True
    return a_full, False


def effective_opaque_thr(alpha_opaque, a):
    """不透明阈值：不透明资产用 `alpha_opaque`；**半透明资产改相对阈值**（峰值的一半）。

没有这一条时，峰值 α < 128 的资产（半透卡片/半透面板）四角 d 全 = -1 → 整条半径判据失效。
    """
    amax = float(a.max()) if a.size else 0.0
    if amax * 255.0 < alpha_opaque:
        return max(1, int(math.ceil(0.5 * amax * 255.0))) / 255.0
    return alpha_opaque / 255.0


def _neighbour_any(mask):
    """4 邻域（图外视为 False）—— 向量化。"""
    out = np.zeros_like(mask)
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    return out


def arc_metrics(a, tok, d):
    """【B】弧线过渡质量：四角角块内「外沿进入像素」的覆盖率下限。

进入像素 = α > 背景阈值 且 4 邻域存在 α ≤ 背景阈值的像素（内容区最外沿按背景算）。
覆盖率 = α / 峰值α（相对刻度，与半透明/不透明无关）。
返回 dict(verdict=CLEAN|WARN|DEFECT|NOTE, judged, min_cov, n_px, corners, amax, reason)
    """
    out = {'judged': False, 'verdict': 'NOTE', 'min_cov': None, 'n_px': 0, 'amax': 0.0,
           'corners': {k: {'n': 0, 'min_cov': None} for k in _CORNERS}, 'reason': ''}
    if a.size == 0:
        out['reason'] = '空图'
        return out
    amax = float(a.max())
    out['amax'] = round(amax * 255.0, 1)
    out['levels'] = len(np.unique(np.round(a * 255.0).astype(np.int16)).tolist())
    if amax <= 0.0:
        out['reason'] = '内容区全透明（没有形状可判）'
        return out
    bg_thr = max(float(d.get('arc_bg_abs', 0)) / 255.0, float(d['arc_bg_ratio']) * amax)
    # 背景 = 完全透明像素（α ≤ bg_thr，默认为 0）∪ **图外**
    # （不是「图最外 1px」：9-patch 本体剥离 marker 环后，本体最外一行/列就是卡片自己的描边，
    #把它当背景会把描边内侧的填充像素误判成「进入像素」）
    bgin = a <= bg_thr
    padded = np.pad(bgin, 1, mode='constant', constant_values=True)
    nbr_bg = _neighbour_any(padded)[1:-1, 1:-1]
    enter = (a > bg_thr) & nbr_bg
    if not enter.any():
        out['reason'] = ('内容区没有「背景→形状」的外沿（整图不透明/烘了底色 → 由 alpha_bg_audit 判）')
        return out
    h, w = a.shape
    K = (int(math.ceil(float(tok))) + int(d['arc_pad'])) if tok else max(6, min(w, h) // 4)
    K = int(max(int(d['arc_block_min']), min(K, w, h)))
    per = {}
    for k in _CORNERS:
        ys = slice(0, K) if k in ('tl', 'tr') else slice(h - K, h)
        xs = slice(0, K) if k in ('tl', 'bl') else slice(w - K, w)
        sub = enter[ys, xs]
        vals = a[ys, xs][sub] / amax
        n = int(sub.sum())
        per[k] = {'n': n, 'min_cov': (round(float(vals.min()), 3) if n else None)}
    out['corners'] = per
    ns = [v['min_cov'] for v in per.values() if v['min_cov'] is not None]
    n_tot = sum(v['n'] for v in per.values())
    thr = float(d['arc_lo_cov_max'])
    # 低覆盖率进入像素（成组出现才算）——直接对全图算，保证与角块口径一致
    cov_all = a[enter] / amax
    out.update(judged=True, n_px=n_tot, min_cov=(round(min(ns), 3) if ns else None), block=K,
               lo_n=int((cov_all <= thr).sum()), lo_thr=thr,
               max_corner_cov=(round(max(ns), 3) if ns else None))
    if not ns or n_tot < int(d['arc_min_px']):
        out.update(verdict='NOTE',
                   reason='外沿进入像素只有 %d 个（< arc_min_px=%d）→ 样本不足，不判'
                          % (n_tot, int(d['arc_min_px'])))
        return out
    if min(ns) > thr or out['lo_n'] < int(d['arc_lo_px_min']):
        out.update(verdict='DEFECT',
                   reason='弧线过渡被压进 1px 硬阶梯（外沿进入像素最小覆盖率 %.3f，'
                          '≤%.2f 的只有 %d 个 < %d；角块内 %d 个 α 级别）'
                          % (min(ns), thr, out['lo_n'], int(d['arc_lo_px_min']),
                             out.get('levels') or 0))
        return out
    hard = [k for k in _CORNERS if per[k]['n'] >= int(d['arc_corner_min_px'])
            and per[k]['min_cov'] is not None and per[k]['min_cov'] > thr]
    if hard:
        out.update(verdict='WARN',
                   reason='部分角弧线过渡硬阶梯（%s 最小覆盖率 %s > %.2f）'
                          % (','.join(k.upper() for k in hard),
                             [per[k]['min_cov'] for k in hard], thr))
        return out
    out.update(verdict='CLEAN',
               reason='弧线过渡正常（四角最小覆盖率 %.3f ≤ %.2f，≤%.2f 的进入像素 %d 个，共 %d 个）'
                      % (min(ns), thr, thr, out['lo_n'], n_tot))
    return out


def _frame_mask(shape):
    """（保留：包住整图外沿的 mask；弧线判据不用它——见 arc_metrics 的 pad 口径）"""
    m = np.zeros(shape, dtype=bool)
    m[0, :] = m[-1, :] = m[:, 0] = m[:, -1] = True
    return m


# ---------------------------------------------------------------- 主流程
def audit(path_or_dir, args):
    rules_path = find_rules(args.rules)
    if not rules_path:
        print('[X] 找不到 %s（--rules 或环境变量 ASSET_AUDIT_RULES 指定；'
              '这是判定口径的唯一来源，不能缺省猜测）' % RULES_NAME)
        return None, None
    rdata, defaults, rules = load_rules(rules_path)
    alpha_opaque = defaults['alpha_opaque']
    if os.path.isdir(path_or_dir):
        files = []
        for root, _d, fs in os.walk(path_or_dir):
            if root != path_or_dir and not args.recursive:
                continue
            for f in sorted(fs):
                if f.lower().endswith('.png'):
                    files.append(os.path.join(root, f))
    else:
        files = [path_or_dir]
    if args.exclude:
        files = [f for f in files if not any(fnmatch.fnmatch(os.path.basename(f), p)
                                             for p in args.exclude.split(','))]
    rows = []
    arc_only = bool(getattr(args, 'arc_only', False))
    no_arc = bool(getattr(args, 'no_arc', False))
    for p in sorted(files):
        name = os.path.basename(p)
        kind, radius, rule = classify(name, rules)
        row = {'name': name, 'path': p, 'kind': kind, 'rule': (rule or {}).get('glob'),
               'verdict': 'CLEAN', 'reason': ''}
        try:
            im = Image.open(p)
            row['w'], row['h'] = im.size
            row['mode'] = im.mode
            a_full = np.asarray(im.convert('RGBA'), dtype=np.uint8)[..., 3] \
                .astype(np.float32) / 255.0
        except Exception as e:                            # noqa: BLE001
            row.update(verdict='ERROR', reason='读图失败 %s: %s' % (type(e).__name__, e))
            rows.append(row)
            continue
        # 9-patch 剥离最外 1px marker 环 → 只判本体（否则marker 环会把判据全带偏）
        a, ninepatch = content_alpha(name, a_full)
        row['ninepatch'] = ninepatch
        if ninepatch:
            row['content_size'] = [int(a.shape[1]), int(a.shape[0])]
        thr = effective_opaque_thr(alpha_opaque, a)
        row['opaque_thr'] = round(thr * 255.0, 1)
        if kind in _NOT_CORNER_KIND:
            why = _NOT_CORNER_KIND[kind]
            if kind == 'fullbleed':
                why = '满幅/底图族（必须不透明）登记理由：%s' % (
                    (rule or {}).get('reason') or (rule or {}).get('note') or '见规则表')
            # 弧线判据对 .9.png 仍然跑（修 M8 盲区：9-patch 不论登记为什么族都要查弧）
            if ninepatch and not no_arc:
                am = arc_metrics(a, None, defaults)
                row['arc'] = am
                row['arc_min_cov'] = am['min_cov']
                row['arc_n_px'] = am['n_px']
                if am['verdict'] == 'DEFECT':
                    row.update(verdict='DEFECT', reason='[弧线过渡] %s' % am['reason'],
                               at=['arc'])
                elif am['verdict'] == 'WARN':
                    row.update(verdict='WARN', reason='[弧线过渡] %s' % am['reason'])
                else:
                    row.update(verdict='NOTE', reason='%s；（9-patch 本体）%s'
                               % (why, am.get('reason') or '弧线不适用'))
                if args.evidence_dir and row['verdict'] in ('DEFECT', 'WARN'):
                    os.makedirs(args.evidence_dir, exist_ok=True)
                    row['evidence'] = corner_evidence(p, name, a, corner_metrics(a, thr * 255.0),
                                                      {'arc'}, args.evidence_dir, args.zoom)
                rows.append(row)
                continue
            row.update(verdict=('EXEMPT' if kind == 'fullbleed' else 'NOTE'), reason=why)
            rows.append(row)
            continue
        m = corner_metrics(a, thr * 255.0)
        tok = token_of(kind, radius, a.shape[1], a.shape[0])
        judged = [k for k in ('tl', 'tr', 'bl', 'br') if m[k]['judged']]
        rs = [m[k]['r_est'] for k in judged]
        bad, warns, notes = [], [], []
        for k in judged:
            if m[k]['d_row'] <= defaults['corner_d_square'] and \
               m[k]['d_col'] <= defaults['corner_d_square']:
                bad.append(('%s 直角残留（α 铺到角点：d_row=%d d_col=%d）'
                            % (k.upper(), m[k]['d_row'], m[k]['d_col']), k))
            elif m[k]['r_est'] <= defaults['r_min_abs']:
                bad.append(('%s 倒角过小（r_est=%.1fpx ≤ %.1fpx）'
                            % (k.upper(), m[k]['r_est'], defaults['r_min_abs']), k))
        if tok:
            rmin = min(rs) if rs else None
            if rmin is not None:
                if rmin < defaults['radius_ratio_min'] * tok:
                    bad.append(('倒角小于令牌（r_est=%.1fpx < 0.5×%.0fpx=%.1fpx）'
                                % (rmin, tok, defaults['radius_ratio_min'] * tok),
                                min(judged, key=lambda k: m[k]['r_est'])))
                elif rmin < defaults['radius_ratio_warn'] * tok:
                    warns.append('倒角偏小（r_est=%.1fpx < 0.8×%.0fpx）'
                                 % (rmin, defaults['radius_ratio_warn'] * tok))
                if len(rs) >= 2 and len(judged) == 4:
                    rmax = max(rs)
                    if rmax - rmin > defaults['asym_max'] and rmin < defaults['asym_ratio'] * rmax:
                        bad.append(('四角倒角不一致（r_est %.1f~%.1fpx，极差 %.1fpx）'
                                    % (rmin, rmax, rmax - rmin),
                                    min(judged, key=lambda k: m[k]['r_est'])))
                if len(judged) < 4:
                    notes.append('仅 %d 角可判（其余角所在边整条透明 → 不判）' % len(judged))
        row.update(corners={k: {'d_row': m[k]['d_row'], 'd_col': m[k]['d_col'],
                                'r_est': (None if m[k]['r_est'] is None
                                          else round(m[k]['r_est'], 2))}
                            for k in m},
                   r_est_min=(round(min(rs), 2) if rs else None),
                   radius_token=(round(tok, 2) if tok else None))
        # 【B】弧线过渡质量（与【A】独立计一个判据；--arc-only 时只看它）
        am = None if no_arc else arc_metrics(a, tok, defaults)
        if am is not None:
            row['arc'] = am
            row['arc_min_cov'] = am['min_cov']
            row['arc_n_px'] = am['n_px']
        geo_bad = bool(bad)
        arc_bad = bool(am and am['verdict'] == 'DEFECT')
        if arc_only:
            bad, warns, notes = [], [], []
            if am is None:
                pass
            elif arc_bad:
                bad.append(('[弧线过渡] %s' % am['reason'], 'arc'))
            elif am['verdict'] == 'WARN':
                warns.append('[弧线过渡] %s' % am['reason'])
            elif am['verdict'] == 'NOTE':
                notes.append('[弧线过渡] %s' % am['reason'])
        else:
            if arc_bad:
                bad.append(('[弧线过渡] %s' % am['reason'], 'arc'))
            elif am is not None and am['verdict'] == 'WARN':
                warns.append('[弧线过渡] %s' % am['reason'])
            elif am is not None and am['verdict'] == 'NOTE':
                notes.append('[弧线过渡] %s' % am['reason'])
        if bad:
            row.update(verdict='DEFECT',
                       reason='；'.join(t[0] for t in bad),
                       at=[t[1] for t in bad])
        elif warns:
            row.update(verdict='WARN', reason='；'.join(warns))
        else:
            row.update(reason='；'.join(notes) or '四角倒角正常（r_est=%s / 令牌=%s）'
                       % (row['r_est_min'], row['radius_token']))
        if args.evidence_dir and ((bad and not arc_only) or geo_bad or arc_bad or
                                  args.evidence_all):
            os.makedirs(args.evidence_dir, exist_ok=True)
            row['evidence'] = corner_evidence(p, name, a, m, set(row.get('at') or []),
                                              args.evidence_dir, args.zoom)
        rows.append(row)
    return rows, rules_path, defaults


def main():
    ap = argparse.ArgumentParser(description='切图「缺倒角 / 直角残留」审计')
    ap.add_argument('target', help='图片目录或单张 PNG')
    ap.add_argument('--recursive', action='store_true', help='子目录也扫')
    ap.add_argument('--rules', default=None, help='判定口径登记表（默认 asset_audit_rules.json）')
    ap.add_argument('--json', default=None, help='结果写 JSON')
    ap.add_argument('--evidence-dir', default=None, help='证据图（四角放大 + 红框）目录')
    ap.add_argument('--evidence-all', action='store_true', help='干净图也出证据图')
    ap.add_argument('--zoom', type=int, default=8, help='角部放大倍数（默认 8× 最近邻）')
    ap.add_argument('--exclude', default=None, help='逗号分隔 glob（如 "sheet_*,*_old.png"）')
    ap.add_argument('--fail', action='store_true', help='有真缺陷 → 退出码 1')
    ap.add_argument('--list-classes', action='store_true', help='只打印分类（登记表体检）')
    ap.add_argument('--arc-only', action='store_true',
                    help='只判【B】弧线过渡质量（9-patch 圆角 AA；check_all #25 用）')
    ap.add_argument('--no-arc', action='store_true', help='不判【B】弧线过渡质量（排查用）')
    ap.add_argument('--verbose-arc', action='store_true', help='逐张打印弧线过渡指标（含 CLEAN）')
    args = ap.parse_args()

    if not _HAS_DEPS:
        print('[ERROR] 需要 numpy + Pillow：%s' % _DEP_ERR)
        return 2
    rows, rules_path, defaults = audit(args.target, args)
    if rows is None:
        return 2
    if args.list_classes:
        for r in rows:
            print('%-40s %-10s token=%s rule=%s' % (r['name'], r['kind'],
                                                    r.get('radius_token'), r.get('rule')))
        return 0
    defect = [r for r in rows if r['verdict'] == 'DEFECT']
    warn = [r for r in rows if r['verdict'] == 'WARN']
    exempt = [r for r in rows if r['verdict'] == 'EXEMPT']
    note = [r for r in rows if r['verdict'] == 'NOTE']
    clean = [r for r in rows if r['verdict'] == 'CLEAN']
    err = [r for r in rows if r['verdict'] == 'ERROR']
    print('== corner_audit（缺倒角 / 直角残留%s）口径 %s =='
          % (' + 弧线过渡质量' if not args.no_arc else '', rules_path))
    print('扫 %d 张：真缺陷 %d / WARN %d / EXEMPT %d / NOTE %d / 干净 %d / 错误 %d'
          % (len(rows), len(defect), len(warn), len(exempt), len(note), len(clean), len(err)))
    arc_rows = [r for r in rows if isinstance(r.get('arc'), dict) and r['arc'].get('judged')]
    if arc_rows:
        arc_bad = [r for r in arc_rows if r['arc']['verdict'] == 'DEFECT']
        arc_warn = [r for r in arc_rows if r['arc']['verdict'] == 'WARN']
        arc_note = [r for r in rows if isinstance(r.get('arc'), dict)
                    and r['arc'].get('verdict') == 'NOTE']
        print('【B】弧线过渡质量：可判 %d 张（最小覆盖率 ≤%.2f = 过）；弧线硬阶梯 %d / 部分角 WARN %d /'
              '样本不足或不适用的 NOTE %d'
              % (len(arc_rows), defaults['arc_lo_cov_max'], len(arc_bad), len(arc_warn),
                 len(arc_note)))
        for r in arc_rows:
            if r['arc']['verdict'] != 'CLEAN':
                continue
            if args.arc_only or args.verbose_arc:
                print('  [ARC CLEAN] %-32s α峰值=%-6s 进入像素=%-4d 最小覆盖率=%-6s 角块=%s'
                      % (r['name'], r['arc']['amax'], r['arc']['n_px'], r['arc']['min_cov'],
                         r['arc'].get('block')))
        for r in arc_bad:
            print('  [ARC DEFECT] %-31s %s' % (r['name'], r['arc']['reason']))
            print('四角最小覆盖率 %s（角块 %s，进入像素 %d）'
                  % ({k.upper(): v['min_cov'] for k, v in r['arc']['corners'].items()},
                     r['arc'].get('block'), r['arc']['n_px']))
        for r in arc_warn:
            print('  [ARC WARN]   %-31s %s' % (r['name'], r['arc']['reason']))
        for r in arc_note[:8]:
            print('  [ARC NOTE]   %-31s %s' % (r['name'], r['arc']['reason']))
        if len(arc_note) > 8:
            print('  [ARC NOTE]   ...其余 %d 张同类' % (len(arc_note) - 8))
    if defect:
        print('--- [DEFECT] 真缺陷 ---')
        for r in defect:
            print('%-38s %4dx%-4d %s' % (r['name'], r['w'], r['h'], r['reason']))
            if r.get('corners'):
                print('四角(边界起跑 d / r_est) %s 令牌=%s'
                      % (r['corners'], r['radius_token']))
                for k in dict.fromkeys(r.get('at') or []):
                    if k in r['corners']:
                        print('     %s@ d_row=%s d_col=%s' % (k.upper(),
                                                              r['corners'][k]['d_row'],
                                                              r['corners'][k]['d_col']))
            if r.get('evidence'):
                print('证据图 %s' % r['evidence'])
    if warn:
        print('--- [WARN] 需人工确认（不阻塞）---')
        for r in warn:
            print('%-38s %s' % (r['name'], r['reason']))
    if exempt:
        print('--- [EXEMPT] 豁免（逐条理由）---')
        for r in exempt:
            print('%-38s %s' % (r['name'], r['reason']))
    if note:
        print('--- [NOTE] 不适用 / 未登记（不静默）---')
        for r in note:
            print('%-38s %s' % (r['name'], r['reason']))
    if err:
        print('--- [ERROR] ---')
        for r in err:
            print('%-38s %s' % (r['name'], r['reason']))
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        print('saved -> %s' % args.json)
    if args.fail and defect:
        print('[FAIL] 缺倒角 %d 张：%s' % (len(defect), ', '.join(r['name'] for r in defect[:20])))
        return 1
    if defect:
        print('[PASS?] 真缺陷 %d 张（未加 --fail）' % len(defect))
    else:
        print('[PASS] 真缺陷 0 张（WARN %d / EXEMPT %d / NOTE %d 已逐条列理由）'
              % (len(warn), len(exempt), len(note)))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception as e:                            # noqa: BLE001
            sys.stderr.write('[NOTE] stdout 重编码失败（不影响判定，仅影响控制台字形）：%s\n' % e)
    sys.exit(main())
