/*
 * VinylSpin.cpp - 黑胶唱片自转实现（见 VinylSpin.hpp 的分工说明）
 *
 * 两套后端（都是"把封面按角度画进一张 BGRA 内存位图"）：
 *后端 0（定点映射，VS_BACKEND_SCALAR）：
 *     1) 源：封面 PNG --misc::image_load--> 缩放成 n x n（n = 控件边长 320）--> 我方 RGB 缓冲；
 *圆边 alpha 由 **RoundImageView::makeCircleMask(n)**给（SS=8 面积平均，与静态封面同源）。
 *     2) 每帧：角度 -> 1024 项 sin 表（Q16）拿 cos/sin；反向映射：每个目标像素求源坐标
 *        （Q16 定点），取整到像素中心 + **2x2 盒平均**采样 RGB；alpha 取圆覆盖率表。
 *后端 1（nanovg，VS_BACKEND_NANOVG）：
 *     nanovg 的 AGG 软件光栅器后端：`nvgCreateAGG(w,h,stride,NVG_TEXTURE_BGRA,buf)` **直接渲染到我方位图缓冲**
 *     （不落盘、不进 GL、不开窗口）；每帧：清屏 -> nvgReinitAgge 换目标 -> 平移+旋转 -> 画圆
 *并用 nvgImagePattern 贴封面纹理 -> nvgEndFrame。圆边抗锯齿走 **AGG 自带 edgeAntiAlias**。
 *封面纹理 **必须用 NVG_TEXTURE_BGRA 建**（本包 AGG 后端只支持 BGRA：目标/纹理格式不一致会
 *直接 `Assertion failed: "not supported format"`；nvgCreateImageRGBA 用不了）——源数据本就是
 *     BGRA，所以 **不用做任何通道交换**，直传。
 *角度与时间口径、双缓冲/握手、上屏路径两套后端**完全共用**。
 *   3) 上屏：模式 0 = 把像素拷进交给控件的那张位图 + invalidate（零分配）；
 *模式 1 = 拿本帧缓冲新造一张 bitmap_t 交给 setBackgroundBmp（框架释放旧的）。
 */
#include <zk/zk_vinyl.h>

#include <math.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include <string>

#include <base/log.h>
#include <control/ZKBase.h>
#include <utils/BitmapHelper.h>

#include <nanovg.h>
#include <nanovg_agg.h>

#include "misc/image_utility.h"

#include "zk_vinyl_circle_mask.h"
#include "zk_vinyl_worker.h"

