/*
 * zk_blur_bench.cpp - 高斯模糊各档位实测（真机 C906 用；PC 也能跑）
 *
 * 三段（由 argv 选）：
 *   默认（medium）：1280x800 目标、各档位计时段（无参考图）
 *   lite  ：只跑「铺底推荐口径」几个组合（含缩图输出），秒级
 *   base  ：慢基线（朴素二维 / 分离式 float 全尺寸）
 *   full  ：在 medium 之上再加全尺寸参考误差
 *
 * 输出逐行：
 *   BENCH <tag> mode=<名> down=<d> up=<d> r=<r> src=<WxH> dst=<WxH real=WxH> ms_min=<> ms_avg=<> reps=<>
 *   ERR   <tag> modeA=.. vs modeB=.. r=<r> dst=<WxH> err_max=<> err_avg=<>
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#if defined(_WIN32)
#include <windows.h>
#endif

#include "zk/zk_blur.h"

static long long now_ms(void) {
#if defined(_WIN32)
    /* PC 自测用；真机走 POSIX 分支 */
    LARGE_INTEGER fq;
    LARGE_INTEGER cv;
    QueryPerformanceFrequency(&fq);
    QueryPerformanceCounter(&cv);
    return (long long) ((double) cv.QuadPart * 1000.0 / (double) fq.QuadPart);
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long) ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
#endif
}

/** 造一张「类封面」测试图：渐变 + 两个色块圆 + 细噪声（有高频，模糊差别看得见） */
static uint8_t *makeSrc(int w, int h) {
    uint8_t *buf = (uint8_t *) malloc((size_t) w * h * 4);
    if (buf == NULL) {
        return NULL;
    }
    unsigned int seed = 12345u;
    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            uint8_t *p = buf + ((size_t) y * w + x) * 4;
            const int gx = x * 255 / (w > 1 ? w - 1 : 1);
            const int gy = y * 255 / (h > 1 ? h - 1 : 1);
            int b = 40 + gx / 2;
            int g = 30 + gy / 2;
            int r = 60;
            const int cx1 = w / 3;
            const int cy1 = h / 2;
            const int cx2 = (w * 2) / 3;
            const int cy2 = h / 3;
            if ((x - cx1) * (x - cx1) + (y - cy1) * (y - cy1) < (w / 6) * (w / 6)) {
                r = 230;
                g = 90;
                b = 40;
            }
            if ((x - cx2) * (x - cx2) + (y - cy2) * (y - cy2) < (w / 8) * (w / 8)) {
                r = 40;
                g = 200;
                b = 220;
            }
            seed = seed * 1103515245u + 12345u;
            const int n = (int) ((seed >> 16) & 0x1F) - 16;
            p[0] = (uint8_t) (b + n);
            p[1] = (uint8_t) (g + n);
            p[2] = (uint8_t) (r + n / 2);
            p[3] = 255;
        }
    }
    return buf;
}

static int blurInto(const uint8_t *src, int sw, int sh, int radius, int mode, int down,
                    uint8_t *dst, int dw, int dh, int upBack, int *outW, int *outH) {
    zk_blur_opts_t o;
    zk_blur_opts_default(&o);
    o.mode = mode;
    o.down = down;
    o.upBack = upBack;
    return zk_blur_prep(src, sw, sh, 0, radius, dst, dw, dh, 0, &o, outW, outH);
}

static void runTimingEx(const char *tag, const uint8_t *src, int sw, int sh, int radius,
                        int mode, int down, int dw, int dh, int reps, int upBack) {
    uint8_t *dst = (uint8_t *) malloc((size_t) dw * dh * 4);
    if (dst == NULL) {
        printf("BENCH %s FAIL alloc\n", tag);
        return;
    }
    long long best = -1;
    long long total = 0;
    int rw = 0;
    int rh = 0;
    for (int i = 0; i < reps; ++i) {
        const long long t0 = now_ms();
        const int rc = blurInto(src, sw, sh, radius, mode, down, dst, dw, dh, upBack, &rw, &rh);
        const long long t1 = now_ms();
        if (rc != 0) {
            printf("BENCH %s FAIL rc=%d\n", tag, rc);
            free(dst);
            return;
        }
        if (best < 0 || (t1 - t0) < best) {
            best = t1 - t0;
        }
        total += (t1 - t0);
    }
    printf("BENCH %s mode=%s down=%d up=%d r=%d src=%dx%d dst=%dx%d real=%dx%d ms_min=%lld "
           "ms_avg=%lld reps=%d\n",
           tag, zk_blur_mode_name(zk_blur_mode_active(mode)), down, upBack, radius, sw, sh, dw, dh,
           rw, rh, best, total / reps, reps);
    fflush(stdout);
    free(dst);
}

