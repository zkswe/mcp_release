# ble 模块 —— 平台说明

> 逐平台写清"能不能用、前置条件、实测值、限制、怎么验收"。没实测的标 `未验证`，不写"应该可以"。
> 数据来源：本仓实测记录（2026-09-12~13）+ 包/源码逐条核对 + 2026-09-13 真机（V85X SPINOR）快照。

---

## 0. 汇总

| 平台 | 可用性 | BT 模组 | BT 串口 | 传输/校验 | 上电节点 | 预初始化 | 备注 |
|---|---|---|---|---|---|---|---|
| **F133**（RISC-V） | ✅ 可用（链路最干净） | 非 Realtek 类 | `/dev/ttyS1` | H5 + 无校验 | 无 | 不需要 | 扫描类场景首选（组件例程里有范本工程） |
| **V85X**（V851 系列） | ✅ 可用（坑最多） | **RTL8733BS**| `/dev/ttyS2` | H5 + **偶校验 8E1**+ 无流控 | `state_bt`（出厂 off） | **必须**（Realtek 8733bs） | 需 `setPreinitHook()` 挂 rtk_init |
| **Z20 / Z21**| 🟡 支持（**gatt 后端，主从双角色**，真机跑通） | AIC USB 模组（`aic_btusb.ko`） | 无串口（USB HCI） | 走 `gatt 1.0.0`（BlueZ 用户态，不经 H4/H5 参数） | hci0（`hciconfig hci0 up`） | 不需要（驱动 + hciconfig 拉起） | ⚠️ 中心+外设都真机跑过；见 §0.3 / §0.4 |
| T113 | ❌ gatt 后端已就绪（**未真机**） | AIC USB 模组（同 Z20 族） | 无串口（USB HCI） | 走 `gatt 1.0.0` | hci0 | 不需要 | 包在（z20/z21/t113/t113emmc/v85x 均有）；额外要 `hcitool cmd 0x03 0x0003` 拉起 LE/BR-EDR |

> 口径修正（2026-09-13）：Z20/Z21 **是支持 BLE 的**（但仅 AIC 8800DL 模组有 BLE），电子价签 tag 本就跑在 BLE 方案上。
> 模块侧已预留 **AIC 分支**（H4 + 流控 + 无校验，参数自动判定，`Config.flowcontrol/parity` 可覆盖），
> 剩余阻塞是 **该平台能否拿到 btstack 包**与 **串口/上电节点的实测值**。

### 0.1 传输参数自动判定（模块内实现）

| 分支 | 判定条件 | 传输 | 流控 | 校验 | 波特率 |
|---|---|---|---|---|---|
| Realtek（8733bs） | `persist.wifi.module` 含 `8733` | H5（必须过 SLIP） | off | **偶校验 8E1**| 115200 起步 → 预初始化切 1500000 |
| AIC / 其它 | 否则 | H4（`Config.prefer_h5=true` 可强行 H5） | on（H5 时 off） | 无 | 1500000 |

`Config.flowcontrol` / `Config.parity` 传 ≥0 即显式覆盖自动值（换模组/换板子时的后门）。

### 0.2 组件包里的 BLE 全景（2026-09-13 实测下载核对）

需求方提示「关于 BLE 的可以从组件包里面搜索」→ 实际扫包结果（可直接 `curl` 下载核对）：

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
| V85X | **`blehid`**| 1.1.3 | **BLE HID 外设**（基于 btstack，已封好）：按键/触摸上报、手机类型、RSSI | `ble/server.h` | `libblehid.a` 115KB |
| Z20 | **`ble`**| 1.1.1 | **BLE 外设服务（BlueZ/libgatt）**：设备名 + GATT 服务 + 收包回调 | `ble/bluetooth_service.h` | `libble.a` + `libgatt-server.a` + `bin/{gattserverbin,hciattach,hciconfig,hcitool}` |
| Z21 | **`ble`**| 2.1.0 | 同上 | 同上 | 同上 |
| Z20 | **`gatt`**| 1.0.0 | **BlueZ 用户态 GATT 库（中心 + 外设双角色）**：`gatt-client` / `gatt-server` / `gatt-db` / `hci` / `hci_lib` / `l2cap` / `mainloop` / `uuid` | `gatt/*.h`（19 个头） | `libgatt.a`（静态库 target `gatt`） |
| Z21 | **`gatt`**| 1.0.0 | 同上（实测 `fun install` 拉取成功） | 同上 | 同上 |
| T113 / T113EMMC | **`gatt`**| 1.0.0 | 同上（仓库元数据查到，未在本机安装） | 同上 | 同上 |
| V85X | **`gatt`**| 1.0.0 | 同上（仓库元数据查到，未在本机安装） | 同上 | 同上 |

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
- **中心侧（扫描 / 连接 / GATT 客户端）有两条路**：① btstack（F133 1.7.2 / V85X 1.8.0）；
  ② **Z20/Z21/T113/T113EMMC/V85X 的 `gatt` 1.0.0 包**（BlueZ 用户态 GATT 库，`gatt-client` + `gatt-server` 都在），
参考实现见 Sample 仓库 `BleClientDemo` / `BleServerDemo`（详见 §0.3）。
  ⚠️ 2026-09-13 版本文件曾写「Z20/Z21 目前没有中心侧包」——**该结论已于 2026-09-14 由需求方指路 + 本仓核对推翻**。
  `zk::ble` 要补的那一层不变（统一门面），但 Z20/Z21 后端**可以做成双角色**，不是只能做外设。
