# openssl（OpenSSL 1.1.1w / Z20 变体名 `1.1.1-w`）· 平台实测表

> 口径：**只写实测过的**；没测的写「未验证」+ 需要什么条件，不猜、不套别的平台结论。
> 结论来源：`package.yaml` 的 `verified_20260929` 块 + `evidence/netdir_20260929.txt`（直调真机日志原文）。

| 平台 | 版本 | 结论 | 实测内容 | 证据 |
|---|---|---|---|---|
| **Z20**（SSD20X 480×480 · 86 面板） | 1.1.1-w（= OpenSSL 1.1.1w，2023-09-11） | ✅ 可用（**直调**握手 + 证书校验通过） | `TLS_client_method` + `SSL_CTX_load_verify_locations(/tmp/ui/cacert.pem)` + `VERIFY_PEER` + `getaddrinfo/socket/connect` + `SSL_new/set_fd/SSL_connect` + `SSL_write`(HTTP GET) → **握手 OK 83 ms，TLSv1.2 / ECDHE-RSA-AES128-GCM-SHA256，`SSL_get_verify_result` = OK(0)**；对端证书 subject = `/C=CN/.../CN=baidu.com`；收 511 B，首行 `HTTP/1.0 200 OK`，总 219 ms | `evidence/netdir_20260929.txt` |
| Z21 | — | 未验证 | Z21 上的版本号是 **`1.1.1-g`**（不是 `-w`，见 `packages/curl-cxx/package.yaml` 的 Z21 说明）；本仓**未在 Z21 上直调 openssl 取证**（Z21 证据里只有 curl/ntp/zknet 的上层日志） | `evidence/z21_20260929.txt`（无 openssl 直调行） |
| F133 / F136 | — | 未验证 | 需真机 + 该平台 registry 里的 openssl（版本名按平台，别照抄 Z20 的 `1.1.1-w`） | — |
| T113EMMC | — | 未验证 | 同上 | — |
| V85X | — | 未验证 | 同上 | — |

## Z20 板级事实（本轮实测 / 头文件核对）

- **版本号是平台专属**：Z20 = `1.1.1-w`（其它平台是 `1.1.1-g`）——Manifest 里写错就在 `fun install` 阶段解析不到。
- 头文件实测 `OPENSSL_VERSION_TEXT = "OpenSSL 1.1.1w  11 Sep 2023"`，`OPENSSL_VERSION_NUMBER = 0x1010117fL`。
- **只发静态库**（`libssl.a` + `libcrypto.a`，无 `.so`）→ 必须静态链；**链接顺序 `libssl` 在前、`libcrypto` 在后**，顺序错 undefined reference。
- **证书校验默认开（`VERIFY_PEER`）但 CA 必须自己给**：实测 CA = `/tmp/ui/cacert.pem`（211167 B，= 资源目录 resPath）；
  不给 CA 就是连接失败（拒绝自签/链不全），**不是「库坏了」**。
- 本包在 Z20 上的主要用户是 **`paho-mqtt3as`**（该库二进制里引用 `SSL_CTX_new / SSL_connect` 为证）→ 即 **MQTT over TLS**；
  用 `mqtt-cxx + paho-mqtt3as` 时 **Manifest 必须显式写 openssl**，否则链接期找不到符号。
- 1.1.1 已是 **EOL 版本**（官方支持到 2023-09）：新协议特性（TLS1.3 新扩展、ECH 等）别指望；要新 TLS 特性看 `mbedtls 3.6.5` 那条路线。
- 1.1.1 与 3.x 的 API 不同（3.x 用 `OSSL_PARAM` / `OSSL_LIB_CTX`、部分函数改名）→ **别照 3.x 文档写**。
- 与 mbedtls 的关系：**同一个工程里两条 TLS 路线并存**是正常的（curl→mbedtls，paho→openssl），别混着理解。

## 复现方式

```bash
# 工程：demos/net-direct-tls-z20（第 3 个按钮 = OpenSSL(libssl) 直调握手 + HTTP GET）
#       最小示例见 packages/openssl/example/
cd demos/net-direct-tls-z20 && fun install && fun build -p z20
# 部署（/tmp 劫持调试，不动 /res）——⚠️ 单次 restart；先确认没有残留 zkgui 进程
adb -s 192.168.x.x:5555 push .fun/z20/libzkgui.so /tmp/lib/libzkgui.so
adb -s 192.168.x.x:5555 push ui/main.ftu          /tmp/ui/main.ftu
adb -s 192.168.x.x:5555 push EasyUI.cfg           /tmp/EasyUI.cfg   # startupLibPath=/tmp/lib/libzkgui.so, resPath=/tmp/ui/
adb -s 192.168.x.x:5555 push resources/cacert.pem /tmp/ui/cacert.pem # 必须：CA 只认资源目录
adb -s 192.168.x.x:5555 shell setprop ctl.restart zkswe
# 取证：日志 tag = netdir demo，本包的行前缀 [OPENSSL]
adb -s 192.168.x.x:5555 shell "logcat -d | grep '\[OPENSSL\]'"
```

⚠️ 部署纪律（踩过）：**确认 `pidof zkgui` 只剩一个、上一次实例已退出**再 `ctl.restart`；连续快速重启会把 MI 全局 init 锁占死 → 黑屏 + 进程 D 状态、`kill -9` 无效，只能断电重启。

## 未验证项与所需条件

- **Z21（`1.1.1-g`）**：需要在 Z21 真机上直调一轮（或经 MQTT over TLS 跑通）才能标 ✅；**本仓未做**。
  ⚠️ Z21 想跑 MQTT 也没有 `paho-mqtt3as`/`mqtt-cxx` 包 → 直调示例更现实。
- **F133 / F136 / T113EMMC / V85X**：未跑；版本名与库形态需按平台核对。
- **TLS 1.3**：1.1.1 支持 1.3，但实测协商到 **TLSv1.2**；1.3 会话未取证。
- **`EVP_*` 加解密 / 摘要 / 自签证书**：未测（示例只用 TLS 客户端 + 证书校验）。
- **`SSL_shutdown` 双向关闭、会话复用**：未测。
