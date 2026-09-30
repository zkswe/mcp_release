---
id: uicontrols-listview-image-cache
title: listview 封面刷新卡顿：每次都重解码 → 两件套（尺寸 == 显示盒 + ImageCache）
category: uicontrols
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [F133]
tags: [检索命中条件, 列表封面卡, 回页慢 两类问法都命中本文, 列表刷新卡, 回页卡, 切页慢, 滚动卡, 拖动卡, 封面加载慢, 图片多就卡, 进列表卡一下, 返回上一层卡住, listview 卡顿, 每次刷新都重新解码, 同一张图反复加载, 大图列表卡]
evidence: []
---
# listview 封面刷新卡顿：每次都重解码 → 两件套（尺寸 == 显示盒 + ImageCache）

> 检索导引：问「列表封面卡·回页慢 / 同一张图反复解码 / 要不要上 ImageCache / 取图尺寸和显示盒不一致 / 缓存命中与耗时怎么量」→ 本文（两件套修法）；英文命中词见上方「检索词（同义/别名）」。
> **检索命中条件（列表封面卡 / 回页慢 两类问法都命中本文）**：
> **① 病症族**：列表卡 / 列表刷新卡 / 回页卡 / 切页慢 / 滚动卡 / 拖动卡 / 封面加载慢 / 图片多就卡 /
> 进列表卡一下 / 返回上一层卡住 / listview 卡顿 / setBackgroundPic 慢 / 每次刷新都重新解码 /
> 同一张图反复加载 / 大图列表卡 / 封面列表性能；
> **② 解法族**：图片缓存 / 位图缓存 / 解码缓存 / ImageCache / imageCache / 封面缓存 / 列表封面缓存 /
> LRU 缓存 / 图片预加载 / 减少重复解码 / 缓存已解码位图 / 列表图片优化 / 取图尺寸 / 图比盒子大 / 降尺寸。
> **检索词（同义/别名，降级 BM25 与人工核对都用）**：ImageCache、imageCache、BitmapHelper、
> loadBitmapFromFile、unloadBitmap、setBackgroundPic、coverCache、缓存命中、hits/loads、CACHE_SIZE、
> 权重 LRU、引用计数、releaseAll、drop_caches、串图、批次命名。
> **2026-09-23 立**（钟工口径：把 HaishiM9 的「列表图片 ImageCache 方法」正式入库 open 版 MCP）。
> **相关**：字段与回调全集 `listview-fields.md`；高频回调里别做重活 `high-frequency-callback-perf.md`；
> 滑动/惯性字段 `scroll-drag-interaction-spec.md`；组件 **`components/imagecache/`**（可直接拷的代码）；
> 平台实测与未验证项 `components/imagecache/platforms.md`；原始实测报告 `temp/music_ui/REPORT.md`。
> **一句话**：`setBackgroundPic(path)` 会让框架**当场解这张图**（280×280 圆角封面真机 26~65 ms/张，落在 UI 线程），
> 列表 item 一重建（回页/换页/刷新/控件回收）就**再解一遍**；修法是**两件套、缺一不可**：
> ①**先降尺寸**（出图/取图严格 == 显示盒，别让引擎去缩大图）→ ②**再上 ImageCache**（按路径缓存**已解码位图**，命中不再解码）。
> 真机（F133）：回页重设同一批封面 **315 ms → 1 ms（−99.7%）**，回页合计 **524 → 206 ms**。

## 0. 什么时候该上，什么时候不该上

| 该上 | 不该上 |
|---|---|
| 列表 fill 里**每次都会重设**的封面（`obtainListItemData_*` 里 `setBackgroundPic`） | 静态一次性图（进页面设一次就不动的背景/图标）——装了也要花一次装载 + 占一个槽 |
| 频繁切页/回页、item 会被重建重建再重建的列表 | **只有文字行**的列表（没有封面控件，没图可缓存，别硬接） |
| 一次刷新里同一批路径会被重设多遍的列表 | 需要**首解**变快的场景（缓存不加速首解，只能在后台预热，见 §6 坑 7） |

