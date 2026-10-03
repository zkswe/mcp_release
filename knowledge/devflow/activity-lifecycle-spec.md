---
id: devflow-activity-lifecycle-spec
title: 生命周期与代码接口契约（钩子/导航语义/铁律/控件 API 索引，唯一真源派生）
category: devflow
status: review
confidence: manual
verified_at: 2026-10-02
stale_days: 180
origin: derived
source: 由 lifecycle_spec.json 派生（scripts/gen_lifecycle_doc.py）；钩子集合与 templates/HelloWord_*/src/logic/mainLogic.cc **交叉核对**
needs_evidence: false
platforms: []
tags: [生命周期, onUI_init, onUI_show, onUI_hide, onUI_quit, onUI_Timer, 回调触发, 资源释放放哪, 导航矩阵, goBack, openActivity, 隐藏页定时器, 空闲超时, 按钮回调返回值, 控件 API, ZKListView 三回调]
evidence:
  - cmd: python scripts/gen_lifecycle_doc.py --check
    expect: rc=0（本页与 lifecycle_spec.json 一致，且注册表钩子 == 模板骨架钩子）
---
# FlyThings 生命周期与代码接口契约（由 lifecycle_spec.json 派生）

> ⚙️ **本页是派生物，不要手改**（由 `lifecycle_spec.json` 派生，`--check` 进闸门）。原理与实证过程见 `knowledge/devflow/activity-code-skeleton.md`，控件逐个的代码接口详解见 `knowledge/uicontrols/widget-code-api.md`。
> 检索导引（**口语问法直达**）：资源释放放 onUI_hide 还是 onUI_quit / 切页后回调还触发吗 / 隐藏页的定时器还在跑吗 / 空闲超时怎么判才准 / 操作到一半被屏保打断 / 子页待久了莫名跳屏保 / 按钮回调返回 true 还是 false / onUI_init 什么时候调用 / onUI_init 里能不能 findControlByID / goBack 会走 onUI_hide 吗 / 页面销毁要清什么 / 静态缓存跨页面怎么办 / ZKListView 有哪三个回调 / 控件有哪些 API / check_all 括号不平衡误报 → 本文。

## 1. 骨架与钩子

src/activity/<name>Activity.cpp 是壳：定义 static ZKXxx* mXXXPtr → REGISTER_ACTIVITY(<name>Activity) → #include "logic/<name>Logic.cc"（逻辑文本包含进来，logic 里可直接裸用 mXXXPtr）

**onCreate 标准序列**：

1. 逐个 findControlByID 取控件指针
2. onUI_init()（logic 实现：注册监听器 / 初始化文案 / 串口 listener）
3. EASYUICONTEXT->registerGlobalTouchListener(this)
4. registerProtocolDataUpdateListener(onProtocolDataUpdate)
5. rigesterActivityTimer()（注意官方拼写就是 rigester；拼错 = 定时器不生效）

**析构对称序列**：

1. ungisterActivityTimer()（与上面同款拼写）
2. unregisterGlobalTouchListener(this)
3. unregisterProtocolDataUpdateListener(onProtocolDataUpdate)
4. onUI_quit()（logic 实现：反注册一切 setXxxListener(NULL) / removeListener）
5. 控件指针置 NULL

**定时器表 `REGISTER_ACTIVITY_TIMER_TAB`**：`static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = { {id, intervalMs}, ... };`

- 必须：**每个 logic.cc 必须包含**（不用定时器也保留空表）——这是 check_all 的检查项
- ⚠️ 类型名是 S_ACTIVITY_TIMEER（官方拼写如此），写 ACTIVITY_TIMER 会编译不过

