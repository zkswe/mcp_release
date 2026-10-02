# components/ui_v1/Calendar —— 日历选择器 `zk::ui_v1::Calendar`

> **替代哪个源控件**：LVGL `lv_calendar` ｜ 小程序 `picker mode=date` ｜ Android `DatePicker` / `DatePickerDialog` ｜
> Qt `QCalendarWidget` ｜ MFC `CDateTimeCtrl` / `CMonthCalCtrl`
> **建立**：2026-09-16（经需求方纠正口径：做成能用的自定义控件包，一个源控件一个目录）
> **版本**：0.1.0 ｜ **状态**：已实现（含 Z21 真机证据）｜ **级别**：**L4（降级实现，平台无日历控件）**
> **缺口**：`gap-list.md` G-22（无日期/日历控件）

---

## 1. 我们怎么做（42 个 textview + 业务侧触摸反算）

平台**没有**日历控件（也没有日期滚轮），所以本组件的形态是写死的：

| 组成 | 用什么 | 谁负责 |
|---|---|---|
| 7×6 = 42 个日号格 | `ZKTextView` × 42（行优先摆放，**顺序必须与 json 一致**） | 组件写文字/颜色，业务在 json 里摆位置 |
| 月份标题 | `ZKTextView` × 1 | 组件写 `"%d-%02d"`（如 `2026-09`） |
| `<` `>` 翻月 | `ZKButton` × 2 | 组件**不接管点击**：业务回调里调 `prevMonth()/nextMonth()` |
| 表头（一…日） | `ZKTextView` × 7 | 业务（组件不管） |
| 命中判定 | **业务**在 activity 触摸事件里 `cellAt()/dayAt()` 反算 | 组件（平台 textview 没有点击回调） |
| 月天数 / 星期算法 / 状态机 | 组件 | 组件 |

三条硬约束（决定了 API 长什么样）：

1. **textview 没有点击回调**→ 组件**不装触摸监听**。业务在 `onmainActivityTouchEvent` 里把
屏幕绝对坐标丢给 `cellAt()/dayAt()`，拿到日号后调 `pickDay()`。
2. **绝对坐标**：设备侧 `libeasyui.so` **没有导出**`getParent()` / `getAbsolutePosition()`（用了会整屏黑、无日志），
所以组件只能「容器原点（业务给 `setContainer()`）+ 首格相对坐标（`getPosition()`）」。
3. **改月/改选中/改标记后必须 `refresh()`**才看得见（没有任何自动重绘）。

## 2. 怎么用（28 行可跑：组件 + 命中 + 翻月 + 回填）

> ★★ **`setContainer()` 什么时候「必调」（先看这条再抄代码）**
>
> | 网格摆在哪 | 要不要调 | 不调的后果 |
> |---|---|---|
> | 放在**非原点**的容器里（例：`WinCal` 在 `(162,40)`；案例那种 `(312,112)` 的 modal；卡片里的网格） | ★★ **必调**`setContainer(那个容器)` 或 `setContainerOrigin(x,y)` | `cellAt()/dayAt()` 的命中区域**整体偏移**容器原点那段距离 → 表现为「**点日号没反应**」或「**点错一天**」（组件不会崩、也不会报错，因为偏移后的矩形仍是合法坐标） |
> | 网格**直接铺在 activity 根 / 全屏 window**上 | 可以不调（原点默认 (0,0)） | — |
> | 容器还嵌在更深的容器里 | 必调，且传**各层 `getPosition()` 之和**：`setContainerOrigin(a.mLeft+b.mLeft, a.mTop+b.mTop)` | 同上（只算一层 = 仍偏移） |
>
> 为什么组件不能自己搞定：设备侧 `libeasyui.so` **没有导出**`getParent()` / `getAbsolutePosition()`（用了会整屏黑无日志），
> 组件**无法**从格子往上走到容器 —— 所以「容器原点」只能由业务给。自检：`hasContainer()` 返回 false 且网格不在原点 → 就是漏了。

