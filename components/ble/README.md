# ble —— BLE 门面 `zk::ble` v0.2（**头文件 + 静态库**发布）

> 把蓝牙收拾成微信小程序 `wx.*` 那种用法：**业务/AI 只面对一套接口，脏活全在库里**。
> **中心侧**照微信那套（`openAdapter` → 扫描 → 连接 → GATT 读写订阅）；
> **外设侧**微信没有，按 Android `BluetoothGattServer` + `BluetoothLeAdvertiser` 的形状给（`zk::ble::peripheral::*`）。
>
> **交付形态（v0.2.1 起）**：只发 **`include/zk/zk_ble.h`（唯一对外头） + `lib/<平台>/libzkble.a` + `lib/BUILD_INFO.md`（构建凭据）**。
> **源码不随本仓发布**（内部私有维护）；要用就直接链库，不需要也不应该看实现。
>
> 一个 API 面、两个平台后端（业务代码不改，只看 `getCapabilities()` / `backendName()`）：
>
> | 平台 | 后端 | 中心 | 外设 | 静态库 | 说明 |
> |---|---|---|---|---|---|
> | F133 | `btstack` 1.7.2 | ✅ | ❌ | `lib/f133/libzkble.a` | 串口 HCI（H5）；外设请走别的路线 |
> | V85X | `btstack`（本地 1.7.2 构建） | ✅ | ❌ | `lib/v85x/libzkble.a` | 串口 HCI + 预初始化钩子；**外设/触摸上报用 `blehid` 包**|
> | Z20 | **`gatt` 1.0.0**| ✅ | ✅ | `lib/z20/libzkble.a` | AIC USB 模组 + BlueZ 用户态 GATT，**主从双角色**（真机跑通） |
> | Z21 | **`gatt` 1.0.0**| ✅ | ✅ | `lib/z21/libzkble.a` | 同上（真机跑通） |
> | T113 / T113EMMC | `gatt` 1.0.0 | ⏳ | ⏳ | **待补**| 本机注册表没有该平台的 `gatt` 包 → 未构建（**不拿别的平台的头凑**，见 platforms.md §0.6） |
>
> 立项：2026-09-13（现场反馈：「模仿 Android 或微信的 API 封装一层，最终暴露给 AI 开发的就是 wxapi 这种」）；
> 统一：2026-09-14（现场反馈：「蓝牙部分都统一按照昨天定义的新 API，参考微信的方式」→ 组件收口为一个 API 面 + 两个后端，Z20/Z21 从"只做外设"改成**双角色**）；
> 转为二进制发布：2026-09-14（现场反馈：「验证好了后把你的程序做成静态库+头文件发布给到 open 版本 MCP 里面。不释放源码了」）。
>
> **版本记录**
> - **v0.2.1（2026-09-14）**发布形态改为「头 + 静态库」：新增 `lib/{f133,v85x,z20,z21}/libzkble.a` + `lib/BUILD_INFO.md`
>   （含每平台 sha256/符号数/工具链/依赖版本）；新增 `scripts/verify_lib_symbols.py`（纯 Python 解析 ELF，**不依赖 nm**：
>   Windows 版 binutils 的 nm 缺 `liblto_plugin-0.dll` 会直接报错）；**移除源码**（`src/`、`zkble_*.h`、源码侧编译脚本）。
> - v0.2.0（2026-09-14）统一 API 面 + 两个后端（gatt 后端 Z20/Z21 **主从双角色**），**组件级真机验证通过**（Z20 外设 × Z21 中心，五条验收全过）；含三个真机 bug 修复（uuid 取空 / 自建表拿不到 value_handle / 广播 status=12）。
> - v0.1.0（2026-09-13）首版：btstack 后端（适配器/扫描/连接/GATT 读写订阅/诊断）；外设留口。

---

## 1. 它解决什么问题

蓝牙的门槛不在协议，在**前置条件与规矩**（而且**每个平台的前置条件还不一样**）：

