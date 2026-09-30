/*
 * zk_ha_bridge.cpp —— Home Assistant / MQTT 桥 + 继电器语义（实现）
 *
 * 真源：projects/SmartPanel_HA/src/network/MqttBridge.cpp（Z20 真机在跑）
 *       projects/SmartPanel_HA/src/device/RelayManager.cpp（唯一事实源 + listener 覆盖式事故）
 * 摘掉的工程私有依赖：ConfigStore（配置）/ WebConfigServer（配网页）/ SceneManager（情景）/
 *       PanelLink（整机状态 JSON）-> 全部换成 Config 结构体 + 回调注入。
 *
 * 保留的关键口径（一条都不许省，全是真机踩出来的）：
 *   ① 重连**只有一个真源**：本文件的应用层 tick + 退避；并且**每次建连前先回收旧 client + 代次(gen)作废旧回调**
 *      —— 否则旧实现（每次 new 却不 delete）会让两个 client 用同一 client_id 在 broker 上互踢，
 *      实测 1 分钟 143 次 connected / 123 次 disconnected（packages/mqtt-cxx/package.yaml）。
 *   ② 命令只认「<n>/command 且 payload 恰为 ON/OFF」：broker 在每次（重）订阅后会**回放 retained**，
 *      把回放/空 payload 当命令执行 = 重连一次关一次灯。
 *   ③ 状态**永远**读 RelayBank（唯一事实源），外加 1s 差分兜底（listener 被抹/漏报都能补齐）。
 *   ④ publish/subscribe 返回 true 只代表"提交成功"，不等于 broker 收到 -> 靠 retained + 状态回读对账。
 *   ⑤ 回调在 mqtt-cxx 的库线程上跑：回调里只置标志/打日志，别直接动 UI 控件。
 *   ⑥ retained 是持久状态：清不掉的实体用「同 topic 发空 payload + retained」撤销（clearDiscovery）。
 */
#include "zk/zk_ha_bridge.h"

#include <mqtt/mqtt_client.h>
#include <base/json_object.h>

/* 日志兜底：钩子优先（见 setLogHook）；没装钩子时——
 *   工程里有 easyui（提供 utils/Log.h，即 LOGD/LOGW/LOGE）就用它；否则退到 stderr。
 *   ⚠️ app 模式下 stdout/stderr 是 /dev/null：**上线必须装日志钩子**。*/
#if defined(__has_include)
#  if __has_include("utils/Log.h")
#    include "utils/Log.h"
#    define ZK_HA_HAVE_UTILS_LOG 1
#  endif
#endif

#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include <mutex>
#include <thread>
#include <utility>

namespace {

/* ---------------- 日志：钩子优先，没钩子退回 log 包（app 模式 stdout 是 /dev/null）---------------- */
zk_ha_log_fn gLogFn = NULL;
void *gLogUser = NULL;
std::mutex gLogMtx;

void logImpl(int level, const char *fmt, ...) {
    char buf[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);

    zk_ha_log_fn fn = NULL;
    void *user = NULL;
    {
        std::lock_guard<std::mutex> lk(gLogMtx);
        fn = gLogFn;
        user = gLogUser;
    }
    if (fn != NULL) {
        fn(level, buf, user);
        return;
    }
#ifdef ZK_HA_HAVE_UTILS_LOG
    if (level >= ZK_HA_LOG_ERROR) {
        LOGE("%s", buf);
    } else if (level == ZK_HA_LOG_WARN) {
        LOGW("%s", buf);
    } else {
        LOGD("%s", buf);
    }
#else
    fprintf(stderr, "[ha_bridge] %s\n", buf);
#endif
}

/* prefix -> HA unique_id 基（'/' -> '_'），纯函数（不碰锁）*/
std::string uidOf(const std::string &prefix) {
    std::string u = prefix;
    for (size_t i = 0; i < u.size(); ++i) {
        if (u[i] == '/') u[i] = '_';
    }
    return u;
}

long long monoNowMs() {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) == 0) {
        return (long long) ts.tv_sec * 1000LL + (long long) (ts.tv_nsec / 1000000L);
    }
    return (long long) time(NULL) * 1000LL;
}

} /* namespace */

