/*
 * flythings_wiring.cc —— FlyThings/EasyUI 工程侧接线样板（不是组件本体，剪贴用）
 *
 * 目标工程里的三件事这里都有：
 *   ① 从自己的 prefs 读配置（键名语义来自 SmartPanel_HA 的 ConfigStore，**只取键名语义**）
 *   ② 二维码三态落 UI：远端码图（Image 层）/ 控件现场生成（ZKQRCode）/ 本机上传地址兜底
 *   ③ 生命周期：onUI_init / onUI_show / onUI_hide / onUI_quit / onUI_Timer + 上传完成刷新
 *
 * ⚠️ 本文件**不能单独编译**（要工程里的 easyui 头 + 生成代码 mXxxPtr）：
 *    它是接线形状，判据 = 工程 `fun build` 通过 + 真机扫码（见 ../platforms.md）。
 *    组件本体（include/ + src/）的判据 = PC 侧语法自检（见 ../README.md「验证」）。
 */

#include "zk/zk_album.h"

#include "utils/Log.h"                          /* 工程自有日志 */
#include "storage/StoragePreferences.h"         /* easyui 的 prefs（/data 键值存储） */
#include "control/ZKQRCode.h"                   /* 二维码控件（json 里类型 = qrcode） */
#include "control/ZKTextView.h"                  /* 远端码图图层在 json 里是 textview（带 backgroundPic） */
#include "entry/EasyUIContext.h"                /* EASYUICONTEXT（setScreensaverEnable 等） */
#include "system/NetKeeper.h"                   /* NetKeeper_localIp() —— 工程自有实现 */
#include <http/downloader.h>                    /* $(curl-cxx)/include/http/... */

#include <string>

/* 生成代码里的控件（点号：工程 ui/*.json 的 caption） */
extern ZKQRCode *mQrcodeAlPtr;          /* caption: QrcodeAl（json 类型 qrcode，盒 128×128）—— 控件现场生成用 */
/* ⚠️ 远端码图图层在 json 里是 textview（带 backgroundPic），所以生成的是 ZKTextView*；
 *    它与 qrcode 控件**同盒重叠**（来源工程都在 (176,146) 128×128），靠 setVisible 二选一。 */
extern ZKTextView *mImageAlQrRemotePtr; /* caption: ImageAlQrRemote —— 远端小程序码图用 */

/* ── ① 配置键名语义（**不要写死 AppID / 链接**：部署方在他的 prefs 里配） ── */
static const char *kKeyDevName   = "sp_dev_name";     /* 设备名（广播名） */
static const char *kKeyAlbumMode = "sp_album_mode";   /* 1=相册模式开启（默认）0=已结束 */
static const char *kKeyQrUrl     = "sp_qr_url";       /* 现场生成二维码的内容（扫普通链接打开小程序） */
static const char *kKeyQrImgUrl  = "sp_qr_img_url";   /* 远端微信小程序码图 URL（控件编不出来，只能下载显示） */
static const char *kKeyMpAppId   = "sp_mp_appid";     /* 小程序 AppID（仅记录/业务用） */

static const char *kOwner = "albumActivity";
static std::string sQrShown;            /* ⚠️ 已 load 的二维码内容（QR 重算很贵，变了才重算） */
static volatile bool sNeedRefresh = false;

/* ── ② 本机 IP：工程自己的取法（wlan0 → eth0 → 其它非回环网卡） ── */
static std::string localIp(void *user) {
    (void)user;
    return NetKeeper_localIp();         /* 工程里已有的实现；没有就自己 getifaddrs 走网卡候选链 */
}

/* ── ③ 上传完成 / 连接状态：**在接收线程里** → 只置标志 ── */
static void onFileAdded(const zk::album::FileInfo &info, void *user) {
    (void)user;
    LOGD("album: file added %s (%llu B, kind=%d)", info.path.c_str(),
         (unsigned long long)info.size, info.kind);
    sNeedRefresh = true;                /* UI 定时器里消费（别在这里动控件） */
}

static void onStateChanged(bool connected, void *user) {
    (void)user;
    LOGD("album: peer %s", connected ? "connected" : "disconnected");
    sNeedRefresh = true;
}

/* ── ④ 远端小程序码图：用工程下载器下到 image_path（组件不管网络） ── */
static void ensureRemoteQrImage() {
    zk::album::Uploader &up = zk::album::Uploader::instance();
    zk::album::QrInfo qr = up.qrInfo();
    if (qr.mode == zk::album::QR_REMOTE_IMAGE || qr.image_url.empty()) return;
    static std::string sTrying;
    if (sTrying == qr.image_url) return;       /* 同一个 URL 不反复发起 */
    sTrying = qr.image_url;

    http::Downloader::Task t;
    t.source = qr.image_url;
    t.target = qr.image_path;                  /* 建议 "/mnt/sdnand/qr_code.png" 这类小文件 */
    t.retry_max = 2;
    t.result = [](const http::Downloader::Task &task, bool success) {
        (void)task;
        zk::album::Uploader::instance().notifyQrImageDownloaded(success);  /* 只置标志 */
        sNeedRefresh = true;                   /* 下一拍 UI 定时器再把图贴上去 */
    };
    http::Downloader::instance().add(t);
    LOGD("album: request remote qr image %s -> %s", qr.image_url.c_str(), qr.image_path.c_str());
}

