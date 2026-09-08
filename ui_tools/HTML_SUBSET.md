# 受限 HTML 规范（FlyThings UI 原型 → json 布局）

> 通用工具：`tools/ui_tools/html2json.py`（html → json）、`tools/ui_tools/json2html.py`（json → html 预览）。
> 流程：**HTML 交互原型 → html2json.py → ui/*.json → fui pack → ftu（设备端）**，html 预览与 ftu 同源于 json。

## 为什么用受限 HTML
HTML 是首版交互界面的最佳载体（浏览器直接看、客户确认快、改起来直观）。
但 FlyThings 控件能力有限（无 CSS 动画/圆角阴影/复杂布局），所以 HTML 只允许用
**FlyThings 控件能力范围内的子集**，转换器才能 1:1 还原。

## ⚠️ CSS 效果 / 动效处理原则（转图 + 控件，不是硬转）

**HTML 原型允许任意展示效果**：emoji、iconfont、CSS 渐变/阴影/圆角、粒子、甚至 3D 动效（如
loading 动画）都可以在 HTML 里做——浏览器能力强，原型就是要炫。

**✅ JS 交互设计（2026-08-29 沛哥建议，强烈推荐）**：第一套 HTML 效果稿**建议直接写 JS 交互**——
点击弹窗/页面切换/tab 切换/列表滚动/数据模拟/动效触发等，让客户在浏览器里直接"点得动"，
前期效果确认和修改效率翻倍。转换器已自动忽略 `<script>` 标签和 onclick 等交互属性（实测验证），
JS 只服务于浏览器预览确认，不转 json；FlyThings 端的交互逻辑由 logic.cc 实现（json 布局 + 回调）。

**但转 json 不是硬转**：FlyThings 没有 CSS 引擎，效果类属性无法 1:1 映射成控件属性。
转换器只提取**控件能表达的东西**（位置/尺寸/文字/颜色/背景图引用），
其余效果一律**转图片 + 控件**组合实现：

| HTML 里的效果 | 转 json 的做法 |
|---|---|
| 渐变背景 / 复杂背景图 | 切图 → 普通 PNG 或 .9.png，`data-pic` 引用 |
| 圆角 / 可拉伸背景（卡片/按钮/轨道/输入框） | 切图 → **.9.png 九宫格**（top/left 1px 黑线标拉伸区），`data-pic` 引用 |
| emoji / iconfont / 特殊符号图标 | **转 PNG 图标**（设备字库裁剪不支持 emoji，图片不受字库限制），`data-pic`/`src` 引用 |
| 阴影 / 描边 / 毛玻璃 | 切图（效果画进图片），`data-pic` 引用 |
| loading / 旋转 / 3D / 粒子动效 | **序列帧 PNG 或 GIF** → ZKImageView 动图控件（imageanim，支持 Z20/Z21/T113/V85X 等平台，循环次数 ≤0 无限循环）；静态图则用控件切换 |
| 鼠标 hover / 点击态 | 两态图：normal + pressed（`_p` 后缀），按钮 `picTab{pic0,pic1}` |

**转换器行为（2026-08-29 升级：自动转图）**：style 里出现 `linear-gradient/box-shadow/border-radius/animation` 等效果属性时，转换器**自动生成图片资源**（不再只 warning）：
- `linear-gradient(...)` → 自动生成渐变 PNG（`images/grad_*.png`），控件加 `backgroundPic`
- `box-shadow` + 圆角 → 自动生成阴影卡片图（`images/shadow_*.png` / `gradshadow_*.png`），渐变+阴影自动合成
- `border-radius` → 自动生成圆角图（四角真透明，可叠背景）
- 文本含 emoji → 自动转 emoji PNG 图标（`images/emoji_*.png`），控件变图标 textview（设备字库不支持 emoji）
- `class="loading"/"spinner"` 或 `animation: spin` → 自动生成 loading GIF（`images/loading_*.gif`，12 帧循环）+ imageanim 控件；并在 warning 中提示 logic.cc 里 `mXXXPtr->play("images/loading_*.gif")`
- 图片输出到 json 同目录 `images/`（即 ui/images/），json 引用 `images/xxx.png`；生成数量在返回的 `generatedAssets` 字段
- 其余效果（transition/transform/filter/opacity/radial-gradient）仍不硬转，输出 warning 提示转图后用 data-pic 引用

**切图工具**：`tools/ui_tools/gen_res.py`（Pillow 脚本）可按 CSS 设计稿参数生成
PNG/.9.png/序列帧；手工切图也可，输出到 `resources/images/`。

## 🎯 图标优先（iconfont 矢量线框，沛哥 2026-09-03 定规）

**生成 UI 时常用操作必须用图标表达，禁止用「按钮+文字」糊弄**。返回/播放/暂停/上一首/下一首/
设置/搜索/删除/刷新/确认/关闭/加减/音量/主页/菜单等通用操作，HTML 里写 `data-icon`（或
iconfont class），转换器**自动生成 iconfont 风格矢量线框 PNG**（描边线性图标，单色可配），
设备端显示真图标；图片不受设备裁剪字库限制。

### 写法（三种等效）
```html
<!-- ① 图标按钮（推荐：可点击，自动生成 normal+pressed 两态图 picTab） -->
<div class="btn" data-icon="play" data-x="216" data-y="176" data-w="48" data-h="48" data-caption="BtnPlay"></div>
<div class="btn" data-icon="返回" data-x="10" data-y="10" data-w="40" data-h="40" data-caption="BtnBack" data-color="#EEF2F6"></div>

<!-- ② 纯展示图标（textview 背景图，不可点；要可点请用 ① 的 btn） -->
<div class="icon" data-icon="wifi" data-x="430" data-y="8" data-w="20" data-h="20"></div>

<!-- ③ iconfont class 风格（效果稿里视觉同义，转换器同样识别） -->
<i class="iconfont icon-volume" data-x="30" data-y="200" data-w="24" data-h="24"></i>
```

### 规则
- **data-icon 值**：英文名或中文别名都认（`play`/`播放`/`返回`/`back`...，见下表），自动映射规范名。
- **data-color**：线框颜色 `#RRGGBB`（默认 `#D8E2F0` 浅灰蓝，深色主题友好）；图标按钮按下态自动提亮。
- **尺寸**：控件建议正方形（data-w == data-h）；PNG 与控件同尺寸、线框居中（非正方自动居中不变形）。
- **caption**：图标按钮同样要 data-caption（回调命名用），不要往图标按钮里写文字；
  需要文字说明 → 图标按钮旁另加 `div.text`。
- **覆盖**：若同时给了 data-pic/data-pic0 等显式图，以显式图为准（data-icon 忽略）。
- 未收录的图标名 → warning 提示（列出可用名）；自备图仍用 data-pic 老办法。

### 常用图标词表（46 个，中文别名自动映射）
| 操作 | data-icon | 操作 | data-icon |
|---|---|---|---|
| 返回/左箭头 | back | 前进/右箭头 | forward |
| 上/下 | up / down | 上一首 | prev |
| 下一首 | next | 播放 | play |
| 暂停 | pause | 停止 | stop |
| 设置/齿轮 | settings | 搜索 | search |
| 刷新 | refresh | 主页/首页 | home |
| 删除 | delete | 编辑/改名 | edit |
| 确认/对勾 | check | 关闭/取消 | close |
| 加/新增 | plus | 减 | minus |
| 菜单 | menu | 更多 | more |
| 列表 | list | 音量 | volume |
| 静音 | mute | 电源 | power |
| 下载 | download | 上传 | upload |
| 分享 | share | 用户/我的 | user |
| 锁定 | lock | 信息/详情 | info |
| 警告/告警 | warning | 相机/拍照 | camera |
| 时间/时钟 | clock | 日历/日期 | calendar |
| 通知/铃铛 | bell | 麦克风/语音 | mic |
| 定位/位置 | location | 邮件/邮箱 | mail |
| 预览/眼睛 | eye | 录像/摄像 | video |
| 电话/拨打 | phone | WiFi/无线 | wifi |
| 蓝牙 | bluetooth | 收藏/星标 | star |
| 喜欢/心 | heart | 更多可用名 | gen_res.glyph_list() |

## 结构骨架
```html
<div class="screen" data-res="480x272" data-bg="#0E131A">
  <!-- 页面控件按 Z 序从底到顶书写：顶栏 → 底部按钮 → 卡片 → 弹窗（最后） -->
  <div class="text"  data-x="10" data-y="4"  data-w="200" data-h="24" data-fs="14" data-color="#EEF2F6">标题</div>
  <div class="btn"   data-x="318" data-y="5" data-w="52"  data-h="24" data-fs="11" data-bg="#374457">重命名</div>
  <div class="card"  data-x="8" data-y="42" data-w="149" data-h="118" data-pic="card.9.png">
    <!-- 窗口内子控件：相对坐标 -->
    <div class="text" data-x="8" data-y="6" data-w="100" data-h="16" data-fs="11">1#环网柜</div>
  </div>
  <div class="modal" data-x="80" data-y="46" data-w="320" data-h="180" data-caption="WinNumPad">
    <div class="input" data-x="12" data-y="36" data-w="296" data-h="40" data-num="1"></div>
  </div>
</div>
```

## 元素/class → FlyThings 控件映射表

| HTML（tag + class） | FlyThings 控件 | 说明 |
|---|---|---|
| `div.screen` | 根节点 | 必须；分辨率 data-res="WxH"（也支持 data-width/data-height 或 style 宽高），背景 data-bg / data-background（默认 #0E131A） |
| `div.text` / `p` / `span` | ZKTextView | 字号 data-fs（也认 data-font-size/data-fontSize/内联 font-size）、文字色 data-color、背景 data-bg/data-background、对齐 data-align |
| `div.btn` / `button` | ZKButton | data-bg 底色、data-fs；**图片按钮铁律**：有图（data-pic/data-pic0~4 多态图、data-bgpic 背景图）自动去底色（图片叠色效果错乱）；纯文字才用底色。data-pic0 正常/1 按下/2 选中/3 选中按下/4 无效；data-icon-w/h + data-pad 图标 padding |
| `div.input` / `input` | ZKEditText | data-num="1" 数字键盘、data-hint 提示、data-hint-color 提示色、data-password="1" 密码掩码、data-bg 底色、预填文本=div 内容 |
| `div.imageanim` / `div.anim` / `div.gif` | ZKImageAnim 动图 | data-src/data-play-file GIF 路径（自动加 image/ 前缀）、data-loop 循环次数（0=无限）、data-interval 帧间隔；生成 playFile 字段设备自动播放 |
| `div.bar` / `div.seekbar` | ZKSeekBar 进度条 | data-max 最大值、data-value 当前值、data-track/data-fill 轨道/填充图 |
| `div.circlebar` | ZKCircleBar 圆形进度 | data-bg 背景图（不裁剪）、data-fill 有效图（按进度裁剪扇形）、data-max/data-max-angle/data-start-angle、data-clockwise="0/1"（⚠️ false=逆时针） |
| `div.diagram` / `div.wave` | ZKDiagram 波形图 | 坐标 data-x-min/x-max/y-min/y-max；背景 data-bgpic；子 div.wave 每条波形（data-color 线色/data-pen-width/data-step/data-style 0折线1曲线/data-erase 刷新间距/data-antialias） |
| `div.digitalclock` / `div.clock` / `div.time` | ZKDigitalClock 数字时钟 | data-format 时间格式（HH 24小时制/hh 12小时制/MM 分钟/SS 秒/yyyy-MM-dd 日期/EEEE 星期）、data-beat="1" 冒号闪烁、自动实时刷新系统时间 |
| `div.slidetext` / `div.candidate` | ZKSlideText 候选字滑动条 | data-text-bg 文字背景色（输入法候选词用） |
| `div.cameraview` / `div.camera` | ZKCameraView 摄像头预览 | data-auto-preview 自动预览、data-format-w/h 采集格式 |
| `div.painter` / `div.canvas` | ZKPainter 画布 | 触摸绘制，代码 paint() 刷新 |
| `div.pointer` / `div.gauge` | ZKPointer 仪表盘指针 | data-pointer-pic 指针图、data-bgpic 表盘、data-pointer-w/h、data-start-angle（可负）、data-rotate-speed、data-clockwise、data-animatable |
| `div.qrcode` / `div.qr` | ZKQRCode 二维码 | data-code 初始内容，代码 loadQRCode() 动态生成 |
| `div.videoview` / `div.video` | ZKVideoView 视频播放 | data-volume 默认音量、data-loop 循环播放 |
| `div.card` / `div.window` / `div.panel` | ZKWindow 容器 | 子控件嵌套其内（相对坐标）；data-pic 背景图、data-bg 纯色背景；**默认 visible:false（初始隐藏，代码 showWindow 弹出）** |
| `div.modal` / `div.dialog` | ZKWindow 弹窗 | 自动 modal:true + visible:false + 最后定义（最上层）；data-hide-timeout 自动隐藏秒数（模态 8 实测）；data-bg 纯色背景（无图时） |
> ⚠️ **系统栏（navibar/statusbar）**：类似 Android 状态栏/导航栏的悬浮窗口，根节点加 `data-topmost="1"`（悬浮最上层）+
> 不写 `data-bg`（背景透明）；statusbar 可用 `data-x/y/w/h` 指定局部悬浮块（如 100×41 电量显示），navibar 全屏叠弹窗。
| `div.list` | ZKListView | data-cols/data-rows/data-row-spacing/data-col-spacing；子项为 subItem（见下） |
| `div.slidewindow` / `div.slide` / `div.launcher` | ZKSlideWindow 滑动窗口（Android 主页式） | data-cols/data-rows 每页行列、data-icon-w/h 图标尺寸、data-icon-align 文字对齐、data-icon-pad-b/data-pad-b 间距、data-drag-max 拖动距离、data-edge-effect 边缘效果、data-orientation 方向、data-roll-speed 滚动速度；子 div.item 每个图标项（data-pic/data-pic1 两态图 + 文字） |
| `div.scrollwindow` / `div.scrollwin` / `div.scroll` | ZKScrollWindow 滚动窗口 | data-drag-max 最大拖动距离（=滚动内容尺寸）、data-orientation 滑动方向（0水平/1垂直）、data-edge-effect 边界效果；滚动内容=内嵌普通 window（尺寸=dragMaxDis） |
| `div.pagewindow` / `div.page` / `div.pager` | ZKPageWindow 翻页窗口 | data-drag-max 拖动距离、data-orientation 方向、data-edge-effect 边界、data-roll-speed 滚动速度；页面=多个同尺寸 window 叠放（代码 turnToNextPage/turnToPrevPage 翻页） |
| `div.checkbox` | ZKCheckBox | data-checked="1" 勾选；**padding 三件套**：data-icon-w/h 图标尺寸、data-pad 图标与文字间隙、data-pic/data-pic2 两态图（pic0 未选/pic2 选中，自动生成 iconPosition+textPosition）；无图时 data-bg/data-bg2 + data-color/data-color2 选中变色 |
| `div.radio` / `div.radiogroup` | ZKRadioGroup | 子项自动进 radiobuttons 数组 |
| `div.icon` / `img` | ZKTextView(带背景图) | data-pic / src 图标；空文本 |

## 布局与定位
- `data-x / data-y / data-w / data-h`（px 整数）→ position{left,top,width,height}
- 也支持 `style="left:10px;top:20px;width:100px;height:30px"`
- 窗口内子控件坐标为**相对窗口**的坐标（自动嵌套进 window 键内）
- `.screen` 根节点分辨率：`data-res="WxH"` > `data-width + data-height` > `style="width:..;height:.."` > 默认 480x272；
  强烈建议显式写 data-res 或传 res 参数（默认 480x272 对多数屏是错的）

## 属性速查
| 属性 | 作用 | 示例 |
|---|---|---|
| `data-caption` | 控件名（C 标识符）；缺省自动 TextView1/Button1... | data-caption="BtnRename" |
| `data-fs` | 字号 px（同义：data-font-size / data-fontSize / 内联 style="font-size:14px"） | data-fs="14" |
| `data-color` | 文字色 #RRGGBB | data-color="#EEF2F6" |
| `data-bg` | 底色 #RRGGBB（同义：data-background / 内联 background）| data-bg="#374457" |
| `data-align` | left/center/right → 36/37/38 | data-align="center" |
| `data-pic` | 背景图（相对 resources/ 或 images/） | data-pic="card.9.png" |
| `data-num` | edittext 数字键盘 | data-num="1" |
| `data-hint` | edittext 提示文字 | data-hint="请输入" |
| `data-max/data-value` | seekbar 最大值/当前值 | data-max="100" data-value="52" |
| `data-track/data-fill` | seekbar 轨道图/填充图 | data-track="bar_track.9.png" |
| `data-cols/data-rows` | listview 列/行 | data-cols="1" data-rows="5" |
| `data-row-spacing` / `data-col-spacing` | listview 行/列间距 | data-row-spacing="4" |
| `data-icon-w` / `data-icon-h` | slidewindow 图标尺寸 | data-icon-w="128" data-icon-h="128" |
| `data-icon-align` | slidewindow 图标文字对齐（41 底部） | data-icon-align="41" |
| `data-icon-pad-b` / `data-pad-b` | slidewindow 文字/容器下间距 | data-icon-pad-b="5" data-pad-b="8" |
| `data-drag-max` / `data-edge-effect` / `data-roll-speed` | slidewindow 拖动距离/边缘效果/滚动速度 | data-drag-max="200" |
| `data-drag-max` | scrollwindow 最大拖动距离（=滚动内容尺寸，如 2400） | data-drag-max="2400" |
| `data-orientation` | scrollwindow 滑动方向（0水平/1垂直） | data-orientation="1" |
| `data-edge-effect` | scrollwindow 边界效果（拖拽/无/循环） | data-edge-effect="0" |
| `data-roll-speed` | pagewindow 滚动速度 | data-roll-speed="30" |
| `data-checked` | checkbox 勾选 | data-checked="1" |
| `data-pic0`~`data-pic4` | button 多态图（正常/按下/选中/选中按下/无效） | data-pic0="btn_normal.png" data-pic1="btn_pressed.png" |
| `data-bgpic` | button 背景图（backgroundPic 单图） | data-bgpic="btn_bg.png" |
| `data-icon-w` / `data-icon-h` | checkbox/button 图标尺寸（缺省=控件高） | data-icon-w="48" |
| `data-pad` | checkbox 图标与文字间隙（缺省 6px，自动算 textPosition） | data-pad="8" |
| `data-color2` / `data-bg2` | checkbox 无图时选中态色 | data-color2="#FF0000" |
| `data-clockwise` | circlebar 方向（⚠️ false=逆时针，0/1） | data-clockwise="0" |
| `data-max-angle` / `data-start-angle` | circlebar 最大/起始角度 | data-max-angle="360" data-start-angle="80" |
| `data-fill` | circlebar 有效图 / seekbar 填充图 | data-fill="circle_valid.png" |
| `data-x-min/x-max/y-min/y-max` | diagram 坐标轴范围 | data-x-max="100" |
| `data-pen-width` / `data-step` / `data-style` | diagram 波形线宽/步进/样式（0折线1曲线） | data-style="0" |
| `data-erase` / `data-antialias` | diagram 刷新间距/平滑 | data-erase="20" data-antialias="1" |
| `data-format` | digitalclock 时间格式（HH 24小时/hh 12小时/MM 分/SS 秒/yyyy-MM-dd 日期/EEEE 星期） | data-format="HH:MM:SS" |
| `data-text-bg` | slidetext 候选字文字背景色 | data-text-bg="#FFFFFF" |
| `data-format-w` / `data-format-h` | cameraview 采集格式尺寸 | data-format-w="640" data-format-h="480" |
| `data-pointer-pic` / `data-bgpic` | pointer 指针图/表盘背景 | data-pointer-pic="pointer.png" |
| `data-start-angle` | pointer 起始角度（可为负） | data-start-angle="-120" |
| `data-code` | qrcode 初始内容 | data-code="www.zkswe.com" |
| `data-volume` / `data-loop` | videoview 默认音量/循环 | data-volume="5" data-loop="1" |
| `data-thumb-pressed` | seekbar 滑块按下态图 | data-thumb-pressed="yb_pressed.png" |
| `data-orientation` | seekbar 垂直方向（1=垂直） | data-orientation="1" |
| `data-password-char` | edittext 密码掩码字符 | data-password-char="*" |
| `data-clock-color` | digitalclock 数字颜色 | data-clock-color="#FFFFFF" |
| `data-beat` | digitalclock 冒号闪烁 | data-beat="1" |
| `data-password` | edittext 密码掩码 | data-password="1" |
| `data-hint-color` | edittext 提示文字色 | data-hint-color="#959595" |
| `data-loop` / `data-interval` | imageanim 循环次数（0=无限）/帧间隔 | data-loop="1" |
| `data-play-file` / `data-gif` | imageanim GIF 路径（缺省自动加 image/ 前缀） | data-src="test.gif" |
| `data-hide-timeout` | window/modal 自动隐藏秒数（-1 不自动隐藏） | data-hide-timeout="8" |
| `data-topmost` | 根节点悬浮标记（1=最上层，系统栏/导航栏用） | data-topmost="1" |
| `data-x/y/w/h` | 根节点局部悬浮块（statusbar 电量显示等，缺省全屏） | data-x="615" data-y="25" data-w="100" data-h="41" |

## listview 子项写法
子项控件**直接写在 `div.list` 容器内**即生成 subItem（每个子控件一个 subItem）：
```html
<div class="list" data-x="0" data-y="0" data-w="480" data-h="200" data-rows="4">
  <div class="text" data-x="10" data-y="2" data-w="200" data-h="20" data-fs="13">温度 25°C</div>
  <div class="text" data-x="300" data-y="2" data-w="100" data-h="20" data-fs="13">湿度 60%</div>
</div>
```
- 推荐用 `<div class="item">` 包裹每一行，行内再写多个子控件——转换器会**展开包裹层**、
  逐个生成 subItem（不会吞掉内部控件）：
```html
<div class="list" data-x="0" data-y="0" data-w="480" data-h="200">
  <div class="item">
    <div class="text" data-x="10" data-y="2" data-w="200" data-h="20">第 1 行</div>
    <div class="text" data-x="300" data-y="2" data-w="100" data-h="20">状态 A</div>
  </div>
  <div class="item">
    <div class="text" data-x="10" data-y="2" data-w="200" data-h="20">第 2 行</div>
  </div>
</div>
```
- ⚠️ 旧版本曾要求必须 class="subitem" 直挂、`.item` 包裹会被吞成单个空 subItem，已修复：现在两种写法都支持。

## 铁律（转换器自动处理，手写 HTML 时注意）
1. **Z 序 = HTML 书写顺序**：后定义在上层。弹窗 modal 必须最后书写。
2. **window 子控件必须写在 card/modal 内部**（转换器自动嵌套；平铺会错乱）。
3. 文本只用汉字 + ASCII + 基础符号（/ % # - _ 空格），禁 emoji/特殊字符（字库裁剪）。
4. 图片：需拉伸的背景图用 .9.png；固定尺寸图标用普通 PNG。
5. 进度条用 `div.bar`（ZKSeekBar），**禁止用色块/字符模拟**。
6. 输入框用 `div.input`（ZKEditText 系统键盘），不自绘键盘。
7. 颜色一律 #RRGGBB 6 位十六进制（转十进制自动完成）。
8. **文本支持 `\n` 换行**（沛哥 2026-09-03 纠正：此前 FT-024「textview 不渲染 \n」结论误判）：
   textview/button 的 text 含 `\n` 可正常渲染多行（代码 setText 与 json 布局均支持）。HTML 里的 `<br>` 由转换器转成 `\n`（换行）；
   HTML 文本节点的普通换行/缩进仍折叠为单行（源码排版不产生意外换行，换行请用 `<br>` 显式写）。
   长文本也可用多个 `div.text` 上下排列，或后续富文本控件自动折行。
9. **输出字段全集显式化 v2（沛哥 2026-09-08）**：html2json 生成 json 时每个控件输出本类型**必写字段全集（含默认值）**，不做缺省省略——防版本不匹配。
   **基准 = `projects/SampleUI-New/ui/1024x600` 每类型 100% 交集**（模板见 `references/kb/controls.md`「字段全集显式化」表；check_all #14 验缺键）。
   转换器已内建：textview 恒带 touchable/alignment/colorTab/fontSize；button 恒带 touchable:true/picTab/text；window 恒带
   backgroundColor/hideTimeOut/modal/touchable/visible（不含 beepEnable）；edittext 恒带 bold/textType/text/fontSize（不含 beepEnable）；
   seekbar 恒带 backgroundColor/thumb/touchable/visible；qrcode 恒带 touchable:true/padding:10/visible；videoview 按 SampleUI
   （touchable:true 无 beepEnable）；listview 恒带 touchable:true/hasScrollbar/backgroundColor 等。
   ⚠️ beepEnable 不强制（交互控件默认支持）；交互控件 touchable 显式 true，容器/纯显示 false。

## ⚠️ 切图 / 图片资源铁律（2026-08-29 羊了个羊实战教训）
1. **图片尺寸必须与 json 控件尺寸一致**（瓦片 76×76 控件 → 76×76 图；槽位 72×72 → 72×72 图），
   不要生成大图让控件缩放，也不要小图拉伸。
2. **圆角卡片图四角必须真透明（alpha=0）**：渐变/填充底是整矩形画的，圆角只是描边轮廓，
   所以渐变画完后必须用圆角 mask 裁剪（putalpha）清掉弧线外角落；
   阴影模糊（GaussianBlur）会溢出到弧线外，最后整体再裁一次圆角清掉残影。
   工具：`gen_res.rounded_card()` / `gen_gradient(..., radius=r)` 已内置裁剪。
3. **用透明角图片的按钮不要设 `bgColorTab`**：透明角会透出按钮底色而不是窗口背景。
   需要透背景的图片按钮（瓦片/槽位/图标钮）→ 不放 bgColorTab；纯文字按钮才用底色。
4. **功能按钮尽量用图片按钮**：`picTab{pic0: normal, pic1: pressed(_p 后缀)}` 两态图，
   比纯色底色 + 文字更接近设计稿（2026-08-29：重开/撤回/洗牌/移出全部改图）。
5. **textview 支持 `backgroundPic`**（json 字段）：标题背景条等直接配图，不用套 window。
6. **居中 alignment 实测值（2026-08-29 设备验证，勿信旧文档）**：
   - `37` = 居中（水平+垂直居中，按钮/标题均实测）
   - `36` = 靠左垂直居中（非居中！）
   - `38` = 靠右垂直居中
   HTML 的 `data-align="center"` → 37（html2json 已正确映射，勿改）
7. 渐变底 PNG 生成必须检查四角 alpha：`img.getpixel((2,2))[3] == 0` 才算合格。
8. **PNG 生成管线铁律（2026-09-08 沛哥定规：新 AI 客户端按规范转 png 仍默认锯齿 → 规范显式约束）**：
   AI 需要图片资源时**只能走三条路，禁止自创**：
   ① CSS 效果（渐变/圆角/阴影/emoji/图标/loading）→ 写进 HTML 由 html2json 自动转图（内置抗锯齿管线）；
   ② 图标资源 → `flythings_generate_ui_assets`（内置三级降级 + 超采样抗锯齿）；
   ③ 必须自绘的自定义图 → 用 gen_res.py 公开函数（rounded_card / gen_gradient / gen_shadow_card /
      emoji_icon_ss / glyph_icon_ex / line_icon / frames_loading_gif…，全部内置抗锯齿）。
   **禁止**：AI 用自身 image 生成能力直出小尺寸 png 交付（大图缩小边缘/斜线必锯齿）、
   禁止自写 Pillow/绘图代码 1x 直画圆角/斜线/圆弧（1x 二值 alpha 无抗锯齿，PIL 默认 butt 线帽斜线端点出毛刺）。
9. **PNG 防锯齿五要素（生成后逐条自查，任一不满足重新生成或换工具路径）**：
   ① 像素尺寸与控件 position 严格相等（FlyThings 普通 PNG 不缩放；大图缩小必须交给工具 LANCZOS）；
   ② 斜线/曲线/圆角必须 ≥4x 超采样绘制后 LANCZOS 缩回，或 α 通道高斯羽化过渡（sigma≈0.5），禁止 1x 直画；
   ③ 线段端点加 round cap（PIL 默认 butt 平头 → 斜线端点毛刺缺口）；
   ④ 圆角/异形图弧线外角落 alpha 必须 =0（真透明），阴影模糊溢出须再裁一次圆角清残影；
   ⑤ 全部生成后跑 check_all 校验（#11 图片尺寸 == position、四角 alpha 检查）。

## 示例
`tools/ui_tools/examples/` 下有完整示例（screen + 顶栏 + 卡片 + 弹窗 + 进度条 + 列表）。

## 转换命令
```bash
# html → json（默认输出同名 .json）
python tools/ui_tools/html2json.py ui/main.html ui/main.json
# json → html 预览（客户确认稿）
python tools/ui_tools/json2html.py <项目根目录或json路径>
# 全检（通用，参数化项目路径，不随项目复制）
python tools/ui_tools/check_all.py <项目根目录>
```
