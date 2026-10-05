# 待办总清单（WORK_PLAN §四 的补充通道）

> **为什么要单独一张表**（2026-10-05 全仓盘点结论）：`WORK_PLAN §四` 只从主线文档汇总，
> 于是**「评审报告里写下的承诺」与「注册表/组件页里的验证债」没有任何回填通道** ——
> 实测回填率 **2/13**（REVIEW-10-03 §6.4 的 0/4、REVIEW-10-04 §1.2 的 1/6、
> AI 能力报告的 1/3），另有 15 项验证债散在 `components/*/platforms.md`、`packages/*/`。
> 本表就是那两条通道的落点：**从报告与注册表反向汇总**，进表才算进计划。
> 状态：⬜ 未开工 / 🔄 进行中 / ✅ 已完成 / ⏸ **已决定缓办**（有明确理由压后，不阻塞当前计划；重启需需求方说一声）｜ 👤 需需求方拍板 ｜ 🔌 需设备/样机
> 纪律：完成一项就在原处改 ✅ 并注明落在哪个提交；**不要另抄一张表**。

## A. 真源与知识页的自相矛盾（会直接误导 AI 选型）—— 3 项

| # | 状态 | 事项 | 依据 |
|---|---|---|---|
| A1 | ⏸👤 | **vinyl 在 V85X 仍不可编，但卡点换了**（2026-10-05 真机工具链实编）：`nanovg.h` 那关**已过**（随仓 `.so` 与设备 `/lib` 那份 md5 逐字节相同），真正的卡点是 `zk_vinyl.cpp:40` 的 **`misc/image_utility.h`** —— 不在任何 easyui 包（V85X 2.9.0 / Z20 2.6.0 的 `include/` 都无 `misc/`）、不在仓、设备 `libeasyui.so` 也无 `misc::*` 符号。**出路（两条都已记档、暂不选）**：① 厂商补该头（+实现）；② 把 `misc::image_load/bitmap_scale/bitmap_create/bitmap_destroy` 改写成 easyui 真有的 `utils/BitmapHelper.h`。另：`fun install` 仍拉不到 nanovg（`FATAL 未找到依赖包`）。**⏸ 决定（需求方 2026-10-05）：nanovg 这一路在 V85X 暂不处理、优先级放低，后期需要时再补** —— 所以本项**不阻塞任何当前计划**，两条出路保持记档、不排期；要重启时先看本节「依据」列的两条实测证据 | 实测：`zk_vinyl.cpp:40` fatal error；`platform_capabilities.json` vinyl/V85X 行 |
| A2 | ✅ | blend2d V85X **转正为「可用（已验）」**：本仓自编档 `lib/v85x/`（1,846,636 B / md5 `ED1569…`，NEEDED = `libstdc++.so.6` + `libc.so`(musl) + `libgcc_s.so.1`）→ `fun build` **169/169 → `libzkgui.so`** → 门面 `zk::b2d::Canvas` 真机跑通（480×480 **avg 5.010 ms/帧**、800×1280 avg 7.862 ms/帧，`savePng` 出图目检正确）。真源与 4 处文档已同步。⚠️ 该档**未 strip**；`blend2d.h` 不在仓 → 随仓可复现的是「链接 + 真机运行」 | 2026-10-05 实测；`components/blend2d/lib/v85x/BUILD.md` |
| A3 | ✅ | 5 处读数打架全部判定并修正：① nanovg「未上真机」错（`platforms.md` 对）② i18n 页说没有 `textview-fields.md` 错（该页已存在）③ fonts 把 cmap 列为「待办」错（它早已是**主判据**，体积阈值只是兜底）④ `textview-fields.md` 两处自相矛盾（`rollStep` 单位已定于 `ui_schema.json` 真源）⑤ 顺带：`packages/README.md:30` 两处错（nanovg 状态 + 该包是唯一缺 `example/` 的） | 见本表 §C5 与各文件现值 |

## B. 报告里承诺但没进计划 —— 9 项