- 电子价签 `tag` 工程就是 `ble` 那套的实例（其 `src/ble/bluetooth_service.cpp` + BlueZ/ATT + `aic_btusb.ko` 驱动）。
- 版本要按平台锁：F133 → `btstack 1.7.2`；V85X → `1.8.0`（并且 V85X 要把 `blehid` 一并声明）；
  Z20/Z21/T113/T113EMMC（含 V85X）走 `gatt 1.0.0` 时**要在 Manifest 里显式声明 `gatt`**，并把
  `hciconfig` / `hcitool` 两个二进制放进 `src/dependencies/bin/`（见 §0.3）。

### 0.3 Z20/Z21 主从双角色 —— `gatt` 包 + Sample 两个 demo（2026-09-14 核对）

**来源**：需求方指路 `http://git.com/AppGroup/Sample`（branch master，本机可 clone：`git clone http://git.com/AppGroup/Sample.git`）。

| 目录 | 角色 | 关键文件 | 对外 API | 平台块 |
|---|---|---|---|---|
| `Sample/BleClientDemo` | **主机 / 中心（Central）**| `src/ble/client.cpp|.h`、`src/logic/mainLogic.cc` | `ble::client_start/stop`、`scan_start(filter)`/`scan_stop`、`get_scan_bt_dev_list_size`/`get_scan_bt_dev_by_index`、`connect(addr)`/`disconnect`/`is_connected`、`add_event_cb`（`E_BLE_EVENT_SCAN_*` / `CONNECT` / `DISCONNECT` / `INTERACT_READY`） | Z21 / Z20 / T113 / T113EMMC |
| `Sample/BleServerDemo` | **从机 / 外设（Peripheral）**| `src/ble/server.cpp|.h` | `ble::server_start/stop`、`add_event_cb`；设备名/GATT 服务特征改在 `server.cpp`（`BT_NAME`、`UUID_SERVICE/CHAR1/CHAR2`、`_char*_read_cb` / `_char*_write_cb`） | Z21 / Z20 / T113 / T113EMMC / V85X |

**共同前置条件（两 demo 都一样，`说明.txt` 明说 + 代码里可见）**
1. **Manifest 要声明 `gatt 1.0.0`**（两 demo 的 `enableOnPlatforms` 各平台块都写了）。
2. **必须把 `hciconfig` / `hcitool` 放到 `src/dependencies/bin/`**（demo 的 `tools/z20_z21`、`tools/t113`、`tools/t113emmc` 下给了对应平台二进制，自行拷贝）。
运行期代码直接 `system("/res/bin/hciconfig hci0 up")` + `system("/res/bin/hcitool cmd 0x03 0x0003")`（拉起 LE/BR-EDR），停止时 `hciconfig hci0 down` + `system("rmmod aic_btusb")`
   → 说明 Z20/Z21 侧 BT 是 **AIC USB 模组（`aic_btusb.ko`）**，不是串口 HCI（与 §0 表里"AIC 8800DL"一致）。
3. 两 demo 都先碰 WiFi（`NETMANAGER->getWifiManager()`），与 `ble` 包"开蓝牙自动开 WiFi"同源。

**实测（2026-09-14，本机 Z21 工具链）**
- `gatt` 在 z20 / z21 / t113 / t113emmc / v85x 包仓库都有 `1.0.0`（`flythings_package_search` 查得）；本机 `fun install` 实测拉到
  `~/.fun/registry/public/z21/gatt/1.0.0`，19 个头，`gatt-client.h` + `gatt-server.h` **双角色齐备**。
- 两 demo 复制到 `temp/blecli_test`、`temp/blesrv_test`，`fun install` + `fun build`（-p Z21）**都出 libzkgui.so**✅。
唯一障碍：demo 里 `easyui 2.2.0` / `base-utility 10.1.3` **太老**（新生成模板要 `base::UiHandler::hasTimerRegistration`）
  → 提到 `easyui 2.6.0` + `base-utility 10.9.3`（z21 仓库现有版本）即编过。
**真机验证（2026-09-14）—— 已用两台整机跑通「主从对传」**

设备：Z20 整机（内网地址用 `<Z20-IP>` 表示，`Zkswe_SSD20X_SPINOR`，做**外设**）、
Z21 整机（`<Z21-IP>`，`Zkswe_SSD21X_SPINOR`，做**中心**）。

| 侧 | 证据（日志原话） |
|---|---|
| Z20 外设 | `[ble] hci up OK` → `Started listening on ATT channel` → `adv enable ok` → `evt=0 START(广播已开)` |
| Z21 中心 | `scan start...` → `SCAN_DATA addr=<Z20 的 BD 地址> name=zkswe ble` → `connect` → `connected=1` → GATT dump `charac 0x0003 uuid 0000fff1` / `0x0006 uuid 0000fff2` → `evt=5 INTERACT_READY(服务/特征就绪)` → `已连接：zkswe ble` |
| Z20 侧同步看到 | `Connect from <Z21 的 BD 地址>` → `evt=2 CONNECT` → ATT 报文（Read By Grp Type / Read By Type / **Write Req handle 0x0004 = 订阅 CCCD**）→ 断开后 `adv enable ok` 自动恢复广播 |
| 旁证 | Z21 侧 `hcitool lecc <Z20 的 BD 地址>` → `Connection handle 17`，`hcitool con` 为 `lm MASTER`（控制器层发起连接这条路也通） |

