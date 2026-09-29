# curl —— libcurl 8.12.1（Z20 变体 `8.12.1-mbedtls`，只有静态库）

Z20 专属构建：**SSL=mbedTLS、resolver=c-ares、zlib 开、IPv6 关、无内置 CA、只有 `.a`**（无 `.so`）。
业务层一般用 `curl-cxx`（`http::Axios`/`Downloader`/`WebSocket`）；只有自己拼请求、要精细控制
（超时/重定向/自定义头/流式写）时才直接调 `curl_easy_*`。

**怎么用**
1. Manifest（**四件套缺一不可**，版本名要带 `-mbedtls`）：
   `<package id="curl" version="8.12.1-mbedtls"/>` + `mbedtls ^3.6.5` + `cares ^1.17.2` + `z ^1.2.11`（或直接引 `curl-cxx ^10.0.3` 让它带）→ `fun install` → `fun build -p z20`。
2. 关键 API：`curl_easy_init()` → `curl_easy_setopt(curl, CURLOPT_URL, url)` /
   `CURLOPT_WRITEFUNCTION`+`WRITEDATA` / `CURLOPT_FOLLOWLOCATION, 1L` / `CURLOPT_TIMEOUT, 10L` /
   **`CURLOPT_CAINFO, ".../resources/cacert.pem"`** → `curl_easy_perform` → `curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &code)` → `curl_easy_cleanup`。
3. 无内置 CA 会崩、IPv6 关、静态库链接串、变参 setopt 要写 `1L` 等 8 条坑 → `package.yaml`。

⚠️ 未实测（`verified: null`）：实读包内 configure feature report + 头文件 + 二进制符号反查写成。
