/*
 * nvg_probe3.c —— 渐变缺陷定位：API 返回的 NVGpaint 是否正常？变异调用法是否也无效？
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
    for (int i = 0; i < W * H; i++) { g_buf[i*4]=32; g_buf[i*4+1]=32; g_buf[i*4+2]=32; g_buf[i*4+3]=255; }
}
static void getpix(int x,int y,int*r,int*g,int*b){uint8_t*p=&g_buf[(size_t)y*STRIDE+(size_t)x*4];*b=p[0];*g=p[1];*r=p[2];}
static void dump_paint(const char* tag, NVGpaint p) {
    printf("%s: xform=[%.2f %.2f %.2f %.2f %.2f %.2f] extent=[%.2f %.2f] radius=%.2f feather=%.2f\n",
           tag, p.xform[0],p.xform[1],p.xform[2],p.xform[3],p.xform[4],p.xform[5],
           p.extent[0],p.extent[1],p.radius,p.feather);
    printf("       inner=(%.2f,%.2f,%.2f,%.2f) outer=(%.2f,%.2f,%.2f,%.2f) image=%d\n",
           p.innerColor.r,p.innerColor.g,p.innerColor.b,p.innerColor.a,
           p.outerColor.r,p.outerColor.g,p.outerColor.b,p.outerColor.a, p.image);
}
static void rowsample(const char* tag, int y, int x0, int x1, int step) {
    printf("  %s y=%d x=%d..%d step%d: ", tag, y, x0, x1, step);
    for (int x=x0; x<=x1; x+=step) { int r,g,b; getpix(x,y,&r,&g,&b); printf("(%d,%d,%d) ", r,g,b); }
    printf("\n");
}

int main(void) {
    fill_bg();
    NVGcontext* vg = nvgCreateAGG(W,H,STRIDE,NVG_TEXTURE_BGRA,g_buf);
    if(!vg){printf("FAIL create\n");return 2;}
    NVGcolor BLUE=nvgRGBA(0,0,255,255), YELL=nvgRGBA(255,255,0,255);

    printf("== A) API 返回的 NVGpaint 结构（内蓝外黄, 轴 (20,30)->(300,30)）==\n");
    NVGpaint pl = nvgLinearGradient(vg, 20,30, 300,30, BLUE, YELL); dump_paint("linear", pl);
    NVGpaint pr = nvgRadialGradient(vg, 160,60, 0, 60, BLUE, YELL);  dump_paint("radial", pr);
    NVGpaint pb = nvgBoxGradient(vg, 20,100, 280,40, 8,12, BLUE, YELL); dump_paint("box", pb);

    nvgBeginFrame(vg,W,H,1.0f);

    /* B) 常规调用法：先 beginPath 再建 paint */
    nvgBeginPath(vg); nvgRect(vg,20,10,280,30);
    nvgFillPaint(vg, nvgLinearGradient(vg,20,25,300,25,BLUE,YELL)); nvgFill(vg);

    /* C) 变异 1：paint 在 BeginPath 之前就建好 */
    NVGpaint p2 = nvgLinearGradient(vg,20,55,300,55,BLUE,YELL);
    nvgBeginPath(vg); nvgRect(vg,20,55,280,30); nvgFillPaint(vg,p2); nvgFill(vg);

    /* D) 变异 2：alpha 也做渐变（内 a=0，外 a=255）。若 ramp 死透=全透明=背景*/
    nvgBeginPath(vg); nvgRect(vg,20,100,280,30);
    nvgFillPaint(vg, nvgLinearGradient(vg,20,115,300,115, nvgRGBA(255,0,0,0), nvgRGBA(255,0,0,255))); nvgFill(vg);

    /* E) 变异 3：用 stroke 配渐变 */
    nvgBeginPath(vg); nvgMoveTo(vg,20,160); nvgLineTo(vg,300,160);
    nvgStrokeWidth(vg,20.0f);
    nvgStrokePaint(vg, nvgLinearGradient(vg,20,160,300,160,BLUE,YELL)); nvgStroke(vg);

    nvgEndFrame(vg);

    printf("== B) 常规法（同一行从左到右应 蓝->黄）==\n");
    rowsample("B", 25, 22, 298, 46);
    printf("== C) 变异1 paint 先建 ==\n");
    rowsample("C", 70, 22, 298, 46);
    printf("== D) 变异2 alpha 渐变（红 a=0->255，应 背景->红）==\n");
    rowsample("D", 115, 22, 298, 46);
    printf("== E) 变异3 stroke+渐变 ==\n");
    rowsample("E", 160, 22, 298, 46);

    nvgDeleteAGG(vg);
    return 0;
}
