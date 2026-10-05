---
id: uicontrols-json-field-mandatory
title: ⛔ json 字段全集显式化（每控件必写字段 v2.1，双源基准）
category: uicontrols
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [不同 fui, touchable 为典型, 含默认值 -1, false, 字号, 均显式写, 不做缺省声明, 非噪音, 写全对新引擎无害, 权威基准, 需求方指定, SampleUI-New, ui, 1024x600, 42 json, 新 IDE 全量序列化]
evidence: []
---
# ⛔ json 字段全集显式化（每控件必写字段 v2.1，双源基准）

> 检索导引：问「json 字段要不要写全 / 缺字段会出什么问题 / touchable 默认值 / 为什么 radiogroup 要 touchable true / 每类型必写键有哪些」→ 本文（check_all #14 校验依据）。
> 2026-09-08 需求方定规。**背景**：带默认值字段若靠引擎缺省，不同 fui/easyui 版本默认处理可能不同 → 版本不匹配异常（touchable 为典型）。
> **规则**：生成 json 时每个控件输出本类型**必写字段全集（含默认值 -1/0/false/字号，均显式写）**，不做缺省声明；
> -1 = 0xFFFFFFFF 是有意义的显式值（非噪音）。写全对新引擎无害，且产物与新版 IDE 全量序列化格式兼容。
> ⚠️ **`backgroundColor: -1` 的真实语义 = 框架跳过背景绘制（不渲染），不是"一种透明色"**（2026-10-05 口径）：
> 它不铺任何底 → ① 控件**透明区直接露出背后真正在显示的东西**（页面根底色 / 祖先 window / 下层控件），
> 所以"把 `backgroundColor` 填成贴图主色 → 切图的圆角/透明角被**盖平成直角**，写 `-1` 才露圆角"这类现象才能解释；
> ② 贴图的**半透明像素与下层合成**，不是与某个固定底色合成 —— 需要"半透明按指定底色算"（如 AA 边缘的混色基准）时
> **必须写具体颜色，不能靠 `-1`**。
> **权威基准（指定）**：`projects/SampleUI-New/ui/1024x600`（42 json、新 IDE 全量序列化）——**每类型控件 100% 共有的字段 = 必选**；
> **交叉复验**：`projects/LearningProject/basedemo-new_z20_1024_600`（35 官方 Demo/44 json，ftu unpack 反解）。
> **落地**：check_all.py #14 按本表校验缺键（FAIL）；html2json.py 已按全集输出；手写 json 缺键照本表补默认。

## 5 条口径（2026-09-08）
1. **beepEnable 不强制**：交互控件默认支持，废除「恒带 beepEnable:true」规范（两源 edittext/window 均证实非必写）
2. **touchable 交互控件显式 true**：button/listview/可拖 seekbar(有 thumb)/qrcode/videoview/diagram/subitem/slidewindow/circlebar；容器与纯显示显式 **false**（window/painter/textview/cameraview/digitalclock 主 false）
   - ⚠️ **例外：radiogroup 虽是容器，也必须 `touchable: true`**。写 false 会让整组**收不到触摸、点了没反应**（单选组点不动）；生成器/手写 json 均按 true。详见 `knowledge/uicontrols/touch-events.md`
3. **qrcode 恒写 padding:10**（各边默认 10；SampleUI 无 padding 键、basedemo 亦无，按需求方口径写）
4. **videoview 按 SampleUI**：无 beepEnable；键 backgroundColor 0/caption/defaultVolume 5/id/loopPlayback false/position/rotation 0/touchable true/visible true
   - ⚠️ 这里的 `backgroundColor: 0` 是**官方原值、表示不透明黑**（视频/摄像头面必须有实黑底，basedemo videoview 2/2、cameraview 1/1 = 0）。**别把这个 0 推广到别的控件**：其他控件的底色「透明」是 **-1**，写 0 就是黑块（2026-09-20 M6 实测坑：checkbox/listview/digitalclock/pointer/circlebar 写 0 → 真机黑底）。判据见 knowledge 与 `workspace/references/kb/image-gen-standard.md` §7.6，门禁 `check_all` #24（`ui_tools/zero_color_audit.py` + `zero_color_allow.json`）。
