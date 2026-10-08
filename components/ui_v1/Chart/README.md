# components/ui_v1/Chart —— 图表集合 `zk::ui_v1::Chart`

> **替代哪个源控件**：LVGL `lv_chart` + `lv_scale` + `lv_arc` ｜ Android `MPAndroidChart` ｜ Qt `QCustomPlot` / `QChart`
> **建立**：2026-09-16（经需求方纠正口径：做成能用的自定义控件包，一个源控件一个目录）
> **版本**：0.2.1 ｜ **状态**：已实现（含 Z21 真机证据）｜ **级别**：**L3（必须自绘）**
> **缺口**：`gap-list.md` G-09 / G-10 / G-11（平台无 chart、无坐标轴、无多环）
>
> **变更记录**
> - **0.2.1**（2026-09-16）：**修 `drawGrid()` 的 Y 刻度值序 bug**—— 槽位 0 写 max 却画在**最下面那条线**，
>导致刻度数字上下颠倒（图形对、字反）。按头文件语义「`labels[0..ticks]` = 值从 max 到 min」改成
>   `y = y0 + i*(H-1)/mTicks`（槽位 0 = max = 最上面那条线）。**Y 刻度值序专项证据**：
>   `evidence/08_yaxis_labels_fixed.png`（0.2.1 重抓首帧，纵轴自上而下 `100,80,60,40,20,0`）+ 
>   `evidence/08c_yaxis_before_after.png`（上=0.1.0 旧帧反序 / 下=0.2.1 修复后，同一块折线图对照）；
>另 `01`~`07` 也已用当前布局整组重抓（2026-09-16 19:08）。
> - **0.2.0**（2026-09-16）：补 **分段环**（`setRingSegments` / `clearRingSegments` / `hasRingSegments`）——
>把案例 Analytics 页那块自绘「三段饼环」收成通用能力：一个环按权重切成 2..8 段、段间 2° 间隙、
>第 1 段从正上方顺时针；只在 `RING` 类型下生效（其它类型返回非 0 + 人话 msg）。
>   example 增加第 5 张图（内 2 段 / 中 3 段 / 外 5 段），真机证据 `evidence/06`、`evidence/07`。
> - **0.1.0**（2026-09-16）：首个版本：LINE / BAR / RING / GAUGE 自绘 + textview 刻度池 + 混色近似 alpha。

---

## 1. 我们怎么做（自绘集合，不是"能配的图表控件"）

平台**没有**图表控件（`diagram` 只能画实时波形，没有坐标轴/柱/环/仪表），所以本组件 =
**`ZKPainter` 自绘 + `ZKTextView` 叠刻度文字**：

| 类型 | 画法 | 提炼来源 |
|---|---|---|
| `LINE` 折线 | 横网格（=刻度线）+ 竖分隔 + 面积填充（**混色近似 alpha**）+ 折线 + 数据点 | `lvgl-widgets` `renderLine()` |
| `BAR` 分组柱 | 网格 + N 系列并排柱（组宽/柱宽按画布宽现算） | `renderBar()` |
| `RING` 同心环 | 每环一条底轨 + 进度弧（0 度=正上方，顺时针为正）；**也可整环切段**（`setRingSegments`：权重归一 + 段间 2° 间隙） | `renderTarget()` + 案例 Analytics 页的三段饼环 `PtSess()` |
| `GAUGE` 仪表 | 分区色弧 + 20 格刻度（每 4 格长刻度）+ 指针 + 轴心 | `renderGauge()`；`EasyDevice-Z21` 的色标/反算思路 |

三条硬约束（决定了 API 长什么样）：

1. **painter 不自动重绘**→ 改数据/改样式后**必须显式 `refresh()`**（`onUI_show` 也要刷一遍）。
2. **painter 无文字 API**→ 刻度文字是业务在 json 里摆好的 `textview`，运行时把**指针池**交给组件，
由组件 `setText/setPosition`。池子必须与 painter **同父**（组件会把 painter 的左上角偏移算进去）。
3. **无 alpha 通道**→ 半透明一律走 `Chart::mix(fg, bg, percent)` 混色（面积填充、底轨都用它）。

## 2. 怎么用（20 行可跑）