| 坑（全部来自真机记录） | 库里的处置 |
|---|---|
| V85X：`state_bt` 没上电（出厂 off） | `openAdapter()` 自动 写0→50ms→写1→300ms ×2 轮 + **回读确认**|
| V85X：Realtek 必须先 hciattach | 预留 `setPreinitHook()`，由项目侧挂 `rtk_init`（见 §6） |
| Z20/Z21：BT 是 **AIC USB 模组**（`aic_btusb.ko`），不是串口 HCI | 自动 `insmod` / 拉 `hciattach` 服务 + `hciconfig hci0 up` |
| Z20/Z21：`/res` 只读、**没有 `/res/bin`**（工具找不到） | 工具路径候选链 `/res/bin → /data/bin → /tmp/bin → /usr/bin → /bin` |
| Z20/Z21：**断开后控制器残留链路**（`0x0B`/EIO），下一次连接必失败 | `connect()` 自动重试 + 重试前 `hciconfig hci0 reset`（`Config.connect_retry` / `reset_before_retry`） |
| 外设：断开后重开广播失败却只打一行日志（**静默丢广播**） | `adv enable` 校验 HCI 状态 → 失败先 disable 再 enable → 仍失败**明确报错**|
| 外设：控制器已 enable 广播时改参数被拒（`status=12`） | 设参数前恒发一次 `LE Set Advertise Enable(0)`，被拒则复位 + 重试一次 |
| 串口/波特率/校验写死 | 自动探测 `ttyS1`(F133)/`ttyS2`(V85X)+`Config` 可覆盖；H5+偶校验默认 |
| 跨线程调协议栈 → 卡 `INITIALIZING` | 库内固定线程模型（run loop/mainloop 独占一线程 + 任务投递 + 条件变量等结果） |
| 判据看错（`0x6E` 当芯片回应） | `getDiag()` 只统计真实事件 0x01~0x5F，`transport_sent` 单列 |
| 失败静默（线程 `return NULL`） | 每个失败都带 `Result{code,msg}` + `getDiag().hint` |

---

## 2. 快速开始

### 2.1 中心侧（扫描 → 连接 → 读写订阅）

```cpp
#include "zk/zk_ble.h"                                   // 组件唯一对外头

zk::ble::Config cfg;                                     // 默认值即可
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

完整示例：[`example/main_example.cc`](example/main_example.cc)。

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
zk::ble::peripheral::start(pc);                          // 建表 + 广播（Z20/Z21 可用）

zk::ble::peripheral::notify("fff1", std::string("\x01\x02", 2));   // 主动上报
```

完整示例：[`example/peripheral_example.cc`](example/peripheral_example.cc)。
**先查能力**：`zk::ble::getCapabilities(cap)` → 在 F133/V85X 上 `cap.peripheral == false`，
`peripheral::start()` 返回 `ERR_UNSUPPORTED` 并在 msg 里指路（V85X 用 `blehid` 包），**不假装能用**。

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
| （小程序无外设） | `onCharacteristicWriteRequest` | `onWriteRequest(cb)` |
| （小程序无外设） | `onConnectionStateChange` | `onConnectionChange(cb)`（外设侧也是这个回调） |
| — | — | `getCapabilities(out)` / `backendName()` / `getDiag(out)` / `version()` |

**返回约定**：所有接口同步返回 `Result{code,msg}`；`msg` 直接可打印（中文人话）。
错误码：`ERR_NOT_INIT/-1`、`ERR_POWER_OFF/-2`、`ERR_BUSY/-3`、`ERR_NOT_FOUND/-4`、`ERR_TIMEOUT/-5`、
`ERR_DISCONNECTED/-6`、`ERR_PARAM/-7`、`ERR_UNSUPPORTED/-8`、`ERR_NO_MEM/-9`、`ERR_IO/-10`。

**线程约定**：`on*` 回调在**库内部线程**被调用 —— 回调里只做轻活（存数据/发个通知），
重活切回自己的线程。所有"动作"接口可以从任意线程调用（库内自己投递）。

---

## 4. 怎么把它接进工程（二进制引入）

```
components/ble/
├─ include/zk/zk_ble.h          ← 拷进工程（放到能被 include 到的位置）
├─ lib/<平台>/libzkble.a        ← 按目标平台拷一个（不要混用别的平台）
└─ lib/BUILD_INFO.md            ← 这个二进制是怎么来的（工具链/依赖版本/sha256）
```

