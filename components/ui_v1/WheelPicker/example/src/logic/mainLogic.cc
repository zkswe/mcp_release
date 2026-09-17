#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD
#pragma once
#include "uart/ProtocolSender.h"
#include "zk/zk_wheelpicker.h"
#include <cstdio>
#include <cstring>
#include <string>

/*
 * components/ui_v1/WheelPicker 最小示例（Z21 1024x600）
 *
 * 契约（少一条就不动，见包 README §排错）：
 *   1. onUI_init 里 attach(painter, rows, rowCount) -> setStyle() -> setItems() -> setIndex() -> refresh()
 *   2. REGISTER_ACTIVITY_TIMER_TAB 里有一路 16ms 定时器，onUI_Timer 里调 tick()
 *   3. onmainActivityTouchEvent 里把 MotionEvent 转给 onTouch()（命中判定包内做）
 *   4. rows = 宿主的 textview 池（painter 没有文字 API，文字必须由 textview 承载）
 *
 * 本页两组滚轮：左轮 A（40 项）+ 右轮 B（按 A 的选中值重建 = 联动演示，接线在宿主侧）。
 */

/* ---------- 两个滚轮 + 两个监听器 ---------- */
static zk::ui_v1::WheelPicker s_wheelA;
static zk::ui_v1::WheelPicker s_wheelB;

static const int ITEM_N = 40;      /* 左轮项数 */
static const int LINK_N = 8;       /* 右轮项数（联动重建） */

/* 事件日志（最多留 7 行） */
static std::string s_log[8];
static int s_logCount = 0;
static int s_settledA = 0, s_changedA = 0;

/* 宿主侧「两轮合计」性能统计（60 帧环形缓冲，微秒） */
#define HOST_PERF_N 60
static int s_hostPerf[HOST_PERF_N];
static int s_hostPerfN = 0, s_hostPerfIdx = 0;
static int s_hudTick = 0;

static void logLine(const char *fmt, int a, int b) {
    char buf[120];
    snprintf(buf, sizeof(buf), fmt, a, b);
    if (s_logCount < 8) {
        s_log[s_logCount++] = buf;
    } else {
        for (int i = 0; i < 7; ++i) s_log[i] = s_log[i + 1];
        s_log[7] = buf;
    }
    std::string all;
    for (int i = 0; i < s_logCount; ++i) {
        all += s_log[i];
        all += "\n";
    }
    if (mTxtLogPtr != NULL) {
        mTxtLogPtr->setText(all.c_str());
    }
}

static void updateIndexText() {
    if (mTxtIndexPtr != NULL) {
        char buf[160];
        snprintf(buf, sizeof(buf), "index A=%d  B=%d   changed=%d settled=%d",
                 s_wheelA.getIndex(), s_wheelB.getIndex(), s_changedA, s_settledA);
        mTxtIndexPtr->setText(buf);
    }
}

/* ---------- 联动：A 停下后按 A 的选中值重建 B 的数据 ---------- */
static void rebuildB() {
    std::vector<std::string> items;
    char buf[64];
    for (int i = 0; i < LINK_N; ++i) {
        snprintf(buf, sizeof(buf), "A%02d-%d", s_wheelA.getIndex() + 1, i + 1);
        items.push_back(buf);
    }
    s_wheelB.setItems(items);
    s_wheelB.setIndex(0, false);
    logLine("link: A settle -> B rebuilt (%d items)", (int) items.size(), 0);
}

/* ---------- 监听器：滚动中 / 吸附完成 ---------- */
class WheelListener : public zk::ui_v1::WheelPicker::Listener {
public:
    explicit WheelListener(bool isA) : mIsA(isA) {}
    virtual void onWheelChanged(int idx) {
        if (mIsA) {
            ++s_changedA;
            updateIndexText();
        }
        (void) idx;
    }
    virtual void onWheelSettled(int idx) {
        if (mIsA) {
            ++s_settledA;
            rebuildB();                 /* 联动 */
        }
        logLine(mIsA ? "settled A = %d" : "settled B = %d", idx, 0);
        updateIndexText();
    }
private:
    bool mIsA;
};

static WheelListener s_listenerA(true);
static WheelListener s_listenerB(false);

/* ---------- 控件回调 ---------- */
static bool onButtonClick_BtnNext(ZKButton *p) {
    s_wheelA.setIndex(s_wheelA.getIndex() + 1, true);
    (void) p;
    return false;
}

static bool onButtonClick_BtnPrev(ZKButton *p) {
    s_wheelA.setIndex(s_wheelA.getIndex() - 1, true);
    (void) p;
    return false;
}

static bool onButtonClick_BtnFling(ZKButton *p) {
    int t = s_wheelA.getIndex() + 16;
    if (t > ITEM_N - 1) t = ITEM_N - 1;
    s_wheelA.setIndex(t, true);         /* 大跨度 + 动画 = 快速滚（包内限速 28 项/秒） */
    (void) p;
    return false;
}

static bool onButtonClick_BtnStop(ZKButton *p) {
    s_wheelA.stop();
    s_wheelB.stop();
    (void) p;
    return false;
}

/* ---------- 生命周期 ---------- */
static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 16},        /* 滚轮帧循环：16ms（约 60fps 请求；实测见 TxtPerf / README 性能节） */
};

