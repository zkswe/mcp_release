---
id: uicontrols-scroll-drag-interaction-spec
title: 滑动/拖拽手感规范：dragMaxDis / edgeEffect / autoRollback / rollSpeed
category: uicontrols
status: review
confidence: manual
verified_at: 2026-10-01
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [列表被拖出去, 越界回弹, 拖拽距离填多少, edgeEffect 怎么配, 列表滑动手感, 循环列表拖拽, 松手回弹, 拖动很卡, scrollwindow, pagewindow, slidewindow, 四个控件共用同一批滑动字段, 交互不合格, 1024x600, + 真实工程 json 统计, 取值只落 4 档]
evidence: []
---
# 滑动/拖拽手感规范：dragMaxDis / edgeEffect / autoRollback / rollSpeed

> 检索导引：问「dragMaxDis 填多少 / 列表被一次拖出屏 / overscroll 越界回弹 / edgeEffect·autoRollback·rollSpeed 怎么配 / 松手回弹手感」→ 本文（唯一权威口径，官方未收录）。
> 用户口语："内容滚不到底·最后一行看不到·拉不到末尾" / "边缘效果怎么设置·拖到头有什么反馈·有没有回弹/阻尼"。
> **检索命中条件**：问「dragMaxDis 什么意思 / 列表被拖出去 / 越界回弹 / 拖拽距离填多少 / edgeEffect 怎么配 / 列表滑动手感 / 循环列表拖拽 / 松手回弹 / 拖动很卡」→ 本文。
> 适用控件：`listview` / `scrollwindow` / `pagewindow` / `slidewindow`（四个控件共用同一批滑动字段）。
> 2026-09-12 需求方定规（起因：列表 `dragMaxDis` 按列表高度填 → 一次拖拽把整屏列表拽出去，交互不合格）→ 语义 + 取值规范入库。
> **证据**：SampleUI-New(1024x600) 42 json + basedemo 官方示例（listViewDemo-New / ScrollWindowDemo-New / PageWindowDemo-New / SlideWindowDemo）+ 真实工程 json 统计（取值只落 4 档，见 §5）。
> ⚠️ 官方文档站与 wiki **未收录**`dragMaxDis` 语义 —— 本文是唯一权威口径（实践知识）。检索边界见 `knowledge/uicontrols/retrieval-boundary.md`。

## 0. 一句话

`dragMaxDis` **不是**「内容能滚多远」，而是**手指越过内容边界后，内容还允许被继续拽出去的最大距离（越界拖拽上限 / overscroll）**。
行程（travel）由内容决定、**引擎自己算**（listview 按运行期数据、scrollwindow 按内层 window 尺寸、pagewindow/slidewindow 按页宽），**跟它无关**；
它只决定「拽到边界之后」那一段的手感。
**填成控件可视尺寸 = 允许整屏拖出 → 交互不合格。**

> ★ **2026-10-01 需求方核实修正（重要）**：**四个滑动控件（listview / scrollwindow / pagewindow / slidewindow）该字段语义完全一致 = 越界拖拽上限**。
> 本文此前把 scrollwindow/pagewindow/slidewindow 记成「填**行程值**（200 / 内容尺寸）」是**误读**，已作废——
> 差別只在「行程由谁决定」，不在字段语义。证据见 §5-1（官方 demo 与真机双反例）。
> **别再用 `dragMaxDis` 算行程/判「能不能滚/滚没滚到底」。**

## 1. 三个概念（先分清再填值）

| 概念 | 定义 | 由谁决定 |
|------|------|---------|
| **行程 travel**| 内容可滚动的总距离（**引擎自算**） | listview：`max(0, 项数×行高 − 可视高)`（运行期由数据决定）；scrollwindow：`内层 window 尺寸 − 视口尺寸`；pagewindow/slidewindow：`(页数−1)×页宽(高)`。**与 `dragMaxDis` 无关**|
| **越界拖拽 overscroll**| 滑到两端后还能被手指拽出去多远 | **`dragMaxDis`**|
| **停止位置 stop**| 松手后回弹/停靠到哪 | `edgeEffect`（0 无 / 1 拖拽回弹 / 2 渐隐）+ `autoRollback`（是否对齐整行/整页） |

