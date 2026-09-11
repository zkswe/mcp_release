# -*- coding: utf-8 -*-
"""knowledge ↔ wiki 双份检测（治理工具，见 knowledge/README.md）。

用法：python scripts/check_duplicate.py
输出：双份清单（字节相同 = rag 双命中；不同 = 内容漂移，需人工判断权威侧）
规则：实践文档唯一放 knowledge/，wiki 只留官方镜像 → 双份应为 0。
"""
import os, sys, hashlib

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.abspath(__file__))
OPEN = os.path.dirname(BASE)                     # tools/FlyThings_mcp_open
KNOWLEDGE = os.path.join(OPEN, 'knowledge')
WIKI = os.path.join(os.path.expanduser('~'), '.openclaw', 'workspace', 'wiki', 'flythings')


def _hash(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    if not os.path.isdir(KNOWLEDGE) or not os.path.isdir(WIKI):
        print('knowledge 或 wiki 目录不存在，检查路径')
        return
    same, diff = [], []
    for root, _, files in os.walk(KNOWLEDGE):
        for fn in files:
            if not fn.endswith('.md'):
                continue
            rel = os.path.relpath(os.path.join(root, fn), KNOWLEDGE)
            if rel.lower() == 'readme.md':
                continue  # 两棵树根 README 各自独立（knowledge=治理文档 / wiki=官方说明），非双份
            wf = os.path.join(WIKI, rel)
            if not os.path.isfile(wf):
                continue
            if _hash(os.path.join(root, fn)) == _hash(wf):
                same.append(rel)
            else:
                diff.append(rel)
    print('knowledge ↔ wiki 双份: 相同 %d / 漂移 %d / 共 %d' % (len(same), len(diff), len(same) + len(diff)))
    for r in sorted(same):
        print('  [相同-双命中] %s' % r)
    for r in sorted(diff):
        print('  [漂移-需对齐] %s' % r)
    print('规范要求双份 = 0（实践知识唯一放 knowledge/，见 knowledge/README.md）')


if __name__ == '__main__':
    main()