| 钩子 | 签名 | 何时触发 | 必须做什么 | ⚠️ 坑 |
|---|---|---|---|---|
| `onUI_init` | `static void onUI_init()` | onCreate 内、控件指针已就绪后一次 | 注册监听器 / 初始化文案 / setCheckedID 默认值；**所有控件指针此时已由 IDE 初始化完毕，直接用，不要再 findControlByID** | 禁止在 logic 里定义 ID_MAIN_* 宏 / static ZKxxx* 指针 / new 控件（都由 IDE 生成在 activity 侧） |
| `onUI_intent` | `static void onUI_intent(const Intent *intentPtr)` | 被 openActivity 带参数拉起时 | 从 intentPtr 取参数；intentPtr 可能为 NULL（直接进入页面时） | 不判空会崩（模板里就带 if (intentPtr != NULL) 判空） |
| `onUI_show` | `static void onUI_show()` | 页面可见（≈ onResume）：首次进入、被覆盖页关闭回来、hide 后恢复 | 置可见标志（如 sVisible=true）、起播/恢复、**需要重绘的（painter 等）在这里重画**（首次绘制在 onUI_init 只画一次，翻页回来不会自动重画） | 与 onUI_hide 配对出现，但是**不是**每次都配对（goBack 销毁不经 hide） |
| `onUI_hide` | `static void onUI_hide()` | 被**覆盖**（openActivity 压栈）时；≈ onPause | 只做「被覆盖」的暂停/让位（暂停播放、置可见标志 false） | **禁止在 hide 做一次性资源释放**：goBack/closeActivity 销毁**不经 hide**（放了永不执行 → 播放器/VO/摄像头资源残留，典型事故「播放页残留 VO dev0」），且 hide 后还会 show 回来，释放了没法恢复 |
| `onUI_quit` | `static void onUI_quit()` | 页面销毁：goBack / closeActivity / goHome | **释放媒体与硬件资源**（播放器/摄像头/VO/监听）+ 反注册一切 setXxxListener(NULL) / removeListener + 清页面级 static 缓存 | 漏反注册 → 悬垂指针（监听器是静态长生命周期对象）；缓存不清 → 「切一下才显示」（缓存活了、控件没活） |
| `onProtocolDataUpdate` | `static void onProtocolDataUpdate(const SProtocolData &data)` | 串口协议帧解析完成后（registerProtocolDataUpdateListener 的消费者） | 按 data 更新 UI/业务；耗时逻辑别直接放（串口线程上下文） | 只在构造函数注册、析构反注册 → 漏了会跨页面收到别的页面的数据 |
| `onUI_Timer` | `static bool onUI_Timer(int id)` | REGISTER_ACTIVITY_TIMER_TAB 里登记的每个 id、按 interval 周期触发 | return true=保留定时器、false=注销该定时器；心跳 tick 计数（sIdleTicks++）也放这里 | **定时器与页面可见性无关**：onUI_hide 后照跑（Activity 对象还在）→ 判「空闲超时」必须加可见性门控（sVisible && ticks>=阈值），否则子页待久了被父页逻辑拽回 |
| `onmainActivityTouchEvent` | `static bool onmainActivityTouchEvent(const MotionEvent &ev)` | 全局触摸（registerGlobalTouchListener）分发给本页时；函数名 = on<activityName>TouchEvent | E_ACTION_DOWN 与 E_ACTION_MOVE 都算「有活动」（拖动时不至于被误判空闲）；按需把活动计数值归零 | 函数名要跟 activity 名一致（mainActivity → onmainActivityTouchEvent），改名要同步 |

## 2. 导航 × 回调触发矩阵（释放逻辑放哪？）

| 导航事件 | 触发的回调 | 说明 |
|---|---|---|
| goBack() / 返回键销毁当前页 | `onUI_quit` | ⚠️ 只走 quit，**不经 hide**（多工程日志实证）→ 释放放 hide = 永不执行 |
| openActivity() 新页覆盖当前页 | `onUI_hide` | hide 后页面还在，之后会再 onUI_show 回来；不是销毁 |
| 覆盖页关闭回到本页 | `onUI_show` | 与 hide 配对 |
| closeActivity() / goHome() 销毁 | `onUI_quit` | 按销毁处理（同 goBack） |

