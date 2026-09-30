/*
 * album_upload_example.cc —— zk::album 最小接线示例（设备端）
 *
 * 跑起来要三步（照 README「怎么用」）：
 *   1) 把 components/mp_transfer/ 的 4 个源文件 + 1 个头拷进工程（它在工程里通常叫 src/mp_transfer/ 与 src/system/）；
 *   2) 把 components/album_upload/ 的 include/ 与 src/ 拷进工程，本组件 .cpp 加进编译；
 *   3) 照本文的 main 接：configure → 回调 → start；UI 侧看 example/flythings_wiring.cc。
 *
 * ⚠️ 本文件是**接线形状**，不是已上机产物：本仓没有设备侧验证记录（见 ../platforms.md §0）。
 *    它的编译判据只有「PC 侧语法自检」（见 ../README.md 「验证」一节）。
 *
 * 依赖替换点：本示例只用 libc/printf；工程里把 printf 换成自己的日志宏即可。
 */

#include "zk/zk_album.h"

#include <stdio.h>
#include <string>

/* ------------------------------------------------------------------ *
 * 0) 本机 IP 提供者：兜底二维码要拼 http://<ip>:9000/upload
 *    工程里传自己的实现（如 NetKeeper_localIp()）；不设 → 组件用 0.0.0.0 并 WARN
 * ------------------------------------------------------------------ */
static std::string myLocalIp(void *user) {
    (void)user;
    return "127.0.0.1";     /* 工程里换成真实网卡 IP 的取法（wlan0 → eth0 → 其它非回环） */
}

/* ------------------------------------------------------------------ *
 * 1) 回调：**在 mp_transfer 接收线程里被调** → 只置标志 / 记路径 / 入队列
 * ------------------------------------------------------------------ */
static volatile bool sNeedRefreshUi = false;
static int sPhotoCount = 0;
static int sVideoCount = 0;

static void onFileAdded(const zk::album::FileInfo &info, void *user) {
    (void)user;
    printf("[album] 收到文件: %s (%llu B, kind=%d)\n",
           info.path.c_str(), (unsigned long long)info.size, info.kind);
    if (info.kind == zk::album::FILE_PHOTO) sPhotoCount++;
    else if (info.kind == zk::album::FILE_VIDEO) sVideoCount++;
    sNeedRefreshUi = true;      /* ← UI 刷新交给 UI 线程（定时器里读这个标志） */
}

static void onStateChanged(bool peer_connected, void *user) {
    (void)user;
    /* 手机连上 = 正在收文件：页面把「呼吸灯」换成「帧动画」就靠这个 */
    printf("[album] 手机%s\n", peer_connected ? "已连接，正在接收" : "已断开");
    sNeedRefreshUi = true;
}

static void onLog(int level, const char *msg, void *user) {
    (void)user;
    static const char *kLevel[] = { "D", "W", "E" };
    printf("[album:%s] %s\n", kLevel[level], msg);
}

/* ------------------------------------------------------------------ *
 * 2) 二维码：三态口径（远端码图 / 控件现场生成 / 本机上传地址兜底）
 * ------------------------------------------------------------------ */
static void printQr(const zk::album::QrInfo &qr) {
    switch (qr.mode) {
        case zk::album::QR_REMOTE_IMAGE:
            /* 远端小程序码图已就绪 → 显示图片（setBackgroundPic(image_path)），隐藏 qrcode 控件 */
            printf("[album] QR = 远端小程序码图: %s (本地 %s)\n",
                   qr.image_url.c_str(), qr.image_path.c_str());
            break;
        case zk::album::QR_LOCAL_GENERATED:
            /* 二维码控件现场生成：只在内容变化时 loadQRCode（QR 重算很贵） */
            printf("[album] QR = 控件现场生成: %s\n", qr.content.c_str());
            break;
        default:
            printf("[album] QR = 本机上传地址兜底: %s\n", qr.content.c_str());
            break;
    }
    if (qr.mode != zk::album::QR_REMOTE_IMAGE && !qr.image_url.empty() && !qr.image_ready) {
        /* 配了远端小程序码图但还没下载好 → 先用控件生成顶住，同时去下载 */
        printf("[album]   （远端码图待下载: %s）\n", qr.image_url.c_str());
    }
}

