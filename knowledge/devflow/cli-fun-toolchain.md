---
id: devflow-cli-fun-toolchain
title: 🧰 fun 命令行工具链（原 fuse 更名；2026-09-28 内部又改成 fsc、产物目录 `.fun/` → `.fsc/`）+ 宏/产物目录改名
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [F133, Z20, Z235X]
tags: [产物目录, fun, fsc, fun-lock, fsc-lock, 老工程不用改, MCP 两代都认, 注册表双向兼容, fuse, FSC_HOME_PATH, 工具链, 编译命令, fun build, LOGD_TRACE, logic.cc, base/log.h]
evidence: []
---
# 🧰 fun 命令行工具链（原 fuse 更名；2026-09-28 内部又改成 fsc、产物目录 `.fun/` → `.fsc/`）+ 宏/产物目录改名

> 检索导引：问「用 fun 还是 fuse/fsc / fun build 挂老工程 / FUN_BUILD 宏怎么加 / 产物在 .fun 还是 .fsc / 依赖注册表在哪 / 多设备在线怎么推指定设备」→ 本文；编译部署该调哪个工具见 `knowledge/devflow/deploy-scene-map.md`。
> **2026-09-28 换代**：工具链 `v0.0.2+2609281006_e09dc96` —— 内部包名 `fun`→**`fsc`**；产物目录 `.fun/<平台>/`→**`.fsc/<平台>/`**；锁 `.fun-lock.json`→**`.fsc-lock.json`**；home `~/.fun`→**`~/.fsc`**（env `FSC_HOME_PATH`）；编译宏**同时定义 `FUN_BUILD=1` 和 `FSC_BUILD=1`**，老工程不用改。**MCP 两代都认**（产物/锁/注册表双向兼容）。
> 检索词：fun.exe / fuse.exe / fsc / FSC_HOME_PATH / 工具链 / 编译命令 / fun build / fun install / fun launch / fun sim / FUN_BUILD / FUSE_BUILD / .fun / .fsc / .fsc-lock.json / .fuse / 老工程迁移 / 注册表路径 / 多设备 / 设备选择 / -s / --device / WiFi adb / adb tcpip / adb connect / 推不上去 / more than one device / 旧 ftu / 界面没变 / base/functional.h / 找不到 base utils / base-utility 缺失 / fun install 没生效。
> **口语问法直达**：依赖包下载到哪个目录（注册表位置见 §2）/ 改了 activity 目录为什么编译没变化（fun 根本不编译 src/activity/*，见 §4.5）。

## 1. 结论（一句话）

**命令行统一是 `fun`；`fuse` 是旧名。**

> ⚠️ 但**目录级老名字还在**：生成的 CMake 里依旧写 `$ENV{FUSE_HOME_PATH}/registry/public/<平台>/<包>/<版本>/include`。看到 `.fuse` / `FUSE_HOME_PATH` 不等于工具还是 fuse。

## 2. fun.exe / fui.exe / 注册表在哪

| 位置 | 说明 |
|------|------|
| `C:\zkswe\fun\`（或 `D:\zkswe\fun\`） | 官方工具链安装目录，`fun.exe` + `fui.exe` 同目录 |
| `<项目>\fun.exe`、`<项目>\ui\fui.exe` | `flythings_attach_cli_tools` 复制过去，**随项目交付**（客户不用装 IDE） |
| 环境变量 `FLYTHINGS_FUN_DIR` | MCP 解析工具目录的候选之一（`project_tools._tool_dir()`） |
| 依赖注册表 | 工具链自带 `C:\zkswe\fun\registry\public\<平台小写键>\<包>\<版本>\`；用户级 `~/.fsc/registry/public/`（09-28 起），老 `~/.fun`、`~/.fuse` 并存；MCP `package_tools` 解析顺序 `~/.fsc` → `~/.fun` → `~/.fuse` → `C:\zkswe\fun\registry` |

`fun` 管**编译/依赖/部署/出包**；`fui` 管 **json ↔ ftu**（`pack` / `unpack` 都支持：随包 fui 自 v0.27.91 起含 `unpack`，旧版只有 `pack`）。

### 2.1 工具不在（报「缺少 fun / fui」）怎么办

MCP 找工具目录的唯一入口是 `project_tools._tool_dir()`，顺序：
`FLYTHINGS_FUN_DIR` → **包内 `<MCP>/toolchain/`** → 父目录 `toolchain/` → `D:\zkswe\fun` → `C:\zkswe\fun`；
目录里**有 `fui.exe` 或 `fun.exe` 任一即算命中**，但 `fun.exe` 单独缺失时 `_tool_path('fun.exe')`
会退回裸名 `fun.exe`，构建流程直接回「**fun.exe 未找到（工具目录: …）**」。

排查顺序：
1. 确认是用**仓库/发布包路径**跑 `mcp_server.py`（`pip install` 的 wheel 只含 .py，不含 `toolchain/` 等数据文件）；
2. 确认 `<MCP>/toolchain/fui.exe` 与 `<MCP>/toolchain/fun.exe` **两个都在**（公开版随包分发，缺一个就会报缺）；
3. 要放别处就显式指定 `FLYTHINGS_FUN_DIR=<含 fun.exe/fui.exe 的目录>`；
4. 编译还要各平台工具链：解到 `<fun 目录>/toolchains/<平台小写键>/`，缺了 `fun build` 报
   `platform toolchain url must not be empty`（是工具链没装，不是工程问题）。

> 二进制（`fun.exe` / `fui.exe` / `adb.exe` / `bin_tools/**`）**不做内容词表扫描**：它们含偶然字节
> （实测 `fun.exe` 字节里命中了某个禁词），发布裁剪时只按「路径级存在性」检查——
> **不要因为词表命中就删文件**（2026-10-06 公开版缺 `toolchain/fun.exe` 就是这么来的）。

## 3. 命令表（`fun.exe --help` 实测）

| 命令 | 用途 |
|------|------|
| `fun install` | 安装配置里声明的**所有依赖**（`--project-dir` 可指项目；`-p` 指平台） |
| `fun build -p F133` | 编译（`-p/--platform`、`-t/--target`、`-D` 预定义、`--cflags`、`--project-dir`、`--verbose`） |
| `fun launch -p F133 [-s <serial\|IP>]` | 部署到设备并启动，**仅用于临时调试**（`-s/--device` 只收合法 serial/IP；**多设备在线时必 FAIL**→ §6；MCP 侧失败自动重试 5 次） |
| `fun sim` | **模拟器运行**（fuse 时代没有这条）。⚠️ **MCP 暂不提供/不代跑**（见 §5） |
| `fun create [<starter>]` | 建工程（`--type bin` 出可执行程序工程） |
| `fun add <package>` | 追加依赖包 |
| `fun pack` | 制作升级包 `update.img`（固化用，掉电保留）/ 依赖包 |
| `fun clean` | 清理中间产物（**改了 `package.properties` 必清再全量编**，ninja 不感知） |
| `fun migrate --input= --output=`、`fun publish`、`fun login` | 迁移配置 / 发布依赖包 / 登录 |
| `fui pack <json>` / `fui unpack <ftu>` | json → ftu（设备实际加载 ftu）/ ftu → json |

## 4. 老工程用 fun 编译会挂 → 一行迁移

新生成器产出的 `src/logic/*.cc` 头部用 `#ifdef FUN_BUILD` 包着 `#include GENERATED_UI_DEFINITIONS` + `INIT_UI_EVENT_BINDINGS`；
老工程（fuse 时代）写的是 `#ifdef FUSE_BUILD` → 用 `fun build`（宏 `-DFUN_BUILD=1`）时这段被跳过 → `ui_main.h` 没进来 →
满屏 `error: 'LOGD_TRACE' was not declared` / `'Intent' does not name a type` / `'ZKButton' was not declared`。

**迁移写法（实测通过）**：

```cpp
#if defined(FUSE_BUILD) || defined(FUN_BUILD)   // 原 #ifdef FUSE_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif
```

改完 `fun build -p F133` 通过、出 `libzkgui.so`；或干脆用新 IDE/生成器重新生成 logic 文件。

## 4.5 编译单元口径（IDE vs fun，2026-09-17 纠偏 + 实测）

**两套编译体系，不要混：**

| | IDE（Eclipse/CDT） | `fun build`（本仓库推荐的命令行体系） |
|---|---|---|
| 入口 | `src/activity/mainActivity.cpp` | `src/Main.cpp` + **fun 生成的**`generated/{event,event_dispatcher,ui_main}.cpp` |
| `src/activity/*` | ✅ 参与编译 | ❌ **完全不参与编译**（该目录是 IDE 专用） |
| `src/logic/*.cc` | 由 activity `#include` 进编译单元 | ✅ **直接当编译单元编译**|
| 业务代码 `src/**/*.cpp` | 需在 IDE 工程里登记 | ✅ fun 扫描收进编译单元 |
| 编译宏 | — | `FUN_BUILD=1`（写法与迁移见 §4） |

**实测证据（z21 工程）**：`.fsc/<平台>/CMakeLists.txt`（首行 `# Auto-generated by fun`）与 `compile_commands.json`
（8 个编译单元）里**都没有 `src/activity/*`**，只有 `Main.cpp` + `logic/*.cc` + `uart/*.cpp` + `generated/{event,event_dispatcher,ui_main}.cpp`。

