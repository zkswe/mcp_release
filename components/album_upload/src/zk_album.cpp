/*
 * zk_album.cpp —— zk::album::Uploader 实现（相册传图业务接线层）
 *
 * 依赖两个"邻居"（都是**引用**，不是复制）：
 *   ① components/mp_transfer/  —— UDP 8899 广播 + TCP 9000 收文件 + 分块 ACK + .tmp→rename 落盘
 *   ② easyui 的 StoragePreferences（**只在目标工程侧**用：本组件不认识 prefs，配置由调用方灌进来）
 *
 * 本文件刻意**不含**任何 UI / 项目私有类型：UI 接线看 example/flythings_wiring.cc。
 *
 * 移植注意：
 *   - 若目标平台没有 base::Task（mp_transfer 的基类），照 mp_transfer/README「怎么用」第 2 条
 *     把 mp_transfer 换成项目自己的后台线程 —— 本组件只依赖
 *     MpTransferRuntimeCoordinator / TcpReceiveTask::TcpReceiveListener / TransferFileInfo 三个符号。
 *   - mp_transfer 的**落盘目录是编译期宏**（原工程 config.h 的 MP_PATH / 移植工程 mp_config.h 的 MP_PATH）。
 *     本组件无法在编译期读到它，于是：start() 打印期望目录，回调里核对文件前缀，不一致 → WARN（明说不静默）。
 */

#include "zk/zk_album.h"

#include <ctype.h>
#include <dirent.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include <algorithm>
#include <mutex>
#include <string>
#include <vector>

/* ── 传输本体：引用 components/mp_transfer（工程里通常放在 src/mp_transfer/ 与 src/system/） ── */
#include "mp_transfer/runtime_coordinator.h"
#include "mp_transfer/tcp_receive.h"
#include "system/transfer_type_and_data.h"

namespace zk {
namespace album {

/* ============================ 内部工具 ============================ */

namespace {

const int kProtocolPort = 9000;                 /* 协议固定：小程序侧写死 9000 */
const uint32_t kMaxFileSize = 500u * 1024u * 1024u;   /* 协议上限 500 MiB */
const int kTcpStateReady = 1;                   /* mp_transfer: 1=有客户端连上, 0=断开 */

bool endsWithSlash(const std::string &s) {
    return !s.empty() && s[s.size() - 1] == '/';
}

bool exists(const std::string &path) {
    if (path.empty()) return false;
    struct stat st;
    return stat(path.c_str(), &st) == 0;
}

/* 递归建目录（不依赖 base::mkdirs，纯 POSIX） */
bool ensureDir(const std::string &path) {
    if (path.empty()) return false;
    if (exists(path)) return true;
    std::string cur;
    for (size_t i = 0; i < path.size(); ++i) {
        cur += path[i];
        if (path[i] == '/' && cur.size() > 1) {
            mkdir(cur.c_str(), 0777);   /* 失败不致命（并发/已存在），最后统一判断 */
        }
    }
    mkdir(path.c_str(), 0777);
    return exists(path);
}

bool dirWritable(const std::string &path) {
    if (!exists(path)) return false;
    return access(path.c_str(), W_OK) == 0;
}

int kindOfName(const std::string &name) {
    size_t dot = name.find_last_of('.');
    std::string ext = (dot == std::string::npos) ? "" : name.substr(dot + 1);
    for (size_t i = 0; i < ext.size(); ++i) ext[i] = (char)tolower((unsigned char)ext[i]);
    static const char *kPhoto[] = { "jpg", "jpeg", "png", "bmp", "gif", "webp" };
    static const char *kVideo[] = { "mp4", "avi", "mkv", "mov", "3gp", "ts", "flv" };
    for (size_t i = 0; i < sizeof(kPhoto) / sizeof(kPhoto[0]); ++i) if (ext == kPhoto[i]) return FILE_PHOTO;
    for (size_t i = 0; i < sizeof(kVideo) / sizeof(kVideo[0]); ++i) if (ext == kVideo[i]) return FILE_VIDEO;
    return FILE_OTHER;
}

bool isTmpName(const std::string &name) {
    return name.size() > 4 && name.compare(name.size() - 4, 4, ".tmp") == 0;
}

} /* namespace */

/* ============================ Config 默认值 ============================ */

Config::Config()
    : save_dir("/mnt/sdnand/album/"),
      device_name(""),
      owner("album_upload"),
      listen_port(kProtocolPort),
      start_on_configure(true) {
}

/* ============================ 实现体 ============================ */

struct Uploader::Impl {
    mutable std::mutex mMutex;
    Config mCfg;

