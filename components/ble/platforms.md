# ble 模块 —— 平台说明

> 逐平台写清"能不能用、前置条件、实测值、限制、怎么验收"。没实测的标 `未验证`，不写"应该可以"。
> 数据来源：本仓实测记录（2026-09-12~13）+ 包/源码逐条核对 + 2026-09-13 真机（V85X SPINOR）快照。

---

## 0. 汇总

| 平台 | 可用性 | BT 模组 | BT 串口 | 传输/校验 | 上电节点 | 预初始化 | 备注 |
|---|---|---|---|---|---|---|---|
| **F133**（RISC-V） | ✅ 可用（链路最干净） | 非 Realtek 类 | `/dev/ttyS1` | H5 + 无校验 | 无 | 不需要 | 扫描类场景首选；`projects/BTHomeTempHum-F133` 是范本 |
| **V85X**（V851 系列） | ✅ 可用（坑最多） | **RTL8733BS** | `/dev/ttyS2` | H5 + **偶校验 8E1** + 无流控 | `state_bt`（出厂 off） | **必须**（Realtek 8733bs） | 需 `setPreinitHook()` 挂 rtk_init |
| **Z20 / Z21** | 🟡 支持（**仅 AIC 8800DL 模组是 BLE**） | AIC 8800DL | 待实测 | **H4 + 流控开 + 无校验** + 1500000 | 待实测 | 不需要（AIC 直接走 HCI） | ⚠️ 本平台目前**查不到 btstack 包**（`flythings_query_package(btstack, Z20)` 版本为空）；上 BLE 需先出包 + 补实测值 |
| **电子价签 tag**（Z20 平台） | ✅ 业务上本就是 BLE 方案 | 同 Z20（8800DL） | 待实测 | — | — | — | 项目 `projects/tag`（platform=Z20，依赖 `tag` 12.x）；其 BLE 走哪条链路（btstack / tag 包自带）待确认 |
| T113 | ❌ 未适配 | — | — | — | — | — | 电源与串口链路不同，不要套用 |

> 口径修正（2026-09-13，沛哥）：Z20/Z21 **是支持 BLE 的**（但仅 AIC 8800DL 模组有 BLE），电子价签 tag 本就跑在 BLE 方案上。
> 模块侧已预留 **AIC 分支**（H4 + 流控 + 无校验，参数自动判定，`Config.flowcontrol/parity` 可覆盖），
> 剩余阻塞是 **该平台能否拿到 btstack 包** 与 **串口/上电节点的实测值**。

### 0.1 传输参数自动判定（模块内实现）

| 分支 | 判定条件 | 传输 | 流控 | 校验 | 波特率 |
|---|---|---|---|---|---|
| Realtek（8733bs） | `persist.wifi.module` 含 `8733` | H5（必须过 SLIP） | off | **偶校验 8E1** | 115200 起步 → 预初始化切 1500000 |
| AIC / 其它 | 否则 | H4（`Config.prefer_h5=true` 可强行 H5） | on（H5 时 off） | 无 | 1500000 |

`Config.flowcontrol` / `Config.parity` 传 ≥0 即显式覆盖自动值（换模组/换板子时的后门）。

### 0.2 组件包里的 BLE 全景（2026-09-13 实测下载核对）

沛哥提示「关于 BLE 的可以从组件包里面搜索」→ 实际扫包结果（可直接 `curl` 下载核对）：

```bash
curl -o z20-ble.zip  https://package.flythings.cn/packages/z20/ble/1.1.1.zip
curl -o z21-ble.zip  https://package.flythings.cn/packages/z21/ble/2.1.0.zip
curl -o blehid.zip   https://package.flythings.cn/packages/v85x/blehid/1.1.3.zip
curl -o btstack.zip  https://package.flythings.cn/packages/v85x/btstack/1.8.0.zip
```

| 平台 | 包 | 版本 | 是什么 | 对外头文件 | 库 |
|---|---|---|---|---|---|
| F133 | `btstack` | 1.7.2 | BLE 协议栈（**中心+外设**自己写） | `btstack/*` | `libbtstack.a` 1.04MB |
| V85X | `btstack` | **1.8.0**（比 1.7.2 新） | BLE 协议栈 | `btstack/*` | `libbtstack.a` 460KB |
| V85X | **`blehid`** | 1.1.3 | **BLE HID 外设**（基于 btstack，已封好）：按键/触摸上报、手机类型、RSSI | `ble/server.h` | `libblehid.a` 115KB |
| Z20 | **`ble`** | 1.1.1 | **BLE 外设服务（BlueZ/libgatt）**：设备名 + GATT 服务 + 收包回调 | `ble/bluetooth_service.h` | `libble.a` + `libgatt-server.a` + `bin/{gattserverbin,hciattach,hciconfig,hcitool}` |
| Z21 | **`ble`** | 2.1.0 | 同上 | 同上 | 同上 |

