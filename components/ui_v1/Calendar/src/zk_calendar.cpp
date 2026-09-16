/*
 * zk_calendar.cpp — components/ui_v1/Calendar 实现
 *
 * 提炼来源（只读参考，未改动原工程）：
 *   projects/translate/lvgl-widgets/z21/src/logic/mainLogic.cc
 *     ・daysInMonth() / weekdayOfFirst()   月天数与「1 号是周几」
 *     ・bindCalCells() / rebuildCalendar()  42 个 textview 建网格 + 写日号（空格 setText("")）
 *     ・highlightCal()                       选中格样式切换
 *     ・applyCalDate()                        选中回填（本组件改为 DatePickedFn 回调，由业务回填）
 *     ・触摸命中：窗口矩形 + 网格几何反算 (col,row)（本组件收成 cellAt/dayAt）
 *
 * 两条平台硬约束（决定实现长什么样）：
 *   ① 设备侧 libeasyui.so **没有导出** getParent() / getAbsolutePosition() —— 用了编译链接都过、
 *      运行时加载失败（整屏黑、无日志）。所以绝对坐标 = 「容器原点（业务给） + 首格相对坐标（getPosition）」。
 *   ② textview 没有点击回调、painter 没有文字 API —— 组件只管写文字/样式，命中由业务反算。
 *
 * 高亮实现（2026-09-16 起 = painter 色块；同日 Z21 实测口径）：
 *   ・**ZKTextView 不画 backgroundColor**：json 的 bgColorTab 不画、setBackgroundColor()（含 alpha=FF）不画、
 *     setBgStatusColor() 也不画 —— 这几条路都试过，屏幕像素不变；
 *   ・`setBackgroundBmp()`（运行时生成小位图）**能画**（首帧可见），但**翻月时重设底色会把应用搞崩**
 *     （无任何日志；试过「同指针跳过」「每格独占位图」两种写法都崩）→ 不采用；
 *   ・所以选中态的**色块底改由独立 painter 画**（`setHighlightPainter()`）：painter 是 42 格的同父兄弟、
 *     z 比日号低，在选中格位置画实心高亮（圆带抗锯齿 / 方可硬边），文字仍由 textview 承载。
 *   ・**防呆保底**：没接 painter（或 selText 与所在底色太近）→ 选中文字自动换 `selTextFallback` + 加粗，
 *     绝不允许「文字色 ≈ 底色 = 看不见」（案例实测过的白字白底事故，见 README §排错表）。
 *   ・抗锯齿口径与 RadButton 同一套（painter 无 alpha）：画笔只有不透明 fill，
 *     于是**先铺已知底色**（`Style::cellBg`），再按**逐像素覆盖率**与它混色 —— 这是唯一的「半透明」。
 */
#include "zk/zk_calendar.h"

#include <stdio.h>
#include <string.h>

#include <control/ZKButton.h>
#include <control/ZKPainter.h>
#include <control/ZKTextView.h>

#include <math.h>