namespace zk {

/* 0 = 同张位图原地改像素（零分配；默认先试这个）；1 = 每帧换新位图（框架自动释放旧的） */
#define VS_SWAP_BITMAP     0

/* 后端选择：0 = 自研定点映射（标量，当前默认）；1 = nanovg(AGG) 矢量绘制。
 * 只影响"这一帧怎么画"，不影响角度/时间/上屏/释放口径；两者都保留（真机对比见 REPORT_NANOVG）。 */
#define VS_BACKEND_SCALAR  0
#define VS_BACKEND_NANOVG  1
#ifndef VS_BACKEND_DEFAULT
/* 默认后端 = **定点映射**：真机 A/B（2026-09-21，12fps、同一封面同一首歌）
 *定点：CPU 42.6% / 旋转 7~22ms（典型 7~11）/ 实测 12.3~12.6fps
 *   nanovg：CPU 59.8% / 旋转 21~61ms（典型 25~42）/ 实测 11.1~11.7fps
 * -> 定点更快更省，作默认；nanovg 后端完整保留，改下面这一行即可切换（也支持运行期自动回退到 0）。
 * 数据与口径见 temp/mu_vinyl/REPORT_NANOVG.md。 */
#define VS_BACKEND_DEFAULT VS_BACKEND_NANOVG
#endif

#define VS_SIN_N           1024      /* sin 表项数（0.352 度/项），Q16 int32 共 4KB */
#define VS_DEG_PER_SEC     24        /* 转速：24 度/秒（15 秒一圈；任务要求的 20~30 度/秒档） */
#define VS_ALPHA_FLAG      0x01      /* 位图 type 的「带 alpha 位」（本机约定） */
#define VS_MAX_DT_MS       120       /* 单拍角度增量上限（防页面隐藏回来后角度跳变） */

/* ============================ 调试埋点（真机定位用，默认关闭） ============================
 * 存在 /tmp/vinyl_dump 文件时，逐帧把两块缓冲 dump 到 /tmp/vdump/：
 *   rot_<srcVer>_<idx>.raw = 后台渲染出来的那一帧（写进 wbuf 的像素）
 *   pub_<frame>_<idx>.raw  = UI 线程 memcpy 进「交给控件的位图」后的内容（= 控件要显示的）
 *   src_<srcVer>.raw       = 源封面（BGRA，n*n）
 * 判据：dump 干净而屏幕花 → 合成/显示路径；dump 本身就花 → 渲染/拷贝管线。
 * 代价：仅在 flag 存在时写盘，且总数封顶（VS_DUMP_MAX 帧）；不影响正常路径。 */
#define VS_DUMP_FLAG "/tmp/vinyl_dump"
#define VS_DUMP_DIR  "/tmp/vdump"
#define VS_DUMP_MAX  300

static bool vsDumpOn(void) {
    return access(VS_DUMP_FLAG, F_OK) == 0;
}

/* 测试图（真机查「局部刷新」用）：存在 /tmp/vinyl_testpat 时，把**合成图案**当封面写进 d->src：
 *深灰圆盘 + 12 个扇形分隔线 + 一条 5px 亮线（= 当前角度）+ 红点（0° 参考）。
 *于是每一步转动后，屏幕上应当只有一条亮线；若某块没被重画，那里就会留下**上一步的亮线**
 *  —— 不依赖封面内容、也不依赖图像拟合，肉眼都可直接判定。 */
static bool vsTestPatOn(void) {
    return access("/tmp/vinyl_testpat", F_OK) == 0;
}

/* 2026-09-22 12:16：①**先不裁成圆**（排除圆形覆盖率表这个变量）②**图中间放方块标记**，
 * 旋转一个角度后对比，就能看出「内容区域是不是没拷全」。两个独立 flag：
 *   /tmp/vinyl_nomask -> 圆内/圆外都写满（整幅方图都当有效内容）
 *   /tmp/vinyl_marker -> 在源图上叠**方块标记**：外框 + 中心实心方块 + 四角四色块 + 中心十字线 */
static bool vsNoMaskOn(void) {
    return access("/tmp/vinyl_nomask", F_OK) == 0;
}

static bool vsMarkerOn(void) {
    return access("/tmp/vinyl_marker", F_OK) == 0;
}

static void vsPutPx(uint8_t *s, int n, int x, int y, int b, int g, int r) {
    if (x < 0 || y < 0 || x >= n || y >= n) {
        return;
    }
    uint8_t *p = s + ((size_t) y * n + x) * 4;
    p[0] = (uint8_t) b;
    p[1] = (uint8_t) g;
    p[2] = (uint8_t) r;
    p[3] = 255;
}

/* 在现有源图上叠方块标记（不换图，只画标记，所以真实封面也能用） */
static void vsDrawMarkers(uint8_t *s, int n) {
    if (s == NULL || n <= 0) {
        return;
    }
    const int c = n / 2;
    for (int i = 0; i < n; ++i) {                       /* 整图 3px 白框（看边界有没有被拷贝） */
        for (int w = 0; w < 3; ++w) {
            vsPutPx(s, n, i, w, 255, 255, 255);
            vsPutPx(s, n, i, n - 1 - w, 255, 255, 255);
            vsPutPx(s, n, w, i, 255, 255, 255);
            vsPutPx(s, n, n - 1 - w, i, 255, 255, 255);
        }
    }
    for (int y = -24; y <= 24; ++y) {                   /* 中心 48x48 实心洋红方块 */
        for (int x = -24; x <= 24; ++x) {
            vsPutPx(s, n, c + x, c + y, 255, 0, 255);
        }
    }
    for (int y = -30; y <= 30; ++y) {                   /* 中心十字（判角度/镜像） */
        vsPutPx(s, n, c, c + y, 0, 255, 255);
        vsPutPx(s, n, c + y, c, 0, 255, 255);
    }
    const int bs = 12;                                  /* 四个方块放在**半径 100**处（字内，旋转不被裁） */
    const int rad = 100;
    for (int dy = -bs; dy <= bs; ++dy) {
        for (int dx = -bs; dx <= bs; ++dx) {
            vsPutPx(s, n, c + rad + dx, c + dy, 0, 0, 255);          /* +x：红 */
            vsPutPx(s, n, c + dx, c + rad + dy, 0, 255, 0);          /* +y：绿 */
            vsPutPx(s, n, c - rad + dx, c + dy, 255, 0, 0);          /* -x：蓝 */
            vsPutPx(s, n, c + dx, c - rad + dy, 255, 255, 255);      /* -y：白 */
        }
    }
}

static void vsMakeTestPat(uint8_t *dst, int n) {
    if (dst == NULL || n <= 0) {
        return;
    }
    const int c = n / 2;
    for (int y = 0; y < n; ++y) {
        for (int x = 0; x < n; ++x) {
            uint8_t *p = dst + ((size_t) y * n + x) * 4;
            const int dx = x - c;
            const int dy = y - c;
            const int r2 = dx * dx + dy * dy;
            p[0] = 30;
            p[1] = 30;
            p[2] = 30;
            p[3] = 255;
            if (r2 > 140 * 140 && r2 < 148 * 148) {          /* 外圈环 */
                p[0] = 200;
                p[1] = 200;
                p[2] = 200;
            }
        }
    }
    /* 12 段分隔线（每 30°，细） */
    for (int k = 0; k < 12; ++k) {
        const double a = k * 3.14159265358979323846 / 6.0;
        for (int r = 30; r < 145; ++r) {
            const int x = c + (int) (r * cos(a));
            const int y = c + (int) (r * sin(a));
            if (x >= 0 && y >= 0 && x < n && y < n) {
                uint8_t *p = dst + ((size_t) y * n + x) * 4;
                p[0] = 90;
                p[1] = 90;
                p[2] = 90;
            }
        }
    }
    /* 0° 参考：红点（在 +x 方向 120px 处） */
    for (int y = -5; y <= 5; ++y) {
        for (int x = -5; x <= 5; ++x) {
            const int px = c + 120 + x, py = c + y;
            uint8_t *p = dst + ((size_t) py * n + px) * 4;
            p[0] = 0;
            p[1] = 0;
            p[2] = 255;
        }
    }
    /* 亮线（当前角度 = 0°，宽 5px）——旋转后它跑到哪，就说明该区域是「当前帧」 */
    for (int r = 10; r < 145; ++r) {
        for (int w = -2; w <= 2; ++w) {
            const int px = c + r;
            const int py = c + w;
            uint8_t *p = dst + ((size_t) py * n + px) * 4;
            p[0] = 255;
            p[1] = 255;
            p[2] = 255;
        }
    }
}

/* 单步调试（2026-09-22 建议）：存在 /tmp/vinyl_step 时，读它里面的度数（一行整数，可负），
 * 把角度**静态地推进**这么多度并强制重画一帧，然后删掉该文件。
 * 用途：暂停后一步一步验证「每一步的屏幕内容是否全域都更新」——静止内容的截图不会跨帧。 */
static bool vsStepTake(int *degOut) {
    FILE *f = fopen("/tmp/vinyl_step", "rb");
    if (f == NULL) {
        return false;
    }
    int deg = 0;
    const int got = fscanf(f, "%d", &deg);
    fclose(f);
    unlink("/tmp/vinyl_step");
    if (got != 1 || deg == 0 || deg < -350 || deg > 350) {
        return false;
    }
    *degOut = deg;
    return true;
}

/* 刷新口径（2026-09-22 12:28）：“非必要不要碰 getAbsolutePosition，直接参考我们以前 gameview 那套的
 * setInvalid 带个取反”——即翻转控件自身的 invalid 状态，由框架**按控件为单位**重画：
 *     host->setInvalid(!host->isInvalid());
 * 背景：原口径 `invalidate(getAbsolutePosition())` 传的是**页面绝对矩形**，而框架把该矩形按
 * **控件本地坐标系**理解并裁到控件内，于是只剩本地 (100,166)-(320,320) 那块（右下角）被重画
 * —— 屏上就是「3~6 点方向 12fps、其余 1fps」+ 切歌时的“块状错乱”。
 * 实测（源图 r=100 放四个纯色块，静态走 20°，理论位移 34.7px）：
 *绝对矩形/NULL/面板系/控件矩形+父偏移 -> 位移 **0px**；整页 / 本地(0,0,w,h) / setInvalid 翻转 -> **33~35px**✅
 * 现在默认走 **setInvalid 翻转**（gameview 口径，不碰坐标）；其余口径仅留作对照（flag /tmp/vinyl_inv）。 */
static int vsInvMode(void) {
    FILE *f = fopen("/tmp/vinyl_inv", "rb");
    if (f == NULL) {
        return 0;
    }
    const int c = fgetc(f);
    fclose(f);
    if (c >= '0' && c <= '2') {
        return c - '0';
    }
    return 0;
}

static void vsDumpFile(const char *tag, int a, int b, const uint8_t *buf, int n) {
    if (buf == NULL || n <= 0) {
        return;
    }
    char path[128];
    snprintf(path, sizeof(path), VS_DUMP_DIR "/%s_%04d_%04d.raw", tag, a, b);
    FILE *f = fopen(path, "wb");
    if (f == NULL) {
        return;
    }
    fwrite(buf, 1, (size_t) n * n * 4, f);
    fclose(f);
}

/* ============================ sin 表（首用初始化） ============================ */
static int32_t sSin[VS_SIN_N];
static bool sSinReady = false;

static void vsSinInit(void) {
    if (sSinReady) {
        return;
    }
    for (int i = 0; i < VS_SIN_N; ++i) {
        const double a = 2.0 * 3.14159265358979323846 * (double) i / (double) VS_SIN_N;
        sSin[i] = (int32_t) (sin(a) * 65536.0);
    }
    sSinReady = true;
}

static long long vsNowMs(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long) ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static bitmap_t *vsBmpNew(int n) {
    bitmap_t *b = new bitmap_t;                 /* 56 字节：与框架 operator delete(p, 56) 对齐 */
    memset(b, 0, sizeof(bitmap_t));
    b->data = (uint8_t *) malloc((size_t) n * n * 4);
    if (b->data == NULL) {
        delete b;
        return NULL;
    }
    memset(b->data, 0, (size_t) n * n * 4);     /* 圆外必须真透明 */
    b->type = VS_ALPHA_FLAG;
    b->bits = 32;
    b->bytes = 4;
    b->alpha = 1;
    b->width = (uint32_t) n;
    b->height = (uint32_t) n;
    b->pitch = (uint32_t) (n * 4);
    return b;
}

/* ============================ 旋转核心 ============================ */
/**
 * 采样口径（为什么不是双线性）：本机实测双线性 320x320 约 18~20ms/帧（整机 CPU 69%），
 * 太贵；改成「**取整到像素中心 + 2x2 盒平均**」：
 *   · 采样点四舍五入到像素中心（定点 +0.5），再做 2x2 均值 -> 相当于自带半像素低通，
 *旋转时不会闪烁（比最近邻好很多），代价只有双线性的 1/2.5；
 *   · **正好落在像素中心时（角度 0/90/180/270 度）走单抽头：逐像素与原图一致**，
 *所以「静止/首帧」与静态封面口径完全对齐，一点不糊。
 */
static void vsRotate(uint8_t *dst, const uint8_t *src, const uint8_t *covTab, int n,
                     const int *rx0, const int *rx1, int32_t c16, int32_t s16) {
    const int n4 = n * 4;
    const int32_t cq = (int32_t) (n * 32768);   /* 圆心（Q16：像素中心 = i+0.5） */
    const int maxi = n - 2;                     /* 2x2 抽样要取 i+1 */

    for (int y = 0; y < n; ++y) {
        const int x0 = rx0[y];
        if (x0 < 0) {
            continue;                           /* 整行在圆外：dst 保持已清的 0 */
        }
        int x1 = rx1[y];
        if (x1 > maxi) {
            x1 = maxi;
        }
        const int64_t dyq = ((int64_t) y << 16) + 32768 - cq;
        const int64_t dxq0 = ((int64_t) x0 << 16) + 32768 - cq;
        /* 反向映射（绕圆心转 -a）：源 = 圆心 + R(-a) * (目标 - 圆心) */
        int sxq = (int) (cq + (((dxq0 * c16) + (dyq * s16)) >> 16));
        int syq = (int) (cq + ((((-dxq0) * s16) + (dyq * c16)) >> 16));
        const uint8_t *crow = covTab + (size_t) y * n;
        uint8_t *drow = dst + (size_t) y * n4;
        for (int x = x0; x <= x1; ++x) {
            /* 四舍五入到像素中心：s = (q + 0.5) 取整 */
            int sx = (sxq + 32768) >> 16;
            int sy = (syq + 32768) >> 16;
            const bool exact = ((sxq & 0xFFFF) == 32768) && ((syq & 0xFFFF) == 32768);
            if (sx < 0) {
                sx = 0;
            } else if (sx > maxi) {
                sx = maxi;
            }
            if (sy < 0) {
                sy = 0;
            } else if (sy > maxi) {
                sy = maxi;
            }
            const uint8_t *p1 = src + (size_t) sy * n4 + (size_t) sx * 4;
            const uint8_t *p2 = p1 + 4;
            const uint8_t *p3 = p1 + n4;
            const uint8_t *p4 = p3 + 4;
            uint8_t *dp = drow + (size_t) x * 4;
            if (exact) {
                dp[0] = p1[0];
                dp[1] = p1[1];
                dp[2] = p1[2];
            } else {
                dp[0] = (uint8_t) ((p1[0] + p2[0] + p3[0] + p4[0] + 2) >> 2);
                dp[1] = (uint8_t) ((p1[1] + p2[1] + p3[1] + p4[1] + 2) >> 2);
                dp[2] = (uint8_t) ((p1[2] + p2[2] + p3[2] + p4[2] + 2) >> 2);
            }
            dp[3] = crow[x];                    /* 圆边逐帧固定（不随旋转抖） */
            sxq += c16;
            syq -= s16;
        }
    }
}

/* ============================ nanovg(AGG) 后端 ============================ */
/**
 * 用 nanovg 把封面按角度画进 buf（BGRA、n x n）。
 * 为什么直接写进我们的位图：`nvgCreateAGG(w,h,stride,NVG_TEXTURE_BGRA,data)` 把 AGG 软件光栅器
 * **绑到我们给的缓冲**上（不是 GL/窗口），画完 = 内存位图就绪 -> setBackgroundBmp 直上控件。
 * 双缓冲要换目标，所以每帧先 nvgReinitAgge（同一上下文重指目标，不重建上下文）。
 * 圆边抗锯齿 = AGG 自带 edgeAntiAlias（与定点映射的"圆覆盖率表"是两条不同口径，见报告对比图）。
 *
 * @param angRad 角度（弧度，顺时针；与定点映射同一角度口径换算得到）
 */
static void vsNvgFrame(NVGcontext *vg, int img, int n, uint8_t *buf, float angRad) {
    const int stride = n * 4;
    memset(buf, 0, (size_t) stride * n);              /* 圆外要真透明 + 防上一帧残留 */
    nvgReinitAgge(vg, (uint32_t) n, (uint32_t) n, (uint32_t) stride, NVG_TEXTURE_BGRA, buf);
    const float c = (float) n * 0.5f;
    nvgBeginFrame(vg, (float) n, (float) n, 1.0f);
    nvgSave(vg);
    nvgTranslate(vg, c, c);
    nvgRotate(vg, angRad);
    nvgBeginPath(vg);
    nvgCircle(vg, 0.0f, 0.0f, c - 0.5f);              /* -0.5：圆边 AA 完整落在画布内 */
    nvgShapeAntiAlias(vg, 1);
    nvgFillPaint(vg, nvgImagePattern(vg, -c, -c, (float) n, (float) n, 0.0f, img, 1.0f));
    nvgFill(vg);
    nvgRestore(vg);
    nvgEndFrame(vg);
}

/* ============================ 实现 ============================ */
struct VinylSpin::Impl {
    pthread_mutex_t mx;             /* 保护 src/pending/busy 等跨线程字段 */

