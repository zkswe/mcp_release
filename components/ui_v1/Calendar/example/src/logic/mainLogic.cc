#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD
#include "uart/ProtocolSender.h"
#include <cstdio>
#include "zk/zk_calendar.h"

/* ==========================================================================
 * components/ui_v1/Calendar —— 最小可跑示例（Z21 1024x600 真机验收）
 *
 * 演示四件事：
 *   (1) 打开 modal 日历（42 个 textview）-> 显示当月网格 + 「今天」+ 标记日；
 *   (2) `<` `>` 翻月（setMonth/prevMonth/nextMonth，不触发回调）；
 *   (3) 点日号选中：**组件不装触摸监听**，业务在 onmainActivityTouchEvent 里用
 *       cellAt()/dayAt() 反算命中格 -> pickDay() -> 回调回填输入框 + 弹窗内状态行；
 *   (4) 「跳到今天」按钮：setToday + setMarkedDays 演示。
 *
 * 警告 平台坑（实测）：设备侧 libeasyui.so **没有导出** getParent()/getAbsolutePosition()，
 *    绝对坐标只能 = **沿祖先链把已知指针的 getPosition() 相加**。本示例网格直接挂在 WinCal 上
 *    （WinCal 在屏幕 (162,40)）-> 容器原点 = WinCal.getPosition()。
 * ========================================================================== */

/* 组件本体（= ../include/zk/zk_calendar.h + ../src/zk_calendar.cpp 原样拷贝） */
static zk::ui_v1::Calendar s_cal;

/* 42 个日号格（行优先 7 列 × 6 行，顺序与 json 摆放一致） */
static ZKTextView *s_cells[42];

/* 示例数据 */
static int s_marked[5] = { 5, 12, 18, 25, 30 };
static int s_markedN = 4;
static const int TODAY_Y = 2026, TODAY_M = 9, TODAY_D = 16;

static void bindCells() {
    s_cells[0]  = mTvCalD1Ptr;  s_cells[1]  = mTvCalD2Ptr;  s_cells[2]  = mTvCalD3Ptr;
    s_cells[3]  = mTvCalD4Ptr;  s_cells[4]  = mTvCalD5Ptr;  s_cells[5]  = mTvCalD6Ptr;
    s_cells[6]  = mTvCalD7Ptr;  s_cells[7]  = mTvCalD8Ptr;  s_cells[8]  = mTvCalD9Ptr;
    s_cells[9]  = mTvCalD10Ptr; s_cells[10] = mTvCalD11Ptr; s_cells[11] = mTvCalD12Ptr;
    s_cells[12] = mTvCalD13Ptr; s_cells[13] = mTvCalD14Ptr; s_cells[14] = mTvCalD15Ptr;
    s_cells[15] = mTvCalD16Ptr; s_cells[16] = mTvCalD17Ptr; s_cells[17] = mTvCalD18Ptr;
    s_cells[18] = mTvCalD19Ptr; s_cells[19] = mTvCalD20Ptr; s_cells[20] = mTvCalD21Ptr;
    s_cells[21] = mTvCalD22Ptr; s_cells[22] = mTvCalD23Ptr; s_cells[23] = mTvCalD24Ptr;
    s_cells[24] = mTvCalD25Ptr; s_cells[25] = mTvCalD26Ptr; s_cells[26] = mTvCalD27Ptr;
    s_cells[27] = mTvCalD28Ptr; s_cells[28] = mTvCalD29Ptr; s_cells[29] = mTvCalD30Ptr;
    s_cells[30] = mTvCalD31Ptr; s_cells[31] = mTvCalD32Ptr; s_cells[32] = mTvCalD33Ptr;
    s_cells[33] = mTvCalD34Ptr; s_cells[34] = mTvCalD35Ptr; s_cells[35] = mTvCalD36Ptr;
    s_cells[36] = mTvCalD37Ptr; s_cells[37] = mTvCalD38Ptr; s_cells[38] = mTvCalD39Ptr;
    s_cells[39] = mTvCalD40Ptr; s_cells[40] = mTvCalD41Ptr; s_cells[41] = mTvCalD42Ptr;
}

static void setStatus(const char *txt) {
    if (mTvStatusPtr != NULL) {
        mTvStatusPtr->setText(txt);
    }
}

