/* =====================================================================
 * zk_wall_player.cpp —— zk::wall::Player（相位驱动内核：选片 + 起停）
 *
 * 落地来源（**逐条同源**）：
 *   projects/SmartPanel_HA/src/wall/WallPlayer.cpp（v7.12/v7.13：把解码与"格子对齐"交给
 *   官方包 simple-player 的 SimplePlayer，本层只做**选片**与**起停**）
 *   + projects/SmartPanel_HA/src/logic/mainLogic.cc 的「边界预热踩点」（wallSimpleTick/wallWaitUntil）
 *
 * 去掉的项目私有依赖（→ 构造入参/回调/注入）：
 *   · SimplePlayer（官方包，带 accessKey）        → Engine 接口注入（真源那份见 example/flythings_wiring.cc）
 *   · StoragePreferences（sp_wall_rotate / sp_video_sel / sp_wall_anchor_ms）→ PlayerConfig
 *   · WallLink（组网/时间轴）                     → zk::wall::Sync（同源移植）
 *   · LOGD/LOGW                                   → ZWLOG（LogFn 钩子）
 *
 * 本层保留的两件事（就是真源里"属于本工程"的部分）：
 *   ① **选片**：playlist（一组多视频轮播）模式下按"组内时间栅格"挑当前 clip 的**本机分格**文件，
 *      每轮 play() 返回后重挑一次；单 clip 模式直接用 Sync::playKey()。
 *   ② **起停**：该起就起 / 该停就停（相位由引擎自己锁，本层不每轮重建播放器）。
 *
 * ⚠️ 相位诊断量（pts/want/now/err）在"引擎接管"后**不由本组件测量** → 一律 -1（n/a），
 *    不要当 0 用（真源日志里用 pkg=1 标记这个口径）。
 * ===================================================================== */
#include "zk_wall_internal.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <atomic>
#include <mutex>
#include <string>
#include <thread>

namespace zk {
namespace wall {

using namespace zk::wall::internal;

struct Player::Impl {
    std::thread th;
    std::atomic<bool> alive;
    std::atomic<bool> stopReq;
    std::atomic<bool> playing;        /* 当前有 play() 在跑（= 相位已由引擎接管） */
    std::atomic<int> cycles;          /* 已完成的 play() 轮数 */
    std::atomic<int> clipIdx;
    std::atomic<int> clipCnt;
    std::atomic<int> w, h;            /* 起播时的输出尺寸（判断"同节目同尺寸" -> 不重开） */

    Engine* engine;
    PlayerConfig cfg;

    std::mutex mu;
    std::string key;                  /* 节目键（= Sync::playKey()；换键才重开） */
    std::string cur;                  /* 当前实际在播文件 */
    std::string err;

