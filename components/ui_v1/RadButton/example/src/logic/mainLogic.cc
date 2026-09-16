#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD
#include "uart/ProtocolSender.h"
#include <cstdio>
#include <cstdarg>
#include <string>
#include "zk/zk_radbutton.h"

/* ==========================================================================
 * components/ui_v1/RadButton —— 最小可跑示例（Z21 1024x600）
 *
 * 一件事：把「平台 button__N 只能纯色直角 / 圆角切图」这个缺口，
 *         用一个 painter + 一份代码补上（任意尺寸 / 任意半径 / 四态 / 连边框）。
 *
 * 屏上五行：
 *   (1) PtHard4/8/14   平台原生 fillRect(radius) —— HARD 硬边（对照组）
 *   (2) PtAa4/8/14     本包 MODE_AA（r=8 带 1px 边框、r=14 带 2px 边框）
 *   (3) PtStCur        四态循环（BtnCycle）/ PtStToggle 选中 / PtStPress 按下 / PtStDisabled 静态
 *   (4) PtProbe        painter 原生能力探针：fillRect 直角 + fillArc 圆环 + drawRect 圆角描边
 *   (5) BtnImg         切图路线对照：.9.png 九宫格拉伸（资产 200x56 -> 盒子 300x56）
 *
 * 验收三线：
 *   (1) (1)(2)同半径上下对照 -> 边缘是否有中间档（数字见 evidence/ + platforms.md）
 *   (2) (3)点按钮 -> 状态色切换（幂等，press 抬起回落到按下前状态）
 *   (3) BtnRadius -> 运行时换半径（切图路线做不到的那条）
 *
 * 组件实现：src/zk/zk_radbutton.{h,cpp}（从 components/ui_v1/RadButton/ 原样拷来，未改）
 * ========================================================================== */

static zk::ui_v1::RadButton s_hard4, s_hard8, s_hard14;      /* (1) 对照 */
static zk::ui_v1::RadButton s_aa4, s_aa8, s_aa14;            /* (2) 本包 AA */
static zk::ui_v1::RadButton s_cur, s_toggle, s_press, s_dis; /* (3) 四态 */

/* (6) 自带触摸 + 开关语义（本轮新增：在这三个盒子上没有平台按钮，命中全在包里） */
static zk::ui_v1::RadButton s_pill, s_pillDis, s_rectSw;
/* 这三个 painter 在 WinMain 里（WinMain 在屏幕 (0,56)）-> 绝对屏幕矩形 = 局部坐标 + (0,56)。
 * 【关键】包不许调 getAbsolutePosition()/getParent()（设备端未导出 -> 黑屏），
 *   所以绝对矩形只能由业务算好了 setRect() 喂进去（本例是固定布局，直接写常量；
 *   多层嵌套的写法见案例 projects/translate/lvgl-widgets-uiv1/ 的 absRectOf()）。 */
#define PT_SWPILL_X   24
#define PT_SWPILL_Y   (506 + 56)
#define PT_SWPILL_W   110
#define PT_SWPILL_H   36
#define PT_SWRECT_X   264
#define PT_SWRECT_Y   (506 + 56)
#define PT_SWRECT_W   200
#define PT_SWRECT_H   36

static void tlog(const char *fmt, ...) {
	char buf[200];
	va_list ap;
	va_start(ap, fmt);
	vsnprintf(buf, sizeof(buf), fmt, ap);
	va_end(ap);
	if (mTvTouchLogPtr != NULL) mTvTouchLogPtr->setText(buf);
#ifdef ANDROID_LOG
	LOGD("%s\n", buf);
#endif
}

/* 翻转回调：包在 UP 抬起到界内、且状态真的翻转后调一次 */
static void onPillToggle(bool on, void *user) {
	zk::ui_v1::RadButton *b = (zk::ui_v1::RadButton *)user;
	tlog("PILL 翻转 -> %s（%s）", on ? "ON" : "OFF", b ? b->stateName() : "?");
}

static void onRectToggle(bool on, void *user) {
	(void)user;
	tlog("RECT 翻转 -> %s（填充 0x%06X）", on ? "ON" : "OFF",
	     (unsigned)(on ? 0x0D47A1 : 0x2196F3));
}

