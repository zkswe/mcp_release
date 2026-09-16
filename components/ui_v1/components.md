# components.md — 组件状态表（本代框架：ui_v1）

> **口径（★ 2026-09-16 钟工最终修正）**：跨框架控件分两类处置——
> 1. **有一一映射的控件 → 走「映射能力」，不写散文**：机读索引 `mcp_control_map.json`（六个源框架
>    212 条）+ MCP op `flythings_map_control(query, source)`；此类**不建控件包**（要接线细节放 `_mapping/`）。
> 2. **FlyThings 没有的能力 → 才做成自定义控件包**：`components/ui_v1/<源控件名>/`（四件套 + `example/` + 真机证据）。
>
> 本文件是**状态表**，分三段：**① 已实现自定义控件包**（缺口控件，有源码 + 真机证据）／
> **② 映射项**（已有平台控件 → 指向 op 与数据文件）／**③ 计划中的自定义控件**（平台真缺、还没做）。
> 建立：2026-09-16（v0.27.71-open）｜ 本轮更新：2026-09-16（v0.27.73-open：TabView 迁出 ui_v1 → `_mapping/`，
> 状态表改三段 + 新增「映射项」）

---

## 1. 已实现自定义控件包（平台真缺的能力，可直接用：`components/ui_v1/<控件名>/`）

| # | 目录 | 源框架对应控件（各家） | 我们怎么做（自绘/组合路线） | 级别 | 对外接口（`zk::ui_v1::<控件>`） | 平台 | 版本 | 证据 |
|---|---|---|---|---|---|---|---|---|
| 1 | [`Chart/`](Chart/README.md) | LVGL `lv_chart`（历史/分组/饼环/仪表）；Android MPAndroidChart；Qt `QCustomPlot`/`QChart`；emWin `GRAPH` | **ZKPainter 自绘集合**（LINE 折线 / BAR 分组柱 / RING 同心环 / GAUGE 仪表 + 网格 + 刻度 + 混色近似 alpha），刻度文字用 ZKTextView 池叠加；改数据**必须显式 `refresh()`** | **L3** | `attach(painter)` / `setType(LINE\|BAR\|RING\|GAUGE)` / `setSeries(idx,v,n)` / `appendPoint(idx,v)` / `setAxisRange(min,max,ticks)` / `setRingPercent` / **`setRingSegments(ring,segs,n)`（0.2.0 分段环：一环切 2..8 段、按权重归一）** / `clearRingSegments` / `hasRingSegments` / `setGaugeZones` / `setGaugeValue` / `attachLabels(labels,n)` / `setStyle(Style)` / `refresh()` | Z21 ✅ 真机·F133 ⚠️ 仅编译 | **0.2.1** | `Chart/example/evidence/`（7 张全在 Z21、**同一次会话**；01 = **0.2.1 Y 刻度值序修复后**的首帧（与 06 同帧），06/07 = 分段环可见 + 分段环分区 diff，02~05 = 数据变化/增量重绘与 diff；08/08b/08c = 0.2.1 Y 刻度值序专项（重抓首帧 + 0.1.0 旧帧反序对照）） |
| 2 | [`Calendar/`](Calendar/README.md) | LVGL `lv_calendar`；小程序 `picker mode=date`；Android `DatePicker`/`DatePickerDialog`；Qt `QCalendarWidget`；MFC `CDateTimeCtrl`/`CMonthCalCtrl` | **42 个 `textview` 承载日号（7×6）+ 1 标题 + 2 翻月按钮**；月天数/星期算法/选中状态机在组件里；**命中由业务在 activity 触摸事件里 `cellAt()/dayAt()` 反算**（平台 textview 没有点击回调）；改月/改选中/改标记后**必须 `refresh()`**；高亮 = **文字色 + 选中加粗**（Z21 实测 textview 画不出底色，见包内 `platforms.md`） | **L4** | `attach(cells[42],title,prev,next)` / `setContainer(ZKBase*)` / `setContainerOrigin(x,y)` / `setDate(y,m,d)` / `date()` / `setMonth(y,m)` / `prevMonth()` / `nextMonth()` / `setOnDatePicked(fn,user)` / `pickDay(day)` / `setMarkedDays(days,n)` / `setToday(y,m,d)` / `cellIndexOfDay(day)` / **`cellAt(absX,absY)`** / **`dayAt(absX,absY)`** / `setStyle(Style)` / `refresh()` | Z21 ✅ 真机·F133 未验证 | **0.1.0** | `Calendar/example/evidence/`（5 张真机 + 1 张 diff） |
| 3 | [`RadButton/`](RadButton/README.md) | LVGL `lv_button`（主题倒角 `radius`）；CSS `border-radius`；Android `MaterialButton`/`shape=rounded`；小程序 `button`+`border-radius` | **ZKPainter 自绘带倒角按钮**：`button__N` 是 L1 映射（`lvgl.lv_btn → button`）但**倒角/边框没有任何平台能力**（json 无 radius 字段、`ZKButton` 无半径 setter；只能 `picTab` 挂切图 = 半径/尺寸/状态色全烧进资产）→ 本包 = **一个 painter + 一份代码**，任意尺寸/半径/四态/边框都在运行期给；**抗锯齿 = 圆角弧带逐像素覆盖率（8×8 超采样）+ 与已知底色混色**（Z21 实测平均误差 1.4~2.0/255，平台原生 `fillRect(radius)` 是 8.2~19.6）；**改半径/色/状态后必须 `refresh()`**；**先铺 `Style::bg` 再画**（`erase()` 留黑） | **L3** | `attach(painter)` / `setStyle(Style)` / `setRadius(r)` / `setColors(normal,pressed,selected,disabled,border)` / `setMode(MODE_AA\|MODE_HARD)` / `setState(NORMAL\|PRESSED\|SELECTED\|DISABLED)` / `state()` / `stateName()` / `currentColor()` / **`press(down)`（幂等，抬起回落到按下前状态）** / `setSelected(on)` / `refresh()` / `erase()` / `width()/height()/radiusPx()` / `static mix()` / **`static drawRoundedRect(painter,l,t,w,h,radius,fill,border,borderWidth,bg,mode,aaSamples)`** | Z21 ✅ 真机（含像素数字）·其它平台未验证 | **0.1.0** | `RadButton/example/evidence/`（5 张真机状态帧 + 3 张 8× LANCZOS 角部对照 + 3 张 diff；数字见 `platforms.md` §1.1） |