**步骤**
1. 拷 `include/zk/` 到工程（例：`src/zk/zk_ble.h`，或加进 include 路径）；
2. 拷目标平台的 `libzkble.a` 到工程（例：`src/dependencies/lib/`，或任意目录）；
3. 工程 `Manifest.xml` 声明**该平台的底层包**（见 [`Manifest.xml`](Manifest.xml)）：
   - btstack 后端（F133/V85X）：`btstack` + `easyui` +（可选 `base-utility`/`log`/`zkhardware`）
   - gatt 后端（Z20/Z21）：**只**`gatt 1.0.0`（另需运行期有 `hciconfig`/`hcitool`）
4. 构建里链接 `libzkble.a`（放在底层包之后，或用 `--start-group` 兜顺序）。

**CMake 片段（fun/IDE 生成的构建里加）**
```cmake
target_include_directories(${PROJECT_NAME} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/zk)
target_link_libraries(${PROJECT_NAME} zkble)      # zkble = 链接到 libzkble.a 的 imported target
```

**⚠️ 工具链/ABI 必须与库一致**（`lib/BUILD_INFO.md` 里写了每个库的构建环境）：

| 平台 | 编译器 | libc |
|---|---|---|
| f133 | `riscv64-unknown-linux-musl-g++`（Xuantie 900 V2.10.2） | musl |
| v85x | `arm-unknown-linux-musleabihf-g++` | musl |
| z20 / z21 | `arm-pc-linux-gnueabihf-g++`（8.3.0） | glibc |

**符号自检（拿到库先跑一次，确认库完整）**
```bash
python components/ble/scripts/verify_lib_symbols.py
# [PASS] f133   .a=408KB 公开 API 30/30
# [PASS] v85x   .a=118KB 公开 API 30/30
# ...
```

---

## 5. 平台说明

见 [`platforms.md`](platforms.md)（逐平台前置条件、实测值、限制、真机验收）；重点两节：
- §0.4「统一门面与两个后端」（本模块内部结构 / 后端选择规则）
- §0.5「组件级真机复验」（Z20 × Z21 五条验收 + 三个真机 bug 的根因）
- §0.6「静态库矩阵与构建口径」（每个库用什么工具链/依赖构建、哪些平台待补、为什么不拿别的平台的头凑）

**当前限制（必须知道）**
- btstack 包是 **BLE-only 构建**：只有 BLE + BLE HID（HOGP），**没有经典蓝牙**（SPP/A2DP/AVRCP/经典 HID 主机）。
- **外设/HID 侧**：btstack 后端不做；V85X 用 `blehid` 包（按键/触摸上报，开箱即用）、Z20/Z21 用本组件的 gatt 后端
  （`peripheral::*` 已实现；只要"开箱外设服务"也可直接用 `ble` 包）。
- **Realtek 预初始化（下固件）不在库内**：用 `setPreinitHook()` 挂项目侧 `rtk_init`（工程里 `src/ble/rtk/`）；
模组是 8733bs 时若不挂 hook → `openAdapter` 直接返回 `ERR_UNSUPPORTED` 并说明原因（不静默失败）。
- 单连接模型（v1）：`connect()` 前需先 `disconnect()`。
- Z20/Z21 **无 TLV 落盘**：`getBondedDevices()` / `deleteBonding()` 返回 `ERR_UNSUPPORTED`（没假装返回空表）。
- Z20/Z21 的 LE 建链受**控制器残留链路**影响：库里用"重试 + 复位"兜住，**根因在原厂固件**；产品侧仍建议加应用层保活/断链检测。
- **T113 / T113EMMC 的库还没出**（本机没有该平台的 `gatt` 包）：**不要**拿 z20/z21 的头去凑（结构体 ABI 可能不同）——
内部装好该平台的 `gatt 1.0.0` 后重跑构建脚本即可产出（见 platforms.md §0.6）。

---

## 6. 排错顺序（照走，别跳）

