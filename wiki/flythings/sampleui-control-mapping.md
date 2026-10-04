# SampleUI — Logic.cc ↔ JSON 控件对应关系

> 命名规则: `m` + ID名 + `Ptr` = 控件指针变量
> 回调函数: `onButtonClick_XXXX` 中 XXXX = 控件ID名

---

## 1. main.json ↔ mainLogic.cc

### JSON 控件列表
```json
{
  "textview__1": { "id": 50002, "caption": "TextViewBackground" },
  "slidewindow__2": { "id": 30001, "caption": "Slidewindow1" },
  "window__3": { "id": 110002, "caption": "Window2" },
    "digitalclock__4": { "id": 93002, "caption": "Digitalclock2" },
  "painter__5": { "id": 52001, "caption": "Painter1" },
  "textview__6": { "id": 50001, "caption": "TextView1" },
  "button__7": { "id": 20001, "caption": "ButtonChangeColor" }
}
```

### Logic 代码对照

| JSON caption | JSON id | Logic 变量名 | Logic 使用 |
|-------------|---------|-------------|-----------|
| `TextViewBackground` | 50002 | `mTextViewBackgroundPtr` | `setBackgroundColor()` |
| `Slidewindow1` | 30001 | `mSlidewindow1Ptr` | `turnToNextPage()`, `getCurrentPage()` |
| `Window2` | 110002 | `mWindow2Ptr` | — |
| `Digitalclock2` | 93002 | `mDigitalclock2Ptr` | — |
| `Painter1` | 52001 | `mPainter1Ptr` | `setTouchable()`, `setLineWidth()`, `drawArc()`, `erase()` |
| `TextView1` | 50001 | `mTextView1Ptr` | `setText()`, `getPosition()`, `setPosition()` |
| `ButtonChangeColor` | 20001 | `mButtonChangeColorPtr` | `onButtonClick_ButtonChangeColor()` |

### 回调函数命名规则验证
```c++
// JSON 中 button__7 的 caption = "ButtonChangeColor", id = 20001
// → 指针变量名: m + ButtonChangeColor + Ptr = mButtonChangeColorPtr
// → 回调函数名: onButtonClick_ + ButtonChangeColor
static bool onButtonClick_ButtonChangeColor(ZKButton *pButton) {
    background_color_index = (background_color_index + 1) % 4;
    mTextViewBackgroundPtr->setBackgroundColor(background_colors[background_color_index]);
    return false;
}
```

---

## 2. tesList.json ↔ tesListLogic.cc

### JSON 控件
```json
{
  "listview__2": { "id": 80000, "caption": "Listview1",
    "item": { "subItem": [{ "id": 70001, "caption": "SubItemState" }] }
  },
  "listview__4": { "id": 80002, "caption": "Listview3",
    "item": { "subItem": [
      { "id": 20001, "caption": "SubItemAvatar" },
      { "id": 20002, "caption": "SubItemName" },
      { "id": 20003, "caption": "SubItemDescription" }
    ]}
  },
  "button__6": { "id": 100, "caption": "sys_back" }
}
```

### Logic 对照

| JSON caption | Logic 回调 / 变量 | 作用 |
|-------------|-------------------|------|
| `Listview1` | `getListItemCount_Listview1` | 返回 `sizeof(sSwitches)/sizeof(S_SWITCH_DATA)` |
| | `obtainListItemData_Listview1` | `findSubItemByID(ID_TESLIST_SubItemState)` → `setSelected()` |
| | `onListItemClick_Listview1` | `sSwitches[index].bOn = !sSwitches[index].bOn` → `refreshListView()` |
| | `mListview1Ptr` | `refreshListView()` |
| `Listview3` | `getListItemCount_Listview3` | 返回学生数组长度 |
| | `obtainListItemData_Listview3` | 查找 3 个子项: Avatar/Name/Description |
| | `mListview3Ptr` | — |
| `SubItemState` | `ID_TESLIST_SubItemState` | 宏定义，传给 `findSubItemByID()` |
| `SubItemAvatar` | `ID_TESLIST_SubItemAvatar` | 同上 |
| `SubItemName` | `ID_TESLIST_SubItemName` | 同上 |
| `SubItemDescription` | `ID_TESLIST_SubItemDescription` | 同上 |
| `sys_back` | `onButtonClick_sys_back` | 返回上一页 |

### 关键：子项查找规则
```c++
// JSON 中: subItem caption = "SubItemState", id = 70001
// → 宏定义: ID_TESLIST_SubItemState (ID_UI文件名_子项caption)
// → findSubItemByID 使用这个宏来定位子项
ZKListView::ZKListSubItem* sub = pListItem->findSubItemByID(ID_TESLIST_SubItemState);
```

---

## 3. testButton.json ↔ testButtonLogic.cc