## 1. 病症与判据（先量，再改）

**现象**：列表页刷新/滚动/回页「卡一下」；列表越多、图越大越明显。

**判据 1 —— 单张解码成本**（是不是这个病）：在 `setBackgroundPic()` 前后加临时计时埋点，量 UI 线程耗时：

| 图 | 尺寸 | 单张 `setBackgroundPic`（F133 真机） |
|---|---|---|
| 推荐列表圆角封面 | 280×280 | **26~65 ms** |
| 榜单 / 搜索列表小图 | 64×64 | **3~4 ms** |

**判据 2 —— 是不是「同批路径被反复解」**（值不值得缓存）：回页/刷新时数一数同一批路径被 `setBackgroundPic` 几次。
实测本工程：首屏 8 次 ≈ 211 ms；**回页重设同一批 8 次 ≈ 315 ms**（这 315 里 8 次都是**已经在内存里的图**）。

**判据 3 —— 拖动本身会不会重解**：本工程实测**拖动 0 条解码**（工程侧已有 mark 表挡住）——
所以别默认「滚动一下就在重解」；真正淌血的是**「回页重设」**这条路。先量清是哪条路，再动手。

## 2. 机制（为什么「每次刷新都要解」）

1. `setBackgroundPic(path)` 传的是**路径**，框架拿到路径**当场解码**（PNG → 位图），这次解码全在 UI 线程。
2. item 被重建（回页 / 换页 / `refreshListView()` / 控件回收后再摆上来）时，那份**局部**的解码结果没了，
   再调一次 `setBackgroundPic` 就**再解一遍**。
3. 但框架侧还有一条更耐用的路：`BitmapHelper::loadBitmapFromFile(bmp, path)` 会把解好的位图
   登记进**框架的资源表**并把这份持有；**只要我们不 unload，框架再遇到同路径就直接复用，不再解一遍**。
4. 于是「缓存」其实只做三件事：**持有**（提前把它登记进资源表）、**退役**（不再需要时 unload）、
   **淘汰策略**（别让一次性扫过的图把常看的挤掉 → 权重 LRU）。

> ⚠️ 关键推论：**缓存键就是路径**。同一个文件名换内容 → 命中旧图（上屏还是上一批图 = 串图）。见 §5 坑 1。

## 3. 修法第一件套：尺寸 == 显示盒（先做这个）

出图/取图尺寸**严格等于**控件盒（json 里的 `position.width/height`）。让引擎去缩一张大图，
既费解码时间、又费内存峰值 —— 缓存也救不了它（首解照样慢、位图照样占）。

真机实例（iOSStyle-F133，逐列表核对）：

| 列表 | 显示盒（json） | 取图尺寸（代码） | 结论 |
|---|---|---|---|
| 推荐 `ListRecommend` | `SubPlCover` 280×280 | `kRecCoverSize=280` → `?size=280`，圆角合成也按 280 | 相等，无需降 |
| 榜单 `ListTop` | `SubTopCover` 64×64 | `kTopCoverSize=64` | 相等 |
| 搜索结果 `ListResult` | `SubResCover` 64×64 | 固定 `?size=64` | 相等 |
| 我的 `ListFav/ListRecent` | **没有封面控件** | fill 里没有 `setBackgroundPic` | 无图可缓存（要加封面 = 改布局） |

做法：① 列表封面**取图接口的 size 参数**与控件盒对齐（网络图就带 `?size=`，本地图就用出图脚本按盒尺寸出）；
② 圆角/裁剪合成也按盒尺寸做，不要「先出大图再缩」。相关：图与盒的一般规则见 `ui-asset-rules.md`。

## 4. 修法第二件套：上 ImageCache

### 4.1 用现成组件（推荐）