namespace zk {
namespace ha {

/* =========================== Result =========================== */

Result::Result() : code(HA_OK) {}
Result::Result(int c) : code(c) {}
Result::Result(int c, const std::string &m) : code(c), msg(m) {}
bool Result::ok() const { return code == HA_OK; }

/* =========================== RelayBank =========================== */

RelayBank::RelayBank(int channels) : mChannels(3) {
    reset(channels);
}

void RelayBank::reset(int channels) {
    if (channels < 1) channels = 1;
    if (channels > 8) channels = 8;
    mChannels = channels;
    mState.assign((size_t) channels, false);
    mUi = RelayListener();
    mKeyed.clear();
    logImpl(ZK_HA_LOG_DEBUG, "RelayBank: reset channels=%d (listeners cleared)", mChannels);
}

int RelayBank::channels() const { return mChannels; }

bool RelayBank::get(int ch) const {
    if (ch < 1 || ch > mChannels) {
        logImpl(ZK_HA_LOG_WARN, "RelayBank::get: channel %d out of range 1..%d", ch, mChannels);
        return false;
    }
    return mState[(size_t) (ch - 1)];
}

void RelayBank::set(int ch, bool on) {
    if (ch < 1 || ch > mChannels) {
        logImpl(ZK_HA_LOG_WARN, "RelayBank::set: channel %d out of range 1..%d (ignored)", ch, mChannels);
        return;
    }
    if (mState[(size_t) (ch - 1)] == on) return;   /* 没变就不通知（避免刷屏/风暴）*/
    mState[(size_t) (ch - 1)] = on;
    logImpl(ZK_HA_LOG_DEBUG, "RelayBank: relay %d -> %s", ch, on ? "ON" : "OFF");

    /* 先拷一份再回调：回调里若增删 listener 也不会让迭代失效 */
    RelayListener ui = mUi;
    std::vector<RelayListener> keyed;
    keyed.reserve(mKeyed.size());
    for (size_t i = 0; i < mKeyed.size(); ++i) keyed.push_back(mKeyed[i].second);

    if (ui) ui(ch, on);
    for (size_t i = 0; i < keyed.size(); ++i) {
        if (keyed[i]) keyed[i](ch, on);
    }
}

void RelayBank::toggle(int ch) {
    if (ch < 1 || ch > mChannels) return;
    set(ch, !mState[(size_t) (ch - 1)]);
}

void RelayBank::setUiListener(const RelayListener &fn) {
    mUi = fn;
    logImpl(ZK_HA_LOG_DEBUG, "RelayBank: ui listener set (total=%d)", listenerCount());
}

void RelayBank::addListener(const std::string &key, const RelayListener &fn) {
    if (key.empty()) {
        logImpl(ZK_HA_LOG_WARN, "RelayBank::addListener: empty key rejected (use a name)");
        return;
    }
    for (size_t i = 0; i < mKeyed.size(); ++i) {
        if (mKeyed[i].first == key) {          /* 同 key 覆盖 => 可重复注册（幂等）*/
            mKeyed[i].second = fn;
            logImpl(ZK_HA_LOG_DEBUG, "RelayBank: listener '%s' replaced (total=%d)",
                    key.c_str(), listenerCount());
            return;
        }
    }
    mKeyed.push_back(std::make_pair(key, fn));
    logImpl(ZK_HA_LOG_DEBUG, "RelayBank: listener '%s' registered (total=%d)",
            key.c_str(), listenerCount());
}

bool RelayBank::removeListener(const std::string &key) {
    for (std::vector<std::pair<std::string, RelayListener> >::iterator it = mKeyed.begin();
         it != mKeyed.end(); ++it) {
        if (it->first == key) {
            mKeyed.erase(it);
            logImpl(ZK_HA_LOG_DEBUG, "RelayBank: listener '%s' removed (total=%d)",
                    key.c_str(), listenerCount());
            return true;
        }
    }
    return false;
}

int RelayBank::listenerCount() const {
    return (mUi ? 1 : 0) + (int) mKeyed.size();
}

std::string RelayBank::listenerKeys() const {
    std::string s;
    for (size_t i = 0; i < mKeyed.size(); ++i) {
        if (!s.empty()) s += ",";
        s += mKeyed[i].first;
    }
    return s;
}

void RelayBank::notifyAll() {
    logImpl(ZK_HA_LOG_DEBUG, "RelayBank: notifyAll -> %d listener(s)", listenerCount());
    for (int ch = 1; ch <= mChannels; ++ch) {
        /* 复用 set() 的差分语义会让"相同值不通知"漏掉对齐；这里显式重放 */
        RelayListener ui = mUi;
        std::vector<RelayListener> keyed;
        for (size_t i = 0; i < mKeyed.size(); ++i) keyed.push_back(mKeyed[i].second);
        bool on = mState[(size_t) (ch - 1)];
        if (ui) ui(ch, on);
        for (size_t i = 0; i < keyed.size(); ++i) {
            if (keyed[i]) keyed[i](ch, on);
        }
    }
}

/* =========================== Config =========================== */

Config::Config()
    : channels(3),
      lwtEnabled(true),
      publishStatusJson(true),
      tickMs(1000),
      reconnectMinMs(10000),
      reconnectMaxMs(60000) {
}

/* =========================== Bridge::Impl =========================== */

struct Bridge::Impl {
    Config cfg;
    RelayBank bank;

