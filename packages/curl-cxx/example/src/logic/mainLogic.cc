#pragma once
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#include "uart/ProtocolSender.h"

/*
 * curl-cxx 依赖包用法示例（Z20 86 面板 / 480x480）
 *
 * 覆盖 API（头文件在 registry 的 include/http/）：
 *   http::Axios             —— GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS/request + defaults
 *   http::AxiosRequestConfig—— baseURL/headers/query/连接与总超时
 *   http::AxiosResponse     —— status/status_text/headers/data + getContentLength/getContentType
 *   http::Downloader        —— 单例 instance() + add(Task)（进度/结果回调、低速超时、重试）
 *   http::WebSocket         —— connect/sendFrame/receiveFrame/close（依赖 curl 的 ws 支持）
 *
 * 关键做法：**Axios/Downloader 都是阻塞调用 → 全部丢进 worker 线程**，
 *          主线程只用 200ms 定时器把日志刷到 textview + logcat（否则面板点不动/白屏）。
 *
 * 来源：demos/net-stack-verify-z20（GET/POST/HTTPS）+ demos/net-stack-advanced-z20
 *       （Downloader 双任务 + 进度回调 / WebSocket 回显）——两轮都真机验证过。
 * ⚠️ 目标 IP 是**占位**：改成你自己测试机的 LAN IP（HTTP 服务、WS 服务）。
 * ⚠️ HTTPS 硬前提：① 先校时（ntp 包）② cacert.pem 放**资源目录(resPath)**。
 */

#include <http/axios.h>
#include <http/downloader.h>
#include <http/web_socket.h>
#include <base/exception.h>

#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

/* ---- 改成你自己的测试机（HTTP 服务 8000 / WS 回显服务 8766） ---- */
#define LAN_BASE   "http://192.168.x.x:8000"
#define HTTPS_URL  "https://www.baidu.com"
#define WS_URL     "ws://192.168.x.x:8766"

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

/** UI 线程：把新增日志刷到 textview（末段）+ logcat（按行拆单行，换行会被日志框架截断） */
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
				LOGD("curl-cxx demo: %s\n", line);
				li = 0;
			}
			if (*p == '\0') break;
		} else if (li < (int) sizeof(line) - 1) {
			line[li++] = *p;
		}
	}
	sPrinted = sLogLen;
}

/* ---------------- 各任务（worker 线程里跑） ---------------- */
static http::AxiosRequestConfig makeCfg(int connectMs, int totalMs) {
	http::AxiosRequestConfig cfg;
	cfg.setConnectTimeout(connectMs);
	cfg.setTimeout(totalMs);
	return cfg;
}

static void jobHttpGet() {
	try {
		http::Axios ios;
		http::AxiosResponse r = ios.GET(std::string(LAN_BASE) + "/hello.txt", makeCfg(3000, 10000));
		logLine("[HTTP] GET -> %d %s | %d bytes | ctype=%s",
				r.status, r.status_text.c_str(), (int) r.data.size(), r.getContentType().c_str());
		logLine("[HTTP]   body: %s", r.data.c_str());
	} catch (base::Exception &e) {
		sErrCount++;
		logLine("[HTTP] GET 异常: %s", e.what() ? e.what() : "?");
	}
}

static void jobHttpPost() {
	try {
		http::Axios ios;
		http::AxiosRequestConfig cfg = makeCfg(3000, 10000);
		http::Headers h;
		h["Content-Type"] = "application/json";
		cfg.setHeaders(h);
		std::string body = "{\"from\":\"z20-demo\",\"msg\":\"curl-cxx POST works\"}";
		http::AxiosResponse r = ios.POST(std::string(LAN_BASE) + "/echo", body, cfg);
		logLine("[HTTP] POST -> %d %s | %d bytes", r.status, r.status_text.c_str(), (int) r.data.size());
		logLine("[HTTP]   echo: %s", r.data.c_str());
	} catch (base::Exception &e) {
		sErrCount++;
		logLine("[HTTP] POST 异常: %s", e.what() ? e.what() : "?");
	}
}

static void jobHttpsGet() {
	try {
		http::Axios ios;
		http::AxiosResponse r = ios.GET(HTTPS_URL, makeCfg(5000, 15000));
		logLine("[HTTPS] GET %s -> %d %s | %d bytes（证书校验通过）",
				HTTPS_URL, r.status, r.status_text.c_str(), (int) r.data.size());
	} catch (base::Exception &e) {
		sErrCount++;
		logLine("[HTTPS] GET 异常: %s", e.what() ? e.what() : "?");
		logLine("[HTTPS]   自查：① 校时了吗 ② cacert.pem 在资源目录(resPath) 吗");
	}
}

