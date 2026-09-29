#pragma once
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#include "uart/ProtocolSender.h"

/*
 * curl（libcurl 8.12.1-mbedtls）依赖包用法示例（Z20 86 面板 / 480x480）—— **直调 easy 接口**
 *
 * ⚠️ 先说清楚验证状态：
 *   本仓的 HTTP/HTTPS/下载/WS 真机验证都走 **curl-cxx 门面**（libcurl 是它的底层，请求确实由 libcurl 执行），
 *   但**直接调 `curl_easy_*` 这条路径本仓没有单独上机的记录**（`packages/curl/package.yaml` 里
 *   `verified: null` / `status: unverified`）→ 本示例按包头签名书写，属"可直接抄、未取证"形态。
 *   要标 ✅：在 Z20 上跑一轮并留 logcat（tag = `curl demo`），再更新 `../platforms.md`。
 *
 * 覆盖：curl_global_init / curl_easy_init / curl_easy_setopt / curl_easy_perform /
 *       curl_easy_getinfo / curl_slist_append / curl_easy_cleanup / curl_global_cleanup
 *
 * 硬口径（读包内 feature report + 实测量出来的）：
 *   ① **无内置 CA**（bundle/path/embed/fallback 全 no）→ HTTPS 必须自己 `CURLOPT_CAINFO`；
 *   ② **链接是一串**：curl + mbedtls + cares + z（少一个就满屏 undefined reference）；
 *   ③ **版本名 Z20 专属**：8.12.1-mbedtls（别的平台可能是 8.12.1 = openssl 变体）；
 *   ④ **IPv6 关**（只有 AAAA 记录的域名会失败，别当网络故障查）；
 *   ⑤ `curl_easy_setopt` 是变参 → long 类选项一律显式写 `1L/10L`（传 int 会踩 64 位对齐）；
 *   ⑥ 多线程别共享同一个 easy handle（跨线程用 `curl_easy_duphandle` 各起一份）。
 *
 * ⚠️ 目标 IP 是**占位**：改成你自己测试机的 LAN IP。
 */

#include <curl/curl.h>

#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

/* ---- 改成你自己的测试机 ---- */
#define LAN_BASE  "http://192.168.x.x:8000"
#define HTTPS_URL "https://www.baidu.com"
#define CA_PATH   "/tmp/ui/cacert.pem"      /* 资源目录（resPath）；正式部署 = 与 ftu 同级 */

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
				LOGD("curl demo: %s\n", line);
				li = 0;
			}
			if (*p == '\0') break;
		} else if (li < (int) sizeof(line) - 1) {
			line[li++] = *p;
		}
	}
	sPrinted = sLogLen;
}

/* ---------------- 回调与工具 ---------------- */
static size_t onWrite(char *ptr, size_t size, size_t nmemb, void *userdata) {
	((std::string *) userdata)->append(ptr, size * nmemb);
	return size * nmemb;                    /* 返回值必须 == size*nmemb，否则 curl 判错 */
}

/** 一次 easy 请求（method: "GET"/"POST"），返回 true=传输成功（状态码另看 getinfo） */
static bool easyRequest(const char *method, const std::string &url, const std::string *postBody,
		const char *caFile, long *httpCode, std::string &body) {
	CURL *curl = curl_easy_init();
	if (curl == NULL) {
		logLine("[CURL] curl_easy_init 失败");
		return false;
	}
	body.clear();
	struct curl_slist *headers = NULL;
	if (postBody != NULL) {
		headers = curl_slist_append(headers, "Content-Type: application/json");
		curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
		curl_easy_setopt(curl, CURLOPT_POSTFIELDS, postBody->c_str());
	}
	curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
	curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, method);
	curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, onWrite);
	curl_easy_setopt(curl, CURLOPT_WRITEDATA, &body);
	curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);      /* long 类选项必须写 1L/10L */
	curl_easy_setopt(curl, CURLOPT_TIMEOUT, 15L);
	curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 5L);
	if (caFile != NULL) {
		curl_easy_setopt(curl, CURLOPT_CAINFO, caFile);      /* 本包无内置 CA → HTTPS 必须给 */
	}

	CURLcode rc = curl_easy_perform(curl);
	long code = 0;
	curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &code);
	if (httpCode != NULL) {
		*httpCode = code;
	}
	if (rc != CURLE_OK) {
		logLine("[CURL] perform 失败: %d %s", (int) rc, curl_easy_strerror(rc));
	}
	if (headers != NULL) {
		curl_slist_free_all(headers);
	}
	curl_easy_cleanup(curl);
	return rc == CURLE_OK;
}

