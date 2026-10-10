---
id: devflow-ui-pipeline-spec
title: 界面产物管线口径（唯一产物规范 ui_schema.json · 手写入口不排他 · 三档判据 · 模块 I/O 契约）
category: devflow
status: review
confidence: manual
verified_at: 2026-10-05
stale_days: 180
origin: total
source: 2026-10-05 需求方拍板：原来的「排他性手写源」口径作废，排他性从输入端移到输出端（原文与理由见 REMEDIATION-UI-PIPELINE.md §0/§1）+ 该文件 §2 判据分档 / §3 模块 I/O 契约
needs_evidence: true
platforms: []
tags: [HTML 是不是唯一源, 多个入口怎么选, json 怎么算合格, 离线怎么判定界面, 界面产物管线, 入口分级, 编译式验收, 判据分档, 模块契约, 差异归因, 发射链]
evidence: []
---
# 界面产物管线口径（唯一产物规范 · 手写入口不排他 · 三档判据 · 模块 I/O 契约）

> 检索导引：问「**HTML 是不是唯一源** / **多个入口怎么选**（HTML 原型、块库 spec、LVGL·Qt·QML·Android XML·Vue 迁移、直接手写 json）/ **json 怎么算合格** / **不上机能判定界面吗**（离线判定/离线验收能做到哪一步）/ **预览和真机不一样改哪一层**（差异该谁负责）/ json 渲染和真机不一致该改哪一层 / 界面产物的唯一规范是什么」→ **本文（唯一出处）**。
> 用户口语/别名：不一定非要写 HTML 吧 / **不写 HTML 直接写 json 行不行** / 我直接写 json 行不行 / 小程序（QML·Vue·安卓）能不能迁 / **Vue 工程能迁到 FlyThings 吗** / QML 能迁吗 / 小程序 WXML 能转过来吗 / 不用上机先看看像不像 / **不上机能判定界面吗** / 预览和真机不一样是谁的问题 / 哪个源说了算。
> **本文是界面产物管线的唯一口径出处**：其它页（`knowledge/devflow/platform-translate.md`、`knowledge/devflow/ftu-json-pipeline.md`、`knowledge/devflow/ui-layout-verify.md`、`knowledge/devflow/prototype-flow.md`、`knowledge/devflow/ui-entrypoints.md`）只保留各自专题并**指向本文**，冲突以本文为准。
> 登记**入口**（有哪些入口、各自什么状态/校验链/限制）见 `knowledge/devflow/ui-entrypoints.md`（真源 = 仓库根 `ui_entrypoints.json`）。

## 0. 一句话口径（CRITICAL，逐字照用）

> **`ui_schema.json` 是唯一产物规范，`ui/*.json` 是唯一事实源；手写入口不排他
> （HTML 原型 / 块库 spec / LVGL·Qt·QML·Android XML·Vue 迁移），但任何入口的产物
> 必须由共享发射链产出，或经编译式验收（`ui_compile`）无 fatal/error 才算成立。**

- **排他性从"输入端"移到了"输出端"**：不限制你从哪种源出发，限制的是**产物**——产物必须过验收。
- **HTML 保留两个角色**（去掉的是「唯一」，不是 HTML）：① **缺省前端**（需求 → 线框/风格稿，**客户确认载体**）；② **确认稿渲染**（`json2html` / `flythings_ui_preview(for_customer=True)`）。
- 两个否定式边界（别往两头滑）：**不让 HTML 退化成"必须走"的中间层**；**也不让"手写 json"合法化到无校验**。

## 1. 三档判据

| 档 | 手段 | 强度 | 用途 |
|---|---|---|---|
| **① 编译式验收** | `ui_compile`（json 静态诊断：类型 / 必填 / 全集 / 语义 / 引用） | **硬判据**（可判红、带 exit code、进闸门） | **落盘前 / 上机前**把「能不能加载、字段对不对」一次判完；产出 `success:false` + 逐条诊断（规则 id + 路径 + 修法） |
| **② 离线渲染判定** | `json2img` A/B 像素 diff（**同一渲染器**） | **硬判据**（确定性：同输入同 md5） | 跨源/跨入口**等价性**、字段与几何回归；盲区**不许判通过** |
| **③ 离线近似** | json 渲染 vs 源参考图（浏览器稿 / 设计图） | **松判据（人工）** | 判「像不像源设计」，只作参考，**不作合格结论** |
| **④ 真机真相** | `device_screenshot` + `ui_visual(action="diff")` | **最终真相** | 出货验收；离线两档都替代不了它 |

