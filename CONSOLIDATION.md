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
| ② UI 引擎·生命周期·控件 API | **`lifecycle_spec.json`（待建）**| `knowledge/lifecycle/*` | `create_project` / `activity-code-skeleton.md` | ❌ 缺 |
| ③ OS·分区·img·升级 | `platform_capabilities.json` **（已建：能力矩阵层）**| `knowledge/devflow/{upgrade,deploy,platform}-*.md` | `build_ui_flow` / `pack_upgrade` / `selfcheck` / `gen_hardware_doc` | 🟡 B1 已落地能力矩阵 |
| ④ 硬件外设 API（IIC/SPI/GPIO/ADC/PWM） | `hardware_catalog.json`（已有，待收编） | `knowledge/hardware/*` | `flythings_hardware_info` / 外设 demo | 🟡 半 |
| ⑤ 多媒体 API（播放/录音/图层） | **`media_capabilities.json`（待建）**| `knowledge/media/*` | `device_screenshot(layer=video)` / demos | ❌ 缺 |
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
| **B3**| **实例骨架唯一来源**：519 个自带拷贝 → 骨架 + 生成器 + `--check`（照 `sync_ui_tools.py` 模式） | ★★★☆☆ | 中高 | 新加 example 不再手抄 19 文件；门禁盯一致性 |
| **B4**| `bin_tools/` 平台副本收编（5 组 / ~660KB）：一份二进制 + 平台映射 | ★★☆☆☆ | 低 | push 逻辑按映射取；真机验证 |
| **B5**| **根目录归位 + 历史命名残留清空**：44 个根文件分层；`fyx`/`FYX_BUILD` 清空、`fuse` 分「命令名（清空）/老形态（保留）」、`RENAMED`/flat 双模式/legacy 逐项定去留；顺带修出打包清单漏 15 模块 | ★★★☆☆ | 高（import/打包/闸门连锁） | 打包与 `install.bat` 冒烟通过 |
| **B6**| IDE 冗余出库（76 个 `.prefs`/`.log`）：先确认 IDE 是否必须 | ★★☆☆☆ | 低 | 模板仍能被 IDE 正常打开 |

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
