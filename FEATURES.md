# FlyThings MCP — 功能与细节

> 主 [README.md](README.md) 只讲**安装与使用**；本文件是**细节层**：平台定位、各能力面、
> 工具面模式、编译前置条件。AI 在会话里也能直接检索到这些内容（知识库 + `flythings://` 资源），
> 所以这里不重复安装步骤。

---

## 🧭 平台定位（先读这一条，再判能力）

- **FlyThings OS = 基于 Linux 的操作系统**（内核 + 自研系统框架 + 自研 GUI 交互系统）——不是单片机/RTOS/ESP32 式板级 SDK，
  也不是"一个挂在裸机上的 GUI 库"；**判平台能力的基础架构向 Linux buildroot / OpenWrt 看齐**（应用就是普通 Linux 进程，由 init 托管：`/etc/init.rc: service zkswe /bin/zkgui`）。
- **GUI 库是自研 EasyUI**（产品名 **FlyThings UI**，设备侧产物 `zkgui` / `libzkgui.so`），与 **LVGL 是对标竞争的两套独立 GUI 库**（❌ 不是"FlyThings 用的是 LVGL"）。
- 「**不能直接套 SDK 固件**」的正解 = 要走 **FlyThings 应用形态**（app 工程 → `fun`/`fui` → `libzkgui.so` + `ui/*.ftu`），**不是**"它不在 Linux 上"。
- 长文与证据链（**第一权威**）：`knowledge/devflow/flythings-os-positioning.md`；`flythings_get_version` 返回体的 `positioning` 字段、`flythings://tools` 与 `flythings://version` 资源也带同一口径。

## 🎨 UI 布局（json 与 ftu）

- **布局以 `ui/*.json` 为源**，`fui pack` 生成设备实际加载的 `ui/*.ftu` —— **ftu 是编译产物，不要手写/手改**（口径见 `knowledge/devflow/ftu-json-pipeline.md`）
- HTML 原型 → json 布局（`flythings_html_to_json`）；json → 可确认的 HTML 预览稿（`flythings_ui_preview`，多整屏 window 工程带页面切换条）
- 布局解析（`flythings_read_json`）、字段口径（`knowledge/uicontrols/`）
- **可视化编辑**：可拖拽/缩放的编辑器 → 变更写回 json 并 pack（`flythings_ui_visual(action="editor"|"edit_apply")`）
- **跨框架控件映射**：LVGL / Qt / Android / 小程序 / emWin / MFC 控件 → FlyThings 等价控件 + 可直接粘的 json 片段（`flythings_map_control`）
- **LVGL 界面迁移翻译**：LVGL v8/v9 C 源码 → FlyThings ui json + D-xx 降级登记表（`flythings_translate_ui`，映射与上条同一张表；口径见 `knowledge/devflow/translate-ui-lvgl.md`）
- **图片资源**：AI / emoji / 线条三级降级生成（`flythings_generate_ui_assets`）；尺寸与控件盒核对（`flythings_verify_assets`）
- **界面块库（组装器）**：`templates/ui_blocks/` 的块定义 + 示例随包明文（`blocks/`、`examples/`、`README.md`）；
  组装器本身在工具箱里跑：`zkuitool compose <spec.json> --project <工程根>`（`--render` / `--check` 同源码版），
  块定义目录可用环境变量 `ZKUITOOL_BLOCKS` 指向你工程里那份

## 🔍 预览与像素验收

- 浏览器预览稿（含 `#window__N` 直达、显示隐藏幽灵框）
- **真机抓屏** `flythings_device_screenshot`：PNG/JPG/BMP、缩放省 token、方向/裁剪自动适配工程配置、支持视频层抓帧
- **像素 diff**（`flythings_ui_visual(action="diff")`，±2 容差）→ 0 token 回归验收

## 🏭 编译 / 部署 / 出包