| # | 状态 | 事项 | 依据 |
|---|---|---|---|
| B1 | ✅ | 按需面分层 `describe(section=)` **已落地**：段划分 = 对 `contractOrder` 的**精确划分**（`skeleton` / `flow` / `returns` / `rules` / `refs`，+ `all` = 全文），真源在 `op_spec.json.tiers.onDemand.sections`；`op_spec_loader` 加 `sections()` / `section_ids()` / `render_section()` / `render_default()`，并把渲染器拆成 `_field_text` + `_render_parts` + `_join_parts`（分隔符只有一处口径）。**只加不破**：全文 ≤ 上限时默认形态**逐字节等于全文**（重构时用 48/48 op 的快照比对验证，sha256 相同），超限才退化成 `skeleton` + 段目录（长度由实测派生）。实测：单段最大 **645**（`i18n_to_json:rules`）、默认形态最大 **892**，硬判据从"全文 ≤900"迁到"默认形态 + 单段"（全文超限降为告警——那正是本机制的目的）。工具面：`describe:<名>` + `args={"section":…}`、资源 `flythings://ops/<名>/<段>`、未知段报 `UNKNOWN_SECTION`（已进域⑫码表）+ 合法段清单。契约用例 15 条（`tests/test_op_sections.py`）。⚠️ 顺带订正一处**长期错数字**：`budget.note` 原写「最长 build_ui_flow 757（余 143）」，实测最长是 `i18n_to_json` 805 —— 该错数字同时活在TODO 与评审报告里（真实余量一直更小）；已改并把「最长 `<op>` 已 N/上限」纳入门禁对账，防它再次静默过期 | 本轮提交；`tests/test_op_sections.py`；`op_spec.json.budget.note` |
| B2 | ✅ | 检索召回收口：**全局 top-1 比例判据**已进闸门（`GLOBAL_TOP1_MIN_RATIO = 0.72`；输出 `[PASS] 全局 top-1 708/925 = 76.5% ≥ 72%（98 组）`，分母由实跑 summary 现算、不写死），与每组 `min_top1` 互补（那个管单组回退、这个管"多组各掉一点"的整体滑坡）；契约用例钉四条结构性质：判据存在 / 阈值是登记常量且默认生效 / 分子分母由 summary 现算 / `main()` 真的判且失败进 `bad`。**基线（2026-10-05 实测）**：98 组 / 925 问法 / top-1 **708 = 76.5%**、对照组 9/10、症状组 72/84、未登记问法 0 篇；阈值取 **72%（留 4.5 点 ≈42 条余量）**，**不取 85%** —— 85% 是目标值，现状卡它 = 开局即红、判据当场作废（抬高阈值属"做到了才改"）。契约用例：`tests/test_search_quality.py::TestGlobalTop1Gate` | `AI-DEV-CAPABILITY-2026-10-04.md:29-35,61`；`scripts/check_retrieval.py` 的 `GLOBAL_TOP1_MIN_RATIO` + `global_top1_verdict`（提交由上级统一做） |
| B3 | ⬜ | watch 预览-反馈环（目标本地 <10s / 真机 <40s） | `AI-DEV-CAPABILITY:37-43,62-63`；`REVIEW-2026-10-04.md:105` |
| B4 | ⬜👤 | 协议调试 op 面 = 0：补工具面 **或** 把目标①改成分级目标（"知识支持级"）—— 挂着不承认会让覆盖率讨论失真 | `REVIEW-2026-10-04.md:66-73`；`REVIEW-2026-10-03.md:170,249-254` |
| B5 | ⬜ | 数字「对账」了但没「派生」（仍是手写 + 门禁比对） | `REVIEW-2026-10-04.md:51-57,133` |
| B6 | 🔄 | 「判据依赖的资产必须随仓」制度化：**本轮已补** `stage_test_hermetic` 的 ②③④ —— 此前 docstring 承诺四类、代码只实现 ①`temp/` + ignore，`git ls-files` 的结果是**死代码**；实测三条反例（存在但未入库的 `.ftu` 夹具 / `../ui_tools/x.py` / 写死本仓绝对路径）当时都能静默通过，现分别报 `untracked-path`/`outside-repo`/`repo-abs-path`（契约用例 4 条，含"`'/'`、`'..'`、`'C:'` 这类片段不许假红"）。**剩余缝隙（需拍板，只写建议未实现）**：①`stage_referenced_files_tracked` 的被引用后缀表只有 `.json/.py/.md` → `.ftu/.png/.cc/.h/.so` 等**看不见**（扩表实测多出 1 处假红：`_nanovg_probe.so` ← `REVIEW-2026-10-03.md`，那是报告在描述本机探针产物）②hermetic 字面量只扫 `tests/**/*.py` → `tests/fixtures/*.json`、`tests/README.md`、`ui_tools/*.py` 不在扫描面（实测**全仓 tracked 文本写死本仓绝对路径 = 0 处**，故无现患）③该判据用**手写 skip 清单**而非 `git check-ignore` → ignore 目录里的 `.json` 一旦被引用就假红（实测现 0 处）④路径在运行时拼装（`os.path.join`/f-string）时静态字面量判据看不见 | `REVIEW-2026-10-04.md:80-86`；`d50f2f3`；反例与命令见 `scripts/check_consistency.py::_test_hermetic_hits` docstring、`tests/test_hermetic_paths.py` |
| B7 | ⬜ | 双源知识口径统一（仓内 `knowledge/` vs 仓外 wiki；作者机 1573+ chunk、客户机只有 `knowledge/`） | `REVIEW-2026-10-03.md:238-247,364` |
| B8 | ⬜ | `rag_index.json`(3.7MB)/`models/*.onnx`(24MB) 出库 + 拆 `project_tools.py`(2671)/`kb_tools.py`(2190) | `REVIEW-2026-10-03.md:225-235,256-267,362-366` |
| B9 | ⬜👤 | 构建产物跳过清单要不要建真源（前提：先解决 `ui_tools` 仓外双份分发，会牵动 `PUBLISH.md`） | `CONSOLIDATION.md:653-663` |
| B10 | ⬜👤 | **检索口径：wiki 随仓之后，阈值与"整理页 vs wiki 页"的排序怎么定**（这条是 B2 判据抓出来的真变化）。实测：`wiki/` 入库并进 `rag_index`（1923 → 2617 chunks）后，全局 top-1 由 **708/925 = 76.5% 降到 648/925 = 70.1%**；**随后远端把 wiki 按口径裁到 122 篇重测，仍为 642/925 = 69.4% —— 即这 7 个点主要不是「wiki 抢答」造成的**（裁剪后几乎没回升，甚至略降），主因待查（候选：wiki 页与 `knowledge/` 整理页文本高度重叠，把向量/BM25 的打分摊薄了）；未命中 277 条里 **92 条 top-1 是 wiki 页**（其中 **66 条期望文档仍在 top-3**，例「多媒体…」被 `multimedia/video.md` 抢答、期望页退第 2），另 185 条是仓内文档答错。**两条路（需拍板）**：① 接受新基线，逐步做两者排序收口（阈值先按 0.67 留 3 点余量）；② 把 wiki 移出检索范围（`kb_index_roots` 随仓根 + 重建索引），阈值调回 0.72。**不擅自选** | `scripts/check_retrieval.py` 的 `GLOBAL_TOP1_MIN_RATIO` 注释（含复现命令）；实测明细 `%TEMP%\ret_after_merge.json` |

