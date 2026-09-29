#pragma once
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#include "uart/ProtocolSender.h"

/*
 * 网络包验证示例（Z20 86 面板 / 480x480）
 *   curl-cxx : http::Axios（GET/POST/DELETE/PUT/PATCH/HEAD/OPTIONS request）+ http::Downloader + http::FormData
 *   ntp      : ntp::startSyncTime / ntp::syncTime / ntp::getTime / ntp::defaultServerList
 *   mqtt-cxx : mqtt::Client（publish / subscribe / isConnected + on_connected / on_disconnected）
 *
 * 关键做法：**所有阻塞调用都丢到 worker 线程**，主线程只负责「把日志刷到 textview + logcat」，
 *          避免网络卡住 UI（面板上表现为点不动/白屏）。
 * 目标：HTTP 打本机 LAN 测试服务 192.168.x.x:8000；HTTPS 打百度；MQTT 打 WSL 里的 EMQX 192.168.x.x:1883。
 */

#include <http/axios.h>
#include <http/downloader.h>
#include <ntp/ntp.h>
#include <mqtt/mqtt_client.h>
#include <base/base.h>
#include <base/exception.h>

#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define LAN_BASE   "http://192.168.x.x:8000"
#define HTTPS_URL  "https://www.baidu.com"
#define MQTT_URL   "mqtt://192.168.x.x:1883"
#define MQTT_TOPIC "zk/netstack/108"

/* ---------------- 线程安全日志（worker 写，UI 线程刷） ---------------- */
static char sLog[7000];
static volatile int sLogLen = 0;
static volatile int sPrinted = 0;
static volatile int sBusy = 0;
static volatile int sErrCount = 0;
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

/** UI 线程：把新增日志刷到 textview + logcat（logcat 单行，换行换 ' | '） */
static void flushLog() {
	if (sLogLen <= sPrinted) {
		return;
	}
	char snapshot[7000] = { 0 };
	pthread_mutex_lock(&sLogMx);
	memcpy(snapshot, sLog, sizeof(snapshot) - 1);
	pthread_mutex_unlock(&sLogMx);
	char *newpart = snapshot + sPrinted;
	/* textview：给最后若干行，避免超长 */
	const char *show = newpart;
	if (strlen(newpart) > 900) {
		show = newpart + (strlen(newpart) - 900);
	}
	if (mTextStatusPtr != NULL) {
		mTextStatusPtr->setText(show);
	}
	/* logcat：按行打，行内再压成单行 */
	char line[640] = { 0 };
	int li = 0;
	for (const char *p = newpart; ; p++) {
		if (*p == '\n' || *p == '\0') {
			if (li > 0) {
				line[li] = '\0';
				LOGD("netstack demo: %s\n", line);
				li = 0;
			}
			if (*p == '\0') break;
		} else if (li < (int) sizeof(line) - 1) {
			line[li++] = *p;
		}
	}
	sPrinted = sLogLen;
}

/* ---------------- MQTT 客户端（跨任务复用） ---------------- */
static mqtt::Client *sMqtt = NULL;
static volatile int sMqttConnected = 0;
static volatile int sMqttMsgCount = 0;
static char sMqttLast[256] = { 0 };
static pthread_mutex_t sMqttMx = PTHREAD_MUTEX_INITIALIZER;

static void mqttOnConnected(const std::string &cause) {
	sMqttConnected = 1;
	logLine("[MQTT] on_connected cause=%s", cause.c_str());
}
static void mqttOnDisconnected(const std::string &cause) {
	sMqttConnected = 0;
	logLine("[MQTT] on_disconnected cause=%s", cause.c_str());
}
static void mqttOnMessage(const std::string &topic, const std::string &payload) {
	pthread_mutex_lock(&sMqttMx);
	sMqttMsgCount++;
	size_t pn = payload.size();
	if (pn > sizeof(sMqttLast) - 1) pn = sizeof(sMqttLast) - 1;
	memcpy(sMqttLast, payload.data(), pn);
	sMqttLast[pn] = '\0';
	pthread_mutex_unlock(&sMqttMx);
	logLine("[MQTT] on_message topic=%s len=%d payload=%s",
			topic.c_str(), (int) payload.size(), payload.c_str());
}

static bool ensureMqtt() {
	if (sMqtt != NULL) {
		return sMqttConnected != 0;
	}
	mqtt::Client::Configuration conf;
	conf.client_id = "zk-netstack-108";
	conf.server = MQTT_URL;
	conf.username = "admin";
	conf.password = "zkswe1024";
	conf.on_connected = mqttOnConnected;
	conf.on_disconnected = mqttOnDisconnected;
	logLine("[MQTT] new Client(server=%s client_id=%s)", MQTT_URL, conf.client_id.c_str());
	sMqtt = new mqtt::Client(conf);
	for (int i = 0; i < 75 && !sMqttConnected; i++) {     /* 等 15s */
		usleep(200 * 1000);
	}
	logLine("[MQTT] 连接结果: connected=%d isConnected()=%d", sMqttConnected,
			sMqtt ? (sMqtt->isConnected() ? 1 : 0) : -1);
	return sMqttConnected != 0;
}

