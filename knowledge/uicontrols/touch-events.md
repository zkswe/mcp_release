# 触摸事件与 touchable 语义（「点了没反应」排查手册）

> 2026-09-10 沛哥定规（项目实测发现：生成的 radiogroup 带 `touchable: false` → 单选组整组点不动，会产生**可用性错误代码**）。
> 检索词：触摸/touchable/点击没反应/点不动/事件不触发/穿透/radiogroup 点不了/setSelection 不刷新/层叠遮挡。
> 配套：`json-field-mandatory.md`（字段全集）、`json-layer-rules.md`（层级/层叠）、`radiogroup-checkbox-fields.md`。

## 铁律

1. **touchable ≠ 穿透开关**：`touchable` 只决定「这个控件收不收触摸」。
   想实现「点击穿透到下层」**不要**靠把 touchable 设 false——尤其交互控件，设 false 直接导致自身**点不动**（回调不触发）。
   穿透/遮挡由**层叠顺序与层级结构**决定（见第 4 条与 `json-layer-rules.md`）。
2. **交互控件必须 `touchable: true`**：button / listview / 可拖 seekbar(有 thumb) / qrcode / videoview / diagram / circlebar / slidewindow / subitem。
3. **⚠️ radiogroup 是例外——容器也必须 `touchable: true`**（沛哥 2026-09-10 修正）：
   `json-field-mandatory.md` 的「容器显式 false」口径**不适用于 radiogroup**；写 false 时整组收不到触摸，表现为**单选按钮点了没反应 / 选中态不切换**。
   （radiogroup 子项 radiobutton 本身也带 touchable true。）
4. **容器/纯显示控件 `touchable: false`**：window（非交互面板）/painter/textview/cameraview/digitalclock。
   **但容器若需要拦住下层触摸**（遮罩、弹窗背景拦截点击）→ 该类面板才设 `true`（弹窗 modal 背景用 true 是有意为之，不是 bug）。
5. **层叠顺序决定谁收到触摸**：json 中**后定义的控件在上层**；上层控件 `touchable: true` 会先截走触摸。
   排查「点不动」时，先看是不是被上层全屏（透明）面板挡住了。
6. **选中态不是数据分析，改完要刷新**：
   - listview：`setSelection(idx)` 之后**必须** `refreshListView()`（否则视觉/状态不更新）
   - radiogroup：选某项用子项 ID 宏 `setCheckedID(ID_MAIN_RadioButtonN)`（用行号/序号无效）
7. **回调名必须对得上控件 caption**：`onButtonClick_XXX` / `onCheckedChanged_RadioGroup1` 中的 XXX 必须与 json 里控件 `caption` 一致，否则事件发出去了也没人接。

## 「点了没反应」排查顺序（从 json 到代码，逐层排除）

| 步 | 查什么 | 判定 |
|----|--------|------|
| 1 | 目标控件 json 的 `touchable` | 交互控件（含 radiogroup）必须是 `true`；是 false → 就是这里，改了重编译 |
| 2 | 是否被上层遮挡 | 看 json 顺序，后定义的控件在上层；上层透明但 `touchable: true` 的面板会截走触摸 |
| 3 | 控件是否真在当前显示的 window/Activity 内 | 嵌套 window / 弹窗（modal）里的控件，父层没显示时点不到 |
| 4 | 回调是否注册且命名匹配 | `caption` 与 `onXXX_<caption>` 名字不一致 = 没接上；编译日志一般无报错，容易被忽略 |
| 5 | 状态类操作是否漏刷新 | listview `setSelection` → 漏 `refreshListView()`；radiogroup 用 ID 宏而非序号 |
| 6 | 以上都对仍无响应 | 用 `flythings_device_screenshot` 抓真机图确认控件在屏幕上的实际位置/遮挡，再结合 `adb logcat` 看是否有事件日志 |

## 自检清单（生成 json 后逐条过）

- [ ] 所有交互控件 `touchable: true`（button / listview / 可拖 seekbar / qrcode / videoview / diagram / circlebar / slidewindow / subitem）
- [ ] **radiogroup `touchable: true`**（例外项，最容易漏——生成器已修正）
- [ ] 容器/纯显示 `touchable: false`（window 非交互 / painter / textview / cameraview / digitalclock）
- [ ] 需要拦截下层触摸的遮罩/弹窗面板 `touchable: true`（有意设置）
- [ ] 没有被上层 `touchable: true` 的全屏面板挡住目标控件（层叠顺序）
- [ ] listview `setSelection(idx)` 后跟 `refreshListView()`
- [ ] radiogroup 用子项 ID 宏 `setCheckedID(ID_XXX_RadioButtonN)`（不用序号）
- [ ] 回调函数名与控件 `caption` 完全一致

## 相关

- 字段全集与默认值 → `json-field-mandatory.md`（radiogroup 行已标注 true 例外）
- 层级与层叠顺序 → `json-layer-rules.md` 第 7 条
- radiogroup/checkbox 字段与代码操作 → `radiogroup-checkbox-fields.md`
- 真机确认画面 → `devflow/ui-layout-verify.md` §2-1（`flythings_device_screenshot`）
