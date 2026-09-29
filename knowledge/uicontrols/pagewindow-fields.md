---
id: uicontrols-pagewindow-fields
title: PageWindow 多页窗口控件 JSON 字段规范
category: uicontrols
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [0 SDK, 实测, 引导页, 分类页签内容区]
evidence: []
---
# PageWindow 多页窗口控件 JSON 字段规范

> 检索导引：问「多页窗口怎么做 / 左右滑动切页容器 / PageWindow 字段 / turnToNextPage 翻页 / 页变更回调 / 和 slidewindow·scrollwindow 区别」→ 本文。
> 2026-09-07 basedemo/PageWindowDemo-New + f133 easyui 2.9.0 SDK（zk_pagewindow）实测。
> 场景：同一区域多页内容左右滑动切换（引导页、分类页签内容区）。

## 核心铁律

1. **pagewindow = 多子窗口（页）容器**：子窗口并排排布，左右滑动/编程翻页切换；当前页索引回调 `onPageChange(pPageWindow, page)`（page 从 0 起）。
2. 与 slidewindow 区别：slidewindow 是"图标宫格"（item 是图标+文字）；pagewindow 是"整页窗口容器"（子页是完整 window，可放任意控件）。ScrollWindow 则是单页内容超高滚动。
3. 编程翻页：`turnToNextPage()` / `turnToPrevPage()`；监听：`setPageChangeListener(&listener)`。

## JSON 字段表（PageWindowDemo 实测）

| 字段 | 说明 |
|------|------|
| `caption`/`id` | 控件名/id（实测 30000+ 段） |
| 子 `window__N` | 每页一个子窗口（页内容），并排排布 |
| `orientation` | 0 水平翻页 / 1 垂直（如支持） |
| `dragMaxDis`/`edgeEffect`/`rollSpeed` | 滑动参数：dragMaxDis=**行程**（200 实测）、edgeEffect=1、rollSpeed=60；手感取值规范见 `scroll-drag-interaction-spec.md` |
| 其余通用 | touchable/visible/position |

## 代码操作（PageWindowDemo 实测）

```cpp
class MyListener : public ZKPageWindow::IPageChangeListener {
public:
  virtual void onPageChange(ZKPageWindow *pPageWindow, int page) {
    // page 当前页（0 起）
  }
};
static MyListener sListener;
// onUI_init 里：
mPageWindow1Ptr->setPageChangeListener(&sListener);

// 按钮翻页
mPageWindow1Ptr->turnToNextPage();
mPageWindow1Ptr->turnToPrevPage();
```

## 样例代码
PageWindowDemo-New（button 上一页/下一页 + 页码 textview 显示）。
