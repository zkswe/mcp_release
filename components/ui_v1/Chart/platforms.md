# platforms.md —— Chart 逐平台说明

> 口径：**没实测的一律写 `未验证`**。组件只用到 `easyui` 的 `ZKPainter + ZKTextView`，
> 差异主要在 **painter 的绘制口径**（尤其 `drawArc` 的角度/顺逆）与**平台是否有 GPU**（影响重绘耗时）。
>
> ⚠️ 文档里的设备地址（`192.168.1.100:5555`）是**通用示例**，不是真机 IP；真机清单在开发工作区
> （`references/kb/devices.md`），**不进发布包**。

## Z21（1024×600 横屏）

> **0.2.1 修正**：Y 轴刻度文字槽位与网格线对应反了（槽位 0 = max 却画在最下线）——0.2.1 已修，真机重抓 `evidence/01`；自绘时**记得「槽位顺序 = 从上到下」**。
>
> **0.2.0 分段环**：`setRingSegments / clearRingSegments / hasRingSegments` 在 Z21 真机实测通过（`drawArc` 角度口径与进度环一致：0 度 = 正上方、顺时针为正；段间 2° 缝隙肉眼可见）。

| 项 | 值 |
|---|---|
| 可用性 | ✅ **可用（已真机验收）** |
| 实测 easyui | 设备 `/lib/libeasyui.so`（805,680 B，2024-07-10）；开发侧链接 registry **easyui 2.6.0** |
| `drawArc` 口径（实测） | **0 度 = 正上方，顺时针为正**（源 LVGL 是 3 点钟方向为 0，转换时要减 90）——本组件内部已按平台口径算 |
| 无 alpha | `setSourceColor` 只有 0xRRGGBB → 半透明一律 `Chart::mix()` 混底色近似 |
| 无 GPU / 无硬解 | 纯 CPU 光栅。实测：4 张图（12 折点 + 12×2 柱 + 3 环 + 20 刻度）一次全刷，整屏 diff 39,489 px，肉眼无卡顿 |
| 前置条件 | `/tmp` 可写（`/res` 是 squashfs 只读）；⚠️ `/data` 已满，别推文件到 `/data` |
| 已知限制 | ① fb 双缓冲（`virtualHeight=1200`）：应用固定渲染到 offsetY=600 那一半（offsetY=0 是黑的），抓屏必须按读到的 `pan` 取帧，否则比对的是黑屏/旧帧 → 会得出「图没重绘」的错结论；② **反复 `fun launch` / `kill -9 zkgui` 重启若干次后，触摸注入会「命令成功、应用不响应」**（`touch` 打印 `tap (x,y)`、应用无反应）——⚠️ **重启板子才能恢复**（实测 2026-09-16；与组件无关，是本机输入子系统的状态问题） |
| 真机验收命令 | `fun build -p Z21` → `fun launch -p Z21 -s 192.168.1.100:5555` → `touch tap 805 28` → 抓屏 + `ui_diff.py` |

## F133（1280×800，rotate 270/270）

| 项 | 值 |
|---|---|
| 可用性 | ⚠️ **未验证（仅编译通过）** |
| 依据 | 同代 `easyui 2.9.0` 的 `ZKPainter.h` 公开面与 2.6.0 **完全一致**（`setLineWidth/setSourceColor/drawTriangle/drawRect/drawArc/fillTriangle/fillRect/fillArc/drawLines/drawCurve/erase`）；组件无平台宏 |
| 前置条件 | `package.properties` 写 `{"rotateScreen":270,"rotateTouch":270}`；SD 部署 `/mnt/extsd/{lib,ui}` |
| 未验证项 | 真机重绘耗时、`drawArc` 角度是否与 Z21 同口径（**同代 easyui，推断一致但未实测**） |

## Z20 / T113 / V85X

| 平台 | 可用性 | 依据 |
|---|---|---|
| Z20 | ⚠️ **未验证** | registry `z20/easyui/2.6.0`、`3.0.0` 的 `ZKPainter.h` 公开面一致 |
| T113 | ⚠️ **未验证** | registry `t113emmc/easyui/2.9.0` 一致 |
| V85X | ⚠️ **未验证** | registry `v85x/easyui/2.3.0`、`2.9.0` 一致；V85X 有较多内存/带宽限制，密集点阵（如 PRPS 那种每格一个 fillArc）**先在真机量一遍再上** |

## 跨平台注意事项（平台通用）

1. **坐标系是「控件局部」**：`painter->getPosition()` 返回的是 painter 在**父容器**里的矩形；
   绘制 API 用**局部坐标**（左上角 = 0,0），而刻度文字控件是父容器里的兄弟 → 组件用
   `mOx/mOy`（= painter 的 left/top）给文字加偏移。**换了父容器层级不用改代码**，但文字必须和 painter 同父。
2. **painter 不自动重绘**：所有平台一致（没有 LVGL 的 `invalidate` → 框架合成）。改数据必 `refresh()`。
3. **`erase()` 是必要的**：只画不擦会留下上一帧的残留（折线变"蜘蛛网"）。组件在 `refresh()` 里先整块 `erase`。
4. **别在 100ms 定时器里全刷多张图**：CPU 光栅，成本随像素线性涨；只在图**可见**时刷（参考 `logic-map.md` 的定时器口径）。
