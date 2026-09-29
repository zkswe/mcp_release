#pragma once
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#include "uart/ProtocolSender.h"

/*
 * 底层网络库「直调」验证（Z20 86 面板 / 480x480）
 *
 *   1) ButtonCares   : c-ares 直调 DNS —— ares_library_init / ares_init / ares_gethostbyname
 *                      + ares_fds + select + ares_process_fd 事件循环（超时 5s）
 *   2) ButtonMbedtls : mbedTLS 直调 TLS 握手 + HTTP GET（mbedtls_net_* + mbedtls_ssl_* + mbedtls_x509_crt_parse_file）
 *   3) ButtonOpenssl : OpenSSL 直调 TLS 握手 + HTTP GET（socket/getaddrinfo/connect + SSL_CTX_xx 与 SSL_xx）
 *   4) ButtonDnsBench: c-ares 连解 5 个域名，打印每个的耗时 ms + IP
 *   5) ButtonAuto    : 顺序跑 1→2→3→4，末尾打印「错误数=N」
 *
 * 设计约定（沿用骨架）：
 *   - 所有网络/阻塞调用都在 worker 线程（startJob → pthread_create + detach），UI 线程只刷日志；
 *   - 日志全部走 logLine()（worker 侧加锁追加）+ flushLog()（UI 线程 200ms 定时器刷 textview + logcat 单行）；
 *   - logcat 不能带换行（会截断），flushLog 已按行拆成单行 LOGD；
 *   - 每条日志以 [CARES] / [MBEDTLS] / [OPENSSL] / [DNS] 开头，便于 adb logcat 过滤。
 *
 * 平台：Z20（SD20X）+ GCC 8.3 arm-pc-linux-gnueabihf（-Werror=format / -Werror=format-truncation 敏感，
 *       所以 snprintf 一律传 sizeof(buf)，不写 sizeof(buf)-1）。
 */

#include <ares.h>

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#include <mbedtls/ctr_drbg.h>
#include <mbedtls/entropy.h>
#include <mbedtls/error.h>
#include <mbedtls/net_sockets.h>
#include <mbedtls/ssl.h>
#include <mbedtls/x509_crt.h>
#include <psa/crypto.h>

#include <openssl/err.h>
#include <openssl/ssl.h>
#include <openssl/tls1.h>
#include <openssl/x509.h>

/* ---------------- 目标与常量 ---------------- */
#define ND_HOST        "www.baidu.com"
#define ND_PORT_STR    "443"
#define ND_CA_PRIMARY  "/tmp/ui/cacert.pem"    /* 设备 resPath（EasyUI.cfg 里 resPath=/tmp/ui/） */
#define ND_CA_BACKUP   "/mnt/extsd/cacert.pem"

#define ND_DNS_TIMEOUT_MS   5000     /* 单域名 DNS 超时 */
#define ND_TLS_TIMEOUT_MS   10000    /* 握手总超时 */
#define ND_SOCK_TIMEOUT_MS  8000     /* socket 收发超时 */

static const char *kDnsBenchList[] = {
	"www.baidu.com",
	"www.qq.com",
	"www.taobao.com",
	"github.com",
	"www.zkswe.com",
};
#define ND_DNS_BENCH_N ((int) (sizeof(kDnsBenchList) / sizeof(kDnsBenchList[0])))

