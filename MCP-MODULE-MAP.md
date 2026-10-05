# MCP 功能模块框图（模块划分 · 逐模块输入/输出契约 · 优化清单）

> **这份文件回答**：本 MCP 现在由哪些**互相独立的功能模块**组成？每个模块的**输入是什么、输出是什么、谁来判它合格**？以及每个模块**下一步该优化什么**。
> **它不是什么**：不是新规范，也不覆盖既有真源。凡与下列真源冲突，**以真源为准**：
> `ui_tools/ui_schema.json`（字段/类型/必填/`renderContract`）、`op_spec.json`（op 契约）、`ui_entrypoints.json`（入口登记）、
> `flow_spec.json`（开发流程原子）、`knowledge/devflow/ui-pipeline-spec.md`（界面产物管线口径 = **三档判据 + 模块 I/O 契约的唯一出处**）。
> 本文件的角色是**总览 + 索引**：把散在 42 个 op 与 `ui_tools/`（26 个模块文件 = 19 `.py` + 7 `.json`）里的分工收成一张可对照的图，并把优化项逐条落到模块上。

**统计口径**：本文件所有数字取自实测（`op_spec.json` / 目录清单 / 脚本自报），**不手写**；改动后须重跑
`python scripts/check_consistency.py --with-tests` 与 `python scripts/check_doc_refs.py`。文中"当前值"若与脚本打印不一致，以脚本为准。
（本文件是**总览与索引**，不参与任何派生生成；新增文件要进版本库记得 `git add`。）

---

## 0. 怎么读这份框图

| 你想问 | 看哪节 |
|---|---|
| 一共有哪些模块、谁归谁 | §1（总图）、§2（模块总表） |
| 某个模块吃什么、吐什么、谁判它合格 | §3（重点：逐模块 I/O 契约卡） |
| 某个 op 属于哪个模块、落在哪个文件 | §4（op 级台账） / §5（反查索引） |
| 这个模块现在有什么坑、该优化什么 | §7（优化清单，按模块编号对应） |
| 哪些"降级/盲区"是**如实登记过的**（别当缺陷修） | §6（已知降级/盲区总账） |
| 各模块之间**不许越界**什么 | §8（责任边界与禁止事项） |

---

## 1. 总图（当前实现，非规划）

### 1.1 三条轴：输入轴 → 产物链 → 交付轴

```
        【输入轴】什么样都能进，但要如实报「读懂了多少」
   ┌────────────┬────────────┬────────────┬──────────────┬───────────┐
   │ HTML 受限   │ LVGL C 源码 │ 块库 spec   │ 按 schema    │ 设计稿/线框 │
   │ 原型 /Figma │(translate) │(ui_blocks)  │ 直写 json    │ (客户确认)  │
   └─────┬──────┴─────┬──────┴─────┬──────┴──────┬───────┴─────┬─────┘
         │            │            │             │             │
         ▼            ▼            │             │             │
   ┌───────────────────────────┐  │             │             │
   │ ② json 生成（发射链）      │  │             │             │
   │ html2json / translate_ui  │  │             │             │
   │ ★ 共享发射层 ui_emit       │  │             │             │
   └───────────┬───────────────┘  │             │             │
               └──────────────────┴─────────────┴─────────────┘
                                  ▼
                    ui/*.json = 唯一事实源（可被人/编辑器直写）
                                  │
        ┌─────────────────────────┼───────────────────────────┐
        │ ③ 校验/审计/编译         │ ④ 渲染与像素判定           │ ⑤ 预览/编辑
        │ ui_compile（编译器式）   │ json2img（引擎等价 PNG）   │ json2html → .confirm.html
        │ check_all #1..#37        │ ui_diff（A/B 像素）        │ ui_editor → .edit.html
        │ gen_res / gen_ring 出图  │ wysiwyg_diff / region_attrib│ ui_edit_apply → 写回 json
        │                         │ ⑤→③ 闭环                   │
        └───────────┬─────────────┴─────────────┬─────────────┘
                    ▼                           ▼
        ┌───────────────────────────────────────────────────────┐
        │ ⑥ 编译/打包（fui pack）→ ui/*.ftu  ⑦ 部署（fun build/launch）
        │ 闸门：确认稿硬闸门 + ui_compile fatal 拦截              │
        └───────────────────────────┬───────────────────────────┘
                                    ▼
        【交付轴】⑧ 真机取证验收 → ⑩ 整机自检/缺陷单 → ⑪ 量产 update.img
                  └─ ⑨ 工程与依赖（Manifest/package/依赖树）横向支撑全链
                  └─ ⓪ 输入与规范查询、⓪' 知识库 横向支撑全链
```

### 1.2 一次改动的**必走链路**（跳步即返工）

```
改 ui/*.json → flythings_ui_compile(或 validate_project.ui_check) → flythings_fui_pack → fun build
            → flythings_build_ui_flow（含 launch）→ flythings_device_screenshot → ui_visual(diff/render_check)
```

> 真源：`flow_spec.json.invariants` 的 `json-pack-then-launch`（「改 json → 必 pack → 再 launch → 再抓屏；四步不许跳」）
> 与 `no-selfmade-commands`（口语「编译/构建/调试/部署/推设备/跑一下」**一律** `flythings_build_ui_flow`）。

---

## 2. 模块总表（11 个独立模块 · 42 个 op · `ui_tools/` 26 个模块文件）

