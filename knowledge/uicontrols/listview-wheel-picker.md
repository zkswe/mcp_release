---
id: uicontrols-listview-wheel-picker
title: listview 做滚轮选择器（WheelPicker）：字段配法 + 中心行对齐 + 三个真机坑
category: uicontrols
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [Z21]
tags: [检索命中条件, 三类问法都命中本文, 滚轮怎么做, 滚轮选择器, 转盘, 循环列表做选择器, 无限滚动列表, picker 多列联动, lv_roller 怎么用, QTimeEdit 怎么做, 那个自绘轮子包还在吗, 滚轮改判 L2 了吗, 滚轮机读映射, wheel 别名, 滚轮拖不动, 滚轮惯性]
evidence: []
---
# listview 做滚轮选择器（WheelPicker）：字段配法 + 中心行对齐 + 三个真机坑

> 检索导引：问「滚轮选择器怎么做 / 时间选择·时钟盘 / 选中条跟着行滚 / setSelection 带不带动画 / 中心行选中值怎么回读 / picker-view 怎么实现·picker-view 怎么用」→ 本文；基础字段见 `knowledge/uicontrols/listview-fields.md`。
> **检索命中条件（三类问法都命中本文）**：**① 滚轮族**（滚轮怎么做 / 滚轮选择器 / 转盘 / 循环列表做选择器 / 无限滚动列表 / picker 多列联动 / picker-view 怎么转 / lv_roller 怎么用 / NumberPicker 支持吗 / LISTWHEEL 对应哪个控件 / QTimeEdit 怎么做 / WheelPicker 有没有原生能力 / 那个自绘轮子包还在吗 / 滚轮改判 L2 了吗 / 滚轮机读映射 / wheel 别名 / 滚轮拖不动 / 滚轮惯性 / 惯性回弹 / 松手回弹对齐 / 拖动选择器怎么回读选中值 / 停下报事件 / 选中项变化回调）；**② 居中行 / 选中条族**（listview 居中选中 / 列表中行 / 行停在中行 / 中间行高亮 / 选中行高亮 / 选择条 / 高亮带 / 选中条（高亮带）跟着滚 / 滚动时高亮条跑了 / 选中条放背景图 / 高亮带挂哪层 / 条跟着行走 / 字色淡出 / 边缘渐隐）；**③ 时间 / 时钟盘族**（时间选择器怎么做 / 日期时间选择 / 时间滚轮 / 时·分·秒怎么拼 / 24 小时制选择 / TimePicker 怎么做 / TimePicker 时钟盘 / 时钟盘怎么实现 / clock dial / 圆形时间选择 / 时钟盘有没有对应能力）。
> **检索词（同义/别名，降级 BM25 与人工核对都用）**：WheelPicker、wheel、roller、lv_roller、picker-view、picker-view-column、picker mode=time、NumberPicker、LISTWHEEL、QTimeEdit、TimePicker、TimePickerDialog、选择器、滚动选择、cycleEnable、autoRollback、edgeEffect。
> **相关**：字段与回调全集 `knowledge/uicontrols/listview-fields.md`；滑动/惯性字段取值 `knowledge/uicontrols/scroll-drag-interaction-spec.md`；json 必写字段 `knowledge/uicontrols/json-field-mandatory.md`；装饰件吞触摸 `knowledge/uicontrols/touch-events.md`；跨框架映射 `knowledge/uicontrols/control-mapping-capability.md`。
> 案例 `projects/translate/tdesign-miniprogram`（Z21 1024×600 真机，`z21/evidence/s4b_*` + `s4b_test.log` 24 项全 PASS；`s4c_*` + `s4c_test.log` 30 项全 PASS = 条改静态层后的现役验收）。
> 结论一句话：**平台 listview 能把滚轮做出来（L2 组合），不用自绘**；但三件事要自己做：①「正中行 = 选中行」用**数据侧平移**摆；②**不能用引擎的选中态**（它会把选中态打在列表盒第 1 行，还会盖掉宿主的 `setSelected`）；③**选中条要挂「静态背景层」，不挂行背景图**（挂行 → 滚起来条跟着走）。
> 缺口编号：`knowledge/../components/ui_v1/gap-list.md` G-23（由 L5「明说不支持」改判 **L2 组合**）、G-37、G-38。

