---
title: 重启系统
---

可通过如下代码，主动让系统机器重启。

- 需要的头文件

```c++
#include<unistd.h>
#include<sys/reboot.h>
```

- 代码

```c++
//同步数据，将缓存数据保存，以防数据丢失
sync();
reboot(RB_AUTOBOOT);
```
