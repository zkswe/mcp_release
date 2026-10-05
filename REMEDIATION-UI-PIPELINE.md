# 界面产物管线整改方案（口径 · 编译器式验收 · 闸门）

> 立项：2026-10-05（需求方拍板：**去掉「HTML 是唯一手写源」**、**确认稿硬闸门要上**、
> **要一个像 C 编译一样验收 json 合理性的工具**，用于减少上机来回掰扯）。
> 定位：**工作分解与执行台账**，不是规范。规范真源仍是 `DESIGN_SPEC.md`、`op_spec.json`、
> `knowledge/`（本文件里任何与它们冲突的表述，以它们为准）。
> 数字口径：本文件**不写门禁条数/用例条数**（那两个数只由
> `python scripts/check_consistency.py --with-tests` 与 `python scripts/check_retrieval.py` 打印）。

---

## 0. 目标口径（一句话）

> **`ui_schema.json` 是唯一产物规范，`ui/*.json` 是唯一事实源；手写入口不排他
> （HTML 原型 / 块库 spec / LVGL·Qt·QML·Android XML·Vue 迁移），但任何入口的产物
> 必须由共享发射链产出，或经编译式验收（`ui_compile`）无 fatal/error 才算成立。**

排他性从**输入端**移到**输出端**。HTML 保留两个角色：① 缺省前端（需求→线框/风格稿，客户确认载体）；
② 确认稿渲染（`json2html` / `ui_preview(for_customer=True)`）；**去掉的是「唯一」**，不是 HTML。

## 1. 现状证据（为什么要改）

| 事实 | 出处 |
|---|---|
| 「从零」流程已经**不过 HTML**：`idea-to-app` 走 `write-ui-json` + op `flythings_ui_schema` | `flow_spec.json` |
| 但知识页仍写「HTML 是**唯一手写源**」 | `knowledge/devflow/platform-translate.md` §2 |
| 而同一份知识又写「手写 HTML 原型等于**第二份真相**、json 才是唯一真相」 | `knowledge/devflow/ui-layout-verify.md` §1 |
| 第二个作者入口已存在（块库 `spec.json` → json），且自认 id 分区「与 html2json 同源，只有例外」 | `templates/ui_blocks/compose.py` |
| 生产者 4 个（html2json / translate_ui / compose / 手工），公共映射表只有 1 个消费者，发射层约 3 套 | `ui_tools/html2json.py`、`translate_tools.py`、`mcp_control_map.json` |
| 映射层在 html2json 里只占约 40 行（`CLASS_MAP`/`ID_BASE`/`AUTO_NAME`/`ALIGN`）≈ 1.1% —— **映射表是索引，不是引擎** | `ui_tools/html2json.py` |
| 字段口径已漂移一例：`textview.alignment` 注册表 default 36，发射层写 0，且声称的「差异清单」在注册表里**不存在** | `ui_tools/ui_schema.json`、`translate_tools.py` |
| `json2img` 已是「无设备时唯一的视觉验收手段」，且已有 `--json-report` + `unsupported` 记账 | `tests/test_json2img_engine_model.py`、`ui_tools/json2img.py`、`kb_tools.py` |

## 2. 判据分档（判定谁说了算）

| 档 | 手段 | 强度 | 用途 |
|---|---|---|---|
| **① 编译式验收** | `ui_compile`（json 静态诊断：类型/必填/语义/引用） | **硬判据**（可判红、exit code、进闸门） | 落盘前 / 上机前，把"能不能加载、字段对不对"一次判完 |
| **② 离线渲染判定** | `json2img` A/B 像素 diff（同一渲染器） | **硬判据**（确定性） | 跨源/跨入口等价、字段与几何回归 |
| **③ 离线近似** | json 渲染 vs 源参考图（浏览器稿等） | 松判据（人工） | 「像不像源设计」 |
| **④ 真机真相** | `device_screenshot` + `ui_visual(action="diff")` | 最终真相 | 出货验收 |

`json2img` 是模拟层（字体度量/9-patch/换行/裁剪字库与设备有差）→ 做**归因判定**够硬，替代真机不够。

**差异归因三分**（只有第 ③ 类才动 `json2img`）：① 前端丢语义 → 改前端/登记 `downgrades`；
② 发射层字段或换算错 → 改 fill/换算规则；③ 渲染器不覆盖或语义错 → 才改 `json2img`，
且必须同时更新 `renderContract` 行或 `unsupported` 清单 + 更基线 + 真机对齐证据。
**判据可以改，但只能按规格改，不能按结果改**（`DESIGN_SPEC.md` 第 1.1/1.2 条）。

## 3. 模块 I/O 契约（各司其职，各自保证输入输出）

| 模块 | 输入契约 | 输出契约 | 自检判据（红了就是它的错） | 禁止 |
|---|---|---|---|---|
| **A 前端** | 源文件/源码 | **IR** | 覆盖率报告（`unrecognized`/`downgrades` 逐条）+ IR 校验 | ❌ 不许直接出 json、不许 import PIL |
| **B 映射** | 源控件名 | target / level / 片段 / notes | 条目完整性 + 片段由 schema 派生（`gen_control_map_snippets.py --check`）+ L3 必给 ref | ❌ 不写散文映射表 |
| **C 发射** | IR | `ui/*.json` | `ui_compile` 无 fatal/error + `check_all` 关键项 0 FAIL | ❌ 不解析源语言、不画图 |
| **D 出图** | 效果描述 | PNG（图 == 盒、α=覆盖率） | `renderContract` 十条 + 尺寸/α 断言 + 黄金样例 | ❌ 调阈值/档位修视觉问题 |
| **E 渲染判定** | json + 资源 + 字体 | PNG + `unsupported[]` + 机读报告 | 确定性（同输入同 md5）+ 覆盖矩阵 + **盲区不许判通过** | ❌ 不写业务代码 |
| **F 验收** | 设备 | 截图 + diff | 真机像素 | ❌ 用离线渲染替代真机结论 |

## 4. 任务分解（WS/T）

> 状态：⬜ 未开始 / 🟡 进行中 / ✅ 完成。每个任务**必须有可判红判据**，否则不许标完成。

### WS-0 口径与登记（便宜、先做，防复发）

