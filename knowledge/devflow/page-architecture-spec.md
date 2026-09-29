---
id: devflow-page-architecture-spec
title: 页面架构规范：ftu vs 同 ftu 内多窗口 + src 业务域目录命名
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [确认, 跨业务域, 弹窗, 判断正确后入库, 旧口径易被误读成, 只做一个页面, html2json, pagesProduced, 对齐, 两处口径互为引用]
evidence: []
---
# 页面架构规范：ftu vs 同 ftu 内多窗口 + src 业务域目录命名

> 检索导引：问「一个工程几个 ftu/Activity / 二级页·弹窗放同一 ftu 还是新页 / merge_windows 什么时候用 / showWnd 多窗口 / src 目录与文件怎么命名 / 多屏设计稿要落地几页」→ 本文（默认一屏一 Activity 一 json）；原型分页流程见 `devflow/prototype-flow.md`。
> 2026-09-13 沛哥定规（确认「跨业务域/独立生命周期 → 独立 ftu；同一 Activity 内的页签/弹窗/二级页 → 同 ftu 内整屏 window」判断正确后入库）。
> 2026-09-21 钟工修正补充：**多屏设计稿的 N 屏必须全部落地**（旧口径易被误读成「只做一个页面」），
> 并与 `ui_tools/html2json.py` 的返回字段（`screensDetected`/`pagesProduced`）对齐；
> html2json 内 FT-006 告警文案已同步改为与本文件一致（两处口径互为引用，禁止再漂移）。
> **2026-09-21 钟工再修正（v0.27.100，本条优先）：默认口径反转** —— 钟工原话「不是的，按照客户的设计需求，
> 其实目前已经可以准确的做好了不同的 html 页面分页了。哪些属于不同的 activity 哪些属于 windows，dialog
> 其实前期 AI 可以分清楚。分清楚的情况下不同的 activity 做好不同的 json 布局就好了」。
> 即：**一个 `.screen` = 一个页面 = 一个 Activity = 一个 json/ftu 是常态（html2json 缺省，不带参数）**；
> 「同 ftu 内多个整屏 window」不再默认，只有**同属一个 Activity** 时才用 `merge_windows=true` 合成；
> 归属由 **AI 在 HTML 原型阶段逐屏判定**（不同 Activity -> 各自 json/ftu；同屏内 window/dialog -> 同一 json 内）。
> 检索词：页面架构/ftu 划分/多窗口/showWnd/整屏 window/二级页/弹窗/目录命名/业务域/src 目录/network media/.cpp .h/单 Activity/多 Activity/一个工程几个 Activity/一个工程几个 ftu/多个页面怎么放/页面放一个 ftu 还是多个。

## 0. 一句话口径

**多屏设计稿 = N 屏必须全部落地（页数 = 屏数，一屏不许丢）**；落地形态二选一：

1. **常态（钟工 2026-09-21 口径）：页面按设计稿的 Activity 归属划分 —— 一个页面 = 一个 Activity
= 一个 json/ftu**（`ui/<页>.ftu` + `src/activity/<页>Activity.*` + `src/logic/<页>Logic.cc`）；
设计稿里一个 `.screen` 就是一页，html2json **缺省**就是每屏一个 json（不用带参数）。
2. **同一个 Activity 内的页面/弹窗才放进同一个 ftu**：用该 ftu 内的 window（整屏 window 或局部 window）
+ `showWnd()/hideWnd()` 切换 —— 这类屏在 HTML 里要么写成该 `.screen` 内部的 `div.window`/`div.modal`
（弹窗/浮层），要么由 AI 判定「这几屏同属一个 Activity」后用
`flythings_html_to_json(merge_windows=true)`（CLI `--merge-windows`）合成一个 json 内的多个整屏 window。

**屏数核对（交付前必做）**：html2json 返回体带 `screensDetected`（识别到几个 `.screen`）与
`pagesProduced`（实际产出几页），**两者必须相等且等于设计稿屏数 N**；不等一律 `success:false`，
先修 HTML 再往下走。数屏方法与逐条清单见 `devflow/prototype-flow.md`「分页落地清单（硬规则）」。

**ftu = Activity = 一个独立编译单元（IDE 按 ftu 生成 activity+logic，独立生命周期与返回栈）；window = 同一 Activity 内的显隐（零切换成本、共享控件指针与状态）。**
所以划分依据是**设计稿的 Activity 归属（业务域 + 生命周期）**，不是"页面看起来像不像一页"；
也不是"为了少几个页面所以只做首页"，**更不是"默认所有页面都塞进一个 ftu"**——
按设计稿一页一个 Activity/一个 ftu 是常态，只有**确实同属一个 Activity** 的那些屏才共用 ftu 内的 window。

**AI 前期就把归属分清楚**（钟工口径：不同 activity / 同屏内 window、dialog，前期 AI 可以分清楚）：
第 ③ 步 HTML 原型阶段就为每屏标注归属，转换时只按页输出对应 json —— 工具侧不替 AI 做这个判定。

## 1. 三种页面组织形态

