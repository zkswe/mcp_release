# 界面块片段库 + 组装器（ui_blocks）· MVP

> **一句话**：让 AI（和人）做 FlyThings 界面时，从「手算坐标」变成「**选块 + 填值 + 排序**」——
> 像用 Bootstrap/组件库那样拼界面，并且**一次就出能过的产物**：json + 切图 + 渲染图 + 全检。
>
> 建立：2026-10-01（「按照你的建议做」）。第 2 批（交互类 7 块）：2026-10-01 同日追加。
> 第 3 批（结构 / 导航 / 提示类 7 块 + 两版示例）：2026-10-01 同日追加 → 共 **24 个块 / 6 版示例**。
> **图标来源改口径：2026-10-01 同日**（「这些网络/设备的 icon 来源？效果差异和实际差异太大」
> → 块库图标**唯一来源 = `components/icons` 图标资产库**，禁自绘/禁 emoji 字体兜底，见 **§5.1**）。
> 范围：**只新建/只改本目录**，不改任何现有脚本/知识文档；
> 所有出图/渲染/全检都**调现有工具**（`ui_tools/gen_res.py`、`ui_tools/json2img.py`、`ui_tools/check_all.py`），
> 不复制它们的逻辑。

---

## 1. 目录

```
templates/ui_blocks/
├─ compose.py                 ← 组装器（唯一入口，CLI）
├─ iconlib.py                 ← 图标解析层：语义名 → `components/icons` 资产库（档位 56/24/22、图 == 盒、
│缺档按盒尺寸现出、查不到才回退线框并**明说**）
├─ full_render.py             ← 整页渲染（展平 scrollwindow → y 方向长图，供人工验收；不参与 check_all）
├─ blocks/
│  ├─ _tokens.json            ← 设计令牌 + 相对尺度体系的**唯一数值源**（比例/令牌，不写死某屏像素；含第 3 批语义色与 glyph 尺寸下限）
│  ├─ _icons.json             ← `icon` 字段的**允许值清单**（从 components/icons/catalog.json 摘：203 语义名 / 5 分类 / 两态清单 / 档位与回退口径）
│  ├─ page_title.json         ← 块定义：字段 + 相对约束 + 需要素材 + 禁止项
│  └─ …（共 24 个块定义 = 第 1 批 10 个 + 第 2 批交互类 7 个 + 第 3 批结构/导航/提示类 7 个）
└─ examples/
   ├─ settings_1024x600/      ← 示例 A：spec.json + project/（产物）+ main.render.png + main.full.render.png + 两个日志
   ├─ settings_320x240/       ← 示例 B：**同一套块**，只换分辨率（spec.json 只差 resolution 与短文案）
   ├─ interactive_1024x600/   ← 示例 C：**第 2 批 7 个交互块**全都用上 + 复用 card/section_header/toggle_row/setting_row/bottom_actions/dialog
   ├─ interactive_320x240/    ← 示例 D：与示例 C **同一份块清单**，只换分辨率（极小屏自动降级）
   ├─ nav_1024x600/           ← 示例 E：**第 3 批 7 个新块**全都用上（tabs/bottom_nav/banner×4 态/toast/status_pill×2 态/divider_label/grid_icons）
   │                            + 复用 page_title/card/section_header/bottom_actions/dialog
   └─ nav_320x240/            ← 示例 F：与示例 E **同一份块清单**，只换分辨率与短文案（极小屏：视口 = 屏高 − 标题 − nav − 底栏）
```
六版示例都带 `main.full.render.png` = 展平 scrollwindow 的**整页渲染**（由 `full_render.py` 产出，仅供人工验收，**不参与 check_all**）。
口径：内容展平；**固定带（底导 / 底栏）让位到长图底部**（y = 整页高 − 固定带高，位移量 = 滑动行程）——
旧口径「保持原屏 y 不变」会把底栏摆在长图中段、压住内容（2026-10-01 看图：「内容区伸进底部
固定条，把最后一行盖住」）。整屏浮层（弹窗 / 提示）仍按原屏 y 画（它们是「浮层」不是贴底固定带）。
让位前后都过 `assert_bands_clear`：固定带 × 实际渲染出的内容节点逐对判 rect 相交，相交 → 报错退出、不出图。

## 2. 用法（一条命令）

```bash
python templates/ui_blocks/compose.py <spec.json> --project <工程根> [--page main] [--render] [--check]
```

| 参数 | 说明 |
|---|---|
| `spec.json` | 输入：分辨率 + 页面标题 + 块列表（见 §3） |
| `--project` | 产物落点：`<工程>/ui/…`、`<工程>/resources/images/`、`<工程>/src/logic/` |
| `--page` | 页面名（json 文件名 / 渲染图名），默认 `main` |
| `--render` | 调 `ui_tools/json2img.py` 出渲染图（并核对 **PNG 尺寸 == resolution**） |
| `--check` | 调 `ui_tools/check_all.py` 全检（打印 exit code） |
| `--ui-layout` | `auto`（默认）/ `flat` / `res` —— json 落 `ui/x.json` 还是 `ui/<W>x<H>/x.json` |
| `--font` | 渲染字体；缺省自动找 `<工程>/resources/font/*.ttf` → `components/fonts/fonts/zkswe-hans-common.ttf` |
| `--json-only` / `--no-logic` | 只出 json / 不生成 logic 骨架 |

**实际执行的两条命令（示例产物就是这么来的）**：

```bash
cd tools/FlyThings_mcp_open
python templates/ui_blocks/compose.py templates/ui_blocks/examples/settings_1024x600/spec.json \
       --project templates/ui_blocks/examples/settings_1024x600/project --render --check
python templates/ui_blocks/compose.py templates/ui_blocks/examples/settings_320x240/spec.json \
       --project templates/ui_blocks/examples/settings_320x240/project --render --check
python templates/ui_blocks/compose.py templates/ui_blocks/examples/interactive_1024x600/spec.json \
       --project templates/ui_blocks/examples/interactive_1024x600/project --render --check
python templates/ui_blocks/compose.py templates/ui_blocks/examples/interactive_320x240/spec.json \
       --project templates/ui_blocks/examples/interactive_320x240/project --render --check
python templates/ui_blocks/compose.py templates/ui_blocks/examples/nav_1024x600/spec.json \
       --project templates/ui_blocks/examples/nav_1024x600/project --render --check
python templates/ui_blocks/compose.py templates/ui_blocks/examples/nav_320x240/spec.json \
       --project templates/ui_blocks/examples/nav_320x240/project --render --check
```

**整页渲染（六版都有，供人工验收；不参与 check_all）**：

```bash
cd tools/FlyThings_mcp_open
python templates/ui_blocks/full_render.py templates/ui_blocks/examples/nav_1024x600/project \
       --out templates/ui_blocks/examples/nav_1024x600/main.full.render.png
```

产物清单（每页）：
1. `<工程>/ui/[<W>x<H>/]main.json` —— 字段全集显式、`textview__N/button__N/window__N` **连续编号**、根节点 `id:0 + position + resolution`；
2. `<工程>/resources/images/*.png` —— 只给用到的块出图，**图 == 控件盒**（形状/底图走 `gen_res.py`；**图标走 `components/icons` 资产库**，见 §5.1）；
3. `<工程>/ui/main.render.png`（`--render`）、`<工程>/src/logic/mainLogic.cc`（骨架，按钮回调一个不缺）、`<示例>/main.full.render.png`（`full_render.py`，人工验收）；
4. `check_all` 全检结果（`--check`）。

## 3. spec 格式

```json
{
  "resolution": {"width": 1024, "height": 600},
  "page": {
    "title": "设置", "subtitle": "Settings",
    "blocks": [
      {"type": "card", "title": "设备", "blocks": [
        {"type": "setting_row", "label": "WiFi", "value": "已连接 · 192.168.1.100", "value_short": "已连接", "chevron": true},
        {"type": "icon_row", "icon": "list", "label": "多屏拼接", "value": "已开启 2/2 · 主屏"},
        {"type": "toggle_row", "label": "自动息屏", "value": "已开启", "on": true},
        {"type": "device_card", "icon": "wifi", "label": "客厅面板", "value": "在线 · 信号良好", "online": true}
      ]},
      {"type": "section_header", "text": "其它"},
      {"type": "slider_row", "label": "音量", "value": "当前 60%", "progress": 60},
      {"type": "input_row", "label": "设备名称", "hintText": "请输入名称", "text": "客厅面板", "textType": 0},
      {"type": "checkbox_row", "label": "记住设置", "value": "已勾选", "checked": true},
      {"type": "radio_row", "label": "工作模式", "options": ["本地", "远程", "自动"], "selected": 0},
      {"type": "list_item", "label": "在线设备", "rows": 4, "chevron": true,
       "items": [{"icon": "wifi", "title": "客厅面板", "value": "在线"},
                 {"icon": "bulb", "title": "主卧灯", "value": "离线"},
                 {"icon": "wifi", "title": "书房空气净化器", "value": "在线"},
                 {"icon": "bulb", "title": "Kitchen Light", "value": "离线"}]},
      {"type": "wheel_picker", "label": "定时关闭", "rows": 5,
       "columns": [{"options": ["不关", "15 分", "30 分"], "selected": 1}]},
      {"type": "empty_state", "icon": "info", "text": "暂无其它设备", "sub": "点右上角添加"},
      {"type": "tabs", "items": ["全部", "在线", "离线"], "selected": 0},
      {"type": "status_pill", "state": "ok", "text": "运行正常"},
      {"type": "banner", "state": "warn", "text": "网络信号较弱，建议靠近路由器"},
      {"type": "divider_label", "text": "快捷入口"},
      {"type": "grid_icons", "cols": 3, "tappable": true,
       "items": [{"icon": "wifi", "text": "网络"}, {"icon": "list", "text": "设备"}]},
      {"type": "bottom_nav", "selected": 0,
       "items": [{"icon": "home", "text": "首页"}, {"icon": "user", "text": "我的"}]},
      {"type": "bottom_actions", "status": "已是最新", "primary": "保存", "secondary": "取消"},
      {"type": "toast", "text": "已保存", "visible": false},
      {"type": "dialog", "title": "确认删除", "body": "删除后不可恢复，确定继续吗？", "visible": false}
    ]
  }
}
```

* `page.title`（+ `subtitle`）也可以写成一个 `page_title` 块，二选一；`bottom_actions` 同理可用 `page.footer`。
* 极小块用 `value_short` 给「数得出来的短文案」（长值在 320 上放不下会 #13 FAIL）。
* **第 3 批新块都是根层块**（不进卡）：`tabs` / `bottom_nav` / `banner` / `toast` / `status_pill` / `divider_label` / `grid_icons`；写进 `card.blocks` 会直接报错退出（不静默兜底）。
* `bottom_nav` 与 `bottom_actions` 可**同页共存**：nav 贴底栏上沿（两者不重叠），视口 = 屏高 − 标题带 − nav 带 − 底栏带（compose 打印 `[NOTE] bottom_nav 固定带 N px → 视口缩至 M`）。

## 4. 块清单（24 个 = 第 1 批 10 个 + 第 2 批交互类 7 个 + 第 3 批结构/导航/提示类 7 个）；第 4 批复杂块另见本节末 4 行与 §4.3