```
① openAdapter 失败 → getDiag()
     powered=0        → btstack：state_bt 没上电；gatt：aic_btusb.ko 没 insmod / hciattach 没起来
     preinit_ok=0     → btstack：setPreinitHook 没挂 / rtk_init 失败；gatt：hci0 没 up
     hci_state=1 卡住 → 线程模型/串口参数（库内已处理；若自改过先怀疑自己）
② 扫不到设备 → getDiag().hci_events（0 = 芯片一个字节没回 → 回①）
③ 连不上      → 看 getDiag().connect_attempts（>1 = 重试过）与 hint；
                 Z20/Z21 常见：控制器残留链路 → 靠 reset + 重试；对端广播还在吗？距离？connectable？
④ 读写失败    → 先 getServices() 拿到 handle；写没回应看 properties
⑤ 通知不来    → subscribe() 返回 ok 吗？特征有 NOTIFY 属性吗？外设侧 notify() 要已订阅
⑥ 外设广播不上 → 看日志/Result（库不静默丢广播）；Z20/Z21 断开后可能需要复位再开
⑦ 链接报未定义 → 库的公开 API 是否全在（跑 scripts/verify_lib_symbols.py）；
底层包是否声明（btstack+easyui / gatt）；工具链/libc 是否与库一致（见 §4）
```

---

## 7. 验收状态（诚实版）

| 项 | btstack 后端（F133/V85X） | gatt 后端（Z20/Z21） |
|---|---|---|
| 静态库 | ✅ `lib/f133`、`lib/v85x`（各 30/30 公开 API） | ✅ `lib/z20`、`lib/z21`（各 30/30 公开 API） |
| 库符号自检 | ✅ `scripts/verify_lib_symbols.py` 全 PASS | ✅ 同左 |
| 真机：模组拉起 | ⏳（V851 上 btstack 路线跑过扫描/连接） | ✅ Z20/Z21：`hci0 已存在→跳过 insmod` / `hciconfig hci0 up` → 适配器就绪 |
| 真机：中心（扫描→连接→发现→订阅→读写） | ⏳ 待跑 | ✅ 见 §真机证据（Z21 → Z20） |
| 真机：外设（广播 + GATT 服务 + 收写 + notify） | ❌ 不支持（用 `blehid`） | ✅ 见 §真机证据（Z20 侧） |
| 真机：连接重试 + 复位 | ⏳ 待跑 | ✅ 第 1 次 ETIMEDOUT → 自动 `hciconfig hci0 reset` → 第 2 次成功 |
| 真机：**组件级**（不用 demo 代码，只用公开 API） | — | ✅ 见下 |

**真机证据（2026-09-14，组件级验证工程 `projects/zkble_comp_srv`(Z20 外设) / `zkble_comp_cli`(Z21 中心)）**
```
中心（Z21）：FOUND DC:84:03:A1:2D:84 name=zkswe ble → svc fff0 / chr fff1 props=0x09 handle=0x0003 /
             chr fff2 props=0x06 handle=0x0006 → subscribe ok → readValue len=5 → writeValue code=0 → notify_count=4
外设（Z20）：peripheral::start → code=0 → 中心 CONNECTED → WRITE char=fff2 len=4 data=50494e47("PING")
             → NOTIFY 'N18/N21/N24/N27' → code=0 → 中心断开后「广播已恢复」
```

> 真机记录与证据链（日志原话、跑法、坑）全部在 [`platforms.md`](platforms.md)，本节只给结论。

---

## 8. 维护者须知（源码在哪里）

- **源码不随本仓发布**，在内部私有目录：`<workspace>/private/components-ble/{include,src,example,scripts}`，
构建脚本 `scripts/build_libs.ps1`（一次出四平台 `libzkble.a` 并刷新 `lib/BUILD_INFO.md`）、
源码侧编译自检 `scripts/compile_check.sh`（f133/btstack）与 `scripts/compile_check_gatt.sh`（z20/z21/gatt）。
- 改完源码 → 跑 `build_libs.ps1` 产出新库 → 更新 `lib/BUILD_INFO.md` → 提交（只提交 `include/` + `lib/` + 文档）。
- 门面头 `include/zk/zk_ble.h` 属于**公开 API 契约**：改了要同步 README §3 表与 `verify_lib_symbols.py` 的 API 清单。
