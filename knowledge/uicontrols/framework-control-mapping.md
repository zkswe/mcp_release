---
id: uicontrols-framework-control-mapping
title: 跨框架控件映射（摘要 + 指针）— 权威表在 components/ui_v1/
category: uicontrols
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [跨框架, 控件映射, 翻译, 转换, 小程序转 FlyThings, Qt, Android, emWin, tabview, tab 页签, pagewindow, 五级处置, L1 L2 L3 L4 L5, 缺口级别, 3D 伪 3D, 控件对照表]
evidence: []
---
# 跨框架控件映射（摘要 + 指针）— 权威表在 components/ui_v1/

> 检索导引：问「控件对照表在哪 / LVGL·Qt·Android·小程序控件对应我们什么 / 五级处置 L1~L5 / tab 页签怎么对应」→ 本文为摘要指针；机读权威表走 `flythings_map_control`（用法见 `knowledge/uicontrols/control-mapping-capability.md`）。
> 检索词：跨框架 / 控件映射 / 翻译 / 转换 / LVGL 转 FlyThings / 小程序转 FlyThings / Qt / Android / emWin /
> tabview / tab 页签 / pagewindow / 五级处置 / L1 L2 L3 L4 L5 / 缺口级别 / 3D 伪 3D / 控件对照表。
> 用户口语补充：控件映射怎么查 / 控件映射规则 / tab 页签怎么做 / pagewindow 和 tabview 什么关系 / L1 L2 L3 是什么意思 / 缺口级别 L1 到 L5 / 3D 效果能实现吗 / 跨框架迁移控件怎么处理。
>
> **本文件只放摘要与关键口径**，避免与权威表两处漂移。**权威入口**：
> - ★**机读映射（开发直接用这个）**：仓库根目录 `mcp_control_map.json`（六框架 213 条）+ MCP op
>   **`flythings_map_control(query, source)`**（一次对上我们的控件 + 级别 + 可直接粘的 json 片段；
>用法/命中不到怎么办：`knowledge/uicontrols/control-mapping-capability.md`）
> - `components/ui_v1/control-map.md`（散文权威表：源控件 × 我们控件 × 级别 × 备注）
> - `components/ui_v1/logic-map.md`（逻辑映射：事件/定时器/列表/导航/状态）
> - `components/ui_v1/gap-list.md`（缺口编号 G-01~G-36 + 五级处置 + 3D 策略 + 工具链坑 T1~T12）
> - `components/ui_v1/platforms.md`（分辨率/rotate/easyui 版本与控件可用性差异/设备限制）
> - `components/ui_v1/components.md`（状态表三段：已实现自定义控件 / 映射项 / 计划中的自定义控件）
> - `components/ui_v1/_mapping/`（有平台对应控件的接线留档，**不算控件包**）
> - 案例与真机证据：`components/ui_v1/examples/README.md`
>
> 建立：2026-09-16（v0.27.71-open）｜适用：FlyThings IDE + easyui 这一代（`ui_v1`；将来新方案另开 `ui_v2`）

---

## 1. 三条必须先记住的口径

1. **控件一律换成 FlyThings 自带控件做语义映射**，不照搬源框架外观/自绘实现；
   `ZKPainter` 自绘**只用于平台确实没有的能力**（图表/仪表/环形刻度/富文本），且每处必须在 `components/ui_v1/gap-list.md` 点名。
2. **`tab` 类容器（`lv_tabview` / `ViewPager+TabLayout` / 小程序 `swiper+tab` / `QTabWidget`）→ 一律 `pagewindow`（ZKPageWindow）**，
自带滑动切页 + `onPageChange`；**禁止**用「多个整屏 `window` + 按钮显隐」拼（**丢手势滑动**）。
3. **缺口统一五级**：`L1 等价` / `L2 组合` / `L3 自绘` / `L4 降级` / `L5 不支持`；
旧案例的 `A/B/C/D` 与旧 `L1~L5` 按 `components/ui_v1/control-map.md` §0.1 换算（并列取差、自绘记 L3）。
4. **口径（2026-09-16 需求方修正）**：**有对应控件 → 映射能力（op + `mcp_control_map.json`），不写散文**；
   **平台真缺 → 才做成 `components/ui_v1/<源控件名>/` 自定义控件包**；有对应控件但接线值得留 → `ui_v1/_mapping/`。

## 2. 最常用的 10 条映射（速查，细则看权威表 or 跑 op）

