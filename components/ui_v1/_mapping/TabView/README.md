# components/ui_v1/_mapping/TabView —— 页签页容器 `zk::ui_v1::TabView`

> ⚠️ **这不是自定义控件包**：此类**有平台对应控件（`pagewindow` / ZKPageWindow）**，按 ui_v1 口径
> （2026-09-16：有对应控件的一律走「映射能力」）**只作映射参考**—— 提供「映射索引里的 json 片段 +
> 手感参数 + 高亮同步」这套已验证接线，**不算平台缺能力**，因此从 `ui_v1/<源控件名>/` 移到 `ui_v1/_mapping/`。
> 机读映射见 `mcp_control_map.json`（`lvgl.lv_tabview` / `android.ViewPager|TabLayout` /
> `miniprogram.swiper+tab` / `qt.QTabWidget` 都指向 pagewindow），查法：
> MCP op `flythings_map_control(query="lv_tabview")`。
>
> **替代哪个源控件**：LVGL `lv_tabview` ｜ Android `TabLayout + ViewPager` ｜ 微信小程序 `swiper + tab` ｜ Qt `QTabWidget`
> **建立**：2026-09-16（经需求方纠正口径：不做映射表，做成**能用的自定义控件包**，一个源控件一个目录）
> **迁移**：2026-09-16（v0.27.73-open，需求方再修正：**有对应控件 → 映射项，不进 ui_v1 自定义控件包**）
> **版本**：0.1.0 ｜ **状态**：映射参考（含 Z21 真机证据）｜ **级别**：L1+L2（映射表 `control-map.md` §1.2/§1.3）
> **缺口**：`gap-list.md` G-01（历史写法用「多个整屏 window 显隐」——**丢手势**，本包是修正版）

---

## 1. 我们怎么做（不是新造控件，是把平台已有能力收成组件）

平台**已经有**滑动切页容器 `ZKPageWindow`（json 里的 `pagewindow__N`）：自带「水平拖动 = 翻页」手势、
页间位移动画、`IPageChangeListener` 回调。所以这一项**不重画轮子**，只做三件事（下面是**映射接线参考**，
既有控件 + 这套接线就能覆盖源的 tabview，所以它归「映射项」而不是「平台缺能力的自定义控件」）：

1. **双向绑定**：把「页签按钮高亮 + 下划线标记」与 pagewindow 的当前页绑起来。
   - 滑动 → pagewindow 发 `onPageChange` → 组件回调 `onPageChanged(page)` → 同步页签视觉；
   - 点页签 → `TabView::select(i)` → `turnToNextPage/turnToPrevPage` → 同一回调 → 同一同步函数。
   - **页签高亮的唯一真源 = `getCurrentPage()`**：两条路径都只认它 → 幂等，不会两条路径互相对砍。
2. **手感参数固化**：`dragMaxDis / edgeEffect / rollSpeed / orientation` 平台**只能在 json 里设**
   （`ZKPageWindow` 无运行时 setter）→ 组件提供默认值 `200 / 1 / 60 / 0` + `gestureHtmlAttrs()` 片段
   + `checkGesture()` 反向自检（json 与默认值不一致时把人话差异报出来）。
3. **一处回调**：`onPageChanged(page, user)`，**只在页真的变了时**触发（同一页不重复回调，避免业务重复重绘）。

## 2. 怎么用（15 行可跑）

```cpp
#include "zk/zk_tabview.h"

static zk::ui_v1::TabView s_tab;
static ZKButton *s_tabs[2] = { mBtnTab0Ptr, mBtnTab1Ptr };   // 顺序 = 页序

static void onPageChanged(int page, void *user) {
    (void)user;
    // 切页后自绘图/列表要自己刷（painter、listview 都不自动重绘）
}

static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif
    s_tab.setOnPageChanged(onPageChanged, NULL);
    zk::ui_v1::TabView::Result r = s_tab.attach(mPwPagesPtr, s_tabs, 2, mTvTabMarkPtr);
    if (!r.ok()) { /* r.msg 是人话，直接上屏/打日志 */ }
    s_tab.select(0);                    // 首帧高亮归位（幂等）
}

static bool onButtonClick_BtnTab1(ZKButton *p) { (void)p; s_tab.select(1); return false; }

static void onUI_quit() { s_tab.detach(); }   // 摘监听，避免回调打到已销毁控件
```