**两个现成外设包的真实接口**（挑重点，可直接照抄调用）：

```cpp
// —— V85X · blehid 1.1.3（BLE HID 外设：副屏遥控/触摸上报）——
#include <ble/server.h>
ble_params_t p;  p.module = E_BLE_MODULE_RTK;   // 或 E_BLE_MODULE_AIC —— 包内自己处理模块分支！
                 p.uart = "/dev/ttyS2"; p.baudrate = 115200; p.name = "FlyThings";
ble::server_start(p);
ble::touch(points, count);          // 触摸上报
ble::send_key(BLE_KEY_HOME);        // 按键上报
ble::add_event_cb(cb);              // HCI 启停/连接/断开/设备名/RSSI

// —— Z20/Z21 · ble 1.1.1 / 2.1.0（BlueZ/libgatt 外设）——
#include <ble/bluetooth_service.h>
BluetoothParams bp; bp.name = "ble-123456"; bp.on_message = onMsg;
BluetoothService::instance().start(bp);   // 收包从 on_message 回调出
```

⚠️ `ble` 包 README 第三条硬约束：**「启动蓝牙时内部会自动开 WiFi；WiFi 关了蓝牙也停」**；
且**必须先做一次升级包升级后蓝牙才能启动**；需 IDE 20250530+。

**结论（决定模块分工）**：
- **外设/HID 侧不要重写**：V85X 用 `blehid`、Z20/Z21 用 `ble`（它们已经把模块分支/驱动/粘包都做了）。
  `zk::ble::peripheral::*` 的定位改为**胶水/门面**（或文档里直接写明“外设请直接用这两个包”）。
- **中心侧（扫描 / 连接 / GATT 客户端）只有 btstack 提供** → 这就是 `zk::ble` 真正要补的那一层，
  平台覆盖 = F133(1.7.2) + V85X(1.8.0)；**Z20/Z21 目前没有中心侧包**。
- 电子价签 `tag` 工程就是 `ble` 那套的实例（其 `src/ble/bluetooth_service.cpp` + BlueZ/ATT + `aic_btusb.ko` 驱动）。
- 版本要按平台锁：F133 → `btstack 1.7.2`；V85X → `1.8.0`（并且 V85X 要把 `blehid` 一并声明）。

---

## 1. F133（RISC-V）—— 建链路最简单

- **串口**：`/dev/ttyS1`（本仓实测）。`Config.uart` 留空时模块按存在性探测，顺序 `ttyS1 → ttyS2`。
- **传输**：H5；`Config.prefer_h5 = true`（默认）。
- **上电**：**没有** `state_bt` 这类开关 → 探测不到节点也不报错（模块只在"需要预初始化的模组"上做上电时序）。
- **预初始化**：不需要（`persist.wifi.module` 不含 `8733`）。
- **波特率**：`Config.baud = 0` 时默认 `1500000`（F133 侧实测值）。
- **典型用途**：BLE 扫描（Central/Observer），如 BTHome 温湿度计（Service Data `0xFCD2`）。
- **验收**：
  ```
  1) openAdapter() 返回 ok，getDiag(): ready=1, hci_events > 0
  2) startDiscovery({name_prefix:"BTHome"}) → onDeviceFound 有上报
  3) getDevices() 非空 → connect() ok → getServices() 能列出 fcd2
  ```

## 2. V85X（V851 系列）—— 前置条件最多，务必逐条核对

| 项 | 实测值 | 怎么确认 |
|---|---|---|
| 芯片 | RTL8733BS（WiFi+BT combo） | `getprop persist.wifi.module` = `8733bs`（模块自己会读） |
| 串口 | `/dev/ttyS2` | DT：`uart@2500800` = okay；`ttyS1` / `ttyS3` = disb |
| ⚠️ 出厂配置是错的 | `/res/etc/EasyUI.cfg` 写 `uart:"ttyS1"`（该节点不存在） | 别照抄；用本模块自动探测或显式配 `ttyS2` |
| 传输 | H5 + **偶校验 8E1** + 无流控 | `Config.prefer_h5=true`（默认） |
| 波特率 | 预初始化 115200 → 工作 1500000 | 模块内：`needs_preinit` 时默认 115200 |
| 上电节点 | `/sys/devices/platform/soc/soc@03000000:netRF/state_bt`（兜底 `soc@3000000/soc@3000000:netRF/state_bt`） | 出厂 `off`；模块自动 0→50ms→1→300ms ×2 轮 + 回读 |
| WiFi 电源 | 同族节点 `state_wifi`（**另一个开关**） | WiFi 没起来的板子 BT 往往也没初始化，两边都要看 |
| 固件 | `rtl8733bs_fw`(55580B) + `rtl8733bs_config` | 随应用打包：`src/dependencies/bin/firmware/rtlbt/` → `/res/bin/firmware/rtlbt/` |
| ⚠️ 系统盘里那份固件不是它的 | `/lib/firmware` 只有 `aic8800DC`（AIC8800 的） | 全盘搜不到 rtl → 固件必须随应用走 |

