---
title: ADB 下载调试
---

FlyThings 可以通过 USB数据线或者网络快速下载程序到机器中。

## 设备的连接方式

- WIFI或以太网功能：建议使用网络连接方式
- 不支持WIFI或以太网：建议通过USB数据线连接

### 使用USB数据线连接方式
如果电脑能将设备识别为Android设备，表示连接正常。如果不能正常连接，可尝试[下载更新驱动](./install_adb_driver.html)。
注意：A口(大口)USB由于没有ID脚，默认是U盘模式，可通过[开发者选项](./internal_app.html)调试开关切换。

### 网络连接方式
- 如果选用WIFI，先进入设备的[WIFI设置界面](./wifi.html)，将机器连接到与电脑相同的网络。查看设备的IP地址后，在IDE中配置。
- 如果选用以太网，先进入机器的[以太网设置界面](./eth.html)，查看设备的IP地址。

## 下载调试
在项目资源管理器中，选中项目名，右键，在弹出菜单中选择 下载调试。也可以使用快捷键 Ctrl + Alt + R。

## 通过ADB固化应用程序

```bash
adb push ./update.img /tmp/update.img
adb shell setprop sys.zkupgrade.flag 255
adb shell setprop sys.zkupgrade.dir /tmp
adb shell setprop ctl.restart zkswe
```

## 注意事项
- 尽量插一张TF卡到机器中，确保不会因为可用内存过小出现各种问题。
- 通过下载调试方式运行程序，并不能将程序固化到机器中。

## 在命令行下使用ADB
在IDE中，调试配置 -> 打开系统命令行，可以执行ADB命令。

## 特殊处理
如果下载时提示Read-only file system，可将ADB下载目录更改为/tmp，或重新挂载分区为可读可写。
