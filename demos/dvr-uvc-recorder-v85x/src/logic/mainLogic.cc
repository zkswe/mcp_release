#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD
#pragma once
#include "uart/ProtocolSender.h"
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <atomic>
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <linux/videodev2.h>
#include <vo/hwdisplay.h>  // 先 typedef s32/u32 再包含 sunxi_display2.h（直接 include 后者会缺类型定义）
#include <mpi/case/config.h>
#include <mpi/case/camera.h>
#include <mpi/case/recorder.h>
#include <mpi/case/snapshot.h>
#include <mpi/case/shared_video_device.h>
#include <base/base.h>

/*
 * UvcJpegTest - CV201PND (V85X) JPEG UVC 摄像头链路测试
 * 屏 1600x600，单路 USB UVC(JPEG/MJPEG) 摄像头
 * 按钮: 1 Detect 探测协商 / 2 Preview 预览 / 3 Photo 拍照
 *       4 Record 录像 / 5 Stop 停止 / 6 Play 回放
 * 验证: 格式协商结果 / 预览黑屏 / 录像中预览保持 / 录制文件回放绿屏
 */

namespace {

const int VIDEO_DEV_MAX = 12;
std::atomic<bool> s_previewing(false);
std::atomic<bool> s_recording(false);
int s_uvc_width = 0;
int s_uvc_height = 0;
bool s_detected = false;
std::string s_last_video;   // 最近一次录像文件（回放用）
std::string s_dev = "/dev/video0";

void setStatus(const std::string& msg) {
  LOGD("UvcTest: %s", msg.c_str());
  if (mTextStatusPtr) {
    mTextStatusPtr->setText(msg.c_str());
  }
}

std::string uvcDev() {
  char dev[32];
  for (int i = 0; i <= VIDEO_DEV_MAX; i++) {
    snprintf(dev, sizeof(dev), "/dev/video%d", i);
    int fd = open(dev, O_RDONLY);
    if (fd < 0) continue;
    struct v4l2_capability cap;
    memset(&cap, 0, sizeof(cap));
    if (ioctl(fd, VIDIOC_QUERYCAP, &cap) == 0) {
      close(fd);
      if (strcmp((const char*)cap.driver, "uvcvideo") == 0) {
        return std::string(dev);
      }
    } else {
      close(fd);
    }
  }
  return "";
}

/* 探测：枚举格式 + S_FMT 锁 MJPEG，返回协商尺寸是否成功 */
bool negotiateMJPEG(const std::string& dev, int* out_w, int* out_h) {
  int fd = open(dev.c_str(), O_RDWR);
  if (fd < 0) return false;
  bool ret = false;
  *out_w = 0; *out_h = 0;

  // 读当前默认格式（分辨率）
  struct v4l2_format fmt;
  memset(&fmt, 0, sizeof(fmt));
  fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  if (ioctl(fd, VIDIOC_G_FMT, &fmt) == 0) {
    *out_w = fmt.fmt.pix.width;
    *out_h = fmt.fmt.pix.height;
    LOGD("UvcTest: default fmt = %c%c%c%c %dx%d",
         fmt.fmt.pix.pixelformat & 0xff,
         (fmt.fmt.pix.pixelformat >> 8) & 0xff,
         (fmt.fmt.pix.pixelformat >> 16) & 0xff,
         (fmt.fmt.pix.pixelformat >> 24) & 0xff,
         fmt.fmt.pix.width, fmt.fmt.pix.height);
  }

  // 枚举支持的格式，打印
  struct v4l2_fmtdesc fdesc;
  memset(&fdesc, 0, sizeof(fdesc));
  fdesc.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  for (int i = 0;; i++) {
    memset(&fdesc, 0, sizeof(fdesc));
    fdesc.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    fdesc.index = i;
    if (ioctl(fd, VIDIOC_ENUM_FMT, &fdesc) != 0) break;
    LOGD("UvcTest:   fmt[%d] = %c%c%c%c %s",
         i,
         fdesc.pixelformat & 0xff, (fdesc.pixelformat >> 8) & 0xff,
         (fdesc.pixelformat >> 16) & 0xff, (fdesc.pixelformat >> 24) & 0xff,
         fdesc.description);
  }

  // 尝试 S_FMT 锁 MJPEG，保持默认分辨率
  if (*out_w > 0 && *out_h > 0) {
    memset(&fmt, 0, sizeof(fmt));
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_MJPEG;
    fmt.fmt.pix.width = *out_w;
    fmt.fmt.pix.height = *out_h;
    fmt.fmt.pix.field = V4L2_FIELD_NONE;
    if (ioctl(fd, VIDIOC_S_FMT, &fmt) == 0) {
      *out_w = fmt.fmt.pix.width;
      *out_h = fmt.fmt.pix.height;
      LOGD("UvcTest: S_FMT MJPEG ok -> %dx%d", *out_w, *out_h);
      ret = true;
    } else {
      LOGD("UvcTest: S_FMT MJPEG failed, keep default");
    }
  }
  close(fd);
  return ret;
}

/* UVC 取流保活任务：持续占用 REAR 通道读流，防休眠断流 */
class UvcKeepAlive : public mpi::Task<> {
public:
  UvcKeepAlive() : mpi::Task<>() {}
protected:
  virtual void doTask() override {
    while (isStarted()) {
      try {
        mpi::SharedVideoDevice dev(mpi::VIDEO_DEVICE_REAR);
        while (isStarted()) {
          wait();
        }
      } catch (mpi::Exception& e) {
        LOGE("UvcKeepAlive exception: %s", e.what());
        usleep(100 * 1000);
      }
    }
  }
};

UvcKeepAlive s_keepalive;

/* 注册 REAR UVC 通道（JPEG 采集，aw-dvr 默认 capture=MJPEG）并 apply */
bool initUvcMpi(int w, int h) {
  mpi::initializeSystem();
  mpi::VideoDeviceRegistry::instance().add(mpi::VIDEO_DEVICE_REAR)
      .setFrameRate(0)
      .setPictureSize({w, h})
      .setUvc(true)
      .setId(mpi::DEVICE_ID_AUTO);
  mpi::config().apply();
  return true;
}

void startPreview() {
  if (s_previewing) return;
  mpi::CameraParam param;
  param.viewbox = {0, 0, s_uvc_width, s_uvc_height};
  param.display = {0, 0, 1600, 600};
  param.mirror = false;
  param.visible = true;
  param.layer = -1;
  mpi::RearCamera::instance().setParam(param, true);
  s_previewing = true;
  LOGD("UvcTest: preview started %dx%d", s_uvc_width, s_uvc_height);
}

void stopAll() {
  if (s_recording) {
    try {
      mpi::Recorder::instance().stop();
    } catch (mpi::Exception& e) {
      LOGE("UvcTest: recorder stop ex %s", e.what());
    }
    s_recording = false;
  }
  if (s_previewing) {
    try {
      mpi::RearCamera::instance().setVisible(false, true);
    } catch (mpi::Exception& e) {
      LOGE("UvcTest: camera hide ex %s", e.what());
    }
    s_previewing = false;
  }
  try {
    s_keepalive.stop();
  } catch (...) {
  }
}

std::string latestVideoFile() {
  try {
    auto files = mpi::Recorder::instance().getFiles(
        (mpi::FileFormat)mpi::FILE_FORMAT_MP4,
        mpi::VIEW_REAR, false, true, true);
    if (!files.empty()) {
      return files.front().string();
    }
    files = mpi::Recorder::instance().getFiles(
        (mpi::FileFormat)mpi::FILE_FORMAT_TS,
        mpi::VIEW_REAR, false, true, true);
    if (!files.empty()) {
      return files.front().string();
    }
  } catch (mpi::Exception& e) {
    LOGE("UvcTest: getFiles ex %s", e.what());
  }
  return "";
}

} // namespace

