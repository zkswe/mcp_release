# curl（libcurl 8.12.1 / Z20 变体名 `8.12.1-mbedtls`）· 平台实测表

> 口径：**只写实测过的**；没测的写「未验证」+ 需要什么条件，不猜、不套别的平台结论。
> ⚠️ 本包 `package.yaml` 里是 **`verified: null` / `status: unverified`**：**本仓没有单独直调 libcurl 的真机记录**。
> 下面 Z20/Z21 的结论都标注为「间接（经上层 `curl-cxx`）」，证据是 `curl-cxx` 那两轮的日志。

| 平台 | 版本 | 结论 | 实测内容 | 证据 |
|---|---|---|---|---|
| **Z20**（SSD20X 480×480 · 86 面板） | curl 8.12.1-mbedtls | 🟡 间接可用（**未直调**；上层 `curl-cxx` 全通） | `curl-cxx 10.0.3` 的 Manifest 声明本包，HTTP GET/POST、HTTPS GET、Downloader、WebSocket **全部实测通过** → 这些请求都由 libcurl 执行，可证本包能链能跑；**但没有 `curl_easy_*` 直调日志** | `evidence/netstack_auto_20260929.txt` |
| **Z21**（SSD21X `Zkswe_SSD21X_SPINOR` · 1024×600） | curl 8.12.1-mbedtls | 🟡 间接可用（**未直调**） | Z21 上 curl-cxx 同一套写法 HTTP/HTTPS（校时后）/Downloader/WebSocket 通过；Z21 的 curl 版本名同为 `8.12.1-mbedtls`（见 `packages/curl-cxx/package.yaml` Z21 说明） | `evidence/z21_20260929.txt` |
| F133 / F136 | — | 未验证 | 需真机；且**版本名按平台**（Z20/Z21 是 `8.12.1-mbedtls`，其它平台可能是 `8.12.1` = openssl 变体）→ 先核对包站版本名 | — |
| T113EMMC | — | 未验证 | 同上 | — |
| V85X | — | 未验证 | 同上 | — |

## Z20 变体事实（读包内 README = configure feature report + 符号反查）

- **SSL = mbedTLS**（不是 openssl，也不是 OpenSSL 变体）；**resolver = c-ares**；**zlib 开**；
  **IPv6 = no**；**HTTP2/HTTP3 都关**（HTTP1 internal）；**Build libcurl: Shared=no, Static=yes**（只有 `.a`）。
- **无内置 CA**：feature report 明确 `ca cert bundle: no / ca cert path: no / ca cert embed: no / ca fallback: no`
  → **不设 `CURLOPT_CAINFO` 就连不上 HTTPS**。把 `cacert.pem` 放项目 `resources/` 随包发（实测资源目录口径见 `packages/curl-cxx/platforms.md`）。
  历史踩坑：缺 CA 时 Z21 上**不是优雅报错，而是进程崩 → 看门狗反复重启**。
- **链接是一串**：`libcurl.a` 里有 `mbedtls_*` / `ares_*` / `inflate` 符号 →
  必须同时带 **mbedtls 3.6.5 + cares 1.17.2 + z 1.2.11**（= `curl-cxx 10.0.3` 的 Manifest Z20 段那四件套）。只声明 curl 会满屏 undefined。
- **版本名写错就解析不到**：Z20 必须写 `8.12.1-mbedtls`（写 `8.12.1` 不行）。
- **IPv6 关**：只有 AAAA 记录的域名/纯 IPv6 网络会失败，**别当网络故障查**。
- **`curl_easy_setopt` 是变参**：long 类选项传 `int` 会踩 64 位对齐（`CURLOPT_TIMEOUT` 等）→ 一律显式写 `1L/10L`。
- **多线程别共享同一个 easy handle**（curl 不明文保证线程安全）→ 跨线程用 `curl_easy_duphandle` 各起一份（头文件注释就是这么建议的）。
- 业务层一般用 `curl-cxx`（`http::Axios` / `http::Downloader` / `http::WebSocket`）；直调 `curl_easy_*` 只有要精细控制时才用。

## 复现方式

```bash
# 上层路线（本仓已验证的形态）：demos/net-stack-verify-z20（HTTP/HTTPS）+ demos/net-stack-advanced-z20（下载/WS）
# 直调路线的最小示例：packages/curl/example/（⚠️ 未上机，见下节）
cd demos/net-stack-verify-z20 && fun install && fun build -p z20
# 部署（/tmp 劫持调试，不动 /res）——⚠️ 单次 restart；先确认没有残留 zkgui 进程
adb -s 192.168.x.x:5555 push .fun/z20/libzkgui.so /tmp/lib/libzkgui.so
adb -s 192.168.x.x:5555 push ui/main.ftu          /tmp/ui/main.ftu
adb -s 192.168.x.x:5555 push EasyUI.cfg           /tmp/EasyUI.cfg   # startupLibPath=/tmp/lib/libzkgui.so, resPath=/tmp/ui/
adb -s 192.168.x.x:5555 push resources/cacert.pem /tmp/ui/cacert.pem # 跑 HTTPS 必须
adb -s 192.168.x.x:5555 shell setprop ctl.restart zkswe
adb -s 192.168.x.x:5555 shell "logcat -d | grep 'netstack demo'"
```

⚠️ 部署纪律（踩过）：**确认 `pidof zkgui` 只剩一个、上一次实例已退出**再 `ctl.restart`；连续快速重启会把 MI 全局 init 锁占死 → 黑屏 + 进程 D 状态、`kill -9` 无效，只能断电重启。

## 未验证项与所需条件

- **直调 `curl_easy_*` / `curl_multi_*`**：本包**没有任何直调真机记录**（`package.yaml` 保持 `verified: null`）。
  要把它变 ✅，需在 Z20（或 Z21）上跑一轮 `packages/curl/example/` 里的工程并留日志。**本次补文档不改这个状态。**
- **F133 / F136 / T113EMMC / V85X**：未跑；且版本名/变体（mbedtls vs openssl）需按平台核对。
- **HTTP2/HTTP3、IPv6、`curl_multi` 并发**：本变体里 HTTP2/3 与 IPv6 都关着 → 属"不支持"，不是"未测"；`curl_multi` 未测。
- **`CURLOPT_CAINFO` 之外的 TLS 细节**（客户端证书、SNI 覆盖、代理）：未测。
