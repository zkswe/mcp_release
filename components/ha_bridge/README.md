# ha_bridge —— Home Assistant / MQTT 桥 + 继电器语义 v0.1.0

**能吃就用的东西**：把设备按 **HA MQTT Discovery** 标准接进 Home Assistant（Domoticz 也认，见 `platforms.md` §3），
同时把「继电器（开关）」收拾成**唯一事实源 + 变化通知**，从接口上消灭那个经典事故
（UI 覆盖式刷新把业务上报回调抹掉 → HA 命令下发后状态又翻回去）。

- 对外命名空间 `zk::ha`（唯一对外头 `include/zk/zk_ha_bridge.h`），**源码型**（`include/ + src/ + example/`）
- **不泄漏底层类型**：头文件里没有 `mqtt::Client` / paho / rapidjson 任何符号（底层在 `.cpp` 里）
- 依赖包：`mqtt-cxx`（+ 必带的 `paho-mqtt3as` / `openssl`）、`base-json`、`base-utility`、`log`（可选 `easyui`/`rapidjson`） —— 见 `Manifest.xml`
- 平台：**Z20 已实测**（明文 MQTT / MQTTS / LWT / retained / 重连口径全部来自真机）；**组件形态已在 Z20 真机单独验收**（2026-10-01，FlyThings zkgui 工程形态，5 条判据全过，见 `platforms.md` §6）；其余平台**未验证**（无 mqtt-cxx 包）
- 落地来源：`projects/SmartPanel_HA`（Z20 86 面板，HA + Domoticz 双向实测）

**版本记录**
- **v0.1.0（2026-09-30）** 首版入库：`zk::ha::Bridge`（start/stop/tick + discovery / 命令 / 状态 / retained 校准）
  + `zk::ha::RelayBank`（唯一事实源 + UI 槽/业务具名槽分离）；坑与实测数字全部搬自 `SmartPanel_HA` 真机记录
  （数字出处逐条标注，未取证的写「未取证」）。
  **检查过什么**：`src/` 与 `example/` 已过 `g++ -fsyntax-only -std=c++11 -Wall -Wextra -D__PLATFORM_Z20__=1`
  （0 error / 0 warning，头文件用 Z20 registry 真实包）。
  **2026-10-01 补验收**：组件形态已在 Z20 真机以 **zkgui 工程形态**落地跑通（`fun install && fun build -p Z20`
  真编译 + 真机 5 条判据：连上 broker / retained 上行 / 自动 discovery / 下行命令 → `onCommand` + 继电器真实动作 /
  `start()/stop()` + kick 重连），证据见 `platforms.md` §6；仍未取证的项见同节末尾清单。

---

## 1. 是什么 / 不是什么

**是**：
- 一条 **HA MQTT 桥**：上行 availability / state / status，下行 command，连接成功后自动发 **Discovery**
  （3 路灯具开关，缩写键 `stat_t`/`cmd_t`/`pl_on`/`avty_t`/`dev` 风格，Domoticz 也认）；
- 一套**继电器语义**：`RelayBank` 是唯一事实源，`set()` 变化才通知；UI 视觉单槽与业务具名多路**互不覆盖**；
- 一套**连接纪律**：单一应用层重连真源 + 代次作废旧回调 + 1s 差分兜底 + retained 撤销原语。

**不是**（刻意不做，工程侧自己接）：
- ❌ 不是 MQTT 客户端实现（底层 `mqtt-cxx`，paho 异步）；❌ 不管配置存储（`ConfigStore`）、板内配网页（`WebConfigServer`）、
  二维码配网：**组件不写死任何地址/账号/口令/前缀/设备名，默认值一律为空**，配置由调用方给；
- ❌ 不做 UI / 逻辑（情景引擎 `SceneManager`、整机状态 JSON 的**内容**由业务通过 `statusJson` 回调给）；
- ❌ 不做「本地主机/从机」那套板内 broker 互联（`LocalLink` + `MiniBroker`/`LocalBrokerService`）——
  它与 HA 模式**互斥**，属于同工程的另一条链路，本组件不纳入（见 §9）。

---

## 2. 用法（能直接抄）

