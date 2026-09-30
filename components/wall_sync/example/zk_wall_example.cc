/* =====================================================================
 * zk_wall_example.cc —— zk::wall 最小可跑示例（配置 + 起播 + 状态打印）
 *
 * 作用：**不接任何平台播放器**跑通「组网/时间轴 + 相位驱动」这一层，确认：
 *   ① 配置进得去（含从素材路径推导组名/序号）；
 *   ② Sync 能算出整边界、相位、钟差（单机也能跑：自己既是主机又是唯一屏）；
 *   ③ Player 能把选片结果交给"引擎"（本示例用桩引擎，打印它收到的文件）；
 *   ④ 诊断量能打出来对账。
 * 桩引擎每轮按"周期"睡满一轮（模拟引擎自己锁相），不真正解码/上屏。
 *
 * 编译（PC 自测；Linux/WSL）：
 *   g++ -std=c++11 -Iinclude -Isrc -I<rapidjson>/include \
 *       src/zk_wall_sync.cpp src/zk_wall_player.cpp example/zk_wall_example.cc -o zk_wall_demo -lpthread
 * 工程内使用（真机接线）见 example/flythings_wiring.cc。
 * ===================================================================== */
#include "zk/zk_wall.h"

#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include <atomic>
#include <string>

using namespace zk::wall;

/* ── ① 日志钩子：接到业务自己的日志（设备上不接 = 什么都看不到）── */
static void myLog(int level, const char* msg, void* user) {
    (void)user;
    static const char* kLevel[4] = { "D", "I", "W", "E" };
    printf("[zk-wal %s] %s\n", kLevel[level & 3], msg);
    fflush(stdout);
}

/* ── ② 桩播放引擎（真实工程这里放官方包 SimplePlayer；见 example/flythings_wiring.cc）──
 *  Engine 语义：open() 一次；play() **阻塞**到 EOF 或被 stop() 打断；stop() 从别的线程打断。 */
class StubEngine : public Engine {
public:
    StubEngine() : stopReq_(false), rounds_(0) {}

    virtual bool open(const EngineConfig& cfg) {
        printf("[stub-engine] open sync=%d rotate=%d ch=(%d,%d)\n",
               cfg.synchronize ? 1 : 0, cfg.rotateDeg, cfg.vdecChannel, cfg.dispChannel);
        return true;
    }

    virtual bool play(const std::string& file, const Rect& rect) {
        stopReq_ = false;
        ++rounds_;
        printf("[stub-engine] play #%d %s rect=(%d,%d,%d,%d)\n",
               rounds_, file.c_str(), rect.x, rect.y, rect.w, rect.h);
        /* 模拟"引擎自己按本机钟锁相"把这一轮播完：睡到本轮结束（最多 2s，示例别等太久） */
        Sync& wl = Sync::instance();
        long long deadline = Sync::nowMs() + 2000;
        if (wl.hasEpoch()) {
            const long long nb = wl.nextBoundaryMs();
            if (nb > 0 && nb - Sync::nowMs() < 2000) deadline = nb;
        }
        while (!stopReq_.load() && Sync::nowMs() < deadline) usleep(20 * 1000);
        if (stopReq_.load()) printf("[stub-engine] play #%d interrupted by stop()\n", rounds_);
        return true;
    }

    virtual void stop() { stopReq_ = true; }
    virtual const char* name() const { return "stub"; }

private:
    std::atomic<bool> stopReq_;
    int rounds_;
};

