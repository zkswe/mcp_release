# -*- coding: utf-8 -*-
"""zero_color_audit.py — **颜色值 0（不透明黑）误用**审计（0 token，有退出码）。

背景（2026-09-20 M6：「控件/切图黑底」；根因 = M1 起 json 里把「透明」写成 0）：本平台颜色语义：**0 = 不透明黑（0xFF000000）**；**透明标记是 -1（0xFFFFFFFF）**。
历史上把 0 当「透明/缺省」写进 `backgroundColor` / `bgColorTab.color0` / `textBgColor`，
真机就渲染成黑块（ControlTest-F133 实测：checkbox 行底、listview 行、digitalclock、
  pointer、circlebar 一共 83k 近黑像素，其中 61k 是这类误用）。

判据（三源，见 references/kb/image-gen-standard.md §7.6）：
  · 官方基准 A：projects/SampleUI-New/ui/1024x600（42 json，新 IDE 全量序列化）
  · 官方基准 B：官方 Demo 集合 `basedemo-new_z20_1024_600`（
    `<项目>/ui/fui.exe unpack` 反解）：checkbox/radiogroup/seekbar/digitalclock/pointer/
    circlebar/listview/painter/slidetext/diagram/textview = **-1**；
    videoview 2/2、cameraview 1/1 = **0**（视频/摄像头面必须有实黑底）；
    listview.item.bgColorTab.color0 = **-1**。
  · 令牌基准：工程 DESIGN.md 颜色令牌表（要实底就写令牌色，不写 0）。

判定：
  · 命中 `backgroundColor`/`*color*` 字段且值 == 0，未登记豁免 → **DEFECT**（--fail 退出码 1）
  · 命中且被 `tools/qa/zero_color_allow.json` 规则命中 → **EXEMPT**（打印登记理由，不判 FAIL）
  · 无命中 → **CLEAN**

用法：
  python tools/qa/zero_color_audit.py <项目根>            # 扫 <项目根>/ui/*.json
  python tools/qa/zero_color_audit.py <样例目录>          # 目录下每个含 ui/ 的子目录算一个样例工程
  python tools/qa/zero_color_audit.py <目标> --fail       # DEFECT 时退出码 1（check_all #24 用）
  python tools/qa/zero_color_audit.py <目标> --json out.json
"""
import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ALLOW = os.path.join(HERE, 'zero_color_allow.json')

# 含 color 但不是「颜色值」的键（显式排除，避免误报）
NOT_COLOR_KEYS = ('colortab', 'bgcolortab', 'colorindex', 'colortype', 'colorformat')


def is_color_field(k, v):
    """字段名含 color（或 backgroundColor）且值是可比较的整数 → 视为颜色值字段。"""
    if isinstance(v, bool) or not isinstance(v, int):
        return False
    lk = k.lower()
    if lk in NOT_COLOR_KEYS:
        return False
    return ('color' in lk)


def ctrl_type(node_key):
    """节点键名 → 控件类型（videoview__1 → videoview）。"""
    return node_key.split('__')[0] if '__' in node_key else node_key


def load_allow():
    if not os.path.isfile(ALLOW):
        return {'rules': [], 'exact': [], 'track_allow': []}
    try:
        return json.load(io.open(ALLOW, encoding='utf-8'))
    except Exception as e:                                   # noqa: BLE001
        print('[WARN] 豁免表读取失败 %s：%s' % (ALLOW, e))
        return {'rules': [], 'exact': [], 'track_allow': []}


# ---- 第二判据：「切图被当成不透明填充」（seekbar 轨道/填充图）----
# 背景（M6 原话里的「切图黑底/白杠」）：seekbar 的 backgroundPic（轨道）本该是
# 「凹槽」——令牌 track-on-dark #3C3C3E；实际 ct_track.png 被出成**不透明白条**
# （294x18，不透明占比 98.1%，RGB 全 255），真机观感就是一条白杠而不是槽。
# 判据（对 seekbar 的 backgroundPic / progressPic）：
#   · 不透明占比 ≥ 0.95 且平均亮度 ≥ 200 → DEFECT（近白不透明整条 = 白杠）
#   · 不透明占比 ≥ 0.95 且平均亮度 ≤ 12  → DEFECT（近黑不透明整条 = 黑杠/黑底）
#   · 其余 → CLEAN；确实要纯白/纯黑整条（浅色主题等）→ 在 zero_color_allow.json 的
#     track_allow 里登记（file/pic/reason）。阈值出处：实测改前 ct_track 98.1%/255、
#改后令牌 97.7%/#3C3C3E(亮度 60) 与 accent ct_fill(亮度 109) 均不命中。
TRACK_OPAQUE_MIN = 0.95
TRACK_LUM_WHITE = 200.0
TRACK_LUM_BLACK = 12.0


