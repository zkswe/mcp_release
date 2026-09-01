# -*- coding: utf-8 -*-
"""
通用一键全检（通用工具 v1，不随项目复制）：python tools/ui_tools/check_all.py <项目根目录>
依次执行：根节点 / 嵌套深度 / 特殊字符 / 图片引用 / 回调 / 指针 / 定时器表 / 括号 /
开发者修改检测（ftu 比 json 新>30s 自动同步）+ fui pack 成功。
全部 PASS 才允许交付。任何 FAIL 都会给出具体文件与原因。
"""
import glob
import json
import os
import re
import subprocess
import sys
import shutil
import tempfile
import time as _t

BASE = os.path.dirname(os.path.abspath(__file__))
# fui.exe 优先用项目内（ui/fui.exe），否则 workspace/projects/fui.exe，否则 PATH
FUI = None
for cand in (
    os.path.join(BASE, '..', '..', 'projects', 'fui.exe'),
    'fui',
):
    if os.path.exists(cand):
        FUI = cand
        break
if not FUI:
    FUI = 'fui'

BLACKLIST = set('⌫℃■●‹－＋–…→★◆▶▷①')
failures = []


def _is_bad_char(c):
    """设备裁剪字库外的字符：黑名单特殊符号 + emoji 范围。"""
    if c in BLACKLIST:
        return True
    o = ord(c)
    return (0x1F000 <= o <= 0x1FAFF) or (0x2600 <= o <= 0x27BF) or \
        (0x2300 <= o <= 0x23FF) or (0x2190 <= o <= 0x21FF) or \
        (0x25A0 <= o <= 0x25FF) or (0x2460 <= o <= 0x24FF) or \
        (0x2100 <= o <= 0x214F) or (0x2B00 <= o <= 0x2BFF) or \
        o in (0xFE0F, 0x200D)


def log(ok, msg):
    print(('  [PASS] ' if ok else '  [FAIL] ') + msg)
    if not ok:
        failures.append(msg)


def walk(d, out, depth=0):
    for k, v in d.items():
        if isinstance(v, dict) and '__' in k:
            out.append((depth, k, v.get('caption', '')))
            walk(v, out, depth + 1)


