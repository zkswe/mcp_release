# example · ntp 最小示例（可直接拷）

480×480 页面 + 3 个按钮 + 1 个「自检 AUTO」：每键 = 一次 ntp 调用，结果进 textview + logcat。
**AUTO 键** = 读时间 → 阻塞校时 → 再读时间（一句话验证"校时前/后"）。

| 文件 | 用途 |
|---|---|
| `ui/main.json` | 页面：NTP 同步（阻塞）/ NTP 同步（异步回调）/ 读系统时间 / 自检 AUTO + 结果 textview。`cd ui && fui pack ./` |
| `src/logic/mainLogic.cc` | 回调实现：`setupTimezone()` / `serverList()` / `jobSyncBlocking()` / `jobSyncAsync()`（含 `onSyncEnd` 回调）/ `jobShowTime()` |
| `mainActivity_button_tab.snippet.cpp` | **必须补**：activity 的 `sButtonCallbackTab` 注册（4 行） |
| `Manifest.xml` | 依赖：easyui / log / base-utility / ntp 2.1.1，改完 `fun install` |

**来源**：`demos/net-stack-verify-z20`（AUTO 第 4 步 = NTP 校时，真机验证 ✅）+ `demos/net-stack-verify-z21`（Z21 上它是 HTTPS 的前置）。

## 关键口径（照抄这三条）

```cpp
setenv("TZ", "UTC-8", 1);   tzset();                       // ① 先设时区，否则本地时间不对
bool ok = ntp::syncTime(servers, 3000);                    // ② 阻塞版（每台超时 3s）→ 放 worker 线程
ntp::startSyncTime(servers, onSyncEnd);                    // ③ 异步版：回调里只打日志，别动 UI 控件
```

- ⚠️ **内置服务器列表混了境外地址**（NIST/Apple/Windows 等）→ 无外网时逐个试会白等很久；示例只留了阿里 3 台。
- ⚠️ **`getTime()` 有硬编码时间下限**（必须 ≥ `1748510332` = 2025-05-29），比它早一律抛 `invalid time` → 别当网络故障查。
- ⚠️ **`startSyncTime` 有全局单任务保护**：失败时线程内部 5 s 退避无限重试、永不返回 → 周期刷新调用方会以为"任务还在跑"。
- ⚠️ **精度不够**：本库公式退化成 `T3 + RTT/2`（单次误差几十~几百 ms）→ 毫秒级稳态/组网对时请自己发 SNTP。
- ⚠️ Z21 那类上电 **RTC=1970** 的板子：**HTTPS/TLS 之前必须先跑这一步**（否则 `certificate validity starts in the future`）。

## 三步跑起来

1. `ui/main.json` → 工程 `ui/`，`cd ui && fui pack ./`（出 `main.ftu`）
2. `src/logic/mainLogic.cc` 并进工程 logic；把 `mainActivity_button_tab.snippet.cpp` 的 4 行填进 `src/activity/mainActivity.cpp` 的 `sButtonCallbackTab[]`
3. `fun install && fun build -p z20` → 部署见 `../platforms.md`（`/tmp` 劫持 + 单次 `setprop ctl.restart zkswe`）

## 验证点（真机实测口径，见 `../evidence/`）

| 按钮 | 期望（Z20 实测值） |
|---|---|
| NTP 同步（阻塞） | `syncTime -> 成功`；Z20 校时后 `2026-09-29 10:55:04`（TZ=UTC-8，用时约 4 s） |
| NTP 同步（异步） | `startSyncTime -> 0（线程已起）` + 回调 `[cb] ... （已写入系统时钟/RTC）` |
| 读系统时间 | 大于 2025-05-29 的合理时间（Z21 上电初始会是 1970-01-01） |
| AUTO | 打印校时前/后时间，结尾 `错误数=0` |
