/*
 * nvg_probe2.c —— 渐变族专项探针（V85X 真机）
 * 目的：确认 nvgLinearGradient 是否真的不生效；并覆盖 反向线性 / 径向 / 箱形。
 * 每条带子画一个渐变矩形，打印 起点/中点/终点 的实测像素。
 */
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "nanovg.h"
#include "nanovg_agg.h"

#define W 320
#define H 240
#define STRIDE (W * 4)
static uint8_t g_buf[STRIDE * H];

static void fill_bg(void) {
    for (int i = 0; i < W * H; i++) {
        g_buf[i*4+0] = 32; g_buf[i*4+1] = 32; g_buf[i*4+2] = 32; g_buf[i*4+3] = 255;
    }
}
static void getpix(int x, int y, int* r, int* g, int* b) {
    uint8_t* p = &g_buf[(size_t)y * STRIDE + (size_t)x * 4];
    *b = p[0]; *g = p[1]; *r = p[2];
}
static void show(const char* tag, int x, int y) {
    int r, g, b; getpix(x, y, &r, &g, &b);
    printf("  %-22s px(%3d,%3d) = R%3d G%3d B%3d\n", tag, x, y, r, g, b);
}

int main(void) {
    fill_bg();
    NVGcontext* vg = nvgCreateAGG(W, H, STRIDE, NVG_TEXTURE_BGRA, g_buf);
    if (!vg) { printf("FAIL nvgCreateAGG\n"); return 2; }
    printf("== 渐变族探针 ==  内色=蓝(0,0,255) 外色=黄(255,255,0)\n");
    NVGcolor BLUE = nvgRGBA(0, 0, 255, 255);
    NVGcolor YELL = nvgRGBA(255, 255, 0, 255);
    nvgBeginFrame(vg, W, H, 1.0f);

    /* A: 水平线性 x 20..300, y 10..50 */
    nvgBeginPath(vg); nvgRect(vg, 20, 10, 280, 40);
    nvgFillPaint(vg, nvgLinearGradient(vg, 20, 30, 300, 30, BLUE, YELL)); nvgFill(vg);
    /* B: 垂直线性 x 20..300, y 60..100 */
    nvgBeginPath(vg); nvgRect(vg, 20, 60, 280, 40);
    nvgFillPaint(vg, nvgLinearGradient(vg, 160, 60, 160, 100, BLUE, YELL)); nvgFill(vg);
    /* C: 径向 中心(160,150) r 0->60 */
    nvgBeginPath(vg); nvgRect(vg, 20, 110, 280, 80);
    nvgFillPaint(vg, nvgRadialGradient(vg, 160, 150, 0, 60, BLUE, YELL)); nvgFill(vg);
    /* D: 箱形 x 20..300 y 200..230, r=8 f=12 */
    nvgBeginPath(vg); nvgRect(vg, 20, 190, 280, 40);
    nvgFillPaint(vg, nvgBoxGradient(vg, 20, 190, 280, 40, 8, 12, BLUE, YELL)); nvgFill(vg);

    nvgEndFrame(vg);

    printf("[A] 水平线性 (期望 蓝->黄 横变)\n");
    show("A-left", 22, 30);  show("A-mid", 160, 30);  show("A-right", 298, 30);
    printf("[B] 垂直线性 (期望 上蓝->下黄)\n");
    show("B-top", 160, 62);  show("B-mid", 160, 80);  show("B-bot", 160, 98);
    printf("[C] 径向 (期望 中心蓝->外黄)\n");
    show("C-center", 160, 150); show("C-r30", 190, 150); show("C-out", 230, 150);
    printf("[D] 箱形 (期望 内蓝->外黄)\n");
    show("D-inside", 160, 210); show("D-left", 22, 210); show("D-out", 10, 210);

    nvgDeleteAGG(vg);
    printf("done\n");
    return 0;
}
