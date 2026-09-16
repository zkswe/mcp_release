# components/ui_v1/RadButton —— 带倒角按钮 `zk::ui_v1::RadButton`

> **替代哪个源控件**：LVGL `lv_button`（主题倒角 `lv_style_set_radius`）｜ CSS `button { border-radius }` ｜
> Android `shape=rounded` / `MaterialButton` ｜ 小程序 `button` + `border-radius`
> **建立**：2026-09-16（钟工口径：一个源控件一个目录，只做「平台没有的能力」）
> **版本**：0.1.1 ｜ **状态**：已实现（含 Z21 真机证据 + 像素数字）｜ **级别**：**L3（必须自绘）**
> **0.1.1（2026-09-16 晚）**：修「药丸圆钮外围露出方角」—— 钮从「铺底盒 + 圆角矩形」改成**图层叠加**
> （逐像素 `mix(mix(track, Style::bg, 1-P), knob, K)`，`P=0` 的像素不画 → 方角被药丸轮廓裁掉）。
> 真机数字：理想轮廓外的纯药丸色像素 **6/个钮 → 0**（`z21/evidence/zzc_*`、STATUS §12）。
> **本包对外证据**：`example/evidence/13–19`（8× 左右对照 / 严格口径 diff / 上机前本地渲染桩）+ `FIX_metric.log`、`FIX_local_check.log`；
> 修前帧与 `zzc_*` 全量 20 张在案例工程 `projects/translate/lvgl-widgets-uiv1/z21/evidence/`。
---

## 0. 先回答「为什么必须有这个包」（平台真缺的证据）

| 问 | 答（可核） |
|---|---|
| FlyThings 有按钮吗？ | 有，`button__N` / `ZKButton`。机读映射：`mcp_control_map.json` → `lvgl.lv_btn → target=button`（L1）；`qml.Button`、`miniprogram.button` 同样指过去 |
| 那缺什么？ | **倒角（圆角）与边框没有任何平台能力**。`button__N` 的 json 里没有 radius 字段（`mcp_control_map.json` 的 button/button_pic 两个模板只有 `position / colorTab / bgColorTab / picTab / fontSize / alignment / text / touchable`），`ZKButton` 也没有任何半径 setter；唯一途径是 `picTab` 挂**切图** |
| 切图不够吗？ | 不够。切图 = 半径/尺寸/状态色**全部写死在资产里**：<br>· 每个半径一份资产（实测：r=14 的资产拿去当 r=13 用，边缘误差从 10.0 跳到 **59.1/255**，见 §3）；<br>· 每个状态色一份资产（四态 × N 个按钮 = 4N 张）；<br>· 运行时改尺寸/换主题色 = 重新出图重新发版 |
| 有没有别的控件能顶？ | `ZKCircleBar`（单环、按进度裁图）、`ZKPainter`（有 `fillRect(l,t,w,h,radius)`，**但没有 alpha、也没有「任意半径的平滑边」保证**，见 §3 实测）→ 只有 painter 能当底座 |
| 结论 | 缺口成立（`gap-list.md` G-07 从 L4「只做圆角切图」升级为 **L3 自绘**：`RadButton` = **一个 painter + 一份代码**，尺寸/半径/四态/边框全在运行时给） |

> 与 `ui_v1/_mapping/TabView` 的区别：TabView 有平台对应控件（`pagewindow`）→ 它是**映射参考**；
> 本包没有对应能力（`button__N` 之外没有「圆角按钮」这个控件）→ 它是**自定义控件包**（与 `Chart`/`Calendar` 同类）。

---

## 1. 我们怎么做（一个 painter 画完）

```
json:  painter__N (控件盒 = 按钮盒)          ← 只有这一个控件
代码:  RadButton::attach(painter) → setStyle/setRadius/setColors → refresh()
```

绘制分三层（都在 painter 自己的局部坐标，`getPosition()` 只用来读宽高）：

| 层 | 画法 | 为什么 |
|---|---|---|
| ⓪ 底 | 整个控件盒先铺 `Style::bg`（1 次 `fillRect`） | ① painter 的 `erase()` 在设备上留下的是**不透明黑**（实测：跳过的圆角外像素就是 4 个黑方块）；② 铺实后圆角外的像素与 AA 混色基准同色，边缘无色差 |
| ① 直边 | 中竖带 + 左右横带（3 次 `fillRect`，轴对齐、精确） | 直边与像素网格对齐，**根本不需要抗锯齿** |
| ② 圆角 | 4 个 r×r 角方块**逐像素**算覆盖率 → 与 `bg` 混出中间色 → 按行合并同色像素成 span 再画 | 只有弧带上的像素需要 AA（r=14 → 约 21 个像素/角）；合并后一次绘制约几十次 `fillRect`，肉眼无卡顿 |
| ③ 边框 | 直边 4 条整块画；圆角处按「外覆盖 − 内覆盖」的环带覆盖率混色 | 边框同样是弧线，硬画照样有台阶 |
| ④ **内嵌图形**（药丸的圆钮） | **图层叠加**：逐像素 `base = mix(track, bg, P)` → `final = mix(knob, base, K)`；`P == 0` 的像素**一个都不画** | ⓪ 的铺底盒只对「形状自己」成立。内嵌图形若也铺一个 `dia×dia` 盒，盒子外角会落到药丸端头半圆之外 → 卡片底上露方角（0.1.0 的真实 bug）。`P` = 药丸覆盖率、`K` = 圆钮覆盖率，见 §1.1 |

