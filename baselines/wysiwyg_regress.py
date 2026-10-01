#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wysiwyg_regress.py —— 真机基线库 · 离线回归（0 token，本地算法）

回答一个问题：**改了布局之后，设备上看起来还一样吗？** —— 不用再上机。

对 `baselines/<集合>/manifest.json` 里的每条真机基线：
  1) 按该条对应的工程 `ui/<page>.json` 用 `ui_tools/json2img.py` 离线渲染（`--scale 1`，引擎等价）
  2) 用 `ui_tools/wysiwyg_diff.py` 比对「离线渲染 vs 真机基线截图」
     （排除运行期文字盒；`ignoreRegions` 的运行期生成区两边同色置空）
  3) 打印逐条明细（wysiwyg_diff 原文） + 末尾汇总表（一致率 / 结构块 / 结果）

判据与 `wysiwyg_diff` 同源：**非文字区超容差 ≤ --max-ratio 且无 ≥ --min-block 的连通差异块**。

「运行期状态」按 manifest 复现（否则静态 json ≠ 设备上的样子，必假 FAIL）：
  · `scrollY`           滚动容器内容上移该像素（= 滚到该位置）
  · `visibleOverrides`  按 caption 覆盖 visible（= 运行期的显示/隐藏，如 HA 模式显示二维码块/隐藏 IP 行）
  · `ignoreRegions`     运行期生成内容（二维码控件等）两边同色置空，不比
三类都写进临时 json，且**渲染与 wysiwyg_diff 用同一份**（否则文字盒错位 → 假结构块）。

用法（工作目录任意，脚本自己定位仓库根）：
  python tools/FlyThings_mcp_open/baselines/wysiwyg_regress.py                # 跑默认集合全部条目
  python tools/FlyThings_mcp_open/baselines/wysiwyg_regress.py --only wall,home
  python tools/FlyThings_mcp_open/baselines/wysiwyg_regress.py --json temp/regress.json
  python tools/FlyThings_mcp_open/baselines/wysiwyg_regress.py --set z20_480x480

重新取基线（要上机；设备串口用 --device 或环境变量 FLYTHINGS_TEST_DEVICE 传，**不落盘设备 IP**）：
  python .../wysiwyg_regress.py --update --only wall --device <serial|IP>:5555
  （--update 只重抓指定条目：先回到主页 → 按 manifest 的 capture.steps 走 → 抓屏覆盖基线 →
    立刻跑一次该条的回归当自检；`capture.from != home` 的条目要加 --force 才动）