5. **必选 = 扫描 SampleUI 每类型控件 100% 共有的字段（交集）**；值含默认全部显式

## 每类型必写键（注册表 v1.1 @ 2026-10-04）

⚠️ 本表由 scripts/gen_ui_schema_docs.py 从 ui_tools/ui_schema.json 生成，勿手改；改规范改注册表。
（必写键口径 = check_all #14 同源：注册表 required ∪ #14 兼容垫片，见 check_all._required_keys）

| 控件 | 必填键 | 默认值要点 |
|------|--------|-----------|
| textview | id/caption/position/alignment/colorTab/fontSize/touchable | alignment 36；fontSize 16；touchable false；visible true；bold false；italic false；rollEnable false；rollDirection 1；rollIntervalTime 150；rollStep 5；fontFamily 0；backgroundColor -1；alignment: 位模型：36=左中对齐常用；colorTab: color0 主文字色；text: 非空才写 |
| button | id/caption/position/alignment/colorTab/picTab/text/touchable | alignment 37；touchable true；visible true；longClickTimeOut -1；longClickIntervalTime -1；bold false；italic false；fontFamily 0；backgroundColor -1；rollEnable false；rollDirection 1；rollIntervalTime 150；rollStep 5；alignment: 位模型居中；picTab: {} 合法（无图也写键）；text: 文本内联 button（schema 支持），不要再叠 textview |
| window | id/caption/position/backgroundColor/hideTimeOut/modal/touchable/visible | backgroundColor -1；hideTimeOut -1；modal false；touchable false；visible true；modal: 弹窗 = modal true + visible false |
| edittext | id/caption/position/alignment/bgColorTab/bold/colorTab/fontSize/hintTextColor/text/textType | bold false；fontSize 16；textType 0；isPassword false；passwordChar "*"；beepEnable true；fontFamily 0；touchable true；rollEnable false；rollDirection 1；rollIntervalTime 150；rollStep 5；visible true；italic false；text: "" 合法；textType: 0/1 恒写；isPassword: 密码框（html2json 由 data-password 触发 |
| seekbar | id/caption/position/backgroundColor/backgroundPic/defProgress/max/orientation/progressPic/thumb/touchable/visible | backgroundColor -1；defProgress 0；max 100；orientation 0；visible true；position: height 决定滑块渲染高度；backgroundPic: 背景图路径；progressPic: 有效图 |
| listview | id/caption/position/autoRollback/backgroundColor/cols/cycleEnable/dragMaxDis/edgeEffect/hasScrollbar/rows/touchable/visible/orientation/colSpacing/rowSpacing/item | backgroundColor -1；cols 1；dragMaxDis 200；edgeEffect 0；hasScrollbar true；touchable true；visible true；orientation 0 |
| circlebar | id/caption/position/backgroundColor/clockwise/max/maxAngle/progressPic/progressPicPos/startAngle/textColor/textSize/textType/thumb/touchRange/touchable/unit/visible | backgroundColor -1；clockwise true；max 100；maxAngle 360；startAngle 0；textType 0；visible true；progressPic: 有效图按扇形裁剪显示进度；progressPicPos: 有效图显示位置尺寸（可小于控件做内环效果）；textType: 0 不绘制/1 数字/2 数字+unit |
| slidewindow | id/caption/position/backgroundColor/cols/fontSize/iconSize/items/padding/rollSpeed/rows/touchable/visible | rollSpeed 60；touchable true；visible true；iconSize: 图标尺寸 {width,height} |
| digitalclock | id/caption/position/backgroundColor/beat/clockColor/fontSize/format/touchable/visible | beat false；clockColor 16777215；format "HH:MM"；touchable false；visible true |
| qrcode | id/caption/position/backgroundColor/padding/touchable/visible | padding 10；touchable true；visible true；codeStr: 有值才写；padding: 恒写 10（经需求方口径） |
| videoview | id/caption/position/backgroundColor/defaultVolume/loopPlayback/rotation/touchable/visible | backgroundColor 0；defaultVolume 5；loopPlayback false；rotation 0；touchable true；visible true；backgroundColor: ⛔ 官方原值 0=不透明黑（视频面必须实黑底），勿推广到其他控件 |
| cameraview | id/caption/position/autoPreview/backgroundColor/cvbs/formatSize/mirror/touchable/visible | autoPreview true；backgroundColor 0；formatSize "640x480"；mirror 0；touchable false；visible true；backgroundColor: ⛔ 同 videoview：官方原值 0=实黑底 |
| painter | id/caption/position/backgroundColor/touchable/visible | touchable false；visible true |
| pointer | id/caption/position/animatable/backgroundColor/backgroundPic/clockwise/fixedPoint/pointerPic/pointerSize/rotateSpeed/rotationPoint/startAngle/touchable/visible | animatable true；clockwise true；rotateSpeed 1；startAngle 0；touchable false；visible true；backgroundPic: 背景图路径；fixedPoint: 指针固定点（相对指针图，可超界做游标环）；rotateSpeed: 动画实测配 500 |
| diagram | id/caption/position/backgroundColor/infos/region/touchable/visible/xAxisRange/yAxisRange | touchable true；visible true；region: 波形绘制区域（相对控件），通常=position；xAxisRange: 颠倒会左右镜像+刷新方向颠倒；yAxisRange: 颠倒上下镜像 |
| checkbox | id/caption/position/alignment/checked/colorTab/bgColorTab/backgroundColor/bold/fontSize/iconPosition/italic/text/touchable/textPosition/visible | checked false；bold false；fontSize 16；fontFamily 0；italic false；touchable true；visible true；text: 恒写 |
| radiogroup | id/caption/position/backgroundColor/touchable/visible/radiobuttons | touchable true；visible true |
| radiobutton | id/caption/position/alignment/checked/colorTab/bgColorTab/backgroundColor/bold/fontSize/italic/text/touchable/visible | checked false；bold false；fontSize 16；italic false；touchable true；visible true |
| pagewindow | id/caption/position/dragMaxDis/orientation/edgeEffect/rollSpeed | dragMaxDis 200；orientation 0；edgeEffect 1；rollSpeed 60 |
| scrollwindow | id/caption/position/dragMaxDis/orientation/edgeEffect | dragMaxDis 200；orientation 0；edgeEffect 1；touchable true；touchable: 滚动容器要接收触摸（实测显式 true） |
| imageanim | id/caption/position/loopCount/playFile | loopCount 0；loopCount: 0=无限循环；playFile: 只支持 .gif/.webp |
| slidetext | id/caption/position/touchable | touchable: IME 候选条专用 |

