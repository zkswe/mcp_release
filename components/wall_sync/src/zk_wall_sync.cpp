/* =====================================================================
 * zk_wall_sync.cpp —— zk::wall::Sync（组网 / 校时 / 时间轴内核）
 *
 * 落地来源（**逐条同源，不新造实现**）：
 *   projects/SmartPanel_HA/src/wall/WallLink.cpp（真机验证版 v7.13，831 行）
 * 去掉的项目私有依赖（→ 改成构造入参/回调，见 zk_wall.h）：
 *   · StoragePreferences（读 sp_wall_* 配置）  → SyncConfig
 *   · LOGD/LOGW/LOGI（工程日志）               → LogFn 钩子 + ZWLOG
 *   · TimeHelper（墙钟回退链）                 → NowMsFn 钩子（不设 = clock_gettime）
 *   · ClockManager（从机系统时钟跟随）          → ClockFollowFn 钩子
 *   · 硬编码 "/mnt/sdnand/wall" / 端口 8901     → SyncConfig::wallRoot / udpPort
 *
 * 协议（明文、局域网；一条 ≤176 字节）：
 *   host → peers : wall|<组名>|<t0_ms>|<seg_ms>|<n>|<pub_ms>[|<clips>|<total_ms>]
 *   slave → host : ping|<本机ms>|<组名>     （报活 + 双向测时起手；主机据此登记单播名单）
 *   host → slave : pong|<t0>|<主机ms>       （从机算 RTT/2 钟差）
 *   slave → host : wall?|<组名>             （请主机立刻补发 epoch；进屏保快通道）
 *   组名不匹配 → 直接丢弃。老读法只读前 6 段 → 末尾追加字段向后兼容。
 *
 * 三个"必须这样"的坑（真源实测，改动前先读）：
 *   ① 墙钟必须**毫秒级绝对钟**：旧版回退到秒级（x500）时只能测到 ±1000ms，两台相位永远收敛不到 1 帧。
 *   ② skew 必须**双向测时 RTT/2**：单程中值 = 真钟差 + 排队延迟（实测被污染成 116ms / 8.0s，
 *      画面差同量级）；单程值只作 pong 断 >20s 时的兜底，且要与当前值相差 ≤250ms 才采用。
 *   ③ 收包必须**一次排空**：接收队列积压时手里的样本是几秒前的旧包（现场实测积压 8.0s），
 *      所以 drainUdp 单次上限 64 包（旧版 8）。
 * ===================================================================== */
#include "zk_wall_internal.h"

#include <rapidjson/document.h>

#include <arpa/inet.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <vector>

namespace zk {
namespace wall {

using namespace zk::wall::internal;

#define WALL_LOST_MS 10000          /* >10s 收不到 epoch = 失联 → 业务回退普通轮播 */
#define WALL_PEER_MAX 8             /* 一组最多 4 屏；名单留余量，溢出不再收 */
#define WALL_DRAIN_MAX 64           /* 单次收包上限（坑③：必须一次排空） */

/* ═════════════════ internal：钩子 / 日志 / 时钟 / 文件 ═════════════════ */

namespace internal {

Hooks& hooks() {
    static Hooks h;
    return h;
}

void log(int level, const char* fmt, ...) {
    Hooks& h = hooks();
    if (h.logFn == NULL) return;                 /* 没接日志就静默（设备上 stdout 是 /dev/null） */
    char b[256];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(b, sizeof(b), fmt, ap);
    va_end(ap);
    h.logFn(level, b, h.logUser);
}

long long nowMsRaw() {
    Hooks& h = hooks();
    if (h.nowFn != NULL) {
        const long long t = h.nowFn(h.nowUser);
        if (t > 1000000000000LL) return t;       /* 形如 ms 时间戳（2001 以后）才算可信 */
    }
    /* 默认：clock_gettime(CLOCK_REALTIME) 直取毫秒（坑①：不要退到秒级分辨率） */
    struct timespec ts;
    if (clock_gettime(CLOCK_REALTIME, &ts) == 0) {
        const long long ms = (long long)ts.tv_sec * 1000LL + (long long)(ts.tv_nsec / 1000000L);
        if (ms > 1000000000000LL) return ms;
    }
    return 0;                                    /* <=0 = 时钟不可信，调用方按"未校时"处理 */
}

bool readFileAll(const std::string& path, std::string* out) {
    if (out == NULL) return false;
    FILE* f = fopen(path.c_str(), "rb");
    if (f == NULL) return false;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return false; }
    const long n = ftell(f);
    if (n <= 0 || n > 4 * 1024 * 1024) { fclose(f); return false; }
    rewind(f);
    out->resize((size_t)n);
    const size_t rd = fread(&(*out)[0], 1, (size_t)n, f);
    fclose(f);
    out->resize(rd);
    return rd > 0;
}

} /* namespace internal */

/* ═════════════════ internal：playlist.json 取值小工具 ═════════════════ */

namespace {

long long jLong(const rapidjson::Value& o, const char* key, long long def) {
    if (!o.IsObject() || !o.HasMember(key)) return def;
    const rapidjson::Value& v = o[key];
    if (v.IsInt64()) return (long long)v.GetInt64();
    if (v.IsInt()) return (long long)v.GetInt();
    if (v.IsUint()) return (long long)v.GetUint();
    if (v.IsDouble()) return (long long)(v.GetDouble() + 0.5);
    return def;
}

std::string jStr(const rapidjson::Value& o, const char* key) {
    if (!o.IsObject() || !o.HasMember(key)) return std::string();
    const rapidjson::Value& v = o[key];
    return v.IsString() ? std::string(v.GetString()) : std::string();
}

} /* anonymous namespace */

/* ═════════════════ Sync::Impl ═════════════════ */

struct Sync::Impl {
    /* playlist 内部表示（一个 clip 一个条目；files 按"面板序号-1"索引，缺项留空 → 用默认名兜底） */
    struct Clip {
        std::string name;
        long long durMs;
        std::vector<std::string> files;
        Clip() : durMs(0) {}
    };
    struct WallPeer { unsigned int ip; int port; long long lastMs; };

    SyncConfig cfg;
    bool started;

    bool master;
    int idx, n;
    long long segMs;
    int leadMs;
    long long t0Ms;              /* epoch（墙钟 ms） */
    long long lastHbMs;          /* 主机低频广播心跳（每 3s 一包，零配置可发现） */
    long long lastRecvMs;        /* 上次收到 epoch 的墙钟 */
    long long playStartMs;       /* 本段起播墙钟（诊断） */
    long long lastTargetMs;      /* 本段目标整边界墙钟（诊断） */
    int driftMs;