```cpp
#include "zk/zk_calendar.h"

static zk::ui_v1::Calendar s_cal;
static ZKTextView *s_cells[42];          // = mTvCalD1Ptr .. mTvCalD42Ptr（行优先）

/* ① 选中回调：回填输入框（组件在 pickDay() 里同步调用） */
static void onDatePicked(const zk::ui_v1::Calendar::Date &d, void *user) {
    (void)user;
    char buf[32];
    snprintf(buf, sizeof(buf), "%04d-%02d-%02d", d.year, d.month, d.day);
    mEtDatePtr->setText(buf);
}

/* ② 初始化（onUI_init）：attach -> 容器原点 -> 样式 -> 今天/标记 -> 定位 -> refresh */
static void onUI_init() {
    bindCells();                                   // s_cells[] = mTvCalD1Ptr ...（42 个）
    s_cal.setStyle(zk::ui_v1::Calendar::Style());
    s_cal.attach(s_cells, mTvCalTitlePtr, mBtnCalPrevPtr, mBtnCalNextPtr);
    s_cal.setContainer(mWinCalPtr);                // ★ 网格所在容器（绝对坐标的前提）
    s_cal.setOnDatePicked(onDatePicked);
    s_cal.setHighlightPainter(mPtCalHlPtr);        // ★ 选中高亮色块 = 单独 painter（见 §4）
                                                   //必须与 42 格**同父**、z 更低（json 里先定义）
    s_cal.setHighlightShape(zk::ui_v1::Calendar::HIGHLIGHT_CIRCLE);   // 默认就是圆
    s_cal.setHighlightInset(2);                    // 圆直径 = min(格宽,格高) - 2*inset
    s_cal.setToday(2026, 9, 16);                   // 「今天」高亮
    int marks[2] = { 5, 20 };
    s_cal.setMarkedDays(marks, 2);                 // 标记日
    s_cal.setDate(2026, 9, 0);                     // 定位到 2026-09，不选中（d == 0）
    s_cal.refresh();                               // ★ 不调什么都不显示
}

/* ③ 点日号：业务反算命中 -> pickDay -> refresh（组件不装触摸监听，这就是全部接线） */
static bool onmainActivityTouchEvent(const MotionEvent &ev) {
    if (ev.mActionStatus != MotionEvent::E_ACTION_UP) return false;
    if (mWinCalPtr == NULL || !mWinCalPtr->isWndShow()) return false;   // 只在窗口可见时处理
    const int day = s_cal.dayAt(ev.mX, ev.mY);     // 屏幕绝对坐标；0 = 空格/未命中
    if (day > 0) {
        s_cal.pickDay(day);                        // 选中 + 触发回调
        s_cal.refresh();                           // ★ 改选中必须 refresh
    }
    return false;
}

/* ④ 翻月 */
static bool onButtonClick_BtnCalPrev(ZKButton *p) { (void)p; s_cal.prevMonth(); s_cal.refresh(); return false; }
static bool onButtonClick_BtnCalNext(ZKButton *p) { (void)p; s_cal.nextMonth(); s_cal.refresh(); return false; }
```

## 3. API

