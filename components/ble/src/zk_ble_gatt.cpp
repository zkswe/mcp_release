/*
 * zk_ble_gatt.cpp —— BLE 门面实现（gatt 1.0.0 = BlueZ 用户态 GATT 库）
 *
 * 适用平台：Z20 / Z21 / T113 / T113EMMC，蓝牙走 **AIC USB 模组**（aic_btusb.ko + hciconfig，
 * 不是串口 HCI）→ include 路径里没有 btstack 时由 zkble_backend.h 自动选中本后端。
 * 主从双角色：中心（扫描 / 连接 / GATT 客户端）+ 外设（广播 + 自定义 GATT 服务 + notify）。
 *
 * 线程模型（与 zk_ble.cpp 的 btstack 后端同一套心智模型）：
 *   · gatt 的 mainloop（epoll）独占**一条后端线程**：mainloop_init()/mainloop_run() 只在它里面调，
 *     HCI socket 读写、L2CAP/GATT 的所有 API 调用都发生在这个线程；
 *   · 业务线程（UI/主线程）要干活 → 往 socketpair 写一条 {命令号, gen}，主循环线程收到后执行；
 *   · 需要同步语义的接口（connect/read/write/subscribe/peripheral::*）→ 业务线程用
 *     internal::Waiter 带超时等结果。★Waiter 是 Impl 的成员（不是调用方栈上对象），
 *     所以「业务线程超时返回」不会让后端线程 signal 一块已失效的栈内存；
 *     超时后用 gen（代际号）作废该次操作的后到回调，避免把旧结果填进新请求；
 *   · 所有 fire*（onDeviceFound / onConnectionChange / onValueChange / onWriteRequest）
 *     都在后端线程里调用 —— 与 zk_ble.h 硬约定第 3 条一致（回调里只做轻活）。
 *
 * 连接稳定性（2026-09-14 真机实测根因，见 platforms.md §0.3「稳定性深度分析」）：
 *   本 SDK 的 AIC 控制器在「连接 → 断开」后会**残留链路状态**：LE Create Connection 返 0x0B
 *   (Connection Already Exists)、LE Disconnect 返 EIO，残留期间任何新建连接都被拒，
 *   只能复位控制器恢复（实测「hciconfig hci0 reset 后第一次连接必成功」）。
 *   → connect() 按 Config.connect_retry 自动重试；重试前若 Config.reset_before_retry 为真，
 *     先复位控制器再连；尝试次数记进 getDiag().connect_attempts；最终失败的人话 msg 明说
 *     「疑似控制器残留链路，已重试 N 次」。
 *   同一根因在外设侧的表现是「断开后重新开广播失败」（demo 只打一句
 *   `likely already advertising...`，等于静默丢广播）→ 本文件把 adv enable 的 HCI 返回状态当
 *   一等公民校验：失败 → 先 disable 再 enable → 仍失败 → 复位控制器重试 → 再失败就如实
 *   返回 Result 错误码（绝不静默）。
 *
 * 真机口径与「未验证」标注：
 *   · 扫描 / hci_le_create_conn / L2CAP ATT 连接 / 全量 GATT 发现：Z21 真机跑通（projects/zbble_cli）；
 *   · 广播 + 自定义服务 + 读写回调 + notify：Z20 真机跑通（projects/zbble_srv）；
 *   · 标了 [未真机验证] 的分支是「照实测结论组合出来、但还没在整机端到端跑过」的路径。
 */

#include "zkble_common.h"
#include "zkble_backend.h"

#if ZKBLE_IS_GATT

#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/utsname.h>
#include <unistd.h>

// BlueZ 的 C 头没有 extern "C" 包裹，必须自己包；顺序也固定：
// bluetooth.h（bdaddr_t / htobs / ba2str）必须排第一，hci.h / uuid.h / l2cap.h 才编得过。
// ⚠️ att-types.h 没有 include guard（att.h 已经包含它一次）→ 这里不能再显式包含，否则
//    在 C++ 下会 `redefinition of 'struct bt_att_pdu_error_rsp'`（gcc 8.3 实测）。
extern "C" {
#include <gatt/bluetooth.h>
#include <gatt/att.h>
#include <gatt/hci.h>
#include <gatt/hci_lib.h>
#include <gatt/l2cap.h>
#include <gatt/uuid.h>
#include <gatt/mainloop.h>
#include <gatt/gatt-db.h>
#include <gatt/gatt-client.h>
#include <gatt/gatt-server.h>
}

#include <map>
#include <string>
#include <vector>

namespace zk {
namespace ble {
namespace {

// ================================================================ 常量
const uint8_t  kAttCid             = 4;      // ATT 固定通道 CID（LE 上 ATT 永远走 4）
const uint16_t kPeriphMtu          = 517;    // 外设侧 ATT MTU（demo 实测值）
const uint8_t  kScanDupFilterOff   = 0;      // 0 = 重复广播也报上来（去重自己做，语义与 btstack 后端对齐）
const uint8_t  kHciDisconnReason   = 0x13;   // Remote User Terminated Connection（主动断链的规范值）
const int      kHciCmdTimeout      = 10000;  // 单条 HCI 命令的等待毫秒
const int      kCreateConnTimeout  = 5000;   // LE Create Connection 等连接完成的上限

// ================================================================ 类型
// 中心侧「一个连接」的客户端单元（照 projects/zbble_cli/src/ble/client.cpp 的 client_cell_t）
struct ClientCell {
    int fd = -1;
    struct bt_att* att = NULL;
    struct gatt_db* db = NULL;              // ★我们自己的那份引用（teardown 里 unref）
    struct bt_gatt_client* gatt = NULL;
    bool ready = false;
    int ready_timeout_id = -1;              // 「等 ready」定时器 id（-1 = 没挂）
    bool closing = false;                   // 主动拆除中：断链回调不要再往里钻
};

// 外设侧一条自定义特征
struct PeriphChar {
    std::string uuid;
    int properties = 0;
    std::string value;
    uint16_t value_handle = 0;
};

// 后端线程与业务线程之间的公共请求槽（**同一时刻只允许一个在飞**，串行换简单与安全）
struct PendingReq {
    uint32_t gen = 0;               // 代际号：超时后作废旧回调
    internal::Waiter w;             // 业务线程等它；Impl 成员 ⇒ 永不悬空
    int status = 0;                 // ErrorCode
    std::string msg;                // 人话
    std::string s1;                 // device_id / service_uuid / 新设备名（按命令分工）
    std::string char_uuid;
    std::string data;               // 读结果 / 通知载荷（★出参：submitAndWait 每轮会清它）
    std::string in_data;            // ★写 / notify 的入参载荷（必须与 data 分开，否则会被 submitAndWait 清掉 → len=0）
    bool flag = true;               // 通用布尔（with_response / enable）
    PeripheralConfig pcfg;          // 只在 peripheral::start 用
    std::vector<Service> services;  // 只在 getServices 用
};

// 投递到后端线程的命令头（8 字节定长：AF_UNIX 下这种小消息一次性写入是原子的）
struct CmdHdr {
    int kind;
    uint32_t gen;
};

enum CmdKind {
    CMD_SCAN_START = 1,
    CMD_SCAN_STOP,
    CMD_CONNECT,
    CMD_DISCONNECT,
    CMD_GET_SERVICES,
    CMD_READ,
    CMD_WRITE,
    CMD_SUBSCRIBE,
    CMD_PERIPH_START,
    CMD_PERIPH_STOP,
    CMD_PERIPH_SETNAME,
    CMD_PERIPH_NOTIFY,
    CMD_QUIT,
};

// ---------------------------------------------------------------- 全局单例
struct Impl {
    pthread_mutex_t mtx;
    Config cfg;

    bool opened = false;
    bool ready = false;             // HCI 通路拉起成功 + 后端线程在跑
    bool powered = false;           // /sys/class/bluetooth/hci0 实测存在（不是"我以为上电了"）
    bool preinit_ok = false;        // 本后端 = HCI 通路（hci0 up）成功
    std::string chip = "未知";
    std::string route;              // 通路说明（写进 diag）
    std::string hint = "尚未 openAdapter";
    int last_error = 0;
    std::string last_error_msg;

    PreinitHook preinit;            // gatt 路线不需要，存下来即可（getDiag().hint 会说明）

    pthread_t thread;
    bool thread_started = false;
    int ctrl_fds[2] = { -1, -1 };

    internal::DeviceCache cache;

    // 扫描
    bool discovering = false;
    ScanOptions scan_opts;
    int scan_dd = -1;               // 扫描用的 HCI socket（-1 = 没在扫）
    int scan_timeout_id = -1;
    int adv_unknown_subevents = 0;  // 收到但没解析的 LE 子事件数（落 diag.hint，不静默）
    int hci_events = 0;             // 我们在自己 socket 上看到的 HCI 事件数（0x01~0x5F）
    int hci_state = 0;              // 0=OFF / 1=初始化中 / 2=就绪（gatt 路线没有 btstack 的状态机，语义对齐）

    // 中心侧
    std::string connected_id;
    bool connected = false;         // ATT 客户端 ready（= 门面语义的「已连接」）
    int connect_attempts = 0;
    uint16_t acl_handle = 0;        // hci_le_create_conn 拿到的 ACL handle（断开要用）
    std::vector<Service> services;
    ClientCell client;              // 只有后端线程碰
    std::map<uint16_t, unsigned int> notify_ids;   // value_handle → register_notify 的 id

    // 外设侧
    bool periph_on = false;
    bool periph_connected = false;
    std::string periph_name;
    std::string periph_svc;
    std::vector<PeriphChar> pchars;
    int plisten_fd = -1;
    struct gatt_db* pdb = NULL;
    struct bt_att* patt = NULL;
    struct bt_gatt_server* pserver = NULL;

    // 请求槽
    PendingReq req;
    bool req_busy = false;

