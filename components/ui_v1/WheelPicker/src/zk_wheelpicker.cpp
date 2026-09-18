/**
 * zk_wheelpicker.cpp —— 滚轮选择器实现（自绘 + 惯性 + 吸附）
 *
 * 实现要点（都是被平台限制逼出来的，见头文件注释）：
 *   ① **文字由宿主 textview 池承载**：painter 没有文字 API，所以本包只负责
 *      「把每个 textview 挪到正确位置 + 换文字 + 按距离改文字色」；
 *   ② **静态层只画一次**：底色 / 选中带 / 分隔线 与滚动无关 → `mStaticDirty` 时才重画，
 *      滚动中每帧只动 textview（这是本包性能的关键，实测见 README §性能）；
 *   ③ **伪 alpha 淡出**：边缘行文字色向 Style::bg 插值（没有真 alpha）；
 *   ④ **帧循环交宿主**：tick() 返回「是否还在动」，宿主在 onUI_Timer 里调（16ms）。
 *
 * 坐标系：全部用 painter 的局部坐标（0,0 = painter 左上角）；
 *        滑动量 `mScroll` 用 index 空间（= 中间行当前显示的 item 下标，可为小数）。
 */
#include "zk/zk_wheelpicker.h"

#include <algorithm>
#include <math.h>
#include <vector>
#include <stdio.h>
#include <string.h>
#include <time.h>

namespace zk {
namespace ui_v1 {

#define WP_PERF_N 120

static double nowSec() {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double) ts.tv_sec + (double) ts.tv_nsec / 1e9;
}

static int iClamp(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }
static double dClamp(double v, double lo, double hi) { return v < lo ? lo : (v > hi ? hi : v); }

/* 色彩插值：t = 0 → fg，t = 1 → bg（用于伪 alpha 淡出） */
static unsigned int mixColor(unsigned int fg, unsigned int bg, double t) {
    t = dClamp(t, 0.0, 1.0);
    int fr = (fg >> 16) & 0xFF, fgn = (fg >> 8) & 0xFF, fb = fg & 0xFF;
    int br = (bg >> 16) & 0xFF, bgn = (bg >> 8) & 0xFF, bb = bg & 0xFF;
    int r = (int) (fr + (br - fr) * t + 0.5);
    int g = (int) (fgn + (bgn - fgn) * t + 0.5);
    int b = (int) (fb + (bb - fb) * t + 0.5);
    return ((unsigned int) (r & 0xFF) << 16) | ((unsigned int) (g & 0xFF) << 8) | (unsigned int) (b & 0xFF);
}

WheelPicker::Style WheelPicker::Style::defaultStyle() {
    Style st;
    st.bg           = 0xFFFFFF;
    st.textColor    = 0x666666;
    st.selTextColor = 0x0052D9;
    st.bandColor    = 0xF2F3FF;
    st.lineColor    = 0xE7E7E7;
    st.rowHeight    = 40;
    st.visibleRows  = 5;
    st.bandInset    = 8;
    st.bandRadius   = 8;
    st.showLines    = true;
    st.fadeEdges    = true;
    st.fadeMax      = 0.55;      /* 最远行保留 45% 文字色（1.0 → 整行消失，实测踩过） */
    return st;
}

struct WheelPicker::Impl {
    ZKPainter *painter;
    std::vector<ZKTextView *> pool;
    std::vector<int> poolItem;        /* 该 textview 当前承载的 item 下标；-1 = 空闲 */
    std::vector<double> poolY;        /* 该 textview 上次摆到的局部 y（double） */
    std::vector<char> poolVis;        /* 上次是否可见（ZKTextView 没有 isVisible() getter，自己记） */
    std::vector<int> poolText;        /* 该行当前已写入的 item 下标（-1 = 未写/已失效） */
    std::vector<int> poolFade;        /* 当前文字色的量化档位，用于少调 setTextColor */