def _lum(rgb):
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def check_track_pics(root, fname, d, allow, rows):
    """扫 seekbar 的轨道/填充图：近白/近黑的不透明整条 → DEFECT（切图当不透明填充）。"""
    try:
        from PIL import Image
        import numpy as np
    except Exception as e:                                   # noqa: BLE001
        print('  [NOTE] 轨道/填充图判据跳过（缺 PIL/numpy）：%s' % e)
        return
    imgdir = os.path.join(root, 'resources', 'images')
    if not os.path.isdir(imgdir):
        return
    pics = []

    def walk(o, jpath=''):
        if isinstance(o, dict):
            for k, v in o.items():
                if k.startswith('seekbar__') and isinstance(v, dict):
                    for fld in ('backgroundPic', 'progressPic'):
                        p = v.get(fld)
                        if isinstance(p, str) and p:
                            pics.append((jpath + '/' + k, fld, p))
                walk(v, jpath + '/' + k)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, '%s[%d]' % (jpath, i))

    walk(d)
    for jpath, fld, pic in pics:
        ap = os.path.join(root, pic.replace('/', os.sep)) if pic.startswith('resources')\
            else os.path.join(root, 'resources', pic.replace('/', os.sep))
        if not os.path.isfile(ap):
            continue
        try:
            im = Image.open(ap).convert('RGBA')
            arr = np.asarray(im).astype('float32')
        except Exception as e:                               # noqa: BLE001
            print('  [NOTE] %s 读图失败，跳过轨道/填充判据：%s' % (pic, e))
            continue
        a = arr[:, :, 3]
        op = float((a > 250).mean())
        if op < TRACK_OPAQUE_MIN:
            continue
        mask = a > 250
        rgb = [float(arr[:, :, i][mask].mean()) if mask.any() else 0.0 for i in range(3)]
        lum = _lum(rgb)
        name = '%s#%s' % (fname, jpath + '/' + fld)
        allowhit = None
        for r in allow.get('track_allow', []):
            if r.get('pic') in (None, '*', pic):
                allowhit = r
                break
        if allowhit is not None:
            rows.append({'name': name, 'verdict': 'EXEMPT', 'file': fname,
                         'path': jpath + '/' + fld, 'field': fld, 'value': pic,
                         'reason': '已登记豁免（轨道/填充图）：%s' % allowhit.get('reason', '')})
        elif lum >= TRACK_LUM_WHITE:
            rows.append({'name': name, 'verdict': 'DEFECT', 'file': fname,
                         'path': jpath + '/' + fld, 'field': fld, 'value': pic,
                         'reason': '切图被当成不透明填充：%s 不透明占比 %.1f%%、平均亮度 %.0f（近白）'
                                   '→ 观感是一条白杠。轨道应是令牌 track-on-dark #3C3C3E、'
                                   '填充应是 accent #0A84FF（DESIGN.md §2）'
                                   % (pic, op * 100, lum)})
        elif lum <= TRACK_LUM_BLACK:
            rows.append({'name': name, 'verdict': 'DEFECT', 'file': fname,
                         'path': jpath + '/' + fld, 'field': fld, 'value': pic,
                         'reason': '切图被当成不透明填充：%s 不透明占比 %.1f%%、平均亮度 %.0f（近黑）'
                                   '→ 整条黑杠/黑底；若不是有意设计请在 DESIGN.md 登记'
                                   % (pic, op * 100, lum)})


def match_allow(allow, fname, path, ctype, field, value):
    """命中豁免规则 → (reason, evidence) 或 None。"""
    for r in allow.get('exact', []):
        if (r.get('file') in (None, fname) and r.get('path') == path
                and r.get('field') in (None, field) and r.get('value', 0) == value):
            return r.get('reason', ''), r.get('evidence', '')
    for r in allow.get('rules', []):
        if r.get('control') not in (None, '*', ctype):
            continue
        if r.get('field') not in (None, '*', field):
            continue
        if r.get('value', 0) != value:
            continue
        return r.get('reason', ''), r.get('evidence', '')
    return None


