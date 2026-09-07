# 🖥️ V85X 摄像头自维护出图 → videoView 零代码透出视频层（透明渲染区域）

> 2026-09-07 沛哥知识补充（来源：V85X 平台实测经验）。官方口径佐证：video 控件「轮播类型=否」时
> **仅创建一个视频渲染区域，除此以外没有其他操作**（wiki `uicontrols/video.md`）。
> 适用：**V85X**（V853/V553 等）摄像头画面由**用户自己打开并维护显示内容**的场景。

## 0. 一句话知识

**V85X 摄像头如果显示内容由用户自己打开维护（不走 FlyThings 预览/播放链路，画面直接由用户代码/底层输出到 Video 层），
UI 上只需要添加一个 videoView 控件——不需要写任何关联代码（不 play / 不 startPreview / 不设源），
画面就会从该控件区域透出来。videoView 在 UI 层开了一块透明渲染区域，Video 层的内容经此透出。**

## 1. 场景区分（先判断属于哪条路，禁止套错）

| 场景 | 画面谁在驱动 | UI 做法 | 代码 |
|------|-------------|--------|------|
| A. 倒车/实时预览（内置链路） | ZKCameraView（easyui 预览） | cameraview 控件 | setDevPath/setFormatSize/startPreview 等 |
| B. 播放文件/回放/拉流 | ZKVideoView（easyui 播放器） | videoview 控件 | `play(path, 0)` / pause / resume / stop |
| C. **摄像头自维护出图（本知识点）** | **用户/系统自己打开摄像头并把内容输出到 Video 层** | **videoview 控件（仅作透明渲染窗口）** | **零代码，不需要 play/关联** |

⚠️ A/B 的详细字段与坑位见 `uicontrols/cameraview-fields.md`（实时预览/播放禁混用）；
本文专讲 **C 场景**——videoView 不当播放器用，当"视频层窗口"用。

## 2. 操作步骤（极简）

1. UI 布局里放一个 **videoView 控件**（属性「轮播视频类型」= 否，即非轮播）
2. **位置/尺寸即画面显示区域**：videoView 放哪、多大，视频层画面就从哪透出
3. 编译运行——**不需要在 logic.cc 里写任何关联代码**
   - 不调用 `play()` / `stop()` / `setVideoPath` 之类
   - 控件自动生成的 `onVideoViewPlayerMessageListener_XXX` 回调也可不填（没人播报不了状态，不影响透出）
4. 摄像头画面由用户侧逻辑（V4L2/系统服务/第三方出图层等）打开维护，输出进 Video 层即可

## 3. 原理与要点

- **videoView = UI 层给 Video 层开的透明窗口**：UI 是独立一层，Video 层内容在下面；
  videoView 控件区域不画不透明背景 → 透明 → Video 层画面从该区域透出显示
- 画面区域完全由 videoView 的 position（left/top/width/height）决定，不随控件背景图/文字影响
- 用户自己的出图代码与 FlyThings UI **互不感知**：出图侧无需知道 UI 结构，UI 侧无需知道出图细节
- 想隐藏画面：把该 videoView `setVisible(false)` 或移出可视区即可（透出随控件显隐/位置走）

## 4. 坑位清单

1. **别画不透明背景**：videoView 区域内不要放不透明的图片/底色覆盖，否则 Video 层被 UI 层挡住透不出来
2. **别当场景 A/B 套代码**：这是"用户自维护出图"专用场景；若走 FlyThings 播放链路却只放控件不 play，画面也不会自己来
3. **平台限定**：本条为 V85X 平台经验（Video 层与 UI 分层叠加）；其他平台（F133/T113/Z20）摄像头显示按各自链路处理，不要直接套用
4. 若透出区域大小/位置不对 → 改 videoView 的 position，不是改出图侧

## 5. 参考

- 官方 wiki `uicontrols/video.md`（非轮播=仅创建视频渲染区域）
- `uicontrols/cameraview-fields.md`（场景 A/B 控件字段与禁混用铁律）
- `v85x/uvc-usb-camera.md` / `v85x/jpeg-decode-record.md`（V85X 视频层相关实测）
