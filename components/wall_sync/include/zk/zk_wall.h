/* =====================================================================
 * zk_wall.h —— 多屏拼接 / 视频墙「跨设备同步」唯一对外头（zk::wall）
 *
 * 是什么：
 *   N 块（≤4，单行横排 1xN）同型号面板拼一面墙，播放**同一素材的各自那一格**，
 *   要求"同一时刻同一帧"。本组件给出两件事：
 *     ① Sync   —— 组网/校时/时间轴内核：UDP 自组网（无服务器）+ 主机广播 epoch +
 *                 双向测时（ping/pong, RTT/2）算真实钟差 + 整边界（栅格）定标 +
 *                 playlist.json 多 clip 轮播清单（组内时间 g → 第几个 clip + 段内偏移）。
 *     ② Player —— 相位驱动内核：每一轮按"组内时间栅格"挑**本机那一格**的文件，
 *                 交给**注入的播放引擎**（Engine）持续送流；引擎在跑就代表相位已被接管，
 *                 外层只做"该起就起 / 该停就停"。
 *
 * 不是什么：
 *   · **不含解码/上屏引擎**。解码那一层（Z20 上 = 官方包 simple-player 的 SimplePlayer，
 *     MI VDEC + MI DISP）通过 Engine 接口注入；本组件不泄漏任何底层类型（无 MI_/simple_player.h/ffmpeg 符号）。
 *   · **不含 UI**（不依赖 easyui 控件、不读写项目的配置存储、不管屏保页生命周期）。
 *     配置从构造入参进；配置存储/UI 接线见 example/flythings_wiring.cc。
 *   · 不含素材切分工具（把源视频切成每屏一格的 `seg_<N>.mp4` + `playlist.json`）。
 *
 * 口径与实测数字来源（本头不编数字）：
 *   · knowledge/devflow/video-wall-sync.md（本仓知识库）
 *   · references/kb/video-wall-sync.md（workspace 主源）
 *   · projects/SmartPanel_HA/docs/说明书-多屏拼接.md（产品说明书）
 *   落地来源：projects/SmartPanel_HA/src/wall/{WallLink.*, WallPlayer.*}（真机验证版）
 *
 * 线程模型（重要）：
 *   · Sync：**非线程安全**，只在调用者自己的线程上跑（真源 = UI 主线程的 1s 定时器：
 *     工程里 tick() 与 poll()/requestEpoch()/pingNow() 都在主线程调）。
 *   · Player：start() 起**一条内部线程**持续调 Engine::play()；stop() 会 join 该线程。
 *     Engine::play()/stop()/open() 都在这条 Player 线程上被调（stop() 例外：它从调用者线程
 *     直接调 Engine::stop() 去打断阻塞的 play()，跟着再 join）。
 *   · 回调：`LogFn` / `NowMsFn` / `ClockFollowFn` 都在**同步调用它的那条线程**上被调（Sync 回调=调用线程，
 *     Player 内部日志=Player 线程）；回调里**不要**再回调 Sync/Player 的写接口（会重入）。
 *
 * 依赖：C++11；libc + POSIX socket（设备端）；rapidjson（仅解析 playlist.json，见 Manifest.xml）。
 * 版本：1.0.0（2026-09-30 入库；来源 = SmartPanel_HA 现网多屏拼接实现 v7.13 口径）
 * ===================================================================== */
#ifndef ZK_WALL_H
#define ZK_WALL_H

#include <stdint.h>
#include <string>
#include <vector>

