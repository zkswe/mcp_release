---
id: uicontrols-control-mapping-capability
title: 跨框架控件映射能力（op `flythings_map_control`）
category: uicontrols
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [检索词：控件映射, 映射能力, 跨框架, 源控件, lv_slider, RecyclerView]
evidence: []
---
# 跨框架控件映射能力（op `flythings_map_control`）

> 检索导引：问「映射能力怎么用 / flythings_map_control 怎么调 / 命中不到映射怎么办 / 和 components/ui_v1 什么分工」→ 本文（工具用法与边界）；常见映射速查见 `uicontrols/framework-control-mapping.md`。
> 检索词：控件映射 / 映射能力 / 跨框架 / 源控件 / lv_slider / RecyclerView / QCalendarWidget /
> lv_tabview / swiper / CALENDAR / CDateTimeCtrl / 映射表 / control map / mcp_control_map.json /
> 别的框架的控件对应我们哪个控件 / 有对应控件就直接用 / 命中不到怎么办 / 缺口五级。
>
> 建立：2026-09-16（v0.27.73-open，钟工口径：「有对应控件的走映射能力，不写散文说明」）｜
> **机读数据**：仓库根目录 `mcp_control_map.json`（六个源框架 213 条）｜
> **散文权威表**：`components/ui_v1/control-map.md`（级别判定与换算）＋ `components/ui_v1/gap-list.md`（缺口 G-01~G-36）

---

## 1. 一句话口径（先记住这条，别做反）

| 情形 | 怎么做 | 落点 |
|---|---|---|
| **平台有对应控件**（能 1:1 或组合覆盖） | **走映射能力**：查 op → 拿到 target/level/可直接粘的 json 片段 → 用平台自带控件 | `mcp_control_map.json` + op `flythings_map_control` |
| **平台真缺的能力**（无任何可组合路径） | **才做自定义控件包**：一个缺口控件一个目录 | `components/ui_v1/<源控件名>/`（如 `Chart/`） |
| 有对应控件、但接线细节值得留档（手感/同步/验收判据） | 放**映射参考目录**（**不算控件包**） | `components/ui_v1/_mapping/<源控件名>/` |

**判定判据只有一个：平台有没有能覆盖的控件**（不看外观、不看源框架写法）。有 → 映射；无 → 才建包。

## 2. 怎么用（op 签名与返回）

```
flythings_map_control(query, source='')
  query  源框架控件名或别名（忽略大小写与下划线/连字符）：lv_slider / RecyclerView /
         QCalendarWidget / lv_tabview / swiper / CDateTimeCtrl / CALENDAR / lv_chart …
  source 可选：只在该框架内找 —— lvgl / qt / android / miniprogram / emwin / mfc
```

分发器模式下等价调用：`flythings_kb(op='flythings_map_control', args='{"query":"lv_slider"}')`。

**命中返回**（`ok:true`）：

| 字段 | 含义 |
|---|---|
| `source` / `sourceLabel` | 命中的源框架（如 `android` / `Android View / Material`） |
| `name` | 命中的源控件名 |
| `target` | **我们的控件**（json 里的类型名，如 `seekbar` / `pagewindow` / `listview`） |
| `level` / `levelName` | `L1 等价 / L2 组合 / L3 自绘 / L4 降级 / L5 不支持`（判定口径见 `control-map.md` §0） |
| `json` | **可直接粘进 `ui/*.json` 的片段**（字段全集显式写出，含默认值；caption 用规范命名） |
| `notes` | 坑与降级点（例如「背景禁 `.9.png`」「行自身要 `setText('')`」「F133 不支持动图」） |
| `ref` | L3/L4/L5 时指向 `components/ui_v1/<包>` 或计划条目；L1/L2 通常为空 |
| `control` | 目标控件的规范 caption、指针名（`mXxxPtr`）、一句话用法 |
| `alsoMatched` | 多个框架都沾边时的其他候选（最多 4 条） |
| `warnings` | 模糊命中提醒（score < 100 时） |

**未命中返回**（`ok:false`）：`error.code = NO_HIT` + `candidates`（相近控件名）+ `gapPolicy`
（五级口径 + 「有对应控件走映射 / 真缺才建包」两条出路 + 文档指针）。`source` 写错回 `BAD_SOURCE`
（并把可取值列出来）；`query` 为空回 `BAD_PARAMS`。

## 3. 覆盖范围（六个源框架，213 条）

