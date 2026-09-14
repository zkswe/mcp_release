# ble —— BLE 门面 `zk::ble` v0.2（一个 API，两个后端）

> 把蓝牙收拾成微信小程序 `wx.*` 那种用法：**业务/AI 只面对一套接口，脏活全在库里**。
> **中心侧**照微信公众号那套（`wx.openBluetoothAdapter` → 扫描 → 连接 → GATT 读写订阅）；
> **外设侧**微信没有，按 Android `BluetoothGattServer` + `BluetoothLeAdvertiser` 的形状给（`zk::ble::peripheral::*`）。
>
> 一个 API 面、两个平台后端（业务代码不改，只看 `getCapabilities()` / `backendName()`）：
>
> | 平台 | 后端 | 中心 | 外设 | 说明 |
> |---|---|---|---|---|
> | F133 | `btstack` 1.7.2 | ✅ | ❌ | 串口 HCI（H5）；外设请走别的路线 |
> | V85X | `btstack` 1.8.0 | ✅ | ❌ | 串口 HCI + 预初始化钩子；**外设/触摸上报用 `blehid` 包** |
> | Z20 / Z21 | **`gatt` 1.0.0** | ✅ | ✅ | AIC USB 模组 + BlueZ 用户态 GATT，**主从双角色**（真机跑通） |
> | T113 / T113EMMC | **`gatt` 1.0.0** | ✅ | ✅ | 同 Z20/Z21（带上 `hcitool cmd 0x03 0x0003` 拉起 LE） |
>
> 立项：2026-09-13（沛哥：「模仿 Android 或微信的 API 封装一层，最终暴露给 AI 开发的就是 wxapi 这种」）；
> 统一：2026-09-14（钟工：「蓝牙部分都统一按照昨天定义的新 API，参考微信的方式」→ 组件收口为一个 API 面 + 两个后端，Z20/Z21 从"只做外设"改成**双角色**）。
>
> **版本记录**
> - **v0.2.0（2026-09-14）** 统一 API 面 + 两个后端（gatt 后端 Z20/Z21/T113 **主从双角色**），**组件级真机验证通过**（Z20 外设 × Z21 中心，五条验收全过）；含三个真机 bug 修复（uuid 取空 / 自建表拿不到 value_handle / 广播 status=12）。
> - v0.1.0（2026-09-13）首版：btstack 后端（适配器/扫描/连接/GATT 读写订阅/诊断）；外设留口。

---

## 1. 它解决什么问题

蓝牙的门槛不在协议，在**前置条件与规矩**（而且**每个平台的前置条件还不一样**）：

| 坑（全部来自本仓 bring-up / 真机记录） | 本模块的处置 |
|---|---|
| V85X：`state_bt` 没上电（出厂 off） | `openAdapter()` 自动 写0→50ms→写1→300ms ×2 轮 + **回读确认** |
| V85X：Realtek 必须先 hciattach | 预留 `setPreinitHook()`，由项目侧挂 `rtk_init`（见 §6） |
| Z20/Z21：BT 是 **AIC USB 模组**（`aic_btusb.ko`），不是串口 HCI | gatt 后端自动 `insmod` / 拉 `hciattach` 服务 + `hciconfig hci0 up` |
| Z20/Z21：`/res` 只读、**没有 `/res/bin`**（工具找不到） | 工具路径候选链 `/res/bin → /data/bin → /tmp/bin → /usr/bin → /bin` |
| Z20/Z21：**断开后控制器残留链路**（`0x0B`/EIO），下一次连接必失败 | `connect()` 自动重试 + 重试前 `hciconfig hci0 reset`（`Config.connect_retry` / `reset_before_retry`） |
| 外设：断开后重开广播失败却只打一行日志（**静默丢广播**） | `adv enable` 校验 HCI 状态 → 失败先 disable 再 enable → 仍失败**明确报错** |
| 串口/波特率/校验写死 | 自动探测 `ttyS1`(F133)/`ttyS2`(V85X)+`Config` 可覆盖；H5+偶校验默认 |
| 跨线程调协议栈 → 卡 `INITIALIZING` | 库内固定线程模型（run loop/mainloop 独占一线程 + 任务投递 + 条件变量等结果） |
| 判据看错（`0x6E` 当芯片回应） | `getDiag()` 只统计真实事件 0x01~0x5F，`transport_sent` 单列 |
| 失败静默（线程 `return NULL`） | 每个失败都带 `Result{code,msg}` + `getDiag().hint` |

