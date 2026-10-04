/*
 * nvg_smoke.c —— nanovg(AGG) 在 V85X 真机上的离屏光栅冒烟验证
 *
 * 目的：不经 easyui、不落盘、不进 GL，直接验证 libnanovg.so 这份设备档
 *       能否在 V85X(ARMv7 musl) 上：建上下文 → 光栅化 → 产出正确像素。
 *
 * 用它是因为：easyui 集成链重且要拉包；这条链路只依赖 libc + libgcc_s + libnanovg，
 *             能把"库本身能不能用"与"工程能不能编"两件事解耦。
 *
 * 场景（全部可解析验算，不用另一份参考图）：
 *   1) 背景        纯色 RGBA(32,32,32)
 *   2) 实心圆      center(80,120) r=48 红(255,0,0)
 *   3) 线性渐变    矩形 x[160,304) y[40,120)  绿(0,255,0) -> 蓝(0,0,255)
 *   4) 贴图 pattern 矩形 x[160,304) y[140,220) 16x16 棋盘格（走 nvgCreateImageRaw 通道）
 *
 * 产出：/tmp/nvg_out.bgra   原始 BGRA（pc 侧转 PNG 并逐像素比对）
 *       /tmp/nvg_out.ppm    P6，方便直接看
 *       控制台：每帧耗时 / VmRSS / 关键采样点实测像素
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>
#include "nanovg.h"
#include "nanovg_agg.h"

#define W 320
#define H 240
#define STRIDE (W * 4)

static uint8_t g_buf[STRIDE * H];          /* 静态，避免 malloc 对齐/释放问题 */
static uint8_t g_tex[16 * 16 * 4];         /* 棋盘格贴图，BGRA */

/* 把整块 buffer 刷成一个 BGRA 4 字节模式 */
static void fill_bgra(uint8_t* p, size_t npx, uint8_t b, uint8_t g, uint8_t r, uint8_t a) {
    for (size_t i = 0; i < npx; i++) {
        p[i*4+0] = b; p[i*4+1] = g; p[i*4+2] = r; p[i*4+3] = a;
    }
}

/* 取某点 RGB（从 BGRA 里读，返回 R,G,B） */
static void getpix(int x, int y, int* r, int* g, int* b) {
    uint8_t* p = &g_buf[(size_t)y * STRIDE + (size_t)x * 4];
    *b = p[0]; *g = p[1]; *r = p[2];
}

static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

static int read_vmrss_kb(void) {
    FILE* f = fopen("/proc/self/status", "r");
    if (!f) return -1;
    char line[256];
    int kb = -1;
    while (fgets(line, sizeof(line), f)) {
        if (strncmp(line, "VmRSS:", 6) == 0) { sscanf(line + 6, "%d", &kb); break; }
    }
    fclose(f);
    return kb;
}

/* 画一帧确定性场景 */
static void draw_scene(NVGcontext* vg) {
    fill_bgra(g_buf, (size_t)W * H, 32, 32, 32, 255);   /* 背景 BGRA(32,32,32,255) */

    nvgBeginFrame(vg, (float)W, (float)H, 1.0f);

    /* (2) 实心圆 */
    nvgBeginPath(vg);
    nvgCircle(vg, 80.0f, 120.0f, 48.0f);
    nvgFillColor(vg, nvgRGBA(255, 0, 0, 255));
    nvgFill(vg);

    /* (3) 线性渐变矩形 */
    nvgBeginPath(vg);
    nvgRect(vg, 160.0f, 40.0f, 144.0f, 80.0f);
    nvgFillPaint(vg, nvgLinearGradient(vg, 160.0f, 40.0f, 304.0f, 40.0f,
                                       nvgRGBA(0, 255, 0, 255), nvgRGBA(0, 0, 255, 255)));
    nvgFill(vg);

    /* (4) 贴图 pattern 矩形 */
    {
        int img = nvgCreateImageRaw(vg, 16, 16, NVG_TEXTURE_BGRA, 0, g_tex);
        if (img > 0) {
            nvgBeginPath(vg);
            nvgRect(vg, 160.0f, 140.0f, 144.0f, 80.0f);
            nvgFillPaint(vg, nvgImagePattern(vg, 160.0f, 140.0f, 16.0f, 16.0f, 0.0f, img, 1.0f));
            nvgFill(vg);
        } else {
            printf("WARN: nvgCreateImageRaw failed img=%d\n", img);
        }
    }

    nvgEndFrame(vg);
}

