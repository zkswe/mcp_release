---
id: devflow-html-subset-quickref
title: HTML 原型 → json 规范速查（HTML_SUBSET）
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [长尾在这里, 实现规范, 工具开发用, HTML_SUBSET, md, 内容以本页为准]
evidence: []
---
# HTML 原型 → json 规范速查（HTML_SUBSET）

> 检索导引：写「受限 HTML 原型 / 原型转 json / 控件映射 / data-* 属性 / data-touchable 不生效 / data-icon 图标 / CSS 效果转图 / JS 交互稿 / data-bgpic / div.text 底图 / backgroundPic 没生成 / 底图没画出来 / 卡片白卡看不到 / 容器默认可见盖住页面」时命中。
> 用途：`flythings_html_to_json` 的完整口径（该工具 docstring 只保留要点，长尾在这里）。
> 实现规范（工具开发用）：仓库 `ui_tools/HTML_SUBSET.md`；本页是 AI 生成原型时的口径，内容以本页为准。

## 1. 结构（根节点）

`<div class="screen" data-res="WxH" data-bg="#RRGGBB">` 为根。

- 也可用 `data-width` / `data-height` 或内联 `style` 宽高替代 `data-res`
- `data-background` 与 `data-bg` 互为别名
- 缺省分辨率 480x272；建议显式传 `res` 参数（如 `"800x480"`）或写 `data-res`

## 2. 控件映射

| HTML | FlyThings 控件 |
|------|----------------|
| `div.text` / `p` / `span` | textview |
| `div.btn` / `button` | button |
| `div.input` / `input` | edittext |
| `div.bar` / `seekbar` | seekbar |
| `div.card` / `window` / `panel` / `win` | window 容器（子控件相对坐标；**默认可见**，见下表注） |
| `div.modal` / `dialog` / `popup` | 弹窗（modal + **默认隐藏**） |

⚠️ **容器窗口的初始可见性不同**（代码注释：弹窗 modal 默认隐藏；普通卡片/容器窗口**默认可见**）：
`div.window` / `card` / `panel`（非 modal）生成出来就是 `visible=true`。用它们做「第二个页面」时，
**它一生成就在屏幕上、会盖住后面定义的同层内容**，必须靠逻辑侧 `hideWnd()` 收起来。
（案例真根因：一个非 modal window 忘了 hide → 表单页永远压在最上面 + 吃掉下半屏点击，
一度被误判成「触摸注入坏了」。）
| `div.list` / `listview` | listview（子项见 §3） |
| `div.checkbox` | checkbox |
| `div.radio` / `radiogroup` | radiogroup |
| `div.icon` / `img` | 图标 textview |

## 3. listview 子项

子控件直接写在 list 容器内即生成 subItem；若用 `<div class="item">` 包裹，转换器会展开包裹层、
逐个生成 subItem（不会吞掉内部控件）。

## 4. 属性

- **定位**：`data-x` / `data-y` / `data-w` / `data-h`（或 `data-left/top/width/height`、`style` left/top/width/height）
- **字号**：`data-fs` / `data-font-size` / `data-fontSize` / 内联 `style="font-size:NNpx"` 都认
- **颜色**：`data-color` 文字色；`data-bg` 或 `data-background` 背景色（textview/button/edittext 均支持背景）
  - ✅ **纯黑 `#000000` 已修**（A2，2026-09-27）：转换器改成按「属性是否出现」判定未设置，
    `data-color` / `data-color2` / `data-bg` / `data-bg2` / `data-text-bg` / `data-hint-color`
    共 16 处不再走 `to_dec(...) or 默认值`。**老工程里「纯黑写 `#010101`」的绕过写法继续有效**（
    `#010101` 也是纯黑），不必回改。
