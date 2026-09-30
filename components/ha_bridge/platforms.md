# ha_bridge · 平台实测表

> 口径：**只写实测过的**；没测的写「未验证」+ 缺什么条件，不猜、不套别的平台结论。
> 结论来源：`packages/mqtt-cxx/{platforms.md, package.yaml}`（2026-09-29 三块真机验证记录，Z20）
> + `projects/SmartPanel_HA/docs/{DOMOTICZ-COMPAT.md, HA-CONFIG-WEB.md}`（2026-09-30 真机/网关实测）。
> 本组件自身的**组件形态尚未单独上机**（见 §6「未验证项」）。

---

## 1. 总表

| 平台 | 可用性 | 前提 | 实测内容 |
|---|---|---|---|
| **Z20**（SSD20X 480×480 · 86 面板） | ✅ **可用**（`mqtt-cxx` 3.2.0） | Manifest 必须一起声明 `mqtt-cxx` + `paho-mqtt3as` + `openssl 1.1.1-w`（漏 openssl 链接报 `BIO_read / RAND_bytes / SHA1_*` undefined） | 明文 `mqtt://…:1883`（EMQX）：`on_connected` 触发、`isConnected()=1`、qos1 订阅→发布→`on_message` 原样回显（len=35）、`unsubscribe` OK；MQTTS `mqtts://test.mosquitto.org:8883`（`ssl.verify=false`）连通 + qos1 收发回显；LWT 注册后 **`kill -9` 异常断线 → 约 2 s broker 代发遗嘱**（PC 见证端，payload 与注册值一致）；断线重连：`enableWifi(false)` 90 s → `on_disconnected`，`enableWifi(true)` 后 **`on_connected` 再触发（cause=`automatic reconnect`，≈10.5 s）** |
| Z21 | ❌ 未验证（**平台无此包**） | Z21 registry **没有 `mqtt-cxx` / `paho-mqtt3as`** | 不验 MQTT（换平台要换 MQTT 方案） |
| F133 / F136 | ❌ 未验证 | 同上：f133/f136/t113emmc/v85x 目录下**都没有** `paho-mqtt3as` | — |
| T113EMMC | ❌ 未验证 | 同上 | — |
| V85X | ❌ 未验证 | 同上 | — |

**证据**：`packages/mqtt-cxx/evidence/{netstack_auto_20260929.txt, netstack2_20260929.txt, lwt_will_20260929.txt}`。

**不做跨平台推断**：Z20 的组合（mqtt-cxx 3.2.0 + paho-mqtt3as 1.3.13 + openssl 1.1.1-w）是本仓唯一实测组合。

### Z20 板级事实

- **部署纪律（踩过）**：确认 `pidof zkgui` 只剩一个、上一次实例已退出再 `ctl.restart`（连续快速重启会把 MI 全局 init 锁占死 → 黑屏 + 进程 D 状态，`kill -9` 无效，只能断电）。
- 另有 `/tmp` 劫持调试法（不动 `/res`）：`EasyUI.cfg` 指向 `/tmp/lib/libzkgui.so` + `/tmp/ui/`。
- 设备 shell 常缺 `md5sum/grep` 等 → 用 `tools/busybox/bin/z20/busybox`。

---

## 2. 主题口径与 availability / Discovery（Z20 实测）

| 项 | 口径 | 实测 |
|---|---|---|
| 前缀 | 工程侧给（真源工程：`smartpanel/<deviceId>`；`<deviceId>` = 芯片唯一 ID 前 8 字节） | ✅ |
| availability | `<prefix>/availability` = `online` / `offline`，**retained**；`offline` 由 LWT 兜底 | ✅ 异常断线约 2 s 代发（见总表） |
| state | `<prefix>/switch/relay_<n>/state` = `ON`/`OFF`，**retained**；连上后主动推一遍新鲜状态覆盖 broker 残留 | ✅ Domoticz 侧读到状态并与面板一致 |
| command | `<prefix>/switch/relay_<n>/command` = `ON`/`OFF`；**只认这一个形状** | ✅ Domoticz 点 `switchlight idx=3 On` → 面板 `relay_3/state` 由 OFF→ON，点 Off 回 OFF（面板真的执行） |
| status | `<prefix>/status` = 整机 JSON（retained） | ✅ |
| Discovery | `<discoveryPrefix>/switch/<uid>_relay_<n>/config`（默认 `homeassistant`），缩写键（`uniq_id/stat_t/cmd_t/pl_on/pl_off/stat_on/stat_off/avty_t/pl_avail/pl_not_avail/ic/dev`）+ `dev` 归组对象（`ids/name/mf/mdl`） | ✅ Domoticz 侧建出 3 个 Light/Switch |
| 顺序 | 先 `online` → 再 discovery/订阅 → 最后推新鲜状态（HA 才不会把 discovery 当成不可用） | ✅（真源工程口径） |

