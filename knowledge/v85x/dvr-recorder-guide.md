# 🎥 V85X DVR 录制功能开发 Playbook（端到端：工程 → UI → 摄像头 → 录像 → 回放 → 存储 → 排障）

> 2026-09-09 沉淀（V85X 行车记录仪/DVR 类产品全链路实战：内置 AHD/TVI 双路 + UVC JPEG 单路，预览/录像/拍照/回放真机验证）。
> 适用：**V85X**（AW_V853 / V553 等），Manifest `platform="V85X"` + 宏 `AWCHIP=AW_V853`。
> ⚠️ 仅 V85X 平台（aw-dvr/mpi:: 为 V85X 专属）；T113/F133/Z20 摄像头走各自链路，勿跨平台照抄依赖。
> **检索导引**：问「DVR / 行车记录仪 / 录像功能 / 录制回放 / 预览拍照录像 / 摄像头存储」→ 本篇为**端到端开发指南**；再按需查细分文档（见 §0 文档地图）。

## 0. 文档地图（配合使用，避免碎片化漏环节）

| 本指南章节 | 配套细读 |
|------|------|
| §4 屏幕方向 | `devflow/package-properties-easyui-cfg.md`（rotateScreen 机制）|
| §5-1 UI 透出 | `v85x/videoview-transparent-window.md`（videoView 透明窗口权威口径）|
| §5-2/§9 图层与回放方向 | `v85x/display-layer-debug.md`（releaseLayer/图层检查/rotation 枚举）|
| §6 UVC 摄像头 | `v85x/uvc-usb-camera.md` + `v85x/jpeg-decode-record.md` |
| §8 录制卡 | `v85x/tfcard-format-requirement.md`（FAT32+64KB 簇要求）|

**为什么需要 playbook**：DVR 是跨显示/媒体/存储/硬件的复合功能，只检索碎片文档容易漏环节（最常见漏项：videoView 没 visible、回放 rotation 写角度值、卡没按 64KB 簇格式化）。

> 💡 **有现成实现可抄**：同仓 `demos/dvr-uvc-recorder-v85x/` = 本指南的可运行参考工程（UVC 摄像头 探测/预览/拍照/录像/停止/回放全链路，真机验证过），照抄改改就能跑；改内置 AHD/TVI 双路见其 README「改成内置」节。

---

## 1. 前置判定（先答 4 问再开工）

1. **平台是 V85X？** aw-dvr/mpi:: 仅 V85X（V853/V553）。其他平台停下，问平台方。
2. **摄像头形态？** 内置 AHD/TVI/CVBS（TP9950 等转 MIPI，走 `mpi::FrontCamera/RearCamera`）还是 USB UVC（JPEG/MJPEG，`VideoDeviceRegistry + setUvc(true)`）？两者接入代码不同，见 §6。
3. **屏幕方向？** UI 逻辑分辨率 vs 物理屏安装方向。横 UI 用在竖装屏 = 布局溢出屏外错屏，见 §4。
4. **录制介质？** TF 卡/EMMC 有**专属 FAT32+64KB 簇格式要求**，见 §8。

## 2. 工程与依赖（Manifest）

工程创建用 MCP `flythings_create_project`（platform=V85X + 分辨率），然后 Manifest 加依赖：