## 带子内容的子结构（SampleUI 1024x600 子结构 100% 键，双源验证）
### listview.item（SampleUI/basedemo 均 17 键 100%，无 id）
必写：caption/alignment/backgroundColor/bgColorTab/bold/colorTab/fontSize/italic/longClickIntervalTime/longClickTimeOut/picTab/**position**/text/touchable/visible/subItem
- ⚠️ **item.position 必写（2026-09-08）**，行高公式（basedemo 3 例 + SampleUI 验证）：
  **itemH = int(lv高 / rows) − rowSpacing；itemW = lv 宽；left/top = 0**
例：lv 300 高 rows6 rs2 → 48；164/4−5=36；437/3−5≈140；424/5−0=84；216x275 rows5 → 55
- 🎯 **除不尽的余数「是故意的」（2026-10-01）**：引擎按上式计算，余下的几个像素会**露出下一项的一小块**——
这是**有意设计**，让用户一眼知道「还能继续滑」。所以 **item 高不要求 `rows×(itemH+rowSpacing)` 恰好等于板高**，
也不要把「底部露出下一条」当成缺陷。
需求方给的算例：竖向 listview 高 100、rows=6、间隔 rowSpacing=5 → itemH = int(100/6)−5 = 16−5 = **11**
  （原文算例按“可用高 400”计：`(400/6)−5 = 61.66 → 61`，`61+5=66`，`66×6=396`，**余 4px 就是那截“可滑动提示”**）。
