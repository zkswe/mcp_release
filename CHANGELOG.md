# CHANGELOG — FlyThings MCP Open

> 版本迭代记录（按版本从新到旧）。当前版本：**v0.17.0-open**（2026-09-04）。
> 每次迭代在本文件顶部新增一节；MCP_FEATURES（kb_tools.py）只保留精华摘要，完整历史以本文件为准。

---

## v0.17.0-open (2026-09-04) — data-icon 图标默认风格改为 emoji 彩色，风格在 HTML 原型阶段选定
**V553 项目反馈：强制线框风格不适用所有产品（医疗白底 UI 需要彩色图标），且风格应在 HTML 出效果稿时就确认下来，而不是转换后才发现。**
- ★ gen_res.py 新增 `_GLYPH_EMOJI` 映射表：46 个图标中 39 个有彩色 emoji 字形（带 VS16 强制彩色呈现）；menu/more/power/share/bluetooth 等无对应彩色 emoji 的自动降级线框，不断链
- ★ gen_res.py 新增 `_emoji_img()` / `emoji_icon_ss()`：emoji **4x 超采样**渲染（3 倍画布居中修顶部裁切 + bbox 裁剪 + 最长边 86% 画布适配 + LANCZOS 缩回），替代 1x 直画的旧 `emoji_icon`（旧函数保留兼容）
- ★ gen_res.py 新增 `glyph_icon_ex(style=)` 统一入口：`emoji`（默认）/ `line`（iconfont 矢量线框，等价 glyph_icon）/ `ai`（AI 生图，失败降级 emoji → 线框）；按下态 emoji/ai 压暗 20%、line 提亮 35%；非正方 canvas 居中语义与 glyph_icon 一致；`ai_icon` 重构出 `_ai_img` 复用
- ★ html2json.py 支持 `data-icon-style="emoji|line|ai"`（缺省 emoji，非法值回退 emoji）；生成文件名带风格标识（`icon_play_24x24_emoji.png` / `icon_play_24x24_line_1E88E5.png`），同控件不同风格不冲突
- ★ HTML_SUBSET.md 图标章节改写：「图标优先」保留（仍禁止按钮+文字），风格三选一在 HTML 原型阶段写明，preview.html 预览即最终效果

---

## v0.16.0-open (2026-09-03) — 图标抗锯齿根治（沛哥反馈 png 仍有锯齿）
**根因不是提示词约束，是渲染管线三处缺陷（程序化定位）**：
- ① iconfont 图标超采样只有 4 倍：小尺寸（20-40px）斜线阶梯仍可见 → **提高到 8 倍**（SS 画布 + LANCZOS 缩回，A/B 实验 ss16 最优、ss8 已接近）
- ② PIL line 端点是平头（butt cap），Feather 风格应为圆头 → 所有线段/折线/圆弧端点**补圆头 round cap**（斜线端点毛刺/缺口感的来源）
- ③ assets 兜底图标 icon_circle/line_icon/frames_loading/frames_loading_gif **此前 1x 直画，0% 抗锯齿必锯齿** → 全部改为超采样渲染（量化：AA 占比 0%→39%）
- 回归：46 图标 + 15 中文别名 + pressed 两态 + 非正方 canvas + 8 种线条兜底共 **115 项全过**；修复后 80px 平滑放大目检「斜线平滑无锯齿、端点圆润无毛刺、符合高清显示标准」

---
## v0.15.0-open (2026-09-03) — 图标优先规范落地：HTML 生成强制用 iconfont 矢量线框图标，禁止按钮+文字糊弄
**沛哥定规：生成 UI 时常用操作（返回/播放/暂停/上一首/下一首/设置/搜索/删除/刷新/确认/关闭/加减/音量/主页/菜单等）必须用图标表达，禁止用「按钮+文字」！**
- ★ gen_res.py 新增 **46 个 iconfont 风格矢量线框图标库**：back/forward/up/down/close/check/plus/minus/menu/more/search/home/list/play/pause/stop/prev/next/power/volume/mute/delete/edit/share/download/upload/user/lock/info/warning/camera/clock/calendar/bell/mic/location/mail/eye/video/phone/settings/refresh/wifi/bluetooth/heart/star（Feather 同款 24 网格坐标 + 数学采样抗锯齿 + 中文别名，形状程序化验证）；按钮自动 normal+pressed 两态（_p 提亮），非正方画布自动居中
- ★ html2json.py 识别 `data-icon="play"` / `class="iconfont icon-play"` / `class="btn icon-play"` → 自动生成 PNG 落 json：图标按钮→picTab{pic0,pic1} 两态图，纯图标→textview backgroundPic；未收录名 warning 列出可用表
- ★ json2html.py 预览图片 base64 内联（preview.html 单文件独立显示，ui/ 下不破图）
- ★ HTML_SUBSET.md + kb_tools 工具描述新增「🎯 图标优先」引导：46 个图标词表（中文别名自动映射）+ 写法示例（btn data-icon / icon data-icon / i.iconfont icon-xxx）
- 工具链验证：端到端测试通过（HTML 图标→html2json→json 引用→json2html 内联显示）

---
## v0.14.0-open (2026-09-03) — 自定义字库修正：fun 流程权威规则（font/ + enable.font.location，非 .prefs）

**重写 knowledge/devflow/custom-font-config.md（沛哥 20:51 纠正 v0.13 方向错误）**
⚠️ v0.13.0 按 KlipperF133 写入的「改 .prefs font 字段」是 IDE 视角，**fun 流程不适用、不需要**。

fun build/launch 流程换字库标准 4 步（沛哥定规，AI 引导「换库」直接照做，禁止绕 IDE 属性）：
① 项目根建 font/ 文件夹拷入 ttf（仅支持 ttf）② package.properties 加 enable.font.location=true
（新模板已内置，没有才补）③ 单字体→自动全局默认、代码零改动；多字体按文件名 ASCII 排序最靠前为默认、
个别控件 setFontFamily("文件名不含后缀") 指定（easyui≥2.2.0）④ 完成，不动 .prefs/IDE 属性。

机制：字库是运行时资源不参与编译，fun launch 随资源推送；Z20/Z21/H500S/T113/V85X 及后续平台系统内置
fzcircle.ttf（思源黑体裁剪版），项目 font/ 存在字体后完全使用项目字体；字库不含 emoji/特殊符号
（■●⌫℃▲▼），布局文本只用汉字+ASCII+基础符号，图标转 PNG。实测样例：mark_cv201 根 font/sans.ttf
+ enable.font.location=true。

