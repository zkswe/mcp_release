---
id: devflow-activity-code-skeleton
title: FlyThings 工程代码骨架（35 官方 Demo 深度阅读提炼）
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [35 工程, 逐源码深读, activity 骨架, 回调表, 生命周期, logic, cc, 定时器, 串口模板, SysApp, 全检误报, 隐藏页定时器, 可见性门控, 心跳 tick 计时, static 缓存, onUI_quit 清理]
evidence: [projects/SmartPanel_HA/src/logic/homeLogic.cc:49-63, projects/SmartPanel_HA/src/logic/homeLogic.cc:437-456, projects/SmartPanel_HA/src/logic/homeLogic.cc:476-480, projects/SmartPanel_HA/src/logic/settingsLogic.cc:28-37, projects/SmartPanel_HA/src/logic/settingsLogic.cc:179-207, projects/SmartPanel_HA/src/logic/mainLogic.cc:95-101, projects/SmartPanel_HA/src/logic/mainLogic.cc:976-987, projects/SmartPanel_HA/src/logic/modeLogic.cc:108-139, projects/SmartPanel_HA/src/logic/modeLogic.cc:187-195, projects/SmartPanel_HA/src/logic/albumLogic.cc:119, projects/SmartPanel_HA/src/logic/albumLogic.cc:260-263]
---
# FlyThings 工程代码骨架（35 官方 Demo 深度阅读提炼）

> 检索导引：问「activity 骨架怎么写 / 回调分发表在哪 / onUI_init·onUI_quit 标准序列 / logic.cc 与 activity.cpp 谁参与编译 / 切页后回调还触发吗 / check_all 括号平衡误报」→ 本文（工程代码骨架总纲）；控件逐个的代码接口见 `knowledge/uicontrols/widget-code-api.md`。
> **口语问法直达**：切页后显示不对 / 切一下才显示 / 二次进页就不对 / 子页待久了跳屏保 / 子页待久了被拽回主页 / 操作到一半被屏保打断 / 隐藏页的定时器还在跑吗 / 空闲超时怎么判才准 / 时间跳变导致计时错乱 → 见 §3-2~§3-4（生命周期三条硬经验，真工程实证）。
> **同义说法**：切到别的页再切回来才对 / 返回再进页面内容就不对了 / 第二次进页面显示空白 / 界面要切一下才刷新 / 屏保是谁触发的怎么关掉 → 仍看 §3-1~§3-4。
> 2026-09-08 basedemo-new_z20_1024_600（35 工程）逐源码深读。所有 Demo 共用同一套生成器骨架，理解它=理解一切控件如何被代码驱动。
> 检索词：activity 骨架/回调表/生命周期/logic.cc/定时器/串口模板/SysApp/REGISTER_ACTIVITY/check_all 括号不平衡/全检误报/隐藏页定时器/可见性门控/心跳 tick 计时/static 缓存跨页面/onUI_quit 清理清单。


## 0. ⚠️ 先看：两套编译体系（2026-09-17 纠偏）

- **IDE 体系**：`src/activity/<name>Activity.cpp` 参与编译，它 `#include` 同名 logic（`logic/<name>Logic.cc`）。
- **`fun build`（命令行，推荐）**：**`src/activity/*` 完全不参与编译**；fun 直接把 `src/logic/*.cc`、`src/**/*.cpp` 与**自己生成的** `generated/{event,event_dispatcher,ui_main}.cpp` 编成 `libzkgui.so`（编译宏 `FUN_BUILD=1`）。
- 所以：改 activity 对 fun 构建**无效**；**不要改 `.fun/<平台>/CMakeLists.txt`**（fun 自动生成、会被覆盖）。细节见 `knowledge/devflow/cli-fun-toolchain.md` §4.5。