## C. 验证「最后一公里」（注册表里已登记、但没有回归通道）—— 4 项

| # | 状态 | 事项 | 依据 |
|---|---|---|---|
| C1 | ⬜👤 | **已实测平台的组件形态未回归**一组：imagecache 形态、wall_sync `zk::wall`、icons v0.2.0 真机投递、album_upload「手机微信真扫」唯一一环 | 各 `platforms.md`；`WORK_PLAN §五` 的任务 D 口径**覆盖不到**这格（D 谈非代表平台） |
| C2 | ⬜ | ble：gatt 后端未上机路径 + 缺 T113/T113EMMC 库 | `ble/platforms.md:253-256,286-287`；`ble/Manifest.xml:61` |
| C3 | ⬜ | ha_bridge / mqtt 未取证清单 | `ha_bridge/platforms.md:143,152-153,163,167`；`mqtt-client-lifecycle.md:258,264` |
| C4 | ⬜ | 字库 4 条：cmap 精确判定（**疑似已完成，需核对**）/多字体链/按平台自动选版本/T113·Z20·Z21 实测补录 | `fonts/platforms.md:54-59`；`vinyl/README.md:103` |
| C5 | ⬜ | **`device_font_check.py` 在 V85X 上字体扫描直接失败**（2026-10-05 实测复现）：本机固件 `ls -l` 出 **ISO 日期**（`2026-09-18 06:51`），而 `:158` 拿**月份名**做锚点 → `size=None` → `collect() fonts=[]` → `verdict: "no_font"`。设备上**明明有** `/res/font/pocketgame.ttf`（1,094,104 B）。后果：**cmap 硬判据根本没跑**，还会误报「缺中文字库」触发无谓投递。修法：`:158` 改「ISO 日期 + 月名」双锚点 | 实测命令与输出在 `_a123_scratch/`；`components/fonts/scripts/device_font_check.py:158` |
| C6 | ⬜ | **随仓 `bin_tools/v85x/busybox` 在该设备上不可用**：`/tmp/bb ls -l …` → `applet not found`（`ls/md5sum/sh/cat/find/du/echo` 全一样，无参也一样），而 strings 显示确实是 `BusyBox v1.36.1`。`device_font_check.py:48` 的 `BUSYBOX_LOCAL` 正指向它 → **兜底路径同样是坏的**。未深挖配置（疑 `FEATURE_INDIVIDUAL` 单 applet 构建） | 2026-10-05 实测；`bin_tools/v85x/busybox`、`device_font_check.py:48` |

