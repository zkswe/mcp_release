# openssl —— OpenSSL 1.1.1w（Z20 变体 `1.1.1-w`，只有静态库）

Z20 上这条 TLS 路线**主要给 MQTT 用**：`libpaho-mqtt3as.a` 二进制里引用 `SSL_CTX_new`/`SSL_connect`
→ 上 `mqtt-cxx` + `paho-mqtt3as` 时 Manifest 必须显式带 `openssl`。包内只有 `lib/libssl.a` +
`lib/libcrypto.a`（**无 .so**）；版本宏实测 `OPENSSL_VERSION_TEXT = "OpenSSL 1.1.1w  11 Sep 2023"`。

**怎么用**
1. Manifest：`<package id="openssl" version="1.1.1-w"/>`（**Z20 就是 `-w`，别的平台是 `1.1.1-g`**）
   → `fun install` → `fun build -p z20`（链接顺序 `libssl.a` 在前、`libcrypto.a` 在后）。
2. 关键 API：`OPENSSL_init_ssl` → `SSL_CTX_new(TLS_client_method())` → `SSL_CTX_set_verify(SSL_VERIFY_PEER)`
   + `SSL_CTX_load_verify_locations(CA)` → `SSL_new` → `SSL_set_fd` → `SSL_connect` → `SSL_read`/`SSL_write`
   → `SSL_shutdown` → `SSL_free`/`SSL_CTX_free`；算法层用 `EVP_*`/`SHA256*`，排错看 `ERR_print_errors_fp`。
3. EOL 风险 / 与 mbedtls 双栈 / 完整符号表 → `package.yaml`。

⚠️ 未实测（`verified: null`）：实读头文件 + 二进制符号反查写成。
