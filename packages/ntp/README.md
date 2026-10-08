# ntp —— NTP 客户端（Z20 时间同步，静态 `libntp.a`）

往 NTP 服务器（UDP 123）要时间，写进**系统时钟 + RTC**；只做客户端。默认服务器是 15 个内置 IP
（阿里云 `203.107.6.88` 打头，里面混了 NIST/Apple 等境外地址）。2.1.1 的回调是 `timeval`（微秒），
老版本 0.1.0 是 `struct tm`（秒级）。

⚠️ **精度实测差**：上游源码（`gitcom/AppGroup/lib-ntp/src/ntp/ntp.cpp`）里 `T1` 恒为 0、`T4` 只取发送后的差值，四时间戳公式退化 → 每台设备系统性偏、重校不收敛（现场两台互差 30~180ms）。要毫秒级/组网对时就自己发 SNTP（参照 `projects/SmartPanel_HA/src/system/ClockManager.cpp`）。

**怎么用**
1. Manifest：`<package id="ntp" version="2.1.1"/>`（依赖 `base-utility`）→ `fsc install` → `fsc build -p z20`。
2. 关键 API：`setenv("TZ","UTC-8",1); tzset();` → `ntp::startSyncTime(ntp::defaultServerList(), cb)`
   （异步，回调 `void (*)(const std::string&, const timeval*)`）或阻塞的 `ntp::syncTime(servers, 3000)`。
3. 单任务保护、硬编码 2025-05-29 时间下限、失败无限重试等 7 条坑 + 源码仓位置 → `package.yaml`。

⚠️ 未实测（`verified: null`）：实读头文件 + 上游源码 + Z20 现场记录写成。
