/*
 * zk_ha_bridge_demo.cc —— ha_bridge 最小示例（FlyThings 逻辑文件，拷进工程 src/logic/ 即用）
 *
 * 做什么：连 broker -> 连上后自动发一次 discovery/state/status -> 收命令打印 + 翻转继电器。
 *
 * 用法：
 *   ① 把 components/ha_bridge/{include,src} 拷进工程（如 src/zk/），Manifest 按 ha_bridge/Manifest.xml 声明依赖；
 *   ② 本文件拷进 src/logic/，改名为你的页面逻辑名（或直接合并进现有 onUI_init/onUI_Timer）；
 *   ③ onUI_init 里填你的 broker 地址与前缀（**别写死在组件里** —— 工程侧应从配网页/prefs 取）。
 *
 * ⚠️ 三条纪律（真机踩出来的）：
 *   - onCommand/onConnected/onDisconnected 都在 mqtt-cxx 的**库线程**上跑：只置标志位，别动 UI；
 *   - tick() 必须被周期调（本示例 1s）：它负责重连（**唯一的应用层重连真源**）与差分兜底；
 *   - 继电器状态一律读 `Bridge::instance().relays().get(ch)`，别自己另存一份。
 */

#include "zk/zk_ha_bridge.h"

#include "utils/Log.h"   /* LOGD/LOGW：来自 log 包（app 模式 stdout 是 /dev/null，组件日志建议装钩子）*/

#include <stdio.h>
#include <string>

/* ============ 工程侧配置（示例：真机上改成从配网页/prefs 读，组件本身不写死任何值）============ */
static zk::ha::Config makeConfig() {
    zk::ha::Config cfg;
    cfg.server      = "mqtt://<broker>:1883";      /* 必填 */
    cfg.username    = "";                          /* 不用认证留空 */
    cfg.password    = "";                          /* HA 长令牌放这里；粘贴时先去换行/空格 */
    cfg.prefix      = "panel/<设备ID>";             /* 主题前缀：工程侧按 deviceId 拼好 */
    cfg.deviceId    = "<设备ID>";                   /* HA unique_id / device 归组用 */
    cfg.deviceName  = "客厅面板";                   /* HA 里显示的名字 */
    cfg.manufacturer = "";                          /* 空 = 不发该字段（不编造）*/
    cfg.model       = "";
    cfg.channels    = 3;
    cfg.relayNames.push_back("客厅灯");
    cfg.relayNames.push_back("卧室灯");
    cfg.relayNames.push_back("灯带");

    /* 命令回调：**库线程** —— 只置待办标志，UI 放到定时器里做 */
    cfg.onCommand = [](int ch, bool on) {
        LOGD("ha demo: command relay_%d = %s", ch, on ? "ON" : "OFF");
    };
    cfg.onConnected    = []() { LOGD("ha demo: connected"); };
    cfg.onDisconnected = [](const std::string &cause) { LOGW("ha demo: lost (%s)", cause.c_str()); };

    /* 整机状态 JSON：组件不编造状态内容，由业务给（示例给个最小串）*/
    cfg.statusJson = []() {
        char buf[192];
        snprintf(buf, sizeof(buf), "{\"relays\":[%d,%d,%d]}",
                 zk::ha::Bridge::instance().relays().get(1) ? 1 : 0,
                 zk::ha::Bridge::instance().relays().get(2) ? 1 : 0,
                 zk::ha::Bridge::instance().relays().get(3) ? 1 : 0);
        return std::string(buf);
    };
    return cfg;
}

/* ============ FlyThings 页面钩子 ============ */

static void onUI_init() {
    /* 继电器 listener 要在 start() 之后注册（start 可能重设通道数并清 listener）*/
    zk::ha::Result r = zk::ha::Bridge::instance().start(makeConfig());
    if (!r.ok()) LOGW("ha demo: start failed (%d) %s", r.code, r.msg.c_str());

    /* UI 视觉单槽（覆盖式，跟业务上报互不影响 —— 这就是 RelayManager 那个坑的修法）*/
    zk::ha::Bridge::instance().relays().setUiListener(
        [](int ch, bool on) { LOGD("ha demo: ui refresh card %d -> %d", ch, on ? 1 : 0); });

    /* 本地/触摸操作：一律走 relays().set()（唯一事实源）-> 自动回发 HA */
    zk::ha::Bridge::instance().relays().set(1, true);
}

static bool onUI_Timer(int id) {
    if (id == 0) {
        /* 1s：重连 + 差分兜底（**唯一的应用层重连真源**，别在别处再 new client）*/
        zk::ha::Bridge::instance().tick();
    }
    return true;
}

static void onUI_quit() {
    zk::ha::Bridge::instance().stop();   /* 停 = 销毁 client（同 client_id 不许留两个）*/
}

/* ============ 对外动作示例 ============ */

/* 收到触摸/按键：翻一路灯，状态自动上报 */
static void onSwitchTouched(int ch) {
    zk::ha::RelayBank &bank = zk::ha::Bridge::instance().relays();
    bank.toggle(ch);
}

/* 只发一次状态（手动补发场景）*/
static void publishOnce() {
    zk::ha::Result r = zk::ha::Bridge::instance().publishState(1, true);
    if (!r.ok()) LOGW("ha demo: publishState -> %s", r.msg.c_str());
}

/* 换了设备名之后让 HA 立刻更新 */
static void renameDevice(const std::string &newName) {
    (void) newName;                              /* 工程侧：先写 prefs，再重建 Config */
    zk::ha::Bridge::instance().start(makeConfig());   /* start 内部先 stop：换名称即重连重发 */
    zk::ha::Bridge::instance().publishDiscovery();
}

/* 清掉旧版本发过的残留实体（retained 撤销：空 payload + retained）*/
static void clearLegacyEntity() {
    zk::ha::Bridge::instance().clearDiscovery("sensor", zk::ha::Bridge::instance().uniqueId() + "_temperature");
}