`components/imagecache/`（`zk::ImageCache`，源码型，核心零依赖）：按路径缓存已解码位图，
权重 LRU + 引用计数 + 锁 + 容量参数 + 诊断读数（`hits()/loads()` 就是验收要的「命中/解码次数」）。
接线三步（完整样板见 `components/imagecache/example/flythings_wiring.cc`）：

```cpp
/* ① 配一次（幂等）：装载/释放走回调（FlyThings 上就是 BitmapHelper） */
zk::ImageCache::Config cfg;
cfg.load = myLoad; cfg.free = myFree;      // myLoad 里 BitmapHelper::loadBitmapFromFile
cfg.capacity = 128;                        // 内存换速度：按板子内存算账
zk::ImageCache::instance().configure(cfg);

/* ② 页面：onUI_init -> acquire()　onUI_quit -> release()（配对；引用计数，最后一个才真清） */
zk::ImageCache::instance().acquire();

/* ③ 列表 fill：setBackgroundPic(path) 之后紧跟一句（就这一句） */
subCover->setBackgroundPic(p.c_str());
zk::ImageCache::instance().cache(p.c_str());
```

### 4.2 手抄（上游口径，不用组件时）

与组件同一套语义（下文 §5 的坑同样适用）：`缓存命中 → 权重++，不解码`；
`未命中的已占用槽一律权重--`；`腾位置时空槽优先、否则权重最小的踢掉，再装载 weight=1`。

## 5. 坑（硬约束，全是真机踩出来的）

1. ⚠️ **固定文件名的封面被 pin 住会串图**：搜索结果封面原来用固定名（`cm_cov_sg<i>.png` 一类），
   进缓存后新一批**复用了旧路径** → 上屏是上一批的图（真机复现：搜「周杰伦」再搜「陈奕迅」，显示还是周杰伦的封面）。
   **修法：路径带批号/版本号**（`cm_cov_sg<批号>_<序号>.png`，开新一批时删上一批文件）。
   **硬约束：缓存键 = 路径，路径必须唯一（含批次/版本）。** 工程里本来就有「代后缀」的封面（`cm_riv_rec0_..._<N>.png`）不受影响。
2. ⚠️ **不要**照抄 HaishiM9 `releaseAll()` 末尾的 `system("echo 3 > /proc/sys/vm/drop_caches")`：
   全局副作用（把整个页缓存倒掉，后续**所有**文件读反而更慢）+ UI 线程 `system()` fork 一个 shell 本身就是卡顿源。
   缓存的目的**是「少解码」，不是「倒缓存」**。
3. **多页共用一个缓存实例要引用计数**（`acquire()/release()` 配对）：否则一个页面退出就把别人还在用的位图踢了
   （首页↔搜索页来回切就是这种情况）。
4. **容量是内存换速度，不是越大越好**：`capacity × 单图解码体积` = 峰值占用（280×280 BGRA ≈ 300 KB/张 → 128 槽上限 ≈ 38 MB）。
   Z20/Z21 那类 36~128 MB 内存板尤其要算账。真机实测本工程缓存 8~40 张时 `VmRSS ≈ 8964 kB`（与改前同量级）。
5. **只对「每次刷新都会重设的图」有价值**（列表 fill / 频繁切页的封面）；静态一次性图不需要。
6. **不是所有列表都有图**（有的列表只有文字行）→ 别硬接；没有封面的行**别调** `cache()`（空路径属调用方 bug）。
7. **首解不加速**：只在「同一路径第二次上屏」时生效（实测首次解码 211→208 ms，符合预期）。
   想让新图也快只能在**后台线程预热**（渲染完顺手 `cache()`）——涉及跨线程持有框架资源表，**尚未验证**。
8. **拖动本来就不重复解码**（本工程改前后都是 0 条）——别把「拖动卡」直接归因到这个病，先按 §1 判据 3 量。

## 6. 实测数字（F133 真机；内网板，地址从略）

同一操作、同一台板、改前后各一次（口径：在 `obtainListItemData_*` 里临时埋点，
量 `setBackgroundPic()` 的 UI 线程耗时；量完已删埋点）：

