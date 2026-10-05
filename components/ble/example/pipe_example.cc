/*
 * pipe_example.cc —— 透传管道（zk::ble::pipe）最小案例
 *
 * 这就是「AI 最省事」的那条路：不懂 GATT 的服务/特征/CCCD，只收发字节。
 * 同一个进程里不要同时用两端（单连接模型）；下面用宏切换角色。
 *
 * 编译（示例）：见 components/ble/scripts/compile_check.sh（只编不链，验证 API 面）
 * 真机（V85X 外设端）：
 *   1) openAdapter() 之前，先挂项目侧的预初始化钩子（RTL8733BS 必须）：
 *        zk::ble::setPreinitHook([](const std::string& uart, uint32_t baud) -> zk::ble::Result {
 *            return rtk_init(uart.c_str()) == 0 ? zk::ble::Result::ok_()
 *                                              : zk::ble::Result::err(zk::ble::ERR_POWER_OFF, "rtk_init 失败");
 *        });
 *   2) openAdapter() → pipe::listen("zkswe-pipe") → pipe::onData(...) → pipe::send(...)
 */
#include "zk/zk_ble.h"

#include <stdio.h>
#include <unistd.h>
#include <string>

// 0 = 外设端（设备当 BLE 从机，手机连上来读写）
// 1 = 中心端（设备当主机，去连别的 BLE 从机）
#define PIPE_DEMO_ROLE_CENTRAL 0

static void onPipeData(const std::string& data) {
    printf("[pipe] 收到 %u 字节:", (unsigned)data.size());
    for (size_t i = 0; i < data.size(); i++) printf(" %02x", (unsigned char)data[i]);
    printf("\n");
}

static void onPipeState(bool connected, const std::string& peer) {
    printf("[pipe] %s %s\n", connected ? "已连接" : "已断开", peer.c_str());
}

int main() {
    zk::ble::Capabilities cap;
    zk::ble::getCapabilities(cap);
    printf("[pipe] backend=%s peripheral=%d central=%d | %s\n",
           cap.backend.c_str(), (int)cap.peripheral, (int)cap.central, cap.note.c_str());
    if (!cap.peripheral && !cap.central) {
        printf("[pipe] 本平台不支持外设也不支持中心，退出\n");
        return 1;
    }

    // 适配器（V85X 记得先 setPreinitHook；见文件头注释）
    zk::ble::Result r = zk::ble::openAdapter();
    if (!r.ok()) {
        printf("[pipe] openAdapter 失败: code=%d msg=%s\n", r.code, r.msg.c_str());
        zk::ble::Diag d;
        zk::ble::getDiag(d);
        printf("[pipe] hint: %s\n", d.hint.c_str());
        return 1;
    }

    zk::ble::pipe::onData(onPipeData);
    zk::ble::pipe::onState(onPipeState);

#if PIPE_DEMO_ROLE_CENTRAL
    r = zk::ble::pipe::connect("zkswe-pipe", 10000);
#else
    r = zk::ble::pipe::listen("zkswe-pipe");
#endif
    printf("[pipe] %s → code=%d msg=%s\n",
           PIPE_DEMO_ROLE_CENTRAL ? "connect" : "listen", r.code, r.msg.c_str());
    if (!r.ok()) { zk::ble::closeAdapter(); return 1; }

    // 每 3 秒发一条（连上才发；没连上会返回 ERR_DISCONNECTED，这是预期行为）
    for (int i = 0; i < 20; i++) {
        sleep(3);
        if (!zk::ble::pipe::isConnected()) continue;
        char buf[16];
        snprintf(buf, sizeof(buf), "hello %02d", i);
        zk::ble::Result sr = zk::ble::pipe::send(std::string(buf, 8));
        printf("[pipe] send '%s' → code=%d msg=%s\n", buf, sr.code, sr.msg.c_str());
    }

    zk::ble::pipe::stop();
    zk::ble::offAll();
    zk::ble::closeAdapter();
    return 0;
}
