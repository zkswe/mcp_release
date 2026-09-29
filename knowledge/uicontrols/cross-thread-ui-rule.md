---
id: uicontrols-cross-thread-ui-rule
title: 跨线程操作 UI 规则（沛哥 2026-09-07 确认）
category: uicontrols
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: []
evidence: []
---
# 跨线程操作 UI 规则（沛哥 2026-09-07 确认）

> 检索导引：问「子线程能不能直接 setText / 工作线程刷 UI 要不要 post·handler / 跨线程操作控件安全吗 / UI 回调里 sleep 等资源释放行不行」→ 本文。

## 铁律
**所有控件都支持跨线程操作**：子线程/工作线程里可直接调用 setText/setVisible/setProgress/setBackgroundPic 等任意控件接口，FlyThings UI 框架内部会处理线程同步动作，**无需 handler/post 包装**（ThreadDemo-New 实测：MyThread::threadLoop 里直接 mTextView2Ptr->setText）。

## 适用说明
- 新工程（fun，原 fuse）同规则：任意线程可直接操作任意控件
- 常见做法：Thread 子类 threadLoop 里循环 setText 刷 UI（计数/倒计时/波形指针）；或 std::thread 里直接刷新
- 与定时器 onUI_Timer 的关系：两者都行，按场景选——固定频率 UI 刷新用定时器表更省事；长任务+UI 反馈用线程

## 边界注意
- 仍要避免 obtainListItemData_XXX 这类高频回调里做耗时代码（那是每行滚动都会调，线程无关，纯性能问题）
- 跨线程大批量 setText 频繁调用会加重 UI 线程负担，必要时节流（如 20ms 间隔）

## 异步资源释放反模式（禁止 UI 回调 sleep 等资源释放）

**反模式**：UI 回调/页面切换路径（onUI_quit/onUI_hide/onUI_Timer/按钮回调）里用**固定 sleep 等媒体/硬件资源异步释放**——典型如播放器 stop 后 `usleep(600~800ms)` 等 VO/解码器让位。若资源**根本不释放**（如播放器占用 VO dev 直到进程级泄漏），sleep 多久都白等，且掩盖真问题、把排查方向带偏到"时序"（浪费数小时调 sleep 时长）。

**铁律**：UI 回调禁止用固定 sleep 等资源释放（卡 UI 线程 + 时序脆弱）；先确认"资源到底会不会释放、由谁释放"，再选处理方式。

**异步资源释放三选一**（按优先级）：
1. **官方回调/轮询确认**：等官方完成信号（播放器 stop 完成回调、线程退出标志），或轮询探测资源可用（如 VO enable 试探成功才继续，失败带重试）
2. **raw 层强制回收**：不依赖异步释放，直接 raw API 强制回收并拿返回码（如 `AW_MPI_VO_Disable(0)` 强占 VO，见 `v85x/display-layer-debug.md` §4）
3. **接受重建**：确认资源确实不再需要 → 允许重建通路（重启预览/重开页面），而不是空等它释放

**实例**（播放页退出 → 预览页 VO 冲突 0xa00f8042）：错误做法 = quit 里 sleep 600-800ms 等 VO 让位（不释放就永远失败）；正确做法 = ② raw `AW_MPI_VO_Disable(0)` 强制回收，或 ① 预览启动对 VO enable 失败轮询重试。

> 固定 sleep 仅在"已知释放时长上限 + 无回调可用"的少数场景做最后兑底，且要注释为什么上限成立。
