# zknet · 平台实测表

> 口径：**只写实测过的**；没测的写「未验证」+ 需要什么条件，不猜、不套别的平台结论。

| 平台 | 版本 | 结论 | 实测内容 | 证据 |
|---|---|---|---|---|
| **Z20**（SSD20X 480×480 · 86 面板 · RTL8188 WiFi） | zknet 0.0.0 | ✅ 可用（WiFi 全流程 + 只读面） | 读状态 / `startScan`(13 AP, 200ms) / `disconnect` / `connect`(4.2s) / `enableWifi(false)`→`(true)` 自恢复(5.2s) / `NetUtils` iface / `SoftApManager` 只读 / `getConnChannel` | `evidence/zknet_auto_20260929.txt`、`evidence/zknet_readonly_20260929.txt`、`evidence/zknet_panel_20260929.png` |
| Z21 | — | 未验证 | 需 Z21 真机（WifiTest-New 里有 Z21 依赖组合：zknet 0.0.0） | — |
| F133 | 1.1.0 | ✅ 可用（读路径） | SoftAp `setEnable(true)` 15s 未起来（平台结论）；Ethernet `isSupported=0`、`getStaticConfigureInfo` 可读、`setAutoMode` OK | `evidence/f133_20260929.txt` |
| T113EMMC | — | 未验证 | 需真机（WifiTest-New：T113EMMC 用 zknet 1.1.0） | — |
| V85X | — | 未验证 | 需真机（WifiTest-New：V85X 用 zknet 0.0.0） | — |

## Z20 / 86 面板 板级事实（本轮实测）

- 设备：`192.168.x.x`（`Zkswe_SSD20X_SPINOR`），**adb 走 WiFi**（`192.168.x.x:5555`）→ 关 WiFi 会断 adb，测试要能自恢复。
- iface = **`wlan0`**（zknet 自己打印 `the wifi.interface is primary_iface = wlan0`）。
- 已配 AP：`zkswe-soft` / `www.zkswe.com`（`/data/misc/wifi/wpa_supplicant.conf`）；MAC `28:f5:2b:45:f5:a5`。
- **`getConnectionInfo()` 的 RSSI/Freq 返回 0**（本板未填充）→ 信号强度用扫描结果的 `getRssi()`。
- `SoftApManager` 默认 **关**（`isEnable=0`，ssid=`zkswe` / pwd=`12345678` / ip=`192.168.x.x`）；**STA 连通时开 AP 未验证**（RTL8188 并发 AP+STA 行为待现场确认）。
- `EthernetManager::isSupported()=1`（本板有以太网管理面，实际未插线 → `isConnected=0`）；`LTE4GManager::isSupported()=0`。
- 热点/以太网/4G 的**动作类 API**（`setEnable`/`configure`/`setPower`）本轮未验证。

## 复现方式

```bash
# 工程：projects/pkg_zknet（Z20 480x480，九键 + 自检 AUTO）
cd projects/pkg_zknet && fsc install && fsc build -p z20
# 部署（/tmp 劫持调试，不动 /res）——⚠️ 单次 restart，先确认没有残留 zkgui 进程
adb -s 192.168.x.x:5555 push .fun/z20/libzkgui.so /tmp/lib/libzkgui.so
adb -s 192.168.x.x:5555 push ui/main.ftu          /tmp/ui/main.ftu
adb -s 192.168.x.x:5555 push EasyUI.cfg           /tmp/EasyUI.cfg   # startupLibPath=/tmp/lib/libzkgui.so, resPath=/tmp/ui/
adb -s 192.168.x.x:5555 shell setprop ctl.restart zkswe
# 一键跑全流程（不需要人工点）：touch 注入点「自检 AUTO」按钮（480x480 坐标 240,259）
adb -s 192.168.x.x:5555 shell "/tmp/touch tap 240 259"
adb -s 192.168.x.x:5555 shell "logcat -d | grep 'zknet demo'"
```

⚠️ 部署纪律（踩过）：**确认 `pidof zkgui` 只有一个、且上一次的实例已经退出**再 `ctl.restart`；连续快速重启会把 MI 全局 init 锁占死 → 黑屏 + 进程 D 状态、`kill -9` 无效，只能断电重启。