覆盖率口径：像素 `[x,x+1)×[y,y+1)` 与圆的交面积（每轴 8 等分超采样 = 64 级 → 65 档中间色），
与 `tools/ui_tools/gen_res.py::rounded_rect_ss` 是**同一套口径**，区别只是它在 PC 上出图，本包在设备上实时算。

### 1.1 图层叠加：为什么内嵌图形不能自己铺盒（0.1.1 的修复）

平台 painter **没有 alpha、也没有 clip/mask**，所以「把圆钮盖到药丸上」只能自己算：

```
P = 该像素的药丸覆盖率（图层叠加里用 rrectCoverage，x∈药丸盒、r = h/2）
K = 该像素的圆钮覆盖率（同一个函数，x∈钮盒、r = dia/2）
base  = mix(track, Style::bg, P)    // 药丸与卡片混出来的「那一层」——即 ⓪+①+② 已经画在那里的颜色
final = mix(knob , base, K)         // 钮的 AA 混色基准是 base，**不是** track
只画 P > 0 的像素（P == 0 = 药丸外 → 一个像素都不碰，保留卡片底色）
```

三处细节（都是踩过的）：

- **混色基准逐像素变**：钮边缘半透明像素的底下是「药丸+卡片」的混合色，拿纯 `track` 去混会在端头露一圈深边。
- **`P == 0` 必须不画**：这就是「方角」的根治。药丸端头是半径 `h/2` 的半圆，钮盒（边长 `dia` 的正方盒）
  的**外上/外下角**到端头圆心的距离 = `√2/2 × dia ≈ 0.707·dia`；`dia = h - 2·padding`，所以只要
  `padding < 0.293·h`，钮盒角就一定在药丸轮廓外（56×28 药丸 + `padding=3` 时超出 ~0.9px）。
- **性能不退化**：只有钮那一块（`dia²` ≈ 484 像素）逐像素，且先用圆角矩形 SDF 把「整像素全内/全外」
  的像素挡掉（判据：像素中心到轮廓距离 ≥ √2/2），只有边缘 1px 带才跑 8×8 超采样。

---

## 2. 怎么用（12 行可跑）

```cpp
#include "zk/zk_radbutton.h"

static zk::ui_v1::RadButton s_ok;

static void onUI_init() {
    zk::ui_v1::RadButton::Style st = zk::ui_v1::RadButton::defaultStyle();
    st.radius = 12;
    st.bg     = 0xF5F7FA;                 // ★ 按钮背后的真实底色（AA 混色基准）
    st.normal = 0x2196F3;
    s_ok.setStyle(st);
    s_ok.attach(mPtOkPtr);                // json 里的 painter__N
    s_ok.setState(zk::ui_v1::RadButton::NORMAL);
    s_ok.refresh();                       // ★ 不调什么都不显示
}

/* 按下反馈（触摸由业务负责 —— 本包不接管触摸，两种写法都行） */
static bool onmainActivityTouchEvent(const MotionEvent &ev) {
    if (ev.mActionStatus == MotionEvent::E_ACTION_DOWN) { s_ok.press(true);  s_ok.refresh(); }
    else if (ev.mActionStatus == MotionEvent::E_ACTION_UP) { s_ok.press(false); s_ok.refresh(); }
    return false;
}
/* 或者干脆用平台按钮当热区（本包示例就是这么做的，见 example/）
   static bool onButtonClick_BtnOk(ZKButton *p) { ...; return false; } */
```

**必调项**（少一条就出问题，排错表 §8 有症状对照）：

1. `attach(painter)` —— 且 json 里那个 `painter__N` 的 `position.width/height` 必须 > 0；
2. `Style::bg` **必须** = 按钮所在位置的真实底色（画在卡片上用卡片色、画在图上就只能近似）；
3. 任何改动（半径/色/状态/切页回来）后 `refresh()` —— painter 不自动重绘。

---

## 3. 抗锯齿实测：数字 + A/B/C 三路线对照（本包最有价值的部分）

**测法**（`example/aa_ideal.py`，0 token、纯像素、可复现）：把控件盒与半径还原成几何，
对每个像素做 **16×16 超采样**求「理想覆盖率」，理想色 = `mix(fill, bg, 覆盖率)`，
再拿 Z21 真机截图的**实际像素**减理想色；只统计 **AA 带**（0.02 < 覆盖率 < 0.98）的像素。

