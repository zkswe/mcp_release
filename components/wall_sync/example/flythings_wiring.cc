/* =====================================================================
 * flythings_wiring.cc —— FlyThings 工程接线（把 components/wall_sync 接进一个真实工程）
 *
 * 落地来源：projects/SmartPanel_HA 的
 *   · src/logic/mainLogic.cc（屏保页 1s 定时器里的起停 + 总闸 + 400ms 沉降 + 日志口径）
 *   · src/logic/wallLogic.cc（设置页读写配置；本文件不搬 UI，只示范配置怎么进 SyncConfig）
 *   · src/system/* ClockManager（组内时钟跟随）
 * 本文件是**代码样板**（拷进工程后按自己的类名/页名改），不是组件的一部分：
 *   组件本身不含任何 easyui / 工程符号。
 *
 * 接线要点（照做即可，都是踩出来的）：
 *   1) 配置从 prefs 读一次组装 SyncConfig（键名沿用 sp_wall_*，见 README 配置表）。
 *   2) 引擎 = 官方包 simple-player 的 SimplePlayer（包里有格子对齐；本工程只选片+起停）。
 *   3) **总闸**：simple 引擎模式下，所有 easyui ZKVideoView 的起播路径直接 return
 *      —— 两个内核抢 MI 图层会把 disp 图层任务卡死（表现 = 屏保画面冻住不动）。
 *   4) 停 easyui 播放器后要**沉降 400ms** 再起引擎（MI 图层拆解是异步的）。
 *   5) 拼接**只在屏保页生效**：进主页/设置页要显式停（本组件不做页面判断）。
 *   6) 真实工程的 easyui 播放器控件（`mVideoSsPtr` / `mImageSsBgPtr`）与 `SS_SCR_W/SS_SCR_H`
 *      **本文件按工程符号直接引用**（这是接线样板，不是组件的一部分）。
 * ===================================================================== */
#include "zk/zk_wall.h"

#include "storage/StoragePreferences.h"
#include "system/ClockManager.h"
#include "utils/Log.h"

#include "simple_player.h"           /* 官方包 simple-player（Manifest 里有 accessKey 授权） */
#include <base/rectangle.h>

#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <string>

#undef LOG_TAG
#define LOG_TAG "WallWiring"

using namespace zk::wall;

/* ═════════ ① 日志钩子：组件日志 → 工程 LOGD/LOGW/LOGE ═════════ */
static void wallLogHook(int level, const char* msg, void* user) {
    (void)user;
    switch (level) {
    case ZW_LOG_DEBUG: LOGD("%s", msg); break;
    case ZW_LOG_INFO:  LOGI("%s", msg); break;
    case ZW_LOG_WARN:  LOGW("%s", msg); break;
    default:           LOGE("%s", msg); break;
    }
}

/* ═════════ ② 播放引擎：官方包 SimplePlayer（MI 硬解 + 上屏 + 自带格子对齐）═════════
 * 语义严格对齐 zk::wall::Engine（open 一次 / play 阻塞 / stop 打断）。 */
class SimplePlayerEngine : public Engine {
public:
    SimplePlayerEngine() {}
    virtual ~SimplePlayerEngine() {}

    virtual bool open(const EngineConfig& cfg) {
        /* 旋转口径：包按环境变量取顺时针角度（真源：不设则用 ConfigManager 的 screenRotate 反推）。
         * 多台必须统一；本工程的配置项 = prefs sp_wall_rotate。 */
        if (cfg.rotateDeg != 0) {
            char b[16];
            snprintf(b, sizeof(b), "%d", cfg.rotateDeg);
            setenv("SIMPLE_PLAYER_CLOCKWISE_ROTATION", b, 1);
            LOGI("wall[sp-pkg]: SIMPLE_PLAYER_CLOCKWISE_ROTATION=%d", cfg.rotateDeg);
        }
        sp_.setSynchronizing(cfg.synchronize);
        return true;
    }

    virtual bool play(const std::string& file, const Rect& rect) {
        sp_.play(file, base::Rectangle(rect.x, rect.y, rect.w, rect.h));   /* 阻塞到 EOF 或 stop() */
        return true;
    }

    virtual void stop() { sp_.stop(); }        /* 从别的线程打断 play() */
    virtual const char* name() const { return "simple-player(pkg)"; }

private:
    SimplePlayer sp_;
};

