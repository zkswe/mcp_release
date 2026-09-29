---
id: devflow-package-verify-playbook
title: 依赖包/网络 API 真机自动化验证套路（playbook）
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [Z20, Z21]
tags: [devflow]
evidence: []
---
# 依赖包/网络 API 真机自动化验证套路（playbook）

> 检索导引：需求里出现「验证依赖包 / 网络 API 真机验收 / 自动跑一遍 / 自检 / 触摸注入取证 / 部署调试怎么不翻车 / 面板黑屏了」时命中本文。
> 配套实现：`demos/net-stack-verify-z20`、`net-stack-advanced-z20`、`net-wifi-verify-z20`、`net-stack-verify-z21`、`net-direct-tls-z20`、`hw-relay-verify-z20`；包文档见 `knowledge/devflow/dependency-package-docs.md` 与 `packages/<包>/`。

> **补充检索词**：Z21 上电 RTC 1970 / HTTPS certificate validity starts in the future / 必须先校时再 HTTPS / 无 RTC 板开机时间 / 证书校验失败不是证书坏

## 1. 一句话套路

**一个 480×480（或 1024×600）页面 + N 个「一按钮 = 一次 API 调用」+ 一个「自检 AUTO」按钮**，配合
**脚本注入触摸 → tag 过滤抓 logcat → 抓 framebuffer 截图**，就能在没有人工点击的情况下把一整套 API 验完并留证。

## 2. 工程骨架（照抄）

- **UI**：标题 + 按钮网格 + 结果 `textview`（`ui/main.json`，`fui pack ./` 出 ftu）。
  分辨率不同就按 `1024/480`、`600/480` 缩放重排（Z21 版就是这么来的）。
- **回调**：每个按钮一个 `onButtonClick_<Caption>`，**必须注册进 activity 的 `sButtonCallbackTab`**（漏了 = 点了没反应）。
- **阻塞调用全部丢 worker 线程**（`pthread_create` + `pthread_detach`），UI 线程只用 `{0, 200}` 定时器把日志刷到 textview/logcat。
  ⚠️ **绝不在 `onUI_init` 里调网络/硬件 API**（会把页面卡住，实测 Z20 上表现为黑屏 + 卡 `MI_SYS_IOCTL_Init`）。
- **线程安全日志**：`logLine()`（加锁追加到静态缓冲）→ `flushLog()`（UI 线程取增量，按行打 logcat）。
- **AUTO 键**：顺序跑全部步骤，末尾打「错误数=N」——这就是验收结论；顺序要注意依赖（**校时/连网先于需要 TLS/服务器的步骤**）。

## 3. 取证三件套（脚本侧）

```bash
# ① 注入触摸（bin_tools/<平台>/touch）
adb -s <IP>:5555 shell "/tmp/touch tap X Y"          # 按钮中心 = left+width/2, top+height/2
# ② 抓日志（**必须按 tag 过滤**）
adb -s <IP>:5555 shell "logcat -d -s zkgui"          # 事件线程（如 zknet）刷屏会把你方日志挤出缓冲
# ③ 抓屏（/dev/fb0 双/三缓冲：取多张，选颜色数最多的那张才是当前画面）
adb -s <IP>:5555 shell "/tmp/busybox dd if=/dev/fb0 of=/data/fb.raw bs=<stride> count=<virtualH>"
```
Python/PIL 侧把 raw 按 `BGRA` 解成 PNG（stride = 宽×4）。比较两屏用 `flythings_ui_visual(action="diff")`。

## 4. 部署纪律（**踩过大坑**）

- 临时调试走 **/tmp 劫持**：push `libzkgui.so`→`/tmp/lib/`、`main.ftu`→`/tmp/ui/`、`cacert.pem`→`/tmp/ui/`，
  写 `/tmp/EasyUI.cfg`（`resPath=/tmp/ui/`、`startupLibPath=/tmp/lib/libzkgui.so`）→ `setprop ctl.restart zkswe`。
  **不要直接覆盖 `/res`**（那是整机默认程序）。
- ⚠️ **不要连续快速 `setprop ctl.restart zkswe`**：旧实例没退干净就起新的 → MI 全局 init 锁被占 → **黑屏 + 多个进程 D 状态、`kill -9` 无效**，只能**断电重启**。
  → 部署脚本要「先确认 `pidof zkgui` 无残留 → 单次 restart → 等新 pid」。
- 平台差异：**Z20 没有 `/mnt/sdnand`… 反了，Z20 有；Z21 只有 `/mnt/extsd`、`/mnt/usb1`** → 落盘写 `/data/`；触摸设备节点、uart、字体列表按各机 `/res/etc/EasyUI.cfg` 抄。
- 触摸/取证工具用 **`bin_tools/<平台>/`**（每平台一份 touch/zkshot/busybox）。

## 5. 主机侧测试设施（离线可复现）

| 用途 | 做法 |
|---|---|
| HTTP/HTTPS 目标 | 本机起个 LAN 测试服务（`GET /hello.txt`、`POST /echo` 回显、`GET /big?kb=N` 测下载），设备打 `http://<你的IP>:8000/...` |
| WebSocket 回显 | 本机 WS echo 服务（注意端口别撞：`8795/8791/8765` 可能被既有服务占着） |
| MQTT | 本地 broker（EMQX 等）；⚠️ **主机侧见证端要连 `127.0.0.1:1883`**——宿主访问自身 LAN IP 常被拦（表现为 connect timeout） |
| HTTPS 证书 | `cacert.pem` 推 **资源目录**（`/tmp/ui/`）——放别处报 `not correctly signed by the trusted CA`（= CA 没找到） |
| 时间 | **TLS 前先校时**：上电 RTC 停在上古时间的板子（Z21 实测 1970）会报 `certificate validity starts in the future` |

## 6. 每包的验收结论放哪

- 包文档 `packages/<包>/package.yaml` 的 `verified_<日期>` 块（步骤 → 结果 → 判据）+ `evidence/` 里的设备日志；
  **没上真机的一律 `verified: null`**，不冒充实测。
- 平台差异写进 `platforms.md` 的实测表（没测的平台写「未验证 + 需要什么条件」）。

## 7. 常见误判（都真踩过）

1. **「没日志」= 缓冲被刷屏冲掉**，不是程序没跑 → 用 `logcat -d -s zkgui` 复核。
2. **黑屏不要先怀疑 UI/布局**：先看 `pidof zkgui` 有几个、进程状态（D = 卡内核）、`sys.zkapp.dbg` 停在哪一步。
3. **一次失败别急着下结论**：`enableWifi(false)` 之后 adb 断是正常现象；TLS 首次失败可能只是时钟；多跑一次/换个顺序再判。
4. **别用宿主 LAN IP 让宿主连自己的服务**（MQTT/HTTP 见证端都栽过）。
5. **同一台机器别边验边让别人升级 `/res`**：会互相顶掉（108 上遇到过一次整机重启 + 程序被换成拼墙 App）。