**纪律**：① **不要改 `.fsc/<平台>/CMakeLists.txt`**（生成物，下次 build 覆盖，改了不生效；要加源文件→放 `src/` 下）；
② 不要靠改 activity 影响 fun 构建（fun 根本不编译它，activity 只在 IDE 体系有意义）；
③ 回调/定时器注册由 `generated/event_dispatcher.cpp` 接管（`REGISTER_ACTIVITY_TIMER_TAB` 仍写在 logic 里）。

## 4.6 平台工具链放哪 + 模板依赖最低集（2026-09-17 Z235X 实测）

**工具链目录约定**：`<fun 安装目录>/toolchains/<平台小写键>/`（如 `C:/zkswe/fun/toolchains/z235x/`），内含
`bin/ include/ lib/ libexec/ share/` + 目标三元组目录（如 `arm-unknown-linux-gnueabihf/`）。
- 缺工具链时 `fun build -p <平台>` 直接 **panic：`platform toolchain url must not be empty`**（`core/platform.go:88`）——不是工程问题，是工具链没装。
- 工具链**不随 MCP/仓库分发**：拿到压缩包解压到上述目录即可用（实测编译命令变成 `.../toolchains/z235x/bin/arm-unknown-linux-gnueabihf-gcc.exe`）。
- **模板 Manifest 依赖最低集**：新平台模板除 `easyui / log / zkhardware / zknet` 外**必须带 `base-utility`**
  （版本写法与缺包处置见 §4.7）；`fun install` 从 `package.flythings.cn` 拉（Z235X 实测 `base-utility@10.11.0` + `ext4@0.0.1`）。
