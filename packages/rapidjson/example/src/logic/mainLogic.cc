#pragma once
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#include "uart/ProtocolSender.h"

/*
 * rapidjson 依赖包用法示例（Z20 86 面板 / 480x480）—— 纯头文件 JSON 库
 *
 * ⚠️ **本示例未上机**：rapidjson 是纯头文件包（`libs: []`），本仓没有它的真机验证记录
 *    （`packages/rapidjson/package.yaml` 是 `verified: null` / `status: unverified`，见 ../platforms.md）。
 *    所以这里验证的是"**能不能编进工程 + 解析/生成语义对不对**"这类**编译期/语义**结论，
 *    真机数据（耗时/内存/大报文）待补。要标 ✅ 需上机跑一轮并留 logcat（tag = `rapidjson demo`）。
 *
 * 覆盖 API（头文件在 registry 的 include/rapidjson/）：
 *   Document::Parse / HasParseError / GetParseError / GetErrorOffset
 *   IsObject / IsArray / HasMember / operator[] / Size / GetString / GetInt / GetBool
 *   StringBuffer + Writer（生成 JSON）
 *
 * 关键口径（读包头实读出来的，别照最新官方文档抄）：
 *   ① **纯头文件**：没有 .a/.so，不要去找 librapidjson；改 Manifest 后**仍要 fun install**（让 include 路径进 CMake）；
 *   ② `Parse` **不抛异常** → 必须查 `HasParseError()` / `GetParseError()` / `GetErrorOffset()`；
 *   ③ **取值前必须判类型**（`IsString/IsArray/HasMember`）→ 否则 debug 下 `RAPIDJSON_ASSERT` 直接 abort；
 *   ④ 带内嵌 `\0` 的二进制 payload 要用 `Parse(str, length)`；默认 `Parse(const Ch*)` 要求以 `\0` 结尾；
 *   ⑤ 大报文别用 `Document`（全量树），用 `Reader`（SAX）+ 自己的 handler 更省内存；
 *   ⑥ 与 `base-json`/`easyui` 的 jsoncpp（`#include <json/json.h>`）**不是一套库**，别混用。
 */

#include <rapidjson/document.h>
#include <rapidjson/error/en.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <string>

/* ---------------- 日志（本示例不联网，直接刷） ---------------- */
static char sLog[4096];
static volatile int sLogLen = 0, sPrinted = 0;
static volatile int sErrCount = 0;

static void logLine(const char *fmt, ...) {
	char buf[512] = { 0 };
	va_list ap;
	va_start(ap, fmt);
	vsnprintf(buf, sizeof(buf), fmt, ap);
	va_end(ap);
	int n = (int) strlen(sLog);
	if (n + (int) strlen(buf) + 4 < (int) sizeof(sLog)) {
		memcpy(sLog + n, buf, strlen(buf));
		sLog[n + strlen(buf)] = '\n';
		sLog[n + strlen(buf) + 1] = '\0';
	}
	sLogLen = (int) strlen(sLog);
}

static void flushLog() {
	if (sLogLen <= sPrinted) {
		return;
	}
	const char *newpart = sLog + sPrinted;
	if (mTextStatusPtr != NULL) {
		mTextStatusPtr->setText(newpart);
	}
	char line[600] = { 0 };
	int li = 0;
	for (const char *p = newpart;; p++) {
		if (*p == '\n' || *p == '\0') {
			if (li > 0) {
				line[li] = '\0';
				LOGD("rapidjson demo: %s\n", line);
				li = 0;
			}
			if (*p == '\0') break;
		} else if (li < (int) sizeof(line) - 1) {
			line[li++] = *p;
		}
	}
	sPrinted = sLogLen;
}

/* ---- 演示报文：实际项目里换成"设备收到的真实报文"（如 MQTT 下行） ---- */
static const char *kPayload =
	"{\"name\":\"panel-108\",\"brightness\":37,\"online\":true,"
	"\"relays\":[{\"ch\":1,\"on\":true},{\"ch\":2,\"on\":false},{\"ch\":3,\"on\":true}],"
	"\"tags\":[\"z20\",\"86panel\"]}";

