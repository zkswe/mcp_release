# platforms.md —— Calendar 逐平台说明

> 口径：**没实测的一律写 `未验证`**。组件只用到 `easyui` 的 `ZKTextView + ZKButton + ZKBase::getPosition()`，
> 平台差异主要在 **① touch 事件怎么拿到绝对坐标**、**② textview 能不能画底色**。
>
> ⚠️ 文档里的设备地址是**通用示例**，不是真机 IP；真机清单在开发工作区（`references/kb/devices.md`），不进发布包。

## Z21（1024×600 横屏）

| 项 | 值 |
|---|---|
| 可用性 | ✅ **可用（已真机验收，2026-09-16）** |
| 实测 easyui | 设备 `/lib/libeasyui.so`（805,680 B，2024-07-10）；开发侧链接 registry **easyui 2.6.0** |
| **符号可用性（实测，关键）** | ✅ 导出：`ZKBase::{setPosition,getPosition,setTouchable,setTouchPass,setBackgroundColor,setBgStatusColor,setBackgroundBmp,setBackgroundPic,setAlpha,setLayerIndex}`、`ZKTextView::{setText,setTextColor,setTextStatusColor,setBold,setAlignment}`、`ZKWindow::{showWnd,hideWnd,isWndShow}`、`BitmapHelper::loadBitmapFromFile`<br>❌ **未导出**：`ZKBase::getParent()`、`ZKBase::getAbsolutePosition()`（registry 的 libeasyui.so **有**这两个符号，所以**编译链接都能过**，只有真机加载时才炸 → 黑屏、无日志） |
| 触摸事件怎么拿坐标 | activity 层 `onmainActivityTouchEvent(ev)`（框架在 onResume 注册了 `registerGlobalTouchListener`）拿到的是**屏幕绝对坐标**（实测：注入 `tap 805 28` → 代码里读到 `x=805 y=28`，点在按钮上也一样） |
| **textview 底色（实测，关键）** | ❌ json 的 `bgColorTab` 不画；❌ `setBackgroundColor()`（6 位色 / 0xAARRGGBB 都试过）不画；❌ `setBgStatusColor(NORMAL/SELECTED/INVALID, …)` 不画；✅ `setBackgroundBmp()`（运行时位图）画得出来；✅ `setBackgroundPic(路径)` 也画得出来<br>⚠️ 但 **`setBackgroundBmp` 在「翻月重设底色」时会崩应用**（无日志）：试过「同一格重复设同一个指针 → 崩」「同指针跨格共用 → 崩」「每格独占位图 → 也崩」三种写法，最稳的结论是 **本代 textview 的底色不适合做动态高亮**；静态一张（只在 attach 时设一次）可以用 |
| **textview 底色（复核更正，2026-09-16 晚）** | 上一条结论**只在 `div.modal` 弹窗内成立**：**普通容器里 textview 底色能画**（反例：案例顶栏下划线 `TvTabMark` 是 json `bgColorTab` 的 textview，真机像素 140x3 实心蓝 = 420 px）。差异与容器有关，**根因未定位**；本组件全在弹窗内，故仍走「文字色 + 加粗」 → **2026-09-16 晚：选中高亮已改走 `ZKPainter`（见下一条），不再靠 textview 底色。** |
| **选中高亮：已解决，改用 `ZKPainter`（2026-09-16 晚）** | ✅ **不再是降级**：`setHighlightPainter(painter__N)` 在**选中格位置**画实心高亮（填充色 `Style::selBg`，圆/方可选、内缩可配，圆带抗锯齿）。painter 只是**普通控件**，走的是「能画」的那条路（不依赖 textview 底色）。<br>⚠️ 三条接线铁律：① painter **必须与 42 格同父**（设备端不导出 `getParent()`，无父链可算）；② painter 必须**定义在 42 格之前**（json 后定义 = z 更高，反了会把日号数字整片盖住）；③ painter 不自动重绘 → 切月/选日后照旧 `refresh()`。<br>⚠️ painter 无 alpha：高亮块是**先铺 `Style::cellBg`（必须 == 真实底色）再按覆盖率混色**画出来的；`erase()` 会留不透明黑（别用）。 |
| 文字色 / 加粗 | ✅ `setTextColor()`、`setBold()` 正常（高亮的**文字**这一半靠这两个；**色块**那一半靠 painter） |
| painter 自绘 | ✅ 正常（`RadButton` / `Chart` / 本组件的 highlight block 都在用）：`setSourceColor` + `fillRect(l,t,w,h,radius)` 是可靠原语；**无 alpha**、**`erase()` 留不透明黑**、**不自动重绘** |
| modal 窗口里的绘制差异（附带发现） | `div.modal` 窗口**不画自己的底色**，里面**普通 window 的底色也不画**；但**按钮的底色会画**、textview 的**文字**会画。所以 example 里用一张铺满的「卡片按钮」当白底（`setTouchable(false)+setTouchPass(true)`，不抢事件） |
| 前置条件 | `/tmp` 可写（`/res` 是 squashfs 只读）；⚠️ `/data` 已满，别推文件到 `/data` |
| 已知限制 | ① fb 双缓冲（`virtualHeight=1200`）：抓屏必须按读到的 `pan` 取帧，否则比对的是黑屏/旧帧；② **【已勘正 2026-09-28】�回重复重启后触摸不响应 = 当时脚本用 `kill -9 zkgui` 的后果** —— 按框架口径（应用由类 init 服务托管，不能 kill）改成 `setprop ctl.restart zkswe` 后，**Z20 108 实测 10 轮重启：pid 每轮换新、触摸注入每轮都有响应（帧差 230400 px）**，不再需要重启板子（详见 `knowledge/devflow/device-deploy-budget.md` §5） |
| 真机验收命令 | 见 `example/README.md`（`fun build` → 推 `/tmp` → `touch tap …` → 抓屏 + `ui_diff.py`） |