退出码：0 = 全部 PASS / 1 = 有 FAIL / 2 = 环境或参数错误。
"""
import argparse
import copy
import datetime
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))            # .../baselines
MCP = os.path.dirname(HERE)                                  # .../FlyThings_mcp_open
REPO = os.path.dirname(os.path.dirname(MCP))                 # 仓库/工作区根
DEFAULT_SET = 'z20_480x480'
MASK_COLOR = (0, 0, 0)                                       # 排除区两边同色（不参与像素判据）


def find_ui_tools(explicit=''):
    """ui_tools 目录：显式 > 本包内（<MCP>/ui_tools） > 工作区（<REPO>/tools/ui_tools）。"""
    cands = [explicit] if explicit else []
    cands += [os.path.join(MCP, 'ui_tools'), os.path.join(REPO, 'tools', 'ui_tools')]
    for c in cands:
        if c and os.path.isfile(os.path.join(c, 'json2img.py')):
            return os.path.abspath(c)
    return ''


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for blk in iter(lambda: f.read(1 << 20), b''):
            h.update(blk)
    return h.hexdigest()


def rel(p):
    try:
        return os.path.relpath(p, REPO).replace('\\', '/')
    except ValueError:
        return p.replace('\\', '/')


def resolve_set_dir(a):
    """→ 基线集合目录（含 manifest.json）。--set 支持：绝对路径 / 仓库相对 / 本目录相对 / 集合名。"""
    if a.set_dir:
        cands = [a.set_dir] if os.path.isabs(a.set_dir) else [
            os.path.join(HERE, a.set_dir), os.path.abspath(a.set_dir),
            os.path.join(REPO, a.set_dir)]
        for d in cands:
            if os.path.isfile(os.path.join(d, 'manifest.json')):
                return os.path.abspath(d)
        raise SystemExit('[X] 这些位置都没有 manifest.json：%s' % ' ; '.join(cands))
    if os.path.isfile(os.path.join(HERE, 'manifest.json')):
        return HERE
    sets = sorted(n for n in os.listdir(HERE)
                  if os.path.isfile(os.path.join(HERE, n, 'manifest.json')))
    if not sets:
        raise SystemExit('[X] %s 下没有任何基线集合（缺 manifest.json）' % HERE)
    pick = DEFAULT_SET if DEFAULT_SET in sets else sets[0]
    return os.path.join(HERE, pick)


# ---------------------------------------------------------------------------
# 滚动：把「内容容器」上移 scrollY（= 运行期滚到该位置时的静态布局）
# ---------------------------------------------------------------------------
CLIP_KINDS = ('scrollwindow', 'pagewindow', 'slidewindow')


def apply_visible(doc, ov):
    """按 caption 覆盖 `visible`（= 复现运行期的显示/隐藏状态，例如 HA 模式下
    显示二维码块、隐藏主机 IP 行）。→ (命中的 caption 列表, 未命中的 caption 列表)。"""
    seen = set()

    def rec(n):
        for k, v in list(n.items()):
            if not isinstance(v, dict) or '__' not in k:
                continue
            cap = v.get('caption')
            if cap in ov:
                v['visible'] = bool(ov[cap])
                seen.add(cap)
            rec(v)
    rec(doc)
    return sorted(seen), sorted(set(ov) - seen)


def apply_scroll(doc, scroll_y):
    """→ (新 doc, 被上移的容器数)。内容容器 = <裁剪容器> 下高度大于视口的 window__* 子节点。"""
    doc2 = copy.deepcopy(doc)
    moved = []

    def rec(node, path):
        for k, v in list(node.items()):
            if not isinstance(v, dict) or '__' not in k or k.split('__')[0] not in CLIP_KINDS:
                continue
            vh = (v.get('position') or {}).get('height') or 0
            for ck, cv in v.items():
                if not isinstance(cv, dict) or '__' not in ck or ck.split('__')[0] != 'window':
                    continue
                cp = cv.setdefault('position', {})
                if (cp.get('height') or 0) > vh:
                    cp['top'] = (cp.get('top') or 0) - scroll_y
                    moved.append(path + '/' + k + '/' + ck)
            rec(v, path + '/' + k)
    rec(doc2, '')
    return doc2, moved


# ---------------------------------------------------------------------------
# 渲染 / 比对
# ---------------------------------------------------------------------------
def prepare_json(entry, project, tmpdir):
    """→ (渲染+比对用的 json 路径, 状态说明)。

    「运行期状态」两类（都写进 manifest，可复现）：
      · scrollY         —— 滚动容器内容上移该像素（复现滚到某位置）
      · visibleOverrides —— 按 caption 覆盖 visible（复现运行期的显示/隐藏）
    有状态改动时落一份临时 json：**渲染与 wysiwyg_diff 用同一份**，否则比对用的
    文字盒/控件盒位置会与渲染图错位（踩过：滚动页的 mask 留在未滚动坐标上）。"""
    page = entry['page']
    src = os.path.join(project, 'ui', page + '.json')
    if not os.path.isfile(src):
        raise RuntimeError('找不到布局 json：%s' % rel(src))
    scroll_y = int(entry.get('scrollY') or 0)
    ov = entry.get('visibleOverrides') or {}
    if not scroll_y and not ov:
        return src, ''
    doc = json.load(open(src, encoding='utf-8'))
    notes = []
    if scroll_y:
        doc, moved = apply_scroll(doc, scroll_y)
        if not moved:
            raise RuntimeError('%s 没有可上移的滚动内容容器（scrollY=%d 无法套用）' % (page, scroll_y))
        notes.append('scrollY=%d (%d 个内容容器)' % (scroll_y, len(moved)))
    if ov:
        hit, miss = apply_visible(doc, ov)
        if miss:
            raise RuntimeError('visibleOverrides 里这些 caption 在 %s.json 里找不到：%s'
                               % (page, ','.join(miss)))
        notes.append('visibleOverrides=%d 项' % len(hit))
    jp = os.path.join(tmpdir, entry['name'] + '.state.json')
    json.dump(doc, open(jp, 'w', encoding='utf-8'), ensure_ascii=False)
    return jp, '；'.join(notes)


def render_entry(entry, jp, project, tmpdir, scale, ui_tools):
    """按 jp 渲染（scale=1）→ 返回 (png, 渲染报告 dict)。"""
    sys.path.insert(0, ui_tools)
    import json2img                                          # noqa: E402（单一实现，不复制逻辑）
    out = os.path.join(tmpdir, entry['name'] + '.render.png')
    rep = json2img.Report()
    info = json2img.render_one(project, jp, out, scale=scale, report=rep, verbose=False)
    r = rep.as_dict()
    return out, {'size': list(info['size']), 'unsupported': r['unsupported'],
                 'missing_assets': r['missing_assets'], 'stretched': len(r['stretched'])}


def mask_regions(src_png, regions, out_png):
    """把排除区（运行期生成内容）在图上涂成 MASK_COLOR —— 渲染图与真机图**两边同色**，
    于是这些像素对判据贡献 0（等价于「该区域不比」）。"""
    from PIL import Image
    im = Image.open(src_png).convert('RGB')
    W, H = im.size
    for (x, y, w, h) in regions:
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(W, int(x) + int(w)), min(H, int(y) + int(h))
        if x1 > x0 and y1 > y0:
            im.paste(MASK_COLOR, (x0, y0, x1, y1))
    im.save(out_png)
    return out_png


def run_diff(ui_tools, render_png, device_png, page_json, project, tmpdir, name, a):
    """子进程调 wysiwyg_diff（单一实现）→ (原文 stdout, 结果 dict)。"""
    out_json = os.path.join(tmpdir, name + '.diff.json')
    cmd = [sys.executable, os.path.join(ui_tools, 'wysiwyg_diff.py'),
           render_png, device_png, page_json,
           '--tol', str(a.tol), '--max-ratio', str(a.max_ratio),
           '--min-block', str(a.min_block), '--top', str(a.top),
           '--project', project, '--json', out_json]
    if a.runtime_caps:
        cmd += ['--runtime-caps', a.runtime_caps]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800)
    text = p.stdout.decode('utf-8', 'replace')
    res = {}
    if os.path.isfile(out_json):
        try:
            res = json.load(open(out_json, encoding='utf-8'))
        except ValueError as ex:                              # 报告坏了要吭声，不静默
            sys.stderr.write('[warn] 读不了 %s：%s\n' % (out_json, ex))
    res['exitCode'] = p.returncode
    res['raw'] = text
    return text, res


# ---------------------------------------------------------------------------
# 上机重取基线（--update）
# ---------------------------------------------------------------------------
def need_device(a):
    dev = a.device or os.environ.get('FLYTHINGS_TEST_DEVICE', '')
    if dev:
        return dev
    raise SystemExit('[X] --update 需要设备串口：--device <serial|IP>:5555 或环境变量 '
                     'FLYTHINGS_TEST_DEVICE（设备 IP 不落盘进仓库文件）')


def prep_touch(a, ui_tools):
    """把本包 bin_tools/<平台>/touch 推到设备（自动扫节点判协议）。→ (adb, touch_remote)"""
    sys.path.insert(0, MCP)
    import adb_tools                                          # noqa: E402（单一实现）
    adb = adb_tools.resolve_adb()
    if not adb:
        raise SystemExit('[X] 找不到 adb（可放环境变量 ADB 或装到 PATH）')
    plat = a.platform
    local = os.path.join(MCP, 'bin_tools', plat, 'touch')
    if not os.path.isfile(local):
        raise SystemExit('[X] 缺触摸注入工具：%s' % rel(local))
    remote = '/tmp/bsl_touch'
    rc, out, err = adb_tools.push(adb, a.device_serial, local, remote, timeout=120)
    if rc != 0:
        raise SystemExit('[X] push touch 失败：%s %s' % (out.strip(), err.strip()))
    adb_tools.sh(adb, a.device_serial, 'chmod 777 ' + remote)
    return adb, remote


def dev_sh(adb, serial, cmd, ui_tools):
    sys.path.insert(0, MCP)
    import adb_tools
    return adb_tools.sh(adb, serial, cmd)


def capture_now(device, out, ui_tools):
    sys.path.insert(0, ui_tools)
    import device_screenshot                                  # noqa: E402（单一实现）
    r = device_screenshot.capture(device=device, out=out)
    if not r.get('success'):
        raise SystemExit('[X] 抓屏失败：%s' % json.dumps(r, ensure_ascii=False)[:400])
    return r


def quick_same(a_png, b_png, tol=2):
    """两张图有多少比例的像素在容差内（用于「现在是不是停在主页」这类粗判）。"""
    from PIL import Image, ImageChops
    ia = Image.open(a_png).convert('RGB')
    ib = Image.open(b_png).convert('RGB')
    if ia.size != ib.size:
        return 0.0
    d = ImageChops.difference(ia, ib)
    W, H = ia.size
    try:
        import numpy as np                                     # numpy 已随 ui_diff 依赖进来
        bad = int((np.asarray(d, dtype=np.int16).max(axis=2) > tol).sum())
    except ImportError:
        raw = d.tobytes()                                      # 无 numpy：逐像素取 max（不用已弃用的 getdata）
        bad = sum(1 for i in range(0, len(raw), 3) if max(raw[i], raw[i + 1], raw[i + 2]) > tol)
    return 1.0 - bad / float(W * H)


def update_entry(entry, set_dir, project, adb, touch, a, ui_tools, home_png):
    """重抓一条：回主页 → 走 capture.steps → 抓屏覆盖基线。"""
    cap = entry.get('capture') or {}
    if cap.get('from') != 'home' and not a.force:
        print('  [skip] %s：capture.from=%s 不是 home（要重抓加 --force 并人工把设备停到该页）'
              % (entry['name'], cap.get('from') or '?'))
        return False
    if cap.get('from') == 'home':
        for _ in range(7):                                    # 主页右上角不是按钮 → 多点无害
            dev_sh(adb, a.device_serial, '%s tap 417 32' % touch, ui_tools)
            import time
            time.sleep(0.7)
        probe = os.path.join(set_dir, '_probe_home.png')
        capture_now(a.device_serial, probe, ui_tools)
        if home_png and os.path.isfile(home_png):
            r = quick_same(probe, home_png)
            print('  [nav] 回主页自检：与 home 基线一致率 %.2f%%%s'
                  % (r * 100, '' if r > 0.98 else '  ← ⚠ 可能没回到主页，步骤结果存疑'))
        os.remove(probe)
    for step in cap.get('steps') or []:
        parts = step.split()
        act = parts[0]
        if act == 'wait':
            import time
            time.sleep(float(parts[1]))
            continue
        dev_sh(adb, a.device_serial, '%s %s' % (touch, step), ui_tools)
        import time
        time.sleep(1.5)
    out = os.path.join(set_dir, entry['file'])
    r = capture_now(a.device_serial, out, ui_tools)
    entry['capturedAt'] = datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
    entry['width'], entry['height'] = r['width'], r['height']
    entry['md5'] = md5(out)
    print('  [cap] %s ← %s（%dx%d, md5 %s…）'
          % (entry['file'], r.get('source', 'device'), r['width'], r['height'], entry['md5'][:12]))
    return True


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description='真机基线库 · 离线所见即所得回归')
    ap.add_argument('--set', dest='set_dir', default='', help='基线集合名或目录（默认 %s）' % DEFAULT_SET)
    ap.add_argument('--only', default='', help='只跑/只更新这些条目（逗号分隔 name）')
    ap.add_argument('--update', action='store_true', help='上机重抓基线（默认只抓 --only 指定的条目）')
    ap.add_argument('--force', action='store_true', help='--update 时允许动 capture.from != home 的条目')
    ap.add_argument('--device', default='', help='设备串口（--update 用；也可用环境变量 FLYTHINGS_TEST_DEVICE）')
    ap.add_argument('--platform', default='', help='触摸工具平台目录名（默认取 manifest.device.platform 小写）')
    ap.add_argument('--uitools', default='', help='ui_tools 目录（默认本包内 → 工作区）')
    ap.add_argument('--project', default='', help='覆盖工程根（默认 manifest.project.root）')
    ap.add_argument('--scale', type=int, default=1, help='渲染放大倍数（判据口径固定 1）')
    ap.add_argument('--tol', type=int, default=2, help='像素容差（默认 2）')
    ap.add_argument('--max-ratio', type=float, default=1.0, help='非文字区超容差上限 %%（默认 1.0）')
    ap.add_argument('--min-block', type=int, default=8, help='结构性差异块最小边长（默认 8）')
    ap.add_argument('--top', type=int, default=8, help='逐控件归因条数（默认 8）')
    ap.add_argument('--runtime-caps', default='', help='额外指定运行期文字控件 caption（逗号分隔）')
    ap.add_argument('--json', dest='json_out', default='', help='汇总结果写 json')
    ap.add_argument('--quiet', action='store_true', help='不打逐条 diff 原文（只留汇总表）')
    ap.add_argument('--keep-temp', action='store_true', help='保留 temp/ 下的渲染中间产物')
    a = ap.parse_args()

    ui_tools = find_ui_tools(a.uitools)
    if not ui_tools:
        raise SystemExit('[X] 找不到 ui_tools（缺 json2img.py / wysiwyg_diff.py）')

    set_dir = resolve_set_dir(a)
    man = json.load(open(os.path.join(set_dir, 'manifest.json'), encoding='utf-8'))
    project = a.project or os.path.join(REPO, man['project']['root'])
    project = os.path.abspath(project)

    only = [x.strip() for x in a.only.split(',') if x.strip()]
    entries = [e for e in man['entries'] if not only or e['name'] in only]
    if only:
        miss = [n for n in only if n not in [e['name'] for e in man['entries']]]
        if miss:
            raise SystemExit('[X] manifest 里没有这些条目：%s' % ','.join(miss))
    if not entries:
        raise SystemExit('[X] 没有可跑的条目（--only %s）' % a.only)

    a.device_serial = ''
    if a.update:
        a.device_serial = need_device(a)
        if not a.platform:
            a.platform = (man.get('device', {}).get('platform') or 'z20').lower()

    tmpdir = os.path.join(REPO, 'temp', 'baseline_render', os.path.basename(set_dir))
    os.makedirs(tmpdir, exist_ok=True)

    print('=' * 92)
    print('真机基线离线回归   set=%s   条目=%d   渲染=json2img(--scale %d)   判据=wysiwyg_diff'
          % (os.path.basename(set_dir), len(entries), a.scale))
    print('  工程=%s   ui_tools=%s' % (rel(project), rel(ui_tools)))
    print('  设备基线：%s（%s / %s / easyui %s）'
          % (man.get('device', {}).get('model', '?'), man.get('device', {}).get('platform', '?'),
             man.get('device', {}).get('resolution', '?'), man.get('device', {}).get('easyuiVersion', '?')))
    print('  临时目录=%s' % rel(tmpdir))
    print('=' * 92)

    adb = touch = None
    if a.update:
        adb, touch = prep_touch(a, ui_tools)
        home_png = ''
        for e in man['entries']:
            if e['name'] == 'home':
                home_png = os.path.join(set_dir, e['file'])
        for e in entries:
            print('--- 重取 %s ---' % e['name'])
            update_entry(e, set_dir, project, adb, touch, a, ui_tools, home_png)
        json.dump(man, open(os.path.join(set_dir, 'manifest.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=2)
        print('[manifest 已更新] %s' % rel(os.path.join(set_dir, 'manifest.json')))

    rows, results = [], []
    for i, e in enumerate(entries, 1):
        name = e['name']
        dev_png = os.path.join(set_dir, e['file'])
        print('\n[%d/%d] %s  page=%s  %s' % (i, len(entries), name, e['page'], rel(dev_png)))
        if not os.path.isfile(dev_png):
            print('  [X] 基线图不存在：%s' % rel(dev_png))
            results.append({'name': name, 'pass': False, 'error': 'baseline-missing'})
            rows.append((name, e['page'], '-', '-', '-', 'MISSING'))
            continue
        try:
            use_json, state_note = prepare_json(e, project, tmpdir)
            render_png, rinfo = render_entry(e, use_json, project, tmpdir, a.scale, ui_tools)
        except Exception as ex:                               # 渲染失败要显式失败，不静默
            print('  [X] 渲染失败：%r' % ex)
            results.append({'name': name, 'pass': False, 'error': 'render: %r' % ex})
            rows.append((name, e['page'], '-', '-', '-', 'RENDER-FAIL'))
            continue

        dev_used, ren_used = dev_png, render_png
        regions = [tuple(r) for r in (e.get('ignoreRegions') or [])]
        if regions:
            dev_used = mask_regions(dev_png, regions, os.path.join(tmpdir, name + '.dev.masked.png'))
            ren_used = mask_regions(render_png, regions, os.path.join(tmpdir, name + '.ren.masked.png'))
        text, res = run_diff(ui_tools, ren_used, dev_used, use_json, project, tmpdir, name, a)
        if not a.quiet:
            print('  —— wysiwyg_diff 原文 ——')
            for line in text.rstrip().splitlines():
                print('  | ' + line)
        note = []
        if state_note:
            note.append(state_note)
        if regions:
            note.append('排除区 %d 处（运行期生成）' % len(regions))
        if rinfo['missing_assets']:
            note.append('缺资源 %d 类' % len(rinfo['missing_assets']))
        if rinfo['unsupported']:
            note.append('降级 %d 类' % len(rinfo['unsupported']))
        if note:
            print('  · ' + '；'.join(note))
        ok = bool(res.get('pass'))
        rows.append((name, e['page'],
                     '%.2f%%' % res.get('nonTextConsistencyPct', -1),
                     '%dx%d(%d)' % (res.get('maxBlock', {}).get('w', -1),
                                    res.get('maxBlock', {}).get('h', -1),
                                    res.get('maxBlock', {}).get('area', -1)),
                     '%.2f%%' % res.get('runtimeTextRatioPct', -1),
                     'PASS' if ok else 'FAIL'))
        results.append({'name': name, 'page': e['page'], 'file': e['file'],
                        'pass': ok, 'nonTextConsistencyPct': res.get('nonTextConsistencyPct'),
                        'runtimeTextRatioPct': res.get('runtimeTextRatioPct'),
                        'maxBlock': res.get('maxBlock'),
                        'ignoreRegions': len(regions), 'scrollY': int(e.get('scrollY') or 0),
                        'render': rel(render_png), 'device': rel(dev_png),
                        'attribution': res.get('attribution', [])[:8]})

    print('\n' + '-' * 92)
    print('汇总（pct=非文字区一致率，判据 ≥ %.2f%% 且无结构性差异块；运行期文字按既有口径排除）'
          % (100.0 - a.max_ratio))
    print('%-22s %-11s %8s %-14s %12s  %s' % ('名字', '页面', '一致率', '结构块', '运行期文字差异', '结果'))
    for (n, pg, pct, blk, rt, st) in rows:
        print('%-22s %-11s %8s %-14s %12s  %s' % (n, pg, pct, blk, rt, st))
    npass = sum(1 for r in results if r.get('pass'))
    print('-' * 92)
    print('合计 %d 条：PASS %d / FAIL %d' % (len(results), npass, len(results) - npass))
    print('（滚动位置/动画/视频/屏保/旋转/系统栏不在离线承诺范围内，见 '
          'knowledge/devflow/wysiwyg-render-spec.md 边界表）')

    if a.json_out:
        out = a.json_out if os.path.isabs(a.json_out) else os.path.join(REPO, a.json_out)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        json.dump({'set': os.path.basename(set_dir), 'project': rel(project),
                   'generatedAt': datetime.datetime.now().astimezone().replace(microsecond=0).isoformat(),
                   'device': man.get('device', {}), 'params': {'scale': a.scale, 'tol': a.tol,
                                                               'maxRatio': a.max_ratio,
                                                               'minBlock': a.min_block},
                   'entries': results, 'summary': {'total': len(results), 'passed': npass,
                                                   'failed': len(results) - npass}},
                  open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('清单: %s' % rel(out))

    if not a.keep_temp:
        for f in os.listdir(tmpdir):
            if f.endswith('.diff.json'):                        # 留证据：逐控件归因清单小且有用
                continue
            try:
                os.remove(os.path.join(tmpdir, f))
            except OSError as ex:                             # 删不掉不影响结论，但要吭声
                sys.stderr.write('[warn] 清不掉 %s：%s\n' % (f, ex))
    return 0 if npass == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
