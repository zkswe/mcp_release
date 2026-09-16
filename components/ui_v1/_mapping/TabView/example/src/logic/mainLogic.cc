#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD
#include "uart/ProtocolSender.h"
#include <cstdio>
#include "zk/zk_tabview.h"

/* ==========================================================================
 * components/ui_v1/TabView —— 最小可跑示例（Z21 1024x600 真机验收）
 *
 * 这个文件只做三件事：
 *   (1) 把 ui json 里的 pagewindow + 两个页签按钮 + 下划线 textview 交给 TabView 组件；
 *   (2) 注册 onPageChanged(page) 回调（滑动 / 点页签 两条路径同源）；
 *   (3) 演示「页内业务控件照常可点」（两个 +1 按钮）——证明翻页手势没吃掉点击。
 * 组件实现：src/zk/zk_tabview.{h,cpp}（从 components/ui_v1/TabView/ 拷来，原样未改）
 * ========================================================================== */

static zk::ui_v1::TabView s_tab;          /* 页签容器组件 */
static ZKButton *s_tabs[2] = { 0, 0 };    /* 页签按钮（顺序 = 页序） */
static int s_count[2] = { 0, 0 };         /* 两个页内计数器的值（业务状态） */

/* ---- 页切换回调：组件保证「实际生效页」才回调（幂等，不会同一页回调两次） ---- */
static void onPageChanged(int page, void *user) {
    (void)user;
    char buf[96];
    snprintf(buf, sizeof(buf), "onPageChanged: page=%d  (当前页=%d %s)",
             page, s_tab.current(), (page == s_tab.current()) ? "OK" : "MISMATCH");
    if (mTvLogPtr != NULL) {
        mTvLogPtr->setText(buf);
    }
}

static void showCount(int idx) {
    char buf[32];
    snprintf(buf, sizeof(buf), "%d", s_count[idx]);
    if (idx == 0 && mTvCount0Ptr != NULL) {
        mTvCount0Ptr->setText(buf);
    } else if (idx == 1 && mTvCount1Ptr != NULL) {
        mTvCount1Ptr->setText(buf);
    }
}

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    /* 本示例不需要周期任务；保留空表（平台要求这个符号必须存在） */
};

static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD

    s_tabs[0] = mBtnTab0Ptr;
    s_tabs[1] = mBtnTab1Ptr;

    s_tab.setOnPageChanged(onPageChanged, NULL);
    zk::ui_v1::TabView::Result r = s_tab.attach(mPwPagesPtr, s_tabs, 2, mTvTabMarkPtr);
    if (!r.ok() && mTvLogPtr != NULL) {
        mTvLogPtr->setText(r.msg.c_str());        /* 组件不静默失败：错误人话直接上屏 */
    }
    s_tab.select(0);                              /* 首帧高亮归位（幂等） */

    showCount(0);
    showCount(1);
}

static void onUI_intent(const Intent *intentPtr) { (void)intentPtr; }

static void onUI_show() {
    /* 切回本页时 painter/文字都不会自动刷；这里只需要把页签视觉再对一次（幂等） */
    s_tab.sync();
}

static void onUI_hide() {}

static void onUI_quit() {
    s_tab.detach();                               /* 摘监听，避免回调打到已销毁控件 */
}

static void onProtocolDataUpdate(const SProtocolData &data) { (void)data; }

static bool onUI_Timer(int id) { (void)id; return true; }

static bool onmainActivityTouchEvent(const MotionEvent &ev) { (void)ev; return false; }

/* ---- 点页签按钮 -> 编程切页（组件内部只用 getCurrentPage() 一个口径） ---- */
static bool onButtonClick_BtnTab0(ZKButton *pButton) { (void)pButton; s_tab.select(0); return false; }
static bool onButtonClick_BtnTab1(ZKButton *pButton) { (void)pButton; s_tab.select(1); return false; }

/* ---- 页内业务控件：证明翻页手势不吃点击 ---- */
static bool onButtonClick_BtnCount0(ZKButton *pButton) { (void)pButton; ++s_count[0]; showCount(0); return false; }
static bool onButtonClick_BtnCount1(ZKButton *pButton) { (void)pButton; ++s_count[1]; showCount(1); return false; }
