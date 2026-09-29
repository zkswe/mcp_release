#pragma once
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#include "uart/ProtocolSender.h"

/*
 * cares（c-ares 异步 DNS）依赖包用法示例（Z20 86 面板 / 480x480）
 *
 * 覆盖 API（头文件在 registry 的 include/）：
 *   ares_library_init / ares_init / ares_gethostbyname / ares_fds / ares_timeout / ares_process_fd / ares_destroy
 *
 * 关键口径（都是实测踩出来的）：
 *   ① 本包**只有静态库**（没有 .so）；ares_* **不自己开线程** → 必须自己 select 驱动事件循环；
 *   ② 依赖设备的 **/etc/resolv.conf**（`ares_init(&ch)` 传空 options 时读它）；
 *   ③ `ares_library_init` 在 POSIX 上近似 no-op：**返回非 0 不判失败**；
 *   ④ 回调里的 `struct hostent` / 字符串归 ares 所有 → 用完 `ares_free_hostent()` / `ares_free_string()`；
 *   ⑤ Z20 的 curl 的 resolver 就是 c-ares → 业务一般不用直接调它，要自己取消/异步解析才用。
 *
 * 来源：demos/net-direct-tls-z20（第 1 个按钮 = 单域名解析，第 4 个 = 5 域名批量测速）——真机验证 ✅
 */

#include <ares.h>

#include <arpa/inet.h>
#include <errno.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/types.h>
#include <unistd.h>

#define DNS_TIMEOUT_MS 5000      /* 单域名超时 */

static const char *kBenchList[] = {
	"www.baidu.com", "www.qq.com", "www.taobao.com", "github.com", "www.zkswe.com",
};
#define BENCH_N ((int) (sizeof(kBenchList) / sizeof(kBenchList[0])))

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
				LOGD("cares demo: %s\n", line);
				li = 0;
			}
			if (*p == '\0') break;
		} else if (li < (int) sizeof(line) - 1) {
			line[li++] = *p;
		}
	}
	sPrinted = sLogLen;
}

static long long nowMs() {
	struct timeval tv;
	gettimeofday(&tv, NULL);
	return (long long) tv.tv_sec * 1000 + (long long) tv.tv_usec / 1000;
}

/* ---------------- 解析回调（ares 事件循环里跑：只记结果，别动 UI） ---------------- */
static volatile int sDnsDone = 0;
static volatile int sDnsStatus = -1;
static volatile int sDnsTimeouts = 0;
static char sDnsIp[64] = { 0 };

static void onDnsDone(void *arg, int status, int timeouts, struct hostent *hostent) {
	(void) arg;
	sDnsStatus = status;
	sDnsTimeouts = timeouts;
	sDnsIp[0] = '\0';
	if (status == ARES_SUCCESS && hostent != NULL && hostent->h_addr_list != NULL
			&& hostent->h_addr_list[0] != NULL && hostent->h_addrtype == AF_INET) {
		if (inet_ntop(AF_INET, hostent->h_addr_list[0], sDnsIp, (socklen_t) sizeof(sDnsIp)) == NULL) {
			sDnsIp[0] = '\0';
		}
	}
	/* ⚠️ hostent 归 ares 所有：要延后使用就得 ares_free_hostent() 而不是 free() */
	sDnsDone = 1;
}

/** 阻塞式解析一个域名：内部跑 ares_fds → select → ares_process_fd 事件循环 */
static int resolveOne(ares_channel ch, const char *name, char *ipOut, size_t ipOutSize,
		int *elapsedMs, int *timedOut) {
	sDnsDone = 0;
	sDnsStatus = -1;
	sDnsTimeouts = 0;
	sDnsIp[0] = '\0';

	ares_gethostbyname(ch, name, AF_INET, onDnsDone, NULL);
	long long t0 = nowMs();
	*elapsedMs = 0;
	*timedOut = 0;

	while (sDnsDone == 0) {
		fd_set rd, wr;
		FD_ZERO(&rd);
		FD_ZERO(&wr);
		int nfds = ares_fds(ch, &rd, &wr);
		if (nfds == 0) {
			usleep(20 * 1000);                 /* 没有待处理 fd：小睡一下再看超时 */
		} else {
			struct timeval tv;
			tv.tv_sec = 0;
			tv.tv_usec = 100 * 1000;
			int rc = select(nfds, &rd, &wr, NULL, &tv);
			if (rc > 0) {
				for (int fd = 0; fd < nfds; fd++) {
					ares_socket_t rf = ARES_SOCKET_BAD, wf = ARES_SOCKET_BAD;
					if (FD_ISSET(fd, &rd)) rf = (ares_socket_t) fd;
					if (FD_ISSET(fd, &wr)) wf = (ares_socket_t) fd;
					if (rf != ARES_SOCKET_BAD || wf != ARES_SOCKET_BAD) {
						ares_process_fd(ch, rf, wf);
					}
				}
			} else if (rc == 0) {
				ares_process_fd(ch, ARES_SOCKET_BAD, ARES_SOCKET_BAD);   /* 喂 0 让 ares 走重传/超时 */
			} else if (errno != EINTR) {
				ares_process_fd(ch, ARES_SOCKET_BAD, ARES_SOCKET_BAD);
			}
		}
		*elapsedMs = (int) (nowMs() - t0);
		if (*elapsedMs > DNS_TIMEOUT_MS) {
			*timedOut = 1;
			break;
		}
	}
	if (*elapsedMs == 0) {
		*elapsedMs = (int) (nowMs() - t0);
	}
	if (ipOut != NULL && ipOutSize > 0) {
		snprintf(ipOut, ipOutSize, "%s", sDnsIp);
	}
	return sDnsStatus;
}