**跑法（重要，`fun launch` 在当前环境用不了时的替代）**
- `fun launch` 在本机（同时挂着 USB V85X + 两台网络设备）会报 `"host:transport …" FAIL: more than one device/emulator`，`-s`（IP / IP:port）都一样 → 只能单设备时可用。
- 替代：把 demo 的 ble 代码做成 **bin 工具**（`fun.json` 里 `"type": "executable"`）→ `fun build -p z20/z21` 出 ELF → `adb -s <serial> push … /tmp/ && chmod 777 && /tmp/xxx`。
参考工程：Z20 外设 / Z21 中心各一；两者用 `src/comp/zk_compat.h` 把 easyui/zknet/base-utility 垫掉（只依赖 `gatt`），否则可执行体链接会因 `-Wl,-z,defs` 报 `libeasyui.so: undefined reference to FT_*/png_*/nvg*/MI_SYS_*`。
- **Z21 整机 `/res` 是只读 squashfs且没有 `/res/bin`**（Z20 有）→ demo 里写死的 `system("/res/bin/hciconfig hci0 up")` 会直接失败；本次把工具路径改成兜底查找（`/res/bin` → `/data/bin` → `/tmp/bin` → `/usr/bin` → `/bin`），把 `hciconfig`/`hcitool`（来自 demo `tools/z20_z21/`）推到 `/data/bin` 即可。产品化还是要靠升级包把这两个工具放进 `/res/bin`。
- AIC 模组：`/lib/modules/<ver>/aic_btusb.ko` 存在时由代码自行 `insmod`（Z20 本次就是这条路），否则回退 `hciattach` 服务；`hciconfig hci0 up` 后 `hci0` 就绪。

**坑（以本次实测为准）**
- demo 里 `easyui 2.2.0 / base-utility 10.1.3` **太老**，配上现在的 fun 生成模板会报 `hasTimerRegistration` 缺失 → 升到 z21 的 `easyui 2.6.0 + base-utility 10.9.3`（z20 用 `3.0.0 + 10.8.5`）。
- demo 源码里 `LOGE(...)` **不带分号**（因为 easyui 的 `utils/Log.h` 在 `USE_ANDROID_LOG` 下宏尾自带分号）→ 自己写日志垫片时必须让宏尾带 `;`，否则 `expected ';' before 'return'`。
- 首次连接偶发失败（客户端 `Failed to connect`，服务端未收到连接），重跑即成功 → 已由 §0.3 末尾的**深度分析**定位（控制器残留链路状态，**与连接参数/间隔无关**），产品侧必须做「复位 + 重试」。

**应用路径（zkgui 里跑 demo 本体）补充验证（2026-09-14 下午）**
- 需求方提醒：`zkgui` 被 kill 后 init 会**自动拉起**—— 实测确认，且可用 `fun launch` 的同一机制手工部署：推 `/tmp/EasyUI.cfg`（`startupLibPath=/tmp/zkapp_lib.so`、`resPath=/tmp/zkapp_ui/`）+ 把应用 `libzkgui.so`、`ui/*.ftu` 推到 `/tmp` → `setprop ctl.restart zkswe` → 新 zkgui 进程确实加载 `/tmp` 的 lib（`/proc/<pid>/maps` 可见），无需 kill。
- Z20 应用侧（服务端 demo）跑通：logcat `initEasyUICfg ok` → `[ble] hci up OK` → `Started listening on ATT channel` → `adv enable ok`（屏幕上是 demo 的「网络设置」界面）。
- Z21 应用侧（客户端 demo）跑通，**应用 ↔ 应用主从对传成功**：客户端 `scan data addr=DC:84:03:A1:2D:84 name=zkswe ble` → `Connect done` → GATT 发现 `0xfff1/0xfff2` → `evt=4 INTERACT_READY`；服务端同步收到 `Connect from <Z21 的 BD>` + ATT 报文（Read By Grp/Type + **Write Req handle 0x0004 订阅**）。**两边屏幕都显示“已连接”**（客户端：`已连接：zkswe ble`；服务端：`已连接 38:54:39:DA:1…`）。
- ✅ **文字显示/字库（校正口径 2026-09-14）**：**系统字库在 `/etc/font/`**（Z21 是 `/etc/font/fzcircle.ttf`）；**`/res` 是用户 `update.img` 的升级区，产品做好后是全覆盖的，不能当「系统资源」参考**。本次「全屏无文字只剩色块」的真实原因是 `/tmp/EasyUI.cfg` 的 `font` 指向了设备上不存在的路径，**改指 `/etc/font/fzcircle.ttf` 即恢复 → 不需要往机器里推字库**。
- ⚠️ **`/tmp/EasyUI.cfg` 千万不能带 BOM**（PowerShell `Set-Content -Encoding UTF8` 会加 BOM）→ 解析失败时引擎会**静默回退**`/res/etc/EasyUI.cfg`（现象：跑的还是原应用、但字库正常），完全看不到报警。
- ⚠️ **LE 连接不稳**：`connect()` 会得到 `Function not implemented (errno=38)` / `Transport endpoint is not connected (errno=107)`，`Failed to connect` 后重试常能成功 → **根因和处置见下方「稳定性深度分析」**。
- 工具侧：`fun launch` 在**多于一台 adb 设备**时选不中（报 `more than one device/emulator`，`-s IP`/`-s IP:port` 均无效；`flythings_build_ui_flow` 同样卡此步）→ 跑应用路径部署前先只留一台设备（例：拔掉 USB 那台）。

