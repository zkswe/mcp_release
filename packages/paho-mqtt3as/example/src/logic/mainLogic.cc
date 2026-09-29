#pragma once
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#include "uart/ProtocolSender.h"

/*
 * paho-mqtt3as 依赖包用法示例（Z20 86 面板 / 480x480）—— **直接调 paho C API**
 *
 * ⚠️ 先说清楚验证状态：
 *   本仓 demos 里的 MQTT 走的是 **mqtt-cxx 门面**（paho 被 mqtt-cxx 间接使用），
 *   明文 + MQTTS + LWT 都真机验证过（见 packages/paho-mqtt3as/evidence/）。
 *   但**直接调 `MQTTClient_*` / `MQTTAsync_*` 这条路径本仓没有单独上机的记录** →
 *   本示例按包头签名写成（签名取自 packages/paho-mqtt3as/package.yaml 的 api 段，实读包头），
 *   属"可直接抄、但未取证"形态。要标 ✅ 需在 Z20 上跑一轮并留 logcat。
 *
 * 覆盖：
 *   MQTTClient（同步 API）  —— create / setCallbacks / connect / subscribe / publish / waitForCompletion / disconnect / destroy
 *   MQTTAsync（异步 API）   —— create / setCallbacks / connect（回调式，非阻塞）
 *
 * 硬约束（来自包 gotchas，实测过）：
 *   ① 本包**没有 README、没有 Manifest** → Manifest 里必须自己显式声明 openssl（+ pthread），
 *      否则链接报 BIO_read / RAND_bytes / SHA1_Init/Update/Final undefined；
 *   ② 回调里必须 MQTTClient_freeMessage() + MQTTClient_free()，否则消息体泄漏；
 *   ③ 同一个 client_id 在 broker 侧互斥（两个连接互踢）。
 *
 * ⚠️ broker 地址是**占位**：改成你自己测试机的 IP。
 */

#include <MQTTClient.h>
#include <MQTTAsync.h>

#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

/* ---- 改成你自己的 broker ---- */
#define MQTT_SERVER "tcp://192.168.x.x:1883"
#define TOPIC_DATA  "zk/demo/paho"

/* ---------------- 线程安全日志（worker 写，UI 线程刷） ---------------- */
static char sLog[4096];
static volatile int sLogLen = 0, sPrinted = 0, sBusy = 0, sErrCount = 0;
static volatile int sMsgCount = 0;
static char sLastMsg[256] = { 0 };
static pthread_mutex_t sLogMx = PTHREAD_MUTEX_INITIALIZER;   /* 只保护日志缓冲 */
static pthread_mutex_t sMsgMx = PTHREAD_MUTEX_INITIALIZER;   /* 只保护 sMsgCount/sLastMsg（回调里用，别拿日志锁） */

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
				LOGD("paho demo: %s\n", line);
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

/* ---------------- 同步 API 的回调（库线程！只记数+日志） ---------------- */
static int onArrived(void *ctx, char *topicName, int topicLen, MQTTClient_message *msg) {
	pthread_mutex_lock(&sMsgMx);
	sMsgCount++;
	size_t n = (size_t) msg->payloadlen;
	if (n > sizeof(sLastMsg) - 1) n = sizeof(sLastMsg) - 1;
	memcpy(sLastMsg, msg->payload, n);
	sLastMsg[n] = '\0';
	pthread_mutex_unlock(&sMsgMx);
	logLine("[C] on_message topic=%.*s len=%d payload=%s", topicLen, topicName,
			msg->payloadlen, (const char *) msg->payload);
	/* ⚠️ 必须释放：本库不替你释放 */
	MQTTClient_freeMessage(&msg);
	MQTTClient_free(topicName);
	return 1;                    /* 1 = 消息已处理 */
}

static void onConnLost(void *ctx, char *cause) {
	logLine("[C] connection_lost cause=%s", cause ? cause : "(无)");
}

