---
id: devflow-builtin-packages
title: 内置依赖包总览（包键 / 通用包 / 包名索引）
category: devflow
status: review
confidence: manual
verified_at: 2026-09-17
stale_days: 180
origin: derived
source: 由 package_catalog.json 派生（scripts/gen_package_catalog_doc.py）；包名与版本逐字取自注册表
needs_evidence: false
platforms: [A33NOR, F133, F135, H500S, T113, V85X, Z20, Z21, Z235X, Z261, Z6S]
tags: [内置包, 依赖包, 有哪些包, 包清单, package 包, 版本, 加包, 依赖, MQTT 包, openssl 版本,
       curl, zlib, poco, easyui 版本, 包键, PACKAGE_KEYS, 选型 现成包]
evidence:
  - cmd: python scripts/gen_package_catalog_doc.py --check
    expect: rc=0（本页与 package_catalog.json 一致）
---

# 内置依赖包总览

> 检索导引：问「有没有现成的 XXX 包 / 内置了哪些包 / openssl·curl·zlib·MQTT 是什么版本 /
> 这平台上能用哪些包 / 怎么加包」→ 本文（生态总览）；
> 精确查询走 op：`flythings_list_packages`（列包）/ `flythings_query_package`（查单包版本）
> / `flythings_get_package_api`（看包内 API）/ `flythings_add_package`（加进工程 Manifest）。
> 用法与解析顺序（本地 registry → 离线 catalog → 在线 semver）见
> `knowledge/devflow/dependency-package-docs.md`。
>
> ⚠️ **本页是派生物，不要手改**（由 `package_catalog.json` 派生，`--check` 进闸门）。
> 包键含平台变体与别名（`f136`→F135、`v85xemmc`→V85X），查询时自动折算，不用自己换算。

## 1. 包键 → 芯片 / 包数

| 包键 | 芯片 | 平台（规范化） | 包数 |
|---|---|---|---|
| `a33nor` | — | A33NOR | 13 |
| `f133` | F133-B / F133-MX | F133 | 46 |
| `f133emmc` | F133-B / F133-MX | F133 | 11 |
| `f136` | F135 / F136 | F135 | 52 |
| `f136emmc` | F135 / F136 | F135 | 49 |
| `h500s` | — | H500S | 16 |
| `t113` | T113 / T113-S3 / T113-S4 / T113-i | T113 | 41 |
| `t113emmc` | T113 / T113-S3 / T113-S4 / T113-i | T113 | 71 |
| `t113stdcxx` | T113 / T113-S3 / T113-S4 / T113-i | T113 | 46 |
| `v85x` | V553 / V851 / V853 / V851S / V851S3 / V853S | V85X | 62 |
| `v85xemmc` | V553 / V851 / V853 / V851S / V851S3 / V853S | V85X | 48 |
| `z20` | SSD201 / SSD202D / SSD203 | Z20 | 92 |
| `z21` | SSD210 / SSD212 / SSD222 / SSD222D | Z21 | 67 |
| `z235x` | SSD2355 | Z235X | 17 |
| `z261` | SSD261Q | Z261 | 59 |
| `z6s` | — | Z6S | 1 |

> 包键按 SoC 变体分（`v85x` vs `v85xemmc`、`f133` vs `f133emmc`…），**与平台规范名不是简单大小写关系**；别名折算见 `platforms.py`。

## 2. 通用包（跨 ≥8 个包键，选型优先看这批）

| 包 | 说明 | 版本 | 覆盖 |
|---|---|---|---|
| `base-utility` | 提供一些基础通用功能 | 10.9.3（各键不同：a33nor 10.4.0、f133 10.10.2、f133emmc 10.4.0） | 15 键 |
| `easyui` | — | 3.0.0（各键不同：a33nor 0.0.0、f133 2.8.0、f133emmc 2.3.0） | 15 键 |
| `log` | — | 1.0.0（各键不同：a33nor 0.0.0、f133 1.0.0、f133emmc 1.0.0） | 15 键 |
| `openssl` | — | 3.0.12（各键不同：a33nor 1.1.1-g、f133 1.1.1-g、f133emmc 1.1.1-g） | 15 键 |
| `z` | zlib 压缩与解压 | 1.2.11 | 15 键 |
| `cares` | — | 1.17.2 | 14 键 |
| `curl` | — | 8.12.1（各键不同：a33nor 7.88.1、f133 8.12.1、f133emmc 7.88.1） | 14 键 |
| `watchdog` | 系统看门狗 | 1.0.3（各键不同：a33nor 1.0.2、f133 1.0.3、f136 1.0.3） | 14 键 |
| `zkhardware` | — | 1.2.0（各键不同：f133 1.1.0、f133emmc 1.1.0、f136 1.0.0） | 14 键 |
| `zknet` | — | 1.1.0（各键不同：f133 1.1.0、f133emmc 1.0.0、f136 1.1.0） | 14 键 |
| `curl-cxx` | libcurl使用实例 | 9.0.1（各键不同：f133 11.0.0、f133emmc 6.1.0、f136 11.0.0） | 12 键 |
| `ntp` | NTP客户端，同步网络时间 | 2.1.1（各键不同：f133 2.1.1、f136 2.1.1、f136emmc 2.1.1） | 12 键 |
| `base-json` | rapidjson wrapper | 3.1.0（各键不同：f133 3.1.0、f136 3.1.0、f136emmc 3.1.0） | 11 键 |
| `jpeg` | — | 9.1.0 | 11 键 |
| `png` | — | 1.2.56 | 11 键 |
| `rapidjson` | — | 1.1.0 | 11 键 |
| `civetweb` | — | 1.17.0（各键不同：f133 1.16.1、f136 1.16.1、f136emmc 1.16.1） | 10 键 |
| `civetweb-cxx` | HTTP服务端 | 4.1.3-test2（各键不同：f133 4.1.3、f136 4.1.3、f136emmc 4.1.3） | 10 键 |
| `ffmpeg` | — | 4.1.9-media（各键不同：f133 4.1.9-media、f136 4.1.9-extract-h264、f136emmc 4.1.9-extract-h264） | 10 键 |
| `transfer-protocols` | 处理协议的接收和发送 | 3.0.0（各键不同：f133 3.0.0、f136 3.0.0、f136emmc 3.0.0） | 10 键 |
| `freetype` | — | 2.5.5（各键不同：f133 2.5.5、f136 2.5.5、f136emmc 2.5.5） | 9 键 |
| `sqlite3` | sqlite3数据库 | 3.7.11 | 9 键 |
| `zkupgrade` | — | 1.0.0 | 9 键 |
| `ini` | ini配置文件读写 | 0.0.1 | 8 键 |
| `paho-mqtt3as` | — | 1.3.13 | 8 键 |
| `utf8conv` | 转换UTF8编码与GBK编码 | 1.1.1（各键不同：a33nor 1.1.1、f133 1.1.1、t113 1.1.1） | 8 键 |

