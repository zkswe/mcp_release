# 📜 ScrollWindow 滚动窗口布局设计

> 2026-09-01 实测校准（ScrollWindowDemo-New / PageWindowDemo-New，basedemo-new_z20_1024_600）
> 官方文档只讲"怎么用"，这里补 json 布局设计细节。

## 1. 结构（三件套）

```
scrollwindow（可视区，固定尺寸）
  └── window（滚动内容容器，尺寸 > 可视区）
        └── 子控件（button/textview/...）
```

真实 json（ScrollWindowDemo-New/ui/main.json）：

```json
"scrollwindow__1": {
  "caption": "ScrollWindow1",
  "dragMaxDis": 200,        // 最大拖动距离（滚动行程）
  "edgeEffect": 1,          // 边界效果（0=无 / 1=回弹，demo 用 1）
  "id": 32001,
  "orientation": 0,         // 滚动方向（0=垂直 / 1=水平）
  "position": { "height": 315, "left": 175, "top": 42, "width": 450 },
  "window__2": {            // ★ 滚动内容 window 嵌套在 scrollwindow 内
    "caption": "Window1",
    "id": 110001,
    "position": { "height": 315, "left": -175, "top": 0, "width": 800 },  // 内容比可视区宽（800 > 450）
    "button__3": { ... },   // 内容里的控件
    ...
  }
}
```

## 2. 关键设计点（实测）

- **内容 window 尺寸要比滚动窗口大**：滚动窗口 450×315，内容 window 800×315，多出的 350px 就是可滚动空间
- **left/top 可为负值**：内容 window 的 left:-175 是初始偏移（内容先往左偏，往右拖能看到左侧内容）；垂直滚动时用 top 负值
- **dragMaxDis 控制行程**：最大拖拽距离（demo=200），不是简单的内容-可视差值，按实际手感调
- **orientation**：0=垂直滚动（上下滑）/ 1=水平滚动（左右滑）
- **edgeEffect**：边界效果，demo=1（回弹）
- **滚动窗口本身也是容器**：`__container` 语义，支持嵌套（scrollwindow 内嵌 window，window 内再嵌子控件/面板）

## 3. 与 PageWindow 的区别

| 控件 | 结构 | 特性 |
|------|------|------|
| ScrollWindow | 1 个 scrollwindow + 1 个大 window（连续内容） | dragMaxDis 行程 + 连续滚动 |
| PageWindow | 1 个 pagewindow + 多个**同尺寸** window 叠放 | rollSpeed 滚动速度 + `turnToNextPage()/turnToPrevPage()` 翻页 |

PageWindow 真实 json 额外字段：`rollSpeed: 30`（滚动速度），页面 = 多个 400×260 同尺寸 window 叠放。

## 4. html2json 支持（已实现）

```html
<div class="scroll" data-caption="ScrollWin1" style="left:175px;top:42px;width:450px;height:315px"
     data-drag-max="200" data-orientation="0" data-edge-effect="1">
  <div class="window" style="left:-175px;top:0px;width:800px;height:315px">
    <!-- 内容控件 -->
  </div>
</div>
```

- 类名：`scroll` / `scrollwin` / `scrollwindow`
- 属性：`data-drag-max`（dragMaxDis）、`data-orientation`（0垂直/1水平）、`data-edge-effect`（0/1）
- 内嵌 `div.window` 自动生成嵌套 window（内容容器），子控件相对 window 定位

## 5. 代码操作

```c++
ZKScrollWindow* p = (ZKScrollWindow*)findControlByID(ID_MAIN_ScrollWindow1);
```

滚动窗口继承自窗口容器，除滚动效果外其他操作与窗口容器类似（官方文档）。
ScrollWindowDemo 源码未调用具体滚动 API（只取指针），精确滚动方法以 IDE 属性/官方文档为准，不猜。