static void setCalLog(const char *txt) {
    if (mTvCalLogPtr != NULL) {
        mTvCalLogPtr->setText(txt);
    }
}

/* 组件回调：选中日期 -> 回填输入框 + 弹窗状态行（回调在 pickDay() 内部同步触发） */
static void onDatePicked(const zk::ui_v1::Calendar::Date &d, void *user) {
    (void)user;
    char buf[64];
    snprintf(buf, sizeof(buf), "%04d-%02d-%02d", d.year, d.month, d.day);
    if (mEtDatePtr != NULL) {
        mEtDatePtr->setText(buf);                       /* 回填输入框 */
    }
    char log[160];
    snprintf(log, sizeof(log), "已选：%s（弹窗内即时可见）", buf);
    setCalLog(log);
}

/* 翻月后刷新弹窗内状态行（把返回的 msg 也显示出来，演示「不静默失败」） */
static void refreshCal(const char *what) {
    zk::ui_v1::Calendar::Result r = s_cal.refresh();
    if (!r.ok()) {
        setStatus(r.msg.c_str());
        return;
    }
    zk::ui_v1::Calendar::Date d = s_cal.date();
    char buf[128];
    if (d.day > 0) {
        snprintf(buf, sizeof(buf), "%s：%d-%02d，选中 %d 日", what, d.year, d.month, d.day);
    } else {
        snprintf(buf, sizeof(buf), "%s：%d-%02d（未选日）", what, d.year, d.month);
    }
    setStatus(buf);
}

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    /* 本示例不需要定时器 */
};

static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD

    bindCells();

    zk::ui_v1::Calendar::Style st;                      /* 默认样式：蓝底白字选中 + 浅黄标记 */
    s_cal.setStyle(st);

    zk::ui_v1::Calendar::Result r =
        s_cal.attach(s_cells, mTvCalTitlePtr, mBtnCalPrevPtr, mBtnCalNextPtr);
    if (!r.ok()) {
        setStatus(r.msg.c_str());                       /* msg 是人话，直接显示 */
        return;
    }
    /* 容器原点（绝对坐标命中的前提）：
     *   platform 不导出 getParent()/getAbsolutePosition() -> 自己沿【已知指针】的祖先链相加。
     *   网格直接挂在 WinCal 上 -> 原点 = WinCal.getPosition()（= 162,40）。
     *   若容器还嵌在别的容器里，就用 setContainerOrigin(各层 getPosition() 之和)。
     *   （网格铺在 activity 根/全屏 window 上时原点是 (0,0)，这一段可以省） */
    {
        zk::ui_v1::Calendar::Result rc = s_cal.setContainer(mWinCalPtr);
        if (!rc.ok()) {
            setStatus(rc.msg.c_str());
            return;
        }
    }
    /* 铺满弹窗的「卡片按钮」只当白底用：关掉触摸，免得抢事件（命中由 activity 触摸事件反算） */
    /* 铺满弹窗的「卡片按钮」只当白底用（modal 里只有按钮的底色画得出来）：不接收触摸 + 穿透 */
    if (mBtnCalCardPtr != NULL) {
        mBtnCalCardPtr->setTouchable(false);
        mBtnCalCardPtr->setTouchPass(true);
    }
    s_cal.setOnDatePicked(onDatePicked, NULL);

    s_cal.setToday(TODAY_Y, TODAY_M, TODAY_D);          /* 「今天」= 2026-09-16（浅灰文字） */
    s_cal.setMarkedDays(s_marked, s_markedN);           /* 标记日：5/12/18/25（橙棕色文字） */
    s_cal.setDate(TODAY_Y, TODAY_M, 0);                 /* 定位到 2026-09，不选中 */

    if (mWinCalPtr != NULL) {
        mWinCalPtr->hideWnd();                          /* 弹窗默认隐藏，按钮打开 */
    }
    if (mEtDatePtr != NULL) {
        mEtDatePtr->setText("");
    }
    if (mTvPickedLogPtr != NULL) {
        mTvPickedLogPtr->setText(
            "用法：\n"
            "1) 点「打开日历」-> 弹出 modal 日历（42 个 textview 网格）\n"
            "2) 点日号 -> 组件 cellAt()/dayAt() 反算命中 -> pickDay() -> 回调回填输入框\n"
            "3) < > 翻月（prevMonth/nextMonth/setMonth，不触发回调）\n"
            "4) OK 关窗；点「跳到今天」演示 setToday + setMarkedDays\n"
            "高亮 = 文字色：深蓝加粗 = 选中日；橙棕色 = 标记日；浅灰 = 今天\n"
            "（平台事实：textview 画不出底色，详见组件 README 第 5 节）");
    }
    setStatus("日历已就绪（2026-09，今天=16，标记 4 天）");
}