| ID | 任务 | 交付物 | 判据 | 状态 |
|---|---|---|---|---|
| T0.1 | 口径单出处：把三档判据/入口分级/模块契约写成唯一规范页，其它页改为引用 | `knowledge/devflow/ui-pipeline-spec.md`；`platform-translate.md` §2、`ftu-json-pipeline.md` §1/§3、`ui-layout-verify.md` §1、`prototype-flow.md` 改为指针 | 检索问法命中新页；`check_doc_refs` PASS | ✅ 2026-10-05（新页已建；4 处旧口径改为指针；`components/ui_v1/platforms.md` 最后一处「唯一手写源」也已改净。**行数不写**：它会随每次编辑漂，看文件本身） |
| T0.2 | 废止短语黑名单：`唯一手写源` / `HTML 是唯一源` 等出现即判红 | `tests/test_ui_pipeline_spec.py` | 断言当前 0 命中；注入旧句必须变红（自证） | ✅ 2026-10-05（17 项 OK；全仓 0 命中，白名单只留 CHANGELOG/VERSION_HISTORY/整改方案自身/测试自身/`tests/` 负例） |
| T0.3 | 入口登记真源 + 派生文档 + `--check` 进闸门 | `ui_entrypoints.json`、`scripts/gen_entrypoints_doc.py`、`knowledge/devflow/ui-entrypoints.md` | `gen_entrypoints_doc.py --check` rc=0；smoke/一致性挂上 | ✅ 2026-10-05（10 入口 = 5 active + 5 planned；派生页 `--check` PASS；已挂进 `check_consistency.stage_delegated`） |
| T0.4 | 检索回归：Vue / WXML / QML / 不写 HTML 直出 json 四类问法 | `scripts/retrieval_groups/ui-pipeline-spec.json` | `check_retrieval.py` PASS | ✅ 2026-10-05（新页 9 条问法建组，**按实测**登记 `min_top1=2 / max_miss=2`；`check_retrieval.py` → `[PASS] 检索回归全绿（100 组 / 950 问法，top-1 721/950 = 75.9% ≥ 72%）`，未登记问法的文档 0 篇） |

### WS-1 编译器式验收（核心）

| ID | 任务 | 交付物 | 判据 | 状态 |
|---|---|---|---|---|
| T1.1 | `ui_compile`：parse → 类型 → 必填/全集 → 语义 → 引用/资产 → 诊断（规则 id + 路径 + 修法）+ exit code + `--json` | `ui_tools/ui_compile.py` | 对一个**合法**样例 rc=0；六类坏样例逐类 rc≠0 且报对规则 id | ✅ 2026-10-05（**22 条规则**：PARSE001/002、PAGE001、SCH001-004、NAME001/002、ID001/002、**TREE001-004**、ROOT001、CHAR001、ASSET001/002、GEOM001 + 附加 RES001/SCAN001；**2026-10-05 检讨重测**：`templates/` 全跑 —— `HelloWord_*` 7 个工程 `fatal=0 error=0`；
`DemoControls_V85X` 也 `fatal=0 error=0`（8 页 / 71 控件）。原写"23 页实跑 22 ok / 1 红"不可复现，
当时的"1 红"是**未接入导航的测试页** `ui/maintest.json`（9 条 SCH002），该页已按需求方口径删除，见下）。**2026-10-05 追加 TREE002/003/004**：结构容器平铺子控件 / 容器 `only` 子类型 / 数组子结构归属 —— 与 `check_all` #2 **同一真源**（`ui_schema.json#controls[].children`），修的是「同一份 json 一个红一个绿」的假绿（见 `tests/test_layer_rules.py`） |
| T1.2 | 库化 API：`compile_json(...) -> report`（生成器出口可直接调） | 同上 | `tests/test_ui_compile.py` 覆盖 API | ✅ 2026-10-05（`compile_json` / `compile_project`；**57** 项用例 OK（2026-10-05 检讨按实测订正：原写 53），坏例一律「错法报该规则号 → 改回必须转绿」自证） |
| T1.3 | 出口闸门：产 json 的路径落盘前调 T1.2；fatal/error → 拒绝落盘（`success:false` + 诊断）；`allow_unvalidated=True` 才放行且带标记 | `kb_tools.py`、`ui_edit_apply.py`、`project_tools.py` | 「坏产物被拒 / 好产物放行 / override 带标记」三向用例 | ✅ 2026-10-05（**两批全落**）：① 到设备的路 —— `fui_pack`/`build_ui_flow` 拦（`UI_JSON_INVALID`）；② 生成/落盘路 —— `html_to_json`（生成期写临时 json、图片照常落项目、不合格**撤回**）、`translate_ui`（写前备份、不合格**还原/删除**）、`ui_visual(edit_apply)`（不合格从 `.bak` **回滚**并重 pack）。fatal 一律拦；error 默认只记 `uiCheck.errorsNotBlocking`，`strict_ui=True` 加严。`tests/test_ui_compile_gate_paths.py` 10 项 OK；`test_translate_ui` / `test_html2json_*` 全绿 |
| T1.4 | 去重：`check_all` 的 json 侧检查项改为调用 T1.2（唯一实现，不新增第三份） | `ui_tools/check_all.py` | check_all 行为不变（对既有样例结论一致） | 🟡 2026-10-05 部分完成：**判据数据已同源**（层级判据一律派生自 `ui_schema.json#controls[].children`，check_all #2 去掉四份硬编码表、ui_compile 有了 TREE001-004）；**代码尚未合并**（两份实现并存，ui_compile 报告 `delegated` 如实登记）。check_all 行为等价性有实测证据：`_layer_problems` 新旧实现跑遍全仓 93 份页面 json **逐条文本完全一致** |
| T1.5 | op 面：**并入既有 `flythings_validate_project`**（新增按需参数 `ui_check`，诊断进 `errors`/`warnings`），**不新增 op** | `kb_tools.py`、`op_spec.json` | `validate_project` 既有行为不变；带 fatal 的 json → errors 命中 | ✅ 2026-10-05（`ui_check='auto'` 默认开；fatal/error → `errors[]`，`type=ui_compile_<规则号>`，带修法 hint；warn → `warnings[]`；工具缺失时登记 `ui_check_unavailable`）。**决策**：常驻预算 5989/6000，不新增 op；合成验收改走 `validate_project` 的短硬规则（~55 字符） |
| T1.6 | 自证用例：thumb 写字符串 / 缺必填 / 图≠盒 / caption 重复 / id 撞段 / 子盒写成标量 | `tests/test_ui_compile.py` | 每条坏例必须判红；修好必须转绿 | ⬜ |

### WS-2 判定基准（json2img）

