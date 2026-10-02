# gap-list.md — 缺口清单 + 五级处置 + 3D 策略 + 工具链坑

> 「源框架有、FlyThings 没有（或不同）」的**唯一清单**：每条都给级别、处置、出处、证据。
> 级别定义与换算规则见 `control-map.md` §0（L1 等价 / L2 组合 / L3 自绘 / L4 降级 / L5 不支持）。
> **机读版**（开发优先用）：`../../mcp_control_map.json` + MCP op `flythings_map_control(query, source)`
> （213 条、含级别与可直接粘的 json 片段）；本文件是缺口的散文清单与编号来源。
> 合并来源：`lvgl-widgets/TRANSLATE.md` §3（20 条）、`miniprogram-form-list/TRANSLATE.md` §3.1（D1~D22）
> 与其 `README.md` §6（T1~T6）、`CANDIDATES.md` §三、`knowledge/devflow/gui-controls-gap.md`（9 条）。
> 建立：2026-09-16（v0.27.71-open）

---

## 1. 缺口总表（去重合并后）

**读法**：`级别` = 本轮统一五级口径；`原级别/出处` = 原案例编号（换算关系见 `control-map.md` §0.1）。

### 1.1 容器 / 布局 / 外观

| # | 缺口（源能力） | 源框架 | 级别 | 处置（我们怎么做） | 原级别 / 出处 | 证据 |
|---|---|---|---|---|---|---|
| G-01 | 无原生「页签容器 tabview」 | LVGL `lv_tabview` / Android `ViewPager+TabLayout` / 小程序 `swiper+tab` / Qt `QTabWidget` | **L1**（已覆盖） | ★**本轮修正**：一律 `pagewindow`（ZKPageWindow，自带滑动切页 + `onPageChange`）；页签条 = 按钮组。**接线留档（非控件包）**：`_mapping/TabView/`；机读映射 `flythings_map_control("lv_tabview")` | LVGL §3-1 相关（旧写法「多整屏 window + 按钮」） | `uicontrols/pagewindow-fields.md` |
| G-02 | 无横向滚动容器（惯性 + 越界回弹） | 小程序 `scroll-view scroll-x` | **L4**| N 个横排按钮 + `setSelected()` 选一态；**滑动/惯性丢弃**| D7（L4 旧） | 案例截图 `14_list_seg_b` |
| G-03 | 无侧滑抽屉 Drawer | Android `DrawerLayout` / Flutter `Drawer` | **L4**| 自研 `PullWidget` 下拉面板近似（无侧滑手势/遮罩动画） | `gui-controls-gap` 已有不算缺项 | `devflow/custom-widget.md` §9 |
| G-04 | 无 flex / grid 布局引擎 | 小程序 `enable-flex` / LVGL `lv_obj_set_flex_flow` / Qt `QLayout` / Android `LinearLayout` | **L5**| **明说不支持**；替代 = 转换器按源语义层级手工排**绝对坐标**| D15（L5 旧） | `CANDIDATES` §三 草案 |
| G-05 | 整页滚动与「圆角图 + 绝对坐标」耦合 | LVGL content 超出可滚 | **L4**| 1024×600 下手工重排塞进一屏；内容更多时再引 `scrollwindow` | LVGL §3-17（C） | 案例 README |
| G-06 | 卡片阴影（主题 shadow）默认不画 | LVGL `lv_style_set_shadow_*` / CSS `box-shadow` | **L4**| 只做圆角（自动转图）；要阴影显式写 `box-shadow`（会外扩控件盒 + 多一份资产） | LVGL §3-4（B） | `html2json` 阴影三连修复（v0.27.30） |
| G-07 | 卡片/按钮圆角、边框（外观能力） | LVGL 主题按钮 radius / CSS border | **L3（已实现）**| **2026-09-16 升级：`components/ui_v1/RadButton/`**—— `ZKPainter` 自绘带倒角按钮（任意尺寸/半径/四态/边框，抗锯齿 = 圆角弧带逐像素覆盖率 + 混底色，Z21 实测边缘误差平均 1.4~2.0/255）。旧口径仍适用：纯色直角按钮 + 三态色（`bgColorTab`）/ 圆角走图片按钮（`picTab`，代价 ×N 资产，且半径写死——同资产当 r=13 用误差跳到 59.1） | LVGL §3-5（B） | 案例两平台截图；**`RadButton/example/evidence/` + `RadButton/platforms.md` §1.1（数字）**|
| G-08 | 高 DPI 自适应缩放（`LV_DPX`/`dp`） | LVGL `LV_DPX()` / Android `dp/sp` | **L4**| 固定像素工程；多分辨率按 `ui/<分辨率>/` + router 或多份工程（案例按 ×1.25 出第二套） | LVGL §3-20（B） | 两平台工程 |

