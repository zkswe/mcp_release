# 触摸事件与遮挡（touchable / touchPass / 谁吃掉了我的点击）

> 2026-09-10 沛哥报障「控件点不动 / 列表拖不动 / 点了没选中」定位产出，V85X + EasyUI 2.9.0 实机逐条验证。
> 2026-09-17 补充 §6（`setInvalid` 是禁用不是重绘）/ §7（嵌套 window 的卡片内部点不动）——
> 两节均来自真机案例 `projects/translate/tdesign-miniprogram`（同一个「点哪都没反应」的两个真根因）。
> 检索词：触摸/点击无效/点不动/拖不动/滑动/穿透/遮挡/touchable/touchPass/setTouchPass/单选点不了/
> setInvalid/禁用控件/强制重绘/invalidate/嵌套 window/遮罩抢触摸/卡片里的按钮点不动/扁平化/
> data-touchable 不生效/真禁用只能改 json。

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
- [ ] 代码里**没有把 `setInvalid()` 当重绘用**（§6；禁用控件会让整屏点不动）
- [ ] 弹层卡片**不是嵌套 window**：卡片底图与子控件扁平化、排在遮罩之后（§7）
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

## 6. `setInvalid()` 是「禁用控件」，**不是**「强制重绘」（2026-09-17 案例实测）

> ⚠️ 2026-09-22 钟工定规纠偏：**别把这条读成「setInvalid 一律不能用于刷新」**——
> `setInvalid(true)` 是禁用；而 **`setInvalid(!isInvalid())`（交替翻转）是自定义 view / 帧缓冲刷新的平台惯例**，
> gameview / GIF / 地图 / 掌机显示层全这么写。两者的区分、正确写法与真机数据 →
> **`uicontrols/custom-view-refresh.md`**（该文为本类刷新的唯一权威口径）。

⛔ **最容易致命的一条**：`ZKBase::setInvalid(bool)` 的语义是**把控件置为无效状态**
（`ZK_CONTROL_STATUS_INVALID` = 禁用），**不是**通用框架里「invalidate = 标脏重绘」那个意思。

- 头文件事实（`references/easyui/*/include/control/ZKBase.h`）：
  ```cpp
  void setInvalid(bool isInvalid);   // @brief 设置无效状态
  bool isInvalid() const;            // @brief 是否是无效状态
  void invalidate(const LayoutPosition *dirty = NULL);   // @brief 重绘
  ```
  **只有带 `bool` 的版本，没有 `setInvalid()` 无参版本**——照「重绘」的直觉写根本编译不过。
- 真机实测（案例 `projects/translate/tdesign-miniprogram`）：阶段 2 在 `showPage()` 里给 **13 个导航键**
  都调了 `nav->setInvalid(true)`（本意是「强制重绘」），`showOv()` 给弹层也调了一处 →
  **导航全部被禁用、整个案例「点哪都没反应」**。排查了大半天，且一度被误判成「触摸注入坏了 / 面板坏了」
  （注入侧 `dd if=/dev/input/event0` 能证明事件确实写进了节点）。两处删掉后导航立刻全部复活。
- **判据（30 秒定位）**：现象是「界面能看、但所有控件/整屏都不响应」时，**先 grep 代码里有没有 `setInvalid`**，
  再去看注入和像素——顺序反了会白查一天。

### 6.1 为什么「网上/示例里拿它刷帧」也会碰得上：它**确实会触发重绘**（但那不是它的语义）

平台实践里真的存在「用 `setInvalid(!isInvalid())` 交替来刷帧」的写法，来源是**自定义帧缓冲**那条路：

```cpp
// 帧缓冲渲染（GameView / GIF 博客 / game-knob 示例 / setBackgroundBmp 自定义渲染引擎）
mTextView->setBackgroundBmp(&bmp);          // 只调一次
mTextView->setInvalid(!mTextView->isInvalid());   // 交替 → 控件重画 → 把新帧抖出来
```

**机理**：状态变了就要重画外观，于是**顺手把控件重绘了一遍**。所以：

| 用在哪 | 后果 |
|---|---|
| **只读控件**（`textview`，本就不响应点击） | 重绘生效、**看不到副作用**——所以这个技巧“能用” |
| **可交互控件**（`button` / `radiogroup` …） | **控件被禁用**（半个周期还带着“无效态”外观）→ 点不动 |

⇒ 结论：**这是一个依赖“状态变更顺带重绘”的旁路技巧，不是通用重绘 API**；
新代码**不要**用它做通用的“强制重绘”，尤其别用在可交互控件上（可交互控件要刷新请用别的手段）。

