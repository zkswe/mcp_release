/*
 * zk_blur.cpp - 高斯模糊实现（标量档位 + 调度）
 *
 * 档位实现要点（不依赖第三方库）：
 *   0 NAIVE2D     : 二维直接卷积，O(r^2)/像素 —— 只做正确性基线
 *   1 SEP_FLOAT   : 分离式两趟（横 + 竖），float 核（sigma = radius/2）
 *   2 SEP_FIXED   : 分离式两趟，定点 Q8 核（sum = 256）+ 256 项乘积查表 + 移位代替除法
 *   3 BOX3        : 三次盒式近似（滑窗 O(1)/像素，倒数乘 + 移位），整数，最快
 *   4 RVV         : BOX3 的向量化版（竖趟 + 下采样走 RVV 0.7.1）；无 RVV 编译时退回 BOX3
 *
 * 通用约定：
 *   · 4 字节 BGRA -> 拆成 4 张 8bit 平面逐张处理 -> 合回（平面化后滑窗每像素只做
 *     一次加一次减，且天然可向量化）；
 *   · 边缘一律 clamp（复制边），与铺底视觉口径一致（不出暗边）。
 */
#include "zk/zk_blur.h"

#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#if defined(_WIN32)
#include <windows.h>
#endif

/* 平台适配层提供的 RVV 加速（无 RVV 时返回 0 / 空实现） */
extern "C" {
int zk_rvv_available(void);
int zk_rvv_box_v_plane(const uint8_t *src, uint8_t *dst, int w, int h, int r, uint32_t recip,
                       int shift);
int zk_rvv_downsample_plane(const uint8_t *src, int w, int h, int f, uint8_t *dst, int dw,
                            int dh);
}

#define ZK_BLUR_MAX_RADIUS   128
#define ZK_BLUR_BOX_SHIFT    16

/* ============================ 小工具 ============================ */
static zk_blur_log_fn gLog = NULL;

static long long zk_now_us(void) {
#if defined(_WIN32)
    /* PC 自测用（真机走 POSIX 分支）；不参与真机验收口径 */
    LARGE_INTEGER fq;
    LARGE_INTEGER cv;
    QueryPerformanceFrequency(&fq);
    QueryPerformanceCounter(&cv);
    return (long long) ((double) cv.QuadPart * 1000000.0 / (double) fq.QuadPart);
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long) ts.tv_sec * 1000000 + ts.tv_nsec / 1000;
#endif
}

static void zk_log(const char *fmt, ...) {
    if (gLog == NULL) {
        return;
    }
    char buf[256];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    gLog(buf);
}

static inline int zk_clampi(int v, int lo, int hi) {
    return (v < lo) ? lo : ((v > hi) ? hi : v);
}

static inline uint8_t zk_clamp255(int v) {
    return (uint8_t) ((v < 0) ? 0 : ((v > 255) ? 255 : v));
}

/* ============================ 平面缓冲 ============================ */
typedef struct {
    uint8_t *ch[4];
    uint8_t *pool;
    int w;
    int h;
} ZkPlanes;

static int zk_planes_alloc(ZkPlanes *p, int w, int h) {
    p->w = w;
    p->h = h;
    p->pool = (uint8_t *) malloc((size_t) w * h * 4);
    if (p->pool == NULL) {
        return -1;
    }
    for (int c = 0; c < 4; ++c) {
        p->ch[c] = p->pool + (size_t) c * w * h;
    }
    return 0;
}

static void zk_planes_free(ZkPlanes *p) {
    if (p->pool != NULL) {
        free(p->pool);
        p->pool = NULL;
    }
    for (int c = 0; c < 4; ++c) {
        p->ch[c] = NULL;
    }
}

