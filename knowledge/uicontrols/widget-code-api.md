---
id: uicontrols-widget-code-api
title: 控件代码 API 速查（35 官方 Demo 源码实证，2026-09-08）
category: uicontrols
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [Z21]
tags: [回调签名, 触发时机, 事件语义, 实测坑, 通用骨架, activity 壳, 回调表, 返回值语义, 生命周期, 定时器, 串口模板, SysApp, md, onButtonClick, setTargetAngle, setData]
evidence: []
---
# 控件代码 API 速查（35 官方 Demo 源码实证，2026-09-08）

> 检索导引：问「控件代码接口怎么调 / 回调函数签名与触发时机 / setTouchPass 在哪设 / 监听器什么时候注册 / 哪个 Demo 有用法」→ 本文（代码侧速查）；工程骨架见 `knowledge/devflow/activity-code-skeleton.md`。
> 用户口语（代码侧）："回调函数怎么写 / listview 的三个回调怎么写 / obtainListItemData 怎么写 / 列表行数据怎么填 / window 的 showWnd 怎么用 / play 接口怎么播视频"。
> 用户口语（例子与绘制）："这个控件哪个 demo 有例子·哪个示例工程有" / "图表控件怎么画·波形图怎么灌数据" / "画布怎么画圆·画圆弧·画笔怎么用" / "二维码怎么生成" / "摄像头预览怎么做"。
> 与 json 字段文档互补：本文聚焦**代码怎么驱动控件**（回调签名/触发时机/事件语义/实测坑），证据全部来自 basedemo-new_z20_1024_600 源码原文。
> 通用骨架（activity 壳/回调表/返回值语义/生命周期/定时器/串口模板/SysApp）见 `knowledge/devflow/activity-code-skeleton.md`。
> 检索词：onButtonClick/onProgressChanged/onEditTextChanged/onListItemClick/setTargetAngle/setData/loadQRCode/play/setCheckedID/showWnd。

## ZKBase 通用（所有控件）
- 触摸开关 / 穿透：`setTouchable(bool)` + **`setTouchPass(true)`**（ZKBase：本控件不响应触摸时把事件放行给下层控件）。
  ⚠️ `touchPass` **没有 json 字段**，只能代码设；压在可触摸控件上的装饰件（渐隐遮罩/高亮色带/徽标/半透明蒙层）必须
  `setTouchable(false)+setTouchPass(true)`，否则下层列表拖不动、点行无回调（V85X + EasyUI 2.9.0 实测，见 `knowledge/uicontrols/touch-events.md` §1）。
- 监听器注册：`setTouchListener`(ITouchListener) / `setLongClickListener`(ILongClickListener)——onUI_init 注册、onUI_quit 置 NULL。

## ZKButton（ButtonDemo）
- 单击：`bool onButtonClick_Caption(ZKButton*)`（生成回调表分发；**true=吞事件 false=走系统默认**，模板注释写反）
- 长按：`ZKBase::ILongClickListener::onLongClick(ZKBase*)` + `setLongClickListener(&obj)`（onUI_init 注册/onUI_quit 置 NULL；static 长生命对象；时间由 json longClickTimeOut/longClickIntervalTime 配，见 button-fields.md）
- 按下/抬起：`ZKBase::ITouchListener::onTouchEvent(ZKBase*, const MotionEvent&)`，switch ev.mActionStatus（E_ACTION_DOWN/UP/MOVE）+ `setTouchListener`（Z6S/A33NOR 平台被宏排除）
- 选中态切换：`pButton->setSelected(!pButton->isSelected())` + `isSelected()` 查询——驱动 picTab 多态图/开关（两态开关图放 pic0/pic2）；状态存在控件上，业务回调里不必另存标志

## ZKTextView / ZKEditText（TextViewDemo / EditTextDemo / DateDemo）
- `setText` 多重重载：int/char/const char*/std::string——显示数字传 int 别传 char 0（会走 char 分支）；文字只认 **utf-8**
- 动态属性：`setTextColor(int)`、`setBackgroundPic("animation/loading_%d.png")`（**逐帧换 png 即动画**，50ms 定时器驱动 60 帧）；json 里 roll/bold/italic 静态配
- `\n` 多行 setText 直接支持
- EditText 输入监听：`setTextChangeListener(this)`（Activity 实现 ITextChangeListener），回调 `void onTextChanged(ZKTextView*, const std::string&)` → 表分发到 `void onEditTextChanged_Caption(const std::string&)`（**每敲一键触发一次**，勿放重量级逻辑）
- 回填：`mEditPtr->setText(str)`（可串口注入）；密码模式切换：`setPassword(bool)`（与 IME isPassword 联动）；取内容 `getText().c_str()`

