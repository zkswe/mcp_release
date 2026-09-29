---
id: devflow-dynamic-screen-rotation
title: 🔄 动态旋转屏幕 / 运行时切换布局（relayout）
category: devflow
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [F133, Z20, Z21, T113, V85X]
tags: [RelayoutDemo, F133, 0 引入, 现有公开包的 z20, z21, 动态旋转, 运行时旋转, 横竖屏切换, 屏幕方向切换, 两套 ftu]
evidence: []
---
# 🔄 动态旋转屏幕 / 运行时切换布局（relayout）

> 检索导引：问「运行时转屏 / 横竖屏切换不重启应用 / relayout 怎么用 / setScreenRotate·setTouchRotate / 两套 ftu 怎么切 / 某版本不支持某控件（scrollwindow 看不到）」→ 本文；静态方向配置见 `devflow/package-properties-easyui-cfg.md`。
> 2026-09-14 沛哥指路 `projects/LearningProject/RelayoutDemo`（F133）→ 本机 easyui 逐版本实测校准（**需要较新的 EasyUI**：relayout 由 easyui 2.9.0 引入；现有公开包的 z20/z21/t113 均无 → 找 FlyThings 厂家支持）。
> 检索词：动态旋转 / 运行时旋转 / 横竖屏切换 / 屏幕方向切换 / 两套 ftu / relayout / setScreenRotate / setTouchRotate / EasyUI 版本要求 /
> **scrollwindow 不显示 / 控件看不到 / 控件没渲染 / 页面只有标题 / 某版本不支持某控件 / 编译期头版本 vs 设备运行库 / ro.easyui.version / strings libeasyui.so**。

## 1. 一句话机制

**运行时**改屏幕 + 触摸方向，再换到对应方向的布局，**不重启应用**：

```cpp
CONFIGMANAGER->setScreenRotate(rot);   // 屏幕内容旋转 0/90/180/270
CONFIGMANAGER->setTouchRotate(rot);    // 触摸坐标同步旋转（不跟随就只设前者）
mActivityPtr->relayout(payloadFtu);    // 换布局：传 ui/ 下的 ftu 文件名
```

- `relayout(const std::string &appName)` 在 **`include/app/BaseApp.h`**（Activity/Window 继承链上都能调）
- 另有控件级 `ZKBase::relayout(const Json::Value &json)`（`control/ZKBase.h`，用 json 直接重排单个控件，属另一路）
- 与静态旋转的区别：静态旋转是编译期写 `package.properties` 的 `EasyUI.cfg={"rotateScreen":270}`（见 `devflow/package-properties-easyui-cfg.md`），**开机定死**；动态旋转用于「用户能切 / 按场景切 / 传感器切」

## 2. Demo 全量逻辑（RelayoutDemo/src/logic/mainLogic.cc，核心就这几行）

```cpp
static bool onButtonClick_Button1(ZKButton *pButton) {
    static int rot = 0;
    CONFIGMANAGER->setScreenRotate(rot);   // 先转屏幕
    CONFIGMANAGER->setTouchRotate(rot);    // 再转触摸
    mActivityPtr->relayout(((rot == 0) || (rot == 180)) ? "main.ftu" : "main_p.ftu");
    rot = (rot + 90) % 360;                // 0 → 90 → 180 → 270 循环
    return false;
}
```

- Demo 里挂在定时器（`{1, 500}` 每 500ms 自动调一次）上，所以上电就自己转圈演示；实际项目挂按钮/设置项/传感器回调
- 0/180 用 `main.ftu`（800×1280），90/270 用 `main_p.ftu`（1280×800）

## 3. 工程结构要求（拆 RelayoutDemo 得到）

| 要求 | 说明 |
|------|------|
| **两套（或多套）ftu，同一个 Activity** | `ui/main.ftu`(800×1280) + `ui/main_p.ftu`(1280×800)，都是这个 `mainActivity` 的布局，`getAppName()` 仍返回主 `main.ftu` |
| **控件 ID 必须完全一致** | 实测两版 json 里 Button1=20001、QRCode1=92001、DigitalClock1=93001、ListView1=80001、PageWindow1=31001… 一模一样 → relayout 后 Activity 里 `mXXXPtr` 仍有效，`onCreate` 里注册的 adapter/监听器/串口回调不用重来，只变布局 |
| `package.properties` | `ignore.ftu.regex=*_p.ftu`（`*_p.ftu` 是备方向布局，按此正则处理，不要被当成普通 UI 一起处理） |
| 切完要做的收尾 | 布局变了 → 尺寸/坐标相关的东西（列表刷新、控件重排、状态恢复）放在 relayout 之后，或在 `onUI_show` 里按当前 `CONFIGMANAGER->getScreenRotate()` 判方向 |

