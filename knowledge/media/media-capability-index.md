---
id: media-media-capability-index
title: 多媒体能力索引（播放/录像/录音/图层/抓帧，唯一真源派生）
category: media
status: review
confidence: manual
verified_at: 2026-10-03
stale_days: 180
origin: derived
source: 由 media_capabilities.json 派生（scripts/gen_media_cap_doc.py）；平台可用性由 package_catalog.json 联接派生
needs_evidence: false
platforms: []
tags: [多媒体, 视频播放, 摄像头预览, 录像, 录音, 对讲, 图层, 视频层, 抓帧, vdec, zkshot, ffmpeg, 预装库, DVR, 软解, 图片解码]
evidence:
  - cmd: python scripts/gen_media_cap_doc.py --check
    expect: rc=0（本页与 media_capabilities.json 一致）
---

# 多媒体能力索引（播放 / 录像 / 录音 / 图层 / 抓帧）

> ⚠️ **本页是派生物，不要手改**（由 `media_capabilities.json` 派生，`--check` 进闸门）。
> 平台可用性那几列由包目录联接派生（"这块板能不能用某个包"看这里；包的版本/清单不在本页）。

## 1. 能力总表

| 能力 | 大类 | 用什么（包 / 免编译库） | 覆盖平台 | 出处 |
|---|---|---|---|---|
| **摄像头预览（DVR 主力：内置 AHD/TVI/CVBS 与 USB UVC）** | 自绘 / 图层 | 包：`aw-dvr`、`aw-mpp`、`aw-mpp-uvc`、`uvc-camera`、`ir-camera`、`uav-camera` | V85X | `dvr-recorder-guide.md` |
| **录像（写入 TF/EMMC）** | 录像 / 录音 | 包：`aw-dvr`、`aw-mpp`、`aw-cedarc` | V85X | `dvr-recorder-guide.md` |
| **拍照与回放** | 抓帧 / 取图 | 包：`aw-dvr`、`awjpegdecoder`、`aw-mpp`、`display_utility` | F133、F135、T113、V85X、Z20、Z21 | `dvr-recorder-guide.md` |
| **播放 H.264 流 / 文件** | 播放（视频/音频） | 包：`awh264player`、`h264-player`、`simple-player`、`ffmpeg`、`parsesps` | F133、F135、T113、V85X、Z20、Z21、Z261 | `builtin-packages.md` |
| **预烘帧序列（视频/动画转贴图）** | 自绘 / 图层 | — | 免编译库（不占包） | `custom-render-paths.md` |
| **自绘 / 离屏渲染（框架内 canvas、nanovg、cairo）** | 自绘 / 图层 | 包：`nanovg`、`blend2d`、`mi_gfx`、`display_utility`<br>库：libnanovg.so | F133、F135、T113、Z20、Z21、Z235X | `custom-render-paths.md` |
| **音频播放** | 播放（视频/音频） | 包：`audio-utility`、`faac`、`mp4v2`、`mad` | F133、T113、V85X、Z20、Z21、Z261 | `builtin-packages.md` |
| **对讲：录音 + 播放（双向）** | 录像 / 录音 | 包：`zkaudio`、`lylink_cpaacfapwd` | F133、T113、Z20、Z21、Z261 | `builtin-packages.md` |
| **多路录音** | 录像 / 录音 | 包：`multi-channel-audio-recorder` | Z20 | `builtin-packages.md` |
| **音频前处理（回声消除等）** | 编解码 / 图像 | 包：`webrtc-audio-processing`、`webrtc-aec` | T113、V85X、Z20、Z21 | `builtin-packages.md` |
| **JPEG / 图像解码** | 编解码 / 图像 | 包：`awjpegdecoder`、`zkmedia`、`giflib`、`gif`<br>库：libjpeg.so.9.1.0、libpng12.so.0.56.0 | F133、F135、T113、Z21 | `device-preinstalled-libs.md` |
| **软解兜底（ffmpeg）** | 编解码 / 图像 | 包：`ffmpeg` | F133、F135、T113、V85X、Z20、Z21、Z261 | `builtin-packages.md` |
| **设备预装可借库（dlopen 即用，免编译）** | 设备预装可借库（免编译） | 库：libmad.so.0.2.1、libjpeg.so.9.1.0、libpng12.so.0.56.0、libfreetype.so.6.11.4、libz.so.1.2.8、libnanovg.so | 免编译库（不占包） | `device-preinstalled-libs.md` |
| **抓帧：视频层（硬件 vdec 输出）** | 抓帧 / 取图 | — | 免编译库（不占包） | `device-screenshot.md` |
| **抓帧：UI/OSD 层（framebuffer）** | 抓帧 / 取图 | — | 免编译库（不占包） | `device-screenshot.md` |