/* ═════════ ③ 配置存储 → SyncConfig（键名沿用工程口径）═════════ */
static SyncConfig wallConfigFromPrefs() {
    SyncConfig c;
    c.enabled  = StoragePreferences::getBool("sp_wall_en", false);
    c.group    = StoragePreferences::getString("sp_wall_group", "zksw-wall");
    c.index    = StoragePreferences::getInt("sp_wall_idx", 1);
    c.panels   = StoragePreferences::getInt("sp_wall_n", 2);
    c.role     = StoragePreferences::getInt("sp_wall_role", -1);   /* -1 = 第 1 屏自动当主机 */
    c.segMs    = StoragePreferences::getInt("sp_wall_seg_ms", 30000);
    c.leadMs   = StoragePreferences::getInt("sp_wall_lead_ms", 0);
    c.masterAddr = StoragePreferences::getString("sp_wall_peer", "");   /* 从机："ip" 或 "ip:port" */
    c.mediaHint  = StoragePreferences::getString("sp_video_sel", "");   /* 零配置：从素材路径推导 */
    c.gridAnchorMs = StoragePreferences::getInt("sp_wall_anchor_ms", 0);
    c.logFn = wallLogHook;
    c.nowFn = NULL;            /* 不设 = 组件内 clock_gettime(CLOCK_REALTIME)，毫秒口径 */
    c.clockFollowFn = NULL;    /* 见 ④ */
    return c;
}

/* ═════════ ④ 从机时钟跟随：把组内钟差喂给工程的 ClockManager ═════════
 * （真源 tick() 里直接调 ClockManager::setGroupHealthy / groupFollow；组件改成钩子） */
static void wallClockFollowHook(bool healthy, int skewMs, int rttMs, void* user) {
    (void)user;
    ClockManager::getInstance()->setGroupHealthy(healthy);
    if (healthy) ClockManager::getInstance()->groupFollow(skewMs, rttMs);
}

/* ═════════ ⑤ 屏保页接线（1s 定时器 + 生命周期）═════════ */
#define WALL_V4_SETTLE_MS 400          /* 停 easyui 播放器后等 MI 图层拆完（实测会踩坏 chn0） */

static SimplePlayerEngine sWallEngine;
static std::string sWallSpKey;         /* 当前"节目键"（换键才重开播放器） */
static int  sWallSpFailTicks = 0;      /* 起播失败重试节流（每 5s 一次） */
static bool sScreenOff = false;        /* 业务自己的熄屏/编辑态标志 */
static bool sEditMode = false;

/* 屏保页进入 */
void wallOnSaverEnter() {
    Sync& wl = Sync::instance();
    SyncConfig cfg = wallConfigFromPrefs();
    cfg.clockFollowFn = wallClockFollowHook;
    wl.start(cfg);                     /* 幂等：UDP 通道已起就不重复 bind */

    PlayerConfig pc;
    pc.rect = Rect(0, 0, SS_SCR_W, SS_SCR_H);          /* 屏保全屏（工程自己的宏） */
    pc.engine.synchronize = true;
    pc.engine.rotateDeg = StoragePreferences::getInt("sp_wall_rotate", 0);
    pc.fallbackFile = StoragePreferences::getString("sp_video_sel", "");
    pc.startLeadMs = StoragePreferences::getInt("sp_wall_start_lead_ms", wl.leadMs());
    pc.gridAnchorMs = StoragePreferences::getInt("sp_wall_anchor_ms", 0);
    Player::instance().configure(pc);
    Player::instance().setEngine(&sWallEngine);

    if (wl.enabled()) {
        wl.publishNow();      /* 主机：立刻补发 epoch（从机马上有新鲜网格） */
        wl.requestEpoch();    /* 从机：请主机立刻补发（把等待从 1s 压到 ms 级） */
        wl.pingNow();         /* 从机：join 前先把钟差量准 */
    }
}

/* 屏保页退出：**必须**停（拼接只在屏保生效；不停 = 主页面上还在放视频） */
void wallOnSaverLeave() {
    Player::instance().stop();
    sWallSpKey.clear();
    sWallSpFailTicks = 0;
}

