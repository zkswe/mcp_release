/*
 * zk_ble.h —— BLE 门面（zk::ble）v0.1 —— 面向业务/AI 的蓝牙接口
 *
 * 定位：拿微信小程序 wx.* BLE 那套用法，做 C++ 版；底层是 btstack 1.7.2（BLE-only 构建）。
 *   openAdapter → startDiscovery → onDeviceFound → getDevices
 *   → connect → getServices / getCharacteristics → readValue / writeValue / subscribe → onValueChange
 *
 * 硬约定（写代码前先读这 5 条）：
 *   1) 全部接口同步返回 Result{code,msg}，msg 是人话；不抛异常、不静默失败；
 *   2) 本头文件里不出现任何 btstack 类型（底层细节不外泄）；想直接调底层仍可自行 include btstack；
 *   3) 回调（on*）在库内部线程被调用 —— 回调里只做轻活，重活请切回自己的线程；
 *   4) 平台差异、上电、hciattach 预初始化、H5/偶校验、TLV 落盘、run loop 线程，全部由本模块做掉；
 *   5) 排错先看 getDiag() —— 它会告诉你卡在哪一步、下一步该查什么。
 *
 * 依赖：btstack 1.7.2、easyui 2.9.0（SystemProperties）、base-utility（可选）、pthread。
 * 详见同目录 README.md（用法）与 platforms.md（平台说明）。
 */
#pragma once

#include <stdint.h>
#include <string>
#include <vector>
#include <functional>

