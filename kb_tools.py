# -*- coding: utf-8 -*-
"""FlyThings_mcp_open: 全套 MCP 工具定义（stdio 本地部署，完全开放）。

每个工具都是普通函数，返回 str/JSON 字符串；由 mcp_server.py（stdio）注册。
✅ 开源版：检索完全本地化（内置 bge-small-zh 向量模型，免 API Key，
不可用时自动降级 BM25），不依赖任何远程 MCP 服务。
"""
import html.parser  # PyInstaller 打包需要（html2json 运行时导入，静态分析漏收）
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag_search as rs
import project_tools as pt
import package_tools as pkgtools
UI_TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ui_tools')
if getattr(sys, 'frozen', False):  # PyInstaller 打包：ui_tools 随包进 _MEIPASS
    UI_TOOLS = os.path.join(sys._MEIPASS, 'ui_tools')
if UI_TOOLS not in sys.path:
    sys.path.insert(0, UI_TOOLS)
import html2json as h2j
import json2html as j2h
import gen_res as h2j_genres
import i18n_tools as itx
import test_tools as tt
# UI 可视化编辑 / 像素验收（2026-09-10 起）：缺依赖时降级为对应工具报错，不影响其它工具
try:
    import ui_editor as uied
except Exception:
    uied = None
try:
    import ui_edit_apply as uia
except Exception:
    uia = None
try:
    import ui_diff as udf
except Exception:
    udf = None
try:
    import device_screenshot as dss
except Exception:
    dss = None