- `json2img` 是**模拟层**（字体度量 / 9-patch 拉伸 / 换行 / 裁剪字库与设备有差）→ 做**归因判定**够硬，**替代真机不够**。
- ✅ **第 ① 档已可用（2026-10-05 起）**：`ui_tools/ui_compile.py`（22 条规则，规则号 + 路径 + 修法 + exit code，
  另有 `compile_json` / `compile_project` 库化 API）；生成/落盘路径的出口闸门见 `REMEDIATION-UI-PIPELINE.md` T1.1–T1.3。
- ⚠️ **两档口径（别把 error 一律当必拦）**：`fatal > 0` **一律拒绝**（`error.code=UI_JSON_INVALID`）；
  `error > 0` 默认只回 `uiCheck.errorsNotBlocking` + warning（存量 / IDE 手写 json 常见"字段全集"欠账），
  要拦就传 `strict_ui=True`。
- ⚠️ **它不覆盖的判据（如实登记，别当成已验收）**：图片尺寸 vs 控件盒 / AA / 倒角 / 透明底归
  `check_all`（委派 `tools/qa/*`）；`check_all` 的 json 侧检查项目前仍是**第二份实现**（T1.4 未合并，
  每次报告都会在 `delegated` 里点名）。

## 2. 入口分级

| 档 | 是什么 | 约束 |
|---|---|---|
| **default（缺省）** | 需求 → 线框/风格稿（HTML 受限子集）→ `flythings_html_to_json` → `ui/*.json` | 新需求没给稿时的**缺省走法**；线框/风格稿是**客户确认载体**（不 pack、不写逻辑，先确认）；产物一律过 §1 ①/② 才落盘 |
| **allowed（允许）** | 直接按 schema 写 `ui/*.json`、块库 spec（`templates/ui_blocks/compose.py`） | 不排他，但**产物必须等价**：字段来自 `flythings_ui_schema`（不许凭记忆）、过同一套校验链；**跳过 HTML 不等于跳过验收** |
| **migration（迁移）** | LVGL → `flythings_translate_ui`；Qt / QML / Android XML / 小程序 WXML / Vue → 逐控件 `flythings_map_control` + 手工搭 json | 前端（A 层）只许产 IR/中间表示；**未实现的入口一律登记 status=planned**（不许把"能手工做"写成"入口已支持"）；L3 以上（自绘/降级/不支持）必须逐条登记 `downgrades` |

**入口清单是登记制**：有哪些入口、各自 status（`active` / `planned` / `unsupported`）、校验链、证据、已知限制
→ **真源 = 仓库根 `ui_entrypoints.json`**，人读版 = `knowledge/devflow/ui-entrypoints.md`（派生）。
**每个 `active` 入口必须有非空 `validator_chain` 与 `evidence`**（没有校验链和证据的入口不许标 active）。

## 3. 模块 I/O 契约

| 模块 | 输入契约 | 输出契约 | 自检判据（红了就是它的错） | 禁止事项 |
|---|---|---|---|---|
| **A 前端** | 源文件 / 源码 | **IR** | 覆盖率报告（`unrecognized` / `downgrades` 逐条）+ IR 校验 | ❌ 不许直接出 json；❌ 不许 import PIL |
| **B 映射** | 源控件名 | `target` / `level` / 片段 / `notes` | 条目完整性 + 片段由 schema 派生（`gen_control_map_snippets.py --check`）+ L3 必给 `ref` | ❌ 不写散文映射表（索引不是引擎） |
| **C 发射** | IR | `ui/*.json` | `ui_compile` 无 fatal/error + `check_all` 关键项 0 FAIL | ❌ 不解析源语言；❌ 不画图 |

