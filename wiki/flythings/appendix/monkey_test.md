---
title: 自动化测试
---

## 下载使用

- [下载自动化测试包](/src/input.zip)
- 与测试设备进行连接：adb connect ip
- 将input文件放到设备的/tmp/目录下：adb push ..\input\libs\armeabi\input /tmp/
- 修改权限：adb shell chmod 777 /tmp/input
- 查看支持测试的事件操作说明：adb shell /tmp/input

## 随机测试
随机进行点击、滑动等操作，其中1024 600是指操作执行的区间（屏幕分辨率），测试程序挂掉后会自动停止。

```bash
adb shell /tmp/input /dev/input/event0 monkey 1024 600
```

## 操作录制与执行

- 操作录制

```bash
adb shell /tmp/input /dev/input/event0 record /tmp/events
```

- 操作执行（-r 5是指执行5次，-1表示无限次）

```bash
adb shell /tmp/input /dev/input/event0 play /tmp/events -r 5
```

## 自动化测试脚本说明

```bash
..\input\shell-runer.bat /dev/input/event0 monkey 1024 600
```
