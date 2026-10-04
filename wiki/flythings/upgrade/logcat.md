---
title: 查看日志
---

## 添加日志

- 所需头文件

```c++
#include "utils/Log.h"
```

FlyThings 的打印统一调用 LOGD 或 LOGE 宏输出，使用方法与C语言的printf相同。

```c++
static bool onButtonClick_Button1(ZKButton *pButton) {
 LOGD("onButtonClick_Button1\n");
 return true;
}
```

## 查看应用程序打印日志

### 命令行的方式查看（推荐）

- 找到软件的顶部菜单，依次打开菜单 调试配置->打开系统命令行
- USB连接：直接输入 adb shell logcat -v time
- 网络连接（WIFI/以太网）：先输入 adb connect IP地址，再输入 adb shell logcat -v time
- 按 Ctrl + C 停止日志显示
- 清空缓存日志：adb logcat -c

### UI界面的方式查看 (弃用)

## 查看应用程序标准输出日志

```bash
adb shell setprop ctl.stop zkswe
zkgui
```

## 查看系统日志

```bash
adb shell cat /proc/kmsg
```
