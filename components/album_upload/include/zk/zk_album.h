/*
 * zk_album.h —— 相册传图（手机 → 面板）业务接线层（可复用组件）
 *
 * 是什么：把「面板上显示小程序码 → 手机扫码 → 同局域网把照片/视频传进面板 → 落盘 → 通知业务」
 *   这一整套**业务口径**收成一个 API 面（zk::album::Uploader）。
 *
 * 不是什么：**传输本体不在这里**。UDP 8899 广播 + TCP 9000 收文件 + 32 KiB 分块 ACK + `.tmp`→rename
 *   全部由 components/mp_transfer/ 负责（本组件**引用它、不复制它**）。本头文件里也不会出现
 *   mp_transfer / base::Task / TransferFileInfo 等类型 —— 想用底层的自己 include 底层头。
 *
 * 三层分工（移植时对号入座）：
 *   ① components/mp_transfer/  —— 协议/网络/落盘（组件的"腿"）
 *   ② 本组件 zk::album         —— 配置、生命周期、回调归一化、二维码内容（URL）、计数（业务接线层）
 *   ③ 目标工程                 —— 读写自己的 prefs（落盘目录/设备名/二维码链接）、UI 显示二维码、刷新列表
 *
 * 二维码口径（2026-09-30 起，只有一条路 + 一个兜底）：**面板上不铺任何二维码位图**，
 *   一律把「链接字符串」交给 easyui 的二维码控件现场生成（`ZKQRCode::loadQRCode`）。
 *   位图 128px / 37 模块 = 3.46 px/模块（非整数）→ 边缘发糊、扫不动；控件生成模块像素对齐。
 *   链接从哪来见 assets/README.md（本仓附 assets/qr_url.txt）。
 *
 * 线程模型（重要，别踩）：
 *   - configure()/start()/stop()/stats()/qrInfo() 等都可以在 UI 线程调；
 *   - 回调 setOnFileAdded / setOnStateChanged **在 mp_transfer 的接收线程里被调**：
 *     只允许「置标志 / 入队列 / 记路径」，禁止在回调里直接动控件、注册注销、起停服务；
 *   - 二维码控件（ZKQRCode::loadQRCode）只能在 UI 线程调，本组件只负责"内容是什么"。
 *
 * 日志：库内日志走 setLogHook（app 模式下 stdout 是 /dev/null，不接出去现场只能靠猜）。
 *
 * 版本：0.1.0（2026-09-30 入库；口径来源见 README「来源与实测」）
 */

#ifndef ZK_ALBUM_H
#define ZK_ALBUM_H

#include <stdint.h>
#include <string>

/* ---------------- 日志钩子 ---------------- */
enum zk_album_log_level {
    ZK_ALBUM_LOG_DEBUG = 0,
    ZK_ALBUM_LOG_WARN  = 1,
    ZK_ALBUM_LOG_ERROR = 2
};
/* msg 只在本回调内有效；user 就是 setLogHook 里传的那个。 */
typedef void (*zk_album_log_fn)(int level, const char *msg, void *user);

namespace zk {
namespace album {

/* ---------------- 统一结果类型（msg 是人话，可直接打日志/回给用户） ---------------- */
struct Result {
    int code;          /* 0 = 成功；非 0 = 失败（见 msg） */
    std::string msg;
    bool ok() const { return code == 0; }
};

/* ---------------- 文件类别（不泄漏底层枚举） ---------------- */
enum FileKind {
    FILE_PHOTO = 0,     /* jpg/jpeg/png/bmp/gif/webp */
    FILE_VIDEO = 1,     /* mp4/avi/mkv/mov/3gp/ts/flv */
    FILE_OTHER = 2      /* 其它扩展名；**本组件只收不解析媒体** */
};

struct FileInfo {
    std::string path;      /* 落盘绝对路径 */
    std::string name;      /* 文件名（UTF-8） */
    uint64_t size;         /* 字节 */
    long mtime;            /* 修改时间（秒） */
    int kind;              /* FileKind */
};

struct Stats {
    int photos;
    int videos;
};

/* ---------------- 二维码内容来源（一条路 + 一个兜底；口径见 assets/README.md） ----------------
 * ① QR_FROM_CONFIG            用配置给的链接（Config::qr_url = 「扫普通链接二维码打开小程序」链接）
 * ② QR_LOCAL_UPLOAD_FALLBACK  qr_url 为空 → 本机上传地址兜底 http://<ip>:<port>/upload（联调保底）
 * 两种情况的处理方式**完全一样**：把 content 交给控件现场生成。AppID / 链接**一律配置项，不许写死**。
 */
enum QrMode {
    QR_FROM_CONFIG            = 0,
    QR_LOCAL_UPLOAD_FALLBACK  = 1
};

struct QrInfo {
    int mode;              /* QrMode：内容是从配置来的，还是本机地址兜底 */
    std::string content;   /* 要喂给 ZKQRCode::loadQRCode(content) 的 URL；**永远非空**（兜底也在） */
    std::string local_url; /* 本机上传地址 http://<ip>:<port>/upload（调试/提示用；兜底时 == content） */
};

/* ---------------- 配置（默认值安全：不传参也能跑） ---------------- */
struct Config {
    Config();

