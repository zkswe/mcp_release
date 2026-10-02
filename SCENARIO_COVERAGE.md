# FlyThings MCP · 四场景覆盖评估与 AI 推广策略

> 日期：2026-10-02 · 基于 v0.27.171（44 ops，本轮真机全链路验证后）
> 结论先行：**场景④（改已有项目）已达生产可用，场景①（只有想法）链路通但缺「页面模式库」这块关键拼图，场景③通了 LVGL 一路，场景②中段强、两头缺。推广上最高杠杆不是 VSCode 插件，而是「场景 Skill 四件套 + MCP 市场上架 + 页面模式库」。**

---

## 一、四场景覆盖矩阵

### 场景① 只有想法就想开发 —— 覆盖度 ★★★☆☆（链路通，缺模式库）

**现有链路**（本轮全部真机验证）：
`quickstart.md` → `get_project_spec`（工程规范）→ `knowledge_search`（控件/规范检索）→ `create_project`（7 平台模板）→ 写 json → `ui_preview`（客户确认稿，带确认闸门）→ `generate_ui_assets`（AI 生图标，带 assetAudit 自检）→ `build_ui_flow`（pack→build→launch）→ `device_screenshot` → `gen_ui_test`+`test_run`（触摸回归）

**缺口**：
1. **没有页面模式库**——AI 每次都从零排版，温控面板、音乐播放、设置列表、仪表盘这类高频页面没有「最佳实践骨架」可抄，产出质量看模型运气。这是场景①体验的最大变量。
2. 想法→原型的引导在知识库（`prototype-flow.md`），但 op 层没有编排，全靠 AI 自己串。

**建议**（按杠杆排序）：
- 建 `knowledge/patterns/` 页面模式库：每个模式 = 一篇 md（布局要点+配色铁律）+ 一个可直接 create 的模板工程/json 片段。先做 6 个：仪表盘、温控/环境面板、音乐播放、设置列表、摄像头监视、门禁/对讲。
- 场景① playbook 写成 Skill（见第二节），把「想法→确认稿→上机」固化成流程。

### 场景② Figma/设计稿过来开发 —— 覆盖度 ★★★☆☆（中段强，两头缺）

**现有链路**：
设计稿 →（导出 HTML）→ `html_to_json`（HTML_SUBSET 规范，CSS 效果自动转图，产物尺寸==控件盒）→ `ui_visual diff`（渲染图 vs 设计稿/真机截图的还原度校验）→ `verify_assets`

**亮点**：`ui_visual diff` 做还原度闭环是独家能力——「像不像」从玄学变成 916px/38.4万px 的数字。

**缺口**：
1. Figma 直连：现在靠人把 Figma 导出成 HTML，断层在第一步。
2. 纯图片稿（截图/照片）只能靠 AI 视觉直接写 json，没有专用支撑。

**建议**：
- 短期：文档化「Figma → HTML 导出 → html_to_json」链路（推荐插件 + HTML_SUBSET 对照清单），成本几乎为零。
- 中期：`figma_to_json` op（Figma REST API 拉 frame 树直转 json，token 由用户提供）——这会是对外宣传时最抓眼球的 demo。

### 场景③ 其他 APP 源码转换 —— 覆盖度 ★★☆☆☆（LVGL 一路已通）

**现有链路**：
- LVGL v8/v9 C → `flythings_translate_ui`（本轮新落地，真机验证：映射表 L1~L5、降级登记、未识别不静默丢、缺图三级处置）
- VUE/Web → 渲染/HTML → `html_to_json`
- 微信小程序 → `knowledge/devflow/mp-transfer-miniprogram.md`

**缺口**：Android XML、Qt QML、iOS、树莓派（GTK/Qt）没有翻译器；`translate_ui` 目前是 LVGL 单语言实现。

**建议**：
- 把 translate_ui 抽象成**翻译器框架**：mapping 表驱动（沿用 `mcp_control_map.json` 模式）+ 契约测试模板，每接一种源语言只是加一张映射表 + 一组测试。
- 下一路优先级：**Android XML**（布局模型和 FlyThings 最接近，存量源码最多）> **Qt QML**（用户明确点名，嵌入式存量大）> VUE 补文档（通路已在）。

### 场景④ 已有 FlyThings 项目替换 UI / 改功能 —— 覆盖度 ★★★★☆（最强，功能面缺一截）

