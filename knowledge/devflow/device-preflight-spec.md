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

> ⚙️ **本页是派生物，不要手改**（由 `preflight_spec.json` 派生，`--check` 进闸门）。
> 口语问法直达：上机之前要检查什么 / 接上设备先看哪些东西 / 屏幕分辨率和设计不一样怎么办 / 屏比设计大会怎样 / 屏比设计小会怎样 / 设备上中文显示不出来怎么办 / 要不要给工程放字库 / 放哪一档字库 / 打包会不会超出 res 分区 / 体积是不是太大了。

上机前跑 `flythings_device_preflight`（launch 流程里自动跑同一套）：**分辨率 / 字库 / 体积**三项判据如下。

## 1. 分辨率：设计 vs 面板

- **面板分辨率** = 读 /dev/fb0 的**可见**分辨率：/sys/class/graphics/fb0/modes 优先，缺则退 virtual_size；双缓冲时 virtual_size 的高 = 页数 × 屏高，**不是**分辨率
- **设计分辨率** = **启动窗口**的宽高：src/Main.cpp 的 onStartupApp 返回 "<name>Activity" → ui/<name>.json 的 resolution（缺则退根节点 position）
  - 设计分辨率读不到时按序退：ui/main.json（启动窗口名解析不到时的约定名）；.settings/*.prefs 的 resolution=（再退）
- 设计 W×H 与面板 H×W 视为同一块屏（转屏角度由工程 EasyUI.cfg 的 rotateScreen 决定），不算不一致
- 比例"接近"的容差：相对差 ≤ **3.0%**，超过就按不同比例处理

### 1.1 三分支（按顺序命中即停）

| 条件 | 动作 | 为什么 / 该做什么 |
|---|---|---|
| 面板宽、高都 ≥ 设计 | `push` | 屏幕大于设计分辨率时 UI 可以完整显示，不影响 |
| 面板任一维 < 设计 | `warn` | 屏比设计小 → 超出可视区的部分在屏上看不到（画面被裁）；尺寸不符还可能表现为灰窗/黑屏或布局错位（见 knowledge/devflow/canvas-panel-coverage.md）。必须让用户先决定：按面板重做布局，还是保持设计、接受画面被裁 |
| 工程读不出启动窗口尺寸 | `adapt_device` | 用户未指定设计分辨率 → 默认按设备面板分辨率重新适配 layout |

### 1.2 要适配时改到什么程度

| 两屏宽高比 | 动作 | 怎么做 | 怎么触发 |
|---|---|---|---|
| 相同或接近 | `scale` | 口径对齐（.settings/*.prefs / ui/*.json / ftu 内嵌的 resolution 与根 position）+ 控件盒与字号按 sx/sy 换算 | 用户确认后 `flythings_device_preflight(adapt='force')` 一把落盘 |
| 不同 | `relayout` | 比例不同 → 只做等比缩放会变形，必须重排布局（区域比例重划 / 控件重排 / 必要时拆并页）。工具只出 plan，不落盘 | `flythings_device_preflight(adapt='force')` 也只出 plan（不改盘） |

**三条不变式**：改完必须 fui pack 出 ftu（设备加载的是 ftu，不是 json）；只改布局不用重编/重推 .so；改完跑 flythings_layout_audit 复核控件盒越界/遮挡，必要时 flythings_ui_preview 或抓屏复核。

## 2. 字库：设备认不认中文

- 判据（设备内置字库 `/etc/font/fzcircle.ttf`）：内置字库 < 200KB 判定为**不支持中文**（只带拉丁字形）→ 需要往工程投递裁剪字库

| 档位 | 文件 | 体积 | 什么时候用 |
|---|---|---|---|
| `common` | `zkswe-hans-common.ttf` | 871.9 KB | 工程文案只用常用汉字（默认档） |
| `full` | `zkswe-hans-full.ttf` | 7389.9 KB | 工程文案含 GB2312 一级之外的生僻字 |
| `multi` | `zkswe-hans-multi.ttf` | 10490.8 KB | 工程要多语言（中 + 拉丁/其他语系） |

**按工程实际用到的汉字选最小够用档**：扫工程 UI 文案（ui/*.json 的 text/caption + tr/*.json）取**用到的 CJK 字集** → 从最小档起比对各档 cmap 覆盖率 → 选「够用的最小档」；fontTools 不可用时退**编解码器分级**（编得进 GB2312 → common / 仅 GBK → full / 更外 → multi）

- 工程 0 个 CJK 字 → 不投递（设备内置拉丁字库够用）
- 投递：`flythings_device_preflight(font_apply=True)` 自动投最小够用档；要指定档位传 `font_tier=`

## 3. 体积：会不会撑爆 /res 分区

- 上限 **8 MB**（可按平台覆盖）；用到 90% 起提示、超了告警。
- 计入：`resources/`、`**/*.ttf|*.ttc`、`.fsc|.fun/<平台>/libzkgui.so`。
- 不计入（报告里另附参考字节数）：`ui/*.ftu`、`tr/`、`src/（编译进 .so）`。

| 级别 | 触发 | 为什么 |
|---|---|---|
| `over` | used ≥ limit | 打包文件可能大于 /res 分区大小 → 升级/固化会失败或被截断 |
| `near` | used ≥ nearPct% × limit | 已接近 /res 分区上限，再加资源要小心 |