**稳定性深度分析（2026-09-14，需求方要求：查是否蓝牙连接参数/间隔导致）结论：不是连接参数（scan interval/window、connection interval、supervision timeout）的问题**，而是**控制器/固件在「连接 → 断开」之间会残留链路状态**：残留期间 HCI 层面任何新建连接都被拒（`Connection Already Exists`），只能靠复位控制器恢复。

测量条件（保证干净）：两台整机的应用都 `setprop ctl.stop zkswe` 停掉，Z20 只跑外设广播，Z21 只发连接，无扫描干扰。

| 实验 | 结果 |
|---|---|
| Z21 当中心 `hcitool lecc <Z20 的 BD 地址>` × 10 | **4 成功 / 6 失败**；失败码 `Connection timed out`(ETIMEDOUT) 与 `Input/output error`(EIO) |
| 同上但重试间隔 2s → 10s | 仍 **4/10**→ **排除「重试太快 / 间隔不够」**|
| raw HCI `LE Create Connection`（`hcitool cmd 0x08 0x000d …`）参数扫描 | scan interval/window = 2.5ms / 10ms / 100ms，conn interval = 7.5–15 / 30–50 / 100–200ms，supervision timeout = 320ms / 2s / 4s —— **控制器状态干净时全部一次成功**（参数不敏感） |
| 解码 Command Status | 反复出现 **`0x0B` = Connection Already Exists**；`hcitool con` 里那条 LE 链路**一直在**，`hcitool ledc <handle>` 返回 **EIO 断不掉**（残留 handle 还会变：16/17/18） |
| `hciconfig hci0 reset` 后 | **第一次连接必成功**（handle 16，`ledc 16` 能干净断开、`hcitool con` 变空）；**紧接着的第二次连接就 `Connection timed out`**→ 「一次干净连接之后马上再连」必失败 |
| 外设侧（Z20）同样会卡 | 日志出现 `E/ble: [ble] likely already advertising...`（断开后**重新开广播失败**）+ 一条卡住约 10 min 的链路，最终以 `att: Physical link disconnected: Connection timed out`（**supervision timeout 触发**）收场 |
| 产品路径（内核 L2CAP，demo / bin 客户端） | 表现与上面一致 → **不是工具/调用方式问题**|

**给产品的处置建议**
1. **断开后必须校验**：外设的 adv enable 要检查 HCI 返回状态（demo 现在失败只打一句 `likely already advertising...`，等于**静默丢掉广播**）→ 失败时先 disable 再 enable，或直接复位控制器。
2. **重试前先复位**：`hciconfig hci0 reset`（或 down/up + 重新初始化）后再重试；纯靠「多连几次」不稳。
3. **加应用层保活/断链检测**：链路可能因 supervision timeout 被判掉（对端日志已见）。
4. **向原厂（AIC）报问题**：LE link teardown 后控制器残留链路（LE Create Connection 返 `0x0B`、LE Disconnect 返 EIO），需固件修复；复现步骤 = 本文的测量表。

**与 `ble` 包的分工**：`ble`（Z20 1.1.1 / Z21 2.1.0）= 开箱即用的**外设服务**（`BluetoothService`）；
`gatt` = **底层库**（自己定义 GATT 表 / 写客户端流程，中心 + 外设都能做，demo 里还带私有协议测距机）。
产品要"主从都能"→ 走 `gatt` 这套。

---

### 0.4 统一门面 `zk::ble` 与两个后端（2026-09-14 落地）

> 注：本节提到的组件内部实现与内部头文件自 v0.2.1 起**不再随本仓发布**，
> 已移到内部私有目录（模块只发布 `include/` + `lib/`）；这里保留结构说明，因为**后端矩阵与行为口径照着它对**。

需求方：「蓝牙部分都统一按照我们昨天定义的新 API，参考微信的方式」→ 组件收口成**一个 API 面 + 两个平台后端**：

| | btstack 后端 | gatt 后端 |
|---|---|---|
| 代码 | `src/zk_ble.cpp` | `src/zk_ble_gatt.cpp` |
| 平台 | F133（btstack 1.7.2）、V85X（1.8.0） | Z20 / Z21 / T113 / T113EMMC（gatt 1.0.0） |
| HCI 通路 | 串口（H5 / H4，可配） | AIC USB 模组 + `hciconfig`/`hcitool` |
| 上电 | `state_bt` sysfs + 预初始化 hook（Realtek） | `insmod aic_btusb.ko` 或 `ctl.start=hciattach` + `hciconfig hci0 up` |
| 中心侧 | ✅ | ✅（真机跑通） |
| 外设侧 | ✅（v0.3.0 起：`att_db_util` 运行时建表 + 广告 + `notify`；缓冲忙自动排队） | ✅（真机跑通） |
| 配对落盘 | ✅ TLV（`Config.tlv_path`） | ❌ `getBondedDevices` 返回 `ERR_UNSUPPORTED` |
| 公共层 | 公共层头文件（inline）：日志/工具/AD 解析/扫描过滤/`DeviceCache`/回调/`Waiter` | 同左 |

**后端怎么选**（后端选择头文件）：显式 `-DZKBLE_BACKEND_GATT=1` / `-DZKBLE_BACKEND_BTSTACK=1` 优先；
否则按 include 路径自动（有 `btstack/btstack.h` → btstack；否则有 `gatt/gatt-client.h` → gatt）。
⚠️ 两个 `.cpp` 都用 `#if` 互斥包住，**同一工程只会编进一个后端**（同时声明两个包时会自动选 btstack —— V85X 就是这个情况，要试 gatt 就显式传宏）。

