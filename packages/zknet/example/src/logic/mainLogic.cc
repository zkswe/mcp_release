#pragma once
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#include "uart/ProtocolSender.h"

/*
 * zknet 依赖包用法示例（Z20 86 面板 / 480x480 · WiFi）
 *
 * 覆盖 API（头文件在 <项目>/../registry 的 include/net/）：
 *   NetManager  —— NETMANAGER 总入口：getWifiManager / getEthernetManager /
 *                  getLTE4GManager / getSoftApManager / getConnChannel()
 *   WifiManager —— enableWifi / isWifiEnable / startScan / stopScan / connect / disconnect /
 *                  reconnect / isConnected / getConnectionInfo / getIp / getMacAddr /
 *                  getWifiScanInfosLock / IWifiListener 回调 / 静态 IP 配置
 *   NetUtils    —— 静态工具：getIp(iname) / getMacAddr(iname) / getConfigureInfo(iname,...) /
 *                  enableIfc / dhcpRequestIp / dhcpReleaseIp
 *   SoftApManager —— setEnable / isEnable / getSoftApState / getIp / getSsid / getPwd
 *   EthernetManager / LTE4GManager —— isSupported / isConnected / getIp / getMacAddr
 *
 * ⚠️ 本示例的目标 AP 是常量（真机联调用）；产品里应从配置读。
 * ⚠️ 「WiFi 关」会切断 108 的 adb（adb 走 192.168.x.x:5555）——只在你人在现场时点。
 */

#include "net/NetManager.h"			// zknet：网络总入口
#include "net/WifiManager.h"		// zknet：WiFi
#include "net/WifiInfo.h"			// zknet：AP 信息
#include "net/NetUtils.h"			// zknet：静态网络工具
#include "net/SoftApManager.h"		// zknet：热点
#include "net/EthernetManager.h"	// zknet：以太网
#include "net/LTE4GManager.h"		// zknet：4G

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

/* 联调目标 AP（与 108 上 /data/misc/wifi/wpa_supplicant.conf 一致） */
static const char *kTargetSsid = "zkswe-soft";
static const char *kTargetPwd  = "www.zkswe.com";

/* 等待状态机（定时器 200ms 驱动，避免在 UI 线程里阻塞等待） */
enum EWait { E_WAIT_NONE = 0, E_WAIT_ENABLE, E_WAIT_SCAN, E_WAIT_CONNECT };
static int sWait = E_WAIT_NONE;
static int sWaitTick = 0;
static int sListenerAdded = 0;

/* 监听回调计数（zknet 内部线程回调，只记数+打日志，状态一律以 manager 读回为准） */
static int sCbEnable = 0, sCbConnect = 0, sCbScan = 0, sCbSupplicant = 0, sCbError = 0;

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
	{0, 200},
};

static void setStatus(const char *fmt, ...) {
	char buf[1024] = { 0 };
	va_list ap;
	va_start(ap, fmt);
	vsnprintf(buf, sizeof(buf) - 1, fmt, ap);
	va_end(ap);
	if (mTextStatusPtr != NULL) {
		mTextStatusPtr->setText(buf);
	}
	/* logcat 里每行都被日志框架截在换行处 → 打日志时把换行换成 " | "，保证取证是完整一条 */
	char oneline[1024] = { 0 };
	for (int i = 0, j = 0; buf[i] != '\0' && j < (int) sizeof(oneline) - 4; i++) {
		if (buf[i] == '\n') {
			oneline[j++] = ' ';
			oneline[j++] = '|';
			oneline[j++] = ' ';
		} else {
			oneline[j++] = buf[i];
		}
	}
	LOGD("zknet demo: %s\n", oneline);
}

static const char* enableStateText(E_WIFI_ENABLE st) {
	switch (st) {
	case E_WIFI_ENABLE_ENABLE:		return "开";
	case E_WIFI_ENABLE_DISABLE:		return "关";
	case E_WIFI_ENABLE_ENABLEING:	return "打开中";
	case E_WIFI_ENABLE_DISABLEING:	return "关闭中";
	default:						return "未知";
	}
}

static const char* channelText(ENetChannel ch) {
	switch (ch) {
	case E_NET_CHANNEL_WIFI:		return "WiFi";
	case E_NET_CHANNEL_ETHERNET:	return "以太网";
	case E_NET_CHANNEL_SOFTAP:		return "热点";
	default:						return "无";
	}
}

