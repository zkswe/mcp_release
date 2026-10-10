# curl-cxx · 平台实测表

> 口径：**只写实测过的**；没测的写「未验证」+ 需要什么条件，不猜、不套别的平台结论。
> 本文件所有结论都出自 `package.yaml` 的 `verified_*` 块与 `evidence/*.txt`（真机日志原文）。

| 平台 | 版本 | 结论 | 实测内容 | 证据 |
|---|---|---|---|---|
| **Z20**（SSD20X 480×480 · 86 面板 · RTL8188 WiFi） | curl-cxx 10.0.3 | ✅ 可用（HTTP/HTTPS/Downloader/WebSocket 全通） | HTTP GET `/hello.txt` → 200 OK 33 B；HTTP POST `/echo`（JSON + 自定义头）→ 200 OK 51 B 回显；HTTPS GET `https://www.baidu.com` → 200 OK 29506 B（证书校验通过）；`http::Downloader` 双任务 2/2（307200 B + 81 B，进度回调逐段上报、队列清空）；`http::WebSocket` 回显 `sendFrame 17 B → receiveFrame 22 B` | `evidence/netstack_auto_20260929.txt`、`evidence/netstack2_20260929.txt` |
| **Z21**（SSD21X `Zkswe_SSD21X_SPINOR` · easyui 2.2.0 · 1024×600） | curl-cxx 10.0.3 | ✅ 可用（同 Z20 一套写法，布局按 1024×600 重生成） | HTTP GET/POST 200 OK（33 B / 51 B）；HTTPS **首次 FAIL**（`mbedTLS: The certificate validity starts in the future`，RTC=1970）→ **NTP 校时后复跑 200 OK / 29506 B**；Downloader 双任务 2/2（落盘 `/data/z21_*.bin|json`）；WebSocket 回显 `echo:hello-ws-from-z21` | `evidence/z21_20260929.txt` |
| F133 | 11.0.0 | ✅ 可用 | HTTP GET/POST 200、HTTPS 200（**需先 NTP 校时**）、Downloader 2/2+进度、WebSocket 回显 | `evidence/f133_20260929.txt` |
| T113EMMC | — | 未验证 | 同上 | — |
| V85X | — | 未验证 | 同上 | — |

## Z20 / 86 面板 板级事实（本轮实测）

- 设备：`192.168.x.x`（`Zkswe_SSD20X_SPINOR`），HTTP 打本机 LAN 测试服务，MQTT/WS 打 WSL 里的服务。
- 工程：`projects/pkg_netstack`（HTTP/HTTPS/NTP/MQTT 一键自检）、`projects/pkg_netstack2`（Downloader/WebSocket/MQTTS/LWT 等补验项）。
- **HTTPS 的两条硬前提**：① 先校时（`ntp` 包）② `cacert.pem` 必须落在**资源目录（resPath）**。
  实测 resPath=`/tmp/ui` 时只有 `/tmp/ui/cacert.pem` 能过校验；放 `/tmp/resources/`、`/tmp/` 都报
  `mbedTLS: The certificate is not correctly signed by the trusted CA`（该报错 = CA 没找到/用错，不是服务器证书坏）。
- Z20 的 curl 是 **8.12.1-mbedtls** 变体：feature report 显示 **IPv6=no、无内置 CA bundle/path/embed** → 必须自带 CA。
- 历史踩坑：**缺 CA 不是优雅报错，而是进程崩 → 看门狗反复重启**（`references/kb/build.md`）。
- `http::Axios` 全是**阻塞**调用 → 必须放 worker 线程（本仓示例统一 pthread + 日志缓冲，UI 线程只刷 textview/logcat）。
- 非 2xx 会抛 `base::Exception`（Downloader 也按 README：状态码非 200/206 或长度不符即失败）→ 一定要 `try/catch`。
- 同一个工程里 **HTTP 走 mbedtls、MQTT(paho) 走 openssl** → 会链进两套 TLS，体积/内存要算进去。
- WebSocket 回显要有自己的 WS 服务端：本机 **8765 被 `tools/lite_ui` 的 http.server 占着**，用 **8766**。

## 复现方式

```bash
# 工程：demos/net-stack-verify-z20（HTTP/HTTPS）+ demos/net-stack-advanced-z20（Downloader/WS）
#      最小示例见 packages/curl-cxx/example/
cd demos/net-stack-verify-z20 && fsc install && fsc build -p z20
# 部署（/tmp 劫持调试，不动 /res）——⚠️ 单次 restart；先确认没有残留 zkgui 进程
adb -s 192.168.x.x:5555 push .fun/z20/libzkgui.so /tmp/lib/libzkgui.so
adb -s 192.168.x.x:5555 push ui/main.ftu          /tmp/ui/main.ftu
adb -s 192.168.x.x:5555 push EasyUI.cfg           /tmp/EasyUI.cfg   # startupLibPath=/tmp/lib/libzkgui.so, resPath=/tmp/ui/
adb -s 192.168.x.x:5555 push resources/cacert.pem /tmp/ui/cacert.pem # 跑 HTTPS 必须
adb -s 192.168.x.x:5555 shell setprop ctl.restart zkswe
# 取证：按 tag 过滤（zknet 事件线程会刷屏，把内部日志挤出缓冲）
adb -s 192.168.x.x:5555 shell "logcat -d | grep 'netstack demo'"   # 或 'netstack2 demo'
```

⚠️ 部署纪律（踩过）：**确认 `pidof zkgui` 只剩一个、上一次实例已退出**再 `ctl.restart`；连续快速重启会把 MI 全局 init 锁占死 → 黑屏 + 进程 D 状态、`kill -9` 无效，只能断电重启。

## 未验证项与所需条件

- **F133 / F136 / T113EMMC / V85X**：需要该平台真机 + 该平台 registry 里可用的 `curl` 变体（Z20 是 `8.12.1-mbedtls`，
  别的平台可能是 `8.12.1`（openssl 变体）→ Manifest 版本名会不同）。本仓未在这几个平台跑过，**结论留空**。
- **大文件/弱网**：Downloader 只在 LAN 测过（307200 B）；`LowSpeedLimit`/`retry_max` 的边界未做压力测试。
- **HTTPS 的双向证书 / 自签 CA 场景**：未测（示例只用公网 CA 校验证书链）。
