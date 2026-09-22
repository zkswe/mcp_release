#pragma once

/**
 * vinyl_demoLogic.cc —— zk::VinylSpin 最小示例（标准接入，拷进任意工程即可跑）
 *
 * 页面布局（ui/vinyl_demo.json，1024x600）：
 *   CoverArt(320x320 正方形占位控件，不配图) + BtnPlayPause + BtnBackend + BtnCover + TextDiag
 *
 * 接入三步（本文件就是标准写法）：
 *   ① onUI_init：attach(占位控件) + setCover(封面路径)
 *   ② 定时器表 {0, 83}：每拍 tick()（旋转与解码都在组件后台队列上跑）
 *   ③ onUI_quit：detach()
 * 播放/暂停联动 setPlaying()；想现场对比两个内置后端用 setBackend()。
 */
#include <stdio.h>
#include <string>

#include "manager/ConfigManager.h"

#include "zk_vinyl/zk_vinyl.h"          /* 组件唯一对外头（源码引入时按工程路径调整） */

#if defined(FUSE_BUILD) || defined(FUN_BUILD)
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif

/* 铁律：每个 logic.cc 都要有定时器表（不用定时器也保留空表） */
static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 83},        /* 12fps 驱动黑胶自转（重活在组件后台队列） */
    {1, 1000},      /* 每秒刷一次诊断行 */
};

/* 演示用：两张封面轮流换（换成你自己的资源路径即可） */
static const char *kCovers[] = {
    "images/album_a.png",
    "images/album_b.png",
};
static int sCoverIdx = 0;
static bool sPlaying = true;
static std::string sDispDiag;

static std::string resPath(const char *rel) {
    std::string p = CONFIGMANAGER->getResFilePath(rel);
    return p.empty() ? std::string(rel) : p;
}

/* =========================== 生命周期 =========================== */
static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif
    sCoverIdx = 0;
    sPlaying = true;
    sDispDiag.clear();

    if (mCoverArtPtr == NULL) {
        LOGW("vinyl_demo: json 里没有 CoverArt 占位控件");
        return;
    }
    /* ① 挂载（控件必须是正方形；json 里不要给它配图，首帧算好前显示占位） */
    if (!zk::VinylSpin::instance().attach(mCoverArtPtr)) {
        LOGW("vinyl_demo: VinylSpin attach 失败（控件非正方形？）");
        return;
    }
    zk::VinylSpin::instance().setCover(resPath(kCovers[sCoverIdx]).c_str());
    zk::VinylSpin::instance().setPlaying(sPlaying);
    LOGD("vinyl_demo: 组件就位 %dx%d", mCoverArtPtr->getPosition().mWidth,
         mCoverArtPtr->getPosition().mHeight);
}

static void onUI_quit() {
    /* ③ 摘下：停转 + 释放我方缓冲（已交给框架的位图随控件销毁释放） */
    zk::VinylSpin::instance().detach();
}

static void onUI_intent(const Intent *intentPtr) {
    (void) intentPtr;
}

/* =========================== 定时器 =========================== */
static bool onUI_Timer(int id) {
    if (id == 0) {
        /* ② 每拍驱动：本拍只做「取上一帧结果 + 上屏」，旋转在后台线程 */
        zk::VinylSpin::instance().tick();
        return true;
    }
    /* 诊断读数（验收直接看这一行） */
    zk::VinylSpin &vs = zk::VinylSpin::instance();
    char buf[192];
    snprintf(buf, sizeof(buf), "黑胶 %s | %s %d度 %d帧 %d.%dfps | 旋转 %dms 上屏 %dms",
             sPlaying ? "播放中" : "暂停", vs.backend() == 1 ? "nanovg" : "定点",
             vs.angleDeg(), vs.frames(), vs.fpsX10() / 10, vs.fpsX10() % 10,
             vs.lastRotMs(), vs.lastPubMs());
    if (sDispDiag != buf) {
        sDispDiag = buf;
        if (mTextDiagPtr != NULL) {
            mTextDiagPtr->setText(sDispDiag);
        }
    }
    return true;
}

/* =========================== 按钮 =========================== */
static bool onButtonClick_BtnPlayPause(ZKButton *pButton) {
    (void) pButton;
    sPlaying = !sPlaying;
    zk::VinylSpin::instance().setPlaying(sPlaying);   /* 暂停即停转，恢复从当前角度继续 */
    return false;
}

static bool onButtonClick_BtnBackend(ZKButton *pButton) {
    (void) pButton;
    zk::VinylSpin &vs = zk::VinylSpin::instance();
    const int want = (vs.backend() == 1) ? 0 : 1;
    const int got = vs.setBackend(want);              /* 返回实际生效值（nanovg 建不起来会保持定点） */
    LOGD("vinyl_demo: 切后端 want=%d -> 生效 %d", want, got);
    return false;
}

static bool onButtonClick_BtnCover(ZKButton *pButton) {
    (void) pButton;
    sCoverIdx = (sCoverIdx + 1) % (int) (sizeof(kCovers) / sizeof(kCovers[0]));
    zk::VinylSpin::instance().setCover(resPath(kCovers[sCoverIdx]).c_str());  /* 换图，角度回 0 */
    LOGD("vinyl_demo: 换封面 -> %s", kCovers[sCoverIdx]);
    return false;
}
