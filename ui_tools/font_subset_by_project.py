# -*- coding: utf-8 -*-
"""按工程实际用到的字符裁剪字库（极小字库）。

⚠️ **优先级（2026-10-05 口径）——这是「存储/内存异常」专用的口子，不是日常首选**：
  · 日常缺中文 → **先选现成三档**：`flythings_build_ui_flow(font_tier='common'|'full'|'multi')`；
    不知道选哪档就问 `flythings_check_project_deps`（返回体 `fontTiers` = 三档菜单 +
    按本工程实际字集算的**推荐档** + 现工程档位 + 可执行下一步）。
  · **只有**设备 tmpfs / 存储装不下现成档（一次 fun launch 要推 libzkgui.so + font + ftu +
    EasyUI.cfg，字库是最大头 → OOM 杀 zkgui、设备重启）时才用本工具把字库压到数十 KB。
  · 判据与处置顺序见 `knowledge/devflow/device-deploy-budget.md` §3。

用法:
  python ui_tools/font_subset_by_project.py <项目根> [--src <源ttf>] [--out <输出ttf>]

收集来源: src/**/*.cc|.cpp|.h 与 ui/*.html|*.json 里出现的所有非 ASCII 字符 + ASCII 可见字符 + 常用标点。
产出: <项目根>/font/font.ttf（默认）
"""
import argparse
import os
import sys

from fontTools import subset

# 源字库真源 = 仓内 `components/fonts/fonts/`（与 device_font_check.TIERS / preflight_spec.json
# 同一批文件）。2026-10-05 修（MCP-MODULE-MAP P1-9）：原先指向 ../FlyThings_mcp_open/... ——
# 那是 workspace 布局下的路径，**本检出不存在** → 不传 --src 必然 rc=2。
DEFAULT_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           '..', 'components', 'fonts', 'fonts',
                           'zkswe-hans-common.ttf')
EXTRA = set(u'　、。〈〉《》「」『』【】（）·—…‘’“”－＋／％＃：；，．！？～￥')
ASCII = [chr(c) for c in range(0x20, 0x7F)]


def collect_chars(project_root):
    chars = set(ASCII) | EXTRA
    exts = ('.cc', '.cpp', '.h', '.hpp', '.html', '.json', '.tr', '.xml')
    for root, _dirs, files in os.walk(project_root):
        # 构建产物目录**两代都跳**（09-28 起 `.fun/` 改名 `.fsc/`）：产物是工程内容的副本，
        # 不会带来新字符，跳过不丢字；只跳一代会让新一代工程多扫一遍副本。
        if (os.sep + '.fun' in root or os.sep + '.fsc' in root
                or os.sep + '.git' in root):
            continue
        for fn in files:
            if not fn.endswith(exts):
                continue
            p = os.path.join(root, fn)
            try:
                with open(p, 'r', encoding='utf-8', errors='ignore') as fp:
                    text = fp.read()
            except OSError as e:
                print('  跳过 %s (%s)' % (p, e))
                continue
            chars |= {ch for ch in text if ord(ch) > 0x7F}
    return chars


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project_root')
    ap.add_argument('--src', default=DEFAULT_SRC)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    src = os.path.abspath(args.src)
    if not os.path.isfile(src):
        print('源字库不存在: %s' % src)
        print('  → 正常做法是**先选现成档**（font_tier），不要一上来就裁：')
        print('     flythings_check_project_deps → fontTiers（菜单 + 按本工程字集的推荐档）')
        print('  → 确实要裁（存储/内存异常）时用 --src 指到仓内真源，例如：')
        print('     --src components/fonts/fonts/zkswe-hans-full.ttf')
        return 2

    chars = collect_chars(os.path.abspath(args.project_root))
    cps = sorted({ord(c) for c in chars})
    out = args.out or os.path.join(args.project_root, 'font', 'font.ttf')
    os.makedirs(os.path.dirname(out), exist_ok=True)

    subset.main([src,
                 '--unicodes=' + ','.join('U+%04X' % c for c in cps),
                 '--output-file=' + out,
                 '--layout-features=',
                 '--no-hinting',
                 '--desubroutinize',
                 '--name-IDs=*',
                 '--recommended-glyphs',
                 '--drop-tables+=DSIG'])

    print('字符数 %d（汉字 %d）' % (len(cps), len([c for c in cps if c > 0x7F])))
    print('源字库 %.1f KB -> 产出 %.1f KB  %s'
          % (os.path.getsize(src) / 1024.0, os.path.getsize(out) / 1024.0, out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