static void runTiming(const char *tag, const uint8_t *src, int sw, int sh, int radius, int mode,
                      int down, int dw, int dh, int reps) {
    runTimingEx(tag, src, sw, sh, radius, mode, down, dw, dh, reps, 1);
}

/** 正确性：同尺寸同参数下，模式 A 与模式 B 的逐像素 RGB 差 */
static void runErr(const char *tag, const uint8_t *src, int sw, int sh, int radius, int modeA,
                   int downA, int modeB, int downB, int dw, int dh, int upBack) {
    const size_t bytes = (size_t) dw * dh * 4;
    uint8_t *a = (uint8_t *) malloc(bytes);
    uint8_t *b = (uint8_t *) malloc(bytes);
    if (a == NULL || b == NULL) {
        printf("ERR %s FAIL alloc\n", tag);
        free(a);
        free(b);
        return;
    }
    int aw = 0;
    int ah = 0;
    int bw = 0;
    int bh = 0;
    if (blurInto(src, sw, sh, radius, modeA, downA, a, dw, dh, upBack, &aw, &ah) != 0 ||
            blurInto(src, sw, sh, radius, modeB, downB, b, dw, dh, upBack, &bw, &bh) != 0) {
        printf("ERR %s FAIL rc\n", tag);
        free(a);
        free(b);
        return;
    }
    if (aw != bw || ah != bh) {
        printf("ERR %s SIZE MISMATCH %dx%d vs %dx%d\n", tag, aw, ah, bw, bh);
        free(a);
        free(b);
        return;
    }
    long long acc = 0;
    int mx = 0;
    const long long n = (long long) aw * ah * 3;
    for (long long i = 0; i < n; ++i) {
        const long long px = i / 3;
        const int c = (int) (i % 3);
        /* dst 以 dw 为行距写（stride=0 -> dw*4） */
        const long long row = px / aw;
        const long long col = px % aw;
        const long long off = (row * dw + col) * 4 + c;
        const int d = (int) a[off] - (int) b[off];
        const int ad = (d < 0) ? -d : d;
        if (ad > mx) {
            mx = ad;
        }
        acc += ad;
    }
    printf("ERR   %s modeA=%s/d%d vs modeB=%s/d%d r=%d dst=%dx%d up=%d err_max=%d err_avg=%d\n",
           tag, zk_blur_mode_name(zk_blur_mode_active(modeA)), downA,
           zk_blur_mode_name(zk_blur_mode_active(modeB)), downB, radius, aw, ah, upBack, mx,
           (int) (acc / n));
    fflush(stdout);
    free(a);
    free(b);
}

static void header(void) {
    printf("# zk_blur bench rvv=%d recommended=%s %s %s\n", zk_blur_has_rvv(),
           zk_blur_mode_name(zk_blur_mode_recommended()), __DATE__, __TIME__);
    FILE *f = fopen("/proc/cpuinfo", "r");
    if (f != NULL) {
        char line[256];
        while (fgets(line, sizeof(line), f) != NULL) {
            if (strncmp(line, "isa", 3) == 0) {
                printf("# cpuinfo %s", line);
            }
        }
        fclose(f);
    }
}