def main(project_root):
    root = os.path.abspath(project_root)
    if not os.path.isdir(root):
        print(f'[X] 项目目录不存在: {root}')
        sys.exit(1)
    ui = os.path.join(root, 'ui')
    if not os.path.isdir(ui):
        print(f'[X] ui 目录不存在: {ui}')
        sys.exit(1)

    PAGES = sorted(['ui/' + os.path.basename(f) for f in glob.glob(os.path.join(ui, '*.json'))])
    LOGICS = sorted(['src/logic/' + os.path.basename(f)
                     for f in glob.glob(os.path.join(root, 'src', 'logic', '*.cc'))])
    if not PAGES:
        print('[X] ui/ 下没有 json 布局')
        sys.exit(1)
    if not LOGICS:
        print('[WARN] src/logic/ 下没有 logic.cc（纯 UI 交付可忽略；有交互则必须有）')

    print('== 1. 根节点（id:0 + position 全屏 + resolution 一致）==')
    for f in PAGES:
        d = json.load(open(os.path.join(root, f), encoding='utf-8'))
        ok = (d.get('id') == 0 and isinstance(d.get('position'), dict)
              and isinstance(d.get('resolution'), dict)
              and d['position'].get('left') == 0 and d['position'].get('top') == 0
              and d['position'].get('width') == d['resolution'].get('width')
              and d['position'].get('height') == d['resolution'].get('height'))
        log(ok, '%s 根节点' % f)

    print('== 2. 嵌套深度（window 子控件必须嵌套，深度 >= 1）==')
    for f in PAGES:
        d = json.load(open(os.path.join(root, f), encoding='utf-8'))
        items = []
        walk(d, items)
        has_child = any(it[0] == 1 for it in items)
        log(has_child, '%s 嵌套（存在 window 内子控件）' % f)

    print('== 3. 特殊字符（emoji/字库外字符）==')
    for f in PAGES:
        txt = open(os.path.join(root, f), encoding='utf-8').read()
        bad = sorted(set(c for c in txt if _is_bad_char(c)))
        log(not bad, '%s 特殊字符 %s' % (f, bad if bad else '无'))
    for f in LOGICS:
        txt = open(os.path.join(root, f), encoding='utf-8').read()
        bad = sorted(set(c for c in txt if _is_bad_char(c)))
        log(not bad, '%s 特殊字符 %s' % (f, bad if bad else '无'))

    print('== 4. 图片引用（json + logic.cc 引用的图片必须存在）==')
    refs = set()
    for f in PAGES + LOGICS:
        txt = open(os.path.join(root, f), encoding='utf-8').read()
        for m in re.finditer(r'"(images/[^"]+\.png)"', txt):
            refs.add(m.group(1))
    missing = []
    for r in refs:
        if '%s' in r:
            # %s 格式化前缀（如 images/dot_%s.png → images/dot_*）：去掉 %s 及其后的 .png
            prefix = r.split('%s')[0]
            if not glob.glob(os.path.join(root, 'resources', prefix + '*.png')):
                missing.append(r + '（前缀无匹配文件）')
            continue
        if not os.path.exists(os.path.join(root, 'resources', r)):
            missing.append(r)
    log(not missing, '图片引用 %s' % (missing if missing else '全部存在'))

    print('== 5. 回调核对（button → onButtonClick，edittext → onEditTextChanged）==')
    logic_map = {}
    for lf in LOGICS:
        base = os.path.splitext(os.path.basename(lf))[0].replace('Logic', '')
        logic_map[base] = lf
    for f in PAGES:
        d = json.load(open(os.path.join(root, f), encoding='utf-8'))
        caps = {}

        def by_caption(dd, out):
            for k, v in dd.items():
                if isinstance(v, dict) and '__' in k:
                    out[v.get('caption', '')] = v
                    by_caption(v, out)

        by_caption(d, caps)
        # 页面对应 logic：main.json → mainLogic.cc（模糊匹配）
        page_base = os.path.basename(f)[:-5]
        logic_file = None
        for lf in LOGICS:
            lb = os.path.basename(lf)
            if lb.startswith(page_base):
                logic_file = lf
                break
        if not logic_file:
            logic_file = logic_map.get(page_base) or (LOGICS[0] if LOGICS else None)
        if not logic_file:
            log(False, '%s 找不到对应 logic.cc' % f)
            continue
        code = open(os.path.join(root, logic_file), encoding='utf-8').read()

        def has_fn(name):
            return bool(re.search(name + r'\s*\(', code))

        bad = []
        for cap, v in caps.items():
            cid = v.get('id', 0)
            if 20000 <= cid < 30000 and not has_fn('onButtonClick_' + cap):
                bad.append('onButtonClick_' + cap)
            if 51000 <= cid < 52000 and not has_fn('onEditTextChanged_' + cap):
                bad.append('onEditTextChanged_' + cap)
        log(not bad, '%s 回调 %s' % (f, bad if bad else '齐全'))

    print('== 6. 指针核对（mXXXPtr 必须存在于 caption）==')
    for f in PAGES:
        d = json.load(open(os.path.join(root, f), encoding='utf-8'))
        ccaps = set()

        def collect(dd, out):
            for k, v in dd.items():
                if isinstance(v, dict) and '__' in k:
                    out.add(v.get('caption', ''))
                    collect(v, out)

        collect(d, ccaps)
        page_base = os.path.basename(f)[:-5]
        logic_file = None
        for lf in LOGICS:
            if os.path.basename(lf).startswith(page_base):
                logic_file = lf
                break
        if not logic_file:
            continue
        code = open(os.path.join(root, logic_file), encoding='utf-8').read()
        code2 = re.sub(r'//[^\n]*', '', code)
        used = set(re.findall(r'\bm([A-Za-z_]\w*)Ptr\b', code2))
        missing = [p for p in used if p not in ccaps]
        log(not missing, '%s 指针 %s' % (f, missing if missing else '全部有效'))

    print('== 7. REGISTER_ACTIVITY_TIMER_TAB（每个 logic.cc 必须包含）==')
    for f in LOGICS:
        txt = open(os.path.join(root, f), encoding='utf-8').read()
        log('REGISTER_ACTIVITY_TIMER_TAB' in txt, '%s 定时器表' % f)

    print('== 8. 括号平衡 ==')
    for f in LOGICS + ['src/Main.cpp']:
        p = os.path.join(root, f)
        if not os.path.isfile(p):
            continue
        code = open(p, encoding='utf-8').read()
        depth = 0
        in_str = False
        bad = 0
        for ch in code:
            if in_str:
                if ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth < 0:
                    bad += 1
                    depth = 0
        log(bad == 0 and depth == 0, '%s 括号 %s' % (f, '平衡' if bad == 0 and depth == 0 else '不平衡'))

    print('== 9. 开发者修改检测 + fui pack 成功生成 ftu ==')
    # ① ftu 比 json 新超 30 秒 → 判定开发者/IDE 直接改过 ftu → 先同步 json 再 pack
    for jf in PAGES:
        jp = os.path.join(root, jf)
        fp = os.path.join(ui, os.path.splitext(os.path.basename(jf))[0] + '.ftu')
        if os.path.isfile(fp) and os.path.isfile(jp):
            jt = os.path.getmtime(jp)
            ft = os.path.getmtime(fp)
            if ft > jt + 30:
                print('  [WARN] %s ftu 比 json 新 %.0f 秒（开发者/IDE 改过 ftu，自动以 ftu 同步 json）'
                      % (os.path.basename(jf), ft - jt))
                r = subprocess.run([FUI, 'unpack', ui], capture_output=True, text=True)
                if r.returncode == 0:
                    os.utime(jp, (ft, ft))  # json mtime 对齐 ftu（ftu 同步出的 json mtime 是 ftu 内嵌时间戳，需对齐避免误判）
                    print('  [PASS] %s ftu→json 同步 成功' % os.path.basename(jf))
                else:
                    log(False, '%s ftu→json 同步 失败' % os.path.basename(jf))
            else:
                log(True, '%s ftu 与 json 时间戳正常' % os.path.basename(jf))
    # ② pack 生成 ftu（json→ftu 已验证无损）
    r = subprocess.run([FUI, 'pack', ui], capture_output=True, text=True)
    if r.returncode != 0:
        log(False, 'fui pack 失败: %s' % ((r.stderr or r.stdout or '')[-200:]))
    else:
        for jf in PAGES:
            ftu = os.path.join(ui, os.path.splitext(os.path.basename(jf))[0] + '.ftu')
            log(os.path.isfile(ftu), '%s pack 成功 → %s' % (os.path.basename(jf), os.path.basename(ftu)))

    print()
    if failures:
        print('[X] %d 项 FAIL，修复后再交付：' % len(failures))
        for f in failures:
            print('   -', f)
        sys.exit(1)
    else:
        print('[OK] 全部 PASS，可以交付。')
        sys.exit(0)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        print('用法: python tools/ui_tools/check_all.py <项目根目录>')
        sys.exit(1)
    main(sys.argv[1])
