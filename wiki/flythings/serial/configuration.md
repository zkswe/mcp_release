---
title: 如何配置串口
---

## 串口号的选择

软件串口号与硬件串口号对应关系：

### Z11系列平台
| 软件串口号 | 硬件串口号 |
|-----------|-----------|
| ttyS0     | UART1     |
| ttyS1     | UART2     |

### Z6系列平台
| 软件串口号 | 硬件串口号 |
|-----------|-----------|
| ttyS0     | UART0     |
| ttyS1     | UART1     |
| ttyS2     | UART2     |

### A33、H500S系列平台
| 软件串口号 | 硬件串口号 |
|-----------|-----------|
| ttyS1     | UART1     |
| ttyS2     | UART2     |
| ttyS3     | UART3     |

### Z20系列平台
| 软件串口号 | 硬件串口号 |
|-----------|-----------|
| ttyS1     | UART1     |
| ttyS2     | FUART     |
| ttyS3     | UART2     |

### Z21系列平台
| 软件串口号 | 硬件串口号 |
|-----------|-----------|
| ttyS1     | UART1     |
| ttyS2     | UART2     |
| ttyS3     | UART3     |

## 串口波特率配置

- 新建工程时配置波特率
- 右键工程, 选择 Properties 选项修改波特率

## 串口打开与关闭

在 jni/Main.cpp 中：

```c++
void onEasyUIInit(EasyUIContext *pContext) {
 LOGD("onInit\n");
 UARTCONTEXT->openUart(CONFIGMANAGER->getUartName().c_str(), CONFIGMANAGER->getUartBaudRate());
}

void onEasyUIDeinit(EasyUIContext *pContext) {
 LOGD("onDestroy\n");
 UARTCONTEXT->closeUart();
}
```
