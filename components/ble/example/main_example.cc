/*
 * main_example.cc —— zk::ble 中心侧最小示例（扫描 → 连接 → 服务发现 → 读写订阅）
 *
 * 拿去就能用：把 components/ble/{include,src} 拷进工程，本文件当 src/main.cpp 或业务逻辑用。
 * 编译自检：wsl bash components/ble/scripts/compile_check.sh（btstack 后端）
 *           wsl bash components/ble/scripts/compile_check_gatt.sh（gatt 后端）
 *
 * 说明：示例只用公开 API，不 include 任何底层头（btstack/gatt 都被门面挡住了）。
 */
#include "zk/zk_ble.h"

#include <stdio.h>
#include <unistd.h>
#include <string>
#include <vector>

static std::vector<zk::ble::DeviceInfo> g_devices;

static void dumpResult(const char* what, const zk::ble::Result& r) {
    printf("[%s] %s %s\n", r.ok() ? "OK" : "FAIL", what, r.msg.c_str());
}

int main() {
    // 0) 先问能力（跨平台早知道；F133/V85X 外设=false，Z20/Z21 才是双角色）
    zk::ble::Capabilities cap;
    zk::ble::getCapabilities(cap);
    printf("后端=%s 中心=%d 外设=%d ｜ %s\n",
           cap.backend.c_str(), (int)cap.central, (int)cap.peripheral, cap.note.c_str());

    // 1) 回调（在库线程里被调 —— 只做轻活）
    zk::ble::onAdapterStateChange([](const zk::ble::AdapterState& st) {
        printf("[cb] adapter available=%d discovering=%d power_on=%d\n",
               (int)st.available, (int)st.discovering, (int)st.power_on);
    });
    zk::ble::onDeviceFound([](const zk::ble::DeviceInfo& d) {
        printf("[cb] 发现 %s  name=%s  rssi=%d  adv=%s\n",
               d.id.c_str(), d.name.c_str(), d.rssi, d.adv_data_hex.c_str());
        g_devices.push_back(d);
    });
    zk::ble::onConnectionChange([](const std::string& id, bool connected) {
        printf("[cb] %s %s\n", id.c_str(), connected ? "已连接" : "已断开");
    });
    zk::ble::onValueChange([](const zk::ble::Value& v) {
        printf("[cb] 通知 %s/%s len=%zu\n",
               v.service_uuid.c_str(), v.char_uuid.c_str(), v.data.size());
    });

    // 2) 打开适配器（上电/预初始化/HCI/线程，全部内部做掉）
    zk::ble::Config cfg;
    cfg.connect_retry = 2;              // Z20/Z21 实测：控制器会残留链路 → 让库自己重试
    dumpResult("openAdapter", zk::ble::openAdapter(cfg));

    if (!zk::ble::adapterReady()) {
        zk::ble::Diag d;
        zk::ble::getDiag(d);
        printf("适配器没起来 → backend=%s chip=%s powered=%d preinit_ok=%d hci_state=%d\n  hint: %s\n",
               d.backend.c_str(), d.chip.c_str(), (int)d.powered, (int)d.preinit_ok, d.hci_state, d.hint.c_str());
        return 1;
    }

    // 3) 扫描（示例：按名字前缀过滤；也可 addr_prefix / service_uuid）
    zk::ble::ScanOptions so;
    so.name_prefix = "zkswe";            // 只扫目标设备（列表干净，方便点选/自动连）
    so.duration_ms = 8000;
    dumpResult("startDiscovery", zk::ble::startDiscovery(so));
    sleep(5);

    std::vector<zk::ble::DeviceInfo> devs;
    zk::ble::getDevices(devs);
    printf("扫到 %zu 个设备\n", devs.size());
    if (devs.empty()) {
        zk::ble::stopDiscovery();
        zk::ble::closeAdapter();
        return 2;
    }

    // 4) 连接 + 服务发现
    const std::string id = devs[0].id;
    dumpResult("connect", zk::ble::connect(id));

    std::vector<zk::ble::Service> svcs;
    dumpResult("getServices", zk::ble::getServices(id, svcs));
    for (size_t i = 0; i < svcs.size(); i++) {
        printf("  service %s\n", svcs[i].uuid.c_str());
        for (size_t j = 0; j < svcs[i].characteristics.size(); j++) {
            const zk::ble::Characteristic& c = svcs[i].characteristics[j];
            printf("    char %s props=0x%02x handle=0x%04x\n",
                   c.uuid.c_str(), c.properties, c.value_handle);
        }
    }
    if (svcs.empty() || svcs[0].characteristics.empty()) {
        zk::ble::disconnect();
        zk::ble::closeAdapter();
        return 3;
    }

    // 5) 读 / 写 / 订阅（第一个服务的第一个特征做演示）
    const std::string su = svcs[0].uuid;
    const std::string cu = svcs[0].characteristics[0].uuid;

    std::string val;
    dumpResult("readValue", zk::ble::readValue(id, su, cu, val));
    printf("  读到 %zu 字节\n", val.size());

    dumpResult("writeValue", zk::ble::writeValue(id, su, cu, std::string("\x01", 1), true));
    dumpResult("subscribe", zk::ble::subscribe(id, su, cu, true));

    sleep(3);

    // 6) 收尾（一定 offAll + disconnect + closeAdapter）
    zk::ble::subscribe(id, su, cu, false);
    zk::ble::disconnect();
    zk::ble::offAll();
    zk::ble::closeAdapter();
    printf("done\n");
    return 0;
}