| ID | 任务 | 交付物 | 判据 | 状态 |
|---|---|---|---|---|
| T2.1 | 覆盖矩阵：`renderContract` 十条 × 实现状态（implemented / approximate / unsupported）派生 + `--check` | `ui_tools/json2img.py`（`--coverage`）、矩阵数据 | `--coverage --check` rc=0 | ✅ 2026-10-05（行集合真源 = `ui_schema.json#renderContract.rows`，矩阵不重抄 id；实测 **implemented 4 / approximate 4 / unsupported 2**，blindSpot 2 条 = `stroke-aa`/`family-consistency`） |
| T2.2 | 盲区判红：判定模式下命中「不允许的盲区」→ FAIL（白名单登记制） | 同上 + `--judge`（默认关） | 盲区样例判红；已登记白名单放行 | ✅ 2026-10-05（未豁免盲区 → `blindSpots[]` + rc=1；豁免表 `reason` 必填、支持 `allow:false` 显式拒绝；**默认行为逐字节一致**：8 个真工程页 stdout/PNG md5/json-report md5 全同） |
| T2.3 | 确定性基线：同输入同 md5；基线绑定 `json2img.__version__` | `tests/test_json2img_determinism.py` | 跑两次 md5 相同；改渲染器版本 → 基线报「需同批更新」 | ✅ 2026-10-05（进程内 + 跨进程/换 `PYTHONHASHSEED` 均同字节；`EXPECTED_RENDERER_VERSION='0.1.0'` 绑定） |
| T2.4 | 区域级归因 diff：按控件盒/caption 报「哪块差多少」并归因到 A/C/E 层 | `ui_tools/region_attrib.py`（复用 `wysiwyg_diff.walk/biggest_block`）+ `render_check` 接线 | 差异样例能指出具体控件与责任层 | ✅ 2026-10-05（见下方「区域级层归因」） |
| T2.5 | 副本一致性：`sync_ui_tools.py --check` 留在闸门 + 版本一致性断言 | `scripts/smoke.py`（已有）/ 用例 | 故意改副本 → 判红 | ⬜ |

### WS-3 确认稿硬闸门（需求方已拍板）

| ID | 任务 | 交付物 | 判据 | 状态 |
|---|---|---|---|---|
| T3.1 | `_confirm_gate` 升级为硬闸门：pack / edit_apply / build_ui_flow 前必须有 `for_customer` 确认稿，且**比 json 新**；否则拒绝（带 `force_confirm`） | `kb_tools.py`、`project_tools.py` | 「无稿拒 / 过期拒 / 新稿放行 / force 放行且带标记」四向用例 | ✅ 2026-10-05（`tests/test_confirm_gate.py` 14 项 OK；错误码 `CONFIRM_REQUIRED` 已登记） |
| T3.2 | 确认稿指纹：确认稿记录 json 的内容 sha256（副文件 `<稿>.fingerprint.json`） | `kb_tools.py`（出稿侧 + 闸门侧） | 指纹不匹配 → 判红（mtime 更新也救不了） | ✅ 2026-10-05（`write_confirm_fingerprint` / 闸门指纹核对；历史稿无指纹按 `confirmLegacy` 如实标注） |
| T3.3 | 知识同步：把硬闸门写进流程页（新项目硬、改版可软） | `prototype-flow.md`、`ui-layout-verify.md` §0 | 检索命中；无旧口径残留 | ✅ 2026-10-05（`ui-layout-verify.md` §0 由「只提醒」改为硬闸门五条：拦截点/指纹/历史稿/`force_confirm`/副文件不许放 `ui/` 下；`prototype-flow.md` 落地工具节补两道闸门与跳过开关） |

### WS-4 视觉口径与出图（防多源各画各的）

| ID | 任务 | 交付物 | 判据 | 状态 |
|---|---|---|---|---|
| T4.1 | `renderContract` 覆盖声明：保真实现文件用**数据**声明「实现哪些 row」，门禁校验与代码事实一致 | `ui_tools/render_contract_coverage.json` + `scripts/check_render_contract_coverage.py`（已挂 `check_consistency`） | 删掉某 row 的声明 → 判红 | ✅ 2026-10-05（4 个实现文件 × 10 条 row：`gen_res` implements 3 / partial 4 / delegated 2 / n-a 1；`html2json` 5/1/3/1；`check_all` 5/5；`json2img` 指向它自己的细矩阵并校验两边行集合一致。**evidence 必须是文件里真实存在的函数/常量名（AST 校验）** —— 函数被删/改名 → 门禁当场红；`tests/test_render_contract_coverage.py` 8 项 OK，含 6 条变异自证） |
| T4.2 | 出图白名单扫描：生产者文件不许**新增**"自己画形状"的 PIL 原语；只拦新增、存量进基线 | `scripts/lint_draw_sites.py` + `scripts/draw_sites_baseline.txt` / `draw_sites_whitelist.txt`（照 `scripts/lint_silent_except.py` 模式） | 注入一行 `Image.new(...)` → 判红；命中下降提示可下调基线 | ✅ 2026-10-05（生产者 = `ui_tools/html2json.py` hits=15 / `templates/ui_blocks/compose.py` hits=17 / `translate_tools.py` hits=0；14 项用例 OK，含"别名解析坏掉 → 15→4 处漏报"变异自证；已挂进 `smoke.py` 第 9b 项） |
| T4.3 | 跨源 A/B 黄金样例（先 HTML vs LVGL，同一视觉目标） | `tests/fixtures/` + 用例 | 两源产物经同一发射链后 `json2img` diff 在阈值内，差异逐条登记 | ⬜ |
| T4.4 | **控件 id 段口径收口**（用户点名：在制品 id 重复 = AI 写的，且"之前的设计确实分了段"） | `ui_tools/html2json.py`（`ID_BASE`）、`knowledge/uicontrols/layout-audit.md` §3、`tests/test_id_segments.py` | 段位表两份一致 + 硬约束带不误收 + `templates/**` 实际 id 在段内 | ✅ 2026-10-05（见下方「ID 分区收口」） |
| T4.5 | **json2img 颜色语义修正**（用户点名：修 `color_rgba` 的负数 bug） | `ui_tools/json2img.py`（0.1.0 → 0.1.1）、`tests/test_json2img_color_semantics.py` | `0` = 不透明黑、`-1` = 不填充、其它负数按 `0xAARRGGBB`；基线版本同批更新 | ✅ 2026-10-05（见下方「颜色语义」） |