| # | 模块 | 一句话职责 | 入口 op | 支撑脚本（`ui_tools/` 等） | 输入 | 输出 | 谁判它合格 |
|---|---|---|---|---|---|---|---|
| **M1** | **输入与规范查询** | 「写之前先读」：把平台/屏/字段/映射问清楚 | `get_project_spec`、`ui_schema`、`read_json`、`map_control`、`hardware_info` | `ui_schema_loader.py`、`ui_schema.json`、`mcp_control_map.json`、`platform_capabilities.json` | 控件类型名 / 源框架控件名 / 型号+平台 / json 路径 | 字段表·必填键·默认值 / 型号 preset / L1~L5 映射 + 可粘 json 片段 / 控件清单 | `scripts/gen_control_map_snippets.py --check`、`tests/test_ui_schema.py` |
| **M2** | **json 生成（源 → `ui/*.json`）** | 把**非 json 的源**翻译成布局 json；也是资源出图入口 | `html_to_json`、`translate_ui`、`generate_ui_assets` | `html2json.py`、`translate_tools.py`、`ui_emit.py`、`gen_res.py`、`gen_ring.py` | 受限 HTML/CSS 子集、LVGL C 源码、`assets[]` 描述 | `ui/*.json`（+`resources/images/*.png`）、`unrecognized`/`downgrades` 记账 | 落盘前 `ui_compile`（fatal 一律不落盘）+ `check_all` 关键项 0 FAIL |
| **M3** | **json 编译式验收与静态审计** | 回答「这个 json 能不能被设备加载 / 字段对不对 / 图与盒对不对」 | `validate_project`、`fui_pack`、`fui_unpack`、`edit_ftu`、`layout_audit`、`verify_assets` | `ui_compile.py`、`check_all.py`、`alpha_bg_audit.py`、`corner_audit.py`、`zero_color_audit.py` | `ui/*.json`（+`resources/images/`+`src/**`） | 诊断列表（规则号+路径+修法）/ 退出码 / `ui/*.ftu` | `ui_compile` rc=0、`check_all` 退出码、门禁脚本 |
| **M4** | **json → img 渲染与像素判定** | 无设备时**唯一的视觉验收手段**；有设备时做归因 | `ui_visual(action=render/render_check/diff/baseline)` | `json2img.py`、`ui_diff.py`、`wysiwyg_diff.py`、`region_attrib.py` + 像素基线库 `<项目>/ui_baseline/` | json + 资源 + 字体（离线）；渲染图 + 真机截图（归因） | PNG + `unsupported[]` + 机读报告 + 逐区域归因（C/E/A/U） | 确定性（同输入同 md5）+ 覆盖矩阵 `--coverage --check` + 盲区不许判通过 |
| **M5** | **预览、确认稿与可视化编辑** | 给人看的稿子；改坐标的入口（**不产最终判定**） | `ui_preview`、`ui_visual(action=editor/edit_apply)` | `json2html.py`、`ui_editor.py`、`ui_edit_apply.py` | 项目根或单个 json；变更 JSON | `.preview.html` / `.confirm.html` / `.edit.html`；指纹副文件；写回后的 json | 确认稿**硬闸门**：`pack` / `build_ui_flow` 前必须有比 json 新的 `for_customer` 稿 + 指纹匹配 |
| **M6** | **工程骨架与依赖（Manifest/package）** | 建工程、管依赖、管进度 | `create_project`、`attach_cli_tools`、`gen_logic_stub`、`project_state`、`list_packages`、`query_package`、`package_search`、`get_package_api`、`resolve_dependencies`、`manifest`、`add_package`、`check_project_deps` | `project_tools.py`、`package_tools.py`、`package_catalog.json`、`components_catalog.py` | 平台+分辨率+工程名；功能关键词；`include` 清单 | 工程骨架 / Manifest 编辑 / 依赖树 / 回调桩 / 进度槽位 | `validate_project`、`fun install` / `fun build` 实测、`tests/test_package_*.py` |
| **M7** | **打包与部署（fui pack / fun build / launch）** | 把 json 变成设备真正加载的 ftu 并推上去 | `build_ui_flow`、`pack_upgrade`、`device_preflight` | `project_tools.py`、`font_tools.py`、`preflight.py`、`toolchain/fui.exe`、`fun.exe` | 工程根；`with_launch`/`device`/`font_tier` 等策略参数 | `ui/*.ftu`、设备侧运行态、`steps[]`/`staleOnDevice`、`update.img` | `ui_compile` 闸门 + 设备侧 ftu/so 字节与 md5 一致性（`deviceSync`） |
| **M8** | **设备与真机验收 / 缺陷单** | 真机取证、批量用例、整机快照、出缺陷单 | `device_screenshot`、`gen_ui_test`、`test_run`、`selfcheck`、`bugreport` | `device_screenshot.py`、`bin_tools/<平台>/`（touch/busybox/zkshot）、`adb_tools.py`、`selfcheck_tools.py`、`test_tools.py` | 设备 serial / `IP:5555`；用例 plan JSON | 截图 PNG/JPG/BMP、`report.json`+`report.xml`、十一分区快照、缺陷单 md | 真机像素（最终真相）；`no-baseline` 记「未比到基线」而**不记通过** |
| **M9** | **i18n（多语言）** | 一条 op 六个 action 走完翻译链路 | `i18n` | `i18n_tools.py` | `i18n/*.tr`、布局 `@key` 引用、译文 | `i18n/<lang>.json` + 推送结果 | 设备读 json 不是 .tr → 必须 `action="to_json"`；格式判据（tab 制表 / 冒号后无空格 / 末尾无空行） |
| **M10** | **环境与自测** | 环境体检、版本、上机前探路 | `get_version`、`selfcheck`（环境侧） | `preflight.py`、`device_probes.py`、`platform_capabilities.json`、`media_capabilities.json`、`error_codes.json` | 本机环境 / 设备 | 版本与工具数 / 能力矩阵 / 错误码解释 | `scripts/check_consistency.py`、`scripts/smoke.py` |
| **M11** | **正式交付（量产）** | 固化升级包与刷机口径 | `pack_upgrade` | `project_tools.py`、`toolchain/` | 工程根 + 版本号 | `.fsc/<平台>/update.img` + 四种刷法说明 | 体积/签名错误码前置检查 + `fun pack` 实测 |
| **K** | **知识库与知识生长**（横切） | 检索、记缺口、落候选、导出回流 | `knowledge_search`、`knowledge_gaps`、`knowledge_capture`、`knowledge_export` | `rag_search.py`、`kb_local.py`、`kb_authority.py`、`knowledge/` | 中文 query / 一篇候选知识 | 带 `status`/`evidenceLevel` 的片段；缺口清单；脱敏补丁包 | `scripts/check_kb.py`、`scripts/check_retrieval.py`、`kb_verify.py` |

> 说明：`M11` 与 `M7` 共用 `pack_upgrade` 的链路（前者=交付固化，后者=调试部署），按**用途**分家；表中 op 名重复是刻意的 —— 一个 op 服务两个用途时，判定口径不同（交付要体积/签名，调试要 `deviceSync`）。
> `ui_visual` 跨 `M4`/`M5`（同一 op 按 `action` 分叉，共 32 个参数，`action=list` 才现场列全）；`selfcheck` 跨 `M8`/`M10`。

---

## 3. 逐模块 I/O 契约卡

> 卡片格式统一：**输入 → 输出 → 判据 → 已知边界**。
> 「判据」一栏写的是**谁红了就是谁的错**；跨层"顺手修一下"会抹掉责任归属（口径见 `knowledge/devflow/ui-pipeline-spec.md` §4）。

### M1 · 输入与规范查询

