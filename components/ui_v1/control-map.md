# control-map.md — 跨框架控件映射（★ 散文权威表）

> **口径修正（2026-09-16，钟工）**：**有一一映射的控件走「映射能力」，不写散文说明** —— 机读索引在仓库根目录
> `mcp_control_map.json`（六个源框架 212 条，含 `level / json 可直接粘 / notes / ref`），查询入口是 MCP op
> **`flythings_map_control(query, source)`**；本文件保留为**级别口径、缺口编号、平台事实的散文说明与索引**
> （机读数据从这里 + KB 收口而来）。开发时**优先用 op**，本文用于人读与校对。
>
> 本文件是「源框架控件 → FlyThings 控件」的**唯一散文权威表**。知识库侧只留摘要 + 指针
> （`knowledge/uicontrols/framework-control-mapping.md` / `control-mapping-capability.md`），**禁止在别处再抄一份**（防两处漂移）。
>
> 口径（钟工 2026-09-16 批复）：控件一律换成 **FlyThings 自带控件做语义映射**，不照搬源框架的
> 控件外观/自绘实现；`ZKPainter` 自绘**只用于「平台确实没有对应控件」的能力**（图表/仪表/环形刻度），
> 每一处都在 `gap-list.md` 点名。程序侧（事件/状态/列表/导航/定时器）见 `logic-map.md`。
>
> 合并来源（四份草案 + KB 家底，本轮去重去冲突后合并成一张表）：
> - `projects/translate/lvgl-widgets/TRANSLATE.md` §1 控件映射 / §2 逻辑映射 / §3 差异清单 20 条
> - `projects/translate/miniprogram-form-list/TRANSLATE.md` §1~§3 + 其 `README.md`（缺口 D1~D22）
> - `projects/translate/CANDIDATES.md` §三（草案表）
> - `knowledge/devflow/gui-controls-gap.md`（内置 21 控件 + 自研 8 控件 + 缺口清单）
>   + `knowledge/uicontrols/*-fields.md`（控件字段口径）+ `knowledge/devflow/custom-widget.md`
>
> 建立/裁定：2026-09-16（v0.27.71-open）｜适用框架代次：**FlyThings IDE + easyui（v1 基线）**

---

## 0. 级别口径（五级，全库统一）

| 级别 | 名称 | 判据（必满足） | 处置动作 |
|---|---|---|---|
| **L1** | **等价** | 有对应自带控件；语义 + 行为 1:1（平台固有差异如系统键盘/设备字库**计入 L1**） | 直接映射同名控件 + 对应回调 |
| **L2** | **组合** | 无单一控件，但 2+ 自带控件/容器/容器组合 + logic 侧聚合即可**无能力丢失** | 拆成多个控件，观感用两态图/`.9.png`/图标补齐；差异写进 `gap-list.md` |
| **L3** | **自绘** | 平台**真缺**该能力（无任何可组合路径），必须 `ZKPainter` 自绘 | 自绘 + 文字部分一律 `ZKTextView` 叠加（painter 无文字 API）；登记自绘必要性论证 |
| **L4** | **降级** | 语义保留，但**交互体验或观感明确降低**（手势/动画/CSS 动态样式/平滑/任意深度/拖拽过渡/滚轮惯性…） | 用按钮/定时器/数值联动近似；真机证据里标注「降级实现」 |
| **L5** | **不支持** | 平台无对应能力**且无合理替代** | 明说不支持，不假装能转；给出替代建议或「不做」的书面理由 |

**判定规则（消歧，必须照此裁）**
1. **只看能力，不看外观**：源控件的外观（圆角/阴影/渐变）不算能力，缺它最多 L4。
2. **并列取差**：同一项既「可组合」又「有可见差异/能力丢失」→ **取 L4**（并列取更差者）。
3. **自绘优先判 L3**：只要能自绘解决，级别记 **L3**，把仍残留的降级点写进备注（不写 L4）。
4. **工具链/平台事实不进 L1~L5**：如「`fun` 不为 `checkbox__` 生成宏」「设备侧无 `getAbsolutePosition()`」
   这类是**事实条目**（§5），若它导致换了控件/写法，则**在对应控件行备注里点名**，不单独计级别。

### 0.1 旧级别 → 五级换算（原案例 A/B/C/D 与 L1~L5 的对应）