| 路线 | 画法 | AA 带像素 | 平均误差 | p95 | 最大 | 误差 >30 占比 |
|---|---|---|---|---|---|---|
| **A 平台原生** `fillRect(l,t,w,h,radius)` r=4 | HARD | 7 | 10.0 | 12 | 12 | 0% |
| **A 平台原生** r=8 | HARD | 11 | **19.6** | **34** | **34** | **36%** |
| **A 平台原生** r=14 | HARD | 21 | 8.2 | 13 | 14 | 0% |
| **B 本包 AA**（默认）r=4 | `MODE_AA` | 7 | **1.4** | 2 | 2 | 0% |
| **B 本包 AA** r=8 | `MODE_AA` | 11 | **1.8** | 3 | 3 | 0% |
| **B 本包 AA** r=14 | `MODE_AA` | 21 | **2.0** | 5 | 5 | 0% |
| **C 切图** `.9.png`（资产本身，4× SS + LANCZOS） | `gen_res.rounded_rect_ss` | 21 | 10.6 | 18 | 22 | 0% |
| **C 切图** 设备上经 `button__N` 渲染（同资产拉伸 200×56 → 300×56） | `picTab` | 21 | 10.0 | 17 | 21 | 0% |

读出来的三件事：

1. **平台原生 `fillRect(radius)` 是抗锯齿的，但很粗**：r=14 看着还行（8.2），**r=8 明显不行**（19.6 平均、
   36% 的弧带像素误差 >30/255 —— 也就是肉眼能看出「阶梯」）。原因是它的覆盖率量化档太少 + 偏差方向一致
   （实测像素恒比理想**更浅**，如 `#98CCF7` vs 理想 `#75BDF6`）→ 就是「发虚的一圈台阶」。
2. **本包 AA 基本贴着理想**：平均 1.4~2.0、最大 5/255（**比平台原生好 4~10 倍**）。因为它是
   「几何覆盖率 + 与已知底色混色」，不是估的、也不是重采样出来的。
3. **切图路线（C）质量够用**（10.0，与资产本身 10.6 一致 → **9-patch 拉伸不额外损失**），
   代价是**半径/尺寸/状态色全部烧进资产**：同一张 r=14 资产当 r=13 用时误差立刻跳到 **59.1**（74% 的像素 >30）。
   → 结论：**能预知尺寸/半径的静态美术件，切图仍是最省事的选择；要「运行时任意尺寸 + 任意半径 + 四态 + 无资产」，
   只有本包这条路**（这也是本包存在的理由，不是「切图不行」）。

**中间档数量**（另一种口径，供对比）：r=14 角上 ——
HARD：中间档像素 23 个 / 14 档色 / 占边界像素 34.8%；
AA：中间档像素 23 个 / 12 档色 / 占边界像素 26.1%。
（档数相当，差别在**准不准**，所以判据用「误差」而不是「档数」。）

证据图（`example/evidence/`）：
`06_zoom8x_r14_hard_vs_aa.png`、`07_zoom8x_r8_hard_vs_aa.png`（8× **LANCZOS** 放大，NEAREST 必然看着有台阶）、
`08_zoom8x_three_routes.png`（三条路线同屏对照）。

---

## 4. API

| 成员 | 说明 |
|---|---|
| `Result attach(ZKPainter *painter)` | 绑画布（`onUI_init` 里调）；空指针 / 尺寸 0 → 非 0 + 人话 `msg` |
| `void detach()` | 解绑（`onUI_quit`）；同时把状态复位到 NORMAL |
| `bool isAttached() const` | 是否已绑 |
| `Result setStyle(const Style &)` | 一次给全（半径/四态色/边框/底色/画法/采样数）；非法值返回非 0 且**不生效** |
| `const Style &style() const` / `static Style defaultStyle()` | 读样式 / 默认样式（白底无关，见下表） |
| `Result setRadius(int r)` | 圆角半径；`<=0` → 自动 = `min(w,h)/3`（药丸）；超 `min(w,h)/2` 自动夹取 |
| `Result setColors(normal, pressed, selected, disabled, border = 0)` | 一次改四态色（`border` 省略 = 保留原边框色） |
| `Result setMode(Mode)` | `MODE_AA`（默认）/ `MODE_HARD`（平台原生硬边，对照/兜底用） |
| `Result setState(State)` | `NORMAL/PRESSED/SELECTED/DISABLED`；**幂等**（同状态重复调返回 code=0，不重绘不报错） |
| `State state() const` / `const char *stateName() const` / `uint32_t currentColor() const` | 读状态 / 状态名（打日志用）/ 当前填充色 |
| `Result press(bool down)` | 按下/抬起。`down=true` 记住「按下前状态」→ PRESSED；`false` 回落。**幂等**：重复 `press(true)` 不覆盖基准；`press(false)` 未按下时是 no-op |
| `Result setSelected(bool on)` | = `setState(SELECTED/NORMAL)`，幂等 |
| `bool isSelected() const` | |
| `Result refresh()` | **重绘**（改半径/色/状态/切页回来都要调） |
| `Result erase()` | 擦掉控件盒（业务想在按钮上叠自绘内容时用） |
| `int width() / height() / radiusPx() const` / `static int autoRadius(int w,int h)` | 当前几何（来自 `getPosition()`）/ 自动半径口径 |
| `static uint32_t mix(uint32_t fg, uint32_t bg, int percentFg)` | 混色（painter 无 alpha 时半透明的替代） |
| `static Result drawRoundedRect(painter, l, t, w, h, radius, fill, border, borderWidth, bg, mode = MODE_AA, aaSamples = 8)` | **核心可独立用的静态画法**：任意 painter 上画一个 AA 圆角矩形（含边框）。RadButton 内部就是调它 |
| `struct Result { int code; std::string msg; bool ok(); }` | 统一结果类型（`components/README.md` 规范 2）：`0` = OK、`<0` = 出错且**什么都没改** |