**预初始化（本模块不内置，用 hook 挂）**
```cpp
#include "rtk/hciattach.h"                 // 工程里 src/ble/rtk/ 那套（3.1.3 分支）
zk::ble::setPreinitHook([](const std::string& uart, uint32_t baud) -> zk::ble::Result {
    if (rtk_init(uart.c_str()) != 0)
        return zk::ble::Result::err(zk::ble::ERR_POWER_OFF, "rtk_init 失败");
    return zk::ble::Result::ok_();
});
zk::ble::openAdapter();                     // 内部：上电 → preinit → btstack 装配 → 等 WORKING
```
判据（跑通时的日志形态）：
```
[rtk] [SYNC] Get SYNC Resp Pkt   ← H5 同步握手成功
[rtk] IC: RTL8733BS, chip_type 0x76
[rtk] Load FW .../rtl8733bs_fw OK, size 55580
[zkble] HCI state = 2            ← WORKING（到达这里才算就绪）
```
**验收**：`getDiag()` 里 `powered=1, preinit_ok=1, ready=1`；`startDiscovery()` 能看到周边设备。

**⚠️ 已知平台级限制（不是本模块能解决的）**
- 预初始化**成功率不稳定**：失败多为 `OP_H5_SYNC Transmission timeout`，现象是 btstack 一直 `INITIALIZING`。
  已排除参数/时序/内存/WiFi 共存；**软 `reboot` 无效**（连续 3 次 reboot 后立即跑，全失败）。
  → **能一次跑通就别反复重初始化**；必须重来时**物理断电重上电**。产品化建议：**开机后首次进入该功能时初始化一次**。
- 集成期零碎坑：HID 报告必须吃**含 report id 的完整报告**；PC（Windows/bleak）枚举不到 HID 服务特征，
  **HIDS 订阅只能用手机验证**；TLV 落盘优先 `/data`（`/`、`/res` 只读）。
- 抓包重放学遥控器**不成立**（HID 链路加密，会话密钥独立）→ 正解是当 **HID 主机**（`hids_client`）在**本机**建映射表。

## 3. btstack 包能力边界（F133 1.7.2 / V85X 1.8.0 实测符号扫描）

| 能力 | 有没有 | 证据 |
|---|---|---|
| BLE 中心/观察者（扫描、连接、GATT 客户端） | ✅ | `gap_le_*`、`gatt_client_*` |
| BLE 外设（广播、ATT/GATT 服务端、HID 外设 HOGP） | ✅ | `att_server_*`、`hids_device_init` |
| BLE HID 主机（读对方报告） | ✅ | `hids_client_connect` |
| 经典蓝牙（SPP / A2DP / AVRCP / HFP / 经典 HID 主机 / SDP） | ❌ **全无** | `rfcomm/sdp_/avdtp/a2dp/hfp/bnep/goep/avrcp` 在 `.a` 里 0 符号 |
| 经典 L2CAP 通道 | ❌ | 无 `l2cap_register_service` / `l2cap_create_channel` |
| LE Secure Connections | ❌ F133(1.7.2) 未编；⚠️ V85X(1.8.0) config 里宏是开的但**库里仍查无 lesc/ECC 符号**（同 1.7.2 的“宏残留”现象）→ 以真机实测为准 | 配置注释/声明 + `.a` 符号扫描 |

## 4. 要支持新平台（T113 / Z20 / Z21）要改什么

只需动**平台适配层**（`src/zk_ble.cpp` 里的 `kPowerNodes` / `defaultUart()` / chip 判定），不改接口面：
1. 加串口候选（`defaultUart()`）；
2. 加上电节点候选（`kPowerNodes`，多个候选 + 存在性判断，别写死）；
3. 确认芯片判定属性（`persist.wifi.module` 在该平台是否可用）与是否需要预初始化；
4. 实测值补进本文件（含"未验证"标注），并在 `Manifest.xml` 的 `enableOnPlatforms` 里加平台。

