#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""region_attrib.py —— 差异**区域级归因**：把「渲染图 vs 真机截图」的差异块归到**哪一层契约没满足**（T2.4）。

为什么要有它（REMEDIATION-UI-PIPELINE.md §2「差异归因三分」）：
  像素 diff 只回答「哪块不一样」，不回答「该改谁」。没有归因就会出现两种浪费：
  ① 把渲染器近似当成真缺陷去改渲染器（`DESIGN_SPEC` 1.2 的 ⛔TWEAK）；
  ② 把发射层字段错当成"渲染器不准"，然后去调阈值。
本文件把离线**已有**的三类证据拼起来，逐控件给出层级判定 + 证据；**判不出来就如实标
`U/UNATTRIBUTED`**（不猜），并统计「差异像素里有多少落在渲染器盲区」——那个比例就是
"这批差异离线判不了、必须真机复验"的量化口径。

层级口径（与 `knowledge/devflow/ui-pipeline-spec.md` §4 一致）：
  · `C/EMIT-FIELDS`   —— `ui_compile` 在该控件上报 fatal/error（字段/类型/必填）→ 改发射层
  · `E/RENDERER-BLINDSPOT` —— json2img 的 `unsupported[]` 命中该控件 → 渲染器不覆盖，离线判不了
  · `C/ASSET-GEOMETRY` —— json2img 报 `stretched`/`missing_assets` 命中（图≠盒、缺图）→ 资产/字段
  · `E/FONT-METRICS`  —— 文字盒内的差异（字形栅格化是模拟层，与 wysiwyg_diff 的 B 段同口径）
  · `A/FRONTEND-REPORT` —— 可选：把前端报告（html2json/translate_ui 的返回体）里的
     `warnings/downgrades/unrecognized` 按 caption 对上 → 前端已登记的语义丢失
  · `U/UNATTRIBUTED`  —— 以上都不命中：**不猜**，给 box/caption/量值交人工

用法：
  python ui_tools/region_attrib.py --json <页面.json> --render <渲染.png> --device <截图.png> \
      [--render-report <json2img --json-report 产物>] [--frontend-report <前端返回体.json>] \
      [--project <项目根>] [--tol 2] [--max-ratio 1.0] [--min-block 8] [--json-out <报告.json>]
