---
id: devflow-flow-index
title: 开发流程索引（场景 × 动作两条轴，由 flow_spec.json 派生）
category: devflow
status: review
confidence: manual
verified_at: 2026-10-03
stale_days: 180
origin: derived
source: 由 flow_spec.json 派生（scripts/gen_flow_doc.py）
needs_evidence: false
platforms: []
tags: [开发流程, 场景, 从零做界面, 设计稿转界面, 框架迁移, 改已有工程, 分辨率适配, 编译部署, UI 验收, 依赖包, 步骤顺序, 铁律]
evidence:
  - cmd: python scripts/gen_flow_doc.py --check
    expect: rc=0（本页与 flow_spec.json 一致）
---
# 开发流程索引（由 flow_spec.json 派生）

> ⚙️ **本页是派生物，不要手改**（由 `flow_spec.json` 派生，`--check` 进闸门）。
> 口语问法直达：从零做个界面 / 我想做个面板 / 怎么开始 / 设计稿怎么变界面 / 原型转 json / 还原度 / LVGL 迁过来 / 换框架 / 控件对应关系 / 改已有工程 / 加个按钮 / 换个配色 / 适配面板分辨率该走什么流程 / 换块屏怎么改 / 编译部署流程 / 上机顺序 / 做完怎么验收。

「该走哪条流程」有两个入口：**按场景**（用户带了什么来）和**按动作**（要做哪件事）。两条轴穿过同一批步骤 —— 所以下面步骤库里的一段，几条流程都会引用。

## 1. 场景轴（用户带着什么进来）

### 场景① 从想法到上机