| 旧口径 | 出处 | 换算规则 |
|---|---|---|
| `L1 直译` | 小程序案例 §3 | → **L1** |
| `L2 等价改写` | 小程序案例 §3 | 逐条判：换控件但 1:1 → **L1**；换控件 + 拼接 → **L2**；换控件 + 能力丢失 → **L4** |
| `L3 组合替代` | 小程序案例 §3 | 无能力丢失 → **L2**；有丢失 → **L4** |
| `L4 能力降级` | 小程序案例 §3 | → **L4** |
| `L5 不支持` | 小程序案例 §3 | → **L5**（同名同义，定义未变） |
| `A 等价实现` | LVGL 案例 §3 | → **L1**（`A（平台差异）`同样是 L1） |
| `B 近似（有可见差异）` | LVGL 案例 §3 | → **L4**（若该项实际走自绘 → **L3**） |
| `C 降级（能力削弱）` | LVGL 案例 §3 | → **L4**（若该项实际走自绘 → **L3**） |
| `C→A`（缺能力但自绘等价） | LVGL 案例 §3 | → **L3**（自绘），残留降级点写备注 |
| `D 不支持` | LVGL 案例 §3 | → **L5** |
| 草案表（无级别） | CANDIDATES §三 | 本轮**逐行补齐**级别（见下表） |

> **本轮修正（必须遵守）**：`tab` 类控件一律走 **`pagewindow`（ZKPageWindow）**，
> **禁止**用「多个整屏 `ZKWindow` + 按钮显隐」拼 —— 后者**丢手势滑动**（这是本轮修正的核心）。
> 历史案例 `lvgl-widgets` 的 `WinProfile/WinAnalytics` 双窗切换属旧写法，**新工程不得照抄**（见 §6 变更）。

---

## 1. 结构 / 容器

| # | 源框架控件（各家写法） | FlyThings 控件（json / C++） | 级别 | 原级别 | 备注 |
|---|---|---|---|---|---|
| 1.1 | 屏幕根 / 页面容器：`lv_screen`、Android Activity layout、小程序 `page`、Qt `QWidget` | 根节点（`backgroundColor` 令牌）+ 整屏 `window__N`（`ZKWindow`），或独立 `*.ftu` | L1 | — | 整屏 window = 同 ftu 多页显隐（零切换成本、共享指针）；独立 ftu = 独立生命周期/返回栈（见 `devflow/page-architecture-spec.md`） |
| 1.2 | **Tab 内容区（滑动切页容器）**：`lv_tabview`、`ViewPager`、`swiper`、`QStackedWidget`、`QTabWidget` 内容区 | **`pagewindow__N` / `ZKPageWindow`**（子 `window__N` 为页，并排叠放） | **L1** | — | ★**本轮修正**：pagewindow 自带左右**滑动切页** + `onPageChange(pPageWindow, page)`（page 从 0 起）+ `turnToNextPage()/turnToPrevPage()`。**禁止**「多整屏 window + 按钮」拼（丢手势）。接线留档（非控件包）：`_mapping/TabView/` |
| 1.3 | **Tab 页签条**：`lv_tabview` 顶部页签、`TabLayout`、小程序 `tab` 标签、`QTabBar`、`CTabCtrl` | N × `button__N`（`ZKButton`，`setSelected()` 走 `bgColorTab.color2`/`picTab`） | L2 | — | 页签条仍需按钮组（pagewindow 不带标签栏）；`onPageChange` 里回设按钮选中态，保证「手势滑页 + 点页签」两向同步；下划线用 `textview` 色带（接线留档 `_mapping/TabView/`） |
| 1.4 | 纵向滚动容器：`scroll-view scroll-y`、`ScrollView`、`QScrollArea`、`lv_obj`(scrollable) | `scrollwindow__N` / `ZKScrollWindow` | L1 | L1 | 内容 window 可大于视口整体拖动；纯结构用法，零代码 |
| 1.5 | 横向滚动容器：`scroll-view scroll-x`、`HorizontalScrollView`、`QScrollArea(H)` | 无横向滚动容器控件 | **L4** | L2(旧) | 降级：N 个横排 `button__N` + `setSelected()` 选一态，**滑动/惯性/越界回弹丢弃**（小程序 D7） |
| 1.6 | 宫格轮播 / 引导页：`swiper`、`ViewPager`（图标页）、`lv_tileview` | `slidewindow__N` / `ZKSlideWindow`（宫格轮播，`items[]`） | L1 | L1 | 点击回调 `onSlideItemClick_Caption(ZKSlideWindow*, int index)`，index 是**跨屏全局下标** |
| 1.7 | 弹窗 / 对话框：`modal`、`Dialog`、`lv_msgbox`、`QDialog` | `window__N` / `ZKWindow`（`modal:true`） | L1 | L1 | `showWnd()/hideWnd()/isWndShow()`；`modal=true` 拦截底层点击；`hideTimeOut` 可自动关 |
| 1.8 | 轻提示 Toast/Snackbar | `window__N`(小) + `hideTimeOut` 2~3s + `showWnd()` | L2 | — | 组合：平台无角落浮动条（`gui-controls-gap` #6 半缺）；不占焦点、常驻可用 |
| 1.9 | 侧滑抽屉 Drawer / 下拉面板 | 自研 `PullWidget`（下拉展开面板，app 级触摸） | L4 | — | 无原生 Drawer；下拉面板语义近似，侧滑手势与遮罩动画丢失 |
| 1.10 | 卡片 / 圆角面板：`lv_obj_create`+radius、`div`+border-radius、`CardView`、`QFrame` | `window__N` + `border-radius`（html2json **自动转圆角图** `images/round_*.png`） | L2 | — | 卡片本身是 window 组合；不写 radius 就是方角 |
| 1.11 | 卡片阴影 / 主题阴影：`lv_style_set_shadow_*`、`box-shadow` | 支持 `box-shadow` 自动转图，**默认不画** | L4 | B | 阴影图会外扩控件盒 + 每卡多一份资产、透明角叠色风险高；要就显式写 `box-shadow`（html2json 已支持单位解析/1:1 出图） |
| 1.12 | 列表容器：`scroll-view` 列表、`RecyclerView`、`ListView`、`lv_list`、`QListView` | `listview__N` / `ZKListView`（`cols/rows/orientation/hasScrollbar`） | L1 | L1 | 三回调：`getListItemCount_*` / `obtainListItemData_*`（**禁耗时**）/ `onListItemClick_*`（id=被点子控件 ID） |
| 1.13 | 表格 TableView（表头/列宽/行数据） | `textview` 表头 + `listview` 网格 | L2 | — | `gui-controls-gap` #3「真缺」：无表头/列定义能力，列宽需手工对齐；要真表头走自绘（→ 候选组件 `table_grid`） |
| 1.14 | 富文本 RichText / 样式混排 / 自动折行 | 无 | **L3** | — | `gui-controls-gap` #1「真缺」：`textview` 支持 `\n` 但**不自动折行**、无段内样式混排、无图文混排 → 需自绘（候选组件 `rich_text`，未开发） |
| 1.15 | flex / grid 布局引擎：`enable-flex`、`lv_obj_set_flex_flow`、`QLayout`、`LinearLayout` | **无** → 一律**绝对定位**（`data-x/y/w/h`） | **L5** | L5(旧) | 平台无 flex/grid 引擎；替代建议 = 转换器按源语义层级手工排绝对坐标（小程序 D15） |

