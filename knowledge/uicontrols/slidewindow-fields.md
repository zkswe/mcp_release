# 🎠 SlideWindow 滑动窗口 JSON 字段规范

> 2026-09-01 沛哥定规 + 入库（UIlayoutDemo/main.ftu + SlideWindowDemo 实测校准）。
> Android 主页式九宫格滑动：一个滑动主窗口 + 多个图标项，翻页滑动。

## JSON 字段表

| 字段 | 类型/取值 | 说明 |
|------|----------|------|
| `id` | int | **30000+**（html2json 起始 30000） |
| `caption` | string | 控件名（SlideWindow1…） |
| `position` | {left,top,width,height} | 控件位置尺寸（整个滑动窗口区域） |
| `cols` / `rows` | int | 每页行列数（如 4×2，控件区域按 cols×rows **平分格子**） |
| `iconSize` | {width,height} | **图标实际尺寸——必须按实际图片尺寸设置**，不一定等于平分格子大小！ |
| `iconMaxSize` | {width,height} | 图标最大尺寸限制（可选） |
| `padding` | {paddingTop/Bottom/Left/Right} | **图标相对平分格子的内边距**（图标在格子内的边界留白） |
| `iconTextPadding` | {top/bottom/left/right} | **图标配套文字（caption 文本）的 padding 位置**（文字相对图标的位置） |
| `iconTextAlignment` | int | 文字对齐（41 实测默认） |
| `fontSize` | int | 图标文字字号 |
| `dragMaxDis` | int | 最大拖动距离（200 实测） |
| `edgeEffect` | int | 边缘效果（1 实测） |
| `orientation` | int | 0=水平滑动（默认）/ 1=垂直 |
| `rollSpeed` | int | 滚动速度（999 实测） |
| `backgroundPic` | string | 背景图 |
| `items[]` | array | 图标项数组，每项 `{picTab{pic0,pic1} 两态图, text 文字, colorTab}` |

## ⚠️ 布局铁律（沛哥 2026-09-01 定规，图标位置不对的根因）

1. **iconSize 按实际图片尺寸设置，不是平分格子大小**
   - 控件区域按 cols×rows 平分出格子，但图标图片有自己的实际宽高
   - `iconSize.width/height` 必须填**图片真实像素**（如 60×60 的 png 就写 60×60），
     填大了/填小了图标会拉伸变形或位置偏移
   - ❌ 常见错：以为 iconSize = 格子大小（控件宽/cols），导致图标被拉伸、位置不对
2. **同一 slidewindow 的所有图标尺寸必须一致（沛哥 21:52 补充）**
   - 生成图标时保证所有 items 的图片尺寸统一（如全部 60×60），不一致会导致位置错乱
   - html2json 已加一致性检查：items 图片尺寸不一致 → warning 提示统一尺寸后重转
3. **padding = 图标相对平分格子区域的内边距**
   - 平分格子是 iconSize 的基准，padding 描述**实际图标相对于平分后格子边界的留白**
   - paddingTop/Bottom/Left/Right 控制图标在格子内距各边界的距离（图标比格子小多少/偏移多少）
4. **iconTextPadding = 图标配套文字的 padding**
   - 是 icon 配套文本（caption 文字）相对图标的位置偏移（通常 bottom=文字在图标下方间距）
   - 调整它改变文字与图标的距离，不是改图标位置
5. **坐标由 HTML 原型绝对定位确定，确认好即无需微调（沛哥 21:59 纠正）**
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

- **图标位置不对/拉伸** → iconSize 没按实际图片尺寸填（最常见，见布局铁律 1）
- 图标挤在格子一角 → padding 各边没配好（padding 是图标相对格子边界的留白）
- 文字叠在图标上/离太远 → 调 iconTextPadding（文字 padding），不是调 padding
- 图片尺寸与 iconSize 不一致 → 设备上拉伸变形；生成图片时按 iconSize 出图
