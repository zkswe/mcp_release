/*
 * album_upload_example.cc —— zk::album 最小接线示例（设备端）
 *
 * 跑起来要三步（照 README「怎么用」）：
 *   1) 把 components/mp_transfer/ 的 4 个源文件 + 1 个头拷进工程（它在工程里通常叫 src/mp_transfer/ 与 src/system/）；
 *   2) 把 components/album_upload/ 的 include/ 与 src/ 拷进工程，本组件 .cpp 加进编译；
 *   3) 照本文的 main 接：configure → setQrUrl(配置链接) → 回调 → start；
 *      UI 侧看 example/flythings_wiring.cc（二维码 = `qrInfo().content` 交给控件现场生成）。
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
 * 2) 二维码：**一条路 + 一个兜底**（都交给 ZKQRCode::loadQRCode，不铺任何位图）
 *    · QR_FROM_CONFIG            配置给的链接（从 prefs 灌进来）
 *    · QR_LOCAL_UPLOAD_FALLBACK  链接为空 → 本机上传地址 http://<ip>:9000/upload
 * ------------------------------------------------------------------ */
static void printQr(const zk::album::QrInfo &qr) {
    printf("[album] QR = %s: %s\n",
           (qr.mode == zk::album::QR_FROM_CONFIG) ? "配置的小程序链接" : "本机上传地址兜底",
           qr.content.c_str());
    printf("[album]   → 上屏：mQrcodePtr->loadQRCode(\"%s\")（UI 线程；内容变了才重算）\n",
           qr.content.c_str());
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
    cfg.mp_app_id = "";                     /* AppID 只记录，不参与生成 —— 一律配置，不许写死 */
    cfg.start_on_configure = true;

    zk::album::Result r = up.configure(cfg);
    printf("[album] configure: %s (%s)\n", r.ok() ? "OK" : "FAIL", r.msg.c_str());
    if (!r.ok()) return;

    /* 二维码内容：从你自己的 prefs 读出来灌进去（组件不带默认链接）
     * —— 链接怎么来见 ../assets/README.md（附 assets/qr_url.txt 供部署方填配置）；空串 = 本机地址兜底 */
    up.setQrUrl("");                        /* ← 换成 prefs 取值（如 StoragePreferences::getString("sp_qr_url", "")） */

    up.refresh();                           /* 进页先扫一遍，拿图片/视频计数 */
    printQr(up.qrInfo());                   /* 取一次就把 content 交给二维码控件（内容变了才重新 loadQRCode） */

    /* …… 应用运行：小程序随时发图；UI 定时器里消费 sNeedRefreshUi …… */

    /* 设置页改完链接：setQrUrl(新链接) → 下一拍 UI 定时器里重新 loadQRCode（传空串 = 退回兜底） */
    up.setQrUrl("https://mp.weixin.qq.com/a/~换成你自己的小程序链接~~");
    printQr(up.qrInfo());

    up.stop();                              /* 离开页面停传输（省电；小程序侧会显示设备不可见） */

    /* ⚠️ 页面销毁：清掉**业务侧**那份"已 load 的内容"缓存（组件侧不缓存二维码内容，无需额外清理）：
     *    不清 → 新控件从未 loadQRCode、缓存比对直接 return → 再进页二维码空白（真机复现过，见 ../README.md §6 坑 1） */
}
