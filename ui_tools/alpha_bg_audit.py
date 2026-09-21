# -*- coding: utf-8 -*-
"""alpha_bg_audit.py — 「该透明的图片做成了黑底 / 烘了底色」审计（2026-09-20 M5）

钟工原话：「控件里面图片背景是黑色的，应该做成透明的，**这个设计不符合 flyThings OS 平台的能力**」。

平台口径（标准侧 ≠ Lite 侧，两套口径不能混）
--------------------------------------------
* **标准侧（Linux SoC：F133/Z20/Z21/T113/V85x）支持 PNG alpha** → 形状类资产必须是
  **真透明底**（形状外 α=0）；**禁止**把页面底色/黑底烘进图里充当透明。
* **Lite 侧（MCU，RGB565 + colorkey，无 α 混合）**才用「形状外填页面背景色 / 键色」的烘焙法
  （出处：`references/kb/lite-input-pipeline.md` §「平台画图硬约束：只支持 RGB565 + colorkey」）。
  把 Lite 的做法带到标准侧 = 本审计要拦的缺陷。

判据（`asset_audit_rules.json` 分类 + `defaults` 阈值，逐条追溯到标准 §7.1/§7.4）
--------------------------------------------------------------------------
| 指标 | 适用类 | 口径 | 级别 |
|---|---|---|---|
| `no_alpha` | rect/round/inscribed/icon | `min(α) >= min_alpha_max`(=250) → **整图没有透明像素** = 底色被烘进图（或根本没存 α 通道） | DEFECT |
| `corner_opaque` | round/inscribed/icon | 四角角块（`corner_block`²）不透明率 ≥ `corner_opaque_max`(=0.5) → **形状外（角区）有不透明像素** | DEFECT |
| `edge_bleed` | icon | 最外 1px 环不透明率 ≥ `edge_bleed_fail`(=0.25)，或任一条边 ≥ `edge_bleed_edge`(=0.9) → 图标贴死图边（标准 §2.3：图标四周须留 ≥1px 透明） | DEFECT |
| `low_zero` | rect/round/inscribed/icon | 透明像素占比 < `zero_ratio_min`(=0.2%) → 疑似满幅烘底（需人确认/登记） | WARN |
| — | fullbleed | 满幅/底图族（照片、壁纸、遮罩、1px 通栏线、软阴影）→ 按登记理由 `EXEMPT` | — |
| — | unknown | 未登记资产 → `NOTE`（列出来，不静默、不判 FAIL） | — |

用法
----
    python tools/qa/alpha_bg_audit.py <目录|单图> [--recursive] [--rules ...]
            [--json out.json] [--evidence-dir dir] [--zoom 4] [--fail]
            [--exclude "sheet_*"] [--list-classes]
  退出码：0 = 无缺陷；`--fail` 时「有真缺陷」→ 1（门禁用这个）。
"""
import argparse
import fnmatch
import json
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
    'alpha_opaque': 128,
    'min_alpha_max': 250,
    'zero_ratio_min': 0.002,
    'corner_block': 3,
    'corner_opaque_max': 0.5,
    'edge_bleed_fail': 0.25,
    'edge_bleed_edge': 0.9,
    'edge_bleed_warn': 0.05,
}
# 形状类（必须真透明）：由分类表 kind 决定；fullbleed 是「必须不透明」族（登记理由）
_SHAPE_KINDS = ('rect', 'round', 'inscribed', 'icon')


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
    for r in rules:
        if fnmatch.fnmatch(name.lower(), str(r.get('glob', '')).lower()):
            return r.get('kind', 'unknown'), r
    return 'unknown', None


def _corner_blocks(a, n):
    h, w = a.shape
    n = max(1, min(n, w, h))
    return {
        'tl': a[0:n, 0:n], 'tr': a[0:n, w - n:w],
        'bl': a[h - n:h, 0:n], 'br': a[h - n:h, w - n:w],
    }


def metrics(a, d):
    """返回 no_alpha / zero_ratio / 角块不透明率 / 边环不透明率（全部可复算）。"""
    h, w = a.shape
    opq = d['alpha_opaque'] / 255.0
    min_a = float(a.min())
    zero_ratio = float((a < 0.004).mean())
    cb = {k: float((v >= opq).mean()) for k, v in _corner_blocks(a, d['corner_block']).items()}
    edges = {'top': float((a[0, :] >= opq).mean()), 'bottom': float((a[h - 1, :] >= opq).mean()),
             'left': float((a[:, 0] >= opq).mean()), 'right': float((a[:, w - 1] >= opq).mean())}
    ring = (edges['top'] * w + edges['bottom'] * w + edges['left'] * h + edges['right'] * h) \
        / float(2 * (w + h))
    return {'min_alpha': min_a, 'zero_ratio': zero_ratio, 'corners': cb,
            'edges': edges, 'ring': ring}