| 项 | 内容 |
|---|---|
| 入口 op | `flythings_get_project_spec()`（无参）、`flythings_ui_schema(control_type, include)`、`flythings_read_json(json_path)`、`flythings_map_control(query, source)`、`flythings_hardware_info(model, platform)` |
| 输入契约 | 控件类型名 / 源框架控件名 + `source∈{lvgl,qt,android,miniprogram,emwin,mfc}` / 型号或平台 / json（或 `.ftu`，先 unpack）路径 |
| 输出契约 | 字段表·必填键·默认值·类型；型号 preset（分辨率/方向/按键/接口）；L1~L5 等价级 + **可直接粘的 json 片段**；控件列表 + `caption→id` 映射 |
| 真源 | `ui_tools/ui_schema.json`（唯一）+ `mcp_control_map.json`（人工维护的索引）+ `hardware_catalog.json` |
| 判据（红了算它的） | `gen_control_map_snippets.py --check`（片段必须由 schema 派生）、`tests/test_ui_schema.py`、`tests/test_control_map.py` |
| 已知边界 | 注册表缺失 → **抛 `SchemaRegistryError`，不退回内嵌副本**；只说型号系列时**不外推规格**（猜错=整份工程返工）；未命中映射回 `NO_HIT`+候选，不编 |
| 优化 | §7-M1 |

### M2 · json 生成（源 → `ui/*.json`）

| 项 | 内容 |
|---|---|
| 入口 op | `flythings_html_to_json(input_html, output_json, res, merge_windows, allow_unvalidated, strict_ui)`、`flythings_translate_ui(source, out, res, dry_run, gen_placeholders, ...)`、`flythings_generate_ui_assets(project_root, assets)` |
| 输入契约 | **HTML 受限子集**（写法见 `ui_tools/HTML_SUBSET.md`；多屏 = 每屏一个 `div.screen`）；**LVGL C 源码**（只识别子集）；`assets[]` = JSON 数组 `{name,size,prompt,emoji,color,kind}`（`name` 必填） |
| 输出契约 | `ui/*.json`（缺省：一屏一 json = 一页 = 一 Activity = 一个 ftu）；`<项目>/resources/images/*.png`（CSS 效果自动转图，尺寸==控件盒）；返回体 `screensDetected`/`pagesProduced`/`pages[]`；`unrecognized`/`downgrades` 逐条记账 |
| 共享发射链 | `ui_tools/ui_emit.py` = **字段补全的唯一实现**（`fill_required` 只补注册表必填键；`schema_complete` 管键序/`tab5`）。三个前端 `translate_tools` / `html2json` / `ui_blocks.compose` 都走它；差异逐条登记在 `ui_tools/emit_conformance.json`，由 `scripts/gen_emit_conformance.py --check` 对账 |
| 判据（红了算它的） | ① `ui_compile` **fatal > 0 一律不落盘**（`UI_JSON_INVALID` + `uiDiagnostics[]`）；② `screensDetected == pagesProduced == 设计稿屏数 N`，不等即 `success:false`（不静默丢页）；③ `check_all` 关键项 0 FAIL |
| 已知边界 | CSS 不可实现项**一律点名**（伪元素 `::-webkit-slider-thumb`、有效图右端圆角、`.fill` 自身宽度渐变、`inset` 内阴影…）；运行时 `setBackgroundPic` 不保留 alpha（透明底 PNG 会变白块）；单冒号伪类不支持；无布局引擎 → 百分比只能近似 |
| 优化 | §7-M2 |

### M3 · json 编译式验收与静态审计

| 项 | 内容 |
|---|---|
| 入口 op | `flythings_validate_project(project_root, ui_check='auto')`（**主入口**）、`flythings_fui_pack(json_path, force_confirm, allow_unvalidated, strict_ui)`、`flythings_fui_unpack(ftu_path, overwrite)`、`flythings_edit_ftu(ftu_path, operations, ...)`、`flythings_layout_audit(project_root, page)`、`flythings_verify_assets(project_root)` |
| 输入契约 | 单个 `.json` / 工程根（扫 `ui/*.json`，下探一层 `ui/<分辨率>/*.json`）/ 目录；`--res WxH` 可钉屏；`json_path` 给 `fui pack` = 打包该目录下所有同名 json |
| 输出契约 | 诊断列表（**规则号 + 路径 + 原因 + 修法**）+ 退出码（0 无 fatal/error；1 有；2 用法错）；`ui/*.ftu`；`uiCheck{fatal,error,warn}` + `uiDiagnostics[]`；`ftuPath`/`controlsCount`/`resolution` |
| 规则真源 | `ui_compile.py`（消费 `ui_schema.json`，22 条规则：PARSE001/002、PAGE001、SCH001–004、NAME001/002、ID001/002、TREE001–004、ROOT001、CHAR001、ASSET001/002、GEOM001 + RES001/SCAN001）；`check_all.py` #1..#37（含 4b、#15/#16 为 WARN） |
| 判据（红了算它的） | `ui_compile` rc=0；`check_all` rc=0；`tests/test_ui_compile.py`、`tests/test_layer_rules.py`、`tests/test_render_contract.py` |
| 两档口径 | `fatal > 0` **一律拒绝**；`error > 0` 默认只记 `uiCheck.errorsNotBlocking` + warning，`strict_ui=True` 才拦（存量/IDE 手写 json 的"字段全集"欠账不挡 pack） |
| 已知边界 | `ui_compile` **不实现** `renderContract` 的 `pic-scale`/`progress-clip`/`thumb-size`/`alpha-compose`/`edge-aa`/`stroke-aa`/`nine-patch`/`rounding`/`family-consistency`（在报告 `delegated` 里点名交给 `check_all`）；图尺寸==盒子 / AA / 倒角 / 透明底**不在** `ui_compile`；`check_all` 的 json 侧检查目前仍是**第二份实现**（T1.4 未合并代码） |
| 优化 | §7-M3 |

### M4 · json → img 渲染与像素判定

| 项 | 内容 |
|---|---|
| 入口 op | `flythings_ui_visual(action=…)`：`render` / `render_check` / `diff` / `baseline` / `list` |
| 输入契约 | 离线：`project_root` + `page` + `scale` + 可选 `--font`；归因：`渲染图 + 真机截图 + 页面 json`；A/B：两张同尺寸图 + `tol/shift/min_area` |
| 输出契约 | 引擎等价 PNG（默认 `<json目录>/<page>.render.png`）；`unsupported[]` / `stretched` / `missing_assets` 机读报告（`--json-report`）；像素差异清单（0 token）；`region_attrib` 的 `layerAttribution`（C/EMIT-FIELDS、C/ASSET-GEOMETRY、E/RENDERER-BLINDSPOT、E/FONT-METRICS、A/FRONTEND-REPORT、U/UNATTRIBUTED） |
| 真源 | `ui_schema.json#renderContract.rows`（**10 条**，行集合唯一真源）；状态住 `ui_tools/json2img_coverage.json`；豁免登记 `ui_tools/json2img_blindspot_allow.json`（每条必须写 `reason`） |
| 判据（红了算它的） | 确定性（同输入同 md5，基线绑定 `json2img.__version__`）；`--coverage --check` rc=0；`--judge` 下未豁免盲区 rc=1（**盲区不许当通过**） |
| 已知边界 | 静止态渲染：滚动位置/动画/视频**不还原**；`circlebar` 近似弧；`listview` 运行期数据与滚动不还原；`radiogroup`/`checkbox` 按 json `checked` 画静止态；`imageanim` 只画 `pic0` 首帧；`videoview` 画色块；`digitalclock`/`painter`/`pointer`/`diagram`/`cameraview`/`slidetext`/`charsetTab` 不还原；`alignment` 的 `5/0/1/4/6/2` **没有真机实测表**（`--align-mode measured|task36` 两解码，都会打印进校准清单） |
| 优化 | §7-M4 |

