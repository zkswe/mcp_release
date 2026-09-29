---
id: devflow-ui-editor-usage
title: UI 可视化编辑器（ui_editor）用法与能力
category: devflow
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [显示隐藏控件, 预检红黄标 时命中, ` 的完整口径]
evidence: []
---
# UI 可视化编辑器（ui_editor）用法与能力

> ⚠️ v0.27.37 起 ui-visual 组已收口为一个入口：`flythings_ui_visual(action="editor" | "edit_apply" | "diff")`
> （旧名 `flythings_ui_editor` / `flythings_ui_edit_apply` / `flythings_ui_diff` 不再提供，调到会回 OP_RENAMED + 对应 action）。

> 检索导引：让用户自己拖控件 / 可视化改布局 / 拖完怎么回到 json / Alt 点穿透选中 / 属性栏字段 /
> 显示隐藏控件 / 预检红黄标 时命中。用途：`flythings_ui_visual(action="editor")` 的完整口径。

## 1. 定位（UI 微调闭环第二步）

① AI 生成/改 json 布局 → ② **本工具出编辑器给用户拖** → ③ 用户点「复制变更 JSON」→
④ `flythings_ui_visual(action="edit_apply")` 写回 json + pack ftu。

预览与设备同源（都来自 json），改完即所得。用户不用再嘴描述「往左一点」。

## 2. 输出

每个 json → `<项目>/ui/_edit/<name>.edit.html`（`ui` 目录递归扫描，兼容 `ui/<分辨率>/*.json`）。

- 单文件 HTML，图片 base64 内联（含 `audio/xxx.png` 这类带子目录的相对 resources 引用）
- 双击即用，无需服务器

## 3. 页面能力

- 点选 / 拖动 / 8 手柄缩放；方向键 1px（Shift 10px）；网格吸附 1/2/5/10
- **Alt+点** = 穿透选中下层控件（专治全屏透明 button 压住其它控件）
- 选中框左上 ✥ 绿块可拖 = 被遮罩压住的控件也能拖
- 控件列表可搜 key / caption；「显示隐藏」把 `visible:false` 的弹窗显示成虚线幽灵框
- 属性栏列出该控件**全部字段**：`text`（多行）/ `fontSize` / `colorTab.color0`（颜色拾取器）/
  `backgroundPic` / `picTab.pic0~pic4`（正常/按下/选中/选中按下/无效）/ `visible` / `touchable` …
  改完画布即时生效；`id` 只读（IDE 生成）
- 预检红黄标：图片尺寸 ≠ 控件尺寸（**红** = 图比控件大会被裁切；**黄** = 大控件配小图）、文本明显超框
- 深链接 `<name>.edit.html#button__2` 打开即选中该控件

## 4. 参数

- `output_dir` 缺省 `<项目>/ui/_edit`
- 变更 JSON 格式与写回安全（.bak / dry_run / 默认不 pack）见 `flythings_ui_visual(action="edit_apply")`

## 5. 相关

- 布局验收三段式与像素 diff → `ui-layout-verify.md`
- json 字段全集（属性栏列出哪些字段）→ `uicontrols/json-field-mandatory.md`
