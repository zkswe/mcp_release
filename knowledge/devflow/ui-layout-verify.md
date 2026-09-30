---
id: devflow-ui-layout-verify
title: UI 布局可视化编辑与像素验收（json 为源 · 拖拽微调 · 0 token 校验）
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [⚠️ v0, 27, action=]
evidence: []
---
# UI 布局可视化编辑与像素验收（json 为源 · 拖拽微调 · 0 token 校验）

> 检索导引：问「布局位置不对 / 想拖控件微调 / 图片与控件尺寸对不上（含 thumb.size）/ 要像素回归对比 / 多页工程预览怎么切页 / **改完布局怎么给客户（需求方）确认 / 客户确认稿 / 反复改布局浪费时间**」→ 本文（三段式验收总纲）；三个 action 的细节见 `knowledge/devflow/ui-editor-usage.md`。
> ⚠️ v0.27.37 起三个 op 合并为 `flythings_ui_visual(action=...)`：`"editor"` / `"edit_apply"` / `"diff"`

> 命中条件：UI 布局做完需要"看得见、拖得动、验得了"时——用户说布局位置不对 / 图标锯齿 /
> 切图不对 / 预览丢图 / 想直接改文字和属性 / 要验收或回归对比 / 不想靠嘴描述"往左一点" /
> **图片与控件尺寸对不上（含滑块 thumb.size）**。
> 工具：`flythings_ui_visual(action="editor")`（出可拖拽编辑器）→ `flythings_ui_visual(action="edit_apply")`（写回 + pack ftu）→
> `flythings_ui_visual(action="diff")`（像素 diff）。

## 0. 确认闸门（改完布局 → 出确认稿 → 需求方确认 → 才 pack / 推真机）

> 2026-09-30 补（钟工 SmartPanel 检讨：UI 控件布局位置**多次来回对齐**，过程中没提醒用**可分享的
> HTML 版**跟客户确认 → 在“改 json → 编译 → 推真机 → 目视”上反复烧时间）。**这条是流程红线**，不是可选优化。

| 环节 | 做什么 | 工具 |
|---|---|---|
| 改前/改中 | 出**可拖拽编辑器**给自己或用户微调（本地静态页；拖完复制变更 JSON 回写） | `flythings_ui_visual(action="editor")` |
| **改完（关键）** | 出**客户确认稿**：单文件 `.confirm.html`（图内联、手机可打开/可转发），带「标注」开关看控件名/尺寸/坐标 | `flythings_ui_preview(target=…, for_customer=True)` |
| 确认后 | 才 `fui pack` / `edit_apply(pack=True)` / 推真机 / 写逻辑 | — |
| 回归 | 真机截图 + 像素 diff / 基线比对（**真机像素才是最终真相**） | `device_screenshot` + `ui_visual(diff/baseline)` |

- `flythings_ui_visual(action="edit_apply")` 与 `flythings_fui_pack` 的返回体带 **`confirmNeeded` /
  `confirmHint`**：项目里没有比本次改动**更新**的确认稿（`.confirm.html` / `.preview.html` /
  `_edit/*.edit.html`）时会提示先出确认稿（**只提醒、不阻塞**）。
- **多轮沟通就用确认稿**：客户指着标注说「这个按钮往右 20px」→ 改完**重出确认稿**再确认；
  不要直接推真机让他看屏（一次推机 = 编译 + 推送 + 人工目视，成本高一个量级）。
- 生成物是**近似渲染**（字体度量 / 9-patch 拉伸与设备有差）→ **最终验收仍需真机像素**（§2 三段式）。

## 1. 铁律：json 是唯一真相

设备加载的是 **ftu**，而 ftu 由 **json** pack 出来 → **json 是唯一数据源**。
所以预览与编辑器都必须**从 json 渲染**：手写 HTML 原型等于第二份真相，CSS 盒模型、字体度量、
行内基线跟设备 Canvas 是两套规则，必然漂移。

单向链路（不要逆向）：

```
HTML 交互原型 → flythings_html_to_json → ui/*.json（唯一源）
                                        ├─ flythings_ui_preview / flythings_ui_visual(action="editor")（看/改）
                                        └─ flythings_fui_pack → .ftu → 设备
```

