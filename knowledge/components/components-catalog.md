---
id: components-components-catalog
title: 可复用组件目录（components/ 树派生：形态 / 四件套 / 平台 / 依赖 / 示例）
category: components
status: review
confidence: manual
verified_at: 2026-10-03
stale_days: 180
origin: derived
source: 由 components/ 树扫描派生（scripts/gen_components_catalog.py）；平台可用性取自 platform_capabilities.json，依赖取自各组件 Manifest.xml
needs_evidence: false
platforms: []
tags: [可复用组件, 组件目录, 有没有现成的, 复用库, 字体, 图标, 图表, 日历, 蓝牙, 传图, 高斯模糊, 缓存, 多屏同步, ui_v1, ble, fonts]
evidence:
  - cmd: python scripts/gen_components_catalog.py --check
    expect: rc=0（本页与 components/ 树及各注册表一致）
---

# 可复用组件目录

> 口语问法直达：有没有现成的组件 / 组件目录 / 「可复用组件、组件目录、有没有现成的、复用库、字体、图标、图表、日历」这些有吗 /这块平台能用哪些组件 / 怎么把组件接进工程。
>
> ⚠️ **本页是派生物，不要手改**（由 `components/` 这棵树扫描派生，`--check` 进闸门）。落地规范（四件套、模块形态、代码规范、新增模块 checklist）见 `components/README.md` 的 §7。
> 依赖读各组件 `Manifest.xml`，平台可用性读 `platform_capabilities.json` —— 两处都不会在本页编一份。

## 1. 组件总表

| 组件 | 形态 | 一句话 | 平台 | 依赖包 | 示例 |
|---|---|---|---|---|---|
| **album_upload** | 源码型 | 相册传图（手机 → 面板）业务接线层 zk::album | F135、T113、V85X、Z20、Z21 | `easyui`、`log`、`base-utility` | `components/album_upload/example` |
| **ble** | 二进制型 | BLE 门面 zk::ble v0.2（头文件 + 静态库发布） | F133、T113、V85X、Z20、Z21 | `btstack`、`easyui`、`base-utility`、`log`、`zkhardware`、`gatt` | `components/ble/example` |
| **blend2d** | 源码型 | 离屏矢量出图 zk::b2d v0.1（头 + 门面源码 + 两个库档） | F133、F135、T113、V85X、Z20、Z21 | `easyui`、`log` | `components/blend2d/example` |
| **blur** | 源码型 | 高斯模糊（铺底 / 封面背景）v0.1.0 | F133、F135、T113、V85X、Z20、Z21 | 无 | `components/blur/example` |
| **fonts** | 资产/工具型 | 字库模块：思源黑体三版本 + 设备字体自检 | （见 platforms.md） | 无 | — |
| **ha_bridge** | 源码型 | Home Assistant / MQTT 桥 + 继电器语义 v0.1.0 | F133、F135、T113、V85X、Z20、Z21 | `mqtt-cxx`、`paho-mqtt3as`、`openssl`、`base-json`、`base-utility`、`log`、`rapidjson` | `components/ha_bridge/example` |
| **icons** | 资产/工具型 | 图标资产库（vendor Tabler + 少量自绘，单色烘焙 PNG，任意分辨率） | ALL、F133、T113、V85X、Z20、Z21 | 无 | `components/icons/example` |
| **imagecache** | 源码型 | 列表封面「已解码位图」缓存 v0.1.0 | F133、F135、T113、V85X、Z20、Z21 | `easyui`、`log` | `components/imagecache/example` |
| **mp_transfer** | 源码型 | 小程序传图/视频（设备端接收参考实现） | F133、T113、V85X、Z20、Z21 | `base-utility`、`log` | `components/mp_transfer/example` |
| **ui_v1/Calendar** | 源码型 | 日历选择器 zk::ui_v1::Calendar | T113、V85X、Z20 | `easyui`、`log`、`zkhardware`、`zknet`、`base-utility` | `components/ui_v1/Calendar/example` |
| **ui_v1/Chart** | 源码型 | 图表集合 zk::ui_v1::Chart | T113、V85X、Z20 | `easyui`、`log`、`zkhardware`、`zknet`、`base-utility` | `components/ui_v1/Chart/example` |
| **ui_v1/RadButton** | 源码型 | 带倒角按钮 zk::ui_v1::RadButton | F133、F135、T113、V85X、Z20、Z21 | `easyui`、`log`、`zkhardware`、`zknet`、`base-utility` | `components/ui_v1/RadButton/example` |
| **ui_v1/_mapping/TabView** | 源码型 | 页签页容器 zk::ui_v1::TabView | T113、V85X、Z20 | `easyui`、`log`、`zkhardware`、`zknet`、`base-utility` | `components/ui_v1/_mapping/TabView/example` |
| **vinyl** | 源码型 | 黑胶唱片自转（封面按角度旋转上屏）组件 | F133、F135、T113、V85X、Z20、Z21 | `easyui`、`log`、`nanovg` | `components/vinyl/example` |
| **wall_sync** | 源码型 | 多屏拼接 / 视频墙「跨设备同步」（zk::wall） | F133、F135、T113、V85X、Z20、Z21 | `rapidjson`、`base-utility`、`easyui`、`log`、`ffmpeg`、`mi-module`、`ntp` | `components/wall_sync/example` |

