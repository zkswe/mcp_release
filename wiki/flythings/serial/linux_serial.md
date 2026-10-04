---
title: Linux串口编程
---

> 本篇文档旨在让大家理解FlyThings项目串口部分的代码是如何从零到有的这个过程，从而更容易理解我们最终提供的串口部分代码流程。理解之后，您可以根据自己的需求任意修改源代码。

该产品基于Linux系统，所以我们可以完全沿用标准Linux编程来操作串口。

## 基本步骤
我将Linux串口编程分为以下5个步骤：打开串口、配置串口、读串口、写串口、关闭串口。

- 打开串口

```c++
int fd = open("/dev/ttyS0", O_RDWR | O_NOCTTY);
```

open是系统函数，负责打开某个节点 以上代码表示：以可读可写的方式，尝试打开/dev/ttyS0这个串口，如果打开成功，返回一个非负值，这个值表示串口描述符，若失败，返回一个负数，即错误码。/dev/ttyS0 可以理解为串口号，类似Windows系统上的COM1。

- 配置串口 成功打开串口后，还需要配置串口，设置波特率等参数。

```c++
int openUart() {
 int fd = open("/dev/ttyS0", O_RDWR | O_NOCTTY);
 struct termios oldtio = { 0 };
 struct termios newtio = { 0 };
 tcgetattr(fd, &oldtio);
 //设置波特率为115200
 newtio.c_cflag = B115200 | CS8 | CLOCAL | CREAD;
 newtio.c_iflag = 0; // IGNPAR | ICRNL
 newtio.c_oflag = 0;
 newtio.c_lflag = 0; // ICANON
 newtio.c_cc[VTIME] = 0;
 newtio.c_cc[VMIN] = 1;
 tcflush(fd, TCIOFLUSH);
 tcsetattr(fd, TCSANOW, &newtio);

 //设置为非阻塞模式，这个在读串口的时候会用到
 fcntl(fd, F_SETFL, O_NONBLOCK);
 return fd;
}
```

> 以上是本平台的默认串口配置，8个数据位，1个停止位，无校验。非特殊需求请勿修改，受限于硬件与驱动，如果修改其为其他配置，可能会无效。

- 读串口

```c++
unsigned char buffer[1024] = {0};
int ret = read(fd, buffer, sizeof(buffer));
```

read是系统函数，它提供了读串口的功能，该函数需要三个参数：
- 第一个参数 是串口描述符，即打开串口步骤中open函数的返回值。
- 第二个参数 是缓冲区指针，用于保存读取的串口数据。
- 第三个参数 是缓冲区长度，也表示本次最多能读取多少个字节。
调用该函数，如果返回值大于0，表示有正确收到串口数据，且返回值等于读取到数据量的字节数。如果返回值小于或等于0，表示有错误或者暂时没读到数据。

- 发送串口

```c++
unsigned char buffer[4] = {0};
buffer[0] = 0x01;
buffer[1] = 0x02;
buffer[2] = 0x03;
buffer[3] = 0x04;
int ret = write(fd, buffer, sizeof(buffer));
```

write是系统函数，它提供了发送串口的功能，该函数需要三个参数：
- 第一个参数 是串口描述符，即打开串口步骤中open函数的返回值。
- 第二个参数 是待发送缓冲区指针。
- 第三个参数 是待发送缓冲区长度
调用该函数, 如果返回值大于0， 且返回值等于传递的第三个参数，表示发送成功。如果返回值小于或等于0，表示异常。

> read函数只是顺序读取串口收到的数据流，但不能保证一次就读取完整的数据。

- 关闭串口

```c++
close(fd);
```

## 综合使用
以下是一个简单的Linux串口编程的完整例子：

```c++
#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>

int main(int argc, char** argv) {
 int fd = open("/dev/ttyS0", O_RDWR | O_NOCTTY);
 if (fd < 0) {
 return -1;
 }

 struct termios oldtio = { 0 };
 struct termios newtio = { 0 };
 tcgetattr(fd, &oldtio);
 newtio.c_cflag = B115200 | CS8 | CLOCAL | CREAD;
 newtio.c_iflag = 0;
 newtio.c_oflag = 0;
 newtio.c_lflag = 0;
 newtio.c_cc[VTIME] = 0;
 newtio.c_cc[VMIN] = 1;
 tcflush(fd, TCIOFLUSH);
 tcsetattr(fd, TCSANOW, &newtio);
 fcntl(fd, F_SETFL, O_NONBLOCK);

 while (true) {
 unsigned char buffer[1024] = {0};
 int ret = read(fd, buffer, sizeof(buffer));
 if (ret > 0) {
 for (int i = 0; i < ret; ++i) {
 LOGD("收到%02x", buffer[i]);
 }
 int n = write(fd, buffer, ret);
 if (n != ret) {
 LOGD("发送失败");
 }
 if (buffer[0] == 0xFF) {
 break;
 }
 } else {
 usleep(1000 * 50);
 }
 }
 close(fd);
 return 0;
}
```

## 如何在软件上保证串口稳定通信

- 制定通信协议，包括帧头、帧尾、帧内容、校验等部分
- 多次调用read函数，将前后数据拼接起来，再按协议校验
- 使用多线程，将串口处理放在子线程中

## 总结
FlyThings提供了一份通用代码，它解决了如下问题：
- 串口的打开、关闭、读写操作
- 协议的拼接处理
- 提供统一的数据回调接口
这部分的源码是完全开源的，可以在项目的uart文件夹下找到。