> 版本逐字取自注册表；同一包在不同包键上版本可能不同（上表差异只列前 3 个键），**要精确版本请用 `flythings_query_package`**。

## 3. 包名索引（全 166 个，按覆盖度分层）

**通用（≥8 键，26 个）**：`base-json`、`base-utility`、`cares`、`civetweb`、`civetweb-cxx`、`curl`、`curl-cxx`、`easyui`、`ffmpeg`、`freetype`、`ini`、`jpeg`、`log`、`ntp`、`openssl`、`paho-mqtt3as`、`png`、`rapidjson`、`sqlite3`、`transfer-protocols`、`utf8conv`、`watchdog`、`z`、`zkhardware`、`zknet`、`zkupgrade`

**常见（3~7 键，69 个）**：`Poco`、`Poco-http`、`aec`、`animations`、`apc`、`audio-utility`、`av`、`awh264player`、`awjpegdecoder`、`awmetadataretriever`、`base-http-client`、`ble`、`blehid`、`boost`、`btstack`、`ext4`、`ext_widgets`、`fribidi`、`frpc`、`fvad`、`fx`、`gatt`、`gumbo`、`h264-player`、`hostapd-wpa_supplicant`、`html-builder`、`imageinfo`、`ktp`、`lrtp`、`lunasvg`、`mbedtls`、`mi_ai`、`mi_aio`、`mi_ao`、`mi_common`、`mi_disp`、`mi_panel`、`mi_sys`、`mp4v2`、`mqtt-cxx`、`nanovg`、`networking`、`openh264`、`opus`、`paho-mqtt3c`、`pinyin`、`plutovg`、`rapidxml`、`result`、`rtp`、`rtsp`、`srt`、`tag`、`uClibc++`、`uav-network`、`unibreak`、`usb`、`webp`、`webpdemux`、`webrtc-audio-processing`、`webview`、`wise_enum`、`yuv`、`zint`、`zip`、`zkaudio`、`zkmbr`、`zkmedia`、`zkmisc`

**个别包键独有（<3 键，71 个）**：`CTML`、`OutdoorExample`、`ad-mcu-proto`、`ai`、`amqpcpp`、`awface`、`blend2d`、`cam_os_wrapper`、`cdx`、`cjson`、`cobs`、`cppzmq`、`cus3a`、`cutils`、`display_utility`、`e2fsprogs`、`eigen`、`ev`、`event`、`faac`、`face-manager`、`flatbuffers`、`gemmlowp`、`gif`、`giflib`、`glibcxx-headers`、`gnutls`、`hostapd`、`ir-camera`、`ispalgo`、`kcp`、`liteui`、`ltp`、`mad`、`md5`、`mi-module`、`mi_gfx`、`mi_hdmi`、`mi_isp`、`mi_jpd`、`mi_ldc`、`mi_scl`、`mi_sensor`、`mi_vdec`、`mi_vif`、`mosquitto`、`mpp-middleware`、`multi-channel-audio-recorder`、`nexus`、`npu`、`paho-mqtt3a`、`paho-mqtt3cs`、`parsesps`、`rabbitmq-c`、`reed-solomon`、`rtmp-cxx`、`ruy`、`sdk-tmp-20240221`、`sensor`、`simple-player`、`snappy`、`sodium`、`st_sensor`、`test`、`test-pkg`、`tinyxml2`、`uav-camera`、`utf8sconv`、`webrtc-aec`、`zeromq`、`zkcarotp`

> 这批里 113 个包在注册表里**没有一句话说明**（多为示例工程/内部件）。要确认某个包能干什么，用 `flythings_get_package_api` 看它导出的 API。

## 4. 怎么用（选型 → 加包 → 看 API）

1. **先看有没有**：本页 §2/§3，或 `flythings_list_packages(platform=...)`（列该平台全部包）。
2. **确认版本与依赖**：`flythings_query_package(name, platform)`；版本解析顺序 = 本地 registry → 离线 catalog → 在线 semver。
3. **看包内 API**：`flythings_get_package_api(name)`——**不要凭记忆写包内 API**。
4. **加进工程**：`flythings_add_package(project_root, id, version)`（自动改 Manifest + `fun install`）；只想要推荐清单不动盘就用 `flythings_manifest(features=...)`。

> ⚠️ 约束：Manifest 必须声明传递依赖（例：用 `mqtt-cxx` 要连 `paho-mqtt3as` + `openssl` 一起声明，否则链接报 `BIO_read / RAND_bytes / SHA1_*` undefined）。判据见 `knowledge/devflow/dependency-package-docs.md`。
