#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD
#include "uart/ProtocolSender.h"
#include <cstdio>
#include "zk/zk_chart.h"

/* ==========================================================================
 * components/ui_v1/Chart —— 最小可跑示例（Z21 1024x600 真机验收）
 *
 * 五张图（每个 Chart 实例绑一个 painter）：
 *   折线 PtLine / 分组柱 PtBar / 三同心环 PtRing / 仪表盘 PtGauge / 分段环 PtSegRing
 * 三条验收线：
 *   (1) 点「换一批数据」-> 五个系列全换 + 五个 refresh() -> 画面必须整体变化；
 *   (2) 点「追加一个点」-> appendPoint + refresh() -> 折线长度/形状变化；
 *   (3) 分段环（v0.2.0 新增 setRingSegments）：内环 2 段 / 中环 3 段 / 外环 5 段，
 *       「换一批数据」后各段权重变化 -> 环上的色块扇区跟着变（见 evidence/06、07）。
 * 组件实现：src/zk/zk_chart.{h,cpp}（从 components/ui_v1/Chart/ 拷来，原样未改）
 * ========================================================================== */

#define N 12

static zk::ui_v1::Chart s_line;
static zk::ui_v1::Chart s_bar;
static zk::ui_v1::Chart s_ring;
static zk::ui_v1::Chart s_gauge;
static zk::ui_v1::Chart s_seg;                 /* v0.2.0：分段环 */

/* 刻度文字池（必须与 painter 同父；坐标由组件写） */
static ZKTextView *s_lineY[6] = { 0, 0, 0, 0, 0, 0 };
static ZKTextView *s_barY[6]  = { 0, 0, 0, 0, 0, 0 };
static ZKTextView *s_ringT[3] = { 0, 0, 0 };
static ZKTextView *s_gaugeT[3] = { 0, 0, 0 };
static ZKTextView *s_segT[3] = { 0, 0, 0 };    /* 分段环：每环显示「最大段占比」 */

/* 数据（固定种子的 LCG -> 每次上电一致，便于真机像素比对） */
static float s_visits[N];
static float s_revA[N];
static float s_revB[N];
static float s_ringPct[3];
static float s_gaugeVal;

/* 分段环数据：内环 2 段 / 中环 3 段 / 外环 5 段（权重，组件按总和归一） */
static const int SEG_N[3] = { 2, 3, 5 };
static float s_segVal[3][5];
static unsigned int s_seed = 20260916u;
static int s_round = 0;

static float rnd01() {
    s_seed = s_seed * 1103515245u + 12345u;
    return (float)((s_seed >> 16) & 0x7FFF) / 32767.0f;
}

static void setStatus(const char *fmt, float a, float b, float c) {
    char buf[160];
    snprintf(buf, sizeof(buf), fmt, (double)a, (double)b, (double)c);
    if (mTvStatusPtr != NULL) {
        mTvStatusPtr->setText(buf);
    }
}

static void regenData() {
    for (int i = 0; i < N; ++i) {
        s_visits[i] = 20.0f + 78.0f * rnd01();
        s_revA[i]   = 10.0f + 84.0f * rnd01();
        s_revB[i]   = 10.0f + 84.0f * rnd01();
    }
    s_ringPct[0] = 0.20f + 0.78f * rnd01();
    s_ringPct[1] = 0.20f + 0.78f * rnd01();
    s_ringPct[2] = 0.20f + 0.78f * rnd01();
    s_gaugeVal = 10.0f + 80.0f * rnd01();
    for (int k = 0; k < 3; ++k) {
        for (int i = 0; i < SEG_N[k]; ++i) {
            s_segVal[k][i] = 1.0f + 9.0f * rnd01();
        }
    }
}