    mutable std::mutex mtx;
    void *client;                 /* mqtt::Client* —— 头文件不泄漏 mqtt-cxx 类型 */
    int mGen;                     /* 代次：旧 client 的迟到回调一律丢弃 */
    bool mConnected;
    bool mConnecting;
    bool mStarted;
    long long mLastTryMono;
    int mFailStreak;
    int mReconnectCount;

    std::vector<bool> mLastState; /* 已发布基线（差分兜底用）*/
    std::vector<bool> mLastValid;

    std::string mLastError;
    mutable std::string mErrCache;   /* lastError() 返回的 c_str 要活到下次 setErr */

    Impl() : bank(3), client(NULL), mGen(0), mConnected(false), mConnecting(false),
             mStarted(false), mLastTryMono(0), mFailStreak(0), mReconnectCount(0) {
    }

    /* ---- 小工具 ---- */
    std::string prefix() const {
        std::lock_guard<std::mutex> lk(mtx);
        return cfg.prefix;
    }

    std::string uidBase() const { return uidOf(prefix()); }

    bool started() const {
        std::lock_guard<std::mutex> lk(mtx);
        return mStarted;
    }

    std::string discoveryRoot() {
        std::lock_guard<std::mutex> lk(mtx);
        if (cfg.discoveryPrefix.empty()) return std::string("homeassistant");
        return cfg.discoveryPrefix;
    }

    void setErr(const std::string &m) {
        std::lock_guard<std::mutex> lk(mtx);
        mLastError = m;
    }

    std::string lastErr() const {
        std::lock_guard<std::mutex> lk(mtx);
        return mLastError;
    }

    std::string stateTopic(int ch) {
        char t[192];
        snprintf(t, sizeof(t), "%s/switch/relay_%d/state", prefix().c_str(), ch);
        return std::string(t);
    }

    std::string commandTopic(int ch) {
        char t[192];
        snprintf(t, sizeof(t), "%s/switch/relay_%d/command", prefix().c_str(), ch);
        return std::string(t);
    }

    /* ---- 底层发布（不检查连接；调用方保证）---- */
    bool publishRaw(const std::string &topic, const std::string &payload, bool retained) {
        mqtt::Client *c = NULL;
        {
            std::lock_guard<std::mutex> lk(mtx);
            c = static_cast<mqtt::Client *>(client);
        }
        if (c == NULL) return false;
        bool ok = c->publish(topic, payload, mqtt::QOS_AT_MOST_ONCE, retained);
        if (!ok) {
            /* ⚠️ 返回 false 只代表"提交失败"；QOS0 下 true 也不等于 broker 收到 */
            logImpl(ZK_HA_LOG_WARN, "publish failed (submit) %s", topic.c_str());
        }
        return ok;
    }

    /* ---- 建连（跑在 detached 线程里）---- */
    void connectAsync() {
        std::thread(&Bridge::Impl::connect, this).detach();
    }

