---
id: hardware-peripheral-api-zkhardware
title: 硬件外设 API 权威页（GPIO / I2C / SPI / PWM / ADC / 背光显示 / 蜂鸣器 / 过零继电器）—— zkhardware 包头口径 + 平台差异
category: hardware
status: review
confidence: offline
verified_at: 2026-10-03
stale_days: 180
origin: total
source: 2026-10-03 收录：逐个读 zkhardware 包头 include/utils/*.h + include/hw/HardwareManager.h（本机 registry 里 z20 / z21 / v85x / z235x 四份对比，含逐字节哈希与体积）
needs_evidence: true
platforms: [Z20, Z21, V85X, Z235X]
tags: [GPIO, I2C, SPI, PWM, ADC, 背光, 蜂鸣器, 过零, 继电器, 外设, 硬件接口, 引脚, zkhardware, 外设API]
evidence: []
---
# 硬件外设 API 权威页（GPIO / I2C / SPI / PWM / ADC / 背光显示 / 蜂鸣器 / 过零继电器）

> 检索导引：问「GPIO 怎么读写 / I2C 怎么用 / SPI 怎么配置 / PWM 怎么输出 / ADC 怎么读 /
> 背光亮度怎么调 / 蜂鸣器怎么响 / 过零继电器怎么控 / 外设 API 在哪 / 引脚名怎么写 /
> `B_02` 是什么 / `HARDWAREMANAGER` / `GpioHelper` / `AdcHelper` / `I2CHelper` / `SpiHelper` /
> `PWMHelper` / `BrightnessHelper`」→ 本文（**跨平台外设 API 的唯一权威页**）。
> 真机实测读数与硬约束不在本文重复 → `packages/zkhardware/README.md`（§2 速查 / §4 实测 / §5 坑）
> 与 `packages/zkhardware/platforms.md`（逐平台结论）。
> 引脚/接口的**板级规格**（哪块板有几个 I2C/SPI/PWM、座子定义）→ `knowledge/hardware/hardware-models.md`。

## 0. 来源、可信度与自查方式（**先读这一节**）

**本文抄自 `zkhardware` 包的公开头文件**，不是真机验收结论，也不是派生页。三件事必须说清：

| 项 | 说明 |
|---|---|
| **头文件在哪** | 包内 `include/utils/*.h` + `include/hw/HardwareManager.h`。**不在本仓库**：它随包注册表分发。按 `package_tools.REGISTRY_CANDIDATES` 的顺序找：`$FLYTHINGS_REGISTRY` → `~/.fsc/registry/public` → `~/.fun/registry/public` → `~/.fuse/registry/public` → `C:\zkswe\fun\registry\public`；包目录为 `<registry>/<平台小写>/zkhardware/<版本>/` |
| **为什么不是派生页** | 生成器要在 fresh clone / CI 上能跑才配当"派生"。头文件不在仓库里 → 生成器在别人的机器上必然失败。所以本页是**人工维护 + 标明出处 + 给出可复核的清单**（见下表），不是 `--check` 派生页。**改头文件版本后请按 §3 复核本页** |
| **哪些是"契约"、哪些是"实测"** | 签名/默认值/枚举/返回约定 = **头文件契约**（离线可核，本页负责）；**行为与真机读数**（比如某块板没有 ADC 接口、继电器索引不是顺序映射）只在 **Z20 86 面板**实测过 → 一律指向 `packages/zkhardware/`，本文不复制 |

**收录时实测的版本与清单**（可据此判断你手上的头文件是否同一版）：

| 平台 | 包版本 | utils 头文件 | HardwareManager |
|---|---|---|---|
| Z20 | `0.0.0` | 6 个：`AdcHelper.h` 569B / `BrightnessHelper.h` 1457B / `GpioHelper.h` **3882B** / `I2CHelper.h` 1809B / `PWMHelper.h` 1117B / `SpiHelper.h` 2443B | `hw/HardwareManager.h` 754B |
| Z21 | `0.0.0` | 同上，唯 `GpioHelper.h` **3682B** | 同上（逐字节相同） |
| V85X | `0.0.0` | 同上，唯 `GpioHelper.h` **2775B**、`BrightnessHelper.h` **1838B** | 同上（逐字节相同） |
| Z235X | `1.1.0` | 同上，唯 `BrightnessHelper.h` **1929B**；`GpioHelper.h` 与 V85X **逐字节相同** | 同上（逐字节相同） |
| T113 / F133 / F135 | — | **未核**：本机 registry 里没有这三个平台的 `zkhardware`（它们有注册表就有，见上面候选链） | 未核 |

> ⚠️ **`AdcHelper.h` / `I2CHelper.h` / `PWMHelper.h` / `SpiHelper.h` / `HardwareManager.h` 四个平台逐字节相同**；
> **只有 `GpioHelper.h` 与 `BrightnessHelper.h` 存在平台变体** —— 差异见 §3，那是本页最大的增量。

## 1. 一分钟速查

| 类 / 宏 | 形态 | 头文件 | 一句话 |
|---|---|---|---|
| `GpioHelper` | **全静态** | `utils/GpioHelper.h` | GPIO 读写 + 边沿中断监听 + **过零 IO（控交流继电器）** |
| `AdcHelper` | **全静态** | `utils/AdcHelper.h` | ADC：使能 → 选通道 → 读值 |
| `BrightnessHelper` / `BRIGHTNESSHELPER` | **单例** | `utils/BrightnessHelper.h` | 亮度 / 开屏关屏 / 背光 / 对比度饱和度色调 |
| `HardwareManager` / `HARDWAREMANAGER` | **单例** | `hw/HardwareManager.h` | 蜂鸣器（含自定义 beep 回调、beep PWM） |
| `I2CHelper` | **实例（自己持有）** | `utils/I2CHelper.h` | I2C 总线读写（构造即持总线号/从机地址/超时/重试） |
| `SpiHelper` | **实例（自己持有）** | `utils/SpiHelper.h` | SPI 全双工/半双工/单工 |
| `PWMHelper` | **实例（自己持有）** | `utils/PWMHelper.h` | PWM 频率/占空比/极性/使能 |

工程里这样 include（包已把 `include/` 加进搜索路径）：

```cpp
#include "utils/GpioHelper.h"
#include "utils/AdcHelper.h"
#include "utils/I2CHelper.h"
#include "utils/SpiHelper.h"
#include "utils/PWMHelper.h"
#include "utils/BrightnessHelper.h"   // 亮度 / 背光 / 开关屏
#include "hw/HardwareManager.h"       // 蜂鸣器
```

## 2. 逐外设 API（签名照抄头文件）

### 2.1 GPIO —— `GpioHelper`（全静态）

```cpp
static int  input(const char *pPin);            // -1 失败；1 高电平 / 0 低电平
static int  output(const char *pPin, int val);  // val 1 高 / 0 低；-1 失败，0 成功
static void registerGpioListener(const char *pPin, IGpioListener *pListener, EGpioEdgeType type);
static void unregisterGpioListener(const char *pPin, IGpioListener *pListener);

typedef enum {
    E_GPIO_EDGE_TYPE_NONE,      // 无中断触发（默认值）
    E_GPIO_EDGE_TYPE_RISING,    // 上升沿
    E_GPIO_EDGE_TYPE_FALLING,   // 下降沿
    E_GPIO_EDGE_TYPE_BOTH       // 双边沿
} EGpioEdgeType;

class IGpioListener {                       // 你自己的监听类继承它
public:
    virtual ~IGpioListener() { }
    virtual bool onGpioEdge(const char *pPin) = 0;
    virtual void onGpioError(const char *pPin, int error) = 0;
};
```

**注意两个返回约定不一致**（照抄别想当然）：`input()` 成功返回 **电平 1/0**、失败 `-1`；
`output()` 成功返回 **0**、失败 `-1` —— 所以判成功要写 `rc != -1`（`output` 的 0 是成功，别写成 `if (!output(...))`）。

**引脚名是字符串**，来自头文件里的宏分组（不是数字）：

| 宏分组 | 引脚 | 出现在哪些平台变体 |
|---|---|---|
| Z11 | `B_02` `B_03` `E_20` `E_14`（注释标 beep） | **全部** |
| SV50PB | `PIN7`…`PIN14`、`PIN23` `PIN24` `PIN26` `PIN27` | **全部** |
| SV50PC | `PIN2`…`PIN11`、`PIN13`…`PIN18`、`PIN22`、`PIN24`…`PIN31` | **全部** |
| SV50PD | `A0`…`A8` | 仅 **Z20 / Z21** |
| H500S | `PG0`…`PG5`、`PG10`…`PG13` | 仅 **Z20** |

> 用法是直接把宏或字面量传给 API：`GpioHelper::input(GPIO_PIN_B_02)` 与 `input("B_02")` 等价。
> **引脚名与平台的对应关系**（哪块板引出了哪几路）看 `knowledge/hardware/hardware-models.md` 的管脚表。

### 2.2 过零 IO（控交流电继电器）—— 同 `GpioHelper`，**仅 Z20 / Z21 有**

```cpp
static int  zeroOutput(uint8_t index, bool onoff, uint32_t onns = 0, uint32_t offns = 0);  // -1 失败，0 成功
static int  getZeroIoNum();                    // 过零 io 路数
static bool getZeroIoStatus(uint8_t index);    // true 开 / false 关
static void zeroResetPeriod();                 // 重置过零 io 周期
```

⚠️ **`onns`/`offns` 的"默认值"有两套说法**：签名默认是 `0`，而头文件注释写「默认 4900000ns / 6000000ns」
→ 只能理解为 **`0` 是"用内部默认"的哨兵值**（照注释推断）。**这一点未在真机验证**；
要精确控制导通/关断时刻就显式传 ns，别依赖 0 的语义。

⚠️ **索引与物理通道不是顺序映射**：Z20 实测索引映射是 `{3,1,2}`、索引 0 是备注位 → 见
`packages/zkhardware/platforms.md`「3 路继电器分别控制已实测」一节。**别按 0/1/2 顺序接**。

### 2.3 ADC —— `AdcHelper`（全静态）

```cpp
static bool setEnable(bool isEnable);   // true 使能 / false 禁止
static bool setChannel(int ch);         // 选通道
static int  getVal();                   // 成功返回 adc 值；-1 失败
```

调用顺序固定：**`setEnable(true)` → `setChannel(ch)` → `getVal()`**。
⚠️ 通道数与量程**由板级决定**，头文件不给；而且「`setChannel` 返回成功」只代表**软件路径通了**，
不代表板上真有 ADC 接口 —— Z20 86 面板就是这情况（四路都能选中，但读到的是无效通道/噪声），
详见 `packages/zkhardware/README.md` §4 的 ADC 行。**没实测过就别标定阈值。**

### 2.4 背光 / 显示 —— `BrightnessHelper`（单例）

```cpp
static BrightnessHelper* getInstance();     // 或宏 BRIGHTNESSHELPER
int  getMaxBrightness() const;
int  getBrightness() const;
void setBrightness(int brightness);
void screenOff();  void screenOn();
void backlightOff();  void backlightOn();
void setLCDEnable(bool enable);
bool isScreenOn() const;
void setContrast(int contrast);      void setSaturation(int saturation);   void setHue(int hue);
```

⚠️ **头文件注释与真机实测冲突，以实测为准**：注释写 `setBrightness` 范围 `0 ~ 100`，
而 Z20 实测口径是 **`1 ~ 100`，传 0 不是"最暗"而是关屏语义**（见 `packages/zkhardware/README.md` §5）。
自己夹下限，别传 0。

**平台变体**（这是背光这块最容易踩的地方，见 §3）：`screenOffEx/screenOnEx` **只有 Z20/Z21 有**；
`setLuminance/getLuminance`、`getContrast/getSaturation/getHue`、`setDvdd` 只有 **V85X/Z235X 有**；
`setVcom` 只有 **Z235X** 有。

### 2.5 蜂鸣器 —— `HardwareManager`（单例）

```cpp
typedef void (*custom_beep_cb_t)();
static HardwareManager* getInstance();          // 或宏 HARDWAREMANAGER
void beep();                                    // 响一声
void setBeepPWM(uint32_t freq, uint8_t duty);   // 注释：freq 默认 2500、duty 默认 50
void setCustomBeep(custom_beep_cb_t cb);        // 用自定义回调替换默认 beep
```

⚠️ 头文件注释写「默认 2500 / 50」，但**签名没有默认参数** —— 要默认行为就自己传 `2500, 50`。
⚠️ 换 `setCustomBeep` 后 `beep()` 走你的回调；**用回默认要重新 `setCustomBeep` 恢复**（头文件未提供"取消"接口）。

### 2.6 I2C —— `I2CHelper`（实例类，自己持有）

```cpp
I2CHelper(int nr, uint32_t slaveAddr, uint32_t timeout, uint32_t retries);   // timeout 单位 ms
virtual ~I2CHelper();
bool setSlaveAddr(uint32_t slaveAddr);
bool setTimeout(uint32_t timeout);
bool setRetries(uint32_t retries);
bool transfer(const uint8_t *tx, uint32_t txLen, uint8_t *rx, uint32_t rxLen);  // 半双工：共用读写、中间无 stop
bool read(uint8_t *rx, uint32_t len);
bool write(const uint8_t *tx, uint32_t len);
```

- **`transfer` 是"写寄存器再读"的正解**（中间不发 stop）；分两次调 `write` + `read` 会在中间插 stop，
  很多从机不认。
- `nr` 是**总线号**、`slaveAddr` 是**从机地址**，都**按板级定**（头文件不给值）→ 查
  `knowledge/hardware/hardware-models.md` 的板级默认参数（如 Z21 是 `I2C0`/`I2C1`）。
- 头文件只有前置声明 `struct i2c_dev;`，实现依赖 `linux/i2c-dev.h` —— **系统头，工程不用额外带**。

### 2.7 SPI —— `SpiHelper`（实例类，自己持有）

```cpp
SpiHelper(int nr, uint8_t mode, uint32_t speed, uint8_t bits = 8, bool isLSB = false);
virtual ~SpiHelper();
bool setMode(uint8_t mode);          // SPI_MODE_0 / 1 / 2 / 3
bool setSpeed(uint32_t speed);
bool setBitsPerWord(uint8_t bits);
bool setBitSeq(bool isLSB);          // true 低位在前 / false 高位在前
bool fullduplexTransfer(const uint8_t *tx, uint8_t *rx, uint32_t len);      // ⚠️ 读、写长度需一致
bool halfduplexTransfer(const uint8_t *tx, uint32_t txLen, uint8_t *rx, uint32_t rxLen);
bool read(uint8_t *rx, uint32_t len);
bool write(const uint8_t *tx, uint32_t len);
```

- `bits` 默认 **8**、`isLSB` 默认 **false（高位在前）**（头文件唯一给了默认值的实例类）。
- ⚠️ `fullduplexTransfer` **只有一个 `len`** —— 头文件注释明写「读、写数据长度需一致」；
  收发的字节数不等就用 `halfduplexTransfer`。

### 2.8 PWM —— `PWMHelper`（实例类，自己持有）

```cpp
PWMHelper(int nr, uint32_t freq, uint8_t duty, uint8_t polarity);
virtual ~PWMHelper();
bool setFreq(uint32_t freq);
bool setDuty(uint8_t duty);
bool setPolarity(uint8_t polarity);
bool setEnable(bool isEnable);
```

⚠️ 仓库已有的实测警告（`packages/zkhardware/README.md` §2 表末）：**PWM 可能与本机背光 PWM 同路**，
动之前先确认，别把背光调没了。`duty` 是 `uint8_t`（不是 0~100 的百分比类型），量程按驱动。

## 3. 平台差异矩阵（**本页最大增量**：头文件级差异，不是实测差异）

| 能力 | Z20 | Z21 | V85X | Z235X |
|---|---|---|---|---|
| `GpioHelper::input/output` + 边沿监听 | ✅ | ✅ | ✅ | ✅ |
| `GpioHelper::initPinMap` | **❌ 没有** | ✅ | ✅ | ✅ |
| **过零 IO**（`zeroOutput` / `getZeroIoNum` / `getZeroIoStatus` / `zeroResetPeriod`） | ✅ | ✅ | **❌ 没有** | **❌ 没有** |
| 引脚宏 `SV50PD`（`A0`…`A8`） | ✅ | ✅ | ❌ | ❌ |
| 引脚宏 `H500S`（`PG0`…） | ✅ | ❌ | ❌ | ❌ |
| `BrightnessHelper::screenOffEx/screenOnEx` | ✅ | ✅ | **❌** | **❌** |
| `setLuminance/getLuminance`、`getContrast/getSaturation/getHue`、`setDvdd` | ❌ | ❌ | ✅ | ✅ |
| `BrightnessHelper::setVcom` | ❌ | ❌ | ❌ | ✅ |
| ADC / I2C / SPI / PWM / 蜂鸣器 | ✅ | ✅ | ✅ | ✅（四平台头文件逐字节相同） |

**结论怎么用**：
- **过零继电器只在 Z20/Z21 存在** —— 在 V85X/Z235X 上写 `zeroOutput` 是**编译不过**（不是运行期失败），
  移植时别照抄 Z20 的继电器逻辑。
- **`initPinMap` 只在 Z20 缺席** —— 用到它的代码搬到 Z20 会编译不过。
- 背光增强能力（明度/电压）是 **V85X/Z235X 独有**；`screenOffEx/screenOnEx` 反过来只有 **Z20/Z21** 有。
- 上表是**头文件级**结论（能编过/编不过）。**运行期能不能用**是另一回事，看 `packages/zkhardware/platforms.md`。

## 4. 工程接入

```xml
<!-- Manifest.xml -->
<package id="zkhardware" version="0.0.0"></package>   <!-- Z235X 上是 1.1.0，版本按平台写死 -->
```

- 版本号**写死**、不要浮动（`components/README.md` §3 口径）；改完 Manifest **必须重跑 `fun install`**。
- ⚠️ **`fun.json` 优先于 `Manifest.xml`**：依赖写 `fun.json` 的 `dependencies` 才生效，
  只写 Manifest 时 `fun install` 可能"报成功但没装"（`knowledge/v85x/h264-player-usage.md` §2 有实测记录）。
- 用哪个包/版本的查询与加包闭环：`flythings_query_package` / `flythings_add_package` /
  `flythings_get_package_api`（返回体带 `packages/zkhardware` 的包卡）。

## 5. 硬约束与铁律（本文只列**头文件口径**推出的坑；真机坑看 `packages/zkhardware/README.md` §5）

1. ⚠️ **`output()` 的 0 是成功**，`-1` 才是失败 —— 判成功写 `rc != -1`，别写 `if (!output(...))`。
2. ⚠️ **`input()` 返回三态**（`1`/`0`/`-1`）—— 别把 `-1` 当低电平用。
3. ⚠️ **过零继电器索引非顺序映射**（Z20 实测 `{3,1,2}`），且 `zeroOutput` 的 `onns/offns`
   默认值有两套说法（签名 `0` = 哨兵）→ 安全件，先读 `getZeroIoNum()`/`getZeroIoStatus()` 再写。
4. ⚠️ **亮度 1~100 不是 0~100**（头文件写 0~100，真机口径是 1~100）—— 传 0 = 关屏语义。
5. ⚠️ **`SpiHelper::fullduplexTransfer` 要求读写等长**，不等长用 `halfduplexTransfer`。
6. ⚠️ **`I2CHelper` 读寄存器用 `transfer`**（无中间 stop），别 `write` + `read` 拼。
7. ⚠️ **`AdcHelper::setChannel` 成功 ≠ 板上有 ADC** —— 先确认接口存在，再定阈值。
8. ⚠️ **PWM 可能与背光同路**（README §2 实测警告）—— 动 PWM 前先确认不抢背光。
9. ⚠️ **过零 IO / `initPinMap` / `screenOffEx` 等有平台差异** —— 跨平台移植先过 §3 矩阵，
   否则是**编译期**失败（不是运行期）。
10. **`IGpioListener` 的回调在什么线程上被调、能做什么**——头文件未声明，仓库也未实测 → **未核**；
   按 `activity-code-skeleton.md` 的跨线程纪律处理（别在回调里直接操作 UI，走队列/标志位）。

## 6. 未收录 / 待补（**如实登记，别当已核**）

| 项 | 状态 | 补什么 |
|---|---|---|
| **T113 / F133 / F135 的头文件** | 未核 | 那三个平台若在 registry 里有 `zkhardware`，按 §0 的路径找出来对比 §3 矩阵 |
| 所有**运行期行为** | 仅 Z20 86 面板实测过 | `packages/zkhardware/platforms.md` 把 Z21/F133/F135/V85x/T113 都标着「未验证」 |
| `onns/offns` 传 0 的真实语义 | 未核（头文件注释与签名不一致） | 真机上用示波器/日志确认，或显式传 ns 绕开 |
| `IGpioListener` 回调线程模型 | 未核 | 读实现或用例实测 |
| 各 `setXxx` 失败时的 errno / 日志 | 头文件只给 bool/int | 真机抓 `logcat` 补 |
| 本页的机器可读化（域④ 真源收编） | 未做 | `CONSOLIDATION.md` §2 把域④的真源定为 `hardware_catalog.json`（"已有，待收编"）——外设 API 表**尚未**进注册表；收编后可像 ui_schema 那样派生+门禁，但**前提是头文件进仓库或能稳定取到**（见 §0 第 2 行） |

## 7. 相关

- `packages/zkhardware/README.md`：用法示例 + API 速查（**子集**）+ 真机实测 + 硬约束
- `packages/zkhardware/platforms.md`：逐平台实测表 + Z20 板级事实（继电器索引映射、GPIO 只能 `zeroOutput`）
- `knowledge/hardware/hardware-models.md`：板级规格（分辨率/接口数量/管脚表/默认参数）
- `knowledge/devflow/activity-code-skeleton.md`：`GpioHelper` 在 activity 里的用法位置与跨线程纪律
- `knowledge/devflow/dependency-package-docs.md` / `knowledge/devflow/builtin-packages.md`：包怎么找、包卡怎么读
