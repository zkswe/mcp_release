# 🧵 FT-009 .9.png 生成规则（必读）

> 2026-09-01 沛哥定规范。适用：一切自动生成 stretchable 圆角图片（.9.png）的代码
> 与 AI 手写生成逻辑（Pillow 绘制卡片/按钮/轨道/输入框九宫格背景）。
> 违反规则 → 设备端拉伸变形 / marker 残影 / 内容区错位。

## 五条规则（必须全部满足）

1. **marker 线颜色必须为纯黑不透明 `(0,0,0,255)`**，禁止透明 `(0,0,0,0)`（透明 marker 设备端识别不到，等同没标）
2. **top / left 黑线：只画中间拉伸段**，排除左右/上下 radius 像素的倒角区（圆角弧线内不能有黑线）
3. **right / bottom 黑线：宽度与拉伸区（stretch 区）同宽**——right 竖线范围 = left 拉伸段（y0..y1），bottom 横线范围 = top 拉伸段（x0..x1），四边 marker 语义完整（拉伸区 + 内容区）
4. **marker 线宽 = 1px，紧贴图片边缘**（top/bottom 在 y=0 / y=h+1，left/right 在 x=0 / x=w+1）
5. **marker 必须在所有绘图完成后最后绘制**，且不能被后续 alpha 操作覆盖（先画图 → 扩边 → 最后画 marker；任何 putalpha/裁剪必须发生在画 marker 之前）

## 生成流程（Pillow 示例）

```python
from PIL import Image, ImageDraw

def to_9patch(img, radius, out_dir, name):
    """普通图 → .9.png：四周扩 1px 透明边，四边黑线标记（FT-009）"""
    w, h = img.size
    out = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0))
    out.paste(img, (1, 1))          # 内容图居中，四周留 1px marker 边
    d = ImageDraw.Draw(out)
    x0, x1 = 1 + radius, w - radius  # top/bottom 拉伸段（排除倒角）
    y0, y1 = 1 + radius, h - radius  # left/right 拉伸段（排除倒角）
    black = (0, 0, 0, 255)           # 规则1：纯黑不透明
    # 规则2+4：top/left 只画中间段，1px 贴边
    if x1 > x0:
        d.line([(x0, 0), (x1, 0)], fill=black, width=1)
    else:
        d.point((1 + w // 2, 0), fill=black)
    if y1 > y0:
        d.line([(0, y0), (0, y1)], fill=black, width=1)
    else:
        d.point((0, 1 + h // 2), fill=black)
    # 规则3：right/bottom 与拉伸区同宽
    if y1 > y0:
        d.line([(w + 1, y0), (w + 1, y1)], fill=black, width=1)
    else:
        d.point((w + 1, 1 + h // 2), fill=black)
    if x1 > x0:
        d.line([(x0, h + 1), (x1, h + 1)], fill=black, width=1)
    else:
        d.point((1 + w // 2, h + 1), fill=black)
    out.save(os.path.join(out_dir, name))
    return os.path.join(out_dir, name)
```

## 验证方法

生成后检查 marker 像素（四边 1px 环）：
- `img.getpixel((x0, 0)) == (0, 0, 0, 255)`（top 起点，纯黑不透明）
- `img.getpixel((0, y0)) == (0, 0, 0, 255)`（left 起点）
- 倒角区无黑线：`img.getpixel((1, 0))` 应为透明（不落 marker）
- right/bottom 黑线范围与 top/left 一致

## 常见坑

- 只画 top/left 不画 right/bottom（旧版 gen_res.to_9patch 的 bug，v0.6.10 修复）→ 内容区标记缺失
- marker 用 `(0,0,0,0)` 或半透明 → 设备端不识别
- 扩边前画 marker → paste 内容图时被覆盖
- 圆角后 putalpha 裁剪 → marker 被 alpha 清掉（必须先裁完再画 marker）
- 9-patch 黑线画进倒角弧线内 → 圆角拉伸变形

> ⚠️ 注意：fix_tools.py 的 FT-002 规定 **ZKSeekBar 不解析 9-patch**（marker 会画成黑框），
> SeekBar 背景一律用普通 .png，禁止 .9.png；本规则适用于按钮/卡片/面板/轨道等支持 9-patch 的控件。
