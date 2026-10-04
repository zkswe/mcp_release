---
title: WiFi
---

引入头文件

```c++
#include "net/NetManager.h"
```

打开系统内置的WIFI设置界面

```c++
EASYUICONTEXT->openActivity("WifiSettingActivity");
```

## wifi操作接口说明

获取WifiManager对象

```c++
#include "net/NetManager.h"
WifiManager *pWM = NETMANAGER->getWifiManager();

// 可以定义个宏,方便以下接口调用
#define WIFIMANAGER NETMANAGER->getWifiManager()
```

检测机器是否支持wifi

```c++
WIFIMANAGER->isSupported();
```

检测wifi是否打开

```c++
WIFIMANAGER->isWifiEnable();
```

开关wifi

```c++
WIFIMANAGER->enableWifi(true);
```

扫描wifi

```c++
WIFIMANAGER->startScan();
```

连接wifi

```c++
WIFIMANAGER->connect(ssid, pw);
```

断开wifi连接

```c++
WIFIMANAGER->disconnect();
```

检测wifi是否已连接

```c++
WIFIMANAGER->isConnected();
```

获取已连接wifi的信息

```c++
WIFIMANAGER->getConnectionInfo();
```

注册、反注册wifi信息监听

```c++
void addWifiListener(IWifiListener *pListener);
void removeWifiListener(IWifiListener *pListener);
```

## 样例代码
见 [样例代码](./demo_download.html#demo_download) 里的 NetDemo 工程
