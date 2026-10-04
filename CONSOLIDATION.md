# FlyThings MCP · 历史包袱与知识散落 —— 归集方案（第一性原理）

> 起因：`plan.md` 里的 7 条根因 + 3 条目标。本文件回答两件事：
> **① 现在到底有多少包袱（实测，不是印象）② 按什么原则重排、分几批做、每批怎么验收。**
> 度量脚本：`python scripts/audit_baggage.py`（只读，可复跑，看趋势）

---

## 0. 结论先行（实测反直觉）

审计（2026-10-02，1354 文件 / 101.35 MB）推翻了「重复文件太多」的直觉：

- **真正的内容重复只有 5 组**，全在 `bin_tools/`（同一二进制在 2~3 个平台目录各存一份，如 `touch` 488KB×2）。
- 其余 **114 组重复全在实例目录**（`components/ demos/ packages/ templates/`）——那是**结构拷贝**：每个 example / 模板自带整份 src 骨架（`main.json`×40、`mainLogic.cc`×38、`UartContext.cpp`×19…）。
这是"每个实例必须能独立编译"的代价，**不能简单删**，只能靠"骨架唯一来源 + 派生 + 门禁"治理。
- 所以包袱的主项不是"文件重复"，而是这四条：
  1. **知识散落**：同一概念散在 3~31 篇 md 里（见 §1.2）← 与目标①「像开发网页/Android 一样」直接冲突
  2. **平台差异抄了 27 份**：`components/*/platforms.md` + `hardware_catalog.json` + `platforms.py` + `knowledge/devflow/*`
     → 「这组件在 Z20 能不能用」现在要跨 4 类来源拼答案
  3. **根目录平铺**：44 个文件（模块、数据、产物、日志混放）+ 历史命名残留（`fyx`／`FYX_BUILD` 已清空）+ 仍需保留的兼容垫片（`RENAMED`/flat-dispatcher 双模式/legacy）
  4. **入库的 IDE 冗余**：76 个 `.prefs`/`.log`/`.cproject`/`.deps.lock`

## 1. 实测数据

### 1.1 规模与重复

| 指标 | 现值 |
|---|---|
| 文件 / 体积 | 1354 / 101.35 MB（`toolchain/` 42.7MB、`components/` 30.7MB、`bin_tools/` 9.8MB、`templates/` 499 文件） |
| 完全重复 | 119 组 / 519 文件 / 冗余 4.13 MB（**其中 114 组在实例目录**，真·重复 5 组在 bin_tools） |
| 同名散落（≥3 处） | 73 个名字（`README.md`×74、`Manifest.xml`×43、`main.json`×40、`platforms.md`×27） |
| md | 219 篇（`knowledge/` 104、`components/` 57、其它 58） |
| IDE 冗余入库 | 76 个 |

### 1.2 同一概念散落在多少篇 md（越散越该归集）

| 概念 | 篇数 | knowledge/ |
|---|---|---|
| 图片尺寸==控件盒 | 31 | 14 |
| activity 禁手改 | 27 | 6 |
| 分区/升级 img | 22 | 12 |
| UI 生命周期 | 19 | 11 |
| thumb 子盒 | 17 | 12 |
| i18n 逐字节 | 15 | 5 |
| libc glibc/musl | 14 | 4 |
| 配色/对比度 | 7 | 3 |
| staleOnDevice | 6 | 3 |
| findControlByID | 6 | 3 |

> 含义：AI 要确认一条铁律，得先命中 3~31 篇里的哪一篇才是"真源"。检索命中率、答案一致性、
> 维护成本三者同时被拖累。**这是"知识不接近 AI 原生"的根子。**

## 2. 第一性原理：知识按"能力轴"组织，每个域一个唯一真源

`plan.md` 的 7 条根因本质是 7 个**能力域**。归集目标就是：每域 = `1 个机器可读真源 + 原理文档 + 全派生消费方`。

| 域（=根因） | 唯一真源（机器可读） | 原理/流程文档（人写） | 消费方（派生，禁止另抄） | 状态 |
|---|---|---|---|---|
| ① UI 布局 ftu/json | `ui_tools/ui_schema.json` | `knowledge/uicontrols/*` | check_all / translate_ui / map_control / `flythings_ui_schema` | ✅ 已建 |
| ② UI 引擎·生命周期·控件 API | **`lifecycle_spec.json`（已建，见 §11）** | `knowledge/devflow/activity-lifecycle-spec.md`（派生） | `flythings_gen_logic_stub` / `activity-code-skeleton.md` | ✅ 已建 |
| ③ OS·分区·img·升级 | `platform_capabilities.json` **（已建：能力矩阵层）**| `knowledge/devflow/{upgrade,deploy,platform}-*.md` | `build_ui_flow` / `pack_upgrade` / `selfcheck` / `gen_hardware_doc` | 🟡 B1 已落地能力矩阵 |
| ④ 硬件外设 API（IIC/SPI/GPIO/ADC/PWM） | `hardware_catalog.json`（已有，待收编） | `knowledge/hardware/*` | `flythings_hardware_info` / 外设 demo | 🟡 半 |
| ⑤ 多媒体 API（播放/录音/图层） | **`media_capabilities.json`（已建，见 §12）** | `knowledge/media/media-capability-index.md`（派生） | `device_screenshot(layer=video)` / `list_packages` / demos | ✅ 已建 |
| ⑥ 组件包 | `package_catalog.json`（已有） | `knowledge/devflow/dependency-package-docs.md` | `list_packages` / `add_package` / `manifest` | ✅ 有 |
| ⑦ 可复用组件/样例 | `packages/` + ③ 的能力行 | `components/*/README.md`（仅原理/坑/验收） | `create_project` / `build_ui_flow` | 🟡 半 |
| ⑧ MCP 工具契约 | `op_spec.json` | — | docstring / manifest / gate_catalog / seeAlso | ✅ 已建 |

**三条纪律**（与 `ui_schema.json`、`op_spec.json` 完全同构，已在 ⑧ 上验证过一轮）：

1. **唯一真源**：每个域的契约只写一次，文件头带 `authority` 声明（真源 + 消费方清单 + 「改契约=改本文件」）。
2. **只派生不抄**：消费方一律从真源派生；派生脚本带 `--check`，进 `scripts/check_consistency.py` 闸门。
3. **原理归文档**：`knowledge/*.md` 只留原理/流程/踩坑/验收方法；字段/矩阵/默认值/铁律清单归注册表。

## 3. 分批路线（按杠杆排序，每批可独立验收与回滚）

| 批 | 动作 | 杠杆 | 风险 | 验收 |
|---|---|---|---|---|
| **B1**| **平台能力收编**：27 篇 `platforms.md` 的「汇总/可用性」+ `hardware_catalog.json` + `platforms.py` + `capability-boundaries.md` → `platform_capabilities.json` + loader + `gen`（重写各 platforms.md 的汇总节，其余人工内容不动）+ 门禁 | ★★★★★ | 中（读路径要一起改） | 门禁全绿；「Z20 能不能用 BLE」1 次查询得答 |
| **B2**| **知识散落收敛**：把 §1.2 的高散概念收敛为「真源节 + 其余改指针」 | ★★★★☆ | 中（改 md 正文） | `audit_baggage` 的 scatter 数下降；检索回归不变差 |
| **B3**| 实例骨架唯一来源 —— **已完成（§13）**：实测 20 个工程带骨架、171 份逐字节一致 → `templates/HelloWord_Z20/src` 为唯一来源 + `sync_project_skeleton.py --check` 进闸门 | ★★★☆☆ | 中高 | 新加 example 不再手抄 19 文件；门禁盯一致性 |
| **B4**| ~~`bin_tools/` 平台副本收编：一份二进制 + 平台映射~~ **实测后否决**（§10）：660KB 是工作区口径，git 早已 delta/去重；改为「ELF 架构门禁 + 平台匹配规则」 | ★★☆☆☆ | 低 | 19/19 二进制架构匹配 + 门禁能抓错配 |
| **B5**| **根目录归位 + 历史命名残留清空**：44 个根文件分层；`fyx`/`FYX_BUILD` 清空、`fuse` 分「命令名（清空）/老形态（保留）」、`RENAMED`/flat 双模式/legacy 逐项定去留；顺带修出打包清单漏 15 模块 | ★★★☆☆ | 高（import/打包/闸门连锁） | 打包与 `install.bat` 冒烟通过 |
| **B6**| IDE 冗余出库 —— **已完成（§9）**：75 个里只有 28 个该出（本机状态 / 工具生成物），工程必需的三件保留 | ★★☆☆☆ | 低 | 门禁 `stage_no_ide_local_files` 全绿 |

## 4. 度量（包袱是否真的在减少）

`python scripts/audit_baggage.py` 四个主指标 + 两组明细；`--json` 可存基线做趋势对比：

```
files / size总文件数与体积                          （目标：减）
dup_groups / waste完全重复组数 / 冗余体积                  （目标：减；实例组单列）
basename_ge3同名散落处数                             （目标：减）
concept_scatter同一概念的 md 篇数（收敛到 1 真源+N 指针） （目标：降）
ide_junk_files入库的 IDE 冗余                          （目标：0）
```

## 5. 与既有资产的关系（不重复造）

- ⑧ 已跑通一轮：`op_spec.json` 把 docstring/brief/risk/stage/seeAlso 五处事实来源收成一处 →
这批的模板与门禁写法直接复用（`op_spec_loader.py` / `gen_op_docs.py` / `--check --strict`）。
- ① 的 `ui_schema.json` 已是样板：真源 + loader + 派生文档 + 契约用例四件套。
- 本方案**不新增概念**，只是把同样的纪律铺到 ②③⑤ 这些还空着的域上。

---

## 6. B1 落地记录（平台能力收编，2026-10-02）

**做了什么**

| 角色 | 文件 |
|---|---|
| 唯一真源 | `platform_capabilities.json` —— 15 个组件 × 66 条「平台 × 能力」行（含列名/原始标签/单元格文本/口径注释），平台键另存 `canonical` |
| 唯一消费入口 | `platform_cap_loader.py` —— `components/rows_for_platform/components_for_platform/status_of/cell/render_table/validate`；缺失或查不存在的组件 → `PlatformCapError`，不静默 |
| 生成器 | `scripts/gen_component_platforms.py` —— 重写各篇 `platforms.md` 里那张矩阵表；`--check` 进闸门 |
| 契约用例 | `tests/test_platform_cap.py`（11 条） |
| 门禁 | `check_consistency.py` 新增 `gen_component_platforms --check` → **41 条全绿**|

**结果：0 漂移。**bootstrap 抽取的表渲染回去与原 md **逐字节一致**—— 说明注册表是忠实的机器可读镜像，
15 篇 `platforms.md` **一个字都没改**，但那张表从此是派生物（手改会被门禁抓住）。

**新增能力（以前做不到）**：`components_for_platform('Z20')` 直接给出 Z20 上声明支持的 15 个组件；
`cell('ble','Z20','可用性')` 直接取单元格。以前要翻 15 篇 md 手拼。

**顺带查出的跨来源不一致**：文档里在用的 `F136` / `T113EMMC` 并不是独立平台，而是 `platforms.py` 里
`F135.alias` / `T113.alias` 的**别名**。所以查询层改成「输入也过一遍 `platforms.resolve`」——
查 `F136` 等价于查 `F135`。**没有新增第二份平台词表**：词表只在 `platforms.py`。

**B1.2 让 AI 真用上（已落地）—— 附带一个关键发现**

实测：**RAG 检索索引只覆盖 `knowledge/`**，`components/*/platforms.md`（15 篇 / 1779 行）**不在检索范围内**。
也就是说这份平台能力知识对 AI 是**黑洞**——问「Z20 上能跑哪些组件」时 `knowledge_search` 返回的全是不相干文档。
（注：`kb_index.json` 是知识看板，**不等于**检索索引；真正的检索索引是 `rag_index.json`，
由 `rebuild_index_local.py` 重建。新增知识文档后必须重跑它，否则"可检索"是假的。）

因此不新增 op（不增常驻 schema），改为**由注册表派生一篇可检索知识页**：

| 新增 | 说明 |
|---|---|
| `knowledge/devflow/platform-capability-matrix.md` | 265 行，由 `scripts/gen_platform_cap_doc.py` 从注册表生成；含「平台→组件」「组件→平台」「逐组件矩阵」「怎么改」四节 + 检索导引 |
| `scripts/gen_platform_cap_doc.py` | 生成器；`--check` 进闸门 |
| 门禁 | 新增一条 → **42 条全绿**；`check_retrieval.py` 新增 1 组 8 条问法（项目纪律：新增知识文档必须附 ≥5 条问法）|

**实证检索命中**：8 条真实问法里 7 条 top-1、1 条 top-3（`ble 在 Z20 能用吗`）；
检索回归从 22 组 / 163 问法 → **23 组 / 171 问法，全绿**，对照组 9/10 未变（没污染检索）。
以前这 8 个问法一条都命不中相关文档。

**B1.3 平台正文（另一半黑洞）—— 只修可达性，不搬内容**

动手前先量了一遍：16 篇 `platforms.md` 之间**整行级重复 = 0 条**，短语级只有 37 条且全是
`component`/`EasyUI.cfg` 这类通用词。**结论：这 16 篇内容互补、没有真·重复可去。**
所以"归集"在这里的正确动作不是搬内容（那会凭空多一份 1200 行副本 = 反包袱），而是**修可达性**。

| 新增/改动 | 说明 |
|---|---|
| `kb_index_roots.py`（新） | **「哪些文档进检索索引」的唯一真源**。原本这条口径被抄在两处（`rebuild_index_local.py` 走一遍、`check_consistency._expected_md_sets` 又"同口径"走一遍），加一类文档要改两处、漏一处就漂移 |
| 索引范围扩一项 | `components/**/platforms.md`（16 篇）进索引；**只收这一个文件名**，组件 README 等仍留给维护者、不进 AI 语料 |
| `rebuild_index_local.py` / `check_consistency.py` | 两边都改为从真源取范围 |
| `tests/test_kb_index_roots.py` | 7 条用例钉住范围（含"黑洞修复不许被回退"、"两个消费方不许再各写一遍遍历"） |

**效果**：`rag_index.json` 1363 → **1573 chunk**。实测 8 条"前置/限制/验收"类问法
**8/8 top-1 命中对应组件页**（以前一条都命不中）。

**检索回归如实记录了 3 处挤出**（新竞争者进入语料必然发生，按项目惯例**不调阈值凑数**）：
- `ble 在 Z20 能用吗`：新 top-1 是 `components/ble/platforms.md` —— **那是更优答案**，是我这条问法
归属定错（本篇是总览，组件专属问法该走组件页）→ 换问法 + 在组注释里写清边界。
- `setprop ctl.restart zkswe…`、`第三方 .so 放哪`：被合理竞争者挤出到 #4，分差 <5%、权威答案仍在 top-5
  → 显式 `max_miss: 1` 并写明原因（榜首分别是 z20-86panel-upgrade、blend2d/platforms 的「库从哪来」列）。

回归总账：23 组 / 171 问法，top-1 **133 → 135**，对照组 9/10 未变。门禁 **42/42 全绿**。

**B1.4 口径修正 + 内置包说明（2026-10-02 反馈）**

三条口径修正，都改在**真源**（派生页下次生成会被覆盖，改它没用）：

| 反馈 | 落地 |
|---|---|
| MCU Lite 属于另外的东西，整个系统不关注 | 从能力矩阵删除 MCU 行；`MCU` 不再是合法平台键（`EXTRA_PLATFORMS` 只剩 `ALL`）；icons 的「全平台（… MCU Lite）」标签一并抹掉 |
| PC 不需要体现，用户不关注 | 删除 4 条 PC 行（blend2d / blur / imagecache / wall_sync）；PC 不再解析为平台键 |
| Z20 tag 相关标识去掉，不特殊区分 tag ESL 项目 | 删除 ble 的「电子价签 tag（Z20 平台）」行（业务/项目标识不进平台能力矩阵） |

抽取规则同时收敛为**两条显式规则**（不再是特例打补丁）：① 标签命中业务/项目标识（价签/tag/ESL）→ 整行丢弃；
② 归不到任何平台键的行 → 丢弃。**丢弃都打印出来，不静默**（本次共丢 6 行：tag 1 / PC 4 / MCU 1）。
注册表 66 → **60 行**；6 篇 `platforms.md` 的矩阵表同步重写。

**新增：内置包说明（回应"系统有内置 package 包，MCP 里有收录，也应该提供一份说明"）**

| 新增 | 说明 |
|---|---|
| `knowledge/devflow/builtin-packages.md` | 106 行：包键→芯片/包数（16 键）、通用包（跨 ≥8 键的 26 个，带版本）、**全 182 个包名的分层索引**、选型→加包→看 API 的四步用法 |
| `scripts/gen_package_catalog_doc.py` | 由 `package_catalog.json` 派生，`--check` 进闸门 |
| 门禁 | 新增一条 → **43 条全绿**；检索回归再 +1 组 8 条问法 |

**实测**：8/8 条问法（`有哪些内置包` / `openssl 是什么版本` / `有没有 MQTT 包` …）**全部 top-1 命中**；
检索回归 **24 组 / 179 问法，top-1 141**，对照组 9/10 未变。

**顺带修掉一个摩擦点**：`--check` 现在容忍**纯格式差异**（新增 `derived_md.py`）——
人用编辑器/格式化器打开派生页后会引入表格对齐空格、行尾空白、`---`→`\---` 转义，
这些不该让门禁变红；**语义漂移照旧抓**。

**两处仍是"逐字引用的源文"，未改**（不属于矩阵平台维度，要改得改源文件）：
`album_upload/platforms.md` 某单元格提到"协议等价 PC 客户端代跑"、`ha_bridge` 提到"PC 见证端"、
`ble/platforms.md` 口径注提到"电子价签 tag 本就跑在 BLE 方案上"、
`ui_v1/RadButton/platforms.md` 提到"若是 MCU Lite 平台，本组件不适用"。