/** 交错 BGRA -> 4 平面 */
static void zk_split(const uint8_t *src, int w, int h, int stride, ZkPlanes *p) {
    for (int y = 0; y < h; ++y) {
        const uint8_t *s = src + (size_t) y * stride;
        for (int c = 0; c < 4; ++c) {
            uint8_t *d = p->ch[c] + (size_t) y * w;
            const uint8_t *sp = s + c;
            for (int x = 0; x < w; ++x) {
                d[x] = sp[x * 4];
            }
        }
    }
}

/** 4 平面 -> 交错 BGRA */
static void zk_merge(const ZkPlanes *p, uint8_t *dst, int stride) {
    const int w = p->w;
    const int h = p->h;
    for (int y = 0; y < h; ++y) {
        uint8_t *d = dst + (size_t) y * stride;
        for (int c = 0; c < 4; ++c) {
            const uint8_t *s = p->ch[c] + (size_t) y * w;
            uint8_t *dp = d + c;
            for (int x = 0; x < w; ++x) {
                dp[x * 4] = s[x];
            }
        }
    }
}

/* ============================ 核 ============================ */
/** float 高斯核（sigma = radius/2，归一化到 1.0），调用方 free */
static float *zk_kernel_f(int radius, int *outN) {
    const int n = 2 * radius + 1;
    float *k = (float *) malloc(sizeof(float) * (size_t) n);
    if (k == NULL) {
        return NULL;
    }
    const float sigma = (radius > 0) ? ((float) radius / 2.0f) : 1.0f;
    const float inv = 1.0f / (2.0f * sigma * sigma);
    float sum = 0.0f;
    for (int i = 0; i < n; ++i) {
        const float d = (float) (i - radius);
        k[i] = expf(-d * d * inv);
        sum += k[i];
    }
    for (int i = 0; i < n; ++i) {
        k[i] /= sum;
    }
    *outN = n;
    return k;
}

/** 定点 Q8 核（sum = 256，最大那项吸收舍入误差），调用方 free */
static int32_t *zk_kernel_q8(int radius, int *outN) {
    int n = 0;
    float *kf = zk_kernel_f(radius, &n);
    if (kf == NULL) {
        return NULL;
    }
    int32_t *kq = (int32_t *) malloc(sizeof(int32_t) * (size_t) n);
    if (kq == NULL) {
        free(kf);
        return NULL;
    }
    int32_t acc = 0;
    int maxI = 0;
    for (int i = 0; i < n; ++i) {
        kq[i] = (int32_t) (kf[i] * 256.0f + 0.5f);
        acc += kq[i];
        if (kq[i] > kq[maxI]) {
            maxI = i;
        }
    }
    kq[maxI] += (256 - acc);
    if (kq[maxI] < 0) {
        kq[maxI] = 0;
    }
    free(kf);
    *outN = n;
    return kq;
}

/* ============================ 档位 0：朴素二维 ============================ */
static void zk_naive2d_plane(const uint8_t *src, uint8_t *dst, int w, int h, int radius) {
    int n = 0;
    float *k = zk_kernel_f(radius, &n);
    if (k == NULL) {
        memcpy(dst, src, (size_t) w * h);
        return;
    }
    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            float a = 0.0f;
            for (int j = 0; j < n; ++j) {
                const uint8_t *row = src + (size_t) zk_clampi(y + j - radius, 0, h - 1) * w;
                const float kj = k[j];
                for (int i = 0; i < n; ++i) {
                    a += (float) row[zk_clampi(x + i - radius, 0, w - 1)] * kj * k[i];
                }
            }
            dst[(size_t) y * w + x] = zk_clamp255((int) (a + 0.5f));
        }
    }
    free(k);
}