### JSON 控件
```json
{
  "button__1": { "id": 20004, "caption": "Buttonbg" },
  "button__2": { "id": 20005, "caption": "Buttonsw" },
  "button__3": { "id": 20006, "caption": "Buttoncheck" },
  "button__4": { "id": 20002, "caption": "Buttonspecial" },
  "button__5": { "id": 20003, "caption": "Button2" },
  "textview__6": { "id": 50001, "caption": "Textview1" },
  "button__11": { "id": 20007, "caption": "Button_open_developer" },
  "button__14": { "id": 20009, "caption": "Button4" },
  "button__15": { "id": 100, "caption": "sys_back" }
}
```

### Logic 对照

| JSON caption | 回调函数 | 操作 |
|-------------|---------|------|
| `Buttonbg` | `onButtonClick_Buttonbg` | `pButton->setSelected(!pButton->isSelected())` |
| `Buttonsw` | `onButtonClick_Buttonsw` | toggle 开关选中 |
| `Buttoncheck` | `onButtonClick_Buttoncheck` | 复选框切换 |
| `Buttonspecial` | `onButtonClick_Buttonspecial` | 数字 0-9 循环 + 自定义字符图 |
| `Button_open_developer` | `onButtonClick_Button_open_developer` | 开发者模式 |
| `Button4` | `onButtonClick_Button4` | 打开帮助页 |
| `sys_back` | `onButtonClick_sys_back` | 返回 |

---

## 4. testText.json ↔ testTextLogic.cc

### JSON 控件
```json
{
  "textview__1": { "id": 50000, "caption": "Textnormal" },
  "textview__2": { "id": 50002, "caption": "TextTime" },
  "textview__3": { "id": 50003, "caption": "Textpic" },
  "textview__4": { "id": 50005, "caption": "Textview1" },
  "textview__5": { "id": 50006, "caption": "Textview3" },
  "textview__6": { "id": 50007, "caption": "Textview4" },
  "button__7": { "id": 20001, "caption": "Button1" },
  "button__8": { "id": 100, "caption": "sys_back" }
}
```

### Logic 对照
```c++
// Textview1 → mTextview1Ptr — 本例中未使用（只有 onUI_init 的 hideStatusBar）
// Button1 → onButtonClick_Button1 — 打开帮助页
// sys_back → onButtonClick_sys_back — 返回
```

---

## 5. testSlider.json ↔ testSliderLogic.cc

### JSON 控件
```json
{
  "seekbar__1": { "id": 91001, "caption": "SeekBar1" },
  "seekbar__2": { "id": 91002, "caption": "SeekBar2" },
  "circlebar__3": { "id": 130001, "caption": "Circlebar1" },
  "textview__4": { "id": 50001, "caption": "TextValue" },
  "textview__5": { "id": 50004, "caption": "Textview3" }
}
```

### Logic 对照
```c++
// SeekBar1 → mSeekBar1Ptr / onProgressChanged_SeekBar1
static void onProgressChanged_SeekBar1(ZKSeekBar *pSeekBar, int progress) {
    mTextview3Ptr->setText(progress);
    sendProtocol(CMD_SEEKBAR_TEMPERATURE, data, sizeof(data));
}

// SeekBar2 → mSeekBar2Ptr / onProgressChanged_SeekBar2
static void onProgressChanged_SeekBar2(ZKSeekBar *pSeekBar, int progress) {
    mTextValuePtr->setText(progress);
    BRIGHTNESSHELPER->setBrightness(progress);
    sendProtocol(CMD_SEEKBAR_LIGHT, data, sizeof(data));
}

// Circlebar1 → mCirclebar1Ptr
mCirclebar1Ptr->setProgress(50);  // onUI_init 初始化

// TextValue → mTextValuePtr — 显示亮度值
// Textview3 → mTextview3Ptr — 显示温度值
```

---

## 6. 核心命名规则总结

```
JSON 控件 caption    →  Logic 指针变量         →  宏 ID
"ButtonChangeColor"  →  mButtonChangeColorPtr  →  ID_MAIN_ButtonChangeColor
"Buttonbg"           →  mButtonbgPtr           →  ID_TESTBUTTON_Buttonbg
"SubItemState"       →  (子项)                 →  ID_TESLIST_SubItemState
"sys_back"           →  mSys_backPtr           →  ID_MAIN_sys_back
"Textview1"          →  mTextview1Ptr          →  ID_MAIN_Textview1
"SeekBar1"           →  mSeekBar1Ptr           →  ID_TESTSLIDER_SeekBar1
```

**规则公式：**
- **指针变量**: `m` + `caption字段值` + `Ptr`
- **回调函数**: `on` + `控件类型Click_` + `caption字段值`
- **子项宏**: `ID` + `_UI文件名(大写)` + `_` + `子项caption`
- **列表回调**: `getListItemCount_` + `caption` / `obtainListItemData_` + `caption` / `onListItemClick_` + `caption`