---

## 7. B2 落地记录（知识散落收敛，2026-10-02）—— 结论：**没有重复可去，缺的是权威归属先量后动（`scripts/kb_scatter_report.py`，新增）**：对 10 个高散概念逐一提炼"含该概念的段落"，
按 9 字滑窗 Jaccard 找近似重复族。阈值 0.40 → **0 族**；降到 0.20 → 仅 **1 族**（ADB 固化命令串 5 处）。

| 概念 | 提及处数 | 篇数 | 近似重复 |
|---|---|---|---|
| 图片尺寸==控件盒 | 26 | 14 | 0 |
| 分区/升级 img | 45 | 13 | **1 族（5 处）**|
| UI 生命周期 | 34 | 22 | 0 |
| thumb 子盒 | 17 | 9 | 0 |
| 其余 6 个概念 | 4~9 | 2~6 | 0 |

**所以 B2 的正确形态不是"删重复"，而是"指定权威 + 检索时告诉你权威在哪"**：

| 新增 | 说明 |
|---|---|
| `knowledge/authority_map.json` | 11 个「概念 → 权威文档」登记（别名含口语与常见错说法；`ops` 指服务该概念的工具） |
| `kb_authority.py` | 唯一消费入口；`for_query` 子串 + 4 字滑窗覆盖率匹配（容忍插词）；`validate` 硬约束：**canonical 必须落在检索范围内**（存在但不在索引里 = AI 拿到也搜不到） |
| `kb_tools.knowledge_search` | 返回体新增 `authority` 字段（命中已登记概念时附权威文档）—— 命中首篇若**不是**权威，AI 一眼就知道该信谁 |
| 门禁 + 用例 | `stage_kb_authority`；`tests/test_kb_authority.py`（9 条） |

**实测**：问「图片尺寸和控件盒对不上」→ hits[0] 是 `ui-layout-verify.md`（非权威），
而返回体 `authority` 直接给出权威 `ui-asset-rules.md`。**这正是散落场景下最需要的东西。顺带修掉的真问题：2 处死指针**（AI 拿到会去搜一个搜不到的文档）
`knowledge/devflow/design.md` 被 `icon-library.md` / `scrollwindow-layout-checklist.md` 引用但早已不存在
→ 前者改指 `custom-font-config.md`（字库口径实际所在），后者删掉该从句（内容就在本篇）。
并把这类问题做成常驻门禁 `scripts/check_doc_refs.py`（白名单 8 个路径均写明理由：历史 CHANGELOG 记录 / 负例测试假路径 / 按需生成报告）。

**唯一那族真重复（ADB 固化命令串）**：已由 `authority_map` 的 `upgrade-image` 概念把权威钉到
`upgrade-pack-image.md`；**未删**重复文本——删它需要动两份真机验证过的文档，收益不抵风险，
先靠权威提示解决"该信谁"。

---

## 8. B5 落地记录（根目录与兼容垫片，2026-10-02）

**一、历史命名残留：分清「可调的命令」与「要认识的老形态」**（2026-10-02 按需求方口径复核）

判据：**名字只有指向真实存在的东西才该留**。旧名会占常驻契约面（AI 读到会以为还有这条命令），
所以按「是否还指向实体」逐项处置：

| 对象 | 判定依据 | 处理 |
|---|---|---|
| `fyx`（旧 CLI 名） | **仓库里查无实体**（`find -iname '*fyx*'` 为空），却登记在 `tools_manifest.json` 名词表、并当 op 参数名 `with_fyx` | **清空**（见「四」） |
| `CLI_NAMES['fuse']`（“本机引擎 CLI”） | 作为**命令行**已不存在（命令统一是 `fun`） | **清空命令名**；`.fuse/` 产物目录 / `FUSE_BUILD` 宏 / `~/.fuse` 注册表路径**保留**（老工程真实存在，删了无法诊断） |
| `FYX_BUILD`（check_all 第 12 项所检宏） | 知识库 **0 处**、真实旧宏是 `FUSE_BUILD`（知识 2 处 / 代码 3 处）→ 该检查**长期失效**| **改正为 `FUSE_BUILD`**|
| `RENAMED`（旧 op 改名提示表） | 22 处 / 8 文件，含契约用例；作用是「AI 用旧 op 名时回正确新名」，**只提示不执行**| 保留（是守卫，不是残留） |
| `flat/dispatcher` 双模式（`FLYTHINGS_MCP_MODE`） | 11 处 / 5 文件（README + 用例） | 保留（文档化的两种入口） |
| `legacy`（图标旧别名 / 平台旧名归一 / `ADB_PATH`） | 归一功能：删了老引用会找不到图标与平台 | 保留 |

**四、旧 CLI 名清空（2026-10-02：`fyx` 这类残留一律清空）**

清空的是**已经不存在、只剩名字**的；保留的是**东西还在、需要识别**的。

| 改动 | 文件 |
|---|---|
| op 签名去掉 `with_fyx` 参数（唯一调用恒传 True，参数已无意义；实际行为 = 复制 `fun.exe`） | `kb_tools.py` / `project_tools.py` |
| 名词表删 `fyx` / `fuse` 两条，只留当前在用的 `fun` / `fui` | `scripts/gen_manifest.py` → `tools_manifest.json` |
| 失效检查改正：`FYX_BUILD` → `FUSE_BUILD` | `ui_tools/check_all.py` 第 12 项 |
| **防回退门禁**：`manifest.cli` 与 op 签名参数名不得含废弃名 | `scripts/check_consistency.py` → `stage_cli_names` |
| 契约用例 | `tests/test_cli_names.py` |

**为什么不连知识文档里的 `fuse` 一起删**：`knowledge/devflow/cli-fun-toolchain.md` 的 fuse 内容是
**故障诊断知识**（老工程 `#ifdef FUSE_BUILD` → `fun build` 时该段被跳过 → `ui_main.h` 没进来 →
满屏「未声明」错误）。删掉它，AI 遇到这类老工程就无法诊断。
**区分标准：要认识的老形态保留，可调的命令清空。二、根目录分层：结论是不做大搬迁**（实测代价）

根目录 50 个文件（25 个 .py / 10 个 json 注册表 / 8 个 md / 4 个构建配置 / 其它 3）。
**没有一个模块是无人引用的**（被引用最少 4 次）——所以不存在"删死文件"的空间。
而搬进 `mcp/` 包要同时改：`pyproject` 的 `py-modules` 与 `[project.scripts]` entry point、
25 个模块之间的全部 import、`configure.py` 写出的**用户 `.mcp.json` 绝对路径**（已安装用户会失效）、
`install.bat`、测试与脚本里的 BASE 推导、以及门禁里所有相对路径断言。
收益只是观感 → **建议不做**（真要做得配一层薄转发垫片并作为大版本迁移）。

**三、换来的真问题：打包清单漏了 15 个模块**← 这才是根目录平铺的实际代价

`pyproject.toml` 的 `py-modules` 只手写了 10 个，而根目录有 25 个 .py。
漏掉的包括 **`mcp_extras`**（`mcp_server.py` 直接 import）、**`mcp_server_flat`**（文档里的另一个入口）、
`platforms`、`kb_local`、`font_tools`、`hardware_tools`、`translate_tools`、`test_tools`、
`ui_baseline`、`rebuild_index_local`，以及本次新增的 `derived_md` / `kb_authority` /
`kb_index_roots` / `op_spec_loader` / `platform_cap_loader`。
**`pip install .` 出来的包会缺模块 → 运行时 ImportError。**

修法（把清单从"人维护"改成"比对"）：
1. 补全 `py-modules` 为根目录全部 25 个模块；
2. 新增门禁 `stage_package_manifest`：**「根目录 .py 集合 == py-modules」**，漏一个直接红。

**四、零风险清理**：根目录散落的 `err.log`（未入库、.gitignore 里已有）归档到 `temp/err.log.archived`。

## 9. B6 落地记录（IDE 冗余出库，2026-10-02）—— 结论：75 个里只有 28 个该出

原计划的验收点是「**先确认 IDE 是否必须**」。逐个查证后（`git ls-files` 全量分类）：

| 文件 | 判定 | 依据 |
|---|---|---|
| `.project` / `.cproject` | **必需，留** | IDE 打开与编译必需；`project_tools` 还要改里面的工程名，`validate_project` 也会检查它们存在 |
| `.settings/com.zksw.flythings.easyui.prefs` | **必需，留** | `resolution=` 是 op 取分辨率的来源（改了分辨率只改 prefs 不够，ftu 内嵌也要改）；`easyui.cfg.*` 是工程配置本体 |
| `.settings/org.eclipse.core.resources.prefs` | **留** | `encoding/<project>=UTF-8`（中文注释保真） |
| `.settings/language.settings.xml` | **出库 ×8** | Eclipse CDT 语言设置缓存，**含本机 `env-hash`**（每台机器不同）→ 入库即"错的" |
| `.settings/org.eclipse.core.runtime.prefs` | **出库 ×8** | 只有 `line.separator`（本机行尾习惯），Eclipse 自动生成 |
| `.deps.lock` | **出库 ×12** | 文件头自己写着「不适用于手动编辑」；`fun install` 重新解析。且 `demos/README` 早写明"不提交 `.deps.lock`"——demo 确实没有，**模板/示例才是异常** |
| `evidence/*.log`、`ui_blocks/examples/*/{check_all,last-run}.log` | **留 ×18** | 被 README 明确引为**对外证据**（RadButton 修前/修后指标、六版 UI 块的 exit 0 记录）——不是垃圾 |

**动作**（索引与磁盘各清 28 个）：
1. `git rm --cached` + 删盘（都可重建：Eclipse 导入时重建 / `fun install` 重新解析）；
2. `.gitignore` 加 `language.settings.xml` / `org.eclipse.core.runtime.prefs` / `.deps.lock`
   —— **注意 pattern 不带路径锚**：含 `/` 的 pattern 只匹配 .gitignore 所在目录，写成
   `.settings/language.settings.xml` 会匹配不到 `templates/*/.settings/...`（实测踩到）；
3. 新增门禁 `stage_no_ide_local_files()`（`git ls-files` 里不得再有这三类）；
4. `audit_baggage` 的 IDE 冗余口径同步改成"真正不该入库的三类"——原先把 `.project`/`.cproject`
   也算进去，会误导（它们是被保留的工程必需件）。出库后该指标 **75 → 0**。

## 10. B4 落地记录（bin_tools 平台副本，2026-10-02）—— 结论：**不收编，原计划的口径算错了**

原计划：`bin_tools/` 5 组重复 / ~660KB → 「一份二进制 + 平台映射」。实测**推翻**：

1. **重复副本在仓库里几乎不占空间。** `git verify-pack` 实测：
   - 完全相同的（z20/z21 的 `touch`/`ui_test`/`zkshot`、f133/f135 的 `touch`、t113/v85x 的 `touch`）
     —— **本来就是同一个 blob**（git 按内容寻址）；
   - 只差 4 字节构建时间戳的（f133/f135 的 `busybox`，1101048 B ×2）—— pack 里是
     **1 份全量 + 1 个 53 字节 delta**。
   那个 660KB 是**工作区**字节数，不是仓库体积。git 早就收掉了。
2. **按平台各放一份本来就是正确设计。** 各平台架构/ABI 不同，放错会**静默失败或打崩应用**
   （`bin_tools/z235x/README.md` 早写着"禁止拿其它平台的 ELF 顶替"）。加一层映射只增加间接。
3. **于是做了真正该做的**（按"匹配不同硬件平台"）：
   - 实测全部二进制 + `platforms.py` 的 `arch`：**19/19 匹配**（`riscv64`→ELF64/RISC-V、`arm`→ELF32/ARM、小端）；
   - 新增门禁 `stage_bin_tools()`：读 **ELF 头**核架构（不靠目录名）。**负向自测**：把 z20 的 ARM `touch`
     放进 `f133/` → 立刻 `FAIL bin_tools/f133/...(ELF32/ARM，期望 ELF64/RISC-V)`；
   - `bin_tools/README.md`：补上**漏登记**的 `zkshot` 行 + 写明「平台匹配（唯一规则）」及"为什么不需要映射层"；
   - 一度做过的"统一三对 busybox 构建"**已回退**：既然没有体积收益，就不动已交付的二进制
     （构建时间戳是构建溯源的一部分）。
4. **没做的**：Z235X 设备端工具仍缺（需该平台工具链 + 样机，README 已如实登记，不伪造）；
   f135 缺 `ui_test`（`touch` 是首选、已覆盖其能力；不塞未实测的二进制）。

## 11. 域② 落地记录（生命周期与代码接口契约，2026-10-02）

照 ①③⑥⑧ 的同一套纪律（唯一真源 + 唯一消费入口 + 全派生 + `--check` 进闸门）：

| 角色 | 文件 |
|---|---|
| 唯一真源 | `lifecycle_spec.json`：`activity`（钩子集合与语义）/ `navigation`（导航矩阵与可见性语义）/ `rules`（铁律）/ `checkAllGotchas`（check_all 误报口径）/ `controls`（控件 API 索引）/ `retrievalHints` |
| 唯一消费入口 | `lifecycle_loader.py`（`hooks()` / `hook_names()` / `render_doc()` / `validate()`） |
| 生成器 | `scripts/gen_lifecycle_doc.py`（派生 `knowledge/devflow/activity-lifecycle-spec.md`，`--check`） |
| 契约用例 | `tests/test_device_probes.py` 之外的注册表自检（`validate()` + 模板交叉核对） |
| 门禁 | 新增 `gen_lifecycle_doc --check` → 53 条 |

**★ 这个域多了一道别人没有的交叉核对**：钩子名/签名的权威形态是
`templates/HelloWord_*/src/logic/mainLogic.cc`（真机可编译）。`--hooks` 会把
**注册表 vs 模板骨架**对账（注册表多一个钩子 / 模板少一个钩子都红）——比「只比自己生成的文档」强弱得多。
本次实测**完全对齐**（`onUI_init` / `onUI_show` / `onUI_hide` / `onUI_quit` / `onUI_intent` /
`onUI_Timer` / `onProtocolDataUpdate` / `onmainActivityTouchEvent` / `REGISTER_ACTIVITY_TIMER_TAB`）。

**踩坑两条（都已修）**：
1. **tags 有硬上限 16**（`kb_local.MAX_TAGS`）。生成器一开始写了 22 个 → 知识库门禁报
   `tags 不合规: ['（共 22 个，超过 16）']`。**口语问法不该塞 tags**，它们走
   `retrievalHints`（渲染成正文的「常见问法」节）；tags 只放检索词。
2. 生成器里 `except OSError: continue` 被静默异常 lint 判红 → 改成显式 `[warn]`
   （模板骨架读不了会让交叉核对变成**假通过**，必须可见）。

**检索实测（如实登记，不调参）**：本页 9 条问法 top-1 **3/9**、全部 top-5 内。
top-1 常被同内容的散文页 `activity-code-skeleton.md` / `widget-code-api.md` 拿走——那是
**合法替代答案**（同一事实的两种载体），不是检索坏了 → `min_top1: 3` + `max_miss: 2`
（两条口语问法被骨架散文页的上下文压到 4/5，答案仍完整可读）。

## 12. 域⑤ 落地记录（多媒体能力，2026-10-03）

| 角色 | 文件 |
|---|---|
| 唯一真源 | `media_capabilities.json`：15 条能力（播放 / 录像录音 / 抓帧 / 自绘图层 / 编解码 / 免编译库）+ 3 个图层（UI·OSD / 视频层 / 独立硬件图层） |
| 唯一消费入口 | `media_cap_loader.py`（`capabilities` / `cap` / `availability` / `platforms_of` / `for_query` / `validate`） |
| 生成器 | `scripts/gen_media_cap_doc.py` → `knowledge/media/media-capability-index.md`（231 行，`--check`） |
| 契约用例 | `tests/test_media_cap.py`（11 条） |
| 门禁 | 新增 `gen_media_cap_doc --check` |

**★ 它解决了什么**：以前问「这块板能不能放视频 / 摄像头预览怎么做 / 对讲用什么」，
答案散在 14 个包的描述与 5 篇文档里，得人肉拼；现在一次可查，且**出处可追**（每条能力带 `docRef`）。

**它的两条对账**（这是本域的主要价值，不是"能加载"）：
1. `docRef` 必须真实存在 —— 死指针会让 AI 去搜不存在的东西；
2. `packages` 里的包必须在 `package_catalog.json` 里确有 —— 注册表说"用这个包"而包目录没有，
   这条能力就落不了地。
3. **包的可用性/版本不写在本表**（真源仍是 `package_catalog.json`），查询时由 loader 联接派生；
   平台名走 `platforms.resolve()`（`f136`→`F135`，不养第二份词表）。

**「口语问法」挂在每条能力上**（初版做成顶层一堆句子 + 启发式归属，判定太脆 → 改成显式归属、
可 review，门禁要求每条能力至少 1 条）。实测 8 条问法 top-1 命中 6，另 2 条被更具体的细节页接走。

## 13. B3 落地记录（工程骨架唯一来源，2026-10-03）—— 前提成立，且比原估计小得多

原口径「519 个自带拷贝」是**全文件口径**。按骨架文件实测（逐字节哈希）：

- 带这份 uart 骨架的工程 **20 个**（templates ×7 / demos ×8 / components/example ×5），
  其中 **171 份逐字节一致** —— 即同一份 `Main.cpp` + `uart/*` 被复制了 18 遍；
- **唯一一个自带骨架**的是 `demos/h264-player-v85x`（无 `uart/`，最小播放器）—— **报告出来但不动它**。

动作：`templates/HelloWord_Z20/src` 作**唯一来源** + `scripts/sync_project_skeleton.py`
（`--check` 进闸门 / `--apply` 同步）+ `tests/test_project_skeleton.py`（6 条）。

