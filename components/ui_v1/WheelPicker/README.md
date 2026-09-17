# components/ui_v1/WheelPicker —— 滚轮选择器 `zk::ui_v1::WheelPicker`

> **替代哪个源控件**：iOS WheelPicker ｜ Android `NumberPicker` ｜ 小程序 `picker-view`（多列联动 + 惯性吸附）
> **建立**：2026-09-16（钟工：「把这批控件走一遍，缺失的自己做一个，然后仔细验收：细节显示效果 + 实际性能」）
> **版本**：0.1.0 ｜ **状态**：Z21 真机跑通（视觉/性能验收数据见 §6）｜ **级别**：**L5 缺口补位（真缺）**

---

## 0. 先回答「为什么必须有这个包」（平台真缺的证据）

| 问 | 答（可核） |
|---|---|
| 映射表怎么说？ | `mcp_control_map.json`：小程序 `picker-view` → `wheelpicker`，**级别 L5**（明说平台无能力）；缺口清单 `ui_v1/gap-list.md` **G-23**「无滚轮选择器 WheelPicker（联动/惯性）」= **L5**，替代方案只有「步进按钮组 / 模态列表」 |
| 平台有什么？ | 列表类只有 `listview`（整行滚动、无「滚动中位置可读 + 吸附」），弹层只有 `window`；**没有任何"滚轮"形态的控件**；`painter` 只能画矩形/圆弧/线，**没有文字 API** |
| 结论 | 缺口成立：滚轮 = **自绘静态层 + 宿主 textview 池承载文字 + 惯性/吸附帧循环**。本包把这三件事收成一个类 |

---

## 1. 平台限制 → 实现形态（都是实测结论，别绕）

| 限制 | 实测表现 | 本包的处置 |
|---|---|---|
| `painter` 没有文字 API | 只能画矩形/弧/线 | 文字由**宿主传入的 `ZKTextView*` 池**承载（`attach(painter, rows, rowCount)`），包负责挪位置/换字/改色 |
| 没有 alpha / clip | 边缘淡出、行裁剪都没有原生支持 | ① 淡出 = **文字色向 `Style::bg` 插值**（伪 alpha，所以 `bg` 必须给真实底色）；② 行跑出盒子 = **隐藏该行**（`setVisible(false)`），否则文字会溢到轮子外面 |
| 设备端 `libeasyui.so` 比本机头文件**旧** | `ZKBase::invalidate(LayoutPosition*)` **未导出** → 用它 `dlopen` 报 undefined symbol → **整屏黑**（与 D20 `getAbsolutePosition()` 同族） | 只用设备端已验证的符号：`setPosition / setVisible / setInvalid / setText / setTextColor / setAlignment`（`/tmp/busybox strings /lib/libeasyui.so` 可复核） |
| 定时器不能由库自建 | 帧循环要落在 Activity 上 | 包只暴露 `bool tick()`，宿主在 `onUI_Timer` 里按 16ms 调；返回值 = 「还在动」（可据此省 CPU） |
| painter 不自动重绘 | 静态层要自己擦 | `erase + fillRect`（RadButton 同款路径），且**只在需要时重画**（静止时零开销） |

---

## 2. API（`include/zk/zk_wheelpicker.h` 是唯一对外面）

| 方法 | 说明 |
|---|---|
| `void attach(ZKPainter *painter, ZKTextView **rows, int rowCount)` | 绑定 painter 与文字池（`rowCount ≥ visibleRows`）；池里的 textview 由包接管位置/文字/颜色 |
| `void setStyle(const Style&)` | 外观与手感（见下表）；`Style::defaultStyle()` 给一套可用默认值 |
| `void setItems(const std::vector<std::string>&)` / `(const char* const*, int)` | 数据；item 变更会重排 |
| `void setIndex(int idx, bool animate=false)` | 选中项；`animate=true` 给一段滚动动画（内部限速 28 项/秒，避免"瞬移"） |
| `int getIndex()` / `const char* getItem(int)` / `int getItemCount()` | 读状态 |
| `void setListener(Listener*)` | `onWheelChanged(idx)`（滚动中，每 tick 可能回调）/ `onWheelSettled(idx)`（停下只回调一次） |
| `bool tick()` | 帧循环（宿主 16ms 调一次）；返回 `true` = 还在动 |
| `void refresh()` / `void stop()` | 整屏重画 / 立即吸附停止 |
| `bool onTouch(const MotionEvent&)` / `bool hitTest(x,y)` | 触摸转发；**命中才消费**（宿主 `return true` 吞掉即可） |
| `void setPerfHud(ZKTextView*)` / `void getPerf(frames, avgUs, maxUs)` | 性能自检（120 帧环形缓冲）；不接 HUD 则零开销 |
| `const char* debugDump()` | **布局自检**：`s=0.00 idx=0 pool=5 \| 0@90 1@130 2@170 3@1e9 -1@1e9`（滚动位置 + 每槽位 item@行框top；`-1`=空闲）。排查“布局对不对”一眼可判 |
| `void forceRepaint()` | **强制整块重绘**（painter + 全部行 `setInvalid(true)`）。换数据后包内已自动调；从隐藏页回来/发现旁列残影时宿主可手动调 |

