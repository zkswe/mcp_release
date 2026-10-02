/*
 * zk_radbutton.cpp — components/ui_v1/RadButton 实现
 *
 * 提炼来源（只读参考，未改动原案例）：
 *   projects/translate/lvgl-widgets-uiv1/  —— LVGL `lv_button` 主题倒角在迁移后丢失
 *     （案例 TRANSLATE.md 差异清单记为降级 B：`button__N` 只有纯色直角 / 圆角切图）
 *   tools/ui_tools/gen_res.py `rounded_rect_ss` —— 「切图路线」的抗锯齿口径（≥4x 超采样 + LANCZOS）
 *解释器版本：本文件是它的**运行期等价物**（覆盖率 → 与底色混色），代价是任意尺寸/任意半径
 *
 * 核心思路（为什么这样能抗锯齿）：
 *平台 painter 只有不透明 fill（无 alpha），但**圆角弧带上的像素覆盖率是已知的几何量**：
 *   · 直边与像素网格对齐 → 一整块 fillRect 就是精确的；
 *   · 只有 4 个圆角方块里的 ~r 个像素带（每角）落在弧线上 → 对它们做「超采样求覆盖率」，
 *再拿覆盖率把前景色与**已知底色**（Style::bg）混出中间色，最后画 1x1 像素。
 *于是边缘得到 ~65 档中间色（aaSamples=8），设备上不再是阶梯。
 *代价：AA 只对「底色为纯色」的场景精确；底是图片/渐变时中间色会偏（见 README 限制）。
 */
#include "zk/zk_radbutton.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include <control/ZKPainter.h>