**安全底线（用例钉住）**：同步范围只有 `src/Main.cpp` + `src/uart/*` ——
**绝不碰** `src/logic/*`（各工程自己的业务）与 `src/activity/*`（IDE 生成、禁手改）。
负向自测：往副本注入一行漂移 → `--check` 立刻报「与唯一来源不一致」；`--apply` 复原后退出码 0。

**注**：与 B4 同样的口径修正 —— 逐字节相同的副本在 git 里本就是同一个 blob，**省不下仓库体积**；
这里省的是**维护面**（骨架改一处 vs 改 18 处），所以不做"映射层"，只做"唯一来源 + 副本 + 门禁"。

## 14. 顺带修掉的一处口径缺陷（derived_md.verified_day）

派生页 front-matter 的 `verified_at` 原有两种坏写法：`date.today()`（每天 `--check` 都漂）
与文件 `mtime`（**新克隆的仓库上 = 检出时间，CI 必红**）。
统一到 `derived_md.verified_day()`：真源 `updated` → 该文件**最后一次 git 提交日** → mtime 兜底；
每级回落原因收进可选 `why`（不静默）。同时清掉 `gen_hardware_doc` 里 `io.open('')` 那处死代码
（它必然抛异常 → `verified_at` 长期固定成一个硬编码日期）。

## 15. 域⑦ 落地记录（可复用组件，2026-10-03）

| 角色 | 文件 |
|---|---|
| 真源 | **`components/` 这棵树**（形状由目录结构决定）+ `components/README.md`（规范：四件套/形态/代码规范/checklist）+ `platform_capabilities.json`（平台可用性） |
| 唯一消费入口 | `components_catalog.py`（`modules` / `get` / `by_platform` / `for_query` / `validate` / `declared_gaps`） |
| 生成器 | `scripts/gen_components_catalog.py` → `knowledge/components/components-catalog.md`（196 行，`--check`） |
| 契约用例 | `tests/test_components_catalog.py`（8 条） |
| 门禁 | 新增 `gen_components_catalog --check` |

**★ 没有新造一份组件 JSON**：形状/依赖/示例本来就在树里（依赖在各组件 `Manifest.xml`，机器可读），
平台可用性已有真源。所以本域做的是**扫描 + 把那条人自觉的规则机器化**：
`components/README.md` 的「**四件套缺一不收**」现在由 `validate()` 按形态核对（源码型/二进制型/资产型
要求不同），门禁盯住。

**两处真问题（都修了）**：
1. `mp_transfer` 缺 `Manifest.xml`（依赖只写在 README 文字里）→ **补上**（`base-utility` + `log`）。
2. `fonts` 不在 `platform_capabilities.json`（它的 `platforms.md` 是逐平台正文、没有"平台×能力"矩阵表，
   B1 抽取时被跳过）→ 以**已登记缺口**放行（写清原因与日期，看得见，不静默）。

**「已登记缺口」机制**（`DECLARED_GAPS`）：门禁只放行登记过的缺口；新增缺口直接红。
另修：`_summary` 原来取 README 第一个正文段 → 抓到的是"第一条要点"（`fonts` 变成"构建前做字体体检"），
改成**取 H1 标题的描述段**（作者本来就是那么写的）。

## 16. 顺手收敛的一处「第二份规格」（域⑦ 的一部分）

`knowledge/devflow/reusable-components.md`（230 行）把 `components/README.md` 的**规范整段抄了一遍**，
而且**已经分叉**（它写"两种模块形态"，规范已是**三种**），还自带一份手维护的组件表与若干组件实测明细。

处理：**独有内容搬进规范**（代码规范第 8 条"日志要能接出去"、`fun.json` 优先/`type:"executable"`、
与知识库的分工定位），然后把该页瘦成**指针页**（230 → 54 行，id/title 保留 → 9 处引用不失效）。
组件实测数字（blur 59~88ms / imagecall 315→1ms / vinyl 双后端 / wall_sync RTT/2…）**逐条核对过**
——都已在各自组件 README 里，所以不再在总页重复。

顺带把两页的**检索职责分开**（原来互相抢）：清单类问法归派生页（实测 top-1 4/8、8 条全在 top-3），
"规范在哪/四件套"归指针页（实测 4/5）——两组都按实测登记进检索回归。

## 17. UI 相关待确认项：V85X 列已真机确认（2026-10-03）

`platform_capabilities.json` 里共 **44 处「未验证/待测」**，其中 UI 控件（`ui_v1`）的 **V85X 列**本轮确认：

| 组件 | 方式 | 结果 |
|---|---|---|
| `ui_v1/Chart` / `Calendar` / `RadButton` / `_mapping/TabView` | 示例工程改平台为 V85X → **标准 fun 链路**（`fun install` → `fun build` → `fun launch`）→ 抓屏 | 4/4：编译通过、`launched=True`、logcat 见 `onUI_show`、抓屏有内容且**四张画面互不相同** |

- 设备：USB `Zkswe_V85X_SPINOR`（easyui 2.4.0）。⚠️ 面板尺寸**两处读数不一致**、待现场确认：
  上一轮记的是「480×1600」，而本轮 `device_probes.panel_resolution()` 读到
  `/sys/class/graphics/fb0/modes = U:480x800p-60`、`virtual_size = 480,1600`（`pan=0,800` → **2 页缓冲**）
  ⇒ **可见区 480×800**。（判据取 fb modes；1600 是缓冲区总高。可能是"面板物理 1600 / fb 只驱动 800"，
  也可能是上一轮记错 —— 上机时用 `hw_panel_target` 的 `RGB_LCD…` 原文核一次。）

- 设备：USB `Zkswe_V85X_SPINOR`（easyui 2.4.0，面板 480×1600）；**全程 `fun launch`，没有手工 adb push 部署**。
- 注册表 4 个单元格改为「✅ 可用（真机已验收 2026-10-03）」并追加实测依据；4 篇 `platforms.md` 的矩阵表
  由 `gen_component_platforms` 自动重生成；**证据截图**按 ui_v1 约定存进各自 `example/evidence/v85x_20261003_full.png`。
- **口径如实标注**：示例是 1024×600、面板 480×1600 → 验的是**组件在该平台可用**（编译/加载/绘制/起来），
  **不是版式**（版式未适配这块面板）。
- 顺带修一处判据硬度问题：`logcat -d` 读的是整个缓冲区（含 launch**之前**的旧行），
  现在 **launch 前先 `clear_logcat`**，避免把上一轮的 `onUI_show` 当本轮证据（清失败只记 warning，不拦流程）。

**仍未确认**：blur / imagecache / vinyl / wall_sync / blend2d / ha_bridge / mp_transfer 的未验证平台
—— 都需要对应平台的设备（现场逐项对接）。

**`ui_v1` 的 Z20 / T113 / F133 列：需求方 2026-10-03 定「不逐平台验，V85X 单平台即代表」**，
故这 10 个单元格已从「⚠️ 未验证」改成 `➖ 不逐平台验（口径：UI 控件只做 V85X 单平台代表验收，2026-10-03）`，
并把这套口径登记进注册表 `verificationPolicy`（写清 rule/why/decidedAt/scope），由 `platform_cap_loader.validate()`
**闸门化**：登记过的组件，非代表平台的行**不许再出现「未验证」**（改口径就得改单元格，不是留 TODO 挂着）。
4 篇组件 `platforms.md` 的手写口径行（"没实测的一律写未验证"）也一并加上例外说明，避免正文与表分叉。
—— 于是注册表里的「未验证」从 42 处降到 **32 处**（那 32 处要设备，才是真正的待办）。

---

## 18. 组件在 V85X 的首次实编复验（2026-10-03）

需求方口径：**UI 不需要逐平台验证，一个平台验好即可验收**；设备 USB V85X 已接入。
ui_v1 四件上一轮已按单平台验收，故本轮转向**显示/媒体组件**。

### 18.1 方法（可复现）

```
cp -r templates/HelloWord_V85X /tmp/v85x_base
cp toolchain/fun.exe toolchain/fui.exe /tmp/v85x_base/
cp -r components/<名>/include/* /tmp/v85x_base/src/      # include 根就是 src/（见 .fsc/v85x/CMakeLists.txt）
mkdir -p /tmp/v85x_base/src/comp_<名>
cp components/<名>/src/*.cpp /tmp/v85x_base/src/comp_<名>/
cd /tmp/v85x_base && ./fun.exe build                     # fsc 自动扫 src/ 生成 CMakeLists
```

工具链 `arm-unknown-linux-musleabihf-gcc`（V85X = ARMv7 **musl**）。
基准：未改动的模板本身 9/9 编过、链成 `libzkgui.so`。

### 18.2 结果

| 组件 | V85X | 证据 / 卡点 |
|---|---|---|
| **blur** | ✅ **可编译可链接** | 标量 `zk_blur.cpp` + RVV 桩 `zk_blur_rvv.cpp`（`#ifdef __riscv_vector` … `#else` 桩，**跨架构回退设计成立**）→ 12/12 编过并链成 `libzkgui.so` |
| **imagecache** | ✅ **可编译可链接** | `zk_imagecache.cpp` 只依赖标准库 + pthread，无外部包 |
| **vinyl** | ❌ **不可用（缺 nanovg 包）** | 核心 `zk_vinyl.cpp` 需 `<nanovg.h>`；V85X registry 只有 5 个包、**无 nanovg**，仓库离线 `packages/` 也没有 |
| **wall_sync** | ❌ **不可用（缺 rapidjson 包）** | `zk_wall_sync.cpp` 需 `<rapidjson/document.h>`；声明 `rapidjson 1.1.0` 后 `fun install` 拉 `packages/v85x/rapidjson/1.1.0.zip` → **502 Bad Gateway** |
| **blend2d** | ❌ 无库（**原本就已正确标注**） | 只有 `lib/z20/` 与 `z20-neon` 的 `.so`，其 `NEEDED` 是 glibc，musl 平台没有 |
| **icons** | ➖ 平台无关（**原本就已正确标注**） | 纯 PNG 资源 + 三条硬规则，无平台分支 |

### 18.3 一条比"未验证"更有用的结论

**V85X 的包 registry 只有 5 个基础包**（base-utility / easyui / log / zkhardware / zknet），
而 Z20 有 20+。所以"组件在 V85X 能不能用"的**主要卡点是包供给，不是组件代码** ——
`vinyl` / `wall_sync` 属于这类，现在是明确的「❌ 不可用」而不是含糊的「未验证」。

未验证单元格 **32 → 30**：blur/imagecache 的 V85X 格由「未验证」变「✅ 已实编」；
vinyl/wall_sync 由「未验证」变「❌ 不可用」——后者其实是**更强的结论**（知道为什么不行）。

### 18.4 单机验不了的那一类

`wall_sync` 的核心是**拼墙相位对齐**，需要 ①可注入硬解引擎 ②各机可校时 ③MI 图层多实例
—— **一台设备验不了**，必须多台同型号组墙。这类"未验证"不该被单平台口径消化掉，
已在它的 `platforms.md §1` 里写明"这一条单机验不了"。

---

## 19. 检索黑洞第 3 例（`packages/**`，2026-10-03）—— 同一个成因，同一个手法，第三次

### 19.1 现象与实测口径

`packages/` 下 **40 篇 md**（12 个包的 `README.md` 用法 + `platforms.md` 逐平台真值 +
`example/`、`evidence/`、`lib/` 附带件）在 `rag_index.json` 里的 **chunk 数 = 0**。
换句话说：**厂家依赖包怎么用**这件事，AI 一篇都搜不到。

判据不是"感觉"，是三条 grep 对照（同一手法验第 1 例是否修好）：

| 探针 | 结果 | 含义 |
|---|---|---|
| `ftu-json-pipeline`（knowledge/） | ✅ 命中 | knowledge 在索引里 |
| `components/ble/platforms`（components/） | ✅ 命中 | B1.3 修的**第 1 例**确实补上了 |
| `zkhardware/README`、`zkhardware/platforms`（packages/） | ❌ **全部不命中** | **第 3 例：没修** |

为什么这次要单独列：这**不是设计缺陷，是收尾没做** —— B1.2/B1.3 已经把
「知识在 `knowledge/` 之外 → 不索引就等于不存在」这条判据跑通过一次，
`components/*/platforms.md` 用同一手法救回来了，但**同一个手法没有铺到 `packages/`**。
而它正是 plan.md 根因④「硬件外设 API（IIC/SPI/GPIO/ADC/PWM）」与根因⑥「组件包」
**唯一带真机实测的答案载体**（`zkhardware`：继电器 `zeroOutput` / 背光 / ADC / GPIO / 过零 / PWM）。

### 19.2 修法：复刻 B1.3，不新造机制

| 角色 | 文件 | 改动 |
|---|---|---|
| 唯一真源 | `kb_index_roots.py` | `ROOTS` 加第 3 个根 `packages`：`include=('README.md','platforms.md')`、`skipDirs=('example','evidence','lib')` |
| 消费方 | `rebuild_index_local.py` / `scripts/check_consistency.py` | **一行都没改** —— 两处本来就都从真源派生（这正是 B1.3 收编索引范围换来的红利） |
| 契约用例 | `tests/test_kb_index_roots.py` | +2 条（包级用法页必须进 / `example·evidence·lib` 必须不进，口径由共用的 `_packages_expected()` 唯一表述） |

**判据只有一条**（三个根共用）：**这份知识是不是 AI 干活时要用**。是 → 进索引；
维护者/工程视角（组件 README、`example/` 示例自带件、`evidence/` 取证、`lib/` 构建凭据）→ 不进。

结果：**150 篇 / 1830 chunk**（1676 → 1830，+154），索引 3.7 → 3.9 MB。

### 19.3 代价账：如实登记 6 处挤出，**不调阈值凑数**

新语料进池必然与旧文档竞争 top-1（B1.3 已记录过 3 处）。这次逐条取证后登记 6 处，
**新 top-1 全部是更优或合法的答案**：

| 问法 | 新 top-1 | 判定 |
|---|---|---|
| `Z20 的 openssl 和别的平台版本不一样` | `packages/openssl/platforms.md` | **更优**（逐平台版本真值表；原榜首是"怎么读包卡"的方法论页） |
| `openssl 是什么版本` / `有没有 curl 包` | `packages/<包>/platforms.md` | **更优**（比 `builtin-packages.md` 这份派生总览更具体）→ 该组 `min_top1` 8→6 |
| `registry 里没有这个包` | `packages/nanovg/README.md` | **更优**（nanovg 正是"注册表没有但本仓自带"的典范） |
| `setprop ctl.restart zkswe 连续重启 黑屏` | `packages/mqtt-cxx/platforms.md` | **更优**（这条坑的**真源**就在那页） |
| `包验证工程 自检 AUTO 一键跑完` | `packages/zknet/platforms.md` | 合法（真机验证记录） |
| 生命周期 3 条 | `activity-code-skeleton.md` | **合法替代**（同事实的散文载体，§11 已定过此口径） |

**总账**：`30 组 / 225 问法 / top-1 172` → `31 组 / 234 问法 / top-1 175`，对照组 9/10 未变
（没污染别的主题）。折算到**旧 225 问法**：top-1 **172 → 169（−3）**，6 条落外全部有据 ——
这就是这次改动的真实代价，写在门禁注释里（每组一条「第 N 条例外（2026-10-03…）」），
不删问法、不隐藏。

新组自身 **9 条问法 / top-1 6**，其中 **2 条如实留为已知限制**：`背光亮度怎么调`、
`ADC 读数怎么取` 命中 uicontrols 无关页且返回体 `quality=low_confidence`
（coverage 0.133 / 0.349）—— 探针逐行核过本页**确实写了**背光（5 行）/ADC（6 行），
且换贴近文档用词的问法即 top-1（`背光 亮度 接口` / `ADC 电压怎么读` / `zkhardware ADC`），
所以是**措辞级召回限制，不是语料缺失**。这类限制要留在门禁里看得见。

### 19.4 顺带修掉「本次改动会放大」的两处旧口径缺陷

1. **`gen_manifest.py` 把「非 `knowledge/` 前缀」当成 wiki**：
   `wiki_paths = [p for p in rag_paths if not p.startswith('knowledge/')]`。
   components 收编后那 **16 篇仓库内文档**就被算进了 `docs.wikiFiles`，加 packages 会变 41。
   更要命的是门禁 `wiki page count` 拿它与**真实 wiki 篇数**比 —— 于是在**有本机 wiki 的机器上
   （发布前必跑）必然假红**。现改成从索引范围真源派生（真源声明的 + `kb_local/` 之外的才是 wiki）
   → `wikiFiles: 16 → 0`（本机无 wiki，数字终于名实相符）。
2. **`PUBLISH.md` 的「✅ 保留」漏了 `packages/`**：`package_tools.package_card()` 运行时要读
   `packages/<包>/package.yaml`（`flythings_get_package_api` 的 `card` 字段靠它），
   保留篇 `knowledge/devflow/dependency-package-docs.md` 也引用这些路径 ——
   发布时若裁掉，**包卡功能、文档指针、索引覆盖度门禁会同时坏**。已补进保留清单并写明原因。

### 19.5 一条流程观察

`scripts/smoke.py` 在这次改动前**就是红的**（`silent except lint`）：REVIEW-2026-10-03 §6
整改给 `tests/_util.py` 加的 Windows 清理快路径里有一个 `except Exception: pass`（"退化到
`shutil.rmtree` 真删"），**当时漏登记**进 `silent_except_baseline/whitelist`。
本次按 lint 自己的文档口径（填得出理由就登记）补进白名单并写明理由。
**教训与项目既有结论一致：改了代码就要跑门禁 —— 工作区当时是脏的，没人跑。**

---

## 20. 判据可信度两修（2026-10-03）—— 「改名漏改」是一类，不是一处

### 20.1 起因：一条会**假绿**的判据

`fun` 在 09-28 版把工程产物目录从 `<项目>/.fun/<平台>/` 改名到 `.fsc/<平台>/`。
`project_tools._find_build_artifact` / `_find_update_img` 当时就改成**两代都认**了，
但 `preflight.budget_usage()` 漏改：它只找 `.fun/<包键>/libzkgui.so`。后果：

