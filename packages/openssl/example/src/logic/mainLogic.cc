#pragma once
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#include "uart/ProtocolSender.h"

/*
 * openssl（OpenSSL 1.1.1w / Z20 变体名 "1.1.1-w"）依赖包用法示例（Z20 86 面板 / 480x480）—— **直调 TLS**
 *
 * 覆盖 API（头文件在 registry 的 include/openssl/）：
 *   SSL_CTX_new / SSL_CTX_load_verify_locations / SSL_CTX_set_verify / SSL_new / SSL_set_fd /
 *   SSL_set_tlsext_host_name(SNI) / SSL_connect / SSL_get_version / SSL_get_current_cipher /
 *   SSL_get_verify_result / SSL_get_peer_certificate / SSL_write / SSL_read / SSL_shutdown / SSL_free
 *
 * 关键口径（实测）：
 *   ① **版本号是平台专属**：Z20 = `1.1.1-w`（其它平台是 `1.1.1-g`）→ Manifest 写错就 install 不到；
 *   ② **证书校验默认开（VERIFY_PEER）但 CA 必须自己给**：不给 CA 就是连接失败（拒绝自签/链不全），不是库坏了；
 *   ③ **只发静态库**（libssl.a + libcrypto.a）→ 链接顺序 **libssl 在前、libcrypto 在后**；
 *   ④ 1.1.1 已 EOL（支持到 2023-09）→ 要 TLS1.3 新特性看 mbedtls 3.6.5 那条路线；
 *   ⑤ 1.1.1 与 3.x 的 API 不同（3.x 用 OSSL_PARAM/OSSL_LIB_CTX）→ 别照 3.x 文档写；
 *   ⑥ 本包在 Z20 上主要服务 **paho-mqtt3as（MQTT over TLS）**；用 mqtt-cxx + paho 时 Manifest 必须显式带它。
 *
 * 来源：demos/net-direct-tls-z20（第 3 个按钮 = OpenSSL 直调握手 + HTTP GET）——真机验证 ✅
 */

#include <openssl/err.h>
#include <openssl/ssl.h>
#include <openssl/x509.h>

#include <arpa/inet.h>
#include <errno.h>
#include <netdb.h>
#include <netinet/in.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

#define TLS_HOST      "www.baidu.com"
#define TLS_PORT      "443"
#define CA_PRIMARY    "/tmp/ui/cacert.pem"      /* 设备 resPath */
#define CA_BACKUP     "/mnt/extsd/cacert.pem"
#define SOCK_TIMEOUT_MS 8000

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
				LOGD("openssl demo: %s\n", line);
				li = 0;
			}
			if (*p == '\0') break;
		} else if (li < (int) sizeof(line) - 1) {
			line[li++] = *p;
		}
	}
	sPrinted = sLogLen;
}

/* ---------------- 小工具 ---------------- */
static long long nowMs() {
	struct timeval tv;
	gettimeofday(&tv, NULL);
	return (long long) tv.tv_sec * 1000 + (long long) tv.tv_usec / 1000;
}

static void setTimeoutOnFd(int fd, int ms) {
	struct timeval tv;
	tv.tv_sec = ms / 1000;
	tv.tv_usec = (ms % 1000) * 1000;
	setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
	setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
}

static const char *resolveCaPath(char *dbg, size_t dbgLen) {
	static const char *cands[3] = { CA_PRIMARY, CA_BACKUP, "cacert.pem" };
	for (int i = 0; i < 3; i++) {
		FILE *f = fopen(cands[i], "rb");
		if (f != NULL) {
			fseek(f, 0, SEEK_END);
			long sz = ftell(f);
			fclose(f);
			if (dbg != NULL) {
				snprintf(dbg, dbgLen, "%s (%ld bytes)", cands[i], sz);
			}
			return cands[i];
		}
	}
	if (dbg != NULL) {
		snprintf(dbg, dbgLen, "未找到（试过 %s / %s / ./cacert.pem）", CA_PRIMARY, CA_BACKUP);
	}
	return NULL;
}