- **初始隐藏**：`data-visible="false"`（A5，2026-09-27 新增）—— 控件 / 容器（window、listview 与 subItem）
  都直通 json 的 `visible`；缺省不写 = 保持各类型默认（普通 window 默认可见、modal 默认隐藏）。
  （旧版不认该属性 → 只能运行时代码 patch，且控件名要在生成器与 patch 两处同步，漏一处即静默失败。）
- **反性**：`data-visible` 之外**没有**别的新式属性；`data-touchable` 仍**不解析**（见下条）。
- **命名**：`data-caption` 指定控件名（C 标识符）；缺省自动 `TextView1` / `Button1` …
- **圆角外底色**（A6，2026-09-27 修）：有图控件（`data-pic`/`data-bgpic`/CSS 效果图/图标）的
  **四角透出的是 `bgColorTab`**。旧版「有图一律 pop 底色」→ 四角露窗口黑底（坐卡片上就是「图标角落发黑」）。
  现口径：**`data-bg` 优先 > 最近祖先容器底色 > 引擎缺省（并在 warnings 里告警）**。
  ⚠️ `bgColorTab` 只管**最外 1px**；圆角里侧 4~5px 那圈是图里的像素，补色救不回来 →
  坐卡片的底板要么 1:1 普通 PNG + 圆角外烘容器色，要么整张图在出图侧就烘好底色。
- ⚠️ **`data-touchable` 不解析**（2026-09-17 实测 + 代码核对）：转换器**根本没读**这个属性
  —— `button` 恒 `touchable:true`、`textview` 恒 `false`、`window` 也不解析。
  想**真禁用**某个控件、或让容器按你要的语义「吸收 / 穿透」点击，只能落到 **json**：
  `patch_json` / `ui_edit_apply` 改 `touchable`，或运行期 `setTouchable()` / `setTouchPass()`
  （语义与坑见 `uicontrols/touch-events.md`）。
- **自备图**：`data-pic`（引用自己切好的 PNG / .9.png / 序列帧 GIF）
- **静默提醒**（A1/A8，2026-09-27 修）：转换器**不再静默丢改动** —— 返回体 `warnings[]` 会给出
  「丢字符（emoji/黑名单字）」「有图控件无圆角外底色」「文本最小宽超出容器」等条目；
  `controls` / `controlsTopLevel` / `controlsNested` 三个计数**含嵌套控件**（A7 修，2026-09-27）。

## 4.1 三张对照表（属性直通 / 丢弃 / 默认值）

> A8（2026-09-27）：这三张表以前只能靠真机反推，现补上；每行「行为」一栏的 `warn` 表示
> 转换期会在返回体 `warnings[]` 里给出提示。

### ① 直通表（写了就用，1:1 落到 json）

| HTML 属性 | 落地字段 | 适用 | 备注 |
|---|---|---|---|
| `data-x/y/w/h`（别名 `data-left/top/width/height`、`style`） | `position` | 全部 | 取值单位 px |
| `data-res` / `data-width`+`data-height` | `resolution` | `.screen` | 缺省 480x272 |
| `data-bg` / `data-background` / `style.background` | `bgColorTab.color0` / `backgroundColor` | 全部 | 纯黑现已正确（A2） |
| `data-color` | `colorTab.color0` | 文字类 | 同上 |
| `data-color2` / `data-bg2` | `colorTab.color2` / `bgColorTab.color2` | 多态控件 | 选中态 |
| `data-fs` / `data-font-size` / `data-fontSize` | `fontSize` | 文字类 | 缺省 16 |
| `data-caption` | `caption` | 全部 | 非 C 标识符字符转 `_` |
| `data-pic` / `data-pic0..pic4` | `picTab` | button/radiobutton/checkbox | 多态图 |
| `data-bgpic` / `data-background-pic` | `backgroundPic` | textview/button/window | 有图后走「圆角外底色」口径 |
| `data-visible` | `visible` | 全部（含 subItem/window） | **A5 新增** |
| `data-text-bg` | `textBgColor` | slidetext | 纯黑现已正确（A2） |
| `data-hint-color` / `data-hint` | `hintTextColor` / `hintText` | edittext | 同上 |
| `data-password` / `data-password-char` / `data-num` | `isPassword` / `passwordChar` / `textType` | edittext | |
| `data-icon` / `class="icon-xxx"` | 自动出 PNG → `picTab`/`backgroundPic` | button/textview/subItem | 图标优先定规 |
| `data-icon-w/-h/-pad` | `iconPosition` | button | |
| `data-cols` / `data-rows` / `data-row-spacing` | listview 行高/列宽公式 | listview | 行高 = 高/rows − rowSpacing |
| `data-charset` | `charsetTab` | subItem | JSON 字符串 |
| `data-modal` / `class="modal"` | `modal`+`visible:false` | window | |
| `data-hide-timeout` / `data-topmost` | `hideTimeOut` / `topmost` | window / 根 | |
| `data-rotate` 类平台专有 | 对应字段 | 见平台 kb | 不逐一列 |

