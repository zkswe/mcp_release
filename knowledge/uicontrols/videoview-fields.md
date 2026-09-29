---
id: uicontrols-videoview-fields
title: VideoView 视频控件 JSON 字段规范（含轮播/API 双模式）
category: uicontrols
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [2026-09-07 git, 0 SDK 校准, 广告机轮播, 本地视频播放, RTSP 等, MusicDemo]
evidence: []
---
# VideoView 视频控件 JSON 字段规范（含轮播/API 双模式）

> 检索导引：问「视频播放怎么做 / 轮播列表文件 _video_list.txt 放哪 / loopPlayback 两种模式 / play 接口 / 播放状态回调 / rotation 是角度还是枚举」→ 本文；摄像头实时预览见 `uicontrols/cameraview-fields.md`。
> 2026-09-07 git.com 全库学习 + basedemo/VideoPlayerDemo-New、VideoViewDemo-New + f133 easyui 2.9.0 SDK 校准。
> 场景：视频播放器（广告机轮播、本地视频播放、RTSP 等）。音频播放器见 ZKMediaPlayer 说明（MusicDemo）。

## 核心铁律

1. **两种播放模式（沛哥 2026-09-07 确认）**：
   - **自动轮播模式**：ftu 属性 `loopPlayback=true`（属性表"是否为轮播视频类型"）→ 进页面自动读取 **TF 卡根目录 `<UI文件名>_video_list.txt`**（如 main.ftu → `main_video_list.txt`，每行一个视频绝对路径，建议英文名），循环播放；退出页面自动停止。适合广告机、无人值守轮播，**零代码**。
   - **API 模式**：`loopPlayback=false` 只建渲染区域 → 代码 `play(path, msec)` 控制。
2. 播放状态监听：`setVideoPlayerMessageListener` → `onVideoPlayerMessage(pVideoView, msg)`，msg 枚举 E_MSGTYPE_VIDEO_PLAY_STARTED / COMPLETED / ERROR。广告机表驱动切集/错误自愈都靠它。
3. 平台注意：视频功能非所有机器版本支持，需多媒体版机器。
4. 音量 0.0~1.0 float；rotation 0/1/2/3 = 0°/90°/180°/270°（顺时针）。

## JSON 字段表（ftu 实测校准）

| 字段 | 说明 |
|------|------|
| `caption`/`id` | id 实测 videoview 段（Advertising 用 40000+） |
| `loopPlayback` | **true=轮播模式**（读 UI名_video_list.txt 自动播）；false=API 模式 |
| `defaultVolume` | 默认音量（注意广告机代码 defaultvolume/10.0 使用） |
| `rotation` | 0/1/2/3 旋转 |
| `backgroundColor` | 默认黑 |
| `touchable`/`visible`/`beepEnable` | 通用 |

## 代码操作（VideoPlayerDemo 实测）

```cpp
mVideoViewPtr->play("/mnt/extsd/test.mp4", 0); // 从 0ms 播（第二参可断点续播）
mVideoViewPtr->pause();  mVideoViewPtr->resume();
mVideoViewPtr->stop();
mVideoViewPtr->seekTo(ms);
mVideoViewPtr->isPlaying();
mVideoViewPtr->getDuration();      // 总时长 ms
mVideoViewPtr->getCurrentPosition(); // 当前 ms
mVideoViewPtr->setVolume(0.5f);    // 0.0~1.0

// 进度条联动：1s 定时器 getCurrentPosition/1000 → setProgress
// 拖动：onStopTrackingTouch 里 seekTo(progress*1000)
// 播完自动下一集：onVideoPlayerMessage COMPLETED → next()
```

## 自动轮播文件列表格式
`main_video_list.txt`（TF 根目录）：
```
/mnt/extsd/movie1.mp4
/mnt/extsd/movie2.mp4
```

## 样例代码
VideoPlayerDemo-New（完整播放器：列表+进度+音量+监听）；VideoViewDemo-New（轮播/API 基础）；Advertising playLogic（表驱动循环播放+错误计数自愈）；lib-simple-player、lib-upnp-dlna（消息监听用法）。