⚠️ **四个控件字段语义相同，别混的是「行程由谁决定」**：

- `scrollwindow` / `pagewindow` / `slidewindow`：**填手感值**（基准 1024×600 取 50~200；demo 用 200）。
行程由内层 window 尺寸（scrollwindow）或页数（pagewindow/slidewindow）决定，**不要拿内容尺寸往这个字段里写**。
- `listview`：行程由运行期数据决定，**只能填手感值**，≈ ≤ 一行高（基准 50）。**禁止填列表高度。**
- 共同硬约束：**`dragMaxDis` 不得 ≥ 控件可视尺寸**（≥ 即越界能把整屏拽出去、露底）。

## 2. 取值规范（基准 1024×600）

| 场景 | 控件 | edgeEffect | dragMaxDis | autoRollback | 手感目标 |
|------|------|-----------|-----------|--------------|---------|
| 数据浏览列表（不用回弹） | listview | 0 | **0**| false | 到边界硬停，最干净 |
| 一屏内菜单/设置列表 | listview | 1 | **50**| true | 边界能拽出一点、松手对齐 |
| 循环选择器（月/日/时/分） | listview | 1 | **50**| true | 循环 + 轻微拖拽感（cycleEnable=true） |
| 长数据列表（滚动为主） | listview | 0 或 1 | **0 或 50**| false | 别开大，滚动本身已够长 |
| 滚动窗口（内容超高） | scrollwindow | 1 | **50~200**（基准屏高 8%~30%；480×480 取 40~60，实测 60） | — | 连续滚动 + 边缘反馈。**行程由内层 window 定，不写这里**|
| 整页翻页 | pagewindow | 1 | **200**| — | 翻页，rollSpeed 60 |
| 图标宫格滑动 | slidewindow | 1 | **200**| — | 翻页 + 图标按下态，rollSpeed 999 |

### 规则（硬约束）

- **R1 数量级**：`dragMaxDis` 一律取**手感值**—— listview ≤ 一行高（基准 50 @1024×600）；scrollwindow/pagewindow/slidewindow 50~200（基准 1024×600，demo 用 200）。**四个控件都不准填内容尺寸。**
- **R2 上限**：**四个控件一律禁止 `dragMaxDis` ≥ 控件可视尺寸**（≥ 值 = 整屏可被拽出，用户失去「边界」物理感知，回弹前界面露底 → 判不合格）。
- **R3 `0` 的语义**：`0` = 关闭越界拖出（配 `edgeEffect:0`）。要回弹手感就 `edgeEffect:1 + dragMaxDis:50`；**`edgeEffect:1 + dragMaxDis:0` 是自相矛盾的配法**（白配，等效硬停）。
- **R4 循环列表**（`cycleEnable:true`）：本身没有边界，越界拖拽别开大，用基准 50。
- **R5 回弹对齐**（`autoRollback:true`）：只影响拖拽过程手感，不改变最终停靠（对齐整行/整页）；改停靠位置靠 `setSelection()`（其后必须 `refreshListView()`，见 `knowledge/uicontrols/listview-fields.md`）。
- **R6 分辨率换算**：基准 50 @1024×600 ≈ 屏高 8%；其他分辨率 `round(scale × 50)`，下限 24（480×272 → 24；800×480 → 40；1280×800 → 67）。
- **R7 手感验收（实机）**：拽到边界应 1-2 帧内「拽不动」并带阻尼；松手 200-300ms 内回弹归位；**任何情况下不允许整屏内容被拖离后长时间露底**。
- **R8 别拿它做别的**：翻页用 `pagewindow`；下拉刷新自己做手势判定（`onXxxActivityTouchEvent` + 边缘判定），`dragMaxDis` 做不到。
- **R10 别拿它当行程**（2026-10-01）：行程引擎自己算 —— scrollwindow = 内层 window 尺寸 − 视口尺寸。
  「内容滚不到底/末尾控件看不到」的修法是**把内层 window 尺寸改成 ≥ 内容总高**，不是去调 `dragMaxDis`。
  `check_all` **第 26 项**已按此口径自动量行程（并按 `dragMaxDis` 只做越界手感判据）。
