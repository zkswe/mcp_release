# rapidjson · 平台实测表

> 口径：**只写实测过的**；没测的写「未验证」+ 需要什么条件，**不编、不推**。
> ⚠️ 本包 `package.yaml` 里是 **`verified: null` / `status: unverified`**，且 `libs: []`（**纯头文件包**）。
> **本仓没有任何 rapidjson 的真机验证记录** —— 本文件的结论就是「全部未验证」，理由与所需条件写在下面。

| 平台 | 版本 | 结论 | 实测内容 | 证据 |
|---|---|---|---|---|
| Z20 | rapidjson 1.1.0 | ❌ 未验证 | 无（本仓未上真机；见「为什么没验证」） | — |
| Z21 | — | ❌ 未验证 | 无。**且本包在本地 registry 只有 z20 目录**（z21/f133/f136/t113emmc/v85x 下都没有）→ 别的平台要用得先确认包站是否有 | — |
| F133 / F136 | — | ❌ 未验证 | 同上（registry 无包 + 无真机记录） | — |
| T113EMMC | — | ❌ 未验证 | 同上 | — |
| V85X | — | ❌ 未验证 | 同上 | — |

## 为什么没验证（如实说明）

- 本包是**纯头文件库**（`include/rapidjson/*.h`，36 个头；`libs` 为空，没有 `.a`/`.so`）。
  它的"可用性"只取决于 **include 路径是否进 CMake**，不存在"库能不能链"的问题 → 没有传统意义上的"驱动验证"。
- 它的 `package.yaml` 事实来源是**实读包头**（`document.h` / `reader.h` / `writer.h` 里的真实签名）
  + 交叉对照既有工程代码 `projects/SmartPanel_HA/src/network/LocalLink.cpp`、`src/logic/scenesLogic.cc`（Z20 在跑，直接 `#include <rapidjson/...>`）。
  **⚠️ 那是既有项目在用的痕迹，不是本仓自己的验证记录** → 不能据此写成"已验证"。
- 本轮补文档**没有**为了凑"已验"而上机跑一遍（任务口径：宁可写未验证，不编）。

## 要把它变成「已验证」需要什么

1. 在 Z20 真机上跑一个最小工程（可直接用本包 `example/`）：`fsc install && fsc build -p z20` → `/tmp` 劫持部署（见下方复现方式）；
2. 用**真实报文**（不是自造小 JSON）走一遍 `Document::Parse` → 取值 → `Writer` 生成 → 再解析回读，留 logcat 日志；
3. 记录：解析耗时、报文大小、`HasParseError`/`GetParseError` 行为、大报文（>64 KB）时的内存表现；
4. 把日志放进本目录 `evidence/`，才算验过。

## 复现方式（先编译，再上机取证）

```bash
# 最小示例（纯头文件包 → 重点是"能编进工程 + 能解析真实报文"）
#   packages/rapidjson/example/  ui/main.json + src/logic/mainLogic.cc + Manifest.xml
fsc install && fsc build -p z20
# 部署（/tmp 劫持调试，不动 /res）——⚠️ 单次 restart；先确认没有残留 zkgui 进程
adb -s 192.168.x.x:5555 push .fsc/z20/libzkgui.so /tmp/lib/libzkgui.so
adb -s 192.168.x.x:5555 push ui/main.ftu          /tmp/ui/main.ftu
adb -s 192.168.x.x:5555 push EasyUI.cfg           /tmp/EasyUI.cfg   # startupLibPath=/tmp/lib/libzkgui.so, resPath=/tmp/ui/
adb -s 192.168.x.x:5555 shell setprop ctl.restart zkswe
adb -s 192.168.x.x:5555 shell "logcat -d | grep 'rapidjson demo'"
```

⚠️ 部署纪律（踩过）：**确认 `pidof zkgui` 只剩一个、上一次实例已退出**再 `ctl.restart`；连续快速重启会把 MI 全局 init 锁占死 → 黑屏 + 进程 D 状态、`kill -9` 无效，只能断电重启。

## 已知口径（来自包头实读，非实测）

- **纯头文件**：`libs` 为空，没有 `.a`/`.so` → 不要去找 `librapidjson`；改 Manifest 后**仍要 `fsc install`** 让 include 路径进 CMake。
- **`Document::Parse` 不抛异常**（失败返回自身，必须查 `HasParseError()` / `GetParseError()` / `GetErrorOffset()`）。
- **取值前必须判类型**：debug 下 `RAPIDJSON_ASSERT` 会直接 abort（release 下是垃圾值）→ 一律先 `IsString/IsArray/HasMember`。
- **带内嵌 `\0` 的二进制 payload** 要用 `Parse(str, length)`；默认 `Parse(const Ch*)` 要求以 `\0` 结尾。
- **大报文别用 `Document`（全量树）**，用 `Reader`（SAX）+ 自己的 handler 更省内存。
- **1.1.0 是上游老版本（2016 年线）**，与 master/新文档有行为差异 → 别照最新官方文档抄。
- **和 `base-json`/`easyui` 里的 jsoncpp（`#include <json/json.h>`）不是一套库**：项目里同时出现会重复解析逻辑，选一套用。
- Z20 上它通常由 **`base-json 3.1.0`** 依赖引入（`base::JSONObject`）。