### M5 · 预览、确认稿与可视化编辑

| 项 | 内容 |
|---|---|
| 入口 op | `flythings_ui_preview(target, output_dir, for_customer)`；`flythings_ui_visual(action="editor"\|"edit_apply", changes, dry_run, pack, ...)` |
| 输入契约 | 项目根或单个 json；变更 JSON `{file, resolution, changes{}, props{}}`；`for_customer=True` 出客户确认稿 |
| 输出契约 | `.preview.html`（内部预览）/ `.confirm.html`（**单文件、图内联、可转发**）/ `.edit.html`（拖拽编辑器页）；写回时 `ui/*.json` + `<name>.json.bak`（可选重 `pack`）；确认稿旁落指纹副文件 `<项目>/temp/confirm/<稿名>.fingerprint.json`（json 内容 sha256） |
| 判据（红了算它的） | **确认稿硬闸门**：`fui_pack`（显式打包必拦）、`build_ui_flow`（仅当这次真会把新布局推上设备时拦）、`ui_visual(edit_apply, pack=True)` 前，必须有 `for_customer` 稿且**比 json 新** + 指纹匹配；`force_confirm=True` 放行但返回体带 `confirmOverridden=true` + warnings；历史稿无指纹按时间判 + `confirmLegacy=true` 如实标注 |
| 已知边界 | 稿子**不许放 `ui/` 下**（会被 `fui pack` / `ui_compile` 当页面 json）；`.edit.html` **不算确认稿**（拿工具当确认）；`ui_editor` 页面内没有回传通道（必须复制粘贴给 AI）；图内联累计上限 14 MB；`id` 由 IDE 生成、编辑器不支持改 |
| 优化 | §7-M5 |

### M6 · 工程骨架与依赖（Manifest/package）

| 项 | 内容 |
|---|---|
| 入口 op | `create_project`、`attach_cli_tools`、`gen_logic_stub`、`project_state`、`list_packages`、`query_package`、`package_search`、`get_package_api`、`resolve_dependencies`、`manifest`、`add_package`、`check_project_deps` |
| 输入契约 | 平台 + 分辨率 + 工程名（**两项平台参数必须由用户/型号库给出**）；功能关键词（`features="mqtt,json,蓝牙"`）；`packages` = JSON 数组字符串 |
| 输出契约 | 工程骨架（模板 → 工程名/分辨率/平台替换）；`Manifest.xml`（默认 `dry_run=True` **只推荐**，写盘先备份 `.bak`）；依赖树与冲突建议；回调桩（**只补不改**）；进度槽位（`flow_spec.json.stateSlots` 10 个） |
| 判据（红了算它的） | `validate_project`（含 `ui_check`）；`fun install` / `fun build` 实测；`tests/test_ui_compile_gate_paths.py`、`tests/test_package_*.py` |
| 已知边界 | 桩**禁手写**：缺桩让 `fun build` 追加后把桩移到文件作用域；⛔ `rm <p>Logic.cc` 重建**只允许首次构建/空文件**，有业务代码时删除 = 代码衰退、禁止；**Manifest 必须声明传递依赖**（用 `mqtt-cxx` 要连 `paho-mqtt3as` + `openssl`）；**注册表没有 ≠ 平台没有**（设备 `/lib` 自带 nanovg/libpng12/freetype/jpeg/mad/zlib，可 dlopen 免编译） |
| 优化 | §7-M6 |

### M7 · 打包与部署（fui pack / fun build / launch）

| 项 | 内容 |
|---|---|
| 入口 op | `flythings_build_ui_flow(project_root, with_launch=True, device, font_check, font_tier, force_confirm, strict_ui)`、`flythings_device_preflight(project_root, device, adapt, font_check, font_apply)` |
| 输入契约 | 工程根；`with_launch=False` 只编译不碰设备；`device='<IP>:5555'` 或留空自动探测（**0 台 → `needDeviceInput` + `installHint`；多台 → 列出来不替你猜**） |
| 输出契约 | `steps[]`（`check_timestamps` → `fui pack` → `fun install` → `check_font` → `fun build` → 设备探测 → `fun launch` → `verify_device_sync`）；`launched`/`pushed`/`device`/`model`/`platformMatch`/`staleOnDevice`（true ⇒ 设备上跑的还是旧版）；`ui/*.ftu`；字体体检 `fontCheck{missingChinese,maxFontBytes,advisedTier,delivered,deviceFonts}` |
| 判据（红了算它的） | `ui_compile` 闸门（fatal 拦）+ 设备侧 ftu/so **字节与 md5 一致性**（`deviceSync`）+ 时间戳防呆 |
| 已知边界 | ftu 是**编译产物**，改布局一律改 json 再 pack，**不要手写/手改 ftu**；`src/activity/` 由 ftu/IDE 生成、**禁手改**；链库 `src/dependencies/lib/`，**libc 必须匹配**（Z20/Z21=glibc，其余=musl 系）；分辨率比例差 > 3% 时**任何档都不改盘**，只出 plan |
| 优化 | §7-M7 |

### M8 · 设备与真机验收 / 缺陷单

