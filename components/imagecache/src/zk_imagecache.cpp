/*
 * zk_imagecache.cpp —— 「已解码位图」按路径缓存（LRU 权重 + 引用计数 + 锁）
 *
 * 语义逐行对齐两处基准（改动只在「装载/释放走回调」与「错误处理不静默」）：
 *   · HaishiM9 `src/logicSelf/imageCache.h`（上游参考）
 *   · `projects/iOSStyle-F133/src/core/ImageCache.hpp`（真机验证过的工程化版）
 *
 * 每次 cache(path)：
 *   命中       -> weight++（最近用得越多越重），不解码；
 *   未命中的**已占用**槽一律 weight--（路过一次掉一点）；
 *   腾位置时挑「空槽优先，否则 weight 最小」的那个踢掉（踢 = 交还 FreeFn），再装载新图（weight=1）。
 * 于是「常看的封面」不会被「一次性扫过的图」挤出去。
 */
#include "zk/zk_imagecache.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---------------- 锁：设备侧 pthread（与验证过的工程版同源）；PC/Windows 用 std::mutex ---------------- */
#if ZK_IMAGECACHE_NO_THREADS
namespace {
struct Lock {
    void init() {}
    void destroy() {}
    void lock() {}
    void unlock() {}
};
} /* namespace */
#elif defined(_WIN32)
#include <mutex>
namespace {
struct Lock {
    void init() {}
    void destroy() {}
    void lock() { mMx.lock(); }
    void unlock() { mMx.unlock(); }
    std::mutex mMx;
};
} /* namespace */
#else
#include <pthread.h>
namespace {
struct Lock {
    void init() { pthread_mutex_init(&mMx, NULL); }
    void destroy() { pthread_mutex_destroy(&mMx); }
    void lock() { pthread_mutex_lock(&mMx); }
    void unlock() { pthread_mutex_unlock(&mMx); }
    pthread_mutex_t mMx;
};
} /* namespace */
#endif

namespace zk {

struct ImageCache::Impl {
    struct Slot {
        char *path;     /* NULL = 空槽（空槽优先级最高，一定先被用）*/
        Bitmap bmp;     /* 非 NULL = 本缓存持有的一张已解码位图 */
        int weight;     /* 越大越不容易被踢 */
    };

    Impl()
        : loadFn(NULL), freeFn(NULL), user(NULL), cap(0), pathMax(0), cfg(false),
          slots(NULL), refs(0), hits(0), loads(0), evicts(0), fails(0),
          logFn(NULL), logUser(NULL) {
        mtx.init();
        lastErr[0] = '\0';
        logHookMtx.init();
    }
    ~Impl() {
        releaseAllLocked();
        if (slots != NULL) {
            free(slots);
            slots = NULL;
        }
        logHookMtx.destroy();
        mtx.destroy();
    }

    /* ---- 日志：库内可诊断，日志能接出去（components/README.md §2.8）---- */
    void logf(int level, const char *fmt, ...) {
        zk_ic_log_fn fn = NULL;
        void *lu = NULL;
        logHookMtx.lock();
        fn = logFn;
        lu = logUser;
        logHookMtx.unlock();
        if (fn == NULL) {
            return;                     /* 没装钩子 = 不打（设备 app 模式 stdout 是 /dev/null）*/
        }
        char buf[256];
        va_list ap;
        va_start(ap, fmt);
        vsnprintf(buf, sizeof(buf), fmt, ap);
        va_end(ap);
        fn(level, buf, lu);
    }

    void setError(const char *fmt, const char *a1) {
        snprintf(lastErr, sizeof(lastErr), fmt, a1 == NULL ? "" : a1);
    }

    int usedSlotsLocked() const {
        int n = 0;
        for (int i = 0; i < cap; ++i) {
            if (slots[i].bmp != NULL) {
                ++n;
            }
        }
        return n;
    }

    void releaseAllLocked() {
        if (slots == NULL) {
            return;
        }
        for (int i = 0; i < cap; ++i) {
            if (slots[i].bmp != NULL) {
                freeFn(slots[i].bmp, user);     /* 交还（框架若还引用着，它自己记账）*/
                slots[i].bmp = NULL;
            }
            if (slots[i].path != NULL) {
                ::free(slots[i].path);
                slots[i].path = NULL;
            }
            slots[i].weight = 0;
        }
    }