| 成员 | 说明 |
|---|---|
| `Result attach(ZKTextView *const cells[42], ZKTextView *title = 0, ZKButton *prev = 0, ZKButton *next = 0)` | 绑 42 格 + 标题 + 翻月按钮；`cells[0]` 不能空（用它反推网格几何） |
| `void detach()` | 解绑（`onUI_quit`） |
| `Result setContainer(ZKBase *c)` / `Result setContainerOrigin(int x, int y)` / `bool hasContainer()` | **容器原点**（屏幕绝对左上角）。网格铺在 activity 根/全屏 window 上时原点就是 (0,0)，可不调；嵌套时传「各层 `getPosition()` 之和」 |
| `Result setDate(int y, int m, int d)` | 定位日期；**d == 0 → 只定位月份、不选中**；`d` 超出当月天数 → `-2` 且不改状态 |
| `Date date() const` | 当前状态（未选中 `day == 0`） |
| `Result setMonth(int y, int m)` / `prevMonth()` / `nextMonth()` | 翻月，**不触发回调**；月份越界会自动归一（如 13 → 次年 1 月，返回 `code=1` 说明）；原选中日号在新月份不存在时清成未选中 |
| `void setOnDatePicked(DatePickedFn fn, void *user = 0)` | 选中回调（UI 线程、`pickDay()` 内同步调用） |
| `Result pickDay(int day)` | 编程选中某日（**会触发回调**）；不在当月 → `-1` |
| `Result setMarkedDays(const int *days, int n)` | 标记日（`n <= 0` 清空；不在当月的日号忽略并在 `msg` 说明） |
| `Result setToday(int y, int m, int d)` | 「今天」高亮（`d == 0` 关闭） |
| `int cellIndexOfDay(int day) const` | 日号在当前月是第几格（0..41；不在当月 → `-1`） |
| `int cellAt(int absX, int absY) const` | 屏幕绝对坐标 → 格下标 0..41 / **-1**（网格外、格子间隙、未 attach） |
| `int dayAt(int absX, int absY) const` | 同上，直接给日号（**0 = 空格/未命中**） |
| `Result setHighlightPainter(ZKPainter *p)` | **选中高亮色块**：在**选中格位置**画实心高亮（填充色 = `Style::selBg`）；painter 必须**与 42 格同父**、z 更低。幂等（重复接/换一个都直接生效）。`code: 0` / `-1` p 为空（等于 detach）/ `-2` painter 尺寸为 0 | 
| `void detachHighlightPainter()` / `bool hasHighlightPainter()` | 摘掉/查询高亮画布（摘掉后回到「只写文字色 + `selTextFallback` 兜底」） |
| `Result setHighlightShape(HighlightShape s)` / `HighlightShape highlightShape()` | 高亮形状：`HIGHLIGHT_CIRCLE`（默认，**带抗锯齿**）/ `HIGHLIGHT_SQUARE`（内缩矩形，硬边）。别名 `CIRCLE`/`SQUARE` |
| `Result setHighlightInset(int px)` / `int highlightInset()` | 高亮相对格子四边的内缩（默认 2；夹到 `0..min(格宽,格高)/2`，越界返回 `code=1`） |
| `const std::string &lastWarning() const` | 上一次 `refresh()` 的自检告警（空 = 无）。例：「未接高亮 painter → 选中文字已回落 `selTextFallback`」 |
| `Result refresh()` | 重建文字 + 高亮（**改月/改选中/改标记/改今天后必须调**）。`code: 0` OK / `1` OK 但走了兜底（选中文字换成 `selTextFallback`，`msg` 说明）/ `-2` 接了 painter 但尺寸为 0（高亮画不出来）/ `-1` 未 attach |
| `void setStyle(const Style &)` / `const Style &style()` | 样式（见 §4） |
| `enum { COLS = 7, ROWS = 6, CELLS = 42 }` | 网格规模（编译期常量，**无动态分配**） |
| `struct Result { int code; std::string msg; bool ok(); }` | 统一结果类型（`components/README.md` 规范 2）：`code 0` = OK、`1` = 已接受但降级、`<0` = 出错 |

## 4. 样式与高亮（**painter 色块 + 文字兜底**）

高亮 = **`setHighlightPainter(painter__N)` 画的实心块**（填充色 `Style::selBg`，形状/内缩可配，圆带抗锯齿）
+ **格子里的文字色**。为什么不直接用 textview 底色：见下面的平台事实。

| 字段 | 作用 | 本代平台是否生效 |
|---|---|---|
| `selBg` | **选中高亮块填充色**（由 highlight painter 画；默认主蓝 `0xFF2196F3`） | ✅ 生效（**前提：接了 painter**） |
| `selText` + `selBold` | 选中日：文字色 + 加粗（默认深蓝 + 加粗） | ✅ 生效（题面文字，压在 `selBg` 色块上） |
| `selTextFallback` | **兜底选中文字色**（默认 `0xFF0D47A1` 深蓝）：没接 painter / painter 尺寸为 0 / `selText` 与所在底色太近（亮度差 ≤ 40）时**自动启用 + 加粗**| ✅ 生效（防呆硬规则，见下） |
| `markText` | 标记日文字色（默认橙棕） | ✅ 生效 |
| `mutedText` | 「今天」文字色（默认浅灰；不想区分今天可设成 == `cellText`） | ✅ 生效 |
| `cellText` / `titleText` | 普通日号 / 月份标题文字色 | ✅ 生效 |
| `cellBg` | 普通格底色 **== highlight painter 的基底色**（painter 无 alpha，铺底 + 混色只能以它为准） | ✅ 生效（★ 必须 == 网格区真实底色，否则 painter 会露出一块色差方块） |
| `markBg` | 标记日底色（ARGB 口径） | ❌ 本代平台不生效（textview 画不出底色） |