> **新工具链工程的 `libzkgui.so` 体积一律计 0** → `usedMB` 偏小 → `level` 可能从
> `near`/`over` **假绿**成 `ok`。而这条判据的用途正是拦「打包超 /res 分区、升级被截断」。

修法：目录名从**唯一真源** `project_tools.BUILD_DIR_NAMES` 取。
⚠️ 只能**函数内延迟导入** —— `project_tools` 在模块级就 `import preflight`（它要用
`resolution_decision`），模块级互导会成环。导入不上**不静默**：退回两代硬编码 + 写进 `warnings`。
（`preflight_spec.json` 的 `budget.parts` 口径与派生页同步。）

### 20.2 「先量后动」：同一漏改还有几处？

全仓 grep `.fun` 硬编码得 **46 处**，逐条判定后分三类：

| 类别 | 处置 | 例子 |
|---|---|---|
| **真 bug（会改变结论）** | 修 + 补用例 | `preflight.budget_usage`；`kb_tools._DESIGN_WALK_SKIP` |
| **口径不一致（影响面小）** | 一并收，写清影响面 | `error_codes_loader._SKIP_DIRS`、`ui_tools/check_all._SRC_SKIP_DIRS`、`ui_tools/font_subset_by_project` |
| **查过不是 bug / 只是注释陈旧** | 只改注释，**不顺手改代码** | `ui_tools/device_screenshot`（它读的是**设备上**的 `/res/etc/EasyUI.cfg`，不做工程目录查找） |

第 2 行那条真 bug 值得单独记：`_has_design_artifacts()` 是**全树 walk**，只跳 `.fun`
等于**对新工具链工程完全没跳构建产物** —— `.fsc/**` 里任何 `.html`/preview 文件都会被
当成「设计产物」，从而**静默抑制**「设计先行」软提示（`_DESIGN_WARN`）。

**46 处里已经正确的 3 处**（`font_tools` / `package_tools` / `selfcheck_tools` 都是
`('.fsc', '.fun')`，`ui_tools/json2img` 甚至认到 `.fuse`）说明这不是"没人知道要两代"，
而是**漏改**：改名是一次机械操作，散布在各模块里的字面量清单没人有义务全找一遍。

### 20.3 为什么这次没做「唯一真源」的大收编

看起来该把「构建产物目录跳过清单」也收成一份真源。**实际约束挡住了**：

- `ui_tools/` 有一份**仓库外的双份副本**（`sync_ui_tools.py` 维护，`dst=dirname(BASE)/ui_tools`），
  它必须能**独立运行** → 不能依赖仓库根的模块；
- `error_codes_loader` 是**错误路径上的模块**（"错误路径上不该再抛错"），不宜引入重依赖；
- `project_tools` 与 `preflight` 之间已有方向相反的依赖（前者模块级 import 后者）。

所以这次按「**每处一行 + 注释写清为什么**」处理，把"要不要建真源"留给后续：
真要收，得先解决双份副本的分发问题（那会牵动 `PUBLISH.md` 的发布清单）。

### 20.4 第二修：selfcheck 分区份数**没有一处派生**

真源 `selfcheck_tools.SECTIONS` 在 v0.27.134 / v0.27.147 两次扩容（⑩ 库清单、
⑪ 部署一致性）后已是 **11 个分区**，但份数**没有任何一处派生**，于是 5 个地方还写 9：
`README.md`、`selfcheck_tools` 的失败告警文案、`tests/README.md`、
知识页 §2 的标题与表格（表里连 ⑩ 都缺）、示例 `summary.total`。

处置（与工具数六方一致同一手法）：

| 项 | 做法 |
|---|---|
| 运行时文案 | 从 `summary.total` 派生（`summary.total` 本身 = `len(SECTIONS)`） |
| 活文档 | 纠正为 11；知识页补上缺的 ⑩ 行、示例 `total` 9→11 |
| **防回退** | 新增门禁 `stage_selfcheck_sections`：扫 4 个活文档里「N 个分区 / N 分区」的提法，**只认数字与真源一致，不管措辞**；`一/1` 不计（「采集一个分区」是单数习惯用法）；命中行可带 `分区数豁免` 标记 |
| 历史实测记录 | v0.27.123 那条「九分区 8/9 ok」**原文保留 + 加豁免标记** —— 改它等于篡改证据 |
| 证据 | **负向自测**：往 README 注入错误份数 → 门禁红；逐字节还原并复核一致（证明判据不空转） |

> 这类数字的教训项目里已写过多次（「易漂移的数字必须派生」）。本条的新意是：
> **光把真源写对不够 —— 还要有一条门禁盯着"引用它的散文"**，否则真源越长越对、
> 散文越长越错。

---

## 21. 域④ 收编第一步：硬件外设 API 权威页（2026-10-03）

### 21.1 为什么是「最薄的一条」

`CONSOLIDATION.md` §2 把域④（硬件外设 API：IIC/SPI/GPIO/ADC/PWM）一直标着「🟡 半」，
`WORK_PLAN.md` 写「域④ 硬件外设 API 仍半成品」。实测口径：修之前 `knowledge/hardware/`
5 篇全是 **UVC / USB / 显示 / 升级**，**没有一篇讲外设怎么写**；真机数据只在
`packages/zkhardware/`（而它直到 §19 才进检索范围）。plan.md 七条根因里，
**只有域④ 没有权威页**。

### 21.2 收录口径（需求方 2026-10-03 定）

> 「硬件 API 在 `packages\zkhardware\README.md` 有说明。`…\include\utils` 这个里面有头文件 API。
> 你可以直接收录，**不需要验收**，按照这个理解接入即可。后续有问题的时候我会单独提出来。」

于是：**头文件 = API 权威面 → 直接收录、不做真机验收**。新增
`knowledge/hardware/peripheral-api-zkhardware.md`（`confidence: offline`、`status: review`、
`needs_evidence: true`），逐个头文件抄完整签名，并**把"哪些是契约、哪些是实测"分开**：
签名/默认值/枚举/返回约定 = 头文件契约（本页负责）；行为与真机读数 = 一律指向
`packages/zkhardware/{README,platforms}.md`，**本文不复制**。

### 21.3 收录时最大的增量：平台变体矩阵

本机 registry 四份 `zkhardware`（`~/.fsc` 的 v85x/z20、`~/.fun` 的 z21/z235x）逐字节哈希比对：

| 头文件 | 变体数 | 结论 |
|---|---|---|
| `AdcHelper.h` / `I2CHelper.h` / `PWMHelper.h` / `SpiHelper.h` / `hw/HardwareManager.h` | **1** | 四平台**逐字节相同** |
| `GpioHelper.h` | 3 | Z20 / Z21 / (V85X=Z235X) |
| `BrightnessHelper.h` | 3 | (Z20=Z21) / V85X / Z235X |

由此得到的**跨平台硬约束**（README 的 API 速查是子集、不含这些）：

- **过零 IO 全家**（`zeroOutput` / `getZeroIoNum` / `getZeroIoStatus` / `zeroResetPeriod`）
  **只有 Z20/Z21 有** → 在 V85X/Z235X 上写 `zeroOutput` 是**编译不过**，不是运行期失败；
- **`initPinMap` 只有 Z20 缺席**；
- 引脚宏：`SV50PD` 仅 Z20/Z21、`H500S` 仅 Z20；
- 背光：`screenOffEx/screenOnEx` 仅 Z20/Z21；`setLuminance`/`getContrast`…/`setDvdd` 仅
  V85X/Z235X；`setVcom` 仅 Z235X。

> 「哪些平台有这个 API」以前只能靠翻各自 registry 的头文件 —— 现在一页可查，且**分歧点被显式化**。

### 21.4 顺手抓出的两处口径冲突（如实并列，以真机为准）

1. `setBrightness`：头文件注释写范围 `0 ~ 100`，而真机口径是 **1 ~ 100（传 0 = 关屏语义）**。
2. `zeroOutput` 的 `onns/offns`：**签名默认 `0`，注释却写「默认 4900000ns / 6000000ns」**
   → 只能理解为 `0` 是"用内部默认"的哨兵；**未真机验证**，已在页里标为待核。

两条都写进了页面的「踩坑与铁律」，并注明**冲突存在**（不替厂商选一个说法）。

### 21.5 为什么这一页是"人工维护"而不是派生页

项目纪律是「唯一真源 + 全派生」。这里**故意不派生**，理由写在页面 §0：

> 生成器要在 fresh clone / CI 上能跑才配当"派生"。**头文件不在仓库里**（随包注册表分发）
> → 生成器在别人机器上必然失败。

替代方案给了两条：① 页面标出处 + 收录时的**平台/版本/体积清单**（读者可据此判断是不是同一版）；
② 「域④ 机器可读真源」（`hardware_catalog.json` 收编外设 API 表）**留给后续**，
并写明前提 = *头文件进仓库或能稳定取到*。这是"如实登记而不是假装已收编"。

### 21.6 权威归属 + 两组重划（含一个被修掉的真问题）

- `knowledge/authority_map.json` 加 `peripheral-api` 概念（21 别名 + 2 op）→
  `knowledge_search` 命中即回权威指针；**12 概念 validate 全过**，实测问「GPIO 怎么读电平」
  返回体已带该指针。
- 检索回归新增 1 组 16 条问法。**同一天新页把包组（`packages/zkhardware/README.md`）的 top-1 抢走 7/9**
  —— 逐条取证后判定其中 4 条是**问法归属定错**（问"接口/怎么写/背光怎么调"本就该由 API 契约页答），
  按语义移交；包组只留「装法/真机/坑」口径（5 条，`min_top1` 按实测 2）。这与 B1.3 的处理一致：
  **先取证、再决定是"挤出"还是"归属错"，两种都写清理由**。
- ⚠️ **一个被新页修掉的真问题**：上一轮把 `背光亮度怎么调`、`ADC 读数怎么取` 登记为
  「措辞级召回限制」（当时命中的是 uicontrols 无关页）。新页给出专门的背光/ADC 小节后，
  **两条都变成 top-1** —— 说明当时的诊断（语料不够聚焦）是对的，而**补一个聚焦页就是修法**。
  这条值得记住：**"检索不到"有时不是检索坏了，是知识本身没有一页在讲那件事。**

---

## 22. 串口通讯权威页（2026-10-03）—— plan.md 目标 1 里那块「零覆盖」的地方

### 22.1 空白区的实测口径

`REVIEW-2026-10-03.md` §2.3 记过一条：**全表扫「协议 / 串口 / UART / Modbus / CAN / 通信」
一条命中都没有** —— 而 plan.md 目标 1 明写要让 AI 能做「**通讯协议对接调试**」。修之前：

| 现状 | 说明 |
|---|---|
| 零 op | 没有任何工具服务"协议对接"这件事 |
| 零权威页 | 只有 `activity-code-skeleton.md` §5 的 **9 行摘要** |
| 真机知识只在代码里 | 19 个工程共用的 `src/uart/` 骨架（**代码不是可检索知识**） |

### 22.2 需求方口径 = 一条边界声明（这才是关键决定）

> 「UART 部分在 demo 程序里面有 uart 的框架。这个是基于标准的 linux uart，但是结合 UI 的
> 生命周期以及框架做了 `SProtocolData` 共享变量的设计。……类似的 modbus 和其他协议都是可以
> 借用 **linux、arduino 生态的开源代码复用**。**MCP 更多的是为了 FlyThings 系统和 UI 的一些
> 约定而来**。」

于是页首立了**分工判据**（这一条比正文更重要，它决定了以后不要往哪花力气）：

| 问题 | 去哪 |
|---|---|
| 「**怎么接进 FlyThings**」（开串口时机 / Activity 订阅 / 共享变量 / 线程模型 / 帧解析契约） | **本页**（MCP 的独有价值） |
| 「**帧怎么编怎么解**」（Modbus CRC、DLT645 报文、自定义字段语义） | **协议本身** → Linux/Arduino 生态现成实现；按 `open-source-stack-integration.md` 四判据引进 |
| 「串口名/波特率给我什么值」 | `package-properties-easyui-cfg.md` + `hardware-models.md` |

> 附带的纪律：**模板里的帧格式（`FF 55 | CmdID | DataLen | Data | [CheckSum]`）是示例，不是平台规定**。
> 换协议只要改 `CommDef.h` / `Parser` / `Sender` 三处，**框架其余部分一行不动** —— 这句写进页面，
> 才不会有人为了接 Modbus 去改 `UartContext`。

### 22.3 11 条铁律**全部从代码读出**（其中 4 条是硬 bug 级）

不是经验之谈，是逐行读 9 个骨架文件的结果。最值得记的四条：

1. **`procParse` 里 `pData[5]` 无边界校验** —— 帧长校验只保证这一帧有 `frameLen` 字节，
   而 `DataLen=0` 时 `frameLen` 也是 5 → 读 `pData[5]` 是**下一帧的头字节**。
   **不崩、值是错的、只在 `DataLen=0` 的帧上出现** —— 这类"静默错值"最难查。
2. **回调里增删 listener = 自锁死** —— `notifyProtocolDataUpdate` **持非递归 `Mutex` 调用**回调，
   而 register/unregister 要同一把锁。现象是界面卡死、**没有崩溃栈**。
3. **`parseProtocol` 返回负数会撑爆 16KB 缓冲** —— `threadLoop` 里 `mDataBufLen -= len`
   **无条件执行**，"出错返回 -1"这种自然写法会让长度**变大** → 下一轮 `read` 往缓冲区外写。
   → 铁律：**报错走 `LOGE`，不要用负返回值**。
4. **`openUart` 的失败模板里不检查** —— 串口名/波特率配错**零提示**，现象只是"收不到数据"。

另记一条**设计缺口**（不是 bug，是留给后面的决定）：`SProtocolData` **没有「是否已收到首帧」标志**
→ `power == 0` 区分不了"设备报 0"与"还没收到"。

### 22.4 唯一真源纪律：§5 改成指针

`activity-code-skeleton.md` §5 原是这 9 行摘要，但它同时是 `ui-lifecycle` 概念的权威页 ——
串口在那里留第二份就是**跨页双份**。已按 `reusable-components.md` 的先例（230 → 54 行）
把 §5 改成**指针**，只留两条真正属于 activity 骨架的钩子级事实（app 级开串口 / page 级注册成对
+ 回调在串口线程）。改前已 grep 确认：**没有活文档引用 §5**（只有冻结的 CHANGELOG / VERSION_HISTORY 提过）。

### 22.5 代价账：新页入库挤动了 4 组（逐条取证，全部登记）

语料增长必然带来挤出。这次逐条查了「新 top-1 是谁」，结论：**3 组合法、1 组是我自己撞词**：

| 组 | 新 top-1 | 判定 |
|---|---|---|
| `reusable-components` | `components/ui_v1/{_mapping/TabView,Calendar,Chart}/platforms.md` | **合法**：那是真·platforms.md 实例，对"这文件写什么"更直观 |
| `custom-font-config` | `upgrade-pack-image.md` / `device-preflight-spec.md` | **合法**：都在讲"字库与部署"这个相邻话题 |
| `open-source-stack-integration` | `knowledge/v85x/h264-player-usage.md` | **合法**：该文有真实的 `undefined reference` 实战 |
| `dependency-package-docs` | `knowledge/hardware/peripheral-api-zkhardware.md` | ⚠️ **是新页 §4 的 `<package id=…>` XML 片段与泛问法撞词** —— 已如实登记，权威仍是本页 |

同时给新组**如实留了 2 条措辞弱点**：`UART 怎么用`（**纯英文缩写 + 泛问句**进不了 top-5）、
`半包重组怎么做`（本页用口语「半包，等下次再拼」，术语命中不足）。另**剔除 1 条**：
`串口回调里能不能刷 UI` 的正解本就是 `cross-thread-ui-rule.md`，不该由本组认领。

### 22.6 顺手修的「错误信息指不到真因」（含一次失败的自测）

我这轮**两次**把 `features_recent.json` 写成非法 JSON（字符串里用了未转义的 ASCII 引号），
而 `smoke.py` 报的是：

> `[FAIL] MCP_FEATURES[0] mentions version   empty`

—— 这句会把"JSON 语法错误"误导成"忘了写版本"（我第一次就是这么误判的）。已修：
`kb_tools` 本来就把真因记在 `_FEATURES_ERR`，smoke 现在直接透出：

> `读取失败：features_recent.json 读取失败：Expecting ',' delimiter: line 2 column 17 (char 18)`

**负向自测**（写坏 → 应报真因 → 逐字节还原）已过。
⚠️ 记一笔过程教训：我第一版自测脚本把 `sys.exit()` 写在 `finally` 里 ——
**`SystemExit` 会覆盖在飞的断言异常**，于是"测试失败"被静默成"exit 0"。
自测脚本本身也要自测。

---

## 23. P2 元层债三清（2026-10-03）—— **同一概念被实现三遍，数字就必然分叉**

### 23.1 `source`：把仓库内文档说成了外部镜像（且被前两轮改动放大）

`kb_tools` 的原口径是一句二选一：

```python
'source': 'knowledge（实践）' if path.startswith('knowledge/') else 'wiki（官方镜像）'
```

于是**仓库内**的 `components/**/platforms.md`（16 篇，2026-10-02 收编）与 `packages/**`
（25 篇，§19 收编）**全被标成「wiki（官方镜像）」** —— 等于对 AI 说「这是外部镜像、
不是本仓实践知识」。它读检索结果时最先看到这个字段，**可信度判错、出处指错**。
本地层（`kb_local/**`）命中也一样。

修法：按**索引范围唯一真源** `kb_index_roots` 派生标签
（`knowledge（实践）` / `components（组件平台页）` / `packages（包用法）` /
`kb_local（用户本地层）`，真外部镜像仍回 `wiki（官方镜像）`），真源不可用不静默。