**同步**：rag_index 重建；版本 0.13.0→0.14.0-open。

---

## v0.13.0-open (2026-09-03) — 自定义字库配置入库（改 .prefs font 字段替换全局默认字库）

**新建 knowledge/devflow/custom-font-config.md（沛哥 20:43 讲解 + KlipperF133 实测 + mark_cv201 对照）**

两条路先分清：
- **全局默认字库替换（整 UI 换字体，不用代码）= 改 .prefs 的 font 字段**（沛哥定规）：
  `.settings/com.zksw.flythings.easyui.prefs` 里 easyui.cfg.debug 与 easyui.cfg.release 两份 JSON 都加
  "font" 字段指向自定义 ttf（实测 KlipperF133：debug=/mnt/extsd/ui/KaiTi.ttf、release=/res/ui/KaiTi.ttf，
  与同 JSON resPath 对应）；ttf 放工程 resources/ 编译打包到设备 ui 目录；默认模板 .prefs 无 font 字段
  = 用内置 fzcircle.ttf（思源黑体裁剪），写了 = 全系统换自定义字库；IDE 对应：项目属性→字体→取消默认
  导入新 ttf（仅支持 ttf）
- **多字体混排（控件级指定）= enable.font.location=true + font/ 目录 + setFontFamily**（wiki font_setting.md，
  mark_cv201 font/sans.ttf 用此法；easyui 2.2.0+；setFontFamily 参数=文件名不带 .ttf；多字体按 ASCII 排序
  最前作默认）

补充：package.properties 覆盖层也可配 font（F133UhaleAlbum 实测冒号分隔 debug:release 两路径）。
坑：全局换字体别写 setFontFamily；.prefs 改 font 不生效查 debug/release 双改 + ttf 打包路径。

**同步**：rag_index 重建；版本 0.12.0→0.13.0-open。

---

## v0.12.0-open (2026-09-03) — package.properties / EasyUI.cfg 工程配置机制入库（屏幕旋转适配）

**新建 knowledge/devflow/package-properties-easyui-cfg.md（沛哥讲解机制定规 + mark_cv201 双工程实测）**
来源：CV201_PND（1600×600，rotateScreen:270）vs CV201_PND_1024_600（1024×600，无 rotateScreen）对比 +
沛哥提供 EasyUI.cfg 标准 JSON 格式；全 workspace 13 工程横向统计 + ConfigManager.h + 代码消费链查证。

核心机制（沛哥 2026-09-03 定规）：
- **编译工具自动生成完整 EasyUI.cfg**（默认 JSON：baud/defBrightness/font/languageCode/languagePath/
  resPath/rotateScreen/rotateTouch/screensaverTimeOut/startupLibPath/startupTouchCalib/touchDev/uart/
  zkdebug，debug=/mnt/extsd 与 release=/res 两套路径）
- 工程根目录 package.properties 的 EasyUI.cfg={...} **是覆盖层**：写哪个字段优先采用哪个，
  不需要特殊处理的字段不用写（不整段照抄）
- 与 .settings/com.zksw.flythings.easyui.prefs（IDE 属性）并存时 **package.properties 优先**
- enable.font.location=true 是独立开关（font/ 目录自定义字体，非 EasyUI.cfg 覆盖层）

**何时用 package.properties 覆盖（沛哥 20:12 补充定规）**：正常情况（屏幕与触摸方向一致/都不转）
**发 .prefs 配置即可**，不用写 package.properties；只有需要特殊处理覆盖时才用——典型场景 =
**某些硬件屏幕需要旋转、触摸不需要旋转**（方向不一致），此时只覆盖 rotateScreen、rotateTouch 不写/
保持默认（mark_cv201 CV201_PND 正例：只配 rotateScreen:270 不配 rotateTouch）；
同值成套的常规旋转（F133 工程 rotateScreen:270+rotateTouch:270）走 .prefs 就够。

字段表（文档内）含 rotateScreen 0/90/180/270 + rotateTouch（触摸坐标旋转）；watchDogEnable 等其它字段
以编译工具生成为准，需要才覆盖。

核心经验：**屏幕旋转跟随设备物理安装方向，不是 UI 决定**（同 1600×600：lib_uav_camera 不转、
CV201_PND 转 270；T113 PND 竖装横显同款 rotateScreen:270）；改方向只改 package.properties 不碰
.ftu/代码；代码侧 CONFIGMANAGER->getScreenRotate() 读取（link 投屏 disp_rot_e=getScreenRotate()/90、
V85X 摄像头 setRotation 跟随）；mark_cv201 倒车 get_camera_rot() 是摄像头画面另一路参数勿混淆。

**同步**：rag_index 重建；版本 0.11.0→0.12.0-open。

---

## v0.11.0-open (2026-09-03) — cameraview(ZKCameraView) 相机预览控件 ftu/json 字段规范入库

**新建 knowledge/uicontrols/cameraview-fields.md（沛哥指定学习 LearningProject/mark_cv201 倒车影像工程）**
来源：CV201_PND（1600×600）+ CV201_PND_1024_600（1024×600）双分辨率 fui unpack 实测校准（V85X/AW_V853）。

核心铁律：
- **实时摄像头预览用 cameraview；播放文件/回放/拉流用 videoview，禁止混用**
  （cameraview=ZKCameraView 接 /dev/video 实时预览/拍照/多通道；videoview=ZKVideoView 播文件，
  loopPlayback/defaultVolume 是 videoview 字段。mark_cv201 分工：reverse=倒车 cameraview，
  reverse2 回放/Dvr/lylinkview=videoview）
- cameraview 必须嵌 window 容器内（window → cameraview + painter overlay），不做顶层裸控件
- formatSize 是视频源分辨率（如 640×480）不是控件大小；控件铺满窗口，等比裁剪适配用代码 setCropPosition

json 字段（实测）：autoPreview:true(自动预览关键)/backgroundColor/caption/cvbs:false(数字源)/
formatSize{640,480}/id 97001 段/mirror:0(EMirror)/touchable:false/position 全屏；
同容器配 painter(id 52001) 画倒车轨迹线。不同分辨率工程结构一致只改 resolution+position。

