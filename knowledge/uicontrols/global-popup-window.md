---
id: uicontrols-global-popup-window
title: 工程自定义系统窗口 / 全局弹框（含 car 工程 btcall 来电弹框做法）
category: uicontrols
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [F133]
tags: [statusbar, navibar 以及, 自定义全局弹框, 官方无条款的地方一律标, 未收录, 不猜, 全局弹框, 自定义弹框, 弹窗, 悬浮窗, 浮窗, floatwnd, popupWnd, popup window, btcall, 蓝牙来电弹框]
evidence: []
---
# 工程自定义系统窗口 / 全局弹框（含 car 工程 btcall 来电弹框做法）

> 检索导引：问「全局弹框/悬浮窗怎么做 / 蓝牙来电话弹窗（btcall）/ 自定义系统级弹窗注册 / 顶层窗口层级与生命周期能不能自创」→ 本文；框架内建的系统窗口见 `knowledge/uicontrols/system-windows.md`。
> 2026-09-22 需求方定规（与 `knowledge/uicontrols/system-windows.md` 同批）：「系统级页面 screensave/statusbar/navibar 以及
> **自定义全局弹框**（car 相关项目里面的 btcall 页面），AI 要能**精准命中**；**不要自己去创造页面的生命周期和层级关系**」。
> 本文只写**有出处的做法**（easyui 头文件 + 真实工程代码行号）；官方无条款的地方一律标「未收录」，不猜。
> 检索词：全局弹框 / 自定义弹框 / 弹窗 / 悬浮窗 / 浮窗 / floatwnd / popupWnd / popup window /
> btcall / show_btcall_widget / hide_btcall_widget / 蓝牙来电弹框 / 通话 UI / 顶层窗口 / 系统级弹窗 /
> APP_TYPE_SYS_POPUPWND / APP_TYPE_SYS_FLOATWND / APP_TYPE_SYS_CTRLBAR / REGISTER_SYSAPP / SYSAPPFACTORY /
> sysapp_context / attach_timer / show_xxx / hide_xxx / is_hit_xxx / BaseApp::show。

## 0. 一句话口径

内建系统窗口只有 4 类（statusbar / navibar / screensaver / IME，见 `knowledge/uicontrols/system-windows.md`）。
**「全局弹框 / 悬浮窗 / 来电弹框」不是框架内建类型**—— 真实做法是：
**工程自定义一个 appType 编号 → `REGISTER_SYSAPP` 注册 → `SYSAPPFACTORY->create()` 创建 / `delete` 销毁**，
**显示与隐藏由业务代码决定**（工程里通常封一层 `app::show_xxx()/hide_xxx()`）。
→ 找弹框时先找这套「自定义 appType + 工程封装」，**不要**去 `EASYUICONTEXT` 里找一个不存在的弹框 API。

## 1. 机制（宏与工厂；以工程内自带的头文件为准）

`app/SysAppFactory.h`（工程内自带）：

```cpp
class SysAppFactory {
public:
    static SysAppFactory *getInstance();
    bool registerSysApp(int appType, BaseApp* (*create)());
    BaseApp* create(int appType);
};

#define SYSAPPFACTORY  SysAppFactory::getInstance()

#define REGISTER_SYSAPP(appType, _class) \
    static struct _SysAppFactory_##_class { \
        static BaseApp* create() { return new _class(); } \
        _SysAppFactory_##_class() { SYSAPPFACTORY->registerSysApp(appType, create); } \
    } _autoRegister_SysApp_##_class
```

要点：`appType` 参数就是 **`int`**，**不限于内建的 1..4**（工程自定义编号是常规操作）；
`REGISTER_SYSAPP` 是**静态对象构造期注册**；`create()` 返回的对象由调用方负责 `delete`。

## 2. 真实工程证据（三种写法都在产，行号可核）