## 3. 铁律

- **R1** 媒体/硬件资源（播放器/摄像头/VO/监听）的释放一律放 onUI_quit；onUI_hide 只做「被覆盖」场景的暂停/让位
  - 为什么：goBack 销毁不经 hide（放了=永不执行 → 资源残留）；hide 后还会 show 回来，释放了没法恢复
  - 实证：多工程日志实证；典型事故「播放页残留 VO dev0 → 回预览 0xa00f8042」
- **R2** 按钮回调返回值：true=吞事件（onClick 直接结束、不再走默认），false=放行（继续走默认处理）
  - 为什么：ID=100 sys_back 的关闭页面行为依赖 false 放行；模板文件头注释写反了，以壳代码 Activity::onClick 的 `if (回调(pBase)) return;` 为准
  - 实证：壳代码分发实现
- **R3** 空闲/时长计时禁用墙钟，改「心跳 tick 计数」（1s 定时器 +1，活动时归零）
  - 为什么：墙钟非单调：ClockManager 校时成功会步进系统时间 → 两个墙钟读数之差要么永不推进要么瞬间超时（用户表述「操作到一半被屏保打断」）
  - 实证：activity-code-skeleton.md §3-3
- **R4** 判空闲必须加可见性门控：static bool sVisible（默认 false）、onUI_show 置 true、hide/quit 置 false，写法 `if (sVisible && sIdleTicks >= IDLE_ENTER_SEC)`
  - 为什么：隐藏页的定时器照跑，tick 数与「被看到且空闲」无关 → 不加门控会误伤子页（「子页待久了莫名跳屏保/被拽回主页」）
  - 实证：activity-code-skeleton.md §3-2
- **R5** static 缓存的生命周期必须与页面实例对齐：onUI_quit 里清掉页面级缓存
  - 为什么：缓存跨页面存活、控件是新建的 → 刷新函数见「值没变」就 return，新控件空白（「二维码经常不显示，切一下模式才出来」）
  - 实证：activity-code-skeleton.md §3-4
- **R6** onUI_quit 里必须反注册一切 setXxxListener(NULL) / removeListener（长按/触摸/拍照/播放器/网络监听）
  - 为什么：这些监听器是静态长生命周期对象 + 成对注册注销，漏了就是悬垂
  - 实证：activity-code-skeleton.md §3
- **R7** onUI_init 时所有控件指针已由 IDE/生成器初始化完毕，直接用；只有「改监听」才用 findControlByID
  - 为什么：logic 里自己 findControlByID = 多余且易错（check_all 会 WARN manual_find_control）
  - 实证：activity-code-skeleton.md §1

## 4. `check_all` 的两个字符级扫描口径（书写前先知道，免得白查）

- **#8 括号平衡**（字符级扫描）：逐字符数 ( / )，**只跳过双引号字符串**（连转义 \" 也不处理），注释与字符字面量都计入 → 注释里写孤立括号会误报 FAIL（例：`// 1) 先取指针`）
  - 做法：注释里带括号就写配对，或不写；真怀疑时排除注释重数一遍，先别改代码
- **#6 指针核对**（字符级扫描）：mXXXPtr 必须在 json caption 集合里找得到；扫描前**只剔了 `//` 行注释**（块注释 /* */ 不剔）→ 块注释里写不存在的 mFooPtr 会被当真引用报缺失
  - 做法：看到这两条 FAIL 先怀疑注释写法，而不是代码真坏了

## 5. 控件代码 API 索引

> 只列**关键方法名**（够查够用）；逐个控件的完整讲解、参数口径与实测坑见 `knowledge/uicontrols/widget-code-api.md`。