| 块 | 用途 | 占几行 | 需要素材（`gen_res` 出） | 能滚动 | 关键相对约束 |
|---|---|---|---|---|---|
| `page_title` | 标题 + 英文副标题 | 顶栏带 | — | ✗ | 带高 = max(屏高×10%, 标题带内容高+12)；h1 + bold + fg1 |
| `section_header` | 分组小标题 | 1 带 | — | 随内容 | 带高 = max(spacer-3, h2×1.45)；h2 + fg2 |
| `setting_row` | 设置行（标题 + 值 + 箭头） | 1 行 | `chev_`（+可选 `icbg_/ic_`） | 随内容 | 行高 = 屏高 10%（极小屏 11.7%）；两行式：标题在上、值在下、**左缘同一**；箭头贴右缘 − pad |
| `toggle_row` | 开关行 | 1 行 | `sw_*_on/off`、`swk_` | 随内容 | 开关盒 = 行高×1.30 × 0.72，贴右缘；**装饰件呈现态 + 整行透明 button 命中**|
| `icon_row` | 图标底 + 图标 + 标题 + 值 + 箭头 | 1 行 | `icbg_`、`ic_<glyph>_`、`chev_` | 随内容 | 图标底 = 行高×0.60（垂中）、图标 = 行高×0.40（同心）；文本左缘 = 图标底右缘 + spacer |
| `device_card` | 设备卡（图标 + 名称 + 状态 + 箭头） | 1 行 | 同 `icon_row` + `dot_` | 随内容 | 与 `icon_row` **同一套行模板**（同页行族一致） |
| `card` | 圆角卡片容器（白底 + 行内分割线） | N 行 | `card_<W>x<H>`、`sep_<W>x1` | 随内容 | 宽 = 屏宽 − 2×spacer-2；圆角 = min(6, 行高×0.18) 且 ≥4；相邻行 1px 分割线 |
| `empty_state` | 空态（图标 + 文案，居中） | 1 带 | `icbg_`、`ic_<glyph>_` | 随内容 | 带高 = 屏高×30%；图标底 = 2×行高×0.60；文案居中 |
| `bottom_actions` | 底部状态文案 + 主/次按钮 | 底栏带 | `footbg_`、`btn_primary_`、`btn_secondary_` | ✗（固定件） | 带高 = max(屏高×12%, 按钮高+24)；主按钮贴右，次按钮在其左 − spacer |
| `dialog` | 弹窗（遮罩 + 面板 + 标题 + 正文 + 双按钮） | 覆盖层 | `cc_scrim_<W>x<H>`、`panel_`、双按钮图 | ✗ | 根层整屏 `window`（modal + visible:false）；面板宽 = 屏宽×60%，整屏居中；遮罩 **touchable 显式 false**|
| `slider_row` | 滑块行（标题 + 数值 + 可拖滑块） | 2 带（文本带 + 滑块带） | `sk_track_`、`sk_fill_`、`sk_thumb_` | 随内容 | 文本带照抄行族；滑块带高 = 盒高 + 2×spacer；盒高 = max(thumb, 行高×0.60) 且 **≥ thumb.size.height**；**thumb 盒 == 图**；progress 0~100 |
| `progress_row` | 进度行（只读进度条 + 百分比） | 2 带 | 同 `slider_row`（同名同尺寸只出一张） | 随内容 | 与 `slider_row` **同一套几何**；thumb 图留空 + `thumb.size` 写 0（否则被当可拖滑块） |
| `input_row` | 输入行（标题 + edittext） | 2 带 | —（底色走 `bgColorTab` 浅灰） | 随内容 | 输入框盒高 = max(标题高+spacer, 行高×0.70)；id 51000 段 → logic 骨架自动带 `onEditTextChanged_<caption>` |
| `checkbox_row` | 复选行（标题 + 值 + 右端复选框） | 1 行 | `cb_{S}_on/off` | 随内容 | 复选框正方盒 = max(12, 行高×0.50)，贴行条右端槽（同 toggle_row 形态）；**自身就是命中区**|
| `radio_row` | 单选行（标题 + **竖排**选项） | 2 带（带高 = 选项数 × 项高 + 2×spacer） | `rd_{S}_on/off` | 随内容 | 项高 = max(标题高+spacer, 行高×0.70)；子项坐标**相对 radiogroup**；组 **touchable 必须 true**|
| `list_item` | 列表行块（listview + subItem 行模板，行内容由 `items` 给） | 自带块高（rows × 模板高 + 余数） | `chev_`（行尾箭头子项）、`ic_`（行内图标） | ✗（自带滚动） | **itemH = int(lv高/rows) − rowSpacing**，模板高 == 它；**余数是「有意的可滑动提示」**；item.text 必须空串；**列表内容必须由 `items` 给**（只写 rows = 空列表） |
| `wheel_picker` | 滚轮选择块（listview 组合，非自绘） | 自带块高（rows × 模板高） | `wband_`（选中条） | ✗（自带滚动） | 选中条 = **静态 textview 且写在 listview 之前**；rows 必须奇数（正中行 = 选中行）；cycleEnable + autoRollback + edgeEffect 1 + dragMaxDis 手感值 |
| `tabs` | 顶部分段控件（N 个 tab：选中底色/文字色 + 底部指示条） | 1 顶带（随内容） | `tabsbg_`、`ind_`、`tab_on_` | 随内容 | 带高 = max(屏高 9%, b1 高 + 2×spacer)；tab 等分内容区宽（末个吃余数）；**指示条盒 = tab 宽 − 2×圆角 × ind_h（高 3/2px 直角条）且写在所有 tab 之前**；选中 = brand1 底（高让出 ind_h）+ brand 字 |
| `bottom_nav` | 底部导航（3~5 个图标+文字项，选中用品牌色） | **固定带**| `navbg_`、`nav_<glyph>_<S>_on/off` | ✗（固定件） | 带高**固定**（与项数无关）= max(屏高 10%, 图标档 + 间距 + b2 + 2×spacer)；贴底栏上沿；视口 = 屏高 − 标题带 − nav 带 − 底栏带；项宽 = 屏宽/N（末个吃余数） |
| `banner` | 提示/告警条（图标 + 一行文案 + 可选关闭） | 1 带 | `bnr_<state>_`、`ic_<glyph>_<S>_<state>`、`ic_close_<S>_<state>` | 随内容 | 带高 = max(屏高 8%, b1 高 + 2×spacer)；4 语义色走令牌（state = info/success/warn/danger）；关闭盒 = max(16, 图标档) 贴右缘；文案右缘 → 关闭盒间隙 = 行族同口径 |
| `toast` | 浮层提示（半透明圆角底 + 文案） | 覆盖层（根层整屏 window） | `toast_bg_` | ✗ | **visible:false 默认**；modal=false + touchable=false；盒宽 = min(内容宽 × 0.70, 文本盒 + 2×spacer-3)，高 = b1 + 2×spacer-2；垂直 = (屏高 − 盒高) × 0.60；**最后定义 = 最上层**|
| `status_pill` | 状态胶囊（圆角药丸 + 彩色文字） | 1 带 | `pill_<state>_` | 随内容 | 带高 = max(屏高 7%, b2 高 + spacer)；盒宽 = 文本盒（估算 × 1.10，向上取 4px 栅格）+ 2×pill_pad；圆角 = 带高/2；state = ok/warn/danger/off |
| `divider_label` | 带文字分割线（左右 1px 线 + 中间小字） | 1 带 | `sep_<W>x1`（与行内分割线共用） | 随内容 | 带高 = max(屏高 5%, b2 高)；线长 = (内容宽 − 文本盒)/2 − 间隙（**随容器比例伸缩，不给固定像素**）；两侧等长；轴线直角（不用圆角） |
| `grid_icons` | 图标宫格（N×M 等距格：格底 + 图标底 + 图标 + 文字） | 自带块高（rows × 格高 + 行距） | `gtile_`、`icbg_`、`ic_<glyph>_<S>` | 随内容 | 格宽 = 内容宽/cols（末列吃余数）− 横向间隙；**格盒 == 图**；格高 = 2×spacer + 图标底 + b2 高；图标底 = max(图标底档, 图标 × 1.5)；`tappable` → 每格一个整格 button（最后定义） |
| `toolbar` | 顶部工具条（左返回 + 标题 + 右侧动作图标，图标走 `components/icons`） | **固定带**（占标题带位置） | `toolbg_<W>x<H>`、`ic_back_`、`ic_<glyph>_` | ✗（固定件） | 带高 = max(屏高 12%, 图标档 + 2×spacer)（1024→72 / 320→40）；**与 `page_title` 二选一**（同页同给 → 报错退出）；动作图标 ≤3；返回/动作命中盒 = min(带高, max(图标档+2×spacer, 32))；底盘 → 图标 → 命中 button（最后定义 = z 最高） |
| `loading` | 加载态（spinner 转圈图 + 文案 / skeleton 文案 + N 条骨架条；**静态帧**） | 自带块高（1 带） | `card_<W>x<H>`、`skel_<W>x<H>`、`ic_<glyph>_<S>` | 随内容 | 根层块（卡内写报错退出）；spinner 带高 = max(屏高×0.18, 图标档+spacer+b1+2×spacer-2)（1024→108 / 320→80）；skeleton 带高 = 2×spacer-2 + b1 + spacer-1 + lines×条高 + (lines−1)×spacer；条高 = max(10, b1×0.70)（**≥10px 硬口径**）；整块装饰件 touchable 显式 false |
| `time_row` | 时间行（标题 + 时间/日期值 + 箭头；**是「行」不是日历**） | 1 行 | `chev_`（+可选 `icbg_/ic_`） | 随内容 | 与 `setting_row` **同一套行模板**（行高 = 屏高 10%、极小屏 11.7%）；两行式标题在上、值在下、**左缘同一**；极小屏整页降单行式（标题左、值右，可给 `value_short`）；值 = 已格式化**字符串**（块库不解析时间）；命中区 = 整行透明 button（caption = `ButtonRowTimeRow<n>`） |
| `form_section` | 表单分组（组标题 + 字段行集合 + 组间距；行族口径复用 `setting_row`） | 组标题 1 带 + N 行（自带块高） | 可选 `card_<W>x<H>`（surface=true）、`sep_<W>x1` | 随内容 | 行集合与 card **同一套 builder**（字段行 / 行块 / list_item / wheel_picker；根层块写进 `blocks` 报错退出）；组内行间 1px 分割线（`RowSep<行块序号>`）、组内行与行**不额外留空**；组间距 = 块前后各一个 `group_gap(spacer-2)`（run() 统一加，与 card 同口径）；surface=false 默认（行直接落页面灰底，无底图） |

> `value_row`（左标题 + 右值，无箭头）不用单独建块：`{"type":"setting_row","chevron":false,"icon":""}` 就是它。

