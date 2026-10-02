# -*- coding: utf-8 -*-
"""从平台能力注册表（platform_capabilities.json）重写 components/*/platforms.md 里的矩阵表。

为什么：那 15 张「平台 × 可用性」表曾是各篇独立手写的——同一份能力知识抄 15 份，
「这组件在 Z20 能不能用」要逐篇翻；改一个平台状态要记得改所有相关篇。
现在统一进注册表，各篇只留**原理、坑、验收方法、细节展开**，那张表降级为派生产物。

派生范围严格受限：只重写「首列表头 == 平台 且 表头 == 注册表 columns」的那一张表，
其余内容（含该表下方的口径注释、其它表格、正文）一字不动。

用法：
    python scripts/gen_component_platforms.py            # 写回（--apply 同义）
    python scripts/gen_component_platforms.py --check    # 只比对漂移（门禁用，漂移退出码 1）
    python scripts/gen_component_platforms.py --show ble # 打印某组件的渲染结果
"""
import argparse
import io
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import platform_cap_loader as pc                   # noqa: E402
import derived_md                                   # noqa: E402

FIRST_COL = ('平台', '平台/型号')


def _cells(line):
    s = line.strip()
    if s.startswith('|'):
        s = s[1:]
    if s.endswith('|'):
        s = s[:-1]
    return [c.strip() for c in s.split('|')]


def _strip_md(s):
    return s.replace('**', '').replace('`', '').strip()


def find_table(lines, columns):
    """找目标表：表头首列是「平台」且其余列与注册表 columns 逐项相同。返回 (start, end)。"""
    i = 0
    while i < len(lines):
        if not lines[i].lstrip().startswith('|'):
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].lstrip().startswith('|'):
            j += 1
        head = _cells(lines[i])
        if head and _strip_md(head[0]) in FIRST_COL:
            rest = [_strip_md(c) for c in head[1:]]
            if rest == [_strip_md(c) for c in columns]:
                return i, j
        i = j
    return None


def render_block(comp):
    return [ln + '\n' for ln in pc.render_table(comp)]


def plan():
    """返回 [(组件, 文件, 现状行, 期望行, start, end)]，只含**真有漂移**的。"""
    out, missing = [], []
    for comp in pc.components():
        path = os.path.join(BASE, pc.spec(comp)['file'])
        if not os.path.isfile(path):
            missing.append((comp, pc.spec(comp)['file']))
            continue
        text = io.open(path, encoding='utf-8').read()
        lines = text.splitlines(True)
        hit = find_table(lines, pc.columns(comp))
        if not hit:
            missing.append((comp, pc.spec(comp)['file']))
            continue
        st, en = hit
        want = render_block(comp)
        have = lines[st:en]
        # 比较口径：抹掉纯格式差异（表格对齐/行尾空白不算漂移），内容漂移照旧算红
        if not derived_md.same(''.join(have), ''.join(want)):
            out.append((comp, pc.spec(comp)['file'], have, want, st, en))
    return out, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='只比对漂移（漂移退出码 1）')
    ap.add_argument('--show', metavar='COMP', help='打印某组件的渲染结果')
    a = ap.parse_args()

    if a.show:
        for ln in pc.render_table(a.show):
            print(ln)
        return 0

    errs = pc.validate()
    if errs:
        print('[FAIL] platform_capabilities.json 自检不通过：')
        for e in errs:
            print('  - %s' % e)
        return 1

    drift, missing = plan()
    print('注册表：%d 组件 / %d 行；可定位到表格的 %d 篇'
          % (len(pc.components()), sum(len(pc.rows(c)) for c in pc.components()),
             len(pc.components()) - len(missing)))
    if missing:
        print('[FAIL] 以下组件的矩阵表在 md 里定位不到（表头须为「平台 | %s」）：'
              % ' | '.join(pc.columns(missing[0][0])[:3]) + ' …')
        for comp, f in missing:
            print('  - %s (%s)' % (comp, f))
    print('表格漂移（需重生成）：%d 篇%s'
          % (len(drift), '' if not drift else ' → ' + ', '.join(d[1] for d in drift[:6])))

    if a.check:
        if missing or drift:
            print('[FAIL] platforms.md 的矩阵表与注册表不一致（跑 '
                  'scripts/gen_component_platforms.py 重生成）')
            return 1
        print('[PASS] 全部 %d 篇 platforms.md 的矩阵表与注册表一致' % len(pc.components()))
        return 0

    if missing or not drift:
        return 1 if missing else 0

    changed = {}
    for comp, rel, have, want, st, en in drift:
        changed.setdefault(rel, []).append((st, en, want))
    for rel, edits in changed.items():
        path = os.path.join(BASE, rel)
        text = io.open(path, encoding='utf-8').read()
        lines = text.splitlines(True)
        for st, en, want in sorted(edits, reverse=True):
            lines[st:en] = want
        io.open(path, 'w', encoding='utf-8', newline='').write(''.join(lines))
    print('updated: %d 篇 platforms.md 的矩阵表已由注册表重生成' % len(changed))
    return 0


if __name__ == '__main__':
    sys.exit(main())