## 2. 组件明细（怎么接进工程）

### 2.1 源码型 —— 拷 `include/` + `src/` 进工程（推荐起步）

#### album_upload

- **用途**：相册传图（手机 → 面板）业务接线层 zk::album
- **平台**：F135、T113、V85X、Z20、Z21
- **依赖包**：`easyui`、`log`、`base-utility`
- **示例工程**：`components/album_upload/example`
- **文档**：`components/album_upload/README.md`

#### blend2d

- **用途**：离屏矢量出图 zk::b2d v0.1（头 + 门面源码 + 两个库档）
- **平台**：F133、F135、T113、V85X、Z20、Z21
- **依赖包**：`easyui`、`log`
- **预编译库平台**：z20、z20-neon
- **示例工程**：`components/blend2d/example`
- **文档**：`components/blend2d/README.md`

#### blur

- **用途**：高斯模糊（铺底 / 封面背景）v0.1.0
- **平台**：F133、F135、T113、V85X、Z20、Z21
- **依赖包**：无
- **示例工程**：`components/blur/example`
- **文档**：`components/blur/README.md`

#### ha_bridge

- **用途**：Home Assistant / MQTT 桥 + 继电器语义 v0.1.0
- **平台**：F133、F135、T113、V85X、Z20、Z21
- **依赖包**：`mqtt-cxx`、`paho-mqtt3as`、`openssl`、`base-json`、`base-utility`、`log`、`rapidjson`
- **示例工程**：`components/ha_bridge/example`
- **文档**：`components/ha_bridge/README.md`

#### imagecache

- **用途**：列表封面「已解码位图」缓存 v0.1.0
- **平台**：F133、F135、T113、V85X、Z20、Z21
- **依赖包**：`easyui`、`log`
- **示例工程**：`components/imagecache/example`
- **文档**：`components/imagecache/README.md`

#### mp_transfer

- **用途**：小程序传图/视频（设备端接收参考实现）
- **平台**：F133、T113、V85X、Z20、Z21
- **依赖包**：`base-utility`、`log`
- **示例工程**：`components/mp_transfer/example`
- **文档**：`components/mp_transfer/README.md`

#### ui_v1/Calendar

- **用途**：日历选择器 zk::ui_v1::Calendar
- **平台**：T113、V85X、Z20
- **依赖包**：`easyui`、`log`、`zkhardware`、`zknet`、`base-utility`
- **示例工程**：`components/ui_v1/Calendar/example`
- **文档**：`components/ui_v1/Calendar/README.md`

#### ui_v1/Chart

- **用途**：图表集合 zk::ui_v1::Chart
- **平台**：T113、V85X、Z20
- **依赖包**：`easyui`、`log`、`zkhardware`、`zknet`、`base-utility`
- **示例工程**：`components/ui_v1/Chart/example`
- **文档**：`components/ui_v1/Chart/README.md`

#### ui_v1/RadButton

- **用途**：带倒角按钮 zk::ui_v1::RadButton
- **平台**：F133、F135、T113、V85X、Z20、Z21
- **依赖包**：`easyui`、`log`、`zkhardware`、`zknet`、`base-utility`
- **示例工程**：`components/ui_v1/RadButton/example`
- **文档**：`components/ui_v1/RadButton/README.md`

#### ui_v1/_mapping/TabView

