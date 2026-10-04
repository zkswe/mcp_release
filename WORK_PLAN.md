# FlyThings MCP 后续工作安排计划

> 整理：2026-10-03（第四轮刷新）
> 实测数字**不写在这里**（本行原先手写「门禁 N 项 / 用例 N 项 / 检索 N 组…」，
> 三轮里漂了两次 —— **正因为抄一份漂一份，这些数字一个都不留在这里**，连"最近一次读数"也不留：
> 留在纸上的每个数都必须是**当前值**，而"当前值"只由下面两条命令产出）。
> 要当前值就跑下面两条，它们**自己会打印**：
> `python scripts/check_consistency.py --with-tests`（看 `total=… fail=…` 与
> `test count matches real run` 两行）· `python scripts/check_retrieval.py`（看 `[PASS]` 行）
> 工具数仍是 **48 op**（由 `stage_tool_count` 六方一致盯着，可放心引用）。
> 状态：✅ 已完成 / 🤖 AI 可执行 / 👤 需需求方输入 / 🔌 需设备

> ⚠️ 上一版（2026-10-03 第二轮）写「门禁 61/61 全绿」—— **实为 63 项且 2 项红**（用例超时 + 门禁不可复现），
> 已在「验证层体检」中修复（详见 `REVIEW-2026-10-03.md` §6）。**门禁条数与用例耗时不由人写**，
> 每次大动作后按实跑刷新。

---

## 一、已完成：域注册表归集（①–⑫，本阶段主线）

起点是需求方的一句「从第一性原理出发，减少 MCP 的历史包袱」——把散落重复的知识收成
**唯一真源 + 单一 loader + 全派生 + `--check` 进闸门**。现在共 12 个域：

| 域 | 真源 | 唯一消费入口 | 状态 |
|---|---|---|---|
| ① op 契约 + 工具面分层 | `op_spec.json` | `op_spec_loader.py` | ✅ 三层（常驻/按需/深入）；常驻 **5080/6000**（84.7%，`params` 已移出常驻；数字由门禁对账，见 §二） |
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
| ✅ 三层拆分 | 常驻（summary+triggers+hardRules）→ tool description；按需（params/flow/rules/notes…）→ `op="describe:<名>"` / 资源 `flythings://ops/<名>`；深入 → knowledge 检索。常驻从 11943 → 5878 → **4730 → 5080**（`params` 移出后再进 4 条硬规则） |
| ✅ 常驻再瘦身 | **`params` 移出常驻**（2026-10-03）：参数名 `op="list"` 已回、语义 `describe` 按需给，常驻再写一遍是重复计费（占 19.5%）。**5878 → 4730（78.8%）**；同日三批 `notes` 清零 + 4 条硬规则 → **5080/6000（84.7%）**，余量按实测均值 ≈ 再加 **8** 个 op |
| ✅ 分级筛选 | 需求原话进来 → `op="find:<原话>"` 出候选（带命中理由 + 知识指针）→ describe 取契约 → 调用。**207 条口语触发词**，匹配器与知识权威归属**共用一份**（`kb_authority.alias_hit`） |
| ✅ 路由回归 | `tests/test_op_routing.py`：27 组口语 → 期望 op top-3 命中（实测 27/27） |
| ✅ 长任务进度 | 10 个长任务 op（清单在 `op_spec.json.longOps`）走工作线程 + `ctx.report_progress`；顺带修掉「同步长任务堵死事件循环」 |
| ✅ 跨会话状态 | `<项目>/.flythings/state.json`；`_envwrap` 一处回写覆盖三模式；资源 `flythings://state` 看「上次做到哪」 |
| ✅ 错误码语义 | 22+1 个码登记（含义 / 该谁动手 / 默认可重试 / 下一步动作），自动注入失败返回 |

## 三、已完成：早先计划里的技术债与真机加固