    Impl() : alive(false), stopReq(false), playing(false), cycles(0), clipIdx(0), clipCnt(1),
             w(0), h(0), engine(NULL) {}
};

Player::Player() : impl_(new Impl()) {}

Player::~Player() {
    stop();
    delete impl_;
}

Player& Player::instance() {
    static Player p;
    return p;
}

void Player::setEngine(Engine* engine) { impl_->engine = engine; }

void Player::configure(const PlayerConfig& cfg) { impl_->cfg = cfg; }

const PlayerConfig& Player::config() const { return impl_->cfg; }

/* ── 组内时间轴（诊断用；播放相位由引擎自己算）── */
static long long groupElapsed(long long* period) {
    Sync& wl = Sync::instance();
    const long long p = wl.playlistMode() ? wl.totalMs() : wl.segMs();
    if (period != NULL) *period = p;
    if (!wl.enabled() || !wl.hasEpoch() || p <= 0) return -1;
    const long long n = Sync::nowMs();
    if (n <= 0) return -1;
    long long g = (n - wl.epochMs()) % p;
    if (g < 0) g += p;
    return g;
}

long long Player::periodMs() const {
    long long p = 0;
    groupElapsed(&p);
    return p;
}

long long Player::beginMs() const {
    return groupElapsed(NULL);
}

long long Player::anchorMs() const {
    long long p = 0;
    const long long g = groupElapsed(&p);
    if (g < 0) return -1;
    return Sync::nowMs() - g;
}

/* 引擎接管后这四个量不再由本组件测量 → -1（n/a） */
long long Player::lastPtsMs() const  { return -1; }
long long Player::lastWantMs() const { return -1; }
long long Player::lastNowMs() const  { return -1; }
long long Player::lastErrMs() const  { return -1; }

int Player::cycles() const { return impl_->cycles.load(); }

bool Player::running() const { return impl_->alive.load(); }

std::string Player::currentFile() const {
    std::lock_guard<std::mutex> lk(impl_->mu);
    return impl_->cur;
}

std::string Player::clipFile() const { return currentFile(); }

int Player::clipIndex() const { return impl_->clipIdx.load(); }
int Player::clipCount() const { return impl_->clipCnt.load(); }

bool Player::locked() const {
    /* 引擎在跑且没出错 = "格子对齐已接管"（不再有旧版的追赶/锁相两态） */
    return impl_->playing.load() && impl_->err.empty();
}

std::string Player::lastError() const {
    std::lock_guard<std::mutex> lk(impl_->mu);
    return impl_->err;
}

Result Player::start(const std::string& playKey) {
    Impl* im = impl_;
    if (playKey.empty()) return Result(ZW_EINVAL, "playKey 为空（先 Sync::start()，再用 Sync::playKey()）");
    if (im->engine == NULL)
        return Result(ZW_ENO_ENGINE, "未注入播放引擎：先 Player::setEngine()（参考 example/flythings_wiring.cc）");

    if (im->alive.load()) {
        bool same;
        {
            std::lock_guard<std::mutex> lk(im->mu);
            same = (im->key == playKey) &&
                   im->w.load() == im->cfg.rect.w && im->h.load() == im->cfg.rect.h;
        }
        if (same) return Result(ZW_OK, "已在播同一个节目（不重开，避免反复拆建 MI 图层）");
        stop();
    }
    if (im->cfg.rect.w <= 0 || im->cfg.rect.h <= 0)
        return Result(ZW_EINVAL, "输出矩形为空：先 Player::configure() 设屏保全屏尺寸");

    {
        std::lock_guard<std::mutex> lk(im->mu);
        im->key = playKey;
        im->cur.clear();
        im->err.clear();
    }
    im->cycles = 0;
    im->stopReq = false;
    im->w = im->cfg.rect.w;
    im->h = im->cfg.rect.h;
    im->alive = true;

    /* 线程参数：拷贝一份配置/键（避免运行期 configure() 改到线程读的那份） */
    const PlayerConfig cfg = im->cfg;
    im->th = std::thread([this, playKey, cfg]() {
        Impl* p = impl_;
        Engine* eng = p->engine;

        if (!eng->open(cfg.engine)) {
            {
                std::lock_guard<std::mutex> lk(p->mu);
                p->err = "engine open failed";
            }
            ZWLOG(ZW_LOG_ERROR, "wall[player]: engine(%s) open failed -> 不再送流（查引擎日志/通道占用）",
                  eng->name());
            p->alive = false;
            return;
        }

        /* ── 边界预热踩点（真源 mainLogic：等「下一个整边界 − lead」再拉起引擎，
         *    让第一帧正好落在整边界；引擎没有 seek API 时的替代做法）。
         *    调度口径与真源一致：**粗轮询（50ms）直到离目标 ≤1600ms，再精等到毫秒**
         *    （Sync::waitUntil 自带「>1600ms 就不等」的保护，不能拿它一把等几十秒）。
         *    放在本线程里做，所以**不阻塞**调用者（UI 主线程）。── */
        {
            Sync& wl = Sync::instance();
            const int lead = cfg.startLeadMs;
            long long boundary = 0;
            if (cfg.gridAnchorMs != 0) {
                /* 方案 B：锚点是常数，边界 = anchor + k*period（各屏用本机 NTP 钟，零网络） */
                const long long per = wl.periodMs();
                const long long n = Sync::nowMs();
                if (per > 0 && n > 0) {
                    const long long d = n - cfg.gridAnchorMs;
                    boundary = cfg.gridAnchorMs + ((d >= 0 ? d / per : 0) + 1) * per;
                }
            } else if (wl.hasEpoch()) {
                boundary = wl.nextBoundaryMs();
            }
            if (lead > 0 && boundary > 0) {
                const long long wait = boundary - Sync::nowMs();
                if (wait > (long long)lead + 100) {
                    const long long target = boundary - lead;
                    ZWLOG(ZW_LOG_INFO, "wall[player]: 边界踩点排队 距边界=%lldms lead=%dms -> %.1fs 后起播",
                          wait, lead, (wait - lead) / 1000.0);
                    while (!p->stopReq.load()) {                 /* 停策略：粗轮询 */
                        const long long rem = target - Sync::nowMs();
                        if (rem <= 0) break;
                        if (rem <= 1600) { Sync::waitUntil(target); break; }
                        usleep(50 * 1000);
                    }
                    if (p->stopReq.load()) { p->alive = false; return; }
                    wl.markPlayStarted(boundary);              /* 记偏差：正文=迟于边界（诊断口径） */
                }
            }
        }

        while (!p->stopReq.load()) {
            std::string f = playKey;
            Sync& wl = Sync::instance();
            /* 多视频轮播：按**栅格锚点**（真源方案 B：锚点 = 常数，各屏用本机 NTP 钟；
             *   0 = 退回主机 epoch 网格）算出"此刻该放哪个 clip 的本机分格"。 */
            if (wl.playlistMode()) {
                const long long total = wl.totalMs();
                const long long n = Sync::nowMs();
                const long long anchor = (cfg.gridAnchorMs != 0) ? cfg.gridAnchorMs : wl.epochMs();
                if (total > 0 && n > 0 && (cfg.gridAnchorMs != 0 || wl.hasEpoch())) {
                    long long g = (n - anchor) % total;
                    if (g < 0) g += total;
                    int k = 0;
                    long long off = 0;
                    if (wl.clipAt(g, &k, &off)) {
                        const std::string nf = wl.segPathForClip(k);
                        if (!nf.empty()) {
                            if (nf != f)
                                ZWLOG(ZW_LOG_INFO, "wall[player]: clip -> %d/%d off=%lldms %s",
                                      k, wl.clipCount(), off, nf.c_str());
                            f = nf;
                            p->clipIdx = k;
                            p->clipCnt = wl.clipCount();
                        }
                    }
                } else {
                    /* 时钟不可信：本地兜底（真源 prefs sp_video_sel），每次只报一次日志 */
                    const std::string sel = cfg.fallbackFile.empty() ? wl.segPathForClip(0) : cfg.fallbackFile;
                    static std::string sLastPick;
                    f = sel;
                    if (f != sLastPick) {
                        sLastPick = f;
                        ZWLOG(ZW_LOG_WARN, "wall[player]: clock not ready -> local pick %s", f.c_str());
                    }
                    p->clipIdx = 0;
                    p->clipCnt = wl.clipCount();
                }
            }
            /* 双保险：任何情况下都不把清单/配置文件当视频交给引擎 */
            if (f.size() > 5 && f.compare(f.size() - 5, 5, ".json") == 0) {
                ZWLOG(ZW_LOG_WARN, "wall[player]: %s 不是视频，回退清单第 0 段", f.c_str());
                f = wl.segPathForClip(0);
            }
            {
                std::lock_guard<std::mutex> lk(p->mu);
                p->cur = f;
            }
            p->playing = true;
            ZWLOG(ZW_LOG_INFO, "wall[player]: play %s (cycle=%d, clip=%d/%d, engine=%s)",
                  f.c_str(), p->cycles.load() + 1, p->clipIdx.load(), p->clipCnt.load(), eng->name());

            /* 引擎的 play() 会抛异常（真源 simple-player 就是这套）；这里必须接住，
             * 否则一条坏文件就把播放线程打死（现场表现 = 屏保黑屏）。 */
            bool ok = true;
            try {
                ok = eng->play(f, cfg.rect);     /* **阻塞**：读到 EOF 或被 stop() 打断 */
            } catch (std::exception& e) {
                ok = false;
                {
                    std::lock_guard<std::mutex> lk(p->mu);
                    p->err = e.what();
                }
                ZWLOG(ZW_LOG_WARN, "wall[player]: play error -> %s（1s 后重试）", e.what());
            } catch (...) {
                ok = false;
                {
                    std::lock_guard<std::mutex> lk(p->mu);
                    p->err = "unknown exception";
                }
                ZWLOG(ZW_LOG_WARN, "wall[player]: play unknown error（1s 后重试）");
            }
            if (!ok && p->stopReq.load()) break;
            if (!ok) usleep(1000 * 1000);        /* 失败歇 1s，别把 CPU/驱动打爆 */
            else {
                std::lock_guard<std::mutex> lk(p->mu);
                p->err.clear();
            }
            p->playing = false;
            p->cycles.fetch_add(1);
        }

        p->playing = false;
        p->alive = false;
        ZWLOG(ZW_LOG_INFO, "wall[player]: player thread exit (cycles=%d)", p->cycles.load());
    });
    ZWLOG(ZW_LOG_INFO, "wall[player]: start %s rect=(%d,%d,%d,%d) engine=%s sync=%d",
          playKey.c_str(), im->cfg.rect.x, im->cfg.rect.y, im->cfg.rect.w, im->cfg.rect.h,
          im->engine->name(), im->cfg.engine.synchronize ? 1 : 0);
    return Result(ZW_OK, "已起播");
}

void Player::stop() {
    Impl* im = impl_;
    if (!im->alive.load()) {
        if (im->th.joinable()) im->th.join();
        return;
    }
    im->stopReq = true;
    if (im->playing.load() && im->engine != NULL)
        im->engine->stop();                 /* 从调用者线程打断阻塞中的 play() */
    if (im->th.joinable()) im->th.join();
    im->alive = false;
    im->playing = false;
    ZWLOG(ZW_LOG_INFO, "wall[player]: stopped (cycles=%d)", im->cycles.load());
}

} /* namespace wall */
} /* namespace zk */