| 项 | 内容 |
|---|---|
| 入口 op | `device_screenshot(device, out, fmt, scale, layer, vdec_chn, crop, rotate, …)`、`gen_ui_test(test_type, …)`、`test_run(plan, devices, parallel, baseline)`、`selfcheck(device, diff_against, out)`、`bugreport(...)` |
| 输入契约 | 设备 serial / `IP:5555` / `auto`；`plan` 用例 JSON（`steps[].action ∈ tap/long/swipe/wait/monkey/run/shot/log`，每步可带 `shot/expectLog/expectNoLog/allowRegions`） |
| 输出契约 | 截图 PNG/JPG/BMP（`--scale` 省 token、自动方向/裁剪）；`report.json` + `report.xml`（可进 CI）；十一分区快照 `{ok,hint,data}`；缺陷单 markdown（**证据文件不存在 → `EVIDENCE_MISSING`，不静默**） |
| 判据（红了算它的） | **真机像素 = 最终真相**；`no-baseline` 记「未比到基线」而**不记通过**；跨设备**不要共用同一个基线 key** |
| 已知边界 | 设备 rootfs 是裁剪版：没有 `screencap`/`dd`/`head`/`uname`，只有 `cat`/`ls`/`echo`；`adb exec-out cat /dev/fb0` 不可用（patched adbd 无 shell v2）；`layer="video"` 仅 SigmaStar，多路/拼墙必须给 `vdec_chn`（**拼墙在 chn 1**），通道选错 = 抓不到帧；Z20 屏保是 FFmpeg 软解、不建 MI VDEC 通道 |
| 优化 | §7-M8 |

### M9 · i18n（多语言）

| 项 | 内容 |
|---|---|
| 入口 op | `flythings_i18n(project_root, action, lang, lang_name, base_lang, keys, context, translations, merge, dry_run, langs, push, device)` |
| 输入契约 | `action ∈ {scan, refactor, add_language, export, import, to_json}`（一步一 action）；`.tr` 文件、布局里的 `@key` 引用、译文 |
| 输出契约 | `scan`→语言表/各语言 key 数/缺失 key/引用缺失；`export`→待译清单 + 翻译提示；`import`→写回文件清单；`to_json`→`i18n/<lang>.json` 清单 + 推送结果 |
| 判据（红了算它的） | 设备**读 json 不是 .tr** → 改完必须 `action="to_json"`；`i18n/<lang>.json` 必须是 **tab 制表 + 冒号后无空格 + 末尾无空行**（不要手改 json） |
| 已知边界 | `scan` 只读；`refactor` 缺省 `dry_run=true`；纯数字/时间占位自动跳过；布局 `text` 带 `@key`，代码 `setTextTr(key)` **不带 @** |
| 优化 | §7-M9 |

### M10 · 环境与自测 · M11 · 正式交付（量产）

| 模块 | 输入 | 输出 | 判据 / 边界 |
|---|---|---|---|
| **M10** | 本机环境 / 设备 | `get_version`→版本+`toolCount`+`positioning`+`binTools`；`selfcheck`→十一分区快照；能力矩阵（`platform_capabilities.json`/`media_capabilities.json`）；错误码解释（`error_codes.json`） | 「读不到」本身就是结论（`ok=false` + hint 说清条件），**绝不静默吞掉**；采集容忍设备缺工具（优先随仓 `bin_tools/<平台>/busybox`） |
| **M11** | 工程根 + 版本号 + `with_build` | `.fsc/<平台>/update.img` + 四种刷法（TF 卡 / ADB setprop / zkautoupgrade / HTTP OTA）+ `howToFlash` | `dry_run=True` 只回命令计划；`sign error 0xc0000135`=缺 32 位 VC++；`package not found in local`=先 `fun install`；**不推设备**（与调试部署分家） |

### K · 知识库与知识生长（横切）

| 项 | 内容 |
|---|---|
| 入口 op | `knowledge_search(query, k)`、`knowledge_gaps(limit, out)`、`knowledge_capture(...)`、`knowledge_export(...)` |
| 输入契约 | **中文** query；一篇候选知识（title/body/category/evidence/layer） |
| 输出契约 | 带 `status`/`evidenceLevel`/`freshness` 的片段（未验/过期带 advisory）；缺口清单（top-N 问法 + 次数 + `nextActions`）；脱敏补丁包 `kb-contrib-<时间>.json` |
| 判据（红了算它的） | `scripts/check_kb.py`、`scripts/check_retrieval.py`（检索回归，按组阈值）、`scripts/kb_verify.py` |
| 已知边界 | 导出**强制脱敏**（IP/本机路径/凭据/主机名 → 占位符），未脱敏必须显式 `internal=True`；缺口数据来自本地层 `_logs/no_hit.jsonl`（**不外发**）；命中同主题回 `duplicateOf`，提示**合并**而非新建 |
| 优化 | §7-K |

---

## 4. op 级台账（42 个 op：模块归属 + 风险档 + 实现文件）

| op | 模块 | category | stage | `risk` 登记 | 实现落地 |
|---|---|---|---|---|---|
| `flythings_create_project` | M6 | project | build | write | `project_tools.py` |
| `flythings_pack_upgrade` | M11/M7 | build | build | write | `project_tools.py` + `kb_tools.py` 编排 |
| `flythings_device_screenshot` | M8 | device | build | device | `ui_tools/device_screenshot.py::capture` |
| `flythings_verify_assets` | M3 | layout | build | read | `ui_tools/check_all.py::verify_assets` |
| `flythings_ui_schema` | M1 | layout | design | read | `ui_tools/ui_schema_loader.py` + `ui_schema.json` |
| `flythings_get_version` | M10 | kbase | other | read | `kb_tools.py` |
| `flythings_knowledge_gaps` | K | kbase | other | read | `kb_local.py::gaps` |
| `flythings_knowledge_search` | K | kbase | design | read | `rag_search.py` + `kb_local.py` |
| `flythings_knowledge_capture` | K | kbase | other | write | `kb_local.py::capture` |
| `flythings_knowledge_export` | K | kbase | other | read | `kb_local.py::export_pack` |
| `flythings_hardware_info` | M1 | kbase | other | read | `hardware_tools.py::query` |
| `flythings_map_control` | M1 | layout | design | read | `kb_tools.py` + `mcp_control_map.json` |
| `flythings_translate_ui` | M2 | layout | design | write | `translate_tools.py` + `ui_tools/ui_emit.py` |
| `flythings_read_json` | M1 | layout | design | read | `project_tools.py` |
| `flythings_get_project_spec` | M1 | layout | design | read | `project_tools.py` |
| `flythings_validate_project` | M3 | layout | design | read | `project_tools.py` + `ui_tools/ui_compile.py` |
| `flythings_layout_audit` | M3 | layout | design | read | `project_tools.py` |
| `flythings_fui_pack` | M3 | layout | build | write | `project_tools.py` + `toolchain/fui.exe` |
| `flythings_fui_unpack` | M3 | layout | build | write | `project_tools.py` + `toolchain/fui.exe` |
| `flythings_edit_ftu` | M3 | layout | build | write | `project_tools.py` |
| `flythings_device_preflight` | M7 | build | build | read ⚠️ | `project_tools.py` + `font_tools.py` + `preflight.py` |
| `flythings_build_ui_flow` | M7 | build | build | device | `project_tools.py` |
| `flythings_ui_preview` | M5 | layout | design | write | `ui_tools/json2html.py` + `kb_tools.py` 指纹 |
| `flythings_html_to_json` | M2 | layout | design | write | `ui_tools/html2json.py` + 验收闸门 |
| `flythings_list_packages` | M6 | package | build | read | `package_tools.py` |
| `flythings_project_state` | M6 | build | build | write | `project_state.py` + `flow_spec.json` |
| `flythings_query_package` | M6 | package | build | read | `package_tools.py` |
| `flythings_manifest` | M6 | package | build | write | `package_tools.py` |
| `flythings_add_package` | M6 | package | build | write | `package_tools.py` |
| `flythings_package_search` | M6 | package | build | read | `package_tools.py` |
| `flythings_get_package_api` | M6 | package | build | read | `package_tools.py` |
| `flythings_resolve_dependencies` | M6 | package | build | read | `package_tools.py` |
| `flythings_gen_logic_stub` | M6 | project | build | write | `logic_tools.py` |
| `flythings_gen_ui_test` | M8 | device | build | device | `test_tools.py` |
| `flythings_test_run` | M8 | device | build | device | `test_tools.py` |
| `flythings_attach_cli_tools` | M6 | project | build | write | `project_tools.py` |
| `flythings_check_project_deps` | M6 | project | build | read | `package_tools.py` + `font_tools.py` |
| `flythings_generate_ui_assets` | M2 | assets | design | write | `ui_tools/gen_res.py::gen_ui_assets` |
| `flythings_ui_visual` | M4/M5 | ui-visual | design | write | `kb_tools.py` + `ui_tools/{ui_editor,ui_edit_apply,ui_diff,json2img,wysiwyg_diff}.py` + 仓根 `ui_baseline.py` |
| `flythings_selfcheck` | M8/M10 | device | build | device | `selfcheck_tools.py` |
| `flythings_bugreport` | M8 | device | write | write | `selfcheck_tools.py` |
| `flythings_i18n` | M9 | i18n | build | write | `i18n_tools.py` |

