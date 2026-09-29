---
id: v85x-uvc-usb-camera
title: V85X USB 摄像头（UVC）接入 + 预览/录像/拍照（V85X 平台绑定实现）
category: v85x
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [V85X]
tags: [**未指定平台, 其他平台, T113, F133, Z20, Z21]
evidence: []
---
# V85X USB 摄像头（UVC）接入 + 预览/录像/拍照（V85X 平台绑定实现）

> 🔍 **检索导引（命中条件）**：用户指定 **V85X 平台** + 「UVC / USB 摄像头接入 / 预览 / 拍照 / 录像 / 回放 / JPEG/MJPEG」→ 本篇为**平台绑定实现**；
> **未指定平台 / 其他平台（T113/F133/Z20/Z21）问 UVC 接入** → 先读 `hardware/uvc-camera-generic.md`（平台无关通用层：发现/协商/保活/状态机/JPEG 必查清单）。
> 来源：V85X 平台通用 UVC 接入实测（2026-09-03 学习收录，沛哥 2026-09-07 转正；2026-09-08 去工程化，纯通用形态）。
> 平台：V85X（AW_V853），aw-dvr 3.13.12 / aw-mpp 2.0.2。
> 场景：**V85X 主机通过 USB 接入 UVC 摄像头**，与内置 ISP 前摄像头双路共存：预览/录像/拍照。
> 本文为 V85X aw-dvr/mpi:: **绑定层**（MPP 注册/双路预览/Recorder/Snapshot）；平台无关的 UVC 通用逻辑（inotify 发现、
> V4L2 格式协商、持续取流保活、状态机设计、JPEG 摄像头防坑清单）见 `hardware/uvc-camera-generic.md`。
> ⚠️ 通用 JPEG(MJPEG) UVC 摄像头接入前**必读硬件通用篇 §5 落地必查清单**（格式协商/尺寸对齐/互斥顺序/保活），否则易出录制绿屏、录制中黑屏。

## 0. 接入主链路（通用，任意 UVC 摄像头可抄）

```
USB UVC 摄像头（免驱，uvcvideo 驱动）
   ▼
 /dev/videoN（热插拔 inotify 发现）
   ▼
 mpi::SharedVideoDevice(VIDEO_DEVICE_REAR).getFileDescriptor()  ← 拿到 V4L2 fd 交给 mpi
   ▼
 mpi::RearCamera（预览，layer 叠加）/ mpi::Recorder（录像）/ mpi::Snapshot（拍照）
```

**双路共存**：`VIDEO_DEVICE_FRONT` = 内置 ISP sensor（如 1920×1080，layer0 全屏），
`VIDEO_DEVICE_REAR` = **UVC 外接**（setUvc(true)，layer4 半屏/叠加）——后路通道让给 UVC。
`CameraHelper::isUvcCameraConnected()` 由状态机 NORMAL 决定（见 §5）。

> 📐 显示分层权威口径（沛哥 2026-09-07 补充）：
> ① **UI 层在最顶上**，disp 视频层按 **4、3、2、1** 叠在 UI 下方；
> ② **layer 编号 = disp 硬件层号**（不是 mpi 逻辑层）——FrontCamera→layer0、UVC RearCamera→layer4 是工程绑定；
> ③ **VI→VO 是内部处理，不需要关心**：取流→VI→VO 视频层的数据搬运由 mpi/aw-dvr 内部完成，应用只配 CameraParam。

## 1. UVC 设备发现（inotify + uvcvideo 驱动匹配）

```cpp
#define VIDEO_DEV_MAX 12
std::string get_uvc_dev() {
    for (int i = 0; i <= VIDEO_DEV_MAX; i++) {
        sprintf(dev, "/dev/video%d", i);
        if (access(dev, F_OK) != 0) continue;
        if (!_query_video_info(dev, &cap)) continue;   // open + VIDIOC_QUERYCAP
        if (strcmp("uvcvideo", (const char*)cap.driver) == 0) return std::string(dev);
    }
    return "";
}
```

