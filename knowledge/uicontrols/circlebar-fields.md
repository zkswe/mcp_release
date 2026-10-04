---
id: uicontrols-circlebar-fields
title: CircleBar 圆形进度条控件 JSON 字段规范
category: uicontrols
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [2026-09-07 git, 0 SDK 头文件校准, h 源码]
evidence: []
---
# CircleBar 圆形进度条控件 JSON 字段规范

> 检索导引：问「圆形进度条怎么做 / 圆环仪表·调温调光旋钮 / CircleBar 字段 / progressPic 扇形裁剪 / textType 与 unit / touchRange」→ 本文。
> **口语问法直达**：开口的环怎么设置角度 / 半圆环怎么设置起始角度（`startAngle` + `maxAngle`<360，见字段表）。
> 2026-09-07 git.com 全库学习 + basedemo/CircleBarDemo-New + f133 easyui 2.9.0 SDK 头文件校准（fui unpack 实测字段 + ZKCircleBar.h 源码）。

## 核心铁律

> **缺图不致命但属验收缺陷**：`progressPic/thumb.normalPic/pressedPic` 指向不存在的文件 →
> 控件不可见（framework 容错，不挂死）；图没出好就置 `''`，只写已落盘的图。
> ⛔ 子盒对象字段（`thumb`/`position`/`size`/`progressPicPos`…）**必须写成对象**，
> 写成字符串或其他标量 = ftu 加载无声挂死（规格见 `seekbar-fields.md` §0）。

1. **圆形进度条 = 有效图按扇形裁剪显示进度**：进度值对应的扇形区域是从 `progressPic`（有效图）裁剪出来的；`backgroundPic` 背景图**不会被裁剪**（完整显示垫底）。进度=25/100 且 startAngle=0 顺时针 → 只显示右上 90° 扇形；进度=100 显示全部有效图。
2. **支持触摸拖动**：SDK `ICircleBarChangeListener` 带 onProgressChanged / onStartTrackingTouch / onStopTrackingTouch（与 SeekBar 同构）——可做圆形调温/调光旋钮。但 git.com 产品 18 处 circlebar **全部 touchable=false 只读显示**（净饮机滤芯寿命、烤箱火力环等）；交互优先考虑 seekbar 或确认产品需求再开 touchable。
3. **文本显示 textType**：0=不绘制文本；1=数字；2=数字+单位（`unit` 如 `%`）。实测产品用 textType=2 + unit。
4. `touchRange{lower,upper}` 是触摸可调的角度/进度范围限制（仅 touchable=true 有意义）。

## JSON 字段表（ftu 实测校准）

| 字段 | 类型/取值 | 说明 |
|------|----------|------|
| `caption` | string | 控件名 |
| `id` | int | 控件 id（实测 **130001** 段） |
| `max` | int | 最大进度值（默认 100） |
| `progressPic` | string | 有效图（被扇形裁剪显示进度） |
| `backgroundPic` | string | 背景图（不裁剪，垫底） |
| `progressPicPos` | {left,top,width,height} | 有效图显示位置尺寸（可小于控件做内环效果） |
| `startAngle` | int | 起始角度（0=3 点钟方向起？实测 0） |
| `maxAngle` | int | 最大扫过角度（360=整圆；<360 为开口环） |
| `clockwise` | bool | true=顺时针 |
| `unit` | string | 单位文本（textType=2 时显示，默认 %） |
| `textType` | int | 0 无文本 / 1 数字 / 2 数字+单位 |
| `textSize`/`textColor` | int | 中心文本字号/颜色 |
| `touchRange` | {lower,upper} | 触摸调节范围 |
| `touchable` | bool | 是否可触摸拖动（产品只读场景 false） |
| `visible`/`backgroundColor`/`beepEnable` | | 通用 |

## 代码操作（CircleBarDemo 实测）

```cpp
mCirclebar1Ptr->setProgress(progress);   // 设置进度
mCirclebar1Ptr->setMax(100);
// 触摸监听（需 touchable=true）
class Listener : public ZKCircleBar::ICircleBarChangeListener {
  virtual void onProgressChanged(ZKCircleBar *p, int progress) { }
  virtual void onStartTrackingTouch(ZKCircleBar *p) { }
  virtual void onStopTrackingTouch(ZKCircleBar *p) { }
};
mCirclebar1Ptr->setCircleBarChangeListener(&listener);
```

## 样例代码
CircleBarDemo-New（seekbar 联动两个 circlebar 进度）；KaiduZ9 净饮机滤芯寿命环（只读显示）。
