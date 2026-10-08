#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD

/**
 * @brief 当界面显示时触发
 */
static void onUI_show() {
  LOGD_TRACE("");
}

/**
 * @brief 当界面隐藏时触发
 */
static void onUI_hide() {
  LOGD_TRACE("");
}

/**
 * @brief 串口数据回调接口
 */
static void onProtocolDataUpdate(const SProtocolData &data) {
  LOGD_TRACE("");
}
#pragma once

/*
 * mainLogic.cc —— Blend2D 门面（zk::b2d）最小示例：离屏矢量出图 → easyui 上屏
 *
 * 页面（ui/main.json）：B2dCanvas(480x440 只读 textview，当"画布"用) + TextDiag(480x40 读数行)
 * 流程：
 *   ① onUI_init   ：open(480x440, threadCount=2, 字体) → 帧缓冲交给 bitmap_t →
 *                   setBackgroundBmp(**只挂一次**)
 *   ② 每 200 ms   ：clear → shadow(2 层) → roundRect → 渐变条 → 三行文本 → submit →
 *                   **setInvalid(!isInvalid()) 翻帧**（平台唯一刷帧口径）
 *   ③ 首帧同时    ：savePng("/tmp/b2d_card.png") —— 同一份像素也能"离屏出图"
 *   ④ onUI_quit   ：close()
 *
 * 本示例只**编译验证**（fsc build -p Z20），未上真机；真机性能/效果见组件
 * README.md 的性能表与 lib/BUILD_INFO.md。
 */

#include <stdio.h>
#include <stdarg.h>
#include <string.h>

#include "zk/zk_blend2d.h"          /* ← 组件唯一对外头（不含任何 BL* 类型） */

#include <control/ZKBase.h>
#include <control/ZKTextView.h>
#include <utils/BitmapHelper.h>

/* 铁律：每个 logic.cc 都保留定时器表 */
static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 200},
};

#define CANVAS_W 480
#define CANVAS_H 440

static zk::b2d::Canvas sCanvas;      /* 画布：建一次，复用到底（禁逐帧 new） */
static bitmap_t  sBmp;               /* easyui 位图描述符（指向 sCanvas 的帧缓冲） */
static bool      sBmpReady = false;
static int       sFrame = 0;
static char      sDiag[256] = "b2d: boot";

static void setDiag(const char* fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(sDiag, sizeof(sDiag), fmt, ap);
    va_end(ap);
    if (mTextDiagPtr != NULL) mTextDiagPtr->setText(sDiag);
    printf("[b2d] %s\n", sDiag);
}

/* 字体候选链（不同板子内核枚举不同，写死必翻车；文本用 TTF/OTF） */
static const char* pickFont() {
    static const char* cands[] = {
        "/res/font/zkswe-hans-common.ttf",
        "/res/font/HanSans-Medium.ttf",
        "/tmp/font/zkswe-hans-common.ttf",
        "/mnt/extsd/font/zkswe-hans-common.ttf",
        "/mnt/sdnand/font/zkswe-hans-common.ttf",
    };
    for (unsigned i = 0; i < sizeof(cands) / sizeof(cands[0]); ++i) {
        FILE* f = fopen(cands[i], "rb");
        if (f != NULL) { fclose(f); return cands[i]; }
    }
    return NULL;
}