| 形态 | 实现 | 切换成本 | 状态 | 适用 |
|------|------|----------|------|------|
| **A. 独立 ftu**（一页一 ftu） | 每个 ftu → 一套 `<page>Logic.cc` + `<page>Activity`；`openActivity("xxxActivity")` 跳转 | 高（新建 Activity / 走生命周期 / 需返回栈管理） | 各页独立，互不共享控件指针 | 跨业务域的主页面；需要独立生命周期与返回栈；大页面 |
| **B. 同 ftu 内多个整屏 window + `showWnd()/hideWnd()`** | 一个 ftu 内叠多个顶层整屏 window（`width/height ≥ resolution`），首屏 window `visible:true`、其余 `visible:false`，代码里切显隐 | 低（同一 Activity 内） | 共享同一份控件指针与状态 | **同一 Activity 内**：页签/设置二级页/弹窗/临时遮挡页（**前提是先按 §2 第 0 步判定为同一个 Activity**，否则回 A） |
| **C. 容器内切换**（pagewindow / slidewindow / scrollwindow） | 一个容器控件内部翻页或滚动 | 最低 | 容器内子页共享 | 宫格翻页、引导页、分类内容区、内容超高的单页滚动 |

## 2. 决策清单（按顺序问；**默认答案 = 一页一个 Activity/一个 json/ftu**，只有答"是"才合并）

0. **先按设计稿分 Activity 归属**（第 ③ 步 HTML 原型阶段就定）：设计稿里每一屏（每个 `.screen`）先问
   "它是独立的一个 Activity，还是别的页里的弹窗/浮层？" —— 独立 -> 各自 json/ftu（缺省）；弹窗/浮层 ->
   写在该屏内部（`div.window`/`div.modal`）。**这一判定由 AI 前期做，工具只按页输出 json。**
   只有同属一个 Activity 的一批整屏窗口，才在本清单里问"能不能合并"。


1. **是否跨业务域？**（比如「网络配置」vs「媒体回放」）跨 → **A 独立 ftu**；不跨 → 看 2
2. **是否需要独立生命周期 / 独立返回栈 / 大页面？** 是 → **A**；否 → 看 3
   （**A 是缺省**：判不准就各自一个 ftu，不要默认合并 —— 合并的代价是一个域崩了整 Activity 一起塌）
3. **是否是同一页内的并列内容区（页签、宫格、列表内容区）？** 是 → **C 容器**；否（是叠加显示的弹窗/二级页/遮挡）→ 看 4
4. **（同一 Activity 内）需要盖住整屏 / 需要一整套独立控件组？** 是 → **B 整屏 window + showWnd**；否（小范围覆盖）→ B 的**局部 window**（非整屏）
   - 第 0 步判定为**不同 Activity** 的屏，**不许**走 B —— 各自 A（一个 json/ftu）。

**辅助判据**：
- 这页要不要"返回上一页"的语义？要 → 倾向 A（或 B 内自己维护返回逻辑，写清楚）。
- 这页的控件需不需要和上一页**共享状态/指针**（同一份列表数据、同一路视频、同一个定时器）？需要 → 倾向 B/C（同 Activity 才有共享指针）。
- 页内是否有**媒体/硬件资源**？资源跟随 Activity 生命周期 → 独立页用 A 更好，释放点按 `onUI_quit`（见 activity-code-skeleton.md §3-1：`goBack/返回销毁只走 onUI_quit`）。

## 3. 常见错法（反例）

| 错法 | 症状 | 正解 |
|------|------|------|
| 把**不同设计页**全都塞进一个 ftu 的多个 window（默认合并） | 与设计稿的 Activity 划分不一致；单文件巨大、logic 混杂 | 回到缺省 **A**（每屏一个 json/ftu，html2json 不带参数）；只有**同属一个 Activity** 的屏才用 **B**（`merge_windows=true` + showWnd） |
| 需要共享控件指针/状态的**同一 Activity**内的多屏硬拆成多个 ftu | 跨页状态要手工传递、返回栈混乱 | 那几屏用 **B**（同 ftu 整屏 window + showWnd；HTML 侧传 `merge_windows=true` 合成一个 json） |
| 把不同业务域硬塞进一个 ftu 的多个 window | 单文件巨大、logic 混杂无关逻辑、一个域崩了整 Activity 一起塌 | 拆 **A**（独立 ftu） |
| 用 window 显隐当"页面跳转"但不管理 `visible` 初值 | 首次进页面所有 window 都不显示（或多页叠着显示） | 首屏 window `visible:true`、其余 `visible:false`；切换只走 `showWnd/hideWnd` |
| 叠在整屏 window 之上的**装饰件**没设穿透 | 下层列表能看不能拖 / 点行没反应（`touchable=false` 不等于穿透） | `pCtrl->setTouchable(false); pCtrl->setTouchPass(true);`（见 touch-events.md） |
| 多整屏 window 工程预览/交付只见首页 | 客户只看到首屏 | 预览稿用**页面切换条** / `xxx.preview.html#window__N` 直达（ui-layout-verify.md §2-2） |
| **多屏设计稿只落地第一屏**（其余屏静默丢掉） | 客户要的 N 页只出来一页（html2json 旧版只取第一个 `.screen` 的行为） | 转换后核 **`screensDetected` == `pagesProduced` == N**；不等看返回值里的 error/failed 先修 HTML（见 prototype-flow.md「分页落地清单」） |
| 把多屏 HTML 里非首屏的 `.screen` 改成嵌套/删掉 | 屏数悄悄少了，交付缺页 | `.screen` 必须**并列**（嵌套 = 转换报错）；改设计稿就重走一遍屏数核对 |