**布局侧（HTML 原型 → json）**：

```html
<div class="btn" data-x="20" data-y="24" data-w="180" data-h="36" data-caption="BtnTab0">Page 0</div>
<div class="btn" data-x="212" data-y="24" data-w="180" data-h="36" data-caption="BtnTab1">Page 1</div>
<div class="text" data-x="20" data-y="60" data-w="180" data-h="4" data-bg="#2196F3" data-caption="TvTabMark"></div>

<div class="pagewindow" data-x="0" data-y="64" data-w="1024" data-h="536" data-caption="PwPages"
     data-drag-max="200" data-edge-effect="1" data-roll-speed="60" data-orientation="0">
  <div class="window" data-x="0" data-y="0" data-w="1024" data-h="536" data-caption="Page0">...</div>
  <div class="window" data-x="0" data-y="0" data-w="1024" data-h="536" data-caption="Page1">...</div>
</div>
```

## 3. API

| 成员 | 说明 |
|---|---|
| `Result attach(ZKPageWindow *pages, ZKButton *const *tabs, int tabCount, ZKTextView *marker = 0)` | 绑定页容器 + 页签按钮数组 + 下划线标记。**必须在 `onUI_init` 里调**（控件已创建）。`pages` 空 / 页数 0 → 返回非 0 + 人话 `msg` |
| `void detach()` | 解绑并摘监听（`onUI_quit` 里调） |
| `Result select(int page)` | 编程切页（点页签用）。越界返回非 0；内部只用 `getCurrentPage()` 口径 + 显式 `sync()`，幂等 |
| `int current() const` | 当前页（未绑定 = -1） |
| `int pageCount() const` | 页数（= pagewindow 的 `getPageSize()`） |
| `void sync()` | 强制同步一次页签视觉（幂等；回调缺失时的兜底） |
| `void setOnPageChanged(PageChangedFn fn, void *user = 0)` | 页切换回调（滑动 / 点页签 / select 同源） |
| `void setStyle(const Style &)` | 选中/未选中文字色、下划线色/高/内缩 |
| `static const Gesture &defaultGesture()` | 默认手感：`{dragMaxDis=200, edgeEffect=1, rollSpeed=60, orientation=0}` |
| `static std::string gestureHtmlAttrs()` | 生成 `data-drag-max="200" data-edge-effect="1" data-roll-speed="60" data-orientation="0"` |
| `static Result checkGesture(const Gesture &actual)` | 把 json 里的实际 4 个值传进来，与默认值不一致时返回非 0 并列出差异 |
| `struct Result { int code; std::string msg; bool ok(); }` | 统一结果类型（`components/README.md` 规范 2：`msg` 说人话，不静默失败） |

`Style` 默认值：`activeColor=0x2196F3`（选中文字 + 下划线）、`idleColor=0x616161`、
`markHeight=0`（自动 = 页签高 / 13，最小 2px）、`markInset=0`（与页签同宽）。

## 4. 依赖与线程模型

- **依赖包（Z21/实测）**：`easyui`（`ZKPageWindow` / `ZKButton` / `ZKTextView`）+ 工程常规 `log / zkhardware / zknet / base-utility`。
见 `Manifest.xml`。
- **线程模型**：**全部在 UI 线程**。`onPageChange` 由平台在 UI 线程回调；组件内无定时器、无锁、无阻塞调用。
业务回调里**不要**做长耗时操作（会卡翻页动画）。
- **内存**：组件自身只保存 5 个指针 + 少量状态，**无动态分配**（唯一 `new` 是 1 个监听桥对象，`attach` 时创建一次）。

## 5. 限制（写清楚，别让人猜）

