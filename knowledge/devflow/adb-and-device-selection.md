---
id: devflow-adb-and-device-selection
title: ADB 随包 + 设备选择 + 「跑起来了没」（v0.27.84）
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [F133, F135, Z21, V85X]
tags: [adb 在哪, 找不到 adb, adb 驱动, 设备连不上, 该推哪台设备, 多设备推错, installHint, staleOnDevice, 设备上跑的还是旧版, launch 默认推设备吗, with_launch, 探测, 推送, 抓屏, i18n 推送, CLI 侧的]
evidence: []
---
# ADB 随包 + 设备选择 + 「跑起来了没」（v0.27.84）

> 检索导引：问「找不到 adb / 要不要装 Android SDK / 设备连不上 / 多台设备推错台 / 怎么知道程序跑起来了没 / launch 默认推哪台」→ 本文；多设备推送的 CLI 侧陷阱见 `knowledge/devflow/cli-fun-toolchain.md` §6。
> 检索词：adb 在哪 / 找不到 adb / 要不要装 Android SDK / adb 驱动 / 设备连不上 /
> 该推哪台设备 / 多设备推错 / needDeviceInput / installHint / staleOnDevice /
> 设备上跑的还是旧版 / launch 默认推设备吗 / with_launch
>
> 适用范围：MCP 侧一切要连设备的动作（探测、推送、抓屏、i18n 推送）。CLI 侧的
> `fun launch` 机制见 `knowledge/devflow/cli-fun-toolchain.md`（含 §7 多设备陷阱）。

## 1. adb 从哪来（单一入口 `adb_tools.resolve_adb()`）

v0.27.84 之前，仓库里 **6 处各写一份**adb 定位逻辑，且默认写死 `'adb'` 字面量
→ 客户机没装 Android SDK 就到处「找不到 adb」。现在：

| 优先级 | 来源 | 说明 |
|--------|------|------|
| ① | 环境变量 `ADB` / `FLYTHINGS_ADB`（兼容旧名 `ADB_PATH`） | 显式指定永远优先 |
| ② | **随包**`tools/adb/adb.exe`（非 Windows 用 `tools/adb/adb`） | 随 MCP 分发，开箱可用（≈6.1 MB） |
| ③ | `PATH` 里的 `adb` | 客户自己装过 platform-tools 时兜底 |

随包内容只有三件：`adb.exe` + `AdbWinApi.dll` + `AdbWinUsbApi.dll`
（实测版本 `1.0.41 / 31.0.3-7562133`）。**不带**IDE 里那些杂件
（`vdisp_capture.exe`、`adb*.tmp`、日志快捷方式）。

排查一条命令（零副作用，适合让客户自己跑）：

```
python adb_tools.py            # 解析来源 + 版本 + 设备列表（带型号↔平台判定）
python adb_tools.py devices    # 只列设备
```

⚠️ `fun launch` **走的是 fun 自带的 Go adb 客户端**（直连 `127.0.0.1:5037`），
不用这里的 adb 二进制；两者共用同一个 host server（所以启动 server 对双方都有利）。
宿主 server 版本冲突/设备 `offline` 时先 `kill-server` 再 `devices`（比拔插有效）。

## 2. 型号 → 平台（`device_models.json`）

设备与工程平台必须一致，否则 `fun launch` 直接 `FATAL platform not match`。
型号串取自设备 `ro.product.model`（`adb devices -l` 常常不带，要 `getprop` 问）：

| `ro.product.model` | 平台 | 依据 |
|--------------------|------|------|
| `Zkswe_SSD21X_SPINOR` | Z21 | 本仓实测（`components/ble/platforms.md`、`knowledge/devflow/device-deploy-budget.md`）+ 2026-09-17 真机复测 |
| `Zkswe_SSD20X_SPINOR` | Z20 | 本仓实测（`components/ble/platforms.md`）+ 2026-09-17 真机复测 |
| `Zkswe_V85X_SPINOR` | V85X | 本仓实测（`components/fonts/platforms.md`、`knowledge/v85x/display-layer-debug.md`）+ 复测 |
| `Zkswe_F133_SPINOR` | **待确认**| 本仓无实测记录（举例提到）；`device_models.json` 里登记为 `todo`、平台留空 |
| `Zkswe_F136_SPINOR` | **待确认**| 同上（若确认，平台写 `F135`——`platforms.py` 把 F136 归一为 F135） |

