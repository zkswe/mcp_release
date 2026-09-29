#pragma once
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#include "uart/ProtocolSender.h"

/*
 * 网络包验证 v2（Z20 86 面板 / 480x480）—— 补齐 v1 未验项
 *   MQTTS(TLS) : mqtt::Client + server="mqtts://..."（paho-mqtt3as + openssl；ssl.verify=false 跳过自签校验）
 *   LWT 遗嘱   : conf.will{topic,message,qos,retained} → 异常断线时由 broker 代发
 *   断线+重连  : enableWifi(false) 90s（> paho keepalive 60s，让遗嘱有机会触发）→ enableWifi(true) → 看是否自动回连
 *   Downloader : http::Downloader::instance().add(Task) 双任务 + 进度/结果回调 + 文件完整性
 *   WebSocket  : http::WebSocket connect/sendFrame/receiveFrame/close（ws://192.168.x.x:8765 本地回显服务）
 *   SoftAp     : zknet SoftApManager::setEnable(true/false) + 状态/ssid/ip
 *   Ethernet   : zknet EthernetManager 读配置 + configure() 原值回写 + setAutoMode
 *   LTE4G      : zknet LTE4GManager 支持性/电源状态/queryRSSI（本板 isSupported=0）
 *
 * 阻塞调用一律在 worker 线程；主线程 200ms 定时器只刷日志。
 */

#include <http/axios.h>
#include <http/downloader.h>
#include <http/web_socket.h>
#include <mqtt/mqtt_client.h>
#include <net/NetManager.h>
#include <net/SoftApManager.h>
#include <net/EthernetManager.h>
#include <net/LTE4GManager.h>
#include <net/WifiManager.h>
#include <base/base.h>
#include <base/exception.h>

#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define LAN_HOST   "192.168.x.x"
#define WS_URL     "ws://192.168.x.x:8766"
#define MQTTS_URL  "mqtts://test.mosquitto.org:8883"
#define MQTT_PLAIN "mqtt://192.168.x.x:1883"
#define TOPIC_DATA "zk/netstack2/108"
#define TOPIC_WILL "zk/netstack2/will108"

/* ---------------- 线程安全日志 ---------------- */
static char sLog[9000];
static volatile int sLogLen = 0, sPrinted = 0, sBusy = 0, sErrCount = 0;
static pthread_mutex_t sLogMx = PTHREAD_MUTEX_INITIALIZER;

static void logLine(const char *fmt, ...) {
	char buf[512] = { 0 };
	va_list ap;
	va_start(ap, fmt);
	vsnprintf(buf, sizeof(buf), fmt, ap);
	va_end(ap);
	pthread_mutex_lock(&sLogMx);
	int n = (int) strlen(sLog);
	if (n + (int) strlen(buf) + 4 < (int) sizeof(sLog)) {
		memcpy(sLog + n, buf, strlen(buf));
		sLog[n + strlen(buf)] = '\n';
		sLog[n + strlen(buf) + 1] = '\0';
	}
	sLogLen = (int) strlen(sLog);
	pthread_mutex_unlock(&sLogMx);
}

static void flushLog() {
	if (sLogLen <= sPrinted) {
		return;
	}
	char snap[9000] = { 0 };
	pthread_mutex_lock(&sLogMx);
	memcpy(snap, sLog, sizeof(snap) - 1);
	pthread_mutex_unlock(&sLogMx);
	char *newpart = snap + sPrinted;
	const char *show = newpart;
	if (strlen(newpart) > 1000) {
		show = newpart + (strlen(newpart) - 1000);
	}
	if (mTextStatusPtr != NULL) {
		mTextStatusPtr->setText(show);
	}
	char line[560] = { 0 };
	int li = 0;
	for (const char *p = newpart;; p++) {
		if (*p == '\n' || *p == '\0') {
			if (li > 0) {
				line[li] = '\0';
				LOGD("netstack2 demo: %s\n", line);
				li = 0;
			}
			if (*p == '\0') break;
		} else if (li < (int) sizeof(line) - 1) {
			line[li++] = *p;
		}
	}
	sPrinted = sLogLen;
}

