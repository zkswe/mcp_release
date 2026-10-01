---
id: uicontrols-scrollwindow-layout-checklist
title: scrollwindow 布局异常清单（反复踩的那些坑 + 逐条判据）
category: uicontrols
status: review
confidence: manual
verified_at: 2026-10-01
stale_days: 180
origin: partial
source: 2026-09-20~10-01 SmartPanel_HA 现场反复返工 + 2026-10-01 真机交互复核（480×480 面板）
needs_evidence: true
platforms: [Z20]
tags: [scrollwindow异常, 滚动窗口显示不对, 加了一行滚不到, 末尾行看不到, 内容堆叠, 固定件跟着滚, 点了点不到, 图标被文字盖住, 改了像没改, 滑动窗口怎么做]
evidence:
  - "2026-10-01 真机复核（192.168.x.x / Z20 480×480）：settings 页视口 418 / 内层 window 832（行程 414，dragMaxDis=60）→ 滚到底后最底行完整出现在 y≈441，点它进入「多屏拼接」"
  - "同次复核：标题带 y0..62 跨顶/底两帧超容差像素 = 0（固定件不滚）；行端箭头恒在 x=437..442 与数值段(≤417) 间隙 20px 无重叠"
  - "SmartPanel_HA 历史返工：window 高 720→776→832（每加一行整体下移 56）；新行直挂 scrollwindow 未进内层 window；行端箭头被数值文字压住（重叠 22px）"
---

# scrollwindow 布局异常清单（反复踩的那些坑 + 逐条判据）

> 检索导引：scrollwindow 布局异常 / 滚动窗口显示不对 / **加了一行滚不到** / 末尾行看不到 /
> 内容堆叠 / 固定件跟着滚 / 滚到底点不到 / 图标被文字盖住 / **改了像没改** / 滑动窗口怎么做 /
> 内层 window 高度填多少 / `dragMaxDis` 怎么填 / 行内控件重叠。
> 用途：**写/改滑动窗口页面前照着过一遍**；每条都给了机读判据（工具 → 判什么 → 阈值）。
> 口径来源：`dragMaxDis` 语义见 `knowledge/uicontrols/scroll-drag-interaction-spec.md`；
> 层级合法性见 `knowledge/uicontrols/json-layer-rules.md`。

## 0. 结构（先摆对，再谈别的）

```
scrollwindow__N（视口：只决定「看多大」）
  └── window__M（内容：**尺寸 = 内容总高**，引擎按它算行程）
        └── 行/卡片（button + 背景图 + 图标 + 文字，绝对坐标平铺）
固定件（标题/返回、分组说明、底部状态行与主按钮）→ **放在 scrollwindow 外面**
```

- **行程 = 内层 window 尺寸 − 视口尺寸**（引擎自算）；`dragMaxDis` 只决定越界拖拽手感，**不是行程**。
- `scrollwindow` **只能装 `window`**（子控件必须进内层 window，不能平铺挂在 scrollwindow 上）。

## 1. 十类反复出现的异常（现象 → 根因 → 修 → 判据）