---

## 2. 基础控件

| # | 源框架控件（各家写法） | FlyThings 控件（json / C++） | 级别 | 原级别 | 备注 |
|---|---|---|---|---|---|
| 2.1 | 按钮：`button`、`lv_btn`、`Button`、`QPushButton` | `button__N` / `ZKButton` | L1 | L1 | 两态/多态图 `picTab{pic0..pic4}`；纯色三态 `bgColorTab`；回调 `bool onButtonClick_Caption(ZKButton*)` |
| 2.2 | 文本（单行/多行、可手动换行）：`text`、`lv_label`、`TextView`、`QLabel` | `textview__N` / `ZKTextView` | L1 | L1 | `setText` 支持 `\n` 多行；**不自动折行**（超宽自己插 `\n`）；文字只认 utf-8 |
| 2.3 | 输入框（单行）：`input`、`lv_textarea`(one_line)、`EditText`、`QLineEdit` | `edittext__N` / `ZKEditText` | L1 | L1 | **系统内置键盘**自动弹出（源自制键盘一律丢弃）；回调 `onEditTextChanged_Caption(const std::string&)`（每键一次，禁放重活） |
| 2.4 | 密码输入 / placeholder / 最大长度 | `edittext__N` + `isPassword:true` / `hintText` | L1 | — | 掩码字符 `*`；`setPassword()` 与 IME 联动 |
| 2.5 | **开关**：`switch`、`lv_switch`、`Switch`、`QCheckBox`(开关型) | **`button__N` 双态图**（`picTab{pic0 关, pic1 按下, pic2 开}` + `setSelected()`） | L2 | L2/D17 | ⚠️ **事实 D17**：`fun` 代码生成器**不为 `checkbox__` 生成 ID 宏/指针/回调** → 一律用两态按钮（语义目标 `ZKCheckbox` 暂不可用）。降级点：无 iOS 式**拖拽过渡动画**（该点属 L4） |
| 2.6 | 复选：`checkbox`、`lv_checkbox`、`CheckBox`、`QCheckBox` | `checkbox__N` / `ZKCheckBox`（`pic0` 未选 / `pic2` 选中） | L2 | — | 同 D17 限制：当前生成器不支持 → 实际落地走两态 `button__N`；`setChecked()` 会触发回调（注意回环） |
| 2.7 | 复选组（多选 + 取值数组）：`checkbox-group`、`QButtonGroup` | N × `button__N`（两态）+ logic 侧 `collectFormValue()` 聚合 | L2 | L2/D2 | 平台无 group 容器（→ 候选组件 `choicegroup`） |
| 2.8 | 单选组：`radio-group`+`radio`、`RadioGroup`、`QRadioButton`、`lv_obj`+状态 | `radiogroup__N` / `ZKRadioGroup`（子项自动进 `radiobuttons`） | L1 | L1 | 回调 `onCheckedChanged_Caption(ZKRadioGroup*, int checkedID)` **给的是选中项控件 ID，不是索引**（用 `switch ID_MAIN_RadioButtonX`）；程序选中 `setCheckedID()` |
| 2.9 | 滑块：`slider`、`lv_slider`、`SeekBar`、`QSlider` | `seekbar__N` / `ZKSeekBar` | L1 | L1 | 回调 `onProgressChanged_Caption(ZKSeekBar*, int)`；⚠️ **拿不到拖拽起止**（要起止须换 `ZKSeekBar::ISeekBarChangeListener`，注册后会**顶掉** Activity 分发的那套）；背景图**禁 9-patch**、**尺寸 == position** |
| 2.10 | 滑块内建数值气泡：`show-value`、knob 浮层、`QSlider`+label | `seekbar__N` + 并列 `textview__N` 常驻数值 | L4 | L2/D5 | 无 knob 自绘扩展点 → 改常驻数值文本（反而便于验收读值） |
| 2.11 | 进度条（只读）：`progress`、`lv_bar`、`ProgressBar` | `seekbar__N` + `touchable:false`（只读） | L2 | — | 平台无独立 progressbar；只读语义靠关触摸实现 |
| 2.12 | 环形进度（单环）：`lv_arc`(单值)、环形 ProgressBar | `circlebar__N` / `ZKCircleBar` | L1 | L1 | `setProgress(0..max)`；按进度**裁有效图**成扇形（非转图），每种色要一份有效图；无拖拽回调 |
| 2.13 | 表针 / 仪表指针：`lv_scale`+needle、`QDial` | `pointer__N` / `ZKPointer` | L1 | L1 | 唯一 API `setTargetAngle(deg)`；需 `rotationPoint`(控件系圆心)+`fixedPoint`(图系铰点)+表盘底图配套 |
| 2.14 | 下拉选择 / 选项框：`picker`、`Spinner`、`QComboBox`、`lv_dropdown` | `button__N` + `window__N`(modal) + `listview__小`/按钮组 | **L4** | L3/D6、B/7 | 组合可行但**无滚轮惯性、无多列联动**，且展开位从「框下」变「居中模态」→ 取差为 L4（→ 候选组件 `picker`） |
| 2.15 | 日期/时间选择：`picker mode=date/time`、`DatePicker`、`QDateTimeEdit`、`lv_calendar` | `button__N`/`edittext__N` + `window__N` 日历（**7×6 = 42 个 `textview__N`** 承载日号）+ activity 触摸事件反算命中格 | **L4** | B/8 | painter **无文字 API** → 网格数字必须 textview；降级点：无「今天」高亮、无年/月下拉跳转（只能逐月翻）→ 候选组件 `calendar` |
| 2.16 | 数值步进：`stepper`、`QSpinBox`、`NumberPicker`(小) | 2 × `button__N`(+/-) + `textview__N` | L2 | — | 组合 |
| 2.17 | 图标字体 Symbol：`LV_SYMBOL_*`、Material Icons 字体 | `textview__N` + `data-icon="mail"`（html2json 自动转**线框 PNG**） | L1 | A | 设备字库无 Symbol 码位 → 一律走图标 PNG（`components/icons` Tabler，MIT） |
| 2.18 | 图片：`image`、`lv_img`、`ImageView`、`QLabel`+pixmap | `textview__N` + `backgroundPic`，或 `imageview` | L1 | L1 | **铁律**：`resources/images/` 自动生成的 PNG 尺寸 **必须 == 控件盒**（`check_all #11/#17`） |
| 2.19 | 动图 GIF/WebP：`lv_gif`、`image`(gif)、`AnimatedDrawable` | `imageanim__N` / `ZKImageAnim`（`playFile`+`loopCount`） | L1 | — | **平台有差异**：Z20/Z21/T113/V85X 支持，**F133 不支持**（见 `platforms.md`） |
| 2.20 | 二维码：`canvas`+lib、`qrcode`、QZXing | `qrcode__N` / `ZKQRCode` | L1 | — | 唯一 API `loadQRCode(const char* utf8)`，每次全量重生成 |
| 2.21 | 数字时钟 / 跑马灯：`digitalclock`、marquee、`lv_label`(long scroll) | `digitalclock__N` / `slidetext__N` | L1 | — | 时钟 **零代码自走时**（json `format/beat/clockColor`）；跑马灯走 `SlideText` |
| 2.22 | 长按：`bindlongpress`、`OnLongClickListener`、`QToolButton`+timer | `ZKBase::ILongClickListener` + json `longClickTimeOut/longClickIntervalTime` | L1 | — | 注册 `setLongClickListener(&obj)`，`onUI_quit` 置 NULL |
| 2.23 | 拖拽排序 / 滑动删除列表项 | 无 | **L5** | — | `gui-controls-gap` #9：`AlbumListView` 有长按但无换序/侧滑删；**替代建议** = 上/下移按钮 + 删除按钮（不假装能转） |
| 2.24 | 滚轮选择器 WheelPicker（时间/数值联动） | 无 | **L5** | — | `gui-controls-gap` #5「真缺」；替代 = 步进按钮组 / `picker` 模态列表（→ 候选组件 `wheel_picker`，滚动惯性属自绘） |