# ========== MCP 版本号（每次发布递增，AI/用户可查询确认是否最新）==========
MCP_VERSION = '0.27.23-open'
MCP_BUILD = '2026-09-10'
MCP_FEATURES = [
    '2026-09-10: 触摸语义修正 v0.27.23（沛哥：项目 UI 实现发现的问题，前两项会产生错误代码优先改）——①**radiogroup touchable 必须 true**（`json-field-mandatory.md` 第 12 行口径补例外 + radiogroup 行改 true；`html2json.py` `_open_radiogroup` 模板 False→True；**它是「容器显式 false」通用口径的例外**（radiogroup 是交互集合不是背景容器），写 false 会让整组收不到触摸=单选按钮点了没反应）②新增 `knowledge/uicontrols/touch-events.md`（触摸事件与 touchable 语义 /「点了没反应」排查手册）：**touchable≠穿透开关**（只管收不收触摸，不靠它实现穿透）、交互控件必 true、容器/纯显示 false、层叠顺序决定谁收到触摸、「点了没反应」六步排查顺序（touchable→上层遮挡→是否在当前 window→回调名是否匹配 caption→状态类是否漏 refresh→真机截图+logcat）③`listview-fields.md` 铁律 7：`setSelection(idx)` 后**必须** `refreshListView()`（只改选中态不重绘，漏刷新界面不更新）④`json-layer-rules.md` 第 7 条：层叠顺序决定谁收到触摸（上层 touchable:true 先截走）⑤`radiogroup-checkbox-fields.md` touchable 单独拎出说明；v0.27.23-open',
    '2026-09-10: 真机抓屏工具入库 v0.27.22（沛哥：从设备取图的能力 AI 不知道，直接给明确指令）——新增 flythings_device_screenshot：把设备当前显示的画面抓成 png/jpg/bmp 给 AI 看（视觉分析）或给 ui_diff 做像素验收。要点：①设备 rootfs 裁剪版**没有 screencap/dd/head**，`adb exec-out` 也不可用（patched adbd 无 shell v2 → error: closed），唯一链路=设备侧 `busybox dd ... | busybox gzip -1 > /tmp/x` + `adb pull`（实测 600x1600 裸 raw 7.68MB 经 WiFi pull 要 4 分钟+，gzip 后只有 37KB、0.3 秒）（无 busybox 时退化 cat + pull 并提示）②fb 参数必须问 sysfs（modes=可见分辨率 / virtual_size 可能是 2 倍 OVERALLOC / stride / bits_per_pixel），可见高≠文件行数，必须按 stride 逐行取 ③**双缓冲页翻转坑**：palette 必须读 `/sys/class/graphics/fb0/pan` 的 yoffset 并 `dd skip=<yoffset>`，否则抓到的是上一帧旧画面（本机实测 pan=0,1600，pan 取值靠前一半就是旧屏）④32bpp 内存序 BGRA（小端 ARGB8888），按 alpha 字节位置自动判通道序，红蓝互换可传 pixel=rgba ⑤输出支持 fmt=png/jpg/bmp + scale 缩放 + quality；v0.27.22-open',
    '2026-09-10: UI 布局可视化编辑 + 像素验收工作流入库 v0.27.21（knowledge/devflow/ui-layout-verify.md；配套 v0.27.20 的 flythings_ui_editor / ui_edit_apply / ui_diff）——要点：json 是唯一真相（设备加载 ftu，ftu 由 json pack，手写 HTML 预览=第二份真相必然漂移；json2html 也只是近似，像素真相只有真机截图）；三段式验收（预览→真机截图→像素 diff）；编辑器指哪打哪（Alt+点穿透下层、✥绿块拖遮罩下控件、属性栏按原 json 动态出字段、id 只读、visible:false 幽灵框）；变更写回三条安全（.bak / 格式自检 / 边界钳制）；像素 diff 默认容差±2+抖动补偿+模糊+噪声块过滤，主力是回归对比（改前截图 vs 改后截图），分层省钱 L1 像素(0 token)→L2 只裁差异区小图给模型→L3 人工看标注图；图片引用是相对 resources 可带子目录的路径（audio/horn.png），只按 basename 找 resources/images 会大面积丢图；现象→根因排查表（锯齿/位置/切图/丢图/裁字）；v0.27.21-open',
    '2026-09-10: UI 可视化编辑 + 像素验收入 open 版 v0.27.20（沛哥：布局调整要「指哪打哪」，预览里的文字/属性都要能改，图片资源要能加载）——新增 3 个工具：① flythings_ui_editor：ui/*.json → 单文件可拖拽编辑器（拖/缩放/Alt+点穿透选中下层/属性栏列出全部字段含 text·fontSize·colorTab·picTab 四状态图，改完画布即时生效，id 只读；内置图片尺寸≠控件尺寸红黄标）② flythings_ui_edit_apply：变更 JSON（changes 几何 + props 属性）写回 ui/*.json（自动 .bak + 格式自检）并 pack ftu ③ flythings_ui_diff：像素 diff 0 token，容差±2 + ±1px 抖动补偿 + 高斯模糊 + 噪声块过滤，输出差异清单/标注图（回归对比专治改 A 碰坏 B）；顺带修 json2html 图片路径解析（支持 audio/xxx.png 这类带子目录的相对 resources 引用，之前只按 basename 找 resources/images/ 导致预览丢图、尺寸预检形同虚设）；v0.27.20-open',
    '2026-09-09: package API 识别规则定规 v0.27.19（沛哥 21:42：AI 对 FlyThings package 只允许通过头文件识别 API，不要猜也不要反编译二进制浪费时间，不会就是不会；标准 C/C++/Linux 开发按标准+开源社区参考）——retrieval-boundary.md 新增「Package API 识别规则」：package C++ API（类/方法/枚举/注释）只读包内头文件（aw-dvr mpi/*.h、easyui control/*.h）；禁猜（读不出标未收录问官方）/禁反编译（objdump 禁止，readelf 仅排障用）；两层区分：头文件能确认的（签名/枚举/注释）读头文件、表达不了的（控件 json 字段/回调语义）走 wiki/knowledge（与 09-01 easyui 条款不冲突）；标准 C/C++/Linux（socket/pthread/v4l2/std 等非 FlyThings 私有 API）按标准+开源社区参考不受限；v0.27.19-open',
    '2026-09-09: MCP 知识库结构化整理 v0.27.18（沛哥确认：平台化/结构化治理，消重复啰嗦）——①content 唯一化：删除 wiki/flythings 下 44 篇 knowledge 实践文档副本（28 字节相同双命中 + 16 漂移），实践知识唯一放 knowledge/（随 Gitee+检索主源），wiki 只留官方镜像 129 篇；rag 去重重建 ②MCP_FEATURES 精简 70 条 25.8KB → 近期精华+能力概括（完整史在 CHANGELOG）③治理机制固化：knowledge/README.md 治理规范（新增文档只改 knowledge 禁复制 wiki/命名/流程红线）+ scripts/check_duplicate.py 双份检测工具',
    '2026-09-09: 异步资源释放反模式入库 v0.27.17（⑥ V553 实证：UI 回调固定 sleep 等媒体资源释放=空等永不释放资源，浪费 4 小时）——cross-thread-ui-rule.md 新增「异步资源释放反模式」：UI 回调（onUI_quit/hide/Timer）禁止固定 sleep 等资源释放（卡 UI 线程+时序脆弱）；先确认资源会不会释放/由谁释放，再选三选一：①官方回调/轮询确认（stop 完成回调/线程退出标志/资源可用轮询）②raw 层强制回收（AW_MPI_VO_Disable 拿返回码，见 v85x/display-layer-debug.md §4）③接受重建（确认不需要就重建通路不空等）；实例=播放页退出→预览 VO 冲突 0xa00f8042（错误 sleep 等让位，正确 raw VO_Disable 或 enable 轮询重试）；固定 sleep 仅已知释放时长上限+无回调可用时兜底且注释；v0.27.17-open',
    '2026-09-09: 部署可靠性 v0.27.16（④ V553 踩坑：fun launch 网络超时静默/推送中断误推旧固件；沛哥指示 timeout 就 retry 5 次、不自写 push 脚本校验、信任 fun 差分）——_run_fun 加 retries 参数（失败/超时自动重试间隔 2s，返回含 retried）；flythings_build_ui_flow 的 fun launch 传 retries=5（网络抖动自愈），5 次仍失败才 needDeviceInput 询问设备接入；未自写任何 push/校验脚本；kb_tools 工具描述同步；v0.27.16-open',
    '2026-09-09: V553 踩坑 ②③ 入库 v0.27.15（沛哥要求先检讨正确性：②缺口属实 ③主体属实且揪出旧策略误导——"直接用最新版 aw-dvr"致 V553 选 4.0.1 踩 dlopen 坑，已修正）——②activity-code-skeleton.md 新增 §3-1 导航×回调触发矩阵：**goBack/返回销毁只走 onUI_quit、不经 onUI_hide**（日志实证；释放放 onUI_hide=永不执行=VO 残留事故代码根因）；openActivity 覆盖→onUI_hide；铁律=媒体/硬件资源释放放 onUI_quit、hide 只做被覆盖暂停 ③新增 v85x/aw-dvr-runtime-compat.md：版本×runtime 矩阵（3.13.12↔aw-mpp 2.0.2 ✅ 全适配当前实测组合 / 4.0.1 需 aw-mpp 3.0.0-pre2 ❌ runtime 2.0.2 装不上 / 3.9.12 ⚠️能跑不能录 UVC 待复核）；勿加 aw-middleware（旧包头冲突+无 UVC backend）；libmpp_uvc.so 由 aw-mpp-uvc 提供；dlopen 失败 SOP=readelf -d NEEDED→比对设备库→readelf -Ws UND 找版本专属符号→换 SDK 或升 runtime；dvr-recorder-guide Manifest 示例/版本策略/自检清单同步修正；v0.27.15-open',
    '2026-09-09: VO dev0 抢占冲突排障知识入库 v0.27.14（V553 UVC 相机项目实证：从独立播放页返回预览页图像出不来，logcat 反复 0xa00f8042 AW_MPI_VO_Enable error；此坑全库 0 命中——disp 层知识只到 layer 级没到 VO dev 级）——①错误码实锤 0xa00f8042=EN_ERR_VO_DEV_HAS_ENABLED（aw-mpp mm_comm_vo.h，VO 设备已被 enable；0x41=DEV_NOT_ENABLE 常态忽略）②架构事实：easyui ZKVideoView(zkmedia/CedarX) 与 mpi 预览(aw-dvr RearCamera) **共用 VO dev0**，播放器退出/播放页销毁后 VO dev0 不自动释放 → mpi enable 报 HAS_ENABLED；触发条件=播放页独立 Activity 走销毁路径，videoview 常驻同页无此问题 ③解法：mpi 预览启动前 **raw AW_MPI_VO_Disable(0)** 强制让位拿返回码（⚠️ mpi::VO 包装类 disable 吞异常/不返回真实码，必须 raw API）；Disable 失败 sleep 300-500ms 重试 2-3 次（播放器异步释放~400ms）；兜底 enable 失败 Disable+延时重试循环 ④排查顺序 disp 层(releaseLayer)→VO dev(0xa00f8042→raw Disable)→UI 透出(videoView visible)；display-layer-debug.md 新增 §4 VO dev0 抢占冲突（§4-7 顺延 §5-8）；v0.27.14-open',
    '2026-09-09: demos 案例库上线 v0.27.13（沛哥拍板方案 B：验证全功能 demo 带着走，AI 照抄避免反复 try 浪费 token；后续可批量做）——①新增 demos/README.md 案例库规范：demo=已真机验证可编译可运行的功能闭环（源码级 <100KB）；命名 <功能>-<形态>-<平台>；必备 Manifest/ui json+ftu/src 只写 logic/package.properties/README 三件套；红线：accessKey 占位 REPLACE_WITH_ACCESS_KEY_FROM_ZKSWE 禁止真实 key 进公开仓库、不提交 .fun/exe/.vscode、去工程化、闭环宁缺毋滥；knowledge 头部加 demo 指引 ②首个案例 demos/dvr-uvc-recorder-v85x/：V85X+1600x600 竖装屏(rotateScreen270)+USB UVC(JPEG/MJPEG) DVR 全链路参考工程（探测协商/预览/拍照/录像/停止/回放 + releaseLayer + 保活 + videoView 透明窗 rotation:3），真机全链路验证过，内置 AHD/TVI 双路改法见 README ③dvr-recorder-guide.md 头部加 demo 指引；v0.27.13-open',
    '2026-09-09: DVR 录制功能端到端 Playbook v0.27.12（沛哥：外部开发者同步 MCP 要能准确无误开发 DVR 类录制功能、AI 不走弯路）——盘点确认知识碎片化缺功能链串联 + TF 卡格式化要求未入库；新增 ①knowledge/v85x/dvr-recorder-guide.md（12 节端到端：文档地图防漏环节/前置 4 问/Manifest aw-dvr accessKey 最新版策略/屏幕方向 rotateScreen 硬件适配/UI videoView 可见透明窗+rotation 枚举 3=270°/摄像头内置 mpi+UVC JPEG 双形态/录像产品级+UVC 简化两套参数（frame_rate 15~60、size=实际分辨率）/拍照回放 VO 延迟初始化/存储/排障日志判据表（黑屏 fps、绿屏=0字节文件、一直提示格式化=卡被电脑格过）/8 项自检清单）②knowledge/v85x/tfcard-format-requirement.md（V85X TF 录制卡专属格式 FAT32+64KB 簇 65536+OEM=zkswe；statfs f_bsize==65536 校验，不符弹「文件系统不符合要求」；挂载失败 5 次自动强制重格；电脑 FAT32≤32KB/exFAT/NTFS 判不符=录不了像头号原因；formatTfcardProcess 统一流程；双介质探针）；v0.27.12-open',
    '2026-09-09: V85X 显示分层调试入库 v0.27.11（竖屏 600x1600 + 横 UI + UVC 摄像头实测：错屏/无图像/回放方向三连坑闭环）——①**错屏=UI 布局超出屏幕**（横 UI 1600×600 在竖装屏 600×1600，不旋转时 1600 宽 > 600 物理宽，内容溢出屏外）；rotateScreen 是**硬件物理方向适配**（值由屏幕安装方向决定，非 UI 分辨率/代码决定）→ package.properties 写 EasyUI.cfg={"rotateScreen":270}（触摸不转=不写 rotateTouch），改后必 fun clean 全量重编（ninja 不感知 package.properties），EasyUI.cfg 由 fun launch 合并生成 ②**无图像根因=UI 层(z=16 最顶)不透明盖住 disp 视频层(z=1)**：摄像头 fps 30 正常+视频层 enable 也没画面，UI 必须有 **visible:true 的 videoView 透明窗口**（visible:false 是最常见坑，不透出=视频层白跑；position=画面区域，自维护出图零关联代码）③**ZKVideoView rotation 是枚举 0/1/2/3=0°/90°/180°/270° 顺时针，写 270 无效被忽略**，竖屏回放写 rotation:3（同平台产品 DvrPlay 同款）④releaseLayer 释放残留 disp 层工具代码（保留 UI 层 ch2/layer0；include 坑：直接 <video/sunxi_display2.h> 缺 s32/u32 编译错，用 aw-mpp <vo/hwdisplay.h>）；新增 knowledge/v85x/display-layer-debug.md + 无 screencap/input 设备调试技巧（fb0 alpha 分析/静态 tap 工具/触摸节点 gt9xx 可能 event0）；v0.27.11-open',
    '2026-09-08: JPEG UVC 实测证据入库 v0.27.10（CV201PND 板 1280x720 JPEG UVC 六步验证全通：探测/预览/拍照/录像/停止/回放；对比旧 AI 工具失败现场，绿屏/黑屏根因实锤）——①**绿屏直接原因=录像文件 0 字节**（取流断：get video frame timeout / rear camera fps 0.2 → VENC no stream → 0 字节 mp4 → 播放器解不出=绿屏），排查先 ls -la 看文件大小 ②**黑屏=取流/保活断**（REAR FPS≈0）；边录边看正常时 rear camera fps≈29 + venc fps≈25 ③**RecordingSettings.frame_rate 必须 15~60**（设 0 抛 frame rate must be betwen 15~60）④录像成功日志判据：MPP_EVENT_RECORD_DONE+done 路径/文件 12s 720p≈29MB/回放 media play ok（demux/vdec/vo/clock 全 success）；uvc-usb-camera.md 新增 §8 六步验证法表（每步成功日志判据），jpeg-decode-record.md 坑 7~10；v0.27.10-open',
    '2026-09-08: UVC 知识分层 v0.27.9（沛哥定规：V85X 平台 UVC/USB 摄像头统一按通用形态；通用 UVC 层沉淀为跨平台知识，可适配 T113/F133/Z20/Z21）——新增 knowledge/hardware/uvc-camera-generic.md（平台无关通用 UVC 层：前置条件 USB Host+uvcvideo / inotify 发现 / V4L2 格式协商 ENUM_FMT+S_FMT / 取流保活 / 状态机 / JPEG(MJPEG) 落地必查清单 / 平台绑定对照表 V85X 已收录、T113/F133/Z20/Z21 绑定层未实测不编造）；v85x/uvc-usb-camera.md 改「V85X 平台绑定实现」+ 检索导引分流（未指定平台→通用篇）；v85x/jpeg-decode-record.md 头部补通用篇引用；v0.27.9-open',
    '2026-09-08: UVC 摄像头知识去工程化 v0.27.8（沛哥定规：更新后不体现内部工程名，只保留通用 UVC 摄像头知识；外部 AI 落地 JPEG UVC 时出现录制绿屏/录制中黑屏，根因=格式协商缺失/录像尺寸错配/录像预览互斥顺序/保活缺失）——uvc-usb-camera.md 新增 §7 通用 JPEG(MJPEG) UVC 落地必查清单（①ENUM_FMT+S_FMT 锁 MJPEG，摄像头默认可能 YUYV，不协商=绿屏 ②RecordingSettings.size(REAR)=UVC 实际分辨率，不照抄 1080P/720P 档 ③开始录像不停预览/保活，切流/拔插/进回放前才 Recorder::stop+RearCamera::stop ④SharedVideoDevice(REAR) 保活录像期间不停 ⑤录像仅 mp4/ts，JPEG 仅照片场景 Snapshot→JpegViewer）；jpeg-decode-record.md 去除全部工程路径引用改职责描述；v0.27.8-open',
    '2026-09-08: PNG 生成管线规范显式化 v0.27.7（方案 A，沛哥定规：新 AI 客户端按规范转 png 仍默认锯齿，根因=抗锯齿只做在 gen_res 内部，规范没显式约束 AI 生成方式）——HTML_SUBSET 切图铁律新增 #8（PNG 生成只走三条路：html2json 自动转图 / generate_ui_assets / gen_res 公开函数，禁止 AI 自绘 1x 直画/外部生图直出小图交付）+ #9（防锯齿五要素：尺寸==position、≥4x 超采样 LANCZOS 或 α 羽化 sigma≈0.5、端点 round cap、圆角四角 alpha=0、check_all 校验）；generate_ui_assets 描述同步加 ⑦；v0.27.7-open',
    '2026-09-08: 全控件深度阅读 v0.27.6（沛哥要求：深度读基础 Demo 形成对 FlyThings 所有控件的深度理解）——basedemo-new_z20_1024_600 35 工程源码逐行精读（5 子代理并行，产出 130KB 原始笔记归档 workspace/references/demo-read-2026-09-08/）→ 新增 2 篇知识：①devflow/activity-code-skeleton.md（生成器骨架：activity 壳+#include logic/回调分发表语义 true=吞 false=默认（模板注释写反）/生命周期/定时器静态表+动态 register-unregister-reset/串口协议模板（UartContext 读线程 16KB 拼接+帧头对齐粘包处理+listener 订阅）/SysApp 三槽位（STATUSBAR/SCREENSAVER/IME）/多语言/平台编译宏）②uicontrols/widget-code-api.md（21 控件代码 API 速查：回调签名/触发时机/坑——自定义 ISeekBarChangeListener 三回调拿拖拽起止、ZKVideoView vs ZKMediaPlayer 两套消息枚举、camera 拍照四回调+jpg、pointer/clock 角度坐标系+浮点回绕坑、diagram setData/addData 双刷新、painter 绘图 API 全集、IME 集成范本、wifi/lte/softap/ethernet Manager+Listener、listview 删除漏 refresh 官方坑）；v0.27.6-open',
    '2026-09-08: Button 长按/循环重复机制收录 v0.27.5（沛哥确认学习：长按触发时间/循环重复时间通过 UI 属性表可配）——json 字段 longClickTimeOut（长按事件触发时间 ms，>0 启用，默认 -1 不启用）+ longClickIntervalTime（长按循环触发间隔 ms，>0 长按期间反复触发，-1 单次）；实测：ButtonDemo LongButton 1000/1000（1s 触发+1s 循环连发）、ImeDemo 删除键 600/-1（快启单次）；代码 ZKBase::ILongClickListener::onLongClick + setLongClickListener（onUI_init 注册/onUI_quit 注销，匿名 namespace）；新增 knowledge/uicontrols/button-fields.md（button 全字段频率表 + 长按三件套 + 图片按钮铁律）；v0.27.5-open',
    '2026-09-08: 控件层级检讨 v0.27.4（沛哥问“控件层级有检讨吗”——此前只有零散结论（Z序/window嵌套/pagewindow叠放/listview结构），缺系统矩阵）——扫描 86 json（SampleUI 1024x600 + basedemo-new_z20_1024_600）容器→子内容矩阵实证零越界：window 万能容器（可深嵌 window）；pagewindow/scrollwindow 只装 window；listview/radiogroup/slidewindow/diagram 只走结构键（item/radiobuttons/items/infos）禁止平铺控件键；叶子 14 类不得生子；数组子结构归属固定；新增 knowledge/uicontrols/json-layer-rules.md；check_all #2 升级层级合法性检查（_layer_problems：缺 window 子页/平铺/叶子生子/数组错位 4 类非法全拦截，86 真实 json 0 误报）；v0.27.4-open',
    '2026-09-08: json 字段全集显式化 v2.1（沛哥定规：字段缺省省略→引擎版本默认漂移→版本不匹配异常；以 SampleUI-New/ui/1024x600 每类型 100% 交集=必选，basedemo-new_z20_1024_600 交叉复验+补缺）——口径：beepEnable 不强制（废除恒带 true）/交互控件 touchable 显式 true（容器纯显示 false）/qrcode 恒写 padding 10/videoview 按 SampleUI/-1=0xFFFFFFFF 有意义非噪音；新增 knowledge/uicontrols/json-field-mandatory.md（21 类必写键全集表 + 子结构模板：listview.item 17 键含 position/subItem/diagram.infos 含 visible/slidewindow.items/radiobuttons）；⚠️ item.position 必写，行高公式 itemH=int(lv高/rows)-rowSpacing（basedemo 验证 164/4-5=36 等）；html2json 全部控件按全集输出+item 行高自动算；check_all #14 模板 v2.1（listitem 含 position + checkbox/radiogroup/radiobutton/imageanim 升级 + item/subItem/infos[]/items[]/radiobuttons[] 子结构检查）；v0.27.3-open',
    '2026-09-08: 补 MT Type-A 触摸注入工具 mt_test + 协议速判坑位（沛哥 V85X 实测 ui_test 单点协议在 gt9xx 注入坐标恒 0）——根因：设备 MODALIAS ra30,32,35,36,39=ABS_MT_*，不订阅单点 ABS_X/Y → 新增 bin_tools/{v85x,t113,z20,z21}/mt_test（ARMv7 musl 72KB + ARMv7 glibc 4.5MB，接口对齐 ui_test：tap/swipe/long/monkey/run；RISC-V 暂缓待 WSL）；bin_tools/README 加 mt_test 工具表行+「触摸协议速判」节（EVIOCGABS 能力位/getevent -p/试注入判据+协议用错→坐标恒0）；touch-inject-autotest.md 分列 ui_test(单点) vs mt_test(MT) 工具表+关键坑点破+协议铁律加 MT 序列+坐标恒0判据；v0.27.2-open',
    '2026-09-08: 补触摸注入/UI 自动化测试检索缺口（沛哥反馈：AI 调试没调用现成 input/ui_test 工具干活）——根因：references/kb/adb-input-autotest.md 最新版（含现成 input 工具说明）不在 MCP 索引范围，MCP 检索命中的 wiki 版是 8-31 老原理 → 新增 knowledge/devflow/touch-inject-autotest.md（首选 flythings_gen_ui_test + bin_tools/{平台}/ui_test 现成 ELF：tap/swipe/long/monkey/run + 部署命令；event.c 原理降为定制/移植参考；协议铁律 EV_SYN/逐像素/时间戳；判定闭环 logd>raw fb）；wiki/test/adb-input-autotest.md 同步 9-08 最新版消旧误导；v0.27.1-open',
    '2026-09-08: i18n 翻译推送工具入库（沛哥：V553 实测 fun launch 不推 i18n 盲点）——新增 flythings_i18n_to_json（.tr→.json 序列化与设备逐字节一致 + adb push /tmp/tr/；设备 DEBUG 实际加载 /tmp/tr/<lang>.json，生产固件 /res/ 用 push=False）；flythings_build_ui_flow 描述顶部加「fun launch 不推 i18n」警告；AI 改完翻译必须调本工具否则设备跑旧翻译；v0.27.0-open',
    '2026-09-08: BusyBox 调试工具库入库（沛哥：设备系统没 busybox/ifconfig 等工具，要预编译分发）——新增 bin_tools/{f133,f135,z20,z21,t113,v85x}/busybox（v1.36.1 全静态 ELF，网络工具 ifconfig/ip/ping/netstat/route/telnet/nc/wget 全开，adb push 即用，与 ui_test 同架构）；bin_tools/README 工具表+调用方法；新增 knowledge/devflow/busybox-debug-library.md 检索导引；v0.26.0-open',
    '2026-09-08: 部署/调试场景别名映射（沛哥反馈：客户端 AI 收「AI 应用调试全量推送」时检索不到 build_ui_flow 描述而自造 deploy_debug.sh）——flythings_build_ui_flow docstring 头部加「场景别名」段（编译/构建/调试/全量推送/部署/部署到设备/跑一下/AI 自定义编译/自主编译验证 一律本工具，禁止自创脚本路径）；新增 knowledge/devflow/deploy-scene-map.md（用户话语→唯一动作表 + 坑源说明）；v0.26.0-open',
    '2026-09-07: 自研帧动画知识移出 open 版（沛哥指示：ImageAnimView/FrameImageView ZKBIN+QOI+region 机制依赖自研 ZKBIN 工具链，open 用户缺工具无法使用）——删除 knowledge/devflow/frame-image-anim-bin.md，知识保留本地 references/kb/frame-image-anim-bin.md（125 行完整原版）；dashboard-can-arch.md 还原 v0.22.1 无 ImageAnimView 版（6 处引用全清，CAN 架构保留）；v0.25.2-open',
    '2026-09-07: 清理冗余（沛哥要求整理 open 版多余反复内容）——删除 knowledge/ 与 wiki 字节完全相同的 3 个重复副本（esl/tag-esl.md、uicontrols/image-path-rule.md、uicontrols/scrollwindow-layout.md），wiki 保留唯一一份，检索不再双份命中；layout-audit.md 两版非字节相同（knowledge 含实测校准 edittext id 51000/imageanim 无 frameInterval）保留 knowledge 版；wiki 官方源自身重复不动；v0.25.1-open',
    '2026-09-07: 冷门控件字段文档批量入库（git.com 全库学习产出，沛哥确认 3 点：listview 点击 id=被点 subitem 的 ID / slidewindow cols×rows=每页格数 11 项=1页8+3 翻页 / 所有控件支持跨线程操作）——新增 uicontrols 文档 11 篇：pointer（双坐标定圆心+animatable 自动动画）、circlebar（有效图扇形裁剪+触摸监听）、digitalclock（纯属性+TimeHelper 改系统时间）、slidetext（输入法候选词条）、qrcode（loadQRCode 传 JSON）、radiogroup-checkbox（pic2 选中图+子项 ID 宏）、diagram（统一 SZKPoint+setData/addData 双模式）、videoview（轮播 loopPlayback 读 UI名_video_list.txt / API 双模式）、pagewindow（多页容器）、listview（三回调+无 subitem 数量限制）、cross-thread-ui-rule；全部 fui unpack 实测 + f133 easyui 2.9.0 SDK 头文件校准，非猜测；v0.25.0-open',
    '2026-09-01: SlideWindow 布局定规修正（沛哥 21:59 纠正）——json 坐标来自 HTML 原型绝对定位，确认好即无需微调；若交付后还要调位置 = 前期 HTML 效果没确认好（正确流程：HTML → 预览确认 → 才 pack/交付）；删掉 v0.7.8 错误的「绝对布局需微调」表述',
    '早期迭代（0.27.10 之前，完整史见 CHANGELOG.md）：基础控件字段/代码 API 全覆盖（uicontrols 22 篇：button/listview/window/slidewindow/pagewindow/cameraview/videoview/circlebar/diagram/edittext 等，字段全集显式化+层级规则）；devflow 工程机制（package.properties/EasyUI.cfg rotateScreen、自定义字库/控件、i18n 多语言工具链、原型流程、自动化测试 touch-inject/ui_test）；RAG 检索基建（bge-small-zh 本地向量+BM25 混合、检索边界定规、去工程化）',
    '平台知识分层：通用层（hardware/uvc-camera-generic 跨平台 UVC、usb-otg-switch 跨平台 OTG）与平台绑定层分离；V85X 深度知识（aw-dvr 版本兼容、VO/disp 层调试、UVC JPEG 链路）仅内部版；方案类（车载/涂鸦/SIP/ESL）仅内部版',

]