### 1.2 图表 / 数据可视化（★ 自绘主战场）

| # | 缺口 | 源框架 | 级别 | 处置 | 原级别 / 出处 | 证据 |
|---|---|---|---|---|---|---|
| G-09 | **无通用图表控件**（历史折线 / 分组柱 / 面积渐变 / 点高亮） | LVGL `lv_chart` / MPAndroidChart / `QChart` / QCustomPlot | **L3 自绘**| `ZKPainter` 手画网格/坐标/折线/柱/面积层 + 刻度文字用 `textview` 叠加；残留降级点：无高亮气泡、无平滑曲线、刻度手写 | LVGL §3-2（C→A）、`gui-controls-gap` #2 | 案例 `PtLine`/`PtBar` |
| G-10 | **无多环/三段饼/分区刻度**（`lv_scale` round + 3×`lv_arc`） | LVGL `lv_scale` + `lv_arc` | **L3 自绘**| `ZKPainter` 自绘三同心环 / 三段环（2° 缝）+ 分区刻度；`ZKCircleBar` 只有**单环**且需按色出有效图 | LVGL §3-3（C→A） | 案例 `PtArc`/`PtSess` |
| G-11 | **无仪表盘**（225° 刻度 + 分区色 + 指针） | LVGL `lv_scale` + `lv_image` 指针 | **L3 自绘**| `ZKPainter` 画弧段 + 刻度 + **直线指针**（不用针位图：`ZKPointer` 需表盘图 + 固定圆心，不适用） | LVGL §3-12（B） | 案例 `PtGauge` |
| G-12 | 实时波形以外的图表语义 | LVGL chart 静态/历史 | **L1**（非缺口） | `ZKDiagram` 专做「x 自动推进 + 单值追加」的实时波形（够用就别自绘） | `gui-controls-gap` #2 说明 | `uicontrols/diagram-fields.md` |
| G-13 | 组件语义：painter **无文字 API**| — | **L2**| 所有数字/文字一律 `ZKTextView` 叠加（刻度/图例/数值） | LVGL §3.1 自绘论证 | 案例 §1.3 |

### 1.3 富文本 / 表格 / 小件

| # | 缺口 | 源框架 | 级别 | 处置 | 原级别 / 出处 | 证据 |
|---|---|---|---|---|---|---|
| G-14 | **富文本真缺**（自动折行 / 段内样式混排 / 图文混排 / 长文滚动） | Android `Spannable` / Qt rich text / Web | **L3 自绘**（未开发） | 短期：手动 `\n` 分段（`textview` 支持 `\n`）；长期走自绘 `RichTextView`（候选组件 `rich_text`） | `gui-controls-gap` #1 | 该 KB 2026-09-03 |
| G-15 | **表格 TableView 缺**（表头 / 列宽 / 列定义） | 小程序 `table` / Android TableLayout | **L2**| `textview` 表头 + `listview` 网格，列宽手工对齐 | `gui-controls-gap` #3 | 同上 |
| G-16 | 轻提示/角标/加载半缺（Toast 角落浮动、Badge、菊花） | 小程序 `wx.showToast` / Snackbar / Badge | **L2**| 组合小件：居中/角落 window + `hideTimeOut`；加载动画 = 定时器逐帧换 PNG | `gui-controls-gap` #6 | `uicontrols/widget-code-api.md` |
| G-17 | 长按拖拽排序 / 滑动删除列表项 | Android `ItemTouchHelper` / RecyclerView | **L5**| **明说不支持**；替代建议 = 上/下移按钮 + 删除按钮 | `gui-controls-gap` #9 | 同上 |

