# 触摸事件与遮挡（touchable / touchPass / 谁吃掉了我的点击）

> 2026-09-10 沛哥报障「控件点不动 / 列表拖不动 / 点了没选中」定位产出，V85X + EasyUI 2.9.0 实机逐条验证。
> 检索词：触摸/点击无效/点不动/拖不动/滑动/穿透/遮挡/touchable/touchPass/setTouchPass/单选点不了。

## 1. `touchable=false` **不等于**触摸穿透（最容易搞错的一条）

`touchable` 只表示"**这个控件自己**不响应点击"，它**照样会挡住**矩形范围内的下层控件：
下层收不到 `DOWN`，于是既不能拖动、也不会触发点击。

- 症状：列表**能显示、能看**，但**拖不动**；点某一行**没反应**。
- 谁最容易犯：**压在可触摸控件之上的"装饰件"** —— 渐隐/渐变遮罩、选中高亮色带、
  徽标红点、纯图标层、半透明蒙层。
- **正解**：装饰件除 `touchable=false` 外，还要运行期调
 ```cpp
 pCtrl->setTouchable(false);
 pCtrl->setTouchPass(true); // ZKBase：触摸穿透，事件落到下层控件
 ```
 在 `onUI_init()` 里对这批装饰件**统一设置**最省事。
- ⚠ **没有对应的 json 字段**（`touchPass` 不是 json 键），必须写代码。

**层叠顺序**：json 书写顺序 = 层叠顺序（后定义在上层，见 `json-layer-rules.md`）。
所以"渐隐层要盖住滚动文字"就注定它在上层 —— **它必须穿透，否则列表就废了**。

**实测对照**（同一固件，只开关 `setTouchPass`；控件为 listview 顶/底各 42px 的渐隐层）：

| 操作 | 穿透关闭 | 穿透开启 |
|---|---|---|
| 在渐隐覆盖区拖动 | 0% 像素变化（拖不动） | 正常滚动 |
| 在渐隐覆盖区点某行 | 无回调（触摸没到列表） | 正常触发 |
| 在未覆盖的中间条带拖动 | 正常 | 正常 |

## 2. `radiogroup` 等**交互容器**的 `touchable` 必须 `true`

非触摸**容器**会把**整棵子树**从触摸分发里剪掉 —— 子项写 `touchable=true` 也没用。

- 实测：`radiogroup.touchable=false` → 其 `radiobuttons` **全部点不动**（语言设置页完全无法选语言）；改 `true` 后正常。
- 因此 `radiogroup` 是"容器显式 false"通用口径的**例外**，必须写 `true`。
- 补充（2026-09-10 录入）：选中某项用子项 ID 宏 `setCheckedID(ID_MAIN_RadioButtonN)`，**不要用序号/行号**（与字段表一致，见 `radiogroup-checkbox-fields.md`）。

## 3. `ZKListView::setSelection()` 之后必须 `refreshListView()`

`setSelection()` 只改**滚动位置**，不触发**重排 + 重绘** → 会出现
**"行位置与选中样式错位"**：中心行显示的是新值，但"选中样式"（大字号/变色/加粗）
被画到相邻行上 → 用户看到"点了上/下行，高亮却跑到别的行"＝像没选中。

```cpp
lv->setSelection(idx);
lv->refreshListView(); // ⚠ 不能省
```
- 凡是"数据/选中项驱动样式"的列表（`obtainListItemData` 里按 `sel` 改字号颜色）都会踩。
- **定位线索**：如果"进页面时是对的、交互后是错的"，就去比对两条路径 —— 通常一条带了
 `refreshListView()`、另一条漏了。

## 4. 排查顺序（别跳步）

1. **先看日志**：事件到底有没有到控件？回调有没有进？（给关键路径打 `LOGD`）
 —— 只到"页面级全局触摸监听"不算到控件。
 补充（2026-09-10 录入）：事件到了但"没人接"时，检查回调函数名是否与控件 `caption` 完全一致
 （`onButtonClick_<caption>` / `onCheckedChanged_<caption>`），名字不匹配编译不报错、但点了没反应。
2. **再看像素**：视觉对不对？（注意：抓屏要按 `pan` 取当前显示的那一页缓冲，
 否则读到上一帧会得出相反结论）
3. 两者都可能骗人：**日志只证明逻辑跑了，像素可能读错缓冲**。

## 5. 自检清单（改完 UI 必跑）

- [ ] 每个"压在可触摸控件之上的装饰件"都设了 `setTouchPass(true)`
- [ ] `radiogroup`/`checkbox` 等交互容器 `touchable=true`
- [ ] 列表里所有 `setSelection()` 后面都跟了 `refreshListView()`
- [ ] **实机**逐项验证：从控件**边缘起手**拖动 / 点首行 / 点末行 / 跨页返回再进入
- [x] **自动审计已实现**（2026-09-10，`check_all.py` #15 / #16，报 WARN 交人工审批 —— 见下）

### 自动审计：check_all #15 / #16（WARN 需人工审批，不影响交付判定）

| 项 | 查什么 | 判定 |
|----|--------|------|
| **#15**（json 静态） | **同层**中后定义（z 更高）且 `touchable=false` 的控件压在 `touchable=true` 控件之上 | **[WARN]** 附「故意遮挡评估」（见下）；重叠任一轴 <4px 不计（降噪） |
| **#16**（代码静态） | logic.cc 里有 `X->setTouchable(false)` 但同对象无 `setTouchPass(true)` | **[WARN]** 直接给出修复行 `mXxx->setTouchPass(true);` |

**故意遮挡 vs 误压（沛哥 2026-09-10：「方案一也要评估一种可能就是故意遮挡」）**

WARN 分两类，**故意遮挡不是 bug，人工审批时直接忽略**：

| 分类 | 线索（任一命中即判「可能有意」） | 典型情形 |
|------|--------------------------------|----------|
| **[可能有意遮挡]** | ① `modal=true` ② 遮挡件是容器类（`window`/`painter`/`scrollwindow`/`pagewindow`）③ 几乎完全覆盖被压控件（≥90%）④ 遮挡件为整屏尺寸 | 弹窗背景蒙层、禁用态蒙层、防盗点遮挡、渐隐层 |
| **[疑似误压]** | 以上都不满足（多为小装饰件压住可触摸控件的一角/一条） | 图标/文字装饰压在按钮、列表上 |

- 两类都只 **WARN**：不计入 `failures`、不影响 PASS/FAIL 与退出码，逐条人工审批。
- 实测噪声（175 个真实 json，2026-09-10）：命中 14 文件 / 17 处 → **可能有意 7 处、疑似误压 10 处**；负向用例（装饰件移开 + 补穿透）0 命中。
- 局限：#15 只能看 json 层叠与 `touchable`，**查不到运行期才设的 `setTouchPass`**，分类只是线索，最终仍需实机验证（清单第 4 条）。

## 相关

- 层级与层叠顺序 → `json-layer-rules.md`（第 7 条：层叠顺序决定谁收到触摸）
- 字段全集与默认值 → `json-field-mandatory.md`（radiogroup 行已标注 true 例外）
- radiogroup / checkbox 字段与代码操作 → `radiogroup-checkbox-fields.md`
- listview 回调与刷新 → `listview-fields.md`（铁律 7）
- 真机确认画面（按 pan 取活帧） → `devflow/ui-layout-verify.md` §2-1
