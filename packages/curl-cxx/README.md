# curl-cxx —— 用法示例（真机验证 ✅）

> `curl-cxx` `10.0.3`（Z20）· 真机实测 2026-09-29 · 设备 `192.168.x.x`（86 面板）
> **一句话**：HTTP/HTTPS 客户端（`http::Axios` / `http::Downloader` / `http::FormData`），底层 libcurl 8.12.1-mbedtls。
> 机器可读版：`package.yaml`

## 怎么装（Z20）

```xml
<dependencies enableOnPlatforms="Z20">
    <package id="easyui" version="^2.2.0"/>
    <package id="base-utility" version="^10.8.5"/>
    <package id="curl-cxx" version="10.0.3"/>
    <package id="curl" version="8.12.1-mbedtls"/>
    <package id="mbedtls" version="3.6.5"/>
    <package id="cares" version="1.17.2"/>
    <package id="z" version="1.2.11"/>
</dependencies>
```

`fun install && fun build -p z20`

## 最小用法

```cpp
#include <http/axios.h>
http::Axios ios;
http::AxiosRequestConfig cfg;
cfg.setConnectTimeout(3000); cfg.setTimeout(10000);
http::AxiosResponse r = ios.GET("https://www.baidu.com", cfg);   // 阻塞！
LOGD("status=%d %d bytes", r.status, (int) r.data.size());
```

POST / 自定义头 / multipart / 下载器：见 `package.yaml` 的 `usage_cpp`，真机工程 `projects/pkg_netstack`。

## 真机实测（Z20 / 108，全自动）

| 步骤 | 结果 |
|---|---|
| HTTP GET `http://192.168.x.x:8000/hello.txt` | **200 OK**，33 B，body 正确 |
| HTTP POST `.../echo`（JSON + 自定义头） | **200 OK**，51 B，回显 `ECHO:{...}` |
| HTTPS GET `https://www.baidu.com` | **200 OK**，29506 B（证书校验通过） |

证据：`evidence/netstack_auto_20260929.txt`

## 坑（真机踩到的）

1. **HTTPS 前先校时**（包 README 第 1 条），否则证书校验必失败。
2. **`cacert.pem` 要放在「资源目录（resPath）」下**：实测只有 `<resPath>/cacert.pem` 生效（hijack 调试时 = `/tmp/ui/cacert.pem`；正常部署 = `/res/ui/cacert.pem`，与 ftu 同级）。放 `/tmp/resources/`、`/tmp/` 都无效，报 `mbedTLS: The certificate is not correctly signed by the trusted CA` —— 那是「CA 没找到/用错」，不是服务器证书问题。
3. Z20 的 curl 是 **mbedtls 变体**（无 IPv6、无内置 CA）→ cacert.pem 必须自带；历史上缺 CA 会崩进程→看门狗重启。
4. `http::Axios` **全阻塞** → 放 worker 线程跑；非 2xx 会抛 `base::Exception`，务必 catch。
