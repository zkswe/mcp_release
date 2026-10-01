#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""整页渲染（展平 scrollwindow）——给人工验收看的「一屏看到全部内容」的证据图。

为什么需要它：`ui_tools/json2img.py` 出的是**真机同尺寸**渲染图（320×240 / 1024×600），
滑动区外的内容被 scrollwindow 裁掉——看渲染图会觉得「下半页整块没了」。
本脚本按**只动几何、不动口径**的方式展平一版 y 方向长图（供人工验收；**不参与 check_all**）：

    整页高 = 标题带 + 内容总高 + 底部固定带
    底部固定带 = 屏高 − min(top of 贴底固定的顶层节点)（底导 + 底栏；没有底导时就是底栏）
    内容子节点上提（坐标 = 内层 window 局部 + scrollwindow.top）

⚠️ **固定带让位（缺陷 A 修，2026-10-01）**：固定带（底导 / 底栏）**随内容一起下移到长图底部**
（y = 整页高 − 固定带高）——旧口径「保持原屏 y 不变」会把底栏压在长图中段、盖住内容
（钟工看图：「内容区伸进底部固定条，把最后一行盖住」：ButtonRowDeviceCard9 508..568 被
FooterBg12 528..600 盖掉 40px）。让位后二者零相交；位移量 = 滑动行程（内容高 − 视口高）。
让位前后都逐对判 rect 相交（固定带 × 实际渲染出的内容节点），相交 → 报错退出、不出图。

整屏浮层（弹窗 / 提示）仍按原屏 y 画（它们是「浮在屏上的层」，不是贴底固定带）。

口径来源：README §6.2/§6.4 的 `main.full.render.png`（interactive_1024x600 → 1024×1514、
nav_320x240 → 320×792 等，均由本脚本产出）。

用法：
    python templates/ui_blocks/full_render.py <工程根 | ui/main.json> [--page main]
                                              [--out <png>] [--font <ttf>]

产物：默认 <工程>/ui/<page>.full.png；示例目录把它复制成 examples/<示例>/main.full.render.png。
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))                    # tools/FlyThings_mcp_open
UI_TOOLS = os.path.join(os.path.dirname(REPO), 'ui_tools')

sys.stdout.reconfigure(encoding='utf-8')


def _walk(node, ox, oy, band_keys=None, is_band=False, out=None):
    """递归收集 (rect, caption, is_band)。跳过隐藏节点；band_keys 命中的顶层子树 = 固定带。"""
    out = [] if out is None else out
    for k, v in (node or {}).items():
        if not isinstance(v, dict) or '__' not in k or 'position' not in v:
            continue
        b_ = is_band or bool(band_keys and k in band_keys)
        p = v['position']
        l, t = ox + int(p.get('left') or 0), oy + int(p.get('top') or 0)
        w, h = int(p.get('width') or 0), int(p.get('height') or 0)
        if v.get('visible', True) is False or w <= 0 or h <= 0:
            continue
        out.append({'rect': (l, t, l + w, t + h), 'caption': v.get('caption') or k,
                    'band': b_})
        _walk(v, l, t, band_keys, b_, out)
    return out


def assert_bands_clear(doc, meta):
    """自检（缺陷 A）：整合页后，固定带不得与内容节点相交（逐对判 rect，含最后一行/卡片底）。

    相交 → 返回冲突清单（调用方报错退出、**不出图**）。
    整屏浮层（弹窗 / 提示遮罩）不算内容：它们压在固定带上合法（它们本就该盖住一切）。
    """
    W, H_orig = meta['screen_w'], meta['screen_h']
    full_h, band_keys = meta['full_h'], meta.get('band_keys') or []
    rects = _walk(doc, 0, 0, band_keys)
    content, bands = [], []
    for r in rects:
        l, t, rr, b = r['rect']
        if t == 0 and (rr - l) >= W and (b - t) >= H_orig:     # 整屏浮层（弹窗/遮罩）
            continue
        (bands if r['band'] else content).append(r)
    bad = []
    for a in bands:
        for c in content:
            al, at, ar, ab = a['rect']
            cl, ct, cr, cb = c['rect']
            ix, iy = min(ar, cr) - max(al, cl), min(ab, cb) - max(at, ct)
            if ix > 0 and iy > 0:
                bad.append('%s %d,%d..%d,%d ∩ %s %d,%d..%d,%d = %dx%d px'
                           % (c['caption'], cl, ct, cr, cb, a['caption'], al, at, ar, ab, ix, iy))
    return bad


