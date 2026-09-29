#pragma once
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#include "uart/ProtocolSender.h"

/*
 * mqtt-cxx 依赖包用法示例（Z20 86 面板 / 480x480）
 *
 * 覆盖 API（唯一头 include/mqtt/mqtt_client.h）：
 *   mqtt::Client(Configuration)   —— 构造即发起连接（异步，看 on_connected / isConnected）
 *   subscribe(topic, Qos, handler) / publish(topic, payload, Qos[, retained]) / unsubscribe(topic)
 *   Qos: QOS_AT_MOST_ONCE / QOS_AT_LEAST_ONCE / QOS_EXACTLY_ONCE
 *   Configuration: server / client_id / username / password / clean_session / will / ssl / 两个回调
 *
 * 关键做法：
 *   ① 阻塞式等待连上（示例里轮询 isConnected 最多 15 s）必须放 worker 线程；
 *   ② **回调在库线程里跑** → 只置标志位 + 打日志，别在回调里动 UI 控件；
 *   ③ 连接失败会抛异常（构造/使用都可能）→ 一定 try/catch；
 *   ④ TLS（mqtts）要连带声明 paho-mqtt3as + openssl，否则链接报 BIO_read/RAND_bytes/SHA1_* undefined。
 *
 * 来源：demos/net-stack-verify-z20（明文 qos1 收发回显）+ demos/net-stack-advanced-z20
 *       （MQTTS(TLS) / LWT 遗嘱 / 异常断线自动重连）——都真机验证过。
 * ⚠️ broker 地址是**占位**：改成你自己测试机的 IP（或公网 broker）。
 */

#include <mqtt/mqtt_client.h>

#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

/* ---- 改成你自己的 broker ---- */
#define MQTT_PLAIN "mqtt://192.168.x.x:1883"
#define MQTTS_URL  "mqtts://test.mosquitto.org:8883"
#define TOPIC_DATA "zk/demo/data"
#define TOPIC_WILL "zk/demo/will"

