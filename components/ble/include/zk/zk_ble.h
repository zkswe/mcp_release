/*
 * zk_ble.h —— BLE 门面（zk::ble）v0.2 —— 面向业务/AI 的**唯一**蓝牙接口
 *
 * 定位：拿微信小程序 wx.* BLE 那套用法做 C++ 版；**一个 API 面、两个平台后端**：
 *   · 中心侧（Central）   openAdapter → startDiscovery → onDeviceFound → getDevices
 *                        → connect → getServices → readValue / writeValue / subscribe → onValueChange
 *   · 外设侧（Peripheral）peripheral::start(PeripheralConfig) → 广播 + GATT 服务
 *                        → onConnectionChange / onWrite → peripheral::notify()
 *
 * 平台后端（业务不用改代码，只看 backendName() / getCapabilities()）：
 *   ┌──────────┬───────────────┬───────────────────────────────────────────────┐
 *   │ 平台     │ 后端          │ 说明                                          │
 *   ├──────────┼───────────────┼───────────────────────────────────────────────┤
 *   │ F133     │ btstack 1.7.2 │ 串口 HCI（H5）；中心 + 外设（v0.3.0 起）      │
 *   │ V85X     │ btstack 1.8.0 │ 串口 HCI（H5）+ 预初始化钩子；中心 + 外设    │
 *   │ Z20/Z21  │ gatt 1.0.0    │ AIC USB 模组 + BlueZ 用户态 GATT，**主从双角色** │
 *   │ T113(EMMC) │ gatt 1.0.0  │ 同 Z20/Z21                                    │
 *   └──────────┴───────────────┴───────────────────────────────────────────────┘
 *   选哪个后端由编译期自动判定（谁的头文件在 include 路径里就用谁）；
 *   要强制指定：-DZKBLE_BACKEND_GATT=1 或 -DZKBLE_BACKEND_BTSTACK=1。
 *
 * 硬约定（写代码前先读这 6 条）：
 *   1) 全部接口同步返回 Result{code,msg}，msg 是人话；不抛异常、不静默失败；
 *   2) 本头文件里不出现任何 btstack / gatt 类型（底层细节不外泄）；想直接调底层仍可自行 include；
 *   3) 回调（on*）在库内部线程被调用 —— 回调里只做轻活，重活请切回自己的线程；
 *   4) 平台差异、上电、hciattach/hciconfig、H5/偶校验、TLV 落盘、run loop 线程，全部由本模块做掉；
 *   5) 平台能力不一致时**明确返回 ERR_UNSUPPORTED + 人话 hint**（例：F133 上跑 peripheral），
 *      不假装能用；要提前判断就调 getCapabilities()；
 *   6) 排错先看 getDiag() —— 它会告诉你卡在哪一步、下一步该查什么。
 *
 * 详见同目录 README.md（用法）与 platforms.md（平台/后端逐条说明）。
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
    ERR_UNSUPPORTED = -8,    // 当前平台/后端/裁剪不支持（msg + hint 说明该怎么办）
    ERR_NO_MEM = -9,
    ERR_IO = -10,            // 节点读写/落盘/系统命令失败（含权限）
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

struct Value {                       // 读/通知回来的数据（中心侧）
    std::string device_id;
    std::string service_uuid;
    std::string char_uuid;
    std::string data;                // 原始字节（std::string 当 byte buffer 用）
};

struct AdapterState {
    bool available = false;          // 适配器可用（HCI 到了 WORKING / hci0 已 up）
    bool discovering = false;        // 是否正在扫描
    bool power_on = false;           // 模组是否已上电（sysfs/驱动实测回读，非"我以为"）
};

// ---------------------------------------------------------------- 能力（跨平台早知道）
struct Capabilities {
    bool central = false;            // 能当中心（扫描/连接/GATT 客户端）
    bool peripheral = false;         // 能当外设（广播 + GATT 服务）
    bool notify = false;             // 外设侧能主动 notify
    bool bonded_db = false;          // 支持配对信息落盘（getBondedDevices 有内容）
    std::string backend;             // "btstack" / "gatt"
    std::string note;                // 人话补充（例："外设侧请用 V85X 的 blehid 包"）
};
Result getCapabilities(Capabilities& out);
std::string backendName();           // 当前编译进来的后端名（"btstack" / "gatt"）

// ---------------------------------------------------------------- 配置（中心侧）
struct Config {
    std::string module;              // 模组标识覆盖（默认读 /data/property/persist.wifi.module）；含 "8733" → Realtek 分支
    std::string uart;                // 留空 = 自动（按平台默认 + 节点存在性探测）
    uint32_t baud = 0;               // 0 = 默认（Realtek 预初始化内部会 115200 → 1500000）
    std::string tlv_path = "/data/bttlv.db";  // 配对信息落盘（需可写分区）
    std::string fw_dir;              // Realtek 补丁固件目录；留空走候选链
    bool auto_power = true;          // ★自动上电（sysfs state_bt / insmod+hciconfig）
    int  power_off_ms = 3000;        // Realtek 类：断电保持时间（实测 3s 比 50ms 稳）
    int  power_on_ms = 2000;         // Realtek 类：上电后等待时间
    int  preinit_retry = 3;          // 预初始化失败重试次数（每次重试前重新上电）
    bool prefer_h5 = true;           // 8733bs 必须 H5；AIC（8800DL 等）置 false 走 H4
    int  flowcontrol = -1;           // -1 = 自动（8733bs→0；AIC→1）；0=off 1=on
    int  parity = -1;                // -1 = 自动（8733bs→偶校验 8E1；AIC/F133→无）
    int  open_timeout_ms = 60000;    // openAdapter 等 HCI 到 WORKING 的超时（含预初始化重试余量）
    int  op_timeout_ms = 8000;       // 连接/读写等单次操作超时
    int  connect_retry = 2;          // ★连接失败自动重试次数（Z20/Z21 实测：控制器残留链路 → 必须重试）
    bool reset_before_retry = true;  // ★重试前 hciconfig reset（gatt 后端；实测"复位后第一次必成功"）
};

// ================================================================ 适配器
// 一步完成：芯片判定 → 上电 → (预初始化) → HCI 通路 → TLV → 起线程 → 等 WORKING
Result openAdapter(const Config& cfg = Config());
void   closeAdapter();
bool   adapterReady();
Result getAdapterState(AdapterState& out);

// 日志钩子：默认走 printf；应用里可挂到自己的日志系统（如 easyui 的 LOGD → logcat）
using LogHook = std::function<void(const std::string&)>;
void setLogHook(LogHook hook);

// ---------------------------------------------------------------- btstack 后端专用钩子
// Realtek（RTL8733BS 等）类模组必须做 hciattach 预初始化（同步握手/读ROM/下固件/切波特率）。
// 本模块不内置该流程：由项目侧提供实现并注册（把工程里 src/ble/rtk/ 那套挂进来即可）。
// 未注册 + 模组需要预初始化 → openAdapter 返回 ERR_UNSUPPORTED 并指明。
// （gatt 后端不走这条路：AIC USB 模组由驱动 + hciconfig 拉起）
using PreinitHook = std::function<Result(const std::string& uart, uint32_t baud)>;
void setPreinitHook(PreinitHook hook);

// ================================================================ 扫描（中心侧）
struct ScanOptions {
    std::string name_prefix;         // 按名字前缀过滤，如 "BTHome"
    std::string addr_prefix;         // 按地址前缀过滤，如 "DC:84"；兼容 Sample 的 "A#<addr前缀>" 写法
    std::string service_uuid;        // 按 Service Data 里的服务过滤，如 "fcd2"（16 位或 128 位）
    bool allow_duplicates = false;   // 同一设备重复上报？
    int  duration_ms = 0;            // 0 = 一直扫，直到 stopDiscovery()
};
Result startDiscovery(const ScanOptions& opts = ScanOptions());
Result stopDiscovery();
Result getDevices(std::vector<DeviceInfo>& out);   // 扫描缓存快照（线程安全）
Result clearDevices();

// ================================================================ 连接 + 服务发现（中心侧）
Result connect(const std::string& device_id, int timeout_ms = 0);   // 0 = 用 Config.op_timeout_ms
Result disconnect(const std::string& device_id = std::string());    // 空 = 断当前连接
bool   isConnected(const std::string& device_id = std::string());
Result getServices(const std::string& device_id, std::vector<Service>& out);   // 含特征列表
Result getCharacteristics(const std::string& device_id,
                          const std::string& service_uuid,
                          std::vector<Characteristic>& out);

// ================================================================ 数据（中心侧）
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

// ================================================================ 外设模式（Peripheral）
// 对标 Android 的 BluetoothGattServer + BluetoothLeAdvertiser（微信小程序没有外设侧，故参照 Android）。
// 支持情况看 getCapabilities().peripheral：
//   · gatt 后端（Z20/Z21/T113）：✅ 自定义服务表 + 广播 + notify
//   · btstack 后端（F133/V85X）：❌ 返回 ERR_UNSUPPORTED，hint 指路（V85X 用 blehid 包做 HID/触摸上报）
struct PeripheralChar {
    std::string uuid;                // 特征 UUID（16 位如 "fff1" 或 128 位）
    int properties = PROP_READ | PROP_WRITE | PROP_NOTIFY;   // 见 CharProp
    std::string value;               // 初始值（可空）

    // ★显式构造函数：C++11 下带默认成员初值的结构体不是聚合体，不能 `PeripheralChar{"fff1",x,y}`
    // （fsc build 固定 -std=c++11 → 实测报 no matching function）
    PeripheralChar() {}
    PeripheralChar(const std::string& u, int p = PROP_READ | PROP_NOTIFY,
                   const std::string& v = std::string())
        : uuid(u), properties(p), value(v) {}
};

struct PeripheralConfig {
    std::string device_name = "FlyThings";   // 对外广播名（写进 AD 的 Complete Local Name）
    std::string service_uuid;                // 必填：自定义服务 UUID（如 "fff0"）
    std::vector<PeripheralChar> characteristics;   // 至少一个；第一个常做"透传/上报"通道
    bool auto_power = true;                  // 自动 insmod/hciconfig up
    bool auto_adv = true;                    // start() 里直接开广播
};

namespace peripheral {
    Result start(const PeripheralConfig& cfg);
    Result stop();
    Result setDeviceName(const std::string& name);
    Result notify(const std::string& char_uuid, const std::string& data);  // 主动通知已订阅的中心
    Result isConnected(bool& out);
}  // namespace peripheral

// ================================================================ 透传管道（pipe）—— AI 最省事的入口
// 90% 的活其实就是「发字节 / 收字节」：不想懂 GATT 的服务/特征/CCCD 时，直接用 pipe。
// 形状参考 Nordic UART Service（NUS，事实标准，手机端有现成 App 可对接）：
//   · 外设端：pipe::listen("名字") → pipe::onData(cb) → pipe::send(bytes)
//   · 中心端：pipe::connect("名字") → pipe::onData(cb) → pipe::send(bytes)
// 默认服务 UUID = NUS（6e400001-b5a3-f393-e0a9-e50e24dcca9e），可传自定义 service_uuid。
// 注意：pipe 是便捷层，会占用 onWriteRequest / onConnectionChange / onValueChange 三个回调槽；
//       要自己接管这些回调就别用 pipe（或改用 peripheral::* / 中心侧细粒度 API）。
namespace pipe {
    using OnData  = std::function<void(const std::string& data)>;                 // 收到字节
    using OnState = std::function<void(bool connected, const std::string& peer)>; // 连接变化

    Result listen(const std::string& device_name,                    // 外设端：起表 + 广播（内部 peripheral::start）
                  const std::string& service_uuid = std::string());
    Result connect(const std::string& device_name,                   // 中心端：扫描→连接→订阅（同步，带超时）
                   int scan_timeout_ms = 8000);
    Result send(const std::string& data);                            // 两端都能用
    bool   isConnected();
    Result disconnect();
    Result stop();                                                   // 收摊（外设端停广播）

    void onData(OnData cb);
    void onState(OnState cb);
}  // namespace pipe

// ================================================================ 回调（wx 的 onXxx / offXxx）
using OnAdapterStateChange = std::function<void(const AdapterState&)>;
using OnDeviceFound        = std::function<void(const DeviceInfo&)>;
using OnConnectionChange   = std::function<void(const std::string& device_id, bool connected)>;
using OnValueChange        = std::function<void(const Value&)>;          // 中心侧：通知/指示
using OnWriteRequest       = std::function<void(const std::string& char_uuid,
                                                const std::string& data)>;   // 外设侧：中心写了我们的特征

void onAdapterStateChange(OnAdapterStateChange cb);
void onDeviceFound(OnDeviceFound cb);
void onConnectionChange(OnConnectionChange cb);
void onValueChange(OnValueChange cb);
void onWriteRequest(OnWriteRequest cb);
void offAll();                       // 一键清空全部回调（退出页面前调）

// ================================================================ 诊断（给 AI 排错用，0 猜测）
struct Diag {
    std::string backend;             // "btstack" / "gatt"
    std::string chip;                // 判定到的芯片/通路（如 "RTL8733BS" / "AIC USB 模组" / "未知"）
    std::string uart;                // btstack 后端：实际用的串口；gatt 后端：空
    uint32_t baud = 0;               // btstack 后端：实际工作波特率
    bool powered = false;            // 实测回读（state_bt / hci0 存在）
    bool preinit_ok = false;         // 预初始化是否完成（gatt 后端 = HCI 通路拉起成功）
    bool ready = false;              // HCI 到 WORKING / hci0 up
    int  hci_state = 0;              // 0 OFF / 1 INITIALIZING / 2 WORKING / ...
    int  hci_events = 0;             // 芯片真实事件数（只统计 0x01~0x5F）
    int  transport_sent = 0;         // 0x6E 计数：只是"我发出去了"，不算芯片回应（btstack 后端）
    int  devices_seen = 0;           // 扫到的设备数（缓存里）
    int  connect_attempts = 0;       // 本次连接尝试次数（含自动重试）
    int  last_error = 0;
    std::string last_error_msg;
    std::string hint;                // 一句话下一步建议（人话）
};
Result getDiag(Diag& out);

// 版本：门面版本（与底层包版本分开报）
std::string version();

}  // namespace ble
}  // namespace zk
