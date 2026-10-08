# paho-mqtt3as —— MQTT C 客户端（async + SSL）预编译库

Z20 的 MQTT 底层库：`libpaho-mqtt3as.a`/`.so`（**as = async + SSL**），头文件同时给异步（`MQTTAsync_*`）
和同步（`MQTTClient_*`）两套 C API。**日常别直接用它**——Z20 用 `mqtt-cxx` 的 `mqtt::Client`（它包的就是
`MQTTAsync.h`）；要 MQTT v5 属性 / 原生回调时才下探到本包。

**怎么用**
1. Manifest（本包**没有 Manifest.xml**，依赖不会自动带出来）：
   `<package id="paho-mqtt3as" version="^1.3.13"/>` + **`<package id="openssl" version="1.1.1-w"/>`**
   （二进制里有 `SSL_CTX_new`/`SSL_connect` → 链接期必须有 openssl）→ `fsc install` → `fsc build -p z20`。
2. 关键 API：同步 `MQTTClient_create/connect/setCallbacks/subscribe/publish/disconnect/destroy`；
   异步 `MQTTAsync_create/setCallbacks/connect/subscribe/sendMessage/disconnect/destroy`。
3. 符号表 / 6 条坑 / 跨平台可用性（**只有 Z20 有，没有 paho-mqtt3a**）→ `package.yaml`。

⚠️ 未实测（`verified: null`）：实读头文件 + 二进制符号反查写成。