    void connect() {
        std::string server;
        {
            std::lock_guard<std::mutex> lk(mtx);
            server = cfg.server;
        }
        if (server.empty()) {
            logImpl(ZK_HA_LOG_WARN, "connect: no server configured (Config::server 为空)");
            setErr("broker 未配置：Config::server 为空（组件不写死任何地址）");
            std::lock_guard<std::mutex> lk(mtx);
            mConnecting = false;
            return;
        }

        /* ① 先回收旧 client：锁内摘指针 + 代次 +1，锁外 delete（避免与库线程回调互等）*/
        mqtt::Client *old = NULL;
        int myGen = 0;
        {
            std::lock_guard<std::mutex> lk(mtx);
            old = static_cast<mqtt::Client *>(client);
            client = NULL;
            myGen = ++mGen;
            mLastTryMono = monoNowMs();
            mReconnectCount++;
        }
        if (old != NULL) {
            delete old;   /* 析构 = 断开 paho 连接；其迟到回调将因 gen 不符直接返回 */
            logImpl(ZK_HA_LOG_DEBUG, "old client dropped (gen=%d)", myGen);
        }

        /* ⚠️ 取值必须在锁外/不嵌套锁：uidOf 是纯函数，uidBase() 会再取一次锁（会自锁）*/
        std::string prefix_, clientId_, user_, pass_;
        bool lwt = true;
        {
            std::lock_guard<std::mutex> lk(mtx);
            prefix_ = cfg.prefix;
            clientId_ = cfg.clientId.empty() ? uidOf(cfg.prefix) : cfg.clientId;
            user_ = cfg.username;
            pass_ = cfg.password;
            lwt = cfg.lwtEnabled;
        }

        mqtt::Client::Configuration conf;
        conf.server = server;
        conf.client_id = clientId_;
        conf.username = user_;
        conf.password = pass_;
        conf.clean_session = true;
        if (lwt) {
            conf.will.topic = prefix_ + "/availability";
            conf.will.message = "offline";
            conf.will.qos = mqtt::QOS_AT_MOST_ONCE;
            conf.will.retained = true;
        }

        /* ② 回调里只在锁内翻标志；真正干活（发布/订阅/业务回调）放锁外 */
        conf.on_connected = [this, myGen](const std::string &cause) {
            {
                std::lock_guard<std::mutex> lk(mtx);
                if (myGen != mGen) return;          /* 旧 client 的迟到回调 */
                mConnected = true;
                mConnecting = false;
                mFailStreak = 0;
            }
            logImpl(ZK_HA_LOG_DEBUG, "connected (gen=%d cause=%s)", myGen, cause.c_str());
            onConnectedWork();
            std::function<void()> cb;
            {
                std::lock_guard<std::mutex> lk(mtx);
                cb = cfg.onConnected;
            }
            if (cb) cb();
        };
        conf.on_disconnected = [this, myGen](const std::string &cause) {
            std::function<void(const std::string &)> cb;
            int streak = 0;
            {
                std::lock_guard<std::mutex> lk(mtx);
                if (myGen != mGen) return;
                mConnected = false;
                mConnecting = false;
                if (mFailStreak < 100) mFailStreak++;
                streak = mFailStreak;
                cb = cfg.onDisconnected;
            }
            /* 日志/业务回调都放锁外：业务日志钩子若回查 Bridge（connected() 等）不会再取锁 */
            logImpl(ZK_HA_LOG_WARN, "disconnected (gen=%d fail=%d cause=%s)",
                    myGen, streak, cause.c_str());
            if (cb) cb(cause);
        };

        logImpl(ZK_HA_LOG_DEBUG, "connecting %s ... (gen=%d total=%d)",
                conf.server.c_str(), myGen, mReconnectCount);

        mqtt::Client *nc = NULL;
        bool created = false;
        try {
            nc = new mqtt::Client(conf);   /* 构造即发起连接（异步）*/
            created = true;
        } catch (const std::exception &e) {
            setErr(std::string("建连异常：") + e.what());
            logImpl(ZK_HA_LOG_ERROR, "connect failed: %s", e.what());
        } catch (...) {
            setErr("建连异常（未知）");
            logImpl(ZK_HA_LOG_ERROR, "connect failed (unknown)");
        }

        bool discard = true;
        {
            std::lock_guard<std::mutex> lk(mtx);
            mConnecting = false;
            if (created && mStarted && myGen == mGen) {
                client = nc;               /* 只保留这一个 client（同 client_id 互踢的根治办法）*/
                discard = false;
            }
        }
        if (discard && nc != NULL) {
            delete nc;                     /* stop() 期间 / 被下一代取代：丢弃，别留在 broker 上 */
            logImpl(ZK_HA_LOG_WARN, "connect result discarded (gen=%d started=%d)",
                    myGen, started() ? 1 : 0);
        }
    }

    /* ---- 连上后的固定动作（顺序有意义）---- */
    void onConnectedWork() {
        /* ① 继电器变化 -> 上报：**每次连接都幂等注册**（具名 key，同 key 只占一个槽）。
         *    不用"只注册一次"的门闩 —— 一旦回调被抹掉，门闩会让它在本进程内永远无法恢复。*/
        bank.addListener("ha_bridge", [this](int ch, bool on) { onRelayChanged(ch, on); });
        logImpl(ZK_HA_LOG_DEBUG, "relay listener ok, total=%d [%s]",
                bank.listenerCount(), bank.listenerKeys().c_str());

        /* ② 先宣告在线（HA 才不会把紧接着的 discovery 当成不可用），再 discovery/订阅，
         *    最后主动推一遍**新鲜**状态（覆盖 broker 上可能残留的旧 retained）。*/
        publishAvailability(true);
        publishDiscovery();
        subscribeAll();
        publishAllStates();
        bool wantStatus = false;
        {
            std::lock_guard<std::mutex> lk(mtx);
            wantStatus = cfg.publishStatusJson;
        }
        if (wantStatus) publishStatus();
    }

