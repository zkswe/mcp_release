---
title: 系统时间
---

- 所需头文件

```c++
#include "utils/TimeHelper.h"
```

tm 结构体各字段解释

```c++
struct tm {
 int tm_sec;   /* 秒–取值区间为[0,59] */
 int tm_min;   /* 分 - 取值区间为[0,59] */
 int tm_hour;  /* 时 - 取值区间为[0,23] */
 int tm_mday;  /* 一个月中的日期 - 取值区间为[1,31] */
 int tm_mon;   /* 月份（从一月开始，0代表一月） - 取值区间为[0,11] */
 int tm_year;  /* 年份，其值从1900开始 */
 ...
}
```

- 获取当前日期

```c++
struct tm *t = TimeHelper::getDateTime();
```

- 显示时间代码样例

```c++
static void updateUI_time() {
 char timeStr[20];
 static bool bflash = false;
 struct tm *t = TimeHelper::getDateTime();

 sprintf(timeStr, "%02d:%02d:%02d", t->tm_hour, t->tm_min, t->tm_sec);
 mTextTimePtr->setText(timeStr);

 sprintf(timeStr, "%d年%02d月%02d日", 1900 + t->tm_year, t->tm_mon + 1, t->tm_mday);
 mTextDatePtr->setText(timeStr);

 static const char *day[] = { "日", "一", "二", "三", "四", "五", "六" };
 sprintf(timeStr, "星期%s", day[t->tm_wday]);
 mTextWeekPtr->setText(timeStr);
}
```

- 设置时间代码样例

```c++
// 利用tm结构体设置时间
static void setSystemTime() {
 struct tm t;
 t.tm_year = 2017 - 1900;
 t.tm_mon = 9 - 1;
 t.tm_mday = 13;
 t.tm_hour = 16;
 t.tm_min = 0;
 t.tm_sec = 0;

 TimeHelper::setDateTime(&t);
}

// 或者用字符串设置时间
TimeHelper::setDateTime("2017-09-13 16:00:00");
```

完整源码见[样例代码包](./demo_download.html#demo_download)中的DateDemo工程