```xml
<compiler><macro>AWCHIP=AW_V853</macro></compiler>
<dependencies enableOnPlatforms="V85X">
  <package id="easyui" version="..."/>
  <!-- 勿加 aw-middleware：旧包头文件冲突且无 UVC backend（V553 实证）；aw-mpp 由 aw-dvr 传递依赖带入 -->
  <package id="aw-dvr" version="3.13.12" accessKey="0000000000000000000000000000000000000000"/>
  <!-- accessKey 发布版默认全 0 占位（40 位），实际 key 向平台方获取后替换；真实 key 不进公开仓库
       aw-dvr 版本必须与设备 runtime 的 aw-mpp 配套（见 v85x/aw-dvr-runtime-compat.md）：
       runtime aw-mpp 2.0.2 对应 aw-dvr 3.13.12；4.0.1 需 aw-mpp 3.0.0-pre2 装不上，勿用 -->
  <!-- ⚠️ accessKey 发布版默认全 0 占位（40 位），实际 key 向平台方获取后替换；真实 key 不进公开仓库 -->
  <package id="base-utility" version="4.0.2"/>
  <package id="ini" version="0.0.1"/> <package id="freetype" version="2.2.5"/>
  <package id="ntp" version="0.1.0"/>  <!-- 按需 -->
</dependencies>
```
- **aw-dvr = 核心 MPP 封装（`mpi::` 命名空间，accessKey 私有包）**，registry 在 package.flythings.cn
- **版本不是越新越好**：aw-dvr 必须与设备 runtime 的 aw-mpp 配套（4.0.1 需 aw-mpp 3.0.0-pre2，设备 runtime 2.0.2 装不上）；**V85X runtime aw-mpp 2.0.2 → 用 aw-dvr 3.13.12**（当前实测全适配组合）；版本×runtime 兼容矩阵与 dlopen 排障见 `v85x/aw-dvr-runtime-compat.md`
- ⚠️ aw-* 系列仅 V85X；T113 分支无 MPP 依赖
- 头文件：`<mpi/case/recorder.h>` `<mpi/case/front_camera.h>` `<mpi/case/rear_camera.h>` `<mpi/case/jpeg_viewer.h>` `<mpi/module/vo.h>` `<mpi/case/shared_video_device.h>`；异常走 `mpi::Exception`

## 3. 架构认知（三层）

```
① ZKCameraView 控件（easyui 内置，单摄像头调试/预览）→ 场景 A
② mpi:: C++ 封装（aw-dvr）→ DVR 产品主力：Recorder/FrontCamera/RearCamera/VO/JpegViewer
③ AllWinner MPP 底层（V853 编解码硬件 H.264/H.265）
```
- **显示分层（权威口径）**：UI 层在最顶（z=16），disp 视频层在下面（layer 4/3/2/1 叠放）；视频画面经 **UI 层 videoView 透明区域**透出
- **VI→VO 内部处理**：取流→VI→VO 由 mpi/aw-dvr 内部搬运，应用只配 `CameraParam{viewbox/display/layer/visible}`

## 4. 屏幕方向（硬件适配，错屏根因）

**错屏根因 = UI 布局超出物理屏**：横 UI（如 1600×600）用在竖装屏（600×1600），不旋转时 UI 宽 1600 > 物理宽 600，内容溢出屏外。**rotateScreen 是硬件方向适配**（值由屏幕安装方向决定，非 UI/代码决定）。

```properties
# 工程根 package.properties（触摸不转 = 只写 rotateScreen 不写 rotateTouch）
EasyUI.cfg={"rotateScreen": 270}
```
⚠️ 改后 `fun build` 会 `ninja: no work to do`——**必须 `fun clean` 全量重编**；EasyUI.cfg 由 fun launch 合并生成，设备端 `/tmp/EasyUI.cfg` 可验证 `rotateScreen:270 / rotateTouch:0`。

## 5. UI 布局（videoView 透明窗 + 控制件）

### 5-1 画面显示：videoView 当透明窗口（DVR 预览核心）
```json
"videoview__1": {
  "caption": "VideoViewMain",
  "rotation": 3,          // ⚠️ 枚举 0/1/2/3 = 0°/90°/180°/270° 顺时针，不是角度值！
  "visible": true,        // ⚠️ 必须 true！false = UI 不透出，视频层白跑 = 没图像头号坑
  "position": {"left": 0, "top": 0, "width": 1600, "height": 600}  // 画面区域=控件区域
}
```
- videoView 在 UI 层开透明渲染窗口，下层 disp 视频层画面从该区域透出（**零关联代码**：不 play/不设源）
- 预览与回放可共用一个全屏 videoView（预览=透出窗口；回放=播放器）
- 控件区域内别放不透明图片/底色，会挡住透出

### 5-2 控制件
底部按钮排（录像/拍照/停止/回放）、状态栏（TextStatus 显示当前动作与结果）、回放文件列表（ZKListView 展示 getFiles 结果）、进度 SeekBar（拖动 seekTo 防抖 150ms）。

## 6. 摄像头接入