---

## 3. 复杂控件（图表 / 选择 / 媒体 / 手势）

| # | 源框架控件（各家写法） | FlyThings 控件（json / C++） | 级别 | 原级别 | 备注 |
|---|---|---|---|---|---|
| 3.1 | **实时波形**：`lv_chart`(滚动)、实时曲线控件 | `diagram__N` / `ZKDiagram`（`infos[]` 子波形 + `addData(index,y)` / `setData(index,points,count)`） | L1 | — | 语义就是「x 自动按 step 推进的单值追加」；数据坐标系 = **轴范围逻辑值**（0..100 刻度非像素） |
| 3.2 | **通用图表（折线历史/柱状/饼环/仪表）**：`lv_chart`、MPAndroidChart、`QChart`、QCustomPlot | **`painter__N` / `ZKPainter` 自绘**（网格/坐标/折线/柱/环/指针）+ 刻度文字用 `textview__N` 叠加 | **L3** | C→A / #2#3#12 | ★**平台真缺**：无任何 chart 控件；`ZKDiagram` 做不了「12 月静态对照 + 分组柱」；`ZKCircleBar` 单环做不了三环叠加/三段饼；`ZKPointer` 需表盘图+固定圆心。残留降级点：无点高亮气泡、无平滑曲线、刻度手写（→ 候选组件 `chartv`） |
| 3.3 | 画板 / 自由自绘：`canvas`、`android.graphics`、`QPainter`、`lv_canvas` | `painter__N` / `ZKPainter`（`setLineWidth/setSourceColor` + `drawRect/drawArc/fillArc/drawTriangle/fillTriangle/drawLines/drawCurve`、`fillRect/erase`） | L1 | — | ⚠️ `drawArc` **实参口径存疑**（两套记录冲突）：本项目按 Z21(easyui 2.6.0) 实测的 `(cx,cy,rx,ry,start,sweep)`；用前按目标平台跑小图自证。painter **不自动重绘** → 在 `onUI_show`/改数据回调里显式重画 |
| 3.4 | 图片相框 / 翻页相册（滑动切页、双指缩放） | `slidewindow__N`（语义近似）或自研 `ImageBoxView`（预加载/滑动/双指缩放/特效） | L2 | — | 自研 `ImageBoxView`（含 `event::multi_touch` 多指）是组合式控件，能力覆盖但非 ftu 内建 |
| 3.5 | 视频：`video`、`VideoView`、`QVideoWidget` | `videoview__N` / `ZKVideoView` | L1 | — | `setVideoPlayerMessageListener` + `E_MSGTYPE_VIDEO_PLAY_STARTED/COMPLETED/ERROR`；进度条联动见 `widget-code-api.md` |
| 3.6 | 摄像头预览 / 拍照：`camera`、Camera2、`QCamera` | `cameraview__N` / `ZKCameraView` | L1 | — | 拍照四回调 `IPictureCallback`（纯虚必实现，**仅 jpg**）；`End` 后 `sync()` 落盘 |
| 3.7 | 纯音频播放（非控件）：`innerAudioContext`、MediaPlayer、`QMediaPlayer` | `ZKMediaPlayer`（代码 API，非 ftu 控件） | L1 | — | ⚠️ 消息枚举与 videoview **两套**（`E_MSGTYPE_PLAY_STARTED` vs `E_MSGTYPE_VIDEO_PLAY_STARTED`），别混 |
| 3.8 | 图片加载/解码/缓存（异步） | 自研 `AlbumListView`(LRU)/`ImageBoxView`(预加载) + `MessageQueueThread` | L2 | — | 重活丢工作线程 + 脏区重绘（方法见 `devflow/custom-widget.md`） |
| 3.9 | 手势：惯性滚动 / 越界回弹 / 拖拽 | `scrollwindow`/`listview` 自带（`dragMaxDis`/`edgeEffect`/`rollSpeed`）；要自定义走 `onTouchEvent` + `VelocityTracker` | L1 | — | ⚠️ `dragMaxDis` 语义**两种**：listview = 越界拖拽上限；scrollwindow/pagewindow/slidewindow = 行程（取值规范见 `uicontrols/scroll-drag-interaction-spec.md`） |
| 3.10 | 下拉刷新（`refresher-enabled`/`SwipeRefreshLayout`/`PullToRefresh`） | 按钮触发 + `REGISTER_ACTIVITY_TIMER_TAB` 状态机 | **L4** | L4/D8 | 平台**无下拉手势**、无 CSS 动态样式 → 保留「刷新状态机 + 完成回调 + 数据更新」语义，手势/下拉动画丢弃（→ 候选组件 `refresher`） |
| 3.11 | 滚动驱动动画：`this.animate({...},{scrollSource})`、`lv_anim` on scroll | 触摸位移 → 数值联动（`seekbar`/`textview` 百分比） | **L4** | L4/D10 | 无 CSS 动画/圆角插值（→ 见 4.2 动画口径） |
| 3.12 | 到顶/到底事件：`bindscrolltoupper/lower`、`OnScrollListener` | `onXxxActivityTouchEvent` 里按 `ev.mY` 与列表区上下界比较 | L4 | L2/D2# | 平台 listview **无到顶/到底回调**；触摸位置近似判定（有边界误判风险） |
| 3.13 | 滚动位置/进度：`bindscroll`、`getScrollY()` | `onXxxActivityTouchEvent`(E_ACTION_MOVE) 计算进度 | L4 | L2/D3# | 同上；回调里只做轻量状态更新 |
| 3.14 | 跳转到指定项 / 平滑滚动：`scroll-into-view`、`smoothScrollToPosition` | `mListPtr->setSelection(index)` + `refreshListView()` | L4 | L2/D14 | **无平滑动画**（直跳）；⚠️ `setSelection` 只改滚动位置、**不重排不重绘** → 数据变了必须 `refreshListView()` |
| 3.15 | 页面栈（任意深度 push/pop、`navigateBack(Δ)`） | `EASYUICONTEXT->openActivity()/closeActivity()`，**页栈深度 ≤2** | **L4** | L2/D16 | 平台限制页栈 ≤2；替代 = 多整屏 window 显隐或 pagewindow（不靠深栈） |