def full_page(doc):
    """整页 json（展平 scrollwindow + 固定带让位）。返回 (doc, 整页高, meta)。"""
    d = json.loads(json.dumps(doc))
    H = int(d['resolution']['height'])
    W = int(d['resolution']['width'])
    swkey = next((k for k in d if k.startswith('scrollwindow__')), None)
    base = {'full_h': H, 'band_top': H, 'band_h': 0, 'new_band_top': H, 'dy': 0,
            'band_keys': [], 'screen_w': W, 'screen_h': H}
    if not swkey:
        return d, H, base
    sw = d[swkey]
    innerkey = next(k for k in sw if k.startswith('window__'))
    inner = sw[innerkey]
    sw_top = int(sw['position']['top'])
    content_h = int(inner['position']['height'])
    band_keys = [k for k, v in d.items()
                 if isinstance(v, dict) and '__' in k and 'position' in v
                 and v['position']['top'] >= H * 0.5]
    band_top = min(int(d[k]['position']['top']) for k in band_keys) if band_keys else H
    bottom_h = H - band_top                              # 底部固定带总高（底导 + 底栏）
    full_h = sw_top + content_h + bottom_h
    for k, v in list(inner.items()):
        if '__' in k:
            v['position']['top'] += sw_top                          # 内层局部 → 整页绝对
            d[k] = v
    del d[swkey]
    for k, v in list(d.items()):                                    # 整屏浮层随长图拉高
        if not (isinstance(v, dict) and 'position' in v and 'text' not in v):
            continue
        if v['position']['top'] == 0 and v['position']['height'] == H:
            v['position']['height'] = full_h                        # 弹窗/浮层的整屏层
    # 固定带让位：贴底固定带随内容下移到长图底部（y = 整页高 − 固定带高）
    new_band_top = full_h - bottom_h
    dy = new_band_top - band_top
    for k in band_keys:
        d[k]['position']['top'] += dy
    d['resolution'] = {'width': int(d['resolution']['width']), 'height': full_h}
    d['position']['height'] = full_h
    return d, full_h, {'full_h': full_h, 'band_top': band_top, 'band_h': bottom_h,
                       'new_band_top': new_band_top, 'dy': dy, 'band_keys': band_keys,
                       'screen_w': W, 'screen_h': H}


def find_font(project_root):
    import glob
    for pat in (os.path.join(project_root or '', 'resources', 'font', '*.ttf'),
                os.path.join(REPO, 'components', 'fonts', 'fonts', 'zkswe-hans-common.ttf')):
        hit = sorted(glob.glob(pat))
        if hit:
            return hit[0]
    return None


def main():
    ap = argparse.ArgumentParser(description='整页渲染（展平 scrollwindow）')
    ap.add_argument('target', help='工程根目录（含 ui/）或 ui/<page>.json 路径')
    ap.add_argument('--page', default='main')
    ap.add_argument('--out', default=None, help='输出 PNG（默认 <工程>/ui/<page>.full.png）')
    ap.add_argument('--font', default=None)
    ap.add_argument('--json-out', default=None,
                    help='展平后的 json 落点（默认**临时写进工程的 ui/ 目录**，渲染完即删——'
                         'json2img 用相对路径解析 images/，不放在工程里会丢底图）')
    a = ap.parse_args()

    t = os.path.abspath(a.target)
    if os.path.isdir(t):
        project_root = t
        json_path = os.path.join(t, 'ui', a.page + '.json')
        if not os.path.isfile(json_path):
            cands = [os.path.join(t, 'ui', d, a.page + '.json')
                     for d in sorted(os.listdir(os.path.join(t, 'ui')))
                     if os.path.isdir(os.path.join(t, 'ui', d))]
            json_path = cands[0] if cands else json_path
        out = a.out or os.path.join(t, 'ui', a.page + '.full.png')
    else:
        json_path = t
        project_root = os.path.dirname(os.path.dirname(t))
        out = a.out or os.path.join(os.path.dirname(t), a.page + '.full.png')

    doc = json.load(open(json_path, encoding='utf-8'))
    full, full_h, meta = full_page(doc)
    bad = assert_bands_clear(full, meta)
    if bad:
        print('  [X] 整页渲染自检失败：固定带与内容相交 %d 对（缺陷 A：底栏/底导盖住内容）——不出图'
              % len(bad))
        for line in sorted(set(bad))[:12]:
            print('      - %s' % line)
        return 4
    if meta['band_h']:
        print('  固定带让位：y %d → %d（%+d px = 滑动行程）｜ 带高 %d ｜ 整页 %d'
              % (meta['band_top'], meta['new_band_top'], meta['dy'], meta['band_h'], full_h))
    else:
        print('  无滑动窗口：固定带保持原屏 y（本页内容不需要展平）')
    # 展平 json 必须与 main.json 同目录：json2img 用相对路径解析 images/*.png，
    # 放到临时目录会让所有底图（卡片/图标/底栏）“缺失”，长图看上去一片灰。
    tmp_json = a.json_out is None
    dst = a.json_out or os.path.join(os.path.dirname(json_path),
                                     '_%s.full.json' % a.page)
    with open(dst, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(full, ensure_ascii=False, indent=2) + '\n')

    font = a.font or find_font(project_root)
    cmd = [sys.executable, os.path.join(UI_TOOLS, 'json2img.py'), dst, '--page', a.page,
           '--out', os.path.abspath(out), '--report']
    if font:
        cmd += ['--font', font]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                           errors='replace')
    finally:
        if tmp_json:
            try:
                os.remove(dst)                                  # 不给 check_all 留一页
            except OSError as ex:                              # 清理失败不致命，但不静默
                sys.stderr.write('[warn] 清理临时页失败 %s：%s\n' % (dst, ex))
    if r.returncode != 0:
        print('  [X] json2img 失败 exit=%d\n%s' % (r.returncode, (r.stderr or r.stdout)[-800:]))
        return r.returncode
    log = (r.stdout or '')
    if '[缺失图片' in log:
        print('  [X] 展平渲染缺底图（images/ 未解析到）——请检查 json 是否与 main.json 同目录')
        print('\n'.join(l for l in log.splitlines() if '缺失' in l or 'pic' in l)[:600])
        return 3
    from PIL import Image
    im = Image.open(out)
    print('  整页渲染 %s %dx%d（原屏 %dx%d；内容被 scrollwindow 裁掉的都分已展平）'
          % (os.path.basename(out), im.size[0], im.size[1],
             doc['resolution']['width'], doc['resolution']['height']))
    print('  展平 json 临时落盘 → %s（已删）' % dst if tmp_json else '  展平 json → %s' % dst)
    return 0


if __name__ == '__main__':
    sys.exit(main())
