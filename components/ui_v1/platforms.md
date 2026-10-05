# platforms.md — ui_v1 基线平台口径（分辨率 / rotate / easyui 版本 / 设备限制）

> 本文件是 `components/ui_v1/*` 各表的**平台前置条件**：哪些平台可用、每平台分辨率与旋转怎么配、
> easyui 版本差异导致哪些控件/API 不可用、真机硬限制（内存/双缓冲/共用设备）。
> 未实测项一律标 **未验证**，禁止写"应该可以"。
> 建立：2026-09-16（v0.27.71-open）｜数据源：两个转换案例真机实测 + `knowledge/devflow/*` 已入库结论。

---

## 0. 速查表

| 平台 | 面板 fb | UI resolution（json 写的） | EasyUI.cfg 旋转 | 部署路径 | 编译命令 | 内存/能力 |
|---|---|---|---|---|---|---|
| **Z21**| 1024×600 横 | **1024×600**| `rotateScreen/rotateTouch = 0/0` | `fun launch` → `/tmp/{lib,ui,font}` + `EasyUI.cfg` | `fun build -p Z21` | 36MB RAM，无 GPU / 无硬解 |
| **F133**| 800×1280 竖 fb | **1280×800**| `{"rotateScreen":270,"rotateTouch":270}`（写进 `package.properties`） | SD：`/mnt/extsd/{lib,ui}` + 手写 `EasyUI.cfg` | **`fun build -p F136`**（Manifest `platform="F136"`） | 无 GPU / 无硬解 |
| **Z20**| 800×1280 | 按工程 | 按工程 | 按工程 | `fun build -p Z20` | 视频走 MI 硬件图层（抓 fb0 是黑的） |
| **T113 / T113EMMC**| 按工程 | 按工程 | 按工程 | 按工程 | `fun build -p T113` | easyui 2.6.0（无 `relayout`） |
| **V85X（V851/V853/SPINOR/EMMC）**| 800×480 或 1600×600 | 按工程 | 按工程 | `update.img` / `/res` | `fun build -p v85x` | **有 disp 分层**（真 3D/图层合成仅此平台验证过） |

> ⚠️ **F133 专项**：工具链**不接受 `F135`**，Manifest 必须写 `platform="F136"`；
> 用 `fun build -p F133` 在本地注册表缺 easyui 包时会因 include 路径缺失而**编译失败**（案例 README §4）。
>
> ⚠️ **F133/横屏 fb**：面板 fb 是 800×1280 竖屏，UI 是 1280×800 横屏 → `EasyUI.cfg` **必须手写 rotate**，
> 否则画面/触摸方向错（案例已固化口径）。

---

## 1. 分辨率与多分辨率策略

| 项 | 口径 |
|---|---|
| 单一分辨率工程 | 一套 `ui/*.json` + 一套绝对坐标（平台无 `dp`/`LV_DPX` 自适应，见 `gap-list.md` G-08） |
| 第二套分辨率 | 等比缩放生成（案例做法：Z21 1024×600 → F133 ×1.25 = 1280×800；**缺省前端是 HTML 原型**（手写入口不排他，见 `knowledge/devflow/ui-pipeline-spec.md`），其余分辨率由脚本生成） |
| 分层多分辨率工程 | `ui/<分辨率>/*.json`（MCP 的 `check_all` / `verify_assets` / `json2html` 已支持分层扫描） |
| 运行时换布局 | `relayout()`，需 easyui ≥ 2.9.0 且**同一控件 ID 一一对应**（见 §2） |

---

## 2. easyui 版本与控件可用性差异（★ 写进表，别按"文档有就能用"写）

| 能力 / 控件 | 版本要求 | Z21 | F133 | Z20 | T113 | V85X | 结论 |
|---|---|---|---|---|---|---|---|
| `Activity::relayout()`（运行时换布局） | **easyui ≥ 2.9.0**| ❌(2.6.0) | ❌(2.8.0)/✅(2.9.0) | ✅(3.0.0) | ❌(2.6.0) | ✅(2.9.0) | 现有公开包 z20/z21/t113 均无 → 要就得**找 FlyThings 厂家支持**（`devflow/dynamic-screen-rotation.md`） |
| `setScreenRotate()/setTouchRotate()`（运行时转屏） | 老版本即有 | ✅ | ✅ | ✅ | ✅ | ✅ | 与 `relayout` 分开看，**只有 relayout 是新的**|
| `ZKBase::getAbsolutePosition()` | **设备侧 `libeasyui.so` 可能比本地包旧**| ❌实测无 | 未验证 | 未验证 | 未验证 | 未验证 | 用它 → `dlopen` undefined symbol → **整屏黑**；一律用 `getPosition()`（`gap-list.md` T3） |
| `ZKImageAnim`（GIF/WebP 动图） | 平台支持列表 | ✅ | **❌ 不支持**| ✅ | ✅ | ✅ | 跨平台工程**别默认用动图**（`uicontrols/imageanim-fields.md`） |
| `checkbox__`（`ZKCheckBox`） | **`fun` 生成器**侧限制（非 easyui 版本） | ❌ | ❌ | ❌ | ❌ | ❌ | 全平台一律两态按钮绕过（`gap-list.md` G-18） |
| `ZKPageWindow`（tab 容器，★本轮修正选型） | 公开包内即有 | ✅ | ✅ | ✅ | ✅ | ✅ | 实测见 `uicontrols/pagewindow-fields.md`；`dragMaxDis`=**行程**（200） |
| `ZKPainter`（自绘） | 公开包内即有 | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ `drawArc` 实参口径存疑（T11）；`fillRect/erase` 实测可用（Z21） |
| 富媒体/视频层（disp 合成） | 平台级 | ❌(软解) | ❌ | 硬件图层（MI） | — | ✅ disp 分层 | 见 `knowledge/v85x/display-layer-debug.md` |

