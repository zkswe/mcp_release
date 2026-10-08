# -*- coding: utf-8 -*-
"""logic 回调桩**体检 / 兜底**（op: `flythings_gen_logic_stub`）。

**定位（2026-10-05 起）**：桩的**生成**归工具链 —— `fui pack` 后 `fsc build` 会为新页
生成 `src/logic/<p>Logic.cc`（含 `INIT_UI_EVENT_BINDINGS`、生命周期/触摸钩子）并**追加**缺失的
回调桩（2026-10-05 实测：新页自动建文件；已有文件追加的函数落在文件作用域 EOF，不覆盖原内容）。
本模块只做**体检**：按 `ui/*.json` 的控件表算出「该有哪些桩、缺哪些」，用在**还没打包 /
机器上没有工具链 / 想先看清单**的场合；缺文件时不代建（那是 fsc build 的活）。

为什么还要它：FlyThings 控件回调是**按 caption 拼名**的（`onButtonClick_<Caption>`）——
漏写或拼错一个字 = 「点了没反应」；listview 的 3 条回调缺一条 = 列表永远空白。
所以「换皮 → 换功能」的第一步就是**先知道该有哪些桩**。本模块只生成**空桩 +
TODO 注释**（形状取自 ui_schema 的 `callbacks[].stub`），**业务逻辑由 AI 写在同一个文件里**
（流程步骤 `write-logic`；容器/显示类控件没有桩，走 `findControlByID` + `setXxxListener` 接线）。

回调名与签名**只在 `ui_tools/ui_schema.json` 的 `controls.<类型>.callbacks` 里**
（本模块不另写一份表——照仓库「唯一真源 + 全派生」的纪律；讲解见
`knowledge/uicontrols/widget-code-api.md`）。

⚠️ 生成物要过 `check_all` 的两个字符级口径（见 `knowledge/devflow/activity-code-skeleton.md` §1-1）：
`#8` 括号平衡把注释也算进去 → 注释里不写孤立括号；`#6` 指针核对会认块注释里的
`mXXXPtr` → 桩里不出现控件指针名。
"""
import io
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
_UI_TOOLS = os.path.join(BASE, 'ui_tools')
if getattr(sys, 'frozen', False):          # PyInstaller 打包：ui_tools 随包进 _MEIPASS
    _UI_TOOLS = os.path.join(sys._MEIPASS, 'ui_tools')
if _UI_TOOLS not in sys.path:
    sys.path.insert(0, _UI_TOOLS)
import ui_schema_loader as _uischema       # noqa: E402 回调名唯一真源（ui_schema.json）

_CONTROL_KEY = re.compile(r'^([a-z][a-z0-9]*)__(\d+)$')
_EXISTING_FN = re.compile(r'\b((?:on|get|obtain)[A-Za-z]+_\w+)\s*\(')   # 取组 = 不带尾括号的函数名


def _load_pages(project_root):
    """工程里的 json 布局：支持 `ui/*.json` 与 `ui/<分辨率>/*.json` 两种布局。

    返回 `(pages, bad)`：pages = [(页名, 数据, 路径)]（页名 = 文件名去扩展，对应
    `src/logic/<页名>Logic.cc`）；bad = 读不了/不是合法 JSON 的文件说明（不静默吞）。
    """
    ui_dir = os.path.join(project_root, 'ui')
    if not os.path.isdir(ui_dir):
        return [], []
    cands = []
    for name in sorted(os.listdir(ui_dir)):
        p = os.path.join(ui_dir, name)
        if os.path.isfile(p) and name.endswith('.json'):
            cands.append(p)
        elif os.path.isdir(p):
            cands.extend(os.path.join(p, n) for n in sorted(os.listdir(p))
                         if n.endswith('.json'))
    out, bad = [], []
    for p in cands:
        try:
            with io.open(p, encoding='utf-8') as fh:
                data = json.loads(fh.read())
        except (OSError, ValueError) as e:
            bad.append('%s（%s）' % (os.path.basename(p), type(e).__name__))
            continue
        out.append((os.path.splitext(os.path.basename(p))[0], data, p))
    return out, bad


def _controls_of(page):
    """一页 json 里的控件：[(类型, caption, id)]；递归进 window 类容器。

    key 形如 `button__1`（类型 + 序号），回调名用的是 **caption** 字段，不是序号。
    """
    out = []

    def walk(node):
        if not isinstance(node, dict):
            return
        for k, v in node.items():
            if not isinstance(v, dict):
                continue
            m = _CONTROL_KEY.match(k)
            if m:
                out.append((m.group(1), v.get('caption') or '', v.get('id')))
            walk(v)

    walk(page)
    return out