/* 释放 disp 图层（保留 UI 层 ch2/layer0，关闭其余残留层，防错屏/层叠加） */
static int _layer_config(int fd, int cmd, disp_layer_config *cfg) {
  unsigned long args[4] = {0};
  args[1] = (unsigned long)cfg;
  args[2] = 1;
  return ioctl(fd, cmd, args);
}

void releaseLayer() {
#define CHN_NUM 4
#define LYL_NUM 4
#define UI_LYCHN 2
#define UI_LYLAY 0

  int fd = open("/dev/disp", O_RDWR);
  if (fd < 0) {
    LOGE("Failed to open disp device, errno: %d\n", errno);
    return;
  }

  for (int ch = 0; ch < CHN_NUM; ++ch) {
    for (int lyl = 0; lyl < LYL_NUM; ++lyl) {
      if ((ch == UI_LYCHN) && (lyl == UI_LYLAY)) {
        continue;
      }

      disp_layer_config config;
      memset(&config, 0, sizeof(disp_layer_config));
      config.channel = ch;
      config.layer_id = lyl;

      _layer_config(fd, DISP_LAYER_GET_CONFIG, &config);
      if (!config.enable) {
        continue;
      }

      config.enable = 0;
      _layer_config(fd, DISP_LAYER_SET_CONFIG, &config);
      LOGD("[hw] close channel[%d] layer_id[%d]\n", ch, lyl);
    }
  }
  LOGD("@@@@@@@@@@@@@@@@@@@@@@@ releaseLayer ##### \n");

  close(fd);
}

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    // {id, 间隔毫秒}
};

