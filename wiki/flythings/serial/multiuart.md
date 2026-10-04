---
title: 多串口配置
---

常规项目默认只支持一个串口，如果您要使用双串口，甚至多串口，请下载[DoubleUartDemo样例](./demo_download.html#demo_download)，该样例在常规项目中修改了串口部分代码，以支持多串口。

## 变更

变更部分见如下说明。

- uart部分代码经过修改，所以项目属性里的串口配置失效。
- 串口号及波特率请参照 jni/uart/UartContext.cpp 文件中的 init()函数修改。

```c++
void UartContext::init() {
 uart0 = new UartContext(UART_TTYS0);
 uart0->openUart("/dev/ttyS0", B9600);

 uart1 = new UartContext(UART_TTYS1);
 uart1->openUart("/dev/ttyS1", B9600);
}
```

- 发送数据到指定串口

```c++
unsigned char buf[2] = {1, 1};
sendProtocolTo(UART_TTYS1, 1, buf, 2); //发送到TTYS1串口

unsigned char buf[2] = {0};
sendProtocolTo(UART_TTYS0, 1, buf, 2);//发送到TTYS0串口
```

- 接收串口数据的方式与常规项目相同 如果需要区分数据来自哪一个串口，建议在SProtocolData 结构体中添加一个字段标识该帧来自哪一个串口。

修改 uart/ProtocolData.h:

```c++
typedef struct {
 BYTE power;
 int uart_from; //来自哪一个串口
} SProtocolData;
```

修改 uart/ProtocolParser.cpp:

```c++
static void procParse(int uart, const BYTE *pData, UINT len) {
 switch (MAKEWORD(pData[3], pData[2])) {
 case CMDID_POWER:
 sProtocolData.power = pData[5];
 break;
 }
 sProtocolData.uart_from = uart;
 notifyProtocolDataUpdate(sProtocolData);
}
```

然后在Logic.cc中，可以使用uart_from字段判断该数据来自哪一个串口。

```c++
static void onProtocolDataUpdate(const SProtocolData &data) {
 LOGD("onProtocol %d", data.uart_from);
 char buf[128] = {0};
 snprintf(buf, sizeof(buf), "收到串口 %d的数据", data.uart_from);
 mTextview1Ptr->setText(buf);
}
```

## 样例代码
完整代码见[样例代码](./demo_download.html#demo_download) 里的 DoubleUartDemo 工程