- **Z235X 建工程 → 编译闭环（实测）**：`flythings_create_project(platform="Z235X")` → 工具链解压到 `toolchains/z235x`
  → `fun install` → `fun build -p Z235X` → **9/9 编译链接成功，产出 `.fsc/z235x/libzkgui.so`（217,240 B）**。

## 4.7 老工程升级：补 base-utility（本口径唯一正文；2026-09-17 实测，v0.27.83）

**现象**：老工程（源头 IDE 工程 / 用户自建工程）用 `fun build` 编不过，报的是**编译错误**（不是链接错误）：
`In file included from generated/event_dispatcher.cpp:1: fatal error: base/functional.h: No such file or directory`。

**根因**：`fun` 生成的 `generated/{event_dispatcher,event_app}.{h,cpp}`、`ui_main.*` 里**固定**`#include <base/functional.h>`
（还有 `base/base.h`/`base/defer.h`/`base/exception.h`），归**依赖包 `base-utility`**；而它不是模板/IDE 自动带的——
`Manifest.xml` 不声明 → include 路径就不进 CMake（症状像「框架头文件不存在」，其实只是**包没声明/没装**）。

**处置（三步，顺序不能改）**：

1. 工程 `Manifest.xml` 的 `<dependencies>` 加一行：`<package id="base-utility" version="^10.0.0"></package>`
   （或直接 `flythings_add_package(project_root, "base-utility", with_install=True)`——写 Manifest 并跑 install）。