## 速查（滚轮 / 选择器 / 时间选择 / 时钟盘）

- 滚轮选择器 / 转盘 / 循环列表 / 居中选中 / picker 多列联动 → 平台 `listview` 组合（**L2**），不用自绘、不建包。
- 中间行高亮 / 正中行 / 居中选中行 / 选中条 / 高亮带 → **数据侧平移**定中心行（§1）+ 条挂**静态装饰层**（§3 坑 4）。
- 拖不动 / 惯性 / 回弹对齐 / 回读中心行 / 停下报事件 → §2、§4。
- 时间选择 / 时·分·秒 / 时钟盘（clock dial）/ TimePicker / NumberPicker → §6。

## 0. 一句话配法

```jsonc
// 一列 = 一个 listview；可见 5 行；行高 36；总高 180（图 == 盒 铁律 #1）
"listview__N": {
  "caption": "DtHourLv", "rows": 5, "cols": 1, "orientation": 1,
  "rowSpacing": 0, "colSpacing": 0,
  "cycleEnable": true,      // 循环列表：无限滚，没有硬边界（滚轮的语义）
  "edgeEffect": 1,          // 越界拖拽回弹
  "dragMaxDis": 50,         // 越界拖拽上限（**不是**列表高度！见 scroll-drag-interaction-spec.md R2）
  "autoRollback": true,     // 松手对齐整行
  "hasScrollbar": false,    // 选择器不显示滚动条
  "touchable": true, "visible": true, "backgroundColor": -1,
  "position": {"left": 28, "top": 70, "width": 176, "height": 180},
  "item": {                 // 行模板：文字由 obtainListItemData 填，text 留空 ""（见 listview-fields.md 坑 1）
    "caption": "item", "text": "", "alignment": 37, "fontSize": 18,
    "colorTab": {"color0": 6710886, "color1": 6710886, "color2": 6710886, "color3": 6710886, "color4": -1},
    "picTab": {"pic0": "", "pic1": "", "pic2": ""},   // 态图全空：不用引擎选中态（见 §3 坑 1）
    "position": {"left": 0, "top": 0, "width": 176, "height": 36}
  }
}
```

**选中条（高亮带）另外给一个静态层控件，写在 listview 之前**（2026-09-19 12:00 口径，见 §3 坑 4）：

```jsonc
// 5 个装饰 textview：底图 = 条图（176×36 == 控件盒），position = 该列**正中行**盒
"textview__N": {
  "caption": "DtHourBand", "text": "", "alignment": 37, "fontSize": 18,
  "touchable": false,                              // ★装饰件必须不可点
  "backgroundPic": "images/dt_band.png",           // 浅品牌带 + 上下 1px 通栏线（属「条」自身边框）
  "position": {"left": 592, "top": 70 + 2 * 36, "width": 176, "height": 36}
}
// 运行期在 onUI_init/attach 里补：setTouchable(false) + setTouchPass(true)
//（touchPass 无 json 字段，必须写代码，见 uicontrols/touch-events.md §1）
```

字段取值依据：`knowledge/uicontrols/scroll-drag-interaction-spec.md`「循环选择器（月/日/时/分）」档 = `edgeEffect 1 / dragMaxDis 50 / autoRollback true / cycleEnable true`。`dragMaxDis` 的分辨率换算（R6）：基准 50 @1024×600，其他分辨率 `round(scale×50)`，下限 24。（案例里列盒是固定 176×180 不随 k 缩放，与阶段 1-3 的控件盒口径一致。）

⚠️ `color2/pic2` 全置中色/空图**是有意的**：引擎的选中态要「看不见」，见 §3 坑 1。

## 1. 正中行 = 选中行（核心：数据侧平移）

listview 的行排列是「第一可见项 `fi` 往下数 N 行」，5 行时**正中行 = fi + 2**；而平台**没有**「把第 i 项摆到正中」的 API（`setSelection(i)` 只把第 i 项摆到列表盒**第 1 行**，且带动画，见 §3 坑 3）。于是用「数据平移」把位置搬过来：行数据数组长 **2n**（值域重复两遍），数组下标 k 承载

```
值下标(valueAt) = (k - ROT + shift) mod n        // ROT = (可见行数-1)/2 = 2
```

`shift` 就是**「希望落在正中行的值下标」**（当 fi=0 时正中行 = 数组下标 2）。于是：

