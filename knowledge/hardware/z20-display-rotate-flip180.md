---
id: hardware-z20-display-rotate-flip180
title: Z20 整屏 + 视频层旋转（倒装 180°）口径
category: hardware
status: review
confidence: manual
verified_at: 2026-09-30
stale_days: 180
origin: partial
source: 2026-09-27 SmartPanel_HA 设备倒装需求（）+ Z20 真机取证（fb0 像素比对 + mi_disp rotatemode A/B）
needs_evidence: true
platforms: [Z20]
tags: [倒装, 屏幕旋转, 触摸旋转, 视频层旋转, 屏幕方向, 180度, 安装方向]
evidence:
  - "UI/触摸映射：easyui 运行库反汇编（zk_disp_set_rotate / zk_event_set_touch_rotate）"
  - "视频层自证：/proc/mi_modules/mi_disp/mi_disp0 的 rotatemode 字段 A/B 对比 + MI_DISP_SetVideoLayerRotateMode 返回 0"
  - "UI 层像素：/dev/fb0 抓帧逐像素比对（工程内脚本 flip_rot_cmp.py）"
---
# Z20 整屏 + 视频层旋转（倒装 180°）口径

> 检索导引：倒装 / 倒挂 / 装反了 / 屏装倒了（180°）/ 整屏旋转 / 触摸坐标反了 / 点按位置不对 /
> 画面转了触摸没转 / 视频方向不对 / 拼墙倒装后画面方向 / setScreenRotate / setTouchRotate /
> MI_DISP_SetVideoLayerRotateMode / `rotatemode` / 视频层不在 fb0 怎么核验 / 一键倒装开关。
> 用途：面板**物理倒装**（旋转 180°）时的三层口径：① UI ② 触摸 ③ **视频层**（独立于 fb0，必须单独转）。
> 典型场景：86 面板吸顶/倒挂安装、多屏拼接墙其中一台装反。

## 1. 一句话结论

**UI 走 easyui `CONFIGMANAGER->setScreenRotate(rot)`；触摸走 `setTouchRotate(rot)`；视频层走 MI
`MI_DISP_SetVideoLayerRotateMode(layer, cfg)`；三者必须一起转，视频层方向用 `mi_disp` proc 的
`rotatemode` 自证（`/dev/fb0` 里看不到视频层）。**

## 2. UI + 触摸（easyui，rot = 0/90/180/270）

```cpp
CONFIGMANAGER->setScreenRotate(180);   // -> zk_disp_set_rotate(rot/90)，随后全屏重绘
CONFIGMANAGER->setTouchRotate(180);    // -> zk_event_set_touch_rotate(rot/90)，点按位置与显示一致
```

- 底层走系统 disp 驱动的 `set_rotate` 钩子；**只有 90/270 才交换宽高**，
  180/0 不交换 → **正方形面板（如 480×480）180° 不需要第二套布局**（老 easyui 也没有 `relayout`，
别为倒装去做两套 ftu）。
- **调用时机**：驱动初始化前的调用会被丢弃（fbdev 未 init 直接 return）→ 不要放
  `Main.cpp:onEasyUIInit`，放在**首页（屏保页）`onUI_init`**最稳（画面已起，重绘生效）。
- 触摸：转屏后**注入坐标按物理屏坐标给**即可（同角度映射），不要手工换算。
- 切换时**先停播放器 → 改旋转 → 再起播放器**；播放中改图层属性会踩坏 disp 通道。

## 3. 视频层（MI，必须单独转）

```cpp
#include "mi_disp.h"
MI_DISP_RotateConfig_t cfg; memset(&cfg, 0, sizeof(cfg));
cfg.eRotateMode = E_MI_DISP_ROTATE_180;      // NONE=0 / 90=1 / 180=2 / 270=3
MI_DISP_SetVideoLayerRotateMode(0, &cfg);    // 返回 0 = OK
```

- **层号怎么定**：读 `/proc/mi_modules/mi_disp/mi_disp0`，看视频在哪个 `LayerId`——表里的
  “ChnId” 是**输入端口序号**不是层号；实测 easyui `ZKVideoView`（v4 引擎）与自建 MI 播放器
  （simple 引擎）**都在 LayerId 0**，只是输入端口不同 → **一条层级调用覆盖两条引擎**。
- 若播放器每次起播都会重新下发自己的旋转配置 → 让“配置 → 停 → 由心跳重起”这条路径生效最稳。

## 4. 怎么证明生效（视频层不在 fb0！）

| 手段 | 命令 / 位置 | 说明 |
|---|---|---|
| 图层属性（客观自证，推荐） | `cat /proc/mi_modules/mi_disp/mi_disp0` → `LayerId … rotatemode` | 开 = `rotate_180`，关 = `NONE`；两台设备可做 A/B |
| API 返回码 | 日志打 `MI_DISP_SetVideoLayerRotateMode(layer, mode) -> 0` | 0 = OK |
| UI 层 | `dd if=/dev/fb0` 抓帧 → PNG | fb0 **只有 UI 层**；把“开启后/开启前”两帧比像素（含整体 180° 旋转 + 差异应只剩改动控件） |
| 视频画面方向 | **只能相机拍屏**（或 `device_screenshot(layer='video')` 取 vdec 帧看画面） | fb0 抓不到合成后的视频层 |
| 解码质量回归 | `zkshot <out.raw> vdec <chn> 0` → 算块度 | 判据 ≤1.2（源帧 1.05~1.25） |

## 5. 坑清单（都踩过）

1. **fb0 是多缓冲**（本板 3 块），别只比一块面板就判“没反应”；块内容在缓冲间轮转。
2. 改 `ui/*.json` 后**必须 `fui pack` 出 ftu 再编译**（`generated/ui_*.cpp` 由 ftu 生成，
只改 json 会报控件指针未声明）。
3. **源码注释别用 emoji / 特殊字符**（`check_all` 的特殊字符项会把 `⚠️` 之类判 FAIL）。
4. 拼墙 + 倒装同时开时，相位判据要**按同一时刻（now）配对**再比 pts（按 `(cyc,pts)` 配，
跨轮会出现“恰好差一个周期”的假差异）。
5. 倒装开关**要落 prefs**（掉电保持），设置页改完别忘了 `setInvalid` 触发重绘。

## 6. 相关

- 同步/拼墙：`knowledge/devflow/video-wall-sync.md`
- 设备抓帧（视频层在 vdec chn 1）：`knowledge/devflow/device-screenshot.md`
- 运行时换布局（`relayout`，需 easyui ≥ 2.9.0，与倒装是两件事）：`knowledge/devflow/dynamic-screen-rotation.md`
- 版本 → 能力判定：`knowledge/devflow/easyui-version-capability.md`