static void initWheel(zk::ui_v1::WheelPicker &w, ZKPainter *pt, ZKTextView **rows,
                      zk::ui_v1::WheelPicker::Listener *ls) {
    zk::ui_v1::WheelPicker::Style st = zk::ui_v1::WheelPicker::Style::defaultStyle();
    st.bg           = 0xFFFFFF;
    st.textColor    = 0x666666;
    st.selTextColor = 0x0052D9;
    st.bandColor    = 0xF2F3FF;
    st.lineColor    = 0xE7E7E7;
    st.rowHeight    = 40;
    st.visibleRows  = 5;
    st.bandInset    = 10;
    st.bandRadius   = 8;
    st.showLines    = true;
    st.fadeEdges    = true;
    w.attach(pt, rows, 5);
    w.setStyle(st);
    w.setListener(ls);
}

static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD

    static ZKTextView *rowsA[5] = {mRowA0Ptr, mRowA1Ptr, mRowA2Ptr, mRowA3Ptr, mRowA4Ptr};
    static ZKTextView *rowsB[5] = {mRowB0Ptr, mRowB1Ptr, mRowB2Ptr, mRowB3Ptr, mRowB4Ptr};
    initWheel(s_wheelA, mPtWheelAPtr, rowsA, &s_listenerA);
    initWheel(s_wheelB, mPtWheelBPtr, rowsB, &s_listenerB);

    std::vector<std::string> items;
    char buf[64];
    for (int i = 0; i < ITEM_N; ++i) {
        snprintf(buf, sizeof(buf), "选项 %02d", i + 1);
        items.push_back(buf);
    }
    s_wheelA.setItems(items);
    s_wheelA.setIndex(0, false);
    rebuildB();

    s_settledA = 0;
    s_changedA = 0;
    s_logCount = 0;
    /* 性能 HUD：不用包内 HUD（那只统计左轮），改用宿主侧「两轮合计」+ 包内左轮单轮 一起显示 */
    s_wheelA.setPerfHud(NULL);
    /* 日志框 h=150，平台 textview 默认**垂直居中** -> 多行日志会看着跑到盒子中间，显式改顶部对齐 */
    if (mTxtLogPtr != NULL) {
        mTxtLogPtr->setAlignment(ZKTextView::E_ALIGN_H_LEFT, ZKTextView::E_ALIGN_V_TOP);
    }
    logLine("init: A=%d items, B=%d items", (int) items.size(), LINK_N);
    updateIndexText();
    s_wheelA.refresh();
    s_wheelB.refresh();
    LOGD("wheelpicker example init");
}

static void onUI_intent(const Intent *intentPtr) {
    (void) intentPtr;
}

static void onUI_show() {
    s_wheelA.refresh();
    s_wheelB.refresh();
}

static void onUI_hide() {
}

static void onUI_quit() {
}

static void onProtocolDataUpdate(const SProtocolData &data) {
    (void) data;
}

static bool onUI_Timer(int id) {
    if (id != 0) return true;
    /* 两轮合计耗时（宿主口径：这就是「一帧里滚轮要花的活」） */
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    s_wheelA.tick();
    s_wheelB.tick();
    clock_gettime(CLOCK_MONOTONIC, &t1);
    int us = (int) ((t1.tv_sec - t0.tv_sec) * 1000000 + (t1.tv_nsec - t0.tv_nsec) / 1000);
    s_hostPerf[s_hostPerfIdx] = us;
    s_hostPerfIdx = (s_hostPerfIdx + 1) % HOST_PERF_N;
    if (s_hostPerfN < HOST_PERF_N) s_hostPerfN++;

    /* 每 15 帧刷一次 HUD：宿主两轮合计 + 包内左轮单轮（都是环形缓冲口径） */
    if ((++s_hudTick % 15) == 0 && mTxtPerfPtr != NULL) {
        long long sum = 0;
        int mx = 0;
        for (int i = 0; i < s_hostPerfN; ++i) {
            sum += s_hostPerf[i];
            if (s_hostPerf[i] > mx) mx = s_hostPerf[i];
        }
        int avg = s_hostPerfN ? (int) (sum / s_hostPerfN) : 0;
        int pf = 0, pa = 0, pm = 0;
        s_wheelA.getPerf(pf, pa, pm);
        char buf[160];
        snprintf(buf, sizeof(buf), "both: avg %dus max %dus (n=%d)   A only: avg %dus max %dus",
                 avg, mx, s_hostPerfN, pa, pm);
        mTxtPerfPtr->setText(buf);

        /* 布局自检：把两轮的「滚动位置 + 每槽位 item@行框top」直接显示出来（排错/验收用） */
        if (mTxtDbgAPtr != NULL) mTxtDbgAPtr->setText(s_wheelA.debugDump());
        if (mTxtDbgBPtr != NULL) mTxtDbgBPtr->setText(s_wheelB.debugDump());
    }
    return true;
}

static bool onmainActivityTouchEvent(const MotionEvent &ev) {
    /* 契约第 3 条：把触摸转给滚轮（包内自己做命中判定，命中才消费） */
    if (s_wheelA.onTouch(ev)) return true;
    if (s_wheelB.onTouch(ev)) return true;
    return false;
}