namespace zk {
namespace wall {

/* ── 统一结果类型（规范 §2.2：msg 必须是人话，禁止只回 -1 / 禁止静默失败）── */
struct Result {
    int code;           /**< 0 = 成功，非 0 见 ResultCode */
    std::string msg;    /**< 人话；失败时必须写清"下一步查什么" */
    Result() : code(0) {}
    Result(int c, const std::string& m) : code(c), msg(m) {}
    bool ok() const { return code == 0; }
};

enum ResultCode {
    ZW_OK = 0,
    ZW_EINVAL = 1,      /**< 参数非法（组名空/序号越界/矩形为空…） */
    ZW_ENOT_READY = 2,  /**< 还没有 epoch / 失联 / 时钟不可信 */
    ZW_EIO = 3,         /**< 网络/文件 IO 失败 */
    ZW_ENO_ENGINE = 4   /**< 没设播放引擎就 start() */
};

enum LogLevel { ZW_LOG_DEBUG = 0, ZW_LOG_INFO = 1, ZW_LOG_WARN = 2, ZW_LOG_ERROR = 3 };

/** 日志钩子（可选）。真源用工程的 LOGD/LOGW；app 模式下 stdout 是 /dev/null，现场排错必须接出来。 */
typedef void (*LogFn)(int level, const char* msg, void* user);

/** 墙钟毫秒钩子（可选）。不设 = 组件内用 clock_gettime(CLOCK_REALTIME)（毫秒分辨率）。
 *  ⚠️ 必须是**绝对墙钟毫秒**（> 1e12）；秒级分辨率会让相位永远收敛不到 1 帧（真源踩过）。 */
typedef long long (*NowMsFn)(void* user);

/** 组内时钟跟随钩子（可选）。从机双向测时拿到"新鲜样本"时回调，业务把它喂给自己的校时/时钟管理器
 *  （真源 = ClockManager::setGroupHealthy()/groupFollow()）。不用系统校时的话不设即可。 */
typedef void (*ClockFollowFn)(bool healthy, int skewMs, int rttMs, void* user);

/* ── 几何（只用到输出矩形，不含任何平台类型）── */
struct Rect {
    int x, y, w, h;
    Rect() : x(0), y(0), w(0), h(0) {}
    Rect(int X, int Y, int W, int H) : x(X), y(Y), w(W), h(H) {}
};

/* =====================================================================
 * Sync —— 组网 / 校时 / 时间轴内核
 * ===================================================================== */

struct SyncConfig {
    /** 拼接总开关。false = 内核不起 UDP、不下发任何包（业务照常走普通轮播）。 */
    bool enabled;
    /** 组名。同组才互认（收到别的组的包一律丢弃）。默认 "zksw-wall"。
     *  也是素材目录名：<wallRoot>/<group>/ */
    std::string group;
    /** 本机序号 1..panels（唯一；决定播 seg_<序号>.mp4 与格子位置）。 */
    int index;
    /** 总屏数 2..4（单行横排 1xN；>4 或 <2 会被钳到 2）。 */
    int panels;
    /** 角色：-1 = 自动（index==1 当主机）；1 = 强制主机；0 = 强制从机。
     *  ⚠️ 两台都当主机会互相打架（真源 §配置键表）。 */
    int role;
    /** 片段时长 ms（单 clip 模式**必须 = 素材真实时长**；多 clip 模式以清单 total_ms 为准，本值只作兜底）。 */
    long long segMs;
    /** 起播提前量 ms（补偿引擎起播延迟）。0 = 内容零截断（推荐，真源默认 0）。 */
    int leadMs;
    /** 从机专用：主机地址 "ip" 或 "ip:port"（真源 prefs sp_wall_peer）。
     *  给了就走**全程单播**（不广播）；空 = 未知，等主机低频广播发现，之后学源地址。 */
    std::string masterAddr;
    /** 素材根目录。默认 "/mnt/sdnand/wall"（设备盘；真源组网清单也在盘上）。 */
    std::string wallRoot;
    /** 零配置提示（可选）：本机素材的完整路径，形如 <wallRoot>/<组名>/c<k>/seg_<N>.mp4。
     *  给了就能**推导**出组名/本机序号（省掉两个配置项）；空 = 用上面显式配置。 */
    std::string mediaHint;
    /** UDP 端口。默认 8901。 */
    int udpPort;
    /** 进屏保"等 epoch"超时 ms（超时用本机时间兜底 + WARN，绝不卡画面）。默认 5000。 */
    int joinTimeoutMs;
    /** 多 clip 模式的**绝对栅格锚点**（ms 墙钟；真源方案 B：各屏都用本机 NTP 时间，
     *  锚点是个常数 → 同一时刻算出同一 clip，播放相位零网络）。默认 0。 */
    long long gridAnchorMs;

    /** 回调（都可为 NULL） */
    LogFn logFn; void* logUser;
    NowMsFn nowFn; void* nowUser;
    ClockFollowFn clockFollowFn; void* clockFollowUser;

