---
id: uicontrols-textview-fields
title: 文本控件（TextView）—— 特殊字符集 / 状态色 / 跑马灯 / 纯显示定位（字段表不在这里）
category: uicontrols
status: review
confidence: offline
verified_at: 2026-10-03
stale_days: 180
origin: total
source: 2026-10-03 收录：官方文档 developer.flythings.cn/zh-hans/textview.html（行为与代码 API 的权威）+ ui_tools/ui_schema.json（字段真源，只读不抄）+ 仓内既有四页（json-field-mandatory 派生表 / widget-code-api / text-box-height-rule / wysiwyg-render-spec §4）对账后只补缺口
needs_evidence: true
platforms: []
tags: [文本控件, textview, 特殊字符集, charsetTab, 状态色, 跑马灯, rollEnable, 字号下限, 文本盒, setText, 背景图动画, 文字颜色, 字体, 多行]
evidence: []
---
# 文本控件（TextView）

> 检索导引：问「文本控件怎么用 / 文本有哪些属性 / 特殊字符集怎么配 / 字符变图片 / 文字颜色怎么改（含
> 无效·选中·按下三态）/ 跑马灯怎么滚 / 文字能不能点击 / 背景图当动画 / 怎么显示小数 / 文字不显示」
> → 本文。
> **字段（必填/默认值）不在这里**，去看 §0 的真源表；渲染与对齐语义也不在这里。

## 0. 先看真源与分工（**本页故意不抄字段表**）

`ui_tools/ui_schema.json` 自己写着：「字段/类型/必填/默认值以本表为准；`knowledge/*.md` 只负责原理、流程与行为」。
所以本页**只补没人写过的行为与坑**，其余一律指路：

| 你要问的 | 唯一真源 |
|---|---|
| 有哪些字段 / 哪些必填 / 默认值多少 | `knowledge/uicontrols/json-field-mandatory.md` 的**「每类型必写键」表**（由 `scripts/gen_ui_schema_docs.py` **从注册表派生**，`--check` 进门禁）↔ 机器可读真源 `ui_tools/ui_schema.json` |
| 代码 API（`setText` 重载 / `setTextColor` / `setBackgroundPic` 逐帧动画套路 / `\n` 多行） | `knowledge/uicontrols/widget-code-api.md` §ZKTextView |
| 居中/左对齐那个数字是什么（对齐位模型） | `knowledge/devflow/wysiwyg-render-spec.md` §4（2026-10-01 真机定案，**含真机证据**） |
| 字号下限 18px / 文本盒抬高度 / UTF-8 安全截断 | `knowledge/uicontrols/text-box-height-rule.md` |
| 文字跟语言变（`@key` / `setTextTr`） | `knowledge/devflow/i18n-multilang.md` |
| 图片与控件盒尺寸铁律 | `knowledge/devflow/ui-asset-rules.md` |

## 1. 定位：**纯显示控件**，没有回调

- 注册表里 `textview` 的 `interactive: false`、**没有任何 `callbacks`** —— 它**不能接收事件**。
- 所以：**「一段会变的文字」用它；「一段能点的文字」要用 `button`**（button 支持内联 `text`，
  schema 明确写着「不要再叠 textview」）。
- `touchable` 是**必填**字段，纯显示控件要**显式 `false`**（容器与纯显示控件都显式 false ——
  见 `json-field-mandatory.md` §2 的分组）。⚠️ 把它写成 `true` 会让它**吃掉触摸**却**无事可做**
  （`flythings_layout_audit` 的 `touch_steal` 就是查这类；触摸层问题另见
  `knowledge/uicontrols/touch-events.md`）。
- 多行：`\n` 直接支持（`widget-code-api.md`）；换行的**版面与盒高**规则见 `text-box-height-rule.md`。

## 2. ⚠️ 特殊字符集（`charsetTab`）：**字符 → 图片**的映射表

官方口径（textview 页「特殊字符集的使用」）：

- 作用：把每个字符按 ASC 码**映射成一张图片**显示 —— 适合数码管风格时钟、信号格这类"图标化字符"。
- 配法：IDE 里「特殊字符集设置 → 更多 → 导入图片 → 可改对应的 asc 码/字符 → 保存」。
  对应 json 字段就是 `charsetTab`（`button-fields.md` 记它出现率 0.7%，属"要才写"）。
- ⚠️ **硬约束（最容易踩）**：**一旦设了特殊字符集，每个字符都会被拿去查表；表里没有映射的字符
  `不会显示到屏幕上`**（不是显示成原字，是**不显示**）。
  → 现象对照：客户说「设了字符集以后有些字没了」= 这条。
- 用法样例（仓内实战）：信号格 = `setText(5 + level)` 配字符表（`widget-code-api.md` 网络节）。

## 3. 文字颜色的**三态**：属性表三组色 ↔ 代码 setXxx

官方口径：textview 有**三组**与颜色相关的属性 ——

| 属性（IDE 属性表） | 对应 json | 说明 |
|---|---|---|
| 颜色设置 | `colorTab` | **按控件状态**分别设文字色（`color0` 是主文字色；五槽色表，未用槽恒 `-1`） |
| 背景色 | `backgroundColor` | 整个矩形区域的底色，**不随状态变化** |
| 背景颜色设置 | `bgColorTab` | 背景色的**按状态**扩展版 |