    /* 钟差：双向测时（主路径）+ epoch 单程（兜底） */
    int skewMs;
    int skewRttMs;
    bool skewFromPp;
    bool skewValid;
    int skewDrop;
    long long fastRtt[6];        /* 短窗（最近 6 个 pong）min-RTT —— 供时钟跟随环用 */
    long long fastOff[6];
    int fastN, fastIdx;
    int fastSkewMs, fastRttMs;
    long long ppRtt[32];         /* 长窗 32 笔 min-RTT（NTP clock-filter 口径） */
    long long ppOff[32];
    int ppN, ppIdx;
    long long lastPongMs;
    int pongRecv;
    long long lastPingMs;
    long long epochSkewRing[8];
    int epochSkewN, epochSkewIdx;
    long long epochSkewMs;
    bool epochSkewValid;

    /* 主机地址（从 epoch 包源地址学得）—— 从机做双向测时/单播用 */
    unsigned int peerIp;
    int peerPort;
    bool peerValid;
    std::vector<WallPeer> peers;
    int cfgMasterPort;
    long long lastAskMs;         /* 广播兜底请求的节流时间戳 */
    unsigned heartbeat;

    /* UDP */
    bool udpReady;
    int fd;

    /* playlist（clipCount==0 → 旧布局单 clip 模式） */
    std::vector<Clip> clips;
    int clipCount;
    long long totalMsVal;
    long long remoteClips;
    long long remoteTotalMs;
    long long warnedRemoteTotal;

    Impl()
        : started(false), master(false), idx(1), n(2), segMs(30000), leadMs(0),
          t0Ms(0), lastHbMs(0), lastRecvMs(0), playStartMs(0), lastTargetMs(0), driftMs(0),
          skewMs(0), skewRttMs(-1), skewFromPp(false), skewValid(false), skewDrop(0),
          fastN(0), fastIdx(0), fastSkewMs(0), fastRttMs(-1),
          ppN(0), ppIdx(0), lastPongMs(0), pongRecv(0), lastPingMs(0),
          epochSkewN(0), epochSkewIdx(0), epochSkewMs(0), epochSkewValid(false),
          peerIp(0), peerPort(0), peerValid(false), cfgMasterPort(8901), lastAskMs(0),
          heartbeat(0), udpReady(false), fd(-1),
          clipCount(0), totalMsVal(0), remoteClips(0), remoteTotalMs(0), warnedRemoteTotal(-1) {
        for (int i = 0; i < 6; i++) { fastRtt[i] = 0; fastOff[i] = 0; }
        for (int i = 0; i < 32; i++) { ppRtt[i] = 0; ppOff[i] = 0; }
        for (int i = 0; i < 8; i++) epochSkewRing[i] = 0;
    }

    /* ── 路径 ─────────────────────────────────────────────── */
    std::string wallRoot() const { return cfg.wallRoot.empty() ? std::string("/mnt/sdnand/wall") : cfg.wallRoot; }
    std::string groupDir() const { return wallRoot() + "/" + cfg.group; }
    std::string playlistPath() const { return groupDir() + "/playlist.json"; }
    std::string segPath() const {
        char b[256];
        snprintf(b, sizeof(b), "%s/seg_%d.mp4", groupDir().c_str(), idx);
        return b;
    }
    /* 播放器"当前节目"键：playlist = 清单文件（稳定）；单 clip = seg_<idx>.mp4 */
    std::string playKey() const { return playlistMode() ? playlistPath() : segPath(); }

    bool playlistMode() const { return clipCount > 0 && totalMsVal > 0; }

    long long clipDurMs(int k) const {
        if (k < 0 || k >= (int)clips.size()) return 0;
        return clips[(size_t)k].durMs;
    }
    long long clipStartMs(int k) const {
        long long c = 0;
        for (int i = 0; i < k && i < (int)clips.size(); i++) c += clips[(size_t)i].durMs;
        return c;
    }
    long long periodMs() const {
        if (playlistMode()) return totalMsVal;
        return (segMs >= 1000) ? segMs : 30000;
    }
    /* 组内时间 g → (clip k, 段内偏移 off)；单 clip 模式返回 false（调用方按老口径走） */
    bool clipAt(long long groupTimeMs, int* k, long long* offMs) const {
        if (!playlistMode()) return false;
        long long pos = groupTimeMs % totalMsVal;
        if (pos < 0) pos += totalMsVal;
        long long cum = 0;
        for (int i = 0; i < (int)clips.size(); i++) {
            const long long d = clips[(size_t)i].durMs;
            if (pos < cum + d) {
                if (k) *k = i;
                if (offMs) *offMs = pos - cum;
                return true;
            }
            cum += d;
        }
        /* 清单异常（Σdur < total）兜底：落最后一个 clip 的段内 0 */
        if (k) *k = (int)clips.size() - 1;
        if (offMs) *offMs = 0;
        return true;
    }
    std::string segPathForClip(int k) const {
        if (!playlistMode()) return segPath();              /* 旧布局：口径不变 */
        if (k < 0) k = 0;
        if (k >= (int)clips.size()) k = (int)clips.size() - 1;
        const Clip& c = clips[(size_t)k];
        const int i = idx - 1;
        std::string rel;
        if (i >= 0 && i < (int)c.files.size() && !c.files[(size_t)i].empty()) rel = c.files[(size_t)i];
        if (rel.empty()) {
            char b[64];
            snprintf(b, sizeof(b), "%s/seg_%d.mp4", c.name.c_str(), idx);
            rel = b;
        }
        if (!rel.empty() && rel[0] == '/') return rel;       /* 清单里给了绝对路径就用它 */
        return groupDir() + "/" + rel;
    }