### 1.4 表单 / 选择器 / 交互

| # | 缺口 | 源框架 | 级别 | 处置 | 原级别 / 出处 | 证据 |
|---|---|---|---|---|---|---|
| G-18 | **checkbox 控件当前不可用**（生成器不生成宏/指针/回调） | 所有（小程序 `switch`/`checkbox`、LVGL `lv_switch`、Android `Switch`） | **L2**| 开关/复选一律用**两态 `button__N`**（`picTab{pic0,pic1,pic2}` + `setSelected()`），状态在 logic 侧；**建议反馈工具链**| D17（L3 旧）/ T1 | 生成的 `ui_main.h` 三个 checkbox 全缺 |
| G-19 | iOS 风格开关：拖拽滑块 + 过渡动画 | 小程序 `switch` / LVGL `lv_switch` | **L4**| 两态图**点击**切换（无拖拽过渡） | D1（L2 旧） | 案例截图 `02_form_switch_on` |
| G-20 | 无 `setEnabled` 真禁用态（源真不响应事件） | LVGL `LV_STATE_DISABLED` / Android `setEnabled(false)` | **L4**| **仅视觉灰**（`picTab.pic4` 只对有图按钮生效），逻辑上仍可点 → 要真禁用须在回调里自己拦 | LVGL §3-6（C） | 案例 `BtnInvite` |
| G-21 | 无下拉选择控件（dropdown / ComboBox） | 小程序 `picker` / Android `Spinner` / Qt `QComboBox` / LVGL `lv_dropdown` | **L4**| 按钮 → `window`(modal) 列表（点选回写并关闭）；降级点：无滚轮惯性、无多列联动、展开位从「框下」变「居中模态」 | D6 / LVGL §3-7 / `gui-controls-gap` #4 | 案例截图 `06_form_picker_open` |
| G-22 | 无日期/日历控件（**日期部分**） | 小程序 `picker mode=date` / LVGL `lv_calendar` / Qt `QCalendarWidget` / MFC `CDateTimeCtrl` | **L4**| 按钮 + 模态日历（**7×6=42 个 `textview`**+ activity 触摸事件反算命中格）；降级点：无「今天」高亮、无年/月下拉、只能逐月翻。**时间部分不归本缺口**：`TimePicker`（含时钟盘）/`picker mode=time`/`QTimeEdit`/`LISTWHEEL` 一律走 **G-23 的 `listview` 组合（L2）**——2026-09-19 口径「TimePicker 通过 listview 这个实现对应」，**不再有「时间无对应能力」的例外**| LVGL §3-8（B） | 案例 `WinCalendar` / `components/ui_v1/Calendar/`（Z21 真机） |
| G-23 | 滚轮选择器 WheelPicker（联动/惯性）——**含 TimePicker 全族（滚轮 + 时钟盘）**| iOS WheelPicker / Android `NumberPicker`·**`TimePicker`**/ 小程序 `picker-view`·`picker mode=time` / Qt `QTimeEdit` / emWin `LISTWHEEL` | **L2**（2026-09-19 由 L5 改判） | ★**一列 = 一个 `listview`**：`cycleEnable=true + edgeEffect=1 + dragMaxDis=50 + autoRollback=true`（循环列表 + 引擎惯性/回弹）。正中行 = 选中行用**数据侧平移**（`items[k]=label((k-ROT+shift) mod n)` + `refreshListView()`）—— **不能**用引擎选中态：用户拖过后它会把选中态打在列表盒第 1 行、盖掉宿主的 `setSelected`（真机现象：正中行 8 月、底带跑到 6 月）；中心行回读 `A = fi + (h/2 - off)/itemH`（定时器轮询）。**选中条（高亮带）挂「静态背景层」而不是行背景图**（2026-09-19 12:00 需求方口径；挂行 -> 滚动时条跟着行走）：listview **之前**一个装饰 `textview`（`backgroundPic` = 条图、图 == 盒、`touchable:false` + 运行期 `setTouchPass(true)`），选中感只剩正中行文字色。自绘包 `components/ui_v1/WheelPicker` **已于 2026-09-19 移除**（A3 拍板；旧路线曾用于逐像素 alpha 淡出 / 行内非文字内容，现并入本 listview 方案）。**TimePicker 全族统一收口**（★2026-09-19）：「TimePicker 通过 listview 实现对应」——**滚轮形态与时钟盘（clock dial）形态都归本行**：时钟盘的数值/联动语义由 listview 列承载（12 个方位值一列排布，回读中心行 → 时/分），**圆形排列观感**要用 12 方位按钮组或 ZKPainter 自绘才有（**观感降级说明，不是能力缺失**；圆周/非矩形布局属 L3 自绘，要做按本节编号立项）。`NumberPicker` 同步由 `stepper` 改判本行（`listview` / L2） | `gui-controls-gap` #5（旧「真缺」）；口径见 `knowledge/uicontrols/listview-wheel-picker.md` | 案例 `tdesign-miniprogram` 日期页：真机 `z21/evidence/s4b_*`+`s4b_test.log`（24 项，条挂行上）、**`s4c_*`+`s4c_test.log`（30 项，条挂静态层，现役）**；官方样例 `SampleUI-New/ListviewTimePicker` |
| G-24 | 无 group 容器（多选/单选聚合、整表单取值） | 小程序 `radio-group`/`checkbox-group`/`form` | **L2**| N 个两态按钮 + logic 侧 `collectFormValue()` 聚合；无表单容器 → 提交时逐控件取值 | D2/D3/D4（L2 旧） | 案例截图 `05_form_submit_result` |
| G-25 | slider 内建数值气泡（`show-value`） | 小程序 `show-value` / LVGL knob 自绘气泡 | **L4**| 并列常驻数值 `textview` | D5 / LVGL §3-9 | 案例截图 `04_form_slider_right` |
| G-26 | 观感细节：图例色点、月份全称、展开位、调色盘位置/动画 | LVGL / 小程序 | **L4**| 彩色文字代替色点；月份 3 字母缩写；调色盘改弹窗（无宽度展开动画） | LVGL §3-10/11/13（B） | 案例 §3 |