代码用法（reverseLogic.cc onUI_init 实测顺序）：setErrorCodeCallback(无信号检测 E_CAMERA_STATUS_CODE_
NO_SIGNAL/HAS_SIGNAL，计数≥2 才提示防抖) → setDevPath → setFormatSize → setFrameRate → setRotation
(0/90/180/270) → setMirror(EMirror) → setChannel；防拉伸：按控件宽高比算 setCropPosition(cp)，
旋转 90/270 swap l/t/w/h；页面退出防同开冲突：onUI_hide WAIT(!isPreviewing(),100,30)；onUI_quit 反注册回调。

**同步**：rag_index 重建；版本 0.10.0→0.11.0-open。

---

## v0.10.0-open (2026-09-03) — 自定义控件实现方法入库 + GUI 差距盘点 + FT-024 纠正

**① 新建 knowledge/devflow/custom-widget.md（自定义控件实现方法，沛哥要求先记录方法后续再实现）**
来源：内部私有仓库 guoxs/lib-ext_widgets 拆解（F136/F133，8 个自研控件：AlbumListView/ImageBoxView/
FrameImageView/ImageEditView/RotateImageView/SliceProgressBar/PullWidget + BaseView 基类）。

核心方法（一句话）：
- **控件 = 继承 ZKBase → `create(Json::Value())` 纯代码实例化 → new 到 ftu 容器 Window 上**
  （不进 ftu/IDE，纯 C++ 类；onUI_init new / onUI_quit delete）
- 两条路线：组合式（内部 new ZKButton 当通用矩形拼装，进度条/列表）vs 自绘式（重写 `onDraw(ZKCanvas*)`
  + bitmap_t 内存画布 + Region 脏区）
- 控件不带业务：外观用 Attr 结构 build() 一次配置；数据/事件走函数指针适配器（setDataAdapter/
  setClickListener）；obtain 回调禁耗时
- 手势：onTouchEvent（DOWN/MOVE/UP）+ VelocityTracker 惯性 + 定时器回弹 + event::multi_touch 双指缩放
- 异步：解码/加载丢 MessageQueueThread；图片显示优先子按钮 setBackgroundBmp/Pic
- 附 8 控件能力表（做新控件前先查可抄） + 新控件开发 10 步 checklist

**② 新建 knowledge/devflow/gui-controls-gap.md（现代化 GUI 控件差距盘点，沛哥 19:14 要求）**
现有家底：内置 21 控件 + 自研 8 控件。真缺（按优先级）：
富文本 RichTextView（**最高优先**，缺自动折行/样式混排/嵌图/滚动）/ 通用图表 ChartView / 表格 TableView /
下拉选择 ComboBox / 滚轮 WheelPicker / 轻提示-角标-菊花（Toast/Snackbar/Badge/Spinner）。
可代不算缺：轮播（ImageBoxView）/跑马灯（SlideText）/下拉面板（PullWidget）/双指缩放（自研）/动图/弹窗等。

**③ FT-024 纠正（沛哥 19:27-19:35 确认：textview 实际支持 \n 换行）**
- 背景：v0.8.0 前 FT-024（2026-08-29）认定「textview 不渲染 \n、json 写换行异常」——**误判/误泛化**；
  实际代码 setText 与 json/ftu 布局 text 写 \n 均正常多行渲染
- html2json.py：`<br>` 折叠空格 → **转 '\n'**；handle_data 增加 HTML 文本节点空白折叠（源码换行缩进→单空格，
  避免意外换行）；_clean_text 及两处 raw_text 只折叠空格类、保留 \n（冒烟：`第一行<br>第二行` → text=`第一行\n第二行` ✓）
- check_all.py：**删除第 12 项「text 禁换行」误报检查**（13/14 重编号 12/13）
- HTML_SUBSET.md 第 8 条改写：支持 \n，`<br>` 转 \n，源码缩进仍折叠，换行请显式写 `<br>`
- knowledge/devflow/gui-controls-gap.md 富文本描述同步修正（缺口=折行/样式/嵌图/滚动，非换行）

**同步**：rag_index 重建；版本 0.9.0→0.10.0-open。

---

## v0.9.0-open (2026-09-03) — V85X UVC 摄像头接入入库 + USB 存储双介质文档重构（沛哥指定）

**① 新建 knowledge/v85x/uvc-usb-camera.md（补「V85x USB 摄像头接入」空缺）**
来源：沛哥指定 `LearningProject/mark_cv201` → CV201_PND（+CV201_PND_1024_600 同架构验证）
（V85X/AW_V853 + aw-dvr 3.9.12）。场景：V85X 主机 USB 接入 UVC 摄像头，与内置 ISP 前摄双路并存。

收录（**通用骨架，沛哥指示：模块私有协议层不入库**）：
1. UVC 设备发现：inotify /dev（IN_CREATE/IN_DELETE + video\d* 正则）→ 延时 ~3s 枚举 →
   扫 /dev/video0..12 `VIDIOC_QUERYCAP` 且 `driver=="uvcvideo"` 命中；多节点防重、只认自己记录节点
2. 打开初始化：`VIDIOC_G_FMT` 读默认分辨率 → CameraHelper.Init(w,h) 幂等；
   **MPP 注册关键**：FRONT setIsp(true) + REAR `setUvc(true).setId(DEVICE_ID_AUTO)`（UVC 走后路通道）
3. fd 来源：`mpi::SharedVideoDevice(REAR).getFileDescriptor()`
4. **取流保活**：UvcCameraDetection : mpi::Task<>（SharedVideoDevice + wait()），停久断流（关键坑）
5. 双路预览布局：FRONT 内置 layer0 全屏 + UVC REAR layer4 半屏拉伸，VIEW_TYPE 显隐组合
6. 录像：RecorderParameters.settings[FRONT]+[REAR]（有 UVC 才加 REAR 路），同套 Recorder
7. **拍照走 mpi::Snapshot**：`mpi::Snapshot::instance().takePicture(names, {})` + 200ms 防抖
   （⚠️ 不是 Recorder::takePicture）
8. 状态机通用设计：连接/断开/异常 + 50 帧防抖切换 + 回调集 + 恢复后 resetCameraPreview 重建预览