    /* ── playlist.json 解析（成功判据：clips>=1 且 Σ clip.dur_ms > 0）── */
    bool loadPlaylist(const std::string& group, int panels, PlaylistInfo* info, std::vector<Clip>* out) const {
        if (info) *info = PlaylistInfo();
        if (out) out->clear();
        if (group.empty()) { if (info) info->why = "empty_group"; return false; }

        const std::string path = wallRoot() + "/" + group + "/playlist.json";
        std::string js;
        if (!readFileAll(path, &js)) {
            if (info) info->why = "no_playlist_json";        /* 旧布局（单 clip）走这条 → 不打 WARN */
            return false;
        }
        rapidjson::Document doc;
        if (doc.Parse(js.c_str()).HasParseError() || !doc.IsObject()) {
            if (info) info->why = "playlist_parse_error";
            ZWLOG(ZW_LOG_WARN, "wall: playlist parse error: %s", path.c_str());
            return false;
        }

        const int version = (int)jLong(doc, "version", 0);
        const int nDecl = (int)jLong(doc, "n", 0);
        const int cols = (int)jLong(doc, "cols", 0);
        const long long totalDecl = jLong(doc, "total_ms", 0);
        if (version != 2)
            ZWLOG(ZW_LOG_WARN, "wall: playlist version=%d (expect 2) -> 按 v2 口径解析: %s", version, path.c_str());
        if (!doc.HasMember("clips") || !doc["clips"].IsArray() || doc["clips"].Size() == 0) {
            if (info) info->why = "no_clips";
            ZWLOG(ZW_LOG_WARN, "wall: playlist has no clips array: %s", path.c_str());
            return false;
        }

        const int fileSlots = (panels > 0) ? panels : 4;
        std::vector<Clip> tmp;
        long long sum = 0;
        int mismatch = 0;
        const rapidjson::Value& arr = doc["clips"];
        for (rapidjson::SizeType i = 0; i < arr.Size(); i++) {
            const rapidjson::Value& cv = arr[i];
            if (!cv.IsObject()) continue;
            Clip cl;
            cl.name = jStr(cv, "name");
            if (cl.name.empty()) {
                char b[16];
                snprintf(b, sizeof(b), "c%u", (unsigned)(i + 1));
                cl.name = b;
            }
            long long d = jLong(cv, "dur_ms", 0);
            cl.files.assign((size_t)fileSlots, std::string());
            long long segMin = 0, segMax = 0;
            bool segSeen = false;
            if (cv.HasMember("segments") && cv["segments"].IsArray()) {
                const rapidjson::Value& segs = cv["segments"];
                for (rapidjson::SizeType j = 0; j < segs.Size(); j++) {
                    const rapidjson::Value& sv = segs[j];
                    if (!sv.IsObject()) continue;
                    const int sIdx = (int)jLong(sv, "index", 0);
                    const std::string f = jStr(sv, "file");
                    const long long sd = jLong(sv, "dur_ms", 0);
                    if (sIdx >= 1 && sIdx <= fileSlots && !f.empty()) cl.files[(size_t)(sIdx - 1)] = f;
                    if (sd > 0) {
                        if (!segSeen) { segMin = segMax = sd; segSeen = true; }
                        else { if (sd < segMin) segMin = sd; if (sd > segMax) segMax = sd; }
                    }
                }
            }
            if (d <= 0) d = segMax;                          /* clip.dur_ms 缺省 → 用段声明时长 */
            if (d <= 0) {
                if (info) info->why = "clip_dur_invalid";
                ZWLOG(ZW_LOG_WARN, "wall: playlist clip[%u] dur_ms invalid -> 退回单 clip 模式: %s",
                      (unsigned)i, path.c_str());
                return false;
            }
            cl.durMs = d;                                    /* ★ 必须回写：时间轴全靠它 */
            tmp.push_back(cl);
            sum += d;
            if (segSeen && (segMax - segMin) > 40) {
                mismatch++;
                ZWLOG(ZW_LOG_WARN, "wall: clip %s 内各段时长不一致 (min=%lld max=%lld ms, clip=%lld ms) -> "
                       "请核对同一切块工具导出的各段等长（只警告，不停播）",
                       cl.name.c_str(), segMin, segMax, d);
            }
        }
        if (tmp.empty() || sum <= 0) {
            if (info) info->why = "clips_invalid";
            ZWLOG(ZW_LOG_WARN, "wall: playlist clips invalid -> 退回单 clip 模式: %s", path.c_str());
            return false;
        }
        if (totalDecl > 0 && (totalDecl - sum > 40 || sum - totalDecl > 40))
            ZWLOG(ZW_LOG_WARN, "wall: playlist total_ms=%lld != Σdur=%lld -> 以 Σdur 为准（%s）",
                  totalDecl, sum, path.c_str());
        if (nDecl > 0 && panels > 0 && nDecl != panels)
            ZWLOG(ZW_LOG_WARN, "wall: playlist n=%d != panels=%d（以配置为准，只警告）", nDecl, panels);

        if (out) *out = tmp;
        if (info) {
            info->ok = true;
            info->version = version;
            info->clips = (int)tmp.size();
            info->cols = cols;
            info->totalMs = sum;
            info->firstClipMs = tmp[0].durMs;
            info->mismatchSegs = mismatch;
            info->why.clear();
        }
        return true;
    }

    /* 零配置：组名/第几屏从**素材路径**推导（<wallRoot>/<组名>/c<k>/seg_<N>.mp4 → 组名 + N） */
    void deriveFromMedia(std::string& group, int& index, int& panels) const {
        std::string s = cfg.mediaHint;
        if (s.size() < 8) return;
        while (!s.empty() && (s[s.size() - 1] == '\n' || s[s.size() - 1] == '\r' || s[s.size() - 1] == ' '))
            s.erase(s.size() - 1);
        size_t wp = s.find("/wall/");
        if (wp == std::string::npos) return;
        size_t g0 = wp + 6;                                  /* "/wall/" 之后 */
        size_t g1 = s.find('/', g0);
        if (g1 == std::string::npos || g1 <= g0) return;
        const std::string g = s.substr(g0, g1 - g0);
        size_t sl = s.rfind('/');
        const std::string base = (sl == std::string::npos) ? s : s.substr(sl + 1);
        int seg = 0;
        size_t sp = base.find("seg_");
        if (sp != std::string::npos) seg = atoi(base.c_str() + sp + 4);
        group = g;
        if (seg > 0) index = seg;                            /* 第几屏 = 推送时选的那一份 */
        if (panels <= 0) panels = 3;
        ZWLOG(ZW_LOG_INFO, "wall: 从素材推导 group=%s idx=%d n=%d (hint=%s)",
              group.c_str(), index, panels, s.c_str());
    }

