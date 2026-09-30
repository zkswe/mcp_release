---
id: devflow-render-extension-boundary
title: 渲染扩展能力边界（基础控件 / canvas 画布 / 自定义控件 三层）—— 非 3D GPU 皆可，含软件模拟
category: devflow
status: review
confidence: manual
verified_at: 2026-09-30
stale_days: 180
origin: total
source: 2026-09-30 钟工口径（"FlyThings GUI 提供基础控件，canvas（textview + setBackgroundBmp）提供自定义渲染扩展，自定义控件方案可扩展到任意不需要 3D GPU 的效果，但可支持软件模拟 GPU 效果"）+ 修正 custom-render-paths.md / framework-control-mapping.md 的不当表述
needs_evidence: true
platforms: []
tags: [渲染能力边界, canvas 画布, 自定义控件, 自绘, 位图画布, 硬件合成, 软渲染, 软件模拟 GPU, 伪 3D, 真 3D, GPU, 视频图层尺寸, 任意角度旋转, 动画计时, 绝对时间基准]
evidence: []
---
# 渲染扩展能力边界（基础控件 / canvas 画布 / 自定义控件 三层）

> **检索导引**：问「FlyThings 能做到什么视觉效果 / 渲染能力边界在哪 / 有没有 GPU /
> 能不能做 3D / 平台缺这个控件能不能自己做出来 / canvas 画布能做到什么程度 /
> 自绘限制有哪些 / 软件模拟 GPU 效果行不行 / 文字缩放有没有上限 / 视频图层尺寸限制 / 动画计时怎么算」→ 本文（**能力边界总纲**）；
> 具体做法见 `devflow/custom-widget.md`（自定义控件方法论）、`devflow/custom-render-paths.md`（渲染五条路）、
> `uicontrols/custom-view-refresh.md`（刷帧口径）。
>
> **口径来源**：2026-09-30 钟工定 —— 本文是**能力边界的唯一权威表述**，其余文档只讲做法，不另立边界。

---

## 0. 一句话

**FlyThings 的 UI 能力是三层的：基础控件（够用的常规 UI）→ canvas 画布（单控件级自绘扩展）→
自定义控件（控件级完整扩展）。这三层合起来，可以覆盖「任意不需要 3D GPU 的效果」；
需要 GPU 风格的效果可以用软件模拟（软渲染 / 软光栅）达成；真正做不到的只有
「必须真 3D GPU 实时管线（着色器 / 实时光栅化 / 硬件加速 3D）」这一类。**

---

## 1. 三层模型（能用到哪一层，先看需求落在哪层）

| 层 | 形态 | 能力 | 落到哪份文档 |
|---|---|---|---|
| ① **基础控件层** | 内置 **21 控件**（button / textview / edittext / window / listview / slidewindow / scrollwindow / pagewindow / pointer / circlebar / diagram / digitalclock / imageanim / painter / qrcode / radiogroup / checkbox / seekbar / cameraview / videoview / slidetext）+ 自研 **8 控件**（lib-ext_widgets） | 常规交互与显示（含列表、翻页、动态波形、表针、环形进度、动图、二维码…），**纯 json/ftu 配置即用** | `devflow/gui-controls-gap.md`（家底/缺口）、`uicontrols/*`（字段） |
| ② **canvas 画布层**（自定义渲染扩展） | **`ZKTextView` / `ZKButton` + `setBackgroundBmp(bitmap_t*)`**（挂一张内存位图当画布，自己在 `data` 上画/拷帧）；或 `ZKPainter` 控件在控件画布上直接画 | **单控件级自绘**：帧序列、位图自绘、图像处理、游戏画面、指针/波形类局部绘制 | 本文 §2 + `uicontrols/custom-view-refresh.md` |
| ③ **自定义控件层** | 继承 `ZKBase`（`create(Json::Value())` 纯代码实例化）→ **组合基础控件** 或 **重写 `onDraw(ZKCanvas*)`** → 暴露 `build(attr)` / `setXxxAdapter()` | **控件级完整扩展**：平台没有的控件都能自己造（富文本、图表、表格、下拉选择、拖拽排序…） | `devflow/custom-widget.md`（10 步 checklist） |

层级选择顺序：**① 能用就别往下走**；① 表达不了 → ②（单控件自绘最省事）；② 也不够（要多控件协作 / 要复用 / 要进组件库）→ ③。

## 2. canvas 画布层的标准形态（务必按这个写法）

```cpp
// ① 内存位图当画布（createBmp / BitmapHelper），只挂一次
mTextView->setBackgroundBmp(&bmp);                 // ⚠️ 只调一次，别每帧新建位图
// ② 内容变化：直接改写位图 data，然后交替 invalid 触发重绘
mTextView->setInvalid(!mTextView->isInvalid());    // 自定义 view 的每帧刷新口径
```

- **只调一次 `setBackgroundBmp`**，帧刷新靠 `setInvalid` 交替（每帧新建位图 = 分配抖动/内存涨）。
- ⚠️ `setInvalid(!isInvalid())` 是「状态变更顺带重绘」的**旁路技巧**，不是通用重绘 API：
  用在**可交互控件**上会把它半个周期置成无效态（点不动）→ 可交互控件请用别的手段；
  自定义 view（内容自己在位图里改）用它刷帧是平台通行做法。
- 自绘控件（`onDraw`）走 `ZKCanvas` API + 预解码 `bitmap_t` + `Region` 脏区。详见 `devflow/custom-widget.md` §6。

## 3. 边界（三条，按"能不能"分）

