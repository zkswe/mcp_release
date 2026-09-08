# 控件层级规则（容器 → 子内容矩阵，双源实证）

> 2026-09-08 沛哥要求「控件层级问题检讨」产出。**方法**：扫描 86 个真实 json（`projects/SampleUI-New/ui/1024x600` 42 + `projects/LearningProject/basedemo-new_z20_1024_600` 35 demo/44，ftu unpack 反解），统计每个容器类型的直接子内容分布——**零越界样例**，基线全绿。
> **落地**：check_all.py #2 层级合法性检查（_layer_problems）自动校验；html2json 嵌套栈生成天然合规。
> 检索词：控件层级/嵌套/容器/父子/结构键/subItem/radiobuttons/页面 window。

## 容器 → 直接子内容矩阵（实证次数）
| 容器 | 允许的直接子内容 | 实证 |
|------|----------------|------|
| 根层 | 全部 21 类控件均允许 | 各类均有根层样例 |
| **window** | **万能容器**：textview/button/edittext/listview/seekbar/**window(深嵌套)**/qrcode/digitalclock/slidetext/slidewindow 等全部控件类型 | textview 147 / button 128 / edittext 16 / listview 8 / seekbar 7 / window 5 / qrcode 2 / digitalclock 1 / slidetext 1 / slidewindow 1 |
| **pagewindow** | **只装 window**（页面叠放，同尺寸；代码 turnToNextPage 翻页） | window 3（basedemo 3 页） |
| **scrollwindow** | **只装 window**（滚动内容，window 尺寸=dragMaxDis） | window 1 |
| **listview** | 只走 **item**（行模板）→ 行内容在 `item.subItem[]`；**禁止平铺 __N 控件键** | item 100%（两源） |
| **radiogroup** | 只走 **radiobuttons[]**（每项带 id/caption，本质按钮） | basedemo |
| **slidewindow** | 只走 **items[]**（图标项 {colorTab/picTab/text}，非控件） | 两源 |
| **diagram** | 只走 **infos[]**（波形配置，非控件） | 两源 |
| **叶子控件 14 类** | textview/button/edittext/seekbar/circlebar/checkbox/slidetext/cameraview/painter/pointer/digitalclock/qrcode/videoview/imageanim：**不得含子控件** | 无越界 |

## 规则要点（违反即 check_all #2 FAIL）
1. **window 是唯一万能嵌套容器**：可 window 内嵌 window（无限深）、scrollwindow → window → 面板 window、pagewindow 页面 window 叠放、弹窗 = window(modal) 最后定义（Z 序最上层）。
2. **数组子结构归属固定**：`radiobuttons`→radiogroup / `items`→slidewindow / `infos`→diagram / `subItem`→listview.item——出现在别处 = 非法（如 button 带 radiobuttons）。
3. **结构容器不平铺**：listview/radiogroup/slidewindow/diagram 的直接子键只能是结构键（item/radiobuttons/items/infos）；直接写 `window__N`/`textview__N` 等控件键 = 非法（如 listview 里直接放 window）。
4. **pagewindow/scrollwindow 必须含 window 子页面**，且只装 window（装 textview 等 = 非法）。
5. **叶子控件不能生子**（textview 内含 button 等 = 非法）。
6. Z 序与层级正交：json 书写顺序 = 层叠顺序（后定义在上层）；层级（谁嵌谁）由结构键/嵌套决定。

## 相关
- 子结构字段全集（item 17 键含 position / subItem / infos 含 visible）见 `json-field-mandatory.md`
- window 嵌套/弹窗结构见 `uicontrols/window` wiki；页面级多全屏 window 应拆多 Activity（非同一 json 堆叠）
