#pragma once
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#include "uart/ProtocolSender.h"

/*
 * zkhardware 依赖包用法示例（Z20 86 面板 / 480x480）
 *
 * 重点：3 路继电器**分别控制**（开/关切换）——面板侧 GPIO 操作只能走
 *       GpioHelper::zeroOutput(index, onoff)（过零 IO 控交流电继电器）。
 * 另有：蜂鸣器(HardwareManager) / 亮度背光(BrightnessHelper) / ADC(AdcHelper)。
 * 每个按钮 = 一次调用，结果同时写 textview 与 logcat（TAG 文本含 "zkhardware demo"）。
 *
 * ⚠️ 安全：zeroOutput 驱动的是**交流电继电器**。本示例**上电不写状态**（只读回显），
 *          切某一路必须由人点了对应按钮才动；接线/负载不明时先别点。
 */

#include "utils/GpioHelper.h"			// zkhardware：GPIO / 过零 IO（继电器）
#include "utils/AdcHelper.h"			// zkhardware：ADC
#include "utils/BrightnessHelper.h"		// zkhardware：亮度 / 背光 / 开关屏
#include "hw/HardwareManager.h"			// zkhardware：蜂鸣器

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

/**
 * 注册定时器（本示例不用定时器，但框架要求保留该表，否则编译不过）
 */
static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
	//{0, 1000},
};

/* ==================== 继电器（3 路，分别控制） ==================== */

#define RELAY_CH_NUM	3

// 过零 IO 索引映射：通道 1 / 2 / 3 → 过零输出索引 3 / 1 / 2（**不是顺序映射**）
// 与 SmartPanel_HA 的 RelayManager 同一张表（硬件接线表，改接线只动这里）
static const int kZeroIndexMap[RELAY_CH_NUM] = { 3, 1, 2 };

// 纯 GPIO 模式备用脚（本面板上这三脚是过零驱动脚，只在无过零设备时才用）
static const char *kGpioPins[RELAY_CH_NUM] = { "B_02", "B_03", "E_20" };

static int  sRelayMode = -1;			// 0=过零 IO / 1=纯 GPIO / 2=模拟（都没有）
static int  sRelayOn[RELAY_CH_NUM] = { 0, 0, 0 };	// 软件侧真值（回读失败时兜底）

static void relayDetectMode() {
	if (sRelayMode >= 0) {
		return;
	}
	int n = GpioHelper::getZeroIoNum();
	if (n >= RELAY_CH_NUM) {
		sRelayMode = 0;
		LOGD("zkhardware demo: relay mode=过零 IO（%d 路，索引表 3/1/2）\n", n);
	} else if (GpioHelper::output(kGpioPins[0], 0) == 0) {
		sRelayMode = 1;
		LOGD("zkhardware demo: relay mode=纯 GPIO（B_02/B_03/E_20，高电平吸合）\n");
	} else {
		sRelayMode = 2;
		LOGW("zkhardware demo: relay mode=模拟（无过零 IO 也无 GPIO）\n");
	}
}

static const char *relayModeName() {
	switch (sRelayMode) {
	case 0: return "过零 IO";
	case 1: return "纯 GPIO";
	default: return "模拟";
	}
}

/** 回读某一路真实状态；-1 = 读不到 */
static int relayRead(int ch) {
	if (ch < 1 || ch > RELAY_CH_NUM) {
		return -1;
	}
	relayDetectMode();
	if (sRelayMode == 0) {
		int v = GpioHelper::getZeroIoStatus(kZeroIndexMap[ch - 1]);
		return (v < 0) ? -1 : (v ? 1 : 0);
	}
	if (sRelayMode == 1) {
		int v = GpioHelper::input(kGpioPins[ch - 1]);
		return (v < 0) ? sRelayOn[ch - 1] : (v ? 1 : 0);
	}
	return sRelayOn[ch - 1];
}

/** 写某一路：on=1 吸合 / 0 断开 */
static void relayWrite(int ch, int on) {
	if (ch < 1 || ch > RELAY_CH_NUM) {
		return;
	}
	relayDetectMode();
	if (sRelayMode == 0) {
		GpioHelper::zeroOutput(kZeroIndexMap[ch - 1], on ? 1 : 0);
	} else if (sRelayMode == 1) {
		GpioHelper::output(kGpioPins[ch - 1], on ? 1 : 0);
	}
	sRelayOn[ch - 1] = on ? 1 : 0;
}

