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
| zknet | ⏳ 待验 | — | 计划：WifiManager / NetUtils / SoftAp |
| easyui | ⏳ 待验 | — | 计划：控件/回调/定时器/页面切换最小骨架 |

## 缺口背景（为什么要补）

Z20 registry 27 个包里 **17 个完全没有 README、没有示例**（含 `easyui` 核心、`zkhardware`、`zknet`、
`mi-*`、`mbedtls`、`openssl`、`paho-mqtt3as`、`rapidjson`…），其余多数只有 1 段代码；
MCP 的包查询只能给出「一行描述 + 从 README 抓的代码块」，抓不到就只剩几条静态兜底 →
AI 拿到包后基本无从下手。本目录就是补这块。
