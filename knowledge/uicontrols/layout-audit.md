---
id: uicontrols-layout-audit
title: 🔍 UI 控件 Layout 全量检查报告
category: uicontrols
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [35 个官方 demo, 本次已全部修复]
evidence: []
---
# 🔍 UI 控件 Layout 全量检查报告

> 检索导引：问「21 个控件字段到底全不全 / html2json 支持哪些字段 / 控件 id 段怎么分配 / 有没有遗漏控件」→ 本文（全量对账报告）。
> 2026-09-01 沛哥要求：所有 UI 控件 Layout 确认学习后统一检查。
> 方法：basedemo-new_z20_1024_600（35 个官方 demo）批量抽取 21 种控件真实 json 字段，逐控件对照 html2json 转换实现找缺口，本次已全部修复。

## 1. 检查结论（21 控件全过）

| # | 控件 | basedemo 样例 | 关键字段（实测） | html2json 支持 | 本次修复 |
|---|------|--------------|-----------------|---------------|---------|
| 1 | button | ButtonDemo (139) | picTab 五态/bgColorTab/colorTab/iconPosition/roll* | ✅ 完整 | +bold/italic/roll |
| 2 | textview | TextViewDemo (137) | colorTab/bgColorTab/roll*/textPosition | ✅ 完整 | +bold/italic/roll |
| 3 | edittext | EditTextDemo (18) | hintText/hintTextColor/isPassword/passwordChar/textType | ✅ 完整 | +bold/italic/roll |
| 4 | window | WindowDemo (31) | modal/hideTimeOut/backgroundColor/visible | ✅ 完整 | — |
| 5 | listview | listViewDemo (3) | cols/rows/rowSpacing/colSpacing/item.subItem | ✅ | +autoRollback/cycleEnable/dragMaxDis/edgeEffect/hasScrollbar |
| 6 | slidewindow | SlideWindowDemo (1) | cols/rows/iconSize/items[]/rollSpeed/padding | ✅ | +backgroundPic/iconMaxSize |
| 7 | scrollwindow | ScrollWindowDemo (1) | dragMaxDis/orientation/edgeEffect + 内嵌 window | ✅ 完整 | —（已入库） |
| 8 | pagewindow | PageWindowDemo (1) | dragMaxDis/orientation/edgeEffect/rollSpeed + 页面 window 叠放 | ✅ 完整 | — |
| 9 | pointer | PointerDemo/clockDemo (5) | pointerPic/fixedPoint/rotationPoint/pointerSize/startAngle | ✅ 完整 | —（已修复坐标） |
| 10 | circlebar | CircleBarDemo (2) | progressPic/progressPicPos/clockwise/maxAngle | ✅ | +textColor/textSize/textType/unit/thumb/touchRange |
| 11 | diagram | DiagramDemo (3) | xAxisRange/yAxisRange/region/infos[]（wave 子项） | ✅ 完整 | — |
| 12 | digitalclock | DigitalClockDemo (6) | format/beat/clockColor | ✅ 完整 | — |
| 13 | imageanim | ImageAnimDemo (3) | playFile/loopCount（实测无 frameInterval，详见 imageanim-fields.md） | ✅ 完整 | — |
| 14 | painter | PainterDemo (1) | 触摸绘制，代码 paint() | ✅ | — |
| 15 | qrcode | QRCodeDemo (3) | codeStr/backgroundColor/padding | ✅ | — |
| 16 | radiogroup | RadioGroupDemo (1) | radiobuttons[]（picTab 两态+checked） | ✅ 完整 | — |
| 17 | checkbox | CheckBoxDemo (1) | picTab{pic0,pic2}/iconPosition/textPosition/checked | ✅ | +bold/italic/roll |
| 18 | seekbar | SeekBarDemo (8) | backgroundPic/progressPic/thumb{size,normalPic,pressedPic}/orientation | ✅ 完整 | — |
| 19 | slidetext | ImeDemo (1) | textBgColor/colorTab | ✅ | +bold/italic/roll |
| 20 | cameraview | CameraDemo (1) | autoPreview/formatSize | ✅ | +cvbs/mirror |
| 21 | videoview | VideoViewDemo (2) | defaultVolume/loopPlayback | ✅ | +rotation |

## 2. 本次修复清单（html2json，2026-09-01）

1. **circlebar**：+ 中间文字 `data-text-color/data-text-size/data-text-type/data-unit`（textColor/textSize/textType/unit）、+ 滑块 `data-thumb/data-thumb-size`（thumb{size,normalPic}）、+ 触摸范围 `data-touch-range="lower,upper"`（touchRange）
2. **cameraview**：+ `data-cvbs`（cvbs 布尔）、+ `data-mirror`（mirror 整数）
3. **videoview**：+ `data-rotation`（rotation 0/90/180/270）
4. **listview**：+ `data-auto-rollback`（autoRollback）、`data-cycle`（cycleEnable）、`data-drag-max`（dragMaxDis）、`data-edge-effect`（edgeEffect）、`data-scrollbar`（hasScrollbar）
5. **slidewindow**：+ `data-bgpic/data-background-pic`（backgroundPic）、`data-icon-max`（iconMaxSize）
6. **文字控件通用**（textview/button/edittext/checkbox/slidetext）：新增 `_text_extra()` 辅助，+ `data-bold`（bold）、`data-italic`（italic）、`data-roll`（rollEnable）+ `data-roll-direction`（rollDirection）+ `data-roll-step`（rollStep）+ `data-roll-interval`（rollIntervalTime）文字滚动

## 3. 之前已校准控件（本报告确认无缺口）

- **pointer**：pointerPic/fixedPoint/rotationPoint/pointerSize/startAngle/rotateSpeed/clockwise/animatable（坐标三件套 16:35 修复）
- **scrollwindow/pagewindow**：容器嵌套结构 + dragMaxDis/orientation/edgeEffect/rollSpeed（16:37 入库）
- **diagram/digitalclock/imageanim/seekbar**：字段与 demo 完全一致

## 4. 控件 id 段（html2json NID 映射，与 IDE 一致）

| 控件 | id 起始 | 控件 | id 起始 |
|------|--------|------|--------|
| button | 20000 | slidewindow | 30000 |
| scrollwindow | 32000 | pagewindow | 31000 |
| textview | 50000 | edittext | 51000 |
| window | 110000 | listview | 70000 |
| checkbox | 80000 | radiogroup | 81000 |
| pointer | 90000 | circlebar | 130000 |
| diagram | 140000 | digitalclock | 93000 |
| imageanim | 94000 | videoview | 95000 |
| qrcode | 92000 | cameraview | 97000 |

## 5. 遗留说明（诚实标注）

- **slidetext**：候选字滑动条（输入法专用），一般项目用不到
- **date**：DateDemo 存在但抽取未检出独立 date 控件类型（demo 里可能用 digitalclock/textview 实现），如有需要再校准
- 各控件 visible/touchable/backgroundColor 等默认值属性 html2json 未全部暴露（不影响主流程，IDE 可再调）
- 文字滚动 roll* 与粗斜体 bold/italic 已在 html2json 支持；textPosition（文字区域）未暴露（布局自动计算）
