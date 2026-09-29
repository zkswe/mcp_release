#pragma once
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#include "uart/ProtocolSender.h"

/*
 * 网络包验证 —— Z21（SSD21X / 1024x600）版本，与 Z20 版同一套写法
 *   curl-cxx : http::Axios（HTTP GET/POST、HTTPS）+ http::Downloader（双任务+进度）+ http::WebSocket（回显）
 *   ntp      : ntp::syncTime
 *   zknet    : SoftApManager::setEnable / EthernetManager 读配置 + configure 原值回写
 *   ⚠️ mqtt-cxx / paho-mqtt3as 本地 registry 只有 Z20 版 → 本版不验 MQTT
 *
 * 阻塞调用一律 worker 线程；主线程 200ms 定时器刷 textview + logcat（单行）。
 */

#include <http/axios.h>
#include <http/downloader.h>
#include <http/web_socket.h>
#include <ntp/ntp.h>
#include <net/NetManager.h>
#include <net/SoftApManager.h>
#include <net/EthernetManager.h>
#include <net/WifiManager.h>
#include <net/NetUtils.h>
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

#define LAN_BASE   "http://192.168.x.x:8000"
#define HTTPS_URL  "https://www.baidu.com"
#define WS_URL     "ws://192.168.x.x:8766"

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
	if (strlen(newpart) > 1200) {
		show = newpart + (strlen(newpart) - 1200);
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
				LOGD("netz21 demo: %s\n", line);
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

/* ---------------- 任务 ---------------- */
static void jobHttpGet() {
	try {
		http::Axios ios;
		http::AxiosRequestConfig cfg;
		cfg.setConnectTimeout(3000);
		cfg.setTimeout(10000);
		http::AxiosResponse r = ios.GET(std::string(LAN_BASE) + "/hello.txt", cfg);
		logLine("[HTTP] GET /hello.txt -> %d %s | %d bytes | ctype=%s",
				r.status, r.status_text.c_str(), (int) r.data.size(), r.getContentType().c_str());
		std::string d = r.data;
		if (d.size() > 3) d.erase(d.size() - 1);
		logLine("[HTTP]   body: %s", d.c_str());
		if (r.status != 200) sErrCount++;
	} catch (base::Exception &e) {
		sErrCount++;
		logLine("[HTTP] GET 异常: %s", e.what() ? e.what() : "?");
	}
}

static void jobHttpPost() {
	try {
		http::Axios ios;
		http::AxiosRequestConfig cfg;
		cfg.setConnectTimeout(3000);
		cfg.setTimeout(10000);
		http::Headers h;
		h["Content-Type"] = "application/json";
		cfg.setHeaders(h);
		std::string body = "{\"from\":\"z21-191\",\"msg\":\"curl-cxx POST works\"}";
		http::AxiosResponse r = ios.POST(std::string(LAN_BASE) + "/echo", body, cfg);
		logLine("[HTTP] POST /echo -> %d %s | %d bytes", r.status, r.status_text.c_str(), (int) r.data.size());
		logLine("[HTTP]   echo: %s", r.data.c_str());
		if (r.status != 200) sErrCount++;
	} catch (base::Exception &e) {
		sErrCount++;
		logLine("[HTTP] POST 异常: %s", e.what() ? e.what() : "?");
	}
}

static void jobHttpsGet() {
	try {
		http::Axios ios;
		http::AxiosRequestConfig cfg;
		cfg.setConnectTimeout(5000);
		cfg.setTimeout(15000);
		http::AxiosResponse r = ios.GET(HTTPS_URL, cfg);
		logLine("[HTTPS] GET %s -> %d %s | %d bytes（证书校验 mbedtls）",
				HTTPS_URL, r.status, r.status_text.c_str(), (int) r.data.size());
		if (r.status != 200) sErrCount++;
	} catch (base::Exception &e) {
		sErrCount++;
		logLine("[HTTPS] GET 异常: %s", e.what() ? e.what() : "?");
	}
}

static void jobNtp() {
	setenv("TZ", "UTC-8", 1);
	tzset();
	time_t before = time(NULL);
	std::vector<std::string> servers = ntp::defaultServerList();
	bool ok = ntp::syncTime(servers, 3000);
	time_t after = time(NULL);
	char b1[64] = { 0 }, b2[64] = { 0 };
	struct tm tm1, tm2;
	localtime_r(&before, &tm1);
	localtime_r(&after, &tm2);
	strftime(b1, sizeof(b1), "%Y-%m-%d %H:%M:%S", &tm1);
	strftime(b2, sizeof(b2), "%Y-%m-%d %H:%M:%S", &tm2);
	logLine("[NTP] syncTime(%d 个服务器) -> %s | 前=%s 后=%s（TZ=UTC-8）",
			(int) servers.size(), ok ? "成功" : "失败", b1, b2);
	if (!ok) sErrCount++;
}

static volatile int sDlDone = 0;
static void dlResult(const http::Downloader::Task &task, bool ok) {
	struct stat st;
	long long sz = 0;
	if (stat(task.target.c_str(), &st) == 0) sz = (long long) st.st_size;
	logLine("[DL] 结果 %s -> %s，落盘 %lld B", task.source.c_str(), ok ? "成功" : "失败", sz);
	sDlDone++;
	if (!ok) sErrCount++;
}

static void jobDownload() {
	logLine("[DL] http::Downloader 双任务（进度 + 结果回调）");
	sDlDone = 0;
	http::Downloader &dl = http::Downloader::instance();
	{
		http::Downloader::Task t;
		t.source = "http://192.168.x.x:8000/big?kb=300";
		t.target = "/data/z21_big.bin";
		t.retry_max = 3;
		t.low_speed_limit = http::LowSpeedLimit(512, 10);
		t.progress = [](const http::Downloader::Task &task, int64_t d, int64_t total) -> void {
			if (d == total || d % 100000 < 16000) {
				logLine("[DL] 进度 %s %lld/%lld", task.target.c_str(), (long long) d, (long long) total);
			}
		};
		t.result = dlResult;
		dl.add(t);
	}
	{
		http::Downloader::Task t;
		t.source = "http://192.168.x.x:8000/json";
		t.target = "/data/z21_json.json";
		t.retry_max = 2;
		t.result = dlResult;
		dl.add(t);
	}
	int waited = 0;
	while (waited < 90000 && sDlDone < 2) {
		waitMs(500);
		waited += 500;
	}
	logLine("[DL] 双任务结束：完成 %d/2，用时≈%dms（剩余队列=%d）", sDlDone, waited, dl.size());
	if (sDlDone < 2) sErrCount++;
}

static void jobWebSocket() {
	try {
		http::WebSocket ws;
		http::AxiosRequestConfig cfg;
		cfg.setConnectTimeout(5000);
		cfg.setTimeout(15000);
		logLine("[WS] connect(%s)", WS_URL);
		ws.connect(WS_URL, cfg);
		const char *msg = "hello-ws-from-z21";
		int sent = ws.sendFrame(msg, (int) strlen(msg));
		logLine("[WS] sendFrame %d B: %s", sent, msg);
		char buf[512] = { 0 };
		int n = ws.receiveFrame(buf, sizeof(buf) - 1, 8000);
		if (n > 0) buf[n] = '\0';
		logLine("[WS] receiveFrame %d B: %s", n, n > 0 ? buf : "(空)");
		ws.close();
		logLine("[WS] close() 完成");
		if (n <= 0) sErrCount++;
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
	logLine("[AP] 初始 isEnable=%d state=%s ssid=%s ip=%s", ap->isEnable() ? 1 : 0,
			apStateText(ap->getSoftApState()), ap->getSsid() ? ap->getSsid() : "-",
			ap->getIp() ? ap->getIp() : "-");
	ap->setEnable(true);
	int waited = 0;
	while (waited < 15000 && !ap->isEnable()) {
		waitMs(500);
		waited += 500;
	}
	bool opened = ap->isEnable();
	logLine("[AP] 开热点 isEnable=%d state=%s ssid=%s pwd=%s ip=%s（≈%dms）",
			opened ? 1 : 0, apStateText(ap->getSoftApState()),
			ap->getSsid() ? ap->getSsid() : "-", ap->getPwd() ? ap->getPwd() : "-",
			ap->getIp() ? ap->getIp() : "-", waited);
	waitMs(2000);
	ap->setEnable(false);
	waited = 0;
	while (waited < 15000 && ap->isEnable()) {
		waitMs(500);
		waited += 500;
	}
	logLine("[AP] 关热点 isEnable=%d state=%s（≈%dms）wifi连接=%d", ap->isEnable() ? 1 : 0,
			apStateText(ap->getSoftApState()), waited,
			NETMANAGER->getWifiManager() ? (NETMANAGER->getWifiManager()->isConnected() ? 1 : 0) : -1);
	if (!opened) sErrCount++;
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
	logLine("[ETH] NetUtils: iface=%s ip=%s mac=%s", "eth0",
			NetUtils::getIp("eth0") ? NetUtils::getIp("eth0") : "-",
			NetUtils::getMacAddr("eth0") ? NetUtils::getMacAddr("eth0") : "-");
	bool aok = eth->setAutoMode(true);
	logLine("[ETH] setAutoMode(true) -> %s isAutoMode=%d", aok ? "OK" : "FAIL", eth->isAutoMode() ? 1 : 0);
	if (!aok) sErrCount++;
}

/* ---------------- worker ---------------- */
enum { JOB_NONE = 0, JOB_HTTP_GET, JOB_HTTP_POST, JOB_HTTPS, JOB_NTP, JOB_DL, JOB_WS, JOB_AP, JOB_ETH, JOB_AUTO };

static void *workerProc(void *arg) {
	int job = (int) (long) arg;
	if (job == JOB_HTTP_GET) {
		logLine("== HTTP GET（curl-cxx） ==");
		jobHttpGet();
	} else if (job == JOB_HTTP_POST) {
		logLine("== HTTP POST ==");
		jobHttpPost();
	} else if (job == JOB_HTTPS) {
		logLine("== HTTPS GET ==");
		jobHttpsGet();
	} else if (job == JOB_NTP) {
		logLine("== NTP 校时 ==");
		jobNtp();
	} else if (job == JOB_DL) {
		logLine("== Downloader 双任务 ==");
		jobDownload();
	} else if (job == JOB_WS) {
		logLine("== WebSocket 回显 ==");
		jobWebSocket();
	} else if (job == JOB_AP) {
		logLine("== SoftAp 开关 ==");
		jobSoftAp();
	} else if (job == JOB_ETH) {
		logLine("== Ethernet 配置 ==");
		jobEthernet();
	} else if (job == JOB_AUTO) {
		logLine("########## 自检 AUTO（Z21）开始：不验 MQTT（Z21 无 mqtt-cxx/paho 包） ##########");
		logLine("== 1/7 HTTP GET ==");
		jobHttpGet();
		logLine("== 2/7 HTTP POST ==");
		jobHttpPost();
		logLine("== 3/7 HTTPS GET ==");
		jobHttpsGet();
		logLine("== 4/7 NTP 校时 ==");
		jobNtp();
		logLine("== 5/7 Downloader 双任务 ==");
		jobDownload();
		logLine("== 6/7 WebSocket 回显 ==");
		jobWebSocket();
		logLine("== 7/7 SoftAp + Ethernet ==");
		jobSoftAp();
		jobEthernet();
		logLine("########## 自检 AUTO（Z21）结束：错误数=%d ##########", sErrCount);
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
	logLine("就绪：网络包验证（Z21 1024x600）");
	logLine("HTTP %s / WS %s / HTTPS %s", LAN_BASE, WS_URL, HTTPS_URL);
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
	if (id == 0) flushLog();
	return true;
}

static bool onmainActivityTouchEvent(const MotionEvent &ev) {
	return false;
}

static bool onButtonClick_ButtonHttpGet(ZKButton *p) { startJob(JOB_HTTP_GET); return true; }
static bool onButtonClick_ButtonHttpPost(ZKButton *p) { startJob(JOB_HTTP_POST); return true; }
static bool onButtonClick_ButtonHttpsGet(ZKButton *p) { startJob(JOB_HTTPS); return true; }
static bool onButtonClick_ButtonNtp(ZKButton *p) { startJob(JOB_NTP); return true; }
static bool onButtonClick_ButtonDownload(ZKButton *p) { startJob(JOB_DL); return true; }
static bool onButtonClick_ButtonWebSocket(ZKButton *p) { startJob(JOB_WS); return true; }
static bool onButtonClick_ButtonSoftAp(ZKButton *p) { startJob(JOB_AP); return true; }
static bool onButtonClick_ButtonEth(ZKButton *p) { startJob(JOB_ETH); return true; }
static bool onButtonClick_ButtonAuto(ZKButton *p) {
	if (sBusy) {
		logLine("AUTO 正在跑，忽略");
	} else {
		sErrCount = 0;
		startJob(JOB_AUTO);
	}
	return true;
}
