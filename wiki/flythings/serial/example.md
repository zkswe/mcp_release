---
title: 通讯案例实战
---

通过前面章节[通讯框架讲解](./serial_framework.html)，串口通讯主要有以下4点内容：
- 接收数据
- 解析数据
- 展示数据
- 发送数据

## 案例一

完整代码见[样例代码](./demo_download.html#demo_download)里控件样例的UartDemo工程。实现效果是通过串口发送指令来控制显示屏上的仪表指针旋转。

我们只需要修改3处地方就可以实现：

1. 新增自己的协议指令CMDID_ANGLE对应的值为0x0001：

ProtocolData.h:
```c++
#define CMDID_POWER 0x0
#define CMDID_ANGLE 0x1 // 新增ID

typedef struct {
 BYTE power;
 BYTE angle; // 新增变量，用于保存指针角度值
} SProtocolData;
```

2. 在procParse中处理对应的CmdID值：

```c++
static void procParse(const BYTE *pData, UINT len) {
 switch (MAKEWORD(pData[3], pData[2])) {
 case CMDID_POWER:
 sProtocolData.power = pData[5];
 break;
 case CMDID_ANGLE:
 sProtocolData.angle = pData[5];
 break;
 }
 notifyProtocolDataUpdate(sProtocolData);
}
```

3. 在logic/mainLogic.cc的数据回调接口中设置仪表指针：

```c++
static void onProtocolDataUpdate(const SProtocolData &data) {
 mPointer1Ptr->setTargetAngle(data.angle);
}
```

通过MCU向屏发送指令就可以看到仪表指针的旋转了。协议数据如下：

```
帧头     CmdID       数据长度 角度值
0xFF 0x55 0x00 0x01 0x01    angle
```

程序里也开启了一个定时器，2s模拟一次数据发送：

```c++
static bool onUI_Timer(int id) {
 BYTE data = rand() % 200;
 sendProtocol(CMDID_ANGLE, &data, 1);
 return true;
}
```
