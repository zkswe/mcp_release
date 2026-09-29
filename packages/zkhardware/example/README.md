# example · zkhardware 最小示例（可直接拷）

一个 480×480 页面 + 9 个按钮：**重点是 3 路继电器分别控制**（`zeroOutput` 过零 IO），
另有蜂鸣器 / 背光± / 读 ADC；每个按钮 = 一次 zkhardware 调用，结果同时进 textview 与 logcat。

| 文件 | 用途 |
|---|---|
| `ui/main.json` | 页面：标题 + 继电器 1/2/3 切换 + 读继电器状态 + 全部断开 + 蜂鸣器 + 背光± + 读 ADC + 结果 textview。`cd ui && fui pack ./` 出 `main.ftu` |
| `src/logic/mainLogic.cc` | 回调实现（`relayToggle()` / `relayRead()` / `relayWrite()` / `relayStatusStr()` + `onButtonClick_ButtonXxx`）+ `setStatus()` + 空定时器表（框架要求保留） |
| `Manifest.xml` | 依赖声明（easyui / log / zkhardware），改完 `fun install` |
| `mainActivity_button_tab.snippet.cpp` | **必须补的一步**：activity 里 `sButtonCallbackTab` 按键注册片段（漏了按钮点了没反应） |

## 继电器三路怎么控（核心口径）

```cpp
// 过零 IO 索引映射：通道 1 / 2 / 3 → 过零输出索引 3 / 1 / 2（不是顺序映射！与 SmartPanel_HA 同一张表）
static const int kZeroIndexMap[3] = { 3, 1, 2 };
static const char *kGpioPins[3]  = { "B_02", "B_03", "E_20" };   // 备用纯 GPIO（高电平吸合）

GpioHelper::zeroOutput(kZeroIndexMap[ch - 1], on ? 1 : 0);       // 动作（驱动交流电继电器）
int cur = GpioHelper::getZeroIoStatus(kZeroIndexMap[ch - 1]);    // 回读真实状态（推荐每次写后回读）
```

- 模式判定：`getZeroIoNum() >= 3` → 过零 IO 模式；否则退纯 GPIO（`output()`）；都没有 → 模拟模式只记日志。
- 三路状态用 `getZeroIoStatus()` 读，**别用 `GpioHelper::input()`** —— 面板上那三脚是过零驱动脚，`input()` 恒返回 -1。
- ⚠️ `zeroOutput` 驱动的是**交流电继电器**：示例**上电不写状态**（`onUI_init` 只回读），切哪一路都由人点了对应按钮才动。

## 三步跑起来

1. `ui/main.json` 放进工程 `ui/`，`cd ui && fui pack ./`（生成 `main.ftu`）
2. `src/logic/mainLogic.cc` 内容并进工程的 logic 文件；把 `mainActivity_button_tab.snippet.cpp` 的 9 行填进
   `src/activity/mainActivity.cpp` 的 `sButtonCallbackTab[]`
3. `fun install && fun build -p z20`，部署（调试走 /tmp 劫持，见 `../platforms.md`）

> 控件指针 `mTextStatusPtr` 和 ID 宏 `ID_MAIN_ButtonRelay1` 由构建自动生成在
> `.fun/<平台>/generated/ui_main.h`（logic 里 `#include GENERATED_UI_DEFINITIONS` 即可用）；
> caption（json 里的 `caption` 字段）= 回调名后缀，必须与 `onButtonClick_<Caption>` 一致。

真机实测数据见 `../README.md` §4 与 `../evidence/`（`zkhardware_108_relay3_20260929.txt/.png`）。