/* ---------------- WiFi 监听（IWifiListener 五个回调全实现） ---------------- */
class DemoWifiListener : public WifiManager::IWifiListener {
public:
	virtual void handleWifiEnable(E_WIFI_ENABLE event, int args) {
		sCbEnable++;
		LOGD("zknet demo: [cb] handleWifiEnable event=%d args=%d\n", (int) event, args);
	}
	virtual void handleWifiConnect(E_WIFI_CONNECT event, int args) {
		sCbConnect++;
		LOGD("zknet demo: [cb] handleWifiConnect event=%d args=%d\n", (int) event, args);
	}
	virtual void handleWifiErrorCode(E_WIFI_ERROR_CODE code) {
		sCbError++;
		LOGD("zknet demo: [cb] handleWifiErrorCode code=%d\n", (int) code);
	}
	virtual void handleWifiScanResult(std::vector<WifiInfo>* wifiInfos) {
		sCbScan++;
		LOGD("zknet demo: [cb] handleWifiScanResult n=%d\n",
				wifiInfos ? (int) wifiInfos->size() : -1);
	}
	virtual void notifySupplicantStateChange(int networkid, const char* ssid,
			const char* bssid, E_SUPPLICATION_STATE newState) {
		sCbSupplicant++;
		LOGD("zknet demo: [cb] supplicant netid=%d ssid=%s state=%d\n",
				networkid, ssid ? ssid : "(null)", (int) newState);
	}
};
static DemoWifiListener sWifiListener;

/* 把扫描结果拼成多行文本（按 RSSI 排序取前 6 个） */
static void formatScanList(std::vector<WifiInfo> &infos, char *buf, int size) {
	buf[0] = '\0';
	char head[128] = { 0 };
	snprintf(head, sizeof(head) - 1, "扫描到 %d 个 AP：\n", (int) infos.size());
	strncat(buf, head, size - strlen(buf) - 1);
	// 简单选择排序（AP 数量少，够用）
	for (size_t i = 0; i + 1 < infos.size(); i++) {
		for (size_t j = i + 1; j < infos.size(); j++) {
			if (infos[j].getRssi() > infos[i].getRssi()) {
				WifiInfo t = infos[i];
				infos[i] = infos[j];
				infos[j] = t;
			}
		}
	}
	int n = infos.size() > 6 ? 6 : (int) infos.size();
	for (int i = 0; i < n; i++) {
		char line[160] = { 0 };
		snprintf(line, sizeof(line) - 1, "  %s  %ddBm  %s\n",
				infos[i].getSsid().c_str(), infos[i].getRssi(),
				infos[i].getEncryption().c_str());
		strncat(buf, line, size - strlen(buf) - 1);
	}
}

/* 读一次连接信息 → 文本 */
static void formatConnection(char *buf, int size) {
	buf[0] = '\0';
	WifiManager *wifi = NETMANAGER->getWifiManager();
	if (wifi == NULL) {
		snprintf(buf, size - 1, "NETMANAGER->getWifiManager() = NULL");
		return;
	}
	char line[256] = { 0 };
	snprintf(line, sizeof(line) - 1, "支持=%d 开关=%s 连接=%d\nIP=%s MAC=%s\n",
			wifi->isSupported() ? 1 : 0, enableStateText(wifi->getEnableStatus()),
			wifi->isConnected() ? 1 : 0,
			wifi->getIp() ? wifi->getIp() : "-",
			wifi->getMacAddr() ? wifi->getMacAddr() : "-");
	strncat(buf, line, size - strlen(buf) - 1);
	WifiInfo *info = wifi->getConnectionInfo();
	if (info != NULL) {
		char l2[320] = { 0 };
		snprintf(l2, sizeof(l2) - 1,
				"当前 AP：%s  %ddBm  %dMHz\nbssid=%s enc=%s\n",
				info->getSsid().c_str(), info->getRssi(), info->getFreq(),
				info->getBssid().c_str(), info->getEncryption().c_str());
		strncat(buf, l2, size - strlen(buf) - 1);
	} else {
		strncat(buf, "当前 AP：-（getConnectionInfo() = NULL）\n", size - strlen(buf) - 1);
	}
}

/** 惰性拿 WifiManager（并注册监听）——**不在 onUI_init 里碰网络**，避免启动线程阻塞页面 */
static WifiManager* acquireWifi() {
	LOGD("zknet demo: acquireWifi: getWifiManager() ...\n");
	WifiManager *wifi = NETMANAGER->getWifiManager();
	LOGD("zknet demo: acquireWifi: -> %p\n", wifi);
	if (wifi != NULL && !sListenerAdded) {
		wifi->addWifiListener(&sWifiListener);
		sListenerAdded = 1;
		LOGD("zknet demo: acquireWifi: addWifiListener done\n");
	}
	return wifi;
}