**Z20/Z21（AIC 8800DL）的待办**：① 确认该平台有/能出 `btstack` 包（当前包仓库查不到版本）；
② 实测 BT 串口节点与 `state_bt`/`state_wifi` 是否同族；③ AIC 走 H4 + 流控，需确认该平台 btstack 构建含 H4 传输。

## 5. 真机快照（2026-09-13 已接入本机的那块）

```
$ adb devices -l
  20080411   device product:swaio model:Zkswe_V85X_SPINOR device:swaio
$ adb shell getprop persist.wifi.module                 → 8733bs
$ adb shell cat /sys/devices/platform/soc/soc@03000000:netRF/state_bt  → on
$ adb shell cat /proc/modules                           → 8733bs 1709148 0 - Live
$ adb shell ls /dev/ttyS*                               → ttyS0  ttyS2        （★没有 ttyS1）
$ adb shell ls /data                                    → bttlv.db 已存在（之前跑过）
$ adb shell ls /res/bin                                 → firmware/ 存在
```
→ 这块板走的正是 **V85X + RTL8733BS** 路径（H5 + 偶校验 + `state_bt` 上电 + rtk 预初始化）。

### 5.1 真机跑测证据（2026-09-13，`projects/ZkBleScanTest`）

构建：`fun install` → `fun build` → **Linking CXX executable ZkBleScanTest** ✅
（bin 工程要点：`fun.json` 优先于 `Manifest.xml`，依赖写 fun.json；type=executable 才出 ELF；
rtk 移植件要 `utils/Log.h` → 本工程用 `src/utils/Log.h` 本地垫片顶掉 easyui 依赖，避免拖进 freetype/nanovg/png 一串）

运行：`adb push … /tmp/ && ./ZkBleScanTest`
```
[test] rtk_init(/dev/ttyS2) ...
I/Realtek: Realtek hciattach version 3.1.3be84a4.20240130-154850
W/Realtek: OP_H5_SYNC Transmission timeout  ×N   ← 偶发一次 [SYNC] Get SYNC Pkt 但还是走到
E/Realtek: Retransmission exhausts                    Retransmission exhausts
[zkble] ERR(-2) preinit 失败: rtk_init 失败
[test] openAdapter -> code=-2 …
[test][after-open] chip=8733bs uart=/dev/ttyS2 baud=115200 powered=1 preinit=0 ready=0 hci_state=0 events=0
```

**结论**：上电链路（`powered=1`）与串口/参数选择都对，卡在**文档已记的“预初始化不稳定”**（`OP_H5_SYNC` 超时）。

### 5.2 真机跑通记录（2026-09-13 11:2x）✅

事实链路：上电 → rtk_init（SYNC/CONFIG/下固件/切 1500000）→ btstack HCI **WORKING(2)** → 扫描 → **17 个设备**（含电子价签 `tag-dc8403a119fc`）：
```
[test][end] chip=8733bs uart=/dev/ttyS2 powered=1 preinit=1 ready=1 hci_state=2 events=554 sent=19 devices=17
[test] DEV DC:84:03:A1:2D:84  tag-dc8403a119fc  rssi=-74 conn=1     ← 扫到自家价签
```

**跑通的关键（三个都是真机试出来的）**

1. ★ **必须先停掉抢串口的 app**：`/bin/zkgui`（系统应用）开机后就持着 `/dev/ttyS2` **两个 fd**，
   此时 rtk_init 的 H5 同步永远超时。查法：`ls -l /proc/<pid>/fd | grep ttyS2`。
   长期正解：**我们的应用自己固化进设备**（升级包），不跟系统 app 抢。
2. ★ **传输层必须照实测可用写法**（错一个就在 `hci_power_control()` 里段错）：
   | 项 | 可用 | 不可用（真机段错） |
   |---|---|---|
   | 配置结构体 | `hci_transport_config_uart_t` + `type=HCI_TRANSPORT_CONFIG_UART` | `btstack_uart_config_t` |
   | 波特率 | **1500000**（预初始化后的工作值） | 115200（起步值） |
   | SLIP | 不套，posix uart 直接给 `h5_instance` | 再套 `slip_wrapper_instance` |
3. **上电时序拉长更稳**：实测“断电 3s → 上电 2s”比文档里的 50ms/300ms 稳得多（本轮每轮都过）。