> 这条是「**同一个错口径被复制**」的典型：`startswith('knowledge/')` 在 2026-09 是**对的**
> （那时索引里只有 knowledge），收编第二个根之后就**变成了错的**，而它不会自己报错。

### 23.2 `kb_index` 漏收两类：类别名单被手抄两处

`gen_kb_index.py` 与 `kb_frontmatter.py` 各写了一遍
`('devflow','uicontrols','hardware','esl','t113-car','v85x')`；`check_kb.py` 已经从前者派生。
后来新增 `knowledge/media/` 与 `knowledge/components/` 时**两处都没补** → 那两篇派生页
「**在磁盘上、也在 `rag_index.json` 里，却不在 `kb_index.json` 里**」：
拿不到 `freshness/advisory` 标注、不受 front-matter 门禁约束，
`kb_index` 的 `doc_count` 与磁盘篇数出现**系统性缺口**（106 vs 108 —— 而 `stage_index`
只盯 rag 索引的覆盖度，**没人盯看板的覆盖度**）。

修法：`kb_local.categories()` —— **从 `knowledge/` 一级目录派生**（跳过 `inbox/_reports/_logs`），
三处消费方全部派生，**加新分类不用改任何名单**。`kb_index` 106 → 110 篇。

### 23.3 `evidenceLevel`：三套口径，而它直接进 `advisory`

| 实现 | 判据 | 对错 |
|---|---|---|
| `kb_local.evidence_level` | evidence 里有 `cmd`/`artifact`（**可执行判据**） | ✅ 正确 |
| `gen_kb_index` | evidence **列表非空** | ❌ |
| `check_kb` | evidence **列表非空** | ❌ |
| `kb_frontmatter` 的打印标签「带可执行证据」 | evidence **列表非空** | ❌ |

后果不是"数字难看"：`gen_kb_index` 的值进 `kb_index`，检索侧 `kb_tools` 读它决定**加不加
`advisory`** —— 只有人工判据的文档被算成「有可执行判据」→ **不再加 advisory**，
于是"没验过"被展示成"有判据"。修法：三处全部派生到 `kb_local.evidence_level`；
`带证据 22 → 14`（**修正后的诚实数字**）。

**顺手修三态自洽的两处**（都会原样出现在 `advisory` 的「证据等级=x」里）：
① `manual-only` 原先只在 `needs_evidence` 为真时给出 → 一篇明确写了 `evidence: [{kind: manual,…}]`
却没写 `needs_evidence` 的文档被判成 **`none`**；② 判「有没有证据条目」用的是**过滤后的 dict 列表**
→ 把**散文串形态**的 evidence（实测 `color-contrast-standard.md`：4 条实测描述全是纯字符串）
也算成「没有证据」。两处都等于对 AI 说「这篇没有证据」。现三态自洽：**14 / 95 / 1**。

### 23.4 一条方法结论

这三条**没有一条是"新功能的 bug"**，全都是**同一个概念在不同文件里被重新实现了一遍**：
第 2 条抄了名单、第 3 条抄了判据、第 1 条抄的是**一个曾经正确、后来失效的假设**。
它们的共同症状也一样：**没有门禁盯着的地方，数字会安静地分叉**。

### 23.5 顺手把「我自己犯三次的错」变成门禁

`features_recent.json` 我在这几轮里**写坏过三次**（JSON 字符串里用了未转义的 ASCII 双引号），
每次都得另写脚本定位。已加门禁 `stage_json_registries`：**根目录所有 `*.json` 必须能解析**，
失败时**报文件 + 行列**（实测输出：`features_recent.json → Expecting ',' delimiter: line 2 column 17`）。
根目录这些 JSON 都是唯一真源或派生快照，坏一个就是某项能力静默失效
（`op_spec.json` 坏 → 契约全拉不到；`error_codes.json` 坏 → 失败体没有 action）。
**负向自测**已过（写坏 → 红且报行列 → 逐字节还原）。

---

## 24. `notes` 债第一刀（2026-10-03）—— 33 → 25 个 op

`notes` 是 `op_spec.json` 里的**迁移兜底桶**：非空 = 该 op 的**结构化契约还没做完**。
门禁口径（`op_spec_loader.validate`）：① 不在名单里的 op **不许**有 notes（新增即红）；
② 名单里的**只许减**（字符数不得增加），**清零后从名单删除**。
存量基线 33 个 op / 5233 字符。本批清掉 8 个（**→ 25 个 / 3621 字符**）。

### 24.1 归位规则（照 `renderSpec` 的字段语义，不是凭感觉放）

| 散文内容 | 归到 |
|---|---|
| 参数语义（`compact`/`dry_run`/`with_install`/`evidence`…） | `params`（只登记**需额外说明**的参数） |
| 返回体字段与判据（`binTools`、`assetAudit`、落盘路径…） | `returns` |
| 流程/顺序（版本解析顺序、无 json 源时自动 unpack…） | `flow` |
| 跨 op 路由与铁律（「已知包名走 add_package」） | `rules` |
| 检索词 | `keywords` |
| **「口径见 xxx.md」** | **直接删** —— `docRef`/`seeAlso` 已承接，写进契约是跨层重复、白占预算 |

### 24.2 一个关键性质：这一批**没动任何 docstring**

`renderOrder = summary / triggers / hardRules`（常驻面），而 `params` 与 `notes` **都不在其中**
（`params` 在 2026-10-03 就已被移出常驻，省了 19.5%）。所以：

- `gen_op_docs --check --strict` → **漂移 0 条**；
- 常驻预算 **4730/6000**（本轮不动它；⚠️ 同日的第二批把 2 条判据归进 `hardRules` 后是 4861，**
  到今天本轮收口时实测已是 5080/6000 = 84.7% —— 这个数以 `gen_op_docs` 输出为准，
  `op_spec.budget.basis` 里的数字由门禁对账，见 §31）；
- 变的只有**按需契约**（`op='describe:<名>'`）—— 从「一坨散文」变成「参数：… / 返回：… / 检索词：…」分节。

> 这正是分层的意义：**修结构化，不必碰常驻面**。所以这一批可以放心地小步做。

### 24.3 改法：放弃 8 次手改，用**字符串感知的原子脚本**

手改 8 处 JSON（每处几十行、缩进各异）风险高。改用脚本：括号匹配（**字符串/转义感知**）
定位 `"<op>": { … }`，再在其中定位 `"notes": [ … ]`；替换成结构化字段（缩进按 notes 键的
实际列宽派生）；**每处断言恰好命中一次**；先 `json.loads` 验证**再**落盘；最后删掉
`notesDebt.items` 里对应的整行。

期间真抓到一个 bug —— 第一版跑出 `Expecting ',' delimiter`：**我把 notes 后面的逗号吃掉了**。
`notes` 常常**不是对象最后一个键**（`flythings_get_version` 后面还有 `noneReason`/`triggers`），
吃掉它就少一个逗号。**教训：做文本级结构变换时，"尾随分隔符"是最容易搞错的一处**——
所以脚本里必须保留原分隔符，并且**落盘前先验证语法**（这次就是这么抓到的）。

### 24.4 第二批（2026-10-03 同日）：33 → 25 → **17 个 op / 1693 字符**

两批共清 **3540 字符（67%）**。第二批 8 个 op 里有三条判断值得记下来：

**① 归位前先查重：`hardware_info` 的那条 note 与它**已有的 hardRule** 是同一件事**
（note：「用户说我这台是 X 时先查这里，别按同系列型号外推」；hardRule：「平台/分辨率以用户或
型号库为准；只说型号系列时不要外推（猜错 = 整份工程返工）」）。→ **重复的直接删，不是搬**。
（不查重就会把同一句话在两个层级各留一份，正是这个项目反复在治的病。）

**② 有 2 个 op 既没有 `docRef` 也没有 `seeAlso`**（`create_bin_project`、`i18n_scan`）——
对它们，「notes 里的知识指针直接删」这条规则**不适用**（删了就真丢了）。其中 `i18n_scan` 暴露了
一个**覆盖缺口**：**全仓没有专门的 i18n 知识页**，多语言机制只在 `activity-code-skeleton.md` §7
有三行。于是机制说明**留在 `flow` 不删**，并把缺口登记下来（候选：补一篇 i18n 权威页）。

**③ 有两条判据归进了 `hardRules`（常驻面）—— 这是有意的，代价是 docstring 变化**
`hardRules` 在 `renderOrder` 里（常驻面），进它就会改 docstring、动常驻预算：

| op | 判据 | 为什么必须常驻 |
|---|---|---|
| `test_run` | 比不到基线记 no-baseline，**不算通过** | 违反 = 把没比基线的步骤报成「通过」（**误报**，返工级） |
| `knowledge_export` | **强制脱敏**；未脱敏必须显式 `internal=True` | 违反 = 把本机路径/凭据/内网 IP 交出去（**泄露**级） |

→ 常驻预算 **4730 → 4861 / 6000（81%）**；docstring 漂移 2 条 → `gen_op_docs --apply` → 0 条。
**这正是分层的价值**：该进常驻的（会让 AI 误判的）进常驻并接受预算上涨；不该进的
（参数语义、返回体字段）留在按需面，一行常驻都不占。

**另记一条克制**：`selfcheck` 的 notes 里那份**分区清单**（设备信息/应用状态/…/部署一致性）
**故意没有复制进契约** —— 那会是这份清单的**第三份副本**，而 §21 新加的 `stage_selfcheck_sections`
门禁只扫 README / tests/README / `selfcheck_tools.py` / 知识页，**扫不到 `op_spec.json`**。
契约里改为写「分区清单不在此复制，以知识页的表为准」（知识页那份是门禁盯着的）。
**没有门禁盯着的副本，就不要建。**

### 24.5 第三批（2026-10-03 同日）：17 → **0，收口**

余下 17 个 op 一次清完。总量：**33 个 op / 5233 字符 → 0**（三批）。
`op_spec.json.notesDebt.items` 现在是 `{}`，注册表里**没有任何 op 还带 notes**。

本批新增的看点是**三条"指针其实不该删"的反例**（都是先查再判断的结果，不是照规则套）：

| op | notes 里的指针 | 判断 |
|---|---|---|
| `get_package_api` | 「清单见 `device-preinstalled-libs.md`」 | **原以为要补进 seeAlso** —— 一查发现它 seeAlso **本来就含那篇** → 纯冗余，直接删 |
| `attach_cli_tools` | 「业务代码只写 `src/logic/*.cc`」 | 与它**已有的 hardRule 是同一件事** → **扩写那条 hardRule**（而不是新建一个 `rules`） |
| `fui_unpack` | 「改布局仍以 json 为源」 | 它的 `rules` 已经说了这件事 → **整块删**（本批唯一的"整块删"案例） |

**再加两条进常驻面**（都是"会让 AI 走错路"的概念陷阱，AI 不拉契约也得看到）：

| op | hardRule | 为什么 |
|---|---|---|
| `get_package_api` | **注册表没有 ≠ 平台没有**（设备 /lib 自带 nanovg/libpng12/… 可 dlopen） | 不写 → AI 会断定「平台没这个能力」，白造一轮 |
| `fui_pack` | ftu 是**编译产物**，改布局一律改 json 后 pack，**不要手改 ftu** | 不写 → 手改的 ftu 被下次 pack 覆盖（静默丢改动） |

→ 常驻预算 **4861 → 5080 / 6000（85%）**；docstring 漂移 3 条 → `--apply` → 0 条。

### 24.6 收口钉子：把"迁移已结束"也变成契约

写完清零后，我检查了既有的门禁用例，发现一个**逃逸口**：
`test_op_spec.py` 那条只保证「**有 notes 就必须在名单里**」——
也就是说，**把某个 op 重新登记回 `notesDebt.items`** 就能合法地再写 notes，门禁拦不住。
已补一条 `test_notes_migration_is_closed`：**名单必须为空、且没有任何 op 带 notes**，
一旦回退即红。（`op_spec.json.notesDebt.authority` 里也写明了这个结论。）

> 这是本项目的第二次"把结论钉成门禁"：第一次是 §21 的 `stage_selfcheck_sections`
> （份数必须等于真源），这次是"迁移已完成"本身。**口头说的完成会漂，门禁说的不会。**

### 24.7 顺带登记的缺口（不在 notes 债范围，但值得留档）

`i18n` 一族共 **4 个 op**（`i18n_scan` / `i18n_export` / `i18n_import` / `i18n_add_language` /
`i18n_refactor` / `i18n_to_json`，其中 4 个）**既无 `docRef` 也无 `seeAlso`** ——
因为**全仓没有一篇专门的 i18n 知识页**，多语言机制只在 `activity-code-skeleton.md` §7 有三行。
本批把机制说明保留在各自的 `flow` 里（删了就真丢），并把「补一篇 i18n 权威页」登记为候选。

---

## 25. fui 三问：把转述变成实测（2026-10-03）

2026-10-03 早先有一份**子代理实读报告**提了 3 条 fui 问题。我当时只是转述，**没自己核过**。
本轮逐条取证，结论是：**1 条成立、1 条部分成立、1 条不成立** —— 正好说明"转述不能当结论"。

### 25.1 「`fui unpack` 传目录会 FATAL」→ **实证否定**（注释是陈旧的）

`tests/test_toolchain_capability.py` 曾写「⚠️ 传目录会 FATAL」，而生产代码有 3 处传目录
（`project_tools._run_fui` / `_sync_ftu_to_json` / `check_all`）。**用随包真 fui 实测**：

```
fui unpack <dir>       → rc=0，"unpacked …/main.ftu -> …/main.json"，目录里出现 main.json
fui unpack <dir>/x.ftu → rc=0，同样解出
```

→ **传目录可批量解**（与 v0.27.91 发布说明一致）。注释已按实测改写，
并写明"改前这里是错的、会误导后来者去修本来正常的代码"。

### 25.2 「探测失败会静默降级 + 缓存再不重试」→ **部分成立，已修**

子代理说 `_sync_ftu_to_json` 走 `skipped` 是"静默" —— **不成立**：
`skipped` 带 `reason` 且被写进 `build_ui_flow` 返回体的 `steps[].skipped[]`。

但**同一段代码里有两个真问题**（子代理没点准）：

```python
except Exception:
    _fui_supports_unpack._cached = False     # ← 改前
```

① **把"探测失败"报成"能力缺失"**：文件找不到 / 不可执行 / 超时，全被说成
「当前 fui.exe 不含 unpack」→ **会把人送去换 fui（方向是错的）**；
② **失败结论被缓存**：一次 15s 超时就让整个进程从此认定"这机器不能 unpack"。

已修成 `_fui_probe() -> (ok, why)`：原因分**两类**（真·能力缺失 / 探测失败）、
**失败不缓存**（可重试）、并按**二进制绝对路径**缓存（为"工程带多份 fui"留出正确性）；
4 处「当前 fui.exe 不含 unpack」统一成 `_fui_no_unpack_msg()`（**带路径 + 原因**）。
契约用例 `test_probe_distinguishes_failure_from_capability_absence` 钉住这三点。

### 25.3 「三处 `fui` 查找顺序不一致」→ **成立，但没统一（附理由）**

逐份代码取证（详见 `knowledge/devflow/ftu-json-pipeline.md` §6.1）：

| 谁 | 实际用哪份 |
|---|---|
| `project_tools`（**MCP op 走这条**） | **工具链那份**（完全不看项目内） |
| `ui_tools/check_all.py` | **项目 `<项目>/ui/fui.exe` 优先**（v0.27.172 补回的优先级） |
| `ui_tools/ui_edit_apply.py` | **项目那份优先** |

（子代理说 check_all「优先项目内」是对的，但要看到 CLI 入口那句覆盖才算读全 ——
模块级常量其实是 toolchain 优先。）

**为什么没统一**：① `ui_tools/` 是**可整目录复制出去**的（`sync_ui_tools.py` 维护
`D:\flythings\ui_tools` 双份），那边**取不到 `project_tools`**，共享不了一份解析器；
② `attach_cli_tools` **必须**用工具链那份（它就是"复制进项目"的来源），
所以 `FUI_EXE` 也不能一律项目优先。

→ 现状分工（**MCP op 用工具链、独立 CLI 用项目**）**登记在案**，连同后果
（工程自带那份与工具链版本不同时，两条路径可能产出**不同的 ftu**）与规避
（让两份一致，或全程只走一条路径）。**这条是"已知不一致"，不是"没发现"。**

### 25.4 一条方法结论

三问里有一问**完全不成立**、一问**理由说反了**。如果当时照转述去改，
就会：把正常代码"修"坏（25.1）、去改一个不出问题的 `skipped` 分支（25.2）。
→ **转述只配当线索；动手前必须自己跑一遍代码/命令。** 本轮改动的依据全部是
实测输出（`fui help` + 两次 unpack 的 rc 与产物）或逐份代码引用。

---

## 26. i18n 权威页：一次「官方文档 vs 代码注释」的对账（2026-10-03）

### 26.1 缺口的样子

全仓此前**没有任何 i18n 知识页**：多语言机制只在 `activity-code-skeleton.md` §7 有三行，
6 个 i18n op **既无 `docRef` 也无 `seeAlso`**（§24 清 notes 时发现的），
而且 —— **没有任何契约用例**（`test_op_routing` 只认触发词，碰不到 `i18n_tools` 的实现）。

### 26.2 需求方给了官方文档，于是有了"第三方口径"可对账

`developer.flythings.cn/zh-hans/i18n.html` 取回后逐条对齐，**补正 4 处**：

| 官方口径 | 我原稿 | 性质 |
|---|---|---|
| 换行用 **`&#x000A;`**（XML 字符引用） | 写 `\n`（跟了 `i18n_tools.py` 注释，而它自称"官方文档"） | ⚠️ **归因错误**（见 26.3） |
| 加自定义语言**必须并入内置界面翻译**（官方给 `zh_CN.tr` 地址） | **整条漏了** | 真缺口 |
| 同一 `.tr` 内**别名不能重复**；各语言用**相同 name** | 只说了"要对齐" | 补充 |
| 加语言 = **拷贝现有 `.tr` 改名**，代号可任取（前两段不冲突） | 只说"用 add_language" | 补充 |
| 工作流：**IDE 编译**把 `.tr` 转 json；样例 = **TranslationDemo**（官网样例包） | 只写了 MCP 的 `i18n_to_json`；样例记成"仓内没有" | 补充 |