    SyncConfig()
        : enabled(false), group("zksw-wall"), index(1), panels(2), role(-1),
          segMs(30000), leadMs(0), masterAddr(), wallRoot("/mnt/sdnand/wall"),
          mediaHint(), udpPort(8901), joinTimeoutMs(5000), gridAnchorMs(0),
          logFn(NULL), logUser(NULL), nowFn(NULL), nowUser(NULL),
          clockFollowFn(NULL), clockFollowUser(NULL) {}
};

/** playlist.json（一组多视频轮播）的统计信息（设置页/日志用；不改动内部播放状态）。 */
struct PlaylistInfo {
    bool ok;                /**< true = 该组可用 playlist 模式 */
    int version;            /**< 清单 version（期望 2） */
    int clips;              /**< clip 数 K */
    int cols;               /**< 排布列数（切块工具写，仅展示/诊断） */
    long long totalMs;      /**< 总时长 = Σ clip.dur_ms */
    long long firstClipMs;  /**< 第 1 个 clip 时长（= 广播 seg_ms 字段口径） */
    int mismatchSegs;       /**< 同一 clip 内各段声明时长不一致的 clip 数（WARN 口径，>40ms 才计） */
    std::string why;        /**< 未进入 playlist 模式的原因（no_playlist_json / playlist_parse_error …） */
    PlaylistInfo()
        : ok(false), version(0), clips(0), cols(0), totalMs(0), firstClipMs(0),
          mismatchSegs(0), why() {}
};

class Sync {
public:
    /** 单例（真源语义：全进程只有一个 UDP 8901 监听/一个 epoch 状态机）。 */
    static Sync& instance();

    /* ── 生命周期 ─────────────────────────────────────────────── */
    /** 起/重载配置（**幂等**：UDP 通道已起就不重复 bind；主机侧重发一次 epoch 无害）。
     *  失败也给 msg（例如端口被占）；不阻塞。 */
    Result start(const SyncConfig& cfg);
    /** 关闭（关拼接 / 退出应用）。幂等。 */
    void stop();

    /* ── 心跳（业务在主线程每秒调一次）─────────────────────────── */
    /** 1s 心跳：收包 → 从机发双向测时探针 → 从机判断"该要 epoch 了" → 主机发 epoch
     *  → 统计起播偏差 drift → 打一条诊断日志。 */
    void tick();
    /** 立刻排空一次收包（不等 1s 心跳）。可从其它线程调（真源：播放线程 join 前用）。 */
    void poll();

    /* ── 进屏保快通道 ─────────────────────────────────────────── */
    /** 主机：立刻（重）发一次 epoch（从机则空操作）。进屏保时调用。 */
    void publishNow();
    /** 从机：广播/单播一次 "wall?|<组>"，请主机立刻补发 epoch（把等待从 1s 压到 ms 级）。 */
    void requestEpoch();
    /** 从机：立刻发一次双向测时探针（join 前先把钟差量准，不等 1s 节流）。 */
    void pingNow();

    /* ── 状态（业务/状态页读）──────────────────────────────────── */
    bool enabled() const;
    bool isMaster() const;
    int segIndex() const;
    int panelCount() const;
    std::string group() const;
    /** 本机那一格的路径（旧布局：<组目录>/seg_<idx>.mp4）。 */
    std::string segPath() const;
    long long segMs() const;
    int leadMs() const;
    /** 已启用 && 有 epoch && 未失联（>10s 收不到 epoch 即判失联，业务应回退普通轮播）。 */
    bool readyToPlay() const;
    bool hasEpoch() const;
    long long epochMs() const;              /**< 本轮循环起点墙钟（主机定的绝对时刻） */
    long long phaseMs() const;              /**< 当前应在段内的位置 */
    long long waitToBoundaryMs() const;     /**< 距下一个整边界还有多久 */
    long long nextBoundaryMs() const;       /**< 下一个整边界的**绝对墙钟 ms**（两台同式 = 同一时刻） */
    long long driftMs() const;              /**< 上次实测起播偏差（正文=迟于目标；负=早于目标） */
    void markPlayStarted(long long targetMs);/**< 起播时记录（target = 本次对齐的整边界墙钟） */
    std::string stateText() const;          /**< 给人看的一行状态（状态页直接用） */