### 6-1 内置 AHD/TVI/CVBS（产品主力）
```cpp
// 前/后摄单例，各自 setParam 后 setVisible
mpi::CameraParam param;
param.mirror = false;
param.viewbox = {0, 0, 1920, 1080};     // 源裁剪（全幅）
param.display = {0, 0, 1600, 600};      // 目标显示区（UI 坐标全屏）
param.visible = true;
param.layer   = -1;                     // 默认自动
mpi::FrontCamera::instance().setParam(param, true);   // is_sync
mpi::RearCamera::instance().setParam(param, true);
// 切换视图：setupCamera(ViewType, sync)；显隐：setVisible(bool, sync)
// 缩放/平移：FrontCamera::instance().moveViewbox(x, y)
```
- 环境变量：`ZKCAMERA_DI_ENABLE`（隔行转逐行）、`ZKCAMERA_SKIP_FRAMES`（跳前 N 帧）
- 信号：AHD/TVI 720P/1080P 25/30、CVBS PAL/NTSC（DI 使能）

### 6-2 USB UVC（JPEG/MJPEG，外接摄像头）
```cpp
mpi::initializeSystem();
mpi::VideoDeviceRegistry::instance().add(mpi::VIDEO_DEVICE_REAR)
    .setFrameRate(0).setPictureSize({w, h}).setUvc(true).setId(mpi::DEVICE_ID_AUTO);
mpi::config().apply();
// 取流保活任务（防休眠断流）：SharedVideoDevice(REAR) 循环 wait
// 显示与 6-1 相同：RearCamera::instance().setParam(...)
```
⚠️ 详见 `v85x/uvc-usb-camera.md`：**ENUM_FMT+S_FMT 必须锁 MJPEG**（摄像头默认可能 YUYV，不协商=绿屏）；录制尺寸必须=UVC 实际分辨率。

## 7. 录像（mpi::Recorder）

### 7-1 启动参数（两种形态）
```cpp
// A. 产品级（内置多路）：组装 RecorderParam
//   front_video{1920,1080} rear_video{1920,1080} 等档位（1080P/2K/4K UI 档 → 实际分辨率映射表）
//   duration_per_file: 60/180/300s；audio.enable=录音开关；*_video.enable=true
mpi::Recorder::instance().start(param);

// B. UVC 单路简化：RecorderParameters + RecordingSettings
mpi::RecordingSettings s;
s.duration = 60;                        // 分段秒
s.audio = false;
s.bitrate = 8 * 1024 * 1024;
s.frame_rate = 25;                      // ⚠️ 必须 15~60！设 0 抛错
s.size = {uvc_w, uvc_h};                // ⚠️ = UVC 实际分辨率，否则绿屏
s.thumbnail_size = {0, 0};
s.video_format = mpi::FILE_FORMAT_MP4;  // mp4 / ts（AVI 等需确认）
mpi::RecorderParameters p;
p.settings[mpi::VIDEO_DEVICE_REAR] = s;
mpi::Recorder::instance().start(p);
```
### 7-2 控制与铁律
```cpp
mpi::Recorder::instance().stop();
isStarted(); state();            // UNSTARTED/RECORDING/EXCEPTION
elapseTime();                    // 已录毫秒 → UI 时间
lockNext(true);                  // 紧急录像（下一段锁定）
takePicture(rear);               // 拍照（200ms 防抖）
getFiles(type, view, lock, ...); // 文件列表
lockFile(file) / unlockFile(file);
```
- **录像期间不停预览/保活**（边录边看常态）；只有切流/拔插/进回放前才 `Recorder::stop + Camera::stop`（顺序反=黑屏）
- 分辨率/参数切换后必须 `restartRecorder(true)` 才生效
- 首次进入回放/播放页：先停 Recorder/FrontCamera/RearCamera，**50ms 延迟初始化 VO**（避免 MPP 资源冲突）

## 8. 拍照与回放（mpi::VO + JpegViewer + videoView）

