# 页面架构规范：ftu vs 同 ftu 内多窗口 + src 业务域目录命名

> 2026-09-13 沛哥定规（确认「跨业务域/独立生命周期 → 独立 ftu；同业务域内的页签/弹窗/二级页 → 同 ftu 内整屏 window」判断正确后入库）。
> 2026-09-21 钟工修正补充：**多屏设计稿的 N 屏必须全部落地**（旧口径易被误读成「只做一个页面」），
> 并与 `ui_tools/html2json.py` 的返回字段（`screensDetected`/`pagesProduced`）对齐；
> html2json 内 FT-006 告警文案已同步改为与本文件一致（两处口径互为引用，禁止再漂移）。
> 检索词：页面架构/ftu 划分/多窗口/showWnd/整屏 window/二级页/弹窗/目录命名/业务域/src 目录/network media/.cpp .h/单 Activity/多 Activity/一个工程几个 Activity/一个工程几个 ftu/多个页面怎么放/页面放一个 ftu 还是多个。

## 0. 一句话口径

**多屏设计稿 = N 屏必须全部落地（页数 = 屏数，一屏不许丢）**；落地形态二选一：

1. **默认（同业务域）：一个工程一个 Activity —— `ui/main.ftu` + `src/activity/mainActivity.*` + `src/logic/mainLogic.cc`；
同一个业务域里的多个页面 = 同一个 ftu 内的多个整屏 window，用 `showWnd()/hideWnd()` 切换** ——
不要为每个页面新建 ftu/Activity（那样会变成多 Activity：Activity 数量、返回栈、跨页状态都要自己管）。
2. **跨业务域 / 需独立生命周期与返回栈 / 超大页面 → 每屏一个 ftu**（= 新 Activity）：转换时用
`flythings_html_to_json(split_per_page=true)`（CLI `--split-per-page`）每屏一个 json。

**屏数核对（交付前必做）**：html2json 返回体带 `screensDetected`（识别到几个 `.screen`）与
`pagesProduced`（实际产出几页），**两者必须相等且等于设计稿屏数 N**；不等一律 `success:false`，
先修 HTML 再往下走。数屏方法与逐条清单见 `devflow/prototype-flow.md`「分页落地清单（硬规则）」。

**ftu = Activity = 一个独立编译单元（IDE 按 ftu 生成 activity+logic，独立生命周期与返回栈）；window = 同一 Activity 内的显隐（零切换成本、共享控件指针与状态）。**
所以划分依据是**业务域与生命周期**，不是"页面看起来像不像一页"；也不是"为了少几个页面所以只做首页"。

## 1. 三种页面组织形态

| 形态 | 实现 | 切换成本 | 状态 | 适用 |
|------|------|----------|------|------|
| **A. 独立 ftu**（一页一 ftu） | 每个 ftu → 一套 `<page>Logic.cc` + `<page>Activity`；`openActivity("xxxActivity")` 跳转 | 高（新建 Activity / 走生命周期 / 需返回栈管理） | 各页独立，互不共享控件指针 | 跨业务域的主页面；需要独立生命周期与返回栈；大页面 |
| **B. 同 ftu 内多个整屏 window + `showWnd()/hideWnd()`** | 一个 ftu 内叠多个顶层整屏 window（`width/height ≥ resolution`），首屏 window `visible:true`、其余 `visible:false`，代码里切显隐 | 低（同一 Activity 内） | 共享同一份控件指针与状态 | **同一业务域内**：页签/设置二级页/弹窗/临时遮挡页 |
| **C. 容器内切换**（pagewindow / slidewindow / scrollwindow） | 一个容器控件内部翻页或滚动 | 最低 | 容器内子页共享 | 宫格翻页、引导页、分类内容区、内容超高的单页滚动 |

## 2. 决策清单（按顺序问）

1. **是否跨业务域？**（比如「网络配置」vs「媒体回放」）跨 → **A 独立 ftu**；不跨 → 看 2
2. **是否需要独立生命周期 / 独立返回栈 / 大页面？** 是 → **A**；否 → 看 3
3. **是否是同一页内的并列内容区（页签、宫格、列表内容区）？** 是 → **C 容器**；否（是叠加显示的弹窗/二级页/遮挡）→ 看 4
4. **需要盖住整屏 / 需要一整套独立控件组？** 是 → **B 整屏 window + showWnd**；否（小范围覆盖）→ B 的**局部 window**（非整屏）

**辅助判据**：
- 这页要不要"返回上一页"的语义？要 → 倾向 A（或 B 内自己维护返回逻辑，写清楚）。
- 这页的控件需不需要和上一页**共享状态/指针**（同一份列表数据、同一路视频、同一个定时器）？需要 → 倾向 B/C（同 Activity 才有共享指针）。
- 页内是否有**媒体/硬件资源**？资源跟随 Activity 生命周期 → 独立页用 A 更好，释放点按 `onUI_quit`（见 activity-code-skeleton.md §3-1：`goBack/返回销毁只走 onUI_quit`）。

## 3. 常见错法（反例）

| 错法 | 症状 | 正解 |
|------|------|------|
| 所有二级页/设置页都开新 ftu | Activity 数量爆炸、返回栈混乱、跨页状态要手工传递 | 同一业务域内的二级页改 **B**（同 ftu 整屏 window + showWnd） |
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