    void subscribeAll() {
        mqtt::Client *c = NULL;
        std::string p;
        std::vector<std::string> extra;
        {
            std::lock_guard<std::mutex> lk(mtx);
            c = static_cast<mqtt::Client *>(client);
            if (c == NULL) return;
            p = cfg.prefix;
            extra = cfg.extraSubscriptions;
        }
        std::string cmd = p + "/switch/+/command";
        c->subscribe(cmd, mqtt::QOS_AT_MOST_ONCE,
                     [this](const std::string &t, const std::string &pl) { onMessage(t, pl); });
        for (size_t i = 0; i < extra.size(); ++i) {
            if (extra[i].empty()) continue;
            c->subscribe(extra[i], mqtt::QOS_AT_MOST_ONCE,
                         [this](const std::string &t, const std::string &pl) { onMessage(t, pl); });
            logImpl(ZK_HA_LOG_DEBUG, "subscribed (extra) %s", extra[i].c_str());
        }
        logImpl(ZK_HA_LOG_DEBUG, "subscribed %s (+%d extra)", cmd.c_str(), (int) extra.size());
    }

    void onRelayChanged(int ch, bool on) {
        publishState(ch, on);
        publishStatus();                 /* state 与 status 必须同时刷新，否则 HA 侧两套读数自相矛盾 */
    }

    void onMessage(const std::string &topic, const std::string &payload) {
        logImpl(ZK_HA_LOG_DEBUG, "recv %s = %s", topic.c_str(), payload.c_str());

        std::string p = prefix() + "/switch/relay_";
        if (topic.compare(0, p.size(), p) == 0) {
            /* ⚠️ 只认「<n>/command」且 payload 恰为 ON/OFF：broker 每次（重）订阅后会回放
             *    retained（含空 payload 的撤销消息），把回放当命令执行 = 重连一次关一次灯。*/
            std::string rest = topic.substr(p.size());
            const char *suf = "/command";
            const size_t sufLen = strlen(suf);
            if (rest.size() != 1 + sufLen || rest.compare(1, sufLen, suf) != 0) {
                logImpl(ZK_HA_LOG_DEBUG, "ignore non-command topic shape (%s)", topic.c_str());
                return;
            }
            int ch = rest[0] - '0';
            if (ch < 1 || ch > bank.channels()) {
                logImpl(ZK_HA_LOG_WARN, "ignore command for bad channel (%s)", topic.c_str());
                return;
            }
            if (payload == "ON") {
                bank.set(ch, true);      /* set() -> listener -> 回执 state/status（retained）*/
            } else if (payload == "OFF") {
                bank.set(ch, false);
            } else {
                logImpl(ZK_HA_LOG_WARN, "ignore non ON/OFF command (%s = [%s])",
                        topic.c_str(), payload.c_str());
                return;
            }
            std::function<void(int, bool)> cb;
            {
                std::lock_guard<std::mutex> lk(mtx);
                cb = cfg.onCommand;
            }
            if (cb) cb(ch, payload == "ON");
            return;
        }

        std::function<void(const std::string &, const std::string &)> cb;
        {
            std::lock_guard<std::mutex> lk(mtx);
            cb = cfg.onMessage;
        }
        if (cb) cb(topic, payload);
    }

    /* ---- 上行 ---- */
    bool connectedNow() const {
        std::lock_guard<std::mutex> lk(mtx);
        return mConnected;
    }

    void publishAvailability(bool online) {
        if (!publishRaw(prefix() + "/availability", online ? "online" : "offline", true)) {
            /* 未连接/无 client：显式可观测，不静默丢（真机事故：静默丢导致现场看不出问题）*/
            logImpl(ZK_HA_LOG_DEBUG, "availability skipped (client=null) online=%d", online ? 1 : 0);
        }
    }

