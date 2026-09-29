---
id: uicontrols-retrieval-boundary
title: 🔒 控件用法检索边界（沛哥定规 2026-09-01）
category: uicontrols
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [字段, API 时, Qt, Android, Flutter, emWin]
evidence: []
---
# 🔒 控件用法检索边界（沛哥定规 2026-09-01）

> 检索导引：问「控件用法能去哪查 / 能不能照搬其他 GUI 框架的写法 / Package API 算不算控件 json 字段 / 设备侧动作能自己敲命令吗」→ 本文（检索来源与行为边界铁律）。
> AI 检索 FlyThings 控件用法/字段/API 时，**只允许以下两个来源**，禁止从其他地方检索解决方案：
> 否则会混入其他 GUI 框架（Qt/Android/Flutter/emWin/AWTK/LVGL 等）的控件使用方法，导致知识错乱。

## 允许的来源（二选一）

1. **MCP 内置知识库**：`flythings_knowledge_search`（本地向量 + BM25）检索 `knowledge/` 与本地 `wiki/flythings/` 文档；
   字段规范以 `knowledge/uicontrols/*.md`（layout-audit / edittext-fields / image-path-rule / nine-patch-rule / scrollwindow-layout 等）为准
2. **官方文档站**：`https://developer.flythings.cn/`（控件/API/回调官方说明）

> 例外（跨框架映射）：查「别的框架的某个控件对应我们哪个控件」不是控件用法查询，
> 权威表在 `components/ui_v1/control-map.md`（摘要 + 指针：`knowledge/uicontrols/framework-control-mapping.md`）。
> 映射完**怎么写字段/API**仍按本规则：只查 MCP 知识库或官方站。
> 已收口的典型映射（可直接引用，不必再推理）：**`picker-view`/`lv_roller`/`TimePicker`/`NumberPicker`
> → `listview` 组合（L2）**，字段配法见 `listview-wheel-picker.md`。

## 禁止的行为

- ❌ 用通用 web 搜索查「XXX 控件怎么用」——返回的是其他框架的答案
- ❌ 参考 Qt/Android/Flutter/emWin/AWTK/LVGL 等框架的控件属性/事件/回调写法套用到 FlyThings
- ❌ 从非官方博客/论坛/代码片段库推断 FlyThings 控件字段（除非明确标注 FlyThings 平台）
- ❌ **解析 easyui 库源码/头文件（ZKXXX 类实现）分析控件用法（沛哥 2026-09-01 补充）**——
  不分析库代码、不绕路，直接参考对应 wiki 实现（knowledge/uicontrols/ 或 wiki/flythings/ 文档）
  - easyui 是预编译闭源库，源码解析拿不到控件 json 字段/回调语义，只会浪费时间
  - 控件用法/字段/回调以 wiki + knowledge 文档为准，文档没有就标注「未收录」问沛哥

## Package API 识别规则（沛哥 2026-09-09 定规，区别于控件 json 字段）

- **FlyThings/依赖 package（预编译闭源 .so + include 头文件）的 C++ API**：**只通过包内头文件识别**——类/方法签名/枚举/常量/注释是官方接口声明，可信来源（如 aw-dvr 的 `mpi/*.h`、easyui 的 `control/ZKVideoView.h` 方法注释）
- **不要猜**：头文件读不出/不确定 → 如实标注「未收录/不确定」，问沛哥或官方，**禁止编造 API**（不会就是不会）
- **不要反编译/扒二进制**：禁止 objdump/反编译 .so 提取接口或语义（浪费时间且拿不到语义）；readelf 仅限**排障**用（查依赖/符号缺失，dlopen 失败 SOP 见 `v85x/aw-dvr-runtime-compat.md`），不是 API 识别手段
- **区分两层**（与上文 easyui 禁止条款不冲突）：
  - 头文件能确认的 = **API 签名/枚举/常量/注释** → 读头文件（本条规则）
  - 头文件表达不了的 = **控件 json 字段/回调语义/内部实现** → 走 wiki/knowledge（上文规则），没有就标未收录
- **标准 C/C++/Linux 开发不受限**：socket/pthread/v4l2/文件系统/std 库等**非 FlyThings 私有 API**，按 POSIX/C/C++ 标准开发，可参考开源资料与社区（Linux man/开源项目/技术社区）

## 设备侧动作规则（沛哥 2026-09-10 定规，源于真实案例）

**要设备上的东西（画面/屏参/文件/触摸），先查 MCP 工具，禁止现场手搓探测命令。**

