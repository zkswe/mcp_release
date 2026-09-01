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

## 边界澄清：不影响什么（2026-09-01 沛哥确认）

本规则只管「控件用法/字段/API 知识从哪来」，**不限制需求理解与逻辑参考**：

- ✅ **HTML 理解/转换不受影响**：HTML/CSS 是通用 Web 标准，不是 GUI 框架控件知识；
  html2json 转换走 MCP 内置 HTML_SUBSET 规范（div.input→edittext、data-hint→hintText 等映射已在 MCP 内），照常工作
- ✅ **参考其他框架代码的「业务逻辑」不受影响**：Android 工程/其它代码里的业务流程、数据结构、算法
  （MQTT 收发、列表数据组装、定时逻辑等）属于需求理解，可以借鉴参考
- ❌ 受影响（规则本意）：把其他框架的**控件字段名/API**直接套用到 FlyThings——
  如 `android:hint`→FlyThings 是 `hintText`、RecyclerView.Adapter→`obtainListItemData_XXX` 回调、
  `android:gravity`→`alignment` 位标志；控件实现细节必须查 MCP/官方

> 一句话边界：**需求逻辑随便参考，控件实现只查 MCP/官方。**
