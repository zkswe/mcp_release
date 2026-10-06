# -*- coding: utf-8 -*-
"""T5.1：生成「发射口径对账」快照（发射层 vs 前端自带发射） —— `ui_emit`（唯一发射层）vs `html2json`（前端自带发射）。

对账维度（每个控件类型）：
  · `missingRequired`：注册表 required 键里，前端产物**没写**的（真缺陷：字段不全 → 真机隐患）
  · `valueDiffs`：前端写了、但取值与发射层默认不同的键（**登记制**：要么是有意为之并写理由，
    要么就是漂移 → 修）
  · `extraKeys`：前端写了、注册表未声明的键（与 ui_compile 的 SCH004 同源）

输出：`ui_tools/emit_conformance.json`（快照；`tests/test_emit_conformance.py` 重算对比，漂移即红）。
用法：python scripts/gen_emit_conformance.py [--check]   # --check 只比对（rc=1 = 快照过期）
"""
import io
import json
import os
import sys
try:                       # Windows 控制台/重定向默认 GBK：报告里若有编不出的字符，
    sys.stdout.reconfigure(encoding='utf-8')   # print 会抛 UnicodeEncodeError 把失败本身藏掉
except Exception:          # （2026-10-06：门禁委派本脚本时正是这个崩法）
    pass
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, 'ui_tools'))
import html2json as H                                       # noqa: E402
import ui_emit as E                                         # noqa: E402
import ui_schema_loader as US                               # noqa: E402

OUT = os.path.join(BASE, 'ui_tools', 'emit_conformance.json')

HTML = '''<!doctype html><html><body>
<div class="screen" data-res="480x272" data-bg="#101418">
  <div class="card" data-caption="WinCard" data-x="10" data-y="10" data-w="300" data-h="120"></div>
  <p class="text" data-caption="TvTitle" data-x="20" data-y="20" data-w="200" data-h="30">标题</p>
  <button class="btn" data-caption="BtnOk" data-x="20" data-y="60" data-w="120" data-h="40">确定</button>
  <div class="input" data-caption="EdName" data-x="20" data-y="110" data-w="200" data-h="36"></div>
  <div class="bar" data-caption="SkLevel" data-x="20" data-y="160" data-w="240" data-h="30"></div>
</div></body></html>'''


def _html2json_controls():
    tmp = tempfile.mkdtemp(prefix='emit_conf_')
    try:
        src = os.path.join(tmp, 'p.html')
        io.open(src, 'w', encoding='utf-8', newline='\n').write(HTML)
        out = os.path.join(tmp, 'p.json')
        r = H.html2json(src, out, res='480x272')
        if not r.get('success') or not os.path.isfile(out):
            return {}, 'html2json 没出页面：%s' % (r.get('error') or r)
        page = json.load(io.open(out, encoding='utf-8'))
        ctrls = {}
        for k, v in page.items():
            if isinstance(v, dict) and '__' in k:
                ctrls[k] = v
        return ctrls, ''
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def _defaults(tname):
    """发射层默认值（含 caption/position 这类必填但由调用方给的键，跳过比较）。"""
    return dict(E.DEFAULT_BY_TYPE.get(tname) or {})


SKIP = ('caption', 'position', 'id', 'text')

REASONS = {'alignment': '编码口径不同：html2json 写 36/37，发射层写 0/5（位模型 5≡37 已见于注册表；0 与 36 的**等价性未实测**）→ 待真机各出一张对齐样例核对，核完在此写结论',
    'colorTab': 'html2json 只写用到的槽（color0），发射层写五槽（未用恒 -1）——引擎按缺省补，语义等价；差异属**编码形态**，不是取值冲突',
    'bgColorTab': '同 colorTab（编码形态）',
    'hintTextColor': '默认值口径不同（html2json 0 = 黑 vs 发射层 0x808080 灰）→ 待确认哪个是 IDE 真源',
    'touchable': '默认值口径不同（html2json seekbar 写 False；注册表/发射层 True——滑条不可触摸等于点不动，**倾向发射层对**）→ 待真机核',
    '_missingRequired': '前端产物**缺注册表必填键** = 字段全集铁律的缺口（真缺陷，不是编码差异）；未修前由 `ui_compile` 报 SCH002（默认不阻断 pack，`strict_ui=True` 拦）'}                # 由调用方给/内容相关，不作口径对比


def compare():
    ctrls, err = _html2json_controls()
    rep = {'schema': 1,
           'authority': ('发射口径对账快照：真源 = `ui_tools/ui_emit.py`（唯一发射层）；'
                         '对照方 = `ui_tools/html2json.py` 的实际产物。由 '
                         '`tests/test_emit_conformance.py` 重算对比，漂移即红。'),
           'updated': '2026-10-05', 'html2jsonError': err,
           '_reasons': REASONS, 'types': {}}
    for key, ctl in sorted(ctrls.items()):
        tname = key.split('__')[0]
        if tname not in E.DEFAULT_BY_TYPE:
            continue
        req = set(US.required_fields(tname))
        have = set(ctl) - {'__container', '__listview'}
        miss = sorted(req - have)
        dflt = _defaults(tname)
        diff = {}
        for k, v in sorted(dflt.items()):
            if k in SKIP or k not in ctl:
                continue
            if ctl[k] != v:
                diff[k] = {'html2json': ctl[k], 'uiEmit': v}
        reg = set(US.load()['controls'].get(tname, {}).get('fields', {}))
        extra = sorted(k for k in have if k not in reg)
        rep['types'][tname] = {'sample': key, 'missingRequired': miss,
                               'valueDiffs': diff, 'extraKeys': extra}
    return rep


