# example · paho-mqtt3as 最小示例（C API 直调 · **未上机**）

480×480 页面 + 4 个按钮 + 1 个「自检 AUTO」：同步 API（`MQTTClient_*`）与异步 API（`MQTTAsync_*`）各一条闭环。

> ⚠️ **验证状态（务必先读）**：本仓的 MQTT 真机验证都是**经 `mqtt-cxx` 门面**做的
> （明文 / MQTTS(TLS) / LWT 全通，见 `../evidence/`）。**直接调 paho C API 这条路径本仓没有单独上机**，
> 本示例的调用形态按 `../package.yaml` 的 `api` 段（实读包头）书写 → **属"可直接抄、未取证"**。
> 要标 ✅：在 Z20 上跑一遍并留 logcat（tag = `paho demo`），然后更新 `../platforms.md`。

| 文件 | 用途 |
|---|---|
| `ui/main.json` | 页面：连接 / 发布 / 订阅 / 异步连接 / 自检 AUTO + 结果 textview。`cd ui && fui pack ./` |
| `src/logic/mainLogic.cc` | 回调实现：`onArrived`（同步回调，含必须的 `MQTTClient_freeMessage/free`）、`onConnLost`、`jobSync()`、`jobAsync()`（含异步回调） |
| `mainActivity_button_tab.snippet.cpp` | **必须补**：activity 的 `sButtonCallbackTab` 注册（5 行） |
| `Manifest.xml` | 依赖：easyui / log / base-utility / **paho-mqtt3as** / **openssl**（漏 openssl 链接必炸），改完 `fun install` |

## 关键口径（照抄这几条）

```cpp
MQTTClient_create(&cli, "tcp://<broker>:1883", "client-id", MQTTCLIENT_PERSISTENCE_NONE, NULL);
MQTTClient_connectOptions opt = MQTTClient_connectOptions_initializer;   // 别自己 memset
opt.keepAliveInterval = 20;  opt.cleansession = 1;
MQTTClient_setCallbacks(cli, NULL, onConnLost, onArrived, NULL);
MQTTClient_subscribe / MQTTClient_publish / MQTTClient_waitForCompletion / MQTTClient_disconnect / MQTTClient_destroy
```

- ⚠️ **回调里必须 `MQTTClient_freeMessage(&msg)` + `MQTTClient_free(topicName)`**（异步版用 `MQTTAsync_free*`）——本库不替你释放。
- ⚠️ **Manifest 必须显式带 `openssl`**（本包无 Manifest，依赖不会自动进来）：实测漏了报 `BIO_read / RAND_bytes / SHA1_Init/Update/Final` undefined。
- ⚠️ **同一个 `client_id` 在 broker 侧互斥**：两个连接会互踢（实测"每 10 s 重复 new client 不 delete 旧的"→ broker 每秒踢 2~3 次）。
- ⚠️ 业务日常**优先用 `mqtt-cxx`** 的 `mqtt::Client`（本包就是它内部包的那层）；只有要 MQTT v5 属性、原生回调或自己封装时才直接调。
- ⚠️ 回调在库线程 → 只置标志位/打日志；示例里 UI 线程只用 200 ms 定时器刷 textview。

## 三步跑起来

1. `ui/main.json` → 工程 `ui/`，`cd ui && fui pack ./`（出 `main.ftu`）
2. `src/logic/mainLogic.cc` 并进工程 logic；把 `mainActivity_button_tab.snippet.cpp` 的 5 行填进 `src/activity/mainActivity.cpp` 的 `sButtonCallbackTab[]`
3. 改掉 broker 占位（`192.168.x.x`）→ `fun install && fun build -p z20` → 部署见 `../platforms.md`

## 验证点

| 按钮 | 期望 |
|---|---|
| 连接 | `MQTTClient_connect -> 0`（成功码 0；1=版本不符 2=clientID 被拒 3=broker 不可用） |
| 发布 | `publish qos1 -> 0` + `waitForCompletion -> 0（已确认）` |
| 订阅 | `subscribe -> 0`，自己发的 payload 原样收回（`on_message`） |
| 异步连接 | `MQTTAsync_connect -> 0` + 回调 `connected (MQTTAsync)` + 订阅/发消息成功 |
| AUTO | 同步 API 全流程跑完，结尾 `错误数=0` |

> 上表是**按 API 语义写的期望值**（同步版 `rc==0` 为成功）；**真机实测值待补**（本仓未跑，见文件头说明）。
> 已实测的等价链路（经 mqtt-cxx）结果：明文 qos1 订阅/发布/回显全通；MQTTS 连通 + 收发回显 1 条；LWT 异常断线约 2 s 代发。