def flythings_get_version() -> str:
    """返回 MCP 版本号、工具数量与关键特性。用户问「MCP 版本是多少 / 是不是最新的」时调用。
    """
    import inspect as _i
    tools = [n for n, _ in _i.getmembers(sys.modules[__name__], _i.isfunction)
             if n.startswith('flythings_')]
    return json.dumps({
        'mcpName': 'flythings-kb-open',
        'version': MCP_VERSION,
        'build': MCP_BUILD,
        'toolCount': len(tools),
        'tools': sorted(tools),
        'features': MCP_FEATURES,
        'checkHint': '在 AI 工具中问 AI：MCP 版本是多少？返回 version 与 0.3.0 比对即可确认是否最新',
    }, ensure_ascii=False)


def flythings_search(query: str, k: int = 3) -> str:
    """在 FlyThings 知识库（wiki 118 篇文档）中检索相关文档片段（完全本地，零 Key）。
    遇到 FlyThings 开发问题（控件/API/布局/FTU/回调/编译/平台差异等）时调用。query 用中文描述。
    内置 bge-small-zh 本地模型做向量检索，模型不可用时自动降级 BM25 关键词检索。"""
    kk = max(1, min(int(k), 8))
    try:
        top = rs.search(query, kk)
        if not top:
            return "no results found"
        parts = []
        for s, c in top:
            parts.append(f"===== {c['path']} (similarity {s:.3f}) =====\n{c['text']}")
        return '\n\n'.join(parts)
    except Exception as e:
        return f"search error: {e}"


