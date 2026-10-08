---
id: devflow-platform-translate
title: 跨框架 / 竞品 UI 迁移口径（映射表 + 四阶段路线 + 双平台）
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [F133]
tags: [界面迁移, 竞品样式对齐, 跨框架移植, 小程序转 FlyThings, Android 控件对应, 组件库迁移, TDesign 迁移, 视觉还原, 设计稿换算 rpx, 迁移工作量评估, 分阶段迁移, 映射表, 差异降级清单 D-xx, translate, md, §1 的机读索引]
evidence: []
---
# 跨框架 / 竞品 UI 迁移口径（映射表 + 四阶段路线 + 双平台）

> 检索导引：问「竞品/别的框架界面搬过来 / 小程序·LVGL 转 FlyThings 怎么排期 / rpx 与视觉换算 / 差异降级清单 D-xx / 双分辨率同源怎么做」→ 本文（迁移方法论）；控件级对应走 `flythings_map_control`（见 `knowledge/uicontrols/control-mapping-capability.md`）。
> 口语/错说法（用户原话）：双分辨率同时出一套怎么搞 / 一套设计稿要出两种分辨率怎么办 / Android 控件在我们平台怎么对应 / 安卓·别家的控件对应我们哪个控件。
> 检索词：界面迁移 / 竞品样式对齐 / 跨框架移植 / 小程序转 FlyThings / LVGL 转 FlyThings /
> Android 控件对应 / 组件库迁移 / TDesign 迁移 / 视觉还原 / 设计稿换算 rpx / 迁移工作量评估 /
> 分阶段迁移 / 映射表 / 差异降级清单 D-xx。
> 案例：`projects/translate/tdesign-miniprogram`（TDesign 小程序组件库 → FlyThings，2026-09-17 三阶段收口；
> 口径总表 `projects/translate/<案例>/TRANSLATE.md`（案例侧口径总表），阶段 3 报告 `projects/translate/tdesign-miniprogram/STAGE3.md`）。
> 本文是**方法论 + 口径**；具体控件的逐条对应**不在这里**（见 §1 的机读索引，避免双份漂移）。
> ✅ **文末 §5 的 `flythings_translate_ui` op 已实现**（v0.27.171-open，LVGL → ui json v1，
> 识别形态/报告读法/已知限制见 `knowledge/devflow/translate-ui-lvgl.md`）。

## 1. 先查机读索引，别背散文映射表

| 要找什么 | 去哪 | 说明 |
|---|---|---|
| **控件 ↔ 控件** 对应（6 个框架） | `flythings_map_control(query, source='')` op / 仓库根 `mcp_control_map.json` | 213 条：lvgl 32 / qt 40 / android 43 / **miniprogram 39** / emwin 29 / mfc 30；每条含 `level` / `target` / **可直接粘的 `json` 片段** / `notes` / `ref` |
| 平台**真缺**的能力（要自定义控件） | `components/ui_v1/`（一个源控件一个目录）+ `components/ui_v1/gap-list.md` G-xx | 有对应控件的**不进**控件包，只作映射参考（`_mapping/`） |
| 缺口分级口径 | 五级 `L1 等价 / L2 组合 / L3 自绘 / L4 降级 / L5 不支持` | 与 `mcp_control_map.json` 的 `level` 同一套 |
| 检索口 | `knowledge/uicontrols/control-mapping-capability.md`、`knowledge/uicontrols/framework-control-mapping.md` | |

⇒ **做迁移第一步：把源界面里的控件逐个过 `flythings_map_control`**，命中 L1/L2 直接用（拿它的 `json`），
只有 L3 以上才需要出图标/组合/自定义控件。**不要**在本文里再抄一份映射表。

## 2. 视觉换算与「铁律」口径（与框架无关，先立规矩）