    /* ── UDP ──────────────────────────────────────────────── */
    bool ensureUdp() {
        if (udpReady) return true;
        fd = socket(AF_INET, SOCK_DGRAM, 0);
        if (fd < 0) {
            ZWLOG(ZW_LOG_ERROR, "wall: socket() failed: %s（下一步：查进程 fd 上限/net 权限）", strerror(errno));
            return false;
        }
        int on = 1;
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on));
        setsockopt(fd, SOL_SOCKET, SO_BROADCAST, &on, sizeof(on));
        struct sockaddr_in a;
        memset(&a, 0, sizeof(a));
        a.sin_family = AF_INET;
        a.sin_port = htons((uint16_t)cfg.udpPort);
        a.sin_addr.s_addr = htonl(INADDR_ANY);
        if (bind(fd, (struct sockaddr*)&a, sizeof(a)) != 0) {
            ZWLOG(ZW_LOG_WARN, "wall: bind %d failed (%s) -> 拼接不可用（下一步：查是否被别的实例占用）",
                  cfg.udpPort, strerror(errno));
            close(fd);
            fd = -1;
            return false;
        }
        int fl = fcntl(fd, F_GETFL, 0);
        fcntl(fd, F_SETFL, fl | O_NONBLOCK);
        udpReady = true;
        return true;
    }

    void sendUdp(const std::string& s) {                     /* 广播（只用于低频发现/兜底） */
        if (!udpReady || fd < 0) return;
        struct sockaddr_in b;
        memset(&b, 0, sizeof(b));
        b.sin_family = AF_INET;
        b.sin_port = htons((uint16_t)cfg.udpPort);
        b.sin_addr.s_addr = htonl(INADDR_BROADCAST);
        sendto(fd, s.c_str(), s.size(), 0, (struct sockaddr*)&b, sizeof(b));
    }

    void sendUdpTo(const std::string& s, unsigned int ip, int port) {
        if (!udpReady || fd < 0 || ip == 0 || port <= 0) return;
        struct sockaddr_in b;
        memset(&b, 0, sizeof(b));
        b.sin_family = AF_INET;
        b.sin_port = htons((uint16_t)port);
        b.sin_addr.s_addr = ip;
        sendto(fd, s.c_str(), s.size(), 0, (struct sockaddr*)&b, sizeof(b));
    }

    /* 主机侧：登记"报活的从机"（收包源地址学得，10s 没动静淘汰） */
    void addPeer(unsigned int ip, int port, long long nowMsVal) {
        if (ip == 0 || port <= 0) return;
        for (size_t i = 0; i < peers.size(); i++) {
            if (peers[i].ip == ip && peers[i].port == port) { peers[i].lastMs = nowMsVal; return; }
        }
        if (peers.size() >= WALL_PEER_MAX) return;
        WallPeer p; p.ip = ip; p.port = port; p.lastMs = nowMsVal;
        peers.push_back(p);
        struct in_addr ia; ia.s_addr = ip;
        ZWLOG(ZW_LOG_INFO, "wall: peer + %s:%d (peers=%d)", inet_ntoa(ia), port, (int)peers.size());
    }

    /* 主机侧：epoch **单播**给名单里的从机（组内不得大量广播） */
    void sendEpochToPeers(const char* payload) {
        if (!master || !udpReady || payload == NULL) return;
        const long long t = nowMsRaw();
        if (t <= 0) return;
        int sent = 0;
        for (size_t i = 0; i < peers.size(); ) {
            if (t - peers[i].lastMs > WALL_LOST_MS) {        /* 10s 没报活 → 淘汰 */
                struct in_addr ia0; ia0.s_addr = peers[i].ip;
                ZWLOG(ZW_LOG_INFO, "wall: peer - %s:%d (silent >%dms)", inet_ntoa(ia0), peers[i].port, WALL_LOST_MS);
                peers.erase(peers.begin() + (long)i);
                continue;
            }
            sendUdpTo(payload, peers[i].ip, peers[i].port);
            sent++;
            i++;
        }
        if (sent == 0 && (heartbeat % 60) == 0)
            ZWLOG(ZW_LOG_DEBUG, "wall: no slave peer yet -> epoch not sent (waiting for their probe)");
    }

    /* 主机：发 epoch（含低频广播兜底，让没配 masterAddr 的从机也能发现主机） */
    void publishEpoch() {
        long long t = nowMsRaw();
        if (t <= 0) return;                                  /* 未校时：不发布（避免垃圾 epoch） */
        if (t0Ms == 0) t0Ms = t;                             /* 主机自己定 epoch（首次） */
        const bool pl = playlistMode();
        const long long pubSeg = pl ? clipDurMs(0) : segMs;
        const long long pubClips = pl ? (long long)clipCount : 0;
        const long long pubTotal = pl ? totalMsVal : 0;
        char b[176];
        snprintf(b, sizeof(b), "wall|%s|%lld|%lld|%d|%lld|%lld|%lld",
                 cfg.group.c_str(), t0Ms, pubSeg, n, t, pubClips, pubTotal);
        sendEpochToPeers(b);                                 /* 单播给本组从机 */
        if (t - lastHbMs >= 3000) {                          /* 每 3s 一包广播（1 包/组，零配置发现） */
            lastHbMs = t;
            sendUdp(b);
        }
    }

    void publishNow() {
        if (!started || !master || !udpReady) return;
        publishEpoch();
    }

    void requestEpoch() {
        /* 从机专用：要一次 epoch（主机收到立刻补发，不等 1s 心跳）。
         * 优先单播给已知主机；地址未知才发一包广播兜底，且 ≥3s 才允许一包。 */
        if (!started || master || !udpReady) return;
        char b[96];
        snprintf(b, sizeof(b), "wall?|%s", cfg.group.c_str());
        if (peerValid) { sendUdpTo(b, peerIp, peerPort); return; }
        const long long tq = nowMsRaw();
        if (tq > 0 && lastAskMs > 0 && (tq - lastAskMs) < 3000) return;
        lastAskMs = tq;
        ZWLOG(ZW_LOG_WARN, "wall: no master addr yet -> one broadcast wall? (throttled >=3s, group=%s)",
              cfg.group.c_str());
        sendUdp(b);
    }

    void pingNow() {
        if (!started || master || !udpReady || !peerValid) return;
        const long long t = nowMsRaw();
        if (t <= 0) return;
        lastPingMs = t;
        char b[64];
        snprintf(b, sizeof(b), "ping|%lld", t);
        sendUdpTo(b, peerIp, peerPort);
    }

    /* 从机 NTP 式双向测时（RTT/2 = 真实钟差；见坑②） */
    void onPong(const char* payload) {
        long long t0 = 0, mnow = 0;
        if (sscanf(payload, "%lld|%lld", &t0, &mnow) != 2) return;
        if (t0 <= 0 || mnow <= 0) return;
        const long long t3 = nowMsRaw();
        const long long rtt = t3 - t0;
        if (rtt < 0 || rtt > 2000) return;                    /* 离谱的丢掉（计时器串了/积压太久） */
        const long long off = (t0 + t3) / 2 - mnow;           /* 本机钟 - 主机钟 */
        if (off > 120000LL || off < -120000LL) { skewDrop++; return; }
        ppRtt[ppIdx % 32] = rtt;
        ppOff[ppIdx % 32] = off;
        ppIdx++;
        if (ppN < 32) ppN++;
        long long bestR = -1, bestO = 0;
        for (int i = 0; i < ppN; i++) {
            if (bestR < 0 || ppRtt[i] < bestR) { bestR = ppRtt[i]; bestO = ppOff[i]; }
        }
        skewMs = (int)bestO;
        skewRttMs = (int)bestR;
        /* 短窗（最近 6 个样本）min-RTT —— 跟随环要"新鲜"，长窗 32 样本滞后又与每秒增益叠加会震荡 */
        fastRtt[fastIdx % 6] = rtt;
        fastOff[fastIdx % 6] = off;
        fastIdx++;
        if (fastN < 6) fastN++;
        {
            long long fR = -1, fO = 0;
            for (int i = 0; i < fastN; i++) {
                if (fR < 0 || fastRtt[i] < fR) { fR = fastRtt[i]; fO = fastOff[i]; }
            }
            fastSkewMs = (int)fO;
            fastRttMs = (int)fR;
        }
        skewFromPp = true;
        skewValid = true;
        lastPongMs = t3;
        pongRecv++;
    }

    void onEpoch(const std::string& payload) {
        /* wall|<组>|<t0>|<seg>|<n>|<pub>[|<clips>|<total>] —— 老主机的可选字段缺失不影响 */
        std::string s = payload;
        while (!s.empty() && (s[s.size() - 1] == '\n' || s[s.size() - 1] == '\r' ||
                              s[s.size() - 1] == ' ')) s.erase(s.size() - 1);
        if (s.compare(0, 5, "wall|") != 0) return;
        size_t p1 = s.find('|', 5);
        if (p1 == std::string::npos) return;
        const std::string grp = s.substr(5, p1 - 5);
        if (grp != cfg.group) return;                          /* 组名不匹配直接丢 */
        size_t p2 = s.find('|', p1 + 1);
        if (p2 == std::string::npos) return;
        size_t p3 = s.find('|', p2 + 1);
        if (p3 == std::string::npos) return;
        const long long t0 = atoll(s.substr(p1 + 1, p2 - p1 - 1).c_str());
        const long long seg = atoll(s.substr(p2 + 1, p3 - p2 - 1).c_str());
        long long pub = 0, rclips = 0, rtotal = 0;
        size_t p4 = s.find('|', p3 + 1);
        if (p4 != std::string::npos) {
            size_t p5 = s.find('|', p4 + 1);
            pub = atoll(s.substr(p4 + 1, (p5 == std::string::npos) ? std::string::npos
                                                                  : p5 - p4 - 1).c_str());
            if (p5 != std::string::npos) {
                size_t p6 = s.find('|', p5 + 1);
                rclips = atoll(s.substr(p5 + 1, (p6 == std::string::npos) ? std::string::npos
                                                                         : p6 - p5 - 1).c_str());
                if (p6 != std::string::npos) rtotal = atoll(s.substr(p6 + 1).c_str());
            }
        }
        const long long rcv = nowMsRaw();
        if (pub > 0 && rcv > 0) {
            /* ⚠️ 不再用单程中值当钟差（坑②）：这里只是**兜底** —— 窗口内最小样本（delay≥0 → 最小最接近真值）。
             * 正常路径是 onPong()（RTT/2）；只有 pong 断 >20s 且差值 ≤250ms 才采用本兜底。 */
            const long long raw = rcv - pub;
            if (raw > 120000LL || raw < -120000LL) {
                skewDrop++;
                ZWLOG(ZW_LOG_WARN, "wall: skew sample %lldms out of +-120s -> dropped (drop=%d, local clock maybe unsynced)",
                      raw, skewDrop);
            } else {
                epochSkewRing[epochSkewIdx % 8] = raw;
                epochSkewIdx++;
                if (epochSkewN < 8) epochSkewN++;
                long long mn = epochSkewRing[0];
                for (int i = 1; i < epochSkewN; i++) if (epochSkewRing[i] < mn) mn = epochSkewRing[i];
                epochSkewMs = mn;
                epochSkewValid = true;
                const long long sincePong = lastPongMs > 0 ? (rcv - lastPongMs) : 999999LL;
                if (!skewValid) {
                    skewMs = (int)epochSkewMs;
                    skewRttMs = -1;
                    skewFromPp = false;
                    skewValid = true;
                } else if (sincePong > 20000 && skewFromPp) {
                    const long long d = mn - (long long)skewMs;
                    if (d <= 250 && d >= -250) {
                        skewMs = (int)epochSkewMs;
                        skewRttMs = -1;
                        skewFromPp = false;
                    }
                }
            }
        }
        /* playlist 模式以**本地清单**为准；广播值不符只 WARN（绝不因它停播），同一值只报一次 */
        remoteClips = rclips;
        remoteTotalMs = rtotal;
        if (playlistMode() && rtotal > 0 && rtotal != totalMsVal) {
            if (warnedRemoteTotal != rtotal) {
                warnedRemoteTotal = rtotal;
                ZWLOG(ZW_LOG_WARN, "wall: 广播 total_ms=%lld != 本地 playlist total_ms=%lld（clips=%lld vs %d）"
                       " -> 以本地清单为准继续播放，请核对各面板是否用同一份清单",
                       rtotal, totalMsVal, rclips, clipCount);
            }
        } else if (playlistMode() && rclips > 0 && rclips != (long long)clipCount) {
            if (warnedRemoteTotal != -2) {
                warnedRemoteTotal = -2;
                ZWLOG(ZW_LOG_WARN, "wall: 广播 clips=%lld != 本地 clips=%d -> 以本地清单为准（请核对清单版本）",
                      rclips, clipCount);
            }
        }
        if (t0 > 0 && (seg >= 1000 || playlistMode())) {
            if (t0Ms != t0)
                ZWLOG(ZW_LOG_DEBUG, "wall: epoch updated t0=%lld seg=%lld clips=%lld total=%lld",
                      t0, seg, rclips, rtotal);
            t0Ms = t0;
            segMs = seg;
            lastRecvMs = rcv;
        }
    }

    /* 一次排空收包（坑③：上限 64，别拿几秒前的旧包当钟差） */
    void drainUdp() {
        if (!udpReady || fd < 0) return;
        char buf[256];
        for (int k = 0; k < WALL_DRAIN_MAX; k++) {
            struct sockaddr_in from;
            socklen_t fl = (socklen_t)sizeof(from);
            memset(&from, 0, sizeof(from));
            const ssize_t nr = recvfrom(fd, buf, sizeof(buf) - 1, 0, (struct sockaddr*)&from, &fl);
            if (nr <= 0) break;
            buf[nr] = '\0';
            if (strncmp(buf, "ping|", 5) == 0) {
                char rb[80];
                const long long t0 = atoll(buf + 5);
                /* 带组名的探针 = 本组从机报活 → 主机登记它（epoch 单播给它） */
                const char* gpos = strchr(buf + 5, '|');
                if (master && gpos != NULL && cfg.group == std::string(gpos + 1))
                    addPeer(from.sin_addr.s_addr, (int)ntohs(from.sin_port), nowMsRaw());
                if (t0 > 0) snprintf(rb, sizeof(rb), "pong|%lld|%lld", t0, nowMsRaw());
                else        snprintf(rb, sizeof(rb), "pong|%lld", nowMsRaw());   /* 无 t0 的探针兼容 */
                sendto(fd, rb, strlen(rb), 0, (struct sockaddr*)&from, fl);
                continue;
            }
            if (strncmp(buf, "pong|", 5) == 0) {
                onPong(buf + 5);
                continue;
            }
            if (strncmp(buf, "wall?", 5) == 0) {
                /* 从机进屏保要 epoch：主机立刻补发（把等待从 ~1s 压到 ms 级） */
                const std::string reqGroup(buf + 5, strnlen(buf + 5, 64));
                if (master && reqGroup == cfg.group) {
                    addPeer(from.sin_addr.s_addr, (int)ntohs(from.sin_port), nowMsRaw());
                    publishEpoch();
                }
                continue;
            }
            if (strncmp(buf, "wall|", 5) == 0) {
                /* 记下源地址 —— 从机据此向主机发双向测时探针 */
                peerIp = from.sin_addr.s_addr;
                peerPort = (int)ntohs(from.sin_port);
                peerValid = true;
            }
            onEpoch(std::string(buf));
        }
    }

    void tick() {
        if (!started || !udpReady) return;
        /* 1) 收包(非阻塞)：ping/pong 测时 + wall?（补发 epoch）+ epoch 本体 */
        drainUdp();
        /* 1.5) 从机每 1s 向主机发一次双向测时探针（pong 回来即得真实钟差） */
        if (!master && peerValid) {
            const long long t = nowMsRaw();
            if (t > 0 && (lastPingMs == 0 || (t - lastPingMs) >= 1000)) {
                lastPingMs = t;
                char b[64];
                snprintf(b, sizeof(b), "ping|%lld|%s", t, cfg.group.c_str());
                sendUdpTo(b, peerIp, peerPort);
            }
        }
        /* 1.55) 主机地址未知 / epoch 陈旧 -> 节流要一次（单播优先，无地址才广播兜底） */
        if (!master) {
            const long long tq = nowMsRaw();
            const bool stale = (lastRecvMs == 0) || (tq > 0 && (tq - lastRecvMs) > 3000);
            if (stale && (tq - lastAskMs) > 3000) { lastAskMs = tq; requestEpoch(); }
        }
        /* 1.6) 组内时钟跟随（可选的业务钩子；真源 = ClockManager）
         *      新鲜 pingpong 样本 → follow；>5s 没样本 → not healthy */
        if (hooks().clockFollowFn != NULL) {
            if (!master) {
                const long long tNow = nowMsRaw();
                const bool ppFresh = (skewValid && skewFromPp && lastPongMs > 0 &&
                                      tNow > 0 && (tNow - lastPongMs) < 5000);
                hooks().clockFollowFn(ppFresh, ppFresh ? fastSkewMs : skewMs, ppFresh ? fastRttMs : skewRttMs,
                                      hooks().clockFollowUser);
            } else {
                hooks().clockFollowFn(false, 0, -1, hooks().clockFollowUser);   /* 主机自己保持 NTP */
            }
        }
        /* 2) 主机每秒心跳（同时修正从机的钟差感知） */
        if (master) {
            heartbeat++;
            publishEpoch();
        }
        /* 3) 起播偏差统计（正文=迟，负=早） */
        if (playStartMs > 0 && lastTargetMs > 0) {
            long long d = playStartMs - lastTargetMs;
            if (d > 32767) d = 32767;
            if (d < -32768) d = -32768;
            driftMs = (int)d;
        }
        /* 4) 每秒一条自证日志（现场排查全靠它） */
        const long long now = nowMsRaw();
        ZWLOG(ZW_LOG_DEBUG,
              "wall tick: now=%lld epoch=%lld seg=%lld phase=%lld wait=%lld next=%lld drift=%d "
              "skew=%d(%s,rtt=%d) ready=%d lost=%d playlist=%d clips=%d total=%lld remote_clips=%lld remote_total=%lld",
              now, t0Ms, segMs, phaseMs(), waitToBoundaryMs(), nextBoundaryMs(), driftMs, skewMs, skewSrc(),
              skewRttMs, readyToPlay() ? 1 : 0,
              (now > 0 && lastRecvMs > 0 && (now - lastRecvMs) > WALL_LOST_MS) ? 1 : 0,
              playlistMode() ? 1 : 0, clipCount, totalMsVal, remoteClips, remoteTotalMs);
    }

    /* ── 时间轴 ───────────────────────────────────────────── */
    long long phaseMs() const {
        if (!hasEpoch()) return 0;
        const long long now = nowMsRaw();
        if (now <= 0) return 0;
        long long d = now - t0Ms;
        if (d < 0) d = 0;
        return d % periodMs();
    }
    bool hasEpoch() const { return t0Ms > 0; }
    /* 下一个整边界的**绝对墙钟**：两台同一 epoch + 同一公式 → 同一时刻（不靠互发开始信令） */
    long long nextBoundaryMs() const {
        if (!hasEpoch()) return 0;
        const long long now = nowMsRaw();
        if (now <= 0) return 0;
        long long d = now - t0Ms;
        if (d < 0) d = 0;
        const long long per = periodMs();
        return t0Ms + (d / per + 1) * per;
    }
    long long waitToBoundaryMs() const {
        if (!hasEpoch()) return 0;
        const long long per = periodMs();
        const long long ph = phaseMs();
        long long w = per - ph;
        if (w <= 0 || w > per) w = per;
        return w;
    }
    bool readyToPlay() const {
        if (!started) return false;
        if (master && t0Ms == 0) return false;
        if (!hasEpoch()) return false;
        const long long now = nowMsRaw();
        if (now > 0 && lastRecvMs > 0 && (now - lastRecvMs) > WALL_LOST_MS) return false;   /* 从机失联 */
        return true;
    }
    bool clockPlausible() const {
        /* 2024-01-01 00:00:00 UTC = 1704067200000ms：比这早 = 掉电后/未校时（RTC 空 → 1970） */
        const long long t = nowMsRaw();
        return t > 1704067200000LL;
    }
    const char* skewSrc() const { return skewFromPp ? "pingpong" : "epoch"; }

    std::string stateText() const {
        if (!started) return "未开启";
        if (!hasEpoch()) return master ? "初始化中" : "等待主机 epoch";
        const long long now = nowMsRaw();
        const bool lost = (now > 0 && lastRecvMs > 0 && (now - lastRecvMs) > WALL_LOST_MS);
        if (lost) return "失联（已回普通屏保）";
        char b[128];
        if (master) {
            if (playlistMode()) snprintf(b, sizeof(b), "主机 · seg_%d/%d · %d段轮播", idx, n, clipCount);
            else snprintf(b, sizeof(b), "主机 · seg_%d/%d · 已发 epoch", idx, n);
        } else {
            if (playlistMode()) snprintf(b, sizeof(b), "从机 · seg_%d/%d · %d段轮播 · 偏差 %+dms",
                                         idx, n, clipCount, driftMs);
            else snprintf(b, sizeof(b), "从机 · seg_%d/%d · 偏差 %+dms", idx, n, driftMs);
        }
        return b;
    }
};