def flythings_read_json(json_path: str) -> str:
    """解析 .json 布局文件为 JSON（分辨率、控件列表、caption→id 映射）。传入 json 完整路径。
    ⚠️ 传入 .ftu 时返回错误提示：ftu 为加密文件无法解析，可提供设计文件 / AI 重新设计界面 / 采用 HTML 布局。
    （flythings_read_ftu 已移除——无 unpack 能力时它只是 read_json 的包装）"""
    return json.dumps(pt.flythings_read_json(json_path), ensure_ascii=False)


def flythings_get_project_spec() -> str:
    """返回 FlyThings 项目结构化规范（目录规则、生成规则、注意事项）。编写/修改项目代码前调用。"""
    return json.dumps(pt.flythings_get_project_spec(), ensure_ascii=False)


def flythings_validate_project(project_root: str) -> str:
    """检查项目是否符合 FlyThings 规范，返回 errors/warnings。生成代码后调用。
    空白项目判定：工作目录 ui/ 下无 .ftu 即视为空白（无需再去读 json），返回
    isEmptyProject=true；此时直接询问用户平台（F133/F135/Z21）与分辨率后调用
    create_project，禁止去其他目录检索 json/ftu。
    ⚠️ 若 projectInfo.platform/resolution 为 null，必须先向用户询问，禁止猜测。
    """
    return json.dumps(pt.flythings_validate_project(project_root), ensure_ascii=False)


def flythings_fui_pack(json_path: str) -> str:
    """将 json 布局打包为 ftu（设备实际加载的是 ftu）。返回 ftu 路径、控件数、分辨率。"""
    return json.dumps(pt.flythings_fui_pack(json_path), ensure_ascii=False)




def flythings_edit_ftu(ftu_path: str, operations: str, output_ftu: str = '') -> str:
    """编辑 ftu 布局：自动应用编辑到 json 后 pack 回 ftu（默认覆盖原文件，或 output_ftu 指定新文件）。
    operations 为 JSON 数组字符串，支持：
    set      {"op":"set","target":"caption或key","props":{"x":100,"y":200,"text":"新文本"}}
    remove   {"op":"remove","target":"caption或key"}
    add      {"op":"add","template":"caption或key","newKey":"textview__4","props":{...}}
    set_root {"op":"set_root","props":{"backgroundColor":"#FFFFFF"}}
    客户说「把这个按钮往右移/改文本/换颜色/删掉某控件/复制一个控件」时调用。
    布局修改以 ftu 为目标（json 为内部中间文件自动处理）；改界面布局也可直接编辑 HTML 原型后重新转换。
    ⚠️ 布局以 json 为源：优先直接编辑同目录已有 json 再 pack 回 ftu；无 json 时报错。"""
    return json.dumps(pt.flythings_edit_ftu(ftu_path, operations, output_ftu), ensure_ascii=False)


def flythings_build_ui_flow(project_root: str, with_launch: bool = True, device: str = '') -> str:
    """⚠️ 场景别名（编译部署类意图一律本工具，禁止自造命令；不限触发入口）：
    ① 用户口语：「编译/构建/调试/全量推送/部署/部署到设备/推送到设备/跑一下/运行到真机」；
    ② 自定义功能/自动化流程触发：客户端「AI 应用调试」「自定义编译」等按钮/动作，凡意图是「把项目编译并部署到真机调试」→ 一律调本工具；
    ③ AI 自主决策：写完/改完代码后主动编译验证、调试看效果，同样调本工具。
    内部 fun launch 完成程序+资源+ftu 全量推送并启动；⚠️ 不存在 tools/deploy_debug.sh 之类的额外部署脚本，禁止 AI 自创脚本/命令路径。
    UI 构建流程：① json/ftu 时间戳一致性检查（以 json 为源，改过 json 自动重新 pack）
    ② fui pack ③ fun install 同步依赖 ④ fun build ⑤ build 通过后直接 fun launch 推送启动（with_launch=False 可跳过）。
    ⚠️ fun launch 网络推送失败/超时会**自动重试 5 次**（间隔 2s，覆盖网络抖动；信任 fun 差分推送，不自写 push 脚本校验）；
    5 次仍失败（无 adb 设备/网络中断）时返回 needDeviceInput=true，必须询问用户接入方式：
    1) USB 接入：设备 USB 连电脑，确认 adb devices 可见后重试；2) 网络接入：
    先在电脑执行 adb connect <设备IP> 完成配对再重试。
    ⚠️ fun launch 不支持 -s 参数（带参数有其他问题），设备选择由 fun 自动完成，禁止替用户猜测 IP。
    传入项目根目录。改过 json 必须 pack，否则设备仍跑旧 ftu。
    ⚠️⚠️ src/activity/ 目录（mainActivity.cpp/h）由 IDE 编译时自动生成，构建流程已自动处理；
    禁止手动创建/修改该目录文件，业务代码只写 src/logic/*.cc。
    """
    return json.dumps(pt.flythings_build_ui_flow(project_root, with_launch, device), ensure_ascii=False)