`Style` 字段与默认值：

| 字段 | 默认 | 说明 |
|---|---|---|
| `radius` | `12` | `<=0` → 自动药丸 `min(w,h)/3` |
| `normal / pressed / selected / disabled` | `0x2196F3 / 0x1976D2 / 0x0D47A1 / 0xBDBDBD` | 四态填充色（每态一份，无需资产） |
| `border` / `borderWidth` | `0` / `1` | 边框色 `0` = 不画；`DISABLED` 态**自动不画边框** |
| `bg` | `0xFFFFFF` | ★ AA 混色基准 = 按钮背后的真实底色 |
| `mode` | `MODE_AA` | 圆角画法 |
| `aaSamples` | `8` | 每轴超采样数（2..16），8 = 65 档覆盖率 |

---

## 5. 依赖与线程模型

- **依赖包（Z21/实测）**：只有 `easyui`（`ZKPainter`）+ 工程常规 `log / zkhardware / zknet / base-utility`。见 `Manifest.xml`。
  用到的 painter API 共 7 个：`setSourceColor / setLineWidth / fillRect / drawRect / fillArc / erase / getPosition`。
- **线程模型**：**全部在 UI 线程**；无定时器、无锁、无阻塞、**无动态分配**（全部编译期定长）。
- **性能（Z21 实测）**：一次 `refresh()` = `erase` + 3 次整块 `fillRect` + 4 个角方块的逐像素 span（r=14 时约 50~80 次
  `fillRect`）。同屏 10 个按钮（含最大 240×64）整屏重绘肉眼无卡顿；**别**把它放进 100ms 级定时器里无脑全刷。
- **触摸**：**本包不接管触摸**（照 TabView/Calendar 口径）。命中判定与「按下态」由业务负责：
  要么在 `onmainActivityTouchEvent` 里调 `press(true/false)`，要么用平台 `button__N` 当热区盖在上面
  （示例走的就是后者，业务侧 0 行手写命中；`example/` 里还有一条 `ITouchListener` 的写法）。

## 6. 限制（写清楚，别让人猜）

1. **AA 只对「纯色底」精确**：混色基准是 `Style::bg` 这一个颜色。按钮压在图片/渐变上时，
   边缘中间色会与真实背景有偏差（painter 无 alpha，物理限制）。要压在图上就：
   该按钮用 `MODE_HARD`，或把 `bg` 设成该位置的主色（视觉上最接近）。
2. **`refresh()` 必须显式调**：平台没有「invalidate 后由框架合成」（LVGL 有），painter 不自动重绘。
3. **不做圆角以外的形状**：不做胶囊内的斜切、不做渐变填充、不做阴影（阴影见 `gap-list.md` G-06）。
4. **不做内边距/图标/文字排布**：本包只画底；文字用 json 里的 `textview` 摆在 painter 上（同父容器），
   图标用另一个 `imageanim`/`button` 叠。**别把控件盒做太小**——圆角半径挤到 `min(w,h)/2` 时形状会变椭圆。
5. **`MODE_HARD` 是「平台原生」，不是「平滑」**：它等价于 `fillRect(radius)` + `drawRect(radius)`，
   边缘质量见 §3（r=8 时会看到台阶），保留它只是为了对照与兜底。
6. **`aaSamples` 调大更准但更慢**：16 已是收益拐点（覆盖率档数 256），不建议超过。
7. **边框宽 > 半径时只能画到半径宽**（自动夹取，`bw <= r`）。

## 7. 真机验收记录（Z21 1024×600，2026-09-16）