**能力门控（不假装能用）**：`getCapabilities(out)` / `backendName()` 提前告知；平台不支持的能力返回
`ERR_UNSUPPORTED` + 人话 hint（例：F133 上调 `peripheral::start()` → 提示用 V85X 的 `blehid` 包或 Z20/Z21 的 gatt 后端）。

**编译自检**（改动后必跑）：`scripts/compile_check.sh`（F133/btstack）与 `scripts/compile_check_gatt.sh`（Z20/Z21/gatt）
—— 两个后端都是“单文件 `-c`”口径，不依赖完整工程。

### 0.5 gatt 后端实现口径与踩坑（2026-09-14 落地，含真机验证）

#### 0.5.1 实现口径（照这个写，别自己另搞一套）
- **线程模型**：一条后端线程独占 gatt mainloop（`mainloop_init` + `mainloop_run`，epoll）。
业务线程向 `socketpair` 写定长命令（8 字节，一次写原子），后端线程执行；同步接口用 `internal::Waiter` 带超时等结果。
  ★ `Waiter` 是 `Impl` 成员而**不是调用方栈对象**（否则业务线程超时返回后，后端线程会 signal 已失效的栈）；
再用 **gen 代际号**作废旧操作的后到回调（防“旧结果填进新请求”）。
- **连接重试/复位**：`connect()` 先停扫 → 逐次尝试（1..`connect_retry`）：`hci_le_create_conn`
  （`errno==0x0B` = 控制器残留链路，落日志/hint）→ L2CAP ATT connect → `bt_att_new`+`gatt_db_new`+`bt_gatt_client_new`。
重试前若 `reset_before_retry` 则 `hciconfig hci0 reset` + 300ms。`getDiag().connect_attempts` 记次数。
- **广播失败不静默**：`adv enable` 失败 → 先 disable 再 enable → 仍失败则复位控制器后重试 → 再不行就 `ERR_IO` + 人话（含 status 码）。
- **上电短路（真机实测后修正）**：`hci0` 已存在时**直接跳过 `insmod`**。否则在「驱动已由系统/上次启动加载」的机器上，
  `insmod` 会报 `File exists`，原实现把它当致命错 → `openAdapter` 直接 `ERR_POWER_OFF`（Z21 整机实测踩到，已修）。
另：`insmod` 是系统工具（常在 `/sbin`），**不走**本模块的 bin 候选链（那个链是给 `hciconfig`/`hcitool` 这种散装二进制用的）。
- **diag 口径**：`uart=""` / `baud=0`（USB HCI 没有串口概念，如实留空）；`powered` = `/sys/class/bluetooth/hci0` 实测存在；
  `hci_state` 0/1/2（gatt 没有 btstack 的 WORKING 状态机，2=就绪）；`hci_events` = 我们在自己 socket 上看到的 0x01~0x5F 事件数
  （`hci_send_req` 内部那部分看不到）；`transport_sent` 恒 0。

#### 0.5.2 真机验证（组件级，2026-09-14）
验证工程（**只用公开 API，不用 demo 代码**）：Z20 外设 / Z21 中心各一，
两个工程的 `src/` 是组件源码的拷贝（`sync_and_build.sh` 同步）+ `fun build`（`-Werror=format/-Werror=array-bounds/...` 真实标志）。

已跑通：`openAdapter`（hci0 已存在 → 短路）→ 扫描发现 `DC:84:03:A1:2D:84 name=zkswe ble rssi=-47`（Z20 的 BD 地址）
→ LE 连接 `handle=17` → L2CAP ATT → GATT 发现 → `getServices` → `subscribe` → `readValue`（读到 `hello` 5 字节）
→ 干净断开。**这一轮就是“组件 API 到底能不能用”的验收**，也抳出了两个真 bug（见下）。

真机抳出的两个 bug（**已修**，教训入库）：
1. **`hci0` 已存在却先 `insmod` 并当致命错**→ `openAdapter` 误报 `ERR_POWER_OFF`（Z21 实测）。
2. **服务/特征 UUID 取不回来（空串）**：中心侧 `getServices()` 打印 `svc `/`chr ` 后面空，
但 handle/props 均正确 → 连带 `writeValue` 用空 uuid 匹配到只读特征（`att_ecode=0x3 Write Not Permitted`）；
外设侧同一根因表现为 `WARN: 特征 fff1 拿不到 value_handle`（notify 找不到句柄）。
   ⚠️ 这两个都是「编译自检全过、一上机就现形」的类型 —— **BLE 改动必须上机跑**，别拿编译过当验收。

#### 0.5.3 实现踩坑（写 gatt 代码前先看，能省一轮）
1. **BlueZ 头必须自己 `extern "C"` 包**，且顺序固定：`bluetooth.h` **必须第一**（`bdaddr_t/htobs/ba2str`），
   `hci.h`/`uuid.h`/`l2cap.h` 才能在 C++ 里编。
2. **`att-types.h` 没有 include guard**，而 `att.h` 已包含它 → 再显式 include 一次就 `redefinition of 'struct bt_att_pdu_error_rsp'`。
3. **`BT_UUID16/BT_UUID32` 是 `bt_uuid_t` 内部枚举**（**值是 16/32/128，不是 0/1/2**）：C 里能裸写，
   C++ 里是类作用域（`bt_uuid_t::BT_UUID16`）→ 用 `bt_uuid_len()`（2/4/16 字节）判断，既编过又不依赖写法。
