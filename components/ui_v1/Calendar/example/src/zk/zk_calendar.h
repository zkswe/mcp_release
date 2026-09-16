/*
 * zk_calendar.h — components/ui_v1/Calendar（源控件：lv_calendar · Android DatePicker · Qt QCalendarWidget · 小程序 picker mode=date）
 *
 * 唯一对外头文件。实现见 src/zk_calendar.cpp。
 *
 * 设计要点（为什么长这样）：
 *   ・平台**没有**日历控件（gap-list.md G-22 / L4）：日历 = **42 个 ZKTextView**（7 列 × 6 行）承载日号，
 *     翻月按钮用 ZKButton，月份标题用 1 个 ZKTextView —— 组件只负责「算日子 / 写文字 / 写高亮」。
 *   ・**painter 没有文字 API，textview 也没有点击回调**，所以：
 *       文字 → 组件写；点击 → 业务在 activity 触摸事件里用 `cellAt()/dayAt()` **反算命中格**（见 README §2 模板）。
 *   ・**绝对坐标**：设备侧 `libeasyui.so` **没有导出** `getParent()` / `getAbsolutePosition()`
 *     （用了编译链接都过、运行时整屏黑且无日志）——组件绝不调它们。
 *     组件只知道「格子在容器里的相对坐标」（`ZKBase::getPosition()`），
 *     容器原点（容器相对屏幕的左上角）由业务通过 `setContainer()/setContainerOrigin()` 提供。
 *     网格**直接铺在 activity 根/全屏 window** 时原点就是 (0,0)，可以不调。
 *   ・**选中高亮 = 文字色 + 独立的 `painter__N` 色块**（2026-09-16 修复「选中项看不见 / 白字白底」）：
 *     ZKTextView **画不出 backgroundColor**（json 的 bgColorTab 不画、`setBackgroundColor()`（含 alpha=FF）
 *     不画、`setBgStatusColor()` 不画 —— 三条路实测屏幕像素不变），而 `setBackgroundBmp()` 的运行时位图
 *     底色**「翻月重设」时会把应用搞崩**（无日志，实测 2026-09-16）—— 所以选中态的**色块底改由 painter 画**：
 *     `setHighlightPainter(painter__N)`，painter 是**42 格网格的同父兄弟**（z 必须比日号 textview 低），
 *     组件在**选中格的位置**画抗锯齿实心高亮（形状/内缩可配），格子文字仍由 ZKTextView 承载。
 *     ⚠️ **没接 highlight painter 也不会出现白字白底**：`refresh()` 会把选中文字自动换成
 *     `Style::selTextFallback` + 加粗（自检口径见 README §排错表）。
 *     `Style::markBg` 仍是「底色口径」（本代平台不生效）；`Style::cellBg` 兼作**高亮 painter 的基底色**
 *     （painter 无 alpha → 铺底 + 混色的唯一基准，必须 == 网格区域的真实底色）。
 *
 * 调用顺序（写死）：
 *   onUI_init : attach(...) → setContainer(...) → setStyle(...) → setOnDatePicked(...) → setToday/setMarkedDays → setDate(...) → refresh()
 *   翻月      : prevMonth()/nextMonth()（或 setMonth）→ refresh()
 *   点日号    : 在 activity 触摸事件里 cellAt/dayAt 反算 → pickDay(day) → refresh()
 */
#ifndef _ZK_UI_V1_CALENDAR_H_
#define _ZK_UI_V1_CALENDAR_H_

#include <stdint.h>
#include <string>

class ZKBase;
class ZKButton;
class ZKTextView;
class ZKPainter;