int main(void) {
    /* 棋盘格：8x8 一格，黄/蓝交替 */
    for (int y = 0; y < 16; y++) {
        for (int x = 0; x < 16; x++) {
            int c = ((x / 8) + (y / 8)) & 1;
            uint8_t* p = &g_tex[(y * 16 + x) * 4];
            if (c == 0) { p[0] = 0;   p[1] = 255; p[2] = 255; p[3] = 255; } /* RGB(255,255,0) 黄 */
            else        { p[0] = 255; p[1] = 0;   p[2] = 0;   p[3] = 255; } /* RGB(0,0,255)   蓝 */
        }
    }

    printf("== nanovg(AGG) V85X smoke ==\n");
    printf("canvas %dx%d BGRA stride=%d\n", W, H, STRIDE);

    NVGcontext* vg = nvgCreateAGG((uint32_t)W, (uint32_t)H, (uint32_t)STRIDE,
                                  NVG_TEXTURE_BGRA, g_buf);
    if (!vg) {
        printf("FAIL: nvgCreateAGG returned NULL\n");
        return 2;
    }
    printf("OK: nvgCreateAGG ctx=%p\n", (void*)vg);

    /* 首帧（含首次光栅器初始化） */
    double t0 = now_ms();
    draw_scene(vg);
    double t_first = now_ms() - t0;
    printf("frame[0] (cold) = %.3f ms  VmRSS=%d kB\n", t_first, read_vmrss_kb());

    /* 稳态：跑 N 帧记耗时分布 */
    const int N = 200;
    double best = 1e9, sum = 0.0, worst = 0.0;
    for (int i = 0; i < N; i++) {
        double a = now_ms();
        draw_scene(vg);
        double d = now_ms() - a;
        if (d < best) best = d;
        if (d > worst) worst = d;
        sum += d;
    }
    printf("frame[1..%d]: min=%.3f avg=%.3f max=%.3f ms  VmRSS=%d kB\n",
           N, best, sum / N, worst, read_vmrss_kb());

    /* 关键采样点（app 侧自证，pc 侧另有独立复算） */
    int r, g, b;
    getpix(80, 120, &r, &g, &b);  printf("px(80,120)   circle-center  = R%d G%d B%d (exp 255,0,0)\n", r, g, b);
    getpix(80, 60,  &r, &g, &b);  printf("px(80,60)    above-circle   = R%d G%d B%d (exp 32,32,32)\n", r, g, b);
    getpix(161, 80, &r, &g, &b);  printf("px(161,80)   gradient-left  = R%d G%d B%d (exp ~0,255,0)\n", r, g, b);
    getpix(232, 80, &r, &g, &b);  printf("px(232,80)   gradient-mid   = R%d G%d B%d (exp ~0,128,127)\n", r, g, b);
    getpix(303, 80, &r, &g, &b);  printf("px(303,80)   gradient-right = R%d G%d B%d (exp ~0,0,255)\n", r, g, b);
    getpix(150, 80, &r, &g, &b);  printf("px(150,80)   gap(bg)        = R%d G%d B%d (exp 32,32,32)\n", r, g, b);
    getpix(162, 142, &r, &g, &b); printf("px(162,142)  pattern-tile0  = R%d G%d B%d (exp 255,255,0)\n", r, g, b);
    getpix(170, 142, &r, &g, &b); printf("px(170,142)  pattern-tile1  = R%d G%d B%d (exp 0,0,255)\n", r, g, b);

    /* 落盘：原始 BGRA + PPM(P6) */
    FILE* f = fopen("/tmp/nvg_out.bgra", "wb");
    if (f) { fwrite(g_buf, 1, sizeof(g_buf), f); fclose(f); printf("wrote /tmp/nvg_out.bgra (%d B)\n", (int)sizeof(g_buf)); }
    else   { printf("WARN: cannot write /tmp/nvg_out.bgra\n"); }

    f = fopen("/tmp/nvg_out.ppm", "wb");
    if (f) {
        fprintf(f, "P6\n%d %d\n255\n", W, H);
        for (int i = 0; i < W * H; i++) { fputc(g_buf[i*4+2], f); fputc(g_buf[i*4+1], f); fputc(g_buf[i*4+0], f); }
        fclose(f);
        printf("wrote /tmp/nvg_out.ppm\n");
    } else { printf("WARN: cannot write /tmp/nvg_out.ppm\n"); }

    nvgDeleteAGG(vg);
    printf("OK: nvgDeleteAGG done\n");
    return 0;
}
