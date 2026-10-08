# example · mbedtls 最小示例（可直接拷）

480×480 页面 + 2 个按钮 + 1 个「自检 AUTO」：每键 = 一次 mbedTLS 直调，结果进 textview + logcat。

| 文件 | 用途 |
|---|---|
| `ui/main.json` | 页面：握手（看版本/套件）/ 握手 + HTTP GET / 自检 AUTO + 结果 textview。`cd ui && fui pack ./` |
| `src/logic/mainLogic.cc` | 回调实现：`resolveCaPath()`（CA 候选链）、`jobTls(bool doHttpGet)`（entropy+drbg → CA → net_connect → config → handshake → 可选 HTTP GET） |
| `mainActivity_button_tab.snippet.cpp` | **必须补**：activity 的 `sButtonCallbackTab` 注册（3 行） |
| `Manifest.xml` | 依赖：easyui / log / base-utility / mbedtls，改完 `fsc install` |

**来源**：`demos/net-direct-tls-z20`（第 2 个按钮 = mbedTLS 直调握手 + HTTP GET）——真机验证 ✅（Z20）。

## 关键口径（照抄这几条）

```cpp
psa_crypto_init();                                             // 3.x 的 TLS1.3 路径需要（幂等，显式调一次）
mbedtls_ctr_drbg_seed(&drbg, mbedtls_entropy_func, &entropy, pers, len);   // rng 是 TLS 必需的
mbedtls_x509_crt_parse_file(&ca, "/tmp/ui/cacert.pem");        // CA 必须自带（放资源目录 resPath）
mbedtls_ssl_conf_authmode(&conf, MBEDTLS_SSL_VERIFY_REQUIRED);
mbedtls_ssl_set_hostname(&ssl, "www.baidu.com");               // SNI + 域名校验，REQUIRED 下必须有
mbedtls_ssl_set_bio(&ssl, &net, mbedtls_net_send, mbedtls_net_recv, NULL);
```

- ⚠️ **CA 只认资源目录（resPath）**：示例按 `resPath(/tmp/ui)` → 外置卡 → 当前目录 三级候选找；
  报 `not correctly signed by the trusted CA` = **CA 没找到/用错**，不是服务器证书坏。
- ⚠️ **缺 CA 不是优雅报错**：历史实测"缺 CA → 进程崩 → 看门狗反复重启"（`references/kb/build.md`）。
- ⚠️ **HTTPS/TLS 前先校时**：RTC=1970 的板子（如 Z21）会报 `certificate validity starts in the future`。
- ⚠️ **3.x ≠ 2.x**：`ssl_conf_rng` 的 rng 类型、entropy 回调签名都变了 → 别照 2.x 教程抄。
- ⚠️ **链接顺序**：`mbedtls → mbedx509 → mbedcrypto`（+ `p256m`/`everest`），顺序错满屏 undefined。
- ⚠️ **`THREADING_C=off`**：库自身无锁 → 多线程共用同一个 `ssl`/`drbg` 要自己加锁。

## 三步跑起来

1. `ui/main.json` → 工程 `ui/`，`cd ui && fui pack ./`（出 `main.ftu`）
2. `src/logic/mainLogic.cc` 并进工程 logic；把 `mainActivity_button_tab.snippet.cpp` 的 3 行填进 `src/activity/mainActivity.cpp` 的 `sButtonCallbackTab[]`
3. `fsc install && fsc build -p z20` → 部署见 `../platforms.md`（**记得把 `cacert.pem` 推到 `/tmp/ui/cacert.pem`**）

## 验证点（真机实测口径，见 `../evidence/netdir_20260929.txt`）

| 按钮 | 期望（Z20 实测值） |
|---|---|
| 握手 | `握手 OK 耗时=103ms 版本=TLSv1.2 套件=TLS-ECDHE-RSA-WITH-AES-128-GCM-SHA256` |
| 握手 + HTTP GET | 另加：收 511 B，首行 `HTTP/1.0 200 OK`，总计 **352 ms** |
| AUTO | 握手 + GET 各跑一遍，结尾 `错误数=0` |

> CA 文件实测大小 211167 B（示例会把实际使用的 CA 路径与大小打进日志，便于排错）。
> ⚠️ 实测协商到的是 **TLSv1.2**（本包 TLS1.3 只是编进去了，未取到 1.3 会话证据）。
