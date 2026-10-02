# -*- coding: utf-8 -*-
"""工程骨架同步：`templates/HelloWord_Z20/src/` 是**骨架的唯一来源**，各工程里的同名文件是它的副本。

背景（2026-10-03 实测）：20 个工程带这份 uart 协议骨架，其中 **171 份逐字节一致** —— 也就是同一份
`Main.cpp` + `uart/*` 被复制了 18 遍。骨架改一次要改 18 处，漏一处就是"某个 demo 行为不一致"。
所以口径与 `scripts/sync_ui_tools.py` 同类：**唯一来源 + 副本 + `--check` 进闸门**。

用法：
    python scripts/sync_project_skeleton.py            # 只报告（哪些工程带骨架 / 有没有漂移）
    python scripts/sync_project_skeleton.py --check     # 门禁口径：有漂移退出码 1
    python scripts/sync_project_skeleton.py --apply     # 用唯一来源覆盖副本

**只管骨架**：`src/Main.cpp` + `src/uart/*`。
**绝不碰** `src/logic/*`（每工程自己的业务）与 `src/activity/*`（IDE 生成、禁手改）。

带 `src/Main.cpp` 但**没有** `src/uart/` 的工程（如最小播放器 demo）视为"自带骨架"，
**报告出来但不动它** —— 不静默跳过，也不强行塞骨架。
"""
import io
import os
import shutil
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANON_DIR = os.path.join(BASE, 'templates', 'HelloWord_Z20', 'src')

# 骨架文件（相对 src/）：与唯一来源逐字节对齐
SKELETON = [
    'Main.cpp',
    'uart/CommDef.h', 'uart/ProtocolData.h',
    'uart/ProtocolParser.cpp', 'uart/ProtocolParser.h',
    'uart/ProtocolSender.cpp', 'uart/ProtocolSender.h',
    'uart/UartContext.cpp', 'uart/UartContext.h',
]
# 「带骨架」的判据：有该文件即认为这个工程用的是同一套骨架
MARKER = 'uart/UartContext.cpp'
# 扫描哪些 src 目录（glob，随仓库增长自动覆盖；不维护清单）
SCAN = ('templates/*/src', 'demos/*/src', 'components/**/example/src',
        'components/**/*/example/src', 'packages/**/src')


def _rel(p):
    return os.path.relpath(p, BASE).replace('\\', '/')


def _read(p):
    with open(p, 'rb') as fh:
        return fh.read()


def is_canonical(src):
    """该 src 是不是唯一来源本身（是自己就不算副本，也不许自我复制）。"""
    return os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(CANON_DIR))


def projects(include_canonical=False):
    """全仓带 src/ 的工程 → [{'src','name','carries'}]（carries=是否用同一套骨架）。"""
    import glob
    out = []
    for pat in SCAN:
        for src in sorted(set(glob.glob(os.path.join(BASE, pat), recursive=True))):
            src = src.replace('\\', '/')
            if not os.path.isdir(src):
                continue
            if is_canonical(src) and not include_canonical:
                continue                      # 唯一来源自己不是副本
            carries = os.path.isfile(os.path.join(src, MARKER))
            if not carries and not os.path.isfile(os.path.join(src, 'Main.cpp')):
                continue                      # 既没骨架也没 Main.cpp → 不是候选
            out.append({'src': src, 'name': _rel(os.path.dirname(src)), 'carries': carries})
    seen, uniq = set(), []
    for r in out:
        if r['src'] in seen:
            continue
        seen.add(r['src'])
        uniq.append(r)
    return uniq


def drift():
    """(漂移清单, 自定义骨架清单)。漂移 = 副本与唯一来源不一致（或副本缺失）。"""
    bad, custom = [], []
    for pr in projects():
        if not pr['carries']:
            custom.append(pr['name'])
            continue
        for rel in SKELETON:
            src = os.path.join(CANON_DIR, rel)
            dst = os.path.join(pr['src'], rel)
            if not os.path.isfile(dst):
                bad.append('%s/%s（缺）' % (pr['name'], rel))
            elif _read(dst) != _read(src):
                bad.append('%s/%s（与唯一来源不一致）' % (pr['name'], rel))
    return bad, custom


def main(argv):
    a = set(argv[1:])
    if not os.path.isdir(CANON_DIR):
        print('[FAIL] 骨架唯一来源不存在：%s' % _rel(CANON_DIR))
        return 1
    bad, custom = drift()
    carried = [p for p in projects() if p['carries']]
    print('骨架唯一来源：%s（%d 个文件）' % (_rel(CANON_DIR), len(SKELETON)))
    print('带骨架的工程：%d 个（%d 份副本）' % (len(carried), len(carried) * len(SKELETON)))
    if custom:
        print('自带骨架（不纳入同步，也不改动）：%s' % '、'.join(custom))
    if '--apply' in a:
        if not bad:
            print('[PASS] 无需同步')
            return 0
        for pr in carried:
            for rel in SKELETON:
                src = os.path.join(CANON_DIR, rel)
                dst = os.path.join(pr['src'], rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(src, dst)
        print('已同步 %d 个工程的骨架' % len(carried))
        return 0
    if bad:
        print('[FAIL] 骨架漂移 %d 处（跑 --apply 同步）：' % len(bad))
        for b in bad[:10]:
            print('   -', b)
        return 1
    print('[PASS] 骨架与唯一来源一致')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
