# -*- coding: utf-8 -*-
"""从 op 契约注册表生成 op_seealso.json（op → 知识「去哪找」）。

设计（v0.27.174）：op_seealso.json 曾是**人工维护**的第二份事实来源；现在降级为
**派生产物**——seeAlso / wiki / none 理由都写在 op_spec.json 里，本脚本负责落盘与比对。
消费方不变：kb_tools._seealso_for 在返回体注入 seeAlso 字段（AI 拿到结果就知道去哪看细节），
所以「知识归属」不必再写进 docstring，也就不用占 12000 字符的常驻描述预算。

判据（--check 时任何一条不满足即退出码 1）：
  1. 注册表里的每个 op 都必须二选一：seeAlso（非空 list，路径必须真实存在）或 noneReason（≥6 字）。
  2. seeAlso 路径必须是仓库内路径（随包分发）；wiki 是本地官方镜像，缺失只提示不算失败。
  3. kb_tools.OP_NAMES 与注册表必须逐个对上（少登记 / 多登记都 FAIL）。

用法：
    python scripts/gen_seealso.py            # 写回 op_seealso.json
    python scripts/gen_seealso.py --check    # 只比对漂移（门禁调用）
"""
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import op_spec_loader as osl                       # noqa: E402

OUT = os.path.join(BASE, 'op_seealso.json')
NOTE = ('op → 知识文档「去哪找」映射。**派生产物**：真源 = op_spec.json 的 seeAlso / wiki / '
        'noneReason 字段（scripts/gen_seealso.py 生成，勿手改）。由 kb_tools.normalize_result '
        '注入返回体 seeAlso 字段；seeAlso 只写仓库内 knowledge/ 路径（随包分发），wiki 是本地'
        '官方镜像（不进仓库）仅作提示。noneReason 表示该 op 没有实践知识归属，必须写理由。')


def build():
    """由注册表生成 op_seealso.json 的结构（确定性排序）。"""
    ops = {}
    for op in osl.registered():
        s = osl.spec(op)
        ent = {}
        refs = [str(x) for x in (s.get('seeAlso') or [])]
        if refs:
            ent['seeAlso'] = refs
        if s.get('wiki'):
            ent['wiki'] = [str(x) for x in s['wiki']]
        if not refs:
            reason = str(s.get('noneReason') or '').strip()
            if reason:
                ent['none'] = reason
        ops[op] = ent
    return {'schema': 1, 'note': NOTE, 'ops': ops}


def validate():
    """覆盖度 + 路径自检；返回 (fails, warns, table)。"""
    import kb_tools as kt
    defined = list(getattr(kt, 'OP_NAMES', ()))
    reg = osl.registered()
    fails, warns = [], []
    missing = [o for o in defined if o not in set(reg)]
    extra = [o for o in reg if o not in set(defined)]
    if missing:
        fails.append('op 未登记进 op_spec.json（%d 个）：%s' % (len(missing), ', '.join(missing)))
    if extra:
        fails.append('注册表里的 op 在 kb_tools 不存在（%d 个）：%s' % (len(extra), ', '.join(extra)))
    table = build()['ops']
    for op, ent in sorted(table.items()):
        refs = ent.get('seeAlso')
        if isinstance(refs, list) and refs:
            for r in refs:
                if not os.path.exists(os.path.join(BASE, r.replace('/', os.sep))):
                    fails.append('%s: seeAlso 路径不存在 → %s' % (op, r))
        elif len(str(ent.get('none') or '').strip()) < 6:
            fails.append('%s: 既没有 seeAlso，也没有 ≥6 字的 noneReason' % op)
        for w in (ent.get('wiki') or []):
            root = os.path.join(os.path.expanduser('~'), '.openclaw', 'workspace', 'wiki', 'flythings')
            if not os.path.exists(os.path.join(root, str(w).replace('/', os.sep))):
                warns.append('%s: wiki 镜像文件不在本机（%s，可忽略）' % (op, w))
    return fails, warns, table


def main():
    check = '--check' in sys.argv
    fails, warns, table = validate()
    print('op_seealso：%d op（%d 有 seeAlso / %d 登记 none）%s'
          % (len(table), sum(1 for e in table.values() if e.get('seeAlso')),
             sum(1 for e in table.values() if e.get('none')),
             '' if not warns else '；%d 条 wiki 提示' % len(warns)))
    for w in warns[:5]:
        print('   [warn]', w)
    for f in fails:
        print('   [FAIL]', f)

    want = json.dumps(build(), ensure_ascii=False, indent=2) + '\n'
    cur = ''
    if os.path.isfile(OUT):
        cur = io.open(OUT, encoding='utf-8').read().replace('\r\n', '\n')
    if fails:
        print('[FAIL] seeAlso 覆盖度 %d 项' % len(fails))
        return 1
    if check:
        if cur != want:
            print('[FAIL] op_seealso.json 与注册表漂移（跑 scripts/gen_seealso.py 重生成）')
            return 1
        print('[PASS] op_seealso.json 与注册表一致（%d op）' % len(table))
        return 0
    if cur != want:
        io.open(OUT, 'w', encoding='utf-8', newline='\n').write(want)
        print('updated: %s（已由 op_spec.json 重生成）' % OUT)
    else:
        print('[PASS] op_seealso.json 已与注册表一致，无需更新')
    return 0


if __name__ == '__main__':
    sys.exit(main())