## 1. 代码组织（生成器骨架）
- **src/activity/mainActivity.cpp 是"壳"**：顶部定义 `static ZKXxx* mXXXPtr`（控件全局指针，与 ftu 的 caption 对应）→ `REGISTER_ACTIVITY(mainActivity);` → `#include "logic/mainLogic.cc"` 把用户逻辑**文本包含**进来 → logic 里可直接裸用 mXXXPtr/mActivityPtr，无需自己 findControl（但要改监听才用 findControlByID 或直接在 onCreate 已配好）。
- 控件 ID 宏：`src/activity/*Activity.h` 里 `#define ID_MAIN_<caption> <json id>`；子项（listview subItem）宏 `ID_MAIN_SubItemXxx`。
- 类继承：Activity 多重继承各监听接口（ZKListView::AbsListAdapter、IItemClickListener、ZKRadioGroup::ICheckedChangeListener、ZKCheckBox::ICheckedChangeListener、ZKSeekBar::ISeekBarChangeListener、ZKVideoView 消息监听、ITextChangeListener…），`onCreate` 里 `setXxxListener(this)` + `findControlByID` 取指针。
- **回调分发表**：生成器把 logic 里 static 回调登记进静态映射表（sButtonCallbackTab/SZKSeekBarCallbackTab/SEditTextInputCallbackTab/SVideoViewCallbackTab/SSlideWindowItemClickCallbackTab…），Activity 虚函数（onClick/onProgressChanged/onTextChanged/onVideoPlayerMessage/onTimer）只做"按控件 ID 查表分发"。

## 1-1 logic.cc 静态全检的两个已知口径（书写前先知道，免得白查）

`check_all` 对 logic.cc 的第 6 / 8 项是**字符级扫描**，不是真正的语法分析：

- **#8 括号平衡**（实测实现，2026-09-17）：逐字符数 `(` / `)`，**只跳过双引号字符串**
  （连字符串里的转义 `\"` 也不处理），**注释与字符字面量都计入**。
  ⇒ **注释里写孤立的括号会误报「括号不平衡」FAIL**（例：`// 1) 先取指针`、`// 见上文（注`）；
  书写纪律：注释里带上括号就写配对，或干脆不写。真怀疑时排除注释重数一遍，**先别急着改代码**。
- **#6 指针核对**：`mXXXPtr` 必须在 json caption 集合里找得到；扫描前**只剔了 `//` 行注释**
  （块注释 `/* */` 不剔）⇒ 块注释里写一个不存在的 `mFooPtr` 会被当成真引用报缺失。

> 排查顺序：看到这两条 FAIL 先怀疑「注释写法」而不是「代码真的坏了」。

## 2. ⚠️ 按钮回调返回值语义（模板注释写反了，以壳代码为准）
`Activity::onClick()` 分发代码：`if (回调(pBase)) return;` ——
- **返回 true = 拦截**，onClick 直接结束（事件被吞，不再走默认）；
- **返回 false = 放行**，继续执行 `Activity::onClick(pBase)` 默认处理（ID=100 sys_back 的关闭页面行为依赖它）。
各 logic 文件头注释"返回 false 系统不再处理"是过期注释，勿信。

## 3. Activity 生命周期（onCreate 标准序列）
`onCreate()`：逐个 `findControlByID` 取指针 → `onUI_init()`（logic 实现：注册控件监听器/初始化文案/串口 listener）→ `EASYUICONTEXT->registerGlobalTouchListener(this)` → `registerProtocolDataUpdateListener(onProtocolDataUpdate)` → `rigesterActivityTimer()`。析构对称：unregisterGlobalTouchListener / unregisterProtocolDataUpdateListener / `onUI_quit()` / 指针置 NULL。
logic 钩子：onUI_init / onUI_show(≈onResume) / onUI_hide(≈onPause) / onUI_intent / onUI_quit / onUI_Timer(id)。**onUI_quit 里必须反注册一切 setXxxListener(NULL)/removeListener，否则悬垂**（长按/触摸/拍照/播放器/网络监听都是静态长生命周期对象 + 成对注册注销）。

### 3-1 导航 × 回调触发矩阵（释放逻辑放哪？关键！）

| 导航事件 | 当前页回调 | 说明/实证 |
|------|------|------|
| `goBack()` / 返回键销毁当前页 | **只走 `onUI_quit`，不经 `onUI_hide`** | ⚠️ 日志实证（多工程）：释放放 onUI_hide = 永不执行 → 播放器/VO/摄像头资源残留（典型事故：播放页残留 VO dev0 → 回预览 0xa00f8042） |
| `openActivity()` 新页覆盖当前页 | `onUI_hide`（后 `onUI_show` 回来） | hide 后页面还在，会再 show；不是销毁 |
| 覆盖页关闭回到本页 | `onUI_show` | 与 hide 配对 |
| `closeActivity()` / `goHome()` 销毁 | `onUI_quit`（同 goBack 销毁语义） | 按销毁处理 |

