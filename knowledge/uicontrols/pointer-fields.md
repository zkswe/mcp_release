---
id: uicontrols-pointer-fields
title: Pointer 指针仪表控件 JSON 字段规范
category: uicontrols
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [0 SDK 头文件校准, h 源码, 非猜测, 适用平台：全平台, fun 新工程, 原 fuse]
evidence: []
---
# Pointer 指针仪表控件 JSON 字段规范

> 检索导引：问「指针·表盘怎么做 / 指针绕的圆心不对 / rotationPoint 与 fixedPoint 怎么配 / 起始角负数 / 旋转动画 animatable·rotateSpeed」→ 本文。
> 2026-09-07 git.com 全库学习 + basedemo/PointerDemo-New + f133 easyui 2.9.0 SDK 头文件校准（fui unpack 实测字段 + ZKPointer.h 源码，非猜测）。
> 适用平台：全平台（fun 新工程（原 fuse）同样适用）。

## 核心铁律

1. **指针控件 = 表盘指针/旋转图标专用**：做仪表、时钟指针、WiFi 扫描旋转图标等"绕固定圆心旋转"效果用 pointer，不要用 textview/button 拼旋转。
2. **旋转圆心由两个坐标共同决定**：`rotationPoint`（旋转点，相对控件左上）+ `fixedPoint`（指针固定点，相对指针图）——两者配合指针才绕对圆心转。起始角度不准时先查这两个值。
3. **fixedPoint 可超出图片范围**：把固定点设到图片外很远 + 调 rotationPoint，可做出"游标环"效果（PointerDemo/wiki 实测）。
4. **动画方式二选一**：
   - `animatable=true` + `rotateSpeed`（实测配 500）：控件内部自动旋转到目标角（SDK 有 ID_ROTATE_POINTER_TIMER 内置定时器）
   - `animatable=false`（产品中绝大多数，29/32）：调用方定时器/线程循环 `setTargetAngle` 驱动（KaiduZ9S wifi 图标 3ms/+1°、clockDemo 表针每秒+6°）
5. **起始角度支持负数**（-120° = 表盘 0 位校准）。

## JSON 字段表（ftu 实测校准）

| 字段 | 类型/取值 | 说明 |
|------|----------|------|
| `caption` | string | 控件名（IDE 自动 m+Caption+Ptr） |
| `id` | int | 控件 id（实测 **90001** 段） |
| `pointerPic` | string | 指针图片路径（相对 resources，如 `wifi/SX.png`） |
| `pointerSize` | {width,height} | 指针图显示尺寸（如 50×50） |
| `rotationPoint` | {x,y} | 旋转点坐标（相对控件，控制绕哪转） |
| `fixedPoint` | {x,y} | 指针固定点坐标（相对指针图，可超界做游标） |
| `startAngle` | int | 起始角度（默认 0，可负） |
| `clockwise` | bool | true=顺时针 |
| `rotateSpeed` | int | 自动旋转速度（animatable=true 时生效，实测 500） |
| `animatable` | bool | true=控件自动动画；false=调用方驱动（默认） |
| `touchable` | bool | 通常 false |
| `backgroundColor`/`backgroundPic` | | 背景（表盘图可放背景或放控件下层） |
| `position` | {left,top,width,height} | 控件位置尺寸 |

## 代码操作

```cpp
// 转到指定角度（float，度）
mPointer1Ptr->setTargetAngle(90.0f);

// 表针换算（clockDemo 实测）
// 秒针 = sec * 6.0
// 分针 = min * 6.0 + 秒针/60
// 时针 = (hour%12) * 30.0 + 分针/12
// 每秒定时器：秒针 += 6.0 再 setTargetAngle
```

## 样例代码
PointerDemo-New（随机角度+串口角度双模式）；clockDemo-New（3 pointer 组装时钟）；KaiduZ9S wifiLogic.cc（旋转 loading 图标）。
