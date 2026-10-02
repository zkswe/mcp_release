---
id: devflow-translate-ui-lvgl
title: LVGL → FlyThings ui json 迁移翻译器（flythings_translate_ui v1）
category: devflow
status: review
confidence: offline
verified_at: 2026-10-02
stale_days: 180
origin: 实践
source: 2026-10-02 场景③跨框架迁移落地（v0.27.171-open）；映射数据 mcp_control_map.json
needs_evidence: false
platforms: [通用]
tags: [LVGL 迁移, lvgl 迁移, lv_obj_create, lv_label, lv_slider, lv_chart, 界面迁移, 控件映射, D-xx 降级登记, ui json 生成, translate ui, 跨框架移植, 温控面板迁移, lvgl v8, lvgl v9]
evidence:
  - {kind: offline, cmd: python -m unittest discover -s tests -k translate, expect_rc: 0, expect_contains: OK}
---

# LVGL → FlyThings ui json 迁移翻译器（flythings_translate_ui v1）

> 检索导引：问「LVGL 工程/界面怎么迁到 FlyThings / lv_obj_create lv_label 转成我们的 json /
> lvgl 代码转 ui json / 温控面板 LVGL 迁移 / lv_chart lv_roller 怎么办 / 迁移降级清单 D-xx 怎么出」→ 本文。
> 方法论与铁律（视觉换算 / 四阶段 / D-xx 登记制）在 `knowledge/devflow/platform-translate.md`；
> 单控件对应在 `flythings_map_control`（数据 = `mcp_control_map.json`，翻译器与它是**同一张表**）。

## 1. 这是什么

`flythings_translate_ui(source, out='', res='1024x600', dry_run=True, gen_placeholders=False)`：
把 **LVGL v8/v9 风格 C 源码**翻译成一个 FlyThings `ui/*.json` 页面 + 一份**转换报告**。

- `source`：`.c` 文件路径，或直接传内联源码字符串；
- `dry_run=True`（默认）：json 放在返回体 `uiJson` 字段，**不落盘**；
- `dry_run=False` + `out=<项目>/ui/main.json`：写盘（自动建目录，返回 `jsonPath`/`affectedFiles`）；
- `res`：目标分辨率，默认 1024x600（迁移基准屏，见 platform-translate.md §2）；
- `gen_placeholders=True`：缺图引用不剥除，改为同步出**纯色占位 PNG** 到 `<项目>/ui/images/`
  （尺寸 = 控件盒，图==盒；仅离线确认稿用，正式图仍走 flythings_generate_ui_assets）。

v1 是**确定性行/正则解析器**（不是 C 编译器）：同一份输入永远产出同一份 json；
**识别不了的一律进 `unrecognized` 清单，L3/L4/L5 一律进 `downgrades`（D-xx）登记，绝不静默丢**。

## 1.5 ⛔ 真机实测硬规则（2026-10-02，V85X iMirror 固件，A/B 对照终裁）

> 背景：翻译器初版产物 pack 成功但**真机 runtime 在 ftu 加载时无声挂死**（userspace 空转，
> 无 onUI_init/onUI_show、无报错日志）。先经逐项二分（temp/bisect）缩小到 seekbar，
> 再用 A/B 对照（temp/abtest_a/b）钉死唯一变量：

1. **`seekbar.thumb` 等子盒对象字段写成字符串 = ftu 加载无声挂死（唯一真凶，致命）**。
   thumb 真 schema 是 `{size:{width,height}, normalPic, pressedPic}` 对象；
   初版映射表片段的 `"thumb":"images/x.png"` 是类型违规。
   A/B 终裁：**thumb 对象 + 图不存在 → 正常加载；thumb 字符串 + 图存在 → 挂死**。
   （当日「缺图=死循环」的二分结论是错归因：剥图把写错类型的 thumb 一起剥掉了。）