## D. 能力与内容缺口 —— 6 项

| # | 状态 | 事项 | 依据 |
|---|---|---|---|
| D1 | ⬜👤 | ui_v1 计划控件 RichText/TableGrid/BadgeToast/Pseudo3D 排期（P1 = RichText/BadgeToast） | `components/ui_v1/components.md:65-88` |
| D2 | ⬜ | `gap-list.md §5` 待确认 7 项：drawArc 实参口径待官方确认、checkbox__ 生成器待工具链修复、F133 真机验收待设备、relayout 依赖 easyui≥2.9.0… | `components/ui_v1/gap-list.md:133-144` |
| D3 | ⬜ | easyui 版本与生成器是否官方配套 | `dynamic-screen-rotation.md:133-137` |
| D4 | ⬜👤 | i18n：换行写法定案 **已落地**（2026-10-05 需求方拍板统一 `&#x000A;`：`_escape_tr`/`_write_tr` 改写字符引用、读侧保留历史字面 `\n` 兼容、知识页 §6 与用例同批改）；**仍待办 = 真机复验**（`/tmp/tr/` 与 `languagePath`、`fun launch` 不推、切语言刷新） | `i18n-multilang.md` §6/§10；`tests/test_i18n_tools.py::TestTrEscaping` |
| D5 | ⬜ | `ui_blocks` 未覆盖块 + `DemoControls_V85X` 缺项；含**工具侧判据缺陷**：`check_all #13` 没有 rollEnable 豁免 → 跑马灯页必然红 | `templates/ui_blocks/README.md:509-511`；`DemoControls_V85X/README.md` |
| D6 | ⬜👤 | **fun 工具链缺陷（待厂家修）：`fun build` / `fun pack` 不产出 i18n 的翻译 json** —— `.tr`（XML）→ 设备读的那份 json 这一跳**没有任何一步由 fun 完成**：实测 `fun.exe --help` 与全部 16 个子命令 help 无 i18n/tr/locale 选项；Go 包列表（`github.com/zkswe/fsc/internal/`）内无 i18n/lang/locale/tr 包；全二进制仅 1 处 `i18n` 字面量、0 处 `/res/tr`；`fui.exe` 只有 json↔ftu；`fun create` 内嵌模板（fv 新框架）不含 i18n 目录。而**设备侧只认 json**（反汇编 `LanguageManager::loadContent`：`ConfigManager::getLanguagePath()` 取目录 → `string::append` 拼语言代码 → 拼扩展名 → `JsonHelper::readJsonFile`；该文件缺失时回退「语言代码-显示名」那一份）。后果：改完 `.tr` 直接 build/pack 上机 = 翻译不生效（logcat 刷 `name: %s not found value !!!`）。MCP 现状由 `i18n_tools.py` 自己补这一跳（`action=to_json`）—— ⚠️ 顺带一条**我们的**隐患：它把推送目录写死 `/tmp/tr/`，而生效目录由设备 EasyUI.cfg 的 `languagePath` 决定（IDE 默认 debug=`/mnt/extsd/tr/`、release=`/res/tr/`）→ **推错目录同样静默不生效**。修完把 `fun_capabilities.json` 里 `bugs` 的 `no-i18n-json.status` 改 `fixed` 并注明 fun 版本 | 机读记录：`fun_capabilities.json`（新增 `bugs` 段，含 5 条静态证据）；既有旁证：`CHANGELOG.md:585`（V553 真机 2026-09-08：设备加载 json、`fun launch` 不推 i18n）。**未核**：真机实跑 `fun build`+`fun pack` 复核；官方 IDE 那条路是否转 json |

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
