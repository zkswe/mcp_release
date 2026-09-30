# -*- coding: utf-8 -*-
"""小程序码图 → 面板控件盒尺寸的二维码素材（默认 128×128，纯黑白，机器验扫）

用途（对应 assets/README.md 的三态口径）：
  · 只有「② 控件现场生成」这一态需要素材/链接 —— 用本脚本从微信给的小程序码图里**解出链接**；
  · 「① 远端小程序码图」直接把图放服务器上、面板下载显示，不走本脚本。

背景（为什么不用位图直接上屏）：
  微信小程序码图是 37 模块、中心带 logo、底部带「微信扫一扫，使用小程序」文案；
  压到控件盒（128px）时 128/37 = 3.46 px/模块，**模块宽不是整数像素** → 边缘发糊、扫码容错吃紧。
  所以设备上改用二维码控件**按解出来的链接现场生成**（模块像素对齐，锐利）。

判据（脚本会自动验，全绿才退出码 0）：
  1) 裁切框 = zxingcpp 报的 QR 四边形（去掉底部文案与白边）
  2) 模块数由首行黑 run 推出（首行 = 左上定位符 7 模块）→ 必须为合法值且模块像素接近整数
  3) 落盘素材纯黑白（只有 0 / 255）
  4) 素材本身可解，内容与输入一致
  5) 模拟上屏（白卡 + 码 + 静区）仍可解

用法：
  # 默认：源图 → 128×128 素材（== 控件盒）
  py make_qr_asset.py --src mp_qr.png --out album_qr_mp128.png --keep ./qr_asset
  # 只要链接（配置项 kQrUrlDefault 用）
  py make_qr_asset.py --src mp_qr.png --decode-only

⚠️ 输入必须是**微信给的原图**（高分辨率）：
  拿已经缩到 128 的素材当源会 FAIL 第 2 条判据（模块 ≈ 3.43 px，是槽位决定的），属预期；
  assets/album_qr_mp128.png 是本脚本在**原图**上跑出来的产物，重跑（同一原图）应逐字节一致
  （md5 5AF8B65E6CBE92A6FAD6D3158B4D144E / 1287 B）—— 本仓不复分发原图（现场找微信侧要）。

依赖：Pillow + numpy + zxing-cpp（`py -m pip install pillow numpy zxing-cpp`）；仅为出素材用，组件运行不需要。
"""
import argparse
import os
import sys

from PIL import Image
import numpy as np
import zxingcpp


def decode(path):
    res = zxingcpp.read_barcodes(Image.open(path).convert("RGB"))
    return res[0] if res else None


def main():
    ap = argparse.ArgumentParser(description="小程序码图 → 控件盒尺寸二维码素材（含验扫）")
    ap.add_argument("--src", required=True, help="微信小程序码原图（png/jpg）")
    ap.add_argument("--out", default="album_qr_mp128.png", help="输出素材（尺寸 == 控件盒，默认 128×128）")
    ap.add_argument("--box", type=int, default=128, help="控件盒边长像素（默认 128）")
    ap.add_argument("--keep", default="", help="留档目录（1:1 裁切图 + 上屏模拟图）")
    ap.add_argument("--decode-only", action="store_true", help="只解链接（不写素材）")
    args = ap.parse_args()

    fails = []

    def chk(name, cond, detail=""):
        print("  [%s] %-44s %s" % ("OK" if cond else "FAIL", name, detail))
        if not cond:
            fails.append(name)

    res = decode(args.src)
    if res is None:
        print("FAIL: 源图解不出二维码，换一张（原图/更清晰的那张）")
        return 1
    pts = res.position
    xs = [p.x for p in (pts.top_left, pts.top_right, pts.bottom_right, pts.bottom_left)]
    ys = [p.y for p in (pts.top_left, pts.top_right, pts.bottom_right, pts.bottom_left)]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    print("输入：%s" % args.src)
    print("  payload = %r" % res.text)
    print("  ec=%s，二维码 %dx%d @(%d,%d)" % (res.ec_level, x1 - x0, y1 - y0, x0, y0))
    if args.decode_only:
        print("")
        print("把上面这行 payload 填到你的配置项（如 prefs 的 sp_qr_url / kQrUrlDefault）。")
        print("注意：组件里不许写死 AppID / 链接：一律从配置读。")
        return 0

    im = Image.open(args.src).convert("RGB")
    crop = im.crop((x0, y0, x1, y1))

    # ── 模块数：首行第一个黑 run = 左上定位符 7 模块 ──
    g = np.array(crop.convert("L"))
    row = g[1] < 128
    first_black = int(np.argmax(row))
    run = 0
    while first_black + run < len(row) and row[first_black + run]:
        run += 1
    mod = run / 7.0
    n = int(round(crop.width / mod))
    print("  首行黑 run = %d px → 模块 ≈ %.2f px → 符号边长 %d 模块" % (run, mod, n))
    chk("模块像素接近整数（原图是渲染出来的，不是缩放糊图）", abs(mod - round(mod)) < 0.06, "%.3f px" % mod)
    chk("模块数合法（21+4k, 21..57）", (n - 21) % 4 == 0 and 21 <= n <= 57, "n=%d" % n)

    box = args.box
    small = crop.convert("L").resize((box, box), Image.BOX)
    arr = np.array(small)
    # box/模块数 一般不是整数 → 过渡带必然有灰像素（槽位尺寸决定，非素材瑕疵）；
    # 关键是**落盘素材必须纯黑白**（设备上不再被插值糊），灰阶占比只报出。
    bw = np.where(arr >= 128, 255, 0).astype(np.uint8)
    out = Image.fromarray(bw, "L").convert("RGB")
    out.save(args.out, optimize=True)
    print("写出 %s（%d B，%dx%d）" % (args.out, os.path.getsize(args.out), box, box))
    chk("尺寸 == 控件盒 %dx%d" % (box, box), out.size == (box, box), str(out.size))

    saved = np.array(Image.open(args.out).convert("L"))
    chk("落盘素材纯黑白（只有 0 / 255）", set(np.unique(saved).tolist()) <= {0, 255},
        "灰阶过渡像素占比 %.1f%%（已二值化抹平）" % (100 * float(((arr > 40) & (arr < 215)).mean())))

    d = zxingcpp.read_barcodes(out)
    chk("素材可解且内容一致", bool(d) and d[0].text == res.text, (d[0].text[:48] if d else "no decode"))

    # ── 模拟上屏：白卡（比控件盒大一圈）+ 码居中；白边即静区 ──
    card_box = box + 32
    card = Image.new("RGB", (card_box, card_box), (255, 255, 255))
    card.paste(out, (16, 16))
    if args.keep:
        os.makedirs(args.keep, exist_ok=True)
        card.save(os.path.join(args.keep, "on_screen_%d.png" % card_box))
    d2 = zxingcpp.read_barcodes(card)
    chk("模拟上屏（%d 白卡 + 码）可解" % card_box, bool(d2) and d2[0].text == res.text,
        (d2[0].text[:48] if d2 else "no decode"))

    if args.keep:
        q = int(round(mod)) * 4
        pad = Image.new("RGB", (crop.width + 2 * q, crop.height + 2 * q), (255, 255, 255))
        pad.paste(crop, (q, q))
        pad.save(os.path.join(args.keep, "qr_symbol_1to1.png"))
        print("留档 %s（%dx%d，静区 %dpx = 4 模块；以后要更大尺寸时用它重缩）"
              % (os.path.join(args.keep, "qr_symbol_1to1.png"), pad.width, pad.height, q))

    print("\n判定：%s" % ("全部通过" if not fails else "FAIL %s" % fails))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
