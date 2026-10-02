# imagecache —— 列表封面「已解码位图」缓存 v0.1.0

**能吃就用的东西**：按**路径**缓存「已解码的位图」，让 `listview` 在刷新/回页重建 item 时
**不再把同一张图解第二遍**。专治「列表一多 / 图一大就卡」：回页重设同一批封面真机 **315 ms → 1 ms**。

- 对外命名空间：`zk::`（头文件 `include/zk/zk_imagecache.h`，C++），**源码型**
  （`include/ + src/ + example/`，整目录拷进工程即用，核心**零第三方依赖**）
- 依赖：核心无（只用 libc）；FlyThings 接线用 `easyui`（`BitmapHelper`）+ `log`，见 `Manifest.xml`
- 机制来源（指定口径）：装载/释放**回调注入**→ 同一份代码在设备与 PC 上都能跑
- 落地来源：`projects/iOSStyle-F133`（CloudMusic-F133 音乐 App 首页/搜索页封面列表），
真机数字与踩坑记录见 `platforms.md` + `temp/music_ui/REPORT.md`

**版本记录**
- **v0.1.0（2026-09-23）**首版入库：`zk::ImageCache`（单例 + `acquire/release` 引用计数 +
权重 LRU + `capacity`/`pathMaxLen` 参数 + 日志钩子 + `lastError()` 不静默）；
  PC 自测 29 项（含「固定名换内容 → 串图」复现）；F133 真机数字沿用工程内联基线（见 `platforms.md` §5 未验证项）。

## 1. 用法（能直接抄，10 行）

```cpp
#include "zk/zk_imagecache.h"

/* ① 装载/释放回调：FlyThings 上就是 BitmapHelper（别的宿主自己实现这两个） */
static int  myLoad(const char *path, zk::Bitmap *out, void *user) {
    bitmap_t *bmp = NULL;
    if (!BitmapHelper::loadBitmapFromFile(bmp, path) || bmp == NULL) return -1;  /* 失败不静默 */
    *out = (zk::Bitmap) bmp;  return 0;
}
static void myFree(zk::Bitmap bmp, void *user) { BitmapHelper::unloadBitmap((bitmap_t *) bmp); }

/* ② 配一次（幂等；重复调返回 false + warning，不覆盖回调） */
static void setup() {
    zk::ImageCache::Config cfg;               /* 默认 capacity=128, pathMaxLen=256 */
    cfg.load = myLoad; cfg.free = myFree;
    cfg.capacity = 128;                       /* 内存换速度：按板子内存算账（见 §4 坑 4） */
    zk::ImageCache::instance().setLogHook(myLog, NULL);
    zk::ImageCache::instance().configure(cfg);
}

/* ③ 页面：onUI_init -> acquire()　onUI_quit -> release()（配对，最后一个才真清） */
/* ④ 列表 fill：setBackgroundPic(path) 之后紧跟一句 */
static void obtainListItemData_ListResult(ZKListView *, ZKListView::ZKListItem *item, int index) {
    ZKListView::ZKListSubItem *cover = item->findSubItemByID(ID_XXX_SubCover);
    const std::string &p = vData[index].coverPath;      /* ⚠️ 路径必须唯一（含批次/版本）*/
    cover->setBackgroundPic(p.c_str());                 /* 首次：框架当场解 */
    zk::ImageCache::instance().cache(p.c_str());        /* 就这一句：登记已解码位图 */
}
```

完整的接线样板（含 `acquire/release` 与验收读数）见 `example/flythings_wiring.cc`。

## 2. 为什么能变快（机制）

`setBackgroundPic(path)` 会让框架**当场解这张 PNG**（280×280 圆角封面真机 **26~65 ms/张**，
64×64 小图 3~4 ms），全部落在 UI 线程；列表被重建（回页/换页/刷新/控件回收后重设）时同一张图会被反复解。
`BitmapHelper::loadBitmapFromFile` 会把解好的位图登记进框架资源表并**持有**它 —— 只要本缓存不 `unload`，
框架再遇到同路径就直接复用，**不再解一遍**。缓存做的就是「持有 + 退役」这件事。

**权重 LRU 语义**（与 HaishiM9 逐行同义）：每槽 = `{路径, 位图, weight}`；每次 `cache(path)`：命中 → `weight++`；未命中的**已占用**槽一律 `weight--`；腾位置时挑「空槽优先，否则 weight 最小」踢掉，再装载新图（`weight=1`）。
→ 「常看的封面」不会被「一次性扫过的图」挤出去。

## 3. API

| 成员 | 作用 |
|---|---|
| `static ImageCache &instance()` | 单例（一个进程一份） |
| `bool configure(const Config &)` | 配回调 + 容量。`Config{load, free, user, capacity=128, pathMaxLen=256}`；幂等，重复调返 false |
| `bool configured()` | 是否已配 |
| `void acquire()` / `void release()` | 页面进入/退出（**引用计数**：计数归零才真正释放全部） |
| `bool cache(const char *path)` | **核心一句**：命中只涨权重；未命中按 LRU 腾位置装载。false = 拒收/失败（原因见 `lastError()`） |
| `void releaseAll()` | 立刻放掉全部（正常由 `release()` 归零时调；手动调供收尾/调试） |
| `int slots()/capacity()/hits()/loads()/evicts()/fails()/refs()` | 诊断读数。**`hits()/loads()` 就是验收要的「命中次数/解码次数」**|
| `const char *lastError()` | 最后一条错误（人话，可直接打日志）；无错误返 `""`（不返 NULL） |
| `void setLogHook(zk_ic_log_fn, void *user)` | 日志接出去（app 模式下 stdout 是 `/dev/null`，必须接） |