static void onUI_init() {
#ifdef FUN_BUILD
  INIT_UI_TIMERS
#endif // FUN_BUILD
  releaseLayer();  // 释放残留图层（保留 UI 层），防错屏
  setStatus("JPEG UVC Test Ready");
}

static void onUI_intent(const Intent *intentPtr) {
  if (intentPtr != NULL) {
    //TODO
  }
}

static void onUI_show() {}

static void onUI_hide() {}

static void onUI_quit() {
  stopAll();
}

static void onProtocolDataUpdate(const SProtocolData &data) {}

static bool onUI_Timer(int id) {
  switch (id) {
  default:
    break;
  }
  return true;
}

static bool onmainActivityTouchEvent(const MotionEvent &ev) {
  return false;
}

/* 1 探测：找 uvcvideo 设备 + 协商 MJPEG */
static bool onButtonClick_BtnDetect(ZKButton *pButton) {
  try {
    s_dev = uvcDev();
    if (s_dev.empty()) {
      setStatus("No uvcvideo device found");
      return false;
    }
    char msg[128];
    snprintf(msg, sizeof(msg), "Found %s, negotiating...", s_dev.c_str());
    setStatus(msg);
    bool ok = negotiateMJPEG(s_dev, &s_uvc_width, &s_uvc_height);
    s_detected = ok && s_uvc_width > 0 && s_uvc_height > 0;
    if (s_detected) {
      snprintf(msg, sizeof(msg), "MJPEG %dx%d OK (S_FMT locked)",
               s_uvc_width, s_uvc_height);
    } else {
      snprintf(msg, sizeof(msg), "Negotiate failed, use default %dx%d",
               s_uvc_width, s_uvc_height);
      s_detected = s_uvc_width > 0 && s_uvc_height > 0;
    }
    setStatus(msg);
  } catch (std::exception& e) {
    setStatus(std::string("Detect ex: ") + e.what());
  }
  return false;
}

