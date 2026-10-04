#!/usr/bin/env python3
"""±2 逐像素比对：app 交给 easyui 的离屏 buffer  vs  抓屏得到的控件区域。
两路独立采集（一路是 app 落盘的内存位图，一路是 fb0 上屏后的像素），
一致性可同时验证通道顺序 / stride / 裁剪 / 上屏路径。
纯标准库。"""
import os, struct, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, STRIDE = 480, 800, 1920
CL, CT, CW, CH = 20, 20, 440, 440
TOL = 2

fb = open(os.path.join(HERE, "fb.raw"), "rb").read()
buf = open(os.path.join(HERE, "nvg_ondev.bgra"), "rb").read()
assert len(buf) == CW * CH * 4, len(buf)

# 活动半屏判定（本 demo 特征色：棋盘橙/蓝、青条）
def score(off):
    n = 0
    for y in range(0, H, 3):
        s = off + y*STRIDE
        for x in range(0, W, 3):
            b, g, r = fb[s+x*4], fb[s+x*4+1], fb[s+x*4+2]
            if (abs(r-255) < 12 and abs(g-200) < 12 and b < 20) or \
               (abs(r-20) < 12 and abs(g-40) < 12 and abs(b-200) < 12) or \
               (abs(r-0) < 12 and abs(g-220) < 12 and abs(b-180) < 12):
                n += 1
    return n
OFF = max((0, W*H*4), key=score)
print(f"活动半屏 OFF={OFF} (score={score(OFF)})")

maxd = 0
over = 0
total = 0
hist = {}
worst = None
for ly in range(CH):
    srow = OFF + (CT+ly)*STRIDE + CL*4
    for lx in range(CW):
        o = srow + lx*4
        sr, sg, sb = fb[o+2], fb[o+1], fb[o+0]          # 屏 BGRA -> RGB
        b = (ly*CW + lx)*4
        br, bg_, bb = buf[b+2], buf[b+1], buf[b+0]      # 缓冲 BGRA -> RGB
        d = abs(sr-br) + abs(sg-bg_) + abs(sb-bb)
        total += 1
        if d > maxd:
            maxd = d; worst = (lx, ly, (sr,sg,sb), (br,bg_,bb))
        if d > TOL: over += 1
        hist[d] = hist.get(d, 0) + 1

print(f"像素总数 {total}")
print(f"max |Δ|(R+G+B) = {maxd}   超差(> {TOL}) 像素 = {over}  ({100.0*over/total:.4f}%)")
print("Δ 分布(前 8 档):", sorted(hist.items())[:8])
if worst:
    print(f"最差点 local({worst[0]},{worst[1]}): 屏{worst[2]} vs 缓冲{worst[3]}")
print("结论:", "PASS —— 上屏与离屏出图逐像素一致（通道/stride/裁剪/上屏均无偏差）"
      if over == 0 else f"有 {over} 个像素超差，需核查")

# 顺带导出 PNG（缓存的离屏图，作为交付物）
def png(path, w, h, get):
    lines = []
    for y in range(h):
        line = bytearray([0]); line += bytes(get(y)); lines.append(bytes(line))
    idat = zlib.compress(b"".join(lines), 9)
    def ck(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
    p = b"\x89PNG\r\n\x1a\n" + ck(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + ck(b"IDAT", idat) + ck(b"IEND", b"")
    open(path, "wb").write(p); print("wrote", path, len(p), "B")

def off_get(y):
    out = bytearray()
    r0 = ((y)*CW)*4
    for x in range(CW):
        b = r0 + x*4
        out += bytes((buf[b+2], buf[b+1], buf[b+0]))
    return out
png(os.path.join(HERE, "offscreen_nanovg.png"), CW, CH, off_get)

def scr_get(y):
    out = bytearray()
    for x in range(CW):
        o = OFF + (CT+y)*STRIDE + (CL+x)*4
        out += bytes((fb[o+2], fb[o+1], fb[o+0]))
    return out
png(os.path.join(HERE, "onscreen_nanovg.png"), CW, CH, scr_get)
