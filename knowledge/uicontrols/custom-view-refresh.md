# 自定义 view / 自绘帧的「刷新口径」（GameView 那一套）

> 2026-09-22 钟工定规：「open mcp 优化指的是针对**自定义 view，类似 gameview 这个部分的刷新**的问题」
> → 本文是这类刷新的**唯一权威口径**，每条都有工程出处（可 grep 核对）。
> 检索词：自定义控件刷新 / 自定义 view 刷新 / 自绘刷新 / 帧刷新 / 逐帧刷新 / 自绘帧 / 位图刷新 /
> 视频帧控件 / GIF 控件 / 地图控件 / 游戏视图 / GameView / gameview / setInvalid / isInvalid /
> invalidate / 脏区 / getAbsolutePosition / setBackgroundBmp 不刷新 / 只刷一块 / 局部刷新 /
> 部分区域不刷新 / 半屏不刷新 / 右下一块在动 / 3点到6点方向在动 / 每帧刷新 / 12fps 1fps。

## 0. 一句话口径

自定义 view 的每帧刷新 = **交替翻转控件自身的 invalid 状态**：

```cpp
ctrl->setInvalid(!ctrl->isInvalid());     // ✅ 平台惯例（gameview / GIF / 帧动画 / 地图 / 位图渲染 全都这么写）
```

**不要**用 `invalidate(&getAbsolutePosition())` 传绝对矩形去"脏化自己"：那个矩形是**控件本地坐标系**语义，
传页面绝对坐标会被裁成"右下角一块"，导致屏上只有那块在动（2026-09-22 真机实测，见 §2）。
**非必要也不要碰 `getAbsolutePosition()`**（钟工 2026-09-22 12:28）。

## 1. 四种"看着像重绘"的写法，语义完全不同

| 写法 | 真实语义 | 该不该用 |
|---|---|---|
| `setInvalid(true)` | **把控件置为无效/禁用**（`ZK_CONTROL_STATUS_INVALID`）→ **会吃掉触摸**（可交互控件变点不动） | ❌ 除"真禁用"外不要用 |
| **`setInvalid(!isInvalid())`** | 状态**交替变更** → 框架**按控件为单位重画一次** | ✅ 自定义 view 每帧刷新的惯例 |
| `invalidate()` / `invalidate(&rect)` | 正式"重绘"API；**带脏区版本在旧设备可能未导出**（undefined symbol → 整屏黑）；`rect` 是**控件本地坐标系** | ⚠️ 慎用；传矩形极易只刷一块（§2） |
| `setText` / `setBackgroundPic` / `setProgress` … | 内容变更，引擎本就会重画该控件 | ✅ 普通控件改内容**不需要**手动刷 |

> 注意区分：`setInvalid(true)` 是"禁用"，`setInvalid(!isInvalid())` 是"刷新"——**别因为前者危险就把后者也禁掉**
> （真实工程里后者是刷帧主力，见 §3）。

## 2. 真机实测：为什么 `invalidate(绝对矩形)` 会让屏幕「只刷一块」

场景：`projects/iOSStyle-F133` 播放页黑胶旋转（320×320 自绘控件，每帧改位图像素）。
现象：圆盘上只有**右下角一块**按 12fps 刷新，其余区域 ~1fps（用户原话「3~6 点方向每秒 12fps，剩下的 1fps」）。

判据（**无参考、可复用**）：源图**半径 100 处放四个纯色方块**（并且先不裁圆），暂停后**静态**走 20° 再截图 ——
理论位移 = `2 × r × sin(10°) = 34.7 px`；某色块**位移 0** = 那块**压根没被重画**。

| 刷新的矩形口径 | 色块位移（20°） | 判定 |
|---|---|---|
| `getAbsolutePosition()` = (100,166,320×320)（原口径） | **0 px** | ❌ 只剩本地 (100,166)-(320,320) 那块被刷 |
| `NULL` | 0 px | ❌ 等价"用控件自己的矩形" |
| 面板系坐标（按 rotateScreen=270 换算） | 0 px | ❌ |
| 控件矩形 + 父容器偏移 (184,316) | 0 px | ❌ |
| 整页 (0,0,screenW,screenH) | 33~35 px | ✅ |
| 本地矩形 (0,0,w,h) | 33~35 px | ✅ |
| **`setInvalid(!isInvalid())` 翻转（gameview 口径）** | **35 px** | ✅ **推荐** |