## ZKDigitalClock（DigitalClockDemo）
- **零代码自走时**：json format/beat/clockColor 即全部；无 setText
- 校时：`TimeHelper::getDateTime()` 取 struct tm* → 改字段 → `TimeHelper::setDateTime(t)`（RTC 变，所有钟自动刷新）；tm_year±1900、tm_mon±1、tm_wday 0=周日查表

## ZKWindow（WindowDemo）
- 显隐：`showWnd()/hideWnd()/isWndShow()`（无视 json 初始 visible=false 弹出）+ `setVisible(true/false)`（普通控件式）
- 交互语义由 json 决定：modal=true+hideTimeOut=N → 阻塞底层+自动/点外消失；modal=false+hideTimeOut=-1 → 常驻需主动 hideWnd
- 弹窗轻提示组合：showWnd + hideTimeOut 2~3s 自动关（WindowPasswordError/SlideWindow 提示窗同款）

## ZKListView（listViewDemo）
- 三回调：`int getListItemCount_Caption(const ZKListView*)`（可顺带做空态提示）/ `void obtainListItemData_Caption(ZKListView*, ZKListView::ZKListItem*, int index)`（**每行复用模板全量覆盖**：setText + findSubItemByID 取子项 setBackgroundPic/setSelected）/ `void onListItemClick_Caption(ZKListView*, int index, int id)`（**id=被点子控件 ID**，switch ID_MAIN_SubXxx 区分；非子项=点主区）
- 子项：`pListItem->findSubItemByID(ID_MAIN_SubXxx)` 返回 ZKListView::ZKListSubItem*
- 数据变更后必须 `mListPtr->refreshListView()`（⚠️ Demo 删除分支漏调，是坑）；数据源 vector 全局 + num 同步
- 下拉选择框套路：按钮 `isWndShow()?hideWnd():showWnd()` 弹小窗 + 小 ListView 选完 `setText` + hideWnd
- 资源图：`CONFIGMANAGER->getResFilePath("pic/x.jpg")` 后 setBackgroundPic（按 index 换行背景图示例）

## ZKPageWindow / ZKScrollWindow（PageWindowDemo / ScrollWindowDemo）
- 翻页监听：`setPageChangeListener(&l)`（ZKPageWindow::IPageChangeListener::onPageChange(pWin, page)，页 0 起，手势/按钮共用）
- 翻页：`turnToNextPage(true)/turnToPrevPage(true)`（true=动画）；⚠️ Demo 按钮与函数映射是反的（NextPage 绑 turnToPrevPage），照抄会反向
- 页 = 与容器等大的 window 子节点叠放；ScrollWindow 内容 window 可大于视口整体拖动，**本 demo 零代码**（纯结构用法，无 scroll API）

## ZKSlideWindow（SlideWindowDemo）
- 点击：`void onSlideItemClick_Caption(ZKSlideWindow*, int index)`（**带 pSlideWindow 参数**；旧头注释签名已过时）
- index = **跨屏全局下标**（非本屏第几个）→ 可直接 index 查文案表；内容静态配在 json items[]，代码不填充
- 图标项文案表与 json items 两处手写要同步（无 ID 绑定，纯 index 对齐）

## ZKRadioGroup / ZKCheckBox（RadioGroupDemo / CheckBoxDemo）
- 单选：`void onCheckedChanged_Caption(ZKRadioGroup*, int checkedID)`（**回调给选中项控件 ID** 非索引→switch ID_MAIN_RadioButtonX）；程序选中 `mGroupPtr->setCheckedID(ID_MAIN_RadioButtonX)`（与用户点击同回调）
- 复选：`void onCheckedChanged_Caption(ZKCheckBox*, bool isChecked)`；`setChecked(bool)`
- 坑：初始全 unchecked 时首次点击才触发回调，需默认值就在 onUI_init setCheckedID；⚠️ setChecked 触发回调→回调里无条件重发协议会回环；选中图约定 pic0 未选/pic2 选中

## ZKSeekBar（SeekBarDemo / VideoPlayer 进度条）
- 生成回调：`void onProgressChanged_Caption(ZKSeekBar*, int progress)`（拖动/ setProgress 连续触发）
- ⚠️ **拿不到拖拽起止**：Activity 分发只有 onProgressChanged。要「拖动中不抢、松手才 seek」必须换自定义监听：
  ```cpp
  class L : public ZKSeekBar::ISeekBarChangeListener {
    void onProgressChanged(ZKSeekBar*, int p) { track_ = p; }
    void onStartTrackingTouch(ZKSeekBar*) { tracking_ = true; }
    void onStopTrackingTouch(ZKSeekBar*) { tracking_ = false; if (track_>=0) { seekTo(track_*1000); track_=-1; } } };
  mSeekPtr->setSeekBarChangeListener(&l);   // 会顶掉 Activity 分发的 this！
  ```
  两套监听并存易误以为回调没执行；进度条量程动态 `setMax(总秒数)`（json max=100 只是占位）