- **什么时候用**：只有需求、还没有工程
- **走哪些步**：先把三个参数定下来（别猜） → 找相近模式（先查再画，省一轮返工） → 写码前必读规范（不能跳） → 建工程 → 先出预览稿让用户点头 → 写 ui/*.json → 补回调桩 → 再填业务 → 打包 → 编译部署到真机 → 抓真机屏幕 → 像素验收（还原度闭环）
- **口语触发**：做个界面 / 从零做个项目 / 我想做个面板 / 帮我起个新项目 / 做个智能开关
- **做完的标志**：上机抓屏有内容、`launched=true`，且与预览稿 / 设计稿 diff 通过（验收三样：`launched` + logcat `onUI_show` + 抓屏 md5 与前次不同）

### 场景② 设计稿 → 工程 UI

- **什么时候用**：手上有原型 / 设计稿
- **走哪些步**：先判形态（决定走哪条路） → 建工程 → HTML 原型 → ui json → 写 ui/*.json → 三道核对（改完必跑） → 先出预览稿让用户点头 → 打包 → 编译部署到真机 → 抓真机屏幕 → 像素验收（还原度闭环）
- **口语触发**：把这个原型做成界面 / 还原这个设计稿 / 设计稿转 json / Figma 稿子落地
- **做完的标志**：`ui_visual diff` 的差异清单收敛（或差异区已逐条解释），且改完重 pack 后抓屏确认

### 场景③ 从别的框架迁移

- **什么时候用**：源码来自别的框架
- **走哪些步**：先查控件对应关系（别一边翻一边猜） → 源码 → ui json（自动翻译） → 写码前必读规范（不能跳） → 建工程 → 补回调桩 → 再填业务 → 检索包生态 → 写 Manifest → 打包 → 编译部署到真机 → 抓真机屏幕 → 像素验收（还原度闭环） → 自动化回归
- **口语触发**：LVGL 工程迁过来 / 把这个控件对应过来 / 换个框架 / 从 Qt 搬过来
- **做完的标志**：`downgrades` / `unrecognized` 全部逐条处置完毕，且上机抓屏与源界面结构一致

### 场景④ 改已有工程（换皮 → 换功能）

- **什么时候用**：已有 FlyThings 工程要改
- **走哪些步**：先摸清现状（别凭文件名猜） → 改 UI → 补回调桩 → 再填业务 → 三道核对（改完必跑） → 打包 → 编译部署到真机 → 抓真机屏幕 → 像素验收（还原度闭环）
- **口语触发**：这个界面改一下 / 加个按钮 / 客户要换个配色 / 加个页面 / 在现有项目上加功能
- **做完的标志**：改前 / 改后抓屏能看出预期变化，三道核对全过，且原有功能回归通过

### 场景⑤ 分辨率适配（设计 ≠ 面板）

- **什么时候用**：面板与设计不一致
- **走哪些步**：先体检，拿判据（别先动手） → 比例相同 / 接近 → 等比换算（机械活，别手工算） → 比例不同 → 重排布局（判断活） → 打包 → 编译部署到真机 → 抓真机屏幕 → 像素验收（还原度闭环）
- **口语触发**：屏和设计分辨率不一样 / 屏比设计小 / 界面显示不全 / 适配这块面板 / 换块屏
- **做完的标志**：再跑一次 `flythings_device_preflight` 落回 `push`（自封闭、不反复放大），且抓屏与设计稿比对通过

## 2. 动作轴（要做哪件事）

| 动作 | 走哪些步 | 口语触发 |
|---|---|---|
| **新建 FlyThings 工程** | 建工程 → 找相近模式（先查再画，省一轮返工） → HTML 原型 → ui json → 先出预览稿让用户点头 → 打包 → 编译部署到真机 | 新建工程 / 建个项目 / 从零做个工程 / 起个项目 |
| **HTML 原型 → UI 布局** | 找相近模式（先查再画，省一轮返工） → HTML 原型 → ui json → 先出预览稿让用户点头 → 三道核对（改完必跑） → 打包 | 原型转界面 / 设计稿转 json / HTML 转 json / 把原型做成界面 |
| **UI 验收（预览 → 真机 → 像素）** | 三道核对（改完必跑） → 先出预览稿让用户点头 → 抓真机屏幕 → 像素验收（还原度闭环） | 验收界面 / 看看做得对不对 / 界面还原度 / 渲染和稿子像不像 |
| **编译部署到真机调试** | 编译部署到真机 → 抓真机屏幕 → 无画面 / 黑屏排查 → 多语言 | 部署到设备 / 推到设备上跑 / 上机调试 / 黑屏没画面 |
| **依赖包与 Manifest** | 检索包生态 → 看包内 API → 写 Manifest → 解析依赖 + 核对声明 | 加个包 / 要个库 / 依赖怎么配 / Manifest 怎么写 |

## 3. 步骤库（两条轴共用）

| 步骤 | 主要 op | 闸门 | 做什么 |
|---|---|---|---|
| 先把三个参数定下来（别猜） | `flythings_hardware_info` | 前置条件 | 平台：用户说型号 → `flythings_hardware_info(model=…)` 拿 preset；只说平台 → `flythings_hardware_info(platform=…)` |
| 找相近模式（先查再画，省一轮返工） | `flythings_knowledge_search` | — | `flythings_knowledge_search(query="温控面板 布局")`、`flythings_knowledge_search(query="仪表盘 控件")` |
| 写码前必读规范（不能跳） | `flythings_get_project_spec` | 前置条件 | `flythings_get_project_spec()` —— 目录规则 + 生成规则 + 注意事项 |
| 先判形态（决定走哪条路） | （人判断） | — | **HTML 原型**（可交互、有 CSS）→ `flythings_html_to_json`，确定性转换，**首选** |
| HTML 原型 → ui json | `flythings_html_to_json` | 前置条件 | `flythings_html_to_json(input_html="<HTML 文件路径>", output_json="<目标工程>/ui/main.json")` |
| 建工程 | `flythings_create_project` | 前置条件 | `flythings_create_project(project_root="…", platform="Z20", resolution="1024x600")` |
| 先出预览稿让用户点头 | `flythings_ui_preview` | 需用户确认 | 排版稿：`flythings_ui_preview(target="<项目>")` → HTML 预览（只交 html，不产图片） |
| 写 ui/*.json | `flythings_ui_schema` | — | 字段 / 必填键 / 默认值：`flythings_ui_schema(control_type="seekbar")` —— **唯一真源**，不要凭记忆写 |
| 三道核对（改完必跑） | `flythings_layout_audit` | 前置条件 | `flythings_validate_project(project_root=…)` —— 规范体检 → errors / warnings |
| 补回调桩 → 再填业务 | `flythings_gen_logic_stub` | — | `flythings_gen_logic_stub(project_root=…)` —— 读 `ui/*.json` 的控件表 → 补齐回调桩（**只补不改**，已有同名函数一律跳过） |
| 先摸清现状（别凭文件名猜） | `flythings_read_json` | — | `flythings_read_json(json_path="<项目>/ui/main.json")` —— 分辨率、控件列表、caption → id 映射 |
| 改 UI | `flythings_edit_ftu` | — | 控件属性 / 坐标（源码级）→ 直接改 `ui/*.json`，字段口径查 `flythings_ui_schema(control_type=…)` |
| 先查控件对应关系（别一边翻一边猜） | `flythings_map_control` | — | `flythings_map_control(query="lv_slider")`；限定源框架 `flythings_map_control(query="QCalendarWidget", source="qt")` |
| 源码 → ui json（自动翻译） | `flythings_translate_ui` | — | `flythings_translate_ui(source="<.c 路径或内联源码>", out="<项目>/ui/main.json", res="<工程分辨率>")` |
| 检索包生态 | `flythings_package_search` | — | `flythings_package_search(keyword="mqtt")` —— **有包用包，禁止手写协议栈 / 库** |
| 看包内 API | `flythings_get_package_api` | — | `flythings_get_package_api(...)` —— 包头文件级 API（**只认头文件，禁猜、禁反编译**） |
| 写 Manifest | `flythings_manifest` | — | `flythings_manifest(project_root=…)` —— 默认**只推荐不写盘**（dry_run），确认后再写 Manifest.xml |
| 解析依赖 + 核对声明 | `flythings_resolve_dependencies` | — | `flythings_resolve_dependencies(packages="<包名>", platform="<平台>")` —— 递归解析 + 冲突 / 循环检查 |
| 先体检，拿判据（别先动手） | `flythings_device_preflight` | — | `flythings_device_preflight(project_root="<项目>", device="<serial|IP>")` —— 返回里直接给结论 |
| 比例相同 / 接近 → 等比换算（机械活，别手工算） | `flythings_device_preflight` | 需用户确认 | `flythings_device_preflight(project_root="<项目>", device="<serial>", adapt="force")` —— 用户已确认要按面板改 |
| 比例不同 → 重排布局（判断活） | `flythings_edit_ftu` | 需用户确认 | **算清两个比例差多少**：`sx = 面板宽/设计宽`、`sy = 面板高/设计高`；差距小（如 1280×750 → 1280×800）常只需**改画布高**（只改 `resolution.height` 与根 `position.height`，控件全绝对定位、位置不动） |
| 打包 | `flythings_fui_pack` | — | `flythings_fui_pack(json_path="<项目>/ui/main.json")` —— json → ftu（设备实际加载 ftu） |
| 编译部署到真机 | `flythings_build_ui_flow` | 不可逆操作 | `flythings_build_ui_flow(project_root=…, device="<IP>:5555")` —— 编译 + 推送 + 运行 |
| 抓真机屏幕 | `flythings_device_screenshot` | — | `flythings_device_screenshot(device=…)` —— 方向 `rotate='auto'`（按工程 `rotateScreen`） |
| 像素验收（还原度闭环） | `flythings_ui_visual` | — | `flythings_ui_visual(action="diff", ...)` —— 0 token 差异清单；**只看差异区小图给视觉模型**，别丢整屏原图 |
| 无画面 / 黑屏排查 | （人判断） | — | 顺序：**先日志**（事件到没到控件 / 回调进没进）**再像素**（抓帧要按 pan 取当前页） |
| 自动化回归 | `flythings_gen_ui_test` | — | `flythings_gen_ui_test(project_root=…)` 生成遍历 / 压测工程 |
| 整机自检 | `flythings_selfcheck` | — | `flythings_selfcheck(device=…)` —— 十一分区快照 |
| 问题记录 | `flythings_bugreport` | — | `flythings_bugreport(...)` —— 把现象 / 复现 / 证据整理成问题单 |
| 交付随项目带工具 | `flythings_attach_cli_tools` | — | `flythings_attach_cli_tools(project_root=…)` —— 复制 fui / fun 到项目（对方不装 MCP 也能编译） |
| 多语言 | `flythings_i18n_refactor` | — | `flythings_i18n_refactor`（写死文案抽 @key）→ `flythings_i18n_export` → 翻译 → `flythings_i18n_import` → `flythings_i18n_to_json` |

## 4. 跨流程铁律（去重后只此一份）

| 不变量 | 规则 | 违反的后果 |
|---|---|---|
| `src-activity-readonly` | `src/activity/` 由 IDE 按 ftu 生成、**禁手改**；业务只写 `src/logic/*.cc` | 手改会在下次生成时被覆盖，白写 |
| `image-size-eq-box` | 图片尺寸必须 == 控件盒；换图后必跑 `flythings_verify_assets` | 图 != 盒 时引擎拉伸填充且**不报错**，属静默质量缺陷 |
| `json-pack-then-launch` | 改 json → 必 `flythings_fui_pack` → 再 launch → 再抓屏；四步不许跳 | 设备加载的是 ftu 不是 json，不 pack 就是「改了像没改」 |
| `platform-consistency` | 平台 / 架构 / libc / 包键**四者一致**（ARM 与 RISC-V64 二进制不通用；Z20/Z21=glibc，其余=musl） | 任一处错配 → 链接失败或运行时崩溃，且现象离根因很远 |
| `schema-before-write` | 写 json 字段前查 `flythings_ui_schema`，**不凭记忆填** | 字段名/必填键/默认值以 schema 为唯一真源；错字段会加载异常 |
| `callback-name-by-caption` | 回调名按 **caption** 拼（`on<Event>_<Caption>`）；`listview` 的 count/data/click **三条成组** | caption 改了没补桩 → 点了没反应；三回调缺一条 → 列表空白 |
| `no-selfmade-commands` | 口语「编译 / 构建 / 调试 / 部署 / 推设备 / 跑一下」**一律** `flythings_build_ui_flow`，不自造命令、不自写 push 脚本 | 自造命令会绕过 pack / 设备探测 / 日志清理，产出的现象不可信 |
| `dry-run-and-confirm` | 写操作默认 dry_run / 不推真机；pack 与推真机必须显式确认后传参 | 误推会污染真机现场，且覆盖掉可用于对比的旧画面 |

## 5. 工程状态位（跨会话「做到哪了」）

| 状态位 | 由哪步写入 | 挡住哪步 | 含义 |
|---|---|---|---|
| `paramsDecided` | clarify-params | create-project | 平台 / 分辨率 / 交互三项已由用户明确 |
| `projectCreated` | create-project | write-ui-json | 工程骨架已生成（含平台 / 分辨率替换） |
| `designConfirmed` | preview | gen-logic-stub | 用户确认过版式预览稿 |
| `uiWritten` | write-ui-json | pack | ui/*.json 已写完并通过三道核对 |
| `stubsGenerated` | gen-logic-stub | — | 回调桩已补齐（只补不改，可反复跑） |
| `packed` | pack | launch | ftu 已按当前 json 重新生成 |
| `launched` | launch | screenshot | 已推送到设备并成功启动 |
| `screenshotTaken` | screenshot | visual-diff | 已有本机当次画面（不是旧图） |
| `verified` | visual-diff | — | 像素验收通过（或差异已逐条解释） |