- 后台线程 `inotify_init` + `inotify_add_watch("/dev", IN_CREATE|IN_DELETE)`，
  文件名 `regex_match("video\\d*")`：
  - **IN_CREATE**：当前无设备才触发，**延时 ~3s** 再枚举（等内核枚举完成，太早 open 失败；
    UVC 常建多个 videoN，用「无设备才触发」防重复处理）
  - **IN_DELETE**：删除节点 == 当前记录节点 → 关设备（先停录像/预览/取流任务），清状态广播断开
- 命中后：`mpi::SharedVideoDevice dev(VIDEO_DEVICE_REAR); fd = dev.getFileDescriptor();`
  记下节点 → 启动取流任务 → 状态置正常广播

## 2. 打开与初始化（一次，幂等）

```cpp
void initializeUvcCamera(std::string device) {
    if (CameraHelper::getInstance().isInit()) return;    // 只初始化一次
    int fd = open(device.c_str(), O_RDONLY);
    struct v4l2_capability cap; _query_video_info(...);  // driver/card/bus_info 打印调试
    struct v4l2_format fmt; fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    ioctl(fd, VIDIOC_G_FMT, &fmt);                       // 读摄像头默认分辨率
    CameraHelper::getInstance().Init(fmt.fmt.pix.width, fmt.fmt.pix.height);
    close(fd);
}
```

CameraHelper::Init(w, h) 关键（幂等，isInit 早退）：
1. **MPP 注册**：
   ```cpp
   mpi::VideoDeviceRegistry::instance().add(mpi::VIDEO_DEVICE_FRONT)
       .setIsp(true).setFrameRate(25).setPictureSize({1920,1080}).setId(0);
   mpi::VideoDeviceRegistry::instance().add(mpi::VIDEO_DEVICE_REAR)
       .setFrameRate(25).setPictureSize({w, h})          // = UVC 默认分辨率
       .setUvc(true).setId(mpi::DEVICE_ID_AUTO);         // ⚠️ UVC 走 REAR + 自动绑定
   mpi::config().apply();
   ```
2. 需要逐帧业务（OSD/检测/取帧尾数据等）时挂
   `mpi::VideoFrameInterceptor::filter(REAR, [](const VIDEO_FRAME_S* raw){ ... return true; })`；
   耗时不阻塞取流回调（handler/线程转发）

## 3. 持续取流保活（关键）

```cpp
class UvcCameraDetection: public mpi::Task<> {
  virtual void doTask() override {
    while (isStarted()) {
      try {
        mpi::SharedVideoDevice device(mpi::VIDEO_DEVICE_REAR);  // 占用后路设备
        while (isStarted()) { wait(); }                          // mpi 持续拉流
      } catch (mpi::Exception& e) { Thread::sleep(100); }
    }
  }
};
```
⚠️ **UVC 必须有任务持续读流**，否则断流/摄像头休眠；切走/断开先 stop，重新接入再 start。

## 4. 预览布局与录像/拍照（复用 MPP 双路）

- 预览：FRONT（内置源，viewbox 平移缩放，display 全屏 layer0）与 UVC REAR（源=UVC 实际分辨率，
  display 半屏/右屏拉伸显示，layer4）按 VIEW_TYPE_FRONT/REAR/BOTH/UNVISIBLE 显隐组合
- 录像：`RecorderParameters.settings[FRONT] + settings[REAR]`（有 UVC 才加 REAR 路），
  分段 duration/audio/bitrate/25fps/720P 或 1080P——与内置摄像头同一套 Recorder
- **拍照走 mpi::Snapshot**（不是 Recorder::takePicture）：
  ```cpp
  #include <mpi/case/snapshot.h>
  static base::timer take_picture_timer;              // 200ms 防抖（连点保护）
  if (take_picture_timer.elapsed() < 200) return;
  std::vector<std::string> names = ...;               // 快照文件名（可多路）
  NO_EXCEPTION(mpi::Snapshot::instance().takePicture(names, {}));
  take_picture_timer.reset();
  ```