int main(int argc, char** argv) {
    /* ── ③ 配置：来自业务的配置存储/入参（工程里 = prefs sp_wall_*，见 flythings_wiring.cc）── */
    SyncConfig cfg;
    cfg.enabled = true;
    cfg.group = (argc > 1) ? argv[1] : "zksw-wall";   /* 组名 = 盘上素材目录名 */
    cfg.wallRoot = (argc > 2) ? argv[2] : "/mnt/sdnand/wall";
    cfg.index = 1;              /* 本机序号（播 seg_<序号>.mp4） */
    cfg.panels = 2;             /* 单行横排 1x2（支持 2..4） */
    cfg.role = -1;              /* -1 = 第 1 屏自动当主机 */
    cfg.segMs = 10000;          /* 单 clip 模式**必须 = 素材真实时长**；示例用 10s 便于观察边界踩点 */
    cfg.leadMs = 0;             /* 0 = 内容零截断（推荐） */
    /* cfg.mediaHint = "<wallRoot>/<组名>/c1/seg_1.mp4";  // 可选：从素材路径推导组名/序号 */
    /* cfg.masterAddr = "192.0.2.1";                      // 从机才需要（示例地址是文档保留段） */
    cfg.gridAnchorMs = 0;       /* 多 clip 栅格绝对锚点（方案 B）；0 = 用主机 epoch 网格 */
    cfg.logFn = myLog;

    /* ── ④ 起组网/时间轴内核 ── */
    Result r = Sync::instance().start(cfg);
    printf("[demo] Sync::start -> code=%d msg=%s\n", r.code, r.msg.c_str());

    /* 清单诊断（设备上随时可查；不改播放状态） */
    PlaylistInfo pi;
    if (Sync::instance().queryPlaylist(cfg.group, cfg.panels, &pi))
        printf("[demo] playlist ok: %d clip / total %lldms / cols=%d\n", pi.clips, pi.totalMs, pi.cols);
    else
        printf("[demo] playlist 不可用（%s）-> 单 clip 模式：%s\n",
               pi.why.c_str(), Sync::instance().segPath().c_str());
    std::vector<std::string> gs = Sync::instance().listGroups();
    printf("[demo] 组目录 %d 个\n", (int)gs.size());

    /* ── ⑤ 配播放器 + 注引擎（引擎生命周期由业务负责）── */
    StubEngine engine;
    Player& player = Player::instance();
    player.setEngine(&engine);
    PlayerConfig pc;
    pc.rect = Rect(0, 0, 1280, 800);       /* 屏保全屏 */
    pc.engine.synchronize = true;          /* 引擎自带对齐开关（各机钟必须一致前提 -> 靠 Sync） */
    pc.engine.rotateDeg = 0;               /* 多台必须统一 */
    pc.startLeadMs = 150;                  /* 边界预热踩点：第一帧落整边界（<0 = 不踩点） */
    player.configure(pc);

    /* ── ⑥ 主循环：业务每秒调一次 tick();"该起就起 / 该停就停" ── */
    for (int i = 0; i < 12; i++) {
        Sync& wl = Sync::instance();
        wl.tick();                          /* 收包/发探针/发 epoch/诊断日志 */

        /* 时钟守卫：RTC 空、未校时时**不要**起播（真源 wall_clock_not_set / clock_insane） */
        if (wl.enabled() && !wl.clockPlausible()) {
            printf("[demo] 时钟不可信（<2024-01-01）-> 先等 NTP，不起播\n");
            sleep(1);
            continue;
        }
        /* 就绪就起播；键不变时 Player 内部不会重开 */
        if (wl.enabled() && wl.readyToPlay() && !player.running()) {
            Result rs = player.start(wl.playKey());
            printf("[demo] Player::start -> code=%d msg=%s\n", rs.code, rs.msg.c_str());
        }
        /* 状态打印（状态页/日志口径） */
        printf("[demo] %llds state=%s phase=%lldms wait=%lldms next=%lldms skew=%d(%s,rtt=%d) "
               "playlist=%d clip=%d/%d file=%s cyc=%d\n",
               (long long)i, wl.stateText().c_str(), wl.phaseMs(), wl.waitToBoundaryMs(),
               wl.nextBoundaryMs(), wl.skewMs(), wl.skewSrc(), wl.skewRttMs(),
               wl.playlistMode() ? 1 : 0, player.clipIndex(), player.clipCount(),
               player.currentFile().c_str(), player.cycles());
        sleep(1);
    }

    /* ── ⑦ 收摊（进主页/设置页时业务要显式停：拼接只在屏保生效）── */
    player.stop();
    Sync::instance().stop();
    printf("[demo] done\n");
    return 0;
}
