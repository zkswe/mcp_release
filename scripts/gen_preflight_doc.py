# -*- coding: utf-8 -*-
"""由上机前体检判据注册表生成知识页 knowledge/devflow/device-preflight-spec.md。

用法：
    python scripts/gen_preflight_doc.py            # 生成/更新
    python scripts/gen_preflight_doc.py --check    # 只比对（门禁口径；漂移退出码 1）

为什么要有这一页：判据本来只在 `preflight_spec.json` 里，**RAG 只覆盖 knowledge/**，
AI 检索不到就会凭感觉判断（"屏比设计大应该没事吧"）—— 这一页把判据摊成可检索的一页，
顺带把与 `components/fonts` 的跨来源对账（字库阈值/档位）跑成可执行校验。
"""
import io
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import derived_md                                    # noqa: E402
import preflight_loader as P                         # noqa: E402

DOC = os.path.join(BASE, P.doc_path())


def main(argv):
    a = set(argv[1:])
    errs = P.validate(include_doc=False)
    if errs:
        print('[FAIL] 体检判据注册表自检未过：')
        for e in errs[:8]:
            print('   -', e)
        return 1
    want = P.render_doc()
    cur = io.open(DOC, encoding='utf-8').read() if os.path.isfile(DOC) else ''
    if derived_md.same(cur, want):
        print('[PASS] 已一致，无需更新')
        return 0
    if '--check' in a:
        print('[FAIL] 上机前体检判据页与 preflight_spec.json 不一致（跑 gen_preflight_doc.py 重生成）')
        return 1
    os.makedirs(os.path.dirname(DOC), exist_ok=True)
    with io.open(DOC, 'w', encoding='utf-8', newline='') as fh:
        fh.write(want)
    print('已写入 %s（%d 行）' % (P.doc_path(), len(want.splitlines())))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