⚠️ **json2html 预览也只是"近似渲染"**（字体度量、裁剪字库、九宫格拉伸、换行都是模拟层）。
**像素级真相只有一条路：pack 后在真机截图。**

## 2. 三段式验收（各管一段）

| 段 | 手段 | 成本 | 用途 |
|----|------|------|------|
| 1 | `flythings_ui_preview` / `flythings_ui_visual(action="editor")` | 秒级、0 token | 看结构、相对关系，确认交互 |
| 2 | `flythings_build_ui_flow` 推真机 + **`flythings_device_screenshot` 抓屏** | 一次编译 + 几秒 | 像素真相，最终验收 |
| 3 | `flythings_ui_visual(action="diff")` 对比两张截图 | 0 token | 回归/验收，差异可视化 |

## 2-1 真机截图怎么拿（`flythings_device_screenshot`，一行搞定）

⚠️ **要设备上的画面，直接调这个工具，不要自己手搓 adb / dd / cat /sys/class/graphics**。
设备侧探测（有没有 screencap、busybox 在哪、fb 是几 bpp、要不要按 pan 偏移）工具内部全做完了，
而且踩过的坑都在里面；手搓的结果往往是**抓到旧帧**或者**等几分钟传不完**。

```
flythings_device_screenshot()                       # 默认：当前设备 → screenshots/device_600x1600_<时间>.png
flythings_device_screenshot(scale=0.5)             # 长宽各半，省 AI token
flythings_device_screenshot(fmt='jpg', quality=85) # jpg / bmp
flythings_device_screenshot(device='<设备IP>:5555')  # 多设备指定
flythings_device_screenshot(pixel='rgba')          # 颜色红蓝互换时
flythings_device_screenshot(rotate='auto')         # 缺省值：按**项目工程** EasyUI.cfg 的 rotateScreen 转（出来就是正立的）
flythings_device_screenshot(crop='auto')           # 按 disp 图层 frame 裁出「项目逻辑分辨率」区域（非全屏图层唯一时）
```

典型用法（**回归验收**，0 token 对比）：

```
1. 改前：flythings_device_screenshot(out='before.png')
2. 改代码 → flythings_build_ui_flow(project_root, with_launch=True) 推真机
3. 改后：flythings_device_screenshot(out='after.png')
4. flythings_ui_visual(action="diff", image_a="before.png", image_b="after.png")   # 差异清单 + 标注图
5. 只看某块差异的语义时，才把差异区小图裁出来给视觉模型
```

参数：`device, out, fmt(png/jpg/bmp), scale, quality, fb, pixel, width, height, offset_y, flip, rotate, crop, name, timeout`；
返回 `{success, path, width, height, format, sizeBytes, device, method, screenInfo{...offsetY,pan,rotate,rotateScreen,rotateTouch}, uiLayer, pixelOrder, rotateDeg, rotateSource, crop, readHint}`。
调完把 **path** 交给看图能力，**不要把 raw/整文件丢给模型**。

### 2-1-1 取图方向/角度：读**项目工程**的配置，不要猜（❗踩过坑）

旋转/取图角度口径见 `knowledge/devflow/package-properties-easyui-cfg.md` §9（唯一来源 = 工程 `EasyUI.cfg` 的
`rotateScreen` / `rotateTouch`；工具 `rotate='auto'`（缺省）读它，返回值 `rotateSource` 可自证）。

设备侧实现要点（AI 不需要重做，但排障要懂）：

- 设备 rootfs 多为裁剪版：**没有 screencap / dd / head**，`adb exec-out` 也可能不通（patched adbd）；
  链路 = 设备侧 `busybox dd if=<fb> bs=<stride> skip=<panY> count=<h> | busybox gzip -1 > /tmp/x` + `adb pull`。
  裸 raw 一大就慢（600×1600×4≈7.7MB，WiFi 上几分钟）；gzip 后 ~37KB、0.3 秒。设备上没 busybox 会自动退化全量 cat（会提示先 push 一个 busybox）。