> ⚠️ **21:2x 更正**：本节证据**有效**（早前误判为「别人的画面」已撤回；见
> `example/evidence/EVIDENCE_STATUS.md`）。真实情况是**本 example 当时把 Z21 从案例下顶掉了**，
> 导致另一个任务的截图全成了本页画面 —— 根因是设备排队，不是证据造假。
> 唯一保留的提示：`platforms.md` §1.1 的数字在「§7.1 重测」前，按本轮实测值引用。

| 验收项 | 命令/判据 | 结论 | 证据 |
|---|---|---|---|
| 编译 | `fun build -p Z21` | ✅ 无警告无错误（`src/zk/*.cpp` 被 `fun build` 自动收编，**无需改构建**） | — |
| 静态全检 | `python tools/ui_tools/check_all.py <example>` | ✅ 全部 PASS | — |
| 首帧：三档半径 + 上下对照 | reboot → 部署一次 → 抓图 | ✅ HARD r=4/8/14 与 AA r=4/8/14 同尺寸同色上下两排；③ 四态四个盒子；④ 探针（圆环/圆角描边）；⑤ `.9.png` 拉伸按钮 | `evidence/01_initial_full.png` |
| **圆角边缘不是阶梯（数字）** | `python example/aa_ideal.py …`（16×16 理想覆盖率） | ✅ AA：**平均 2.0 / p95 5 / 最大 5**（r=14）；HARD：平均 8.2 / 最大 14；**r=8 时 HARD 平均 19.6 / 最大 34 / 36% 超 30** → AA 更平滑一个量级 | `evidence/06_zoom8x_r14_hard_vs_aa.png`、`07_zoom8x_r8_hard_vs_aa.png`、`08_zoom8x_three_routes.png` |
| **状态切换（四态）** | 自动演示定时器 step1（`setState(PRESSED)`，与 `onButtonClick_BtnCycle` 同一函数） | ✅ 状态 → PRESSED，填充色 0x2196F3 → 0x1976D2，状态行 `step1 setState(PRESSED) -> PRESSED（填充 0x1976D2）` | `evidence/02_state_pressed.png`、`10_diff_initial_vs_pressed.png` |
| **选中态** | 定时器 step2（`setSelected(true)`） | ✅ 第二个盒子 → SELECTED（0x0D47A1），日志 `step2 setSelected(true) -> SELECTED` | `evidence/03_toggle_selected.png`、`11_diff_pressed_vs_selected.png` |
| **按下态 + 回落幂等** | 定时器 step3/step4（`press(true)` → 抓图 → `press(false)`） | ✅ step3 帧捕获到 PRESSED（`按住（2px 边框）`盒变成按下色+边框）；step4 后回到 NORMAL（**不是卡在 PRESSED**），日志 `step4 press(false) -> NORMAL（幂等回落）` | `evidence/04_press_held_true.png`、`05_press_rolled_back_and_radius28.png` |
| **运行时换半径（切图做不到）** | 定时器 step5（`setRadius(28)`） | ✅ AA 行 r=14 → **r=28**（56 高的药丸），日志 `step5 setRadius(28) -> 200x56 药丸（无资产）`；同一份代码、无资产、无需重新打包 | `evidence/05_press_rolled_back_and_radius28.png`、`12_diff_initial_vs_radius28.png` |
| 像素 diff（机器可核） | `python tools/ui_tools/ui_diff.py 01 02 --out 10…` | ✅ 差异块只落在「当前状态盒 + 日志行」等相关区域，不是整屏乱刷 | `evidence/10_diff_*.png` |

> **触摸路径的实情（不藏）**：四个按钮的 `onButtonClick_*` 与上面定时器调的是**同一批函数**（业务侧接线已编译进去，`generated/ui_main.h` 可见 4 个 CLICK 监听）。
> 本轮上机时 **`/tmp/touch` 注入在本 boot 内没生效**（`touch list`/`check` 均正常：节点 `/dev/input/event0` gt9xx proto=MT-B，注入 rc=0；但 `--proto single/a/b`、`--hold 200`、`monkey` 后目标控件均无反应；同一轮里 device 曾被外部重起过）
> —— 所以**状态机证据改用不依赖触摸的自动演示定时器拿**，抓图仍可复现、且不走特殊路径；触摸注入的问题另记（见回报）。
>
> 复现命令（一条不差）：
> ```powershell
> # ① 本机：json -> ftu -> 编译
> python tools\ui_tools\html2json.py <example>\ui\main.html <example>\ui\main.json
> cd <example>\ui ; fui pack .
> cd <example> ; fun build -p Z21
> # ② 上机（Z21 同一时间只允许一个任务）
> adb reboot ; 等 35s ; adb connect 192.168.1.100:5555
> adb push tools\FlyThings_mcp_open\bin_tools\z21\touch /tmp/touch ; adb shell chmod 777 /tmp/touch
> python temp\uiv1\deploy.py <example>          # 同 boot 内只部署一次
> # ③ 一口气点完再抓图（touch 注入在同一 boot 的第 2 次部署后会失效）
> adb shell "/tmp/touch tap 89 372"   # BtnCycle
> adb shell "/tmp/touch tap 345 372"  # BtnToggle
> adb shell "/tmp/touch tap 485 372"  # BtnPress
> adb shell "/tmp/touch tap 625 372"  # BtnRadius
> # ④ 抓图 + 数字
> python tools\FlyThings_mcp_open\ui_tools\device_screenshot.py --device 192.168.1.100:5555 --out rb_01.png
> python <example>\aa_ideal.py rb_01.png --box 456,198,200,56 --radius 14 --corner tl --label AA_r14
> ```