| source | 条数 | 覆盖（举例） |
|---|---|---|
| `lvgl` | 32 | `lv_slider`、`lv_switch`、`lv_arc`、`lv_chart`、`lv_tabview`、`lv_calendar`、`lv_roller`、`lv_canvas`、`lv_anim`、`lv_obj_set_flex_flow`… |
| `qt` | 40 | `QPushButton`、`QSlider`、`QComboBox`、`QTabWidget`、`QCalendarWidget`、`QTimeEdit`、`QChart`、`QScrollArea`、`QVBoxLayout`… |
| `android` | 43 | `RecyclerView`、`SeekBar`、`Switch`、`TabLayout`、`ViewPager2`、`DatePicker`、`TimePicker`、`NumberPicker`、`SwipeRefreshLayout`、`ItemTouchHelper`… |
| `miniprogram` | 39 | `view`、`input`、`swiper`、`picker`、`picker-view`、`radio-group`、`switch`、`slider`、`rich-text`、`refresher-enabled`、`wx.showToast`… |
| `emwin` | 29 | `WINDOW`、`FRAMEWIN`、`BUTTON`、`LISTBOX`、`LISTWHEEL`、`DROPDOWN`、`GRAPH`、`ICONVIEW`、`SWIPELIST`、`KNOB`、`QRCODE`… |
| `mfc` | 30 | `CButton`、`CEdit`、`CListCtrl`、`CComboBox`、`CSliderCtrl`、`CTabCtrl`、`CDateTimeCtrl`、`CMonthCalCtrl`、`CAnimateCtrl`… |

数据文件里另有 `targets`（41 项）：**我们这侧每个控件的规范片段**（`caption` / 指针 / json / 一句话用法），
例如 `targets.seekbar = {caption:'SkSpeed', ptr:'mSkSpeedPtr (ZKSeekBar)', json:'{...}'}`。

**覆盖不到的部分怎么办**：L4/L5 的条目都带替代建议（写进 `notes`）；映射表里没有的控件名 → 见下一节。

## 4. 命中不到怎么办（两条出路，别即兴发挥）

1. **先判是不是「已有控件换个写法」**：看 `NO_HIT` 返回的 `candidates`，或直接用源框架自己的词再试
   （例如 `CALENDAR`→`lv_calendar`、`CDateTimeCtrl`→`calendar`、`swiper`→`swiper+tab`）。
2. **确认平台真缺 → 按「缺口处置五级」走**（`components/ui_v1/gap-list.md`）：
   - **L1 等价 / L2 组合**：**禁止建包**，用自带控件 + logic 侧聚合（可把接线放 `_mapping/`）。
   - **L3 自绘**：`ZKPainter` 自绘（文字一律 `textview` 叠加），**必须先在 `gap-list.md` 登记缺口编号**，
     再落到 `components/ui_v1/<源控件名>/`（已实现的先看 `Chart/`）。
   - **L4 降级**：保留语义、写明降级点后实现；真机证据里标注「降级实现」。
   - **L5 不支持**：**明说不支持**，给替代建议或书面理由，不假装能转。
3. **别做的事**：不要拿别家框架的字段/API 套用到我们控件上（`android:hint`→`hintText`、
   `lv_label_set_text()`→`setText()`）——控件用法/字段只查 MCP 知识库或官方站
   （`uicontrols/retrieval-boundary.md`）；本能力只回答「**哪个控件对应哪个控件**」。

## 5. 与 `components/ui_v1/` 的分工（最容易做反的地方）

| | 映射能力（本文件） | 自定义控件包（`components/ui_v1/<源控件名>/`） | 映射参考（`components/ui_v1/_mapping/`） |
|---|---|---|---|
| 放什么 | 源控件 → 我们控件的机读索引 + 可直接粘的片段 | **平台真缺的能力**的实现（四件套 + `example/` + 真机证据） | **有平台控件**但接线细节值得留档（手感参数/双向同步/验收判据） |
| 典型 | `lv_slider`→`seekbar`（L1）、`lv_tabview`→`pagewindow`（L1）、**`picker-view`/`lv_roller`/`TimePicker`（含时钟盘）/`NumberPicker`→`listview` 组合（L2）** | `Chart/`（L3 自绘）、`Calendar/`（L4）、`RadButton/`（L3）、计划 `RichText/` | `_mapping/TabView/`（基于 `pagewindow`） |
| 不许 | 不许给「已有控件」再包一层当自定义控件 | 不许在无 L1/L2 判定前建包；不许文档先行（`example/` 必须真编译过） | 不许把「真缺能力」的实现塞这里（该进 `<源控件名>/`） |

看板：`components/ui_v1/components.md`（三段状态表：**已实现自定义控件 / 映射项 / 计划中的自定义控件**）。

