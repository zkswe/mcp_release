---
id: devflow-mqtt-client-lifecycle
title: MQTT 客户端连接生命周期（重连真源 / 互踢 / retained 回放 / availability）
category: devflow
status: review
confidence: manual
verified_at: 2026-10-01
stale_days: 180
origin: partial
source: 2026-10-01 真机工程复盘（projects/SmartPanel_HA v7.3 MQTT 接入）+ packages/mqtt-cxx 真机实测记录
needs_evidence: true
platforms: [Z20]
tags: [HA 实体反复掉线, MQTT 一直重连, client_id 互踢, 重连后灯全灭, retained 回放当命令, 实体总是不可用, 回调线程别动 UI, 重连谁负责, 先报在线再报实体, 板内 broker 能力边界]
evidence:
  - "projects/SmartPanel_HA/src/network/MqttBridge.cpp L118-126（dropClientLocked：mClientGen++ 后 delete 旧 client）"
  - "MqttBridge.cpp L132（stop 也回收）、L164-197（tick 是唯一应用层建连入口；退避 10→20→40→封顶 60s）"
  - "MqttBridge.cpp L199-249（connect()：先 dropClientLocked → gen=++mClientGen → 新 client；WillOpts 见 L214-218）"
  - "MqttBridge.cpp L226-236（on_connected 回调：锁内只翻标志，onConnected()/日志在锁外）、L237-245（on_disconnected，日志在锁内 243）"
  - "MqttBridge.cpp L270-273（具名 addListener(\"mqtt_bridge\")，幂等重注册）、L280-285（上行顺序 availability→discovery→subscribe→state→status）"
  - "MqttBridge.cpp L345-365（retained 回放防护：只认 <prefix>/switch/relay_<n>/command 且 payload 恰为 ON/OFF，其余 LOGW 忽略）"
  - "MqttBridge.cpp L478-480（avty_t/pl_avail/pl_not_avail）、L489-501（空 retained 清旧 sensor/button 实体）、L523（改设备名后 republishDiscovery）"
  - "projects/SmartPanel_HA/src/network/LocalLink.cpp L168-178（板内链路同款严格解析：ON/OFF/1/0/on/off 之外一律忽略）"
  - "projects/SmartPanel_HA/src/network/LocalLink.cpp L310-372（masterTick 每 2s 重连；L350-353 先建新再 delete 旧，但**无代次**）"
  - "projects/SmartPanel_HA/src/network/MiniBroker.cpp L111（listen backlog=16）、L159-177（订阅即回放匹配的 retained）、L213-216（空 payload = 删 retained）"
  - "MiniBroker.cpp L275（CONNECT flags 直接跳过 = 免认证）、L276（keepalive 读了不判超时）、L163/L198/L309-310（一律 QoS0）、全文无 will/LWT 解析"
  - "projects/SmartPanel_HA/src/network/LocalBrokerService.cpp L25-29（zkmqtt 候选路径）、L55-101（拉不起 → 返回 false 由调用方回退 MiniBroker）"
  - "projects/SmartPanel_HA/src/logic/mainLogic.cc L872（1s 心跳调 MqttBridge.tick）、src/network/WebConfigServer.cpp L383-387（改配置后 stop+init）"
  - "projects/SmartPanel_HA/src/network/MqttBridge.h L95-108（mClient/mClientGen/mLastTryMono/mFailStreak/mReconnectCount）"
  - "~/.fun/registry/public/z20/mqtt-cxx/3.2.0/include/mqtt/mqtt_client.h L63-69（on_connected/on_disconnected 带 cause）、L72-86（publish/subscribe/isConnected）；Configuration 里**没有**关闭库自动重连的开关"
  - "tools/FlyThings_mcp_open/packages/mqtt-cxx/platforms.md（Z20 实测：断网 90s → on_disconnected；复网再次 on_connected，cause=automatic reconnect，回连约 10.5s；同 client_id 互踢风暴实测 每分钟 143 connected / 123 disconnected，两条 disconnected 相隔 2 ms）"
  - "tools/FlyThings_mcp_open/packages/mqtt-cxx/package.yaml L84-88,117（gotchas：不 delete 旧 client 会被 broker 互踢；回调在库线程；evaluate 返回 true 不等于 broker 收到）"
  - "tools/FlyThings_mcp_open/packages/mqtt-cxx/evidence/netstack2_20260929.txt、evidence/lwt_will_20260929.txt（真机日志；遗愿 kill -9 后代发约 2 s）"