```cpp
#include "zk/zk_chart.h"

static zk::ui_v1::Chart s_line;
static ZKTextView *s_y[6] = { mTvY100Ptr, mTvY80Ptr, mTvY60Ptr, mTvY40Ptr, mTvY20Ptr, mTvY0Ptr };
static const float DATA[12] = { 42, 61, 33, 78, 55, 46, 71, 28, 64, 51, 37, 69 };

static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif
    zk::ui_v1::Chart::Style st;            // 默认样式（白底 / 浅灰网格 / 主题蓝系列）
    st.areaFill = true;                    // 折线带面积渐层

    s_line.attach(mPtLinePtr);             // 绑画布
    s_line.setType(zk::ui_v1::Chart::LINE);
    s_line.setAxisRange(0.f, 100.f, 5);    // 0..100，5 段 = 6 条刻度（配 6 个 Y 文字）
    s_line.setStyle(st);
    s_line.attachLabels(s_y, 6);           // 刻度文字池
    s_line.setSeries(0, DATA, 12);
    s_line.refresh();                      // ★ 不调就什么都不显示
}

static bool onButtonClick_BtnNext(ZKButton *p) {
    (void)p;
    s_line.appendPoint(0, 66.f);            // 追加一个点（满 64 丢最旧）
    s_line.refresh();                       // ★ 改完数据必须重绘
    return false;
}
```

## 3. API

| 成员 | 说明 |
|---|---|
| `Result attach(ZKPainter *painter)` | 绑画布（`onUI_init` 里调）；null → 非 0 + 人话 `msg` |
| `void detach()` | 解绑（`onUI_quit`） |
| `Result setType(Type)` | `LINE / BAR / RING / GAUGE` |
| `Result setSeries(int idx, const float *v, int n)` | 整段替换系列（`idx` 0..3，`n` ≤ 64，超出截断并返回 code=1） |
| `int appendPoint(int idx, float v)` | 追加一点（队列满丢最旧，保持 64）；返回追加后点数，<0 = 出错 |
| `Result clearSeries(int idx)` / `int pointCount(int idx) const` / `int seriesCount() const` | 数据查询与清空 |
| `Result setAxisRange(float min, float max, int ticks = 5)` | 值域 + 刻度段数（1..12，建议 5） |
| `Result setRingPercent(int ring, float p)` | 第 ring 环进度（0..1，自动夹取）。**该环若已设分段，分段优先**（进度弧不再画） |
| `Result setRingSegments(int ring, const Segment *segs, int n)` | **分段环**：第 ring 环切成 n 段（1..`MAX_SEGMENTS`=8）。`value` 是权重（按总和归一，3/1/1 ≡ 60/20/20）；`color=0` 用默认系列色；段间固定 2° 间隙，第 1 段从**正上方**起顺时针。**只在 `RING` 类型下生效**，其它类型返回 `-2` + 人话 msg；`n<=0` 等价清空；段数超上限截断（`code=1`）；全部段 `value<=0` 时按约定**不画段**（只留底轨，`code=1` 提醒） |
| `Result clearRingSegments(int ring)` | 清掉该环分段（回到 `setRingPercent` 的进度弧画法） |
| `bool hasRingSegments(int ring) const` | 该环当前是否分段（越界返回 false） |
| `struct Segment { float value; uint32_t color; }` | 分段环的一段（权重 + 颜色；编译期定长，**无动态分配**） |
| `Result setGaugeZones(const Zone *z, int n)` | 仪表分区（≤4 段，必须 v2>v1）；不设则用系列色均分 |
| `Result setGaugeValue(float v)` | 仪表指针值（自动夹到值域） |
| `Result attachLabels(ZKTextView **labels, int n)` | 刻度文字池（语义见 §4） |
| `Result setStyle(const Style &)` | 底色/网格/轴线/文字色/系列色/线宽/点半径/面积填充/竖网格/四边内边距/仪表起止角 |
| `Result refresh()` | **重绘**（painter 不自动重绘；改数据、改样式、切页回来都要调） |
| `static uint32_t mix(uint32_t fg, uint32_t bg, int percentFg)` | 混色（painter 无 alpha 时的半透明替代） |
| `enum { MAX_SERIES=4, MAX_POINTS=64, MAX_RINGS=3, MAX_ZONES=4, MAX_SEGMENTS=8 }` | 容量上限（编译期常量，**无动态分配**） |
| `struct Result { int code; std::string msg; bool ok(); }` | 统一结果类型（`components/README.md` 规范 2） |

