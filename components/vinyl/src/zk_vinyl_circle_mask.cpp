/*
 * zk_vinyl_circle_mask.cpp - 正圆覆盖率表（SS=8 子采样面积平均，纯整数、无浮点）
 *
 * 与「静态圆封面」（工程里的 RoundImageView）**完全同源**的口径，保证旋转中的唱片与静态圆边一致。
 * 抽自 iOSStyle-F133/src/core/RoundImageView.cpp，只取正圆所需的最小子集
 * （圆角矩形/描边/位图合成等其余能力不要）。
 */
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "zk_vinyl_circle_mask.h"

#define ZKV_SS 8
#define ZKV_CIRCLE 0

/* 取绝对值（原文件里的 rivAbs，随几何一起抽过来） */
static int rivAbs(int v) {
    return v < 0 ? -v : v;
}

typedef struct RShape {
    int nx;
    int ny;
    int r2;         /* 圆角半径（半单位）；正圆时 = min(nx,ny) - SS */
    bool circle;
};
static inline bool shapeInside(const RShape &sh, int x2, int y2) {
    if (sh.circle) {
        const int cx = sh.nx - 1;
        const int cy = sh.ny - 1;
        const long long dx = x2 - cx;
        const long long dy = y2 - cy;
        return (dx * dx + dy * dy) <= ((long long) sh.r2 * sh.r2);
    }
    const int l = sh.r2;
    const int r = 2 * sh.nx - sh.r2;
    const int t = sh.r2;
    const int b = 2 * sh.ny - sh.r2;
    if (((x2 >= l) && (x2 <= r)) || ((y2 >= t) && (y2 <= b))) {
        return true;                            /* 中带（横或纵）：整条都在形状内 */
    }
    const int cx = (x2 < l) ? l : r;            /* 落在某个角区：离该角圆心比半径 */
    const int cy = (y2 < t) ? t : b;
    const long long dx = x2 - cx;
    const long long dy = y2 - cy;
    return (dx * dx + dy * dy) <= ((long long) sh.r2 * sh.r2);
}

/** 一个像素的覆盖率 0..255（SS=8 -> 64 子采样面积平均；纯整数） */
static int shapeCoverage(const RShape &sh, int px, int py) {
    const int xlo = 2 * (px * ZKV_SS) + 1;
    const int xhi = 2 * (px * ZKV_SS + ZKV_SS - 1) + 1;
    const int ylo = 2 * (py * ZKV_SS) + 1;
    const int yhi = 2 * (py * ZKV_SS + ZKV_SS - 1) + 1;

    if (sh.circle) {
        const int cx = sh.nx - 1;
        const int cy = sh.ny - 1;
        const int dxmin = (cx < xlo) ? (xlo - cx) : ((cx > xhi) ? (cx - xhi) : 0);
        const int dymin = (cy < ylo) ? (ylo - cy) : ((cy > yhi) ? (cy - yhi) : 0);
        const long long rr = (long long) sh.r2 * sh.r2;
        if (((long long) dxmin * dxmin + (long long) dymin * dymin) > rr) {
            return 0;                            /* 整格都在圆外 */
        }
        const int dxmax = (rivAbs(cx - xlo) > rivAbs(cx - xhi)) ? rivAbs(cx - xlo) : rivAbs(cx - xhi);
        const int dymax = (rivAbs(cy - ylo) > rivAbs(cy - yhi)) ? rivAbs(cy - ylo) : rivAbs(cy - yhi);
        if (((long long) dxmax * dxmax + (long long) dymax * dymax) <= rr) {
            return 255;                          /* 整格都在圆内 */
        }
    } else {
        const int l = sh.r2;
        const int r = 2 * sh.nx - sh.r2;
        const int t = sh.r2;
        const int b = 2 * sh.ny - sh.r2;
        if (((xlo >= l) && (xhi <= r)) || ((ylo >= t) && (yhi <= b))) {
            return 255;                          /* 整格在中带 -> 全内 */
        }
        const bool xIn = !((xhi < l) || (xlo > r));
        const bool yIn = !((yhi < t) || (ylo > b));
        if (!xIn && !yIn) {                      /* 整格在某个角区（不跨中带） */
            const int cx = (xlo < l) ? l : r;
            const int cy = (ylo < t) ? t : b;
            const int dxmin = (cx < xlo) ? (xlo - cx) : ((cx > xhi) ? (cx - xhi) : 0);
            const int dymin = (cy < ylo) ? (ylo - cy) : ((cy > yhi) ? (cy - yhi) : 0);
            if (((long long) dxmin * dxmin + (long long) dymin * dymin) >
                    ((long long) sh.r2 * sh.r2)) {
                return 0;
            }
        } else if ((xhi < 0) || (xlo > 2 * sh.nx) || (yhi < 0) || (ylo > 2 * sh.ny)) {
            return 0;                            /* 整格在画布外 */
        }
    }

    int n = 0;
    for (int j = 0; j < ZKV_SS; ++j) {
        const int y2 = ylo + 2 * j;
        for (int i = 0; i < ZKV_SS; ++i) {
            if (shapeInside(sh, xlo + 2 * i, y2)) {
                ++n;
            }
        }
    }
    return (n * 255 + (ZKV_SS * ZKV_SS) / 2) / (ZKV_SS * ZKV_SS);
}