/* ============================ 档位 1：分离式 float ============================ */
static void zk_sep_float_plane(const uint8_t *src, uint8_t *dst, int w, int h, int radius,
                               uint8_t *tmp) {
    int n = 0;
    float *k = zk_kernel_f(radius, &n);
    if (k == NULL) {
        memcpy(dst, src, (size_t) w * h);
        return;
    }
    for (int y = 0; y < h; ++y) {                       /* 横趟 */
        const uint8_t *s = src + (size_t) y * w;
        uint8_t *d = tmp + (size_t) y * w;
        for (int x = 0; x < w; ++x) {
            float a = 0.0f;
            for (int i = 0; i < n; ++i) {
                a += (float) s[zk_clampi(x + i - radius, 0, w - 1)] * k[i];
            }
            d[x] = zk_clamp255((int) (a + 0.5f));
        }
    }
    for (int y = 0; y < h; ++y) {                       /* 竖趟 */
        uint8_t *d = dst + (size_t) y * w;
        for (int x = 0; x < w; ++x) {
            float a = 0.0f;
            for (int j = 0; j < n; ++j) {
                a += (float) tmp[(size_t) zk_clampi(y + j - radius, 0, h - 1) * w + x] * k[j];
            }
            d[x] = zk_clamp255((int) (a + 0.5f));
        }
    }
    free(k);
}

/* ============================ 档位 2：分离式定点 + 查表 ============================ */
/* 乘积表：lut[k*256 + v] = v * kq[k]（Q8），uint16 足够（255*256 = 65280）；
 * 内层循环只剩「查表 + 累加 + 移位」，没有乘法没有除法。 */
static uint16_t *zk_mul_lut(const int32_t *kq, int n) {
    uint16_t *lut = (uint16_t *) malloc(sizeof(uint16_t) * 256u * (size_t) n);
    if (lut == NULL) {
        return NULL;
    }
    for (int i = 0; i < n; ++i) {
        uint16_t *row = lut + (size_t) i * 256;
        const int32_t kv = kq[i];
        for (int v = 0; v < 256; ++v) {
            row[v] = (uint16_t) (v * kv);
        }
    }
    return lut;
}

static void zk_sep_fixed_plane(const uint8_t *src, uint8_t *dst, int w, int h, int radius,
                               uint8_t *tmp) {
    int n = 0;
    int32_t *kq = zk_kernel_q8(radius, &n);
    if (kq == NULL) {
        memcpy(dst, src, (size_t) w * h);
        return;
    }
    uint16_t *lut = zk_mul_lut(kq, n);
    free(kq);
    if (lut == NULL) {
        memcpy(dst, src, (size_t) w * h);
        return;
    }
    for (int y = 0; y < h; ++y) {                       /* 横趟 */
        const uint8_t *s = src + (size_t) y * w;
        uint8_t *d = tmp + (size_t) y * w;
        for (int x = 0; x < w; ++x) {
            uint32_t acc = 0;
            for (int i = 0; i < n; ++i) {
                acc += lut[(size_t) i * 256 + s[zk_clampi(x + i - radius, 0, w - 1)]];
            }
            d[x] = (uint8_t) ((acc + 128) >> 8);
        }
    }
    for (int y = 0; y < h; ++y) {                       /* 竖趟 */
        uint8_t *d = dst + (size_t) y * w;
        for (int x = 0; x < w; ++x) {
            uint32_t acc = 0;
            for (int i = 0; i < n; ++i) {
                acc += lut[(size_t) i * 256 +
                           tmp[(size_t) zk_clampi(y + i - radius, 0, h - 1) * w + x]];
            }
            d[x] = (uint8_t) ((acc + 128) >> 8);
        }
    }
    free(lut);
}

/* ============================ 档位 3：三次盒式 ============================ */
/** 倒数乘系数：win = 2r+1 -> (sum * recip) >> 16 约等于 sum / win（相对误差 < 1/1000） */
static uint32_t zk_recip(int win) {
    return (uint32_t) (((1u << ZK_BLUR_BOX_SHIFT) + (uint32_t) win / 2) / (uint32_t) win);
}

static inline uint8_t zk_div_recip(uint32_t sum, uint32_t recip) {
    return (uint8_t) (((sum * recip) + (1u << (ZK_BLUR_BOX_SHIFT - 1))) >> ZK_BLUR_BOX_SHIFT);
}

