---
id: devflow-device-preflight-spec
title: 上机前体检判据（分辨率适配 / 字库 / res 体积预算，唯一真源派生）
category: devflow
status: review
confidence: manual
verified_at: 2026-10-03
stale_days: 180
origin: derived
source: 由 preflight_spec.json 派生（scripts/gen_preflight_doc.py）；字库阈值与档位与 components/fonts 跨来源对账
needs_evidence: false
platforms: []
tags: [上机前体检, 分辨率适配, 设计分辨率, 面板分辨率, fb0, 等比缩放, 重排布局, 中文字库, fzcircle, 字库档位, res 分区, 体积预算, 打包超限]
evidence:
  - cmd: python scripts/gen_preflight_doc.py --check
    expect: rc=0（本页与 preflight_spec.json 一致，且字库阈值/档位与组件对账通过）
---
# 上机前体检判据（由 preflight_spec.json 派生）

> ⚙️ **本页是派生物**：内容由 `preflight_spec.json`（唯一真源）经 `scripts/gen_preflight_doc.py` 生成，**不要手改**（改了下次生成会覆盖，门禁 `gen_preflight_doc --check` 会红）。
> 检索导引（**口语问法直达**）：上机之前要检查什么 / 接上设备先看哪些东西 / 屏幕分辨率和设计不一样怎么办 / 屏比设计大会怎样 / 屏比设计小会怎样 / 设备上中文显示不出来怎么办 / 要不要给工程放字库 / 放哪一档字库 / 打包会不会超出 res 分区 / 体积是不是太大了 → 本文。

上机前跑 `flythings_device_preflight`（launch 流程里也会自动跑一遍），三项体检：**分辨率**、**字库**、**体积**。判据如下。

## 1. 分辨率：设计 vs 面板

- **面板分辨率**（设备侧真值）：读 /dev/fb0 的**可见**分辨率：/sys/class/graphics/fb0/modes 优先，缺则退 virtual_size；双缓冲时 virtual_size 的高 = 页数 × 屏高，**不是**分辨率 —— 实现 `device_probes.panel_resolution()`。
- **设计分辨率**（工程侧真值）：**启动窗口**的宽高：src/Main.cpp 的 onStartupApp 返回 "<name>Activity" → ui/<name>.json 的 resolution（缺则退根节点 position） —— 实现 `preflight.startup_window()`。
- 设计分辨率读不到时的退路（按顺序）：ui/main.json（启动窗口名解析不到时的约定名）；.settings/*.prefs 的 resolution=（再退）
- 转屏不算不一致：设计 W×H 与面板 H×W 视为同一块屏（转屏角度由工程 EasyUI.cfg 的 rotateScreen 决定），不算不一致
- 比例"接近"的容差：相对差 ≤ **3.0%**（超过就按不同比例处理）

### 1.1 三分支（按顺序命中即停）

| id | 条件 | 动作 | 级别 | 为什么 |
|---|---|---|---|---|
| `screen_ge_design` | 面板宽、高都 ≥ 设计 | `push` | info | 屏幕大于设计分辨率时 UI 可以完整显示，不影响 |
| `screen_lt_design` | 面板任一维 < 设计 | `warn` | warn | 屏比设计小 → 超出可视区的部分在屏上看不到（画面被裁）；尺寸不符还可能表现为灰窗/黑屏或布局错位（见 knowledge/devflow/canvas-panel-coverage.md）。必须让用户先决定：按面板重做布局，还是保持设计、接受画面被裁 |
| `design_unknown` | 工程读不出启动窗口尺寸 | `adapt_device` | warn | 用户未指定设计分辨率 → 默认按设备面板分辨率重新适配 layout |

### 1.2 需要适配时怎么改

- **比例相同或接近** → `scale`（两屏宽高比相对差 ≤ aspectTolerancePct%）
  - 怎么做：口径对齐（.settings/*.prefs / ui/*.json / ftu 内嵌的 resolution 与根 position）+ 控件盒与字号按 sx/sy 换算
  - 工具：`flythings_device_preflight(adapt='auto')`
- **比例不同** → `relayout`（两屏宽高比相对差 > aspectTolerancePct%）
  - 怎么做：比例不同 → 只做等比缩放会变形，必须重排布局（区域比例重划 / 控件重排 / 必要时拆并页）。工具只出 plan，不落盘
  - 工作流（重排这类需要判断的活）：skill `flythings-resolution-adapt`
  - 工具：`flythings_device_preflight(adapt='ask'|'auto') → plan`

**三条不变式**：
- 改完必须 fui pack 出 ftu（设备加载的是 ftu，不是 json）
- 只改布局不用重编/重推 .so
- 改完跑 flythings_layout_audit 复核控件盒越界/遮挡，必要时 flythings_ui_preview 或抓屏复核

## 2. 字库：设备认不认中文

- 系统内置字库：`/etc/font/fzcircle.ttf`；**200.0 KB**。判定：内置字库 < 200KB 判定为**不支持中文**（只带拉丁字形）→ 需要往工程投递裁剪字库
- 实现：`preflight.font_verdict()`
- 档位清单与体积的真源：components/fonts/scripts/device_font_check.py::TIERS（门禁对账：档位键与文件名必须一致；档位体积按 components/fonts/fonts/ 实际文件算，不在这里抄一份）

| 档位 | 文件 | 体积 | 级别 | 什么时候用 |
|---|---|---|---|---|
| `common` | `zkswe-hans-common.ttf` | 871.9 KB | 常用中文 | 工程文案只用常用汉字（默认档） |
| `full` | `zkswe-hans-full.ttf` | 7389.9 KB | 全中文 | 工程文案含 GB2312 一级之外的生僻字 |
| `multi` | `zkswe-hans-multi.ttf` | 10490.8 KB | 多国语言 | 工程要多语言（中 + 拉丁/其他语系） |

**按工程中文级别选档**：扫工程 UI 文案（ui/*.json 的 text/caption + tr/*.json）取**用到的 CJK 字集** → 从最小档起比对各档 cmap 覆盖率 → 选「够用的最小档」；fontTools 不可用时退**编解码器分级**（编得进 GB2312 → common / 仅 GBK → full / 更外 → multi）

- 实现：`preflight.pick_font_tier()`；投递：`font_tools.font_preflight()（投递 + 改 prefs）`
- 工程 0 个 CJK 字 → 不投递（设备内置拉丁字库够用）

## 3. 体积：会不会撑爆 /res 分区

- 上限：**默认 8 MB**（`perPlatform` 可按平台覆盖）；接近阈值 = 用量的 90%。
- 计入体积的三部分：
  - `resources/` —— 工程资源（图 / 字体 / 其他随包资源）
  - `**/*.ttf|*.ttc` —— 工程内字体（resources/ 之外单独放的也算，按绝对路径去重）
  - `.fun/<平台>/libzkgui.so` —— 应用库（fun build 产物）
- **不计入**（但会在报告里附参考字节数）：`ui/*.ftu`、`tr/`、`src/（编译进 .so）`

| 级别 | 触发 | 动作 | 为什么 |
|---|---|---|---|
| `over` | used ≥ limit | `warn` | 打包文件可能大于 /res 分区大小 → 升级/固化会失败或被截断 |
| `near` | used ≥ nearPct% × limit | `info` | 已接近 /res 分区上限，再加资源要小心 |

> perPlatform 为空 = 全部平台用 limitMB；实测到某平台分区不同就在这里覆盖（键用 platforms.py 的规范名，别名由 platforms.resolve() 折算）