namespace zk {
namespace ui_v1 {

/**
 * @brief 日历选择器（42 个 textview 承载日号 + 触摸反算命中）
 *
 * 最短用法（完整示例见 example/）：
 * @code
 *   static zk::ui_v1::Calendar s_cal;
 *   static ZKTextView *s_cells[42] = { mTvCalD1Ptr, ..., mTvCalD42Ptr };   // 行优先 7 列 × 6 行
 *
 *   static void onDatePicked(const zk::ui_v1::Calendar::Date &d, void *user) {
 *       char buf[24]; snprintf(buf, sizeof(buf), "%04d-%02d-%02d", d.year, d.month, d.day);
 *       mEtDatePtr->setText(buf);                     // 回填输入框
 *   }
 *
 *   void onUI_init() {
 *       s_cal.setStyle(zk::ui_v1::Calendar::Style());   // 默认样式
 *       s_cal.attach(s_cells, mTvCalTitlePtr, mBtnCalPrevPtr, mBtnCalNextPtr);
 *       s_cal.setContainer(mWinCalPtr);                 // ★ 网格容器（见头文件顶部的「绝对坐标」说明）
 *       s_cal.setOnDatePicked(onDatePicked);
 *       s_cal.setToday(2026, 9, 16);                    // 「今天」高亮
 *       int marks[2] = { 5, 20 }; s_cal.setMarkedDays(marks, 2);
 *       s_cal.setDate(2026, 9, 0);                      // 定位到 2026-09，不选中（d==0）
 *       s_cal.refresh();                                // ★ 不调什么都不显示
 *   }
 *
 *   bool onmainActivityTouchEvent(const MotionEvent &ev) {      // ★ 组件不装触摸监听，业务自己反算
 *       if (ev.mActionStatus == MotionEvent::E_ACTION_UP && mWinCalPtr->isWndShow()) {
 *           int day = s_cal.dayAt(ev.mX, ev.mY);                  // 0 = 空格/未命中
 *           if (day > 0) { s_cal.pickDay(day); s_cal.refresh(); }  // 选中 + 回调 + 重绘
 *       }
 *       return false;
 *   }
 *   bool onButtonClick_BtnCalPrev(ZKButton *p) { s_cal.prevMonth(); s_cal.refresh(); return false; }
 * @endcode
 */
class Calendar {
public:
	/** 统一结果类型（components/README.md 规范 2）：msg 说人话，禁止静默失败 */
	struct Result {
		int code;          // 0 = OK；1 = 已接受但有降级（截断/忽略了非法值）；<0 = 出错
		std::string msg;
		Result() : code(0) {}
		Result(int c, const std::string &m) : code(c), msg(m) {}
		bool ok() const { return code == 0; }
	};

	/** 日期（month 1..12；day == 0 表示「未选中」） */
	struct Date {
		int year, month, day;
		Date() : year(0), month(0), day(0) {}
	};

	/** 网格规模：7 列 × 6 行 = 42 格（行优先，与 json 里摆放顺序一致） */
	enum { COLS = 7, ROWS = 6, CELLS = 42 };

	/**
	 * 样式
	 * @note 文字色各平台都能画；`selBg` 是**选中高亮块的填充色**（由 highlight painter 画，
	 *       见 `setHighlightPainter()`）；`cellBg` 兼作 painter 的**基底色**；`markBg` 本代平台不生效
	 *       （textview 画不出底色，详见头文件顶部平台事实）。
	 *       高亮实际生效的是 `selBg`（painter 色块）、`selText`（+选中加粗，或被 `selTextFallback` 顶替）、
	 *       `markText`、`mutedText`、`cellText`。
	 */
	struct Style {
		uint32_t selBg;      // 选中高亮块填充色（由 painter 画；未接 painter → 靠 selTextFallback 兜底）
		uint32_t selText;    // 选中格文字色
		uint32_t cellText;   // 普通日号文字色
		uint32_t mutedText;  // 「今天」文字色（未选中/未标记时用来标记今天；不想区分今天可设成 == cellText）
		uint32_t titleText;  // 月份标题文字色
		uint32_t markBg;     // 标记日底色（ARGB；本代平台不生效，见上）
		uint32_t markText;   // 标记日文字色
		uint32_t cellBg;     // 普通格底色 == **高亮 painter 的基底色**（painter 无 alpha，混色只能以它为准；
		                     //   ★ 必须 == 网格区域的真实底色，否则 painter 会露出一块色差方块）
		uint32_t selTextFallback;  // ★ 兜底选中文字色：**没接 highlight painter**（或自检发现
		                     //   selText ≈ 所在底色）时自动改用本色 + 加粗 —— 杜绝「文字色 ≈ 底色 = 看不见」
		bool     selBold;    // 选中日是否加粗（默认 true：底色画不出来时靠它拉开层次）
		Style()
			: selBg(0xFF2196F3), selText(0xFF1565C0), cellText(0xFF212121), mutedText(0xFF9E9E9E),
			  titleText(0xFF212121), markBg(0xFFFFF3CD), markText(0xFFB26A00), cellBg(0xFFFFFFFF),
			  selTextFallback(0xFF0D47A1), selBold(true) {}
	};