---

## 4. 能力型（动效 / 主题 / 3D / 布局）

| # | 源能力 | FlyThings | 级别 | 原级别 | 备注 |
|---|---|---|---|---|---|
| 4.1 | 生命周期/数据驱动的视觉状态（`LV_STATE_DISABLED`、`setEnabled(false)`） | 无 `setEnabled` 语义 | **L4** | C/6 | `picTab.pic4`（无效图）只对有图按钮生效 → 本版用**视觉灰底**表达禁用，逻辑上仍可点（真禁用须在回调里自己拦） |
| 4.2 | 动画/缓动（`lv_anim`、`QPropertyAnimation`、CSS transition/keyframes、`requestAnimationFrame`） | `REGISTER_ACTIVITY_TIMER_TAB` + `INIT_UI_TIMERS` + `onUI_Timer(id)` 逐帧算值 | **L4** | C/19、D9 | 定时器 tick 内可自算缓动函数；**无 CSS 引擎**（动态样式/圆角插值/滤镜不支持） |
| 4.3 | 主题引擎/动态换肤（`lv_theme_default_init`、`wx.onThemeChange`、`QSS`） | 无 theme 引擎 → 主色存 `static uint32_t s_primary`，换色时逐控件 `setTextColor()` + 重绘 painter | **L5** | L5/D11 | 系统级主题事件不支持（固定单套令牌）；应用内换色可做（≈L2），系统主题联动 L5 |
| 4.4 | 高 DPI 自适应缩放（`LV_DPX()`、`dp/sp`、`qreal` 缩放） | 固定像素工程；多分辨率 = `ui/<分辨率>/` + router 或多份工程 | **L4** | B/20 | 单一分辨率工程下按等比 ×1.25 出第二套（案例做法）；非运行时自适应 |
| 4.5 | **3D / 真渲染**（OpenGL ES、`GLSurfaceView`、`Three.js`、`Scene3D`） | **一律伪 3D / 2.5D**（预渲染贴图 + 烘焙阴影高光 + 序列帧旋转体，定时器切图） | **L4** | — | **Z21 / F133 无 GPU、无硬解**（硬口径）；真 3D（EGL/GL 离屏 + disp 分层）**仅在 V85X 验证过**。见 `gap-list.md` §3 与 `platforms.md` §3 |
| 4.6 | 页面滚动（整页可滚）：`page scroll`、`NestedScrollView` | `scrollwindow__N`；否则手工重排塞进一屏 | L4 | C/17 | 引 `scrollwindow` 与「卡片圆角图 + 绝对坐标」耦合复杂；内容多时再引 |
| 4.7 | 运行时换布局/换方向：`relayout`、`setRequestedOrientation` | `CONFIGMANAGER->setScreenRotate(rot)` + `setTouchRotate(rot)` + `Activity::relayout("x.ftu")` | L2 | — | ⚠️ `relayout()` **需 easyui ≥ 2.9.0**（Z21/T113 2.6.0 无、F133 2.8.0 无 / 2.9.0 有）；两套 ftu 控件 ID 必须一一对应（见 `devflow/dynamic-screen-rotation.md`） |
| 4.8 | 富媒体图层（视频层/OSD 分层合成） | 平台级能力（V85X disp 分层），非控件面 | L5 | — | 由平台能力矩阵决定，不进控件映射（Z20 视频走 MI 硬件图层） |