- fb 参数问 sysfs：`modes`(可见分辨率) / `virtual_size`(可能是 2 倍 OVERALLOC) / `stride` / `bits_per_pixel`；**必须按 stride 逐行取**。
- **双缓冲页翻转**：读 `/sys/class/graphics/fb0/pan`（如 `0,1600`）按 yoffset 抓，否则抓到的是**上一帧**（旧画面也可能是完整 UI，肉眼难发现）；工具已在抓后二次确认 pan 未变。
- 32bpp 内存序 BGRA（小端 ARGB8888）；颜色反了就 `pixel='rgba'`。

## 2-2 多页工程的预览怎么切页（整屏 window + `showWnd()` 架构，v0.27.35 起）

⚠️ **背景（AI 实测反馈过的失效场景）**：FlyThings 常见写法是「多个**整屏 window** 叠在同一页，
logic.cc 里用 `showWnd()/hideWnd()` 切页」（弹窗、设置页、二级页都这么干）。旧版预览把所有
`visible:false` 的控件一律 `display:none` → **客户确认稿只能看到首屏**，看不到的页面等于没交付。
现在预览稿自带切页能力，看到的是**全部页面**：

| 能力 | 用法 | 说明 |
|------|------|------|
| 页面切换条 | 预览页顶部页签 | 列出**全部整屏 window** 的 caption；点页签 = 显示该页、隐藏其余整屏窗口 |
| 默认页 | 自动 | = json 里**首个 `visible!=false` 的整屏窗口**（与 logic.cc 首屏对齐，不用手点） |
| hash 直达 | `main.preview.html#window__29`（也认简写 `#29`） | **给客户发某一张页面的链接**就用这个 |
| 「显示隐藏」 | 顶部开关 | `visible:false` 的控件/窗口以 35% 透明 + 橙色虚线**幽灵框**叠显（与编辑器 `.ed-ghost` 同一行为） |
| 项目页面行 | 自动（同项目多 json 时） | 在多个 `.preview.html` 之间跳转；单文件模式只链已生成的邻居，不出死链接 |
| 翻页键 | ← / → | 上一页 / 下一页 |

**「整屏窗口」怎么判定**：顶层（`depth==0`）window 且 `width/height ≥ resolution − 4px`。
**只在「≥2 个整屏窗口 / 存在 `visible:false` 控件 / 同项目多 json」时才出条** ——
单页无隐藏的工程预览**零变化**，不会多出一行 UI。

**边界**：

- 切页条只在**预览稿**（`*.preview.html`）里；编辑器（`*.edit.html`）不注入，保留自己的控件列表 + ghost。
- 半屏窗口、弹窗（如 400×200）**不算页面**，它们归「显示隐藏」开关管。
- 预览仍是**近似渲染**（第 1 节铁律）：切页只解决「看得到哪一页」，像素真相还得真机截图。

## 3. 可视化编辑器（`flythings_ui_visual(action="editor")`）

每个 `ui/*.json` → `<项目>/ui/_edit/<name>.edit.html`：**单文件、图片 base64 内联、双击即用**，
不需要装环境、不需要起服务。ui 目录递归扫描（多分辨率子目录也能出）。

页面操作：

| 操作 | 效果 |
|------|------|
| 点控件 / 悬停 | 亮蓝框提示 → 点击选中（绿框 + 8 个手柄） |
| 拖动 / 拖手柄 | 移动 / 缩放（整数像素，吸附网格 1/2/5/10） |
| 方向键 | 1px（Shift 10px；Alt 强制 1px；按住 Alt 拖动临时关吸附） |
| **Alt + 点** | **穿透选中下层控件**（专治全屏透明 button 压住其它控件） |
| 选中框左上 **✥ 绿块** | 拖动 = 移动当前选中控件，**被遮罩压住也能拖** |
| 控件列表 | 可搜 key / caption / 坐标，点一行即选中并滚动定位（被遮挡或隐藏的控件从这里选） |
| 「显示隐藏」 | 把 `visible:false` 的弹窗（modal 类）显示成虚线幽灵框，摆完位再关掉 |
| 深链接 | `<name>.edit.html#button__2`（嵌套用 `#window__1%2Ftextview__3`）打开即选中 |
| Ctrl+Z / Ctrl+Y | 撤销 / 重做 |

**属性栏（该控件的全部字段，改完画布即时生效）**：按控件原始 json 动态生成，不是写死几个——