**复现命令（本机）**
```bash
wsl 无关；全程 Windows + fun + adb：
 cd projects/ZkBleScanTest && C:/zkswe/fun/fun.exe build
 adb push .fun/v85x/ZkBleScanTest /tmp/ && adb shell chmod 777 /tmp/ZkBleScanTest
 adb shell '/tmp/busybox killall zkgui; echo 0 > <state_bt>; sleep 3; echo 1 > <state_bt>; sleep 2; cd /tmp && ./ZkBleScanTest'
```

**未完成（下一步）**：把我们的应用做**固化升级包**（`fun pack` → update.img → adb 固化），
让设备上的 app 就是我们自己的，彻底消除抢串口冲突，而不是每次靠 kill。

### 5.3 ✅ 固化升级跑通（2026-09-13 11:2x，改成 app 工程）

**做法**：按 FlyThings 流程建 **app 工程**（不是 bin！）——`flythings_create_project(platform=V85X, resolution=480x800)`
→ 挂 `components/ble` 模块 + rtk 预初始化件 → UI（html→json→ftu）→ `fun build` → `flythings_pack_upgrade`
→ ADB 固化（`setprop sys.zkupgrade.*` + `ctl.restart zkswe`）。

**为什么必须做成 app**（沛哥指正）：**init 托管 zkgui，kill 掉只会被立刻重生**，抢窗口只能验证、不能交付；
bin 只能用来做测试验证，验证完就要走 FlyThings 应用流程。固化后 app 自己拥有 `/dev/ttyS2`，冲突自然消失。

**开机自启日志（证据链完整）**
```
I/Realtek: Load FW /res/bin/firmware/rtlbt/rtl8733bs_fw OK, size 55580
I/Realtek: Final speed 1500000 → Init Process finished
D/zkgui  : [zkble] HCI state = 1 → HCI state = 2 → scan started
```
真机屏幕：汉字正常，状态行“适配器就绪，开始扫描… | 设备 19 | HCI 2”，列表里含 `tag-dc8403a119fc`。

**⚠️ 固化升级的三个坑（原 app 的东西会被覆盖）**

| 现象 | 根因 | 修法 |
|---|---|---|
| `E/Realtek: Can't open firmware` → preinit 永远失败 | 升级包**覆盖了原 app 的 `/res/bin/firmware/rtlbt/`**，固件没了 | 固件放工程 `src/dependencies/bin/firmware/rtlbt/{rtl8733bs_fw,rtl8733bs_config}` → 进包 `/res/bin/firmware/rtlbt/` |
| 汉字全变方块（英文正常） | `/res/font` 被清空（原 app 自带字体），回退到 `/etc/font/fzcircle.ttf`（无汉字） | 字体放工程 `font/*.ttf` → 进包 `/res/font/`；并在 `.settings/com.zksw.flythings.easyui.prefs` 的 `easyui.cfg.release/debug` 里加 `"font":"/res/font/font.ttf"`（打包时写进 EasyUI.cfg） |
| 传输走错串口 | 预置 `EasyUI.cfg` 里是平台默认 `uart:"ttyS1"`（本板无此节点） | 同上改 `.settings` 里的 `uart` 为 `ttyS2`（BT 侧本模块会自己探测，这主要影响 easyui 自己的串口协议） |

**其他随本轮固化的改进**
- `Config.open_timeout_ms` 默认 10s → **60s**：要盖得住预初始化重试的总耗时（否则重试还没跑完就报“等 HCI WORKING 超时”）。
- 新增 `setLogHook()`：把组件日志接到应用日志（`LOGD` → logcat, tag=zkgui），现场排错不用再靠猜。
- 上电时序默认改为**断电 3s / 上电 2s**，并支持 `preinit_retry`（默认 3 次，每次重试前重新上电）。
按实测结论：**需要物理冷启动（拔插/复位），软 `reboot` 无效**；产品上应“开机后首次进入该功能时初始化一次”。

**真机一次跑测抓到并修的自家 bug（均已重编重跑验证）**：
1. `openAdapter()` **误报成功**：线程内 preinit 失败只 signal 没置错 → 返回 `code=0`。
   修法：检查 waiter 状态，失败就返回 `ERR_POWER_OFF` + 人话 msg。
2. **preinit 失败后段错误**：btThread 提前 return，run loop 从未启动，但 `startDiscovery()` 仍往
   未初始化的 run loop 投递任务。修法：新增 `failed` 标记 + 所有动作接口在 `!ready` 时直接拒绝。
3. **`hci_power_control()` 段错（真机硬阻）**：传输配置结构体用错（`btstack_uart_config_t` 应为
   `hci_transport_config_uart_t`）+ 波特率用错（115200 应为工作值 1500000）+ 多套了一层 SLIP。
   修后一次跑到 WORKING 并扫出 17 个设备（见 §5.2）。
