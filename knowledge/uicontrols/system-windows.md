---
id: uicontrols-system-windows
title: 系统级窗口（状态栏 statusbar / 导航栏 navibar / 屏保 screensaver / 输入法 IME）
category: uicontrols
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [statusbar, 查不到的一律标, 未收录, 不猜, 不套别的 GUI 框架, 检索词：系统级页面]
evidence: []
---
# 系统级窗口（状态栏 statusbar / 导航栏 navibar / 屏保 screensaver / 输入法 IME）

> 检索导引：问「状态栏·导航栏怎么开 / 屏保怎么配 / 输入法窗口怎么写 / showStatusBar·screensaverOn 等 API / 系统级页面能不能自己创生命周期」→ 本文。
> 2026-09-22 钟工定规：「系统级页面 screensave/statusbar/navibar 以及自定义全局弹框，AI 要能**精准命中**；
> **不要自己去创造页面的生命周期和层级关系**」→ 本文只写**有出处的事实**（官方文档 + easyui 头文件 + 真实工程），
> 查不到的一律标「未收录」，不猜、不套别的 GUI 框架。
> 检索词：系统级页面 / 系统窗口 / 系统内置界面 / statusbar / 状态栏 / navibar / 导航栏 / screensaver /
> screensave / 屏保 / 输入法 / IME / UserIme / APP_TYPE_SYS_ / REGISTER_SYSAPP / SYSAPPFACTORY /
> showStatusBar / hideStatusBar / isStatusBarShow / getStatusBar / showNaviBar / hideNaviBar /
> screensaverOn / screensaverOff / isScreensaverOn / setScreensaverTimeOut / setScreensaverEnable /
> loadStatusBar / loadNaviBar / 悬浮层 / 全局层 / 通用来电弹框（见 `global-popup-window.md`）。

## 0. 一句话口径

普通界面 = **Activity**（一个 ftu 一个 Activity）；
**系统级窗口 = BaseApp**（框架注册/装载，悬浮在普通窗口之上），
**不是 Activity**，所以 **不能** `openActivity("statusbar")`。

## 1. 内建系统窗口只有 4 类（官方口径，别扩写）

出处：`wiki/flythings/interaction/system_apps.md`（官方文档镜像 developer.flythings.cn）
+ `app/AppTypeDef.h`（easyui 2.2.0 与 2.9.0 实测一致，行 14-17）

| 类型 | 固定文件名（IDE「窗口类型」生成） | APP_TYPE（头文件常量） | 生成代码里的注册宏 | 显示 / 隐藏 |
|---|---|---|---|---|
| 状态栏 | `statusbar.ftu` | `APP_TYPE_SYS_STATUSBAR` = 1 | `REGISTER_SYSAPP(APP_TYPE_SYS_STATUSBAR, statusbar)` | `EASYUICONTEXT->showStatusBar()` / `hideStatusBar()` |
| 导航栏 | `navibar.ftu` | `APP_TYPE_SYS_NAVIBAR` = 2 | `REGISTER_SYSAPP(APP_TYPE_SYS_NAVIBAR, navibar)` | `showNaviBar()` / `hideNaviBar()` |
| 屏保 | `screensaver.ftu` | `APP_TYPE_SYS_SCREENSAVER` = 3 | `REGISTER_SYSAPP(APP_TYPE_SYS_SCREENSAVER, screensaver)` | `screensaverOn()` / `screensaverOff()` + 超时/使能 |
| 输入法 | `UserIme.ftu`（生成 `UserImeActivity`） | `APP_TYPE_SYS_IME` = 4 | `REGISTER_SYSAPP(APP_TYPE_SYS_IME, UserImeActivity)` | `showIME(...)` / `hideIME()` |

- 官方原话（状态栏）：**「一个悬浮在 UI 界面之上的一个通用显示区」**，常用于常见信息/返回键/Home 键；
  导航栏「跟状态栏没有什么差别」，一般在页面底部。
- **文件名与类型绑定**：IDE 里选窗口类型后工具自动生成文件 + 注册代码；
  自己改文件名 / 自造类型编号 = 框架不认识（`APP_TYPE_ACTIVITY` = 0 是普通 Activity；**内建只有 1/2/3/4**）。
- 屏保语义（官方）：用户停止交互超过设定时长，系统**自动打开**该页面（超时可在工程属性里设，-1 = 不进屏保）。

## 2. API 全集（`entry/EasyUIContext.h`，easyui 2.9.0 实测行号）

| 类别 | API | 行 |
|---|---|---|
| 状态栏 | `showStatusBar()` / `hideStatusBar()` / `isStatusBarShow()` / `getStatusBar()`（返回 `BaseApp*`，可 `->show()/->hide()`） | 103-115 |
| 导航栏 | `showNaviBar()` / `hideNaviBar()` / `isNaviBarShow()` / `getNaviBar()` | 120-132 |
| 屏保 | `setScreensaverTimeOut(int)` / `getScreensaverTimeOut()` / `resetScreensaverTimeOut()` / `performResetScreensaverTimeOut()` | 142-154 |
| 屏保 | `setScreensaverEnable(bool)` / `isScreensaverEnable()` / `screensaverOn()` / `screensaverOff()` / `isScreensaverOn()` / `performScreensaverOn()` / `performScreensaverOff()` | 159-184 |
| 输入法 | `showIME(IMEContext::SIMETextInfo*, IMEContext::IIMETextUpdateListener*)` / `hideIME()` / `performHideIME()` / `isIMEShow()` | 186-193 |
| 装载（框架级） | `loadStatusBar()` / `loadNaviBar()` / `unloadStatusBar()` / `unloadNaviBar()` / `performLoadStatusBar()` / `performLoadNaviBar()` / `performScreensaver()` | 213-224 |
| 成员 | `mStatusBarPtr` / `mNaviBarPtr` / `mScreensaverPtr` | 233-235 |

