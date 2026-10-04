---
title: 远程升级
---

目前系统没有直接进行远程升级的接口。但是我们可以了解TF卡检测升级的机制后，再添加上自己的代码，即可达到远程升级的目的。

## TF卡检测升级流程
当系统启动或者插入TF卡的时候，如果TF卡正常挂载，系统会检测TF卡根目录下是否存在 update.img 文件、以及是否存在 boot_logo.JPG 文件。如果存在，进一步校验文件是否符合要求，如果通过校验，然后弹出升级提示界面。

## 实现步骤

- 通过HTTP协议下载升级镜像 update.img 或 boot_logo.JPG，保存到TF卡目录下。
- 调用升级检测函数：

```c++
#include "os/UpgradeMonitor.h"

//主动检测 /mnt/extsd目录下是否有正确的update.img文件
UpgradeMonitor::getInstance()->checkUpgradeFile("/mnt/extsd");
```

## 下载文件后自动更新
如果希望下载升级文件后，强制更新，只需要参考[自动升级](./autoupgrade.html)文档，用代码创建 zkautoupgrade文件即可。

## 避免反复升级
下载镜像文件时，将它保存到非 /mnt/extsd/ 目录，例如：/mnt/extsd/temp/，并同步修改调用检测函数的参数。

完整样例请参考[netupdate.zip](../src/netupdate.zip)。
