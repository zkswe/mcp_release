# -*- coding: utf-8 -*-
"""出图白名单扫描（T4.2，REMEDIATION-UI-PIPELINE §WS-4）：**只拦新增画图点**。

为什么要有这道闸门：本仓的**唯一出图实现**是 `ui_tools/gen_res.py`（形状 / 抗锯齿 / 倒角 /
透明底口径的唯一实现，实现了 `ui_schema.json` 的 `renderContract` 条目）。但**生产者文件**里
也散落着自己的 PIL 画图/合成代码 —— 那就是「多源各自画图、视觉口径漂移」的来源
（见 REMEDIATION-UI-PIPELINE.md §1 现状证据）。一次性重构是 T5 的事；本闸门先把血止住：
**把现有画图点登记成基线，只拦新增**。

口径（唯一真源 = 本文件的 `PRODUCERS` 常量 + 下面六个原语；要扩面先改这里、再评审）：

  扫描范围 = `PRODUCERS` 里的**生产者文件**。**不扫全仓**：`gen_res.py` 是**允许**画图的
  唯一实现；`json2img.py` 是渲染器、`tools/qa/*` 与 `tests/*` 是审计/断言，都不属本闸门范围。

  命中 = 「自己画 / 合成形状」的 PIL 原语（**恰好六个，不扩不缩**）：
      `ImageDraw` ／ `Image.new(` ／ `ImageFilter` ／ `ImageChops` ／
      `.alpha_composite(` ／ `Image.blend(`
  **只读取图不算**：`Image.open` / `.convert` / `.resize` / `.getpixel`（量尺寸、读像素）一律不计。
  `from PIL import X as Y` 这类**别名会解析**（否则改个别名就能把画图点藏起来；本仓
  `ui_tools/html2json.py` 正是 `from PIL import Image as _I` → `_I.new(...)` 的写法）。
  已知不覆盖：`from PIL.Image import new` 形式的裸函数导入（本仓实测 0 处）、注释行不算
  （写文档时提到原语名不该判红）、字符串里出现原语名会算命中（保守方向）。

三层口径（与 `scripts/lint_silent_except.py` 同构，同一套 `--check/--update/退出码` 习惯）：

  1. 历史基线 `scripts/draw_sites_baseline.txt`
     —— 已登记的存量画图点，键 = **相对路径**，值 = **命中数**（是计数不是清单：
        同一处多写两行也会被抓到）。文件不在基线里却有命中 = FAIL；命中数**超过**基线 = FAIL。
  2. 白名单 `scripts/draw_sites_whitelist.txt`
     —— 显式豁免，**每条必须写理由**，格式（`::` 分隔）：
         `<相对路径>  ::  <为什么这个文件必须自己画图>`
     白名单文件**不参与计数**（豁免生效），但每次运行都会把它连命中数与理由**列出来**（不静默）。
  3. 其余 = 违规 → 退出码 1。处置二选一：把画图点改走 `gen_res`（首选），
     或在白名单登记并写理由（等于承认"这个文件确实得自己画"，要走评审）。

用法（仓库根或任意位置）：
    python scripts/lint_draw_sites.py                    # 检查（等价 --check）
    python scripts/lint_draw_sites.py --check             # 检查
    python scripts/lint_draw_sites.py --update            # 重写基线（只允许下调 / 登记新文件；
                                                          #  命中数上升 → 拒绝并 rc≠0）
    python scripts/lint_draw_sites.py --json out.json     # 附机器可读结果（'-' = stdout）
    python scripts/lint_draw_sites.py --root <dir> --baseline <path> --whitelist <path>
                                                          # 供用例造夹具（默认都在 --root 下）
"""
import argparse
import io
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE_REL = os.path.join('scripts', 'draw_sites_baseline.txt')
WHITELIST_REL = os.path.join('scripts', 'draw_sites_whitelist.txt')

# ⚠️ 唯一真源：扫描范围（生产者文件）。以后新增前端/生成器**只改这一处**（改这里就是改闸门口径）。
PRODUCERS = ('ui_tools/html2json.py', 'templates/ui_blocks/compose.py', 'translate_tools.py')

