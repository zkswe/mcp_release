# -*- coding: utf-8 -*-
"""由症状注册表生成知识页 `knowledge/devflow/symptom-index.md`（域⑭的派生物）。

用法：
    python scripts/gen_symptom_doc.py            # 生成/更新
    python scripts/gen_symptom_doc.py --check    # 只比对（门禁口径；漂移退出码 1）

为什么要有这一页（2026-10-04）：口语症状散进各篇正文 = 记录踩坑故事（违反 DESIGN_SPEC §1），
而且必然漂移。收成注册表后派生一页：症状原话逐字进页（检索锚点），机制/规范/权威文档一处维护。
"""
import io
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import derived_md                                    # noqa: E402
import symptom_loader as S                           # noqa: E402

DOC = os.path.join(BASE, S.doc_path())


def main(argv):
    a = set(argv[1:])
    errs = S.validate(include_doc=False)
    if errs:
        print('[FAIL] 症状注册表自检未过：')
        for e in errs[:8]:
            print('   -', e)
        return 1
    want = S.render_doc()
    cur = io.open(DOC, encoding='utf-8').read() if os.path.isfile(DOC) else ''
    if derived_md.same(cur, want):
        print('[PASS] 已一致，无需更新')
        return 0
    if '--check' in a:
        print('[FAIL] 症状索引页与 symptom_spec.json 不一致（跑 gen_symptom_doc.py 重生成）')
        return 1
    os.makedirs(os.path.dirname(DOC), exist_ok=True)
    with io.open(DOC, 'w', encoding='utf-8', newline='') as fh:
        fh.write(want)
    print('已写入 %s（%d 行）' % (S.doc_path(), len(want.splitlines())))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