**② knowledge/v85x/usb-gadget-storage.md 重构为「双介质」主线**（沛哥 2026-09-03 指示整合）
把 v0.8.1（USB 双档）+ v0.8.2（xdv200300 TF 卡）合并成单一主线：
介质（EMMC 分区 mmcblk0p1→/mnt/storage / TF 卡 mmcblk1→/mnt/extsd，探针 mmcblk0boot0）×
USB 档位（ADB / U盘 / NONE）两个正交维度；挂载（Main.cpp）与 UVC 档暴露源（lun.0/file）
同一探针二选一；口径澄清：暴露的是块设备不是 /mnt/extsd 挂载点字符串。

**同步**：references/kb/v85x-uvc-camera.md（速查）+ MEMORY.md 分类表；重建 rag_index；
版本 0.8.2→0.9.0-open。

---

## v0.8.2-open (2026-09-03) — V85X USB 存储双介质差异补入（沛哥验证 xdv200300）

**沛哥提示**：兄弟项目 xdv200300 有新的暴露路径（应为 /mnt/extsd），验证是否存在。

**验证结论**：存在，且机制已完全摸清——xdv200300 新增 **TF 卡存储方案**：
1. config.h 新增 `EMMC_BLOCK_BOOT=/dev/block/mmcblk0boot0`（EMMC 存在性探针）、
   `TFCARD_BLOCK=/dev/block/mmcblk1`、`TFCARD_MOUNT_POINT=/mnt/extsd`
2. Main.cpp 挂载双分支：mmcblk0boot0 存在 → checkAndMount(mmcblk0p1→/mnt/storage)；否则 → checkAndMount(mmcblk1→/mnt/extsd)
3. usb_monitor.cpp STORAGE 档（lun.0/file）同一探针二选一：EMMC 存在暴露 mmcblk0p1，否则暴露 **TF 卡 mmcblk1**；xdv23 固定暴露 mmcblk0p1（无分支）
4. ⚠️ 口径澄清：mass_storage lun.0/file 暴露的是**块设备**（不接受挂载路径），
   `/mnt/extsd` 是 TF 卡在设备内的挂载点而非暴露源；电脑看到的是 TF 卡文件系统内容

**更新**：knowledge/v85x/usb-gadget-storage.md 新增 §1.5 双介质差异表 + references/kb/v85x-usb.md 同步；
重建 rag_index；版本 0.8.1→0.8.2-open。

---

## v0.8.1-open (2026-09-03) — V85X USB Device 模式（ADB/U盘存储）知识入库

**来源**：内网 git.com/AppGroup/xdv 仓库 xdv23（+兄弟项目 xdv200300 同源）实测
（V85XEMMC 平台，AW_V853 芯片红外热像仪，usb_monitor.cpp，ZKSWE Develop Team 2023）。

**背景**：沛哥提示该工程涉及 V85x 平台「MTP」功能；查知识库确认 USB device 存储模式未收录，学习入库。

**技术定界**：客户口径「MTP」在该工程 = USB 连电脑当存储设备（电脑读设备内照片/视频），
实现是 **configfs usb_gadget + mass_storage（U盘/UMS 模式）**，与 **functionfs（ADB 调试）** 双档共用一套 gadget 配置器；
非 MTP 协议栈。

**收录要点**（新建 knowledge/v85x/usb-gadget-storage.md）：
1. 双档差异表：ADB（ffs.adb，VID/PID 0x18D1/0xD002）vs U盘（mass_storage.usb0 暴露 mmcblk0p1，0x1F3A/0x1000）vs NONE
2. V85X/全志 usbc0 OTG 角色切换：/sys/devices/platform/soc/usbc0/{otg_role, usb_device, usb_host, usb_null}，**读节点即切换**（fopen/fread 文件 IO），与 Z21（cat soc0/soc/soc:usbotg/usb_host|usb_device）路径/方式不同
3. configfs gadget 完整配置序列（8 步顺序）：mount configfs → g1 strings（manufacturer/product/serialnumber）→ configs/c.1（bmAttributes 0xc0 / MaxPower 500）→ unlink 旧 symlink → 切角色 → VID/PID + function → symlink 挂 config → ctl.restart adbd → 枚举 /sys/class/udc 写 g1/UDC
4. 应用集成：开机 set_usb_config（Settings.dev ? ADB : STORAGE，开发样机 adb / 量产 U盘）；SystemProperties app.usb.cfg 防重复配置；GPIO_USBIN_DET 插拔检测；相册路径 /mnt/storage/photo|video
5. EMMC FAT32 管理：edge/fat32（base::fat32::{format_fat32fs, mount_vfat, umount, checkAndMount, getBlockSize}），Main.cpp onEasyUIInit checkAndMount(mmcblk0p1 → /mnt/storage)
6. 坑位：换档必须 unlink 两个旧 symlink；configfs 未挂先 mount；整分区暴露与设备端写入抢数据（量产按 dev 开关取舍）；UDC 未绑定电脑不识别；functionfs uid/gid=2000

**同步**：references/kb/v85x-usb.md（速查）+ MEMORY.md 分类表登记；重建 rag_index；版本 0.8.0→0.8.1-open。

---

## v0.8.0-open (2026-09-03) — 移除 fix_tools.py 独立修复工具，修复能力前移到创建功能点（沛哥定规）

**背景**：fix_tools.py（90KB，FT-001~FT-024 共 18 条 detect/fix/verify 规则）是历史遗留的「事后打补丁」工具——
规则根源是各创建环节没做对。本次逐一审计规则 ↔ 源头功能点，已内化的保留，缺失的补进对应创建/校验功能点，
然后移除 fix_tools.py 独立入口（不再有「生成后跑一遍修复」的路径）。

**源头功能点审计结论（24 条规则去向）**：
1. **早已内化，无需处理**：
   - FT-004（json/ftu 时间戳防呆）→ project_tools._ui_timestamp_check + flythings_build_ui_flow ①②
   - FT-008（圆角抗锯齿）→ gen_res.py 内置 _aa_rounded_rect/_aa_mask/_aa_outline（1x 直画 + α 羽化）
   - FT-010/011/014（包版本查 registry + 改依赖先 fun install）→ flythings_add_package 闭环（registry→catalog→online 自动取版本 + 自动 install）+ build_ui_flow 每次 build 前 fun install
   - FT-020（HTML 语义图标/emoji 自动转 PNG）→ html2json icon 分支自动转图 + qrcode__ 控件支持
   - FT-021（渐变/圆角背景转 backgroundPic + 删除底色字段）→ html2json _effect_assets + gen_res.gen_gradient_stops
   - FT-022 生成端（资源按 position 尺寸生成）→ html2json 自动转图传控件 position 尺寸
   - FT-023（端到端自检）→ ui_tools/check_all.py 通用一键全检（9 项，比原 4 阶段更全）
   - FT-024（text 禁换行）→ html2json _clean_text / <br> 折叠为空格