	/** 选中回调（**在 UI 线程、pickDay() 内部同步调用**；回调里可以读 date()、写输入框） */
	typedef void (*DatePickedFn)(const Date &d, void *user);

	/** 选中高亮块的形状（见 setHighlightShape） */
	enum HighlightShape {
		HIGHLIGHT_CIRCLE = 0,   // ★ 默认：圆（直径 = min(格宽,格高) - 2*inset），带抗锯齿
		HIGHLIGHT_SQUARE = 1    // 方：内缩矩形（边与像素网格对齐 → 硬边即精确，不需要 AA）
	};
	// 别名（口径同 RadButton::Shape 的 RECT/PILL）
	enum { CIRCLE = HIGHLIGHT_CIRCLE, SQUARE = HIGHLIGHT_SQUARE };

	Calendar();
	~Calendar();

	/* ---------------- 绑定 ---------------- */
	/**
	 * @brief 绑定控件（onUI_init 里，控件已创建之后调）
	 * @param cells 42 个日号 ZKTextView（行优先 7 列 × 6 行，**必须与 json 摆放顺序一致**）；允许个别为 NULL（画不出那格）
	 * @param title 月份标题 ZKTextView（可 NULL）；组件写 `"%d-%02d"`（如 `2026-09`）
	 * @param prev  上一月 ZKButton（可 NULL；组件**不接管点击**，业务回调里调 prevMonth()）
	 * @param next  下一月 ZKButton（可 NULL；同上）
	 * @return code: 0 OK / 1 有格子为 NULL（其余照常工作）/ -1 cells 为空 / -2 cells[0] 为空（拿不到网格几何）
	 */
	Result attach(ZKTextView *const cells[CELLS], ZKTextView *title = 0, ZKButton *prev = 0, ZKButton *next = 0);
	void detach();

	/**
	 * @brief 告诉组件「网格所在容器」（**绝对坐标命中的前提**，见头文件顶部说明）
	 * @param container 网格控件的**直接父容器**（通常就是那个 window / 卡片）；取其 `getPosition()` 作容器原点
	 * @note ★★ **网格在「非原点」容器里时这里必调**（如容器在 (162,40)）——不调则 `cellAt()/dayAt()`
	 *       的命中区域整体偏移容器原点，表现为「点日号没反应 / 点错一天」（不崩、不报错，极难查）。
	 *       容器本身还嵌在别的容器里时，用 `setContainerOrigin()` 传「所有祖先 getPosition() 之和」。
	 *       网格直接铺在 activity 根 / 全屏 window 上 → 原点 (0,0)，**可以不调**（默认就是 0,0）。
	 *       自检：`hasContainer()` 为 false 且网格不在原点 → 就是漏调。
	 */
	Result setContainer(ZKBase *container);
	/** 直接给容器原点（容器相对屏幕的左上角，像素）；等价于 setContainer，用于嵌套容器 */
	Result setContainerOrigin(int x, int y);
	/** 是否已经给过容器原点（没给也能用，但只对「原点 (0,0)」的摆法正确） */
	bool hasContainer() const { return mContainerSet; }