---

# MQTT 客户端连接生命周期（重连真源 / 互踢 / retained 回放 / availability）

> 检索导引：HA 实体反复掉线 / MQTT 一直重连 / 连上了又掉 / 同一个 client_id 互踢 /
> 重连后灯全灭 / 一重连就关灯 / retained 回放被当命令执行 / 空 payload 被当 OFF /
> 实体永远 unavailable 但日志说已连接 / on_connected 回调里能不能动 UI / 回调线程 /
> 重连要不要自己 new client / 库自带自动重连还要不要看门狗 / 断网恢复要多久 /
> 先发 availability 还是先发 discovery / 升级后 HA 里残留旧实体清不掉 /
> 板内 broker 回退（MiniBroker）能干什么。

## 0. 一句话

「连上」只是生命周期的开始。MQTT 客户端的坑几乎全在**连接状态与消息语义的边界**上：
**重连只有一个真源**、**建连前必须回收旧 client**、**回调线程不碰 UI**、
**retained 回放 ≠ 命令**、**availability 必须先于 discovery**、**LWT 主题逐字对齐**。
这六条错了，现象长成「HA 实体反复掉线 / 重连后灯全灭 / 实体永远不可用」这种
**完全看不出跟 MQTT 有关**的样子，最后全被误判成 UI 或继电器问题。

本文口径来自真机工程 `projects/SmartPanel_HA`（Z20 面板）v7.3，配套包级实测见
`packages/mqtt-cxx/platforms.md`。**每条都给「现象 → 根因 → 做法 → 怎么一眼发现」+ 行号**。

---

## 1. 单一重连真源：库的自动重连 与 应用层看门狗 只能留一条主路

**现象**：HA 里实体反复掉线/恢复；broker 日志里**每秒 2~3 次**connect/disconnect；
实体状态在 `unavailable`/`online` 之间高频抖动，设备本地日志看起来却"一直在连"。

**根因**：`mqtt-cxx` 底层是 paho **异步 API**，**库自带 automatic reconnect**——
网络恢复后它自己会把同一个 client 重新连上，并以 `on_connected(cause)` 回调，
`cause = "automatic reconnect"`（`platforms.md` Z20 实测，回连约 **10.5s**；
`mqtt_client.h:63-69` 的 handler 签名就是 `void(const std::string& cause)`）。
如果应用层再看门狗里 `!connected 就 connect()` 并且**每次 `new` 一个 client**，
就出现**两个 client 用同一个 `client_id`**，broker 按协议**互相踢下线**→
自激风暴（真机实测：1 分钟 **143 次 connected / 123 次 disconnected**，
两条 disconnected 只隔 **2 ms**）。

**做法**：
1. 应用层**只保留一个建连入口**。本工程把唯一入口定在 `tick()`（`MqttBridge.cpp:164`），
由主页 1s 心跳驱动（`mainLogic.cc:872`）；`init()`（`:148-159`）与改配置后的
   `stop()+init()`（`WebConfigServer.cpp:383-387`）是同一入口的显式重启，不另开新路径。
2. `tick()` 里加**节流 + 指数退避**：`!connected && !connecting` 才试；
退避 10s → 20s → 40s → **封顶 60s**（`MqttBridge.cpp:177-191`，
   `mLastTryMono`/`mFailStreak` 见 `MqttBridge.h:106-107`）。
退避窗口内直接 return，**绝不每秒起线程**。
3. 若要保留库的自动重连（本项目就是保留的），应用层**不能再自己 new 第三份 client**；
库重连用的还是原来那个 client 实例，不会新增 `client_id` 副本——
真正致命的是应用层 `new` 出来又不 `delete` 的那些（见 §2）。

