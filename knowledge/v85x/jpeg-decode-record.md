# V85X JPEG 硬件解码与 MJPEG 录像编码用法（V853 照片显示 / UVC 录制 mp4/ts）

> 🔍 **检索导引**：V853/V85X「**JPEG 硬件解码**」「**MJPEG 摄像头转码录制 mp4**」「**UVC 摄像头录像**」「**照片显示**」「**录像格式 mp4/ts/avi**」「**DVR 录制/拍照**」问题。
> 沛哥 2026-09-07 定规：**只记录怎么用**；aw-dvr/aw-mpp 预编译闭源内部（MJPEG→H264 转码实现）不解析不深挖。
> 来源：CV201_PND（mark_cv201）实测 + aw-dvr 3.13.12 / aw-mpp 2.0.2 头文件。

## 场景总览（两个方向分开处理）

| 场景 | 方向 | 典型需求 | 用什么 |
|------|------|---------|--------|
| **① 解码** | JPEG/MJPEG → YUV/屏幕 | 看照片/相册、UVC 预览、取帧做算法 | `mpi::JpegViewer`（显示）/ `jpegdecode.h`（拿像素） |
| **② 编码（录制）** | 摄像头流 → 文件 | DVR 录像（内置/UVC 摄像头）、循环录像 | `mpi::Recorder`（视频 mp4/ts 两档） |

**不要混**：显示照片走解码（JpegViewer），录像走编码（Recorder）；MJPEG 摄像头流录制 = 编码场景，走 Recorder，与单张 JPEG 解码无关。

---

## ① 解码场景（JPEG 显示/取像素）

### 1.1 照片显示：mpi::JpegViewer（推荐，DvrPlayLogic 实测）

```cpp
#include <mpi/case/jpeg_viewer.h>
#include <mpi/case/camera.h>        // initPlayerEnv / mpi::VO

// 延迟初始化（避免与预览 MPP 冲突）
vo_dev = initPlayerEnv();                                   // mpi::VO 显示环境
jpeg_viewer = std::make_shared<mpi::JpegViewer>(*vo_dev);   // 绑定 VO

// 显示 JPEG 照片 → 指定屏幕区域（硬件解码出图）
jpeg_viewer->start(file, {pos.mLeft, pos.mTop, pos.mWidth, pos.mHeight});

// 停止 / 切换（先停显示再放视频）
jpeg_viewer->stop();
```

DvrPlayLogic 分流：`FILE_TYPE_PHOTO`（jpg/jpeg/png/bmp）→ JpegViewer 显示；
`FILE_TYPE_VIDEO` → `mVideoView1Ptr->play(file)`。切换前 `mVideoView1Ptr->stop()` + `jpeg_viewer->stop()` 都调。

### 1.2 取像素：jpegdecode.h（libcedarc C API，要裸数据时）

```c
JpegDecoder* JpegDecoderCreate();
void JpegDecoderSetDataSource(JpegDecoder* v, const char* pUrl,
     JpegDecodeScaleDownRatio scaleRatio, JpegDecodeOutputDataType outputType);  // 文件
void JpegDecoderSetDataSourceBuf(JpegDecoder* v, char* buffer, int bufLen,
     JpegDecodeScaleDownRatio scaleRatio, JpegDecodeOutputDataType outputType);  // 内存
ImgFrame *JpegDecoderGetFrame(JpegDecoder* v);   // mYuvData/mRGB565Data + 实际宽高
void JpegDecoderDestory(JpegDecoder* v);
```

- 缩放：`JPEG_DECODE_SCALE_DOWN_1/2/4/8`（解缩略图用 4/8，省带宽）
- 输出：`NV21/NV12/YU12/YV12/RGB565`；`ImgFrame.mDisplayWidth/Height` 是实际尺寸
- 头文件：`src/dependencies/include/jpegdecode.h`（随项目依赖带出）

---

## ② 编码场景（录制）

### 2.1 格式口径（沛哥 2026-09-07 定）

- **V85X 带编码器，录制默认支持 `mp4` / `ts` 两种格式**（aw-dvr `FileFormat { JPEG, TS, MP4 }`，
  `recorder.h` 注明视频仅 TS/MP4；`MEDIA_FILE_FORMAT_E` 另有 mp3/aac/wav/raw 音频类）
- **客户要其他格式（如 AVI）→ 提示客户**：默认只出 mp4/ts；AVI 属**大文件格式**（体积大），
  确认客户是否接受再走 AVI 方案，不默认承诺
- 设备端回放/取文件按格式类型筛：`Recorder::getFiles((mpi::FileFormat)type, view, lock, ...)`