### 4.1 第 2 批 7 个块的禁止项（红线；完整版在 `blocks/<type>.json` 的 `forbidden`）
| 块 | 红线（写了就注定返工/编译不过/真机不对） |
|---|---|
| `slider_row` | ① **滑块盒 ≠ 图**（`thumb.size` 与滑块图不一致 → 真机滑块与轨道错位，check_all #11/#17 FAIL）；② **滑块被盒高压扁**（控件 `position.height` < `thumb.size.height` → 屏幕上是扁椭圆，**只改图或只改盒都没用**）；③ 为给滑块腾位去收窄/挪 title·value 文本盒；④ 滑轨/有效图用 `.9.png`（ZKSeekBar 不解析 marker → 黑框，#10 FAIL）；⑤ 可见条矮于 10px（药丸端弧线过不了 AA 审计，#21 真缺陷）。 |
| `progress_row` | ① 给只读进度条配 thumb 图（会被当成可拖滑块）；② 与 `slider_row` 用不同盒高/左缘（同页进度控件口径必须照抄第一个）；③ 盒高 < 可见条高（条被裁）。 |
| `input_row` | ① 底色写 `0`（= 不透明黑，真机黑块；透明写 `-1`，#24 FAIL）；② `isPassword=true` 却不给 `passwordChar`；③ 密码框把真密码预填进 `text`；④ 自绘键盘（系统内置，点击自动弹）。 |
| `checkbox_row` | ① **在复选框上再压一个整行透明 button**（吃掉勾选：点行没反应 —— checkbox 与 toggle_row 不同，**它自己就是命中区**）；② 盒 ≠ 图（引擎拉伸 → 圆角糊、勾变形）；③ 只给 `pic0` 不给 `pic2`（点了没视觉反馈）；④ id 取 21000 段（html2json 旧口径；#5 会把 20000~30000 段当 button 要求 `onButtonClick_<caption>`）—— 本块用 **94500**段。 |
| `radio_row` | ① **radiogroup 的 `touchable` 写 false**（整组收不到触摸 = 点了没反应；它是「容器 false」口径的**例外**）；② 选中图写进 `pic1`（引擎只认 `pic2` = 选中态）；③ 选项横排（横排要按选项数动态改行族预留 → 同页其它行文本盒跟着变；竖排在极小屏也放得下）；④ 圆点盒 ≠ 图；⑤ 极小屏用 1px 描边环 / 极小内点（AA 真缺陷）。 |
| `list_item` | ① **只写 `rows` 不给 `items`**（列表内容必须由 `items` 给；只写 rows 会得到空列表——**这是规范，不是渲染 bug**）；② **item 高 ≠ `int(lv高/rows) − rowSpacing`**（#37 WARN：写大 = 挤爆/裁切，写小 = 每项底部多空带）；③ 把「底部露出下一项一小块」当缺陷去凑整（**那是引擎给的可滑动提示**，余数是有意的）；④ `item.text` 写占位串（真机每行常显占位文字；`items` 给的**真实首行文案**是有意的模板样例，但真机必须 `obtainListItemData` 逐行覆盖）；⑤ 在 listview 下平铺 textview/button 当行（#2 层级非法）；⑥ subItem 图 ≠ subItem 盒；⑦ 行内图标盒 < 24px 硬塞（极小屏宁可**省图标**，不是缩图标）。 |
| `wheel_picker` | ① **选中条挂行背景图**（滚动时条跟着行走）；② **条写在 listview 之后**（z 更高会盖住列表/吃触摸）；③ 条设成可触摸（装饰件必须 `touchable:false` 显式写）；④ 用引擎选中态（`pic2`/`color2`）做正中行高亮（引擎把选中态打在第 1 可见行，会盖掉宿主）；⑤ 程序化定位用 `setSelection`（只对齐第 1 行 + 带动画 → 「读-改-读」会越推越远，要用数据侧平移）；⑥ lv 高非 rows 整除却当「可滑动提示」凑格（滚轮要刚好一屏窗口）；⑦ 自绘轮子（listview 组合就是 L2 能力）。 |

### 4.2 第 3 批 7 个块的禁止项（红线；完整版在 `blocks/<type>.json` 的 `forbidden`）

| 块 | 红线（写了就注定返工/编译不过/真机不对） |
|---|---|
| `tabs` | ① **指示条定义在 tab 之后**（静态件必须写在所有 tab/button 之前；写在后面 z 更高 → 盖住 tab 文字、可能吃触摸）；② 指示条写成圆角药丸（2~3px 高的小弧在 `aa_audit` 里退化成硬阶梯 → #21 真缺陷）、或把指示条内缩（两侧各缩容器圆角宽之类 → 与 tab 项左右不齐；2026-10-01 需求方看图实修）、或让装饰件用**自己那份半径**叠在药丸条上（半径 ≠ 条半径 → 同一根条左端方角、右端圆角；必须从整条形状裁切，见 §4.2）；③ 选中底与指示条**几何重叠**（选中底高度必须让出 `ind_h`，否则指示条被底色盖住 = 「看不见指示条」）；④ tab 用 textview + 整行透明 button 两层（tab 只需一个透明 button 自带文字）；⑤ 给 tab 再挂底图做「选中态」（底图 == 盒，会让未选中 tab 也带底色）。 |
| `bottom_nav` | ① 把 bottom_nav 放进滑动区（固定件必须放 scrollwindow 外面）；② 底导带与底栏带**重叠**（nav 必须贴底栏上沿；视口 = 屏高 − 标题 − nav − 底栏）；③ 项数变了就改带高（**带高固定**，只有项宽随项数变）；④ 图标盒 ≠ 图（glyph 必须给 `canvas=图标档`）；⑤ **项宽写死像素**（必须按**屏宽比例**等分：项宽 = 屏宽/N，末项吃余数）；⑥ 给 nav 加主/次按钮（那是 `bottom_actions` 的活）。 |
| `banner` | ① 语义色写死十六进制（必须走 `_tokens.json` 的 info/success/warn/danger + -1 浅底）；② 底图 ≠ 容器盒（引擎拉伸 → 圆角糊）；③ 把多条提示塞进一个块（一个 banner = 一条语义提示）；④ 关闭按钮做成纯装饰（关不掉，且必须写在底盘/图标/文字**之后**= z 最高）；⑤ 关闭按钮盒 < 16px（真实手指点不到）。 |
| `toast` | ① **`visible` 写 true**（默认弹出会盖住首屏）；② **定义在弹窗/内容之前**（z 不够高会被盖住；toast 必须最后定义）；③ 写 `modal=true` 或 `touchable=true`（提示不该拦触摸，modal 会让整屏点不动）；④ 用 pagewindow/scrollwindow 做浮层（层级非法）；⑤ 底色写不透明 `#000000`（失去「浮层」语义；用 `mask` 令牌半透明）。 |
| `status_pill` | ① 胶囊盒 ≠ 图（引擎拉伸 → 药丸两端变椭圆）；② 色值写死（4 态走令牌）；③ 胶囊拉满内容区宽（宽度由文案反算；拉满就成了色带）；④ `state` 写成表外值（compose 报错退出，不静默兜底）；⑤ 药丸高 < b2 文本高 + spacer（文字贴边）。 |
| `divider_label` | ① 线用圆角药丸（1px 高的圆角在 `aa_audit` 里退化成硬阶梯 → #21 真缺陷；轴线一律直角）；② 线长写死像素（换分辨率/换容器宽就错位；必须由「容器宽 − 文本盒宽」反算）；③ 左右线长不等（文字偏心）；④ 线用 `backgroundColor` 画 + 又给 `backgroundPic`（底色盖底图，见反面清单 #10）；⑤ 文本盒宽 < 估算宽 × 1.05（#36 余量不足；compose 已按 1.10 给余量）。 |
| `grid_icons` | ① **格盒 ≠ 图**（格底图尺寸必须 == 格盒；否则格间等距被拉伸破坏 → #11/#17 FAIL）；② 格宽写死像素 / 每格单独调宽（必须 `cols` 等分 + 余数给最后一格）；③ `cols` 变了就改格高（格高由「图标底 + 文字」反算，与 cols 无关）；④ 图标盒 ≠ 图（glyph 必须给 `canvas=图标档`）；⑤ 把宫格塞进卡（根层块；卡内写 `grid_icons` 会报错退出）；⑥ `tappable=true` 却把整格 button 写在装饰件之前（装饰件会压住命中区）。 |

> **第 3 批公共红线（三处措辞已写回各块 forbidden）**：
> **① 图的尺寸下限**：块内 glyph 尺寸 >= `_tokens.json` 的 `glyph_min_px = 24`。实测（`aa_audit --fail`）：`wifi@12` / `home@16` / `settings@16` / `bell@20` 全部判**真缺陷**，`home@20` / `wifi@16` 已是 WARN 边界。图标**不像字号可以降档**（降了就退化成硬阶梯），极小屏宁可省图标（见反面清单 #18/#38）。
> **② 根层块不进卡**：`tabs / bottom_nav / banner / toast / status_pill / divider_label / grid_icons` 都是根层块；卡内只收行块 / 列表块（`build_card` 类型校验直接报错退出）。
> **③ 「文本→右端控件」间隙口径全页一致**：banner 的「文案 → 关闭盒」与 divider_label 的「线 → 文字」都走 `m['text_chev_gap']`（与行族同一口径）→ `note_row_gaps` + `assert_row_gaps` 同页一致（不同口径会直接报错退出，不是静默放过）。

### 4.3 第 4 批 4 个块的禁止项（红线；完整版在 `blocks/<type>.json` 的 `forbidden`）

| 块 | 红线（写了就注定返工/编译不过/真机不对） |
|---|---|
| `toolbar` | ① **同页再写 `page_title` / 用 `page.title` 同时给工具条标题**（两者争同一条固定带 → compose 报错退出，不静默兜底）；② 把工具条放进滑动区（固定件进 scrollwindow → 上滑时工具条跟着滚走）；③ 给工具条加主/次按钮（那是 `bottom_actions` 的活；工具条只收图标动作）；④ action 图标自绘 / 用 emoji 字体兜底（图标唯一来源 = `components/icons`）；⑤ 图标盒 ≠ 图 / 图标盒 < `glyph_min_px`(24px) 硬塞；⑥ 返回/动作命中盒 < 16px；⑦ actions 超过 3 个（标题带放不下，多动作请收进 more 菜单）。 |
| `loading` | ① **骨架条矮于 10px**（药丸端弧线在 `aa_audit` 里退化成硬阶梯 → #21 真缺陷）；② 条盒 ≠ 图（拉伸 → 药丸两端变椭圆）；③ 条/卡盒用 1px 描边环做「轮廓」；④ 图标盒 ≠ 图 / < 24px 硬塞；⑤ 在块里跑动画 / 定时器（块库只出静态帧，转圈动画由业务换图驱动）；⑥ 让加载态吃触摸；⑦ 把加载态塞进卡（根层块）；⑧ 用 loading 冒充 `empty_state`（中间态 vs 结论态，语义不同）。 |
| `time_row` | ① **在块里画日历 / 月历网格 / 星期头**（那是 `components/ui_v1/Calendar` 的能力，块库不重造）；② 让块库解析 / 格式化时间（`value` 是**字符串**，时区、相对时间都在业务侧算好）；③ 同页行族里只有时间行带图标（`assert_icon_uniform` 直接报错退出——要么都带、要么都不带）；④ 值文案超长却不用 `value_short`（极小屏单行式会 #13 FAIL）；⑤ 为给箭头腾位去收窄 / 挪值文本盒；⑥ 把时间行做成两行以上（它是一行）；⑦ icon 用 emoji 字体兜底。 |
| `form_section` | ① **在组里另起一套行几何**（行高 / 文本左缘 / 右端预留 / 图标列必须与全页行族同源）；② 把根层块（`tabs`/`banner`/`toast`/`status_pill`/`divider_label`/`grid_icons`/`chart_card`/`image_gallery`/`keypad`/`loading`/`toolbar`）塞进 `blocks`（只收行块 / 列表块 → 报错退出）；③ 一个分组同时给 `title` 又给 card 包一层（组标题与卡标题连成两层标题）；④ 组间距手写像素（必须走 `group_gap` = spacer-2）；⑤ `surface=true` 时又给行底色（会盖住卡底圆角）；⑥ 组内有的行两行式、有的单行式（极小屏整页降单行式，禁混用）。 |

