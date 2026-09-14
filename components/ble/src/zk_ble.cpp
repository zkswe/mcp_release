/*
 * zk_ble.cpp —— BLE 门面实现（btstack 1.7.2，BLE-only 构建）
 *
 * 线程模型（照本仓验证过的范本：projects/BTHomeTempHum-F133、V851ExtendedScreen_ap_p2p）：
 *   · btstack 的 run loop 独占一条线程，且 btstack 的所有 API 只在它里面调；
 *   · 业务线程（UI/主线程）要干活 → 投递任务到该线程（btstack_run_loop_execute_on_main_thread）；
 *   · 需要"同步语义"的接口（connect/read/write/subscribe）→ 业务线程用 条件变量+超时 等结果；
 *   · 上电（sysfs）与预初始化（hciattach）都在 BT 线程里、btstack 初始化之前做。
 */
#include "zk/zk_ble.h"

#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <pthread.h>
#include <time.h>
#include <sys/stat.h>

#include <string>
#include <vector>
#include <map>
#include <algorithm>

extern "C" {
#include "btstack/btstack.h"
#include "btstack/hci_transport_h4.h"
#include "btstack/hci_transport_h5.h"
#include "btstack/btstack_uart_slip_wrapper.h"
#include "btstack/posix/btstack_run_loop_posix.h"
#include "btstack/posix/btstack_tlv_posix.h"
#include "btstack/ble/le_device_db_tlv.h"
}

#define ZKBLE_VERSION "0.1.0"

// 日志：默认 printf；应用可 setLogHook() 挂到自己的日志系统
namespace {
std::function<void(const std::string&)> g_log_hook;
}

