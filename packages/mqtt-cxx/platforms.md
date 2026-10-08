# mqtt-cxx · 平台实测表

> 口径：**只写实测过的**；没测的写「未验证」+ 需要什么条件，不猜、不套别的平台结论。
> 结论来源：`package.yaml` 的 `verified_20260929` / `verified_20260929_part2` / `verified_20260929_will` 块
> + `evidence/netstack_auto_20260929.txt`、`evidence/netstack2_20260929.txt`、`evidence/lwt_will_20260929.txt`。

| 平台 | 版本 | 结论 | 实测内容 | 证据 |
|---|---|---|---|---|
| **Z20**（SSD20X 480×480 · 86 面板） | mqtt-cxx 3.2.0 | ✅ 可用（明文 / MQTTS(TLS) / LWT 遗嘱 / 异常断线自动重连 全部实测） | 明文 `mqtt://…:1883`（EMQX）：`on_connected` 触发、`isConnected()=1`、qos1 订阅→发布→`on_message` 原样回显（len=35）、`unsubscribe` OK；MQTTS：`mqtts://test.mosquitto.org:8883`（`ssl.verify=false`）连通 + qos1 收发回显；LWT：注册遗嘱后 **`kill -9` 异常断线 → 约 2 s broker 代发遗嘱**，payload 与注册值一致（PC 侧见证端）；断线重连：`enableWifi(false)` 90 s → `on_disconnected`，`enableWifi(true)` 后 **`on_connected` 再触发（cause=`automatic reconnect`，≈10.5 s）** | `evidence/netstack_auto_20260929.txt`、`evidence/netstack2_20260929.txt`、`evidence/lwt_will_20260929.txt` |
| Z21 | — | 未验证（**平台无此包**） | Z21 registry **没有 mqtt-cxx / paho-mqtt3as** → Z21 上不验 MQTT。要验需要 Z21 包站提供该包（或换 MQTT 方案） | `evidence/z21_20260929.txt`（该轮 AUTO 明写「不验 MQTT」） |
| F133 / F136 | — | 未验证 | 需真机 + registry 里的 mqtt-cxx；且 Z20 走的 paho-mqtt3as 在 f133/f136/t113emmc/v85x 目录下都不存在 → 换平台要换 MQTT 方案 | — |
| T113EMMC | — | 未验证 | 同上 | — |
| V85X | — | 未验证 | 同上 | — |

## Z20 板级事实（本轮实测）

- Broker：`mqtt://192.168.x.x:1883`（WSL 里的 EMQX，`admin/zkswe1024`）；PC 侧见证端**直连设备网段会超时**，
  用 `127.0.0.1:1883`（localhost）或进 WSL 跑 `mosquitto_sub` 才通（实测结论）。
- **TLS 场景必须连带声明依赖**：`mqtt-cxx` → `paho-mqtt3as` → `openssl 1.1.1-w`，
  漏 openssl 会链接报 `BIO_read / RAND_bytes / SHA1_*` undefined（实测）。
- `conf.ssl.verify=false` 是"只为验公网通路"的用法（公网 broker 自签/不受信 CA）；产品侧要配 `trust_store`。
- 回调在库自己的线程上跑 → 回调里只置标志位/打日志，**别直接动 UI 控件**（Z20 面板会卡）。
- 同一个 `client_id` 被 broker 互斥：每次重连都 `new` 却不 `delete` 旧 client → 会被 broker 每秒踢 2~3 次（实测过）。
- ⚠️ **重连只能有一个真源（2026-09-28 实测）**：mqtt-cxx/mqtt-cxx 库**自带自动重连**（`onReconnect`
  cause=`automatic reconnect`），若应用层看门狗同时又 `connect()` 并 `new` 一个 client，**两个 client 用同一
  client_id 互相踢** → 自激风暴（真机实测：一分钟 143 次 `connected` / 123 次 `disconnected`，两条
  `disconnected` 相隔 2 ms）。修法二选一：① 关掉库的自动重连，只留应用层一条；② 只留库的重连，
  应用层只做状态监听；**无论如何重连前先 `delete` 旧 client**（回调也要认准当前实例，别让旧 client 回调生效）。
- `publish/subscribe` 返回 true 只代表"提交成功"，不等于 broker 收到（QOS0 更是发完就忘）→ 要送达确认靠 retained + 状态回读对账。

## 复现方式

```bash
# 工程：demos/net-stack-verify-z20（明文 MQTT qos1 收发）
#       demos/net-stack-advanced-z20（MQTTS(TLS) / LWT 遗嘱 / 异常断线重连）
#       最小示例见 packages/mqtt-cxx/example/
cd demos/net-stack-verify-z20 && fsc install && fsc build -p z20
# 部署（/tmp 劫持调试，不动 /res）——⚠️ 单次 restart；先确认没有残留 zkgui 进程
adb -s 192.168.x.x:5555 push .fsc/z20/libzkgui.so /tmp/lib/libzkgui.so
adb -s 192.168.x.x:5555 push ui/main.ftu          /tmp/ui/main.ftu
adb -s 192.168.x.x:5555 push EasyUI.cfg           /tmp/EasyUI.cfg   # startupLibPath=/tmp/lib/libzkgui.so, resPath=/tmp/ui/
adb -s 192.168.x.x:5555 shell setprop ctl.restart zkswe
# 取证：tag = netstack demo（明文）/ netstack2 demo（MQTTS/LWT/重连）
adb -s 192.168.x.x:5555 shell "logcat -d | grep -E '\[MQTT\]|\[MQTTS\]|\[LWT\]|\[RECON\]'"
```

遗嘱代发的见证端（PC 侧，2026-09-29 实测口径）：
```bash
# 设备端注册 will 后 kill -9 制造异常断线；PC 侧订阅 will 主题看 broker 是否代发（实测约 2 s）
# 见证端连 localhost:1883（直连设备网段那个 IP 会超时）
```

⚠️ 部署纪律（踩过）：**确认 `pidof zkgui` 只剩一个、上一次实例已退出**再 `ctl.restart`；连续快速重启会把 MI 全局 init 锁占死 → 黑屏 + 进程 D 状态、`kill -9` 无效，只能断电重启。

## 未验证项与所需条件

- **Z21 / F133 / F136 / T113EMMC / V85X**：这些平台的 registry/包站没有 `mqtt-cxx`（Z20 独有组合），
  要验需先有对应平台包；**本仓不做跨平台推断**。
- **MQTT v5 属性、wss（WebSocket over TLS）**：未测（示例只覆盖 mqtt:// 与 mqtts://）。
- **QoS2（EXACTLY_ONCE）**：未测（实测都是 QoS1）。
- **遗嘱代发的可靠性**：只做了 1 次（异常断线 → 2 s 代发）；未做多次重复与保留位（retained will）回归。