    void publishDiscovery() {
        mqtt::Client *c = NULL;
        std::string p, uidBase, devName, mf, mdl, root;
        std::vector<std::string> names;
        int n = 0;
        {
            std::lock_guard<std::mutex> lk(mtx);
            c = static_cast<mqtt::Client *>(client);
            if (c == NULL) return;
            p = cfg.prefix;
            uidBase = uidOf(p);
            devName = cfg.deviceName.empty() ? cfg.deviceId : cfg.deviceName;
            mf = cfg.manufacturer;
            mdl = cfg.model;
            names = cfg.relayNames;
            root = cfg.discoveryPrefix.empty() ? std::string("homeassistant") : cfg.discoveryPrefix;
            n = bank.channels();
        }

        base::JSONObject dev;
        dev.put("ids", uidBase);
        if (!devName.empty()) dev.put("name", devName);
        if (!mf.empty()) dev.put("mf", mf);
        if (!mdl.empty()) dev.put("mdl", mdl);

        for (int ch = 1; ch <= n; ++ch) {
            std::string rid = "relay_" + std::to_string(ch);
            std::string rname;
            if ((size_t) ch <= names.size()) rname = names[(size_t) (ch - 1)];
            if (rname.empty()) rname = rid;          /* 回落派生名，不编造本地化字面量 */

            base::JSONObject j;
            j.put("name", rname);
            j.put("uniq_id", uidBase + "_" + rid);
            j.put("stat_t", p + "/switch/" + rid + "/state");
            j.put("cmd_t", p + "/switch/" + rid + "/command");
            j.put("pl_on", std::string("ON"));
            j.put("pl_off", std::string("OFF"));
            j.put("stat_on", std::string("ON"));
            j.put("stat_off", std::string("OFF"));
            j.put("avty_t", p + "/availability");
            j.put("pl_avail", std::string("online"));
            j.put("pl_not_avail", std::string("offline"));
            j.put("dev", dev);
            c->publish(root + "/switch/" + uidBase + "_" + rid + "/config",
                       j.toString(), mqtt::QOS_AT_MOST_ONCE, true);
        }
        logImpl(ZK_HA_LOG_DEBUG, "HA discovery published (%d switch(es), root=%s)",
                n, root.c_str());
    }

    bool publishState(int ch, bool on) {
        if (!connectedNow()) {
            logImpl(ZK_HA_LOG_WARN, "drop relay_%d state publish (not connected)", ch);
            setErr("未连接 broker：state 未发出（等重连后由差分兜底补发）");
            return false;
        }
        if (ch < 1 || ch > bank.channels()) return false;
        bool ok = publishRaw(stateTopic(ch), on ? "ON" : "OFF", true);
        {
            std::lock_guard<std::mutex> lk(mtx);
            if ((size_t) ch <= mLastState.size()) {
                mLastState[(size_t) (ch - 1)] = on;
                mLastValid[(size_t) (ch - 1)] = true;
            }
        }
        logImpl(ZK_HA_LOG_DEBUG, "%s = %s", stateTopic(ch).c_str(), on ? "ON" : "OFF");
        return ok;
    }

    void publishAllStates() {
        for (int ch = 1; ch <= bank.channels(); ++ch) {
            publishState(ch, bank.get(ch));
        }
    }

    bool publishStatus() {
        std::function<std::string()> fn;
        {
            std::lock_guard<std::mutex> lk(mtx);
            if (!cfg.publishStatusJson) return false;
            fn = cfg.statusJson;
        }
        if (!fn) {
            logImpl(ZK_HA_LOG_WARN, "status skipped: Config::statusJson 未给（组件不编造状态内容）");
            return false;
        }
        if (!connectedNow()) return false;
        std::string json = fn();
        if (json.empty()) {
            logImpl(ZK_HA_LOG_WARN, "status skipped: statusJson 返回空串");
            return false;
        }
        return publishRaw(prefix() + "/status", json, true);
    }

