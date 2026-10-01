# 界面块片段库 + 组装器（ui_blocks）· MVP

> **一句话**：让 AI（和人）做 FlyThings 界面时，从「手算坐标」变成「**选块 + 填值 + 排序**」——
> 像用 Bootstrap/组件库那样拼界面，并且**一次就出能过的产物**：json + 切图 + 渲染图 + 全检。
>
> 建立：2026-10-01（钟工「按照你的建议做」）。范围：**只新建本目录**，不改任何现有脚本/知识文档；
> 所有出图/渲染/全检都**调现有工具**（`ui_tools/gen_res.py`、`ui_tools/json2img.py`、`ui_tools/check_all.py`），
> 不复制它们的逻辑。

---

## 1. 目录

```
templates/ui_blocks/
├─ compose.py                 ← 组装器（唯一入口，CLI）
├─ blocks/
│  ├─ _tokens.json            ← 设计令牌 + 相对尺度体系的**唯一数值源**（比例/令牌，不写死某屏像素）
│  ├─ page_title.json         ← 块定义：字段 + 相对约束 + 需要素材 + 禁止项
│  └─ …（共 10 个块定义）
└─ examples/
   ├─ settings_1024x600/      ← 示例 A：spec.json + project/（产物）+ main.render.png + 两个日志
   └─ settings_320x240/       ← 示例 B：**同一套块**，只换分辨率（spec.json 只差 resolution 与短文案）
```

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
```

产物清单（每页）：
1. `<工程>/ui/[<W>x<H>/]main.json` —— 字段全集显式、`textview__N/button__N/window__N` **连续编号**、根节点 `id:0 + position + resolution`；
2. `<工程>/resources/images/*.png` —— 只给用到的块出图，**图 == 控件盒**（走 `gen_res.py`）；
3. `<工程>/ui/main.render.png`（`--render`）、`<工程>/src/logic/mainLogic.cc`（骨架，按钮回调一个不缺）；
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
      {"type": "empty_state", "icon": "info", "text": "暂无其它设备", "sub": "点右上角添加"},
      {"type": "bottom_actions", "status": "已是最新", "primary": "保存", "secondary": "取消"},
      {"type": "dialog", "title": "确认删除", "body": "删除后不可恢复，确定继续吗？", "visible": false}
    ]
  }
}
```

* `page.title`（+ `subtitle`）也可以写成一个 `page_title` 块，二选一；`bottom_actions` 同理可用 `page.footer`。
* 极小块用 `value_short` 给「数得出来的短文案」（长值在 320 上放不下会 #13 FAIL）。

## 4. 块清单（10 个）

| 块 | 用途 | 占几行 | 需要素材（`gen_res` 出） | 能滚动 | 关键相对约束 |
|---|---|---|---|---|---|
| `page_title` | 标题 + 英文副标题 | 顶栏带 | — | ✗ | 带高 = max(屏高×10%, 标题带内容高+12)；h1 + bold + fg1 |
| `section_header` | 分组小标题 | 1 带 | — | 随内容 | 带高 = max(spacer-3, h2×1.45)；h2 + fg2 |
| `setting_row` | 设置行（标题 + 值 + 箭头） | 1 行 | `chev_`（+可选 `icbg_/ic_`） | 随内容 | 行高 = 屏高 10%（极小屏 11.7%）；两行式：标题在上、值在下、**左缘同一**；箭头贴右缘 − pad |
| `toggle_row` | 开关行 | 1 行 | `sw_*_on/off`、`swk_` | 随内容 | 开关盒 = 行高×1.30 × 0.72，贴右缘；**装饰件呈现态 + 整行透明 button 命中** |
| `icon_row` | 图标底 + 图标 + 标题 + 值 + 箭头 | 1 行 | `icbg_`、`ic_<glyph>_`、`chev_` | 随内容 | 图标底 = 行高×0.60（垂中）、图标 = 行高×0.40（同心）；文本左缘 = 图标底右缘 + spacer |
| `device_card` | 设备卡（图标 + 名称 + 状态 + 箭头） | 1 行 | 同 `icon_row` + `dot_` | 随内容 | 与 `icon_row` **同一套行模板**（同页行族一致） |
| `card` | 圆角卡片容器（白底 + 行内分割线） | N 行 | `card_<W>x<H>`、`sep_<W>x1` | 随内容 | 宽 = 屏宽 − 2×spacer-2；圆角 = min(6, 行高×0.18) 且 ≥4；相邻行 1px 分割线 |
| `empty_state` | 空态（图标 + 文案，居中） | 1 带 | `icbg_`、`ic_<glyph>_` | 随内容 | 带高 = 屏高×30%；图标底 = 2×行高×0.60；文案居中 |
| `bottom_actions` | 底部状态文案 + 主/次按钮 | 底栏带 | `footbg_`、`btn_primary_`、`btn_secondary_` | ✗（固定件） | 带高 = max(屏高×12%, 按钮高+24)；主按钮贴右，次按钮在其左 − spacer |
| `dialog` | 弹窗（遮罩 + 面板 + 标题 + 正文 + 双按钮） | 覆盖层 | `cc_scrim_<W>x<H>`、`panel_`、双按钮图 | ✗ | 根层整屏 `window`（modal + visible:false）；面板宽 = 屏宽×60%，整屏居中；遮罩 **touchable 显式 false** |

> `value_row`（左标题 + 右值，无箭头）不用单独建块：`{"type":"setting_row","chevron":false,"icon":""}` 就是它。

## 5. 相对尺度体系（唯一的数值源 = `blocks/_tokens.json`）

| 维度 | 采用值 | 出处 |
|---|---|---|
| 色 | 页面 `#F3F3F3` / 容器白 / 主文 `#1A1A1A` / 次文 `#666` / 分割线 `#E7E7E7` / brand `#0052D9` | TDesign v1.17.0（rpx÷2 = px） |
| 型 | 字号**按屏选档**（不线性放大）：28/20/16/14 px @1024×600；14/12/12/10 @320×240；层级 = **字号档 + 字重 + 灰阶**（级差 <1.3 时不再堆字号） | TDesign 档位 + `SPEC-CHECK §8` |
| 距 | spacer 8 / 12 / 16 / 24；分组间距 = spacer-2 | TDesign spacer |
| 形 | 容器圆角 = min(radius-default 6, 行高×0.18) 且 ≥4；分割线 1px；**白卡不给描边**（见反面清单 #10） | `SPEC-CHECK §8` |
| 组件级 | 行高 = 屏高 10%（极小屏 11.7%，并给文本可读性兜底）；行条宽 = 屏宽 − 2×spacer-2；左内边距 ≈ 屏宽 3.1%；图标底 0.6×行高；图标 0.4×行高；箭头 max(12, 屏宽 2.5%) × max(16, 屏高 2.7%) | `scrollwindow-layout-checklist §2.1` + `SPEC-CHECK §7` |
| 滚动 | `dragMaxDis` = **越界拖拽上限**（全页 max(24, 屏宽×6%)），**不是行程**；行程 = 内层 window − 视口，引擎自算 | `scroll-drag-interaction-spec` R1/R2/R6/R10 |

**布局自动决策**：内容总高 > 视口 → 自动包 `scrollwindow`（视口高）→ 内层 `window`（高 = 内容总高）；≤ 视口 → **不上滑动窗口**（白放一层没意义，§2.1 第 1 步）。

## 6. 自测结果（两版示例，全自动）

| 项 | 1024×600 | 320×240 |
|---|---|---|
| 块数 / 行数 | 10 个块类型 / 7 行（2 卡 + 1 独立分组标题 + 空态 + 底栏 + 弹窗） | 同左（**同一套块**） |
| 控件数（含嵌套） | **66**（textview 49 / button 11 / window 5 / scrollwindow 1） | **59**（textview 42 / button 11 / window 5 / scrollwindow 1） |
| 关键度量 | 行高 60 ｜ 字号 28/20/16/14 ｜ 圆角 6 ｜ 图标底/图标 36/24 ｜ 箭头 24×16 | 行高 28 ｜ 字号 14/12/12/10 ｜ 圆角 5 ｜ 图标底 16（图标省略）｜ 箭头 12×16 ｜ **单行式** |
| 内容 → 视口 / 行程 | 716 → 452 / **行程 264**，dragMaxDis 60 | 372 → 168 / **行程 204**，dragMaxDis 24 |
| 出图 | **19 张**（图 == 盒，#11 PASS 0 处不匹配） | **15 张**（同上） |
| logic 骨架 | `src/logic/mainLogic.cc`，**11 个按钮回调**齐全 | 同左，11 个 |
| `json2img --report` unsupported | **1 类**：`bold x4`（渲染器无 `*Bold*.ttf` 变体 → 用同字体；真机由字库承担） | 同左：`bold x4` |
| 渲染图 | `main.render.png` **1024×600 == resolution** ✓ | `main.render.png` **320×240 == resolution** ✓ |
| `check_all` | **exit 0（0 FAIL）**，0 条 WARN | **exit 0（0 FAIL）**，0 条 WARN |
| #26 行程 / #27 同族 | 行程=内层−视口 ✓ ｜ 同族口径 0 条离群、文本×图标 0 处相交 | 同左 ✓ |
| 证据 | `examples/settings_1024x600/{main.render.png,last-run.log,check_all.log}` | `examples/settings_320x240/{main.render.png,last-run.log,check_all.log}` |

对齐解码：全部文字控件用 **36/37/38（真机实测表）**，`json2img` 报「待校准 0 处 / 表外 0 处」。

## 7. ⛔ 反面清单（照抄我们踩过的坑，别重犯）

| # | 坑 | 症状 | 本库怎么防 |
|---|---|---|---|
| 1 | **行做成「左标题 + 右值单行式」，同页其它行是两行式** | 该行文字明显外凸/不齐；箭头和值挤一起 | 行族口径**全页统一**（`scan_row_family`：文本左缘/右值预留/图标列一致）；极小屏**整页**降单行式，禁混用 |
| 2 | **为给箭头腾位把值框收窄/挪位**（挤文本去让位） | 对齐走样；引擎先画底图后画文字 → 箭头被文字盖住 | 冲突只改**布局形态或盒子**；文本盒宽度由行条宽 − 预留反算，绝不"挤" |
| 3 | **文本盒与图标/箭头盒相交** | 箭头/图标看不见，或被文字压住 | 文本左缘 = 图标底右缘 + spacer；值盒右缘 = 箭头/开关盒左缘 − spacer；`check_all #27` 复核 0 处 |
| 4 | **图标/箭头盒太小** | glyph 被压到 6×6 发糊 | 盒下限：图标 ≥12、箭头 ≥12×16（对齐 TDesign 32rpx=16px 档） |
| 5 | **图 ≠ 控件盒** | 引擎**拉伸填充** → 圆角/描边糊、字形压扁 | 所有切图按控件盒尺寸出（`card_992x180.png`…）；`check_all #11` 复核 0 处不匹配 |
| 6 | **把 `dragMaxDis` 当行程/内容尺寸填** | "滚不到底/末尾行看不到"或整屏被拽出去 | 行程 = 内层 window − 视口（引擎自算）；`dragMaxDis` 只取手感值 `max(24, 屏宽×6%)` 且 < 控件高 |
| 7 | **固定件（标题/底栏）放进滑动区** | 上滑时标题和按钮跟着滚走 | 标题/底栏/弹窗是根层节点，只有中段内容进 `scrollwindow` |
| 8 | **`scrollwindow` 下平铺非 window 子控件** | 新加的行整块不显示 | 内容全部进内层 `window`，其高 = 内容总高（增删行自动同步） |
| 9 | 内容放得下也硬上 `scrollwindow` | 白放一层、手势白吃 | 内容总高 ≤ 视口 → 直接摆（§2.1 第 1 步） |
| 10 | **`colorTab` 底色 + 底图同时给** | 方形底色盖掉底图圆角与描边（表现＝"倒角没生效"） | 卡片／面板的底色由底图承担，行按钮底色 `-1` |
| 11 | **白卡配 1px 描边环** | 行高 <40 时 1px 环让 AA 审计退回「直通 α 脏边」判据报 dirty | 描边按 §8 **降级为可选**（灰底衬托 + 分组间距），容器/面板/次按钮一律素面 |
| 12 | **在白色底上放白色按钮** | 次按钮"看不见" | 次按钮用 TDesign light 变体（浅品牌底 `#F2F3FF` + 品牌字） |
| 13 | **色值写 `0` 当"透明"** | 真机渲染成不透明**黑块** | 透明一律 `-1`；`backgroundColor/bgColorTab.color0` 禁 0（`zero_color_audit` 拦） |
| 14 | **alignment 用未校准值（0/5/6…）** | 渲染器只能按位模型猜（"待校准"清单） | 统一用真机实测表 **36/37/38**（本库已全量切换 → 待校准 0 处） |
| 15 | **放大渲染图用 BOX** | 面积平均 = 把素材糊掉，被误判成素材缺陷 | 渲染放大一律 NEAREST（本库渲染 scale=1 即为原尺寸） |
| 16 | **装饰件后定义（z 更高）且没写 `touchable:false`** | 吃掉下层触摸；`check_all #15/#29` 报警 | 装饰件一律**先定义** + `touchable` 显式 false；整行命中 `button` 最后定义（z 最高） |
| 17 | **改了 json 不 pack** | "改了像没改"（ftu→json 自动同步把改动打回） | 交付前 `check_all`（内含 `fui pack` 与 ftu/json 时间戳核对 #9） |
| 18 | **极小屏硬上两行式** | 行高被文本顶到 ~18% 屏高，一屏只剩 4 行 | 屏高 <320 自动降**单行式** + 字号降 2 级 + 省图标 |
| 19 | **极小屏用长值文案** | `check_all #13` 文本最小尺寸 FAIL（如"已连接 · 192.168.1.100"在 136px 盒里放不下） | 提供 `value_short`，本库在极小屏自动启用；`compose.py` 还做**事前自检**并点名是哪条文案 |
| 20 | **单分辨率工程把 json 放到 `ui/<W>x<H>/`** | `check_all #9` 的 `fui pack` 只认扁平 `ui/*.json` → 误报 `pack 成功 → main.ftu` FAIL | `--ui-layout auto`：没有现成的 `ui/<W>x<H>/` 就按**扁平**落（`res` 留给真多分辨率工程，此时 #9 的误报是既有工具的已知限制） |

**两条纪律（写在最显眼处）**
1. **加行 = 照抄同页已有行的口径**（行高/步进/文本左缘/各元素盒），禁止自创形态；
2. **文本禁止为避让控件而改宽/挪位**——要改的是布局形态或盒子。

## 8. 本库做的取舍（如实报告）

1. **`setting_row` 用「两行式」而不是左标题右值**：`scrollwindow-layout-checklist §2.1` 明确把"左标题 + 右值单行式"列为返工第一名（同页混用 → 文字外凸、箭头被压）。极小屏放不下两行时**整页**降单行式（全页一致），不是单行特例。
2. **卡片不给描边**：`SPEC-CHECK §7.1/§8` 的结论（1px 描边环在弧线上会让 AA 审计退回硬阶梯；TDesign 靠灰底衬托）→ 容器/面板/次按钮全部素面或浅色实底。
3. **箭头贴图按 `SPEC-CHECK §7` 的箭头专属口径自绘**（45° + 圆头 + 笔画 ≈ 盒宽 12% 且 ≥2px + SS≥8 + BOX）：`gen_res.glyph_icon('forward')` 的 iconfont 比例在 12px 盒上只剩 1px 笔画 → `aa_audit` 判 `hard_diag` FAIL。**其余所有图（卡片/圆角/图标/开关/分割线）都走 `gen_res` 的现成函数**。
4. **logic 骨架一并生成**：`check_all #5` 要求每个 button 有 `onButtonClick_<caption>`，否则整个工程 FAIL。骨架只含空实现 + 定时器表 + 生命周期钩子，业务自填。
5. **弹窗只出结构**（modal + `visible:false`）：真机由业务 `showWnd()/hideWnd()` 控制；`setTouchPass(true)` 等运行期口径不在 json 里（模板装饰件已 `touchable:false`，是否补穿透由业务按 §15 判）。
6. **未生成 `src/activity/*Activity.*`、`Manifest.xml`、`Main.cpp`**：这些属工程壳（`flythings_create_project` / HelloWord 模板的活），本库只管 UI 与 logic 骨架。

## 9. 已知限制 / 下一步

* 块数量按需扩展：新增块 = 加一个 `blocks/<type>.json`（字段 + 相对约束 + 素材 + 禁止项）+ 在 `compose.py` 里指到已有 builder（`title/section/row/card/empty/actions/dialog`）；新增形态才写新 builder。
* 暂未覆盖：listview/滚动列表块、tab 页签、日期/滚轮选择器、图表块（可复用 `components/ui_v1/` 的自绘控件后再包成块）。
* 渲染图是**静止态近似**（`json2img` v0.1.0），真观感仍需模拟器/真机；320×240 的 10~12px 字号在设备字库下的可读性**未验证**。
* `check_all #9` 对 `ui/<W>x<H>/` 布局的误报（见反面清单 #20）——修在 `check_all` 里更合适，本库用 `--ui-layout` 绕开，不去改既有工具。
