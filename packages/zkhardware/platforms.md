# zkhardware · 平台实测表

> 口径：**只写实测过的**；没测的写「未验证」并说明需要什么条件，不猜、不套其他平台结论。

| 平台 | 版本 | 结论 | 实测内容 | 证据 |
|---|---|---|---|---|
| **Z20**（SSD20X 480×480，easyui 2.6.0）·**86 面板**| zkhardware 0.0.0 | ✅ 可用（**亮度 / 3 路继电器（写+回读）**）；⚠️ 蜂鸣器、ADC **面板侧无硬件**| 蜂鸣器 `beep()`（调用链通、面板无蜂鸣器不发声）、亮度 `1~100` 读写（人眼确认变亮度）、**3 路继电器分别控制**（`zeroOutput(索引 3/1/2)` + `getZeroIoStatus` 回读双向一致、「全部断开」生效）、ADC ch0~3（**面板无 ADC 接口**，值为无效通道）、GPIO `input()`（三脚 -1 → 面板 GPIO **只能 `zeroOutput()`**） | `evidence/zkhardware_108_screen.png`、`evidence/zkhardware_108_logcat.txt`、`evidence/zkhardware_108_logcat_86panel_20260929.txt`、`evidence/zkhardware_108_relay3_20260929.txt/.png` |
| Z21 | — | 未验证 | — | — |
| F133 / F135 | — | 未验证 | — | — |
| V85x | — | 未验证 | — | — |
| T113 | — | 未验证 | — | — |

## Z20 板级事实（本轮实测）

- **面板口径（Z20 86 面板，2026-09-29 需求方确认）**：**没接蜂鸣器**→ `beep()` 只验调用不崩、验不了声；**没有 ADC 接口**→ `AdcHelper` 读到的 ch0~3 是无效通道/噪声（别标定阈值）；**GPIO 操作只能走 `zeroOutput()`**—— 面板侧是 **IO 控交流电继电器**，`input()` 读那三脚无意义（永远 -1）。
- 引脚名走 **Z11 组**：`B_02` / `B_03` / `E_20`（`E_14` 注释标 beep；蜂鸣器未接）。
- 过零 IO **4 路**，状态 `#0=OFF，#1/#2/#3=ON`（与 SmartPanel 三路继电器 + 1 备注一致）。
- **3 路继电器分别控制已实测**（2026-09-29）：`zeroOutput()` 写 + `getZeroIoStatus()` 回读双向一致；**索引映射 `{3,1,2}`**→ 通道 1/2/3 = 索引 3/1/2（**不是顺序映射**，索引 0 = 通道 3/备注位）；有效电平 **高电平吸合**；`zeroOutput()` 驱动的是**交流电继电器**（安全件）。
- `getMaxBrightness() = 100`；测试时初始亮度 17。
- ADC **4 通道（0~3）都能 `setChannel` 成功**，返回值 0~1000 量级、会浮动。
- `GpioHelper::input()` 对 `B_02/B_03/E_20` **返回 -1**：面板上这三脚是继电器过零驱动，读状态用 `getZeroIoStatus()`。
- I2C / PWM / SPI **本轮未验证**（需板级总线号/设备地址；PWM 可能与背光同路，动前先确认）。
- 本机无线为 **RTL8188（WiFi，无蓝牙）**→ `gatt`/BLE 类包**不适用本机**，需换有蓝牙平台的机器验证。

## 复现方式

```bash
# 工程：projects/pkg_zkhardware（Z20）
fsc install && fsc build -p z20
# 部署（/tmp 劫持调试，不动 /res）：
adb push .fun/z20/libzkgui.so /tmp/lib/libzkgui.so
adb push ui/main.ftu /tmp/ui/main.ftu
adb push EasyUI.cfg /tmp/EasyUI.cfg      # startupLibPath=/tmp/lib/libzkgui.so, resPath=/tmp/ui/
adb shell setprop ctl.restart zkswe
adb shell logcat -d | findstr "zkhardware demo"
```
