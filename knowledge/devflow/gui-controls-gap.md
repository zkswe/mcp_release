---
id: devflow-gui-controls-gap
title: 现代化 GUI 控件差距盘点（FlyThings 现状 vs 需求）
category: devflow
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [+ 自研 8 控件, md 方法论逐个补齐, 草稿待确认入库]
evidence: []
---
# 现代化 GUI 控件差距盘点（FlyThings 现状 vs 需求）

> 检索导引：问「平台缺哪些控件 / 有没有富文本控件 / 家底盘点（21 内置 + 8 自研）/ 下一步该补什么」→ 本文（缺口清单）；补法见 `devflow/custom-widget.md`。
> 2026-09-03 沛哥要求：查看目前缺失的现代化 GUI 控件（例：富文本显示）。
> 现状盘点来源：内置 21 控件（layout-audit 2026-09-01 校准）+ 自研 8 控件（guoxs lib-ext_widgets）。
> 结论用途：按缺失清单 + custom-widget.md 方法论逐个补齐。草稿待确认入库。

## 0. 现有家底

**内置 21 控件**：button / textview（单行）/ edittext（内置键盘）/ window（modal 弹窗）/
listview / slidewindow（宫格轮播）/ scrollwindow / pagewindow / pointer（表针）/
circlebar（环形进度）/ diagram（**实时波形**专用）/ digitalclock / imageanim（GIF/WebP 动图）/
painter（画板）/ qrcode / radiogroup / checkbox / seekbar / cameraview / videoview /
slidetext（跑马灯滚动文本，有 roll*）

**自研 8 控件**（lib-ext_widgets）：AlbumListView（分头多子项列表/惯性滚动/图片缓存）、
ImageBoxView（图片翻页相框：预加载/滑动/双指缩放/裁剪/切换特效）、FrameImageView（帧图播放）、
ImageEditView / RotateImageView（看图旋转编辑）、SliceProgressBar（切片进度）、
PullWidget（下拉展开面板，app 级触摸）、BaseView（基类）

## 1. 缺失清单（按 HMI 实用优先级）

| # | 控件 | 缺失度 | 现状/可代方案 | 建议路线 | 典型场景 |
|---|------|--------|--------------|---------|---------|
| 1 | **富文本 RichTextView（样式混排/自动折行/图文混排）** | ❌ 真缺 | textview 支持 **\n 换行**（沛哥 2026-09-03 纠正，此前 FT-024 结论误泛化）；但无自动折行（不换行只手动 \n）、无段落样式混排（局部色/字号/粗斜）、无嵌图 | 自绘 | 协议/说明/弹窗正文/日志/长文案（沛哥点名） |
| 2 | **通用图表 ChartView**（折线历史/柱状/饼/仪表） | ❌ 真缺 | diagram 只做实时波形（addData + 轴范围），无静态/历史/多类型 | 自绘 | 数据可视化、统计页、曲线历史 |
| 3 | **表格 TableView**（表头/列宽/行数据） | ❌ 真缺 | listview 网格可凑内容但无表头/列定义 | 组合+自绘 | 参数表、记录列表、设置矩阵 |
| 4 | **下拉选择 ComboBox/选项框** | ❌ 真缺 | 产品都在自造单选列表（xdv ufs.add_item_radio）；无现成"点击弹出选择" | 组合 | 设置页选项、模式选择 |
| 5 | **滚轮选择器 WheelPicker**（时间/日期/数值） | ✅ **可代（2026-09-19 改判）** | **`listview` 组合**：循环列表（`cycleEnable:true`）+ 引擎惯性/回弹（`edgeEffect:1`/`dragMaxDis:50`/`autoRollback:true`）+ **数据侧平移**定正中行 + **选中条挂静态层**；原自绘包 `ui_v1/WheelPicker/` 已移除 | **映射（L2）**，不建包 | 调时间日期、数值步进选择（口径 `uicontrols/listview-wheel-picker.md`） |
| 6 | **轻提示/角标/加载指示**（Toast/Snackbar、Badge、Spinner 菊花） | 🟡 半缺 | PopupService 只有居中 dialog；无角落浮动条/角标/转圈 | 组合小件 | 操作反馈、未读角标、等待 |
| 7 | **Switch 现代开关** | 🟡 可代 | checkbox picTab 两态图可做出开关样式 | 组合 | 开关设置项 |
| 8 | **标签页 TabHost/侧滑抽屉 Drawer** | 🟡 架构可代 | 多 Activity openActivity / pagewindow / PullWidget 下拉面板 | 组合 | 多页签导航 |
| 9 | **长按拖拽排序 / 滑动删除列表项** | 🟡 缺 | AlbumListView 有长按但无拖拽换序/侧滑删除 | 扩展 AlbumListView | 排序设置、删除列表项 |

