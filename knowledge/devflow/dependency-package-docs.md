---
id: devflow-dependency-package-docs
title: 依赖包用法文档（packages/<包>/package.yaml）怎么读、怎么查
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [Z20]
tags: []
evidence: []
---
# 依赖包用法文档（packages/<包>/package.yaml）怎么读、怎么查

> 检索导引：需求里出现「某个依赖包怎么用 / 这个包有什么 API / Manifest 该写哪个包和版本 / 包说明不全 / package.yaml / 组件包用法」时命中本文。
> 本文是**索引 + 读法**；每个包的详细文档在仓库 `packages/<包名>/` 下。

## 1. 文档在哪、长什么样

| 文件 | 内容 | 给谁看 |
|---|---|---|
| `packages/<包>/package.yaml` | **机器可读**：`id/version/platforms`（含各平台 `registry` 路径与 `verified` 状态）、`summary`、`headers`（关键头文件+用途）、`api`（类/方法签名，**逐个能在头文件里 grep 到**）、`deps`（Manifest 依赖）、`usage_cpp`（≤25 行可粘贴示例）、`gotchas`（真坑）、`verified_*`（真机实测结果+证据文件） | AI 优先读这个 |
| `packages/<包>/README.md` | 人读版：装法（Manifest 片段 + `fun install`）、API 速查表、最小示例、真机实测表、坑清单 | 人 |
| `packages/<包>/platforms.md` | 平台实测表（**只写实测过的**，没测写「未验证 + 需要什么条件」）+ 板级事实 + 复现命令 | 人/AI |
| `packages/<包>/example/` | 真机验证过的 `ui/*.json`、`src/logic/*.cc`、按键注册片段、Manifest | 直接拷 |
| `packages/<包>/evidence/` | 设备日志（`logcat` 摘录）、真机截图 | 验收 |

**约定**：`verified: null` / `status: unverified` = **没上过真机**，只有头文件/二进制层面的说明；看到 `verified_<日期>` 才是实测过的结论。

## 2. 查一个包怎么用（推荐顺序）

1. `packages/<包>/package.yaml` → 看 `summary` / `api` / `usage_cpp` / `gotchas`
2. 还不够 → `packages/<包>/README.md`（含真机实测表）→ `platforms.md`（板级差异）
3. 要直接上手 → 拷 `example/` 进工程；跑法见该包 `platforms.md` 的「复现方式」
4. 包里没有？→ 用 MCP 的 `flythings_query_package` / `flythings_list_packages` 查平台可用版本；再不行 `flythings_get_package_api`（读 registry 头文件）
5. 想看实现 → 本地 git 里按 **`lib-<包名>`** 形式找源码仓（例：`lib-networking`、`lib-ntp`、`lib-json`、`lib-civetweb-cxx`）

## 3. 目前收录（2026-09-29 首轮，Z20 为主）

- 已真机验证（Z20/108）：`zkhardware`（GPIO/过零继电器/背光）、`zknet`（WiFi 全流程 + 以太网/热点/4G 结论）、`curl-cxx`（HTTP/HTTPS/Downloader/WebSocket）、`ntp`、`mqtt-cxx`（明文/TLS/LWT/异常断线重连）、`paho-mqtt3as`、`cares`（DNS 直调）、`mbedtls`、`openssl`（TLS 直调）
- 只有说明（未上真机）：`rapidjson`、`curl`（`curl` 由 `curl-cxx` 间接验证）
- 判据：文件内有没有 `verified_<日期>` 块；`platforms.md` 表里未测的平台一律写「未验证 + 需要什么条件」
- 依赖版本按平台分叉，别照抄：**Z20 的 `openssl` = `1.1.1-w`（其他平台 `1.1.1-g`）**；**Z20/Z21 的 `curl` = `8.12.1-mbedtls`（其他平台 `8.12.1`）**；`paho-mqtt3as` / `mqtt-cxx` / `rapidjson` 本地 registry **只有 Z20 有**

## 4. 红线（踩过的）

- **不要凭记忆写包内 API**：`api.methods` 里的签名必须能在该包头文件里 grep 到（AI 写文档时同理）
- **`cacert.pem` 只认资源目录（resPath）下**：HTTPS 失败常见根因；报 `not correctly signed by the trusted CA` = CA 没找到
- **Z20 的 `paho-mqtt3as` 必须一起声明 `openssl`**，否则链接报 `BIO_read / RAND_bytes / SHA1_*`
- **改 Manifest 后必须 `fun install`**，否则包内头文件路径不进 CMake
- **部署调试别连续快速 `setprop ctl.restart zkswe`**（MI 全局 init 锁被占 → 黑屏 + D 状态进程）
