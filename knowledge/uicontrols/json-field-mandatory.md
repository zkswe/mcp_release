# ⛔ json 字段全集显式化（每控件必写字段 v2.1，双源基准）

> 2026-09-08 沛哥定规。**背景**：带默认值字段若靠引擎缺省，不同 fui/easyui 版本默认处理可能不同 → 版本不匹配异常（touchable 为典型）。
> **规则**：生成 json 时每个控件输出本类型**必写字段全集（含默认值 -1/0/false/字号，均显式写）**，不做缺省声明；
> -1 = 0xFFFFFFFF 是有意义的显式值（非噪音）。写全对新引擎无害，且产物与新版 IDE 全量序列化格式兼容。
> **权威基准（沛哥指定）**：`projects/SampleUI-New/ui/1024x600`（42 json、新 IDE 全量序列化）——**每类型控件 100% 共有的字段 = 必选**；
> **交叉复验**：`projects/LearningProject/basedemo-new_z20_1024_600`（35 官方 Demo/44 json，ftu unpack 反解）。
> **落地**：check_all.py #14 按本表校验缺键（FAIL）；html2json.py 已按全集输出；手写 json 缺键照本表补默认。

## 沛哥 5 条口径（2026-09-08）
1. **beepEnable 不强制**：交互控件默认支持，废除「恒带 beepEnable:true」规范（两源 edittext/window 均证实非必写）
2. **touchable 交互控件显式 true**：button/listview/可拖 seekbar(有 thumb)/qrcode/videoview/diagram/subitem/slidewindow/circlebar；容器与纯显示显式 **false**（window/painter/textview/cameraview/digitalclock 主 false）
   - ⚠️ **例外：radiogroup 虽是容器，也必须 `touchable: true`**（2026-09-10 修正）。写 false 会让整组**收不到触摸、点了没反应**（单选组点不动）；生成器/手写 json 均按 true。详见 `uicontrols/touch-events.md`
3. **qrcode 恒写 padding:10**（各边默认 10；SampleUI 无 padding 键、basedemo 亦无，按沛哥口径写）
4. **videoview 按 SampleUI**：无 beepEnable；键 backgroundColor 0/caption/defaultVolume 5/id/loopPlayback false/position/rotation 0/touchable true/visible true
5. **必选 = 扫描 SampleUI 每类型控件 100% 共有的字段（交集）**；值含默认全部显式