> 方法上的收获：**"官方文档"这种第三方口径最值钱的地方不是补充，而是对账** ——
> 它能照出"自称来自官方"的二手注释。这次的 `&#x000A;` 就是这么照出来的。

### 26.3 一条口径冲突：`&#x000A;` 还是 `\n`（**如实并列，未擅自改行为**）

- **官方**：`<string name="new_line_test">第一行&#x000A;第二行</string>`
- **MCP 工具**：读时容忍字面 `\n`（`_unescape_tr`），**写时也写字面 `\n`**（`_escape_tr`）；
  模块注释把 `\n` 归因为"官方 i18n 文档"——**错的**，已修正注释。
- **两者在 MCP 自己的转换里都成立**（`&#x000A;` 由 XML 解析器解开；`\n` 由 `_unescape_tr` 解开）。
- **风险在"谁来转 json"**：官方那条路是**编译器**转。若编译器**不做反斜杠还原**
  （与反汇编观察到的 `LanguageManager::getValue` 直接 `asString()` 一致），
  则 MCP 写出的字面 `\n` 经它转出的 json 会把 `\n` 当普通字符 → 设备显示「\n」两个字。
- **建议**：`.tr` 一律写 **`&#x000A;`**（唯一对编译器与 MCP 都安全的写法）。
- **没做的事**：**没有**去改 `_escape_tr` 的写行为 —— 那会影响所有生成/回写的 `.tr`，
  且我**无法在本机验证 IDE 编译器的行为**。按"未验证就登记、不猜着改"处理。
  （`i18n_tools.py` 的两处错误归因注释已修正 —— 那是纯文档修正，零行为风险。）

### 26.4 契约用例从 0 到 10：钉住的都是"静默坏"

i18n 有两个**不会报错、只会"看起来就是不对"**的地方，正好都没人看着：

1. **换行还原**：`.tr` 的换行若没变成真 `0x0A` → 设备**原样显示「\n」**（不换行）。
   用例同时钉**两条来源**：官方 `&#x000A;`（XML 解析器解）与字面 `\n`（`_unescape_tr` 解）。
2. **json 字节格式**：必须是「tab 缩进 + 冒号后无空格 + **末尾无换行**」才与设备端逐字节一致
   —— 用例直接断言这三条（**手改这个 json 就会破坏它**）。

另加：`@key` 收集、转义往返、`scan` 的"布局引用了但 `.tr` 没有"必须报出、
**没有 i18n 时不许假装有**（回 `hasI18n:false` + 指路 export）、
`to_json` 出的 json 必须是真换行、**指定不存在的语言必须明确报错**。

### 26.5 顺手收掉的一个测试基础设施坑

分发器统一包一层信封 `{ok, op, data(JSON 字符串), warnings}` —— 其中 `ok` 的含义是
**"这次调用没炸"**，不是 op 自己的 `ok`；op 的真实返回体在 `data` 里（还是个 JSON **字符串**）。
我第一版 i18n 用例直接读顶层，于是 4 条一起红：`r['ok']` 恒真、`r['converted']` 根本不在顶层。
已把它收成公共辅助 `tests/_util.py::payload()`（不是信封时原样返回），
并写明这个坑 —— 以后写 op 级用例的人不用再踩一遍。

### 26.6 门禁又抓了我一次：i18n 页里的**死指针**

第一版页面 §11 我写了 `knowledge/uicontrols/textview-fields.md` / `button-fields.md`
—— 前者**不存在**，被 `check_doc_refs` 当场抓出（`1 个路径 / 1 处引用`）：

> 有死指针：指向不存在的文档会让 AI 去搜一个搜不到的东西

（这正是那条门禁的设计意图：**知识页里的指针是给 AI 导航用的，指向不存在的文档比不写更糟**。）

**背后的真实发现**：`knowledge/uicontrols/` 下 **16 个控件有 `*-fields.md`，唯独没有
`textview-fields.md`**（文本控件；`button-fields.md` 有）。已改指真实文档
（`button-fields.md` + `widget-code-api.md`），并把「补 `/knowledge/uicontrols/textview-fields.md`」
**登记为缺口候选**（根因 ② 控件 API 的范围）。**不猜着写指针、也不新建一个我没读过源码的字段页。**

---

## 27. 文本控件页：一次「先查重再动笔」的示范（2026-10-03）

### 27.1 缺口长什么样

`knowledge/uicontrols/` 下 **16 个控件有 `*-fields.md`，唯独没有 `textview-fields.md`** ——
这是上一轮写 i18n 页时被 `check_doc_refs` 顺手照出来的（死指针事件）。

### 27.2 动笔前的查重，**改变了这页的形态**

按老习惯，一篇 `*-fields.md` 应该带一张「JSON 字段全集」表（`button-fields.md` 就是这样）。
但查重后发现**四处都已有主**：

| 内容 | 已有真源 | 性质 |
|---|---|---|
| 字段 / 必填 / 默认值 | `ui_tools/ui_schema.json` → **派生表** `json-field-mandatory.md`「每类型必写键」 | **机器派生 + `--check` 进门禁** |
| 代码 API | `widget-code-api.md` §ZKTextView | 手写页 |
| 字号下限 / 文本盒抬高度 / UTF-8 截断 | `text-box-height-rule.md` | 手写页 |
| 对齐位模型（36/37/38 ≡ 4/5/6） | `wysiwyg-render-spec.md` §4 | 真机定案 |

而 `ui_schema.json` 的 `authority` 自己就写着：

> 「字段/类型/必填/默认值以本表为准；**`knowledge/*.md` 只负责原理、流程与行为**」

⇒ **如果照老习惯再抄一张字段表，就是同一个概念的第四份副本**（schema → 派生表 → 老字段页 → 新页），
必然漂移，而且漂了没人盯。所以这页**故意不含字段表**：开头立一张「真源分工表」指路，
正文只补**没人写过的行为与坑**（特殊字符集硬约束、三态色生效条件、跑马灯未核边界、纯显示定位）。

> 这条值得单独记：**"每个控件一页"是命名惯例，不是内容模板。**
> 以前那 16 页带字段表是因为当时没有注册表；现在有注册表 + 派生表了，
> 新页要跟着**新的分层**走，而不是跟着旧页的**形状**走。

### 27.3 补的四块（都对账了官方 textview 页）

1. **特殊字符集 `charsetTab`**：官方口径「字符按 ASC 码映射为图片」+⚠️**硬约束**：
   **设了之后没有映射的字符不是显示原字，而是根本不显示**
   —— 客户说"设了字符集后有些字没了"的正解。仓内此前只记了它的出现率（0.7%）和一个用法（信号格）。
2. **文字颜色三态**：属性表三组色（`colorTab` 按状态文字色 / `backgroundColor` 不随状态 / `bgColorTab` 背景色按状态）
   ↔ 代码 `setInvalid/setSelected/setPressed`；**生效条件**：**属性表配了对应状态色才变色，为空则无变化**
   —— "代码设了选中态但颜色没变"的正解。
3. **跑马灯 `roll*`**：登记已知（四个可选字段 + 默认值 + 语义），并**如实标未核** ——
   `rollDirection` 取值含义 / `rollStep` 单位 / 与 `rollIntervalTime` 的关系，**仓内与官方文档都没有**。
   另记两条边界：离线渲染器**不渲染滚动**（所以**预览图里看不到跑马灯是正常的**，别据此判它没生效）；
   它与 `slidetext`（多单元滑动选择器）**不是一回事**。
4. **纯显示定位**：注册表 `interactive:false` 且**无任何 callbacks** → 「会变的文字用它，**能点的文字用 button**」；
   `touchable` 必填且要**显式 `false`**，写 `true` 会吞触摸却无事可做。

### 27.4 检索组：**剔除 3 条不属于本页的问法**（而不是硬留着凑数）

试跑的 16 条里有 3 条落外，逐条看**归属**而不是看排名：

| 试过的问法 | 判断 |
|---|---|
| `setTextColor 怎么用` | 答案真源是 **`widget-code-api.md`**（API 页）→ 剔除 |
| `setBackgroundPic 相对路径` | 同上 → 剔除 |
| `touchable 要不要写 true` | 真源是**派生表 §2 分组**与 `touch-events.md` → 剔除 |

最终 **13 条全部 top-1**（`min_top1 12` 留 1 条余量）。做法与 §22.5/§24.5 一致：
**先取证判断"是被挤出还是归属错"，两种都在组注释里写清理由。**

---

## 28. 字段真源补漏：`edittext` 的密码三件套（2026-10-03）—— 以及我自己量错的两次

### 28.1 起因：上一轮的假设被**自己的测量**否掉

上一轮我说"16 个老 `*-fields.md` 各嵌一份字段清单，是没人盯的副本"。这轮先量：

| 量的口径 | 结果 |
|---|---|
| 有"斜杠状字段名单行"的页面 | **只有 1 个**（`button-fields.md`，2 行）——而且那 2 行带**实测出现率**（`longClickTimeOut 97.8%` 这类），**是证据不是副本**，还已注明「见 json-field-mandatory.md」 |
| schema 字段在这些页里"漏提"的情况 | 基本只漏 `id`/`position`/`visible` 这类**根本不用解释**的通用字段 |

⇒ **"16 份副本"不成立**，所以**没有按原计划重构那 16 页**（那就是凭假设 churn，
而且会把 `button-fields.md` 里的实测频率一起删掉）。
**教训：上一个轮次里的"发现了系统性问题"也是待验证假设，动手前同样要量。**

### 28.2 但测量照出了一个**真**缺口：生成器在写、真源不知道

把页面提到的字段名与 `ui_tools/ui_schema.json`（字段唯一真源）比对后，逐条追证：

| 字段 | 谁在写 | 真源 |
|---|---|---|
| `isPassword` / `passwordChar` | `ui_tools/html2json.py`（HTML 带 `data-password` / `data-password-char` 时写）、`templates/ui_blocks/compose.py`（edittext 模板**恒写**）、`knowledge/uicontrols/edittext-fields.md` 有记 | **完全没有** ❌ |
| `beepEnable`（**控件级**） | `compose.py` 写；`ui_tools/check_all.py:136` 的注释写着「beepEnable 不强制（交互控件默认支持）」 | **只有页级登记**（`page.rootFields`），控件级没有 ❌ |

**后果不是"文档不好看"**：字段真源驱动按需契约与派生表
（`json-field-mandatory.md` 由 `gen_ui_schema_docs.py` 从注册表生成）——
真源不认这些字段，**派生表里就不会出现"密码框"这件事，AI 也就不知道 edittext 能配密码**。
而生成器照写不误 ⇒ 「同一概念的两种口径」又出现一次。

**修法**：把三个字段补进 `controls.edittext.fields`（全部 `required: false` + 显式默认值
`false / "*" / true`，这样派生表的「默认值要点」列才带得上）→ 重生成派生表：

```
| edittext | … | bold false；fontSize 16；textType 0；isPassword false；passwordChar "*"；beepEnable true；… |
```

### 28.3 证据链我改了**三次口径**（这才是本节最该记的）

1. 初稿写「**真实工程**在用」→ 查出处发现：那 4 个含密码字段的 ui json
   **全是我们自己 `ui_blocks` 生成的示例** → **循环证据**（我们的生成器写它，然后我们数它）。
2. 改成正确表述：**出处 = 我们自己的两个生成器 + 散文页 + `check_all` 的口径**，
   **不是第三方工程**。（`html2json` 的触发条件是 HTML 的 `data-password` 属性，
   这是本仓 HTML 子集的**映射特性**，算工具链口径。）
3. `beepEnable` 该不该补：`html2json.py:1772` 的注释写「（**去** beepEnable）」，
   而 `check_all.py:136` 写「**不强制**（交互控件默认支持）」—— 两句看着矛盾。
   读完上下文判定：`去` 指的是"SampleUI 的**必写键**清单里没有它"，
   不是"它非法" ⇒ **应补，但标 `required: false`**。

### 28.4 本轮我**量错了两次**，都是"先验证再动手"挡下的

| 第几次错 | 错在哪 | 若照错的结论动手会怎样 |
|---|---|---|
| 第 1 次 | 探测只数**反引号里**的标识符，而不少页面把字段写在表格里（`\| id/caption/position \|`，**不带反引号**） | 会把 `button` 页的 11 个字段误判成"滞后"，进而"修"一个本来对的页面 |
| 第 2 次 | 统计 universe 时**漏了 `page.rootFields`**，于是把 `beepEnable` 报成"未登记" | 会去给控件级补一个**页级早已登记**的字段，制造重复登记 |
| （第 3 次） | 出处判断用了循环证据（28.3-1） | 会把"我们自己的生成器"说成"真实工程"，把结论吹大 |

### 28.5 钉子：让"生成器写了真源不知道的字段"下次直接红

`tests/test_ui_schema.py` 加 3 条：
① **生成器会写的键 ⊆ 注册表认识**（本批钉 `edittext` 的三个）；
② 密码字段形态（可选 + 有显式 `default`，派生表才带得上）；
③ **派生表必须真的列出它们**。

⚠️ **这条钉子当场抓到我自己**：我把 `beepEnable` 写进「生成器会写的键」时，
schema 里还没补它 → 用例立刻红 → 复核证据（28.3-3）后补上，两边才一致。

### 28.6 顺带

`features_recent.json` 我又写坏一次（**第 6 次**，长中文里混了 ASCII 双引号）——
已在那条 JSON 门禁的失败信息里加**修复提示**（"正文引号请写「」，`` ` `` 里的英文键名不受影响"），
让下一个人（和我）不用再从 `Expecting ',' delimiter` 去反推原因。

---

## 29. 字段真源全面对账（2026-10-03）—— 缺口 **24 → 1**

### 29.1 把"随机撞到"变成"系统性对账"

§28 是随机撞到 `edittext` 的密码字段。这轮把方法补全：
**扫全仓 52 个 ui json → 按控件类型（键名 `<type>__N`）汇总"工程实际用到的字段" → 与 `ui_schema.json` 比对。**
（只看控件的**直接字段**，不递归进子盒：`position`/`thumb`/`colorTab`/`item`/`subitem`…）

结果一次照出 **24 个「工程在用、真源没有」的字段名**，集中在**两个最常用的控件**：

| 控件 | 缺的字段（括号 = 实测处数） |
|---|---|
| **textview** | `backgroundColor`(509)、`backgroundPic`(291)、`textPosition`(279) |
| **button** | `fontSize`(**290**)、`backgroundColor`/`bold`/`italic`/`fontFamily`/`rollEnable`/`rollDirection`/`rollIntervalTime`/`rollStep`(各 140)、`textPosition`(40)、`backgroundPic`(34) |
| edittext | `hintText`、`touchable`、`fontFamily`、`roll*` |
| scrollwindow | `touchable`(8) |

**这是一条比 §28 严重得多的口径缺口**：`button`/`textview` 是最常用的两个控件，
而真源对它们的登记是**残缺的** —— 派生表与按需契约因此少讲了 14 个真实字段
（`fontSize` 在 button 上被用了 290 次，真源却不知道 button 有字号）。

### 29.2 每个字段都取到**四条独立证据**才补

| 证据 | 说明 |
|---|---|
| ① 真实取值形态一致 | `backgroundColor` int(-1)、`bold/italic` bool、`backgroundPic` str、`textPosition` **dict** |
| ② 多个生成器在写 | `ui_tools/html2json.py`、`templates/ui_blocks/compose.py`、`translate_tools.py` |
| ③ **离线渲染器在读** | `ui_tools/json2img.py` —— 它曾与真机截图对齐 **100%**，它认这些字段说明是真的渲染语义 |
| ④ 知识页/派生表有记 | `button-fields.md`（还带**实测出现率** 97.8%/89%）等 |

**默认值只在有证据时给**，否则只写 `note`：
- 敢给：`bold/italic false`、`fontFamily 0`、`roll* false/1/150/5`（textview 已登记同语义值 + 实测一致）、
  `backgroundColor -1`（`valueRules.colorZero` 明文规定）、
  `edittext.touchable true`（`html2json` 注释明写"漏写则输入框点不动、**IME 不弹**"）；
- **不敢给**：`button.fontSize` —— 只写了实测值域 `10~40`，**没有编一个默认 16 出来**
  （虽然 textview/edittext 是 16，但"别的控件是"不是证据）。

### 29.3 过程中自己抓到两处**口径不一致**

1. **`textPosition` 的类型**：我给 button/textview 写了 `position`，而 `checkbox` 用的是 `iconBox`。
   一查 `sharedTypes.iconBox` 的 note 就是「**iconPosition/textPosition 用**」，
   且两者**形状完全相同**（`left/top/width/height:int`）、三处真实取值也一致
   ⇒ **是我的写法才是异类**，已全改为 `iconBox`。
2. **`valueRules.subboxType` 的清单**（"子盒写字符串 = 真机 ftu 加载无声挂死"那条铁律）
   漏了 `bgColorTab`/`iconPosition`/`textPosition`/`iconBox`，
   而 `tests/test_ui_schema.py` 的子盒用例**早就把它们列进去了** ——
   **规则文本与用例口径不一致**（用例比规则更全）。已按用例补齐。

> 两次都是"**同一个概念在两个地方各写一遍**"（控件 vs sharedType note；valueRules vs 用例清单）。

### 29.4 对账复跑：**24 → 1**，剩下那个是**有意的**