| # | 现象 | 根因 | 修 | 机读判据 |
|---|------|------|----|----------|
| 1 | **加了一行，末尾滚不到 / 最后一行看不到** | 内层 `window` 尺寸没跟着内容加高（行程不够） | 内层 window 高 = 内容总高（行数×行距+首行偏移），**每次增删行都要同步** | `check_all` **#26 WARN-A**（行程≤0 但内层内容已超出） |
| 2 | 新加的行/控件**整块不显示** | 新控件**直接挂在 `scrollwindow` 下**（该容器只装 window） | 搬进内层 `window__M`，并把 window 加高 | `check_all` **#2 层级合法性**（pagewindow/scrollwindow 只装 window） |
| 3 | 标题/底部按钮**跟着一起滚走** | 固定件放进了 scrollwindow | 固定件移到 scrollwindow 外层；只滚中间列表 | 实机：标题带跨顶/底两帧像素差 = 0（`ui_visual(action="diff")`） |
| 4 | 判定「**滚不到底**」或把内容尺寸写进 `dragMaxDis` | 把 `dragMaxDis` 当行程（旧误读） | 行程按内层 window 算；`dragMaxDis` 取手感值 50~200（480×480 取 40~60） | `check_all` **#26**（打印行程 + WARN-B：`dragMaxDis` ≥ 可视尺寸） |
| 5 | **滚到底后点行点错**（点到别的行/别的页） | 触摸坐标没叠加 scrollwindow 的 `top` + **当前滚动偏移** | 目标坐标 = 行在内容窗口内的 y + scrollwindow.top − 滚动偏移 | 实机：滚到底后按算式坐标 tap → 命中预期页（日志 + 截图） |
| 6 | 行端**箭头/图标看不见** | 行内控件盒重叠：引擎**先画背景图、后画文字**，数值文字把图标盖住（实测重叠 22px 即必现） | 拉开盒子（数值框右缘 ≤ 箭头盒左缘 − 间隙）；图标/箭头别与同层文字重叠 | 像素：行内墨迹列段互不重叠（箭头段恒定、与数值段留 ≥ 10px 间隙） |
| 7 | 某几行**倒角线看着变粗** | 同一页混用两种切图口径（有描边带 vs 素面） | 同族图统一口径（素面 r=12 + 覆盖率高斯/BOX 面积平均） | `check_all` #22/#25 + `references/kb/image-gen-standard.md` §1.6 |
| 8 | 控件**拖不动** | scrollwindow 缺 `touchable:true` | 补 `touchable:true` | `check_all` #14 字段全集 |
| 9 | **改了像没改**（界面上还是旧布局） | ① 改 json 没立刻 `fui pack` → `fun pack` 的 ftu→json 自动同步把改动打回；② **部署层混搭**（新 lib + 旧 UI） | ① 改完 json 立刻 pack 出 ftu；② 部署后跑 `flythings_selfcheck` **第⑪区「部署一致性」** | 见 `knowledge/devflow/deploy-consistency-check.md` |
| 10 | 内容溢出屏幕 / 元素挤在一起 ("堆叠") | 设计期没算「内容总高 vs 可用高」，靠压行距/字号硬塞 | 设计阶段先算总高，超了就上滑动窗口（钟工 2026-09-26 口径） | 见 `knowledge/devflow/design.md` 的「内容可能溢出 → 用滑动窗口」 |

## 2. 建/改滑动窗口页的流程（防返工）

1. **先算数**：行数 × 行距（含首行偏移）= 内容总高；`可用高 = 页面高 − 顶部固定带 − 底部固定带`。
   - 内容总高 ≤ 可用高 → **不要**上 scrollwindow（白放一层，见 `check_all` #26 的相反提示）。
2. **摆结构**：`scrollwindow`（视口 = 可用高）→ 内层 `window`（高 = 内容总高）→ 行控件；固定件外置。
3. **一次改一处**：增删行时**同一脚本里**同步改三样 —— ① 行控件坐标 ② 内层 window 高 ③ 后续行整体平移量。
   （反例：SmartPanel_HA 设置页 `window` 高一路 720→776→832，每轮要平移 43~50 个控件 —— 手改必错。）
4. **静态自检**：`python tools/ui_tools/check_all.py <项目根>`（重点 #2 / #14 / #15 / **#26**）。
5. **出确认稿**给需求方看：`flythings_ui_preview(target, for_customer=True)`。
6. **上机复核**（改完必做，判据见 §3）。

## 3. 上机复核判据（2026-10-01 实测口径，可直接照抄）

| 判据 | 做法 | 通过标准 |
|------|------|----------|
| 行程/末尾可达 | 连续上滑到底，抓帧 | 最底行**完整可见**且可点（例：视口 418/内容 832 → 行程 414 ≥ 一行高） |
| 越界手感 | 到底后继续长滑，抓**手势中途帧** vs 底位基线帧 | 不出现整屏露底；本工程实测为「零位移」（越界未产生可见位移） |
| 固定件不滚 | 顶位帧 vs 底位帧，比固定带 | 固定带超容差像素 = 0 |
| 触摸命中 | 滚到底后按算式坐标 tap | 命中预期页/行（`logcat -s zkgui` 佐证） |
| 行内层叠 | 行带列墨迹连通段统计 | 箭头段与数值段互不重叠（间隙 ≥ 10px） |

工具：`bin_tools/<平台>/touch`（注入）+ `flythings_device_screenshot`（抓帧，含 pan 校正）+
`flythings_ui_visual(action="diff")`（像素比对，0 token）。**`touch raw` 在部分板卡无效**，
量越界请用 `touch swipe` + 中途抓帧，别指望「按住不放」。

## 4. 相关

- `dragMaxDis` / `edgeEffect` / `autoRollback` / `rollSpeed` 取值：`knowledge/uicontrols/scroll-drag-interaction-spec.md`
- 容器→子内容层级矩阵（scrollwindow 只装 window）：`knowledge/uicontrols/json-layer-rules.md`
- 字段必写全集：`knowledge/uicontrols/json-field-mandatory.md`
- 部署层「新库旧界面」混搭：`knowledge/devflow/deploy-consistency-check.md`
- 页面架构（何时该拆页、多全屏 window 的替代）：`knowledge/devflow/page-architecture-spec.md`
- 布局验收与确认稿流程：`knowledge/devflow/ui-layout-verify.md`