    LoadFn loadFn;
    FreeFn freeFn;
    void *user;
    int cap;
    int pathMax;
    bool cfg;
    Slot *slots;
    int refs;
    int hits;
    int loads;
    int evicts;
    int fails;
    char lastErr[192];
    zk_ic_log_fn logFn;
    void *logUser;
    Lock logHookMtx;
    Lock mtx;
};

ImageCache::Config::Config()
    : load(NULL), free(NULL), user(NULL),
      capacity(128), pathMaxLen(ZK_IMAGECACHE_PATH_MAX_DEFAULT) {
}

ImageCache &ImageCache::instance() {
    static ImageCache sInst;            /* C++11 magic static：初始化线程安全 */
    return sInst;
}

ImageCache::ImageCache() : mImpl(new Impl()) {
}

ImageCache::~ImageCache() {
    delete mImpl;
}

bool ImageCache::configure(const Config &cfg) {
    if (cfg.load == NULL || cfg.free == NULL) {
        mImpl->setError("configure 失败：load/free 回调不能为空", NULL);
        mImpl->logf(ZK_IC_LOG_ERROR, "ImageCache %s", mImpl->lastErr);
        return false;
    }
    const int cap = cfg.capacity > 0 ? cfg.capacity : 128;
    const int pmax = cfg.pathMaxLen >= 8 ? cfg.pathMaxLen
                                         : ZK_IMAGECACHE_PATH_MAX_DEFAULT;
    Impl::Slot *slots = (Impl::Slot *) calloc((size_t) cap, sizeof(Impl::Slot));
    if (slots == NULL) {
        mImpl->setError("configure 失败：槽位数组分配失败（capacity=%d）", NULL);
        mImpl->logf(ZK_IC_LOG_ERROR, "ImageCache %s cap=%d", mImpl->lastErr, cap);
        return false;
    }
    mImpl->mtx.lock();
    if (mImpl->cfg) {
        mImpl->mtx.unlock();
        ::free(slots);                  /* 幂等：已配置不覆盖（两个页面抢着换回调是大坑）*/
        mImpl->setError("configure 忽略：已配置过（本进程一份，先 releaseAll 也不会重配）", NULL);
        mImpl->logf(ZK_IC_LOG_WARN, "ImageCache %s", mImpl->lastErr);
        return false;
    }
    mImpl->slots = slots;
    mImpl->cap = cap;
    mImpl->pathMax = pmax;
    mImpl->loadFn = cfg.load;
    mImpl->freeFn = cfg.free;
    mImpl->user = cfg.user;
    mImpl->cfg = true;
    mImpl->mtx.unlock();
    mImpl->logf(ZK_IC_LOG_DEBUG, "ImageCache 配置完成 cap=%d pathMax=%d", cap, pmax);
    return true;
}

bool ImageCache::configured() const {
    return mImpl->cfg;
}

void ImageCache::acquire() {
    mImpl->mtx.lock();
    ++mImpl->refs;
    const int r = mImpl->refs;
    mImpl->mtx.unlock();
    mImpl->logf(ZK_IC_LOG_DEBUG, "ImageCache acquire refs=%d", r);
}

void ImageCache::release() {
    mImpl->mtx.lock();
    if (mImpl->refs > 0) {
        --mImpl->refs;
    }
    const bool freeAll = (mImpl->refs == 0);
    if (freeAll) {
        mImpl->releaseAllLocked();
    }
    mImpl->mtx.unlock();
    if (freeAll) {
        mImpl->logf(ZK_IC_LOG_DEBUG, "ImageCache 释放全部（无页面在用）");
    }
}

bool ImageCache::cache(const char *path) {
    /* 空路径不是「没事发生」：调用方契约是「有封面的行才调 cache」。计入 fails 并报出来。*/
    if (path == NULL || path[0] == '\0') {
        mImpl->mtx.lock();
        ++mImpl->fails;
        mImpl->setError("cache 拒收：路径为空（没封面的行别调 cache）", NULL);
        mImpl->mtx.unlock();
        mImpl->logf(ZK_IC_LOG_WARN, "ImageCache %s", mImpl->lastErr);
        return false;
    }
    if (!mImpl->cfg || mImpl->slots == NULL) {
        mImpl->mtx.lock();
        ++mImpl->fails;
        mImpl->setError("cache 拒收：未配置（先 configure(load/free)）", NULL);
        mImpl->mtx.unlock();
        mImpl->logf(ZK_IC_LOG_ERROR, "ImageCache %s", mImpl->lastErr);
        return false;
    }
    const size_t plen = strlen(path);
    if ((int) plen >= mImpl->pathMax) {
        mImpl->mtx.lock();
        ++mImpl->fails;
        mImpl->setError("cache 拒收：路径过长（超过 pathMaxLen）", NULL);
        mImpl->mtx.unlock();
        mImpl->logf(ZK_IC_LOG_WARN, "ImageCache %s len=%d max=%d",
                    mImpl->lastErr, (int) plen, mImpl->pathMax);
        return false;
    }

    mImpl->mtx.lock();
    int index = -1;
    for (int i = 0; i < mImpl->cap; ++i) {
        Impl::Slot &it = mImpl->slots[i];
        if (it.bmp != NULL && it.path != NULL && strcmp(it.path, path) == 0) {
            ++it.weight;                        /* 命中：权重 +1，不重解 */
            ++mImpl->hits;
            const int w = it.weight;
            mImpl->mtx.unlock();
            mImpl->logf(ZK_IC_LOG_DEBUG, "ImageCache 命中 %s weight=%d", path, w);
            return true;
        }
        if (it.bmp != NULL) {
            --it.weight;                        /* 老项每路过一次掉一点权重 */
            if (index < 0 || (mImpl->slots[index].bmp != NULL
                              && mImpl->slots[index].weight > it.weight)) {
                index = i;
            }
        } else if (index < 0 || mImpl->slots[index].bmp != NULL) {
            index = i;                          /* 空槽优先当牺牲位 */
        }
    }
    if (index < 0) {                            /* capacity <= 0 才会到这；不静默 */
        ++mImpl->fails;
        mImpl->setError("cache 拒收：无可用槽位（capacity<=0）", NULL);
        mImpl->mtx.unlock();
        mImpl->logf(ZK_IC_LOG_ERROR, "ImageCache %s", mImpl->lastErr);
        return false;
    }

    Impl::Slot &victim = mImpl->slots[index];
    if (victim.bmp != NULL) {
        mImpl->freeFn(victim.bmp, mImpl->user);
        victim.bmp = NULL;
        ++mImpl->evicts;
    }
    if (victim.path != NULL) {
        ::free(victim.path);
        victim.path = NULL;
    }
    victim.weight = 0;

    Bitmap nb = NULL;
    const int rc = mImpl->loadFn(path, &nb, mImpl->user);
    if (rc == 0 && nb != NULL) {
        victim.path = (char *) malloc(plen + 1);
        if (victim.path == NULL) {              /* 分配失败：位图已装进来，得立刻交还，别泄漏 */
            mImpl->freeFn(nb, mImpl->user);
            ++mImpl->fails;
            mImpl->setError("cache 失败：路径串分配失败", NULL);
            mImpl->mtx.unlock();
            mImpl->logf(ZK_IC_LOG_ERROR, "ImageCache %s", mImpl->lastErr);
            return false;
        }
        memcpy(victim.path, path, plen + 1);
        victim.bmp = nb;
        victim.weight = 1;
        ++mImpl->loads;
        const int slot = mImpl->usedSlotsLocked();
        mImpl->mtx.unlock();
        mImpl->logf(ZK_IC_LOG_DEBUG, "ImageCache 装载 %s 槽=%d/%d", path, slot, mImpl->cap);
        return true;
    }
    ++mImpl->fails;
    mImpl->setError("cache 装载失败：load 回调没给出位图", NULL);
    mImpl->mtx.unlock();
    mImpl->logf(ZK_IC_LOG_WARN, "ImageCache %s %s", mImpl->lastErr, path);
    return false;
}

void ImageCache::releaseAll() {
    mImpl->mtx.lock();
    mImpl->releaseAllLocked();
    mImpl->mtx.unlock();
    mImpl->logf(ZK_IC_LOG_DEBUG, "ImageCache releaseAll（手动）");
}

int ImageCache::slots() const {
    mImpl->mtx.lock();
    const int n = mImpl->usedSlotsLocked();
    mImpl->mtx.unlock();
    return n;
}

int ImageCache::capacity() const { return mImpl->cap; }
int ImageCache::hits() const { return mImpl->hits; }
int ImageCache::loads() const { return mImpl->loads; }
int ImageCache::evicts() const { return mImpl->evicts; }
int ImageCache::fails() const { return mImpl->fails; }

int ImageCache::refs() const {
    mImpl->mtx.lock();
    const int r = mImpl->refs;
    mImpl->mtx.unlock();
    return r;
}

const char *ImageCache::lastError() const {
    return mImpl->lastErr;
}

void ImageCache::setLogHook(zk_ic_log_fn fn, void *user) {
    mImpl->logHookMtx.lock();
    mImpl->logFn = fn;
    mImpl->logUser = user;
    mImpl->logHookMtx.unlock();
}

} /* namespace zk */