    /* ── 钟差（真实钟差 = 双向测时 RTT/2；失败才退到 epoch 单程兜底）── */
    int skewMs() const;                     /**< 本机钟 − 主机钟 */
    int skewRttMs() const;                  /**< 最佳样本的往返时间（越小越可信；-1 = 单程兜底） */
    const char* skewSrc() const;            /**< "pingpong" / "epoch" */
    bool skewValid() const;
    /** 本机墙钟是否可信（>= 2024-01-01 UTC）。掉电后 RTC 空、未校时时 false ——
     *  此时**不要**起播（真源守卫：wall_clock_not_set / clock_insane）。 */
    bool clockPlausible() const;

    /* ── 时间原语 ─────────────────────────────────────────────── */
    /** 墙钟毫秒（有 nowFn 则用业务给的，否则 clock_gettime(CLOCK_REALTIME)）。 */
    static long long nowMs();
    /** 精等到 deadline（毫秒级）：≤4ms 分片轮询（单次 usleep(几百 ms) 实测会超时 10~30ms，
     *  直接变成起播相位抖动）。只在临近起播时调，单次阻塞 ≤1600ms，时钟跳变也不会死等。 */
    static bool waitUntil(long long deadlineMs);

    /* ── playlist.json（一组多视频轮播）───────────────────────── */
    /** 查询某个组目录的清单统计（**不改内部播放状态**，可对任意组名查询）。 */
    bool queryPlaylist(const std::string& group, int panels, PlaylistInfo* out) const;
    /** 扫 <wallRoot> 下真实存在的组目录（名称序）。业务用它做"组名在设备上循环"。 */
    std::vector<std::string> listGroups() const;
    /** 素材根目录（= 配置的 wallRoot）。 */
    std::string wallRoot() const;

    bool playlistMode() const;              /**< 多 clip 模式（清单可用）*/
    int clipCount() const;                  /**< 单 clip 模式 = 0 */
    long long clipDurMs(int k) const;       /**< 0-based；越界返回 0 */
    long long clipStartMs(int k) const;     /**< 第 k 个 clip 相对轮起点的偏移 */
    long long totalMs() const;              /**< playlist 总时长（单 clip 模式 = 0） */
    long long periodMs() const;             /**< 时间轴周期：playlist = total，单 clip = segMs */
    /** 组内时间 g → (clip k, 段内偏移 off)；单 clip 模式返回 false（调用方按老口径走）。 */
    bool clipAt(long long groupTimeMs, int* k, long long* offMs) const;
    std::string groupDir() const;           /**< <wallRoot>/<组名> */
    std::string playlistPath() const;       /**< <组目录>/playlist.json */
    /** 第 k 个 clip 下**本机那一格**的绝对路径（清单缺项 → 用 c<k>/seg_<idx>.mp4 兜底）。 */
    std::string segPathForClip(int k) const;
    /** 播放器"当前节目"键（**换键才重开播放器**）：
     *  playlist 模式 = <组目录>/playlist.json（稳定，clip 切换由 Player 内部处理）；
     *  单 clip 模式 = seg_<idx>.mp4。 */
    std::string playKey() const;

private:
    Sync();
    ~Sync();
    Sync(const Sync&);
    Sync& operator=(const Sync&);
    struct Impl;
    Impl* impl_;
};

/* =====================================================================
 * Engine —— 播放引擎（**业务注入**：解码 + 上屏那一层）
 *
 * 参考实现（Z20）：官方包 simple-player 的 SimplePlayer（MI VDEC + MI DISP 硬解送显）
 *   —— 现场验证过的那套；见 example/flythings_wiring.cc 的 ZkSimplePlayerEngine。
 * 只要你自己的播放器满足下面语义，本组件不关心它是什么。
 * ===================================================================== */

struct EngineConfig {
    /** 引擎自带对齐开关（真源 simple-player：setSynchronizing(true)）。
     *  ⚠️ 引擎的对齐口径是"本机绝对钟 % (时长+解析耗时)"，各机钟必须一致才成立
     *  —— 本组件的 Sync（NTP 校时 + 从机跟随）就是为满足这个前提。 */
    bool synchronize;
    /** 画面旋转角（度；多台必须统一）。0 = 不旋转。 */
    int rotateDeg;
    /** 参考实现用到的 MI 通道对（引擎自己的事；本组件只是透传，不解释）。 */
    int vdecChannel;
    int dispChannel;
    void* user;
    EngineConfig() : synchronize(true), rotateDeg(0), vdecChannel(1), dispChannel(1), user(NULL) {}
};

class Engine {
public:
    virtual ~Engine() {}
    /** 一次性初始化（旋转/通道/同步开关）。在 Player 线程上、play() 之前调一次。 */
    virtual bool open(const EngineConfig& cfg) = 0;
    /** **阻塞**播放一个文件，读到 EOF 或被 stop() 打断才返回。
     *  返回 false = 失败（Player 会 1s 后重试并记 lastError()）。 */
    virtual bool play(const std::string& file, const Rect& rect) = 0;
    /** 从**别的线程**打断阻塞中的 play()（真源：SimplePlayer::stop()）。 */
    virtual void stop() = 0;
    /** 引擎名（日志用）。 */
    virtual const char* name() const = 0;
};

/* =====================================================================
 * Player —— 相位驱动内核（选片 + 起停；相位由 Engine 接管）
 * ===================================================================== */

struct PlayerConfig {
    /** 输出矩形（屏保全屏口径） */
    Rect rect;
    /** 引擎配置（旋转/通道/同步开关） */
    EngineConfig engine;
    /** 无 epoch/时钟不可信时的**本地兜底文件**（真源 prefs sp_video_sel）。
     *  空 = 用 playlist 第 0 段。 */
    std::string fallbackFile;
    /** 边界预热踩点提前量 ms（真源 sp_wall_start_lead_ms / 默认 150）：离整边界还早时先排队，
     *  到「边界 − lead」才拉起引擎，让第一帧正好落在整边界（引擎无 seek API 时的替代做法）。
     *  ≤0 = 不踩点（立即起播，等价老行为）。 */
    int startLeadMs;
    /** 多 clip 栅格锚点 ms（真源方案 B sp_wall_anchor_ms；0 = 用 Sync 的 epoch 网格）。 */
    long long gridAnchorMs;