```cpp
#include "zk/zk_ha_bridge.h"

static void onUI_init() {
    zk::ha::Config cfg;                        /* 默认值全空：不填就明确报错，不猜、不写死 */
    cfg.server   = "mqtt://<broker>:1883";     /* 必填 */
    cfg.prefix   = "smartpanel/" + deviceId;   /* 必填（或只给 deviceId 由组件派生前缀）*/
    cfg.deviceId = deviceId;                   /* HA unique_id / device 归组 */
    cfg.deviceName = "客厅面板";                /* HA 里显示的名字；空 -> 回落 deviceId */
    cfg.password = haToken;                    /* HA 长令牌（粘贴时先去换行与空格）*/
    cfg.relayNames.push_back("客厅灯");
    cfg.relayNames.push_back("卧室灯");
    cfg.relayNames.push_back("灯带");

    /* 命令回调：**在 mqtt-cxx 的库线程上跑** —— 只置标志位，别动 UI 控件 */
    cfg.onCommand = [](int ch, bool on) { pendingCmd = { ch, on }; };
    /* 整机状态 JSON：由业务给（组件不编造状态内容）*/
    cfg.statusJson = []() { return buildStatusJson(); };

    zk::ha::Result r = zk::ha::Bridge::instance().start(cfg);   /* 非阻塞，内部线程建连 */
    if (!r.ok()) LOGW("ha start failed: %s", r.msg.c_str());     /* msg 是人话 */
}

static bool onUI_Timer(int id) {               /* 1000 ms 定时器 */
    if (id == 0) zk::ha::Bridge::instance().tick();   /* 重连（唯一真源）+ 1s 差分兜底 */
    return true;
}

static void onUI_quit() { zk::ha::Bridge::instance().stop(); }

/* 触摸/按键：一律走唯一事实源，状态回发是自动的 */
static void onCardTouched(int ch) { zk::ha::Bridge::instance().relays().toggle(ch); }
```

### 主题口径（全部 retained，除 `event`）

| 方向 | 主题 | payload | 说明 |
|---|---|---|---|
| 上行 | `<prefix>/availability` | `online` / `offline` | LWT 遗嘱兜底（异常断线由 broker 代发 offline） |
| 上行 | `<prefix>/switch/relay_<n>/state` | `ON` / `OFF` | 继电器状态（retained，覆盖旧值） |
| 上行 | `<prefix>/status` | 整机 JSON | 内容来自 `Config::statusJson` |
| 上行 | `<prefix>/event` | JSON | **非** retained（事件不进历史状态） |
| 下行 | `<prefix>/switch/relay_<n>/command` | `ON` / `OFF` | **只认这一个形状**，其余一律忽略（§4 坑 4） |
| 发现 | `<discoveryPrefix>/switch/<uid>_relay_<n>/config` | HA discovery JSON | `<discoveryPrefix>` 空则 `homeassistant` |

`<uid>` = 前缀里 `/` 换 `_`（如 `smartpanel/PANEL-A1B2` → `smartpanel_PANEL-A1B2`）。
业务自己的主题（情景清单之类）走 `Config::extraSubscriptions` 订阅、消息交 `Config::onMessage`——
**组件不预设任何业务主题字面量**。

---

## 3. 配置项 / API

### Config（默认值：字符串**全空**、`channels=3`、`lwtEnabled=true`、`publishStatusJson=true`、退避 10→60 s）

| 字段 | 默认 | 说明 |
|---|---|---|
| `server` | `""` | **必填**，`mqtt://host:1883`（TLS `mqtts://host:8883`） |
| `username` / `password` | `""` | 可空；HA 长令牌放 `password` |
| `prefix` | `""` | **必填**；空且 `deviceId` 非空 → 前缀 = `deviceId`（不编造层级） |
| `deviceId` | `""` | unique_id / device 归组；prefix 已给时可留空 |
| `deviceName` | `""` | 空 → 回落 `deviceId`（不写死字面量） |
| `clientId` | `""` | 空 → 由 prefix 派生（`/`→`_`） |
| `discoveryPrefix` | `""` | 空 → `homeassistant`（HA 标准发现前缀，协议常量） |
| `manufacturer` / `model` | `""` | 空 → Discovery 里**不发**该字段（不编造） |
| `relayNames` | 空 | 空项 → 回落 `relay_<n>` |
| `extraSubscriptions` | 空 | 额外订阅（支持 `+`/`#`），交 `onMessage` |
| `channels` | `3` | 1..8（>8 截断并 warning） |
| `lwtEnabled` / `publishStatusJson` | `true` | 遗嘱 / 连接后是否发 status |
| `tickMs` | `1000` | 调用方 tick 周期建议值 |
| `reconnectMinMs` / `reconnectMaxMs` | `10000` / `60000` | 退避窗口（10→20→40→封顶 60 s） |
| `onCommand` / `onMessage` / `onConnected` / `onDisconnected` / `statusJson` | 空 | **都在库线程上跑**（`statusJson` 例外：由 tick/库线程调，内部只读状态） |