def flythings_generate_ui_preview(project_root: str, output_dir: str = '') -> str:
    """将项目 ui/*.json 生成 HTML 预览页（客户确认 UI 用，每个 json 生成同名 .preview.html）。
    ⚠️ 流程约束：HTML 布局出来后必须先本工具出预览给用户确认（只交付 .preview.html 文件，
    不生成图片/截图），确认 OK 后才允许 fui pack / 写逻辑 / 交付（未确认禁止开工）。
    无 UI 设计稿时：先建 json 布局 → 预览确认 → pack。
    """
    r = j2h.json2html(project_root, output_dir)
    if isinstance(r, dict) and r.get('success'):
        for f in r.get('files', []):
            jp = os.path.join(project_root, 'ui', f.get('json', ''))
            if os.path.isfile(jp):
                try:
                    with open(jp, encoding='utf-8-sig') as fh:
                        data = json.load(fh)
                    f['controls'] = sum(1 for k, v in data.items()
                                         if isinstance(v, dict) and '__' in k)
                except Exception:
                    pass
        r['projectRoot'] = project_root
        r['outputDir'] = output_dir or os.path.join(project_root, 'ui')
        r['note'] = 'html 为客户预览稿；设备端仍用 fui pack 生成的 ftu，两者同源于 json'
    return json.dumps(r, ensure_ascii=False)


def flythings_html_to_json(input_html: str, output_json: str = '', res: str = '') -> str:
    """受限 HTML 交互原型 → ui/*.json 布局。

    ⚠️ 规范内嵌（HTML_SUBSET，无需另找文档）：
    - 结构：<div class="screen" data-res="WxH" data-bg="#RRGGBB"> 为根（也可用 data-width/data-height 或 style 宽高替代 data-res；
      data-background 与 data-bg 互为别名；缺省分辨率 480x272，建议显式传 res 参数或写 data-res）。
    - 控件映射：div.text/p/span→textview；div.btn/button→button；div.input/input→edittext；
      div.bar/seekbar→seekbar；div.card/window/panel→window 容器（子控件相对坐标）；div.modal/dialog→弹窗（modal+隐藏）；
      div.list/listview→listview（子项见下）；div.checkbox→checkbox；div.radio/radiogroup→radiogroup；div.icon/img→图标 textview。
    - 🎯 图标优先（沛哥 2026-09-03 定规，生成 UI 时必守）：常用操作（返回/播放/暂停/上一首/下一首/设置/搜索/删除/
      刷新/确认/关闭/加减/音量/主页/菜单等）必须用图标表达，禁止用「按钮+文字」糊弄！写法：
      ① 图标按钮 <div class="btn" data-icon="play" data-x.. data-y.. data-w.. data-h.. data-caption="BtnPlay">
      ② 纯展示图标 <div class="icon" data-icon="wifi" ...>（或 <i class="iconfont icon-volume">，等价识别）
      转换器自动生成 iconfont 风格矢量线框 PNG：图标按钮自动 normal+pressed 两态 picTab，纯图标自动 backgroundPic；
      data-color 可配线框颜色（#RRGGBB，缺省浅灰蓝）；控件建议正方形；未收录图标名给 warning。
      46 个内置图标词表见 HTML_SUBSET（back/forward/up/down/close/check/plus/minus/menu/more/search/home/list/
      play/pause/stop/prev/next/power/volume/mute/delete/edit/share/download/upload/user/lock/info/warning/camera/
      clock/calendar/bell/mic/location/mail/eye/video/phone/settings/refresh/wifi/bluetooth/heart/star，中文别名
      如 data-icon="播放"/"返回" 也认）；需要自备图时仍用 data-pic。
    - 定位：data-x/data-y/data-w/data-h（或 data-left/top/width/height、style left/top/width/height）。
    - 字号：data-fs / data-font-size / data-fontSize / 内联 style="font-size:NNpx" 都认。
    - 颜色：data-color 文字色、data-bg 或 data-background 背景色（textview/button/edittext 均支持背景）。
    - 命名：data-caption 指定控件名（C 标识符）；缺省自动 TextView1/Button1...。
    - listview 子项：子控件直接写在 list 容器内即生成 subItem；若用 <div class="item"> 包裹，
      转换器会展开包裹层、逐个生成 subItem（不会吞掉内部控件）。
    - 铁律：Z 序=书写顺序（弹窗最后）；文本只用汉字+ASCII+基础符号（/ % # - _ 空格），禁 emoji；
      进度条用 div.bar；输入框用 div.input（系统键盘）；颜色一律 #RRGGBB 6 位。
    - ⚠️ CSS 效果不硬转：HTML 原型允许任意效果（emoji/iconfont/CSS 渐变阴影圆角/粒子/3D 动效），
      但 FlyThings 无 CSS 引擎，转 json 时效果一律转图片 + 控件组合实现：
      渐变/复杂背景/阴影/描边 → 切 PNG 或 .9.png 用 data-pic 引用；emoji/iconfont → 转 PNG 图标；
      loading/旋转/粒子动效 → 序列帧 PNG 或 GIF（imageanim 动图控件，循环次数 ≤0 无限循环）；
      按钮两态 normal+pressed（_p 后缀）→ picTab{pic0,pic1}。
      ⚠️ 图片一律由转换器自动转图（内置抗锯齿管线），**禁止 AI 自绘 1x 直画 png 或用外部生图能力直出小图交付**
      （1x 二值 alpha / 大图缩小边缘必锯齿；防锯齿铁律见 HTML_SUBSET「切图 / 图片资源铁律」#8 #9）。
      转换器对 style 中的效果属性（linear-gradient/box-shadow/border-radius/animation 等）
      自动输出 warning 提示转图，不会硬转。
    - ✅ JS 交互设计（2026-08-29 沛哥建议）：第一套 HTML 效果稿建议直接写 JS 交互——
      点击弹窗/页面切换/tab 切换/列表滚动/数据模拟/动效触发等，让客户在浏览器里直接"点得动"，
      前期效果确认和修改效率翻倍。转换器自动忽略 <script> 标签和 onclick 等交互属性（实测验证），
      JS 只服务于浏览器预览确认，不转 json；FlyThings 端交互逻辑由 logic.cc 实现（json 布局 + 回调）。
    - ✅ CSS 效果自动转图（2026-08-29 沛哥要求 + 2026-09-01 路径修复）：style 里出现 linear-gradient/box-shadow/border-radius/
      animation 等效果时自动生成图片资源（不再只 warning）——渐变→grad_*.png（backgroundPic）、
      阴影+圆角→shadow_*/gradshadow_*.png（渐变阴影自动合成）、emoji 文本→emoji_*.png 图标、
      class=loading/spinner 或 animation:spin→loading_*.gif（12 帧）+ imageanim 控件（warning 提示
      logic.cc 里 mXXXPtr->play()）。图片自动输出到 <项目>/resources/images/（output_json 在 <项目>/ui/ 下时自动识别；
      json 引用路径 images/xxx.png 相对 resources 目录，与设备加载一致；非 ui/ 目录结构回退 json 同目录 images/ 并警告）。
      返回 generatedAssets 计数 + assetDir 实际输出目录。

    ⚠️ 客户发说明书/参考照片/需求文档时不能直接转 json：先按 skill §7.0 引导分析
    提炼 UI 需求清单 → 用户确认 → 再写受限 HTML → 才调本工具。
    ⚠️ 转换后必须先 json2html/generate_ui_preview 出预览稿给用户确认（只交付 .preview.html
    文件本身，不生成图片/截图），确认 OK 后才允许 fui pack / 写逻辑 / 交付（未确认禁止开工）。
    output_json 缺省为 html 同名 .json；res 可覆盖分辨率（如 "800x480"）。
    """
    return json.dumps(h2j.html2json(input_html, output_json or None, res or None), ensure_ascii=False)


def flythings_json_to_html(target: str, output_dir: str = '') -> str:
    """json 布局 → HTML 预览稿（客户确认 UI 用，只交付 .preview.html 文件本身，不生成图片/截图）。
    target 为项目根目录（全部 ui/*.json）或单个 json 文件路径。
    ⚠️ HTML 布局出来后必须先调本工具出预览稿给用户确认，确认后才开工（pack/写逻辑）。
    """
    return json.dumps(j2h.json2html(target, output_dir), ensure_ascii=False)


def flythings_list_packages(platform: str = '') -> str:
    """列出依赖包生态（platform 如 F133/Z20，留空列全部），含功能描述与版本。写代码前调用。"""
    return json.dumps(pkgtools.flythings_list_packages(platform or None), ensure_ascii=False)


def flythings_query_package(package: str, platform: str = 'F133') -> str:
    """查询依赖包在指定平台的可用版本。传入包名（如 mqtt-cxx）与平台。"""
    return json.dumps(pkgtools.flythings_query_package(package, platform), ensure_ascii=False)


