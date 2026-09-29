# 网络包验证（Z21 / SSD21X / 1024x600）：HTTP(S) + 校时 + 下载 + WS + 热点 + 以太网

> 真机验证状态：true
> 平台依赖与坑位见包文档 `packages/<包>/package.yaml`（本 demo 是它的可运行实现）。

## 1. 三步跑起来

1. **改 IP**：本 demo 里的 `192.168.x.x` 是占位，改成你自己测试机的 LAN IP（HTTP/WS 服务地址、MQTT broker 等）
2. 编译：`fun install && fun build -p z21`
3. 部署（**临时调试用 /tmp 劫持**，别直接覆盖 `/res`；部署纪律见下）：
   ```bash
   adb -s <设备IP>:5555 push .fun/z21/libzkgui.so /tmp/lib/libzkgui.so
   adb -s <设备IP>:5555 push ui/main.ftu          /tmp/ui/main.ftu
   adb -s <设备IP>:5555 push /tmp/EasyUI.cfg      # resPath=/tmp/ui/、startupLibPath=/tmp/lib/libzkgui.so
   adb -s <设备IP>:5555 shell setprop ctl.restart zkswe
   ```
   要跑 HTTPS 的 demo：把 `resources/cacert.pem` 推到 **`/tmp/ui/cacert.pem`**（= 资源目录）。

## 2. 功能与验证点

- HTTP GET/POST → 200 OK；HTTPS → **必须先 NTP 校时**（Z21 上电 RTC=1970，否则报 `certificate validity starts in the future`），校时后 200 OK 29506 B
- `ntp::syncTime` → 成功（1970-01-01 → 2026-09-29，TZ=UTC-8）
- `http::Downloader` 双任务 → 2/2（落 `/data/`，Z21 没有 `/mnt/sdnand`）
- `http::WebSocket` 回显 OK；SoftAp `setEnable(true)` → ENABLED（≈5s）
- Ethernet：`getStaticConfigureInfo` 读到静态配置；`NetUtils(eth0)` 取值；`setAutoMode(true)` OK
- ⚠️ Z21 无 `mqtt-cxx`/`paho-mqtt3as` 包 → 本工程不验 MQTT

## 3. 关键坑位（代码里已处理，别回退）

- **部署别连续快速重启**：旧实例没退干净就起新的 → MI 全局 init 锁被占 → 黑屏 + 进程 D 状态、`kill -9` 无效，只能断电。**先确认 `pidof zkgui` 无残留，再单次 `setprop ctl.restart zkswe`**。
- **取证用 tag 过滤**：`logcat -d -s zkgui`（zknet 事件线程会刷屏，把内部日志挤出缓冲）。
- **`cacert.pem` 只认资源目录(resPath)**：放别处会报 `not correctly signed by the trusted CA`（那是「CA 没找到」，不是证书坏）。
- **别在 `onUI_init` 里调网络 API**：会在页面前卡住；本 demo 全部阻塞调用都在 worker 线程，UI 线程只用定时器刷日志。
- **HTTPS/TLS 前先校时**（Z21 那类上电 RTC=1970 的板子尤其明显）。