/* ---------------- 各任务（在 worker 线程里跑） ---------------- */
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
		if (d.size() > 3) d.erase(d.size() - 1);      /* 去尾部换行 */
		logLine("[HTTP]   body: %s", d.c_str());
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
		h["X-Demo"] = "zkswe-netstack";
		cfg.setHeaders(h);
		std::string body = "{\"from\":\"z20-108\",\"msg\":\"curl-cxx POST works\"}";
		http::AxiosResponse r = ios.POST(std::string(LAN_BASE) + "/echo", body, cfg);
		logLine("[HTTP] POST /echo -> %d %s | %d bytes", r.status, r.status_text.c_str(),
				(int) r.data.size());
		logLine("[HTTP]   echo: %s", r.data.c_str());
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
		logLine("[HTTPS] GET %s -> %d %s | %d bytes（证书校验 + 时间）",
				HTTPS_URL, r.status, r.status_text.c_str(), (int) r.data.size());
	} catch (base::Exception &e) {
		sErrCount++;
		logLine("[HTTPS] GET 异常: %s", e.what() ? e.what() : "?");
	}
}

static void jobNtp() {
	setenv("TZ", "UTC-8", 1);       /* 北京时区（TZ 字符串就是 UTC-8） */
	tzset();
	time_t before = time(NULL);
	std::vector<std::string> servers = ntp::defaultServerList();
	char list[200] = { 0 };
	for (size_t i = 0; i < servers.size() && i < 3; i++) {
		strncat(list, servers[i].c_str(), sizeof(list) - strlen(list) - 1);
		strncat(list, " ", sizeof(list) - strlen(list) - 1);
	}
	logLine("[NTP] 服务器: %s", list);
	bool ok = ntp::syncTime(servers, 3000);
	time_t after = time(NULL);
	char b1[64] = { 0 }, b2[64] = { 0 };
	struct tm tm1, tm2;
	localtime_r(&before, &tm1);
	localtime_r(&after, &tm2);
	strftime(b1, sizeof(b1), "%Y-%m-%d %H:%M:%S", &tm1);
	strftime(b2, sizeof(b2), "%Y-%m-%d %H:%M:%S", &tm2);
	logLine("[NTP] syncTime -> %s | 校时前=%s 校时后=%s（TZ=UTC-8 即北京时区）",
			ok ? "成功" : "失败", b1, b2);
	if (!ok) {
		sErrCount++;
	}
}

static void jobMqttPub() {
	if (!ensureMqtt()) {
		sErrCount++;
		logLine("[MQTT] 未连上，发布跳过");
		return;
	}
	char payload[160] = { 0 };
	time_t now = time(NULL);
	snprintf(payload, sizeof(payload), "{\"dev\":\"108\",\"ts\":%ld,\"msg\":\"mqtt-cxx publish ok\"}",
			(long) now);
	bool ok = sMqtt->publish(MQTT_TOPIC, std::string(payload), mqtt::QOS_AT_LEAST_ONCE);
	logLine("[MQTT] publish(topic=%s qos=1) -> %s | payload=%s", MQTT_TOPIC, ok ? "OK" : "FAIL", payload);
	if (!ok) {
		sErrCount++;
	}
}

static void jobMqttSub() {
	if (!ensureMqtt()) {
		sErrCount++;
		logLine("[MQTT] 未连上，订阅跳过");
		return;
	}
	pthread_mutex_lock(&sMqttMx);
	sMqttMsgCount = 0;
	sMqttLast[0] = '\0';
	pthread_mutex_unlock(&sMqttMx);
	bool sok = sMqtt->subscribe(MQTT_TOPIC, mqtt::QOS_AT_LEAST_ONCE, mqttOnMessage);
	logLine("[MQTT] subscribe(topic=%s qos=1) -> %s", MQTT_TOPIC, sok ? "OK" : "FAIL");
	if (!sok) {
		sErrCount++;
		return;
	}
	char payload[160] = { 0 };
	snprintf(payload, sizeof(payload), "{\"dev\":\"108\",\"msg\":\"sub echo test\"}");
	sMqtt->publish(MQTT_TOPIC, std::string(payload), mqtt::QOS_AT_LEAST_ONCE);
	logLine("[MQTT] 已发一条等回显: %s", payload);
	for (int i = 0; i < 30 && sMqttMsgCount == 0; i++) {     /* 等 6s */
		usleep(200 * 1000);
	}
	pthread_mutex_lock(&sMqttMx);
	int cnt = sMqttMsgCount;
	char last[256] = { 0 };
	memcpy(last, sMqttLast, sizeof(last) - 1);
	last[sizeof(last) - 1] = '\0';
	pthread_mutex_unlock(&sMqttMx);
	logLine("[MQTT] 收到 %d 条，最后一条=%s", cnt, cnt ? last : "(无)");
	if (cnt == 0) {
		sErrCount++;
	}
	bool uok = sMqtt->unsubscribe(MQTT_TOPIC);
	logLine("[MQTT] unsubscribe -> %s", uok ? "OK" : "FAIL");
}