static const int AA_RADIUS[3] = { 4, 14, 28 };               /* BtnRadius 循环 */
static int s_radiusIdx = 1;

static void logf(const char *fmt, ...) {
	char buf[200];
	va_list ap;
	va_start(ap, fmt);
	vsnprintf(buf, sizeof(buf), fmt, ap);
	va_end(ap);
	if (mTvLogPtr != NULL) mTvLogPtr->setText(buf);
	if (mTvStatusPtr != NULL) mTvStatusPtr->setText(buf);
}

/* 底色（与 json 里 WinMain 的 #F5F7FA 一致）—— AA 混色基准，给错就会有一圈 halo */
#define PAGE_BG 0xF5F7FA

/* ---------------- (1) HARD 对照组 ---------------- */
static void initHardRow() {
	zk::ui_v1::RadButton::Style st = zk::ui_v1::RadButton::defaultStyle();
	st.mode = zk::ui_v1::RadButton::MODE_HARD;
	st.bg = PAGE_BG;
	st.normal = 0x2196F3;

	st.radius = 4;  s_hard4.setStyle(st);  s_hard4.attach(mPtHard4Ptr);   s_hard4.refresh();
	st.radius = 8;  s_hard8.setStyle(st);  s_hard8.attach(mPtHard8Ptr);   s_hard8.refresh();
	st.radius = 14; s_hard14.setStyle(st); s_hard14.attach(mPtHard14Ptr); s_hard14.refresh();
}

/* ---------------- (2) 本包 AA ---------------- */
static void initAaRow() {
	zk::ui_v1::RadButton::Style st = zk::ui_v1::RadButton::defaultStyle();
	st.bg = PAGE_BG;
	st.normal = 0x2196F3;

	st.radius = 4;
	s_aa4.setStyle(st);  s_aa4.attach(mPtAa4Ptr);  s_aa4.refresh();

	st.radius = 8;
	s_aa8.setStyle(st);  s_aa8.attach(mPtAa8Ptr);  s_aa8.refresh();

	st.radius = 14;
	s_aa14.setStyle(st); s_aa14.attach(mPtAa14Ptr); s_aa14.refresh();
}

/* ---------------- (3) 四态 ---------------- */
static void initStateRow() {
	zk::ui_v1::RadButton::Style st = zk::ui_v1::RadButton::defaultStyle();
	st.bg = PAGE_BG;
	st.radius = 14;
	st.normal   = 0x2196F3;
	st.pressed  = 0x1976D2;
	st.selected = 0x0D47A1;
	st.disabled = 0xBDBDBD;

	s_cur.setStyle(st);      s_cur.attach(mPtStCurPtr);           s_cur.setState(zk::ui_v1::RadButton::NORMAL);
	st.border = 0x0D47A1;              /* 边框演示：2px 深蓝描边（st 上面的改不影响已 setStyle 的实例）*/
	st.borderWidth = 2;
	s_toggle.setStyle(st);   s_toggle.attach(mPtStTogglePtr);     s_toggle.setState(zk::ui_v1::RadButton::NORMAL);
	s_press.setStyle(st);    s_press.attach(mPtStPressPtr);       s_press.setState(zk::ui_v1::RadButton::NORMAL);
	s_dis.setStyle(st);      s_dis.attach(mPtStDisabledPtr);      s_dis.setState(zk::ui_v1::RadButton::DISABLED);

	s_cur.refresh(); s_toggle.refresh(); s_press.refresh(); s_dis.refresh();
}

/* ---------------- (4) painter 原生能力探针 ---------------- */
static void initProbe() {
	if (mPtProbePtr == NULL) return;
	const LayoutPosition &p = mPtProbePtr->getPosition();
	mPtProbePtr->erase(0, 0, p.mWidth, p.mHeight);

	/* (a) fillRect 直角：满幅底色块 */
	mPtProbePtr->setSourceColor(0xE3E7EC);
	mPtProbePtr->fillRect(10, 10, p.mWidth - 20, p.mHeight - 20, 0);

	/* (b) fillArc 圆环：外圆 - 内圆 = 环（painter 无「环形」API，只能两笔叠） */
	mPtProbePtr->setSourceColor(0x2196F3);
	mPtProbePtr->fillArc(80, 100, 56, 0, 0, 360);
	mPtProbePtr->setSourceColor(0xE3E7EC);
	mPtProbePtr->fillArc(80, 100, 36, 0, 0, 360);

	/* (c) drawRect 圆角描边（半径 16）*/
	mPtProbePtr->setLineWidth(2);
	mPtProbePtr->setSourceColor(0xF44336);
	mPtProbePtr->drawRect(160, 40, 120, 120, 16);
	mPtProbePtr->setLineWidth(1);
}

