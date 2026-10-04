---
title: PWM操作
---

## 引入头文件

```c++
#include "utils/PWMHelper.h"
```

## 具体操作

```c++
#include "utils/PWMHelper.h"

static void testPwm() {
/**
 * 参数1：端口号
 * 参数2：频率
 * 参数3：占空比
 * 参数4：极性
 *
 * 默认是使能状态，变量析构会自动关闭pwm
 */
PWMHelper pwm(0, 2500, 50, 0);

usleep(50000);

// 设置频率
pwm.setFreq(2700);
// 设置占空比
pwm.setDuty(100);
usleep(50000);

// 关闭
pwm.setEnable(false);
usleep(50000);

// 打开
pwm.setEnable(true);
usleep(50000);
}
```
