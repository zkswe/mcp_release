/*
 * zkble_common.h —— 门面公共层（内部头，不对外）
 *
 * 两个后端（btstack / gatt）共用，只放**与底层协议无关**的东西：
 *   · 日志钩子（setLogHook + ZKBLE_LOG）
 *   · 小工具（单调时钟 / 文件 / hex / uuid 归一 / 属性读写 / 工具路径兜底）
 *   · 广播数据（AD/EIR）解析 + 扫描过滤（name_prefix / addr_prefix / service_uuid）
 *   · 设备缓存 DeviceCache（线程安全、按 id 去重更新）
 *   · 回调注册表 + fire*（两个后端都往这里投事件）
 *   · 同步等待槽 Waiter（业务线程带超时等后端线程的结果）
 *   · 公共 API 的 inline 实现（version / setLogHook / on* / offAll）
 *
 * 协议相关（btstack 的 run loop、gatt 的 mainloop 等）一律留在各后端文件里。
 */
#pragma once

#include "zk/zk_ble.h"
#include "zkble_backend.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <ctype.h>
#include <pthread.h>
#include <sys/stat.h>

#include <algorithm>
#include <string>
#include <vector>

#define ZKBLE_VERSION "0.2.0"

#define ZKBLE_LOG(fmt, ...) ::zk::ble::internal::logf(fmt, ##__VA_ARGS__)

