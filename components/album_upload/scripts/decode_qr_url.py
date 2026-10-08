# -*- coding: utf-8 -*-
"""码图 → 二维码链接（离线一次性工具；**运行时不依赖图片**）

用途（对应 assets/README.md 的「一条路 + 一个兜底」口径）：
  · 面板上**不铺二维码位图**：只把"链接字符串"交给 `ZKQRCode` 控件现场生成
    （位图 128px / 37 模块 = 3.46 px/模块，模块宽非整数像素 → 边缘发糊、扫不动）；
  · 于是本脚本只干一件事：**把一张码图里的链接解出来**，供部署方填进自己的配置
    （如 prefs 键 `sp_qr_url`），或者写进 `assets/qr_url.txt`。

什么时候跑：换小程序 / 换码 / 核对 existing 链接时**跑一次**；
  组件本体、设备上屏、`fsc build` 都**不需要**本脚本，也不读任何图片素材。

用法：
  py scripts/decode_qr_url.py --src mp_qr.png                      # 只打印链接
  py scripts/decode_qr_url.py --src mp_qr.png --write assets/qr_url.txt
  py scripts/decode_qr_url.py --src mp_qr.png --expect "https://mp.weixin.qq.com/a/~...~~"  # 核对

⚠️ 源图要**清晰的原图**（小程序后台下载的那张/商家素材），别拿已缩到 128 的糊图当源。

依赖：Pillow + zxing-cpp（`py -m pip install pillow zxing-cpp`）—— 仅为出链接用，组件运行不需要。
"""
import argparse
import os
import sys

try:
    import zxingcpp
    from PIL import Image
except ImportError as e:  # 明确报缺什么，不给"import error 堆栈"让人猜
    print("缺少依赖：%s" % e)
    print("装：py -m pip install pillow zxing-cpp")
    sys.exit(2)

FILE_NOTE = "# 我方小程序码解出来的链接（= 「扫普通链接二维码打开小程序」链接）。\n" \
            "# 用法：填进你自己的配置（如 prefs 键 sp_qr_url），面板交给 ZKQRCode 控件现场生成；\n" \
            "#      **换成你自己的小程序链接**（见 README.md §3），组件本身不带任何默认链接。\n"


def decode(path):
    res = zxingcpp.read_barcodes(Image.open(path).convert("RGB"))
    return res[0] if res else None


def main():
    ap = argparse.ArgumentParser(description="码图 → 二维码链接（离线；组件运行不依赖图片）")
    ap.add_argument("--src", required=True, help="码图（png/jpg；要清晰原图）")
    ap.add_argument("--write", default="", help="把链接写成 qr_url.txt 形态（首行注释 + 一行链接）")
    ap.add_argument("--expect", default="", help="核对：与给定链接不一致则退出码 1")
    args = ap.parse_args()

    if not os.path.isfile(args.src):
        print("FAIL: 找不到源图 %s" % args.src)
        return 1

    res = decode(args.src)
    if res is None:
        print("FAIL: 这张图解不出二维码，换一张更清晰的（原图/小程序后台下载的那张）")
        return 1

    text = res.text
    pts = res.position
    w = abs(pts.top_right.x - pts.top_left.x)
    h = abs(pts.bottom_left.y - pts.top_left.y)
    print("输入：%s" % args.src)
    print("  payload = %r" % text)
    print("  ec=%s，码区 ≈ %dx%d px（供参考）" % (res.ec_level, w, h))

    rc = 0
    if args.expect and text != args.expect:
        print("FAIL: 与 --expect 不一致\n  期望 = %r" % args.expect)
        rc = 1
    elif args.expect:
        print("  OK: 与 --expect 一致")

    if args.write:
        out_dir = os.path.dirname(os.path.abspath(args.write))
        if out_dir and not os.path.isdir(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        with open(args.write, "w", encoding="utf-8", newline="\n") as f:
            f.write(FILE_NOTE)
            f.write(text + "\n")
        print("写出 %s（一行 = 链接；注释行不参与解析，取链接用最后一行）" % args.write)

    print("")
    print("下一步：把上面的 payload 填到你的配置项（如 prefs 的 sp_qr_url），"
          "面板侧 ZKQRCode 控件会现场生成；组件里不许写死 AppID / 链接。")
    return rc


if __name__ == "__main__":
    sys.exit(main())
