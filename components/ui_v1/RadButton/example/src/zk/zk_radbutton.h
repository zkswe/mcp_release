/*
 * zk_radbutton.h — components/ui_v1/RadButton（源控件：lv_button 的主题倒角 / CSS border-radius）
 *
 * 唯一对外头文件。实现见 src/zk_radbutton.cpp。
 *
 * 为什么有这个东西（一句话）：
 *平台 `button__N`（L1 映射，见 mcp_control_map.json 的 lvgl.lv_btn → button）只有
 *   **纯色直角**与 **切图**两条路：json 里没有任何 radius 字段，`ZKButton` 也没有半径 setter。
 *切图（.9.png）能出平滑圆角，但**每种尺寸/每种半径都要提前出一份资产**，
 *运行时「任意尺寸 + 任意半径」做不到（见 gap-list.md G-07）。
 *所以本包把「带倒角按钮」做成 **ZKPainter 自绘控件**：一个 painter + 一份代码，
 *尺寸/半径/四态色全在运行时给。
 *
 * 三条平台事实（决定了 API 长什么样，Z21 easyui 2.6.0 实测）：
 *   1. `ZKPainter::setSourceColor(0xRRGGBB)` **没有 alpha 通道**→ 真·半透明叠加不存在。
 *本包的抗锯齿走「逐像素覆盖率 + 与已知底色混色」（`Style::bg` 必须给对，
 *否则边缘会带一条底色的色差 halo）。
 *   2. `ZKPainter` **不自动重绘**→ 改半径/改色/改状态后必须显式 `refresh()`。
 *      （例外：`onTouch()` 默认 `setAutoRefresh(true)`，它替你调。）
 *   3. `ZKPainter::fillRect(l,t,w,h,radius)` 的圆角是**硬边**（边界只有前景/底色两档，
 *无中间值）→ 本包默认 `MODE_AA` 自己算覆盖率，`MODE_HARD` 保留旧行为供对照。
 *实测数字见例程 `example/evidence/` 与 platforms.md 的「AA 对照表」。
 *      （注：`fillRect(radius)` 在 Z21 上其实**有阿玛但很粗**：平均误差 8~20/255，r=8 时 36% 的弧带像素误差 >30，
 *本包 AA 是 1.4~2.0 —— 数字见 platforms.md §1.1）
 *   4. `erase()` 擦出来的是**不透明黑**（不是透明）→ 画之前必须自己铺底；
 *本包 `drawRoundedRect` 会先用 `bg` 铺满整个控件盒（圆角外的像素也因此与混色基准同色）。
 *
 * ⚠️ 平台符号铁律：不许用 `getParent()` / `getAbsolutePosition()`
 *   （设备端 libeasyui.so 未导出 → dlopen 失败 → 整屏黑）。本包只用
 *   `painter->getPosition()`（父相对坐标），**命中所需的「绝对屏幕矩形」由业务显式给**
 *   （`setRect()`），包内绝不去推祖先链。
 *
 * 本轮（2026-09-16 晚，需求方两句话）新增：
 *   · **自带触摸**：`setRect()` + `onTouch(x,y,action)`（命中 / 按下态 / 移出取消 / UP 翻转 / 消费语义）；
 *   · **当「带倒角的开关」用**：`setSwitchable()` + `setOn()/isOn()/toggle()/setOnToggle(cb,user)`
 *与 `setShape(SHAPE_RECT|SHAPE_PILL)` 药丸形态（可配圆钮：钮位/钮色/内边距）。
 *
 * 命名空间：zk::ui_v1::RadButton
 * 对应：control-map.md §1.x（lv_button → button__N，L1）+ gap-list.md G-07（圆角/边框无平台能力，L4→本包 L3 自绘）
 */
#ifndef _ZK_UI_V1_RADBUTTON_H_
#define _ZK_UI_V1_RADBUTTON_H_

#include <stdint.h>
#include <string>

class ZKPainter;