- **R9 回调重量也算手感**（2026-09-17 实测）：拖动回调里**禁止全量刷新**——同一页 4 条滑块只因回调重量不同，
拖动期的 CPU 就相差一个数量级（重回调 **73.8%**vs 轻回调 **7.1%**，快拖延迟 **383ms vs 169ms**）。
手感不对时先量「回调里写了几次控件」，再看字段取值。详见 `knowledge/uicontrols/high-frequency-callback-perf.md`。

## 3. 症状 → 病因对照

| 症状 | 病因 | 修 |
|------|------|----|
| 拖一下整屏列表被拽走，松手才弹回来 | listview `dragMaxDis` = 列表高度 | 改 50；无回弹需求则 `0 + edgeEffect:0` |
| 边缘毫无反馈、硬邦邦 | `edgeEffect:0`（或 `edgeEffect:1` 但 `dragMaxDis:0`） | 要回弹就 `edgeEffect:1 + 50` |
| 列表停在不该停的位置 | 缺 `autoRollback:true`（或改数据后没 refresh） | 补 autoRollback / `refreshListView()` |
| 滚动页滚不到底 / 末尾行看不到 | scrollwindow 的**内层 window 尺寸没跟上实际内容**（行程不够；跟 `dragMaxDis` 无关） | 内层 window 高度改成 ≥ 内容总高（行数×行距+首行偏移）；`check_all` #26 报此条 |
| 拖到边界还能把整屏内容拽出去、界面露底 | `dragMaxDis` ≥ 控件可视尺寸（照内容尺寸填的典型后果） | 改手感值（基准 50~200；480×480 取 40~60） |
| 同一个页面的同类控件，**有的顺有的卡**| 卡的那条回调里走了**全量刷新**（每次拖动 80+ 次 GUI 调用） | 回调只刷变化的那一个控件，见 `knowledge/uicontrols/high-frequency-callback-perf.md` |

## 4. 验收清单（交付前打勾）

- [ ] **四个滑动控件**：`dragMaxDis` < 控件可视尺寸（**≥ 即不合格**）
- [ ] listview：`dragMaxDis` < 控件可视高（**≥ 即不合格**）
- [ ] scrollwindow：**行程 = 内层 window 尺寸 − 视口**（不拿 `dragMaxDis` 算）；内容超视口时内层 window 已加高（`check_all` #26）
- [ ] 有回弹手感 → `edgeEffect:1` 且 `dragMaxDis` ≈ 50（非 0、非控件高）
- [ ] 无回弹 → `edgeEffect:0` 且 `dragMaxDis:0`（不要 1+0）
- [ ] 循环列表（cycleEnable）取基准 50，不开大
- [ ] 对齐停靠用 `autoRollback`，不靠加大 dragMaxDis 凑
- [ ] 实机过 R7 手感验收（阻尼 + 200-300ms 回弹，无整屏露底）

## 5. 实测证据

| 来源 | 控件 | 控件高 | edgeEffect | dragMaxDis | autoRollback |
|------|------|-------|-----------|-----------|--------------|
| SampleUI-New detail / ListviewMenu | listview | 113 | 1 | 50 | true |
| SampleUI-New detail / ListviewTimePicker（循环） | listview | 168 | 0 | 0 | — |
| listViewDemo-New / ListView1 | listview | 437 | 0 | 0 | false |
| listViewDemo-New / CityListView | listview | 164 | 0 | 0 | false |
| 真实工程 / 循环选择器组（月/日/时/分/年） | listview | 150 | — | 50 | true |
| 案例 `tdesign-miniprogram` 日期页（5 列，可见 5 行；★ 2026-09-19 实测这套配法可做出滚轮） | listview | 180 | 1 | 50 | true（+cycleEnable） |
| ScrollWindowDemo-New | scrollwindow | — | 1 | 200（★ 视口 450 / 内容 800 → 行程 350，**既不是行程也不是内容尺寸**） | — |
| UIlayoutDemo / setting.json `scrollwindow__3` | scrollwindow | — | 0 | 2400（视口 1245 / 内容 2400 → 行程 1155） | — |
| SmartPanel_HA / settings.json（2026-10-01 核） | scrollwindow | 418（视口） | 1 | 60（内容 832 → 行程 414） | — |
| PageWindowDemo-New | pagewindow | — | 1 | 200 | rollSpeed 60 |
| SlideWindowDemo | slidewindow | — | 1 | 200 | rollSpeed 999 |