**怎么一眼发现**：
- 串口/broker 侧日志出现 **connect/disconnect 频率 ≈ 秒级**，且两条 disconnected 间隔 ~ms 级 → 互踢。
- 应用日志里一个退避窗口内出现 **多条**`MqttBridge: connecting ...`（应只有一条）→ 有第二个真源。
- `platforms.md` 的实测表：断网 90s → 一条 `on_disconnected`；复网 → **一条**`on_connected`
  （cause=automatic reconnect）。**数量对不上就是有两个源。**

---

## 2. 建连前回收旧 client + 代次（gen）作废旧回调

**现象**：内存/句柄缓慢增长；`disconnected`/`connected` 日志**成对但错位**（旧 client 的迟到回调
把新 client 刚置上的 `mConnected` 又抹回 false）；HA 实体"刚上线又掉"。

**根因**：`mqtt::Client` **构造即连接、析构即断开**（包级 fact）。
`connect()` 里 `new` 新 client 却**不 `delete` 旧的**：旧 client 既泄漏，又继续在自己线程上回调——它的 `on_disconnected` 会把
**新连接的状态**改掉（标志位共享），形成"看起来连上了其实是幽灵在报断线"。

**做法**（`MqttBridge.cpp:117-126` / `:224-247`）：
1. 建新 client **之前**先 `dropClientLocked()`：`mClient=nullptr; mClientGen++; delete old;`
   （`delete` 会断开旧 paho 连接）。
2. 每代回调**捕获自己的 gen**；回调内第一件事 `if (gen != mClientGen) return;`
   —— 旧 client 的迟到回调一律丢弃（`on_connected` :226-233、`on_disconnected` :237-242）。
3. `stop()` 也走同一个 `dropClientLocked()`（`:128-134`），不另写一套清理。
4. 状态字段全部由 `mMtx` 保护（`MqttBridge.h:104-108`）。

**怎么一眼发现**：
- 日志里 `old client dropped (gen=N)` 的 **N 单调递增**，且紧跟着的
  `connecting ... (gen=N+1)` 与它同代 → 回收+代次都对上了。
- 出现 **`(gen=` 值比当前小的日志行**→ 有旧回调没被拦住。
- `mReconnectCount`（累计重连数，`MqttBridge.h:108`）在**稳定网络下应长期不涨**；
持续上涨 = 有东西在反复踢。

---

## 3. 回调线程纪律：回调跑在库线程上，别在里面动 UI

**现象**：消息一来面板就卡一下／偶发卡死、触摸迟滞；或者"命令到了但界面没刷新"。

**根因**：`on_connected`/`on_disconnected`/`subscribe` 的 `MessageHandler`
**都在库自己的线程上执行**（`platforms.md` 实测口径：Z20 面板在回调里直接操作控件会卡）。
UI 控件（`ZKButton` 等）不是线程安全的，跨线程直接 `setText/setBackground` 会崩或卡。

**做法**：
1. 回调里**只做**：翻标志位、拷状态、打日志。**不**调 UI API。
2. **锁内只翻标志，锁外干重活**：`on_connected` 里锁内改
   `mConnected/mConnecting/mFailStreak`，随后在**锁外**`LOGD` 并调
   `onConnected()`（:234-235）——因为 `onConnected()` 自己会 `publish/subscribe`，
带锁做 I/O 会阻塞 tick 和其他回调。
3. 业务回调也用「置脏 + 主线程刷新」的形态，别在库线程里刷控件。

**怎么一眼发现**：
- 代码审查判据：回调 lambda 体内**没有**`EASYUICONTEXT`/控件方法调用；
有 `publish/subscribe/LOGD` 时**不在 `lock_guard` 作用域内**。
- ⚠️ **本工程的已知残留**：`onMessage`（:318-376）里 `RelayManager::set()`
会**同步**触发 UI 视觉回调（`homeLogic.cc:416-419` 的 `setListener` → `applyCardVisual`），
这条路径实际上仍在库线程上碰控件。**本轮只读代码、未跑真机复现卡顿，属未取证风险点**，
迁移到新工程时建议改成置脏 + 心跳刷新。

