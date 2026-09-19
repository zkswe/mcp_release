#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CSS 效果 → PNG/.9.png 资源生成器（通用版，Pillow）

用途：HTML 原型里的 CSS 效果（渐变/圆角/阴影/图标/loading 动效）FlyThings 不支持，
按「转图片 + 控件」原则生成设备端图片资源，输出到 <项目>/resources/images/。

用法：
    python gen_res.py <项目根目录>          # 按本文件下方 GEN 配置生成
    # 或 import 本文件复用通用函数（to_9patch/rounded_rect/gen_btn9/gen_gradient/dot/icon/frames）

支持生成：
- .9.png 九宫格（圆角可拉伸背景：卡片/按钮/轨道/输入框）——top/left 1px 黑线标拉伸区
- 普通 PNG（渐变背景/固定图标/状态点/emoji 替代图标）
- 序列帧（loading/旋转动效，配合 imageanim 动图控件）
- 按钮两态（_p pressed 边框高亮，还原 :active）

图标生成三级降级（MCP flythings_generate_ui_assets）：
  AI 生图（需 OPENAI_API_KEY，gpt-image-2 透明底） → emoji 渲染（本地彩色 emoji 字体） → 线条/几何兜底

依赖：pip install Pillow
"""
import io
import json
import os
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ---------- 通用函数 ----------

def save(img, out_dir, name):
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, name)
    img.save(p)
    print("  %s  %dx%d" % (name, img.width, img.height))
    return p


# ---------- 抗锯齿（FT-008）----------
# 2026-09-01 沛哥反馈：超采样（SS 倍画布绘制 → LANCZOS 缩回）会引入像素网格取整偏移，
# 导致圆角倒角视觉变宽 1px（且 radius 接近钳制上限时动态校准也救不回）。
# 改为「1x 直画 + α 高斯羽化」：几何轮廓（α>=128）与 1x 直画逐像素一致（倒角宽度不变），
# 弧线处 α 平滑过渡（抗锯齿），直线段保持硬边（直线不需要 AA）。
# 实验验证：r=2..20 × 多组尺寸，几何全部一致；sigma=0.5 过渡 3-4px 平滑不糊。
_AA_SIGMA = 0.5  # α 羽化强度：过渡带宽度（0.5≈3-4px，视觉平滑不糊）


def _aa_rounded_rect(w, h, radius, fill, border=None, border_w=1, ss=None):
    """圆角矩形（FT-008 抗锯齿）：1x 直画保证几何与修复前完全一致（倒角宽度不变），
    α 通道高斯羽化平滑弧线边缘。供 to_9patch / 直接保存。"""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=fill,
                                          outline=border, width=border_w)
    return _feather_alpha(img)


def _feather_alpha(img, sigma=_AA_SIGMA):
    """α 通道高斯羽化：只模糊 alpha（几何轮廓 128 阈值不变），RGB 不动。"""
    alpha = img.getchannel('A').filter(ImageFilter.GaussianBlur(sigma))
    img.putalpha(alpha)
    return img


def _aa_mask(w, h, radius, ss=None):
    """圆角 mask（FT-008 抗锯齿）：1x 直画 + α 羽化，几何与 1x 一致，边缘平滑。

    ⚠️ 强曲率（radius ≈ min(w,h)/2：圆 / 药丸 / 细圆条）下本 mask 的边界误差
    mean 21~44/255 → 要出这类形状请用 `rounded_rect_ss`（FT-010）。"""
    m = Image.new('L', (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    return m.filter(ImageFilter.GaussianBlur(_AA_SIGMA))


def _aa_outline(w, h, radius, color, width=1, ss=None):
    """圆角描边层（透明底 + 仅描边，FT-008 抗锯齿），供叠加到渐变/填充底上。"""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, w - 1, h - 1],
                                          radius=radius, outline=color, width=width)
    return _feather_alpha(img)


def to_9patch(img, radius, out_dir, name):
    """普通图 → .9.png：四周扩 1px 透明边，四边黑线标记（FT-009 规则）。
    ⚠️ 只处理「标记」，不负责抗锯齿：底色图请先按形状选函数（大圆角 `rounded_rect` /
    强曲率 `rounded_rect_ss`，见 FT-010），本函数再打 marker。
    规则（沛哥 2026-09-01）：
      1) marker 纯黑不透明 (0,0,0,255)
      2) top/left 只画中间拉伸段（排除 radius 倒角区）
      3) right/bottom 黑线宽度与拉伸区同宽
      4) 线宽 1px 紧贴边缘
      5) marker 在所有绘图完成后最后绘制，不被后续 alpha 覆盖
    """
    w, h = img.size
    out = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0))
    out.paste(img, (1, 1))
    d = ImageDraw.Draw(out)
    x0, x1 = 1 + radius, w - radius
    y0, y1 = 1 + radius, h - radius
    black = (0, 0, 0, 255)
    if x1 > x0:
        d.line([(x0, 0), (x1, 0)], fill=black, width=1)
    else:
        d.point((1 + w // 2, 0), fill=black)
    if y1 > y0:
        d.line([(0, y0), (0, y1)], fill=black, width=1)
    else:
        d.point((0, 1 + h // 2), fill=black)
    # 规则3：right/bottom 黑线与拉伸区同宽（内容区标记）
    if y1 > y0:
        d.line([(w + 1, y0), (w + 1, y1)], fill=black, width=1)
    else:
        d.point((w + 1, 1 + h // 2), fill=black)
    if x1 > x0:
        d.line([(x0, h + 1), (x1, h + 1)], fill=black, width=1)
    else:
        d.point((1 + w // 2, h + 1), fill=black)
    return save(out, out_dir, name)


def rounded_rect(w, h, radius, fill, border=None, border_w=1):
    """圆角矩形（透明底，FT-008 超采样抗锯齿）→ 供 to_9patch / 直接保存

    ⚠️ 强曲率形状（圆钮/药丸/细圆条）请改用 `rounded_rect_ss`（见 FT-010 说明）。"""
    return _aa_rounded_rect(w, h, radius, fill, border, border_w)


# ---------- 抗锯齿（FT-010，2026-09-16）----------
# 背景：FT-008 的「1x 直画 + α 羽化 σ0.5」在**大半径卡片**够用，但在**强曲率**形状
# （圆 / 圆钮 / 药丸 / 细圆条）上远不够。用 16x 超采样覆盖率当理想值逐像素对比
# （本机 Pillow 12.2.0 / numpy 2.5.1；边界带 = 理想 α 介于 4~251 的像素；单位 /255；
#  复现口径见 knowledge/devflow/ui-asset-rules.md §2 铁律 #8）：
#     形状                  FT-008 mean/p95     rounded_rect_ss(ss=4)   ss=8
#     药丸 80x40 r20           35.4 /  97.9          5.3 / 22.7        1.4 / 3.8
#     圆   30x30 r15           40.9 / 102.0          3.7 / 11.0        1.2 / 4.0
#     圆钮 31x31 r15           42.0 / 105.0          6.3 / 17.0          —  /  —
#     细圆条 200x8 r4          21.0 /  43.0          3.2 /  6.0        1.8 / 3.0
#     大卡片 300x180 r16       43.9 / 153.0         10.0 / 22.0          —  /  —
#   → 强曲率必须 ≥4x 超采样 + LANCZOS 缩回（小尺寸强曲率可用 ss=8，p95 <4）；
#     大半径卡片两条路都能用，但 FT-008 的几何与 1x 直画逐像素一致（FT-008 的修复目的：
#     倒角宽度不漂），**故大卡片仍默认走 FT-008**，只把新函数给强曲率用，老调用者不受影响。
# 实测案例：LVGL 迁移案例（projects/translate/lvgl-widgets-uiv1，Z21/F133/F136）
# SeekBar 圆钮 sk_thumb + 开关药丸 sw_on/sw_off。
#
# 2026-09-16 钟工拍板（v0.27.76，上条的「大卡片仍默认走 FT-008」只对**手写调用**有效）：
#   html2json（CSS 效果自动出图）一律走 SS（SS_DEFAULT = 4，每像素 16 子采样）；
#   gen_gradient / gen_gradient_stops / gen_shadow_card / rounded_card / gen_btn9
#   都加了可选的 `ss=0`（**默认 0 = 老口径，默认行为逐字节不变**）；
#   `rounded_rect` 默认（FT-008）保持不变，仅手写调用按形状选：强曲率 rounded_rect_ss /
#   大半径卡片 rounded_rect。
# 缩回前必须 **alpha 预乘**，否则透明像素的 RGB（黑）渗进边界 → 暗边（halo）。
def _ss_down(big, w, h):
    """超采样画布（RGBA）→ LANCZOS 缩回；带 alpha 预乘 / 反预乘（防暗边）。

    numpy 为 lock 里钉死的依赖（requirements.lock: numpy==2.5.1），下面的显式预乘是
    **不依赖 Pillow 内部实现**的写法（老 Pillow 的 RGBA resize 不预乘 → 暗边）。
    无 numpy 时退化为直缩：Pillow 12.2.0 实测其 RGBA resize 内部已按 alpha 预乘
    （与手工预乘结果逐像素 0 差，半透明底边界 G/B 通道均为 0 → 无暗边），故可安全退化。
    """
    try:
        import numpy as np
    except ImportError:                 # 无 numpy：直缩（见 docstring，实测无暗边）
        return big.resize((w, h), Image.LANCZOS)
    a = np.asarray(big).astype(np.float64)
    al = a[..., 3:4] / 255.0
    pm = np.clip(a[..., :3] * al + 0.5, 0, 255).astype(np.uint8)
    pm_s = np.asarray(Image.fromarray(pm, 'RGB').resize((w, h), Image.LANCZOS)).astype(np.float64)
    al_s = np.asarray(big.getchannel('A').resize((w, h), Image.LANCZOS)).astype(np.float64)
    rgb = np.clip(pm_s * 255.0 / np.maximum(al_s[..., None], 1.0), 0, 255)
    return Image.fromarray(np.concatenate([rgb, al_s[..., None]], axis=2).astype(np.uint8), 'RGBA')


# 超采样画布像素上限：防「大图 + 高档位」把内存吃爆（默认 1024x600 ss=4 = 9.8M px，安全）。
_SS_MAX_PX = 40 * 1000 * 1000

# html2json（CSS 效果自动出图）统一档位 —— 钟工 2026-09-16 拍板：CSS 效果一律走 SS，
# 不再保留「1x + α 羽化」那条路（固定本地脚本工作，不额外耗 token）。
# ⚠️ `rounded_rect` 的默认行为（FT-008：1x 直画 + α 羽化 σ0.5）**保持不变**，
# 只有 ①html2json 自动出图 ②调用方显式 `rounded_rect_ss`/`ss>0` 时才走超采样。
SS_DEFAULT = 4


def _ss_fit(w, h, ss, label='SS'):
    """把 ss 降到「画布不超 _SS_MAX_PX」的最大档（≥2）；降档时打一行 NOTE（不静默）。"""
    ss = max(2, int(ss))
    while ss > 2 and w * ss * h * ss > _SS_MAX_PX:
        ss -= 1
        print('  [NOTE] %s: %dx%d 画布过大，ss 自动降到 %d（防内存爆）' % (label, w, h, ss))
    return ss


def _ss_rounded_rect(w, h, radius, fill, border=None, border_w=1, ss=4):
    """圆角矩形（SS 画布绘制 → 预乘 LANCZOS 缩回）。

    共用方：rounded_rect_ss / gen_btn9(ss>0) / gen_shadow_card(ss>0) 主体 / rounded_card 高光层。
    """
    ss = _ss_fit(w, h, ss, 'SS')
    wd = max(1, int(border_w * ss)) if border else 1
    big = Image.new('RGBA', (w * ss, h * ss), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius=radius * ss,
                                          fill=fill, outline=border, width=wd)
    return _ss_down(big, w, h)


def _ss_mask(w, h, radius, ss=4):
    """圆角 mask（L 模式，0~255 = 理想覆盖率）：SS 画布二值 → LANCZOS 缩回。

    给「渐变/阴影裁剪层」用（`_aa_mask` 的 SS 版）。L 单通道无需预乘。
    用于 putalpha 时**替换** alpha（底图本来全不透明，安全）；用于已有 alpha 的图层时
    必须 ImageChops.multiply（见 ss_shape_mask docstring）。
    """
    ss = _ss_fit(w, h, ss, 'SS mask')
    big = Image.new('L', (w * ss, h * ss), 0)
    ImageDraw.Draw(big).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1],
                                          radius=radius * ss, fill=255)
    return big.resize((w, h), Image.LANCZOS)


def _ss_outline(w, h, radius, color, width=1, ss=4):
    """圆角描边层（透明底 + 仅描边）——`_aa_outline` 的 SS 版，供 rounded_card(ss>0)。"""
    ss = _ss_fit(w, h, ss, 'SS outline')
    wd = max(1, int(width * ss))
    big = Image.new('RGBA', (w * ss, h * ss), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius=radius * ss,
                                          outline=color, width=wd)
    return _ss_down(big, w, h)


def ss_shape_mask(w, h, radius, ss=4):
    """**公开**：SS 版圆角 mask（L 模式，形状外=0 / 内=255 / 边界=理想覆盖率）。

    给「自己画合成层的调用方」用（如 html2json 的渐变+阴影叠加层）。用法铁律：
      给目标层套形状时用 `ImageChops.multiply(layer.getchannel('A'), mask)` **缩放 alpha**，
      别用 `paste(color_layer, mask)`（那会把 RGB 一起按 mask 缩小 → 边界发黑 = 暗边 halo）。
    """
    return _ss_mask(w, h, radius, ss)


def rounded_rect_ss(w, h, radius, fill, border=None, border_w=1, ss=4):
    """圆角矩形 / 圆 / 药丸（≥ss 倍超采样 + LANCZOS 缩回）——**强曲率形状用这个**。

    与 rounded_rect 的分工（2026-09-16 实测口径，数字见模块头 FT-010 注释）：
      - `rounded_rect`（1x 直画 + α 羽化 σ0.5）：几何与 1x 直画逐像素一致（倒角宽度不漂），
        适合**大半径卡片**圆角 → 强曲率下边界误差 mean 21~44/255、p95 43~153/255；
      - **本函数**（SS + LANCZOS）：圆 / 圆钮 / 药丸 / 细圆条等强曲率形状 →
        边界误差 mean 3~6/255、p95 11~23/255 （ss=8 时 p95 <4）→ 设备上才不发锯齿。
    参数：radius 同 PIL（> min(w,h)/2 自动按药丸/正圆钳制）；border/border_w 同 rounded_rect；
         ss≥2（画布过大会自动降档并打一行提示，不静默）。
    设备端验证：LVGL 迁移案例 Z21/F133/F136 的 SeekBar 圆钮 + 开关药丸（2026-09-16）。
    """
    ss = max(2, int(ss))
    while ss > 2 and w * ss * h * ss > _SS_MAX_PX:
        ss -= 1
        print('  [NOTE] rounded_rect_ss: %dx%d 画布过大，ss 自动降到 %d（防内存爆）' % (w, h, ss))
    wd = max(1, int(border_w * ss)) if border else 1
    big = Image.new('RGBA', (w * ss, h * ss), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius=radius * ss,
                                          fill=fill, outline=border, width=wd)
    return _ss_down(big, w, h)


def gen_btn9(out_dir, name, w, h, radius, fill, border=None, pressed=None, ss=0):
    """按钮两态 .9.png：normal + _p（pressed 边框高亮，还原 CSS :active）

    ss>0：两态底图走 SS（`_ss_rounded_rect`，药丸/强曲率按钮不发锯）；
    ss=0（默认）：仍走 `rounded_rect`（FT-008：1x 直画 + α 羽化）—— 默认行为不变。
    """
    if border is None:
        border = fill
    if pressed is None:
        pressed = tuple(min(255, c + 60) for c in fill[:3]) + (fill[3],)

    def _base(f):
        if ss > 0:
            return _ss_rounded_rect(w, h, radius, f, border, 1, ss)
        return rounded_rect(w, h, radius, f, border)

    to_9patch(_base(fill), radius, out_dir, name + ".9.png")
    to_9patch(_base(pressed), radius, out_dir, name + "_p.9.png")


def gen_gradient(out_dir, name, w, h, color_from, color_to, horizontal=True, to9=False, radius=0, ss=0):
    """CSS linear-gradient → PNG（可选转 .9.png 圆角九宫格）
    ⚠️ 圆角裁剪：ss>0 走 SS mask（理想覆盖率，html2json 一律走这条）；ss=0（默认）走
    FT-008 mask（1x + α 羽化）：大半径卡片没问题，**radius 接近 min(w,h)/2（药丸/正圆）
    时会有肉眼可见锯齿**——这类形状改用 `rounded_rect_ss` 出底图（FT-010）。
    ⚠️ radius>0 且非 to9 时也会用圆角 mask 裁剪四角透明（否则弧线外是实心色块，
    叠放/透背景时会露出方角——2026-08-29 羊了个羊瓦片坑）"""
    img = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(img)
    for i in range(max(w, h)):
        t = i / max(1, max(w, h) - 1)
        c = tuple(int(color_from[k] + (color_to[k] - color_from[k]) * t) for k in range(3)) + (255,)
        if horizontal:
            d.line([(i, 0), (i, h)], fill=c)
        else:
            d.line([(0, i), (w, i)], fill=c)
    if radius > 0:
        # 圆角 mask 裁剪：清掉弧线外角落，边缘 α 平滑
        # ss>0 → SS mask（理想覆盖率）；ss=0 → FT-008（1x 直画 + α 羽化，几何不漂）
        img.putalpha(_ss_mask(w, h, radius, ss) if ss > 0 else _aa_mask(w, h, radius))
    if to9:
        return to_9patch(img, radius, out_dir, name)
    return save(img, out_dir, name)


def rounded_card(out_dir, name, w, h, radius, color_from, color_to, border=None,
                 border_w=2, highlight=None, size=None, ss=0):
    """圆角卡片图（渐变底 + 可选描边/高光），四角真透明。
    ss>0 走 SS（底 mask / 描边层 / 高光层全走）；ss=0（默认）= FT-008 老口径。
    ⚠️ 尺寸参数 size 与 json 控件尺寸保持一致（默认 w×h）。
    教训（2026-08-29）：渐变/填充不能直接画满矩形，必须圆角 mask 裁剪；
    阴影模糊会溢出到弧线外，最后整体再裁一次圆角清掉残影。"""
    if size:
        w = h = size
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i in range(h):
        t = i / max(1, h - 1)
        c = tuple(int(color_from[k] + (color_to[k] - color_from[k]) * t) for k in range(3)) + (255,)
        d.line([(0, i), (w, i)], fill=c)
    # 圆角 mask 裁剪（ss>0 → SS；ss=0 → FT-008 1x + α 羽化）
    img.putalpha(_ss_mask(w, h, radius, ss) if ss > 0 else _aa_mask(w, h, radius))
    # 描边（超采样描边层，避免 outline 二值锯齿）
    if border:
        img.alpha_composite(_ss_outline(w, h, radius, border, border_w, ss) if ss > 0
                            else _aa_outline(w, h, radius, border, border_w))
    # 顶部高光（圆角小，直接画可接受；用超采样描边层方式合成）
    if highlight:
        _hw, _hh = w - highlight[0] - highlight[2], h - highlight[1] - highlight[3]
        _hr = max(4, radius // 2)
        hl = (_ss_rounded_rect(_hw, _hh, _hr, (255, 255, 255, highlight[4]), ss=ss)
              if ss > 0 else
              _aa_rounded_rect(_hw, _hh, _hr, (255, 255, 255, highlight[4])))
        img.alpha_composite(hl, (highlight[0], highlight[1]))
    return save(img, out_dir, name)


def gen_gradient_stops(out_dir, name, w, h, stops, horizontal=True, radius=0, to9=False, ss=0):
    """多色标线性渐变（CSS linear-gradient 自动转图用）。
    stops: [(pos_0to1, (r,g,b,a)), ...]，至少 2 个色标；
    按 pos 线性插值逐行/逐列绘制。
    ⚠️ radius>0 时用圆角 mask 裁剪四角透明（透背景叠放不露方角）。
    ⚠️ ss>0 走 SS mask（**html2json 一律走这条**，形状分类见 knowledge/devflow/ui-asset-rules.md）；
    ss=0（默认）走 FT-008（1x + α 羽化）：**强曲率（radius≈min(w,h)/2 的药丸/圆）**下
    边界误差 mean 21~44/255 → 手写调用请改用 `rounded_rect_ss` 或传 ss>0（FT-010）。
    """
    if len(stops) < 2:
        stops = stops + [(1.0, stops[-1][1])] if stops else [(0.0, (0, 0, 0, 255)), (1.0, (255, 255, 255, 255))]
    stops = sorted(stops, key=lambda s: s[0])
    img = Image.new('RGBA', (w, h))
    d = ImageDraw.Draw(img)
    n = max(w, h)

    def _color_at(t):
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if p0 <= t <= p1:
                k = (t - p0) / max(1e-6, p1 - p0)
                return tuple(int(c0[j] + (c1[j] - c0[j]) * k) for j in range(4))
        return stops[-1][1]

    for i in range(n):
        t = i / max(1, n - 1)
        c = _color_at(t)
        if horizontal:
            d.line([(i, 0), (i, h)], fill=c)
        else:
            d.line([(0, i), (w, i)], fill=c)
    if radius > 0:
        # ss>0 → SS mask（理想覆盖率）；ss=0 → FT-008（1x + α 羽化，几何逐像素不漂）
        img.putalpha(_ss_mask(w, h, radius, ss) if ss > 0 else _aa_mask(w, h, radius))
    if to9:
        return to_9patch(img, radius, out_dir, name)
    return save(img, out_dir, name)


def gen_shadow_card(out_dir, name, w, h, radius, fill, shadow=None, border=None, border_w=1,
                    crop=True, ss=0):
    """带阴影的圆角卡片（CSS box-shadow 自动转图用）。
    ss>0：阴影层 / 主体圆角层 / 二次裁剪 mask 全走 SS（html2json 一律走这条）；
    ss=0（默认）：全走 FT-008（1x + α 羽化）—— 默认行为逐字节不变。
    shadow: (offset_x, offset_y, blur, (r,g,b,a))；阴影先画（超出卡片边缘 blur 模糊），
    最后整体圆角 mask 裁剪清掉残影（阴影模糊会溢出到弧线外，必须二次裁剪）。
    crop=True（默认）：裁掉多余透明边，图尺寸不定（历史行为）；
    crop=False：保完整画布 → 尺寸恒为 (w+2*pad) x (h+2*pad)（pad=max(2, blur+max(|ox|,|oy|))），
    主体卡片左上角恰好落在 (pad, pad) —— html2json 靠这个确定性把控件盒外扩，保证「图==控件」。
    """
    if shadow:
        ox, oy, blur, sc = shadow
        pad = max(2, blur + max(abs(ox), abs(oy)))
        cw, ch = w + pad * 2, h + pad * 2
        img = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
        # 阴影圆角矩形（高斯模糊）
        sh = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
        if ss > 0:
            # SS：阴影矩形画在 ss 画布上 → LANCZOS 缩回当覆盖率 mask，再只缩放 alpha
            # （不能用 paste(color, mask)：RGB 会被一起按 mask 缩小 → 边界发黑）
            _s = _ss_fit(cw, ch, ss, 'SS shadow')
            sbig = Image.new('L', (cw * _s, ch * _s), 0)
            ImageDraw.Draw(sbig).rounded_rectangle(
                [(pad + ox) * _s, (pad + oy) * _s,
                 (pad + ox + w) * _s - 1, (pad + oy + h) * _s - 1],
                radius=radius * _s, fill=255)
            smask = sbig.resize((cw, ch), Image.LANCZOS)
            sh = Image.new('RGBA', (cw, ch), sc)
            from PIL import ImageChops as _IC
            sh.putalpha(_IC.multiply(sh.getchannel('A'), smask))
        else:
            ImageDraw.Draw(sh).rounded_rectangle(
                [pad + ox, pad + oy, pad + ox + w - 1, pad + oy + h - 1],
                radius=radius, fill=sc)
        if blur > 0:
            sh = sh.filter(ImageFilter.GaussianBlur(blur))
        img.alpha_composite(sh)
        # 主体卡片（ss>0 → SS；ss=0 → FT-008：局部 w×h 圆角矩形后贴到 pad 位置）
        body = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
        body_patch = (_ss_rounded_rect(w, h, radius, fill, border, border_w, ss) if ss > 0
                      else _aa_rounded_rect(w, h, radius, fill, border, border_w))
        if ss > 0:
            # 真 source-over：半透明边界像素不会被「paste 当 mask」把 α 再乘一次
            # （paste(patch, patch) 会把 α 压成 α²/255 → 边界发虚/发暗）
            body.alpha_composite(body_patch, (pad, pad))
        else:
            body.paste(body_patch, (pad, pad), body_patch)
        img.alpha_composite(body)
        # 二次圆角裁剪（FT-008 超采样局部 mask）：清掉阴影残影
        # ⚠️ 2026-09-11 修：必须与已有 alpha **相乘**，不能直接 putalpha 覆盖 ——
        # 覆盖会把阴影的 alpha 渐变（10% 透明黑）压成 255 不透明 → 卡片四周出现一圈硬黑边
        # （视觉验收表现为“粗黑描边”，阴影柔化全丢）。
        mw, mh = w + 2 * blur + 2, h + 2 * blur + 2
        mask = Image.new('L', (cw, ch), 0)
        mask.paste(_ss_mask(mw, mh, radius + blur, ss) if ss > 0
                   else _aa_mask(mw, mh, radius + blur), (pad - blur - 1, pad - blur - 1))
        from PIL import ImageChops
        img.putalpha(ImageChops.multiply(img.getchannel('A'), mask))
        # 裁掉多余透明边（阴影下/右延伸）；crop=False 时保留完整画布 → 尺寸可预测（图==控件）
        if crop:
            bbox = img.getbbox()
            if bbox:
                img = img.crop(bbox)
        return save(img, out_dir, name)
    return save(_ss_rounded_rect(w, h, radius, fill, border, border_w, ss) if ss > 0
                else rounded_rect(w, h, radius, fill, border, border_w), out_dir, name)
    """状态点（实心圆，普通 PNG）"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([0, 0, size - 1, size - 1], fill=color)
    return save(img, out_dir, name)


