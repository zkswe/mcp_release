# HTML 原型 → json 规范速查（HTML_SUBSET）

> 检索导引：写「受限 HTML 原型 / 原型转 json / 控件映射 / data-* 属性 / data-icon 图标 / CSS 效果转图 / JS 交互稿」时命中。
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
| `div.card` / `window` / `panel` | window 容器（子控件相对坐标） |
| `div.modal` / `dialog` | 弹窗（modal + 隐藏） |
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
- **命名**：`data-caption` 指定控件名（C 标识符）；缺省自动 `TextView1` / `Button1` …
- **自备图**：`data-pic`（引用自己切好的 PNG / .9.png / 序列帧 GIF）

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