2. **本次补进源头功能点**：
   - **check_all.py 交付全检新增 5 项**（第 10~14 项）：SeekBar 禁用 9-patch（原 FT-002）/ 图片尺寸==控件 position（原 FT-003/022 校验端）/ text 禁换行符（原 FT-024 校验端）/ INIT_UI_TIMERS 不被 FYX_BUILD 保护（原 FT-005）/ TextView/Button 最小尺寸公式（原 FT-009 校验端）
   - **html2json.py 生成端内化**：FT-009 最小尺寸自动扩宽（超容器告警不扩）+ FT-006 多全屏互斥 window 告警（页面级应拆多 Activity）；顺带清理 html2json() 主函数 return 后历史死代码
3. **删除/归档**：fix_tools.py + fix.log 归档至 memory/backup_20260903_fix_tools/（不物理删除）；kb_tools.py 移除 import/入口/注册，工具数 31→30；README 工具表同步

**工具数**：31 → 30（移除 flythings_fix_project）

---

## v0.7.15-open (2026-09-02) — FT-007 废弃：部署统一只用 fun launch（沛哥定规）

**废弃 FT-007 手动部署顺序规则**：
1. 删除 fix_tools.py 中 FT-007 检测/修复/验证（先 adb push images 再 kill zkgui + deploy_order.md 生成），修复规则 19→18 条
2. 部署流程统一只用 **fun launch**（fun launch 内部已正确部署程序+资源+ftu 并启动，无需手动 push + kill zkgui）
3. kb_tools.py docstring / fix_tools.py docstring 同步标注 FT-007 已废弃

---

## v0.7.14-open (2026-09-02) — T113 倒车摄像头格式参数表入库（沛哥要求）

**收录内容**（来源：git 收录工程 `temp_car/public/t113/T113CarSystem_PND/jni/logic/` 实测）：
1. **完整格式参数表**：AHD/TVI 720P/1080P（分辨率+帧率）、CVBS PAL/NTSC、DM5885 逐行/隔行——12 种格式全表
2. **对应代码**：cam_info_t 结构 + _s_cam_info_tab[] 表 + 切换流程（stopPreview→setFormatSize+setFrameRate→setenv ZKCAMERA_DI_ENABLE→startPreview）+ 摄像头初始化 + 设置页保存 + setting 接口

**关键知识点**：
- TVI 标 25/30 实际帧率 24/29（易踩坑）；CVBS/DM5885 隔行才使能 ZKCAMERA_DI_ENABLE 奇偶合并
- 摄像头节点：AHD=/dev/video0、CVBS=/dev/video4；无信号回调连续 2 次才提示

**入库**：新建 `knowledge/t113-car/ahd-camera-format.md`（知识点+完整代码）；wiki 源 t113-car-link.md 倒车段补全格式表；references/kb 同步；重建 rag_index。

---

## v0.7.13-open (2026-09-02) — ImageAnim 动图控件字段规范入库（沛哥定规）

**两点定规**：
1. **动图控件只支持 GIF 和 WebP 两种格式**——playFile 只能指 .gif/.webp，其他格式不显示（硬限制）
2. **动图控件 ≠ 文本帧动画，禁止混用**——动图控件直接播放 gif/webp 文件（json 一个 playFile）；文本帧动画是 textview + setBackgroundPic() 逐帧切 PNG；❌ 禁止在动图控件里用 PNG 帧图/逐帧切换方式实现，也不要为播放 gif 建 textview 切图

**字段校准（实测）**：ImageAnimDemo-New/main.json + UIlayoutDemo/imageanim.json 两 demo 核对——json 字段仅 `caption/id/loopCount/playFile/position` 五项；**修正 layout-audit.md 误写的 frameInterval**（实测 json 无此字段）。

**平台限制**：只支持 Z20/Z21/T113/T113STDCXX/T113EMMC/Z261/V85X；**F133 不支持动图控件**（只能 textview 帧动画）。

**入库**：新建 `knowledge/uicontrols/imageanim-fields.md`（字段表 + html2json 写法 + 代码操作 + 常见坑）；修正 layout-audit.md；重建 rag_index。

---

## v0.7.12-open (2026-09-02) — 流程文档修正（沛哥补充）

**两点修正**：
1. 医疗口腔内窥镜仅为示例，流程适用于**任何产品**（拆解维度按产品类型调整，不套模板）
2. 美化风格**不套固定模板**——按实际产品行业/场景定制：
   医疗/专业→科技蓝/纯净白/深色；消费电子→明亮暖色/圆润卡片；工业/车载→高对比大控件；智能家居→简约浅色等

---

## v0.7.11-open (2026-09-02) — 一句话需求→线框→美化流程入库（沛哥定规）

**流程**：用户一句话产品需求（如「我想设计一个医疗口腔内窥镜」）→
① 功能拆解（功能清单 + 客户确认清单）→ ② 页面层级设计（页面树，page-id）→
③ 单 HTML 多 .screen 线框图（data-page/data-page-name/data-note/data-goto 标注，AI 后续按此分页）→
④ 用户确认（线框 + 确认清单，多轮沟通带标注定位修改）→
⑤ UI 美化 3+ 套风格（医疗蓝/纯净白/深色/暖色）→ ⑥ 风格选择 → ⑦ 美化稿预览确认 →
⑧ html2json 按 data-page 分页 → preview → pack → build_ui_flow 交付。

**沛哥决策**：① 需要确认清单 ② 文字输入（不做语音）③ 单 HTML 多页面 data-page 区分 ④ 3+ 套风格。

**入库**：新建 `knowledge/devflow/prototype-flow.md`（完整流程 + 标注规范 + 风格方案表）；重建 rag_index。

---

## v0.7.10-open (2026-09-01) — 检索边界补充：禁止解析 easyui 库源码（沛哥 22:09）

