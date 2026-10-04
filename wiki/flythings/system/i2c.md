---
title: I2C操作
---

## 引入头文件

```c++
#include "utils/I2CHelper.h"
```

## 具体操作

```c++
#include "utils/I2CHelper.h"

#define CFG_L 0x47
#define CFG_H 0x80
#define VER_L 0x41
#define VER_H 0x81

static void testI2C() {
 uint8_t tx[512], rx[512];
 memset(tx, 0, 512);
 memset(rx, 0, 512);

 /**
 * 定义变量
 * 参数1：i2c总线号
 * 参数2：从机地址，注意是7bit地址
 * 参数3：超时时间，最小10ms
 * 参数4：重试次数
 */
 I2CHelper i2c(0, 0x5e, 1000, 5);

 tx[0] = CFG_H;
 tx[1] = CFG_L;

 // 单工写
 if (!i2c.write(tx, 2)) {
 LOGD("i2c tx cfg error!\n");
 }

 // 单工读
 if (!i2c.read(rx, 1)) {
 LOGD("i2c rx cfg error!\n");
 }

 // 半双工传输
 if (!i2c.transfer(tx, 2, rx, 1)) {
 LOGD("i2c transfer cfg error!\n");
 }
}
```

## I2C操作—EEPROM读写案例

以AD24C32存储器为例，I2C对象构造时传入从机地址。

```c++
static I2CHelper i2c(1, 0x50, 1000, 5);
```

读操作和写操作需要关注从设备的通信协议和电器特性。完整代码请参见原始文档。

测试代码写入"www.zkswe.com"后读出，日志输出显示读取结果与写入数据一致。