```cpp
// 让「值 v」落在正中行：纯数据侧动作（改 shift + 重建行数据 + refreshListView）
static void s4DtCenterOn(int c, int v) {
    s_dtShift[c] = v;
    for (int k = 0; k < 3; ++k) {                 // 迭代 3 次只为抹平「读到的中心不是恰好 fi=0」的偏差
        buildItems(c);                            // items[k] = label((k - ROT + shift) mod n)
        lv[c]->refreshListView();
        int A = centerArrIdx(c);                  // 见 §2（回读）
        int cur = valueOf(c, A);                  // (A - ROT + shift) mod n
        if (cur == v) break;
        s_dtShift[c] = ((v + (v - cur)) % n + n) % n;   // 平移补偿：shift +d -> 同一下标的值也 +d
    }
}
```

**为什么不用 `setSelection` 做程序化定位**：引擎对它是**带动画**的（调用后 `fi` 会连续跑好几帧，立即回读拿到的是中间态）→ 「读-改-读」的迭代校正会越推越远。真机现场（改数据平移之前）：点「复位」后小时列跑到 **14 时**、年列跑到 **2025**（应当回到 9 时 / 2024）。数据平移不碰滚动位置、不受动画干扰，且**不打断用户手指**，一次收敛。

## 2. 中心行回读（实时联动 / 停下报事件）

平台**没有**「滚到底 / 停下 / 选中项变化」回调（G-27/G-28），用宿主定时器（16ms）轮询两个 getter：

```cpp
int fi  = lv->getFirstVisibleItemIndex();     // 第一可见项（下标）
int off = lv->getFirstVisibleItemOffset();    // 第一可见项被上移的像素数的**相反数**
int ih  = (int) lv->getItemHeight();
int h   = lv->getPosition().mHeight;
int A   = fi + (h / 2 - off) / ih;            // 盒中线落在哪一行（= 正中行）
```

**`off` 的符号口径（真机实测，别猜）**：往前滚 -> `off` 从 0 递减到 −35 左右，然后 `fi` +1、`off` 归 0。轨迹样本：`fis=[2,2,3,3,4,4,5,5,6,6]` / `offs=[0,-20,0,-21,-1,-21,-1,-19,-3,-19]`。所以 `off<0` = 内容整体上移 |off| 像素 -> 公式里是 `(h/2 - off)`；写成 `(h/2 + off)` 会**差 1~2 行**，现象就是「拖动时底带明显飘在中线之上/之下」（案例里有像素断言：拖动中底带垂直重心与盒中线误差 ≤ 30px，公式对 = 实测 0.5~7px；公式错 ≥ 54px）。两条 API 在 easyui **2.6.0（Z21）/ 2.9.0（F133|F136）/ 2.10.0**头文件里都有（`ZKListView.h`）。

## 3. 四个真机坑（都不在官方文档里）

### 坑 1：引擎自己维护「当前项」选中态，会盖掉宿主的 `setSelected`
- **现象**：`obtainListItemData` 里对正中行 `setSelected(true)`（配 `item.picTab.pic2 = 选中带图`）、底带也确实出现在正中行；但**用户拖过一列之后**，底带跑到**列表盒第 1 行**（= `getFirstVisibleItemIndex()`）上去，正中行反倒没带。
- **根因**：listview 引擎自己记着「当前项」，绘制时按它套用态图/态色，用户在列表上操作后它把这个当前项更新为**第 1 可见行**，于是宿主在 `obtainListItemData` 里设的 `setSelected` 被覆盖。
- **处置**：**选中视觉全部由宿主自己画**，不用引擎的态图 —— `item->setTextStatusColor(0, 品牌色/淡出色)`（正中行文字色）+ **静态选中条层**（见 坑 4）；同时 json 里把 `pic0/pic1/pic2` 留空、`color2/color3` 置**与常态同色**，让引擎的选中态「看不见」。（2026-09-19 12:00 之前这里的处置是「行上 `setBackgroundPic(条图/空图)`」——**那条路已废弃**，条会跟着行走，见 坑 4。）
- **顺带**：这正好也解决了「淡出」——按行距给每行设文字色（向白底插值）即等价自绘包的伪 alpha。