- 亮度/音量：`BRIGHTNESSHELPER->setBrightness(progress)` / `player->setVolume(progress/10.0)`（max=10 → 0~1）

## ZKCircleBar / ZKPointer / clock（CircleBarDemo / PointerDemo / clockDemo）
- CircleBar：`setProgress(0..max)`（按进度裁剪有效图成扇形，非转图）；环自身 touchable+touchRange 但无回调 demo，别以为放上去就能拖
- Pointer 唯一 API：`setTargetAngle(度数)`（目标角非增量，按 rotateSpeed 动画转过去；animatable=true 才平滑）；rotationPoint=控件系圆心、fixedPoint=指针图系铰点，配套否则绕错圆心；startAngle 负值对表盘零位
- 时钟套路：三 ZKPointer 同址叠放仅一层挂表盘图；统一角度刻度：秒 +6°/s、分 +0.1°/s、时每 12s +0.1°；⚠️ 回绕 `if(360==x)x=0` 浮点精确比较对小数累加会漏（应 >= 减）；只 init 取一次 RTC 后自由累加会漂；换针图要回 IDE 调 startAngle/fixedPoint

## ZKDiagram（DiagramDemo）
- 子波形无指针，全经 `mDiagramPtr->setData(index, SZKPoint*, count)`（全量刷新，滚动自己前滚数组定时重发）或 `addData(index, y)`（局部刷新，x 自动按子项 step 推进；eraseSpace 仅此模式生效）
- 数据坐标系=轴范围逻辑值（0..100 刻度非像素），越界裁剪；index 对应 json infos[] 顺序

## ZKPainter（PainterDemo）
- 状态式画笔：`setLineWidth(px)/setSourceColor(0xRRGGBB)` 后画：`drawRect(x,y,w,h,r)/fillRect(x,y,w,h,r)/drawArc(cx,cy,rx,ry,start,sweep)/fillArc(同 drawArc)/drawTriangle(x0,y0,x1,y1,x2,y2)/fillTriangle(...)/drawLines(SZKPoint*,n)/drawCurve(SZKPoint*,n)`
  （真源签名：`ZKPainter.h` v85x easyui 2.9.0 —— `void erase(int x,int y,int w,int h); void drawLines(const SZKPoint*,int); void drawCurve(const SZKPoint*,int);`）
- ⛔ **没有 `drawLine(...)` 这个 API**：单条直线要 `SZKPoint p[2]={{x0,y0},{x1,y1}}; pPainter->drawLines(p,2);`；写 `drawLine(a,b,c,d)` 直接**编译不过**（早期页面的错误写法来源见 temp/_demo_canvas*.py）。
- ⛔ **`erase()` 不是无参清屏**（同上复核）：签名是 `erase(x,y,w,h)`，清整屏要 `erase(0,0,控件宽,控件高)`。无参 `erase();` 编译不过——本页旧文案「`erase` 清屏」已按真源签名改掉。
- **`drawArc` 实参口径（Z21 easyui 2.6.0 真机实测）**：按 `(cx, cy, rx, ry, start, sweep)`（圆心 + 半径）写**渲染正确**
  （按格子填色，无残影）；可复现调用点：`projects/EasyDevice-Z21/src/logic/mainLogic.cc`。
  V85X 480×800 复现：`temp/demo_proj` 画布页用 `fillRect(24,24,180,90)/drawRect(230,24,200,90,18)/fillArc(130,250,90,90,0,270)/drawArc(330,250,90,90,0,360)` 出图正确（截 `temp/acc_canvas.png`）。
- **`fillRect` / `erase` 实测可用（Z21，同上调用点）**：`fillRect` 填矩形、`erase(x,y,w,h)` 清指定矩形
  （清后无残影，适合做数据刷新前的整块重画）——官方 demo 未演示，故补记。
- **z 序（2026-09-16 Z21 真机实测，静态检查发现不了）**：json 里**后定义 = z 更高**。
  painter 自带不透明底（`erase()`/铺底色），所以**叠在它上面的刻度数字/文字必须写在 painter 之后**；
  写在前面会被整块盖住（图形正常、字全不见，`check_all`/本地预览都发现不了）。案例复现：
  `projects/translate/lvgl-widgets-uiv1/gen_html.py`（c4/c5 把 painter 挪到刻度 textview 之前修好）。
- 控件相对坐标（0,0=画布左上）；⚠️ 官方 demo 只在 onUI_init 画一次、touchable=false——翻页回来不会自动重画（要做 onUI_show 重绘）；触摸手绘需自己拦 touch 换算坐标增量画