### 1.5 滚动 / 手势 / 动效 / 主题

| # | 缺口 | 源框架 | 级别 | 处置 | 原级别 / 出处 | 证据 |
|---|---|---|---|---|---|---|
| G-27 | 列表**无到顶/到底回调**| 小程序 `bindscrolltoupper/lower` / Android `OnScrollListener` | **L4**| `on<Page>ActivityTouchEvent` 里按 `ev.mY` 与列表区上下界**近似**判定；**精确态**用宿主定时器轮询 `getFirstVisibleItemIndex()/getFirstVisibleItemOffset()`（easyui 2.6.0/2.9.0 都有；案例 16ms 轮询做滚轮中心行） | D2#（L2 旧）；`uicontrols/listview-wheel-picker.md` §2 | 案例 `listLogic.cc`；`tdesign-miniprogram` 日期页 |
| G-28 | 无滚动位置回调 | 小程序 `bindscroll` | **L4**| 触摸事件 `E_ACTION_MOVE` 算进度（只做轻量更新） | D3#（L2 旧） | 案例截图 `15_list_step`/`16_list_drag_anim` |
| G-29 | 无下拉刷新手势（threshold/pulling/restore/abort） | 小程序 `refresher-*` / Android `SwipeRefreshLayout` | **L4**| 按钮触发 + 定时器状态机 `IDLE→PULLING→REFRESHING→DONE`（案例 2s 完成，源 3s） | D8（L4 旧） | 案例截图 `11_list_refreshing`/`12_list_refreshed` |
| G-30 | 无 CSS 动态样式 / 无 `<wxs>` 改 style | 小程序 `<wxs>` + `setStyle` | **L4**| 状态文本 + 只读进度条代替动态样式 | D9（L4 旧） | 平台无 CSS 引擎 |
| G-31 | 无滚动驱动动画（`scrollSource` + 属性插值） | 小程序 `this.animate(..., {scrollSource})` | **L4**| 触摸位移 → 数值联动（进度条 + 百分比文本），无插值 | D10（L4 旧） / §3-11 | 案例截图 `16_list_drag_anim` |
| G-32 | 无平滑滚动动画（`scroll-into-view` 平滑） | 小程序 / Android `smoothScrollToPosition` | **L4**| `setSelection(index)` 直跳（**2026-09-19 修正：真机实测 `setSelection` 是带滚动动画的**，它缺的是「滚到任意像素偏移」，且它只把第 i 项对齐到列表盒**第 1 行**）；程序化定位改用数据侧平移 + `refreshListView()` | D14（L2 旧）；`uicontrols/listview-wheel-picker.md` §1/§3 | `uicontrols/listview-fields.md` |
| G-33 | 页面栈只支持 ≤2 | 小程序任意深度 push/pop / Android 栈 | **L4**| `openActivity/closeActivity`；多页场景用整屏 window 或 pagewindow 代替深栈 | D16（L2 旧） | 案例两页 |
| G-34 | 无 theme 引擎 / 无系统主题事件 | LVGL `lv_theme_default_init` / 小程序 `wx.onThemeChange` / Qt QSS | **L5**| **明说不支持**系统主题联动；应用内换色可做（主色 static + 逐控件 `setTextColor` + painter 重绘） | D11（L5 旧）/ LVGL §2 | 案例固定单套令牌 |
| G-35 | 动画缓动曲线（quadratic/overshoot…） | LVGL `lv_anim` / CSS `transition` | **L4**| 定时器 tick 内自算（可加缓动函数，性价比低）；默认线性 | LVGL §3-19（C） | 案例三角波 |
| G-36 | 3D / 真渲染能力（GPU/GL） | OpenGL ES / Three.js / Scene3D | **L4**| **一律伪 3D/2.5D**（见 §3） | — | Z21/F133 无 GPU/无硬解 |
| G-37 | 列表**无「把第 i 项摆到正中」的 API**（`setSelection(i)` 只对齐到列表盒**第 1 行**，且带动画） | Android `smoothScrollToPosition` + 自定义 center 对齐 / iOS `selectRow(at:animated:scrollPosition:.middle)` | **L4**| 数据侧平移（`items[k]=label((k-ROT+shift) mod n)`）+ `refreshListView()`；要「不动手指地换选中值」（复位/取消/步进）只能这样 | 2026-09-19 Z21 实测（案例日期页） | `uicontrols/listview-wheel-picker.md` §1；`tdesign-miniprogram` `s4b_test.log`（24 项）/ `s4c_test.log`（30 项，含静态条） |
| G-38 | listview **引擎自维护「当前项」选中态**（会覆盖宿主 `setSelected`）；且**行属性不随中心行变化自动重刷**，也**没有单行重刷 API**（`ZKListView.h` 只有 `refreshListView()`，`setSelection(i)` 也不是） | — | **L4**| 选中视觉全部宿主自画：**静态选中条层**（listview 之前的装饰 `textview` + `backgroundPic`，见 G-23）+ `setTextStatusColor(0,色)` 画正中行文字色；json 里 `pic0/1/2` 留空、`color2/3` 置中色；中心行一变就 `refreshListView()` —— 「只刷变化行」做不到，降级为**全量重刷可视行**（≤rows 行，频次 = 每跨一行一次） | 2026-09-19 Z21 实测（真机现象：正中行 8 月、底带跑到第 1 行的 6 月）；头文件核对：同版本 `ZKListView.h` 只有 `refreshListView()` | `uicontrols/listview-wheel-picker.md` §3 坑 1/4；`uicontrols/listview-fields.md` |