static void onUI_intent(const Intent *intentPtr) { (void)intentPtr; }

static void onUI_show() {}

static void onUI_hide() {}

static void onUI_quit() {
    s_cal.detach();
}

static void onProtocolDataUpdate(const SProtocolData &data) { (void)data; }

static bool onUI_Timer(int id) { (void)id; return true; }

/* ---- 触摸命中：组件不装监听，业务反算（这就是 README §2 推荐的那 6 行） ---- */
static bool onmainActivityTouchEvent(const MotionEvent &ev) {
    if (ev.mActionStatus != MotionEvent::E_ACTION_UP) {
        return false;
    }
    if (mWinCalPtr == NULL || !mWinCalPtr->isWndShow()) {
        return false;
    }
    const int day = s_cal.dayAt(ev.mX, ev.mY);          /* 屏幕绝对坐标；0 = 空格/未命中 */
    if (day > 0) {
        zk::ui_v1::Calendar::Result r = s_cal.pickDay(day);   /* 选中 + 触发回调 */
        if (!r.ok()) {
            setCalLog(r.msg.c_str());
        }
        s_cal.refresh();                                /* * 改选中必须 refresh */
    }
    return false;
}

/* ---- 卡片按钮：只是弹窗白底，不做任何事（回调必须存在，check_all 回调核对要求） ---- */
static bool onButtonClick_BtnCalCard(ZKButton *pButton) {
    (void)pButton;
    return false;
}

/* ---- 打开日历 ---- */
static bool onButtonClick_BtnOpenCal(ZKButton *pButton) {
    (void)pButton;
    if (mWinCalPtr != NULL) {
        mWinCalPtr->showWnd();
    }
    refreshCal("打开日历");
    return false;
}

/* ---- 上一月 / 下一月 ---- */
static bool onButtonClick_BtnCalPrev(ZKButton *pButton) {
    (void)pButton;
    s_cal.prevMonth();
    refreshCal("上一月");
    return false;
}

static bool onButtonClick_BtnCalNext(ZKButton *pButton) {
    (void)pButton;
    s_cal.nextMonth();
    refreshCal("下一月");
    return false;
}

/* ---- OK / 取消：关窗 ---- */
static bool onButtonClick_BtnCalOk(ZKButton *pButton) {
    (void)pButton;
    zk::ui_v1::Calendar::Date d = s_cal.date();
    if (mWinCalPtr != NULL) {
        mWinCalPtr->hideWnd();
    }
    char buf[128];
    snprintf(buf, sizeof(buf), "OK：已确认 %d-%02d-%02d（输入框已回填）", d.year, d.month, d.day);
    setStatus(buf);
    return false;
}

static bool onButtonClick_BtnCalCancel(ZKButton *pButton) {
    (void)pButton;
    if (mWinCalPtr != NULL) {
        mWinCalPtr->hideWnd();
    }
    setStatus("取消：未确认");
    return false;
}

/* ---- 输入框文本变化（本示例只在选中日号时由组件回调回填，这里不需要处理） ---- */
static void onEditTextChanged_EtDate(const std::string &text) {
    (void)text;
}

/* ---- 跳到今天：setToday + setMarkedDays ---- */
static bool onButtonClick_BtnToday(ZKButton *pButton) {
    (void)pButton;
    static const int marks[3] = { 3, 11, 20 };
    s_cal.setMonth(TODAY_Y, TODAY_M);                   /* 回到今天所在月（不触发回调） */
    s_cal.setToday(TODAY_Y, TODAY_M, TODAY_D);          /* 「今天」高亮 */
    s_cal.setMarkedDays(marks, 3);                      /* 换一批标记日 */
    if (mWinCalPtr != NULL) {
        mWinCalPtr->showWnd();                          /* 打开窗口才能看到效果 */
    }
    refreshCal("跳到今天");
    setCalLog("跳到今天：2026-09-16（标记 3/11/20）");
    return false;
}