## 4. src 目录与文件命名规范

**目录按业务域直接建在 `src/` 下，不设 `core/`、`modules/` 这类中间分层目录。**

```
src/
├── activity/        # IDE 生成（mainActivity.cpp/.h），禁止创建/修改/覆盖
├── logic/           # IDE 按 ftu 生成 <page>Logic.cc，只做 UI↔业务关联
├── uart/            # 系统模板（勿改 UartContext/ProtocolSender）
├── network/         # ★ 业务域：配网/WiFi/BLE/MQTT/HTTP 等
│   ├── NetworkManager.cpp / .h
│   ├── WifiService.cpp / .h
│   └── MqttClient.cpp / .h
├── media/           # ★ 业务域：视频/音频/录像/拍照
│   ├── MediaPlayer.cpp / .h
│   └── RecordService.cpp / .h
└── storage/         # ★ 业务域：配置持久化/文件/TF 卡
    └── ConfigStore.cpp / .h
```

规则：

1. **一级子目录 = 业务域**（network / media / storage / ui-config …），域名用**小写英文单数名词**，不用 `core`、`common`、`misc`、`utils` 这类无域含义的名字（真有两个域共用的东西，才另起 `common/`，并写明归属）。
2. **不在 `src/` 下先分 `core/`/`modules/` 再分业务域**（两层壳只会让 include 路径变长、归属变模糊）。
3. **文件 = 业务域内的一个职责类**：`<职责>.cpp` + `<职责>.h` 成对；类名用大驼峰，与文件名一致（`NetworkManager` ↔ `NetworkManager.cpp/.h`）。
4. **一律 `.cpp`/`.h`**：新增业务代码禁止建 `.cc`（`.cc` 是 IDE 按页面生成的 logic 专属）。**两套编译体系别混**：IDE 里 `.cc` 靠 `mainActivity.cpp` `#include` 进编译单元（Makefile 只编 `%.cpp %.c`）；**`fun build` 里 `src/activity/*` 不参与编译，`src/logic/*.cc` 直接被编译，业务 `src/**/*.cpp` 被扫描收进编译单元** —— **不要改 `.fun/<平台>/CMakeLists.txt`**（fun 自动生成、会覆盖）。详见 `cli-fun-toolchain.md` §4.5。
5. **`src/logic/*.cc` 只做关联层**：取控件指针 / `setText` / 调业务对象；复杂逻辑放业务域目录里的类，logic 只 include + 调用。
6. **include 路径**：业务模块头文件用相对 `src/` 的路径（如 `#include "network/NetworkManager.h"`），不要写绝对路径。
7. **资源与代码分开**：图片等资源仍放 `resources/`（自动生成图放 `resources/images/`，json 引用写 `images/xxx.png`），业务域目录只放代码。

## 5. 自检清单

- [ ] **屏数核对**：设计稿 N 屏 <-> 产出 N 页（html2json 的 `screensDetected` == `pagesProduced` == N）；
      同 ftu 形态数整屏 window 个数，独立 ftu 形态数 json/ftu 个数（见 prototype-flow.md「分页落地清单」）
- [ ] 每个 ftu 对应一个**业务域内**的完整页面单元，页面名与 logic 名同前缀（`main.ftu` ↔ `mainLogic.cc`）
- [ ] 跨业务域/需独立返回栈的页面是独立 ftu；同域内的页签/二级页/弹窗是同 ftu 内的 window
- [ ] 同 ftu 多整屏 window 工程：首屏 `visible:true`、其余 `visible:false`，切换只走 `showWnd/hideWnd`
- [ ] 整屏 window 之上的装饰件已 `setTouchable(false)+setTouchPass(true)`
- [ ] `src/` 下目录全部是业务域名，没有 `core/`、`modules/` 中间层
- [ ] 新增业务代码全是 `.cpp`/`.h`，没有新建 `.cc`
- [ ] logic 里只有关联操作，复杂逻辑在业务域目录的类里
- [ ] 交付预览稿能切到每一页（多整屏 window 用页面切换条 / `#window__N`）

## 6. 相关文档

- **系统级窗口**（状态栏/导航栏/屏保/输入法：固定文件名、APP_TYPE、REGISTER_SYSAPP、API、层级与生命周期）→ uicontrols/system-windows.md
- **工程自定义系统窗口 / 全局弹框**（floatwnd / popupWnd / 蓝牙来电 btcall 弹框：自定义 appType + SYSAPPFACTORY + show/hide 封装）→ uicontrols/global-popup-window.md
