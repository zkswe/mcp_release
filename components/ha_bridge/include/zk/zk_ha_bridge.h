/*
 * zk_ha_bridge.h —— Home Assistant / MQTT 桥 + 继电器语义（可复用组件）
 *
 * 是什么：把「面板这类设备」按 **Home Assistant MQTT Discovery** 标准接进 HA / Domoticz，
 *   同时把「继电器（开关）语义」收进来：唯一事实源 + 变化通知 + 覆盖式 listener 的坑。
 *
 * 做什么（三条链路，全部 retained，连接成功后自动跑一遍）：
 *   上行：<prefix>/availability                    -> online / offline（LWT 遗嘱兜底）
 *         <prefix>/switch/relay_<n>/state         -> ON / OFF
 *         <prefix>/status                         -> 整机状态 JSON（由 statusJson 回调给）
 *   下行：<prefix>/switch/relay_<n>/command       <- ON / OFF（仅认这一个主题 + 恰好 ON/OFF）
 *   发现：homeassistant/switch/<uid>_relay_<n>/config（retained）
 *
 * 不是什么（刻意不做，见 README §1）：
 *   - 不是 MQTT 客户端实现：底层是 `mqtt-cxx`（`mqtt::Client`，paho 异步）；本头**不泄漏** mqtt-cxx 任何类型
 *   - 不管配置存储/HTTP 配网页/UI/情景引擎：调用方给配置结构体 + 回调（工程侧原来用 ConfigStore/WebConfigServer）
 *   - 不做「本地主机/从机」那套板内 broker 互联（那是同工程的另一条互斥链路，见 README §9）
 *
 * 出处（真源，本组件 = 摘掉工程私有依赖后的可复用版）：
 *   projects/SmartPanel_HA/src/network/MqttBridge.{h,cpp}（HA Discovery / 命令 / 状态 / retained 校准）
 *   projects/SmartPanel_HA/src/device/RelayManager.{h,cpp}（继电器唯一事实源 + listener 覆盖式事故）
 *   坑与实测数字：projects/SmartPanel_HA/docs/{DOMOTICZ-COMPAT.md,HA-CONFIG-WEB.md}、
 *                 tools/FlyThings_mcp_open/packages/mqtt-cxx/{platforms.md,package.yaml}
 *
 * ⚠️ 线程模型（业务必读）：
 *   - `Bridge::tick()` / `publishXxx()` / `relays().set()` 由**调用方线程**（通常是 UI 线程的 1s 定时器）调；
 *   - `onCommand` / `onMessage` / `onConnected` / `onDisconnected` 回调**在 mqtt-cxx 的库线程上跑**；
 *     回调里只置标志位/打日志，**别直接动 UI 控件**（Z20 面板实测会卡/崩）——跨线程动作放 `tick()` 里做；
 *   - 组件内部用一把 mutex 保护 client / 代次 / 连接标志，业务不需要理解 paho 的 run loop。
 */
#ifndef ZK_HA_BRIDGE_H
#define ZK_HA_BRIDGE_H

#include <functional>
#include <string>
#include <vector>

/* ---------------- 日志钩子 ----------------
 * app 模式下 stdout 是 /dev/null，库内日志必须能接出去（components/README.md §2.8）。
 * msg 只在本回调内有效，不要存指针；user 就是 setLogHook 传进来的那个。*/
enum zk_ha_log_level {
    ZK_HA_LOG_DEBUG = 0,
    ZK_HA_LOG_WARN  = 1,
    ZK_HA_LOG_ERROR = 2
};
typedef void (*zk_ha_log_fn)(int level, const char *msg, void *user);