/** 横趟盒式（滑窗，clamp 边） */
static void zk_box_h_plane(const uint8_t *src, uint8_t *dst, int w, int h, int r,
                           uint32_t recip) {
    for (int y = 0; y < h; ++y) {
        const uint8_t *s = src + (size_t) y * w;
        uint8_t *d = dst + (size_t) y * w;
        uint32_t sum = 0;
        for (int i = -r; i <= r; ++i) {
            sum += s[zk_clampi(i, 0, w - 1)];
        }
        d[0] = zk_div_recip(sum, recip);
        for (int x = 1; x < w; ++x) {
            sum += s[zk_clampi(x + r, 0, w - 1)];
            sum -= s[zk_clampi(x - r - 1, 0, w - 1)];
            d[x] = zk_div_recip(sum, recip);
        }
    }
}

/** 竖趟盒式（整行加减，天然可向量化；RVV 版就是替换这个函数） */
static void zk_box_v_plane(const uint8_t *src, uint8_t *dst, int w, int h, int r,
                           uint32_t recip) {
    uint32_t *sum = (uint32_t *) malloc(sizeof(uint32_t) * (size_t) w);
    if (sum == NULL) {
        return;
    }
    for (int x = 0; x < w; ++x) {
        sum[x] = 0;
    }
    for (int i = -r; i <= r; ++i) {
        const uint8_t *row = src + (size_t) zk_clampi(i, 0, h - 1) * w;
        for (int x = 0; x < w; ++x) {
            sum[x] += row[x];
        }
    }
    for (int y = 0; y < h; ++y) {
        uint8_t *d = dst + (size_t) y * w;
        if (y > 0) {
            const uint8_t *add = src + (size_t) zk_clampi(y + r, 0, h - 1) * w;
            const uint8_t *sub = src + (size_t) zk_clampi(y - r - 1, 0, h - 1) * w;
            for (int x = 0; x < w; ++x) {
                sum[x] += add[x];
                sum[x] -= sub[x];
            }
        }
        for (int x = 0; x < w; ++x) {
            d[x] = zk_div_recip(sum[x], recip);
        }
    }
    free(sum);
}

/**
 * 三次盒式（盒宽由 sigma 反推：b = sqrt(12*sigma^2/p + 1)，r = (b-1)/2）。
 * 乒乓：每趟 = 横(pa) + 竖(pb)，依次 pa<->pb 互换；结果拷回 dst。
 * tmp 由调用方给（w*h），本函数另分配一块同尺寸暂存。
 */
static void zk_box3_plane(const uint8_t *src, uint8_t *dst, int w, int h, int radius,
                          uint8_t *tmp, int passes, int useRvv) {
    const float sigma = (radius > 0) ? ((float) radius / 2.0f) : 1.0f;
    const int p = (passes >= 1 && passes <= 3) ? passes : 3;
    const float b = sqrtf(12.0f * sigma * sigma / (float) p + 1.0f);
    int br = (int) ((b - 1.0f) / 2.0f);
    if (br < 1) {
        br = 1;
    }
    if (br > ZK_BLUR_MAX_RADIUS) {
        br = ZK_BLUR_MAX_RADIUS;
    }
    const uint32_t recip = zk_recip(2 * br + 1);
    uint8_t *pb = (uint8_t *) malloc((size_t) w * h);
    if (pb == NULL) {
        memcpy(dst, src, (size_t) w * h);
        return;
    }
    uint8_t *pa = tmp;
    const uint8_t *in = src;
    const int rvv = (useRvv && zk_rvv_available()) ? 1 : 0;
    for (int i = 0; i < p; ++i) {
        zk_box_h_plane(in, pa, w, h, br, recip);            /* 横趟：in -> pa */
        if (!(rvv && zk_rvv_box_v_plane(pa, pb, w, h, br, recip, ZK_BLUR_BOX_SHIFT) == 0)) {
            zk_box_v_plane(pa, pb, w, h, br, recip);        /* 竖趟：pa -> pb */
        }
        in = pb;
        uint8_t *t = pa;                                    /* 换手，下一趟横趟写另一块 */
        pa = pb;
        pb = t;
    }
    memcpy(dst, in, (size_t) w * h);                        /* 结果在 in 指向的块里 */
    free((in == tmp) ? pb : pa);
}

