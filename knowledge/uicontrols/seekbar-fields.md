---
id: uicontrols-seekbar-fields
title: seekbar（滑块/进度条）字段与「滑块形状」口径
category: uicontrols
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [需要什么关键词才能生成圆滑块, 只由, 图片 + 控件盒子高度, 两件事决定, 滑块, 进度条, seekbar, SeekBar, slider, thumb]
evidence: []
---
# seekbar（滑块/进度条）字段与「滑块形状」口径

> 检索导引：问「进度条滑块为什么是扁的 / 圆滑块怎么做 / thumb.size 和盒子高度关系 / 轨道图·有效图配错 / 播放进度条与音量条」→ 本文（滑块形状无字段可调）。
> 2026-09-22 钟工报障「音乐播放页进度条的滑块为什么做成这样扁的？什么关键词影响了你生成 / 需要什么关键词才能生成圆滑块」
> → 真机定位后入库。**滑块形状没有 json 字段可调，只由「图片 + 控件盒子高度」两件事决定。**
> 检索词：滑块 / 进度条 / seekbar / SeekBar / slider / thumb / 滑块图 / 圆滑块 / 圆形滑块 /
> 滑块扁的 / 滑块被压扁 / 滑块变成椭圆 / 滑块高度 / 滑块尺寸 / thumb.size / thumbPic /
> backgroundPic / progressPic / data-thumb / data-thumb-size / 轨道图 / 有效图 / 滑块常显图 /
> 播放进度条 / 音量条 / onProgressChanged / setProgress / getProgress / max / defProgress / orientation。

## 0. 一句话口径

**滑块（thumb）的形状 = 滑块图本身的形状 × 控件盒子高度**：

- 形状**只由图片决定** —— json/html 里**没有任何「圆形/胶囊」关键词**；
- 但**渲染高度会被控件盒子压**：`thumb.size` 写 24×24、控件 `position.height` 只有 12 → 屏幕上渲染成 **24×12（扁椭圆）**。
- ⇒ **要圆滑块**：① 出一张**正圆**图（正方形画布 + 半径=边长/2）② **控件 `position.height` ≥ `thumb.size.height`**
  ③ `thumb.size` 与图**同尺寸正方形**。本次修法：控件 12 → **28 高**、轨道图也做成 28 高（可见圆条 12px 居中、上下透明），thumb 24×24 正圆。

## 1. 字段全集（json，实测自 `SampleUI-New` 基准 + 本项目）

| 字段 | 含义 | 备注 |
|---|---|---|
| `position` | 控件盒（left/top/width/height） | **height 决定滑块能被渲染多高**（见 §2） |
| `max` | 最大值 | 进度 = progress/max |
| `defProgress` | 默认进度 | |
| `orientation` | 0 = 横向 | |
| `backgroundPic` | 轨道底图（"背景图"） | 高度按控件盒（本工程 28，可见条 12 居中） |
| `progressPic` | 进度图（"有效图"） | 引擎按进度横向裁剪 |
| `thumb.size` | **滑块自有尺寸子盒**（不是控件盒） | 必须与滑块图同尺寸；正方形才可能出圆 |
| `thumb.normalPic` / `thumb.pressedPic` | 滑块常显图 / 按下图 | |
| `touchable` | 交互控件 → `true`（铁律 #5） | |

回调与代码：`onProgressChanged_XXXX(ZKSeekBar*, int progress)`、`setProgress(int)`、`getProgress()`（官方 `uicontrols/seekbar.md`）。

## 2. ⚠️ 实测铁律：滑块会被**控件盒高度**压扁（官方文档未收录）

真机实测（iOSStyle-F133 播放页，1280×800）：

| 配置 | 屏幕上滑块实测 | 结果 |
|---|---|---|
| 图 24×24 正圆 + 滑块图无 AA、控件 `height=12` | **24 × 12**（宽保留、高度被压到控件高） | ❌ 扁椭圆（用户看到的就是这个） |
| 24×24 正圆图 + 控件 `height=28`（轨道图 28 高、可见条 12 居中） | **24 × 24**（逐行 4/16/20/22/24/22/20/14 = 标准圆） | ✅ 正圆 |

⇒ **只改图不改控件盒没用**（这次就先踩了：把 `flat_rounded` 换成正圆图，屏幕上照样扁）；
**只改控件盒不改图也没用**（方块还是方块）。两件事必须一起做。

## 3. 出图口径（要什么形状，就出什么图）

- **正圆**：`gen_res.rounded_rect_cov(w, h, radius=w/2, color)` —— 半径取边长一半即正圆，
  覆盖率口径（SS≥4 + `Image.BOX` 面积平均）→ 边缘 12 级灰度、`aa_audit` PASS。
- **胶囊/椭圆**：`rounded_rect_cov(w, h, radius=h/2…)`（细长条两端半圆）。
- ❌ **别用"flat_rounded"-类无抗锯齿画法**：本次原始滑块图 alpha 只有 0/255（零过渡）→ 边缘硬；
  圆角半径写 11（24 见方）= 圆角方块（squircle），本来就"不是圆"。
- 轨道/进度图：**高度 = 控件盒高度**，把可见圆条画在中间、上下留透明（本次 28 高 / 可见 12）。
- 出图后必跑 `check_all`（铁律 #11）：`thumb.size` 与图尺寸不符 = FAIL；`aa_audit` 过弧线判据。

## 4. HTML（原型稿）→json 的关键词

`tools/ui_tools/html2json.py:1732-1744`（SeekBar 分支，用 `SeekBarDemo` 校准）：
`data-thumb`（滑块图，缺省不生成图）、`data-thumb-pressed`（按下图）、`data-thumb-size`（**px，缺省 24**）。
→ 所以原型稿里要圆滑块，写的是**"给一张圆的滑块图 + `data-thumb-size` 与图一致"**，
并且**让该元素的盒子高度 ≥ 滑块直径**（否则照样被压扁）。

## 5. 反例（AI 常写错）

| 反面 | 后果 |
|---|---|
| 滑块图是圆角方块/无 AA，指望引擎"画成圆" | 引擎不画形状，只贴图 → 扁/硬边 |
| 控件 12 高 + `thumb.size` 24×24 | 屏幕上是 24×12 扁椭圆（§2 实测） |
| `thumb.size` 与图尺寸不一致 | 真机滑块与轨道错位（`ui-asset-rules.md` §thumb 子盒、`ui-layout-verify.md`） |
| 只想"看起来像 iOS"就把滑块做很大但不加高控件盒 | 一定被压扁 |
| 改 json 时用 `sort_keys=True` 整体重排 | **控件顺序 = 图层顺序**，会把全屏铺底层排到进度条之上 → 进度条/滑块整条看不见（本次踩过，回滚重排才恢复） |

## 6. 相关文档

- 图片/尺寸铁律（`thumb.size` 子盒口径）：`devflow/ui-asset-rules.md`
- 布局审计与红标（含 thumb 子盒）：`devflow/ui-layout-verify.md`、`uicontrols/layout-audit.md`
- 字段必写口径：`uicontrols/json-field-mandatory.md`；图层顺序：`uicontrols/json-layer-rules.md`
- 官方滑块文档（四张图 + 三个函数）：`wiki/flythings/uicontrols/seekbar.md`
