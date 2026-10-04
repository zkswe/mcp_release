/*
 * zk_nanovg_ondev.cpp —— nanovg(AGG) 在 V85X 工程里的上屏验证
 *
 * 复刻 components/vinyl 的 nanovg 后端调用路径（F133 真机跑过的那条）：
 *   nvgCreateAGG 绑到我方 BGRA 缓冲 -> 画 -> setBackgroundBmp 交控件上屏。
 * 位图字段照 vinyl 的 vsBmpNew()：type=0x01 / bits=32 / bytes=4 / alpha=1 / pitch=w*4。
 *
 * 场景：① 贴图 pattern 填充的圆（+旋转）② 棋盘贴图方阵 ③ 渐变条（预期蓝->黄）
 *       ④ 旋转色条 ⑤ 描边圆环
 */
#include "nanovg.h"
#include "nanovg_agg.h"
#include "control/ZKTextView.h"
#include "utils/BitmapHelper.h"
#include "utils/Log.h"

#include <string.h>
#include <stdlib.h>
#include <stdio.h>

#define NVW 440
#define NVH 440
#define NV_ALPHA_FLAG 0x01

static uint8_t  s_buf[NVW * NVH * 4];
static bitmap_t s_bmp;
#define TEXN 256
static uint8_t  s_tex[TEXN * TEXN * 4];    /* 256x256，32px 格：够一格铺满一个区域 */
static NVGcontext* s_vg = NULL;
static bool s_handed = false;

static void buildChecker(void) {
    for (int y = 0; y < TEXN; y++)
        for (int x = 0; x < TEXN; x++) {
            int c = ((x / 32) + (y / 32)) & 1;
            uint8_t* p = &s_tex[(y * TEXN + x) * 4];
            if (c == 0) { p[0] = 0;   p[1] = 200; p[2] = 255; p[3] = 255; } /* 橙 */
            else        { p[0] = 200; p[1] = 40;  p[2] = 20;  p[3] = 255; } /* 蓝 */
        }
}

static void drawScene(NVGcontext* vg) {
    memset(s_buf, 0, sizeof(s_buf));

    nvgBeginFrame(vg, (float)NVW, (float)NVH, 1.0f);

    int img = nvgCreateImageRaw(vg, TEXN, TEXN, NVG_TEXTURE_BGRA, 0, s_tex);

    /* 背景 */
    nvgBeginPath(vg); nvgRect(vg, 0, 0, NVW, NVH);
    nvgFillColor(vg, nvgRGBA(24, 26, 32, 255)); nvgFill(vg);

    /* ① 贴图 pattern 填充的圆 + 旋转（1:1 贴一格，复刻 vinyl 用法）*/
    nvgSave(vg);
    nvgTranslate(vg, 110, 110);
    nvgRotate(vg, 20.0f * 3.14159265f / 180.0f);
    nvgBeginPath(vg); nvgCircle(vg, 0, 0, 90);
    nvgFillPaint(vg, nvgImagePattern(vg, -90, -90, 180, 180, 0.0f, img, 1.0f));
    nvgFill(vg);
    nvgRestore(vg);

    /* ② 棋盘贴图方阵（1:1）*/
    nvgBeginPath(vg); nvgRect(vg, 230, 20, 200, 190);
    nvgFillPaint(vg, nvgImagePattern(vg, 230, 20, 200, 190, 0.0f, img, 1.0f));
    nvgFill(vg);

    /* ③ 渐变条：预期 蓝 -> 黄（后端忽略渐变 -> 整条纯蓝）*/
    nvgBeginPath(vg); nvgRect(vg, 10, 240, 420, 80);
    nvgFillPaint(vg, nvgLinearGradient(vg, 10, 280, 430, 280,
                                       nvgRGBA(0, 90, 255, 255), nvgRGBA(255, 210, 0, 255)));
    nvgFill(vg);

    /* ④ 旋转色条 */
    nvgSave(vg);
    nvgTranslate(vg, 130, 385);
    nvgRotate(vg, 15.0f * 3.14159265f / 180.0f);
    nvgBeginPath(vg); nvgRect(vg, -100, -20, 200, 40);
    nvgFillColor(vg, nvgRGBA(0, 220, 180, 255)); nvgFill(vg);
    nvgRestore(vg);

    /* ⑤ 描边圆环 */
    nvgBeginPath(vg); nvgCircle(vg, 330, 385, 45);
    nvgStrokeColor(vg, nvgRGBA(255, 255, 255, 255)); nvgStrokeWidth(vg, 7.0f); nvgStroke(vg);

    nvgEndFrame(vg);
    LOGD("nanovg-ondev: tex img id=%d", img);
}

void nvgOnDevEntry(ZKTextView* host) {
    buildChecker();

    memset(&s_bmp, 0, sizeof(s_bmp));
    s_bmp.type   = NV_ALPHA_FLAG;      /* 照 vinyl：位图带 alpha 位 */
    s_bmp.bits   = 32;
    s_bmp.bytes  = 4;
    s_bmp.alpha  = 1;
    s_bmp.width  = NVW;
    s_bmp.height = NVH;
    s_bmp.pitch  = (uint32_t)(NVW * 4);
    s_bmp.data   = s_buf;

    s_vg = nvgCreateAGG((uint32_t)NVW, (uint32_t)NVH, (uint32_t)(NVW * 4),
                        NVG_TEXTURE_BGRA, s_buf);
    if (s_vg == NULL) {
        LOGD("nanovg-ondev: nvgCreateAGG FAILED");
        return;
    }
    LOGD("nanovg-ondev: nvgCreateAGG ok ctx=%p", (void*)s_vg);

    drawScene(s_vg);

    /* 采样点自证（打到日志，便于与抓屏对照）*/
    {
        const uint8_t* p;
        p = &s_buf[((size_t)110 * NVW + 110) * 4]; LOGD("nanovg-ondev: px(110,110)=B%d G%d R%d", p[0],p[1],p[2]);
        p = &s_buf[((size_t)280 * NVW + 20) * 4];  LOGD("nanovg-ondev: grad-left(20,280)=B%d G%d R%d", p[0],p[1],p[2]);
        p = &s_buf[((size_t)280 * NVW + 220) * 4]; LOGD("nanovg-ondev: grad-mid(220,280)=B%d G%d R%d", p[0],p[1],p[2]);
        p = &s_buf[((size_t)280 * NVW + 420) * 4]; LOGD("nanovg-ondev: grad-right(420,280)=B%d G%d R%d", p[0],p[1],p[2]);
    }

    ZKBase* ctrl = host;
    if (ctrl == NULL) {
        LOGD("nanovg-ondev: control 50001 NOT FOUND");
        return;
    }
    ctrl->setBackgroundBmp(&s_bmp);     /* 所有权移交框架（只交一次）*/
    s_handed = true;
    LOGD("nanovg-ondev: setBackgroundBmp done, %dx%d -> ctrl50001", NVW, NVH);

    /* 离屏出图落盘：供 PC 侧与抓屏做 ±2 逐像素比对 */
    FILE* f = fopen("/tmp/nvg_ondev.bgra", "wb");
    if (f != NULL) {
        fwrite(s_bmp.data, 1, (size_t)NVW * NVH * 4, f);
        fclose(f);
        LOGD("nanovg-ondev: dumped /tmp/nvg_ondev.bgra (%d B)", NVW * NVH * 4);
    } else {
        LOGD("nanovg-ondev: dump FAILED");
    }
}
