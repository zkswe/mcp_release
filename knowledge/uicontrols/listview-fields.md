---
id: uicontrols-listview-fields
title: ListView 列表控件字段 + 回调语义（含 subitem 点击 id 确认）
category: uicontrols
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [0 SDK 校准, 可做更多]
evidence: []
---
# ListView 列表控件字段 + 回调语义（含 subitem 点击 id 确认）

> 检索导引：问「列表怎么做 / listview 字段 / 三回调一刷新 / 点击拿到的是行号还是 subitem id / 每行都常显 ListItem / 刷新不跟最新行」→ 本文；滚轮选择器见 `uicontrols/listview-wheel-picker.md`，封面卡顿见 `uicontrols/listview-image-cache.md`。
> 2026-09-07 git.com 全库学习 + basedemo/listViewDemo-New + f133 easyui 2.9.0 SDK 校准。
> ⚠️ 沛哥 2026-09-07 确认：新版 SDK **已无 subitem 数量 5 个限制**（老 SDK S_MAX_SUB_ITEM_COUNT=5 已移除，可做更多）。

## 核心铁律

1. **三回调 + 一刷新**（老工程命名 / fun 新工程（原 fuse）同构）：
   - `getListItemCount_XXX(const ZKListView*)` → 返回总行数
   - `obtainListItemData_XXX(pListView, pListItem, index)` → 填第 index 行内容（**禁止耗时代码**，滚动逐行调）
   - `onListItemClick_XXX(pListView, index, id)` → **id = 被点击 subitem 的控件 ID**（沛哥确认），用于区分同一行里点了标题/按钮/删除钮
   - 数据变更后 `mListPtr->refreshListView()`
2. **行内子项用 ID 取**：`pListItem->findSubItemByID(ID_MAIN_SubItemText)`；subitem 本质是 ZKButton，可 setText/setSelected/setBackgroundPic/setVisible。
3. **点击回调第三个参数是 subitem 的 id**（不是行号）：行号是 index；要区分行内不同可点区域就 switch(id)。
4. 删除行套路：数据容器 erase → 更新计数 → refreshListView（listViewDemo 实测）。
5. 资源路径用 `CONFIGMANAGER->getResFilePath("pic/xxx.jpg")` 拼（相对 resources）。
6. 另一种编程式用法：`setListAdapter(AbsListAdapter)` + `setItemClickListener`（NetDemo/New 风格），与命名回调二选一。
7. **`setSelection(idx)` 之后必须 `refreshListView()`**（沛哥 2026-09-10）：setSelection 只改选中态，
   不重新拉行数据/不重绘，漏刷新 = 界面上看不到变化（高亮/滚动位置不更新）。改数据（erase/新增）同理，改完一律 refresh。
8. **刷完要主动决定「停在哪一行」**（2026-09-16 实测，**日志/监控列表必踩**）：`refreshListView()` 只让数据重排重绘，
   **滚动位置不变**。日志/进度这类「只看最新」的列表不主动跳行 → 屏幕上永远是最早的旧行，
   看起来像"数据不更新"。顺序不能反：
   ```cpp
   p->setSelection(count - 1);   // 先跳到最后一行
   p->refreshListView();         // 再刷新（顺序反了可能不重绘）
   ```
   ⚠️ 数据浏览型列表（用户手动翻页）**不要**强制跟随，会打断阅读——只在「最新即有用」的列表上做。

## ⚠️ 两个高频坑（2026-09-16 实测：html2json 生成 + Z21 日志列表）

### 坑 1：`item.text` 默认 `"ListItem"` → 每一行常显一个 ListItem
- **现象**：列表每行末尾多一个英文 `ListItem`（跟数据无关、刷新不掉）。
- **原因**：行模板（`item`）自带默认文本；`html2json` 老版本照抄控件默认值，写死 `"text": "ListItem"`。
- **修法**：json 里 `item.text` 写 `""`；`html2json` 自 2026-09-16 起默认输出空串
  （MCP 源 + `tools/ui_tools/` 两份已同步 `sync_ui_tools.py`）。