### WS-5 发射层与映射统一（中长线）

| ID | 任务 | 交付物 | 判据 | 状态 |
|---|---|---|---|---|
| T5.1 | 发射口径对账（`ui_emit` vs `html2json` 实际产物） | `ui_tools/emit_conformance.json` + `scripts/gen_emit_conformance.py --check`（已进一致性门禁） | 差异逐条有归属（编码形态 / 待核 / 真缺陷） | ✅ 2026-10-05（快照 5 类；抓到 1 处真缺陷见下） |
| T5.2 | 抽唯一发射层：`ui_tools/ui_emit.py`（由 `translate_tools._SCHEMA_FILL`/`_schema_complete` **整块搬出**），`translate_tools` 只留别名 | 新模块 + `translate_tools.py` | 接入前后产物**逐字节一致** | ✅ 2026-10-05（3 个 LVGL 夹具 md5 全同；`test_translate_ui` 20 项未改仍绿） |
| T5.3 | `sources.html` 进映射表（`CLASS_MAP` 搬表，片段由 schema 派生） | `mcp_control_map.json`、`html2json.py`、`gen_control_map_snippets.py` | `test_control_map.py` PASS + 对账用例 | ⬜ |
| T5.5 | **`html2json` 的控件写入接入共享发射层**（只补注册表必填键，不注入可选键） | `ui_tools/ui_emit.py`（`fill_required`）、`ui_tools/html2json.py`（`_Ctx.add` 唯一收敛点） | 对账快照里 `seekbar` 缺必填 2 → 0，且 html2json 既有 61 项用例不改仍绿 | ✅ 2026-10-05（见下方「html2json 接入共享发射层」） |
| T5.6 | **`templates/ui_blocks/compose.py` 接入共享发射层**（`serialize()` 唯一收敛点）+ 第三个发射实现纳入对账 | `compose.py`、`scripts/gen_emit_conformance.py`（compose 段） | 对账覆盖 compose 251 个控件：缺必填 0 / 未声明键 0 | ✅ 2026-10-05 |
| T5.4 | QML / Qt `.ui` / Android XML / Vue 前端只写 A 层 | 各前端 + `ui_entrypoints.json` 登记 | 至少一条端到端样例经同一发射链 + `ui_compile` 无 error | ⬜ |

## 5. 执行顺序与并行

- **P0（先做）**：T1.1/T1.2（编译器核心，T1.3~T1.6 与 WS-3 都依赖它）→ T3.1/T3.2（确认稿硬闸门）→
  T0.1/T0.2/T0.3（口径与登记，便宜且防复发）。
- **P1**：T1.3~T1.6、T2.1~T2.3、T4.1/T4.2。
- **P2**：T2.4、T4.3、T5.1~T5.3；T5.4 视排期。
- **互斥资源（同时只允许一个写者）**：`scripts/check_consistency.py`（门禁挂载）、`kb_tools.py`（op 面）、
  `ui_schema.json`（规范真源）、`ui_tools/gen_res.py`。其余文件可按任务分工并行。

## 6. 验收与门禁（每个任务收尾必跑）

```
python scripts/check_consistency.py --with-tests     # 必须 total=<N> fail=0 OK
python scripts/check_retrieval.py                    # 检索回归 PASS
```

派生文件重生成顺序：**索引类在前、`tools_manifest.json` 最后**。
新文件必须 `git add`（`stage_referenced_files_tracked` 只看 git 索引）。

## 7. 风险与回滚

| 风险 | 处置 |
|---|---|
| T1.3 出口闸门让**存量**工程 json 被拒 | 两档上线：先「警告不拒」（新生成路径严格、存量路径提示），再按实测收紧 |
| T3 硬闸门打断既有交付节奏 | 只对「新项目/新需求」硬；改版路径软提示；`override` 留痕可审计 |
| T5.2 抽发射层改动面大 | 先出对账表（T5.1），接入以「产物逐字节一致」为硬判据；不一致就回滚 |
| 口径改写导致检索漂移 | T0.4 问法组 + `check_retrieval.py` 进闸门 |
| 判定基准（json2img）被当结论用 | §2 三档判据写进规范页；真机仍为最终真相 |

## 8. 明确不做

- ❌ 不重写 `html2json` 的 CSS 引擎（它是资产：CSS 效果→图是迁移通路最缺的能力）；
- ❌ 不让 HTML 退化为"必须走"的中间层，也不让"手写 json"合法化到无校验；
- ❌ 不为统一而改动 `fun`/`fui` 工具链行为（那是厂家工具，本仓只调用）。

## 9. 执行记录

### 2026-10-05 · 检讨第二轮（需求方拍板三项，全部落地）

| 项 | 需求方口径 | 落地与实测 |
|---|---|---|
| `ui/maintest.json` 那页 | 「是我做的测试，可以删掉」 | 页面/json/ftu/logic/activity + IDE 构建残留（`Release/`）**全部删除**；模板回到 8 页 —— `ui_compile` **8 页 / 71 控件 / fatal=0 error=0** |
| 它为什么是 480×480 | 「`com.zksw.flythings.easyui.prefs` 的分辨率字段是 480×480，导致 IDE 新建页面自动匹配」 | 根因确认并修：`templates/DemoControls_V85X/.settings/com.zksw.flythings.easyui.prefs` → **`resolution=480x800`**（该值是工程 480×800 的真源；`HelloWord_V85X` 本身就是 480×480，**不动**）。README §1 加提醒（新建页前先看 prefs） |
| 进度条两张切图（450×34 药丸 vs 盒 448×32） | 「**重出**」 | 用 `ui_tools/gen_res.py` 的 `rounded_rect_cov(448, 32, 4, …)`（α=覆盖率口径）重出 `pb_track`/`pb_fill`，颜色沿用原图（36,48,74 / 77,166,255）；`check_all` 该项转 PASS → 模板 FAIL **4 项 → 1 项**（只剩跑马灯最小尺寸这一条设计意图） |
| `temp/` 与 README 的截图列 | 「temp 只是测试，可以全部删除」 | 模板 README 去掉「真机截图」列（指向 gitignored 的会话产物 = 指向不存在的文件），改为"要复现就照 §7 现场抓屏" |
| `.preview.html` / `.edit.html` 的语义 | 「preview 是需求确认稿，edit 是用户自己编辑坐标规格参数的在线编辑工具」 | 确认闸门的 `CONFIRM_DRAFT_SUFFIXES` = **(`.confirm.html`, `.preview.html`)** —— **`_edit/*.edit.html` 不再算确认稿**（拿工具当确认）；`ui-layout-verify.md` §0 写明口径；`tests/test_confirm_gate.py` 加 2 条用例（preview 算 / edit 不算），14 → 16 项 |

