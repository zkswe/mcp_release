# -*- coding: utf-8 -*-
"""MCP 自检 / 冒烟（离线，零副作用）——发布前必跑。

用法（在 MCP 根目录或任意位置）：
    python scripts/smoke.py            # 离线自检（默认）
    python scripts/smoke.py --screenshot   # 额外真机抓屏冒烟（需 adb + 设备）
    python scripts/smoke.py --json out.json

检查项：
  1. 版本号 / build / 工具数（kb_tools.MCP_VERSION）
  2. register_all 注册的工具：存在、可调用、签名可解析
  3. 关键模块依赖：ui_editor/ui_edit_apply/ui_diff/device_screenshot 等是否可用
  4. 入口一致性：ui_tools 副本与 MCP 内副本、mcp_server 入口 docstring 工具数
  5. 文档漂移：README / CHANGELOG 顶部的版本号与工具数是否等于真实值
  6. catalog.json（本地意图闸门）ops 数是否等于真实工具数
退出码：0 = 全通过；1 = 有 FAIL。
输出为纯 ASCII（Windows 控制台 GBK 安全）。
"""
import argparse
import io
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, 'ui_tools'))

RESULT = []


def check(ok, name, detail=''):
    RESULT.append((bool(ok), name, detail))
    print('%s %-46s %s' % ('[PASS]' if ok else '[FAIL]', name, detail))
    return bool(ok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--screenshot', action='store_true', help='extra: real device screenshot smoke')
    ap.add_argument('--device', default='', help='device serial for --screenshot')
    ap.add_argument('--json', default='', help='write result JSON here')
    a = ap.parse_args()

    print('=' * 72)
    print('FlyThings MCP smoke  (BASE=%s)' % BASE)
    print('=' * 72)

    # ---- 1) import + 版本
    try:
        import kb_tools as k
    except Exception as e:
        check(False, 'import kb_tools', repr(e))
        return finish(a)
    check(True, 'import kb_tools', '')
    ver = getattr(k, 'MCP_VERSION', '?')
    build = getattr(k, 'MCP_BUILD', '?')
    check(bool(re.match(r'^\d+\.\d+\.\d+-open$', str(ver))), 'MCP_VERSION format', str(ver))
    print('       version=%s build=%s' % (ver, build))

    # ---- 2) 注册工具
    src = io.open(os.path.join(BASE, 'kb_tools.py'), encoding='utf-8').read()
    names = re.findall(r'mcp\.tool\(\)\((\w+)\)', src)
    check(len(names) > 0, 'register_all tool count', str(len(names)))
    bad = []
    for n in names:
        f = getattr(k, n, None)
        if f is None or not callable(f):
            bad.append(n + ':missing')
            continue
        try:
            import inspect
            inspect.signature(f)
        except Exception as e:
            bad.append('%s:%s' % (n, e))
    check(not bad, 'tool functions callable', ','.join(bad) if bad else 'all ok')

    # ---- 3) 依赖模块
    for mod in ('uied', 'uia', 'udf', 'dss', 'h2j', 'j2h', 'h2j_genres', 'itx', 'tt', 'rs', 'pt', 'pkgtools'):
        if hasattr(k, mod):
            check(getattr(k, mod) is not None, 'module %s' % mod, '')
    for f in ('device_screenshot.py', 'ui_editor.py', 'ui_edit_apply.py', 'ui_diff.py'):
        check(os.path.isfile(os.path.join(BASE, 'ui_tools', f)), 'ui_tools/%s' % f, '')

    # ---- 4) 入口一致性
    srv = io.open(os.path.join(BASE, 'mcp_server.py'), encoding='utf-8').read()
    m = re.search(r'(\d+)\s*个能力合一', srv)
    check(bool(m) and int(m.group(1)) == len(names), 'mcp_server docstring count',
          '%s vs %d' % (m.group(1) if m else '?', len(names)))

    # ---- 5) 文档漂移
    rd = io.open(os.path.join(BASE, 'README.md'), encoding='utf-8').read()
    m = re.search(r'\*\*(\d+)\s*个工具\*\*', rd)
    check(bool(m) and int(m.group(1)) == len(names), 'README tool count',
          '%s vs %d' % (m.group(1) if m else '?', len(names)))
    check(ver in rd, 'README mentions current version', str(ver))
    m = re.search(r'\| 工具列表 <\s*(\d+)', rd)
    check(bool(m) and int(m.group(1)) == len(names), 'README FAQ count',
          '%s vs %d' % (m.group(1) if m else '?', len(names)))
    cl = io.open(os.path.join(BASE, 'CHANGELOG.md'), encoding='utf-8').read()
    m = re.search(r'当前版本：\*\*(v[\d.]+-open)\*\*', cl)
    check(bool(m) and m.group(1).lstrip('v') == str(ver), 'CHANGELOG top version',
          '%s vs %s' % (m.group(1) if m else '?', ver))
    check(('v%s' % ver) in cl.splitlines()[2] if len(cl.splitlines()) > 2 else False,
          'CHANGELOG has section?', 'see top block')
    feats = getattr(k, 'MCP_FEATURES', [])
    check(bool(feats) and str(ver) in feats[0], 'MCP_FEATURES[0] mentions version',
          feats[0][:40] if feats else 'empty')

    # ---- 6) 意图闸门 catalog
    catp = os.path.join(os.path.dirname(BASE), 'flythings_intent_gate', 'catalog.json')
    if os.path.isfile(catp):
        cat = json.load(io.open(catp, encoding='utf-8'))
        cnt = cat.get('count', len(cat.get('ops', [])))
        check(cnt == len(names), 'gate catalog ops count', '%s vs %d (regenerate: temp/gen_catalog.py)' % (cnt, len(names)))
    else:
        check(False, 'gate catalog.json exists', catp)

    # ---- 7) 可选：真机抓屏冒烟
    if a.screenshot:
        try:
            r = json.loads(k.flythings_device_screenshot(device=a.device, scale=0.25, timeout=120))
            check(bool(r.get('success')), 'device screenshot', str(r.get('path', r.get('error')))[:90])
            if r.get('success'):
                check(os.path.isfile(r['path']), 'screenshot file exists', r['path'])
        except Exception as e:
            check(False, 'device screenshot', repr(e))

    return finish(a)


def finish(a):
    fails = [r for r in RESULT if not r[0]]
    print('-' * 72)
    print('total=%d  fail=%d  %s' % (len(RESULT), len(fails), 'OK' if not fails else 'FAILED'))
    for _, n, d in fails:
        print('  FAIL %s %s' % (n, d))
    if a.json:
        io.open(a.json, 'w', encoding='utf-8').write(json.dumps(
            [{'ok': o, 'name': n, 'detail': d} for o, n, d in RESULT], ensure_ascii=False, indent=2))
        print('json -> %s' % a.json)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
