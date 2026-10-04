---
title: SPI操作
---

## 引入头文件

```c++
#include "utils/SpiHelper.h"
```

## 具体操作

```c++
#include "utils/SpiHelper.h"

static void testSpi() {
 uint8_t tx[512], rx[512];

 /**
 * 定义变量
 * 参数1：spi总线号
 * 参数2：模式，可选值：SPI_MODE_0、SPI_MODE_1、SPI_MODE_2、SPI_MODE_3
 * 参数3：spi时钟频率，这里设置了50M
 * 参数4：一个字有多少位，默认值：8
 * 参数5：位顺序，true：低位在前，false：高位在前；默认值：false
 */
 SpiHelper spi(1, SPI_MODE_0, 50*1000*1000, 8, false);

 memset(tx, 0, 512);
 memset(rx, 0, 512);
 tx[0] = 0x4B;

 // 单工写
 if (!spi.write(tx, 5)) {
 LOGD("spi tx error!\n");
 }

 // 单工读
 if (!spi.read(rx, 8)) {
 LOGD("spi rx error!\n");
 }

 // 半双工传输
 if (!spi.halfduplexTransfer(tx, 5, rx, 8)) {
 LOGD("spi halfduplexTransfer error!\n");
 }

 for (int i = 0; i < 8; i++) {
 LOGD("spi[%d]=0x%x\n", i, rx[i]);
 }
}
```
