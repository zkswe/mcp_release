/*
 * flythings_wiring.cc —— FlyThings 工程接线（拷进工程用）
 *
 * ⚠️ 本文件依赖 easyui / log，**PC 上编不过**（这是接线样板，不是自测）。
 *    组件本体 + 可在 PC 跑的自测在 `example/zk_imagecache_test.cpp`。
 *
 * 用法（两步，真机验证过的口径来自 projects/iOSStyle-F133）：
 *   ① app 启动（或首个用到封面的页面 onUI_init）调一次 `zkImageCacheSetup()`；
 *   ② 每个用到封面的页面：onUI_init -> `zk::ImageCache::instance().acquire();`
 *                           onUI_quit -> `zk::ImageCache::instance().release();`
 *   ③ 列表 fill 里：`setBackgroundPic(path)` 之后紧跟一句 `cache(path)`。
 *
 * ⚠️ 硬约束：路径必须唯一（含批次/版本）。固定名封面（换内容不换名）会命中成旧图 ——
 *    搜索结果封面请改成 `xxx_<批号>_<序号>.png`，开新一批时删上一批文件。
 */
#include "zk/zk_imagecache.h"

#include <utils/BitmapHelper.h>
#include <base/log.h>

namespace {

/* 装载 = 交给框架解这张图。关键点：BitmapHelper 会把解好的位图登记进框架资源表**并持有**它，
 * 只要我们不 unload，框架再遇到同路径就直接复用（这就是「命中不再解码」的机制来源）。 */
int icLoad(const char *path, zk::Bitmap *out, void *user) {
    (void) user;
    bitmap_t *bmp = NULL;
    if (!BitmapHelper::loadBitmapFromFile(bmp, path) || bmp == NULL) {
        return -1;                     /* 组件会记 lastError + 打 warning，不会静默 */
    }
    *out = (zk::Bitmap) bmp;
    return 0;
}

/* 释放 = 交还（框架自己记账：控件还引用着也不会出事）。 */
void icFree(zk::Bitmap bmp, void *user) {
    (void) user;
    BitmapHelper::unloadBitmap((bitmap_t *) bmp);
}

/* 日志接出去：app 模式下 stdout 是 /dev/null，必须走 LOGD/LOGW 才能在现场看到。 */
void icLog(int level, const char *msg, void *user) {
    (void) user;
    if (level == ZK_IC_LOG_DEBUG) {
        LOGD_TRACE("%s", msg);
    } else {
        LOGW_TRACE("%s", msg);         /* WARN / ERROR 都按 warning 出，现场一定能看到 */
    }
}

} /* namespace */

/** ① 配置一次（幂等：重复调用返回 false 并 warning，不会覆盖回调）。 */
void zkImageCacheSetup() {
    zk::ImageCache::Config cfg;
    cfg.load = icLoad;
    cfg.free = icFree;
    cfg.user = NULL;
    cfg.capacity = 128;      /* 内存换速度：128 × 单图解码体积。Z20/Z21 那类 36~128MB 板先算账 */
    cfg.pathMaxLen = 256;
    zk::ImageCache::instance().setLogHook(icLog, NULL);
    if (!zk::ImageCache::instance().configure(cfg)) {
        LOGW_TRACE("ImageCache configure 失败：%s", zk::ImageCache::instance().lastError());
    }
}

/** ③ 列表 fill 里的用法（以「行内一个封面 subitem」为例）。 */
void fillRowCover(ZKListView::ZKListItem *item, int coverSubItemId, const char *coverPath) {
    ZKListView::ZKListSubItem *cover = item->findSubItemByID(coverSubItemId);
    if (cover == NULL || coverPath == NULL || coverPath[0] == '\0') {
        return;                            /* 没封面的行：既不 setBackgroundPic 也不 cache */
    }
    cover->setBackgroundPic(coverPath);    /* 框架当场解这张图（首次）*/
    zk::ImageCache::instance().cache(coverPath);   /* 就这一句：登记已解码位图 */
}

/* ② 页面侧的 acquire/release 样板（放在你自己的 onUI_init / onUI_quit 里）：
 *
 *   static void onUI_init() {
 *       zkImageCacheSetup();                                  // 幂等，放哪都行
 *       zk::ImageCache::instance().acquire();                 // 本页开始用缓存
 *   }
 *   static void onUI_quit() {
 *       zk::ImageCache::instance().release();                 // 最后一个页面退出才真清
 *   }
 *   static void obtainListItemData_ListResult(ZKListView *, ZKListView::ZKListItem *item, int index) {
 *       fillRowCover(item, ID_XXX_SubCover, vData[index].coverPath.c_str());
 *   }
 *
 * 验收读数（改前/改后各量一次）：
 *   LOGD("ImageCache hits=%d loads=%d slots=%d",
 *        zk::ImageCache::instance().hits(), zk::ImageCache::instance().loads(),
 *        zk::ImageCache::instance().slots());
 *   → 回页重设同一批封面：改前 hits=0/loads=8，改后 hits=8/loads=0。
 */
