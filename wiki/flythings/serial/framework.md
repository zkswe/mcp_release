---
title: 通讯框架讲解
---

## 通讯框架讲解
这一章节重点讲解通讯框架的实现原理。软件APP部分分为两层：

- **uart协议解析和封装的串口HAL层**
  - UartContext：串口的实体控制层，提供串口的开关，发送，接收接口
  - ProtocolData：定义通讯的数据结构体，用于保存通讯协议转化出来的实际变量
  - ProtocolSender：完成数据发送的封装
  - ProtocolParser：完成数据的协议解析部分，然后将解析好的数据放到ProtocolData的数据结构中；同时管理了应用监听串口数据变化的回调接口

- **APP应用接口层**
  - 通过ProtocolParser提供的接口注册串口数据接收监听获取串口更新出来的ProtocolData
  - 通过ProtocolSender提供的接口往MCU发送指令信息

## 协议接收部分使用和修改方法

### 通讯协议格式修改

常见的通讯协议例子：
```
协议头（2字节） 命令（2字节） 数据长度（1字节） 数据（N） 校验（1字节 可选）
0xFF55          Cmd           len               data      checksum
```

CommDef.h 文件中定义了同步帧头信息及最小数据包大小信息：

```c++
// 需要打印协议数据时，打开以下宏
//#define DEBUG_PRO_DATA

// 支持checksum校验，打开以下宏
//#define PRO_SUPPORT_CHECK_SUM

/* SynchFrame CmdID DataLen Data CheckSum (可选) */
/* 2Byte 2Byte 1Byte N Byte 1Byte */
#ifdef PRO_SUPPORT_CHECK_SUM
#define DATA_PACKAGE_MIN_LEN 6
#else
#define DATA_PACKAGE_MIN_LEN 5
#endif

// 同步帧头
#define CMD_HEAD1 0xFF
#define CMD_HEAD2 0x55
```

ProtocolParser.cpp 文件中的协议解析函数：

```c++
/**
 * 功能：解析协议
 * 参数：pData 协议数据，len 数据长度
 * 返回值：实际解析协议的长度
 */
int parseProtocol(const BYTE *pData, UINT len) {
 UINT remainLen = len;
 UINT dataLen;
 UINT frameLen;

 while (remainLen >= DATA_PACKAGE_MIN_LEN) {
 while ((remainLen >= 2) && ((pData[0] != CMD_HEAD1) || (pData[1] != CMD_HEAD2))) {
 pData++;
 remainLen--;
 continue;
 }

 if (remainLen < DATA_PACKAGE_MIN_LEN) {
 break;
 }

 dataLen = pData[4];
 frameLen = dataLen + DATA_PACKAGE_MIN_LEN;
 if (frameLen > remainLen) {
 break;
 }

#ifdef PRO_SUPPORT_CHECK_SUM
 if (getCheckSum(pData, frameLen - 1) == pData[frameLen - 1]) {
 procParse(pData, frameLen);
 } else {
 LOGE("CheckSum error!!!!!!\n");
 }
#else
 procParse(pData, frameLen);
#endif

 pData += frameLen;
 remainLen -= frameLen;
 }

 return len - remainLen;
}
```

### 通讯协议数据怎么和UI控件对接

procParse函数解析协议数据并更新到sProtocolData结构体：

```c++
void procParse(const BYTE *pData, UINT len) {
 switch (MAKEWORD(pData[2], pData[3])) {
 case CMDID_POWER:
 sProtocolData.power = pData[5];
 LOGD("power status:%d", sProtocolData.power);
 break;
 }
 notifyProtocolDataUpdate(sProtocolData);
}
```

### 数据结构

ProtocolData.h中定义数据结构：

```c++
typedef struct {
 BYTE power;
 // 可以在这里面添加协议的数据变量
} SProtocolData;
```

### UI更新

UI界面在Activity生成时就完成了串口数据更新监听注册：

```c++
static void onProtocolDataUpdate(const SProtocolData &data) {
 // 串口数据回调接口
 if (mProtocolData.power != data.power) {
 mProtocolData.power = data.power;
 }
 // ... 处理其他数据更新
}
```

## 串口数据发送

ProtocolSender.cpp 中sendProtocol方法负责协议封装发送：

```c++
bool sendProtocol(const UINT16 cmdID, const BYTE *pData, BYTE len) {
 BYTE dataBuf[256];
 dataBuf[0] = CMD_HEAD1;
 dataBuf[1] = CMD_HEAD2;
 dataBuf[2] = HIBYTE(cmdID);
 dataBuf[3] = LOBYTE(cmdID);
 dataBuf[4] = len;
 UINT frameLen = 5;
 for (int i = 0; i < len; ++i) {
 dataBuf[frameLen] = pData[i];
 frameLen++;
 }
#ifdef PRO_SUPPORT_CHECK_SUM
 dataBuf[frameLen] = getCheckSum(dataBuf, frameLen);
 frameLen++;
#endif
 return UARTCONTEXT->send(dataBuf, frameLen);
}
```

使用示例：

```c++
BYTE mode[] = { 0x01, 0x02, 0x03, 0x04 };
sendProtocol(0x01, mode, 4);
```