def flythings_recommend_manifest(features: str, platform: str = 'F133') -> str:
    """按功能需求推荐 Manifest.xml 依赖配置。features 为逗号分隔关键词，如 'mqtt,json,蓝牙'。"""
    flist = [f.strip() for f in str(features).split(',') if f.strip()]
    return json.dumps(pkgtools.flythings_recommend_manifest(flist, platform), ensure_ascii=False)
def flythings_add_package(project_root: str, package: str, version: str = '',
                          platform: str = '', with_install: bool = True) -> str:
    """把 package 添加进项目 Manifest.xml 并执行 fun install 拉取依赖（添加包闭环流程）。

    - 版本解析顺序：本地 registry → 离线 catalog → 在线（semver 取最新，不依赖包实体是否存在）
    - 已声明同包则更新版本；未声明则追加 <package id version/>；保留原 Manifest 格式
    - with_install=True（默认）执行 fun install 同步依赖（Manifest 变更后自动拉取）
    用户说「给项目加个 XXX 包 / 项目要用 MQTT/JSON/蓝牙需要加依赖」时调用。
    """
    return json.dumps(pkgtools.flythings_add_package(project_root, package,
                                                     version or None,
                                                     platform or None,
                                                     with_install), ensure_ascii=False)




def flythings_search_package(keyword: str, platform: str = 'F133') -> str:
    """按功能关键词搜索可用 package（mqtt/json/http/ssl/ble/ota/audio 等）。"""
    return json.dumps(pkgtools.flythings_search_package(keyword, platform), ensure_ascii=False)


def flythings_get_package_api(package_id: str, platform: str = 'F133', version: str = '') -> str:
    """获取 package 的头文件路径、类方法签名、使用示例。传入包名与可选版本。"""
    return json.dumps(pkgtools.flythings_get_package_api(package_id, platform, version or None), ensure_ascii=False)


def flythings_resolve_dependencies(packages: str, platform: str = 'F133') -> str:
    """递归解析 package 依赖树并检测冲突。packages 为 JSON 数组字符串，
    如 '[{"id":"mqtt-cxx","version":"3.2.0"}]'。返回依赖树、解析结果与冲突建议。
    """
    return json.dumps(pkgtools.flythings_resolve_dependencies(packages, platform), ensure_ascii=False)


def flythings_generate_manifest(features: str, platform: str = 'F133') -> str:
    """按功能需求生成完整 Manifest.xml（依赖递归补齐）。features 为逗号分隔关键词，
    如 'mqtt,json,http_download,ssl_mqtt'。
    """
    flist = [f.strip() for f in str(features).split(',') if f.strip()]
    return json.dumps(pkgtools.flythings_generate_manifest(flist, platform), ensure_ascii=False)


def flythings_create_bin_project(project_root: str, project_name: str = '', platform: str = 'z21',
                                 app_version: str = '1.0.0', description: str = '',
                                 with_build: bool = True) -> str:
    """创建「可执行程序」项目（fun create --type bin）并编译为直接可运行的 ELF 二进制。

    - 项目类型 4 选 1：zkgui（UI应用）/ bin（可执行程序）/ staticLibrary / sharedLibrary
    - bin 项目结构极简：fun.json（"type": "executable"）+ src/main.cpp（标准 int main()）
    - 编译：fun build → 产物 .fun/{platform}/{项目名}，ELF 魔数验证
    - 部署：adb push + chmod +x 直接跑（无 zkgui 宿主，不能启动 UI 应用）
    - 非交互：自动传 --app-version/--description 跳过向导；目录非空直接报错（防覆盖询问卡死）

    用户要「编译出可直接执行的二进制/bin 程序/执行程序（非 UI 应用）」时调用。
    platform 默认 z21（支持 z20/t113/f133 等）；project_name 缺省取目录名。
    """
    return json.dumps(pt.flythings_create_bin_project(
        project_root, project_name, platform, app_version, description, with_build),
        ensure_ascii=False)


def flythings_gen_ui_test(project_root: str, test_type: str = 'ask', output_dir: str = '',
                          platform: str = 'z21', with_build: bool = True,
                          monkey_count: int = 500) -> str:
    """根据 UI json 布局生成自动化测试项目（纯代码，不依赖 AI，省 token）。

    ui/*.json 已含全部控件坐标（position left/top/width/height）与可交互信息
    （touchable/visible），直接解析生成可编译的 bin 测试项目：
      ask      - 询问用户三种验收方式（默认，返回选项让用户选）
      traverse - 遍历控件验收：所有可交互控件逐个点击+滑动 + 图片资源缺失检查 + logcat 配合
      monkey   - 压测 MonkeyTest：随机 tap/swipe 指定次数，发现潜在隐患
      custom   - 自定义验收：按用户输入要求生成（差异化逻辑走 AI，此模式仅返回提示）

    用户提出「自动化测试 / 验收 / 遍历控件 / 压测 / Monkey」等需求时调用；
    默认先问用户选哪种验收方式，避免 AI 参与重复生成（省 token）。
    """
    return json.dumps(tt.flythings_gen_ui_test(
        project_root, test_type, output_dir, platform, with_build, monkey_count),
        ensure_ascii=False)


def flythings_attach_cli_tools(project_root: str, with_fyx: bool = True) -> str:
    """复制 fui.exe（→项目 ui/）与 fun.exe（→项目根目录）到项目，随项目交付。
    生成后用 fun.exe build 编译、launch 推送，无需客户导入 IDE。
    ⚠️⚠️ src/activity/ 目录（mainActivity.cpp/h）由 IDE 编译时自动生成，禁止创建/修改；
    业务代码只写 src/logic/*.cc。
    """
    return json.dumps(pt.flythings_attach_cli_tools(project_root, with_fyx), ensure_ascii=False)


def flythings_create_project(project_root: str, platform: str, resolution: str,
                             app_name: str = '', with_cli: bool = True, force: bool = False) -> str:
    """从 HelloWord Demo 复制骨架创建 FlyThings 项目，自动替换工程名/分辨率/平台。
    传入目标项目根目录、平台（F133/F135/Z21）与分辨率（如 800x480）。
    ⚠️ platform/resolution 必填且必须来自用户明确提供，未指定时先询问，禁止猜测或用默认值。
    ⚠️⚠️ src/activity/ 目录（mainActivity.cpp/h）由 IDE 编译时根据 ftu 自动生成，
    禁止创建/修改/覆盖该目录任何文件！业务代码只能写 src/logic/*.cc；
    mXXXPtr 控件指针 / ID_MAIN_* 宏 / 回调表 / findControlByID 初始化全部由 IDE 自动生成，禁止手写。
    """
    return json.dumps(pt.flythings_create_project(project_root, platform, resolution,
                                                  app_name, with_cli, force), ensure_ascii=False)


def flythings_check_project_deps(project_root: str, platform: str = 'F133') -> str:
    """扫描项目 include 的三方库与 Manifest 声明对比，返回缺失依赖。
    需要三方能力（MQTT/HTTP/JSON/蓝牙/SSL 等）时先调用。
    """
    return json.dumps(pkgtools.flythings_check_project_deps(project_root, platform), ensure_ascii=False)


def flythings_generate_ui_assets(project_root: str, assets: str) -> str:
    """生成 UI 图片资源（图标/牌面/按钮背景等），输出到 <项目>/resources/images/。

    ⚠️ 三级降级策略（任何环境都能出图）：
      ① AI 生图（配置了 OPENAI_API_KEY 且网络可达 → gpt-image-2 透明底，最精致）
      ② 本地 emoji 渲染（Windows seguiemj.ttf / Linux NotoColorEmoji → 卡通风，羊了个羊同款）
      ③ 线条/几何兜底（Pillow 画圆/方/星/心/对勾等 → 无 AI 无 emoji 字体也能出）
    最终用户（客户）没有 AI 能力时自动降级，无需任何外部依赖。

    ⚠️ 图片资源铁律（2026-08-29 羊了个羊实战，务必遵守）：
      ① 图片尺寸必须与 json 控件尺寸一致（瓦片 76×76 控件 → 76×76 图；槽位 72×72 → 72×72 图），
         不要生成大图让控件缩放，也不要小图拉伸。
      ② 圆角卡片图四角必须真透明（alpha=0）：渐变/填充底是整矩形画的，圆角只是描边轮廓，
         必须用圆角 mask 裁剪（putalpha）清掉弧线外角落；阴影模糊（GaussianBlur）会溢出到弧线外，
         最后整体再裁一次圆角清掉残影。
         通用函数 gen_res.rounded_card()（渐变+圆角+描边+高光）已内置裁剪；
         gen_res.gen_gradient(..., radius=r) 也已修复（radius>0 自动裁圆角）。
      ③ 用透明角图片的按钮不要设 bgColorTab：透明角会透出按钮底色而不是窗口背景，
         需要透背景的图片按钮（瓦片/槽位/图标钮）不放 bgColorTab；纯文字按钮才用底色。
      ④ 功能按钮尽量用图片按钮：picTab{pic0: normal, pic1: pressed(_p 后缀)} 两态图。
      ⑤ 生成后必须检查四角 alpha：img.getpixel((2,2))[3] == 0 才算合格。
      ⑥ 路径规范（2026-09-01 沛哥要求）：自动生成的图片一律放 <项目>/resources/images/，
         json 布局引用路径写 images/xxx.png（相对 resources 目录，与设备/ftu 加载一致）；
         返回的 path 字段就是 images/xxx.png，直接填 json 的 backgroundPic / picTab.pic0 / picTab.pic1，
         不要写绝对路径，也不要带 resources/ 前缀。
      ⑦ PNG 生成管线铁律（2026-09-08 沛哥定规，方案 A 显式化）：AI/客户端需要图片时
         禁止自写绘制代码 1x 直画、禁止用外部生图能力直出小图交付（1x 二值 alpha 无抗锯齿、
         大图缩小边缘必锯齿）；**只走三条路**——CSS 效果交 html2json 自动转图（内置抗锯齿）/ 本工具生成 /
         gen_res 公开函数（rounded_card / gen_gradient / gen_shadow_card / emoji_icon_ss /
         glyph_icon_ex / line_icon / frames_loading_gif，全部内置抗锯齿）。
         PNG 防锯齿五要素：尺寸 == 控件 position / ≥4x 超采样 + LANCZOS 缩回或 α 羽化（sigma≈0.5）/ 端点 round cap /
         圆角四角 alpha=0 / 生成后跑 check_all 校验（#11 图片尺寸 + 四角 alpha）。
         完整规范见 HTML_SUBSET.md「切图 / 图片资源铁律」#8 #9。

    assets 为 JSON 数组字符串，每项：
      {"name": "icon_ok.png", "size": 128,
       "prompt": "cute white cartoon sheep, game icon",   ← 有则优先 AI 生图
       "emoji": "🐑",                                      ← AI 失败后用它
       "color": "#42C9FF" 或 [r,g,b,a], "kind": "check"} ← 线条兜底参数
    kind 可选：check/charging/wifi/alert/circle/square/star/heart。
    name 必填（自动补 .png）；返回每项实际生成方式（method: ai/emoji/line）。
    """
    return json.dumps(h2j_genres.gen_ui_assets(project_root, assets), ensure_ascii=False)


