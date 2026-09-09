# CHANGELOG — FlyThings MCP Open

> 版本迭代记录（按版本从新到旧）。当前版本：**v0.27.11-open**（2026-09-09）。
> 每次迭代在本文件顶部新增一节；MCP_FEATURES（kb_tools.py）只保留精华摘要，完整历史以本文件为准。

---

## v0.27.11-open (2026-09-09) — V85X 显示分层调试入库（错屏/无图像/回放方向三连坑闭环 + releaseLayer 代码）
**背景**：V85X 竖屏（600×1600）+ 横 UI（1600×600）+ UVC 摄像头工程实测（预览/录像/回放链路）：①竖屏错屏→rotateScreen 270 ②预览无图像→UI 层不透明盖住视频层、videoView 藏坑 ③回放画面没旋转→rotation 枚举写错。三坑全部实锤修复，沉淀为可复用排查套路 + 工具代码。
**结论（入库）**：
- **错屏 → 屏幕旋转**：`package.properties` 写 `EasyUI.cfg={"rotateScreen": 270}`（触摸不转=不写 rotateTouch）；⚠️ 改后 `fun build` 报 `ninja: no work to do`——**必须 `fun clean` 全量重编**；EasyUI.cfg 由 fun launch 本地合并生成（.fun/<平台>/launch/EasyUI.cfg），设备端 /tmp/EasyUI.cfg 可验证 rotateScreen:270/rotateTouch:0
- **无图像根因 = UI 层（z=16 最顶）不透明背景盖住 disp 视频层（z=1）**：摄像头出流正常（rear camera fps 30）+ 视频层 enable 有 addr，但屏幕没画面；UI 必须放 **`visible:true` 的 videoView 透明窗口**（position=画面区域，摄像头自维护出图时零关联代码）——**visible:false 是最常见坑**，控件隐藏时 UI 层不透出、视频层白跑
- **ZKVideoView rotation 是枚举不是角度**：`0/1/2/3 = 0°/90°/180°/270°`（顺时针，头文件注释权威），json 写 `"rotation": 270` 是无效值被忽略毫无效果，竖屏回放写 `"rotation": 3`
- **releaseLayer 工具代码入库**：启动早期关闭除 UI 层(ch2/layer0)外所有 enabled disp 层，防残留图层错屏/叠加；include 坑：直接 `#include <video/sunxi_display2.h>` 缺 s32/u32 定义编译报错，必须用 aw-mpp `<vo/hwdisplay.h>`（先 typedef 再包含，DISP_LAYER_GET_CONFIG=0x48 在内）
- 设备侧调试技巧：无 screencap 用 busybox dd 抓 /dev/fb0 分析像素 alpha 判 UI 层透明性；无 input 命令用交叉工具链 -static 编 tap 小工具（查 /proc/bus/input/devices 定节点，gt9xx 可能是 event0 非 event1）
**改动**：
- 新增 knowledge/v85x/display-layer-debug.md（排查四板斧 + 分层结构 + releaseLayer 完整代码 + videoView 透出/旋转/调试技巧）；wiki/flythings/v85x/ 同步
- 版本 0.27.10 → 0.27.11-open

---