**纪律**：型号表只放型号字符串，**不放内网 IP / 序列号**（隐私闸门会拦）；
不确定的一律 `platform=""` + `confidence="todo"`，**不臆造**。拿到新板子后按下面第 4 节回填。

## 3. 「跑起来了没」（v0.27.84 的 launch 默认动作）

`flythings_build_ui_flow(project_root)` **默认 `with_launch=True`**：
build 通过 → 设备探测 → 推送/运行 → **比对设备侧产物**。
只编译不碰设备：显式传 `with_launch=False`（保守开关，行为与旧版一致）。

探测规则（**不猜**）：

| 探测结果 | 行为 |
|----------|------|
| 0 台 device | `needDeviceInput=true` + `installHint`（见下）+ 失败原因 |
| 多台 | 列 serial / model / 平台匹配情况，**要求显式 `device=`**（多设备下 fun 会硬失败，见 §5 报文证据） |
| 1 台且平台匹配 | 自动 `fun launch -s <serial>` |
| 1 台但平台不一致 | 不推，报明原因（显式传 `device=` 才算「你知情」） |
| 1 台但型号未知 | 照推 + `warnings`（fun 自己会做平台校验） |

⚠️ **`device=` 也救不了多设备**（2026-09-17 实测）：本机 platform-tools 1.0.41/31.0.3 下，
只要 adb 列表不只一台，`fun launch`（带不带 `-s`）都 `FATAL more than one device/emulator`
—— 因为 fun 的 adb 客户端发的是旧式 `host:transport <serial>`（空格分隔），现代 server 不认，
serial 被当空气（报文级证据见 `knowledge/devflow/cli-fun-toolchain.md` §6）。处置：先把其它设备下线
（`adb disconnect <其它serial>`，可逆）再推。

`installHint`（0 台时给用户的照做清单）：① **ADB 驱动**（本包只带 adb 程序本身，
Windows 上设备管理器带叹号 = 缺驱动）；② 设备侧开 **USB 调试**并在弹框授权
（未授权会显示 unauthorized，不是没连上）；③ 或改用**网络接入**
`device='<设备IP>:5555'`（工具会先 `adb connect` 再推）；④ 若 `adb devices` 里有
offline/unauthorized 条目会一并列出；⑤ 附 adb 报错原文。

**`staleOnDevice`**（把「改了 json 忘 pack / 推了没生效」两个坑堵住）：
launch 成功后比对设备侧 `/tmp/ui/*.ftu`、`/tmp/lib/libzkgui.so` 与本地
（能拿到 md5 比 md5，否则退化为比字节数），返回体给 `deviceSync`
（`localBytes`/`deviceBytes`/`localMd5`/`deviceMd5`/`same`/`reason`）：

- `staleOnDevice=true` ⇒ **设备上跑的还是旧版**，`warnings` 里给两条最常见原因：
  ① 改了 `ui/*.json` 但时间戳没变（本工具第②步按时间戳决定是否 pack）→ 先 `flythings_fui_pack`；
  ② launch 推送没生效/掉线 → 确认 `device=` 选对了机器后重跑。
- 设备侧文件读不到（缺 busybox、文件不存在）也会算 stale 并在 `reason` 说明，不假装一致。

⚠️ 判定依据是 fun launch 的部署约定：UI 资源 → `/tmp/ui/`，库 → `/tmp/lib/`。
设备重启会清空 `/tmp`，所以「重启后没推 = 一定不一致」是预期行为（不是 bug）。

## 4. 新板子入库流程（拿到样机 10 分钟）

```
tools/adb/adb.exe connect <设备IP>:5555          # 或直接 USB
tools/adb/adb.exe devices -l                     # 看 model 字段
tools/adb/adb.exe -s <serial> shell getprop ro.product.model   # 没 model 就问它
python adb_tools.py                              # 确认判定与预期一致
```

把型号串按第 2 节格式补进 `device_models.json`（写 `source` = 实测日期与依据，
`confidence="confirmed"`），并在本表同步一行。

