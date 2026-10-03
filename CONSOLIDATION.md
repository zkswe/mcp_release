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
