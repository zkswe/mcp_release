#pragma once
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#include "uart/ProtocolSender.h"

/*
 * mbedtls（Mbed TLS 3.6.5）依赖包用法示例（Z20 86 面板 / 480x480）—— **直调 TLS**
 *
 * 覆盖 API（头文件在 registry 的 include/mbedtls/）：
 *   mbedtls_net_connect / mbedtls_net_send / mbedtls_net_recv / mbedtls_net_free
 *   mbedtls_ssl_config_defaults / ssl_setup / ssl_set_bio / ssl_set_hostname / ssl_conf_ca_chain /
 *   ssl_conf_authmode / ssl_conf_rng / ssl_handshake / ssl_read / ssl_write / ssl_get_version / ssl_get_ciphersuite
 *   mbedtls_x509_crt_parse_file / mbedtls_ctr_drbg_seed / mbedtls_entropy_func（+ psa_crypto_init）
 *
 * 关键口径（实测）：
 *   ① **必须自带 CA**（本包无内置 CA、不读系统信任目录）→ `cacert.pem` 放**资源目录(resPath)**；
 *      缺 CA 不是优雅报错 —— 实测过"缺 CA → 进程崩 → 看门狗反复重启"；
 *   ② 3.x 的 API 与 2.x 教程**不兼容**（`ssl_conf_rng` 的 rng 类型、entropy 回调签名都变了）→ 别照 2.x 抄；
 *   ③ 本包 TLS1.3 编进去了（`SSL_PROTO_TLS1_3=on`）→ 走 TLS1.3 路径要先 `psa_crypto_init()`（示例已调，幂等）；
 *   ④ `THREADING_C=off` → 库自身无锁，多线程共用同一个 ssl/ctr_drbg 上下文要自己加锁；
 *   ⑤ entropy 走平台默认 → 设备必须能读 `/dev/urandom`；
 *   ⑥ 只发静态库（5 个 .a）→ 链接顺序 mbedtls → mbedx509 → mbedcrypto（p256m/everest 也要带上）。
 *
 * 来源：demos/net-direct-tls-z20（第 2 个按钮 = mbedTLS 直调握手 + HTTP GET）——真机验证 ✅
 */

#include <mbedtls/ctr_drbg.h>
#include <mbedtls/entropy.h>
#include <mbedtls/error.h>
#include <mbedtls/net_sockets.h>
#include <mbedtls/ssl.h>
#include <mbedtls/x509_crt.h>
#include <psa/crypto.h>

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
#define CA_PRIMARY    "/tmp/ui/cacert.pem"      /* 设备 resPath（EasyUI.cfg 里 resPath=/tmp/ui/） */
#define CA_BACKUP     "/mnt/extsd/cacert.pem"   /* 兜底：外置卡 */
#define SOCK_TIMEOUT_MS 8000
#define TLS_TIMEOUT_MS  10000

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
				LOGD("mbedtls demo: %s\n", line);
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

/** CA 文件候选链（不同板子/不同部署位置，写死必翻车）：resPath → 外置卡 → 当前目录 */
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

static void reportError(const char *what, int code) {
	char eb[160] = { 0 };
	mbedtls_strerror(code, eb, sizeof(eb));
	logLine("[MBEDTLS] 失败 %s: -0x%04X %s", what, (unsigned int) (-code), eb);
}

