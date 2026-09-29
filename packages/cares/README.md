# cares —— c-ares 异步 DNS 解析库（1.17.2，只有静态库）

Z20 上**一般不直接用**：它是 `libcurl` 的 DNS 后端（`curl 8.12.1-mbedtls` 编的就是 `resolver=c-ares`，
`libcurl.a` 里能查到 `ares_getaddrinfo`/`ares_init_options`）。只有要自己做**异步/可取消 DNS** 时才碰 `ares_*`。

**怎么用**
1. Manifest：用 curl/curl-cxx（Z20 段会显式带 `cares ^1.17.2`）时自动引入；手工用：
   `<package id="cares" version="1.17.2"/>` → `fun install` → `fun build -p z20`（只有 `.a`，静态链）。
2. 关键 API：`ares_library_init(ARES_LIB_INIT_ALL)` → `ares_init_options(&ch, NULL, 0)` →
   `ares_gethostbyname(ch, "example.com", AF_INET, cb, NULL)` → 自己 `select` 驱动
   `ares_fds`/`ares_timeout`/`ares_process` → `ares_destroy(ch)` → `ares_library_cleanup()`。
3. 内存归还（`ares_free_hostent`/`ares_free_string`）、坑、完整符号表 → `package.yaml`。

⚠️ 未实测（`verified: null`）：实读 `ares*.h` + 二进制符号反查写成。