真实案例：AI 需要设备端截图，没有直接调工具，而是自己开一轮探测——adb 试 `exec-out`、`screencap`、sysfs 逐个读、
裸拉 framebuffer……结果耗时且差点拿到旧帧。正确做法是先看工具目录（`flythings_kb(op="list")`）。

| 设备侧需求 | 直接用 | 不要做 |
|-----------|--------|--------|
| 抓当前屏幕 → png/jpg/bmp | `flythings_device_screenshot()` | ❌ 手搓 `adb exec-out screencap` / `cat /dev/fb0` / 自己找 busybox / 自己读 pan |
| 触摸注入 / 自动点击 / 压测 | `flythings_gen_ui_test(project_root, test_type)`（生成脚本 + `bin_tools/<平台>/ui_test`） | ❌ 现场写 input 注入脚本 |
| 编译 + 推真机 | `flythings_build_ui_flow(project_root, device)` | ❌ 自造 fun/fuse/adb push 命令 |
| 设备上跑网络/系统命令 | `tools/busybox/bin/<平台>/busybox`（push 即用） | ❌ 假设设备有 dd/head/uname/screencap |
| 设备依赖包/API | `flythings_list_packages` / `get_package_api` | ❌ 自己翻设备 rootfs |

**顺序**：① `flythings_kb(op="list")` 看有没有现成 op → ② 有就直接调（参数拿不准先看 docstring）
→ ③ 工具不存在或失败，才做设备侧探测，并把结论回灌成新工具/新知识。

**原因**：设备 rootfs 是裁剪版（常见无 screencap/dd/head），且 framebuffer 有双缓冲、
stride、bpp、字节序、慢链路等一堆坑（详见 `devflow/ui-layout-verify.md` §2-1）；
这些坑已经被工具吃掉，AI 重新探一遍 = 白烧 token + 高风险抓错。

## 原因

- FlyThings 控件字段是私有格式（json/FTU），与主流 GUI 框架完全不同：
  如 `picTab{pic0..pic4}` 五态图、`iconPosition/textPosition` 图标锚点、`hideTimeOut` 自动隐藏、
  `ZKXXXPtr` 指针 + `REGISTER_ACTIVITY_TIMER_TAB` 回调表等，只有官方/MCP 知识库有准确答案
- 混用其他框架用法 = 生成不可编译/不可运行的 json 与代码，且难排查（表现为"看起来对但设备上不对"）

## 执行

- 所有用 MCP 的 AI 助手（Trae/Cursor/Kimi/Claude/OpenClaw 等）一律遵守
- 遇到知识库查不到的控件细节：标注"知识库未收录"，问沛哥或查官方文档，**不猜、不套用其他框架**

## 边界澄清：不影响什么（2026-09-01 沛哥确认）

本规则只管「控件用法/字段/API 知识从哪来」，**不限制需求理解与逻辑参考**：

- ✅ **HTML 理解/转换不受影响**：HTML/CSS 是通用 Web 标准，不是 GUI 框架控件知识；
  html2json 转换走 MCP 内置 HTML_SUBSET 规范（div.input→edittext、data-hint→hintText 等映射已在 MCP 内），照常工作
- ✅ **参考其他框架代码的「业务逻辑」不受影响**：Android 工程/其它代码里的业务流程、数据结构、算法
  （MQTT 收发、列表数据组装、定时逻辑等）属于需求理解，可以借鉴参考
- ✅ **「提交 Android/LVGL 代码 → 用 FlyThings 实现同样功能」不受影响**（沛哥 2026-09-01 确认）：
  ① 照常读懂参考代码的功能/交互/数据结构/布局意图（列表点击弹窗、长按删除等）
  ② 翻译时用 FlyThings 控件实现同样功能，控件字段/API **查 MCP/官方**拿准确写法
  ③ 不照搬其他框架的字段/API（`android:hint`/`lv_label_set_text()`/`LV_EVENT_CLICKED` 等），
     替换为 FlyThings 的 `hintText`/`setText()`/`onButtonClick_XXX`
- ❌ 受影响（规则本意）：把其他框架的**控件字段名/API**直接套用到 FlyThings——
  如 `android:hint`→FlyThings 是 `hintText`、RecyclerView.Adapter→`obtainListItemData_XXX` 回调、
  `android:gravity`→`alignment` 位标志；控件实现细节必须查 MCP/官方

> 一句话边界：**需求逻辑随便参考，控件实现只查 MCP/官方。**