/** 失败先看 ERR 栈（排 TLS 失败必用） */
static void reportSslError(const char *what, SSL *ssl, int rc) {
	char eb[256] = { 0 };
	unsigned long e = ERR_get_error();
	if (e != 0) {
		ERR_error_string(e, eb);
	} else {
		snprintf(eb, sizeof(eb), "(err 队列空)");
	}
	if (ssl != NULL) {
		logLine("[OPENSSL] 失败 %s: rc=%d SSL_get_error=%d %s", what, rc, SSL_get_error(ssl, rc), eb);
	} else {
		logLine("[OPENSSL] 失败 %s: rc=%d %s", what, rc, eb);
	}
}

/* ---------------- 主任务：握手（可选再发一枪 HTTP GET） ---------------- */
static void jobTls(bool doHttpGet) {
	SSL_CTX *ctx = NULL;
	SSL *ssl = NULL;
	int fd = -1;
	struct addrinfo hints, *res = NULL;
	long long t0 = nowMs();
	char caDbg[256] = { 0 };
	const char *caPath = resolveCaPath(caDbg, sizeof(caDbg));

	ERR_clear_error();
	logLine("[OPENSSL] CA 文件: %s", caDbg);

	do {
		ctx = SSL_CTX_new(TLS_client_method());
		if (ctx == NULL) {
			sErrCount++;
			logLine("[OPENSSL] SSL_CTX_new 失败");
			break;
		}
		logLine("[OPENSSL] SSL_CTX_new OK (%s)", OpenSSL_version(OPENSSL_VERSION));

		if (caPath == NULL) {
			sErrCount++;
			logLine("[OPENSSL] 找不到 CA → 请把 cacert.pem 推到 %s（不给 CA 就是连接失败，不是库坏了）", CA_PRIMARY);
			break;
		}
		if (SSL_CTX_load_verify_locations(ctx, caPath, NULL) != 1) {
			sErrCount++;
			reportSslError("SSL_CTX_load_verify_locations", NULL, 0);
			break;
		}
		SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, NULL);
		logLine("[OPENSSL] load_verify_locations OK + VERIFY_PEER");

		memset(&hints, 0, sizeof(hints));
		hints.ai_family = AF_INET;                 /* 板子上先用 IPv4，稳 */
		hints.ai_socktype = SOCK_STREAM;
		int grc = getaddrinfo(TLS_HOST, TLS_PORT, &hints, &res);
		if (grc != 0 || res == NULL) {
			sErrCount++;
			logLine("[OPENSSL] getaddrinfo 失败: %s (%d)", gai_strerror(grc), grc);
			break;
		}
		char ipstr[64] = { 0 };
		struct sockaddr_in *sin = (struct sockaddr_in *) res->ai_addr;
		inet_ntop(AF_INET, &sin->sin_addr, ipstr, (socklen_t) sizeof(ipstr));
		logLine("[OPENSSL] getaddrinfo OK: %s -> %s", TLS_HOST, ipstr);

		fd = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
		if (fd < 0) {
			sErrCount++;
			logLine("[OPENSSL] socket 失败 errno=%d", errno);
			break;
		}
		setTimeoutOnFd(fd, SOCK_TIMEOUT_MS);
		long long tc = nowMs();
		if (connect(fd, res->ai_addr, res->ai_addrlen) != 0) {
			sErrCount++;
			logLine("[OPENSSL] connect 失败 errno=%d (%dms)", errno, (int) (nowMs() - tc));
			break;
		}
		logLine("[OPENSSL] connect OK fd=%d 耗时=%dms", fd, (int) (nowMs() - tc));

		ssl = SSL_new(ctx);
		if (ssl == NULL || SSL_set_fd(ssl, fd) != 1) {
			sErrCount++;
			logLine("[OPENSSL] SSL_new/SSL_set_fd 失败");
			break;
		}
		SSL_set_tlsext_host_name(ssl, TLS_HOST);   /* SNI */
		long long th = nowMs();
		int rc = SSL_connect(ssl);
		if (rc != 1) {
			sErrCount++;
			reportSslError("SSL_connect", ssl, rc);
			logLine("[OPENSSL] 自查：① 校时了吗 ② CA 对吗（1.1.1 要自己 load_verify_locations）");
			break;
		}
		long vr = SSL_get_verify_result(ssl);
		logLine("[OPENSSL] 握手 OK 耗时=%dms 版本=%s 套件=%s verify=%s(%ld)",
				(int) (nowMs() - th), SSL_get_version(ssl),
				SSL_CIPHER_get_name(SSL_get_current_cipher(ssl)),
				(vr == X509_V_OK) ? "OK" : "FAIL", vr);

		if (!doHttpGet) {
			break;
		}

		X509 *cert = SSL_get_peer_certificate(ssl);
		if (cert != NULL) {
			char subj[512] = { 0 };
			X509_NAME_oneline(X509_get_subject_name(cert), subj, sizeof(subj));
			logLine("[OPENSSL] 服务端证书 subject: %s", subj);
			X509_free(cert);
		}
		const char *req = "GET / HTTP/1.0\r\nHost: " TLS_HOST "\r\n\r\n";
		int wn = SSL_write(ssl, req, (int) strlen(req));
		if (wn <= 0) {
			sErrCount++;
			reportSslError("SSL_write", ssl, wn);
			break;
		}
		char buf[512] = { 0 };
		int total = 0;
		long long tr = nowMs();
		while (total < (int) sizeof(buf) - 1 && (nowMs() - tr) < SOCK_TIMEOUT_MS) {
			int n = SSL_read(ssl, buf + total, (int) sizeof(buf) - 1 - total);
			if (n <= 0) {
				if (total == 0) {
					sErrCount++;
					reportSslError("SSL_read", ssl, n);
				}
				break;
			}
			total += n;
			if (total >= 16) {
				break;
			}
		}
		buf[total] = '\0';
		logLine("[OPENSSL] 收到 %d 字节 耗时=%dms", total, (int) (nowMs() - tr));
		if (total > 0) {
			char line[240] = { 0 };
			int i = 0;
			for (i = 0; i < total && i < (int) sizeof(line) - 1; i++) {
				if (buf[i] == '\r' || buf[i] == '\n') break;
				line[i] = buf[i];
			}
			line[i] = '\0';
			logLine("[OPENSSL] 首行(=HTTP 状态行): %s", line);
		}
	} while (0);

	logLine("[OPENSSL] 总计耗时=%dms", (int) (nowMs() - t0));
	if (ssl != NULL) {
		if (fd >= 0) {
			setTimeoutOnFd(fd, 300);           /* 关的时候别被 8s 超时拖住 */
		}
		SSL_shutdown(ssl);
		SSL_free(ssl);
	}
	if (fd >= 0) close(fd);
	if (res != NULL) freeaddrinfo(res);
	if (ctx != NULL) SSL_CTX_free(ctx);
}

