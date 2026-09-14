#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gen_font_subset.py —— 把思源黑体裁成三个版本（可复现）

用法（Windows 侧直接跑）：
  python components/fonts/scripts/gen_font_subset.py \
      --src "tools/FlyThingsIDE/bin/configuration/org.eclipse.osgi/551/0/.cp/bundle/font/SourceHanSansCN-Normal.ttf" \
      --out components/fonts/fonts

产出（TTF，均带中文标点/全角/ASCII）：
  1) zkswe-hans-common.ttf  常用中文（GB2312 一级字 3755 + 标点）      —— 设备无中文字库时的**默认**投递版本
  2) zkswe-hans-full.ttf    全中文（CJK 基本区 + 扩展A + 中文标点/全角）
  3) zkswe-hans-multi.ttf   多国语言（全中文 + 拉丁/希腊/西里尔/假名/谚文）

说明：
  · 只保留字形与必要表（去掉 hinting、以及不需要的 layout 表以外的重表），体积可控；
  · 若源字体本身不含某段码位（如 CN 版对部分谚文/假名），pyftsubset 会自动跳过，不报错；
  · 需要 fonttools：pip install fonttools
"""
import argparse
import os
import sys

from fontTools import subset

# ---------------- 码位集合 ----------------
ASCII = list(range(0x0020, 0x007F))

CJK_PUNCT = list(range(0x3000, 0x3040))          # 、。〈〉《》「」…等
FULLWIDTH = list(range(0xFF00, 0xFFF0))          # 全角字符
GENERAL_PUNCT = list(range(0x2000, 0x2070))      # – — ‘ ’ “ ” … 等
CIRCLED = list(range(0x2460, 0x2500))            # ①②③ 常用


def gb2312_level1():
    """GB2312 一级汉字（3755 个，最常用）"""
    out = []
    skipped = 0
    for cp in range(0x4E00, 0x9FA6):
        ch = chr(cp)
        try:
            b = ch.encode('gb2312')
        except UnicodeEncodeError:
            # 该码位不在 GB2312 里（不是错误，是过滤）—— 计数并在最后汇总打印，不静默
            skipped += 1
            continue
        if len(b) == 2 and 0xB0 <= b[0] <= 0xD7:   # 一级区
            out.append(cp)
    if skipped:
        print('  (GB2312 不可编码的码位 %d 个，已跳过)' % skipped)
    return out


def cjk_basic():
    return list(range(0x4E00, 0xA000))               # CJK 基本区 20992


def cjk_exta():
    return list(range(0x3400, 0x4DC0))               # 扩展 A 6592


def cjk_extb():
    return list(range(0x20000, 0x2A6E0))              # 扩展 B 2051（生僻字/人名）


def build_sets():
    common = sorted(set(ASCII + CJK_PUNCT + FULLWIDTH + GENERAL_PUNCT + gb2312_level1()))
    full = sorted(set(common + cjk_basic() + cjk_exta() + CIRCLED))
    multi = sorted(set(full + cjk_extb()
                       + list(range(0x00A0, 0x0250))     # 拉丁补充/扩展
                       + list(range(0x0370, 0x0400))     # 希腊
                       + list(range(0x0400, 0x0530))     # 西里尔
                       + list(range(0x3040, 0x3100))     # 平假名/片假名
                       + list(range(0xAC00, 0xD7A4))     # 谚文音节
                       + list(range(0x2190, 0x2200))     # 箭头
                       + list(range(0x25A0, 0x2600))     # 几何图形（UI 常用）
                       ))
    return common, full, multi


def subset_one(src, dst, codepoints, drop_layout=False):
    args = [
        src,
        '--unicodes=' + ','.join('U+%04X' % c for c in codepoints),
        '--output-file=' + dst,
        '--layout-features=',                       # 不需要复杂排版特性（CJK 不需要）
        '--no-hinting',
        '--desubroutinize',
        '--name-IDs=*',
        '--recommended-glyphs',
        '--drop-tables+=DSIG',
    ]
    subset.main(args)
    return os.path.getsize(dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True, help='思源黑体源文件（常用/全中文用，如 CN Normal）')
    ap.add_argument('--src-multi', default=None,
                    help='多国语言源（需含谚文/假名/扩展B 的完整版）；缺省回落到 --src')
    ap.add_argument('--out', required=True, help='输出目录')
    args = ap.parse_args()

    if not os.path.isfile(args.src):
        print('源字体不存在: %s' % args.src)
        return 2
    src_multi = args.src_multi or args.src
    if not os.path.isfile(src_multi):
        print('多国语言源不存在: %s' % src_multi)
        return 2
    os.makedirs(args.out, exist_ok=True)

    common, full, multi = build_sets()
    jobs = [
        ('zkswe-hans-common.ttf', common, args.src, '常用中文(GB2312一级 %d 字)' % (len(common),)),
        ('zkswe-hans-full.ttf', full, args.src, '全中文(CJK基本+扩展A %d 字)' % (len(full),)),
        ('zkswe-hans-multi.ttf', multi, src_multi, '多国语言(+扩展B/拉丁/希腊/西里尔/假名/谚文 %d 字)' % (len(multi),)),
    ]
    print('源(常用/全中文): %s (%.2f MB)' % (args.src, os.path.getsize(args.src) / 1048576.0))
    print('源(多国语言):   %s (%.2f MB)' % (src_multi, os.path.getsize(src_multi) / 1048576.0))
    for name, cps, src, desc in jobs:
        dst = os.path.join(args.out, name)
        size = subset_one(src, dst, cps)
        print('  -> %-24s %10.1f KB   %s' % (name, size / 1024.0, desc))
    return 0


if __name__ == '__main__':
    sys.exit(main())