**补充规则**：AI 分析控件用法时**禁止解析 easyui 库源码/头文件（ZKXXX 类实现）**——
easyui 是预编译闭源库，源码解析拿不到控件 json 字段/回调语义，浪费时间绕路；
直接参考 wiki 实现（knowledge/uicontrols/ 或 wiki/flythings/），文档没有标注「未收录」问沛哥。

**入库**：retrieval-boundary.md「禁止的行为」新增一条；MEMORY.md 铁律 1 同步；重建 rag_index。

---

## v0.7.9-open (2026-09-01) — SlideWindow 布局定规修正（沛哥 21:59 纠正）

**纠正 v0.7.8 的错误表述**：「绝对布局需按实际微调」是错的——
- json 的 position（left/top/width/height）**直接来自 HTML 原型的 data-x/y/w/h**，本来就是绝对布局，坐标明确
- **HTML 效果确认后 → json 坐标即准确 → 不需要（也不该）再微调**
- 若交付后还要调位置 = **前期 HTML 效果没确认好**——正确流程：HTML 布局 → json2html/generate_ui_preview 出预览稿确认 → 确认 OK 才 fui pack / 写逻辑 / 交付
- padding/iconTextPadding 同理：HTML 阶段（data-pad-b/data-icon-pad-b）调好，确认后即定稿

**文档**：slidewindow-fields.md 铁律 5 已重写；重建 rag_index。

---

## v0.7.8-open (2026-09-01) — SlideWindow 图标布局补充（沛哥 21:52 定规）

**两条补充定规**
1. **同一 slidewindow 所有图标尺寸必须一致**：生成图标时统一尺寸（如全部 60×60），
   不一致会导致位置错乱。html2json 已加 items 图片尺寸一致性检查——不一致 → warning 提示统一后重转
2. **默认 padding 值没问题，但 FlyThings 绝对布局需按实际微调**：默认 paddingBottom=8 /
   iconTextPadding bottom=5 只是起点，绝对布局（left/top 像素定位）下必须根据实际显示效果
   微调 padding / iconTextPadding / iconSize 使图标落在期望位置，改后重新 fui pack 看设备效果

**验证**：尺寸一致回填 60×60 正常；尺寸不一致（60+80）warning 正确。文档 slidewindow-fields.md 同步补充。

---

## v0.7.7-open (2026-09-01) — SlideWindow 图标布局铁律入库（沛哥定规）

**定规**：SlideWindow 图标布局三要素——
① `iconSize` 必须按**实际图片尺寸**（非控件平分格子大小；默认 128 会导致图标位置不对/拉伸）
② `padding` = 图标相对平分格子边界的留白 ③ `iconTextPadding` = 图标配套文字的 padding

**入库 + 修复**
- 新建 `knowledge/uicontrols/slidewindow-fields.md`（字段表 + 布局铁律 + html2json 写法 + 常见坑）
- html2json：未显式指定 data-icon-w/h 时自动读 items 首张图标图实际尺寸回填 iconSize（读不到 warning 提示）
- 验证：显式指定保留；自动回填 60x60 成功；缺图 warning 正常
- 重建 rag_index

---

## v0.7.6-open (2026-09-01) — validate_project 去噪（沛哥确认）

**清理 3 处冗余**
1. 删 `src/activity 目录缺失` warning：新建模板项目未编译时 activity 不存在是正常状态，属误报
2. 删 `cacert_ok`「HTTPS 证书已就位（仅提示）」warning：正常配置报 warning 是噪音（缺证书已报 error 足够）
3. 删 `defined_cbs` 死代码（赋值后从未被读取）

**验证**：模块导入 OK；空白项目/不存在目录冒烟通过；其余检查项不变。

---

## v0.7.5-open (2026-09-01) — 移除 flythings_read_ftu（沛哥确认）

**背景**：新版 fui.exe 仅支持 pack（json→ftu）不支持 unpack，read_ftu 在无同目录 json 时必失败，
实际只是 read_json 的包装。沛哥确认删除，只保留 read_json。

**改动**
- 删除 `flythings_read_ftu` 工具（kb_tools 定义+注册 / project_tools 实现）
- `flythings_read_json` 增强：传入 .ftu 时友好提示——提供同目录 json / 重新设计界面 / IDE 打开 ftu 另存 json
- 工具数 32 → 31；README 同步

---

## v0.7.4-open (2026-09-01) — 控件用法检索边界定规（沛哥）

**定规**：AI 检索 FlyThings 控件用法/字段/API 时**只允许两个来源**：
① MCP 内置知识库（flythings_search / knowledge/uicontrols/ 文档）② 官方文档站 developer.flythings.cn。
禁止从其他渠道检索（通用 web 搜索、Qt/Android/Flutter/emWin/AWTK/LVGL 等其他 GUI 框架、非官方博客/论坛）——
防止混入其他框架控件用法导致知识错乱；查不到的标注「未收录」不猜不套用。

**入库**：新建 `knowledge/uicontrols/retrieval-boundary.md`；重建 rag_index。

---

## v0.7.3-open (2026-09-01) — EditText JSON 字段规范入库

**背景（沛哥要求）**：MCP 查询不到 EditText 字段规范——规范散在本地 references 与 layout-audit 里，knowledge 无专门文档。

**入库**
- 新建 `knowledge/uicontrols/edittext-fields.md`：完整 JSON 字段表（text/hintText/hintTextColor/textType/isPassword/
  passwordChar/fontSize/colorTab/bgColorTab/beepEnable/bold/italic/roll*）、onEditTextChanged 回调、
  html2json HTML 写法（data-hint/data-num/data-password/data-password-char）、常见坑（isPassword 必须配 passwordChar 等）
- 修正 layout-audit.md id 段笔误：edittext 60000 → **51000**（60000 是 diagram 的；html2json/check_all/controls.md 均 51000）
- 重建 rag_index

---

## v0.7.2-open (2026-09-01) — 圆角抗锯齿方案重做（弃超采样，改 1x 直画+α 羽化）

**问题（沛哥反馈）**：v0.7.1 的超采样（SS2 + LANCZOS 缩回）带来**倒角宽度变宽**问题。
实测量化：LANCZOS 缩回存在像素网格取整偏移（多数 r 差 1px，r=19/20 接近钳制上限时动态校准也救不回）——
缩放本身必然引入几何偏移，radius 越大越接近 min(w,h)/2 越明显。