### 坑 2：行属性不会因为「中心行变了」而自动重刷
- **现象**：滚完停住，正中行明明换了，底带却停在**错的行**上（比如停在第 1 行）。
- **根因**：引擎只在「行进入可视区」或 `refreshListView()` 时调 `obtainListItemData`；行上带的是**当时的**中心行下标，中心行后来变了，旧行不会重刷。
- **处置**：**中心行一变就 `refreshListView()`**（频率 = 每跨一行一次 ≈ 旧自绘包重画 painter 的频率，CPU 可接受）。

### 坑 3：`setSelection(i)` 是带动画的，且只对齐到「第 1 行」
- **现象**：连调 `setSelection` 做迭代校正会**越推越远**（复位后跑偏，见 §1）。
- **口径**：`setSelection(i)` 让第 i 项落在列表盒**第 1 行**（不是正中行），且落地是**动画**（多帧）。
- **处置**：程序化定位改用 §1 的数据平移；确实要 `setSelection` 时，调用后**先等动画跑完再回读**（`fi` 连续 2~3 帧不变再判定），不要「调用+立即回读+再调用」。
- 另注：`components/ui_v1/gap-list.md` G-32 旧口径写「`setSelection(index)` 直跳」（无平滑滚动）—— 本次实测**它是有滚动动画的**，缺的是「滚动到任意偏移 / 平滑滚到指定像素」（G-32 已同步修正）。

### 坑 4：**选中条挂在行背景图上 -> 滚动时条跟着行走**（★2026-09-19 12:00 需求方口径：条要挂**静态背景层**）
- **现象**（经需求方原话「选中条放到背景图里面。这样子滚动以后选中条不会动」）：上一轮的实现是「正中行在 `obtainListItemData` 里 `item->setBackgroundPic(条图)`」——挑不出错，底带也确实只出现在正中行，但**手指一拖，条就跟着行跑**（整条跟着滚动位移，不是停在框的正中）。
- **根因**：行背景图是**行自己的绘制内容**，行随滚动偏移 -> 条也随滚动偏移。listview 没有「固定叠层（sticky overlay）」概念，行模板能画的只有「行盒内、随行移动」的东西。
- **处置（正确做法）**：把条做成页面里的**静态控件**（z 比 listview 低），行侧**不再挂任何背景图**：
  1. json 里给每列加一个装底图的 **装饰 `textview`**（`backgroundPic = images/xxx.png`，图 == 盒），`position` 就取该列**正中行**的盒（列盒 176×180 / 行高 36 -> 正中行 top = 列 top + 2×36）；
  2. **必须写在 listview 之前**：json 书写顺序 = z 序（后定义在上层，见 `knowledge/uicontrols/json-layer-rules.md`）-> 条在下层；行的 `item` **无底图/无底色（透明）**-> 条从行下面透出来，**滚动时条一个像素不动**；
  3. 装饰件 `touchable:false`（json 显式写），运行期再 `setTouchable(false) + setTouchPass(true)`（`touchPass` **无 json 字段**，见 `knowledge/uicontrols/touch-events.md` §1；虽然条在下层、理论上抽不到触摸，但作为防线很便宜）；
  4. 选中感就只剩**正中行文字色**（`setTextStatusColor`），顶/底「渐隐」仍按行距给文字色插值。
- **通栏 1px 分隔线归谁**：本案例判定归「**条**」——两条线正好落在条盒的上下边缘（旧自绘包里也是随条一起画的两条线）：不拆图、不拆层。若要把它当「框」看（不随条挪位），就拆成「框线层 + 条层」两个静态控件，都写在 listview 之前即可。
- **验收（两个可机器断言的硬指标，本轮真机实测值）**：
  - **同一次拖动里抓两帧**，对「**纯条区**」逐像素比：差异必须 **0**；纯条区 = **文字永远到不了的侧带**（横向上 `dx <= 50` 或 `dx >= 125`；字形横向范围实测 dx 59..116）—— **不要**把条盒上下 3px 带算进去：静止时那里无字，但**滚动中相邻行的字形会扫过整条**，会把「行在动」误判成「条在动」（本轮第一次就是这么错的：77 px 假阳性）。案例数值：`band_diff = 0 / 3672 px`（5 个条各 3672 个纯条像素）且 `col_diff = 1653~2103 / 31680 px`。
  - **与「条挂行上」旧版同状态帧逐像素一致**：整条轮子带 `diff = 0 / 158400 px`（说明改层不改观感）。
