# zknet —— 用法示例（真机全流程验证 ✅）

> **包信息**：`zknet` `0.0.0`（只发 `include/net/*.h` + `lib/libzknet.so`，**包内没有 README/Manifest**）
> **实测平台**：Z20 / 86 面板（480×480，easyui 2.6.0，RTL8188 WiFi）· 2026-09-29 · 设备 `192.168.x.x`
> **一句话**：网络门面 —— WiFi（开关/扫描/连接/断开/静态IP/MAC）、以太网、SoftAP 热点、4G + `NetUtils` iface 工具。
> **机器可读版**：`package.yaml`（头文件/API/坑/实测逐步结果，AI 优先读它）

## 1. 怎么装

```xml
<dependencies enableOnPlatforms="Z20">
    <package id="easyui" version="^2.2.0"/>
    <package id="log" version="0.0.0"/>
    <package id="zknet" version="0.0.0"/>
    <package id="base-utility" version="^10.8.5"/>   <!-- 实测项目里一起声明，zknet 自身 Manifest 缺这行 -->
</dependencies>
```

```bash
fun install && fun build -p z20
```

## 2. 入口与 API 速查

| 类 / 宏 | 关键方法 | 说明 |
|---|---|---|
| `NetManager` / **`NETMANAGER`** | `getWifiManager()` / `getEthernetManager()` / `getLTE4GManager()` / `getSoftApManager()` / `getConnChannel()` | 总入口（单例） |
| `WifiManager` | `enableWifi(bool)` / `isWifiEnable()` / `getEnableStatus()` | 开关（状态是 `E_WIFI_ENABLE_*`，异步，要等回调/轮询） |
| | `startScan()` / `stopScan()` / `getWifiScanInfosLock(vec)` | 扫描；结果也走 `handleWifiScanResult` |
| | `connect(ssid, pw)` / `connect(ssid, pw, encryption)` / `reconnect()` / `disconnect()` / `isConnected()` | 连接/断开 |
| | `getIp()` / `getMacAddr()` / `getConnectionInfo()` | ⚠️ `getConnectionInfo()` 的 RSSI/Freq 本板返回 0 |
| | `configure(...)` / `getConfigureInfo(...)` / `setAutoMode(bool)` / `isAutoMode()` | 静态 IP |
| | `addWifiListener(IWifiListener*)` | 5 个回调：enable / connect / errorCode / scanResult / supplicantState |
| `WifiInfo` | `getSsid/getBssid/getRssi/getFreq/getEncryption/getLevel` | 扫描结果项 |
| `NetUtils`（静态） | `getIp("wlan0")` / `getMacAddr("wlan0")` / `getConfigureInfo("wlan0", ...)` / `enableIfc` / `dhcpRequestIp` | ifconfig 级工具 |
| `SoftApManager` | `setEnable/isEnable/getSoftApState/setSsidAndPwd/getSsid/getPwd/getIp` | 热点 |
| `EthernetManager` | `isSupported/isConnected/getIp/getMacAddr/configure/setAutoMode` | 以太网 |
| `LTE4GManager` | `setPower/getPowerState/getIMEI/getICCID/getIMSI/queryRSSI` | 4G |

## 3. 最小用法（可直接粘，完整版见 `example/`）

```cpp
#include "net/NetManager.h"      // NETMANAGER
#include "net/WifiManager.h"
#include "net/NetUtils.h"

class MyWifi : public WifiManager::IWifiListener {
    void handleWifiEnable(E_WIFI_ENABLE ev, int args)  { LOGD("enable ev=%d\n", (int) ev); }
    void handleWifiConnect(E_WIFI_CONNECT ev, int args){ LOGD("conn ev=%d\n",   (int) ev); }
    void handleWifiScanResult(std::vector<WifiInfo>* v){ LOGD("scan n=%d\n", (int) v->size()); }
};
static MyWifi sWifi;

static bool onButtonClick_ButtonScan(ZKButton *p) {
    WifiManager *w = NETMANAGER->getWifiManager();   // ⚠️ 别放 onUI_init 里（见坑 1）
    if (w == NULL) return true;
    w->addWifiListener(&sWifi);
    w->startScan();
    std::vector<WifiInfo> infos;
    w->getWifiScanInfosLock(infos);                  // 也可等回调
    LOGD("n=%d ip=%s\n", (int) infos.size(), w->getIp());
    return true;
}
```