/* ============================ 下采样 / 放大 ============================ */
/** 盒式下采样（f 倍面积平均） */
static void zk_down_box_plane(const uint8_t *src, int w, int h, int f, uint8_t *dst, int dw,
                              int dh, int useRvv) {
    if (f <= 1) {
        const int cw = (dw < w) ? dw : w;
        for (int y = 0; y < dh && y < h; ++y) {
            memcpy(dst + (size_t) y * dw, src + (size_t) y * w, (size_t) cw);
        }
        return;
    }
    if (useRvv && zk_rvv_available()) {
        if (zk_rvv_downsample_plane(src, w, h, f, dst, dw, dh) == 0) {
            return;
        }
    }
    const int area = f * f;
    for (int y = 0; y < dh; ++y) {
        uint8_t *d = dst + (size_t) y * dw;
        for (int x = 0; x < dw; ++x) {
            uint32_t acc = 0;
            for (int j = 0; j < f; ++j) {
                const int yy = y * f + j;
                const uint8_t *row = src + (size_t) ((yy < h) ? yy : (h - 1)) * w;
                for (int i = 0; i < f; ++i) {
                    const int xx = x * f + i;
                    acc += row[(xx < w) ? xx : (w - 1)];
                }
            }
            d[x] = (uint8_t) ((acc + area / 2) / area);
        }
    }
}

/** 双线性重采样（8.8 定点权重）：(sw,sh) -> (dw,dh) */
static void zk_resample_bilinear_plane(const uint8_t *src, int sw, int sh, uint8_t *dst, int dw,
                                       int dh) {
    if (sw == dw && sh == dh) {
        memcpy(dst, src, (size_t) dw * dh);
        return;
    }
    for (int y = 0; y < dh; ++y) {
        int32_t fy = (int32_t) ((((long long) y * 2 + 1) * sh * 128 / dh) - 128);
        int y0 = fy >> 8;
        int wy = fy - (y0 << 8);
        if (y0 < 0) {
            y0 = 0;
            wy = 0;
        }
        const int y1 = (y0 + 1 < sh) ? (y0 + 1) : (sh - 1);
        uint8_t *d = dst + (size_t) y * dw;
        const uint8_t *r0 = src + (size_t) y0 * sw;
        const uint8_t *r1 = src + (size_t) y1 * sw;
        for (int x = 0; x < dw; ++x) {
            int32_t fx = (int32_t) ((((long long) x * 2 + 1) * sw * 128 / dw) - 128);
            int x0 = fx >> 8;
            int wx = fx - (x0 << 8);
            if (x0 < 0) {
                x0 = 0;
                wx = 0;
            }
            const int x1 = (x0 + 1 < sw) ? (x0 + 1) : (sw - 1);
            const int top = r0[x0] * (256 - wx) + r0[x1] * wx;
            const int bot = r1[x0] * (256 - wx) + r1[x1] * wx;
            d[x] = (uint8_t) ((top * (256 - wy) + bot * wy + 32768) >> 16);
        }
    }
}