- **附带修复（G-38 仍适用）**：中心行变了必须 `refreshListView()` 重刷可视行（否则正中行文字色停在旧行）；平台**没有单行重刷 API**（`ZKListView.h` 2.6.0/2.9.0 只有 `refreshListView()`）-> 只能全量重刷可视行（≤rows 行）。

## 4. 手感验收（真机，可机器断言）

| 判据 | 手法 | 案例实测 |
|---|---|---|
| 惯性存在 | 手势返回后**再采样**到状态变化（手指已抬起内容还在动） | post=(4,-19) -> final=(6,0) ✓ |
| 拖动中行未对齐 + 松手对齐整行 | dtdiag 轨迹里出现 `off != 0` 的中间帧、末帧 `off == 0` | 6 帧 off≠0（-32…-19），末帧 off=0 ✓ |
| **选中条静止 / 条跨越「停稳」也不动**（★本轮） | 同一次拖动里抓两帧 + 拖动帧 vs 停稳帧，对「纯条区」（文字到不了的侧带）逐像素比对 = **0**；同时列盒必须有差异 | band_diff=**0/3672 px**，col_diff=1653~2103/31680 px ✓ |
| **改层不改观感**（★本轮） | 与「条挂行上」旧版同状态帧逐像素比（整条轮子带） | diff=**0/158400 px**✓ |
| 只有正中行有带 | 「正中行盒内浅品牌色像素」> 2000 且「其他行」< 60 | bands 4842…5034 / 其他行 0 ✓ |
| 条不吞触摸（★本轮） | 从**条矩形内部**起手拖动 -> 列内容必须变 | col_chg=True ✓ |
| 选中 = 正中行文字色 | 正中行品牌蓝像素 > 40；上下相邻行无品牌蓝 | blue 159/66/93/105/91；邻居 0 ✓ |
| 相邻列不受影响 | 拖 A 列后，其余列正中行裁图 md5 **逐像素相同**| same=[True×4] ✓ |

## 5. 机读映射口径（源控件 → `target` / `level` + 验证入口）

滚轮族（含时间选择 / 时钟盘形态）在 `mcp_control_map.json` 里**一律**`target: listview` + `level: L2`，不再有 L5 例外：LVGL `lv_roller`（`wheel` / `滚轮` / `转盘`）/ Qt `QTimeEdit`·`QDateTimeEdit`（时间部分）/ Android `TimePicker`·`TimePickerDialog`（含**时钟盘**形态）/ Android `NumberPicker`·小程序 `picker-view`（`picker mode=time`）/ emWin `LISTWHEEL` → 全部 `listview` **L2**。

**验证入口（可复现）**：
```python
flythings_map_control("lv_roller")      # -> target=listview / level=L2
flythings_map_control("TimePicker")     # -> 同上（含时钟盘形态）
flythings_map_control("wheel")          # -> 同上（中文/英文别名都认）
```

**自绘包已移除**：`components/ui_v1/WheelPicker/` 已被 `listview` 组合方案取代（2026-09-19），`mcp_control_map.json` 里旧的 `targets.wheelpicker` 占位条目**同时删除**（5 条源条目已全部改指 `listview`，无悬空引用）；自绘轮曾用于的「逐像素 alpha 渐隐 / 行内非文字内容」已分别并入本文 §0 与行模板 `subItem`。

## 6. 时间选择 / 时钟盘（`TimePicker` 全族；★2026-09-19 需求方口径「TimePicker 通过 listview 这个实现对应」）

### 6.1 口径（先记住这条，别做反）

- 以下源控件**一律**`target: listview` + `level: L2`：Android `TimePicker`（**滚轮形态**+ **时钟盘 clock dial 形态**）/ `TimePickerDialog` / `NumberPicker`；Qt `QTimeEdit` / `QDateTimeEdit`（**时间部分**）；小程序 `picker mode=time`；emWin `LISTWHEEL`。
- **没有「时钟盘无对应能力」这种例外**（旧表述自 2026-09-19 起作废，`mcp_control_map.json` 表版本 3 已清理干净，无残留）。
- 一句话：**取值与联动语义由 `listview` 列承载；“圆的观感”是另一回事**（§6.3 如实写清）。
- **日期部分不在这里**：日历/日期选择仍是 `calendar` L4（已落地 `components/ui_v1/Calendar/`，见 `knowledge/../components/ui_v1/control-map.md` 2.15）。