---

## 2. 快速开始

### 2.1 中心侧（扫描 → 连接 → 读写订阅）

```cpp
#include "zk/zk_ble.h"

zk::ble::Config cfg;                                     // 默认值即可（Z20/Z21 无串口，F133/V85X 自动探串口）
cfg.connect_retry = 2;                                   // Z20/Z21 建议保留：控制器残留链路 → 自动重试
zk::ble::openAdapter(cfg);                               // 上电 + (预初始化) + HCI + TLV + 线程，一步到位

zk::ble::onDeviceFound([](const zk::ble::DeviceInfo& d){
    printf("发现 %s %s rssi=%d\n", d.id.c_str(), d.name.c_str(), d.rssi);
});
zk::ble::onValueChange([](const zk::ble::Value& v){ /* 通知数据 */ });

zk::ble::ScanOptions so;  so.name_prefix = "BTHome";
zk::ble::startDiscovery(so);

std::vector<zk::ble::DeviceInfo> devs;
zk::ble::getDevices(devs);
zk::ble::connect(devs[0].id);

std::vector<zk::ble::Service> svcs;
zk::ble::getServices(devs[0].id, svcs);                  // 服务+特征一次拿全
zk::ble::subscribe(devs[0].id, "fcd2", "fcd2", true);
```

完整可编译示例：[`example/main_example.cc`](example/main_example.cc)。

### 2.2 外设侧（广播 + GATT 服务 + notify / 收写）

```cpp
#include "zk/zk_ble.h"

zk::ble::onConnectionChange([](const std::string& id, bool connected){
    printf("中心 %s %s\n", id.c_str(), connected ? "连上了" : "断开了");
});
zk::ble::onWriteRequest([](const std::string& cu, const std::string& data){
    printf("收到写 %s: %zu 字节\n", cu.c_str(), data.size());
});

zk::ble::PeripheralConfig pc;
pc.device_name   = "zkswe ble";
pc.service_uuid  = "fff0";
pc.characteristics = { {"fff1", zk::ble::PROP_READ | zk::ble::PROP_NOTIFY, ""},
                       {"fff2", zk::ble::PROP_WRITE | zk::ble::PROP_WRITE_NO_RESPONSE, ""} };
zk::ble::peripheral::start(pc);                          // 建表 + 广播（Z20/Z21/T113 可用）

zk::ble::peripheral::notify("fff1", std::string("\x01\x02", 2));   // 主动上报
```

完整可编译示例：[`example/peripheral_example.cc`](example/peripheral_example.cc)。
**先查能力**：`zk::ble::getCapabilities(cap)` → 在 F133/V85X 上 `cap.peripheral == false`，
`peripheral::start()` 会返回 `ERR_UNSUPPORTED` 并在 msg 里指路（V85X 用 `blehid` 包），**不假装能用**。

---

## 3. API 一览（对标微信小程序 / Android）