/**
 * 当界面构造时触发
 * ⚠️ 只做 UI 初始化（不上网、不碰 NetManager）——首版在 init 里调 getWifiManager() 导致页面没起来
 */
static void onUI_init() {
  #ifdef FUN_BUILD
  INIT_UI_TIMERS
  #endif // FUN_BUILD
	LOGD("zknet demo: onUI_init enter（不碰网络，等按钮触发）\n");
	setStatus("就绪：zknet 网络包示例。\n点按钮执行调用（扫描 / 连接 / 读 IP·MAC / NetUtils / 热点 / 通道），\n"
			"结果同时进 logcat（zknet demo）。\n"
			"⚠️ 「WiFi 关」会切断本机 adb，只在现场点。");
}

static void onUI_intent(const Intent *intentPtr) {
	if (intentPtr != NULL) {
		//TODO
	}
}

static void onUI_show() {

}

static void onUI_hide() {

}

static void onUI_quit() {
	WifiManager *wifi = NETMANAGER->getWifiManager();
	if (wifi != NULL) {
		wifi->removeWifiListener(&sWifiListener);
	}
}

static void onProtocolDataUpdate(const SProtocolData &data) {

}

/* ==================== 自检 AUTO：全自动跑一遍（不需人工点） ====================
 * 顺序：读状态 → startScan → disconnect → connect(目标 AP) → enableWifi(false) 等 10s → enableWifi(true)
 * 每步一条 logcat（前缀 [AUTO k/6]）+ textview；WiFi 关 期间 adb 会断，10s 后自动开回来
 */
enum {
	AUTO_IDLE = 0, AUTO_READ, AUTO_SCAN, AUTO_DISCON, AUTO_CONN, AUTO_OFF, AUTO_ON, AUTO_DONE
};
static int sAuto = AUTO_IDLE;
static int sAutoTick = 0;
static char sAutoPanel[1200] = { 0 };

static WifiManager* acquireWifi();

static void autoLog(int step, const char *fmt, ...) {
	char msg[600] = { 0 };
	va_list ap;
	va_start(ap, fmt);
	vsnprintf(msg, sizeof(msg) - 1, fmt, ap);
	va_end(ap);
	char line[700] = { 0 };
	snprintf(line, sizeof(line) - 1, "[%d/6] %s\n", step, msg);
	strncat(sAutoPanel, line, sizeof(sAutoPanel) - strlen(sAutoPanel) - 1);
	if (mTextStatusPtr != NULL) {
		mTextStatusPtr->setText(sAutoPanel);
	}
	char one[700] = { 0 };
	snprintf(one, sizeof(one) - 1, "[AUTO %d/6] %s", step, msg);
	for (char *p = one; *p; p++) {
		if (*p == '\n') *p = ' ';
	}
	LOGD("zknet demo: %s\n", one);
}

static void autoStart() {
	sAuto = AUTO_READ;
	sAutoTick = 0;
	sAutoPanel[0] = '\0';
	autoLog(1, "开始自检：读状态");
	acquireWifi();
	char st[600] = { 0 };
	formatConnection(st, sizeof(st));
	autoLog(1, "%s", st);
}