    ZKBase *host;
    bitmap_t *hostBmp;              /* 模式 0：交给控件的那张（借用；框架所有） */
    int n;

    int backend;                    /* 实际生效后端（0 定点 / 1 nanovg；nanovg 建不起来时回退为 0） */
    NVGcontext *vg;                 /* nanovg 上下文（AGG 后端，绑我方位图缓冲） */
    int nvgImg;                     /* 封面纹理句柄（-1 = 无；源用 d->src，**BGRA**） */
    int nvgSrcVer;                  /* 纹理里当前是哪一版源（-1 = 内容待上传；上传在后台绘制线程做） */
    bool dumpOn;                    /* 埋点开关（每 ~1s 探测一次 flag 文件） */
    bool testPatOn;                 /* 测试图开关（/tmp/vinyl_testpat） */
    bool noMask;                    /* 不裁圆（/tmp/vinyl_nomask）：整幅方图都当有效内容 */
    bool markerOn;                  /* 叠方块标记（/tmp/vinyl_marker） */
    uint8_t *covFull;               /* n*n 全 255 覆盖率表（不裁圆时用） */
    int dumpN;                      /* 已 dump 帧数（封顶 VS_DUMP_MAX） */
    int dumpSrcVer;                 /* 已 dump 的源版本 */
    long long dumpCheckMs;
    long long invLogMs;             /* 脏矩形诊断日志节流 */