    /* ---- 1s 差分兜底 ---- */
    void relayWatchdog() {
        bool changed = false;
        {
            std::lock_guard<std::mutex> lk(mtx);
            for (int ch = 1; ch <= bank.channels(); ++ch) {
                bool v = bank.get(ch);
                bool valid = (size_t) ch <= mLastValid.size() && mLastValid[(size_t) (ch - 1)];
                bool same = valid && (size_t) ch <= mLastState.size()
                            && mLastState[(size_t) (ch - 1)] == v;
                if (!same) changed = true;
            }
        }
        if (!changed) return;
        logImpl(ZK_HA_LOG_WARN, "relay watchdog resync (listener miss / restore 未对齐)");
        publishAllStates();
        publishStatus();
    }
};

/* =========================== Bridge =========================== */

Bridge::Bridge() : mImpl(new Impl()) {
}

Bridge::~Bridge() {
    stop();
    delete mImpl;
    mImpl = NULL;
}

Bridge &Bridge::instance() {
    static Bridge s;
    return s;
}

Result Bridge::start(const Config &cfgIn) {
    Config cfg = cfgIn;

    if (cfg.server.empty()) {
        const std::string m = "broker 未配置：Config::server 为空（组件不写死任何地址；"
                              "工程侧应从配网页/prefs 取）";
        mImpl->setErr(m);
        logImpl(ZK_HA_LOG_ERROR, "start refused: %s", m.c_str());
        return Result(HA_ERR_NOT_CONFIGURED, m);
    }
    if (cfg.prefix.empty()) {
        if (cfg.deviceId.empty()) {
            const std::string m = "主题前缀未配置：Config::prefix 与 Config::deviceId 都为空";
            mImpl->setErr(m);
            logImpl(ZK_HA_LOG_ERROR, "start refused: %s", m.c_str());
            return Result(HA_ERR_NOT_CONFIGURED, m);
        }
        cfg.prefix = cfg.deviceId;   /* 给了 deviceId 没给 prefix：前缀就是它，不编造额外层级 */
        logImpl(ZK_HA_LOG_WARN, "prefix empty -> derived from deviceId: %s", cfg.prefix.c_str());
    }
    if (cfg.channels < 1) {
        const std::string m = "继电器路数非法：Config::channels < 1";
        mImpl->setErr(m);
        return Result(HA_ERR_ARG, m);
    }
    if (cfg.channels > 8) {
        logImpl(ZK_HA_LOG_WARN, "channels %d > 8 -> clamped to 8", cfg.channels);
        cfg.channels = 8;
    }
    if (cfg.reconnectMinMs < 1000) cfg.reconnectMinMs = 1000;
    if (cfg.reconnectMaxMs < cfg.reconnectMinMs) cfg.reconnectMaxMs = cfg.reconnectMinMs;

    stop();   /* 重复 start / 改完配置重连：先干净地停（销毁 client）再起 */

    {
        std::lock_guard<std::mutex> lk(mImpl->mtx);
        if (cfg.channels != mImpl->bank.channels()) {
            /* reset() 会清 listener —— 所以 listener 请在 start() 之后再注册 */
            mImpl->bank.reset(cfg.channels);
        }
        mImpl->cfg = cfg;
        mImpl->mLastState.assign((size_t) cfg.channels, false);
        mImpl->mLastValid.assign((size_t) cfg.channels, false);
        mImpl->mFailStreak = 0;
        mImpl->mLastTryMono = 0;
        mImpl->mStarted = true;
        mImpl->mConnecting = true;
        mImpl->mLastError.clear();
    }
    const std::string server = cfg.server;
    const std::string prefix = cfg.prefix;
    logImpl(ZK_HA_LOG_DEBUG, "start: server=%s prefix=%s channels=%d", server.c_str(),
            prefix.c_str(), cfg.channels);
    mImpl->connectAsync();
    return Result(HA_OK, "已启动（正在连接 " + server + "）");
}

void Bridge::stop() {
    mqtt::Client *old = NULL;
    {
        std::lock_guard<std::mutex> lk(mImpl->mtx);
        mImpl->mConnected = false;
        mImpl->mConnecting = false;
        mImpl->mStarted = false;
        old = static_cast<mqtt::Client *>(mImpl->client);
        mImpl->client = NULL;
        mImpl->mGen++;       /* 代次 +1：旧 client 的迟到回调全部作废 */
    }
    if (old != NULL) {
        delete old;          /* 锁外 delete */
        logImpl(ZK_HA_LOG_DEBUG, "stopped, client destroyed");
    }
}

Result Bridge::tick() {
    if (!mImpl->started()) {
        return Result(HA_ERR_NOT_STARTED, "未 start()：tick 无动作");
    }

    bool connected = false, connecting = false;
    {
        std::lock_guard<std::mutex> lk(mImpl->mtx);
        connected = mImpl->mConnected;
        connecting = mImpl->mConnecting;
    }

    if (!connected && !connecting) {
        long long backoff = mImpl->cfg.reconnectMinMs;
        for (int i = 0; i < mImpl->mFailStreak && i < 3; i++) backoff *= 2;   /* 10→20→40→封顶 60s */
        if (backoff > mImpl->cfg.reconnectMaxMs) backoff = mImpl->cfg.reconnectMaxMs;
        const long long now = monoNowMs();
        if (mImpl->mLastTryMono != 0 && (now - mImpl->mLastTryMono) < backoff) {
            return Result(HA_OK, "重连退避中");                     /* 退避窗口内不重试 */
        }
        logImpl(ZK_HA_LOG_WARN, "link down -> reconnect (gen=%d fail=%d backoff=%lldms total=%d)",
                mImpl->mGen, mImpl->mFailStreak, backoff, mImpl->mReconnectCount);
        {
            std::lock_guard<std::mutex> lk(mImpl->mtx);
            mImpl->mConnecting = true;
        }
        mImpl->connectAsync();
        return Result(HA_OK, "发起重连");
    }

    if (connected) {
        mImpl->relayWatchdog();
    }
    return Result(HA_OK);
}

bool Bridge::started() const { return mImpl->started(); }

bool Bridge::connected() const { return mImpl->connectedNow(); }

RelayBank &Bridge::relays() { return mImpl->bank; }

Result Bridge::publishState(int ch, bool on) {
    if (ch < 1 || ch > mImpl->bank.channels()) {
        char m[128];
        snprintf(m, sizeof(m), "通道越界：ch=%d（合法 1..%d）", ch, mImpl->bank.channels());
        return Result(HA_ERR_ARG, m);
    }
    if (!connected()) {
        return Result(HA_ERR_NOT_CONNECTED, "未连接 broker：state 未发出（重连后由 1s 差分兜底补发）");
    }
    mImpl->publishState(ch, on);
    return Result(HA_OK, "已发布 state");
}

Result Bridge::publishAllStates() {
    if (!connected()) {
        return Result(HA_ERR_NOT_CONNECTED, "未连接 broker：state 未发出");
    }
    mImpl->publishAllStates();
    return Result(HA_OK, "已发布全部 state");
}

Result Bridge::publishStatus() {
    if (!connected()) {
        return Result(HA_ERR_NOT_CONNECTED, "未连接 broker：status 未发出");
    }
    bool ok = mImpl->publishStatus();
    if (!ok) {
        return Result(HA_ERR_ARG, "status 未发：Config::statusJson 未给/返回空（组件不编造状态内容）");
    }
    return Result(HA_OK, "已发布 status");
}

Result Bridge::publishEvent(const std::string &json) {
    if (json.empty()) return Result(HA_ERR_ARG, "事件 JSON 为空");
    if (!connected()) return Result(HA_ERR_NOT_CONNECTED, "未连接 broker：event 未发出");
    mImpl->publishRaw(prefix() + "/event", json, false);   /* 非 retained：事件不进历史状态 */
    return Result(HA_OK, "已发布 event");
}

Result Bridge::publishAvailability(bool online) {
    if (!connected()) {
        return Result(HA_ERR_NOT_CONNECTED, "未连接 broker：availability 未发出");
    }
    mImpl->publishAvailability(online);
    return Result(HA_OK, "已发布 availability");
}

Result Bridge::publishDiscovery() {
    if (!connected()) {
        return Result(HA_ERR_NOT_CONNECTED, "未连接 broker：discovery 未发出（重连后自动补发）");
    }
    mImpl->publishDiscovery();
    return Result(HA_OK, "已发布 discovery");
}

Result Bridge::clearDiscovery(const std::string &component, const std::string &objectId) {
    if (component.empty() || objectId.empty()) {
        return Result(HA_ERR_ARG, "clearDiscovery 需要 component 与 objectId 都非空");
    }
    if (!connected()) {
        return Result(HA_ERR_NOT_CONNECTED, "未连接 broker：撤销消息未发出");
    }
    const std::string topic = mImpl->discoveryRoot() + "/" + component + "/" + objectId + "/config";
    /* retained 撤销：发**空 payload** + retained（HA 收到空载荷会删掉该实体）*/
    mImpl->publishRaw(topic, std::string(), true);
    logImpl(ZK_HA_LOG_DEBUG, "retained entity cleared: %s", topic.c_str());
    return Result(HA_OK, "已撤销 " + topic);
}

std::string Bridge::prefix() const { return mImpl->prefix(); }

std::string Bridge::uniqueId() const { return mImpl->uidBase(); }

int Bridge::reconnects() const {
    std::lock_guard<std::mutex> lk(mImpl->mtx);
    return mImpl->mReconnectCount;
}

int Bridge::generation() const {
    std::lock_guard<std::mutex> lk(mImpl->mtx);
    return mImpl->mGen;
}

const char *Bridge::lastError() const {
    /* 拷进持久缓冲再返指针：调用方拿到的串在下一次 lastError()/setErr() 前一直有效 */
    mImpl->mErrCache = mImpl->lastErr();
    return mImpl->mErrCache.c_str();
}

void Bridge::setLogHook(zk_ha_log_fn fn, void *user) {
    std::lock_guard<std::mutex> lk(gLogMtx);
    gLogFn = fn;
    gLogUser = user;
}

} /* namespace ha */
} /* namespace zk */
