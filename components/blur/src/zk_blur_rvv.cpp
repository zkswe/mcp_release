/*
 * zk_blur_rvv.cpp - RVV 0.7.1（C906）向量化加速
 *
 * 只在编译期带向量扩展（-march=rv64gcv0p7 / __riscv_vector 有定义）时才有实体；
 * 其它平台整个文件编译成「不可用」桩，zk_rvv_available() 返回 0，主实现自动退回标量 BOX3。
 *
 * 两个热函数（都是整行元素级运算，天然可向量化；横趟有像素间依赖，保持标量）：
 *   1) zk_rvv_box_v_plane   ：盒式竖趟（滑窗 u16 累加 + vmulhu 代替除法 + 收窄回 u8）
 *   2) zk_rvv_downsample_plane：盒式下采样（跨行跨列求和，用跨步加载 vlse8）
 *
 * 口径与标量版一致：clamp 边、窗口和 / (2r+1)、面积平均。除法的舍入口径为
 * 「高 16 位截断」（vmulhu），与标量版「+0.5 舍入」最多差 1 LSB（实测见 REPORT）。
 */
#include "zk/zk_blur.h"

#ifdef __riscv_vector

#include <riscv_vector.h>

#include <stdlib.h>
#include <string.h>

#ifndef ZK_BLUR_RVV_MAX_RADIUS
#define ZK_BLUR_RVV_MAX_RADIUS 128
#endif

extern "C" int zk_rvv_available(void) {
    return 1;
}

static inline int rvv_clampi(int v, int lo, int hi) {
    return (v < lo) ? lo : ((v > hi) ? hi : v);
}

/** sum[] += row[]（sign > 0）或 sum[] -= row[]（sign < 0）；u16 车道，u8 源加宽 */
static void rvv_acc_row(uint16_t *sum, const uint8_t *row, int w, int sign) {
    int i = 0;
    while (i < w) {
        const size_t vl = vsetvl_e16m2(w - i);
        vuint16m2_t s = vle16_v_u16m2(sum + i, vl);
        const size_t vl8 = vsetvl_e8m1(w - i);
        const vuint8m1_t r = vle8_v_u8m1(row + i, vl8);
        if (sign > 0) {
            s = vwaddu_wv_u16m2(s, r, vl);
        } else {
            s = vwsubu_wv_u16m2(s, r, vl);
        }
        vse16_v_u16m2(sum + i, s, vl);
        i += (int) vl;
    }
}

/** dst[] = (sum[] * recip) >> 16（vmulhu = 取乘积高 16 位，等价除以 65536） */
static void rvv_emit_row(const uint16_t *sum, uint8_t *dst, int w, uint32_t recip) {
    int i = 0;
    while (i < w) {
        const size_t vl = vsetvl_e16m2(w - i);
        const vuint16m2_t s = vle16_v_u16m2(sum + i, vl);
        const vuint16m2_t hi = vmulhu_vx_u16m2(s, recip, vl);
        const size_t vl8 = vsetvl_e8m1(w - i);
        vse8_v_u8m1(dst + i, vnsrl_wx_u8m1(hi, 0, vl8), vl8);
        i += (int) vl;
    }
}

extern "C" int zk_rvv_box_v_plane(const uint8_t *src, uint8_t *dst, int w, int h, int r,
                                  uint32_t recip, int shift) {
    if (src == NULL || dst == NULL || w <= 0 || h <= 0 || r < 0 ||
            r > ZK_BLUR_RVV_MAX_RADIUS || shift != 16) {
        return -1;                       /* 口径不符 -> 让调用方走标量 */
    }
    uint16_t *sum = (uint16_t *) malloc(sizeof(uint16_t) * (size_t) w);
    if (sum == NULL) {
        return -1;
    }
    memset(sum, 0, sizeof(uint16_t) * (size_t) w);
    for (int i = -r; i <= r; ++i) {
        rvv_acc_row(sum, src + (size_t) rvv_clampi(i, 0, h - 1) * w, w, +1);
    }
    for (int y = 0; y < h; ++y) {
        if (y > 0) {
            rvv_acc_row(sum, src + (size_t) rvv_clampi(y + r, 0, h - 1) * w, w, +1);
            rvv_acc_row(sum, src + (size_t) rvv_clampi(y - r - 1, 0, h - 1) * w, w, -1);
        }
        rvv_emit_row(sum, dst + (size_t) y * w, w, recip);
    }
    free(sum);
    return 0;
}

extern "C" int zk_rvv_downsample_plane(const uint8_t *src, int w, int h, int f, uint8_t *dst,
                                       int dw, int dh) {
    if (src == NULL || dst == NULL || w <= 0 || h <= 0 || f < 2 || f > 8 || dw <= 0 ||
            dh <= 0) {
        return -1;
    }
    const int area = f * f;
    const uint32_t recip = (uint32_t) (((1u << 16) + (uint32_t) area / 2) / (uint32_t) area);
    uint16_t *sum = (uint16_t *) malloc(sizeof(uint16_t) * (size_t) dw);
    if (sum == NULL) {
        return -1;
    }
    for (int y = 0; y < dh; ++y) {
        memset(sum, 0, sizeof(uint16_t) * (size_t) dw);
        for (int j = 0; j < f; ++j) {
            const int yy = y * f + j;
            const uint8_t *row = src + (size_t) ((yy < h) ? yy : (h - 1)) * w;
            for (int k = 0; k < f; ++k) {
                int i = 0;
                while (i < dw) {
                    const size_t vl = vsetvl_e16m2(dw - i);
                    vuint16m2_t s = vle16_v_u16m2(sum + i, vl);
                    const size_t vl8 = vsetvl_e8m1(dw - i);
                    const int xx = (i + (int) vl8 <= dw) ? (i + (int) vl8) : dw;
                    (void) xx;
                    const vuint8m1_t v = vlse8_v_u8m1(row + k + (size_t) i * f, (long) f, vl8);
                    s = vwaddu_wv_u16m2(s, v, vl);
                    vse16_v_u16m2(sum + i, s, vl);
                    i += (int) vl;
                }
            }
        }
        rvv_emit_row(sum, dst + (size_t) y * dw, dw, recip);
    }
    free(sum);
    return 0;
}

#else  /* 非 RVV 编译：桩，主实现自动退回标量 */

extern "C" int zk_rvv_available(void) {
    return 0;
}

extern "C" int zk_rvv_box_v_plane(const uint8_t *src, uint8_t *dst, int w, int h, int r,
                                  uint32_t recip, int shift) {
    (void) src;
    (void) dst;
    (void) w;
    (void) h;
    (void) r;
    (void) recip;
    (void) shift;
    return -1;
}

extern "C" int zk_rvv_downsample_plane(const uint8_t *src, int w, int h, int f, uint8_t *dst,
                                       int dw, int dh) {
    (void) src;
    (void) w;
    (void) h;
    (void) f;
    (void) dst;
    (void) dw;
    (void) dh;
    return -1;
}

#endif /* __riscv_vector */