/* ── ⑤ 二维码落 UI（唯一允许动控件的地方：UI 线程） ── */
static void refreshQrcode() {
    zk::album::Uploader &up = zk::album::Uploader::instance();
    zk::album::QrInfo qr = up.qrInfo();

    if (qr.mode == zk::album::QR_REMOTE_IMAGE) {
        /* 微信原生小程序码：只能远端下载后当图片显示 */
        if (mQrcodeAlPtr != NULL) mQrcodeAlPtr->setVisible(false);
        if (mImageAlQrRemotePtr != NULL) {
            mImageAlQrRemotePtr->setBackgroundPic(qr.image_path.c_str());
            mImageAlQrRemotePtr->setVisible(true);
        }
        return;
    }

    if (mImageAlQrRemotePtr != NULL) mImageAlQrRemotePtr->setVisible(false);
    if (mQrcodeAlPtr != NULL) {
        mQrcodeAlPtr->setVisible(true);
        if (qr.content != sQrShown) {          /* 内容变了才重算（QR 生成很贵） */
            mQrcodeAlPtr->loadQRCode(qr.content.c_str());
            sQrShown = qr.content;
        }
    }
    LOGD("album: qr(%d) -> %s", qr.mode, qr.content.c_str());
    ensureRemoteQrImage();                     /* 配了远端码图就顺手拉一份，拉到再切第一态 */
}

/* ── ⑥ 页面状态 + 计数（1s 刷新就够；别跟 120ms 的动画定时器混） ── */
static bool albumModeEnabled() {
    return StoragePreferences::getInt(kKeyAlbumMode, 1) != 0;
}

static void refreshUi() {
    bool on = albumModeEnabled();
    bool connected = on && zk::album::Uploader::instance().peerConnected();
    zk::album::Stats st = zk::album::Uploader::instance().stats();

    /* 标题/副行/呼吸灯 vs 帧动画/计数 —— 按你的布局控件逐个 set */
    LOGD("album: mode=%d connected=%d photos=%d videos=%d", (int)on, (int)connected,
         st.photos, st.videos);
}

/* ── ⑦ 生命周期 ── */
static void albumPageInit() {
    zk::album::Uploader &up = zk::album::Uploader::instance();
    up.setOnFileAdded(onFileAdded, NULL);
    up.setOnStateChanged(onStateChanged, NULL);
    up.setLocalIpProvider(localIp, NULL);

    zk::album::Config cfg;
    cfg.save_dir    = "/mnt/sdnand/album/";   /* ⚠️ 与 mp_transfer 的 MP_PATH 一致，末尾带 '/' */
    cfg.device_name = StoragePreferences::getString(kKeyDevName, "Panel");  /* 空 → "Frame" */
    cfg.owner       = kOwner;
    cfg.qr_url      = StoragePreferences::getString(kKeyQrUrl, "");         /* 空 → 本机地址兜底 */
    cfg.qr_image_url= StoragePreferences::getString(kKeyQrImgUrl, "");
    cfg.qr_image_local_path = "/mnt/sdnand/qr_code.png";
    cfg.mp_app_id   = StoragePreferences::getString(kKeyMpAppId, "");
    cfg.start_on_configure = false;           /* 是否开启由相册模式开关决定，见下 */

    zk::album::Result r = up.configure(cfg);
    if (!r.ok()) LOGE("album: configure failed: %s", r.msg.c_str());

    if (albumModeEnabled()) {
        zk::album::Result s = up.start();      /* 开：UDP 广播 + 监听 9000 */
        LOGD("album: start -> %s (%s)", s.ok() ? "OK" : "FAIL", s.msg.c_str());
    }
    up.refresh();                              /* 进页重扫落盘目录 */
    refreshQrcode();
    refreshUi();
}

static void albumPageShow() {
    /* 子页不进屏保（真源口径：setScreensaverEnable(false)） */
    EASYUICONTEXT->setScreensaverEnable(false);
    if (albumModeEnabled()) zk::album::Uploader::instance().start();
    zk::album::Uploader::instance().refresh();
    refreshQrcode();
    refreshUi();
}

static void albumPageHide() {
    /* 离开页面就停传输（省电；小程序侧会显示设备不可见） */
    zk::album::Uploader::instance().stop();
}

static void albumPageQuit() {
    sQrShown.clear();      /* ⚠️ 缓存与控件同生共死：不清 → 重进页二维码空白（真机复现过） */
    zk::album::Uploader::instance().resetQrCache();
    zk::album::Uploader::instance().stop();
}

/* 定时器（1s）：消费 sNeedRefresh → 刷 UI；二维码内容变了才 loadQRCode */
static bool albumPageTimer(int id) {
    if (id == 0) {
        if (sNeedRefresh) {
            sNeedRefresh = false;
            zk::album::Uploader::instance().refresh();
            refreshQrcode();       /* 远端码图下载完成 → 这一拍切到第一态 */
            refreshUi();
        }
    }
    return true;
}

/* 结束/重新开启相册模式按钮 */
static void albumToggleMode() {
    bool on = albumModeEnabled();
    StoragePreferences::putInt(kKeyAlbumMode, on ? 0 : 1);
    if (on) zk::album::Uploader::instance().stop();
    else    zk::album::Uploader::instance().start();
    refreshUi();
}