### Style 字段

| 字段 | 默认 | 说明 |
|---|---|---|
| `bg` | `0xFFFFFF` | **必给真实底色**（伪 alpha 淡出按它插值） |
| `textColor` / `selTextColor` | `0x666666` / `0x0052D9` | 普通行 / 选中行文字色 |
| `bandColor` / `bandInset` / `bandRadius` | `0xF2F3FF` / `8` / `8` | 选中带（左右内缩 + 圆角） |
| `lineColor` / `showLines` | `0xE7E7E7` / `true` | 选中带上下分隔线 |
| `rowHeight` / `visibleRows` | `40` / `5` | 行高 / 可见行数（自动取奇数，保证有正中行） |
| `fadeEdges` / `fadeMax` | `true` / `0.55` | 边缘伪淡出；`fadeMax` = 最远行向底色混的上限（**1.0 会让远端行整行看不见**，实测踩过） |

---

## 3. 最小用法（宿主 4 步；完整可跑见 `example/`）

```cpp
#include "zk/zk_wheelpicker.h"

static zk::ui_v1::WheelPicker s_wheel;
static ZKTextView *s_rows[5] = {mRow0Ptr, mRow1Ptr, mRow2Ptr, mRow3Ptr, mRow4Ptr};

static void onUI_init() {
    INIT_UI_TIMERS                                     // 必须
    zk::ui_v1::WheelPicker::Style st = zk::ui_v1::WheelPicker::Style::defaultStyle();
    st.bg = 0xFFFFFF; st.rowHeight = 40; st.visibleRows = 5; st.bandInset = 10;
    s_wheel.attach(mPtWheelPtr, s_rows, 5);            // painter + 文字池
    s_wheel.setStyle(st);
    s_wheel.setItems(items);                           // 你的数据
    s_wheel.setIndex(0);
    s_wheel.refresh();                                 // ★ 不调不显示
}

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {{0, 16}};   // 帧循环

static bool onUI_Timer(int id) { if (id == 0) s_wheel.tick(); return true; }

static bool onmainActivityTouchEvent(const MotionEvent &ev) {
    return s_wheel.onTouch(ev);                        // 命中才消费
}
```

**多列联动**：包只做单列；联动在宿主侧接线（`onWheelSettled(idx)` 里按左列的值重建右列 `setItems` + `setIndex(0)`），example 里有现成写法。

---

## 4. 依赖

- 只依赖 easyui 自带控件（`painter` / `textview`）+ `log`；见 `Manifest.xml`
- 工程侧接入：把 `include/zk/` 拷进工程 `src/zk/`（或整包拷 `src/` 下），`fun build` 自动收 `src/**/*.cpp`

---

## 5. 排错表

| 症状 | 原因 | 处置 |
|---|---|---|
| 整屏黑 + `1.initLib error: undefined symbol: _ZN6ZKBase10invalidateEPK14LayoutPosition` | 用了设备端没导出的 `invalidate(LayoutPosition*)` | 改用 `setInvalid(bool)`；设备端符号表可用 `/tmp/busybox strings /lib/libeasyui.so` 核 |
| 一行文字都不出来 | 没 `attach` / 没 `setItems` / 没 `refresh()`，或 painter 尺寸为 0 | 按 §3 四步检查；`fun build` 后看 json 里 painter 的 `position` |
| 远端行整行"消失" | `fadeMax` 给到 1.0（远端完全混成底色） | `fadeMax ≤ 0.7` |
| 文字溢到轮子盒子外面 | 平台没有 clip | 包内已按「行中心是否在盒内」隐藏；若自绘了外框，把 `rowHeight/visibleRows` 对齐盒子高度 |
| 甩动后出现**叠字/错位** | 行池**换绑 item 时清了 `poolY` 缓存**（本包 0.1.0 已修） | 若二次开发改了池逻辑，务必在换绑时重置位置/颜色缓存 |
| 滑动时文字有旧像素残留 | 平台重绘以控件为单位，移动 textview 不会自动清旧位置 | 本包在文字层变动时**重画静态层**（`dirtyStatic`）；必要时对 painter `setInvalid(true)` |
| 卡顿 / CPU 高 | 定时器帧率过高或 `tick` 里做了重活 | 16ms 足够；静止时 `tick()` 走快路径（实测可忽略） |