---

## 4. retained 回放会被当成命令：只认「精确 topic + 精确 payload」

**现象**：**一重连灯全灭**（或状态被莫名改回旧值）；"重新注册 HA 服务/断网重连后灯光自己变了"；
空 payload 一到，三路继电器全被写成 OFF。

**根因**：broker 在**每次（重）订阅成功后**会立刻把该主题上已有的 **retained**消息**回放**一份
（本机 MiniBroker 同样行为：`MiniBroker.cpp:159-177` 在 `addSub` 时补发匹配的 retained）。
retained 里可能存着**上一次的 state/status**，甚至是**空 payload 的"清除包"**。
旧代码的写法是"不是 ON 就当 OFF"（或 `payload.empty()` 落到 else 分支），
于是**每一次重连都等于执行一次关灯命令**。

**做法**（`MqttBridge.cpp:345-365`）：
1. topic 必须**精确等于**`<prefix>/switch/relay_<n>/command`：
   `rest.size() == 1 + 5 && rest.compare(1, 5, "/command") == 0`（:351-353），
别的后缀（`/state`、`/command2`、子主题）直接 `return`。
2. payload 必须**恰为**`ON` 或 `OFF`（:356-359）；其余**含空 payload**→
   `LOGW("ignore non ON/OFF command ...")` 后丢弃（:360-361）。
3. 通道号还要范围校验（:354-355）。
4. 同款纪律在板内链路：`LocalLink.cpp:168-178`（白名单 `ON/OFF/1/0/on/off`，其余忽略）。
5. 反向的"清除"也要走 retained：**往同 topic 发空 payload + retained=true**才是撤销
   （`MQTT` 语义；本机 MiniBroker 的对应实现 `MiniBroker.cpp:213-216`）。

**怎么一眼发现**：
- 日志里出现 `recv <prefix>/switch/relay_N/state = OFF` 这类**我们自己发的 state**
被当成命令——说明收口没做在 topic 上（state 是 retained，回放必然出现）。
- 出现 `ignore non ON/OFF command (… = [])` → 防护生效（这是**好事**，不是报错）。
- 自测判据：**拔网线/重启 broker 再恢复，灯光状态必须不变**（2026-09-30 口径）。

---

## 5. 上行顺序：先 availability(online)，再 discovery；升级要发空 retained 清残留

**现象**：设备明明连着，HA 里实体却是 `unavailable`；或"升级完 HA 里多出几个旧实体清不掉"。

**根因**：HA 把 discovery 配置和 availability 联合判断——**设备先声明 offline / 或从未声明 online 时
收到的 discovery，会被 HA 标成不可用**。另外 `homeassistant/.../config` 是 **retained**：降级/改版后**旧主题仍在 broker 上**，HA 会一直恢复出已经不存在的实体。

**做法**（`MqttBridge.cpp:266-286`，顺序固定）：
1. `publishAvailability(true)` —— 先"我在线"（:280）。
2. `publishDiscovery()` —— 再发 `homeassistant/switch/<uid>/config`（:281；函数 :447-503，实体定义 :466-485）。
3. `subscribeAll()` —— 再订阅下行命令（:282）。
4. `publishAllRelayStates()` + `publishStatus(...)` —— 最后主动推一遍**新鲜**状态，
覆盖 broker 上可能残留的旧 retained（:283-285）。
5. 版本升级/功能下线时，对**旧主题发空 payload + retained**：
   `homeassistant/sensor/<uid>_temperature|_humidity/config`（:489-492）、
   `homeassistant/button/<uid>_scene_1..8/config`（:497-501）→ HA 自动删除残留实体。
6. 设备名等元数据变了，主动 `republishDiscovery()`（:518-526），HA 侧立刻改名。