### Bridge API

| 成员 | 作用 |
|---|---|
| `Result start(const Config&)` | 启动（非阻塞）。配置不全 → `HA_ERR_NOT_CONFIGURED` + 人话；重复调用会先 `stop()`（= 换配置重连） |
| `void stop()` | 停止并**销毁 client**（代次 +1，旧回调作废） |
| `Result tick()` | 周期驱动（建议 1 s）：未连 → 退避重连；已连 → 1 s 差分兜底 |
| `bool started()` / `bool connected()` | 连接状态 |
| `RelayBank& relays()` | 唯一事实源（`get/set/toggle/notifyAll` + listener 两套槽） |
| `Result publishState(int,bool)` / `publishAllStates()` | 发 state（未连接时返回 `HA_ERR_NOT_CONNECTED`，**不静默丢**） |
| `Result publishStatus()` | 发 `<prefix>/status`（`statusJson` 没给 → 明确报错，不编造） |
| `Result publishEvent(const std::string&)` | 发事件（非 retained） |
| `Result publishAvailability(bool)` | 发 online/offline |
| `Result publishDiscovery()` | 重发 Discovery（改设备名/继电器名后调） |
| `Result clearDiscovery(component, objectId)` | **retained 撤销**：往 `.../config` 发空 payload + retained |
| `std::string prefix()/uniqueId()` | 实际前缀 / unique_id 基 |
| `int reconnects()/generation()` | 累计建连次数 / client 代次（排障用） |
| `const char* lastError()` | 最后一条错误（人话）；无错误返 `""`（不返 NULL） |
| `void setLogHook(zk_ha_log_fn, void*)` | 日志接出去（app 模式 stdout 是 `/dev/null`，必须接） |

---

## 4. 已知坑（真机踩出来的，照做即可）

1. ⚠️ **同一个 `client_id` 在 broker 侧互斥**：每次重连 `new` 却不 `delete` 旧 client
   → 多个 client 抢同一 id，broker 每秒踢 2~3 次（实测）。
   本组件的做法：**先回收旧 client（锁内摘指针 + 代次 +1，锁外 delete）再建新的**，且只保留一个 client 引用；
   旧 client 的迟到回调按代次丢弃。
2. ⚠️ **重连只能有一个真源**：`mqtt-cxx` 底层（paho 异步）**自带 automatic reconnect**（实测
   `on_connected cause=automatic reconnect`，断网 90 s → 回连约 **10.5 s**）；若应用层看门狗又 `connect()`
   并 `new` 一个 client，两个 client 同 client_id **互踢成自激风暴** ——
   **实测 1 分钟 143 次 `connected` / 123 次 `disconnected`**（来源 `packages/mqtt-cxx/package.yaml`，
   口径另有「143/90+ 次」表述）。
   本组件的立场：**应用层 `tick()` 是唯一的建连动作**（带退避），并保证任何时刻只有一个 client 实例；
   如果工程侧改用库自带重连，就必须**不要**再调 `tick()` 的重连路径（否则回到互踢）。
3. ⚠️ **retained 是持久状态，撤销要发空 payload**：旧版本发过的实体不撤销会一直在 HA/Domoticz 里阴魂不散
   → 用 `clearDiscovery(component, objectId)`（空 payload + retained）。
4. ⚠️ **命令必须按形状过滤**：broker 每次（重）订阅后会**回放该主题上的 retained**；把回放、空 payload 或
   状态类 payload 当命令执行 = **重连一次关一次灯**（真机事故）。本组件只认
   `<prefix>/switch/relay_<n>/command` 且 payload **恰为** `ON`/`OFF`，其余一律忽略并 warning。
5. ⚠️ **回调在 mqtt-cxx 的库线程上跑**：`onCommand`/`onMessage`/`onConnected`/`onDisconnected` 里
   **只置标志位/打日志，别直接动 UI 控件**（Z20 面板实测会卡/崩）；跨线程动作挪到 `tick()` 里做。