static void zkbleLog(const char* fmt, ...) {
    char buf[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    if (g_log_hook) {
        g_log_hook(std::string(buf));
    } else {
        printf("[zkble] %s\n", buf);
    }
}

#define ZKBLE_LOG(fmt, ...) zkbleLog(fmt, ##__VA_ARGS__)

namespace zk {
namespace ble {

// ============================================================ 内部工具
namespace {

const char* kPowerNodes[] = {
    // V85X 实测（两条为同类板子的不同内核枚举写法，不许写死一条）
    "/sys/devices/platform/soc/soc@03000000:netRF/state_bt",
    "/sys/devices/platform/soc@3000000/soc@3000000:netRF/state_bt",
    NULL,
};

uint32_t monotonicMs() {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t)((uint32_t)ts.tv_sec * 1000u + (uint32_t)ts.tv_nsec / 1000000u);
}

bool exists(const char* path) {
    return access(path, F_OK) == 0;
}

std::string bytesToHex(const uint8_t* data, size_t len) {
    static const char* kHex = "0123456789abcdef";
    std::string out;
    out.reserve(len * 2);
    for (size_t i = 0; i < len; i++) {
        out.push_back(kHex[(data[i] >> 4) & 0x0F]);
        out.push_back(kHex[data[i] & 0x0F]);
    }
    return out;
}

std::string uuidToStr(uint16_t uuid16, const uint8_t* uuid128) {
    char buf[40] = {0};
    if (uuid16 != 0) {
        snprintf(buf, sizeof(buf), "%04x", uuid16);
        return std::string(buf);
    }
    // btstack 的 uuid128 是小端存储：按 16 字节逆序打印
    for (int i = 0; i < 16; i++) {
        snprintf(buf + i * 2, 3, "%02x", uuid128[15 - i]);
    }
    return std::string(buf);
}

// 把 "fcd2"（16 位）或 32 字符 128 位 uuid 统一成小写无横线形式
std::string normalizeUuid(const std::string& in) {
    std::string s;
    for (char c : in) {
        if (c == '-' || c == ':' || c == ' ') continue;
        if (c >= 'A' && c <= 'Z') c = (char)(c - 'A' + 'a');
        s.push_back(c);
    }
    return s;
}

// 同步等待槽：btstack 线程 signal，业务线程带超时 wait
struct Waiter {
    pthread_mutex_t m;
    pthread_cond_t c;
    bool done;
    int status;              // 0 = OK
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

// 传输参数按模组分支决定（可被 Config 显式覆盖）：
//   8733bs（Realtek）：H5 + 偶校验 8E1 + 无流控（实测）
//   AIC 类（8800DL 等）：H4 + 流控开 + 无校验 + 1500000（实测口径）
struct LinkParams { bool use_h5; int flow; int parity; uint32_t baud; };

LinkParams resolveLinkParams(const Config& cfg, bool needs_preinit) {
    LinkParams p;
    if (needs_preinit) {                      // Realtek 分支（rtk_init 已把模块切到工作波特率）
        p.use_h5 = cfg.prefer_h5;
        p.flow = 0;
        p.parity = BTSTACK_UART_PARITY_EVEN;
        p.baud = cfg.baud ? cfg.baud : 1500000;  // ★btstack 开串口用的是**工作波特率**
    } else {                                  // AIC / F133 分支
        p.use_h5 = cfg.prefer_h5;
        p.flow = cfg.prefer_h5 ? 0 : 1;
        p.parity = BTSTACK_UART_PARITY_OFF;
        p.baud = cfg.baud ? cfg.baud : 1500000;
    }
    if (cfg.flowcontrol >= 0) p.flow = cfg.flowcontrol;
    if (cfg.parity >= 0) p.parity = cfg.parity;
    return p;
}

// ============================================================ 内部状态
struct CachedDevice {
    DeviceInfo info;
    uint8_t addr_type = 0;
};

struct GattJob {
    Waiter* waiter = NULL;
    std::vector<gatt_client_service_t> raw_services;
    size_t index = 0;
    std::vector<Service> result;
    // 读/写/订阅的返回
    std::string value;
    int att_status = 0;
};

struct Impl {
    pthread_mutex_t mtx;
    Config cfg;
    bool opened = false;
    bool closed = false;
    bool failed = false;          // BT 线程内部失败（上电/预初始化）已置位

    std::string chip = "未知";
    std::string uart;
    uint32_t baud = 0;
    bool powered = false;
    bool preinit_ok = false;
    bool ready = false;
    bool needs_preinit = false;

    int hci_state = 0;
    int hci_events = 0;
    int transport_sent = 0;
    int last_error = 0;
    std::string last_error_msg;
    std::string hint = "尚未 openAdapter";

    PreinitHook preinit;
    LinkParams link = {true, 0, 1, 115200};

    pthread_t thread;
    bool thread_started = false;

    Waiter open_waiter;
    Waiter conn_waiter;
    Waiter op_waiter;

    bool discovering = false;
    bool scan_pending = false;
    ScanOptions scan_opts;
    std::vector<CachedDevice> devices;

    // 连接态（单连接模型：v1 够用，多连接后续扩展）
    std::string conn_id;
    hci_con_handle_t conn_handle = HCI_CON_HANDLE_INVALID;
    std::vector<Service> services;

    GattJob job;
    btstack_timer_source_t scan_stop_timer;

    Impl() {
        pthread_mutex_init(&mtx, NULL);
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

// ============================================================ sysfs / 属性
int findPowerNode(std::string& out) {
    for (int i = 0; kPowerNodes[i]; i++) {
        if (exists(kPowerNodes[i])) {
            out = kPowerNodes[i];
            return 0;
        }
    }
    return -1;
}

// 写 0/1 并回读确认（写成功 != 状态已变，供电有建立时间）
int btEnable(int on) {
    std::string node;
    if (findPowerNode(node) != 0) return -1;
    FILE* pf = fopen(node.c_str(), "w");
    if (!pf) return -1;
    const char* v = on ? "1" : "0";
    const int n = (int)fwrite(v, 1, 1, pf);
    fclose(pf);
    if (n <= 0) return -1;

    pf = fopen(node.c_str(), "r");
    if (!pf) return -1;
    const char* want = on ? "on" : "off";
    const size_t want_len = strlen(want);
    for (int i = 0; i < 100; i++) {         // 最多等 100 × 30ms ≈ 3s
        char st[16] = {0};
        fseek(pf, 0, SEEK_SET);
        if (fread(st, 1, sizeof(st) - 1, pf) <= 0) break;
        if (strncmp(st, want, want_len) == 0) break;
        usleep(30000);
    }
    fclose(pf);
    return 0;
}

// 读系统属性：直接读 /data/property/<key>（不依赖 easyui，bin 工程也能用）
std::string readProp(const char* key) {
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

// 按平台探测默认串口（不写死一条）
std::string defaultUart() {
    static const char* kCandidates[] = {
        "/dev/ttyS1",     // F133 实测
        "/dev/ttyS2",     // V85X 实测
        NULL,
    };
    for (int i = 0; kCandidates[i]; i++) {
        if (exists(kCandidates[i])) return std::string(kCandidates[i]);
    }
    return std::string();
}

// ============================================================ btstack 侧
void packetHandler(uint8_t packet_type, uint16_t channel, uint8_t* packet, uint16_t size);
void opCompleteHandler(uint8_t packet_type, uint16_t channel, uint8_t* packet, uint16_t size);
void notifyHandler(uint8_t packet_type, uint16_t channel, uint8_t* packet, uint16_t size);
void scanStopTimerHandler(btstack_timer_source_t* ts);

btstack_packet_callback_registration_t g_hci_cb;
btstack_tlv_posix_t g_tlv_ctx;
OnAdapterStateChange g_cb_adapter;
OnDeviceFound g_cb_device;
OnConnectionChange g_cb_conn;
OnValueChange g_cb_value;
std::map<uint16_t, gatt_client_notification_t> g_notifications;   // value_handle -> listener

void fireAdapterState() {
    if (!g_cb_adapter) return;
    Impl& I = impl();
    AdapterState st;
    pthread_mutex_lock(&I.mtx);
    st.available = I.ready;
    st.discovering = I.discovering;
    st.power_on = I.powered;
    pthread_mutex_unlock(&I.mtx);
    g_cb_adapter(st);
}

// 投递任务到 run loop 线程。注意：注册结构体必须活到被执行完，故用环形池（不 malloc）。
void sendCmd(void (*fn)(void*), void* ctx) {
    static btstack_context_callback_registration_t regs[16];
    static int idx = 0;
    btstack_context_callback_registration_t* reg = &regs[(idx++) % 16];
    reg->callback = fn;
    reg->context = ctx;
    btstack_run_loop_execute_on_main_thread(reg);
}

// ---- 扫描
void cmdStartScan(void*) {
    Impl& I = impl();
    if (hci_get_state() != HCI_STATE_WORKING) {
        pthread_mutex_lock(&I.mtx);
        I.scan_pending = true;
        pthread_mutex_unlock(&I.mtx);
        return;
    }
    gap_set_scan_params(0 /*passive*/, 0x0030, 0x0030, 0 /*all devices*/);
    gap_set_scan_duplicate_filter(I.scan_opts.allow_duplicates);
    gap_start_scan();
    pthread_mutex_lock(&I.mtx);
    I.discovering = true;
    I.scan_pending = false;
    const int dur = I.scan_opts.duration_ms;
    pthread_mutex_unlock(&I.mtx);
    ZKBLE_LOG("scan started");
    fireAdapterState();
    if (dur > 0) {
        btstack_run_loop_set_timer(&I.scan_stop_timer, (uint32_t)dur);
        btstack_run_loop_set_timer_handler(&I.scan_stop_timer, scanStopTimerHandler);
        btstack_run_loop_add_timer(&I.scan_stop_timer);
    }
}

void cmdStopScan(void*) {
    Impl& I = impl();
    gap_stop_scan();
    btstack_run_loop_remove_timer(&I.scan_stop_timer);
    pthread_mutex_lock(&I.mtx);
    I.discovering = false;
    I.scan_pending = false;
    pthread_mutex_unlock(&I.mtx);
    ZKBLE_LOG("scan stopped");
    fireAdapterState();
}

void scanStopTimerHandler(btstack_timer_source_t*) {
    cmdStopScan(NULL);
}

// ---- 连接
std::string g_connect_id;

void cmdConnect(void*) {
    Impl& I = impl();
    bd_addr_t addr;
    uint8_t addr_type = 0;
    std::string id;
    pthread_mutex_lock(&I.mtx);
    id = g_connect_id;
    addr_type = 0;
    for (size_t i = 0; i < I.devices.size(); i++) {
        if (I.devices[i].info.id == id) { addr_type = I.devices[i].addr_type; break; }
    }
    pthread_mutex_unlock(&I.mtx);

    if (sscanf_bd_addr(id.c_str(), addr) != 1) {
        I.conn_waiter.signal(-1, "设备地址解析失败: " + id);
        return;
    }
    if (gap_connect(addr, (bd_addr_type_t)addr_type) != 0) {
        I.conn_waiter.signal(-1, "gap_connect 被拒绝（可能正在扫描或链路忙）");
    }
}

void cmdDisconnect(void*) {
    Impl& I = impl();
    if (I.conn_handle != HCI_CON_HANDLE_INVALID) {
        gap_disconnect(I.conn_handle);
    }
}

// ---- GATT
void gattDiscoveryHandler(uint8_t packet_type, uint16_t channel, uint8_t* packet, uint16_t size) {
    (void)channel;
    (void)size;
    Impl& I = impl();
    if (packet_type != HCI_EVENT_PACKET) return;

    switch (packet[0]) {
    case GATT_EVENT_SERVICE_QUERY_RESULT: {
        gatt_client_service_t svc;
        gatt_event_service_query_result_get_service(packet, &svc);
        I.job.raw_services.push_back(svc);
        break;
    }
    case GATT_EVENT_CHARACTERISTIC_QUERY_RESULT: {
        gatt_client_characteristic_t ch;
        gatt_event_characteristic_query_result_get_characteristic(packet, &ch);
        Service& s = I.job.result.back();
        Characteristic c;
        c.uuid = uuidToStr(ch.uuid16, ch.uuid128);
        c.value_handle = ch.value_handle;
        c.properties = ch.properties;
        s.characteristics.push_back(c);
        break;
    }
    case GATT_EVENT_QUERY_COMPLETE: {
        const uint8_t att = gatt_event_query_complete_get_att_status(packet);
        if (I.job.index == 0) {
            // 服务发现完成 → 逐个服务查特征
            if (att != 0) {
                I.job.att_status = att;
                I.job.waiter->signal(-1, "服务发现失败 att_status=" + std::to_string(att));
                return;
            }
            for (size_t i = 0; i < I.job.raw_services.size(); i++) {
                Service s;
                s.uuid = uuidToStr(I.job.raw_services[i].uuid16, I.job.raw_services[i].uuid128);
                I.job.result.push_back(s);
            }
            if (I.job.raw_services.empty()) {
                I.job.waiter->signal(0);
                return;
            }
            I.job.index = 1;
            gatt_client_discover_characteristics_for_service(
                gattDiscoveryHandler, I.conn_handle, &I.job.raw_services[0]);
            return;
        }
        // 某个服务的特征查完 → 下一个
        I.job.index++;
        if (I.job.index > I.job.raw_services.size()) {
            I.job.waiter->signal(0);
            return;
        }
        gatt_client_discover_characteristics_for_service(
            gattDiscoveryHandler, I.conn_handle, &I.job.raw_services[I.job.index - 1]);
        break;
    }
    default:
        break;
    }
}

void cmdDiscoverServices(void*) {
    Impl& I = impl();
    gatt_client_discover_primary_services(gattDiscoveryHandler, I.conn_handle);
}

// 读/写/订阅共用的发起参数
struct OpRequest {
    int kind;               // 0 read, 1 write, 2 subscribe, 3 unsubscribe
    uint16_t value_handle;
    std::string data;
    bool with_response;
};
OpRequest g_op;

void cmdRunOp(void*) {
    Impl& I = impl();
    switch (g_op.kind) {
    case 0:
        gatt_client_read_value_of_characteristic_using_value_handle(
            opCompleteHandler, I.conn_handle, g_op.value_handle);
        break;
    case 1:
        if (g_op.with_response) {
            gatt_client_write_value_of_characteristic(
                opCompleteHandler, I.conn_handle, g_op.value_handle,
                (uint16_t)g_op.data.size(), (uint8_t*)g_op.data.data());
        } else {
            gatt_client_write_value_of_characteristic_without_response(
                I.conn_handle, g_op.value_handle,
                (uint16_t)g_op.data.size(), (uint8_t*)g_op.data.data());
            I.op_waiter.signal(0);
        }
        break;
    case 2:
    case 3: {
        gatt_client_characteristic_t ch;
        memset(&ch, 0, sizeof(ch));
        ch.value_handle = g_op.value_handle;
        gatt_client_notification_t& n = g_notifications[g_op.value_handle];
        memset(&n, 0, sizeof(n));
        if (g_op.kind == 2) {
            gatt_client_listen_for_characteristic_value_updates(&n, notifyHandler, I.conn_handle, &ch);
        }
        gatt_client_write_client_characteristic_configuration(
            opCompleteHandler, I.conn_handle, &ch,
            g_op.kind == 2 ? GATT_CLIENT_CHARACTERISTICS_CONFIGURATION_NOTIFICATION : 0);
        break;
    }
    default:
        I.op_waiter.signal(-1, "未知操作");
        break;
    }
}

void opCompleteHandler(uint8_t packet_type, uint16_t channel, uint8_t* packet, uint16_t size) {
    (void)channel;
    (void)size;
    Impl& I = impl();
    if (packet_type != HCI_EVENT_PACKET) return;

    switch (packet[0]) {
    case GATT_EVENT_CHARACTERISTIC_VALUE_QUERY_RESULT: {
        const uint16_t len = gatt_event_characteristic_value_query_result_get_value_length(packet);
        const uint8_t* v = gatt_event_characteristic_value_query_result_get_value(packet);
        I.job.value.assign((const char*)v, len);            // 读到的原始字节
        break;
    }
    case GATT_EVENT_QUERY_COMPLETE: {
        const uint8_t att = gatt_event_query_complete_get_att_status(packet);
        if (att != 0) {
            I.op_waiter.signal(-1, "att_status=" + std::to_string(att));
        } else {
            I.op_waiter.signal(0);
        }
        break;
    }
    default:
        break;
    }
}

void notifyHandler(uint8_t packet_type, uint16_t channel, uint8_t* packet, uint16_t size) {
    (void)channel;
    (void)size;
    if (packet_type != HCI_EVENT_PACKET) return;
    if (packet[0] != GATT_EVENT_NOTIFICATION && packet[0] != GATT_EVENT_INDICATION) return;

    const uint16_t handle = (packet[0] == GATT_EVENT_NOTIFICATION)
        ? gatt_event_notification_get_value_handle(packet)
        : gatt_event_indication_get_value_handle(packet);
    const uint16_t len = (packet[0] == GATT_EVENT_NOTIFICATION)
        ? gatt_event_notification_get_value_length(packet)
        : gatt_event_indication_get_value_length(packet);
    const uint8_t* v = (packet[0] == GATT_EVENT_NOTIFICATION)
        ? gatt_event_notification_get_value(packet)
        : gatt_event_indication_get_value(packet);

    if (!g_cb_value) return;
    Impl& I = impl();
    Value out;
    pthread_mutex_lock(&I.mtx);
    out.device_id = I.conn_id;
    for (size_t i = 0; i < I.services.size(); i++) {
        for (size_t j = 0; j < I.services[i].characteristics.size(); j++) {
            if ((uint16_t)I.services[i].characteristics[j].value_handle == handle) {
                out.service_uuid = I.services[i].uuid;
                out.char_uuid = I.services[i].characteristics[j].uuid;
                break;
            }
        }
    }
    pthread_mutex_unlock(&I.mtx);
    out.data.assign((const char*)v, len);
    g_cb_value(out);
}

// ---- 广播上报
void handleAdvReport(uint8_t* packet) {
    Impl& I = impl();
    const uint8_t adv_type = gap_event_advertising_report_get_advertising_event_type(packet);
    const uint8_t ad_len = gap_event_advertising_report_get_data_length(packet);
    const uint8_t* ad = gap_event_advertising_report_get_data(packet);
    const int8_t rssi = (int8_t)gap_event_advertising_report_get_rssi(packet);
    bd_addr_t addr;
    gap_event_advertising_report_get_address(packet, addr);
    const uint8_t addr_type = gap_event_advertising_report_get_address_type(packet);

    CachedDevice cd;
    cd.addr_type = addr_type;
    char id[24] = {0};
    snprintf(id, sizeof(id), "%02X:%02X:%02X:%02X:%02X:%02X",
             addr[0], addr[1], addr[2], addr[3], addr[4], addr[5]);
    cd.info.id = id;
    cd.info.rssi = rssi;
    cd.info.last_seen_ms = monotonicMs();
    cd.info.connectable = (adv_type == 0x00 || adv_type == 0x01);
    cd.info.adv_data_hex = bytesToHex(ad, ad_len);

    // 解析 AD：名字 + Service Data
    ad_context_t ctx;
    ad_iterator_init(&ctx, ad_len, ad);
    while (ad_iterator_has_more(&ctx)) {
        const uint8_t type = ad_iterator_get_data_type(&ctx);
        const uint8_t len = ad_iterator_get_data_len(&ctx);
        const uint8_t* d = ad_iterator_get_data(&ctx);
        if (type == 0x08 || type == 0x09) {
            cd.info.name.assign((const char*)d, len);
        } else if (type == 0x16 && len >= 2) {
            cd.info.service_data_hex = bytesToHex(d, len);
        }
        ad_iterator_next(&ctx);
    }

    ScanOptions opts;
    pthread_mutex_lock(&I.mtx);
    opts = I.scan_opts;
    bool dup = false;
    for (size_t i = 0; i < I.devices.size(); i++) {
        if (I.devices[i].info.id == cd.info.id) {
            I.devices[i] = cd;
            dup = true;
            break;
        }
    }
    if (!dup) I.devices.push_back(cd);
    pthread_mutex_unlock(&I.mtx);

    if (!opts.name_prefix.empty() && cd.info.name.compare(0, opts.name_prefix.size(), opts.name_prefix) != 0) return;
    if (!opts.service_uuid.empty()) {
        // Service Data 前两字节是小端 UUID，hex 里是反序的（FCD2 → "d2fc"）
        std::string want = normalizeUuid(opts.service_uuid);
        if (want.size() >= 4) {
            std::string head = want.substr(0, 4);
            std::string le = std::string() + head[2] + head[3] + head[0] + head[1];
            if (cd.info.service_data_hex.compare(0, 4, le) != 0) return;
        }
    }
    if (dup && !opts.allow_duplicates) return;
    if (g_cb_device) g_cb_device(cd.info);
}

// ---- HCI 事件总入口
void packetHandler(uint8_t packet_type, uint16_t channel, uint8_t* packet, uint16_t size) {
    (void)channel;
    (void)size;
    Impl& I = impl();
    if (packet_type != HCI_EVENT_PACKET) return;

    const uint8_t code = packet[0];
    if (code == HCI_EVENT_TRANSPORT_PACKET_SENT) {          // 0x6E：只是"我发出去了"，不算芯片回应
        I.transport_sent++;
        return;
    }
    if (code >= 0x01 && code <= 0x5F) I.hci_events++;        // 芯片真实事件

    if (code == BTSTACK_EVENT_STATE) {
        const int st = (int)btstack_event_state_get_state(packet);
        I.hci_state = st;
        ZKBLE_LOG("HCI state = %d", st);
        if (st == HCI_STATE_WORKING) {
            I.ready = true;
            I.hint = "就绪：可以 startDiscovery() / connect()";
            I.open_waiter.signal(0);
            bool pending = false;
            pthread_mutex_lock(&I.mtx);
            pending = I.scan_pending;
            pthread_mutex_unlock(&I.mtx);
            if (pending) cmdStartScan(NULL);
            fireAdapterState();
        }
        return;
    }

    if (code == GAP_EVENT_ADVERTISING_REPORT) {
        handleAdvReport(packet);
        return;
    }

    if (code == HCI_EVENT_LE_META &&
        hci_event_le_meta_get_subevent_code(packet) == HCI_SUBEVENT_LE_CONNECTION_COMPLETE) {
        const uint8_t status = hci_subevent_le_connection_complete_get_status(packet);
        if (status == 0) {
            I.conn_handle = hci_subevent_le_connection_complete_get_connection_handle(packet);
            pthread_mutex_lock(&I.mtx);
            I.conn_id = g_connect_id;
            pthread_mutex_unlock(&I.mtx);
            ZKBLE_LOG("connected handle=0x%04x", I.conn_handle);
            I.conn_waiter.signal(0);
            if (g_cb_conn) g_cb_conn(g_connect_id, true);
        } else {
            I.conn_waiter.signal(-1, "连接失败 status=" + std::to_string(status));
        }
        return;
    }

    if (code == HCI_EVENT_DISCONNECTION_COMPLETE) {
        std::string id;
        pthread_mutex_lock(&I.mtx);
        id = I.conn_id;
        I.conn_id.clear();
        I.conn_handle = HCI_CON_HANDLE_INVALID;
        I.services.clear();
        pthread_mutex_unlock(&I.mtx);
        I.op_waiter.signal(-1, "链路已断");
        I.conn_waiter.signal(-1, "链路已断");
        ZKBLE_LOG("disconnected");
        if (g_cb_conn) g_cb_conn(id, false);
        return;
    }
}

// ---- BT 线程主体：上电 → 预初始化 → btstack 装配 → run loop
void* btThread(void*) {
    Impl& I = impl();

    // 1) 上电 + 2) 预初始化（Realtek；失败按 preinit_retry 重试，每次重试前重新上电）
    //    实测：断电 3s / 上电 2s 比 50ms/300ms 稳得多；开机首启偶发失败靠重试兜住。
    if (I.needs_preinit) {
        if (!I.preinit) {
            I.hint = "该模组需要预初始化：请 setPreinitHook() 挂上 rtk_init（见 README/platforms.md）";
            I.failed = true;
            I.open_waiter.signal(-1, "缺少预初始化实现（setPreinitHook）");
            return NULL;
        }
        const int attempts = I.cfg.preinit_retry > 0 ? I.cfg.preinit_retry : 1;
        for (int attempt = 1; attempt <= attempts; attempt++) {
            if (I.cfg.auto_power) {
                btEnable(0);
                usleep((useconds_t)I.cfg.power_off_ms * 1000);
                btEnable(1);
                usleep((useconds_t)I.cfg.power_on_ms * 1000);
                I.powered = true;
                ZKBLE_LOG("power cycle done (attempt %d/%d)", attempt, attempts);
            }
            Result r = I.preinit(I.uart, 115200);   // 预初始化固定从 115200 起步（rtk_init 内部自己切）
            if (r.ok()) {
                I.preinit_ok = true;
                break;
            }
            ZKBLE_LOG("preinit attempt %d/%d failed: %s", attempt, attempts, r.msg.c_str());
            if (attempt == attempts) {
                I.hint = "预初始化失败：" + r.msg + "（查 state_bt / 固件路径 / 串口被谁占用；8733 类失败后往往要物理冷启动）";
                I.failed = true;
                I.open_waiter.signal(-1, "preinit 失败: " + r.msg);
                return NULL;
            }
        }
    }

    // 3) btstack 装配（顺序固定：内存 → run loop → uart/传输 → hci_init → 事件回调 → profile → 上电）
    ZKBLE_LOG("step1: btstack_memory_init");
    btstack_memory_init();
    ZKBLE_LOG("step2: run_loop_init");
    btstack_run_loop_init(btstack_run_loop_posix_get_instance());
    ZKBLE_LOG("step3: uart instance");

    // ★ 必须用 hci_transport_config_uart_t（带 type 字段）+ 预初始化后的工作波特率；
    //   与 V85X 工程实测可用写法一致。用错结构体（如 btstack_uart_config_t）会在
    //   hci_power_control() 里直接段错误（已真机复现）。
    hci_transport_config_uart_t uart_cfg;
    memset(&uart_cfg, 0, sizeof(uart_cfg));
    uart_cfg.type = HCI_TRANSPORT_CONFIG_UART;
    uart_cfg.device_name = I.uart.c_str();
    uart_cfg.baudrate_init = I.link.baud;
    uart_cfg.flowcontrol = I.link.flow;
    uart_cfg.parity = I.link.parity;

    const btstack_uart_t* uart = btstack_uart_posix_instance();
    ZKBLE_LOG("step4: uart=%p", (void*)uart);
    const hci_transport_t* transport = NULL;
    if (I.link.use_h5) {
        // 实测可用组合：posix uart 直接给 h5（别再套 slip wrapper，V85X 工程就没套）
        transport = hci_transport_h5_instance(uart);
        ZKBLE_LOG("step6: h5 transport=%p", (void*)transport);
    } else {
        transport = hci_transport_h4_instance_for_uart(uart);
        ZKBLE_LOG("step6: h4 transport=%p", (void*)transport);
    }
    ZKBLE_LOG("step7: hci_init");
    hci_init(transport, &uart_cfg);
    ZKBLE_LOG("step8: hci_add_event_handler");
    g_hci_cb.callback = &packetHandler;
    hci_add_event_handler(&g_hci_cb);                       // ★必须在 hci_init 之后
    ZKBLE_LOG("step9: tlv");

    // TLV：配对信息落盘（失败只告警，不阻断）
    const btstack_tlv_t* tlv = btstack_tlv_posix_init_instance(&g_tlv_ctx, I.cfg.tlv_path.c_str());
    if (tlv) {
        btstack_tlv_set_instance(tlv, &g_tlv_ctx);
        le_device_db_tlv_configure(tlv, &g_tlv_ctx);
    } else {
        ZKBLE_LOG("WARN: TLV 落盘不可用（%s）→ 配对信息重启会丢", I.cfg.tlv_path.c_str());
    }

    ZKBLE_LOG("step10: profiles");
    l2cap_init();
    sm_init();
    gatt_client_init();

    ZKBLE_LOG("step11: hci_power_control(ON)");
    hci_power_control(HCI_POWER_ON);
    ZKBLE_LOG("step12: run_loop_execute");
    btstack_run_loop_execute();                             // 阻塞：本线程贯穿生命周期
    return NULL;
}

uint16_t findValueHandle(const std::string& service_uuid, const std::string& char_uuid) {
    Impl& I = impl();
    const std::string su = normalizeUuid(service_uuid);
    const std::string cu = normalizeUuid(char_uuid);
    for (size_t i = 0; i < I.services.size(); i++) {
        if (!su.empty() && I.services[i].uuid != su) continue;
        for (size_t j = 0; j < I.services[i].characteristics.size(); j++) {
            if (I.services[i].characteristics[j].uuid == cu) {
                return (uint16_t)I.services[i].characteristics[j].value_handle;
            }
        }
    }
    return 0xFFFF;
}

}  // namespace

// ============================================================ 公开接口
std::string version() {
    return std::string(ZKBLE_VERSION);
}

void setPreinitHook(PreinitHook hook) {
    impl().preinit = hook;
}

void setLogHook(LogHook hook) {
    g_log_hook = hook;
}

Result openAdapter(const Config& cfg) {
    Impl& I = impl();
    if (I.opened) return Result::ok_("已经打开");

    I.cfg = cfg;
    I.chip = cfg.module.empty() ? readProp("persist.wifi.module") : cfg.module;
    if (I.chip.empty()) I.chip = "未知（persist.wifi.module 读不到）";
    I.needs_preinit = (I.chip.find("8733") != std::string::npos);

    I.uart = cfg.uart.empty() ? defaultUart() : cfg.uart;
    if (I.uart.empty()) {
        I.hint = "找不到蓝牙串口：节点不存在（F133 期望 /dev/ttyS1，V85X 期望 /dev/ttyS2）";
        setError(ERR_IO, I.hint);
        return Result::err(ERR_IO, I.hint);
    }
    I.baud = cfg.baud ? cfg.baud : (I.needs_preinit ? 115200 : 1500000);
    I.link = resolveLinkParams(cfg, I.needs_preinit);
    I.hint = I.needs_preinit
        ? "正在初始化 Realtek 分支（上电 → hciattach → H5 + 偶校验）…"
        : "正在初始化 AIC/F133 分支（H4/H5 + 无校验）…";
    I.opened = true;
    I.closed = false;
    I.open_waiter.reset();

    if (pthread_create(&I.thread, NULL, btThread, NULL) != 0) {
        I.opened = false;
        setError(ERR_IO, "BT 线程创建失败");
        return Result::err(ERR_IO, "BT 线程创建失败");
    }
    I.thread_started = true;

    if (!I.open_waiter.wait(cfg.open_timeout_ms)) {
        I.hint = "等 HCI WORKING 超时：查 state_bt 上电、hciattach 预初始化、串口/校验是否匹配";
        setError(ERR_POWER_OFF, I.hint);
        I.failed = true;
        return Result::err(ERR_POWER_OFF, I.hint);
    }
    // ★线程内失败（上电/预初始化）必须如实上报，不能因为没超时就当成功
    if (I.open_waiter.status != 0) {
        setError(ERR_POWER_OFF, I.open_waiter.msg);
        I.failed = true;
        I.opened = false;
        return Result::err(ERR_POWER_OFF, I.open_waiter.msg + " | " + I.hint);
    }
    if (!I.ready) {
        setError(ERR_POWER_OFF, "HCI 未到 WORKING");
        return Result::err(ERR_POWER_OFF, "HCI 未到 WORKING（看 getDiag().hint）");
    }
    return Result::ok_("适配器就绪");
}

void closeAdapter() {
    Impl& I = impl();
    if (!I.opened) return;
    if (I.conn_handle != HCI_CON_HANDLE_INVALID) {
        sendCmd(cmdDisconnect, NULL);
        usleep(200 * 1000);
    }
    if (I.discovering) sendCmd(cmdStopScan, NULL);
    btstack_run_loop_trigger_exit();        // POSIX run loop 的退出口，不是 exit()
    pthread_detach(I.thread);
    I.opened = false;
    I.closed = true;
    I.ready = false;
    I.hint = "已关闭";
}

bool adapterReady() {
    return impl().ready;
}

Result getAdapterState(AdapterState& out) {
    Impl& I = impl();
    pthread_mutex_lock(&I.mtx);
    out.available = I.ready;
    out.discovering = I.discovering;
    out.power_on = I.powered;
    pthread_mutex_unlock(&I.mtx);
    return Result::ok_();
}

Result startDiscovery(const ScanOptions& opts) {
    Impl& I = impl();
    if (!I.opened) return Result::err(ERR_NOT_INIT, "先 openAdapter()");
    if (!I.ready) return Result::err(ERR_POWER_OFF, "适配器未就绪（初始化失败或还没到 WORKING）—— 看 getDiag().hint");
    pthread_mutex_lock(&I.mtx);
    const bool busy = I.discovering;
    I.scan_opts = opts;
    pthread_mutex_unlock(&I.mtx);
    if (busy) return Result::err(ERR_BUSY, "正在扫描，先 stopDiscovery()");
    sendCmd(cmdStartScan, NULL);
    return Result::ok_("扫描已受理（HCI 未就绪会自动等）");
}

Result stopDiscovery() {
    Impl& I = impl();
    if (!I.opened || !I.ready) return Result::err(ERR_NOT_INIT, "适配器未就绪");
    sendCmd(cmdStopScan, NULL);
    return Result::ok_();
}

Result getDevices(std::vector<DeviceInfo>& out) {
    Impl& I = impl();
    out.clear();
    pthread_mutex_lock(&I.mtx);
    for (size_t i = 0; i < I.devices.size(); i++) out.push_back(I.devices[i].info);
    pthread_mutex_unlock(&I.mtx);
    return Result::ok_();
}

Result clearDevices() {
    Impl& I = impl();
    pthread_mutex_lock(&I.mtx);
    I.devices.clear();
    pthread_mutex_unlock(&I.mtx);
    return Result::ok_();
}

Result connect(const std::string& device_id, int timeout_ms) {
    Impl& I = impl();
    if (!I.opened) return Result::err(ERR_NOT_INIT, "先 openAdapter()");
    if (!I.ready) return Result::err(ERR_POWER_OFF, "适配器未就绪（看 getDiag().hint）");
    if (I.conn_handle != HCI_CON_HANDLE_INVALID) return Result::err(ERR_BUSY, "已有连接，先 disconnect()");

    if (I.discovering) {
        sendCmd(cmdStopScan, NULL);
        usleep(150 * 1000);
    }
    g_connect_id = device_id;
    I.conn_waiter.reset();
    sendCmd(cmdConnect, NULL);

    const int t = timeout_ms > 0 ? timeout_ms : I.cfg.op_timeout_ms;
    if (!I.conn_waiter.wait(t)) {
        sendCmd(cmdDisconnect, NULL);
        setError(ERR_TIMEOUT, "连接超时: " + device_id);
        return Result::err(ERR_TIMEOUT, "连接超时: " + device_id + "（设备在广播吗？/ 距离 / connectable？）");
    }
    if (I.conn_waiter.status != 0) {
        setError(ERR_DISCONNECTED, I.conn_waiter.msg);
        return Result::err(ERR_DISCONNECTED, I.conn_waiter.msg);
    }
    return Result::ok_("已连接");
}

Result disconnect(const std::string& device_id) {
    Impl& I = impl();
    if (!I.opened || !I.ready) return Result::err(ERR_NOT_INIT, "适配器未就绪");
    if (!device_id.empty() && !I.conn_id.empty() && device_id != I.conn_id) {
        return Result::err(ERR_NOT_FOUND, "当前连接不是 " + device_id);
    }
    sendCmd(cmdDisconnect, NULL);
    return Result::ok_();
}

bool isConnected(const std::string& device_id) {
    Impl& I = impl();
    if (I.conn_handle == HCI_CON_HANDLE_INVALID) return false;
    if (device_id.empty()) return true;
    return device_id == I.conn_id;
}

Result getServices(const std::string& device_id, std::vector<Service>& out) {
    Impl& I = impl();
    out.clear();
    if (!isConnected(device_id)) return Result::err(ERR_DISCONNECTED, "未连接");

    I.job = GattJob();
    I.job.waiter = &I.op_waiter;
    I.op_waiter.reset();
    sendCmd(cmdDiscoverServices, NULL);

    if (!I.op_waiter.wait(I.cfg.op_timeout_ms)) {
        return Result::err(ERR_TIMEOUT, "服务发现超时");
    }
    if (I.op_waiter.status != 0) {
        return Result::err(ERR_NOT_FOUND, I.op_waiter.msg);
    }
    pthread_mutex_lock(&I.mtx);
    I.services = I.job.result;
    out = I.job.result;
    pthread_mutex_unlock(&I.mtx);
    return Result::ok_();
}

Result getCharacteristics(const std::string& device_id,
                          const std::string& service_uuid,
                          std::vector<Characteristic>& out) {
    out.clear();
    std::vector<Service> svcs;
    Result r = getServices(device_id, svcs);
    if (!r.ok()) return r;
    const std::string want = normalizeUuid(service_uuid);
    for (size_t i = 0; i < svcs.size(); i++) {
        if (want.empty() || svcs[i].uuid == want) {
            out = svcs[i].characteristics;
            return Result::ok_();
        }
    }
    return Result::err(ERR_NOT_FOUND, "服务不存在: " + service_uuid);
}

Result readValue(const std::string& device_id,
                 const std::string& service_uuid,
                 const std::string& char_uuid,
                 std::string& out) {
    Impl& I = impl();
    out.clear();
    if (!isConnected(device_id)) return Result::err(ERR_DISCONNECTED, "未连接");
    const uint16_t vh = findValueHandle(service_uuid, char_uuid);
    if (vh == 0xFFFF) return Result::err(ERR_NOT_FOUND, "特征不存在（先 getServices）");

    g_op.kind = 0;
    g_op.value_handle = vh;
    I.job.value.clear();
    I.op_waiter.reset();
    sendCmd(cmdRunOp, NULL);
    if (!I.op_waiter.wait(I.cfg.op_timeout_ms)) return Result::err(ERR_TIMEOUT, "读超时");
    if (I.op_waiter.status != 0) return Result::err(ERR_IO, I.op_waiter.msg);
    out = I.job.value;
    return Result::ok_();
}

Result writeValue(const std::string& device_id,
                  const std::string& service_uuid,
                  const std::string& char_uuid,
                  const std::string& data,
                  bool with_response) {
    Impl& I = impl();
    if (!isConnected(device_id)) return Result::err(ERR_DISCONNECTED, "未连接");
    const uint16_t vh = findValueHandle(service_uuid, char_uuid);
    if (vh == 0xFFFF) return Result::err(ERR_NOT_FOUND, "特征不存在（先 getServices）");

    g_op.kind = 1;
    g_op.value_handle = vh;
    g_op.data = data;
    g_op.with_response = with_response;
    I.op_waiter.reset();
    sendCmd(cmdRunOp, NULL);
    if (!I.op_waiter.wait(with_response ? I.cfg.op_timeout_ms : 500)) {
        return Result::err(ERR_TIMEOUT, "写超时");
    }
    if (I.op_waiter.status != 0) return Result::err(ERR_IO, I.op_waiter.msg);
    return Result::ok_();
}

Result subscribe(const std::string& device_id,
                 const std::string& service_uuid,
                 const std::string& char_uuid,
                 bool enable) {
    Impl& I = impl();
    if (!isConnected(device_id)) return Result::err(ERR_DISCONNECTED, "未连接");
    const uint16_t vh = findValueHandle(service_uuid, char_uuid);
    if (vh == 0xFFFF) return Result::err(ERR_NOT_FOUND, "特征不存在（先 getServices）");

    g_op.kind = enable ? 2 : 3;
    g_op.value_handle = vh;
    I.op_waiter.reset();
    sendCmd(cmdRunOp, NULL);
    if (!I.op_waiter.wait(I.cfg.op_timeout_ms)) return Result::err(ERR_TIMEOUT, "订阅超时");
    if (I.op_waiter.status != 0) return Result::err(ERR_IO, I.op_waiter.msg);
    return Result::ok_();
}

Result getBondedDevices(std::vector<std::string>& out) {
    out.clear();
    // 注：le_device_db_info() 返回 void，空槽位按全 0 地址过滤
    const int max = le_device_db_max_count();
    for (int i = 0; i < max; i++) {
        bd_addr_t addr;
        int addr_type = 0;
        memset(addr, 0, sizeof(bd_addr_t));
        le_device_db_info(i, &addr_type, addr, NULL);
        bool empty = true;
        for (int k = 0; k < 6; k++) if (addr[k] != 0) { empty = false; break; }
        if (empty) continue;
        char buf[24] = {0};
        snprintf(buf, sizeof(buf), "%02X:%02X:%02X:%02X:%02X:%02X",
                 addr[0], addr[1], addr[2], addr[3], addr[4], addr[5]);
        out.push_back(std::string(buf));
    }
    return Result::ok_();
}

Result deleteBonding(const std::string& device_id) {
    bd_addr_t addr;
    if (sscanf_bd_addr(device_id.c_str(), addr) != 1) {
        return Result::err(ERR_PARAM, "地址格式不对: " + device_id);
    }
    gap_delete_bonding(BD_ADDR_TYPE_LE_PUBLIC, addr);
    return Result::ok_();
}

// ---- 外设模式（二期，先给出明确答复而不是假装能用）
namespace peripheral {
Result start(const Config&) {
    return Result::err(ERR_UNSUPPORTED,
        "外设/HID 模式在二期实现（hids_device + 广播）；当前版本只做中心侧");
}
Result stop() { return Result::err(ERR_UNSUPPORTED, "二期"); }
Result setDeviceName(const std::string&) { return Result::err(ERR_UNSUPPORTED, "二期"); }
Result sendInputReport(const std::string&) { return Result::err(ERR_UNSUPPORTED, "二期"); }
Result isConnected(bool& out) { out = false; return Result::err(ERR_UNSUPPORTED, "二期"); }
}  // namespace peripheral

// ---- 回调
void onAdapterStateChange(OnAdapterStateChange cb) { g_cb_adapter = cb; }
void onDeviceFound(OnDeviceFound cb) { g_cb_device = cb; }
void onConnectionChange(OnConnectionChange cb) { g_cb_conn = cb; }
void onValueChange(OnValueChange cb) { g_cb_value = cb; }
void offAll() {
    g_cb_adapter = NULL;
    g_cb_device = NULL;
    g_cb_conn = NULL;
    g_cb_value = NULL;
}

Result getDiag(Diag& out) {
    Impl& I = impl();
    pthread_mutex_lock(&I.mtx);
    out.chip = I.chip;
    out.uart = I.uart;
    out.baud = I.baud;
    out.powered = I.powered;
    out.preinit_ok = I.preinit_ok;
    out.ready = I.ready;
    out.hci_state = I.hci_state;
    out.hci_events = I.hci_events;
    out.transport_sent = I.transport_sent;
    out.devices_seen = (int)I.devices.size();
    out.last_error = I.last_error;
    out.last_error_msg = I.last_error_msg;
    out.hint = I.hint;
    pthread_mutex_unlock(&I.mtx);
    return Result::ok_();
}

}  // namespace ble
}  // namespace zk