# 六个命中原语（标签 → PIL 名 / 尾巴正则）。`alpha_composite` 是实例方法，任何接收者都算。
_FAMILIES = (('ImageDraw', 'ImageDraw', ''),
             ('Image.new', 'Image', r'\s*\.\s*new\s*\('),
             ('ImageFilter', 'ImageFilter', ''),
             ('ImageChops', 'ImageChops', ''),
             ('alpha_composite', None, r'\.\s*alpha_composite\s*\('),
             ('Image.blend', 'Image', r'\s*\.\s*blend\s*\('))

# 能当别名目标的 PIL 名 → 族内的"种类"。
_ALIAS_KIND = {'Image': 'Image', 'ImageDraw': 'ImageDraw',
               'ImageFilter': 'ImageFilter', 'ImageChops': 'ImageChops'}

# `from PIL import a, b as c` / `from PIL.Image import ...`（支持括号跨行）。
_FROM_PIL = re.compile(r'^[ \t]*from[ \t]+PIL(?:\.[A-Za-z_]\w*)?[ \t]+import[ \t]+'
                       r'(?:\(([^)]*)\)|([^\n(]+))', re.M)
# `import PIL.Image as X`
_IMPORT_PIL_AS = re.compile(r'^[ \t]*import[ \t]+PIL\.([A-Za-z_]\w*)[ \t]+as[ \t]+([A-Za-z_]\w*)', re.M)
# PIL import 语句所在行：这类行只按**字面名**计数（否则 `ImageDraw as _D` 会算两次）。
_PIL_IMPORT_LINE = re.compile(r'^[ \t]*(?:from[ \t]+PIL\b|import[ \t]+PIL\b)')
_IMPORT_ITEM = re.compile(r'^([A-Za-z_]\w*)(?:[ \t]+as[ \t]+([A-Za-z_]\w*))?$')


def _aliases(src):
    """→ {别名: 种类}。只认 `from PIL import …` / `import PIL.<mod> as …` 两种写法。"""
    out = {}
    for paren, plain in _FROM_PIL.findall(src):
        for item in (paren or plain).split(','):
            m = _IMPORT_ITEM.match(item.strip())
            if not m:
                continue
            name, alias = m.group(1), m.group(2) or ''
            kind = _ALIAS_KIND.get(name)
            if kind and alias and alias != name:
                out[alias] = kind
    for mod, alias in _IMPORT_PIL_AS.findall(src):
        kind = _ALIAS_KIND.get(mod)
        if kind and alias != mod:
            out[alias] = kind
    return out


def _patterns(aliases):
    """→ ((标签, 仅字面名正则, 含别名正则), …)；含别名正则用于普通代码行。"""
    def rx(kind, tail, canon_only):
        names = [kind]
        if not canon_only:
            # 长别名在前，避免 `_I` 抢先匹配 `_Im`（正则回溯能兜住，但别指望它）。
            names += sorted((a for a, k in aliases.items() if k == kind), key=len, reverse=True)
        return re.compile(r'\b(?:%s)\b%s' % ('|'.join(re.escape(n) for n in names), tail))

    out = []
    for label, kind, tail in _FAMILIES:
        if kind is None:                          # alpha_composite：无模块名可别名
            pat = re.compile(tail)
            out.append((label, pat, pat))
        else:
            out.append((label, rx(kind, tail, True), rx(kind, tail, False)))
    return tuple(out)


def sites(path):
    """扫一个文件 → [(行号, 原语, 该行片段)]；命中 = 出现次数（一行两处算两处）。

    只读取图不计；注释行（`#` 开头）不计 —— 文档里提一句 `Image.new` 不该判红。
    读不动（非 UTF-8 / IO 错）就抛出去，由调用方判 FAIL（**不静默跳过**）。
    """
    with io.open(path, encoding='utf-8') as f:
        src = f.read()
    pats = _patterns(_aliases(src))
    out = []
    for i, line in enumerate(src.split('\n'), 1):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        is_import = bool(_PIL_IMPORT_LINE.match(line))
        for label, canon, with_alias in pats:
            for _ in (canon if is_import else with_alias).finditer(line):
                out.append((i, label, s[:110]))
    return out