1. **手感参数改不了运行时**：`dragMaxDis / edgeEffect / rollSpeed / orientation` 是 `ZKPageWindow` 的**创建期属性**，
平台只从 json 读。要改 → 改原型 HTML 的 `data-*` → `html2json` → `fui pack` → 重新部署。
2. **下划线标记必须与页签按钮同父**：组件用「页签按钮的 `getPosition()`（相对父）± 高度」反算标记矩形，
两个控件不在同一父容器时坐标基准不同 → 标记会错位。这条是平台 `getPosition()` 只给父相对坐标导致的。
3. **不接管触摸**：组件不拦截任何事件（不做手势判定），所以**页内控件的点击/拖动照常工作**；
代价是滑块这类「水平拖动」控件在 pagewindow 内会被父容器抢走 MOVE（平台固有手势冲突，见 `gap-list.md`，
本包不处理，需要时业务自行接管 `onmainActivityTouchEvent`）。
4. **页签个数 != 页数**时组件会返回 code=-3 并照常同步（不崩、不错位，但页签少的那些页没有高亮）。

## 6. 验收记录（Z21 1024×600 真机，2026-09-16）

| 验收项 | 命令 | 结论 | 证据 |
|---|---|---|---|
| 编译 | `fsc build -p Z21` | ✅ 无警告无错误 | — |
| 初始帧 | 部署后抓屏 | ✅ 「第 0 页」+ Page 0 文字变蓝 + 下划线 x=20–199 | `example/evidence/01_page0_initial.png` |
| **滑动切页**| `/tmp/touch swipe 900 300 150 300` | ✅ 切到「第 1 页」，状态行 `onPageChanged: page=1 (当前页=1 OK)`；Page 1 变蓝、下划线 x=212–391 | `02_swipe_page0_to_page1.png` |
| **点页签切页**| `/tmp/touch tap 110 42`（点 Page 0） | ✅ 回到「第 0 页」，`page=0`，下划线回到 x=20–199 | `03_tap_tab0_back_to_page0.png` |
| 页内控件可用 | `tap 130 248` ×3 | ✅ 计数 0 → 3（手势没吃掉点击） | `04_page0_button_tapped_3x.png` |

> 像素判据（脚本可复现）：下划线区 `y=58..59` 的蓝色（`#2196F3`）x 范围；
> 页签文字区 `y=24..58` 内蓝/灰像素计数（`Page0` 蓝=100/灰=0 表示左页签激活，反之亦然）。

## 7. 排错

| 现象 | 原因 | 处置 |
|---|---|---|
| 页签高亮不动 | `attach` 的 `tabs` 为空 / 顺序与页序不一致（`attach` 会返回 -3） | 检查 `src/logic/mainLogic.cc` 里的按钮数组顺序 |
| 下划线跑到左上角 | 标记与页签按钮不同父 | 把 `TvTabMark` 放到页签按钮所在的同一个 `window` 里 |
| 滑动翻不了页 | 手势被页内可拖动控件（滑块/滚动列表）接管；或 `data-drag-max` 太大 | 见「限制 3」；或把 `data-drag-max` 调小 |
| 翻页后自绘图不更新 | painter/列表不自动重绘 | 在 `onPageChanged` 里显式 `refresh()` |

## 8. 相关文件

- 目录规范（四件套）：`components/README.md`
- 映射口径：`ui_v1/control-map.md` §1.2/§1.3、`ui_v1/logic-map.md`、`ui_v1/gap-list.md` G-01
- **机读映射（推荐入口）**：`mcp_control_map.json` + op `flythings_map_control(query="lv_tabview")`
- 与本包的对应条目：`lvgl.lv_tabview`、`android.ViewPager`、`android.TabLayout`、`miniprogram.swiper+tab`、`qt.QTabWidget`、`qt.QTabBar`、`qt.QStackedWidget`、`mfc.CTabCtrl`、`mfc.CPropertySheet`
- 文案口径：`knowledge/uicontrols/control-mapping-capability.md`
- 提炼来源（只读，未改动）：`projects/translate/lvgl-widgets/z21/src/logic/mainLogic.cc`
- 状态表：`ui_v1/components.md`（已实现 / 映射项 / 计划 三段）