- 回放/删除/锁定等复用 aw-dvr 既有链路（ZKVideoView / JpegViewer，见 v85x-mpp.md）

## 5. 连接状态机与 UI 联动（通用设计）

- 状态枚举（可按产品裁剪）：连接正常 / USB 断开 / 摄像头异常 / 流异常 / 其他
- **防抖计数**：状态连续 N 帧（如 50）才切换广播，避免瞬时抖动闪 UI
- 回调集 `uvc_add_camera_state_cb` 通知 UI；从异常恢复或断开重连后，若在预览页 →
  `runInUiThreadUniqueDelayed("resume_display", resetCameraPreview(false), ~200ms)` 重建预览
- 开机流程：注册状态回调 → `uvc_video_detect_start()` → 初始 `setupCameraPreview(UNVISIBLE)`；
  设置页可提供"重新探测"（open_uvc_camera）

## 6. 坑与注意

1. **UVC 必须持续读流**：取流任务（§3）不能停久，否则断流/休眠；接入成功先 start 再开预览
2. **MPP 互斥**：拔插/切流/进回放前先 `mpi::Recorder::stop()` + `mpi::RearCamera::stop()`；
   **开始录像时不要停预览/保活任务**（预览+录像共用 REAR 通道，可同开，停了才黑屏）
3. **热插拔时序**：IN_CREATE 后延时 ~3s 再枚举；「当前无设备才触发」防多节点重复；
   IN_DELETE 只认自己记录的节点
4. **REAR 通道让给 UVC**：产品若还要后录/倒车摄像头（占 REAR）会冲突；倒车检测可挂
   RTSP 流状态监听联动（REAR 有流停检测、无流起检测）
5. **通用 JPEG UVC 摄像头必须显式协商格式**（见 §7.1）：不能只 `VIDIOC_G_FMT` 读默认宽高就初始化；
   摄像头默认格式未必是 MJPEG，格式错配 → 绿屏/花屏
6. **重新接入不同分辨率模块**：Init 幂等只跑一次，运行时换分辨率需进程级重建或显式 Deinit

## 7. 通用 JPEG(MJPEG) UVC 摄像头落地必查清单（绿屏/黑屏防坑）

> 2026-09-08 补：外部 AI 工具按骨架落地 JPEG UVC 时出现「录制文件播放绿屏」「录制中摄像头图像黑掉」
> 两类异常，根因集中在格式协商缺失、录像尺寸错配、录像/预览互斥顺序、UVC 保活四件事，逐条自查：

### 7.1 格式协商（接入第一步，决定全链路）

- aw-dvr UVC 通道**默认按 MJPEG 采集**：`VideoDeviceParameters.capture_pixel_format` 默认
  `V4L2_PIX_FMT_MJPEG`（可切 YUYV/YUV420），内部 JPEG→NV21 解码由 SDK 完成，应用层不碰解码；
  输出 `pixel_format` 默认 NV21（MM_PIXEL_FORMAT_YVU_SEMIPLANAR_420）
- **通用 JPEG UVC 摄像头接入必须显式协商**，不能只 G_FMT 读宽高就 Init：
  ```cpp
  // 1. ENUM_FMT 确认支持 MJPEG（部分摄像头默认 YUYV 优先，不协商会按错格式采集）
  struct v4l2_fmtdesc fd; memset(&fd,0,sizeof(fd)); fd.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  for (int i=0; ioctl(fd, VIDIOC_ENUM_FMT, &fd) == 0; i++, fd.index++) {
      if (fd.pixelformat == V4L2_PIX_FMT_MJPEG) { /* 支持 JPEG */ }
  }
  // 2. S_FMT 锁定 MJPEG + 目标分辨率
  struct v4l2_format fmt; memset(&fmt,0,sizeof(fmt)); fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_MJPEG;
  fmt.fmt.pix.width = W; fmt.fmt.pix.height = H;   // W/H 从 ENUM_FRAMESIZES 或默认取
  if (ioctl(fd, VIDIOC_S_FMT, &fmt) < 0) { /* 摄像头不支持该尺寸，回退 */ }
  // 3. 用 S_FMT 实际返回的宽高 Init（部分摄像头会回退到相邻档位）
  CameraHelper::Init(fmt.fmt.pix.width, fmt.fmt.pix.height);
  ```