**风险档实测分布**：`read` 19 / `write` 18 / `device` 5。
⚠️ 标记的 `device_preflight` 是**登记值与行为不符**的一例（`font_apply` 默认 True 会往工程投字库，`adapt='force'` 会改 `.settings`）：见 §7-P0-2，本表按 `op_spec.json` **原样登记**，不擅自改真源。

---

## 5. 反查索引（`ui_tools/` 脚本 → 属于哪个模块）

| 脚本（`ui_tools/`） | 模块 | 只读/写盘 | 一句话 |
|---|---|---|---|
| `ui_schema.json` + `ui_schema_loader.py` | M1 | 只读 | 字段/类型/必填唯一真源 + 唯一消费入口 |
| `ui_emit.py` | M2 | 只读（纯库，无 CLI） | **唯一发射层**：必填键补全 / 键序 / `tab5` |
| `html2json.py` | M2 | 写盘 | 受限 HTML → `ui/*.json`（CSS 效果自动出图） |
| `json2html.py` | M5 | 写盘 | json → `.preview.html` / `.confirm.html` |
| `ui_editor.py` | M5 | 写盘 | json → 可拖拽 `.edit.html`（**自己不改 json**） |
| `ui_edit_apply.py` | M5 | 写盘 | 变更 JSON → 写回 json（留 `.bak`，可选 pack） |
| `ui_compile.py` | M3 | 只读 | **编译器式验收**：规则号 + 路径 + 修法 + 退出码 |
| `check_all.py` | M3 | 只读（#9 例外：会自动同步 + pack） | 一键全检 #1..#37（交付门禁） |
| `gen_res.py` | M2 | 写盘 | CSS 效果 → PNG/`.9.png`/序列帧（出图唯一实现） |
| `gen_ring.py` | M3 | 写盘 | `circlebar` 环图（**换尺寸必须重生成，不能 .9 拉伸**） |
| `alpha_bg_audit.py` / `corner_audit.py` / `zero_color_audit.py` | M3 | 只读 + 可选产物 | 透明底/倒角/弧线质量/`0` 值颜色 四类资产审计 |
| `json2img.py` | M4 | 写盘（PNG/报告），**不改工程文件** | json → 引擎等价 PNG + 覆盖矩阵 + 盲区记账 |
| `ui_diff.py` | M4 | 只读 + 可选产物 | 两张图逐像素 diff（0 token 清单） |
| `wysiwyg_diff.py` | M4 | 只读 + `--json` | 渲染图 vs 真机截图一致性（逐控件 top N） |
| `region_attrib.py` | M4 | 只读 + `--json-out` | 区域级归因：C 发射层 / E 渲染器 / A 前端 / U 判不了 |
| `device_screenshot.py` | M8 | 写盘（截图） | 真机抓屏（fb0 / SigmaStar 视频层） |
| `font_subset_by_project.py` | M7 辅助（**存储异常专用**） | 写盘 | 按工程字符裁字库 → `<项目>/font/font.ttf`；**日常缺中文请先选档**（`font_tier='common'\|'full'\|'multi'`，或问 `flythings_check_project_deps` 的 `fontTiers`），只有 tmpfs/存储装不下现成档才裁（口径见 `knowledge/devflow/device-deploy-budget.md` §3） |

> **副本口径**：`ui_tools/` 的**单一来源 = 本仓 `ui_tools/`**；`scripts/sync_ui_tools.py` 管「源 → 副本（默认 `../ui_tools`）」的 `--check` / `--apply`。
> 本仓是 MCP 包根（`tools/FlyThings_mcp_open/` 那套 workspace 布局在本检出**不存在**），所以开发只改仓内这一份。

---

## 6. 已知降级/盲区总账（**如实登记过，别当缺陷修**）