    uint8_t *cov;                   /* 我方：圆覆盖率 n*n（RoundImageView::makeCircleMask） */
    int *rx0;                       /* 我方：每行有覆盖的 x 起（-1 = 整行在圆外） */
    int *rx1;                       /* 我方：每行有覆盖的 x 止 */
    uint8_t *src;                   /* 我方：正圆封面源（n*n*4，RGB 有效、alpha 忽略） */
    int srcVer;

    uint8_t *wbuf[2];               /* 我方：双缓冲旋转结果（模式 0 复用，零分配） */
    int wbufCur;
    bool handed;                    /* 模式 0：那张位图是否已经交给控件（交了 = 归框架） */
    uint8_t *pending;               /* 本帧算完待上屏（指针交接，不拷贝） */
    int pendingVer;
    bool havePending;
    bool busy;                      /* 后台有旋转任务在跑 */
    bool srcJob;                    /* 后台有解码任务在跑 */

    long long spinMs;               /* 播放态累计毫秒（角度 = spinMs * DEG_PER_SEC） */
    long long lastTickMs;
    long long firstPubMs;           /* 首帧上屏时刻（算 fps 用） */
    bool playing;
    int frames;
    int lastIdx;
    int lastSrcVer;
    int lastRotMs;
    int lastPubMs;
    std::string note;

    Impl()
        : host(NULL), hostBmp(NULL), n(0), backend(VS_BACKEND_DEFAULT), vg(NULL), nvgImg(-1),
          nvgSrcVer(-1), dumpOn(false), testPatOn(false), noMask(false), markerOn(false),
          covFull(NULL), dumpN(0), dumpSrcVer(-1), dumpCheckMs(0),
          invLogMs(0),
          cov(NULL), rx0(NULL), rx1(NULL), src(NULL),
          srcVer(0), wbufCur(0), handed(false), pending(NULL), pendingVer(0),
          havePending(false), busy(false), srcJob(false), spinMs(0), lastTickMs(0), firstPubMs(0),
          playing(false), frames(0), lastIdx(-1), lastSrcVer(0), lastRotMs(0), lastPubMs(0) {
        pthread_mutex_init(&mx, NULL);
        wbuf[0] = NULL;
        wbuf[1] = NULL;
    }

    /**丢掉「算完但还没上屏」的那一帧。模式 0 的 pending 指向复用的 wbuf，**不能 free**。 */
    void dropPending(void) {
        if (pending != NULL && VS_SWAP_BITMAP != 0) {
            free(pending);
        }
        pending = NULL;
        havePending = false;
    }

    void vsFree(void) {
        if (vg != NULL) {
            if (nvgImg > 0) {
                nvgDeleteImage(vg, nvgImg);          /* 纹理先于上下文释放 */
            }
            nvgDeleteAGG(vg);                        /* AGG 上下文（含光栅器缓冲） */
            vg = NULL;
        }
        nvgImg = -1;
        if (cov != NULL) {
            free(cov);
            cov = NULL;
        }
        if (covFull != NULL) {
            free(covFull);
            covFull = NULL;
        }
        if (rx0 != NULL) {
            free(rx0);
            rx0 = NULL;
        }
        if (rx1 != NULL) {
            free(rx1);
            rx1 = NULL;
        }
        if (src != NULL) {
            free(src);
            src = NULL;
        }
        for (int i = 0; i < 2; ++i) {
            if (wbuf[i] != NULL) {
                free(wbuf[i]);
                wbuf[i] = NULL;
            }
        }
        dropPending();                           /* 模式 0 下它只是 wbuf 的别名 */
        if (!handed && hostBmp != NULL) {       /* 还没交出去的：我方所有，必须释放 */
            if (hostBmp->data != NULL) {
                free(hostBmp->data);
                hostBmp->data = NULL;
            }
            delete hostBmp;
        }
        hostBmp = NULL;                          /* 已交给框架的：随控件销毁由框架释放 */
        handed = false;
    }

    /**惰性建 nanovg(AGG) 上下文 + 封面纹理（绑 wbuf[0] / src）。
     *运行期切后端时用（原先只在 attach 时按 VS_BACKEND_DEFAULT 建一次）。
     *  · 建不起来返回 false：调用方保持原后端，**不报错**（页面照常显示）。
     *  · 只建壳不承诺纹理内容：切换瞬间 src 可能正被后台解码更新 -> 交给 doRotate 按 srcVer
     *上传（与绘制同线程，不会打架）；所以这里把 nvgSrcVer 置 -1 强制传一次。 */
    bool ensureNvg(void) {
        if (vg != NULL) {
            return true;
        }
        if (n <= 0 || wbuf[0] == NULL || src == NULL) {
            return false;                    /* 还没 attach，别建（attach 里会按意愿建） */
        }
        vg = nvgCreateAGG((uint32_t) n, (uint32_t) n, (uint32_t) (n * 4), NVG_TEXTURE_BGRA,
                          wbuf[0]);
        if (vg == NULL) {
            return false;
        }
        nvgImg = nvgCreateImageRaw(vg, n, n, NVG_TEXTURE_BGRA, 0, src);
        if (nvgImg <= 0) {
            nvgDeleteAGG(vg);
            vg = NULL;
            nvgImg = -1;
            return false;
        }
        nvgSrcVer = -1;                      /* 内容待上传 */
        return true;
    }