static void jobDownload() {
	logLine("[DL] http::Downloader 双任务（带进度 + 结果回调）");
	static int done = 0;
	done = 0;
	http::Downloader &dl = http::Downloader::instance();
	{
		http::Downloader::Task t;
		t.source = std::string(LAN_BASE) + "/big?kb=300";
		t.target = "/data/demo_big.bin";             /* ⚠️ 落盘目录改成本机可写目录 */
		t.retry_max = 3;
		t.low_speed_limit = http::LowSpeedLimit(512, 10);
		t.progress = [](const http::Downloader::Task &task, int64_t d, int64_t total) -> void {
			logLine("[DL] 进度 %s %lld/%lld", task.target.c_str(), (long long) d, (long long) total);
		};
		t.result = [](const http::Downloader::Task &task, bool ok) -> void {
			struct stat st;
			long long sz = (stat(task.target.c_str(), &st) == 0) ? (long long) st.st_size : 0;
			logLine("[DL] 结果 %s -> %s，落盘 %lld B", task.source.c_str(), ok ? "成功" : "失败", sz);
			done++;
		};
		dl.add(t);
	}
	{
		http::Downloader::Task t;
		t.source = std::string(LAN_BASE) + "/json";
		t.target = "/data/demo_json.json";
		t.retry_max = 2;
		t.progress = NULL;
		t.result = [](const http::Downloader::Task &task, bool ok) -> void {
			logLine("[DL] 结果 %s -> %s", task.source.c_str(), ok ? "成功" : "失败");
			done++;
		};
		dl.add(t);
	}
	int waited = 0;
	while (waited < 90000 && done < 2) {              /* 最多等 90s */
		usleep(500 * 1000);
		waited += 500;
	}
	logLine("[DL] 双任务结束：完成 %d/2 用时≈%dms（剩余队列=%d）", done, waited, dl.size());
	if (done < 2) {
		sErrCount++;
	}
}

static void jobWebSocket() {
	try {
		http::WebSocket ws;
		logLine("[WS] connect(%s)", WS_URL);
		ws.connect(WS_URL, makeCfg(5000, 15000));
		const char *msg = "hello-ws-from-demo";
		int sent = ws.sendFrame(msg, (int) strlen(msg));
		logLine("[WS] sendFrame %d B: %s", sent, msg);
		char buf[512] = { 0 };
		int n = ws.receiveFrame(buf, sizeof(buf) - 1, 8000);
		if (n > 0) {
			buf[n] = '\0';
		}
		logLine("[WS] receiveFrame %d B: %s", n, n > 0 ? buf : "(空)");
		ws.close();
		logLine("[WS] close() 完成（回显服务要自己有；8765 可能被别的服务占着）");
		if (n <= 0) {
			sErrCount++;
		}
	} catch (base::Exception &e) {
		sErrCount++;
		logLine("[WS] 异常: %s", e.what() ? e.what() : "?");
	}
}

/* ---------------- worker ---------------- */
enum { JOB_NONE = 0, JOB_HTTP_GET, JOB_HTTP_POST, JOB_HTTPS_GET, JOB_DL, JOB_WS, JOB_AUTO };

static void *workerProc(void *arg) {
	int job = (int) (long) arg;
	if (job == JOB_HTTP_GET) {
		logLine("== HTTP GET（http::Axios::GET） ==");
		jobHttpGet();
	} else if (job == JOB_HTTP_POST) {
		logLine("== HTTP POST（POST + Headers） ==");
		jobHttpPost();
	} else if (job == JOB_HTTPS_GET) {
		logLine("== HTTPS GET（curl + mbedtls，CA 走资源目录） ==");
		jobHttpsGet();
	} else if (job == JOB_DL) {
		logLine("== http::Downloader 多任务 ==");
		jobDownload();
	} else if (job == JOB_WS) {
		logLine("== http::WebSocket ==");
		jobWebSocket();
	} else if (job == JOB_AUTO) {
		logLine("########## 自检 AUTO 开始 ##########");
		logLine("== 1/5 HTTP GET ==");    jobHttpGet();
		logLine("== 2/5 HTTP POST ==");   jobHttpPost();
		logLine("== 3/5 HTTPS GET ==");   jobHttpsGet();
		logLine("== 4/5 Downloader ==");  jobDownload();
		logLine("== 5/5 WebSocket ==");   jobWebSocket();
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

/** 构造时触发 —— 只做 UI 初始化，不碰网络（网络任务全走按钮 → worker 线程） */
static void onUI_init() {
  #ifdef FUN_BUILD
  INIT_UI_TIMERS
  #endif // FUN_BUILD
	logLine("就绪：curl-cxx 示例（HTTP/HTTPS/Downloader/WebSocket）");
	logLine("HTTP 目标 %s", LAN_BASE);
	logLine("WS   目标 %s", WS_URL);
	logLine("⚠️ 用前把 IP 占位改成你的测试机；HTTPS 要先校时 + cacert.pem 放资源目录");
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
static bool onButtonClick_ButtonHttpGet(ZKButton *pButton)  { startJob(JOB_HTTP_GET);   return true; }
static bool onButtonClick_ButtonHttpPost(ZKButton *pButton) { startJob(JOB_HTTP_POST);  return true; }
static bool onButtonClick_ButtonHttpsGet(ZKButton *pButton) { startJob(JOB_HTTPS_GET);  return true; }
static bool onButtonClick_ButtonDownload(ZKButton *pButton) { startJob(JOB_DL);         return true; }
static bool onButtonClick_ButtonWs(ZKButton *pButton)       { startJob(JOB_WS);         return true; }
static bool onButtonClick_ButtonAuto(ZKButton *pButton) {
	if (sBusy) {
		logLine("AUTO 正在跑，忽略");
	} else {
		sErrCount = 0;
		startJob(JOB_AUTO);
	}
	return true;
}
