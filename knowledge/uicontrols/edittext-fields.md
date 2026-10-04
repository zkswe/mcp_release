---
id: uicontrols-edittext-fields
title: ⌨️ EditText 输入框 JSON 字段规范
category: uicontrols
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [2026-09-01 入库, UIlayoutDemo, edittext, 默认内置键盘, 不自绘, 输入完成触发回调]
evidence: []
---
# ⌨️ EditText 输入框 JSON 字段规范

> 检索导引：问「输入框怎么做 / edittext 字段 / 预填内容 / 只要数字键盘 / 密码框 / 提示文案 hintText / 输入完成回调」→ 本文。
> 用户口语补充：input 控件的字段有哪些 / 输入框有哪些属性 / placeholder 对应哪个字段 / placeholder 怎么写 / 掩码字符怎么显示。
> 2026-09-01 入库（UIlayoutDemo/edittext.ftu + EditTextDemo basedemo 实测校准，与 html2json 转换实现一致）。
> 输入框：点击自动弹出系统键盘（默认内置键盘，不自绘），输入完成触发回调。

## JSON 字段表

> 字段 / 类型 / 默认值 / 必填以 `ui_tools/ui_schema.json` 为准（`flythings_ui_schema(control_type=edittext)` 取）；
> 下表只留字段名与语义说明。

| 字段 | 说明 |
|------|------|
| `id` | **51000+**（html2json 起始 51000，实际从 51001 分配） |
| `caption` | 控件名（EditText1…），回调函数名由它生成 |
| `position` | 控件位置尺寸 `{left,top,width,height}` |
| `text` | **预填内容**（初始显示文本，如 EtPre 预填 hello） |
| `textType` | **0=全文本（中英文数字）/ 1=仅数字**（数字键盘，EtNumber 实测） |
| `hintText` | **提示文本**（内容为空时显示，如 "请输入账号"） |
| `hintTextColor` | 提示文本颜色（十进制 int，0x888888→8947848） |
| `isPassword` | **true=密码框**，输入字符显示为 passwordChar（EtPwd 实测） |
| `passwordChar` | 密码掩码字符（如 "*"；须配合 isPassword=true 才生效） |
| `fontSize` | 字号（20/24 实测） |
| `colorTab` | 文字颜色（十进制 int；子盒 `{color0}`） |
| `bgColorTab` | 背景颜色（默认 0xFFFFFF 白底；子盒 `{color0}`） |
| `beepEnable` | 按键音（true 默认） |
| `alignment` | 对齐位标志（37=水平垂直居中） |
| `visible` | 可见性 |
| `touchable` | 可交互 |
| `bold` / `italic` | 粗体/斜体（文字控件通用，2026-09-01 校准） |
| `rollEnable` / `rollDirection` / `rollStep` / `rollIntervalTime` | 文字滚动（文字控件通用） |

## 回调

```c++
// 输入内容变化时触发（参数为当前完整字符串）
static void onEditTextChanged_EditText1(const std::string &text) {
    LOGD("输入内容 = %s", text.c_str());
    int n = atoi(text.c_str());   // 数字字符串转 int
    double f = atof(text.c_str()); // 转浮点
}
```
- 控件指针 `mEditText1Ptr->getText()` 可代码读取；`setText()` 可写回
- check_all 会核对：edittext（id 51000~52000）必须有对应 `onEditTextChanged_<caption>` 回调

## html2json HTML 写法

```html
<!-- 普通输入框：div.input，内容=预填文本 -->
<div class="input" data-x="20" data-y="30" data-w="300" data-h="40"
     data-caption="EditText1" data-hint="请输入账号" data-hint-color="#888888">hello</div>

<!-- 数字键盘：data-num -->
<div class="input" data-num="1" ...></div>

<!-- 密码框：data-password + data-password-char -->
<div class="input" data-password="1" data-password-char="*" ...></div>
```
- class 映射：`input / edit / edittext` → edittext 控件
- `data-hint` → hintText；`data-hint-color` → hintTextColor；`data-num` → textType=1；`data-password` → isPassword=true；`data-password-char` → passwordChar；div 文本 → text（预填）
- 输入法：全文本需项目开启拼音输入法（pinyin 包）；仅数字用 textType:1

## 常见坑

- **isPassword 必须配合 passwordChar**：只设 isPassword=true 不设 passwordChar，掩码字符默认行为可能不符合预期
- 密码框禁止预填真实密码到 `text`（明文入库）
- 输入框背景默认白色：透明背景需求要显式设 bgColorTab 或背景图
- 键盘是系统内置（ZKEditText 自动弹出），**不要自绘键盘**（除非自定义输入法 IME 场景）
- id 段 51000 与 textview(50000)/diagram(60000) 相邻，回调核对按 `51000 <= id < 52000` 判定