| 微信小程序（中心侧） | Android | `zk::ble` |
|---|---|---|
| `wx.openBluetoothAdapter` | `BluetoothAdapter` + Gatt | `openAdapter(cfg)` / `closeAdapter()` / `adapterReady()` |
| `wx.getBluetoothAdapterState` | `getState()` | `getAdapterState(out)` |
| `wx.onBluetoothAdapterStateChange` | `ACTION_STATE_CHANGED` | `onAdapterStateChange(cb)` |
| `wx.startBluetoothDevicesDiscovery` | `startScan` | `startDiscovery(opts)` / `stopDiscovery()` |
| `wx.onBluetoothDeviceFound` | `ScanCallback` | `onDeviceFound(cb)` |
| `wx.getBluetoothDevices` | 自己缓存 | `getDevices(out)` / `clearDevices()` |
| `wx.createBLEConnection` | `connectGatt` | `connect(id, timeout)` / `disconnect()` / `isConnected()` |
| `wx.getBLEDeviceServices` | `discoverServices` | `getServices(id, out)` |
| `wx.getBLEDeviceCharacteristics` | `getCharacteristics()` | `getCharacteristics(id, svc, out)` |
| `wx.readBLECharacteristicValue` | `readCharacteristic` | `readValue(id, svc, chr, out)` |
| `wx.writeBLECharacteristicValue` | `writeCharacteristic` | `writeValue(id, svc, chr, data, with_response)` |
| `wx.notifyBLECharacteristicValueChange` | `setCharacteristicNotification` | `subscribe(id, svc, chr, enable)` |
| `wx.onBLECharacteristicValueChange` | `onCharacteristicChanged` | `onValueChange(cb)` |
| （小程序无外设） | `BluetoothLeAdvertiser` + `BluetoothGattServer` | `peripheral::start(PeripheralConfig)` / `stop()` / `setDeviceName()` / `notify()` / `isConnected()` |
| （小程序无外设） | `onCharacteristicWriteRequest` | `onWriteRequest(cb)`（中心写了我们的特征） |
| （小程序无外设） | `onConnectionStateChange` | `onConnectionChange(cb)`（外设侧同样是这个回调） |
| — | — | `getCapabilities(out)` / `backendName()` / `getDiag(out)` / `version()` |

**返回约定**：所有接口同步返回 `Result{code,msg}`；`msg` 直接可打印（中文人话）。
错误码：`ERR_NOT_INIT/-1`、`ERR_POWER_OFF/-2`、`ERR_BUSY/-3`、`ERR_NOT_FOUND/-4`、`ERR_TIMEOUT/-5`、
`ERR_DISCONNECTED/-6`、`ERR_PARAM/-7`、`ERR_UNSUPPORTED/-8`、`ERR_NO_MEM/-9`、`ERR_IO/-10`。

**线程约定**：`on*` 回调在**库内部线程**被调用 —— 回调里只做轻活（存数据/发个通知），
重活切回自己的线程。所有"动作"接口可以从任意线程调用（库内自己投递）。

**平台差异一律走"能力门控 + 人话 hint"**，不在业务代码里写 `#ifdef 平台名`（组件规范 §2.5）。

---

## 4. 内部结构（改代码前看这里）

```
components/ble/
├─ include/zk/zk_ble.h     ← 唯一对外头文件（不含任何 btstack/gatt 类型）
└─ src/
   ├─ zkble_backend.h      ← 后端选择（显式 -D 优先；否则按 include 路径自动判定）
   ├─ zkble_common.h       ← 公共层（inline）：日志/工具/AD 解析/扫描过滤/DeviceCache/回调/Waiter
   ├─ zkble_public.cpp     ← 公共 API 实现（version/setLogHook/on*/offAll，**后端无关，必须一起编**）
   ├─ zk_ble.cpp           ← **btstack 后端**（F133/V85X）：串口 HCI + H5 + TLV + run loop 线程
   └─ zk_ble_gatt.cpp      ← **gatt 后端**（Z20/Z21/T113）：AIC USB + BlueZ 用户态 GATT（主从双角色）
```

> ⚠️ **公共 API 为什么单独一个 .cpp**：应用只 include 公开头（看不到定义），若把 `onDeviceFound()` 这类
> 写成内部头里的 `inline`，应用 TU 就链不上（子代理做链接验证时暴露的真问题）。所以：`zkble_public.cpp`
> **两个后端工程都必须编**；两个自检脚本会用 `nm` 核对它确实导出了 8 个公共符号。

