---
title: Z210核心板使用指引
---

我们以核心板 + 底板为例，讲解基础的使用问题。

## 调试串口
调试串口是一组专用的串口，连接该串口，就是一个Shell终端。调试串口不能用作协议通信，协议通讯请使用普通串口。

### 使用PuTTY连接调试串口
- 先将核心板供电
- 准备一个USB转TTL的串口板
- 找到底板上的DEBUG_TX、DEBUG_RX、GND脚，连接到串口板上的RXD、TXD、GND
- 使用PuTTY软件，选择串口连接类型，波特率115200
- 输入命令 `logcat -v threadtime` 查看日志

## USB功能
底板上有一个Type-C的USB口，可以切换为ADB、U盘或WIFI功能（三选一）。

### 切换USB模式
- U盘模式：`cat /sys/devices/soc0/soc/soc:usbotg/usb_host`
- ADB模式：`cat /sys/devices/soc0/soc/soc:usbotg/usb_device`

### 代码中切换

```c++
// 切换到U盘模式
system("cat /sys/devices/soc0/soc/soc:usbotg/usb_host");
// 切换到adb模式
system("cat /sys/devices/soc0/soc/soc:usbotg/usb_device");
```

## 下载调试
支持USB下载调试和网络调试两种方式。详见[ADB下载调试](./adb_debug.html)。

## 软件升级
支持USB线升级、网络升级、插U盘升级等方式。详见[固化升级](./make_image.html)。

## 通讯串口
Z210核心板的功能串口为/dev/ttyS2，对应引脚TXD2和RXD2。

## ADC使用

```c++
#include "utils/AdcHelper.h"
AdcHelper::setChannel(0);
AdcHelper::setEnable(true);
int val = AdcHelper::getVal();
```

## 样例下载
z210出厂样例代码下载：[点此下载](/src/Z210_SampleDemo.zip)