---

## 5. 平台 / 工具链事实（已核实，映射时按此写）

> 这些**不是级别**，是「写错就不亮/不编译」的硬事实。出处：两个案例真机实测 + 工具链源码。

| # | 事实 | 影响 | 正确做法 |
|---|---|---|---|
| F1 | **`fun` 不给 `checkbox__` 生成宏/指针/回调**（生成的 `ui_<page>.h` 里 checkbox 全缺；ftu 本身正常、设备能显示） | 用 `ZKCheckbox` 就无法从 logic 侧读写状态 | 开关/复选一律用**两态 `button__N`**（`picTab{pic0,pic1,pic2}` + `setSelected()`）；建议反馈工具链（小程序 D17/T1） |
| F2 | 设备侧 `libeasyui.so` **无 `ZKBase::getAbsolutePosition()`**（比本地包旧） | 用它 → `dlopen` undefined symbol → **整屏黑**（形似布局/打包问题，排查成本高） | 只用 `getPosition()`（顶级控件的坐标即屏绝对坐标）（小程序 D20） |
| F3 | `fun launch`（Windows）把 `resources/<子目录>/*` 推成**字面平铺名**（`images\x.png`） | 设备端解析不到路径 → **所有图片控件全空**（按钮只剩文字） | 设备侧脚本把平铺文件搬回 `images/`（`fui unpack` 校验 ftu 内是正斜杠）；见案例 `z21/evidence/fix_res_paths_busybox.sh`（D21/T2） |
| F4 | listview **行自身**的 `text` 会铺满整行，与 subItem **叠字** | 行内文字重影 | `obtainListItemData_XXX` 里显式 `pListItem->setText("")`（D22/T6） |
| F5 | `html2json` 把 **`#000000` 当「未设置」**（`data-color/data-bg` 走 `to_dec(...) or 默认值`，0 是 falsy） | 想写纯黑被换成默认色（文字 `0xEEF2F6`/按钮底 `0x374457`/窗口底 `0xFFFFFF`） | 要纯黑请写 **`#010101`**（深色底/黑字真踩到过） |
| F6 | `check_all #10` 禁 `ZKSeekBar` 用 `.9.png`，而 `#11/#17` 要求 `resources/images/` 下自动生成的图与控件盒 **1:1** | 轨道/填充图必须按控件盒尺寸出**普通 PNG** | 按 `(w,h)` 逐尺寸生成（案例 T4/D19） |
| F7 | `check_all #6` 把框架名 `mActivityPtr` 误判为控件指针 | 想用 `findControlByID` 取未生成指针的控件时会 FAIL | 与 F1 同源；改用生成器支持的控件后自然规避（T5） |
| F8 | `check_all #14` 的字段全集（SampleUI 基准）要求 checkbox 恒有 `bgColorTab`，而 `html2json` 有图时会 `pop bgColorTab` | 工具链内部口径冲突 | 走 F1（两态按钮）后不再触发（D18） |
| F9 | 编译平台口径：Manifest 写 `platform="F136"`（工具链**不接受 `F135`**） | `fun build -p F133` 在本地注册表缺 easyui 包时因 include 路径缺失而失败 | F133 工程用 `fun build -p F136`（同 RISC-V 工具链）（F133 案例 README §4） |
| F10 | ZKPainter `drawArc` 实参口径**两套记录冲突** | 照抄可能画错 | 按 Z21(easyui 2.6.0) 实测 `(cx,cy,rx,ry,start,sweep)`；用前小图自证（`widget-code-api.md`） |
| F11 | `ZKListView::setSelection()` **只改滚动位置、不触发重排+重绘** | 「行位置与选中样式错位」/看起来没刷新 | 数据变更后必须走 `refreshListView()`；刷完要定位末项则 `setSelection(count-1)`（顺序不能反） |
| F12 | Z21 是**共用真机**，`/tmp/ui` 会被其它会话覆盖；`/tmp` 是 tmpfs（36MB 内存板） | 抓图/验收串场拿到别的工程；推大文件触发 OOM 杀 `zkgui` | 验收脚本「一条命令内做完部署→修复→重启→注入→抓图」；只推必需小工具、用完删 |