/* ═════════════════ Sync 外观 ═════════════════ */

Sync::Sync() : impl_(new Impl()) {}

Sync::~Sync() {
    stop();
    delete impl_;
}

Sync& Sync::instance() {
    static Sync s;
    return s;
}

Result Sync::start(const SyncConfig& cfg) {
    Impl* im = impl_;
    im->cfg = cfg;
    hooks().logFn = cfg.logFn;       hooks().logUser = cfg.logUser;
    hooks().nowFn = cfg.nowFn;       hooks().nowUser = cfg.nowUser;
    hooks().clockFollowFn = cfg.clockFollowFn;
    hooks().clockFollowUser = cfg.clockFollowUser;

    /* ── 零配置口径：优先按素材路径推导组名/序号；显式值仍作兜底 ── */
    std::string g = cfg.group;
    int ix = cfg.index;
    int nn = cfg.panels;
    im->deriveFromMedia(g, ix, nn);
    if (g.empty()) g = "zksw-wall";
    if (ix < 1) ix = 1;
    if (nn < 1) nn = 2;

    im->master = (cfg.role < 0) ? (ix == 1) : (cfg.role != 0);
    if (cfg.role < 0)
        ZWLOG(ZW_LOG_INFO, "wall: role 未显式配置 -> 按「第 1 屏为主机」判定 master=%d (idx=%d)",
              im->master ? 1 : 0, ix);

    im->idx = ix;
    im->n = nn;
    im->segMs = cfg.segMs;
    im->leadMs = cfg.leadMs;

    /* 主机地址解析（从机全程单播；没配 → 等主机低频广播发现，之后学源地址） */
    {
        unsigned int ip = 0;
        int port = cfg.udpPort > 0 ? cfg.udpPort : 8901;
        const std::string& peer = cfg.masterAddr;
        std::string host = peer;
        if (!peer.empty()) {
            size_t c = peer.find(':');
            if (c != std::string::npos) {
                host = peer.substr(0, c);
                const int p2 = atoi(peer.substr(c + 1).c_str());
                if (p2 > 0) port = p2;
            }
            struct in_addr ia;
            if (inet_aton(host.c_str(), &ia) != 0) ip = ia.s_addr;
        }
        im->cfgMasterPort = port;
        if (!im->master && ip != 0) { im->peerIp = ip; im->peerPort = port; im->peerValid = true; }
        ZWLOG(ZW_LOG_INFO, "wall: unicast cfg masterAddr=\"%s\" master=%s:%d mode=%s",
              peer.c_str(), ip ? host.c_str() : "(none)", port,
              (ip != 0) ? "unicast" : (!im->master ? "broadcast-fallback(>=3s,only when epoch stale)" : "master"));
    }

    /* 钳制（与真源一致；越界一律收敛而不是报错停机） */
    if (im->idx < 1) im->idx = 1;
    if (im->n < 2 || im->n > 4) im->n = 2;
    im->cfg.index = im->idx;            /* 回写：派生后的一致口径（Player 读它挑文件） */
    im->cfg.panels = im->n;
    if (im->segMs < 1000) im->segMs = 30000;
    im->cfg.segMs = im->segMs;
    if (im->leadMs < 0 || im->leadMs > 2000) im->leadMs = 0;
    im->cfg.leadMs = im->leadMs;

    /* ── playlist.json（多视频轮播）：有且合法 → playlist 模式；无/非法 → 旧布局单 clip ── */
    {
        PlaylistInfo pi;
        std::vector<Impl::Clip> clips;
        if (im->loadPlaylist(im->cfg.group, im->n, &pi, &clips)) {
            im->clips.swap(clips);
            im->clipCount = pi.clips;
            im->totalMsVal = pi.totalMs;
            ZWLOG(ZW_LOG_INFO, "wall: playlist mode group=%s clips=%d total=%lldms first=%lldms cols=%d segsMismatch=%d",
                  im->cfg.group.c_str(), im->clipCount, im->totalMsVal, pi.firstClipMs, pi.cols, pi.mismatchSegs);
        } else {
            im->clips.clear();
            im->clipCount = 0;
            im->totalMsVal = 0;
            if (!pi.why.empty() && pi.why != "no_playlist_json")
                ZWLOG(ZW_LOG_WARN, "wall: playlist unusable (%s) -> 退回单 clip 模式", pi.why.c_str());
        }
    }

    im->started = cfg.enabled;
    if (!cfg.enabled) {
        ZWLOG(ZW_LOG_DEBUG, "wall: disabled (playlist=%d clips=%d)",
              im->playlistMode() ? 1 : 0, im->clipCount);
        return Result(ZW_OK, "拼接已配置但未启用");
    }
    if (im->ensureUdp()) {
        ZWLOG(ZW_LOG_DEBUG, "wall: enabled group=%s idx=%d/%d master=%d seg=%lldms lead=%dms udp=%d playlist=%d clips=%d total=%lldms",
              im->cfg.group.c_str(), im->idx, im->n, im->master ? 1 : 0, im->segMs, im->leadMs,
              im->udpReady ? 1 : 0, im->playlistMode() ? 1 : 0, im->clipCount, im->totalMsVal);
        if (im->master) im->publishEpoch();
        return Result(ZW_OK, "拼接已启用");
    }
    return Result(ZW_EIO, "UDP 绑定失败：拼接不可用（查端口是否被占用 / 是否有网络权限）");
}