static void waitMs(int ms) {
	while (ms > 0) {
		int step = ms > 200 ? 200 : ms;
		usleep(step * 1000);
		ms -= step;
	}
}

/* ---------------- MQTT 客户端（明文 + TLS 两个实例） ---------------- */
static mqtt::Client *sPlain = NULL;      /* 本地 EMQX，用于 LWT / 重连 */
static mqtt::Client *sTls = NULL;        /* 公网 mosquitto TLS */
static volatile int sPlainConn = 0, sTlsConn = 0;
static volatile int sPlainMsg = 0, sTlsMsg = 0;
static volatile int sPlainConnectTimes = 0;   /* on_connected 触发次数（看重连有没有成功） */
static char sPlainLast[256] = { 0 }, sTlsLast[256] = { 0 };
static pthread_mutex_t sMqttMx = PTHREAD_MUTEX_INITIALIZER;

static void plainOnConnected(const std::string &cause) {
	sPlainConn = 1;
	sPlainConnectTimes++;
	logLine("[LWT] on_connected（第 %d 次）cause=%s", sPlainConnectTimes, cause.c_str());
}
static void plainOnDisconnected(const std::string &cause) {
	sPlainConn = 0;
	logLine("[LWT] on_disconnected cause=%s", cause.c_str());
}
static void plainOnMessage(const std::string &topic, const std::string &payload) {
	pthread_mutex_lock(&sMqttMx);
	sPlainMsg++;
	size_t n = payload.size();
	if (n > sizeof(sPlainLast) - 1) n = sizeof(sPlainLast) - 1;
	memcpy(sPlainLast, payload.data(), n);
	sPlainLast[n] = '\0';
	pthread_mutex_unlock(&sMqttMx);
	logLine("[LWT] on_message topic=%s len=%d payload=%s", topic.c_str(), (int) payload.size(), payload.c_str());
}

static void tlsOnConnected(const std::string &cause) {
	sTlsConn = 1;
	logLine("[MQTTS] on_connected cause=%s", cause.c_str());
}
static void tlsOnDisconnected(const std::string &cause) {
	sTlsConn = 0;
	logLine("[MQTTS] on_disconnected cause=%s", cause.c_str());
}
static void tlsOnMessage(const std::string &topic, const std::string &payload) {
	pthread_mutex_lock(&sMqttMx);
	sTlsMsg++;
	size_t n = payload.size();
	if (n > sizeof(sTlsLast) - 1) n = sizeof(sTlsLast) - 1;
	memcpy(sTlsLast, payload.data(), n);
	sTlsLast[n] = '\0';
	pthread_mutex_unlock(&sMqttMx);
	logLine("[MQTTS] on_message topic=%s len=%d payload=%s", topic.c_str(), (int) payload.size(), payload.c_str());
}

static bool ensurePlain() {
	if (sPlain != NULL) {
		return sPlainConn != 0;
	}
	mqtt::Client::Configuration conf;
	conf.client_id = "zk-ns2-108";
	conf.server = MQTT_PLAIN;
	conf.username = "admin";
	conf.password = "zkswe1024";
	conf.will.topic = TOPIC_WILL;
	conf.will.message = "{\"dev\":\"108\",\"msg\":\"will: offline\"}";
	conf.will.qos = mqtt::QOS_AT_LEAST_ONCE;
	conf.will.retained = false;
	conf.on_connected = plainOnConnected;
	conf.on_disconnected = plainOnDisconnected;
	logLine("[LWT] new Client(%s) will_topic=%s payload=%s", MQTT_PLAIN, TOPIC_WILL, conf.will.message.c_str());
	sPlain = new mqtt::Client(conf);
	for (int i = 0; i < 75 && !sPlainConn; i++) {
		waitMs(200);
	}
	logLine("[LWT] 连接结果 connected=%d isConnected=%d", sPlainConn,
			sPlain ? (sPlain->isConnected() ? 1 : 0) : -1);
	return sPlainConn != 0;
}