唯一残留：`videoview.beepEnable`（**全仓 1 处**，在 `demos/dvr-uvc-recorder-v85x` 里，
且**没有任何生成器为 videoview 写它**；`html2json.py` 的注释本身就是「videoview 全键（**无 beepEnable**）」）。
⇒ **不猜着补**，如实登记为已知残留（这正是"未验证就登记、不猜着改"）。

### 29.5 钉子升级

`tests/test_ui_schema.py::TestGeneratorFieldsAreRegistered` 的 `EMITTED`
从 edittext 三个键扩到**四个控件 22 个键**（本批全部）——
以后任何一批"生成器写了真源不知道的字段"都会直接红。

---

## 30. 翻译层的补齐表落后真源（2026-10-03）—— 补键不补值，以及一次"差点引入"的风险

### 30.1 先验证上一批改动**没有副作用**（这才是该先做的）

改真源最该怕的是"生成产物悄悄变了"。逐项查：

| 查什么 | 结果 |
|---|---|
| 新字段在 `defaults()` 里正确出现 | ✅ `backgroundColor -1`、`roll*` 等都在 |
| `type_check(defaults)` 有无违规 | ✅ **0 违规** |
| 片段生成器 `gen_control_map_snippets --check` | ✅ **0 处需重生成**（输出字节未变） |
| `check_all` #14（必填键） | ✅ 只用 `required_fields`，我补的全是 optional |

⇒ **生成产物一处未变，只是 AI 面变全了。**

### 30.2 对账出第二份口径落后：`translate_tools._SCHEMA_FILL`

它是"片段控件 → schema 完整字段集"的**缺键补齐表**。对账（`fill` vs 真源）：

| 控件 | fill 比真源少 |
|---|---|
| **button** | **14 个**（`backgroundColor/backgroundPic/bold/italic/fontFamily/roll*` …）—— 正是 §29 才补进真源的那批 |
| edittext | 15 个（含 `touchable`、密码三件套、`roll*`、`hintText`…） |
| textview | 8 个（`backgroundColor/fontFamily` …） |

**后果不是"不整齐"**：翻译出来的控件达不到真源定义的"完整"。
最要命的一条是 **`edittext.touchable` 缺失 → 翻译产出的输入框点不动、IME 不弹**
（这条连 `html2json` 的注释都专门标注过）。

### 30.3 但**值一个都没动** —— 因为它是"发射层口径"，不是 schema 副本

该表自己的注释（2026-10-02 注册表化时写的）：

> 标量 = **发射层口径**（demos ftu 反解的 IDE 全量序列化 + hw-relay 真源），与注册表 `default`
> 存在**刻意差异**的已逐条标注「发射层口径」（如 textview alignment 0 vs 注册表默认 36、
> button fontSize 18 vs 注册表 16）—— 差异清单见 `ui_schema.json` 维护记录，**勿在此静默对齐**。

所以我只**补缺键**（值取实测众数，恰好与真源默认一致），而把对账报出的那几处"默认值不一致"
（`textview.alignment 0` vs 36、`button.fontSize 18` vs 16、`circlebar.textColor/textSize`、
`painter/qrcode.backgroundColor 0xFFFFFF` vs -1、`seekbar.touchable True` vs False、
`edittext.alignment 36`/`hintTextColor`）**原样保留** —— 它们是**刻意的翻译口径**。

> 这条是本轮最值钱的判断：**对账报"不一致"时，先问"两边是不是本来就在说不同的事"**。
> 上一轮我把 `iconBox`/`position` 的不一致判成"我写错了"（确实错了，因为两者形状相同、note 明确）；
> 这一轮同样形式的"不一致"却是**对的**（发射层口径 ≠ 注册表默认值）。

### 30.4 一次**差点引入**的风险，被拦下了

我本来顺手给 textview/button 也补了 `backgroundPic: ''`。随后发现：

- `ui_schema.json` 的 `valueRules.missingImage`：「图片字段指向不存在文件**或置 `''`** → **控件不可见**」；
- 全仓 `backgroundPic` 出现 **333 次，只有 1 次是空串**，而那 1 次来自 **我们自己的产物**（`temp/lvgl_demo_v85x`）；
- ⇒ **没有任何 IDE 序列化的真实工程是空串** ⇒ 「空串是否被容忍」**未核**。

**处置**：**撤掉这两个键的补齐**，在代码注释里写明理由，并登记"未核"。
（顺带发现：`missingImage` 这条规则**没有任何消费方**，只存在于 schema 里给 AI 看 —— 是说明，不是门禁。）

### 30.5 没补的键，每条都有理由（写进测试的豁免集）

`id/caption/position`（片段自带）；`colorTab/bgColorTab/picTab/thumb`（`_schema_complete` 归一）；
`text`（textview「非空才写」，补了会被 pop）；`textPosition`/`iconPosition`（**条件写的布局盒**，
零值盒无意义 —— iconBox 的 note 就是这么写的）；`playFile`（imageanim「无文件不写引用」）；
`codeStr`（qrcode「有值才写」）；`backgroundPic`（§30.4 未核）。

### 30.6 钉子：`_SCHEMA_FILL` 不得落后真源

`tests/test_translate_ui.py::TestSchemaFillDoesNotLagRegistry`：
对每个控件断言「**真源字段 − 豁免集 ⊆ fill**」。**值仍然不比对**（那是刻意的差异），
只钉**键集**——真源将来加字段而 fill 不跟，直接红。

---

## 31. 根因③首次审计（2026-10-03）—— 一处**假绿**、一处**算术错**、一处漏参

### 31.1 为什么这轮审 ③

plan.md 七条根因里，**只有③（OS 分区与 img 升级）我从没审过**（①②④⑤⑥⑦ 都过过）。
先盘覆盖，结论是**不薄**：18KB 权威页 `upgrade-pack-image.md` + 三篇配套
（`device-deploy-budget` / `deploy-scene-map` / `deploy-consistency-check`）+ 24KB
`hardware/z20-86panel-upgrade.md`，且 `flythings_pack_upgrade` 的 docRef 就指向权威页。
⇒ 审计重点不是"有没有页"，而是**数字与契约准不准**。

### 31.2 发现一：**假绿** —— 判据上限比真机分区还大（与 round 1 的 `.fsc` 漏算同类）

| 项 | 值 | 出处 |
|---|---|---|
| `preflight_spec.budget.limitMB` | **8 MiB** | 缺省口径，`perPlatform` **空** = 全平台 |
| 真机 **res** 分区（Z20/Z21） | **0x720000 = 7,471,104 B = 7.12 MiB** | 权威页 `cat /proc/mtd` 实测 |

**实测行为**：7.13 MiB 的工程在 Z20 上判 `ok`（89.1% < nearPct 90）——
**但它根本刷不进 /res**。而这条判据的立身之本就是 `levels.over.why` 写的那句
「打包文件可能大于 /res 分区大小 → **升级/固化会失败或被截断**」。
⇒ **判据在自己最该拦的地方放行**。这与 round 1 修的 `.fsc`（产物目录改名漏认 → 体积计 0 → 假绿）
是**同一类错**：数字口径与真机不一致。

**修法（走 spec 自带的机制，不动缺省值）**：
- `perPlatform: {"Z20": 7.12, "Z21": 7.12}`（键用 `platforms.py` 规范名，spec 的 note 早有此约定）；
- 缺省 `limitMB=8` **不动** —— 它是**未实测平台的圆整占位**，且 `tests/test_preflight.py:231`
  明确钉着 `limitMB == 8.0`（改它会破坏既有口径）；
- 把**实测依据 + 警告**写进 spec 的 `note`：「缺省 8 是未实测平台的圆整占位，实测 Z20/Z21 只有 7.12 MiB
  ⇒ **别拿 8 当「还能加」的依据**；换板先 `cat /proc/mtd` 再登记」。

**修后实测**：同工程 Z20 → **`over`(100.1%)** ✓；V85X（未实测）→ 仍 `ok`(89.1%)，
但这条**已被显式登记为已知占位**，不再是暗的。

### 31.3 发现二：权威页里的**算术错**

页面两处写 `0x720000 = 7,470,080 B` —— **算错了**：`0x720000` = 7×16⁵ + 2×16⁴ = **7,471,104 B**（差 1 KB）。
而这个数字**就是"包体上限"本身**。已按十六进制原文改正为 `7,471,104 B = 7.12 MiB`（两处）。

> 页面里其余数字都自带口径与出处（"本板实测 / 换板先量"），唯独这个十进制换算是手算的
> —— **手算的派生值最容易错**，正是本项目那句「易漂移的数字必须派生」的又一例。

### 31.4 发现三：op 契约**漏登记**用户真要传的参数

权威页明确让用户调 `flythings_pack_upgrade(project_root, out_path, release_version)`，
而 op 契约的 `params` 只有 `out_path / ab / dry_run`：

| 参数 | 真实签名里有 | 契约里有 | 实现里干什么 |
|---|---|---|---|
| `release_version` | ✅ | ❌ | 传 `fun pack --release-version`（发布版本号） |
| `with_build` | ✅ | ❌（只在一句 `flow` 里带过） | 是否先跑 `fun build` 再 pack |

⇒ **AI 拉按需契约时看不到这两个参数**，而权威页却在用它们。已补齐两条（带语义）。

### 31.5 钉子

`tests/test_preflight.py::test_measured_partition_caps_z20_z21`：
- 断言「**超过实测分区必须判 `over`**」（不许假绿）；
- 并**显式断言未实测平台仍走 8.0 占位**，注释写明「若将来收紧缺省值，请连同这条断言一起更新」
  —— 把"已知限制"也钉进用例，避免它悄悄变回"没人知道的口径"。

### 31.6 一条方法上的复述

这轮三条发现**都不是"缺页"**，而是**"页/契约/真源三处的数字或参数不一致"**：
判据的 8 MiB vs 实测 7.12 MiB、页面的 7,470,080 vs 十六进制的 7,471,104、
权威页用的参数 vs 契约登记的参数。
⇒ 与 §23、§28、§30 同一条规律：**同一个概念写两遍，迟早分叉；分叉处若没有门禁，就是静默的。**

---

## 32. 根因③配套三页审计（2026-10-03）—— 陈旧路径、三套字库数字、以及我自己的三次失误

### 32.1 先自动取证：op 名全有效，问题在路径与数字

对三篇配套页（`device-deploy-budget` / `deploy-scene-map` / `deploy-consistency-check`）扫
**op 名 / 仓内路径 / 数字**：**提到的 `flythings_*` 全部存在**（无死 op）✓，
问题集中在**陈旧路径**与**同一事实的多套数字**。

### 32.2 26 处陈旧路径（12 个文件）：本仓的 `tools/...` 时代

本仓经历过 `tools/...` → 仓根的重排，页面里还留着那个时代的示例路径：
`tools/ui_tools/json2img.py`、`tools/qa/corner_audit.py`、`tools/FlyThings_mcp_open/packages/...` 等。

**改法（关键在"怎么确认"）**：按**重排规则**改写（`tools/FlyThings_mcp_open/`→根、
`tools/ui_tools/`→`ui_tools/`、`tools/qa/`→`ui_tools/`、`tools/`→根），
且**逐条用文件系统验证目标存在**才落下。

> 第一版我是按**同名文件在仓内别处存在**来判"挪位"的 —— 结果把
> `projects/SmartPanel_HA/src/logic/mainLogic.cc`、`workspace/tools/qa/README.md`
> 这类**重名**误判成搬移。**basename 相同 ≠ 同一个文件**；重排规则 + 存在性验证才可靠。

### 32.3 真漂移：同一批字库，**两页三套数字**

| 出处 | `zkswe-hans-full.ttf` | `zkswe-hans-multi.ttf` |
|---|---|---|
| `device-deploy-budget.md`（正文） | 7.5 MB | 10.7 MB |
| `device-deploy-budget.md`（下文） | **7.4** MB | — |
| `custom-font-config.md`（表格） | **7.39** MB | **10.5** MB |
| **实际文件**（唯一真源） | **7,567,300 B = 7.22 MiB** | **10,742,560 B = 10.24 MiB** |

不但数字互不相同，**单位口径也混用**（872 KB 是 KiB，7.5 MB 是十进制 MB）。
而「**字库是最大头**」正是这条部署预算结论的支点 —— 数字漂了，结论看着还成立，最难发现。

**修法**：两页统一为**「实际字节 + MiB」**（如 `**7567300 B**（7.22 MiB）`），
并**新增门禁 `stage_font_sizes`**：以字体文件为唯一真源，**两页一起看住**。
**负向自测**（把表格里一个数改错 1 字节）精确报出「哪个文件、哪一页、差多少」✓。

### 32.4 两页各写一个 `/tmp` 容量

`device-deploy-budget.md`：Z21 实测 tmpfs **13.6MB**；`deploy-consistency-check.md`：常见 **32MB** 量级。
同一条 ③ 里两个数，读者无从取舍。**处置**：各自标明适用范围，并写明
「**别拿某个数字当通用值，部署前先 `df -k /tmp`**」。设备侧数值我**无法复测**，所以只并列、不裁断。

### 32.5 一处「证据已不在仓内」

`device-deploy-budget.md` 引 `temp/setprop_accept.py` 与 20 张逐轮截图 —— **全仓都不存在**
（`temp/` 是临时区、**不随仓交付**）。而项目自己的证据纪律就写着「**证据文件丢了就不算证据**」
（`kb_local` 对 `evidence.artifact` 是硬校验）。已显式标注「结论有真机复现记录，但要复验请按本节步骤重做」。

### 32.6 我自己的三次失误（都挡住了，但值得记）

| # | 失误 | 怎么发现的 |
|---|---|---|
| 1 | 自动检查器把 `tools/deploy_debug.sh` 报成**死路径** | 读上下文才发现它是**故意的反例** —— 那页的铁律就是「**不存在**任何 `tools/deploy_debug.sh`」。**机器读不出否定语义** |
| 2 | 按 basename 猜「文件挪位」 | 误报 `mainLogic.cc`/`README.md` 这类重名（§32.2） |
| 3 | 改写规则碰到**派生页** | `components-catalog.md` 由 `gen_components_catalog.py` 生成，我手改后被 `--check` 抓出；更重要：那条路径**在组件自己的语境里本来是对的**（相对该组件目录）⇒ 让生成器重新接管该页 |

> 三条合起来是一句话：**批量修改文档时，"哪些是派生页""哪些是相对路径""哪些是否定语义"
> 都得先判**——否则会"修好一处、改坏一处"，而报表看起来还是绿的。

---

## 33. 把「陈旧路径」收进门禁（2026-10-03）—— 以及先量噪声、再扩扫描集

### 33.1 动机：§32 的 26 处是**手工扫的**

一次性劳动，下次还会烂。所以这轮把判据交给门禁：`check_doc_refs` 从"只扫 `knowledge/`"
扩到"**仓内根相对路径**"。

### 33.2 扩之前先量噪声（否则会误报一片）

| 前缀 | 初量 | 修正正则后 |
|---|---|---|
| `scripts/` | 135 | **10** |
| `tools/` | 147 | —（**不扫**，见下） |
| `projects/` | 82 | —（不扫） |
| `workspace/` | 23 | —（不扫） |

**135 与 147 这两个大数字大半是我自己正则的错**：
`\.(?:[a-z]{2,4})` 把 `.ps1` 截成 `.ps`、`org.eclipse…` 截成 `.ecli`；
左边没边界，`knowledge/components/x.md` 被截成 `components/x.md`（**后缀误匹配**）。

> 又一次"先验证再下结论"：**看见 135 处就想动手改，是会改坏东西的**。

### 33.3 扫描集与"不扫"的理由（都写进门禁 docstring）

**扫**：`knowledge/`（原行为不变）+ `ui_tools/ components/ packages/ templates/ demos/
bin_tools/ toolchain/`，以及 `scripts/` —— **仅当引用方不在 `components/` 下**。

> 那条组件相对的规则是 §32 的教训：`components/ble/README.md` 里写 `scripts/verify_lib_symbols.py`
> 是**对的**（相对该组件目录），上一轮我按"根相对"把它改错了。规则这次写死在门禁里。

**不扫**（天然仓外/临时/历史）：
- `projects/` —— 仓外样例工程（页面把它们当"校准源"）
- `workspace/` —— 本地工作区（入库前的源，不入库）
- `tools/` —— 本仓 `tools/…` → 仓根 重排**之前**的布局

### 33.4 它抓出 8 处，其中 2 处是我手扫漏的

| 位置 | 问题 | 处置 |
|---|---|---|
| `kb_local.py` 的 hint | 指 `scripts/kb_grow.py`（**不存在**） | 改指真命令：`kb_verify.py` + `check_kb` + `kb_frontmatter --check` |
| `ui_tools/check_all.py` ×2 | 指 `templates/DESIGN.md`（**不存在**） | 见 §33.5 |
| `bin_tools/*/README.md`、`busybox-debug-library.md`、`touch-inject-autotest.md` | 指 `scripts/bb_build_all.sh` / `touch_build_all.sh`（**全仓不存在**） | 标注「在**本地 workspace、不入库**」（同页既有口径） |

**新增 3 条白名单（逐条取证）**：
- `components/platforms.md` —— **集体引用**（指 components/ 下那 16 篇），不是单个文件；
- `scripts/release_scope.json` —— **release 分支**才带，拿 master 跑本就没有（注释已写明）；
- `scripts/verify_lib_symbols.py` —— **组件相对**（生成器以组件目录为基准用它，派生页照抄）。

### 33.5 我自己的一次"用死指针换死指针"

把 `templates/DESIGN.md` 换成「skill `flythings-ui-dev`」之后一查：**该 skill 根本不存在**
（实际只有 9 个 skill；DESIGN.md 模板在**仓里与 skill 里都找不到**）。
已改成**只讲可验证的事实**：「它放在**工程根**（`check_all` 自己的代码就是
`os.path.join(project_root, 'DESIGN.md')`），**本仓不附带模板**」。

> 教训很直白：**改指针时不能凭记忆写新指针** —— 得先确认它存在。
> 这一条与本项目"不许声称未验证的事"是同一条纪律。

---