> **第 4 批公共红线**：**① 顶部固定带只有一个**（`toolbar` 与 `page_title` 二选一；`toolbar` 只能出现一次）；**② 根层块**= `loading` / `form_section`（+ `chart_card` / `image_gallery` / `keypad`），卡内写直接报错退出；**③ 行 = 全页一套几何**：`time_row` 与 `setting_row` 同一套行模板、`form_section` 组内行复用同一批行 builder（同页 `assert_row_gaps` / `assert_icon_uniform` 一致，不一致直接报错退出）。

## 5. 相对尺度体系（唯一的数值源 = `blocks/_tokens.json`）

| 维度 | 采用值 | 出处 |
|---|---|---|
| 色 | 页面 `#F3F3F3` / 容器白 / 主文 `#1A1A1A` / 次文 `#666` / 分割线 `#E7E7E7` / brand `#0052D9` | TDesign v1.17.0（rpx÷2 = px） |
| 型 | 字号**按屏选档**（不线性放大）：28/20/16/14 px @1024×600；14/12/12/10 @320×240；层级 = **字号档 + 字重 + 灰阶**（级差 <1.3 时不再堆字号） | TDesign 档位 + `SPEC-CHECK §8` |
| 距 | spacer 8 / 12 / 16 / 24；分组间距 = spacer-2 | TDesign spacer |
| 形 | 容器圆角 = min(radius-default 6, 行高×0.18) 且 ≥4；分割线 1px；**白卡不给描边**（见反面清单 #10） | `SPEC-CHECK §8` |
| 组件级 | 行高 = 屏高 10%（极小屏 11.7%，并给文本可读性兜底）；行条宽 = 屏宽 − 2×spacer-2；左内边距 ≈ 屏宽 3.1%；图标底 0.6×行高；图标 0.4×行高；箭头 max(12, 屏宽 2.5%) × max(16, 屏高 2.7%) | `scrollwindow-layout-checklist §2.1` + `SPEC-CHECK §7` |
| 滚动 | `dragMaxDis` = **越界拖拽上限**（全页 max(24, 屏宽×6%)），**不是行程**；行程 = 内层 window − 视口，引擎自算 | `scroll-drag-interaction-spec` R1/R2/R6/R10 |
| 交互控件（第 2 批） | 滑块盒高 = max(图标档, 行高×0.60)（且 ≥ 滑块图高，可见条高 ≥ 10px）；输入框盒高 = 单选项高 = max(标题高+spacer, 行高×0.70)；复选/圆点盒 = max(12, 行高×0.50)；列表模板行高 = max(标题高+spacer, 行高×0.70)（余 2px 可滑动提示）；滚轮模板行高 = max(标题高+spacer, 行高×0.60)；滚轮列宽 = 内容宽 20%（≥ 2×复选盒） | `seekbar-fields` / `edittext-fields` / `listview-wheel-picker` / `radiogroup-checkbox-fields` + 同页行族口径 |
| 结构/导航/提示（第 3 批） | 段带高 = max(屏高 9%, b1+2×spacer)、指示条高 = max(2, 屏高 0.005)、胶囊带高 = max(屏高 7%, b2+spacer)、提示条高 = max(屏高 8%, b1+2×spacer)、分割线带高 = max(屏高 5%, b2)、底导带高 = max(屏高 10%, 图标+间距+文字+2×spacer)、浮层盒高 = b1+2×spacer2、浮层位置 = 屏高×0.60、格高 = 2×spacer+图标底+文字、**块内 glyph 尺寸下限 = 24px**| `_tokens.json` §size ·第 3 批 + `aa_audit` 实测（见 §4.2 公共红线 ①） |

**行族文本盒宽 = 全页族预留（2026-10-01 第 2 批修正）**：右缘按 **全页**`fam_reserve`（max(箭头, 开关, 复选框)）算，而不是「本行自己有什么右端控件」——否则「只有箭头的行」会得到比「有开关的行」宽 56px 的文本盒，check_all #27 会报「口径偏离同族」（第 1 批两版示例各有 2 条 WARN 就是这个原因，本批修掉）。代价：只有箭头的行多留一段死区（文本左对齐且短，观感无影响）。

**第 2 批交互块度量（`_tokens.json` 只给基准，公式在 `compose.build_metrics`）**：滑块盒 = max(图标档, 行高×0.60)（1024→36，320→16）；thumb = 图标档（24/12）；输入框盒 = 单选项高 = max(标题高+spacer, 行高×0.70)（42/24）；复选/圆点盒 = max(12, 行高×0.50)（32/16）；列表模板高（40/24，余 2px）；滚轮模板高（36/24，整除）；滚轮列宽（200/56）。

**第 3 批结构/导航/提示块度量（实测值，公式在 `compose.build_metrics`）**：

| 度量 | 1024×600 | 320×240 | 说明 |
|---|---|---|---|
| `tab_h`（段带高） | 56 | 32 | max(r4(屏高×0.09), b1 高+16) |
| `ind_h`（指示条高） | 3 | 2 | max(2, round(屏高×0.005))——不画圆角（2~3px 小弧会退化成硬阶梯，与滑轨可见条同口径）；盒 = tab 项盒本身，形状由整条裁切（见 §4.2） |
| `pill_h`（胶囊带高） | 44 | 24 | 圆角 = 带高/2 |
| `banner_h`（提示条带高） | 48 | 32 | 4 语义色浅底 + 图标（24/24） |
| `divider_h`（分割线带高） | 32 | 16 | 线长 440/114（同一页两侧等长，随宽度伸缩） |
| `nav_h`（底导带高） | 64 | 60 | = 图标+间距+文字+16，**与项数无关**；320 上占屏高 25%（极小屏两带叠置的代价，见 §8 第 0 条④） |
| `toast_h` | 56 | 40 | b1 + 2×spacer2；盒宽 132/120（文本反算） |
| 宫格格（格盒 == 图） | 314×72（3 列 6 格） | 80×68（3 列 6 格） | 格高 = 16 + 图标底 + 文字高（图标底 36/36 = 图标 24×1.5） |
| 块内图标档 | 24 | 24 | **与屏高无关**（`glyph_min_px`）：小屏不降图标，靠「省图标」降级（见 §4.2 ①） |


**布局自动决策**：内容总高 > 视口 → 自动包 `scrollwindow`（视口高）→ 内层 `window`（高 = 内容总高）；≤ 视口 → **不上滑动窗口**（白放一层没意义，§2.1 第 1 步）。
**视口扣除（第 3 批新增）**：有 `bottom_nav` 时视口再减 `nav_h`（视口 = 屏高 − 标题带 − nav 带 − 底栏带），并在 compose 日志里打印一行 `[NOTE] bottom_nav 固定带 N px 贴底栏上沿 → 视口缩至 M`。

### 5.1 图标来源 = `components/icons` 资产库（2026-10-01 改口径）

需求方 2026-10-01：「这些网络/设备的 icon 来源？效果差异和实际差异太大」——块库原先的 `glyph()`
走 `ui_tools/gen_res.glyph_icon()` 的兜底（默认 style=emoji → 查 `_GLYPH_EMOJI` + 本地 emoji 字体，
缺字体退简笔线框），与**真机/产品用的那套图标**不是同一套图形。
现在块库图标**唯一来源 = `components/icons`**（v0.3.1 = Tabler Icons 3.46.0 单色烘焙 PNG；
矢量源 `vendor/tabler/**`，生成器 `components/icons/scripts/gen_icons.py`），实现见同目录 **`iconlib.py`**。

| 项 | 口径 |
|---|---|
| 来源 | `components/icons`——**禁自绘、禁 emoji 字体兜底**（真机没那套字体） |
| 档位（按盒尺寸） | 盒 ≥ 44px → **56 档**；≥ 26px → **24 档**；否则 **22 档**；盒尺寸**正好等于**档位（22/24/56）且库里有该状态产物 → 直接取库里 `out/<档>/` 那张（按 alpha 换色，与重新渲染**像素等价**，实测 maxdiff = 0） |
| 缺档 | 盒不是 22/24/56（示例里：空态 1024→36px、320→16px）→ 用库自带生成器按**盒尺寸**现出（缺档补齐，**不放大控件盒去凑档**） |
| 尺寸铁律 | 产物图**严格 == 控件盒**（#11/#17；引擎对「图 ≠ 盒」是拉伸填充） |
| 颜色 | FlyThings 无 tint → 生成时烘焙（brand `#0052D9` / fg2 `#666666` / 语义 -7 档；库预置产物是白的） |
| 两态 | `off` = 描边态（行/宫格/空态默认）、`on` = 实心态（底导选中自动用 `_on`；`grid_icons` 项可显式 `state:"on"`；checkbox 勾用 `control.check` 的 `_on`） |
| 回退 | 库里**查不到**该语义名 → 回退 `gen_res` 线框，且 compose 输出里**明说「回退线框」**（不静默）；六版示例实测 **0 处**|
| 允许值 | **`blocks/_icons.json`**（从 `catalog.json` 摘：203 语义名按 5 分类列全 + 两态清单 + 档位/回退口径）；各 `blocks/*.json` 的 `icon` 字段都指向它；`compose` 每次运行会把「图标来源 / 档位 / 名称×尺寸×态 组合」打进日志 |

**六版示例用到的名字 → 库名 / 档位**（块里的 `icon` 只写短名，库自己解析别名）：

| 块里的 `icon` | 库语义名 | 档位（盒尺寸） | 用在哪 |
|---|---|---|---|
| `info` | `system.info` | 24 档（1024 空态 36px，**缺档现出**）/ 22 档（320 空态 16px） | 空态、提示条、宫格 |
| `wifi` | `system.wifi` | 24 档（24px） | 行族图标、宫格 |
| `list` | `system.list` | 24 档 | 行族图标、宫格、底导 |
| `bell` | `system.bell` | 24 档 | 行族图标、宫格、底导、提示条 |
| `settings` | `system.settings` | 24 档 | 行族图标、宫格 |
| `user` | `system.user` | 24 档 | 宫格、底导 |
| `star` | `system.star` | 24 档（`state:"on"` 实心态） | 宫格 |
| `home` | `system.home` | 24 档（`_on` 选中态） | 底导 |
| `check` | `control.check` | 24 档 | 提示条（success） |
| `close` | `control.close` | 24 档 | 提示条关闭钮 |
| `warning` | `system.warning` | 24 档 | 提示条（warn / danger） |

**一个实测坑（已写进 `blocks/_icons.json`）**：`star` **描边态 @24px**会被 `tools/qa/aa_audit` 判
**真缺陷**（`hard_diag=4` 占斜线边界 67% ≥ 60% —— 细描边星形在小盒上退成硬阶梯）→ 小盒上的 star 请用
**实心态**（spec 里 `{"icon": "star", "state": "on"}`，nav 示例就是这么写的）或改用 `heart`（两态都干净）。
其余 20+ 个常用名 @16/24/36px 实测干净或只 WARN（不构成 FAIL）。