    bool mRunning;
    bool mWarnedNoIp;
    bool mWarnedQrFallback;
    std::string mLastError;
    Stats mStats;

    FileAddedFn mFileFn;
    void *mFileUser;
    StateChangedFn mStateFn;
    void *mStateUser;
    zk_album_log_fn mLogFn;
    void *mLogUser;
    LocalIpFn mIpFn;
    void *mIpUser;

    /* mp_transfer 的监听适配器：把底层回调归一化成我们的回调 */
    class Bridge : public TcpReceiveTask::TcpReceiveListener {
    public:
        explicit Bridge(Impl *o) : mOwner(o) {}

        void onScanFinished(const std::vector<TransferFileInfo> &fileList) {
            /* 扫描结果只用来更新计数（业务侧刷新列表自己 refresh()） */
            Stats st;
            st.photos = st.videos = 0;
            for (size_t i = 0; i < fileList.size(); ++i) {
                int k = kindOfName(fileList[i].name);
                if (k == FILE_PHOTO) st.photos++;
                else if (k == FILE_VIDEO) st.videos++;
            }
            mOwner->setStats(st);
        }

        void onFileAdded(const TransferFileInfo &info) {
            /* ⚠️ 本回调在 mp_transfer 接收线程里 → 只做轻活 */
            FileInfo out;
            out.path = info.path;
            out.name = info.name;
            out.size = info.size;
            out.mtime = info.last_modified;
            out.kind = kindOfName(info.name);
            mOwner->checkDirPrefix(info.path);
            FileAddedFn fn = 0;
            void *user = 0;
            {
                std::lock_guard<std::mutex> lk(mOwner->mMutex);
                fn = mOwner->mFileFn;
                user = mOwner->mFileUser;
            }
            if (fn != 0) fn(out, user);
        }

        void onTcpStateChanged(int state) {
            StateChangedFn fn = 0;
            void *user = 0;
            {
                std::lock_guard<std::mutex> lk(mOwner->mMutex);
                fn = mOwner->mStateFn;
                user = mOwner->mStateUser;
            }
            if (fn != 0) fn(state == kTcpStateReady, user);
        }

    private:
        Impl *mOwner;
    };

    Bridge *mBridge;

    Impl() : mRunning(false), mWarnedNoIp(false), mWarnedQrFallback(false),
             mFileFn(0), mFileUser(0), mStateFn(0), mStateUser(0),
             mLogFn(0), mLogUser(0), mIpFn(0), mIpUser(0), mBridge(0) {}

    ~Impl() {
        if (mBridge != 0) {
            TcpReceiveTask::instance().removeListener(mBridge);
            delete mBridge;
            mBridge = 0;
        }
    }

    void log(int level, const char *fmt, ...) {
        char buf[512];
        va_list ap;
        va_start(ap, fmt);
        vsnprintf(buf, sizeof(buf), fmt, ap);
        va_end(ap);
        zk_album_log_fn fn = 0;
        void *user = 0;
        {
            std::lock_guard<std::mutex> lk(mMutex);
            fn = mLogFn;
            user = mLogUser;
        }
        if (fn != 0) fn(level, buf, user);
    }