namespace zk {
namespace ui_v1 {

/* ============================ 小工具 ============================ */

static int iMin2(int a, int b) { return a < b ? a : b; }
static int iMax2(int a, int b) { return a > b ? a : b; }
static int clampI(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }

/* 前景 fg 与底色 bg 按 t（0..1 = 前景权重）混色。painter 无 alpha → 这是唯一的「半透明」实现 */
static uint32_t mixF(uint32_t fg, uint32_t bg, double t) {
	if (t <= 0.0) return bg & 0xFFFFFF;
	if (t >= 1.0) return fg & 0xFFFFFF;
	const double it = 1.0 - t;
	int r = (int)(((fg >> 16) & 0xFF) * t + ((bg >> 16) & 0xFF) * it + 0.5);
	int g = (int)(((fg >> 8) & 0xFF) * t + ((bg >> 8) & 0xFF) * it + 0.5);
	int b = (int)((fg & 0xFF) * t + (bg & 0xFF) * it + 0.5);
	return (uint32_t)((clampI(r, 0, 255) << 16) | (clampI(g, 0, 255) << 8) | clampI(b, 0, 255));
}

/*
 * 像素 [px,px+1) x [py,py+1) 落在「圆心 (cx,cy)、半径 r 的圆」内的面积占比（= 覆盖率）。
 * 只对 quadrant (qx,qy) 那一侧采样（qx<0 → 只算 x<=cx 的一侧），角方块正好整块在一个象限里。
 * 超采样 ss x ss（ss=8 → 覆盖率量化到 1/64，即最多 65 档中间色）。
 */
static double quarterCoverage(int px, int py, double cx, double cy, double r,
                              int qx, int qy, int ss) {
	if (r <= 0.0) return 0.0;
	const double inv = 1.0 / (double)ss;
	const double area = 1.0 / (double)(ss * ss);
	const double r2 = r * r;
	int hit = 0;
	for (int i = 0; i < ss; ++i) {
		const double x = px + (i + 0.5) * inv;
		if (qx < 0) { if (x > cx) continue; } else { if (x < cx) continue; }
		for (int j = 0; j < ss; ++j) {
			const double y = py + (j + 0.5) * inv;
			if (qy < 0) { if (y > cy) continue; } else { if (y < cy) continue; }
			const double dx = x - cx, dy = y - cy;
			if (dx * dx + dy * dy <= r2) ++hit;
		}
	}
	return hit * area;
}

/*
 * 画一个角方块（r x r）：逐像素算覆盖率 → 与底色混出中间色 → 按行合并同色像素成 span 再 fillRect。
 * 覆盖不足 0.2% 的像素不画（留给底下原有的内容）。
 */
static void paintCornerBox(ZKPainter *p, int l, int t, int r,
                           double cx, double cy, int qx, int qy,
                           uint32_t fill, uint32_t border, int bw,
                           uint32_t bg, int ss) {
	const int inner = r - bw;                       // 内侧半径（边框环带 = 外覆盖 - 内覆盖）
	const bool hasBorder = (border != 0 && bw > 0 && inner > 0);
	for (int y = 0; y < r; ++y) {
		const int py = t + y;
		uint32_t runColor = 0;
		int runX = 0, runLen = 0;
		for (int x = 0; x <= r; ++x) {              // x == r 是收尾哨兵
			uint32_t col = 0;
			bool draw = false;
			if (x < r) {
				const int px = l + x;
				const double covOut = quarterCoverage(px, py, cx, cy, (double)r, qx, qy, ss);
				if (covOut > 0.002) {
					draw = true;
					if (!hasBorder) {
						/* 无边框：一层覆盖率直接混（混的对象是底色，不是 0）*/
						col = (covOut >= 0.998) ? fill : mixF(fill, bg, covOut);
					} else {
						double covIn = 0.0;
						if (inner > 0) {
							covIn = quarterCoverage(px, py, cx, cy, (double)inner, qx, qy, ss);
						}
						const uint32_t base = (covIn >= 0.998) ? fill : mixF(fill, bg, covIn);
						const double covBorder = covOut - covIn;
						col = (covBorder <= 0.002) ? base : mixF(border, base, covBorder);
					}
				}
			}
			if (draw && runLen > 0 && col == runColor && (l + x) == runX + runLen) {
				++runLen;
				continue;
			}
			if (runLen > 0) {
				p->setSourceColor(runColor);
				p->fillRect(runX, py, runLen, 1);
				runLen = 0;
			}
			if (draw) {
				runColor = col;
				runX = l + x;
				runLen = 1;
			}
		}
	}
}

/* ---------------- 图层叠加：把内嵌图形（圆钮）盖到「已经画好的形状」上 ----------------
 *
 * 为什么不能拿 drawRoundedRect() 画钮：它会**先用 bg 把整个 w×h 方盒铺实**（为了绕开设备端
 * erase() 留下的不透明黑角）。钮在药丸端头时，这个方盒的**两个外角落在药丸端头半圆之外**，
 * 于是卡片底色上露出 1~1.6px 的方角（Z21 真机实测：理想药丸轮廓外多 18px 药丸色）。
 *
 * 这里改成逐像素合成，混色基准**逐像素**取：
 *     base  = mix(track, cardBg, P)     // P = 药丸覆盖率：药丸与卡片混出来的「那一层」
 *     final = mix(knob , base  , K)     // K = 圆钮覆盖率
 * 并且 **P == 0 的像素一个都不画**（保留已经铺好的卡片底色）
 *   → 钮的外形被药丸轮廓裁掉，方角在几何上不存在。
 */

/* 点 (x,y) 是否落在圆角矩形 [l,l+w)x[t,t+h)、圆角半径 r 内 */
static bool insideRRect(double x, double y, double l, double t, double w, double h, double r) {
	if (r <= 0.0) {
		return x >= l && x < l + w && y >= t && y < t + h;
	}
	double dx = 0.0, dy = 0.0;
	if (x < l + r)             dx = (l + r) - x;
	else if (x > l + w - r)    dx = x - (l + w - r);
	if (y < t + r)             dy = (t + r) - y;
	else if (y > t + h - r)    dy = y - (t + h - r);
	if (dx <= 0.0 && dy <= 0.0) return true;      /* 直边围出的十字区（含四角圆心以内） */
	return dx * dx + dy * dy <= r * r;
}

/* 像素 [px,px+1)x[py,py+1) 落在上面那个圆角矩形内的面积占比（ss x ss 超采样，口径同 §AA） */
static double rrectCoverage(int px, int py, double l, double t, double w, double h,
                            double r, int ss) {
	const double inv = 1.0 / (double)ss;
	int hit = 0;
	for (int i = 0; i < ss; ++i) {
		const double x = (double)px + (i + 0.5) * inv;
		for (int j = 0; j < ss; ++j) {
			const double y = (double)py + (j + 0.5) * inv;
			if (insideRRect(x, y, l, t, w, h, r)) ++hit;
		}
	}
	return (double)hit / (double)(ss * ss);
}

/* 圆角矩形的有符号距离（<0 内 / >0 外）：只用于「整像素全内 / 全外」的快速判据，省掉超采样
 * 标准 2D rounded-box SDF：`length(max(q,0)) + min(max(qx,qy),0) - r`，q = |p-center| - (halfSize - r)。
 * ⚠️ 最后一项是 **min**（<0 才取），写成 max 会把距离算大 → 边缘像素被误判成「全外」而漏画（踩过）。*/
static double rrectDist(double x, double y, double l, double t, double w, double h, double r) {
	const double cx = l + w * 0.5, cy = t + h * 0.5;
	const double qx = (x > cx ? x - cx : cx - x) - (w * 0.5 - r);
	const double qy = (y > cy ? y - cy : cy - y) - (h * 0.5 - r);
	const double mx = (qx > 0.0) ? qx : 0.0;
	const double my = (qy > 0.0) ? qy : 0.0;
	const double mq = (qx > qy) ? qx : qy;
	return sqrt(mx * mx + my * my) + ((mq < 0.0) ? mq : 0.0) - r;
}

/* 像素中心离轮廓 ≥ 半像素对角线（√2/2）时，整个像素必然全内 / 全外 */
#define ZK_RB_PIXEL_HALF 0.70710678118654752

static void paintKnobLayer(ZKPainter *p, int kx, int ky, int dia,
                           int pl, int pt, int pw, int ph, int pr,
                           uint32_t knob, uint32_t track, uint32_t cardBg, int ss) {
	if (dia <= 0) return;
	const double kr = dia / 2.0;
	const double kl = kx, kt = ky;
	for (int y = 0; y < dia; ++y) {
		const int py = ky + y;
		uint32_t runColor = 0;
		int runX = 0, runLen = 0;
		for (int x = 0; x <= dia; ++x) {                    /* x == dia 是收尾哨兵 */
			uint32_t col = 0;
			bool draw = false;
			if (x < dia) {
				const int px = kx + x;
				const double cx = px + 0.5, cy = py + 0.5;
				const double dp = rrectDist(cx, cy, pl, pt, pw, ph, pr);
				if (dp < ZK_RB_PIXEL_HALF) {                /* ← 药丸之外：一个像素都不碰 */
					const double dk = rrectDist(cx, cy, kl, kt, dia, dia, kr);
					if (dk < ZK_RB_PIXEL_HALF) {
						const double P = (dp <= -ZK_RB_PIXEL_HALF) ? 1.0
						                 : rrectCoverage(px, py, pl, pt, pw, ph, pr, ss);
						if (P > 0.0) {
							const double K = (dk <= -ZK_RB_PIXEL_HALF) ? 1.0
							                 : rrectCoverage(px, py, kl, kt, dia, dia, kr, ss);
							if (K > 0.002) {
								const uint32_t base = (P >= 0.998) ? (track & 0xFFFFFF)
								                     : mixF(track, cardBg, P);
								col = (K >= 0.998) ? (knob & 0xFFFFFF) : mixF(knob, base, K);
								draw = true;
							}
						}
					}
				}
			}
			if (draw && runLen > 0 && col == runColor && (kx + x) == runX + runLen) {
				++runLen;
				continue;
			}
			if (runLen > 0) {
				p->setSourceColor(runColor);
				p->fillRect(runX, py, runLen, 1);
				runLen = 0;
			}
			if (draw) {
				runColor = col;
				runX = kx + x;
				runLen = 1;
			}
		}
	}
}

/* ============================ 构造 / 析构 ============================ */

RadButton::RadButton()
	: mPainter(0), mState(NORMAL), mPrevState(NORMAL), mPressHeld(false),
	  mShape(SHAPE_RECT), mHasRect(false), mSwitchable(false), mAutoRefresh(true),
	  mCb(0), mCbUser(0) {
	mRect[0] = mRect[1] = mRect[2] = mRect[3] = 0;
}

RadButton::~RadButton() {}

/* ============================ 绑定 ============================ */

RadButton::Result RadButton::attach(ZKPainter *painter) {
	if (painter == 0) {
		return Result(-1, "RadButton::attach: painter 为空 —— 先确认 ui json 里有 painter__N 且 caption 与 mXXXPtr 一致");
	}
	const LayoutPosition &pos = painter->getPosition();
	if (pos.mWidth <= 0 || pos.mHeight <= 0) {
		mPainter = painter;
		return Result(-2, "RadButton::attach: painter 尺寸为 0 —— json 里 position 的 width/height 没写");
	}
	mPainter = painter;
	return Result(0, "ok");
}

void RadButton::detach() {
	mPainter = 0;
	mState = NORMAL;
	mPrevState = NORMAL;
	mPressHeld = false;
}

/* ============================ 样式 ============================ */

RadButton::Result RadButton::setStyle(const Style &st) {
	if (st.borderWidth < 1) {
		return Result(-1, "RadButton::setStyle: borderWidth 必须 >= 1（不要边框请把 border 设 0）");
	}
	if (st.aaSamples < 2 || st.aaSamples > 16) {
		return Result(-2, "RadButton::setStyle: aaSamples 取值范围 2..16（8 = 65 档覆盖率）");
	}
	mStyle = st;
	mStyle.bg &= 0xFFFFFF;
	mStyle.normal &= 0xFFFFFF;
	mStyle.pressed &= 0xFFFFFF;
	mStyle.selected &= 0xFFFFFF;
	mStyle.disabled &= 0xFFFFFF;
	mStyle.border &= 0xFFFFFF;
	return Result(0, "ok");
}

RadButton::Result RadButton::setRadius(int r) {
	if (r < -1) {
		return Result(-1, "RadButton::setRadius: 半径不能为负（-1/0 = 自动药丸）");
	}
	mStyle.radius = r;
	return Result(0, "ok");
}

RadButton::Result RadButton::setColors(uint32_t normal, uint32_t pressed, uint32_t selected,
                                       uint32_t disabled, uint32_t border) {
	mStyle.normal   = normal   & 0xFFFFFF;
	mStyle.pressed  = pressed  & 0xFFFFFF;
	mStyle.selected = selected & 0xFFFFFF;
	mStyle.disabled = disabled & 0xFFFFFF;
	if (border != 0) {
		mStyle.border = border & 0xFFFFFF;
	}
	return Result(0, "ok");
}

RadButton::Result RadButton::setMode(Mode m) {
	if (m != MODE_AA && m != MODE_HARD) {
		return Result(-1, "RadButton::setMode: 只支持 MODE_AA / MODE_HARD");
	}
	mStyle.mode = m;
	return Result(0, "ok");
}

/* ============================ 状态 ============================ */

RadButton::Result RadButton::setState(State s) {
	if (s != NORMAL && s != PRESSED && s != SELECTED && s != DISABLED) {
		return Result(-1, "RadButton::setState: 未知状态（NORMAL/PRESSED/SELECTED/DISABLED）");
	}
	if (mState == s) {
		return Result(0, "ok（状态未变，幂等）");   // 幂等：同状态不报错
	}
	mState = s;
	mPrevState = s;      // 显式设状态 = 新基准，按下后回到这里
	mPressHeld = false;
	return Result(0, "ok");
}

const char *RadButton::stateName() const {
	switch (mState) {
	case PRESSED:  return "PRESSED";
	case SELECTED: return "SELECTED";
	case DISABLED: return "DISABLED";
	default:       return "NORMAL";
	}
}

uint32_t RadButton::currentColor() const {
	switch (mState) {
	case PRESSED:  return mStyle.pressed;
	case SELECTED: return mStyle.selected;
	case DISABLED: return mStyle.disabled;
	default:       return mStyle.normal;
	}
}

RadButton::Result RadButton::press(bool down) {
	if (down) {
		if (mPressHeld) {
			return Result(0, "ok（已按下，幂等）");       // 幂等：重复按下不覆盖基准
		}
		mPrevState = mState;
		mPressHeld = true;
		mState = PRESSED;
		return Result(0, "ok");
	}
	if (!mPressHeld) {
		return Result(0, "ok（未按下，幂等）");
	}
	mPressHeld = false;
	mState = mPrevState;                              // 回到按下前那个状态
	return Result(0, "ok");
}

RadButton::Result RadButton::setSelected(bool on) {
	return setState(on ? SELECTED : NORMAL);
}

/* ============================ 触摸（包自己算命中） ============================ */

RadButton::Result RadButton::setRect(int left, int top, int width, int height) {
	int w = width, h = height;
	if (w <= 0 || h <= 0) {					// 尺寸没给 → 退回 painter 自身尺寸（尺寸来自 json，业务一般也照它给）
		w = this->width();
		h = this->height();
	}
	if (w <= 0 || h <= 0) {
		return Result(-1, "RadButton::setRect: 宽高都没给，也取不到 painter 尺寸 —— 先 attach(painter) 或显式给 width/height");
	}
	mRect[0] = left;
	mRect[1] = top;
	mRect[2] = w;
	mRect[3] = h;
	mHasRect = true;
	return Result(0, "ok");
}

void RadButton::getRect(int &left, int &top, int &width, int &height) const {
	left = mRect[0];
	top = mRect[1];
	width = mRect[2];
	height = mRect[3];
}

bool RadButton::hitTest(int x, int y) const {
	if (!mHasRect) return false;
	return x >= mRect[0] && x < mRect[0] + mRect[2] &&
	       y >= mRect[1] && y < mRect[1] + mRect[3];
}

void RadButton::setAutoRefresh(bool on) { mAutoRefresh = on; }

/*
 * 触摸状态机（一张表就能看完）：
 *   DOWN界内 → 按下态（记住按下前状态）              | 界外 → 不消费
 *   MOVE已在按下态且移出界 → 取消按下态；否则自家手势继续消费 | 没按下过 → 不消费（让别人滑动）
 *   UP按下态 → 先回落，再（界内 + 开关模式）翻转 | 没按下过 → 界内 + 开关模式也兜底翻转一次
 *   CANCEL 按下态 → 回落
 */
bool RadButton::onTouch(int x, int y, int action) {
	if (!mHasRect) {
		return false;							// 没给几何 → 不消费（README 排错表第 1 条）
	}
	const bool inside = hitTest(x, y);
	bool consumed = false;

	switch (action) {
	case TOUCH_DOWN:
		if (!inside) return false;
		press(true);							// 幂等：重复 DOWN 不覆盖「按下前状态」
		consumed = true;
		break;

	case TOUCH_MOVE:
		if (!mPressHeld) return false;		// 不是我们起的头 → 不消费（滑动/翻页照常）
		if (!inside) press(false);			// 移出边界 → 取消按下态（回落幂等）
		consumed = true;
		break;

	case TOUCH_UP:
		if (mPressHeld) {
			press(false);					// 先回落（回到按下前那个状态）
			if (inside && mSwitchable && mState != DISABLED) toggle();
			consumed = true;
		} else if (inside && mSwitchable && mState != DISABLED) {
			toggle();						// 兜底：只收到 UP（触摸注入/快速一扫）也算一次点击
			consumed = true;
		} else {
			return false;
		}
		break;

	case TOUCH_CANCEL:
		if (!mPressHeld) return false;
		press(false);
		consumed = true;
		break;

	default:
		return false;
	}

	if (consumed && mAutoRefresh) refresh();	// 状态变了顺手重绘（painter 不自动重绘）
	return consumed;
}

/* ============================ 开关语义 ============================ */

RadButton::Result RadButton::setSwitchable(bool on) {
	mSwitchable = on;
	return Result(0, "ok");
}

RadButton::Result RadButton::setOn(bool on) {
	return setState(on ? SELECTED : NORMAL);	// setState 幂等：同值不报错、不重绘
}

RadButton::Result RadButton::toggle() {
	if (mState == DISABLED) {
		return Result(0, "ok（DISABLED：不翻转）");
	}
	const Result r = setOn(!isOn());
	if (mCb) {								// 编程 setOn() 不触发回调，只有 toggle() 触发
		mCb(isOn(), mCbUser);
	}
	return r;
}

RadButton::Result RadButton::setOnToggle(ToggleCallback cb, void *user) {
	mCb = cb;
	mCbUser = user;
	return Result(0, "ok");
}

/* ============================ 形态 ============================ */

RadButton::Result RadButton::setShape(Shape s) {
	if (s != SHAPE_RECT && s != SHAPE_PILL) {
		return Result(-1, "RadButton::setShape: 只支持 SHAPE_RECT / SHAPE_PILL");
	}
	mShape = s;
	if (s == SHAPE_PILL) {
		mSwitchable = true;					// 药丸 = 开关形态（经需求方口径：倒角按钮当带倒角的开关用）
	}
	return Result(0, "ok");
}

RadButton::Result RadButton::setPillStyle(const PillStyle &ps) {
	if (ps.padding < 0) {
		return Result(-1, "RadButton::setPillStyle: padding 不能为负");
	}
	if (ps.knobDia < 0) {
		return Result(-2, "RadButton::setPillStyle: knobDia 不能为负（0 = 自动 = 高 - 2*padding）");
	}
	mPill = ps;
	mPill.knobOff &= 0xFFFFFF;
	mPill.knobOn &= 0xFFFFFF;
	return Result(0, "ok");
}

/* ============================ 几何 ============================ */

int RadButton::width() const {
	return mPainter ? mPainter->getPosition().mWidth : 0;
}

int RadButton::height() const {
	return mPainter ? mPainter->getPosition().mHeight : 0;
}

int RadButton::autoRadius(int w, int h) {
	const int m = iMin2(w, h);
	return iMax2(1, m / 3);
}

int RadButton::radiusPx() const {
	const int w = width(), h = height();
	if (w <= 0 || h <= 0) return 0;
	if (mShape == SHAPE_PILL) {
		return iMax2(1, h / 2);				// 药丸：半径 = 高/2（两端半圆，不看 Style::radius）
	}
	const int m = iMin2(w, h);
	int r = (mStyle.radius <= 0) ? autoRadius(w, h) : mStyle.radius;
	const int cap = iMax2(0, m / 2);
	return clampI(r, 0, cap);
}

/* ============================ 画 ============================ */

uint32_t RadButton::mix(uint32_t fg, uint32_t bg, int percentFg) {
	return mixF(fg, bg, clampI(percentFg, 0, 100) / 100.0);
}

RadButton::Result RadButton::drawRoundedRect(ZKPainter *painter, int left, int top,
                                             int width, int height, int radius,
                                             uint32_t fill, uint32_t border, int borderWidth,
                                             uint32_t bg, Mode mode, int aaSamples) {
	if (painter == 0) {
		return Result(-1, "RadButton::drawRoundedRect: painter 为空");
	}
	if (width <= 0 || height <= 0) {
		return Result(-2, "RadButton::drawRoundedRect: 宽高必须 > 0");
	}
	if (borderWidth < 1) {
		return Result(-3, "RadButton::drawRoundedRect: borderWidth 必须 >= 1");
	}
	fill &= 0xFFFFFF;
	border &= 0xFFFFFF;
	bg &= 0xFFFFFF;

	int r = (radius <= 0) ? autoRadius(width, height) : radius;
	r = clampI(r, 0, iMax2(0, iMin2(width, height) / 2));
	const int bw = (border == 0) ? 0 : iMin2(borderWidth, iMax2(1, r));

	/* ⓪ 先把整个控件盒铺成底色（两张原因）：
	 *   ① painter 的 `erase()` 在设备上是**不透明黑**（不是透明），AA 时跳过的圆角外像素
	 *就会留黑角（实测：Z21 上直接就是 4 个黑方块）；
	 *   ② 底色铺实后，圆角外的像素 = 与 AA 混色基准同一颜色 → 边缘没有色差。
	 *所以 `Style::bg` 必须 = 按钮所在位置的真实底色（见 README 限制 1）。*/
	painter->setSourceColor(bg);
	painter->fillRect(left, top, width, height, 0);

	if (mode == MODE_HARD) {
		/* 平台原生：圆角是硬边（边界只有前景/底色两档）—— 对照用 */
		painter->setSourceColor(fill);
		painter->fillRect(left, top, width, height, r);
		if (bw > 0) {
			painter->setSourceColor(border);
			painter->drawRect(left, top, width, height, r);
		}
		return Result(0, "ok（MODE_HARD：平台原生的硬边圆角）");
	}

	int ss = clampI(aaSamples, 2, 16);
	const int h2r = height - 2 * r;
	const int w2r = width - 2 * r;

	/* ① 三块直边区域整块填充（与像素网格对齐 → 本身就是精确的） */
	painter->setSourceColor(fill);
	if (w2r > 0) {
		painter->fillRect(left + r, top, w2r, height, 0);           // 中竖带（含上下直边）
	}
	if (h2r > 0) {
		painter->fillRect(left, top + r, r, h2r, 0);                // 左横带
		painter->fillRect(left + width - r, top + r, r, h2r, 0);    // 右横带
	}
	if (r == 0) {
		painter->fillRect(left, top, width, height, 0);
	}

	/* ② 四个圆角方块逐像素做 AA（只有弧带会落到这里，量级 ~4r 个像素） */
	if (r > 0) {
		const double cxL = left + r;
		const double cxR = left + width - r;
		const double cyT = top + r;
		const double cyB = top + height - r;
		paintCornerBox(painter, left, top, r, cxL, cyT, -1, -1, fill, border, bw, bg, ss);
		paintCornerBox(painter, left + width - r, top, r, cxR, cyT, 1, -1, fill, border, bw, bg, ss);
		paintCornerBox(painter, left, top + height - r, r, cxL, cyB, -1, 1, fill, border, bw, bg, ss);
		paintCornerBox(painter, left + width - r, top + height - r, r, cxR, cyB, 1, 1, fill, border, bw, bg, ss);
	}

	/* ③ 四条直边上的边框（轴对齐 → 整块画） */
	if (bw > 0 && r > 0) {
		painter->setSourceColor(border);
		if (w2r > 0) {
			painter->fillRect(left + r, top, w2r, bw, 0);
			painter->fillRect(left + r, top + height - bw, w2r, bw, 0);
		}
		if (h2r > 0) {
			painter->fillRect(left, top + r, bw, h2r, 0);
			painter->fillRect(left + width - bw, top + r, bw, h2r, 0);
		}
	}

	return Result(0, "ok");
}

RadButton::Result RadButton::refresh() {
	if (mPainter == 0) {
		return Result(-1, "RadButton::refresh: 还没 attach(painter)");
	}
	const LayoutPosition &pos = mPainter->getPosition();
	if (pos.mWidth <= 0 || pos.mHeight <= 0) {
		return Result(-2, "RadButton::refresh: painter 尺寸为 0（检查 json position）");
	}
	mPainter->erase(0, 0, pos.mWidth, pos.mHeight);      // painter 不自动擦除/重绘

	/* ---- 药丸形态（开关）：轨道 = 高/2 半径的药丸；圆钮 = 边长为直径的正圆 ---- */
	if (mShape == SHAPE_PILL) {
		const int w = pos.mWidth, h = pos.mHeight;
		uint32_t track = isOn() ? mStyle.selected : mStyle.normal;   // 开/关轨色
		if (mState == DISABLED) {
			track = mStyle.disabled;
		} else if (mState == PRESSED) {
			track = mixF(track, 0x000000, 0.88);                      // 按下：轨色压深 12%
		}
		Result rt = drawRoundedRect(mPainter, 0, 0, w, h, iMax2(1, h / 2), track,
		                            (mState == DISABLED) ? 0 : mStyle.border, mStyle.borderWidth,
		                            mStyle.bg, mStyle.mode, mStyle.aaSamples);
		if (!rt.ok()) return rt;

		int pad = iMax2(0, mPill.padding);
		int room = h - 2 * pad;                                   // 钮可用的最大直径
		if (room < 2) {                                           // 内边距太大 → 自动收
			pad = iMax2(0, (h - 2) / 2);
			room = h - 2 * pad;
		}
		int dia = (mPill.knobDia > 0) ? mPill.knobDia : room;
		dia = clampI(dia, 2, iMax2(2, room));
		const int cy = h / 2;
		const int cx = isOn() ? (w - pad - dia / 2) : (pad + dia / 2);   // ★ 钮位：开→右，关→左
		uint32_t knob = isOn() ? mPill.knobOn : mPill.knobOff;
		if (mState == DISABLED) knob = mixF(knob, mStyle.disabled, 0.6);
		/* 正圆 = 「边长 dia、圆角 dia/2」的圆角矩形（AA 口径与轨道一致，边缘比 fillArc 干净）
		 * MODE_HARD：保留原来的「方盒铺底 + 硬边圆角」路径（对照用；已知同样会露方角，不修） */
		if (mStyle.mode == MODE_HARD) {
			return drawRoundedRect(mPainter, cx - dia / 2, cy - dia / 2, dia, dia, dia / 2,
			                       knob, 0, 1, track, mStyle.mode, mStyle.aaSamples);
		}
		/* MODE_AA：图层叠加 —— 钮被药丸轮廓裁掉，方角不再存在（详见 paintKnobLayer 注释） */
		paintKnobLayer(mPainter, cx - dia / 2, cy - dia / 2, dia,
		               0, 0, w, h, iMax2(1, h / 2), knob, track, mStyle.bg, mStyle.aaSamples);
		return Result(0, "ok（PILL：轨道 + 圆钮图层叠加）");
	}

	return drawRoundedRect(mPainter, 0, 0, pos.mWidth, pos.mHeight, radiusPx(),
	                       currentColor(), (mState == DISABLED) ? 0 : mStyle.border,
	                       mStyle.borderWidth, mStyle.bg, mStyle.mode, mStyle.aaSamples);
}

RadButton::Result RadButton::erase() {
	if (mPainter == 0) {
		return Result(-1, "RadButton::erase: 还没 attach(painter)");
	}
	const LayoutPosition &pos = mPainter->getPosition();
	mPainter->erase(0, 0, pos.mWidth, pos.mHeight);
	return Result(0, "ok");
}

} // namespace ui_v1
} // namespace zk