/* ---------------- 各任务 ---------------- */
static void jobMqtts() {
	if (sTls == NULL) {
		mqtt::Client::Configuration conf;
		conf.client_id = "zk-ns2-108-tls";
		conf.server = MQTTS_URL;
		conf.ssl.verify = false;                 /* 公网 broker 自签/不受信 CA → 跳过校验只为验通路 */
		conf.ssl.enable_server_cert_auth = false;
		conf.on_connected = tlsOnConnected;
		conf.on_disconnected = tlsOnDisconnected;
		logLine("[MQTTS] new Client(%s) ssl.verify=false", MQTTS_URL);
		sTls = new mqtt::Client(conf);
	}
	for (int i = 0; i < 100 && !sTlsConn; i++) {  /* 等 20s（公网 TLS 慢） */
		waitMs(200);
	}
	logLine("[MQTTS] 连接结果 connected=%d isConnected=%d", sTlsConn,
			sTls ? (sTls->isConnected() ? 1 : 0) : -1);
	if (!sTlsConn) {
		sErrCount++;
		return;
	}
	pthread_mutex_lock(&sMqttMx);
	sTlsMsg = 0;
	sTlsLast[0] = '\0';
	pthread_mutex_unlock(&sMqttMx);
	bool sok = sTls->subscribe(TOPIC_DATA, mqtt::QOS_AT_LEAST_ONCE, tlsOnMessage);
	logLine("[MQTTS] subscribe(%s qos1) -> %s", TOPIC_DATA, sok ? "OK" : "FAIL");
	char payload[128] = { 0 };
	snprintf(payload, sizeof(payload), "{\"dev\":\"108\",\"via\":\"mqtts\",\"ts\":%ld}", (long) time(NULL));
	bool pok = sTls->publish(TOPIC_DATA, std::string(payload), mqtt::QOS_AT_LEAST_ONCE);
	logLine("[MQTTS] publish qos1 -> %s payload=%s", pok ? "OK" : "FAIL", payload);
	for (int i = 0; i < 30 && sTlsMsg == 0; i++) {
		waitMs(200);
	}
	pthread_mutex_lock(&sMqttMx);
	int cnt = sTlsMsg;
	char last[256] = { 0 };
	memcpy(last, sTlsLast, sizeof(last) - 1);
	pthread_mutex_unlock(&sMqttMx);
	logLine("[MQTTS] 收到 %d 条 echo=%s", cnt, cnt ? last : "(无)");
	if (cnt == 0 || !sok || !pok) {
		sErrCount++;
	}
}

static void jobLwt() {
	logLine("[LWT] 注册遗嘱 topic=%s payload={\"dev\":\"108\",\"msg\":\"will: offline\"}", TOPIC_WILL);
	if (!ensurePlain()) {
		sErrCount++;
		logLine("[LWT] 连不上 broker，遗嘱未注册成功");
		return;
	}
	bool sok = sPlain->subscribe(TOPIC_DATA, mqtt::QOS_AT_LEAST_ONCE, plainOnMessage);
	logLine("[LWT] subscribe(%s) -> %s（订阅自己的数据主题做存活对照）", TOPIC_DATA, sok ? "OK" : "FAIL");
	bool pok = sPlain->publish(TOPIC_DATA, std::string("{\"dev\":\"108\",\"msg\":\"alive\"}"),
			mqtt::QOS_AT_LEAST_ONCE);
	logLine("[LWT] publish alive -> %s", pok ? "OK" : "FAIL");
	waitMs(1500);
	logLine("[LWT] 遗嘱已就绪：接下来由「断线+重连」按钮制造异常断线，看 broker 是否代发遗嘱");
	if (!sok || !pok) {
		sErrCount++;
	}
}