/* ---------------- 业务侧触摸：按下态（可选路径） ---------------- */
class PressTouchListener : public ZKBase::ITouchListener {
public:
	PressTouchListener() {}
	virtual ~PressTouchListener() {}
	virtual void onTouchEvent(ZKBase *pBase, const MotionEvent &ev) {
		(void)pBase;
		if (ev.mActionStatus == MotionEvent::E_ACTION_DOWN) {
			s_press.press(true);
			s_press.refresh();
			logf("press DOWN -> %s（%dx%d r=%d）", s_press.stateName(),
			     s_press.width(), s_press.height(), s_press.radiusPx());
		} else if (ev.mActionStatus == MotionEvent::E_ACTION_UP ||
		           ev.mActionStatus == MotionEvent::E_ACTION_CANCEL) {
			s_press.press(false);
			s_press.refresh();
			logf("press UP   -> %s（回落幂等）", s_press.stateName());
		}
	}
};

static PressTouchListener s_pressListener;

/* ---------------- (6) 自带触摸 + 开关语义（PILL / RECT，都在包的 onTouch 里） ---------------- */
static void initTouchRow() {
	/* 三块共同样式：底色 = WinMain 的 #F5F7FA（AA 混色基准） */
	zk::ui_v1::RadButton::Style st = zk::ui_v1::RadButton::defaultStyle();
	st.bg       = PAGE_BG;
	st.normal   = 0xB0BEC5;		/* PILL：关态轨色（灰） */
	st.selected = 0x2196F3;		/* PILL：开态轨色（主色）；RECT：选中填充 */
	st.pressed  = 0x1976D2;		/* PILL 不用它（改用轨色压深 12%）；RECT 用 */
	st.disabled = 0xBDBDBD;

	/* (1) PILL 药丸开关：圆钮（白）+ 内边距 3，点一下翻转（开关模式由 setShape(PILL) 自带） */
	zk::ui_v1::RadButton::PillStyle ps;
	ps.padding = 3;
	ps.knobDia = 0;				/* 0 = 自动 = 高 - 2*padding */
	ps.knobOff = 0xFFFFFF;
	ps.knobOn  = 0xFFFFFF;
	s_pill.setStyle(st);
	s_pill.setPillStyle(ps);
	s_pill.setShape(zk::ui_v1::RadButton::PILL);		/* * 药丸 = 开关形态 */
	s_pill.attach(mPtSwPillPtr);
	s_pill.setRect(PT_SWPILL_X, PT_SWPILL_Y, PT_SWPILL_W, PT_SWPILL_H);
	s_pill.setOnToggle(onPillToggle, &s_pill);
	s_pill.setOn(false);
	s_pill.refresh();

	/* (2) 同款药丸的**禁用态**（点它不翻转。演示「DISABLED = 不翻转但可显示按下态」） */
	s_pillDis.setStyle(st);
	s_pillDis.setPillStyle(ps);
	s_pillDis.setShape(zk::ui_v1::RadButton::PILL);
	s_pillDis.attach(mPtSwPillDisPtr);
	s_pillDis.setRect(PT_SWPILL_X + 120, PT_SWPILL_Y, PT_SWPILL_W, PT_SWPILL_H);
	s_pillDis.setOn(true);				/* 先置 ON，再看禁用态长什么样 */
	s_pillDis.setState(zk::ui_v1::RadButton::DISABLED);
	s_pillDis.refresh();

	/* (3) RECT 倒角开关：半径 12，选中 = 深蓝（开关语义用在矩形上，验证形态与语义解耦） */
	zk::ui_v1::RadButton::Style st2 = st;
	st2.radius   = 12;
	st2.normal   = 0x2196F3;
	st2.selected = 0x0D47A1;
	s_rectSw.setStyle(st2);
	s_rectSw.setShape(zk::ui_v1::RadButton::SHAPE_RECT);
	s_rectSw.setSwitchable(true);		/* 矩形也能当开关（默认不翻转） */
	s_rectSw.attach(mPtTouchRectPtr);
	s_rectSw.setRect(PT_SWRECT_X, PT_SWRECT_Y, PT_SWRECT_W, PT_SWRECT_H);
	s_rectSw.setOnToggle(onRectToggle, &s_rectSw);
	s_rectSw.setOn(false);
	s_rectSw.refresh();

	tlog("ready：药丸 %dx%d r=%d（钮 dia=%d）/ 倒角 %dx%d r=%d",
	     s_pill.width(), s_pill.height(), s_pill.radiusPx(),
	     s_pill.height() - 2 * 3, s_rectSw.width(), s_rectSw.height(), s_rectSw.radiusPx());
}

