<div align="center">

# 🦅 FlyThings MCP Open

**让 AI 助手直接获得 FlyThings 完整开发能力：一句话安装，一句话开发 FlyThings OS 人机交互产品**

**flythings-mcp | FlyThings MCP | FlyThings OS | FlyThings AI 助手 | 中科世为 MCP | FlyThings HMI**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)
[![FastMCP](https://img.shields.io/badge/FastMCP-Powered-orange.svg)](https://github.com/jlowin/fastmcp)

</div>

---

## ① 一键安装

**方式一：让 AI 帮你装（推荐）** —— 直接对你的 AI 说：

```
帮我克隆并安装 https://gitee.com/Kwolve/fly-things-os_-mcp 项目
```

AI 会自动完成：克隆项目 → 按 `requirements.lock` 安装依赖（该文件是已锁定、实测通过的版本组合）→ 引导配置 → 完成。

> 需要 Python 3.10+。Windows 也可双击 `install.bat` 一键装依赖（装完自动跑一次离线自检）；
> 双击 `setup.bat` 可交互生成配置（等价于 `python configure.py`）。
> 想自己拉最新版也行：`pip install mcp onnxruntime tokenizers Pillow`（不锁定，风险自负）。

**2) 配置到 AI 工具（stdio）** —— 在**你的项目根目录**建 `.mcp.json`（Trae / Cursor / Kimi 均识别）：

```json
{
  "mcpServers": {
    "flythings-kb-open": {
      "type": "stdio",
      "command": "python",
      "args": ["C:/你的路径/flythings-mcp-open/mcp_server.py"]
    }
  }
}
```

各工具放置位置：Trae → 项目根 `.trae/mcp.json` 或 `.mcp.json`；Cursor → 项目根 `.cursor/mcp.json`（或 Settings → MCP → Add）；
Kimi → 项目根 `.mcp.json` 或 `.kimi/mcp.json`；Claude Desktop → `claude_desktop_config.json` 的 `mcpServers`。
> `python` 不在 PATH 时用完整路径（如 `C:/Users/<你>/AppData/Local/Programs/Python/Python313/python.exe`）。

**3) 验证** —— 问 AI「**MCP 版本是多少？**」：
应返回 `flythings-kb-open 0.27.84-open`，**35 个工具**（另含 `binTools` 字段：设备端预编译工具 touch / busybox / ui_test / mt_test / zkshot，
在 `bin_tools/<平台>/` 下，**不是 op、不占 op 名额**）。

> **工具面三模式（按客户端选一个，别同时配）**
> | 模式 | 怎么配 | 客户端看到什么 |
> |------|--------|----------------|
> | `dispatcher`（默认） | 只指 `mcp_server.py` | 只暴露分发器 `flythings_kb`（`op="list"` 取目录）—— schema 开销最小 |
> | `all` | `FLYTHINGS_MCP_MODE=all` | 分发器 + 35 个独立工具（旧配置兼容） |
> | `flat` | 指 `mcp_server_flat.py`（或 `FLYTHINGS_MCP_MODE=flat`） | 35 个独立工具，无分发器（Trae / Cursor / Claude Desktop 需要独立 schema 时用；代价 ≈ 1 万 token/session） |
>
> 默认从「全注册」改为「只分发器」是 v0.27.34 的**行为变更**；受影响就设 `FLYTHINGS_MCP_MODE=all` 恢复。

---

## ② 功能说明

### 🎨 UI 布局（json 与 ftu）
- **布局以 `ui/*.json` 为源**，`fui pack` 生成设备实际加载的 `ui/*.ftu` —— **ftu 是编译产物，不要手写/手改**（口径见 `knowledge/devflow/ftu-json-pipeline.md`）
- HTML 原型 → json 布局（`flythings_html_to_json`）；json → 可确认的 HTML 预览稿（`flythings_ui_preview`，多整屏 window 工程带页面切换条）
- 布局解析（`flythings_read_json`）、字段口径（`knowledge/uicontrols/`）
- **可视化编辑**：可拖拽/缩放的编辑器 → 变更写回 json 并 pack（`flythings_ui_visual(action="editor"|"edit_apply")`）
- **跨框架控件映射**：LVGL / Qt / Android / 小程序 / emWin / MFC 控件 → FlyThings 等价控件 + 可直接粘的 json 片段（`flythings_map_control`）
- **图片资源**：AI / emoji / 线条三级降级生成（`flythings_generate_ui_assets`）；尺寸与控件盒核对（`flythings_verify_assets`、`ui_tools/check_all.py`）

### 🔍 预览与像素验收
- 浏览器预览稿（含 `#window__N` 直达、显示隐藏幽灵框）
- **真机抓屏** `flythings_device_screenshot`：PNG/JPG/BMP、缩放省 token、方向/裁剪自动适配工程配置、支持视频层抓帧
- **像素 diff**（`flythings_ui_visual(action="diff")`，±2 容差）→ 0 token 回归验收