## 4. ⚠️ 版本与平台支持（本机逐版本实测，2026-09-14）

判定方法：拉包到本地 registry 后 grep `include/app/BaseApp.h` 是否有 `relayout`。

| 平台 | easyui 版本 | `relayout` | 证据 |
|------|------|------|------|
| F133 | 2.9.0 | ✅ | `BaseApp.h:30 void relayout(const std::string &appName);` |
| F133 | 2.8.0 / 2.7.0 | ❌ 无 | 实装拉包后 grep 0 命中 |
| V85X | 2.9.0 | ✅ | 同上（另有 `getTouchRotate()`） |
| Z20 | 3.0.0（当前公开最新） | ❌ 无 | `BaseApp.h` 里只有 `updateLocales()` |
| Z21 | 2.6.0（公开最新） | ❌ 无 | 同上 |
| T113 | 2.6.0（公开最新） | ❌ 无 | 同上 |

- **结论：`relayout` 由 easyui 2.9.0 引入**（2.8.0 → 2.9.0 之间越过；2.9.0 及以上才有）
- `setScreenRotate` / `setTouchRotate` / `getScreenRotate` **很老就有**（z20 3.0.0、z21 2.6.0、t113 2.6.0 全有）——**只有 `relayout` 是新的**，所以「能转但换不了布局」的老平台别以为是同一回事
- 公开仓库各平台 easyui 可用版本（`package_catalog.json` / `flythings_package_search`）：f136 2.10.0/2.9.0；f133 2.9.0/2.8.0/2.7.0/2.3.0；v85x 2.9.0/2.3.0/2.2.0；z20 3.0.0/2.6.0/2.2.0；z21 2.6.0/2.2.0；t113 2.6.0/2.5.0/2.2.0
- **平台没有 ≥2.9.0 的 easyui（z20/z21/t113 现状）→ 找 FlyThings 厂家（中科世为）要带 `relayout` 的 EasyUI 版本**，不要在业务代码里模拟（自绘旋转/整页重开 Activity 是另一回事，体验与资源都差）

### 4.1 同一判定法用于其它能力：`scrollwindow`（2026-09-27 核实：**不是版本问题**）

> 检索词：**scrollwindow 不显示 / 控件看不到 / 控件没渲染 / 页面只有标题 / 某版本不支持某控件 /
> 编译期头版本 vs 设备运行库 / ro.easyui.version / strings libeasyui.so**。

上表只 grep `include/` 是不够的（**控件类由设备运行库提供**，工程只编头）。完整三步：

| 步 | 看什么 | 怎么做 |
|---|---|---|
| ① 工程**编译期**解析版本 | `Manifest.xml` 写的是范围（如 `easyui ^2.2.0`），真版本在锁文件 | `<工程>/.deps.lock` 的 `"revision"`；实用 include 路径见 `.fun/<平台>/build.ninja` 的 `-I.../registry/public/<平台>/easyui/<版本>/include` |
| ② registry 里**有没有这个类** | 逐版本 grep `include/` | `grep -rl ZKScrollWindow <registry>/<平台>/easyui/*/include/` |
| ③ 设备**运行库**有没有 | `getprop ro.easyui.version` + pull 运行库看符号 | `adb pull /lib/libeasyui.so` → 在 PC 上 `strings`/正则扫 `ZKScrollWindow` 与 `_ControlFactory_ZKScrollWindow::create` |

**Z20 实测结果（2026-09-27）**：registry **2.6.0 / 3.0.0 都有** `window/ZKScrollWindow.h`
（2.6.0 = 1317 B，API 更全：`setScrollbarColor`/`moveTo`/`setScrollStep`/`setMoveCheckTimeThreshold`；
3.0.0 = 716 B 是**裁剪版**）；设备 `/lib/libeasyui.so`（822,656 B）含 **40 个 `ZKScrollWindow*` 符号**
（含 `_ControlFactory_ZKScrollWindow::create`）→ 运行期真能创建。
**⇒「某版本不支持 `scrollwindow`」不成立**，别往这个方向查。

