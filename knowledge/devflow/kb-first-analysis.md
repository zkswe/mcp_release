# 开发先检索铁律：AI 分析优先用 MCP 知识库，禁止盲试/猜测

> 沛哥定规（2026-09-07）。背景：查「V85x 如何切换 USB OTG」时检索命中 Z21 通用文档、
> v85x 专项知识查不到 → 根因：检索接入的是旧服务/检索策略偏（已修复 v0.17.0）。
> 借此立规：**AI 做 FlyThings 开发，先检索分析，禁止先试错。**

## 适用范围

所有 FlyThings 开发任务：写 UI/布局/逻辑、查控件字段/API/回调、编译报错、平台差异、
方案分析、参考代码定位。

## 铁律（顺序不可反）

1. **动手前先检索**：`flythings_search`（MCP 知识库 = wiki 官方文档 + knowledge/ 实践文档）
   或官方 developer.flythings.cn。命中片段 → 按知识分析，禁止自己猜 API/字段/流程。
2. **禁止先试后查**：不许"先试编译/试回调/试 json 字段，报错再回来查"——顺序反了，
   浪费迭代。先检索、先读文档，再写代码。
3. **查不到 ≠ 没收录**：换关键词再搜（专名/缩写/中文口语/平台名），或直接读
   knowledge/ 对应目录（v85x/ uicontrols/ devflow/ esl/ t113-car/）。
   真的没有 → 标注「未收录」，翻本地参考工程（projects/、LearningProject/）或问沛哥。
4. **禁止套用其他 GUI 框架**（Qt/Android/Flutter/emWin/LVGL/AWTK 等）控件用法/API，
   也禁止解析 easyui 闭源库源码猜 json 字段/回调语义（详见 uicontrols/retrieval-boundary.md）。
5. **检索接入检查**：若检索结果明显缺失 practice 知识（knowledge/ 文档一条都不出），
   先确认 MCP 服务接的是 open 版（tools/FlyThings_mcp_open），不是遗留 rag 服务。
6. **跨平台硬件操作必须先给对照/问平台**（沛哥 2026-09-07 补）：USB OTG/ADB/U盘 切换、GPIO、
   串口、路径类问题，用户没指定平台时（V85X/T113/Z21 路径不同）→ 检索命中
   knowledge/hardware/usb-otg-switch.md 之类的对照文档，回答给**多平台对照表 + 请用户确认平台**，
   禁止默认按检索命中的第一个平台答（v85x 文档块多常霸榜，不代表用户用的是 V85X）。

## 原因

FlyThings 是私有框架（easyui/ftu/json 布局），字段/回调/坐标系与其他框架不对应；
knowledge/ 是沛哥与多个实测项目沉淀的实践知识，比通用猜测可靠。
