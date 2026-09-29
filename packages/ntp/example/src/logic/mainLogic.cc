#pragma once
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#include "uart/ProtocolSender.h"

/*
 * ntp 依赖包用法示例（Z20 86 面板 / 480x480）
 *
 * 覆盖 API（头文件在 registry 的 include/ntp/）：
 *   ntp::syncTime(servers, recv_timeout)      —— 阻塞版，逐台服务器试
 *   ntp::startSyncTime(servers, callback)     —— 异步版（起线程后台跑，回调通知结果）
 *   ntp::getTime(ip, recv_timeout)            —— 单台取时间（失败抛 base::Exception）
 *   ntp::defaultServerList()                  —— 15 个内置 IP（阿里云优先）
 *
 * 关键做法：
 *   ① **必须先设时区**：setenv("TZ","UTC-8",1) + tzset()，否则本地时间不对（库只写 UTC 秒进系统时钟/RTC）；
 *   ② 阻塞版要放 worker 线程（同步一次约 3~4 s，卡 UI 线程 = 面板点不动）；
 *   ③ 实测步骤见 demos/net-stack-verify-z20 的 `[NTP]` 日志。
 *
 * ⚠️ 精度：本库四时间戳公式退化（T3 + RTT/2）→ 毫秒级稳态/组网对时不要用它（见包 gotchas）。
 */

#include <ntp/ntp.h>
#include <base/exception.h>

#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

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
				LOGD("ntp demo: %s\n", line);
				li = 0;
			}
			if (*p == '\0') break;
		} else if (li < (int) sizeof(line) - 1) {
			line[li++] = *p;
		}
	}
	sPrinted = sLogLen;
}

/* ---------------- 工具 ---------------- */
static void setupTimezone() {
	setenv("TZ", "UTC-8", 1);      /* 北京 = UTC-8（TZ 字符串就是这么写的） */
	tzset();
}

static void nowText(char *out, int size) {
	time_t t = time(NULL);
	struct tm tmv;
	localtime_r(&t, &tmv);
	strftime(out, size, "%Y-%m-%d %H:%M:%S", &tmv);
}

static std::vector<std::string> serverList() {
	/* 现场建议传自己的服务器（内置列表里混了境外地址，无外网时会白等很久） */
	std::vector<std::string> srv;
	srv.push_back("203.107.6.88");      /* 阿里云 ntp.aliyun.com，实测较稳 */
	srv.push_back("182.92.12.11");
	srv.push_back("120.25.115.20");
	return srv;
}

/* ---------------- 各任务 ---------------- */
static void jobSyncBlocking() {
	setupTimezone();
	std::vector<std::string> srv = serverList();
	logLine("[NTP] 服务器: %s %s %s", srv[0].c_str(), srv[1].c_str(), srv[2].c_str());
	char b1[64] = { 0 }, b2[64] = { 0 };
	nowText(b1, sizeof(b1));
	bool ok = ntp::syncTime(srv, 3000);       /* 阻塞：每台服务器超时 3s */
	nowText(b2, sizeof(b2));
	logLine("[NTP] syncTime -> %s | 校时前=%s 校时后=%s（TZ=UTC-8 北京时区）", ok ? "成功" : "失败", b1, b2);
	if (!ok) {
		sErrCount++;
	}
}

/* 异步版的回调在库线程里跑 → 只打日志/置标志，不动 UI 控件 */
static volatile int sAsyncDone = 0, sAsyncOk = 0;
static char sAsyncServer[64] = { 0 };
static struct timeval sAsyncTv;

static void onSyncEnd(const std::string &server, const struct timeval *tv) {
	if (tv != NULL) {
		sAsyncTv = *tv;
		sAsyncOk = 1;
	}
	snprintf(sAsyncServer, sizeof(sAsyncServer), "%s", server.c_str());
	logLine("[NTP] [cb] startSyncTime 结束 server=%s %s", server.c_str(),
			tv ? "（已写入系统时钟/RTC）" : "（全部服务器失败）");
	sAsyncDone = 1;
}

static void jobSyncAsync() {
	setupTimezone();
	char b1[64] = { 0 }, b2[64] = { 0 };
	nowText(b1, sizeof(b1));
	sAsyncDone = 0;
	sAsyncOk = 0;
	int rc = ntp::startSyncTime(ntp::defaultServerList(), onSyncEnd);   /* 0 = 线程已起 */
	logLine("[NTP] startSyncTime(defaultServerList()) -> %d（0=线程已起）", rc);
	for (int i = 0; i < 100 && !sAsyncDone; i++) {                      /* 最多等 20s */
		usleep(200 * 1000);
	}
	nowText(b2, sizeof(b2));
	logLine("[NTP] 异步结果：done=%d ok=%d server=%s timeval=%ld.%06ld | 前=%s 后=%s",
			sAsyncDone, sAsyncOk, sAsyncServer[0] ? sAsyncServer : "-",
			(long) sAsyncTv.tv_sec, (long) sAsyncTv.tv_usec, b1, b2);
	if (!sAsyncDone || !sAsyncOk) {
		sErrCount++;
	}
}

static void jobShowTime() {
	setupTimezone();
	char t[64] = { 0 };
	nowText(t, sizeof(t));
	time_t raw = time(NULL);
	logLine("[NTP] 系统时间（TZ=UTC-8）= %s | time_t=%ld", t, (long) raw);
	if (raw < 1748510332L) {          /* 库内硬编码的合理性下限：2025-05-29 */
		logLine("[NTP] ⚠️ 时间早于 2025-05-29：ntp::getTime() 会抛 invalid time（别当网络故障查）");
	}
}

/* ---------------- worker ---------------- */
enum { JOB_NONE = 0, JOB_SYNC, JOB_SYNC_ASYNC, JOB_TIME, JOB_AUTO };

static void *workerProc(void *arg) {
	int job = (int) (long) arg;
	if (job == JOB_SYNC) {
		logLine("== NTP 同步（阻塞版 ntp::syncTime） ==");
		jobSyncBlocking();
	} else if (job == JOB_SYNC_ASYNC) {
		logLine("== NTP 同步（异步版 ntp::startSyncTime） ==");
		jobSyncAsync();
	} else if (job == JOB_TIME) {
		logLine("== 读系统时间 ==");
		jobShowTime();
	} else if (job == JOB_AUTO) {
		logLine("########## 自检 AUTO 开始 ##########");
		jobShowTime();
		jobSyncBlocking();
		jobShowTime();
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

/** 构造时触发 —— 只做 UI 初始化（改时间要联网，别放这里） */
static void onUI_init() {
  #ifdef FUN_BUILD
  INIT_UI_TIMERS
  #endif // FUN_BUILD
	logLine("就绪：ntp 示例（阻塞同步 / 异步同步 / 读系统时间）");
	logLine("⚠️ 先设时区再同步：setenv(TZ=UTC-8) + tzset()");
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
static bool onButtonClick_ButtonSync(ZKButton *pButton)      { startJob(JOB_SYNC);       return true; }
static bool onButtonClick_ButtonSyncAsync(ZKButton *pButton) { startJob(JOB_SYNC_ASYNC); return true; }
static bool onButtonClick_ButtonShowTime(ZKButton *pButton)  { startJob(JOB_TIME);       return true; }
static bool onButtonClick_ButtonAuto(ZKButton *pButton) {
	if (sBusy) {
		logLine("AUTO 正在跑，忽略");
	} else {
		sErrCount = 0;
		startJob(JOB_AUTO);
	}
	return true;
}