2. **重跑 `fun install`**（改过 `Manifest.xml` 必须重跑，否则新包的 include/lib 路径**不会**进生成的
   `.fsc/<平台>/CMakeLists.txt`，加了也白加，报错一模一样——「加了包还是编不过」这类假象的来源）。
3. `fun build -p <平台>`。

**判据（别靠猜）**：① 编过与否 = `fun build -p <平台>` 出 `.fsc/<平台>/libzkgui.so`（09-28 前 `.fun/`）；
② 依赖装上没 = `.fsc-lock.json`（前 `.fun-lock.json`）的 `dependencies.<平台小写键>.base-utility`，
且 `C:\zkswe\fun\registry\public\<平台键>\base-utility\<版本>\include\base\functional.h` 真实存在；
③ 头文件在不在命令行 = `.fsc/<平台>/build.ninja` 的 `INCLUDES` 应有 `<注册表>/<平台>/base-utility/<版本>/include`。

**工具侧防护（v0.27.83，别只靠人眼）**：
- `flythings_check_project_deps` / `flythings_validate_project`：代码或 `generated/*.h` 出现 `#include <base/…>` 而 Manifest
未声明 base-utility（依赖锁也没解析到）→ 报 `missing_framework_dependency` + 可照做的 fix。
- `flythings_build_ui_flow`：`fun install` 失败不再静默（返回体顶层 `warnings`）；build 前做框架基础头体检，缺包直接点明。
判定口径（避免误报）：**Manifest 已声明 或 依赖已解析（传递依赖也算）**即 OK（实测 `easyui` 有时会把 `base-utility` 带出来）；
  ⚠️ `base/` 前缀**不是 base-utility 独占**：`base-http-client`→`base/http_*.h`、`base-json`→`base/json_*.h`、`easyui 3.0.0(Z20)`→`base/fy_*.h`（本机注册表实扫），按「精确头名 + 前缀排除」判定。

**同源现象（一起记）**：`fun build` 报 `找不到 base utils` / `base-utility 缺失` / `fun install 没生效` —— 同一条根因。

## 4.8 `<page>Logic.cc` 头部：IDE 编译 vs FUN 编译 的两处差异（2026-10-06 实测）

**一句话**：`fun build`（以及 IDE 生成器）产出的 `<page>Logic.cc` 头部，把
`REGISTER_ACTIVITY_TIMER_TAB` 写在 `#ifdef FUN_BUILD` **里面**、并且**不补** `#include "base/log.h"` ——
这会让**两种编译各坏一种**。正确形态 = 两者都放在守卫**外面**。

### 症状（对着报错直接定位）

| 你看到的报错 | 哪个编译体系 | 根因 |
|---|---|---|
| `'REGISTER_ACTIVITY_TIMER_TAB' was not declared in this scope`（出现在 `src/activity/<page>Activity.cpp` 的 `sizeof(REGISTER_ACTIVITY_TIMER_TAB)/sizeof(S_ACTIVITY_TIMEER)`） | **IDE（Eclipse/CDT）** | 不定义 `FUN_BUILD` → 守卫块里的定时器表**整个消失** |
| `'LOGD_TRACE' was not declared` / `'LOGD' was not declared` | **`fun build`** | 缺 `#include "base/log.h"` |

### 两种形态（照 `templates/DemoControls_V85X/src/logic/` 对比）

| | `buttonLogic.cc`（**正确**） | `canvasLogic.cc`（fun 生成，需修） |
|---|---|---|
| `REGISTER_ACTIVITY_TIMER_TAB` | 在 `#ifdef FUN_BUILD … #endif` **外面** | 在守卫**里面** |
| `#include "base/log.h"` | **有** | **没有** |

修完的目标形态（头部）：

```c
#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS

#endif // FUN_BUILD          // ← 守卫收口在表之前

/** 注册定时器 … */
static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
  //{0,  6000}, //定时器id=0, 时间间隔6秒
};

#include "base/log.h"        // ← 必须有
```

