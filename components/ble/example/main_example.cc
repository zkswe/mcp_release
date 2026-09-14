/*
 * main_example.cc —— 直接可用的最小示例（扫到 → 连上 → 收到通知）
 *
 * 放进工程 src/ 下、或加到 CMake 即可；对应 UI 上一颗"开始/停止"按钮也行。
 * 依赖：components/ble（见 ../README.md 的「怎么把它接进工程」）。
 */
#include "zk/zk_ble.h"
#include <stdio.h>

static std::vector<zk::ble::DeviceInfo> g_devices;

int main_ble_demo() {
    // 1) 打开适配器（默认就把上电/预初始化/H5/TLV/线程做掉）
    zk::ble::Config cfg;
    zk::ble::Result r = zk::ble::openAdapter(cfg);
    if (!r.ok()) {
        printf("openAdapter 失败: %s\n", r.msg.c_str());
        zk::ble::Diag d;                     // 失败先看诊断，不要猜
        zk::ble::getDiag(d);
        printf("  chip=%s uart=%s powered=%d preinit=%d hci_state=%d events=%d\n",
               d.chip.c_str(), d.uart.c_str(), d.powered, d.preinit_ok, d.hci_state, d.hci_events);
        printf("  hint=%s\n", d.hint.c_str());
        return -1;
    }

    // 2) 注册回调（回调里只做轻活）
    zk::ble::onDeviceFound([](const zk::ble::DeviceInfo& d) {
        printf("发现 %s  %s  rssi=%d\n", d.id.c_str(), d.name.c_str(), d.rssi);
    });
    zk::ble::onValueChange([](const zk::ble::Value& v) {
        printf("通知 %s %s/%s  len=%zu\n", v.device_id.c_str(),
               v.service_uuid.c_str(), v.char_uuid.c_str(), v.data.size());
    });

    // 3) 扫描（可选过滤）
    zk::ble::ScanOptions so;
    so.name_prefix = "";        // 如 "BTHome"
    so.duration_ms = 5000;      // 0 = 一直扫
    zk::ble::startDiscovery(so);

    // 4) 拿到设备
    { zk::ble::DeviceInfo first; bool has = false;
      while (!has) {
          zk::ble::getDevices(g_devices);
          if (!g_devices.empty()) { first = g_devices[0]; has = true; }
          else usleep(200 * 1000);
      }
      // 5) 连接 + 服务发现 + 订阅第一个可通知特征
      zk::ble::connect(first.id);
      std::vector<zk::ble::Service> svcs;
      if (zk::ble::getServices(first.id, svcs).ok()) {
          for (size_t i = 0; i < svcs.size(); i++) {
              for (size_t j = 0; j < svcs[i].characteristics.size(); j++) {
                  if (svcs[i].characteristics[j].properties & zk::ble::PROP_NOTIFY) {
                      zk::ble::subscribe(first.id, svcs[i].uuid, svcs[i].characteristics[j].uuid, true);
                      i = svcs.size(); break;
                  }
              }
          }
      }
    }
    return 0;
}