int main(int argc, char **argv) {
    int W = 1280;
    int H = 800;
    int full = 0;
    int lite = 0;
    int base = 0;
    if (argc >= 3) {
        W = atoi(argv[1]);
        H = atoi(argv[2]);
    }
    for (int i = 3; i < argc; ++i) {
        if (strcmp(argv[i], "full") == 0) {
            full = 1;
        } else if (strcmp(argv[i], "lite") == 0) {
            lite = 1;
        } else if (strcmp(argv[i], "base") == 0) {
            base = 1;
        }
    }
    header();
    uint8_t *src = makeSrc(W, H);
    if (src == NULL) {
        printf("FAIL makeSrc\n");
        return 1;
    }

    /* ---------------- base：慢基线（各 1 次） ---------------- */
    if (base) {
        runTiming("base_naive2d_r8", src, W, H, 8, ZK_BLUR_NAIVE2D, 1, W, H, 1);
        runTiming("base_naive2d_r8_q", src, W, H, 8, ZK_BLUR_NAIVE2D, 1, W / 4, H / 4, 1);
        runTiming("base_sepfloat_r32", src, W, H, 32, ZK_BLUR_SEP_FLOAT, 1, W, H, 1);
        runTiming("base_sepfloat_r32_q", src, W, H, 32, ZK_BLUR_SEP_FLOAT, 1, W / 4, H / 4, 1);
        runTiming("base_sepfixed_r32_q", src, W, H, 32, ZK_BLUR_SEP_FIXED, 1, W / 4, H / 4, 1);
        free(src);
        return 0;
    }

    /* ---------------- lite：铺底推荐口径 ---------------- */
    if (lite) {
        /* 全尺寸输出（upBack=1）：一屏一张 1280x800 铺底 */
        runTimingEx("P_full_d4_up", src, W, H, 32, ZK_BLUR_BOX3, 4, W, H, 3, 1);
        runTimingEx("P_full_d4_up_rvv", src, W, H, 32, ZK_BLUR_RVV, 4, W, H, 3, 1);
        runTimingEx("P_full_d1_up", src, W, H, 32, ZK_BLUR_BOX3, 1, W, H, 3, 1);
        /* 缩图输出（upBack=0）：300x200 铺底，由显示层拉伸 */
        runTimingEx("P_q_d4_noup", src, W, H, 32, ZK_BLUR_BOX3, 4, W, H, 3, 0);
        runTimingEx("P_q_d4_noup_rvv", src, W, H, 32, ZK_BLUR_RVV, 4, W, H, 3, 0);
        runTimingEx("P_q_d1_r8", src, W, H, 8, ZK_BLUR_BOX3, 1, W / 4, H / 4, 3, 0);
        runTimingEx("P_q_d1_r8_rvv", src, W, H, 8, ZK_BLUR_RVV, 1, W / 4, H / 4, 3, 0);
        runTimingEx("P_q_d2_r8", src, W, H, 8, ZK_BLUR_BOX3, 2, W / 2, H / 2, 3, 0);
        runTimingEx("P_h_d1_r16", src, W, H, 16, ZK_BLUR_BOX3, 1, W / 2, H / 2, 3, 0);
        /* 真实形态：640x640 封面 -> 320x200 铺底（缩图） */
        {
            uint8_t *cover = makeSrc(640, 640);
            if (cover != NULL) {
                runTimingEx("P_cover640_q_r8", cover, 640, 640, 8, ZK_BLUR_BOX3, 1, W / 4, H / 4,
                            3, 0);
                runTimingEx("P_cover640_q_r8_rvv", cover, 640, 640, 8, ZK_BLUR_RVV, 1, W / 4,
                            H / 4, 3, 0);
                runTimingEx("P_cover640_q_d4", cover, 640, 640, 32, ZK_BLUR_BOX3, 4, W / 4, H / 4,
                            3, 0);
                runTimingEx("P_cover640_full_d4", cover, 640, 640, 32, ZK_BLUR_BOX3, 4, W, H, 3,
                            1);
                free(cover);
            }
        }
        /* 缩图口径的正确性：320x200 铺底（r=8） vs 同尺寸真高斯 */
        {
            uint8_t *cov = makeSrc(640, 640);
            if (cov != NULL) {
                runErr("q_r8", cov, 640, 640, 8, ZK_BLUR_BOX3, 1, ZK_BLUR_SEP_FLOAT, 1, W / 4,
                       H / 4, 0);
                runErr("q_r8", cov, 640, 640, 8, ZK_BLUR_RVV, 1, ZK_BLUR_SEP_FLOAT, 1, W / 4, H / 4,
                       0);
                runErr("q_r8_d4", cov, 640, 640, 8, ZK_BLUR_BOX3, 4, ZK_BLUR_SEP_FLOAT, 4, W / 4,
                       H / 4, 0);
                free(cov);
            }
        }
        free(src);
        return 0;
    }

    /* ---------------- medium / full：1280x800 各档位 ---------------- */
    if (full) {
        runTiming("sepfloat_full", src, W, H, 32, ZK_BLUR_SEP_FLOAT, 1, W, H, 1);
    }
    runTiming("sepfixed_full", src, W, H, 32, ZK_BLUR_SEP_FIXED, 1, W, H, 2);
    runTiming("box3_full_r32", src, W, H, 32, ZK_BLUR_BOX3, 1, W, H, 3);
    runTiming("box3_full_r16", src, W, H, 16, ZK_BLUR_BOX3, 1, W, H, 3);
    runTiming("rvv_full_r32", src, W, H, 32, ZK_BLUR_RVV, 1, W, H, 3);
    runTiming("box3_d2_r16", src, W, H, 32, ZK_BLUR_BOX3, 2, W, H, 3);
    runTiming("box3_d4_r8", src, W, H, 32, ZK_BLUR_BOX3, 4, W, H, 3);
    runTiming("box3_d8_r4", src, W, H, 32, ZK_BLUR_BOX3, 8, W, H, 3);
    runTiming("rvv_d2_r16", src, W, H, 32, ZK_BLUR_RVV, 2, W, H, 3);
    runTiming("rvv_d4_r8", src, W, H, 32, ZK_BLUR_RVV, 4, W, H, 3);
    runTiming("rvv_d8_r4", src, W, H, 32, ZK_BLUR_RVV, 8, W, H, 3);
    runTiming("box3_d4_r8_p1", src, W, H, 32, ZK_BLUR_BOX3, 4, W, H, 3);
    runTiming("rvv_d4_r8_p1", src, W, H, 32, ZK_BLUR_RVV, 4, W, H, 3);
    /* 小尺寸对照 */
    runTiming("naive2d_small", src, W, H, 8, ZK_BLUR_NAIVE2D, 1, 320, 200, 1);
    runErr("r8", src, W, H, 8, ZK_BLUR_SEP_FLOAT, 1, ZK_BLUR_NAIVE2D, 1, 320, 200, 1);
    runErr("r8", src, W, H, 8, ZK_BLUR_SEP_FIXED, 1, ZK_BLUR_NAIVE2D, 1, 320, 200, 1);
    runErr("r8", src, W, H, 8, ZK_BLUR_BOX3, 1, ZK_BLUR_NAIVE2D, 1, 320, 200, 1);
    runErr("r8", src, W, H, 8, ZK_BLUR_RVV, 1, ZK_BLUR_NAIVE2D, 1, 320, 200, 1);
    runErr("r32", src, W, H, 32, ZK_BLUR_SEP_FIXED, 1, ZK_BLUR_SEP_FLOAT, 1, 320, 200, 1);
    runErr("r32", src, W, H, 32, ZK_BLUR_BOX3, 1, ZK_BLUR_SEP_FLOAT, 1, 320, 200, 1);
    runErr("r32", src, W, H, 32, ZK_BLUR_RVV, 1, ZK_BLUR_SEP_FLOAT, 1, 320, 200, 1);
    runErr("r32d4", src, W, H, 32, ZK_BLUR_BOX3, 4, ZK_BLUR_SEP_FLOAT, 1, 320, 200, 1);
    runErr("r32d4", src, W, H, 32, ZK_BLUR_RVV, 4, ZK_BLUR_SEP_FLOAT, 1, 320, 200, 1);

    printf("MEM note: prep 平面池 2*(tw*th*4) + tmp (tw*th) + crop (cw*ch) + 输出缓冲\n");
    free(src);
    return 0;
}