/* ---------------- 线程安全日志（worker 写，UI 线程刷） ---------------- */
static char sLog[8000];
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
	char snapshot[8000] = { 0 };
	pthread_mutex_lock(&sLogMx);
	memcpy(snapshot, sLog, sizeof(snapshot) - 1);
	pthread_mutex_unlock(&sLogMx);
	char *newpart = snapshot + sPrinted;
	const char *show = newpart;
	if (strlen(newpart) > 1100) {
		show = newpart + (strlen(newpart) - 1100);
	}
	if (mTextStatusPtr != NULL) {
		mTextStatusPtr->setText(show);
	}
	char line[640] = { 0 };
	int li = 0;
	for (const char *p = newpart; ; p++) {
		if (*p == '\n' || *p == '\0') {
			if (li > 0) {
				line[li] = '\0';
				LOGD("netdir demo: %s\n", line);
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

/** 找 CA 文件：优先 /tmp/ui/cacert.pem（resPath），其次 /mnt/extsd，最后当前目录 */
static const char *resolveCaPath(char *dbg, size_t dbgLen) {
	static const char *cands[3] = { ND_CA_PRIMARY, ND_CA_BACKUP, "cacert.pem" };
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
		snprintf(dbg, dbgLen, "未找到（试过 %s / %s / ./cacert.pem）", ND_CA_PRIMARY, ND_CA_BACKUP);
	}
	return NULL;
}

/** 取响应的第一行（HTTP 状态行）打印 */
static void logFirstLine(const char *tag, const char *buf, int len) {
	char line[240] = { 0 };
	int i = 0;
	for (i = 0; i < len && i < (int) sizeof(line) - 1; i++) {
		if (buf[i] == '\r' || buf[i] == '\n') {
			break;
		}
		line[i] = buf[i];
	}
	line[i] = '\0';
	logLine("[%s] 首行(=HTTP 状态行): %s", tag, line);
}

/* =======================================================================
 *  1) c-ares 直调 DNS
 * ======================================================================= */
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
	sDnsDone = 1;
}

/**
 * 阻塞式解析一个域名（内部跑 ares_fds + select + ares_process_fd 事件循环）
 * 返回 ares 状态码；ipOut 里是点分十进制（失败为空串）
 */
static int caresResolveOne(ares_channel channel, const char *name, char *ipOut, size_t ipOutSize,
		int *elapsedMs, int *timedOutFlag) {
	sDnsDone = 0;
	sDnsStatus = -1;
	sDnsTimeouts = 0;
	sDnsIp[0] = '\0';

	ares_gethostbyname(channel, name, AF_INET, onDnsDone, NULL);

	long long t0 = nowMs();
	*elapsedMs = 0;
	*timedOutFlag = 0;
	while (sDnsDone == 0) {
		fd_set readers, writers;
		FD_ZERO(&readers);
		FD_ZERO(&writers);
		int nfds = ares_fds(channel, &readers, &writers);
		if (nfds == 0) {
			/* 没有待处理的 fd：等一小会再看超时 */
			usleep(20 * 1000);
		} else {
			struct timeval tv;
			tv.tv_sec = 0;
			tv.tv_usec = 100 * 1000;
			int rc = select(nfds, &readers, &writers, NULL, &tv);
			if (rc > 0) {
				for (int fd = 0; fd < nfds; fd++) {
					ares_socket_t rf = ARES_SOCKET_BAD;
					ares_socket_t wf = ARES_SOCKET_BAD;
					if (FD_ISSET(fd, &readers)) {
						rf = (ares_socket_t) fd;
					}
					if (FD_ISSET(fd, &writers)) {
						wf = (ares_socket_t) fd;
					}
					if (rf != ARES_SOCKET_BAD || wf != ARES_SOCKET_BAD) {
						ares_process_fd(channel, rf, wf);
					}
				}
			} else if (rc == 0) {
				/* 超时：喂 0 timeout 让 c-ares 自己走重传/超时逻辑 */
				ares_process_fd(channel, ARES_SOCKET_BAD, ARES_SOCKET_BAD);
			} else {
				if (errno != EINTR) {
					ares_process_fd(channel, ARES_SOCKET_BAD, ARES_SOCKET_BAD);
				}
			}
		}
		*elapsedMs = (int) (nowMs() - t0);
		if (*elapsedMs > ND_DNS_TIMEOUT_MS) {
			*timedOutFlag = 1;
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

static void jobCares() {
	int rc = ares_library_init(ARES_LIB_INIT_ALL);
	/* POSIX 上 c-ares 的 library_init 基本是 no-op，返回非 0 也继续（只记录） */
	logLine("[CARES] ares_library_init(ARES_LIB_INIT_ALL) -> %d (%s)", rc, ares_strerror(rc));

	ares_channel channel = NULL;
	rc = ares_init(&channel);
	if (rc != ARES_SUCCESS || channel == NULL) {
		sErrCount++;
		logLine("[CARES] ares_init 失败: %d (%s)", rc, ares_strerror(rc));
		return;
	}
	logLine("[CARES] ares_init OK, 开始 ares_gethostbyname(%s, AF_INET)", ND_HOST);

	char ip[64] = { 0 };
	int elapsed = 0, timedOut = 0;
	int status = caresResolveOne(channel, ND_HOST, ip, sizeof(ip), &elapsed, &timedOut);

	logLine("[CARES] 解析结果 status=%d (%s) ip=%s 耗时=%dms timeouts=%d",
			status, ares_strerror(status), ip[0] ? ip : "(无)", elapsed, sDnsTimeouts);
	if (status == ARES_SUCCESS && ip[0] != '\0' && timedOut == 0) {
		logLine("[CARES] OK: %s -> %s", ND_HOST, ip);
	} else {
		sErrCount++;
		logLine("[CARES] FAIL: %s (status=%d%s)", ND_HOST, status, timedOut ? ", 事件循环 5s 超时" : "");
	}
	ares_destroy(channel);
}

/* =======================================================================
 *  2) mbedTLS 直调 TLS 握手 + HTTP GET
 * ======================================================================= */
static void reportMbedError(const char *what, int code) {
	char eb[160] = { 0 };
	mbedtls_strerror(code, eb, sizeof(eb));
	logLine("[MBEDTLS] 失败 %s: -0x%04X %s", what, (unsigned int) (-code), eb);
}

static void jobMbedtls() {
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
	const char *pers = "zk-netdir-mbedtls";

	logLine("[MBEDTLS] CA 文件: %s", caDbg);

	do {
		/* mbedtls 3.x 的 TLS1.3 路径走 PSA，先显式初始化一次（幂等） */
		psa_status_t pst = psa_crypto_init();
		logLine("[MBEDTLS] psa_crypto_init -> %d", (int) pst);

		ret = mbedtls_ctr_drbg_seed(&drbg, mbedtls_entropy_func, &entropy,
				(const unsigned char *) pers, strlen(pers));
		if (ret != 0) {
			reportMbedError("mbedtls_ctr_drbg_seed", ret);
			sErrCount++;
			break;
		}
		logLine("[MBEDTLS] ctr_drbg_seed OK");

		if (caPath == NULL) {
			sErrCount++;
			logLine("[MBEDTLS] 找不到 CA 文件，无法 REQUIRED 校验证书，请把 cacert.pem 推到 %s", ND_CA_PRIMARY);
			break;
		}
		ret = mbedtls_x509_crt_parse_file(&ca, caPath);
		if (ret != 0) {
			reportMbedError("mbedtls_x509_crt_parse_file", ret);
			sErrCount++;
			break;
		}
		logLine("[MBEDTLS] x509_crt_parse_file OK (%s)", caPath);

		ret = mbedtls_net_connect(&net, ND_HOST, ND_PORT_STR, MBEDTLS_NET_PROTO_TCP);
		if (ret != 0) {
			reportMbedError("mbedtls_net_connect", ret);
			sErrCount++;
			break;
		}
		setTimeoutOnFd(net.fd, ND_SOCK_TIMEOUT_MS);
		logLine("[MBEDTLS] net_connect(%s:%s) OK, fd=%d", ND_HOST, ND_PORT_STR, net.fd);

		ret = mbedtls_ssl_config_defaults(&conf, MBEDTLS_SSL_IS_CLIENT,
				MBEDTLS_SSL_TRANSPORT_STREAM, MBEDTLS_SSL_PRESET_DEFAULT);
		if (ret != 0) {
			reportMbedError("mbedtls_ssl_config_defaults", ret);
			sErrCount++;
			break;
		}
		mbedtls_ssl_conf_authmode(&conf, MBEDTLS_SSL_VERIFY_REQUIRED);
		mbedtls_ssl_conf_ca_chain(&conf, &ca, NULL);
		mbedtls_ssl_conf_rng(&conf, mbedtls_ctr_drbg_random, &drbg);

		ret = mbedtls_ssl_setup(&ssl, &conf);
		if (ret != 0) {
			reportMbedError("mbedtls_ssl_setup", ret);
			sErrCount++;
			break;
		}
		ret = mbedtls_ssl_set_hostname(&ssl, ND_HOST);   /* REQUIRED 必须有 hostname，否则拒握手 */
		if (ret != 0) {
			reportMbedError("mbedtls_ssl_set_hostname", ret);
			sErrCount++;
			break;
		}
		mbedtls_ssl_set_bio(&ssl, &net, mbedtls_net_send, mbedtls_net_recv, NULL);

		/* 握手（WANT_READ/WANT_WRITE 时小睡重试，总超时 10s） */
		long long th = nowMs();
		do {
			ret = mbedtls_ssl_handshake(&ssl);
			if (ret == MBEDTLS_ERR_SSL_WANT_READ || ret == MBEDTLS_ERR_SSL_WANT_WRITE) {
				usleep(50 * 1000);
			}
		} while ((ret == MBEDTLS_ERR_SSL_WANT_READ || ret == MBEDTLS_ERR_SSL_WANT_WRITE)
				&& (nowMs() - th) < ND_TLS_TIMEOUT_MS);

		if (ret != 0) {
			reportMbedError("mbedtls_ssl_handshake", ret);
			sErrCount++;
			break;
		}
		logLine("[MBEDTLS] 握手 OK 耗时=%dms 版本=%s 套件=%s", (int) (nowMs() - th),
				mbedtls_ssl_get_version(&ssl), mbedtls_ssl_get_ciphersuite(&ssl));

		/* 服务端证书 subject */
		const mbedtls_x509_crt *peer = mbedtls_ssl_get_peer_cert(&ssl);
		if (peer == NULL) {
			logLine("[MBEDTLS] 服务端证书: (NULL)");
		} else {
			char info[512] = { 0 };
			int n = mbedtls_x509_crt_info(info, sizeof(info), "  ", peer);
			char subj[256] = { 0 };
			int k = 0;
			for (int i = 0; i < n && i < (int) sizeof(subj) - 1; i++) {
				if (info[i] != '\r' && info[i] != '\n') {
					subj[k++] = info[i];
				} else if (k > 0 && subj[k - 1] != ' ') {
					subj[k++] = ' ';
				}
			}
			subj[k] = '\0';
			logLine("[MBEDTLS] 服务端证书: %s", subj);
		}

		/* 发 HTTP GET，读回状态行 */
		const char *req = "GET / HTTP/1.0\r\nHost: " ND_HOST "\r\n\r\n";
		ret = mbedtls_ssl_write(&ssl, (const unsigned char *) req, strlen(req));
		if (ret <= 0) {
			reportMbedError("mbedtls_ssl_write", ret);
			sErrCount++;
			break;
		}
		logLine("[MBEDTLS] 已发送 GET 请求 %d 字节", ret);

		char buf[512] = { 0 };
		int total = 0;
		long long tr = nowMs();
		while (total < (int) sizeof(buf) - 1 && (nowMs() - tr) < ND_SOCK_TIMEOUT_MS) {
			int n = mbedtls_ssl_read(&ssl, (unsigned char *) buf + total, sizeof(buf) - 1 - total);
			if (n == MBEDTLS_ERR_SSL_WANT_READ || n == MBEDTLS_ERR_SSL_WANT_WRITE) {
				usleep(50 * 1000);
				continue;
			}
			if (n <= 0) {
				if (total == 0) {
					reportMbedError("mbedtls_ssl_read", n);
					sErrCount++;
				}
				break;
			}
			total += n;
			if (total >= 16) {
				break;      /* 拿到状态行+部分头就够了 */
			}
		}
		buf[total] = '\0';
		logLine("[MBEDTLS] 收到 %d 字节 耗时=%dms", total, (int) (nowMs() - tr));
		if (total > 0) {
			logFirstLine("MBEDTLS", buf, total);
		} else {
			sErrCount++;
			logLine("[MBEDTLS] FAIL: 没读到数据");
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

/* =======================================================================
 *  3) OpenSSL 直调 TLS 握手 + HTTP GET
 * ======================================================================= */
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

static void jobOpenssl() {
	SSL_CTX *ctx = NULL;
	SSL *ssl = NULL;
	int fd = -1;
	struct addrinfo hints;
	struct addrinfo *res = NULL;
	long long t0 = nowMs();
	char caDbg[256] = { 0 };
	const char *caPath = resolveCaPath(caDbg, sizeof(caDbg));

	ERR_clear_error();
	logLine("[OPENSSL] CA 文件: %s", caDbg);

	do {
		ctx = SSL_CTX_new(TLS_client_method());
		if (ctx == NULL) {
			sErrCount++;
			logLine("[OPENSSL] SSL_CTX_new(TLS_client_method()) 失败");
			break;
		}
		logLine("[OPENSSL] SSL_CTX_new OK (OpenSSL %s)", OpenSSL_version(OPENSSL_VERSION));

		if (caPath == NULL) {
			sErrCount++;
			logLine("[OPENSSL] 找不到 CA 文件，跳过校验（请把 cacert.pem 推到 %s）", ND_CA_PRIMARY);
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
		hints.ai_family = AF_INET;              /* Z20 上先用 IPv4，稳 */
		hints.ai_socktype = SOCK_STREAM;
		int grc = getaddrinfo(ND_HOST, ND_PORT_STR, &hints, &res);
		if (grc != 0 || res == NULL) {
			sErrCount++;
			logLine("[OPENSSL] getaddrinfo 失败: %s (%d)", gai_strerror(grc), grc);
			break;
		}
		char ipstr[64] = { 0 };
		struct sockaddr_in *sin = (struct sockaddr_in *) res->ai_addr;
		inet_ntop(AF_INET, &sin->sin_addr, ipstr, (socklen_t) sizeof(ipstr));
		logLine("[OPENSSL] getaddrinfo OK: %s -> %s", ND_HOST, ipstr);

		fd = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
		if (fd < 0) {
			sErrCount++;
			logLine("[OPENSSL] socket 失败: errno=%d %s", errno, strerror(errno));
			break;
		}
		setTimeoutOnFd(fd, ND_SOCK_TIMEOUT_MS);

		long long tc = nowMs();
		if (connect(fd, res->ai_addr, res->ai_addrlen) != 0) {
			sErrCount++;
			logLine("[OPENSSL] connect 失败: errno=%d %s (%dms)", errno, strerror(errno), (int) (nowMs() - tc));
			break;
		}
		logLine("[OPENSSL] connect OK fd=%d 耗时=%dms", fd, (int) (nowMs() - tc));

		ssl = SSL_new(ctx);
		if (ssl == NULL) {
			sErrCount++;
			logLine("[OPENSSL] SSL_new 失败");
			break;
		}
		if (SSL_set_fd(ssl, fd) != 1) {
			sErrCount++;
			logLine("[OPENSSL] SSL_set_fd 失败");
			break;
		}
		SSL_set_tlsext_host_name(ssl, ND_HOST);      /* SNI */

		long long th = nowMs();
		int rc = SSL_connect(ssl);
		if (rc != 1) {
			sErrCount++;
			reportSslError("SSL_connect", ssl, rc);
			break;
		}
		long vr = SSL_get_verify_result(ssl);
		logLine("[OPENSSL] 握手 OK 耗时=%dms 版本=%s 套件=%s verify=%s(%ld)",
				(int) (nowMs() - th), SSL_get_version(ssl),
				SSL_CIPHER_get_name(SSL_get_current_cipher(ssl)),
				(vr == X509_V_OK) ? "OK" : "FAIL", vr);

		X509 *cert = SSL_get_peer_certificate(ssl);
		if (cert == NULL) {
			logLine("[OPENSSL] 服务端证书: (NULL)");
		} else {
			char subj[512] = { 0 };
			X509_NAME_oneline(X509_get_subject_name(cert), subj, sizeof(subj));
			logLine("[OPENSSL] 服务端证书 subject: %s", subj);
			X509_free(cert);
		}

		const char *req = "GET / HTTP/1.0\r\nHost: " ND_HOST "\r\n\r\n";
		int wn = SSL_write(ssl, req, (int) strlen(req));
		if (wn <= 0) {
			sErrCount++;
			reportSslError("SSL_write", ssl, wn);
			break;
		}
		logLine("[OPENSSL] 已发送 GET 请求 %d 字节", wn);

		char buf[512] = { 0 };
		int total = 0;
		long long tr = nowMs();
		while (total < (int) sizeof(buf) - 1 && (nowMs() - tr) < ND_SOCK_TIMEOUT_MS) {
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
			logFirstLine("OPENSSL", buf, total);
		}
	} while (0);

	logLine("[OPENSSL] 总计耗时=%dms", (int) (nowMs() - t0));
	if (ssl != NULL) {
		if (fd >= 0) {
			setTimeoutOnFd(fd, 300);      /* 关掉时别被 8s 超时拖住 */
		}
		SSL_shutdown(ssl);
		SSL_free(ssl);
	}
	if (fd >= 0) {
		close(fd);
	}
	if (res != NULL) {
		freeaddrinfo(res);
	}
	if (ctx != NULL) {
		SSL_CTX_free(ctx);
	}
}

/* =======================================================================
 *  4) c-ares DNS 批量测速
 * ======================================================================= */
static void jobDnsBench() {
	int rc = ares_library_init(ARES_LIB_INIT_ALL);
	logLine("[DNS] ares_library_init -> %d (%s)", rc, ares_strerror(rc));

	ares_channel channel = NULL;
	rc = ares_init(&channel);
	if (rc != ARES_SUCCESS || channel == NULL) {
		sErrCount++;
		logLine("[DNS] ares_init 失败: %d (%s)", rc, ares_strerror(rc));
		return;
	}

	int okCount = 0;
	for (int i = 0; i < ND_DNS_BENCH_N; i++) {
		char ip[64] = { 0 };
		int elapsed = 0, timedOut = 0;
		int status = caresResolveOne(channel, kDnsBenchList[i], ip, sizeof(ip), &elapsed, &timedOut);
		logLine("[DNS] %d/%d %-16s -> %-16s %4dms status=%d(%s)%s",
				i + 1, ND_DNS_BENCH_N, kDnsBenchList[i], ip[0] ? ip : "(无)", elapsed,
				status, ares_strerror(status), timedOut ? " [超时]" : "");
		if (status == ARES_SUCCESS && ip[0] != '\0') {
			okCount++;
		}
	}
	logLine("[DNS] 完成：成功 %d/%d", okCount, ND_DNS_BENCH_N);
	if (okCount != ND_DNS_BENCH_N) {
		sErrCount++;
	}
	ares_destroy(channel);
}

/* ---------------- worker 线程 ---------------- */
enum { JOB_NONE = 0, JOB_CARES, JOB_MBEDTLS, JOB_OPENSSL, JOB_DNSBENCH, JOB_AUTO };

static void *workerProc(void *arg) {
	int job = (int) (long) arg;
	if (job == JOB_CARES) {
		logLine("===== 1) c-ares 直调 DNS（ares_fds + select 事件循环） =====");
		jobCares();
	} else if (job == JOB_MBEDTLS) {
		logLine("===== 2) mbedTLS 直调 TLS 握手 + HTTP GET =====");
		jobMbedtls();
	} else if (job == JOB_OPENSSL) {
		logLine("===== 3) OpenSSL(libssl) 直调 TLS 握手 + HTTP GET =====");
		jobOpenssl();
	} else if (job == JOB_DNSBENCH) {
		logLine("===== 4) c-ares DNS 批量测速（%d 个域名） =====", ND_DNS_BENCH_N);
		jobDnsBench();
	} else if (job == JOB_AUTO) {
		logLine("########## AUTO 自检开始（1→2→3→4） ##########");
		logLine("----- 1/4 c-ares DNS -----");
		jobCares();
		logLine("----- 2/4 mbedTLS TLS -----");
		jobMbedtls();
		logLine("----- 3/4 OpenSSL TLS -----");
		jobOpenssl();
		logLine("----- 4/4 c-ares DNS 批量 -----");
		jobDnsBench();
		logLine("########## AUTO 自检结束：错误数=%d ##########", sErrCount);
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
	logLine("就绪：底层网络库直调验证（c-ares / mbedTLS / OpenSSL）。");
	logLine("目标 %s:%s；CA 期望在 %s", ND_HOST, ND_PORT_STR, ND_CA_PRIMARY);
	logLine("所有请求都在 worker 线程跑，UI 线程只刷日志。");
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
static bool onButtonClick_ButtonCares(ZKButton *pButton) {
	startJob(JOB_CARES);
	return true;
}
static bool onButtonClick_ButtonMbedtls(ZKButton *pButton) {
	startJob(JOB_MBEDTLS);
	return true;
}
static bool onButtonClick_ButtonOpenssl(ZKButton *pButton) {
	startJob(JOB_OPENSSL);
	return true;
}
static bool onButtonClick_ButtonDnsBench(ZKButton *pButton) {
	startJob(JOB_DNSBENCH);
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