/* 2 预览：注册 REAR UVC + 保活 + RearCamera 显示 */
static bool onButtonClick_BtnPreview(ZKButton *pButton) {
  try {
    if (!s_detected) {
      setStatus("Run Detect first");
      return false;
    }
    stopAll();
    initUvcMpi(s_uvc_width, s_uvc_height);
    s_keepalive.start();
    usleep(200 * 1000);
    startPreview();
    char msg[128];
    snprintf(msg, sizeof(msg), "Preview ON %dx%d (keep-alive running)",
             s_uvc_width, s_uvc_height);
    setStatus(msg);
  } catch (std::exception& e) {
    setStatus(std::string("Preview ex: ") + e.what());
  }
  return false;
}

/* 3 拍照 */
static bool onButtonClick_BtnPhoto(ZKButton *pButton) {
  try {
    if (!s_previewing && !s_recording) {
      setStatus("Run Preview first");
      return false;
    }
    std::vector<mpi::VideoDeviceName> names;
    names.push_back(mpi::VIDEO_DEVICE_REAR);
    mpi::Snapshot::instance().takePicture(names, {});
    setStatus("Photo taken (REAR jpg)");
  } catch (std::exception& e) {
    setStatus(std::string("Photo ex: ") + e.what());
  }
  return false;
}

/* 4 录像（开始；Stop 停止） */
static bool onButtonClick_BtnRecord(ZKButton *pButton) {
  try {
    if (s_recording) return false;
    if (!s_detected) {
      setStatus("Run Detect first");
      return false;
    }
    if (!s_previewing) {
      // 未预览先初始化并开启预览（录像过程中预览保持 = 验证点）
      stopAll();
      initUvcMpi(s_uvc_width, s_uvc_height);
      s_keepalive.start();
      usleep(200 * 1000);
      startPreview();
    }
    mpi::RecordingSettings s;
    s.duration = 60;
    s.audio = false;
    s.bitrate = 8 * 1024 * 1024;
    s.frame_rate = 25;
    s.size = {s_uvc_width, s_uvc_height};   // 尺寸 = UVC 实际分辨率（防绿屏）
    s.thumbnail_size = {0, 0};
    s.video_format = mpi::FILE_FORMAT_MP4;
    mpi::RecorderParameters p;
    p.settings[mpi::VIDEO_DEVICE_REAR] = s;
    mpi::Recorder::instance().start(p);
    s_recording = true;
    char msg[128];
    snprintf(msg, sizeof(msg), "Recording MP4 %dx%d ... (Stop to end)",
             s_uvc_width, s_uvc_height);
    setStatus(msg);
  } catch (std::exception& e) {
    setStatus(std::string("Record ex: ") + e.what());
  }
  return false;
}

/* 5 停止：停录像 + 停预览 + 停保活 */
static bool onButtonClick_BtnStop(ZKButton *pButton) {
  try {
    bool was_rec = s_recording;
    stopAll();
    if (was_rec) {
      usleep(300 * 1000);
      s_last_video = latestVideoFile();
      if (!s_last_video.empty()) {
        std::string msg = "Recorded: " + s_last_video;
        setStatus(msg);
      } else {
        setStatus("Record stopped (file not found yet)");
      }
    } else {
      setStatus("Stopped");
    }
  } catch (std::exception& e) {
    setStatus(std::string("Stop ex: ") + e.what());
  }
  return false;
}

/* 6 回放：用 videoview 播放最近录像文件（验证是否绿屏） */
static bool onButtonClick_BtnPlay(ZKButton *pButton) {
  try {
    if (s_recording || s_previewing) {
      stopAll();
      usleep(300 * 1000);
    }
    if (s_last_video.empty()) {
      s_last_video = latestVideoFile();
    }
    if (s_last_video.empty()) {
      setStatus("No video file to play");
      return false;
    }
    if (!mVideoViewTestPtr) return false;
    mVideoViewTestPtr->setVisible(true);
    mVideoViewTestPtr->play(s_last_video.c_str());
    std::string msg = "Play: " + s_last_video;
    setStatus(msg);
  } catch (std::exception& e) {
    setStatus(std::string("Play ex: ") + e.what());
  }
  return false;
}