⚠️ **状态色的生效条件**（官方原文）：代码调用 `setInvalid(true)` / `setSelected(true)` / `setPressed(true)`
时，**只有当属性表里对应的那个状态色不为空**，颜色才会变；**为空则无变化**。
→ 现象对照：「代码里 `setSelected(true)` 了，颜色没变」= 属性表里没配"选中时颜色"，不是 API 没生效。

```cpp
mTextView1Ptr->setInvalid(true);        // 无效态（配了"无效时颜色"才变色）
mTextView1Ptr->setSelected(true);       // 选中态
mTextView1Ptr->setPressed(true);        // 按下态
mTextView1Ptr->setTextColor(0xFF0000);  // 直接给 RGB（16 进制）
```

## 4. 跑马灯（`rollEnable` / `rollDirection` / `rollIntervalTime` / `rollStep`）

- 已知（注册表口径）：四个可选字段，默认 `false / 1 / 150 / 5`；
  语义是**单条文字滚动（跑马灯）**，文字控件通用（`edittext-fields.md` 也归为"文字滚动"）。
- **规范**：`rollEnable` 开滚动；**`rollStep` = 每步位移像素**；`rollIntervalTime` = 每步间隔毫秒；`rollDirection` = 方向（0/1）。**仍未核**：`rollDirection` 0/1 与左右方向的对应、滚完一圈是否循环。（字段级规范的真源 = `ui_tools/ui_schema.json`；本节只说用法与约束）
  （`rollStep` 的单位、`rollIntervalTime` 与它的关系**已定**于真源 `ui_schema.json`：位移 = `rollStep` × 步数、步频 = `rollIntervalTime`；不必再上机试。）
- 另外两条**已知边界**（不是坑，是"别期待"）：
  ① 离线渲染器**不渲染滚动**（`json2img` 把它列进"未支持"：只画静止首屏）——
     所以**预览图里看不到跑马灯效果是正常的**，别据此判它没生效；
  ② 它与 `slidetext` **不是一回事**：`slidetext` 是**多单元滑动选择器**（输入法候选条那类），
     见 `knowledge/uicontrols/slidetext-fields.md`。

## 5. 显示数字/小数：走代码不是走字段

- `setText` 有 **int / char / const char\* / std::string 多重载**（`widget-code-api.md` 有提醒：
  **显示数字就传 int，别传 `char 0`**，否则会走 char 分支）。
- 小数：官方做法是 **`snprintf` 先格式化再 `setText`**（如 `"%.3f"`）—— 文本控件本身不做数字格式化。

## 6. 用背景图做逐帧动画（套路，别造新控件）

官方给的写法：给 textview 设背景图 → 定时器每 **50ms** 换一张 `setBackgroundPic("animation/loading_%d.png")`。
⚠️ `setBackgroundPic` 的参数是**相对 `<项目>/resources` 的路径**（也接受绝对路径如
`/mnt/extsd/x.png`），**只有 `resources` 下的资源会被自动打包** → 图一律放 resources。
（仓内同款记录在 `widget-code-api.md`；图与盒尺寸铁律见 `ui-asset-rules.md`。）

## 7. 未收录 / 待补（**如实登记**）

| 项 | 状态 |
|---|---|
| 真机复验 | **未做**（本页无一条是我上机测的）：字段来自注册表、行为来自官方文档与仓内既有页，标 `needs_evidence: true` |
| `roll*` 四个字段的**语义值域** | `rollEnable` / `rollStep`（每步位移像素）/ `rollIntervalTime`（每步毫秒）**已定**（真源 `ui_schema.json`）；**未核**：`rollDirection` 的 0/1 方向映射、滚完一圈是否循环 |
| `charsetTab` 的 json 结构与 asc 码映射表 | 未核（官方只讲了 IDE 侧配法；json 侧字段形态待读源码/实测） |
| `backgroundPic: ""` 的影响 | **规范**：`""` = 不设背景图，**不影响控件可见性**（照常画 `backgroundColor` 与文字）；只有**指向不存在的文件**才会异常。真源 = `ui_schema.json` 的 `valueRules.missingImage` |
| 三态色在**各平台固件**上的差异 | 未核（官方口径未提平台差异）。**复验方法**：同一份 fui 在 F133 / V85X / Z20 上各推一次，用 `flythings_device_preflight` 或设备端 `zkshot` 抓**按下态**那一帧，比对三态色像素是否与 `colorTab` 声明一致 |
| 本页**故意不含**字段表 | 避免成为第 4 份副本 —— 派生表（`json-field-mandatory.md`）由门禁盯着，抄一份出来就会漂 |

## 8. 相关

- `knowledge/uicontrols/json-field-mandatory.md`：**每类型必写键表**（派生，含 textview 行）
- `knowledge/uicontrols/widget-code-api.md`：ZKTextView / ZKEditText 代码 API
- `knowledge/devflow/wysiwyg-render-spec.md` §4：对齐位模型（36/37/38 与 4/5/6 等价）
- `knowledge/uicontrols/text-box-height-rule.md`：字号下限 18px / 文本盒抬高度
- `knowledge/devflow/i18n-multilang.md`：`@key` 与 `setTextTr`
- `knowledge/uicontrols/button-fields.md`：要"能点的文字"用它（含内联 `text`）
- **官方页**：<https://developer.flythings.cn/zh-hans/textview.html>（样例 `TextViewDemo`）；
  通用属性 <https://developer.flythings.cn/zh-hans/ctrl_common.html>