    void setError(const std::string &msg) {
        std::lock_guard<std::mutex> lk(mMutex);
        mLastError = msg;
    }

    void setStats(const Stats &st) {
        std::lock_guard<std::mutex> lk(mMutex);
        mStats = st;
    }

    /* 可诊断：文件没落在配置目录 → 明确说是谁的锅（mp_transfer 的编译期 MP_PATH） */
    void checkDirPrefix(const std::string &path) {
        std::string dir;
        {
            std::lock_guard<std::mutex> lk(mMutex);
            dir = mCfg.save_dir;
        }
        if (dir.empty()) return;
        if (path.compare(0, dir.size(), dir) != 0) {
            log(ZK_ALBUM_LOG_WARN,
                "落盘目录与配置不一致：文件落在 %s，配置的是 %s。"
                "请检查 mp_transfer 的编译期宏 MP_PATH（原工程 config.h / 移植工程 mp_config.h）是否与 save_dir 相同。",
                path.c_str(), dir.c_str());
        }
    }

    Result scan() {
        std::string dir;
        {
            std::lock_guard<std::mutex> lk(mMutex);
            dir = mCfg.save_dir;
        }
        if (dir.empty()) return makeResult(-1, "落盘目录为空：configure() 里给 save_dir（末尾带 '/'）");
        if (!ensureDir(dir)) return makeResult(-2, "落盘目录不可用：" + dir + "（检查 TF 卡/分区是否挂载）");
        DIR *d = opendir(dir.c_str());
        if (d == 0) return makeResult(-3, "打不开落盘目录：" + dir);
        Stats st;
        st.photos = st.videos = 0;
        struct dirent *e = 0;
        while ((e = readdir(d)) != 0) {
            if (e->d_name[0] == '.') continue;
            if (isTmpName(e->d_name)) continue;     /* 残留 .tmp 由 mp_transfer 清理，不计数 */
            int k = kindOfName(e->d_name);
            if (k == FILE_PHOTO) st.photos++;
            else if (k == FILE_VIDEO) st.videos++;
        }
        closedir(d);
        setStats(st);
        return makeResult(0, "扫描完成");
    }

    static Result makeResult(int code, const std::string &msg) {
        Result r;
        r.code = code;
        r.msg = msg;
        return r;
    }

    std::string localUploadUrl() {
        std::string ip;
        LocalIpFn fn = 0;
        void *user = 0;
        int port = kProtocolPort;
        {
            std::lock_guard<std::mutex> lk(mMutex);
            fn = mIpFn;
            user = mIpUser;
            port = mCfg.listen_port;
        }
        if (fn != 0) ip = fn(user);
        if (ip.empty()) {
            if (!mWarnedNoIp) {
                mWarnedNoIp = true;
                log(ZK_ALBUM_LOG_WARN,
                    "取不到本机 IP（未设 setLocalIpProvider 或返回空）→ 兜底二维码用 0.0.0.0。"
                    "接线层应传工程里的本机 IP（如 NetKeeper_localIp()）。");
            }
            ip = "0.0.0.0";
        }
        char buf[160];
        snprintf(buf, sizeof(buf), "http://%s:%d/upload", ip.c_str(), port);
        return std::string(buf);
    }