static void autoTick() {
	WifiManager *wifi = acquireWifi();
	sAutoTick++;
	if (wifi == NULL) {
		autoLog(0, "getWifiManager()=NULL，停止");
		sAuto = AUTO_DONE;
		return;
	}
	switch (sAuto) {
	case AUTO_READ:
		autoLog(2, "startScan() 下发");
		wifi->startScan();
		sAuto = AUTO_SCAN;
		sAutoTick = 0;
		break;
	case AUTO_SCAN: {
		std::vector<WifiInfo> infos;
		wifi->getWifiScanInfosLock(infos);
		if (!infos.empty()) {
			wifi->stopScan();
			int n = (int) infos.size();
			for (size_t i = 0; i + 1 < infos.size() && i < 3; i++) {
				for (size_t j = i + 1; j < infos.size(); j++) {
					if (infos[j].getRssi() > infos[i].getRssi()) {
						WifiInfo t = infos[i];
						infos[i] = infos[j];
						infos[j] = t;
					}
				}
			}
			char top3[300] = { 0 };
			for (int i = 0; i < 3 && i < n; i++) {
				char t[110] = { 0 };
				snprintf(t, sizeof(t) - 1, "%s(%ddBm) ", infos[i].getSsid().c_str(), infos[i].getRssi());
				strncat(top3, t, sizeof(top3) - strlen(top3) - 1);
			}
			autoLog(2, "扫描到 %d 个 AP（%dms）：%s", n, sAutoTick * 200, top3);
			autoLog(3, "disconnect() 下发");
			wifi->disconnect();
			sAuto = AUTO_DISCON;
			sAutoTick = 0;
		} else if (sAutoTick > 40) {
			autoLog(2, "扫描 8s 无结果（回调 scan=%d），跳过", sCbScan);
			autoLog(3, "disconnect() 下发");
			wifi->disconnect();
			sAuto = AUTO_DISCON;
			sAutoTick = 0;
		}
		break;
	}
	case AUTO_DISCON:
		if (!wifi->isConnected() || sAutoTick > 50) {
			autoLog(3, "断开完成（%dms，连接=%d）", sAutoTick * 200, wifi->isConnected() ? 1 : 0);
			autoLog(4, "connect(\"%s\") 下发", kTargetSsid);
			wifi->connect(kTargetSsid, kTargetPwd);
			sAuto = AUTO_CONN;
			sAutoTick = 0;
		}
		break;
	case AUTO_CONN:
		if (wifi->isConnected() && wifi->getIp() != NULL && strcmp(wifi->getIp(), "0.0.0.0") != 0) {
			autoLog(4, "已连上（%dms）：IP=%s", sAutoTick * 200, wifi->getIp());
			autoLog(5, "enableWifi(false) 下发——adb 会断，10s 后自动开回来");
			wifi->enableWifi(false);
			sAuto = AUTO_OFF;
			sAutoTick = 0;
		} else if (sAutoTick > 200) {
			autoLog(4, "40s 未连上（连接=%d 回调 connect=%d error=%d），继续",
					wifi->isConnected() ? 1 : 0, sCbConnect, sCbError);
			autoLog(5, "enableWifi(false) 下发——adb 会断，10s 后自动开回来");
			wifi->enableWifi(false);
			sAuto = AUTO_OFF;
			sAutoTick = 0;
		}
		break;
	case AUTO_OFF:
		if (sAutoTick == 25) {
			autoLog(5, "5s：开关状态=%s", enableStateText(wifi->getEnableStatus()));
		}
		if (sAutoTick > 50) {
			autoLog(6, "enableWifi(true) 下发（恢复）");
			wifi->enableWifi(true);
			sAuto = AUTO_ON;
			sAutoTick = 0;
		}
		break;
	case AUTO_ON:
		if (wifi->getEnableStatus() == E_WIFI_ENABLE_ENABLE && wifi->isConnected()
				&& wifi->getIp() != NULL && strcmp(wifi->getIp(), "0.0.0.0") != 0) {
			autoLog(6, "WiFi 已恢复并回连（%dms）：IP=%s", sAutoTick * 200, wifi->getIp());
			sAuto = AUTO_DONE;
		} else if (sAutoTick > 150) {
			autoLog(6, "30s 未恢复到已连接（开关=%s 连接=%d IP=%s）",
					enableStateText(wifi->getEnableStatus()), wifi->isConnected() ? 1 : 0,
					wifi->getIp() ? wifi->getIp() : "-");
			sAuto = AUTO_DONE;
		}
		break;
	default:
		sAuto = AUTO_DONE;
		break;
	}
}