| 模块 | 已登记的降级/盲区（要点） | 登记在哪 |
|---|---|---|
| M2 | CSS 不可实现项逐条点名；运行时 `setBackgroundPic` 不保留 alpha；无布局引擎 → 百分比近似；单冒号伪类不支持 | `ui_tools/HTML_SUBSET.md`、`html2json.py` 头 |
| M3 | `ui_compile` 不实现 9 条 `renderContract`（`delegated` 点名）；图==盒/AA/倒角/透明底不在它；`check_all` json 侧仍是第二份实现（T1.4）；#15/#16 为 WARN 需人工审批；无 `DESIGN.md` → NOTE 跳过 | `ui_compile.py` 报告、`check_all.py` |
| M4 | 静止态不还原动态；`circlebar` 近似；`listview`/`radiogroup`/`checkbox`/`imageanim`/`videoview` 限制；`alignment` 6 个值无真机表；缩放算子 NEAREST（设备端缩放器无规格） | `ui_tools/json2img_coverage.json` + `json2img.py` 头 |
| M5 | 稿子不许进 `ui/`；`.edit.html` 不算确认稿；编辑器无回传通道；图内联 14 MB 上限；`id` 不可改 | `knowledge/devflow/ui-layout-verify.md` §0、`ui_editor.py` |
| M6 | 桩只补不改；注册表没有 ≠ 平台没有；Manifest 必须声明传递依赖 | `op_spec.json` 的 `rules` |
| M7 | 比例差 > 3% 不改盘；libc 必须匹配；ftu 禁手改 | `op_spec.json` 的 `rules`/`hardRules` |
| M8 | rootfs 裁剪（无 screencap/dd）；`exec-out` 不可用；通道选错抓不到帧；Z20 屏保无 VDEC 通道 | `device_screenshot.py` 头 |
| M9 | 设备读 json 不是 .tr；格式三判据；`scan` 只读 / `refactor` 默认 dry_run | `op_spec.json` 的 `hardRules`/`rules` |
| K | 导出强制脱敏；缺口数据不外发；同主题回 `duplicateOf` | `op_spec.json` 的 `hardRules` |

---

## 7. 优化清单（按模块对应；**先只列清单，未动实现**）

> 编号规则：`P0`=一致性/正确性缺陷（能被判红）｜`P1`=能力缺口（影响交付质量）｜`P2`=长线/收口。
> 每条给 **问题 → 证据 → 建议动作 → 判据（怎么算做完）**。改任何一条前先读 `DESIGN_SPEC.md`（规范优先、实测优先、不静默、唯一真源）。

### 7.1 P0 —— 登记与真源不一致（**当前就能判红，且会误导 AI**）

| # | 模块 | 问题 | 证据（实测） | 建议动作 | 判据 |
|---|---|---|---|---|---|
| **P0-1** | 全局 | op 数出现 **47** 与 **42** 两种说法 | 实测 `len(op_spec.ops)` = 42、`kb_tools.OP_NAMES` = 42、`register_all()` 注释 = 42；而 `mcp_server_flat.py` 文件头、`mcp_extras.py`、`op_spec.json` 的 `tiers`、`mcp_server.py` 注释里写 47 | 把「47」统一为 42（或改成不写数字的表述），并加一条用例断言「docstring 里的 op 数 == `len(OP_NAMES)`」 | 新用例能判红；全仓 grep「47 个 op」0 命中 |
| **P0-2** | M7/K/M10 | 4 个 op 的 `risk` 登记与代码行为不符 | `device_preflight`（read，但 `font_apply` 默认 True 会投字库、`adapt='force'` 改 prefs/ftu）、`knowledge_search`（read，但未命中会 append `_logs/no_hit.jsonl`）、`knowledge_gaps`（read，但传 `out` 写文件）、`knowledge_export`（read，但写导出包） | 二选一：① 改 `risk` 登记为 write；② 保持 read 但在 `op_spec` 里显式注明「会写本地记账文件」。**倾向 ①**（`risk` 是给调用方看的风险档） | `check_consistency` 加一条「risk=read 的 op 不得出现写盘调用」的静态扫描（或逐条人工签字） |
| **P0-3** | M4 | `json2img` 的 `alignment` 6 个值（`5/0/1/4/6/2`）**没有真机实测表**，靠位模型推断 | `json2img.py` 头「TODO(待校准)…这 6 个值**没有**真机实测表」；`--align-mode measured\|task36` 两解码并存 | 出对照图钉死真源：对 6 个值各渲染一次 + 真机抓屏，逐值判定后把 `ALIGN_TABLE` 的 `uncalibrated=True` 改掉，并删掉多余分支 | 真机对照证据入 `tests/` 或 `knowledge/_reports/`；`--align-mode` 只剩一种解码 |
| **P0-4** | M4 | 判定基准有被当结论用的风险 | `ui-pipeline-spec.md` §1 已写「`json2img` 是模拟层…替代真机不够」，但 `ui_visual(render_check)` 的 `pass` 判据与真机结论仍是两回事 | 在 `ui_visual` 返回体里**显式带**「这是离线近似，真机真相需 `device_screenshot`」（若已有则本条作废） | 返回体含该字段；用例断言它的存在 |

### 7.2 P1 —— 各模块的能力缺口