/* ---------------- 各任务 ---------------- */
static void jobGet() {
	logLine("== curl_easy GET %s/hello.txt ==", LAN_BASE);
	long code = 0;
	std::string body;
	bool ok = easyRequest("GET", std::string(LAN_BASE) + "/hello.txt", NULL, NULL, &code, body);
	logLine("[CURL] rc=%s HTTP=%ld bytes=%d", ok ? "OK" : "FAIL", code, (int) body.size());
	logLine("[CURL]   body: %s", body.c_str());
	if (!ok || code != 200) {
		sErrCount++;
	}
}

static void jobHttpsGet() {
	logLine("== curl_easy HTTPS GET（CAINFO=%s） ==", CA_PATH);
	long code = 0;
	std::string body;
	bool ok = easyRequest("GET", HTTPS_URL, NULL, CA_PATH, &code, body);
	logLine("[CURL] rc=%s HTTP=%ld bytes=%d", ok ? "OK" : "FAIL", code, (int) body.size());
	if (!ok) {
		sErrCount++;
		logLine("[CURL] 自查：① 校时了吗 ② CAINFO 指到资源目录了吗（本包无内置 CA）");
	}
}

static void jobPost() {
	logLine("== curl_easy POST %s/echo ==", LAN_BASE);
	std::string payload = "{\"from\":\"z20\",\"msg\":\"libcurl easy POST works\"}";
	long code = 0;
	std::string body;
	bool ok = easyRequest("POST", std::string(LAN_BASE) + "/echo", &payload, NULL, &code, body);
	logLine("[CURL] rc=%s HTTP=%ld bytes=%d", ok ? "OK" : "FAIL", code, (int) body.size());
	logLine("[CURL]   echo: %s", body.c_str());
	if (!ok || code != 200) {
		sErrCount++;
	}
}

/* ---------------- worker ---------------- */
enum { JOB_NONE = 0, JOB_GET, JOB_HTTPS, JOB_POST, JOB_AUTO };

static void *workerProc(void *arg) {
	int job = (int) (long) arg;
	/* 多线程场景：在起线程之前（或第一次用之前）调一次；easy 会隐式初始化，但显式更稳 */
	if (job == JOB_GET) {
		jobGet();
	} else if (job == JOB_HTTPS) {
		jobHttpsGet();
	} else if (job == JOB_POST) {
		jobPost();
	} else if (job == JOB_AUTO) {
		logLine("########## 自检 AUTO 开始 ##########");
		jobGet();
		jobHttpsGet();
		jobPost();
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
	logLine("就绪：libcurl 示例（easy 接口：GET / HTTPS / POST）");
	logLine("版本 %s", curl_version());
	logLine("HTTP 目标 %s；HTTPS 目标 %s", LAN_BASE, HTTPS_URL);
	logLine("⚠️ 这是「直调 easy」路径，本仓未单独上机；日常建议走 curl-cxx 门面");
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
static bool onButtonClick_ButtonGet(ZKButton *pButton)      { curl_global_init(CURL_GLOBAL_DEFAULT); startJob(JOB_GET);   return true; }
static bool onButtonClick_ButtonHttpsGet(ZKButton *pButton) { startJob(JOB_HTTPS); return true; }
static bool onButtonClick_ButtonPost(ZKButton *pButton)     { startJob(JOB_POST);  return true; }
static bool onButtonClick_ButtonAuto(ZKButton *pButton) {
	if (sBusy) {
		logLine("AUTO 正在跑，忽略");
	} else {
		sErrCount = 0;
		startJob(JOB_AUTO);
	}
	return true;
}