- `text`（多行框，Ctrl+Enter 生效）、`fontSize`、`alignment`、`caption`
- `colorTab.color0` / `backgroundColor` 等颜色：颜色拾取器 + 十进制数值双份
- `backgroundPic` / `picTab.pic0~pic4`（中文状态名：**正常 / 按下 / 选中 / 选中按下 / 无效**）
- `visible` / `touchable` / `bold` / `italic` 等布尔项
- 嵌套结构（`iconPosition`、`textPosition`、`thumb`）自动展开成子行；数组类（listview `item`、
  `charsetTab`）给 JSON 编辑框，失焦校验
- ⚠️ **`id` 只读**：由 IDE 生成，改了会与 IDE 自动生成的 mainActivity 代码对不上

**内置预检（红/黄标，省一轮沟通）**：

| 级别 | 触发条件 | 说明 |
|------|----------|------|
| 红 | 图片尺寸 > 控件尺寸 | 设备不缩放普通 PNG，会被裁切/错位 |
| 红 | 自动生成 thumb 图 != `thumb.size`（v0.27.75） | 滑块自有尺寸子盒对不上 → 真机上滑块与轨道错位 |
| 黄 | 大控件（>100px）配小图 | 会留边或拉糊 |
| 黄 | 文本估算宽度 > 控件宽 × 1.35，或字号 > 控件高 | 设备端会裁字 |

只校验“按控件尺寸画”的图（`backgroundPic` / `picTab.picN`）→ 超过控件盒 = 红，大控件配小图 = 黄；跳过
`.9.png`（本来就要拉伸）、全透明占位图（`transparency.png` 类技巧）。
阈值取“宁可漏报不误报”，基准工程要求零误报。

**thumb 滑块（自有尺寸子盒）不在这里报，但**不**等于不核**（v0.27.75 去掉了旧说法“跳过 thumb”，它会
真出事：案例 `sk_thumb.png` 31×31 配 `thumb.size` 30×30 一路 PASS，真机上滑块与轨道对不上）：

| 面 | 盒子 | 口径 |
|----|------|------|
| 编辑器预检（本节） | `thumb.size` | **自动生成图**（`resources/images/`）失配 → 红标（修图，别改 json 盒子） |
| `check_all` #11 / #17 / `verify_assets` | `thumb.size` | 自动生成图失配 → `mismatch[]` = **FAIL** |
| 同上 | `thumb.size` | 手绘 thumb 失配 → 仅 `stretched[]` 提示：官方基准工程 `SampleUI-New` 就是手绘 `slider_/jdt_ht.png` 35×34 vs `thumb.size` 33×35（引擎会拉伸） |
| 同上 | — | `thumb` 没写 `size` → 跳过 + `skippedNoBox[]`/warning（不误报） |

完整口径与量化数字（形状分类出图 / 抗锯齿档位）见 `knowledge/devflow/ui-asset-rules.md` §2 铁律 #1 与 #8。

### 3-1 代码侧：运行期设的图也要核（v0.27.90 起，`check_all` 第 20 项）

上一节核的都是 **json 里声明**的图；`mXXXPtr->setBackgroundPic("images/x.png")` 这类
**运行期设图**以前是盲区（案例实测：48×16 三点图进了被抬高的 48×26 盒 → 引擎按盒拉伸 →
正圆变竖椭圆，静态全检一路 PASS）。现在 `check_all` **第 20 项**补上：

| 面 | 口径 |
|----|------|
| 扫描 | `<项目>/src/**/*.cc`｜`*.cpp` 里 `set…Pic("…")` 的**字面量**实参（去注释保行号；三元式多个字面量一并查） |
| 目标 | `mXxxPtr` → caption `Xxx`（同第 6 项）；映射不到 → `unresolved[]` 列出，**不静默跳过** |
| FAIL | `resources/images/` 的自动生成图 != 控件盒（同一 caption 在**任一页**对上就算对） |
| NOTE | 手绘图（`navi/` 等）!= 盒子 → `stretched[]` 仅提示（官方基准 `navi/fh.png` 44×26 → 72×40 按钮是合法拉伸）；`.9.png` 豁免 |
| NOTE | 实参是变量/拼接（运行时才知道用哪张图）→ 只计 `dynamic`（案例 `ldFrame()` 拼路径就是这类） |