    std::string save_dir;      /* 落盘目录，**末尾必须带 '/'**；默认 "/mnt/sdnand/album/"。
                                * ⚠️ 真正写盘的是 mp_transfer 的编译期宏（原工程 config.h 的 MP_PATH /
                                *    移植工程 mp_config.h 的 MP_PATH）—— 必须与这里**一致**；
                                *    本组件在回调里核对前缀，不一致会明确报错（可诊断，不静默）。 */
    std::string device_name;   /* UDP 广播显示名（小程序端看到）；空 → mp_transfer 用 "Frame" */
    std::string owner;         /* mp_transfer 的 retain/release owner（多页共用时区分持有者） */
    int listen_port;           /* 监听端口，协议固定 9000（改了两端要一起改） */

    std::string qr_url;        /* 现场生成二维码的内容（扫普通链接二维码打开小程序，如 "https://mp.weixin.qq.com/a/~...~~"）；
                                * 空 → 兜底本机上传地址。**组件不带任何默认链接**：由部署方从 prefs 读出来灌进来
                                * （本仓 assets/qr_url.txt 只是给部署方填配置用的示例值，见 assets/README.md）。 */
    std::string mp_app_id;     /* 微信小程序 AppID：**仅记录/业务用**，不参与本机生成二维码 */

    bool start_on_configure;   /* configure() 后自动 start()；默认 true */
};

/* ---------------- 回调（都在 mp_transfer 接收线程里被调；快返回） ---------------- */
typedef void (*FileAddedFn)(const FileInfo &info, void *user);
typedef void (*StateChangedFn)(bool peer_connected, void *user);
/* 本机 IP 提供者：兜底二维码要拼 http://<ip>:9000/upload；不设 → 用 "0.0.0.0" 并 WARN */
typedef std::string (*LocalIpFn)(void *user);

class Uploader {
public:
    static Uploader &instance();

    /* 配置（可重复调；落盘目录不存在时按需创建）。成功后默认自动 start()（可用 start_on_configure 关掉）。 */
    Result configure(const Config &cfg);
    const Config &config() const;

    /* 启动/停止接收（内部 = mp_transfer 的 retain/release；幂等）。
     * start() 返回成功 ≠ 已经 listen 成功（底层任务异步），用 peerConnected()/日志确认。 */
    Result start();
    Result stop();
    bool running() const;

    /* 手机是否已连上（正在收文件）—— 页面提示 / 呼吸灯 vs 帧动画就靠它 */
    bool peerConnected() const;

    void setOnFileAdded(FileAddedFn fn, void *user);
    void setOnStateChanged(StateChangedFn fn, void *user);
    void setLogHook(zk_album_log_fn fn, void *user);
    void setLocalIpProvider(LocalIpFn fn, void *user);

    /* 重扫落盘目录（清掉残留 .tmp 由 mp_transfer 负责；这里只统计），返回是否扫成功 */
    Result refresh();
    Stats stats() const;

    /* 最近一次错误（人话，可直接显示/打日志） */
    std::string lastError() const;

    /* ---------------- 二维码 ---------------- */
    /* 算出「现在该喂给控件的链接」：qr_url 非空 → QR_FROM_CONFIG；空 → QR_LOCAL_UPLOAD_FALLBACK。
     * **即时计算、组件内不缓存**：内容变了才需重新 loadQRCode，由调用方比对 QrInfo::content
     * （业务侧那份"已 load 的内容"缓存在页面销毁时必须清，见 README §6 坑 1）。
     * 两种 mode 的 UI 处理完全一样：ZKQRCode::loadQRCode(qr.content.c_str())。 */
    QrInfo qrInfo() const;
    std::string localUploadUrl() const;             /* http://<ip>:<端口>/upload（兜底内容） */
    void setQrUrl(const std::string &url);          /* 由业务从自己的 prefs 读出来后灌进来（空 → 兜底） */

private:
    Uploader();
    Uploader(const Uploader &);
    Uploader &operator=(const Uploader &);
    ~Uploader();

    struct Impl;
    Impl *mImpl;
};

} /* namespace album */
} /* namespace zk */

#endif /* ZK_ALBUM_H */
