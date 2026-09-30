# -*- coding: utf-8 -*-
"""op → 知识「去哪找」（op_seealso.json）覆盖度闸门。

用法：
  python scripts/gen_seealso.py           # 打印覆盖度报告（退出码 0）
  python scripts/gen_seealso.py --check   # 门禁用：有 FAIL 退出码 1

判据：
  1. 每个 op（kb_tools.OP_NAMES）都必须有条目；多出未定义的 op 名 → FAIL。
  2. 条目必须二选一：seeAlso（非空 list，路径必须真实存在）或 none（理由 ≥ 6 字）。
  3. seeAlso 路径必须是仓库内路径（随包分发）；wiki: 前缀 = 本地官方镜像，缺失只提示。
"""
import io, json, os, sys
sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

MAP = os.path.join(BASE, 'op_seealso.json')


def main(check=False):
    import kb_tools as kt                                  # noqa: F401 提供 OP_NAMES
    ops_defined = list(getattr(kt, 'OP_NAMES', ()))
    try:
        data = json.loads(io.open(MAP, encoding='utf-8').read())
    except Exception as e:
        print('[FAIL] 读不了 %s（%s: %s）' % (MAP, type(e).__name__, e))
        return 1
    table = data.get('ops') or {}
    fails, warns = [], []
    missing = [o for o in ops_defined if o not in table]
    extra = [o for o in table if o not in ops_defined]
    if missing:
        fails.append('未登记 seeAlso 的 op（%d 个）：%s' % (len(missing), ', '.join(missing)))
    if extra:
        fails.append('登记了不存在的 op（%d 个）：%s' % (len(extra), ', '.join(extra)))
    n_doc = n_none = 0
    for op, ent in sorted(table.items()):
        refs = ent.get('seeAlso')
        none_reason = ent.get('none')
        if isinstance(refs, list) and refs:
            for r in refs:
                p = os.path.join(BASE, r.replace('/', os.sep))
                if not os.path.exists(p):
                    fails.append('%s: seeAlso 路径不存在 → %s' % (op, r))
            n_doc += 1
        elif none_reason and len(str(none_reason).strip()) >= 6:
            n_none += 1
        else:
            fails.append('%s: 既没有 seeAlso，也没有可读的 none 理由' % op)
        for w in (ent.get('wiki') or []):
            root = os.path.join(os.path.expanduser('~'), '.openclaw', 'workspace', 'wiki', 'flythings')
            if not os.path.exists(os.path.join(root, str(w).replace('/', os.sep))):
                warns.append('%s: wiki 镜像文件不在本机（%s，可忽略）' % (op, w))
    print('op_seealso：%d op（%d 有 seeAlso / %d 登记 none）%s'
          % (len(table), n_doc, n_none, '' if not warns else '；%d 条 wiki 提示' % len(warns)))
    for w in warns[:5]:
        print('   [warn]', w)
    for f in fails:
        print('   [FAIL]', f)
    if fails:
        print('[FAIL] seeAlso 覆盖度 %d 项' % len(fails))
        return 1
    print('[PASS] seeAlso 覆盖完整（OP_NAMES %d 个，路径全在）' % len(ops_defined))
    return 0


if __name__ == '__main__':
    sys.exit(main(check='--check' in sys.argv))
