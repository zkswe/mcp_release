/*
 * zk_imagecache_test.cpp —— imagecache 组件自测（PC 可直接编能跑，不需要真机/不需要 easyui）
 *
 * 为什么 PC 能跑：组件的装载/释放是**回调注入**的，与平台无关。本测试把「解码」换成一个
 *   真实的文件读（句柄 = 读到的内容+字节数），于是能验证「命中不重解」「LRU 权重」「引用计数」
 *   「同路径换内容会串图」这些语义，并在 PC 上量出「解码次数」。
 *
 * 编译（Windows / llvm-mingw g++ 实测；Linux g++ 同样）：
 *   g++ -std=c++11 -O2 -Wall -I../include zk_imagecache_test.cpp ../src/zk_imagecache.cpp -o zk_imagecache_test.exe
 * 运行：
 *   ./zk_imagecache_test.exe            # 退出码 0 = 全 PASS
 *
 * ⚠️ PC 上的 ms 只是「相对值」（PC 读文件+分配是 µs 级），**真机数字看 platforms.md**。
 *    本测试的硬证据是**解码次数（loads）**：回页重设同一批封面 = 8 次 → 0 次。
 */
#include "zk/zk_imagecache.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <chrono>
#include <string>

/* ---------------- 断言小工具 ---------------- */
static int g_checks = 0;
static int g_fails = 0;
static void check(bool ok, const char *name, const char *extra = "") {
    ++g_checks;
    if (!ok) {
        ++g_fails;
    }
    printf("[%s] %s %s\n", ok ? "PASS" : "FAIL", name, extra);
}

/* ---------------- 模拟「装载 = 解码」：句柄 = 文件内容 ---------------- */
struct Handle {
    long bytes;
    char tag[96];       /* 文件内容（去换行）—— 用来证明「缓存里还是旧图」*/
    char path[160];
};
static int g_loadCalls = 0;         /* = 解码次数 */
static std::string g_lastFreedPath; /* 被 LRU 踢掉/释放的最后一个路径 */
static int g_warnCount = 0;
static int g_debugCount = 0;
static bool g_verbose = false;      /* -v：逐次打印 load/free（默认只打结论）*/

static int loadFromFile(const char *path, zk::Bitmap *out, void *user) {
    (void) user;
    FILE *fp = fopen(path, "rb");
    if (fp == NULL) {
        return -1;                  /* 打不开 = 装载失败（组件会记 lastError + warning）*/
    }
    char buf[96];
    const size_t n = fread(buf, 1, sizeof(buf) - 1, fp);
    fclose(fp);
    buf[n] = '\0';
    for (char *p = buf; *p != '\0'; ++p) {
        if (*p == '\n' || *p == '\r') {
            *p = '\0';
        }
    }
    Handle *h = (Handle *) malloc(sizeof(Handle));
    if (h == NULL) {
        return -2;
    }
    h->bytes = (long) n;
    snprintf(h->tag, sizeof(h->tag), "%s", buf);
    snprintf(h->path, sizeof(h->path), "%s", path);
    *out = h;
    ++g_loadCalls;
    if (g_verbose) {
        printf("        load  #%-3d %-22s tag=%s\n", g_loadCalls, path, h->tag);
    }
    return 0;
}

static void freeHandle(zk::Bitmap b, void *user) {
    (void) user;
    Handle *h = (Handle *) b;
    if (h != NULL) {
        g_lastFreedPath = h->path;
        if (g_verbose) {
            printf("        free      %-22s (tag=%s)\n", h->path, h->tag);
        }
        free(h);
    }
}

static void logHook(int level, const char *msg, void *user) {
    (void) user;
    if (level == ZK_IC_LOG_WARN) {
        ++g_warnCount;
    } else if (level == ZK_IC_LOG_DEBUG) {
        ++g_debugCount;
    }
    if (level != ZK_IC_LOG_DEBUG) {
        printf("        [%s] %s\n", level == ZK_IC_LOG_ERROR ? "ERROR" : "WARN", msg);
    }
}

/* ---------------- 造文件 ---------------- */
static bool writeFile(const char *path, const char *content) {
    FILE *fp = fopen(path, "wb");
    if (fp == NULL) {
        return false;
    }
    fputs(content, fp);
    fclose(fp);
    return true;
}

static double nowMs() {
    using namespace std::chrono;
    return (double) duration_cast<microseconds>(
               steady_clock::now().time_since_epoch()).count() / 1000.0;
}