**现有链路**（本轮真机闭环验证：edit_ftu 改嵌套温度文本 23.5C→25.0C 上屏）：
`read_json`/`map_control` → `edit_ftu`（已修：嵌套控件递归、假成功、嵌套 remove）→ `validate_project`+`layout_audit`（0 错误 0 发现）→ `ui_visual diff` → `build_ui_flow` 重推 → `test_run` 触摸回归（4/4 pass）

**缺口**：
1. **改「功能」要动 C++**：`src/logic/*.cc` 回调桩手写，编译断链本轮实测踩过（我手工修的嵌套括号）。UI 面已闭环，逻辑面还是手工活。
2. 换肤类需求没有「主题/配色一键替换」op（配色对比度标准已入库，缺执行器）。

**建议**：
- **C++ 回调桩生成 op**（从 json 控件表生成 logic/*.cc 骨架：mXXXPtr / ID_MAIN_* / 回调注册 / findControlByID 按规范生成）——场景④ 从「换皮」升级到「换功能」，优先级最高。
- 主题替换 op（`edit_ftu` 批量 set_root/set 的封装 + 对比度校验）。

---

## 二、AI 浪潮下的推广策略（不局限于 MCP）

| 方向 | 杠杆 | 成本 | 优先级 | 说明 |
|---|---|---|---|---|
| **场景 Skill 四件套** | ★★★★★ | 极低 | P0 | 把四场景各写成一份 SKILL.md（流程+铁律+op 调用顺序），Claude/Kimi/Cline 等所有支持 skills 的 agent 自动加载。纯文档，直接提升①④体验 |
| **MCP 市场上架** | ★★★★☆ | 低 | P0 | Smithery / glama / 官方 servers 列表；`configure.py` 一键配置已有，README 补英文版（配合出海硬件） |
| **页面模式库** | ★★★★☆ | 中 | P0 | 场景① 的质量天花板；也是「生态缺乏」最可见的补法 |
| **C++ 回调桩 op** | ★★★★☆ | 中 | P1 | 场景④ 功能面的最后一块 |
| **翻译器框架化 + Android XML** | ★★★☆☆ | 中 | P1 | 吃「迁移存量」叙事，一路一个 demo 视频 |
| **独立 CLI（flythings-ai）** | ★★★☆☆ | 中 | P2 | fun 已是 CLI，薄封装一条龙（create→translate→build→launch→shot），服务不装 MCP 的 agent 和 CI |
| **VSCode 插件** | ★★☆☆☆ | 高 | P2 | 定位要克制：AI 能力全部交给 MCP（VSCode 已原生支持 MCP），插件只做「人」的部分——json 预览面板（复用 ui_preview 渲染器）、schema 补全校验、一键 pack/launch、截图回显。**不要在插件里再造一个 agent** |
| **figma_to_json** | ★★☆☆☆ | 高 | P3 | 宣传价值大于实用价值，适合做 demo 视频素材 |

**内容营销**（配合已在做的宣传物料）：
- 「用 AI 30 分钟从想法到上机」实录短视频——场景① 全流程，片尾落在「不用懂嵌入式」
- 「LVGL 项目一杯咖啡迁到 FlyThings」——translate_ui 实录
- demos/ 已有 8 个工程（dvr 录像、h264 播放、网络栈验证…），配截图/GIF + README 索引变成 demo gallery

**验证指标**（推广动作是否奏效，建议按季度看）：

| 指标 | 确认阈值 | 挑战阈值 | 触发动作 |
|---|---|---|---|
| MCP 市场安装量 | 上架后 90 天 >100 | <20 | 低于挑战值→转向 README/视频引流 |
| 场景① 首次上机耗时（新用户实测） | <30 分钟 | >60 分钟 | 超时→补模式库/quickstart |
| translate_ui 迁移 demo 完播/转化 | 视频完播 >40% | <15% | 换叙事角度 |
| 页面模式库复用率（新项目引用模式数） | >50% 新项目用模式 | <20% | 模式不对题→重做选题 |

---

## 三、本轮已落地的铺垫（v0.27.171）

- `translate_ui`（场景③第一路）+ 14 契约测试，真机验证
- `quickstart.md` + README 上手引导（场景①入口）
- edit_ftu 三处修复（场景④闭环）
- 七平台模板补 main.json、create_project 分辨率回写（场景①地基）
- 39 项一致性门禁全绿
