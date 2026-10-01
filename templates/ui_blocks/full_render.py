#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""整页渲染（展平 scrollwindow）——给人工验收看的「一屏看到全部内容」的证据图。

为什么需要它：`ui_tools/json2img.py` 出的是**真机同尺寸**渲染图（320×240 / 1024×600），
滑动区外的内容被 scrollwindow 裁掉——看渲染图会觉得「下半页整块没了」。
本脚本按**只动几何、不动口径**的方式展平一版 y 方向长图（供人工验收；**不参与 check_all**）：

    整页高 = 标题带 + 内容总高 + 底部固定带
    底部固定带 = 屏高 − min(top of 贴底固定的顶层节点)（底导 + 底栏；没有底导时就是底栏）
    内容子节点上提（坐标 = 内层 window 局部 + scrollwindow.top）

⚠️ **固定带（底导/底栏/弹窗/浮层）保持原屏 y 不变**（与上一批交付的 `main.full.render.png` 口径一致，
`git diff` 除图标外零差异已核对）：所以它们会出现在长图的中段、与下方内容重叠——
看长图时把这两条带当「原屏上的固定层」看即可（真要它们贴到长图底部是另一种口径，必须说清）。

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


def full_page(doc):
    """整页 json（展平 scrollwindow）。返回 (doc, 整页高)；本就无滑动窗口 → 原样返回。"""
    d = json.loads(json.dumps(doc))
    H = int(d['resolution']['height'])
    swkey = next((k for k in d if k.startswith('scrollwindow__')), None)
    if not swkey:
        return d, H
    sw = d[swkey]
    innerkey = next(k for k in sw if k.startswith('window__'))
    inner = sw[innerkey]
    sw_top = int(sw['position']['top'])
    content_h = int(inner['position']['height'])
    tops = [v['position']['top'] for k, v in d.items()
            if isinstance(v, dict) and '__' in k and 'position' in v
            and v['position']['top'] >= H * 0.5]
    bottom_h = H - min(tops) if tops else 0
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
    d['resolution'] = {'width': int(d['resolution']['width']), 'height': full_h}
    d['position']['height'] = full_h
    return d, full_h


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
    full, full_h = full_page(doc)
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
