---
title: TF卡/U盘
---

当插入TF卡后，系统会自动将其挂载到 /mnt/extsd目录。
当插入U盘后，系统会自动将其挂载到 /mnt/usb1或者/mnt/usb2或者/mnt/usb3目录（根据使用的USB口变化）。

## 监听挂载事件
首先打开项目下的Manifest.xml，并添加base-utility包（要求9.0.0及更高版本）。

```c++
#include <base/base.h>
```

```c++
static void onMyMountEvent(int status, const std::string& mount_point) {
 switch (status) {
 case MountMonitor::E_MOUNT_STATUS_MOUNTED:
 LOGD_TRACE("已挂载 %s 状态 %d ", mount_point.c_str(), status);
 break;
 case MountMonitor::E_MOUNT_STATUS_REMOVE:
 LOGD_TRACE("移除挂载 %s 状态 %d ", mount_point.c_str(), status);
 break;
 default:
 LOGD_TRACE("其他状态 %d", status);
 break;
 }
}

static void onUI_init() {
 #if 1
 /// 监听/mnt/extsd 这个路径的挂载事件，也就相当于监听TF卡
 static base::MountNotification mn_extsd("/mnt/extsd", onMyMountEvent);
 /// 监听各个USB的挂载事件
 static base::MountNotification mn_usb1("/mnt/usb1", onMyMountEvent);
 static base::MountNotification mn_usb2("/mnt/usb2", onMyMountEvent);
 static base::MountNotification mn_usb3("/mnt/usb3", onMyMountEvent);
 #else
 //如果第一个参数赋值空字符串，表示监听所有的USB和TF卡挂载事件
 static base::MountNotification mn_any("", onMyMountEvent);
 #endif
}
```

## 检查挂载状态

```c++
#include <os/MountMonitor.h>

if (MOUNTMONITOR->isMounted("/mnt/extsd")) {
 LOGD_TRACE("TF卡已挂载");
} else {
 LOGD_TRACE("TF卡未挂载");
}

if (MOUNTMONITOR->isMounted("/mnt/usb1")) {
 LOGD_TRACE("U盘usb1 已挂载");
} else {
 LOGD_TRACE("U盘usb1 未挂载");
}
```

## 文件路径
在系统内访问TF卡或者U盘内文件的路径 = 挂载目录 + 自身文件目录。
例如：如果你的TF卡根目录内有一个 test.txt 文件，在设备上，这个文件的绝对路径就是 /mnt/extsd/test.txt。

## 读写TF卡/U盘注意事项
- 读写TF卡或者U盘文件前，应该先检查挂载状态，确保已挂载后再读写。
- 在数据写入完成后，建议显式调用同步函数sync()，强制将文件系统缓冲区内容持久化到物理存储介质。
- 频繁调用同步函数会降低I/O性能，建议根据业务需求权衡。

## /mnt 目录
设备内，/mnt下的各个目录，通常与挂载的存储设备有关。系统默认会固定创建/mnt/extsd、/mnt/usb1等目录。
不存在TF卡、U盘时，该目录下的文件总是保存在内存中（断电数据会消失），并且共用系统内存。
/tmp目录也具有相同的特性。