2. **缺图不致命，但属验收缺陷**。引用不存在的文件 → 控件不可见（framework 容错）。
   为保「该显示的都能看到」，翻译器**仍不 emit 指向不存在文件的图片路径**：默认**剥除**
   （字符串字段置 `''`、picTab 删条、thumb 子盒清空并 size 置 0 —— 控件隐形但合规），
   剥除明细进报告 `imageActions[]`；`gen_placeholders=True` 时改为出占位图；
   图片已落盘（ui/images 或 resources/images 有同名文件）则保留引用。
3. **每控件必须写全 schema 字段全集**（json-field-mandatory.md 的「字段全集显式化」在此落地）：
   - **textview**：`colorTab`/`bgColorTab` 均为**五槽**（color0..color4，未用恒 -1）、
     `bold/italic/visible/rollEnable/rollDirection/rollIntervalTime/rollStep` 全写；
   - **button**：`text` **内联**（schema 本就支持，hw-relay ftu 真源）、`alignment: 5`（居中，
     位模型 ≡37）、`picTab/longClickTimeOut/longClickIntervalTime/visible` 全写；
   - **seekbar.thumb 是子盒对象** `{size:{width,height}, normalPic, pressedPic}`，
     **不是字符串**（映射表旧片段的 `"thumb":"images/x.png"` 是错误形态，发射层已纠正）；
   - window/painter 等按发射层 `_SCHEMA_FILL` 补齐。
   真源：demos/hw-relay-verify-z20 ftu 反解 + templates/ui_blocks/examples。
3. 根 window、textview、嵌套 window+textview、纯 button 在真机渲染均正常（已验证）。

配套变化：**LVGL 按钮的 label 子控件 → button.text 内联**，旧版 D-03「按钮不能装子控件 →
独立 textview」变通废止（schema 从来没有这个问题）；文字色并进按钮 colorTab（color0=color1）。

## 2. 识别的调用形态（只认这些，别假设更多）

| 类别 | 调用 |
|---|---|
| 创建 | `<var> = lv_<type>_create(<parent>)`（`lv_obj_create(NULL)` / 父为 `lv_scr_act()` = 屏幕） |
| 几何 | `lv_obj_set_pos/set_x/set_y/set_size/set_width/set_height`（整数字面量或 `int±int`） |
| 对齐 | `lv_obj_align(obj, LV_ALIGN_*, dx, dy)` 九宫位、`lv_obj_center`（父几何已知时换算绝对坐标） |
| 文本 | `lv_label_set_text` / `lv_textarea_set_text`（字符串字面量） |
| 样式（主选择器） | `lv_obj_set_style_bg_color` / `..._bg_opa`（仅全透明）/ `..._text_color` / `..._text_font`（从字体名尾数读字号）/ `..._radius` / `..._pad_*` |
| 值域 | `lv_slider/lv_bar/lv_arc` 的 `set_range` / `set_value` |
| 图片 | `lv_img_set_src("...")`（取 basename → `images/`，图要自己拷） |
| 事件 | `lv_obj_add_event_cb`（回调名登记进 events，不丢） |
| 显隐 | `lv_obj_add_flag/clear_flag(..., LV_OBJ_FLAG_HIDDEN)` |

其余 `lv_*` 调用（shadow/border/动画/align_to/text_fmt/表达式坐标如 `LV_PCT` …）→ `unrecognized`；
系统级调用（`lv_init`/`lv_tick_*`/`lv_disp_*`/`lv_fs_*` 等）不属 UI 语义，不识别也不上报。

## 3. 换算规则（铁律落地处）

- **坐标**：LVGL 子控件相对父对象，FlyThings 子控件相对父容器 → 直接平移；align 在父几何已知时换算。
- **颜色**：一律转十进制 int；`#000000` 按铁律改写 `#010101`（0 会被当「未设置」）。
- **字号**：正文/按钮 **≥18px**；源更小 → 抬到 18 并登记 D-xx（盒会比源稿大）。
- **圆角 / padding**：平台无对应属性 → 登记 D-xx（圆角走出图、padding 折算进子控件几何）。
- **屏幕**：第一个 `lv_obj_create(NULL)` = 页面根（bg_color 落到页底）；**第二屏起**生成顶层 `window__N`
  （visible:false）并登记 D-xx（平台无多 Activity 页栈，多页 = 整屏 window 显隐）。
