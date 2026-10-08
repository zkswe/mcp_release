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
- **走哪些步**：先把三个参数定下来（别猜） → 找相近模式（先查再画，省一轮返工） → 写码前必读规范（不能跳） → 建工程 → 先出预览稿让用户点头 → 写 ui/*.json → 补回调桩（生成归 fsc build，本 op 是体检 / 兜底） → 在 logic 里写页面逻辑 → 打包 → 编译部署到真机 → 抓真机屏幕 → 像素验收（还原度闭环）
- **口语触发**：做个界面 / 从零做个项目 / 我想做个面板 / 帮我起个新项目 / 做个智能开关
- **做完的标志**：上机抓屏有内容、`launched=true`，且与预览稿 / 设计稿 diff 通过（验收三样：`launched` + logcat `onUI_show` + 抓屏 md5 与前次不同）

### 场景② 设计稿 → 工程 UI

- **什么时候用**：手上有原型 / 设计稿
- **走哪些步**：先判形态（决定走哪条路） → 建工程 → HTML 原型 → ui json → 写 ui/*.json → 三道核对（改完必跑） → 先出预览稿让用户点头 → 打包 → 编译部署到真机 → 抓真机屏幕 → 像素验收（还原度闭环）
- **口语触发**：把这个原型做成界面 / 还原这个设计稿 / 设计稿转 json / Figma 稿子落地
- **做完的标志**：`ui_visual diff` 的差异清单收敛（或差异区已逐条解释），且改完重 pack 后抓屏确认

### 场景③ 从别的框架迁移

- **什么时候用**：源码来自别的框架
- **走哪些步**：先查控件对应关系（别一边翻一边猜） → 源码 → ui json（自动翻译） → 写码前必读规范（不能跳） → 建工程 → 补回调桩（生成归 fsc build，本 op 是体检 / 兜底） → 在 logic 里写页面逻辑 → 检索包生态 → 写 Manifest → 打包 → 编译部署到真机 → 抓真机屏幕 → 像素验收（还原度闭环） → 自动化回归
- **口语触发**：LVGL 工程迁过来 / 把这个控件对应过来 / 换个框架 / 从 Qt 搬过来
- **做完的标志**：`downgrades` / `unrecognized` 全部逐条处置完毕，且上机抓屏与源界面结构一致

### 场景④ 改已有工程（换皮 → 换功能）

- **什么时候用**：已有 FlyThings 工程要改
- **走哪些步**：先摸清现状（别凭文件名猜） → 改 UI → 补回调桩（生成归 fsc build，本 op 是体检 / 兜底） → 在 logic 里写页面逻辑 → 三道核对（改完必跑） → 打包 → 编译部署到真机 → 抓真机屏幕 → 像素验收（还原度闭环）
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
| **新建 FlyThings 工程** | 建工程 → 找相近模式（先查再画，省一轮返工） → HTML 原型 → ui json → 先出预览稿让用户点头 → 在 logic 里写页面逻辑 → 打包 → 编译部署到真机 | 新建工程 / 建个项目 / 从零做个工程 / 起个项目 |
| **HTML 原型 → UI 布局** | 找相近模式（先查再画，省一轮返工） → HTML 原型 → ui json → 先出预览稿让用户点头 → 三道核对（改完必跑） → 在 logic 里写页面逻辑 → 打包 | 原型转界面 / 设计稿转 json / HTML 转 json / 把原型做成界面 |
| **UI 验收（预览 → 真机 → 像素）** | 三道核对（改完必跑） → 先出预览稿让用户点头 → 抓真机屏幕 → 像素验收（还原度闭环） | 验收界面 / 看看做得对不对 / 界面还原度 / 渲染和稿子像不像 |
| **编译部署到真机调试** | 编译部署到真机 → 抓真机屏幕 → 无画面 / 黑屏排查 → 多语言 | 部署到设备 / 推到设备上跑 / 上机调试 / 黑屏没画面 |
| **依赖包与 Manifest** | 检索包生态 → 看包内 API → 写 Manifest → 解析依赖 + 核对声明 | 加个包 / 要个库 / 依赖怎么配 / Manifest 怎么写 |

## 3. 步骤库（两条轴共用）

| 步骤 | 主要 op | 闸门 | 做什么 | 通过判据 |
|---|---|---|---|---|
| 先把三个参数定下来（别猜） | `flythings_hardware_info` | 前置条件 | 平台：用户说型号 → `flythings_hardware_info(model=…)` 拿 preset；只说平台 → `flythings_hardware_info(platform=…)` | 平台与分辨率都来自用户原话或型号库查询结果 |
| 找相近模式（先查再画，省一轮返工） | `flythings_knowledge_search` | — | `flythings_knowledge_search(query="温控面板 布局")`、`flythings_knowledge_search(query="仪表盘 控件")` | 命中相近布局/控件的现成结论，并记下用了哪页 |
| 写码前必读规范（不能跳） | `flythings_get_project_spec` | 前置条件 | `flythings_get_project_spec()` —— 目录规则 + 生成规则 + 注意事项 | 拿全目录规则 + 生成规则 + 注意事项 |
| 先判形态（决定走哪条路） | （人判断） | — | **HTML 原型**（可交互、有 CSS）→ `flythings_html_to_json`，确定性转换，**首选** | 四类形态之一被明确选中（HTML 原型 / Figma 导出的 HTML / 纯图片稿 / 仅参考风格） |
| HTML 原型 → ui json | `flythings_html_to_json` | 前置条件 | `flythings_html_to_json(input_html="<HTML 文件路径>", output_json="<目标工程>/ui/main.json")` | 转换成功：控件数 > 0、产物图片都在 `<项目>/resources/images/`、未识别项已登记 |
| 建工程 | `flythings_create_project` | 前置条件 | `flythings_create_project(project_root="…", platform="Z20", resolution="1024x600")` | 工程骨架齐全（package.properties / ui/ / resources/images/ / src/），分辨率与平台已写入 |
| 先出预览稿让用户点头 | `flythings_ui_preview` | 需用户确认 | 排版稿：`flythings_ui_preview(target="<项目>")` → HTML 预览（只交 html，不产图片） | 预览稿已交付且用户明确确认版式 |
| 写 ui/*.json | `flythings_ui_schema` | — | 字段 / 必填键 / 默认值：`flythings_ui_schema(control_type="seekbar")` —— **唯一真源**，不要凭记忆写 | 控件字段与必填键都来自 `ui_schema` 查询结果，json 可被 pack |
| 三道核对（改完必跑） | `flythings_layout_audit` | 前置条件 | `flythings_validate_project(project_root=…)` —— 规范体检 → errors / warnings | `validate_project` 无 errors 且 `layout_audit` 无遮挡/越界/触摸穿透 |
| 补回调桩（生成归 fsc build，本 op 是体检 / 兜底） | `flythings_gen_logic_stub` | — | `flythings_gen_logic_stub(project_root=…, dry_run=true)` —— 按 `ui/*.json` 的控件表**核对**该有哪些桩、缺哪些（只补不改，已有同名函数一律跳过） | 桩与 `ui/*.json` 控件一一对应，无缺、无重复生成 |
| 在 logic 里写页面逻辑 | （人判断） | 前置条件 | `src/logic/<页>Logic.cc` 是**页面逻辑的唯一落点**：在回调桩里写「控件 ↔ 业务」的关联（取指针 / 取值 / `setText` / `refreshListView` / `setXxxListener`），别只留桩体占位 | 该页交互控件在 `src/logic/<页>Logic.cc` 里有对应实现（桩体不再是占位）；容器 / 显示类控件已在代码侧接线 |
| 先摸清现状（别凭文件名猜） | `flythings_read_json` | — | `flythings_read_json(json_path="<项目>/ui/main.json")` —— 分辨率、控件列表、caption → id 映射 | 分辨率、控件清单、caption→id 映射三者都拿到 |
| 改 UI | `flythings_edit_ftu` | — | 控件属性 / 坐标（源码级）→ 直接改 `ui/*.json`，字段口径查 `flythings_ui_schema(control_type=…)` | 改完 json 后 ftu 已重新 pack，两者内容一致 |
| 先查控件对应关系（别一边翻一边猜） | `flythings_map_control` | — | `flythings_map_control(query="lv_slider")`；限定源框架 `flythings_map_control(query="QCalendarWidget", source="qt")` | 源控件对上目标控件，给出等价级别 L1~L5 与可粘贴片段 |
| 源码 → ui json（自动翻译） | `flythings_translate_ui` | — | `flythings_translate_ui(source="<.c 路径或内联源码>", out="<项目>/ui/main.json", res="<工程分辨率>")` | pack rc=0 且真机加载正常（无无声挂死） |
| 检索包生态 | `flythings_package_search` | — | `flythings_package_search(keyword="mqtt")` —— **有包用包，禁止手写协议栈 / 库** | 命中时给出包名 + 平台可用性与依赖 |
| 看包内 API | `flythings_get_package_api` | — | `flythings_get_package_api(...)` —— 包头文件级 API（**只认头文件，禁猜、禁反编译**） | API 清单来自包头文件 |
| 写 Manifest | `flythings_manifest` | — | `flythings_manifest(project_root=…)` —— 默认**只推荐不写盘**（dry_run），确认后再写 Manifest.xml | Manifest 声明与源码 include 一致，`fsc install` rc=0 |
| 解析依赖 + 核对声明 | `flythings_resolve_dependencies` | — | `flythings_resolve_dependencies(packages="<包名>", platform="<平台>")` —— 递归解析 + 冲突 / 循环检查 | 递归依赖解析完成：无缺、无冲突、无循环；声明与 include 一致 |
| 先体检，拿判据（别先动手） | `flythings_device_preflight` | — | `flythings_device_preflight(project_root="<项目>", device="<serial|IP>")` —— 返回里直接给结论 | 三项判据（分辨率/字库/体积）都有结论与来源 |
| 比例相同 / 接近 → 等比换算（机械活，别手工算） | `flythings_device_preflight` | 需用户确认 | `flythings_device_preflight(project_root="<项目>", device="<serial>", adapt="force")` —— 用户已确认要按面板改 | 换算后：所有坐标/字号/画布尺寸严格等比，无越界 |
| 比例不同 → 重排布局（判断活） | `flythings_edit_ftu` | 需用户确认 | **算清两个比例差多少**：`sx = 面板宽/设计宽`、`sy = 面板高/设计高`；差距小（如 1280×750 → 1280×800）常只需**改画布高**（只改 `resolution.height` 与根 `position.height`，控件全绝对定位、位置不动） | 重排后各段高度累加 == 新画布高，无控件被截断或压扁 |
| 打包 | `flythings_fui_pack` | — | `flythings_fui_pack(json_path="<项目>/ui/main.json")` —— json → ftu（设备实际加载 ftu） | ftu 生成、控件数与源 json 一致、分辨率一致 |
| 编译部署到真机 | `flythings_build_ui_flow` | 不可逆操作 | `flythings_build_ui_flow(project_root=…, device="<IP>:5555")` —— 编译 + 推送 + 运行 | 应用在设备上跑起来：logcat 出现启动标记，抓屏是新帧 |
| 抓真机屏幕 | `flythings_device_screenshot` | — | `flythings_device_screenshot(device=…)` —— 方向 `rotate='auto'`（按工程 `rotateScreen`） | 抓到当前页、方向正确、内容非旧帧 |
| 像素验收（还原度闭环） | `flythings_ui_visual` | — | `flythings_ui_visual(action="diff", ...)` —— 0 token 差异清单；**只看差异区小图给视觉模型**，别丢整屏原图 | 差异清单为空，或每条差异都被判为可接受并写明理由 |
| 无画面 / 黑屏排查 | （人判断） | — | 顺序：**先日志**（事件到没到控件 / 回调进没进）**再像素**（抓帧要按 pan 取当前页） | 先日志（事件到没到、回调进没进）→ 再像素（按 pan 取当前帧），根因落到具体一环 |
| 自动化回归 | `flythings_gen_ui_test` | — | `flythings_gen_ui_test(project_root=…)` 生成遍历 / 压测工程 | 遍历/压测工程生成 + 用例跑完，基线比对通过 |
| 整机自检 | `flythings_selfcheck` | — | `flythings_selfcheck(device=…)` —— 十一分区快照 | 分区快照全部执行，`ok=false` 的逐条给 hint 与结论 |
| 问题记录 | `flythings_bugreport` | — | `flythings_bugreport(...)` —— 把现象 / 复现 / 证据整理成问题单 | 问题单含现象/复现/期望/实际/证据，可直接转交 |
| 交付随项目带工具 | `flythings_attach_cli_tools` | — | `flythings_attach_cli_tools(project_root=…)` —— 复制 fui / fun 到项目（对方不装 MCP 也能编译） | fui/fun 已复制到项目，交付后无需安装 MCP 即可编译 |
| 多语言 | `flythings_i18n` | — | `flythings_i18n`（`action=refactor`）（写死文案抽 @key）→ `flythings_i18n`（`action=export`） → 翻译 → `flythings_i18n`（`action=import`） → `flythings_i18n`（`action=to_json`） | 文案全走 @key、翻译已 import 并 push，设备显示新语言 |

## 4. 验收判据（每步「做完了算不算过」；`verify` 真源在 flow_spec.json）

| 步骤 | ✅ 通过 | ⛔ 不通过（继续会返工/出错） | 证据 / 怎么验 |
|---|---|---|---|
| 先把三个参数定下来（别猜） | 平台与分辨率都来自用户原话或型号库查询结果 | 按同系列型号外推，或分辨率留空就往下走 | 返回体里 `model/platform` 与 `resolution` 都有确定值；缺任一项就停下问用户 |
| 找相近模式（先查再画，省一轮返工） | 命中相近布局/控件的现成结论，并记下用了哪页 | 跳过这步直接开画 | `knowledge_search` 返回的 path 为据；无命中可继续，但要在回复里写明「知识库无相近模式」 |
| 写码前必读规范（不能跳） | 拿全目录规则 + 生成规则 + 注意事项 | 凭记忆写 ui json 的目录结构或业务代码位置 | `get_project_spec()` 返回非空，且已读过「目录规则」一节 |
| 先判形态（决定走哪条路） | 四类形态之一被明确选中（HTML 原型 / Figma 导出的 HTML / 纯图片稿 / 仅参考风格） | 拿纯图片稿走 html_to_json（会得到空产物） | 回复里写出判定的形态与对应通路；纯图片稿要走切图通路 |
| HTML 原型 → ui json | 转换成功：控件数 > 0、产物图片都在 `<项目>/resources/images/`、未识别项已登记 | 控件数为 0，或产物图片路径不存在 | 返回体 `converted`/控件清单 + `unrecognized`；`flythings_verify_assets` 复核图片引用与尺寸 |
| 建工程 | 工程骨架齐全（package.properties / ui/ / resources/images/ / src/），分辨率与平台已写入 | 设计稿未经用户确认就建工程（返工），或分辨率与设计稿不一致（坐标全偏） | `validate_project` 无 errors；`package.properties` 与 `ui/*.json` 的 resolution 一致 |
| 先出预览稿让用户点头 | 预览稿已交付且用户明确确认版式 | 未确认就 pack 或写业务逻辑 | 用户回复里出现确认（或改版意见已落回 json）；预览 html 路径存在 |
| 写 ui/*.json | 控件字段与必填键都来自 `ui_schema` 查询结果，json 可被 pack | 凭记忆写字段，或缺必填键（真机加载异常） | `ui_schema(control_type=…)` 的返回为据；`layout_audit` 无 fatal |
| 三道核对（改完必跑） | `validate_project` 无 errors 且 `layout_audit` 无遮挡/越界/触摸穿透 | 只看 pack 成功就去推设备 | 两个 op 的返回逐条为空或仅为 warnings；有 fatal 就必须改后重跑 |
| 补回调桩（生成归 fsc build，本 op 是体检 / 兜底） | 桩与 `ui/*.json` 控件一一对应，无缺、无重复生成 | 覆盖已有业务代码，或手写回调桩（绕过 op / 工具链） | `git diff` 只新增函数骨架；返回体的 affectedFiles 与控件数一致；`fsc build` 通过 |
| 在 logic 里写页面逻辑 | 该页交互控件在 `src/logic/<页>Logic.cc` 里有对应实现（桩体不再是占位）；容器 / 显示类控件已在代码侧接线 | 只补了桩就打包上机；或把业务代码写进 `src/activity/`（下次 ftu 生成会覆盖） | `git diff src/logic/*.cc` 里能看到函数体实现（setText / setXxxListener / refreshListView / 业务对象调用）；`fsc build` 通过；真机点一下有反应（logcat 有回调日志） |
| 先摸清现状（别凭文件名猜） | 分辨率、控件清单、caption→id 映射三者都拿到 | 凭文件名猜页面结构 | `read_json` 返回含 caption/id 列表；`get_project_spec` 已读 |
| 改 UI | 改完 json 后 ftu 已重新 pack，两者内容一致 | 手改 ftu（ftu 是产物，改了会被下次 pack 覆盖） | `fui_unpack` 或 `read_json` 复核；`validate_project` 无 errors |
| 先查控件对应关系（别一边翻一边猜） | 源控件对上目标控件，给出等价级别 L1~L5 与可粘贴片段 | 未命中却自己造一个等价控件 | 返回体 `level` + `snippet`；NO_HIT 时按 candidates 走人工确认 |
| 源码 → ui json（自动翻译） | pack rc=0 且真机加载正常（无无声挂死） | 产物里控件字段写成字符串（子盒对象必须是对象），或整页无控件 | `fui_pack` rc=0 + 真机截图；`translate_ui` 返回的 `unrecognized`/`downgrades` 已登记 |
| 检索包生态 | 命中时给出包名 + 平台可用性与依赖 | 有现成包却手写协议栈/库 | `package_search` 返回体；未命中才考虑自实现并登记缺口 |
| 看包内 API | API 清单来自包头文件 | 猜 API 或反编译取签名 | 返回体的头文件路径与签名列表；调用的每个方法都能在清单里找到 |
| 写 Manifest | Manifest 声明与源码 include 一致，`fsc install` rc=0 | 只写 Manifest 不 install（编译期缺库） | `fsc install` 输出 + `check_project_deps` 无 missing |
| 解析依赖 + 核对声明 | 递归依赖解析完成：无缺、无冲突、无循环；声明与 include 一致 | 只看直接依赖，间接依赖留到编译期才炸 | `resolve_dependencies` 的 conflicts/cycles 为空 + `check_project_deps` 无 missing |
| 先体检，拿判据（别先动手） | 三项判据（分辨率/字库/体积）都有结论与来源 | 跳过体检直接 build_ui_flow，或把 `decision.action=push` 当成要改盘 | 返回体 `checks.*.decision`；面板 ≥ 设计时动作就是 push（什么都别改） |
| 比例相同 / 接近 → 等比换算（机械活，别手工算） | 换算后：所有坐标/字号/画布尺寸严格等比，无越界 | 手工拆项乘系数（漏项就错位），或用户没确认就落盘 | 改盘前后各抓一张对比 + `layout_audit` 无越界；`adapt='force'` 才落盘 |
| 比例不同 → 重排布局（判断活） | 重排后各段高度累加 == 新画布高，无控件被截断或压扁 | 比例不同还硬做等比缩放（界面变形） | 真机截图 + `layout_audit`；先出 plan 让用户确认分段再落盘 |
| 打包 | ftu 生成、控件数与源 json 一致、分辨率一致 | 改了 json 没重 pack（设备仍加载旧 ftu） | `fui_pack` 返回的控件数/分辨率 + ftu 文件 mtime 晚于 json |
| 编译部署到真机 | 应用在设备上跑起来：logcat 出现启动标记，抓屏是新帧 | 进程 D 状态卡死，或抓到的是上一轮旧帧 | `build_ui_flow` 返回的 launch 活性结论 + `device_screenshot` 连抓两帧取第二张 |
| 抓真机屏幕 | 抓到当前页、方向正确、内容非旧帧 | 拿旧帧当结果（对比全错） | 连抓两帧看是否一致；`rotate` 与工程 `rotateScreen` 一致 |
| 像素验收（还原度闭环） | 差异清单为空，或每条差异都被判为可接受并写明理由 | 只看整屏缩略图就说「还原了」 | `ui_visual(action='diff')` 的差异区清单（错位/缺图/配色三类） |
| 无画面 / 黑屏排查 | 先日志（事件到没到、回调进没进）→ 再像素（按 pan 取当前帧），根因落到具体一环 | 一上来就改布局/改代码（没定位就动手） | logcat 片段 + 当前帧截图；设备缺命令时先 push busybox 再采 |
| 自动化回归 | 遍历/压测工程生成 + 用例跑完，基线比对通过 | 把 no-baseline 的步骤报成「通过」 | `test_run` 的 JSON + JUnit 报告；no-baseline 必须如实列为 no-baseline |
| 整机自检 | 分区快照全部执行，`ok=false` 的逐条给 hint 与结论 | 把 `ok=false` 当异常抛掉，或只报总分 | 返回体 `summary.total/failedSections`；读不到本身是结论，要如实报告 |
| 问题记录 | 问题单含现象/复现/期望/实际/证据，可直接转交 | 只有一句描述、无复现与证据 | `bugreport` 渲染的文本；采不到真机数据时写明原因（未连设备/设备不可定位） |
| 交付随项目带工具 | fui/fun 已复制到项目，交付后无需安装 MCP 即可编译 | 只复制了一半（缺 fun 就无法 install/build） | 项目根有 `fsc.exe`、`ui/` 下有 `fui.exe`；用项目自带工具链跑一次 build |
| 多语言 | 文案全走 @key、翻译已 import 并 push，设备显示新语言 | 改完 tr 不 push（设备仍跑旧翻译，logcat 刷 not found value） | `i18n_to_json` 后设备文案变化；换行一律写 `&#x000A;`，json 里必须是真实 0x0A |

## 5. 跨流程铁律（去重后只此一份）

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

## 6. 工程状态位（跨会话「做到哪了」）

| 状态位 | 由哪步写入 | 挡住哪步 | 含义 |
|---|---|---|---|
| `paramsDecided` | clarify-params | create-project | 平台 / 分辨率 / 交互三项已由用户明确 |
| `projectCreated` | create-project | write-ui-json | 工程骨架已生成（含平台 / 分辨率替换） |
| `designConfirmed` | preview | gen-logic-stub | 用户确认过版式预览稿 |
| `uiWritten` | write-ui-json | pack | ui/*.json 已写完并通过三道核对 |
| `stubsGenerated` | gen-logic-stub | — | 回调桩已补齐（只补不改，可反复跑） |
| `logicWritten` | write-logic | pack | 页面逻辑已写进 src/logic/<页>Logic.cc（桩体不再是占位；容器/显示类控件已在代码侧接线） |
| `packed` | pack | launch | ftu 已按当前 json 重新生成 |
| `launched` | launch | screenshot | 已推送到设备并成功启动 |
| `screenshotTaken` | screenshot | visual-diff | 已有本机当次画面（不是旧图） |
| `verified` | visual-diff | — | 像素验收通过（或差异已逐条解释） |