## F133（1280×800，rotate 270/270）

| 项 | 值 |
|---|---|
| 可用性 | ⚠️ **未验证（仅源码同口径可编译）** |
| 依据 | 同代 `easyui 2.9.0` 的 `ZKTextView/ZKButton` 公开面与 2.6.0 一致；组件无平台宏 |
| 待实测 | ① `getParent/getAbsolutePosition` 是否导出（**上机前先 `readelf --dyn-syms /lib/libeasyui.so` 查**，别踩 Z21 那个坑）；② textview 底色是否同样画不出；③ 触摸事件坐标是否同为屏幕绝对 |
| 前置条件 | `package.properties` 写 `{"rotateScreen":270,"rotateTouch":270}`；SD 部署 `/mnt/extsd/{lib,ui}` |

## Z20 / T113 / V85X

| 平台 | 可用性 | 依据 | 上机前必查 |
|---|---|---|---|
| Z20 | ⚠️ **未验证** | registry `z20/easyui/2.6.0`、`3.0.0` 头文件面一致 | 同 F133 三条 |
| T113 | ⚠️ **未验证** | registry `t113emmc/easyui/2.9.0` 一致 | 同 F133 三条 |
| V85X | ✅ **可用（真机已验收 2026-10-03）** | registry `v85x/easyui/2.3.0`、`2.9.0` 一致；**V85X 实测（2026-10-03）**：`fun build` + `fun launch` 通过、launch 后 `onUI_show` 确认、抓屏有内容（证据 `example/evidence/v85x_20261003_full.png`）。口径：示例为 1024×600、面板 480×1600，验的是**组件可用性**，不是版式 | 同 F133 三条；V85X 内存/带宽紧，长按翻月之类别做 |

## 跨平台注意事项（平台通用）

1. **坐标系是「控件局部」**：`getPosition()` 返回控件在**父容器**里的矩形；触摸事件给的是**屏幕绝对**坐标
   → 必须让业务把「容器原点」告诉组件（`setContainer` / `setContainerOrigin`）。
2. **别用 `getParent()` / `getAbsolutePosition()` 往上走**：这代设备库导出不全（开头上机前先查符号），
   用了会「编译链接都过、运行时黑屏无日志」。
3. **组件不装触摸监听**：textview 没有点击回调；命中一律由业务反算（`cellAt/dayAt`）。
4. **改状态必须 `refresh()`**：没有任何自动重绘。
