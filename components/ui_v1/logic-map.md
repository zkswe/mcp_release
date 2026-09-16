# logic-map.md — 跨框架逻辑映射（事件 / 定时器 / 列表 / 导航 / 状态）

> 与 `control-map.md` 配套：控件面在那边，**程序面（页面代码怎么驱动）**在这边。
> 合并来源：`projects/translate/lvgl-widgets/TRANSLATE.md` §2、`projects/translate/miniprogram-form-list/TRANSLATE.md` §2
> （含 §2.3 跨页面/工程级）、`projects/translate/CANDIDATES.md` §四、`knowledge/devflow/activity-code-skeleton.md`、
> `knowledge/uicontrols/widget-code-api.md`、`knowledge/devflow/page-architecture-spec.md`。
> 建立：2026-09-16（v0.27.71-open）

---

## 1. 一张总表（源写法 → FlyThings 写法）

| 面 | 源写法（小程序 / LVGL / Qt / Android） | FlyThings 写法 | 落地要点 / 坑 |
|---|---|---|---|
| **事件绑定** | `bindtap`/`bindchange`/`catchsubmit`、`lv_obj_add_event_cb(obj,cb,LV_EVENT_CLICKED,ud)`、`connect(slot)`、`setOnClickListener` | **回调表分发**：`bool onButtonClick_<Caption>(ZKButton*)`（`REGISTER_ACTIVITY_BUTTON_TAB`） | `fun build` 扫 ftu 控件**自动生成**绑定；回调**逐个人工显式定义**（禁宏批量生成）。`true`=吞事件 / `false`=走系统默认（模板注释写反，别信） |
| **值变化（开关/复选）** | `lv_event_get_code()==LV_EVENT_VALUE_CHANGED`、`bindchange`、`OnCheckedChangeListener` | `void onCheckedChanged_<Caption>(ZKCheckBox*, bool)`（两态按钮则走 `onButtonClick_*` + `setSelected()/isSelected()`） | ⚠️ 事实 F1：`checkbox__` 无生成器支持 → 用两态按钮（状态存控件上）；`setChecked()` 也会触发回调 → 注意回环 |
| **值变化（单选组）** | `radio-group bindchange`、`RadioGroup.setOnCheckedChangeListener` | `void onCheckedChanged_<Caption>(ZKRadioGroup*, int checkedID)` | 回调给的是**选中项控件 ID**（`switch ID_MAIN_RadioButtonX`），不是索引；程序选中用 `setCheckedID()` |
| **值变化（滑块/进度）** | `slider bindchange`、`lv_slider` VALUE_CHANGED、`OnSeekBarChangeListener` | `void onProgressChanged_<Caption>(ZKSeekBar*, int progress)` | 拖拽中连续触发；**拿不到起止**（要起止换 `ZKSeekBar::ISeekBarChangeListener`，会顶掉 Activity 分发）；进度条量程 `setMax()` |
| **值变化（输入框）** | `input bindinput`、`lv_textarea` VALUE_CHANGED、`TextWatcher` | `void onEditTextChanged_<Caption>(const std::string&)` | **每敲一键触发一次** → 勿放重量级逻辑；取内容 `getText().c_str()` |
| **点击（列表行 / 子项）** | `wx:for` + `bindtap(data-index)`、`onItemClick`、`OnItemClickListener` | `void onListItemClick_<Caption>(ZKListView*, int index, int id)` | `id` = **被点子控件 ID**（`switch ID_MAIN_SubXxx` 区分是点行还是点行内按钮）；index 为 0 起的行号 |
| **点击（宫格轮播）** | `swiper bindchange`、`tileview` event | `void onSlideItemClick_<Caption>(ZKSlideWindow*, int index)` | index 是**跨屏全局下标**（非本屏第几个）；内容静态配在 json `items[]` |
| **翻页（tab / pager）** | `ViewPager.addOnPageChangeListener`、`lv_tabview_set_active`、`QTabWidget currentChanged` | `ZKPageWindow::IPageChangeListener::onPageChange(pPageWindow, page)`（`setPageChangeListener(&l)`）+ `turnToNextPage()/turnToPrevPage()` | ★**本轮修正**：tab 类容器一律 `pagewindow`（自带滑动 + 手势）；页签按钮选中态在 `onPageChange` 里回设，两向同步 |
| **生命周期** | `Page.onLoad/onUnload/onShow/onHide`、`lv_screen load/unload`、`onCreate/onDestroy`、`QWidget showEvent` | `onUI_init / onUI_show / onUI_hide / onUI_quit`（+ `onUI_intent`） | 六个一个不少；**`onUI_init` 里必须调 `INIT_UI_TIMERS`**（漏了定时器不跑）；资源释放走 `onUI_quit` |
| **定时器 / 动画步进** | `setInterval/setTimeout`、`lv_timer_create`、`QTimer`、`Handler.postDelayed` | `REGISTER_ACTIVITY_TIMER_TAB = {{0,100},{1,500}}` + `INIT_UI_TIMERS` + `bool onUI_Timer(int id)` | id 不重复；毫秒级 tick；动画 = tick 内自算值（可自写缓动）；**别忘 `INIT_UI_TIMERS`** |
| **状态 / 数据模型** | 小程序 `data`+`setData`、`lv_chart_set_next_value`、ViewModel、Qt signal/slot | `logic.cc` 内 `static` 变量为**唯一数据真源** + `updateUi()` 单入口刷控件 | 单一刷新入口，避免散点 `setData`；跨线程用锁，**UI 只在 UI 线程刷** |
| **列表数据源** | `wx:for`、Adapter、`lv_list`、`QAbstractItemModel` | `getListItemCount_<Caption>()` + `obtainListItemData_<Caption>(ZKListView*, ZKListItem*, int index)` | 行**全量覆盖**（复用模板）；**禁耗时**（滚动逐项调用）；行自身 `setText("")` 否则与 subItem 叠字（事实 F4） |
| **列表刷新** | `setData` 重渲染、`notifyDataSetChanged`、`refreshListView` | `mListPtr->refreshListView()` | ⚠️ `setSelection()` **只改滚动位置不重绘**（事实 F11）；数据变更后必须 refresh；要定位末项先 `setSelection(count-1)` 再刷新 |
| **列表空态 / 计数** | `wx:if="{{list.length==0}}"` | `getListItemCount_*()` 里顺带做空态提示（返回 0 + 切提示控件） | 官方 Demo 套路 |
| **到顶 / 到底** | `bindscrolltoupper/lower`、`OnScrollListener` | `on<Page>ActivityTouchEvent` 里按 `ev.mY` 与列表区上下界比较 | 平台 listview **无到顶/到底回调** → 近似判定（control-map 3.12，L4） |
| **滚动位置 / 进度** | `bindscroll`、`getScrollY()` | `on<Page>ActivityTouchEvent`（`E_ACTION_MOVE`）算进度 | 只做轻量状态更新（control-map 3.13，L4） |
| **滚动驱动动画** | `this.animate({opacity/scale/borderRadius},{scrollSource})`、`<wxs>` 动态 style | 触摸位移 → 数值联动（`seekbar`/`textview` 百分比） | 无 CSS 引擎/无插值（control-map 3.11，L4） |
| **页面 / 路由** | 小程序 `navigateTo/redirectTo/navigateBack`、Android `Intent`+`startActivity`、Qt `QStackedWidget` | `EASYUICONTEXT->openActivity("xActivity")` / `closeActivity()` | **页栈 ≤2**（硬限制）；`onUI_intent` 收参 |
| **页内分页** | `ViewPager`+Fragment、`QStackedWidget`、多 `tab` | `showWnd()/hideWnd()`（同 ftu 多整屏 window）或 **`pagewindow`**（要手势） | 要不要独立生命周期/返回语义 → 见 `devflow/page-architecture-spec.md` 决策清单 |
| **弹窗 / 弹层显隐** | `picker` 弹层、`showModal`、`Dialog.show()`、`lv_layer_top()` | `window__N`（`modal:true`）+ `showWnd()/hideWnd()/isWndShow()`；或 `setVisible(true/false)` | 二者不等价：`showWnd` 无视 json 初始 `visible=false`；`modal` 拦截底层点击 |
| **轻提示自动关** | `wx.showToast({duration})`、`Snackbar` | `showWnd()` + `hideTimeOut` 2~3s（自动关） | 组合小件（control-map 1.8，L2） |
| **系统键盘** | 自制 `lv_keyboard`（源撑高布局） | **系统内置键盘**（`ZKEditText` 点击自动弹） | 源自制键盘整段丢弃（平台有更完整输入法）；属 L1 平台差异 |
| **触摸命中 / 自绘区点击** | 框架 hit-test、`onTouchEvent` | `bool on<Page>ActivityTouchEvent(const MotionEvent &ev)` + `LayoutPosition::isHit(x,y)` | painter **无点击回调** → 自绘区（如 42 格日历）由 activity 触摸事件**反算行列** |
| **触摸开关 / 穿透** | `setEnabled`、`clickable`、`pointer-events:none` | `pCtrl->setTouchable(false)` + **`setTouchPass(true)`**（`touchPass` **不是 json 字段**，只能代码设） | 压在可触摸控件上的装饰件必须补穿透，否则下层拖不动（`uicontrols/touch-events.md` §1） |
| **自绘刷新** | 框架自动合成 `lv_obj_invalidate()` | **`ZKPainter` 不自动重绘** → `onUI_init`/`onUI_show`/每个改数据的回调里显式 `renderXxx()` | 统一入口（如 `renderCharts()`），翻页回来必须重画 |
| **主题 / 换色** | `lv_theme_default_init`、`QSS`、`wx.onThemeChange` | 无 theme 引擎 → `static uint32_t s_primary` + 逐控件 `setTextColor()` + painter 用新色重绘 | 系统主题事件不支持（L5）；应用内换色可做（control-map 4.3） |
| **样式效果 → 资源** | CSS radius/shadow/gradient、`lv_style_set_*` | `html2json` **自动转图**（圆角 / 线性渐变 / shadow+radius 一键出 PNG，尺寸 == 控件盒） | 无 CSS 引擎，不能 1:1；转不了的（径向渐变/文字阴影/变换/滤镜/透明度）要手工切图 |
| **随机数** | `Math.random()`、`lv_rand()` | 自带 LCG（不用平台 `random()`） | 固定种子 → 两次上图像素可比对（便于验收） |
| **持久化** | `wx.setStorage`、`SharedPreferences`、`QSettings` | 设备侧文件 / 配置接口（按平台能力） | 纯交互演示不引 StoragePreferences（避免「模拟数据写 flash」） |
| **异步 / 网络 / 串口** | `wx.request`、`fetch`、Retrofit、`QNetworkAccessManager` | 线程 + 回调；**UI 刷新交给定时器轮询**（保守做法） | 网络 Manager 异步一律 `addXxxListener`（回调在 Manager 内部线程，数据拷贝加锁） |
| **重活（解码/IO）** | WebView 线程、`AsyncTask`、`QThread` | 自研控件用 `MessageQueueThread` 投递工作线程，完成后触发重绘 | 页面级也可用 `Thread::readyToRun/threadLoop`；析构要停线程 |
| **多指缩放 / 手势** | `touchstart/move` 多点、`ScaleGestureDetector` | `event::multi_touch`（全局多点分发 `TouchPoint` 列表）+ 控件 `onTouchEvent` | 参考 `ImageBoxView`（prepareScale/processScale） |
| **多语言** | `i18n @key`、`strings.xml`、`tr()` | `@key` + i18n 工具链（`i18n_tools`） | 案例本轮不做多语言（英文硬编码，与源一致） |
| **页面注册 / 工程结构** | `app.json` `pages`/`subPackages`、AndroidManifest | `ui/*.ftu` → `fun build` 自动生成 `ui_<page>.h/.cpp` + `REGISTER_ACTIVITY`；`src/logic/<page>Logic.cc` 每页一个 | `manifest.xml` 的 `activities` 决定入口（`mainActivity`）；起始页 = `pages[0]` |
| **业务域目录** | 各框架自由 | `src/<业务域>/`（小写英文单数，如 `src/network/`、`src/media/`），**不设 core/modules 中间分层** | 见 `devflow/page-architecture-spec.md` |
| **控件字段写法** | `android:hint`、`lv_label_set_text()`、`LV_EVENT_CLICKED`… | FlyThings 对照：`hintText`、`setText()`、`onButtonClick_XXX` | ⛔ **禁止套用别家控件字段/API**（`uicontrols/retrieval-boundary.md`）；业务逻辑随便参考，控件实现只查 MCP/官方 |
| **缺失能力自检** | — | MCP op 候选 `translate_lint`：扫 logic/json 是否残留源框架专有概念（`setData`/`wx:`/`flex`/CSS 动画）+ 差异是否登记 | 防「假装能转」（候选组件，见 `components.md`） |