/* ------------------------------------------------------------------ *
 * 3) 典型生命周期（放你工程的 onUI_init / onUI_quit 对应位置）
 * ------------------------------------------------------------------ */
void album_upload_example_main() {
    zk::album::Uploader &up = zk::album::Uploader::instance();

    up.setLogHook(onLog, 0);
    up.setOnFileAdded(onFileAdded, 0);
    up.setOnStateChanged(onStateChanged, 0);
    up.setLocalIpProvider(myLocalIp, 0);

    zk::album::Config cfg;                  /* 默认值安全：不传参也能跑（save_dir=/mnt/sdnand/album/） */
    cfg.save_dir = "/mnt/sdnand/album/";    /* ⚠️ 必须与 mp_transfer 编译期 MP_PATH 一致，末尾带 '/' */
    cfg.device_name = "我的相框";            /* 小程序里看到的设备名；空 → "Frame" */
    cfg.owner = "albumActivity";            /* 谁持有（多页共用时区分） */
    cfg.qr_url = "";                        /* 空 → 兜底本机上传地址；非空 = 现场生成的内容 */
    cfg.qr_image_url = "";                  /* 非空 = 远端微信小程序码图（控件编不出来） */
    cfg.mp_app_id = "";                     /* AppID 只记录，不参与生成 —— 一律配置，不许写死 */
    cfg.start_on_configure = true;

    zk::album::Result r = up.configure(cfg);
    printf("[album] configure: %s (%s)\n", r.ok() ? "OK" : "FAIL", r.msg.c_str());
    if (!r.ok()) return;

    up.refresh();                           /* 进页先扫一遍，拿图片/视频计数 */
    printQr(up.qrInfo());
    printQr(up.qrInfo());                   /* 远端码图就绪后（notifyQrImageDownloaded(true)）再取一次就变三态第一态 */

    /* …… 应用运行：小程序随时发图；UI 定时器里消费 sNeedRefreshUi …… */

    up.stop();                              /* 离开页面停传输（省电；小程序侧会显示设备不可见） */
    up.resetQrCache();                      /* ⚠️ 页面销毁时必调，否则重进页二维码可能空白 */
}

/* ------------------------------------------------------------------ *
 * 4) 远端小程序码图怎么下来？（组件不干网络，用工程自己的下载器）
 *
 *    up.notifyQrImageDownloaded(true/false) 由**下载完成回调**调：
 *
 *    // 工程侧（easyui 的 http::Downloader；见 $(curl-cxx)/include/http/downloader.h）
 *    if (zk::album::Uploader::instance().qrInfo().mode != zk::album::QR_REMOTE_IMAGE
 *        && !zk::album::Uploader::instance().qrInfo().image_url.empty()) {
 *        http::Downloader::Task t;
 *        t.source = zk::album::Uploader::instance().qrInfo().image_url;
 *        t.target = zk::album::Uploader::instance().qrInfo().image_path;
 *        t.retry_max = 2;
 *        t.result = [](const http::Downloader::Task &task, bool ok) {
 *            (void)task;
 *            zk::album::Uploader::instance().notifyQrImageDownloaded(ok);  // ← 标志位
 *            // ⚠️ 别在这里动控件：下载器回调不在 UI 线程；下一拍 UI 定时器里再刷
 *        };
 *        http::Downloader::instance().add(t);
 *    }
 *
 *    失败 → 组件自动回落到「控件现场生成 / 本机地址兜底」，不会卡在空白。
 * ------------------------------------------------------------------ */