- **用途**：页签页容器 zk::ui_v1::TabView
- **平台**：T113、V85X、Z20
- **依赖包**：`easyui`、`log`、`zkhardware`、`zknet`、`base-utility`
- **示例工程**：`components/ui_v1/_mapping/TabView/example`
- **文档**：`components/ui_v1/_mapping/TabView/README.md`

#### vinyl

- **用途**：黑胶唱片自转（封面按角度旋转上屏）组件
- **平台**：F133、F135、T113、V85X、Z20、Z21
- **依赖包**：`easyui`、`log`、`nanovg`
- **示例工程**：`components/vinyl/example`
- **文档**：`components/vinyl/README.md`

#### wall_sync

- **用途**：多屏拼接 / 视频墙「跨设备同步」（zk::wall）
- **平台**：F133、F135、T113、V85X、Z20、Z21
- **依赖包**：`rapidjson`、`base-utility`、`easyui`、`log`、`ffmpeg`、`mi-module`、`ntp`
- **示例工程**：`components/wall_sync/example`
- **文档**：`components/wall_sync/README.md`

### 2.2 二进制型 —— 按目标平台取 `lib/<平台>/`，别拿别平台的头凑

#### ble

- **用途**：BLE 门面 zk::ble v0.2（头文件 + 静态库发布）
- **平台**：F133、T113、V85X、Z20、Z21
- **依赖包**：`btstack`、`easyui`、`base-utility`、`log`、`zkhardware`、`gatt`
- **预编译库平台**：f133、v85x、z20、z21
- **示例工程**：`components/ble/example`
- **机器自检**：`scripts/verify_lib_symbols.py`
- **文档**：`components/ble/README.md`

### 2.3 资产/工具型 —— 不写代码，按 README 一条命令用

#### fonts

- **用途**：字库模块：思源黑体三版本 + 设备字体自检
- **平台**：见 `components/fonts/platforms.md`
- **依赖包**：无
- **文档**：`components/fonts/README.md`

#### icons

- **用途**：图标资产库（vendor Tabler + 少量自绘，单色烘焙 PNG，任意分辨率）
- **平台**：ALL、F133、T113、V85X、Z20、Z21
- **依赖包**：无
- **示例工程**：`components/icons/example`
- **文档**：`components/icons/README.md`

## 3. 分组与索引页

| 目录 | 性质 | 成员 |
|---|---|---|
| `components/ui_v1` | 分组 | `ui_v1/Calendar`、`ui_v1/Chart`、`ui_v1/RadButton`、`ui_v1/_mapping/TabView` |
| `components/ui_v1/_mapping` | 分组 | `ui_v1/_mapping/TabView` |
| `components/ui_v1/examples` | 索引页 | — |

## 4. 已登记的缺口（不是漏件，是登记在案的形态变体）

- **`mp_transfer`**（缺 include，登记于 2026-10-03）：公开头就在 src/mp_transfer/*.h —— 本模块的用法是「拷源文件」（README §怎么用、Manifest 注释），没有做 include/ + lib/ 的库化封装。属**已登记的形态变体**。
- **`fonts`**（不进 platform_capabilities（无平台矩阵表），登记于 2026-10-03）：平台可用性写在 platforms.md 的逐平台正文里（V85X 已实测、其余未验证），没有「平台 × 能力」矩阵表，所以不进 platform_capabilities.json（资产/工具型，用法是"一条命令体检/投递"）。

> 口径：新增缺口**不会**被自动放行 —— `components_catalog.validate()` 只认登记过的（`DECLARED_GAPS`，每条要写原因与日期），其余一律判失败。所以这份缺口清单是有账可查的，不是「坏了也不报」。

## 5. 把一个组件接进工程

1. **先查**：本页 §1/§2（有没有现成的、形态、平台、依赖、示例在哪）；
   要精确问「某平台能用哪些组件」用 `flythings_knowledge_search`，或直接看 `platform_capabilities.json` 派生的平台能力矩阵页。
2. **再看示例**：每个组件都有 `example/`（能拷进工程就跑）——先照示例跑通，再改。
3. **源码引入**：拷 `include/` + `src/` 进工程；**依赖包引用**（组件已注册进包仓库时）：一行 `<package id="<组件>" version="x.y.z"/>`。
4. **声明依赖**：把本页「依赖包」那列写进工程 `Manifest.xml`（或 `fun.json`，其优先级更高），**改完必须重跑 `fun install`**（否则新包的 include 路径进不了 CMake）。
5. **换平台先查 `platforms.md`**：没实测的写的就是 `未验证`，别当结论用。