    Impl() {
        pthread_mutex_init(&mtx, NULL);
        pchars.reserve(8);          // 外设特征表开播后不再增删 ⇒ 回调里存的下标永远有效
    }
};

Impl& impl() {
    static Impl s;
    return s;
}

void setError(int code, const std::string& msg) {
    Impl& I = impl();
    pthread_mutex_lock(&I.mtx);
    I.last_error = code;
    I.last_error_msg = msg;
    pthread_mutex_unlock(&I.mtx);
    ZKBLE_LOG("ERR(%d) %s", code, msg.c_str());
}

// ================================================================ 基础工具
bool writeCmd(int kind, uint32_t gen) {
    Impl& I = impl();
    if (I.ctrl_fds[1] < 0) return false;
    CmdHdr h;
    h.kind = kind;
    h.gen = gen;
    const ssize_t n = write(I.ctrl_fds[1], &h, sizeof(h));
    return n == (ssize_t)sizeof(h);
}

// 结果回填 + 唤醒业务线程；只有「同一代」的完成事件才作数（超时作废的旧回调不许填新请求）
void completeOp(uint32_t gen, int status, const std::string& msg) {
    Impl& I = impl();
    bool live = false;
    pthread_mutex_lock(&I.mtx);
    live = (gen != 0 && gen == I.req.gen);
    if (live) {
        I.req.status = status;
        I.req.msg = msg;
    }
    pthread_mutex_unlock(&I.mtx);
    if (live) {
        I.req.w.signal(status, msg);
    } else {
        ZKBLE_LOG("op gen=%u 已作废（业务线程早超时），结果丢弃: status=%d %s",
                  gen, status, msg.c_str());
    }
}

// 业务线程侧：投递 + 等待。返回 0=完成 / 1=超时 / 2=忙 / 3=投递失败
int submitAndWait(int kind, int timeout_ms, const std::string& what) {
    Impl& I = impl();
    pthread_mutex_lock(&I.mtx);
    if (I.req_busy) {
        pthread_mutex_unlock(&I.mtx);
        return 2;
    }
    I.req_busy = true;
    I.req.gen++;
    if (I.req.gen == 0) I.req.gen = 1;
    const uint32_t gen = I.req.gen;
    I.req.status = 0;
    I.req.msg.clear();
    // ★2026-09-14 真机 bug D：这里原来会清 data，而 writeValue / peripheral::notify 的入参载荷
    //   恰好就存在 data 里 → 载荷在后端线程看到它之前就被清空（真机表现：写/notify 全部 len=0；
    //   与 bug A/B 无关，是第三个独立缺陷）。现在入参单独走 in_data，data 只当「读结果」出参清。
    I.req.data.clear();
    I.req.services.clear();
    I.req.w.reset();
    pthread_mutex_unlock(&I.mtx);

    if (!writeCmd(kind, gen)) {
        pthread_mutex_lock(&I.mtx);
        I.req_busy = false;
        pthread_mutex_unlock(&I.mtx);
        setError(ERR_IO, "命令投递失败（后端线程没在跑？）：" + what);
        return 3;
    }
    const bool done = I.req.w.wait(timeout_ms);
    pthread_mutex_lock(&I.mtx);
    I.req_busy = false;
    pthread_mutex_unlock(&I.mtx);
    if (!done) {
        ZKBLE_LOG("%s 超时（%dms）——旧代 gen=%u 的结果会被丢弃", what.c_str(), timeout_ms, gen);
        return 1;
    }
    return 0;
}

// ---------------------------------------------------------------- 平台工具
int sysTool(const char* tool, const char* args) {
    return internal::runTool(tool, args);
}

// 控制器复位：AIC 残留链路的唯一解药（实测「复位后第一次连接必成功」）
int resetController() {
    ZKBLE_LOG("hciconfig hci0 reset（清 AIC 残留链路）");
    const int rc = sysTool("hciconfig", "hci0 reset");
    if (rc != 0) {
        ZKBLE_LOG("WARN: hciconfig hci0 reset rc=%d（实际路径 = %s；Z21 整机 /res 只读且无 /res/bin）",
                  rc, internal::findToolPath("hciconfig").c_str());
    }
    usleep(300 * 1000);   // 复位后给控制器喘息时间 [未真机验证：时长按整机可微调]
    return rc;
}

bool hciIfaceExists() { return internal::fileExists("/sys/class/bluetooth/hci0"); }

// insmod aic_btusb.ko：insmod 是系统工具（常在 /sbin），**不走我们的 bin 候选链**（那个链是给
// hciconfig/hcitool 这种散装二进制用的），直接走 PATH；
// 失败也不立刻当致命 —— 模块可能已被系统/上次启动加载过（报 "File exists"），交给调用方看 hci0 是否存在。
// 【2026-09-14 Z21 真机实测】原实现（findToolPath + 失败即 return -1）在「hci0 已存在」的机器上直接
// 把 openAdapter 打成了 ERR_POWER_OFF —— 真机验证才抳出来的坑。
int insmodKo(const std::string& ko) {
    const std::string cmd = std::string("insmod ") + ko;
    const int rc = system(cmd.c_str());
    ZKBLE_LOG("`%s` rc=%d（非 0 不一定是错：已在则报 File exists）", cmd.c_str(), rc);
    return rc;
}

// 上电 / 拉起 HCI 通路（照 projects/zbble_cli|srv 的 _hci_up() 实测流程）
int hciUp(std::string& err) {
    struct utsname u;
    memset(&u, 0, sizeof(u));
    uname(&u);

    bool is_usb_bt = false;
    const char* modules_path[] = { "/lib/modules", "/late/lib/modules" };

    if (hciIfaceExists()) {
        // ★已就绪短路：驱动/模组已加载（系统启动时拉起、或上次我们加载过、或产品应用正在用 BT）
        is_usb_bt = true;
        ZKBLE_LOG("hci0 已存在 → 跳过 insmod（驱动已由系统/上次启动加载）");
    } else {
        for (size_t i = 0; i < sizeof(modules_path) / sizeof(modules_path[0]); ++i) {
            char ko[160];
            snprintf(ko, sizeof(ko), "%s/%s/aic_btusb.ko", modules_path[i], u.release);
            if (!internal::fileExists(ko)) continue;
            // insmod 失败只有在“hci0 仍未就绪”时才算真失败（File exists = 已加载，算成功路径）
            if (insmodKo(ko) != 0 && !hciIfaceExists()) {
                err = std::string("insmod 失败：") + ko + "（看 dmesg / 是否已被占用）";
                return -1;
            }
            is_usb_bt = true;
            ZKBLE_LOG("AIC USB 模组驱动已加载：%s", ko);
            break;
        }
    }

    if (!is_usb_bt) {
        // 没有 ko → 回退系统 hciattach 服务（等价 setprop ctl.start hciattach）
        if (internal::writeProp("ctl.start", "hciattach") != 0) {
            err = "写 /data/property/ctl.start=hciattach 失败（权限/只读分区？），且没找到 aic_btusb.ko";
            return -1;
        }
        int cnt = 500;                       // 500 × 10ms = 5s
        for (; cnt > 0; --cnt) {
            if (hciIfaceExists()) break;
            usleep(10 * 1000);
        }
        if (cnt == 0) {
            err = "启动 hciattach 后 5s 内没等到 /sys/class/bluetooth/hci0（模组没上电？驱动没编？）";
            return -1;
        }
    }

    if (sysTool("hciconfig", "hci0 up") != 0) {
        err = std::string("hciconfig hci0 up 失败（工具路径 = ") + internal::findToolPath("hciconfig") +
              "；Z21 整机 /res 只读且无 /res/bin，开发期把 hciconfig 推到 /data/bin，产品化靠升级包进 /res/bin）";
        return -1;
    }
    if (!hciIfaceExists()) {
        err = "hciconfig hci0 up 之后 hci0 仍不存在（驱动异常）";
        return -1;
    }

#if defined(__PLATFORM_T113__) || defined(__PLATFORM_T113EMMC__)
    // T113(EMMC) 需显式拉起 LE/BR-EDR（与 demo 同一条）[未真机验证：本机无 T113 可跑]
    sysTool("hcitool", "cmd 0x03 0x0003");
#endif

    return 0;
}

void hciDown() {
    sysTool("hciconfig", "hci0 down");
    // 刻意不 rmmod aic_btusb：BT/WiFi 同模组，卸驱动会连带影响 WiFi；下次 openAdapter 会再 up。
    ZKBLE_LOG("hciconfig hci0 down 完成（不 rmmod aic_btusb，避免波及 WiFi）");
}

int hciOpen() {
    int dev = hci_get_route(NULL);
    if (dev < 0) dev = 0;
    const int dd = hci_open_dev(dev);
    if (dd < 0) ZKBLE_LOG("WARN: hci_open_dev(%d) 失败 errno=%d（%s）", dev, errno, strerror(errno));
    return dd;
}

void fireAdapterStateInLoop() {
    Impl& I = impl();
    AdapterState st;
    pthread_mutex_lock(&I.mtx);
    st.available = I.ready;
    st.discovering = I.discovering;
    st.power_on = I.powered;
    pthread_mutex_unlock(&I.mtx);
    internal::fireAdapterState(st);
}

// ---------------------------------------------------------------- uuid 归一
// 门面约定：小写无横线；16 位给 "fff1"，128 位给 32 字符。
// ★从 ATT 发现回来的 uuid 在 BlueZ 里通常是 **128 位形式**（Bluetooth base UUID），
//   必须折回 16 位短写，否则业务按 "fff1" 查不到（最容易踩的形态差异）。
std::string uuidToStr(const bt_uuid_t* u) {
    char buf[40] = { 0 };
    if (!u) return std::string();
    // 【2026-09-14 真机根因 · bug A】
    //   ① bt_uuid_t::type 的取值是 BT_UUID16=16 / BT_UUID32=32 / BT_UUID128=128（见 gatt/uuid.h），
    //      这里直接比数值，不依赖 bt_uuid_len() 的写法（它只是 type/8，语义易混）。
    //   ② ★真正的空 uuid 来源：BlueZ 的 bt_uuid_to_string() **成功时返回 0**、失败才返回 -EINVAL
    //      （gatt/uuid.c 末尾 `return 0;`），原代码写 `<= 0` 当失败 → 128 位路径永远返回空串。
    //   ③ 为什么 128 位路径必然被走到：中心侧全量发现（gatt-client.c）把 ATT 里拿到的 uuid 一律
    //      按 128 位塞进 gatt_db（`bt_uuid128_create(&uuid, u128)`），所以 svc/chr 的 uuid 全是
    //      BT_UUID128 → 短路分支不命中 → 落到下面那个写错的判断上，打印全空、按 uuid 查 handle 全废。
    const int type = (int)u->type;
    if (type == 16) {
        snprintf(buf, sizeof(buf), "%04x", u->value.u16);   // 16 位在库里按主机序存
        return std::string(buf);
    }
    if (type == 32) {
        snprintf(buf, sizeof(buf), "%08x", u->value.u32);
        return std::string(buf);
    }
    if (type != 128) {                     // 0 = BT_UUID_UNSPEC：BT_UUID_UNSPEC 的 uuid 没法转字符串
        ZKBLE_LOG("WARN: uuid 类型非法 type=%d（UNSPEC=0）→ 按空 uuid 处理", type);
        return std::string();
    }
    bt_uuid_t u128;
    memset(&u128, 0, sizeof(u128));
    bt_uuid_to_uuid128(u, &u128);
    char full[MAX_LEN_UUID_STR + 1] = { 0 };
    bt_uuid_to_string(&u128, full, sizeof(full));   // ★返回值 0=成功，别拿它当失败判据
    if (full[0] == '\0') {                          // 真失败时才为空（UNSPEC 会给 "NULL" 且带负返回值）
        ZKBLE_LOG("WARN: bt_uuid_to_string 没给出字符串（type=%d）→ 按空 uuid 处理", type);
        return std::string();
    }
    const std::string s = internal::normalizeUuid(full);
    if (s.size() == 32 && s.compare(0, 4, "0000") == 0 &&
        s.compare(8, 24, "00001000800000805f9b34fb") == 0) {
        return s.substr(4, 4);
    }
    return s;
}

bool uuidFromStr(const std::string& in, bt_uuid_t* out) {
    const std::string s = internal::normalizeUuid(in);
    if (s.empty()) return false;
    if (s.size() <= 8) {
        char* end = NULL;
        const unsigned long v = strtoul(s.c_str(), &end, 16);
        if (end == NULL || *end != '\0') return false;
        if (s.size() <= 4) bt_uuid16_create(out, (uint16_t)v);
        else bt_uuid32_create(out, (uint32_t)v);
        return true;
    }
    if (s.size() != 32) return false;
    uint128_t u128;
    memset(&u128, 0, sizeof(u128));
    for (int i = 0; i < 16; i++) {
        char b[3] = { s[i * 2], s[i * 2 + 1], 0 };
        char* end = NULL;
        const unsigned long v = strtoul(b, &end, 16);
        if (end == NULL || *end != '\0') return false;
        u128.data[15 - i] = (uint8_t)v;      // 文本是大端，uint128_t 是内存序（小端）
    }
    bt_uuid128_create(out, u128);
    return true;
}

// BlueZ 属性位 ↔ 门面 CharProp 位（两套编号不同，必须显式映射，不能直接 cast）
int propsFromBlueZ(uint8_t p) {
    int out = 0;
    if (p & BT_GATT_CHRC_PROP_READ)               out |= PROP_READ;
    if (p & BT_GATT_CHRC_PROP_WRITE)              out |= PROP_WRITE;
    if (p & BT_GATT_CHRC_PROP_WRITE_WITHOUT_RESP) out |= PROP_WRITE_NO_RESPONSE;
    if (p & BT_GATT_CHRC_PROP_NOTIFY)             out |= PROP_NOTIFY;
    if (p & BT_GATT_CHRC_PROP_INDICATE)           out |= PROP_INDICATE;
    return out;
}

// ---------------------------------------------------------------- 服务表遍历（就绪快照 / getServices 共用）
struct CharWalkCtx { std::vector<Characteristic>* out; };

void charWalkCb(struct gatt_db_attribute* attr, void* ud) {
    CharWalkCtx* c = (CharWalkCtx*)ud;
    uint16_t decl = 0, vh = 0, ext = 0;
    uint8_t props = 0;
    bt_uuid_t cu;
    if (!gatt_db_attribute_get_char_data(attr, &decl, &vh, &props, &ext, &cu)) return;
    Characteristic ch;
    ch.uuid = uuidToStr(&cu);
    ch.properties = propsFromBlueZ(props);
    ch.value_handle = vh;
    c->out->push_back(ch);
}

void svcWalkCb(struct gatt_db_attribute* attr, void* ud) {
    std::vector<Service>* out = (std::vector<Service>*)ud;
    uint16_t s = 0, e = 0;
    bool primary = false;
    bt_uuid_t uuid;
    if (!gatt_db_attribute_get_service_data(attr, &s, &e, &primary, &uuid)) return;
    Service sv;
    sv.uuid = uuidToStr(&uuid);
    CharWalkCtx cc;
    cc.out = &sv.characteristics;
    gatt_db_service_foreach_char(attr, charWalkCb, &cc);
    out->push_back(sv);
}

void walkDb(struct gatt_db* db, std::vector<Service>& out) {
    out.clear();
    if (!db) return;
    gatt_db_foreach_service(db, NULL, svcWalkCb, &out);
}

// ---------------------------------------------------------------- 广播数据（AD）构造
// flags(0x01) + Complete Local Name(0x09) + Complete 16/128-bit Service UUID(0x03/0x07)
size_t buildAdvData(const std::string& name, const std::string& svc_uuid, uint8_t* out, size_t cap) {
    size_t n = 0;
    if (cap < 4) return 0;
    out[n++] = 0x02; out[n++] = 0x01; out[n++] = 0x06;   // LE General Discoverable + BR/EDR Not Supported

    std::string nm = name;
    while (!nm.empty() && n + 2 + nm.size() > cap) nm.erase(nm.size() - 1);   // AD 只有 31 字节
    if (nm.size() != name.size()) ZKBLE_LOG("WARN: 广播名被截断到 \"%s\"（AD 放不下）", nm.c_str());
    if (!nm.empty()) {
        out[n++] = (uint8_t)(nm.size() + 1);
        out[n++] = 0x09;
        memcpy(out + n, nm.c_str(), nm.size());
        n += nm.size();
    }

    bt_uuid_t u;
    if (uuidFromStr(svc_uuid, &u)) {
        if (bt_uuid_len(&u) == 2 && n + 4 <= cap) {
            out[n++] = 0x03; out[n++] = 0x03;
            out[n++] = (uint8_t)(u.value.u16 & 0xFF);
            out[n++] = (uint8_t)(u.value.u16 >> 8);
        } else if (n + 18 <= cap) {
            bt_uuid_t u128;
            memset(&u128, 0, sizeof(u128));
            bt_uuid_to_uuid128(&u, &u128);
            out[n++] = 17; out[n++] = 0x07;
            for (int i = 0; i < 16; i++) out[n++] = u128.value.u128.data[15 - i];
        } else {
            ZKBLE_LOG("WARN: AD 装不下服务 UUID（已占 %zu 字节），只广播 flags+名字", n);
        }
    } else {
        ZKBLE_LOG("WARN: 服务 UUID 不合法（%s），AD 里就不放了", svc_uuid.c_str());
    }
    return n;
}

// ================================================================ 外设侧：GATT 表 / 回调
void periphReadCb(struct gatt_db_attribute* attrib, unsigned int id, uint16_t offset,
                  uint8_t opcode, struct bt_att* att, void* user_data) {
    (void)opcode; (void)att;
    Impl& I = impl();
    const size_t idx = (size_t)(uintptr_t)user_data;   // 1-based（0 会被当空指针，故 +1）
    if (idx == 0 || idx > I.pchars.size()) {
        ZKBLE_LOG("外设读回调：特征下标越界 %zu", idx);
        gatt_db_attribute_read_result(attrib, id, BT_ATT_ERROR_UNLIKELY, NULL, 0);
        return;
    }
    const std::string& v = I.pchars[idx - 1].value;
    if (offset > v.size()) {
        gatt_db_attribute_read_result(attrib, id, BT_ATT_ERROR_INVALID_OFFSET, NULL, 0);
        return;
    }
    gatt_db_attribute_read_result(attrib, id, 0,
                                  (const uint8_t*)v.data() + offset, v.size() - offset);
}

void periphWriteCb(struct gatt_db_attribute* attrib, unsigned int id, uint16_t offset,
                   const uint8_t* value, size_t len, uint8_t opcode, struct bt_att* att,
                   void* user_data) {
    (void)opcode; (void)att;
    Impl& I = impl();
    const size_t idx = (size_t)(uintptr_t)user_data;
    if (idx == 0 || idx > I.pchars.size() || !value) {
        ZKBLE_LOG("外设写回调：参数异常（idx=%zu value=%p）", idx, (const void*)value);
        gatt_db_attribute_write_result(attrib, id, BT_ATT_ERROR_INVALID_ATTRIBUTE_VALUE_LEN);
        return;
    }
    PeriphChar& c = I.pchars[idx - 1];
    const std::string d((const char*)value, len);
    if (offset == 0) {
        c.value = d;                          // 常见路径：整体覆盖
    } else if (offset <= c.value.size()) {    // 长写/分段写：按偏移拼接 [未真机验证]
        if (offset + len > c.value.size()) c.value.resize(offset + len);
        c.value.replace(offset, len, d);
    } else {
        gatt_db_attribute_write_result(attrib, id, BT_ATT_ERROR_INVALID_OFFSET);
        return;
    }
    ZKBLE_LOG("外设收到写：char=%s len=%zu offset=%u", c.uuid.c_str(), len, offset);
    gatt_db_attribute_write_result(attrib, id, 0);
    internal::fireWriteRequest(c.uuid, d);
}

// 前置声明（下面几个函数互相调用）
int advEnableChecked(bool enable, std::string* err);
// 广播准备/恢复三件套（定义在下面「外设侧：广播」一节，先声明给断开回调与本函数之后的调用点用）
void advForceDisableForSetup(const char* why);
typedef bool (*AdvStepFn)(std::string*, int*);
bool advStepWithRecover(AdvStepFn step, const char* label, std::string* err);
bool advSetParamsStep(std::string* err, int* status_out);
bool advSetDataStep(std::string* err, int* status_out);
void periphServerAcceptCb(int fd, uint32_t events, void* user_data);

void periphAttDisconnectCb(int err, void* user_data) {
    (void)user_data;
    Impl& I = impl();
    std::string id;
    pthread_mutex_lock(&I.mtx);
    id = I.connected_id;
    I.connected_id.clear();
    pthread_mutex_unlock(&I.mtx);
    ZKBLE_LOG("外设：中心断开（%s）", strerror(err));
    I.periph_connected = false;
    internal::fireConnectionChange(id, false);

    // 断开后把广播恢复起来（demo 也是这么做的）；失败不能静默（§0.3 的坑）。
    // 【2026-09-14 真机口径】恢复路径与 peripheral::start 同一口径：
    //   先 LE Set Advertise Enable(0)（忽略「本来就没开」）→ 重设参数 → 重设数据 → 开广播；
    //   任何一步被控制器拒（如 status=12/0x0C Command Disallowed）→ hciconfig hci0 reset + 等待 + 重试一次，
    //   仍失败则把 status 码与已做处置写进 last_error/ diag.hint（绝不只打一句日志）。
    if (I.periph_on) {
        std::string emsg;
        advForceDisableForSetup("断开后恢复广播");
        const bool ok = advStepWithRecover(advSetParamsStep, "断开后重设广播参数(LE Set Advertising Parameters)", &emsg) &&
                        advStepWithRecover(advSetDataStep, "断开后重设广播数据(LE Set Advertising Data)", &emsg) &&
                        (advEnableChecked(true, &emsg) == 0);
        if (!ok) {
            setError(ERR_IO, "断开后恢复广播失败：" + emsg);
            ZKBLE_LOG("WARN: 断开后恢复广播失败：%s", emsg.c_str());
        } else {
            ZKBLE_LOG("断开后广播已恢复");
        }
    }
}

void periphListenCb(int fd, uint32_t events, void* user_data) {
    (void)user_data;
    Impl& I = impl();
    if (events & (EPOLLRDHUP | EPOLLHUP | EPOLLERR)) {
        ZKBLE_LOG("WARN: 外设监听 socket 异常事件 0x%x，移除", events);
        mainloop_remove_fd(fd);
        I.plisten_fd = -1;
        return;
    }
    periphServerAcceptCb(fd, events, NULL);
}

void periphServerAcceptCb(int fd, uint32_t events, void* user_data) {
    (void)events; (void)user_data;
    Impl& I = impl();
    struct sockaddr_l2 addr;
    memset(&addr, 0, sizeof(addr));
    socklen_t optlen = sizeof(addr);
    const int nsk = accept(fd, (struct sockaddr*)&addr, &optlen);
    if (nsk < 0) {
        ZKBLE_LOG("外设 accept 失败 errno=%d（%s）", errno, strerror(errno));
        return;
    }
    char ba[18] = { 0 };
    ba2str(&addr.l2_bdaddr, ba);
    ZKBLE_LOG("中心接入：%s", ba);

    if (I.patt) {                       // 单连接模型：已有中心时先拆旧的（避免 refcount 泄漏）
        ZKBLE_LOG("WARN: 已有中心连接，拆掉旧的再接新的（本后端只支持单连接）");
        if (I.pserver) { bt_gatt_server_unref(I.pserver); I.pserver = NULL; }
        bt_att_unref(I.patt);
        I.patt = NULL;
    }
    I.periph_connected = false;

    I.patt = bt_att_new(nsk, false);
    if (!I.patt) {
        ZKBLE_LOG("bt_att_new 失败");
        close(nsk);
        return;
    }
    bt_att_set_close_on_unref(I.patt, true);
    if (!bt_att_register_disconnect(I.patt, periphAttDisconnectCb, NULL, NULL)) {
        ZKBLE_LOG("bt_att_register_disconnect 失败");
        bt_att_unref(I.patt);
        I.patt = NULL;
        return;
    }
    I.pserver = bt_gatt_server_new(I.pdb, I.patt, kPeriphMtu, 0);
    if (!I.pserver) {
        ZKBLE_LOG("bt_gatt_server_new 失败");
        bt_att_unref(I.patt);
        I.patt = NULL;
        return;
    }
    I.periph_connected = true;
    pthread_mutex_lock(&I.mtx);
    I.connected_id = std::string(ba);
    pthread_mutex_unlock(&I.mtx);
    internal::fireConnectionChange(std::string(ba), true);
}

// ---------------------------------------------------------------- 外设侧：广播（全部校验 HCI 状态）
// 【2026-09-14 真机根因 · bug C】
//   LE Set Advertising Parameters / Data 在「控制器已处于 advertising enable」状态下会被拒
//   （HCI status=12 = 0x0C Command Disallowed）——进程被杀/上次运行残留时就是这种状态。
//   规范做法：改参数/数据前**总是**先 LE Set Advertise Enable(0)（本来就没开的返回忽略掉）。
// 参数/数据两步共用的「重试一次」口径：被拒 → 复位控制器 + 等待 → 重试；再失败如实上报。
bool advSetParams(std::string* err, int* status_out) {
    const int dd = hciOpen();
    if (dd < 0) { if (err) *err = "hci_open_dev 失败（hci0 没 up？）"; if (status_out) *status_out = -1; return false; }

    struct hci_request rq;
    le_set_advertising_parameters_cp p;
    uint8_t status = 0xFF;
    memset(&p, 0, sizeof(p));
    p.min_interval = htobs(0x0020);      // 20ms
    p.max_interval = htobs(0x01E0);      // 300ms（demo 实测值）
    p.advtype = 0;                       // ADV_IND：可连接、可扫描
    p.own_bdaddr_type = LE_PUBLIC_ADDRESS;
    p.chan_map = 7;                      // 37/38/39 全开
    p.filter = 0;
    memset(&rq, 0, sizeof(rq));
    rq.ogf = OGF_LE_CTL;
    rq.ocf = OCF_LE_SET_ADVERTISING_PARAMETERS;
    rq.cparam = &p;
    rq.clen = LE_SET_ADVERTISING_PARAMETERS_CP_SIZE;
    rq.rparam = &status;
    rq.rlen = 1;

    const int ret = hci_send_req(dd, &rq, kHciCmdTimeout);
    hci_close_dev(dd);
    if (status_out) *status_out = (ret < 0) ? -1 : (int)status;
    if (ret < 0) { if (err) *err = "LE Set Advertising Parameters 无响应（hci_send_req 失败）"; return false; }
    if (status != 0) { if (err) *err = "LE Set Advertising Parameters 被拒 status=" + std::to_string(status); return false; }
    return true;
}

bool advSetData(const std::string& name, const std::string& svc, std::string* err, int* status_out) {
    const int dd = hciOpen();
    if (dd < 0) { if (err) *err = "hci_open_dev 失败"; if (status_out) *status_out = -1; return false; }

    uint8_t ad[31];
    memset(ad, 0, sizeof(ad));
    const size_t n = buildAdvData(name, svc, ad, sizeof(ad));
    if (n == 0) {
        hci_close_dev(dd);
        if (status_out) *status_out = -1;
        if (err) *err = "广播数据构造失败（名字/服务 UUID 不合法？）";
        return false;
    }

    struct hci_request rq;
    le_set_advertising_data_cp cp;
    uint8_t status = 0xFF;
    memset(&cp, 0, sizeof(cp));
    cp.length = (uint8_t)n;
    memcpy(cp.data, ad, n);
    memset(&rq, 0, sizeof(rq));
    rq.ogf = OGF_LE_CTL;
    rq.ocf = OCF_LE_SET_ADVERTISING_DATA;   // gatt 包里没有 hci_le_set_adv_data() 封装 → 直接发原始命令
    rq.cparam = &cp;
    rq.clen = LE_SET_ADVERTISING_DATA_CP_SIZE;
    rq.rparam = &status;
    rq.rlen = 1;

    const int ret = hci_send_req(dd, &rq, kHciCmdTimeout);
    hci_close_dev(dd);
    if (status_out) *status_out = (ret < 0) ? -1 : (int)status;
    if (ret < 0) { if (err) *err = "LE Set Advertising Data 无响应"; return false; }
    if (status != 0) { if (err) *err = "LE Set Advertising Data 被拒 status=" + std::to_string(status); return false; }
    return true;
}

// 单次开关广播：0 = 成功；*status 收 HCI 状态码（BlueZ 的 hci_le_set_advertise_enable 把状态塞 errno）
int advEnableOnce(bool enable, int* status) {
    const int dd = hciOpen();
    if (dd < 0) { if (status) *status = -1; return -1; }
    errno = 0;
    const int rc = hci_le_set_advertise_enable(dd, enable ? 1 : 0, kHciCmdTimeout);
    const int e = errno;
    hci_close_dev(dd);
    if (status) *status = (rc < 0) ? e : 0;
    return rc;
}

// 带校验的 adv enable：失败 → disable 再 enable → 仍失败 → 复位控制器重试 → 再失败如实上报
int advEnableChecked(bool enable, std::string* err) {
    Impl& I = impl();
    int status = 0;
    if (advEnableOnce(enable, &status) == 0) return 0;

    if (!enable) {
        if (err) *err = "LE Set Advertise Enable(0) 失败 status=" + std::to_string(status);
        return status ? status : -1;
    }

    ZKBLE_LOG("adv enable 失败 status=%d（0x0C=Command Disallowed，通常是「已在广播」/链路残留）→ 先 disable 再 enable", status);
    advEnableOnce(false, NULL);
    usleep(100 * 1000);
    if (advEnableOnce(true, &status) == 0) {
        ZKBLE_LOG("disable→enable 之后广播恢复 OK");
        return 0;
    }

    ZKBLE_LOG("adv enable 仍失败 status=%d → 复位控制器再试一次", status);
    resetController();
    if (advEnableOnce(true, &status) == 0) {
        ZKBLE_LOG("复位控制器后广播开启 OK");
        return 0;
    }

    // 走到这里就是真失败：绝不当成功（demo 的静默丢广播就是这么来的）
    I.hint = "广播开不起来：HCI LE Set Advertise Enable 返回 status=" + std::to_string(status) +
             "（常见 0x0C=Command Disallowed）。已试过 disable→enable 与 hciconfig hci0 reset；"
             "仍失败请查是否有别的进程占着 hci0，或对端链路残留后需要整机重启。";
    setError(ERR_IO, I.hint);
    if (err) *err = I.hint;
    return status ? status : -1;
}

// 【bug C 主修正】准备广播前**总是**先关一次广播：
//   控制器已在 advertising enable 时，LE Set Advertising Parameters/Data 会被拒 status=12(0x0C)。
//   「本来就没开 / 已经关了」的返回一律忽略（只记日志，不当失败）。
void advForceDisableForSetup(const char* why) {
    int st = 0;
    const int rc = advEnableOnce(false, &st);
    if (rc == 0) {
        ZKBLE_LOG("广播准备（%s）：LE Set Advertise Enable(0) OK（关掉，便于后续改参数/数据）", why);
    } else {
        ZKBLE_LOG("广播准备（%s）：LE Set Advertise Enable(0) 返回 status=%d rc=%d（忽略：本来就没开也算正常）",
                  why, st, rc);
    }
}

bool advSetParamsStep(std::string* err, int* status_out) {
    return advSetParams(err, status_out);
}

bool advSetDataStep(std::string* err, int* status_out) {
    Impl& I = impl();
    return advSetData(I.periph_name, I.periph_svc, err, status_out);
}

// 设置广播参数/数据这类 LE 命令的统一口径：被拒 → hciconfig hci0 reset + 等待 + 重试一次；
// 仍失败 → 把 status 码与已做处置写进 Result/Diag（绝不静默）。
bool advStepWithRecover(AdvStepFn step, const char* label, std::string* err) {
    Impl& I = impl();
    int st1 = 0;
    std::string e1;
    if (step(&e1, &st1)) return true;

    ZKBLE_LOG("%s 失败（%s）→ 先关广播 + hciconfig hci0 reset + 等待，然后重试一次", label, e1.c_str());
    advForceDisableForSetup("复位重试前");
    resetController();                 // 内部自带 300ms 喘息
    usleep(200 * 1000);

    int st2 = 0;
    std::string e2;
    if (step(&e2, &st2)) {
        ZKBLE_LOG("%s 复位控制器后重试成功（首次 status=%d）", label, st1);
        return true;
    }

    const std::string hint = std::string(label) + " 失败：首次 status=" + std::to_string(st1) +
        "，复位重试后 status=" + std::to_string(st2) + "（" + e2 + "）；已做处置：LE Set Advertise "
        "Enable(0) + hciconfig hci0 reset + 等待 + 重试一次，仍失败。常见根因：改参数时广播还处于 "
        "enable 状态（status=12/0x0C Command Disallowed）或 AIC 链路残留；请确认没有别的进程占着 hci0。";
    I.hint = hint;
    setError(ERR_IO, hint);
    if (err) *err = hint;
    return false;
}

// 句柄交叉校验用：从「特征声明属性」里抠 value_handle（走 gatt_db_service_foreach_char，
// 只回调 uuid==0x2803 的声明属性 → 这里 get_char_data 必定拿得到）
struct CharHandleCtx { std::vector<uint16_t>* out; };

void charHandleCb(struct gatt_db_attribute* attr, void* ud) {
    CharHandleCtx* c = (CharHandleCtx*)ud;
    uint16_t decl = 0, vh = 0, ext = 0;
    uint8_t props = 0;
    if (!gatt_db_attribute_get_char_data(attr, &decl, &vh, &props, &ext, NULL)) return;
    c->out->push_back(vh);
}

bool periphBuildDb(const PeripheralConfig& cfg, std::string* err) {
    // [未真机验证] 这张表的装法（add_service / add_characteristic / CCCD / set_active）与
    // projects/zbble_srv/src/ble/server.cpp 完全一致（Z20 真机跑通），但通过 zk::ble 门面这条路
    // 还没上整机；差别只在属性位从 CharProp 映射过来（map 表见上）。
    Impl& I = impl();
    bt_uuid_t su;
    if (!uuidFromStr(cfg.service_uuid, &su)) {
        if (err) *err = "service_uuid 不合法（16 位如 fff0 或 32 字符 hex）: " + cfg.service_uuid;
        return false;
    }
    if (cfg.characteristics.empty()) {
        if (err) *err = "characteristics 不能为空（至少一个特征）";
        return false;
    }

    uint16_t handles = 1;                        // 服务声明自己占 1 个
    for (size_t i = 0; i < cfg.characteristics.size(); i++) {
        handles = (uint16_t)(handles + 2);       // 特征声明 + value
        if (cfg.characteristics[i].properties & (PROP_NOTIFY | PROP_INDICATE)) handles++;   // CCCD
    }

    if (!I.pdb) I.pdb = gatt_db_new();
    if (!I.pdb) { if (err) *err = "gatt_db_new 失败"; return false; }

    struct gatt_db_attribute* svc = gatt_db_add_service(I.pdb, &su, true, handles);
    if (!svc) { if (err) *err = "gatt_db_add_service 失败"; return false; }

    I.pchars.clear();
    for (size_t i = 0; i < cfg.characteristics.size(); i++) {
        const PeripheralChar& pc = cfg.characteristics[i];
        bt_uuid_t cu;
        if (!uuidFromStr(pc.uuid, &cu)) { if (err) *err = "特征 uuid 不合法: " + pc.uuid; return false; }

        uint8_t props = 0;
        uint32_t perms = 0;
        if (pc.properties & PROP_READ) props |= BT_GATT_CHRC_PROP_READ;
        if (pc.properties & PROP_WRITE) props |= BT_GATT_CHRC_PROP_WRITE;
        if (pc.properties & PROP_WRITE_NO_RESPONSE) props |= BT_GATT_CHRC_PROP_WRITE_WITHOUT_RESP;
        if (pc.properties & PROP_NOTIFY) props |= BT_GATT_CHRC_PROP_NOTIFY;
        if (pc.properties & PROP_INDICATE) props |= BT_GATT_CHRC_PROP_INDICATE;
        if (pc.properties & PROP_READ) perms |= BT_ATT_PERM_READ;
        if (pc.properties & (PROP_WRITE | PROP_WRITE_NO_RESPONSE)) perms |= BT_ATT_PERM_WRITE;
        if (perms == 0) perms = BT_ATT_PERM_READ;      // 一个权限都不给的话属性读不到，兜一个

        PeriphChar entry;
        entry.uuid = internal::normalizeUuid(pc.uuid);
        entry.properties = pc.properties;
        entry.value = pc.value;
        I.pchars.push_back(entry);
        const size_t idx = I.pchars.size();            // 1-based（0 当空指针用）

        struct gatt_db_attribute* ch = gatt_db_service_add_characteristic(
            svc, &cu, perms, props, periphReadCb, periphWriteCb, (void*)(uintptr_t)idx);
        if (!ch) { if (err) *err = "gatt_db_service_add_characteristic 失败: " + pc.uuid; return false; }

        // 【2026-09-14 真机根因 · bug B】
        //   gatt_db_service_add_characteristic() 返回的是**特征值属性**，不是「特征声明属性」：
        //   gatt-db.c 里 service_insert_characteristic() 末尾 `return service->attributes[i];`
        //   → i 已经被 ++ 过 → 拿到的是 new_attribute(handle, uuid, NULL, 0) 那个值属性。
        //   而 gatt_db_attribute_get_char_data() 只认声明属性（先比 attrib->uuid == 0x2803），
        //   传值属性进去必然 false → 原代码就落进「拿不到 value_handle」的 WARN。
        //   正解：值属性自己的 handle 就是 value_handle → 用 gatt_db_attribute_get_handle()。
        //   （中心侧能拿到 props/handle 是因为 walkDb 走的是 gatt_db_service_foreach_char，
        //    它只回调 uuid==0x2803 的声明属性，所以那里 get_char_data 是对的。）
        const uint16_t vh = gatt_db_attribute_get_handle(ch);
        I.pchars[idx - 1].value_handle = vh;
        ZKBLE_LOG("外设特征表：%s value_handle=0x%04x props=0x%02x",
                  entry.uuid.c_str(), (unsigned)vh, (unsigned)props);
        if (vh == 0) {
            if (err) *err = "特征 value_handle 为 0（gatt_db_attribute_get_handle 异常）: " + pc.uuid;
            return false;
        }

        if (pc.properties & (PROP_NOTIFY | PROP_INDICATE)) {
            bt_uuid_t ccc;
            bt_uuid16_create(&ccc, GATT_CLIENT_CHARAC_CFG_UUID);
            if (!gatt_db_service_add_descriptor(svc, &ccc, BT_ATT_PERM_READ | BT_ATT_PERM_WRITE,
                                                NULL, NULL, NULL)) {
                if (err) *err = "CCCD(0x2902) 描述符添加失败（中心将无法订阅 notify）: " + pc.uuid;
                return false;
            }
        }
    }

    if (!gatt_db_service_set_active(svc, true)) {
        if (err) *err = "gatt_db_service_set_active 失败";
        return false;
    }

    // 交叉校验（真机证据）：走一遍「特征声明属性」拿官方 value_handle，与上面记的比。
    // 一旦不一致（比如库版本又改了 add_characteristic 的返回语义）能当场吐出来，而不是等 notify 默默失败。
    {
        std::vector<uint16_t> official;
        CharHandleCtx hc;
        hc.out = &official;
        gatt_db_service_foreach_char(svc, charHandleCb, &hc);
        if (official.size() != I.pchars.size()) {
            ZKBLE_LOG("WARN: 特征声明属性个数 %zu != 装配的特征数 %zu（句柄校验跳过）",
                      official.size(), I.pchars.size());
        } else {
            for (size_t k = 0; k < official.size(); k++) {
                if (official[k] != I.pchars[k].value_handle) {
                    ZKBLE_LOG("WARN: 特征 %s 的 value_handle 不一致（装配=0x%04x 官方=0x%04x）",
                              I.pchars[k].uuid.c_str(),
                              (unsigned)I.pchars[k].value_handle, (unsigned)official[k]);
                }
            }
            ZKBLE_LOG("外设句柄校验通过：%zu 个特征与 gatt_db 声明属性一致", official.size());
        }
    }
    ZKBLE_LOG("外设 GATT 表装配完成：service=%s 特征 %zu 个（handles=%u）",
              cfg.service_uuid.c_str(), I.pchars.size(), (unsigned)handles);
    return true;
}

int periphListen() {
    const int sk = socket(PF_BLUETOOTH, SOCK_SEQPACKET, BTPROTO_L2CAP);
    if (sk < 0) {
        ZKBLE_LOG("L2CAP socket 创建失败 errno=%d（%s）", errno, strerror(errno));
        return -1;
    }
    struct sockaddr_l2 src;
    memset(&src, 0, sizeof(src));
    src.l2_family = AF_BLUETOOTH;
    src.l2_cid = htobs(kAttCid);
    src.l2_bdaddr_type = BDADDR_LE_PUBLIC;
    if (bind(sk, (struct sockaddr*)&src, sizeof(src)) < 0) {
        ZKBLE_LOG("L2CAP bind(ATT) 失败 errno=%d（%s）—— 是否有别的进程在监听 ATT？", errno, strerror(errno));
        close(sk);
        return -1;
    }
    struct bt_security sec;
    memset(&sec, 0, sizeof(sec));
    sec.level = BT_SECURITY_LOW;
    if (setsockopt(sk, SOL_BLUETOOTH, BT_SECURITY, &sec, sizeof(sec)) != 0) {
        ZKBLE_LOG("WARN: 设置 L2CAP 安全等级失败 errno=%d（继续，demo 没设也跑通）", errno);
    }
    if (listen(sk, 5) < 0) {
        ZKBLE_LOG("listen 失败 errno=%d（%s）", errno, strerror(errno));
        close(sk);
        return -1;
    }
    ZKBLE_LOG("外设已监听 ATT 通道（CID=%u）", (unsigned)kAttCid);
    return sk;
}

void periphStopInLoop() {
    Impl& I = impl();
    if (I.pserver) { bt_gatt_server_unref(I.pserver); I.pserver = NULL; }
    if (I.patt) { bt_att_unref(I.patt); I.patt = NULL; }      // close_on_unref=true ⇒ 顺带关 fd
    if (I.plisten_fd >= 0) {
        mainloop_remove_fd(I.plisten_fd);
        close(I.plisten_fd);
        I.plisten_fd = -1;
    }
    if (I.pdb) { gatt_db_unref(I.pdb); I.pdb = NULL; }
    I.periph_connected = false;
    if (I.periph_on) {
        std::string err;
        advEnableChecked(false, &err);
        I.periph_on = false;
    }
    I.pchars.clear();
    ZKBLE_LOG("外设已停止");
}

// ================================================================ 扫描（后端线程内）
void scanStopInLoop() {
    Impl& I = impl();
    if (I.scan_timeout_id >= 0) {
        mainloop_remove_timeout(I.scan_timeout_id);
        I.scan_timeout_id = -1;
    }
    if (I.scan_dd >= 0) {
        errno = 0;
        if (hci_le_set_scan_enable(I.scan_dd, 0x00, kScanDupFilterOff, kHciCmdTimeout) < 0) {
            ZKBLE_LOG("WARN: hci_le_set_scan_enable(0) 失败 errno=%d（仍继续关 socket）", errno);
        }
        mainloop_remove_fd(I.scan_dd);
        hci_close_dev(I.scan_dd);
        I.scan_dd = -1;
    }
    if (I.discovering) {
        I.discovering = false;
        ZKBLE_LOG("扫描已停止");
        fireAdapterStateInLoop();
    }
}

void scanTimeoutCb(int id, void* user_data) {
    (void)user_data;
    Impl& I = impl();
    if (I.scan_timeout_id == id) I.scan_timeout_id = -1;
    ZKBLE_LOG("扫描到时长上限，自动停止");
    scanStopInLoop();
}

// 一条 LE Advertising Report → DeviceInfo（RSSI 挂在 AD 数据后面的最后一个字节上）
void handleOneAdvReport(const uint8_t* data, size_t len) {
    Impl& I = impl();
    if (len < LE_ADVERTISING_INFO_SIZE + 1) return;
    const le_advertising_info* info = (const le_advertising_info*)data;
    if ((size_t)LE_ADVERTISING_INFO_SIZE + info->length + 1 > len) {
        ZKBLE_LOG("广播报文长度异常（length=%u > 可用 %zu），丢弃", info->length, len);
        return;
    }
    internal::CachedDevice cd;
    cd.addr_type = info->bdaddr_type;
    char id[20] = { 0 };
    snprintf(id, sizeof(id), "%02X:%02X:%02X:%02X:%02X:%02X",
             info->bdaddr.b[5], info->bdaddr.b[4], info->bdaddr.b[3],
             info->bdaddr.b[2], info->bdaddr.b[1], info->bdaddr.b[0]);
    cd.info.id = id;
    // ★零长柔性数组（data[0]）必须按指针取元素：GCC 8 在 -Werror=array-bounds 下会拒绍直接下标
    // （独立 -c 自检用 -Wall 看不出，fun build 的真实 flag 会拦 → 2026-09-14 修）
    const uint8_t* ad = (const uint8_t*)info->data;
    cd.info.rssi = (int16_t)(int8_t)ad[info->length];   // RSSI 在 AD 之后
    cd.info.last_seen_ms = (int64_t)internal::monotonicMs();
    cd.info.connectable = (info->evt_type == 0x00 || info->evt_type == 0x01);
    internal::parseAdFields(ad, info->length, cd.info.name,
                            cd.info.service_data_hex, cd.info.adv_data_hex);

    ScanOptions opts;
    pthread_mutex_lock(&I.mtx);
    opts = I.scan_opts;
    pthread_mutex_unlock(&I.mtx);
    if (!internal::matchScanFilter(cd.info, opts)) return;

    const bool is_new = I.cache.upsert(cd);
    if (is_new || opts.allow_duplicates) internal::fireDeviceFound(cd.info);
}

void scanCb(int fd, uint32_t events, void* user_data) {
    (void)events; (void)user_data;
    Impl& I = impl();
    uint8_t buf[HCI_MAX_EVENT_SIZE];
    const ssize_t n = read(fd, buf, sizeof(buf));
    if (n < 0) {
        if (errno == EINTR || errno == EAGAIN) return;
        ZKBLE_LOG("扫描 socket 读失败 errno=%d（%s）", errno, strerror(errno));
        mainloop_remove_fd(fd);
        I.scan_dd = -1;
        I.discovering = false;
        fireAdapterStateInLoop();
        return;
    }
    if (n < 1 + HCI_EVENT_HDR_SIZE) return;
    const uint8_t evt = buf[1];
    if (evt >= 0x01 && evt <= 0x5F) I.hci_events++;
    if (evt != EVT_LE_META_EVENT) return;

    const evt_le_meta_event* meta = (const evt_le_meta_event*)(buf + 1 + HCI_EVENT_HDR_SIZE);
    const size_t after_meta = (size_t)n - 1 - HCI_EVENT_HDR_SIZE;
    if (after_meta < 2) return;

    if (meta->subevent == EVT_LE_ADVERTISING_REPORT) {     // 0x02 传统广播上报
        // 事件体：num_reports(1) + report...（照 hcitool 的解析：跳过 num_reports 字节）
        // [未真机验证] demo 只取第一条上报；这里按 num_reports 逐条解（一个事件里本来就可能多条）。
        // ★零长柔性数组（data[0]）必须用指针解引用：GCC 8 在 fun build 的 -Werror=array-bounds 下
        // 会拒绍直接下标（独立 -c 自检只开 -Wall，看不出 → 2026-09-14 由真机工程抳出）
        const uint8_t* mdata = (const uint8_t*)meta->data;
        const uint8_t num = mdata[0];
        const uint8_t* p = mdata + 1;
        size_t remain = after_meta - 2;
        for (uint8_t i = 0; i < num && remain >= LE_ADVERTISING_INFO_SIZE; i++) {
            const le_advertising_info* info = (const le_advertising_info*)p;
            const size_t used = (size_t)LE_ADVERTISING_INFO_SIZE + info->length + 1;
            if (used > remain) break;
            handleOneAdvReport(p, remain);
            p += used;
            remain -= used;
        }
        return;
    }
    // 其它 LE 子事件（5.0 extended adv 等）：布局不一致，只做「降级尝试」不留 = 计数 + 落 diag.hint
    I.adv_unknown_subevents++;
    if (I.adv_unknown_subevents <= 3) {
        ZKBLE_LOG("收到未支持的 LE 子事件 0x%02x（累计 %d）→ 该设备可能走 5.0 extended adv；"
                  "扫不到设备时优先核对这里", meta->subevent, I.adv_unknown_subevents);
    }
}

int scanStartInLoop(std::string* msg) {
    Impl& I = impl();
    if (I.scan_dd >= 0) {
        ZKBLE_LOG("已经在扫描，忽略重复 start");
        return ERR_OK;
    }
    const int dd = hciOpen();
    if (dd < 0) {
        *msg = "扫描失败：hci_open_dev 打不开（hci0 没 up？）";
        return ERR_POWER_OFF;
    }
    const uint8_t own_type = LE_PUBLIC_ADDRESS;
    const uint8_t scan_type = 0x01;          // 主动扫描（要拿 Scan Response 里的名字）
    const uint8_t filter_policy = 0x00;
    const uint16_t interval = htobs(0x0010); // 10ms（demo / Z21 实测值）
    const uint16_t window = htobs(0x0010);

    if (hci_le_set_scan_parameters(dd, scan_type, interval, window, own_type,
                                   filter_policy, kHciCmdTimeout) < 0) {
        ZKBLE_LOG("LE Set Scan Parameters 失败 errno=%d", errno);
        hci_close_dev(dd);
        *msg = "扫描参数设置失败（控制器拒绝）";
        return ERR_IO;
    }
    if (hci_le_set_scan_enable(dd, 0x01, kScanDupFilterOff, kHciCmdTimeout) < 0) {
        ZKBLE_LOG("LE Set Scan Enable 失败 errno=%d", errno);
        hci_close_dev(dd);
        *msg = "开启扫描失败（控制器拒绝；可能链路残留 → hciconfig hci0 reset）";
        return ERR_IO;
    }

    struct hci_filter nf;
    hci_filter_clear(&nf);
    hci_filter_set_ptype(HCI_EVENT_PKT, &nf);
    hci_filter_set_event(EVT_LE_META_EVENT, &nf);
    if (setsockopt(dd, SOL_HCI, HCI_FILTER, &nf, sizeof(nf)) < 0) {
        ZKBLE_LOG("setsockopt(HCI_FILTER) 失败 errno=%d", errno);
        hci_le_set_scan_enable(dd, 0x00, kScanDupFilterOff, kHciCmdTimeout);
        hci_close_dev(dd);
        *msg = "扫描 socket 过滤器设置失败";
        return ERR_IO;
    }

    I.scan_dd = dd;
    mainloop_add_fd(dd, EPOLLIN, scanCb, NULL, NULL);
    I.discovering = true;
    I.adv_unknown_subevents = 0;
    const int dur = I.scan_opts.duration_ms;
    ZKBLE_LOG("扫描已开启（主动扫描；重复上报按 allow_duplicates=%d 处理）",
              I.scan_opts.allow_duplicates ? 1 : 0);
    if (dur > 0) {
        I.scan_timeout_id = mainloop_add_timeout((unsigned int)dur, scanTimeoutCb, NULL, NULL);
    }
    fireAdapterStateInLoop();
    return ERR_OK;
}

// ================================================================ 中心侧：连接
// L2CAP ATT 连接：非阻塞 connect + poll 超时（不让主循环线程被无限期卡死）
// [未真机验证] demo（Z21 真机跑通）用的是**阻塞** connect；这里为了不让后端线程被卡死改成
//   非阻塞 + poll，语义等价但没在整机上跑过 —— 若出现连接异常，先怀疑这一处。
// ★地址类型编号两套 API 不同：HCI 广播上报 0=public 1=random；
//   sockaddr_l2.l2_bdaddr_type 用内核枚举 BDADDR_LE_PUBLIC=1 / BDADDR_LE_RANDOM=2 → 必须转换
//   （demo 里写死 BDADDR_LE_PUBLIC，遇到随机地址设备就连不上）。
int l2capAttConnect(const bdaddr_t& dst, uint8_t hci_addr_type, int timeout_ms) {
    const int sk = socket(PF_BLUETOOTH, SOCK_SEQPACKET, BTPROTO_L2CAP);
    if (sk < 0) {
        ZKBLE_LOG("L2CAP socket 创建失败 errno=%d", errno);
        return -1;
    }
    struct sockaddr_l2 src;
    memset(&src, 0, sizeof(src));
    src.l2_family = AF_BLUETOOTH;
    src.l2_cid = htobs(kAttCid);
    src.l2_bdaddr_type = BDADDR_LE_PUBLIC;
    if (bind(sk, (struct sockaddr*)&src, sizeof(src)) < 0) {
        ZKBLE_LOG("L2CAP bind 失败 errno=%d（%s）", errno, strerror(errno));
        close(sk);
        return -1;
    }
    struct bt_security sec;
    memset(&sec, 0, sizeof(sec));
    sec.level = BT_SECURITY_LOW;
    if (setsockopt(sk, SOL_BLUETOOTH, BT_SECURITY, &sec, sizeof(sec)) != 0) {
        ZKBLE_LOG("WARN: 设置 L2CAP 安全等级失败 errno=%d（继续）", errno);
    }

    struct sockaddr_l2 dstaddr;
    memset(&dstaddr, 0, sizeof(dstaddr));
    dstaddr.l2_family = AF_BLUETOOTH;
    dstaddr.l2_cid = htobs(kAttCid);
    dstaddr.l2_bdaddr_type = (hci_addr_type == 0x01) ? BDADDR_LE_RANDOM : BDADDR_LE_PUBLIC;
    bacpy(&dstaddr.l2_bdaddr, &dst);

    const int oldfl = fcntl(sk, F_GETFL, 0);
    if (oldfl < 0 || fcntl(sk, F_SETFL, oldfl | O_NONBLOCK) < 0) {
        ZKBLE_LOG("WARN: 设置非阻塞失败 errno=%d（退化为阻塞 connect）", errno);
    }
    int rc = connect(sk, (struct sockaddr*)&dstaddr, sizeof(dstaddr));
    if (rc < 0 && errno != EINPROGRESS && errno != EAGAIN) {
        ZKBLE_LOG("L2CAP ATT connect 失败 errno=%d（%s）", errno, strerror(errno));
        close(sk);
        return -1;
    }
    if (rc < 0) {
        struct pollfd pfd;
        pfd.fd = sk;
        pfd.events = POLLOUT;
        pfd.revents = 0;
        const int pr = poll(&pfd, 1, timeout_ms);
        if (pr <= 0) {
            ZKBLE_LOG("L2CAP ATT connect 超时（poll=%d errno=%d）", pr, errno);
            close(sk);
            return -1;
        }
        int soerr = 0;
        socklen_t slen = sizeof(soerr);
        getsockopt(sk, SOL_SOCKET, SO_ERROR, &soerr, &slen);
        if (soerr != 0) {
            ZKBLE_LOG("L2CAP ATT connect 异步失败 errno=%d（%s）", soerr, strerror(soerr));
            close(sk);
            return -1;
        }
    }
    if (oldfl >= 0) fcntl(sk, F_SETFL, oldfl);    // 还原阻塞（ATT 库按阻塞 fd 用）
    ZKBLE_LOG("L2CAP ATT 通道已建立");
    return sk;
}

void clientTeardownInLoop(bool disconnectAcl);

void clientReadyCb(bool success, uint8_t att_ecode, void* user_data) {
    const uint32_t gen = (uint32_t)(uintptr_t)user_data;
    Impl& I = impl();
    if (I.client.ready_timeout_id >= 0) {
        mainloop_remove_timeout(I.client.ready_timeout_id);
        I.client.ready_timeout_id = -1;
    }
    if (!success) {
        ZKBLE_LOG("GATT 发现失败 att_ecode=0x%02x", att_ecode);
        clientTeardownInLoop(true);
        completeOp(gen, ERR_DISCONNECTED,
                   "GATT 服务发现失败 att_ecode=0x" + std::to_string(att_ecode));
        return;
    }
    I.client.ready = true;

    std::vector<Service> svcs;
    walkDb(I.client.db, svcs);      // 就绪即快照：业务先 getServices 再 read/write 的顺序就不用再打一趟循环
    pthread_mutex_lock(&I.mtx);
    I.services = svcs;
    I.connected = true;
    pthread_mutex_unlock(&I.mtx);
    ZKBLE_LOG("GATT 就绪：发现 %zu 个服务", svcs.size());
    completeOp(gen, ERR_OK, "已连接");
    internal::fireConnectionChange(I.connected_id, true);
}

void clientReadyTimeoutCb(int id, void* user_data) {
    (void)id;
    const uint32_t gen = (uint32_t)(uintptr_t)user_data;
    Impl& I = impl();
    I.client.ready_timeout_id = -1;
    ZKBLE_LOG("等 GATT 发现就绪超时（%dms）", I.cfg.op_timeout_ms);
    clientTeardownInLoop(true);
    completeOp(gen, ERR_TIMEOUT, "连接后等 GATT 服务发现就绪超时（链路不稳 / 对端没响应）");
}

void clientAttDisconnectCb(int err, void* user_data) {
    (void)user_data;
    Impl& I = impl();
    if (I.client.closing) return;         // 我们自己拆的，不要递归
    ZKBLE_LOG("中心侧链路断开：%s", strerror(err));
    std::string id;
    pthread_mutex_lock(&I.mtx);
    id = I.connected_id;
    I.connected_id.clear();
    I.connected = false;
    I.services.clear();
    pthread_mutex_unlock(&I.mtx);
    clientTeardownInLoop(false);
    internal::fireConnectionChange(id, false);
}

void clientTeardownInLoop(bool disconnectAcl) {
    Impl& I = impl();
    I.client.closing = true;
    if (I.client.ready_timeout_id >= 0) {
        mainloop_remove_timeout(I.client.ready_timeout_id);
        I.client.ready_timeout_id = -1;
    }
    if (I.client.gatt) {
        bt_gatt_client_cancel_all(I.client.gatt);
        bt_gatt_client_unref(I.client.gatt);   // 它自己持有的 db 引用在这里释放
        I.client.gatt = NULL;
    }
    if (I.client.att) {
        bt_att_set_close_on_unref(I.client.att, true);
        bt_att_unref(I.client.att);            // 顺带关 fd
        I.client.att = NULL;
    } else if (I.client.fd >= 0) {
        close(I.client.fd);
    }
    if (I.client.db) {                         // ★我们自己那份 db 引用
        gatt_db_unref(I.client.db);
        I.client.db = NULL;
    }
    I.client.fd = -1;
    I.client.ready = false;
    I.notify_ids.clear();

    if (disconnectAcl && I.acl_handle != 0) {
        const int dd = hciOpen();
        if (dd >= 0) {
            errno = 0;
            const int rc = hci_disconnect(dd, I.acl_handle, kHciDisconnReason, 3000);
            const int e = errno;
            hci_close_dev(dd);
            if (rc < 0) {
                // 实测：这里经常返 EIO —— 就是「控制器残留链路」的直接证据
                ZKBLE_LOG("LE Disconnect(handle=%u) 失败 errno=%d（%s）→ 疑似控制器残留链路",
                          (unsigned)I.acl_handle, e, strerror(e));
                I.hint = "断开时 LE Disconnect 返 errno=" + std::to_string(e) +
                         "（EIO=5 常见）：AIC 控制器残留链路；下次连接前会按配置 hciconfig hci0 reset。";
                if (I.cfg.reset_before_retry) resetController();
            } else {
                ZKBLE_LOG("LE Disconnect(handle=%u) OK（干净断开）", (unsigned)I.acl_handle);
            }
        } else {
            ZKBLE_LOG("WARN: 断开时打不开 hci0，ACL handle=%u 没断干净", (unsigned)I.acl_handle);
        }
    }
    I.acl_handle = 0;
    I.client.closing = false;
}

// 一次连接尝试：hci_le_create_conn → L2CAP ATT → bt_att + gatt_client
// 返回 true = 已进入「等 GATT 就绪」阶段（结果由 clientReadyCb / ready 超时收尾）
//
// [未真机验证] ★「先 hci_le_create_conn 建 ACL、再 L2CAP ATT connect」这个**组合顺序**还没在整机
//   验证过：两条路各自都在 Z21 真机上跑通过（`hcitool cmd 0x08 0x000d` 建链 / `hcitool lecc`
//   就是第 2 步），但组合起来用没有先例。这样写的收益是能拿到 0x0B 这种「残留链路」的明确证据。
//   如果真机上发现组合反而让建链变差，把第 1 步整段删掉即可 —— 第 2 步自己就能把 LE 链建起来。
bool connectOnceInLoop(const internal::CachedDevice& cd, uint32_t gen, std::string* why) {
    Impl& I = impl();
    const int t = I.cfg.op_timeout_ms > 0 ? I.cfg.op_timeout_ms : 8000;

    bdaddr_t addr;
    memset(&addr, 0, sizeof(addr));
    if (str2ba(cd.info.id.c_str(), &addr) != 0) {
        *why = "地址解析失败: " + cd.info.id;
        return false;
    }

    // 1) 控制器层发起 LE 连接。这一步既是执行、也是「有没有残留链路」的探针：
    //    errno=0x0B(Connection Already Exists) 明确说明链路上还残留着旧连接。
    const int dd = hciOpen();
    if (dd < 0) {
        *why = "hci_open_dev 失败（hci0 没 up 或权限不足）";
        return false;
    }
    uint16_t handle = 0;
    errno = 0;
    const int cr = hci_le_create_conn(dd, htobs(0x0010), htobs(0x0010), 0, cd.addr_type, addr,
                                      LE_PUBLIC_ADDRESS,
                                      htobs(0x0018), htobs(0x0028), 0, htobs(0x00C8),
                                      0, 0, &handle, kCreateConnTimeout);
    const int cerr = errno;
    hci_close_dev(dd);
    if (cr < 0) {
        if (cerr == 0x0B) {
            ZKBLE_LOG("LE Create Connection 返 0x0B（Connection Already Exists）→ 控制器残留链路");
            *why = "LE Create Connection 返 0x0B（Connection Already Exists）—— 控制器残留链路";
        } else {
            ZKBLE_LOG("LE Create Connection 失败 errno=%d（%s）", cerr, strerror(cerr));
            *why = "LE Create Connection 失败 errno=" + std::to_string(cerr) + "（" + strerror(cerr) + "）";
        }
        // 0x0B 时链路其实"已经在"，下面的 L2CAP connect 反而可能连上 → 不 return，继续试
        I.acl_handle = 0;
    } else {
        I.acl_handle = handle;
        ZKBLE_LOG("LE 连接已建立 handle=%u", (unsigned)handle);
    }

    // 2) ATT 通道（L2CAP 固定 CID=4）。真机实测这条路自己也能把 LE 连接建起来
    //    （hcitool lecc 走的就是它）→ 上面 0x0B 的情况这里仍有机会成功。
    const int fd = l2capAttConnect(addr, cd.addr_type, t);
    if (fd < 0) {
        *why = std::string("L2CAP ATT 连接失败（") + strerror(errno) + "）";
        return false;
    }

    I.client.fd = fd;
    I.client.att = bt_att_new(fd, false);
    if (!I.client.att) {
        close(fd);
        I.client.fd = -1;
        *why = "bt_att_new 失败（ATT 传输层初始化失败）";
        return false;
    }
    bt_att_set_close_on_unref(I.client.att, true);
    if (!bt_att_register_disconnect(I.client.att, clientAttDisconnectCb, NULL, NULL)) {
        *why = "bt_att_register_disconnect 失败";
        clientTeardownInLoop(false);
        return false;
    }
    I.client.db = gatt_db_new();
    if (!I.client.db) {
        *why = "gatt_db_new 失败";
        clientTeardownInLoop(false);
        return false;
    }
    I.client.gatt = bt_gatt_client_new(I.client.db, I.client.att, 0);
    if (!I.client.gatt) {
        *why = "bt_gatt_client_new 失败";
        clientTeardownInLoop(false);
        return false;
    }
    // ★不在这里 unref db：client 自己也 ref 了一份，我们这份留给 teardown 统一释放

    if (!bt_gatt_client_ready_register(I.client.gatt, clientReadyCb, (void*)(uintptr_t)gen, NULL)) {
        *why = "bt_gatt_client_ready_register 失败";
        clientTeardownInLoop(true);
        return false;
    }
    I.client.ready_timeout_id = mainloop_add_timeout((unsigned int)t, clientReadyTimeoutCb,
                                                     (void*)(uintptr_t)gen, NULL);
    ZKBLE_LOG("已连上 ATT，等 GATT 全量发现（超时 %dms）", t);
    return true;
}

void doConnectInLoop(const std::string& device_id, uint32_t gen) {
    Impl& I = impl();
    internal::CachedDevice cd;
    if (!I.cache.find(device_id, cd)) {
        completeOp(gen, ERR_NOT_FOUND,
                   "设备不在扫描缓存里：" + device_id + "（先 startDiscovery 等它出现，或核对 MAC）");
        return;
    }
    scanStopInLoop();

    const int attempts = I.cfg.connect_retry > 0 ? I.cfg.connect_retry : 1;
    std::string why;
    for (int a = 1; a <= attempts; a++) {
        I.connect_attempts = a;
        if (a > 1 && I.cfg.reset_before_retry) {
            ZKBLE_LOG("第 %d/%d 次连接前先复位控制器（上次失败：%s）", a, attempts, why.c_str());
            resetController();
        } else if (a > 1) {
            ZKBLE_LOG("第 %d/%d 次连接（未开 reset_before_retry；实测复位更稳）", a, attempts);
        }
        why.clear();
        if (connectOnceInLoop(cd, gen, &why)) {
            pthread_mutex_lock(&I.mtx);
            I.connected_id = device_id;
            pthread_mutex_unlock(&I.mtx);
            return;                    // 收尾交给 clientReadyCb / ready 超时回调
        }
        ZKBLE_LOG("连接尝试 %d/%d 失败：%s", a, attempts, why.c_str());
    }

    const std::string msg = "连接失败：" + why + "｜疑似控制器残留链路（LE Create Connection 返 0x0B / "
                            "LE Disconnect 返 EIO），已重试 " + std::to_string(attempts) + " 次" +
                            (I.cfg.reset_before_retry ? "（每次重试前都 hciconfig hci0 reset）"
                                                     : "（未开 reset_before_retry，建议打开）");
    I.hint = msg + "；可先手动 `hciconfig hci0 reset` 或断电重启模组再试";
    setError(ERR_DISCONNECTED, msg);
    completeOp(gen, ERR_DISCONNECTED, msg);
}

void doDisconnectInLoop() {
    Impl& I = impl();
    std::string id;
    pthread_mutex_lock(&I.mtx);
    id = I.connected_id;
    pthread_mutex_unlock(&I.mtx);
    clientTeardownInLoop(true);
    pthread_mutex_lock(&I.mtx);
    I.connected = false;
    I.connected_id.clear();
    I.services.clear();
    pthread_mutex_unlock(&I.mtx);
    if (!id.empty()) internal::fireConnectionChange(id, false);
    ZKBLE_LOG("已断开");
}

// ================================================================ 中心侧：服务/读写/订阅
void snapshotServicesInLoop() {
    Impl& I = impl();
    std::vector<Service> svcs;
    if (I.client.ready) walkDb(I.client.db, svcs);
    pthread_mutex_lock(&I.mtx);
    I.services = svcs;
    I.req.services = svcs;
    pthread_mutex_unlock(&I.mtx);
}

void readCb(bool success, uint8_t att_ecode, const uint8_t* value, uint16_t length, void* user_data) {
    const uint32_t gen = (uint32_t)(uintptr_t)user_data;
    Impl& I = impl();
    if (!success) {
        completeOp(gen, ERR_IO, "读失败 att_ecode=0x" + std::to_string(att_ecode));
        return;
    }
    pthread_mutex_lock(&I.mtx);
    I.req.data.assign((const char*)value, length);
    pthread_mutex_unlock(&I.mtx);
    completeOp(gen, ERR_OK, "");
}

void writeCb(bool success, uint8_t att_ecode, void* user_data) {
    const uint32_t gen = (uint32_t)(uintptr_t)user_data;
    if (!success) {
        completeOp(gen, ERR_IO, "写失败 att_ecode=0x" + std::to_string(att_ecode));
        return;
    }
    completeOp(gen, ERR_OK, "");
}

void notifyCb(uint16_t value_handle, const uint8_t* value, uint16_t length, void* user_data) {
    (void)user_data;
    Impl& I = impl();
    Value v;
    v.data.assign((const char*)value, length);
    pthread_mutex_lock(&I.mtx);
    v.device_id = I.connected_id;
    bool found = false;
    for (size_t i = 0; i < I.services.size() && !found; i++) {
        for (size_t j = 0; j < I.services[i].characteristics.size(); j++) {
            if ((uint16_t)I.services[i].characteristics[j].value_handle == value_handle) {
                v.service_uuid = I.services[i].uuid;
                v.char_uuid = I.services[i].characteristics[j].uuid;
                found = true;
                break;
            }
        }
    }
    pthread_mutex_unlock(&I.mtx);
    if (!found) {
        ZKBLE_LOG("收到 notify，但 handle=0x%04x 不在已发现的服务表里（照实上报，uuid 留空）",
                  (unsigned)value_handle);
    }
    internal::fireValueChange(v);
}

void registerNotifyCb(uint16_t att_ecode, void* user_data) {
    const uint32_t gen = (uint32_t)(uintptr_t)user_data;
    if (att_ecode != 0) {
        completeOp(gen, ERR_IO, "订阅失败 att_ecode=0x" + std::to_string(att_ecode) +
                                "（对端没给 CCCD / 特征没开 notify？）");
        return;
    }
    completeOp(gen, ERR_OK, "订阅成功");
}

void doReadInLoop(uint16_t vh, uint32_t gen) {
    Impl& I = impl();
    bt_gatt_client_cancel_all(I.client.gatt);      // 清掉可能残留的旧请求
    const unsigned int id = bt_gatt_client_read_value(I.client.gatt, vh, readCb,
                                                      (void*)(uintptr_t)gen, NULL);
    if (id == 0) completeOp(gen, ERR_BUSY, "读请求投递失败（客户端忙或链路已断）");
}

void doWriteInLoop(uint16_t vh, const std::string& data, bool with_response, uint32_t gen) {
    Impl& I = impl();
    bt_gatt_client_cancel_all(I.client.gatt);
    if (with_response) {
        const unsigned int id = bt_gatt_client_write_value(I.client.gatt, vh,
                                                           (const uint8_t*)data.data(),
                                                           (uint16_t)data.size(), writeCb,
                                                           (void*)(uintptr_t)gen, NULL);
        if (id == 0) completeOp(gen, ERR_BUSY, "写请求投递失败（客户端忙或链路已断）");
    } else {
        const unsigned int id = bt_gatt_client_write_without_response(
            I.client.gatt, vh, false, (const uint8_t*)data.data(), (uint16_t)data.size());
        if (id == 0) completeOp(gen, ERR_BUSY, "无响应写投递失败（客户端忙或链路已断）");
        else completeOp(gen, ERR_OK, "已发出（无响应写，不保证对端收到）");
    }
}

void doSubscribeInLoop(uint16_t vh, bool enable, uint32_t gen) {
    Impl& I = impl();
    if (enable) {
        const unsigned int id = bt_gatt_client_register_notify(I.client.gatt, vh, registerNotifyCb,
                                                               notifyCb,
                                                               (void*)(uintptr_t)gen, NULL);
        if (id == 0) {
            completeOp(gen, ERR_IO, "订阅失败：register_notify 返回 0（对端没有 CCCD？）");
            return;
        }
        I.notify_ids[vh] = id;
    } else {
        std::map<uint16_t, unsigned int>::iterator it = I.notify_ids.find(vh);
        if (it == I.notify_ids.end()) {
            completeOp(gen, ERR_NOT_FOUND, "该特征没有订阅记录（没订阅过或已断开）");
            return;
        }
        const bool ok = bt_gatt_client_unregister_notify(I.client.gatt, it->second);
        I.notify_ids.erase(it);
        if (!ok) completeOp(gen, ERR_IO, "注销订阅失败（unregister_notify 返回 false）");
        else completeOp(gen, ERR_OK, "已注销订阅");
    }
}

// 在已发现的服务表里按 uuid 找 value handle（0 = 没找到）。调用时必须已持有 I.mtx。
uint16_t findValueHandle(const std::string& svc, const std::string& chr) {
    Impl& I = impl();
    for (size_t i = 0; i < I.services.size(); i++) {
        if (!svc.empty() && I.services[i].uuid != svc) continue;
        for (size_t j = 0; j < I.services[i].characteristics.size(); j++) {
            if (I.services[i].characteristics[j].uuid == chr) {
                return (uint16_t)I.services[i].characteristics[j].value_handle;
            }
        }
    }
    return 0;
}

// ================================================================ 外设侧命令
void doPeriphStartInLoop(const PeripheralConfig& cfg, uint32_t gen) {
    Impl& I = impl();
    if (I.periph_on) { completeOp(gen, ERR_BUSY, "外设已经在跑（先 peripheral::stop()）"); return; }
    if (I.connected) { completeOp(gen, ERR_BUSY, "当前有中心侧连接，先 disconnect() 再切外设模式"); return; }

    std::string err;
    if (!periphBuildDb(cfg, &err)) {
        if (I.pdb) { gatt_db_unref(I.pdb); I.pdb = NULL; }
        completeOp(gen, ERR_PARAM, err);
        return;
    }
    I.periph_name = cfg.device_name;
    I.periph_svc = internal::normalizeUuid(cfg.service_uuid);

    I.plisten_fd = periphListen();
    if (I.plisten_fd < 0) {
        gatt_db_unref(I.pdb);
        I.pdb = NULL;
        completeOp(gen, ERR_IO, "ATT 监听失败（日志里有 errno：bind CID=4 失败通常是别的进程占着 ATT）");
        return;
    }
    if (mainloop_add_fd(I.plisten_fd, EPOLLIN, periphListenCb, NULL, NULL) < 0) {
        ZKBLE_LOG("mainloop_add_fd(监听 socket) 失败");
        close(I.plisten_fd);
        I.plisten_fd = -1;
        gatt_db_unref(I.pdb);
        I.pdb = NULL;
        completeOp(gen, ERR_IO, "监听 socket 注册进主循环失败");
        return;
    }

    if (cfg.auto_adv) {
        // 【bug C 修正】改广播参数/数据前总是先关广播（status=12 的根因就是「已在广播」），
        // 被拒则复位控制器重试一次；仍失败走 Result/Diag，不静默。
        advForceDisableForSetup("peripheral::start");
        if (!advStepWithRecover(advSetParamsStep, "广播参数设置(LE Set Advertising Parameters)", &err)) {
            periphStopInLoop();
            completeOp(gen, ERR_IO, "广播参数设置失败：" + err);
            return;
        }
        if (!advStepWithRecover(advSetDataStep, "广播数据设置(LE Set Advertising Data)", &err)) {
            periphStopInLoop();
            completeOp(gen, ERR_IO, "广播数据设置失败：" + err);
            return;
        }
        if (advEnableChecked(true, &err) != 0) {
            periphStopInLoop();
            completeOp(gen, ERR_IO, "开广播失败：" + err);
            return;
        }
        I.periph_on = true;
    }
    ZKBLE_LOG("外设已启动：name=%s service=%s adv=%d",
              cfg.device_name.c_str(), cfg.service_uuid.c_str(), cfg.auto_adv ? 1 : 0);
    completeOp(gen, ERR_OK, "外设已启动");
}

void doPeriphNotifyInLoop(const std::string& char_uuid, const std::string& data, uint32_t gen) {
    Impl& I = impl();
    if (!I.periph_on || !I.pserver) { completeOp(gen, ERR_NOT_INIT, "外设没在跑（先 peripheral::start()）"); return; }
    const std::string want = internal::normalizeUuid(char_uuid);
    uint16_t vh = 0;
    for (size_t i = 0; i < I.pchars.size(); i++) {
        if (I.pchars[i].uuid == want) { vh = I.pchars[i].value_handle; break; }
    }
    if (vh == 0) { completeOp(gen, ERR_NOT_FOUND, "特征不存在（不在本外设表里）: " + char_uuid); return; }
    if (!I.periph_connected) {
        completeOp(gen, ERR_DISCONNECTED, "还没有中心连接：notify 要等中心连上并订阅（CCCD）才发得出去");
        return;
    }
    // 未订阅时 bt_gatt_server_send_notification 返回 false → 如实报错，不假装发成功
    if (!bt_gatt_server_send_notification(I.pserver, vh, (const uint8_t*)data.data(),
                                          (uint16_t)data.size())) {
        completeOp(gen, ERR_IO,
                   "notify 失败：中心没有订阅该特征（写 CCCD 0x2902）或链路已断（value_handle=" +
                   std::to_string(vh) + "）");
        return;
    }
    ZKBLE_LOG("notify 已发出：char=%s len=%zu", want.c_str(), data.size());
    completeOp(gen, ERR_OK, "");
}

void doPeriphSetNameInLoop(const std::string& name, uint32_t gen) {
    Impl& I = impl();
    if (!I.periph_on) { completeOp(gen, ERR_NOT_INIT, "外设没在跑（先 peripheral::start()）"); return; }
    if (name.empty()) { completeOp(gen, ERR_PARAM, "设备名不能为空"); return; }

    // 广播中改名必须「先停 → 改数据 → 再开」，否则改的是下一轮的参数，广播里还是旧名字。
    // 同口径：先强制关广播；数据设置被拒 → 复位控制器重试一次；仍失败如实上报。
    std::string err;
    advForceDisableForSetup("peripheral::setDeviceName");
    const std::string old_name = I.periph_name;
    I.periph_name = name;               // advSetDataStep 取的是 Impl 里的名字
    if (!advStepWithRecover(advSetDataStep, "广播数据设置(改名)", &err)) {
        I.periph_name = old_name;
        completeOp(gen, ERR_IO, "改名失败（广播数据设置失败）：" + err);
        return;
    }
    if (advEnableChecked(true, &err) != 0) {
        I.periph_on = false;
        completeOp(gen, ERR_IO, "改名后重新开广播失败：" + err);
        return;
    }
    ZKBLE_LOG("广播名已更新为：%s", name.c_str());
    completeOp(gen, ERR_OK, "设备名已更新");
}

// ================================================================ 命令分发（后端线程内）
void dispatchInLoop(int kind, uint32_t gen) {
    Impl& I = impl();
    std::string s1, s2, data;
    bool flag = true;
    switch (kind) {
    case CMD_SCAN_START: {
        std::string msg;
        const int rc = scanStartInLoop(&msg);
        if (rc == ERR_OK) {
            completeOp(gen, ERR_OK, "扫描已开始（结果走 onDeviceFound；duration_ms>0 会自动停）");
        } else {
            setError(rc, msg);
            completeOp(gen, rc, msg);
        }
        break;
    }
    case CMD_SCAN_STOP:
        scanStopInLoop();
        completeOp(gen, ERR_OK, "");
        break;
    case CMD_CONNECT:
        pthread_mutex_lock(&I.mtx);
        s1 = I.req.s1;
        pthread_mutex_unlock(&I.mtx);
        doConnectInLoop(s1, gen);
        break;
    case CMD_DISCONNECT:
        doDisconnectInLoop();
        completeOp(gen, ERR_OK, "已断开");
        break;
    case CMD_GET_SERVICES:
        if (!I.client.ready) {
            completeOp(gen, ERR_DISCONNECTED, "链路未就绪（先 connect）");
            break;
        }
        snapshotServicesInLoop();
        if (I.services.empty()) completeOp(gen, ERR_NOT_FOUND, "对端没有可发现的服务（或链路已断）");
        else completeOp(gen, ERR_OK, "");
        break;
    case CMD_READ: {
        pthread_mutex_lock(&I.mtx);
        s1 = I.req.s1;
        s2 = I.req.char_uuid;
        const uint16_t vh = findValueHandle(s1, s2);
        pthread_mutex_unlock(&I.mtx);
        if (vh == 0) completeOp(gen, ERR_NOT_FOUND, "特征不存在（先 getServices）: " + s2);
        else doReadInLoop(vh, gen);
        break;
    }
    case CMD_WRITE: {
        pthread_mutex_lock(&I.mtx);
        s1 = I.req.s1;
        s2 = I.req.char_uuid;
        data = I.req.in_data;          // ★入参载荷（不能读 data，它上面已被清）
        flag = I.req.flag;
        const uint16_t vh = findValueHandle(s1, s2);
        pthread_mutex_unlock(&I.mtx);
        if (vh == 0) completeOp(gen, ERR_NOT_FOUND, "特征不存在（先 getServices）: " + s2);
        else doWriteInLoop(vh, data, flag, gen);
        break;
    }
    case CMD_SUBSCRIBE: {
        pthread_mutex_lock(&I.mtx);
        s1 = I.req.s1;
        s2 = I.req.char_uuid;
        flag = I.req.flag;
        const uint16_t vh = findValueHandle(s1, s2);
        pthread_mutex_unlock(&I.mtx);
        if (vh == 0) completeOp(gen, ERR_NOT_FOUND, "特征不存在（先 getServices）: " + s2);
        else doSubscribeInLoop(vh, flag, gen);
        break;
    }
    case CMD_PERIPH_START: {
        PeripheralConfig cfg;
        pthread_mutex_lock(&I.mtx);
        cfg = I.req.pcfg;
        pthread_mutex_unlock(&I.mtx);
        doPeriphStartInLoop(cfg, gen);
        break;
    }
    case CMD_PERIPH_STOP:
        periphStopInLoop();
        completeOp(gen, ERR_OK, "外设已停止");
        break;
    case CMD_PERIPH_SETNAME:
        pthread_mutex_lock(&I.mtx);
        s1 = I.req.s1;
        pthread_mutex_unlock(&I.mtx);
        doPeriphSetNameInLoop(s1, gen);
        break;
    case CMD_PERIPH_NOTIFY:
        pthread_mutex_lock(&I.mtx);
        s1 = I.req.char_uuid;
        data = I.req.in_data;          // ★同上：入参载荷走 in_data
        pthread_mutex_unlock(&I.mtx);
        doPeriphNotifyInLoop(s1, data, gen);
        break;
    default:
        ZKBLE_LOG("收到未知命令 %d（不静默：如实回错）", kind);
        completeOp(gen, ERR_PARAM, "未知命令 " + std::to_string(kind));
        break;
    }
}

void ctrlCb(int fd, uint32_t events, void* user_data) {
    (void)events; (void)user_data;
    Impl& I = impl();
    CmdHdr h;
    memset(&h, 0, sizeof(h));
    const ssize_t n = read(fd, &h, sizeof(h));
    if (n != (ssize_t)sizeof(h)) {
        ZKBLE_LOG("控制通道读到 %zd 字节（期望 %zu）—— 命令可能被截断，丢弃本轮", n, sizeof(h));
        return;
    }
    if (h.kind == CMD_QUIT) {
        ZKBLE_LOG("收到 QUIT：收尾后退出主循环");
        scanStopInLoop();
        if (I.connected) doDisconnectInLoop();
        periphStopInLoop();
        I.ready = false;
        I.hci_state = 0;
        mainloop_quit();
        return;
    }
    dispatchInLoop(h.kind, h.gen);
}

// ================================================================ 后端线程
void* backendThread(void*) {
    Impl& I = impl();
    mainloop_init();
    mainloop_add_fd(I.ctrl_fds[0], EPOLLIN, ctrlCb, NULL, NULL);
    ZKBLE_LOG("后端线程进入 mainloop（epoll）");
    mainloop_run();
    ZKBLE_LOG("后端线程退出 mainloop");
    return NULL;
}

bool ensureThread() {
    Impl& I = impl();
    if (I.thread_started) return true;
    if (socketpair(PF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0, I.ctrl_fds) < 0) {
        setError(ERR_IO, std::string("socketpair 创建失败 errno=") + strerror(errno));
        return false;
    }
    if (pthread_create(&I.thread, NULL, backendThread, NULL) != 0) {
        setError(ERR_IO, "后端线程创建失败");
        close(I.ctrl_fds[0]);
        close(I.ctrl_fds[1]);
        I.ctrl_fds[0] = I.ctrl_fds[1] = -1;
        return false;
    }
    I.thread_started = true;
    return true;
}

}  // namespace

// ================================================================ 公开接口：适配器
std::string backendName() { return std::string("gatt"); }

Result getCapabilities(Capabilities& out) {
    out.central = true;
    out.peripheral = true;
    out.notify = true;
    out.bonded_db = false;      // 本后端不落 TLV（配对信息在控制器/内核侧，门面不假装有）
    out.backend = "gatt";
    out.note = "AIC USB 模组 + BlueZ 用户态 GATT，中心/外设双角色；"
               "配对信息不落盘 → getBondedDevices / deleteBonding 返回 ERR_UNSUPPORTED；"
               "预初始化钩子不适用（走 aic_btusb.ko + hciconfig，不经 hciattach）；"
               "连接不稳的已知根因见 platforms.md §0.3（控制器残留链路），本后端已内置重试 + 复位。";
    return Result::ok_();
}

void setPreinitHook(PreinitHook hook) {
    Impl& I = impl();
    I.preinit = hook;
    ZKBLE_LOG("gatt 后端不需要预初始化（AIC USB 模组由 aic_btusb.ko + hciconfig 拉起）："
              "setPreinitHook 的钩子被保存但不会调用");
}

Result openAdapter(const Config& cfg) {
    Impl& I = impl();
    if (I.opened) return Result::ok_("已经打开");

    I.cfg = cfg;
    const std::string prop = cfg.module.empty() ? internal::readProp("persist.wifi.module") : cfg.module;
    I.chip = prop.empty() ? "AIC USB 模组（未读到 persist.wifi.module）" : prop + "（AIC USB 模组）";
    I.route = "USB HCI（aic_btusb.ko / hciattach 服务）+ BlueZ 用户态 GATT";
    I.hint = "正在拉起 AIC 蓝牙通路（insmod aic_btusb.ko → hciconfig hci0 up → 起后端线程）…";
    I.hci_state = 1;
    I.last_error = 0;
    I.last_error_msg.clear();
    I.connect_attempts = 0;
    I.cache.clear();
    pthread_mutex_lock(&I.mtx);
    I.services.clear();
    pthread_mutex_unlock(&I.mtx);

    if (cfg.auto_power) {
        std::string err;
        if (hciUp(err) != 0) {
            I.hint = "拉起 AIC 蓝牙失败：" + err;
            I.hci_state = 0;
            setError(ERR_POWER_OFF, I.hint);
            return Result::err(ERR_POWER_OFF, I.hint);
        }
    } else if (!hciIfaceExists()) {
        I.hint = "auto_power=false 且 /sys/class/bluetooth/hci0 不存在：请自行 insmod + hciconfig hci0 up";
        setError(ERR_POWER_OFF, I.hint);
        return Result::err(ERR_POWER_OFF, I.hint);
    }
    I.powered = hciIfaceExists();

    if (!ensureThread()) {
        I.hint = "后端线程起不来（见 last_error_msg）";
        return Result::err(ERR_IO, I.hint);
    }

    // 先自己打一次 HCI socket 验证通路真的可用（不留给业务"提交任务才发现打不开"）
    const int dd = hciOpen();
    if (dd < 0) {
        I.hint = "hci0 存在但 hci_open_dev 打不开：权限问题？驱动半挂？";
        setError(ERR_POWER_OFF, I.hint);
        return Result::err(ERR_POWER_OFF, I.hint);
    }
    hci_close_dev(dd);

    I.preinit_ok = true;
    I.ready = true;
    I.hci_state = 2;          // gatt 路线没有 btstack 的 WORKING 状态机；2 = 就绪（与 btstack 后端同义）
    I.opened = true;
    I.hint = "就绪：可以 startDiscovery() / connect()；外设用 peripheral::start()。"
             "（本后端不落 TLV，配对信息不落盘）";
    ZKBLE_LOG("适配器就绪：chip=%s route=%s", I.chip.c_str(), I.route.c_str());
    return Result::ok_("适配器就绪");
}

void closeAdapter() {
    Impl& I = impl();
    if (!I.opened) return;
    if (I.thread_started) {
        // 断开 + 停扫描 + 停外设 + 退 mainloop 全在后端线程里做（照 btstack 后端的收尾顺序）
        if (!writeCmd(CMD_QUIT, 0)) ZKBLE_LOG("WARN: QUIT 投递失败，直接 join（线程可能已退出）");
        pthread_join(I.thread, NULL);
        I.thread_started = false;
    }
    if (I.ctrl_fds[0] >= 0) close(I.ctrl_fds[0]);
    if (I.ctrl_fds[1] >= 0) close(I.ctrl_fds[1]);
    I.ctrl_fds[0] = I.ctrl_fds[1] = -1;

    hciDown();
    I.opened = false;
    I.ready = false;
    I.powered = false;
    I.preinit_ok = false;
    I.discovering = false;
    I.connected = false;
    I.connected_id.clear();
    I.hci_state = 0;
    pthread_mutex_lock(&I.mtx);
    I.services.clear();
    I.req_busy = false;
    pthread_mutex_unlock(&I.mtx);
    I.hint = "已关闭（hciconfig hci0 down；未 rmmod aic_btusb，避免影响 WiFi）";
    ZKBLE_LOG("适配器已关闭");
}

bool adapterReady() { return impl().ready; }

Result getAdapterState(AdapterState& out) {
    Impl& I = impl();
    pthread_mutex_lock(&I.mtx);
    out.available = I.ready;
    out.discovering = I.discovering;
    out.power_on = I.powered;
    pthread_mutex_unlock(&I.mtx);
    return Result::ok_();
}

// ================================================================ 公开接口：扫描
Result startDiscovery(const ScanOptions& opts) {
    Impl& I = impl();
    if (!I.opened) return Result::err(ERR_NOT_INIT, "先 openAdapter()");
    if (!I.ready) return Result::err(ERR_POWER_OFF, "适配器未就绪 —— 看 getDiag().hint");
    pthread_mutex_lock(&I.mtx);
    const bool busy = I.discovering;
    I.scan_opts = opts;
    pthread_mutex_unlock(&I.mtx);
    if (busy) return Result::err(ERR_BUSY, "正在扫描，先 stopDiscovery()");

    const int rc = submitAndWait(CMD_SCAN_START, 3000, "startDiscovery");
    if (rc == 1) return Result::err(ERR_TIMEOUT, "扫描启动超时（后端线程没响应）");
    if (rc == 2) return Result::err(ERR_BUSY, "上一动作还没结束，稍后再试");
    if (rc == 3) return Result::err(ERR_IO, "命令投递失败（后端线程没在跑）");
    pthread_mutex_lock(&I.mtx);
    const int st = I.req.status;
    const std::string msg = I.req.msg;
    pthread_mutex_unlock(&I.mtx);
    if (st != ERR_OK) return Result::err(st, msg);
    return Result::ok_("扫描已开始");
}

Result stopDiscovery() {
    Impl& I = impl();
    if (!I.opened || !I.ready) return Result::err(ERR_NOT_INIT, "适配器未就绪");
    const int rc = submitAndWait(CMD_SCAN_STOP, 3000, "stopDiscovery");
    if (rc == 1) return Result::err(ERR_TIMEOUT, "停止扫描超时");
    if (rc != 0) return Result::err(ERR_BUSY, "上一动作还没结束，稍后再试");
    return Result::ok_();
}

Result getDevices(std::vector<DeviceInfo>& out) {
    impl().cache.snapshot(out);
    return Result::ok_();
}

Result clearDevices() {
    impl().cache.clear();
    return Result::ok_();
}

// ================================================================ 公开接口：连接 + 服务发现
Result connect(const std::string& device_id, int timeout_ms) {
    Impl& I = impl();
    if (!I.opened) return Result::err(ERR_NOT_INIT, "先 openAdapter()");
    if (!I.ready) return Result::err(ERR_POWER_OFF, "适配器未就绪（看 getDiag().hint）");
    if (isConnected(std::string())) return Result::err(ERR_BUSY, "已有连接，先 disconnect()");
    const int t = timeout_ms > 0 ? timeout_ms : (I.cfg.op_timeout_ms > 0 ? I.cfg.op_timeout_ms : 8000);

    pthread_mutex_lock(&I.mtx);
    I.req.s1 = device_id;
    I.connect_attempts = 0;
    pthread_mutex_unlock(&I.mtx);
    I.connect_attempts = 0;

    // 一次 connect 内部可能重试 N 次（每次 5s 建链 + 等发现），总超时给够
    const int attempts = I.cfg.connect_retry > 0 ? I.cfg.connect_retry : 1;
    const int total = t * attempts + (I.cfg.reset_before_retry ? attempts * 500 : 0) + 3000;

    const int rc = submitAndWait(CMD_CONNECT, total, "connect");
    if (rc == 1) {
        setError(ERR_TIMEOUT, "连接整体超时: " + device_id);
        return Result::err(ERR_TIMEOUT,
                           "连接超时: " + device_id + "（设备在广播吗？距离？connectable？另见 getDiag()）");
    }
    if (rc == 2) return Result::err(ERR_BUSY, "上一动作还没结束，稍后再试");
    if (rc == 3) return Result::err(ERR_IO, "命令投递失败（后端线程没在跑）");

    pthread_mutex_lock(&I.mtx);
    const int st = I.req.status;
    const std::string msg = I.req.msg;
    pthread_mutex_unlock(&I.mtx);
    if (st == ERR_OK) return Result::ok_("已连接（服务已全量发现）");
    setError(st, msg);
    return Result::err(st, msg);
}

Result disconnect(const std::string& device_id) {
    Impl& I = impl();
    if (!I.opened || !I.ready) return Result::err(ERR_NOT_INIT, "适配器未就绪");
    if (I.periph_on) return Result::err(ERR_UNSUPPORTED, "当前是外设模式，断开由中心发起");
    if (!device_id.empty()) {
        pthread_mutex_lock(&I.mtx);
        const std::string cur = I.connected_id;
        pthread_mutex_unlock(&I.mtx);
        if (cur != device_id) return Result::err(ERR_NOT_FOUND, "当前连接不是 " + device_id);
    }
    const int rc = submitAndWait(CMD_DISCONNECT, I.cfg.op_timeout_ms > 0 ? I.cfg.op_timeout_ms : 8000,
                                 "disconnect");
    if (rc == 1) return Result::err(ERR_TIMEOUT, "断开超时（链路可能已被 supervision timeout 判掉）");
    if (rc != 0) return Result::err(ERR_BUSY, "上一动作还没结束，稍后再试");
    return Result::ok_("已断开");
}

bool isConnected(const std::string& device_id) {
    Impl& I = impl();
    pthread_mutex_lock(&I.mtx);
    const bool c = I.connected;
    const std::string id = I.connected_id;
    pthread_mutex_unlock(&I.mtx);
    if (!c) return false;
    if (device_id.empty()) return true;
    return device_id == id;
}

Result getServices(const std::string& device_id, std::vector<Service>& out) {
    Impl& I = impl();
    out.clear();
    if (!isConnected(device_id)) return Result::err(ERR_DISCONNECTED, "未连接（先 connect）");
    const int rc = submitAndWait(CMD_GET_SERVICES, I.cfg.op_timeout_ms > 0 ? I.cfg.op_timeout_ms : 8000,
                                 "getServices");
    if (rc == 1) return Result::err(ERR_TIMEOUT, "取服务列表超时");
    if (rc != 0) return Result::err(ERR_BUSY, "上一动作还没结束，稍后再试");
    pthread_mutex_lock(&I.mtx);
    const int st = I.req.status;
    const std::string msg = I.req.msg;
    out = I.req.services;
    pthread_mutex_unlock(&I.mtx);
    if (st != ERR_OK) return Result::err(st, msg);
    return Result::ok_();
}

Result getCharacteristics(const std::string& device_id,
                          const std::string& service_uuid,
                          std::vector<Characteristic>& out) {
    out.clear();
    std::vector<Service> svcs;
    Result r = getServices(device_id, svcs);
    if (!r.ok()) return r;
    const std::string want = internal::normalizeUuid(service_uuid);
    for (size_t i = 0; i < svcs.size(); i++) {
        if (want.empty() || svcs[i].uuid == want) {
            out = svcs[i].characteristics;
            return Result::ok_();
        }
    }
    return Result::err(ERR_NOT_FOUND, "服务不存在: " + service_uuid);
}

// ================================================================ 公开接口：数据
Result readValue(const std::string& device_id, const std::string& service_uuid,
                 const std::string& char_uuid, std::string& out) {
    Impl& I = impl();
    out.clear();
    if (!isConnected(device_id)) return Result::err(ERR_DISCONNECTED, "未连接");
    pthread_mutex_lock(&I.mtx);
    I.req.s1 = internal::normalizeUuid(service_uuid);
    I.req.char_uuid = internal::normalizeUuid(char_uuid);
    pthread_mutex_unlock(&I.mtx);

    const int rc = submitAndWait(CMD_READ, I.cfg.op_timeout_ms > 0 ? I.cfg.op_timeout_ms : 8000,
                                 "readValue");
    if (rc == 1) return Result::err(ERR_TIMEOUT, "读超时（对端没回）");
    if (rc != 0) return Result::err(ERR_BUSY, "上一动作还没结束，稍后再试");
    pthread_mutex_lock(&I.mtx);
    const int st = I.req.status;
    const std::string msg = I.req.msg;
    out = I.req.data;
    pthread_mutex_unlock(&I.mtx);
    if (st != ERR_OK) return Result::err(st, msg);
    return Result::ok_();
}

Result writeValue(const std::string& device_id, const std::string& service_uuid,
                  const std::string& char_uuid, const std::string& data, bool with_response) {
    Impl& I = impl();
    if (!isConnected(device_id)) return Result::err(ERR_DISCONNECTED, "未连接");
    pthread_mutex_lock(&I.mtx);
    I.req.s1 = internal::normalizeUuid(service_uuid);
    I.req.char_uuid = internal::normalizeUuid(char_uuid);
    I.req.in_data = data;          // ★要写出去的载荷（入参）
    I.req.flag = with_response;
    pthread_mutex_unlock(&I.mtx);

    const int t = with_response ? (I.cfg.op_timeout_ms > 0 ? I.cfg.op_timeout_ms : 8000) : 2000;
    const int rc = submitAndWait(CMD_WRITE, t, "writeValue");
    if (rc == 1) return Result::err(ERR_TIMEOUT, "写超时（对端没回 Write Response）");
    if (rc != 0) return Result::err(ERR_BUSY, "上一动作还没结束，稍后再试");
    pthread_mutex_lock(&I.mtx);
    const int st = I.req.status;
    const std::string msg = I.req.msg;
    pthread_mutex_unlock(&I.mtx);
    if (st != ERR_OK) return Result::err(st, msg);
    return Result::ok_();
}

Result subscribe(const std::string& device_id, const std::string& service_uuid,
                 const std::string& char_uuid, bool enable) {
    Impl& I = impl();
    if (!isConnected(device_id)) return Result::err(ERR_DISCONNECTED, "未连接");
    pthread_mutex_lock(&I.mtx);
    I.req.s1 = internal::normalizeUuid(service_uuid);
    I.req.char_uuid = internal::normalizeUuid(char_uuid);
    I.req.flag = enable;
    pthread_mutex_unlock(&I.mtx);

    const int rc = submitAndWait(CMD_SUBSCRIBE, I.cfg.op_timeout_ms > 0 ? I.cfg.op_timeout_ms : 8000,
                                 "subscribe");
    if (rc == 1) return Result::err(ERR_TIMEOUT, "订阅超时（对端没回 Write Response）");
    if (rc != 0) return Result::err(ERR_BUSY, "上一动作还没结束，稍后再试");
    pthread_mutex_lock(&I.mtx);
    const int st = I.req.status;
    const std::string msg = I.req.msg;
    pthread_mutex_unlock(&I.mtx);
    if (st != ERR_OK) return Result::err(st, msg);
    return Result::ok_(enable ? "订阅成功" : "已注销订阅");
}

// ================================================================ 公开接口：配对（本后端不支持）
Result getBondedDevices(std::vector<std::string>& out) {
    out.clear();
    return Result::err(ERR_UNSUPPORTED,
        "本后端（gatt/BlueZ 用户态）不落 TLV 配对库，拿不到配对列表 —— 不假装返回空成功。"
        "配对信息在控制器/内核侧：用 `hcitool con` / 内核 debugfs 看；"
        "要 TLV 落盘请用 btstack 后端（F133/V85X，Config.tlv_path）。");
}

Result deleteBonding(const std::string& device_id) {
    (void)device_id;
    return Result::err(ERR_UNSUPPORTED,
        "本后端没有配对落盘，也就没有可删的绑定信息；要清链路用 `hciconfig hci0 reset`"
        "（本门面在 connect 重试时会自己做），或用 btstack 后端（Config.tlv_path）。");
}

// ================================================================ 公开接口：外设
namespace peripheral {

Result start(const PeripheralConfig& cfg) {
    Impl& I = impl();
    if (I.periph_on) return Result::ok_("外设已在运行");
    if (cfg.service_uuid.empty()) {
        return Result::err(ERR_PARAM, "PeripheralConfig.service_uuid 必填（如 \"fff0\"）");
    }
    if (cfg.characteristics.empty()) {
        return Result::err(ERR_PARAM, "PeripheralConfig.characteristics 至少要有一个特征");
    }

    if (!I.opened) {
        // 外设模式可独立于 openAdapter 用：自己把 HCI 通路拉起来
        Config c;
        c.auto_power = cfg.auto_power;
        Result r = openAdapter(c);
        if (!r.ok()) return r;
    } else if (!I.ready) {
        return Result::err(ERR_POWER_OFF, "适配器未就绪（看 getDiag().hint）");
    }

    pthread_mutex_lock(&I.mtx);
    I.req.pcfg = cfg;
    pthread_mutex_unlock(&I.mtx);

    const int rc = submitAndWait(CMD_PERIPH_START, 20000, "peripheral::start");
    if (rc == 1) return Result::err(ERR_TIMEOUT, "外设启动超时（广播/监听装配没在 20s 内完成）");
    if (rc == 2) return Result::err(ERR_BUSY, "上一动作还没结束，稍后再试");
    if (rc == 3) return Result::err(ERR_IO, "命令投递失败（后端线程没在跑）");
    pthread_mutex_lock(&I.mtx);
    const int st = I.req.status;
    const std::string msg = I.req.msg;
    pthread_mutex_unlock(&I.mtx);
    if (st != ERR_OK) return Result::err(st, msg);
    return Result::ok_("外设已启动（广播中，等中心连接）");
}

Result stop() {
    Impl& I = impl();
    if (!I.opened || !I.ready) return Result::err(ERR_NOT_INIT, "适配器未就绪");
    if (!I.periph_on) return Result::ok_("外设本来就没在跑");
    const int rc = submitAndWait(CMD_PERIPH_STOP, 5000, "peripheral::stop");
    if (rc == 1) return Result::err(ERR_TIMEOUT, "停止外设超时");
    if (rc != 0) return Result::err(ERR_BUSY, "上一动作还没结束，稍后再试");
    return Result::ok_("外设已停止（适配器仍可用）");
}

Result setDeviceName(const std::string& name) {
    Impl& I = impl();
    if (!I.opened || !I.ready) return Result::err(ERR_NOT_INIT, "适配器未就绪");
    if (!I.periph_on) return Result::err(ERR_NOT_INIT, "外设没在跑（先 peripheral::start()）");
    pthread_mutex_lock(&I.mtx);
    I.req.s1 = name;
    pthread_mutex_unlock(&I.mtx);
    const int rc = submitAndWait(CMD_PERIPH_SETNAME, 5000, "peripheral::setDeviceName");
    if (rc == 1) return Result::err(ERR_TIMEOUT, "改名超时");
    if (rc == 2) return Result::err(ERR_BUSY, "上一动作还没结束，稍后再试");
    if (rc == 3) return Result::err(ERR_IO, "命令投递失败");
    pthread_mutex_lock(&I.mtx);
    const int st = I.req.status;
    const std::string msg = I.req.msg;
    pthread_mutex_unlock(&I.mtx);
    if (st != ERR_OK) return Result::err(st, msg);
    return Result::ok_("设备名已更新（广播已按新名字重开）");
}

Result notify(const std::string& char_uuid, const std::string& data) {
    Impl& I = impl();
    if (!I.opened || !I.ready) return Result::err(ERR_NOT_INIT, "适配器未就绪");
    pthread_mutex_lock(&I.mtx);
    I.req.char_uuid = internal::normalizeUuid(char_uuid);
    I.req.in_data = data;          // ★要发出去的通知载荷（入参）
    pthread_mutex_unlock(&I.mtx);
    const int rc = submitAndWait(CMD_PERIPH_NOTIFY, 3000, "peripheral::notify");
    if (rc == 1) return Result::err(ERR_TIMEOUT, "notify 超时");
    if (rc == 2) return Result::err(ERR_BUSY, "上一动作还没结束，稍后再试");
    if (rc == 3) return Result::err(ERR_IO, "命令投递失败");
    pthread_mutex_lock(&I.mtx);
    const int st = I.req.status;
    const std::string msg = I.req.msg;
    pthread_mutex_unlock(&I.mtx);
    if (st != ERR_OK) return Result::err(st, msg);
    return Result::ok_();
}

Result isConnected(bool& out) {
    Impl& I = impl();
    pthread_mutex_lock(&I.mtx);
    out = I.periph_connected;
    pthread_mutex_unlock(&I.mtx);
    return Result::ok_();
}

}  // namespace peripheral

// ================================================================ 公开接口：诊断
Result getDiag(Diag& out) {
    Impl& I = impl();
    pthread_mutex_lock(&I.mtx);
    out.backend = "gatt";
    out.chip = I.chip;
    out.uart = "";                 // gatt 后端走 USB HCI，没有串口概念（如实留空）
    out.baud = 0;
    out.powered = I.powered;
    out.preinit_ok = I.preinit_ok;
    out.ready = I.ready;
    out.hci_state = I.hci_state;
    out.hci_events = I.hci_events;
    out.transport_sent = 0;        // 0x6E 计数是 btstack 传输层的东西，本后端无此概念 → 恒 0
    out.devices_seen = I.cache.size();
    out.connect_attempts = I.connect_attempts;
    out.last_error = I.last_error;
    out.last_error_msg = I.last_error_msg;
    out.hint = I.hint;
    const bool has_preinit_hook = (bool)I.preinit;
    const int unk = I.adv_unknown_subevents;
    const bool do_reset = I.cfg.reset_before_retry;
    pthread_mutex_unlock(&I.mtx);

    // 把「本后端特有、排错最需要」的事实补进 hint（只追加，不改写）
    std::string extra;
    if (has_preinit_hook) {
        extra += "｜setPreinitHook 的钩子被忽略（本后端走 aic_btusb.ko + hciconfig，不经 hciattach）";
    }
    if (unk > 0) {
        extra += "｜收到 " + std::to_string(unk) +
                 " 条未支持的 LE 子事件（可能是 5.0 extended adv），扫不到设备时先查这里";
    }
    if (do_reset) extra += "｜connect 失败会自动 hciconfig hci0 reset 后重试";
    else extra += "｜reset_before_retry=0：实测 AIC 残留链路时强烈建议打开";
    if (!extra.empty()) out.hint += extra;
    return Result::ok_();
}

}  // namespace ble
}  // namespace zk

#endif  // ZKBLE_IS_GATT
