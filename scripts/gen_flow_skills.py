# -*- coding: utf-8 -*-
"""把场景流程（`flow_spec.json` 里 `kind=scenario`）派生成本地 skill 的 `SKILL.md`。

用法：
    python scripts/gen_flow_skills.py                 # 写用户级 skill 目录
    python scripts/gen_flow_skills.py --dry-run       # 只打印（不写盘）
    python scripts/gen_flow_skills.py --check         # 只比对（漂移退出码 1）
    python scripts/gen_flow_skills.py --out <目录>    # 换目标根目录

为什么派生：同一批步骤此前在三个地方各写一遍（MCP prompts / 用户级 skills /
`SCENARIO_COVERAGE.md`），改一处另两处**静默过期**。真源 = `flow_spec.json`。

⚠️ 本脚本写的是**用户级 skill 目录**（仓库之外）—— 所以它**不进仓库门禁**
（别人 clone 后没有那个目录），只作为手动 `--check` 的同步工具。
这条边界是有意的：技能是发布产物，仓库里只留源。
"""
import io
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import flow_loader as F                                   # noqa: E402

DEFAULT_OUT = os.path.join(os.path.expanduser('~'), '.workbuddy', 'skills')


def targets(root):
    """[(flow_id, SKILL.md 绝对路径)] —— 顺序稳定（按注册表顺序）。"""
    out = []
    for fid, f in F.flows_of('scenario').items():
        name = f.get('skillName')
        if not name:
            raise F.FlowSpecError('场景流程 %s 缺 skillName，无法定位落点' % fid)
        out.append((fid, os.path.join(root, name, 'SKILL.md')))
    return out


def main(argv):
    a = list(argv[1:])
    dry = '--dry-run' in a
    chk = '--check' in a
    if dry and chk:
        print('[FAIL] --dry-run 与 --check 不能同时用')
        return 2
    root = a[a.index('--out') + 1] if '--out' in a else DEFAULT_OUT

    errs = F.validate(include_doc=False)
    if errs:
        print('[FAIL] 流程注册表自检未过：')
        for e in errs[:8]:
            print('   -', e)
        return 1

    plan = targets(root)
    if not os.path.isdir(root) and not (dry or chk):
        os.makedirs(root, exist_ok=True)

    drift = []
    for fid, path in plan:
        want = F.render_skill(fid)
        cur = io.open(path, encoding='utf-8').read() if os.path.isfile(path) else ''
        rel = os.path.relpath(path, root).replace(os.sep, '/')
        if cur == want:
            print('[PASS] %s 已一致' % rel)
            continue
        drift.append((fid, path, want))
        if dry:
            print('--- %s ---' % rel)
            print(want)
        elif chk:
            print('[FAIL] %s 与 flow_spec.json 不一致（%s）'
                  % (rel, '文件不存在' if not cur else '内容漂移'))
        else:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with io.open(path, 'w', encoding='utf-8', newline='') as fh:
                    fh.write(want)
            except OSError as e:
                print('[FAIL] 写 %s 失败：%s' % (rel, e))
                return 1
            print('已写入 %s（%d 行）' % (rel, len(want.splitlines())))
    if chk and drift:
        print('跑 scripts/gen_flow_skills.py 重生成（%d 篇漂移）' % len(drift))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
