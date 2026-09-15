# 🧰 fun 命令行工具链（原 fuse 更名）+ 宏/产物目录改名

> 2026-09-14 沛哥指出「fuse 命令行已换成 fun，文档没更新」→ 本机逐项实测校准（`fun.exe v0.0.2+2609032137_b8f28e3`、宏 `FUN_BUILD`、产物 `.fun/<平台>/`）。
> 检索词：fun.exe / fuse.exe / 命令行工具 / 工具链 / 编译命令 / fun build / fun install / fun launch / fun sim / FUN_BUILD / FUSE_BUILD / .fun / .fuse / 老工程迁移 / 注册表路径 / 多设备 / 设备选择 / -s / --device / WiFi adb / adb tcpip / adb connect / 推不上去 / more than one device / 旧 ftu / 界面没变。

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
| `fun launch -p F133 [-s <serial\|IP>]` | 部署到设备并启动，**仅用于临时调试**（`-s/--device` **支持**：序号或 IP；**多设备时必须显式指定**，否则 fun 静默取列表第一个 → 见 §7；MCP 侧失败自动重试 5 次） |
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

## 7. ⚠️ 多设备（USB + WiFi adb）时的设备选择陷阱（2026-09-16 实测）

> 起因：沛哥报「fun launch 在同时连着 WiFi adb 时静默失败，改了 ui 加控件、build 通过、launch 看着成功，界面就是不画」。实测验收后**现象成立、机制要改**（不是 adb 报错被吞，见下）。

**机制（实测，扫 fun.exe 字符串 + 伪造 adb host server 抓包）**
- `fun launch` 走 **fun 自带 Go adb 客户端**（`pkg/adb` → 直连 adb host server `127.0.0.1:5037`，序列 `host:version` → `host:devices` → `host:transport <serial>` → `shell:` / `sync:`）。
- fun.exe 里 shell 出 `adb` 二进制**只有两处，且都带 `-s`**（`adb -s %s shell chmod 777 %s`、`adb -s %s shell %s`）→ fun **不会**报 adb 的 `more than one device/emulator`。
- 2 台设备同时在线时：fun **不报错、不警告、不询问**，按 `adb devices` 列表顺序**取第一个**直接推（实测两种顺序各跑一次，WiFi 在前推 WiFi、把另一台放前面就推那台；pty 交互模式也一样）。
- 唯一会拦下来的是**平台校验**（`shell:getprop 'ro.product.model'` 对比项目平台），不匹配才 `FATAL platform not match`（exit 1）；push 真出错也会 `FATAL …` + exit 1（不是把输出全吞）。

**为什么危害很大**：被选中的那台若与目标**同平台/同型号**（或 push 到另一台同型号机器），push 会「成功」，目标机仍是旧 `ftu`/旧 `libzkgui.so` → 症状是「build 通过、launch 成功、界面就是不变」，极易被误判成「框架不支持这个控件」。

**正确做法**
1. `fun launch -p <平台> -s <serial|IP>`（`-s/--device` 实测可用，v0.0.2；支持序号或 IP）；
2. 或调试完 `adb disconnect <ip>:5555` 只留目标设备再 launch。

**判据（别靠猜）**：比对设备与本地 `ui/*.ftu`

```bash
adb -s <serial> shell "ls -la /tmp/ui"                       # 设备侧字节数/时间
adb -s <serial> shell "/tmp/busybox md5sum /tmp/ui/main.ftu" # 设备无 md5sum，用已推的 busybox
```

设备 `/tmp/ui/main.ftu` 应与本地 `ui/main.ftu` **字节数 + md5 一致**（实测单设备 launch 后 1419 B / `FDC802FF232328DD5395EB433F8BA223` 完全一致；不一致 = 没推上去）。注意设备侧 `ls` 不认 `head`（管道会报 `head: not found`）。

**WiFi adb 用法**：`adb tcpip 5555` → `adb connect <ip>:5555`；该设置掉线后可随时重连（实测未重跑 `tcpip` 直接重连成功），设备重启前一直有效；**用完 `adb disconnect <ip>:5555`**，避免 fun 选错设备。

## 8. 未验证 / 边界

- `fun sim` 只确认了 `--help` 存在该命令，**没实跑**（模拟器细节看 wiki 官方镜像）；⚠️ 且**发布的 MCP 暂不支持该功能**（沛哥 2026-09-14 定，见 §5）
- 本机旧 `fuse.exe` 仍可运行（实测能编过），所以历史工程里的 `.fuse/` 产物与 `FUSE_BUILD` 宏**不是错误**，只是旧代；**新知识一律按 fun 写**
- `~/.fun` 与 `~/.fuse` 两套注册表的具体分工（哪套优先、镜像还是复制）未逐条验证；MCP `package_tools` 的解析顺序是 `~/.fun` → `~/.fuse` → `C:\zkswe\fun\registry`