/* 定时器：推进「等扫描 / 等连接 / 等开关」状态机（不阻塞 UI 线程） */
static bool onUI_Timer(int id) {
	if (id != 0) {
		return true;
	}
	if (sAuto == AUTO_READ || sAuto == AUTO_SCAN || sAuto == AUTO_DISCON
			|| sAuto == AUTO_CONN || sAuto == AUTO_OFF || sAuto == AUTO_ON) {
		autoTick();
		return true;
	}
	WifiManager *wifi = NETMANAGER->getWifiManager();
	if (wifi == NULL) {
		return true;
	}
	if (sWait != E_WAIT_NONE) {
		sWaitTick++;
	}
	if (sWait == E_WAIT_ENABLE) {
		if (wifi->getEnableStatus() == E_WIFI_ENABLE_ENABLE) {
			LOGD("zknet demo: enable 完成（%d tick）\n", sWaitTick);
			sWait = E_WAIT_NONE;
			setStatus("enableWifi(true) 完成：开关=%s（%d ms）\n回调计数 enable=%d",
					enableStateText(wifi->getEnableStatus()), sWaitTick * 200, sCbEnable);
		} else if (sWaitTick > 75) {		// 15s
			sWait = E_WAIT_NONE;
			setStatus("enableWifi(true) 超时 15s：开关=%s（回调 enable=%d）",
					enableStateText(wifi->getEnableStatus()), sCbEnable);
		}
	} else if (sWait == E_WAIT_SCAN) {
		std::vector<WifiInfo> infos;
		wifi->getWifiScanInfosLock(infos);
		if (!infos.empty()) {
			wifi->stopScan();
			char list[1000] = { 0 };
			formatScanList(infos, list, sizeof(list));
			sWait = E_WAIT_NONE;
			setStatus("startScan() → %d ms 拿到结果（回调 scan=%d）\n%s",
					sWaitTick * 200, sCbScan, list);
		} else if (sWaitTick > 40) {		// 8s
			wifi->stopScan();
			sWait = E_WAIT_NONE;
			setStatus("startScan() 8s 内没有结果（回调 scan=%d）\n"
					"可能：模组刚枚举完/开关未开", sCbScan);
		}
	} else if (sWait == E_WAIT_CONNECT) {
		if (wifi->isConnected()) {
			WifiInfo *info = wifi->getConnectionInfo();
			sWait = E_WAIT_NONE;
			setStatus("connect(\"%s\") 成功，%d ms\nIP=%s  信号=%ddBm\n回调 connect=%d",
					kTargetSsid, sWaitTick * 200,
					wifi->getIp() ? wifi->getIp() : "-",
					info ? info->getRssi() : 0, sCbConnect);
		} else if (sWaitTick > 150) {		// 30s
			sWait = E_WAIT_NONE;
			setStatus("connect(\"%s\") 30s 未连上\n回调 connect=%d error=%d\n"
					"（下一步照 WifiTest 的稳妥做法：先扫到目标 SSID 再 connect）",
					kTargetSsid, sCbConnect, sCbError);
		}
	}
	return true;
}

static bool onmainActivityTouchEvent(const MotionEvent &ev) {
	return false;
}

/* ==================== 按钮：WiFi 开关 / 扫描 / 连接 ==================== */

static bool onButtonClick_ButtonWifiOn(ZKButton *pButton) {
	WifiManager *wifi = NETMANAGER->getWifiManager();
	if (wifi == NULL) {
		setStatus("getWifiManager() = NULL");
		return true;
	}
	wifi->enableWifi(true);
	sWait = E_WAIT_ENABLE;
	sWaitTick = 0;
	setStatus("enableWifi(true) 已下发（原开关=%s）\n等回调/轮询…",
			enableStateText(wifi->getEnableStatus()));
	return true;
}

static bool onButtonClick_ButtonWifiOff(ZKButton *pButton) {
	WifiManager *wifi = NETMANAGER->getWifiManager();
	if (wifi == NULL) {
		setStatus("getWifiManager() = NULL");
		return true;
	}
	wifi->disconnect();
	wifi->enableWifi(false);
	sWait = E_WAIT_NONE;
	setStatus("disconnect() + enableWifi(false) 已下发（开关=%s）\n"
			"⚠️ WiFi 关掉后 adb（192.168.x.x:5555）会断，要现场才能点「WiFi 开」救回来",
			enableStateText(wifi->getEnableStatus()));
	return true;
}

static bool onButtonClick_ButtonScan(ZKButton *pButton) {
	WifiManager *wifi = NETMANAGER->getWifiManager();
	if (wifi == NULL) {
		setStatus("getWifiManager() = NULL");
		return true;
	}
	wifi->startScan();
	sWait = E_WAIT_SCAN;
	sWaitTick = 0;
	setStatus("startScan() 已下发，等 handleWifiScanResult / getWifiScanInfosLock…");
	return true;
}

static bool onButtonClick_ButtonConnect(ZKButton *pButton) {
	WifiManager *wifi = NETMANAGER->getWifiManager();
	if (wifi == NULL) {
		setStatus("getWifiManager() = NULL");
		return true;
	}
	wifi->connect(kTargetSsid, kTargetPwd);
	sWait = E_WAIT_CONNECT;
	sWaitTick = 0;
	setStatus("connect(\"%s\", \"******\") 已下发（2 参数重载，加密方式自动判定）\n等连上…",
			kTargetSsid);
	return true;
}