---

## 2. 四个"必须记住"的最小骨架

```cpp
// ① 回调逐个显式定义（禁宏批量）；框架按 TAB 分发
static bool onButtonClick_BtnSubmit(ZKButton *pButton) { /* ... */ return false; }

// ② 定时器：表 + onUI_init 里的 INIT_UI_TIMERS + onUI_Timer
static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = { {0, 100}, {1, 500} };
static void onUI_init() { INIT_UI_TIMERS(); /* ... */ }
static bool onUI_Timer(int id) { /* id0@100ms / id1@500ms */ return false; }

// ③ 列表三件套（行全量覆盖 + 禁耗时 + 行自身 setText("")）
static int getListItemCount_ListDemo(const ZKListView *pListView);
static void obtainListItemData_ListDemo(ZKListView*, ZKListView::ZKListItem *pListItem, int index) {
    pListItem->setText("");                       // 事实 F4：不清空会与 subItem 叠字
    pListItem->findSubItemByID(ID_MAIN_SubName)->setText(g_rows[index].name);
}
static void onListItemClick_ListDemo(ZKListView*, int index, int id) { /* ... */ }

// ④ 数据变了：先定位、再刷新（顺序不能反）
mListDemoPtr->setSelection(count - 1);            // 只改滚动位置（事实 F11）
mListDemoPtr->refreshListView();                  // 才是真正重排+重绘
```

---

## 3. 相关文件

- 控件映射（★ 权威）：`control-map.md`　·　缺口/坑/3D：`gap-list.md`　·　平台口径：`platforms.md`
- 候选组件（逻辑类）：`refresher` / `list_select` / `choicegroup` / `picker` / `translate_lint` → `components.md`
- 代码骨架：`knowledge/devflow/activity-code-skeleton.md`　·　控件 API：`knowledge/uicontrols/widget-code-api.md`
- 页面架构（ftu vs 页内 window vs 容器控件）：`knowledge/devflow/page-architecture-spec.md`