---

## 6. 验收记录（Z21 1024×600，2026-09-16）

**功能**（`example/evidence/*.png`）：拖动滚轮 → 松手惯性 → 吸附对齐；直接点某行可选中；`onWheelSettled` 触发联动重建右列；按钮「下一项/上一项/快速滚/立即停」全部生效。

**细节**：
- 选中带（圆角浅蓝）+ 上下分隔线 + 边缘行渐进淡出（0.55 上限）—— 8× 放大可核；
- 行高 40 / 可见 5 行 / 选中行严格居中（吸附后 `scroll` 为整数）；
- 行跑出滚轮盒自动隐藏，不外溢。

**性能（同一帧循环里实测，HUD 直接显示在屏幕上）**：

| 指标 | 实测 | 口径 |
|---|---|---|
| 两轮合计 `tick()` | **avg 8~10 µs / max 12~19 µs**（60 帧环形缓冲） | 一帧里两列滚轮的"活"；16ms 帧预算里占 **0.05~0.12%** |
| 单轮（左列，包内 120 帧缓冲） | **avg 1~2 µs / max 4~6 µs** | 静止/微动时几乎为 0（静态层不重画） |
| 进程 CPU（`busybox top` 增量） | **0.4%** | 甩动后静止状态；无"定时器空转吃 CPU" |
| 内存 | **VmRSS 5824 kB**；设备 `MemAvailable 16836 kB / 36024 kB` | 26 个控件（2 painter + 10 textview + 4 button + 其余 text） |

**已修的重绘/残影问题（2026-09-16 23:0x，钟工指出 A05-1 与 A05-4 重叠）**：
- **根因（实测定位，不是布局算错）**：包内布局是精确的（`debugDump` 可证：`0@90 1@130 2@170 3@1e9 -1@1e9`），问题出在**写入顺序**——
  原先在“分配 item”阶段就 `setText()`，此时控件还在**json 初始位置**，框架会先在那画一次；接着因该行在滚轮盒外被 `setVisible(false)`，
  而隐藏**不会清掉已画的像素** → 旧位置永久残留一行（实测残影停在 y≈202，正是某个 Row 的 json 初始位置）。
- **修法**：**先定可见性 + 位置，再写文字**；隐藏/移出时把“已写入文字”标记置位，回到可见区重写；
  并且**行集合变化（换绑/隐藏）那一帧强制整块重绘**（`forceRepaint()`，因为设备端没有区域标脏 API）。
- **验收（像素级行位）**：修后两轮文字行精确落在 **174 / 214 / 254**（40px 等距，item3 起按规则隐藏），
  静态与“联动重建右轮 + 甩动”后都无重叠/无残影（`evidence/15_*`、`evidence/16_*`）。

**已知未做**：F133 / T113 / Z20 / V85X **未上机**（仅编译）；多列**同帧同步**滚动未做（联动目前是「停下后重建」）；惯性参数（衰减/阈值）暂不可配。

---

## 6.1 验收中发现并修掉的 5 个真 bug（都写进排错表 / 注释）

| # | 现象 | 根因 | 修法 |
|---|---|---|---|
| 1 | 远端行**整行消失** | 伪 alpha 淡出曲线过猛（dist≥2 直接 100% 混底色） | 新增 `Style::fadeMax`（默认 0.55）+ 按可见行数归一曲线 |
| 2 | 文字**滥到轮子盒外**（平台无 clip） | 只按「行完全出盒」隐藏，部分出盒的行中心仍在画 | 改判据：**行中心出盒即隐藏** |
| 3 | **整屏黑** + `undefined symbol: _ZN6ZKBase10invalidateEPK14LayoutPosition` | 用了设备端 libeasyui 未导出的符号（本机头文件有） | 改用设备端有的 `setInvalid(bool)`；同类坑与 D20 `getAbsolutePosition()` 同源 |
| 4 | 甩动后**叠字/错位** | 行池**换绑 item 时没清 `poolY` 缓存** → 新 item 的 y 恰好等于旧值时跳过 `setPosition` | 换绑时重置 `poolY=1e9` / `poolFade=-1` |
| 5 | `setItems()` 后**文字不刷新** | 池按 item 下标判「已有宿主」，下标未变就跳过 `setText` | 新增 `relayoutAll`：数据一换，池全部重绑（重 `setText` + 重摆位） |
| 6 | 甩动/联动后**多出一行错位文字**（钟工从截图看出 A05-1 与 A05-4 重叠） | 在“分配 item”阶段就 `setText()` → 控件还在 json 初始位置就被画了一次，随后被隐藏又不清像素 | **先定可见性/位置、再写文字**；行集合变化那一帧强制整块重绘（`forceRepaint()`）；新增 `debugDump()` 供以后一眼判布局 |