/* ============================ 单平面总入口 ============================ */
static void zk_blur_plane(const uint8_t *src, uint8_t *dst, int w, int h, int radius, int mode,
                          int down, int upBack, int passes, uint8_t *tmp) {
    const int f = (down >= 1) ? down : 1;
    const int dw = (w + f - 1) / f;
    const int dh = (h + f - 1) / f;
    const int rd = (radius / f >= 1) ? (radius / f) : 1;
    const int useRvv = (mode == ZK_BLUR_RVV);

    if (mode == ZK_BLUR_NAIVE2D) {
        zk_naive2d_plane(src, dst, w, h, radius);
        return;
    }

    uint8_t *small = NULL;
    const uint8_t *in = src;
    int iw = w;
    int ih = h;
    if (f > 1) {
        small = (uint8_t *) malloc((size_t) dw * dh);
        if (small == NULL) {
            return;
        }
        zk_down_box_plane(src, w, h, f, small, dw, dh, useRvv);
        iw = dw;
        ih = dh;
        in = small;
    }
    uint8_t *base = (uint8_t *) malloc((size_t) iw * ih);
    uint8_t *base2 = (uint8_t *) malloc((size_t) iw * ih);
    if (base == NULL || base2 == NULL) {
        free(base);
        free(base2);
        free(small);
        return;
    }
    switch (mode) {
    case ZK_BLUR_SEP_FLOAT:
        zk_sep_float_plane(in, base, iw, ih, rd, base2);
        break;
    case ZK_BLUR_SEP_FIXED:
        zk_sep_fixed_plane(in, base, iw, ih, rd, base2);
        break;
    case ZK_BLUR_RVV:
    case ZK_BLUR_BOX3:
    default:
        zk_box3_plane(in, base, iw, ih, rd, base2, passes, useRvv);
        break;
    }
    if (f > 1 && upBack) {
        zk_resample_bilinear_plane(base, iw, ih, dst, w, h);
    } else if (w == iw && h == ih) {
        memcpy(dst, base, (size_t) w * h);
    } else {
        for (int y = 0; y < h && y < ih; ++y) {
            memcpy(dst + (size_t) y * w, base + (size_t) y * iw, (size_t) ((w < iw) ? w : iw));
        }
    }
    free(base);
    free(base2);
    free(small);
}

/* ============================ 公共 API ============================ */
void zk_blur_set_log(zk_blur_log_fn fn) {
    gLog = fn;
}

int zk_blur_has_rvv(void) {
    return zk_rvv_available();
}

int zk_blur_mode_recommended(void) {
    return ZK_BLUR_RVV;             /* 有 RVV 走 RVV；无 RVV 时内部自动退回 BOX3 */
}

int zk_blur_mode_active(int mode) {
    if (mode == ZK_BLUR_MODE_AUTO) {
        mode = zk_blur_mode_recommended();
    }
    if (mode == ZK_BLUR_RVV && !zk_rvv_available()) {
        return ZK_BLUR_BOX3;
    }
    if (mode < 0 || mode >= ZK_BLUR_MODE_MAX) {
        return ZK_BLUR_BOX3;
    }
    return mode;
}

const char *zk_blur_mode_name(int mode) {
    switch (mode) {
    case ZK_BLUR_NAIVE2D:
        return "naive2d";
    case ZK_BLUR_SEP_FLOAT:
        return "sep_float";
    case ZK_BLUR_SEP_FIXED:
        return "sep_fixed_lut";
    case ZK_BLUR_BOX3:
        return "box3_int";
    case ZK_BLUR_RVV:
        return "box3_rvv";
    default:
        return "auto";
    }
}

void zk_blur_opts_default(zk_blur_opts_t *o) {
    if (o == NULL) {
        return;
    }
    o->mode = ZK_BLUR_MODE_AUTO;
    o->down = 4;
    o->upBack = 1;
    o->passes = 3;
    o->threads = 1;
    o->logTime = 0;
}