def scan(root):
    """扫 `PRODUCERS` → ({相对路径: [(行,原语,片段)]}, {相对路径: 错误说明})。"""
    found, errs = {}, {}
    for rel in PRODUCERS:
        p = os.path.join(root, rel.replace('/', os.sep))
        if not os.path.isfile(p):
            errs[rel] = 'PRODUCERS 里的文件不存在'
            continue
        try:
            found[rel] = sites(p)
        except (OSError, UnicodeDecodeError) as e:
            errs[rel] = '读取失败：%s' % e
    return found, errs


def _breakdown(entries):
    """[(行,原语,片段)] → 'Image.new=4 ImageDraw=2 …'（按族固定顺序，便于 diff）。"""
    cnt = {}
    for _ln, label, _seg in entries:
        cnt[label] = cnt.get(label, 0) + 1
    order = [f[0] for f in _FAMILIES]
    return ' '.join('%s=%d' % (k, cnt[k]) for k in order if cnt.get(k))


def read_baseline(path):
    """→ ({相对路径: 命中数}, [无法解析的行])。格式：`<相对路径>  hits=<N>  # 备注`。"""
    hits, bad = {}, []
    if not os.path.isfile(path):
        return hits, bad
    with io.open(path, encoding='utf-8') as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            head = s.split('  # ')[0].strip()
            m = re.match(r'^(\S+)[ \t]+hits=(\d+)$', head)
            if not m:
                bad.append('无法解析：%s' % s)
                continue
            rel = m.group(1).replace('\\', '/')          # 手写 Windows 分隔符也认
            if rel in hits:
                bad.append('重复条目：%s' % rel)
                continue
            hits[rel] = int(m.group(2))
    return hits, bad


def read_whitelist(path):
    """→ ({相对路径: 理由}, [缺理由的条目])。格式：`<相对路径>  ::  <理由>`。"""
    wl, noreason = {}, []
    if not os.path.isfile(path):
        return wl, noreason
    with io.open(path, encoding='utf-8') as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            key, _, reason = s.partition('::')
            key, reason = key.strip().replace('\\', '/'), reason.strip()
            if not key:
                noreason.append('无法解析：%s' % s)
                continue
            wl[key] = reason
            if not reason:
                noreason.append(key)
    return wl, noreason


def write_baseline(path, hits, detail):
    """重写基线（只写有命中的文件；0 命中的文件不登记 = 以后一有命中就 FAIL）。"""
    lines = ['# 出图白名单扫描基线（生产者文件里自己画/合成形状的 PIL 原语命中数）。',
             '# 键 = 相对路径，值 = 命中数。文件不在基线里却有命中 → FAIL；命中数超过基线 → FAIL。',
             '# 格式：<相对路径>  hits=<命中数>  # 命中原语明细（人读；闸门只认 hits=<N>）。',
             '# 处置：把画图点改走唯一出图实现 ui_tools/gen_res.py，或在 '
             'scripts/draw_sites_whitelist.txt 登记并写理由。',
             '# 重建/下调：python scripts/lint_draw_sites.py --update（命中数上升会被拒绝）']
    for rel in sorted(hits):
        lines.append('%s  hits=%d  # %s' % (rel, hits[rel], _breakdown(detail.get(rel, []))))
    d = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')


def _dump_json(path, report):
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if path == '-':
        print(text)
        return
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text + '\n')
    print('json -> %s' % path)