int main(int argc, char **argv) {
    zk::ImageCache &ic = zk::ImageCache::instance();
    if (argc > 1 && strcmp(argv[1], "-v") == 0) {
        g_verbose = true;
    }
    printf("=== zk::ImageCache 组件自测（PC）===\n\n");

    /* ---- 0) 未配置就 cache：必须「不静默」（返 false + lastError + warning）---- */
    printf("-- 0) 未配置时的错误处理（不静默）\n");
    const bool r0 = ic.cache("zkic_never.txt");
    check(r0 == false, "0.1 未 configure 就 cache 返 false", ic.lastError());
    check(ic.fails() == 1, "0.2 计入 fails()");

    ic.setLogHook(logHook, NULL);

    /* ---- 1) 配置 ---- */
    printf("\n-- 1) configure\n");
    zk::ImageCache::Config cfg;                 /* 默认 capacity=128 / pathMaxLen=256 */
    cfg.load = loadFromFile;
    cfg.free = freeHandle;
    cfg.capacity = 8;                           /* 小容量，方便逼出 LRU 淘汰 */
    cfg.pathMaxLen = 64;
    check(ic.configure(cfg) == true, "1.1 configure 成功");
    check(ic.configure(cfg) == false, "1.2 重复 configure 被拒（幂等，不覆盖回调）", ic.lastError());
    check(ic.capacity() == 8, "1.3 capacity 生效");

    /* ---- 2) 首批 8 张：全部装载（= 首次解码，不可避免）---- */
    printf("\n-- 2) 首批 8 张封面（首次解码）\n");
    std::string paths[8];
    for (int i = 0; i < 8; ++i) {
        char p[64];
        snprintf(p, sizeof(p), "zkic_rec_%d.txt", i);
        paths[i] = p;
        writeFile(p, i % 2 == 0 ? "COVER-A" : "COVER-B");
    }
    ic.acquire();
    const int load0 = ic.loads();
    for (int i = 0; i < 8; ++i) {
        ic.cache(paths[i].c_str());
    }
    check(ic.slots() == 8, "2.1 8 张全部装载", (char *) (std::to_string(ic.slots()) + "/8").c_str());
    check(ic.loads() == load0 + 8, "2.2 首次解码 8 次（缓存不加速首解，符合预期）");
    check(ic.refs() == 1, "2.3 acquire 后 refs=1");

    /* ---- 3) 回页重设同一批：命中，0 次解码（本组件的核心价值）---- */
    printf("\n-- 3) 回页重设同一批封面（核心场景）\n");
    const int load1 = ic.loads();
    const int hits1 = ic.hits();
    for (int i = 0; i < 8; ++i) {
        ic.cache(paths[i].c_str());
    }
    check(ic.loads() == load1, "3.1 解码次数 8 -> +0（命中，不再解码）",
          (char *) ("loads=" + std::to_string(ic.loads())).c_str());
    check(ic.hits() == hits1 + 8, "3.2 命中 8 次");

    /* ---- 4) 引用计数：计数没归零不许清（多页共用）---- */
    printf("\n-- 4) 引用计数（多页共用一个缓存）\n");
    ic.acquire();                               /* 第 2 个页面也进了 */
    ic.release();                               /* 第 2 个页面退出 */
    check(ic.refs() == 1, "4.1 还有一个页面在用 -> refs=1");
    check(ic.slots() == 8, "4.2 别人还在用 -> 不清缓存（slots 仍 8）");
    ic.release();                               /* 最后一个页面退出 */
    check(ic.refs() == 0, "4.3 refs=0");
    check(ic.slots() == 0, "4.4 最后一个退出才 releaseAll（slots=0）");

    /* ---- 5) LRU 权重：常看的封面不被一次性扫过的图挤掉 ---- */
    printf("\n-- 5) 权重 LRU（hot 存活 / cold 先被踢）\n");
    ic.acquire();
    writeFile("zkic_hot.txt", "HOT-COVER");
    writeFile("zkic_extra.txt", "NEW-COVER");
    ic.cache("zkic_hot.txt");
    for (int i = 0; i < 4; ++i) {
        ic.cache("zkic_hot.txt");               /* 命中 4 次 -> 权重抬高 */
    }
    check(ic.loads() == load1 + 0 + 1, "5.1 hot 首次装载 1 次 + 命中 4 次（没重解）");
    for (int i = 0; i < 7; ++i) {               /* 7 张冷图：路过后 hot 权重每轮掉 1 */
        char p[64];
        snprintf(p, sizeof(p), "zkic_cold_%d.txt", i);
        writeFile(p, "COLD");
        ic.cache(p);
    }
    check(ic.slots() == 8, "5.2 槽位满了（8/8）");
    g_lastFreedPath.clear();
    ic.cache("zkic_extra.txt");                 /* 第 9 张 -> 必须踢一个 */
    check(g_lastFreedPath == "zkic_cold_0.txt",
          "5.3 被踢的是最早那张冷图（权重最小）", g_lastFreedPath.c_str());
    const int load2 = ic.loads();
    ic.cache("zkic_hot.txt");                   /* hot 还活着 */
    check(ic.loads() == load2, "5.4 hot 没被踢（仍命中，0 次解码）");
    ic.cache("zkic_cold_0.txt");                /* 被踢的那张要重解 */
    check(ic.loads() == load2 + 1, "5.5 被踢的冷图重解 1 次（淘汰的代价）");
    printf("        （evicts=%d，slots=%d）\n", ic.evicts(), ic.slots());
    ic.release();

    /* ---- 6) ⚠️ 路径必须唯一：固定名换内容 -> 命中成旧图（串图复现）---- */
    printf("\n-- 6) ⚠️ 固定名换内容 = 命中旧图（串图）——所以路径必须带批次/版本\n");
    ic.acquire();
    writeFile("zkic_pin.txt", "SEARCH-1ST");
    ic.cache("zkic_pin.txt");                   /* 装载，内容 = SEARCH-1ST */
    const int load3 = ic.loads();
    writeFile("zkic_pin.txt", "SEARCH-2ND");    /* 同名文件被覆盖成新内容 */
    const bool hit = ic.cache("zkic_pin.txt");
    check(hit == true && ic.loads() == load3,
          "6.1 同路径不再解码（缓存里还是 SEARCH-1ST -> 这就是串图的根因）");
    writeFile("zkic_pin_b2.txt", "SEARCH-2ND");
    ic.cache("zkic_pin_b2.txt");                /* 修法：路径带批号 -> 新路径 -> 新解码 */
    check(ic.loads() == load3 + 1, "6.2 路径带批号后重新解码（新图能上屏）");
    ic.release();

    /* ---- 7) 错误路径全覆盖（都要给 lastError，不静默）---- */
    printf("\n-- 7) 错误路径（不静默）\n");
    const int fails0 = ic.fails();
    check(ic.cache(NULL) == false, "7.1 NULL 路径被拒", ic.lastError());
    check(ic.cache("") == false, "7.2 空路径被拒", ic.lastError());
    std::string tooLong(80, 'x');
    tooLong += ".txt";
    check(ic.cache(tooLong.c_str()) == false, "7.3 超长路径被拒（pathMaxLen=64）", ic.lastError());
    check(ic.fails() == fails0 + 3, "7.4 三次拒收都计入 fails()");
    check(g_warnCount >= 3, "7.5 每次拒收都发过 warning（日志能接出去）");
    check(g_debugCount > 0, "7.6 debug 日志钩子有输出（命中/装载可观察）");

    /* ---- 8) 「无缓存 vs 有缓存」同操作对比（8 张封面 × 20 轮回页）---- */
    printf("\n-- 8) 无缓存 vs 有缓存（8 张封面 × 20 轮回页重设；硬证据 = 解码次数）\n");
    ic.acquire();
    int l0 = ic.loads();
    double t0 = nowMs();
    for (int r = 0; r < 20; ++r) {
        ic.releaseAll();                        /* 模拟"每轮都重建、缓存没命中"的最坏口径 */
        for (int i = 0; i < 8; ++i) {
            ic.cache(paths[i].c_str());
        }
    }
    double tNo = nowMs() - t0;
    int loadsNo = ic.loads() - l0;
    ic.releaseAll();                            /* 有缓存这一组也从冷启动开始（公平对比）*/
    l0 = ic.loads();
    t0 = nowMs();
    for (int r = 0; r < 20; ++r) {
        for (int i = 0; i < 8; ++i) {
            ic.cache(paths[i].c_str());         /* 有缓存：第 1 轮装载后全是命中 */
        }
    }
    double tYes = nowMs() - t0;
    int loadsYes = ic.loads() - l0;
    ic.release();
    printf("        | 场景 | 解码次数 | 耗时(PC 相对值) |\n");
    printf("        | 无缓存(releaseAll 每轮) | %d | %.3f ms |\n", loadsNo, tNo);
    printf("        | 有缓存(ImageCache)      | %d | %.3f ms |\n", loadsYes, tYes);
    check(loadsYes == 8, "8.1 有缓存：20 轮只解码 8 次（= 首批那一次）");
    check(loadsNo == 8 * 20, "8.2 无缓存：20 轮解码 160 次");
    printf("        → 真机口径（280x280 封面 26~65ms/张）见 platforms.md：回页 315ms -> 1ms\n");

    printf("\n=== 合计 %d 项，FAIL %d ===\n", g_checks, g_fails);
    printf("（本自测的硬证据是解码次数；PC 上的 ms 只是相对值）\n");
    return g_fails == 0 ? 0 : 1;
}