def flythings_i18n_scan(project_root: str) -> str:
    """诊断项目多语言（i18n）现状：i18n/*.tr 语言文件、key 对齐、布局 @key 引用完整性。
    项目做多语言时先调用；返回 JSON：languages/keysPerLanguage/缺失 key/引用缺失。
    多语言机制：翻译文件 i18n/<语言>.tr（文件名三段式 xx_XX-语言名，Android strings.xml 同款），
    布局 text 写 @key，代码 setTextTr("key") 或 LANGUAGEMANAGER->getValue("key")。"""
    return json.dumps(itx.flythings_i18n_scan(project_root), ensure_ascii=False)


def flythings_i18n_add_language(project_root: str, lang: str, lang_name: str, base_lang: str = 'zh_CN', context: str = '') -> str:
    """添加新语言：从基础语言（缺省 zh_CN）复制 key 骨架，生成 i18n/<lang>-<lang_name>.tr 待翻译文件。
    lang 为语言代码（如 fr_FR），lang_name 为语言名（如 法语，显示在切换列表）。
    返回待翻译清单（key→基础语言原文）+ 专业翻译提示（结合项目语境，如车载项目 CAN BUS 不译公共汽车）；
    翻译后调用 flythings_i18n_import 写回。"""
    return json.dumps(itx.flythings_i18n_add_language(project_root, lang, lang_name, base_lang, context), ensure_ascii=False)


def flythings_i18n_export(project_root: str, lang: str = 'zh_CN', keys: str = '', context: str = '') -> str:
    """导出指定语言（缺省 zh_CN）的 key→文本清单（JSON），供翻译后 import 写回。
    keys 可选：逗号分隔的 key 子集；缺省导出全部。context 可选：项目语境描述，
    返回 translationGuide 提示 AI 专业翻译（术语如 CAN BUS 保持行业译法）。"""
    return json.dumps(itx.flythings_i18n_export(project_root, lang, keys, context), ensure_ascii=False)


def flythings_i18n_import(project_root: str, lang: str, translations: str, merge: bool = True) -> str:
    """将翻译结果写回项目 i18n/<lang>.tr（生成新语言文件或更新已有）。
    translations 为 JSON 对象 {"key": "翻译文本"}；merge=True 与已有内容合并，False 整体覆盖。"""
    return json.dumps(itx.flythings_i18n_import(project_root, lang, translations, merge), ensure_ascii=False)


def flythings_i18n_refactor(project_root: str, lang: str = 'zh_CN', dry_run: bool = True) -> str:
    """把布局 json 里写死的非空文本控件替换为 @key 引用（多语言改造辅助）。
    dry_run=True 只预览不改文件；False 执行替换并写入指定语言 .tr。
    纯数字/时间占位文本自动跳过。"""
    return json.dumps(itx.flythings_i18n_refactor(project_root, lang, dry_run), ensure_ascii=False)


def flythings_i18n_to_json(project_root: str, langs: str = '', push: bool = True, device: str = '') -> str:
    """把 i18n/*.tr 转为 i18n/*.json（设备 zkgui 实际加载格式），并可推送到设备 /tmp/tr/。

    ⚠️ **fun launch 不推 i18n**（只推 ftu/images/font/lib/cfg）—— 改完翻译后必须显式调本工具，
    否则设备仍跑旧翻译（logcat 刷 'not found value' 警告）。本工具生成 json 与设备端逐字节一致
    （tab 缩进+无空格冒号+末尾无换行），默认自动 adb push 到 /tmp/tr/；多设备需传 device=IP。
    生产固件翻译打包到 /res/，无需推送（push=False）。

    完整流程：flythings_i18n_import / add_language / refactor 改 .tr → 本工具转 json + push →
    adb shell "setprop ctl.stop zkswe && setprop ctl.start zkswe"（DEBUG 模式重启加载）。
    """
    return json.dumps(itx.flythings_i18n_to_json(project_root, langs, push, device), ensure_ascii=False)


# 注册辅助：把上面全部工具注册到任意 FastMCP 实例
def flythings_ui_editor(project_root: str, output_dir: str = '') -> str:
    """把 ui/*.json 生成「可视化编辑器」网页：拖控件就改布局，不用嘴描述"往左一点"。

    ⚠️ 定位（UI 微调闭环第二步）：① AI 生成/改 json 布局 → ② 本工具出编辑器给用户拖 →
    ③ 用户点「复制变更 JSON」→ ④ flythings_ui_edit_apply 写回 json + pack ftu。
    预览与设备同源（都来自 json），改完即所得。

    输出：每个 json → <项目>/ui/_edit/<name>.edit.html（ui 目录递归扫描），单文件 HTML
    （图片 base64 内联，含 audio/xxx.png 这类带子目录的相对 resources 引用），双击即用。

    页面能力：
    - 点选 / 拖动 / 8 手柄缩放；方向键 1px（Shift 10px）；网格吸附 1/2/5/10
    - Alt+点 = 穿透选中下层控件（专治全屏透明 button 压住其它控件）
    - 选中框左上 ✥ 绿块可拖 = 被遮罩压住的控件也能拖
    - 控件列表可搜 key / caption；「显示隐藏」把 visible:false 的弹窗显示成虚线幽灵框
    - 属性栏列出该控件全部字段：text（多行）/ fontSize / colorTab.color0（颜色拾取器）/
      backgroundPic / picTab.pic0~pic4（正常/按下/选中/选中按下/无效）/ visible / touchable…
      改完画布即时生效；id 只读（IDE 生成）
    - 预检红黄标：图片尺寸≠控件尺寸（红=图比控件大会被裁切；黄=大控件配小图）、文本明显超框
    - 深链接 <name>.edit.html#button__2 打开即选中该控件

    output_dir 缺省 <项目>/ui/_edit
    """
    if uied is None:
        return json.dumps({'success': False, 'error': 'ui_editor 不可用（缺 ui_tools/ui_editor.py 或 Pillow）'},
                          ensure_ascii=False)
    try:
        r = uied.make_editor(project_root, output_dir)
    except Exception as e:
        return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    if isinstance(r, dict) and r.get('success'):
        r['projectRoot'] = project_root
        r['note'] = ('在浏览器打开 *.edit.html 拖动/改属性；改完点「复制变更 JSON」或「下载变更 JSON」，'
                     '把内容交给 flythings_ui_edit_apply 写回 json 并 pack ftu')
        for f in r.get('files', []):
            if f.get('html'):
                f['open'] = f['html']
    return json.dumps(r, ensure_ascii=False)


