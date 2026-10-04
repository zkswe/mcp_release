---
title: 滑动窗口
---

滑动窗口控件与手机主界面九宫格左右滑动的界面效果类似。由一个滑动主窗口和多个图标组成。

## 如何使用

- 首先在UI文件中创建一个 滑动主窗口 控件，然后再添加多个 滑动窗口图标 控件到 主窗口控件中。
- 添加 滑动窗口图标 控件时，它会自动按顺序排列图标，如果添加满一页后，继续添加也会自动翻页。所有添加的图标控件都可以在 大纲视图 中找到。如果想调整 滑动窗口图标 排列的位置，你可以在大纲视图中选中节点,然后直接通过拖拽来调整。
- 在 大纲视图 中，选中 滑动窗口图标 控件，可以分别添加图片以及修改文字；选中整个 滑动主窗口 可以调整排列的 行数 和 列数， 还可以统一调整字体大小、图标大小。

## 代码操作

- 如果你添加了滑动窗口控件，那么在编译后，会自动生成关联函数， 函数具体介绍参考[滑动窗口关联函数](./relation_function.html#slidewindow)
- 一般情况下，我们只需要通过触摸滑动来上下翻页。但是，我们也提供了相应的翻页函数。

- 切换下一页

```c++
// 切换到下一页，有动画
mSlideWindow1Ptr->turnToNextPage(true);
// 切换到下一页，无动画
mSlideWindow1Ptr->turnToNextPage(false);
```

- 切换上一页

```c++
// 切换到上一页，有动画
mSlideWindow1Ptr->turnToPrevPage(true);
// 切换到上一页，无动画
mSlideWindow1Ptr->turnToPrevPage(false);
```

- 我们还可以通过代码监听到滑动窗口翻到了第几页：

```c++
namespace { // 加个匿名作用域，防止多个源文件定义相同类名，运行时冲突
 // 实现自己的监听接口
 class MySlidePageChangeListener : public ZKSlideWindow::ISlidePageChangeListener {
 public:
 virtual void onSlidePageChange(ZKSlideWindow *pSlideWindow, int page) {
 LOGD("当前切换到第%d页", page);
 }
 };
 }
 // 定义监听对象
 static MySlidePageChangeListener sMySlidePageChangeListener;

 static void onUI_init() {
 mSlidewindow1Ptr->setSlidePageChangeListener(&sMySlidePageChangeListener);
 }
```

- 获取当前是哪一页

```c++
int i = mSlideWindow1Ptr->getCurrentPage();
LOGD("当前是第%d页", i);
```

## 样例代码
具体滑动窗口控件的使用，参考[样例代码](./demo_download.html#demo_download)中的SlideWindowDemo项目。
