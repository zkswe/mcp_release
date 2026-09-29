# DigitalClock 数字时钟控件 JSON 字段规范

> 检索导引：问「数字时钟控件 / 时间显示要不要写代码 / 冒号跳动 beat / 怎么改显示时间（改系统时间）/ 秒显示」→ 本文。
> 2026-09-07 git.com 全库学习 + basedemo/DigitalClockDemo-New + f133 easyui 2.9.0 SDK（ZKDigitalClock.h 继承 ZKTextView）校准。

## 核心铁律

1. **数字时钟自动跟随系统时间显示，无需任何代码**——纯 ftu/json 属性配置即用（显示时/分，秒以下可选）。
2. **改显示内容 = 改系统时间**：代码里 `TimeHelper::getDateTime()` 改 tm 字段后 `TimeHelper::setDateTime(&tm)`，时钟控件自动刷新（DigitalClockDemo/DateDemo 实测）。
3. **`beat` = 冒号(:)每秒跳动闪烁**（秒跳动画效）；不想要跳动设 false。
4. 普通文本时间显示（要自定义样式/多种格式拼接）用 textview + 定时器自己刷；纯标准时间显示用 digitalclock。

## JSON 字段表（ftu 实测校准）

| 字段 | 类型/取值 | 说明 |
|------|----------|------|
| `caption` | string | 控件名 |
| `id` | int | 控件 id（实测 **93001** 段） |
| `format` | string | 时间格式，实测 `"HH:MM"`（12/24 小时制、是否带秒由内部解析） |
| `beat` | bool | true=冒号跳动 |
| `clockColor` | int | 时间颜色（16777215=白） |
| `fontSize` | int | 字号 |
| `backgroundColor` | int | 背景色 |
| `touchable`/`visible`/`position` | | 通用 |

## 代码操作

```cpp
// 读取系统时间
struct tm *t = TimeHelper::getDateTime();
// 修改系统时间（DateDemo/DigitalClockDemo 实测写法）
struct tm t2; /* 或取 getDateTime() 后改字段 */
t2.tm_year = year - 1900; t2.tm_mon = mon - 1; t2.tm_mday = day;
t2.tm_hour = hour; t2.tm_min = min; t2.tm_sec = sec;
TimeHelper::setDateTime(&t2);
```

## 样例代码
DigitalClockDemo-New（4 种配置时钟 + 系统时间设置）；ScreensaverDemo-New（屏保时钟）。