## 6. 写法示例：有对应控件 → 直接加载组件用

**① 布局侧（json，片段来自 op 返回的 `json` 字段，可直接粘）**

```json
"seekbar__1":{"id":33001,"caption":"SkSpeed","position":{"left":40,"top":200,"width":400,"height":40},
"backgroundColor":-1,"backgroundPic":"images/sk_track_400x40.png","defProgress":0,"max":100,
"orientation":0,"progressPic":"images/sk_fill_400x40.png","thumb":"images/sk_thumb_24x24.png",
"touchable":true,"visible":true}
```

（源控件 `lv_slider` / `SeekBar` / `QSlider` / `slider` / `SLIDER` / `CSliderCtrl` 都是这一条；
`notes` 里的坑要一起照做：背景禁 `.9.png`、图尺寸 == position。）

**② 代码侧（用生成器给的指针，别自己 `findControlByID`）**

```cpp
// caption=SkSpeed → 指针 mSkSpeedPtr（src/logic/mainLogic.cc）
static void onProgressChanged_SkSpeed(ZKSeekBar *pBar, int progress) {
    // 每拖一格回调一次；禁放耗时操作
}

static void onUI_init() {
    mSkSpeedPtr->setProgress(60);      // 初值（defProgress 只管初始显示）
}

static void onUI_quit() { }            // 有 listener 就在这里置 NULL
```

**③ tab 类（L1 映射 + 接线留档）**

```cpp
// 源：lv_tabview / ViewPager+TabLayout / swiper+tab / QTabWidget → pagewindow__N
// 映射：flythings_map_control("lv_tabview") → target=pagewindow, ref=components/ui_v1/_mapping/TabView
static void onPageChange(ZKPageWindow *pw, int page) { /* 页签高亮/下划线同步 + 自绘控件重绘 */ }
static void onUI_init() { mPwPagesPtr->setPageChangeListener(&s_listener); }
```

**④ 真缺能力（L3/L4/L5）示例**：`flythings_map_control("lv_chart")` → `target=chart`、`level=L3`、
`ref=components/ui_v1/Chart` ⇒ 不要自己从零画：**直接取 `components/ui_v1/Chart/`**（`include/zk/` + `src/`，
照 `example/` 接线；改数据必须 `refresh()`）。计划中的（`RichText/`、`TableGrid/`、`BadgeToast/`、`Pseudo3D/`）**还没有包**，走批次立项，期间按 `gap-list.md` 的过渡方案；
**滚轮选择器（`picker-view`/`lv_roller`/`WheelPicker`/`TimePicker` 含时钟盘/`NumberPicker`/`LISTWHEEL` 类）不是 L3/L4/L5**：2026-09-19 已改为 **L2**（`listview` 组合，
口径见 `knowledge/uicontrols/listview-wheel-picker.md`，含 §6 时间选择/时钟盘），原自绘包 `components/ui_v1/WheelPicker/` **已移除**、`TimePicker/` **不做包**——查这类控件
直接 `flythings_map_control("picker-view")` / `("TimePicker")` / `("clock dial")` / `("NumberPicker")` 拿 `target=listview` + `level=L2` + 可直接粘的片段。

## 7. 维护（加/改条目）

1. 改 **`mcp_control_map.json`**（唯一数据源）：对应 `sources.<框架>` 加/改一条
   （`name`/`aliases`/`target`/`level`/`json`/`notes`/`ref`），新控件类型再补 `targets.<类型>`。
2. 同步散文表 `components/ui_v1/control-map.md`（级别口径/行）与 `gap-list.md`（真缺能力必须补缺口编号）。
3. 跑 `python rebuild_index_local.py`（重建检索索引）＋ `python scripts/check_consistency.py --with-tests`（全绿）。
4. **冲突一律以 KB 为准**（`knowledge/uicontrols/*-fields.md`、`knowledge/devflow/gui-controls-gap.md`、
   `knowledge/uicontrols/json-field-mandatory.md`）。

## 8. 相关文件

- 机读数据：`mcp_control_map.json`（仓库根目录）
- 散文权威表 / 缺口 / 组件状态：`components/ui_v1/control-map.md`、`gap-list.md`、`components.md`
- 映射参考（接线留档）：`components/ui_v1/_mapping/README.md`
- 摘要版指针：`knowledge/uicontrols/framework-control-mapping.md`
- 字段全集与 json 口径：`knowledge/uicontrols/json-field-mandatory.md`（+ `*-fields.md`）
- 自研控件方法论：`knowledge/devflow/custom-widget.md`　·　家底盘点：`knowledge/devflow/gui-controls-gap.md`
