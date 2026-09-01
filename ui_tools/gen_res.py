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


def to_9patch(img, radius, out_dir, name):
    """普通图 → .9.png：四周扩 1px 透明边，四边黑线标记（FT-009 规则）。
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
    """圆角矩形（透明底）→ 供 to_9patch / 直接保存"""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=fill,
                        outline=border, width=border_w)
    return img


def gen_btn9(out_dir, name, w, h, radius, fill, border=None, pressed=None):
    """按钮两态 .9.png：normal + _p（pressed 边框高亮，还原 CSS :active）"""
    if border is None:
        border = fill
    if pressed is None:
        pressed = tuple(min(255, c + 60) for c in fill[:3]) + (fill[3],)
    to_9patch(rounded_rect(w, h, radius, fill, border), radius, out_dir, name + ".9.png")
    to_9patch(rounded_rect(w, h, radius, fill, pressed), radius, out_dir, name + "_p.9.png")


def gen_gradient(out_dir, name, w, h, color_from, color_to, horizontal=True, to9=False, radius=0):
    """CSS linear-gradient → PNG（可选转 .9.png 圆角九宫格）
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
        # 圆角 mask 裁剪：清掉弧线外角落（渐变是整矩形画的，必须裁）
        mask = Image.new('L', (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
        img.putalpha(mask)
    if to9:
        return to_9patch(img, radius, out_dir, name)
    return save(img, out_dir, name)


def rounded_card(out_dir, name, w, h, radius, color_from, color_to, border=None,
                 border_w=2, highlight=None, size=None):
    """圆角卡片图（渐变底 + 可选描边/高光），四角真透明。
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
    # 圆角 mask 裁剪
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    img.putalpha(mask)
    # 描边
    if border:
        ImageDraw.Draw(img).rounded_rectangle(
            [0, 0, w - 1, h - 1], radius=radius, outline=border, width=border_w)
    # 顶部高光
    if highlight:
        ImageDraw.Draw(img).rounded_rectangle(
            [highlight[0], highlight[1], w - highlight[2], highlight[3]],
            radius=max(4, radius // 2), fill=(255, 255, 255, highlight[4]))
    return save(img, out_dir, name)


def gen_gradient_stops(out_dir, name, w, h, stops, horizontal=True, radius=0, to9=False):
    """多色标线性渐变（CSS linear-gradient 自动转图用）。
    stops: [(pos_0to1, (r,g,b,a)), ...]，至少 2 个色标；
    按 pos 线性插值逐行/逐列绘制。
    ⚠️ radius>0 时用圆角 mask 裁剪四角透明（透背景叠放不露方角）。
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
        mask = Image.new('L', (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
        img.putalpha(mask)
    if to9:
        return to_9patch(img, radius, out_dir, name)
    return save(img, out_dir, name)


def gen_shadow_card(out_dir, name, w, h, radius, fill, shadow=None, border=None, border_w=1):
    """带阴影的圆角卡片（CSS box-shadow 自动转图用）。
    shadow: (offset_x, offset_y, blur, (r,g,b,a))；阴影先画（超出卡片边缘 blur 模糊），
    最后整体圆角 mask 裁剪清掉残影（阴影模糊会溢出到弧线外，必须二次裁剪）。
    返回卡片图（含阴影区域，画布尺寸 = w+2*offset+2*blur）。
    """
    if shadow:
        ox, oy, blur, sc = shadow
        pad = max(2, blur + max(abs(ox), abs(oy)))
        cw, ch = w + pad * 2, h + pad * 2
        img = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
        # 阴影圆角矩形（高斯模糊）
        sh = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle(
            [pad + ox, pad + oy, pad + ox + w - 1, pad + oy + h - 1],
            radius=radius, fill=sc)
        if blur > 0:
            sh = sh.filter(ImageFilter.GaussianBlur(blur))
        img.alpha_composite(sh)
        # 主体卡片
        body = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(body).rounded_rectangle(
            [pad, pad, pad + w - 1, pad + h - 1], radius=radius, fill=fill,
            outline=border, width=border_w)
        img.alpha_composite(body)
        # 二次圆角裁剪：清掉阴影残影
        mask = Image.new('L', (cw, ch), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [pad - blur - 1, pad - blur - 1, pad + w + blur, pad + h + blur],
            radius=radius + blur, fill=255)
        img.putalpha(mask)
        # 裁掉多余透明边（阴影下/右延伸）
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
        return save(img, out_dir, name)
    return save(rounded_rect(w, h, radius, fill, border, border_w), out_dir, name)
    """状态点（实心圆，普通 PNG）"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([0, 0, size - 1, size - 1], fill=color)
    return save(img, out_dir, name)


def icon_circle(out_dir, name, size, color, kind="check"):
    """圆形图标（外圈 + 内部符号：check/charging/wifi/alert），emoji 替代方案"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = size // 10
    d.ellipse([m, m, size - m - 1, size - m - 1], outline=color, width=max(2, m))
    cx, cy = size // 2, size // 2
    if kind == "check":
        d.line([(cx - size // 4, cy), (cx - size // 12, cy + size // 5),
                (cx + size // 3, cy - size // 4)], fill=color, width=max(3, m), joint="curve")
    elif kind == "charging":
        pts = [(cx + size // 16, cy - size // 4), (cx - size // 5, cy + size // 12),
               (cx - size // 24, cy + size // 12), (cx - size // 8, cy + size // 4),
               (cx + size // 5, cy - size // 12), (cx + size // 24, cy - size // 12)]
        d.polygon(pts, fill=color)
    elif kind == "wifi":
        for r, wdt in ((size // 3, m), (size // 5, m), (size // 8, m)):
            d.arc([cx - r, cy - r, cx + r, cy + r], start=210, end=330, fill=color, width=wdt)
        d.ellipse([cx - m, cy + size // 8, cx + m, cy + size // 8 + 2 * m], fill=color)
    elif kind == "alert":
        pts = [(cx, cy - size // 3), (cx - size // 4, cy + size // 4), (cx + size // 4, cy + size // 4)]
        d.polygon(pts, fill=color)
        d.rectangle([cx - m // 2, cy - size // 10, cx + m // 2, cy + size // 12], fill=(255, 255, 255, 255))
    return save(img, out_dir, name)


def frames_loading(out_dir, prefix, size, color, n=12, ring_r=None, width=None):
    """loading 旋转序列帧：n 张 PNG（size×size，圆环缺口旋转），配合 imageanim 动图控件
    循环次数 ≤0 无限循环。命名 <prefix>_00.png .. <prefix>_NN.png"""
    cx = cy = size // 2
    ring_r = ring_r or size // 3
    width = width or max(3, size // 16)
    paths = []
    for i in range(n):
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        start = -90 + i * (360 // n)
        end = start + 300  # 缺口 60°
        d.arc([cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
              start=start, end=end, fill=color, width=width)
        paths.append(save(img, out_dir, "%s_%02d.png" % (prefix, i)))
    return paths


def frames_loading_gif(out_dir, name, size, color, n=12, duration=80, ring_r=None, width=None):
    """loading 旋转动画 → GIF（imageanim 动图控件 play(file) 直接加载）。
    ZKImageAnim::play 播放的是 GIF/WebP 动画文件（非序列帧目录）；
    序列帧 PNG 用 Pillow save_all 打包成 GIF，循环次数 0 = 无限循环。"""
    cx = cy = size // 2
    ring_r = ring_r or size // 3
    width = width or max(3, size // 16)
    frames = []
    for i in range(n):
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        start = -90 + i * (360 // n)
        end = start + 300
        d.arc([cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
              start=start, end=end, fill=color, width=width)
        frames.append(img)
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
    """本地彩色 emoji 渲染 → 普通 PNG（无 AI 依赖，羊了个羊同款卡通风）"""
    fp = _emoji_font()
    if not fp:
        raise RuntimeError('未找到彩色 emoji 字体（seguiemj.ttf / NotoColorEmoji.ttf）')
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(fp, int(size * 0.82))
    d.text((0, 0), ch, font=f, embedded_color=True)
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    w, h = img.size
    canvas.paste(img, ((size - w) // 2, (size - h) // 2), img)
    return save(canvas, out_dir, name)


def ai_icon(out_dir, name, size, prompt):
    """OpenAI gpt-image-2 生图（透明背景 PNG）。无 key/网络失败抛异常，由调用方降级。"""
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
    img = img.resize((size, size), Image.LANCZOS)
    return save(img, out_dir, name)


# 线条/几何兜底图标：kind → 内部形状（check/charging/wifi/alert + 补充）
_LINE_KINDS = ('check', 'charging', 'wifi', 'alert', 'circle', 'square', 'star', 'heart')


def line_icon(out_dir, name, size, color, kind='check'):
    """纯线条/几何兜底（无 AI 无 emoji 字体时仍能出图）"""
    if kind in ('check', 'charging', 'wifi', 'alert'):
        return icon_circle(out_dir, name, size, color, kind)
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = size // 5
    cx = cy = size // 2
    if kind == 'circle':
        d.ellipse([m, m, size - m, size - m], outline=color, width=max(2, size // 12))
    elif kind == 'square':
        d.rounded_rectangle([m, m, size - m, size - m], radius=size // 10,
                            outline=color, width=max(2, size // 12))
    elif kind == 'star':
        import math
        pts = []
        for i in range(10):
            ang = -90 + i * 36
            rr = size // 3 if i % 2 == 0 else size // 7
            pts.append((cx + rr * math.cos(math.radians(ang)),
                        cy + rr * math.sin(math.radians(ang))))
        d.polygon(pts, outline=color, width=max(2, size // 16))
    elif kind == 'heart':
        d.ellipse([cx - size // 4, cy - size // 4, cx, cy + size // 4], outline=color, width=max(2, size // 14))
        d.ellipse([cx, cy - size // 4, cx + size // 4, cy + size // 4], outline=color, width=max(2, size // 14))
        d.line([(cx - size // 4, cy + size // 10), (cx, cy + size // 3), (cx + size // 4, cy + size // 10)],
               fill=color, width=max(2, size // 14))
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