**铁律：媒体/硬件资源（播放器/摄像头/VO/监听）的释放放 `onUI_quit`；`onUI_hide` 只做「被覆盖」场景的暂停/让位，禁止在 hide 做一次性资源释放**（goBack 销毁不经 hide，放了=永不执行；且 hide 后还会 show 回来，释放了没法恢复）。

> ⚠️ 部分回调语义（openActivity 压栈 vs 覆盖细节）随版本可能有差异；拿不准时按「销毁→onUI_quit、覆盖→onUI_hide」二分先写对，再用 logcat 验证。

### 3-2 隐藏页的定时器仍在跑 → 空闲/超时判定必须加可见性门控

- **现象**：`onUI_hide` 之后，本页的 1s 定时器照样每秒钟回调，空闲累计照涨。用户从主页点进「设置」子页停留 15s，被主页那条空闲逻辑 `goHome()` 拽回屏保。用户侧表述：**「子页待久了莫名跳屏保/被拽回主页」**。
- **根因**：`REGISTER_ACTIVITY_TIMER_TAB` 里的定时器**与页面可见性无关**——页面被新页覆盖（push）后并不停表，Activity 对象还在、定时器还在跑。因此「本页定时器累计到 N 秒」≠「本页被看到且空闲 N 秒」，直接拿来判「空闲超时」必然误伤子页。
- **做法**：
  - `static bool sVisible = false;` —— **默认 false**，防止 onCreate 后还没 show 就开始计时；
  - `onUI_show()` 置 `true`，`onUI_hide()` / `onUI_quit()` 置 `false`；
  - 判空闲写成 `if (sVisible && sIdleTicks >= IDLE_ENTER_SEC)`；
  - 活动归零由**各页自己的触摸回调**做（`E_ACTION_DOWN` 与 `E_ACTION_MOVE` 都算活动，拖动时不被抢走），父页/子页各自持有自己的 activity 标记，不跨页共享。
  - 配套口径：屏保只由主页触发（子页 `onUI_show` 里 `setScreensaverEnable(false)`）。
- **怎么发现**：把「空闲累计」和「可见性」分开打日志，看到 hide 之后 tick 仍在上涨即确诊；或最小复现——进子页静置超过父页阈值，看是否被弹回屏保。

### 3-3 空闲/时长计时禁用墙钟，改「心跳 tick 计数」

- **现象**：用 `TimeHelper::getCurrentTime()` 前后差值算 elapsed，出现两种相反故障：要么**永不推进**（该次会话返回 0，或校时前后基准被重置），要么**瞬间超时**（NTP 拨钟把系统时间向前跳了一大截）。用户侧统一表述：**「操作到一半被屏保打断」**。
- **根因**：墙钟不是单调时钟。`ClockManager` 这类组件**在校时成功后本身就会步进系统时间**，任何以「两个墙钟读数之差」为时间量的逻辑，都会在拨钟那一刻失真。
- **做法**：
  - 空闲：复用 3-2 的 1s 心跳，`sIdleTicks++`，触摸/`onUI_show` 时归零，阈值 `>= 15` 判空闲；
  - 媒体/素材时长同理：`sMediaTicks`（每秒 +1）；换素材时归零；
  - 计时只随心跳走，与任何时钟源无关；
  - 诊断日志**同时**打印墙钟差值作参考（`wall_diff_ms`），便于区分「真空闲」与「校时跳变」。
- **怎么发现**：怀疑计时失真时，先看 `TimeHelper::getCurrentTime()` 是否在校时后出现阶跃（对比 tick 与墙钟两条曲线）；把判定切成 tick 计数后故障应立即消失。

### 3-4 `static` 缓存与控件指针必须同生命周期（页面销毁要清缓存）