---

## 3. 必须写进的坑（全是真机踩出来的）

1. **同一个 `client_id` 在 broker 侧互斥**：每次重连 `new` 却不 `delete` 旧 client → broker 每秒踢 2~3 次（实测）。
   → 组件做法：建新之前先**回收旧 client**（摘指针 + 代次 +1 → 锁外 `delete`），旧回调按代次丢弃。
2. ⚠️ **重连只能有一个真源**：`mqtt-cxx` 底层 paho **自带 automatic reconnect**（实测 `cause=automatic reconnect`）；
   应用层看门狗若又 `connect()` 并 `new` client，两个 client 同 `client_id` **互踢风暴** ——
   **实测 1 分钟 143 次 `connected` / 123 次 `disconnected`**（两条 `disconnected` 相隔 2 ms），HA 实体反复掉线。
   另有一处口径写作「1 分钟 143/90+ 次」。
   修法（二选一）：① 关掉库的自动重连，只留应用层一条；② 只留库的重连，应用层只做状态监听。
   **无论如何重连前先 `delete` 旧 client，并让回调认准当前实例**（本组件 = `gen` 代次 + 锁内翻标志）。
   本组件默认走 ①：`tick()` 是唯一的建连动作，退避 **10→20→40→封顶 60 s**。
3. **retained 撤销要发空 payload**：`retained` 是持久状态，清不掉会一直影响新订阅者。
   → `clearDiscovery(component, objectId)` = 往 `…/config` 发**空 payload + retained**。
   （真源工程用它清掉旧版本发过的 `sensor`/`button` 残留实体。）
4. **回调线程别动 UI**：`on_connected`/`on_disconnected`/消息回调都在 **mqtt-cxx 的库线程**上跑；
   回调里只置标志位/打日志，**别直接动 UI 控件**（Z20 面板实测会卡）。跨线程动作放 `tick()`。
5. **`setListener()` 是覆盖式的（真源工程事故）**：只有一个 UI 槽且会清整个列表 → 某页面 `onUI_init` 用它刷卡片时
   把 Bridge 注册的上报回调抹掉 → 「HA 命令下发后状态又翻回旧值（切过去一会儿又切回来）」。
   本组件从接口上分离：`setUiListener()`（覆盖式单槽）/ `addListener(key, fn)`（具名多路、同 key 覆盖 = 幂等）。
   → **业务监听别用"只注册一次"的门闩**：一旦被抹掉，本进程内永远恢复不了（真机上就是这么死的）。
6. **MQTT 见证端要连 `127.0.0.1:1883`**：PC 侧直连设备网段那个 broker IP **会超时**（宿主访问被拦，实测）；
   用 localhost / 进 WSL 跑 `mosquitto_sub` 才通。做任何上行验证（state/discovery/LWT）都按这个口径。
7. **`publish/subscribe` 返回 true 只代表"提交成功"**，不等于 broker 收到（QoS0 发完就忘）
   → 送达确认只能靠 retained + 状态回读对账（本组件的 1 s 差分兜底即是）。

补充（工程侧继电器语义，沿用真源时别踩）：`init()` 被多个页面各调一次 + `restore()` 用缺省掩码 0 回写
→ 每切一次页把灯写 OFF（真机「反复关灯」）；存档键**不存在**时不许回写硬件（哨兵区分「键不存在」与合法 `0`）。

---

## 4. Domoticz 兼容口径与缺口

Domoticz 的 `hardware/MQTTAutoDiscover.{h,cpp}` 实现的就是 **Home Assistant MQTT Discovery**，所以本组件发的
discovery **不用改风格**就能被 Domoticz 吃下：

- 建硬件用 JSON API，**`htype = 125`**（`HTYPE_MQTTAutoDiscovery`）；两个必踩的坑：
  ① 不能只给 `address/port` —— 校验要求 `mode1` 非空（TLS 版本），只给地址返回 `{"status":"ERR"}`；
  ② **discovery 前缀走 `extra` 字段**，格式 `<CA>;<..>;<..>;<prefix>` → 传 `extra=;;;homeassistant`。
- 订阅 `<前缀>/#`；component 白名单：`sensor` `binary_sensor` `switch` `light` `lock` `select` `cover` `climate`
  `button` `number` `device_automation` `fan` `text`；**长键名与缩写键都认**
  （`unit_of_measurement`/`unit_of_meas`、`brightness_value_template`/`bri_val_tpl`…）→ 本组件用缩写风格无需改。

**实测结果（108 + 71 两台面板 + 模拟传感器，一台 broker）**