### 修法（临时补丁，fun 侧修好生成器后可撤）

- **脚本**：`python scripts/fix_fun_logic_cc.py <项目根|目录|单个 .cc>`
  - 把定时器表（连同上方注释块）移出守卫；文件里真用了 `LOGD*`/`LOGI*` 时补 `base/log.h`
  - **幂等**；`--check` 只报告（rc=1=有需修的）、`--dry-run`、`--quiet`
- **自动**：`flythings_build_ui_flow` 在 **`fun build` 前 / 后各跑一次**（build 会重生成 `logic.cc`），
  修了哪些文件写进返回体 `steps` + `warnings`（不静默）
- 判据/验证（实测）：修完 `canvasLogic.cc` 头部与 `buttonLogic.cc` **逐行同构**；复跑 `--check` → 需修 0

### AI 处置口径（2026-10-06 需求方定：确认即动手，不要只给建议）

命中上面两条症状之一、且形态与你看到的一致（`REGISTER_ACTIVITY_TIMER_TAB` 在 `#ifdef FUN_BUILD` 里 / 缺
`base/log.h`）时，**直接改代码**，不要停在"建议你改一下"：

1. **直接跑修**：`python scripts/fix_fun_logic_cc.py <项目根>`（幂等；要只看不改用 `--check`）
   —— 它会修项目里**所有** `src/logic/*.cc`（不只报错那一个页面），并把改动列出来
2. **fun 侧复验**：重跑 `fun build`（`flythings_build_ui_flow` 已内置：build 前/后自动修 + 命中签名时自动重试一次）
3. **必须提示用户**：`logic.cc` 修好后请**用 IDE 重新编译一次** —— IDE 的编译单元是
   `src/activity/<page>Activity.cpp`（再由它 `#include` logic），`fun build` 不会重建 IDE 侧产物；
   两边都重编过才算修完
4. **诚实记账**：把「改了哪些文件 + 需要 IDE 重编」明确告诉用户（工具侧会写进返回体 `steps`/`warnings`）

> 反例（不要这样做）：只回一句"你的 logic.cc 头部有问题，建议把定时器表移出 `#ifdef`" —— 需求方口径是
> **能确定的就直接改**，改完把结果和后续动作（IDE 重编）交待清楚。

### 检索词

`LOGD_TRACE 未声明` / `REGISTER_ACTIVITY_TIMER_TAB 未声明` / `sizeof(REGISTER_ACTIVITY_TIMER_TAB)` /
`IDE 编译 定时器表 消失` / `logic.cc 头部` / `fun 生成 logic.cc 报错` / `FUN_BUILD 守卫`

---

## 5. 纪律与惯例

- 工具侧动作优先走 MCP（`flythings_build_ui_flow` / `flythings_add_package` / `flythings_pack_upgrade`），**禁止手搓 fun/adb 命令**（MCP 已处理 retry、设备选择、i18n 盲点等）
- **改过 `Manifest.xml`（加包/改版本/改平台）→ 必须先 `fun install` 再 `fun build`**：根因、判据、工具侧防护见 §4.7
- 调试 = `fun launch`（临时推送，掉电即失）；固化 = `fun pack` 出 `update.img`（掉电保留）——两者语义别混（见 `knowledge/devflow/deploy-scene-map.md`）；
抓帧/设备侧动作仍走 `flythings_device_screenshot`（内部已处理 rootfs 裁剪、pan 偏移、压缩链路）
- ⚠️ **`fun sim` 不在 MCP 能力面内**（2026-09-14 定「暂时发布的 mcp 不要支持 sim 功能」）：工具面不暴露该能力，`project_tools._run_fun` 也**显式拒绝 `cmd == 'sim'`**并返回正解 hint（推真机→`flythings_build_ui_flow`；出图→`flythings_device_screenshot`；要跑模拟器自己去本地命令行）。**AI 不要拿 `flythings_*` 工具去实现模拟器运行，也不要因这条向用户承诺 MCP 能跑模拟器。**

## 6. ⚠️ 多设备在线时「把工程推到指定设备」（2026-09-16 首测 / 09-17 复测 / **09-28 三测定稿**）