**「已实现」的验收门槛（缺一不算）**：四件套齐（`README.md` + `platforms.md` + `Manifest.xml` + `include/src`）
+ `example/` **真的编译过** + 能在真机跑起来的**有 `example/evidence/*.png`**（拿不到设备的写「待设备空闲补真机验收」）。
**进这一段的前置条件（本轮新增）**：op `flythings_map_control` 对该能力必须**没有 L1/L2 命中**（有命中 → 走映射，不进包）。

---

## 2. 映射项（**有平台对应控件** → 走映射能力，不建包）

> **权威数据**：`mcp_control_map.json`（机读，212 条）｜**查询入口**：MCP op `flythings_map_control(query, source)`；
> **平台对应控件的手感/接线留档**（仅当映射有细节值得留时）放 `_mapping/<源控件名>/`。
> 这一段**不是待开发清单**：这些能力现在就能用（`target` 是已有控件 + 组合套路），不需要写自定义控件。

| # | 源框架控件（各家） | 我们的做法（映射） | 级别 | 查询 | 接线留档 |
|---|---|---|---|---|---|
| 1 | Tab 内容区：`lv_tabview` / `swiper` / `ViewPager` / `QStackedWidget` / `QTabWidget` / `CTabCtrl` / `CPropertySheet` | **`pagewindow__N`（ZKPageWindow）**，自带左右滑动切页 + `onPageChange(pw,page)`；**禁止**多整屏 window + 按钮拼（丢手势） | L1 | `flythings_map_control("lv_tabview")` | ★ [`_mapping/TabView/`](_mapping/TabView/README.md)（页签高亮/下划线双向同步 + 手感默认值 200/1/60/0 + Z21 真机证据） |
| 2 | Tab 页签条：`TabLayout` / `tab` / `QTabBar` / 小程序 `custom-tab-bar` | N × `button__N`（`setSelected()` 走 `bgColorTab.color2`/`picTab`）+ `onPageChange` 回设选中态 | L2 | `flythings_map_control("TabLayout")` | 同上 |
| 3 | 开关/复选：`lv_switch` / `switch` / `QCheckBox` / `CheckBox` / `BS_AUTOCHECKBOX` | **两态 `button__N`**（`picTab{pic0 关, pic1 按下, pic2 开}` + `setSelected()`）；⚠️ `fun` 不为 `checkbox__` 生成宏/指针/回调 | L2 | `flythings_map_control("lv_switch")` | — |
| 4 | 复选组/单选组聚合：`checkbox-group` / `QButtonGroup` / `ChipGroup` | N 个两态按钮 + logic 侧 `collectFormValue()` 聚合（平台无 group 容器） | L2 | `flythings_map_control("checkbox-group")` | — |
| 5 | 列表：`RecyclerView` / `lv_list` / `scroll-view` / `QListView` / `CListBox` / `SWIPELIST` | `listview__N`（三回调；行自身 `setText("")`；数据变了必须 `refreshListView()`）；**不做 view 复用回收** | L1(+L2) | `flythings_map_control("RecyclerView")` | — |
| 6 | 下拉选择：`lv_dropdown` / `picker` / `Spinner` / `QComboBox` / `DROPDOWN` | `button__N` + `window__N`(modal) 列表/按钮组；降级点：无滚轮惯性、无多列联动、展开位变居中模态 | **L4** | `flythings_map_control("QComboBox")` | — |
| 7 | 下拉刷新：`refresher-enabled` / `SwipeRefreshLayout` | 按钮触发 + `REGISTER_ACTIVITY_TIMER_TAB` 状态机 `IDLE→PULLING→REFRESHING→DONE` | **L4** | `flythings_map_control("refresher-enabled")` | — |
| 8 | 轻提示/角标/加载：`wx.showToast` / `Toast` / `Snackbar` / `Badge` / `Spinner` 菊花 | 小 `window__N` + `hideTimeOut` 2~3s + `showWnd()`；加载动画 = 定时器逐帧换 PNG | L2 | `flythings_map_control("Toast")` | — |
| 9 | 数值步进：`stepper` / `QSpinBox` / `SPINBOX` / `CSpinButtonCtrl` | 2 × `button__N`(+/-) + `textview__N` | L2 | `flythings_map_control("QSpinBox")` | — |
| 10 | 表格网格：`table` / `QTableView` / `LISTBOX+HEADER` / `CListCtrl(report)` | `textview` 表头 + `listview` 网格（列宽手工对齐） | L2 | `flythings_map_control("QTableView")` | — |
| 11 | 图片/图标：`lv_img` / `image` / `ImageView` / `icon` / `LV_SYMBOL_*` | `textview__N` + `backgroundPic`（图标走 `components/icons` Tabler PNG，尺寸必须 == 控件盒） | L1 | `flythings_map_control("ImageView")` | — |
| 12 | 实时波形：`lv_chart`(滚动) / 示波类控件 | `diagram__N`（`addData/setData`，x 自动推进）——够用就别自绘（自绘的那部分是 `Chart/`） | L1 | `flythings_map_control("lv_chart")` | — |

