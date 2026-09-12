# ListView 列表控件字段 + 回调语义（含 subitem 点击 id 确认）

> 2026-09-07 git.com 全库学习 + basedemo/listViewDemo-New + f133 easyui 2.9.0 SDK 校准。
> ⚠️ 沛哥 2026-09-07 确认：新版 SDK **已无 subitem 数量 5 个限制**（老 SDK S_MAX_SUB_ITEM_COUNT=5 已移除，可做更多）。

## 核心铁律

1. **三回调 + 一刷新**（老工程命名 / fuse 同构）：
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
| `item` | 行模板（内含各 subitem 定义） |

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