/* ---------------- 各任务 ---------------- */
static void jobResolve() {
	int rc = ares_library_init(ARES_LIB_INIT_ALL);
	logLine("[CARES] ares_library_init -> %d (%s)（POSIX 上近似 no-op，非 0 不判失败）", rc, ares_strerror(rc));

	ares_channel ch = NULL;
	rc = ares_init(&ch);                       /* 空 options → 读 /etc/resolv.conf */
	if (rc != ARES_SUCCESS || ch == NULL) {
		sErrCount++;
		logLine("[CARES] ares_init 失败: %d (%s)", rc, ares_strerror(rc));
		return;
	}
	logLine("[CARES] ares_init OK，开始 ares_gethostbyname(www.baidu.com, AF_INET)");

	char ip[64] = { 0 };
	int elapsed = 0, timedOut = 0;
	int st = resolveOne(ch, "www.baidu.com", ip, sizeof(ip), &elapsed, &timedOut);
	logLine("[CARES] status=%d (%s) ip=%s 耗时=%dms timeouts=%d",
			st, ares_strerror(st), ip[0] ? ip : "(无)", elapsed, sDnsTimeouts);
	if (st == ARES_SUCCESS && ip[0] != '\0' && !timedOut) {
		logLine("[CARES] OK: www.baidu.com -> %s", ip);
	} else {
		sErrCount++;
		logLine("[CARES] FAIL（status=%d%s）", st, timedOut ? ", 事件循环 5s 超时" : "");
	}
	ares_destroy(ch);
}

static void jobDnsBench() {
	int rc = ares_library_init(ARES_LIB_INIT_ALL);
	logLine("[DNS] ares_library_init -> %d", rc);
	ares_channel ch = NULL;
	rc = ares_init(&ch);
	if (rc != ARES_SUCCESS || ch == NULL) {
		sErrCount++;
		logLine("[DNS] ares_init 失败: %d (%s)", rc, ares_strerror(rc));
		return;
	}
	int ok = 0;
	for (int i = 0; i < BENCH_N; i++) {
		char ip[64] = { 0 };
		int elapsed = 0, timedOut = 0;
		int st = resolveOne(ch, kBenchList[i], ip, sizeof(ip), &elapsed, &timedOut);
		logLine("[DNS] %d/%d %-16s -> %-16s %4dms status=%d(%s)%s",
				i + 1, BENCH_N, kBenchList[i], ip[0] ? ip : "(无)", elapsed,
				st, ares_strerror(st), timedOut ? " [超时]" : "");
		if (st == ARES_SUCCESS && ip[0] != '\0') {
			ok++;
		}
	}
	logLine("[DNS] 完成：成功 %d/%d", ok, BENCH_N);
	if (ok != BENCH_N) {
		sErrCount++;
	}
	ares_destroy(ch);
}

/* ---------------- worker ---------------- */
enum { JOB_NONE = 0, JOB_RESOLVE, JOB_BENCH, JOB_AUTO };

static void *workerProc(void *arg) {
	int job = (int) (long) arg;
	if (job == JOB_RESOLVE) {
		logLine("== c-ares 单域名解析 ==");
		jobResolve();
	} else if (job == JOB_BENCH) {
		logLine("== c-ares 5 域名批量测速 ==");
		jobDnsBench();
	} else if (job == JOB_AUTO) {
		logLine("########## 自检 AUTO 开始 ##########");
		jobResolve();
		jobDnsBench();
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
	logLine("就绪：c-ares 示例（单域名解析 / 5 域名批量测速）");
	logLine("⚠️ 解析走设备 /etc/resolv.conf；resolver 也可是 curl 的 DNS 后端（业务一般不用直调）");
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
static bool onButtonClick_ButtonResolve(ZKButton *pButton)  { startJob(JOB_RESOLVE); return true; }
static bool onButtonClick_ButtonDnsBench(ZKButton *pButton) { startJob(JOB_BENCH);   return true; }
static bool onButtonClick_ButtonAuto(ZKButton *pButton) {
	if (sBusy) {
		logLine("AUTO 正在跑，忽略");
	} else {
		sErrCount = 0;
		startJob(JOB_AUTO);
	}
	return true;
}
