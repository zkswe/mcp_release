---
id: devflow-platform-capability-matrix
title: 平台能力矩阵（组件 × 平台 可用性，唯一真源派生）
category: devflow
status: review
confidence: manual
verified_at: 2026-10-03
stale_days: 180
origin: derived
source: 由 platform_capabilities.json 派生（scripts/gen_platform_cap_doc.py）；表格内容与注册表逐字节一致
needs_evidence: false
platforms: [F133, F135, T113, V85X, Z20, Z21]
tags: [平台支持, 组件可用性, 能不能用, 选型, Z20, Z21, F133, F135, T113, V85X, Z235X, 跨平台移植,
       蓝牙 BLE 平台, 图标库平台, 双缓冲 blend2d, 视频层, 组件矩阵, capability matrix]
evidence:
  - cmd: python scripts/gen_platform_cap_doc.py --check
    expect: rc=0（本页与 platform_capabilities.json 一致）
---

# 平台能力矩阵（组件 × 平台 可用性）

> 检索导引：问「这组件在 Z20 / F133 / V85X / T113 上能不能用」「某设备上能跑哪些组件」
> 「跨平台移植前要查什么」→ 本文。
> 检索词：平台支持 / 组件可用性 / 能不能用 / 选型 / Z20 / Z21 / F133 / F135 / T113 / V85X / Z235X /
> 跨平台 / 能力矩阵 / capability matrix。
>
> ⚠️ **本页是派生物，不要手改**（由 `platform_capabilities.json` 派生，`--check` 进闸门）；
> 要改能力请改注册表。各组件 `components/*/platforms.md` 里的矩阵表同源派生，那几页另有原理/坑/验收方法。
> 平台别名（F136→F135、T113EMMC→T113）查询时自动折算，不用自己换算。

## 1. 平台 → 可用组件（答「这台设备上能跑什么」）

| 平台 | 组件数 | 组件 |
|---|---|---|
| **Z20** | 15 | album_upload / ble / blend2d / blur / ha_bridge / icons / imagecache / mp_transfer / ui_v1 / ui_v1/Calendar / ui_v1/Chart / ui_v1/RadButton / ui_v1/_mapping/TabView / vinyl / wall_sync |
| **Z21** | 12 | album_upload / ble / blend2d / blur / ha_bridge / icons / imagecache / mp_transfer / ui_v1 / ui_v1/RadButton / vinyl / wall_sync |
| **F133** | 11 | ble / blend2d / blur / ha_bridge / icons / imagecache / mp_transfer / ui_v1 / ui_v1/RadButton / vinyl / wall_sync |
| **F135** | 9 | album_upload / blend2d / blur / ha_bridge / icons / imagecache / ui_v1/RadButton / vinyl / wall_sync |
| **T113** | 15 | album_upload / ble / blend2d / blur / ha_bridge / icons / imagecache / mp_transfer / ui_v1 / ui_v1/Calendar / ui_v1/Chart / ui_v1/RadButton / ui_v1/_mapping/TabView / vinyl / wall_sync |
| **V85X** | 15 | album_upload / ble / blend2d / blur / ha_bridge / icons / imagecache / mp_transfer / ui_v1 / ui_v1/Calendar / ui_v1/Chart / ui_v1/RadButton / ui_v1/_mapping/TabView / vinyl / wall_sync |
| **Z235X** | 1 | icons |
| **ALL** | 1 | icons |