## 8. 排错

| 现象 | 原因 | 处置 |
|---|---|---|
| 圆角外是**4 个黑方块** / 边缘一圈黑 | 代码自己 `erase()` 后跳过了圆角外像素，而设备上 `erase()` 留下的是不透明黑 | 用本包（0.1.0 起会先铺 `Style::bg` 再画）；自己写画法时**必须自己铺底** |
| 边缘有一圈「颜色不对的浅边」（halo） | `Style::bg` 与实际底色不一致 | 把 `bg` 改成按钮所在位置的真实底色（卡片色/页面色/图上的主色） |
| 什么都不显示 | 忘了 `refresh()`；或 `attach` 的不是 painter | `onUI_init` 末尾 `refresh()`；核对 json caption 与 `mXXXPtr` |
| 切页回来按钮没了 | painter 不自动重绘 | 在 `onUI_show()` 里 `refresh()` |
| 半径看着没变化 | 半径被夹到 `min(w,h)/2`（控件盒太小） | 把 painter 的 `position` 调大，或减小半径 |
| 边框看不见 | `border == 0`（且 `DISABLED` 态自动不画边框） | 给 `Style::border` 一个色 |
| `setStyle` 返回 `-1/-2` | `borderWidth < 1` 或 `aaSamples` 不在 2..16 | 按 `msg` 改（msg 是人话，可直接上屏） |
| **圆钮外围露出方角**（药丸端头处多出 1~2px 药丸色方块） | 画钮时**单独铺了 `dia×dia` 底色盒**，纽盒的**外上/外下角落在药丸端头半圆之外** —— 铺底盒没被外轮廓裁掉 | 本包 **0.1.1 起已修**（钮走图层叠加，`P == 0` 不画）；自己在 painter 上叠内嵌图形时同样要按外层轮廓裁，**不能**再单独铺盒。（`MODE_HARD` 对照路径仍是旧的铺盒画法，不修） |
| 点按钮没反应 | 本包不接管触摸 | 按 §5 接线（activity 触摸 或 盖一个 `button__N` 热区） |
| 按下去回不来（卡在 PRESSED） | 只调了 `press(true)`，UP/CANCEL 没接到 | `press(false)` 在 UP **和** CANCEL 都要调 |

## 9. 相关文件

- 目录规范（四件套）：`components/README.md`
- 映射与缺口：`ui_v1/gap-list.md` **G-07**（圆角/边框无平台能力）、`mcp_control_map.json`（`lvgl.lv_btn → button`）
- 平台事实：`ui_v1/platforms.md`（painter 的 11 个公开 API 各平台一致性）
- 抗锯齿口径（PC 侧）：`tools/ui_tools/gen_res.py`（`rounded_rect_ss` / `to_9patch`，FT-010）
- 本包数字的测量脚本：`example/aa_ideal.py`（与理想覆盖率比）、`example/aa_measure.py`（中间档档数/占比）
- 来源（只读，未改动）：`projects/translate/lvgl-widgets-uiv1/`（LVGL `lv_button` 倒角丢失 → `TRANSLATE.md` 差异清单 B）
- 状态表：`ui_v1/components.md`


## 10. 自带触摸（`setRect` + `onTouch`）—— 2026-09-16 钟工要求

> 原话：「radButton 需要自己接受触摸处理，应用程序把他当成一个带倒角的开关处理」。
> 于是本包从「只画不管」升级为「画 + 命中 + 按下态 + 沿手势取消 + 开关翻转」。

### 10.1 坐标口径（**必须记死**）

**绝对屏幕坐标**，与 `MotionEvent::mX/mY` 完全同口径。

为什么不让包自己算：`getAbsolutePosition()` / `getParent()` 在 Z21 设备端
`libeasyui.so` **未导出** → 链接能过、运行时 dlopen 失败 → **整屏黑**。
所以几何只能由业务给，业务用「祖先链上各层 `getPosition()` 相加 + 本 painter 的 `getPosition()`」：