**怎么一眼发现**：
- 抓包/日志顺序里 discovery 出现在 availability **之前**→ 抓到这个就能定性。
- HA 侧"实体不可用但设备日志已连接" → 先查 availability 主题是否被真的发出（见 §6）。
- 升级后残留实体：判据 = 有没有对旧 `.../config` 发过空 retained。

---

## 6. LWT / availability 主题必须逐字一致

**现象**：实体**永远**`unavailable`，设备日志却是 `connected`；或掉线后 HA 不显示离线。

**根因**：三个地方各写一份主题/载荷，**只要有一处拼错、多了空格、prefix 不齐**，
HA 就永远等不到匹配的 availability：
- 注册遗愿：`conf.will.topic = prefix() + "/availability"`、`will.message="offline"`、
  `will.retained=true`（`MqttBridge.cpp:214-218`）
- 实体定义：`avty_t = prefix()+"/availability"`、`pl_avail="online"`、`pl_not_avail="offline"`（:478-480）
- 实际上报：`publishAvailability()` 往同一主题发 `online`/`offline`（:378-383）

**做法**：把**主题与载荷都收敛到同一处常量/同一函数**（本项目全部走 `prefix()` + 同一份
`"online"/"offline"` 字面量），禁止在业务代码里另拼字符串。LWT 保证**异常断电/进程被杀**时
broker 代发 `offline`（真机实测 `kill -9` 后约 **2 s**代发，`evidence/lwt_will_20260929.txt`）。

**怎么一眼发现**：
- 拿注册遗愿的 topic 字符串 与 discovery 的 `avty_t` 字符串**做逐字比对**（含大小写、斜杠数）。
- `pl_avail/pl_not_avail` 与实际上报的 payload 必须逐字相同（`online` vs `ON` 这种就是错的）。
- 面板侧自检：HA 里手动断开设备电源，实体应在数秒内变 `unavailable`；不变 → LWT 主题没对上。

---

## 7. 板内 broker 回退时的能力边界（MiniBroker）

**现象**：MASTER 模式下"用板内 broker 也能跑"的表象下，availability 不可靠、
QoS1 订阅实际降成 QoS0、遗嘱机制完全缺失。

**根因**：自研 `MiniBroker` 只是**最小可用子集**，与标准 broker 差距是能力级的：
- **一律 QoS0**：分发头写死 `0x30`（`MiniBroker.cpp:163,198`），SUBACK 授予 QoS0（:309-310）
  → `publish/subscribe` 返回 true **只代表提交成功**，不代表 broker 收到，无重传。
- **无 LWT/will**：CONNECT 解析直接跳过 flags、keepalive 读了不判超时
  （`MiniBroker.cpp:275-276`）→ **没有遗愿代发，也没有 keepalive 超时摘除**。
- **无鉴权**：username/password 被跳过（:275）。
- **backlog = 16**：`listen(fd, 16)`（:111）。
- **通配只支持 `#` 与 `+` 两级**（`topicMatch` :83-98：`#` 只当末级匹配全部）。
- 板内服务优选"外部进程"：`LocalBrokerService` 依次找 `/mnt/sdnand/hub/bin/zkmqtt`、
  `/res/bin/zkmqtt`、`/tmp/zkmqtt`（:25-29）并 `fork/exec`；**起不来才由调用方回退 MiniBroker**（:97-101）。

**做法**：回退到板内 broker 时**必须显式声明降级**（日志 + 文档 + 产品口径）：不承诺 availability、不承诺 QoS1 投递、不做遗愿；需要可靠性的场景（HA 接入）**走外接 broker**。

**怎么一眼发现**：
- 看到 `MiniBroker: listening on :1883` 而**没有**`LocalBrokerService: ... started` → 已降级。
- 判断"是否可靠"的一条硬判据：**有没有 LWT**。无 will 解析的 broker，`unavailable` 语义不存在。
- 通配写法里出现 `#` 不在末级、或 `+/+` 之外的三级组合 → 本 broker 不匹配。

---

## 8. 验证边界（真机已验 vs 未取证）