## 3. 屏保的两个配置入口（都对，别只认一个）

1. 代码：`setScreensaverTimeOut(秒)` / `setScreensaverEnable(bool)`
   —— 官方给的真实场景：升级界面不能进屏保 → 升级页里 `setScreensaverEnable(false)`，退出时恢复 `true`。
2. 工程配置：`.settings/*.easyui.prefs` 与 `package.properties` 的 `EasyUI.cfg` 键 `screensaverTimeOut`（-1 = 不进屏保）
   → 详见 `devflow/package-properties-easyui-cfg.md`。

## 4. 真实工程事实（用于核对；`内部` 前缀=不进对外发布版）

| 事实 | 出处 |
|---|---|
| 官方可编样例工程 | `projects/basedemo-new_z20_1024_600/{StatusBarDemo-New,ScreensaverDemo-New,ImeDemo-New}` |
| 生成代码长什么样 | `projects/iOSStyle-F133/.fun/f133/generated/ui_statusbar.cpp:8` → `REGISTER_SYSAPP(APP_TYPE_SYS_STATUSBAR, statusbar)` |
| 屏保逻辑文件与触摸回调名 | 内部 car/PND 工程 `src/logic/screensaver.cc:64 onscreensaverActivityTouchEvent`（回调命名同普通页面） |
| 屏保与业务互斥（真实做法） | 内部 `mark_cv201/CV201_PND`：来电/通话 `mainLogic.cc:138-139 screensaverOff()`；倒车中不进屏保 `mainLogic.cc:393-395`；升级测试页 `TestLogic.cc:136-137 setScreensaverEnable(false)`；设置页改超时 `settingsLogic.cc:354-362 setScreensaverEnable/TimeOut` |
| 系统窗口里也能放业务 UI | 同工程状态栏页里放通话 window（见 `global-popup-window.md` §4） |

## 5. 生命周期与层级（**只认这些，别自创**）

- **回调**：系统窗口的 logic 与普通页面**同一套回调名**：`onUI_init` / `onUI_show` / `onUI_hide` / `onUI_quit` /
  `onUI_Timer(int)` / `onButtonClick_<Caption>` / `on<页面名>ActivityTouchEvent`，定时器仍写 `REGISTER_ACTIVITY_TIMER_TAB`
  （页面名 = 文件名：statusbar / navibar / screensaver / UserIme）。
- **装载/卸载**：走框架的 `load*/unload*`（§2 最后一行）——**不要自己造装载流程**，也不要手动 `new` 系统窗口。
- **层级**：状态栏/导航栏由框架叠在普通窗口**之上**（官方用词「悬浮」、导航栏一般在底部）；
  **具体 z 序 / 多系统窗口叠放顺序官方无可查条款 → 标「未收录」，以真机实测为准，不要编**。
- **触摸**：系统窗口是独立一层，会挡住下层（与控件 `touchable` 无关）；要穿透见 `uicontrols/touch-events.md`。

## 6. 反例（AI 最常见的「自创」）

| 自创写法 | 为什么错 | 正确做法 |
|---|---|---|
| `EASYUICONTEXT->openActivity("statusbar")` | statusbar 不是 Activity，是框架按 sysapp 装载的窗口 | `showStatusBar()` / `hideStatusBar()`（或 `getStatusBar()->show()/hide()`） |
| 自己 `#define APP_TYPE_SYS_STATUSBAR 5` | 内建编号固定 1/2/3/4 | 用 `AppTypeDef.h` 常量；要新类型见 `global-popup-window.md` |
| 给状态栏编 `onUI_create/onUI_destroy/onUI_pause` 之类回调 | 框架没有这些回调 | 只有 §5 列出的那套 |
| 假设屏保「有返回栈/自动 onUI_quit/会自动退回上一页」 | 官方只给 on/off/enable/timeout 语义 | 用 `isScreensaverOn()` 判断、`screensaverOff()` 退 |
| 把 `FLOATWND` / `POPUPWND` / `CTRLBAR` 当作内建系统类型 | 头文件里没有 | 那是**工程自定义**类型 → `uicontrols/global-popup-window.md` |
| 把「导航栏 navibar」当 Android 的导航栏 API 套用 | 只用官方那 4 个 API | 只用 §2 表中的接口 |

## 7. 相关文档

- 自定义全局弹框 / 悬浮窗 / 来电弹框：`uicontrols/global-popup-window.md`
- 页面归属判定（一个页面=一个 Activity=一个 ftu；同 Activity 内的 window 用 showWnd）：`devflow/page-architecture-spec.md`
- 工程配置（screensaverTimeOut 等 EasyUI.cfg）：`devflow/package-properties-easyui-cfg.md`
- 页面代码骨架与回调时机：`devflow/activity-code-skeleton.md`
- 触摸穿透/命中：`uicontrols/touch-events.md`；跨线程操作 UI：`uicontrols/cross-thread-ui-rule.md`