/** "#1=ON #2=OFF #3=ON" 形式的三路状态串 */
static void relayStatusStr(char *buf, int size) {
	buf[0] = '\0';
	for (int ch = 1; ch <= RELAY_CH_NUM; ch++) {
		int v = relayRead(ch);
		char tmp[32] = { 0 };
		snprintf(tmp, sizeof(tmp) - 1, "#%d=%s(索引%d) ", ch,
				(v == 1) ? "ON" : (v == 0 ? "OFF" : "?"),
				kZeroIndexMap[ch - 1]);
		strncat(buf, tmp, size - strlen(buf) - 1);
	}
}

static void setStatus(const char *fmt, ...) {
	char buf[512] = { 0 };
	va_list ap;
	va_start(ap, fmt);
	vsnprintf(buf, sizeof(buf) - 1, fmt, ap);
	va_end(ap);
	if (mTextStatusPtr != NULL) {
		mTextStatusPtr->setText(buf);
	}
	LOGD("zkhardware demo: %s\n", buf);
}

/**
 * 当界面构造时触发
 * 注意：**只读不写** —— 不在这里动继电器（避免上电自己切交流回路）
 */
static void onUI_init() {
  #ifdef FUN_BUILD
  INIT_UI_TIMERS
  #endif // FUN_BUILD
	int cur = BRIGHTNESSHELPER->getBrightness();
	int max = BRIGHTNESSHELPER->getMaxBrightness();
	int zio = GpioHelper::getZeroIoNum();
	relayDetectMode();
	char st[160] = { 0 };
	relayStatusStr(st, sizeof(st) - 1);
	LOGD("zkhardware demo: onUI_init brightness=%d/%d zeroIo=%d mode=%s\n",
			cur, max, zio, relayModeName());
	LOGD("zkhardware demo: relay read %s\n", st);
	setStatus("就绪：亮度 %d/%d，过零 IO %d 路，继电器模式 %s\n"
			"当前继电器：%s\n点「继电器 N 切换」分别控制三路（结果进 logcat）",
			cur, max, zio, relayModeName(), st);
}

static void onUI_intent(const Intent *intentPtr) {
	if (intentPtr != NULL) {
		//TODO
	}
}

static void onUI_show() {

}

static void onUI_hide() {

}

static void onUI_quit() {

}

/**
 * 串口数据回调接口
 */
static void onProtocolDataUpdate(const SProtocolData &data) {

}

/**
 * 定时器触发函数（本示例未注册定时器）
 */
static bool onUI_Timer(int id) {
	switch (id) {
	default:
		break;
	}
	return true;
}

/**
 * 新的触摸事件触发
 */
static bool onmainActivityTouchEvent(const MotionEvent &ev) {
	return false;
}

/* ==================== 按钮回调：3 路继电器分别控制 ==================== */

/**
 * 继电器切换（通道 ch）：先回读真实状态 → 取反写入 → 再回读确认
 * 调用：GpioHelper::zeroOutput(index, onoff)（过零 IO）；读：getZeroIoStatus(index)
 */
static bool relayToggle(int ch) {
	relayDetectMode();
	int cur = relayRead(ch);
	int want = (cur == 1) ? 0 : 1;
	relayWrite(ch, want);
	int back = relayRead(ch);
	char st[160] = { 0 };
	relayStatusStr(st, sizeof(st) - 1);
	LOGD("zkhardware demo: relay %d: 读=%d -> zeroOutput(索引%d,%d) -> 回读=%d\n",
			ch, cur, kZeroIndexMap[ch - 1], want, back);
	setStatus("继电器 %d：读 %s → 写 %s → 回读 %s（%s，过零索引 %d，高电平吸合）\n"
			"三路：%s",
			ch, (cur == 1 ? "ON" : (cur == 0 ? "OFF" : "?")),
			want ? "ON" : "OFF", (back == 1 ? "ON" : (back == 0 ? "OFF" : "?")),
			relayModeName(), kZeroIndexMap[ch - 1], st);
	return true;
}

static bool onButtonClick_ButtonRelay1(ZKButton *pButton) {
	return relayToggle(1);
}

static bool onButtonClick_ButtonRelay2(ZKButton *pButton) {
	return relayToggle(2);
}

static bool onButtonClick_ButtonRelay3(ZKButton *pButton) {
	return relayToggle(3);
}