**已在真机验证（Z20，有日志/实测记录）**
- 库自带自动重连：断网 90s → `on_disconnected`；复网 `on_connected`，`cause=automatic reconnect`，回连 ≈ **10.5s**
  （`packages/mqtt-cxx/platforms.md`，证据 `evidence/netstack2_20260929.txt`）。
- **同 `client_id` 互踢风暴**：1 分钟 **143 connected / 123 disconnected**，两条 disconnected 相隔 **2 ms**（2026-09-28 真机实测）。
- **LWT 遗愿代发**：`kill -9` 后约 **2 s**broker 代发（`evidence/lwt_will_20260929.txt`）。
- **回调在库线程上跑、回调里动 UI 会让 Z20 面板卡**（`platforms.md` 实测口径）。
- "不 delete 旧 client 就被 broker 互踢"（`package.yaml:84`）。

**只有代码口径 / 未单独取证（本轮只做只读代码分析）**
- §2 的「gen 作废旧回调」：代码已落地（v7.3，2026-09-30 快照），但**未单独取证**"旧回调确实被丢弃"的逐条日志。
- §1 修复后"风暴消失"：**未做修复前/后的对照复现实验**（修复前风暴有实测，修复后只读代码）。
- §4「一重连就关灯」：代码已按2026-09-30 口径收口（:347-350 注释），
  **未找到真机复现记录**；同款防护见 `LocalLink.cpp:169-170`、`MiniBroker.cpp:213-216`。
- §3 残留：`onMessage → RelayManager::set → applyCardVisual` 仍在库线程（`homeLogic.cc:416-419`），**未复现卡顿**。
- §7 板内 MiniBroker 降级态：**代码能力边界**（读源码得出），**未跑真机**验证 availability 不可靠。
- §2 同类残留：`LocalLink::masterTick` 建连顺序为"先 new 再 delete 旧"（`LocalLink.cpp:350-353`）且**无代次**，
理论上有旧回调污染新状态的风险；**未取证**，迁移时应统一到 `dropClientLocked + gen` 模式。

---

## 9. 一眼发现速查表

| 你在现场看到 | 大概率是 | 先看哪一行 |
|---|---|---|
| 实体反复掉线、broker 日志秒级 connect/disconnect | 双 client 同 `client_id` 互踢 | `MqttBridge.cpp:224-247`（回收+gen）、`:177-191`（退避） |
| 一个退避窗口里多条 `connecting ...` | 不止一个建连真源 | `MqttBridge.cpp:164`（唯一入口 tick） |
| `gen=` 比当前小的日志行 | 旧回调没拦住 | `MqttBridge.cpp:229,239` |
| 一重连灯全灭 / 空 payload 被当 OFF | retained 回放当命令 | `MqttBridge.cpp:351-361`、`LocalLink.cpp:168-178` |
| 实体永远 unavailable 但日志已连接 | `avty_t`/`pl_avail` 与 will 主题不一致 | `MqttBridge.cpp:214-218` vs `:478-480` |
| discovery 先于 availability 出现 | 上行顺序倒置 | `MqttBridge.cpp:280-285` |
| 升级后 HA 多出旧实体 | 没对旧 `.../config` 发空 retained | `MqttBridge.cpp:489-501` |
| 消息一到面板卡一下 | 回调线程碰 UI | `MqttBridge.cpp:226-235`（正确形态）；残留 `homeLogic.cc:416-419` |
| 只有 `MiniBroker: listening` 没有 `LocalBrokerService: started` | 板内 broker 降级态 | `MiniBroker.cpp:111,275`、`LocalBrokerService.cpp:55-101` |

## 10. 相关文档

- 包级实测与 gotchas：`packages/mqtt-cxx/platforms.md`、`packages/mqtt-cxx/package.yaml`、
  `packages/mqtt-cxx/README.md`（README 已指向本文）
- 依赖包文档怎么读：`knowledge/devflow/dependency-package-docs.md`
- 设备侧部署/自检：`knowledge/devflow/deploy-consistency-check.md`
- 能力边界总表：`knowledge/devflow/capability-boundaries.md`