> ★ **防呆硬规则（2026-09-16 加）**：`refresh()` 每次都会自检 ——
> **接了 painter**时比 `selText` vs `selBg`；**没接 painter**时比 `selText` vs `cellBg`。
> 一旦「两者太近（亮度差 ≤ 40）」或「没接 painter / painter 尺寸为 0」→ 选中文字**自动换成
> `selTextFallback` + 加粗**，并把原因写进 `refresh()` 的返回值（`code=1`/`-2` + 人话 `msg`）和 `lastWarning()`。
> 这样「白字 + 白底 = 选中项看不见」在**任何接线失误下都不会再发生**（`mainLogic.cc` 里用 `calRefresh()` 打日志）。
>
> ★ **抗锯齿口径**（与 `RadButton` 同一套）：painter 只有不透明 fill（无 alpha），
> 所以**先铺已知底色**（`Style::cellBg`）再用**逐像素覆盖率**（8×8 超采样 → 65 档中间色）与底色混色 ——
> 这是本平台唯一的「半透明」。代价：AA 只在「底色是纯色」时精确（底为图片/渐变时边缘会偏）。
> 边缘覆盖率 < 0.4% 的像素不画（沿用 RadButton 口径）。

> **平台事实（Z21 easyui 2.6.0 实测，2026-09-16）**：`ZKTextView` 底色**在弹窗内画不出**。
> **2026-09-16 晚复核（口径收窄，重要）**：上面这条**只在 `div.modal` 弹窗内成立**。
> 反例（同一台 Z21、同一代 easyui）：案例顶栏下划线的 `TvTabMark` 就是一个 json `bgColorTab` 的 **textview**，
> 真机像素实测为 **140x3 实心蓝条（420 px 命中 0x2196F3）**，即**普通容器里 textview 底色是能画的**。
> 本组件全在弹窗里，所以对本组件等价于「画不出」；差异与容器有关，**根因未定位**（别当成全局结论）。
> ① json 里的 `bgColorTab` 不画；② `setBackgroundColor()`（6 位色、带 alpha 的 0xAARRGGBB 都试过）不画；
> ③ `setBgStatusColor(NORMAL/SELECTED/INVALID, …)` 不画；④ `setBackgroundBmp()`（运行时生成小位图）
> **能画出来**（`setBackgroundPic()` 也行），**但翻月时重设底色会把应用直接搞崩**（无任何日志；
> 「同指针跳过」「每格独占位图」两种写法都崩）。
> 所以本组件把 `*Bg` 三个字段**保留为口径约定但不使用**，高亮统一走文字色 + 加粗。
> 要色块底请在业务侧摆一层「常态按钮/图片」当高亮块（按钮的底色在这代平台是正常画的，见 example 的白底卡片按钮）。
> 复现与详细记录见 `platforms.md`。

## 5. 已知限制（写清楚）

1. **高亮的色块底必须自己摆 painter**：textview 底色在**弹窗内**画不出来（普通容器里可用，根因未定位，见 §4 平台事实）
   → 选中块的底色由 `setHighlightPainter(painter__N)` 画。**没接 painter 也能跑**，但此时只能退回
   「`selTextFallback` + 加粗」，选中态没有色块（老案例的观感）。
2. **不显示邻月日期**：本月之外的格子一律 `setText("")`（空）。要显示灰色邻月日期需业务自己摆（组件不做）。
3. **只能逐月翻**：没有年/月下拉、没有长按连翻（案例口径一致）。
4. **组件不装触摸监听**：点击必须由业务在 activity 触摸事件里反算（这是平台的限制，不是偷懒）。
5. **翻月会清掉「已选日号」当新月份没有那一天时**（如 1 月 31 日 → 2 月）；有选中日被清掉时 `setMonth` 返回 `code=1` 并说明。
6. **`refresh()` 至少要调一次**（`onUI_init` 末尾），否则格子是空的。

## 6. 依赖与线程模型

- **依赖包（Z21/实测）**：`easyui`（`ZKTextView` / `ZKButton`）+ 工程常规 `log / zkhardware / zknet / base-utility`。见 `Manifest.xml`。
- **线程模型**：**全部在 UI 线程**；无定时器、无锁、无阻塞、无动态分配。
回调（`DatePickedFn`）在 `pickDay()` 内部**同步**触发，回调里只做轻量事（写文字/输入框），别做耗时操作。