**箭头仍不走图标库**：`chev_{w}x{h}.png` 继续用 `chevron_image()` 的箭头专属口径（45° + 圆头 +
笔画 ≈ 盒宽 12% 且 ≥2px）——库的 `control.chevron-right` 是 24 网格的细描边，在 12×16 小盒上会退成
1px 硬斜边（`aa_audit` 报 `hard_diag`），见 §8-3；`checkbox` 勾选符号（`mark_image` 里的 `check`）
已改走库（`control.check` 的 `_on`）。

## 6. 自测结果（六版示例，全自动）

> 命令：`python templates/ui_blocks/compose.py <示例>/spec.json --project <示例>/project --render --check`\
> 再加一遍 `python tools/ui_tools/check_all.py <示例>/project`（存到 `check_all.log`）。**六版都是 compose exit 0 + check_all exit 0（0 FAIL / 0 需审批 WARN）**；
> 第 3 批改完 `compose.py` 后，**旧四版全部重跑一遍（回归）仍是 exit 0**，且旧四版产物与上一版**逐字节一致**（`git status` 无改动 = 新代码对旧块零影响）。\
> **图标来源改口径（§5.1）后六版又全部重跑一遍**：仍是 compose exit 0 + check_all exit 0（0 FAIL），
> 图标回退线框 **0 处**，六版都补了 `main.full.render.png`（含旧两版）——核对见 **§6.5**。\
> **`list_item` 逐行内容（2026-10-01 二次修，需求方「现在就是列表显示不出来了」）后六版再重跑一遍**：
> 仍是 compose exit 0 + check_all exit 0（0 FAIL），`#37 itemH` 比对照旧输出（余数 = 可滑动提示）；
> **旧四版（settings×2 / nav×2）的长图与单屏图与上一版像素零差异**（`ui_diff` PASS，容差 ±2 + 抖动补偿），
> 只有两个 interactive 版的长图在**列表行区域**有差异（1024：24 处 / 4272 px；320：8 处 / 1324 px）——逐块核对见 §6.2。

### 6.1 第 1 批（基础块，10 块）

| 项 | 1024×600 | 320×240 |
|---|---|---|
| 块数 / 行数 | 10 个块类型 / 7 行（2 卡 + 1 独立分组标题 + 空态 + 底栏 + 弹窗） | 同左（**同一套块**） |
| 控件数（含嵌套） | **62**（textview 45 / button 11 / window 5 / scrollwindow 1） | **59**（textview 42 / button 11 / window 5 / scrollwindow 1） |
| 关键度量 | 行高 60 ｜ 字号 28/20/16/14 ｜ 圆角 6 ｜ 图标底/图标 36/24 ｜ 箭头 24×16 | 行高 28 ｜ 字号 14/12/12/10 ｜ 圆角 5 ｜ 图标底 16（图标省略）｜ 箭头 12×16 ｜ **单行式**|
| 内容 → 视口 / 行程 | 716 → 452 / **行程 264**，dragMaxDis 60 | 404 → 168 / **行程 236**，dragMaxDis 24 |
| 出图 | **16 张**（图 == 盒，#11 PASS 0 处不匹配） | **15 张**（同上） |
| logic 骨架 | `src/logic/mainLogic.cc`，**11 个按钮回调**齐全 | 同左，11 个 |
| `json2img --report` unsupported | **1 类**：`bold x4`（渲染器无 `*Bold*.ttf` 变体 → 用同字体；真机由字库承担） | 同左：`bold x4` |
| 渲染图 | `main.render.png` **1024×600 == resolution**✓ | `main.render.png` **320×240 == resolution**✓ |
| `check_all` | **exit 0（0 FAIL / 0 需审批 WARN）**；#21 AA 真缺陷 0（扫 20 张，WARN 5 / EXEMPT 2） | **exit 0（0 FAIL / 0 需审批 WARN）**；#21 AA 真缺陷 0（扫 16 张，WARN 0 / EXEMPT 2） |
| #26 行程 / #27 同族 | 行程=内层−视口 ✓ ｜ 同族口径 0 条离群、文本×图标 0 处相交 | 同左 ✓ |
| 证据 | `examples/settings_1024x600/{main.render.png,main.full.render.png,last-run.log,check_all.log}` | 同左 |

> 注：示例工程 `resources/images/` 里可能留有**历史多余切图**（compose 只增量出图、不清理旧文件）——以 `last-run.log` 的「出图 N 张」清单为准（旧两版各余 4/1 张旧版图标/分隔线）。

### 6.2 第 2 批（交互类 7 块）

| 项 | interactive_1024x600 | interactive_320x240 |
|---|---|---|
| 块数 / 行数 | 17 个块类型里用了 **12 个**（7 新 + card/section_header/toggle_row/setting_row/bottom_actions/dialog） | 同左（**同一份块清单**） |
| 控件数（含嵌套） | **64**（textview 42 / button 6 / window 6 / scrollwindow 1 / seekbar 2 / edittext 1 / checkbox 2 / radiogroup 1 / listview 3） | **62**（textview 40 + 其余同左） |
| 关键度量 | 行高 60 ｜ 滑块盒 960×36（thumb 24）｜ 输入框盒 42 ｜ 项高 42 ｜ 复选盒 32 ｜ 列表模板 960×40（rows 4，**行内 subItem**：图标 24 / 标题 804×24 / 值 52×20 / 箭头 24×16）｜ 滚轮列 200×180（rows 5 / 模板高 36）｜ 选中条 200×36 | 行高 28 ｜ 滑块盒 272×16（thumb 12）｜ 输入框盒 24 ｜ 项高 24 ｜ 复选盒 16 ｜ 列表模板 272×24（rows 4；**极小屏省行内图标**：标题 188×16 / 值 44×16 / 箭头 12×16）｜ 滚轮列 56×120（rows 5 / 模板高 24）｜ 选中条 56×24 |
| 内容 → 视口 / 行程 | 1366 → 452 / **行程 914**，dragMaxDis 60 | 858 → 168 / **行程 690**，dragMaxDis 24 |
| 列表行内容（`items` → subItem） | 模板行 = `items[0]`（客厅面板 / 在线）：`…SubIcon 16,8,24×24（ic_wifi_24.png）｜…SubTitle 48,8,804×24「客厅面板」｜…SubValue 860,10,52×20「在线」（右对齐）｜…SubChevron 920,12,24×16`；item.text = `""` | 同左（无图标列）：`…SubTitle 8,4,188×16「客厅」｜…SubValue 204,4,44×16「在线」｜…SubChevron 252,4,12×16`；compose 打 `[NOTE] list_item … 行内图标省去（图标档 24 + 上下各 1×spacer 8 > 模板行高 24）` |
| 出图 | **23 张**（= 旧 22 + 行内图标 `ic_wifi_24.png`；图 == 盒，#11/#17 PASS 0 处不匹配；`thumb.size == 滑块图` ✓） | **22 张**（同上；320 省行内图标 → 无新增图） |
| logic 骨架 | **6 个按钮回调 + 1 个输入框回调**（`onEditTextChanged_EditRowInputRow7Box`）齐全 | 同左 |
| #37 listview item 高 | `ListListItem13 item 高 40 = int(162/4)−0 ✓，余 2 px = 可滑动提示（预期）`；`ListWheelPicker14Col1/2 item 高 36 = int(180/5)−0 ✓，余 0 px` | `ListListItem13 item 高 24 = int(98/4)−0 ✓，余 2 px`；`ListWheelPicker14Col1/2 item 高 24 = int(120/5)−0 ✓，余 0 px` |
| `check_all` | **exit 0（0 FAIL / 0 需审批 WARN）**；#21 AA 真缺陷 0（扫 23 张，WARN 4 / EXEMPT 2） | **exit 0（0 FAIL / 0 需审批 WARN）**；#21 AA 真缺陷 0（扫 22 张，WARN 0 / EXEMPT 2） |
| 渲染图 | `project/ui/main.render.png` **1024×600 == resolution**✓ | `project/ui/main.render.png` **320×240 == resolution**✓ |
| 整页证据图 | `main.full.render.png` 1024×1514（展平 scrollwindow；供人工验收） | `main.full.render.png` 320×930 |
| 证据 | `examples/interactive_1024x600/{main.render.png,main.full.render.png,last-run.log,check_all.log}` | 同左 |

### 6.3 `json2img --report` 未支持/降级清单（**如实列出，不吞**）

> `json2img` v0.1.0 是**静止态近似**渲染器；下面这些**不是缺陷**，写在这里保证「看一眼渲染图就以为是 bug」不会发生。

| 控件 | 报告项 | 渲染表现 | 真机行为 |
|---|---|---|---|
| `textview` | `bold`（交互版 x5 / 基础版 x4） | 用同字体（无 `*Bold*.ttf` 变体）；标题/分组标题看上去不粗 | 字库承担字重 |
| `seekbar` | `defProgress`（x2） | 只画静止进度（60% / 45%） | 引擎按 `defProgress`/`max` 画；可拖 |
| `seekbar` | `拉伸填充 sk_fill_<W>x<H>.png`（x2，属「拉伸」类不是 unsupported） | 渲染器把「有效图」按 defProgress **缩放**近似 | 引擎是**横向裁剪**（不是拉伸）；图 == 盒已由 #11/#17 核对通过 |
| `edittext` | （无） | 画 `text`；空则画 `hintText` | 点击弹系统内置键盘 |
| `checkbox` | （无新增降级项） | **按 `checked` 切图**：选中画 `pic2`（品牌底 + 白勾），未选画 `pic0` | 引擎同口径 |
| `radiogroup` | `runtimeState`（x1） | **`radiobuttons[]` 逐项画圆点 + 选项文字**（选中走 `pic2` + `colorTab.color2`）；组内联动/点击态不还原 | 引擎同口径 + 运行期组内联动 |
| `listview` | `runtimeRows`（x3） | 按 `rows`/`rowSpacing`/`itemH` **逐行铺模板**（行底 + `subItem[]` 的图/文本）；`list_item` 块的模板行 = `items[0]` → **静态图里 4 行都看得到「图标 + 标题 + 值 + 箭头」（模板是一份、行行相同）**；滚轮的模板 `text` 仍是空串（只看到静态选中条） | 引擎按运行期数据填行（**逐行各异**）+ 滚动 + 循环 |
| `listview.item.subItem` | `picTab.pic0`（交互 1024 x8 / 交互 320 x4） | 行内子项图（行首图标 / 行尾箭头）按背景图绘制（仅常态） | 行内子项图由引擎直接贴（图 == subItem 盒） |

> **数组子项渲染（2026-10-01 补，缺陷 B）**：`radiobutton` / `checkbox` / `listview.item+subItem` 过去只走
> 「通用兜底」→ 渲染图里选项区、勾选态是空的（经需求方原话「列表依旧没有刷新出来」）。现在三者都专有实现；
> 模板缺 `pic2` 时 `checkbox` 的勾走 `components/icons` 的 `control.check_on`（只缩不放；勾色按盒底亮度二选一，
> 否则白勾落在浅灰盒上「看不见」）——夹具实测可见。
> **列表行文本（2026-10-01 二次修，需求方「现在就是列表显示不出来了」）**：块库原先只按「item.text 空串 + 子项空文本」
> 出行模板 → 渲染图/首次上屏是**一列空行**（只有箭头）。现在 `list_item` 块吃 `items[]`，把行内容落成
> subItem（图标 + 标题 + 值）→ 静态图可见；⚠ **引擎只有一份行模板**，所以静态图 4 行相同（= `items[0]`），
> 逐行各异是**运行期数据**（`obtainListItemData` 填），json 表达不了。