### ② 丢弃表（写了不生效，且**不会报错**）

| HTML 属性 / 内容 | 行为 | 替代写法 |
|---|---|---|
| `data-touchable` | **不解析**（转换器没读）→ 恒按类型默认 | 改 json 或运行期 `setTouchable/setTouchPass` |
| emoji / 黑名单特殊字符（`⌫ ℃ ■ ● ‹ ＋ – … → ★ ◆ ▶ ▷ ①` 等） | **整字丢弃** → 现在 `warn` 记账（A1 修） | 改图片素材或换字符（铁律 1） |
| 字库缺字形的其它字符 | 字库层整字消失（转换器不拦） | 同上 |
| 未知 `class` / 未知标签 | 兑底成 textview（`warn`） | 用 §2 映射表里的 class |
| `style` 里除 left/top/width/height/font-size/background 外的声明 | 不解析 | 用 CSS 效果转图（渐变/阴影/圆角） |
| 嵌套 `.screen` | 不展开，`warn` | 改为同屏内 window |

### ③ 默认值表（不写就长这样，显式写才覆盖）

| 字段 | 默认值 | 说明 |
|---|---|---|
| `fontSize` | 16（textview/button/edittext/subItem） | |
| `colorTab.color0` | `0xEEF2F6`（文字）/ edittext `0` | 浅色字 |
| `bgColorTab.color0` | button：无 `data-bg` 且无文字时**不写**；有则 `0x374457`；window `-1`；subItem `-1` | 透明热区不铺底 |
| `alignment` | textview 36（左）/ button・subItem 37（中） | |
| `touchable` | button/subItem/可拖 seekbar/radiogroup/qrcode/videoview `true`；textview/window/seekbar `false`；**edittext `true`（A4 修，2026-09-27）** | 交互控件必须 true |
| `visible` | 全部 `true`；`modal` 窗口 `false` | A5 起可被 `data-visible` 覆盖 |
| `backgroundColor` | `-1`（video/cameraview 为 0） | 0 = 不透明黑，别当透明用 |
| `controls` 计数 | 含嵌套（A7 修）；另给 `controlsTopLevel` / `controlsNested` | |
  - ✅ **`div.text` 上的 `data-bgpic` 已原生支持**（**v0.27.90-open 起**）：转换器把 `data-bgpic`
    正常落成该节点的 `backgroundPic`（与 button / window / seekbar / circlebar 等分支同口径：
    裸文件名补 `images/` 前缀，相对 resources 目录；有图就**不再写背景色**，与 button 的
    「图片按钮不放底色」同规则，避免透明角图透出底色）。
    - **历史**（v0.27.90 之前）：textview 分支**不读**这个属性 → JSON 里那节点**没有 `backgroundPic`**
      （同一份 JSON 里 seekbar 的 textview 却有，极易看成「怎么别人就好」），现象是「卡片/底图
      压根没画出来」（案例：弹窗打开、变暗也对，就是**看不到白卡**）；当时靠 `patch_json` 反查
      HTML 按 caption 回填。
    - **旧工程可照旧保留 `patch_json` 兜底** —— 现在它是**幂等**的（转换器已写出同样的值，兜底
      覆写同值 / 只补缺的，重跑不产生差异）；不必为了这条专门改老工程。
    - 实测口径（TDesign 迁移案例双平台）：HTML 里 `class="text"` + `data-bgpic` 共 87 个节点，
      旧转换器直接落地 0/87（全靠兜底），新转换器 87/87，两条路径的 `caption→backgroundPic`
      **语义等价（110 条全等）**。
  - 注：`data-bg` / `data-background` 是**背景色**，不是图；要图不能用它们替代。