另：本文件 §1 表里 T1.1 的"1 红"已随上表一并订正（见该行）。


> ⚠️ **读法（2026-10-05 检讨补）**：下面每一节都是**当时那一次**的实测快照 —— 其中的
> 常驻字符数 / 门禁项数 / 用例数 / 检索命中率**都会随后续改动变**，别拿它们当"当前值"。
> **当前值只有两个出处**：`op_spec.json` 的 `budget.basis` / `budget.note`（由门禁对账），
> 以及 `python scripts/check_consistency.py --with-tests` 与 `python scripts/check_retrieval.py`
> 自己打印的行。本文件按 §0 的口径**不再新写**这四个数字；历史节里的旧数字**保留原样**（它们记录的是当时事实）。

## 附：op_spec.json 瘦身（2026-10-05，用户指示，A+B+C+E）

**用户问题**：「op_spec.json 瘦身有办法优化效率和 token 吗？」→ 先做只读体检（`temp/opspec_slim_audit.py`），
再按选定范围实施。**常驻面 = 每次会话都要付的 token**，所以只动它 + 明确登记的按需去重。

| 杠杆 | 做法 | 实测 |
|---|---|---|
| **A. triggers 移出常驻面** | `renderOrder` 由 `[summary, triggers, hardRules]` → `[summary, hardRules]`；**contractOrder/sections 同步重排**（triggers 落到 hardRules 之后，保证"契约以常驻面开头"这条不变量不破） | 路由**功能不变**（dispatcher `_find`、意图目录、manifest 都直接读 op_spec 字段）；常驻 −1348 |
| **B. `fragments` 共享片段表** | 新增顶层 `fragments` + loader 载入时**一次展开** `@platform-positioning`（原来同一句抄 4 份）；`validate()` 增两条：未定义片段引用 / 定义了没人用 | 展开后文本逐字不变，下游（含目录/manifest）看到的都是展开后文本 |
| **C. `seeAlso` 渲染去重** | `_field_text('seeAlso')` 过滤掉与 `docRef` 相同的路径（数据不动） | ⚠️ **实测更正**：`seeAlso` **不在 contractOrder 里**，所以这 1550 字符的节省**今天不会出现在契约文本里**（它只在"该字段被取用"时生效，例如返回体注入路径）。评估时的"省按需 1550"是**数据级**估算，不是渲染级 —— 已按实测改口径 |
| **E. rules/notes 内联路径指针化** | 扫出候选 1 条（`build_ui_flow`） | **保留不改**：该路径（`page-architecture-spec.md §1.5`）不在它的 seeAlso 里，删掉就是丢指针 |

**结果（门禁口径 = 所有 `flythings_*` docstring 之和，含分发器）**：
常驻 **5669 → 3921 / 6000（94.5% → 65.4%）**；单条最长 332 → **296**（`create_project`）；
`budget.perOpMax` 360 → **320**（按实测留 24 余量）；按需面最长不变（`get_package_api` 892/900）。
文件本体行数不写（会随编辑漂）→ 见 `git diff --stat`（去掉重复句子 + triggers 仍在数据里，仅不再渲染进常驻）。

**新增判据** `tests/test_op_spec_slim.py`（4 条）：triggers 不在常驻但仍在 op_spec / 契约以常驻面开头 /
片段展开且无未定义引用 / seeAlso 去重只在渲染层且数据未被改。
`tests/test_op_spec.py::test_tool_face_tiers` 与 `tests/test_op_sections.py` 的既有不变量在重排后仍绿（未放宽）。

（决策与实测）

### 2026-10-05 · compose 接入共享发射层 + 三方对账齐（T5.6）

**落点**：`compose.py` 的 `serialize()` 是唯一发射收敛点（每个节点经 `n.to_ctrl()` 出去）→ 与 html2json 同口径：
只补**注册表必填键**（`ui_emit.fill_required`），**不动**它自己的可选字段与取值（取值来自块 token 表 + 块参数，
与"发射层默认值"对比没有意义 → 对账只比**字段完整性**）。

**对账第三列**（`scripts/gen_emit_conformance.py` 新增 compose 段）：跑自带 example spec
（`complex_320x240` / `complex_1024x600`）到临时工程，**递归**统计全部控件 →
button 54 / edittext 2 / textview 175 / window 20（共 **251**）：**缺必填 0、未声明键 0**。
（扫描器第一版有**假阳性**：只扫顶层键漏掉嵌套控件、把子控件键 `button__1` 当成"未声明字段" → 已修。）

**至此三处发射实现全部走同一份补全实现**：`translate_tools`（整表 `schema_complete`）、`html2json`、`compose`
（后两者按需只补必填键）；差异仍在 `ui_tools/emit_conformance.json` 里逐条登记、由门禁对账。

### 2026-10-05 · `html2json` 接入共享发射层（T5.5，「共用一条发射链」再进一步）

**落点**：`html2json._Ctx.add()` 是**唯一收敛点**（每个控件都从这里进 json）→ 一处改动覆盖全部控件类型。

**过程（两次，第一次是错的，留档）**：
1. 先按"字段全集"接了 `ui_emit.schema_complete(normalize=False)` → **3 条既有用例当场红**，其中一条是
   **设备教训写成的判据**：「热区按钮带了底色 → 会盖住 RadButton 画布」——整表补全把前端**故意省略**的
   `bgColorTab` 补了回来（另外两条钉的是 html2json 的单槽 `colorTab` 形态）。
2. 改成 **`ui_emit.fill_required()`：只补注册表必填键**（值取发射层默认表；表里没有的键不猜，
   返回未补清单并进 `warnings`）。前端有意省略的**可选字段一律不碰**。

**实测结果**：对账快照 `seekbar` 缺必填 **2 → 0**（`backgroundPic`/`progressPic`，正是 T5.1 抓到的真缺口）；
`html2json` 既有 **61 项用例不改全绿**；新增 3 条判据（必填键来自共享层 / 可选键不被注入 / 源码必须调用共享层）。

**教训（已写进代码注释）**：「共用一条发射链」不等于"所有前端输出都长一样"——
**必填键的完整性**可以统一，**可选字段的取舍**属于前端的有意编码（有设备后果），
混在一起改会把别人的现场教训推翻。差异继续留在 `ui_tools/emit_conformance.json` 里逐条登记。

