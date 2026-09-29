# zkhardware —— 用法示例（真机验证）

> **包信息**：`zkhardware` `0.0.0`（设备端 `libzkhardware.so`，头文件在 `include/hw`、`include/utils`）
> **实测平台**：Z20（SSD20X，480×480，easyui 2.6.0）·2026-09-28 / 09-29 · 证据见 `evidence/`
> **⚠️ 面板口径（Z20 86 面板，2026-09-29 钟工确认）**：**没接蜂鸣器**、**没有 ADC 接口**、**GPIO 操作只能走 `zeroOutput()`**（IO 控交流电继电器）——`input()` 那类读法在面板上不成立。别按「通用开发板」理解本包能力，见 §4 / §5。
> **一句话**：硬件外设门面类——蜂鸣器 / 亮度背光 / ADC / GPIO（含**过零 IO → 3 路继电器分别控制**）/ I2C / PWM / SPI。

## 1. 怎么装

`Manifest.xml` 里声明依赖（**改完必须 `fun install`**，否则头文件路径不进 CMake）：

```xml
<dependencies enableOnPlatforms="Z20">
    <package id="easyui" version="^2.2.0"/>
    <package id="log" version="0.0.0"/>
    <package id="zkhardware" version="0.0.0"/>
</dependencies>
```

```bash
fun install      # 解析依赖（本机解析到 easyui 2.6.0 / zkhardware 0.0.0）
fun build -p z20
```

## 2. API 速查（按头文件口径）

| 类 / 宏 | 方法 | 语义（实测口径） |
|---|---|---|
| `HardwareManager` / `HARDWAREMANAGER` | `beep()` | 蜂鸣器响一声（void，无返回值） |
| | `setBeepPWM(freq, duty)` | 频率默认 2500、占空比默认 50 |
| | `setCustomBeep(cb)` | 自定义 beep 回调 |
| `BrightnessHelper` / `BRIGHTNESSHELPER` | `getMaxBrightness()` / `getBrightness()` / `setBrightness(v)` | 范围 **1~100**（本机 max=100）；`getBrightness` 读回生效值 |
| | `screenOff()/screenOn()/backlightOff()/backlightOn()/screenOffEx()/screenOnEx()` | 关/开屏、关/开背光 |
| | `setContrast/setSaturation/setHue(v)` | 0~100 |
| `AdcHelper`（静态） | `setEnable(bool)` → `setChannel(ch)` → `getVal()` | `getVal()` 返回 ADC 值，**-1 = 失败** |
| `GpioHelper`（静态） | `input(pin)` | 返回 `1/0` 电平，**-1 = 失败** |
| | `output(pin, val)` | 1 高 / 0 低；返回 -1 失败 |
| | `registerGpioListener(pin, listener, edgeType)` | 边沿中断回调（`IGpioListener::onGpioEdge/onGpioError`） |
| | `zeroOutput(index, onoff, onns=0, offns=0)` | **过零 IO 输出**（继电器/可控硅；默认 onns=4900000ns、offns=6000000ns） |
| | `getZeroIoNum()` / `getZeroIoStatus(index)` / `zeroResetPeriod()` | 过零 IO 路数 / 状态 / 重置周期 |
| `I2CHelper`（实例） | `I2CHelper(nr, slaveAddr, timeout, retries)` + `transfer/read/write/setSlaveAddr` | 总线号/从机地址按板级定 |
| `PWMHelper`（实例） | `PWMHelper(nr, freq, duty, polarity)` + `setFreq/setDuty/setPolarity/setEnable` | ⚠️ 可能与本机背光 PWM 同路，动前先确认 |
| `SpiHelper`（实例） | `SpiHelper(nr, mode, speed, bits=8, isLSB=false)` + `fullduplex/halfduplex/read/write` | — |

引脚名常量在 `utils/GpioHelper.h`：Z11 组 `B_02/B_03/E_20/E_14`、SV50PB/PC 组 `PINn`、H500S 组 `PGn`、SV50PD 组 `An`。

## 3. 最小示例（可直接粘贴，见 `example/`）