| # | 模块 | 问题 | 证据 | 建议动作 | 判据 |
|---|---|---|---|---|---|
| **P1-1** | M1 | `params`/`returns` 字段覆盖不全（31/42、13/42），按需面契约有洞 | 实测 `op_spec`: `params` 31、`returns` 13、`hardRules` 13、`flow` 22、`rules` 26 | 补齐 `returns`（至少把 42 条的返回体关键字段登记全）；`params` 按 `renderSpec` 口径只登记"需要额外说明"的，**不复制签名** | 覆盖率数字由脚本打印；新增 op 缺 `returns` 时门禁提示 |
| **P1-2** | M1 | 英文问法够不着（`button`↔按钮、`slider`↔seekbar、`checkbox`↔勾选框） | `DESIGN_SPEC.md` §6 实测：`flythings_gen_logic_stub` 英文问法只拿 3 分 | 按 §6 最小改动：① `triggers` 批量补英文同义控件名（可从 `ui_schema.json` 的 key 取候选）；② 错误码 `hint` 双语 | `check_retrieval.py` 加英文问法组，top-1 达阈值 |
| **P1-3** | M2 | 三个前端各持一份**取值表**，取值漂移抓不住 | `emit_conformance.json` 只比**必填键完整性、不比取值**，且 `html2json` 只抽到 5 个类型 | 把对账器扩到**全类型 + 取值**（先出差异快照，再逐条定性：编码形态 / 待核 / 真缺陷） | `gen_emit_conformance.py --check` 覆盖全类型且带取值列；已知差异逐条有归属 |
| **P1-4** | M2 | `html2json` 的不可实现项只写在文件头/文档，AI 侧不可机读 | 降级清单在 `html2json.py` docstring + `HTML_SUBSET.md` | 把降级清单做成**机读表**（新增一份 JSON，随 `ui_tools/` 走），`html_to_json` 返回体的 `downgrades[]` 直接引用它 | 返回体 `downgrades[]` 与机读表逐条一致；用例断言 |
| **P1-5** | M3 | `check_all` 与 `ui_compile` 两份 json 侧实现并存（T1.4 只完成"判据同源"，代码未合并） | `REMEDIATION-UI-PIPELINE.md` T1.4 🟡；`ui_compile` 报告里 `delegated` 点名 | 按 T1.4 收口：`check_all` 的 json 侧检查改调 `ui_compile`（唯一实现），先定「注册表声明字段 vs check_all 硬编码字段表」谁说了算 | 全仓工程 json 跑两边结论一致（逐条文本）；`delegated` 里不再点名 |
| **P1-6** | M3 | `check_all` 37 项里 #21/#34 实际跑不到（委派脚本不在仓内） | `tools/qa/` 在本检出不存在；`aa_audit.py`/`contrast_check.py` 全树搜不到 → 该项 NOTE 跳过（而 `corner_audit`/`alpha_bg_audit`/`zero_color_audit` 已在 `ui_tools/` 内，可真跑） | 补 `aa_audit.py` / `contrast_check.py`（或明确降级为"未覆盖"并在交付结论里点出） | 要么 #21/#34 真跑出 PASS/FAIL，要么交付结论显式写「这两项未覆盖」 |
| **P1-7** | M4 | `json2img` 覆盖矩阵：`implemented 4 / approximate 4 / unsupported 2`，近似项没有收敛计划 | `--coverage` 实测输出 | 给 4 条 `approximate` 各定"收敛到 implemented 的真机判据"（否则永远停在近似） | 矩阵里每条 `approximate` 都带 `plan`（怎么验、验到什么程度算 implemented） |
| **P1-8** | M5 | 确认稿闸门已硬，但**改版路径**仍是软提示，容易漏 | `REMEDIATION-UI-PIPELINE.md` §7 风险表「只对新项目/新需求硬；改版路径软提示」 | 改版路径也加"出稿提醒 + 无稿时返回体显式 `confirmNeeded`"（不拦但记账） | 改版路径返回体带 `confirmNeeded=true`；用例覆盖 |
| **P1-9** | M7 | 字体裁剪脚本的默认源字库路径指向**本检出不存在**的目录 | `font_subset_by_project.py` 的 `DEFAULT_SRC` = `../FlyThings_mcp_open/components/fonts/...` | 改成仓内真源（`components/fonts/`）+ 找不到时给可执行提示（现有行为是 rc=2） | 不传 `--src` 也能跑通；或在返回体里给出仓内正确路径 |
| **P1-10** | M8 | 真机抓屏"通道选错 = 抓不到帧"是最高频失败原因，但错误提示未收敛成**单条**可执行动作 | `device_screenshot.py` 头「这是该工具最常见的失败原因」 | 失败体里按平台给**唯一推荐通道 + 一条命令**（而不是列出所有可能） | 失败返回体含单条 `nextAction`；用例断言 |
| **P1-11** | K | 知识页 `status`/`verified_at` 的老化没有"到期自动提醒"闭环 | `knowledge/` 下 121 篇 md（`check_kb.py` 自报：篇数 116、`verified` 5、待补证据 100），frontmatter 带 `stale_days`（如 180） | `kb_health.py` 增加"已过期未复核"清单并接到交付前体检 | 过期清单可复现；门禁或报告里点名 |

### 7.3 P2 —— 长线收口

| # | 模块 | 事项 | 依据 |
|---|---|---|---|
| P2-1 | M2 | QML / Qt `.ui` / Android XML / Vue 前端只写 A 层（IR），至少一条端到端样例经同一发射链 + `ui_compile` 无 error | `ui_entrypoints.json` 里 5 个 `planned` 入口 + `REMEDIATION-UI-PIPELINE.md` T5.4 |
| P2-2 | M4 | 跨源 A/B 黄金样例（HTML vs LVGL 同一视觉目标） | `REMEDIATION-UI-PIPELINE.md` T4.3 ⬜ |
| P2-3 | M2/M5 | 确认稿自动回传（编辑器页面 → json 的回传通道） | `ui_editor.py`「页面内没有回传通道，必须复制粘贴」 |
| P2-4 | 全局 | 常驻预算纪律：要加常驻内容必须先腾地方（当前 `budget` 由门禁对账） | `op_spec.json` 的 `budget.note` |
| P2-5 | M3 | `ui_compile` 规则集 v1（22 条）与 `renderContract` 9 条的边界：哪条该进编译器、哪条留给资产审计，写成一张归属表 | `ui_compile.py` 头 + `check_render_contract_coverage.json` |

---

## 8. 责任边界与禁止事项（跨模块）

| 边界 | 内容 |
|---|---|
| **入口不排他，产物排他** | 从哪种源出发都行（HTML / 块库 / 直写 json / 迁移），但**产物**必须由共享发射链产出，或经 `ui_compile` 无 fatal/error 才算成立 |
| **A 前端 / B 映射 / C 发射** | A 只把源读懂（读懂多少要如实报）；B 只做控件对应（索引不是引擎）；C 只把 IR 变成合法 json（**不解析源语言、不画图**） |
| **D 出图 / E 渲染判定 / F 验收** | D 只管出图准（图==盒、α=覆盖率）；E 只管画得对不对并**如实记账**盲区；**只有 F 才下结论** |
| **归因三分** | ① 前端丢语义 → 改前端（做不到就登记 `downgrades`）；② 发射层字段/换算错 → 改 fill 规则（先改规格）；③ 渲染器不覆盖或语义错 → **只有这一类才动 `json2img`**，且要同时更新 `renderContract` 行或 `unsupported` + 基线 + 真机对齐证据 |
| **禁止的两类"修复"** | `⛔EXCUSE`（把缺陷登记成"已知代价/豁免"了事）、`⛔TWEAK`（调阈值/容差/采样算子/档位把观感修过去）—— 判据一句话：**改动之后，规格里多了一条"该怎么做"吗？** |
| **永远的真机真相** | 离散两档（编译式验收、离线渲染判定）都替代不了 `device_screenshot` + `ui_visual(diff)` |

---

## 相关（不要在本文件里找细节，去这些真源）

- 界面产物管线口径（**模块 I/O 契约的规范出处**）→ `knowledge/devflow/ui-pipeline-spec.md`
- 入口登记（有哪些入口 / 状态 / 校验链 / 证据）→ `knowledge/devflow/ui-entrypoints.md`（真源 `ui_entrypoints.json`）
- 字段与必填键唯一真源 → `ui_tools/ui_schema.json`（op `flythings_ui_schema`）
- op 契约真源 → `op_spec.json`；开发流程原子 → `flow_spec.json`
- 渲染语义规格（离线所见即所得）→ `knowledge/devflow/wysiwyg-render-spec.md`
- json 与 ftu 的关系 → `knowledge/devflow/ftu-json-pipeline.md`
- 整改台账（任务分解，**不是规范**）→ `REMEDIATION-UI-PIPELINE.md`
- 本仓设计规范（写知识/判据前必读）→ `DESIGN_SPEC.md`
