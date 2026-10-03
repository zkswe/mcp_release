# FlyThings MCP 后续工作安排计划

> 整理：2026-10-03（第二轮刷新）· 基线 **v0.27.173-open**
> 实测：**48 op** ｜ 一致性门禁 **61/61 全绿** ｜ 检索回归 **30 组 / 225 问法，top-1 172**，对照组 9/10
> 状态：✅ 已完成 / 🤖 AI 可执行 / 👤 需需求方输入 / 🔌 需设备

> ⚠️ 上一版（2026-10-02）的基线是「v0.27.173 / 门禁 39 / 44 ops」——**数字与内容都已脱节**，
> 那张表已经不能当雷达用了（任务 1/5–11/13 当时标着"未开工"，其实早已完成）。
> 本版按**实测**重写；以后每次大动作后同步刷新。

---

## 一、已完成：域注册表归集（①–⑫，本阶段主线）

起点是需求方的一句「从第一性原理出发，减少 MCP 的历史包袱」——把散落重复的知识收成
**唯一真源 + 单一 loader + 全派生 + `--check` 进闸门**。现在共 12 个域：

| 域 | 真源 | 唯一消费入口 | 状态 |
|---|---|---|---|
| ① op 契约 + 工具面分层 | `op_spec.json` | `op_spec_loader.py` | ✅ 三层（常驻/按需/深入）；常驻 **5878/6000** |
| ② 生命周期 / 代码接口 | `lifecycle_spec.json` | `lifecycle_loader.py` | ✅ |
| ③ 平台能力矩阵 | `platform_capabilities.json` | `platform_cap_loader.py` | ✅ |
| ④ 硬件外设 API | `hardware_catalog.json` | `hardware_tools.py` | 🟡 **仍半成品**（只收型号/坑，API 面未收编） |
| ⑤ 多媒体能力 | `media_capabilities.json` | `media_cap_loader.py` | ✅ |
| ⑥ 检索范围 | `kb_index_roots.py` | 同左 | ✅ |
| ⑦ 可复用组件目录 | `components/` 这棵树 | `components_catalog.py` | ✅ |
| ⑧ 知识权威归属 | `knowledge/authority_map.json` | `kb_authority.py` | ✅ |
| ⑨ 上机前体检判据 | `preflight_spec.json` | `preflight_loader.py` | ✅ 分辨率/字库/体积三分支 |
| ⑩ 开发流程 | `flow_spec.json` | `flow_loader.py` | ✅ 31 步骤原子 + 10 流程（场景×动作两条正交轴） |
| ⑪ 工程状态（跨会话） | `flow_spec.json.stateSlots`（复用⑩） | `project_state.py` | ✅ 新 op `flythings_project_state` + 资源 |
| ⑫ 错误码语义 | `error_codes.json` | `error_codes_loader.py` | ✅ 注入每次失败返回的 `error.action` |

**纪律**：每个域 = 唯一真源（带头部 `authority` 声明）→ 一个 loader（缺失/查不到**抛错不静默**）
→ 生成器派生 → `scripts/check_consistency.py` 里一条 delegated 检查 → 一个契约用例。
详见用户级 skill `flythings-domain-registry`。

## 二、已完成：工具面架构

| 内容 | 说明 |
|---|---|
| ✅ 三层拆分 | 常驻（summary+triggers+params+hardRules）→ tool description；按需（flow/rules/notes…）→ `op="describe:<名>"` / 资源 `flythings://ops/<名>`；深入 → knowledge 检索。常驻从 11943 降到 5878 |
| ✅ 分级筛选 | 需求原话进来 → `op="find:<原话>"` 出候选（带命中理由 + 知识指针）→ describe 取契约 → 调用。**207 条口语触发词**，匹配器与知识权威归属**共用一份**（`kb_authority.alias_hit`） |
| ✅ 路由回归 | `tests/test_op_routing.py`：27 组口语 → 期望 op top-3 命中（实测 27/27） |
| ✅ 长任务进度 | 10 个长任务 op（清单在 `op_spec.json.longOps`）走工作线程 + `ctx.report_progress`；顺带修掉「同步长任务堵死事件循环」 |
| ✅ 跨会话状态 | `<项目>/.flythings/state.json`；`_envwrap` 一处回写覆盖三模式；资源 `flythings://state` 看「上次做到哪」 |
| ✅ 错误码语义 | 22+1 个码登记（含义 / 该谁动手 / 默认可重试 / 下一步动作），自动注入失败返回 |

## 三、已完成：早先计划里的技术债与真机加固