/* ---------------- 1) 解析 ---------------- */
static void jobParse() {
	logLine("== Document::Parse（%d 字节） ==", (int) strlen(kPayload));
	rapidjson::Document d;
	/* ⚠️ Parse 不抛异常：失败必须自己查 HasParseError */
	if (d.Parse(kPayload).HasParseError()) {
		sErrCount++;
		logLine("[JSON] 解析失败: %s (offset=%u)", rapidjson::GetParseError_En(d.GetParseError()),
				(unsigned) d.GetErrorOffset());
		return;
	}
	if (!d.IsObject()) {
		sErrCount++;
		logLine("[JSON] 顶层不是对象");
		return;
	}

	/* ⚠️ 取值前必须判类型/判存在 */
	std::string name = (d.HasMember("name") && d["name"].IsString()) ? d["name"].GetString() : "(无)";
	int bright = (d.HasMember("brightness") && d["brightness"].IsInt()) ? d["brightness"].GetInt() : -1;
	bool online = (d.HasMember("online") && d["online"].IsBool()) ? d["online"].GetBool() : false;
	logLine("[JSON] name=%s brightness=%d online=%d", name.c_str(), bright, online ? 1 : 0);

	if (d.HasMember("relays") && d["relays"].IsArray()) {
		const rapidjson::Value &relays = d["relays"];
		logLine("[JSON] relays 数组 %u 项：", (unsigned) relays.Size());
		for (rapidjson::SizeType i = 0; i < relays.Size(); ++i) {
			const rapidjson::Value &it = relays[i];
			if (!it.IsObject()) {
				continue;
			}
			int ch = it.HasMember("ch") && it["ch"].IsInt() ? it["ch"].GetInt() : -1;
			bool on = it.HasMember("on") && it["on"].IsBool() ? it["on"].GetBool() : false;
			logLine("[JSON]   ch=%d on=%d", ch, on ? 1 : 0);
		}
	} else {
		logLine("[JSON] relays 缺失或不是数组");
	}

	/* 失败样例：验证"先判类型再取"这条纪律（这里不真取值，只报类型） */
	rapidjson::Document bad;
	if (bad.Parse("{oops").HasParseError()) {
		logLine("[JSON] 故意给坏报文 → ParseError=%s offset=%u（不抛异常，返回值判）",
				rapidjson::GetParseError_En(bad.GetParseError()), (unsigned) bad.GetErrorOffset());
	}
}

/* ---------------- 2) 生成 ---------------- */
static void jobBuild() {
	logLine("== Writer 生成 JSON ==");
	rapidjson::StringBuffer sb;
	rapidjson::Writer<rapidjson::StringBuffer> w(sb);
	w.StartObject();
	w.Key("name");
	w.String("panel-108");
	w.Key("brightness");
	w.Int(37);
	w.Key("relays");
	w.StartArray();
	for (int ch = 1; ch <= 3; ch++) {
		w.StartObject();
		w.Key("ch");
		w.Int(ch);
		w.Key("on");
		w.Bool(ch != 2);
		w.EndObject();
	}
	w.EndArray();
	w.EndObject();
	std::string out(sb.GetString(), sb.GetSize());   /* 用 (ptr,len)：JSON 里允许内嵌 \0 */
	logLine("[JSON] 生成 (%d 字节): %s", (int) out.size(), out.c_str());

	/* 回读一遍，确认生成的能被自己解析（闭环） */
	rapidjson::Document d;
	if (d.Parse(out.c_str()).HasParseError() || !d.IsObject()) {
		sErrCount++;
		logLine("[JSON] 回读失败");
		return;
	}
	int cnt = (d.HasMember("relays") && d["relays"].IsArray()) ? (int) d["relays"].Size() : 0;
	logLine("[JSON] 回读 OK：relays=%d 项", cnt);
	if (cnt != 3) {
		sErrCount++;
	}
}

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
	{0, 200},
};

static void onUI_init() {
  #ifdef FUN_BUILD
  INIT_UI_TIMERS
  #endif // FUN_BUILD
	sLog[0] = '\0';
	sLogLen = 0;
	sPrinted = 0;
	logLine("就绪：rapidjson 示例（解析 / 生成）");
	logLine("⚠️ 纯头文件包 + 本仓未上机：本示例验证的是编译期与语义，真机数据待补");
	logLine("⚠️ 解析失败不抛异常；取值前必须判类型（否则 debug 下 assert 崩）");
	flushLog();
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

/* ==================== 按钮（纯计算，直接在 UI 线程跑即可） ==================== */
static bool onButtonClick_ButtonParse(ZKButton *pButton) {
	sErrCount = 0;
	jobParse();
	flushLog();
	return true;
}

static bool onButtonClick_ButtonBuild(ZKButton *pButton) {
	sErrCount = 0;
	jobBuild();
	flushLog();
	return true;
}

static bool onButtonClick_ButtonAuto(ZKButton *pButton) {
	sErrCount = 0;
	sLog[0] = '\0';
	sLogLen = 0;
	sPrinted = 0;
	jobParse();
	jobBuild();
	logLine("########## 自检 AUTO 结束：错误数=%d ##########", sErrCount);
	flushLog();
	return true;
}