namespace zk {
namespace ui_v1 {

/**
 * @brief 带倒角（圆角）按钮 —— painter 自绘，运行时任意尺寸/任意半径/四态；可选「开关模式 + 药丸形态」
 *
 * 最短用法（完整可跑示例见 example/）：
 * @code
 *   static zk::ui_v1::RadButton s_ok;
 *
 *   void onUI_init() {
 *       zk::ui_v1::RadButton::Style st = zk::ui_v1::RadButton::defaultStyle();
 *       st.radius = 12;
 *       st.bg     = 0xF5F7FA;                  // ★ 按钮背后的底色（AA 混色基准）
 *       s_ok.setStyle(st);
 *       s_ok.attach(mPtOkPtr);                 // json 里的 painter__N
 *       s_ok.setState(zk::ui_v1::RadButton::NORMAL);
 *       s_ok.setRect(120, 300, 200, 48);       // ★ 绝对屏幕矩形（触摸命中用；样例值）
 *       s_ok.refresh();                        // ★ 不调什么都不显示
 *   }
 *
 *   // 自带触摸（业务只喂坐标，命中/按下态/回落都在包里）：
 *   void onmainActivityTouchEvent(const MotionEvent &ev) {
 *       int act = (ev.mActionStatus == MotionEvent::E_ACTION_DOWN) ? zk::ui_v1::RadButton::TOUCH_DOWN
 *               : (ev.mActionStatus == MotionEvent::E_ACTION_UP)   ? zk::ui_v1::RadButton::TOUCH_UP
 *                                                                 : zk::ui_v1::RadButton::TOUCH_MOVE;
 *       if (s_ok.onTouch(ev.mX, ev.mY, act)) return true;   // ★ true = 已消费
 *       return false;
 *   }
 * @endcode
 */
class RadButton {
public:
	/**按钮状态（四态，与 json 的 bgColorTab 语义对齐） */
	enum State {
		NORMAL   = 0,   // 常态
		PRESSED  = 1,   // 按下（手指在按钮上）
		SELECTED = 2,   // 选中/激活（开关、页签、单选组）——开关的「开」就是这个态
		DISABLED = 3    // 不可用（点不动的语义色；命中仍由业务判断）
	};

	/**圆角画法 */
	enum Mode {
		MODE_AA   = 0,  // ★ 默认：逐像素覆盖率 + 混底色（边缘有中间档，不阶梯）
		MODE_HARD = 1   // 平台原生 `fillRect(l,t,w,h,radius)`：直角以外是硬边（对照/兜底用）
	};

	/**形态 */
	enum Shape {
		SHAPE_RECT = 0,     // ★ 默认：矩形 + `Style::radius` 倒角（普通按钮）
		SHAPE_PILL = 1,     // 药丸：半径 = h/2 + 圆钮（开关；轨色用 Style.normal[关] / selected[开]）
		RECT = SHAPE_RECT,  // 别名（经需求方口径：setShape(RECT|PILL)）
		PILL = SHAPE_PILL
	};

	/**触摸动作码（业务把平台 MotionEvent 映射过来即可） */
	enum Touch {
		TOUCH_DOWN   = 0,
		TOUCH_UP     = 1,
		TOUCH_MOVE   = 2,
		TOUCH_CANCEL = 3
	};

	/**翻转回调（开关模式下每次状态真的翻转后触发一次） */
	typedef void (*ToggleCallback)(bool on, void *user);

	/**药丸形态的圆钮配置：钮位由 on/off 决定（左/右），内边距与钮色可配 */
	struct PillStyle {
		int padding;        // 圆钮与药丸边缘的内边距(px)；也是「钮位」的左右基准（默认 3）
		int knobDia;        // 圆钮直径(px)；<=0 → 自动 = h - 2*padding
		uint32_t knobOff;   // 关态钮色
		uint32_t knobOn;    // 开态钮色（默认与关态同色 = 白钮）
		PillStyle() : padding(3), knobDia(0), knobOff(0xFFFFFF), knobOn(0xFFFFFF) {}
	};

	/**统一结果类型（components/README.md 规范 2）：msg 说人话，禁止静默失败 */
	struct Result {
		int code;          // 0 = OK；<0 = 出错（什么都没改）
		std::string msg;
		Result() : code(0) {}
		Result(int c, const std::string &m) : code(c), msg(m) {}
		bool ok() const { return code == 0; }
	};

	/**样式 */
	struct Style {
		int radius;            // 圆角半径(px)；<=0 → 自动 = min(w,h)/3（药丸）；> min(w,h)/2 会被夹取
		uint32_t normal;       // 常态填充色（SHAPE_PILL 下 = 开关「关」的轨色）
		uint32_t pressed;      // 按下填充色（SHAPE_PILL 下不用它，改用按轨色压深 12%）
		uint32_t selected;     // 选中填充色（SHAPE_PILL 下 = 开关「开」的轨色）
		uint32_t disabled;     // 禁用填充色
		uint32_t border;       // 边框色；0 = 不画边框
		int borderWidth;       // 边框宽(px)，>=1
		uint32_t bg;           // ★ 按钮**背后**的底色（AA 混色基准，必须与画布/父容器实际底色一致）
		Mode mode;             // 圆角画法
		int aaSamples;         // 每像素每轴超采样数(2..16)：8 → 65 档覆盖率（默认 8）