int zk_blur_bgra(const uint8_t *src, int w, int h, int srcStride, int radius, uint8_t *dst,
                 int dstStride, const zk_blur_opts_t *o) {
    if (src == NULL || dst == NULL || w <= 0 || h <= 0 || radius < 1) {
        return -1;
    }
    if (radius > ZK_BLUR_MAX_RADIUS) {
        radius = ZK_BLUR_MAX_RADIUS;
    }
    zk_blur_opts_t def;
    zk_blur_opts_default(&def);
    const zk_blur_opts_t *op = (o != NULL) ? o : &def;
    const int ss = (srcStride > 0) ? srcStride : w * 4;
    const int ds = (dstStride > 0) ? dstStride : w * 4;
    const int mode = zk_blur_mode_active(op->mode);
    const int down = (op->down > 1) ? op->down : 1;
    const long long t0 = zk_now_us();

    ZkPlanes pin;
    ZkPlanes pout;
    if (zk_planes_alloc(&pin, w, h) != 0) {
        return -2;
    }
    if (zk_planes_alloc(&pout, w, h) != 0) {
        zk_planes_free(&pin);
        return -2;
    }
    uint8_t *tmp = (uint8_t *) malloc((size_t) w * h);
    if (tmp == NULL) {
        zk_planes_free(&pin);
        zk_planes_free(&pout);
        return -2;
    }
    zk_split(src, w, h, ss, &pin);
    for (int c = 0; c < 4; ++c) {
        zk_blur_plane(pin.ch[c], pout.ch[c], w, h, radius, mode, down, op->upBack, op->passes,
                      tmp);
    }
    zk_merge(&pout, dst, ds);
    free(tmp);
    zk_planes_free(&pin);
    zk_planes_free(&pout);
    if (op->logTime) {
        zk_log("zk_blur: %dx%d r=%d %s down=%d -> %lld us", w, h, radius,
               zk_blur_mode_name(mode), down, zk_now_us() - t0);
    }
    return 0;
}

int zk_blur_prep(const uint8_t *src, int w, int h, int srcStride, int radius, uint8_t *dst,
                 int dw, int dh, int dstStride, const zk_blur_opts_t *o, int *outW,
                 int *outH) {
    if (src == NULL || dst == NULL || w <= 0 || h <= 0 || dw <= 0 || dh <= 0 || radius < 1) {
        return -1;
    }
    zk_blur_opts_t def;
    zk_blur_opts_default(&def);
    const zk_blur_opts_t *op = (o != NULL) ? o : &def;
    const int ss = (srcStride > 0) ? srcStride : w * 4;
    const int ds = (dstStride > 0) ? dstStride : dw * 4;
    const int mode = zk_blur_mode_active(op->mode);
    int f = (op->down > 1) ? op->down : 1;
    int tw = dw;                       /* 真实输出尺寸 */
    int th = dh;
    int radiusI = radius;              /* 在输出尺寸下的等效半径 */
    if (!op->upBack) {
        /* 输出缩小图：直接把源缩到小尺寸再糊（先缩后糊），内部不再二次降采样 */
        tw = (dw + f - 1) / f;
        th = (dh + f - 1) / f;
        radiusI = radius * tw / dw;
        f = 1;
    }
    if (radiusI < 1) {
        radiusI = 1;
    }
    const long long t0 = zk_now_us();

    /* 源按 cover 等比裁到目标比例（避免铺底图拉伸变形） */
    const int cw = (w * th > h * tw) ? ((h * tw) / th) : w;
    const int ch = (w * th > h * tw) ? h : ((w * th) / tw);
    const int cx = (w - cw) / 2;
    const int cy = (h - ch) / 2;

    ZkPlanes psrc;
    ZkPlanes pdst;
    if (zk_planes_alloc(&psrc, tw, th) != 0) {
        return -2;
    }
    if (zk_planes_alloc(&pdst, tw, th) != 0) {
        zk_planes_free(&psrc);
        return -2;
    }
    for (int c = 0; c < 4; ++c) {                    /* 取平面 + 裁 + 缩到输出尺寸 */
        uint8_t *crop = (uint8_t *) malloc((size_t) cw * ch);
        if (crop == NULL) {
            zk_planes_free(&psrc);
            zk_planes_free(&pdst);
            return -2;
        }
        for (int y = 0; y < ch; ++y) {
            const uint8_t *srow = src + (size_t) (cy + y) * ss;
            uint8_t *drow = crop + (size_t) y * cw;
            for (int x = 0; x < cw; ++x) {
                drow[x] = srow[(size_t) (cx + x) * 4 + c];
            }
        }
        zk_resample_bilinear_plane(crop, cw, ch, psrc.ch[c], tw, th);
        free(crop);
    }
    uint8_t *tmp = (uint8_t *) malloc((size_t) tw * th);
    if (tmp == NULL) {
        zk_planes_free(&psrc);
        zk_planes_free(&pdst);
        return -2;
    }
    for (int c = 0; c < 4; ++c) {
        zk_blur_plane(psrc.ch[c], pdst.ch[c], tw, th, radiusI, mode, f, 1, op->passes, tmp);
    }
    zk_merge(&pdst, dst, ds);
    free(tmp);
    zk_planes_free(&psrc);
    zk_planes_free(&pdst);
    if (outW != NULL) {
        *outW = tw;
    }
    if (outH != NULL) {
        *outH = th;
    }
    if (op->logTime) {
        zk_log("zk_blur_prep: %dx%d r=%d %s down=%d up=%d -> %dx%d %lld us", w, h, radius,
               zk_blur_mode_name(mode), op->down, op->upBack, tw, th, zk_now_us() - t0);
    }
    return 0;
}

