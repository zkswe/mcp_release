---
id: devflow-quickstart
title: 🚀 新手快速上手（装完验证后的第一句话 + 四条路径 + 最小闭环）
category: devflow
status: review
confidence: manual
verified_at: 2026-10-02
stale_days: 180
origin: total
source: 2026-10-02 A3 任务：补 onboarding 缺口（装完验证后没有"下一步"指引）
needs_evidence: true
platforms: []
tags: [新手, 快速上手, quickstart, 第一句话, 装完了干什么, 下一步, 入门, 四条路径, 最小闭环, 第一周坑位, 新项目怎么开始, 教程, onboarding, 从哪开始]
evidence: []
---
# 🚀 新手快速上手（装完验证后的第一句话 + 四条路径 + 最小闭环）

> 检索导引：问「装完了接下来干什么 / 第一句话对 AI 说什么 / 新手从哪开始 / 怎么快速上手 / 有没有教程 / 拿到这个 MCP 第一步做什么 / 第一周容易踩什么坑」→ 本文（onboarding 总入口）；具体流程细节不在本文，逐一指向已有权威文档。
> 检索词（用户问法与 AI 检索都命中这里）：新手 / 快速上手 / quickstart / 入门 / 教程 / onboarding / 第一句话 / 装完了 / 下一步 / 从哪开始 / 怎么做第一个项目 / 四条路径 / 最小闭环 / 第一周坑位 / 我想做一个面板 / 帮我看看这个工程。
> ⚠️ 本文只做**导航**：每一条路、每一个坑都指向已有文档，**不要在本文复制那些文档的内容**（防双份漂移）。

## 现象：装完验证通过，然后呢

README 装到「3) 验证」（问 AI「MCP 版本是多少」返回 `flythings-kb-open <版本>` + 47 个工具）就结束了。
新用户（和带新用户的 AI）此刻的典型卡点是：**工具清单看到了，但不知道第一句话该说什么、
自己的情况该走哪条路**。本文就是这一步的答案：先按「四条路径」对号入座，再照「最小闭环」
跑通第一个界面，最后用「第一周坑位 top5」自查。

## 装完后的第一句话（直接照说就行）

| 你的情况 | 对 AI 说的第一句话 | 触发什么 |
|---|---|---|
| 有个想法，从零开始 | 「**我想做一个 XXX 面板**」（XXX = 你的产品，如温控器 / 考勤机 / 充电桩屏） | prototype-flow 九步流程（功能拆解 → 线框确认 → 美化 → 转换） |
| 手里已有设计稿 | 「**按这个设计稿帮我做界面**」（附上 UI 图 / HTML 原型 / 布局文件） | 先按稿还原出**确认稿**，确认后才建工程 |
| 从别的框架迁移 | 「**把小程序 / LVGL / Android 的这个界面迁到 FlyThings**」 | 先 platform-translate 口径 + `flythings_map_control` 逐个控件映射 |
| 已有 FlyThings 工程 | 「**帮我看看这个工程**」（给出工程路径） | `flythings_validate_project` 先读工程、做规范全检，再谈改动 |

> 客户端支持 MCP prompt 的话，也可以直接唤起 `flythings-new-project`（等价于第一条路径的
> 结构化版）；其余 prompt：`ui-from-prototype` / `ui-verify` / `deploy-debug` / `package-deps`。

## 四条典型路径（一句话入口 → 先做什么 → 权威文档）