## 4. 刻度文字池语义（painter 无文字 API 的必然结果）

| 类型 | `labels[k]` 的含义 | 位置由谁定 |
|---|---|---|
| `LINE` / `BAR` | `0..ticks` = Y 轴刻度（值从 **max 到 min**）；再往后的槽位 = X 轴分类文字（逐点一个，可省） | **组件**（`setText` + `setPosition`，已含 painter 偏移） |
| `RING` | `k` = 第 k 环的百分比文字：**进度环**= 该环进度；**分段环**= **最大那段**占全部的比例 | **json**（组件只写文字与颜色，不动位置 —— 环内文字位置主观，交给设计） |
| `GAUGE` | `0` = 下限、`1` = 上限、`2` = 当前值 | **组件**|

池子不够（`n` 太小）时组件**不报错、不越界**：少放几个文字，图形照画。

## 4.5 分段环怎么用（3 分钟）

```cpp
/* 一个环切成 3 段（值 = 权重，源数据要多少给多少，组件自己归一） */
zk::ui_v1::Chart::Segment segs[3];
segs[0].value = 42.f; segs[0].color = 0x2196F3;
segs[1].value = 28.f; segs[1].color = 0x4CAF50;
segs[2].value = 30.f; segs[2].color = 0;         /* 0 = 用默认系列色 */
s_ring.setType(zk::ui_v1::Chart::RING);           /* ★ 必须在 setRingSegments 之前 */
zk::ui_v1::Chart::Result r = s_ring.setRingSegments(1, segs, 3);   // 第 1 环（0 = 最内环）
if (!r.ok()) mTvLogPtr->setText(r.msg.c_str());   /* msg 是人话，可直接显示/打日志 */
s_ring.refresh();                                 /* ★ 改完必须重绘 */
```

语义与边界（写死，按这个用）：

| 项 | 口径 |
|---|---|
| `value` 含义 | **权重**不是百分比：组件按 `sum(value)` 归一，所以 `3/1/1` 与 `60/20/20` 画出来一样 |
| 全 0 / 全负 | **不画段**（只留底轨），返回 `code=1` + msg 说明（不静默失败） |
| 段间隙 | 固定 **2°**，从第 1 段到第 n 段依次排；占用角 = `360 - n*2°` |
| 起始方向 | 第 1 段从**正上方**开始，**顺时针**（与 `RING` 进度弧同口径） |
| 与进度共存 | 同一环上「分段优先」：设了分段就不画该环的进度弧；清掉分段即恢复 |
| 段数上限 | `MAX_SEGMENTS = 8`（编译期常量，超了截断 + `code=1` 提示） |
| 文字 | `labels[k]` = 该环**最大段**占比（`"52%"`），颜色 = 最大段的颜色 |
| 调用顺序 | `attach` → `setType(RING)` → `setRingSegments` → `refresh`；顺序错了返回 `-2` 并说清原因 |

## 5. 依赖与线程模型

- **依赖包（Z21/实测）**：`easyui`（`ZKPainter` / `ZKTextView`）+ 工程常规 `log / zkhardware / zknet / base-utility`。见 `Manifest.xml`。
- **线程模型**：**全部在 UI 线程**；无定时器、无锁、无阻塞。业务若在别的线程拿到数据，请自己投递到 UI 线程后再调
  `setSeries/refresh`（平台没有线程安全的控件写入口）。
- **性能**（Z21 实测）：单张图 `erase` + 最坏 12 柱 / 12 折点 / 3 环 / 20 刻度，四张图一起重绘肉眼无卡顿；
  `refresh()` 是同步绘制，别在 100ms 级定时器里无脑全刷四张（省 CPU：只在可见页刷，见 `logic-map.md`）。

## 6. 限制（写清楚）

