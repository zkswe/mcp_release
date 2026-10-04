---
title: ADC操作
---

## 引入头文件

```c++
#include "utils/AdcHelper.h"
```

## 具体操作

```c++
#include "utils/AdcHelper.h"

static void testAdc() {

 //设置adc通道,默认是0,可在0-5之间设置
 AdcHelper::setChannel(0);
 /**
 * 设置adc使能状态
 * @param true 使能 false 禁止
 * 默认是使能状态
 */
 AdcHelper::setEnable(true);

 for (int i = 0; i < 10; i++) {
 // 读取adc值
 int val = AdcHelper::getVal();
 LOGD("adc val = %d\n", val);
 }
}
```