对齐解码：全部文字控件用 **36/37/38（真机实测表）**，`json2img` 报「待校准 0 处 / 表外 0 处」（六版示例均是）。
**第 3 批新增块：渲染器零 unsupported 新增**——7 个新块全部由 `textview` / `button` / `window` 组成（不引入 checkbox/radiogroup/listview/seekbar 这类「v0 未专有实现」的控件），所以 `json2img --report` 的清单比第 2 批更短（只剩 `bold` 一类）：

| 示例 | `json2img --report` unsupported/降级 | 拉伸填充 |
|---|---|---|
| nav_1024x600 | `textview bold x3`（TextTitle / SectionHeader2 / SectionHeader6 → 用同字体） | 0 处 |
| nav_320x240 | `textview bold x3`（同上） | 0 处 |

### 6.4 第 3 批（结构 / 导航 / 提示类 7 块）

| 项 | nav_1024x600 | nav_320x240 |
|---|---|---|
| 块用量 | 24 个块里用了 **15 个**（7 新 + page_title / card / icon_row / toggle_row / setting_row / section_header / bottom_actions / dialog） | 同左（**同一份块清单**） |
| 控件数（含嵌套） | **124**（textview 86 / button 23 / window 14 / scrollwindow 1） | **116**（textview 78 / button 23 / window 14 / scrollwindow 1） |
| 关键度量 | 行高 60 ｜ tab 带 56 / 指示条 3 ｜ 胶囊 128×44 / 144×44 ｜ 提示条 992×48 ｜ 分割线 440+96+440 ｜ 宫格 314×72（3 列 2 行）｜ nav 带 64 ｜ 浮层 132×56 | 行高 28 ｜ tab 带 32 / 指示条 2 ｜ 胶囊 76×24 ｜ 提示条 288×32 ｜ 分割线 114+52+114 ｜ 宫格 80×68 ｜ nav 带 60 ｜ 浮层 120×40 |
| 内容 → 视口 / 行程 | 916 → 388（=600−76−72−64）/**行程 528**，dragMaxDis 60 | 660 → 108（=240−32−40−60）/**行程 552**，dragMaxDis 24 |
| 出图 | **44 张**（#11/#17 图 == 盒 0 处不匹配；格盒 == 格底图 0 处不匹配） | **43 张**（同上） |
| logic 骨架 | **23 个按钮回调**（3 tab + 6 宫格 + 4 底导 + 3 提示关闭 + 主/次 + 弹窗 2 + 3 行命中区）齐全 | 同左 23 个 |
| `check_all` | **exit 0（0 FAIL / 0 需审批 WARN）**；#21 AA 真缺陷 0（扫 44 张，WARN 7 / EXEMPT 3）｜#22/#23/#25/#24 真缺陷 0 | **exit 0（0 FAIL / 0 需审批 WARN）**；#21 AA 真缺陷 0（扫 43 张，WARN 3 / EXEMPT 3） |
| #27 同族 / #29 触摸 / #31 对齐 | 均 PASS（0 条离群、0 处文本×图标相交、无显示件压交互控件） | 同左 |
| #30 caption / #35 盒下限 / #36 文本余量 | PASS 唯一 / PASS ≥ 12×16 / PASS 余量充足 | 同左 |
| 渲染图 | `project/ui/main.render.png` **1024×600 == resolution**✓ | **320×240**✓ |
| 整页证据图 | `main.full.render.png` 1024×1128（展平 scrollwindow；供人工验收） | 320×792 |
| 证据 | `examples/nav_1024x600/{main.render.png,main.full.render.png,last-run.log,check_all.log}` | 同左 |


### 6.5 图标来源核对（2026-10-01 改口径后重跑六版，口径见 §5.1）

| 示例 | 图标处数 | 档位（盒尺寸） | 回退线框 | 出图 / 控件数 | #21 AA（真缺陷） | 整页图 |
|---|---|---|---|---|---|---|
| settings_1024x600 | 1（`info`） | 24 档 @36px（**缺档现出**） | **0**| 16 / 62 | 0 张（WARN 5 / EXEMPT 2） | 1024×864 |
| settings_320x240 | 1（`info`） | 22 档 @16px（**缺档现出**） | **0**| 15 / 59 | 0 张（WARN 0 / EXEMPT 2） | 320×476 |
| interactive_1024x600 | 1（`wifi` = 列表模板行图标；其余行只核名） | 24 档 @24px | **0**| 23 / 64 | 0 张（WARN 4 / EXEMPT 2） | 1024×1514 |
| interactive_320x240 | 0（极小屏省行内图标） | — | **0**| 22 / 62 | 0 张（WARN 0 / EXEMPT 2） | 320×930 |
| nav_1024x600 | 20（14 种 名×尺寸×态） | 24 档 @24px ×20 | **0**| 44 / 124 | 0 张（WARN 7 / EXEMPT 3） | 1024×1128 |
| nav_320x240 | 17（同上 14 种） | 24 档 @24px ×17 | **0**| 43 / 116 | 0 张（WARN 3 / EXEMPT 3） | 320×792 |

> 六版都是 **compose exit 0 + check_all exit 0（0 FAIL）**。`json2img --report` 的 unsupported/降级清单：
> settings 两版 `bold x4`（1 类）；nav 两版 `bold x3`（1 类）；interactive 两版 **7 类**（`bold x5` +
> `subitem picTab.pic0`（1024 **x8**= 4 行 ×(图标+箭头) / 320 **x4**= 4 行 × 箭头）+ `listview runtimeRows x2/x1` +
> `seekbar defProgress x1`×2 + `radiogroup runtimeState x1`）+「拉伸填充」2 处（`sk_fill_960x36.png`，引擎语义 = 裁剪）——逐条解读见 §6.3。
> 列表行文本已从「模板空文本」变为「模板行 = `items[0]`」：`listview runtimeRows` 的 note 从「模板无行文本」
> 变成「**8 处文本已画**」（4 行 ×(标题+值)）——这是缺陷 B 之后的**第二次修**（`list_item` 块吃 `items`）。
> 旧清单里的 `checkbox v0 未专有实现 x2` / `checkbox picTab.pic0 x2` / `radiogroup v0 未专有实现 x1` /
> `listview item/subItem x3` **已随缺陷 B 的修复去掉**（改成逐项 / 逐行真画）。
>
> 另：compose 打一行 `[NOTE] 固定带自检：…`（缺陷 A），`full_render.py` 打一行 `固定带让位：y A → B`——
> 六版数值：settings 1024 `528 → 792（+264）`；settings 320 `200 → 372（+236，整页 476）`；
> interactive 1024 `528 → 1442（+914）`；interactive 320 `200 → 890（+690）`；
> nav 1024 `464 → 992（+528，带高 136）`；nav 320 `140 → 692（+552，带高 100）`。
>
> **图标像素等价实证**：库里 `out/24/` 的预置产物按 alpha 换色，与用 `gen_icons.py` 按同尺寸重新渲染**逐像素一致**
> （`star`/`wifi`/`bell`/`info`/`check` @24px 实测 maxdiff = 0）——所以「取库产物」与「按盒尺寸现出」没有口径差。
> **star 坑**：`star` 描边态 @24px 会被 aa_audit 判真缺陷（`hard_diag=4` / 斜线边界 67%）→ nav 示例的宫格写的是
> `{"icon": "star", "state": "on", "text": "收藏"}`（实心态，实测 WARN 21%，不判缺陷）。


## 7. ⛔ 反面清单（照抄我们踩过的坑，别重犯）

| # | 坑 | 症状 | 本库怎么防 |
|---|---|---|---|
| 1 | **行做成「左标题 + 右值单行式」，同页其它行是两行式**| 该行文字明显外凸/不齐；箭头和值挤一起 | 行族口径**全页统一**（`scan_row_family`：文本左缘/右值预留/图标列一致）；极小屏**整页**降单行式，禁混用 |
| 2 | **为给箭头腾位把值框收窄/挪位**（挤文本去让位） | 对齐走样；引擎先画底图后画文字 → 箭头被文字盖住 | 冲突只改**布局形态或盒子**；文本盒宽度由行条宽 − 预留反算，绝不"挤" |
| 3 | **文本盒与图标/箭头盒相交**| 箭头/图标看不见，或被文字压住 | 文本左缘 = 图标底右缘 + spacer；值盒右缘 = 箭头/开关盒左缘 − spacer；`check_all #27` 复核 0 处 |
| 4 | **图标/箭头盒太小**| glyph 被压到 6×6 发糊 | 盒下限：图标 ≥12、箭头 ≥12×16（对齐 TDesign 32rpx=16px 档） |
| 5 | **图 ≠ 控件盒**| 引擎**拉伸填充**→ 圆角/描边糊、字形压扁 | 所有切图按控件盒尺寸出（`card_992x180.png`…）；`check_all #11` 复核 0 处不匹配 |
| 6 | **把 `dragMaxDis` 当行程/内容尺寸填**| "滚不到底/末尾行看不到"或整屏被拽出去 | 行程 = 内层 window − 视口（引擎自算）；`dragMaxDis` 只取手感值 `max(24, 屏宽×6%)` 且 < 控件高 |
| 7 | **固定件（标题/底栏）放进滑动区**| 上滑时标题和按钮跟着滚走 | 标题/底栏/弹窗是根层节点，只有中段内容进 `scrollwindow` |
| 8 | **`scrollwindow` 下平铺非 window 子控件**| 新加的行整块不显示 | 内容全部进内层 `window`，其高 = 内容总高（增删行自动同步） |
| 9 | 内容放得下也硬上 `scrollwindow` | 白放一层、手势白吃 | 内容总高 ≤ 视口 → 直接摆（§2.1 第 1 步） |
| 10 | **`colorTab` 底色 + 底图同时给**| 方形底色盖掉底图圆角与描边（表现＝"倒角没生效"） | 卡片／面板的底色由底图承担，行按钮底色 `-1` |
| 11 | **白卡配 1px 描边环**| 行高 <40 时 1px 环让 AA 审计退回「直通 α 脏边」判据报 dirty | 描边按 §8 **降级为可选**（灰底衬托 + 分组间距），容器/面板/次按钮一律素面 |
| 12 | **在白色底上放白色按钮**| 次按钮"看不见" | 次按钮用 TDesign light 变体（浅品牌底 `#F2F3FF` + 品牌字） |
| 13 | **色值写 `0` 当"透明"**| 真机渲染成不透明**黑块**| 透明一律 `-1`；`backgroundColor/bgColorTab.color0` 禁 0（`zero_color_audit` 拦） |
| 14 | **alignment 用未校准值（0/5/6…）**| 渲染器只能按位模型猜（"待校准"清单） | 统一用真机实测表 **36/37/38**（本库已全量切换 → 待校准 0 处） |
| 15 | **放大渲染图用 BOX**| 面积平均 = 把素材糊掉，被误判成素材缺陷 | 渲染放大一律 NEAREST（本库渲染 scale=1 即为原尺寸） |
| 16 | **装饰件后定义（z 更高）且没写 `touchable:false`**| 吃掉下层触摸；`check_all #15/#29` 报警 | 装饰件一律**先定义**+ `touchable` 显式 false；整行命中 `button` 最后定义（z 最高） |
| 17 | **改了 json 不 pack**| "改了像没改"（ftu→json 自动同步把改动打回） | 交付前 `check_all`（内含 `fui pack` 与 ftu/json 时间戳核对 #9） |
| 18 | **极小屏硬上两行式**| 行高被文本顶到 ~18% 屏高，一屏只剩 4 行 | 屏高 <320 自动降**单行式**+ 字号降 2 级 + 省图标 |
| 19 | **极小屏用长值文案**| `check_all #13` 文本最小尺寸 FAIL（如"已连接 · 192.168.1.100"在 136px 盒里放不下） | 提供 `value_short`，本库在极小屏自动启用；`compose.py` 还做**事前自检**并点名是哪条文案 |
| 20 | **单分辨率工程把 json 放到 `ui/<W>x<H>/`**| `check_all #9` 的 `fui pack` 只认扁平 `ui/*.json` → 误报 `pack 成功 → main.ftu` FAIL | `--ui-layout auto`：没有现成的 `ui/<W>x<H>/` 就按**扁平**落（`res` 留给真多分辨率工程，此时 #9 的误报是既有工具的已知限制） |
| 21 | **小盒上用 1px 描边环做「未选态」**（复选/单选/小图标） | `aa_audit` 报「成片直通 α」/`hard_diag` 占比 ≥60% → #21 **真缺陷**（radius=8、32px 方框 1px 环 实测 50% WARN；同一图放 16px 盒就变直通 α 缺陷） | 未选态用 **switchOff 实底**（`gen_res.rounded_rect_cov`），不用 `bordered_cov` 的 1px 环（见 §8-3） |
| 22 | **极小内点/小弧线**（复选勾画 7px、单选内点 7px、矮于 10px 的药丸条） | 同上（7px 内点实测 78~100% hard_diag = #21 真缺陷；8px 药丸条 67~75%） | 圆点内点只在标记盒 ≥24px 时给（极小屏用实底色区分态）；滑轨可见条高 **≥ 10px**；这些阈值是本库实测写回 `compose.py` 的 |
| 23 | **`checkbox` 的 id 落在 20000~30000 段**| `check_all #5` 按 id 段把 checkbox 当 button → 要求 `onButtonClick_<caption>`（而 checkbox 的语义回调是 `onCheckedChanged`），要么编译不过要么得编个假回调 | checkbox id 取 **94500**段（radiobutton 94100、subitem 24000）——真机 id 段无语义，只要求页内唯一 |
| 24 | **给 checkbox 行再压一个整行透明 button**（照抄 `toggle_row` 的「装饰件 + 整行命中」） | 复选框永远选不上（button 在 z 更高、吃掉 DOWN）——而 `toggle_row` 那种写法是**对的**，因为它的开关只是呈现态、由代码切图 | `checkbox_row` **不给整行 button**（勾选框自己就是命中区）；`radio_row` 同理不加整行 button |
| 25 | **tab 指示条定义在 tab 之后**（静态件没写最前） | z 更高 → 盖住 tab 文字、可能吃触摸；且选中底把指示条压没（「看不见指示条」） | 指示条**紧跟容器底**定义（先于所有 tab 与 button），`touchable:false` 显式写；选中底**高度让出 `ind_h`**（与指示条几何不重叠） |
| 26 | **2~3px 高的小弧/圆角当指示条**（或把滑轨可见条压到 10px 以下） | `aa_audit` 报成片 hard_diag / 直通 α → #21 **真缺陷**（与 #22 极端内点同一类） | 指示条用**直角实条**（radius 0）；滑轨可见条高 **≥ 10px**|
| 27 | **块内 glyph 跟着小屏降档**（12/16px 图标） | `aa_audit` 真缺陷：`wifi@12` / `home@16` / `settings@16` / `bell@20` 实测 FAIL（图标笔画 <1px 退成硬阶梯） | 第 3 批引入 `glyph_min_px = 24`（块内图标尺寸**不随屏降**）；极小屏靠「省图标」降级，不靠缩小图标 |
| 28 | **浮层（toast）写在普通层里**/ `visible` 写 true | 被内容/弹窗盖住（提示根本看不见）；或一进页就弹一层遮屏 | toast = 根层整屏 window（modal=false + touchable=false） + **最后定义 = 最上层**+ `visible:false` 默认 |
| 29 | **底导与底栏两带叠在一起**（或 nav 放进滑动区） | 按钮被盖住/点不动（重叠）；上滑时 nav 跟着滚走（进滚动区） | nav 贴底栏上沿 + **视口扣除 nav 带高**（`compose` 日志会打 `[NOTE] bottom_nav … → 视口缩至 N`，看得见） |
| 30 | **块内图标自绘 / 用 emoji 字体兜底**（`gen_res.glyph_icon` 默认 style=emoji） | 观感与真机/产品那套图标完全不同（2026-10-01：「效果差异和实际差异太大」） | 图标**唯一来源 = `components/icons`**（`iconlib.py`，见 §5.1）；库里没该语义名 → 回退线框**并在日志里明说**（不静默）；小盒上的 `star` **描边
| 31 | **底栏 y 与内容视口各算一套**（底栏 `H − bar_bot`，视口忘了扣底栏高） | 内容流按错视口排 → **最后一行/卡片底落进底栏带被盖住**（2026-10-01 看图：「内容区伸进底部固定条，把最后一行盖住」；展平长图里 `ButtonRowDeviceCard9 508..568 ∩ FooterBg12 528..600 = 992×40 px`） | 视口与底栏**同源**（`m['content_bottom'] = H − bar_bot`）+ 自检 `assert_no_bar_overlap`（逐对判 rect、裁剪后有效矩形、相交报错退出；实测旧口径下能拓出上述 992×40）；展平长图里固定带**让位到长图底部**（`assert_bands_clear` 守） |
| 32 | **块自己报的高度装不下子节点**（空态块 `H×0.30` 在 320×240 上 72 < 需要的 104） | 内容实际底 > 声明内容高 → 滑动窗行程不够，**最后一段永远滚不出来**（且展平长图里压到底栏） | 块高按内容反算（`band = max(H×0.30, 图标底 + 2×(间距+4+副文案高))`）+ 自检「内容实际底 ≤ 声明内容高」（320 屏实测被拓出来 → 已修） |
| 33 | **数组子项（`radiobuttons[]` / `checkbox.checked` / `item.subItem[]`）只走通用兜底**| 渲染图里单选区 / 勾选态 / 列表行**是空的**，看图以为「列表没刷新出来」（2026-10-01） | 渲染器按引擎口径专有实现：逐项画圆点 + 选项文字（`pic0`/`pic2` 切态）、按 `checked` 切图（缺 `pic2` → `components/icons` 的 `control.check_on`）、按 `rows`/`rowSpacing`/`itemH` 逐行铺模板（行底 + 子项图/文本） |态**会被 `aa_audit` 判真缺陷 → 用 `state:"on"` 实心态或 `heart` |
| 34 | **`list_item` 只写 `rows` 不给 `items`**（把列表内容留给运行期，spec 里什么都不写） | 渲染图/真机首次上屏是**一列空行**（只有箭头）；看的人会当成「渲染 bug / 列表没刷新出来」（2026-10-01：「现在就是列表显示不出来了」） | 块库口径：**列表内容必须由 `items` 给**（`{icon,title,value}` → subItem：图标 + 标题 + 值）；模板行 = `items[0]`，每行都过宽度自检；`items` 给少了只是真机空行（高度只认 `rows`）——不是渲染 bug |

