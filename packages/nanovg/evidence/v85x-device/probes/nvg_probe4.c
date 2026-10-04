/*
 * nvg_probe4.c —— 贴图平铺：flags=0 vs NVG_IMAGE_REPEATX|REPEATY
 * 判据：16x16 贴图画进 64x16 的矩形，看第二、三、四格是否延续（不回落到背景）。
 */
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "nanovg.h"
#include "nanovg_agg.h"

#define W 320
#define H 120
#define STRIDE (W*4)
static uint8_t g_buf[STRIDE*H];
static uint8_t g_tex[16*16*4];

static void fill_bg(void){ for(int i=0;i<W*H;i++){g_buf[i*4]=32;g_buf[i*4+1]=32;g_buf[i*4+2]=32;g_buf[i*4+3]=255;} }
static void getpix(int x,int y,int*r,int*g,int*b){uint8_t*p=&g_buf[(size_t)y*STRIDE+(size_t)x*4];*b=p[0];*g=p[1];*r=p[2];}

int main(void){
    /* 左半红/右半白 的 16x16 贴图（一眼能看出格子边界）*/
    for(int y=0;y<16;y++) for(int x=0;x<16;x++){
        uint8_t*p=&g_tex[(y*16+x)*4];
        if(x<8){p[0]=0;p[1]=0;p[2]=255;p[3]=255;} else {p[0]=255;p[1]=255;p[2]=255;p[3]=255;}
    }
    fill_bg();
    NVGcontext* vg=nvgCreateAGG(W,H,STRIDE,NVG_TEXTURE_BGRA,g_buf);
    if(!vg){printf("FAIL create\n");return 2;}

    nvgBeginFrame(vg,W,H,1.0f);
    int img0 = nvgCreateImageRaw(vg,16,16,NVG_TEXTURE_BGRA,0,g_tex);
    int imgR = nvgCreateImageRaw(vg,16,16,NVG_TEXTURE_BGRA,
                                 NVG_IMAGE_REPEATX|NVG_IMAGE_REPEATY, g_tex);
    printf("img(flags=0)=%d  img(REPEATXY)=%d\n", img0, imgR);

    nvgBeginPath(vg); nvgRect(vg,10,10,256,40);
    nvgFillPaint(vg, nvgImagePattern(vg,10,10,16,16,0,img0,1.0f)); nvgFill(vg);

    nvgBeginPath(vg); nvgRect(vg,10,60,256,40);
    nvgFillPaint(vg, nvgImagePattern(vg,10,60,16,16,0,imgR,1.0f)); nvgFill(vg);
    nvgEndFrame(vg);

    printf("== flags=0 （y=18=short 贴图首行；每 8px 采样：应 红8 白8 然后回落到背景）==\n  ");
    for(int x=12;x<=98;x+=8){int r,g,b;getpix(x,18,&r,&g,&b);printf("(%3d,%3d,%3d) ",r,g,b);}
    printf("\n== REPEATX|REPEATY （y=68）==\n  ");
    for(int x=12;x<=98;x+=8){int r,g,b;getpix(x,68,&r,&g,&b);printf("(%3d,%3d,%3d) ",r,g,b);}
    printf("\n");

    /* 判据：在贴图首个 16px 之外（x=30..265）是否还有非背景像素 */
    int ink0=0, inkR=0;
    for(int x=30;x<265;x++){int r,g,b;getpix(x,18,&r,&g,&b);if(!(r<40&&g<40&&b<40))ink0++;
                            getpix(x,68,&r,&g,&b);if(!(r<40&&g<40&&b<40))inkR++;}
    printf("首格之外的非背景像素: flags=0 -> %d/235 ; REPEATXY -> %d/235\n", ink0, inkR);
    printf("结论: %s\n", (inkR>200 && ink0==0) ? "REPEATXY 才平铺（flags=0 只在首格内有效）"
                                              : "需人工判读");

    nvgDeleteAGG(vg);
    return 0;
}