def compose_report(specs=('complex_320x240', 'complex_1024x600')):
    """跑 compose 自带 example → 按类型统计字段完整性（**不比取值**：取值来自 _tokens/块参数）。"""
    import shutil
    import subprocess
    import tempfile
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(base, 'templates', 'ui_blocks', 'compose.py')
    out = {'specs': [], 'types': {}, 'errors': []}
    for name in specs:
        spec = os.path.join(base, 'templates', 'ui_blocks', 'examples', name, 'spec.json')
        if not os.path.isfile(spec):
            out['errors'].append('%s：spec 不存在' % name)
            continue
        tmp = tempfile.mkdtemp(prefix='emit_conf_cmp_')
        try:
            os.makedirs(os.path.join(tmp, 'ui'), exist_ok=True)
            p = subprocess.run([sys.executable, script, spec, '--project', tmp],
                               capture_output=True, text=True, encoding='utf-8',
                               errors='replace')
            pages = [os.path.join(tmp, 'ui', f) for f in sorted(os.listdir(os.path.join(tmp, 'ui')))
                     if f.endswith('.json')]
            if p.returncode != 0 or not pages:
                out['errors'].append('%s：rc=%s %s' % (name, p.returncode,
                                                       (p.stderr or p.stdout or '')[-160:]))
                continue
            page = json.load(io.open(pages[0], encoding='utf-8'))
            out['specs'].append({'name': name, 'controls': 0})

            def walk(node):
                """递归：**子控件键不进字段统计**（`button__1` 这种是嵌套控件，不是字段）。"""
                for k, ctl in (node or {}).items():
                    if not (isinstance(ctl, dict) and '__' in k):
                        continue
                    tname = k.split('__')[0]
                    if tname in E.DEFAULT_BY_TYPE:
                        st = out['types'].setdefault(
                            tname, {'missingRequired': [], 'extraKeys': [], 'samples': 0})
                        st['samples'] += 1
                        out['specs'][-1]['controls'] += 1
                        have = set(x for x in ctl if '__' not in x)
                        for m in sorted(set(US.required_fields(tname)) - have):
                            if m not in ('caption', 'position', 'id') \
                                    and m not in st['missingRequired']:
                                st['missingRequired'].append(m)
                        declared = set(US.load()['controls'].get(tname, {}).get('fields', {}))
                        for x in sorted(have - declared):
                            if x not in st['extraKeys']:
                                st['extraKeys'].append(x)
                    walk(ctl)

            walk(page)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return out


def main():
    rep = compare()
    rep['compose'] = compose_report()
    rep['_reasons']['composeValueDiffs'] = (
        'compose 的控件**取值**来自 `templates/ui_blocks/blocks/_tokens.json` + 块参数（按源稿而定），'
        '与"发射层默认值"对比没有意义 → 本段只比**字段完整性**（missingRequired / extraKeys）；'
        'compose 的 TD-5 段位口径另在同一份快照的 compose.types 里体现。')
    if rep['html2jsonError']:
        print('[FAIL] %s' % rep['html2jsonError'])
        return 1
    snap = OUT
    if '--snapshot' in sys.argv:
        snap = sys.argv[sys.argv.index('--snapshot') + 1]
    if '--check' in sys.argv:
        cur = json.load(io.open(snap, encoding='utf-8')) if os.path.isfile(snap) else None
        if cur != rep:
            print('[FAIL] 发射口径对账快照与实测不一致 → 重生成：python scripts/gen_emit_conformance.py')
            for t in sorted(set(list(rep['types']) + list((cur or {}).get('types', {})))):
                a = (cur or {}).get('types', {}).get(t)
                b = rep['types'].get(t)
                if a != b:
                    print('   %s：\n     快照=%s\n     实测=%s' % (t, a, b))
            return 1
        print('[PASS] 发射口径对账快照与实测一致（%d 类）' % len(rep['types']))
        return 0
    io.open(snap, 'w', encoding='utf-8', newline='\n').write(
        json.dumps(rep, ensure_ascii=False, indent=1) + '\n')
    print('快照 -> %s' % snap)
    cmp_rep = rep.get('compose') or {}
    for t, d in sorted((cmp_rep.get('types') or {}).items()):
        print('  [compose] %-10s 缺必填=%-2d 未声明键=%-2d（样本 %d）%s'
              % (t, len(d['missingRequired']), len(d['extraKeys']), d['samples'],
                 ('缺：%s' % d['missingRequired']) if d['missingRequired'] else ''))
    if cmp_rep.get('errors'):
        print('  [compose] 未能对账的 spec：%s' % cmp_rep['errors'])
    for t, d in sorted(rep['types'].items()):
        print('  %-10s 缺必填=%-2d 取值差异=%-2d 未声明键=%d %s'
              % (t, len(d['missingRequired']), len(d['valueDiffs']), len(d['extraKeys']),
                 ('缺：%s' % d['missingRequired']) if d['missingRequired'] else ''))
        for k, v in d['valueDiffs'].items():
            print('        %s：html2json=%s  uiEmit=%s' % (k, v['html2json'], v['uiEmit']))
        if d['extraKeys']:
            print('        未声明键：%s' % d['extraKeys'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