- 不协商的后果：采集到非 JPEG 数据仍按 MJPEG 解码 → 编码器吃垃圾流 → **录制文件播放绿屏**

### 7.2 录像分辨率对齐（绿屏第二高发）

- `RecordingSettings.size`（REAR 路）必须与 UVC 实际输出分辨率一致（或确认 VI 缩放链路已启用），
  **不能照抄内置摄像头 1080P/720P 档位**；尺寸错配 → VENC 编码异常 → 回放绿屏
- 录像参数与 Init 注册的 picture_size（= S_FMT 协商后的实际宽高）对齐后再起录

### 7.3 录像与预览互斥顺序（录制中黑屏高发）

- **开始录像**：直接 `mpi::Recorder::instance().start(param)`，**不要**先停 RearCamera/取流保活
  （DVR 常态 = 边录边看，同开才正常）
- **切流/拔插/进回放前**：先 `mpi::Recorder::instance().stop()` + `mpi::RearCamera::instance().stop()`
  再重建（MPP 互斥）；顺序反了 → 录像中画面黑掉 / 断流后不恢复

### 7.4 UVC 保活（录制中黑屏另一高发）

- UVC 必须有任务持续读流（SharedVideoDevice(REAR) 循环 wait()，见 §3），**录像期间也不能停**；
  停了摄像头休眠/断流 → 录制中黑屏

### 7.5 录像/回放格式口径

- 录像产物仅 **mp4 / ts**（H.264 封装）；JPEG 仅用于照片场景（Snapshot 拍照 → 相册 → JpegViewer 回看）
- 回放：视频 → ZKVideoView::play(file)；照片 → mpi::JpegViewer::start(file, rect)（先停视频再显示，成对 stop）
- 详细解码/录制 API 见同目录 `jpeg-decode-record.md`

## 8. 全链路验证流程（实测基准，2026-09-08 CV201PND 板 1280x720 JPEG UVC）

> 六步验证法，每步有明确日志判据；落地 JPEG UVC 功能后照此自测，可定位绿屏/黑屏断在哪个环节：

| 步骤 | 动作 | 成功日志判据 |
|------|------|-------------|
| ① 探测 | ENUM_FMT + S_FMT 锁 MJPEG | `default fmt = MJPG 1280x720`、`S_FMT MJPEG ok -> 1280x720` |
| ② 预览 | 注册 REAR UVC + 保活 + RearCamera | `find uvc /dev/video0`、`rear camera fps 29.3`（接近摄像头帧率=取流正常） |
| ③ 拍照 | Snapshot(REAR) | `image .../photo/Rear/*.jpg`、文件 >0 字节 |
| ④ 录像 | Recorder 录 mp4（尺寸=协商值，frame_rate 25） | `rear venc fps 25.0`（编码持续出帧）、文件实时增长 |
| ⑤ 停止 | 先 Recorder::stop 再停预览 | `MPP_EVENT_RECORD_DONE`、`done <路径>`、文件 12s≈29MB |
| ⑥ 回放 | videoview play 最新文件 | `media play ok`（demux/vdec/vo/clock 全 success）、播完无绿屏 |

- **绿屏排查第一看文件大小**：0 字节 = 取流/保活断（VENC 无数据），不是编码参数问题；正常文件应有 ftyp+avcC+moov
- **frame_rate 必须 15~60**（aw-dvr 校验，0 会抛异常），UVC 25/30fps 就写 25/30