退出码：0 = 超阈值的差异都落在 E 层（渲染器近似/盲区）或阈值内；1 = 有 C 层或未归因的超阈值差异。
"""
import argparse
import io
import json
import os
import sys

try:
    from PIL import Image, ImageChops
except Exception as ex:                                     # pragma: no cover
    print('[X] 需要 Pillow：%s' % ex)
    sys.exit(2)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(BASE, 'ui_tools') not in sys.path:
    sys.path.insert(0, os.path.join(BASE, 'ui_tools'))

import wysiwyg_diff as WD                                   # noqa: E402  （复用 walk / biggest_block：单一实现）

LAYER_C = ('C/EMIT-FIELDS', 'C/ASSET-GEOMETRY')
LAYER_E = ('E/RENDERER-BLINDSPOT', 'E/FONT-METRICS')
LAYER_A = ('A/FRONTEND-REPORT',)
LAYER_U = ('U/UNATTRIBUTED',)


def _load_json(path):
    if not path or not os.path.isfile(path):
        return None
    try:
        with io.open(path, encoding='utf-8-sig') as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        sys.stderr.write('[warn] 读不了 %s：%s\n' % (path, e))
        return None


def _blind_index(report):
    """json2img 报告 → ({type: [note...]}, {caption: [note...]})。

    ⚠️ 类型级只收「**没有任何 caption 例子**」的条目（钉不到具体控件的那种）；
    有例子的条目只按 caption 命中 —— 否则「一个 textview 开了 rollEnable」会把整页 textview
    都判成盲区（实测推演：类型级回落精度不足，归因会失真）。
    """
    by_type, by_cap = {}, {}
    for it in ((report or {}).get('unsupported') or []):
        note = '%s（%s）' % (it.get('field'), (it.get('note') or '')[:80])
        t = it.get('type') or ''
        pinned = []
        for ex in (it.get('examples') or []):
            if not ex:
                continue
            if '/' in str(ex):                      # 形态 = `<type>/<caption>`
                tt, _, cc = str(ex).partition('/')
                if cc:
                    pinned.append(cc)
                    by_cap.setdefault(cc, []).append(note)              # 裸 caption
                    by_cap.setdefault('%s/%s' % (tt, cc), []).append(note)   # 复合键
                continue
            pinned.append(str(ex))
            by_cap.setdefault(str(ex), []).append(note)
        if not pinned and t:
            by_type.setdefault(t, []).append(note)   # 只有钉不到具体控件的条目才允许类型级回落
    return by_type, by_cap


def _stretch_index(report):
    """json2img 的 `stretched` 只有 type、没有 caption → 仅作**兜底**（见 `_asset_mismatch`）。"""
    by_type, by_cap = {}, {}
    for it in ((report or {}).get('stretched') or []):
        r = '%s %s' % (it.get('ref'), it.get('size'))
        by_type.setdefault(it.get('type'), []).append(r)
    for it in ((report or {}).get('missing_assets') or []):
        caps = [c for c in (it.get('examples') or []) if c]
        if not caps:
            by_type.setdefault('*missing*', []).append('缺图 %s' % it.get('ref'))
        for c in caps:
            by_cap.setdefault(c, []).append('缺图 %s' % it.get('ref'))
    return by_type, by_cap


def _asset_mismatch(ctl, box, project_root, errs=None):
    """按**这一个控件**核对「图 == 盒」：→ [证据...]（判不了回空表，不猜）。

    复用 `check_all` 的引用收集与路径解析（单一实现）；PIL 只用来读 PNG 尺寸。

    `errs` 传 list 时，把「这一层**没核**」的原因记进去（不静默 —— 2026-10-05 检讨修：
    原来没给 project_root 或 check_all 导不进来时**静默回空表**，于是真实的「图≠盒」
    会一路掉到 U/UNATTRIBUTED，本该阻塞的 C 层缺陷变成"需人工看图"）。
    """
    out = []
    if not project_root:
        if errs is not None:
            errs.append('C/ASSET-GEOMETRY 未核：调用方没给 project_root → 这一层归因缺失（不静默）')
        return out
    try:
        import check_all as CA
    except Exception as e:                                  # noqa: BLE001
        if errs is not None:
            errs.append('C/ASSET-GEOMETRY 未核：check_all 不可用（%s）→ 这一层归因缺失' % e)
        return out
    w, h = box[2], box[3]
    for fld, ref in CA._ctrl_pic_refs(ctl):
        p = CA._pic_path(project_root, ref)
        if not p:
            out.append('%s → 缺图 %s' % (fld, ref))
            continue
        if ref.lower().endswith('.9.png'):
            continue                                        # 九宫格豁免（拉伸是它的用法）
        try:
            with Image.open(p) as im:
                iw, ih = im.size
        except OSError as e:
            out.append('%s → 读不了 %s（%s）' % (fld, ref, e))
            continue
        if (iw, ih) != (w, h):
            out.append('%s %dx%d ≠ 控件盒 %dx%d' % (fld, iw, ih, w, h))
    return out


def _emit_index(page_json_path, project_root):
    """ui_compile 诊断 → {控件 key: [msg...]}（按 JSON Pointer 的第一段归到控件）。"""
    idx = {}
    try:
        import ui_compile as UC
    except Exception as e:                                  # noqa: BLE001
        return idx, 'ui_compile 不可用（%s）→ 未做字段层归因' % e
    try:
        rep = UC.compile_json(page_json_path, project_root=project_root or None)
    except Exception as e:                                  # noqa: BLE001
        return idx, 'ui_compile 跑不起来（%s）→ 未做字段层归因' % e
    for d in (rep.get('diagnostics') or []):
        if d.get('severity') not in ('fatal', 'error'):
            continue
        seg = (d.get('path') or '').strip('/').split('/')[0]
        idx.setdefault(seg, []).append('[%s] %s' % (d.get('rule'), d.get('msg')))
    return idx, ''


def _frontend_index(report):
    """前端返回体 → {caption: [登记...]}（warnings/downgrades/unrecognized 里的文本按 caption 命中）。"""
    idx = {}
    if not isinstance(report, dict):
        return idx
    texts = []
    for w in (report.get('warnings') or []):
        texts.append(str(w))
    for d in (report.get('downgrades') or []):
        texts.append(json.dumps(d, ensure_ascii=False))
    for u in (report.get('unrecognized') or []):
        texts.append(json.dumps(u, ensure_ascii=False))
    if report.get('imageActions'):
        texts.append(json.dumps(report.get('imageActions'), ensure_ascii=False))
    return texts


def attribute(page_json, render_png, device_png, render_report=None, frontend_report=None,
              project_root='', tol=2, max_ratio=1.0, min_block=8, runtime_caps=(),
              top=None):
    """→ 报告 dict（区域级归因）。判据与 `wysiwyg_diff` 同源（非文字区比例 + 连通块）。"""
    ia = Image.open(render_png).convert('RGB')
    ib = Image.open(device_png).convert('RGB')
    if ia.size != ib.size:
        return {'success': False,
                'error': '尺寸不一致：%s vs %s（先确认渲染分辨率 == 设备分辨率）'
                         % (ia.size, ib.size)}
    W, H = ia.size
    diff = ImageChops.difference(ia, ib)
    px = diff.load()
    with io.open(page_json, encoding='utf-8-sig') as f:
        page = json.load(f)
    ctrls = WD.walk(page)
    # key → 控件本体（归因时按单个控件核对图/盒，见 _asset_mismatch）
    ctl_by_key = {}

    def _collect(n):
        for k, v in (n or {}).items():
            if isinstance(v, dict) and '__' in k:
                ctl_by_key[k] = v
                _collect(v)
            elif isinstance(v, dict):
                _collect(v)
            elif isinstance(v, list):
                for x in v:
                    _collect(x)
    _collect(page)
    blind_t, blind_c = _blind_index(render_report)
    stretch_t, stretch_c = _stretch_index(render_report)
    emit_idx, emit_note = _emit_index(page_json, project_root)
    fe_texts = _frontend_index(frontend_report)
    rcap = set(runtime_caps or ())

    regions, layer_stats = [], {}
    asset_notes = []          # 「C/ASSET-GEOMETRY 这一层没核」的原因（进 rep['notes']，不静默）
    total_bad = 0
    for k, c, (x0, y0, x1, y1), is_text, vis in ctrls:
        if not vis:
            continue
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(W, x1), min(H, y1)
        if x1 <= x0 or y1 <= y0:
            continue
        bad = 0
        for y in range(y0, y1):
            for x in range(x0, x1):
                r, g, b = px[x, y]
                if max(r, g, b) > tol:
                    bad += 1
        total_bad += bad
        if not bad:
            continue
        area = (x1 - x0) * (y1 - y0)
        ratio = 100.0 * bad / max(1, area)
        blk_area, bw, bh, bbox = WD.biggest_block(diff.crop((x0, y0, x1, y1)), tol)
        structural = (bw >= min_block and bh >= min_block and blk_area >= min_block * min_block)
        significant = (bad >= min_block * min_block) or (ratio > max_ratio)
        ctype = k.split('__')[0]
        # 图/盒核对用的盒子 = **json 里声明的 position**，不是裁到画布内的差异矩形。
        # 2026-10-05 检讨修：拿裁过的矩形去比会把「控件伸出画布」误判成 C 层「图≠盒」（假阻塞）；
        # 声明盒拿不到时才退回差异矩形。
        _pos = ctl_by_key.get(k, {}).get('position') or {}
        if all(isinstance(_pos.get(q), int) for q in ('left', 'top', 'width', 'height')):
            abox = (_pos['left'], _pos['top'],
                    _pos['left'] + _pos['width'], _pos['top'] + _pos['height'])
        else:
            abox = (x0, y0, x1, y1)
        _amemo = {}

        def _asset_ev():
            """惰性 + 记忆化：只在真要归因时才读 PNG（一个页面控件很多，别每块都读盘）。"""
            if 'v' not in _amemo:
                _amemo['v'] = _asset_mismatch(ctl_by_key.get(k, {}), abox, project_root,
                                              asset_notes)
            return _amemo['v']

        # ---- 归因（顺序即优先级：能确定的先落，最后才是"不猜"）----
        layer, reason, evidence = 'U/UNATTRIBUTED', '', []
        if k in emit_idx or c in emit_idx:
            layer = 'C/EMIT-FIELDS'
            reason = '该控件在 ui_compile 下有 fatal/error（字段/类型/必填）→ 先改发射层'
            evidence = (emit_idx.get(k) or emit_idx.get(c) or [])[:4]
        elif (c and c in stretch_c) or _asset_ev() or (ctype in stretch_t):
            # 客观缺陷先于"判不了"：图 ≠ 盒是硬规则，渲染器覆不覆盖都得修
            layer = 'C/ASSET-GEOMETRY'
            reason = '图与控件盒不符/缺图 → 资产或字段，先按铁律「图 == 盒」修'
            evidence = ((stretch_c.get(c) or []) + _asset_ev()
                        + (stretch_t.get(ctype) or []))[:4]
            if not (c and c in stretch_c) and not _asset_ev():
                evidence = evidence + ['（类型级兜底：json2img stretched 无 caption，精度有限）']
        elif (c and (c in blind_c or ('%s/%s' % (ctype, c)) in blind_c)) \
                or (ctype in blind_t):
            layer = 'E/RENDERER-BLINDSPOT'
            reason = '渲染器对该控件不覆盖/不校准（json2img unsupported）→ 离线判不了，须真机复验'
            evidence = ((blind_c.get(c) or []) + (blind_t.get(ctype) or []))[:4]
        elif is_text and c not in rcap:
            layer = 'E/FONT-METRICS'
            reason = '文字盒内差异（字形栅格化是模拟层，与 wysiwyg_diff B 段同口径）→ 参考项，不拦'
        elif fe_texts and c and any(c in t for t in fe_texts):
            layer = 'A/FRONTEND-REPORT'
            reason = '前端报告里登记过与该 caption 相关的 warnings/downgrades/unrecognized → 语义在 A 层就丢了'
            evidence = [t[:90] for t in fe_texts if c in t][:3]
        elif c in rcap:
            layer = 'E/FONT-METRICS'
            reason = '运行期文字盒（值由代码灌，json 里没有）→ 不适合拿来判静态一致性'
        regions.append({'key': k, 'caption': c, 'type': ctype,
                        'box': [x0, y0, x1 - x0, y1 - y0], 'bad': bad, 'area': area,
                        'ratioPct': round(ratio, 3), 'structural': bool(structural),
                        'maxBlock': {'w': bw, 'h': bh, 'area': blk_area, 'bbox': bbox},
                        'significant': bool(significant), 'runtimeText': c in rcap,
                        'layer': layer, 'reason': reason, 'evidence': evidence})
        st = layer_stats.setdefault(layer, {'regions': 0, 'badPixels': 0, 'significant': 0})
        st['regions'] += 1
        st['badPixels'] += bad
        st['significant'] += 1 if significant else 0
    regions.sort(key=lambda r: -r['bad'])
    # ⚠️ 2026-10-05 检讨修：判据与汇总**必须先于 `--top` 截断** —— 原来先截断再算
    # `blocking` / `pass` / 百分比，于是 `--top 3` 只要把阻塞区域截掉就能把 FAIL 报成 PASS
    # （而且百分比与 totalBadPixels 分母不一致）。
    blocking = [r for r in regions
                if r['significant'] and (r['layer'] in LAYER_C or r['layer'] in LAYER_U)]
    e_bad = sum(r['bad'] for r in regions if r['layer'] in LAYER_E)
    attributed = sum(r['bad'] for r in regions if r['layer'] not in LAYER_U)
    shown = regions[:top] if top else regions
    rep = {'success': True, 'size': [W, H], 'tol': tol, 'maxRatioPct': max_ratio,
           'minBlock': min_block, 'totalBadPixels': total_bad,
           'regionsTotal': len(regions), 'regionsShown': len(shown),
           'badPixelsInBlindSpots': e_bad,
           'eLayerSharePct': round(100.0 * e_bad / max(1, total_bad), 2),
           'attributedPct': round(100.0 * attributed / max(1, total_bad), 2),
           'layers': layer_stats, 'regions': shown,
           'blocking': [{'key': r['key'], 'caption': r['caption'], 'layer': r['layer'],
                         'ratioPct': r['ratioPct'], 'reason': r['reason']} for r in blocking],
           'pass': not blocking,
           'hint': ('超阈值差异全落在 E 层（渲染器近似/盲区）→ 离线判不了，别改渲染器：'
                    '按 ui-pipeline-spec §4 走真机复验或登记盲区豁免'
                    if not blocking else
                    '有 C 层/未归因的超阈值差异 → 按 regions[].layer 指到的层去修'
                    '（C/* = 发射层与资产；U/* = 需人工看图或补证据）')}
    notes = list(asset_notes)
    if emit_note:
        notes.append(emit_note)
    if notes:
        rep['notes'] = notes
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', required=True, help='页面 json（控件树来源）')
    ap.add_argument('--render', required=True)
    ap.add_argument('--device', required=True)
    ap.add_argument('--render-report', default='', help='json2img --json-report 的产物')
    ap.add_argument('--frontend-report', default='', help='前端返回体（html2json/translate_ui）')
    ap.add_argument('--project', default='')
    ap.add_argument('--tol', type=int, default=2)
    ap.add_argument('--max-ratio', type=float, default=1.0)
    ap.add_argument('--min-block', type=int, default=8)
    ap.add_argument('--runtime-caps', default='')
    ap.add_argument('--top', type=int, default=0)
    ap.add_argument('--json-out', default='')
    a = ap.parse_args()
    rep = attribute(a.json, a.render, a.device,
                    render_report=_load_json(a.render_report),
                    frontend_report=_load_json(a.frontend_report),
                    project_root=a.project, tol=a.tol, max_ratio=a.max_ratio,
                    min_block=a.min_block,
                    runtime_caps=[x.strip() for x in a.runtime_caps.split(',') if x.strip()],
                    top=a.top or None)
    if not rep.get('success'):
        print('[X] %s' % rep.get('error'))
        return 2
    print('== 区域级归因：%s vs %s (%dx%d, tol=%d)'
          % (os.path.basename(a.render), os.path.basename(a.device),
             rep['size'][0], rep['size'][1], a.tol))
    print('   差异像素 %d ｜ E 层（渲染器近似/盲区）占比 %.2f%% ｜ 已归因 %.2f%%'
          % (rep['totalBadPixels'], rep['eLayerSharePct'], rep['attributedPct']))
    for layer, st in sorted(rep['layers'].items()):
        print('   %-24s 区域 %2d（超阈值 %2d）差异像素 %6d' % (layer, st['regions'],
                                                              st['significant'], st['badPixels']))
    print('   ---- 区域 top%d ----' % len(rep['regions']))
    for r in rep['regions'][:20]:
        print('   %-16s %-20s %s,%s %dx%d  超容差 %5d (%5.1f%%)  %s%s'
              % (r['key'], r['caption'], r['box'][0], r['box'][1], r['box'][2], r['box'][3],
                 r['bad'], r['ratioPct'], r['layer'], '  ←结构性' if r['structural'] else ''))
    print('   判据：%s —— %s' % ('PASS' if rep['pass'] else 'FAIL', rep['hint']))
    if a.json_out:
        with io.open(a.json_out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(rep, ensure_ascii=False, indent=1) + '\n')
        print('   报告: %s' % a.json_out)
    return 0 if rep['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
