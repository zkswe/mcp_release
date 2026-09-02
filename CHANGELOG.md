# CHANGELOG — FlyThings MCP Open

> 版本迭代记录（按版本从新到旧）。当前版本：**v0.7.15-open**（2026-09-02）。
> 每次迭代在本文件顶部新增一节；MCP_FEATURES（kb_tools.py）只保留精华摘要，完整历史以本文件为准。

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