- **模板片段**：每控件取映射条目 `json` 片段的首个控件做底（caption 按变量名重生成、id 去重），
  再按 §1.5 的字段全集补齐（片段本身是最小示例，不是完整 schema）；
  片段里的 `images/*.png` 引用按 §1.5 规则 1 处置（剥除/占位图/保留）。
- **父容器**：LVGL 任意控件都能当父；FlyThings 只有 window 系能装子控件 —— 非容器父的子控件
  挂到页面根并登记 D-xx（坐标需手工换算）。

## 4. 报告怎么读（返回体字段）

| 字段 | 含义 |
|---|---|
| `summary` | 控件数 / 按 L1~L5·L? 分级计数 / D 条数 / 未识别条数 / 事件数 |
| `widgets[]` | 每个控件：源变量、LVGL 类型、源行号、映射 target、**level（L1~L5）**、生成 key/caption、notes |
| `downgrades[]` | **D-xx 登记表**（可直接贴进迁移案例的登记清单）：id/源行/控件/level/**reason**/**action** |
| `unrecognized[]` | 识别不了的调用（源行 + 原文 + 原因）——**必须逐条人工过**，不许当不存在 |
| `events[]` | 回调名 + 事件类型 + FlyThings 接线提示（如 `onButtonClick_<Caption>`） |
| `imageActions[]` | 缺图引用处置登记（字段/原引用/stripped·generated·kept·pending，规则 §1.5） |

D-xx 从 D-01 顺序编号（本次转换内连续）；案例收口时接着案例已有编号续编（platform-translate.md §4）。
判定原则不变：**外观一致 + 语义等价 + 可交互 = 迁移成立**；性能与可交互性不算可降级项。

## 5. 典型工作流

1. `flythings_translate_ui(source="<lvgl>.c")` → 看 summary 与 D-xx；
2. 逐条处理 `downgrades`（L3 自绘走 `components/ui_v1/`；L4 写降级点；圆角/描边出图）；
3. 逐条处理 `unrecognized`（多数是动画/阴影/边框 —— 按铁律出图或登记放弃）；
4. `dry_run=False, out=<项目>/ui/main.json` 落盘 → `flythings_ui_preview` 出确认稿 → 回调接线 → pack。

## 6. 已知限制（v1 如实清单）

- **不支持 LVGL v9 XML UI 文件**（`<component>` XML）——评估后超出 v1 范围，留给 v2；
- 坐标/尺寸只认整数字面量（`LV_PCT`/`LV_SIZE_CONTENT`/变量表达式不求值，进 unrecognized）；
- 样式只换算主选择器（`LV_PART_MAIN`/0）；`lv_style_*` 样式对象机制、非主选择器（knob/indicator/
  items/cursor）不换算；
- L2 组合映射（roller→listview、spinbox→stepper 等）只生成**主控件**，组合件/选中条/静态装饰
  需按 `mcp_control_map.json` 片段手工补齐；
- 多行折行：LVGL label 自动折行，FlyThings textview 不折行 —— 超宽文本手工插 `\n`；
- `lv_align_to`（相对兄弟控件）不换算；`lv_label_set_text_fmt` 等动态文本只登记；
- 不生成 logic 代码（回调只登记名字）；不出正式图（缺图引用按 §1.5 剥除或出占位图，
  正式图走 flythings_generate_ui_assets 后把引用写回）。

## 7. 下一步（roadmap）

- v2：LVGL v9 XML 输入、`lv_style_*` 对象机制、L2 组合件自动补齐（参考 `templates/ui_blocks/blocks/`）；
- Qt `.ui` / Android XML 输入路线（同一映射表 + 同一 D-xx 口径，见 platform-translate.md §5 的双平台口径）。

## 相关

- 方法论 / 铁律 / D-xx 登记制 → `knowledge/devflow/platform-translate.md`
- 控件级映射数据 → `mcp_control_map.json` + `flythings_map_control`（`knowledge/uicontrols/control-mapping-capability.md`）
- 出图铁律 → `knowledge/devflow/ui-asset-rules.md`、`knowledge/uicontrols/nine-patch-rule.md`