**三步跑起来**：`example/ui/main.json` → `ui/` + `fui pack ./` → logic/按键表（`example/mainActivity_button_tab.snippet.cpp`）→ `fun build -p z20` → 部署见 `platforms.md`。

## 4. 真机实测（Z20 86 面板，2026-09-29，全自动「自检 AUTO」跑完 6 步）

| 步骤 | 调用 | 实测结果 |
|---|---|---|
| 1 读状态 | `getWifiManager()` + `isSupported/getEnableStatus/isConnected/getIp/getMacAddr/getConnectionInfo/isAutoMode` | 支持=1 · 开关=开 · 连接=1 · **IP=192.168.x.x** · MAC=28:f5:2b:45:f5:a5 · 当前 AP=zkswe-soft · autoIP=1 |
| 2 扫描 | `startScan()` + `getWifiScanInfosLock()` | **200ms 拿到 13 个 AP**：TPLink_zkswe(-32dBm)、ChinaNet-bsyX(-44dBm)、zkswe-soft(-46dBm)… |
| 3 断开 | `disconnect()` | 200ms 后 `isConnected()=0` |
| 4 连接 | `connect("zkswe-soft","www.zkswe.com")` | **4.2s 连上**，IP 回来 192.168.x.x |
| 5 关 WiFi | `enableWifi(false)` | 5s 后 `getEnableStatus()=关`，adb（走 WiFi）断开 → 测试脚本自个儿重连成功 |
| 6 开 WiFi | `enableWifi(true)` | **5.2s 恢复并回连**，IP 192.168.x.x |

只读面另测（同一天）：
- `NetUtils::getIp/getMacAddr/getConfigureInfo("wlan0")` → `192.168.x.x / 28:f5:2b:45:f5:a5 / mask 255.255.255.0 / gw 192.168.x.x / dns 192.168.x.x`（与 `WifiManager` 读回一致 ✅）
- `SoftApManager` 读回：`isEnable=0 state=0 ssid=zkswe pwd=12345678 ip=192.168.x.x`
- `NetManager::getConnChannel()`=**WiFi(1)**；`Ethernet isSupported=1 isConnected=0 ip=0.0.0.0`；`LTE4G isSupported=0`

证据：`evidence/zknet_auto_20260929.txt`（逐步日志）、`evidence/zknet_readonly_20260929.txt`、`evidence/zknet_panel_20260929.png`（真机屏幕）

## 5. 坑（真机踩到的，务必先看）

1. **别在 `onUI_init` / 构造里调 `NETMANAGER->getWifiManager()`** —— 第一版就这么写的，页面没起来（卡在 `MI_SYS_IOCTL_Init`，`sys.zkapp.dbg=[main:onUI_init]`）。改成按钮/后台线程里**惰性取**后正常。
2. **别连着快速 `setprop ctl.restart zkswe`** —— 旧实例没退干净就起新的 → MI 全局 init 锁被占：黑屏 + 多个 `zkgui` 进程 D 状态、`kill -9` 无效，**只能断电重启**。
3. **`enableWifi(false)` 会断 adb**（adb 走 WiFi）→ 自动化测试必须自带恢复（示例：10s 后自动 `enableWifi(true)`）。
4. **先扫到目标 SSID 再 `connect()`**：模组刚枚举完直接 connect 容易失败（`WifiTest-New` 的做法是多轮扫描→命中后连接）。
5. **`getConnectionInfo()` 的 RSSI/Freq 本板返回 0** → 信号强度看扫描结果 `WifiInfo::getRssi()` 或 `WifiCtrl::signalPoll()`。
6. 回调跑在 zknet 线程里 → 只置标志/打日志，状态以 manager 读回为准。

> 验证工程：`projects/pkg_zknet`（480×480 九键 + 「自检 AUTO」一键跑完上面 6 步，全自动、不需要人点）