6. ⚠️ **覆盖式 listener 会抹掉别人的回调**（`RelayManager` 事故复盘）：旧实现只有一个 `setListener()`，
   某页面 `onUI_init` 用它刷卡片时 `clear()` 了整个列表 → Bridge 注册的上报回调被抹掉 → 继电器再变化也不回发，
   表现为「HA 点过去一会儿又切回来」。本组件的接口就把两类槽分开：`setUiListener()`（覆盖式，只影响 UI）
   与 `addListener(key, fn)`（具名，同 key 覆盖 = **幂等**，每次重连都可放心重注册）。
   → **Bridge 自己注册业务槽时不用"只注册一次"的门闩**：门闩一旦被抹掉，本进程内永远无法恢复。
7. ⚠️ **`publish/subscribe` 返回 true 只代表"提交成功"**，不等于 broker 收到（QOS0 发完就忘）
   → 要送达确认只能靠 **retained + 状态回读对账**（本组件的 1 s 差分兜底就是这个用途）。
8. ⚠️ **继电器 init/restore 也会"反复关灯"**（工程侧沿用 RelayManager 时注意，两条真机事故）：
   ① `init()` 被多个页面 `onUI_init` 各调一次，每次 `restore()` 都会把缺省掩码 0 回写 → 每切一次页把灯写 OFF
   → **进程内只初始化一次**；② 存档键**不存在**时不许回写硬件（哨兵 `-1` 区分"键不存在"与合法的 `0`）
   → **没存档就一个电平都别写**。本组件的 `RelayBank` 不碰硬件（只存状态），硬件语义由工程侧实现。

---

## 5. 依赖包（Z20）

| 包 | 版本 | 为什么 |
|---|---|---|
| `mqtt-cxx` | `^3.2.0` | `mqtt::Client`（paho 异步门面） |
| `paho-mqtt3as` | `^1.3.13` | **不能漏**：mqtt-cxx 只发一个 `.a` + 一个头（头里 `#include <MQTTAsync.h>`），链接也靠它 |
| `openssl` | `1.1.1-w` | paho 的 TLS 后端；**漏了会链接报 `BIO_read / RAND_bytes / SHA1_*` undefined**（实测） |
| `base-json` | `^3.1.0` | Discovery/状态对象组装（`base::JSONObject`） |
| `base-utility` | `^10.8.5` | `base/functional.h`（回调类型）、生成头固定 `#include <base/…>` |
| `log` | `0.0.0` | `android/log.h`（`base-utility/base/log.h` 需要它） |
| `easyui` | `^2.2.0` | **可选**：只为「没装日志钩子」时的 `LOGD/LOGW/LOGE` 兜底（`__has_include("utils/Log.h")` 自动探测）。用 `setLogHook()` 的工程不需要它 |
| `rapidjson` | `1.1.0` | **可选**：工程侧解析 HA 回传 JSON 时用（本组件自身不依赖） |

⚠️ **改过 Manifest 必须重跑 `fun install`**，否则新包的 include 路径不进 CMake。
详见 `Manifest.xml` 注释。

---

## 6. 排错

| 症状 | 原因 / 处理 |
|---|---|
| 一直连不上 | `start()` 返回的 `Result.msg` + `lastError()`；先确认 `server` 带 `mqtt://`；Z20 上确认 Manifest 没漏 `paho-mqtt3as`/`openssl` |
| HA 实体反复掉线（1 分钟几十次） | 别处又在 `new` 同 `client_id` 的 client（坑 1/2）。看日志里 `gen=` 是否在频繁增长、`reconnects()` 是否暴涨 |
| 重连后灯被关掉 | 命令没做形状过滤（坑 4），或工程侧把 retained 回放当命令执行 |
| HA 命令能到、状态不回 | 上报 listener 被覆盖式注册抹掉（坑 6）→ 用 `addListener("key", …)` |
| 改了设备名 HA 不更新 | 改名后要重发：`start()`（内部先 stop 再连）或 `publishDiscovery()` |
| 换平台编不过 | 该平台 registry 没有 `mqtt-cxx`/`paho-mqtt3as`（`platforms.md` §2） |
| 日志啥都看不到 | app 模式 stdout 是 `/dev/null`：`setLogHook()` 装上钩子 |

---

## 7. 验收口径（可复用）

