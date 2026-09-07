# 跨线程操作 UI 规则（沛哥 2026-09-07 确认）

## 铁律
**所有控件都支持跨线程操作**：子线程/工作线程里可直接调用 setText/setVisible/setProgress/setBackgroundPic 等任意控件接口，FlyThings UI 框架内部会处理线程同步动作，**无需 handler/post 包装**（ThreadDemo-New 实测：MyThread::threadLoop 里直接 mTextView2Ptr->setText）。

## 适用说明
- 新工程（fuse）同规则：任意线程可直接操作任意控件
- 常见做法：Thread 子类 threadLoop 里循环 setText 刷 UI（计数/倒计时/波形指针）；或 std::thread 里直接刷新
- 与定时器 onUI_Timer 的关系：两者都行，按场景选——固定频率 UI 刷新用定时器表更省事；长任务+UI 反馈用线程

## 边界注意
- 仍要避免 obtainListItemData_XXX 这类高频回调里做耗时代码（那是每行滚动都会调，线程无关，纯性能问题）
- 跨线程大批量 setText 频繁调用会加重 UI 线程负担，必要时节流（如 20ms 间隔）