/* ---------------- 主任务：握手（可选再发一枪 HTTP GET） ---------------- */
static void jobTls(bool doHttpGet) {
	mbedtls_net_context net;
	mbedtls_ssl_context ssl;
	mbedtls_ssl_config conf;
	mbedtls_x509_crt ca;
	mbedtls_ctr_drbg_context drbg;
	mbedtls_entropy_context entropy;

	mbedtls_net_init(&net);
	mbedtls_ssl_init(&ssl);
	mbedtls_ssl_config_init(&conf);
	mbedtls_x509_crt_init(&ca);
	mbedtls_ctr_drbg_init(&drbg);
	mbedtls_entropy_init(&entropy);

	int ret = 0;
	long long t0 = nowMs();
	char caDbg[256] = { 0 };
	const char *caPath = resolveCaPath(caDbg, sizeof(caDbg));
	const char *pers = "zk-demo-mbedtls";
	logLine("[MBEDTLS] CA 文件: %s", caDbg);

	do {
		/* 3.x 的 TLS1.3 路径走 PSA：先显式初始化一次（幂等） */
		psa_status_t pst = psa_crypto_init();
		logLine("[MBEDTLS] psa_crypto_init -> %d", (int) pst);

		ret = mbedtls_ctr_drbg_seed(&drbg, mbedtls_entropy_func, &entropy,
				(const unsigned char *) pers, strlen(pers));
		if (ret != 0) {
			reportError("mbedtls_ctr_drbg_seed", ret);
			sErrCount++;
			logLine("[MBEDTLS] 自查：设备能读 /dev/urandom 吗（entropy 走平台默认）");
			break;
		}

		if (caPath == NULL) {
			sErrCount++;
			logLine("[MBEDTLS] 找不到 CA → 无法 REQUIRED 校验；请把 cacert.pem 推到 %s", CA_PRIMARY);
			break;
		}
		ret = mbedtls_x509_crt_parse_file(&ca, caPath);
		if (ret != 0) {
			reportError("mbedtls_x509_crt_parse_file", ret);
			sErrCount++;
			break;
		}
		logLine("[MBEDTLS] x509_crt_parse_file OK (%s)", caPath);

		ret = mbedtls_net_connect(&net, TLS_HOST, TLS_PORT, MBEDTLS_NET_PROTO_TCP);
		if (ret != 0) {
			reportError("mbedtls_net_connect", ret);
			sErrCount++;
			break;
		}
		setTimeoutOnFd(net.fd, SOCK_TIMEOUT_MS);
		logLine("[MBEDTLS] net_connect(%s:%s) OK, fd=%d", TLS_HOST, TLS_PORT, net.fd);

		ret = mbedtls_ssl_config_defaults(&conf, MBEDTLS_SSL_IS_CLIENT,
				MBEDTLS_SSL_TRANSPORT_STREAM, MBEDTLS_SSL_PRESET_DEFAULT);
		if (ret != 0) {
			reportError("mbedtls_ssl_config_defaults", ret);
			sErrCount++;
			break;
		}
		mbedtls_ssl_conf_authmode(&conf, MBEDTLS_SSL_VERIFY_REQUIRED);   /* 默认就是 REQUIRED */
		mbedtls_ssl_conf_ca_chain(&conf, &ca, NULL);
		mbedtls_ssl_conf_rng(&conf, mbedtls_ctr_drbg_random, &drbg);

		ret = mbedtls_ssl_setup(&ssl, &conf);
		if (ret != 0) {
			reportError("mbedtls_ssl_setup", ret);
			sErrCount++;
			break;
		}
		ret = mbedtls_ssl_set_hostname(&ssl, TLS_HOST);    /* SNI + 证书域名校验（REQUIRED 必须有） */
		if (ret != 0) {
			reportError("mbedtls_ssl_set_hostname", ret);
			sErrCount++;
			break;
		}
		mbedtls_ssl_set_bio(&ssl, &net, mbedtls_net_send, mbedtls_net_recv, NULL);

		long long th = nowMs();
		do {                                               /* WANT_READ/WANT_WRITE 时小睡重试，总超时 10s */
			ret = mbedtls_ssl_handshake(&ssl);
			if (ret == MBEDTLS_ERR_SSL_WANT_READ || ret == MBEDTLS_ERR_SSL_WANT_WRITE) {
				usleep(50 * 1000);
			}
		} while ((ret == MBEDTLS_ERR_SSL_WANT_READ || ret == MBEDTLS_ERR_SSL_WANT_WRITE)
				&& (nowMs() - th) < TLS_TIMEOUT_MS);
		if (ret != 0) {
			reportError("mbedtls_ssl_handshake", ret);
			sErrCount++;
			logLine("[MBEDTLS] 自查：① 校时了吗（RTC=1970 → certificate validity starts in the future）"
					" ② CA 对吗（not correctly signed by the trusted CA = CA 没找到/用错）");
			break;
		}
		logLine("[MBEDTLS] 握手 OK 耗时=%dms 版本=%s 套件=%s",
				(int) (nowMs() - th), mbedtls_ssl_get_version(&ssl), mbedtls_ssl_get_ciphersuite(&ssl));

		if (!doHttpGet) {
			mbedtls_ssl_close_notify(&ssl);
			break;
		}

		const char *req = "GET / HTTP/1.0\r\nHost: " TLS_HOST "\r\n\r\n";
		ret = mbedtls_ssl_write(&ssl, (const unsigned char *) req, strlen(req));
		if (ret <= 0) {
			reportError("mbedtls_ssl_write", ret);
			sErrCount++;
			break;
		}
		char buf[512] = { 0 };
		int total = 0;
		long long tr = nowMs();
		while (total < (int) sizeof(buf) - 1 && (nowMs() - tr) < SOCK_TIMEOUT_MS) {
			int n = mbedtls_ssl_read(&ssl, (unsigned char *) buf + total, sizeof(buf) - 1 - total);
			if (n == MBEDTLS_ERR_SSL_WANT_READ || n == MBEDTLS_ERR_SSL_WANT_WRITE) {
				usleep(50 * 1000);
				continue;
			}
			if (n <= 0) {
				if (total == 0) {
					reportError("mbedtls_ssl_read", n);
					sErrCount++;
				}
				break;
			}
			total += n;
			if (total >= 16) {
				break;                                     /* 拿到状态行+部分头就够 */
			}
		}
		buf[total] = '\0';
		logLine("[MBEDTLS] 收到 %d 字节 耗时=%dms", total, (int) (nowMs() - tr));
		if (total > 0) {
			char line[240] = { 0 };
			int i = 0;
			for (i = 0; i < total && i < (int) sizeof(line) - 1; i++) {
				if (buf[i] == '\r' || buf[i] == '\n') break;
				line[i] = buf[i];
			}
			line[i] = '\0';
			logLine("[MBEDTLS] 首行(=HTTP 状态行): %s", line);
		} else {
			sErrCount++;
		}
	} while (0);

	logLine("[MBEDTLS] 总计耗时=%dms", (int) (nowMs() - t0));
	mbedtls_net_free(&net);
	mbedtls_ssl_free(&ssl);
	mbedtls_ssl_config_free(&conf);
	mbedtls_x509_crt_free(&ca);
	mbedtls_ctr_drbg_free(&drbg);
	mbedtls_entropy_free(&entropy);
}

/* ---------------- worker ---------------- */
enum { JOB_NONE = 0, JOB_HANDSHAKE, JOB_HTTPGET, JOB_AUTO };

static void *workerProc(void *arg) {
	int job = (int) (long) arg;
	if (job == JOB_HANDSHAKE) {
		logLine("== mbedTLS 握手（只握手，不发请求） ==");
		jobTls(false);
	} else if (job == JOB_HTTPGET) {
		logLine("== mbedTLS 握手 + HTTP GET ==");
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
	logLine("就绪：mbedTLS 示例（直调握手 / 握手 + HTTP GET）");
	logLine("目标 %s:%s；CA 期望在 %s", TLS_HOST, TLS_PORT, CA_PRIMARY);
	logLine("⚠️ 上机前把 cacert.pem 推到资源目录（resPath）");
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