**方案重做**：弃 SS 超采样，改 **1x 直画 + α 高斯羽化（sigma=0.5）**
- 几何轮廓（α>=128）与 1x 直画**逐像素一致** → 倒角宽度 100% 不变
- 弧线处 α 平滑过渡（3-4px）→ 抗锯齿保留；直线段保持硬边（直线不需要 AA）
- 实验验证：r=2..20 × 4 组尺寸（32x16~100x50）几何全部一致；to_9patch 四边 marker 不受影响；五函数出图正常

---

## v0.7.1-open (2026-09-01) — 圆角抗锯齿修复（FT-008 落地 gen_res.py）

**问题**：FT-008（SS=2 + LANCZOS 超采样）规则此前只用于修复客户项目脚本（_gen_scripts 扫描注入），
MCP 自己的 gen_res.py 所有圆角绘制仍是 1x 二值 α 锯齿。

**修复**
- 新增超采样辅助：`_aa_rounded_rect` / `_aa_mask` / `_aa_outline`（SS=2 倍画布绘制 → LANCZOS 缩回）
- `rounded_rect` / `rounded_card` / `gen_gradient` / `gen_gradient_stops` / `gen_shadow_card` 全部改走超采样
- 验证：五类资源边缘 α 均出现中间过渡值（13~25 个），不再二值 0/255；to_9patch 四边 marker（FT-009）不受影响

---

## v0.7.0-open (2026-09-01) — FT-009 .9.png 生成规则入库 + 修复

**新规则入库（沛哥定）**
- `knowledge/uicontrols/nine-patch-rule.md`：stretchable 圆角图片（.9.png）生成五条必守规则：
  ① marker 线纯黑不透明 `(0,0,0,255)` ② top/left 只画中间拉伸段（排除 radius 倒角区）
  ③ right/bottom 黑线宽度与拉伸区同宽 ④ 线宽 1px 紧贴边缘 ⑤ marker 最后绘制不被后续 alpha 覆盖。
- 附 Pillow 标准实现 + 验证方法 + 常见坑（含 SeekBar 禁用 9-patch 提醒，联动 FT-002）。

**代码修复**
- `ui_tools/gen_res.py` `to_9patch`：原实现只画 top/left（缺 right/bottom 内容区标记）→ 按规则补全四边 marker，
  验证通过：四边起点/终点纯黑 (0,0,0,255)、倒角区无黑线、right/bottom 与 top/left 拉伸段同宽。

**发布**
- 版本 0.6.9 → 0.7.0-open；MCP_FEATURES 新增条目；重建 rag_index。

---

## v0.6.9-open (2026-09-01) — 全面梳理清洗

**🔴 修复致命 bug**
- `project_tools.py` 缺失 3 个工具函数：`flythings_create_project` / `flythings_build_ui_flow` / `flythings_edit_ftu`
  （含依赖 `_find_control` / `_apply_edits` / `flythings_edit_json`），但 `kb_tools.py` 一直引用它们
  → 这三个 MCP 工具调用即崩（AttributeError）。已从 `tools/flythings-mcp-stdio/project_tools.py` 移植补齐，
  按 open 版口径适配（布局以 json 为源；fun launch 不支持 -s）。
- 冒烟验证：create_project 真实建 F133/800x480 项目成功（Manifest 平台 / 工程名替换 / ftu 生成全对）。

**🟡 去重**
- 删除 `ui_preview.py`：与 `ui_tools/json2html.py` 同函数集合、62.8% 相似（旧版残留）。
  `flythings_generate_ui_preview` 统一走 json2html，并补回 controls 计数等兼容字段。

**📝 精简说明**
- `MCP_FEATURES`：42 条 5649 字符 → 10 条精华（历史压缩，完整记录移入本文件）。
- README：版本 0.4.1/25 工具（过时）→ 0.6.9-open/32 工具；工具列表补全
  （edit_ftu / fix_project / i18n_* / gen_ui_test / generate_ui_assets / create_bin_project）；移除已删文件引用。
- configure.py 版本提示 0.2.4/22 → 0.6.9/32。

**🧹 清理**
- 6 套 HelloWord 模板的 `Release/` 编译产物（共 0.7MB，create_project 本就跳过）。
- `__pycache__` × 2。

**✅ 验证**
- 11 个模块全部导入 OK；32 个工具注册一致；无残留 ui_preview 引用。
- knowledge/ 未变 → rag_index.json 无需重建；未 push Gitee（待沛哥确认）。

---

## v0.6.8-open (2026-09-01)
- UI 控件 Layout 全量检查（basedemo 21 控件逐项核对）：html2json 修复 6 处缺口
  （circlebar 文字/滑块/touchRange、cameraview cvbs/mirror、videoview rotation、
  listview 滚动属性、slidewindow 背景图/iconMaxSize、文字控件 bold/italic/roll 滚动）。
- 检查报告 `knowledge/uicontrols/layout-audit.md` 入库（对照表 + 修复清单 + 控件 id 段）。

## v0.6.7-open (2026-09-01)
- ScrollWindow 布局设计入库（scrollwindow-layout.md）：可视区 + 内嵌大 window 内容、
  dragMaxDis/orientation/edgeEffect；与 PageWindow 区别；html2json div.scroll 支持。
- Pointer 坐标三件套（rotationPoint / fixedPoint / pointerSize）+ 图片字段坑（pointerPic 非 picTab）。
- 图片资源路径铁律修复（致命问题）：自动转图/生成图片统一输出 `resources/images/`，
  json 引用 `images/xxx.png` 相对 resources（与设备加载一致）；html2json 自动识别 ui/ 目录；
  gen_ui_assets 返回相对引用路径；顺修 color list 未转 tuple bug。
- rebuild 双根索引去重 + path 计算修复（knowledge 文档带前缀、跳过本地 wiki 同名文档）。

## v0.6.6-open (2026-08-31)
- 电子价签 ESL 方案入库（esl/tag-esl.md）：Z20/T113EMMC 一套代码双平台
  （Manifest enableOnPlatforms + accessKey 私有包 + #ifdef 三件套）；HTML 渲染体系
  （RenderService/Cron 轮播/StorageRegistry/webview 上屏）；自研 BlueZ GATT Server；
  OTA 整包升级要点。涉密内容按保密要求脱敏。

