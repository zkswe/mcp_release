# RadioGroup 单选组 / CheckBox 复选框 JSON 字段规范

> 2026-09-07 git.com 全库学习 + basedemo/RadioGroupDemo-New、CheckBoxDemo-New 实测（leqinglingchuang 智能家居窗帘/场景开关等产品在用）。

## 核心铁律

1. **radiogroup 内嵌 radiobuttons 数组，每项本质是 checkbox 风格按钮**（SDK: radiobuttons 子项是 ZKCheckBox，继承 ZKButton）——单选互斥由 group 管理。
2. **选中态图是 picTab.pic2（不是 pic1）**：radiobutton/checkbox 三态图 pic0=正常、pic2=选中（实测 key_comm_normal.9.png / key_comm_blue.9.png）。
3. **代码用子项 ID 宏选中**：`setCheckedID(ID_MAIN_RadioButton1)`，回调拿 `checkedID` 反查是哪项（ID 宏 = UI 文件名_子项 caption 大写）。
4. 一个 group 内每项 `checked` 字段决定初始选中（只能一项 true）。

## JSON 字段表（ftu 实测校准）

### radiogroup
| 字段 | 类型/取值 | 说明 |
|------|----------|------|
| `caption` | string | 控件名 |
| `id` | int | 控件 id（实测 **94002** 段） |
| `radiobuttons` | array | 子项数组（见下） |
| `touchable`/`visible`/`position` | | 通用 |

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