> `ALL` = 该组件声明「全平台通用」（如图标库）。别名查询等价：查 `F136` = 查 `F135`。
>
> **验收口径 · ui-controls-single-platform**：UI 控件（ui_v1/*）的行为由 easyui 运行库提供、组件本身没有平台分支 —— 只做 **V85X 单平台代表验收**；其余平台在表里标 ➖（不写「未验证」，也不再逐台排期）（2026-10-03 定）
> 为什么：逐台复验的边际信息量低（同代 easyui 的头文件面已核对一致）、成本高（每台都要一轮真机）；V85X 覆盖面最广，作为代表平台
> 适用范围：只适用于本条列出的组件；其它组件的未验证项照旧（要验或要登记缺口）

## 2. 组件 → 覆盖平台（答「这组件能上哪些平台」）

| 组件 | 覆盖平台 |
|---|---|
| `album_upload` | F135 / T113 / V85X / Z20 / Z21 |
| `ble` | F133 / T113 / V85X / Z20 / Z21 |
| `blend2d` | F133 / F135 / T113 / V85X / Z20 / Z21 |
| `blur` | F133 / F135 / T113 / V85X / Z20 / Z21 |
| `ha_bridge` | F133 / F135 / T113 / V85X / Z20 / Z21 |
| `icons` | ALL / F133 / T113 / V85X / Z20 / Z21 |
| `imagecache` | F133 / F135 / T113 / V85X / Z20 / Z21 |
| `mp_transfer` | F133 / T113 / V85X / Z20 / Z21 |
| `ui_v1` | F133 / T113 / V85X / Z20 / Z21 |
| `ui_v1/Calendar` | T113 / V85X / Z20 |
| `ui_v1/Chart` | T113 / V85X / Z20 |
| `ui_v1/RadButton` | F133 / F135 / T113 / V85X / Z20 / Z21 |
| `ui_v1/_mapping/TabView` | T113 / V85X / Z20 |
| `vinyl` | F133 / F135 / T113 / V85X / Z20 / Z21 |
| `wall_sync` | F133 / F135 / T113 / V85X / Z20 / Z21 |

## 3. 逐组件能力矩阵（原样引用注册表，各组件 `platforms.md` 同源）

### album_upload

> 文件：`components/album_upload/platforms.md`
> 口径：> 「未取证」的准确含义：**没人按本模块 `example/` 的形态在目标机器上把对应环节跑过一遍**。 > Z20 上已于 2026-09-30 按 `example/` 形态跑过一轮（§1.6）——仅剩「手机微信真扫」一环；其它平台仍为❌。

| 平台 | 可用性 | 依据 | 备注 |
|---|---|---|---|
| **Z20** | ✅ **组件形态已在 Z20 真机跑通**（2026-09-30，<验收机IP>:5555，480×480 zkgui 工程）；来源工程 `SmartPanel_HA` 亦在 Z20 面板跑过 | 组件形态：`temp/verify71/album_zkgui` 真机验收（§1.6，4 条判据全过 + 还原复核）；来源工程：`fun build -p Z20` + 推真机（`11_相册上传.png`）；协议侧口径见 `components/mp_transfer/platforms.md` | **微信小程序真机扫码那一环仍无取证**（本机无手机/小程序）；用协议等价 PC 客户端代跑「发图→落盘→回调」（§1.6 判据 d） |
| Z21 / T113 / T113EMMC / V85X / F135 / F136 | ❌ 未取证 | — | 先看 §3 前置条件；⚠️ **Z21 没有 `/mnt/sdnand`**（只有 `/mnt/extsd`、`/mnt/usb1`）→ 落盘目录必须换（该事实为 2026-09-29 Z21 实测记录） |

### ble

> 文件：`components/ble/platforms.md`
> 口径：> 口径修正（2026-09-13）：Z20/Z21 **是支持 BLE 的**（但仅 AIC 8800DL 模组有 BLE），电子价签 tag 本就跑在 BLE 方案上。 > 模块侧已预留 **AIC 分支**（H4 + 流控 + 无校验，参数自动判定，`Config.flowcontrol/parity` 可覆盖）， > 剩余阻塞是 **该平台能否拿到 btstack 包**与 **串口/上电节点的实测值**。

| 平台 | 可用性 | BT 模组 | BT 串口 | 传输/校验 | 上电节点 | 预初始化 | 备注 |
|---|---|---|---|---|---|---|---|
| **F133**（RISC-V） | ✅ 可用（链路最干净） | 非 Realtek 类 | `/dev/ttyS1` | H5 + 无校验 | 无 | 不需要 | 扫描类场景首选；`projects/BTHomeTempHum-F133` 是范本 |
| **V85X**（V851 系列） | ✅ 可用（坑最多） | **RTL8733BS** | `/dev/ttyS2` | H5 + **偶校验 8E1**+ 无流控 | `state_bt`（出厂 off） | **必须**（Realtek 8733bs） | 需 `setPreinitHook()` 挂 rtk_init |
| **Z20 / Z21** | 🟡 支持（**gatt 后端，主从双角色**，真机跑通） | AIC USB 模组（`aic_btusb.ko`） | 无串口（USB HCI） | 走 `gatt 1.0.0`（BlueZ 用户态，不经 H4/H5 参数） | hci0（`hciconfig hci0 up`） | 不需要（驱动 + hciconfig 拉起） | ⚠️ 中心+外设都真机跑过；见 §0.3 / §0.4 |
| T113 | ❌ gatt 后端已就绪（**未真机**） | AIC USB 模组（同 Z20 族） | 无串口（USB HCI） | 走 `gatt 1.0.0` | hci0 | 不需要 | 包在（z20/z21/t113/t113emmc/v85x 均有）；额外要 `hcitool cmd 0x03 0x0003` 拉起 LE/BR-EDR |

### blend2d

> 文件：`components/blend2d/platforms.md`

| 平台 | 可用性 | 依据 | 库从哪来 | 备注 |
|---|---|---|---|---|
| **Z20**（SSD201/202D/203，ARMv7-A + NEON，glibc） | ✅ **可用（已验）** | 真机跑通 + 性能/效果复测两轮 | 原厂档：注册表 `blend2d 0.11.1`；性能档：`lib/z20-neon/` | 详见 §1 |
| **Z21**（ARMv7，glibc，同族工具链） | ⚠️ **未验证** | 无实测 | 无注册表包；**理论上**可复用同一份 `.so` | 详见 §2 |
| **T113EMMC**（ARMv7，glibc） | ⚠️ **未验证** | 无实测 | 同上 | 详见 §2 |
| **V85X / T113（musl）** | ❌ **不可直接用** | `.so` 的 `NEEDED` 是 glibc + `libstdc++.so.6`；musl 平台没有 | 需 musl 重编（**未做**） | 详见 §3 |
| **F133 / F135 / F136（RISC-V64 musl）** | ❌ **不可用** | 架构不同（ELF32 ARM vs RISC-V） | 需另编（**未做**） | 详见 §3 |

### blur

> 文件：`components/blur/platforms.md`

| 平台 | 状态 |
|---|---|
| F133 / F135 / F136（C906，musl） | **已实测**（上表）；RVV 档可用但要整工程开关 |
| Z20 / Z21（ARM glibc） | **未验证**（纯整数代码，无平台依赖；`down`/`radius` 口径通用） |
| T113 / V85X（ARM musl） | **未验证** |

### ha_bridge

> 文件：`components/ha_bridge/platforms.md`
> 口径：**证据**：`packages/mqtt-cxx/evidence/{netstack_auto_20260929.txt, netstack2_20260929.txt, lwt_will_20260929.txt}`。

| 平台 | 可用性 | 前提 | 实测内容 |
|---|---|---|---|
| **Z20**（SSD20X 480×480 · 86 面板） | ✅ **可用**（`mqtt-cxx` 3.2.0）；✅ **组件形态已真机验收**（2026-10-01，zkgui 工程，见 §6） | Manifest 必须一起声明 `mqtt-cxx` + `paho-mqtt3as` + `openssl 1.1.1-w`（漏 openssl 链接报 `BIO_read / RAND_bytes / SHA1_*` undefined） | 明文 `mqtt://…:1883`（EMQX）：`on_connected` 触发、`isConnected()=1`、qos1 订阅→发布→`on_message` 原样回显（len=35）、`unsubscribe` OK；MQTTS `mqtts://test.mosquitto.org:8883`（`ssl.verify=false`）连通 + qos1 收发回显；LWT 注册后 **`kill -9` 异常断线 → 约 2 s broker 代发遗嘱**（PC 见证端，payload 与注册值一致）；断线重连：`enableWifi(false)` 90 s → `on_disconnected`，`enableWifi(true)` 后 **`on_connected` 再触发（cause=`automatic reconnect`，≈10.5 s）** |
| Z21 | ❌ 未验证（**平台无此包**） | Z21 registry **没有 `mqtt-cxx` / `paho-mqtt3as`** | 不验 MQTT（换平台要换 MQTT 方案） |
| F133 / F136 | ❌ 未验证 | 同上：f133/f136/t113emmc/v85x 目录下**都没有**`paho-mqtt3as` | — |
| T113EMMC | ❌ 未验证 | 同上 | — |
| V85X | ❌ 未验证 | 同上 | — |

### icons

> 文件：`components/icons/platforms.md`
> 口径："可用"的含义：产物本身与平台无关；**真机显示效果**需要按 §4 在目标平台各跑一次。 v0.2.0 只做了**离线像素级验收**（selfcheck + contact sheet，含 22px 专项），真机投递未验证。

| 平台 | 可用性 | 说明 |
|---|---|---|
| **全平台（F133 / Z20 / Z21 / V85X / T113 /）** | 可用 | 纯 PNG 资源：生成的图与平台无关；差异只在分辨率/色深/是否硬件加速贴图 |
| V85X | 可用 | 天气/界面图标已在 `projects/inSightOS3` 项目里实际使用过（旧版为自绘天气图，v0.2.0 起换成 Tabler 同名图标） |
| F133 / T113 | 可用 | 高分屏建议 `--size 32/44/56` |
| Z20 / Z21 | 可用 | 小屏优先 `--size 22/24`（本套线宽已按尺寸半像素对齐） |

### imagecache

> 文件：`components/imagecache/platforms.md`
> 口径：前置条件：无（不需要串口/属性门/固件版本）。**唯一前置 = 装载回调必须返回「框架资源表里被持有的位图」**（FlyThings = `BitmapHelper::loadBitmapFromFile`），否则缓存持有了别人随时会释放的指针。

| 平台 | 状态 |
|---|---|
| F133 / F135 / F136（C906，musl） | F133 **已实测**（规格同上，经工程内联版）；F135/F136 **未验证** |
| Z20 / Z21（ARM glibc） | **未验证**。⚠️ 内存敏感：36~128 MB 板的 `capacity` 别按 128 抄，先按 §1 的公式算账 |
| T113 / V85X（ARM musl） | **未验证** |

### mp_transfer

> 文件：`components/mp_transfer/platforms.md`
> 口径：> 「未验证」的准确含义：**没人在本仓按 `example/` 的形态在这台机器上跑过这条链路**。 > 协议本身是来源工程实测过的（见 §1），但"移植到新平台/新工程能不能一次跑通"必须自己验。

| 平台 | 可用性 | 依据 | 备注 |
|---|---|---|---|
| **F133** | 🟡 有来源工程的现场依据（**本仓未上机**） | 来源工程 `F133UhaleAlbum` 提交 `39c25c1` + 维护者用已上线小程序实测（含附带 Python 接收端） | 协议与落盘规则就是按这台机器定的；组件形态的"能不能直接编进别的工程"未在本仓验证 |
| Z20 / Z21 | ❌ 未验证 | — | 需要：可写目录（本模块默认 `/mnt/extsd/mp_transfer/`）、`base::Task` 底座、真机联调一轮 |
| T113 / T113EMMC | ❌ 未验证 | — | 同上；注意 Z21 那类板子**没有 `/mnt/sdnand`**，外置卡路径要实测 |
| V85X | ❌ 未验证 | — | 同上 |

### ui_v1

> 文件：`components/ui_v1/platforms.md`
> 口径：> ⚠️ **F133 专项**：工具链**不接受 `F135`**，Manifest 必须写 `platform="F136"`； > 用 `fun build -p F133` 在本地注册表缺 easyui 包时会因 include 路径缺失而**编译失败**（案例 README §4）。 > > ⚠️ **F133/横屏 fb**：面板 fb 是 800×1280 竖屏，UI 是 1280×800 横屏 → `EasyUI.cfg` **必须手写 rotate**， > 否则画面/触摸方向错（案例已固化口径）。

| 平台 | 面板 fb | UI resolution（json 写的） | EasyUI.cfg 旋转 | 部署路径 | 编译命令 | 内存/能力 |
|---|---|---|---|---|---|---|
| **Z21** | 1024×600 横 | **1024×600** | `rotateScreen/rotateTouch = 0/0` | `fun launch` → `/tmp/{lib,ui,font}` + `EasyUI.cfg` | `fun build -p Z21` | 36MB RAM，无 GPU / 无硬解 |
| **F133** | 800×1280 竖 fb | **1280×800** | `{"rotateScreen":270,"rotateTouch":270}`（写进 `package.properties`） | SD：`/mnt/extsd/{lib,ui}` + 手写 `EasyUI.cfg` | **`fun build -p F136`**（Manifest `platform="F136"`） | 无 GPU / 无硬解 |
| **Z20** | 800×1280 | 按工程 | 按工程 | 按工程 | `fun build -p Z20` | 视频走 MI 硬件图层（抓 fb0 是黑的） |
| **T113 / T113EMMC** | 按工程 | 按工程 | 按工程 | 按工程 | `fun build -p T113` | easyui 2.6.0（无 `relayout`） |
| **V85X（V851/V853/SPINOR/EMMC）** | 800×480 或 1600×600 | 按工程 | 按工程 | `update.img` / `/res` | `fun build -p v85x` | **有 disp 分层**（真 3D/图层合成仅此平台验证过） |

### ui_v1/Calendar

> 文件：`components/ui_v1/Calendar/platforms.md`

| 平台 | 可用性 | 依据 | 上机前必查 |
|---|---|---|---|
| Z20 | ➖ 不逐平台验（口径：UI 控件只做 V85X 单平台代表验收，2026-10-03） | registry `z20/easyui/2.6.0`、`3.0.0` 头文件面一致 | 同 F133 三条 |
| T113 | ➖ 不逐平台验（口径：UI 控件只做 V85X 单平台代表验收，2026-10-03） | registry `t113emmc/easyui/2.9.0` 一致 | 同 F133 三条 |
| V85X | ✅ **可用（真机已验收 2026-10-03）** | registry `v85x/easyui/2.3.0`、`2.9.0` 一致；**V85X 实测（2026-10-03）**：`fun build` + `fun launch` 通过、launch 后 `onUI_show` 确认、抓屏有内容（证据 `example/evidence/v85x_20261003_full.png`）。口径：示例为 1024×600、面板 480×1600，验的是**组件可用性**，不是版式 | 同 F133 三条；V85X 内存/带宽紧，长按翻月之类别做 |

### ui_v1/Chart

> 文件：`components/ui_v1/Chart/platforms.md`

| 平台 | 可用性 | 依据 |
|---|---|---|
| Z20 | ➖ 不逐平台验（口径：UI 控件只做 V85X 单平台代表验收，2026-10-03） | registry `z20/easyui/2.6.0`、`3.0.0` 的 `ZKPainter.h` 公开面一致 |
| T113 | ➖ 不逐平台验（口径：UI 控件只做 V85X 单平台代表验收，2026-10-03） | registry `t113emmc/easyui/2.9.0` 一致 |
| V85X | ✅ **可用（真机已验收 2026-10-03）** | registry `v85x/easyui/2.3.0`、`2.9.0` 一致；V85X 有较多内存/带宽限制，密集点阵（如 PRPS 那种每格一个 fillArc）**先在真机量一遍再上**；**V85X 实测（2026-10-03）**：`fun build` + `fun launch` 通过、launch 后 `onUI_show` 确认、抓屏有内容（证据 `example/evidence/v85x_20261003_full.png`）。口径：示例为 1024×600、面板 480×1600，验的是**组件可用性**，不是版式 |

### ui_v1/RadButton

> 文件：`components/ui_v1/RadButton/platforms.md`

| 平台 | easyui | 状态 | 说明 |
|---|---|---|---|
| **Z21** | 2.6.0 | ✅ **已真机验收**（§1；21:2x 复核证据归属无误） | 1024×600；`fun build -p Z21` 通过、`check_all` 全 PASS（主代理实跑） |
| F133 | 2.9.0 | ➖ 不逐平台验（口径：UI 控件只做 V85X 单平台代表验收，2026-10-03） | API 头文件已核对（§3） |
| F136 | — | ➖ 不逐平台验（口径：UI 控件只做 V85X 单平台代表验收，2026-10-03） | 同上 |
| Z20 | 3.0.0 | ➖ 不逐平台验（口径：UI 控件只做 V85X 单平台代表验收，2026-10-03） | 头文件已核对 |
| T113 / T113eMMC | 2.9.0 | ➖ 不逐平台验（口径：UI 控件只做 V85X 单平台代表验收，2026-10-03） | 头文件已核对 |
| V85X | 2.3.0 | ✅ **可用（真机已验收 2026-10-03）** | 头文件已核对；注意 disp 分层平台的老问题与本包无关；**V85X 实测（2026-10-03）**：`fun build` + `fun launch` 通过、launch 后 `onUI_show` 确认、抓屏有内容（证据 `example/evidence/v85x_20261003_full.png`）。口径：示例为 1024×600、面板 480×1600，验的是**组件可用性**，不是版式 |

### ui_v1/_mapping/TabView

> 文件：`components/ui_v1/_mapping/TabView/platforms.md`

| 平台 | 可用性 | 依据 |
|---|---|---|
| Z20 | ➖ 不逐平台验（口径：UI 控件只做 V85X 单平台代表验收，2026-10-03） | registry 有 `z20/easyui/2.6.0` 与 `3.0.0`，`ZKPageWindow.h` 公开面与 Z21 同名同签名；组件无平台分支 |
| T113 | ➖ 不逐平台验（口径：UI 控件只做 V85X 单平台代表验收，2026-10-03） | registry `t113emmc/easyui/2.9.0` 头文件一致；`bin_tools/t113/touch` 已有（触摸注入可用） |
| V85X | ✅ **可用（真机已验收 2026-10-03）** | registry `v85x/easyui/2.3.0`（较老）与 `2.9.0` 都含 `IPageChangeListener + getPageSize + turnTo*`（**已逐个核对头文件**）；组件无平台宏；**V85X 实测（2026-10-03）**：`fun build` + `fun launch` 通过、launch 后 `onUI_show` 确认、抓屏有内容（证据 `example/evidence/v85x_20261003_full.png`）。口径：示例为 1024×600、面板 480×1600，验的是**组件可用性**，不是版式 |

### vinyl

> 文件：`components/vinyl/platforms.md`

| 平台 | 定点后端 | nanovg 后端 | 每帧耗时（定点 / nanovg） | 备注 |
|---|---|---|---|---|
| **F133**（C906 / musl，1280×800，rotate=270） | ✅ 实测（`projects/iOSStyle-F133` 播放页） | ✅ 实测 | **6~12ms / 23~44ms**（320×320） | 定点 12.3~12.6fps、CPU 42~50%；nanovg 11~12fps、CPU 60~69%；两者均无方角/暗边 |
| F135 | 未验证 | 未验证 | — | 与 F133 同核（C906 RISC-V），预期一致（待测） |
| Z20 / Z21 | 未验证 | 未验证（注册表有 nanovg 包则可用） | — | 待测 |
| T113 | 未验证 | 未验证 | — | 待测 |
| V85X | 未验证 | 未验证 | — | 待测（若是 MCU Lite 平台，本组件**不适用**：那是 `.form`/`zkres.bin` 体系） |

### wall_sync

> 文件：`components/wall_sync/platforms.md`
> 口径：> ⚠️ 结论：**只有 Z20 有拼墙实测口径**。换平台前先按 §3 的"换平台先查三件事"过一遍。

| 平台 | 可用性 | 说明 |
|---|---|---|
| **Z20** | **可用（真机验证；本组件的落地来源平台）** | 组网/校时/时间轴与相位对齐按来源工程的现场版本验证；解码上屏 = MI VDEC + MI DISP（官方包 `simple-player` 引擎） |
| F133 / F135 / F136 | `未验证` | 组件本身是纯 C++11 + POSIX（socket/pthread/clock_gettime）+ rapidjson，**编译大概率没问题**；但"拼墙相位对齐"链条依赖：① 平台有可注入的硬解引擎；② 各机墙钟可校时；③ MI/图层支持多实例。以上均**未在 F133 系上做过拼墙实测** |
| Z21 | `未验证` | 同上；来源工程只在 Z20 上做拼墙 |
| T113 / T113EMMC | `未验证` | 同上 |
| V85X | `未验证` | 同上 |

## 4. 怎么用 / 怎么改

**查**：
```python
import platform_cap_loader as pc
pc.components_for_platform('Z20')      # Z20 上声明支持的组件
pc.cell('ble', 'Z20', '可用性')         # ble 在 Z20 的可用性原话
pc.platforms_of('ble')                 # ble 覆盖哪些平台
```

**改**：① 改 `platform_capabilities.json` 对应组件的行 ② 跑 `python scripts/gen_platform_cap_doc.py` 与本页同步 ③ 跑 `python scripts/gen_component_platforms.py` 与各组件 `platforms.md` 同步。

**判定口径**：状态词沿用各组件原话（可用 / 支持 / 未验证 / 不可用），本页**不改写**结论；「未验证」就是没实测，选型前必须按该组件的 `platforms.md` §验收 真机跑一遍。

> 本页只覆盖「能力矩阵」这一层。各平台的前置条件、已知限制、真机验收命令在各组件的 `components/*/platforms.md` 正文里。
