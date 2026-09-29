# mbedtls —— Mbed TLS 3.6.5（Z20 给 curl 用的 TLS 后端）

Z20 的 **HTTP/HTTPS 走这条 TLS 路线**：`curl 8.12.1-mbedtls` 编的就是 mbedTLS（`libcurl.a` 里有
`mbedtls_ssl_setup` 等符号）→ 用 `curl`/`curl-cxx` 就自动吃到它。**只有自己写 TLS 长连接**（WebSocket、
自研协议、私有 MQTT over TLS）才直接调 `mbedtls_*`。包内 133 个头、5 个 `.a`（无 .so）。

**怎么用**
1. Manifest：`<package id="mbedtls" version="^3.6.5"/>`（一般由 curl-cxx 传递引入）→ `fun install`
   → `fun build -p z20`；**静态库链接顺序** mbedtls → mbedx509 → mbedcrypto（+p256m/everest）。
2. 关键 API：`mbedtls_net_connect` → `mbedtls_ctr_drbg_seed`(+entropy) → `mbedtls_ssl_config_defaults`
   → `mbedtls_ssl_conf_rng/conf_authmode/conf_ca_chain` → `mbedtls_ssl_setup` → `mbedtls_ssl_set_bio`
   → `mbedtls_ssl_handshake` → `read`/`write`。
3. **CA 要自带**：项目 `resources/cacert.pem` 随包发（缺 CA 崩→看门狗反复重启）；编译期开关实测值、双 TLS 栈（mbedtls vs openssl）等 6 条坑 → `package.yaml`。

⚠️ 未实测（`verified: null`）：实读头文件 + `mbedtls_config.h` 逐条 `#define` 核对 + 符号反查写成。
