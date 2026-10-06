# -*- coding: utf-8 -*-
"""发布版形态门禁：`ui_tools/*.py` 是**转发薄壳**，实现在 `bin/zkuitool/`。

为什么单列一条（2026-10-06 定）：发布版把渲染/出图/校验的实现体收进 Cython 编译的
工具箱（`bin/zkuitool/zkuitool.exe`），`ui_tools/*.py` 只留签名与转发 —— 于是
「双份 ui_tools 哈希一致」（比源码副本）在发布版**不适用**（sync_ui_tools 返回 2）。
少了那条，就必须补上**本形态自己的**判据，否则「薄壳化」这件事没人验：

  ① `ui_tools/_zktool.py` 在（转发层）；`bin/zkuitool/zkuitool.exe` 在（工具箱）
  ② 工具箱自检通过（`zkuitool selfcheck`：全部子命令可载入）
  ③ 引擎模块都是薄壳：体积远小于源码版 + 含 `_zktool` 转发 + **不含实现特征**
     （`import PIL` / `import numpy` / `def draw_` / 大段函数体）
  ④ 明文白名单确实在（`ui_schema.json`、`ui_schema_loader.py`、`ui_emit.py`）
  ⑤ MCP 侧 import 得通（`check_all` / `ui_compile` / `json2html` / `ui_editor` …）

退出码：0=通过 / 1=失败 / 2=不是薄壳形态（源形态或干净 clone，本检查不适用）。
"""
import io
import os
import subprocess
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception as e:                    # noqa: BLE001 —— 不静默：说清为什么不重配
        sys.stderr.write('[NOTE] stdout 不支持 UTF-8 重配（判据不受影响）：%s\n' % e)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(BASE, 'ui_tools')

# 引擎模块（发布版应为薄壳）
ENGINE = ['check_all', 'device_screenshot', 'gen_res', 'html2json', 'json2html',
          'region_attrib', 'ui_compile', 'ui_diff', 'ui_edit_apply', 'ui_editor',
          'json2img', 'gen_ring', 'wysiwyg_diff', 'corner_audit', 'alpha_bg_audit',
          'zero_color_audit', 'font_subset_by_project']

# 明文随包（LLM/脚本要读的东西）
PLAIN = ['ui_schema.json', 'ui_schema_loader.py', 'ui_emit.py']

# 薄壳里不该出现的实现特征
SMOKE_IMPL = ('import PIL', 'from PIL', 'import numpy', 'def draw_', 'ImageDraw',
              'ImageFont', 'coverage_ring', 'rounded_rect_ss')

MAX_STUB_BYTES = 20000          # 薄壳只有签名+转发；源码版引擎模块都 >20 KB


def main():
    if not os.path.isfile(os.path.join(UI, '_zktool.py')):
        print('[SKIP] 不是薄壳形态（无 ui_tools/_zktool.py）→ 发布形态检查不适用')
        return 2
    bad = []

    exe_dir = os.path.join(BASE, 'bin', 'zkuitool')
    exe = os.path.join(exe_dir, 'zkuitool.exe')
    if not os.path.isfile(exe):
        alt = os.path.join(BASE, 'bin', 'zkuitool.exe')          # 单文件形态兜底
        exe = alt if os.path.isfile(alt) else exe
    if not os.path.isfile(exe):
        bad.append('缺 bin/zkuitool/zkuitool.exe（工具箱未随包）')
    else:
        r = subprocess.run([exe, 'selfcheck'], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=300)
        if r.returncode != 0:
            tail = ((r.stderr or '') + (r.stdout or '')).strip().splitlines()[-2:]
            bad.append('zkuitool selfcheck 失败：%s' % ' | '.join(tail))
        else:
            print('[PASS] zkuitool selfcheck：%s' % (r.stdout or '').strip().splitlines()[-1][:80])

    for m in ENGINE:
        p = os.path.join(UI, m + '.py')
        if not os.path.isfile(p):
            bad.append('缺薄壳 ui_tools/%s.py' % m)
            continue
        src = io.open(p, encoding='utf-8', errors='replace').read()
        size = len(src.encode('utf-8'))
        if size > MAX_STUB_BYTES:
            bad.append('ui_tools/%s.py 体积 %d B 超薄壳上限（疑带实现）' % (m, size))
        if '_zktool' not in src:
            bad.append('ui_tools/%s.py 未走 _zktool 转发' % m)
        for probe in SMOKE_IMPL:
            if probe in src:
                bad.append('ui_tools/%s.py 含实现特征 %r' % (m, probe))

    for f in PLAIN:
        if not os.path.isfile(os.path.join(UI, f)):
            bad.append('缺明文文件 ui_tools/%s' % f)

    # MCP 侧 import 得通（薄壳 + 转发层）
    probe = ('import sys; sys.path.insert(0, %r)\n'
             'import check_all, ui_compile, json2html, ui_editor, device_screenshot, ui_diff\n'
             'print("imports ok")\n') % UI
    r = subprocess.run([sys.executable, '-c', probe], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=300)
    if r.returncode != 0 or 'imports ok' not in (r.stdout or ''):
        bad.append('MCP 侧 import 薄壳失败：%s'
                   % ((r.stderr or '').strip().splitlines()[-1:][0][:80] if r.stderr else '?'))

    if bad:
        print('[FAIL] 发布形态（薄壳 + 工具箱）%d 项：' % len(bad))
        for b in bad[:10]:
            print('   ' + b)
        return 1
    print('[PASS] 发布形态：薄壳 %d 个 + 工具箱在 + 明文 %d 个 + MCP import 通'
          % (len(ENGINE), len(PLAIN)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