	/* ---------------- 日期 ---------------- */
	/** 定位日期；**d == 0 → 只定位月份、不选中**；d 超出当月天数 → 返回 -2 且不改状态 */
	Result setDate(int y, int m, int d);
	/** 当前状态（未选中时 day == 0） */
	Date date() const;
	/** 翻月（**不触发 DatePickedFn**；已选日号在新月份不存在时会被清成 0） */
	Result setMonth(int y, int m);
	Result prevMonth();
	Result nextMonth();

	/* ---------------- 选中 / 标记 / 今天 ---------------- */
	/** 选中回调（可 NULL = 取消注册） */
	void setOnDatePicked(DatePickedFn fn, void *user = 0);
	/** 编程选中某日（day 1..当月天数）；**会触发 DatePickedFn** */
	Result pickDay(int day);
	/** 标记日（月份内的日号；n <= 0 = 清空；不在当月的日号会被忽略并在 msg 里说明） */
	Result setMarkedDays(const int *days, int n);
	/** 「今天」高亮（d == 0 → 关闭） */
	Result setToday(int y, int m, int d);
	/** 某日号在当前月里是第几格（0..41；不在当月或标记不到 → -1） */
	int cellIndexOfDay(int day) const;

	/* ---------------- 命中反算（业务在 activity 触摸事件里调） ---------------- */
	/**
	 * @brief 屏幕**绝对坐标** → 格下标 0..41
	 * @return 0..41；**-1** = 未命中（在网格外、落在格子间隙、或还没 attach）。
	 *         实现只用 `getPosition()` 累加（容器原点 + 首格相对位置），**不调 getParent()/getAbsolutePosition()**。
	 */
	int cellAt(int absX, int absY) const;
	/** 屏幕绝对坐标 → 日号（**0 = 空格或未命中**） */
	int dayAt(int absX, int absY) const;

	/* ---------------- 选中高亮色块（painter 自绘） ----------------
	 * 为什么需要：本代平台 textview 画不出底色（见头文件顶部）→ 业务设的「主题色底 + 白字」里的底
	 * 根本没画，白字落在白卡上 = **选中项看不见**（Z21 真机实测 2026-09-16）。改由 painter 画实心块。
	 */
	/**
	 * @brief 接选中高亮画布（json 里的 `painter__N`：**必须与 42 格同父**、z 比日号 textview 低）
	 * @param p painter 指针；传 NULL 等价 `detachHighlightPainter()`
	 * @return code: 0 OK / -1 p 为空（已 detach）/ -2 painter 尺寸为 0（json position 没写 width/height）
	 * @note **幂等**：重复接同一个 painter、或中途换一个 painter，都直接生效（不需要先 detach）。
	 *       语义 = 「在**选中格的位置**画实心高亮」，填充色 = `Style::selBg`，几何 = 选中格 `getPosition()`
	 *       相对 painter 左上角 + `setHighlightShape()` / `setHighlightInset()`。
	 *       基底：painter 无 alpha，`erase()` 在设备上是**不透明黑** → 组件先把 painter 整块铺
	 *       `Style::cellBg`（= 该区域真实底色），再在上面混色画高亮（这样才能得到抗锯齿边缘）。
	 *       **painter 不自动重绘**：切月/改选中/改样式后跟文字一样必须 `refresh()`（口径一致）。
	 */
	Result setHighlightPainter(ZKPainter *p);
	/** 断开高亮画布（回到「只写文字色 + selTextFallback 兜底」的降级态；画布上已画的像素不擦） */
	void detachHighlightPainter();
	bool hasHighlightPainter() const { return mHlPainter != 0; }