- **手写 json 自检**：`grep '"text": "ListItem"' ui/*.json` 应为空。

### 坑 2：刷新后不跟最新行 → 一直显示旧数据
- **现象**：数据在涨，屏幕上却一直是几分钟前的行；误以为"刷新失效"。
- **原因**：`refreshListView()` 不改变滚动偏移（见核心铁律 #8）。
- **修法**：`setSelection(count-1)` → `refreshListView()`（先跳行再刷新）。
- **判据**：截图里可见行的**时间戳/序号必须递增且末行是最新**；若停在旧值 → 没做跟随。

## 封面图多 → 刷新/回页卡（2026-09-23）

> fill 里 `setBackgroundPic(path)` 会让框架**当场解这张图**（280×280 圆角封面真机 **26~65 ms/张**，
> 64×64 小图 3~4 ms），全落在 UI 线程；item 一重建（回页/换页/刷新/控件回收）就**再解一遍**。
> 完整口径（病症判据 / 机制 / 两件套修法 / 8 条踩坑 / 实测数字 / 验收怎么量）见
> **`listview-image-cache.md`**；可直接拷的代码在组件 **`components/imagecache/`**（`zk::ImageCache`）。
> 一句话修法：**①先降尺寸（取图 == 显示盒）②再上 ImageCache（按路径缓存已解码位图）**，
> 两件套缺一不可；真机回页重设同一批封面 315 ms → 1 ms。
> ⚠️ 硬约束：**缓存键 = 路径，路径必须唯一（含批次/版本）**——固定名封面换内容会命中旧图（串图）。

## JSON 字段表（ftu 实测校准）

| 字段 | 说明 |
|------|------|
| `caption`/`id` | 控件名/id |
| `rows`/`cols` | 网格行/列（1 列=普通列表） |
| `orientation` | 0 纵向（列表）/ 1 横向 |
| `rowSpacing`/`colSpacing` | 行列间距 |
| `edgeEffect` | 0 无 / 1 拖拽回弹 / 2 渐隐 |
| `dragMaxDis` | **越界拖拽上限（overscroll）**——行程由项数决定，跟它无关。要回弹手感填 50；无越界填 0；**禁止填列表高度**（详见 §dragMaxDis 取值） |
| `autoRollback` | 滑动停止自动回弹对齐 |
| `cycleEnable` | 循环列表 |
| `hasScrollbar` | 滚动条显示 |
| `item` | 行模板（内含各 subitem 定义）；**`item.text` 默认值必须写 `""`**（默认 `ListItem` 会每行常显，见「两个高频坑」） |

## dragMaxDis 取值（越界拖拽上限，2026-09-12 沛哥定规）

> `dragMaxDis` **不是**「列表能滚多远」，而是**手指越过内容边界后，内容还允许被继续拽出去的最大距离**。
> 填成列表高度 → 一次拖拽把整屏列表拽出去，松手才回弹 → **交互不合格**。
> 完整规范（含 edgeEffect/autoRollback 配合、分辨率换算、验收清单）：`scroll-drag-interaction-spec.md`。

| 场景 | edgeEffect | dragMaxDis | autoRollback |
|------|-----------|-----------|--------------|
| 数据浏览列表（不用回弹） | 0 | **0** | false |
| 菜单/设置列表、循环选择器 | 1 | **50** | true |
| 长数据列表 | 0 或 1 | **0 或 50** | false |

- **硬约束**：listview 的 `dragMaxDis` < 控件可视高（≥ 即不合格），基准 ≤ 一行高（50 @1024×600）。
- `0` = 关闭越界拖出（配 `edgeEffect:0`）；`edgeEffect:1 + dragMaxDis:0` 是自相矛盾的配法。
- 循环列表（`cycleEnable:true`）本身无边界，越界拖拽用基准 50，别开大。
- 分辨率换算：基准 50 @1024×600 ≈ 屏高 8%，其他分辨率 `round(scale×50)` 下限 24。