namespace zk {
namespace ui_v1 {

/* ============================ 构造 / 析构 ============================ */
Calendar::Calendar()
	: mTitle(0), mPrev(0), mNext(0),
	  mHlPainter(0), mHlShape(HIGHLIGHT_CIRCLE), mHlInset(2),
	  mGridX(0), mGridY(0), mStepX(0), mStepY(0), mCellW(0), mCellH(0),
	  mOriginX(0), mOriginY(0), mContainerSet(false),
	  mYear(2000), mMonth(1), mDay(0),
	  mTodayY(0), mTodayM(0), mTodayD(0),
	  mFn(0), mUser(0), mAttached(false) {
	for (int i = 0; i < CELLS; ++i) {
		mCells[i] = 0;
		mDayMap[i] = 0;
		mLastBold[i] = false;
	}
	memset(mMarked, 0, sizeof(mMarked));
}

Calendar::~Calendar() {}

/* ============================ 日历算术 ============================ */
bool Calendar::isLeap(int y) {
	return (y % 4 == 0 && y % 100 != 0) || (y % 400 == 0);
}

int Calendar::daysInMonth(int y, int m) {
	static const int d[12] = { 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31 };
	if (m < 1 || m > 12) {
		return 0;
	}
	if (m == 2 && isLeap(y)) {
		return 29;
	}
	return d[m - 1];
}

/* 0 = 周一 .. 6 = 周日（与案例一致；json 表头按 一 二 三 四 五 六 日 摆） */
int Calendar::weekdayOfFirst(int y, int m) {
	static const int t[12] = { 0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4 };
	int yy = y;
	if (m < 3) {
		yy -= 1;
	}
	int w = (yy + yy / 4 - yy / 100 + yy / 400 + t[m - 1] + 1) % 7;   /* 0 = 周日 */
	return (w + 6) % 7;
}

bool Calendar::validYM(int y, int m) const {
	return (m >= 1 && m <= 12 && y >= 1900 && y <= 2999);
}

bool Calendar::isValidDate(int y, int m, int d) const {
	if (!validYM(y, m)) {
		return false;
	}
	return (d >= 0 && d <= daysInMonth(y, m));
}

bool Calendar::isMarked(int day) const {
	return (day >= 1 && day <= 31 && mMarked[day]);
}

bool Calendar::isToday(int day) const {
	return (mTodayD != 0 && day == mTodayD && mYear == mTodayY && mMonth == mTodayM);
}

void Calendar::recalcMap() {
	for (int i = 0; i < CELLS; ++i) {
		mDayMap[i] = 0;
	}
	if (!validYM(mYear, mMonth)) {
		return;
	}
	const int offset = weekdayOfFirst(mYear, mMonth);
	const int dim = daysInMonth(mYear, mMonth);
	for (int d = 1; d <= dim; ++d) {
		const int idx = offset + d - 1;
		if (idx >= 0 && idx < CELLS) {
			mDayMap[idx] = d;
		}
	}
}

/* ============================ 绑定 ============================ */
Calendar::Result Calendar::attach(ZKTextView *const cells[CELLS], ZKTextView *title,
                                  ZKButton *prev, ZKButton *next) {
	if (cells == 0) {
		return Result(-1, "Calendar::attach: cells 为空 —— 传 42 个日号 textview 的数组");
	}
	if (cells[0] == 0) {
		return Result(-2, "Calendar::attach: cells[0] 为空 —— 首格用来反推网格几何，不能省");
	}
	int miss = 0;
	for (int i = 0; i < CELLS; ++i) {
		mCells[i] = cells[i];
		if (cells[i] == 0) {
			++miss;
		}
	}
	mTitle = title;
	mPrev = prev;
	mNext = next;

	/* 网格几何：首格相对容器的位置 + 行列步进（用 cells[1] / cells[7] 反推，支持格子间留缝） */
	{
		const LayoutPosition &p0 = cells[0]->getPosition();
		mGridX = p0.mLeft;
		mGridY = p0.mTop;
		mCellW = p0.mWidth;
		mCellH = p0.mHeight;
		if (mCellW <= 0) {
			mCellW = 1;
		}
		if (mCellH <= 0) {
			mCellH = 1;
		}
		mStepX = mCellW;
		mStepY = mCellH;
		if (cells[1] != 0) {
			const LayoutPosition &p1 = cells[1]->getPosition();
			if (p1.mLeft - p0.mLeft > 0) {
				mStepX = p1.mLeft - p0.mLeft;
			}
		}
		if (cells[COLS] != 0) {
			const LayoutPosition &p7 = cells[COLS]->getPosition();
			if (p7.mTop - p0.mTop > 0) {
				mStepY = p7.mTop - p0.mTop;
			}
		}
	}

	mAttached = true;
	recalcMap();
	if (miss > 0) {
		char buf[128];
		snprintf(buf, sizeof(buf),
		         "Calendar::attach: 有 %d 个格子传了 NULL（那几格不写文字/样式，其余照常）", miss);
		return Result(1, buf);
	}
	return Result(0, "ok");
}

void Calendar::detach() {
	for (int i = 0; i < CELLS; ++i) {
		mCells[i] = 0;
	}
	mTitle = 0;
	mPrev = 0;
	mNext = 0;
	mHlPainter = 0;          /* 画布也一起摘掉（退出时整控件树都要没了） */
	mAttached = false;
	mLastWarn.clear();
}

Calendar::Result Calendar::setContainer(ZKBase *container) {
	if (container == 0) {
		return Result(-1, "Calendar::setContainer: container 为空（不想传指针就用 setContainerOrigin(x, y)）");
	}
	const LayoutPosition &p = container->getPosition();
	mOriginX = p.mLeft;
	mOriginY = p.mTop;
	mContainerSet = true;
	return Result(0, "ok");
}

Calendar::Result Calendar::setContainerOrigin(int x, int y) {
	mOriginX = x;
	mOriginY = y;
	mContainerSet = true;
	return Result(0, "ok");
}

/* ============================ 选中高亮色块（painter） ============================ */

/* 前景 fg 与底色 bg 按 t（0..1 = 前景权重）混色。painter 无 alpha → 这是唯一的「半透明」实现 */
uint32_t Calendar::mixCov(uint32_t fg, uint32_t bg, double t) {
	if (t <= 0.0) {
		return bg & 0xFFFFFF;
	}
	if (t >= 1.0) {
		return fg & 0xFFFFFF;
	}
	const double it = 1.0 - t;
	int r = (int)(((fg >> 16) & 0xFF) * t + ((bg >> 16) & 0xFF) * it + 0.5);
	int g = (int)(((fg >> 8) & 0xFF) * t + ((bg >> 8) & 0xFF) * it + 0.5);
	int b = (int)((fg & 0xFF) * t + (bg & 0xFF) * it + 0.5);
	if (r < 0) r = 0; if (r > 255) r = 255;
	if (g < 0) g = 0; if (g > 255) g = 255;
	if (b < 0) b = 0; if (b > 255) b = 255;
	return (uint32_t)((r << 16) | (g << 8) | b);
}

/* 像素 [px,px+1) x [py,py+1) 落在圆内的面积占比（= 覆盖率）。ss x ss 超采样（8 → 65 档中间色） */
double Calendar::circleCoverage(int px, int py, double cx, double cy, double r, int ss) {
	if (r <= 0.0) {
		return 0.0;
	}
	const double inv = 1.0 / (double)ss;
	const double area = 1.0 / (double)(ss * ss);
	const double r2 = r * r;
	int hit = 0;
	for (int i = 0; i < ss; ++i) {
		const double x = (double)px + (i + 0.5) * inv;
		const double dx = x - cx;
		for (int j = 0; j < ss; ++j) {
			const double y = (double)py + (j + 0.5) * inv;
			const double dy = y - cy;
			if (dx * dx + dy * dy <= r2) {
				++hit;
			}
		}
	}
	return (double)hit * area;
}

/* 感知亮度（0..255）：自检「文字色是否与所在底色太近」用 */
int Calendar::luma(uint32_t c) {
	return (int)(0.299 * ((c >> 16) & 0xFF) + 0.587 * ((c >> 8) & 0xFF) + 0.114 * (c & 0xFF) + 0.5);
}

Calendar::Result Calendar::setHighlightPainter(ZKPainter *p) {
	if (p == 0) {
		detachHighlightPainter();
		return Result(-1, "Calendar::setHighlightPainter: painter 为空（想摘掉画布就用 detachHighlightPainter()）");
	}
	const LayoutPosition &pos = p->getPosition();
	mHlPainter = p;
	if (pos.mWidth <= 0 || pos.mHeight <= 0) {
		return Result(-2, "Calendar::setHighlightPainter: painter 尺寸为 0（json 里 position 的 width/height 没写）"
		                  " —— 高亮画不出来，选中文字会走 selTextFallback 兜底");
	}
	return Result(0, "ok（记得 refresh() 才可见；painter 不自动重绘）");
}

void Calendar::detachHighlightPainter() {
	mHlPainter = 0;
}

Calendar::Result Calendar::setHighlightShape(HighlightShape s) {
	if (s != HIGHLIGHT_CIRCLE && s != HIGHLIGHT_SQUARE) {
		return Result(-1, "Calendar::setHighlightShape: 只支持 HIGHLIGHT_CIRCLE / HIGHLIGHT_SQUARE");
	}
	mHlShape = s;
	return Result(0, "ok（记得 refresh()）");
}

Calendar::Result Calendar::setHighlightInset(int px) {
	if (px < 0) {
		return Result(-1, "Calendar::setHighlightInset: 内缩不能为负（0 = 贴满格子）");
	}
	/* 上界 = 半格（再大高亮就没了）；格宽高此时可能还没 attach，用保守的 64 先夹 */
	int lim = 64;
	if (mCells[0] != 0) {
		const LayoutPosition &p0 = mCells[0]->getPosition();
		const int m = (p0.mWidth < p0.mHeight ? p0.mWidth : p0.mHeight) / 2;
		if (m > 0) {
			lim = m;
		}
	}
	if (px > lim) {
		mHlInset = lim;
		char buf[160];
		snprintf(buf, sizeof(buf),
		         "Calendar::setHighlightInset: %d 超过半格上限 %d，已夹到 %d（再大高亮块就没了）", px, lim, lim);
		return Result(1, buf);
	}
	mHlInset = px;
	return Result(0, "ok（记得 refresh()）");
}

/* 铺基底色 + 画选中格高亮。调用者：refresh()。
 * 为什么每次都整块铺底：painter 无 alpha，其 `erase()` 在设备上留的是**不透明黑**
 * （实测口径同 RadButton）→ 「透明」只能靠「拿真实底色铺满」来模拟；不铺的话上一帧的高亮去不掉。 */
void Calendar::paintHighlight() {
	if (mHlPainter == 0) {
		return;
	}
	const LayoutPosition &pp = mHlPainter->getPosition();
	const int pw = pp.mWidth;
	const int ph = pp.mHeight;
	if (pw <= 0 || ph <= 0) {
		return;
	}
	const uint32_t bg = mStyle.cellBg & 0xFFFFFF;
	mHlPainter->setSourceColor(bg);
	mHlPainter->fillRect(0, 0, pw, ph, 0);

	if (mDay == 0) {
		return;                                   /* 未选中 → 只剩基底色 */
	}
	const int idx = cellIndexOfDay(mDay);
	if (idx < 0 || mCells[idx] == 0) {
		return;
	}
	const LayoutPosition &cp = mCells[idx]->getPosition();
	/* ★ 前提：painter 与 42 格**同父**。设备端不导出 getParent() → 不同父无法换算（见 README §5） */
	const int cl = cp.mLeft - pp.mLeft;
	const int ct = cp.mTop - pp.mTop;
	const int cw = cp.mWidth;
	const int ch = cp.mHeight;
	if (cw <= 0 || ch <= 0) {
		return;
	}

	if (mHlShape == HIGHLIGHT_SQUARE) {
		const int l = cl + mHlInset;
		const int t = ct + mHlInset;
		const int w = cw - 2 * mHlInset;
		const int h = ch - 2 * mHlInset;
		if (w <= 0 || h <= 0) {
			return;
		}
		mHlPainter->setSourceColor(mStyle.selBg & 0xFFFFFF);
		mHlPainter->fillRect(l, t, w, h, 0);      /* 边与像素网格对齐 → 硬边即精确，无需 AA */
		return;
	}

	/* 圆：逐像素覆盖率 → 与基底色混色 → 按行合并同色像素成 span 再一次 fillRect
	 * （口径同 RadButton::paintCornerBox；圆直径 = min(格宽,格高) - 2*inset） */
	const int dia = (cw < ch ? cw : ch) - 2 * mHlInset;
	if (dia <= 0) {
		return;
	}
	const double r = dia / 2.0;
	const double cx = cl + cw / 2.0;
	const double cy = ct + ch / 2.0;
	const uint32_t fg = mStyle.selBg & 0xFFFFFF;
	const int bx0 = (int)(cx - r) - 1;
	const int bx1 = (int)(cx + r) + 1;
	const int by0 = (int)(cy - r) - 1;
	const int by1 = (int)(cy + r) + 1;
	for (int py = by0; py <= by1; ++py) {
		if (py < 0 || py >= ph) {
			continue;
		}
		uint32_t runColor = 0;
		int runX = 0, runLen = 0;
		for (int px = bx0; px <= bx1 + 1; ++px) {          /* px == bx1+1 是收尾哨兵 */
			uint32_t col = 0;
			bool draw = false;
			if (px <= bx1 && px >= 0 && px < pw) {
				const double cov = circleCoverage(px, py, cx, cy, r, 8);
				if (cov > 0.004) {
					draw = true;
					col = (cov >= 0.996) ? fg : mixCov(fg, bg, cov);
				}
			}
			if (draw && runLen > 0 && col == runColor && px == runX + runLen) {
				++runLen;
				continue;
			}
			if (runLen > 0) {
				mHlPainter->setSourceColor(runColor);
				mHlPainter->fillRect(runX, py, runLen, 1);
				runLen = 0;
			}
			if (draw) {
				runColor = col;
				runX = px;
				runLen = 1;
			}
		}
	}
}

/* ============================ 日期 ============================ */
Calendar::Result Calendar::setDate(int y, int m, int d) {
	if (!validYM(y, m)) {
		char buf[128];
		snprintf(buf, sizeof(buf), "Calendar::setDate: 月份越界（y=%d m=%d，月份取 1..12、年份 1900..2999）", y, m);
		return Result(-1, buf);
	}
	if (d < 0 || d > daysInMonth(y, m)) {
		char buf[160];
		snprintf(buf, sizeof(buf), "Calendar::setDate: %d-%02d 没有 %d 日（当月 %d 天）",
		         y, m, d, daysInMonth(y, m));
		return Result(-2, buf);
	}
	mYear = y;
	mMonth = m;
	mDay = d;
	recalcMap();
	return Result(0, "ok（记得 refresh() 才可见）");
}

Calendar::Date Calendar::date() const {
	Date d;
	d.year = mYear;
	d.month = mMonth;
	d.day = mDay;
	return d;
}

Calendar::Result Calendar::setMonth(int y, int m) {
	int yy = y;
	int mm = m;
	bool fixed = false;
	while (mm < 1) { mm += 12; yy -= 1; fixed = true; }
	while (mm > 12) { mm -= 12; yy += 1; fixed = true; }
	if (!validYM(yy, mm)) {
		char buf[128];
		snprintf(buf, sizeof(buf), "Calendar::setMonth: 年份越界（算出 y=%d m=%d，年份取 1900..2999）", yy, mm);
		return Result(-1, buf);
	}
	mYear = yy;
	mMonth = mm;
	/* 翻月不触发回调；已选日号在新月份不存在时清成「未选中」（避免跨月高亮错日号） */
	bool cleared = false;
	if (mDay > daysInMonth(mYear, mMonth)) {
		mDay = 0;
		cleared = true;
	}
	recalcMap();
	if (fixed) {
		char buf[160];
		snprintf(buf, sizeof(buf), "Calendar::setMonth: 月份 %d 已归一为 %d-%02d（翻月不触发回调；记得 refresh()）",
		         m, mYear, mMonth);
		return Result(1, buf);
	}
	if (cleared) {
		return Result(1, "Calendar::setMonth: 原选中日号在新月份不存在，已清成未选中（记得 refresh()）");
	}
	return Result(0, "ok（翻月不触发回调；记得 refresh() 才可见）");
}

Calendar::Result Calendar::prevMonth() {
	int y = mYear;
	int m = mMonth - 1;
	if (m < 1) {
		m = 12;
		y -= 1;
	}
	return setMonth(y, m);
}

Calendar::Result Calendar::nextMonth() {
	int y = mYear;
	int m = mMonth + 1;
	if (m > 12) {
		m = 1;
		y += 1;
	}
	return setMonth(y, m);
}

/* ============================ 选中 / 标记 / 今天 ============================ */
void Calendar::setOnDatePicked(DatePickedFn fn, void *user) {
	mFn = fn;
	mUser = user;
}

Calendar::Result Calendar::pickDay(int day) {
	const int dim = daysInMonth(mYear, mMonth);
	if (day < 1 || day > dim) {
		char buf[160];
		snprintf(buf, sizeof(buf), "Calendar::pickDay: %d 不在 %d-%02d 里（当月 1..%d）",
		         day, mYear, mMonth, dim);
		return Result(-1, buf);
	}
	mDay = day;
	recalcMap();
	if (mFn != 0) {
		Date d = date();
		mFn(d, mUser);
	}
	return Result(0, "ok（记得 refresh() 才看得见高亮）");
}

Calendar::Result Calendar::setMarkedDays(const int *days, int n) {
	memset(mMarked, 0, sizeof(mMarked));
	if (days == 0 || n <= 0) {
		return Result(0, "ok（已清空标记）");
	}
	const int dim = daysInMonth(mYear, mMonth);
	int ignored = 0;
	int firstBad = 0;
	for (int i = 0; i < n; ++i) {
		const int d = days[i];
		if (d >= 1 && d <= 31 && d <= dim) {
			mMarked[d] = true;
		} else {
			if (ignored == 0) {
				firstBad = d;
			}
			++ignored;
		}
	}
	if (ignored > 0) {
		char buf[160];
		snprintf(buf, sizeof(buf),
		         "Calendar::setMarkedDays: 有 %d 个日号不在 %d-%02d（当月 1..%d，首个非法值 %d），已忽略",
		         ignored, mYear, mMonth, dim, firstBad);
		return Result(1, buf);
	}
	return Result(0, "ok（记得 refresh() 才可见）");
}

Calendar::Result Calendar::setToday(int y, int m, int d) {
	if (d == 0) {
		mTodayY = mTodayM = mTodayD = 0;
		return Result(0, "ok（已关闭「今天」高亮；记得 refresh()）");
	}
	if (!isValidDate(y, m, d) || d < 1) {
		char buf[160];
		snprintf(buf, sizeof(buf), "Calendar::setToday: 非法日期 y=%d m=%d d=%d（月份 1..12、日 1..当月天数；d=0 关闭）",
		         y, m, d);
		return Result(-1, buf);
	}
	mTodayY = y;
	mTodayM = m;
	mTodayD = d;
	return Result(0, "ok（记得 refresh() 才可见）");
}

int Calendar::cellIndexOfDay(int day) const {
	if (day < 1) {
		return -1;
	}
	for (int i = 0; i < CELLS; ++i) {
		if (mDayMap[i] == day) {
			return i;
		}
	}
	return -1;
}

/* ============================ 命中反算 ============================ */
int Calendar::cellAt(int absX, int absY) const {
	if (!mAttached) {
		return -1;
	}
	/* 绝对坐标 = 容器原点（业务给） + 首格相对容器坐标（getPosition）
	 * —— 绝不用 getParent()/getAbsolutePosition()（设备侧 libeasyui.so 未导出） */
	const int gx = mOriginX + mGridX;
	const int gy = mOriginY + mGridY;
	if (mStepX <= 0 || mStepY <= 0) {
		return -1;
	}
	const int dx = absX - gx;
	const int dy = absY - gy;
	if (dx < 0 || dy < 0) {
		return -1;
	}
	const int col = dx / mStepX;
	const int row = dy / mStepY;
	if (col < 0 || col >= COLS || row < 0 || row >= ROWS) {
		return -1;
	}
	/* 落在格子与格子的间隙里 → 不算命中（业务什么都不做比点错日号好） */
	if (dx - col * mStepX >= mCellW || dy - row * mStepY >= mCellH) {
		return -1;
	}
	return row * COLS + col;
}

int Calendar::dayAt(int absX, int absY) const {
	const int idx = cellAt(absX, absY);
	if (idx < 0) {
		return 0;
	}
	return mDayMap[idx];
}

/* ============================ 刷新 ============================ */
Calendar::Result Calendar::refresh() {
	if (!mAttached) {
		return Result(-1, "Calendar::refresh: 未 attach（先 attach(cells, title, prev, next)）");
	}
	recalcMap();
	mLastWarn.clear();

	/* ---------- 自检（硬规则）：选中文字色绝不允许 ≈ 它所在的底色 ----------
	 *   接了 painter       → 文字落在 **selBg 色块**上，比的是 selText vs selBg；
	 *   没接 painter       → selBg 根本没画，文字落在 **cellBg** 上，比的是 selText vs cellBg。
	 * 命中任一条 → 选中文字改用 Style::selTextFallback + 加粗，并把人话写进 Result.msg / lastWarning()。
	 * （2026-09-16 事故：案例设了「主题色底 + 白字」，但本代平台 textview 画不出底色 → 白字落在白卡上） */
	const bool hlOk = (mHlPainter != 0) && (mHlPainter->getPosition().mWidth > 0)
	                  && (mHlPainter->getPosition().mHeight > 0);
	const int hlZero = (mHlPainter != 0 && !hlOk) ? 1 : 0;
	const uint32_t selOn = hlOk ? (mStyle.selBg & 0xFFFFFF) : (mStyle.cellBg & 0xFFFFFF);
	bool useFallback = !hlOk;
	int lumaGap = 0;
	if (hlOk) {
		lumaGap = luma(mStyle.selText & 0xFFFFFF) - luma(selOn);
		if (lumaGap < 0) {
			lumaGap = -lumaGap;
		}
		if (lumaGap <= 40) {
			useFallback = true;
		}
	}
	const uint32_t selFg = useFallback ? (mStyle.selTextFallback & 0xFFFFFF) : (mStyle.selText & 0xFFFFFF);
	if (useFallback) {
		char buf[256];
		if (!hlOk) {
			if (hlZero) {
				snprintf(buf, sizeof(buf),
				         "Calendar::refresh: 高亮 painter 尺寸为 0（json position 缺 width/height）→ 色块底画不出来，"
				         "选中文字已回落 selTextFallback(0x%06X) + 加粗（否则白字+白底=看不见）",
				         (unsigned)(mStyle.selTextFallback & 0xFFFFFF));
			} else {
				snprintf(buf, sizeof(buf),
				         "Calendar::refresh: 未接高亮 painter（setHighlightPainter）→ 本代平台 textview 画不出底色，"
				         "选中文字已回落 selTextFallback(0x%06X) + 加粗（否则 selText+cellBg 同色=看不见）",
				         (unsigned)(mStyle.selTextFallback & 0xFFFFFF));
			}
		} else {
			snprintf(buf, sizeof(buf),
			         "Calendar::refresh: selText 与 selBg 底色太近（亮度差 %d <= 40）→ 选中文字已回落 "
			         "selTextFallback(0x%06X) + 加粗（避免文字色 ≈ 底色）",
			         lumaGap, (unsigned)(mStyle.selTextFallback & 0xFFFFFF));
		}
		mLastWarn = buf;
	}

	/* 标题 */
	if (mTitle != 0) {
		char buf[24];
		snprintf(buf, sizeof(buf), "%d-%02d", mYear, mMonth);
		mTitle->setText(buf);
		mTitle->setTextColor((int)(mStyle.titleText & 0xFFFFFF));
	}

	/* 42 格：文字 + 文字色（+ 选中加粗）。本代平台 textview 画不出底色（见文件头平台事实） */
	for (int i = 0; i < CELLS; ++i) {
		ZKTextView *c = mCells[i];
		if (c == 0) {
			continue;
		}
		const int d = mDayMap[i];
		if (d == 0) {
			c->setText("");
		} else {
			char buf[8];
			snprintf(buf, sizeof(buf), "%d", d);
			c->setText(buf);
		}

		const bool sel = (d != 0 && d == mDay);
		const bool mk = (d != 0 && isMarked(d));
		const bool td = (d != 0 && isToday(d));

		uint32_t fg = td ? mStyle.mutedText : mStyle.cellText;
		if (sel) {
			fg = selFg;          /* 兜底命中时 = selTextFallback（见上面自检） */
		} else if (mk) {
			fg = mStyle.markText;
		}
		c->setTextColor((int)(fg & 0xFFFFFF));

		const bool bold = (sel && (mStyle.selBold || useFallback));   /* 兜底时一律加粗，拉开层次 */
		if (bold != mLastBold[i]) {
			c->setBold(bold);
			mLastBold[i] = bold;
		}
	}

	/* 选中高亮色块（painter 自绘；不接 painter 时这里是空操作） */
	paintHighlight();

	if (hlZero) {
		return Result(-2, mLastWarn);
	}
	if (useFallback) {
		return Result(1, mLastWarn);
	}
	return Result(0, "ok");
}

void Calendar::setStyle(const Style &st) {
	mStyle = st;
}

} // namespace ui_v1
} // namespace zk