> **工具链侧（属 MCP op，不随控件包目录走）**：`CssEffectToImage`（`tools/ui_tools/gen_res.py` + `html2json`
> 自动转圆角/阴影/渐变图，已可用）与 `TranslateLint`（扫残留源框架概念，防「假装能转」，待立项）。

---

## 3. 计划中的自定义控件（平台**真缺**、还没有包）

> 判据（三条都要满足）：**① op `flythings_map_control` 无 L1/L2 命中（平台真缺）**＋
> **② `gap-list.md` 有缺口编号**＋**③ 稳定实现套路**（跨案例重复出现）。
> 开工时按四件套落到 `components/ui_v1/<源控件名>/`，做完把条目搬到上面第 1 段。

| # | 计划目录 | 源框架对应控件（各家） | 我们怎么做（自绘/组合路线） | 级别 | 接口草案（对外面） | 出处案例 | 出处缺口 |
|---|---|---|---|---|---|---|---|
| 1 | `TimePicker/` | Android `TimePicker` / `TimePickerDialog`；Qt `QTimeEdit`；小程序 `picker mode=time` | 时/分/秒三组步进按钮 + 数值 textview（12/24h 切换）；或自绘时钟盘（成本高，默认不做） | **L4** | `setTime(h,m,s)` / `getTime()` / `onTimePicked(cb)`；`setFormat(12\|24)` | 无（本轮由 Android/Qt 映射收口派生） | G-22 同族（时间） |
| 2 | `WheelPicker/` | iOS WheelPicker；Android `NumberPicker` / `TimePicker` 滚轮；小程序 `picker-view`；`LISTWHEEL` | 无原生能力 → **自绘 + 手势**（`VelocityTracker` 惯性 + 定时器减速 + 回弹），或按钮步进降级 | **L5**（当前）/ 自绘可升 L3 | `setColumns(vector<vector<string>>)` / `onPicked(cols)` | 无（`gui-controls-gap` #5） | G-23 |
| 3 | `RichText/` | Android `Spannable`；Qt rich text；Web；小程序 `rich-text` / `editor`；emWin `MULTIEDIT`；MFC `CRichEditCtrl` | **自绘**（`onDraw` + 字宽测量逐字符折行 + 脏区局部刷新；图文混排按行内嵌图）；短期用 `textview` + 手动 `\n` | **L3** | `setSegments(vector<Segment{text,size,color,bold}>)` / `setAutoWrap(true)` / `scrollTo(line)` | 无（`gui-controls-gap` #1 提名） | G-14 |
| 4 | `TableGrid/` | 小程序 `table`；Android `TableLayout`；Qt `QTableWidget`；emWin `HEADER` | 要**真表头 + 列定义 + 冻结列**时自绘（`textview` 表头 + `listview` 网格只够过渡，已归映射项） | L3（表头/列定义） | `setHeader(vector<string>)` / `setColsWidth(vector<int>)` / `setRows(vector<vector<string>>)` | 无（`gui-controls-gap` #3） | G-15 |
| 5 | `BadgeToast/` | 小程序 `wx.showToast` / `wx.showLoading`；Android `Badge` / 角标 | 角标跟随控件（坐标联动 + 数字自适应宽度）、加载菊花帧图池（一次注册多实例复用） | L2 | `Toast::show(text, ms)` / `Loading::show()/hide()` / `Badge::attach(ctrl, n)` | 无（`gui-controls-gap` #6） | G-16 |
| 7 | `Pseudo3D/` | Web `three.js`；Android `GLSurfaceView`；Qt `QOpenGLWidget` | 预渲染贴图 + 烘焙阴影高光 + **序列帧旋转体**（定时器切 `backgroundPic`）；图尺寸必须 == 控件盒 | L4 | `loadSeq(dir, frames)` / `rotateTo(deg)` / `playOnce()` | 无（本轮由 3D 口径派生） | G-36 + `gap-list.md` §3 |