- **现象**：二维码**「经常不显示，切一下模式才出来」**。
- **根因**：`sQrUrl` 是 `static`，**跨页面实例存活**；页面销毁时控件指针被 generated 代码置 NULL；重进页面控件是**新建**的、从没执行过 `loadQRCode`，而刷新函数见 `url == sQrUrl` 就 `return` → 新控件里是空白。切到其它模式时缓存被 clear，于是表现为「切一下才显示」。一句话：**缓存活了，控件没活**。
- **做法**：缓存的**生命周期必须与页面实例对齐**——
  - `onUI_quit()` 里清掉页面级缓存（QR 内容重算贵，但仍要清）；
  - `onUI_init()` 里再清一次作双保险（页面重建的第一个刷新就能落到新控件）；
  - 同类修法：相册页 `sQrShown.clear()`。
- **`onUI_quit()` 该清什么（通用清单）**：
  1. **缓存标志**：`sFirstShown` / `sInited` 这类「只做一次」的闸门；
  2. **缓存的 url / 文本 / 内容哈希**：凡「值没变就跳过」的缓存（QR 内容、格式化字符串、上次下发的文案）；
  3. **已下发状态**：是否已 setText / 已 load 过、上次下发的值；
  4. **反注册一切监听**：`setXxxListener(NULL)`、`removeListener`、`unregisterGlobalTouchListener`、`unregisterProtocolDataUpdateListener`——静态长生命周期对象（长按/触摸/拍照/播放器/网络监听）必须成对注册注销，否则悬垂；
  5. **页面级资源/传输**：硬件句柄、播放器、摄像头、推送传输会话（销毁语义见 §3-1，放 quit 不放 hide）。
- **怎么发现**：`static` 缓存与控件指针混用时，症状几乎都是**「第一次进页正常、再次进页异常」或「切一下才对」**。排查法 = 搜 logic 里所有 `static` 变量，逐一自问「页面销毁之后，它还有效吗」。

## 4. 定时器
- 静态表：`static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {{id, 毫秒}, ...};`（**id 全工程唯一**，静态与动态共用 id 空间）→ 页面打开即生效。
- 动态控制（mainActivity.cpp 包装）：`mActivityPtr->registerUserTimer(id, ms) / unregisterUserTimer(id) / resetUserTimer(id, 新ms)`（改已在跑的定时器=变速）。
- 回调 `onUI_Timer(id)`：return true 继续、false 停该 id；**回调在 UI 线程，禁止耗时操作**（长活/高频放 Thread）。
- 用法边界：关动态定时器不影响静态表那条（独立链路）。

## 5. 串口协议模板（→ 已独立成权威页）

`UartContext` 读线程 + `ProtocolParser/Sender` + `SProtocolData` 共享变量 + 帧格式/校验/粘包处理，
**完整口径见 `knowledge/devflow/uart-protocol-framework.md`**（含 11 条从代码读出的铁律、
"加一条协议只改三处"、以及 Modbus 等协议层交给 Linux/Arduino 生态的边界声明）。

本节只留**与 activity 骨架直接相关**的钩子级事实：

- **app 级**：`Main.cpp` 的 `onEasyUIInit` 开串口
  （`UARTCONTEXT->openUart(CONFIGMANAGER->getUartName(), CONFIGMANAGER->getUartBaudRate())`）、
  `onEasyUIDeinit` 关 —— 串口生存期 = 整个应用，页面切换不重开。
- **page 级**：activity `onCreate` **注册** `registerProtocolDataUpdateListener(onProtocolDataUpdate)`、
  **析构反注册**，**成对是铁律**（R6，漏了 = 页面销毁后收到数据即崩）；
  回调 `static void onProtocolDataUpdate(const SProtocolData&)` **在串口线程**上被调 —— 别直接刷 UI。