		Style()
			: radius(12), normal(0x2196F3), pressed(0x1976D2), selected(0x0D47A1),
			  disabled(0xBDBDBD), border(0), borderWidth(1), bg(0xFFFFFF),
			  mode(MODE_AA), aaSamples(8) {}
	};

	RadButton();
	~RadButton();

	/* ---------------- 绑定 ---------------- */

	/**绑画布（`onUI_init` 里调；painter 空 → 非 0 + 人话 msg） */
	Result attach(ZKPainter *painter);
	/**解绑（`onUI_quit`） */
	void detach();
	bool isAttached() const { return mPainter != 0; }

	/* ---------------- 样式 ---------------- */

	Result setStyle(const Style &st);
	const Style &style() const { return mStyle; }
	/**默认样式（白底按钮 / 主题蓝四态 / 半径 12 / AA） */
	static Style defaultStyle() { return Style(); }

	/**改半径（<0 → 自动；等价于改 Style::radius 的前置动作，不自动重绘） */
	Result setRadius(int r);
	/**一次改四态色 + 边框色（border 省略 = 不改边框） */
	Result setColors(uint32_t normal, uint32_t pressed, uint32_t selected,
	                 uint32_t disabled, uint32_t border = 0);
	/**改画法（AA / HARD） */
	Result setMode(Mode m);

	/* ---------------- 状态 ---------------- */

	/**直接设状态（幂等：同状态重复调用不报错、不重绘） */
	Result setState(State s);
	State state() const { return mState; }
	/**状态名（打日志/上屏用）：NORMAL/PRESSED/SELECTED/DISABLED */
	const char *stateName() const;
	/**按当前状态取填充色 */
	uint32_t currentColor() const;

	/**
	 * @brief 按下 / 抬起（业务在触摸回调里调；也可以用 `onTouch()` 让包自己管）
	 * @param down true = 按下（记住按下前的状态 → 切 PRESSED）；false = 抬起（回到记住的状态）
	 * @note **幂等**：重复 `press(true)` 不会把「记住的状态」覆盖成 PRESSED；
	 *抬起后状态回到按下前那个（NORMAL / SELECTED / DISABLED 都能正确回落）。
	 */
	Result press(bool down);
	Result setSelected(bool on);           // = setState(on ? SELECTED : NORMAL)
	bool isSelected() const { return mState == SELECTED; }

	/* ---------------- 触摸（包自己算命中，业务只喂坐标） ---------------- */

	/**
	 * @brief 显式给「控件在屏幕上的矩形」（**绝对屏幕坐标**，与 `MotionEvent::mX/mY` 同口径）
	 *
	 * 为什么不自己取：`getAbsolutePosition()` / `getParent()` 设备端 libeasyui.so 未导出 →
	 * dlopen 失败 → 整屏黑（见本文件顶部铁律）。所以几何只能由业务给：
	 * 业务拿「祖先链上各层的 `getPosition()` 相加 + 本 painter 的 `getPosition()`」算出绝对矩形。
	 * @note width/height <= 0 → 退回用 painter 自身尺寸；
	 *未调过本函数 → `onTouch()` 恒 false（不消费，见 README 排错表）。
	 */
	Result setRect(int left, int top, int width, int height);
	/**读回上面给的矩形（未给过则全 0） */
	void getRect(int &left, int &top, int &width, int &height) const;
	bool hasRect() const { return mHasRect; }

	/**点是否落在控件矩形内（未给几何 → false） */
	bool hitTest(int x, int y) const;

	/**
	 * @brief 触摸事件入口（自带命中 + 按下态 + 移出取消 + 开关翻转 + 回调）
	 * @param x,y    **绝对屏幕坐标**（同 `setRect` 口径）
	 * @param action `TOUCH_DOWN` / `TOUCH_UP` / `TOUCH_MOVE` / `TOUCH_CANCEL`
	 * @return true = 本包**已消费**（业务应把这个事件吞掉，别再交给下面控件）；false = 没碰我，照常传下去
	 * @note 语义：
	 *   · DOWN 命中 → 进按下态（记住按下前状态）；
	 *   · MOVE 移出边界 → 取消按下态（`press(false)` 回落，幂等）；
	 *   · UP 仍在界内且 `switchable()`（开关模式）→ **翻转状态 + 触发 `setOnToggle` 回调**；
	 *   · UP 在界外 → 只回落，不翻转；
	 *   · `DISABLED` 状态 → 按下态照常显示，但**不翻转**；
	 *   · 默认 `setAutoRefresh(true)`：状态真的变了就顺手 `refresh()`（想自己控重绘就关掉）。
	 */
	bool onTouch(int x, int y, int action);
	/**当前是否处在按下态 */
	bool isDown() const { return mPressHeld; }
	/**关掉「状态变了自动重绘」（默认开；关掉后要自己调 refresh()） */
	void setAutoRefresh(bool on);

