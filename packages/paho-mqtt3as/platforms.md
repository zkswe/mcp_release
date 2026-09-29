# paho-mqtt3as · 平台实测表

> 口径：**只写实测过的**；没测的写「未验证」+ 需要什么条件，不猜、不套别的平台结论。
> 结论来源：`package.yaml` 的 `verified_20260929` / `verified_20260929_will` 块 + `evidence/netstack_auto_20260929.txt`、
> `evidence/netstack2_20260929.txt`、`evidence/lwt_will_20260929.txt`。

| 平台 | 版本 | 结论 | 实测内容 | 证据 |
|---|---|---|---|---|
| **Z20**（SSD20X 480×480 · 86 面板） | paho-mqtt3as 1.3.13 | 🟡 间接可用（**经 `mqtt-cxx` 上层**跑通；明文路径实测，TLS 路径包自身未标已验） | 由 `mqtt::Client` 内部使用（业务侧未直接调 `MQTTAsync_*`）：明文 `mqtt://…:1883` 连接 + qos1 订阅/发布/回显全部成功 → **paho 明文路径可用**；`netstack2` 证据里另有 MQTTS（`mqtts://test.mosquitto.org:8883`，`ssl.verify=false`）连接 + 收发成功（仍是经 mqtt-cxx 走 paho）；LWT 遗嘱由 broker 在异常断线后约 2 s 代发 | `evidence/netstack_auto_20260929.txt`、`evidence/netstack2_20260929.txt`、`evidence/lwt_will_20260929.txt` |
| Z21 | — | 未验证（**平台无此包**） | `paho-mqtt3as 1.3.13` 在 z21/f133/f136/t113emmc/v85x 目录下**都不存在**（`package.yaml` gotcha 明确）→ Z21 那轮 AUTO 也明写「不验 MQTT」。要验需该平台先有这个包 | `evidence/z21_20260929.txt` |
| F133 / F136 | — | 未验证 | 同上（本地 registry 无此包） | — |
| T113EMMC | — | 未验证 | 同上 | — |
| V85X | — | 未验证 | 同上 | — |

## Z20 板级事实（本轮实测 / 二进制反查）

- **本包是本地 z20 registry 独有**；且**没有 README、没有 Manifest.xml** → 依赖不会自动带进来，
  **必须自己在 Manifest 里显式声明 `openssl`（+ pthread）**：不加会链接失败（`BIO_read / RAND_bytes / SHA1_Init/Update/Final` undefined，实测）。
- 库名里的 `as` = **async + SSL**：二进制里能查到 `SSL_CTX_new / SSL_connect` → 链接期需要 openssl（Z20 是 `openssl 1.1.1-w`）。
- `mqtt-cxx` 3.2.0 的 README 说"不支持 mqtts/wss 就用 paho-mqtt3a"，但 **z20 registry 没有 paho-mqtt3a** → Z20 就用本包。
- 同时提供 C 同步 API（`MQTTClient_*`）与异步 API（`MQTTAsync_*`）；业务一般走 `mqtt-cxx` 的 `mqtt::Client`，只有要 v5 属性/原生回调才直接调。
- 同步 API 回调里必须 `MQTTClient_freeMessage()` + `MQTTClient_free()`，否则消息体泄漏（本库不替你释放）。
- 同一个 `client_id` 在 broker 侧互斥（两个连接互踢）——实测过"每 10 s 重复 new client 不 delete 旧的"→ broker 每秒踢 2~3 次。

## 复现方式

```bash
# 工程：demos/net-stack-verify-z20（paho 由 mqtt-cxx 间接使用，明文 MQTT qos1）
#       demos/net-stack-advanced-z20（MQTTS(TLS) / LWT 遗嘱 / 异常断线重连）
#       C API 直调的最小示例见 packages/paho-mqtt3as/example/（⚠️ 该示例路径本仓未单独上机，见下节）
cd demos/net-stack-verify-z20 && fun install && fun build -p z20
# 部署（/tmp 劫持调试，不动 /res）——⚠️ 单次 restart；先确认没有残留 zkgui 进程
adb -s 192.168.x.x:5555 push .fun/z20/libzkgui.so /tmp/lib/libzkgui.so
adb -s 192.168.x.x:5555 push ui/main.ftu          /tmp/ui/main.ftu
adb -s 192.168.x.x:5555 push EasyUI.cfg           /tmp/EasyUI.cfg   # startupLibPath=/tmp/lib/libzkgui.so, resPath=/tmp/ui/
adb -s 192.168.x.x:5555 shell setprop ctl.restart zkswe
adb -s 192.168.x.x:5555 shell "logcat -d | grep -E '\[MQTT\]|\[MQTTS\]|\[LWT\]|\[RECON\]'"
```

⚠️ 部署纪律（踩过）：**确认 `pidof zkgui` 只剩一个、上一次实例已退出**再 `ctl.restart`；连续快速重启会把 MI 全局 init 锁占死 → 黑屏 + 进程 D 状态、`kill -9` 无效，只能断电重启。

## 未验证项与所需条件

- **直接调 `MQTTAsync_*` / `MQTTClient_*`（不经 mqtt-cxx）**：本仓**没有单独上机的记录** → `example/` 里的 C API 示例
  是按包头签名写的，属于"可直接抄、但未取证"的形态；要标 ✅ 需在 Z20 上单独跑一轮（本项目验证工程 `projects/pkg_netstack` 系列）。
- **`mqtts://` TLS 路径**：`package.yaml` 的 `verified_20260929.note_2` 明说"本轮未验证（本地无 TLS broker）"，
  后续 `netstack2` 那轮的公网 MQTTS 成功是**经 mqtt-cxx 上层**拿到的 → 本文件按"间接证据、包自身未标已验"如实记录。
- **MQTT v5 属性（`MQTTProperties`）/ 离线持久化（`MQTTCLIENT_PERSISTENCE_FILE`）**：未测。
- **Z21 / F133 / F136 / T113EMMC / V85X**：平台无此包 → 先要有包才能谈验证。