| 项 | 口径 | 依据 |
|---|---|---|
| **单位换算** | 小程序 `rpx × 0.5 = px`（750rpx 设计稿 → 基准 1024 宽画布） | 案例实测 |
| **字号下限** | 正文/按钮 **≥ 18px**；小控件盒（徽标/标签）因此比源稿大 | `knowledge/uicontrols/text-box-height-rule.md` |
| **颜色** | 一律 `#RRGGBB`；⚠️ `#000000` 会被转换器当「未设置」，要纯黑写 `#010101` | `knowledge/devflow/html-subset-quickref.md` |
| **圆角/药丸/描边/渐变/阴影/图标** | **一律出图**（SS 超采样），图尺寸**严格 == 控件盒** | `knowledge/uicontrols/nine-patch-rule.md`、`knowledge/devflow/ui-asset-rules.md` |
| **零自绘** | 能用平台控件 + 出图表达的就不用 painter 自绘；自绘只在平台真缺能力时（并落到 `components/ui_v1/`） | `components/ui_v1/README.md` |
| **手写入口不排他** | 缺省前端是 **HTML 原型**（线框/风格稿，客户确认载体）→ `html2json` → json；**也可按 schema 直写 json 或走块库 spec**；**json 是唯一事实源**（与入口无关），产物一律过 `ui_compile` + `check_all` → `fui pack` → ftu | 口径唯一出处 `knowledge/devflow/ui-pipeline-spec.md`（入口清单见 `knowledge/devflow/ui-entrypoints.md`） |
| **「隐藏」怎么写** | 换**同尺寸透明占位图 + 文本置空**；不用 `setVisible(true)`（动态显示不重绘），**更不用 `setInvalid(true)`（那是禁用）** | `knowledge/uicontrols/custom-view-refresh.md` |
| **高频回调** | 只刷变化的那一个控件，禁止全量刷新 | `knowledge/uicontrols/high-frequency-callback-perf.md` |

## 3. 四阶段路线（案例实际走法，可直接套用到下一个迁移任务）

按「**先立页面骨架 → 再补交互反馈 → 再补数据展示 → 最后补复杂选择器**」推进，
每阶段**独立可交付、独立可验收**（阶段之间不互相阻塞）：

| 阶段 | 内容 | 案例规模 | 验收 |
|---|---|---|---|
| **1 骨架 + 表单类** | 页面容器（单 Activity + 每页一个整屏 `window`）、导航、按钮/单元格/开关/滑块/步进/复选/单选/输入/表单 | 9 页 | 逐帧 md5 去重（每步都真生效）+ 静态全检 |
| **2 反馈类 / 弹层** | dialog / toast / loading / action-sheet（含遮罩、卡片、逐帧动画、非模态超时兜底） | 4 页 | 60 项像素/状态行断言（含新增项后 61） |
| **3 数据展示类** | badge / tag / progress（line·plump·circle）/ count-down | 4 页 | 48 项像素计数 + 文本 md5 |
| **4 复杂选择器** | tabs / picker / date-time-picker（滚轮类） | 待做 | 待定 |

案例总量（可作为工期参考量级）：**17 页 / 651 控件**（textview 403 · button 190 · window 41 ·
seekbar 7 · edittext 6 · radiogroup 3 · circlebar 1）/ **236 张图**，双平台同源。

### 每阶段的固定仪式

1. **离线先做完**：出图 → 生成 HTML → `html2json` → `patch_json` 补漏 → `fui pack` → `check_all`（0 FAIL）→ 双平台 `fsc build`。
2. **再碰设备**：部署（**`--no-reboot`**；部分板子 `adb reboot` 后会整板掉网，**因果未证** → `knowledge/devflow/device-deploy-budget.md` §5）→ 同一 boot 内一口气跑完断言。
3. **每套断言前清场**：重启应用进程（`kill -TERM` 优先，约 3s 内未退出才回退 `kill -KILL`）→ init 自动拉起
   （不是 reboot）；**输入类用例会弹系统键盘**，
   必须在套件间收键盘，否则后续导航点击全落键盘上、假 FAIL 一片（`knowledge/devflow/touch-inject-autotest.md`）。
4. **证据落盘**：`<平台>/evidence/*.png` + 每套 `*_test.log` + 静态全检 log。
5. **差异如实登记**（见 §4），不要「看起来一样」就过。

## 4. 差异与降级清单（D-xx 登记制）

迁移**必然有做不到的**（平台无渐变过渡、无动图、无 slot、无 disabled 状态位……）。
口径是：**逐条编号登记 + 写清「为什么」+ 写清「会不会影响『迁移成立』的判定」**，而不是悄悄降级：