| # | 路径 | 第一步（硬规则） | 去哪看细节 |
|---|------|------------------|-----------|
| ① | 从零想法 | **不许直接建工程**：先走 prototype-flow（功能拆解 → 页面树 → HTML 线框图 → 用户确认 → 3+ 套美化 → 确认 → 转换） | `knowledge/devflow/prototype-flow.md` |
| ② | 有设计稿 | **跳过线框轮**，但必须先确认平台 + 物理分辨率 + 方向，按稿还原 → `flythings_ui_preview` 出确认稿 → 用户确认后才 `flythings_create_project`；分辨率不一致走适配 + `scale_audit.py` 审计 | `knowledge/devflow/prototype-flow.md` 文末「已提供设计稿时」 |
| ③ | 迁移其他框架项目 | 源界面控件逐个过 `flythings_map_control`（命中 L1/L2 直接拿 json 片段），视觉换算与铁律先立规矩，再按四阶段路线推进 | `knowledge/devflow/platform-translate.md` |
| ④ | 改已有工程 | 先 `flythings_validate_project(project_root)` 读工程 + 规范全检；改布局同样要出**确认稿**（`.confirm.html`）给需求方确认，别拿推真机当确认手段 | `knowledge/devflow/ui-layout-verify.md` §0 |

四条路径共同的铁律：**平台 + 分辨率没确认，不许开始建工程 / 写逻辑**（2026-09-21 口径）。

## 最小闭环示例（路径①，从零想法到真机验收）

目标：把「我想做一个 XXX 面板」跑成设备上看得见的界面。每步给出对应 op：

```
① 想法 ──「我想做一个 XXX 面板」──→ AI 走 prototype-flow 拆功能、出页面树
② 线框确认 ── wireframe.html（单 HTML 多 .screen，浏览器打开）──→ 用户确认「做什么」
③ 转换 ── flythings_html_to_json ──→ ui/*.json（唯一真相源；N 屏必须出 N 页）
④ 建工程 ── flythings_create_project(platform, resolution) ──→ 平台+分辨率与确认过的一致
⑤ 编译推送 ── flythings_build_ui_flow(project_root) ──→ pack → build → 探测设备 → launch
⑥ 真机验收 ── flythings_device_screenshot ──→ 抓屏看像素（真机像素才是最终真相）
```

走完这 6 步你就拥有了：一个能跑的工程 + 一套可复用的「确认稿 → 转换 → 验收」节奏。
之后加页面 / 改布局都是同一节奏的循环（改 json → 确认稿 → pack → 截图验收）。

## 第一周坑位 top5（都指向已有文档，别在本文找答案）

| # | 坑 | 怎么一眼发现自己在坑里 | 去哪看 |
|---|----|------------------------|--------|
| 1 | **手改 ftu / 拿 ftu 当源**| 你在用编辑器打开 `.ftu`，或改了 ftu 期望界面变 | json 是唯一真相源，ftu 是 pack 产物；`knowledge/devflow/ftu-json-pipeline.md` |
| 2 | **改了 json 忘 pack**| 界面上看不到刚改的东西，先别怀疑代码——看 json/ftu 时间戳 | `flythings_build_ui_flow` 自带时间戳防呆；同上篇 |
| 3 | **界面中文变方块/缺字**| 真机上英文正常、中文空白或豆腐块 | `flythings_build_ui_flow` 默认做字体体检 + 缺中文自动投递；`knowledge/devflow/custom-font-config.md` |
| 4 | **设备上跑的还是旧版**| 推完了界面没变，`build_ui_flow` 返回体 `staleOnDevice=true` / `deviceSync` 不一致 | `knowledge/devflow/deploy-consistency-check.md`（新库旧界面对账） |
| 5 | **以为模板工程没有 json 可改**| 想改 HelloWord 模板布局却找不到 json | 2026-10-02 起 7 个平台模板自带 `ui/main.json`（由模板 ftu 反解析入库），直接改 json 再 pack；`knowledge/devflow/ftu-json-pipeline.md` §1 |

## 怎么一眼发现走错了路

- AI 听完一句话需求**直接**`flythings_create_project` / 写业务代码，没出线框图 → 违反路径①硬规则，回到 prototype-flow。
- 给了设计稿，AI 没确认平台和分辨率就动手 → 违反路径②硬规则，先停下来对齐。
- 迁移时 AI 凭记忆背「某框架某控件对应某控件」→ 让它过 `flythings_map_control` 拿映射表，不背散文。
- 改已有工程时 AI 反复「编译 → 推真机 → 你看下」→ 让它出 `.confirm.html` 确认稿，按标注指位沟通。