**反向交叉验证（证明这套判定有效）**：同一份设备库 **有** `ConfigManager::setScreenRotate/setTouchRotate/getScreenRotate`、
**没有** `relayout` —— 与上表「`relayout` 需 ≥ 2.9.0，Z20 无」完全吻合。

**「控件看不到 / 页面只有标题」排查顺序**（按命中率）：
1. 设备加载的是**哪一份** lib/ui（`/tmp` > `/mnt/extsd` > `/res`，SD 卡可劫持）
   → `devflow/package-properties-easyui-cfg.md` 的「查找优先级」节；
2. 产物有没有同步（改 `ui/*.json` 必须立即 `fui pack` 出 ftu；`fun pack` 会把旧 ftu 回写成 json）
   → `devflow/ftu-json-pipeline.md`；
3. 能力/类**存不存在**（上述三步，本例已证伪）；
4. 控件结构与字段（`scrollwindow` 只装 `window`；内容高 > 视口才滚；固定件放外面；`touchable`）
   → `uicontrols/scroll-drag-interaction-spec.md`；
5. 可见性/启动态（`visible:false`、被上层装饰层盖住、`getprop sys.zkapp.state` 不是 `running`）。

## 5. 本机编译实测（RelayoutDemo + 当前 fun 工具链；CLI 更名见 `devflow/cli-fun-toolchain.md`）

踩了两个坑，都不在旋转本身：

1. **缺 `base-utility` 包**：新生成器产出的 `.fun/<平台>/generated/event_dispatcher.h` 里 `#include <base/functional.h>`，而 easyui 2.9.0 的依赖图里没有这个头 → 该头属于**独立包 `base-utility`**（`registry/public/{f133,v85x,z20}/base-utility/*/include/base/functional.h`）。
   修法：`Manifest.xml` 追加 `<package id="base-utility" version="10.10.2"/>` → **`fun install`**（刷新 `.deps.lock`，**不 install 新包 include 路径不进生成的 CMake，加了也白加**）
2. **构建宏改名**：老逻辑文件头写的是 `#ifdef FUSE_BUILD`，而 `fun build` 定义的宏是 **`FUN_BUILD`** → 那段被跳过 → `GENERATED_UI_DEFINITIONS`/`INIT_UI_EVENT_BINDINGS` 没进来 → 满屏 `'LOGD_TRACE' was not declared`、`'ZKButton' was not declared`、`'Intent' does not name a type`。
   修法一行：`#ifdef FUSE_BUILD` → `#if defined(FUSE_BUILD) || defined(FUN_BUILD)`

两处都改完：`fun build -p F133` 通过，产出 `libzkgui.so`（251KB，链接期 `relayout` 符号由 libeasyui.so 解析成功）。

## 6. 落地检查清单

1. 目标平台 easyui ≥ 2.9.0（没有就找厂家要；Manifest 里改版本 → `fun install` 拉包）
2. 先做一版布局，另一方向**复制后只改布局，控件 ID 保持一一对应**（ID 变了 relayout 后指针失效，等于白切）
3. `relayout` 参数是 **ftu 文件名**（含 `.ftu` 后缀），不是 json、不是 Activity 名
4. 备方向 ftu 的工程约定（RelayoutDemo 用 `*_p.ftu` + `ignore.ftu.regex=*_p.ftu`）
5. 切换后的尺寸相关收尾（列表刷新、重排）放 relayout 之后 / `onUI_show` 判方向
6. 真机验收：两个方向各抓一帧 `flythings_device_screenshot`，再 `flythings_ui_visual(action="diff")` 做像素比对

## 7. 未验证 / 待办

- 本轮只做**代码 + 版本 + 编译**核对，**未在真机上跑通 demo**（要真机证据：`flythings_build_ui_flow` + `device_screenshot`）
- z20 3.0.0 是否存在**其它名字**的等价「运行时换布局」能力，未找到（BaseApp/EasyUIContext 头文件里没有 → 倾向没有）
- easyui 2.9.0 与「新版生成器（event_dispatcher 那一代）」是否官方配套：F133 公开包最高 2.9.0，但生成器已经是新的一代 → 这套组合大概率要靠厂家发的新 easyui 才顺（当前用 base-utility 兜住了 base/functional.h，其它缺口未继续深挖）
