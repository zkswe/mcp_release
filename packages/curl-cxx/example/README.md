# example · curl-cxx 最小示例（可直接拷）

480×480 页面 + 5 个按钮 + 1 个「自检 AUTO」：每键 = 一次 `http::*` 调用，结果进 textview + logcat。
**AUTO 键自己把整条链路跑一遍**（GET → POST → HTTPS → 下载 → WS），不用人工点。

| 文件 | 用途 |
|---|---|
| `ui/main.json` | 页面：HTTP GET / POST / HTTPS / Downloader / WebSocket + 自检 AUTO + 结果 textview。`cd ui && fui pack ./` |
| `src/logic/mainLogic.cc` | 回调实现：worker 线程 + 线程安全日志缓冲 + 各任务（`jobHttpGet` / `jobHttpPost` / `jobHttpsGet` / `jobDownload` / `jobWebSocket`） |
| `mainActivity_button_tab.snippet.cpp` | **必须补**：activity 的 `sButtonCallbackTab` 注册（6 行） |
| `Manifest.xml` | 依赖：easyui / log / base-utility / curl-cxx / curl / mbedtls / cares / z，改完 `fun install` |

**来源**：`demos/net-stack-verify-z20`（GET/POST/HTTPS）+ `demos/net-stack-advanced-z20`（Downloader 双任务 + 进度回调、WebSocket 回显）——两轮都是真机验证过的。

## 关键口径（照抄这几条就不容易踩）

```cpp
http::Axios ios;                                  // 阻塞 API → 必须放 worker 线程
http::AxiosResponse r = ios.GET(url, cfg);        // 非 2xx 会抛 base::Exception → 一定 try/catch
http::Downloader::instance().add(task);           // 任务队列：progress/result 回调都在库线程
http::WebSocket ws; ws.connect(url, cfg);          // 依赖 curl 的 ws 支持（本包 Protocols 含 ws/wss）
```

- ⚠️ **`cacert.pem` 只认资源目录（resPath）**：放别处报 `not correctly signed by the trusted CA`（那是「CA 没找到」，不是证书坏）。
- ⚠️ **HTTPS 前先校时**（上电 RTC=1970 的板子必踩：`certificate validity starts in the future`）。
- ⚠️ **别在 `onUI_init` 里调网络 API**：会在页面前卡住；示例里 UI 线程只用 200ms 定时器刷日志。
- ⚠️ 下载落盘目录用 `/data/`（示例里写 `/data/demo_*`）：Z21 那类板子**没有 `/mnt/sdnand`**。

## 三步跑起来

1. `ui/main.json` → 工程 `ui/`，`cd ui && fui pack ./`（出 `main.ftu`）
2. `src/logic/mainLogic.cc` 并进工程 logic；把 `mainActivity_button_tab.snippet.cpp` 的 6 行填进 `src/activity/mainActivity.cpp` 的 `sButtonCallbackTab[]`
3. 改掉代码里的 IP 占位（`192.168.x.x` → 你的测试机）→ `fun install && fun build -p z20` → 部署见 `../platforms.md`（`/tmp` 劫持 + 单次 `setprop ctl.restart zkswe`）

## 验证点（真机实测口径，见 `../evidence/`）

| 按钮 | 期望（Z20 实测值） |
|---|---|
| HTTP GET | `200 OK`，33 B，body = `hello from zkswe lan test server` |
| HTTP POST | `200 OK`，51 B，回显 `ECHO:{...}` |
| HTTPS GET | `200 OK`，29506 B（证书校验通过；需先校时 + CA 在 resPath） |
| Downloader | 双任务 **2/2 成功**（307200 B + 81 B），进度回调逐段上报、队列清空 |
| WebSocket | `sendFrame 17 B → receiveFrame 22 B`（回显），`close()` 正常 |
| AUTO | 结尾打印 `错误数=0` |
