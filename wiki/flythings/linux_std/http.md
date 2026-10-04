---
title: HTTP
---

如果需要HTTP客户端，推荐使用依赖包 [curl-cxx](https://package.flythings.cn/packages/Z21/curl-cxx)

如果需要HTTP服务端，推荐使用依赖包 [civetweb-cxx](https://package.flythings.cn/packages/Z21/civetweb-cxx)

HTTP服务端样例代码查看：[HTTP服务器样例代码](https://gitee.com/oszksw/http_server_demo)

## ⚠️ HTTPS 必须打包 resources/cacert.pem（关键坑）

Z21 上 curl-cxx 走 **mbedtls**，请求 `https://` 时如果项目里没有 CA 证书，**不是优雅报错，而是进程崩溃 → 看门狗拉起 → 反复重启**（表面现象：App 一直闪退/起不来，logcat 无有效报错）。

**解决办法**：把 CA 证书文件命名为 `cacert.pem` 放进项目 `resources/` 目录，随 APK 一起打包。证书可从 curl 包内获取，或从任意系统导出（如 `https://curl.se/ca/cacert.pem`）。

```
resources/
  └── cacert.pem   ← HTTPS 必需
```

排查顺序（遇到 HTTPS 崩溃/重启）：
1. `adb shell ls /data/data/<包名>/resources/cacert.pem` 确认证书在设备上
2. `adb shell cat /proc/meminfo` 排除低内存 OOM（Z21 仅 36MB RAM，见平台差异）
3. 确认 Manifest 里 curl/curl-cxx 依赖已声明

> MCP 的 `flythings_validate_project` 会自动检查：Manifest 含 curl/curl-cxx 且代码有 HTTPS 调用时，检查 `resources/cacert.pem` 是否存在。