	/**
	 * @brief 高亮形状（默认 `HIGHLIGHT_CIRCLE` = 圆）
	 * @return code: 0 OK / -1 非法枚举（继续用原形状）
	 * @note 圆走**抗锯齿**（逐像素覆盖率 + 与 `Style::cellBg` 混色，~65 档中间色）；
	 *       方是内缩矩形，边与像素网格对齐 → 硬边即精确。
	 */
	Result setHighlightShape(HighlightShape s);
	HighlightShape highlightShape() const { return mHlShape; }

	/**
	 * @brief 高亮块相对格子四边的内缩（px，默认 2；夹到 0..min(格宽,格高)/2）
	 * @return code: 0 OK / 1 越界已夹到合法范围（msg 说明）/ -1 负数
	 */
	Result setHighlightInset(int px);
	int highlightInset() const { return mHlInset; }

	/**
	 * @brief 上一次 `refresh()` 记下的自检告警（空 = 无）
	 * @note 例：「selText 与底色太近（都≈白）→ 选中文字改用 selTextFallback」。
	 *       `refresh()` 的 Result.msg 里同样带这句人话；本接口给「不想每次判 code」的业务用。
	 */
	const std::string &lastWarning() const { return mLastWarn; }

	/* ---------------- 刷新 ---------------- */
	/**
	 * @brief 重建网格文字 + 高亮（**改月/改选中/改标记/改今天之后必须调，否则界面不变**）
	 * @return code: 0 OK / 1 OK 但走了兜底（选中文字色被换成 `selTextFallback`，msg 说明原因，
	 *               同句可取 `lastWarning()`）/ -2 接了 painter 但尺寸为 0（高亮画不出来）/ -1 未 attach
	 */
	Result refresh();

	void setStyle(const Style &st);
	const Style &style() const { return mStyle; }

private:
	Calendar(const Calendar &);
	Calendar &operator=(const Calendar &);

	static bool isLeap(int y);
	static int daysInMonth(int y, int m);
	static int weekdayOfFirst(int y, int m);     // 0 = 周一 .. 6 = 周日
	void recalcMap();                            // 重算 mDayMap（0 = 空格）
	bool isMarked(int day) const;
	bool isToday(int day) const;
	bool isValidDate(int y, int m, int d) const;
	bool validYM(int y, int m) const;

	/* 高亮色块用小工具（AA 与 RadButton 同一套口径：覆盖率 → 与已知底色混色） */
	static uint32_t mixCov(uint32_t fg, uint32_t bg, double t);
	static double   circleCoverage(int px, int py, double cx, double cy, double r, int ss);
	static int      luma(uint32_t c);
	void paintHighlight();          // 铺基底色 + 画选中格高亮（refresh() 内部调）

	ZKTextView *mCells[CELLS];
	ZKTextView *mTitle;
	ZKButton *mPrev;
	ZKButton *mNext;
	ZKPainter *mHlPainter;          // 选中高亮画布（NULL = 降级态：只写文字色 + 兜底）
	HighlightShape mHlShape;        // 高亮形状
	int mHlInset;                   // 高亮内缩（px）
	std::string mLastWarn;          // 上一次 refresh 的自检告警（空 = 无）

	int mGridX, mGridY;        // 首格在**容器**里的左上角
	int mStepX, mStepY;        // 列/行步进（由 cells[0]/[1]/[7] 反推，支持格子间隙）
	int mCellW, mCellH;        // 单格尺寸
	int mOriginX, mOriginY;    // 容器原点（**屏幕绝对**），默认 (0,0)
	bool mContainerSet;

	int mYear, mMonth, mDay;   // mDay == 0 → 未选中
	int mTodayY, mTodayM, mTodayD;   // 全 0 = 关闭今天高亮
	bool mMarked[32];
	int mDayMap[CELLS];        // 0 = 空格
	bool mLastBold[CELLS];     // 上一帧「加粗」状态（避免每帧都写，省一次控件调用）

	DatePickedFn mFn;
	void *mUser;

	Style mStyle;
	bool mAttached;
};

} // namespace ui_v1
} // namespace zk

#endif /* _ZK_UI_V1_CALENDAR_H_ */