## 2. 能力明细

### 2.1 播放（视频/音频）

#### 播放 H.264 流 / 文件

- **做什么**：按平台选实现：全志系（V85X/T113）有硬解播放器；SigmaStar（Z20/Z261）走 h264-player；F133/F135 走 awh264player。
- **用哪些包**：`awh264player`、`h264-player`、`simple-player`、`ffmpeg`、`parsesps`
- ⚠️ 同一功能在不同平台是不同包 —— 先 flythings_query_package 确认目标平台有没有
- ⚠️ 要软解/容器解析兜底时才上 ffmpeg（体积大）
- ⚠️ 抽帧/取一帧参考「视频层抓帧」那条（硬解通道），别用软件逐帧解
- **常被问成**：「视频播放用什么包」 / 「H264 播放怎么做」 / 「这块板能放视频吗」
- **出处**：`knowledge/devflow/builtin-packages.md`

#### 音频播放

- **做什么**：通用播放用 audio-utility；容器/编码链路用 mp4v2 + faac。
- **用哪些包**：`audio-utility`、`faac`、`mp4v2`、`mad`
- **常被问成**：「音频播放用什么」 / 「MP3 播放怎么做」 / 「怎么放声音」
- **出处**：`knowledge/devflow/builtin-packages.md`

### 2.2 录像 / 录音

#### 录像（写入 TF/EMMC）