## ZKImageAnim（ImageAnimDemo）
- 纯配置即用：json playFile+loopCount(≤0 无限)；代码 API：`play(path)/stop()/pause()/resume()/setLoopCount(n)`（Demo 全未用=最小形态）；仅部分平台支持（Z20/Z21/T113/V85X…，F133 不支持）

## ZKQRCode（QRCodeDemo）
- 唯一 API：`bool loadQRCode(const char* utf8)`（每次全量重生成）；EditText 每字符触发实时刷新、串口帧驱动同款；内容限 utf-8；长文本注意容量与性能

## ZKVideoView（VideoViewDemo / VideoPlayerDemo）
- 消息监听：`setVideoPlayerMessageListener(this)`；枚举 `E_MSGTYPE_VIDEO_PLAY_STARTED/COMPLETED/ERROR`；Activity 分发表第 2 字段 loop=true=内置轮播（读 `/mnt/extsd/<ftu名>_video_list.txt` 逐行播放，ERROR 自动跳下一首，⚠️ 首播从 index1 开始是 off-by-one）
- 控制：`play(path)/pause()/resume()/stop()/seekTo(ms)/isPlaying()/setVolume(0~1)/getDuration()/getCurrentPosition()(ms)`
- 播放器联动范本：STARTED 时 `setMax(getDuration()/1000)`；1s 定时器刷 `getCurrentPosition()/1000` 到进度条（拖动中用 tracking_ 标志防抖）；Play 键 `isPlaying()?pause():resume()`+setSelected 换 play/pause 图
- 页面：onResume 起播 onPause stop（isPlaying 判断）；播放列表 read_dir("/mnt/extsd",true) 扫卡 + 后缀过滤

## ZKCameraView（CameraDemo）
- `startPreview()/stopPreview()/isPreviewing()`（返回 ECameraStatusCode）；onResume/onPause 自动起停（模板）
- 拍照异步四回调：`ZKCV::IPictureCallback{ onPictureTakenStarted(); onPictureTakenEnd(); onPictureTakenError(); const char* onPictureSavePath(); }`（纯虚必实现，**仅支持 jpg**）；`setPictureCallback(&static_obj)`（onUI_init）/ 置 NULL（onUI_quit）；End 后 `sync()` 落盘防 TF 断电丢数据

## ZKMediaPlayer（MusicDemo，纯音频非控件）
- `new ZKMediaPlayer(E_MEDIA_TYPE_AUDIO/VIDEO)`；消息枚举**无 VIDEO 前缀**：`E_MSGTYPE_PLAY_STARTED/COMPLETED/ERROR_MEDIA_ERROR/ERROR_INVALID_FILEPATH/...`；`setPlayerMessageListener(&static)`；控制同 videoview（play/pause/resume/stop/seekTo(ms)/isPlaying/setVolume/getDuration/getCurrentPosition）
- 播放器骨架：错误/播完都 next()（坏歌跳过顺序播放）；onUI_quit 三段式：`setSeekBarChangeListener(NULL); player->setPlayerMessageListener(NULL); player->stop(); delete player;`
- 音视频消息枚举是两套（ZKVideoView 带 VIDEO_ 前缀，ZKMediaPlayer 不带），别混

## MountMonitor / Thread / 网络 Manager（MountDemo / ThreadDemo / NetDemo）
- Mount：`MOUNTMONITOR->addMountListener(&l)`，`IMountListener::notify(what,status,msg)` status∈MOUNTED/REMOVE/UNMOUNTING…10 态；`isMounted(path)` 轮询兜底；监视线程回调直接刷 UI 是官方示例，不稳就定时器轮询
- Thread：`readyToRun()`（true 进循环）/`threadLoop()`（return true 继续 false 退出；`exitPending()` 判断退出请求）；`run("name")/requestExit()/requestExitAndWait()(阻塞)/isRunning()`；工作线程直接刷 UI 是官方写法，保守用共享变量+UI 定时器轮询
- 网络（NetDemo 四页）：`NETMANAGER->getWifiManager()/getLTE4GManager()/getSoftApManager()/getEthernetManager()` 宏；异步一律 addXxxListener（回调在 Manager 内部线程，数据拷贝加锁）→ 刷新 UI；wifi 状态机 `notifySupplicantStateChange`、扫描 `handleWifiScanResult` 后 refreshListView；信号格=charsetTab 字符表技巧 `setText(5+level)`；SoftAP 整页被 FLYTHINGS_ENABLE_HOTSPOT 宏裁剪（默认关）；以太网输入框校验用自定义 ITextChangeListener + `text==addr` 短路防 setText 回环；密码错误弹窗 hideTimeOut 自动隐。详见 NetDemo 源码与 zknet 头文件（无 socket/http 客户端示例，连接管理是 zknet 能力）