## 滚轮选择器 / 居中选中（2026-09-19）

> **完整口径**（字段配法 + 4 个真机坑 + 验收判据与数字）见 **`listview-wheel-picker.md`**，
> 本文不重复。本节点三个**只属 listview 字段/回调**的事实（真机实测，官方文档未收录）：

1. **引擎自己维护「当前项」选中态**：用户在列表上操作后，它把选中态打在**列表盒第 1 行**
   （= `getFirstVisibleItemIndex()`）上，**会盖掉 `obtainListItemData` 里的 `setSelected`**。
   -> 要自己做「正中行高亮」时，**别用引擎的态图**（`pic0/1/2` 留空、`color2/3` 置中色）；
   选中感由宿主自画（选中条层次与文字色口径见 `listview-wheel-picker.md` §3 坑 4）。
2. **行属性不会因为「中心行变了」而自动重刷**：引擎只在行「进入可视区」或 `refreshListView()` 时调
   `obtainListItemData`。中心行一变就要 `refreshListView()`，否则会出现「滚完停住、高亮停在错行」。
3. **`setSelection(i)` 把第 i 项摆到列表盒第 1 行（不是正中行），并且是带动画的**（调用后 `fi` 会连续跑好几帧）
   -> 程序化定位（复位/取消/步进）不要用「调 setSelection + 立即回读 + 再调」的迭代校正（会越推越远），
   用**数据侧平移** + `refreshListView()`（写法见 `listview-wheel-picker.md` §1）。

其余**属于滚轮配法**的内容（中心行回读公式、选中条挂静态层、字段取值档、行数据数组取 2n、
验收判据与像素数字）统一收在 **`listview-wheel-picker.md`**（§0~§4），本文不再重复。

## 代码示例（listViewDemo 实测）

```cpp
static int getListItemCount_ListView1(const ZKListView *p) {
    return vData.size();
}
static void obtainListItemData_ListView1(ZKListView *p, ZKListView::ZKListItem *item, int index) {
    ZKListView::ZKListSubItem* sub = item->findSubItemByID(ID_MAIN_SubItemText);
    sub->setText(vData[index].mainText);
    ZKListView::ZKListSubItem* btn = item->findSubItemByID(ID_MAIN_SubSetlectBtn);
    btn->setSelected(vData[index].state);
    // 行背景：CONFIGMANAGER->getResFilePath(...) 拼路径 setBackgroundPic
}
static void onListItemClick_ListView1(ZKListView *p, int index, int id) {
    if (id == ID_MAIN_SubItemText) { /* 点标题 */ }
    else if (id == ID_MAIN_SubSetlectBtn) { /* 点选择钮 */ }
    else if (id == ID_MAIN_SubDeleteBtn) { vData.erase(...); refreshListView(); }
}

// 选中某行：setSelection 后必须 refreshListView（否则界面不更新）
p->setSelection(2);
p->refreshListView();
```

## 样例代码
listViewDemo-New（增删改查完整 demo：标题+选择钮+删除钮三 subitem）；NetDemo-New（setListAdapter 编程式）；git.com 各产品列表页（38+ 工程在用）。
封面列表（带图片缓存）真机案例：**`projects/iOSStyle-F133`**（推荐/榜单/搜索结果三个封面列表，
口径 `listview-image-cache.md` + 组件 `components/imagecache/`）。
滚轮选择器：`projects/SampleUI-New` 的 `ListviewTimePicker`（3 行循环列表 + 点行选中；口径 `listview-wheel-picker.md`）+ 案例
`projects/translate/tdesign-miniprogram`（5 列 176×180、可见 5 行、正中行 = 选中行 + **选中条挂静态背景层**，
真机 `s4c_*` 30 项验收全 PASS）。