/* 四张图一次全刷：painter 不自动重绘，改完数据必须显式走一遍 */
static void repaintAll() {
    s_line.setSeries(0, s_visits, N);
    s_line.refresh();

    s_bar.setSeries(0, s_revA, N);
    s_bar.setSeries(1, s_revB, N);
    s_bar.refresh();

    s_ring.setRingPercent(0, s_ringPct[0]);
    s_ring.setRingPercent(1, s_ringPct[1]);
    s_ring.setRingPercent(2, s_ringPct[2]);
    s_ring.refresh();

    s_gauge.setGaugeValue(s_gaugeVal);
    s_gauge.refresh();

    /* 分段环：每环切成 SEG_N[k] 段（权重归一，段间隙 2°，第 1 段从正上方顺时针） */
    static char segMsg[96] = "ok";
    int segCode = 0;
    for (int k = 0; k < 3; ++k) {
        zk::ui_v1::Chart::Segment segs[5];
        for (int i = 0; i < SEG_N[k]; ++i) {
            segs[i].value = s_segVal[k][i];
            segs[i].color = 0;                 /* 0 = 用默认系列色 */
        }
        zk::ui_v1::Chart::Result r = s_seg.setRingSegments(k, segs, SEG_N[k]);
        if (!r.ok()) {
            segCode = r.code;
            snprintf(segMsg, sizeof(segMsg), "setRingSegments err%d: %s", r.code, r.msg.c_str());
        }
    }
    s_seg.refresh();

    /* 分段环的权重写进日志区（证据图里要能读出「数据真的换了」） */
    if (mTvLogPtr != NULL) {
        char buf[192];
        if (segCode != 0) {
            mTvLogPtr->setText(segMsg);
        } else {
            snprintf(buf, sizeof(buf),
                     "分段环 权重（按总和归一）:%s 内 %d/%d 中 %d/%d/%d 外 %d/%d/%d/%d/%d",
                     "\n",
                     (int)s_segVal[0][0], (int)s_segVal[0][1],
                     (int)s_segVal[1][0], (int)s_segVal[1][1], (int)s_segVal[1][2],
                     (int)s_segVal[2][0], (int)s_segVal[2][1], (int)s_segVal[2][2],
                     (int)s_segVal[2][3], (int)s_segVal[2][4]);
            mTvLogPtr->setText(buf);
        }
    }
}

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    /* 本示例不自动跑数据；改数据全靠按钮（便于截图比对） */
};

