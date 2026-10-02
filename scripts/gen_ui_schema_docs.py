# -*- coding: utf-8 -*-
"""从注册表（ui_tools/ui_schema.json）生成「每类型必写键」文档表。

唯一真源原则：字段/必填/默认值以注册表为准，文档表是**派生产物**——
本脚本重写 knowledge/uicontrols/json-field-mandatory.md 的「## 每类型必写键」整节
（表格：控件 / 必填键 / 默认值要点），文档其余部分（5 条口径、子结构公式说明等）不动。
必写键口径与 check_all #14 完全同源（复用 check_all._required_keys：注册表必填 ∪ 兼容垫片）。

用法：
    python scripts/gen_ui_schema_docs.py            # 写回 json-field-mandatory.md
    python scripts/gen_ui_schema_docs.py --check    # 只比对（漂移退出码 1）
"""
import io
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, 'ui_tools'))
import ui_schema_loader as us                     # noqa: E402
import check_all as _chk                          # noqa: E402 必写键与 #14 同源（含兼容垫片）

DOC = os.path.join(BASE, 'knowledge', 'uicontrols', 'json-field-mandatory.md')
SECTION_RE = re.compile(r'^## 每类型必写键.*?(?=^## )', re.M | re.S)

# 控件表顺序（沿用旧文档的阅读顺序：常用件在前，容器/低频件在后；子结构不进本表）
_ROW_ORDER = ['textview', 'button', 'window', 'edittext', 'seekbar', 'listview', 'circlebar',
              'slidewindow', 'digitalclock', 'qrcode', 'videoview', 'cameraview', 'painter',
              'pointer', 'diagram', 'checkbox', 'radiogroup', 'radiobutton', 'pagewindow',
              'scrollwindow', 'imageanim', 'slidetext']


def _fmt_default(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    return json.dumps(v, ensure_ascii=False)


def _defaults_brief(tname):
    """「默认值要点」列：注册表**显式 default**的标量 k=v 清单 + 字段 note 的首句（截断）。
    （无 default 的必填零值是占位不是「默认值要点」，不列。）"""
    fields = (us.load()['controls'].get(tname) or {}).get('fields') or {}
    parts = []
    for k, spec in fields.items():
        if 'default' not in spec:
            continue
        v = spec['default']
        if isinstance(v, (dict, list)):
            continue                               # 子盒结构不展开（如 colorTab 五槽见规范节）
        parts.append('%s %s' % (k, _fmt_default(v)))
    notes = []
    for k, spec in fields.items():
        n = (spec.get('note') or '').split('；')[0].split('。')[0].strip()
        if n and len(n) <= 42:
            notes.append('%s: %s' % (k, n))
    out = '；'.join(parts)
    if notes:
        out += ('；' if out else '') + '；'.join(notes[:3])
    return out or '—'


def gen_section():
    reg = us.load()
    rows = []
    for t in _ROW_ORDER:
        if t not in reg['controls']:
            raise SystemExit('[FAIL] _ROW_ORDER 里的 %s 不在注册表 controls 中' % t)
        keys = _chk._required_keys(t)
        rows.append('| %s | %s | %s |' % (t, '/'.join(keys), _defaults_brief(t)))
    missing = sorted(set(reg['controls']) - set(_ROW_ORDER))
    if missing:
        raise SystemExit('[FAIL] 注册表新增控件未登记进 _ROW_ORDER: %s' % missing)
    ver = reg.get('schemaVersion', '?')
    upd = reg.get('updated', '?')
    lines = [
        '## 每类型必写键（注册表 v%s @ %s）' % (ver, upd),
        '',
        '⚠️ 本表由 scripts/gen_ui_schema_docs.py 从 ui_tools/ui_schema.json 生成，勿手改；改规范改注册表。',
        '（必写键口径 = check_all #14 同源：注册表 required ∪ #14 兼容垫片，见 check_all._required_keys）',
        '',
        '| 控件 | 必填键 | 默认值要点 |',
        '|------|--------|-----------|',
    ] + rows
    return '\n'.join(lines) + '\n\n'


def main():
    check = '--check' in sys.argv
    old = io.open(DOC, encoding='utf-8').read()
    if not SECTION_RE.search(old):
        print('[FAIL] 文档里找不到「## 每类型必写键」节: %s' % DOC)
        return 1
    new = SECTION_RE.sub(gen_section(), old, count=1)
    if new == old:
        print('[PASS] 文档表与注册表一致（无需更新）')
        return 0
    if check:
        print('[FAIL] 文档表与注册表漂移（跑 scripts/gen_ui_schema_docs.py 重生成）')
        return 1
    io.open(DOC, 'w', encoding='utf-8', newline='\n').write(new)
    print('updated: %s（「## 每类型必写键」节已由注册表重生成）' % DOC)
    return 0


if __name__ == '__main__':
    sys.exit(main())
