/*
 * nvg_feat.c —— nanovg(AGG) 功能矩阵探针（V85X 真机）
 * 每条能力画出来 → 解析算期望值 → 自判 PASS/FAIL，输出一张矩阵。
 * 覆盖：路径填充 / 描边 / 抗锯齿 / 变换(旋转) / 裁剪 / alpha 合成 / 渐变族 / 贴图
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#include "nanovg.h"
#include "nanovg_agg.h"

#define W 320
#define H 240
#define STRIDE (W * 4)
static uint8_t g_buf[STRIDE * H];

static int g_pass = 0, g_fail = 0;

static void fill_bg(void) {
    for (int i = 0; i < W * H; i++) {
        g_buf[i*4+0] = 32; g_buf[i*4+1] = 32; g_buf[i*4+2] = 32; g_buf[i*4+3] = 255;
    }
}
static void getpix(int x, int y, int* r, int* g, int* b) {
    uint8_t* p = &g_buf[(size_t)y * STRIDE + (size_t)x * 4];
    *b = p[0]; *g = p[1]; *r = p[2];
}
/* 断言某点接近期望色（容差 tol） */
static void chk(const char* name, int x, int y, int er, int eg, int eb, int tol) {
    int r, g, b; getpix(x, y, &r, &g, &b);
    int d = abs(r-er) + abs(g-eg) + abs(b-eb);
    int ok = d <= tol;
    if (ok) g_pass++; else g_fail++;
    printf("  [%s] %-26s px(%3d,%3d)=R%3d G%3d B%3d  期望(%3d,%3d,%3d) tol%d  |Δ|=%d\n",
           ok ? "PASS" : "FAIL", name, x, y, r, g, b, er, eg, eb, tol, d);
}

int main(void) {
    fill_bg();
    NVGcontext* vg = nvgCreateAGG(W, H, STRIDE, NVG_TEXTURE_BGRA, g_buf);
    if (!vg) { printf("FAIL nvgCreateAGG\n"); return 2; }
    nvgBeginFrame(vg, W, H, 1.0f);
    const int PI = 0;

    /* T1 三角形路径填充 */
    nvgBeginPath(vg); nvgMoveTo(vg, 10, 10); nvgLineTo(vg, 70, 10); nvgLineTo(vg, 40, 60); nvgClosePath(vg);
    nvgFillColor(vg, nvgRGBA(255, 0, 0, 255)); nvgFill(vg);

    /* T2 描边（8px 宽白线） */
    nvgBeginPath(vg); nvgMoveTo(vg, 90, 20); nvgLineTo(vg, 90, 60);
    nvgStrokeColor(vg, nvgRGBA(255, 255, 255, 255)); nvgStrokeWidth(vg, 8.0f); nvgStroke(vg);

    /* T3 变换：绕(160,40)转 45°，画 60x20 红条 */
    nvgSave(vg);
    nvgTranslate(vg, 160, 40); nvgRotate(vg, 45.0f * 3.14159265f / 180.0f);
    nvgBeginPath(vg); nvgRect(vg, -30, -10, 60, 20);
    nvgFillColor(vg, nvgRGBA(0, 200, 255, 255)); nvgFill(vg);
    nvgRestore(vg);

    /* T4 裁剪：scissor 到 (200,10,60,60)，再填一个更大的绿块 */
    nvgSave(vg);
    nvgScissor(vg, 200, 10, 60, 60);
    nvgBeginPath(vg); nvgRect(vg, 180, 0, 130, 120);
    nvgFillColor(vg, nvgRGBA(0, 255, 0, 255)); nvgFill(vg);
    nvgRestore(vg);

    /* T5 alpha 合成：50% 红压在背景(32,32,32) 上 -> (144,16,16) */
    nvgBeginPath(vg); nvgRect(vg, 10, 150, 60, 60);
    nvgFillColor(vg, nvgRGBA(255, 0, 0, 128)); nvgFill(vg);

    /* T6 贴图 pattern（8px 棋盘，黄/蓝）*/
    {
        static uint8_t tex[16*16*4];
        for (int y = 0; y < 16; y++) for (int x = 0; x < 16; x++) {
            int c = ((x/8)+(y/8)) & 1; uint8_t* p = &tex[(y*16+x)*4];
            if (c==0){p[0]=0;p[1]=255;p[2]=255;p[3]=255;} else {p[0]=255;p[1]=0;p[2]=0;p[3]=255;}
        }
        int img = nvgCreateImageRaw(vg, 16, 16, NVG_TEXTURE_BGRA, 0, tex);
        printf("  (nvgCreateImageRaw -> img=%d)\n", img);
        nvgBeginPath(vg); nvgRect(vg, 10, 100, 80, 40);
        nvgFillPaint(vg, nvgImagePattern(vg, 10, 100, 16, 16, 0, img, 1.0f));
        nvgFill(vg);
    }

    /* T7 抗锯齿：白色实心圆 center(250,180) r=30 */
    nvgBeginPath(vg); nvgCircle(vg, 250, 180, 30);
    nvgFillColor(vg, nvgRGBA(255, 255, 255, 255)); nvgFill(vg);

    nvgEndFrame(vg);

    printf("== nanovg(AGG) V85X 功能矩阵 ==\n");
    printf("[T1] 任意路径填充（三角形 不闭合边 AA）\n");
    chk("T1-inside",      40, 25, 255, 0, 0, 6);
    chk("T1-outside",     12, 58, 32, 32, 32, 6);
    printf("[T2] 描边 stroke（8px）\n");
    chk("T2-on-line",     90, 40, 255, 255, 255, 6);
    chk("T2-off-line",   110, 40, 32, 32, 32, 6);
    printf("[T3] 变换（绕原点转45°后画矩形）\n");
    chk("T3-rotated-on", 174, 54, 0, 200, 255, 8);
    chk("T3-rotated-off",142, 58, 32, 32, 32, 8);
    printf("[T4] 裁剪 scissor\n");
    chk("T4-inside",     210, 20, 0, 255, 0, 6);
    chk("T4-outside",    190, 20, 32, 32, 32, 6);
    printf("[T5] alpha 合成（a=128 红 over bg）\n");
    chk("T5-blend",       40, 180, 144, 16, 16, 8);
    printf("[T6] 贴图 pattern\n");
    chk("T6-tile0(黄)",    12, 102, 255, 255, 0, 6);
    chk("T6-tile1(蓝)",    22, 102, 0, 0, 255, 6);
    printf("[T7] 抗锯齿（白圆 center(250,180) r=30，统计包围盒内\"部分覆盖\"像素）\n");
    {
        int ramp = 0, minv = 999, maxv = -1;
        for (int y = 149; y <= 211; y++)
            for (int x = 219; x <= 281; x++) {
                int r,g,b; getpix(x,y,&r,&g,&b);
                if (r > 60 && r < 230) { ramp++; if (r<minv) minv=r; if (r>maxv) maxv=r; }
            }
        int ok = ramp >= 20;   /* AA 边环应有数十个过渡像素 */
        if (ok) g_pass++; else g_fail++;
        printf("  [%s] T7-AA 过渡像素数=%d（阈值>=20），过渡值范围 %d..%d\n",
               ok?"PASS":"FAIL", ramp, ramp?minv:-1, ramp?maxv:-1);
    }
    printf("---- 汇总: PASS=%d FAIL=%d ----\n", g_pass, g_fail);

    nvgDeleteAGG(vg);
    return 0;
}