## 6. 系统级界面 SysApp（非 Activity）
注册宏：`REGISTER_SYSAPP(APP_TYPE_SYS_STATUSBAR/SCREENSAVER/IME, 类名)`；类继承 **BaseApp**（不是 Activity），onCreate 先 `BaseApp::onCreate()`；`getAppName()` 返回独立 ftu 文件名。
- **状态栏**：独立 ftu 注册 APP_TYPE_SYS_STATUSBAR（可放 sys_back(100)/sys_home(101) 图标+时钟，自成交互 UI）；业务页 `EASYUICONTEXT->isStatusBarShow()/showStatusBar()/hideStatusBar()` 运行时切显隐；SysApp 按钮回调 return false 交系统默认（返回/回主页）。
- **屏保**：APP_TYPE_SYS_SCREENSAVER 的"UI 壳"，放自刷新 DigitalClock 即零代码；何时进入/退出由系统空闲机制管理（代码/JSON 无超时 API）。
- **自定义输入法 IME**：APP_TYPE_SYS_IME + 继承 IMEBaseApp；系统在任何 EditText 聚焦时自动拉起；`onInitIME(SIMETextInfo*)`（字段 text/isPassword/passwordChar/imeTextType ALL|NUMBER）注入编辑框信息 → 本地缓冲改字 → Enter=`doneIMETextUpdate(整串)` / Hide=`cancelIMETextUpdate()` 一次性交回。词库 `im_open_decoder(CONFIGMANAGER->getDictPinyinPath(), "/data/user.dic")`；候选 `im_search/im_get_candidate(UTF16)` → ConvertUTF16toUTF8 → `mSlideTextPtr->setTextList(vector<string>)`；候选点击 `ZKSlideText::ITextUnitClickListener::onTextUnitClick(..., text)`；按键字符靠 `pButton->getID()` 查静态表（键帽文字只是视觉，四态 ch/upch/numch/symb，NULL=该模式不显示）；密码框强制英文键盘+`passwordChar` 打码回显；DEL 长按 = ILongClickListener 清空。详见 ImeDemo UserImeLogic.cc（1030 行范本）。

## 7. 多语言（TranslationDemo）
- 工程 i18n/*.tr（Android resources XML：`<string name="key">值</string>`；文件名 `locale-显示名.tr`）
- ftu 静态文本写 `@key`；代码 `setTextTr("key")`（**不带 @**）；切语言 `EASYUICONTEXT->updateLocalesCode("zh_CN"/"en_US"/...)` 立即全局生效；跳系统语言设置 `EASYUICONTEXT->openActivity("LanguageSettingActivity")`
- 坑：所有 .tr 的 key 全集必须对齐，漏一种语言=该语言显示缺省；.tr 是 XML 不是 key=value。

## 8. 平台编译宏（裁剪整页业务）
- `#if defined(__PLATFORM_Z6S__) || defined(__PLATFORM_A33NOR__)`：老平台排除（触摸监听/4G/ETH 等）
- `#if defined(FLYTHINGS_ENABLE_HOTSPOT)`（features.h 默认注释）：SoftAP 整页代码被裁
- API 版本差异：`#if defined(FLYTHINGS_API_1_0)`（IME onInitIME 参数指针/引用）
- 点结构体：老平台 MPPOINT，新平台 **SZKPoint**（diagram/painter 用）

## 9. 常用系统能力速查（Demo 实证）
| 能力 | API | Demo |
|---|---|---|
| 读/校系统时间 | `TimeHelper::getDateTime()`(struct tm*) → 改 → `TimeHelper::setDateTime(t)`；tm_year ±1900、tm_mon ±1；tm_wday 0=周日 | DigitalClock/Date/clock |
| 屏幕亮度 | `BRIGHTNESSHELPER->getBrightness()/setBrightness(0..100)` | SeekBarDemo |
| 存储挂载监听 | `MOUNTMONITOR->addMountListener(&l)`（notify(what,status,msg)，status=MOUNTED/REMOVE…中间态 UNMOUNTING 等 10 态）；`isMounted(path)` 轮询兜底 | MountDemo |
| 线程 | `class X: Thread{ readyToRun(); threadLoop(); }`；`run("name")/requestExit()/requestExitAndWait()/isRunning()/exitPending()`；**工作线程直接刷 UI 是官方示例做法，保守改共享变量+UI 定时器轮询** | ThreadDemo |
| GPIO | `GpioHelper::input("B_02")/output("B_02",1)`（引脚名平台不同，返回 -1 失败；边沿中断 registerGpioListener 头文件有 demo 未用；模组需启用 GPIO 固件） | GpioDemo |
| 页面跳转 | `EASYUICONTEXT->openActivity("subActivity")/goHome()/goBack()` | 全系 |
| 资源路径 | `CONFIGMANAGER->getResFilePath("pic/x.png")`（相对资源根） | listViewDemo |