### 2026-10-05 · 发射链收口（T5.1 + T5.2，目标项 (1) 的实体部分）

**T5.2 · 唯一发射层**：`ui_tools/ui_emit.py`（`DEFAULT_BY_TYPE` / `KEY_ORDER` / `color_tab` / `tab5` /
`schema_complete` / `new_control`）。`translate_tools.py` 改成**别名**（`_SCHEMA_FILL = _emit.DEFAULT_BY_TYPE`
——`test_emit_conformance` 断言二者是**同一对象**，不是复制），其余 800 行调用点一行未动。
**证据（逐字节）**：`temp/ab_emit.py` 把 `git show HEAD:translate_tools.py` 放进临时沙箱跑旧版，
与新版对同一批 LVGL 夹具（basic / buttons / gauges）出 json → **3/3 md5 全同**。

**T5.1 · 对账快照**：`ui_tools/emit_conformance.json` = `ui_emit` 默认值与 `html2json` 实际产物的差异登记，
校验器 `scripts/gen_emit_conformance.py --check`（已挂 `check_consistency`）。抓到 **1 处真缺陷 + 4 处待核**：

| 类型 | 差异 | 归属 |
|---|---|---|
| `imageanim` | 发射层**漏必填 `playFile`** | **真缺陷**（用例 `test_emit_layer_covers_required_keys` 抓的）→ 已补 `''`（空=无动图，非挂死路径） |
| `seekbar` | `html2json` 产物**缺 2 个必填键**（`backgroundPic`/`progressPic`） | 真缺口，已登记 → 未修前由 `ui_compile` 报 SCH002（默认不阻断） |
| 全类型 | `alignment`：html2json 36/37 vs 发射层 0/5 | **编码口径**（5≡37 见于注册表；0 与 36 的等价性**未实测**）→ 登记待真机核 |
| 全类型 | `colorTab`/`bgColorTab`：单槽 vs 五槽 | 编码形态（引擎按缺省补，语义等价） |
| `edittext`/`seekbar` | `hintTextColor` 0 vs 0x808080；`touchable` False vs True | 默认值口径不同 → 登记待核（滑条不可触摸=点不动，**倾向发射层对**） |

**同轮收口 · 常驻预算事故（外部写入，非本批）**：`git diff` 显示并发写者给 `flythings_gen_logic_stub`
加了 2 条 hardRules（242 字符）+ 扩写 summary/triggers → 单条 **436 > 360**、常驻合计 **6300 > 6000**。
按本仓分层口径处置（**信息一条不删，只换层**）：两条细则搬进按需面 `rules`、常驻留压缩版；
另把 **5 处重复**的「平台定位」常驻规则（691 字符）统一成一句 75 字符（判据要点不变 + 真源指针）。
结果：**常驻合计 5972/6000、单条无超限**，并刷新 `budget.basis`/`budget.note` 的实测数字。
（提示：本轮检测到**并发写者**在改 `op_spec.json` / `kb_tools.py` / `knowledge/devflow/symptom-index.md`；
凡"摘要与 docstring 不一致"的红，一律以 `op_spec.json` 为真源跑 `gen_op_docs.py` 重生成。）

### 2026-10-05 · 区域级层归因（T2.4，目标项 (4) 收口）

`wysiwyg_diff` 原本只回答「哪块不一样」；本批补上「**该谁修**」——
新模块 `ui_tools/region_attrib.py`（复用 `wysiwyg_diff.walk()` / `biggest_block()`，几何与连通块只有一份实现）：

| 层 | 判据（离线可得的三类证据） |
|---|---|
| `C/EMIT-FIELDS` | 该控件在 `ui_compile` 下有 fatal/error（字段/类型/必填） |
| `C/ASSET-GEOMETRY` | **按这一个控件**核对「图 == 盒」（复用 `check_all._ctrl_pic_refs/_pic_path`）；或缺图 |
| `E/RENDERER-BLINDSPOT` | 命中 json2img 的 `unsupported[]`（`<type>/<caption>` 或裸 caption）→ 离线判不了 |
| `E/FONT-METRICS` | 文字盒内差异 / 运行期文字盒（字形栅格化是模拟层，与 wysiwyg_diff B 段同口径） |
| `A/FRONTEND-REPORT` | 可选：前端返回体里 `warnings/downgrades/unrecognized` 按 caption 对上 |
| `U/UNATTRIBUTED` | 以上都不命中 → **不猜**，给 box/caption/量值交人工 |

汇总口径：`eLayerSharePct`（差异像素里有多少落在 E 层 = "离线判不了"的量化）、`attributedPct`、
`pass`（有 C 层或未归因的**超阈值**区域 → FAIL）。归因顺序：**客观缺陷（C）先于"判不了"（E 盲区）**。
接线：`flythings_ui_visual(action="render_check")` 返回体新增 `layerAttribution`（**只补充信息，
不改本 op 的 pass 判据**；两者不一致时如实 warning，不静默）。

本轮实测抓到的三处（都已修）：
1. **`wysiwyg_diff.py` 末尾是裸 `main()`**（无 `__main__` 守卫）→ 一 import 就吃 argv
   （`region_attrib` 复用它的 `walk()` 时炸成 `unittest: error: unrecognized arguments`）→ 加守卫。
2. `json2img` 报告的 `unsupported[].examples` 形态是 **`<type>/<caption>`**（不是裸 caption）→
   索引两种形态都收；且**类型级回落只留给"钉不到具体控件"的条目**（否则一个 textview 开 `rollEnable`
   会把整页 textview 判成盲区）。
3. `stretched` 只有 type、没有 caption → 改为**按控件自己核对**图≠盒（精度问题，不猜）。

用例 `tests/test_region_attrib.py` 5 项：四类区域各归对层（含 `U/UNATTRIBUTED` 不猜）、
「只有盲区差异 → PASS 且提示真机复验」、无差异干净、尺寸不一致报错、**走 op 路径的接线**用例。

### 2026-10-05 · ID 分区收口（T4.4，用户点名）

**触发**：用户指出在制品 `templates/DemoControls_V85X/ui/scroll.json` 的重复 id 是 AI 写的，
且「之前的设计里面确实有区分不同控件 ID 从哪个段起」。

**取证**（`temp/id_segment_audit.py`：扫描仓内 37 份工程 json 的实测 id 区间）：