**结论**：`invalidate(rect)` 的 rect 按**控件本地坐标**理解并裁到控件内 —— 传绝对矩形 = 只脏化"从 (100,166) 到右下角"那块。
**要整块重画就别传坐标**：用 `setInvalid(!isInvalid())`（或传本地 `(0,0,w,h)`）。

## 3. 工程出处（生产代码，可直接核对）

| 场景 | 出处 | 关键行 |
|---|---|---|
| 游戏帧视图 | `projects/LearningProject/Game640480_Retro/jni/game/GameView.cpp` | 120 `_this->setInvalid(!_this->isInvalid());` |
| 游戏帧视图（内部版） | `gitcom/AppGroup/Game_Retro/jni/game/GameView.cpp` | 159 同 |
| GIF 播放控件 | `.../Game640480_Retro/jni/game/CGifPlayer.cpp:196`、`HaishiM9/src/gif/CGifPlayer.cpp:177`、`gitcom/AppGroup/oven_public*/src/gif/CGifPlayer.cpp:175` | 同款 |
| 仪表自绘动画 | `projects/LearningProject/DashBoard_T113/BMW/jni/ui/ImageAnimView.cpp` | 437 `setInvalid(!isInvalid());` |
| 地图自绘 | `projects/FlyMapDemo/src/logic/mainLogic.cc` | 218 |
| WebView 容器 | `projects/WebViewDemo/src/logic/mainLogic.cc` | 88 |
| 掌机平台显示层 | `projects/V851s/PocketGame/src/platform/PgDisplay.cpp:77`（头注释见 `PgDisplay.h:7`：「每帧 `setInvalid(!isInvalid())` 触发刷新（控件→屏幕走硬件加速）」） | 77 |
| 反面（2026-09-22 修掉） | `projects/iOSStyle-F133/src/core/VinylSpin.cpp`（原 `invalidate(&getAbsolutePosition())`） | 见 §2 |

## 4. 正确写法（自定义 view 模板）

```cpp
// ① 位图只交一次（所有权归框架）；之后每帧改像素 + 翻转 invalid
ctrl->setBackgroundBmp(bmp);                       // 只调一次
/* ... 每帧（UI 线程或定时器） ... */
memcpy(ctrlBmp->data, frame, w * h * 4);           // 或后台算好整帧再 memcpy
ctrl->setInvalid(!ctrl->isInvalid());              // ✅ 整块重画
```

- **刷新时机**：页面定时器（`REGISTER_ACTIVITY_TIMER_TAB`）或 UI 线程里做；跨线程直接调控件接口是允许的
  （见 `cross-thread-ui-rule.md`），但"重活"仍要放后台。
- **省 CPU 的顺序**：① **降帧率**（最有效、线性，例如 12fps→8fps 观感差别不大）② 缩小真正要改的区域
  （自绘时用 `Region` 脏区 + `onDraw`，见 `devflow/custom-widget.md` §6）③ 别每帧 `memset` 整块/整页。
- **别每帧 `setBackgroundBmp(new bmp)`**：那会每帧新建位图（分配抖动、框架反复释放）。
  正确形态是"只交一次 + 原地改像素 + `setInvalid` 翻转"。

## 5. 反例（AI 常写错）

| 反面写法 | 后果 |
|---|---|
| `invalidate(&getAbsolutePosition())` 刷自定义 view | 屏幕**只刷右下角一块**（§2 实测：位移 0px vs 35px） |
| `setInvalid(true)` 当"强制重绘" | 控件**被禁用 → 点不动**（`touch-events.md` §6 案例：13 个导航键全废、整屏无响应） |
| 每帧 `setBackgroundBmp(new bmp)` | 每帧新建位图 → 分配抖动 / 内存涨 |
| 每帧 `memset` 整幅目标缓冲 | 白烧 CPU（实测 320×320 去掉 memset 只省 0.4ms，但更大尺寸/整页就别做） |
| 用 `setText("")`/改内容去"顺手刷新"自定义 view | 语义错位，拿不准时按本文件 §0 的写法来 |

## 6. 相关文档

- 触摸/禁用语义与踩坑（`setInvalid(true)` 的现场）：`uicontrols/touch-events.md` §6
- 自定义控件整体做法（BaseView / onDraw / 适配器 / 脏区）：`devflow/custom-widget.md`
- 跨线程直接操作控件：`uicontrols/cross-thread-ui-rule.md`
- 抓帧与"别拿 setInvalid 当重绘"的误判记录：`devflow/device-screenshot.md` §3.3-1