def icon_circle(out_dir, name, size, color, kind="check"):
    """圆形图标（外圈 + 内部符号：check/charging/wifi/alert）。
    2026-09-03 修复：超采样抗锯齿（此前 1x 直画锯齿明显）。"""
    S = size * _G_SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = S // 10
    d.ellipse([m, m, S - m - 1, S - m - 1], outline=color, width=max(2, m))
    cx, cy = S // 2, S // 2
    if kind == "check":
        pts = [(cx - S // 4, cy), (cx - S // 12, cy + S // 5),
               (cx + S // 3, cy - S // 4)]
        d.line(pts, fill=color, width=max(3, m), joint="curve")
        _round_cap(d, pts[0], max(3, m) / 2.0, color)
        _round_cap(d, pts[-1], max(3, m) / 2.0, color)
    elif kind == "charging":
        pts = [(cx + S // 16, cy - S // 4), (cx - S // 5, cy + S // 12),
               (cx - S // 24, cy + S // 12), (cx - S // 8, cy + S // 4),
               (cx + S // 5, cy - S // 12), (cx + S // 24, cy - S // 12)]
        d.polygon(pts, fill=color)
    elif kind == "wifi":
        for r, wdt in ((S // 3, m), (S // 5, m), (S // 8, m)):
            d.arc([cx - r, cy - r, cx + r, cy + r], start=210, end=330, fill=color, width=wdt)
        d.ellipse([cx - m, cy + S // 8, cx + m, cy + S // 8 + 2 * m], fill=color)
    elif kind == "alert":
        pts = [(cx, cy - S // 3), (cx - S // 4, cy + S // 4), (cx + S // 4, cy + S // 4)]
        d.polygon(pts, fill=color)
        d.rectangle([cx - m // 2, cy - S // 10, cx + m // 2, cy + S // 12], fill=(255, 255, 255, 255))
    img = img.resize((size, size), Image.LANCZOS)
    return save(img, out_dir, name)


def frames_loading(out_dir, prefix, size, color, n=12, ring_r=None, width=None):
    """loading 旋转序列帧：n 张 PNG（size×size，圆环缺口旋转），配合 imageanim 动图控件
    循环次数 ≤0 无限循环。命名 <prefix>_00.png .. <prefix>_NN.png
    2026-09-03 修复：超采样抗锯齿。"""
    S = size * _G_SS
    cx = cy = S // 2
    ring_r = (ring_r or S // 3)
    width = width or max(3, S // 16)
    paths = []
    for i in range(n):
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        start = -90 + i * (360 // n)
        end = start + 300  # 缺口 60°
        d.arc([cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
              start=start, end=end, fill=color, width=width)
        img = img.resize((size, size), Image.LANCZOS)
        paths.append(save(img, out_dir, "%s_%02d.png" % (prefix, i)))
    return paths


def frames_loading_gif(out_dir, name, size, color, n=12, duration=80, ring_r=None, width=None):
    """loading 旋转动画 → GIF（imageanim 动图控件 play(file) 直接加载）。
    ZKImageAnim::play 播放的是 GIF/WebP 动画文件（非序列帧目录）；
    序列帧 PNG 用 Pillow save_all 打包成 GIF，循环次数 0 = 无限循环。
    2026-09-03 修复：超采样抗锯齿。"""
    S = size * _G_SS
    cx = cy = S // 2
    ring_r = ring_r or S // 3
    width = width or max(3, S // 16)
    frames = []
    for i in range(n):
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        start = -90 + i * (360 // n)
        end = start + 300
        d.arc([cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
              start=start, end=end, fill=color, width=width)
        frames.append(img.resize((size, size), Image.LANCZOS))
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, name)
    frames[0].save(p, save_all=True, append_images=frames[1:],
                   duration=duration, loop=0, transparency=0, disposal=2)
    print("  %s  %dx%d %dframes" % (name, size, size, n))
    return p


# ---------- 图标生成三级降级：AI 生图 → emoji 渲染 → 线条/几何兜底 ----------
# 供 MCP 工具 flythings_generate_ui_assets 调用：有 AI 能力用 AI，无 AI 能力也能本地出图。

# 彩色 emoji 字体候选（Windows Segoe UI Emoji / Linux Noto）
_EMOJI_FONT_CANDIDATES = [
    r'C:\Windows\Fonts\seguiemj.ttf',
    '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf',
    '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
]


def _emoji_font():
    for p in _EMOJI_FONT_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def emoji_icon(out_dir, name, size, ch):
    """emoji 彩色字形 -> 普通 PNG（无 AI 依赖）。

    [!] 2026-09-18 钟工：「emoji 表情包转图片的时候切图不完整」。
    根因：原实现在 1x 画布上从 (0,0) 直画再 bbox 裁剪 —— 彩色字形的 ascent 超出 size 时
    **顶部/右侧会被画布边缘切掉**，且四周无留白，真机上就是「图标缺一块 / 贴边」。
    现统一委托 `_emoji_img()`：**4x 超采样 + 3 倍画布居中 + bbox + 最长边缩到 86% + LANCZOS**，
    与 `emoji_icon_ss()` 同口径（html2json 两处自动转图调用点一并受益，不再两套写法）。
    """
    return save(_emoji_img(size, ch), out_dir, name)


# ---------- data-icon 语义图标：emoji 彩色优先（2026-09-04 定规：风格在 HTML 原型阶段选定） ----------
# 图标规范名 → emoji 字形（带 VS16 强制彩色呈现）；menu/more/power/share/bluetooth 等
# 无对应彩色 emoji 的不收录，调用方自动降级线框。
_GLYPH_EMOJI = {
    'back': '⬅️', 'forward': '➡️', 'up': '⬆️', 'down': '⬇️',
    'close': '❌', 'check': '✅', 'plus': '➕', 'minus': '➖',
    'search': '🔍', 'home': '🏠', 'list': '📋',
    'play': '▶️', 'pause': '⏸️', 'stop': '⏹️', 'prev': '⏮️', 'next': '⏭️',
    'volume': '🔊', 'mute': '🔇', 'delete': '🗑️',
    'edit': '✏️', 'download': '📥', 'upload': '📤',
    'user': '👤', 'lock': '🔒', 'info': 'ℹ️', 'warning': '⚠️',
    'camera': '📷', 'clock': '🕐', 'calendar': '📅', 'bell': '🔔',
    'mic': '🎤', 'location': '📍', 'mail': '✉️', 'eye': '👁️',
    'video': '🎥', 'phone': '📞', 'settings': '⚙️',
    'refresh': '🔄', 'wifi': '📶', 'heart': '❤️', 'star': '⭐',
}


def _emoji_img(size, ch):
    """emoji 彩色字形 → RGBA Image：4x 超采样 + 3 倍画布居中（修顶部裁切）+
    bbox 裁剪 + 最长边缩至 86% 画布（四周留白，各图标视觉大小一致）+ LANCZOS 缩回。"""
    fp = _emoji_font()
    if not fp:
        raise RuntimeError('未找到彩色 emoji 字体（seguiemj.ttf / NotoColorEmoji.ttf）')
    SS = 4
    S = size * SS
    big = Image.new('RGBA', (S * 3, S * 3), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    f = ImageFont.truetype(fp, int(S * 0.82))
    d.text((S, S), ch, font=f, embedded_color=True)
    bbox = big.getbbox()
    if bbox:
        big = big.crop(bbox)
    w, h = big.size
    target = int(S * 0.86)
    scale = target / max(w, h)
    w2, h2 = max(1, int(w * scale)), max(1, int(h * scale))
    big = big.resize((w2, h2), Image.LANCZOS)
    canvas = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    canvas.paste(big, ((S - w2) // 2, (S - h2) // 2), big)
    return canvas.resize((size, size), Image.LANCZOS)


def emoji_icon_ss(out_dir, name, size, ch):
    """emoji 彩色图标（4x 超采样抗锯齿版）。"""
    return save(_emoji_img(size, ch), out_dir, name)


def emoji_icon_box(out_dir, name, w, h, ch):
    """emoji 图标 -> 尺寸**恰好等于控件盒 (w,h)** 的 PNG。

    [!] 2026-09-18 钟工：「emoji 表情包转图片的时候切图不完整」。
    根因：html2json 原先按 `size = max(w, h)` 出**正方形**图，却挂在 (w, h) 的控件盒上
    （图 != 盒，违反 assets 铁律）-> 扁盒里塞方图，字形被压扁/切掉，真机看着就是「切图不完整」。
    本函数：字形按 **min(w,h)** 缩放（长宽比不拉伸）+ 居中铺在 (w,h) 透明画布 -> 图 == 盒。
    """
    m = max(1, min(int(w), int(h)))
    return save(_paste_canvas(_emoji_img(m, ch), m, (w, h)), out_dir, name)


def _paste_canvas(img, size, canvas):
    """非正方控件画布：图标 size 居中不变形（与 glyph_icon 的 canvas 语义一致）。"""
    if canvas and (int(canvas[0]), int(canvas[1])) != (int(size), int(size)):
        cw, chh = int(canvas[0]), int(canvas[1])
        base = Image.new('RGBA', (cw, chh), (0, 0, 0, 0))
        base.paste(img, ((cw - int(size)) // 2, (chh - int(size)) // 2), img)
        img = base
    return img


def glyph_icon_ex(out_dir, name, glyph, size=48, color=None, pressed=False, canvas=None,
                  style='emoji'):
    """data-icon 语义图标统一入口（2026-09-04：默认 emoji 彩色，风格在 HTML 原型阶段选定）。
    style:
      'emoji'（默认）查 _GLYPH_EMOJI 映射 + 本地彩色 emoji 字体 4x 超采样渲染，
              未映射/无字体自动降级线框
      'line'  iconfont 矢量线框（8x 超采样，等价 glyph_icon）
      'ai'    AI 生图（需 OPENAI_API_KEY），失败降级 emoji → 线框
    pressed 按下态：emoji/ai 整体压暗 20%，线框提亮 35%。
    canvas=(cw,ch) 非正方控件画布，图标 size 居中不变形。返回保存路径。"""
    g = glyph_canonical(glyph)
    img = None
    if style == 'ai':
        try:
            img = _ai_img(size, '%s icon, flat modern UI icon, single centered'
                          % (g or glyph))
        except Exception:
            img = None   # 降级 emoji → 线框
    if img is None and style in ('emoji', 'ai'):
        ech = _GLYPH_EMOJI.get(g or '') or _GLYPH_EMOJI.get(str(glyph).strip().lower())
        if ech and _emoji_font():
            img = _emoji_img(size, ech)
    if img is not None:
        if pressed:
            r, gg, b, a = img.split()
            dark = Image.merge('RGB', [c.point(lambda v: int(v * 0.8)) for c in (r, gg, b)])
            img = Image.merge('RGBA', (*dark.split(), a))
        return save(_paste_canvas(img, size, canvas), out_dir, name)
    return glyph_icon(out_dir, name, glyph, size=size, color=color, pressed=pressed,
                      canvas=canvas)


def _ai_img(size, prompt):
    """OpenAI gpt-image-2 生图 → RGBA Image（不保存）。无 key/网络失败抛异常。"""
    import base64
    import urllib.request
    key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not key:
        raise RuntimeError('未配置 OPENAI_API_KEY，降级本地生成')
    body = json.dumps({
        'model': 'gpt-image-2',
        'prompt': prompt + ' (transparent background, single centered icon, game asset style, no text)',
        'n': 1,
        'size': '1024x1024',
        'background': 'transparent',
        'output_format': 'png',
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://api.openai.com/v1/images/generations', data=body,
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.load(r)
    b64 = resp['data'][0].get('b64_json')
    if not b64:
        raise RuntimeError('AI 生图响应无 b64_json')
    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert('RGBA')
    return img.resize((size, size), Image.LANCZOS)


def ai_icon(out_dir, name, size, prompt):
    """OpenAI gpt-image-2 生图（透明背景 PNG）。无 key/网络失败抛异常，由调用方降级。"""
    return save(_ai_img(size, prompt), out_dir, name)


# 线条/几何兜底图标：kind → 内部形状（check/charging/wifi/alert + 补充）
_LINE_KINDS = ('check', 'charging', 'wifi', 'alert', 'circle', 'square', 'star', 'heart')


def line_icon(out_dir, name, size, color, kind='check'):
    """纯线条/几何兜底（无 AI 无 emoji 字体时仍能出图）。
    2026-09-03 修复：超采样抗锯齿（此前 1x 直画锯齿明显）。"""
    if kind in ('check', 'charging', 'wifi', 'alert'):
        return icon_circle(out_dir, name, size, color, kind)
    S = size * _G_SS
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = S // 5
    cx = cy = S // 2
    if kind == 'circle':
        d.ellipse([m, m, S - m, S - m], outline=color, width=max(2, S // 12))
    elif kind == 'square':
        d.rounded_rectangle([m, m, S - m, S - m], radius=S // 10,
                            outline=color, width=max(2, S // 12))
    elif kind == 'star':
        import math as _m2
        pts = []
        for i in range(10):
            ang = -90 + i * 36
            rr = S // 3 if i % 2 == 0 else S // 7
            pts.append((cx + rr * _m2.cos(_m2.radians(ang)),
                        cy + rr * _m2.sin(_m2.radians(ang))))
        d.polygon(pts, outline=color, width=max(2, S // 16))
    elif kind == 'heart':
        wdt = max(2, S // 14)
        d.ellipse([cx - S // 4, cy - S // 4, cx, cy + S // 4], outline=color, width=wdt)
        d.ellipse([cx, cy - S // 4, cx + S // 4, cy + S // 4], outline=color, width=wdt)
        d.line([(cx - S // 4, cy + S // 10), (cx, cy + S // 3), (cx + S // 4, cy + S // 10)],
               fill=color, width=wdt)
    img = img.resize((size, size), Image.LANCZOS)
    return save(img, out_dir, name)


def gen_icon(out_dir, name, size=128, prompt='', emoji='', color=None, kind='check'):
    """图标生成统一入口（三级降级）：AI 生图 → emoji 渲染 → 线条/几何。
    返回 (path, method)，method ∈ {'ai', 'emoji', 'line'}。
    - 有 OPENAI_API_KEY 且网络可达 → ai（最精致）
    - 无 AI 能力但有彩色 emoji 字体 → emoji（卡通风，羊了个羊同款）
    - 都不可用 → line（线条几何兜底，任何环境都能出）
    """
    if prompt.strip():
        try:
            return ai_icon(out_dir, name, size, prompt), 'ai'
        except Exception:
            pass  # 降级
    if emoji:
        try:
            return emoji_icon(out_dir, name, size, emoji), 'emoji'
        except Exception:
            pass  # 降级
    c = color or (0x42, 0xC9, 0xFF, 255)
    return line_icon(out_dir, name, size, c, kind if kind in _LINE_KINDS else 'check'), 'line'


def gen_ui_assets(project_root, assets):
    """MCP flythings_generate_ui_assets 底层实现：批量生成 UI 图片资源。
    assets: JSON 数组字符串或 list，每项：
      {"name": "icon_ok.png", "size": 128, "prompt": "cute sheep icon...",
       "emoji": "🐑", "color": "#42C9FF" 或 [r,g,b,a], "kind": "check"}
    name 必填；prompt 有则优先 AI；emoji 有则 AI 失败后用它；color+kind 为最终线条兜底。
    输出到 <项目>/resources/images/，返回每项生成方式。"""
    if isinstance(assets, str):
        try:
            assets = json.loads(assets)
        except Exception as e:
            return {'success': False, 'error': f'assets 不是合法 JSON: {e}'}
    out = os.path.join(os.path.abspath(project_root), 'resources', 'images')
    os.makedirs(out, exist_ok=True)
    results = []
    for i, a in enumerate(assets or []):
        if not isinstance(a, dict):
            results.append({'index': i, 'success': False, 'error': '非对象'})
            continue
        name = a.get('name') or ('gen_%02d.png' % i)
        if not name.endswith('.png'):
            name += '.png'
        size = int(a.get('size', 128) or 128)
        color = a.get('color')
        if isinstance(color, str) and color.startswith('#'):
            h = color.lstrip('#')
            color = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
        if isinstance(color, list) and len(color) >= 3:  # [r,g,b] / [r,g,b,a] → tuple
            color = tuple(int(c) for c in color[:4])
        try:
            path, method = gen_icon(out, name, size,
                                    prompt=str(a.get('prompt', '') or ''),
                                    emoji=str(a.get('emoji', '') or ''),
                                    color=color, kind=str(a.get('kind', 'check') or 'check'))
            # path: 相对 resources 的引用路径（images/xxx.png，json 布局直接引用）
            results.append({'index': i, 'name': name, 'path': 'images/' + name,
                            'absolutePath': path,
                            'method': method, 'size': size, 'success': True})
        except Exception as e:
            results.append({'index': i, 'name': name, 'success': False, 'error': str(e)})
    return {'success': True, 'outputDir': out, 'assets': results,
            'note': 'method: ai=AI生图 / emoji=本地emoji渲染 / line=线条几何兜底'}


# ---------- iconfont 风格矢量线框图标库（2026-09-03 沛哥定规：图标优先）----------
# 用途：返回/播放/暂停/设置/搜索/删除等常用操作必须用图标（禁止纯文字按钮糊弄），
# HTML 里写 data-icon="play"（或 class="iconfont icon-play"）→ 转换器调 glyph_icon 自动生成 PNG。
# 24 网格坐标（Feather 风格），ss=4 超采样 + LANCZOS 缩回抗锯齿；描边=STROKE(2 单位)。

_G_STROKE = 2.0          # 24 网格上描边宽度（Feather 同款）
_G_SS = 8                # 超采样倍数（画 8 倍再 LANCZOS 缩回；2026-09-03 沛哥反馈锯齿，4→8）


def _round_cap(d, p, r, color):
    """线段端点补圆（round cap）：PIL line 端点是平头，斜线端点呈毛刺/缺口。
    Feather 风格图标端点为圆头，在超采样画布上给每条开放线段两端补实心圆。"""
    d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color)


def _glyph_render(ops, size, color):
    """ops 图标指令 → RGBA Image（size×size）。
    op 格式: ('l',[(x1,y1),(x2,y2)]) 线 / ('pl',[...]) 折线(曲线连接)
             ('poly',[...]) 闭合多边形(描边) / ('fill',[...]) 填充多边形
             ('c',(cx,cy,r)) 圆描边 / ('fc',(cx,cy,r)) 实心圆
             ('rect',(x,y,w,h,r)) 圆角矩形描边 / ('frect',(x,y,w,h,r)) 实心
             ('arc',(cx,cy,r,a0,a1)) 圆弧描边（PIL 角度：0=3点,顺时针,270=12点）
    """
    S = size * _G_SS
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = S / 24.0
    w = max(2, int(round(_G_STROKE * k)))
    cap_r = w / 2.0
    for op in ops:
        t = op[0]
        if t == 'l':
            (x1, y1), (x2, y2) = op[1]
            p1, p2 = (x1 * k, y1 * k), (x2 * k, y2 * k)
            d.line([p1, p2], fill=color, width=w)
            _round_cap(d, p1, cap_r, color)   # 圆头端点（去毛刺）
            _round_cap(d, p2, cap_r, color)
        elif t == 'pl':
            pts = [(x * k, y * k) for x, y in op[1]]
            d.line(pts, fill=color, width=w, joint='curve')
            _round_cap(d, pts[0], cap_r, color)   # 折线首尾圆头
            _round_cap(d, pts[-1], cap_r, color)
        elif t == 'poly':
            pts = [(x * k, y * k) for x, y in op[1]]
            d.line(pts + [pts[0]], fill=color, width=w, joint='curve')
        elif t == 'fill':
            d.polygon([(x * k, y * k) for x, y in op[1]], fill=color)
        elif t == 'c':
            cx, cy, r = op[1]
            d.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k],
                      outline=color, width=w)
        elif t == 'fc':
            cx, cy, r = op[1]
            d.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], fill=color)
        elif t == 'rect':
            x, y, ww, hh, r = op[1]
            d.rounded_rectangle([x * k, y * k, (x + ww) * k, (y + hh) * k],
                                radius=r * k, outline=color, width=w)
        elif t == 'frect':
            x, y, ww, hh, r = op[1]
            d.rounded_rectangle([x * k, y * k, (x + ww) * k, (y + hh) * k],
                                radius=r * k, fill=color)
        elif t == 'arc':
            cx, cy, r, a0, a1 = op[1]
            d.arc([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k],
                  start=a0, end=a1, fill=color, width=w)
            # arc 两端补圆头（PIL 角度体系：0=3点，顺时针，端点坐标同 arc 计算）
            for a_deg in (a0, a1):
                a = _math.radians(a_deg)
                ep = ((cx + r * _math.cos(a)) * k, (cy + r * _math.sin(a)) * k)
                _round_cap(d, ep, cap_r, color)
    img = img.resize((size, size), Image.LANCZOS)
    return img


# ---- 复杂图标用专用函数（三角函数/循环），简单图标用 ops 数据 ----
# 2026-09-03 重写：全部数学采样绘制，绕开 PIL arc 方向歧义（θ 增大=屏幕顺时针，
# 视觉角= -θ）；心形用解析曲线采样（两圆+三角拼接有断点）。
import math as _math


def _gear(size, color):
    """设置齿轮（8 齿梯形 + 厚环 + 中心孔）"""
    S = size * _G_SS
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = S / 24.0
    w = max(2, int(round(_G_STROKE * k)))
    cx = cy = 12.0
    pts = []
    # 先画 8 齿（内 6.8 → 外 9.6，齿宽 4.4 弧单位，梯形外侧略窄）
    for i in range(8):
        a = _math.radians(i * 45 - 90)
        c, s = _math.cos(a), _math.sin(a)
        # 齿中心方向两侧展开：顶边（外）窄、底边（内）宽
        pa = _math.radians(i * 45 - 90 + 3.4)
        pb = _math.radians(i * 45 - 90 - 3.4)
        ca, sa = _math.cos(pa), _math.sin(pa)
        cb, sb = _math.cos(pb), _math.sin(pb)
        # 底角（内圈 6.8 处，角宽 5.2°）
        pa2 = _math.radians(i * 45 - 90 + 5.2)
        pb2 = _math.radians(i * 45 - 90 - 5.2)
        c2a, s2a = _math.cos(pa2), _math.sin(pa2)
        c2b, s2b = _math.cos(pb2), _math.sin(pb2)
        pts += [(cx + 6.8 * c2a, cy + 6.8 * s2a), (cx + 9.6 * ca, cy + 9.6 * sa),
                (cx + 9.6 * cb, cy + 9.6 * sb), (cx + 6.8 * c2b, cy + 6.8 * s2b)]
    d.polygon([(x * k, y * k) for x, y in pts], fill=color)          # 齿（梯形实心）
    # 齿根环（覆盖齿底，形成圆形齿盘）
    d.ellipse([(cx - 7.0) * k, (cy - 7.0) * k, (cx + 7.0) * k, (cy + 7.0) * k],
              fill=color)
    # 中心孔（镂空：用透明色重绘不现实，改为画小圆同底色会穿帮 → 用 alpha 0 不可行；
    # 标准做法：齿盘画完后中心挖孔用源底透明：画孔=同尺寸透明不可得，改用「细环+内圆描边」视觉镂空：
    # 实际方案：中心孔直接在齿盘填充前预留 —— 先画环再画孔色覆盖不可取；
    # 采用 draw 两次：第一次填充齿+盘，第二次用 (0,0,0,0) 圆做 alpha 挖孔）
    hole = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(hole).ellipse(
        [(cx - 3.3) * k, (cy - 3.3) * k, (cx + 3.3) * k, (cy + 3.3) * k], fill=(0, 0, 0, 255))
    img.paste((0, 0, 0, 0), (0, 0), hole)   # 挖中心孔（真透明）
    # 中心孔描边（齿轮轴感）
    d = ImageDraw.Draw(img)
    d.ellipse([(cx - 3.3) * k, (cy - 3.3) * k, (cx + 3.3) * k, (cy + 3.3) * k],
              outline=color, width=max(2, w // 2))
    img = img.resize((size, size), Image.LANCZOS)
    return img


def _refresh(size, color):
    """刷新/旋转箭头（逆时针 ↺，Feather rotate-ccw 同构）"""
    S = size * _G_SS
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = S / 24.0
    w = max(2, int(round(_G_STROKE * k)))
    cx = cy = 12.0
    r = 8.4
    # 弧：数学角 135°→405°（y 上正），留顶口 45°~135°（缺口朝上偏左，箭头补位）
    pts = []
    for ang in range(135, 406, 3):
        a = _math.radians(ang)
        pts.append((cx + r * _math.cos(a), cy - r * _math.sin(a)))  # y 翻转为图像坐标
    d.line([(x * k, y * k) for x, y in pts], fill=color, width=w, joint='curve')
    # 箭头：弧末端（ang=45°）切线方向继续指，形成逆时针指示
    ae = _math.radians(45.0)
    pe = (cx + r * _math.cos(ae), cy - r * _math.sin(ae))      # 弧终点
    tang = (-_math.sin(ae), -_math.cos(ae))                     # CCW 切线（图像坐标）
    tip = (pe[0] + tang[0] * 3.6, pe[1] + tang[1] * 3.6)
    # 箭头尾边：径向方向（垂直于切线）向两侧展开
    rad = (_math.cos(ae), -_math.sin(ae))
    b1 = (pe[0] + rad[0] * 2.1, pe[1] + rad[1] * 2.1)
    b2 = (pe[0] - rad[0] * 2.1, pe[1] - rad[1] * 2.1)
    d.polygon([(b1[0] * k, b1[1] * k), (b2[0] * k, b2[1] * k), (tip[0] * k, tip[1] * k)],
              fill=color)
    img = img.resize((size, size), Image.LANCZOS)
    return img


def _wifi(size, color):
    S = size * _G_SS
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = S / 24.0
    w = max(2, int(round(_G_STROKE * k)))
    for rr in (9.2, 6.6, 4.0):
        pts = []
        for ang in range(195, 346, 3):
            a = _math.radians(ang)
            pts.append((12 + rr * _math.cos(a), 13.2 - rr * _math.sin(a)))
        d.line([(x * k, y * k) for x, y in pts], fill=color, width=w, joint='curve')
    d.ellipse([(11.0 - w * 0.45) * k, (20.4 - w * 0.45) * k,
               (11.0 + w * 0.45) * k, (20.4 + w * 0.45) * k], fill=color)
    d.ellipse([9.6 * k, 18.4 * k, 14.4 * k, 23.2 * k], fill=color)
    img = img.resize((size, size), Image.LANCZOS)
    return img


def _heart(size, color):
    """心形：经典解析曲线采样（无拼接断点，天然对称）"""
    S = size * _G_SS
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = S / 24.0
    # 参数曲线（数学 y 上正），尖角在底部：
    # x=16sin^3 t, y=13cos t-5cos2t-2cos3t-cos4t （x∈[-16,16]，y 实际范围 ~[-17,6]）
    raw = []
    for i in range(0, 720, 3):
        t = _math.radians(i * 0.5)
        x = 16 * _math.sin(t) ** 3
        y = 13 * _math.cos(t) - 5 * _math.cos(2 * t) - 2 * _math.cos(3 * t) - _math.cos(4 * t)
        raw.append((x, -y))   # 翻转为图像坐标（尖角向下）
    # 动态归一化到 24 网格留边 2 单位（防顶部超界裁剪，2026-09-03 修复）
    xs = [p[0] for p in raw]; ys = [p[1] for p in raw]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    span = max(x1 - x0, y1 - y0)
    # 等比缩放至 20 单位并居中于 (12,12)
    pts = [(2 + (p[0] - x0) / span * 20, 2 + (p[1] - y0) / span * 20) for p in raw]
    d.polygon([(px * k, py * k) for px, py in pts], fill=color)
    img = img.resize((size, size), Image.LANCZOS)
    return img


def _star(size, color):
    S = size * _G_SS
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = S / 24.0
    pts = []
    for i in range(10):
        a = _math.radians(-90 + i * 36)
        r = 10.2 if i % 2 == 0 else 4.3
        pts.append((12 + r * _math.cos(a), 12 + r * _math.sin(a)))
    d.polygon([(x * k, y * k) for x, y in pts], fill=color)
    img = img.resize((size, size), Image.LANCZOS)
    return img


def _bluetooth(size, color):
    """蓝牙：Feather 官方两段折线（24 网格原坐标，无溢出）"""
    S = size * _G_SS
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = S / 24.0
    w = max(2, int(round(_G_STROKE * k)))
    p1 = [(6.5, 6.5), (17.5, 17.5), (12, 23)]
    p2 = [(12, 1), (17.5, 6.5), (6.5, 17.5)]
    d.line([(x * k, y * k) for x, y in p1], fill=color, width=w, joint='curve')
    d.line([(x * k, y * k) for x, y in p2], fill=color, width=w, joint='curve')
    img = img.resize((size, size), Image.LANCZOS)
    return img


# ---- 图标指令表（24 网格坐标，Feather 同款比例）----
_GLYPHS = {
    'back':      [('l', [(19, 12), (5, 12)]), ('pl', [(12, 5), (5, 12), (12, 19)])],
    'forward':   [('l', [(5, 12), (19, 12)]), ('pl', [(12, 5), (19, 12), (12, 19)])],
    'up':        [('l', [(12, 19), (12, 5)]), ('pl', [(19, 12), (12, 5), (5, 12)])],
    'down':      [('l', [(12, 5), (12, 19)]), ('pl', [(5, 12), (12, 19), (19, 12)])],
    'close':     [('l', [(18, 6), (6, 18)]), ('l', [(6, 6), (18, 18)])],
    'check':     [('pl', [(20, 6), (9, 17), (4, 12)])],
    'plus':      [('l', [(12, 5), (12, 19)]), ('l', [(5, 12), (19, 12)])],
    'minus':     [('l', [(5, 12), (19, 12)])],
    'menu':      [('l', [(3, 6), (21, 6)]), ('l', [(3, 12), (21, 12)]), ('l', [(3, 18), (21, 18)])],
    'more':      [('fc', (5.5, 12, 1.7)), ('fc', (12, 12, 1.7)), ('fc', (18.5, 12, 1.7))],
    'search':    [('c', (11, 11, 7.4)), ('l', [(16.6, 16.6), (21, 21)])],
    'home':      [('pl', [(3, 10.5), (12, 3.2), (21, 10.5)]),
                  ('pl', [(5.5, 9.7), (5.5, 20), (18.5, 20), (18.5, 9.7)]),
                  ('pl', [(10.2, 20), (10.2, 14), (13.8, 14), (13.8, 20)])],
    'list':      [('fc', (4, 6, 1.3)), ('l', [(8, 6), (20, 6)]), ('fc', (4, 12, 1.3)),
                  ('l', [(8, 12), (20, 12)]), ('fc', (4, 18, 1.3)), ('l', [(8, 18), (20, 18)])],
    'play':      [('fill', [(5, 4), (5, 20), (19.5, 12)])],
    'pause':     [('frect', (6, 5, 4, 14, 0.8)), ('frect', (14, 5, 4, 14, 0.8))],
    'stop':      [('frect', (6, 6, 12, 12, 1.2))],
    'prev':      [('frect', (5, 5, 3, 14, 0.8)), ('fill', [(19, 5), (19, 19), (8.5, 12)])],
    'next':      [('frect', (16, 5, 3, 14, 0.8)), ('fill', [(5, 5), (5, 19), (15.5, 12)])],
    'power':     [('l', [(12, 3), (12, 12)]), ('arc', (12, 12, 9, 135, 405))],
    'volume':    [('fill', [(11, 5), (11, 9), (6, 9), (6, 15), (11, 15), (11, 19)]),
                  ('arc', (12.5, 12, 4.5, -45, 45)), ('arc', (14, 12, 7.5, -45, 45))],
    'mute':      [('fill', [(11, 5), (11, 9), (6, 9), (6, 15), (11, 15), (11, 19)]),
                  ('l', [(15.5, 8.5), (20.5, 15.5)]), ('l', [(20.5, 8.5), (15.5, 15.5)])],
    'delete':    [('pl', [(3, 6.5), (21, 6.5)]), ('pl', [(8, 6.5), (8.5, 4.5), (15.5, 4.5), (16, 6.5)]),
                  ('pl', [(6.5, 6.5), (7.3, 20), (16.7, 20), (17.5, 6.5)]),
                  ('l', [(10, 10), (10, 16.5)]), ('l', [(14, 10), (14, 16.5)])],
    'edit':      [('l', [(17.2, 3.2), (20.8, 6.8)]), ('pl', [(15.2, 6.2), (5.5, 15.9), (4.2, 19.8), (8.1, 18.5),
                                                       (17.8, 8.8)]), ('l', [(17.8, 8.8), (20.8, 6.8)])],
    'share':     [('fc', (18, 5.5, 2)), ('fc', (6.5, 12.5, 2)), ('fc', (18, 18.5, 2)),
                  ('l', [(16.4, 7), (8.1, 11.5)]), ('l', [(8.1, 13.5), (16.4, 17)])],
    'download':  [('pl', [(4, 14), (4, 18.5), (20, 18.5), (20, 14)]), ('pl', [(12, 3), (12, 14.5)]),
                  ('pl', [(7, 9.5), (12, 14.5), (17, 9.5)])],
    'upload':    [('pl', [(4, 14), (4, 18.5), (20, 18.5), (20, 14)]), ('pl', [(12, 20.5), (12, 9)]),
                  ('pl', [(7, 13.5), (12, 8.5), (17, 13.5)])],
    'user':      [('c', (12, 7.5, 4.2)), ('arc', (5.5, 11.5, 7.5, 200, 340))],
    'lock':      [('rect', (5.5, 10.5, 13, 9.5, 2)), ('arc', (12, 8.5, 4.6, 180, 360)), ('fc', (12, 15, 1.6))],
    'info':      [('c', (12, 12, 9)), ('l', [(12, 11.5), (12, 16.5)]), ('fc', (12, 8, 1.3))],
    'warning':   [('fill', [(12, 3.5), (21, 20), (3, 20)]), ('l', [(12, 9.5), (12, 14.5)]), ('fc', (12, 17.3, 1.3))],
    'camera':    [('pl', [(3, 8), (3, 17.5), (21, 17.5), (21, 8), (15.5, 8), (14, 5.5), (10, 5.5), (8.5, 8), (3, 8)]),
                  ('c', (12, 12.6, 3.6))],
    'clock':     [('c', (12, 12, 9)), ('pl', [(12, 7), (12, 12), (15.5, 14.5)])],
    'calendar':  [('rect', (3, 4.5, 18, 15.5, 2)), ('l', [(3, 9.5), (21, 9.5)]),
                  ('l', [(8, 2.5), (8, 6)]), ('l', [(16, 2.5), (16, 6)])],
    'bell':      [('arc', (12, 13.5, 8.5, 195, 345)), ('pl', [(4.5, 16.5), (19.5, 16.5)]),
                  ('pl', [(9.2, 20), (14.8, 20)]), ('fc', (12, 5.2, 1.2))],
    'mic':       [('rect', (9.2, 3, 5.6, 11, 2.6)), ('pl', [(12, 14), (12, 18)]),
                  ('arc', (12, 17, 4.6, 0, 180))],
    'location':  [('fill', [(12, 2.5), (19.5, 12.5), (12, 21.5), (4.5, 12.5)]),
                  ('fc', (12, 11.5, 2.6))],
    'mail':      [('rect', (3, 6, 18, 12, 1.5)), ('pl', [(4, 7.2), (12, 13), (20, 7.2)])],
    'eye':       [('arc', (12, 12, 8.5, 195, 345)), ('arc', (12, 12, 8.5, 15, 165)), ('fc', (12, 12, 2.6))],
    'video':     [('rect', (2.5, 6.5, 13, 11, 1.5)), ('fill', [(16.5, 9), (21, 12), (16.5, 15)])],
    'phone':     [('pl', [(7, 3.5), (5.2, 5.3), (5.2, 6.5), (5.4, 9.3), (7.5, 12.8), (11.2, 16.5), (14.7, 18.6),
                          (17.5, 18.8), (18.7, 18.8), (20.5, 17), (20.5, 14.6), (16.9, 12.5), (14.5, 13.2),
                          (12.9, 13.2), (10.8, 11.1), (10.8, 9.5), (11.5, 7.1), (9.4, 3.5), (7, 3.5)])],
}

# 别名：中文/同义词 → 规范英文名（HTML data-icon 可写中文）
_GLYPH_ALIAS = {
    '返回': 'back', 'back': 'back', 'left': 'back', 'arrow-left': 'back', 'arrow_left': 'back', 'prev': 'prev',
    '前进': 'forward', 'right': 'forward', 'arrow-right': 'forward', 'next': 'next', '下一首': 'next',
    '上': 'up', 'arrow-up': 'up', '向上': 'up', '下': 'down', 'arrow-down': 'down', '向下': 'down',
    '关闭': 'close', '叉': 'close', 'x': 'close', '取消': 'close',
    '确定': 'check', '对勾': 'check', 'ok': 'check', '勾': 'check',
    '加': 'plus', 'add': 'plus', '新增': 'plus', '减': 'minus', 'remove': 'minus',
    '菜单': 'menu', '更多': 'more', '搜索': 'search', '查': 'search',
    '主页': 'home', '首页': 'home', '返回主页': 'home',
    '列表': 'list', '播放': 'play', '暂停': 'pause', '停止': 'stop', '上一首': 'prev', '上一曲': 'prev',
    '重播': 'refresh', '刷新': 'refresh', 'refresh': 'refresh', '旋转': 'refresh', 'reload': 'refresh',
    '电源': 'power', '开机': 'power', '音量': 'volume', 'vol': 'volume', '静音': 'mute', 'mute': 'mute',
    '删除': 'delete', 'trash': 'delete', '垃圾桶': 'delete', '编辑': 'edit', '改名': 'edit', 'pencil': 'edit',
    '分享': 'share', '下载': 'download', '上传': 'upload', '用户': 'user', '人': 'user', '我的': 'user',
    '锁': 'lock', '锁定': 'lock', '信息': 'info', 'i': 'info', '详情': 'info',
    '警告': 'warning', '告警': 'warning', 'alert': 'warning', '拍照': 'camera', '相机': 'camera',
    '时间': 'clock', '时钟': 'clock', '日历': 'calendar', '日期': 'calendar', '通知': 'bell', '铃铛': 'bell',
    '麦克风': 'mic', '语音': 'mic', '定位': 'location', '位置': 'location', '邮件': 'mail', '邮箱': 'mail',
    '眼睛': 'eye', '预览': 'eye', '录像': 'video', '摄像': 'video', '电话': 'phone', '拨打': 'phone',
    '设置': 'settings', 'gear': 'settings', 'wifi': 'wifi', '无线': 'wifi', '蓝牙': 'bluetooth', 'bt': 'bluetooth',
    '收藏': 'star', '星标': 'star', '喜欢': 'heart', '心': 'heart', 'favorite': 'heart',
}


def _glyph_draw(glyph, size, color):
    """glyph(规范英文名) → RGBA Image；未收录抛 KeyError。"""
    glyph = _GLYPH_ALIAS.get(str(glyph).strip().lower(), str(glyph).strip())
    if glyph == 'settings':
        return _gear(size, color)
    if glyph == 'refresh':
        return _refresh(size, color)
    if glyph == 'wifi':
        return _wifi(size, color)
    if glyph == 'heart':
        return _heart(size, color)
    if glyph == 'star':
        return _star(size, color)
    if glyph == 'bluetooth':
        return _bluetooth(size, color)
    ops = _GLYPHS.get(glyph)
    if ops is None:
        raise KeyError(glyph)
    return _glyph_render(ops, size, color)


def glyph_list():
    """全部可用图标名（规范英文名，用于转换器 warning 提示）"""
    return sorted(_GLYPHS.keys()) + ['settings', 'refresh', 'wifi', 'heart', 'star', 'bluetooth']


def glyph_canonical(name):
    """图标名（英文/中文别名）→ 规范英文名；未收录返回 None。
    转换器用：校验 data-icon 是否收录 + 生成规范文件名（避免中文/别名进文件名）。"""
    s = str(name or '').strip().lower()
    g = _GLYPH_ALIAS.get(s, s)
    if g in _GLYPHS or g in ('settings', 'refresh', 'wifi', 'heart', 'star', 'bluetooth'):
        return g
    return None


def glyph_icon(out_dir, name, glyph, size=48, color=None, pressed=False, canvas=None):
    """iconfont 风格矢量线框图标 → PNG。
    glyph: 英文名或中文别名（back/返回/play/播放...）；color: (r,g,b,a) 或 None(默认浅色)；
    pressed=True 生成按下态（图标同形 + 高亮提亮，供按钮 picTab pic1）。
    canvas=(cw,ch) 可选：输出非正方形画布（控件非正方时用），图标 size 居中不变形。
    返回相对 resources 引用路径 images/<name>.png。未收录抛 KeyError（调用方给 warning）。
    """
    if color is None:
        color = (0xD8, 0xE2, 0xF0, 255)   # 默认浅灰蓝（深色主题友好）
    else:
        color = tuple(int(c) for c in color[:4])
    img = _glyph_draw(glyph, size, color)
    if pressed:
        # 按下态：颜色提亮 35%（深底主题按钮点击反馈）
        pcol = tuple(int(min(255, c + (255 - c) * 0.35)) for c in color[:3]) + (color[3],)
        img = _glyph_draw(glyph, size, pcol)
    if canvas:
        cw, ch = int(canvas[0]), int(canvas[1])
        if (cw, ch) != (int(size), int(size)):
            base = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
            base.paste(img, ((cw - int(size)) // 2, (ch - int(size)) // 2), img)
            img = base
    return save(img, out_dir, name)


# ---------- 示例 GEN 配置（按项目实际 CSS 设计稿修改后执行） ----------
def main():
    if len(sys.argv) < 2:
        print("用法: python gen_res.py <项目根目录>")
        sys.exit(1)
    out = os.path.join(sys.argv[1], "resources", "images")

    print("[panels]")
    to_9patch(rounded_rect(984, 52, 12, (0x12, 0x1A, 0x29, 255), (0x23, 0x34, 0x4D, 255)),
              12, out, "header.9.png")

    print("[buttons]")
    gen_btn9(out, "btn_primary", 218, 72, 10, (0x23, 0x67, 0xB8, 255))
    gen_btn9(out, "btn_danger", 218, 72, 10, (0xD3, 0x2F, 0x2F, 255))

    print("[seekbar]")
    to_9patch(rounded_rect(282, 10, 5, (0x1C, 0x2A, 0x3F, 255)), 5, out, "bar_track.9.png")
    to_9patch(rounded_rect(282, 10, 5, (0x42, 0xC9, 0xFF, 255)), 5, out, "bar_fill.9.png")

    print("[gradient]")
    gen_gradient(out, "grad_bg.png", 800, 480, (0x0E, 0x13, 0x1A, 255), (0x12, 0x1A, 0x29, 255))

    print("[dots & icons]")
    dot(out, "dot_g.png", 14, (0x00, 0xE6, 0x76, 255))
    dot(out, "dot_r.png", 14, (0xFF, 0x3D, 0x3D, 255))
    icon_circle(out, "icon_ok.png", 160, (0x00, 0xBF, 0xA5, 255), "check")
    icon_circle(out, "icon_alert.png", 160, (0xFF, 0x3D, 0x3D, 255), "alert")

    print("[loading frames]")
    frames_loading(out, "loading", 96, (0x42, 0xC9, 0xFF, 255), n=12)

    print("done ->", out)


if __name__ == '__main__':
    main()