/* ---------------- 同步 API（MQTTClient_*） ---------------- */
static void jobSync() {
	MQTTClient cli = NULL;
	int rc = MQTTClient_create(&cli, MQTT_SERVER, "zk-demo-paho",
			MQTTCLIENT_PERSISTENCE_NONE, NULL);
	logLine("[C] MQTTClient_create -> %d", rc);
	if (rc != MQTTCLIENT_SUCCESS) {
		sErrCount++;
		return;
	}

	MQTTClient_connectOptions opt = MQTTClient_connectOptions_initializer;
	opt.keepAliveInterval = 20;
	opt.cleansession = 1;
	opt.username = NULL;         /* 需要认证再填 */
	opt.password = NULL;

	MQTTClient_setCallbacks(cli, NULL, onConnLost, onArrived, NULL);
	rc = MQTTClient_connect(cli, &opt);
	logLine("[C] MQTTClient_connect -> %d (%s)", rc,
			rc == MQTTCLIENT_SUCCESS ? "OK" : "失败：看 rc 码（1=版本不符 2=clientID 被拒 3=broker 不可用…）");
	if (rc != MQTTCLIENT_SUCCESS) {
		sErrCount++;
		MQTTClient_destroy(&cli);
		return;
	}

	rc = MQTTClient_subscribe(cli, TOPIC_DATA, 1);
	logLine("[C] subscribe(%s qos1) -> %d", TOPIC_DATA, rc);

	MQTTClient_deliveryToken tok;
	char payload[128] = { 0 };
	snprintf(payload, sizeof(payload), "{\"dev\":\"demo\",\"via\":\"MQTTClient\",\"ts\":%ld}", (long) time(NULL));
	rc = MQTTClient_publish(cli, TOPIC_DATA, (int) strlen(payload), payload, 1, 0, &tok);
	logLine("[C] publish qos1 -> %d payload=%s", rc, payload);
	rc = MQTTClient_waitForCompletion(cli, tok, 5000);      /* 等 broker 确认（qos1） */
	logLine("[C] waitForCompletion -> %d (%s)", rc, rc == MQTTCLIENT_SUCCESS ? "已确认" : "超时/失败");
	if (rc != MQTTCLIENT_SUCCESS) {
		sErrCount++;
	}

	for (int i = 0; i < 30 && sMsgCount == 0; i++) {        /* 等回显 6s */
		waitMs(200);
	}
	logLine("[C] 收到 %d 条，最后一条=%s", sMsgCount, sMsgCount ? sLastMsg : "(无)");
	if (sMsgCount == 0) {
		sErrCount++;
	}

	MQTTClient_disconnect(cli, 1000);
	MQTTClient_destroy(&cli);
	logLine("[C] disconnect + destroy 完成");
}

/* ---------------- 异步 API（MQTTAsync_*） ---------------- */
static volatile int sAsyncConn = 0;
static void onAsyncConnect(void *ctx, MQTTAsync_successData *resp) {
	sAsyncConn = 1;
	logLine("[A] connected (MQTTAsync)");
}
static void onAsyncConnectFail(void *ctx, MQTTAsync_failureData *resp) {
	sAsyncConn = 0;
	logLine("[A] connect failed code=%d", resp ? resp->code : -1);
}
static void onAsyncConnLost(void *ctx, char *cause) {
	sAsyncConn = 0;
	logLine("[A] connection_lost cause=%s", cause ? cause : "(无)");
}
static int onAsyncArrived(void *ctx, char *topicName, int topicLen, MQTTAsync_message *msg) {
	pthread_mutex_lock(&sMsgMx);
	sMsgCount++;
	snprintf(sLastMsg, sizeof(sLastMsg), "%.*s", msg->payloadlen, (char *) msg->payload);
	pthread_mutex_unlock(&sMsgMx);
	logLine("[A] on_message topic=%.*s len=%d payload=%.*s", topicLen, topicName,
			msg->payloadlen, msg->payloadlen, (char *) msg->payload);
	MQTTAsync_freeMessage(&msg);      /* 异步版用 MQTTAsync_free* */
	MQTTAsync_free(topicName);
	return 1;
}