static void jobReconnect() {
	logLine("[RECON] 目标：制造异常断线（关 WiFi 90s > paho keepalive 60s）→ 看 ① broker 是否代发遗嘱 ② 开回 WiFi 后是否自动回连");
	if (!ensurePlain()) {
		sErrCount++;
		logLine("[RECON] MQTT 未连上，先做连接");
		return;
	}
	if (!sPlain->subscribe(TOPIC_DATA, mqtt::QOS_AT_LEAST_ONCE, plainOnMessage)) {
		logLine("[RECON] subscribe 失败（继续）");
	}
	WifiManager *wifi = NETMANAGER->getWifiManager();
	if (wifi == NULL) {
		sErrCount++;
		logLine("[RECON] getWifiManager() = NULL");
		return;
	}
	int before = sPlainConnectTimes;
	logLine("[RECON] enableWifi(false) 下发（adb 会断 90s）");
	wifi->enableWifi(false);
	logLine("[RECON] WiFi 关，等 90s 让 keepalive 超时…");
	waitMs(90000);
	logLine("[RECON] enableWifi(true) 下发");
	wifi->enableWifi(true);
	int waited = 0;
	while (waited < 60000 && sPlainConn == 0) {
		waitMs(500);
		waited += 500;
	}
	logLine("[RECON] WiFi 恢复后：wifi连接=%d mqtt connected=%d on_connected 次数 %d->%d（回连耗时≈%dms）",
			wifi->isConnected() ? 1 : 0, sPlainConn, before, sPlainConnectTimes, waited);
	if (sPlainConn == 0) {
		sErrCount++;
	}
	bool uok = sPlain->unsubscribe(TOPIC_DATA);
	logLine("[RECON] unsubscribe -> %s", uok ? "OK" : "FAIL");
}

static void downloadResult(const http::Downloader::Task &task, bool success) {
	struct stat st;
	long long sz = 0;
	if (stat(task.target.c_str(), &st) == 0) {
		sz = (long long) st.st_size;
	}
	logLine("[DL] 结果 %s -> %s，落盘 %lld B", task.source.c_str(), success ? "成功" : "失败", sz);
	if (!success) {
		sErrCount++;
	}
}

static void jobDownload() {
	logLine("[DL] http::Downloader 双任务（含进度回调 + 结果回调）");
	static int done = 0;
	done = 0;
	http::Downloader &dl = http::Downloader::instance();
	{
		http::Downloader::Task t;
		t.source = "http://" LAN_HOST ":8000/big?kb=300";
		t.target = "/mnt/sdnand/ns2_big.bin";
		t.retry_max = 3;
		t.low_speed_limit = http::LowSpeedLimit(512, 10);
		t.progress = [](const http::Downloader::Task &task, int64_t d, int64_t total) -> void {
			logLine("[DL] 进度 %s %lld/%lld", task.target.c_str(), (long long) d, (long long) total);
		};
		t.result = [](const http::Downloader::Task &task, bool ok) -> void {
			downloadResult(task, ok);
			done++;
		};
		dl.add(t);
	}
	{
		http::Downloader::Task t;
		t.source = "http://" LAN_HOST ":8000/json";
		t.target = "/mnt/sdnand/ns2_json.json";
		t.retry_max = 2;
		t.progress = NULL;
		t.result = [](const http::Downloader::Task &task, bool ok) -> void {
			downloadResult(task, ok);
			done++;
		};
		dl.add(t);
	}
	int waited = 0;
	while (waited < 90000 && done < 2) {
		waitMs(500);
		waited += 500;
	}
	logLine("[DL] 双任务结束：完成 %d/2，用时≈%dms（剩余队列=%d）", done, waited, dl.size());
	if (done < 2) {
		sErrCount++;
	}
}