void zk_blur_darken(uint8_t *buf, int w, int h, int stride, int factor256) {
    if (buf == NULL || w <= 0 || h <= 0) {
        return;
    }
    if (factor256 < 0) {
        factor256 = 0;
    }
    if (factor256 > 256) {
        factor256 = 256;
    }
    const int st = (stride > 0) ? stride : w * 4;
    for (int y = 0; y < h; ++y) {
        uint8_t *row = buf + (size_t) y * st;
        for (int x = 0; x < w; ++x) {
            uint8_t *p = row + (size_t) x * 4;
            p[0] = (uint8_t) ((p[0] * factor256 + 128) >> 8);
            p[1] = (uint8_t) ((p[1] * factor256 + 128) >> 8);
            p[2] = (uint8_t) ((p[2] * factor256 + 128) >> 8);
        }
    }
}

int zk_blur_bench_once(const uint8_t *src, int w, int h, int radius, int mode, int down,
                       uint8_t *dst, int dstW, int dstH, int *outErrMax, int *outErrAvg) {
    zk_blur_opts_t o;
    zk_blur_opts_default(&o);
    o.mode = mode;
    o.down = down;
    o.upBack = 1;
    o.logTime = 0;
    uint8_t *ref = NULL;
    if (outErrMax != NULL || outErrAvg != NULL) {     /* 参考：分离式 float 不下采样 */
        ref = (uint8_t *) malloc((size_t) dstW * dstH * 4);
        if (ref != NULL) {
            zk_blur_opts_t orf;
            zk_blur_opts_default(&orf);
            orf.mode = ZK_BLUR_SEP_FLOAT;
            orf.down = 1;
            orf.upBack = 1;
            zk_blur_prep(src, w, h, 0, radius, ref, dstW, dstH, 0, &orf, NULL, NULL);
        }
    }
    const long long t0 = zk_now_us();
    const int rc = zk_blur_prep(src, w, h, 0, radius, dst, dstW, dstH, 0, &o, NULL, NULL);
    const long long t1 = zk_now_us();
    if (ref != NULL && rc == 0) {
        long long acc = 0;
        int mx = 0;
        const long long n = (long long) dstW * dstH * 3;      /* 只比 RGB */
        for (long long i = 0; i < n; ++i) {
            const long long px = i / 3;
            const int c = (int) (i % 3);
            const int d = (int) dst[px * 4 + c] - (int) ref[px * 4 + c];
            const int ad = (d < 0) ? -d : d;
            if (ad > mx) {
                mx = ad;
            }
            acc += ad;
        }
        if (outErrMax != NULL) {
            *outErrMax = mx;
        }
        if (outErrAvg != NULL) {
            *outErrAvg = (int) (acc / n);
        }
    }
    free(ref);
    return (int) ((t1 - t0) / 1000);
}
