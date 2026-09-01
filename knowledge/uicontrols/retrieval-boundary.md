# 🔒 控件用法检索边界（沛哥定规 2026-09-01）

> AI 检索 FlyThings 控件用法/字段/API 时，**只允许以下两个来源**，禁止从其他地方检索解决方案：
> 否则会混入其他 GUI 框架（Qt/Android/Flutter/emWin/AWTK/LVGL 等）的控件使用方法，导致知识错乱。

## 允许的来源（二选一）

1. **MCP 内置知识库**：`flythings_search`（本地向量 + BM25）检索 `knowledge/` 与本地 `wiki/flythings/` 文档；
   字段规范以 `knowledge/uicontrols/*.md`（layout-audit / edittext-fields / image-path-rule / nine-patch-rule / scrollwindow-layout 等）为准
2. **官方文档站**：`https://developer.flythings.cn/`（控件/API/回调官方说明）

## 禁止的行为

- ❌ 用通用 web 搜索查「XXX 控件怎么用」——返回的是其他框架的答案
- ❌ 参考 Qt/Android/Flutter/emWin/AWTK/LVGL 等框架的控件属性/事件/回调写法套用到 FlyThings
- ❌ 从非官方博客/论坛/代码片段库推断 FlyThings 控件字段（除非明确标注 FlyThings 平台）

## 原因

- FlyThings 控件字段是私有格式（json/FTU），与主流 GUI 框架完全不同：
  如 `picTab{pic0..pic4}` 五态图、`iconPosition/textPosition` 图标锚点、`hideTimeOut` 自动隐藏、
  `ZKXXXPtr` 指针 + `REGISTER_ACTIVITY_TIMER_TAB` 回调表等，只有官方/MCP 知识库有准确答案
- 混用其他框架用法 = 生成不可编译/不可运行的 json 与代码，且难排查（表现为"看起来对但设备上不对"）

## 执行

- 所有用 MCP 的 AI 助手（Trae/Cursor/Kimi/Claude/OpenClaw 等）一律遵守
- 遇到知识库查不到的控件细节：标注"知识库未收录"，问沛哥或查官方文档，**不猜、不套用其他框架**