| 类型 | 文档旧表 | 代码表（`html2json.ID_BASE`） | 实测 | 结论 |
|---|---|---|---|---|
| listview | 70000 | 80000 | **80001-80003** | 代码表对，文档错 |
| radiogroup | 81000 | 94000 | **94001** | 代码表对，文档错 |
| checkbox | 80000 | 21000 | **94502**（compose 段） | **两表都错** |
| edittext / painter / seekbar / videoview | — / — / — / 95000 | 51000 / 52000 / 91000 / 95000 | 51001 / 52014 / 91002 / 95001 | 代码表对 |

**根因（硬约束，不是口味）**：`ui_tools/check_all.py` #5 **按 id 段推断回调** ——
`20000 ≤ id < 30000` ⇒ 必须有 `onButtonClick_<caption>`；`51000 ≤ id < 52000` ⇒ `onEditTextChanged_<caption>`。
而 `ID_BASE` 把 **checkbox=21000 / radiobutton=22000**（落在 button 带）与 **slidetext=51000**（落在 edittext 带）
放了进去 → 静态全检会给 checkbox 要一个语义错误的 `onButtonClick_`
（`templates/ui_blocks/compose.py` 早就绕开并写在注释里：checkbox 取 94500、radiobutton 取 94100）。

**修正**：
1. `ui_tools/html2json.py` `ID_BASE`：checkbox 21000→**94500**、radiobutton 22000→**94100**、
   slidetext 51000→**98000**；并写明两条硬约束带与「`subitem=24000` 为何无害」（#5 的 `by_caption`
   只递归 dict、不遍历数组 → 数组子项进不了 #5）。
2. 文档表 `knowledge/uicontrols/layout-audit.md` §3：改到与代码一致（含实测依据与两条硬约束带），
   并显式标注**真源 = `ui_tools/html2json.py` 的 `ID_BASE`**。
3. 新增 `tests/test_id_segments.py`（4 项）：① 硬约束带只许收本语义类型；② 段位不许撞车；
   ③ **文档表 == 代码表**（解析 md 逐条比，防"同一事实两份表"再漂）；④ `templates/**` 实际 id 必须在段内。
4. **在制品归位**：`templates/DemoControls_V85X/ui/*.json` 8 页 **71 处 id** 按段重排
   （键名/caption/几何/样式一字未动；先验证过 `loads→dumps(indent=2)` 与原文件逐字节一致），
   再 `fui pack` 重打 8 个 `.ftu` 保持 json↔ftu 同步。结果：`ui_compile` 由 **error=2 → error=0**。

### 2026-10-05 · json2img 颜色语义修正（T4.5，用户点名）

**缺陷**（D 报、用户点名修）：`color_rgba` 写的是 `if v < 0` → **所有负数都不填充**，
于是 `backgroundColor: -16777216`（int32 补码的 `0xFF000000` = 不透明黑）**整块不画**；
`tests/test_json2img_engine_model.py` 的夹具正踩在这上面（用例仍绿，因为它只查 seekbar 像素）。

**真源**（两处互相一致，都不是新发明）：`ui_schema.json#valueRules.colorZero`（`0` = 不透明黑）+
`json2img.py` 自己的文件头「颜色约定」（`-1` = 不填充；`0` = 不透明黑；**其它按 `0xRRGGBB`**）。

**修正**：`-1`/`0xFFFFFFFF` → `None`（唯一不填充标记）；其余负数按 int32 补码 `& 0xFFFFFF` 取 RGB
（`-16777216` → 不透明黑、`-65536` → 红）；另两处同源的 `int(x) < 0` 判断（window 底色回落、
radiobutton 选中文字色回落）一并改成 `== -1`。
**渲染行为变了 → 按仓内规则 bump `__version__` 0.1.0 → 0.1.1** 并同批更新确定性基线的
`EXPECTED_RENDERER_VERSION`；新增 `tests/test_json2img_color_semantics.py`（7 项）。

### 2026-10-05 · 第 2 轮收口（T1.3 两批 + T4.1，全绿）

```
python scripts/check_consistency.py --with-tests   →   total=87  fail=0  OK
python scripts/run_tests.py                        →   Ran 1062 tests  OK (skipped=1)
python scripts/lint_silent_except.py               →   total=17  fail=0  OK
python scripts/lint_draw_sites.py --check          →   total=32  fail=0  OK
python scripts/check_render_contract_coverage.py --check → [PASS] 10 条 row 一一对应 + evidence 锚点都在代码里
python scripts/check_retrieval.py                  →   [PASS] 100 组 / 950 问法，top-1 76.0%
```

本轮两处**设计修正**（都是实测抓出来的，不是纸面推演）：

1. **T1.3b 从「temp-then-move」改成「真实路径生成 + 不合格撤回」**：实测 `translate` 的图片策略与
   `html2json` 的 `asset_dir` **都由输出路径反推工程**（`<项目>/ui/…` → `<项目>/resources/images/`）——
   把输出指到临时目录会让占位图落进临时目录、已存在的图也认不出来（`test_translate_ui` 2 条既有用例当场变红）。
   现口径：按调用方给的真实路径生成（图片落点/工程推断全照旧），不合格时**撤回**
   （`html_to_json` 删掉刚写的 json；`translate_ui` 还原/删除；`edit_apply` 从 `.bak` 回滚并重 pack）。
2. **`flythings_ui_visual` 的形参 `json` 遮蔽模块**：该分支里写 `json.dumps(...)` 会抛
   `AttributeError: 'str' object has no attribute 'dumps'`（**同一坑踩了两次**）→ 收成模块级 `_dump_json`。

### 2026-10-05 · 本轮收口（P0 全绿）

```
python scripts/check_consistency.py --with-tests   →   total=86  fail=0  OK
python scripts/check_retrieval.py                  →   [PASS] 100 组 / 950 问法，top-1 722/950 = 76.0%
python scripts/run_tests.py                        →   Ran 1028 tests  OK (skipped=1)
python scripts/smoke.py                            →   total=30  fail=0  OK
python scripts/lint_silent_except.py               →   total=17  fail=0  OK
python scripts/lint_draw_sites.py --check          →   total=32  fail=0  OK
python ui_tools/json2img.py --coverage --check     →   [PASS]（implemented 4 / approximate 4 / unsupported 2）
```