**结论**：多设备在线时 `fun launch`（**新旧版一样**，含 `v0.0.2+2609281006_e09dc96`）**不管带不带 `-s` 都硬失败**：

```
FATAL "host:transport <serial>" FAIL: more than one device/emulator
```

**根因（报文级）**：fun 自带 Go adb 客户端发旧式 **`host:transport <serial>`（空格分隔）**，而 platform-tools
（实测 37.0.1 与 31.0.3 一样）只认 **`host:transport:<serial>`（冒号分隔）**；空格形式下 serial 被丢掉 →
adb 按「多设备未指定」回 `more than one device/emulator`。裸 socket 直问 `127.0.0.1:5037` 可复现：

| 请求 | 应答 |
|------|------|
| `host:transport 192.168.x.x:5555`（空格，fun 的写法） | `FAIL more than one device/emulator` |
| `host:transport:192.168.x.x:5555`（冒号） | `OKAY` |

fun launch 完整序列（伪 adb host server 抓包）：`host:version` → `host:devices` → **`host:transport <serial>`（空格）**→
`shell:getprop 'ro.product.model'`。`-s` 本身生效（解析 + 校验都有）：`-s <不存在的 serial/IP>` → `FATAL device "..." not found`；
纯 IP 会自动 `adb connect`；**但不支持序号**（`-s 0/1/5` 均 not found）。单设备在线时能推（server 兜底），所以这个 bug 很容易被忽略。

**两条可行路（按推荐序）**

1. **垫片（不改厂家二进制，已实测走通）**：`scripts/adb_transport_shim.py` 把 5037 上 fun 的空格形式改写成冒号形式，转发给另起一个端口的真 adb server：

```bash
adb kill-server && adb -P 5038 start-server
adb -P 5038 connect <ip>:5555            # 按需把设备连到 5038
python scripts/adb_transport_shim.py 5037 5038
fun launch -p <平台> -s <ip>:5555         # 多设备在线也能精确推到指定设备
# 收尾：停垫片 → adb -P 5038 kill-server → adb start-server → adb connect 连回
```

实测（09-28，本机 **5 台在线**，目标 `192.168.x.x:5555`）：**4.02 s 推完**（`main.ftu` + `images/` + `libzkgui.so` +
`EasyUI.cfg`），设备侧 md5 与本地构建产物**逐一致**，另一台在线设备**未被触碰**。

2. **让 adb 列表只剩目标设备**（最省事）：`adb disconnect <其它 ip>:5555`（网络设备可逆）或拔掉其它 USB，推完连回。

**判据（别靠猜）**：`adb -s <serial> shell "ls -la /tmp/ui /tmp/lib"` + 设备上 busybox `md5sum /tmp/ui/main.ftu`（设备无 `md5sum`）
应与本地 `ui/main.ftu` **字节 + md5 一致**；库取本地 `.fsc/<平台>/libzkgui.so`（09-28 版产物目录已换成 `.fsc/`，老 `.fun/` 不再更新）；设备侧 `ls` 不认 `head`。

**其它**：唯一会拦下来的是**平台校验**（`shell:getprop 'ro.product.model'` 对比工程平台，不匹配 → `FATAL platform not match`，exit 1）；push 出错也 `FATAL` + exit 1。
**WiFi adb**：`adb tcpip 5555` → `adb connect <ip>:5555`；掉线可随时重连（实测未重跑 `tcpip` 直接重连成功），设备重启前有效；**用完 `adb disconnect <ip>:5555`**避免选错设备。

## 7. 未验证 / 边界

- `fun sim` 只确认了 `--help` 存在该命令，**没实跑**（模拟器细节看 wiki 官方镜像）；发布版 MCP 也不支持该功能（见 §5）
- 本机旧 `fuse.exe` 仍可运行（实测能编过），历史工程里的 `.fuse/` 产物与 `FUSE_BUILD` 宏**不是错误**，只是旧代；**新知识一律按 fun 写**
- `~/.fsc`、`~/.fun`、`~/.fuse` 三套注册表的具体分工（哪套优先、镜像还是复制）未逐条验证；MCP 解析顺序见 §2