| 场景 | 改前（无 ImageCache） | 改后（有 ImageCache） | 变化 |
|---|---|---|---|
| **首屏** 6 推荐 + 2 榜单（首次解码，不可避免） | **211 ms**（8 次解码） | **208 ms**（装载 ×8） | ≈持平（不加速首解） |
| **回页重设同一批封面** | **315 ms** | **1 ms**（命中 ×8） | **−99.7%** |
| 回页整体的第二批（新路径，首次解码） | 209 ms | 205 ms | 持平 |
| **回页合计** | **524 ms** | **206 ms** | **−61%** |
| **拖动**（推荐/榜单/搜索结果） | 解码 0 条 | 解码 0 条 | 本来就不重解 |

改后读数摘录（`hits/loads` 口径）：`ImageCache 命中 ... weight=-5` × 8 → 本批 `loads +0`；
下一批新路径 `ImageCache 装载 ... 槽=9/128`（首次解码 37 ms）。

## 7. 验收口径（怎么量「解码次数 / ms」）

1. **解码次数（最硬）**：用组件的 `loads()` 增量 = 解码次数；或数日志里「装载」条数。
   改前：回页一次 `hits=0 / loads=8`；改后：`hits=8 / loads=0`。
   没有读数接口时用临时埋点在 `setBackgroundPic()` 前后计时（**量完必须删掉埋点**）。
2. **UI 线程耗时**：同一操作、同一台板、改前后各一次，量「回页合计 ms」（本工程 524 → 206 ms）。
3. **内存**：`grep VmRSS /proc/<pid>/status`，与改前同量级（本例 ≈ 8964 kB）。
4. **画面**：改前后像素级 diff（`tools/ui_tools/ui_diff.py ... --tol 2`）应**只差动了的地方**；
   列表封面这类改动理想情况是「零像素差」（真机实测：`ui_diff` 只报新按钮那一处）。
5. **反向验证**：换关键词/换批次场景专门验一次**不串图**（§5 坑 1 的回归）。

## 8. 基准实现与出处

| 项 | 位置 | 说明 |
|---|---|---|
| 上游参考实现（钟工指定） | `projects/LearningProject/HaishiM9/src/logicSelf/imageCache.h` | `CACHE_SIZE=128` + 权重 LRU + `BitmapHelper::loadBitmapFromFile/unloadBitmap`；用法见该工程 `src/logic/MenuLogic.cc:1151/1153`、`1219/1221`（`setBackgroundPic` 后紧跟 `cache`）与 `src/logic/HelpInterfaceLogic.cc:129/141/154`（先 `cache` 再 `setBackgroundPic`，两种顺序都成立）。⚠️ 其 `releaseAll()` 末尾的 `drop_caches` 别抄（坑 2）。 |
| 真机验证过的工程化版 | `projects/iOSStyle-F133/src/core/ImageCache.hpp` | 单例 + 引用计数 `acquire()/release()` + 内部加锁；**去掉** `drop_caches`。接线点 `src/logic/mu_mainLogic.cc:521/562`、`src/logic/mu_searchLogic.cc:313`；`onUI_init/onUI_quit` 配 `acquire()/release()`。 |
| 可复用组件（本仓库） | `components/imagecache/` | 把上者的工程耦合摘掉（装载/释放**回调注入**），并补上「不静默的错误处理 + 日志钩子 + 诊断读数」；PC 自测 29 项含串图复现。 |
| 原始实测报告 | `temp/music_ui/REPORT.md` | 改前后数据、串图回归、像素 diff、未验证项。 |

## 相关

- `listview-fields.md`（字段/回调全集、刷新与跟随口径）
- `high-frequency-callback-perf.md`（高频回调里禁做的事）
- `components/imagecache/`（代码 + `platforms.md` 逐平台实测 + `example/` 自测与接线样板）
- `ui-asset-rules.md`（出图尺寸/与控件盒一致的一般规则）