统计口径：真实工程 json 里 `dragMaxDis` 取值散落 **0 / 50 / 60 / 180 / 200 / 2400**——
同一个字段、同一个语义（越界拖拽上限），**只是有人把它当行程/内容尺寸填了**。

### 5-1. ★ 「`dragMaxDis` = 越界拖拽上限、不是行程」的双反例（2026-10-01）

**反例甲（官方 demo，静态即可判）**：`ScrollWindowDemo-New/ui/main.json` ——
`scrollwindow__1` 盒子 **450×315**，内层 `window__2` **800×315**（→ 行程 **350**），而 `dragMaxDis=200`。
若「dragMaxDis = 行程」，350 ≠ 200；若「= 内容尺寸」，800 ≠ 200 → **两种旧说法都不成立**。

**反例乙（SmartPanel_HA 真机）**：`ui/settings.json` 视口 **418**/ 内层 window **832**（行程 414）、`dragMaxDis=60`。
若 60 是行程，可见内容带只有 `[0, 478]` → 底部三行（设备倒装 content y 648 / 版本信息 704 / 多屏拼接 768）
**永远进不了屏幕**；但 09-27 真机点行中部 `(240,438)` **进了「多屏拼接」页**（当页内容 720 / 视口 418）
→ 实际滚了 ≈302px（到底）→ **行程由内容决定、引擎自算，60 只管越界拖拽**。

**误读来源推断**：UIlayoutDemo 那份 `dragMaxDis=2400` 恰好 = 内层 window 尺寸，且 `edgeEffect=0`（越界拖拽本就不生效）
→ 被归纳成「scrollwindow 上 dragMaxDis 就是行程/内容尺寸」。已作废。

## 6. 相关

- ★ **scrollwindow 布局反复踩的坑 + 逐条判据（建/改滑动窗口页面前先过一遍）**：`knowledge/uicontrols/scrollwindow-layout-checklist.md`
- listview 字段/回调（含 `item.text` 必须 `""`）：`knowledge/uicontrols/listview-fields.md`
- ★ **用 listview 做滚轮选择器**（循环选择器档的完整配法 + 中心行对齐 + 三个真机坑）：`knowledge/uicontrols/listview-wheel-picker.md`
  （实测口径：`setSelection(i)` 只把第 i 项摆到列表盒第 1 行**且带动画**；程控定位改用「数据侧平移 + refreshListView()」）
- 字段必写全集（含 dragMaxDis 默认值）：`knowledge/uicontrols/json-field-mandatory.md`
- 分层规则（scrollwindow 内容 = 内层 window：**它的尺寸决定行程**；`dragMaxDis` 只管越界）：`knowledge/uicontrols/json-layer-rules.md`
- slidewindow / pagewindow 字段：`knowledge/uicontrols/slidewindow-fields.md`、`knowledge/uicontrols/pagewindow-fields.md`
- HTML 属性映射：`ui_tools/HTML_SUBSET.md`（`data-drag-max` / `data-edge-effect` / `data-auto-rollback` / `data-roll-speed`）
- 自定义手势（下拉刷新等）：`knowledge/uicontrols/touch-events.md`
- 拖动回调写得太多导致的卡顿（CPU 降一个数量级） → `knowledge/uicontrols/high-frequency-callback-perf.md`