4. **从 ATT 发现回来的 uuid 常是 128 位形式**（Bluetooth base UUID）→ 必须折回 16 位短写（`"fff1"`）；
参考实现：`bt_uuid_to_uuid128()` + `bt_uuid_to_string()`（demo 就是这么干的）。
5. **地址类型编号两套**：HCI 广播上报 `0=public/1=random`，而 `sockaddr_l2.l2_bdaddr_type` 用内核枚举
   `BDADDR_LE_PUBLIC=1 / BDADDR_LE_RANDOM=2` → **必须转换**（demo 写死 PUBLIC，随机地址设备连不上）。
6. **广播上报两个细节**：`meta->data[0]` 是 `num_reports` 要先跳过；**RSSI 挂在 AD 数据后面的那一字节**
   （`info->data[info->length]`）。
7. **要自己控制“重复上报”语义必须 `filter_dup=0`**（控制器去重开着的话 `allow_duplicates` 永远为假）。
8. ⚠️ **零长柔性数组（`data[0]`）不能直接下标**：`fun build` 带 `-Werror=array-bounds`，
   `meta->data[0]` / `info->data[len]` 会直接编译失败（独立 `-c` 自检只开 `-Wall`，**看不出来**）→ 一律用指针解引用。
9. ⚠️ **C++11 下带默认成员初值的结构体不是聚合体**：`PeripheralChar{"fff1", x, y}` 报
   `no matching function`（fun 固定 `-std=c++11`）→ 对外头里给这类结构体**显式构造函数**。
10. **公共 API 必须单独一个 TU**（公共 TU）：若把 `onDeviceFound()` 这类写成内部头里的 `inline`，
只 include 公开头的应用 TU 会**链接不到**（应用看不到定义，编译器不发射符号）。
11. **WSL 里调 Windows 交叉编译器是连环坑**（已写成结论，别改）：直接 exec `.exe` → `argv[0]` 变 POSIX 路径 →
驱动推 libexec 前缀失败（`CreateProcess: No such file or directory`/`cc1plus` 找不到）；用 `-B` 硬指后又变成
    `fatal error: stdint.h`。**正解：写最小 `.bat`（全 Windows 路径、CRLF）用 `cmd.exe /c` 代跑**。
12. 用 `gcc` 驱动单独链接 C++ 程序必须显式 `-lstdc++`；`-Wall` 下 libstdc++ 会刷一屏 `-Wpsabi` note（不是我们的告警）。

#### 0.5.4 gatt 后端尚未验证的路径（如实标注在代码里）
- T113/T113EMMC 专用分支（`hcitool cmd 0x03 0x0003`）未编入 z20/z21 编译范围，**未真机**；
- long-write 按 offset 拼接、5.0 extended adv 的降级尝试、多连接（当前单连接模型）；
- 外设 `setDeviceName` 广播中改名、多个中心并发（当前“再来就拆旧接新”）。

---

### 0.5 组件级真机复验（2026-09-14 下午，Z20 × Z21 两台整机）

**方法（关键：不用 demo 代码）**：Z20 外设、Z21 中心两个验证工程
——两个工程的 `src/` 是**组件源码的拷贝**（`sync_and_build.sh` 负责同步），只用 `zk/zk_ble.h` 的公开 API；
`fun build -p z20/z21` → `adb push /tmp/` → 前台跑（**不要 `> log 2>&1` 重定向**：printf 块缓冲，被 kill 会丢日志）。

| 验收项 | 结果（我本人独立跑的那轮日志原话） |
|---|---|
| a) 中心拿到 uuid（不再是空） | `svc fff0` / `chr fff1 props=0x09 handle=0x0003` / `chr fff2 props=0x06 handle=0x0006` ✅ |
| b) 写不再被拒 | `writeValue(fff2) → code=0 msg=`（修前是 `-10 / att_ecode=0x3 Write Not Permitted`） ✅ |
| c) 中心收通知 ≥3 | `[evt] NOTIFY fff0/fff1 len=3` ×4 → `notify_count=4` ✅ |
| d) 外设启动成功（不再 status=12） | `外设句柄校验通过：2 个特征与 gatt_db 声明属性一致` → `peripheral::start → code=0`；`中心 38:54:39:DA:1B:5F CONNECTED`；`WRITE char=fff2 len=4 data=50494e47`（"PING"） ✅ |
| e) 外设 notify ≥3 且载荷不空 | `NOTIFY 'N18/N21/N24/N27' → code=0`，`notify 已发出：char=fff1 len=3` ✅ |
| 额外：连接重试 + 复位 | `LE Create Connection 失败 errno=110` → `第 2/3 次连接前先复位控制器` → `hciconfig hci0 reset` → **第 2 次成功**✅ |
| 额外：断开后恢复广播 | `外设：中心断开（Connection reset by peer）` → `断开后广播已恢复` ✅ |

**这一轮真机拓出来的三个 bug（都值得记住，后面写 gatt 代码还会撞）**
1. **`bt_uuid_to_string()` 成功时返回 0**（不是返回长度；失败才返回 `-EINVAL`）→ 写 `if (bt_uuid_to_string(...) <= 0) return "";` 会**把成功当失败**→ uuid 全空。
而中心侧全量发现（`gatt-client.c`）把 uuid **一律按 128 位**塞进 gatt_db，所以必然踏中该分支。
   （中心侧验证工程不看返回值，所以它当年"没练到"。）