**两条纪律（写在最显眼处）**
1. **加行 = 照抄同页已有行的口径**（行高/步进/文本左缘/各元素盒），禁止自创形态；
2. **文本禁止为避让控件而改宽/挪位**——要改的是布局形态或盒子。

## 8. 本库做的取舍（如实报告）

0. **第 3 批（结构 / 导航 / 提示）四条关键取舍**（都在对应 `blocks/*.json` 的 `forbidden` 里写了红线）：
   ① **指示条盒 = tab 项盒本身**（同 left / 同 width），选中底/指示条都从**整条形状裁切**出图（半径只跟带高走）：2~3px 高的圆角药丸在 `aa_audit` 里退化成硬阶梯（#21 真缺陷），所以指示条本身仍是直角实条；但**不再内缩**（2026-10-01：「左右各缩 6px，与项不齐」），改由裁切把两端交给条本身的圆角 —— 首/末项不出方角、中间项直角；
   ② **选中底高度让出指示条高**（`tab_h − ind_h`）：这样指示条与选中底**几何不重叠**，谁先定义都不互相遮挡（同时满足「指示条放最前」与「选中态看得见底色」两个要求）；
   ③ **块内 glyph 尺寸下限 24px**（`glyph_min_px`）：图标不像字号可以降档，降了就退化成硬阶梯（实测 `wifi@12`/`home@16`/`settings@16`/`bell@20` 均判真缺陷）——代价是极小屏（320×240）上图标显得相对大（宫格格高 68 与 1024 的 72 几乎一样），这是为了「一次出能过的产物」付的代价；
   ④ **底导叠在底栏上方**（两带不重叠）：两者都是固定带，nav 贴底栏上沿，视口 = 屏高 − 标题 − nav − 底栏；**代价：320×240 上 nav 带 60px = 屏高 25%，视口只剩 108px**（极小屏两带叠置的必然结果，已在日志里打印可见）。