def evidence(path, name, a, m, bad, out_dir, zoom=4):
    """证据图：α 掩膜上把违例的角块/边环标红。"""
    h, w = a.shape
    img = Image.fromarray((np.clip(a, 0, 1) * 255).astype('uint8'), 'L').convert('RGB')
    d = ImageDraw.Draw(img)
    if 'corner_opaque' in bad:
        n = max(1, min(3, w, h))
        for k, box in (('tl', (0, 0, n - 1, n - 1)), ('tr', (w - n, 0, w - 1, n - 1)),
                       ('bl', (0, h - n, n - 1, h - 1)), ('br', (w - n, h - n, w - 1, h - 1))):
            d.rectangle(list(box), outline=(255, 64, 64))
    if 'edge_bleed' in bad:
        d.rectangle([0, 0, w - 1, h - 1], outline=(255, 160, 0))
    sc = max(1, min(zoom, int(600 / float(max(w, h))) or 1))
    if sc > 1:
        img = img.resize((w * sc, h * sc), Image.NEAREST)
    out = os.path.join(out_dir, os.path.splitext(name)[0] + '.alpha.png')
    img.save(out)
    return out


def audit(target, args):
    rules_path = find_rules(args.rules)
    if not rules_path:
        print('[X] 找不到 %s（--rules 或环境变量 ASSET_AUDIT_RULES 指定；'
              '这是判定口径的唯一来源，不能缺省猜测）' % RULES_NAME)
        return None, None
    rdata, defaults, rules = load_rules(rules_path)
    if os.path.isdir(target):
        files = []
        for root, _d, fs in os.walk(target):
            if root != target and not args.recursive:
                continue
            for f in sorted(fs):
                if f.lower().endswith('.png'):
                    files.append(os.path.join(root, f))
    else:
        files = [target]
    if args.exclude:
        files = [f for f in files if not any(fnmatch.fnmatch(os.path.basename(f), p)
                                             for p in args.exclude.split(','))]
    rows = []
    for p in sorted(files):
        name = os.path.basename(p)
        kind, rule = classify(name, rules)
        row = {'name': name, 'path': p, 'kind': kind, 'rule': (rule or {}).get('glob'),
               'verdict': 'CLEAN', 'reason': ''}
        try:
            im = Image.open(p)
            row['w'], row['h'] = im.size
            row['mode'] = im.mode
            a = np.asarray(im.convert('RGBA'), dtype=np.uint8)[..., 3].astype(np.float32) / 255.0
        except Exception as e:                            # noqa: BLE001
            row.update(verdict='ERROR', reason='读图失败 %s: %s' % (type(e).__name__, e))
            rows.append(row)
            continue
        if kind == 'fullbleed':
            row.update(verdict='EXEMPT',
                       reason='满幅/底图族（必须不透明）登记理由：%s'
                              % ((rule or {}).get('reason') or (rule or {}).get('note') or '见规则表'))
            rows.append(row)
            continue
        if kind == 'unknown':
            row.update(verdict='NOTE',
                       reason='未登记资产：按 rules.unknown_policy 只 NOTE、不判 FAIL；'
                              '请在 standard §7.1 分类表补登记')
            rows.append(row)
            continue
        m = metrics(a, defaults)
        bad, warns = [], []
        if m['min_alpha'] >= defaults['min_alpha_max'] / 255.0:
            bad.append('no_alpha（整图最小 α=%.0f ≥ %d：没有任何透明像素 → 底色被烘进图 / 丢了 α 通道）'
                       % (m['min_alpha'] * 255, defaults['min_alpha_max']))
        if kind in ('round', 'inscribed', 'icon'):
            hot = {k: v for k, v in m['corners'].items() if v >= defaults['corner_opaque_max']}
            if hot:
                bad.append('corner_opaque（形状外/角区不透明：%s → 形状外必须 α=0）%s'
                           % (', '.join('%s=%.2f' % (k, v) for k, v in hot.items()),
                              '【判定覆盖的角块 %d×%d】' % (defaults['corner_block'],
                                                          defaults['corner_block'])))
        if kind == 'icon':
            if m['ring'] >= defaults['edge_bleed_fail'] or \
               max(m['edges'].values()) >= defaults['edge_bleed_edge']:
                bad.append('edge_bleed（图标贴死图边：最外 1px 环不透明率 %.3f，各边 %s）'
                           % (m['ring'], ', '.join('%s=%.2f' % (k, v)
                                                   for k, v in m['edges'].items())))
            elif m['ring'] >= defaults['edge_bleed_warn']:
                warns.append('图标边距偏小（最外 1px 环不透明率 %.3f，各边 %s → 标准 §2.3 要求四周留 ≥1px 透明）'
                             % (m['ring'], ', '.join('%s=%.2f' % (k, v)
                                                     for k, v in m['edges'].items())))
        if kind in ('round', 'inscribed', 'icon') and m['zero_ratio'] < defaults['zero_ratio_min']:
            warns.append('透明区占比过低（%.3f%% < %.1f%%）→ 确认不是满幅烘底'
                         % (m['zero_ratio'] * 100, defaults['zero_ratio_min'] * 100))
        row.update(min_alpha=round(m['min_alpha'] * 255, 1), zero_ratio=round(m['zero_ratio'], 5),
                   corners={k: round(v, 3) for k, v in m['corners'].items()},
                   edges={k: round(v, 3) for k, v in m['edges'].items()}, ring=round(m['ring'], 4))
        if bad:
            row.update(verdict='DEFECT', reason='；'.join(bad),
                       at=[b.split('（')[0] for b in bad])
        elif warns:
            row.update(verdict='WARN', reason='；'.join(warns))
        else:
            row.update(reason='形状外真透明（min α=%.0f；透明像素占 %.1f%%；角块 %s）'
                       % (m['min_alpha'] * 255, m['zero_ratio'] * 100, row['corners']))
        if args.evidence_dir and (bad or args.evidence_all):
            os.makedirs(args.evidence_dir, exist_ok=True)
            row['evidence'] = evidence(p, name, a, m, set(row.get('at') or []),
                                       args.evidence_dir, args.zoom)
        rows.append(row)
    return rows, rules_path


