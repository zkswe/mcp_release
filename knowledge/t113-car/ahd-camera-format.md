---
id: t113-car-ahd-camera-format
title: 📹 T113 倒车摄像头格式参数表（AHD/TVI/CVBS/DM5885）
category: t113-car
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [T113]
tags: [public, t113, jni, logic, 分辨率, 帧率配置]
evidence: []
---
# 📹 T113 倒车摄像头格式参数表（AHD/TVI/CVBS/DM5885）

> 检索导引：问「T113 倒车摄像头选哪个格式 / AHD·TVI·CVBS·DM5885 参数表 / 分辨率帧率（标 25 实际 24）配错 / cam_format_tab 改哪 / 格式切换回调」→ 本文；控件字段见 `knowledge/uicontrols/cameraview-fields.md`。
> 2026-09-02 沛哥要求收录（来源：git 收录工程 `temp_car/public/t113/T113CarSystem_PND/jni/logic/`）。
> 适用：T113 车载倒车影像，ZKCameraView 格式/分辨率/帧率配置。

## 一、完整格式参数表（两处代码表一致，实测）

来源：`reverseLogic.cc` 的 `_s_cam_info_tab[]` 与 `settingsLogic.cc` 的 `cam_format_tab[]`（同一张表）。

| 显示名 | 宽 | 高 | 帧率 | di_enable（奇偶合并） | 备注 |
|--------|-----|-----|------|----------------------|------|
| AHD 720P 25 | 1280 | 720 | 25 | false | |
| AHD 720P 30 | 1280 | 720 | 30 | false | |
| TVI 720P 25 | 1280 | 720 | **24** | false | 标 25 实际 24 |
| TVI 720P 30 | 1280 | 720 | **29** | false | 标 30 实际 29 |
| AHD 1080P 25 | 1920 | 1080 | 25 | false | |
| AHD 1080P 30 | 1920 | 1080 | 30 | false | |
| TVI 1080P 25 | 1920 | 1080 | **24** | false | |
| TVI 1080P 30 | 1920 | 1080 | **29** | false | |
| CVBS PAL 50 | 960 | 576 | 50 | **true** | N/P 制才使能奇偶合并 |
| CVBS NTSC 60 | 960 | 480 | 60 | **true** | |
| DM5885 50 | 720 | 480 | 50 | false | 逐行 |
| DM5885 49 | 720 | 480 | 49 | true | 隔行 |

⚠️ **TVI 帧率是 24/29 不是 25/30**（显示名标 25/30，实际传 24/29）；CVBS/DM5885 隔行才开 di_enable。

## 二、对应代码

### 1. 格式表定义（reverseLogic.cc）

```cpp
struct cam_info_t {
	const char *name;
	int w;
	int h;
	int rate;
	bool di_enable;   // 使能硬件奇偶合并
	bool checked;
};

static cam_info_t _s_cam_info_tab[] = {
	{ "AHD 720P 25", 1280, 720, 25, false, false },
	{ "AHD 720P 30", 1280, 720, 30, false, false },
	{ "TVI 720P 25", 1280, 720, 24, false, false },
	{ "TVI 720P 30", 1280, 720, 29, false, false },
	{ "AHD 1080P 25", 1920, 1080, 25, false, false },
	{ "AHD 1080P 30", 1920, 1080, 30, false, false },
	{ "TVI 1080P 25", 1920, 1080, 24, false, false },
	{ "TVI 1080P 30", 1920, 1080, 29, false, false },
	{ "CVBS PAL 50", 960, 576, 50, true, false },
	{ "CVBS NTSC 60", 960, 480, 60, true, false },
	{ "DM5885 50", 720, 480, 50, false, false },   // 逐行
	{ "DM5885 49", 720, 480, 49, true, false },    // 隔行
};
```

### 2. 切换格式（reverseLogic.cc onListItemClick_ListView1 核心）

```cpp
mCameraViewReversePtr->stopPreview();
WAIT(!mCameraViewReversePtr->isPreviewing(), 100, 50);

mCameraViewReversePtr->setFormatSize(_s_cam_info_tab[index].w, _s_cam_info_tab[index].h);
mCameraViewReversePtr->setFrameRate(_s_cam_info_tab[index].rate);

// 通过环境变量设置开启关闭奇偶合并功能，目前N制P制才使能，切换到其他格式前需要置为0
setenv("ZKCAMERA_DI_ENABLE", _s_cam_info_tab[index].di_enable ? "1" : "0", 1);

mCameraViewReversePtr->startPreview();

for (int i = 0; i < (int)TABLESIZE(_s_cam_info_tab); ++i) {
	_s_cam_info_tab[i].checked = (i == index);
}
```

### 3. 摄像头初始化（settingsLogic.cc，从系统设置读配置）

```cpp
mCameraViewReversePtr->setErrorCodeCallback(&sMyErrorCodeCallback);
mCameraViewReversePtr->setPictureCallback(&sMyPictureCallback);
mCameraViewReversePtr->setDevPath(sys::setting::get_camera_dev());   // /dev/video0=AHD, /dev/video4=CVBS
mCameraViewReversePtr->setChannel(sys::setting::get_camera_chn());
mCameraViewReversePtr->setFormatSize(sys::setting::get_camera_wide(), sys::setting::get_camera_high());
mCameraViewReversePtr->setFrameRate(sys::setting::get_camera_rate());
```

### 4. 设置页保存格式（settingsLogic.cc onListItemClick_caminfoListView）

```cpp
s_format_index = index;
sys::setting::set_camera_size(cam_format_tab[index].wide, cam_format_tab[index].high);
sys::setting::set_camera_rate(cam_format_tab[index].rate);
```

### 5. 相关 setting 接口（system/setting.h）

```cpp
void set_camera_dev(const char *dev);   // "/dev/video0" AHD  "/dev/video4" CVBS
char *get_camera_dev();
void set_camera_chn(int chn);           // 通道 0-3（ZKCAMERA_CHN 环境变量）
int  get_camera_chn();
void set_camera_size(int wide, int high);
int  get_camera_wide() / get_camera_high();
void set_camera_rate(int rate);
int  get_camera_rate();
void set_camera_rot(int rot);           // 旋转
int  get_camera_rot();
```

## 三、使用要点

1. **摄像头节点**：AHD=`/dev/video0`，CVBS=`/dev/video4`（设置页可切换，`mCameraTypeText` 显示当前类型）
2. **切换格式流程**：stopPreview → WAIT 等预览停 → setFormatSize + setFrameRate → setenv ZKCAMERA_DI_ENABLE → startPreview
3. **ZKCAMERA_DI_ENABLE**：奇偶合并（deinterlace），仅 N 制/P 制（CVBS PAL/NTSC、DM5885 隔行）使能；切到其他格式前必须置 0
4. **TVI 帧率陷阱**：显示名 "TVI 720P 25/30" 实际帧率传 24/29（不是 25/30）
5. **无信号提示**：`E_CAMERA_STATUS_CODE_NO_SIGNAL` 错误码回调**连续 2 次**才显示"无信号"（防误报）
6. 通道切换：`setenv("ZKCAMERA_CHN", selected ? "1" : "0", 1)`（0-3 通道）