| 原 # | 任务 | 结论 |
|---|---|---|
| 1 | docstring 预算顶爆（11996/12000） | ✅ **改口径解决**：不是删字，是三层分层（常驻 5080/6000，加 op = 加一行） |
| 2 | `test_font_autoscan` ×10 失败 | ✅ 按 `requirements.lock` 装 `fontTools==4.65.0` → 32 OK |
| 14 | **验证层体检**（2026-10-03 二次评审）：用例非 hermetic（漏 mock → 真 adb，全套 >900s）、门禁依赖仓外目录不可复现、数字漂移（op 数/用例数/耗时） | ✅ 三件都修：`tests/_util.py` adb 离线守卫 + `sync_ui_tools` skip 码 2 对齐 + 数字进闸门；另把用例的守法改成**逐用例看门狗**（`scripts/run_tests.py`，慢不算错、挂才算）。用例实测 **737 项**，门禁 **82 项**（两处数字由 `check_consistency.py --with-tests` 的「当前数字各处声明 == 实测」对账，别再手写第三处） |
| 5–10 | launch 活性 / 陈旧帧 / easyui 同源 / 分辨率核对 / cfg 修正 / translate_ui 交互 | ✅ 全部完成（真机闭环） |
| 11 | C++ 回调桩 op | ✅ `flythings_gen_logic_stub`（只补不改、幂等） |
| 13 | 场景 Skill 四件套 | ✅ 已落用户级 skill；**且已升级为「由 `flow_spec.json` 派生」**（5 篇正文不再手写） |

## 四、仍待办

> ⚠️ **本表只是一部分**（2026-10-05 全仓盘点结论）：本表原先只从主线文档汇总，而「评审报告里
> 写下的承诺」与「注册表/组件页里的验证债」**没有回填通道** —— 实测回填率 **2/13**，另盘点出
> **24 项**不在本表的真工作（含 1 项 P0：按需面 `describe(section=)`）。
> **完整清单见 [`TODO.md`](TODO.md)**（A 真源矛盾 / B 报告承诺 / C 验证最后一公里 /
> D 能力缺口 / E 工具与发布 / F 结构性建议）。本表继续只放**主线任务**，两者都要看。

| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| A | **页面模式库** `knowledge/patterns/` ×6（仪表盘/温控/音乐/设置/摄像头/门禁） | 👤 选题 +🤖 制作 | 场景① 质量天花板 —— AI 现在每次从零排版，产出看运气。**主线里唯一还没开工的 P0**（另有 `TODO.md` B1 也是 P0） |
| B | uicontrols 文档瘦身（原写"35 篇"，看板实测 **37 篇**） | 🤖 随任务做 | 口径：注册表拥有字段/类型/默认值/判据，md 只留原理/流程/回调 |
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

**已复验（2026-10-03，V85X 真机工具链实编）** —— 详见 `CONSOLIDATION.md §18`：

| 组件 | V85X 结论 |
|---|---|
| blur / imagecache | ✅ **可编译可链接**（在 `arm-unknown-linux-musleabihf-gcc` 下编过并链成 `libzkgui.so`） |
| vinyl | ❌ **不可编**（2026-10-05 V85X 工具链实编）—— 卡点**不是** nanovg（`nanovg.h` 那关已过，随仓 `.so` 与设备 `/lib` 那份 md5 逐字节相同），而是 `zk_vinyl.cpp:40` 的 **`misc/image_utility.h`**：它不在任何 easyui 包内、不在仓内、设备 `libeasyui.so` 也无 `misc::*` 符号（那是 F133 应用工程侧的头）。出路：厂商补该头，或拍板改写成 easyui 真有的 `utils/BitmapHelper.h` |
| wall_sync | ❌ **不可用** —— 缺 `rapidjson` 包（`fun install` 拉 v85x 源 → **502**） |
| blend2d / icons | 原本就已正确标注（无 V85X 库 / 平台无关） |

> 主要卡点是 **V85X 的包 registry 只有 5 个基础包**（Z20 有 20+）——
> 这是包供给问题，不是组件代码问题。未验证单元格 32 → 30。
>
> `wall_sync` 的**拼墙相位对齐**单机验不了（需多台同型号组墙），属另一类，不并入单平台口径。

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
