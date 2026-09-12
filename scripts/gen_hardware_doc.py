# -*- coding: utf-8 -*-
"""生成 knowledge/hardware/hardware-models.md（硬件型号库的可检索文档，单一来源的派生产物）。

设计（与 gen_manifest.py 同套路）：
  事实来源 = hardware_catalog.json（人工维护）
  产出 = knowledge/hardware/hardware-models.md（只读快照，供 RAG 检索 / resource 挂载）
  ⚠️ 不要手改 .md；改 json 后重跑本脚本，再 rebuild_index_local.py 重建索引。

用法：
    python scripts/gen_hardware_doc.py            # 写入 knowledge/hardware/hardware-models.md
    python scripts/gen_hardware_doc.py --check    # 只比对（漂移退出码 1，check_consistency 调用）
    python scripts/gen_hardware_doc.py --out X    # 指定输出
"""
import argparse
import io
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
DEFAULT_OUT = os.path.join(BASE, 'knowledge', 'hardware', 'hardware-models.md')

HEADER_NOTE = '> 本文件由 scripts/gen_hardware_doc.py 生成'


def collect():
    import hardware_tools as hw
    cat, warn = hw.load(force=True)
    if warn:
        for w in warn:
            print('  [warn] %s' % w)
    bad = [k for k in (cat.get('platforms') or {}) if not hw._known_platform(k)]
    if bad:
        raise SystemExit('hardware_catalog.json 含未知平台名（必须取 platforms.py 规范名）：%s'
                         % ', '.join(sorted(bad)))
    empty = [k for k, v in (cat.get('platforms') or {}).items()
             if not (v or {}).get('models')]
    if empty:
        print('  [warn] 平台无型号（仍是合法状态，文档会标「暂未登记」）：%s'
              % ', '.join(sorted(empty)))
    return hw.build_markdown(cat)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--check', action='store_true', help='只比对，不一致退出码 1')
    a = ap.parse_args()
    want = collect()
    if a.check:
        if not os.path.isfile(a.out):
            print('[FAIL] hardware-models.md missing: %s' % a.out)
            return 1
        cur = io.open(a.out, encoding='utf-8').read()
        if cur != want:
            print('[FAIL] hardware-models.md 与 hardware_catalog.json 不一致（漂移）')
            print('   fix: python scripts/gen_hardware_doc.py'
                  '  然后 python rebuild_index_local.py')
            if HEADER_NOTE not in cur:
                print('   （当前文件疑似手写/旧模板，生成物会带来源说明）')
            return 1
        print('[PASS] hardware-models.md in sync (%d chars)' % len(cur))
        return 0
    d = os.path.dirname(a.out)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    io.open(a.out, 'w', encoding='utf-8', newline='\n').write(want)
    print('hardware doc -> %s (%d chars)' % (a.out, len(want)))
    print('   下一步：python rebuild_index_local.py（否则检索还是旧型号表）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
