# 待办总清单（WORK_PLAN §四 的补充通道）

> **为什么要单独一张表**（2026-10-05 全仓盘点结论）：`WORK_PLAN §四` 只从主线文档汇总，
> 于是**「评审报告里写下的承诺」与「注册表/组件页里的验证债」没有任何回填通道** ——
> 实测回填率 **2/13**（REVIEW-10-03 §6.4 的 0/4、REVIEW-10-04 §1.2 的 1/6、
> AI 能力报告的 1/3），另有 15 项验证债散在 `components/*/platforms.md`、`packages/*/`。
> 本表就是那两条通道的落点：**从报告与注册表反向汇总**，进表才算进计划。
> 状态：⬜ 未开工 / 🔄 进行中 / ✅ 已完成 ｜ 👤 需需求方拍板 ｜ 🔌 需设备/样机
> 纪律：完成一项就在原处改 ✅ 并注明落在哪个提交；**不要另抄一张表**。

## A. 真源与知识页的自相矛盾（会直接误导 AI 选型）—— 3 项

| # | 状态 | 事项 | 依据 |
|---|---|---|---|
| A1 | ✅ | vinyl 在 V85X「缺 nanovg、编不过」已过期 → 订正为「可编（手动接 nanovg），**实编+真机待验**」 | `platform_capabilities.json` vinyl/V85X 行；`packages/nanovg/lib/v85x/BUILD.md`；订正见 `c9f425f` |
| A2 | ⬜ | blend2d V85X 已自编成功（160/160、md5 `ED1569…`）但真源仍写「需 musl 重编（**未做**）」 | `components/blend2d/lib/v85x/BUILD.md:10-14,48-55` ←→ `blend2d/platforms.md:17,125`、注册表 |
| A3 | ⬜ | 知识/派生页 5 处读数打架（nanovg「未上真机」vs 已上、i18n 页说没有 `textview-fields.md` 而该页已存在、fonts cmap 判据是否已替代体积判据、`textview-fields.md` 内部 roll* 前后不一致） | `packages/README.md:30`、`i18n-multilang.md:209-211`、`fonts/platforms.md:56`、`textview-fields.md:85/112` |

## B. 报告里承诺但没进计划 —— 9 项

| # | 状态 | 事项 | 依据 |
|---|---|---|---|
| B1 | ⬜ **P0** | 按需面分层 `describe(section=)` —— `contractPerOpMax=900`，最长 `build_ui_flow` 已 **757/900（余 143）** | `REVIEW-2026-10-04.md:40-49,134` |
| B2 | ⬜ | 检索召回收口：要「top-1 ≥85% 进闸门」；现状每组阈值 = 实测−1、**无全局比例判据** | `AI-DEV-CAPABILITY-2026-10-04.md:29-35,61`；`check_retrieval.py:868-869,895` |
| B3 | ⬜ | watch 预览-反馈环（目标本地 <10s / 真机 <40s） | `AI-DEV-CAPABILITY:37-43,62-63`；`REVIEW-2026-10-04.md:105` |
| B4 | ⬜👤 | 协议调试 op 面 = 0：补工具面 **或** 把目标①改成分级目标（"知识支持级"）—— 挂着不承认会让覆盖率讨论失真 | `REVIEW-2026-10-04.md:66-73`；`REVIEW-2026-10-03.md:170,249-254` |
| B5 | ⬜ | 数字「对账」了但没「派生」（仍是手写 + 门禁比对） | `REVIEW-2026-10-04.md:51-57,133` |
| B6 | ⬜ | 「判据依赖的资产必须随仓」制度化（用例引用仓内路径 → 必须在仓且被 git 跟踪）。**部分已做**：`tests/` 路径守 + `stage_referenced_files_tracked` | `REVIEW-2026-10-04.md:80-86`；`d50f2f3` |
| B7 | ⬜ | 双源知识口径统一（仓内 `knowledge/` vs 仓外 wiki；作者机 1573+ chunk、客户机只有 `knowledge/`） | `REVIEW-2026-10-03.md:238-247,364` |
| B8 | ⬜ | `rag_index.json`(3.7MB)/`models/*.onnx`(24MB) 出库 + 拆 `project_tools.py`(2671)/`kb_tools.py`(2190) | `REVIEW-2026-10-03.md:225-235,256-267,362-366` |
| B9 | ⬜👤 | 构建产物跳过清单要不要建真源（前提：先解决 `ui_tools` 仓外双份分发，会牵动 `PUBLISH.md`） | `CONSOLIDATION.md:653-663` |

