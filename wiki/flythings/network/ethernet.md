---
title: 以太网
---

引入头文件

```c++
#include "net/NetManager.h"
```

打开系统内置的以太网设置界面

```c++
EASYUICONTEXT->openActivity("EthernetSettingActivity");
```

## 以太网操作接口说明

获取EthernetManager对象

```c++
EthernetManager *pWM = NETMANAGER->getEthernetManager();

// 可以定义个宏,方便以下接口调用
#define ETHMANAGER NETMANAGER->getEthernetManager()
```

检测机器是否支持以太网

```c++
ETHMANAGER->isSupported();
```

检测以太网是否已连接

```c++
ETHMANAGER->isConnected();
```

获取已连接的IP

```c++
if (ETHMANAGER->isConnected()) {
 ETHMANAGER->getIp();
}
```

获取物理地址

```c++
ETHMANAGER->getMacAddr();
```

注册、反注册以太网状态监听

```c++
void addEthernetConnStateListener(IEthernetConnStateListener *pListener);
void removeEthernetConnStateListener(IEthernetConnStateListener *pListener);
```

## 样例代码
见 [样例代码](./demo_download.html#demo_download) 里的 NetDemo 工程