    /**造圆覆盖率表 + 每行扫描区间 */
    bool makeCov(int size) {
        cov = zk_vinyl_circle_mask(size);
        if (cov == NULL) {
            return false;
        }
        rx0 = (int *) malloc(sizeof(int) * size);
        rx1 = (int *) malloc(sizeof(int) * size);
        if (rx0 == NULL || rx1 == NULL) {
            return false;
        }
        for (int y = 0; y < size; ++y) {
            const uint8_t *row = cov + (size_t) y * size;
            int a = -1;
            int b = -1;
            for (int x = 0; x < size; ++x) {
                if (row[x] != 0) {
                    if (a < 0) {
                        a = x;
                    }
                    b = x;
                }
            }
            if (b > size - 3) {
                b = size - 3;                   /* 双线性要取 x+1 */
            }
            if (a < 0 || a > b) {
                rx0[y] = -1;
                rx1[y] = -1;
                continue;
            }
            rx0[y] = a;
            rx1[y] = b;
        }
        return true;
    }
};

VinylSpin &VinylSpin::instance() {
    static VinylSpin s;
    return s;
}

VinylSpin::VinylSpin() {
    vsSinInit();
    mImpl = new Impl();
}

bool VinylSpin::attach(ZKBase *host) {
    Impl *d = mImpl;
    if (host == NULL) {
        return false;
    }
    const LayoutPosition &pos = host->getPosition();
    if (pos.mWidth <= 0 || pos.mHeight <= 0 || pos.mWidth != pos.mHeight) {
        LOGW("vinyl: 宿主控件不是正方形 %dx%d，放弃", pos.mWidth, pos.mHeight);
        return false;
    }
    if (d->host != NULL) {
        detach();                                /* 重复 attach：先摘旧的 */
    }
    const int n = pos.mWidth;
    if (!d->makeCov(n)) {
        LOGW("vinyl: 圆覆盖率表分配失败 n=%d", n);
        d->vsFree();
        return false;
    }
    d->covFull = (uint8_t *) malloc((size_t) n * n);
    if (d->covFull != NULL) {
        memset(d->covFull, 255, (size_t) n * n);      /* 不裁圆时用：整幅方图都写满 */
    }
    d->src = (uint8_t *) malloc((size_t) n * n * 4);
    d->wbuf[0] = (uint8_t *) malloc((size_t) n * n * 4);
    d->wbuf[1] = (uint8_t *) malloc((size_t) n * n * 4);
    if (d->src == NULL || d->wbuf[0] == NULL || d->wbuf[1] == NULL) {
        LOGW("vinyl: 缓冲分配失败 n=%d", n);
        d->vsFree();
        return false;
    }
    memset(d->src, 0, (size_t) n * n * 4);
    memset(d->wbuf[0], 0, (size_t) n * n * 4);
    memset(d->wbuf[1], 0, (size_t) n * n * 4);

    /* nanovg 后端：建 AGG 上下文（绑到 wbuf[0]，每帧 nvgReinitAgge 再换到真正要写的那块）
     * + 一张空白封面纹理（切歌时用 nvgUpdateImage 換内容，不重建上下文）。
     * **建不起来就自动回退定点后端**（只 warning，不让页面报错）。
     *
     * 格式口径（真机隔离探针实测，见 REPORT_NANOVG 与 temp/mu_vinyl/nanovg/）：
     *本包的 AGG 后端**只支持 NVG_TEXTURE_BGRA 目标**（其它目标格式在 nvgInitAGG 里直接
     *   `Assertion failed: !"not supported format"`）；纹理格式必须与目标一致，否则 renderPaint 同样断言。
     *所以：目标 BGRA（= 我方位图字节序）+ 纹理也用 NVG_TEXTURE_BGRA，且源数据按 BGRA 传
     *   （实测字节原样进目标 -> 颜色正确），**不需要**再转 RGBA。nvgCreateImageRGBA 会断言，不能用。 */
    if (d->backend == VS_BACKEND_NANOVG) {
        d->vg = nvgCreateAGG((uint32_t) n, (uint32_t) n, (uint32_t) (n * 4), NVG_TEXTURE_BGRA,
                             d->wbuf[0]);
        if (d->vg != NULL) {
            d->nvgImg = nvgCreateImageRaw(d->vg, n, n, NVG_TEXTURE_BGRA, 0, d->src);
        }
        if (d->vg == NULL || d->nvgImg <= 0) {
            LOGW("vinyl: nanovg 上下文/纹理建不起来，自动回退定点后端（n=%d vg=%p img=%d）", n,
                 (void *) d->vg, d->nvgImg);
            if (d->vg != NULL) {
                nvgDeleteAGG(d->vg);
                d->vg = NULL;
            }
            d->nvgImg = -1;
            d->backend = VS_BACKEND_SCALAR;
        }
    }

    /* 先造好一张空白（全透明）位图，但**先不交出去**：等第一帧旋转结果出来再交，
     * 这样封面还没算好之前，控件上还是 json 里的占位图（不会先空一下）。 */
    bitmap_t *b = vsBmpNew(n);
    if (b == NULL) {
        d->vsFree();
        return false;
    }
    pthread_mutex_lock(&d->mx);
    d->n = n;
    d->host = host;
    d->hostBmp = b;
    d->handed = false;
    d->lastTickMs = vsNowMs();
    pthread_mutex_unlock(&d->mx);
    LOGD("vinyl: 挂上宿主 %dx%d（模式 %d 后端 %s；首帧出来才把内存位图交给控件）", n, n,
         VS_SWAP_BITMAP, d->backend == VS_BACKEND_NANOVG ? "nanovg" : "定点");
    return true;
}

int VinylSpin::setBackend(int want) {
    Impl *d = mImpl;
    if (want != VS_BACKEND_NANOVG) {
        want = VS_BACKEND_SCALAR;
    }
    pthread_mutex_lock(&d->mx);
    const bool attached = (d->host != NULL);
    if (want == d->backend && (!attached || want != VS_BACKEND_NANOVG || d->vg != NULL)) {
        pthread_mutex_unlock(&d->mx);            /* 已经是这个后端（且上下文在）-> 不动 */
        return d->backend;
    }
    if (attached && want == VS_BACKEND_NANOVG) {
        if (!d->ensureNvg()) {
            pthread_mutex_unlock(&d->mx);        /* 建不起来：保持原后端，只 warning */
            LOGW("vinyl: nanovg 后端建不起来，保持当前后端 %d（真机对比请查 /lib/libnanovg.so）",
                 d->backend);
            return d->backend;
        }
    }
    const int from = d->backend;
    d->backend = want;
    d->lastIdx = -1;                             /* 强制下一拍重画（暂停态也刷一帧，看得见切换） */
    d->lastSrcVer = -1;
    const int n = d->n;
    pthread_mutex_unlock(&d->mx);
    LOGD("vinyl: 后端切换 %s -> %s（n=%d，向量表/角度口径不变；下一拍重画一帧）",
         from == VS_BACKEND_NANOVG ? "nanovg" : "定点",
         want == VS_BACKEND_NANOVG ? "nanovg" : "定点", n);
    return want;
}

void VinylSpin::detach() {
    Impl *d = mImpl;
    pthread_mutex_lock(&d->mx);
    d->host = NULL;                              /* 之后的 tick/发布都空转 */
    d->playing = false;
    d->spinMs = 0;
    d->frames = 0;
    d->srcVer = 0;
    d->lastIdx = -1;
    d->lastSrcVer = 0;
    d->n = 0;
    pthread_mutex_unlock(&d->mx);
    /* 等后台那一帧写完（它在写我方 wbuf，不能边写边 free）—— 单帧几 ms，最多等 200ms */
    for (int i = 0; i < 400; ++i) {
        pthread_mutex_lock(&d->mx);
        const bool b = d->busy;
        pthread_mutex_unlock(&d->mx);
        if (!b) {
            break;
        }
        usleep(500);
    }
    pthread_mutex_lock(&d->mx);
    d->dropPending();                            /* 丢掉可能刚落下的那一帧 */
    pthread_mutex_unlock(&d->mx);
    d->vsFree();                                 /* 同时处理「还没交出去的那张」（见 vsFree） */
    LOGD("vinyl: 已摘下（我方缓冲已释放；框架那张位图随控件销毁）");
}

void VinylSpin::setCover(const char *pngPath) {
    Impl *d = mImpl;
    if (pngPath == NULL || pngPath[0] == 0) {
        return;
    }
    const std::string path(pngPath);
    pthread_mutex_lock(&d->mx);
    if (d->srcJob || d->host == NULL) {
        pthread_mutex_unlock(&d->mx);
        return;                                  /* 上一张还在解 / 还没挂上宿主 */
    }
    d->srcJob = true;
    d->spinMs = 0;                               /* 切歌回 0 度 */
    pthread_mutex_unlock(&d->mx);

    VinylWorker::instance().start();
    VinylWorker::instance().post([d, path]() {
        const long long t0 = vsNowMs();
        bitmap_t tmp;
        memset(&tmp, 0, sizeof(tmp));
        ui::Size sz;
        sz.w = 0;
        sz.h = 0;
        int n = 0;
        pthread_mutex_lock(&d->mx);
        n = d->n;
        pthread_mutex_unlock(&d->mx);
        bool ok = false;
        if (n > 0 && misc::image_load(path, tmp, &sz, NULL, 0) && tmp.data != NULL) {
            /* 缩放成 n x n（与静态圆封面同一口径：整幅拉伸到方形盒） */
            bitmap_t sc;
            memset(&sc, 0, sizeof(sc));
            if (misc::bitmap_create(sc, (uint32_t) n, (uint32_t) n, tmp.bytes) && sc.data != NULL) {
                misc::bitmap_scale(sc, tmp);
                const int sb = (int) tmp.bytes;   /* sc 与源同字节数 */
                const uint8_t *s = sc.data;
                /* 两套后端都用同一份源：**BGRA**（image_load/框架字节序；nanovg 侧实测也吃 BGRA） */
                uint8_t *dst = d->src;
                if (dst != NULL && sb >= 3) {
                    for (int y = 0; y < n; ++y) {
                        const uint8_t *srow = s + (size_t) y * sc.pitch;
                        uint8_t *drow = dst + (size_t) y * n * 4;
                        for (int x = 0; x < n; ++x) {
                            drow[x * 4 + 0] = srow[x * sb + 0];
                            drow[x * 4 + 1] = srow[x * sb + 1];
                            drow[x * 4 + 2] = srow[x * sb + 2];
                            drow[x * 4 + 3] = 255;
                        }
                    }
                    ok = true;
                }
                misc::bitmap_destroy(sc);
            }
            free(tmp.data);
            tmp.data = NULL;
        }
        if (ok && d->backend == VS_BACKEND_NANOVG && d->vg != NULL && d->nvgImg > 0) {
            /* 纹理上传（与旋转同一个后台线程 -> 不会同时读写；上传在 srcVer++ 之前，帧一定看到新图） */
            nvgUpdateImage(d->vg, d->nvgImg, d->src);
            pthread_mutex_lock(&d->mx);
            d->nvgSrcVer = d->srcVer + 1;        /* 传的就是这一版（下面 ++ 后的值） */
            pthread_mutex_unlock(&d->mx);
        }
        pthread_mutex_lock(&d->mx);
        if (ok) {
            ++d->srcVer;                         /* 版本 +1：tick 看到就重画第 0 帧 */
        }
        d->srcJob = false;
        char buf[160];
        snprintf(buf, sizeof(buf), "vinyl: 封面就绪 %dx%d（源解码+缩放 %lldms ok=%d）", n, n,
                 vsNowMs() - t0, (int) ok);
        d->note = buf;
        pthread_mutex_unlock(&d->mx);
        LOGD("%s", buf);
    });
}

void VinylSpin::setPlaying(bool playing) {
    Impl *d = mImpl;
    pthread_mutex_lock(&d->mx);
    if (d->playing != playing) {
        d->playing = playing;
        LOGD("vinyl: %s（角度 %d 度）", playing ? "开转" : "停转",
             (int) ((d->spinMs * VS_DEG_PER_SEC / 1000) % 360));
    }
    pthread_mutex_unlock(&d->mx);
}

/**后台旋转一帧；结果缓冲指针交到 pending，由上屏那次 tick 取走（由成员函数保证访问私有 Impl） */
void VinylSpin::doRotate(Impl *d, int srcVer, int idx, int n, uint8_t *buf) {
    const long long t0 = vsNowMs();
    uint8_t *src = NULL;
    const uint8_t *cov = NULL;
    const int *rx0 = NULL;
    const int *rx1 = NULL;
    int backend = VS_BACKEND_SCALAR;
    NVGcontext *vg = NULL;
    int nvgImg = -1;
    bool dumpNow = false;
    pthread_mutex_lock(&d->mx);
    if (vsNowMs() - d->dumpCheckMs > 1000) {          /* 每秒探一次 flag，避免每帧 stat */
        d->dumpCheckMs = vsNowMs();
        d->dumpOn = vsDumpOn();
    }
    dumpNow = d->dumpOn && (d->dumpN < VS_DUMP_MAX);
    if (dumpNow && d->dumpSrcVer != srcVer) {
        d->dumpSrcVer = srcVer;
        vsDumpFile("src", srcVer, 0, d->src, n);      /* 源封面（看它是不是本身就花了） */
    }
    src = d->src;
    cov = d->noMask && d->covFull != NULL ? d->covFull : d->cov;
    const bool covIsFull = d->noMask && d->covFull != NULL;
    if (covIsFull) {
        cov = d->covFull;
    }
    rx0 = d->rx0;
    rx1 = d->rx1;
    backend = d->backend;
    vg = d->vg;
    nvgImg = d->nvgImg;
    pthread_mutex_unlock(&d->mx);

    if (backend == VS_BACKEND_NANOVG && vg != NULL && nvgImg > 0 && src != NULL) {
        /* 纹理落后于源（运行期刚切到 nanovg / 刚换过封面）-> 先补一次上传。
         * 上传/绘制都在**同一个后台绘制线程**，与 setCover 的解码任务同队列（TaskRunner 单线程）-> 无竞态。 */
        bool up = false;
        pthread_mutex_lock(&d->mx);
        if (d->nvgSrcVer != srcVer) {
            d->nvgSrcVer = srcVer;
            up = true;
        }
        pthread_mutex_unlock(&d->mx);
        if (up) {
            nvgUpdateImage(vg, nvgImg, src);
        }
        /* nanovg 后端：同一个 sin 表索引 idx（0..1023 = 0..360 度）-> 弧度，角度口径与定点后端一致 */
        vsNvgFrame(vg, nvgImg, n, buf, (float) idx * (2.0f * (float) NVG_PI / (float) VS_SIN_N));
    } else {
        const int32_t c16 = sSin[(idx + VS_SIN_N / 4) % VS_SIN_N];
        const int32_t s16 = sSin[idx % VS_SIN_N];
        /* 圆外区域**不必**每帧清：旋转只写圆内（覆盖率 > 0 的行区间），圆外一直保持 0
         * （两块双缓冲在 attach 时已全零）。模式 1 每帧是新的 malloc 缓冲，必须清。 */
        if (VS_SWAP_BITMAP != 0) {
            memset(buf, 0, (size_t) n * n * 4);
        }
        if (src != NULL && cov != NULL && rx0 != NULL && rx1 != NULL) {
            vsRotate(buf, src, cov, n, rx0, rx1, c16, s16);
        }
    }
    const int ms = (int) (vsNowMs() - t0);
    if (dumpNow) {
        vsDumpFile("rot", srcVer, idx, buf, n);       /* 后台渲染出来的那一帧（未上屏） */
        pthread_mutex_lock(&d->mx);
        ++d->dumpN;
        pthread_mutex_unlock(&d->mx);
    }
    pthread_mutex_lock(&d->mx);
    if (d->pending != NULL) {
        if (VS_SWAP_BITMAP != 0) {
            free(d->pending);                    /* 上一帧还没上屏就被顶掉（仅模式 1 是自己 malloc 的） */
        }
        d->pending = NULL;
    }
    d->pending = buf;
    d->pendingVer = srcVer;
    d->havePending = true;
    d->busy = false;
    d->lastRotMs = ms;
    pthread_mutex_unlock(&d->mx);
}

void VinylSpin::tick() {
    Impl *d = mImpl;
    if (d->host == NULL) {
        return;
    }

    /* ---- 角度推进：按墙钟增量，丢帧也匀速（暂停时不累加 = 停转） ---- */
    const long long now = vsNowMs();
    pthread_mutex_lock(&d->mx);
    long long dt = (d->lastTickMs > 0) ? (now - d->lastTickMs) : 0;
    d->lastTickMs = now;
    if (dt < 0) {
        dt = 0;
    } else if (dt > VS_MAX_DT_MS) {
        dt = VS_MAX_DT_MS;
    }
    if (d->playing) {
        d->spinMs += dt;
    }
    pthread_mutex_unlock(&d->mx);

    /* ---- 测试图 / 方块标记 / 不裁圆 三个调试开关 ---- */
    if (vsTestPatOn() != d->testPatOn) {
        pthread_mutex_lock(&d->mx);
        d->testPatOn = !d->testPatOn;
        if (d->testPatOn && d->src != NULL) {
            vsMakeTestPat(d->src, d->n);
            ++d->srcVer;
            d->lastSrcVer = -1;
            d->lastIdx = -1;
        }
        pthread_mutex_unlock(&d->mx);
        LOGD("vinyl: 测试图 %s（源已重写，强制重画）", d->testPatOn ? "开" : "关");
    }
    if (vsMarkerOn() != d->markerOn) {
        pthread_mutex_lock(&d->mx);
        d->markerOn = !d->markerOn;
        if (d->markerOn && d->src != NULL) {
            vsDrawMarkers(d->src, d->n);              /* 只在开的时候叠一次；关掉不擦 */
            ++d->srcVer;
            d->lastSrcVer = -1;
            d->lastIdx = -1;
        }
        pthread_mutex_unlock(&d->mx);
        LOGD("vinyl: 方块标记 %s", d->markerOn ? "开" : "关");
    }
    {
        const bool nm = vsNoMaskOn();
        if (nm != d->noMask) {
            pthread_mutex_lock(&d->mx);
            d->noMask = nm;
            d->lastSrcVer = -1;
            d->lastIdx = -1;                          /* 强制重画一帧 */
            pthread_mutex_unlock(&d->mx);
            LOGD("vinyl: 不裁圆 %s（覆盖率表 -> %s）", nm ? "开" : "关",
                 nm ? "全 255" : "圆形表");
        }
    }

    /* ---- 单步调试：/tmp/vinyl_step 里的度数 -> 静态推角度 + 强制重画一帧 ---- */
    int stepDeg = 0;
    if (vsStepTake(&stepDeg)) {
        pthread_mutex_lock(&d->mx);
        d->spinMs += (long long) stepDeg * 1000 / VS_DEG_PER_SEC;
        if (d->spinMs < 0) {
            d->spinMs += 360000LL / VS_DEG_PER_SEC * 1000;
        }
        d->lastIdx = -1;                     /* 强制下一拍重画（暂停也刷） */
        d->lastSrcVer = -1;
        const int ang = (int) ((d->spinMs * VS_DEG_PER_SEC / 1000) % 360);
        pthread_mutex_unlock(&d->mx);
        LOGD("vinyl: 单步 %d 度 -> 角度 %d 度（强制重画一帧）", stepDeg, ang);
    }

    /* ---- 1) 上屏（UI 线程；拷贝/交接 + invalidate） ---- */
    uint8_t *pub = NULL;
    pthread_mutex_lock(&d->mx);
    if (d->havePending && d->host != NULL && d->hostBmp != NULL) {
        pub = d->pending;
        d->pending = NULL;
        d->havePending = false;
    }
    const int n = d->n;
    const bool hostOk = (d->host != NULL) && (d->hostBmp != NULL);
    const bool dumpPub = d->dumpOn && (d->dumpN < VS_DUMP_MAX);   /* 埋点：本拍是否 dump 上屏位图 */
    pthread_mutex_unlock(&d->mx);

    if (pub != NULL && hostOk) {
        const long long p0 = vsNowMs();
        if (VS_SWAP_BITMAP == 0) {
            /* 模式 0：原地写进那张位图（零分配）；首帧先交出去一次，之后只 invalidate。
             * 注意：pub 指向**复用的**双缓冲（d->wbuf[i]），**不能 free**（上一版就是这么崩的）。 */
            memcpy(d->hostBmp->data, pub, (size_t) n * n * 4);
            d->hostBmp->type |= VS_ALPHA_FLAG;
            if (dumpPub) {
                /* 埋点：控件将显示的那张位图内容（memcpy 之后） */
                vsDumpFile("pub", d->frames, d->lastIdx < 0 ? 0 : d->lastIdx, d->hostBmp->data, n);
            }
            if (!d->handed) {
                d->host->setBackgroundBmp(d->hostBmp);   /* 所有权移交框架（只交一次） */
                d->handed = true;
            } else {
                /* 只脏化**本控件自己的矩形**。
                 * ⚠️ 2026-09-22 真机发现：原口径 `getAbsolutePosition()` 下屏幕只有一块区域刷新
                 * （实测：3~6 点方向 12fps、其余 1fps）——怀疑该 API 把父容器偏移又叠了一次。
                 * 故加运行期口径开关（/tmp/vinyl_inv），三种口径可现场对照（见 vsInvMode）。 */
                /* ✅ 默认（gameview 口径，已修复）：翻 invalid 状态 → 框架按控件（整块）重画，
                 * 不再传任何坐标（getAbsolutePosition / 绝对矩形一律不用）。 */
                const int mode = vsInvMode();
                if (mode == 1) {
                    /* 对照口径 1：本地全幅矩形（实测与默认等效） */
                    LayoutPosition loc;
                    loc.mLeft = 0;
                    loc.mTop = 0;
                    loc.mWidth = d->host->getPosition().mWidth;
                    loc.mHeight = d->host->getPosition().mHeight;
                    d->host->invalidate(&loc);
                } else if (mode == 2) {
                    /* 对照口径 2：整页矩形（实测也等效，代价略高） */
                    LayoutPosition pg;
                    pg.mLeft = 0;
                    pg.mTop = 0;
                    pg.mWidth = 1280;
                    pg.mHeight = 800;
                    d->host->invalidate(&pg);
                } else {
                    d->host->setInvalid(!d->host->isInvalid());
                }
                if (vsNowMs() - d->invLogMs > 1000) {   /* 每秒一条，便于与屏幕变化区域对照 */
                    d->invLogMs = vsNowMs();
                    const LayoutPosition p = d->host->getPosition();
                    LOGD("vinyl: 刷新 mode=%d（0=setInvalid翻转/1=本地矩形/2=整页）控件pos=(%d,%d %dx%d)",
                         mode, p.mLeft, p.mTop, p.mWidth, p.mHeight);
                }
            }
        } else {
            /* 模式 1：本帧缓冲直接包成新位图换给控件（框架释放旧的） */
            bitmap_t *b = new bitmap_t;
            memset(b, 0, sizeof(bitmap_t));
            b->type = VS_ALPHA_FLAG;
            b->bits = 32;
            b->bytes = 4;
            b->alpha = 1;
            b->width = (uint32_t) n;
            b->height = (uint32_t) n;
            b->pitch = (uint32_t) (n * 4);
            b->data = pub;                       /* 内存直接交给框架（此处不拷贝） */
            if (!d->handed && d->hostBmp != NULL) {
                if (d->hostBmp->data != NULL) {
                    free(d->hostBmp->data);      /* 模式 1：attach 时那张空白图我方释放 */
                    d->hostBmp->data = NULL;
                }
                delete d->hostBmp;
            }
            d->host->setBackgroundBmp(b);
            d->hostBmp = b;                      /* 借用指针更新（框架所有） */
            d->handed = true;
        }
        pthread_mutex_lock(&d->mx);
        ++d->frames;
        if (d->firstPubMs == 0) {
            d->firstPubMs = vsNowMs();
        }
        d->lastPubMs = (int) (vsNowMs() - p0);
        const int fr = d->frames;
        const int ang = (int) ((d->spinMs * VS_DEG_PER_SEC / 1000) % 360);
        const int rms = d->lastRotMs;
        const long long el = vsNowMs() - d->firstPubMs;
        pthread_mutex_unlock(&d->mx);
        if (fr == 1 || (fr % 100) == 0) {
            const int f10 = (el > 1000) ? (int) ((long long) fr * 10000 / el) : 0;
            LOGD("vinyl: 上屏第 %d 帧（上屏 %dms 旋转 %dms 角度 %d 度 fps=%d.%d）", fr, d->lastPubMs,
                 rms, ang, f10 / 10, f10 % 10);
        }
        pub = NULL;
    }

    /* ---- 2) 决定是否投递下一帧（只在上一帧算完时投；角度已由时间定） ---- */
    int srcVer = 0;
    int idx = 0;
    bool post = false;
    pthread_mutex_lock(&d->mx);
    if (d->host != NULL && d->srcVer > 0 && !d->busy) {
        srcVer = d->srcVer;
        idx = (int) (((d->spinMs * VS_DEG_PER_SEC) % 360000LL) * VS_SIN_N / 360000LL);
        post = d->playing || (srcVer != d->lastSrcVer) || (idx != d->lastIdx);
        if (post) {
            d->busy = true;
            d->lastIdx = idx;
            d->lastSrcVer = srcVer;
        }
    }
    pthread_mutex_unlock(&d->mx);
    if (!post) {
        return;                                  /* 静止且封面没变：不重算（停转） */
    }

    uint8_t *buf = NULL;
    if (VS_SWAP_BITMAP == 0) {
        /* 双缓冲：本帧写 buf[1-上次]，与 UI 正在拷贝的那块不同（busy 握手保证不撞） */
        buf = d->wbuf[1 - d->wbufCur];
        d->wbufCur = 1 - d->wbufCur;
    } else {
        buf = (uint8_t *) malloc((size_t) n * n * 4);
    }
    if (buf == NULL) {
        pthread_mutex_lock(&d->mx);
        d->busy = false;
        pthread_mutex_unlock(&d->mx);
        return;
    }
    VinylWorker::instance().post([d, srcVer, idx, n, buf]() {
        doRotate(d, srcVer, idx, n, buf);
    });
}

bool VinylSpin::attached() const {
    return mImpl->host != NULL;
}

bool VinylSpin::hasCover() const {
    return mImpl->srcVer > 0;
}

int VinylSpin::angleDeg() const {
    return (int) ((mImpl->spinMs * VS_DEG_PER_SEC / 1000) % 360);
}

int VinylSpin::frames() const {
    return mImpl->frames;
}

int VinylSpin::fpsX10() const {
    Impl *d = mImpl;
    long long el = 0;
    int fr = 0;
    pthread_mutex_lock(&d->mx);
    fr = mImpl->frames;
    if (d->firstPubMs > 0) {
        el = vsNowMs() - d->firstPubMs;      /* 从首帧算起的实测帧率 */
    }
    pthread_mutex_unlock(&d->mx);
    if (el < 1000 || fr <= 1) {
        return 0;
    }
    return (int) ((long long) fr * 10000 / el);
}

int VinylSpin::lastRotMs() const {
    return mImpl->lastRotMs;
}

int VinylSpin::lastPubMs() const {
    return mImpl->lastPubMs;
}

int VinylSpin::mode() const {
    return VS_SWAP_BITMAP;
}

bool VinylSpin::dumpEnabled() const {
    return mImpl->dumpOn;
}

int VinylSpin::dumpCount() const {
    return mImpl->dumpN;
}

int VinylSpin::backend() const {
    return mImpl->backend;
}

} /* namespace zk */