| 源（各家） | FlyThings | 级别 |
|---|---|---|
| 按钮 `button`/`lv_btn`/`QPushButton` | `button__N`（ZKButton，`picTab`/`bgColorTab`） | L1 |
| 文本 `text`/`lv_label`/`TextView` | `textview__N`（支持 `\n`，**不自动折行**） | L1 |
| 输入框 `input`/`lv_textarea`/`EditText` | `edittext__N`（**系统内置键盘**） | L1 |
| 开关/复选 `switch`/`checkbox` | **两态 `button__N`**（`picTab{pic0,pic1,pic2}`）——⚠️ `fun` 不为 `checkbox__` 生成宏/指针/回调 | L2 |
| 单选组 `radio-group`/`RadioGroup` | `radiogroup__N`（回调给**选中项控件 ID**） | L1 |
| 滑块 `slider`/`lv_slider`/`SeekBar` | `seekbar__N`（背景禁 `.9.png`；尺寸==position） | L1 |
| 列表 `RecyclerView`/`lv_list`/`scroll-view` | `listview__N`（三回调；行自身 `setText("")`） | L1 |
| **页签 `lv_tabview`/`ViewPager`/`swiper`**| **`pagewindow__N`（ZKPageWindow）+ 页签按钮组**（接线留档 `ui_v1/_mapping/TabView/`） | L1/L2 |
| 弹窗 `modal`/`Dialog`/`lv_msgbox` | `window__N`(`modal:true`) + `showWnd/hideWnd` | L1 |
| 图表 `lv_chart`/MPAndroidChart/`QChart` | **`painter__N` 自绘**+ 刻度文字用 `textview__N`（现成包 `ui_v1/Chart/`） | **L3**|
| **滚轮选择器 `picker-view`/`lv_roller`/`LISTWHEEL`/`NumberPicker`/`TimePicker`（含时钟盘）**| **`listview__N` 组合**（`cycleEnable:true` + `edgeEffect:1`/`dragMaxDis`:50/`autoRollback:true`；正中行 = 选中行靠**数据侧平移**；**选中条挂静态装饰 `textview`**，不挂行） | **L2**|

## 3. 高频缺口（一句话版）

- **下拉选择 / picker / Spinner / ComboBox**→ 按钮 + `window`(modal) 列表（**L4**：无滚轮惯性、无多列联动）。
- **日期/日历/时间**→ 日期：按钮 + 模态日历（42 个 `textview` + 触摸反算；painter 无文字 API）（**L4**，已落地 `ui_v1/Calendar/`）；
  **时间：`TimePicker`（含时钟盘）/`QTimeEdit`/`picker mode=time` → `listview` 组合（L2）**（2026-09-19：TimePicker 走 listview 实现对应）。
- **下拉刷新 / 滚动驱动动画 / CSS 动态样式 / 平滑滚动 / 横向滚动惯性**→ 定时器 + 数值联动近似（**L4**）。
- **flex/grid**、**拖拽排序/侧滑删除**、**系统主题联动**→ **L5（不支持）**，有替代建议。
- **滚轮选择器（`WheelPicker`/`TimePicker` 类，含时钟盘）**→ **不是 L5**：2026-09-19 已改为 **L2**（`listview` 组合，循环列表 + 数据侧平移定正中行 + 选中条挂静态层；口径 `knowledge/uicontrols/listview-wheel-picker.md`，含 §6 时间选择/时钟盘），原自绘包 `ui_v1/WheelPicker/` **已移除**、`ui_v1/TimePicker/` **不做包**（时钟盘的圆形排列观感需 12 方位按钮组或自绘 → **观感降级说明，不是能力缺失**）。
- **3D**：Z21/F133 **无 GPU/无硬解 → 伪 3D/2.5D**（贴图 + 烘焙阴影 + 序列帧）**或软件模拟（软渲染/软光栅）**；
  **真 3D GPU 实时管线（着色器/实时光栅化）超出能力边界**，目前仅 V85X（disp 分层）验证过真 3D 形态。
  ⇒ 完整能力边界（三层：基础控件 / canvas 画布 / 自定义控件；非 3D GPU 皆可 + 软件模拟）见 `knowledge/devflow/render-extension-boundary.md`。

## 4. 必须避开的工具链坑（写错就不亮/不编译，详见 `components/ui_v1/gap-list.md` §4）

1. `fun` 不为 `checkbox__` 生成宏/指针/回调 → 用两态按钮。
2. 设备侧 `libeasyui.so` **无 `getAbsolutePosition()`**→ 只用 `getPosition()`（否则 `dlopen` undefined symbol → **整屏黑**）。
3. `fun launch`（Windows）把 `resources/<子目录>/*` 推成**平铺名**（`images\x.png`）→ 图片控件全空，需设备侧修复脚本。
4. `html2json` 把 **`#000000` 当「未设置」**→ 纯黑写 **`#010101`**。
5. listview **行自身 `text` 会与 subItem 叠字**→ 显式 `setText("")`。
6. `ZKListView::setSelection()` **只改滚动位置、不重绘**→ 数据变了必须 `refreshListView()`。
7. `check_all`：seekbar 禁 `.9.png`；`resources/images/` 自动生成的图**尺寸必须 == 控件盒**。

## 5. 边界（与检索规则的关系）

- 「控件用法/字段/API 从哪来」仍按 `knowledge/uicontrols/retrieval-boundary.md`：**只查 MCP 知识库或官方站**，
禁止拿别家框架的字段/API 套用（`android:hint`→`hintText`、`lv_label_set_text()`→`setText()`）。
- 「**别的框架的控件对应我们哪个控件**」是**映射问题**，权威答案就是本文件指向的 `components/ui_v1/control-map.md`。
- 未收录/未验证的：标 `未验证`，**不猜**（要确认的写进 `components/ui_v1/gap-list.md` §5 待确认表）。