static void refreshAll() {
	s_hard4.refresh(); s_hard8.refresh(); s_hard14.refresh();
	s_aa4.refresh();   s_aa8.refresh();   s_aa14.refresh();
	s_cur.refresh();   s_toggle.refresh(); s_press.refresh(); s_dis.refresh();
	s_pill.refresh();  s_pillDis.refresh(); s_rectSw.refresh();
	initProbe();
}

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
	/* 自动演示序列：每 2s 走一步（不依赖触摸，抓图可复现；按钮路径仍在，点一下就会插队改变状态） */
	{ 1, 2000 },
};

static int s_step = 0;

/* 序列：1 PRESSED / 2 SELECTED / 3 press(true) / 4 press(false) 回落 / 5 换半径 r=28 */
static bool onUI_Timer(int id) {
	if (id != 1) return true;
	++s_step;
	switch (s_step) {
	case 1:
		s_cur.setState(zk::ui_v1::RadButton::PRESSED);  s_cur.refresh();
		if (mTvStCurPtr) mTvStCurPtr->setText(std::string("当前：") + s_cur.stateName());
		logf("step1 setState(PRESSED) -> %s（填充 0x%06X）", s_cur.stateName(), (unsigned)s_cur.currentColor());
		break;
	case 2:
		s_toggle.setSelected(true);  s_toggle.refresh();
		logf("step2 setSelected(true) -> %s", s_toggle.stateName());
		break;
	case 3:
		s_press.press(true);  s_press.refresh();
		logf("step3 press(true) -> %s（记住按下前状态）", s_press.stateName());
		break;
	case 4:
		s_press.press(false);  s_press.refresh();
		logf("step4 press(false) -> %s（幂等回落）", s_press.stateName());
		break;
	case 5:
		s_aa4.setRadius(28);  s_aa4.refresh();
		s_aa14.setRadius(28); s_aa14.refresh();
		logf("step5 setRadius(28) -> %dx%d 药丸（无资产）", s_aa4.width(), s_aa4.height());
		break;
	default:
		logf("演示序列结束（%d 步）；按钮仍可用", s_step - 1);
		return false;                     /* 停表 */
	}
	return true;
}

static void onUI_init() {
#ifdef FUN_BUILD
	INIT_UI_TIMERS
#endif // FUN_BUILD

	initHardRow();
	initAaRow();
	initStateRow();
	initTouchRow();
	initProbe();

	if (mTvStCurPtr != NULL) mTvStCurPtr->setText("当前：NORMAL");
	if (mBtnPressPtr != NULL) mBtnPressPtr->setTouchListener(&s_pressListener);
	logf("ready：AA 模式 = 逐像素覆盖率 + 混底色（bg=0x%06X）", (unsigned)PAGE_BG);
}

static void onUI_intent(const Intent *intentPtr) { (void)intentPtr; }

/* 切回本页：painter 不自动重绘 -> 全刷一遍 */
static void onUI_show() { refreshAll(); }

static void onUI_hide() {}