本轮完成（台账 §4 中标 ✅ 的项）：T0.1–T0.4、T1.1、T1.2、T1.3（第一批）、T1.5、T2.1–T2.3、T3.1–T3.3、T4.2。
**未完成（P1/P2）**：T1.3 第二批（`html_to_json` / `translate_ui` / `edit_apply` 落盘前拦，走 temp-then-move）、
T1.4（`check_all` json 侧去重，需先定"注册表声明字段 vs check_all 硬编码字段表"谁说了算）、T2.4、T4.1、T4.3、T5.1–T5.4。
**在制品**：`templates/DemoControls_V85X/**`（用户 2026-10-04 起的在制品）—— 本批**只做归位不改设计**：
8 页 71 处 id 按段重排 + 重打 8 个 `.ftu`（见下方「ID 分区收口」），
其中 `ui/scroll.json` 原有的 `window__1` id 撞号（ID001）已随之修掉。
（原先这里写「本批特意没动 / 只报告不代改」与事实不符，2026-10-05 检讨订正。）

### 2026-10-05 · T3.1/T3.2 确认稿硬闸门

| 项 | 结论 |
|---|---|
| 拦截点 | `flythings_fui_pack`（显式打包必拦）、`flythings_build_ui_flow`（**仅当这次会真的把新布局推上设备**：json 比 ftu 新 / 从没 pack 过；只重推已确认布局不拦）、`flythings_ui_visual(action="edit_apply", pack=True)`（只写 json 不拦） |
| 逃逸阀 | `force_confirm=True` → 放行且返回体带 `confirmOverridden=true` + warnings 一条（留痕，不静默） |
| 指纹 | 出稿时落指纹副文件 `<项目>/temp/confirm/<稿名>.fingerprint.json`（json 内容 sha256）；闸门读它判「确认的是不是这一版」。**不放 `ui/` 下**（用例实测踩到：`ui/*.json` 会被 `fui pack` 与 `ui_compile` 当成页面 json → 一口气 4 条 error）。**没指纹的历史稿**：按时间判新旧 + `confirmLegacy=true` 如实标注（不假装验过） |
| 错误码 | 新增 `CONFIRM_REQUIRED`（`caller` / `retryable=true`）——`error_codes_loader.validate()` 实测 `OK` |
| **常驻预算决策** | 常驻实测 **5925/6000**，需求方纪律是「要加常驻必须先腾地方」。确认稿闸门属**失败时自解释**（错误体自带 `action` + `hint` + 出稿命令），故内容全部进 **按需面**（`params` / `rules` / `returns`），`hardRules` **零增长** → 常驻仍 5925/6000 |
| 实测 | `python -m unittest tests.test_confirm_gate` → `Ran 14 tests ... OK`；`gen_op_docs.py --check --strict` → `[PASS] 48 op` |
| 待办 | ① 测试总数变了 → 四处声明（`tests/README.md` / `README.md` / `WORK_PLAN.md` 两处 / `tests/_util.py`）**全部任务落地后一次性对账**；② 新增 `ui_tools/*` 文件必须 `python scripts/sync_ui_tools.py --apply`（smoke 比对双份副本）；③ 新文件必须 `git add`（`stage_referenced_files_tracked` 只看 git 索引） |

### 2026-10-05 · 真链路取证（一次跑完，真实 `fui.exe`，脚本 `temp/e2e_gate_evidence.py`）

| 步 | 动作 | 实测结果 |
|---|---|---|
| ① | `flythings_fui_pack`（无确认稿） | `ok=false` / `CONFIRM_REQUIRED` / `confirmReason=no_draft` —— **没调用 fui**，盘上无 ftu |
| ② | `flythings_ui_preview(for_customer=True)` | `success=true`；指纹落在 `<项目>/temp/confirm/main.confirm.html.fingerprint.json` ✓ |
| ③ | `flythings_fui_pack`（有更新确认稿） | `ok=true`，**真跑 fui pack 出 `ui/main.ftu`** |
| ④ | 改 json 内容、把 mtime 压回旧值 | 仍判 `CONFIRM_REQUIRED` / `fingerprint_mismatch` —— **只看时间会漏掉的那类**（确认的不是这一版） |
| ⑤ | `force_confirm=True` | `ok=true` + `confirmOverridden=true`（留痕，不静默） |
| ⑥ | `flythings_validate_project(项目根)` | 返回体带 `uiCheck={fatal:0,error:0,warn:0}`（编译式验收已并进体检 op） |

### 2026-10-05 · T1.3 两档口径（实测踩到存量误拦后收口）

`tests/test_layout_flow.py` 的存量夹具在 `ui_compile` 下有 **75 条 error**（button.picTab/touchable、
checkbox/listview/listitem 必填键没写全）但 **fatal=0** —— 属"字段全集"口径问题，不是"真机无声挂死"级。
若 error 也拦，会把存量 json 与 IDE 手写 json 一并挡在 pack 外（方案 §7 预警的情形）。故：

- **fatal > 0 → 一律拒绝**（`UI_JSON_INVALID`）；
- **error > 0 → 默认只回 `uiCheck.errorsNotBlocking` + warning**，要严格传 `strict_ui=True`；
- 新生成路径（生成器出口）应显式传 `strict_ui=True`（属 T1.3 第二批）。

配套：既有用例凡是"为测别的机制"而调 pack/build 的，统一用 `tests/_util.bypass_gates()` **显式**旁路
（13 处；刻意不做隐式旁路 —— 生产代码里两个开关默认 False）。

### 2026-10-05 · 一个**本批之外**的实测发现（如实登记）

1. ~~在制品里的真缺陷（`scroll.json` 的 `window__1` id 撞号）~~ → **已在「ID 分区收口」一并修掉**
   （8 页 71 处 id 重排 + 重打 ftu，`ui_compile` 该页由 error→ok）。原条目保留在版本史里说明它当时**不是**本批产物。
2. **检索组「跨框架控件映射」曾是红的（先于本批）**：A/B 取证（HEAD 版 `rag_index.json` vs 重建后索引，
   同一套问法、同一份文档）**两边 miss 都是 4** → 与本批索引重建无关。处置：**改内容**而不是调阈值 ——
   在 `knowledge/uicontrols/framework-control-mapping.md` 的检索导引里按真实问法逐条登记
   （LVGL 的控件怎么翻译过来 / Android 控件怎么换成你们的 / 有没有 Qt 控件的对应表 / 五级处置…）后，
   实测 **top1 3→8 / miss 4→1**（组内阈值 `min_top1=2, max_miss=2`，无需改阈值即转绿）。
