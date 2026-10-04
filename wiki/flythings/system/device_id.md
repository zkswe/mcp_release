---
title: 设备唯一ID码
---

## 如何读取

- 所需头文件

```c++
#include "security/SecurityManager.h"
```

- 读取设备ID 适用Z6、Z11、A33平台：

```c++
// 设备 id 共8个字节
static unsigned char devID[8];
// 成功返回 true，失败返回 false
static bool ret = SECURITYMANAGER->getDevID(devID);

for (int i = 0; i < 8; ++i) {
 LOGD("%x ", devID[i]);
}
```

- 适用H500S、Z20、Z21、T113及后续其他新平台：

```c++
// 设备 id 最多16个字节
static unsigned char devID[16];
// 返回 devID长度
static int ret = SECURITYMANAGER->getDevID(devID);

for (int i = 0; i < ret; ++i) {
 LOGD("%x ", devID[i]);
}
```