def main():
    ap = argparse.ArgumentParser(description='透明底 / 烘底色审计')
    ap.add_argument('target', help='图片目录或单张 PNG')
    ap.add_argument('--recursive', action='store_true')
    ap.add_argument('--rules', default=None)
    ap.add_argument('--json', default=None)
    ap.add_argument('--evidence-dir', default=None)
    ap.add_argument('--evidence-all', action='store_true')
    ap.add_argument('--zoom', type=int, default=4)
    ap.add_argument('--exclude', default=None)
    ap.add_argument('--fail', action='store_true')
    ap.add_argument('--list-classes', action='store_true')
    args = ap.parse_args()
    if not _HAS_DEPS:
        print('[ERROR] 需要 numpy + Pillow：%s' % _DEP_ERR)
        return 2
    rows, rules_path = audit(args.target, args)
    if rows is None:
        return 2
    if args.list_classes:
        for r in rows:
            print('%-40s %-10s rule=%s' % (r['name'], r['kind'], r.get('rule')))
        return 0
    defect = [r for r in rows if r['verdict'] == 'DEFECT']
    warn = [r for r in rows if r['verdict'] == 'WARN']
    exempt = [r for r in rows if r['verdict'] == 'EXEMPT']
    note = [r for r in rows if r['verdict'] == 'NOTE']
    clean = [r for r in rows if r['verdict'] == 'CLEAN']
    err = [r for r in rows if r['verdict'] == 'ERROR']
    print('== alpha_bg_audit（透明底 / 烘底色）  口径 %s ==' % rules_path)
    print('扫 %d 张：真缺陷 %d / WARN %d / EXEMPT %d / NOTE %d / 干净 %d / 错误 %d'
          % (len(rows), len(defect), len(warn), len(exempt), len(note), len(clean), len(err)))
    if defect:
        print('--- [DEFECT] 真缺陷 ---')
        for r in defect:
            print('%-38s %4dx%-4d %s' % (r['name'], r['w'], r['h'], r['reason']))
            print('     minα=%s 透明区=%s%% 角块=%s 边环=%s'
                  % (r['min_alpha'], r['zero_ratio'] * 100 if r['zero_ratio'] < 1 else r['zero_ratio'],
                     r['corners'], r['ring']))
            if r.get('evidence'):
                print('     证据图 %s' % r['evidence'])
    if warn:
        print('--- [WARN] 需人工确认（不阻塞）---')
        for r in warn:
            print('%-38s %s' % (r['name'], r['reason']))
    if exempt:
        print('--- [EXEMPT] 豁免（逐条理由）---')
        for r in exempt:
            print('%-38s %s' % (r['name'], r['reason']))
    if note:
        print('--- [NOTE] 未登记（不静默）---')
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
        print('[FAIL] 透明底缺陷 %d 张：%s'
              % (len(defect), ', '.join(r['name'] for r in defect[:20])))
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