---

## 2. 自绘（ZKPainter）必要性论证（每一处都要点名）

| 自绘点 | 为什么非自绘不可（平台控件为何不行） |
|---|---|
| 折线图 / 分组柱状图（G-09） | 平台**没有任何图表控件**；`ZKDiagram` 的语义是「实时滚动波形」（x 自动推进 + 单值追加），做不了「12 个月静态对照 + 双系列分组柱」 |
| 三同心环 / 三段饼 / 三环刻度（G-10） | 平台只有 `ZKCircleBar`（**单环**、按进度裁**图**，每种色要一份有效图）与 `ZKPointer`（**指针**，需表盘底图 + 固定圆心）→ 承载不了「多环叠加 / 动态三段切割 / 分区彩色刻度」 |
| 仪表盘（G-11） | `ZKPointer` 需配套表盘位图 + `rotationPoint`/`fixedPoint`，无法嵌在自绘刻度里；改用 painter 画直线针 + 中心轴点，避免位图资产与旋转对齐问题 |
| 刻度 / 图例 / 数值文字 | painter **没有文字 API**→ 一切文字必须 `ZKTextView` 叠加（这是 §1.2 里刻度用 textview 的原因，也解释了为什么图表是「自绘 + 文本叠加」混合体） |
| 富文本 RichTextView（G-14，未开发） | `textview` 无自动折行、无段内样式、无图文混排；要按宽度逐字符折行 + 行内嵌图 + 可视区局部刷新 → 只能自绘（路线见 `devflow/custom-widget.md` §2 路线 B） |