void Sync::stop() {
    Impl* im = impl_;
    if (im->fd >= 0) {
        close(im->fd);
        im->fd = -1;
    }
    im->udpReady = false;
    im->started = false;
    im->t0Ms = 0;
    im->peers.clear();
    ZWLOG(ZW_LOG_DEBUG, "wall: stopped");
}

void Sync::tick()  { impl_->tick(); }
void Sync::poll()  { impl_->drainUdp(); }
void Sync::publishNow()  { impl_->publishNow(); }
void Sync::requestEpoch() { impl_->requestEpoch(); }
void Sync::pingNow()     { impl_->pingNow(); }

bool Sync::enabled() const      { return impl_->started; }
bool Sync::isMaster() const     { return impl_->started && impl_->master; }
int  Sync::segIndex() const     { return impl_->idx; }
int  Sync::panelCount() const   { return impl_->n; }
std::string Sync::group() const { return impl_->cfg.group; }
std::string Sync::segPath() const { return impl_->segPath(); }
long long Sync::segMs() const   { return impl_->segMs; }
int Sync::leadMs() const        { return impl_->leadMs; }

bool Sync::readyToPlay() const  { return impl_->readyToPlay(); }
bool Sync::hasEpoch() const     { return impl_->hasEpoch(); }
long long Sync::epochMs() const { return impl_->t0Ms; }
long long Sync::phaseMs() const { return impl_->phaseMs(); }
long long Sync::waitToBoundaryMs() const { return impl_->waitToBoundaryMs(); }
long long Sync::nextBoundaryMs() const   { return impl_->nextBoundaryMs(); }
long long Sync::driftMs() const { return impl_->driftMs; }
void Sync::markPlayStarted(long long targetMs) {
    impl_->playStartMs = nowMsRaw();
    impl_->lastTargetMs = targetMs;
}
std::string Sync::stateText() const { return impl_->stateText(); }

