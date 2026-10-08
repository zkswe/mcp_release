# example · cares（c-ares）最小示例（可直接拷）

480×480 页面 + 2 个按钮 + 1 个「自检 AUTO」：每键 = 一次 c-ares 调用，结果进 textview + logcat。

| 文件 | 用途 |
|---|---|
| `ui/main.json` | 页面：解析 www.baidu.com / DNS 5 域名测速 / 自检 AUTO + 结果 textview。`cd ui && fui pack ./` |
| `src/logic/mainLogic.cc` | 回调实现：`onDnsDone`（ares 回调，只记结果）+ `resolveOne()`（**ares_fds → select → ares_process_fd 事件循环**）+ `jobResolve()` / `jobDnsBench()` |
| `mainActivity_button_tab.snippet.cpp` | **必须补**：activity 的 `sButtonCallbackTab` 注册（3 行） |
| `Manifest.xml` | 依赖：easyui / log / base-utility / cares（本包无 Manifest，不会自动带进来），改完 `fsc install` |

**来源**：`demos/net-direct-tls-z20`（第 1 个按钮 = 单域名直调解析，第 4 个 = 5 域名批量测速）——真机验证 ✅（Z20）。

## 关键口径（照抄这四条）

```cpp
ares_library_init(ARES_LIB_INIT_ALL);          // POSIX 上近似 no-op：返回非 0 不判失败
ares_init(&ch);                                // 空 options → 读设备 /etc/resolv.conf
ares_gethostbyname(ch, name, AF_INET, onDnsDone, NULL);
while (!done) { nfds = ares_fds(ch,&rd,&wr); select(nfds,&rd,&wr,NULL,&tv); ares_process_fd(ch,rf,wf); }
```

- ⚠️ **ares 不自己开线程**：必须自己 `ares_fds` / `ares_timeout` / `ares_process_fd` 驱动（示例超时 5 s）。
- ⚠️ **回调是异步的**（在 ares 事件循环里）→ 只记结果/打日志，改 UI 走自己的线程安全通道。
- ⚠️ **`struct hostent` 归 ares 所有** → 要延后使用就 `ares_free_hostent()` / `ares_free_string()`，别 `free()`。
- ⚠️ **1.17.2 是 2020 年的版本**（头文件 copyright 2004–2020）→ 别照最新官方文档写新 API。
- ℹ️ Z20 上它还是 **libcurl 的 DNS 后端**（`curl 8.12.1-mbedtls` 的 resolver = c-ares）→ 声明 curl/curl-cxx 时它会被依赖链带进来，业务一般不用直调。

## 三步跑起来

1. `ui/main.json` → 工程 `ui/`，`cd ui && fui pack ./`（出 `main.ftu`）
2. `src/logic/mainLogic.cc` 并进工程 logic；把 `mainActivity_button_tab.snippet.cpp` 的 3 行填进 `src/activity/mainActivity.cpp` 的 `sButtonCallbackTab[]`
3. `fsc install && fsc build -p z20` → 部署见 `../platforms.md`（`/tmp` 劫持 + 单次 `setprop ctl.restart zkswe`）

## 验证点（真机实测口径，见 `../evidence/netdir_20260929.txt`）

| 按钮 | 期望（Z20 实测值） |
|---|---|
| 解析 www.baidu.com | `status=0`，`183.2.172.177`，耗时 **40 ms**，`timeouts=0` |
| DNS 5 域名测速 | **5/5 成功**：baidu 35 ms / qq 30 ms / taobao 30 ms / github 34 ms / zkswe 88 ms |
| AUTO | 单域名 + 批量各跑一遍，结尾 `错误数=0` |

> 要跑批量测速的域名自己改 `kBenchList[]`；无外网/无 DNS 时会走 5 s 超时分支（示例会如实打印 `[超时]`）。