| 写法 | 出处 | 关键行 |
|---|---|---|
| 自定义编号 100/101 | 内部 car/PND 工程 `mark_cv201/CV201_PND` | `src/config.h:170-171` → `#define APP_TYPE_SYS_CTRLBAR 100` / `#define APP_TYPE_SYS_FLOATWND 101`；`src/logic/floatwndLogic.cc:40 REGISTER_SYSAPP(APP_TYPE_SYS_FLOATWND, floatwndActivity)`；`src/logic/ctrlbarLogic.cc:22 REGISTER_SYSAPP(APP_TYPE_SYS_CTRLBAR, ctrlbarActivity)` |
| 直接给数字 1000 | 内部 `DashBoard_T113/BMW` | `jni/logic/camerawindowLogic.cc:47 REGISTER_SYSAPP(1000, camerawindowActivity)`（**编号纯约定，框架不校验含义**） |
| 弹框页 POPUPWND=100 | `projects/CalendarAlbum-F133`、`projects/CycleComputer-F133` | `src/config.h:29 #define APP_TYPE_SYS_POPUPWND 100`；`src/logic/popupWndLogic.cc:46 REGISTER_SYSAPP(APP_TYPE_SYS_POPUPWND, popupWndActivity)` |
| 创建 / 销毁 | `CalendarAlbum-F133/src/logic/sysapp_context.cpp:43` 与 `on_timer()` 内 | `_s_popup_wnd = SYSAPPFACTORY->create(APP_TYPE_SYS_POPUPWND);` / `delete _s_popup_wnd; _s_popup_wnd = nullptr;` |
| 弹框页的 json 长什么样 | 内部 `mark_cv201/CV201_PND/ui/floatwnd.json` | 根节点 `"topmost": true`，内容 = 一个 `window__1`（`PopWindow`）控件；弹框本体就是 window |
| 触摸命中判定 | `CV201_PND/src/logic/sysapp_context.cpp:96` + `src/logic/mainLogic.cc:836` | `app::is_hit_floatwnd(x,y)` / `app::is_hit_ctrlbar(x,y)` —— 弹框/浮窗是**独立一层，触摸不外传**|

## 3. 工程封装的固定套路（`src/logic/sysapp_context.{h,cpp}`，`namespace app`）

- 对外接口名（两套真实例子）：
  - `show_popup_wnd()` / `hide_popup_wnd()`（CalendarAlbum-F133 / CycleComputer-F133）
  - `show_floatwnd()` / `hide_floatwnd()` / `is_show_floatwnd()` / `is_hit_floatwnd()`（CV201_PND）
  - `show_btcall_widget()` / `hide_btcall_widget()`（蓝牙来电弹框；声明见 `KaiduZ9S/src/logic/sysapp_context.h`）
- 内部实现要点（**这是工程约定，不是框架规定**）：
  1. show/hide 不直接 `new/show`，而是 **注册到宿主页的一次性定时器**：
     `attach_timer(reg, unreg)` 拿到宿主页的 `registerTimer/unregisterTimer`，`show_xxx()` 里 `_reg_timer(ID, 0)`，
真正的 `SYSAPPFACTORY->create(...)` / `delete` 落在 `on_timer(int id)` 分支里。
  2. 好处：**从任意线程/蓝牙回调里调用都落到 UI 线程**（配合 `knowledge/uicontrols/cross-thread-ui-rule.md`），
且不在回调里做重活、不把对象生命周期和回调栈绑定。
- 业务页按需**成对调用**：真实调用点 20+ 处，例：`lvinLogic.cc`（show/hide 混合、页面进出切换）、
  `lockLogic.cc`、`EffluentModeLogic.cc`、`CloudCusIntWndLogic.cc`、`AddEffluentModeLogic.cc`、`mainLogic.cc`。
- **btcall（蓝牙来电弹框）**：就是同一套路的一个具名封装（`app::show_btcall_widget()/hide_btcall_widget()`）；
  **谁在什么时候 show / hide 完全由业务约定**——没有「框架自动弹出」「来电结束自动消失」这回事。

## 4. 另一种真实做法：把通话 UI 放进已有系统窗口（同一页面内的 window）

内部 car/PND 工程 `mark_cv201/CV201_PND/src/logic/statusbar.cc:38-76`：

- 状态栏页里放两个 window 控件：去电 `mcallWindowPtr`、来电 `mincomingWindowPtr`；
- 由蓝牙状态回调驱动：`_bt_call_cb(bt_call_state_e state)`（`E_BT_CALL_STATE_IDLE / OUTGOING / INCOMING / TALKING`）
  → `mcallWindowPtr->showWnd()/hideWnd()` + `mstatusbarPtr->show()/hide()`；