**已有不算缺**：图片轮播 Banner（ImageBoxView 可代）、跑马灯（SlideText）、下拉面板（PullWidget）、
双指缩放（ImageBoxView）、惯性滚动/回弹（scrollwindow/自研）、动图（imageanim）、弹窗（modal window）、
环形进度（circlebar）。

## 2. 富文本控件需求展开（优先级 #1）

**现状痛点**（为什么还要做）：
- textview **支持 \n 换行**（沛哥 2026-09-03 纠正：此前 FT-024「不支持 \n」结论是误泛化，实际可换行渲染）
- 但仍缺：**自动折行**（内容长只能自己手插 \n，不能随屏宽自动排）、**段落样式混排**（局部颜色/加粗/字号）、
  **图文混排**（行内嵌图）、**垂直滚动阅读**（长文超出控件高度）——协议全文、操作说明、免责声明这类
  长文本要么手动分段 \n 死排版，要么切图，不可随分辨率自适应

**RichTextView 功能需求草案**（在 textview 已支持 \n 的基础上补能力）：
1. 输入：富文本段描述（分段 + 每段 style：fontSize/color/bold/italic/对齐/行距），或受限 HTML/标记字符串
2. 排版：逐字符折行引擎（复用字库测量 API，中文全角/ASCII 半角宽度系数 1.0/0.55，参考 FT-009 公式），
   自动垂直滚动（内容超控件高时滚动画布）
3. 样式混排：段内支持分段样式（颜色/字号/粗斜体切换）；可嵌小图（inline image，BitmapHelper 解码 + 行内定位）
4. 交互（可选）：超链接区命中（Region 命中检测 → 点击回调）、长按选择复制
5. 显示：自绘路线（onDraw + bitmap_t 离屏排版 + Region 脏区局部刷新）或 子控件按"视觉行"动态复用的组合路线
6. 性能：长文只排版可视区（分段缓存行布局）；不整文重排
7. 配 SliceProgressBar 式资源/Attr 构建 + 独立测试页

**可抄素材**：text_utility（字宽测量/截断）、FT-009 宽度公式、FrameImageView 的 Region 脏区刷新、
AlbumListView 的滚动 + 可视区复用套路、ImageBoxView 的异步加载。

## 3. 落地节奏建议

按 custom-widget.md 的 10 步 checklist 逐个做，每个配独立测试页 + html2json HTML 原型确认：
1. RichTextView（富文本/多行文本）——最高优先，通用性最强
2. ComboBox 下拉选择（最常被自造轮子，做了能立刻替代产品里的单选列表）
3. ChartView 通用图表（折线历史 + 柱状 + 饼）
4. Toast/Snackbar + Loading 菊花 + Badge（小件，一次做一组）
5. TableView（需要时再做，listview 可过渡）
6. ~~WheelPicker~~（配合日期时间场景）—— **2026-09-19 移除**：改判 **L2**，走 `listview` 组合（`uicontrols/listview-wheel-picker.md`），不再建包