**logic 侧**（`src/logic/mainLogic.cc`）：

```cpp
#include "utils/GpioHelper.h"        // GPIO / 过零 IO（继电器）
#include "utils/AdcHelper.h"         // ADC
#include "utils/BrightnessHelper.h"  // 亮度 / 背光 / 开关屏
#include "hw/HardwareManager.h"      // 蜂鸣器

// 过零 IO 索引映射：通道 1/2/3 → 索引 3/1/2（不是顺序映射！与 SmartPanel_HA 同一张表）
static const int kZeroIndexMap[3] = { 3, 1, 2 };

static bool onButtonClick_ButtonRelay1(ZKButton *pButton) {   // 继电器 1 切换
    int ch = 1;
    int cur = GpioHelper::getZeroIoStatus(kZeroIndexMap[ch - 1]);   // 先回读
    int want = cur ? 0 : 1;
    GpioHelper::zeroOutput(kZeroIndexMap[ch - 1], want);           // 再写
    int back = GpioHelper::getZeroIoStatus(kZeroIndexMap[ch - 1]); // 回读确认
    LOGD("relay %d: %d -> %d -> %d\n", ch, cur, want, back);
    return true;
}

static bool onButtonClick_ButtonBeep(ZKButton *pButton) {
    HARDWAREMANAGER->beep();
    LOGD("beep() called\n");
    return true;
}

static bool onButtonClick_ButtonBrightUp(ZKButton *pButton) {
    int max = BRIGHTNESSHELPER->getMaxBrightness();
    int v = BRIGHTNESSHELPER->getBrightness() + 10;
    if (v > max) v = max;
    BRIGHTNESSHELPER->setBrightness(v);
    LOGD("brightness %d/%d\n", BRIGHTNESSHELPER->getBrightness(), max);
    return true;
}
```

> 完整的 3 路版（含 `relayToggle/relayRead/relayWrite/relayStatusStr`、全部断开、模式判定）见 `example/src/logic/mainLogic.cc`。

**activity 侧**（`src/activity/mainActivity.cpp` 的按键表，**漏了这一步按钮点了没反应**）：

```cpp
static S_ButtonCallback sButtonCallbackTab[] = {
    ID_MAIN_ButtonRelay1, onButtonClick_ButtonRelay1,
    ID_MAIN_ButtonRelay2, onButtonClick_ButtonRelay2,
    ID_MAIN_ButtonRelay3, onButtonClick_ButtonRelay3,
    ID_MAIN_ButtonBeep, onButtonClick_ButtonBeep,
    ID_MAIN_ButtonBrightUp, onButtonClick_ButtonBrightUp,
};
```

`ID_MAIN_<Caption>` 与 `mTextXxxPtr` 由构建生成在 `.fun/<平台>/generated/ui_main.h`（logic 里 `#include GENERATED_UI_DEFINITIONS`）。

**三步跑起来**：把 `example/ui/main.json` 放进工程 `ui/` → `fui pack ./` → 把 `example/src/logic/mainLogic.cc` 的片段并进 logic、按上面填按键表 → `fun build -p z20`。

## 4. 真机实测（Z20 480×480 · 86 面板，2026-09-28 / 09-29，证据 `evidence/`）