static bool onButtonClick_ButtonDisconnect(ZKButton *pButton) {
	WifiManager *wifi = NETMANAGER->getWifiManager();
	if (wifi == NULL) {
		setStatus("getWifiManager() = NULL");
		return true;
	}
	wifi->disconnect();
	sWait = E_WAIT_NONE;
	setStatus("disconnect() 已下发（连接=%d）", wifi->isConnected() ? 1 : 0);
	return true;
}

/* ==================== 按钮：状态 / 工具 / 其它网络面 ==================== */

static bool onButtonClick_ButtonNetInfo(ZKButton *pButton) {
	WifiManager *wifi = NETMANAGER->getWifiManager();
	if (wifi == NULL) {
		setStatus("getWifiManager() = NULL");
		return true;
	}
	char st[640] = { 0 };
	formatConnection(st, sizeof(st));
	setStatus("WifiManager 读回：\n%s\n自动 IP=%d", st, wifi->isAutoMode() ? 1 : 0);
	return true;
}

static bool onButtonClick_ButtonNetUtils(ZKButton *pButton) {
	char ip[64] = { 0 }, mask[64] = { 0 }, gw[64] = { 0 }, dns1[64] = { 0 }, dns2[64] = { 0 };
	bool ok = NetUtils::getConfigureInfo("wlan0", ip, mask, gw, dns1, dns2);
	setStatus("NetUtils 静态接口（iface=wlan0）：\n"
			"getIp=%s\ngetMacAddr=%s\ngetConfigureInfo(ok=%d)=%s/%s gw=%s dns=%s,%s\n"
			"INVALID_IP_ADDR=%s INVALID_MAC_ADDR=%s",
			NetUtils::getIp("wlan0") ? NetUtils::getIp("wlan0") : "-",
			NetUtils::getMacAddr("wlan0") ? NetUtils::getMacAddr("wlan0") : "-",
			ok ? 1 : 0, ip, mask, gw, dns1, dns2,
			INVALID_IP_ADDR, INVALID_MAC_ADDR);
	return true;
}

static bool onButtonClick_ButtonSoftAp(ZKButton *pButton) {
	SoftApManager *ap = NETMANAGER->getSoftApManager();
	if (ap == NULL) {
		setStatus("getSoftApManager() = NULL");
		return true;
	}
	setStatus("SoftApManager 读回：\n"
			"isEnable=%d state=%d\nssid=%s pwd=%s\nip=%s\n"
			"（本示例只读；setEnable()/setSsidAndPwd() 未在 STA 连通时验证——"
			"RTL8188 同时开 AP+STA 行为待现场确认）",
			ap->isEnable() ? 1 : 0, (int) ap->getSoftApState(),
			ap->getSsid() ? ap->getSsid() : "-", ap->getPwd() ? ap->getPwd() : "-",
			ap->getIp() ? ap->getIp() : "-");
	return true;
}

static bool onButtonClick_ButtonChannel(ZKButton *pButton) {
	ENetChannel ch = NETMANAGER->getConnChannel();
	EthernetManager *eth = NETMANAGER->getEthernetManager();
	LTE4GManager *lte = NETMANAGER->getLTE4GManager();
	setStatus("NetManager 读回：\ngetConnChannel()=%s(%d)\n"
			"Ethernet: isSupported=%d isConnected=%d ip=%s\n"
			"LTE4G: isSupported=%d powerState=%d\n"
			"回调计数：enable=%d connect=%d scan=%d supplicant=%d error=%d",
			channelText(ch), (int) ch,
			eth ? (eth->isSupported() ? 1 : 0) : -1,
			eth ? (eth->isConnected() ? 1 : 0) : -1,
			(eth && eth->getIp()) ? eth->getIp() : "-",
			lte ? (lte->isSupported() ? 1 : 0) : -1,
			lte ? (int) lte->getPowerState() : -1,
			sCbEnable, sCbConnect, sCbScan, sCbSupplicant, sCbError);
	return true;
}

/* ==================== 按钮：自检 AUTO ==================== */
static bool onButtonClick_ButtonAuto(ZKButton *pButton) {
	if (sAuto == AUTO_READ || sAuto == AUTO_SCAN || sAuto == AUTO_DISCON
			|| sAuto == AUTO_CONN || sAuto == AUTO_OFF || sAuto == AUTO_ON) {
		sAuto = AUTO_DONE;
		autoLog(0, "已手动停止自检");
		return true;
	}
	autoStart();
	return true;
}