- 通话中 `mstatusbarPtr->registerUserTimer(TALK_TIMER, 1000)` 刷通话时长；
- 挂断 / 蓝牙断开 / 掉电统一走 `_call_ui_reset()`（复位 window、复位按钮可见性、注销定时器）。

→ 结论：**能挂进已有系统窗口（状态栏）的就别新造一层**；「来电弹框」在同一工程里两种实现都存在，
选哪种看该工程既有约定（**不确定时先 grep 工程里的 `show_*` 封装**，别自己设计）。

## 5. 生命周期与层级（**只认这些**）

- 自定义全局弹框 = **`BaseApp` 派生类**（就是 IDE 为 `<弹框页>.ftu` 生成的 `<页面名>Activity` 类）+ `REGISTER_SYSAPP` 注册；
生命周期回调与普通页面**同一套**：`onUI_init / onUI_show / onUI_hide / onUI_quit / onUI_Timer / onButtonClick_*` + `REGISTER_ACTIVITY_TIMER_TAB`。
- `BaseApp` 自带的接口（`app/BaseApp.h`，实测行）：`create()`、`show()`、`hide()`、`isShow()`、`relayout(name)`、
  `setPosition(LayoutPosition)`、`findControlByID(int)`、`registerTimer(id,time)`、`unregisterTimer(id)`、`resetTimer(id,time)`；
虚函数 `onCreate()` / `onClick(ZKBase*)` / `onTimer(int)`。
- **对象归属**：`SYSAPPFACTORY->create()` 得到的对象**由业务 `delete`**（工程里正是这么写的）——没有框架自动回收。
- **层级**：弹框/浮窗是**独立于普通页面的系统级一层**，触摸要自己判命中（`is_hit_xxx`）；
  **框架没有公开「弹框之间/与系统窗口之间的叠放顺序」条款 → 标「未收录」，按真机实测**，不要写"最高层"结论。
- `topmost` 字段实测出现在 `floatwnd.json` 根节点；**其精确语义官方未收录**（只照抄用法，不扩写解释）。

## 6. 反例（AI 自创写法）

| 自创 | 错在哪 | 正确 |
|---|---|---|
| `EASYUICONTEXT->openActivity("btcall")` 当弹框用 | 自定义系统窗口不是 Activity；弹框也不在框架 Activities 里 | 走工程 `app::show_btcall_widget()`（或该工程既有的 show/hide 封装） |
| 自造 `#define APP_TYPE_SYS_BTCALL 5` 就以为框架认 | 内建只有 1..4；其它编号必须**自己注册 + 自己 create**| 自定义编号（避开 1..4）+ `REGISTER_SYSAPP` + `SYSAPPFACTORY->create` |
| 给弹框编「自动消失 / 自动回栈 / 自动 onUI_quit」 | 真实工程全是业务 show/hide + delete | 在业务页 `onUI_init`/`onUI_quit`（或进出流程）成对 show/hide |
| 直接在蓝牙回调/工作线程里 `new`+`show` 弹框 | 重活与生命周期耦合，跨线程 UI 也不合规范 | 用工程既有 `sysapp_context` 的定时器转发（`attach_timer` + `_reg_timer`） |
| 假设 `getStatusBar()->show()` 能显示弹框 | 弹框不是状态栏 | 弹框有它自己的 appType 与封装接口 |
| 给弹框页编一套新回调/新注册流程 | 框架只认 `REGISTER_SYSAPP` + 那套回调 | 照 §1/§5 |

## 7. 相关文档

- 内建 4 类系统窗口（statusbar/navibar/screensaver/IME）：`knowledge/uicontrols/system-windows.md`
- 页面归属：同 Activity 内 window（`showWnd`）vs 独立 ftu → `knowledge/devflow/page-architecture-spec.md`
- 触摸穿透与命中：`knowledge/uicontrols/touch-events.md`；跨线程操作 UI：`knowledge/uicontrols/cross-thread-ui-rule.md`
- 页面代码骨架与回调：`knowledge/devflow/activity-code-skeleton.md`