**后端选择规则**（`zkble_backend.h`）：
1. 显式优先：`-DZKBLE_BACKEND_GATT=1` 或 `-DZKBLE_BACKEND_BTSTACK=1`（两个都给 → 编译期报错）；
2. 否则自动：include 路径里有 `btstack/btstack.h` → btstack（**已验证优先**）；否则有 `gatt/gatt-client.h` → gatt；
3. **同一平台只编一个后端**（两个后端 `.cpp` 都被 `#if` 互斥包住，不会重复符号）。

---

## 5. 怎么把它接进工程

**A) 源码引入（推荐起步）**
```
把 components/ble 的 include/ 与 src/ 加进工程构建（两个 .cpp：后端 + zkble_public.cpp）
工程 Manifest.xml 按平台声明底层包：
  · btstack 平台（F133/V85X）： <package id="btstack" version="1.7.2"></package>   ← 只这一个
  · gatt   平台（Z20/Z21/T113(EMMC)）： <package id="gatt" version="1.0.0"></package> ← 只这一个
```
- ⚠️ **本模块不依赖 easyui / zknet / base-utility**（读系统属性直接走 `/data/property`，日志可 `setLogHook` 挂到业务自己的日志系统）——
  别照抄老模板塞一堆用不上的包，那样会把链接搞成满屏 `undefined reference to FT_*/png_*/nvg*`。
- gatt 平台运行期要 `hciconfig` / `hcitool`：产品化请放进升级包的 `/res/bin`；开发期可放 `/data/bin`
  （模块内部有工具路径候选链 `/res/bin → /data/bin → /tmp/bin → /usr/bin → /bin`）。

**B) 依赖包引用（模块定型后）**
```xml
<package id="zkble" version="0.2.0"></package>
```

**必须一起编译的源文件**（组件规范 §2「四件套」）：
```
btstack 后端工程： src/zk_ble.cpp      + src/zkble_public.cpp
 gatt   后端工程： src/zk_ble_gatt.cpp + src/zkble_public.cpp
（include 路径给 components/ble/include）
```

**编译自检（本机已跑通，改动后必须重跑）**
```bash
wsl bash components/ble/scripts/compile_check.sh        # btstack 后端 + 公共 TU + 示例（F133 交叉编译器）
wsl bash components/ble/scripts/compile_check_gatt.sh   # gatt 后端 + 公共 TU（Z20/Z21 交叉编译器，nm 核符号）
```
> 另有两个**组件级工程验证**（工作区 `projects/` 下，仅公开 API）：
> `projects/zkble_comp_f133`（btstack 后端：真实 fun 标志编译+链接，无需设备）、
> `projects/zkble_comp_srv|cli`（gatt 后端：Z20 外设 × Z21 中心真机对传）。

---

## 6. 平台说明

见 [`platforms.md`](platforms.md)（逐平台：前置条件、实测值、限制、真机验收）——
含 §0.2「组件包里的 BLE 全景」、§0.3「Z20/Z21 主从双角色 + 真机验证 + 稳定性深度分析」。

**当前限制（必须知道）**
- btstack 包是 **BLE-only 构建**：只有 BLE + BLE HID（HOGP），**没有经典蓝牙**（SPP/A2DP/AVRCP/经典 HID 主机）。
- **外设/HID 侧**：btstack 后端不做；V85X 用 `blehid` 包（按键/触摸上报，开箱即用）、Z20/Z21 走 `gatt` 后端
  （`peripheral::*` 已实现；若只要"开箱外设服务"也可直接用 `ble` 包）。
- 版本按平台锁：F133 → `btstack 1.7.2`；V85X → `btstack 1.8.0`；Z20/Z21/T113(EMMC) → `gatt 1.0.0`。
- **Realtek 预初始化（下固件）不在本模块内**：用 `setPreinitHook()` 挂项目侧的 `rtk_init`（工程里 `src/ble/rtk/`）；
  模组是 8733bs 时若不挂 hook → `openAdapter` 直接返回 `ERR_UNSUPPORTED` 并说明原因（不静默失败）。