| 控件 | Demo | 关键 API | ⚠️ 坑 |
|---|---|---|---|
| `MountMonitor` | MountDemo | `MOUNTMONITOR->addMountListener(&l)`、`IMountListener::notify(what,status,msg)`、`isMounted(path)` | status 有 10 态（MOUNTED/REMOVE/UNMOUNTING…）；监视线程回调直接刷 UI 不稳 → 改定时器轮询兜底 |
| `ZKBase` | 所有控件 | `setTouchable(bool)`、`setTouchPass(true)`、`setTouchListener(ITouchListener*)`、`setLongClickListener(ILongClickListener*)` | touchPass **没有 json 字段**只能代码设；压在可触摸控件上的装饰件（遮罩/色带/徽标/半透明蒙层）必须 setTouchable(false)+setTouchPass(true)，否则下层列表拖不动、点行无回调 |
| `ZKButton` | ButtonDemo | `onButtonClick_<Caption>(ZKButton*)  [bool 返回]`、`setSelected(bool)`、`isSelected()` | 返回 true=吞事件、false=走系统默认（模板注释写反）；选中态驱动 picTab 多态图，状态存在控件上不必另存标志 |
| `ZKCameraView` | CameraDemo | `startPreview()`、`stopPreview()`、`isPreviewing()`、`setPictureCallback(IPictureCallback*)` | 拍照四回调纯虚必实现（**仅支持 jpg**）；onVideoCallbackEnd 后要 sync() 落盘防 TF 断电丢数据；onUI_init 注册 / onUI_quit 置 NULL |
| `ZKCircleBar/ZKPointer` | CircleBarDemo / PointerDemo / clockDemo | `circlebar.setProgress(0..max)`、`pointer.setTargetAngle(deg)` | circlebar 按进度裁剪有效图成扇形（非转图）；pointer 唯一 API 是 setTargetAngle（目标角非增量）；rotationPoint/fixedPoint 配套否则绕错圆心；回绕用 >= 判断（浮点精确 == 对小数累加会漏） |
| `ZKDiagram` | DiagramDemo | `setData(index, SZKPoint*, count)`、`addData(index, y)` | 全量刷新用 setData、局部前滚用 addData（eraseSpace 仅后者生效）；坐标系是轴范围逻辑值非像素 |
| `ZKDigitalClock` | DigitalClockDemo | `TimeHelper::getDateTime()`、`TimeHelper::setDateTime(t)` | **零代码自走时**（json format/beat/clockColor 即全部，无 setText）；tm_year±1900、tm_mon±1、tm_wday 0=周日 |
| `ZKImageAnim` | ImageAnimDemo | `play(path)`、`stop()`、`pause()`、`resume()`、`setLoopCount(n)` | 仅部分平台支持（Z20/Z21/T113/V85X；**F133 不支持**） |
| `ZKListView` | listViewDemo | `getListItemCount_<Caption>(const ZKListView*)  [int]`、`obtainListItemData_<Caption>(ZKListView*, ZKListItem*, int)`、`onListItemClick_<Caption>(ZKListView*, int index, int id)`、`findSubItemByID(ID_MAIN_SubXxx)`、`refreshListView()` | 三回调是一组，缺一列表就是空白；obtainListItemData **每行复用模板必须全量覆盖**；onListItemClick 的 id 是**被点子控件 ID**（非子项=点主区）；数据变更后必须 refreshListView（Demo 删除分支漏调是坑）；行内禁耗时代码 |
| `ZKMediaPlayer` | MusicDemo（纯音频非控件） | `new ZKMediaPlayer(E_MEDIA_TYPE_AUDIO|VIDEO)`、`setPlayerMessageListener(&l)`、`play/pause/resume/stop/seekTo/isPlaying/setVolume/getDuration/getCurrentPosition` | 消息枚举**不带** VIDEO_ 前缀（与 ZKVideoView 是两套，别混）；onUI_quit 三段式：setSeekBarChangeListener(NULL) → setPlayerMessageListener(NULL) → stop() → delete |
| `ZKPageWindow/ZKScrollWindow` | PageWindowDemo / ScrollWindowDemo | `setPageChangeListener(IPageChangeListener*)`、`turnToNextPage(true)`、`turnToPrevPage(true)` | ⚠️ Demo 按钮与函数映射是反的（NextPage 绑了 turnToPrevPage），照抄会反向；ScrollWindow 纯结构用法、无 scroll API |
| `ZKPainter` | PainterDemo | `setLineWidth(px)`、`setSourceColor(0xRRGGBB)`、`drawRect(x,y,w,h,r)`、`drawArc(cx,cy,rx,ry,start,sweep)`、`fillArc`、`fillRect`、`erase()`、`drawLines(SZKPoint*,n)`、`drawCurve(SZKPoint*,n)` | drawArc 按 (cx,cy,rx,ry,start,sweep) 写渲染正确（Z21 真机实测）；**json 里后定义 = z 更高** → 叠在 painter 上的刻度文字必须写在 painter **之后**；只在 onUI_init 画一次不会自动重画（要 onUI_show 重绘） |
| `ZKQRCode` | QRCodeDemo | `loadQRCode(const char* utf8)` | 唯一 API、每次全量重生成；内容限 utf-8；长文本注意容量与性能 |
| `ZKRadioGroup/ZKCheckBox` | RadioGroupDemo / CheckBoxDemo | `onCheckedChanged_<Caption>(ZKRadioGroup*, int checkedID)`、`onCheckedChanged_<Caption>(ZKCheckBox*, bool)`、`setCheckedID(ID_MAIN_X)`、`setChecked(bool)` | radio 回调给的是**选中项控件 ID** 非索引；初始全 unchecked 时首次点击才触发 → 默认值要在 onUI_init setCheckedID；setChecked 也会触发回调（无条件重发协议会回环）；选中图约定 pic0 未选/pic2 选中 |
| `ZKSeekBar` | SeekBarDemo / VideoPlayer | `onProgressChanged_<Caption>(ZKSeekBar*, int)`、`setSeekBarChangeListener(ISeekBarChangeListener*)`、`setMax(int)`、`BRIGHTNESSHELPER->setBrightness(v)`、`player->setVolume(0~1)` | Activity 分发只有 onProgressChanged，**拿不到拖拽起止**；要「松手才 seek」必须换自定义监听（且会顶掉 Activity 分发的 this）；progress 量程动态（json max=100 只是占位） |
| `ZKSlideWindow` | SlideWindowDemo | `onSlideItemClick_<Caption>(ZKSlideWindow*, int index)` | **带 pSlideWindow 参数**（旧头注释的 onSlideWindowItemClick 已过时）；index 是**跨屏全局下标**；内容静态配在 json items[]，代码不填充 |
| `ZKTextView/ZKEditText` | TextViewDemo / EditTextDemo / DateDemo | `setText(int|char*|std::string)`、`setTextColor(int)`、`setBackgroundPic(path)`、`setTextChangeListener(this)`、`setPassword(bool)`、`getText().c_str()` | 显示数字传 int 别传 char 0（会走 char 分支）；文字只认 utf-8；onEditTextChanged 每敲一键触发一次，勿放重量级逻辑 |
| `ZKVideoView` | VideoViewDemo / VideoPlayerDemo | `setVideoPlayerMessageListener(this)`、`play(path)`、`pause()`、`resume()`、`stop()`、`seekTo(ms)`、`isPlaying()`、`setVolume(0~1)`、`getDuration()`、`getCurrentPosition()` | 消息枚举带 VIDEO_ 前缀（E_MSGTYPE_VIDEO_PLAY_STARTED/COMPLETED/ERROR）；轮播读 /mnt/extsd/<ftu名>_video_list.txt（⚠️ 首播从 index1 开始 off-by-one） |
| `ZKWindow` | WindowDemo | `showWnd()`、`hideWnd()`、`isWndShow()`、`setVisible(bool)` | 交互语义由 json 定（modal/hideTimeOut）；轻提示 = showWnd + hideTimeOut 2~3s 自动关 |