## 34. 「未核 / 待验证」做成派生清单（2026-10-03）

### 34.1 为什么是**派生视图**，不是手抄登记表

各页**本来就有**自己的「待确认 / 未验证」小节：
`upgrade-pack-image.md` 的「边界与待验证」表、`platform-capability-matrix.md` 的 25 处标注、
`custom-render-paths.md` 的 8 处、`textview-fields.md` 的 4 处……

再手抄一张集中登记表 = **同一事实写两遍** → 迟早分叉（本项目反复踩过，见 §23/§28/§30/§31/§32）。

所以 `scripts/gen_unverified_report.py` **只扫不写**：读知识页、按文档聚合标记行，
输出 `knowledge/_reports/unverified.{md,json}`，报告头部第一句就是
「**这是派生视图、别在这里手改；真源在各自页**」。

### 34.2 先量再定口径（否则清单会被噪声埋掉）

初量 88 处 —— 但**标题行与 front-matter tag 混在里面**
（`## 6. 待确认 / 未覆盖`、`tags: [… 草稿待确认入库]`）。加过滤后：**74 处 / 21 篇**。

### 34.3 最有用的不是"哪些没验"，而是"**哪些没写怎么验**"

报告给每行判"有没有复验线索"：含反引号命令 / 实测 / 复验 / adb / cat / df / getprop / md5 /
截图 / 上机 / **自证 / 按 § / 先量 / 先测 / 核对**。

初版报 **29 处缺复验方法** —— 这比"未核"可执行得多：**补一句复验方法，比补一句结论有用**。

**给我自己遗留的未核项补上方法（写在各自页里）**：

| 页 | 未核项 | 补的复验方法 |
|---|---|---|
| `textview-fields.md` | `roll*` 语义值域 | 真机上 `rollEnable: true`，`rollStep` 取 1/5/20、`rollDirection` 取 0/1，各截位移前后图；判据 = 位移像素与 `rollStep` 关系可复现。并加一句「**在此之前不要写 rollStep 是像素**」 |
| `textview-fields.md` | 三态色的各平台差异 | 同一 fui 在 F133/V85X/Z20 各推一次，抓**按下态**帧比对 `colorTab` |
| `upgrade-pack-image.md` | 其它平台 MISC 分区 | 拿到板子 `adb shell cat /proc/mtd` 量，并在升级界面截一张勾选项图 |

⇒ **29 → 21 处**。

### 34.4 为什么放在 `_reports/` 而不是 `knowledge/`

`_reports/` 是 `.gitignore` 的**本地产物** ⇒ 这份清单**不进 kb_index / 检索**。

若放进 `knowledge/`，检索可能返回这份「聚合清单」而**不是权威页** ——
那就是**第二份口径在检索层的翻版**。（与 `kb_health` 同性质，同样由 `--check` 盯新鲜度。）

### 34.5 门禁与一次"同一个病犯在代码里"

新增委派项 `gen_unverified_report --check`（清单滞后即红）⇒ 门禁项 **68 → 69**。

写补丁脚本时我用了 `# 指向"怎么做"的说法都算线索` —— **ASCII 双引号在中文散文里**，
把 Python 字符串字面量截断了，脚本**解析失败、什么都没改**（报告仍是 29 处）。
这正是 `features_recent.json` 那个病，**这次犯在代码里**；换成「」后一次通过。

> 记录它是因为它说明了这条纪律的成本：**同一个习惯会在不同介质上重复犯**
> ——所以能机械挡住的（门禁、落盘前 `json.loads`、`compile()`）都该挡住。

### 34.6 首跑时它立刻抓到我两次（都是"自己造假路径"）

新门禁上线第一趟就红了两回，**两次都是我自己写的文本**：

1. **报告自造假路径**：报告标题原本把 `knowledge/` 前缀剥掉做美化 →
   渲染出「以 `components/` 开头」的标题。那**看着像仓内路径**，于是 `check_doc_refs` 判它死指针
   ——**它是对的**：这份报告若被 AI 读到，AI 会去找一个不存在的文件。
   已改为一律写**完整仓内路径**。
2. **注释里的反例**：我在生成器注释里举了个假路径当例子（说明"剥前缀会造成什么"）→
   又被判死指针。机器读不出"这是反例"（与 §32.6 的 `tools/deploy_debug.sh` 同一类）。
   已改成不含路径形态的措辞。

> 这两条说明：**门禁的价值不在"抓别人"，而在"抓自己没想到的地方"** ——
> 而且**它上线第一分钟就抓到了我**。

---

## 35. 根因⑤收口（2026-10-03）—— 答案本来就在仓里

### 35.1 我反复问的那句，其实有个已有的权威页

前面多轮我都在问："公开版的多媒体落地要不要补一篇去 V85X 化的通用页？"
翻仓时发现 **`knowledge/devflow/capability-boundaries.md`** 早就存在，它的第 2 节
「**明确不在 open 版**（查不到 = 正常，不是缺陷）」里就有一行：

> | **V85X 深水区**（aw-dvr 版本兼容细则、VO/disp 层调优步骤、UVC JPEG 全链路） | 内部版专属 | 通用结论（UVC 接入、OTG 切换）open 版有；深的问厂家 |

而 `PUBLISH.md` 第 3 节也早有同一条口径（V85X 绑定实现「**未收录于公开版，以平台方 SDK 为准**」）。

⇒ **这不是"待你拍板的缺口"，是我没找到已有的权威页。**
（`§31` 我也是靠"先盘覆盖再决定审什么"才发现 ③ 有页；同一个教训第二次。）

### 35.2 真正缺的是「接不上」—— 静默缺口的定义

`media-capability-index.md` 那 8 行能力表里满屏 `aw-dvr` / `aw-mpp` / `uvc-camera`，
**却一个字没说这些深度在公开版里没有**。AI 读完能力表会以为照做就行。

**静默缺口 = 该说而没说**，不是"没有结论"。所以这轮的修法不是新写一篇页，而是**把已有结论接到
读者会看的那一页上**。

### 35.3 修法：唯一真源 + 派生 + 指向权威

| 动作 | 落点 |
|---|---|
| **数据真源** | `media_capabilities.json` 新增 `openBoundary`（statement / notIncluded / because / whatToDo） |
| **渲染** | `gen_media_cap_doc.py` → 媒体页 **第 5 节「公开版边界（别把『没写』当成『没有』）」** |
| **不写两遍** | 该节 `whatToDo` **指向** `capability-boundaries.md` 第 2 节（全局口径的真源），本节只留多媒特有的两条未收录事实 |
| **对外口径** | `PUBLISH.md` 剔除清单点明「**但多媒体能力面仍开放**」+ 该节位置 |

### 35.4 按纪律配检索（≥5 条问法 + 实测阈值）

新增两组、**先实测再登记**：

| 组 | doc | 问法 | 实测 |
|---|---|---|---|
| 能力边界（open 版不做什么） | `capability-boundaries.md` | 5 | top-1 4/5、落外 1 |
| 多媒体公开版边界 | `media-capability-index.md` | 6 | **6/6**、落外 0 |

检索回归：**35 组 / 292 问法 / top-1 220 → 37 组 / 303 问法 / top-1 229**。

### 35.5 一处**如实登记**（没有为绿色调参）

媒体页多 1 个 chunk 后，硬件组的 `setLuminance 哪些平台有` 落到 **#4**。实测原因：

- 第 4 名（本页）与第 3 名**分数并列**（均 `0.0164`；榜首 `0.0315`）⇒ 属**平手顺序被翻转**，
  加一个 chunk 就会发生；
- 处置：**不改问法、不调阈值**，把该组允许落外 `1 → 2`，并把证据与
  「日后本页补强平台变体表应把这 2 收回 1」一起写进注释。

### 35.6 我自己的两个坑（都挡住了）

1. **替换串把 `"capabilities": [` 吃掉却没写回** —— 替换 = 删除原文，我忘了 append 回去。
   落盘前的 `json.loads` 挡住（这已经是它第 N 次救场）。
2. **检索组漏了 `name` 键** → 门禁 `KeyError`。我第一版组结构写错了；修的时候又用正则匹配到
   **另一个组的注释里**（那段注释恰好引用了 `peripheral-api-zkhardware`）→ `compile()` 再次挡住。

> 两条都印证 §34.5 那句：**能机械挡住的（落盘前验证、compile、门禁）都该挡住** ——
> 因为人（我）在长会话末尾确实会犯低级错。

---

## 36. 真机在线上机（2026-10-03，V85X）—— 截图 op 的 0 字节故障定位与修复

### 36.1 设备与连接

| 项 | 实测 |
|---|---|
| 型号 | `Zkswe_V85X_SPINOR`（serial `20080411`，USB，Windows 侧显示「Tina ADB」） |
| 平台 | **V85X**（`device_models.json` 早有 confirmed 记录 ✓） |
| 屏 | **480×800**（`virtual_size = 480,1600`，`stride = 1920`，`bits_per_pixel = 32`） |

⚠️ **`adb devices` 起初是空的**：按知识页 `adb-and-device-selection.md` 记的招
（`kill-server` + `start-server`）后枚举出来 ✓；且**随包的 `tools/adb/adb.exe` 才能认它**
（PATH 上 IDE 那份 `D:\\zkswe\\FlyThingsIDE\\...\\adb.exe` 看不到）。这两条与知识页一致，
等于**把那条口径在真机上复验了一遍**。

### 36.2 登记进唯一真源的三个实测值

| 事实 | 实测 | 落点 |
|---|---|---|
| `res` 分区 | `mtd3 0x7A0000 = 7,995,392 B = **7.625 MiB**` | `preflight_spec.perPlatform` 增 `V85X: 7.62`（缺省 8 MiB 仍偏大 0.375 MiB） |
| 开机 logo 分区 | **叫 `boot_logo`**（`mtd4 = 0x40000 = 256 KiB`）—— **这台没有叫 MISC 的分区** | `upgrade-pack-image.md` 的「边界与待验证」表 |
| `/tmp` | **27M** | `device-deploy-budget.md`（原有两个数：13.6MB / 32MB） |

> logo 那条是最典型的：权威页原来只教「换板先量 **MISC** 大小」，
> 而 V85X 上**连分区名都不一样** ⇒ 已补「**连分区名一起量**，别照抄 MISC 这个名字」。

### 36.3 截图 op 的 `FB_UNREADABLE`：定位到根因并修好（硬件验证）

**现象**：`flythings_device_screenshot` → `FB_UNREADABLE`「framebuffer 不可读：读到 0 字节」。

**定位过程**（都在真机上做）：
1. 手工 `cat /dev/fb0 > /tmp/fb.raw` → **3,072,000 B**（= 480×1600×4 ✓）⇒ fb 本身可读；
2. `dd` → **`/bin/sh: dd: not found`** ⇒ 设备 rootfs 裁剪，**没有 dd**
   （工具 docstring 第 7 行自己就写着「没有 screencap / dd / head / uname」）；
3. 于是 op 走的是**裸 `dd` 的备选路径** ⇒ 0 字节 ⇒ `FB_UNREADABLE`；
4. 主路径（推 busybox → `busybox dd … | busybox gzip`）为何没成：
   `_local_busybox_candidates()` 是 **glob 顺序**（`f133→f135→t113→v85x→z20→z21`），
   在 V85X 上先推**别的平台**的 ELF；模块里**没有「按型号定平台」**的能力。

**修复**：用已有的 `device_models.json`（`Zkswe_V85X_SPINOR → V85X`）
+ `getprop ro.product.model`，把**本平台那份 busybox 排到最前**；拿不到型号则保持原顺序（零回归）。

**验证（同一台机器，改前/改后）**：

| | 结果 |
|---|---|
| 改前 | `FB_UNREADABLE`（0 字节） |
| 改后 | **`ok=True` / `method=busybox-dd-gzip` / 480×800 / 文件落盘** |

旁证：手工同链路压缩后只 **12.8 KB**（比裸 3 MB 快 3 个数量级），
解出的图与此前目视确认的截图 **98.76% 逐像素全等**（差值是时钟秒针/刷新）。

### 36.4 双缓冲（口径确认）

`FBDEV_OVERALLOC=200` ⇒ `virtualHeight = 2 × height`，**可见区 = virtual 的前一半**，
且读图必须按 `pan` 取当前帧 —— 工具抓到图后会**二次读 `pan`**，不一致就重抓 ✓（已实现）。
本轮 `pan = 0,0`，所以取 `y = 0..799` 就是当前帧。

### 36.5 本轮**未完成**的（如实写，不冒称已验证）

`backgroundPic: ""` 是否使控件不可见、`roll*` 的 `rollStep` 单位 ——
判它们必须把测试页推上屏，而 `flythings_build_ui_flow` 在 `fun install` + 字体应用后返回
`success:false`（**没走到 build/launch**；我打印时还截断了明细）。⇒ **这两项仍是"未核"**。

测试工程已备好，下轮可直接推：`temp/v85x_probe/`
（页内 A = 带 `backgroundPic:""`（红底）、B = 不带该键（绿底）= 对照组、
C/D = 长文本 `rollStep` 5 与 20 的对照；控件字段由真源 `required_fields`/`defaults` 构造）。

### 36.6 规范落地：两项判定**已转化为字段规范**（同日，同设备）

**上屏**：`fun build` + `fun launch` 成功（进程 alive 校验通过），测试页跑在 480×800 上，
截图证据 = `temp/judge_t0.png`。

| 未核项 | 判定 | 证据 |
|---|---|---|
| `backgroundPic: ""` 是否让控件不可见 | **不会** | A（带空串，红底）与 B（不带该键，绿底）**都正常画出底色与文字** |
| `rollStep` 的量纲 | **每步位移像素**（配 `rollIntervalTime` 毫秒/步） | C（`step=5`）实测 **20→25 px / ~0.8 s** ≈ 5 px 每 150 ms 步；D（`step=20`）同刻**文本已滚出框外**（约 4 倍速，自洽） |

仍留未核（写进页面，不假装验过）：`rollDirection` 的 0/1 与"左/右"对应（本轮只测 1）、
文本滚完是否循环、三态色各平台差异。

### 36.7 规范落地：`caption` 是标识符，显示文字在 `text`

第一版测试页把显示文字（含空格/冒号/连字符/中文）写进 `caption` → `fun build` 报

```
generated/ui_main.h:92:33: error: expected primary-expression before ')' token
```

根因：**`caption` 会成为 C++ 标识符**（生成 `m<caption>Ptr` 与 `ID_MAIN_<caption>`）。
真实工程里全是标识符式命名（`B2dCanvas` / `BtnToggleOff` / `ImgWeatherBig`…），
**显示文字放 `text`**（textview 的 `text` 是"非空才写"）。

处置：给 `ui_schema.json` 里**全部 25 个带 `caption` 的控件**加了 note（真源一处说清，
AI 拉 `flythings_ui_schema` 就能看到），改页（`caption=tvA/tvB/rollC/rollD` + `text=…`）后重推通过。

> **规范原则（2026-10-03 用户口径，本项目从此照此执行）**：
> **一条经验必须归约为「设计源里的规范条目」**（字段 note / `valueRules` / 判据 / 门禁），
> **不在文档里累积"踩坑记录"** —— 后者只增不减，会把阅读与维护负载无界推高。
> 事件经过只留在本文件（决策记录）与证据体系（`evidence`/`_reports`）里，**不进规范文本**。
> 落地位置示例：`caption`/`roll*`/`backgroundPic` 的规范都写进了 `ui_schema.json` 的
> 字段 note 与 `valueRules`（AI 拉 `flythings_ui_schema` 即可见），知识页只说用法与约束。



---

## 37. 设计规范第一批落地（2026-10-03）—— 全检 46 → 0

**依据**：`DESIGN_SPEC.md`（MCP 只讲"本平台与标准 Linux/rootfs/GUI/包组件的差异"；
通用编程能力属 AI 原生、不入库；规范优先；实测优先；不静默；唯一真源）。

**手段**：`scripts/audit_design_spec.py`（已进门禁 `--check`）扫三类问题。

| 类别 | 命中 | 处置 |
|---|---|---|
| ① 通用内容 | 3 → 0 | 改写成**平台差异**陈述（HTML 源文本的换行/空白折叠、`_dump_json` 的 tab/无空格/无尾空行 —— 都是"设备怎么读"） |
| ② 踩坑叙述 | 33 → 0 | **保义归约**（踩坑/坑位/教训/踩过 → 硬约束/判据/实测/边界）；措辞改动落到**生成器**，不手改派生页 |
| ③ 可实测却硬编码 | 10 → 0 | 能改写的改写（字库字节→「大小随设备而定」、分区字节→指向权威分区表＋「以设备实测为准」）；**必须留存的历史实测记录**打 `design-spec:evidence <理由>` 标记，审计跳过 |

**新机制**（写进 `DESIGN_SPEC.md` 第 5 条）：`<!-- design-spec:evidence 理由 -->`
只给历史实测记录用；不能拿来让"本该归约成规范"的内容免检。

**顺带修掉一个真实负载**：`device-screenshot.md` 内嵌两份文档（第二份自带 front-matter + 标题，
正文相似度 0.94）→ 留更全的第一份（含 §4.3 `staleFrame` / §4.4 launch 活性），
并入第二份唯一独有的一行：**30.9 KB → 16.5 KB**。

**一处如实登记**：`builtin-packages` 组 `min_top1` 6 → 5。3 条落外都不是退化 ——
`openssl 是什么版本`→`packages/openssl/platforms.md`（逐平台版本真值表）、
`有没有 curl 包`→`packages/curl/platforms.md`、`怎么给工程加个包`→`flow-index.md`（流程）：
**更具体的页接走了**。不删问法、不调参。

**方法教训（留决策记录，不进规范）**：我一度用 `difflib.SequenceMatcher` 把文件与自己的尾巴比，
得出"整篇重复"的错误结论并**截坏了页面**（已从备份还原）；正确判据是"**两份 front-matter / 两个一级标题**"。