## 7. 真机验收记录（Z21 1024×600，2026-09-16）

| 验收项 | 命令/判据 | 结论 | 证据 |
|---|---|---|---|
| 编译 | `fun build` | ✅ 无警告无错误 | — |
| 静态全检 | `python tools/ui_tools/check_all.py <工程>` | ✅ 全部 PASS（9 条 WARN = 「卡片按钮当白底」被装饰件压住，**已人工确认无碍**：该按钮 `setTouchable(false)+setTouchPass(true)`，不需要收事件） | — |
| 打开日历 / 当月网格 | `touch tap 180 208` | ✅ `2026-09`；2026-09-01 落在**周二**列（`weekdayOfFirst` 正确）；今天 16 浅灰；标记日 5/12/18/25 橙棕 | `evidence/01_initial.png` |
| 翻月 | `touch tap 806 78`（`>`） | ✅ 标题变 `2026-10`；2026-10-01 落在**周四**列；标记日跟着移到 10 月（5/12/18/25）；状态行 `下一月：2026-10（未选日）` | `evidence/02_next_month.png` |
| **点日号（命中反算 + 回调回填）**| `touch tap 218 78`（回 9 月）→ `touch tap 586 247`（点 18） | ✅ 18 号变**深蓝加粗**；弹窗内状态行 `已选：2026-09-18（弹窗内即时可见）`；**输入框同步回填**（见 05）；`ui_diff`：**16 处差异 / 25,541 像素**，差异块集中在「18 号格 + 状态行 + 弹窗状态行 + 输入框」四处（**没有整屏乱刷**） | `evidence/03_day_picked.png`、`evidence/04_diff_initial_vs_picked.png` |
| OK 关窗 + 输入框回填 | `touch tap 322 480` | ✅ 窗口关闭；输入框显示 `2026-09-18`；状态行 `OK：已确认 2026-09-18（输入框已回填）` | `evidence/05_after_ok_edittext_filled.png` |
| 跳到今天（`setToday` + `setMarkedDays`） | `touch tap 180 414` | ✅ 回到 2026-09 并重新高亮：今天 16 浅灰、标记改成 3/11/20（橙棕）、原选中 18 仍深蓝加粗 | `evidence/06_today_and_marks.png` |

> 像素判据可复现：`python tools/ui_tools/ui_diff.py 01_initial.png 03_day_picked.png --out 04_diff.png`
> （容差 ±2 + 抖动补偿；本组证据的差异块坐标/面积与上表一致）。

### 7.1 选中高亮改 painter（2026-09-16 晚，需求方报「选中项看不见」）

| 验收项 | 判据 | 结论 | 证据 |
|---|---|---|---|
| 现象与根因 | 选中 30 号那格是**纯白块、数字不可见**| 业务设了「`selBg`=主色底 + `selText`=白」，但本代平台 textview **画不出底色**→ 白字落在白卡上 | `example/evidence/…`、案例 `z21/evidence/zzr_08c_calendar_day_selected.png`、`zzr_08k/08l_zoom_daycell_*.png` |
| 包侧修复 | 新增 `setHighlightPainter()`（painter 自绘 AA 实心高亮）+ `setHighlightShape/Inset` + `selTextFallback` 兜底自检 | ✅ 编译通过（`fun build -p Z21`）；`check_all.py` 全 PASS | 本文件 §3/§4；实现 `src/zk_calendar.cpp` |
| 案例侧接线 | `gen_html.py` 在日历弹窗 42 格**之前**加 `painter__143`（caption `PtCalHl`，(16,94,364,212)）；`mainLogic.cc` 接 painter + `cellBg=0xFFFFFF` | ✅ json 里 `PtCalHl` 在 `TvCalD1` 之前（z 更低）；`.ftu` 重 pack 成功 | `z21/ui/main.json`、`f133/ui/main.json` |
| **真机像素验收**| 选中格内出现 `#2196F3` 实心块（> 200 px）且**白色数字像素 > 20**；旧格无残留、无黑块 | ⏳ **待上机**（本地无设备；脚本与判据见下） | 复验清单：`temp/cal_hl/deploy_verify.md` |