| 原 # | 任务 | 结论 |
|---|---|---|
| 1 | docstring 预算顶爆（11996/12000） | ✅ **改口径解决**：不是删字，是三层分层（常驻 5878/6000，加 op = 加一行） |
| 2 | `test_font_autoscan` ×10 失败 | ✅ 按 `requirements.lock` 装 `fontTools==4.65.0` → 32 OK |
| 5–10 | launch 活性 / 陈旧帧 / easyui 同源 / 分辨率核对 / cfg 修正 / translate_ui 交互 | ✅ 全部完成（真机闭环） |
| 11 | C++ 回调桩 op | ✅ `flythings_gen_logic_stub`（只补不改、幂等） |
| 13 | 场景 Skill 四件套 | ✅ 已落用户级 skill；**且已升级为「由 `flow_spec.json` 派生」**（5 篇正文不再手写） |

## 四、仍待办

| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| A | **页面模式库** `knowledge/patterns/` ×6（仪表盘/温控/音乐/设置/摄像头/门禁） | 👤 选题 +🤖 制作 | 场景① 质量天花板 —— AI 现在每次从零排版，产出看运气。**唯一还没开工的 P0** |
| B | 35 篇 uicontrols 文档瘦身 | 🤖 随任务做 | 口径：注册表拥有字段/类型/默认值/判据，md 只留原理/流程/回调 |
| C | alignment 发射层与注册表对齐 | 👤 需校准表 | textview 0/36、button 5/37 等 5 处刻意差异，两种写法真机都工作 |
| D | **组件平台验证**（8 组件 / 32 格） | 🔌 设备已接入 | 见下节 —— **口径待你拍** |
| E | 翻译器框架化 + Android XML（之后 Qt QML） | 🤖 | 现只有 LVGL 单语言；映射表驱动后每接一路 = 加一张表 + 一组测试 |
| F | 域④ 硬件外设 API 收编（IIC/SPI/GPIO/PWM） | 🤖 | 唯一仍是"半"的域 |
| G | demo gallery（8 工程配截图/索引）+「30 分钟想法到上机」视频 | 🤖 | 配合宣传物料 |
| H | MCP 市场上架（Smithery/glama）+ 英文 README | 👤 账号与公开口径 | 指标：90 天安装 >100 |
| I | figma_to_json（Figma API 直连） | 🤖 | P3；另有"纯图片稿"通路缺口 |
| J | flythings-ai CLI 薄封装 / VSCode 插件 | 👤 排期 | P2/P3 |

## 五、设备侧（USB V85X 已接入）

设备：`20080411` = `Zkswe_V85X_SPINOR`（product=swaio，面板 **480×800**，easyui **2.4.0**，FlyThings V2.1）。

**已确认口径（2026-10-03）**：**UI 控件不需要逐平台验证 —— 一个平台验好即可验收**，
代表平台 = **V85X**。ui_v1 四件（RadButton / Chart / Calendar / _mapping·TabView）上一轮已按
标准 fun 链路（`fun install` → `fun build` → `fun launch`）真机验收，其余平台标 `➖ 不逐平台验`。

**待你拍的一块**：另外 **8 个显示/媒体组件**（blur / imagecache / vinyl / wall_sync / blend2d /
ha_bridge / mp_transfer / icons）在注册表里还挂着 **32 个「未验证」单元格**。它们与 ui_v1 性质不同 ——
是**源码型**组件（`include/` + `src/` + `example/`，示例多是 PC 自测程序），"平台可用性"= 能不能在该平台编译跑通，
且部分带**架构专属代码路径**（如 blur 有 RVV 版）。各自已有单平台实测：

| 组件 | 已在哪个平台实测 | 性质 |
|---|---|---|
| blur / imagecache / vinyl | **F133**（C906） | 显示/媒体 |
| wall_sync / blend2d / ha_bridge | **Z20** | 显示/媒体（ha_bridge 为 HA 桥接，非 UI） |
| icons | — | **平台无关**（纯 PNG 资源 + 三条硬规则） |
| mp_transfer | **本仓未验**（文档自己写着「没有任何一格写已验证」） | 小程序传输，非 UI |

## 六、需要你给的输入

1. **组件平台验证口径**（第五节的 D）：① 套用单平台口径 —— 已有单平台实测的 6 个把其余标 `➖`，
   只留 mp_transfer 待验；② 只在 V85X 上真机复验其中 UI 相邻的几个；③ 全部保持现状。
2. **页面模式库 6 个选题确认**（任务 A）—— 这是唯一还没动的 P0。
3. alignment 校准表裁决（任务 C）。
4. gitee 公开 / 英文口径（任务 H）。

## 七、建议执行顺序

任务 A（模式库，推广弹药 + 场景①质量上限）→ 任务 F（域④ 收尾，最后一个"半成品"域）
→ 任务 E（翻译器框架化，吃迁移存量）→ 任务 H（上架/英文，配合物料）。

设备侧若有新需求，随时可从任务 D 插入（设备在线）。