	/* ---------------- 开关语义（把倒角按钮当「带倒角的开关」用） ---------------- */

	/**开关模式：`onTouch` 的 UP 命中界内时翻转状态（`setShape(SHAPE_PILL)` 会自动打开） */
	Result setSwitchable(bool on);
	bool switchable() const { return mSwitchable; }

	/**置开关状态（= `setSelected`，**幂等**：同值重复调不报错、也不触发回调） */
	Result setOn(bool on);
	bool isOn() const { return mState == SELECTED; }
	/**翻转（幂等：已 DISABLED 时不翻转，返回 code=0 + 说明） */
	Result toggle();
	/**注册翻转回调（`cb` 传 0 = 摘掉）；`setOn()` 编程置位**不**触发回调 */
	Result setOnToggle(ToggleCallback cb, void *user);

	/* ---------------- 形态（矩形倒角 / 药丸开关） ---------------- */

	/**切换形态（PILL 会自动把 `switchable` 打开；不影响已设的 Style/PillStyle） */
	Result setShape(Shape s);
	Shape shape() const { return mShape; }
	/**药丸的圆钮配置（只在 SHAPE_PILL 下生效） */
	Result setPillStyle(const PillStyle &ps);
	const PillStyle &pillStyle() const { return mPill; }

	/* ---------------- 画 ---------------- */

	/**重绘（**必须显式调**：painter 不自动重绘；改半径/色/状态后、切页回来时都要调） */
	Result refresh();
	/**擦掉按钮占的矩形（业务想在按钮上叠自绘内容时先擦） */
	Result erase();

	/**当前几何（来自 painter 的 `getPosition()`；未 attach 全 0） */
	int width() const;
	int height() const;
	/**本次实际使用的半径（含「自动」与夹取结果；PILL → h/2） */
	int radiusPx() const;
	/**「自动半径」口径：min(w,h)/3，药丸 */
	static int autoRadius(int w, int h);

	/* ---------------- 工具（可独立用） ---------------- */

	/**两个颜色按百分比混（painter 无 alpha → 半透明的唯一替代；percentFg 0..100） */
	static uint32_t mix(uint32_t fg, uint32_t bg, int percentFg);

	/**
	 * @brief 在任意 painter 上画一个圆角矩形（本包核心；RadButton 内部也是调它）
	 * @param fill填充色；border 0 = 不画边框
	 * @param bg背后底色（AA 混色基准）
	 * @param mode         MODE_AA / MODE_HARD
	 * @param aaSamples每轴超采样数（2..16）
	 * @note 尺寸/半径任意；AA 模式下**只有圆角弧带**逐像素处理（直边仍是整块 fillRect），
	 *所以一次绘制大约 r*4 次 fillRect 量级（r=14 → ~120 次），不会拖慢界面。
	 * @note 画之前会**先用 `bg` 铺满整个控件盒**（原因：`erase()` 在设备上留的是不透明黑；
	 *且铺底后圆角外的像素与 AA 混色基准同色 → 边缘无色差）。
	 * @note 半径 = min(w,h)/2（正方形时）就是**正圆**：本包的药丸圆钮就是用这个口径画的（比 fillArc 边缘干净）。
	 */
	static Result drawRoundedRect(ZKPainter *painter, int left, int top, int width, int height,
	                              int radius, uint32_t fill, uint32_t border, int borderWidth,
	                              uint32_t bg, Mode mode = MODE_AA, int aaSamples = 8);

private:
	ZKPainter *mPainter;
	Style mStyle;
	State mState;
	State mPrevState;         // press(true) 时记住的「按下前状态」
	bool mPressHeld;          // 是否处在 press(true) 阶段（幂等用）

	Shape mShape;             // SHAPE_RECT / SHAPE_PILL
	PillStyle mPill;          // 药丸圆钮配置
	int mRect[4];             // 绝对屏幕矩形 { left, top, width, height }
	bool mHasRect;            // 是否调过 setRect
	bool mSwitchable;         // 开关模式（UP 界内翻转）
	bool mAutoRefresh;        // 状态变了是否自动 refresh
	ToggleCallback mCb;       // 翻转回调
	void *mCbUser;
};

} // namespace ui_v1
} // namespace zk

#endif /* _ZK_UI_V1_RADBUTTON_H_ */