/** 造遮罩：off = 内缩像素（内形状时采样点回退 off，保证内形状居中而不是贴着左上角） */
static void buildMask(uint8_t *mask, int w, int h, const RShape &sh, int off) {
    const int iw = sh.nx / ZKV_SS;          /* 形状自身宽（像素） */
    const int ih = sh.ny / ZKV_SS;
    for (int y = 0; y < h; ++y) {
        uint8_t *row = mask + (size_t) y * w;
        for (int x = 0; x < w; ++x) {
            const int sx = x - off;
            const int sy = y - off;
            if ((sx < 0) || (sy < 0) || (sx >= iw) || (sy >= ih)) {
                row[x] = 0;
                continue;
            }
            row[x] = (uint8_t) shapeCoverage(sh, sx, sy);
        }
    }
}

/** 由（宽, 高, 圆角, 内缩）造形状；in > 0 时是描边内形状 */
static RShape makeShape(int w, int h, int corner, int inset) {
    RShape sh;
    sh.nx = (w - 2 * inset) * ZKV_SS;
    sh.ny = (h - 2 * inset) * ZKV_SS;
    if (sh.nx < ZKV_SS) {
        sh.nx = ZKV_SS;
    }
    if (sh.ny < ZKV_SS) {
        sh.ny = ZKV_SS;
    }
    const bool circle = (corner < 0) || (corner >= (int) ZKV_CIRCLE);
    if (circle) {
        sh.circle = true;
        sh.r2 = ((sh.nx < sh.ny) ? sh.nx : sh.ny) - ZKV_SS;   /* 与确认稿一致 */
        if (sh.r2 < 0) {
            sh.r2 = 0;
        }
        return sh;
    }
    sh.circle = false;
    int radius = corner - inset;
    if (radius < 0) {
        radius = 0;
    }
    const int limit = (((w - 2 * inset) < (h - 2 * inset)) ? (w - 2 * inset) : (h - 2 * inset)) / 2;
    if (radius > limit) {
        radius = limit;
    }
    sh.r2 = radius * 2 * ZKV_SS;
    return sh;
}

/* ============================ 对外：正圆覆盖率表 ============================ */
/* 给「黑胶旋转」这类需要自己逐像素算 alpha 的场景复用**同一套** SS=8 面积平均口径，
 * 避免两处各写一份整数几何（口径漂了就会和静态封面边缘对不上）。 */

uint8_t *zk_vinyl_circle_mask(int size) {
    if (size <= 0) {
        return NULL;
    }
    uint8_t *mask = (uint8_t *) malloc((size_t) size * size);
    if (mask == NULL) {
        return NULL;
    }
    const RShape sh = makeShape(size, size, ZKV_CIRCLE, 0);
    buildMask(mask, size, size, sh, 0);
    return mask;
}
