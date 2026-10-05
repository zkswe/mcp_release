---
name: flythings-new-project
description: 新建 FlyThings 工程（老框架：ui/*.json + ftu + Eclipse 工程文件）的强制流程。用户说「新建工程 / 建个项目 / 起个新项目 / 从零开始 / 建 FlyThings 工程」时加载。先出设计稿让用户确认、平台与分辨率必须问用户，再调 flythings_create_project；顺序错了就是返工。
---

# 新建 FlyThings 工程

## 为什么需要这份流程

FlyThings 的模型先验知识 ≈ 0（自研 EasyUI，不是 LVGL/Qt/Android），所以**建工程这一步的判断必须来自本仓**，
不能按别的框架类推。历史返工全部集中在两件事：**没先确认设计稿就开建**、**平台/分辨率靠猜**。

## 硬闸门（先过这三条，再动手）

1. **平台必须问用户**：支持项用 op 取（`flythings_create_project` 的报错里会列全），**禁止猜、禁止用默认值**。
   常见：`V85X` / `Z20` / `Z21` / `T113` / `F133` / `F135` / `Z235X`。
2. **分辨率必须问用户**（如 `800x480`、`480x272`）。分辨率写错，界面全歪，且**不是**改一个数字就能修好
   （json 坐标是绝对值，要重排）。
3. **先出设计稿/原型让用户确认**再建工程。用户只说「做个 XX」时，走 `knowledge/devflow/prototype-flow.md`
   的流程（一句话需求 → 线框确认 → UI 美化）。跳过确认 = 返工。

## 步骤

### ① 确认范围与技术栈定位

- 定位口径：FlyThings = **Linux 基座**（基线同 buildroot/OpenWrt，**不是** MCU/ESP32 SDK），
  UI 是**自研 EasyUI**（**不是** LVGL）。详见 `flythings-os-positioning.md`。
  这条决定"能不能做某件事"的判断基线 —— 别按单片机的资源模型或 LVGL 的 API 类推。
- 屏数按设计稿定：**多屏 = N 屏全部落地**，不能只做一屏。

### ② 查要用的库/控件是否已有

建工程前先查，别自己造轮子：

| 要什么 | 怎么查 |
|---|---|
| 别的框架的某个控件 → 我们对应哪个 | op `flythings_map_control`（六个源框架 213 条映射，带**可直接粘进 json 的片段**） |
| 自研组件（日历/图表/黑胶/BLE…） | `components/` 下各组件 `README.md` + `platforms.md`；总目录 `knowledge/components/components-catalog.md` |
| 厂家依赖包（easyui/zknet/mqtt…） | `packages/<包名>/README.md`（装法 + API 速查 + 最小示例 + **真机实测的坑**） |
| 真缺（映射与组件都没有） | `components/ui_v1/gap-list.md` 的缺口编号（G-01~G-36），再决定自研 |

> 用库的完整流程见 skill `flythings-use-library`。

### ③ 建工程

```
flythings_create_project(project_root, platform, resolution, app_name='')
```

- `project_root` 给**完整路径**（目录可不存在，会创建；非空目录会被拒，防误覆盖）。
- `app_name` 缺省取目录名。**工程名会同时写进 `.project` / `.cproject`** ——
  这两个文件里可能残留模板的旧名（实测 `HelloWord_T113` 模板里写的是 `HelloWord_T113Nor`），
  工具会按**文件内容**读出真实旧名再改（不是按目录名），这条已有回归测试守着，别绕过工具手改。
- 产出是老框架结构：`ui/*.json`（+ `ui/*.ftu`）、`src/logic/*.cc`、`Manifest.xml`、`fun.json`、
  `.project`/`.cproject`（Eclipse 工程文件，IDE 用）。

> ⚠️ `fun create` 能生成 **fv 新框架**（`fsc.json` + `app/**/*.fv`），但**本 MCP 不服务 fv**：
> 其格式与细节我们没有资料，别去用它、也别按猜的写。建工程只走上面这条。

### ④ 建完立刻自检

1. **编译**：`fun build`（或 `fun.exe build`；**这不是 MCP op，是命令行**）返回 0；
2. **依赖**：op `flythings_check_project_deps` 比对 include 与 Manifest 声明；
3. **设备体检**：op `flythings_device_preflight`（字库覆盖 / 体积 / 能力）；
4. 真机跑起来看界面 —— 判据见 skill `flythings-device-acceptance`。

### ⑤ 在 `src/logic/<页>Logic.cc` 里写页面逻辑（**桩只是骨架**）

`fun build` 生成的 logic 文件里带 `INIT_UI_EVENT_BINDINGS`、生命周期钩子与**空回调桩**；
**交互逻辑写在同一个文件里**，这一步不做 = 界面在、点上去没反应：

- 回调里做「控件 ↔ 业务」关联：`setText` / `refreshListView` / `setXxxListener` / 调业务对象。
  桩体留着 `(void)x;` / `return false;` 就打包上机，**真机表现和「回调没生成」一模一样**。
- 复杂功能写成 `src/<业务域>/*.cpp` + `.h`（如 `src/network/NetworkManager.cpp`），在 logic 里 include 调用；
  **新增代码禁建 `.cc`** —— `.cc` 是按页面生成的 logic 专属（`src/logic/*.cc` 之外手写的 `.cc` 不被编译）。
- 容器 / 显示类控件（pagewindow、scrollwindow、textview、painter…）**没有回调桩** → 在 `onUI_init` 里
  `findControlByID` 取指针 + `setXxxListener` / `setPageChangeListener` 接线，别当成漏生成。
- 回调名按 caption 拼（`on<事件>_<Caption>`）：caption 改过名要重跑 `fun build`（或 op `flythings_gen_logic_stub` 体检）。
- 写完再打包上机：`fui pack` → `fun build` → `fun launch`。缺哪些桩可用
  `flythings_gen_logic_stub(project_root=…, dry_run=true)` 先看清单。

> 完整判据 / 反例在流程步骤 `write-logic`（真源 `flow_spec.json`）；`flythings_project_state` 会把它报成下一步。

## 产出后必须遵守的约定

- `src/activity/` 由 ftu 生成，**禁建/禁改/禁覆盖**；页面逻辑写 `src/logic/<页>Logic.cc`，
  复杂功能写成 `src/<业务域>/*.cpp` + `.h`（新增代码**禁建 `.cc`**）。
- 控件指针/ID 宏由编译期生成，`logic.cc` 直接用 `mXXXPtr`，**禁止手写定义**。
- `logic.cc` 必须保留 `REGISTER_ACTIVITY_TIMER_TAB`（空表也行）。
- `src/uart/` 是系统模板：只改 `ProtocolData.h` / `ProtocolParser.cpp` 的协议解析。
- `ui/` 放 json + ftu，用 `fui pack` 生成 ftu（`fui.exe` 已随工程附带）。
- 交付方式：`fun.exe build` + `fun.exe launch`，**不需要**客户导入 IDE。

## 常见错法（都真发生过）

| 错法 | 后果 |
|---|---|
| 没问平台/分辨率就开建 | 建出来的工程不能用，全部返工 |
| 按 LVGL/Qt 的控件模型写 json | 字段名/回调语义全不对，真机不生效 |
| 手改 `.cproject` 的 Builder ID | **IDE 编译无任何输出**（CDT Build Console 空白） |
| 往 `src/activity/` 里写代码 | 下次 ftu 生成时被覆盖 |
| 只按目录名替换工程名 | 残留模板旧名（如 `...Nor` 尾巴） |
