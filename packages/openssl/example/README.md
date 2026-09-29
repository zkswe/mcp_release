# example · openssl 最小示例（可直接拷）

480×480 页面 + 2 个按钮 + 1 个「自检 AUTO」：每键 = 一次 OpenSSL 直调，结果进 textview + logcat。

| 文件 | 用途 |
|---|---|
| `ui/main.json` | 页面：握手（看 verify 结果）/ 握手 + HTTP GET / 自检 AUTO + 结果 textview。`cd ui && fui pack ./` |
| `src/logic/mainLogic.cc` | 回调实现：`resolveCaPath()`（CA 候选链）、`reportSslError()`（打 ERR 栈）、`jobTls(bool doHttpGet)`（`SSL_CTX_new` → load CA → socket/connect → `SSL_new/set_fd/SSL_connect` → 可选 HTTP GET） |
| `mainActivity_button_tab.snippet.cpp` | **必须补**：activity 的 `sButtonCallbackTab` 注册（3 行） |
| `Manifest.xml` | 依赖：easyui / log / base-utility / **openssl 1.1.1-w**（Z20 专属版本名），改完 `fun install` |

**来源**：`demos/net-direct-tls-z20`（第 3 个按钮 = OpenSSL 直调握手 + HTTP GET）——真机验证 ✅（Z20）。

## 关键口径（照抄这几条）

```cpp
SSL_CTX *ctx = SSL_CTX_new(TLS_client_method());
SSL_CTX_load_verify_locations(ctx, "/tmp/ui/cacert.pem", NULL);   // CA 必须自己给
SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, NULL);                   // 默认就是 PEER，但没 CA = 连接失败
SSL *ssl = SSL_new(ctx);  SSL_set_fd(ssl, fd);
SSL_set_tlsext_host_name(ssl, "www.baidu.com");                   // SNI
if (SSL_connect(ssl) != 1) { /* 先看 ERR 栈：ERR_get_error/ERR_error_string */ }
long vr = SSL_get_verify_result(ssl);                             // X509_V_OK == 0 才算校验通过
```

- ⚠️ **版本名写死按平台**：Z20 = `1.1.1-w`，其它平台 = `1.1.1-g` → Manifest 写错 install 就解析不到。
- ⚠️ **只发 `.a`**：链接顺序 **`libssl` 在前、`libcrypto` 在后**，顺序错 undefined reference。
- ⚠️ **CA 只认你给的那份**：示例按 `resPath` → 外置卡 → 当前目录 三级候选找。
- ⚠️ **1.1.1 已 EOL**（支持到 2023-09）：要 TLS1.3 新特性走 `mbedtls 3.6.5`；**1.1.1 的 API 与 3.x 不同**，别照 3.x 文档写。
- ℹ️ 本包在 Z20 上主要服务 **`paho-mqtt3as`（MQTT over TLS）**：用 `mqtt-cxx + paho-mqtt3as` 时 Manifest 必须显式带 openssl。

## 三步跑起来

1. `ui/main.json` → 工程 `ui/`，`cd ui && fui pack ./`（出 `main.ftu`）
2. `src/logic/mainLogic.cc` 并进工程 logic；把 `mainActivity_button_tab.snippet.cpp` 的 3 行填进 `src/activity/mainActivity.cpp` 的 `sButtonCallbackTab[]`
3. `fun install && fun build -p z20` → 部署见 `../platforms.md`（**记得把 `cacert.pem` 推到 `/tmp/ui/cacert.pem`**）

## 验证点（真机实测口径，见 `../evidence/netdir_20260929.txt`）

| 按钮 | 期望（Z20 实测值） |
|---|---|
| 握手 | `握手 OK 耗时=83ms 版本=TLSv1.2 套件=ECDHE-RSA-AES128-GCM-SHA256 verify=OK(0)` |
| 握手 + HTTP GET | 另加：对端证书 subject `/C=CN/.../CN=baidu.com`，收 511 B，首行 `HTTP/1.0 200 OK`，总计 **219 ms** |
| AUTO | 握手 + GET 各跑一遍，结尾 `错误数=0` |

> URL/端口改成你自己的服务时，注意 **`SSL_set_tlsext_host_name`（SNI）与证书 CN/SAN 要匹配**，否则 `VERIFY_PEER` 会失败。