零误报核查：`SampleUI-New` / `ShowcaseAlbum-F133` / `WebViewDemo` / TDesign 迁移案例双平台
在 v0.27.90 下 **0 新增 FAIL**；把案例 `LdDots` 盒高改回 26（旧值）**当场报出**。
口径与边界详见 `knowledge/uicontrols/text-box-height-rule.md` §4/§5。

## 4. 变更写回（`flythings_ui_visual(action="edit_apply")`）

用户在编辑器里改完 → 「复制变更 JSON」→ 传回 → 写回 json 并 **pack 成 ftu**：

```json
{
  "file": "main.json",
  "resolution": "1024x600",
  "changes": { "button__1": { "left": 130, "top": 60, "width": 150, "height": 54 } },
  "props":   { "textview__4": { "text": "新文字", "fontSize": 22,
                                "colorTab": { "color0": 16711680 } } }
}
```

- `changes` = 几何（`position` 四项）；`props` = 其它属性（深合并写回）；两者都可省
- 控件路径：顶层写 `button__1`；嵌套 window 内用斜杠 `window__2/button__3`

安全措施（写坏 json 的代价很高，这三条不要绕过）：

1. 写回前自动备份 `<name>.json.bak`
2. **格式一致性自检**：原文件必须能 `json.dumps(indent=2, ensure_ascii=False)` 无损还原，
   否则拒写（防止把 IDE 格式的整个文件重排，产生巨大 diff）
3. 坐标取整 + 不越出屏幕边界；宽度/高度至少 1px

## 5. 像素 diff（`flythings_ui_visual(action="diff")`，0 token）

输出的**是差异清单（数字）而不是图**——所以不吃 token：区域坐标 / 尺寸 / 面积 / 最大色差。
把整屏图丢给视觉模型是千级 token/次，迭代十轮就上万，没必要。

默认参数（三道闸，专治假报警）：

| 参数 | 默认 | 作用 |
|------|------|------|
| `tolerance` | 2 | 单通道 \|Δ\| ≤2 视为相同 |
| `shift` | 1 | **±1px 抖动补偿**：每像素在邻域找最优匹配，"看着像差异其实只是抖动"不算 |
| `blur` | 0.7 | 对比前高斯模糊，抹掉字体抗锯齿噪声 |
| `min_area` / `noise_bbox` | 4 / 10 | 小斑点与 bbox ≤10×10 的碎块归入 `noise`，不进主清单 |

**主力用法 = 回归对比**：改动前截一张、改后截一张，两张丢进去。同渲染器、零噪声，
"改 A 碰坏 B"会被逐块列出来。跨渲染器（HTML 预览 vs 设备截图）只能当骨架参考，
字体磨边差异靠阈值压，不能当结论。

分层省钱：**L1 像素 diff（0 token，默认）→ L2 需要语义判断时只把差异区域裁 200×200 小图给模型
→ L3 人工看标注图（0 token）**。

### 5-1 像素基线库（`flythings_ui_visual(action="baseline")`）

把「上一次验收通过的那张图」版本化存到 **`<项目>/ui_baseline/`**（`baseline.json` 索引 + 图片），
下次验收直接比，**省掉人工看图**。必填 `project_root`；

| `mode` | 作用 |
|---|---|
| `save` | 存基线（首次建基线用它） |
| `compare` | 与基线比（+ `image_a`）；**容差档案随基线一起存**，所以比对口径与建基线时一致 |
| `update` | 把当前图替换为基线 |
| `list` | 列出现有基线 |

⚠️ **比不到基线 → 返回 `no-baseline` 并进 `warnings`，不算通过**（不静默放过）。

### 5-2 edit_apply 的写盘开关（默认安全）

- `pack` **默认 False**（只写 json，不自动 pack ftu）——要 pack 得显式传 `pack=true`；
- `dry_run=True` 只预览变更、**不写盘**；
- 写回前一律留 `<name>.json.bak`（见 §4 安全措施）。

## 6. 图片资源路径（易错点，影响所有预览）

