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
tags: [35 工程, 逐源码深读, activity 骨架, 回调表, 生命周期, logic, cc, 定时器, 串口模板, SysApp, 全检误报]
evidence: []
---
# FlyThings 工程代码骨架（35 官方 Demo 深度阅读提炼）

> 检索导引：问「activity 骨架怎么写 / 回调分发表在哪 / onUI_init·onUI_quit 标准序列 / logic.cc 与 activity.cpp 谁参与编译 / 切页后回调还触发吗 / check_all 括号平衡误报」→ 本文（工程代码骨架总纲）；控件逐个的代码接口见 `uicontrols/widget-code-api.md`。
> 2026-09-08 basedemo-new_z20_1024_600（35 工程）逐源码深读。所有 Demo 共用同一套生成器骨架，理解它=理解一切控件如何被代码驱动。
> 检索词：activity 骨架/回调表/生命周期/logic.cc/定时器/串口模板/SysApp/REGISTER_ACTIVITY/check_all 括号不平衡/全检误报。


## 0. ⚠️ 先看：两套编译体系（2026-09-17 纠偏）

- **IDE 体系**：`src/activity/<name>Activity.cpp` 参与编译，它 `#include` 同名 logic（`logic/<name>Logic.cc`）。
- **`fun build`（命令行，推荐）**：**`src/activity/*` 完全不参与编译**；fun 直接把 `src/logic/*.cc`、`src/**/*.cpp` 与**自己生成的** `generated/{event,event_dispatcher,ui_main}.cpp` 编成 `libzkgui.so`（编译宏 `FUN_BUILD=1`）。
- 所以：改 activity 对 fun 构建**无效**；**不要改 `.fun/<平台>/CMakeLists.txt`**（fun 自动生成、会被覆盖）。细节见 `cli-fun-toolchain.md` §4.5。

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

## 4. 定时器
- 静态表：`static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {{id, 毫秒}, ...};`（**id 全工程唯一**，静态与动态共用 id 空间）→ 页面打开即生效。
- 动态控制（mainActivity.cpp 包装）：`mActivityPtr->registerUserTimer(id, ms) / unregisterUserTimer(id) / resetUserTimer(id, 新ms)`（改已在跑的定时器=变速）。
- 回调 `onUI_Timer(id)`：return true 继续、false 停该 id；**回调在 UI 线程，禁止耗时操作**（长活/高频放 Thread）。
- 用法边界：关动态定时器不影响静态表那条（独立链路）。

## 5. 串口协议模板（UartContext + ProtocolParser/Sender，除双串口外 35 工程同款）
- Main.cpp：onEasyUIInit `UARTCONTEXT->openUart(CONFIGMANAGER->getUartName(), CONFIGMANAGER->getUartBaudRate())`；deinit `closeUart()`；onStartupApp 返回 `"mainActivity"`。
- UartContext 是 Thread 子类：openUart 配 termios（8N1 无流控）+ `fcntl(O_NONBLOCK)` + run("uart") 起读线程；send()=write 全量。
- 读线程粘包处理：16KB 拼接缓冲 + 每轮 read 追加 → `parseProtocol(buf, len)` 返回消费字节数 → 残留半包 memcpy 到头部；无数据 `Thread::sleep(50)` 防忙等。天然解决拆包/粘包。
- 帧格式（CommDef.h）：`FF 55 | CmdID(2B 高前) | DataLen(1B) | Data | [CheckSum 1B]`，最小帧 5/6；ProtocolParser 逐字节找帧头自动对齐乱序，数据不全 break 等下次（半包重组）。
- 订阅：全局 `SProtocolData` + Mutex 保护的 listener 数组；activity onCreate `registerProtocolDataUpdateListener(onProtocolDataUpdate)`，析构反注册。收帧→`notifyProtocolDataUpdate`→业务 `static void onProtocolDataUpdate(const SProtocolData&)` 刷 UI（回调里别耗时）。
- 发送：`sendProtocol(cmdID, data, len)`（ProtocolSender.h 组帧后 UARTCONTEXT->send）。
- 校验：CommDef.h 默认 `//#define PRO_SUPPORT_CHECK_SUM`（关）；对端带校验需打开并改最小帧长，两端一致。
- **双串口（DoubleUartDemo）**：单例→双实例 `UartContext::init()` new ttyS0/ttyS1（波特率写死 B9600）+ 各自读线程缓冲；`parseProtocol(uart,...)` 打 `uart_from` 标；`sendProtocolTo(uart, cmdID, ...)` 按口发。共享 SProtocolData/listener 高吞吐会字段覆盖/回调交错，多口业务建议 per-uart 数据。

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
