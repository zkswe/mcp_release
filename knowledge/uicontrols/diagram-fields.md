# Diagram 波形图控件 JSON 字段规范

> 检索导引：问「波形图 / 实时频谱·心率曲线 / diagram 字段 / 多条波形 infos 配置 / setData 与 addData 区别 / 移动动画卡顿」→ 本文。
> 2026-09-07 git.com 全库学习 + basedemo/DiagramDemo-New + f133 easyui 2.9.0 SDK 头文件校准。
> 场景：实时波形（音频频谱、心率、串口 ADC 曲线等）。

## 核心铁律

1. **坐标点统一用 SZKPoint**（沛哥 2026-09-07 纠正：不存在 MPPOINT 平台区分，全平台 SZKPoint，老 wiki 已过时）。
2. **波形图控件含多个波形（wave）**：外层 diagram（xAxisRange/yAxisRange/region 绘制区域）+ infos[] 内每条波形独立样式。**内层波形不生成独立指针变量**，操作通过外层 diagram 指针 + index（从 0 起）。
3. **两种刷数据方式（关键差异）**：
   - `setData(index, SZKPoint*, count)`：全量刷新整条波形。做移动动画需**手动数组整体偏移**（movePoints 把 y[i]=y[i+1]）+ 定时器驱动；大数据量会整图刷新，较慢。
   - `addData(index, float y)` / `addData(index, const float*, count)`：局部刷新，每次自动按 `step`（步进）前进 x，**高效**，适合实时数据流。`step` 和 `eraseSpace`（刷新空缺宽度）只对 addData 生效。
4. 波形 y 值范围由 yAxisRange 决定，超出自动截断；style 0=折线 1=曲线。

## JSON 字段表（ftu 实测校准）

### diagram 外层
| 字段 | 说明 |
|------|------|
| `caption`/`id` | id 实测 **120001** 段 |
| `xAxisRange` | {lower, upper} x 轴范围（颠倒会左右镜像+刷新方向颠倒） |
| `yAxisRange` | {lower, upper} y 轴范围（颠倒上下镜像） |
| `region` | {left,top,width,height} 波形绘制区域（相对控件） |
| `infos` | array 波形数组 |

### infos[] 波形项
| 字段 | 说明 |
|------|------|
| `caption` | 波形名（如 DiagramWave1） |
| `penColor` | 波形颜色 0xARGB |
| `penWidth` | 线宽（实测 2） |
| `style` | 0=折线 LINE / 1=曲线 CURVE |
| `step` | 每次 addData 前进 x 量（受 xScale 影响） |
| `eraseSpace` | 刷新时空缺宽度（只 addData 用） |
| `xScale`/`yScale` | 缩放（业务值×比例后绘制，默认 1.0） |
| `antialias` | 抗锯齿 |

## 代码操作（DiagramDemo 实测）

```cpp
// 全量：onUI_init 先铺底，定时器(90ms)数组左移再 setData
SZKPoint pts[N];  // x = 100*i/N, y=50 铺底
mDiagram1Ptr->setData(0, pts, N);
// onUI_Timer: movePoints(pts) → pts[N-1].y = 新值 → setData(0, pts, N)

// 增量：定时器(30ms) addData 高效实时
mDiagram3Ptr->addData(0, v);   // v = 映射后的 y 值

// 动态改样式
mDiagram1Ptr->setPenWidth(0, 2);
mDiagram1Ptr->setPenColor(0, 0xFF00FF00);
mDiagram1Ptr->setXScale(0, 1.0);
mDiagram1Ptr->clear(0);        // 清空某条
```

## 样例代码
DiagramDemo-New（3 个 diagram：setData 双波+单波 / addData 串口映射波形）；lib-ai audio_waveform.cpp（PCM RMS→dB→0~31 映射，33 点滚动，20ms 节流 addData 变体）。