## 每类型必写键（v2.1 最终表，与 check_all CTRL_FIELD_TEMPLATES 一致）
| 类型 | 必写键 | 默认值要点 |
|------|--------|-----------|
| textview | id/caption/position/alignment/colorTab/fontSize/touchable | fontSize 16；color0 16777215；alignment 36 主；touchable false 主；text 非空才写 |
| button | id/caption/position/alignment/colorTab/picTab/text/touchable | touchable true；picTab {} / text "" 合法（无图无字也写键）；alignment 37 |
| window | id/caption/position/backgroundColor/hideTimeOut/modal/touchable/visible | backgroundColor -1/hideTimeOut -1/modal false/touchable false/visible true（弹窗 modal true+visible false） |
| edittext | id/caption/position/alignment/bgColorTab/bold/colorTab/fontSize/hintTextColor/text/textType | bold false；textType 0/1 恒写；text "" 合法；fontSize 16；无 beepEnable |
| seekbar | id/caption/position/backgroundColor/backgroundPic/defProgress/max/orientation/progressPic/thumb/touchable/visible | max 100；defProgress 0；thumb 空 size 合法；可拖（有 thumb）touchable true、只读 false |
| listview | id/caption/position/autoRollback/backgroundColor/cols/cycleEnable/dragMaxDis/edgeEffect/hasScrollbar/rows/touchable/visible/orientation/colSpacing/rowSpacing/item | touchable true；hasScrollbar true；backgroundColor -1；item 见子结构 |
| circlebar | id/caption/position/backgroundColor/clockwise/max/maxAngle/progressPic/progressPicPos/startAngle/textColor/textSize/textType/thumb/touchRange/touchable/unit/visible | clockwise true；startAngle 0；backgroundPic/文本键按设计有才写 |
| slidewindow | id/caption/position/backgroundColor/cols/fontSize/iconSize/items/padding/rollSpeed/rows/touchable/visible | touchable true |
| digitalclock | id/caption/position/backgroundColor/beat/clockColor/fontSize/format/touchable/visible | beat false；clockColor 16777215；format "HH:MM" |
| qrcode | id/caption/position/backgroundColor/codeStr/padding/touchable/visible | padding 10；touchable true；codeStr 有值才写 |
| videoview | id/caption/position/backgroundColor/defaultVolume/loopPlayback/rotation/touchable/visible | 无 beepEnable；loopPlayback false；touchable true；defaultVolume 5 |
| cameraview | id/caption/position/autoPreview/backgroundColor/cvbs/formatSize/mirror/touchable/visible | autoPreview 默认 true；mirror 0；formatSize 640x480；touchable false |
| painter | id/caption/position/backgroundColor/touchable/visible | touchable false |
| pointer | id/caption/position/animatable/backgroundColor/backgroundPic/clockwise/fixedPoint/pointerPic/pointerSize/rotateSpeed/rotationPoint/startAngle/touchable/visible | rotateSpeed 1；startAngle 0；clockwise/animatable true；图/点位按设计有才写 |
| diagram | id/caption/position/backgroundColor/infos/region/touchable/visible/xAxisRange/yAxisRange | touchable true 主；region=position；infos[] 见子结构 |
| checkbox | id/caption/position/alignment/checked/colorTab/bgColorTab/backgroundColor/bold/fontSize/iconPosition/italic/text/touchable/textPosition/visible | basedemo 23 键全字段折衷；text 恒写 |
| radiogroup | id/caption/position/backgroundColor/touchable/visible/radiobuttons | **touchable true**（⚠️ 是「容器显式 false」通用口径的**例外**，2026-09-10 修正）；radiobuttons[] 子项见下 |
| radiobutton | id/caption/position/alignment/checked/colorTab/bgColorTab/backgroundColor/bold/fontSize/italic/text/touchable/visible | basedemo 23 键全字段折衷；checked false |
| pagewindow | id/caption/position/dragMaxDis/orientation/edgeEffect/rollSpeed | 200/0/1/60；SampleUI 无样例，basedemo+demo 验证（无 beepEnable） |
| scrollwindow | id/caption/position/dragMaxDis/orientation/edgeEffect | 200/0/1；同上（无 beepEnable） |
| imageanim | id/caption/position/loopCount/playFile | playFile 必写（无 GIF 动图无意义）；loopCount 0 无限 |
| slidetext | id/caption/position/touchable | IME 候选条专用，从宽（basedemo 实为 19 键全字段） |

## 带子内容的子结构（SampleUI 1024x600 子结构 100% 键，双源验证）
### listview.item（SampleUI/basedemo 均 17 键 100%，无 id）
必写：caption/alignment/backgroundColor/bgColorTab/bold/colorTab/fontSize/italic/longClickIntervalTime/longClickTimeOut/picTab/**position**/text/touchable/visible/subItem
- ⚠️ **item.position 必写（沛哥 2026-09-08）**，行高公式（basedemo 3 例 + SampleUI 验证）：
  **itemH = int(lv高 / rows) − rowSpacing；itemW = lv 宽；left/top = 0**
  例：lv 300 高 rows6 rs2 → 48；164/4−5=36；437/3−5≈140；424/5−0=84；216x275 rows5 → 55
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
| 结论 | 模板 = SampleUI-New 1024x600 100% 交集 + 沛哥口径；basedemo 用于验证与补齐 |

## 相关
- html2json.py：生成器已按本表输出（含 item.position 自动算）；check_all.py #14 校验
- 历史省略式 json（IDE 手工/旧生成器）跑 check_all #14 会提示缺键，按本表补默认即可
- 检索边界：控件 json 字段以本文件 + knowledge/uicontrols/*-fields.md + 官方文档站为准
- ⚠️ **滑动/拖拽字段取值**（`dragMaxDis`/`edgeEffect`/`autoRollback`/`rollSpeed`，listview/scrollwindow/pagewindow/slidewindow 共用）：本表只定「必写 + 默认值」，**手感取值规范见 `scroll-drag-interaction-spec.md`**（listview 的 dragMaxDis 填手感值 ≤ 一行高，禁止填列表高度）
- ★ 循环选择器类控件（含时间列/钟面形态）：`listview-wheel-picker.md`
  （行模板 `item.text:""`、装饰 `textview` 的必写字段与层序均以本表为准）