static void jobWebSocket() {
	try {
		http::WebSocket ws;
		http::AxiosRequestConfig cfg;
		cfg.setConnectTimeout(5000);
		cfg.setTimeout(15000);
		logLine("[WS] connect(%s)", WS_URL);
		ws.connect(WS_URL, cfg);
		const char *msg = "hello-ws-from-108";
		int sent = ws.sendFrame(msg, (int) strlen(msg));
		logLine("[WS] sendFrame %d B: %s", sent, msg);
		char buf[512] = { 0 };
		int n = ws.receiveFrame(buf, sizeof(buf) - 1, 8000);
		if (n > 0) {
			buf[n] = '\0';
		}
		logLine("[WS] receiveFrame %d B: %s", n, n > 0 ? buf : "(空)");
		ws.close();
		logLine("[WS] close() 完成");
		if (n <= 0) {
			sErrCount++;
		}
	} catch (base::Exception &e) {
		sErrCount++;
		logLine("[WS] 异常: %s", e.what() ? e.what() : "?");
	}
}

static const char* apStateText(ESoftApState st) {
	switch (st) {
	case E_SOFTAP_DISABLED: return "DISABLED";
	case E_SOFTAP_ENABLING: return "ENABLING";
	case E_SOFTAP_ENABLED: return "ENABLED";
	case E_SOFTAP_DISABLING: return "DISABLING";
	case E_SOFTAP_ENABLE_ERROR: return "ERROR";
	default: return "?";
	}
}

static void jobSoftAp() {
	SoftApManager *ap = NETMANAGER->getSoftApManager();
	if (ap == NULL) {
		sErrCount++;
		logLine("[AP] getSoftApManager() = NULL");
		return;
	}
	logLine("[AP] 初始：isEnable=%d state=%s ssid=%s ip=%s", ap->isEnable() ? 1 : 0,
			apStateText(ap->getSoftApState()), ap->getSsid() ? ap->getSsid() : "-",
			ap->getIp() ? ap->getIp() : "-");
	logLine("[AP] setEnable(true) 下发（⚠️ 单射频可能与 STA 抢占，测试里 15s 后自动关）");
	ap->setEnable(true);
	int waited = 0;
	while (waited < 15000 && !ap->isEnable()) {
		waitMs(500);
		waited += 500;
	}
	logLine("[AP] 开热点：isEnable=%d state=%s ssid=%s pwd=%s ip=%s（耗时≈%dms）",
			ap->isEnable() ? 1 : 0, apStateText(ap->getSoftApState()),
			ap->getSsid() ? ap->getSsid() : "-", ap->getPwd() ? ap->getPwd() : "-",
			ap->getIp() ? ap->getIp() : "-", waited);
	bool opened = ap->isEnable();
	waitMs(2000);
	logLine("[AP] setEnable(false) 下发（恢复）");
	ap->setEnable(false);
	waited = 0;
	while (waited < 15000 && ap->isEnable()) {
		waitMs(500);
		waited += 500;
	}
	logLine("[AP] 关热点：isEnable=%d state=%s（耗时≈%dms）wifi 连接=%d",
			ap->isEnable() ? 1 : 0, apStateText(ap->getSoftApState()), waited,
			NETMANAGER->getWifiManager() ? (NETMANAGER->getWifiManager()->isConnected() ? 1 : 0) : -1);
	if (!opened) {
		sErrCount++;
	}
}

