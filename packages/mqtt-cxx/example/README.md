# example · mqtt-cxx 最小示例（可直接拷）

480×480 页面 + 4 个按钮 + 1 个「自检 AUTO」：每键 = 一次 `mqtt::Client` 调用，结果进 textview + logcat。

| 文件 | 用途 |
|---|---|
| `ui/main.json` | 页面：发布 / 订阅回显 / 遗嘱 LWT / MQTTS(TLS) / 自检 AUTO + 结果 textview。`cd ui && fui pack ./` |
| `src/logic/mainLogic.cc` | 回调实现：`ensurePlain()`（惰性建连 + 注册 LWT）、三个回调（connected / disconnected / message）、`jobPub/jobSub/jobWill/jobMqtts` |
| `mainActivity_button_tab.snippet.cpp` | **必须补**：activity 的 `sButtonCallbackTab` 注册（5 行） |
| `Manifest.xml` | 依赖：easyui / log / base-utility / mqtt-cxx / paho-mqtt3as / openssl / z，改完 `fsc install` |

**来源**：`demos/net-stack-verify-z20`（明文 qos1 订阅→发布→回显→取消订阅）+ `demos/net-stack-advanced-z20`（MQTTS(TLS) / LWT 遗嘱 / 异常断线自动重连）——都真机验证过。

## 关键口径（照抄这几条）

```cpp
mqtt::Client::Configuration conf;
conf.server = "mqtt://<broker>:1883";            // TLS 用 mqtts://<broker>:8883（要 paho-mqtt3as + openssl）
conf.will.topic = "...";  conf.will.message = "offline";   // LWT：异常断线时 broker 代发
conf.on_connected / on_disconnected;             // 库线程回调 → 只置标志位/打日志，别动 UI
mqtt::Client client(conf);                       // 构造即连接（异步，看回调 / isConnected）
```

- ⚠️ **TLS 要连带声明依赖**：`mqtt-cxx` + `paho-mqtt3as` + `openssl 1.1.1-w`；漏了 openssl → `BIO_read/RAND_bytes/SHA1_*` undefined。
- ⚠️ **同一 `client_id` 在 broker 侧互斥**：重连时先 `delete` 旧 client（反复 new 不 delete → broker 每秒踢 2~3 次，实测）。
- ⚠️ **回调别动 UI 控件**（Z20 面板会卡）；真正的 subscribe/publish 放到主流程/worker 里做。
- ⚠️ 示例里 MQTTS 用 `conf.ssl.verify = false`，**只为验公网通路**（`test.mosquitto.org` 不受信 CA）；产品要配 `trust_store`。
- ⚠️ `publish` 返回 true 只代表"提交成功"，不等于 broker 收到 → 要送达对账用 retained + 状态回读。

## 三步跑起来

1. `ui/main.json` → 工程 `ui/`，`cd ui && fui pack ./`（出 `main.ftu`）
2. `src/logic/mainLogic.cc` 并进工程 logic；把 `mainActivity_button_tab.snippet.cpp` 的 5 行填进 `src/activity/mainActivity.cpp` 的 `sButtonCallbackTab[]`
3. 改掉 broker 占位（`192.168.x.x`／用户名口令）→ `fsc install && fsc build -p z20` → 部署见 `../platforms.md`

## 验证点（真机实测口径，见 `../evidence/`）

| 按钮 | 期望（Z20 实测值） |
|---|---|
| 发布 | `publish -> OK`，`isConnected()=1`（broker 侧能看到该 topic 的报文） |
| 订阅回显 | `subscribe -> OK`，自己发的 payload **原样收回**（`on_message len=35`），`unsubscribe -> OK` |
| 遗嘱 LWT | 注册成功；**用 `kill -9` 制造异常断线 → broker 约 2 s 代发遗嘱**（见证端见下） |
| MQTTS(TLS) | `mqtts://test.mosquitto.org:8883` 连上 + qos1 收发回显 1 条 |
| AUTO | 结尾 `错误数=0` |

遗嘱代发的见证端（PC 侧）：
```bash
# 设备端点「遗嘱 LWT」注册 → adb shell "kill -9 <zkgui pid>" 制造异常断线 → PC 侧订阅 will 主题看是否代发
# ⚠️ 见证端连 localhost:1883（直连设备网段那个 IP 会超时，实测）
```
