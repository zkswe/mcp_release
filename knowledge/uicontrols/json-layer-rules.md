---
id: uicontrols-json-layer-rules
title: 控件层级规则（容器 → 子内容矩阵，双源实证）
category: uicontrols
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [控件层级问题检讨, ftu unpack 反解, py #2 层级合法性检查, layer_problems, 自动校验, 控件层级, 嵌套, 容器, 父子, 结构键, 坐标负值, 重启后控件跑位, 从右下算, 拖拽夹取边界, 落盘位置读回, 控件跑位]
evidence: []
---
# 控件层级规则（容器 → 子内容矩阵，双源实证）

> 检索导引：问「控件这样嵌套合不合法 / window 里能放什么 / pagewindow 为什么只装 window / 层级报错（check_all #2）/ 先看 json 做遮挡审计 / **重启后控件位置跑了 · 坐标出现负值 · 拖动夹到什么边界**」→ 本文。
> 2026-09-08 沛哥要求「控件层级问题检讨」产出。**方法**：扫描 86 个真实 json（`projects/SampleUI-New/ui/1024x600` 42 + `projects/LearningProject/basedemo-new_z20_1024_600` 35 demo/44，ftu unpack 反解），统计每个容器类型的直接子内容分布——**零越界样例**，基线全绿。
> **落地**：check_all.py #2 层级合法性检查（_layer_problems）自动校验；html2json 嵌套栈生成天然合规。
> 检索词：控件层级/嵌套/容器/父子/结构键/subItem/radiobuttons/页面 window/坐标负值/重启跑位/从右下算/拖动夹取。

## 容器 → 直接子内容矩阵（实证次数）
| 容器 | 允许的直接子内容 | 实证 |
|------|----------------|------|
| 根层 | 全部 21 类控件均允许 | 各类均有根层样例 |
| **window** | **万能容器**：textview/button/edittext/listview/seekbar/**window(深嵌套)**/qrcode/digitalclock/slidetext/slidewindow 等全部控件类型 | textview 147 / button 128 / edittext 16 / listview 8 / seekbar 7 / window 5 / qrcode 2 / digitalclock 1 / slidetext 1 / slidewindow 1 |
| **pagewindow** | **只装 window**（页面叠放，同尺寸；代码 turnToNextPage 翻页） | window 3（basedemo 3 页） |
| **scrollwindow** | **只装 window**（滚动内容；**内层 window 的尺寸 = 滚动行程基准**（滚到不到底看它，不看 `dragMaxDis`） | window 1 |
| **listview** | 只走 **item**（行模板）→ 行内容在 `item.subItem[]`；**禁止平铺 __N 控件键** | item 100%（两源） |
| **radiogroup** | 只走 **radiobuttons[]**（每项带 id/caption，本质按钮） | basedemo |
| **slidewindow** | 只走 **items[]**（图标项 {colorTab/picTab/text}，非控件） | 两源 |
| **diagram** | 只走 **infos[]**（波形配置，非控件） | 两源 |
| **叶子控件 14 类** | textview/button/edittext/seekbar/circlebar/checkbox/slidetext/cameraview/painter/pointer/digitalclock/qrcode/videoview/imageanim：**不得含子控件** | 无越界 |

## 规则要点（违反即 check_all #2 FAIL）
1. **window 是唯一万能嵌套容器**：可 window 内嵌 window（无限深）、scrollwindow → window → 面板 window、pagewindow 页面 window 叠放、弹窗 = window(modal) 最后定义（Z 序最上层）。
2. **数组子结构归属固定**：`radiobuttons`→radiogroup / `items`→slidewindow / `infos`→diagram / `subItem`→listview.item——出现在别处 = 非法（如 button 带 radiobuttons）。
3. **结构容器不平铺**：listview/radiogroup/slidewindow/diagram 的直接子键只能是结构键（item/radiobuttons/items/infos）；直接写 `window__N`/`textview__N` 等控件键 = 非法（如 listview 里直接放 window）。
4. **pagewindow/scrollwindow 必须含 window 子页面**，且只装 window（装 textview 等 = 非法）。
5. **叶子控件不能生子**（textview 内含 button 等 = 非法）。
6. Z 序与层级正交：json 书写顺序 = 层叠顺序（后定义在上层）；层级（谁嵌谁）由结构键/嵌套决定。
7. **层叠顺序决定谁收到触摸**（沛哥 2026-09-10）：上层控件若 `touchable: true` 会**先截走触摸**，下层即使 touchable=true 也收不到——
   「点了没反应」优先查是不是被上层（常是全屏透明面板/遮罩 window）挡住了；要穿透就不要让上层 `touchable: true`
   （注意：radiogroup 必须 true，见 `knowledge/uicontrols/touch-events.md`）。

## 坐标负值 = 从右/下算（**「重启后控件跑位」的根因**）

**现象**：可拖动控件**当次拖动看着完全正常**，但**重启（或重新读落盘）后跑到屏幕另一侧 / 贴右贴下**。
分水岭就在这：是**重启后跑位**，不是当次就跑位 —— 当次跑位是夹取/刷新 bug，重启跑位才是本坑。

**根因**：`LayoutPosition` 里**负的绝对坐标不是「负偏移」，引擎把它当成「从右/从下算」的 bottom/right 值**
（`x = -20` 语义 =「距右边 20」，不是「左边界为 -20」）。于是拖动/持久化时写进负值的那一次，
落盘再读出来就被摆到另一侧。

**一眼发现**：看**落盘的 json / `/data` 配置值里出现负坐标**（正常界面绝对坐标应 ≥ 0）；
配合「重启后才跑位」的现象即可坐实。注意：静态像素/遮挡审计（`layout_audit`）**查不出这类**——几何本身合法，要看**值**。

**正确做法**（真机问题单 09251751-8，钟工 2026-09-25 口径）：
1. **拖动/夹取时左、上边界夹到绝对 0**：调参量 `dx/dy` 的下界取 `lo = -dl / -dt`（即取负的基准左/上），
   保证最终绝对坐标 `dl + dx >= 0`；**不许「可以推出去大半」**（那就是负值来源）。
2. **右下至少留 `SS_EDGE_KEEP`（40px，或控件 1/3 尺寸，取小）在屏内**：`hi = SCR - keep - base`。
3. **落盘读回时 `-1` / 越界一律视为「未设置」**，走默认位置——**历史脏数据（已经写进去的负值）因此自动失效**，不用清库。

**判据**：夹取后恒有 `dl + dx >= 0 && dt + dy >= 0`（**绝对坐标绝不出现负值**）；
读回分支 `x < 0 || x > SCR` → 默认位置；落盘值扫一遍无负数即过。

**证据（真工程只读，行号已实读核对）**：
- `projects/SmartPanel_HA/src/logic/mainLogic.cc:598-612` `ssLoadLayout()`：`-1/越界 视为未设置（用默认位置）；负值一律当未设置（历史脏数据，见问题单 09251751-8）`。
- `projects/SmartPanel_HA/src/logic/mainLogic.cc:614-635` `ssClampX/ssClampY`：注释写明「**绝不允许绝对坐标出现负值** —— LayoutPosition 里负值会被引擎当成「从右/下算」的 bottom/right 值，重启后控件位置就跑了」，故左/上夹到绝对 0（`lo = -dl / -dt`）。
- 对应写入点：`mainLogic.cc:591-596` `ssSaveGroupPos()`（落盘 `dl+dx / dt+dy`）；应用点 `ssApplyGroup()`（`:584-587`，`setPosition(LayoutPosition(dl+dx, dt+dy, dw, dh))`）。
- 口径时间：2026-09-24 现场夹取口径 → 2026-09-25 追加负值硬约束；本文 `verified_at` 维持 2026-09-29。

检索词：重启后控件跑了 / 位置跑到另一边 / 控件位置重置 / 坐标负值 / 负坐标 / LayoutPosition 负值 / 从右下算 / bottom right 语义 / 拖动跑位 / 落盘位置读回 / 夹取边界。

## 相关
- 子结构字段全集（item 17 键含 position / subItem / infos 含 visible）见 `knowledge/uicontrols/json-field-mandatory.md`
- ★ **scrollwindow 内容的尺寸决定行程（不是 dragMaxDis）；加行忘加高内层 window = 末尾滚不到** → `knowledge/uicontrols/scrollwindow-layout-checklist.md`
- window 嵌套/弹窗结构见 `uicontrols/window` wiki；页面级多全屏 window 应拆多 Activity（非同一 json 堆叠）

## 静态遮挡审计（v0.27.92：先看 json，别一上来截图）

用户说「控件被盖住 / 点不到 / 位置不对 / 谁挡着谁」时先调 `flythings_layout_audit(project_root[, page])`，
纯几何 0 token，返回 `pages[].findings[]`：

| kind | 含义 | 典型修法 |
|------|------|----------|
| `fullscreen_layer` | 整屏层（position == resolution）；`touchable:true` 会吞整屏触摸 | 隐藏页用 `visible:false`；遮罩只盖需要拦的区域；装饰加 `touchPass:true` |
| `touch_steal` | **同层更早定义**的 `touchable` 控件完整覆盖它 → 触摸按定义顺序先被拿走 | 遮挡物改 `touchable:false + touchPass:true`，或挪成子级/删掉 |
| `covered_interactive` | 上层 `touchable` 控件完整盖住可交互控件 | 挪 position / 缩小遮挡层 |
| `pass_through_missing` | 装饰件 `touchable:false` 但没 `touchPass:true`，与可点控件重叠 | 补 `touchPass:true` |
| `overlap` | 同层两个盒子相交（后者在上层） | 确认是否故意叠放 |

判据回顾：**z 序 = json 书写顺序（后定义在上层）**；**触摸按定义顺序先命中先定义的可点控件**（F133 实测：
遮罩 button 压住卡片 window 时卡片内按钮点不动 → 卡片扁平化到控件层、排在遮罩之后）。
改动前后对比用 `flythings_ui_visual(action="diff")`；视觉样式（颜色/字体/切图）仍要截图。
检索词：控件被遮挡 / 点不到 / 谁挡着谁 / 控件覆盖 / 重叠 / 层级 / z 序 / touchPass / layout_audit。
