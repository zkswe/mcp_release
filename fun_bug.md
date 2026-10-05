# fun编译文件兼容

## logic.cc 定时器和log_trace找不到定义

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

## 编译处理

1. 多国语言tr文件没有编译json打包
2. 字体文件路径没有处理到/res/font目录，而是按照push的路径