> 复验判据（可机核）：`blue = count(|px - (0x21,0x96,0xF3)| <= 2) > 200`、`white = count(全通道 >= 230) > 20`；
> 旧格 `blue == 0` 且 `count(px <= 8) ≈ 0`（没有 painter `erase()` 的不透明黑残留）。

## 8. 排错

| 现象 | 原因 | 处置 |
|---|---|---|
| 格子全空 | 忘了 `refresh()`（或 `attach` 失败被忽略） | 检查 `attach()` 返回值并在 `onUI_init` 末尾 `refresh()` |
| 点日号没反应 | ① 业务没接 activity 触摸事件；② **`setContainer/setContainerOrigin` 漏调**（网格在非原点容器里 → 命中整体偏移）；③ 窗口不可见时也处理了命中 | 按 §2 ③ 的 6 行接线 + **按 §2 开头的表决定要不要 `setContainer`**；`hasContainer()` 可自检；先判断 `isWndShow()` |
| 点日号「点错了一天」 | 容器原点不对（网格在嵌套容器里）；或 cells 摆放顺序与 json 不一致 | 用 `setContainerOrigin(各层 getPosition() 之和)`；核对 `cells[]` 顺序 = json 里的摆放顺序 |
| **选中项看不见（白字白底 / 数字消失）**| ★ 老坑：业务设 `Style.selBg=主色` + `selText=0xFFFFFF`，但**本代平台 textview 画不出底色**（见 §4 平台事实）→ 底没画、白字压在白卡上 | **接高亮 painter**：json 里加一个 `painter__N`（几何 = 网格覆盖区，**定义在 42 格之前**= z 更低）+ `setHighlightPainter()` + `setHighlightShape()/setHighlightInset()`，并把 `Style::cellBg` 设成网格区真实底色。**没接也不能白字白底**—— `refresh()` 会自动回落 `selTextFallback` + 加粗并返回 `code=1`（看 `lastWarning()` / 日志） |
| 选中格是**一块白/灰色差方块**（有高亮但底色不对） | `Style::cellBg` ≠ 网格区真实底色（painter 用 `cellBg` 铺底 + 混色） | 把 `cellBg` 设成容器实际底色（案例是弹窗 `backgroundColor=0xFFFFFF`） |
| 高亮**完全没有**（选中格和普通格一样） | ① 没调 `setHighlightPainter()`；② painter 尺寸为 0（json `position` 缺 `width/height`，`refresh()` 返回 `code=-2`）；③ 忘了 `refresh()` | 按 §2 接线；`hasHighlightPainter()` 自检；`refresh()` 的 `msg` 直接说原因 |
| **42 个日号数字被一块大色块盖住**| painter 被定义在 42 格**之后**（json 里后定义 = z 更高） | 把 painter 挪到 42 格**之前**（`gen_html.py` 里先 `l.raw(painter…)` 再摆 `textview`） |
| 高亮圆边**有锯齿**| 没接 painter 时本来就没块；接了还锯齿 → `Style::cellBg` 与真实底色不一致（混色基准错） | 同「色差方块」那条；`setHighlightShape(HIGHLIGHT_SQUARE)` 可硬边（无 AA 需求） |
| 翻月后选中日号消失 | 原选中日号在新月份不存在（如 31 日） | 预期行为；`setMonth` 会返回 `code=1` 并在 `msg` 里说明 |
| 标题显示成 `2026-9` 之类 | 业务自己写了标题 | 标题交给组件写（`attach` 的 `title` 参数），格式固定 `%d-%02d` |

## 9. 相关文件

- 目录规范（四件套）：`components/README.md`
- 映射口径：`ui_v1/control-map.md`（`lv_calendar` / `picker mode=date`）+ `ui_v1/gap-list.md` G-22
- 自研控件方法论：`knowledge/devflow/custom-widget.md`
- 提炼来源（只读，未改动原工程）：`projects/translate/lvgl-widgets/z21/src/logic/mainLogic.cc`
  （`daysInMonth / weekdayOfFirst / bindCalCells / rebuildCalendar / highlightCal / 触摸反算`）
- 状态表：`ui_v1/components.md`
- 本轮修复的复验脚本/判据：`temp/cal_hl/deploy_verify.md`（工作区，不进发布包）