1. **上行**：PC 侧见证端（⚠️ 连 **`127.0.0.1:1883`** / 进 WSL 跑 `mosquitto_sub`，**直连设备网段那个 IP 会超时** —— Z20 实测）
   订阅 `<prefix>/#` + `homeassistant/#`，应看到 `availability=online` → `switch/<uid>_relay_N/config` → `state=ON/OFF` → `status`。
2. **下行**：`mosquitto_pub -t '<prefix>/switch/relay_1/command' -m OFF` → 设备回发 `state=OFF`（面板真的执行）。
3. **LWT**：`kill -9` 制造异常断线 → broker 代发 `availability=offline`（实测 **约 2 s**）。
4. **重连**：断网 > keepalive → `on_disconnected`；恢复 → 再连上；**检查 `reconnects()` 增长是否温和**
   （风暴就是坑 2 复现）。
5. **retained 校准**：清空 broker 上的 retained 后重启设备，HA 侧实体状态应与面板一致；
   断电重启后 state 不得翻回旧值（对齐 `RelayManager::notifyAll()` 语义）。
6. **实体清理**：`clearDiscovery()` 后 HA 侧该实体消失。

---

## 8. 文件

```
components/ha_bridge/
├─ include/zk/zk_ha_bridge.h      # 唯一对外头（zk::ha::Bridge / RelayBank / Config / Result）
├─ src/zk_ha_bridge.cpp           # 实现（mqtt-cxx + base-json + log；代次/退避/差分/retained）
├─ example/zk_ha_bridge_demo.cc   # FlyThings 逻辑示例（连 broker → 发一次 → 收命令打印）
├─ example/README.md              # 三步接线 + 见证端确认步骤
├─ platforms.md                   # 逐平台实测/未验证 + Domoticz 兼容口径 + 坑
└─ Manifest.xml                   # 底层依赖 + 本模块被引用的两种方式
```

## 9. 移植注意 / 本组件**未纳入**的东西

真源工程里还有几块与 HA 链路**严格互斥**或**工程私有**的东西，本组件刻意不带（免得你顺手引进来）：

| 真源 | 为什么没纳入 | 移植时注意 |
|---|---|---|
| `LocalLink`（本地主机/从机：广播 `smartpanel/broadcast/scene` + 各机 `status`） | 与 HA 模式**由 runMode 二选一**，同一时刻只有一方持有 broker 连接 | 两套链路必须**互斥**：同一时刻只有一个发布者写 `<prefix>/status`、`switch/relay_N/state`，否则互相覆盖 retained |
| `MiniBroker`（app 内嵌极简 broker）/ `LocalBrokerService`（拉起板内 `zkmqtt`） | 板内 broker 兜底，属「本地主机」链路的实现细节 | 内嵌 MiniBroker **只支持 QoS0、无 Will、broker 随 app 死**；能拉起独立服务就别用内嵌 |
| `ConfigStore` / `WebConfigServer`（prefs + 板内配网页 + 二维码） | 配置来源是工程选择（本组件只吃 `Config`） | 「不写死」是硬口径：给用户一个手机扫码就能填地址与长令牌的入口 |
| `SceneManager`（情景）/ `PanelLink::statusJson()`（整机状态生成） | 业务内容，组件不编造 | 用 `extraSubscriptions` + `onMessage` 接情景主题，用 `statusJson` 回调整机状态 |

**铁律（跨链路都成立）**：继电器状态**只读一个事实源**，任何一侧都不得自己缓存/推算，
也不得用可空指针兜底成 `false`。

## 10. 出处

| 项 | 内容 |
|---|---|
| 真源实现 | `projects/SmartPanel_HA/src/network/MqttBridge.{h,cpp}`、`src/device/RelayManager.{h,cpp}` |
| 邻接链路（未纳入） | `projects/SmartPanel_HA/src/network/{LocalLink.*, MiniBroker.*, LocalBrokerService.*}` |
| 配置键语义 | `projects/SmartPanel_HA/src/storage/ConfigStore.cpp`（键名/默认值语义；**开源版默认全空**） |
| 事实与结论 | `projects/SmartPanel_HA/docs/{DOMOTICZ-COMPAT.md, HA-CONFIG-WEB.md}`、`packages/mqtt-cxx/{platforms.md, package.yaml}` |
| 组件规范 | `components/README.md`、`knowledge/devflow/reusable-components.md` |