```cpp
/* 例：控件在 pagewindow -> page -> card 里（层级写死在布局生成器里） */
static bool absRectOf(ZKBase *a, ZKBase *b, ZKBase *c, ZKPainter *p,
                      int &x, int &y, int &w, int &h) {
    int ox = 0, oy = 0;
    ZKBase *chain[3] = { a, b, c };
    for (int i = 0; i < 3; ++i) {
        if (chain[i] == NULL) continue;
        const LayoutPosition &q = chain[i]->getPosition();
        ox += q.mLeft; oy += q.mTop;
    }
    if (p == NULL) return false;
    const LayoutPosition &q = p->getPosition();
    x = ox + q.mLeft; y = oy + q.mTop; w = q.mWidth; h = q.mHeight;
    return w > 0 && h > 0;
}

int x, y, w, h;
if (absRectOf(mPwPagesPtr, mWinProfilePtr, mWinCard3Ptr, mPtSwTeamPtr, x, y, w, h)) {
    s_swTeam.setRect(x, y, w, h);      // 命中几何（屏幕坐标）
}
```

`setRect(left, top, width, height)`：`width/height <= 0` 时退回 painter 自身尺寸；
**没调过 setRect → `onTouch()` 恒返回 false（不消费）**，这是最常见的「点了没反应」原因。

### 10.2 `onTouch(x, y, action)` 状态机（一张表看完）

| 事件 | 界内 | 界外 |
|---|---|---|
| `TOUCH_DOWN` | 进按下态（记住按下前状态），**返回 true** | 返回 false（不碰我） |
| `TOUCH_MOVE` | 自家手势 → 返回 true | **取消按下态**（`press(false)` 回落）→ 返回 true |
| `TOUCH_MOVE`（没按下过） | 返回 false（让滑动/翻页照常） | 返回 false |
| `TOUCH_UP` | 回落 →（开关模式）**翻转 + 触发回调**，返回 true | 只回落，返回 false |
| `TOUCH_UP`（没收到 DOWN） | 开关模式**兜底翻转**（触摸注入/快扫场景），返回 true | 返回 false |
| `TOUCH_CANCEL` | 回落，返回 true | 返回 false |

- **返回值 = 是否已消费**：`true` 时业务应把这个事件吞掉（activity 触摸回调里 `return true`），
  别再交给下层控件；`false` 时照常往下传。
- `DISABLED` 状态：**按下态照常显示，但不翻转**（`toggle()` 返回 `ok（DISABLED：不翻转）`）。
- 默认 `setAutoRefresh(true)`：状态真的变了就顺手 `refresh()`（painter 不自动重绘）；
  想自己控重绘 `setAutoRefresh(false)`。
- 全部操作**幂等**：重复 DOWN 不覆盖基准、界外 UP 不翻转、同状态 `setOn` 不重复回调。

### 10.3 两种接线姿势（案例里都用到了）

| 姿势 | 写法 | 适用 |
|---|---|---|
| **喂给包看按下态，不消费** | `feedRadButtons()` 里让普通按钮**不置 eaten** | 按钮的文字/图标在平台 `button__N` 上、点击语义不想动 |
| **完全交给包（消费）** | 开关类按钮置 `eaten = true` → activity 层 `return true` | 开关/自绘控件，屏上只有 painter，点击语义归包 |

```cpp
static bool feedRadButtons(const MotionEvent &ev) {
    int act = (ev.mActionStatus == MotionEvent::E_ACTION_DOWN)   ? zk::ui_v1::RadButton::TOUCH_DOWN
            : (ev.mActionStatus == MotionEvent::E_ACTION_UP)     ? zk::ui_v1::RadButton::TOUCH_UP
            : (ev.mActionStatus == MotionEvent::E_ACTION_CANCEL) ? zk::ui_v1::RadButton::TOUCH_CANCEL
                                                                 : zk::ui_v1::RadButton::TOUCH_MOVE;
    bool eaten = false;
    for (int i = 0; i < s_bindN; ++i) {
        const bool c = s_binds[i].btn->onTouch(ev.mX, ev.mY, act);
        if (c && s_binds[i].consume) eaten = true;   // 只有「开关」把事件吞掉
    }
    return eaten;
}
```

⚠️ **别双重处理**：如果平台按钮的 `onButtonClick_XXX` 里**也**翻转状态，而包的 UP 又翻转一次 → 双翻。
案例做法：开关类按钮的 `onButtonClick` 只做「按包的状态同步业务」（`s_teamPlayer = pill.isOn()`），不自己翻转。

## 11. 开关语义 + PILL 药丸形态 —— 2026-09-16 新增

| 成员 | 说明 |
|---|---|
| `Result setSwitchable(bool)` | 开关模式（`onTouch` 的 UP 界内翻转）。**`setShape(SHAPE_PILL)` 会自动打开** |
| `bool switchable() const` | 当前是否开关模式 |
| `Result setOn(bool)` / `bool isOn()` | = `setSelected()` / `isSelected()`；**幂等**，且编程置位**不**触发回调 |
| `Result toggle()` | 翻转（幂等；DISABLED 不翻转）+ 触发 `setOnToggle` 回调 |
| `Result setOnToggle(ToggleCallback cb, void *user)` | 注册翻转回调（`cb=0` 摘掉）；回调签名 `void(bool on, void *user)` |
| `Result setShape(Shape)` / `Shape shape()` | `SHAPE_RECT`（矩形倒角，半径用 `Style::radius`）/ `SHAPE_PILL`（药丸 = 半径 h/2 + 圆钮）；别名 `RECT` / `PILL` |
| `Result setPillStyle(const PillStyle &)` | 圆钮配置：`padding`（内边距，也是钮位基准）/ `knobDia`（0=自动=h-2*padding）/ `knobOff` / `knobOn` |