## 5. 图标优先（沛哥 2026-09-03 定规，生成 UI 时必守）

常用操作（返回 / 播放 / 暂停 / 上一首 / 下一首 / 设置 / 搜索 / 删除 / 刷新 / 确认 / 关闭 / 加减 /
音量 / 主页 / 菜单等）**必须用图标表达，禁止用「按钮 + 文字」糊弄**。

写法：

```html
<!-- ① 图标按钮：自动出 normal + pressed 两态 picTab -->
<div class="btn" data-icon="play" data-x="10" data-y="10" data-w="48" data-h="48" data-caption="BtnPlay"></div>
<!-- ② 纯展示图标：自动出 backgroundPic -->
<div class="icon" data-icon="wifi" data-x="10" data-y="70" data-w="32" data-h="32"></div>
<!-- 等价写法（iconfont class） -->
<i class="iconfont icon-volume"></i>
```

- 转换器自动生成 iconfont 风格矢量线框 PNG；控件建议正方形
- `data-color` 配线框颜色（#RRGGBB，缺省浅灰蓝）
- 未收录图标名会给 warning
- **46 个内置图标词**：back / forward / up / down / close / check / plus / minus / menu / more / search /
  home / list / play / pause / stop / prev / next / power / volume / mute / delete / edit / share /
  download / upload / user / lock / info / warning / camera / clock / calendar / bell / mic /
  location / mail / eye / video / phone / settings / refresh / wifi / bluetooth / heart / star
  （中文别名如 `data-icon="播放"` / `"返回"` 也认）
- 需要自备图时仍用 `data-pic`

## 6. 文本与布局铁律

- Z 序 = 书写顺序（弹窗写最后）
- 文本只用**汉字 + ASCII + 基础符号**（`/ % # - _ 空格`），**禁 emoji**（设备字库是裁剪字库）
- ⚠️ **HTML 里的换行/缩进会被折叠成空格**（不是 `\n`）：要多行文案就**拆成多个 textview**
  （案例实测：在文本里写 `\n` 会被按整串算最小尺寸，撞 `check_all` 第 13 项最小尺寸判定）
- 进度条用 `div.bar`；输入框用 `div.input`（系统键盘）
- 颜色一律 `#RRGGBB` 6 位

## 7. CSS 效果：一律转图片 + 控件组合

HTML 原型允许任意效果（emoji / iconfont / CSS 渐变阴影圆角 / 粒子 / 3D 动效），
但 **FlyThings 无 CSS 引擎**，转 json 时效果一律转图片 + 控件组合实现：

| 效果 | 落地方式 |
|------|----------|
| 渐变 / 复杂背景 / 阴影 / 描边 | 切 PNG 或 .9.png，`data-pic` 引用 |
| emoji / iconfont | 转 PNG 图标 |
| loading / 旋转 / 粒子动效 | 序列帧 PNG 或 GIF（imageanim 动图控件，循环次数 ≤0 = 无限循环） |
| 按钮两态 | normal + pressed（`_p` 后缀）→ `picTab{pic0,pic1}` |

### 7.1 自动转图（2026-08-29 起，2026-09-01 路径修复）