编译期开关：`ZK_IMAGECACHE_NO_THREADS=1`（确定只有 UI 线程用时，锁都不编）、
`ZK_IMAGECACHE_PATH_MAX_DEFAULT`（默认 256）。

## 4. 已知坑（都是真机踩出来的，照做即可）

1. ⚠️ **固定文件名的封面被 pin 住会串图**：搜索结果封面原来用固定名（`cm_cov_sg<i>.png` 一类），
进缓存后新一批**复用了旧路径**→ 上屏是上一批的图。**修法：路径带批号/版本号**
   （`cm_cov_sg<批号>_<序号>.png`，开新一批删上一批文件）。硬约束：**缓存键 = 路径，路径必须唯一**。
2. ⚠️ **不要**照抄 HaishiM9 `releaseAll()` 末尾的 `system("echo 3 > /proc/sys/vm/drop_caches")`：全局副作用（把页缓存全倒掉，后续所有文件读**更慢**）+ UI 线程 `system()` fork 一个 shell 本身就是卡顿源。
本缓存是「少解码」，不是「倒缓存」——本组件没有这一句。
3. **多页共用一个实例要引用计数**（`acquire/release`）：否则一个页面退出就把别人还在用的位图踢了。
4. **容量是内存换速度**：`capacity × 单图解码体积` = 峰值占用（280×280 解码后 ≈300 KB/张 → 128 槽上限 ≈38 MB）。
   Z20/Z21 那类 36~128 MB 内存板尤其注意，**别无脑加大**。
5. **只对「每次刷新都会重设的图」有价值**（列表 fill / 频繁切页的封面）；静态一次性图不需要
   （装了也要为它花一次装载 + 占一个槽）。
6. **不是所有列表都有图**（有的列表只有文字行）→ 别硬接；没封面的行别调 `cache()`（空路径计入 `fails()` + warning）。
7. **首解不加速**：只对「同一路径第二次上屏」生效（实测首次解码 211→208 ms，符合预期）。
要让新图也快只能在后台线程预热 —— 涉及跨线程持有框架资源表，**尚未验证，别默认开**。
8. **拖动本来就不重复解码**（本工程实测改前后都是 0 条）——这套东西真正治的是**「回页重设」**这条路。

## 5. 排错

| 症状 | 原因 / 处理 |
|---|---|
| 回页还是慢 | 打印 `hits()/loads()`：`loads` 还在涨 = 没命中 → 检查路径是否每批都变（坑 1 的反面：**故意变**才对）、`configure` 是否真成功 |
| 上屏是上一批的图 | 固定名封面被 pin：改成带批次/版本的路径（坑 1） |
| `cache()` 返 false | 看 `lastError()`：未 configure / 空路径 / 路径超 `pathMaxLen` / load 回调没给出位图 |
| 内存涨 | `slots()` 是否长期顶到 `capacity()`；按板子内存下调 `capacity`（坑 4） |
| 页面切走后图没了 | `release()` 与 `acquire()` 没配对（计数被减到 0 → 全清）；检查是否漏了某个页面的 acquire |
| 想看命中/装载明细 | `setLogHook()` 装上钩子（DEBUG 级打「命中/装载 槽=n/cap」） |

## 6. 验收口径（可复用）

1. **解码次数（最硬）**：`loads()` 增量。改前回页 `hits=0/loads=8`；改后 `hits=8/loads=0`。
2. **UI 线程耗时**：同一操作、同一台板、改前后各一次（真机口径回页合计 524 → 206 ms）。
3. **内存**：`grep VmRSS /proc/<pid>/status`（本例缓存 8~40 张时 ≈ 8964 kB）。
4. **画面**：改前后像素 diff 应只差动了的地方（本类改动理想是零像素差）。
5. **反向验证**：换批/换关键词场景专门验一次**不串图**。

## 7. 文件

```
components/imagecache/
├─ include/zk/zk_imagecache.h        # 唯一对外头（zk::ImageCache）
├─ src/zk_imagecache.cpp             # 实现（LRU 权重 + 引用计数 + 锁 + 不静默错误）
├─ example/zk_imagecache_test.cpp    # PC 可编可跑的自测（29 项；含串图复现）
├─ example/flythings_wiring.cc       # FlyThings 接线样板（依赖 easyui/log，只能在工程里编）
├─ example/README.md                 # 两条路怎么用（先看这个）
├─ platforms.md                      # 逐平台实测/未验证 + 验收口径
└─ Manifest.xml                      # 底层依赖 + 本模块被引用的两种方式
```

## 8. 出处

| 项 | 内容 |
|---|---|
| 上游参考实现 | `projects/LearningProject/HaishiM9/src/logicSelf/imageCache.h`（指定：`CACHE_SIZE=128` + 权重 LRU + `BitmapHelper`；用法见该工程 `src/logic/MenuLogic.cc`、`HelpInterfaceLogic.cc`） |
| 真机验证过的工程化版 | `projects/iOSStyle-F133/src/core/ImageCache.hpp`（单例 + 引用计数 + 锁；去掉 `drop_caches`） |
| 真机实测报告 | `temp/music_ui/REPORT.md`（改前后同操作数据、串图回归、像素 diff） |
| 知识条目 | `knowledge/uicontrols/listview-image-cache.md`（病症/机制/修法/验收的口径） |
