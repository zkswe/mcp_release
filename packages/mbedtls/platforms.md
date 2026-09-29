# mbedtls（Mbed TLS 3.6.5）· 平台实测表

> 口径：**只写实测过的**；没测的写「未验证」+ 需要什么条件，不猜、不套别的平台结论。
> 结论来源：`package.yaml` 的 `verified_20260929` / `verified_20260929_z21` 块 + `evidence/netdir_20260929.txt`、`evidence/z21_20260929.txt`。

| 平台 | 版本 | 结论 | 实测内容 | 证据 |
|---|---|---|---|---|
| **Z20**（SSD20X 480×480 · 86 面板） | mbedtls 3.6.5 | ✅ 可用（**直调**握手跑通；也作为 curl 的 TLS 后端在跑） | `mbedtls_net_connect` + `ctr_drbg_seed` + `x509_crt_parse_file(/tmp/ui/cacert.pem)` + `ssl_config_defaults` + `ssl_handshake` + `ssl_write`(HTTP GET) → **握手 OK 103 ms，TLSv1.2 / TLS-ECDHE-RSA-WITH-AES-128-GCM-SHA256**；GET `www.baidu.com` 收 511 B，首行 `HTTP/1.0 200 OK`，总计 352 ms；`psa_crypto_init()` 调过（TLS1.3 路径需要） | `evidence/netdir_20260929.txt` |
| **Z21**（SSD21X `Zkswe_SSD21X_SPINOR` · 1024×600） | mbedtls 3.6.5 | 🟡 间接可用（经 `curl-cxx` 上层；无直调取证） | HTTPS GET → 首次 FAIL（`mbedTLS: The certificate validity starts in the future`，RTC=1970）→ **NTP 校时后复跑 200 OK / 29506 B**（这条链路的 TLS 就是本包） | `evidence/z21_20260929.txt` |
| F133 / F136 | — | 未验证 | 需真机 + registry 里的 mbedtls（且要有消费它的 curl 变体） | — |
| T113EMMC | — | 未验证 | 同上 | — |
| V85X | — | 未验证 | 同上 | — |

## Z20 板级事实（本轮实测 / 头文件核对）

- 设备：`192.168.x.x`（`Zkswe_SSD20X_SPINOR`），工程 `projects/pkg_netdir`（mbedTLS 直调）。
- **只发静态库（5 个 `.a`，无 `.so`）** → **链接顺序有讲究**：`mbedtls → mbedx509 → mbedcrypto`（`p256m`/`everest` 也要带上），顺序错就满屏 undefined。
- 能力开关（读 `include/mbedtls/mbedtls_config.h`）：**`SSL_PROTO_TLS1_3=on`、`PSA_CRYPTO_C=on`、`THREADING_C=off`、`NET_C=on`、`FS_IO=on`**。
  - TLS1.3 编进去了 → 3.x 的 API 与 2.x 教程**不兼容**（`ssl_conf_rng` 的 rng 类型、entropy 回调签名都变了），别照 2.x 例子抄。
  - `THREADING_C=off` → 库自身无锁，多线程共用同一个 `ssl`/`ctr_drbg` 上下文要自己加锁。
- **必须自带 CA**（本包无内置 CA、不读系统信任目录）：实测 `cacert.pem` = 211167 B，**放资源目录（resPath）**才能过校验；
  缺 CA 不是优雅报错 —— Z21 实测过"缺 CA → 进程崩 → 看门狗拉起 → 反复重启"（`references/kb/build.md`）。
- `entropy` 走平台默认（无硬件熵源选项）→ 设备上必须能读 `/dev/urandom`，否则握手阶段就失败。
- 服务端证书信息：实测 `mbedtls_x509_crt_info` 打印的 subject 行为空行（本板现象），**不影响握手与校验结果**。
- 同一个工程里可能**两套 TLS 并存**：curl→本包（mbedtls），paho→openssl（`SmartPanel_HA` 就是这种组合）→ 体积/内存要算。

## 复现方式

```bash
# 工程：demos/net-direct-tls-z20（第 2 个按钮 = mbedTLS 直调握手 + HTTP GET）
#       最小示例见 packages/mbedtls/example/
cd demos/net-direct-tls-z20 && fun install && fun build -p z20
# 部署（/tmp 劫持调试，不动 /res）——⚠️ 单次 restart；先确认没有残留 zkgui 进程
adb -s 192.168.x.x:5555 push .fun/z20/libzkgui.so /tmp/lib/libzkgui.so
adb -s 192.168.x.x:5555 push ui/main.ftu          /tmp/ui/main.ftu
adb -s 192.168.x.x:5555 push EasyUI.cfg           /tmp/EasyUI.cfg   # startupLibPath=/tmp/lib/libzkgui.so, resPath=/tmp/ui/
adb -s 192.168.x.x:5555 push resources/cacert.pem /tmp/ui/cacert.pem # 必须：CA 只认资源目录
adb -s 192.168.x.x:5555 shell setprop ctl.restart zkswe
# 取证：日志 tag = netdir demo，本包的行前缀 [MBEDTLS]
adb -s 192.168.x.x:5555 shell "logcat -d | grep '\[MBEDTLS\]'"
```

⚠️ 部署纪律（踩过）：**确认 `pidof zkgui` 只剩一个、上一次实例已退出**再 `ctl.restart`；连续快速重启会把 MI 全局 init 锁占死 → 黑屏 + 进程 D 状态、`kill -9` 无效，只能断电重启。

## 未验证项与所需条件

- **Z21 直调**：目前只有经 `curl-cxx` 的间接证据；要升 ✅ 需在 Z21 真机上跑 `demos/net-direct-tls-z20` 第 2 个按钮（本仓未做）。
- **TLS 1.3 实际协商**：实测协商结果是 **TLSv1.2**（服务端选择）；TLS1.3 只是"编进去了"，**未取到 1.3 会话的证据**。
- **F133 / F136 / T113EMMC / V85X**：未跑。
- **客户端证书（mTLS）/ CRL / 会话恢复**：未测。
- **内存占用/长连接稳定性**：未做量化（只有单次握手的耗时数据）。
