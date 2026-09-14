# ble —— BLE 门面 `zk::ble` v0.1

> 把 btstack 收拾成微信小程序 `wx.*` 那种用法：**业务/AI 只面对 20 来个接口，脏活全在库里**。
> 底层：btstack 1.7.2（**BLE-only 构建**）。平台：F133、V85X。
> 立项：2026-09-13（沛哥：「模仿 Android 或微信的 API 封装一层，最终暴露给 AI 开发的就是 wxapi 这种」）

---

## 1. 它解决什么问题

btstack 的门槛不在协议，在**前置条件与规矩**：BT 要先在 sysfs 上电、Realtek 模组要先跑 hciattach
（同步握手/读ROM/下固件/切波特率）、传输必须 H5+偶校验、所有 API 只能在 run loop 线程里调、
`hci_add_event_handler` 必须在 `hci_init` 之后、上电后要等 `HCI_STATE_WORKING`、
`0x6E` 只是"我发出去了"不是芯片回应……这些在库内做掉，业务只写业务。

| 坑（来自 bring-up 记录） | 本模块的处置 |
|---|---|
| `state_bt` 没上电（出厂 off） | `openAdapter()` 自动 写0→50ms→写1→300ms ×2 轮 + **回读确认** |
| Realtek 必须先 hciattach | 预留 `setPreinitHook()`，由项目侧挂 `rtk_init`（见 §5） |
| 串口/波特率/校验写死 | 自动探测 `ttyS1`(F133)/`ttyS2`(V85X)+`Config` 可覆盖；H5+偶校验默认 |
| 跨线程调 btstack → 卡 `INITIALIZING` | 库内固定线程模型（run loop 独占一线程 + 任务投递 + 条件变量等结果） |
| 判据看错（`0x6E` 当回应） | `getDiag()` 只统计真实事件 0x01~0x5F，`transport_sent` 单列 |
| 失败静默（线程 return NULL） | 每个失败都带 `Result{code,msg}` + `getDiag().hint` |

---

## 2. 快速开始（照抄就能跑）

```cpp
#include "zk/zk_ble.h"

zk::ble::openAdapter();                                  // 上电+预初始化+H5+TLV+线程，一步到位

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

完整示例见 [`example/main_example.cc`](example/main_example.cc)。

---

## 3. API 一览（对标微信小程序 / Android）

| 微信小程序 | Android | `zk::ble` |
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
| （小程序无外设） | `BluetoothGattServer` | `peripheral::*` —— **二期**（当前返回 `ERR_UNSUPPORTED`，不假装能用） |
| — | — | `getDiag(out)` / `version()` |

**返回约定**：所有接口同步返回 `Result{code,msg}`；`msg` 直接可打印。
错误码：`ERR_NOT_INIT/-1`、`ERR_POWER_OFF/-2`、`ERR_BUSY/-3`、`ERR_NOT_FOUND/-4`、
`ERR_TIMEOUT/-5`、`ERR_DISCONNECTED/-6`、`ERR_PARAM/-7`、`ERR_UNSUPPORTED/-8`、`ERR_NO_MEM/-9`、`ERR_IO/-10`。

**线程约定**：`on*` 回调在**库内部线程**被调用 —— 回调里只做轻活（存数据/发个通知），
重活切回自己的线程。所有"动作"接口可以从任意线程调用（库内自己投递）。

---

## 4. 怎么把它接进工程

**A) 源码引入（起步用这个）**
```
把 components/ble/{include,src} 拷进工程 src/ 下  →  构建里包含 src/zk_ble.cpp
工程 Manifest.xml 声明底层包（见 Manifest.xml）
```
编译期需要 include 路径：`components/ble/include` + btstack/easyui 的 include（由包自动带）。

**B) 依赖包引用（模块定型后）**
```xml
<package id="zkble" version="0.1.0"></package>
```

**编译验证命令（本机 F133，交叉编译器在 WSL 里跑）**
```bash
riscv64-unknown-linux-musl-gcc -c src/zk_ble.cpp -Iinclude \
  -I<btstack 包>/include -I<easyui 包>/include -o /tmp/zk_ble.o
```

---

## 5. 平台说明

见 [`platforms.md`](platforms.md)（F133 / V85X 逐条：前置条件、实测值、限制、真机验收）。

**当前限制（必须知道）**
- 本包 btstack 是 **BLE-only 构建**：只有 BLE + BLE HID（HOGP）；**没有经典蓝牙**（SPP/A2DP/AVRCP/经典 HID 主机）。
- **外设/HID 侧不要用本模块**：V85X 有 `blehid` 包、Z20/Z21 有 `ble` 包（BlueZ/libgatt），已经封好；
  本模块专注**中心侧**（扫描 / 连接 / GATT 客户端）——这是目前只有 btstack 才提供的能力。
  详见 [`platforms.md` §0.2「组件包里的 BLE 全景」](platforms.md)。
- 版本按平台锁：F133 → `btstack 1.7.2`；V85X → `btstack 1.8.0`（V85X 同时声明 `blehid`）。
- **Realtek 预初始化（下固件）不在本模块内**：用 `setPreinitHook()` 挂项目侧的 `rtk_init`（工程里 `src/ble/rtk/` 那套），
  或直接用 `blehid` 包（其 `ble_params_t.module` 已内置 AIC/RTK 分支）；
  模组是 8733bs 时若不挂 hook → `openAdapter` 直接返回 `ERR_UNSUPPORTED` 并说明原因（不会静默失败）。
- 单连接模型（v1）：`connect()` 前需先 `disconnect()`。

---

## 6. 排错顺序（照走，别跳）

```
① openAdapter 失败 → getDiag()
     powered=0        → state_bt 没上电（节点不存在/权限/属性门）
     preinit_ok=0     → setPreinitHook 没挂 / rtk_init 失败（看它的日志）
     hci_state=1 卡住 → 线程模型/串口参数（本库应已处理；若自改过先怀疑自己）
② 扫不到设备 → getDiag().hci_events（0 = 芯片一个字节没回 → 回①）
③ 连不上      → 设备是 connectable 吗？距离？广播还在吗？扫描是否还在跑（库内会先停扫）
④ 读写失败    → 先 getServices() 拿到 handle；写没回应看 properties
⑤ 通知不来    → subscribe() 返回 ok 吗？特征有 NOTIFY 属性吗？
```

---

## 7. 验收状态（诚实版）

| 项 | 状态 |
|---|---|
| 接口面 + 头文件 | ✅ v0.1 定稿（本文档 §3） |
| 编译（F133 交叉编译，单文件 `-c`） | ✅ 见 §4 命令（记录在案） |
| F133 真机（BTHome 扫描 → 连接 → 通知） | ⏳ 待跑（下一里程碑） |
| V85X 真机（RTL8733BS 上电 + hciattach + 扫描） | ⏳ 待跑 |
| 外设 / HID | ⏳ 二期 |

**版本记录**：v0.1.0（2026-09-13）首版：适配器/扫描/连接/GATT 读写订阅/诊断；外设留口。

---

## 8. 参考

- 经验来源：`knowledge/hardware/bt-rtl8733bs-bringup.md`、`references/kb/btstack-package.md`（§1.1 能力边界）、`references/kb/v85x-ble-hid-touch.md`
- 本仓现成范本：`projects/BTHomeTempHum-F133`（BLE 扫描，最干净）、
  `projects/LearningProject/V851ExtendedScreen_ap_p2p`（外设 + 跨线程 + TLV；`src/ble/rtk/` 是预初始化实现）
