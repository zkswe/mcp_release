# ha_bridge/example —— 最小可跑示例

## 文件

| 文件 | 是什么 |
|---|---|
| `zk_ha_bridge_demo.cc` | FlyThings 逻辑文件（拷进工程 `src/logic/`）：连 broker → 自动发 discovery/state/status → 收命令打印并翻灯；含 `onUI_Timer` 1s 调 `tick()` 的接线 |

> 说明：示例**不是**独立可编的 PC 程序 —— 它依赖 `mqtt-cxx`（Z20 专属包）+ FlyThings 的 `log` 包，
> 所以它跟 `components/vinyl/example/` 一样，形态是「拷进工程里编」。真源工程里跑通的形态见
> `projects/SmartPanel_HA/src/network/MqttBridge.cpp` + `src/logic/mainLogic.cc`。

## 三步接线（10 分钟）

```cpp
/* ① 拷代码：components/ha_bridge/{include,src} -> 工程的 src/zk/（或任何能被编到的目录）*/
/* ② Manifest 声明依赖（见 ../Manifest.xml；Z20 上 paho-mqtt3as / openssl 一个都不能漏）*/
/* ③ 页面钩子：*/

#include "zk/zk_ha_bridge.h"

static void onUI_init() {
    zk::ha::Config cfg;
    cfg.server   = "mqtt://<broker>:1883";   /* 工程侧从配网页/prefs 取，组件不写死 */
    cfg.prefix   = "panel/<设备ID>";
    cfg.deviceId = "<设备ID>";
    cfg.relayNames.push_back("客厅灯");
    cfg.onCommand = [](int ch, bool on) { LOGD("cmd relay_%d=%d", ch, on); };  /* 库线程：别动 UI */
    cfg.statusJson = []() { return std::string("{\"relays\":[0,0,0]}"); };
    zk::ha::Bridge::instance().start(cfg);
}

static bool onUI_Timer(int id) {          /* id 对应 1000ms 定时器 */
    if (id == 0) zk::ha::Bridge::instance().tick();   /* 重连 + 差分兜底，必须周期调 */
    return true;
}

static void onUI_quit() { zk::ha::Bridge::instance().stop(); }
```

## 怎么确认它真的通了（不需要 HA）

在 PC 侧起一个见证端订阅（⚠️ **要连 `127.0.0.1:1883` / 进 WSL 跑，直连设备网段那个 IP 会超时** ——
这是 Z20 实测过的口径，见 `packages/mqtt-cxx/platforms.md`）：

```bash
# 见证端（本机/WSL；把 <broker> 换成本地 broker 的地址）
mosquitto_sub -h 127.0.0.1 -p 1883 -t 'panel/#' -v
```

设备起来后，见证端应依次看到：

```
panel/<设备ID>/availability                     online          <- 先宣告在线
homeassistant/switch/<uid>_relay_1/config       {"name":"客厅灯",...}   <- HA Discovery
panel/<设备ID>/switch/relay_1/state             ON              <- 新鲜状态（覆盖旧 retained）
panel/<设备ID>/status                           {"relays":[...]}
```

反向控制（等价于 HA/Domoticz 点开关）：

```bash
mosquitto_pub -h 127.0.0.1 -p 1883 -t 'panel/<设备ID>/switch/relay_1/command' -m OFF
# 设备侧应打印 command relay_1 = OFF，并回发 .../relay_1/state = OFF
```

**别拿这个试**：`-t 'panel/<设备ID>/switch/relay_1/state' -m ON` —— 状态主题不是命令主题，
组件只认 `.../relay_<n>/command` 且 payload 恰为 `ON`/`OFF`（其余一律忽略，见 README §4 坑 4）。

## 常见现场问题

| 症状 | 查什么 |
|---|---|
| 一直没连上 | `start()` 的 `Result.msg`；`lastError()`；broker 地址有没有带 `mqtt://`；Z20 上 Manifest 是否漏了 `paho-mqtt3as`/`openssl` |
| HA 里实体反复掉线 | 是不是别处又 `new` 了一个同 `client_id` 的 client（重连只能有一个真源，见 README §4 坑 2） |
| 每次重连灯就关一次 | 命令解析没做「只认 `<n>/command` + 恰好 ON/OFF」过滤（坑 4） |
| 命令能到但状态不回 | 继电器 listener 被**覆盖式**注册抹掉了（用 `addListener("key", ...)`，别用覆盖式的） |
| 改了设备名 HA 不更新 | 改名后要重发 discovery（`start()` 重连，或 `publishDiscovery()`） |