> 结论（案例实证）：`miniprogram-form-list` 自绘用量 **0 处**（全部能力都能被自带控件承载）；
> `lvgl-widgets` 自绘 **5 处**（PtLine/PtBar/PtArc/PtSess/PtGauge），全部集中在图表类。

---

## 3. 3D 处置策略（写死，不许临场决定）

| 平台 | 结论 |
|---|---|
| **Z21**（1024×600，无 GPU / 无硬解 / 36MB RAM） | **一律伪 3D / 2.5D**：预渲染贴图 + 烘焙阴影高光 + 序列帧旋转体（定时器切图）。**不做真 3D**（EGL/GL 离屏 + disp 分层） |
| **F133**（1280×800 UI，无 GPU / 无硬解） | 同上，**一律伪 3D**|
| **V85X**| 平台有 **disp 分层**能力，真 3D / 图层合成**仅在此平台验证过**（如视频层 + OSD 合成） |

**执行要点**
1. 任何 3D 需求先落「伪 3D 方案」再评估（贴图/序列帧优先，帧数与时序写进 README）。
2. 序列帧 = 定时器切 `backgroundPic`（逐帧 PNG），图尺寸必须 == 控件盒（`check_all #11/#17`）。
3. 涉及视频层/图层的（V85X）走平台能力与 `knowledge/v85x/display-layer-debug.md`，**不进控件映射表**。

---

## 4. 工具链 / 平台坑（写错就不亮/不编译，映射时必须避开）

> 与 `control-map.md` §5（F1~F12）同源，这里是排查视角。全部为**实测复现**（设备日志 / 截图 / ftu 反解为证）。