### 🏭 编译 / 部署 / 出包
- `flythings_build_ui_flow`：json/ftu 时间戳检查 → fui pack → fun install → fun build →**设备探测 + fun launch 推送运行**
  > ⚠️ **默认会推设备**（`with_launch` 缺省 True，v0.27.84 起）：build 后自动探测 `adb devices -l` ——
  > 0 台 → `needDeviceInput=true` + `installHint`（要不要装 **ADB 驱动** / 开 USB 调试并授权 / 改用 `device='<IP>:5555'` 网络接入）；
  > 多台 → 列出 serial+model+平台匹配情况，**不替你猜**，要求显式 `device=`；
  > 恰好 1 台且平台匹配 → 自动 `fun launch -s <serial>`。
  > 返回体含 `launched`/`pushed`/`device`/`model`/`deviceSync`（设备侧 ftu/so 字节+md5 与本地是否一致）与 `staleOnDevice`（true ⇒ 设备上跑的还是旧版）。
  > **不想推设备（只编译）就显式传 `with_launch=False`。**
- **PC 端 adb 随包**：`tools/adb/adb.exe`（+ `AdbWinApi.dll`/`AdbWinUsbApi.dll`，≈6.1 MB），客户不必另装 Android SDK；
  全仓 adb 走单一入口 `adb_tools.resolve_adb()`（环境变量 `ADB`/`FLYTHINGS_ADB` → 随包 → PATH）；
  设备型号→平台对照见 `device_models.json`（排查：`python adb_tools.py`）
- `flythings_pack_upgrade`：固化升级包 `update.img`（TF 卡 / ADB setprop / zkautoupgrade / HTTP OTA 四种刷法）
- **换开机 logo**：`boot_logo.JPG` → **MISC 分区**（跟 `update.img` **同一套升级机制与触发**；体积必须 ≤ MISC 分区大小 —— 本板 Z21 实测 512 KB，先量 `cat /proc/mtd`）→
  `python tools/make_boot_logo.py --size 1024x600 --out boot_logo.JPG`（生成 + 体积闸门）/ `python tools/set_boot_logo.py --image boot_logo.JPG --device <serial|IP:5555>`（**默认 dry-run**，`--yes` 才真触发）；
  细节与待验证项见 `knowledge/devflow/upgrade-pack-image.md` §三
- `flythings_create_project` / `flythings_create_bin_project`：从内置模板建工程（F133/F135/Z21/Z20/T113/V85X/Z235X）
- `flythings_attach_cli_tools`：把 `fui.exe`/`fun.exe` 复制进项目，客户不用装 IDE 也能编译部署
- `flythings_validate_project`：工程规范全检（依赖 / 框架约定 / 时间戳防呆）
- **工具链安装（Z235X）**：把 `z235x` 工具链放到 **`<fun 安装目录>/toolchains/z235x/`**
  （目录名 = 平台小写键）；工具链**不随本包分发**，缺了 `fun build -p Z235X` 会报
  `platform toolchain url must not be empty`——先放好再编译

### 📦 依赖包与 Manifest
- 包检索 / 版本 / 头文件级 API（`package_search` / `query_package` / `get_package_api`）
- Manifest 生成（`flythings_manifest`，默认 dry_run 只推荐）→ 加包 `add_package` → 递归解析 `resolve_dependencies` → include 对账 `check_project_deps`

### 🧠 知识库与硬件
- **全离线检索**（本地 bge-small-zh 向量 + BM25 双路 RRF，返回体带 `quality`/`source`，模型不可用自动降级），无需任何 API Key
- 硬件型号库（`flythings_hardware_info`）：分辨率/方向、按键值、接口规格；未收录只给候选不猜规格
- 版本/工具数查询（`flythings_get_version`）

### 🌐 i18n 与自动化测试
- 多语言：`scan` / `add_language` / `export` / `import` / `refactor` / `to_json`
- 自动化测试：`flythings_gen_ui_test`（traverse / monkey / custom，真机触摸注入）

### 🧩 可复用组件（`components/`，随本 MCP 一起发布）
- `ble/`（BLE 门面 `zk::ble`）、`fonts/`（思源黑体三版 + 设备字体自检）、`icons/`（Tabler 图标库单归档 + 单色 PNG 按需生成）
- `ui_v1/`：平台没有的能力做成自定义控件包（如 `Chart/` 图表、`Calendar/` 日历），含 example 与真机证据

### 🔌 MCP 原生原语
- resource：`flythings://catalog/knowledge`、`flythings://knowledge/<分类>/<文件>.md`、`flythings://tools`、`flythings://version`
- prompt：`flythings-new-project` / `ui-from-prototype` / `ui-verify` / `deploy-debug` / `package-deps`

---

当前版本 `0.27.85-open`（35 个工具）；工具清单 / 平台矩阵 / 知识规模快照见 `tools_manifest.json`，自检闸门见 `scripts/check_consistency.py --with-tests`。

MIT License · FlyThings Team · 深圳中科世为科技有限公司 · [developer.flythings.cn](https://developer.flythings.cn/)