namespace zk {
namespace ble {

// ---------------------------------------------------------------- Result
enum ErrorCode {
    ERR_OK = 0,
    ERR_NOT_INIT = -1,       // 还没 openAdapter
    ERR_POWER_OFF = -2,      // 蓝牙模组起不来（上电/预初始化/固件 失败，msg 指明哪一步）
    ERR_BUSY = -3,           // 上一动作没结束（例如正在扫描又调 startDiscovery）
    ERR_NOT_FOUND = -4,      // 设备/服务/特征不存在
    ERR_TIMEOUT = -5,        // 连接/读写超时
    ERR_DISCONNECTED = -6,   // 链路已断
    ERR_PARAM = -7,          // 参数不合法
    ERR_UNSUPPORTED = -8,    // 当前平台/裁剪不支持（例如缺预初始化实现）
    ERR_NO_MEM = -9,
    ERR_IO = -10,            // 节点读写/落盘失败（含权限）
};

struct Result {
    int code = ERR_OK;
    std::string msg;                 // 人话，可直接打日志或展示
    bool ok() const { return code == ERR_OK; }
    static Result ok_(const char* m = "") { Result r; r.code = ERR_OK; r.msg = m; return r; }
    static Result err(int c, const std::string& m) { Result r; r.code = c; r.msg = m; return r; }
};

// ---------------------------------------------------------------- 数据模型
struct DeviceInfo {
    std::string id;                  // 稳定 id：MAC 字符串 "AA:BB:CC:DD:EE:FF"（大写冒号分隔）
    std::string name;                // 广播里的 Name（可能为空）
    int16_t rssi = 0;
    std::string service_data_hex;    // Service Data 原始字节（hex）；BTHome 等由业务自行解析
    std::string adv_data_hex;        // 完整 AD 段原始数据（hex），高级用法
    int64_t last_seen_ms = 0;        // 单调时钟毫秒
    bool connectable = false;
};

enum CharProp {
    PROP_READ = 1 << 0,
    PROP_WRITE = 1 << 1,
    PROP_WRITE_NO_RESPONSE = 1 << 2,
    PROP_NOTIFY = 1 << 3,
    PROP_INDICATE = 1 << 4,
};

struct Characteristic {
    std::string uuid;                // 小写、无横线（16 位如 "fcd2"，128 位全写 32 字符）
    int properties = 0;              // 位掩码，见 CharProp
    int value_handle = 0;            // 内部用（GATT value handle）；业务不用管
};

struct Service {
    std::string uuid;
    std::vector<Characteristic> characteristics;
};

struct Value {                       // 读/通知回来的数据
    std::string device_id;
    std::string service_uuid;
    std::string char_uuid;
    std::string data;                // 原始字节（std::string 当 byte buffer 用）
};

struct AdapterState {
    bool available = false;          // 适配器可用（HCI 到了 WORKING）
    bool discovering = false;        // 是否正在扫描
    bool power_on = false;           // 模组是否已上电（sysfs 实测回读，非"我以为"）
};

// ---------------------------------------------------------------- 配置
struct Config {
    std::string module;              // 模组标识覆盖（默认读 /data/property/persist.wifi.module）；含 "8733" → Realtek 分支
    std::string uart;                // 留空 = 自动（按平台默认 + 节点存在性探测）
    uint32_t baud = 0;               // 0 = 默认（Realtek 预初始化内部会 115200 → 1500000）
    std::string tlv_path = "/data/bttlv.db";  // 配对信息落盘（需可写分区）
    std::string fw_dir;              // Realtek 补丁固件目录；留空走候选链
    std::string device_name = "FlyThings";    // 外设模式对外广播名（二期）
    bool auto_power = true;          // ★自动上电（sysfs state_bt：断电→上电→回读）
    int  power_off_ms = 3000;        // Realtek 类：断电保持时间（实测 3s 比 50ms 稳）
    int  power_on_ms = 2000;         // Realtek 类：上电后等待时间
    int  preinit_retry = 3;          // 预初始化失败重试次数（每次重试前重新上电）
    bool prefer_h5 = true;           // 8733bs 必须 H5；AIC（8800DL 等）置 false 走 H4
    int  flowcontrol = -1;           // -1 = 自动（8733bs→0；AIC→1）；0=off 1=on
    int  parity = -1;                // -1 = 自动（8733bs→偶校验 8E1；AIC/F133→无）
    int  open_timeout_ms = 60000;    // openAdapter 等 HCI 到 WORKING 的超时（含预初始化重试余量）
    int  op_timeout_ms = 8000;       // 连接/读写等单次操作超时
};

// ================================================================ 适配器
// 一步完成：芯片判定 → 上电 → (预初始化) → H5 → TLV → 起线程 → 等 WORKING
Result openAdapter(const Config& cfg = Config());
void   closeAdapter();
bool   adapterReady();
Result getAdapterState(AdapterState& out);

// 日志钩子：默认走 printf；应用里可挂到自己的日志系统（如 easyui 的 LOGD → logcat）
using LogHook = std::function<void(const std::string&)>;
void setLogHook(LogHook hook);

// Realtek（RTL8733BS 等）类模组必须做 hciattach 预初始化（同步握手/读ROM/下固件/切波特率）。
// 本模块不内置该流程：由项目侧提供实现并注册（把工程里 src/ble/rtk/ 那套挂进来即可）。
// 未注册 + 模组需要预初始化 → openAdapter 返回 ERR_UNSUPPORTED 并指明。
// AIC 类（如 8800DL）不需要预初始化，直接走 HCI（H4 + 流控）。
using PreinitHook = std::function<Result(const std::string& uart, uint32_t baud)>;
void setPreinitHook(PreinitHook hook);

// ================================================================ 扫描
struct ScanOptions {
    std::string name_prefix;         // 按名字前缀过滤，如 "BTHome"
    std::string service_uuid;        // 按服务过滤，如 "fcd2"（16 位或 128 位）
    bool allow_duplicates = false;   // 同一设备重复上报？
    int  duration_ms = 0;            // 0 = 一直扫，直到 stopDiscovery()
};
Result startDiscovery(const ScanOptions& opts = ScanOptions());
Result stopDiscovery();
Result getDevices(std::vector<DeviceInfo>& out);   // 扫描缓存快照（线程安全）
Result clearDevices();

// ================================================================ 连接 + 服务发现
Result connect(const std::string& device_id, int timeout_ms = 0);   // 0 = 用 Config.op_timeout_ms
Result disconnect(const std::string& device_id = std::string());    // 空 = 断当前连接
bool   isConnected(const std::string& device_id = std::string());
Result getServices(const std::string& device_id, std::vector<Service>& out);   // 含特征列表
Result getCharacteristics(const std::string& device_id,
                          const std::string& service_uuid,
                          std::vector<Characteristic>& out);

// ================================================================ 数据
Result readValue(const std::string& device_id,
                 const std::string& service_uuid,
                 const std::string& char_uuid,
                 std::string& out);
Result writeValue(const std::string& device_id,
                  const std::string& service_uuid,
                  const std::string& char_uuid,
                  const std::string& data,
                  bool with_response = true);
Result subscribe(const std::string& device_id,
                 const std::string& service_uuid,
                 const std::string& char_uuid,
                 bool enable = true);

// 配对/绑定（落 TLV；重启后不用重配）
Result getBondedDevices(std::vector<std::string>& out);
Result deleteBonding(const std::string& device_id);

// ================================================================ 外设模式（HID 遥控/键盘；二期）
namespace peripheral {
    Result start(const Config& cfg = Config());
    Result stop();
    Result setDeviceName(const std::string& name);
    Result sendInputReport(const std::string& report);   // ★必须带 report id 的完整报告
    Result isConnected(bool& out);
}

// ================================================================ 回调（wx 的 onXxx / offXxx）
using OnAdapterStateChange = std::function<void(const AdapterState&)>;
using OnDeviceFound        = std::function<void(const DeviceInfo&)>;
using OnConnectionChange   = std::function<void(const std::string& device_id, bool connected)>;
using OnValueChange        = std::function<void(const Value&)>;

void onAdapterStateChange(OnAdapterStateChange cb);
void onDeviceFound(OnDeviceFound cb);
void onConnectionChange(OnConnectionChange cb);
void onValueChange(OnValueChange cb);
void offAll();                       // 一键清空全部回调（退出页面前调）

// ================================================================ 诊断（给 AI 排错用，0 猜测）
struct Diag {
    std::string chip;                // 判定到的芯片（如 "RTL8733BS" / "AIC8800" / "未知"）
    std::string uart;                // 实际用的串口
    uint32_t baud = 0;               // 实际工作波特率
    bool powered = false;            // state_bt 实测（回读）
    bool preinit_ok = false;         // 预初始化是否完成
    bool ready = false;              // HCI 到 WORKING
    int  hci_state = 0;              // 0 OFF / 1 INITIALIZING / 2 WORKING / ...
    int  hci_events = 0;             // 芯片真实事件数（只统计 0x01~0x5F）
    int  transport_sent = 0;         // 0x6E 计数：只是"我发出去了"，不算芯片回应
    int  devices_seen = 0;           // 扫到的设备数（缓存里）
    int  last_error = 0;
    std::string last_error_msg;
    std::string hint;                // 一句话下一步建议（人话）
};
Result getDiag(Diag& out);

// 版本：门面版本与内部 btstack 包版本分开报（btstack 头里的版本号不可信）
std::string version();

}  // namespace ble
}  // namespace zk
