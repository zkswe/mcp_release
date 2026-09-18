/**
 * zk_wheelpicker.h —— FlyThings 滚轮选择器（自绘 + 惯性 + 吸附）
 *
 * 补哪个缺口：`ui_v1/gap-list.md` **G-23「无滚轮选择器 WheelPicker（联动/惯性）」= L5**
 *   （映射表 `mcp_control_map.json`：小程序 `picker-view` → `wheelpicker`，级别 L5）
 *   源能力：iOS WheelPicker / Android NumberPicker / 小程序 `picker-view`（多列联动 + 惯性吸附）
 *
 * 平台限制（决定了本包的实现形态，都是实测结论）
 *   ① `ZKPainter` **没有文字 API**，也没有 alpha/clip → 文字行必须由 **宿主提供的 ZKTextView 池** 承载，
 *      painter 只画「选中带 / 分隔线 / 上下边缘带」；
 *   ② 没有 alpha → 上下边缘的「淡出」用 **文字色向底色插值** 近似（所以 `Style::bg` 必须给真实底色）；
 *   ③ 定时器由**宿主 Activity** 提供（`REGISTER_ACTIVITY_TIMER_TAB` + `onUI_Timer`），
 *      本包只暴露 `tick()`，返回「是否还需要继续跑帧」（省 CPU）。
 *
 * 用法见 example/；契约（少一条就出问题）：
 *   attach(painter, rows, rowCount) → setStyle() → setItems() → setIndex() → refresh()，
 *   并在 onUI_Timer 里调 tick()（16ms 一帧）。
 */
#ifndef __ZK_UI_V1_WHEELPICKER_H__
#define __ZK_UI_V1_WHEELPICKER_H__

#pragma once

#include <string>
#include <vector>

#include "control/ZKPainter.h"
#include "control/ZKTextView.h"
#include "control/ZKBase.h"
#include "control/Common.h"      /* MotionEvent / LayoutPosition 都在这里（easyui 没有 events/ 目录）*/

namespace zk {
namespace ui_v1 {

class WheelPicker {
public:
    /** 外观与手感参数（默认值 = example 实测可用的一套） */
    struct Style {
        unsigned int bg;             /* 控件底色（必给：边缘淡出按它插值） */
        unsigned int textColor;      /* 普通行文字色 */
        unsigned int selTextColor;   /* 选中行文字色 */
        unsigned int bandColor;      /* 选中带填充色（盖在 painter 上） */
        unsigned int lineColor;      /* 行分隔线色 */
        int rowHeight;               /* 行高（px） */
        int visibleRows;             /* 可见行数（建议奇数 3/5/7） */
        int bandInset;               /* 选中带左右内缩（px，0 = 通栏） */
        int bandRadius;              /* 选中带圆角（px，0 = 直角） */
        bool showLines;              /* 是否画行分隔线 */
        bool fadeEdges;              /* 边缘行是否向底色淡出（伪 alpha） */
        double fadeMax;              /* 最远行淡出上限（0~1；1 = 完全混成底色 = 看不见） */

        static Style defaultStyle();
    };

    /** 回调（都在 UI 线程；业务侧不要做耗时操作） */
    class Listener {
    public:
        virtual ~Listener() {}
        /** 滚动中（每个 tick 都可能回调；idx = 当前最近行） */
        virtual void onWheelChanged(int idx) { (void) idx; }
        /** 吸附完成（停下后只回调一次） */
        virtual void onWheelSettled(int idx) { (void) idx; }
    };

    WheelPicker();
    ~WheelPicker();

    /* ---------- 必备三件套 ---------- */
    /** rows = 宿主工程里的 textview 指针数组（数量 ≥ visibleRows，本包只管挪位置/改文字/改颜色） */
    void attach(ZKPainter *painter, ZKTextView **rows, int rowCount);
    void setStyle(const Style &st);
    /**
     * @brief 触摸坐标原点补偿（**放在带偏移的容器里的宿主必须调**）。
     *
     * 为什么需要：`ZKPainter::getPosition()` 给的是**父相对坐标**，而触摸事件是**屏幕绝对坐标**。
     * 滚轮直接挂在根节点上时两者相等（example 就是这种），但放进带偏移的容器（如页面 `window`，
     * y=56）后：命中判定与「点某行选中」的相对偏移算错 -> 触摸落不到轮子上/选错行。
     * （设备端 `ZKBase::getAbsolutePosition()` 未导出，属于 D20 同族限制，不能靠它补救。）
     * 用法：`w.setTouchOrigin(containerPos.mLeft, containerPos.mTop);`
     */
    void setTouchOrigin(int originX, int originY);
    /** 数据（每行一条）。内部会做首尾夹取与重排。 */
    void setItems(const std::vector<std::string> &items);
    void setItems(const char *const *arr, int n);
    /** 当前选中行；animate=true 走一段吸附动画 */
    void setIndex(int idx, bool animate = false);
    int  getIndex() const { return mIndex; }
    int  getItemCount() const { return (int) mItems.size(); }
    const char *getItem(int idx) const;   /* 越界返回 "" */

    void setListener(Listener *l) { mListener = l; }

    /* ---------- 帧循环（宿主定时器里调，建议 16ms） ---------- */
    /** 返回 true = 还在动（宿主可以据此继续/停掉定时器）；false = 已静止 */
    bool tick();

    /** 整屏刷新（位置 + 文字 + 颜色 + painter 重绘） */
    void refresh();
    /** 强制静止到当前 index（无动画） */
    void stop();

    /* ---------- 触摸：宿主在 onXXXTouchEvent 里转发 ---------- */
    /** 命中判定用 painter 的 position（父相对）+ setTouchOrigin 补偿；
     *  返回 true = 已消费（宿主 return true 吞掉） */
    bool onTouch(const MotionEvent &ev);
    /** 该点是否落在控件内（宿主可先判，再决定是否转发） */
    bool hitTest(int x, int y) const;

    /* ---------- 性能自检（验收用；关掉零开销） ---------- */
    /** hud = 显示「帧耗时 avg/max µs + 实测帧率」的 textview；传 NULL 关闭 */
    void setPerfHud(ZKTextView *hud);
    /** 最近 N 帧耗时（微秒），N = 120 环形缓冲 */
    void getPerf(int &frames, int &avgUs, int &maxUs) const;

    /* ---------- 布局自检（排错用） ---------- */
    /** 一行文本：滚动位置 + 每个文字槽位当前承载的 item 下标 @ 行框 top（-1 = 空闲）
     *  例：`s=0.00 idx=0 | 0@90 1@130 2@170 3@210 -1@-1`  */
    const char *debugDump() const;

    /* ---------- 重绘（设备端没有区域标脏 API，只能整块标脏） ---------- */
    /** 强制重绘：painter + 池里每个 textview 都 setInvalid(true)。
     *  什么时候必须调：**换了数据（setItems）之后**、从隐藏页回来、或发现旁列残留旧像素时。
     *  （setItems 内部已自动调一次） */
    void forceRepaint();

private:
    struct Impl;
    Impl *mImpl;
    int   mIndex;
    int   mRowCount;
    std::vector<std::string> mItems;
    Style mStyle;
    Listener *mListener;
    mutable char mDump[256];      /* debugDump() 的缓冲区 */
};

}   // namespace ui_v1
}   // namespace zk

#endif  // __ZK_UI_V1_WHEELPICKER_H__
