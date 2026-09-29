# ntp · 平台实测表

> 口径：**只写实测过的**；没测的写「未验证」+ 需要什么条件，不猜、不套别的平台结论。
> 结论来源：`package.yaml` 的 `verified_20260929` / `verified_20260929_z21` 块 + `evidence/netstack_auto_20260929.txt`、`evidence/z21_20260929.txt`。

| 平台 | 版本 | 结论 | 实测内容 | 证据 |
|---|---|---|---|---|
| **Z20**（SSD20X 480×480 · 86 面板） | ntp 2.1.1 | ✅ 可用（阻塞版 `syncTime` 成功） | `setenv("TZ","UTC-8",1)` + `tzset()` + `ntp::syncTime(ntp::defaultServerList(), 3000)` → 返回 true；校时前 `2026-09-29 10:55:00` → 校时后 `10:55:04`（TZ=UTC-8 北京时区），用时 4 s | `evidence/netstack_auto_20260929.txt` |
| **Z21**（SSD21X `Zkswe_SSD21X_SPINOR` · easyui 2.2.0 · 1024×600） | ntp 2.1.1 | ✅ 可用（且这是 Z21 的**必需前置**） | 同一条调用 → 成功；**校时前设备 RTC=1970-01-01**，校时后 `2026-09-29 12:16:12`（TZ=UTC-8）。Z21 上 HTTPS 必须先 NTP 校时，否则报 `certificate validity starts in the future` | `evidence/z21_20260929.txt` |
| F133 | 2.1.2 | ✅ 可用 | `syncTime` → 成功（1970 → 2026-09-29）；是 HTTPS 的前置 | `evidence/f133_20260929.txt` |
| T113EMMC | — | 未验证 | 同上 | — |
| V85X | — | 未验证 | 同上 | — |

## 实测口径与板级事实

- 用的服务器列表：`ntp::defaultServerList()`（15 个内置 IP，阿里云优先）；实测日志里实际用的前三个是
  `203.107.6.88 / 182.92.12.11 / 120.25.115.20`（无外网时逐个试会白等 → 现场建议传自己的列表）。
- **必须先设时区**：`setenv("TZ","UTC-8",1)` + `tzset()`，否则本地时间显示不对（库只写 UTC 秒进系统时钟/RTC）。
- 超时窗口 3000 ms 够用；`syncTime()` 是**阻塞版**（逐个服务器试），异步版是 `startSyncTime(servers, callback)`。
- **Z21 上电 RTC = 1970**（实测）→ 依赖证书校验的 HTTPS/TLS 会报 `The certificate validity starts in the future`；
  **顺序必须是 NTP → HTTPS**（Z20 那台时钟本来就对，所以没暴露这个顺序问题）。
- 精度坑（见 `package.yaml` gotchas）：库内四时间戳公式退化成 `T3 + RTT/2`，**毫秒级稳态/组网对时不要用它**；
  `startSyncTime` 有全局单任务保护 + 失败后 5 s 退避无限重试，失败时新同步永远轮不上。
- 0.1.0 与 2.1.1 的**回调类型不同**（0.1.0 是 `struct tm` 秒级，2.1.1 是 `timeval` 微秒）→ 老工程 Manifest 要升版本。

## 复现方式

```bash
# 工程：demos/net-stack-verify-z20（NTP 按钮 + AUTO 自检第 4 步）；Z21 版 demos/net-stack-verify-z21
#      最小示例见 packages/ntp/example/
cd demos/net-stack-verify-z20 && fun install && fun build -p z20
# 部署（/tmp 劫持调试，不动 /res）——⚠️ 单次 restart；先确认没有残留 zkgui 进程
adb -s 192.168.x.x:5555 push .fun/z20/libzkgui.so /tmp/lib/libzkgui.so
adb -s 192.168.x.x:5555 push ui/main.ftu          /tmp/ui/main.ftu
adb -s 192.168.x.x:5555 push EasyUI.cfg           /tmp/EasyUI.cfg   # startupLibPath=/tmp/lib/libzkgui.so, resPath=/tmp/ui/
adb -s 192.168.x.x:5555 shell setprop ctl.restart zkswe
# 取证：日志 tag = netstack demo（Z20）/ netstack demo（Z21 版同名工程）
adb -s 192.168.x.x:5555 shell "logcat -d | grep -F '[NTP]'"
```

⚠️ 部署纪律（踩过）：**确认 `pidof zkgui` 只剩一个、上一次实例已退出**再 `ctl.restart`；连续快速重启会把 MI 全局 init 锁占死 → 黑屏 + 进程 D 状态、`kill -9` 无效，只能断电重启。

## 未验证项与所需条件

- **F133 / F136 / T113EMMC / V85X**：需要真机 + registry 里的 ntp 包；本仓未跑过。
- **异步接口 `startSyncTime()`**：示例里已给调用姿势，但**真机日志记录的是阻塞版同步**（异步版的回调时序未单独取证）。
- **误差量化**：`package.yaml` 记录的是"现场实测单次误差几十~几百 ms、两台设备互差 30~180 ms"（历史工程侧结论），
  本轮真机只记录了"同步成功 + 时间正确"，**未复测误差数值**。