static void jobAsync() {
	MQTTAsync cli = NULL;
	int rc = MQTTAsync_create(&cli, MQTT_SERVER, "zk-demo-paho-async",
			MQTTCLIENT_PERSISTENCE_NONE, NULL);
	logLine("[A] MQTTAsync_create -> %d", rc);
	if (rc != MQTTASYNC_SUCCESS) {
		sErrCount++;
		return;
	}
	rc = MQTTAsync_setCallbacks(cli, NULL, onAsyncConnLost, onAsyncArrived, NULL);
	logLine("[A] setCallbacks -> %d", rc);

	MQTTAsync_connectOptions opt = MQTTAsync_connectOptions_initializer;
	opt.keepAliveInterval = 20;
	opt.cleansession = 1;
	opt.onSuccess = onAsyncConnect;
	opt.onFailure = onAsyncConnectFail;
	rc = MQTTAsync_connect(cli, &opt);          /* 非阻塞 */
	logLine("[A] MQTTAsync_connect -> %d（异步，等回调）", rc);
	for (int i = 0; i < 75 && !sAsyncConn; i++) {
		waitMs(200);
	}
	logLine("[A] connected=%d", sAsyncConn);

	if (sAsyncConn) {
		MQTTAsync_responseOptions ro = MQTTAsync_responseOptions_initializer;
		rc = MQTTAsync_subscribe(cli, TOPIC_DATA, 1, &ro);
		logLine("[A] subscribe -> %d", rc);
		MQTTAsync_message msg = MQTTAsync_message_initializer;
		const char *payload = "{\"dev\":\"demo\",\"via\":\"MQTTAsync\"}";
		msg.payload = (void *) payload;
		msg.payloadlen = (int) strlen(payload);
		msg.qos = 1;
		rc = MQTTAsync_sendMessage(cli, TOPIC_DATA, &msg, &ro);
		logLine("[A] sendMessage -> %d", rc);
		for (int i = 0; i < 30 && sMsgCount == 0; i++) {
			waitMs(200);
		}
		logLine("[A] 收到 %d 条，最后一条=%s", sMsgCount, sMsgCount ? sLastMsg : "(无)");
	} else {
		sErrCount++;
	}

	MQTTAsync_disconnectOptions dop = MQTTAsync_disconnectOptions_initializer;
	MQTTAsync_disconnect(cli, &dop);
	waitMs(500);
	MQTTAsync_destroy(&cli);
	logLine("[A] disconnect + destroy 完成");
}

/* ---------------- worker ---------------- */
enum { JOB_NONE = 0, JOB_SYNC, JOB_ASYNC, JOB_AUTO };

static void *workerProc(void *arg) {
	int job = (int) (long) arg;
	if (job == JOB_SYNC) {
		logLine("== [C] 同步 API：连接→订阅→发布→收报 ==");
		jobSync();
	} else if (job == JOB_ASYNC) {
		logLine("== [A] 异步 API：MQTTAsync_connect ==");
		jobAsync();
	} else if (job == JOB_AUTO) {
		logLine("########## 自检 AUTO 开始（同步 API 全流程） ##########");
		sMsgCount = 0;
		sLastMsg[0] = '\0';
		jobSync();
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

static void onUI_init() {
  #ifdef FUN_BUILD
  INIT_UI_TIMERS
  #endif // FUN_BUILD
	logLine("就绪：paho-mqtt3as 示例（MQTTClient 同步 / MQTTAsync 异步）");
	logLine("broker %s", MQTT_SERVER);
	logLine("⚠️ 本示例是「直调 C API」路径，本仓未单独上机；日常建议走 mqtt-cxx 门面");
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
static bool onButtonClick_ButtonConnect(ZKButton *pButton) { startJob(JOB_SYNC);  return true; }
static bool onButtonClick_ButtonPub(ZKButton *pButton)     { startJob(JOB_SYNC);  return true; }
static bool onButtonClick_ButtonSub(ZKButton *pButton)     { startJob(JOB_SYNC);  return true; }
static bool onButtonClick_ButtonAsync(ZKButton *pButton)   { startJob(JOB_ASYNC); return true; }
static bool onButtonClick_ButtonAuto(ZKButton *pButton) {
	if (sBusy) {
		logLine("AUTO 正在跑，忽略");
	} else {
		sErrCount = 0;
		startJob(JOB_AUTO);
	}
	return true;
}