/* 画一帧（几何随 frameIdx 变化，避免被当成静态帧） */
static void renderFrame(int frameIdx) {
    if (!sCanvas.isOpen()) return;

    zk::b2d::Result r;

    /* ① 底色（不透明 + SRC_COPY 直传，门面默认就这么干） */
    r = sCanvas.clear();
    if (!r.ok()) { setDiag("clear 失败: %s", r.msg.c_str()); return; }

    /* ② 圆角卡片：阴影 2 层（推荐配方：<=2 层；8 层会吃掉整帧 80%+） */
    zk::b2d::RoundRect card(24.0f, 26.0f, 432.0f, 240.0f, 26.0f);
    r = sCanvas.shadow(card, 0x14000000, 2, 6.0f);
    if (!r.ok()) { setDiag("shadow 失败: %s", r.msg.c_str()); return; }

    /* ③ 卡片本体 + 1px 描边 */
    r = sCanvas.roundRect(card, 0xFFF8F9FB, 1.0f, 0x33000000);
    if (!r.ok()) { setDiag("roundRect 失败: %s", r.msg.c_str()); return; }

    /* ④ 渐变圆角条（宽度随帧动，证明"能逐帧出图"） */
    float frac = 0.35f + 0.55f * (float) (frameIdx % 12) / 11.0f;
    zk::b2d::RoundRect bar(40.0f, 286.0f, 400.0f * frac + 8.0f, 26.0f, 13.0f);
    r = sCanvas.gradientRoundRect(bar, 0xFF3E7BFA, 0xFF17C964);
    if (!r.ok()) { setDiag("gradient 失败: %s", r.msg.c_str()); return; }

    /* ⑤ 三行文本：英文 / 中文（UTF-8 字节直接写 \x 转义，避开工具链字符集差异）/ 数字 */
    r = sCanvas.text(40.0f, 96.0f, 30.0f, "Blend2D on Z20", 0xFF1B1B1F);
    if (!r.ok()) { setDiag("text 失败: %s", r.msg.c_str()); return; }

    r = sCanvas.text(40.0f, 140.0f, 24.0f,
                     "\xe5\x9c\x86\xe8\xa7\x92\xe5\x8d\xa1\xe7\x89\x87 \xc2\xb7 "
                     "\xe7\x9f\xa2\xe9\x87\x8f\xe7\xbb\x98\xe5\x88\xb6 \xc2\xb7 "
                     "\xe6\x8a\x97\xe9\x94\xaf\xe9\xbd\xbf",
                     0xFF5A6270);
    if (!r.ok()) { setDiag("text(中文) 失败: %s", r.msg.c_str()); return; }

    char num[64];
    snprintf(num, sizeof(num), "vector AA text frame %d", frameIdx);
    r = sCanvas.text(40.0f, 184.0f, 20.0f, num, 0xFF2F6FEB);
    if (!r.ok()) { setDiag("text(数字) 失败: %s", r.msg.c_str()); return; }

    /* ⑥ 提交这一帧（flush SYNC）；之后 pixels() 才是最终像素 */
    r = sCanvas.submit();
    if (!r.ok()) { setDiag("submit 失败: %s", r.msg.c_str()); return; }

    setDiag("b2d v%s  frame=%d  %.2f ms/帧 (threadCount=2, 阴影 2 层)",
            zk::b2d::version(), frameIdx, sCanvas.lastFrameMs());
}

static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif
    /* 画布配置：480x440、双线程（Z20 双核实测 -48%）、字体走候选链 */
    zk::b2d::Config cfg;
    cfg.width  = CANVAS_W;
    cfg.height = CANVAS_H;
    cfg.threadCount = 2;            /* ★ 零成本优化第 1 条 */
    cfg.unpremultiply = false;      /* 不透明底直传 → 零转换 */
    const char* font = pickFont();
    if (font != NULL) cfg.fontPath = font;

    zk::b2d::Result r = sCanvas.open(cfg);
    if (!r.ok()) {
        setDiag("open 失败(%d): %s", r.code, r.msg.c_str());
        return;
    }
    printf("[b2d] %s\n", sCanvas.engineInfo().c_str());
    if (font == NULL) setDiag("警告：未找到中文字体，文本将报 ERR_FONT（画布其它能力可用）");

    /* 帧缓冲交给 easyui：BGRA / 4 字节 / 带 alpha，pitch = w*4（与 PRGB32 内存序一致，零转换） */
    memset(&sBmp, 0, sizeof(sBmp));
    sBmp.type   = 0x01;                     /* 本机约定：带 alpha */
    sBmp.bits   = 32;
    sBmp.bytes  = 4;
    sBmp.alpha  = 1;
    sBmp.width  = CANVAS_W;
    sBmp.height = CANVAS_H;
    sBmp.pitch  = sCanvas.pitch();
    sBmp.data   = (uint8_t*) sCanvas.pixels();

    /* 首帧 + 挂位图（setBackgroundBmp 只挂一次） */
    renderFrame(0);
    if (mB2dCanvasPtr != NULL) {
        mB2dCanvasPtr->setBackgroundBmp(&sBmp);
        mB2dCanvasPtr->setInvalid(!mB2dCanvasPtr->isInvalid());
        sBmpReady = true;
    } else {
        setDiag("B2dCanvas 控件指针为空！");
    }

    /* 顺带演示"离屏出图"：同一份像素编码 PNG 落盘（量产出图/取证/PC 预烘同一入口） */
    zk::b2d::Result pr = sCanvas.savePng("/tmp/b2d_card.png");
    printf("[b2d] savePng(/tmp/b2d_card.png): %s\n", pr.msg.c_str());
}

static void onUI_intent(const Intent* intentPtr) { (void) intentPtr; }

static bool onmainActivityTouchEvent(const MotionEvent& ev) { (void) ev; return false; }

static bool onUI_Timer(int id) {
    (void) id;
    if (!sBmpReady) return true;
    renderFrame(++sFrame);
    /* 平台唯一刷帧口径：翻转 invalid 位（buffer 复用，不重新挂） */
    if (mB2dCanvasPtr != NULL) {
        mB2dCanvasPtr->setInvalid(!mB2dCanvasPtr->isInvalid());
    }
    return true;
}

static void onUI_quit() {
    sCanvas.close();               /* 位图指向画布缓冲：先关画布（控件随 Activity 销毁） */
    sBmpReady = false;
    printf("[b2d] onUI_quit：画布已释放\n");
}