### 2.2 mpi::Recorder 用法（DvrLogic/camera_helper 实测）

```cpp
#include <mpi/case/recorder.h>
#include <mpi/case/camera.h>

// 录像参数（多路）：FRONT 内置 + REAR UVC（有 UVC 才加）
mpi::RecordingSettings s;
s.duration = 30;                 // 循环录像每段秒数
s.audio = sys::setting::is_dvr_record_sound_enabled();
s.bitrate = 12 * 1024 * 1024;    // 12Mbps
s.frame_rate = 25;
s.size = {1920, 1080};           // 或 1280x720（分辨率档决定）
// s.video_format = mpi::FILE_FORMAT_MP4;  // 默认 TS，可切 MP4

mpi::RecorderParameters p;
p.settings[mpi::VIDEO_DEVICE_FRONT] = s;              // 内置 ISP 摄像头
p.settings[mpi::VIDEO_DEVICE_REAR]  = s2;             // UVC（有才加）

// 起停（DvrLogic 录按钮）
mpi::Recorder::instance().start(p);
mpi::Recorder::instance().stop();
mpi::Recorder::instance().state();       // UNSTARTED/RECORDING/EXCEPTION
mpi::Recorder::instance().elapseTime();  // 当前段已录毫秒
mpi::Recorder::instance().isLocked();    // 锁定文件（紧急录像）
```

### 2.3 UVC MJPEG 摄像头 → Recorder（CV201_PND 全链路，怎么用）

```
UVC MJPEG 摄像头 (/dev/videoX)
 → CameraHelper::Init() 注册 REAR 通道 setUvc(true) + setPictureSize(uvc实际宽高)
 → UvcCameraDetection（SharedVideoDevice(REAR) 持续读流保活，防休眠断流）
 → mpi::Recorder::start(makeRecorderParam())：settings[FRONT] + settings[REAR] 双路落盘
 → USB 断开：先 Recorder::stop() + RearCamera::stop() 再重建（MPP 互斥）
```

代码位：
- 注册：`src/uvc/camera_helper.cpp`（FRONT setIsp(true).setId(0)；REAR setUvc(true).setId(DEVICE_ID_AUTO)）
- 参数：`camera_helper.cpp` makeRecorderParam()（duration/audio/bitrate 12Mbps/25fps/720P|1080P）
- 起停：`src/logic/DvrLogic.cc`（录按钮 → start/stop）
- 断流：`src/uvc/uvc_camera.cpp`（状态机 USB_DISCONNECTED → stop record + stop camera + 重建）
- 保活：`src/uvc/uvc_camera_detection.cpp`（SharedVideoDevice 循环 wait()）

### 2.4 拍照（不属于录像，但同 MPP 体系）

拍照走 `mpi::Snapshot::instance().takePicture(names, {})`（**不是** `Recorder::takePicture`），
200ms 防抖 timer；产物 JPEG → 相册 → 解码场景 JpegViewer 回看。闭环：Recorder(录) ↔ Snapshot(拍) ↔ JpegViewer(看)。

---

## 坑（实测）

1. **Recorder 与预览互斥**：拔插 UVC/切流/进回放前先 `Recorder::stop()` + `RearCamera::stop()`，否则 MPP 冲突
2. **UVC 必须持续读流保活**：取流任务不能停久，否则休眠断流；接入成功先保活再开预览
3. **显示照片前先停视频**，反之亦然（`mVideoView1Ptr->stop()` 和 `jpeg_viewer->stop()` 成对）
4. **录像格式别承诺 mp4/ts 以外**：客户要 AVI 等 → 提示大文件格式，确认后再做
5. **aw-dvr 内部转码实现不深挖**（闭源预编译）；按上面 API 用即可，遇到异常看 mpi::Exception 信息
6. JpegViewer 分辨率/区域用 `Rectangle{left,top,w,h}` 指定屏幕显示区

## 依赖与来源

- 依赖包：aw-dvr（mpi::Recorder/JpegViewer/Camera/VO/Snapshot）、aw-mpp（MPP 底层）
- 头文件：`~/.fuse/registry/public/v85x/aw-dvr/3.13.12/include/mpi/case/{recorder,config,jpeg_viewer,camera}.h`、
  `aw-mpp/2.0.2/.../mm_common.h`（MEDIA_FILE_FORMAT_E）
- 工程实测：CV201_PND `src/{logic/DvrLogic,DvrPlayLogic}.cc`、`src/uvc/*.cpp`、`src/media/media_context.cpp`
- 平台：V85X（AW_V853/AWCHIP=AW_V853）；其他平台 DVR 封装不同（无 aw-dvr，走 ZKCameraView）