> **与上一版对照**：上一版 15 项里，`pageview_tabbar` → `_mapping/TabView/`（映射项，**已迁出控件包**）；
> `chartv` → `Chart/`（已实现自定义控件）；`Switch` / `ChoiceGroup` / `Picker` / `RecyclerView` / `Refresher` /
> `list_select` → **全部归第 2 段映射项**（平台有对应控件 + 组合套路，不必建包）；
> `badge_toast_loading` → 计划 `BadgeToast/`；`css_effect_to_image` / `translate_lint` → 工具链侧（MCP op）。
> 「级别」列 = 该实现的**落地级别**（L3=必须自绘；L4=含明确降级点；L2=组合；L1=等价）。

### 实现批次的排序建议（不做承诺，等排期）

| 优先级 | 组件 | 理由 |
|---|---|---|
| ~~P0~~ | ~~`pageview_tabbar`~~ | **已完成且归位**（映射项 → `_mapping/TabView/`，含真机证据） |
| P0 | `Calendar`、`TimePicker` | 两个案例已手写实现过日历（有真机验证过的 42-textview + 触摸反算套路）；时间选择同族，一起做最省 |
| P1 | `RichText`、`BadgeToast` | 自绘/小件，通用性最强（`gui-controls-gap` 排序一致） |
| P2 | `TableGrid`、`WheelPicker`、`Pseudo3D` | 需要时再做（都有过渡方案） |
| ~~P3~~ | ~~`CssEffectToImage`、`TranslateLint`~~ | **不在本目录**：属工具链侧（MCP op），已有实现/待立项 |

---

## 4. 落地要求（照 `components/README.md` 收口，缺一不收）

- [ ] **先证明「平台真缺」**：op `flythings_map_control(query)` 无 L1/L2 命中 + `gap-list.md` 有缺口编号
- [ ] 目录：`components/ui_v1/<源控件名>/`（命名空间 `zk::ui_v1::<控件>`）
- [ ] `README.md`：替代哪个源控件 / 我们怎么做（10~30 行可跑代码）/ API 表 / 依赖与线程模型 / **限制** / **验收记录** / 排错
- [ ] `platforms.md`：逐平台可用性 + 前置条件 + 实测值（未实测标 `未验证`）+ **easyui 版本**
- [ ] `Manifest.xml`：底层依赖包 + 被引用的两种方式（源码引入 / 依赖包）
- [ ] `example/`：最小可跑示例，**真的编译过**；能上机的必须有 `example/evidence/*.png`
- [ ] 代码规范：不泄漏底层类型 / `Result{code,msg}` / 默认参数安全 / 线程模型写清 / 平台分支只在内层
- [ ] 与 `control-map.md` / `gap-list.md` 的对应关系写进包 README（哪个源控件、哪个级别、哪个缺口编号）

---

## 5. 相关文件

- ★ **机读映射数据**：`../../mcp_control_map.json`（212 条）+ op `flythings_map_control`
- 能力说明（这个 op 怎么用 / 命中不到怎么办）：`knowledge/uicontrols/control-mapping-capability.md`
- 控件映射（散文权威表）：`control-map.md`　·　逻辑映射：`logic-map.md`
- 缺口 + 级别 + 3D + 工具链坑：`gap-list.md`　·　平台口径：`platforms.md`
- 映射参考（有对应控件的接线留档）：`_mapping/README.md`
- 目录规范与代码尺子：`components/README.md`
- 自研控件方法论（组合式 / 自绘式两条路线）：`knowledge/devflow/custom-widget.md`
- 家底盘点（内置 21 + 自研 8）：`knowledge/devflow/gui-controls-gap.md`
