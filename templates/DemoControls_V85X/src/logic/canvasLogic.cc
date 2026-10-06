#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS

#endif // FUN_BUILD

/**
 * 注册定时器
 * 填充数组用于注册定时器
 * 注意：id不能重复
 */
static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
  //{0,  6000}, //定时器id=0, 时间间隔6秒
  //{1,  1000},
};

#include "base/log.h"

/**
 * @brief 当界面构造时触发
 */
static void onUI_init() {
  #ifdef FUN_BUILD
  INIT_UI_TIMERS
  #endif // FUN_BUILD
    if (mPaAPtr) {
        mPaAPtr->setSourceColor(0xFF4D4D);
        mPaAPtr->fillRect(24, 24, 180, 90);                 // 实心矩形
        mPaAPtr->setSourceColor(0x4DA6FF);
        mPaAPtr->drawRect(230, 24, 200, 90, 18);            // 圆角矩形描边
        mPaAPtr->setSourceColor(0x66E08A);
        mPaAPtr->fillArc(130, 250, 90, 90, 0, 270);         // 扇形：圆心 + 半径 + 起始/扫过角
        mPaAPtr->setSourceColor(0xFFD479);
        mPaAPtr->drawArc(330, 250, 90, 90, 0, 360);         // 整圆描边
        // 直线：ZKPainter 没有 drawLine()，单线用 drawLines(SZKPoint*, 2)（SZKPoint = float x,y）
        mPaAPtr->setSourceColor(0xFFFFFF);
        SZKPoint thinLine[2] = {{24.0f, 380.0f}, {430.0f, 380.0f}};
        mPaAPtr->drawLines(thinLine, 2);
        mPaAPtr->setLineWidth(8);
        mPaAPtr->setSourceColor(0xC08AFF);
        SZKPoint fatLine[2] = {{24.0f, 440.0f}, {430.0f, 440.0f}};
        mPaAPtr->drawLines(fatLine, 2);
    }

  LOGD_TRACE("");
}

/**
 * @brief 当切换到该界面时触发
 */
static void onUI_intent(const Intent *intent) {
  LOGD_TRACE("");
  if (intent != NULL) {
  }
}

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
 * @brief 当界面完全退出时触发
 */
static void onUI_quit() {
  LOGD_TRACE("");
}

/**
 * @brief 串口数据回调接口
 */
static void onProtocolDataUpdate(const SProtocolData &data) {
  LOGD_TRACE("");
}

/**
 * @brief 定时器回调函数, 不要在此函数中写耗时操作, 否则将影响UI刷新
 * @param id 当前所触发定时器的id, 与注册时的id相同
 * @return true  继续运行当前定时器
 *         false 停止运行当前定时器
 */
static bool onUI_Timer(int id) {
  LOGD_TRACE("on timer %d", id);
  switch (id) {

  default:
    break;
  }
  return true;
}


/**
 * @brief 有新的触摸事件时触发
 * @param ev 触摸事件
 * @return true 表示该触摸事件在此被拦截，系统不再将此触摸事件传递到控件上
 *         false 触摸事件将继续传递到控件上
 */
 static bool oncanvasActivityTouchEvent(const MotionEvent &ev) {
  switch (ev.mActionStatus) {
  case MotionEvent::E_ACTION_DOWN: // 触摸按下
    // LOGD_TRACE("时刻 = %ld 坐标  x = %d, y = %d", ev.mEventTime, ev.mX, ev.mY);
    break;
  case MotionEvent::E_ACTION_MOVE: // 触摸滑动
    break;
  case MotionEvent::E_ACTION_UP: // 触摸抬起
    break;
  default:
    break;
  }
  return false;
}
static bool onButtonClick_BtnBack(ZKButton* pButton) {
    EASYUICONTEXT->goBack();
    return true;
}