---

## 6. 本轮裁定与相对两案例的差异（留痕）

| # | 项 | 两案例原写法 | 本轮裁定 | 影响 |
|---|---|---|---|---|
| C1 | **Tab / 页签容器** | LVGL 案例用「2 个整屏 `ZKWindow` 显隐 + 页签按钮」，并在差异清单里写「无原生 tabview」 | **统一走 `pagewindow`（ZKPageWindow）**：自带滑动切页 + `onPageChange`；页签条用按钮组 | 旧写法**丢手势滑动**；`lvgl-widgets` 属历史实现，新工程不得照抄（本表 1.2/1.3） |
| C2 | **缺口级别** | LVGL 用 `A/B/C/D`；小程序用 `L1~L5`（另一套定义） | 统一为 **L1 等价 / L2 组合 / L3 自绘 / L4 降级 / L5 不支持**，逐条换算（§0.1），并列取差、自绘记 L3 | 两案例文件里的旧级别**保留原样**（不改案例工程），换算关系以本表为准 |
| C3 | **3D 口径** | 两案例都只在「不涉及 3D」处顺带写死 | 提级为**硬口径**：Z21/F133 一律伪 3D/2.5D；真 3D 只认 V85X（见 4.5 + `gap-list.md` §3） | 任何 3D 需求先落伪 3D 方案 |
| C4 | **工具链事实** | 散落在两案例的 §3.1/§6 | 收拢成 §5（F1~F12），可检索、可引用，映射表逐行点名 | 不再重复踩坑 |
| C5 | **dropdown/picker** | CANDIDATES 草案写「无原生 dropdown」；两案例分级不同（B/7 vs L3/D6） | 统一 **L4**（组合可行但无滚轮惯性/多列联动 + 展开位变化 → 并列取差） | 候选组件 `picker` |
| C6 | **switch/checkbox** | 草案写 `ZKCheckbox`；小程序案例因 F1 改两态按钮 | 统一：**目标控件 `ZKCheckbox`，实际落地两态 `button__N`**（级别 L2，拖拽过渡降级点 L4） | 候选组件 `switchbtn` |

---

## 7. 相关文件

- ★**机读映射索引**：`../../mcp_control_map.json`（212 条）+ MCP op **`flythings_map_control(query, source)`**
  （能力说明：`knowledge/uicontrols/control-mapping-capability.md`）
- 逻辑映射（事件/定时器/列表/导航/状态）：`logic-map.md`
- 缺口清单 + 五级处置 + 3D 策略 + 工具链坑：`gap-list.md`
- 平台口径（分辨率/rotate/easyui 版本与控件可用性差异）：`platforms.md`
- 候选组件登记表（为替代源控件而做的实现）：`components.md`（三段：已实现自定义控件 / 映射项 / 计划）
- 映射项接线留档（有平台对应控件、不算控件包）：`_mapping/`
- 案例（真机证据）：`examples/README.md`
- 知识库侧摘要 + 指针：`knowledge/uicontrols/framework-control-mapping.md`
