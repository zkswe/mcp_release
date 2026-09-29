---
id: uicontrols-imageanim-fields
title: 🎞️ ImageAnim 动图控件 JSON 字段规范
category: uicontrols
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [F133, T113]
tags: [main, imageanim, json 实测校准]
evidence: []
---
# 🎞️ ImageAnim 动图控件 JSON 字段规范

> 检索导引：问「动图控件 / GIF·WebP 播放 / playFile 不显示 / PNG 序列做动画 / 动图与文本帧动画选型」→ 本文。
> 2026-09-02 沛哥定规 + 入库（ImageAnimDemo-New/main.json + UIlayoutDemo/imageanim.json 实测校准）。

## ⚠️ 核心铁律（沛哥 2026-09-02 定规）

1. **动图控件只支持 GIF 和 WebP 两种格式**
   - `playFile` 字段只能指向 `.gif` 或 `.webp` 文件，其他格式（png 序列/apng 等）不显示
   - 这是**硬限制**：需求是动图 → 给 GIF/WebP 文件，不要生成多张 PNG 帧图塞给动图控件

2. **动图控件 ≠ 文本帧动画（两种实现，禁止混用）**
   - **动图控件（imageanim）**：直接播放 `.gif/.webp` 文件，json 一个 `playFile` 字段搞定
   - **文本帧动画（textview）**：用 textview + `setBackgroundPic()` 代码逐帧切换多张 PNG（定时器驱动），json 里是普通 textview
   - ❌ 禁止在动图控件里用"文本帧"方式实现（生成 PNG 帧图数组/逐帧切换）；也不要为了播放 GIF 去建 textview 切图——直接建 imageanim 控件
   - 判断标准：**要播放动图文件 → imageanim；要代码控制逐帧切换图片 → textview**

3. **平台限制**：只支持 Z20、Z21、T113、T113STDCXX、T113EMMC、Z261、V85X（**F133 不支持动图控件**，F133 需要动图只能 textview 帧动画）

## JSON 字段表（实测，2 个 demo 校准）

| 字段 | 类型/取值 | 说明 |
|------|----------|------|
| `caption` | string | 控件名（ImageAnim1…） |
| `id` | int | 控件 id（html2json 从 **160000** 起；官方 demo 用 53xxx，IDE 版本不同段不同，html2json 固定 160000） |
| `loopCount` | int | 循环次数：**<=0 无限循环**；>0 播放 count 次后停止 |
| `playFile` | string | 动图文件路径，**相对 resources 目录**（如 `image/test.gif`、`logo.gif`）；只支持 .gif/.webp |
| `position` | {left,top,width,height} | 控件位置尺寸（动图按控件大小缩放显示） |

> ⚠️ 实测修正：layout-audit 之前写的 `frameInterval` **json 中不存在**（两个实测 demo json 均无此字段；html2json 虽支持 data-interval 写入但 demo 未出现，以实测为准，不用）

## html2json HTML 写法

```html
<!-- 动图控件：class 用 imageanim/anim/gif；data-src/data-play-file/data-gif 指定动图文件 -->
<div class="imageanim" data-x="120" data-y="120" data-w="96" data-h="96"
     data-src="image/test.gif" data-loop="0"></div>
```
- class：`imageanim / anim / gif` → imageanim 控件（html2json 已支持）
- `data-src` / `data-play-file` / `data-gif` / `src` → playFile（无 `/` 自动补 `image/` 前缀）
- `data-loop` → loopCount（缺省 0 = 无限循环）
- ⚠️ 动图文件必须是 .gif/.webp，路径相对 resources

## 代码操作（官方）

```c++
mImageAnim1Ptr->play("image/test.gif");  // 播放指定动图（也可以运行时换文件）
mImageAnim1Ptr->stop();                  // 停止
mImageAnim1Ptr->pause();                 // 暂停
mImageAnim1Ptr->resume();                // 恢复播放
mImageAnim1Ptr->setLoopCount(3);         // 循环次数（<=0 持续循环）
mImageAnim1Ptr->getImageWidth();         // 动图宽
mImageAnim1Ptr->getImageHeight();        // 动图高
```

## 常见坑

- **动图不显示** → ①格式不是 gif/webp ②playFile 路径不对（要相对 resources）③平台不支持（F133）
- **只播一次就停** → loopCount 设了 >0；要循环设 <=0（如 0）
- **需求是动图却建了 textview 切 PNG** → 实现方式错了，改 imageanim 控件 + playFile
- **动图尺寸不对** → 控件 position 宽高决定显示大小，动图会缩放适配