| 动作 | 调用 | 设备实测结果（Z20 86 面板） | 判据 |
|---|---|---|---|
| **继电器 ×3（分别控制）** | `zeroOutput(kZeroIndexMap[ch-1], on)` + `getZeroIoStatus()` 回读 | 三路逐路切换均成功：`relay 1: 读=1 → zeroOutput(索引3,0) → 回读=0`，再切回 `读=0 → 写 1 → 回读=1`；2/3 路同（索引 1 / 2）；「全部断开」三路一起归 OFF | ✅ **3 路可分别控、写后回读一致**（钟工 09-29 现场面板实点）|
| 蜂鸣器 | `HARDWAREMANAGER->beep()` | 调用无异常、日志回显 `HARDWAREMANAGER->beep() 已调用` | ⚠️ **86 面板没接蜂鸣器** → 只能验「调用链通、不崩」，**验不了声响**；要有声换带蜂鸣器的板 |
| 亮度 | `getBrightness()` 17 → `setBrightness(21/31/41/51/61)` | **人眼确认面板亮度有变化**（钟工 09-29 现场确认） | ✅ 读回值 == 设置值（21/31/41/51/61 逐次一致）；`getMaxBrightness()=100` |
| ADC | `setEnable(true)` + `setChannel(0..3)` + `getVal()` | ch0=0、ch1=41~43、ch2=940~942、ch3=608~611（3 轮扫描**逐次浮动**） | ⚠️ API 四路都返回 `ok=1`，但 **86 面板没有 ADC 接口** → 读到的是无效通道/噪声值，**别当可用能力、别标定阈值**；要 ADC 得换带 ADC 接口的板 |
| GPIO 读 | `input("B_02"/"B_03"/"E_20")` | **三脚全部 -1** | ❌ 面板上不成立：这三脚是**交流继电器过零驱动脚**，面板 GPIO 操作**只能走 `zeroOutput()`**（读状态用 `getZeroIoStatus()`） |
| 过零 IO | `getZeroIoNum()`=**4**、`getZeroIoStatus(i)` | `#0=OFF #1=ON #2=ON #3=ON` | ✅ 读路径可用（4 路）；动作走 `zeroOutput(index,onoff,onns,offns)`——**本轮未做写入**（驱动交流继电器属安全件，见 §5-8） |
| 截图 | — | `evidence/zkhardware_108_screen.png`（480×480 真机帧） | ✅ UI + 结果文字正常上屏 |

## 5. 坑（真机踩到的）

1. **`GpioHelper::input()` 对继电器脚返回 -1**：Z20 86 面板 `B_02/B_03/E_20` 是**过零驱动脚**，面板侧 GPIO 操作**只能走 `zeroOutput()`**（钟工 2026-09-29 口径），读状态用 `getZeroIoStatus(index)`。实测三脚全 -1，不是「坏了」。
2. **ADC 在 86 面板上无意义**：四通道 `ok=1` 且值会浮动（ch1≈41~43、ch2≈940~942、ch3≈608~611、ch0=0），但**该面板没有 ADC 接口** → 是无效通道/噪声，**不要写阈值、不要拿它做产品逻辑**；换带 ADC 接口的板再验。
3. **亮度范围是 1~100**，不是 0~100：传 0 不是「最暗」而是关屏语义，本示例做了下限 1。
4. **按键回调要在 activity 的 `sButtonCallbackTab` 注册**，只在 logic 里写 `onButtonClick_Xxx` 不生效（点按钮无反应、无日志）。
5. **改 Manifest 后必须 `fun install`**，否则 `utils/GpioHelper.h` 这类包内头文件找不到。
6. `beep()` 是 **void 无返回**，调用成功≠一定响（要人耳/示波器确认）；本机 PWM 频率/占空比默认 2500/50。**Z20 86 面板没接蜂鸣器** → 在这块板上永远听不到声，别当成 bug 查。
7. `PWMHelper` 动 PWM 前先确认不占背光 PWM 通道（本示例**没有**演示 PWM 写入，只列 API）。
8. **`zeroOutput()` 驱动的是交流电继电器（安全件）**：写 ON 前必须确认回路/负载已就位（空载台架也要确认），示例默认**上电不写状态**（`onUI_init` 只回读），切哪一路都由人点按钮才动。
9. **过零 IO 索引映射不是顺序映射**：本板 `{3,1,2}` → **通道 1/2/3 = 索引 3/1/2**（索引 0 对应通道 3）。写错映射 = 点「继电器 1」实际动了别的回路。改接线只改这一张表；索引 0 在 SmartPanel 上是第 4 个备注位（实测常显 ON，别当第 1 路）。
10. **写后一定要回读**：`getZeroIoStatus(index)` 才是真实状态；只记软件侧变量会在别处（MQTT/HA/设备重启）改过状态时读错。