def _write_check_report(a, root, found, errs, base, bad_base, wl, wl_noreason):
    """--check：打印逐文件数字 + 结论，返回 (report, fail 数)。"""
    exempt = [r for r in PRODUCERS if r in wl]
    print('=' * 72)
    print('draw-sites lint  (root=%s)' % root)
    print('=' * 72)
    print('baseline=%s' % a.baseline)
    print('whitelist=%s%s' % (a.whitelist, '' if os.path.isfile(a.whitelist) else '  (不存在)'))
    print('producers=%d  baseline=%d  whitelist=%d  已豁免 %d 个文件'
          % (len(PRODUCERS), len(base), len(wl), len(exempt)))

    fails = list('基线行%s' % b for b in bad_base)
    rows, total = {}, 0
    for rel in PRODUCERS:
        if rel in errs:
            fails.append('%s：%s' % (rel, errs[rel]))
            rows[rel] = {'path': rel, 'hits': None, 'baseline': base.get(rel), 'status': 'missing'}
            print('  [FAIL] %s  %s（请更新 PRODUCERS 常量，别让闸门静默漏扫）' % (rel, errs[rel]))
            continue
        entries = found[rel]
        n = len(entries)
        total += n
        old = base.get(rel)
        rows[rel] = {'path': rel, 'hits': n, 'baseline': old,
                     'lines': [{'line': ln, 'pattern': p, 'text': t} for ln, p, t in entries]}
        if rel in wl:
            rows[rel]['status'] = 'exempt'
            continue
        if old is None:
            st = 'new' if n else 'ok'
        elif n > old:
            st = 'increased'
        elif n < old:
            st = 'decreased'
        else:
            st = 'ok'
        rows[rel]['status'] = st
        base_txt = '未登记' if old is None else str(old)
        if st == 'new':
            fails.append('%s：新增画图点（基线未登记，hits=%d）' % (rel, n))
            print('  [FAIL] %s  hits=%d  baseline=%s  ← 新增画图点' % (rel, n, base_txt))
            for ln, p, t in entries:
                print('           %s:%d | %s | %s' % (rel, ln, p, t))
        elif st == 'increased':
            fails.append('%s：命中数上升（%d > 基线 %d）' % (rel, n, old))
            print('  [FAIL] %s  hits=%d  baseline=%s  ← 命中数上升（新增画图点）' % (rel, n, base_txt))
            for ln, p, t in entries:
                print('           %s:%d | %s | %s' % (rel, ln, p, t))
        elif st == 'decreased':
            print('  [PASS] %s  hits=%d  baseline=%s  ← 命中数下降，可下调基线'
                  '（python scripts/lint_draw_sites.py --update）' % (rel, n, base_txt))
        else:
            print('  [PASS] %s  hits=%d  baseline=%s' % (rel, n, base_txt))

    # 白名单豁免：**列出来**（不静默），缺理由的直接 FAIL。
    for rel in exempt:
        n = len(found.get(rel, []))
        reason = wl[rel]
        rows[rel]['reason'] = reason
        if not reason:
            continue                       # 缺理由 → 下面 wl_noreason 里判 FAIL
        if not n:
            print('  [WARN] 白名单文件当前无画图点（可移出白名单）：%s' % rel)
        print('  [SKIP] 已豁免：%s  hits=%d  理由：%s' % (rel, n, reason))
    for rel, reason in sorted(wl.items()):
        if rel not in PRODUCERS:
            print('  [WARN] 白名单条目不是 PRODUCERS 文件（不参与扫描，可移除）：%s' % rel)
            rows[rel] = {'path': rel, 'hits': None, 'baseline': None,
                         'status': 'whitelist-out-of-scope', 'reason': reason}
    for k in wl_noreason:
        fails.append('白名单条目缺理由：%s' % k)
        print('  [FAIL] 白名单条目缺理由（必须写清"为什么这个文件必须自己画图"）：%s' % k)
    for rel in sorted(base):
        if rel not in PRODUCERS:
            print('  [WARN] 基线条目不在 PRODUCERS 内（未扫描，可移除）：%s' % rel)
        elif rel in wl:
            print('  [WARN] 基线条目已被白名单豁免（可从基线移除）：%s' % rel)
    if not os.path.isfile(a.whitelist):
        print('  [INFO] 白名单文件不存在 → 未豁免任何文件：%s' % a.whitelist)

    print('-' * 72)
    print('total=%d  fail=%d  %s' % (total, len(fails), 'OK' if not fails else 'FAILED'))
    report = {'mode': 'check', 'root': root, 'baseline': a.baseline, 'whitelist': a.whitelist,
              'producers': list(PRODUCERS), 'files': [rows[r] for r in PRODUCERS]
              + [rows[r] for r in sorted(rows) if r not in PRODUCERS],
              'exempt': [r for r in exempt], 'exemptCount': len(exempt),
              'baselineMalformed': bad_base, 'whitelistWithoutReason': wl_noreason,
              'totalHits': total, 'fail': len(fails), 'ok': not fails, 'failures': fails}
    return report, len(fails)


