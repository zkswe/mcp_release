# V85X USB 摄像头（UVC）接入 + 预览/录像/拍照

> 来源：`LearningProject/mark_cv201` → `CV201_PND`（+ `CV201_PND_1024_600` 变体）实测（2026-09-03）。
> 平台：V85X（AW_V853），aw-dvr 3.9.12 / 3.3.1（accessKey 私有包）。
> 场景：**V85X 主机通过 USB 接入 UVC 摄像头**，与内置 ISP 前摄像头双路共存：预览/录像/拍照。
> ⚠️ 草稿（待入库）：沛哥 2026-09-03 指示——只记录**通用 UVC 接入**部分；
> 定制模块的私有协议层（帧尾数据区/私有控制编码/AI/超分等）是特殊摄像头自研处理，不收录。

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
2. **MPP 互斥**：拔插/切流/进回放前先 `mpi::Recorder::stop()` + `mpi::RearCamera::stop()`
3. **热插拔时序**：IN_CREATE 后延时 ~3s 再枚举；「当前无设备才触发」防多节点重复；
   IN_DELETE 只认自己记录的节点
4. **REAR 通道让给 UVC**：产品若还要后录/倒车摄像头（占 REAR）会冲突；倒车检测可挂
   RTSP 流状态监听联动（REAR 有流停检测、无流起检测）
5. **格式协商从简**：直接 `VIDIOC_G_FMT` 用摄像头默认分辨率（不枚举/切换格式），
   要切分辨率需自行枚举 `VIDIOC_ENUM_FMT/ENUM_FRAMESIZES` + `S_FMT`（本方案未做）
6. **重新接入不同分辨率模块**：Init 幂等只跑一次，运行时换分辨率需进程级重建或显式 Deinit
