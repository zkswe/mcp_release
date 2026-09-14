# 🧰 fun 命令行工具链（原 fuse 更名）+ 宏/产物目录改名

> 2026-09-14 沛哥指出「fuse 命令行已换成 fun，文档没更新」→ 本机逐项实测校准（`fun.exe v0.0.2+2609032137_b8f28e3`、宏 `FUN_BUILD`、产物 `.fun/<平台>/`）。
> 检索词：fun.exe / fuse.exe / 命令行工具 / 工具链 / 编译命令 / fun build / fun install / fun launch / fun sim / FUN_BUILD / FUSE_BUILD / .fun / .fuse / 老工程迁移 / 注册表路径。

## 1. 结论（一句话）

**命令行统一是 `fun`；`fuse` 是旧名。** 工具更名连带改了三个地方，写文档/写命令时别再用旧名：

| 东西 | 旧（fuse 时代） | 新（fun） | 备注 |
|------|------|------|------|
| CLI | `fuse.exe` | **`fun.exe`** | 本机旧 fuse = `v0.0.2+202606171636`，新 fun = `v0.0.2+2609032137` |
| 构建宏 | `FUSE_BUILD` | **`FUN_BUILD`** | 编译命令行实测 `-DFUN_BUILD=1`（旧版是 `-DFUSE_BUILD=1`） |
| 中间产物目录 | `.fuse/<平台>/` | **`.fun/<平台>/`** | 生成的 UI/CMake/ninja、`update.img` 都在这里 |
| 依赖注册表 | `~/.fuse/registry/public/` | **`~/.fun/registry/public/`** | 旧的 `.fuse` 目录仍是**历史注册表**（MCP 会兜底查），`C:\zkswe\fun\registry\public` 是工具链自带 |

> ⚠️ 但**目录级老名字还在**：生成的 CMake 里依旧写 `$ENV{FUSE_HOME_PATH}/registry/public/<平台>/<包>/<版本>/include`。看到 `.fuse` / `FUSE_HOME_PATH` 不等于工具还是 fuse。

## 2. fun.exe / fui.exe 在哪

| 位置 | 说明 |
|------|------|
| `C:\zkswe\fun\`（或 `D:\zkswe\fun\`） | 官方工具链安装目录，`fun.exe` + `fui.exe` 同目录 |
| `<项目>\fun.exe`、`<项目>\ui\fui.exe` | `flythings_attach_cli_tools` 复制过去，**随项目交付**（客户不用装 IDE） |
| 环境变量 `FLYTHINGS_FUN_DIR` | MCP 解析工具目录的候选之一（`project_tools._tool_dir()`） |

`fun` 管**编译/依赖/部署/出包**；`fui` 管 **json ↔ ftu**（本项目内置的 fui 只支持 `pack`，`unpack` 是空壳 → 逆向要厂家版 fui）。

## 3. 命令表（`fun.exe --help` 实测）

| 命令 | 用途 |
|------|------|
| `fun install` | 安装配置里声明的**所有依赖**（`--project-dir` 可指项目；`-p` 指平台） |
| `fun build -p F133` | 编译（`-p/--platform`、`-t/--target`、`-D` 预定义、`--cflags`、`--project-dir`、`--verbose`） |
| `fun launch -p F133` | 部署到设备并启动，**仅用于临时调试**（不支持 `-s`，设备由 fun 自动选；MCP 侧失败自动重试 5 次） |
| `fun sim` | **模拟器运行**（fuse 时代没有这条）。⚠️ **MCP 暂不提供/不代跑**（沛哥 2026-09-14 定，见 §6） |
| `fun create [<starter>]` | 建工程（`--type bin` 出可执行程序工程） |
| `fun add <package>` | 追加依赖包 |
| `fun pack` | 制作升级包 `update.img`（固化用，掉电保留）/ 依赖包 |
| `fun clean` | 清理中间产物（**改了 `package.properties` 必清再全量编**，ninja 不感知） |
| `fun migrate --input= --output=`、`fun publish`、`fun login` | 迁移配置 / 发布依赖包 / 登录 |
| `fui pack <json>` | json → ftu（设备实际加载 ftu） |

## 4. 老工程用 fun 编译会挂 → 一行迁移

新生成器产出的 `src/logic/*.cc` 头部是：

```cpp
#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD
```

老工程（fuse 时代生成）写的是 `#ifdef FUSE_BUILD` → 用 `fun build`（宏是 `-DFUN_BUILD=1`）时这段被跳过 → `ui_main.h` 没进来 → 满屏：

```
error: 'LOGD_TRACE' was not declared in this scope
error: 'Intent' does not name a type
error: 'ZKButton' was not declared in this scope
```

**迁移写法（实测通过）**：

```cpp
#if defined(FUSE_BUILD) || defined(FUN_BUILD)   // 原 #ifdef FUSE_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif
```

改完 `fun build -p F133` 通过、出 `libzkgui.so`；或者干脆用新 IDE/生成器重新生成 logic 文件。

## 5. 纪律与惯例

- 工具侧动作优先走 MCP（`flythings_build_ui_flow` / `flythings_add_package` / `flythings_pack_upgrade`），**禁止手搓 fun/adb 命令**（MCP 已处理 retry、设备选择、i18n 盲点等）
- **改过 `Manifest.xml`（加包/改版本/改平台）→ 必须先 `fun install` 再 `fun build`**，否则新包 include/lib 路径不会进生成的 CMake（加了也白加）
- 调试 = `fun launch`（临时推送，掉电即失）；固化 = `fun pack` 出 `update.img`（掉电保留）——两者语义别混（见 `deploy-scene-map.md`）
- ⚠️ **`fun sim` 不在 MCP 能力面内**（沛哥 2026-09-14 定：「暂时发布的 mcp 不要支持 sim 功能」）：工具面不暴露该能力，`project_tools._run_fun` 里也**显式拒绝 `cmd == 'sim'`** 并返回正解 hint（推真机→`flythings_build_ui_flow`；出图→`flythings_device_screenshot`；要跑模拟器自己去本地命令行）。**AI 不要拿 `flythings_*` 工具去实现模拟器运行，也不要因这条向用户承诺 MCP 能跑模拟器。**
- 抓帧/设备侧动作仍走 `flythings_device_screenshot`（内部已处理 rootfs 裁剪、pan 偏移、压缩链路）

## 6. 未验证 / 边界

- `fun sim` 只确认了 `--help` 存在该命令，**没实跑**（模拟器细节看 wiki 官方镜像）；⚠️ 且**发布的 MCP 暂不支持该功能**（沛哥 2026-09-14 定，见 §5）
- 本机旧 `fuse.exe` 仍可运行（实测能编过），所以历史工程里的 `.fuse/` 产物与 `FUSE_BUILD` 宏**不是错误**，只是旧代；**新知识一律按 fun 写**
- `~/.fun` 与 `~/.fuse` 两套注册表的具体分工（哪套优先、镜像还是复制）未逐条验证；MCP `package_tools` 的解析顺序是 `~/.fun` → `~/.fuse` → `C:\zkswe\fun\registry`