def _run_update(a, root, found, errs, base, bad_base, wl):
    """--update：只允许下调或登记新文件；任何文件命中数上升 → 拒绝（不动基线文件）。"""
    exempt = [r for r in PRODUCERS if r in wl]
    cur, refuse = {}, []
    for rel in PRODUCERS:
        if rel in errs:
            refuse.append('%s：%s' % (rel, errs[rel]))
            continue
        if rel in wl:
            continue
        n = len(found[rel])
        if n:
            cur[rel] = n
        old = base.get(rel)
        if old is not None and n > old:
            refuse.append('%s：命中数上升 %d -> %d（新增画图点）' % (rel, old, n))
    refuse += ['基线行%s' % b for b in bad_base]
    print('=' * 72)
    print('draw-sites lint --update  (root=%s)' % root)
    print('=' * 72)
    for rel in PRODUCERS:
        if rel in errs:
            print('  [FAIL] %s  %s' % (rel, errs[rel]))
            continue
        n = len(found[rel])
        old = base.get(rel)
        tag = '豁免' if rel in wl else ('新登记' if old is None and n else
                                       ('下调' if old is not None and n < old else
                                        ('不变' if old == n else '0 命中（不登记）')))
        print('  %s  hits=%s  baseline=%s  [%s]'
              % (rel, n, '豁免' if rel in wl else ('未登记' if old is None else old), tag))
    for rel in sorted(base):
        if rel not in PRODUCERS:
            print('  [WARN] 基线条目被移除（不在 PRODUCERS 内）：%s' % rel)
        elif rel in wl and rel not in cur:
            print('  [INFO] 基线条目因白名单豁免而移除：%s（豁免不参与计数 → 不再需要基线）' % rel)
    report = {'mode': 'update', 'root': root, 'baseline': a.baseline, 'whitelist': a.whitelist,
              'producers': list(PRODUCERS), 'current': cur, 'previous': base,
              'exempt': exempt, 'refused': refuse, 'ok': not refuse}
    if refuse:
        for r in refuse:
            print('  [FAIL] 拒绝 --update：%s' % r)
        print('  → 命中数上升 = 新增了画图点。基线**没有被改动**。两条路：')
        print('     ① 把画图点改走唯一出图实现 ui_tools/gen_res.py（首选）；')
        print('     ② 确实必须自己画 → 在 %s 登记该文件并写理由（走评审）。' % a.whitelist)
        print('-' * 72)
        print('total=%d  fail=%d  FAILED' % (sum(cur.values()), len(refuse)))
        report['fail'] = len(refuse)
        return report, len(refuse)
    write_baseline(a.baseline, cur, found)
    for rel in sorted(cur):
        if rel not in base:
            print('  [WARN] 新登记进基线：%s（hits=%d）—— 请确认这是**存量**画图点，不是新增'
                  % (rel, cur[rel]))
    print('baseline updated: %s (%d files, %d hits)'
          % (os.path.relpath(a.baseline, root).replace('\\', '/'), len(cur), sum(cur.values())))
    print('-' * 72)
    print('total=%d  fail=0  OK' % sum(cur.values()))
    report['totalHits'] = sum(cur.values())
    report['fail'] = 0
    return report, 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='出图白名单扫描：拦生产者文件里新增的 PIL 画图点')
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--check', action='store_true', help='检查（默认动作）')
    g.add_argument('--update', action='store_true', help='重写基线（只允许下调/登记新文件）')
    ap.add_argument('--root', default=BASE, help='扫描根（默认仓库根；用例可指向夹具树）')
    ap.add_argument('--baseline', default='', help='基线路径（默认 <root>/scripts/draw_sites_baseline.txt）')
    ap.add_argument('--whitelist', default='', help='白名单路径（默认 <root>/scripts/draw_sites_whitelist.txt）')
    ap.add_argument('--json', default='', help="把机读结果写到该路径（'-' = stdout）")
    a = ap.parse_args(argv)

    root = os.path.abspath(a.root)
    a.baseline = os.path.abspath(a.baseline) if a.baseline else os.path.join(root, BASELINE_REL)
    a.whitelist = os.path.abspath(a.whitelist) if a.whitelist else os.path.join(root, WHITELIST_REL)

    found, errs = scan(root)
    base, bad_base = read_baseline(a.baseline)
    wl, wl_noreason = read_whitelist(a.whitelist)

    if a.update:
        report, fails = _run_update(a, root, found, errs, base, bad_base, wl)
    else:
        report, fails = _write_check_report(a, root, found, errs, base, bad_base, wl, wl_noreason)
    if a.json:
        _dump_json(a.json, report)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
