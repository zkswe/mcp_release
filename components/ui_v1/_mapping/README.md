# components/ui_v1/_mapping/ —— 映射参考（**不是自定义控件包**）

> **口径（2026-09-16 钟工）**：跨框架控件分两类处置——
> 1. **有平台对应控件 → 走「映射能力」**：机读索引 `mcp_control_map.json` + MCP op
>    `flythings_map_control(query, source)`，一次对上我们的控件（级别 + 缺口 + 可直接粘的 json 片段）。
>    **不写散文说明**。
> 2. **平台真缺的能力 → 走自定义控件包**：`components/ui_v1/<源控件名>/`（四件套 + `example/` + 真机证据）。
>
> 本目录放**第 1 类里「已验证的接线/参数」**——它**有平台对应控件**（因此不算缺能力的自定义控件包），
> 但对齐过的接线细节（手感参数、双向同步、真机验收判据）值得留档，避免下一个案例重新推一遍。

## 目录

| 目录 | 源控件（各家） | 平台对应控件 | 为什么留档（不是控件包） |
|---|---|---|---|
| [`TabView/`](TabView/README.md) | LVGL `lv_tabview`；Android `TabLayout`+`ViewPager`；小程序 `swiper`+`tab`；Qt `QTabWidget` | **`pagewindow`（ZKPageWindow）** —— 自带滑动切页 + `onPageChange` | 接线细节：页签高亮/下划线**双向同步**（真源 = `getCurrentPage()`，幂等）、手感参数默认值 `dragMaxDis=200 / edgeEffect=1 / rollSpeed=60 / orientation=0`（无运行时 setter → 默认值 + 自检）、`onPageChanged` 只在真变页时回调；含 Z21 真机证据（滑动切页 / 点页签 / 页内控件不被吃） |

## 怎么用

1. **先查映射**：MCP op `flythings_map_control(query="lv_tabview")`（或直接读 `mcp_control_map.json`）
   → 拿到 `target=pagewindow`、`level=L1`、`json`（可直接贴进 `ui/*.json`）、`ref`（指到本目录）。
2. **再抄接线**：需要「页签高亮 + 下划线 + 手势滑动」这套行为时，照本目录对应包里的
   `README.md` §1/§2（接线 + HTML 原型片段）与 `example/src/logic/mainLogic.cc`。
3. **别做反了**：tab 类**禁止**用「多个整屏 `window` + 按钮显隐」拼（**丢手势滑动**，见
   `../gap-list.md` G-01 与 `../control-map.md` §1.2/§1.3 的本轮修正）。

## 相关

- 机读映射数据：`../../mcp_control_map.json`（唯一来源；由 `control-map.md` / `gap-list.md` / KB 收口而来）
- 权威映射表（散文版，含级别判定与换算）：`../control-map.md`　·　缺口：`../gap-list.md`
- 能力说明（这个 op 怎么用、命中不到怎么办）：`knowledge/uicontrols/control-mapping-capability.md`
- 自定义控件包（平台真缺的）：`../Chart/`、`../components.md`（计划段）