1. **不自动重绘**：平台没有「invalidate 后由框架合成」这条路（LVGL 有），每次改数据都要 `refresh()`。
2. **点数上限 64/系列**：`MAX_POINTS` 是编译期常量（避免运行期分配）。要长波形请用平台的 `diagram` 控件，本组件不做。
3. **无文字测量**→ 折线/柱状**不画数值标签**（只在刻度槽位写轴值）；要数值标签请业务自己摆 `textview`。
4. **RING 不支持部分圆**（固定整圈底轨 + 进度弧/分段环都是整圈）；`GAUGE` 支持起止角与扇区，但不支持非线性刻度。
分段环**不做扇区外扩 / 圆环标签引出线**（那属于设计稿层面，用 json 里的 textview 自己摆）。
5. **半透明是混色近似**：叠在渐变/图片背景上时，混色结果会与源设计有偏差（painter 无 alpha，物理限制）。
6. **系列数 × 点数**：`setSeries` 只写不画；`refresh()` 才画。中途改 `setStyle` 也要 `refresh()` 才生效。

## 7. 验收记录（Z21 1024×600 真机，2026-09-16）

| 验收项 | 命令/判据 | 结论 | 证据 |
|---|---|---|---|
| 编译 | `fsc build` | ✅ 无警告无错误 | — |
| 五张图一次画全 + **Y 刻度值序**| 部署后抓屏 | ✅ 折线（带面积填充）/ 双系列柱 / 三同心环 / 仪表盘 / **分段环**都在；Y 轴刻度**自上而下 `100 80 60 40 20 0`**，与折线高度读数一致（**0.2.1 修**：修复前最上面那条线写 `0`、最下面写 `100`，图形对、字反） | `01_initial_four_charts.png`、**`08_yaxis_labels_fixed.png`（0.2.1 重抓首帧）**、**`08c_yaxis_before_after.png`（上=0.1.0 旧帧反序 / 下=0.2.1 修复后 对照）**、`08b_yaxis_labels_zoom.png`（1.5x 放大：折线+柱两条纵轴列） |
| **数据变化后重绘**| `touch tap 805 28`（换一批数据） | ✅ 状态行 `换一批 round=2 ring0=76% gauge=15`；**ui_diff：36 处差异 / 55,965 像素**（折线+柱+环+仪表+分段环五区全变） | `02_after_next_data.png`、`04_diff_initial_vs_next.png` |
| **增量数据重绘（只该变的变了）**| `touch tap 947 28`（追加一个点） | ✅ 日志行 `追加一个点：count=13 最后一个值=64`；**ui_diff：22 处差异 / 18,364 像素**；分区统计：**折线区 15,705 px、日志行 1,224 px，分组柱 / 同心环 / 仪表 / 分段环 / 顶栏状态行 全 0 px**| `03_after_append_point.png`、`05_diff_next_vs_append.png` |
| **分段环可见（0.2.0 新增）**| 部署后抓屏 | ✅ 内环 2 段 / 中环 3 段 / 外环 5 段都画出来了（段间 2° 缝可见）；三个环文字 `67% / 44% / 29%` = 各环**最大段**占比；无 `setRingSegments` 失败日志 | `06_ring_segments_initial.png`（与 `01` 同一帧：0.2.0 起首帧就含分段环，单列是为了这条验收有独立入口） |
| **分段环数据变化后重绘**| 与「换一批数据」同一次点击；把 `01`/`02` 的**分段环区**（屏幕 `640,400`–`1024,600`）裁出来再 diff | ✅ 环上的色块扇区跟着权重变（`内 2/5 中 5/4/2 外 6/2/7/3/4` → 环文字变 `52% / 40% / 31%`）；**分区 diff：5 处差异 / 4,469 像素**（只反映分段环那一块） | `07_diff_segments_changed.png` |

> **证据说明**：`01`~`07` 是 **0.2.1**（Y 刻度修复 + 分段环）在 Z21 1024×600 真机上**同一次会话**抓的
> （`01`/`06` 是同一帧：0.2.0 起首帧就带分段环）。
>
> **历史口径（0.2.1 修正说明）**：`01`~`05` 原为 **0.1.0**时期产物（布局为旧版 TvLog 大框、无分段环），
> 其中 **Y 刻度文字值序有误**——纵轴自上而下读成 `0,20,…,100`（图形本身是对的，只有字反）；旧帧留档见
> 开发工作区 `tmp_ui_v1/chart_a.png`。**0.2.1 修正后见 `08_yaxis_labels_fixed.png`（重抓首帧，纵轴自上而下
> `100,80,60,40,20,0`）与 `08c_yaxis_before_after.png`（上=旧反序 / 下=修复后，同一块折线图对照）**；
> 0.2.1 亦已把 `01`~`07` 用当前布局整组重抓（时间戳 2026-09-16 19:08）。
>
> 复现：按下面的命令整组跑一遍（抓完首帧/换一批/追加三帧，diff 由脚本离线算）。