### 6.2 怎么拼（时 / 分 / 秒）

| 形态 | 列数 | 每列内容 | 备注 |
|---|---|---|---|
| 时:分 | 2 | `00..23`（或 12h 制 `1..12` + AM/PM 列） | 最常见 |
| 时:分:秒 | 3 | 秒列 `00..59` | 秒不能省的场景 |
| 12h + 上下午 | 3 | 12h 数字列 ×2 + `AM/PM` 列 | 24h 制不需要 |

每一列都用 §0 的同一份片段（`cycleEnable:true` + 5 行可见 + 行高 36 + 静态条层）。**列间联动**（如 AM/PM 影响时列取值域、跨时区重算）在 **logic 侧聚合**：中心行回读定时器（§2）+ 必要时对相邻列 `refreshListView()`。

### 6.3 时钟盘（clock dial）形态：能做到哪 / 降级在哪

- **能做的（语义）**：把 12 个方位值按一列（一列 = 一个 `listview__N`）排布，选中项 = 中心行；回读、惯性、回弹、选中条层与 §1/§2/§3 完全一致；**logic 层与滚轮形态零差别**（同一份代码可复用）。
- **做不出（如实说）**：**圆周观感**——平台 listview 的行盒是**矩形等分行**，没有圆周布局/角度命中能力。
  - 观感路线 A（推荐，**零自绘**）：**12 方位按钮组**（`button__N` × 12 手工摆一圈）+ 中心 `textview` 显示当前时辰；点即选值，缺点是“转”的手感没了（但比拖手更准）。
  - 观感路线 B（要“真圆周拖动”）：**ZKPainter 自绘**+ 角度反算命中（宿主自己算 `atan2`）→ 属 **L3 自绘**，按 `knowledge/../components/ui_v1/gap-list.md` 编号立项 + 给真机证据，**不要临场造包**。
- **定性**：这是**观感降级说明**（圆周排列需 12 方位按钮或自绘、观感有损），**不是“能力缺失 / 不支持”**；选型建议统一按需求方口径走 listview 组合（L2），除非产品硬要求“钟面转圈”。

### 6.4 验证入口（可复现）

```python
flythings_map_control("TimePicker")        # -> target=listview / level=L2 / json 含 listview__
flythings_map_control("clock dial")       # -> 同上（英文别名）
flythings_map_control("时钟盘")            # -> 同上（中文别名）
flythings_map_control("NumberPicker")     # -> listview / L2（原 stepper，同族统一）
flythings_map_control("picker mode=time") # -> listview / L2（小程序）
```

## 7. 相关

- 字段/回调全集：`knowledge/uicontrols/listview-fields.md`（含 `item.text` 必须 `""`、`refreshListView()` 与滚动位置的关系）
- 手感字段取值：`knowledge/uicontrols/scroll-drag-interaction-spec.md`（`dragMaxDis` 的语义与 R1~R9；**循环选择器档 = 本文 §0 片段的取值源**）
- json 必写字段：`knowledge/uicontrols/json-field-mandatory.md`（行模板/装饰件的字段全集在此）
- 装饰件吞触摸（选中条为什么还要 `setTouchPass(true)`）：`knowledge/uicontrols/touch-events.md` §1
- 层叠顺序（装饰条为什么必须写在 listview 之前）：`knowledge/uicontrols/json-layer-rules.md`
- 跨框架映射（`TimePicker` 全族 → `listview`）：`knowledge/uicontrols/control-mapping-capability.md` / `knowledge/uicontrols/framework-control-mapping.md` / `knowledge/../components/ui_v1/control-map.md` 2.24
- 高频回调性能（`obtainListItemData` 里禁止耗时操作）：`knowledge/uicontrols/high-frequency-callback-perf.md`
- 缺口编号与级别：`knowledge/../components/ui_v1/gap-list.md` G-22（日期部分）/ G-23（滚轮·时间·时钟盘）/ G-37 / G-38
- 官方样例（3 行循环列表，点行选中）：`projects/SampleUI-New/ui/1024x600/detail.json` `ListviewTimePicker`