int Sync::skewMs() const        { return impl_->skewMs; }
int Sync::skewRttMs() const     { return impl_->skewRttMs; }
const char* Sync::skewSrc() const { return impl_->skewSrc(); }
bool Sync::skewValid() const    { return impl_->skewValid; }
bool Sync::clockPlausible() const { return impl_->clockPlausible(); }

long long Sync::nowMs() { return nowMsRaw(); }

bool Sync::waitUntil(long long deadlineMs) {
    /* 精等到 deadline：≤4ms 分片轮询（单次 usleep(几百 ms) 实测会超时 10~30ms -> 起播相位抖动）。
     * 为什么不能只靠 1s 心跳：各机心跳相位不同，只能做到 ±1s，而目标是 ≤40ms（1 帧 @25fps）。 */
    for (int i = 0; i < 40000; i++) {                 /* 硬上限：防时钟跳变死等 */
        const long long n = nowMsRaw();
        if (n <= 0) return false;
        const long long d = deadlineMs - n;
        if (d <= 0) return true;
        if (d > 1600) return false;                   /* 不该发生：宁可不等也不阻塞 UI */
        if (d > 4) usleep(4000);
        else if (d > 1) usleep((useconds_t)((d - 1) * 1000));
        else usleep(200);
    }
    return false;
}

