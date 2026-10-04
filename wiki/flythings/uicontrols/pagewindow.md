---
title: 翻页窗口
---

## 如何使用

- 首先在UI文件中创建一个 翻页窗口 控件，然后再添加多个 窗口 控件到 翻页窗口控件中，注意此时添加到翻页窗口中的窗口大小会自动调整到与翻页窗口大小相同，不可自定义，因此在添加窗口时，为了方便后续在窗口中添加一些其他控件，注意添加窗口时选择窗口控件后再选中翻页窗口然后单击即可，这样就可以自动调整大小和位置。
- 在 窗口 中，可以添加其他控件并自定义大小和位置。

## 代码操作

- 一般情况下，我们只需要通过触摸滑动来上下翻页。但是，我们也提供了相应的翻页函数。

- 切换下一页

```c++
// 切换到下一页，有动画
mPageWindow1Ptr->turnToNextPage(true);
// 切换到下一页，无动画
mPageWindow1Ptr->turnToNextPage(false);
```

- 切换上一页

```c++
// 切换到上一页，有动画
mPageWindow1Ptr->turnToPrevPage(true);
// 切换到上一页，无动画
mPageWindow1Ptr->turnToPrevPage(false);
```

- 我们还可以通过代码监听到滑动窗口翻到了第几页：

```c++
namespace { // 加个匿名作用域，防止多个源文件定义相同类名，运行时冲突
 // 实现自己的监听接口
 class MyPageChangeListener : public ZKPageWindow::IPageChangeListener {
 public:
 virtual void onPageChange(ZKPageWindow *pPageWindow, int page) {
 LOGD("当前切换到第%d页", page);
 }
 };
 }
 // 定义监听对象
 static MyPageChangeListener sMyPageChangeListener;

 static void onUI_init() {
 mPageWindow1Ptr->setPageChangeListener(&sMyPageChangeListener);
 }
```

- 获取当前是哪一页

```c++
int i = mPageWindow1Ptr->getCurrentPage();
LOGD("当前是第%d页", i);
```

## 样例代码
具体翻页窗口控件的使用，参考[样例代码](./demo_download.html#demo_download)中的PageWindowDemo项目。