def _stub_text(ctrl_type, caption, cb):
    """一个回调桩的 C++ 源码（注释里不写孤立括号、不写控件指针名）。"""
    sig = cb['sig'].replace('{Caption}', caption)
    when = cb.get('when') or ''
    note = cb.get('note') or ''
    head = '/* %s —— %s.%s（桩：flythings_gen_logic_stub；TODO 处填业务）%s */' % (
        when, ctrl_type, caption, ('  ' + note) if note else '')
    body = cb.get('stub') or ''
    lines = [head, 'static %s' % sig, '{']
    lines.extend('    ' + ln for ln in body.splitlines() if ln.strip())
    lines.append('}')
    return '\n'.join(lines)


def gen_logic_stub(project_root, page='', dry_run=False):
    """按 `ui/*.json` 的控件表补齐 `src/logic/<页>Logic.cc` 的回调桩。

    - **只补不改**：已存在的同名函数一律跳过，不覆盖调用方写的业务；
    - listview 的 3 条（count / data / click）是一组，会一起给（缺一列表就是空白）；
    - dry_run=True 只回清单不落盘。
    """
    if not os.path.isdir(project_root):
        return {'ok': False, 'op': 'flythings_gen_logic_stub',
                'error': {'code': 'NO_PROJECT', 'msg': '工程目录不存在: %s' % project_root,
                          'retryable': False}}
    all_pages, load_bad = _load_pages(project_root)
    pages = [p for p in all_pages if not page or p[0] == page]
    if not pages:
        return {'ok': False, 'op': 'flythings_gen_logic_stub',
                'error': {'code': 'NO_PAGE' if all_pages else 'NO_UI_JSON',
                          'msg': ('工程里找不到页 %r' % page) if all_pages
                                 else 'ui/ 下没有 json 布局',
                          'hint': ('可用页：%s' % ', '.join(p[0] for p in all_pages)) if all_pages
                                  else '先出 json 布局（flythings_html_to_json / ui 编辑），再回来生成桩',
                          'retryable': True, 'warnings': load_bad}}

    out = []
    written = 0
    for pname, data, _jpath in pages:
        logic_rel = 'src/logic/%sLogic.cc' % pname
        logic_path = os.path.join(project_root, 'src', 'logic', '%sLogic.cc' % pname)
        rec = {'page': pname, 'logic': logic_rel, 'generated': [], 'skipped': []}
        if not os.path.isfile(logic_path):
            rec['error'] = ('缺 %s —— 先 `fui pack` 该页再 `fsc build`（工具链会自动建这个文件，'
                            '含 INIT_UI_EVENT_BINDINGS 与生命周期钩子）；本 op 不代建文件'
                            % logic_rel)
            out.append(rec)
            continue
        with io.open(logic_path, encoding='utf-8', errors='replace') as fh:
            src = fh.read()
        existing = set(_EXISTING_FN.findall(src))
        blocks = []
        for ctrl_type, caption, _cid in _controls_of(data):
            if not caption:
                continue
            for cb in _uischema.callbacks(ctrl_type):
                fn = cb['name'].replace('{Caption}', caption)
                if fn in existing:
                    rec['skipped'].append(fn)
                    continue
                existing.add(fn)
                blocks.append(_stub_text(ctrl_type, caption, cb))
                rec['generated'].append(fn)
        if blocks and not dry_run:
            tail = src if src.endswith('\n') else src + '\n'
            with io.open(logic_path, 'w', encoding='utf-8', newline='') as fh:
                fh.write(tail + '\n' + '\n\n'.join(blocks) + '\n')
            written += len(blocks)
        out.append(rec)

    total_gen = sum(len(r['generated']) for r in out)
    return {'ok': True, 'op': 'flythings_gen_logic_stub', 'mode': 'dry-run' if dry_run else 'write',
            'projectRoot': project_root,
            'pageCount': len(out), 'generatedCount': total_gen, 'writtenCount': written,
            'pages': out,
            'warnings': load_bad,
            'notes': ['只补不改：已存在的同名函数一律跳过，不覆盖业务代码',
                      'listview 的 3 条回调是一组（count/data/click），缺一列表就是空白',
                      '返回值语义：onButtonClick 的 true=吞事件、false=放行',
                      '生成物要过 check_all：注释里别写孤立括号',
                      '回调名/签名真源 = ui_tools/ui_schema.json 的 controls.<类型>.callbacks',
                      '★ 桩只是骨架：**页面逻辑写在同一个 src/logic/<页>Logic.cc 里**（函数体留 (void)x; / return false; 就打包上机 = 点上去没反应）',
                      '★ 容器/显示类控件（pagewindow、scrollwindow、textview、painter…）本来就没有回调桩：在 onUI_init 里 findControlByID 取指针 + setXxxListener/setPageChangeListener 接线',
                      '★ 生成归工具链：fui pack 后 fsc build 会为新页建 logic 文件（含 INIT_UI_EVENT_BINDINGS 与生命周期钩子）并追加缺失的桩；本 op 用于未打包/无工具链/先看清单']}
