# components/ui_v1/WheelPicker —— 滚轮选择器 `zk::ui_v1::WheelPicker`

> **替代哪个源控件**：iOS WheelPicker ｜ Android `NumberPicker` ｜ 小程序 `picker-view`（多列联动 + 惯性吸附）
> **建立**：2026-09-16（钟工：「把这批控件走一遍，缺失的自己做一个，然后仔细验收：细节显示效果 + 实际性能」）
> **版本**：**0.2.0**（2026-09-18）｜ **状态**：Z21 真机跑通 + **tdesign 阶段 4 真机验收通过**（三页：tabs/picker/date-time-picker）｜ **级别**：**L5 缺口补位（真缺）**

### 0.2.0 变更（2026-09-18，均经真机复现 + 修复 + 复验）

| # | 问题（真机反馈） | 根因 | 修复 | 复验 |
|---|---|---|---|---|
| 1 | 滚轮「某行整行空白（如 7月不见）」 | 候选窗口 `2*half+3`（visibleRows=5 → **7 个 item**）而文字池只有 **5 槽**；原按 item **升序先到先得**分配 → 窗口内 item 抢不到槽 | **按「离选中行距离」由近到远分配池位**；不在集合里的槽释放 | 该行 0 → 1497 像素 |
| 2 | 松手弹回、**没有惯性** | `vel = -dScroll/0.016` **符号与拖动方向反**；假设 MOVE 恒 16ms；松手 `\|vel\|<2.0` 就清零；吸附取 `floor(scroll+0.5)`（不足半行回原位）；衰减 `pow(0.055,dt)` 每秒 94.5% | 真实 dt 估速（EMA）→ 方向取**拖动方向**；**慢拖（≥1/3 行）= 精准一档**（基准 = DOWN 行号）；**微拖回原行**；**真甩动（`FLING_MIN=8.0` 行/秒）= 惯性滑行**（`vel *= 0.05^dt`） | 快甩 150px **+3 格**；微拖 8px **0 格** |
| 3 | 滑动 **CPU 偏高**（曾试「文字布局层帧率上限 ~36fps」→ 26.2%→18.4%，但**真机出现文字重影**：跳过布局帧时该隐藏/该移动的行没被处理）| — | **已撤回**（正确性优先）：帧率上限移除，CPU 优化改用不牺牲正确性的路子（只重绘被触摸那一列 / 仅行内容真变时标脏）| 撤回后真机复验：5 列 × 各行文字清晰、无残字/无叠字；CPU 回到 ~26% |
| 4 | `setTouchOrigin(x,y)`（沿用 0.1.0 阶段 4 补） | `painter` 位置是**父相对**坐标，而事件是**屏幕绝对**坐标 → 容器有偏移时「看得见、拖不动」 | 新增 `setTouchOrigin(容器 left/top)`（默认 `(0,0)` 向后兼容） | 修前拖动整帧无变化 → 修后滚动成立 |

> 可调旋钮：`FLING_MIN`（默认 8.0 行/秒，甩动阈值）与惯性衰减 `0.05^dt`（默认每秒剩 5%）。

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
| `void setTouchOrigin(int originX, int originY)` | **触摸坐标原点补偿**（0.1.0 阶段 4 补）。`painter->getPosition()` 给的是**父相对坐标**，触摸事件是**屏幕绝对坐标**；滚轮直接挂根节点时两者相等，但放进带偏移的容器（如页面 `window` y=56）后必须把容器偏移告诉包，否则命中判定/「点某行选中」会错位。用法：`w.setTouchOrigin(winPos.mLeft, winPos.mTop);`（设备端 `getAbsolutePosition()` 未导出，不能靠它补救） |
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

**宿主接线三条硬要求**（阶段 4 真机实证，少一条就会「看着对、拖不动/联动不跟」）：

1. `onUI_init` 里 `attach → setStyle → setItems → setIndex → refresh`（不调 `refresh()` 不显示）；
2. **放进带偏移的容器里必须 `setTouchOrigin(容器left, 容器top)`**（本例：页面 window 在 y=56，
   不调就会「滚轮在屏幕上画得对、但手指拖不动」——`hitTest` 拿父相对坐标比绝对触摸点，
   竖向整体偏 56px，下半截永远命中不到）；
3. 宿主在 `onUI_Timer` 里按 16ms 调 `tick()`；多列就每列一个实例、逐个 `tick()`。
   **联动别只依赖 `setIndex(idx, animate=true)`**：那个 `animate` 是「甩一下」语义（给初速度，
   不跟踪目标），会滑过好几项；要「精确 +1」请 `setIndex(i, false)` 并在宿主侧显式走联动。
   另外 `setItems()` 内部会跑一次 tick，**可能立刻回调 `onWheelSettled(idx=0)`** ——
   初始化时如果用 `s_year`（宿主状态变量）去算初始下标，就会先被这个回调盖成 0
   （真机现象：结果行 2024-02-29、选中行 2020-01-01）。初值要在 `setItems` 之后再赋值。

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

**已知未做**：F133 / T113 / Z20 / V85X **未上机**（仅编译）；惯性参数（衰减/阈值）暂不可配。

## 6.2 阶段 4 二次验收（TDesign 迁移案例，Z21 真机，2026-09-18）

| 项 | 结果 |
|---|---|
| 场景 | **5 列**滚轮（年/月/日/时/分）装在**页面 window 内**（y=56 偏移），同一帧循环里 5 个 `tick()` |
| 初始渲染 | 5 列各自画出选中带（`#F2F3FF`，每列 ~1240 个带色像素）+ 正中行有文字，与 JSON 行位一致 |
| 联动 | 年/月停下 -> 日列按当月天数重建：2024-02-29 -> 年+1 -> **2025-02-28**（19 项夹到 28）；再月+1 -> 3 月 31 天（正中行下一行出现「30日」，实测非白像素 0 -> 225） |
| 触摸 | 修 `setTouchOrigin` 前后对比：修前「拖动月列」整帧无变化（命中不到）；修后月列滚动成立、状态行同步 |
| 残留像素 | 本轮**未复现**「未被触摸的那一列 setItems 后残留一行旧像素」（`forceRepaint` 生效）；
证据：`projects/translate/tdesign-miniprogram/z21/evidence/s4_dt_*.png` |
| 已知未做（本轮新增） | `setIndex(idx, animate=true)` 不跟踪目标 -> 只适合“甩动”，精确步进用 `setIndex(i,false)`（宿主侧接线已按此写） |

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