## 5. 实测记录（2026-09-17，本机真机）

**探测/解析**
- `tools/adb/adb.exe version` → `Android Debug Bridge version 1.0.41 / Version 31.0.3-7562133`；
- `python adb_tools.py` → 三台在线全部正确判定（Z21 / Z20 / V85X，型号均由
  `devices -l` 的 `model:` 或 `getprop` 取到）；
- 默认参数 `build_ui_flow`（三台在线）：build 通过 → 探测到多台 → `needDeviceInput=true` +
多设备清单（带平台匹配列），**未替用户选机器**；
- `with_launch=False`：到 build 结束，`launchSkipped=true`、`device=""`，不碰设备。

**单台在线 → 自动选机 + 推送 + 设备侧比对（Z21）**
- `launched/pushed=true`，`device=<Z21 的 IP:5555>`，`model=Zkswe_SSD21X_SPINOR`，`platformMatch=match`；
- `deviceSync`：`/tmp/ui/main.ftu` 本地 186 B / 设备 186 B、md5 两侧相同；
  `/tmp/lib/libzkgui.so` 本地 277340 B / 设备 277340 B、md5 两侧相同 → `staleOnDevice=false`。

**stale 判定（本地改过但没推）**
- 本地 ftu 改到 187 B（设备仍 186 B）→ `staleOnDevice=true`，明细给出两边字节/md5 与 `reason=md5 不一致`，
  `warnings` 里明说「设备上跑的还是旧版」+ 两个常见原因；还原后 `allMatch` 回到 true。

**0 台设备分支（真实复现：临时断开全部设备）**
- `ok=false`、`needDeviceInput=true`、`launched/pushed=false`、`device=""`、`staleOnDevice=false`、
  `device_probe` step `success=false count=0`，`installHint` 原文给出「ADB 驱动 / USB 调试授权 / 网络接入」三条。

**设备端取数踩到的 3 个坑（已修在 `adb_tools`）**
1. `wc -c < file` 返回**空**（裁剪 rootfs）→ 尺寸只能靠 `ls -l`，且 **`ls -l` 第 1 个数字是硬链接数（恒为 1）**，
第 5 列才是字节数（旧写法把每个文件都报成 1 字节 = 假 stale，实测踩到）；
2. 设备没有 `md5sum`、`busybox` 也不在 PATH → 用**随仓**`bin_tools/<平台>/busybox`
   （优先复用设备上已有的 `/tmp/busybox`）拿到 md5，才做到「比 md5」而不是「比字节」；
3. 多设备下 `fun launch` 硬失败（机制与处置见 §3 与 `knowledge/devflow/cli-fun-toolchain.md` §6），
所以单台推送验证需要先 `adb disconnect` 其它设备（本次实测即如此，推完已连回）。

## 6. 待确认 / 未覆盖（诚实标注）

- `Zkswe_F133_SPINOR` / `Zkswe_F136_SPINOR` 两条型号串 **平台留空（todo）**：本仓
没有 F133/F135 真机型号实测记录，不臆造；拿到板子按第 4 节回填。
- 其它平台的型号串（T113 / Z235X）同样**未登记**→ 会走「平台未知」分支（照推 + warning）。
- USB 接入口的 `installHint` 里「驱动没装」的判定**目前只能靠人工**（设备管理器），
工具无法从 adb 侧区分「没插」「驱动没装」「没授权」——三者都表现为 0 台或 unauthorized。
- **fun 与 adb server 的兼容性只在本机 platform-tools 1.0.41/31.0.3 上验证过**：别的 adb server 版本（旧版 / 不同分发）报文解析可能不同，可能在多设备下行为不一样
  —— 复测方法就写在 `knowledge/devflow/cli-fun-toolchain.md` §6（裸 socket 问 5037，看 `host:transport` 是否被认）。
- `deviceSync` 只比对 `ui/*.ftu`（最多 8 个）与 `libzkgui.so`：**图片/字体/i18n/配置没比**
  （那些不是 ftu 时代同一问题，且体积大）；需要时可后续扩。
- 设备侧被 launch 覆盖前的旧文件无备份（`fun launch` 语义就是调试推送）→ 要保留请用 `fun pack` 出 update.img。
