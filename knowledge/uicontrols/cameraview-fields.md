---
id: uicontrols-cameraview-fields
title: 📷 CameraView 相机预览控件 JSON 字段规范
category: uicontrols
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [V85X]
tags: [平台 V85X, AW_V853, 非猜测]
evidence: []
---
# 📷 CameraView 相机预览控件 JSON 字段规范

> 检索导引：问「实时摄像头预览用哪个控件 / cameraview 字段 / formatSize 是源分辨率不是控件大小 / 画面拉伸裁剪怎么处理 / 能不能和 videoview 混用」→ 本文。
> 2026-09-03 沛哥指定 + 实测入库（LearningProject/mark_cv201 倒车影像工程，CV201_PND 1600×600 + CV201_PND_1024_600 双分辨率解包校准，平台 V85X/AW_V853）。
> 来源可靠性：ftu 解包还原 json（fui unpack 实测字段，非猜测）。

## ⚠️ 核心铁律（先分清控件，再谈布局）

1. **实时摄像头预览用 cameraview；播放文件/回放/拉流用 videoview —— 禁止混用**
   - `cameraview`（C++ 类 **ZKCameraView**，include `"control/ZKCameraView.h"`）→ 接 `/dev/video` 设备节点，实时预览/拍照/录像流，可多通道切换
   - `videoview`（ZKVideoView）→ 播放视频文件/URL，`loopPlayback`/`defaultVolume` 是它的字段（cameraview 没有）
   - mark_cv201 实测分工：**reverse（倒车实时画面）= cameraview**；reverse2（回放）/Dvr/lylinkview = videoview。UI 布局阶段先定清楚用哪个
2. **cameraview 必须嵌在 window 容器内**（实测 reverse.ftu：window__1 → cameraview__2 + painter__3 overlay），不做顶层裸控件
3. **`formatSize` 是视频源分辨率，不是控件大小**：控件铺满窗口（position 全屏），formatSize 写摄像头真实输出（如 640×480）；拉伸/裁剪适配在代码里用 setCropPosition 做（见下）

## JSON 字段表（mark_cv201 reverse.ftu 实测校准）

| 字段 | 类型/取值 | 说明 |
|------|----------|------|
| `caption` | string | 控件名（实测 `CameraViewReverse`） |
| `id` | int | 控件 id（实测 **97001**，cameraview 独立 id 段） |
| `autoPreview` | bool | **true = 自动预览**（关键，布局打开即出画面）；false 需代码 startPreview |
| `backgroundColor` | int | 背景色 0=透明/黑 |
| `cvbs` | bool | 模拟视频源（CVBS）标志，数字摄像头 false |
| `formatSize` | {height,width} | 视频源分辨率，如 640×480（**非控件尺寸**） |
| `mirror` | int | EMirror 镜像（0 正常，实测倒车默认 0） |
| `touchable` | bool | 是否响应触摸，预览层通常 false（实测 false） |
| `position` | {left,top,width,height} | 控件位置尺寸（实测全屏铺满：0,0,1600×600 / 1024×600） |
| `beepEnable` | bool | 按键音开关（1024×600 版根/窗口有 true，1600 版无——IDE 版本差异，非必需） |

完整嵌套结构（unpack 后 json）：
```json
"window__1": {
  "backgroundPic": "newmain/bg_1.png",
  "caption": "reverseWindow",
  "id": 110023,
  "position": {"left": 0, "top": 0, "width": 1600, "height": 600},
  "cameraview__2": {
    "autoPreview": true, "backgroundColor": 0,
    "caption": "CameraViewReverse", "cvbs": false,
    "formatSize": {"height": 480, "width": 640},
    "id": 97001, "mirror": 0, "touchable": false,
    "position": {"left": 0, "top": 0, "width": 1600, "height": 600}
  },
  "painter__3": {"caption": "LinePainter", "id": 52001, ...}
}
```
- 同容器常配 `painter`（id 52001）画倒车轨迹线/警戒框 overlay，叠在 cameraview 上层
- 不同分辨率工程（1600×600 vs 1024×600）**结构完全一致，只改 resolution + position**，可直接复用整套 json

## 代码操作（mark_cv201 reverseLogic.cc onUI_init 实测顺序）

```cpp
mCameraViewReversePtr->setErrorCodeCallback(&cb);  // 无信号检测（先注册）
mCameraViewReversePtr->setDevPath("/dev/videoX");  // 摄像头设备节点
mCameraViewReversePtr->setFormatSize(w, h);         // 视频源分辨率
mCameraViewReversePtr->setFrameRate(fps);           // 帧率
mCameraViewReversePtr->setRotation(rot);            // ERotation: 0/90/180/270
mCameraViewReversePtr->setMirror((EMirror)m);       // 镜像
mCameraViewReversePtr->setChannel(chn);             // 通道切换
// 防拉伸：按控件宽高比算裁剪区
const LayoutPosition &vp = ptr->getPosition();
LayoutPosition cp(0, 0, w, h);
if ((float)w / vp.mWidth > (float)h / vp.mHeight)
    { cp.mWidth = h * vp.mWidth / vp.mHeight; cp.mLeft = (w - cp.mWidth) / 2; }
else
    { cp.mHeight = w * vp.mHeight / vp.mWidth; cp.mTop = (h - cp.mHeight) / 2; }
if (rot == E_ROTATION_90 || rot == E_ROTATION_270)  // 旋转后 swap
    { std::swap(cp.mLeft, cp.mTop); std::swap(cp.mWidth, cp.mHeight); }
ptr->setCropPosition(cp);
// 生命周期
ptr->startPreview(); / stopPreview(); / isPreviewing();
```

- **无信号提示**：继承 `ZKCameraView::IErrorCodeCallback`，onErrorCode 判断 `E_CAMERA_STATUS_CODE_NO_SIGNAL` / `E_CAMERA_STATUS_CODE_HAS_SIGNAL`；计数 ≥2 次无信号才出提示（防抖），恢复有信号清零
- **页面退出防冲突**：onUI_hide 里 `WAIT(!ptr->isPreviewing(), 100, 30)` 等预览真正停止再跳转（否则同开两个相机画面会打架）
- onUI_quit 记得 `setErrorCodeCallback(NULL)` 反注册

## 常见坑

- **实时预览黑屏/不出画** → ①布局忘了 `autoPreview: true` ②没 setDevPath/setFormatSize ③设备节点被占用（同时开了两个 cameraview 页面）
- **画面拉伸变形** → 没做 setCropPosition 等比裁剪，或旋转 90/270 没 swap
- **误用 videoview 做实时预览 / 误用 cameraview 播文件** → 都不出画面，先按铁律 1 分控件
- **倒车切页卡死/黑屏** → 页面 hide 时预览没停干净，用 WAIT(!isPreviewing()) 防同开冲突
- **平台**：实测 V85X（AW_V853）；F133/其他平台是否支持以官方文档为准，不确定先查知识库/问沛哥

## 相关

- V85X MPP 完整 API 汇总：`references/kb/v85x-mpp.md` §① ZKCameraView 控件用法
- UVC 摄像头接入（发现/取流/双路预览/录像拍照）：`references/kb/v85x-uvc-camera.md`、`knowledge/v85x/uvc-usb-camera.md`