namespace zk {
namespace ble {

// ---------------------------------------------------------------- 公共实现细节
namespace internal {

// ---- 日志
inline std::function<void(const std::string&)>& logHookRef() {
    static std::function<void(const std::string&)> h;
    return h;
}

inline void logf(const char* fmt, ...) {
    char buf[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    std::function<void(const std::string&)>& h = logHookRef();
    if (h) {
        h(std::string(buf));
    } else {
        printf("[zkble] %s\n", buf);
    }
}

// ---- 时间
inline uint32_t monotonicMs() {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t)((uint32_t)ts.tv_sec * 1000u + (uint32_t)ts.tv_nsec / 1000000u);
}

// ---- 文件 / 命令
inline bool fileExists(const char* path) {
    return path && access(path, F_OK) == 0;
}

inline std::string bytesToHex(const uint8_t* data, size_t len) {
    static const char* kHex = "0123456789abcdef";
    std::string out;
    out.reserve(len * 2);
    for (size_t i = 0; i < len; i++) {
        out.push_back(kHex[(data[i] >> 4) & 0x0F]);
        out.push_back(kHex[data[i] & 0x0F]);
    }
    return out;
}

// 把 "fcd2"（16 位）或 32 字符 128 位 uuid 统一成小写无横线形式
inline std::string normalizeUuid(const std::string& in) {
    std::string s;
    for (size_t i = 0; i < in.size(); i++) {
        char c = in[i];
        if (c == '-' || c == ':' || c == ' ') continue;
        if (c >= 'A' && c <= 'Z') c = (char)(c - 'A' + 'a');
        s.push_back(c);
    }
    return s;
}

// 地址归一：去分隔符、转大写（比较前缀用）
inline std::string normalizeAddr(const std::string& in) {
    std::string s;
    for (size_t i = 0; i < in.size(); i++) {
        char c = in[i];
        if (c == ':' || c == '-' || c == ' ') continue;
        if (c >= 'a' && c <= 'z') c = (char)(c - 'a' + 'A');
        s.push_back(c);
    }
    return s;
}

inline bool startsWith(const std::string& s, const std::string& prefix) {
    if (prefix.size() > s.size()) return false;
    return s.compare(0, prefix.size(), prefix) == 0;
}

// 读系统属性（不依赖 easyui，bin 工程也能用）
inline std::string readProp(const char* key) {
    std::string path = std::string("/data/property/") + key;
    FILE* pf = fopen(path.c_str(), "r");
    if (!pf) return std::string();
    char buf[128] = {0};
    const size_t n = fread(buf, 1, sizeof(buf) - 1, pf);
    fclose(pf);
    if (n == 0) return std::string();
    for (size_t i = 0; i < n; i++) {
        if (buf[i] == '\n' || buf[i] == '\r' || buf[i] == ' ') { buf[i] = '\0'; break; }
    }
    return std::string(buf);
}

// 写系统属性（等价 setprop：AIC 路线的 hciattach 服务就是靠 ctl.start 拉起的）
inline int writeProp(const char* key, const std::string& value) {
    std::string path = std::string("/data/property/") + key;
    FILE* pf = fopen(path.c_str(), "w");
    if (!pf) return -1;
    const int n = (int)fwrite(value.c_str(), 1, value.size(), pf);
    fclose(pf);
    return n > 0 ? 0 : -1;
}

// 工具路径兜底（Z21 整机 /res 是只读 squashfs 且没有 /res/bin，产品化要靠升级包放进 /res/bin）
inline std::string findToolPath(const char* name) {
    static const char* kDirs[] = { "/res/bin", "/data/bin", "/tmp/bin", "/usr/bin", "/bin", NULL };
    for (int i = 0; kDirs[i]; i++) {
        std::string p = std::string(kDirs[i]) + "/" + name;
        if (fileExists(p.c_str())) return p;
    }
    // 都没找到：按第一条给个路径，让调用方看到明确失败
    return std::string("/res/bin/") + name;
}

inline int runTool(const char* tool, const char* args) {
    std::string cmd = findToolPath(tool) + " " + args;
    return system(cmd.c_str());
}

// 按平台探测默认串口（btstack 后端用；gatt 后端走 USB HCI，不需要）
inline std::string defaultUart() {
    static const char* kCandidates[] = { "/dev/ttyS1", "/dev/ttyS2", NULL };  // F133 / V85X 实测
    for (int i = 0; kCandidates[i]; i++) {
        if (fileExists(kCandidates[i])) return std::string(kCandidates[i]);
    }
    return std::string();
}

// ---- 广播数据解析（不依赖任何协议栈）
// 解析 Name（0x08/0x09）与 Service Data（0x16 / 0x15），并回填完整 AD 段 hex
inline void parseAdFields(const uint8_t* ad, uint16_t len,
                          std::string& name, std::string& service_data_hex,
                          std::string& adv_data_hex) {
    adv_data_hex = bytesToHex(ad, len);
    uint16_t off = 0;
    while (off + 1 < len) {
        const uint8_t field_len = ad[off];
        if (field_len == 0) break;                       // 结束
        if (off + field_len + 1 > len) break;            // 越界，忽略残包
        const uint8_t type = ad[off + 1];
        const uint8_t* d = ad + off + 2;
        const uint8_t dlen = (uint8_t)(field_len - 1);
        if (type == 0x08 || type == 0x09) {
            name.assign((const char*)d, dlen);
        } else if ((type == 0x16 || type == 0x15) && dlen >= 2 && service_data_hex.empty()) {
            service_data_hex = bytesToHex(d, dlen);
        }
        off = (uint16_t)(off + field_len + 1);
    }
}

// ---- 扫描过滤
inline bool matchScanFilter(const DeviceInfo& d, const ScanOptions& o) {
    if (!o.name_prefix.empty()) {
        std::string pre = o.name_prefix;
        if (pre.size() >= 2 && pre[0] == 'A' && pre[1] == '#') {
            // 兼容 Sample 的「A#<地址前缀>」语义（其余写法都是名字前缀）
            const std::string ap = normalizeAddr(pre.substr(2));
            if (!startsWith(normalizeAddr(d.id), ap)) return false;
        } else if (!startsWith(d.name, pre)) {
            return false;
        }
    }
    if (!o.addr_prefix.empty()) {
        if (!startsWith(normalizeAddr(d.id), normalizeAddr(o.addr_prefix))) return false;
    }
    if (!o.service_uuid.empty()) {
        // Service Data 前两字节是小端 UUID，hex 里是反序的（FCD2 → "d2fc"）
        const std::string want = normalizeUuid(o.service_uuid);
        if (want.size() >= 4) {
            const std::string head = want.substr(0, 4);
            const std::string le = std::string() + head[2] + head[3] + head[0] + head[1];
            if (d.service_data_hex.compare(0, 4, le) != 0) return false;
        }
    }
    return true;
}

// ---- 设备缓存（扫描结果；两个后端共用）
struct CachedDevice {
    DeviceInfo info;
    uint8_t addr_type = 0;
};

class DeviceCache {
public:
    DeviceCache() { pthread_mutex_init(&mtx_, NULL); }
    ~DeviceCache() { pthread_mutex_destroy(&mtx_); }