json 里的图片引用是**相对 resources 目录、可带子目录**的路径：`audio/horn.png`、
`dvr/record.png`、`window/base_rectangle.png`（不是只有 `images/xxx.png`）。

解析顺序（`json2html.find_asset()`）：`<项目>/resources/<引用>` → `resources/images/<引用>` →
json 同目录 → 项目根 → 再退 `.9.png` 九宫格变体；data URI 按扩展名给对 mime。

⚠️ 只按 basename 去 `resources/images/` 找的实现会**大面积丢图**，并连带让"图片尺寸≠控件尺寸"
预检形同虚设（找不到图就无从比较）。**预览里的图必须是真图**，否则用户没法用来确认效果。

另外：按钮 `picTab` 只填了非 0 状态（如只有 `pic2`）时，预览要取第一个有值的状态图，
否则整片空白。资源引用解析不出来的，要显式报给用户（设备上那块就是空白）。

## 7. 现象 → 根因排查表

| 现象 | 先查 |
|------|------|
| 图标/整体**锯齿、发糊** | ① json `resolution` 是否等于设备屏（不等 = 整屏缩放，全糊）② 图片尺寸 ≠ 控件尺寸 ③ 图标控件过小（<24px）或非正方（图标按 min 边长画，居中后描边发虚） |
| **位置不对** | ① 转换时 CSS 的 padding/border/margin 参与了几何 ② 坐标取整偏差累积 ③ 嵌套 window 子坐标必须**相对父窗口** |
| **切图不对** | 控件尺寸是照着 CSS 猜的，没看真实 PNG 尺寸 → 图片控件尺寸应取 PNG 实际尺寸；同一张图被多个不同尺寸控件引用＝靠缩放硬撑的信号 |
| **预览丢图** | 资源路径解析（第 6 节），带子目录的引用最容易漏 |
| **多屏设计稿只落地第一屏** | 转换器只取了第一个 `.screen`（旧版行为）-> 核 `screensDetected` == `pagesProduced` == 设计稿屏数 N；`.screen` 必须并列（嵌套/重名会 success:false，见 `knowledge/devflow/prototype-flow.md`「分页落地清单」） |
| **预览只看到首页 / 切不了页** | 整屏 window 多页架构 → 用预览稿顶部**页面切换条**或 `#window__N` hash 直达（第 2-2 节）；隐藏的弹窗用「显示隐藏」幽灵框。若预览稿里没有切换条，说明这个 json 确实只有一个整屏窗口（多半页面是 `showWnd()` 动态加载的另一 json，跑项目级预览就会出「项目页面」行） |
| **文字被裁** | 文本估算宽度超控件宽，或字号 > 控件高 |

## 8. 改完布局的检查顺序

0. **屏数核对**（交付前必做，2026-09-21 起）：设计稿 N 屏 <-> 产出 N 页 —— `flythings_html_to_json` 返回的
   `screensDetected` 必须 == `pagesProduced` == N（不等即 `success:false`，先修 HTML）；同 ftu 形态数整屏
   window 个数，独立 ftu 形态数 json/ftu 个数；预览还要能**切到每一页**（不能只看到首页，见第 2-2 节）
1. `flythings_ui_visual(action="editor")` 生成编辑器，先看**红标**（图片尺寸不匹配优先修——那是锯齿/糊的根因）
2. 拖 / 改属性 → 复制变更 JSON → `flythings_ui_visual(action="edit_apply")`（写回 + pack）
3. `flythings_build_ui_flow` 推真机，`flythings_device_screenshot` 抓屏，与上一版截图 `flythings_ui_visual(action="diff")` 对比：
   **只允许出现预期差异**，其余视为回归
4. 需要"这块到底是什么毛病"的判断时，只裁差异区域的小图给视觉模型

## 9. 红线

- 布局以 **json 为源**，不要手改 ftu；不要绕过 pack 直接改设备上的文件
- 自动生成的图片按项目约定目录存放，json 里写相对 resources 的路径（不要绝对路径）
- 验收用**像素 diff + 真机截图**，不要用视觉模型整屏比图（token 白烧且不稳定）
- 编辑器产物 `ui/_edit/*.edit.html` 是生成物，可随时删，不要提交进项目仓库
