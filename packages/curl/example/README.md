# example · curl（libcurl）最小示例（easy 直调 · **未上机**）

480×480 页面 + 3 个按钮 + 1 个「自检 AUTO」：每键 = 一次 `curl_easy_*` 请求，正文/状态码进 textview + logcat。

> ⚠️ **验证状态（务必先读）**：本仓的 HTTP/HTTPS/下载/WS 真机验证**都走 `curl-cxx` 门面**
> （libcurl 是它的底层，请求确实由 libcurl 执行），但**直接调 `curl_easy_*` 这条路径本仓没有单独上机**
> （`../package.yaml` 里 `verified: null` / `status: unverified`）。本示例按包头签名书写 → **"可直接抄、未取证"**。
> 要标 ✅：在 Z20 上跑一遍并留 logcat（tag = `curl demo`），再更新 `../platforms.md`。

| 文件 | 用途 |
|---|---|
| `ui/main.json` | 页面：GET / HTTPS GET / POST / 自检 AUTO + 结果 textview。`cd ui && fui pack ./` |
| `src/logic/mainLogic.cc` | 回调实现：`onWrite`（必须返回 `size*nmemb`）、`easyRequest()`（setopt/perform/getinfo/cleanup 一条龙） |
| `mainActivity_button_tab.snippet.cpp` | **必须补**：activity 的 `sButtonCallbackTab` 注册（4 行） |
| `Manifest.xml` | 依赖：easyui / log / base-utility / **curl + mbedtls + cares + z**（少一个就满屏 undefined），改完 `fsc install` |

## 关键口径（照抄这几条）

```cpp
curl_global_init(CURL_GLOBAL_DEFAULT);                       // 多线程：起线程之前调
CURL *c = curl_easy_init();
curl_easy_setopt(c, CURLOPT_URL, url);
curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, onWrite);          // 返回 size*nmemb，否则 curl 判错
curl_easy_setopt(c, CURLOPT_WRITEDATA, &body);
curl_easy_setopt(c, CURLOPT_FOLLOWLOCATION, 1L);              // long 类选项一律 1L/10L（别传 int）
curl_easy_setopt(c, CURLOPT_CAINFO, "/tmp/ui/cacert.pem");    // 本包无内置 CA → HTTPS 必须给
CURLcode rc = curl_easy_perform(c);
curl_easy_getinfo(c, CURLINFO_RESPONSE_CODE, &code);          // 老名 CURLINFO_HTTP_CODE
```

- ⚠️ **无内置 CA**（feature report：bundle/path/embed/fallback 全 `no`）→ 不设 `CURLOPT_CAINFO` HTTPS 必失败；
  `cacert.pem` 放**资源目录（resPath）**随包发。
- ⚠️ **链接四件套**：`curl + mbedtls 3.6.5 + cares 1.17.2 + z 1.2.11`（只声明 curl 会满屏 undefined reference）。
- ⚠️ **IPv6 关**（本变体）：只有 AAAA 记录的域名/纯 IPv6 网络会失败 → 别当网络故障查。
- ⚠️ **只有静态库**（Shared=no/Static=yes），HTTP2/HTTP3 也关着。
- ⚠️ **多线程别共享同一个 easy handle** → 跨线程用 `curl_easy_duphandle` 各起一份。
- ℹ️ 业务层建议直接用 `curl-cxx`（`http::Axios` / `http::Downloader` / `http::WebSocket`）。

## 三步跑起来

1. `ui/main.json` → 工程 `ui/`，`cd ui && fui pack ./`（出 `main.ftu`）
2. `src/logic/mainLogic.cc` 并进工程 logic；把 `mainActivity_button_tab.snippet.cpp` 的 4 行填进 `src/activity/mainActivity.cpp` 的 `sButtonCallbackTab[]`
3. 改掉代码里的 IP 占位 → `fsc install && fsc build -p z20` → 部署见 `../platforms.md`

## 验证点

| 按钮 | 期望 |
|---|---|
| GET | `rc=OK HTTP=200`，body = `hello from zkswe lan test server`（33 B） |
| HTTPS GET | `rc=OK HTTP=200`（需先校时 + `CURLOPT_CAINFO` 指向资源目录的 cacert.pem） |
| POST | `rc=OK HTTP=200`，回显 `ECHO:{...}`（51 B） |
| AUTO | 三个请求各跑一遍，结尾 `错误数=0` |

> 上表是**按 libcurl 语义写的期望值**；**真机实测值待补**（本示例未上机，见文件头说明）。
> 同一底层经 `curl-cxx` 的已实测结果：HTTP GET 200/33 B、POST 200/51 B、HTTPS 200/29506 B、Downloader 2/2。