/* ---------------- worker 线程 ---------------- */
enum { JOB_NONE = 0, JOB_HTTP_GET, JOB_HTTP_POST, JOB_HTTPS_GET, JOB_NTP, JOB_MQTT_PUB, JOB_MQTT_SUB, JOB_AUTO };

static void *workerProc(void *arg) {
	int job = (int) (long) arg;
	if (job == JOB_HTTP_GET) {
		logLine("== HTTP GET（curl-cxx http::Axios::GET） ==");
		jobHttpGet();
	} else if (job == JOB_HTTP_POST) {
		logLine("== HTTP POST（http::Axios::POST + Headers） ==");
		jobHttpPost();
	} else if (job == JOB_HTTPS_GET) {
		logLine("== HTTPS GET（curl + mbedtls，证书走 resources/cacert.pem） ==");
		jobHttpsGet();
	} else if (job == JOB_NTP) {
		logLine("== NTP 校时（ntp::syncTime） ==");
		jobNtp();
	} else if (job == JOB_MQTT_PUB) {
		logLine("== MQTT 连接 + 发布（mqtt::Client::publish） ==");
		jobMqttPub();
	} else if (job == JOB_MQTT_SUB) {
		logLine("== MQTT 订阅 + 回显（subscribe / on_message） ==");
		jobMqttSub();
	} else if (job == JOB_AUTO) {
		logLine("########## 自检 AUTO 开始（curl-cxx → ntp → mqtt） ##########");
		logLine("== 1/5 HTTP GET ==");
		jobHttpGet();
		logLine("== 2/5 HTTP POST ==");
		jobHttpPost();
		logLine("== 3/5 HTTPS GET ==");
		jobHttpsGet();
		logLine("== 4/5 NTP 校时 ==");
		jobNtp();
		logLine("== 5/5 MQTT 订阅+回显 ==");
		jobMqttSub();
		logLine("########## 自检 AUTO 结束：错误数=%d ##########", sErrCount);
	}
	sBusy = 0;
	return NULL;
}

static void startJob(int job) {
	if (sBusy) {
		logLine("(上一个任务还在跑，忽略本次)");
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

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
	{0, 200},
};

/**
 * 当界面构造时触发 —— 只做 UI 初始化，不碰网络（网络任务全走按钮 → worker 线程）
 */
static void onUI_init() {
  #ifdef FUN_BUILD
  INIT_UI_TIMERS
  #endif // FUN_BUILD
	logLine("就绪：curl-cxx / ntp / mqtt-cxx 验证示例。");
	logLine("HTTP 目标 %s（本机 LAN 测试服务）", LAN_BASE);
	logLine("MQTT 目标 %s", MQTT_URL);
	flushLog();
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

/* ==================== 按钮 ==================== */
static bool onButtonClick_ButtonHttpGet(ZKButton *pButton) {
	startJob(JOB_HTTP_GET);
	return true;
}
static bool onButtonClick_ButtonHttpPost(ZKButton *pButton) {
	startJob(JOB_HTTP_POST);
	return true;
}
static bool onButtonClick_ButtonHttpsGet(ZKButton *pButton) {
	startJob(JOB_HTTPS_GET);
	return true;
}
static bool onButtonClick_ButtonNtp(ZKButton *pButton) {
	startJob(JOB_NTP);
	return true;
}
static bool onButtonClick_ButtonMqttPub(ZKButton *pButton) {
	startJob(JOB_MQTT_PUB);
	return true;
}
static bool onButtonClick_ButtonMqttSub(ZKButton *pButton) {
	startJob(JOB_MQTT_SUB);
	return true;
}
static bool onButtonClick_ButtonAuto(ZKButton *pButton) {
	if (sBusy) {
		logLine("AUTO 正在跑，忽略");
	} else {
		sErrCount = 0;
		startJob(JOB_AUTO);
	}
	return true;
}