/* 1s 定时器（与屏保页其它逻辑同一条主线程） */
bool wallOnSaverTimer() {
    Sync& wl = Sync::instance();
    Player& wp = Player::instance();

    /* 没启用拼接 -> 完全不干预（普通屏保轮播照旧） */
    if (!wl.enabled()) return true;

    /* ⚠️ 时钟守卫：RTC 空、未校时时不起播（否则"每轮都早已过期"刷满日志） */
    if (!wl.clockPlausible()) {
        LOGW("wall: 本机墙钟不可信（<2024-01-01）-> 等 NTP，本轮不起播");
        return true;
    }

    wl.tick();                            /* 收包/发探针/发 epoch/每秒自证日志 */

    /* 编辑态/熄屏态不该出画面（easyui 播放器自己会停；simple 引擎要显式停） */
    if (sEditMode || sScreenOff) {
        wallOnSaverLeave();
        return true;
    }

    /* 两个内核不能同时在显：simple 模式要让 ZKVideoView 让位（MI 图层/解码通道）
     * —— 总闸（所有 easyui 起播路径都要看它）+ 停完沉降 400ms 再起引擎。 */
    if (mVideoSsPtr != NULL && mVideoSsPtr->isPlaying()) {
        mVideoSsPtr->stop();
        usleep(WALL_V4_SETTLE_MS * 1000);
    }
    if (mImageSsBgPtr != NULL) mImageSsBgPtr->setVisible(false);

    /* "当前节目"键 = Sync::playKey()：playlist 模式 = <组目录>/playlist.json（**稳定**，
     * clip 切换由 Player 内部处理）；单 clip = seg_<idx>.mp4。
     * 千万别拿"当前 clip 文件"当键 —— 每切一个 clip 都会被当成换节目 -> 反复拆建 MI 图层。 */
    const std::string key = wl.playKey();
    if (!wp.running() || sWallSpKey != key) {
        if (wp.running()) wp.stop();
        if (sWallSpFailTicks > 0) { sWallSpFailTicks--; return true; }   /* 失败后歇 5s 再试 */
        sWallSpKey = key;
        Result r = wp.start(key);
        if (!r.ok()) LOGW("wall: Player::start 失败 -> %s", r.msg.c_str());
    }
    if (!wp.lastError().empty() && sWallSpFailTicks == 0) {
        LOGW("wall: 引擎报错 -> %s（静默 5s 后重试）", wp.lastError().c_str());
        sWallSpFailTicks = 5;
    }

    /* 每 5s 一条自证：相位的 pts/want/now/err 由引擎接管 -> 一律 -1（n/a），用 pkg=1 标记 */
    static int sTicks = 0;
    if ((++sTicks % 5) == 0) {
        LOGD("wall[sp-pkg]: pkg=1 cyc=%d period=%lldms anchor=%lldms begin=%lldms locked=%d "
             "pts=%lld want=%lld now=%lld err=%lld running=%d state=%s",
             wp.cycles(), wp.periodMs(), wp.anchorMs(), wp.beginMs(), wp.locked() ? 1 : 0,
             wp.lastPtsMs(), wp.lastWantMs(), wp.lastNowMs(), wp.lastErrMs(),
             wp.running() ? 1 : 0, wl.stateText().c_str());
        if (wl.playlistMode())
            LOGD("wall[sp-pkg]: playlist clips=%d total=%lldms clip=%d file=%s (local seg_%d/%d)",
                 wl.clipCount(), wl.totalMs(), wp.clipIndex(), wp.clipFile().c_str(),
                 wl.segIndex(), wl.panelCount());
    }
    return true;
}

/* ═════════ ⑥ 设置页（wallLogic.cc 口径）：配置改动后**重载** + 组目录清单 ═════════
 * 组件只提供数据，UI 行怎么循环取值由业务决定（真源见 projects/SmartPanel_HA/src/logic/wallLogic.cc）。 */
void wallOnSettingsChanged() {
    SyncConfig cfg = wallConfigFromPrefs();
    cfg.clockFollowFn = wallClockFollowHook;
    Result r = Sync::instance().start(cfg);      /* 幂等重载（组名/序号/排布变更后都要调） */
    LOGD("wall: reloaded (%s) -> playlist=%d clips=%d", r.msg.c_str(),
         Sync::instance().playlistMode() ? 1 : 0, Sync::instance().clipCount());
    /* 组名在"盘上真实存在的组目录"之间循环： */
    std::vector<std::string> groups = Sync::instance().listGroups();
    if (groups.empty()) LOGW("wall: %s 下没有组目录（请先用切块工具生成）",
                             Sync::instance().wallRoot().c_str());
}
