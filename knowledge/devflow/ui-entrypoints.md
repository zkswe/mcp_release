---
id: devflow-ui-entrypoints
title: 界面产物入口登记（有哪些入口 / 各自档位·状态·校验链·证据·已知限制）
category: devflow
status: review
confidence: manual
verified_at: 2026-10-05
stale_days: 180
origin: derived
source: 派生自仓库根 ui_entrypoints.json（v1，updated 2026-10-05）
needs_evidence: true
platforms: []
tags: [入口登记, 界面入口, 多个入口怎么选, 手写入口, 迁移入口, 校验链, 入口状态, html 原型, 块库 spec, 直写 json, 入口限制]
evidence: []
---

# 界面产物入口登记（有哪些入口 / 各自档位·状态·校验链·证据·已知限制）

> 本文件是派生：真源 = `ui_entrypoints.json`，不要手改；改真源后重跑生成器即可。

> 检索导引：问「**HTML 是不是唯一源** / 除了写 HTML 还有哪些入口 / 某个框架（LVGL·Qt·QML·Android XML·小程序·Vue）能不能迁 / 哪些入口能用、哪些只是计划 / 产物要过哪些校验」→ 本文；**口径（为什么、怎么判）见 `knowledge/devflow/ui-pipeline-spec.md`**。

> 权威口径：界面产物管线口径的唯一真源（有哪些入口、各自档位/状态/校验链/证据/限制）；口径（为什么、怎么判）见 knowledge/devflow/ui-pipeline-spec.md。任何入口的产物都必须由共享发射链产出，或经编译式验收（ui_compile）无 fatal/error 才算成立。

> 状态口径：`active` = 现在就能用，且已登记非空 validator_chain 与 evidence ｜ `planned` = 尚未实现（或只有人工路径）：如实登记，不许当『已支持』用 ｜ `unsupported` = 已明确不做或平台不支持（写明原因）

## 档位（三档，各自约束）

| 档位 | 约束 |
|---|---|
| default（缺省） | 缺省前端：需求 → 线框/风格稿（受限 HTML）→ html2json → ui/*.json。线框/风格稿是客户确认载体 |
| allowed（允许） | 允许但不排他：直接按 schema 写 json / 块库 spec 组装的，产物必须等价并过同一套校验链 |
| migration（迁移） | 迁移入口：前端只许产 IR，映射走 flythings_map_control，未实现的如实标 planned |

## 入口清单（10 个）

| 入口 | 语言 | 档位 | 状态 | 转换 op | 校验链 | 证据 | 已知限制 |
|---|---|---|---|---|---|---|---|
| `figma-html`（Figma 设计稿（导出 HTML 后走缺省前端）） | Figma → HTML（受限子集） | default（缺省） | active（可用） | `flythings_html_to_json` | `ui_compile`、`check_all`、`json2img`、`device` | 用例：`tests/test_html2json_multiscreen.py`、`tests/test_html2json_radius.py`<br>产物：`ui_tools/HTML_SUBSET.md` | 必须先导出成 HTML 受限子集原型（线框/风格稿）再转，不直接读 .fig<br>导出稿要按分页落地清单核屏数（screensDetected == pagesProduced == N） |
| `html-prototype`（HTML 受限原型） | HTML/CSS 子集 | default（缺省） | active（可用） | `flythings_html_to_json`、`flythings_ui_preview` | `ui_compile`、`check_all`、`json2img`、`device` | 用例：`tests/test_html2json_multiscreen.py`、`tests/test_html2json_radius.py`、`tests/test_html2json_ss.py`、`tests/test_html2json_seekbar_css.py`、`tests/test_preview_pages.py`<br>真机：Z21 1024x600、F133 1280x800 | HTML 受限子集（不是浏览器）：写法与多屏形态见 ui_tools/HTML_SUBSET.md<br>多屏落地硬判据：screensDetected == pagesProduced == 设计稿屏数 N，不等即 success:false |
| `ui-blocks-spec`（界面块库 spec（组装器）） | spec.json（块定义 + 相对约束） | allowed（允许） | active（可用） | — | `check_all`、`json2img`、`device` | 用例：`tests/test_ui_schema.py`<br>产物：`templates/ui_blocks/examples/settings_1024x600/check_all.log`、`templates/ui_blocks/examples/nav_320x240/main.render.png` | 24+ 块定义（templates/ui_blocks/），覆盖不到的能力不硬造（自绘/动图等走 components/ui_v1）<br>块内 glyph 尺寸下限 24px：小屏靠省图标降级，不缩图标<br>图标唯一来源 = components/icons 资产库，禁自绘/禁 emoji 字体兜底 |
| `ui-json-schema-first`（按 schema 直写 ui/*.json） | ui/*.json（字段来自 ui_schema.json） | allowed（允许） | active（可用） | `flythings_ui_schema`、`flythings_layout_audit`、`flythings_verify_assets` | `ui_compile`、`check_all`、`json2img`、`device` | 用例：`tests/test_ui_schema.py`、`tests/test_layout_flow.py`<br>产物：`flow_spec.json` | 字段/必填键必须来自 flythings_ui_schema，不许凭记忆写<br>跳过 HTML 不等于跳过验收：产物仍须过同一套校验链 |
| `lvgl-c`（LVGL C 代码 → ui json（translate_ui）） | LVGL C | migration（迁移） | active（可用） | `flythings_translate_ui`、`flythings_map_control` | `ui_compile`、`check_all`、`json2img`、`device` | 用例：`tests/test_translate_ui.py`<br>产物：`translate_tools.py`<br>真机：Z21 1024x600 | 只识别 LVGL 子集：识别形态/读法/已知限制见 knowledge/devflow/translate-ui-lvgl.md<br>未识别形态走 flythings_map_control 逐控件手工搭，不静默略过 |
| `android-xml`（Android 布局 XML 迁移） | Android layout XML | migration（迁移） | planned（未实现） | `flythings_map_control` | — | — | 当前只能逐控件走 flythings_map_control + 手工搭 json（无前端转换器） |
| `miniprogram-wxml`（小程序 WXML/WXSS 迁移） | 小程序 WXML/WXSS | migration（迁移） | planned（未实现） | `flythings_map_control` | — | — | 当前只能逐控件走 flythings_map_control + 手工搭 json（无前端转换器） |
| `qml`（QML / Qt Quick 迁移） | QML | migration（迁移） | planned（未实现） | `flythings_map_control` | — | — | 当前只能逐控件走 flythings_map_control + 手工搭 json（无前端转换器） |
| `qt-ui`（Qt .ui / Qt Widgets 迁移） | Qt .ui (XML) | migration（迁移） | planned（未实现） | `flythings_map_control` | — | — | 当前只能逐控件走 flythings_map_control + 手工搭 json（无前端转换器） |
| `vue`（Vue（含 uni-app 类）迁移） | Vue SFC / 模板 | migration（迁移） | planned（未实现） | `flythings_map_control` | — | — | 当前只能逐控件走 flythings_map_control + 手工搭 json（无前端转换器） |

> 校验链里的 `ui_compile`（编译式验收）**尚未实现**（见 `REMEDIATION-UI-PIPELINE.md` WS-1）：登记它表示"该入口的产物将来必须过它"，**现在还没过**。

## 相关

- 口径唯一出处（三档判据 / 入口分级 / 模块契约 / 差异归因）→ `knowledge/devflow/ui-pipeline-spec.md`
- 迁移方法论（四阶段 / 降级 D-xx / 双平台）→ `knowledge/devflow/platform-translate.md`
- 控件级对应（带可直接粘的 json 片段）→ op `flythings_map_control`