- ⚠️ 反向的错法才要拦：把 itemH **写成比公式大**（如公式 30 却写 50）→ 行被撑爆/列表被裁（**挤爆**）；
写成比公式小 → 每项底部多出空带。判据见 `check_all #37`。
- iconPosition/textPosition 布局键条件写（有图标/背景图设计时）；背景图/行底色按设计

### listview.subItem（SampleUI 19 键 / basedemo 18 键 100%）
必写（生成器输出 17 键）：id/caption/position/alignment/backgroundColor/bgColorTab/bold/colorTab/fontFamily 0/fontSize 16/italic/longClickIntervalTime -1/longClickTimeOut -1/picTab {}/text ""/touchable true/visible true
（iconPosition/textPosition 布局键条件写——HTML 子项自带 position 不需）

### diagram.infos[] 波形项（两源均 10 键 100%）
必写：caption/penColor/penWidth/step/style/eraseSpace/antialias/**visible true**/xScale/yScale

### slidewindow.items[] 图标项（SampleUI 3 键 / basedemo 6 键）
必写：colorTab/picTab/text（fontSize/fontFamily/padding 条件，basedemo 100% SampleUI 42% 从宽）

### radiogroup.radiobuttons[]（basedemo 23 键全字段）
必写折衷（生成器 14 键）：id/caption/position/alignment/checked/colorTab/bgColorTab/backgroundColor/bold/fontSize/italic/text/touchable/visible

## 双源复验结论（SampleUI-New vs basedemo-new_z20_1024_600）
| 结论 | 类型 |
|---|---|
| 双源一致（模板可靠） | seekbar 12 键全同、listview、diagram（infos 含 visible）、videoview/cameraview/pointer/digitalclock/qrcode/painter、edittext（17 键无 beepEnable）、item/subItem |
| SampleUI 无样例、basedemo 补齐 | pagewindow/scrollwindow（无 beepEnable + 嵌套页面 window）、checkbox（23 键）、radiogroup+radiobutton、imageanim（playFile）、slidetext（IME 从宽） |
| 版本差异说明 | window 在 basedemo（老 IDE ftu）仅 caption/id/position 3 键 → SampleUI 8 键为新 IDE 全量序列化；模板保留 SampleUI 8 键（缺省也兼容老引擎） |
| 结论 | 模板 = SampleUI-New 1024x600 100% 交集 + 需求方口径；basedemo 用于验证与补齐 |

## 相关
- html2json.py：生成器已按本表输出（含 item.position 自动算）；check_all.py #14 校验
- 历史省略式 json（IDE 手工/旧生成器）跑 check_all #14 会提示缺键，按本表补默认即可
- 检索边界：控件 json 字段以本文件 + knowledge/uicontrols/*-fields.md + 官方文档站为准
- ⚠️ **滑动/拖拽字段取值**（`dragMaxDis`/`edgeEffect`/`autoRollback`/`rollSpeed`，listview/scrollwindow/pagewindow/slidewindow 共用）：本表只定「必写 + 默认值」，**手感取值规范见 `knowledge/uicontrols/scroll-drag-interaction-spec.md`**（四个控件的 `dragMaxDis` 语义一致 = 越界拖拽上限，取手感值 50~200；**禁止填内容尺寸/列表高度**）
- ★ 循环选择器类控件（含时间列/钟面形态）：`knowledge/uicontrols/listview-wheel-picker.md`
  （行模板 `item.text:""`、装饰 `textview` 的必写字段与层序均以本表为准）