/* ---------------- 线程安全日志（worker 写，UI 线程刷） ---------------- */
static char sLog[4096];
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
	char snap[4096] = { 0 };
	pthread_mutex_lock(&sLogMx);
	memcpy(snap, sLog, sizeof(snap) - 1);
	pthread_mutex_unlock(&sLogMx);
	const char *newpart = snap + sPrinted;
	const char *show = newpart;
	if (strlen(newpart) > 900) {
		show = newpart + (strlen(newpart) - 900);
	}
	if (mTextStatusPtr != NULL) {
		mTextStatusPtr->setText(show);
	}
	char line[600] = { 0 };
	int li = 0;
	for (const char *p = newpart;; p++) {
		if (*p == '\n' || *p == '\0') {
			if (li > 0) {
				line[li] = '\0';
				LOGD("mqtt-cxx demo: %s\n", line);
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

/* ---------------- 两个客户端实例：明文（LWT/收显）+ TLS ---------------- */
static mqtt::Client *sPlain = NULL;
static mqtt::Client *sTls = NULL;
static volatile int sPlainConn = 0, sTlsConn = 0;
static volatile int sMsgCount = 0;
static char sLastMsg[256] = { 0 };
static pthread_mutex_t sMx = PTHREAD_MUTEX_INITIALIZER;

static void onConnected(const std::string &cause) {
	sPlainConn = 1;
	logLine("[MQTT] on_connected cause=%s", cause.c_str());
}
static void onDisconnected(const std::string &cause) {
	sPlainConn = 0;
	logLine("[MQTT] on_disconnected cause=%s", cause.c_str());
}
static void onMessage(const std::string &topic, const std::string &payload) {
	pthread_mutex_lock(&sMx);
	sMsgCount++;
	size_t n = payload.size();
	if (n > sizeof(sLastMsg) - 1) n = sizeof(sLastMsg) - 1;
	memcpy(sLastMsg, payload.data(), n);
	sLastMsg[n] = '\0';
	pthread_mutex_unlock(&sMx);
	/* ⚠️ 这里在库线程：只打日志，别动 UI 控件 */
	logLine("[MQTT] on_message topic=%s len=%d payload=%s", topic.c_str(), (int) payload.size(), payload.c_str());
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
	pthread_mutex_lock(&sMx);
	sMsgCount++;
	snprintf(sLastMsg, sizeof(sLastMsg), "%s", payload.c_str());
	pthread_mutex_unlock(&sMx);
	logLine("[MQTTS] on_message topic=%s len=%d payload=%s", topic.c_str(), (int) payload.size(), payload.c_str());
}

/** 惰性建明文 client（带 LWT 遗嘱）；返回是否连上 */
static bool ensurePlain() {
	if (sPlain != NULL) {
		return sPlainConn != 0;
	}
	mqtt::Client::Configuration conf;
	conf.client_id = "zk-demo-panel";              /* ⚠️ 同一 client_id 在 broker 侧互斥，别重复 new 不 delete */
	conf.server = MQTT_PLAIN;
	conf.username = "admin";                       /* 不需要认证就留空 */
	conf.password = "zkswe1024";
	conf.clean_session = true;
	conf.will.topic = TOPIC_WILL;                  /* LWT：异常断线时由 broker 代发 */
	conf.will.message = "{\"dev\":\"demo\",\"msg\":\"will: offline\"}";
	conf.will.qos = mqtt::QOS_AT_LEAST_ONCE;
	conf.will.retained = false;
	conf.on_connected = onConnected;
	conf.on_disconnected = onDisconnected;
	logLine("[MQTT] new Client(server=%s client_id=%s will_topic=%s)", MQTT_PLAIN, conf.client_id.c_str(), TOPIC_WILL);
	try {
		sPlain = new mqtt::Client(conf);           /* 构造即连接（异步） */
	} catch (const std::exception &e) {
		sErrCount++;
		logLine("[MQTT] 构造异常: %s", e.what());
		return false;
	}
	for (int i = 0; i < 75 && !sPlainConn; i++) {
		waitMs(200);
	}
	logLine("[MQTT] 连接结果 connected=%d isConnected=%d", sPlainConn,
			sPlain ? (sPlain->isConnected() ? 1 : 0) : -1);
	return sPlainConn != 0;
}

/* ---------------- 各任务 ---------------- */
static void jobPub() {
	if (!ensurePlain()) {
		sErrCount++;
		logLine("[MQTT] 未连上，发布跳过");
		return;
	}
	char payload[160] = { 0 };
	snprintf(payload, sizeof(payload), "{\"dev\":\"demo\",\"ts\":%ld,\"msg\":\"publish ok\"}", (long) time(NULL));
	bool ok = sPlain->publish(TOPIC_DATA, std::string(payload), mqtt::QOS_AT_LEAST_ONCE);
	logLine("[MQTT] publish(topic=%s qos=1) -> %s | payload=%s", TOPIC_DATA, ok ? "OK" : "FAIL", payload);
	if (!ok) {
		sErrCount++;
	}
}

static void jobSub() {
	if (!ensurePlain()) {
		sErrCount++;
		logLine("[MQTT] 未连上，订阅跳过");
		return;
	}
	pthread_mutex_lock(&sMx);
	sMsgCount = 0;
	sLastMsg[0] = '\0';
	pthread_mutex_unlock(&sMx);
	bool sok = sPlain->subscribe(TOPIC_DATA, mqtt::QOS_AT_LEAST_ONCE, onMessage);
	logLine("[MQTT] subscribe(topic=%s qos=1) -> %s", TOPIC_DATA, sok ? "OK" : "FAIL");
	if (!sok) {
		sErrCount++;
		return;
	}
	sPlain->publish(TOPIC_DATA, std::string("{\"dev\":\"demo\",\"msg\":\"sub echo test\"}"),
			mqtt::QOS_AT_LEAST_ONCE);
	logLine("[MQTT] 已发一条等回显…");
	for (int i = 0; i < 30 && sMsgCount == 0; i++) {
		waitMs(200);
	}
	pthread_mutex_lock(&sMx);
	int cnt = sMsgCount;
	char last[256] = { 0 };
	snprintf(last, sizeof(last), "%s", sLastMsg);
	pthread_mutex_unlock(&sMx);
	logLine("[MQTT] 收到 %d 条，最后一条=%s", cnt, cnt ? last : "(无)");
	if (cnt == 0) {
		sErrCount++;
	}
	logLine("[MQTT] unsubscribe -> %s", sPlain->unsubscribe(TOPIC_DATA) ? "OK" : "FAIL");
}

/** 遗嘱注册（真正代发要用 kill -9 制造异常断线，见 example/README.md 的见证端命令） */
static void jobWill() {
	logLine("[LWT] 注册遗嘱 topic=%s payload={\"dev\":\"demo\",\"msg\":\"will: offline\"}", TOPIC_WILL);
	if (!ensurePlain()) {
		sErrCount++;
		logLine("[LWT] 连不上 broker，遗嘱未注册成功");
		return;
	}
	bool sok = sPlain->subscribe(TOPIC_DATA, mqtt::QOS_AT_LEAST_ONCE, onMessage);
	bool pok = sPlain->publish(TOPIC_DATA, std::string("{\"dev\":\"demo\",\"msg\":\"alive\"}"),
			mqtt::QOS_AT_LEAST_ONCE);
	logLine("[LWT] subscribe -> %s | publish alive -> %s", sok ? "OK" : "FAIL", pok ? "OK" : "FAIL");
	if (!sok || !pok) {
		sErrCount++;
	}
	logLine("[LWT] 遗嘱已就绪：用 kill -9 杀进程（不发 DISCONNECT）→ broker 应约 2s 代发遗嘱");
}

static void jobMqtts() {
	if (sTls == NULL) {
		mqtt::Client::Configuration conf;
		conf.client_id = "zk-demo-panel-tls";
		conf.server = MQTTS_URL;
		conf.ssl.verify = false;                     /* 公网 broker 自签/不受信 CA：只为验通路 */
		conf.ssl.enable_server_cert_auth = false;
		conf.on_connected = tlsOnConnected;
		conf.on_disconnected = tlsOnDisconnected;
		logLine("[MQTTS] new Client(%s) ssl.verify=false", MQTTS_URL);
		try {
			sTls = new mqtt::Client(conf);
		} catch (const std::exception &e) {
			sErrCount++;
			logLine("[MQTTS] 构造异常: %s", e.what());
			return;
		}
	}
	for (int i = 0; i < 100 && !sTlsConn; i++) {     /* 公网 TLS 慢：最多等 20s */
		waitMs(200);
	}
	logLine("[MQTTS] 连接结果 connected=%d isConnected=%d", sTlsConn,
			sTls ? (sTls->isConnected() ? 1 : 0) : -1);
	if (!sTlsConn) {
		sErrCount++;
		logLine("[MQTTS] 自查：Manifest 里 paho-mqtt3as + openssl 声明了吗");
		return;
	}
	pthread_mutex_lock(&sMx);
	sMsgCount = 0;
	sLastMsg[0] = '\0';
	pthread_mutex_unlock(&sMx);
	bool sok = sTls->subscribe(TOPIC_DATA, mqtt::QOS_AT_LEAST_ONCE, tlsOnMessage);
	char payload[128] = { 0 };
	snprintf(payload, sizeof(payload), "{\"dev\":\"demo\",\"via\":\"mqtts\",\"ts\":%ld}", (long) time(NULL));
	bool pok = sTls->publish(TOPIC_DATA, std::string(payload), mqtt::QOS_AT_LEAST_ONCE);
	logLine("[MQTTS] subscribe -> %s | publish qos1 -> %s | payload=%s", sok ? "OK" : "FAIL", pok ? "OK" : "FAIL", payload);
	for (int i = 0; i < 30 && sMsgCount == 0; i++) {
		waitMs(200);
	}
	pthread_mutex_lock(&sMx);
	int cnt = sMsgCount;
	char last[256] = { 0 };
	snprintf(last, sizeof(last), "%s", sLastMsg);
	pthread_mutex_unlock(&sMx);
	logLine("[MQTTS] 收到 %d 条 echo=%s", cnt, cnt ? last : "(无)");
	if (cnt == 0 || !sok || !pok) {
		sErrCount++;
	}
}

/* ---------------- worker ---------------- */
enum { JOB_NONE = 0, JOB_PUB, JOB_SUB, JOB_WILL, JOB_MQTTS, JOB_AUTO };

static void *workerProc(void *arg) {
	int job = (int) (long) arg;
	if (job == JOB_PUB) {
		logLine("== MQTT 连接 + 发布 ==");
		jobPub();
	} else if (job == JOB_SUB) {
		logLine("== MQTT 订阅 + 回显 ==");
		jobSub();
	} else if (job == JOB_WILL) {
		logLine("== MQTT LWT 遗嘱 ==");
		jobWill();
	} else if (job == JOB_MQTTS) {
		logLine("== MQTTS(TLS) ==");
		jobMqtts();
	} else if (job == JOB_AUTO) {
		logLine("########## 自检 AUTO 开始 ##########");
		logLine("== 1/4 发布 ==");      jobPub();
		logLine("== 2/4 订阅回显 ==");  jobSub();
		logLine("== 3/4 遗嘱 ==");      jobWill();
		logLine("== 4/4 MQTTS ==");     jobMqtts();
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

/** 构造时触发 —— 只做 UI 初始化，不碰网络 */
static void onUI_init() {
  #ifdef FUN_BUILD
  INIT_UI_TIMERS
  #endif // FUN_BUILD
	logLine("就绪：mqtt-cxx 示例（发布 / 订阅回显 / 遗嘱 / MQTTS）");
	logLine("明文 broker %s", MQTT_PLAIN);
	logLine("MQTTS broker %s", MQTTS_URL);
	logLine("⚠️ 用前把 IP 占位改成你的 broker；TLS 要连带声明 paho-mqtt3as + openssl");
	if (mTextStatusPtr != NULL) {
		mTextStatusPtr->setText(sLog);
	}
	sPrinted = sLogLen;
}

static void onUI_intent(const Intent *intentPtr) { }
static void onUI_show() { }
static void onUI_hide() { }
static void onUI_quit() {
	/* 析构会断连；同一 client_id 别反复 new 不 delete（会被 broker 互踢） */
	if (sPlain != NULL) {
		delete sPlain;
		sPlain = NULL;
	}
	if (sTls != NULL) {
		delete sTls;
		sTls = NULL;
	}
}
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
static bool onButtonClick_ButtonPub(ZKButton *pButton)   { startJob(JOB_PUB);   return true; }
static bool onButtonClick_ButtonSub(ZKButton *pButton)   { startJob(JOB_SUB);   return true; }
static bool onButtonClick_ButtonWill(ZKButton *pButton)  { startJob(JOB_WILL);  return true; }
static bool onButtonClick_ButtonMqtts(ZKButton *pButton) { startJob(JOB_MQTTS); return true; }
static bool onButtonClick_ButtonAuto(ZKButton *pButton) {
	if (sBusy) {
		logLine("AUTO 正在跑，忽略");
	} else {
		sErrCount = 0;
		startJob(JOB_AUTO);
	}
	return true;
}