bool Sync::queryPlaylist(const std::string& group, int panels, PlaylistInfo* out) const {
    std::vector<Impl::Clip> clips;
    return impl_->loadPlaylist(group, panels, out, &clips);
}

std::vector<std::string> Sync::listGroups() const {
    std::vector<std::string> out;
    const std::string root = impl_->wallRoot();
    DIR* dp = opendir(root.c_str());
    if (dp == NULL) return out;                       /* 目录不存在 = 空列表（业务给"未找到组目录"提示） */
    struct dirent* ent = NULL;
    while ((ent = readdir(dp)) != NULL) {
        const std::string nm = ent->d_name;
        if (nm.empty() || nm == "." || nm == ".." || nm[0] == '.') continue;
        const std::string full = root + "/" + nm;
        struct stat st;
        memset(&st, 0, sizeof(st));
        if (stat(full.c_str(), &st) != 0 || !S_ISDIR(st.st_mode)) continue;
        out.push_back(nm);
    }
    closedir(dp);
    std::sort(out.begin(), out.end());
    return out;
}

std::string Sync::wallRoot() const { return impl_->wallRoot(); }

bool Sync::playlistMode() const  { return impl_->playlistMode(); }
int Sync::clipCount() const      { return impl_->clipCount; }
long long Sync::clipDurMs(int k) const   { return impl_->clipDurMs(k); }
long long Sync::clipStartMs(int k) const { return impl_->clipStartMs(k); }
long long Sync::totalMs() const  { return impl_->totalMsVal; }
long long Sync::periodMs() const { return impl_->periodMs(); }
bool Sync::clipAt(long long groupTimeMs, int* k, long long* offMs) const {
    return impl_->clipAt(groupTimeMs, k, offMs);
}
std::string Sync::groupDir() const     { return impl_->groupDir(); }
std::string Sync::playlistPath() const { return impl_->playlistPath(); }
std::string Sync::segPathForClip(int k) const { return impl_->segPathForClip(k); }
std::string Sync::playKey() const      { return impl_->playKey(); }

} /* namespace wall */
} /* namespace zk */
