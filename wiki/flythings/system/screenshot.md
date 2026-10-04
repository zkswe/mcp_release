---
title: 截屏
---

产品开发完毕后，编写使用说明书时，可能需要运行界面的截图，可参考如下代码截屏。

```c++
#include "utils/ScreenHelper.h"

static bool onButtonClick_Button1(ZKButton *pButton) {
 ScreenHelper::screenShot("/mnt/extsd/screenshot.bmp");
 return false;
}
```

如果平台没有这个接口，也可用以下方式截图：
下载[screenshot.h](https://docs.flythings.cn/src/screenshot.h)源文件，保存到项目jni目录下。

```c++
#include "screenshot.h"

static bool onButtonClick_Button1(ZKButton *pButton) {
 //截取当前屏幕，保存为bmp图片，保存到TF卡目录下
 Screenshot::AutoSave();
 return false;
}
```

默认图片保存到TF卡，所以尽量插上TF卡再截屏。
