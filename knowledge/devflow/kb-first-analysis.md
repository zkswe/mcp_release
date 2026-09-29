# 开发先检索铁律：AI 分析优先用 MCP 知识库，禁止盲试/猜测

> 检索导引：问「该先检索还是先试 / 检索命中不准怎么办 / 查不到是不是没收录 / 该拿什么关键词搜」→ 本文（先检索后动手铁律）；允许检索哪些来源见 `uicontrols/retrieval-boundary.md`。
> 沛哥定规（2026-09-07）。背景：查「V85x 如何切换 USB OTG」时检索命中 Z21 通用文档、
> v85x 专项知识查不到 → 根因：检索接入的是旧服务/检索策略偏（已修复 v0.17.0）。
> 借此立规：**AI 做 FlyThings 开发，先检索分析，禁止先试错。**

## 适用范围

所有 FlyThings 开发任务：写 UI/布局/逻辑、查控件字段/API/回调、编译报错、平台差异、
方案分析、参考代码定位。

## 铁律（顺序不可反）

1. **动手前先检索**：`flythings_knowledge_search`（MCP 知识库 = wiki 官方文档 + knowledge/ 实践文档）
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
6. **跨平台硬件操作必须先给对照/问平台**（沛哥 2026-09-07 补）：USB OTG/ADB/U盘 切换、**host 外设接入
   （U盘读不到/挂载点、USB 摄像头、键鼠）**、主从切换、GPIO、串口、路径类问题，用户没指定平台时
   （V85X/T113/Z21 路径不同）→ 检索命中 knowledge/hardware/usb-otg-switch.md 之类的对照文档，
   回答给**多平台对照表 + 请用户确认平台**，禁止默认按检索命中的第一个平台答
   （v85x 文档块多常霸榜，不代表用户用的是 V85X）；客户场景话术统一按该文档的
   「USB HOST 外设接入」节（U盘→/mnt/usb1|usbotg + MountMonitor、摄像头→v85x/uvc、键鼠未收录不猜）。

## 原因

FlyThings 是私有框架（easyui/ftu/json 布局），字段/回调/坐标系与其他框架不对应；
knowledge/ 是沛哥与多个实测项目沉淀的实践知识，比通用猜测可靠。

## 检索质量（v0.27.94 起，钟工「检索质量优化」）

检索链路 = **向量（bge-small-zh）+ BM25 两路 RRF 融合**，外加三道「一次命中」保障：

1. **文档侧**：权威文档顶部写清「检索命中条件」（把真实问法/同义词列全）；结论集中在短节
   （长 chunk 的向量会被稀释——「一句话/速查」类短节才能吃住口语问法）；**同一主题不要在第二篇文档里写重复章节**，
   改写成一句指针（否则第二篇会抢走 top-1，AI 拿到的是不完整的那一份）。
2. **实现侧**（`rag_search.py`）：
   - **专名（rare term）优先重排**：查询里的英文控件名（≥4 字符、全库 df ≤ 2%）命中的片段提前——
     向量路对英文专名几乎不敏感，只能靠这一步抢回来（实测：`QTimeEdit`/`LISTWHEEL`/`NumberPicker` 类问法
     top-1 从 9/12 → 12/12）；
   - **BM25 中文口语别名扩展**（滚轮 → `wheel`/`roller`、时钟盘 → `timepicker`/`dial`…）：
     只为吃到 BM25 的「命中文件名/目录名 idf×2」权重；
   - 两路都做专名重排（降级 BM25 的机器上行为一致）。
3. **回归门禁**：`python scripts/check_retrieval.py`（16 条真实问法 + 11 条与主题无关的对照组；
   模型缺失自动降级 BM25）已接入 `scripts/check_consistency.py`。**改知识文档/改检索代码后必须跑**——
   本轮实测：改则 top-1 9/16 → 16/16，对照组同时 7/11 → 9/11。

排查顺序：先看命中文档对不对（path）→ 再看 `quality`（ok / low_confidence / no_hit）→ 都没命中才去翻目录或问人。