## v0.6.5-open (2026-09-01)
- 移除 check_all 文本换行误报检查：textview text 支持 `\n` 多行（配合 rowSpace），`\n` 不再报错。

## v0.6.4-open (2026-09-01)
- html2json 文本清洗：剥离 emoji/特殊符号全范围，纯 emoji 图标自动转 PNG，混合文本保留文字；
  check_all 特殊字符检查同步升级。

## v0.6.3-open (2026-08-31)
- 模拟器功能开放版不支持（fun sim 禁止 + QEMU 不对外）：交付/验证一律真机 fun build + fun launch。

## v0.6.2-open (2026-08-31)
- fun sim 模拟器功能禁止使用（未开放暂不支持），模拟器验证走本地 QEMU sim/ 方案。

## v0.6.1-open (2026-08-31)
- 修复 .cc 误用规范：手写 .cc 不会被编译（Makefile 只编 %.cpp %.c，.cc 是 IDE 按页面生成的 logic 专属）；
  新增业务代码一律 .cpp/.h；validate_project 新增 manual_cc_file 检查。

## v0.6.0-open (2026-08-31)
- bin_tools 精简：删除 C 源码只留预编译 ELF + 调用方法 README；补编 v85x 平台 ui_test
  （现 5 平台：z21/z20/t113/f133/v85x）。
- flythings_gen_ui_test 架构升级：通用触摸工具预编译各平台 ELF 存 `bin_tools/{platform}/ui_test`，
  测试项目只生成数据脚本不再现场编译（traverse 脚本 + monkey 直接命令），tools 不膨胀。

## v0.5.9-open (2026-08-31)
- iconPosition 铁律入库：控件尺寸与图片尺寸不匹配必须显式设 iconPosition，否则图片按 position 拉伸变形。

## v0.5.8-open (2026-08-31)
- 新增 flythings_gen_ui_test：解析 UI json 坐标生成自动化测试项目
  （traverse 遍历控件验收含资源缺失检查 / monkey 压测 / custom 自定义；ask 先问用户三种验收方式）。

## v0.5.7-open (2026-08-31)
- 自动化测试闭环修正：logd 分析优先，raw fb 抓屏非必要不用（图片解析难）。

## v0.5.6-open (2026-08-31)
- 全自动化测试闭环补充：input 注入 + logcat 分析 + cat /dev/fb0 framebuffer 抓屏解析 UI。

## v0.5.5-open (2026-08-31)
- 新增 flythings_create_bin_project：fun create --type bin 创建可执行程序并编译 ELF。

## v0.5.4-open (2026-08-31)
- 触摸注入实现方法重写：核心是 event.c /dev/input 协议序列，可编 bin 或嵌代码模块跨平台复用。

## v0.5.3-open (2026-08-31)
- adb 触摸注入/录制自动化测试工具入库（test/adb-input-autotest.md，关键词触发不影响常规检索）。

## v0.5.2-open (2026-08-31)
- 游戏机/Knob 补充确认：芯片 SSD201/202 + T113 均支持、ROM 客户自备授权、旋钮节点可自动扫描。

## v0.5.1-open (2026-08-31)
- 游戏机方案 + Knob 旋钮入库（game/game-knob.md，关键词触发不影响常规检索）。

## v0.5.0-open (2026-08-31)
- Z20 智能家居面板语音方案入库（voice/z20-aiui-voice.md，关键词触发不影响常规检索）。

## v0.4.9-open (2026-08-31)
- T113 车载互联补充商务/授权 FAQ（OTP 双模式烧录 / 有线互联占 USB adb / 硬件解码通用 / 蓝牙选型 / lylink 商务流程）。

## v0.4.8-open (2026-08-31)
- T113 车载互联平台入库（t113-car/t113-car-link.md，关键词触发不影响常规检索）。

## v0.4.7-open (2026-08-31)
- Z20 SIP 对讲方案入库（voip/z20-sip-voip.md，关键词触发不影响常规检索）。

## v0.4.6-open (2026-08-29)
- 涂鸦厨电专项入库（tuya/z20-cooking.md，关键词触发不影响常规检索）。

## v0.4.5-open (2026-08-29)
- V85x 摄像头/DVR MPP 用法入库（ZKCameraView + mpi:: 录像/回放/四路拼接/分辨率）。

## v0.4.4-open (2026-08-29)
- 控件能力全面校准汇总：TextView / CheckBox / Button / CircleBar / Diagram / DigitalClock /
  EditText / ImageAnim / ListView / Window / SlideWindow / ScrollWindow / PageWindow / 系统栏 全能力落地。
- 新增控件支持：PageWindow（31001+）、ScrollWindow（32001+）、SlideWindow（30001+）、
  CircleBar（130001+）、Diagram（60001+）、DigitalClock（93001+）、EditText 密码掩码、ImageAnim 动图。
- 系统栏 topmost 悬浮、Window 模态/自动隐藏、window 嵌套修复、ListView 行距/subItem 背景图。
- GPIO 外设控制入规范（GpioHelper input/output/边沿监听 + 平台引脚名）。
- 代码层架构原则入规范：logic/*.cc 只做 UI 与业务关联，复杂功能拆独立 C++ 类（core/modules 等）。

## v0.4.3-open (2026-08-29)
- i18n 工具升级：add_language 添加新语言（三段式文件名）+ 项目语境专业翻译提示。

## v0.4.2-open (2026-08-29)
- 新增多国语言 i18n 工具：scan 诊断 / export 导出 / import 写回 / refactor 布局文本转 @key。

## 早期 (v0.1 ~ v0.4.1)
- 控件能力补全：slidetext / cameraview / painter / pointer / qrcode / videoview 六控件 +
  radiobutton 两态图 / seekbar 按下态 / edittext 掩码字符 / digitalclock 数字颜色 等字段。
- TextView 能力校准：文本不支持多行（\n 折叠为空格）+ FT-024 换行检测。
- CheckBox 校准：padding 三件套（iconPosition/textPosition/data-pad）+ 两态图 picTab{pic0,pic2}。
- Button 校准：图片按钮自动去底色 + 五态图 data-pic0~4 + 背景图按钮 data-bgpic。
- 入口工具加强 Activity 目录强提醒：src/activity 由 IDE 自动生成，禁止创建/修改。
- `0f34dfb` FlyThings MCP Open 完全开源版初始发布（本地部署，零远程依赖）。
