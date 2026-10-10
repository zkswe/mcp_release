# cares（c-ares 1.17.2）· 平台实测表

> 口径：**只写实测过的**；没测的写「未验证」+ 需要什么条件，不猜、不套别的平台结论。
> 结论来源：`package.yaml` 的 `verified_20260929` 块 + `evidence/netdir_20260929.txt`（直调真机日志原文）。

| 平台 | 版本 | 结论 | 实测内容 | 证据 |
|---|---|---|---|---|
| **Z20**（SSD20X 480×480 · 86 面板） | cares 1.17.2 | ✅ 可用（**直调** ares_* 跑通） | `ares_library_init(ARES_LIB_INIT_ALL)` → 0；`ares_init` + `ares_gethostbyname(www.baidu.com, AF_INET)` + `ares_fds`/`select`/`ares_process_fd` 事件循环 → `183.2.172.177`，**40 ms**，`status=0`；5 域名批量：baidu 35 ms / qq 30 ms / taobao 30 ms / github 34 ms / zkswe 88 ms，**5/5 成功** | `evidence/netdir_20260929.txt` |
| **Z21** | — | 未验证（有间接痕迹，无直调取证） | Z21 那轮只在 `curl-cxx` 上层跑（curl 的 resolver = c-ares，HTTPS/DNS 实际走它），**日志里没有 `[CARES]` 直调行** → 不按"已验证"记 | `evidence/z21_20260929.txt` |
| F133 / F136 | — | 未验证 | 需真机 + registry 里的 cares（且要有能消费它的 curl 变体） | — |
| T113EMMC | — | 未验证 | 同上 | — |
| V85X | — | 未验证 | 同上 | — |

## Z20 板级事实（本轮实测）

- 设备：`192.168.x.x`（`Zkswe_SSD20X_SPINOR`），工程 `projects/pkg_netdir`（c-ares / mbedTLS / OpenSSL 直调三合一）。
- **本包只有 `.a` 静态库（没有 `.so`）**；且 `ares_*` **不自己开线程** → 要自己 `select/poll` 驱动
  `ares_fds` → `ares_timeout` → `ares_process`/`ares_process_fd`；本次实测超时窗口 5 s。
- 依赖设备的 **`/etc/resolv.conf`**（`ares_init()` 传 NULL options 时读它）。
- `ares_library_init` 在 POSIX 上近似 no-op：**返回非 0 不判失败**（实测返回 0）。
- 回调里拿到的 `struct hostent` / 字符串归 ares 所有 → 用完 `ares_free_hostent()` / `ares_free_string()`。
- 回调是异步的（在 ares 事件循环里）→ 业务里改 UI 要走自己的线程安全通道，别在回调里直接动控件。
- 本包在 Z20 的真正原因是 **libcurl 的 DNS 后端**：`curl 8.12.1-mbedtls` 的 resolver = c-ares
  （`libcurl.a` 里能查到 `ares_getaddrinfo/ares_init_options/ares_destroy`）→ 声明 curl/curl-cxx 时它会被依赖链带进来。
- `ares 1.17.2` 是 2020 年的版本（头文件 copyright 2004–2020）→ **别照最新官方文档抄**新 API。

## 复现方式

```bash
# 工程：demos/net-direct-tls-z20（第 1 个按钮 = c-ares 直调 DNS，第 4 个 = 5 域名批量测速）
#       最小示例见 packages/cares/example/
cd demos/net-direct-tls-z20 && fsc install && fsc build -p z20
# 部署（/tmp 劫持调试，不动 /res）——⚠️ 单次 restart；先确认没有残留 zkgui 进程
adb -s 192.168.x.x:5555 push .fun/z20/libzkgui.so /tmp/lib/libzkgui.so
adb -s 192.168.x.x:5555 push ui/main.ftu          /tmp/ui/main.ftu
adb -s 192.168.x.x:5555 push EasyUI.cfg           /tmp/EasyUI.cfg   # startupLibPath=/tmp/lib/libzkgui.so, resPath=/tmp/ui/
adb -s 192.168.x.x:5555 shell setprop ctl.restart zkswe
# 取证：日志 tag = netdir demo，本包的行前缀 [CARES] / [DNS]
adb -s 192.168.x.x:5555 shell "logcat -d | grep -E '\[CARES\]|\[DNS\]'"
```

⚠️ 部署纪律（踩过）：**确认 `pidof zkgui` 只剩一个、上一次实例已退出**再 `ctl.restart`；连续快速重启会把 MI 全局 init 锁占死 → 黑屏 + 进程 D 状态、`kill -9` 无效，只能断电重启。

## 未验证项与所需条件

- **Z21**：想从"间接"升到"直调已验"，需在 Z21 真机上跑一遍 `demos/net-direct-tls-z20` 的第 1/4 个按钮
  （Z21 registry 有 cares 1.17.2，见 `packages/curl-cxx/package.yaml` 的 Z21 说明），**本仓尚未做**。
- **F133 / F136 / T113EMMC / V85X**：需要真机 + 对应平台包；本仓未跑。
- **`ares_getaddrinfo`（新版推荐接口）/ IPv6（AAAA）**：未测（实测只用了 `ares_gethostbyname` + `AF_INET`）。
- **DNS 失败路径**（超时/无人应答/bad 域名）：只覆盖了成功路径，失败码未取证。