style 里出现 `linear-gradient` / `box-shadow` / `border-radius` / `animation` 等效果时**自动生成图片资源**：

- 渐变 → `grad_*.png`（backgroundPic）
- 阴影 + 圆角 → `shadow_*.png` / `gradshadow_*.png`（渐变阴影自动合成）
- emoji 文本 → `emoji_*.png` 图标
- `class="loading"` / `spinner` 或 `animation: spin` → `loading_*.gif`（12 帧）+ imageanim 控件
  （warning 提示 logic.cc 里 `mXXXPtr->play()`）
- 图片输出到 `<项目>/resources/images/`（`output_json` 在 `<项目>/ui/` 下时自动识别；
  json 引用路径 `images/xxx.png` 相对 resources 目录，与设备加载一致；
  非 ui/ 目录结构回退 json 同目录 `images/` 并警告）
- 返回 `generatedAssets` 计数 + `assetDir` 实际输出目录

⚠️ **图片一律由转换器自动转图（内置抗锯齿管线），禁止 AI 自绘 1x 直画 png，
或用外部生图能力直出小图交付**（1x 二值 alpha / 大图缩小边缘必锯齿）。
防锯齿铁律见 `ui-asset-rules.md`（本目录）。

**出图档位（v0.27.76 起）**：CSS 效果出图**一律走 SS（`ss=4` = 每像素 16 子采样）**，不再保留
1x + α 羽化那条路 —— 药丸（`border-radius:999px`）/ 正圆（`50%`）/ 圆钮 这类强曲率形状
过去会有肉眼可见锯齿（药丸实测边界误差 mean 35.4/255 → 现在 5.3）。
`border-radius` 现在认 `px` / 无单位 / **`%`**（`50%` → 正圆；旧实现只认 px，会出方角）。

### 7.2 转不了的效果（会提示切图）

`radial-gradient` / `text-shadow` / `transform` / `filter` / `opacity` / `transition` 不会自动烘焙，
warning 会要求切图后用 `data-pic` 引用。

## 8. JS 交互稿（2026-08-29 沛哥建议）

第一套 HTML 效果稿建议直接写 JS 交互——点击弹窗 / 页面切换 / tab 切换 / 列表滚动 / 数据模拟 /
动效触发等，让客户在浏览器里直接「点得动」，前期效果确认和修改效率翻倍。

- 转换器**自动忽略 `<script>` 标签和 `onclick` 等交互属性**（实测验证）
- JS 只服务于浏览器预览确认，不转 json
- FlyThings 端交互逻辑由 `logic.cc` 实现（json 布局 + 回调）

## 9. 工作流红线

1. 客户发说明书 / 参考照片 / 需求文档时**不能直接转 json**：先引导分析提炼 UI 需求清单 → 用户确认 →
   再写受限 HTML → 才调转换工具
2. 转换后**必须先出预览稿给用户确认**（只交付 .preview.html 文件本身，不生成图片/截图），
   确认 OK 后才允许 `fui pack` / 写逻辑 / 交付（**未确认禁止开工**）
3. `output_json` 缺省为 html 同名 `.json`；`res` 可覆盖分辨率

## 10. 相关

- 图片资源铁律与 PNG 抗锯齿管线 → `ui-asset-rules.md`
- json 字段全集/层级规则 → `uicontrols/json-field-mandatory.md`、`uicontrols/json-layer-rules.md`
- 布局产物核对（图尺寸 == 控件盒）→ `flythings_verify_assets` / check_all 第 17 项
  （⚠️ 只管 json **声明**的图；运行期 `setBackgroundPic` 的**字面量**图由 check_all 第 20 项核
  （v0.27.90 起），运行时拼接的路径静态无解 → `uicontrols/text-box-height-rule.md` §4/§5）
- 设计令牌漂移（`DESIGN.md` 令牌 vs json 色值/字号）→ check_all 第 18 项
- 归一化、转图、补丁的完整链路 → `ftu-json-pipeline.md`
