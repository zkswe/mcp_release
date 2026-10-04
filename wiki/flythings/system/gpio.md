---
title: GPIO操作
---

## 引入头文件

```c++
#include "utils/GpioHelper.h"
```

## 操作函数

```c++
class GpioHelper {
public:
 /**
 * 将脚位设置为输入模式，并返回脚位的高低状态
 * @param pPin 脚位名
 * @return -1 操作失败
 *         1 高电平
 *         0 低电平
 */
 static int input(const char *pPin);
 /**
 * 将脚位设置为输出模式, 并指定输出高电平或者低电平
 * @param pPin 脚位名
 * @param val 1 高电平 0 低电平
 * @return -1 失败 0 成功
 */
 static int output(const char *pPin, int val);
};
```

各个平台的IO口定义请参见原始文档。H500S、T113、Z20、Z21及之后的平台支持自定义IO号输入，参数为GPIO_xxx字符串。

完整源码见[样例代码包](./demo_download.html#demo_download)中的GpioDemo项目
