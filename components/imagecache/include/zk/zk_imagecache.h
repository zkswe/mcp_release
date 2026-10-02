/*
 * zk_imagecache.h —— 列表封面「已解码位图」按路径缓存（可复用组件）
 *
 * 解决什么：FlyThings 的 listview 每次刷新/滚动/回页重建 item 时，`setBackgroundPic(path)`
 *会让框架**当场解一遍**这张图（280×280 圆角封面实测 26~65ms/张，64×64 小图 3~4ms/张），
 *全部落在 UI 线程上；同一批封面在「回页重设」这条路上会被反复解码。
 *本组件按**路径**缓存「已解码位图」：命中就不再解码。
 *
 * 出处（两处，口径同源）：
 *   ① 上游参考实现 = HaishiM9 `src/logicSelf/imageCache.h`（指定）：CACHE_SIZE=128 槽 +
 *权重 LRU，`cache(path)` 在 fill 里 `setBackgroundPic(path)` 之后紧跟一句；
 *用法见该工程 `src/logic/MenuLogic.cc`、`HelpInterfaceLogic.cc`。
 *   ② 真机验证过的工程化版 = `projects/iOSStyle-F133/src/core/ImageCache.hpp`（CloudMusic-F133）：
 *相对 HaishiM9 的改动 = 单例 + 引用计数 acquire()/release()、内部加锁、**去掉**
 *      `releaseAll()` 末尾的 `system("echo 3 > /proc/sys/vm/drop_caches")`。
 *本头文件 = 把 ② 的工程耦合（`ui::` 命名空间硬编码 BitmapHelper）摘掉：装载/释放由调用方
 *用回调注入，于是同一份代码在 PC 上也能编、也能自测（见 example/zk_imagecache_test.cpp）。
 *
 * ⚠️ 硬约束（真机踩出来的，见 knowledge/uicontrols/listview-image-cache.md）：
 *缓存键是**路径**。同一个文件名换内容（固定名封面覆盖写）会被命中成旧图 —— 上屏还是上一批。
 *所以**路径必须唯一（含批次/版本号）**；固定名的封面请改成 `xxx_<批号>_<序号>.png`。
 *
 * ⚠️ 只对「每次刷新都会重设的图」有价值（列表 fill / 频繁切页的封面）。
 *静态一次性图不需要（装了也要为它花一次装载 + 一个槽位）。
 *
 * 线程：acquire/cache/release 通常都在 UI 线程调（fill / onUI_quit）；内部加锁是为「以后从
 *后台线程预热」留安全边界 —— 编译期可选（见下面 ZK_IMAGECACHE_* 宏）。
 */
#ifndef ZK_IMAGECACHE_H
#define ZK_IMAGECACHE_H

#include <stddef.h>

/* ---------------- 编译期开关（都有安全默认值） ---------------- */
/* ZK_IMAGECACHE_NO_THREADS=1 —— 全程单线程、连锁都不编（省 40 字节 + 一次 lock 调用）。
 *只在「确定只有 UI 线程用」时开；默认按平台选 pthread（Linux/设备）或 std::mutex（Windows/PC）。*/
#ifndef ZK_IMAGECACHE_NO_THREADS
#define ZK_IMAGECACHE_NO_THREADS 0
#endif
/* ZK_IMAGECACHE_PATH_MAX_DEFAULT —— 不传 pathMaxLen 时的路径串上限（HaishiM9 口径 256）。*/
#ifndef ZK_IMAGECACHE_PATH_MAX_DEFAULT
#define ZK_IMAGECACHE_PATH_MAX_DEFAULT 256
#endif

/* ---------------- 日志钩子 ---------------- */
/* app 模式下 stdout 是 /dev/null，库内日志必须能接出去（components/README.md §2.8）。*/
enum zk_ic_log_level {
    ZK_IC_LOG_DEBUG = 0,
    ZK_IC_LOG_WARN = 1,
    ZK_IC_LOG_ERROR = 2
};
/* msg 只在本回调内有效；不要存指针。user 就是 setLogHook 里传的那个。*/
typedef void (*zk_ic_log_fn)(int level, const char *msg, void *user);