## C. 验证「最后一公里」（注册表里已登记、但没有回归通道）—— 4 项

| # | 状态 | 事项 | 依据 |
|---|---|---|---|
| C1 | ⬜👤 | **已实测平台的组件形态未回归**一组：imagecache 形态、wall_sync `zk::wall`、icons v0.2.0 真机投递、album_upload「手机微信真扫」唯一一环 | 各 `platforms.md`；`WORK_PLAN §五` 的任务 D 口径**覆盖不到**这格（D 谈非代表平台） |
| C2 | ⬜ | ble：gatt 后端未上机路径 + 缺 T113/T113EMMC 库 | `ble/platforms.md:253-256,286-287`；`ble/Manifest.xml:61` |
| C3 | ⬜ | ha_bridge / mqtt 未取证清单 | `ha_bridge/platforms.md:143,152-153,163,167`；`mqtt-client-lifecycle.md:258,264` |
| C4 | ⬜ | 字库 4 条：cmap 精确判定（**疑似已完成，需核对**）/多字体链/按平台自动选版本/T113·Z20·Z21 实测补录 | `fonts/platforms.md:54-59`；`vinyl/README.md:103` |

## D. 能力与内容缺口 —— 5 项

| # | 状态 | 事项 | 依据 |
|---|---|---|---|
| D1 | ⬜👤 | ui_v1 计划控件 RichText/TableGrid/BadgeToast/Pseudo3D 排期（P1 = RichText/BadgeToast） | `components/ui_v1/components.md:65-88` |
| D2 | ⬜ | `gap-list.md §5` 待确认 7 项：drawArc 实参口径待官方确认、checkbox__ 生成器待工具链修复、F133 真机验收待设备、relayout 依赖 easyui≥2.9.0… | `components/ui_v1/gap-list.md:133-144` |
| D3 | ⬜ | easyui 版本与生成器是否官方配套 | `dynamic-screen-rotation.md:133-137` |
| D4 | ⬜👤 | i18n 两处待定：MCP 写 `\n` vs 官方 `&#x000A;`（有让设备显示"\n"两字的风险）、真机复验未做 | `i18n-multilang.md:191-193` |
| D5 | ⬜ | `ui_blocks` 未覆盖块 + `DemoControls_V85X` 缺项；含**工具侧判据缺陷**：`check_all #13` 没有 rollEnable 豁免 → 跑马灯页必然红 | `templates/ui_blocks/README.md:509-511`；`DemoControls_V85X/README.md` |

## E. 工具与发布面 —— 3 项

| # | 状态 | 事项 | 依据 |
|---|---|---|---|
| E1 | ⬜🔌 | **Z235X 设备端工具全缺**（touch/busybox/ui_test/zkshot）—— 禁拿别平台 ELF 顶替；需样机 + 工具链 | `bin_tools/z235x/README.md:10-18`；`platforms.py:60` |
| E2 | ⬜ | **`packages/easyui` 没有包卡** —— 最核心的包没有"怎么用"（`packages/README.md` 的包卡完整度表里无此行） | `packages/README.md:29,44-55` |
| E3 | ⬜ | 6 个包 `example/` 平台实测待补（rapidjson 全平台未验证、curl/paho/mbedtls/openssl/cares/mqtt-cxx） | `packages/README.md:59-60` 及各 `platforms.md` |

## F. 结构性建议（比逐条补更值钱）—— 2 项

| # | 状态 | 事项 | 依据 |
|---|---|---|---|
| F1 | ✅ | **验证债的汇总通道**：注册表里每个「未验证/不可用/缺」单元格必须在派生矩阵页可核对（`check_consistency` 已加计数对账） | 本文件 A/C/E 三节能成立就靠它兜底 |
| F2 | ⬜ | **报告承诺的汇总通道**：评审/能力报告写完必须回填本表（否则又回到"靠人记得"）。候选做法：报告模板加一节「进计划的条目」，或让门禁扫报告的"留给后续"段落并比对 `TODO.md` | 本表 §B 的成因 |

## G. 只算知识库质量（不是工作任务）

- 「未核 / 待验证」清单：**36 处 / 17 篇**，其中 **1 处没给"怎么复验"**（`custom-render-paths.md:115`）
  —— 补一句复验方法比补一句结论有用（`python scripts/gen_unverified_report.py`）。
- 待补判据队列 **97 篇**（无问法登记 79 篇）—— 属写作工单，随任务做。