2. **`gatt_db_service_add_characteristic()` 返回的是「特征值属性」，不是「声明属性 (0x2803)」**→ 拿它去 `gatt_db_attribute_get_char_data()`
必然回 false（那函数第一行就比对 0x2803）→ 自建表拿不到 value_handle。取 value_handle 用 `gatt_db_attribute_get_handle()`（值属性自己的 handle）。
3. **控制器已在广播 enable 状态时改广播参数 → `status=12 (Command Disallowed)`**（触发现场：上一次进程在广播中被 `kill -9`）。
处置：设参数/数据前**总是**先发一次 `LE Set Advertise Enable(0)`（其返回忽略，Z20 上恒为 status=5）→ 被拒则 `hciconfig hci0 reset` + 重试一次。
4. 附带：`writeValue()`/`peripheral::notify()` 的**入参载荷**曾被同一字段当出参用（后端线程先 `clear()` 才用）→ 载荷恒空。入参单独字段即可。

**本轮未覆盖（如实标注）**：自定义 128 位（非 base）uuid 折回分支未上机；`peripheral::setDeviceName` 未上机；
断开后二次重连闭环未跑；多中心并发/扫描期间角色切换未回归。

---

### 0.6 静态库矩阵与构建口径（2026-09-14 起：只发头 + 库）

需求方：「验证好了后把你的程序做成静态库+头文件发布给到 open 版本 MCP 里面。不释放源码了」→ 组件发布形态改为：

```
components/ble/
├─ include/zk/zk_ble.h        ← 唯一对外头（公开 API 契约）
├─ lib/<平台>/libzkble.a      ← 按平台构建的静态库
└─ lib/BUILD_INFO.md          ← 构建凭据（工具链/依赖版本/符号数/大小/sha256）
```

| 平台 | 后端 | 编译器 | libc | 工程侧需声明的包 | 库大小 | 公开 API |
|---|---|---|---|---|---|---|
| f133 | btstack | `riscv64-unknown-linux-musl-g++`（Xuantie 900 V2.10.2） | musl | `btstack 1.7.2` + `easyui 2.9.0` | 408 KB | 30/30 |
| v85x | btstack | `arm-unknown-linux-musleabihf-g++` | musl | `btstack` + `easyui 2.9.0` | 118 KB | 30/30 |
| z20 | gatt | `arm-pc-linux-gnueabihf-g++` 8.3.0 | glibc | `gatt 1.0.0` | 179 KB | 30/30 |
| z21 | gatt | 同上 | glibc | `gatt 1.0.0` | 179 KB | 30/30 |
| t113 / t113emmc | gatt | （待构建） | musl | `gatt 1.0.0` | — | — |

**口径与坑（都是实测）**
- **不拿别的平台的头凑库**：t113/t113emmc 本地没有 `gatt 1.0.0` 包（工具链自带注册表也无），
而 `gatt/hci.h`、`gatt/gatt-db.h` 里有大量**结构体定义**（ABI 相关），跨平台头若不一致会埋雷——
所以宁可不发布那两个平台的库，也不猜。内部装好对应平台包后重跑私有构建脚本即得。
- **z20 与 z21 的 `libzkble.a` 逐字节相同**（sha256 一致）：两个平台的 `gatt 1.0.0` **17 个头文件 md5 逐一相同**（已核对），
同一编译器/同一头文件 → 产物相同。两份都放是为了让工程按平台取，不依赖"知道它们一样"这种隐含知识。
- **V85X 的库是用本地 `btstack 1.7.2` 头构建的**（本机注册表没有 1.8.0）；包站上 V85X 是 1.8.0。
头文件 ABI 未变（本模块只用到 HCI/GAP/GATT 基础声明），但**要严谨就用 1.8.0 重跑一次构建脚本**（装包后一条命令）。
- **符号自检不用 `nm`**：Windows 版 binutils 的 `nm` 缺 `liblto_plugin-0.dll`，一调就报错；
改用 `scripts/verify_lib_symbols.py`（**纯 Python 解析 ar + ELF 符号表**，无外部依赖，任何机器可跑，也方便外部 AI 自己核）。
- 构建脚本（私有）：`private/components-ble/scripts/build_libs.ps1`（一次出四平台库 + 刷新 `lib/BUILD_INFO.md`），
源文件侧编译自检 `compile_check.sh` / `compile_check_gatt.sh` 也一并存放在私有目录。

---

## 1. F133（RISC-V）—— 建链路最简单

- **串口**：`/dev/ttyS1`（本仓实测）。`Config.uart` 留空时模块按存在性探测，顺序 `ttyS1 → ttyS2`。
- **传输**：H5；`Config.prefer_h5 = true`（默认）。
- **上电**：**没有**`state_bt` 这类开关 → 探测不到节点也不报错（模块只在"需要预初始化的模组"上做上电时序）。
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
| 传输 | H5 + **偶校验 8E1**+ 无流控 | `Config.prefer_h5=true`（默认） |
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
| 经典蓝牙（SPP / A2DP / AVRCP / HFP / 经典 HID 主机 / SDP） | ❌ **全无**| `rfcomm/sdp_/avdtp/a2dp/hfp/bnep/goep/avrcp` 在 `.a` 里 0 符号 |
| 经典 L2CAP 通道 | ❌ | 无 `l2cap_register_service` / `l2cap_create_channel` |
| LE Secure Connections | ❌ F133(1.7.2) 未编；⚠️ V85X(1.8.0) config 里宏是开的但**库里仍查无 lesc/ECC 符号**（同 1.7.2 的“宏残留”现象）→ 以真机实测为准 | 配置注释/声明 + `.a` 符号扫描 |