> **版本取值口径**：上表版本号来自本地依赖包注册表与真机 `libeasyui.so` 实测；
> **设备侧库可能比本地包旧**（Z21 实机 2024-07-10 版）→ 新 API 一律**先上机验符号**再用。

---

## 3. 平台硬限制（决定能做/不能做）

### 3.1 图形能力
- **Z21 / F133：无 GPU、无硬解**→ **任何 3D 一律伪 3D/2.5D**（预渲染贴图 + 烘焙阴影 + 序列帧）；
真 3D 只在 **V85X（disp 分层）**验证过。见 `gap-list.md` §3。
- 无 CSS 引擎 / 无 flex-grid / 无 theme 引擎 → 样式靠**转图**（圆角/阴影/渐变自动转 PNG）、布局靠**绝对坐标**。

### 3.2 内存与存储（小内存设备铁律）
- Z21 实测：`Mem total 36072 kB`（**36MB**）、`/tmp` = **tmpfs 13.6MB**（**tmpfs 吃的是 RAM**）。
- `fun launch` 一次至少推 `libzkgui.so` + 字库 + `*.ftu` + `EasyUI.cfg` 到 `/tmp` → 字库是大头
  （常用字 872KB / 全量 7.5MB / 多语言 10.7MB）→ 撑爆即 **OOM 杀 `zkgui` → 设备重启**（现象像"WiFi 坏了"）。
- 处置：字库按工程用字裁剪（`tools/ui_tools/font_subset_by_project.py`，872KB → 数十 KB）；清了垃圾后 `available` 应回到 10MB+。
- 设备**重启清空 `/tmp`**（含 `EasyUI.cfg`）→ 必须整套 `fun launch`；只 push 单文件会跑出厂 UI。

### 3.3 抓屏（验收侧）
- Z21 fb **双缓冲**：`virtualHeight = 2 × height`（1024×1200），`pan` 在 `0,0`/`0,600` 间跳 →
容易抓到**上一帧**（"点了没反应"的假象）。判据与处置见 `devflow/device-screenshot.md` + `gap-list.md` T12。
- 抓屏方向按**项目工程**的 `rotateScreen` 自动取图（`flythings_device_screenshot` 默认 `rotate=auto`），不猜。

### 3.4 设备是共用资源
- Z21 是**共用真机**：`/tmp/ui` 可能被其它会话覆盖（实测两次抓图间 ftu 从 2221B 变 5355B = 别的工程）。
- 重启后**首次触摸注入常被吞**→ 验收脚本先热身点击（`gap-list.md` T9/T10）。
- 验收要在**一条命令内**做完：部署 → 资源路径修复 → 重启 → 注入 → 抓图。

---

## 4. 每平台的"能用/别用"结论（做工程前先看这一节）

| 平台 | 能用 | 别用 / 特殊处理 |
|---|---|---|
| **Z21**| pagewindow / listview / seekbar / edittext / radiogroup / window(modal) / painter / circlebar / pointer / diagram / qrcode / digitalclock / imageanim / videoview / cameraview / slidetext | ✗ `relayout()`；✗ `getAbsolutePosition()`；✗ checkbox（生成器）；✗ 真 3D；字库必须裁剪；图片推法有坑（T2） |
| **F133**| 同 Z21（除动图） | ✗ `ZKImageAnim`；编译必须 `-p F136`；`EasyUI.cfg` 必须带 rotate 270；部署走 SD `/mnt/extsd/{lib,ui}`；✗ 真 3D |
| **Z20**| 全控件 + `relayout`（3.0.0） | 视频是 MI 硬件图层（fb0 抓不到视频，用 `zkshot`） |
| **T113**| 同 Z21 | ✗ `relayout()`（2.6.0） |
| **V85X**| 全控件 + disp 分层（真 3D/图层合成） | ⚠️ 视频解码返回后**必须 releaseLayer**否则黑屏（`knowledge/v85x/display-layer-debug.md`）；触摸协议两块屏两种（MT-A/MT-B） |

---

## 5. 未验证 / 待确认

| 项 | 状态 |
|---|---|
| F133 真机部署与交互验收 | **未验证**（设备不在 adb 列表）——两案例均只出编译产物 |
| F133 easyui 精确版本对 `relayout` 的有无（2.8.0 无 / 2.9.0 有） | 已记录两说，**以工程实际包版本为准**，用前先验 |
| Z20/T113/V85X 的 `pagewindow` 真机实测 | **未验证**（本轮只有 Z21 实测） |
| 设备侧 `libeasyui.so` 的 `getAbsolutePosition()`（Z21 以外平台） | 未验证（Z21 已确认**无**） |
| `drawArc` 实参口径 | 待官方/需求方确认（两份记录冲突） |

---

## 6. 相关文件

- 控件映射（★ 权威）：`control-map.md`　·　逻辑映射：`logic-map.md`　·　缺口/坑/3D：`gap-list.md`
- 部署体积预算：`knowledge/devflow/device-deploy-budget.md`
- 抓屏与双缓冲：`knowledge/devflow/device-screenshot.md`
- 运行时旋转：`knowledge/devflow/dynamic-screen-rotation.md`　·　`EasyUI.cfg`：`knowledge/devflow/package-properties-easyui-cfg.md`