    bool upsert(const CachedDevice& cd) {          // 返回 true = 新设备
        lock();
        bool is_new = true;
        for (size_t i = 0; i < v_.size(); i++) {
            if (v_[i].info.id == cd.info.id) { v_[i] = cd; is_new = false; break; }
        }
        if (is_new) v_.push_back(cd);
        unlock();
        return is_new;
    }

    bool find(const std::string& id, CachedDevice& out) {   // 找设备（拿 addr_type 用）
        lock();
        bool found = false;
        for (size_t i = 0; i < v_.size(); i++) {
            if (v_[i].info.id == id) { out = v_[i]; found = true; break; }
        }
        unlock();
        return found;
    }

    void snapshot(std::vector<DeviceInfo>& out) {
        out.clear();
        lock();
        for (size_t i = 0; i < v_.size(); i++) out.push_back(v_[i].info);
        unlock();
    }

    void clear() { lock(); v_.clear(); unlock(); }

    int size() { lock(); const int n = (int)v_.size(); unlock(); return n; }

private:
    void lock() { pthread_mutex_lock(&mtx_); }
    void unlock() { pthread_mutex_unlock(&mtx_); }
    DeviceCache(const DeviceCache&);
    DeviceCache& operator=(const DeviceCache&);

    pthread_mutex_t mtx_;
    std::vector<CachedDevice> v_;
};

// ---- 同步等待槽：后端线程 signal，业务线程带超时 wait
struct Waiter {
    pthread_mutex_t m;
    pthread_cond_t c;
    bool done;
    int status;                 // 0 = OK，其余按调用方约定
    std::string msg;

    Waiter() : done(false), status(0) {
        pthread_mutex_init(&m, NULL);
        pthread_cond_init(&c, NULL);
    }
    void reset() {
        pthread_mutex_lock(&m);
        done = false;
        status = 0;
        msg.clear();
        pthread_mutex_unlock(&m);
    }
    void signal(int st, const std::string& text = std::string()) {
        pthread_mutex_lock(&m);
        done = true;
        status = st;
        msg = text;
        pthread_cond_broadcast(&c);
        pthread_mutex_unlock(&m);
    }
    bool wait(int timeout_ms) {
        struct timespec ts;
        clock_gettime(CLOCK_REALTIME, &ts);
        ts.tv_sec += timeout_ms / 1000;
        ts.tv_nsec += (long)(timeout_ms % 1000) * 1000000L;
        if (ts.tv_nsec >= 1000000000L) {
            ts.tv_sec += 1;
            ts.tv_nsec -= 1000000000L;
        }
        pthread_mutex_lock(&m);
        while (!done) {
            if (pthread_cond_timedwait(&c, &m, &ts) == ETIMEDOUT) break;
        }
        const bool ok = done;
        pthread_mutex_unlock(&m);
        return ok;
    }
};

// ---- 回调注册表（两个后端共用一套；fire* 由后端在事件发生时调）
inline OnAdapterStateChange& cbAdapterRef() { static OnAdapterStateChange cb; return cb; }
inline OnDeviceFound&        cbDeviceRef()  { static OnDeviceFound cb; return cb; }
inline OnConnectionChange&   cbConnRef()    { static OnConnectionChange cb; return cb; }
inline OnValueChange&        cbValueRef()   { static OnValueChange cb; return cb; }
inline OnWriteRequest&       cbWriteRef()   { static OnWriteRequest cb; return cb; }

inline void fireAdapterState(const AdapterState& st) {
    if (cbAdapterRef()) cbAdapterRef()(st);
}
inline void fireDeviceFound(const DeviceInfo& d) {
    if (cbDeviceRef()) cbDeviceRef()(d);
}
inline void fireConnectionChange(const std::string& device_id, bool connected) {
    if (cbConnRef()) cbConnRef()(device_id, connected);
}
inline void fireValueChange(const Value& v) {
    if (cbValueRef()) cbValueRef()(v);
}
inline void fireWriteRequest(const std::string& char_uuid, const std::string& data) {
    if (cbWriteRef()) cbWriteRef()(char_uuid, data);
}

}  // namespace internal

// 注：公共 API 的**实现**（version / setLogHook / on* / offAll）在 src/zkble_public.cpp ——
// 放这里 inline 会让「只 include 公开头的应用 TU」链接不到（应用看不到定义，编译器不会发射符号）。

}  // namespace ble
}  // namespace zk