## v0.27.10-open (2026-09-08) — JPEG UVC 实测证据入库（绿屏=0字节文件实锤 / frame_rate 15~60 / 六步验证法）
**背景**：v0.27.9 发布后搭建独立测试工程 `projects/UvcJpegTest_V85X`，在 CV201PND 板（V85X、1600×600、单路 USB UVC MJPEG 1280×720）真机实测 JPEG UVC 预览/拍照/录像/回放全链路，六步全通；同时对比发现设备上旧 AI 工具程序的失败现场，绿屏/黑屏根因实锤。
**实测结论（入库）**：
- **绿屏直接原因 = 录像文件 0 字节**（旧程序日志：`get video frame timeout` / `rear camera fps 0.2` → `VideoRecorder: VENC no stream` → 录出 0 字节 mp4 → 播放器解不出画面=绿屏）；排查录像问题先 `ls -la` 看文件大小，0 字节 = 取流/保活断，不是编码参数问题
- **黑屏 = 取流/保活链路断**（REAR FPS≈0）；边录边看正常时 rear camera fps≈29、venc fps≈25
- **`RecordingSettings.frame_rate` 必须在 15~60**（设 0 抛 `frame rate must be betwen 15 ~ 60`），UVC 25/30fps 就写 25/30
- **录像成功日志判据**：`rear camera fps 29.3` / `rear venc fps 25.0` / `MPP_EVENT_RECORD_DONE`+`done <路径>` / 文件大小正常（12s 720p≈29MB）/ 回放 `media play ok`（demux/vdec/vo/clock 全 success）
**改动**：
- knowledge/v85x/jpeg-decode-record.md：坑新增 7~10——frame_rate 15~60、0 字节文件排查、录像成功日志判读（正常链路特征）、拍照验证闭环（photo/Rear/*.jpg）
- knowledge/v85x/uvc-usb-camera.md：新增 **§8 全链路验证流程**（六步验证法表：①探测②预览③拍照④录像⑤停止⑥回放，每步成功日志判据）+ 绿屏排查第一看文件大小 + frame_rate 口径
- 版本 0.27.9 → 0.27.10-open

---

## v0.27.9-open (2026-09-08) — UVC 知识分层：新增跨平台通用层（V85X 绑定实现分离）
**沛哥定规**：V85X 平台 UVC/USB 摄像头统一按 v0.27.8 通用形态走；**通用 UVC 层沉淀为跨平台知识**，可适配 T113 / F133 / Z20 / Z21（平台无关逻辑直接复用，绑定层按各平台媒体栈实现）。
**改动**：
- **新增 knowledge/hardware/uvc-camera-generic.md（跨平台通用 UVC 层）**：检索导引=未指定平台的 UVC/USB 摄像头问题；
  内容=前置条件（USB Host + uvcvideo 驱动）/ inotify 发现（uvcvideo 匹配）/ V4L2 打开与格式协商（ENUM_FMT+S_FMT，JPEG 必做）/
  持续取流保活铁律 / 热插拔状态机 / JPEG(MJPEG) UVC 落地必查清单（绿屏黑屏防坑：格式协商/尺寸对齐/互斥顺序/保活/格式口径）/
  **平台绑定对照表**（V85X=已收录 aw-dvr/mpi:: 绑定篇；T113/F133/Z20/Z21=通用层可用、绑定层未实测不编造，待补录）
- knowledge/v85x/uvc-usb-camera.md：标题改「（V85X 平台绑定实现）」+ 头部加检索导引（未指定平台→先读硬件通用篇）与分层说明，
  明确本文=V85X aw-dvr/mpi:: 绑定层，平台无关逻辑在 hardware/uvc-camera-generic.md
- knowledge/v85x/jpeg-decode-record.md：头部加硬件通用篇引用（JPEG/MJPEG 平台无关接入）
- 版本 0.27.8 → 0.27.9-open

---

## v0.27.8-open (2026-09-08) — UVC 摄像头知识去工程化（纯通用形态）+ 通用 JPEG(MJPEG) UVC 落地必查清单
**沛哥反馈**：MCP 能力被外部 AI 工具落地开发 JPEG UVC 摄像头时出现「录制文件播放绿屏」「录制中摄像头图像黑掉」两类异常。
**定规（沛哥 2026-09-08）**：知识库更新后**不体现内部工程（CV201 类项目名/路径），只保留通用 UVC 摄像头知识**，供任意产品/外部工具直接复用。
**改动**：
- knowledge/v85x/uvc-usb-camera.md：头部来源去工程化（改为「V85X 平台通用实测」）；坑 #5 改为「通用 JPEG UVC 必须显式协商格式（不能只 G_FMT 读宽高）」；
  **新增 §7 通用 JPEG(MJPEG) UVC 摄像头落地必查清单**（绿屏/黑屏防坑）：
  ① §7.1 格式协商——aw-dvr UVC 默认 capture_pixel_format=V4L2_PIX_FMT_MJPEG、内部 JPEG→NV21 解码 SDK 处理；
     接入必须 ENUM_FMT 确认 MJPEG + S_FMT 锁定（摄像头默认可能 YUYV，不协商=绿屏），用 S_FMT 实际返回宽高 Init；
  ② §7.2 录像分辨率对齐——RecordingSettings.size（REAR）必须=UVC 实际分辨率，不能照抄内置摄像头 1080P/720P 档（尺寸错配=绿屏）；
  ③ §7.3 录像与预览互斥顺序——**开始录像不要停预览/保活**（边录边看常态）；切流/拔插/进回放前才 Recorder::stop+RearCamera::stop（顺序反=黑屏）；
  ④ §7.4 UVC 保活——SharedVideoDevice(REAR) 持续读流任务录像期间也不能停（停了=黑屏）；
  ⑤ §7.5 格式口径——录像仅 mp4/ts（H.264），JPEG 仅用于照片（Snapshot→JpegViewer）；回放视频 ZKVideoView/照片 JpegViewer
- knowledge/v85x/jpeg-decode-record.md：来源/标题/工程实测/代码位全部去 CV201 工程引用（DvrLogic/DvrPlayLogic/camera_helper/src 路径 →
  职责描述），仅保留 API 用法与坑（JpegViewer 照片显示 / jpegdecode.h 取像素 / Recorder 录制 mp4-ts / Snapshot 拍照 / 回放分流）
- 版本 0.27.7 → 0.27.8-open

---

## v0.27.7-open (2026-09-08) — PNG 生成管线规范显式化（方案 A：只补铁律条目，不加新 tool）
**沛哥反馈**：新 AI 客户端拿到 MCP 按规范转出的 png 默认仍有锯齿，问是规范没显式说明处理方式还是缺 tool。
**根因分析**：抗锯齿全部做在 gen_res.py 内部（圆角 α 羽化 sigma=0.5、图标/线条 4~8x 超采样 + LANCZOS、round cap），
html2json 自动转图与 generate_ui_assets 走该管线无锯齿；但规范文档（HTML_SUBSET 切图铁律、工具描述）此前只显式写了
尺寸 1:1、圆角四角 alpha=0、路径规范，**没有一句话说明「PNG 必须按什么管线生成、禁止什么做法」**——
AI 客户端只要不乖乖走工具链（自写 1x 直画、用自身 image 能力直出小图），锯齿就进来了，规范拦不住。
**定规（沛哥 2026-09-08）**：采用方案 A——只补规范铁律条目显式化，暂不做后处理 tool。
**改动**：
- HTML_SUBSET.md「切图 / 图片资源铁律」新增 #8 PNG 生成管线铁律（AI 需要图片只能走三条路：CSS 效果→html2json
  自动转图 / 图标→generate_ui_assets / 自绘→gen_res 公开函数，全内置抗锯齿；禁止 AI 自绘 1x 直画圆角/斜线/圆弧、
  禁止自身 image 能力直出小图交付）+ #9 PNG 防锯齿五要素（①尺寸==控件 position ②≥4x 超采样+LANCZOS 或 α 羽化
  sigma≈0.5，禁 1x 直画 ③端点 round cap ④圆角四角 alpha=0、阴影溢出重裁 ⑤生成后跑 check_all #11+四角 alpha）；
  同步到 workspace tools/ui_tools/HTML_SUBSET.md
- kb_tools.py flythings_generate_ui_assets 工具描述新增 ⑦ PNG 生成管线铁律（AI 直读入口同步）；
  flythings_html_to_json 描述 CSS 转图段加「禁止 AI 自绘 1x 直画/外部生图直出小图」警告
- 版本 0.27.6 → 0.27.7-open

---

## v0.27.6-open (2026-09-08) — 全控件深度阅读（35 官方 Demo 源码精读 → 代码 API 知识）
**沛哥要求**：深度阅读基础 Demo，形成对 FlyThings OS 所有控件的深度理解。
**执行**：basedemo-new_z20_1024_600 35 工程（~7200 行 logic）5 路并行逐源码精读，原始笔记 130KB 归档 workspace/references/demo-read-2026-09-08/group{A,B,C,D,E}.md（证据均引源码原文）。
**新增知识 2 篇**：
- devflow/activity-code-skeleton.md：生成器代码骨架——activity 壳（static mXXXPtr + #include logic.cc）/回调分发表语义 （**true=拦截 false=走默认，logic 模板注释写反**）/生命周期钩子/定时器（静态表 + registerUserTimer 动态起停改）/
  串口协议模板（UartContext 读线程 16KB 拼接缓冲+帧头对齐粘包处理+registerProtocolDataUpdateListener 订阅；双串口=双实例+uart_from）/
  SysApp 三槽位（REGISTER_SYSAPP STATUSBAR/SCREENSAVER/IME BaseApp 范式）/多语言 .tr+@key+setTextTr+updateLocalesCode/平台编译宏/常用能力速查
- uicontrols/widget-code-api.md：21 控件代码 API 速查（回调签名/触发时机/实测坑）——
  seekbar 自定义 ISeekBarChangeListener 三回调拿拖拽起止（Activity 分发只有 onProgressChanged）、ZKVideoView(VIDEO_ 前缀) vs ZKMediaPlayer 两套消息枚举、videoview 轮播 _video_list.txt+off-by-one、camera 拍照四回调+jpg+sync、
  pointer/clock 角度坐标系与浮点 ==360 回绕坑、diagram setData 全量/addData 局部双刷新、painter 绘图 API 全集（无触摸手绘/需 onUI_show 重绘）、
  listview 删除漏 refreshListView 官方坑、IME 集成范本（onInitIME/doneIMETextUpdate/候选 slidetext）、wifi/lte/softap/ethernet Manager+Listener、
  imageanim/qrcode/radiogroup/checkbox/pagewindow/slidewindow 等

---

## v0.27.5-open (2026-09-08) — Button 长按/循环重复机制收录（长按时间/重复时间 UI 可配）
**沛哥确认学习**：按键长按模式的时间、循环重复时间通过 UI（IDE 属性表）可配置。
**机制（官方 wiki button.md + 真源实证）**：
- IDE 属性表两属性（单位 ms）：「长按事件触发时间」→ json `longClickTimeOut`；「长按事件循环触发间隔时间」→ json `longClickIntervalTime`
- 默认两键 -1（不启用长按）；>0 启用；interval >0 = 长按不松手时循环重复触发 onLongClick，-1 = 仅触发一次
- 代码：ZKBase::ILongClickListener::onLongClick(ZKBase*) + setLongClickListener（onUI_init 注册 / onUI_quit 注销，匿名 namespace 防冲突）；点击是 IClickListener::onClick
- 实测：ButtonDemo-New LongButton 1000/1000（1s 触发 + 1s 循环连发，官方示例同款）；ImeDemo-New 删除键 600/-1（600ms 快启单次）
- 适用：button / listview item.subItem / item（ZKBase 体系，subItem/listitem 模板已含两键）
**改动**：新增 knowledge/uicontrols/button-fields.md（button JSON 字段频率表 + 长按三件套 + 典型场景 + 图片按钮铁律）

---

## v0.27.4-open (2026-09-08) — 控件层级检讨（容器→子内容矩阵，双源实证）
**沛哥问「控件层级问题有检讨吗」**：此前只有零散结论（Z序=书写顺序/window 嵌套/pagewindow 叠放/listview 结构），缺系统矩阵与合法性校验。
**矩阵实证**：扫描 86 json（SampleUI-New/ui/1024x600 42 + basedemo-new_z20_1024_600 35 demo/44 ftu 反解）容器→直接子内容分布，零越界：
- 根层：全部 21 类控件均允许
- window = 万能容器（textview 147/button 128/edittext 16/listview 8/seekbar 7/window 5 深嵌套/qrcode/digitalclock/slidetext/slidewindow）
- pagewindow/scrollwindow = 只装 window（页面叠放/滚动内容，basedemo 实证）
- listview/radiogroup/slidewindow/diagram = 只走结构键（item/radiobuttons/items/infos），禁止平铺 __N 控件键
- 叶子 14 类控件不得含子控件；数组子结构归属固定（subItem→listview.item 等）
**改动**：
- 新增 knowledge/uicontrols/json-layer-rules.md（层级矩阵 + 6 条规则要点，检索词含 层级/嵌套/容器/父子/结构键）
- ui_tools/check_all.py：#2「嵌套深度」升级为「层级合法性」（_layer_problems）：缺 window 子页/装非 window、结构容器平铺控件键、
  叶子控件生子、数组子结构错位 4 类非法全部拦截；86 真实 json 全过 0 误报
- 回归：合法用例 PASS + 4 类非法用例 FAIL 正确

---

## v0.27.3-open (2026-09-08) — json 字段全集显式化 v2.1（SampleUI-New 双源基准，每控件必写字段）
**沛哥定规**：json 布局字段做缺省省略 → 引擎版本默认漂移 → 版本不匹配异常；必须全集显式（-1/0/false/字号均写）。
**基准**：projects/SampleUI-New/ui/1024x600（42 json、新 IDE 全量序列化）每类型 100% 交集 = 必选；basedemo-new_z20_1024_600（35 demo/44 json ftu 反解）交叉复验 + 补齐 SampleUI 缺的类型（pagewindow/scrollwindow/checkbox/radiogroup/imageanim/slidetext）。
**口径 5 条（沛哥）**：①beepEnable 不强制（废除恒带 true）②交互控件 touchable 显式 true、容器/纯显示 false ③qrcode 恒写 padding:10 ④videoview 按 SampleUI（无 beepEnable/loopPlayback false/touchable true）⑤-1=0xFFFFFFFF 有意义非噪音。
**改动**：
- 新增 knowledge/uicontrols/json-field-mandatory.md：21 类控件必写键全集表 + 子结构模板（listview.item 17 键含 position / subItem / diagram.infos 10 键含 visible / slidewindow.items / radiobuttons）+ 双源复验结论
- ⚠️ listview.item.position 必写（沛哥）：行高公式 itemH=int(lv高/rows)-rowSpacing、itemW=lv宽（basedemo 验证：164/4-5=36、437/3-5≈140、424/5-0=84；SampleUI 216x275 rows5→55）
- ui_tools/html2json.py：全部控件按全集输出——去恒带 beepEnable；button touchable true+picTab{}+text""；textview/edittext fontSize 16；window 8 键（backgroundColor/hideTimeOut -1 等）；listview 17 键 + item.position 自动算；subItem 17 键；checkbox/radiogroup/radiobutton 按 basedemo 补齐；diagram.infos 补 visible:true；qrcode padding 10+touchable true；videoview 按 SampleUI；digitalclock/cameraview/painter/pointer 补齐
- ui_tools/check_all.py：#14 模板 v2.1——listitem 含 position、checkbox/radiogroup/radiobutton/imageanim(playFile) 升级；子结构检查覆盖 item/subItem/infos[]/items[]/radiobuttons[]
- ui_tools/HTML_SUBSET.md：铁律 #9 v2
- 回归：examples + listview/radiogroup/checkbox 合成测试 → 字段检查 PASS + fui pack 成功

---

## v0.27.2-open (2026-09-08) — 补 MT Type-A 触摸注入工具 mt_test + 协议速判坑位
**沛哥反馈**：V85X 项目调试时用现成 `ui_test` 注入触摸，FlyThings 收到坐标恒 0。
**根因（V85X gt9xx 实测）**：
- 设备触摸屏 `/dev/input/event0` = gt9xx，**MT Type-A 协议**（MODALIAS `ra30,32,35,36,39` = ABS_MT_TOUCH_MAJOR/WIDTH_MAJOR/POSITION_X/POSITION_Y/TRACKING_ID），不订阅单点协议 ABS_X(0)/ABS_Y(1)
- `ui_test` 是单点协议（ABS_X/ABS_Y + ABS_PRESSURE + BTN_TOUCH）→ 坐标被驱动丢弃 → FlyThings `x=0 y=0`
- v0.27.1 知识里只写了 MT 序列，没点破"现成 ui_test 就是单点、遇 MT 屏会失效"这个坑 → 后续 AI 调试还会踩

**改动**：
- 新增 `bin_tools/{v85x,t113,z20,z21}/mt_test`（MT Type-A 协议版，接口对齐 ui_test：tap/swipe/long/monkey/run）：
  - ARMv7 musl 版（v85x + t113）：72432 字节，工具链 `arm-unknown-linux-musleabihf-gcc-6.4.1 -static`
  - ARMv7 glibc 版（z20 + z21）：4,770,968 字节（glibc 静态链拉进 NSS，体积是 musl 的 66 倍），工具链 `arm-pc-linux-gnueabihf-gcc-8.3.0 -static`
  - RISC-V 64 musl 版（f133/f135）：暂缓（wsl.exe 被 Program Blacklist 拦截，独立 Xuantie 工具链未在本机）
- 源码来自 V553 项目 `tools/mt_test.c`（同步后项目侧删除，源已在知识里说明；产物进 MCP bin_tools）
- `bin_tools/README.md`：工具表加 `mt_test` 行（标注平台 + 协议）；新增"触摸协议速判"章节（能力位 EVIOCGABS / getevent -p / 试注入判据）；新增 mt_test 调用方法节
- `knowledge/devflow/touch-inject-autotest.md`：首选路径工具表分列 `ui_test`（单点）和 `mt_test`（MT Type-A）；新增"关键坑"小节点破 ui_test 单点协议在 gt9xx 失效；协议铁律加第 2 条 MT 完整序列 + 第 6 条"协议用错 → 坐标恒 0"判据
- 部署命令示例：`adb push bin_tools/v85x/mt_test /tmp/mt_test && adb shell chmod +x /tmp/mt_test`

**自动化测试闭环（不变）**：`adb logcat` 日志判定（首选）> raw fb 抓屏（备选）

---

## v0.27.1-open (2026-09-08) — 补触摸注入/UI 自动化测试检索缺口（AI 调试不会用现成工具）
**沛哥反馈**：adb-input-autotest.md 是不是 MCP 检索不到？AI 工具调试时没调用现成 input/ui_test 工具干活。

**根因（检索链路排查）**：
- MCP 检索范围 = wiki/flythings/ + knowledge/（open 版仓库内）；references/kb/ 是本地私有 KB，不在索引内
- MCP 命中 wiki/test/adb-input-autotest.md 是 8-31 老版（86 行，只有 event.c 实现原理，开头标注「不是现成工具产物」）
- 9-08 沛哥补充的「现成 input 命令行工具（bin/h500s/input、bin/z21/input 已编译，直接 push 用）」只写在 references 最新版（128 行）→ AI 检索不到 → 不知道有现成 ui_test / flythings_gen_ui_test → 调试不调用

**改动**：
- 新增 knowledge/devflow/touch-inject-autotest.md：以「先调现成工具」为主线——首选 flythings_gen_ui_test（traverse/monkey/custom/ask）+ bin_tools/{平台}/ui_test ELF（tap/swipe/long/monkey/run + 部署命令 + 平台表）；event.c 原理降级为「定制/移植才需要」参考；协议铁律（EV_SYN 必发/滑动逐像素/时间戳必填）；自动化闭环判定优先级（logd > raw fb 抓屏）
- wiki/test/adb-input-autotest.md 同步为 9-08 最新版（128 行，含现成工具说明），消除旧版「非现成工具」误导
- 重建 rag_index + kb_tools.py → v0.27.1-open + MCP_FEATURES 头条
 (2026-09-08) — i18n 翻译推送工具入库（修 fun launch 盲点）
**沛哥要求**：把"i18n/*.tr 转 *.json + 推送到设备"的能力整合进 MCP 流程；同时确认 fun launch 推送范围盲点（只推 ftu/images/font/lib/cfg，**不推 i18n**——CHANGELOG 2026-09-02 沛哥定规"部署统一 fun launch"是针对代码+资源，i18n 仍需显式推送），AI 改完翻译后必须调本工具。

**根因（V553 项目实测，2026-09-08）**：
- 设备 zkgui 实际加载翻译是 `/tmp/tr/<lang>.json`（DEBUG 模式），不是 .tr（XML）
- fun launch 推送范围：ftu/images/font/lib/cfg，**不包含 i18n 的 .tr/.json**
- 后果：AI 改完 .tr 后 fun launch 部署，设备仍跑旧翻译 → logcat 刷 `not found value` 警告，部分文案显示原始 key 而非翻译
- 本地开发脚本版（V553 项目）`E:\AICODE\trae\V553\tools\tr2json.py`（同日先落地）逻辑同源

**改动**：
- `i18n_tools.py` 新增 `flythings_i18n_to_json(project_root, langs='', push=True, device='')`：
  - 解析 .tr（ElementTree，XML 实体自动解码）→ 序列化为 json（tab 缩进+无空格冒号+末尾无换行，**与设备端逐字节一致**）
  - 推送：`subprocess.run(['adb', '-s', device, 'push', local, '/tmp/tr/...'])`；自动 adb 设备检测（无设备/多设备未指定/指定设备不在/均给出明确 adbStatus）
  - 生产固件翻译打包到 /res/，传 `push=False` 只生成不推送
  - `stdin=subprocess.DEVNULL` 防 MCP stdio 管道挂起（与 _run_fun/_run_fui 一致）
- `kb_tools.py` 加 `flythings_i18n_to_json` 包装函数（docstring 顶部加"fun launch 不推 i18n"警告 + 完整工作流）+ `register_all` 注册（MCP 工具数 30 → 31）
- `i18n_tools.py` 顶部 docstring 加"设备端加载格式"小节，标注本工具与 fun launch 的职责分界
- MCP_FEATURES `i18n_tools` 摘要更新为 6 工具

**用法（AI 流程标准动作）**：
```
1. flythings_i18n_import / add_language / refactor  → 改 i18n/*.tr（XML 源）
2. flythings_i18n_to_json(project_root)            → 转 json + push 到 /tmp/tr/
3. adb shell "setprop ctl.stop zkswe && setprop ctl.start zkswe"   → DEBUG 模式重启加载
```

**V553 保留**：`tools/tr2json.py` 保留作为本地开发脚本（开发者手动用，逻辑同源）；MCP 工具给 AI 流程用。

**发布修正（2026-09-08 下午，沛哥检讨确认）**：①MCP_VERSION 同步 0.27.0-open（010b4e4 提交漏递增，此前仍 0.26.0-open，客户端查版本会误判落后）；②MCP_FEATURES 顶部补 v0.27.0 摘要条目；③工具数口径核实为 30→31（实际注册 register_all 31 个；README/MCP_FEATURES 原写 32/33 均不符，已统一）；④`flythings_edit_json` 为 edit_ftu 内部辅助（从未注册），改名 `_edit_json` 去 `flythings_` 前缀消除歧义。

---

## v0.26.0-open (2026-09-08) — BusyBox 调试工具库入库 + 部署/调试场景别名映射
**沛哥安排**：设备系统内没有 busybox / ifconfig 等调试工具，需要像 input（ui_test）一样电脑端预编译各平台静态 busybox，放 bin_tools/{平台}/ 随 MCP 分发，adb push 即用；后续调试工具直接从对应平台目录找。

**改动（BusyBox 工具库）**：
- 新增 bin_tools/{f133,f135,z20,z21,t113,v85x}/busybox：BusyBox v1.36.1 全静态 ELF（CONFIG_STATIC=y，零依赖 push 即用），网络工具全开（ifconfig/ip/ping/ping6/netstat/route/arp/telnet/telnetd/nc/wget/httpd/nslookup/hostname/udhcpc...）
- 平台映射：f133/f135=RISC-V 64 musl（Xuantie-900）、z20/z21=ARMv7 glibc（arm-linux-gnueabihf）、t113/v85x=ARMv7 musl（sunxi）；qemu 实测运行 OK
- bin_tools/README.md 工具表新增 busybox 行 + 调用方法节
- 新增 knowledge/devflow/busybox-debug-library.md（检索导引：搜「busybox/调试工具/设备没 ifconfig」命中）
- 重编脚本与坑位（fun/toolchains 是 Windows exe 无法 WSL 派生 cc1、构建必须 WSL 原生盘）保留本地 tools/busybox/README.md，不入库

**改动（部署场景别名，沛哥 09-08 反馈：客户端 AI 收「AI 应用调试全量推送」时自造 deploy_debug.sh）**：
- flythings_build_ui_flow docstring 头部加「场景别名」段：编译/构建/调试/全量推送/部署/部署到设备/跑一下/AI 自定义编译/自主编译验证 → 一律本工具，禁止自创脚本路径
- 新增 knowledge/devflow/deploy-scene-map.md（用户话语→唯一动作映射表 + 坑源 + 历史依据）
- 重建 rag_index + kb_tools.py → v0.26.0-open + MCP_FEATURES 头条

---

## v0.25.2-open (2026-09-07) — 自研帧动画知识移出 open 版（保留本地）
**沛哥指示**：ImageAnimView/FrameImageView（ZKBIN+QOI+region 脏矩形机制）依赖自研 ZKBIN 打包工具链，open 用户缺失工具无法使用 → open 版 MCP 删除，知识保留本地（references/kb/frame-image-anim-bin.md，4 行说明头 + 125 行完整原版）。

**改动**：
- 删除 knowledge/devflow/frame-image-anim-bin.md（git 历史 v0.22.0 有完整原版可追溯）
- dashboard-can-arch.md 还原 v0.22.1 无 ImageAnimView 版：6 处引用全部清除（顶部说明/BMW 行/帧号即角度/差异表指针行/进出场动画行/参考索引），恢复「细节未收录」口径，CAN 架构知识完整保留
- 重建 rag_index + kb_tools.py → v0.25.2-open + MCP_FEATURES 头条

---

## v0.25.1-open (2026-09-07) — 清理 knowledge 与 wiki 重复副本（去冗余）
**沛哥要求**：整理 open 版 MCP 多余反复内容。

**冗余检测结论**：
- knowledge/ 3 个文件与 wiki/flythings 字节完全相同（当初入库时直接复制）→ RAG 索引双份、检索重复命中：
  esl/tag-esl.md、uicontrols/image-path-rule.md、uicontrols/scrollwindow-layout.md
- layout-audit.md 两版 98% 相似但**非字节相同**：knowledge 版含实测校准（edittext id 段 51000 vs wiki 60000、imageanim 实测无 frameInterval）→ **保留 knowledge 实测版，不删**
- wiki 官方源自身重复（multimedia/video.md == uicontrols/video.md、devflow callback/naming 重复块）→ 属官方 wiki 全量镜像，不动
- 新增 11 篇 *-fields.md 与 wiki 同名文档内容互补（覆盖率 0~10%）→ 非冗余 ✅

**改动**：
- 删除 knowledge/ 3 个重复副本（wiki 保留唯一一份）
- 重建 rag_index.json（980 chunks 不变属预期：wiki 全量为主，重复副本去除后检索不再双份命中）
- kb_tools.py → v0.25.1-open + MCP_FEATURES 头条

---

## v0.25.0-open (2026-09-07) — 冷门控件字段文档批量入库（git.com 全库学习产出）
**背景**：沛哥要求拉取公司内网 git.com 全部代码学习，扫盲 FlyThings 控件盲区；本轮把实测字段/用法沉淀进 uicontrols。

**新增知识文档（knowledge/uicontrols/，全部 fui unpack 实测 + SDK 头文件校准，非猜测）**：
- pointer-fields.md：指针控件（rotationPoint/fixedPoint 双坐标定圆心、animatable+rotateSpeed 自动动画 vs 线程驱动、clockDemo 表针换算）
- circlebar-fields.md：圆形进度条（有效图扇形裁剪、textType 0/1/2、触摸拖动监听、产品只读用法）
- digitalclock-fields.md：数字时钟（纯属性显示、beat 冒号跳动、TimeHelper 改系统时间）
- slidetext-fields.md：滑动文本（拼音输入法候选词条 setTextList/onTextUnitClick 实测）
- qrcode-fields.md：二维码（loadQRCode 传字符串/JSON，价签 SN 码场景）
- radiogroup-checkbox-fields.md：单选组/复选框（radiobuttons 子项 ID 宏选中、选中图是 pic2、监听器）
- diagram-fields.md：波形图（统一 SZKPoint；setData 全量 vs addData 增量/step/eraseSpace 语义；style 0折线 1曲线）
- videoview-fields.md：视频（轮播模式 loopPlayback=true 自动读 UI名_video_list.txt；API 模式 play/seek/setVolume/消息监听）
- pagewindow-fields.md：多页窗口（onPageChange/turnToNextPage，与 slidewindow/scrollwindow 区分）
- listview-fields.md：列表（三回调+id=被点 subitem ID（沛哥确认）；无 subitem 数量限制；删除行套路）
- cross-thread-ui-rule.md：跨线程操作 UI 规则（沛哥确认：所有控件支持跨线程，框架内部处理）
- slidewindow-fields.md 补充：宫格翻页语义（cols×rows=每页格数，11 项=1 页 8 + 3 翻页，沛哥确认）

**代码操作汇总**：basedemo 35 个全控件 Demo（projects/basedemo-new_z20_1024_600/）逐个学习；KaiduZ9S 拼音输入法、Advertising 视频轮播、lib-ai 音频波形等产品实例验证。

---

## v0.24.1-open (2026-09-07) — 修复 search 首次调用 30s+ 超时（embedding 启动预热）
**沛哥反馈**：提交给用户的 open 版 MCP search 全部失败（卡死/超时）。

**根因**（协议层逐级打点 + 对照实验定位）：
- `flythings_search` 在 stdio MCP server（mcp.run() 事件循环）内**首次**调用时，
  embed() 首次加载 onnxruntime session 实测耗时 **30.2s**（cos 排序/BM25/RRF 融合合计仅 0.07s），
  超过客户端工具超时 → 每次新会话/新进程第一次 search 必失败。
- 排除项：索引/模型文件完好（922 chunks 正常中文）；独立进程直调、各 import 组合、
  子线程首次加载全部 <0.3s；仅 mcp.run() 运行环境内首次加载异常慢。

**改动**：
- ★ mcp_server.py：mcp.run() 前预热 embedding（embed_local.embed 一次，~0.2s；
  模型缺失/加载失败静默跳过，自动降级 BM25）——session 就绪后检索全程 0.07s 秒回
- kb_tools.py → v0.24.1-open + MCP_FEATURES 头条
- 验证：真实 mcp_server.py stdio 协议层连续双调用均 0.07s 返回（修复前首次 30s+ 超时）

---

## v0.24.0-open (2026-09-07) — 恢复 ImageAnimView 可复用知识 + 清理"不收录"声明（沛哥定规）
**沛哥定规**（2026-09-07 21:59）：① 范围=**全部**——可复用能力知识不锁死，用户需要用到这些功能时都能开发；
② **不收录部分直接不体现即可**——不留"不收录/自有技术"声明字样，文档只保留可复用通用内容。

**背景**：v0.22.1 曾按早期理解移除 ImageAnimView 帧动画知识，现恢复（该技术为 ZKSWE 自研通用能力，可跨项目复用）。

**改动**：
- ★ 恢复 **knowledge/devflow/frame-image-anim-bin.md**（v0.22.0 原版 125 行完整恢复）：
  自研帧动画控件 ImageAnimView/FrameImageView 机制（ZKBIN=zlib+QOI 帧文件 / region.bin=ZKREG 相邻帧差异表 /
  脏矩形局部 invalidate / 异步线程解码 / play(角度) 帧号即角度 + 开机扫针）+ 选型表 + 坑位 7 条；
  与 IDE imageanim 动图控件(GIF/WebP) 区分说明保留
- ★ knowledge/t113-car/dashboard-can-arch.md 还原 ImageAnimView 引用：
  顶部"细节未收录"提示删除并指向 frame-image-anim-bin.md；表格 BMW 行恢复「自研 ImageAnimView 帧动画」；
  §3 帧号即角度补回说明；§5 差异表 BMW 行恢复；§6 参考文件索引补回帧动画文档
- ★ knowledge/v85x/uvc-usb-camera.md 头部转正：去"草稿（待入库）"标记、
  去"定制模块私有协议层…不收录"声明 → 改为「本文为通用 UVC 接入链路，任意 UVC 摄像头产品可复用」
- 全库复查：无"不收录/不入库/待入库/自有技术"残留（仅保留 uicontrols/retrieval-boundary 的检索边界规则文档）
- kb_tools.py → v0.24.0-open + MCP_FEATURES 头条
- 索引重建验证：「帧动画 ImageAnimView」「UVC 接入 预览录像拍照」检索命中

 (2026-09-07) — V85X 显示分层权威口径补充（沛哥答疑三点）
**沛哥答疑**（追问 CV201_PND UVC 流程"数据流如何放到图层"时确认）：
1. **VI→VO 是内部处理，不需要关心**——取流→VI→VO 视频层的数据搬运由 mpi/aw-dvr 内部完成，应用层只配置 CameraParam
2. **UI 层在最顶上**，其下 disp 视频层按 **4、3、2、1** 顺序叠放
3. **layer 编号 = disp 硬件层号**（不是 mpi 逻辑层）——工程绑定 FrontCamera→layer0、UVC RearCamera→layer4

**改动**：
- ★ `knowledge/v85x/videoview-transparent-window.md` 原理节重写为权威口径：
  显示分层结构（UI 顶 + disp 视频层 4321 在下）+ VI→VO 内部处理说明 + 坑位补「layer 不要乱改」
- ★ `knowledge/v85x/uvc-usb-camera.md` 头部补「显示分层权威口径」注释块（UI 顶 / layer=disp 硬件层 / VI→VO 内部）
- kb_tools.py → v0.23.1-open + MCP_FEATURES 头条
- 索引重建验证：「videoView 透明 视频层」「disp 硬件层」检索命中

 (2026-09-07) — V85X 摄像头自维护出图 → videoView 零代码透出视频层（沛哥知识补充）
**沛哥知识补充**：V85X 类型的摄像头，如果显示内容由**用户自己打开摄像头并维护出图**（不走 FlyThings 预览/播放链路），
**UI 只需要添加一个 videoView 控件，不需要写任何关联代码**——只需在 UI 层开一个透明区域给 Video 层，画面即可透出。

**改动**：
- ★ 新增 **knowledge/v85x/videoview-transparent-window.md**：
  - 场景区分表：A. cameraview 实时预览（内置链路） / B. videoview 播文件回放 / C. **用户自维护出图 → videoview 当透明渲染窗口（本知识点）**——禁止套错
  - 操作极简：UI 放 videoView（轮播=否）→ 位置/尺寸即画面区域 → **logic.cc 零代码**（不 play 不设源），用户侧出图代码与 UI 互不感知
  - 原理：videoView = UI 层给 Video 层开的透明窗口，控件区域不画不透明背景 → Video 层画面透出
  - 坑位：别画不透明背景遮挡 Video 层、别当场景 A/B 套代码、平台限定 V85X
  - 官方口径佐证：video 控件「轮播类型=否」= 仅创建视频渲染区域（wiki uicontrols/video.md）
- 索引重建验证：「摄像头画面自己出图 videoView 透明」「videoView 不写代码显示摄像头」检索命中

 (2026-09-07) — 修正：移除 ImageAnimView 帧动画知识（沛哥：自有技术不入库）
**沛哥指示**：v0.22.0 中新增的 `knowledge/devflow/frame-image-anim-bin.md`（自研 ImageAnimView/FrameImageView 帧序列控件详解，
ZKBIN/QOI/region.bin 内部格式与脏矩形机制）属工程自有技术，**不进 open 版知识库公开交付**。

**改动**：
- 删除 **knowledge/devflow/frame-image-anim-bin.md**（ImageAnimView 自研帧序列控件知识全部移除）
- dashboard-can-arch.md 同步清理：BMW 指针方案改为中性表述「预渲染帧图驱动（细节未收录）」，
  去掉 ImageAnimView/ZKBIN/帧动画扫针等实现细节引用，文档顶部加「只收录 CAN 架构，指针动画细节未收录」提示
- kb_tools.py：v0.22.0 → **v0.22.1-open**，MCP_FEATURES 头条重写（只描述 CAN 架构入库 + 不入库说明）
- 索引重建验证：「仪表盘 CAN」「车速转速指针」命中

 (2026-09-07) — T113 车载仪表 CAN 架构 + 自研帧动画控件入库（沛哥安排：学习 DashBoard_T113 整车代码提炼）
**沛哥工作安排**：学习整车代码（BMW/Comaro/Jeep 三套 T113 仪表工程，ZKSWE Develop Team 编写）后提炼知识库交付 MCP。
整车代码位置：`projects/LearningProject/DashBoard_T113/`（BMW 帧动画在 `BMW/jni/ui/ImageAnimView.{h,cpp}`，实测确认作者=ZKSWE Develop Team，自家技术可入库）。

**改动**：
- ★ 新增 **knowledge/t113-car/dashboard-can-arch.md**（T113 车载仪表 CAN 应用架构，三套工程实测）：
  - 架构一句话：CAN 收线程(SocketCAN can0 500k) → `can::parseProtocol` 查 **ID 解析表**(0x1FFF00xx 扩展帧) → 逐位解包写全局 `DashboardData` → 遍历 `CanDataCb` 回调通知 → 页面字段 diff 后刷新
  - 可抄模式：ProcFun 解析表驱动、CanDataCb 函数指针结构体 + 页面级 add_cb/remove_cb 订阅退订、回调内字段级 diff、灯 4 态(FLICKER_500/1000 定时器翻转)、方控边沿检测、故障码 0x1A52 加/0x1A55 删
  - 换算陷阱：speed 0xFFFF/rpm 655 无效值回零位、温度华氏/摄氏双查表、帧号即角度(speed+30 / rpm*2+30)
  - 三套工程差异对照表（BMW 预渲染帧图驱动 / Comaro TweenCpp+CircleBar / Jeep setTargetAngle + 老 m_can 回调 + ID 段 switch）
- ⚠️ BMW 指针预渲染帧序列控件的内部实现（ZKBIN/QOI/region 格式）属工程自有技术，**不入库**（沛哥 2026-09-07 指示，frame-image-anim-bin.md 已移除）
- 索引重建验证：「仪表盘 CAN」「车速转速指针」检索命中

---
## v0.21.0-open (2026-09-07) — V85X JPEG 解码 / 录像编码用法入库（编码解码两场景分开）
**沛哥定规**：MJPEG 转码录制内部（aw-dvr 闭源）没有源码就不用管，**只记录怎么用**；
V85x 带编码器录制默认 **mp4/ts 两种格式**，客户要其他格式（如 AVI）提示大文件格式确认后再做；
**编码、解码两个不同场景区分去处理**。

**改动**：
- ★ 新增 **knowledge/v85x/jpeg-decode-record.md**（V853 JPEG 硬件解码 + MJPEG 录像编码用法，场景分两块）：
  - **① 解码场景**：`mpi::JpegViewer`（照片显示到指定屏幕区域，DvrPlayLogic 实测用法）；
    `jpegdecode.h`（libcedarc C API 取像素：NV21/NV12/YU12/YV12/RGB565 输出 + 1/2/4/8 缩放）
  - **② 编码（录制）场景**：`mpi::Recorder` 用法（RecordingSettings 字段 + start/stop/state/elapseTime/isLocked），
    UVC MJPEG 摄像头全链路（注册 REAR setUvc(true) → SharedVideoDevice 保活 → 双路 settings[FRONT]+[REAR] → USB 断开先 stop 再重建）；
    **格式口径：带编码器默认 mp4/ts 两档（FileFormat{JPEG,TS,MP4}），客户要 AVI 等 → 提示大文件格式，确认后再说**；
    拍照走 `mpi::Snapshot`（非 Recorder::takePicture），闭环 Recorder(录)↔Snapshot(拍)↔JpegViewer(看)
  - 坑位：Recorder 与预览互斥（拔插/切流先 stop）、UVC 必须持续读流保活、显示照片先停视频、闭源转码内部不深挖
- 索引重建：890 chunks（23 knowledge）验证——「V853 JPEG 硬件解码」「MJPEG 摄像头录制 mp4」「录像格式 mp4 ts avi」命中 top1-2

---
## v0.20.0-open (2026-09-07) — USB HOST 外设接入客户场景入库（沛哥：USB HOST devices / 主从切换都参考跨平台对照回复）
**沛哥补充**：客户问题涉及 **USB HOST 外设接入**（U盘/摄像头/键鼠读不到）与 **主从切换** 时，
回复口径统一参考 `hardware/usb-otg-switch.md` 这份跨平台对照（不只是「怎么切」命令）。

**改动**：
- ★ usb-otg-switch.md 标题与检索导引扩展：纳入「USB HOST 外设接入」「U盘插上没反应」「USB host devices」等问法
- ★ 新增 **「USB HOST 外设接入（客户场景）」节**：
  - U盘/TF 存储：官方口径（wiki tf_usb）插 TF→自动挂 `/mnt/extsd`、U盘→`/mnt/usb1|usb2|usb3`；
    工程实测（CV201_PND / T113CarSystem_PND `media_context.cpp` 存储表）另有 OTG 口挂 `/mnt/usbotg`；
    监听拔插：`base::MountNotification`（base-utility ≥9.0.0）/ `MediaMountListener : MountMonitor::IMountListener`，
    查询 `MOUNTMONITOR->isMounted()`；客户「U盘读不到」排查顺序：①otg_role 确认 host ②ls 挂载点 ③确认哪个口 ④监听事件
  - USB 摄像头（UVC）→ 指向 `v85x/uvc-usb-camera.md`（V85X 完整接入知识）；T113/Z21 未收录不编造
  - USB 键鼠（HID）→ **标「未收录」**，问沛哥/查官方文档，不猜
- ★ kb-first-analysis 铁律 6 扩写：host 外设接入（U盘挂载/摄像头/键鼠）+ 主从切换同属跨平台问题，
  未指定平台先给对照+问平台，禁止默认按命中第一平台答
- 索引重建：878 chunks（22 knowledge）验证——
  「U盘插上没反应」「/mnt/usb1 usbotg」「Z21 键鼠 USB 支持吗」「T113 U盘挂载」等客户问法全命中跨平台文档

---
## v0.19.0-open (2026-09-07) — 跨平台 USB OTG 切换对照：不带平台名提问不默认 V85X
**沛哥追问**：「用户不指定 V85x 的时候能识别到这个 OTG 切换问题吗？还有 Z21、T113 平台」——
只让 v85x 文档可命中不够：不带平台名提问时 AI 应意识到 OTG/ADB/U盘 切换是**跨平台共性操作**，
V85X/T113/Z21 路径各不相同，答错平台就误导。

**改动**：
- ★ 新增 **knowledge/hardware/usb-otg-switch.md 跨平台对照**（新开 hardware 分类目录）：
  三平台路径/节点/shell/代码/configfs 对照表 + 坑 + 来源标注；
  首块植入高频问法检索导引（如何切换 USB OTG/怎么切 ADB/切 U盘/USB 连电脑拷文件…），
  并写明「未指定平台 → 必须给三平台对照 + 请用户确认平台，禁止默认按某一平台答」。
  - V85X：`/sys/devices/platform/soc/usbc0/`（CV201_PND/xdv23 实测，4 节点）
  - T113：`/sys/devices/platform/soc@3000000/soc@3000000:usbc0@0/`（⚠️ 带 reg 地址，T113CarSystem_PND 实测）
  - Z21：`/sys/devices/soc0/soc/soc:usbotg/`（wiki 官方文档，仅 usb_host/usb_device 两节点）
- ★ kb-first-analysis.md 新增**铁律 6**：跨平台硬件操作（OTG/GPIO/串口/路径类）用户未指定平台时，
  回答必须给多平台对照表 + 请用户确认平台；禁止默认按检索命中第一的平台答（v85x 文档块多常霸榜）。
- 索引重建：874 chunks（21 knowledge）验证通过——不带平台名 OTG/ADB/U盘 问法跨平台文档进 top2-3，
  「怎么切到 ADB 模式」「usbotg 路径平台区别」跨平台文档 top1。

---
## v0.18.0-open (2026-09-07) — RAG 混合检索修复：V85X USB OTG 专项文档可检索命中
**沛哥反馈**：搜「V85x 如何切换 USB OTG / V85x USB OTG 切换 host device」时纯向量检索
命中 Z21 通用文档（z210_core_board），`knowledge/v85x/usb-gadget-storage.md` 专项文档查不到
（向量语义偏 + 文档标题/首块无 OTG/切换关键词）。

**三处修复（检索端 + 文档端 + 索引）**：
- ★ rag_search.py 检索策略升级：**纯向量 → 向量 + BM25 双路 RRF 融合**（两路各取 top40，
  RRF 平滑常数 K=60 重排）。向量抓语义近邻、BM25 抓专名/缩写精确命中，
  「V85x/USB/OTG/host/device」等混合查询命中率显著提升；BM25 兜底路径不变。
  by_id 映射模块级建一次，无每次检索重建开销。
- ★ usb-gadget-storage.md 文档增强：标题改为「V85X USB OTG 切换与 Device 存储」；
  首块加 🔍 检索导引（一句话：读 /sys/devices/platform/soc/usbc0/ 节点即切换 + cat 四条命令）；
  §3 标题含 host/device 关键词。
- ★ 新增 **knowledge/v85x/usb-otg-mode-switch.md** 直达速查（问答式）：
  一句话结论 + 切 ADB/切 U盘/断开/查当前四种 cat 命令 + 代码切换（usb_monitor.cpp 同款）
  + V85X vs Z21 路径对照表；细节指向 usb-gadget-storage.md 避免双份维护。
- ★ 新增 **knowledge/devflow/kb-first-analysis.md 开发先检索铁律**（沛哥 2026-09-07 定规）：
  AI 做 FlyThings 开发必须先用 MCP 知识库（flythings_search = wiki + knowledge）检索分析再动手；
  禁止先试错后查（顺序反了浪费迭代）；查不到 ≠ 没收录（换词/读 knowledge 目录）；
  禁止套其他 GUI 框架/解析 easyui 源码猜字段；检索接入异常先检查 MCP 连的是不是 open 版。
- 索引重建：863 chunks（20 knowledge）本地 bge 全量嵌入，4 组回归查询 v85x 文档均进前列。

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
