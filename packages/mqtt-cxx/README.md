# mqtt-cxx —— MQTT C++ 门面（Z20 上的标准 MQTT 用法）

一个头 + 一个静态库：`mqtt::Client`（publish/subscribe/unsubscribe/isConnected + 连接/掉线回调 +
LWT 遗嘱 + SSL 配置项），底层是 paho 的**异步 API**。Z20 在跑的样例：`projects/SmartPanel_HA/src/network/MqttBridge.cpp`（Home Assistant MQTT 接入）。

**怎么用**
1. Manifest（**paho 不能漏**，TLS 还要 openssl）：`<package id="mqtt-cxx" version="^3.2.0"/>` +
   `<package id="paho-mqtt3as" version="^1.3.13"/>`（Z20 只有 `as` 变体，**没有 paho-mqtt3a**）+
   `<package id="openssl" version="1.1.1-w"/>` → `fun install` → `fun build -p z20`。
2. 关键 API：`mqtt::Client::Configuration conf;`（`server="mqtt://host:1883"`、`client_id/user/password`、
   `will.*`、`on_connected/on_disconnected`）→ `mqtt::Client client(conf);`（构造即连接，**要 try/catch**）
   → `subscribe(topic, mqtt::QOS_AT_LEAST_ONCE, handler)` / `publish(topic, payload, qos, retained)`。
3. 同 client_id 互踢、重连要 delete 旧 client、回调线程别动 UI、retained 清理等 6 条坑 → `package.yaml`。

⚠️ 未实测（`verified: null`）：实读头文件 + README + Z20 真实工程用法交叉验证写成。