1. **不需要 3D GPU 的效果：都能做。** 矢量图形、图表仪表、富文本排版、图像处理、动画、
   伪 3D（贴图 + 烘焙阴影 + 序列帧）、软件光栅化的"GPU 风格"效果（渐变/模糊近似/光照贴图烘焙）——都在能力范围内，
   走 ② 或 ③。
2. **GPU 风格但不要实时管线：可以，用软件模拟。** 即"**软渲染 / 软光栅**"路线：
   在内存画布上用 CPU 画好再交给框架显示（②b 运行时离屏渲染，`custom-render-paths.md` §2），
   或用 PC 离线预烘成图序列（②a，运行时零成本）。**代价是 CPU 与带宽，不是"做不到"**。
3. **必须真 3D GPU 的：做不到。** 实时着色器、实时光栅化 3D、硬件加速 3D 管线这类需求超出边界
   （`custom-render-paths.md` §4 的禁忌同理：不要在框架进程里另起 GTK/Qt 主循环抢 fb）。
   平台现状：**F133 / Z21 无 GPU、无硬解 → 只能伪 3D / 软模拟**；**真 3D 目前仅 V85X**（disp 分层）验证过。

> ⚠️ 性能不是边界，是**预算**，而且要说清**哪一段花钱**（2026-09-30 钟工更正）：
> **绘制进内存画布**那一段取决于实现/面积（我方 `src/core/PgCanvas.*` = 自研软件实现）；
> **内存画布 → 屏幕**那段是**硬件合成**（平台有 bitblt / 透明 α 混合 / 90° 旋转能力，
> 实证见 `custom-render-paths.md` §0-3）——**不要把“我们的实现是软件”说成“平台只能软渲染”**。
> 开销预算/降本选型不在此页重复展开 → `custom-render-paths.md` §1/§2/§3。

## 4. 术语消歧（**"canvas" 在平台里有三种意思，别混用**）

| 说法 | 指什么 | 判定 |
|---|---|---|
| **布局画布** | 布局 `resolution` / 面板可视区（画布必须盖满面板，否则底部露残留帧） | `devflow/canvas-panel-coverage.md` |
| **内存画布** | `bitmap_t` 内存位图（`createBmp` / `BitmapHelper`），挂在控件上当画布 | 本文 §2 / `devflow/custom-widget.md` §6 |
| **控件画布** | `onDraw(ZKCanvas*)` / `ZKPainter` 拿到的控件绘制面（控件相对坐标，0,0 = 控件左上） | `uicontrols/widget-code-api.md`（ZKPainter） |

检索/写文档时写清是哪一个。“canvas 宽度有上限”这类说法**不成立**（GUI 层缩放/绘制无限制），
唯一相关的尺寸约束是**视频图层尺寸不能超过屏幕区域**（见 §5），别算到画布/文字缩放头上。

## 5. 已知限制（**定性口径；无具体数值上限**）

> ⚠️ 上一版把下面几条写成"画布规格通则"，**表述不当**（无 API 主体、无平台、单点外推），2026-09-30 已改写；
> 同日钟工**三次更正**：「**scale 在 GUI 层没有限制**」→「早年那个 448 限制是**误测，去掉**；全志平台就只有一个
> 视频图层尺寸不能超过屏幕区域的问题」→ 随后给出**两条旧说法的真根因**（见下表：字库预烘档位 / 448=内容区宽）。

| 项 | 准确口径 | 状态 |
|---|---|---|
| **GUI 层缩放 / 文字绘制** | **平台/画布无限制**。旧说法"`scale` 必须是常量 / 只认编译期常量"的**真实出处是我们自研字库只预烘有限档**：档位需编译期常量，**超档位走位图放大 = 拉伸**（违反"不许拉伸"要求）⇒ **资源侧约束，不是画布/引擎限制**（`components/fonts/`；font 相关见 `devflow/custom-font-config.md`） | 已定论 |
| **视频图层尺寸** | **视频图层尺寸不能超过屏幕区域**（全志平台唯一相关限制，定性口径、**不挂具体数值**） | 已定论 |
| ~~画布宽度上限~~ | **已作废（误记）**：早年那个具体数值 = **某工程 UI 的内容区宽**（屏宽 − 2×16 布局留边），**不是任何限制** | 已撤回 |
| **平台做不到的事** | **任意角度旋转位图**：`ZKPainter` 不画位图、`misc::bitmap_rotate` 只支持 **90° 整数倍**，其他角度要自己逐帧算（先例 `components/vinyl` `zk::VinylSpin`，见 `reusable-components.md` §8） | 已定论 |
| **动画计时基准** | **用绝对时间基准（单调时钟 / 时间戳差值）**，不用"帧计数"或相对累加（帧率漂移会累积）。（原话叫"绝对时钟"，为避免与 `digitalclock` 数字时钟**控件**撞名，本库写作绝对时间基准） | 待补判据（漂移对比截图） |

## 6. 相关文档

- 渲染五条路（选型/决策树/禁忌）：`devflow/custom-render-paths.md`
- 自定义控件方法论（继承 ZKBase / 组合 / onDraw / Attr / 适配器 / 10 步 checklist）：`devflow/custom-widget.md`
- 自定义 view 刷帧唯一口径（`setInvalid(!isInvalid())`）：`uicontrols/custom-view-refresh.md`
- 平台缺哪些控件 / 21+8 家底：`devflow/gui-controls-gap.md`
- 跨框架控件映射（有控件就映射，不手写自绘）：`uicontrols/framework-control-mapping.md`、`uicontrols/control-mapping-capability.md`
- 布局画布必须盖满面板：`devflow/canvas-panel-coverage.md`
- 可复用组件交付形态（自定义控件做出来怎么交）：`devflow/reusable-components.md`