1. **`setting_row` 用「两行式」而不是左标题右值**：`scrollwindow-layout-checklist §2.1` 明确把"左标题 + 右值单行式"列为返工第一名（同页混用 → 文字外凸、箭头被压）。极小屏放不下两行时**整页**降单行式（全页一致），不是单行特例。
2. **卡片不给描边**：`SPEC-CHECK §7.1/§8` 的结论（1px 描边环在弧线上会让 AA 审计退回硬阶梯；TDesign 靠灰底衬托）→ 容器/面板/次按钮全部素面或浅色实底。
3. **箭头贴图按 `SPEC-CHECK §7` 的箭头专属口径自绘**（45° + 圆头 + 笔画 ≈ 盒宽 12% 且 ≥2px + SS≥8 + BOX）：`gen_res.glyph_icon('forward')` 的 iconfont 比例在 12px 盒上只剩 1px 笔画 → `aa_audit` 判 `hard_diag` FAIL。第 2 批又多了两个**合成**kind：`bar`（透明画布上居中贴一条药丸 = 滑轨/有效条，`gen_res.rounded_rect_cov`）与 `mark`（复选/单选标记 = `gen_res.rounded_rect_cov`/`bordered_cov` 打底 + `gen_res.glyph_icon('check')`/内圆点叠一次）——**形状与字形都还是 `gen_res` 的现成函数，本库只做「同画布叠一次」**，不重写画形状的逻辑。其余所有图（卡片/圆角/图标/开关/分割线/选中条）都直接走 `gen_res`。
4. **logic 骨架一并生成**：`check_all #5` 要求每个 button 有 `onButtonClick_<caption>`，否则整个工程 FAIL。骨架只含空实现 + 定时器表 + 生命周期钩子，业务自填。
5. **弹窗只出结构**（modal + `visible:false`）：真机由业务 `showWnd()/hideWnd()` 控制；`setTouchPass(true)` 等运行期口径不在 json 里（模板装饰件已 `touchable:false`，是否补穿透由业务按 §15 判）。
6. **未生成 `src/activity/*Activity.*`、`Manifest.xml`、`Main.cpp`**：这些属工程壳（`flythings_create_project` / HelloWord 模板的活），本库只管 UI 与 logic 骨架。
7. **第 2 批交互块的形态选型（都是为了让同页行族口径与 AA 审计同时成立）**：
   * **字段行 = 文本带 + 控件带两带式**（`slider_row`/`progress_row`/`input_row`/`radio_row`），不把控件塞进文本行右端：① seekbar/edittext 需要「盒高 ≥ 滑块高/文本高」才不被压扁；② 塞右端会与值文本盒相交（#27 文本×控件重叠）；③ 极小屏只靠「两带式」才同时放得下控件与文本。
   * **行族文本盒宽按全页预留**（§5 末）：观感上多一段死区，换 #27「同族口径 0 条离群」（旧两版示例的 2 条 WARN 就是这里）。
   * **未选态 = switchOff 实底，不给 1px 环**；**极小屏复选/单选不用内点**：全是 `aa_audit` 实测逼出来的（见反面清单 #21/#22）。
   * **`radio_row` 竖排**（而非右端横排）：横排要按选项数动态改行族预留 → 同页其它行的文本盒会跟着变宽/变窄；竖排在 320×240 也放得下。
   * **`list_item` 行高公式**：`lv高 = rows × (模板高 + rowSpacing) + 余数`，余数默认 2px（= 有意的可滑动提示）；**滚轮反过来——行高恰好整除，不留余数**（滚轮语义是「刚好一屏窗口」）。
   * **`list_item` 行内容（2026-10-01 补）**：行内容**必须由 `items` 给**（`{icon,title,value}` → 图标/标题/值三个 subItem；图标走 `components/icons`）；**模板行取 `items[0]`**（引擎只有一份行模板 → 静态图 4 行相同），逐行各异的文案是运行期数据（`obtainListItemData` 填）；**列表高只由 `rows` 算**（items 少了 = 真机空行，不挤在一起）；**每一行都过宽度自检**+ 非模板行的 icon 名也逐一核对（#13/#36 追不到 subItem，只能块库自己核）。极小屏 **省行内图标**（图标档 24 + 2×spacer > 行高 24）——与§4.2「宁可省图标」同口径。
   * **滚轮选中条用静态 textview**（写在 listview 之前、`touchable:false` 显式写），行模板透明、`picTab.pic0/1/2` 全空 + `color2/color3` 与常态同色（让引擎自带选中态看不见）—— 口径全部照 `knowledge/uicontrols/listview-wheel-picker.md`。

8. **图标来源 = `components/icons` 资产库（2026-10-01 改口径，详见 §5.1）**：
   * 原先走 `gen_res.glyph_icon()`（emoji 字体 / iconfont 线框兜底）→ 与真机/产品那套图标**不是同一套图形**（经需求方原话「效果差异和实际差异太大」）。现在实现是 `iconlib.py`：语义名 → 库条目（复用库自带 `resolve_target` 解析别名/全名/Tabler 名，**不另建名字表**，避免与库漂移）。
   * **为什么不直接拷库里的 PNG**：① FlyThings 无 tint，块内图标各有颜色（brand / fg2 / 语义色）→ 颜色必须生成时烘焙；② 库预置档只有 22/24/56，而块内图标盒有 16/24/36px。所以口径定为「盒 == 档位 → 取库预置产物并按 alpha 换色（与现出**像素等价**，maxdiff = 0）；缺档 → 用库自带生成器按**盒尺寸**现出」。两条都不改盒尺寸（图 == 盒是硬口径）。
   * **箭头（chevron）刻意留在本库自绘**：库的 `control.chevron-right` 是 24 网格的细描边，在 12×16 盒上会退成 1px 硬斜边（`aa_audit` 报 `hard_diag`）——即本库 §8-3 已定的箭头专属口径；`checkbox` 勾选符号已改走库（`control.check` 的 `_on`）。
   * **实测坑**：`star` 描边态 @24px 被 `aa_audit` 判真缺陷（`hard_diag=4` / 斜线边界 67% ≥ 60%）→ 小盒上的 star 用 `state:"on"` 实心态或改 `heart`（已写进 `blocks/_icons.json` 的 `_pitfall`）。
   * **回退不静默**：库里查不到语义名时 compose 打 `[回退线框] …` 并在日志里汇总「回退线框 N 处（目标 0）」；六版示例实测 **0 处**。

## 9. 已知限制 / 下一步

* 块数量按需扩展：新增块 = 加一个 `blocks/<type>.json`（字段 + 相对约束 + 素材 + 禁止项）+ 在 `compose.py` 里指到已有 builder（`title/section/row/field_row/card/empty/actions/dialog/list/wheel`）；新增形态才写新 builder。
* `compose.py` 第 2 批新增的控件 factory：`make_seekbar` / `make_edittext` / `make_checkbox` / `make_radiogroup` / `subitem` / `list_item_template`，及 builder `build_field_row` / `build_list` / `build_wheel`（素材新增 `bar` / `mark` / `chevron` 三个出图 kind）。
* `list_item` 逐行内容（2026-10-01 二次修）：`compose.py` 新增 `row_field()`（行数据取值）、`list_row_boxes()`（行内容盒口径**唯一算式**，模板行与逐行核对共用）、`list_row_check()`（逐行宽度自检 + icon 名存在性核对）、`list_row_subitems()`（行内容 → 图标/标题/值/箭头四个 subItem），`list_item_template(..., row=…)` 与 `build_list()` 吃 `items[]`；`subitem()` 新增 `touchable` 参数（图标子项 = 纯装饰，不吃触摸）。**不写 `items` 的 spec 输出与旧版逐字节一致**（向后兼容）。
* `compose.py` 第 3 批新增：
  · 工具：`r4up`（4px 栅格**向上**取整，专给文本盒宽，#36 余量口径）、`text_box_w`（文本盒宽 = 估算×1.10 向上取4）、`sem_color`（语义状态 → 前景/浅底令牌）、`col_int`（令牌名 → 整型色值）；
  · builder：`build_tabs`（tab 项批量）、`build_nav`（nav 项批量）、`build_banner`、`build_pill`（药丸）、`build_divider_label`、`build_grid`（宫格格子批量）、`build_toast`；全部只复用 `shape()/glyph()/text()/button()` + 第2批的 `bar/mark/chevron`，**没有新出图 kind**；
  · 自检全部复用：`assert_caption_unique`（每次出产物前）/ `assert_icon_uniform`（行族）/ `assert_children_fit`（每个新容器）/ `assert_row_gaps`（banner 的「文案→关闭盒」与 divider_label 的「线→文字」都记入同一张间隙表）/ `next_seq` + `name_block`（caption 唯一性）；
  · **缺陷 A 新增自检 `assert_no_bar_overlap`**（2026-10-01）：① 不变式「标题带 + 内容视口 ≤ 屏高 − 底栏高」；② 底部固定带（`bottom_actions`/`bottom_nav`）与**实际渲染出的**内容节点逐对判 rect 相交（用裁剪后的有效矩形——滑动区外的内容被引擎裁掉，不参与判定），相交 → 报错退出、不出产物；③ 内容实际底 ≤ 声明内容高（越了 = 滑到底也看不到最后一段）。口径来源：底栏 y / 底导 y / 内容视口**都从 `m['content_bottom'] = H − bar_bot` 一个令牌派生**，不再两处各算一套。
  · `_tokens.json` 新增：语义色 9 个（`info/info1/success/success1/warn/warn1/danger/danger1` + `mask`，TDesign v1.17 档位）与比例 `tab_h_of_h/ind_h_of_h/pill_h_of_h/banner_h_of_h/divider_h_of_h/nav_h_of_h/toast_top_of_h` + `glyph_min_px`。
* **图标来源（2026-10-01）新增文件**：`iconlib.py`（语义名 → `components/icons`；档位 56/24/22；盒 == 档位取库产物换色、缺档按盒尺寸现出；回退线框**明说**）、`blocks/_icons.json`（允许值清单：203 名 / 5 分类 / 两态）、`full_render.py`（整页渲染）；
  `compose.py` 新增出图 kind `libicon` + `glyph(state=…)` 参数（底导选中/未选中直接对上库两态）+ `grid_icons.items[].state`；`resources/images/` 里原来的 `ic_*` / `nav_*` 文件名不变（json 引用零改动）。
* **未覆盖**：日期/日历块、图表块（可复用 `components/ui_v1/` 的自绘控件后再包成块）、`circlebar`/`slidetext`/`pagewindow`/`slidewindow`/`digitalclock` 等控件块（tab 页签已在第 3 批覆盖）。
* **第 3 批遗留**：① 底部导航只有「图标 + 文字」两种呈现，没做「选中项突出/凸起」变体；② 宫格行数由 `cols` 与项数隐式决定，未支持跨列合并（`span`）；③ toast 是**单行**盒（多行需改 `toast_h` 公式）；④ 提示条的关闭动作只到回调骨架，关闭后重新弹出需业务自己记状态。
* 渲染图是**静止态近似**（`json2img` v0.1.0），真观感仍需模拟器/真机；320×240 的 10~12px 字号在设备字库下的可读性**未验证**。
* **渲染图的固有盲区**（不是本库的问题，但看渲染图时要知道）：见 §6.3 清单——`listview` 只画模板不填运行期数据（模板 `text` 是空串）、seekbar 有效图按缩放近似（引擎是裁剪）、`rollEnable`/动画/视频只画静止首帧。（`radiogroup` 选项区、`checkbox` 勾选态**已不再是盲区**——2026-10-01 起专有实现。）
* **滚轮/列表的实际手感与回读**需要业务侧代码（中心行回读 + 数据侧平移 + `refreshListView()`），本库只到 UI（json）；骨架里的 listview 三回调以注释形式给出签名。
* **`resources/images/` 不做旧图清理**（compose 只增量出图）：换块/改尺寸后旧切图会留在目录里（check_all 只核**被引用**的图，不影响判定）——要干净就手工删或整目录重建。
* `check_all #9` 对 `ui/<W>x<H>/` 布局的误报（见反面清单 #20）——修在 `check_all` 里更合适，本库用 `--ui-layout` 绕开，不去改既有工具。
* **`check_all` 的 2 条备注**（本库不管，属于既有工具口径）：① 新建的切图（第 2 批 `sk_*`/`cb_*`/`rd_*`/`wband_*`，第 3 批 `tabsbg_*`/`tab_on_*`/`ind_*`/`navbg_*`/`nav_*`/`bnr_*`/`pill_*`/`gtile_*`/`toast_bg_*`/`nav_*_on/off`）未在 `tools/qa/asset_audit_rules.json` 登记 → 按 `unknown_policy` 只出 NOTE（不判 FAIL）；要纳入 AA/倒角/透明底审计需在那个文件补分类（不在本库改动范围）。⚠️ 但 `aa_audit`（#21）**不过滤未登记资产**（它按全目录扫描）→ 所以块内 glyph 才有 `glyph_min_px = 24` 这个硬下限（见 §4.2 与反面清单 #27）。