> **C 层发射（2026-10-05，T5.2 / T5.5 / T5.6）**：`ui_tools/ui_emit.py` 是**必填键补全**与 **`translate` 路径
> 字段全集**的唯一实现 —— `translate_tools.py` 以别名调用它（抽取前后对同一批 LVGL 夹具产物**逐字节一致**）；
> `html2json` 与 `templates/ui_blocks/compose.py` 的 `serialize()` 走它的 `fill_required()`（**只补注册表必填键**，
> 不碰各自有意省略的可选字段）。
> ⚠️ **如实登记（别把"共用一条链"读成"只有一份实现"）**：**键序 / `tab5` 色表规范化只有 `schema_complete()` 一份**
> （`translate` 路径用）；`html2json` / `compose` 仍各自持有**取值表**，差异逐条登记在
> `ui_tools/emit_conformance.json`（校验器 `scripts/gen_emit_conformance.py --check` 已进一致性门禁）——
> 但它**只比必填键完整性、不比取值**，且 `html2json` 只抽到 5 个类型 ⇒ **取值漂移抓不住**。
> **新前端别再写第三份字段补全。**
| **D 出图** | 效果描述 | PNG（**图 == 盒**、α = 覆盖率） | `renderContract` 十条 + 尺寸/α 断言 + 黄金样例 | ❌ 调阈值/档位修视觉问题 |
| **E 渲染判定** | json + 资源 + 字体 | PNG + `unsupported[]` + 机读报告 | 确定性（同输入同 md5）+ 覆盖矩阵 + **盲区不许判通过** | ❌ 不写业务代码 |
| **F 验收** | 设备 | 截图 + diff | 真机像素 | ❌ 用离线渲染替代真机结论 |

> 契约的分工含义：**A 只管把源读懂**（读懂多少要如实报），**C 只管把 IR 变成合法 json**，
> **D/E 只管把 json 画准并如实记账**，**F 才下结论**。跨层"顺手修一下"会抹掉责任归属（见 §4）。

## 4. 差异归因三分

| # | 归因 | 处置 |
|---|---|---|
| ① | **前端丢语义**（A 层没读懂源：`unrecognized` / 静默降级） | 改**前端**；做不到的**逐条登记 `downgrades`**（登记制，不许悄悄降级） |
| ② | **发射层字段或换算错**（C 层：字段取值、单位换算、必填键） | 改 **fill / 换算规则**（先改规格再改实现） |
| ③ | **渲染器不覆盖或语义错**（E 层） | **只有这一类才动 `json2img`**，且必须同时：更新 `renderContract` 行**或** `unsupported` 清单 + 更新基线 + 补**真机对齐证据** |

> **判据可以改，但只能按规格改，不能按结果改**（`DESIGN_SPEC.md` 第 1.1 条「规格先行：规格要求设计，不是设计迁就实现」；第 1.2 条「禁止 `⛔EXCUSE`（把缺陷登记成已知代价/豁免了事）与 `⛔TWEAK`（调阈值/容差/算子/档位把观感修过去）」）。
> 一句话判据：**改动之后，规格里多了一条"该怎么做"吗？** 没多 → 这次修复只是把问题挪了个位置（`scripts/audit_design_spec.py` 的 ⑧/⑨ 就是这条的机器判据）。

## 相关

- **入口登记**（有哪些入口 / 状态 / 校验链 / 限制）→ `knowledge/devflow/ui-entrypoints.md`（真源 = `ui_entrypoints.json`）
- 整改台账（任务分解与状态，**不是规范**）→ `REMEDIATION-UI-PIPELINE.md`
- 迁移方法论（四阶段 / 降级 D-xx / 双平台）→ `knowledge/devflow/platform-translate.md`
- json 与 ftu 的关系（`fui pack` / 改布局改 json）→ `knowledge/devflow/ftu-json-pipeline.md`
- 三段式验收与确认稿闸门 → `knowledge/devflow/ui-layout-verify.md`
- 新需求从哪开始（线框 → 确认 → 美化）→ `knowledge/devflow/prototype-flow.md`
- 渲染语义规格（离线所见即所得单点真相）→ `knowledge/devflow/wysiwyg-render-spec.md`
- 字段与必填键唯一真源 → `ui_tools/ui_schema.json`（op `flythings_ui_schema`）
