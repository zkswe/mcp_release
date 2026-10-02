# -*- coding: utf-8 -*-
"""由 lifecycle_spec.json（唯一真源）生成知识页 knowledge/devflow/activity-lifecycle-spec.md。

用法：
    python scripts/gen_lifecycle_doc.py            # 生成/更新
    python scripts/gen_lifecycle_doc.py --check    # 只比对（门禁口径；漂移退出码 1）
    python scripts/gen_lifecycle_doc.py --hooks    # 打印登记钩子，并核对模板骨架

为什么这个生成器还**核对模板骨架**：钩子名/签名的权威形态是
`templates/HelloWord_*/src/logic/mainLogic.cc`（真机可编译）。注册表写错、或模板被改掉一个钩子，
两边就会不一致 —— 这道交叉检查比只比文档强弱得多（相当于「注册表 vs 真实代码」的对账）。
"""
import io
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import lifecycle_loader as ll          # noqa: E402

DOC = os.path.join(BASE, ll.doc_path())


def template_hooks(template_dir=None):
    """从一个模板骨架里抽出钩子名（与 logic 里 `static ... <name>(...)` 对齐）。"""
    tpl = template_dir or os.path.join(BASE, 'templates', 'HelloWord_Z20', 'src', 'logic')
    cands = [os.path.join(tpl, f) for f in sorted(os.listdir(tpl))] if os.path.isdir(tpl) else []
    out = {}
    for p in cands:
        if not p.endswith('.cc'):
            continue
        try:
            with io.open(p, encoding='utf-8', errors='replace') as fh:
                text = fh.read()
        except OSError as e:
            # 不静默：模板骨架读不了会让「注册表 vs 模板」的交叉核对变成假通过
            print('  [warn] 读不了模板骨架 %s（%s）——本次交叉核对不含该文件'
                  % (os.path.basename(p), type(e).__name__))
            continue
        for m in re.finditer(r'^\s*static\s+[\w:]+\s*\*?\s*(\w+)\s*\(', text, re.M):
            out.setdefault(m.group(1), p)
    return out


def check_template_hooks():
    """注册表登记的钩子 vs 模板骨架实际有的钩子 → (missing_in_tpl, extra_in_tpl)。"""
    tpl = template_hooks()
    reg = [n for n in ll.hook_names() if n != 'REGISTER_ACTIVITY_TIMER_TAB']
    missing = [n for n in reg if n not in tpl]
    # 模板里的其它 static 函数（如各控件回调）不算“多余”，只报「注册表没登记但像钩子」的
    extra = [n for n in tpl if n not in reg
             and re.match(r'^on[A-Z_]|^onmain', n)]
    return missing, extra


def build():
    return ll.render_doc()


def main(argv):
    args = set(argv[1:])
    if '--hooks' in args:
        print('注册表钩子:', ', '.join(ll.hook_names()))
        missing, extra = check_template_hooks()
        print('模板缺失:', missing or '无')
        print('模板多出:', extra or '无')
        return 0

    errs = ll.validate()
    if errs:
        print('[FAIL] 注册表自检未过：')
        for e in errs:
            print('   -', e)
        return 1
    missing, extra = check_template_hooks()
    if missing:
        print('[FAIL] 注册表登记的钩子在模板骨架里找不到: %s' % ', '.join(missing))
        print('       权威形态 = templates/HelloWord_*/src/logic/mainLogic.cc —— 要么注册表写错，'
              '要么模板少了钩子')
        return 1
    if extra:
        print('[WARN] 模板里的钩子未登记: %s（若确为钩子请登记进 lifecycle_spec.json）'
              % ', '.join(extra))

    want = build()
    cur = ''
    if os.path.isfile(DOC):
        with io.open(DOC, encoding='utf-8') as fh:
            cur = fh.read()
    if '--check' in args:
        if cur != want:
            print('[FAIL] %s 与注册表不一致（漂移）→ 跑 python scripts/gen_lifecycle_doc.py 重生成'
                  % ll.doc_path())
            return 1
        print('[PASS] %s 一致，无需更新' % ll.doc_path())
        return 0
    with io.open(DOC, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(want)
    print('已写入 %s（%d 行）' % (ll.doc_path(), len(want.splitlines())))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