**药丸怎么画的**（一次 `refresh()` 两笔）：

| 层 | 画法 | 颜色来源 |
|---|---|---|
| 轨道 | `drawRoundedRect(0,0,w,h, h/2, ...)` | **关** = `Style::normal`，**开** = `Style::selected`，**禁用** = `Style::disabled`，**按下** = 当前轨色压深 12%（`mix(track,0x000000,88)`） |
| 圆钮 | 「边长 `dia`、圆角 `dia/2`」的圆角矩形（= 正圆，AA 口径与轨道一致） | `pillStyle().knobOff / knobOn`（默认都是白）；禁用时与禁用色混 60% |

**钮位**：关 → `x = padding`；开 → `x = w - padding - dia`（对称，不用自己算）。
**轨色/钮色都在运行时给** → 换主色、换尺寸都不用出图（切图路线做不到，这正是本包存在的理由）。

最小用法：

```cpp
zk::ui_v1::RadButton::PillStyle ps;         // padding=3 / knobDia=0(自动) / 白色圆钮
s_sw.setPillStyle(ps);
s_sw.setStyle(st);                          // st.normal=关轨色 0xB0BEC5, st.selected=开轨色 0x2196F3
s_sw.setShape(zk::ui_v1::RadButton::PILL);  // 药丸 + 自动打开开关模式
s_sw.attach(mPtSwTeamPtr);
s_sw.setRect(664, 452, 56, 28);             // 绝对屏幕矩形
s_sw.setOnToggle(onToggle, NULL);           // void onToggle(bool on, void*)
s_sw.setOn(false);
s_sw.refresh();
```

`example/ui/main.html` 的**第 6 行**就是这套的实物演示（PILL 开关 / PILL 禁用态 / RECT 倒角开关，
三块下面**没有平台按钮**，命中完全归包）。

## 12. 排错（触摸/开关补充）

| 现象 | 原因 | 处置 |
|---|---|---|
| `onTouch()` 恒返回 false，点了没反应 | 没调 `setRect()` | 按 §10.1 算绝对矩形后 `setRect()` |
| 命中偏了（要点偏一点才中） | 坐标不是**绝对屏幕坐标**（给了父相对坐标） | 把祖先链偏移加上；或按 §10.1 的 `absRectOf()` 现算 |
| 按下去弹不回来 | UP / CANCEL 没喂给包，或喂了但 action 码传错 | 四个 action 都要映射（含 `TOUCH_CANCEL`） |
| 手指划出按钮还显示按下态 | MOVE 没喂（或没映射到 `TOUCH_MOVE`） | 把 E_ACTION_MOVE 也喂进来 |
| 点一下开关翻两次 | 平台按钮的 `onButtonClick` 里又翻了一次 | 让 `onTouch` 消费（`return true`）**并**把 onClick 改成「只同步不翻转」 |
| 开关点了没反应 | 包返回 true 被业务忽略，事件又传给下层控件 | 业务按返回值 `return true`（消费） |
| 药丸两端是直角 | 用的是 `SHAPE_RECT` + 大半径 | 换 `SHAPE_PILL`（半径严格 = h/2） |
| 圆钮不是正圆 / 偏出药丸 | `padding`/`knobDia` 配得太大 | `knobDia=0`（自动）或保证 `2*padding + dia <= h`（包内已自动夹取） |
| 开关开态颜色不跟主色走 | 业务换主色后没重设 | `setColors(..., selected=新主色, ...)` + `refresh()`（案例里在 `applyPrimary()` 统一做） |

**接案例时踩到的坑（记下来给别人省时间）**：想把倒角 painter 画在**平台按钮下面**（z 更低），
就必须让按钮**别盖住** painter。而 `html2json` 的 button 分支是
`if bgc or text: bgColorTab = bgc or 0x374457` -> **文字按钮一去掉 `data-bg` 就会被填深色底 0x374457**。
两个可行解：(1) 给按钮挂一张**全透明切图**（`picTab`）——有图时 html2json 会自动去掉 `bgColorTab`
（官方 `UserIme` 键盘就是这个口径）；(2) 在生成器里后处理 json 抹掉 `bgColorTab`。
案例（`projects/translate/lvgl-widgets-uiv1`）用的是 (1)，切图由 `gen_assets.py` 按 json 的
`position` 自动出（尺寸严格相等，图片铁律 #1）。