| 项 | 结果 |
|---|---|
| 面板 108 | Domoticz 建出 **3 个 Light/Switch**（客厅灯 On / 卧室灯 On / 灯带 Off），状态与面板一致 |
| 面板 71 | 同样建出 3 个 Light/Switch |
| 反向控制 | Domoticz 点 `switchlight idx=3 On` → 面板发布的 `relay_3/state` 由 **OFF→ON**；点 Off → 回 OFF（面板真的执行） |
| 传感器接入 | 模拟网关发 `homeassistant/sensor/<uid>_{temp,hum}/config` → Domoticz 建出 Temp + Humidity 实体，数值随上报更新（25.2 °C / 48 %） |
| 可用性 | 面板 LWT 发 `availability`，Domoticz 侧按 `avty_t` 订阅（**未做断线场景专项验证**） |

**缺口（用之前要知道）**

- **情景**：面板拉情景清单、点情景发自定义主题，靠 HA 侧自动化执行 → **Domoticz 没有等价物**，要用 dzVents/Lua 自己接
  （本组件把情景留在工程侧：`extraSubscriptions` + `onMessage`）。
- **回传方向（网关 → 面板）**：HA 模式下真源面板**只订阅**自己的 command 主题（+ 情景主题），
  **没有任何天气/传感器回传**；屏保上的温湿度/天气是另一条 TCP 推送链路。要「网关 → 面板」属新能力，本组件不含。
- **未验**：TLS、用户名/口令鉴权、断线重连与实体不可用（availability）场景在 Domoticz 侧的专项验证。

---

## 5. 不同平台的依赖差异（移植时唯一要改的地方）

| 平台 | 依赖 | 说明 |
|---|---|---|
| Z20 | `mqtt-cxx` + `paho-mqtt3as` + `openssl 1.1.1-w` + `base-json` + `base-utility` + `log` | 唯一实测组合 |
| 其它 | — | registry 无 `mqtt-cxx`/`paho-mqtt3as` → **不支持**；要上新平台先让包站提供该包（本仓不做跨平台推断） |

---

## 6. 未验证项与所需条件

- **本组件的组件形态未单独上机**：代码/接口从真源工程摘除私有依赖重写，`example/` 已写好但**未在工程里编过**
  （Z20 上「能不能编」需要一次 `fun install && fun build -p Z20`；**未取证**）。
  **已做的一致性检查**：`g++ -fsyntax-only -std=c++11 -Wall -Wextra -D__PLATFORM_Z20__=1`
  对 `src/zk_ha_bridge.cpp` 与 `example/zk_ha_bridge_demo.cc` 都通过（0 error / 0 warning），
  头文件路径用 Z20 registry 真实包（mqtt-cxx 3.2.0 / paho-mqtt3as 1.3.13 / base-json 3.1.0 /
  base-utility 10.8.5 / easyui 3.0.0 / log 0.0.0 / rapidjson 1.1.0）——**只是语法/接口对得上，不等于真机跑通**。
  已验证的是**同源逻辑**：`SmartPanel_HA` 的 `MqttBridge` + `RelayManager` 组合在 Z20 真机跑通（HA + Domoticz 双向）。
- MQTT v5 属性、`wss`（WebSocket over TLS）：未测（示例只覆盖 `mqtt://` 与 `mqtts://`）。
- QoS2（EXACTLY_ONCE）：未测（实测都是 QoS1；本组件 state/command 用 QoS0 + retained）。
- 遗嘱代发可靠性：只做了 1 次（异常断线 → 约 2 s 代发）；未做多次重复与 retained will 回归。
- 长令牌/大量实体场景下的 discovery 报文体积：未测。

---

## 7. 真机验收步骤（Z20）

```bash
# ① 编译部署（工程侧）
fun install && fun build -p Z20
# 部署：/tmp 劫持法（不动 /res）——⚠️ 单次 restart；先确认没有残留 zkgui 进程
adb -s <设备IP>:5555 push .fun/z20/libzkgui.so /tmp/lib/libzkgui.so
adb -s <设备IP>:5555 push ui/main.ftu          /tmp/ui/main.ftu
adb -s <设备IP>:5555 push EasyUI.cfg           /tmp/EasyUI.cfg
adb -s <设备IP>:5555 shell setprop ctl.restart zkswe

# ② 见证端（PC/WSL；⚠️ 连 localhost:1883，直连设备网段那个 IP 会超时）
mosquitto_sub -h 127.0.0.1 -p 1883 -t '<prefix>/#' -t 'homeassistant/#' -v

# ③ 下行
mosquitto_pub -h 127.0.0.1 -p 1883 -t '<prefix>/switch/relay_1/command' -m OFF

# ④ 看设备日志（tag 按工程自己的日志 tag 改）
adb -s <设备IP>:5555 shell "logcat -d | grep -E 'ha_bridge|MqttBridge|Relay'"
```