- 单连接模型（v1）：`connect()` 前需先 `disconnect()`。
- Z20/Z21 **无 TLV 落盘**：`getBondedDevices()` / `deleteBonding()` 返回 `ERR_UNSUPPORTED`（没假装返回空表）。
- Z20/Z21 的 LE 建链**由控制器残留链路影响**（见 platforms.md §0.3 稳定性分析）：本模块用"重试 + 复位"兜住，
  但**根因在原厂固件**；产品侧仍建议加应用层保活/断链检测。

---

## 7. 排错顺序（照走，别跳）

```
① openAdapter 失败 → getDiag()
     powered=0        → btstack：state_bt 没上电；gatt：aic_btusb.ko 没 insmod / hciattach 没起来
     preinit_ok=0     → btstack：setPreinitHook 没挂 / rtk_init 失败；gatt：hci0 没 up
     hci_state=1 卡住 → 线程模型/串口参数（本库应已处理；若自改过先怀疑自己）
② 扫不到设备 → getDiag().hci_events（0 = 芯片一个字节没回 → 回①）
③ 连不上      → 看 getDiag().connect_attempts（>1 = 重试过）与 hint；
                 Z20/Z21 常见：控制器残留链路 → 靠 reset + 重试；对端广播还在吗？距离？connectable？
④ 读写失败    → 先 getServices() 拿到 handle；写没回应看 properties
⑤ 通知不来    → subscribe() 返回 ok 吗？特征有 NOTIFY 属性吗？外设侧 notify() 要已订阅
⑥ 外设广播不上 → 看日志/Result（本库不静默丢广播）；Z20/Z21 断开后可能需要复位再开
```

---

## 8. 验收状态（诚实版）

| 项 | btstack 后端（F133/V85X） | gatt 后端（Z20/Z21） |
|---|---|---|
| 编译自检 | ✅ `compile_check.sh` rc=0 | ✅ `compile_check_gatt.sh` rc=0（z20/z21） |
| 真机：模组拉起 | ⏳（V851 上 btstack 路线已跑过扫描/连接） | ✅ Z20 `hci up OK` → 广播；Z21 扫描到 `zkswe ble` |
| 真机：中心（扫描→连接→发现→订阅） | ⏳ 待跑 | ✅ Z21 当中心连 Z20：`Connect done` → `0xfff1/0xfff2` → 订阅 CCCD |
| 真机：外设（广播 + GATT 服务） | ❌ 不支持（用 `blehid`） | ✅ Z20 当外设：`adv enable ok` + 收 `Connect from` + ATT 读写 |
| 真机：应用内（zkgui 里跑） | ⏳ 待跑 | ✅ 两端应用同屏显示「已连接」 |
| 外设 notify 上行 | — | ⏳ 组件形态待跑（demo 路线已跑通） |

> 真机记录与证据链（日志原话、跑法、坑）全部在 [`platforms.md`](platforms.md)，本节只给结论。

---

## 9. 参考

- 经验来源：`knowledge/hardware/bt-rtl8733bs-bringup.md`、`references/kb/btstack-package.md`、
  `references/kb/v85x-ble-hid-touch.md`、`references/kb/btstack-package.md`（§1.1 能力边界）
- 本仓现成范本：`projects/BTHomeTempHum-F133`（btstack 扫描，最干净）、
  `projects/LearningProject/V851ExtendedScreen_ap_p2p`（外设 + 跨线程 + TLV；`src/ble/rtk/` 是预初始化实现）
- Z20/Z21 双角色参考：`git.com/AppGroup/Sample` 的 `BleClientDemo` / `BleServerDemo`，
  本仓真机验证工程 `projects/zbble_cli`（Z21 中心）、`projects/zbble_srv`（Z20 外设）