```cpp
// 回放环境（延迟 50ms 初始化）
mpi::initializeSystem();
auto vo = std::make_shared<mpi::VO>(0);
vo->enable();
VO_PUB_ATTR_S attr = vo->getAttr();
attr.enIntfType = VO_INTF_LCD; attr.enIntfSync = VO_OUTPUT_NTSC;
vo->setAttr(attr);

// 照片显示（JpegViewer 走 disp 层，指定显示区域）
auto jpeg_viewer = std::make_shared<mpi::JpegViewer>(*vo);
jpeg_viewer->start(file, {l, t, w, h});  jpeg_viewer->stop();

// 录像播放（videoView 播放器；UI 布局 rotation 见 §5-1，枚举 3=270°）
mVideoView1Ptr->play(file.c_str());
stop() / pause() / resume() / seekTo(ms); getDuration() / getCurrentPosition();
```
- 文件分类：`mpi::FileType` FILE_TYPE_VIDEO/PHOTO；VIEW_FRONT/VIEW_REAR；普通/锁定/照片 分类列表
- 删除：多选后 `base::remove(file)`（fat32）；锁定/解锁走 lockFile/unlockFile
- 进度拖动防抖：SeekBar → handler 延迟 150ms → seekTo

## 9. 存储与录制卡（TF/EMMC）

- **录制卡有专属格式要求（FAT32+64KB 簇+OEM=zkswe），不满足弹「文件系统不符合要求」/自动重格** → 必读 `v85x/tfcard-format-requirement.md`
- 录像/照片目录约定：挂载点下 `/video`、`/photo`（如 `/mnt/extsd/video/Rear/*.mp4`）
- 容量查询：statfs 挂载点（total/free → UI 显示）
- 满卡处理：录满自动覆盖最老普通片段（循环录像，锁定片段不覆盖）；格式化会清空整卡（含锁定片段）

## 10. 调试排障（日志判据表，按现象查）

| 现象 | 看什么 | 结论 |
|------|--------|------|
| 预览黑屏 | logcat `rear camera fps` | fps≈0 = 取流/保活断；fps≈30 但没画面 = UI 层盖住（videoView 没 visible / 不透明背景），查 disp 层 |
| 录制出绿屏 | `ls -la` 录像文件大小 | **0 字节 = 取流断**（get video frame timeout / VENC no stream），不是编码参数问题 |
| 录像中断/黑屏 | fps 日志 | 边录边看正常：rear camera fps≈29 + venc fps≈25 |
| 一直提示格式化 | 卡文件系统 | 卡被电脑格过（簇≠64KB / exFAT/NTFS），用设备格式化 |
| 回放画面方向不对 | UI json rotation | rotation 是枚举 0-3，写 3 才是 270°（写 270 无效） |
| 回放绿屏但文件正常 | 播放链路 | 先停预览链路再进回放；VO 延迟初始化 |

**图层级检查**（无图像最有效）：`cat /sys/class/disp/disp/attr/sys`——看每层 enable/ch/z/frame/addr：
- 视频层 enable 且有 addr + UI 层 z=16 最顶 → 基本是 UI 不透明遮挡
- 启动异常残留层 → 启动早期调 releaseLayer 释放（保留 UI 层 ch2/layer0），代码见 `v85x/display-layer-debug.md`

## 11. 开发顺序自检清单（做完逐项打勾）

1. [ ] Manifest：platform=V85X + AWCHIP + aw-dvr **与 runtime 配套的版本**（默认 3.13.12，勿用 4.0.1；accessKey 已配）
2. [ ] 屏幕方向：rotateScreen 与硬件一致；改过 package.properties 已 clean 重编
3. [ ] UI：videoView `visible:true` + `rotation` 用枚举 0-3；画面区域无不透明遮挡
4. [ ] 摄像头：探测到设备；预览 disp 层 enable；方向正确
5. [ ] 录像：参数合法（frame_rate 15~60、size=实际分辨率）；边录边看正常；文件非 0 字节；`MPP_EVENT_RECORD_DONE`+done 路径
6. [ ] 回放：先停预览 + VO 延迟初始化；画面方向与预览一致；seek/删除/锁定可用
7. [ ] 存储：录制卡按 64KB 簇 FAT32（设备格式化）；容量显示正确
8. [ ] 边界：拔卡/满卡/切分辨率重启录像/热插拔 无黑屏绿屏

## 12. 参考
- `v85x/display-layer-debug.md`（图层/旋转/透出/回放方向排查四板斧）
- `v85x/tfcard-format-requirement.md`（录制卡格式化）
- `v85x/uvc-usb-camera.md` / `v85x/jpeg-decode-record.md`（UVC/JPEG 链路）
- `v85x/videoview-transparent-window.md`（videoView 透出权威口径）
- `devflow/package-properties-easyui-cfg.md`（工程配置机制）
