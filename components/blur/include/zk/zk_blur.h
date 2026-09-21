/*
 * zk_blur.h - 高斯模糊（铺底 / 封面背景）可复用组件
 *
 * 用途：音乐播放器「封面高斯模糊铺底」这类需求，一次算好整屏背景图（切歌时才重算），
 *       不要每帧重算。也支持封面圆形缩略图等任何 4 字节位图的模糊。
 *
 * 数据约定：
 *   · 只吃 4 字节/像素的 BGRA（本机 screencap / image_load 的字节序），alpha 按普通通道一起模糊；
 *   · stride = 每行字节数（0 = w*4）；允许 src/dst 不同 stride；
 *   · 不做内部缩放以外的任何色彩空间转换（不要 premultiply / 不要转 RGB565）。
 *
 * 线程模型：**纯计算，无锁、无全局状态、可重入**；调用方自己在工作线程里调（别在 UI 线程）。
 *
 * 实现档位（mode）：见下方枚举。档位只影响速度/精度，不影响 API 形状。
 * 平台相关：RVV 0.7.1 档位只在编译期带 `-march=rv64gcv0p7`（F133/C906）时才有实体；
 *           其余平台该档位自动退回 ZK_BLUR_BOX3，用 zk_blur_mode_active() 看实际生效档。
 */
#ifndef _ZK_BLUR_H_
#define _ZK_BLUR_H_

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---------------- 实现档位 ---------------- */
enum {
    ZK_BLUR_MODE_AUTO     = -1,  /**< 平台默认推荐（见 zk_blur_mode_recommended） */
    ZK_BLUR_NAIVE2D       = 0,   /**< 朴素二维卷积（基线对照，慢，仅用于正确性参考） */
    ZK_BLUR_SEP_FLOAT     = 1,   /**< 分离式：两趟（横 + 竖），float 核 */
    ZK_BLUR_SEP_FIXED     = 2,   /**< 分离式：定点 Q8 核 + 256 项乘积查表 + 移位代替除法 */
    ZK_BLUR_BOX3          = 3,   /**< 三次盒式（滑窗 O(1)/像素，整数倒数乘移位），推荐的默认档 */
    ZK_BLUR_RVV           = 4,   /**< RVV 0.7.1 向量化（C906）；无 RVV 编译时自动退回 BOX3 */
    ZK_BLUR_MODE_MAX      = 5
};

/* ---------------- 参数 ---------------- */
typedef struct {
    int mode;       /**< 实现档位，ZK_BLUR_MODE_AUTO = 平台默认 */
    int down;       /**< 内部降采样倍率：1 / 2 / 4 / 8（0 或 1 = 不降采样） */
    int upBack;     /**< 1 = 最终仍按请求的 dw x dh 输出（内部糊完再放大）；
                         0 = 输出缩小图（dw/down x dh/down），由显示层自己拉伸 */
    int passes;     /**< BOX3 盒式趟数（默认 3；1 = 单次盒式，最糙但最便宜） */
    int threads;    /**< 线程数（0/1 = 单线程；>1 保留） */
    int logTime;    /**< 1 = 通过 zk_blur_log_fn 打印耗时 */
} zk_blur_opts_t;

/** 推荐默认参数（铺底场景：BOX3 + 1/4 下采样 + 放大回目标） */
void zk_blur_opts_default(zk_blur_opts_t *o);

/** 平台默认推荐档位 */
int zk_blur_mode_recommended(void);

/** 该档位在本平台实际生效的实现（RVV 不可用时回退后的值） */
int zk_blur_mode_active(int mode);

/** 编译期是否带 RVV 实现（0 = 无） */
int zk_blur_has_rvv(void);

/** 档位名（打印用，纯 ASCII） */
const char *zk_blur_mode_name(int mode);

/* ---------------- 日志 ---------------- */
typedef void (*zk_blur_log_fn)(const char *line);
/** 装日志输出（NULL = 关）；默认关 */
void zk_blur_set_log(zk_blur_log_fn fn);

/* ---------------- 主入口 ---------------- */
/**
 * 模糊 w*h 的 4 字节位图。
 * @param src       源（4 字节/像素）
 * @param w,h       源尺寸
 * @param srcStride 源行距（字节），0 = w*4
 * @param radius    高斯半径（像素，>=1；越大越糊）
 * @param dst       目标缓冲（至少 dstStride*h 字节；可与 src 同一块）
 * @param dstStride 目标行距（字节），0 = w*4
 * @param o         参数（NULL = 默认）
 * @return 0 成功；<0 失败（参数非法/内存不足）。失败时 dst 内容不可用。
 */
int zk_blur_bgra(const uint8_t *src, int w, int h, int srcStride, int radius,
                 uint8_t *dst, int dstStride, const zk_blur_opts_t *o);

/**
 * 铺底专用：源图 -> cover 裁切/缩放 -> （可先降采样）模糊 -> （可放大）-> 输出。
 *
 * 输出尺寸口径（**两条都清楚**）：
 *   · opts->upBack = 1：输出就是 dw x dh（内部可能降采样后再放大回 dw x dh）；
 *   · opts->upBack = 0：输出是缩小图，尺寸 = ceil(dw/down) x ceil(dh/down)，
 *     此时 dw/dh 表示“铺底最终要铺多大”，调用方按 outW/outH 拿真实尺寸。
 * dst 缓冲按真实输出尺寸给（缩小时别按 dw x dh 给，省内存）。
 *
 * @param outW,outH 回真实输出尺寸（可传 NULL）
 */
int zk_blur_prep(const uint8_t *src, int w, int h, int srcStride, int radius,
                 uint8_t *dst, int dw, int dh, int dstStride, const zk_blur_opts_t *o,
                 int *outW, int *outH);

/** 定点暗化（铺底可读性）：factor256 = 0..256，256 = 不变，128 = 压到一半亮度 */
void zk_blur_darken(uint8_t *buf, int w, int h, int stride, int factor256);

/** 单档计时（bench 用）：返回本次调用毫秒；不依赖 zk_blur_set_log */
int zk_blur_bench_once(const uint8_t *src, int w, int h, int radius, int mode, int down,
                       uint8_t *dst, int dstW, int dstH, int *outErrMax, int *outErrAvg);
#ifdef __cplusplus
}
#endif

#endif /* _ZK_BLUR_H_ */