namespace zk {

/* 位图句柄（不透明）：本组件只保管指针、从不解引用它。*/
typedef void *Bitmap;

/* 装载：path -> 句柄。成功返 0 且 *out != NULL；失败返非 0（或返 0 但 *out == NULL 也算失败）。
 * 约定：这个位图要**一直有效**到 FreeFn 被调为止（本组件持有它，不去 unload 别人还在用的）。*/
typedef int (*LoadFn)(const char *path, Bitmap *out, void *user);

/* 释放：把装载时给的句柄交还（内部实现通常 = BitmapHelper::unloadBitmap）。*/
typedef void (*FreeFn)(Bitmap bmp, void *user);

/**
 * 图片解码位图缓存（单例；一个进程一份，多页共用要 acquire/release 计数）。
 *
 * 典型用法（页面侧三步，10 行）：
 *   // ① app 启动 / 首个用到缓存的页面 onUI_init：配一次（回调 + 容量）
 *   zk::ImageCache::Config c;                 // 默认 capacity=128, pathMaxLen=256
 *   c.load = myLoad; c.free = myFree;         // 平台适配层里包一层 BitmapHelper
 *   zk::ImageCache::instance().configure(c);
 *   // ② 每个用到的页面：onUI_init acquire() / onUI_quit release()（配对，最后一个才清）
 *   zk::ImageCache::instance().acquire();
 *   // ③ 列表 fill 里，setBackgroundPic(path) 之后紧跟一句
 *   zk::ImageCache::instance().cache(path);
 */
class ImageCache {
public:
    /**装载/释放回调 + 容量。所有字段都有安全默认值（但 load/free 必须给）。*/
    struct Config {
        LoadFn load;        /* 必需 */
        FreeFn free;        /* 必需 */
        void *user;         /* 回传给 load/free/logHook 的上下文（可为 NULL）*/
        int capacity;       /* 槽位上限，默认 128。**内存换速度**：× 单图解码体积 = 峰值占用 */
        int pathMaxLen;     /* 路径串上限，默认 256；更长的路径按「过长」拒收（不静默）*/
        Config();
    };

    static ImageCache &instance();

    /**配置（幂等：已配置过再调返回 false，不覆盖 —— 避免两个页面抢着换回调）。*/
    bool configure(const Config &cfg);
    bool configured() const;

    /**页面进入 / 退出。release() 在计数归零时才真正 releaseAll()。*/
    void acquire();
    void release();

    /**登记一张「已解码」的图：命中只涨权重（不解码）；未命中按权重 LRU 腾位置再装载。
     *返回 true = 命中或装载成功；false = 拒收/装载失败（原因见 lastError()，且已 warning）。*/
    bool cache(const char *path);

    /**立刻放掉全部（正常由 release() 归零时调；手动调仅供收尾/调试）。*/
    void releaseAll();

    /* ---------------- 诊断读数（验收用：hits/loads 就是「解码次数」） ---------------- */
    int slots() const;      /* 当前占用槽位数 */
    int capacity() const;   /* 槽位上限 */
    int hits() const;       /* 命中次数（= 少解码几次）*/
    int loads() const;      /* 实际装载（解码）次数 */
    int evicts() const;     /* 被 LRU 踢掉的次数（踢掉=下次还得重解）*/
    int fails() const;      /* 拒收 + 装载失败次数 */
    int refs() const;       /* 当前 acquire 未 release 的页面数 */

    /**最后一条错误（人话，可直接打日志）；无错误返回 ""。不返回 NULL。*/
    const char *lastError() const;

    /**装日志钩子（可随时调，线程安全）。*/
    void setLogHook(zk_ic_log_fn fn, void *user);

private:
    ImageCache();
    ~ImageCache();
    ImageCache(const ImageCache &);
    ImageCache &operator=(const ImageCache &);
    struct Impl;
    Impl *mImpl;
};

} /* namespace zk */

#endif /* ZK_IMAGECACHE_H */