- `flythings_build_ui_flow`：json/ftu 时间戳检查 → fui pack → fun install → fun build → **设备探测 + fun launch 推送运行**
  > ⚠️ **默认会推设备**（`with_launch` 缺省 True）：build 后自动探测 `adb devices -l` ——
  > 0 台 → `needDeviceInput=true` + `installHint`（要不要装 **ADB 驱动** / 开 USB 调试并授权 / 改用 `device='<IP>:5555'` 网络接入）；
  > 多台 → 列出 serial+model+平台匹配情况，**不替你猜**，要求显式 `device=`；
  > 恰好 1 台且平台匹配 → 自动 `fun launch -s <serial>`。
  > **不想推设备（只编译）就显式传 `with_launch=False`。**
- **PC 端 adb 随包**：`tools/adb/adb.exe`（+ 两个 DLL），客户不必另装 Android SDK；全仓 adb 走单一入口 `adb_tools.resolve_adb()`
  （环境变量 `ADB`/`FLYTHINGS_ADB` → 随包 → PATH）；设备型号→平台对照见 `device_models.json`
- **字体自动体检 + 缺中文自动投递**（`flythings_build_ui_flow` **默认就做**）：有设备就扫设备字体，没设备退化为工程侧自检；
  判定**缺中文**就把 **`common` 档思源黑体**（872 KB）投进工程 `font/`（**在 build 之前**）；
  **要生僻字换 `font_tier='full'`、多语言/日韩换 `'multi'`**，`font_check='off'` 可关；
  只要结论不想动工程 → `flythings_check_project_deps`
- **字体判定用 cmap 硬判据**：挑设备最大字体拉回本机读 cmap，以 **GB2312 一级 3755 字**算覆盖率 ——
  **≥90% `ok` / 50–90% `low`（投）/ <50% `missing`（投）**；超 12 MB 或 fontTools 不可用 → 退回体积判据
- `flythings_pack_upgrade`：固化升级包 `update.img`（TF 卡 / ADB setprop / zkautoupgrade / HTTP OTA 四种刷法）
- **换开机 logo**：`boot_logo.JPG` → **MISC 分区**（体积必须 ≤ MISC 分区大小，先量 `cat /proc/mtd`）→
  `python tools/make_boot_logo.py --size 1024x600 --out boot_logo.JPG` / `python tools/set_boot_logo.py --image boot_logo.JPG --device <serial|IP:5555>`（**默认 dry-run**）
- `flythings_create_project`：从内置模板建工程（F133/F135/Z21/Z20/T113/V85X/Z235X）
  - **ftu 能反解析回 json**：随包 `toolchain/fui.exe` 支持 `unpack`，新增 `flythings_fui_unpack`（**默认覆盖**同目录同名 json）
  - **V85x 芯片名也能直接当平台入参**（`V851 / V851S / V851S3 / V853 / V853S / V553 / V552`）一律 resolve 成 **V85X**，包键走 `v85x`（SPINOR）/ `v85xemmc`（EMMC）
- `flythings_attach_cli_tools`：把 `fui.exe`/`fun.exe` 复制进项目，客户不用装 IDE 也能编译部署
- `flythings_validate_project`：工程规范全检（依赖 / 框架约定 / 时间戳防呆）
- **工具链安装（Z235X）**：放到 **`<fun 安装目录>/toolchains/z235x/`**（目录名 = 平台小写键）；工具链**不随本包分发**

### 编译/部署前置条件（要编译才需要，只做布局可跳过）

- 本仓自带 `toolchain/fun.exe`（依赖/编译/推送/出包）与 `toolchain/fui.exe`（json↔ftu），克隆下来即可用
- 报「**缺少 fun / fui**」时按此查：① 用仓库路径跑 `mcp_server.py`（**不要 `pip install`**，wheel 不含
  `toolchain/`、`templates/`、`knowledge/`、`models/` 等数据文件）；② `fun.exe` 与 `fui.exe` **两个都要在**；
  ③ 想放到别处设 `FLYTHINGS_FUN_DIR=<含这两个 exe 的目录>`；④ 各平台**编译器工具链不随包分发**，
  解到 `<本目录>/toolchain/toolchains/<平台小写键>/`（缺了 `fun build` 会报 `platform toolchain url must not be empty`）