- 编号从 **D-01** 起顺序续编（阶段新增项接着编，如阶段 3 从 **D-31** 起）；代码注释里可引用编号。
- 案例收口时共登记 20+ 条，典型几类（供同类迁移预判）：
  - **尺寸类**：字号下限导致小控件盒比源稿大（D-31）；
  - **动效类**：无过渡/插值动画（D-32）、无动图格式（D-24）、未做毫秒级渲染（D-33）；
  - **能力类**：无多 Activity 页栈（D-01）、无 disabled 状态位（D-03）、无组件 slot（D-L4）；
  - **形态简化**：角标只做右侧（D-34）、标签未做可选态/省略号（D-35）、进度未做渐变（D-36）、
    倒计时底纹简化（D-37）、启动语义改「点开始才走」（D-38）；
  - **平台限制逼出来的硬改法**：模态里画不出底色 → 卡片/药丸一律出图（D-14）；
    非模态 window 的超时不生效 → 代码计时兜底（D-21）。

> 判定原则：**外观风格一致 + 语义等价 + 可交互** 就算迁移成立；纯平台做不到的动效/形态算「已登记降级」。
> 但**性能与可交互性不算可降级项**（拖动卡顿、点不动 = 不合格）。

## 5. 双平台口径（同源、不同分辨率）

- **一源双出**：同一份生成器/HTML 产出两个平台目录（案例：`z21/` 1024×600 与 `f133/` 1280×720 等比 1.25×）。
- **图与盒 1:1 在两平台都必须成立**（不是只在主力平台对）。
- ⚠️ **Manifest 声明的平台键可能与目录名不一致**：案例 `f133/` 目录的 Manifest 声明的是 **F136**，
  用 `fsc build -p F133` 会因 base-utility 版本不匹配失败 → **先看 Manifest 再选 `-p`**。
- **只做静态全检的平台要如实标注**（案例：f133 无真机屏，只做静态全检 + 编译，几何按等比缩放）——
  **不要把「没验过」写成「已验过」**。
- 两个平台的 `mainLogic.cc` **改动必须逐字节一致**（各自手改必漂移；案例用 diff 逐行核对）。

## 6. 已知坑的高频命中（本文只给指针，正文在各专文）

| 坑 | 去哪看 |
|---|---|
| 弹层卡片内部按钮点不动（遮罩抢触摸） | `knowledge/uicontrols/touch-events.md` §6 |
| `setInvalid` 当重绘用 → 整屏点不动 | `knowledge/uicontrols/custom-view-refresh.md` |
| 拖动卡顿（回调全量刷新） | `knowledge/uicontrols/high-frequency-callback-perf.md` |
| `div.text` 上的 `data-bgpic` | `knowledge/devflow/html-subset-quickref.md` §4 |
| 抬盒高把图拉变形（圆点变竖椭圆） | `knowledge/uicontrols/text-box-height-rule.md`（静态检查 = `check_all` 第 20 项） |
| 方块底图刷平卡片下圆角 | `knowledge/uicontrols/nine-patch-rule.md` 进阶节 |
| 定时器里顺序错了会慢 N 倍 | `knowledge/devflow/activity-code-skeleton.md`（`onUI_Timer` 顺序） |
| 键盘盖住界面 → 假 FAIL | `knowledge/devflow/touch-inject-autotest.md` 键盘节 |
| 抓帧抓到上一帧 / 瞬态层被吃掉 | `knowledge/devflow/device-screenshot.md` §3.3-1 / §3.3-2 |

## 相关

- 界面产物管线口径（唯一产物规范 / 入口分级 / 三档判据 / 模块契约）→ `knowledge/devflow/ui-pipeline-spec.md`；入口登记 → `knowledge/devflow/ui-entrypoints.md`
- 控件映射机读索引与 op → `knowledge/uicontrols/control-mapping-capability.md`、`knowledge/uicontrols/framework-control-mapping.md`
- 缺口五级与自定义控件包 → `components/ui_v1/README.md`、`knowledge/devflow/gui-controls-gap.md`
- 页面架构（单 Activity + 多 window） → `knowledge/devflow/page-architecture-spec.md`
- 原型 → json 全链路 → `knowledge/devflow/ftu-json-pipeline.md`、`knowledge/devflow/html-subset-quickref.md`
- 可复用模块（随 MCP 发布） → `knowledge/devflow/reusable-components.md`
