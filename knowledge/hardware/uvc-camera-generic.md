---
id: hardware-uvc-camera-generic
title: UVC / USB 摄像头通用接入（跨平台：V85X / T113 / F133 / Z20 / Z21）
category: hardware
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [F133, Z20, Z21, T113, V85X]
tags: [JPEG, MJPEG 摄像头绿屏, 录制中黑屏, dev, video 热插拔检测, 摄像头格式协商, V4L2 采集, 平台无关通用层, 指定 V85X 且要预览, 录像, v85x, uvc-usb-camera, md, aw-dvr, JPEG 解码, MJPEG 录制]
evidence: []
---
# UVC / USB 摄像头通用接入（跨平台：V85X / T113 / F133 / Z20 / Z21）

> 🔍 **检索导引（命中条件）**：用户问「**UVC 摄像头接入**」「**USB 摄像头预览/拍照/录像**」「**外接摄像头 / USB 摄像头没画面**」
> 「**JPEG/MJPEG 摄像头绿屏 / 录制中黑屏**」「**/dev/video 热插拔检测**」「**摄像头格式协商 / V4L2 采集**」
> **没有指定平台** → **先读本篇**（平台无关通用层）；**指定 V85X 且要预览/录像/拍照全套** → 读
> `v85x/uvc-usb-camera.md`（aw-dvr/mpi:: 绑定实现）+ `v85x/jpeg-decode-record.md`（JPEG 解码/MJPEG 录制）。
> ⚠️ **纪律**：T113 / F133 / Z20 / Z21 的**平台绑定层（预览显示/编码录制 API）未实测不编造**；
> 本篇只给**平台无关通用层**（发现/协商/保活/状态机/JPEG 必查清单），绑定层按各平台媒体栈实现后补录。

## 一句话

Linux 内核带 **uvcvideo 驱动 + USB Host** 的平台都能接 UVC/USB 摄像头：
`/dev/videoN` 即插即用（热插拔）→ V4L2 枚举/协商格式 → 持续取流保活 →
平台媒体栈（绑定层）做预览/编码/录像。**通用层逻辑全平台一致，只有绑定层 API 不同**。

## 0. 前置条件（先查硬件/内核，别急着写代码）

| 检查项 | 说明 |
|--------|------|
| USB 工作在 **Host** 模式 | 设备 USB 口默认可能 OTG/Device（ADB/CDC）；切 Host 见 `hardware/usb-otg-switch.md`（V85X/T113/Z21 节点已实测） |
| 内核有 **uvcvideo** 驱动 | `ls /sys/bus/usb/drivers/uvcvideo` 存在；插入后 `dmesg` 出现 uvcvideo 枚举日志 |
| 插入后出现 **/dev/videoN** | 无节点 = Host 没切对/驱动没编入，先解决前置再谈应用 |

## 1. 设备发现（inotify 监听 /dev + driver 匹配，平台无关）

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

- 后台线程 `inotify_init` + `inotify_add_watch("/dev", IN_CREATE|IN_DELETE)`，文件名 `regex_match("video\\d*")`：
  - **IN_CREATE**：当前无设备才触发，**延时 ~3s** 再枚举（等内核枚举完成，太早 open 失败；
    UVC 常建多个 videoN，用「无设备才触发」防重复处理）
  - **IN_DELETE**：删除节点 == 当前记录节点 → 关设备（先停录像/预览/取流任务），清状态广播断开
- **匹配口径**：`VIDIOC_QUERYCAP` 且 `driver == "uvcvideo"` 才认（排除平台自带 sensor 的 video 节点）

## 2. 打开与格式协商（决定后面全链路）

1. `VIDIOC_QUERYCAP` 读能力（driver/card/bus_info）
2. `VIDIOC_ENUM_FMT` 枚举像素格式（区分 YUYV / MJPEG / H264 / NV12）
3. `VIDIOC_S_FMT` **锁定格式 + 分辨率**（**不能只 G_FMT 读默认就开工**——摄像头默认未必是你想要的格式）
4. 用 S_FMT **实际返回**的宽高做后续初始化（部分摄像头会回退到相邻档位）

- **不协商的后果**：摄像头默认格式可能是 YUYV 却按 MJPEG 处理 → 垃圾流 → **绿屏/花屏**
- 可直接抄的 MJPEG 协商代码（ENUM_FMT + S_FMT + 用返回值 Init）→ `v85x/uvc-usb-camera.md` §7.1

## 3. 持续取流保活（UVC 铁律，平台无关）

⚠️ UVC 摄像头**必须有任务持续读流**，否则摄像头休眠/断流（尤其 USB 带宽紧张或设备省电策略）；
接入成功先启动保活任务再开预览，**录像期间也不能停**（停了 → 录制中画面黑掉）。
V85X 的具体实现（`mpi::Task<>` 循环 + `SharedVideoDevice(REAR)` 持续 wait）见 `v85x/uvc-usb-camera.md` §3。

## 4. 热插拔状态机（通用设计）

状态枚举（按产品裁剪）：连接正常 / USB 断开 / 摄像头异常 / 流异常 / 其他；**防抖计数** = 状态连续 N 帧（如 50）才切换广播，避免瞬时抖动闪 UI；
回调通知 UI，从异常恢复或断开重连后若在预览页 → 延时 ~200ms 重建预览；开机：注册回调 → 启动检测线程 → 初始预览置不可见（设置页可「重新探测」）。
V85X 对应的落地 API（`uvc_add_camera_state_cb` / `runInUiThreadUniqueDelayed` / `uvc_video_detect_start`）见 `v85x/uvc-usb-camera.md` §5。

## 5. JPEG(MJPEG) UVC 摄像头落地必查清单

→ **正文（唯一出处）**：`v85x/uvc-usb-camera.md` §7「通用 JPEG(MJPEG) UVC 摄像头落地必查清单」——格式协商 / 尺寸对齐 /
互斥顺序 / 保活四件事，含代码与日志判据；落地前必读，否则易出「录制文件播放绿屏」「录制中画面黑掉」。

## 6. 平台绑定对照（谁负责哪一层）

| 平台 | 通用层（本篇，平台无关） | 绑定层（预览/编码/录像 API） | 知识位置 |
|------|------------------------|------------------------------|---------|
| **V85X**（AW_V853） | ✅ 直接用 | aw-dvr/mpi::（FRONT 内置 ISP + REAR UVC 双路；Recorder 录 mp4/ts；Snapshot 拍照；JpegViewer 回看照片） | `v85x/uvc-usb-camera.md` + `v85x/jpeg-decode-record.md`（已实测收录） |
| **T113**（车载 PND） | ✅ 直接用（需 USB Host，见 usb-otg-switch） | ⚠️ 未实测未收录；有 AHD 摄像头先例（`t113-car/ahd-camera-format.md`，非 UVC） | 待实测补录 |
| **F133 / Z20 / Z21** | ✅ 通用逻辑可用（需内核 uvcvideo + USB Host） | ⚠️ 未实测未收录，不编造 | 待实测补录 |

## 坑速记

1. IN_CREATE 延时 3s 再枚举、「无设备才触发」防多节点；IN_DELETE 只认自己记录的节点；
2. 平台绑定层细节按各平台媒体栈实现，未实测不写；
3. 保活 / 互斥顺序 / 格式协商 / 尺寸对齐四坑与处置统一见 `v85x/uvc-usb-camera.md` §6/§7。
