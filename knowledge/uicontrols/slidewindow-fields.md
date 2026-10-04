---
id: uicontrols-slidewindow-fields
title: 🎠 SlideWindow 滑动窗口 JSON 字段规范
category: uicontrols
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [UIlayoutDemo, main, 翻页滑动]
evidence: []
---
# 🎠 SlideWindow 滑动窗口 JSON 字段规范

> 检索导引：问「九宫格翻页怎么做 / 手机桌面式图标分页 / cols×rows 每页格子数 / items 跨页 index / 图标位置和布局对不上」→ 本文。
> 2026-09-01 需求方定规 + 入库（UIlayoutDemo/main.ftu + SlideWindowDemo 实测校准）。
> Android 主页式九宫格滑动：一个滑动主窗口 + 多个图标项，翻页滑动。

## ✅ 宫格翻页语义（2026-09-07 确认）
- **cols×rows = 每页格子数**：如 4×2 = 每页 8 格；items 总数 11 = 第 1 页 8 个 + 第 2 页 3 个（第二页未满）
- 像手机桌面图标一样：自动分页、滑动翻页、回调 index 是全局 items 序号（0~10，跨页连续）

## JSON 字段表

> 字段 / 类型 / 默认值 / 必填以 `ui_tools/ui_schema.json` 为准（`flythings_ui_schema(control_type=slidewindow)` 取）；
> 下表只留字段名与语义说明。

| 字段 | 说明 |
|------|------|
| `id` | **30000+**（html2json 起始 30000） |
| `caption` | 控件名（SlideWindow1…） |
| `position` | 控件位置尺寸（整个滑动窗口区域；`{left,top,width,height}`） |
| `cols` / `rows` | 每页行列数（如 4×2，控件区域按 cols×rows **平分格子**） |
| `iconSize` | **图标实际尺寸——必须按实际图片尺寸设置**，不一定等于平分格子大小！（对象 `{width,height}`） |
| `iconMaxSize` | 图标最大尺寸限制（可选；对象 `{width,height}`；注册表 slidewindow 未收录，属真缺口） |
| `padding` | **图标相对平分格子的内边距**（图标在格子内的边界留白；`{paddingTop/Bottom/Left/Right}`） |
| `iconTextPadding` | **图标配套文字（caption 文本）的 padding 位置**（文字相对图标的位置；`{top/bottom/left/right}`；注册表 slidewindow 未收录，属真缺口） |
| `iconTextAlignment` | 文字对齐（41 实测默认；注册表 slidewindow 未收录，属真缺口） |
| `fontSize` | 图标文字字号 |
| `dragMaxDis` | 最大拖动距离 = **越界拖拽上限**（overscroll，不是行程；行程 = (组数−1)×页宽，引擎自算）—— 实测 200（手感值）；手感取值规范见 `knowledge/uicontrols/scroll-drag-interaction-spec.md` |
| `edgeEffect` | 边缘效果（1 实测） |
| `orientation` | 0=水平滑动（默认）/ 1=垂直 |
| `rollSpeed` | 滚动速度（999 实测） |
| `backgroundPic` | 背景图（注册表 slidewindow 未收录，属真缺口） |
| `items[]` | 图标项数组，每项 `{picTab{pic0,pic1} 两态图, text 文字, colorTab}` |

## ⚠️ 布局铁律（2026-09-01 定规，图标位置不对的根因）

1. **iconSize 按实际图片尺寸设置，不是平分格子大小**
   - 控件区域按 cols×rows 平分出格子，但图标图片有自己的实际宽高
   - `iconSize.width/height` 必须填**图片真实像素**（如 60×60 的 png 就写 60×60），
填大了/填小了图标会拉伸变形或位置偏移
   - ❌ 常见错：以为 iconSize = 格子大小（控件宽/cols），导致图标被拉伸、位置不对
2. **同一 slidewindow 的所有图标尺寸必须一致（21:52 补充）**
   - 生成图标时保证所有 items 的图片尺寸统一（如全部 60×60），不一致会导致位置错乱
   - html2json 已加一致性检查：items 图片尺寸不一致 → warning 提示统一尺寸后重转
3. **padding = 图标相对平分格子区域的内边距**
   - 平分格子是 iconSize 的基准，padding 描述**实际图标相对于平分后格子边界的留白**
   - paddingTop/Bottom/Left/Right 控制图标在格子内距各边界的距离（图标比格子小多少/偏移多少）
4. **iconTextPadding = 图标配套文字的 padding**
   - 是 icon 配套文本（caption 文字）相对图标的位置偏移（通常 bottom=文字在图标下方间距）
   - 调整它改变文字与图标的距离，不是改图标位置
5. **坐标由 HTML 原型绝对定位确定，确认好即无需微调（21:59 纠正）**
   - json 的 position（left/top/width/height）直接来自 HTML 原型的 data-x/y/w/h，是**绝对布局**，坐标明确
   - HTML 效果确认后 → json 坐标即准确 → **不需要再微调**（也不该微调）
   - ⚠️ 若交付后还要调位置，说明**前期 HTML 效果没确认好**——正确流程：HTML 布局 → json2html/generate_ui_preview 出预览稿给用户确认 → 确认 OK 才 fui pack / 写逻辑 / 交付
   - padding/iconTextPadding 同理：在 HTML 阶段（data-pad-b/data-icon-pad-b）调好，确认后即定稿

## html2json HTML 写法

```html
<!-- 滑动窗口：cols/rows 平分格子；icon-w/h 必须写实际图片尺寸！ -->
<div class="slidewindow" data-x="0" data-y="0" data-w="800" data-h="480"
     data-cols="4" data-rows="2"
     data-icon-w="60" data-icon-h="60"     <!-- ⚠️ 实际图片尺寸，不是格子大小 -->
     data-icon-pad-b="5"                    <!-- iconTextPadding.bottom 文字与图标间距 -->
     data-pad-b="8"                         <!-- padding.paddingBottom 图标在格子内下边距 -->
     data-icon-align="41">
  <div class="item" data-pic="icon_app.png" data-pic1="icon_app_p.png">应用名</div>
  <div class="item" data-pic="icon_set.png">设置</div>
</div>
```
- class：`slidewindow / slide / launcher` → slidewindow
- 子 `div.item` → items[]（picTab 两态图 + text）
- `data-icon-w/h` → iconSize（⚠️ 写实际图片尺寸）；`data-icon-max` → iconMaxSize
- `data-pad-b` → padding.paddingBottom；`data-icon-pad-b` → iconTextPadding.bottom
- `data-icon-align` → iconTextAlignment；`data-roll-speed` → rollSpeed

## 代码操作（官方）

```c++
mSlideWindow1Ptr->turnToNextPage(true/false);   // 下一页（带/无动画）
mSlideWindow1Ptr->turnToPrevPage(true/false);   // 上一页
mSlideWindow1Ptr->getCurrentPage();             // 当前页码
// 翻页监听：setSlidePageChangeListener(&listener)，onSlidePageChange(pWin, page)
```

## 常见坑

- **图标位置不对/拉伸**→ iconSize 没按实际图片尺寸填（最常见，见布局铁律 1）
- 图标挤在格子一角 → padding 各边没配好（padding 是图标相对格子边界的留白）
- 文字叠在图标上/离太远 → 调 iconTextPadding（文字 padding），不是调 padding
- 图片尺寸与 iconSize 不一致 → 设备上拉伸变形；生成图片时按 iconSize 出图