static void jobEthernet() {
	EthernetManager *eth = NETMANAGER->getEthernetManager();
	if (eth == NULL) {
		sErrCount++;
		logLine("[ETH] getEthernetManager() = NULL");
		return;
	}
	char ip[64] = { 0 }, mask[64] = { 0 }, gw[64] = { 0 }, d1[64] = { 0 }, d2[64] = { 0 };
	char sip[64] = { 0 }, smask[64] = { 0 }, sgw[64] = { 0 }, sd1[64] = { 0 }, sd2[64] = { 0 };
	bool ok = eth->getConfigureInfo(ip, mask, gw, d1, d2);
	bool sok = eth->getStaticConfigureInfo(sip, smask, sgw, sd1, sd2);
	logLine("[ETH] supported=%d connected=%d ip=%s mac=%s autoMode=%d",
			eth->isSupported() ? 1 : 0, eth->isConnected() ? 1 : 0,
			eth->getIp() ? eth->getIp() : "-", eth->getMacAddr() ? eth->getMacAddr() : "-",
			eth->isAutoMode() ? 1 : 0);
	logLine("[ETH] getConfigureInfo(ok=%d) ip=%s mask=%s gw=%s dns=%s,%s", ok ? 1 : 0, ip, mask, gw, d1, d2);
	logLine("[ETH] getStaticConfigureInfo(ok=%d) ip=%s mask=%s gw=%s dns=%s,%s", sok ? 1 : 0, sip, smask, sgw, sd1, sd2);
	/* 原值回写：只为验证 configure() 调用链，不改变实际网络（值就是刚读到的） */
	bool wok = eth->configure(ip, mask, gw, d1, d2);
	logLine("[ETH] configure() 原值回写 -> %s（面板没插网线，写的是刚读到的值）", wok ? "OK" : "FAIL");
	bool aok = eth->setAutoMode(true);
	logLine("[ETH] setAutoMode(true) -> %s isAutoMode=%d", aok ? "OK" : "FAIL", eth->isAutoMode() ? 1 : 0);
	if (!wok || !aok) {
		sErrCount++;
	}
}

static const char* lteStateText(ELTE4GPowerState st) {
	switch (st) {
	case E_LTE4G_POWER_ON: return "POWER_ON";
	case E_LTE4G_POWER_ONING: return "POWER_ONING";
	case E_LTE4G_POWER_OFF: return "POWER_OFF";
	case E_LTE4G_POWER_OFFING: return "POWER_OFFING";
	default: return "UNKNOWN";
	}
}

static void jobLte() {
	LTE4GManager *lte = NETMANAGER->getLTE4GManager();
	if (lte == NULL) {
		sErrCount++;
		logLine("[4G] getLTE4GManager() = NULL");
		return;
	}
	logLine("[4G] isSupported=%d powerState=%s ip=%s imei=%s", lte->isSupported() ? 1 : 0,
			lteStateText(lte->getPowerState()), lte->getIp() ? lte->getIp() : "-",
			lte->getIMEI() ? lte->getIMEI() : "-");
	int rssi = lte->queryRSSI();
	logLine("[4G] queryRSSI() = %d", rssi);
	if (lte->isSupported()) {
		logLine("[4G] setPower(true) 下发");
		lte->setPower(true);
		waitMs(3000);
		logLine("[4G] setPower(true) 后 powerState=%s", lteStateText(lte->getPowerState()));
		lte->setPower(false);
		waitMs(3000);
		logLine("[4G] setPower(false) 后 powerState=%s", lteStateText(lte->getPowerState()));
	} else {
		logLine("[4G] 本板 isSupported=0 → 动作类 API（setPower）无硬件可验，跳过（结论：Z20 86 面板无 4G 模块）");
	}
}

/* ---------------- worker ---------------- */
enum {
	JOB_NONE = 0, JOB_MQTTS, JOB_LWT, JOB_RECON, JOB_DL, JOB_WS, JOB_AP, JOB_ETH, JOB_LTE, JOB_AUTO2
};