    /* 一条路 + 一个兜底：两条路的**处理方式完全一样**（都是 loadQRCode(content)），
     * mode 只是告诉业务"这串内容是从配置来的，还是本机地址顶上的"。 */
    QrInfo qrInfo() {
        std::string cfgUrl;
        {
            std::lock_guard<std::mutex> lk(mMutex);
            cfgUrl = mCfg.qr_url;
        }
        QrInfo out;
        out.local_url = localUploadUrl();

        if (!cfgUrl.empty()) {
            out.mode = QR_FROM_CONFIG;
            out.content = cfgUrl;
            return out;
        }

        /* 本机上传地址兜底（联调保底，不是给终端用户的入口）；**只提醒一次**，不在定时器里刷屏
         * （log() 自己会取 mMutex，所以先出锁再打） */
        out.mode = QR_LOCAL_UPLOAD_FALLBACK;
        out.content = out.local_url;
        bool firstWarn = false;
        {
            std::lock_guard<std::mutex> lk(mMutex);
            if (!mWarnedQrFallback) {
                mWarnedQrFallback = true;
                firstWarn = true;
            }
        }
        if (firstWarn) {
            log(ZK_ALBUM_LOG_WARN,
                "qr_url 为空 → 二维码退回本机上传地址兜底 %s。"
                "正式部署应从 prefs 灌入小程序链接（见 assets/README.md）。",
                out.content.c_str());
        }
        return out;
    }
};

/* ============================ 单例 ============================ */

Uploader &Uploader::instance() {
    static Uploader inst;
    return inst;
}

Uploader::Uploader() : mImpl(new Impl()) {}
Uploader::~Uploader() { delete mImpl; mImpl = 0; }
Uploader::Uploader(const Uploader &) : mImpl(0) {}

/* ============================ 配置 ============================ */

Result Uploader::configure(const Config &cfg) {
    Config c = cfg;
    if (c.save_dir.empty()) {
        mImpl->setError("save_dir 为空");
        return Impl::makeResult(-1, "落盘目录为空：给 save_dir（建议 '/mnt/sdnand/album/' 这类已挂载可写目录）");
    }
    if (!endsWithSlash(c.save_dir)) {
        c.save_dir += "/";                       /* mp_transfer 直接拼文件名，不补斜杠 */
        mImpl->log(ZK_ALBUM_LOG_WARN, "save_dir 末尾没带 '/'，已自动补上：%s", c.save_dir.c_str());
    }
    if (!ensureDir(c.save_dir) || !dirWritable(c.save_dir)) {
        std::string msg = "落盘目录不可写：" + c.save_dir + "（TF 卡/分区没挂载，或只读）";
        mImpl->setError(msg);
        return Impl::makeResult(-2, msg);
    }
    if (c.listen_port != kProtocolPort) {
        mImpl->log(ZK_ALBUM_LOG_WARN,
                   "listen_port=%d ≠ 协议固定 9000：小程序侧写死 9000，改了收不到文件。", c.listen_port);
    }
    if (c.owner.empty()) c.owner = "album_upload";

    {
        std::lock_guard<std::mutex> lk(mImpl->mMutex);
        mImpl->mCfg = c;
        mImpl->mWarnedQrFallback = false;        /* 重新配置 → 允许再提醒一次兜底 */
    }

    mImpl->log(ZK_ALBUM_LOG_DEBUG,
               "configure: dir=%s dev='%s' port=%d qr_url=%s appid=%s",
               c.save_dir.c_str(), c.device_name.c_str(), c.listen_port,
               c.qr_url.empty() ? "(空→兜底本机地址)" : c.qr_url.c_str(),
               c.mp_app_id.empty() ? "(空)" : "(已配)");

    if (c.start_on_configure) return start();
    return Impl::makeResult(0, "配置完成（未启动；start_on_configure=false）");
}

const Config &Uploader::config() const { return mImpl->mCfg; }

/* ============================ 生命周期 ============================ */

Result Uploader::start() {
    if (mImpl->mRunning) {
        /* 幂等；但设备名可能变了 → 名字变化时 mp_transfer 内部会重启广播 */
        MpTransferRuntimeCoordinator::instance().retain(mImpl->mCfg.owner, mImpl->mCfg.device_name);
        return Impl::makeResult(0, "已在运行（设备名若有变化已同步）");
    }
    if (mImpl->mCfg.save_dir.empty()) {
        return Impl::makeResult(-1, "未配置：先 configure()");
    }
    if (mImpl->mBridge == 0) mImpl->mBridge = new Impl::Bridge(mImpl);
    TcpReceiveTask::instance().addListener(mImpl->mBridge);
    MpTransferRuntimeCoordinator::instance().retain(mImpl->mCfg.owner, mImpl->mCfg.device_name);
    mImpl->mRunning = true;
    /* 启动接口返回 ≠ 已 listen 成功（底层 listen 在任务线程里做）→ 日志里确认 */
    mImpl->log(ZK_ALBUM_LOG_DEBUG,
               "start: 广播 UDP 8899 (zkswe:%s) + 监听 TCP %d（单文件上限 %u B），期望落盘 %s",
               mImpl->mCfg.device_name.empty() ? "Frame" : mImpl->mCfg.device_name.c_str(),
               mImpl->mCfg.listen_port, (unsigned)kMaxFileSize, mImpl->mCfg.save_dir.c_str());
    return Impl::makeResult(0, "已启动接收（UDP 8899 广播 + TCP 9000）");
}

Result Uploader::stop() {
    if (!mImpl->mRunning) return Impl::makeResult(0, "未在运行");
    MpTransferRuntimeCoordinator::instance().release(mImpl->mCfg.owner);
    if (mImpl->mBridge != 0) {
        TcpReceiveTask::instance().removeListener(mImpl->mBridge);
    }
    mImpl->mRunning = false;
    mImpl->log(ZK_ALBUM_LOG_DEBUG, "stop: 广播/监听已停（小程序侧将看不到本机）");
    return Impl::makeResult(0, "已停止接收");
}

bool Uploader::running() const { return mImpl->mRunning; }

bool Uploader::peerConnected() const {
    return TcpReceiveTask::instance().isClientConnected();
}

/* ============================ 回调 / 日志 ============================ */

void Uploader::setOnFileAdded(FileAddedFn fn, void *user) {
    std::lock_guard<std::mutex> lk(mImpl->mMutex);
    mImpl->mFileFn = fn;
    mImpl->mFileUser = user;
}

void Uploader::setOnStateChanged(StateChangedFn fn, void *user) {
    std::lock_guard<std::mutex> lk(mImpl->mMutex);
    mImpl->mStateFn = fn;
    mImpl->mStateUser = user;
}

void Uploader::setLogHook(zk_album_log_fn fn, void *user) {
    std::lock_guard<std::mutex> lk(mImpl->mMutex);
    mImpl->mLogFn = fn;
    mImpl->mLogUser = user;
}

void Uploader::setLocalIpProvider(LocalIpFn fn, void *user) {
    std::lock_guard<std::mutex> lk(mImpl->mMutex);
    mImpl->mIpFn = fn;
    mImpl->mIpUser = user;
}

/* ============================ 目录 / 计数 ============================ */

Result Uploader::refresh() {
    Result r = mImpl->scan();
    if (!r.ok()) mImpl->setError(r.msg);
    return r;
}

Stats Uploader::stats() const {
    std::lock_guard<std::mutex> lk(mImpl->mMutex);
    return mImpl->mStats;
}

std::string Uploader::lastError() const {
    std::lock_guard<std::mutex> lk(mImpl->mMutex);
    return mImpl->mLastError;
}

/* ============================ 二维码 ============================ */

QrInfo Uploader::qrInfo() const {
    /* 即时计算（不缓存内容）：内容变了才需重新 loadQRCode，由调用方比对 QrInfo::content */
    return mImpl->qrInfo();
}

std::string Uploader::localUploadUrl() const { return mImpl->localUploadUrl(); }

void Uploader::setQrUrl(const std::string &url) {
    std::lock_guard<std::mutex> lk(mImpl->mMutex);
    mImpl->mCfg.qr_url = url;
    /* 内容变了 → 允许重新提醒一次兜底 */
    if (url.empty()) mImpl->mWarnedQrFallback = false;
}

} /* namespace album */
} /* namespace zk */