/* ---------------- worker ---------------- */
enum { JOB_NONE = 0, JOB_HANDSHAKE, JOB_HTTPGET, JOB_AUTO };

static void *workerProc(void *arg) {
	int job = (int) (long) arg;
	if (job == JOB_HANDSHAKE) {
		logLine("== OpenSSL 握手（只握手） ==");
		jobTls(false);
	} else if (job == JOB_HTTPGET) {
		logLine("== OpenSSL 握手 + HTTP GET ==");
		jobTls(true);
	} else if (job == JOB_AUTO) {
		logLine("########## 自检 AUTO 开始 ##########");
		jobTls(false);
		jobTls(true);
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
	logLine("就绪：OpenSSL 示例（直调握手 / 握手 + HTTP GET）");
	logLine("目标 %s:%s；CA 期望在 %s", TLS_HOST, TLS_PORT, CA_PRIMARY);
	logLine("⚠️ Z20 的版本名是 1.1.1-w；其它平台是 1.1.1-g（别照抄）");
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
static bool onButtonClick_ButtonHandshake(ZKButton *pButton) { startJob(JOB_HANDSHAKE); return true; }
static bool onButtonClick_ButtonHttpGet(ZKButton *pButton)   { startJob(JOB_HTTPGET);  return true; }
static bool onButtonClick_ButtonAuto(ZKButton *pButton) {
	if (sBusy) {
		logLine("AUTO 正在跑，忽略");
	} else {
		sErrCount = 0;
		startJob(JOB_AUTO);
	}
	return true;
}