static void *workerProc(void *arg) {
	int job = (int) (long) arg;
	if (job == JOB_MQTTS) {
		logLine("== MQTTS（TLS） ==");
		jobMqtts();
	} else if (job == JOB_LWT) {
		logLine("== MQTT 遗嘱 LWT ==");
		jobLwt();
	} else if (job == JOB_RECON) {
		logLine("== MQTT 异常断线 + 自动重连 ==");
		jobReconnect();
	} else if (job == JOB_DL) {
		logLine("== http::Downloader 多任务 ==");
		jobDownload();
	} else if (job == JOB_WS) {
		logLine("== http::WebSocket ==");
		jobWebSocket();
	} else if (job == JOB_AP) {
		logLine("== SoftAp setEnable ==");
		jobSoftAp();
	} else if (job == JOB_ETH) {
		logLine("== Ethernet 配置 ==");
		jobEthernet();
	} else if (job == JOB_LTE) {
		logLine("== LTE4G 状态 ==");
		jobLte();
	} else if (job == JOB_AUTO2) {
		logLine("########## 自检 AUTO2 开始 ##########");
		logLine("== 1/7 MQTTS(TLS) ==");
		jobMqtts();
		logLine("== 2/7 MQTT LWT 遗嘱 ==");
		jobLwt();
		logLine("== 3/7 Downloader 双任务 ==");
		jobDownload();
		logLine("== 4/7 WebSocket 回显 ==");
		jobWebSocket();
		logLine("== 5/7 SoftAp 开关 ==");
		jobSoftAp();
		logLine("== 6/7 Ethernet 配置 ==");
		jobEthernet();
		logLine("== 7/7 LTE4G 状态 ==");
		jobLte();
		logLine("########## 自检 AUTO2 结束：错误数=%d ##########", sErrCount);
		logLine("（「断线+重连」要单独点：它会关 WiFi 90s，adb 会断，我单独跑）");
	}
	sBusy = 0;
	return NULL;
}

static void startJob(int job) {
	if (sBusy) {
		logLine("(上一个任务还在跑，忽略)");
		return;
	}
	sBusy = 1;
	pthread_t tid;
	if (pthread_create(&tid, NULL, workerProc, (void *) (long) job) != 0) {
		sBusy = 0;
		logLine("pthread_create 失败");
		return;
	}
	pthread_detach(tid);
}

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = { { 0, 200 } };

static void onUI_init() {
  #ifdef FUN_BUILD
  INIT_UI_TIMERS
  #endif // FUN_BUILD
	logLine("就绪：网络包验证 v2（MQTTS / LWT / 下载 / WS / 热点 / 以太网 / 4G）");
	logLine("MQTTS 目标 %s；明文 MQTT %s；WS %s", MQTTS_URL, MQTT_PLAIN, WS_URL);
	if (mTextStatusPtr != NULL) {
		mTextStatusPtr->setText(sLog);
	}
	sPrinted = sLogLen;
}

static void onUI_intent(const Intent *intentPtr) { }
static void onUI_show() { }
static void onUI_hide() { }
static void onUI_quit() { }
static void onProtocolDataUpdate(const SProtocolData &data) { }

static bool onUI_Timer(int id) {
	if (id == 0) {
		flushLog();
	}
	return true;
}

static bool onmainActivityTouchEvent(const MotionEvent &ev) {
	return false;
}

/* ---------------- 按钮 ---------------- */
static bool onButtonClick_ButtonMqtts(ZKButton *pButton) { startJob(JOB_MQTTS); return true; }
static bool onButtonClick_ButtonLwt(ZKButton *pButton) { startJob(JOB_LWT); return true; }
static bool onButtonClick_ButtonReconnect(ZKButton *pButton) { startJob(JOB_RECON); return true; }
static bool onButtonClick_ButtonDownload(ZKButton *pButton) { startJob(JOB_DL); return true; }
static bool onButtonClick_ButtonWebSocket(ZKButton *pButton) { startJob(JOB_WS); return true; }
static bool onButtonClick_ButtonSoftAp(ZKButton *pButton) { startJob(JOB_AP); return true; }
static bool onButtonClick_ButtonEth(ZKButton *pButton) { startJob(JOB_ETH); return true; }
static bool onButtonClick_ButtonLte(ZKButton *pButton) { startJob(JOB_LTE); return true; }
static bool onButtonClick_ButtonAuto2(ZKButton *pButton) {
	if (sBusy) {
		logLine("AUTO2 正在跑，忽略");
	} else {
		sErrCount = 0;
		startJob(JOB_AUTO2);
	}
	return true;
}
