# Demo: DVR 录制功能参考工程（V85X · USB UVC 摄像头 · 全链路验证过）

> 平台：**V85X**（AW_V853/V553，Manifest `platform="V85X"` + 宏 AWCHIP=AW_V853）。
> 屏幕：**1600×600 横 UI + 600×1600 竖装屏**（`package.properties` rotateScreen 270 硬件适配示例）。
> 摄像头：单路 **USB UVC（JPEG/MJPEG）**。
> 状态：**真机全链路验证通过**（预览/拍照/录像/停止/回放，含绿屏/黑屏/图层/方向坑位修复）。
> 定位：**参考代码，照抄改改就能跑**——验证全功能的 demo 案例，随 open MCP 分发（`demos/`）。
> 配套知识：`knowledge/v85x/dvr-recorder-guide.md`（DVR 开发 Playbook，本工程是它的可运行实现）。

## 📁 工程结构（哪些是重点）

| 文件 | 作用 | 对应 Playbook |
|------|------|------|
| `Manifest.xml` | V85X 平台 + **aw-dvr 私有包**（accessKey 占位，见下） | §2 |
| `package.properties` | `EasyUI.cfg={"rotateScreen": 270}` 竖装屏硬件适配（横装屏删此行） | §4 |
| `ui/main.json` | videoView 全屏**可见透明窗**（visible:true + rotation:**3**=270°）+ 底部 6 按钮 + 状态栏 | §5 |
| `src/logic/mainLogic.cc` | **全链路逻辑**：探测协商 → 预览 → 拍照 → 录像 → 停止 → 回放 + releaseLayer 图层释放 | §6/7/8 |
| `src/activity/` | IDE/构建自动生成，**禁止手改** | - |

## 🚀 三步跑起来

1. **替换 accessKey**：`Manifest.xml` 里 aw-dvr 的 `accessKey="0000...0000"`（发布版默认全 0 占位）替换成实际 key（aw-dvr 是 accessKey 私有包，key 向平台方获取；全 0 拉不到包）
2. **拉依赖**：`fun install`（需要 fun/fui 工具链，IDE 自带或项目内放置）
3. **编译部署**：改过 json 先 `cd ui && fui.exe pack main.json` → `fun build` → `fun launch`（设备 adb 在线）

## 🎮 功能与预期（底部 6 按钮）

| 按钮 | 动作 | 预期/验证点 |
|------|------|------|
| 1 Detect | 扫 /dev/video* 找 uvcvideo → ENUM_FMT → S_FMT 锁 MJPEG | 状态栏显示协商结果 |
| 2 Preview | 注册 REAR UVC(setUvc) → 保活任务 → RearCamera 全屏预览 | **画面正常透出**（黑屏查 §10 日志判据） |
| 3 Photo | Snapshot 拍照 | 生成 JPEG |
| 4 Record | Recorder 录 MP4（**size=UVC 实际分辨率**，边录边预览） | 录像中预览保持不黑；文件非 0 字节 |
| 5 Stop | 停录像→停预览→停保活，列出最新录像 | 状态栏显示路径 |
| 6 Play | videoview 回放最新录像（rotation:3 已转正） | 画面方向与预览一致 |

## 🔑 代码里的关键坑位（都修过，别回退）

- **videoView `visible:true`**：false = UI 不透出 disp 视频层 = 预览黑屏头号坑
- **videoView `rotation` 是枚举 0/1/2/3**（=0°/90°/180°/270°），写 3 才是 270°；写角度值 270 无效
- **录像 `s.size = UVC 实际分辨率`**（Detect 协商值），照抄 720P/1080P 档 = 绿屏
- **`s.frame_rate` 必须在 15~60**（UVC 25/30 就写 25/30）
- **录像中不停预览/保活**（边录边看是常态）；进回放前先 stop 全链路
- **releaseLayer()**（onUI_init 调用）：启动释放残留 disp 层（保留 UI 层 ch2/layer0），防错屏/层叠
- **录制卡格式化**：V85X TF 录制卡要求 FAT32+64KB 簇（电脑格式化卡会被弹窗拒），见 `knowledge/v85x/tfcard-format-requirement.md`

## 🧩 改成内置 AHD/TVI 双路摄像头（产品主力形态）

本 demo 走 UVC 单路（最易复现验证）；产品 DVR 一般是内置前/后路（TP9950 等）：
- 摄像头注册：去掉 `VideoDeviceRegistry...setUvc(true)`，改用 `mpi::FrontCamera/RearCamera` 单例 `setParam({viewbox/display/visible})`
- 录像：`RecordingSettings.settings[mpi::VIDEO_DEVICE_FRONT/REAR]` 分别配（结构与 demo 相同：duration/audio/bitrate/frame_rate/size/thumbnail_size），分辨率档位 720P/1080P 等由产品设置项映射
- 详见 `knowledge/v85x/dvr-recorder-guide.md` §6/§7

## 📚 日志观察

```bash
adb logcat | grep -E "UvcTest|dvr|Exception"
# 录像成功判据：rear camera fps≈30 / MPP_EVENT_RECORD_DONE+done 路径 / media play ok
```
