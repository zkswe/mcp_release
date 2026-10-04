---
title: V85x 摄像头/DVR（MPP 用法）
---

# V85x（V553/V853）摄像头与 DVR：MPP 用法

> 适用平台：**V85X**（Manifest `platform="V85X"` + 编译宏 `AWCHIP=AW_V853`）。
> 本文内容只关联 V85x 平台；F133/T113/Z20 的摄像头走 ZKCameraView 但 MPP 封装包不同（无 aw-dvr）。

## 依赖包（V85X Manifest 关键项）

```xml
<manifest cyclicDependency="true" platform="V85X">
  <compiler><macro>AWCHIP=AW_V853</macro></compiler>
  <dependencies enableOnPlatforms="V85X">
    <package id="easyui" version="0.0.0"/>
    <package id="aw-middleware" version="0.0.0"/>
    <package id="aw-system" version="0.0.0"/>
    <package id="aw-isp" version="0.0.0"/>
    <package id="aw-dvr" version="最新版" accessKey="向中科世为申请"/>
    <package id="base-utility" version="4.0.2+"/>
  </dependencies>
</manifest>
```

- **aw-dvr** 是 V85x 摄像头/DVR 的核心 MPP 封装包（`mpi::` 命名空间），accessKey 私有包
- 版本策略：默认拉最新版即可，此类包与其他产品无关联、版本向下兼容，不必锁旧版

## 三层架构（从控件到代码）

```
① ZKCameraView 控件（easyui 内置，单摄像头调试/预览）
      ↓ setDevPath/setFormatSize/setFrameRate/setRotation/setCropPosition/setChannel
② mpi:: C++ 封装（aw-dvr 包，多路 DVR）
      ↓ mpi::Recorder / FrontCamera / RearCamera / LeftCamera / RightCamera / VO / JpegViewer
③ AllWinner MPP 底层（V853 编解码硬件，H.264/H.265 1080p@60fps 编码）
```

头文件：`<mpi/case/front_camera.h>` `<mpi/case/recorder.h>` `<mpi/case/rear_camera.h>` `<mpi/case/jpeg_viewer.h>` `<mpi/module/vo.h>`，均用 `mpi::` 前缀，异常走 `mpi::Exception`。

## ① ZKCameraView 控件用法（单摄像头调试）

```cpp
mCameraView1Ptr->setDevPath("/dev/video4");        // 摄像头节点
mCameraView1Ptr->setFormatSize(w, h);              // 分辨率
mCameraView1Ptr->setFrameRate(fps);                // 帧率
mCameraView1Ptr->setRotation(rot);                 // ERotation: 0/90/180/270
mCameraView1Ptr->setCropPosition(pos);             // 裁剪区域（LayoutPosition 缩放）
mCameraView1Ptr->setChannel(index);                // 4路通道切换
mCameraView1Ptr->startPreview(); / stopPreview(); / isPreviewing();
mCameraView1Ptr->takePicture();                    // 拍照 → IPictureCallback 保存
mCameraView1Ptr->startStream(); / stopStream();    // 视频流
mCameraView1Ptr->setBrightness/Contrast/Saturation/Sharpness/Hue(int);
mCameraView1Ptr->setErrorCodeCallback(&cb);        // 无信号检测
mCameraView1Ptr->setPictureCallback(&cb);          // onPictureSavePath/onPictureTakenEnd
```

### 旋转 + 裁剪（缩放）核心写法

```cpp
// 跟随屏幕旋转（EasyUI.cfg rotateScreen）
ERotation rot = (ERotation)(CONFIGMANAGER->getScreenRotate() / 90);
mCameraView1Ptr->setRotation(rot);
int w = cam_w, h = cam_h;
if (rot == E_ROTATION_90 || rot == E_ROTATION_270) std::swap(w, h);  // 旋转后宽高互换
LayoutPosition pos = {0, 0, w, h};
mCameraView1Ptr->setCropPosition(pos);
```

### 环境变量

| 变量 | 作用 |
|------|------|
| `ZKCAMERA_DI_ENABLE` | 1/0 开启关闭奇偶合并（N制P制隔行转逐行） |
| `ZKCAMERA_SKIP_FRAMES` | 打开后跳过前 N 帧不稳定图像（默认 3） |
| `ZKCAMERA_ALIGN_HEIGHT` | 对齐高度（16） |

## ② mpi::Recorder 录像

```cpp
#include <mpi/case/recorder.h>
mpi::Recorder::instance().start(sys::setting::makeRecorderParam());  // 开录
mpi::Recorder::instance().stop();
mpi::Recorder::instance().isStarted();
mpi::Recorder::instance().state();        // UNSTARTED/RECORDING/EXCEPTION
mpi::Recorder::instance().elapseTime();   // 已录毫秒 → UI 时间
mpi::Recorder::instance().isLocked();     // 当前片段是否锁定
mpi::Recorder::instance().lockNext(bool); // 锁定/解锁下一段（紧急录像）
mpi::Recorder::instance().takePicture(bool rear);  // 拍照（建议 200ms 防抖）
mpi::Recorder::instance().getFiles(type, view, lock, true, true);  // 文件列表
mpi::Recorder::instance().lockFile(file) / unlockFile(file);       // 回放页锁定/解锁
```

### 录像分辨率

```cpp
enum resolution_mode_e { E_RESOLUTION_MODE_720P_720P, E_RESOLUTION_MODE_1080P_1080P, E_RESOLUTION_MODE_2_5K_720P };
// UI 档位：1080P / 2K / 4K
E_RESOLUTION_MODE_720P_720P   → front_video {1920,1080}, rear_video {1920,1080}
E_RESOLUTION_MODE_1080P_1080P → front_video {2560,1440}, rear_video {1920,1080}
E_RESOLUTION_MODE_2_5K_720P   → front_video {3840,2160}, rear_video {1920,1080}
```