    PlayerConfig() : rect(0, 0, 0, 0), engine(), fallbackFile(), startLeadMs(150), gridAnchorMs(0) {}
};

class Player {
public:
    static Player& instance();

    /** 注入播放引擎（必须在 start() 之前；引擎生命周期由业务负责）。 */
    void setEngine(Engine* engine);
    /** 设默认配置（矩形/旋转/踩点/兜底文件）。可在 start() 前或运行期调（运行期改矩形要重启）。 */
    void configure(const PlayerConfig& cfg);
    const PlayerConfig& config() const;

    /** 异步起播：内部线程持续送流到 stop()。
     *  @param playKey = Sync::playKey()（换键才重开；已在播同一个键 → 直接返回 ok）。
     *  playlist 模式下 Player 每轮**自己重挑当前 clip 的本机那一格**。 */
    Result start(const std::string& playKey);
    /** 停播（打断引擎并 join 线程）。幂等。 */
    void stop();
    bool running() const;
    std::string currentFile() const;        /**< 当前实际在播的文件 */

    /* ── 诊断快照（1s 心跳打印 / 现场对账）── */
    long long periodMs() const;             /**< 本轮周期：playlist = Σclip.dur，单 clip = Sync::segMs() */
    long long anchorMs() const;             /**< 当前轮起点（绝对墙钟 ms）；无 epoch = -1 */
    long long beginMs() const;              /**< 当前应在段内的位置；无 epoch = -1 */
    int cycles() const;                     /**< 已完成的 play() 轮数 */
    int clipIndex() const;                  /**< 当前在播的 clip 序号（0-based；单 clip 恒 0） */
    int clipCount() const;                  /**< 本节目 clip 数（单 clip = 1） */
    std::string clipFile() const;           /**< 当前实际在播的文件（随 clip 切换） */
    bool locked() const;                    /**< 引擎在跑且没出错 = "格子对齐已接管" */
    std::string lastError() const;          /**< 最近一次引擎异常（空 = 没出错） */

    /* ⚠️ 下面四个量在"引擎接管"后**不由本组件测量** → 一律 -1（n/a），不要当 0 用。
     *    （真源：改用官方播放器包后这些自证量消失，日志里用 pkg=1 标记） */
    long long lastPtsMs() const;
    long long lastWantMs() const;
    long long lastNowMs() const;
    long long lastErrMs() const;

private:
    Player();
    ~Player();
    Player(const Player&);
    Player& operator=(const Player&);
    struct Impl;
    Impl* impl_;
};

} /* namespace wall */
} /* namespace zk */

#endif /* ZK_WALL_H */