复现命令（与上表逐条对应）：

```powershell
adb push tools\FlyThings_mcp_open\bin_tools\z21\touch /tmp/touch ; adb shell chmod 777 /tmp/touch

# ① 首帧            -> evidence/01（同时就是 06）
# ② 换一批数据       -> evidence/02，然后 04 = ui_diff(01, 02)
adb shell "/tmp/touch tap 805 28"
# ③ 追加一个点       -> evidence/03，然后 05 = ui_diff(02, 03)
adb shell "/tmp/touch tap 947 28"
# ④ 分段环分区 diff  -> evidence/07 = ui_diff(crop640,400,1024,600(01), crop640,400,1024,600(02))
python tools\ui_tools\ui_diff.py 01.png 02.png --out 04_diff_initial_vs_next.png
python tools\ui_tools\ui_diff.py 02.png 03.png --out 05_diff_next_vs_append.png
```

> 像素判据可复现：`python tools/ui_tools/ui_diff.py <改前.png> <改后.png> --out diff.png`（容差 ±2 + 抖动补偿）。
> 分区统计用同一张图裁区后在 PIL 里数 `|Δ|>2` 的像素（本组数据见上表，脚本口径一致）。

## 8. 排错

| 现象 | 原因 | 处置 |
|---|---|---|
| 画布全白/全黑，什么都没有 | 忘了 `refresh()`；或 `attach` 的不是 painter | 改完数据必须 `refresh()`；确认 caption 与 `mXXXPtr` 一致 |
| 刻度文字挤在容器左上角 | 文字与 painter **不同父**| 把刻度 `textview` 放到 painter 所在的同一个 `window` 里 |
| 折线/柱超出坐标轴 | 数据超出 `setAxisRange` 的值域 | 组件会夹到值域内（柱贴顶裁切），但别把轴设错 |
| 切页回来图没了 | painter 不自动重绘 | 在 `onUI_show()` 里 `refresh()` |
| 柱宽只有 2px | 点数太多 / 画布太窄 | 组件按 `(组宽-系列数)/系列数` 现算，最小 2px；减点数或加宽画布 |
| `setRingSegments` 返回 `-2`「仅 RING 类型生效」 | 调用顺序反了（先设分段后 `setType`），或该 Chart 实例是 LINE/BAR/GAUGE | 按 `attach → setType(RING) → setRingSegments → refresh` 的顺序调 |
| 分段环只看到底轨，没有色块 | 所有段 `value` 都 ≤0（返回 `code=1` 且 msg 已说明） | 传正权重；权重是**相对值**，不用自己算百分比 |
| 分段环色块之间没有缝 | 段数太多 / 环太细（`lw` 由半径自适应） | 2° 缝是固定值，环半径小时视觉上会被吞掉；把 canvas 放大或用 `Style::lineWidth` 调窄 |

## 9. 相关文件

- 目录规范（四件套）：`components/README.md`
- 映射口径：`ui_v1/control-map.md` §3.2、`ui_v1/gap-list.md` G-09/G-10/G-11、`ui_v1/platforms.md`（painter 平台事实）
- 提炼来源（只读，未改动）：`projects/translate/lvgl-widgets/z21/src/logic/mainLogic.cc`（PtLine/PtBar/PtArc/PtSess/PtGauge）、
  `projects/EasyDevice-Z21/src/logic/mainLogic.cc`（色标插值 / 坐标反算 / 密集点阵）
- 分段环的提炼来源：`projects/translate/lvgl-widgets/z21/src/logic/mainLogic.cc` 的 `PtSess`
  （Analytics 页三段饼环：`lv_scale` 360° + 3 个 `lv_arc` + 90ms 定时器驱动占比）
- 状态表：`ui_v1/components.md`