- 分段时长 `duration_per_file`：60 / 180 / 300 秒
- 录音：`param.audio.enable`
- 分辨率切换后必须重启录像（restartRecorder(true)）才生效

## ③ 多路摄像头（四路拼接）

四路各自独立单例，可同时打开，每路 `setParam(CameraParam, is_sync)` 配置：

```cpp
mpi::FrontCamera::instance();  // 前视
mpi::RearCamera::instance();   // 后视
mpi::LeftCamera::instance();   // 左视
mpi::RightCamera::instance();  // 右视
```

### 四路同屏（2×2 拼接）核心写法

```cpp
case VIEW_TYPE_FOURWAY: {
  mpi::CameraParam param;
  { // 前视 → 左上
    param.mirror = false;
    param.viewbox = {0, 0, 1920, 1080};      // 源裁剪区（1920×1080 全幅）
    param.display = {0, 0, 512, 300};        // 目标显示区（1024×600 左上 1/4）
    param.visible = true;
    mpi::FrontCamera::instance().setParam(param, is_sync);
  }
  { // 后视 → 右上（后视镜像可选）
    param.mirror = sys::setting::is_rear_mirror();
    param.viewbox = {0, 0, 1920, 1080};
    param.display = {512, 0, 512, 300};      // 右上 1/4
    param.visible = true;
    mpi::RearCamera::instance().setParam(param, is_sync);
  }
  { // 左视 → 左下
    param.mirror = false;
    param.viewbox = {0, 0, 1920, 1080};
    param.display = {0, 300, 512, 300};      // 左下 1/4
    param.visible = true;
    mpi::LeftCamera::instance().setParam(param, is_sync);
  }
  { // 右视 → 右下
    param.mirror = false;
    param.viewbox = {0, 0, 1920, 1080};
    param.display = {512, 300, 512, 300};    // 右下 1/4
    param.visible = true;
    mpi::RightCamera::instance().setParam(param, is_sync);
  }
}
break;
```

### ViewType 枚举

```cpp
enum ViewType {
  VIEW_TYPE_FRONT = 0, VIEW_TYPE_REAR = 1,
  VIEW_TYPE_LEFT = 2, VIEW_TYPE_RIGHT = 3,
  VIEW_TYPE_FOURWAY = 4,      // 2×2 四路同屏
  VIEW_TYPE_UNVISIBLE = 5,
  VIEW_TYPE_REVERSE,
  VIEW_TYPE_FRONT_MINI,       // 小窗（如互联时右下角 300×196 悬浮预览）
  VIEW_TYPE_REAR_MINI,
};
```

### 四路拼接要点

- **display = 屏幕目标矩形**（x, y, w, h），四路各占一格即拼接；**viewbox = 源裁剪矩形**（1920×1080 全幅，可裁剪/平移）
- 单路模式：其余三路 `setVisible(false, false)` 关闭（false=不同步，避免卡顿）
- 小窗（FRONT_MINI/REAR_MINI）：display {76, 158, 300, 196} 悬浮窗预览
- 切视图手势：左右滑动 `nextViewType()/prevViewType()`，FOURWAY 时禁止拖动平移
- 切换入口封装为 `setupCamera(ViewType, bool)`，内部 switch 各 ViewType 配置各路 param/visible

## ④ 拍照回放

```cpp
mpi::initializeSystem();                      // 初始化 MPP 系统
auto vo = std::make_shared<mpi::VO>(0);       // 视频输出层
vo->enable();
VO_PUB_ATTR_S attr = vo->getAttr();
attr.enIntfType = VO_INTF_LCD; attr.enIntfSync = VO_OUTPUT_NTSC;
vo->setAttr(attr);

auto jpeg_viewer = std::make_shared<mpi::JpegViewer>(*vo);  // 照片查看器
jpeg_viewer->start(file, {l, t, w, h});       // 显示 JPG 到指定区域
jpeg_viewer->stop();

mVideoView1Ptr->play(file.c_str());           // ZKVideoView 播录像
mVideoView1Ptr->stop() / pause() / resume() / seekTo(ms);
mVideoView1Ptr->getDuration() / getCurrentPosition();
```

- 文件分类：`mpi::FileType` = FILE_TYPE_VIDEO / FILE_TYPE_PHOTO；`mpi::VIEW_FRONT` / `VIEW_REAR`
- 回放页：普通视频 / 锁定视频（SOS）/ 照片 三个页签，切换即重新 loadFiles() 并自动播第一个
- 进度条：SeekBar → handler 延迟 150ms 发消息 → seekTo（防抖）
- 删除：多选后删除文件；锁定/解锁走 `lockFile/unlockFile`

## ⑤ 铁律

1. **aw-dvr / aw-* 包仅 V85X 平台**；T113/F133 没有，别跨平台抄依赖
2. **MPP 冲突**：预览/录像/回放互斥，切页前必须 stop 对应的 camera/recorder/player
3. **回放延迟初始化**：进回放页用 50ms 定时器再 init VO，避免与录像抢占 MPP 资源
4. **aw-dvr 是 accessKey 私有包**：新工程要用必须带 accessKey，否则拉不到
5. **分辨率切换要重启录像**（restartRecorder(true)），否则不生效
6. **takePicture 加防抖**（200ms）防止连点卡死
7. UI 档位（1080P/2K/4K）与实际编码分辨率映射在 makeRecorderParam，改档位要同步改这张表
8. 手势缩放走 viewbox（1920×1080 逻辑分辨率），不是控件级缩放；单路调试才用 setCropPosition