static void onUI_quit() {
	s_hard4.detach(); s_hard8.detach(); s_hard14.detach();
	s_aa4.detach();   s_aa8.detach();   s_aa14.detach();
	s_cur.detach();   s_toggle.detach(); s_press.detach(); s_dis.detach();
	s_pill.detach();  s_pillDis.detach(); s_rectSw.detach();
}

static void onProtocolDataUpdate(const SProtocolData &data) { (void)data; }

/* ============================ 触摸：全部交给包的 onTouch（业务只喂坐标 + 看返回值） ============================
 * 【坐标口径】RadButton::setRect()/onTouch() 都是**绝对屏幕坐标**，与 MotionEvent::mX/mY 同口径。
 *   本例三块在 WinMain（屏幕 (0,56)）里 -> 绝对 = 局部 + 56（常量宏见文件上部）。
 * 【为什么不返回 true】(6) 那三块下面没有平台控件，返回什么都不影响；这里演示「按返回值决定是否消费」——
 *   包返回 true = 已消费。案例里（lvgl-widgets-uiv1）对**普通按钮**故意不消费（让平台按钮照常收点击），
 *   只对**开关**消费（开关语义完全归包）。两种用法都合规，看业务想不想接管点击。
 */
static bool onmainActivityTouchEvent(const MotionEvent &ev) {
	int act;
	switch (ev.mActionStatus) {
	case MotionEvent::E_ACTION_DOWN:   act = zk::ui_v1::RadButton::TOUCH_DOWN;   break;
	case MotionEvent::E_ACTION_UP:     act = zk::ui_v1::RadButton::TOUCH_UP;     break;
	case MotionEvent::E_ACTION_CANCEL: act = zk::ui_v1::RadButton::TOUCH_CANCEL; break;
	default:                           act = zk::ui_v1::RadButton::TOUCH_MOVE;   break;
	}
	bool eaten = false;
	eaten |= s_pill.onTouch(ev.mX, ev.mY, act);
	eaten |= s_pillDis.onTouch(ev.mX, ev.mY, act);
	eaten |= s_rectSw.onTouch(ev.mX, ev.mY, act);
	return eaten;
}

/* ---- (3) 四态循环 ---- */
static bool onButtonClick_BtnCycle(ZKButton *pButton) {
	(void)pButton;
	int s = (int)s_cur.state() + 1;
	if (s > 3) s = 0;
	s_cur.setState((zk::ui_v1::RadButton::State)s);
	s_cur.refresh();
	if (mTvStCurPtr != NULL) mTvStCurPtr->setText(std::string("当前：") + s_cur.stateName());
	logf("切换状态 -> %s（填充 0x%06X）", s_cur.stateName(), (unsigned)s_cur.currentColor());
	return false;
}

/* ---- (3) 选中 / 取消（setSelected 幂等） ---- */
static bool onButtonClick_BtnToggle(ZKButton *pButton) {
	(void)pButton;
	s_toggle.setSelected(!s_toggle.isSelected());
	s_toggle.refresh();
	logf("选中切换 -> %s", s_toggle.stateName());
	return false;
}

/* ---- (3) 按下态：也支持「点一下」路径（点击后短暂显示 PRESSED 再回落不可能，故这里是说明性日志） ---- */
static bool onButtonClick_BtnPress(ZKButton *pButton) {
	(void)pButton;
	s_press.press(true);
	s_press.refresh();
	s_press.press(false);
	s_press.refresh();
	logf("press(true)/press(false) 幂等回归 -> %s", s_press.stateName());
	return false;
}

/* ---- (2) 运行时换半径（切图路线做不到：资产半径写死在图里） ---- */
static bool onButtonClick_BtnRadius(ZKButton *pButton) {
	(void)pButton;
	s_radiusIdx = (s_radiusIdx + 1) % 3;
	const int r = AA_RADIUS[s_radiusIdx];
	s_aa4.setRadius(r);   s_aa4.refresh();
	s_aa14.setRadius(r);  s_aa14.refresh();
	logf("AA 行换半径 -> r=%d（%dx%d 同一份代码，无资产）", r, s_aa4.width(), s_aa4.height());
	return false;
}static bool onButtonClick_BtnImg(ZKButton* pButton) {
  LOGD_TRACE("BtnImg click");
  return false;
}


