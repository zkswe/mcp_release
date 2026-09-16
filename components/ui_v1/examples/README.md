# examples（ui_v1）— 已完成案例索引（映射表的实证来源）

> 本目录**不放代码**：本代（ui_v1）的两个已完成案例都在**开发工作区**，
> 不在 MCP 包内（不随包发布）。这里只登记「哪个案例证明了哪张表/哪条结论」，便于按需回查证据。
>
> 工作区路径（从 MCP 仓库根算起）：`../../../projects/translate/`
> 建立：2026-09-16（v0.27.71-open）

---

## 1. 案例 A：小程序「表单 + 列表」双平台转换（批次 1 试水 A）

| 项 | 值 |
|---|---|
| 工程 | `projects/translate/miniprogram-form-list/` |
| 源 | `wechat-miniprogram/miniprogram-demo`（**MIT**）commit `0fe5c7d`；页面 `packageComponent/pages/form/form` + `pages/view/scroll-view` |
| 目标 | Z21 1024×600（真机验收）+ F133 1280×800（仅编译产物） |
| 核心文档 | `TRANSLATE.md`（§1 控件映射 / §2 逻辑映射 / §3 差异 D1~D22 + §3.2 3D / §4 组件提名）、`README.md`（§5 证据、§6 工具链问题 T1~T6） |
| 自绘用量 | **0 处**（全部能力被自带控件承载 → 证明「组合优先」可行） |

**真机证据要点（`z21/evidence/`，18 张）**
- 表单：`02` 开关变蓝并换态、`03` 单选高亮 + 两个复选**同时**打勾（多选成立）、`04` 滑块拖动数值随动、
  `05` 提交回显整表单取值（**真实读控件**）、`06`/`07` 按钮 → **modal window 列表** 弹出与关闭、`08` Reset 全复位。
- 列表：`10` 行点击变「已选中」、`11`/`12` 刷新状态机跑完并自动收敛、`13` 加载更多 6→9 行并定位末项、
  `14` 横向三选一、`15`/`16` 触摸位移驱动进度（滚动驱动动画的降级实现）、`17` 回顶、`18` 返回后状态未丢。
- 附带：`fix_res_paths*.sh`（T2 现场修复脚本，交付物的一部分）。

**本案例证明了哪些结论**
- `control-map.md`：2.5/2.6/2.7（两态按钮绕 checkbox 缺口）、2.9/2.10（滑块 + 数值文本）、2.14（picker=L4）、
  2.15（日历 42 textview + 触摸反算）、1.5（横向滚动 L4）、1.15（无 flex）、3.10（下拉刷新 L4）、3.12~3.14（滚动位置/到顶到底/直跳）
- `logic-map.md`：回调逐个显式定义、`collectFormValue()` 聚合、定时器状态机、`setSelection` 后必须 `refreshListView`
- `gap-list.md`：G-02/G-18/G-19/G-21/G-22/G-24/G-25/G-27~G-33、T1~T6、T8、T9、T10

---

## 2. 案例 B：LVGL `lv_demo_widgets` 转换（批次 1 试水 B）

| 项 | 值 |
|---|---|
| 工程 | `projects/translate/lvgl-widgets/` |
| 源 | `lvgl/lvgl` → `demos/widgets/`（v9.3.0 开发线，commit `3c25ac6`，**MIT**）；取 `Profile` + `Analytics` 两页（`Shop` 不转） |
| 目标 | Z21 1024×600（真机验收）+ F133 1280×800（仅编译产物，rotate 270/270） |
| 核心文档 | `TRANSLATE.md`（§1 控件映射 / §2 逻辑映射 / §3 差异 20 条 + §3.1 自绘论证 / §4 视觉令牌）、`README.md`（许可复核、取舍、一次成流程） |
| 自绘用量 | **5 处**（`PtLine`/`PtBar`/`PtArc`/`PtSess`/`PtGauge`），全部集中在**图表类** → 定义了 L3 自绘的边界 |

**本案例证明了哪些结论**
- `control-map.md`：3.2（无 chart → 自绘 + textview 刻度）、2.12/2.13（circlebar 单环 / pointer 需表盘图）、
  1.11（阴影默认不画）、2.2（textview 不自动折行）、2.17（Symbol 字体 → 图标 PNG）
- `logic-map.md`：`LV_EVENT_VALUE_CHANGED` → `onCheckedChanged_*`/`onProgressChanged_*`、`lv_timer`/`lv_anim` → 定时器 tick 自算、
  painter 不自动重绘 → 显式 `renderXxx()`、随机数用自带 LCG（可复现便于验收）
- `gap-list.md`：G-01（tab，**历史写法待修正**）、G-05~G-11、G-20、G-26、G-35、T11（`drawArc` 口径）
- **待修正点**：案例里的「2 个整屏 `ZKWindow` 显隐 + 页签按钮」是**旧写法**（丢手势滑动），
  新工程一律走 `pagewindow`（见 `control-map.md` §1.2/§1.3 + §6 C1）。**案例工程不改**，作为历史留痕。

---

## 3. 引用规则

1. 要**证据**（截图/日志/实测值）时回这两个案例目录取，不要在 `ui_v1/*.md` 里复制大段案例内容。
2. 案例里的**旧级别**（A/B/C/D、旧 L1~L5）保持原样；换算关系以 `control-map.md` §0.1 为准。
3. 新案例做完，**先补 `control-map.md` / `gap-list.md` / `components.md`**，再在本文件加一节（含证据清单）。
4. 案例工程若被后续批次的写法取代（如 C1 的 tab），**在表里点名「历史写法」**，不要悄悄改案例文档。
