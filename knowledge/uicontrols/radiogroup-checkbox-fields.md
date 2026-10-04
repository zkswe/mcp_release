---
id: uicontrols-radiogroup-checkbox-fields
title: RadioGroup 单选组 / CheckBox 复选框 JSON 字段规范
category: uicontrols
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [2026-09-07 git, 场景开关等产品在用]
evidence: []
---
# RadioGroup 单选组 / CheckBox 复选框 JSON 字段规范

> 检索导引：问「单选组·复选框怎么做 / radiobuttons 子项字段 / 选中态用哪张图（pic2）/ setCheckedID 怎么用 / 单选点了没反应」→ 本文。
> 用户口语："一组选项只能选一个怎么实现·互斥单选·是不是单选还是多选" / "代码怎么知道用户选了哪一项·取选中值·选中项回传" / "选项按钮三态图怎么配（正常·按下·选中）·状态图/切图" / "选中态图片不切换·点了图不变·切了没反应"。
> 2026-09-07 git.com 全库学习 + basedemo/RadioGroupDemo-New、CheckBoxDemo-New 实测（leqinglingchuang 智能家居窗帘/场景开关等产品在用）。

## 核心铁律

1. **radiogroup 内嵌 radiobuttons 数组，每项本质是 checkbox 风格按钮**（SDK: radiobuttons 子项是 ZKCheckBox，继承 ZKButton）——单选互斥由 group 管理。
2. **选中态图是 picTab.pic2（不是 pic1）**：radiobutton/checkbox 三态图 pic0=正常、pic2=选中（实测 key_comm_normal.9.png / key_comm_blue.9.png）。
3. **代码用子项 ID 宏选中**：`setCheckedID(ID_MAIN_RadioButton1)`，回调拿 `checkedID` 反查是哪项（ID 宏 = UI 文件名_子项 caption 大写）。
4. 一个 group 内每项 `checked` 字段决定初始选中（只能一项 true）。
5. **⚠️ `touchable` 必须为 `true`**（2026-09-10 修正，实测出过错代码）：
   radiogroup 虽然写的是「容器」结构（内含 radiobuttons[]），但**不适用**`knowledge/uicontrols/json-field-mandatory.md` 里「容器显式 false」的通用口径；
写 `false` 时整组**收不到触摸**，表现：单选按钮点了没反应 / 选中态不切换。
   - 生成器（html2json.py `_open_radiogroup`）已修为 `'touchable': True`
   - radiobutton 子项本身也是 `touchable: true`（本质 ZKCheckBox 按钮）
   - 为什么不适用：“容器 false” 是给 window/painter 这类**不响应交互的容器/背景**定的；radiogroup 本身就是要被点的交互集合
   - 完整触摸语义与「点了没反应」排查顺序 → `knowledge/uicontrols/touch-events.md`

## JSON 字段表（ftu 实测校准）

### radiogroup
| 字段 | 类型/取值 | 说明 |
|------|----------|------|
| `caption` | string | 控件名 |
| `id` | int | 控件 id（实测 **94002**段） |
| `radiobuttons` | array | 子项数组（见下） |
| `touchable` | bool | **必须 `true`**（2026-09-10 修正；false = 整组点不动，见铁律 5） |
| `visible`/`position` | | 通用 |

### radiobuttons[] 子项（实测结构）
```json
{"caption": "RadioCurtainGauzeOn", "checked": false,
 "picTab": {"pic0": "key_comm_normal.9.png", "pic2": "key_comm_blue.9.png"},
 "text": "开启", "id": 22004, "fontSize": 20,
 "iconPosition": {...}, "colorTab": {...}}
```

### checkbox（独立复选框，CheckBoxDemo）
| 字段 | 说明 |
|------|------|
| `checked` | bool 初始勾选 |
| `picTab` | {pic0: 未选图, pic2: 选中图} |
| `text` | 旁边文字 |

## 代码操作

```cpp
// 单选组
mRadioGroup1Ptr->setCheckedID(ID_MAIN_RadioButton1);   // 选中某项（用子项 ID 宏）
int id = mRadioGroup1Ptr->getCheckedID();               // 当前选中项 ID
mRadioGroup1Ptr->clearCheck();
class Listener : public ZKRadioGroup::ICheckedChangeListener {
  virtual void onCheckedChanged(ZKRadioGroup *pGroup, int checkedID) {
    switch (checkedID) { case ID_MAIN_RadioButton1: ... }
  }
};
mRadioGroup1Ptr->setCheckedChangeListener(&listener);

// 复选框
mCheckbox1Ptr->setChecked(true);
class L : public ZKCheckBox::ICheckedChangeListener {
  virtual void onCheckedChanged(ZKCheckBox *p, bool isChecked) { }
};
mCheckbox1Ptr->setCheckedChangeListener(&l);
```

## 样例代码
RadioGroupDemo-New / CheckBoxDemo-New；leqinglingchuang-transfer（DeviceCurtainLogic 窗帘开关、SceneLogic 场景多选）；老工程回调命名 onCheckedChanged_RadioGroup1(ZKRadioGroup*, int checkedID) / onCheckedChanged_Checkbox1(ZKCheckBox*, bool)。