namespace zk {
namespace ha {

/* ---------------- 统一结果类型（components/README.md §2.2）----------------
 * 禁止只回 -1：msg 必须是**人话**，能直接打日志/回给用户。*/
struct Result {
    int code;
    std::string msg;
    Result();
    Result(int c);
    Result(int c, const std::string &m);
    bool ok() const;
};

enum ResultCode {
    HA_OK                   = 0,
    HA_ERR_ARG              = 1,   /* 参数不合法（通道越界 / JSON 为空 …）*/
    HA_ERR_NOT_CONFIGURED   = 2,   /* 必填配置为空（server / prefix+deviceId）*/
    HA_ERR_NOT_CONNECTED    = 3,   /* 当前未连上 broker（消息没发出去，不是静默丢）*/
    HA_ERR_NOT_STARTED      = 4,
    HA_ERR_INTERNAL         = 5
};

typedef std::function<void(int ch, bool on)> RelayListener;
typedef std::function<void(int ch, bool on)> CommandHandler;

/* ---------------- 继电器（唯一事实源）----------------
 * 铁律（真源工程踩出来的）：状态只有一个地方说了算，任何一侧（触摸/情景/网络/HA）都走 set()，
 * 不得自己缓存/推算，也不得用可空指针兜底成 false。
 *
 * 通知分两类，**互不覆盖**：
 *   setUiListener(fn)     = UI 视觉**单槽**（覆盖式，最后一次生效）——UI 卡片刷新用；
 *   addListener(key, fn)  = 业务具名**多路**（同 key 覆盖 => 可重复调用、幂等）——上报/联动用。
 * 事故复盘：旧实现只有一个 setListener()，它 clear() 整个列表；某个页面 onUI_init 用它刷卡片，
 *   一进主页就把 Bridge 注册的状态上报回调抹掉 -> 继电器再变化也不回发，HA 侧"切过去一会儿又切回来"。
 *   本组件从接口上就消灭这个坑：UI 槽与业务槽分离。*/
class RelayBank {
public:
    explicit RelayBank(int channels = 3);

    int channels() const;

    bool get(int ch) const;              /* ch = 1..channels()，越界返 false（并已 warning）*/
    void set(int ch, bool on);           /* 状态**变化**才通知；相同值直接返回（不刷屏）*/
    void toggle(int ch);

    /* UI 视觉单槽（覆盖式）；传空 function 可清掉 */
    void setUiListener(const RelayListener &fn);

    /* 业务具名多路；同 key 覆盖（=> 幂等，每次重连都可放心再注册一遍）*/
    void addListener(const std::string &key, const RelayListener &fn);
    bool removeListener(const std::string &key);

    int listenerCount() const;           /* 排障可观测*/
    std::string listenerKeys() const;

    /* 用当前真实状态逐个通知（恢复/重载后对齐 retained 用）*/
    void notifyAll();

    /* 重设路数：清空状态与**全部** listener（UI 槽 + 业务具名槽）。
     * Bridge::start() 只在 Config::channels 与当前路数不一致时调它 —— 所以 listener
     * 请在 start() 之后再注册（正常路径不受影响）。*/
    void reset(int channels);

private:
    RelayBank(const RelayBank &);
    RelayBank &operator=(const RelayBank &);

    int mChannels;
    std::vector<bool> mState;
    RelayListener mUi;
    std::vector<std::pair<std::string, RelayListener> > mKeyed;
};

/* ---------------- 配置 ---------------- */
struct Config {
    /* 【默认值一律为空】组件内不写死任何地址/账号/口令/前缀/人名 */
    std::string server;        /* 必填：如 "mqtt://<broker>:1883"（TLS：mqtts://<broker>:8883）*/
    std::string username;      /* 可空 */
    std::string password;      /* 可空（HA 的长令牌也放这里；粘贴时请先去换行与空格）*/
    std::string prefix;        /* 必填：主题前缀，如 "smartpanel/<deviceId>"；空则由 deviceId 派生 */
    std::string deviceId;      /* 用于 prefix 派生与 HA unique_id / device 归组；prefix 已给时可留空 */
    std::string deviceName;    /* HA 里显示的设备名；空 -> 回落 deviceId（不写死字面量）*/
    std::string clientId;      /* MQTT client_id；空 -> 由 prefix 派生（'/'->'_'）*/

    /* HA Discovery（可选；空则不写该字段，HA 侧显示未知，不编造）*/
    std::string discoveryPrefix; /* 空 -> "homeassistant"（HA 标准发现前缀，协议常量）*/
    std::string manufacturer;    /* 对应 discovery 的 mf；空 = 不发 */
    std::string model;           /* 对应 discovery 的 mdl；空 = 不发 */