def flythings_ui_edit_apply(project_root: str, changes: str, pack: bool = True) -> str:
    """把 ui_editor 导出的「变更 JSON」写回 ui/*.json，默认接着 pack 成 ftu。

    changes：可直接传 JSON 文本（用户从编辑器复制过来的），也可传文件路径。
    结构：
        {"file": "main.json", "resolution": "1600x600",
         "changes": {"button__1": {"left": 130, "top": 60, "width": 150, "height": 54}},
         "props":   {"textview__4": {"text": "新文字", "fontSize": 22,
                                     "colorTab": {"color0": 16711680}}}}
    控件路径：顶层 "button__1"；嵌套 window 内 "window__2/button__3"。
    changes = 几何（position 四项）；props = 其它属性（深合并写回）；两者都可省。

    安全：① 写回前自动备份 <name>.json.bak；② 格式一致性自检（原文件必须能被
    json.dumps(indent=2, ensure_ascii=False) 无损还原，否则拒绝写入以免整文件重排）；
    ③ 坐标取整 + 不越出屏幕。pack=True 时调 fui pack 生成同名 ftu。
    """
    if uia is None:
        return json.dumps({'success': False, 'error': 'ui_edit_apply 不可用'}, ensure_ascii=False)
    text = (changes or '').strip()
    tmp = ''
    try:
        if not text:
            return json.dumps({'success': False, 'error': 'changes 为空'}, ensure_ascii=False)
        if not text.startswith('{'):
            if not os.path.isfile(text):
                return json.dumps({'success': False, 'error': 'changes 既不是 JSON 文本也不是文件路径'},
                                  ensure_ascii=False)
            with open(text, encoding='utf-8-sig') as f:
                ch = json.load(f)
        else:
            ch = json.loads(text)
        r = uia.apply_changes(ch, project=project_root, dry_run=False)
        if r.get('success') and pack:
            r['pack'] = uia.pack(r['json'], project_root)
        r['note'] = '变更已写回 json' + ('（含 ftu 重新打包）' if r.get('pack') else '') + \
                    '；备份在同目录 <name>.json.bak'
        return json.dumps(r, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    finally:
        if tmp and os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def flythings_ui_diff(image_a: str, image_b: str, tolerance: int = 2, shift: int = 1,
                      min_area: int = 4, blur: float = 0.7, noise_bbox: int = 10,
                      out_png: str = '', out_json: str = '', show_noise: bool = False) -> str:
    """两张同尺寸截图的像素级对比（0 token，纯本地算法）——UI 验收 / 回归对比。

    输出的**是差异清单（数字）不是图**，所以不吃 token：区域坐标 / 尺寸 / 面积 / 最大色差。
    典型用法：改布局前截一张、改后截一张，两张丢进来 → 只有预期差异才算过；
    「改 A 碰坏 B」会被逐块列出来。跨渲染器（HTML 预览 vs 设备截图）只当骨架参考，
    字体磨边噪声靠下面的阈值压。

    抑制假报警的默认参数（沛哥 2026-09-10 定）：
    - tolerance=2：单通道 |Δ|<=2 视为相同
    - shift=1：±1px 抖动补偿（每像素在邻域找最优匹配，"看着像差异其实只是抖动"不算）
    - blur=0.7：对比前高斯模糊，抹掉字体抗锯齿噪声
    - min_area=4 + noise_bbox=10：小于 4px 的斑点和 bbox<=10x10 的小碎块归入 noise 不计入主清单
      （要连小碎块一起看，传 show_noise=True）
    out_png 给出标注图路径（红框=主差异，黄框=噪声）；out_json 存差异清单；缺省只返回清单。
    """
    if udf is None:
        return json.dumps({'success': False, 'error': 'ui_diff 不可用（缺 numpy/Pillow）'},
                          ensure_ascii=False)
    try:
        for p in (image_a, image_b):
            if not os.path.isfile(p):
                return json.dumps({'success': False, 'error': f'图片不存在: {p}'}, ensure_ascii=False)
        r = udf.diff_images(image_a, image_b, tol=int(tolerance), shift=int(shift),
                            min_area=int(min_area), open_k=3, out_png=out_png,
                            out_json=out_json, blur=float(blur),
                            noise_bbox=int(noise_bbox), show_noise=bool(show_noise))
        r['note'] = ('identical=true 表示无差异；regions 为真实差异块（坐标/面积/最大色差），'
                     'noise 为已忽略的抗锯齿/文字磨边小碎块')
        return json.dumps(r, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)


def flythings_device_screenshot(device: str = '', out: str = '', fmt: str = 'png', scale: float = 1.0,
                               quality: int = 90, fb: str = '/dev/fb0', pixel: str = 'auto',
                               width: int = 0, height: int = 0, offset_y: int = -1,
                               flip: str = '', rotate: int = 0, name: str = '',
                               timeout: int = 180) -> str:
    """从**设备真机**抓当前屏幕 → PNG / JPG / BMP，交给视觉模型看或用 flythings_ui_diff 做像素验收。

    **什么时候用**（AI 自己判）：要确认设备上实际显示成什么样 —— 布局对不对、图标有没有锯齿、切图对不对、
    颜色/文字是否正常、改完要不要验收、用户说“我屏幕上看到的是…”而你手上没有截图。
    三段式验收的第二步：预览(秒级) → **本工具抓真机截图(像素真相)** → flythings_ui_diff 比对。

    **怎么用**（默认参数就够了）：
      ① 抓一张：flythings_device_screenshot()                        → screenshots/device_600x1600_*.png
      ② 省 token：scale=0.5（长宽各半）或 fmt='jpg', quality=85
      ③ 多设备：device='192.168.0.117:5555'（先 `adb connect <IP>:5555`）
      ④ 抓完把返回的 path 交给看图能力分析；**不要把 raw/文件本身丢给模型**。
      ⑤ 改前抓一张存好，改后再抓一张 → flythings_ui_diff(改前, 改后) 0 token 出差异清单。

    **输出**：
      {success, path, width, height, format, sizeBytes, device, method, screenInfo{width,height,virtualHeight,bpp,stride,modes,offsetY,pan}, pixelOrder, readHint}

    **实现要点（踩过的坑，别改错）**：
    - 设备 rootfs 是裁剪版：**没有 screencap / dd / head**，`adb exec-out` 也不通（patched adbd 无 shell v2）；
      唯一可靠链路 = 设备侧 `busybox dd if=<fb> bs=<stride> skip=<pan.y> count=<height> | busybox gzip -1 > /tmp/x`
      + `adb pull`。裸 raw 7.68MB 经 WiFi pull 要 4 分钟+，gzip 后只剩 ~37KB、0.3 秒（画面平坦色块多压缩比极高）；
      设备上没有 busybox 时自动退化 `cat <fb> > /tmp/x` + pull（慢，返回里会提示先 push 一个 busybox）。
    - fb 参数一律问 sysfs：`modes`(=可见分辨率，如 U:600x1600p-50) / `virtual_size`(可能是 2 倍，OVERALLOC) /
      `stride` / `bits_per_pixel`。可见高 ≠ 文件行数，必须按 stride 逐行取，否则下半张图是脏数据。
    - **双缓冲页翻转（最容易抓错）**：读 `/sys/class/graphics/fb0/pan`（如 "0,1600" = 当前显示 yoffset=1600），
      抓图必须 skip=<yoffset>；否则抓到的是上一帧（旧画面仍可能是完整的 UI，肉眼很难发现抓错了）。
      本工具 offset_y=-1 自动读 pan，并在抓图后二次确认 pan 未变（翻了就重抓一次）。
    - 32bpp 内存序是 BGRA（小端 ARGB8888）；本工具按 alpha 字节位置自动判通道序（末字节≈0xFF→BGRA）。
      若颜色红蓝互换，传 pixel='rgba' 重抓；其他可选 bgra/rgba/argb/abgr/rgb565/bgr565/rgb888/bgr888。
    - 匹配参数：width/height 可覆盖（sysfs 读不到时）、flip='v|h|both'、rotate=90/180/270、offset_y 手动指定。
    """
    if dss is None:
        return json.dumps({'success': False, 'error': 'device_screenshot 不可用（缺 ui_tools/device_screenshot.py 或 Pillow）'},
                          ensure_ascii=False)
    try:
        r = dss.capture(device=device, out=out, fmt=fmt, scale=scale, quality=quality, fb=fb,
                        pixel=pixel, width=width, height=height, offset_y=offset_y,
                        flip=flip, rotate=rotate, name=name, timeout=timeout)
    except Exception as e:
        return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    return json.dumps(r, ensure_ascii=False)


def register_all(mcp):
    mcp.tool()(flythings_get_version)
    mcp.tool()(flythings_search)
    mcp.tool()(flythings_read_json)
    mcp.tool()(flythings_get_project_spec)
    mcp.tool()(flythings_validate_project)
    mcp.tool()(flythings_fui_pack)
    mcp.tool()(flythings_edit_ftu)
    mcp.tool()(flythings_build_ui_flow)
    mcp.tool()(flythings_generate_ui_preview)
    mcp.tool()(flythings_html_to_json)
    mcp.tool()(flythings_json_to_html)
    mcp.tool()(flythings_ui_editor)
    mcp.tool()(flythings_ui_edit_apply)
    mcp.tool()(flythings_ui_diff)
    mcp.tool()(flythings_device_screenshot)
    mcp.tool()(flythings_attach_cli_tools)
    mcp.tool()(flythings_create_project)
    mcp.tool()(flythings_create_bin_project)
    mcp.tool()(flythings_gen_ui_test)
    mcp.tool()(flythings_check_project_deps)
    mcp.tool()(flythings_generate_ui_assets)
    mcp.tool()(flythings_i18n_scan)
    mcp.tool()(flythings_i18n_add_language)
    mcp.tool()(flythings_i18n_export)
    mcp.tool()(flythings_i18n_import)
    mcp.tool()(flythings_i18n_refactor)
    mcp.tool()(flythings_i18n_to_json)
    mcp.tool()(flythings_list_packages)
    mcp.tool()(flythings_query_package)
    mcp.tool()(flythings_recommend_manifest)
    mcp.tool()(flythings_add_package)
    mcp.tool()(flythings_search_package)
    mcp.tool()(flythings_get_package_api)
    mcp.tool()(flythings_resolve_dependencies)
    mcp.tool()(flythings_generate_manifest)