⚠️ 但“只限定在只读控件”这个限定**偏窄**（2026-09-22 更新）：平台里**自定义 view**（内容由我们在位图里自己改）
普遍就是这么刷帧的——`GameView.cpp:120`、`CGifPlayer.cpp`（多工程）、`ImageAnimView.cpp:437`、
`FlyMapDemo/mainLogic.cc:218`、`PocketGame/PgDisplay.cpp:77`、`WebViewDemo/mainLogic.cc:88`
（出处行号见 `uicontrols/custom-view-refresh.md` §3）。
**判断口径**：内容是**我们自己往位图/画面里写**的（自绘、帧渲染、双缓冲）→ 用 `setInvalid(!isInvalid())` 翻转；
只是普通控件改了文本/图片/进度 → 引擎本就会重绘，不用手动刷。
（`project_tools` 的 validate 提示、`flythings_blogs` 的 GIF 示例、`references/kb/controls.md`
里那句「帧刷新用 setInvalid 交替」指的正是这个惯例。）

### 6.2 真要用「重绘」：`invalidate()` 也有坑（旧设备可能**未导出**）

⚠️ **2026-09-22 新增（钟工定规 + 真机实测）**：`invalidate(&rect)` 的 `rect` 是**控件本地坐标系**，
不是页面绝对坐标。传 `getAbsolutePosition()` 那种绝对矩形 → 被裁成“从控件本地 (left,top) 到右下角”那块，
**屏上只有那一块会刷新**（实测：20° 步进下纯色标记位移 **0px**，而 `setInvalid(!isInvalid())` 是 **35px**，理论值 34.7px）。
完整对照表 + 判据 → `uicontrols/custom-view-refresh.md` §2。
**非必要不要碰 `getAbsolutePosition()`**（钟工 2026-09-22 12:28）。

- `ctrl->invalidate()`（或带脏区 `invalidate(&pos)`）才是「重绘」的正式 API；
  **带脏区的版本在部分设备上没导出**：实测 `libeasyui.so` 旧于本机头文件时，用它会在 dlopen/链接时报
  `undefined symbol: _ZN6ZKBase10invalidateEPK14LayoutPosition` → **整屏黑**（不是报错退出）。
  真机/组件里用前先确认符号存在（案例侧记录：`projects/translate/tdesign-miniprogram` 的真机验证与
 `gap-list.md` G-38 的头文件核对）。
- **大多数情况根本不需要手动重绘**：`setText` / `setTextColor` / `setBackgroundPic` / `setProgress`
  这类内容变更**引擎本来就会重绘该控件**。
- 「隐藏一个控件」不要靠重绘，用**换同尺寸透明占位图 + 文本置空**
  （`setVisible(true)` 动态显示不重绘）。

## 7. 嵌套 `window` 里的子控件点不动：被**同层更早定义**的 touchable 控件抢走触摸

**现象**：弹窗/卡片**能正常打开、变暗也对**，但**卡片里面的按钮、条目点不动**
（trigger 在页面上点的通，卡片内部一律没反应）。

**根因**：卡片原来是**嵌套 `window`**（`window__N` 里再放一个 window 装卡片），而遮罩是**父窗口里
同层的全屏 `button`（`touchable=true`）且定义在前**。触摸分发按「同层定义顺序」命中——视觉上卡片在上、
不被变暗，但**命中上遮罩先把事件吃掉了**，卡片那一层根本收不到 `DOWN`。
（本质是 §1 的镜像：§1 是「装饰件挡了拖拽」，这里是「遮罩挡了卡片内部」。）

**修法（案例采用，实测有效）**：把卡片**扁平化到控件层**，同层按这个顺序排：

```
[遮罩 button]                  ← 吃空白区，点外部关闭
[卡片底图 textview]            ← touchable=true，吃卡片空白区防误关
[卡片内各控件 ……]             ← 定义在最后 = z 最高 = 先拿触摸
```

要点：

- **不用嵌套 window 装卡片**；卡片底板用 `textview` + `backgroundPic`，子控件坐标改成**绝对坐标**
  （生成器侧把原有相对坐标整体平移即可，案例用的是 `shift(html, dx, dy)` 这类整体平移写法）。
- 卡片底图那层要 `touchable=true`：既吸收卡片空白区的点击（防止穿透到遮罩把弹窗关掉），
  又因为排在遮罩之后而优先拿到触摸。
- 改完验收：**卡片内每个按钮都点一遍**（案例：弹窗「确定/取消/X」+ action-sheet 六形态条目全部恢复，
  check_all 静态检查对这类「跨层抢触摸」**看不出来**，只能真机点）。

## 相关

- 层级与层叠顺序 → `json-layer-rules.md`（第 7 条：层叠顺序决定谁收到触摸）
- 字段全集与默认值 → `json-field-mandatory.md`（radiogroup 行已标注 true 例外）
- radiogroup / checkbox 字段与代码操作 → `radiogroup-checkbox-fields.md`
- listview 回调与刷新 → `listview-fields.md`（铁律 7）
- ★ 装饰件压在可触摸控件之上的陷阱（选中条为什么要 `setTouchPass(true)`） → `listview-wheel-picker.md` §3
- 真机确认画面（按 pan 取活帧） → `devflow/ui-layout-verify.md` §2-1
- 强制重绘 / 禁用语义（`invalidate` vs `setInvalid`） → 本文 §6；抓帧侧口径 `devflow/device-screenshot.md` §3.3-1
- 高频回调只刷变化控件（拖动卡顿的真因） → `high-frequency-callback-perf.md`