/** 只读：三路状态 + 过零 IO 全部通道 + 模式/索引表 */
static bool onButtonClick_ButtonRelayRead(ZKButton *pButton) {
	relayDetectMode();
	int n = GpioHelper::getZeroIoNum();
	char raw[160] = { 0 };
	for (int i = 0; i < n && i < 8; i++) {
		char tmp[32] = { 0 };
		snprintf(tmp, sizeof(tmp) - 1, "#%d=%s ", i,
				GpioHelper::getZeroIoStatus(i) ? "ON" : "OFF");
		strncat(raw, tmp, sizeof(raw) - strlen(raw) - 1);
	}
	char st[160] = { 0 };
	relayStatusStr(st, sizeof(st) - 1);
	LOGD("zkhardware demo: relay read %s| 原始 zeroIo num=%d %s\n", st, n, raw);
	setStatus("继电器（模式 %s，索引表 {3,1,2}）：%s\n"
			"过零 IO 共 %d 路原始状态：%s\n（只读演示；动作 = zeroOutput(index, onoff)）",
			relayModeName(), st, n, raw);
	return true;
}

/** 三路全断（同样只在人点了才动） */
static bool onButtonClick_ButtonRelayAllOff(ZKButton *pButton) {
	relayDetectMode();
	for (int ch = 1; ch <= RELAY_CH_NUM; ch++) {
		relayWrite(ch, 0);
	}
	char st[160] = { 0 };
	relayStatusStr(st, sizeof(st) - 1);
	LOGD("zkhardware demo: relay all OFF -> %s\n", st);
	setStatus("已对三路依次 zeroOutput(索引,%d)：%s", 0, st);
	return true;
}

/* ==================== 按钮回调：其余外设 ==================== */

/**
 * 蜂鸣器：HardwareManager::beep()
 * ⚠️ Z20 86 面板**没接蜂鸣器**：这里只验调用链通，听不到声是硬件缺席
 */
static bool onButtonClick_ButtonBeep(ZKButton *pButton) {
	HARDWAREMANAGER->beep();
	setStatus("HARDWAREMANAGER->beep() 已调用（默认 2500Hz / duty 50，可用 setBeepPWM 改）\n"
			"注意：86 面板未接蜂鸣器，调用成功也不会响");
	return true;
}

/**
 * 亮度：BrightnessHelper（范围 1~getMaxBrightness()，本机 100）
 */
static bool onButtonClick_ButtonBrightDown(ZKButton *pButton) {
	int max = BRIGHTNESSHELPER->getMaxBrightness();
	int v = BRIGHTNESSHELPER->getBrightness() - 10;
	if (v < 1) {
		v = 1;
	}
	BRIGHTNESSHELPER->setBrightness(v);
	setStatus("setBrightness(%d) -> getBrightness() = %d（范围 1~%d）", v,
			BRIGHTNESSHELPER->getBrightness(), max);
	return true;
}

static bool onButtonClick_ButtonBrightUp(ZKButton *pButton) {
	int max = BRIGHTNESSHELPER->getMaxBrightness();
	int v = BRIGHTNESSHELPER->getBrightness() + 10;
	if (v > max) {
		v = max;
	}
	BRIGHTNESSHELPER->setBrightness(v);
	setStatus("setBrightness(%d) -> getBrightness() = %d（范围 1~%d）", v,
			BRIGHTNESSHELPER->getBrightness(), max);
	return true;
}

/**
 * ADC：AdcHelper::setEnable(true) + setChannel(ch) + getVal()
 * ⚠️ 86 面板**没有 ADC 接口** → 这里读到的值是无效通道/噪声，别当能力用、别标阈值
 */
static bool onButtonClick_ButtonAdc(ZKButton *pButton) {
	static const int kChs[] = { 0, 1, 2, 3 };
	char buf[320] = { 0 };
	AdcHelper::setEnable(true);
	for (int i = 0; i < 4; ++i) {
		bool ok = AdcHelper::setChannel(kChs[i]);
		int val = ok ? AdcHelper::getVal() : -1;
		char tmp[64] = { 0 };
		snprintf(tmp, sizeof(tmp) - 1, "ch%d=%d(ok=%d) ", kChs[i], val, ok ? 1 : 0);
		strncat(buf, tmp, sizeof(buf) - strlen(buf) - 1);
		LOGD("zkhardware demo: Adc ch=%d ok=%d val=%d\n", kChs[i], ok ? 1 : 0, val);
	}
	setStatus("ADC 扫 ch0~3：%s\n（-1/ok=0 = 通道不可用）\n"
			"注意：86 面板无 ADC 接口，值仅供参考、勿用于产品逻辑", buf);
	return true;
}
