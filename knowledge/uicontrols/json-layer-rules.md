---
id: uicontrols-json-layer-rules
title: 控件层级规则（容器 → 子内容矩阵，双源实证）
category: uicontrols
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [控件层级问题检讨, ftu unpack 反解, py #2 层级合法性检查, layer_problems, 自动校验, 控件层级, 嵌套, 容器, 父子, 结构键, 坐标负值, 重启后控件跑位, 从右下算, 拖拽夹取边界, 落盘位置读回, 控件跑位]
evidence: []
---
# 控件层级规则（容器 → 子内容矩阵，双源实证）

> 检索导引：问「控件这样嵌套合不合法 / window 里能放什么 / pagewindow 为什么只装 window / 层级报错（check_all #2）/ 先看 json 做遮挡审计 / **重启后控件位置跑了 · 坐标出现负值 · 拖动夹到什么边界**」→ 本文。
> 口语/错说法（用户原话）：pagewindow 里能放文本框吗 / 能不能往 pagewindow 里加按钮、文本 / pagewindow 里放别的为什么没反应 / 为什么只能塞窗口。
> 2026-09-08 需求方要求「控件层级问题检讨」产出。**方法**：扫描 86 个真实 json（`projects/SampleUI-New/ui/1024x600` 42 + `projects/LearningProject/basedemo-new_z20_1024_600` 35 demo/44，ftu unpack 反解），统计每个容器类型的直接子内容分布——**零越界样例**，基线全绿。
> **落地**（2026-10-05 改口径）：**唯一真源 = `ui_tools/ui_schema.json` 的 `controls[].children`**
> （`{"mode": "controls"[, "only": [类型…]]}` 或 `{"mode": "substructure", "key": "<结构键>"}`；无声明 = 叶子），
> 判据由**两个 checker 同源派生**：`check_all.py` #2（`_layer_problems`）与 `ui_compile.py` **TREE001-004**；
> `html2json` 嵌套栈生成天然合规（slidewindow 内的子 div 一律进 `items[]`）。
> ⚠️ **事故记录（本次改口径的原因）**：此前 `check_all` 用四份硬编码表、`ui_compile` 只看 `container: true`
> —— 同一份「slidewindow 平铺子按钮」的 json，一个判 **FAIL**、一个判 **「编译式验收通过」（假绿）**
> （出处 `git show HEAD:templates/DemoControls_V85X/ui/main.json`；该页 2026-10-05 已改成 `window__1` +
> 子按钮，**现行工作区里没有 slidewindow 了**，所以证据**必须指名版本**，别按工作区路径去翻）。
> 跨 checker 同判的契约用例 = `tests/test_layer_rules.py`（含「把错法注回去必须变红」的自证）。
> 检索词：控件层级/嵌套/容器/父子/结构键/subItem/radiobuttons/页面 window/坐标负值/重启跑位/从右下算/拖动夹取。

## 容器 → 直接子内容矩阵（实证次数）
| 容器 | 允许的直接子内容 | 实证 |
|------|----------------|------|
| 根层 | 全部 21 类控件均允许 | 各类均有根层样例 |
| **window**| **万能容器**：textview/button/edittext/listview/seekbar/**window(深嵌套)**/qrcode/digitalclock/slidetext/slidewindow 等全部控件类型 | textview 147 / button 128 / edittext 16 / listview 8 / seekbar 7 / window 5 / qrcode 2 / digitalclock 1 / slidetext 1 / slidewindow 1 |
| **pagewindow**| **只装 window**（页面叠放，同尺寸；代码 turnToNextPage 翻页） | window 3（basedemo 3 页） |
| **scrollwindow**| **只装 window**（滚动内容；**内层 window 的尺寸 = 滚动行程基准**（滚到不到底看它，不看 `dragMaxDis`） | window 1 |
| **listview**| 只走 **item**（行模板）→ 行内容在 `item.subItem[]`；**禁止平铺 __N 控件键**| item 100%（两源） |
| **radiogroup**| 只走 **radiobuttons[]**（每项带 id/caption，本质按钮） | basedemo |
| **slidewindow**| 只走 **items[]**（图标项 {colorTab/picTab/text}，非控件） | 两源 |
| **diagram**| 只走 **infos[]**（波形配置，非控件） | 两源 |
| **叶子控件 14 类**| textview/button/edittext/seekbar/circlebar/checkbox/slidetext/cameraview/painter/pointer/digitalclock/qrcode/videoview/imageanim：**不得含子控件**| 无越界 |

## 规则要点（违反即 check_all #2 FAIL）
1. **window 是唯一万能嵌套容器**：可 window 内嵌 window（无限深）、scrollwindow → window → 面板 window、pagewindow 页面 window 叠放、弹窗 = window(modal) 最后定义（Z 序最上层）。
2. **数组子结构归属固定**：`radiobuttons`→radiogroup / `items`→slidewindow / `infos`→diagram / `subItem`→listview.item——出现在别处 = 非法（如 button 带 radiobuttons）。
3. **结构容器不平铺**：listview/radiogroup/slidewindow/diagram 的直接子键只能是结构键（item/radiobuttons/items/infos）；直接写 `window__N`/`textview__N` 等控件键 = 非法（如 listview 里直接放 window）。
4. **pagewindow/scrollwindow 必须含 window 子页面**，且只装 window（装 textview 等 = 非法）。
5. **叶子控件不能生子**（textview 内含 button 等 = 非法）。
6. Z 序与层级正交：json 书写顺序 = 层叠顺序（后定义在上层）；层级（谁嵌谁）由结构键/嵌套决定。
7. **层叠顺序决定谁收到触摸**（2026-09-10）：上层控件若 `touchable: true` 会**先截走触摸**，下层即使 touchable=true 也收不到——
   「点了没反应」优先查是不是被上层（常是全屏透明面板/遮罩 window）挡住了；要穿透就不要让上层 `touchable: true`
   （注意：radiogroup 必须 true，见 `knowledge/uicontrols/touch-events.md`）。

## 坐标负值 = 从右/下算（**「重启后控件跑位」的根因**）

> ⚠️ **适用范围（2026-10-01 需求方纠正）**：本文只约束**运行期算出来的绝对坐标**（拖动夹取 + 落盘回读 + `setPosition`）。
> **`ui/*.json` 里写 `left/top` 负值是合法写法**，不是问题：
> ① scrollwindow / pagewindow 的内容 window **用负值做初始偏移**（官方 wiki `scrollwindow-layout.md` §2：「left/top 可为负值…内容 window 的 left:-175 是初始偏移」，官方 `ScrollWindowDemo-New` 实际就是 `window__2 left=-175`）；
> ② 装饰件/图标越界（`button top=-7`、`textview left=-12`）、`-1` 表「未设置」（`SampleUI-New/1024x600/ad.json`）也都在用。
> 所以**不要**对 json 的负值/越界报告警（曾据此写过静态 WARN，当日撤下）。

**现象**：可拖动控件**当次拖动看着完全正常**，但**重启（或重新读落盘）后跑到屏幕另一侧 / 贴右贴下**。
分水岭就在这：是**重启后跑位**，不是当次就跑位 —— 当次跑位是夹取/刷新 bug，重启跑位才是本坑。

**根因**：`LayoutPosition` 里**负的绝对坐标不是「负偏移」，引擎把它当成「从右/从下算」的 bottom/right 值**
（`x = -20` 语义 =「距右边 20」，不是「左边界为 -20」）。于是拖动/持久化时写进负值的那一次，
落盘再读出来就被摆到另一侧。

**一眼发现**：看**运行期落盘的那份业务坐标**（本工程存在 prefs，如 `sp_*` 键）里出现负坐标，
配合「重启后才跑位」的现象即可坐实 —— **不是**去看 `ui/*.json`（json 负值合法，见本文开头适用范围）。
注意：静态像素/遮挡审计（`layout_audit`）也**查不出这类**——几何本身合法，要看**运行期写进去的值**。

**正确做法**（真机问题单 09251751-8，2026-09-25 口径）：
1. **拖动/夹取时左、上边界夹到绝对 0**：调参量 `dx/dy` 的下界取 `lo = -dl / -dt`（即取负的基准左/上），
保证最终绝对坐标 `dl + dx >= 0`；**不许「可以推出去大半」**（那就是负值来源）。
2. **右下至少留 `SS_EDGE_KEEP`（40px，或控件 1/3 尺寸，取小）在屏内**：`hi = SCR - keep - base`。
3. **落盘读回时 `-1` / 越界一律视为「未设置」**，走默认位置——**历史脏数据（已经写进去的负值）因此自动失效**，不用清库。

**判据**：夹取后恒有 `dl + dx >= 0 && dt + dy >= 0`（**绝对坐标绝不出现负值**）；
读回分支 `x < 0 || x > SCR` → 默认位置；落盘值扫一遍无负数即过。

**证据（真工程只读，行号已实读核对）**：
- `projects/SmartPanel_HA/src/logic/mainLogic.cc:598-612` `ssLoadLayout()`：`-1/越界 视为未设置（用默认位置）；负值一律当未设置（历史脏数据，见问题单 09251751-8）`。
- `projects/SmartPanel_HA/src/logic/mainLogic.cc:614-635` `ssClampX/ssClampY`：注释写明「**绝不允许绝对坐标出现负值**—— LayoutPosition 里负值会被引擎当成「从右/下算」的 bottom/right 值，重启后控件位置就跑了」，故左/上夹到绝对 0（`lo = -dl / -dt`）。
- 对应写入点：`mainLogic.cc:591-596` `ssSaveGroupPos()`（落盘 `dl+dx / dt+dy`）；应用点 `ssApplyGroup()`（`:584-587`，`setPosition(LayoutPosition(dl+dx, dt+dy, dw, dh))`）。
- 口径时间：2026-09-24 现场夹取口径 → 2026-09-25 追加负值硬约束；本文 `verified_at` 维持 2026-09-29。

检索词：重启后控件跑了 / 位置跑到另一边 / 控件位置重置 / 坐标负值 / 负坐标 / LayoutPosition 负值 / 从右下算 / bottom right 语义 / 拖动跑位 / 落盘位置读回 / 夹取边界。

## 相关
- 子结构字段全集（item 17 键含 position / subItem / infos 含 visible）见 `knowledge/uicontrols/json-field-mandatory.md`
- ★ **scrollwindow 内容的尺寸决定行程（不是 dragMaxDis）；加行忘加高内层 window = 末尾滚不到**→ `knowledge/uicontrols/scrollwindow-layout-checklist.md`
- window 嵌套/弹窗结构见 `uicontrols/window` wiki；页面级多全屏 window 应拆多 Activity（非同一 json 堆叠）

## 静态遮挡审计（v0.27.92：先看 json，别一上来截图）

用户说「控件被盖住 / 点不到 / 位置不对 / 谁挡着谁」时先调 `flythings_layout_audit(project_root[, page])`，
纯几何 0 token，返回 `pages[].findings[]`：

| kind | 含义 | 典型修法 |
|------|------|----------|
| `fullscreen_layer` | 整屏层（position == resolution）；`touchable:true` 会吞整屏触摸 | 隐藏页用 `visible:false`；遮罩只盖需要拦的区域；装饰加 `touchPass:true` |
| `touch_steal` | **同层更早定义**的 `touchable` 控件完整覆盖它 → 触摸按定义顺序先被拿走 | 遮挡物改 `touchable:false + touchPass:true`，或挪成子级/删掉 |
| `covered_interactive` | 上层 `touchable` 控件完整盖住可交互控件 | 挪 position / 缩小遮挡层 |
| `pass_through_missing` | 装饰件 `touchable:false` 但没 `touchPass:true`，与可点控件重叠 | 补 `touchPass:true` |
| `overlap` | 同层两个盒子相交（后者在上层） | 确认是否故意叠放 |

判据回顾：**z 序 = json 书写顺序（后定义在上层）**；**触摸按定义顺序先命中先定义的可点控件**（遮罩 button 压住卡片 window 时卡片内按钮点不动 → 卡片扁平化到控件层、排在遮罩之后）。
改动前后对比用 `flythings_ui_visual(action="diff")`；视觉样式（颜色/字体/切图）仍要截图。
检索词：控件被遮挡 / 点不到 / 谁挡着谁 / 控件覆盖 / 重叠 / 层级 / z 序 / touchPass / layout_audit。


## 根节点（页面尺寸）= 页面的「命门」：写错 → 页面 0×0 → 画不出 + 接不到点击（2026-10-08 事故，MUST）

**规则（违反 = `check_all` 第 1 项 FAIL）**：每个 `ui/*.json` 的**根节点**必须是
`"id": 0` + `"position": {"left": 0, "top": 0, "width": W, "height": H}`，且 **W/H 必须等于 `resolution`**。
例外：`"topmost": true`（系统栏 statusbar/navibar，官方「局部悬浮块」机制）不做全屏要求，
只要求坐标全整数、块非空且完整落在 resolution 内。

**为什么是命门**：引擎按**根节点**算页面尺寸。`position` 里没有 `width/height`
（例如写成 `{"left":0,"top":0,"bottom":0,"right":0}` —— 那是**控件坐标**「从右/下算」的写法，
被误用到根节点）→ 页面尺寸被算成 **0×0** → ① 画不出来（屏幕停在上一页，看着像「页面没打开」）；
② 接不到任何点击（点击落在 0×0 命中区之外）。
**最坑的是设备端完全静默**：不崩溃、不报错、app 日志无异常 —— 本次现场探针显示
`onUI_init` / `onUI_show` / `netRefresh` **全部走完**、当前活动也已切到该页，
但屏幕不重绘、点击零响应，极容易被误判成「死锁 / 视频图层争用 / 触摸驱动坏了」。

**实例（2026-10-08，Z20 SmartPanel，现场面板）**：
- `ui/network.json` / `ui/staticip.json` 由脚本 `gen_net_pages.py::head()` 生成，
  根节点写成 `{'left':0,'top':0,'bottom':0,'right':0}` → 点「设置 → 网络设置」**必现**"卡死"。
- 同批排查：`python tools/ui_tools/check_all.py <项目根>` **第 1 项直接就指出来了**
  （`[FAIL] ui/network.json 根节点`），而 `ui/staticip.json` 同 FAIL。
- 修法：根节点改成 `{'left':0,'top':0,'width':480,'height':480}`（== resolution）
  → `fui pack` 重出 ftu → `fsc build` → 出包，问题消失（截图 + 点击回调双验证通过）。

**防线（2026-10-08 已落地）**：
1. `ui_tools/check_all.py::verify_assets()` **现在也核根节点**（新增返回字段 `badRoot[]` 并参与 `ok`）——
   自动化链路（`flythings_verify_assets`）从此拦得住；判据函数 `_root_problem()` 与第 1 项同源。
   （此前 `verify_assets` 只核图片存在/尺寸，而 `check_all` 第 1 项只是**人工全检**的一项 →
   自动化跑不到，两个脚本生成的页面一路绿灯。）
2. 脚本生成页时：**出图前自检**根节点（`gen_net_pages.py::check_root()`，不合规直接 `SystemExit`，不出坏包）。
3. 排查口径：页面「打不开 / 点了没反应」且**设备端无任何报错** → **第一条先查根节点**，
   然后才是层级（#2）/ 遮挡（#15·#16）/ 视频图层等。

**另一条同源教训（部署侧）**：只改 `ui/*.json`（ftu）不改 C++ 时，`libzkgui.so` 不变 ——
按 lib md5 判「已是最新」的部署脚本会**误判跳过**；必须同时按 **ftu / img md5** 校验。


## 8. window 是容器：内容必须内嵌 + 相对坐标（2026-10-10）

**规则（违反 = `check_all` 第 38 项 / `ui_compile` TREE005 报 WARN）**：带底图的 `window` 容器
（`children.mode=controls`）要是**空壳**（无子控件），却有 **≥2 个同级控件整块落在它的 position 框内**
—— 说明「卡片内容」被平铺成了**兄弟节点**（绝对坐标），没有内嵌。正确写法：内容作为该 window 的
**子控件**、用**相对窗口的坐标**。

**为什么是硬规则**（2026-10-10 UIShowcase-Z21 底部 NavBar 事故）：
1. **位移/隐藏/动画不跟随**：对窗口做整体 `setPosition`（如载入/退出动画 `zk::PageAnim`）时，
   **只有窗口自己动**，平铺在外面的图标/文字原地不动（先例：NavBar 背板滑入、图标文字不动）。
   子控件随父容器移动，兄弟节点不会。
2. **封装语义**：window 是万能容器，同页其它卡片（HeroCard 等）都是「卡片窗口 + 内嵌子控件」；
   空壳窗口 + 外挂内容破坏了「window = 容器」的一致语义，也让后续改动（挪/换屏/z 序）成本翻倍。
3. **坐标空间**：子控件坐标**相对父容器**（实证：HeroCard 子件 36,34 = 卡内偏移）；写绝对坐标当兄弟
   就成了「几何巧合」，容器一挪就散。

**与既有规则的关系**：TREE001-004 / #2 只管**非法嵌套**（叶子装子 / 结构容器平铺 / 只装 window）；
本条管的是**合法但设计错**的空壳容器 —— 两者的 json 都合法、pack 都成功，只有本条能抓。

**修法**：`flythings_read_json` 读出层级后，用 `flythings_edit_ftu(operations=[{"op":"move","target":"<子控件>","into":"<容器>"}])`
把内容**移入容器**（自动按绝对坐标重基为相对坐标）；或直接改 `ui/*.json` 再 `fui pack`。
层级/父子在 MCP 里**只能走 `move`**（`ui_visual(action=edit_apply)` 只改几何+字段，不改父子）。

**判据口径**：带 `backgroundPic` + 无子控件键 + ≥2 同级控件「整块（含 1px 容差）落在窗口框内」→ 报。
只报 WARN（可能是故意「框 + 悬浮件」），交人工判断。
