# -*- coding: utf-8 -*-
"""由流程注册表生成知识页 `knowledge/devflow/flow-index.md`。

用法：
    python scripts/gen_flow_doc.py            # 生成/更新
    python scripts/gen_flow_doc.py --check    # 只比对（门禁口径；漂移退出码 1）

为什么要有这一页：流程本来散在三个地方（MCP prompts / 用户级 skills / SCENARIO_COVERAGE.md），
**RAG 只覆盖 knowledge/** —— AI 检索不到就只能凭感觉串步骤。这一页把「两条轴 + 步骤库 +
铁律 + 状态位」摊成可检索的一页（skills 与 prompts 是它的两种发布形态）。
"""
import io
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import derived_md                                    # noqa: E402
import flow_loader as F                              # noqa: E402

DOC = os.path.join(BASE, F.doc_path())


def main(argv):
    a = set(argv[1:])
    errs = F.validate(include_doc=False)
    if errs:
        print('[FAIL] 流程注册表自检未过：')
        for e in errs[:8]:
            print('   -', e)
        return 1
    want = F.render_doc()
    cur = io.open(DOC, encoding='utf-8').read() if os.path.isfile(DOC) else ''
    if derived_md.same(cur, want):
        print('[PASS] 已一致，无需更新')
        return 0
    if '--check' in a:
        print('[FAIL] 流程索引页与 flow_spec.json 不一致（跑 gen_flow_doc.py 重生成）')
        return 1
    os.makedirs(os.path.dirname(DOC), exist_ok=True)
    with io.open(DOC, 'w', encoding='utf-8', newline='') as fh:
        fh.write(want)
    print('已写入 %s（%d 行）' % (F.doc_path(), len(want.splitlines())))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