    std::vector<std::string> relayNames; /* 各通道名字；为空或某项为空 -> 该通道回落 "relay_<n>"*/
    /* 额外订阅（原始主题，支持 + / # 通配）；收到的消息交给 onMessage 回调。
     * 情景清单这类业务主题留在工程侧，本组件不预设任何主题字面量。*/
    std::vector<std::string> extraSubscriptions;

    int channels;              /* 继电器路数，默认 3 */
    bool lwtEnabled;           /* 是否注册 LWT 遗嘱（availability -> offline，retained），默认 true */
    bool publishStatusJson;    /* 连接后是否发一次 <prefix>/status，默认 true（需给 statusJson）*/

    int tickMs;                /* 调用方 tick 周期建议值（组件只用它做退避/兜底节流），默认 1000 */
    int reconnectMinMs;        /* 重连退避下限，默认 10000（10s）*/
    int reconnectMaxMs;        /* 重连退避上限，默认 60000（60s）*/

    /* 回调（都在 mqtt-cxx 库线程上跑 —— 别动 UI）*/
    CommandHandler onCommand;                    /* 收到 <prefix>/switch/relay_<n>/command = ON/OFF */
    std::function<void(const std::string &topic,
                       const std::string &payload)> onMessage;  /* 其它消息的扩展点（原始 topic/payload）*/
    std::function<void()> onConnected;
    std::function<void(const std::string &cause)> onDisconnected;

    /* 整机状态 JSON（组件不生成状态内容：由业务给）。空 -> 不发 <prefix>/status */
    std::function<std::string()> statusJson;

    Config();
};

/* ---------------- 桥 ---------------- */
class Bridge {
public:
    static Bridge &instance();     /* 单例（一个进程一份 MQTT 连接）*/

    /* 启动（非阻塞：内部起线程建连；结果看 connected()/回调）。
     * 配置不全（server 空 / prefix+deviceId 都空）-> 直接返回 ERR_NOT_CONFIGURED + 人话，不静默。*/
    Result start(const Config &cfg);
    /* 停止并**销毁 client**（代次 +1，旧回调作废）。模式切换 / 改完配置重连都调这个。*/
    void stop();
    /* 由调用方周期驱动（建议 1s，见 Config::tickMs）：
     *   未连上 -> 退避重连（本组件是**唯一的应用层重连真源**，见 README §4 坑 2）；
     *   已连上 -> 1s 差分兜底（比对真实继电器状态，补发漏报的 state/status）。*/
    Result tick();

    bool started() const;
    bool connected() const;

    RelayBank &relays();

    /* ── 上行（全部 retained=true 幂等，连上后自动发一遍；也可手动补发）── */
    Result publishState(int ch, bool on);        /* <prefix>/switch/relay_<n>/state */
    Result publishAllStates();                   /* 逐路发真实状态（覆盖 broker 上残留的旧 retained）*/
    Result publishStatus();                      /* <prefix>/status（内容来自 statusJson 回调）*/
    Result publishEvent(const std::string &json);/* <prefix>/event（**非** retained：事件不进历史状态）*/
    Result publishAvailability(bool online);
    Result publishDiscovery();                   /* homeassistant/switch/<uid>_relay_<n>/config */
    /* retained 撤销：往 homeassistant/<component>/<objectId>/config 发**空 payload + retained**
     * （旧版本发过的实体，不撤销会一直在 HA 里阴魂不散）。*/
    Result clearDiscovery(const std::string &component, const std::string &objectId);

    /* ── 诊断（验收/排错）── */
    std::string prefix() const;      /* 实际生效的主题前缀 */
    std::string uniqueId() const;    /* HA unique_id 基（prefix 的 '/' -> '_'）*/
    int reconnects() const;          /* 累计建连次数 */
    int generation() const;          /* client 代次（每次重建 +1）*/
    const char *lastError() const;   /* 最后一条错误（人话）；无错误返 ""（不返 NULL）*/

    void setLogHook(zk_ha_log_fn fn, void *user);

private:
    Bridge();
    ~Bridge();
    Bridge(const Bridge &);
    Bridge &operator=(const Bridge &);

    struct Impl;
    Impl *mImpl;
};

} /* namespace ha */
} /* namespace zk */

#endif /* ZK_HA_BRIDGE_H */
