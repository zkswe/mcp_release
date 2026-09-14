/*
 * peripheral_example.cc —— zk::ble 外设侧最小示例（广播 + GATT 服务 + notify + 收写）
 *
 * 平台：Z20 / Z21 / T113 / T113EMMC（gatt 后端）。
 * 在 btstack 后端（F133/V85X）上跑会得到 ERR_UNSUPPORTED + 指路 hint（V85X 用 blehid 包），这是**预期行为**。
 *
 * 真机跑法（本机验证过的套路，fun launch 在多设备下选不中时用）：
 *   fun build -p z20 → adb -s <设备> push .fun/z20/peripheral_example /tmp/ && chmod 777 /tmp/peripheral_example && /tmp/peripheral_example
 * 前置：设备上要有 hciconfig/hcitool（没放 /res/bin 时，推到 /data/bin 也能被候选链兜住）。
 */
#include "zk/zk_ble.h"

#include <stdio.h>
#include <string>
#include <unistd.h>

static void dumpResult(const char* what, const zk::ble::Result& r) {
    printf("[%s] %s %s\n", r.ok() ? "OK" : "FAIL", what, r.msg.c_str());
}

int main() {
    zk::ble::Capabilities cap;
    zk::ble::getCapabilities(cap);
    printf("后端=%s 外设=%d ｜ %s\n", cap.backend.c_str(), (int)cap.peripheral, cap.note.c_str());

    // 1) 业务回调
    zk::ble::onConnectionChange([](const std::string& id, bool connected) {
        printf("[cb] 中心 %s %s\n", id.c_str(), connected ? "已连接" : "已断开");
    });
    zk::ble::onWriteRequest([](const std::string& cu, const std::string& data) {
        printf("[cb] 收到写：char=%s len=%zu\n", cu.c_str(), data.size());
        // 收到什么就回什么（示例：把上报通道的当前值更新掉）
        // zk::ble::peripheral::notify("fff1", data);
    });

    // 2) 启动外设：设备名 + 自定义服务/特征 + 自动广播
    zk::ble::PeripheralConfig pc;
    pc.device_name  = "zkswe ble";           // 广播里的 Complete Local Name
    pc.service_uuid = "fff0";                // 自定义服务（16 位或 128 位都行）
    pc.characteristics.push_back(zk::ble::PeripheralChar{
        "fff1", zk::ble::PROP_READ | zk::ble::PROP_NOTIFY, std::string() });
    pc.characteristics.push_back(zk::ble::PeripheralChar{
        "fff2", zk::ble::PROP_WRITE | zk::ble::PROP_WRITE_NO_RESPONSE, std::string() });
    pc.auto_power = true;                    // 自动 insmod aic_btusb / hciconfig hci0 up
    pc.auto_adv   = true;                    // start() 里直接开广播

    zk::ble::Result r = zk::ble::peripheral::start(pc);
    dumpResult("peripheral::start", r);
    if (!r.ok()) {
        zk::ble::Diag d;
        zk::ble::getDiag(d);
        printf("没起来 → backend=%s powered=%d ready=%d hint: %s\n",
               d.backend.c_str(), (int)d.powered, (int)d.ready, d.hint.c_str());
        return 1;
    }

    // 3) 主循环：有中心连上就周期 notify（示例数据 01 02 03）
    while (true) {
        bool connected = false;
        zk::ble::peripheral::isConnected(connected);
        if (connected) {
            const std::string data("\x01\x02\x03", 3);
            dumpResult("notify", zk::ble::peripheral::notify("fff1", data));
        }
        sleep(2);
    }

    // 4) 收尾（本示例是死循环，正常不会走到这儿；业务里记得调）
    // zk::ble::peripheral::stop();
    // zk::ble::offAll();
    return 0;
}