static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD

    /* --- 折线 --- */
    zk::ui_v1::Chart::Style st;
    st.areaFill = true;                          // 折线带面积渐层（混色近似 alpha）
    s_line.attach(mPtLinePtr);
    s_line.setType(zk::ui_v1::Chart::LINE);
    s_line.setAxisRange(0.0f, 100.0f, 5);
    s_line.setStyle(st);
    s_lineY[0] = mTvLineY0Ptr; s_lineY[1] = mTvLineY1Ptr; s_lineY[2] = mTvLineY2Ptr;
    s_lineY[3] = mTvLineY3Ptr; s_lineY[4] = mTvLineY4Ptr; s_lineY[5] = mTvLineY5Ptr;
    s_line.attachLabels(s_lineY, 6);

    /* --- 分组柱 --- */
    s_bar.attach(mPtBarPtr);
    s_bar.setType(zk::ui_v1::Chart::BAR);
    s_bar.setAxisRange(0.0f, 100.0f, 5);
    s_bar.setStyle(st);                          // areaFill 对 BAR 无效，无副作用
    s_barY[0] = mTvBarY0Ptr; s_barY[1] = mTvBarY1Ptr; s_barY[2] = mTvBarY2Ptr;
    s_barY[3] = mTvBarY3Ptr; s_barY[4] = mTvBarY4Ptr; s_barY[5] = mTvBarY5Ptr;
    s_bar.attachLabels(s_barY, 6);

    /* --- 同心环（三环；文字位置由 json 定，组件只写文字/颜色） --- */
    s_ring.attach(mPtRingPtr);
    s_ring.setType(zk::ui_v1::Chart::RING);
    s_ringT[0] = mTvRing0Ptr; s_ringT[1] = mTvRing1Ptr; s_ringT[2] = mTvRing2Ptr;
    s_ring.attachLabels(s_ringT, 3);

    /* --- 仪表盘（三段分区 + 20 格刻度） --- */
    zk::ui_v1::Chart::Zone zones[3];
    zones[0].v1 = 0.0f;   zones[0].v2 = 40.0f;  zones[0].color = 0x2196F3;
    zones[1].v1 = 40.0f;  zones[1].v2 = 70.0f;  zones[1].color = 0x4CAF50;
    zones[2].v1 = 70.0f;  zones[2].v2 = 100.0f; zones[2].color = 0xF44336;
    zk::ui_v1::Chart::Style gst;
    gst.series[1] = 0x607D8B;                    // 指针色
    s_gauge.attach(mPtGaugePtr);
    s_gauge.setType(zk::ui_v1::Chart::GAUGE);
    s_gauge.setAxisRange(0.0f, 100.0f, 5);
    s_gauge.setGaugeZones(zones, 3);
    s_gauge.setStyle(gst);
    s_gaugeT[0] = mTvGaugeMinPtr; s_gaugeT[1] = mTvGaugeMaxPtr; s_gaugeT[2] = mTvGaugeValPtr;
    s_gauge.attachLabels(s_gaugeT, 3);

    /* --- 分段环（v0.2.0：setRingSegments；文字只占 1 槽 -> labels[0] 显示内环最大段占比） --- */
    s_seg.attach(mPtSegRingPtr);
    s_seg.setType(zk::ui_v1::Chart::RING);
    s_segT[0] = mTvSeg0Ptr; s_segT[1] = mTvSeg1Ptr; s_segT[2] = mTvSeg2Ptr;
    s_seg.attachLabels(s_segT, 3);

    regenData();
    repaintAll();
    ++s_round;
    setStatus("初始数据 round=%.0f  ring0=%.0f%%  gauge=%.0f  seg=N2/3/5",
              1.0f * s_round, s_ringPct[0] * 100.0f, s_gaugeVal);
}

static void onUI_intent(const Intent *intentPtr) { (void)intentPtr; }

/* 切回本页：painter 不会自动重绘 -> 全刷一遍 */
static void onUI_show() {
    repaintAll();
}

static void onUI_hide() {}

static void onUI_quit() {
    s_line.detach();
    s_bar.detach();
    s_ring.detach();
    s_gauge.detach();
    s_seg.detach();
}

static void onProtocolDataUpdate(const SProtocolData &data) { (void)data; }

static bool onUI_Timer(int id) { (void)id; return true; }

static bool onmainActivityTouchEvent(const MotionEvent &ev) { (void)ev; return false; }

/* ---- 换一批数据：四个系列全换 + 四个 refresh ---- */
static bool onButtonClick_BtnNext(ZKButton *pButton) {
    (void)pButton;
    regenData();
    repaintAll();
    ++s_round;
    setStatus("换一批 round=%.0f  ring0=%.0f%%  gauge=%.0f  seg=N2/3/5",
              1.0f * s_round, s_ringPct[0] * 100.0f, s_gaugeVal);
    return false;
}

/* ---- 追加一个点：appendPoint + refresh（验证增量变化也重绘） ---- */
static bool onButtonClick_BtnAppend(ZKButton *pButton) {
    (void)pButton;
    float v = 20.0f + 78.0f * rnd01();
    int n = s_line.appendPoint(0, v);
    if (n < 0) {
        if (mTvLogPtr != NULL) mTvLogPtr->setText("appendPoint 失败（系列下标越界）");
        return false;
    }
    s_line.refresh();
    char buf[96];
    snprintf(buf, sizeof(buf), "追加一个点：count=%d  最后一个值=%.0f", n, (double)v);
    if (mTvLogPtr != NULL) mTvLogPtr->setText(buf);
    return false;
}
