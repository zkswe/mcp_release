# packages/ —— 依赖包（registry）用法示例

> 这里放的是**厂家依赖包**（`fun install` 从 registry 装的 `easyui / zkhardware / zknet / mqtt-cxx …`）的
> **可直接照抄的用法示例**，每个包一份，**示例都在真机上跑过**（有证据），不是纸面推断。

## 和 `components/` 的区别

| | 放什么 | 谁用 |
|---|---|---|
| `components/` | **我方自研可复用模块**（BLEn 门面、字库、ui_v1 控件包…） | 自己要复用代码 |
| `packages/`（本目录） | **厂家注册表依赖包的用法**：装法、API 速查、最小示例、真机实测、坑 | AI/开发者拿到包后「怎么用」 |

## 目录规范（一个包一个目录）

```
packages/<包名>/
  README.md        # 包信息 + 装法 + API 速查 + 最小示例代码 + 真机实测 + 坑
  platforms.md     # 逐平台实测表（平台/版本/结论/证据），没测的写「未验证」不猜
  example/         # 最小可跑工程的可拷片段（ui json + logic + 回调注册），三步能跑起来
  evidence/        # 真机证据：截图 + logcat 摘录（可复现的判据）
```

## 状态

| 包 | 状态 | 实测平台 | 备注 |
|---|---|---|---|
| zkhardware | ✅ 已验（2026-09-28） | Z20（SSD20X 480×480，easyui 2.6.0） | 蜂鸣器/亮度/ADC/GPIO/过零 IO |
| zknet | ✅ 已验（2026-09-29） | Z20（SSD20X 480×480，86 面板） | WiFi 全流程 + 只读面；详见 `zknet/platforms.md` |
| easyui | ⏳ 待验 | — | 计划：控件/回调/定时器/页面切换最小骨架 |
| **nanovg** | ✅ **已上真机**（2026-10-03，功能矩阵 **12/12**，`avg 2.483 ms/帧`，见 `nanovg/evidence/v85x-device/`）；⛔ 渐变族失效 / 贴图不平铺（已由独立探针证实）；**唯一缺 `example/` 的包** | — | 服务端**没有** v85x 包 → 本仓自带 `packages/nanovg/{include,lib/v85x}`；符号级已核（85 条 nvg*），20 条字体 API 未编。见 `nanovg/README.md` |

## 缺口背景（为什么要补）

Z20 registry 27 个包里 **17 个完全没有 README、没有示例**（含 `easyui` 核心、`zkhardware`、`zknet`、
`mi-*`、`mbedtls`、`openssl`、`paho-mqtt3as`、`rapidjson`…），其余多数只有 1 段代码；
MCP 的包查询只能给出「一行描述 + 从 README 抓的代码块」，抓不到就只剩几条静态兜底 →
AI 拿到包后基本无从下手。本目录就是补这块。

## 包卡完整度状态（2026-09-29 二次复核，审查报告 §2.3 / P1-⑤ 已补）

> 口径：**规范要求有的东西，要么补齐，要么显式标注「待补 + 计划」，不允许静默不一致。**
> 本表 = 补完之后的状态；**没实测的平台在 `platforms.md` 里写「未验证」+ 所需条件，不编数据**。

| 包 | package.yaml | README | platforms.md | example/ | evidence/ |
|---|---|---|---|---|---|
| zkhardware / zknet | ✅ | ✅ | ✅ | ✅ | ✅ |
| curl-cxx | ✅ | ✅ | ✅（Z20 ✅ 全通 / Z21 ✅；F133-F136-T113EMMC-V85X 未验证） | ✅（GET·POST·HTTPS·Downloader·WebSocket + AUTO） | ✅ |
| ntp | ✅ | ✅ | ✅（Z20 ✅ / Z21 ✅ 且是 Z21 的 HTTPS 前置；其余未验证） | ✅（阻塞同步·异步同步·读时间 + AUTO） | ✅ |
| mqtt-cxx | ✅ | ✅ | ✅（Z20 ✅ 含 MQTTS/LWT/断线重连；Z21 无此包=未验证） | ✅（发布·订阅回显·遗嘱·MQTTS + AUTO） | ✅ |
| paho-mqtt3as | ✅ | ✅ | ✅（Z20 🟡 经 mqtt-cxx 间接可用；其余平台无此包=未验证） | ✅（C API 直调示例，**路径未上机**已标注） | ✅ |
| cares | ✅ | ✅ | ✅（Z20 ✅ 直调；Z21 只有间接痕迹=未验证） | ✅（单域名·5 域名批量 + AUTO） | ✅ |
| mbedtls | ✅ | ✅ | ✅（Z20 ✅ 直调；Z21 🟡 经 curl 间接；其余未验证） | ✅（握手·握手+HTTP GET + AUTO） | ✅ |
| openssl | ✅ | ✅ | ✅（Z20 ✅ 直调 verify=OK；Z21 是 1.1.1-g=未验证直调） | ✅（握手·握手+HTTP GET + AUTO） | ✅ |
| curl | ✅ | ✅ | ✅（Z20/Z21 🟡 **间接**可用，`package.yaml` 保持 `verified: null`） | ✅（easy 直调示例，**未上机**已标注） | ✅ |
| rapidjson | ✅ | ✅ | ✅（**全部未验证** + 说明为什么 + 怎么补） | ✅（解析/生成示例，**未上机**已标注） | ✅（本目录只有 `README.md` 说明「为什么没有证据」，**不放伪造日志**） |

- 包的**可运行实现**仍在 `demos/` 里（`net-stack-verify-z20` / `net-stack-advanced-z20` / `net-direct-tls-z20`，都真机验过）；
  `example/` 是从这些 demo 抽出来的最小片段（`example/README.md` 里写明来源与步骤）。
- **三处「未上机」的 example 已显式标注**：`paho-mqtt3as`（直调 C API 路径）、`curl`（直调 easy 路径）、`rapidjson`（纯头文件包）——
  它们的 API 形态来自包头实读，**真机数据待补**；`platforms.md` 与 `example/README.md` 两处都写了「要标 ✅ 需做什么」。
- `components/mp_transfer` 的四件套缺失**已于本轮补齐**：新增 `platforms.md`（逐平台矩阵 + 协议口径 + 前置条件 + 三层验收 + 已知边界）
  与 `example/`（`README.md` + `mp_transfer_min_example.cc`），并在 `components/README.md` 的模块表里登记。