- **做什么**：mpi::Recorder 启停录像；录制参数有两种形态（见 Playbook §7-1）。
- **用哪些包**：`aw-dvr`、`aw-mpp`、`aw-cedarc`
- **入口**：src/logic/*.cc 里启停 Recorder
- **参考工程**：`demos/dvr-uvc-recorder-v85x`
- ⚠️ 录制目标盘必须先确认可写与剩余空间（TF 未挂载/写保护会静默失败）
- ⚠️ 停止录像后要等落盘再断电，否则文件尾损坏
- **常被问成**：「录像怎么写进 TF 卡」 / 「录像怎么启停」 / 「录出来的文件坏了」
- **出处**：`knowledge/v85x/dvr-recorder-guide.md`

#### 对讲：录音 + 播放（双向）

- **做什么**：zkaudio 提供对讲的录音与播放；互联类型走 lylink_cpaacfapwd。
- **用哪些包**：`zkaudio`、`lylink_cpaacfapwd`
- ⚠️ 对讲是「采 → 编码 → 传输 → 解码 → 播」全链路，任何一段平台不支持就整体不可用
- ⚠️ 回声问题先上 webrtc-audio-processing，别先改音量
- **常被问成**：「对讲怎么实现 录音和播放」 / 「双向语音怎么做」 / 「回声很大」
- **出处**：`knowledge/devflow/builtin-packages.md`

#### 多路录音

- **做什么**：multi-channel-audio-recorder（目前只在 z20 包键下）。
- **用哪些包**：`multi-channel-audio-recorder`
- **常被问成**：「多路录音怎么做」 / 「同时录多路音频」
- **出处**：`knowledge/devflow/builtin-packages.md`

### 2.3 抓帧 / 取图

#### 拍照与回放

- **做什么**：拍照走 mpi::VO 取帧；回放用 JpegViewer / videoView。
- **用哪些包**：`aw-dvr`、`awjpegdecoder`、`aw-mpp`、`display_utility`
- **入口**：src/logic/*.cc（拍照/回放按钮回调）
- **参考工程**：`demos/dvr-uvc-recorder-v85x`
- **常被问成**：「拍照怎么存」 / 「怎么回放录像」 / 「JpegViewer 怎么用」
- **出处**：`knowledge/v85x/dvr-recorder-guide.md`

#### 抓帧：视频层（硬件 vdec 输出）

- **做什么**：屏上在放视频时，fb0 抓到的是 UI 层（可能全黑）；要画面得抓视频层。
- **入口**：flythings_device_screenshot(layer='video')（内部 zkshot + vdec 通道）
- **平台**：Z20、Z21
- ⚠️ 仅 SigmaStar（Z20/Z21）支持；其它平台该参数不适用
- ⚠️ 多路/拼墙必须给 vdec_chn（拼墙在 chn 1），否则取不到帧
- ⚠️ 取帧走 MI_SYS 输出口 + 物理地址映射（非文件读取），失败时先核对通道号
- **常被问成**：「拼墙抓不到画面」 / 「vdec 通道怎么选」 / 「抓屏是黑的 视频在哪一层」 / 「视频层抓帧怎么做」
- **出处**：`knowledge/devflow/device-screenshot.md`

#### 抓帧：UI/OSD 层（framebuffer）

- **做什么**：默认抓屏路径：读 framebuffer（UI 层）。
- **入口**：flythings_device_screenshot(device=…) 默认路径
- ⚠️ 屏上放过视频时这层可能是空的 —— 那不是抓屏坏了，是画面不在这一层
- ⚠️ 双缓冲 pan 偏移、旋转、裁剪会影响取图，参数见文档
- ⚠️ 抓屏前应先做有界预检（读不通就立刻给结论，别把时间耗在等待上）
- **常被问成**：「抓屏是黑的」 / 「framebuffer 抓屏」 / 「怎么截屏」
- **出处**：`knowledge/devflow/device-screenshot.md`

### 2.4 自绘 / 图层

#### 摄像头预览（DVR 主力：内置 AHD/TVI/CVBS 与 USB UVC）

- **做什么**：把摄像头画面显示到屏上：UI 里用 videoView 当**透明窗口**（visible=true + rotation），画面由硬件层直接出。
- **用哪些包**：`aw-dvr`、`aw-mpp`、`aw-mpp-uvc`、`uvc-camera`、`ir-camera`、`uav-camera`
- **入口**：ui/*.json 的 videoView（透明窗）+ Manifest 依赖 aw-dvr
- **参考工程**：`demos/dvr-uvc-recorder-v85x`
- ⚠️ videoView 是透明窗，不是普通显示控件：不要给它填背景图
- ⚠️ 屏幕方向错位先查 rotateScreen 与 videoView 的 rotation（竖装屏 = 270）
- ⚠️ USB UVC 是 JPEG/MJPEG 流；AHD/TVI/CVBS 走内置通道，两者接入方式不同
- **常被问成**：「摄像头预览怎么做」 / 「videoView 透明窗是什么」 / 「内置 AHD/TVI 摄像头怎么接」 / 「USB UVC 摄像头怎么显示」
- **出处**：`knowledge/v85x/dvr-recorder-guide.md`

#### 预烘帧序列（视频/动画转贴图）

- **做什么**：PC 侧离线渲好，运行时按序列换图 —— 视觉最好、运行时几乎零成本，只适合固定视角/固定逻辑。
- **入口**：resources/images/ 的帧序列 + 定时器切 visible
- ⚠️ 适合固定逻辑的动画/循环；需要实时交互的不要用
- ⚠️ 帧数 × 分辨率直接吃 flash 与内存，先算体积
- **常被问成**：「视频转贴图」 / 「预烘帧序列怎么做」 / 「动画卡顿 用帧序列」
- **出处**：`knowledge/devflow/custom-render-paths.md`

#### 自绘 / 离屏渲染（框架内 canvas、nanovg、cairo）

- **做什么**：五条渲染路径见 Playbook；面积小走框架内自绘，全屏动画才上独立图层。
- **用哪些包**：`nanovg`、`blend2d`、`mi_gfx`、`display_utility`
- **可借的库**：libnanovg.so（矢量绘制，设备预装）
- ⚠️ 一帧绘制面积 < 屏幕 1/4 且非全屏动画 → 框架内自绘就够
- ⚠️ 画布方案：ZKTextView/ZKButton + setBackgroundBmp 挂内存位图，只调一次 + setInvalid 交替刷帧
- ⚠️ 离屏渲染（cairo/SDL/LVGL 渲到内存）在 FlyThings 上尚未验证，要做需自行自证
- **常被问成**：「全屏动画性能不够怎么办」 / 「离屏渲染可行吗」 / 「nanovg 能不能用」 / 「cairo SDL LVGL 画东西」
- **出处**：`knowledge/devflow/custom-render-paths.md`

### 2.5 编解码 / 图像

#### 音频前处理（回声消除等）

- **做什么**：webrtc-audio-processing；另有 webrtc-aec 包键。
- **用哪些包**：`webrtc-audio-processing`、`webrtc-aec`
- **常被问成**：「回声消除怎么做」 / 「webrtc 音频处理」
- **出处**：`knowledge/devflow/builtin-packages.md`

#### JPEG / 图像解码

- **做什么**：硬件/专用解码用 awjpegdecoder（部分平台）；通用图像用 giflib/libjpeg；F133/F135 另有 zkmedia。
- **用哪些包**：`awjpegdecoder`、`zkmedia`、`giflib`、`gif`
- **可借的库**：libjpeg.so.9.1.0（设备预装）、libpng12.so.0.56.0（设备预装）
- ⚠️ 设备预装库能借就借（免编译、免进 Manifest），但要在目标设备上确认存在且 ABI 匹配
- ⚠️ 借库前先读 device-preinstalled-libs.md 的三条使用纪律
- **常被问成**：「JPEG 解码怎么做」 / 「图片解码用什么」 / 「gif 怎么显示」
- **出处**：`knowledge/devflow/device-preinstalled-libs.md`

#### 软解兜底（ffmpeg）

- **做什么**：覆盖面最广（10 个包键），硬解不可用或要解非常规容器/编码时用它。
- **用哪些包**：`ffmpeg`
- ⚠️ 软解吃 CPU，全屏高码率视频会掉帧 —— 优先找硬解路径
- ⚠️ 引入 ffmpeg 会显著增大镜像体积，确认 flash 余量
- **常被问成**：「ffmpeg 在这块板上能用吗」 / 「软解兜底」 / 「非常规编码怎么解」
- **出处**：`knowledge/devflow/builtin-packages.md`

### 2.6 设备预装可借库（免编译）

#### 设备预装可借库（dlopen 即用，免编译）

- **做什么**：设备上已有的 .so 可直接 dlopen，不必进 Manifest。
- **可借的库**：libmad.so.0.2.1（MP3 解码）、libjpeg.so.9.1.0（JPEG 解码）、libpng12.so.0.56.0（PNG 解码/编码）、libfreetype.so.6.11.4（字体光栅化）、libz.so.1.2.8（zlib）、libnanovg.so（矢量绘制）
- ⚠️ 先按文档 §1 的两条命令在**目标设备**上确认库存在（不同固件清单不同）
- ⚠️ 确认 ABI/依赖/SONAME（readelf），否则 dlopen 失败或崩在符号解析
- ⚠️ 设备预装库不进 Manifest —— 别把它写成包依赖
- **常被问成**：「能不能不编译直接用设备上的库」 / 「预装库 dlopen」 / 「设备上有哪些 so」
- **出处**：`knowledge/devflow/device-preinstalled-libs.md`

## 3. 画面到底在哪一层（抓帧/叠加必读）

| 图层 | 平台 | 怎么取帧 / 入口 | 说明 |
|---|---|---|---|
| **UI(OSD) 层** | 全平台 | 读 `/dev/fb0` | 框架（zkgui）画的都在这层。抓 fb0 拿到的就是这层 —— 屏上放过视频时，这层可能是空的/黑的。 |
| **视频层（MI 硬件图层）** | Z20、Z21 | flythings_device_screenshot(layer='video') → 设备端 zkshot 从 vdec 输出口取帧 | 与 fb0 双缓冲无关；多路/拼墙要指定 vdec 通道（拼墙播放器在 chn 1，工具默认 chn 0）。 |
| **独立硬件图层（disp layer）** | V85X | 框架外的层，与 UI 并行；需自行管理顺序/裁剪/释放 | 性能最好的一路；已验证但要守 releaseLayer 纪律（用完释放，否则层泄漏）。 |

> ⚠️ **视频层（MI 硬件图层）**：屏上在放视频而 fb0 抓出来是黑的 = 正常（视频在硬件图层，不在 OSD 层）
> ⚠️ **视频层（MI 硬件图层）**：多路/拼墙抓帧必须给 vdec_chn，否则取帧失败或空帧
> ⚠️ **视频层（MI 硬件图层）**：别把「屏保 = chn 0」当通则：屏保的软解路径与拼墙的硬解通道是两回事
> ⚠️ **独立硬件图层（disp layer）**：画面是「视频/摄像头」类且要全屏高帧率 → 走本路，别用软件绘制硬拼
> ⚠️ **独立硬件图层（disp layer）**：releaseLayer：离开页面/停止播放必须释放，参考 demos/dvr-uvc-recorder-v85x

## 4. 平台可用性（能力 × 平台，由包目录派生）

| 能力 | Z20 | Z21 | F133 | F135 | T113 | V85X | Z235X | Z261 |
|---|---|---|---|---|---|---|---|---||
| 摄像头预览（DVR 主力：内置 AHD/TVI/CVBS 与 USB UVC） |  |  |  |  |  | ✓ |  |  |
| 录像（写入 TF/EMMC） |  |  |  |  |  | ✓ |  |  |
| 拍照与回放 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |
| 播放 H.264 流 / 文件 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |
| 自绘 / 离屏渲染（框架内 canvas、nanovg、cairo） | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  |
| 音频播放 | ✓ | ✓ | ✓ |  | ✓ | ✓ |  | ✓ |
| 对讲：录音 + 播放（双向） | ✓ | ✓ | ✓ |  | ✓ |  |  | ✓ |
| 多路录音 | ✓ |  |  |  |  |  |  |  |
| 音频前处理（回声消除等） | ✓ | ✓ |  |  | ✓ | ✓ |  |  |
| JPEG / 图像解码 |  | ✓ | ✓ | ✓ | ✓ |  |  |  |
| 软解兜底（ffmpeg） | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |

`✓` = 该能力的**至少一个包**在这个平台可用（包级细节用 `flythings_query_package`）。只借免编译库的能力（预烘帧序列（视频/动画转贴图）、设备预装可借库（dlopen 即用，免编译）、抓帧：视频层（硬件 vdec 输出）、抓帧：UI/OSD 层（framebuffer））不在此表 —— 它不占包，按设备实有库确认。

## 5. 公开版边界（别把「没写」当成「没有」）

> 公开版（open）保证的是**能力面与工具契约**：能做什么、在哪些平台、用哪个包、怎么调用。

- **未收录**：V85X 绑定的私有媒体栈深度（MPP / DVR / UVC / 图层调试 / 录制卡格式化等 aw-dvr 系）—— 本页的能力、平台、包名仍然可用，但那层的**实现细节与实测结论**不在公开版
- **未收录**：`demos/` 参考工程（依赖私有包，release 不随包；见 PUBLISH.md 第 3 节）

- **为什么**：那些深度结论依赖 V85X 真机实测与私有参考工程，公开版不带这些材料；写了也没有可复现的出处（本项目口径：未验证的一律显式写出、不静默）。
- **那你该怎么做**：要那层深度时以平台方 SDK 与厂家资料为准；本页 + `flythings_query_package` 足够回答「能不能做、在哪些板子、用哪个包」。**全局口径（哪些知识不在 open 版、查不到怎么办）的真源是 `knowledge/devflow/capability-boundaries.md` 第 2 节**，本节只留多媒体特有的事实。