## 4. 要支持新平台要改什么（**已按后端分层**）

**先看后端**（后端选择头文件）：串口 HCI 类平台（F133/V85X）→ btstack 后端；
USB HCI 类平台（Z20/Z21/T113/T113EMMC）→ gatt 后端（`src/zk_ble_gatt.cpp`）。**两个后端共用接口面与公共层，接口不改。**

### 4.1 btstack 后端加平台（串口 HCI）
只需动**平台适配层**（`src/zk_ble.cpp` 的 `kPowerNodes` / 公共层 `internal::defaultUart()` / chip 判定），不改接口面：
1. 加串口候选（公共层头文件的 `defaultUart()`：`ttyS1`→`ttyS2`，新平台追加）；
2. 加上电节点候选（`kPowerNodes`，多个候选 + 存在性判断，别写死）；
3. 确认芯片判定属性（`persist.wifi.module` 在该平台是否可用）与是否需要预初始化；
4. 实测值补进本文件（含"未验证"标注）。

### 4.2 gatt 后端加平台（AIC USB 模组）
1. `Manifest.xml` 声明 `gatt 1.0.0`（版本锁死）；
2. 把 `hciconfig` / `hcitool` 放进升级包的 `/res/bin`（开发期靠工具路径候选链先跑）；
3. 若是 T113/T113EMMC，确认 `hcitool cmd 0x03 0x0003` 已执行（拉起 LE/BR-EDR）；
4. 实测值补进本文件（含"未验证"标注）。

**Z20/Z21 已落地（2026-09-14）**：① 走 `gatt 1.0.0`（中心+外设双角色，见 §0.3）；② BT 是 **AIC USB 模组**
（`/lib/modules/<ver>/aic_btusb.ko` 或 `hciattach` 服务 + `hciconfig hci0 up`）；③ `state_bt`/`state_wifi` 在 gatt 路线下
**不需要处理**（那是 V85X 的 RF 上电门）—— 实测两台整机在 gatt 路线下不碰这两个节点即可拉起 hci0。

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
→ 这块板走的正是 **V85X + RTL8733BS**路径（H5 + 偶校验 + `state_bt` 上电 + rtk 预初始化）。

### 5.1 真机跑测证据（2026-09-13，BLE 扫描验证工程）

构建：`fun install` → `fun build` → **Linking CXX executable <验证工程>**✅
（bin 工程要点：`fun.json` 优先于 `Manifest.xml`，依赖写 fun.json；type=executable 才出 ELF；
rtk 移植件要 `utils/Log.h` → 本工程用 `src/utils/Log.h` 本地垫片顶掉 easyui 依赖，避免拖进 freetype/nanovg/png 一串）

运行：`adb push … /tmp/ && ./<验证工程>`
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

事实链路：上电 → rtk_init（SYNC/CONFIG/下固件/切 1500000）→ btstack HCI **WORKING(2)**→ 扫描 → **17 个设备**（含电子价签 `tag-dc8403a119fc`）：
```
[test][end] chip=8733bs uart=/dev/ttyS2 powered=1 preinit=1 ready=1 hci_state=2 events=554 sent=19 devices=17
[test] DEV DC:84:03:A1:2D:84  tag-dc8403a119fc  rssi=-74 conn=1     ← 扫到自家价签
```

**跑通的关键（三个都是真机试出来的）**

1. ★ **必须先停掉抢串口的 app**：`/bin/zkgui`（系统应用）开机后就持着 `/dev/ttyS2` **两个 fd**，
此时 rtk_init 的 H5 同步永远超时。查法：`ls -l /proc/<pid>/fd | grep ttyS2`。
   **停法（框架口径）**：应用由类 init 服务托管（`/etc/init.rc`: `service zkswe /bin/zkgui`），
   **不要 kill**（kill 只会被 init 立刻拉起）——用 `setprop ctl.stop zkswe` 停服、测完 `setprop ctl.start zkswe` 恢复。
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
 cd <验证工程> && fun.exe build
 adb push .fun/v85x/<验证工程> /tmp/ && adb shell chmod 777 /tmp/<验证工程>
 adb shell 'setprop ctl.stop zkswe; echo 0 > <state_bt>; sleep 3; echo 1 > <state_bt>; sleep 2; cd /tmp && ./<验证工程>'
 # 测完恢复：adb shell 'setprop ctl.start zkswe'
```

**未完成（下一步）**：把我们的应用做**固化升级包**（`fun pack` → update.img → adb 固化），
让设备上的 app 就是我们自己的，彻底消除抢串口冲突，而不是每次靠 `setprop ctl.stop zkswe` 临时停服。

### 5.3 ✅ 固化升级跑通（2026-09-13 11:2x，改成 app 工程）

**做法**：按 FlyThings 流程建 **app 工程**（不是 bin！）——`flythings_create_project(platform=V85X, resolution=480x800)`
→ 挂 `components/ble` 模块 + rtk 预初始化件 → UI（html→json→ftu）→ `fun build` → `flythings_pack_upgrade`
→ ADB 固化（`setprop sys.zkupgrade.*` + `ctl.restart zkswe`）。

**为什么必须做成 app**（指正）：**init 托管 zkgui，kill 掉只会被立刻重生**，抢窗口只能验证、不能交付；
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
