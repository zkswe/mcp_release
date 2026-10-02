# -*- coding: utf-8 -*-
"""生成开机 logo（`boot_logo.JPG`）——PC 侧，一次成，**自带体积闸门**。

为什么要有它（2026-09-17 口径）：开机 logo 的落点是设备 **MISC 分区**（不是 logo 分区、更不是 `/res`），
升级方法与 `update.img` 完全一样（TF 卡根目录 / ADB setprop 两套触发）。
于是**唯一硬约束 = 图片体积 ≤ MISC 分区大小**（本板 Z21 = 512 KB）。
这个脚本负责「生成 + 按上限卡体积」，超过上限直接报错，不让它上机。

默认版式：深底 + 顶部品牌细线 + 「主字样 / 副标题 / 标签行」三行居中 + 底部细线。
文案与配色都可改（`--text/--sub/--tag/--bg/--fg/--accent`）。

用法（在 MCP 根目录）：
    python tools/make_boot_logo.py --size 1024x600 --out boot_logo.JPG
    python tools/make_boot_logo.py --size 1024x600 --out boot_logo.JPG \\
        --text ZKSWE --sub "深圳中科世为科技" --tag "FlyThings OS"
    python tools/make_boot_logo.py --size 1024x600 --out boot_logo.JPG --limit-kb 512

字体解析顺序（**不写死本机路径**）：
    ① 环境变量 `FLYTHINGS_LOGO_FONT`（显式指定永远优先）
    ② 常见系统中文字体候选（Windows / Linux / macOS 各一组；Windows 目录取 `%WINDIR%`）
    ③ 都没命中 → PIL 内置位图字体（会告警：中文可能变方块，请用 ① 指一个 ttf/ttc）

超上限时的处理：自动按 `--quality` 起步质量递减重压（92 → 70 一档档降）；
降到 `--min-quality`（默认 70）还超 → **报错退出（码 2）**，并提示改小分辨率/换版式。
生成成功后打印：文件路径、像素、体积、上限、占比。
细节与设备侧触发见 knowledge/devflow/upgrade-pack-image.md §三。
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

DEFAULT_LIMIT_KB = 512                     # 本板 MISC = 512 KB；换板子先 `cat /proc/mtd` 量
DEFAULT_SIZE = '1024x600'                  # Z21 分辨率
FONT_ENV = 'FLYTHINGS_LOGO_FONT'           # 显式指定字体的环境变量
LIMIT_ENV = 'FLYTHINGS_BOOT_LOGO_LIMIT_KB'  # 显式指定体积上限（KB）的环境变量

# 常见系统字体候选：按顺序取第一个存在的（保持跨平台，不写死某一台机器的绝对路径）
FONT_CANDIDATES = {
    'bold': [
        os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'msyhbd.ttc'),
        os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'simhei.ttf'),
        os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'arialbd.ttf'),
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/System/Library/Fonts/PingFang.ttc',
        '/Library/Fonts/Arial Bold.ttf',
    ],
    'normal': [
        os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'msyh.ttc'),
        os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'simsun.ttc'),
        os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'arial.ttf'),
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/System/Library/Fonts/PingFang.ttc',
    ],
}

BG = '#0b1120'          # 深蓝黑底
ACCENT = '#0052d9'      # 品牌蓝（与设备 UI 令牌一致）
FG = '#ffffff'
SUB = '#96a5be'
WARNINGS = []


def warn(msg):
    """记一条告警并回显（不静默：调用方/人都能看到）。"""
    WARNINGS.append(msg)
    print('[warn] %s' % msg)


def hex_color(s, default):
    """`#rrggbb` / `rrggbb` → (r,g,b)；解析不了就告警并回退默认。"""
    t = (s or '').strip().lstrip('#')
    if len(t) == 3:
        t = ''.join(c * 2 for c in t)
    if len(t) != 6:
        warn('颜色 %r 不合法，回退 %s' % (s, default))
        t = default.lstrip('#')
    try:
        return tuple(int(t[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError as e:
        warn('颜色 %r 解析失败（%s），回退 %s' % (s, e, default))
        return hex_color(default, default)


def pick_font(size, bold=False):
    """字体解析：env → 候选表 → PIL 内置（内置会告警中文风险）。"""
    cands = []
    env_font = (os.environ.get(FONT_ENV) or '').strip()
    if env_font:
        cands.append(env_font)
    cands.extend(FONT_CANDIDATES['bold' if bold else 'normal'])
    for c in cands:
        if not c or not os.path.isfile(c):
            continue
        try:
            return ImageFont.truetype(c, size), c
        except (OSError, ValueError) as e:
            warn('字体 %s 打不开（%s），试下一个' % (c, e))
    warn('没找到可用中文字体（可设 %s=<ttf/ttc 路径>）；回退内置位图字体，中文可能显示为方块' % FONT_ENV)
    return ImageFont.load_default(), ''


def draw_logo(w, h, text, sub, tag, bg, accent, fg, subc):
    """版式：顶部品牌细线 + 三行居中文字 + 底部细线（与草案版式一致）。"""
    im = Image.new('RGB', (w, h), bg)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w, max(2, int(h * 0.01))], fill=accent)

    f_main, used = pick_font(int(h * 0.22), bold=True)
    f_sub, _ = pick_font(int(h * 0.075))
    f_tag, _ = pick_font(int(h * 0.05))
    if used:
        print('[info] 字体: %s' % used)

    rows = [(text, f_main, fg), (sub, f_sub, subc), (tag, f_tag, accent)]
    boxes = []
    for t, f, c in rows:
        if not t:
            continue
        b = d.textbbox((0, 0), t, font=f)
        boxes.append((t, f, c, b))
    gap = int(h * 0.05)
    total = sum(b[3] - b[1] for _t, _f, _c, b in boxes) + gap * max(0, len(boxes) - 1)
    y = (h - total) // 2
    for t, f, c, b in boxes:
        d.text(((w - (b[2] - b[0])) // 2 - b[0], y - b[1]), t, font=f, fill=c)
        y += (b[3] - b[1]) + gap

    yl = h - max(4, int(h * 0.08))
    d.rectangle([int(w * 0.3), yl, int(w * 0.7), yl + 2], fill=accent)
    return im


def save_under_limit(im, out, limit_kb, quality, min_quality):
    """压到体积 ≤ limit_kb；返回 (成功?, 实际 KB, 用了的质量)。"""
    q = quality
    while True:
        im.save(out, 'JPEG', quality=q, optimize=True)
        kb = os.path.getsize(out) / 1024.0
        if kb <= limit_kb:
            return True, kb, q
        if q <= min_quality:
            return False, kb, q
        nq = max(min_quality, q - 4)
        print('[info] %d B 超上限 %.0f KB，重压 quality=%d' % (kb * 1024, limit_kb, nq))
        q = nq


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='生成开机 logo boot_logo.JPG（落点 MISC 分区，体积必须 ≤ 分区大小）')
    ap.add_argument('--size', default=DEFAULT_SIZE, help='分辨率 WxH（默认 %s，Z21）' % DEFAULT_SIZE)
    ap.add_argument('--out', default='boot_logo.JPG', help='输出 JPG 路径（默认 ./boot_logo.JPG）')
    ap.add_argument('--text', default='ZKSWE', help='主字样（默认 ZKSWE）')
    ap.add_argument('--sub', default='深圳中科世为科技', help='副标题（默认 深圳中科世为科技）')
    ap.add_argument('--tag', default='FlyThings OS', help='标签行（默认 FlyThings OS）')
    ap.add_argument('--bg', default=BG, help='底色（默认 %s）' % BG)
    ap.add_argument('--fg', default=FG, help='主字样色（默认 %s）' % FG)
    ap.add_argument('--sub-color', dest='subc', default=SUB, help='副标题色（默认 %s）' % SUB)
    ap.add_argument('--accent', default=ACCENT, help='品牌色（默认 %s）' % ACCENT)
    ap.add_argument('--quality', type=int, default=92, help='JPEG 起始质量（默认 92）')
    ap.add_argument('--min-quality', type=int, default=70, help='自动重压的下限质量（默认 70）')
    ap.add_argument('--limit-kb', type=int,
                    default=int(os.environ.get(LIMIT_ENV) or DEFAULT_LIMIT_KB),
                    help='体积上限 KB（默认 %d = 本板 MISC 大小；换板子先 cat /proc/mtd）'
                         % DEFAULT_LIMIT_KB)
    a = ap.parse_args(argv)

    try:
        w, h = [int(x) for x in a.size.lower().replace('*', 'x').split('x')]
    except ValueError:
        print('[FAIL] --size 要写成 WxH（如 1024x600），收到 %r' % a.size)
        return 2
    if w < 64 or h < 64:
        print('[FAIL] 分辨率太小：%dx%d' % (w, h))
        return 2

    im = draw_logo(w, h, a.text, a.sub, a.tag,
                   hex_color(a.bg, BG), hex_color(a.accent, ACCENT),
                   hex_color(a.fg, FG), hex_color(a.subc, SUB))
    odir = os.path.dirname(os.path.abspath(a.out))
    if odir and not os.path.isdir(odir):
        os.makedirs(odir, exist_ok=True)
    ok, kb, q = save_under_limit(im, a.out, a.limit_kb, a.quality, a.min_quality)
    print('-' * 64)
    print('out     : %s' % os.path.abspath(a.out))
    print('size    : %dx%d  quality=%d' % (w, h, q))
    print('bytes   : %d  (%.1f KB)' % (os.path.getsize(a.out), kb))
    print('limit   : %d KB  (%.1f%% used)' % (a.limit_kb, kb * 100.0 / a.limit_kb))
    if not ok:
        print('[FAIL] 仍超上限 %d KB —— 请改小 --size / 换更简版式（或确认该板 MISC 更大）'
              % a.limit_kb)
        return 2
    print('[OK] 体积校验通过（≤ MISC 上限 %d KB）；拷到 TF 卡根目录或 '
          'python tools/set_boot_logo.py --image %s --device <serial|IP:5555>' % (a.limit_kb, a.out))
    if WARNINGS:
        print('[note] %d 条告警' % len(WARNINGS))
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
