# example · zknet 最小示例（可直接拷）

480×480 页面 + 九个按钮 + 一个「自检 AUTO」：每键 = 一次 zknet 调用，结果进 textview + logcat。
**AUTO 键会自己把整条链路跑一遍**（读状态 → 扫描 → 断开 → 连接 → 关 WiFi 10s → 开 WiFi），无需人工点。

| 文件 | 用途 |
|---|---|
| `ui/main.json` | 页面：WiFi 开/关、扫描、连接、断开、读 IP·MAC、NetUtils 查询、热点状态、网络通道、自检 AUTO + 结果 textview。`cd ui && fui pack ./` |
| `src/logic/mainLogic.cc` | 回调实现：`acquireWifi()`（惰性取 + 注册 IWifiListener）、`DemoWifiListener`、定时器状态机（`sWait` 人工步骤 / `sAuto` 自检 6 步）、各按钮回调 |
| `mainActivity_button_tab.snippet.cpp` | **必须补**：activity 的 `sButtonCallbackTab` 注册（10 行） |
| `Manifest.xml` | 依赖：easyui / log / zknet / base-utility，改完 `fun install` |

## 关键口径（照抄这三条就不容易踩）

```cpp
WifiManager *w = NETMANAGER->getWifiManager();   // ⚠️ 只在按钮/线程里惰性取，别放 onUI_init
w->addWifiListener(&sWifi);                      // 回调：enable/connect/errorCode/scanResult/supplicantState
w->startScan();  w->getWifiScanInfosLock(vec);   // 扫描；先扫到目标 SSID 再 connect 更稳
w->connect(ssid, pw);  w->disconnect();          // 连接 / 断开
int cur = GpioHelper…                            // （无关）状态一律以 manager 读回为准
```

⚠️ `enableWifi(false)` 会断 adb（adb 走 WiFi）→ 自检里 10s 后自动 `enableWifi(true)` 救回来。

## 三步跑起来

1. `ui/main.json` → 工程 `ui/`，`cd ui && fui pack ./`
2. `src/logic/mainLogic.cc` 并进工程 logic；`mainActivity_button_tab.snippet.cpp` 的 10 行填进 `sButtonCallbackTab[]`
3. `fun install && fun build -p z20`，部署见 `../platforms.md`

真机实测（Z20 86 面板，2026-09-29 全自动跑完 6 步）见 `../README.md` §4 与 `../evidence/`。