    double scroll;                    /* index 空间当前位置 */
    double vel;                       /* index/秒 */
    int orgX, orgY;                   /* 触摸坐标原点补偿（父容器偏移；setTouchOrigin） */
    bool dragging;
    int lastY;
    double lastT;
    double downT;
    double downY;
    double moveT;                     /* 上次 MOVE 时间（真实 dt 估速） */
    double flingTarget;               /* 甩动目标行（NAN = 无） */
    int lastDir;                      /* 最近一次拖动方向（+1 = index 增大） */
    double downScroll;                /* DOWN 时的行号（落点基准） */
    double layoutT;                   /* 上次文字层布局时间（帧率上限用） */
    bool dirtyStatic;                 /* 需要重画静态层 */
    bool dirtyText;                   /* 需要重排 textview */
    bool relayoutAll;                 /* 数据换过（setItems）-> 池全部重绑（文字必须重新 setText） */
    bool rowSetChanged;               /* 本帧发生「换绑 / 隐藏」-> 旧位置会留下像素，必须整块重绘 */
    bool settledFired;

    /* 性能环形缓冲（微秒） */
    int perf[WP_PERF_N];
    int perfN, perfIdx;
    ZKTextView *hud;
    int hudTick;

    Impl() : painter(0), scroll(0), vel(0), orgX(0), orgY(0), dragging(false), lastY(0), lastT(0),
             downT(0), downY(0), dirtyStatic(true), moveT(0), flingTarget(NAN), lastDir(0), downScroll(0), layoutT(0), dirtyText(true), relayoutAll(true),
             rowSetChanged(false), settledFired(true),
             perfN(0), perfIdx(0), hud(0), hudTick(0) {
        memset(perf, 0, sizeof(perf));
    }
};

WheelPicker::WheelPicker() : mImpl(new Impl()), mIndex(0), mRowCount(0), mListener(0) {
    mStyle = Style::defaultStyle();
}

WheelPicker::~WheelPicker() {
    delete mImpl;
}

void WheelPicker::attach(ZKPainter *painter, ZKTextView **rows, int rowCount) {
    mImpl->painter = painter;
    mImpl->pool.clear();
    mImpl->poolItem.clear();
    mImpl->poolY.clear();
    mImpl->poolVis.clear();
    mImpl->poolText.clear();
    mImpl->poolFade.clear();
    for (int i = 0; i < rowCount; ++i) {
        if (rows && rows[i]) {
            mImpl->pool.push_back(rows[i]);
            mImpl->poolItem.push_back(-1);
            mImpl->poolY.push_back(0);
            mImpl->poolVis.push_back(0);
            mImpl->poolText.push_back(-1);
            mImpl->poolFade.push_back(-1);
        }
    }
    mRowCount = (int) mImpl->pool.size();
    mImpl->dirtyStatic = true;
    mImpl->dirtyText = true;
}

void WheelPicker::setStyle(const Style &st) {    mStyle = st;
    if (mStyle.visibleRows < 1) mStyle.visibleRows = 1;
    if ((mStyle.visibleRows & 1) == 0) mStyle.visibleRows += 1;   /* 取奇数，保证有正中行 */
    if (mStyle.rowHeight < 8) mStyle.rowHeight = 8;
    mImpl->dirtyStatic = true;
    mImpl->dirtyText = true;
    refresh();
}

void WheelPicker::setItems(const std::vector<std::string> &items) {
    mItems = items;
    /* ★ 数据换了但 item 下标可能没变 -> 必须让池全部重绑（否则 setText 不会重调，
     *   屏幕继续显示旧字符串；实测联动重建右轮时踩过）。 */
    mImpl->relayoutAll = true;
    mImpl->scroll = dClamp(mImpl->scroll, 0.0, (double) iClamp((int) mItems.size() - 1, 0, 1 << 30));
    if (mIndex >= (int) mItems.size()) {
        mIndex = iClamp((int) mItems.size() - 1, 0, 1 << 30);
        mImpl->scroll = mIndex;
    }
    mImpl->dirtyText = true;
    refresh();
    /* 方案 ①：本代平台按控件标脏、且设备端没有区域标脏 API -> 换数据后必须整块重绘一遍，
     * 否则**旁列**会残留旧像素（实测：右轮重建后有一行停在旧 y）。 */
    forceRepaint();
}

void WheelPicker::setItems(const char *const *arr, int n) {
    std::vector<std::string> v;
    for (int i = 0; i < n; ++i) {
        v.push_back(arr[i] ? arr[i] : "");
    }
    setItems(v);
}

const char *WheelPicker::getItem(int idx) const {
    if (idx < 0 || idx >= (int) mItems.size()) return "";
    return mItems[idx].c_str();
}

void WheelPicker::setIndex(int idx, bool animate) {
    int n = (int) mItems.size();
    if (n <= 0) return;
    idx = iClamp(idx, 0, n - 1);
    mIndex = idx;
    if (animate) {
        mImpl->vel = 0;
        mImpl->settledFired = false;
        /* 目标与当前位置差得多时给一个初速度，让它滚过去（观感上像"转"而不是"跳"） */
        double d = (double) idx - mImpl->scroll;
        mImpl->vel = dClamp(d * 6.0, -28.0, 28.0);
    } else {
        mImpl->scroll = idx;
        mImpl->vel = 0;
    }
    mImpl->dirtyText = true;
    refresh();
}

void WheelPicker::stop() {
    mImpl->scroll = (double) iClamp((int) floor(mImpl->scroll + 0.5), 0,
                                    iClamp((int) mItems.size() - 1, 0, 1 << 30));
    mImpl->vel = 0;
    mImpl->dragging = false;
    mImpl->dirtyText = true;
    refresh();
}

bool WheelPicker::hitTest(int x, int y) const {
    if (!mImpl->painter) return false;
    const LayoutPosition &p = mImpl->painter->getPosition();
    const int lx = x - mImpl->orgX;          /* 屏幕绝对坐标 -> 容器相对坐标（父相对 = 控件坐标系） */
    const int ly = y - mImpl->orgY;
    return (lx >= p.mLeft && lx < p.mLeft + p.mWidth && ly >= p.mTop && ly < p.mTop + p.mHeight);
}

void WheelPicker::setTouchOrigin(int originX, int originY) {
    mImpl->orgX = originX;
    mImpl->orgY = originY;
}

/* ---------------- 静态层：底色 + 选中带 + 分隔线（滚动中不重画） ---------------- */
static void paintStatic(WheelPicker::Style &st, ZKPainter *painter) {
    const LayoutPosition &pos = painter->getPosition();
    const int w = pos.mWidth, h = pos.mHeight;
    const int rowH = st.rowHeight;
    const int bandTop = h / 2 - rowH / 2;

    painter->erase(0, 0, w, h);
    /* painter 必须逐笔 setSourceColor（没有「当前色」继承），且自己负责擦除/重绘 */
    painter->setSourceColor(st.bg);
    painter->fillRect(0, 0, w, h, 0);

    /* 选中带 */
    painter->setSourceColor(st.bandColor);
    painter->fillRect(st.bandInset, bandTop, w - 2 * st.bandInset, rowH, st.bandRadius);

    /* 分隔线：选中带上下各一条 */
    if (st.showLines) {
        painter->setSourceColor(st.lineColor);
        painter->fillRect(0, bandTop, w, 1, 0);
        painter->fillRect(0, bandTop + rowH - 1, w, 1, 0);
    }
}

bool WheelPicker::tick() {
    Impl *im = mImpl;
    if (!im->painter || mRowCount <= 0) return false;

    double t0 = nowSec();
    double dt = (im->lastT > 0) ? (t0 - im->lastT) : 0.016;
    im->lastT = t0;
    if (dt > 0.25) dt = 0.25;             /* 长卡顿别把滚动条跳飞 */
    if (dt < 0.001) dt = 0.001;

    const int n = (int) mItems.size();
    bool animating = false;

    if (n > 0) {
        if (im->dragging) {
            animating = true;             /* 拖动中：位置由 onTouch 直接改，这里只负责重排 */
        } else if (!(im->flingTarget != im->flingTarget)) {
            /* ★ 甩动落点缓动（10/s），到点即 settle */
            animating = true;
            double d = im->flingTarget - im->scroll;
            if (fabs(d) < 0.004) {
                im->scroll = im->flingTarget;
                im->flingTarget = NAN;
                im->vel = 0;
                im->dirtyText = true;
            } else {
                im->scroll += d * dClamp(dt * 10.0, 0.0, 1.0);
                im->vel *= pow(0.25, dt);
                im->dirtyText = true;
            }
        } else if (fabs(im->vel) > 0.35) {
            animating = true;
            im->scroll += im->vel * dt;
            im->vel *= pow(0.055, dt);    /* 衰减：~0.055^(1/秒)，1 秒掉到 5.5% */
            /* 越界回弹（橡皮筋） */
            if (im->scroll < 0) {
                im->scroll += (-im->scroll) * dClamp(dt * 8.0, 0, 1);
                im->vel *= 0.5;
            } else if (im->scroll > n - 1) {
                im->scroll -= (im->scroll - (n - 1)) * dClamp(dt * 8.0, 0, 1);
                im->vel *= 0.5;
            }
            im->dirtyText = true;
        } else {
            /* 吸附到最近行 */
            double target = dClamp(floor(im->scroll + 0.5), 0.0, (double) (n - 1));
            double d = target - im->scroll;
            if (fabs(d) > 0.002) {
                animating = true;
                im->scroll += d * dClamp(dt * 14.0, 0, 1);
                im->vel = 0;
                im->dirtyText = true;
            } else if (!im->settledFired) {
                im->scroll = target;
                im->vel = 0;
                im->settledFired = true;
                im->dirtyText = true;
                mIndex = (int) target;
                if (mListener) mListener->onWheelSettled(mIndex);
            }
        }
    }

    /* ---- 静态层：只在需要时重画（滚动中零开销） ---- */
    if (im->dirtyStatic) {
        paintStatic(mStyle, im->painter);
        im->dirtyStatic = false;
    }

    /* [!] 2026-09-18 16:26 钟工真机反馈「日期选择出现文字重影」——根因是这里曾加过
     *   「布局帧率上限（~36fps）」：跳过布局帧时，该隐藏/该移动的行没被处理 -> 留残影。
     *   已撤回（正确性 > CPU）；CPU 优化改用别的路子（只重绘被触摸那一列等）。 */
    if (im->dirtyText) {
        const LayoutPosition &pos = im->painter->getPosition();
        const int w = pos.mWidth, h = pos.mHeight;
        const int rowH = mStyle.rowHeight;
        const int cy = h / 2;
        const double center = im->scroll;
        const int half = mStyle.visibleRows / 2;
        const int lo0 = (int) floor(center) - half - 1;
        int lo = lo0;
        int hi = (int) floor(center) + half + 1;

        /* 数据换过：池整体失效（清缓存 -> 下面会重绑 + 重 setText） */
        if (im->relayoutAll) {
            for (size_t i = 0; i < im->pool.size(); ++i) {
                im->poolItem[i] = -1;
                im->poolY[i] = 1e9;
                im->poolFade[i] = -1;
                im->poolText[i] = -1;
            }
            im->relayoutAll = false;
        }

                /* ★ 池位分配：按「离选中行的距离」由近到远（修「可见行空白 / 月列 7月不见」）
         *   候选窗口是 2*half+3 个 item（visibleRows=5 时 7 个），而池只有 visibleRows 个槽；
         *   旧实现按 item 升序先到先得 -> 窗口内总有 item 抢不到槽 -> 整行空白且随滚动乱跳。
         *   现在槽位只发给「最近的 pool.size() 个 item」，不在集合里的槽释放。 */
        std::vector<int> wanted;
        for (int it = iClamp(lo, 0, iClamp(n - 1, 0, 1 << 30)); it <= hi && it < n; ++it) {
            if (it >= 0) wanted.push_back(it);
        }
        std::sort(wanted.begin(), wanted.end(), [center](int a, int b) {
            double da = fabs((double) a - center), db = fabs((double) b - center);
            if (da != db) return da < db;
            return a < b;                       /* 同距时偏向小 index，保证稳定 */
        });
        if ((int) wanted.size() > (int) im->pool.size()) wanted.resize(im->pool.size());
        /* 释放：槽里的 item 不在 wanted -> 释放回池（旧位置必定留像素，标脏）*/
        for (size_t i = 0; i < im->pool.size(); ++i) {
            int it = im->poolItem[i];
            if (it >= 0 && std::find(wanted.begin(), wanted.end(), it) == wanted.end()) {
                im->poolItem[i] = -1;
                im->rowSetChanged = true;
            }
        }
        /* 分配：wanted 中还没有槽的，按距离由近到远取空闲槽（位置/文字留到下面摆位循环写）*/
        for (size_t wi = 0; wi < wanted.size(); ++wi) {
            int it = wanted[wi];
            bool has = false;
            for (size_t i = 0; i < im->pool.size(); ++i) {
                if (im->poolItem[i] == it) { has = true; break; }
            }
            if (has) continue;
            for (size_t i = 0; i < im->pool.size(); ++i) {
                if (im->poolItem[i] < 0) {
                    im->poolItem[i] = it;
                    im->poolY[i] = 1e9;
                    im->poolFade[i] = -1;
                    im->rowSetChanged = true;
                    break;
                }
            }
        }
/* 摆位置 + 文字色（伪 alpha 淡出） */
        const int fadeSteps = 20;
        for (size_t i = 0; i < im->pool.size(); ++i) {
            ZKTextView *tv = im->pool[i];
            int it = im->poolItem[i];
            if (it < 0 || it >= n) {
                if (im->poolVis[i]) {
                    tv->setVisible(false);
                    tv->setInvalid(true);
                    im->poolVis[i] = 0;
                    im->poolText[i] = -1;          /* 文字失效：下次可见时必须重写 */
                    im->rowSetChanged = true;
                }
                continue;
            }
            double dist = fabs((double) it - center);          /* 离选中行的距离（行） */
            double y = cy + ((double) it - center) * rowH - rowH / 2.0;
            int yy = (int) floor(y + 0.5);

            /* 行中心跑出滚轮盒 -> 隐藏（平台没有 clip，不隐藏就会溢到轮子外面去，实测踩过） */
            if (yy + rowH / 2 < 0 || yy + rowH / 2 >= h) {
                if (im->poolVis[i]) {
                    tv->setVisible(false);
                    tv->setInvalid(true);
                    im->poolVis[i] = 0;
                    im->poolText[i] = -1;          /* 移出盒子：文字失效（回到盒内必须重写） */
                    im->rowSetChanged = true;
                }
                continue;
            }

            LayoutPosition p = tv->getPosition();
            bool needPos = (im->poolY[i] != (double) yy) || !im->poolVis[i];
            bool needTxt = (im->poolText[i] != it);
            if (needPos || needTxt) {
                if (needPos) {
                    tv->setPosition(LayoutPosition(p.mLeft, pos.mTop + yy, p.mWidth, p.mHeight));
                }
                if (needTxt) {
                    tv->setText(mItems[it].c_str());   /* 位置定下来之后才写文字 */
                    im->poolText[i] = it;
                }
                tv->setVisible(true);
                /* ★ 本代平台重绘是「按控件标脏」——只改位置/文字，框架不一定重画，
                 *   所以每次位置/文字真变了都 setInvalid(true)（设备端有该符号）。 */
                tv->setInvalid(true);
                im->poolY[i] = (double) yy;
                im->poolVis[i] = 1;
            }

            /* 文字色：0 行 = 选中色；越远越向底色淡出（量化到 20 档，减少 setTextColor 次数）
             * 淡出上限 = Style::fadeMax：老曲线「dist>=2 直接 100% 混底色」会让远端行整行看不见。 */
            double denom = (half > 0) ? (double) half : 1.0;
            double t = dClamp((dist - 0.5) / denom, 0.0, 1.0) * dClamp(mStyle.fadeMax, 0.0, 1.0);
            unsigned int c = mixColor(mStyle.textColor, mStyle.bg, mStyle.fadeEdges ? t : 0.0);
            if (dist < 0.5) {
                c = mixColor(mStyle.selTextColor, mStyle.textColor, dClamp(dist * 2.0, 0, 1));
            }
            int lvl = (int) (t * fadeSteps + 0.5) * 100 + ((dist < 0.5) ? (int) (dist * 100) : 999);
            if (lvl != im->poolFade[i]) {
                im->poolFade[i] = lvl;
                tv->setTextColor((int) c);
                tv->setInvalid(true);
            }
        }
        im->dirtyText = false;
        /* 文字层动过：先重画静态层，再让框架把这块**连同叠在上面的 textview** 重绘一遍。
         * 为什么不用 ZKBase::invalidate(LayoutPosition*)：**设备端 libeasyui 没导出**
         * （用它会 dlopen undefined symbol -> 整屏黑，与 D20 getAbsolutePosition 同族）。
         * setInvalid(bool) 是设备端有的符号，也是 RadButton 在用的帧刷新路径。
         * 行集合变化（换绑/隐藏）时旧位置一定会留像素（实测：叠字、旁列残留），
         * 这种帧必须**整块重绘**（painter + 全部行），否则残影会一直停着。 */
        im->dirtyStatic = true;
        if (im->rowSetChanged) {
            im->rowSetChanged = false;
            forceRepaint();
        } else {
            im->painter->setInvalid(true);
        }

        int nearest = (int) floor(center + 0.5);
        nearest = iClamp(nearest, 0, n - 1);
        if (nearest != mIndex) {
            mIndex = nearest;
            if (mListener) mListener->onWheelChanged(mIndex);
        }
    }

    /* ---- 性能自检 ---- */
    double t1 = nowSec();
    int us = (int) ((t1 - t0) * 1e6);
    im->perf[im->perfIdx] = us;
    im->perfIdx = (im->perfIdx + 1) % WP_PERF_N;
    if (im->perfN < WP_PERF_N) im->perfN++;
    if (im->hud && (++im->hudTick % 15) == 0) {
        int frames = 0, avg = 0, mx = 0;
        getPerf(frames, avg, mx);
        char buf[128];
        snprintf(buf, sizeof(buf), "frames %d  tick avg %dus  max %dus", frames, avg, mx);
        im->hud->setText(buf);
    }
    return animating;
}

void WheelPicker::setPerfHud(ZKTextView *hud) {
    mImpl->hud = hud;
    mImpl->hudTick = 0;
}

const char *WheelPicker::debugDump() const {
    Impl *im = mImpl;
    int off = snprintf(mDump, sizeof(mDump), "s=%.2f idx=%d pool=%d | ",
                       im->scroll, mIndex, (int) im->pool.size());
    for (size_t i = 0; i < im->pool.size() && off > 0 && off < (int) sizeof(mDump) - 24; ++i) {
        off += snprintf(mDump + off, sizeof(mDump) - off, "%d@%d ",
                        im->poolItem[i], (int) im->poolY[i]);
    }
    return mDump;
}

void WheelPicker::forceRepaint() {
    Impl *im = mImpl;
    if (!im->painter) return;
    im->dirtyStatic = true;
    im->dirtyText = true;
    im->painter->setInvalid(true);
    for (size_t i = 0; i < im->pool.size(); ++i) {
        im->pool[i]->setInvalid(true);
    }
}

void WheelPicker::getPerf(int &frames, int &avgUs, int &maxUs) const {
    frames = mImpl->perfN;
    long long sum = 0;
    int mx = 0;
    for (int i = 0; i < mImpl->perfN; ++i) {
        sum += mImpl->perf[i];
        if (mImpl->perf[i] > mx) mx = mImpl->perf[i];
    }
    avgUs = mImpl->perfN ? (int) (sum / mImpl->perfN) : 0;
    maxUs = mx;
}

void WheelPicker::refresh() {
    if (!mImpl->painter) return;
    mImpl->dirtyStatic = true;
    mImpl->dirtyText = true;
    /* 直接走一遍 tick 的绘制部分（不动速度/位置） */
    double savedVel = mImpl->vel;
    bool savedDragging = mImpl->dragging;
    mImpl->vel = 0;
    mImpl->dragging = false;
    tick();
    mImpl->vel = savedVel;
    mImpl->dragging = savedDragging;
}

bool WheelPicker::onTouch(const MotionEvent &ev) {
    Impl *im = mImpl;
    if (!im->painter || mRowCount <= 0 || mItems.empty()) return false;

    const int n = (int) mItems.size();
    const int action = ev.mActionStatus;
    const int x = ev.mX, y = ev.mY;                  /* 屏幕绝对坐标（hitTest 内部自己扣原点） */
    const int lx = x - im->orgX, ly = y - im->orgY;  /* 容器相对坐标（与 painter 的 position 同系） */
    (void) lx;

    if (action == MotionEvent::E_ACTION_DOWN) {
        if (!hitTest(x, y)) return false;
        const LayoutPosition &p = im->painter->getPosition();
        im->dragging = true;
        im->vel = 0;
        im->lastY = ly;
        im->downY = ly;
        im->downT = nowSec();
        im->settledFired = false;
        mImpl->dirtyText = true;
        im->moveT = 0;
        im->flingTarget = NAN;
        im->downScroll = im->scroll;
        (void) p;
        return true;
    }

    if (action == MotionEvent::E_ACTION_MOVE) {
        if (!im->dragging) return false;
        int dy = ly - im->lastY;
        im->lastY = ly;
        if (dy != 0) {
            double dScroll = -(double) dy / (double) mStyle.rowHeight;
            im->scroll += dScroll;
            /* 越界阻尼 */
            if (im->scroll < 0) im->scroll *= 0.55;
            else if (im->scroll > n - 1) im->scroll = (n - 1) + (im->scroll - (n - 1)) * 0.55;
            /* 速度：指数滑动平均（index/秒） */
            double tnow = nowSec();
            double dtm = (im->moveT > 0) ? (tnow - im->moveT) : 0.016;
            im->moveT = tnow;
            if (dtm < 0.004) dtm = 0.004;
            if (dtm > 0.060) dtm = 0.060;
            double v = -dScroll / dtm;                 /* 真实 dt，不再假设 16ms */
            im->lastDir = (dScroll > 0) ? 1 : -1;      /* 拖动方向 */
            im->vel = fabs(im->vel * 0.45 + v * 0.55);   /* 速度取模 */
            (void) 0;
            im->dirtyText = true;
        }
        return true;
    }

    if (action == MotionEvent::E_ACTION_UP || action == MotionEvent::E_ACTION_CANCEL) {
        if (!im->dragging) return false;
        im->dragging = false;
        double dt = nowSec() - im->downT;
        int moved = (ly > im->downY) ? (ly - im->downY) : (im->downY - ly);

        if (action == MotionEvent::E_ACTION_CANCEL) {
            im->vel = 0;
        } else if (moved < 8 && dt < 0.4) {
            /* 点击：直接选中点到的那一行 */
            const LayoutPosition &p = im->painter->getPosition();
            int cy = p.mHeight / 2;
            double idx = im->scroll + (double) (ly - p.mTop - cy) / (double) mStyle.rowHeight;
            im->vel = 0;
            im->scroll = dClamp(idx, 0.0, (double) (n - 1));
            im->settledFired = false;
        } else {
            /* ★ 两路：快甩=真惯性滑行（不封顶）；慢拖=精准一档；微拖=回原行 */
            double dragRows = im->scroll - im->downScroll;
            double assign = (dragRows >= 0) ? 1.0 : -1.0;
            double crossed = fabs(dragRows);
            const double FLING_MIN = 8.0;          /* 行/秒：真甩动阈值（普通拖一格约 3~5 行/秒，不走这条）*/
            if (fabs(im->vel) >= FLING_MIN) {
                /* 甩动：保留速度，让 tick 里的惯性滑行走完自然减速（滑多远由速度决定）*/
                im->flingTarget = NAN;
                im->vel = fabs(im->vel) * assign;
                if (fabs(im->vel) > 60.0) im->vel = 60.0 * assign;   /* 上限防飞太远 */
            } else if (crossed >= 0.35) {
                /* 慢拖过 1/3 行：精准进一档（基准 = DOWN 行号，不弹回）*/
                im->flingTarget = dClamp(im->downScroll + assign, 0.0, (double) (n - 1));
                im->vel = 0;
            } else {
                /* 微拖：回原行 */
                im->flingTarget = dClamp(im->downScroll, 0.0, (double) (n - 1));
                im->vel = 0;
            }
            im->settledFired = false;
        }
        im->dirtyText = true;
        return true;
    }

    return false;
}

}   // namespace ui_v1
}   // namespace zk