| # | 坑 | 症状 | 处置 | 出处 |
|---|---|---|---|---|
| T1 | `fun` 代码生成器不支持 `checkbox__`（无 ID 宏 / 指针 / 回调；ftu 本身正常、设备能显示） | 逻辑里拿不到 checkbox → 以为框架不支持该控件 | 改用两态 `button__N`（G-18）；建议反馈工具链 | D17 / 案例 README T1 |
| T2 | `fun launch`（Windows）把 `resources/<子目录>/*` 推成**平铺文件名**（`images\x.png`） | 所有图片控件全空（按钮只剩文字） | 设备侧脚本搬回 `images/`（`fui unpack` 校验 ftu 内为正斜杠） | D21 / 案例 README T2 |
| T3 | 设备侧 `libeasyui.so` **无 `ZKBase::getAbsolutePosition()`**| `dlopen: undefined symbol ...getAbsolutePositionEv` → **整屏黑**（形似布局/打包问题） | 只用 `getPosition()`（顶级控件即屏绝对坐标） | D20 / 案例 README T3 |
| T4 | `check_all #10` 禁 `ZKSeekBar` 用 `.9.png`，而 `#11/#17` 又要求 `resources/images/` 图与控件盒 **1:1**| 轨道/填充图必须按控件盒尺寸出图 | 逐尺寸生成普通 PNG（`(w,h)` 参数化） | 案例 README T4 |
| T5 | `check_all #6` 把框架名 `mActivityPtr` 误判为控件指针 | 想 `findControlByID` 取未生成指针的控件时 FAIL | 与 T1 同源，改用生成器支持的控件后自然规避 | 案例 README T5 |
| T6 | listview **行自身**`text` 铺满整行，与 subItem **叠字**| 行内文字重影 | `obtainListItemData_*` 里显式 `pListItem->setText("")` | D22 / 案例 README T6 |
| T7 | `html2json` 把 **`#000000` 当「未设置」**（0 是 falsy） | 想写纯黑被换成默认色 | 纯黑写 `#010101` | `MCP_FEATURES` v0.27.70 |
| T8 | `ZKListView::setSelection()` 只改滚动位置、**不重排不重绘**| 「行位置与选中样式错位」/看着像没刷新 | 数据变更后必须 `refreshListView()`；定位末项先 `setSelection(count-1)` 再刷新（顺序不能反） | v0.27.69 入库 |
| T9 | Z21 是**共用真机**，`/tmp/ui` 可能被其它会话覆盖；`/tmp` 是 tmpfs（36MB 内存板，撑爆 OOM 杀 `zkgui`） | 抓图串场拿到别的工程；设备重启/应用起不来 | 验收「一条命令内做完部署→修复→重启→注入→抓图」；只推必需小工具、用完删 | 案例 §5.1 |
| T10 | 重启后**首次触摸注入常被吞**| picker/开关首点无效，误判为功能失效 | 验收脚本先热身点击再取证 | 案例 §5.1 |
| T11 | ZKPainter `drawArc` 实参口径两套记录冲突 | 照抄可能画错（无报错） | 按 Z21(easyui 2.6.0) 实测 `(cx,cy,rx,ry,start,sweep)`；用前小图自证 | `uicontrols/widget-code-api.md` |
| T12 | 抓屏抓到**上一帧**（fb 双缓冲 pan 偏移） | 「点了没反应」误判成逻辑 bug | 抓屏前后读 `fb0/pan`（或连抓两次比 md5）；触摸 `touch long x y 250` 触发重绘 | `devflow/device-screenshot.md` |

---

## 5. 明确不做 / 待确认（不许含糊）

| 项 | 状态 | 说明 |
|---|---|---|
| LVGL `Shop` 页（商品卡列表 + 6 个 checkbox 筛选 + 价格条） | **不做（本轮）**| 任务口径只取 tab 页；源文件留在 `src-orig/` 供后续批次（LVGL §3-1，旧 D） |
| `lv_keyboard` 自制键盘 | **丢弃**| 平台有更完整的系统输入法（含中文），源的键盘是其平台妥协（LVGL §3-14） |
| 小程序 skyline 渲染器 / `glass-easel` | **不支持（L5）**| 平台无对应渲染器（D13） |
| 多语言 i18n | **本轮不做**| 与源保持一致（英文硬编码）；工具链有 `i18n_tools` 可做 |
| `drawArc` 实参口径 | **待官方/需求方确认**| 两份记录冲突，本项目按 Z21 实测值；建议找官方核实后定稿 |
| F133 真机验收（LVGL 案例 / 小程序案例） | **待设备上线**| 设备（USB `20080411`）不在 adb 列表；已编译、未上机 |
| `checkbox__` 生成器支持 | **待工具链修复**| 当前一律两态按钮绕过；修复后 G-18 可回到 L1（用 `ZKCheckBox`） |
| `relayout()` 运行期换布局 | **依赖 easyui ≥ 2.9.0**| Z21/T113(2.6.0)、F133(2.8.0) 无 → 需问 FlyThings 厂家/官方（`devflow/dynamic-screen-rotation.md`） |

---

## 6. 相关文件

- 控件映射（★ 权威）：`control-map.md`　·　逻辑映射：`logic-map.md`
- 平台口径（分辨率/rotate/easyui 版本差异/设备限制）：`platforms.md`
- 候选组件（把上面处置做成可复用件）：`components.md`　·　案例证据：`examples/README.md`
- 知识库侧摘要 + 指针：`knowledge/uicontrols/framework-control-mapping.md`