def scan_json(path, fname, allow, rows, prefix=''):
    """扫单个 json：把命中项 append 进 rows（DEFECT / EXEMPT）。"""
    try:
        d = json.load(io.open(path, encoding='utf-8'))
    except Exception as e:                                   # noqa: BLE001
        rows.append({'name': '%s%s' % (prefix, fname), 'verdict': 'ERROR',
                     'reason': 'json 解析失败：%s' % e, 'file': fname})
        return

    def walk(o, jpath=''):
        if isinstance(o, dict):
            for k, v in o.items():
                if is_color_field(k, v) and v == 0:
                    full = (jpath + '/' + k).lstrip('/')
                    parts = full.split('/')
                    own = [s for s in parts[:-1]
                           if not s.endswith('Tab') and not s.startswith('color')
                           and not (s.startswith('subItem[') or s in ('item', 'radiobuttons'))]
                    ct = ctrl_type(own[-1]) if own else ''
                    hit = match_allow(allow, fname, full, ct, k, v)
                    if hit:
                        rows.append({'name': '%s%s#%s' % (prefix, fname, full),
                                     'verdict': 'EXEMPT', 'file': fname, 'path': full,
                                     'field': k, 'value': v, 'control': ct,
                                     'reason': '已登记豁免：%s｜依据 %s' % (hit[0], hit[1])})
                    else:
                        rows.append({'name': '%s%s#%s' % (prefix, fname, full),
                                     'verdict': 'DEFECT', 'file': fname, 'path': full,
                                     'field': k, 'value': v, 'control': ct,
                                     'reason': '颜色值 0 = **不透明黑**（不是透明）；此处应为 -1（透明）'
                                               '或 DESIGN.md 令牌色。修法：'
                                               '① 底由下层/图片承担 → -1；② 要实底 → 写令牌色'
                                               '（如 accent 689407）；③ 确实要黑（视频/摄像头面）→'
                                               '在 tools/qa/zero_color_allow.json 登记理由'})
                walk(v, (jpath + '/' + k))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, '%s[%d]' % (jpath, i))

    walk(d)


def scan_project(root, allow, rows, prefix=''):
    ui = os.path.join(root, 'ui')
    n = 0
    for f in sorted(os.listdir(ui)):
        if f.endswith('.json'):
            fp = os.path.join(ui, f)
            scan_json(fp, f, allow, rows, prefix)
            n += 1
            try:
                check_track_pics(root, f, json.load(io.open(fp, encoding='utf-8')), allow, rows)
            except Exception as e:                           # noqa: BLE001
                print('  [NOTE] %s 轨道/填充图判据异常（不静默）：%s' % (f, e))
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('target')
    ap.add_argument('--fail', action='store_true', help='有 DEFECT 时退出码 1')
    ap.add_argument('--json', dest='jsonp', default='')
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    allow = load_allow()
    rows = []
    target = os.path.abspath(a.target)
    if os.path.isdir(os.path.join(target, 'ui')):
        n = scan_project(target, allow, rows)
        scan_mode = 'ui/*.json（%d 个）' % n
    else:
        subs = [d for d in sorted(os.listdir(target))
                if os.path.isdir(os.path.join(target, d, 'ui'))]
        scan_mode = '%d 个样例工程' % len(subs)
        for d in subs:
            sub, subrows = [], []
            scan_project(os.path.join(target, d), allow, sub)
            verdict = 'CLEAN'
            for r in sub:
                if r['verdict'] == 'DEFECT':
                    verdict = 'DEFECT'
                    break
                verdict = 'EXEMPT'
            subrows.append({'name': d, 'verdict': verdict,
                            'reason': '｜'.join(
                                '%s=%s → %s%s' % (r['path'], r['value'], r['verdict'],
                                                  ('：' + r['reason'][:80]) if r.get('reason') else '')
                                for r in sub) or '无 0 值颜色字段',
                            'findings': sub})
            rows.extend(subrows)
    if not rows:
        rows.append({'name': '（无 0 值颜色字段）', 'verdict': 'CLEAN', 'reason': '全部为 -1/令牌色'})

    defect = [r for r in rows if r['verdict'] == 'DEFECT']
    exempt = [r for r in rows if r['verdict'] == 'EXEMPT']
    error = [r for r in rows if r['verdict'] == 'ERROR']
    clean = [r for r in rows if r['verdict'] == 'CLEAN']
    print('zero_color_audit  target=%s扫描=%s' % (target, scan_mode))
    for r in defect:
        print('  [DEFECT] %s' % r['name'])
        print('           %s' % r['reason'])
    for r in exempt:
        print('  [EXEMPT] %s  ← %s' % (r['name'], r['reason'][:150]))
    for r in error:
        print('  [ERROR]  %s  %s' % (r['name'], r['reason']))
    for r in clean:
        print('  [CLEAN]  %s  %s' % (r['name'], r['reason']))
    print('汇总：DEFECT %d / EXEMPT %d / ERROR %d / CLEAN %d'
          % (len(defect), len(exempt), len(error), len(clean)))
    if a.jsonp:
        io.open(a.jsonp, 'w', encoding='utf-8').write(
            json.dumps(rows, ensure_ascii=False, indent=1))
    if a.fail and (defect or error):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