## 🧪 整机自检与缺陷单

- **整机快照** `flythings_selfcheck`：**11 个分区**（设备信息 / 应用状态 / 显示 / 存储 / 网络 / 蓝牙 / 输入 / 外设 / 时间 / 库清单 / 部署一致性），
  每区给 `{ok, hint, data}` —— **「读不到」本身是结论**，绝不静默吞掉；`diff_against=<上次快照.json>` 可逐分区比对
- **缺陷单** `flythings_bugreport`：把缺陷清单 + 真机判据落成可提交 markdown（现象 / 复现步骤 / 期望 vs 实际 / 真机判据 / 证据 / 影响面），
  自动附型号·固件·应用状态·最近 `logcat -d -s zkgui` 摘要；**证据文件不存在会直接报 EVIDENCE_MISSING**

## 📦 依赖包与 Manifest

- 包检索 / 版本 / 头文件级 API（`flythings_search_package` / `flythings_query_package` / `flythings_get_package_api`）
- Manifest 生成（`flythings_manifest`，默认 dry_run 只推荐）→ 加包 `flythings_add_package` → 递归解析 `flythings_resolve_dependencies` → include 对账 `flythings_check_project_deps`

## 🧠 知识库与硬件

- **全离线检索**（本地 bge-small-zh 向量 + BM25 双路 RRF，返回体带 `quality`/`source`，模型不可用自动降级），无需任何 API Key
- 硬件型号库（`flythings_hardware_info`）：分辨率/方向、按键值、接口规格；未收录只给候选不猜规格
- 版本/工具数查询（`flythings_get_version`）

## 🌐 i18n 与自动化测试

- 多语言：`scan` / `add_language` / `export` / `import` / `refactor` / `to_json`
- 自动化测试：`flythings_gen_ui_test`（traverse / monkey / custom，真机触摸注入）

## 🧩 可复用组件（`components/`，随本 MCP 一起发布）

- `ble/`（BLE 门面 `zk::ble`）、`fonts/`（思源黑体三版 + 设备字体自检）、`icons/`（Tabler 图标库单归档 + 单色 PNG 按需生成）
- `imagecache/`（列表封面「已解码位图」缓存 `zk::ImageCache`：真机回页重设同一批封面 **315 ms → 1 ms**）
- `ui_v1/`：平台没有的能力做成自定义控件包（如 `Chart/` 图表、`Calendar/` 日历），含 example 与真机证据

## 🔌 MCP 原生原语

- resource：`flythings://catalog/knowledge`、`flythings://knowledge/<分类>/<文件>.md`、`flythings://tools`、`flythings://version`
- prompt：`flythings-new-project` / `ui-from-prototype` / `ui-verify` / `deploy-debug` / `package-deps`

## 🔧 工具面三模式（按客户端选一个，别同时配）

| 模式 | 怎么配 | 客户端看到什么 |
|------|--------|----------------|
| `dispatcher`（默认） | 只指 `mcp_server.py` | 只暴露分发器 `flythings_kb`（`op="list"` 取目录）—— schema 开销最小 |
| `all` | `FLYTHINGS_MCP_MODE=all` | 分发器 + 43 个独立工具（旧配置兼容） |
| `flat` | 指 `mcp_server_flat.py`（或 `FLYTHINGS_MCP_MODE=flat`） | 43 个独立工具，无分发器（需要独立 schema 时用；代价 ≈ 1 万 token/session） |

---

**写知识/判据/op 契约前先读 [`DESIGN_SPEC.md`](DESIGN_SPEC.md)**（MCP 只讲"本平台与标准 Linux/rootfs/GUI/包组件的差异"；通用编程能力属 AI 原生，不入库；规范优先、实测优先、不静默、唯一真源）。

当前版本 `0.27.200-open`（43 个工具）；工具清单 / 平台矩阵 / 知识规模快照见 `tools_manifest.json`。
