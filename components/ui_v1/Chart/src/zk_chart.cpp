/*
 * zk_chart.cpp — components/ui_v1/Chart 实现
 *
 * 提炼来源（只读参考，未改动原案例）：
 *   projects/translate/lvgl-widgets/z21/src/logic/mainLogic.cc
 *     ・renderLine()  折线：横网格 + 竖分隔 + 面积填充（混色近似 alpha）+ 折线 + 数据点
 *     ・renderBar()   分组柱：两组并排，柱宽/组宽按画布宽现算
 *     ・renderTarget() 三同心环：底环 + 进度弧（同 lv_arc 口径）
 *     ・renderGauge()  仪表盘：三段分区弧 + 20 格刻度（major every 4）+ 指针
 *     ・通用：几何全部从 getPosition() 现取（分辨率无关）；erase+重画；painter 不自动重绘
 *   projects/EasyDevice-Z21/src/logic/mainLogic.cc
 *     ・色标/渐变混色思路（lerpStops / gradientColor）、坐标轴反算、点阵安全 clamp
 */
#include "zk/zk_chart.h"

#include <stdio.h>
#include <math.h>
#include <string.h>

#include <control/ZKPainter.h>
#include <control/ZKTextView.h>

namespace zk {
namespace ui_v1 {

/* ============================ 小工具 ============================ */
#define ZK_PI 3.14159265358979

static int iMax2(int a, int b) { return a > b ? a : b; }
static int iMin2(int a, int b) { return a < b ? a : b; }
static int clampI(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }

/* ============================ 构造 / 析构 ============================ */
Chart::Chart()
	: mPainter(0), mType(LINE), mOx(0), mOy(0), mSeriesCount(0),
	  mMin(0.f), mMax(100.f), mTicks(5),
	  mRingCount(MAX_RINGS), mZoneCount(0), mGaugeValue(0.f),
	  mLabels(0), mLabelCount(0) {
	for (int i = 0; i < MAX_SERIES; ++i) {
		mCount[i] = 0;
		memset(mData[i], 0, sizeof(mData[i]));
	}
	mRing[0] = 0.f; mRing[1] = 0.f; mRing[2] = 0.f;
	for (int k = 0; k < MAX_RINGS; ++k) {
		mSegCount[k] = 0;                  // 默认不分段
	}
	mGaugeValue = mMin;
}

Chart::~Chart() {}

/* ============================ 绑定 ============================ */
Chart::Result Chart::attach(ZKPainter *painter) {
	if (painter == 0) {
		return Result(-1, "Chart::attach: painter 为空 —— 先确认 ui json 里有 painter__N 且 caption 与 mXXXPtr 一致");
	}
	mPainter = painter;
	mOx = painter->getPosition().mLeft;
	mOy = painter->getPosition().mTop;
	return Result(0, "ok");
}

void Chart::detach() {
	mPainter = 0;
	mLabels = 0;
	mLabelCount = 0;
}

Chart::Result Chart::setType(Type t) {
	if (t != LINE && t != BAR && t != RING && t != GAUGE) {
		return Result(-1, "Chart::setType: 未知类型（LINE/BAR/RING/GAUGE）");
	}
	mType = t;
	return Result(0, "ok");
}

/* ============================ 数据 ============================ */
Chart::Result Chart::setSeries(int idx, const float *values, int count) {
	if (idx < 0 || idx >= MAX_SERIES) {
		return Result(-1, "Chart::setSeries: 系列下标越界（0..3）");
	}
	if (values == 0 || count < 0) {
		return Result(-2, "Chart::setSeries: 数据指针为空或点数 <0");
	}
	int n = iMin2(count, MAX_POINTS);
	for (int i = 0; i < n; ++i) {
		mData[idx][i] = values[i];
	}
	mCount[idx] = n;
	if (idx + 1 > mSeriesCount) {
		mSeriesCount = idx + 1;
	}
	if (n < count) {
		return Result(1, "Chart::setSeries: 点数超出上限，已截断到 64 点（要更多请分批 / 用刷新式波形）");
	}
	return Result(0, "ok");
}

int Chart::appendPoint(int idx, float value) {
	if (idx < 0 || idx >= MAX_SERIES) {
		return -1;
	}
	if (mCount[idx] < MAX_POINTS) {
		mData[idx][mCount[idx]++] = value;
	} else {
		memmove(&mData[idx][0], &mData[idx][1], sizeof(float) * (MAX_POINTS - 1));
		mData[idx][MAX_POINTS - 1] = value;
	}
	if (idx + 1 > mSeriesCount) {
		mSeriesCount = idx + 1;
	}
	return mCount[idx];
}

Chart::Result Chart::clearSeries(int idx) {
	if (idx < 0 || idx >= MAX_SERIES) {
		return Result(-1, "Chart::clearSeries: 系列下标越界（0..3）");
	}
	mCount[idx] = 0;
	return Result(0, "ok");
}

int Chart::pointCount(int idx) const {
	if (idx < 0 || idx >= MAX_SERIES) {
		return 0;
	}
	return mCount[idx];
}

Chart::Result Chart::setAxisRange(float min, float max, int ticks) {
	if (!(max > min)) {
		return Result(-1, "Chart::setAxisRange: 需要 max > min（否则纵轴反算会除零）");
	}
	if (ticks < 1 || ticks > 12) {
		return Result(-2, "Chart::setAxisRange: 刻度段数应在 1..12（建议 5）");
	}
	mMin = min;
	mMax = max;
	mTicks = ticks;
	return Result(0, "ok");
}

/* ============================ 环 / 仪表 ============================ */
Chart::Result Chart::setRingPercent(int ring, float percent) {
	if (ring < 0 || ring >= MAX_RINGS) {
		return Result(-1, "Chart::setRingPercent: 环下标越界（0..2）");
	}
	if (percent < 0.f) percent = 0.f;
	if (percent > 1.f) percent = 1.f;
	mRing[ring] = percent;
	if (ring + 1 > mRingCount) {
		mRingCount = ring + 1;
	}
	return Result(0, "ok");
}

float Chart::ringPercent(int ring) const {
	if (ring < 0 || ring >= MAX_RINGS) {
		return 0.f;
	}
	return mRing[ring];
}

/*
 * 分段环：一个环切成 n 段（来源：v1 案例 Analytics 页的三段饼环 PtSess）。
 *   ・value 是权重，按总和归一 -> 3/1/1 与 60/20/20 等价；
 *   ・全 0（或全负）时按约定**不画段**，只留底轨（返回 code=1 提醒，不是静默）；
 *   ・只在 RING 类型下有意义 -> 其它类型直接返回非 0 + 人话 msg（契约要求）。
 */
Chart::Result Chart::setRingSegments(int ring, const Segment *segs, int n) {
	if (mType != RING) {
		char buf[160];
		snprintf(buf, sizeof(buf),
		         "Chart::setRingSegments: 仅 RING 类型生效（当前 mType=%d）—— 先 setType(Chart::RING)",
		         (int)mType);
		return Result(-2, buf);
	}
	if (ring < 0 || ring >= MAX_RINGS) {
		return Result(-1, "Chart::setRingSegments: 环下标越界（0..2，0 = 最内环）");
	}
	if (n <= 0) {
		mSegCount[ring] = 0;                       // n<=0 = 清空（等价 clearRingSegments）
		return Result(0, "ok（n<=0 -> 已清空该环分段）");
	}
	if (segs == 0) {
		return Result(-3, "Chart::setRingSegments: segs 为空指针（要清空请传 n=0 或调 clearRingSegments）");
	}
	const int m = iMin2(n, MAX_SEGMENTS);
	int nonPositive = 0;
	for (int i = 0; i < m; ++i) {
		mSegs[ring][i] = segs[i];
		if (!(segs[i].value > 0.f)) {
			++nonPositive;
		}
	}
	mSegCount[ring] = m;
	if (m < n) {
		return Result(1, "Chart::setRingSegments: 段数超出上限，已截断到 8 段（多余段丢弃）");
	}
	if (nonPositive == m) {
		return Result(1, "Chart::setRingSegments: 所有段 value 都 <=0，按约定不画段（只留底轨）");
	}
	return Result(0, "ok");
}

Chart::Result Chart::clearRingSegments(int ring) {
	if (ring < 0 || ring >= MAX_RINGS) {
		return Result(-1, "Chart::clearRingSegments: 环下标越界（0..2）");
	}
	mSegCount[ring] = 0;
	return Result(0, "ok");
}

bool Chart::hasRingSegments(int ring) const {
	if (ring < 0 || ring >= MAX_RINGS) {
		return false;
	}
	return mSegCount[ring] > 0;
}

Chart::Result Chart::setGaugeZones(const Zone *zones, int count) {
	if (zones == 0 || count <= 0) {
		mZoneCount = 0;      // 清空 → 用 series 色均分
		return Result(0, "ok");
	}
	int n = iMin2(count, MAX_ZONES);
	mZoneCount = n;
	for (int i = 0; i < n; ++i) {
		if (!(zones[i].v2 > zones[i].v1)) {
			mZoneCount = 0;
			char buf[80];
			snprintf(buf, sizeof(buf), "Chart::setGaugeZones: 第 %d 段需要 v2 > v1（当前 v1=%.1f v2=%.1f）",
			         i + 1, (double)zones[i].v1, (double)zones[i].v2);
			return Result(-1, buf);
		}
		mZones[i] = zones[i];
	}
	return Result(0, "ok");
}

Chart::Result Chart::setGaugeValue(float v) {
	mGaugeValue = v;
	return Result(0, "ok");
}

/* ============================ 刻度文字 ============================ */
Chart::Result Chart::attachLabels(ZKTextView **labels, int n) {
	mLabels = labels;
	mLabelCount = (labels == 0) ? 0 : iMax2(0, n);
	return Result(0, "ok");
}

int Chart::slotCount() const {
	return mTicks + 1;          // Y 轴刻度个数
}

void Chart::putLabel(int slot, const char *text, int x, int y, int w, int h) {
	if (mLabels == 0 || slot < 0 || slot >= mLabelCount || mLabels[slot] == 0) {
		return;
	}
	mLabels[slot]->setText(text);
	mLabels[slot]->setTextColor((int)mStyle.label);
	/* 文字与 painter 同父：加 painter 左上角偏移，否则会挤到容器左上角去 */
	mLabels[slot]->setPosition(LayoutPosition(mOx + x, mOy + y, w, h));
}

/* ============================ 样式 ============================ */
Chart::Result Chart::setStyle(const Style &s) {
	mStyle = s;
	return Result(0, "ok");
}

uint32_t Chart::mix(uint32_t a, uint32_t b, int percentA) {
	int pa = clampI(percentA, 0, 100);
	int r = (int)(((a >> 16) & 0xFF) * pa + ((b >> 16) & 0xFF) * (100 - pa)) / 100;
	int g = (int)(((a >> 8) & 0xFF) * pa + ((b >> 8) & 0xFF) * (100 - pa)) / 100;
	int bl = (int)((a & 0xFF) * pa + (b & 0xFF) * (100 - pa)) / 100;
	return ((uint32_t)r << 16) | ((uint32_t)g << 8) | (uint32_t)bl;
}

/* ============================ 纵轴反算 ============================ */
void Chart::valueToY(float v, int y0, int h, int &out) const {
	float span = mMax - mMin;
	if (span <= 0.f) span = 1.f;
	float t = (v - mMin) / span;
	if (t < 0.f) t = 0.f;
	if (t > 1.f) t = 1.f;
	out = y0 + h - 1 - (int)(t * (float)(h - 1) + 0.5f);
}

/* ============================ 网格 ============================ */
void Chart::drawGrid(int x0, int y0, int x1, int y1) {
	const int W = x1 - x0 + 1;
	const int H = y1 - y0 + 1;
	if (W <= 2 || H <= 2) {
		return;
	}
	mPainter->setLineWidth(1);

	/* 横网格 = 刻度线（含上下边），并在左侧槽位写刻度值 */
	mPainter->setSourceColor(mStyle.grid);
	for (int i = 0; i <= mTicks; ++i) {
		int y = y1 - i * (H - 1) / mTicks;
		mPainter->fillRect(x0, y, W, 1, 0);
	}
	if (mType == LINE || mType == BAR) {
		int pc = mCount[0];
		for (int s = 0; s < mSeriesCount; ++s) {
			if (mCount[s] > pc) pc = mCount[s];
		}
		if (mStyle.gridVertical && pc > 1) {
			for (int i = 1; i < pc; ++i) {
				mPainter->fillRect(x0 + i * W / pc, y0, 1, H, 0);
			}
		}
	}

	/* 轴线（左 + 下） */
	mPainter->setSourceColor(mStyle.axis);
	mPainter->fillRect(x0, y0, 1, H, 0);
	mPainter->fillRect(x0, y1, W, 1, 0);

	/* Y 轴刻度文字：槽位 0..mTicks，值从 max 到 min；
	 * ★ 槽位 0 = max → 必须画在**最上面那条线**（y0），否则刻度值会上下颠倒（图形对、字反）。
	 *   历史 bug（0.2.0 及以前）：这里误用 `y1 - i*(H-1)/mTicks`（i=0 落在**底部线**）却写 max。 */
	{
		char buf[24];
		int slotW = iMax2(24, mStyle.padL - 4);
		for (int i = 0; i <= mTicks; ++i) {
			float v = mMax - (mMax - mMin) * (float)i / (float)mTicks;
			if (fabsf(v) < 0.05f) {
				v = 0.f;                       // 防 -0.0 / 1e-7
			}
			snprintf(buf, sizeof(buf), "%.0f", (double)v);
			int y = y0 + i * (H - 1) / mTicks;   // i=0 → 最上面那条线（= max）
			putLabel(i, buf, iMax2(0, x0 - slotW - 2), y - 8, slotW, 16);
		}
	}
}

/* ============================ 折线 ============================ */
void Chart::drawLine() {
	const LayoutPosition &pos = mPainter->getPosition();
	const int W = pos.mWidth, H = pos.mHeight;
	mPainter->setSourceColor(mStyle.bg);
	mPainter->fillRect(0, 0, W, H, 0);

	const int x0 = clampI(mStyle.padL, 0, W - 6);
	const int y0 = clampI(mStyle.padT, 0, H - 6);
	const int x1 = W - 1 - clampI(mStyle.padR, 0, W - 2);
	const int y1 = H - 1 - clampI(mStyle.padB, 0, H - 2);
	if (x1 - x0 < 8 || y1 - y0 < 8) {
		return;                                        // 画布太小：只铺底，别画坏
	}
	drawGrid(x0, y0, x1, y1);

	const int gw = x1 - x0 + 1;
	const int gh = y1 - y0 + 1;

	/* X 轴分类文字（槽位 slotCount() 之后逐点一个） */
	{
		int slot = slotCount();
		for (int s = 0; s < mSeriesCount; ++s) {
			for (int i = 0; i < mCount[s]; ++i) {
				if (slot + i >= mLabelCount) {
					break;
				}
				int cx = x0 + (int)((i + 0.5) * (double)gw / (double)mCount[s]);
				char buf[16];
				snprintf(buf, sizeof(buf), "%d", i + 1);
				putLabel(slot + i, buf, iMax2(0, cx - 20), y1 + 2, 40, 14);
			}
			break;                                     // 只按系列 0 的密度摆
		}
	}

	for (int s = 0; s < mSeriesCount; ++s) {
		const int n = mCount[s];
		if (n <= 0) {
			continue;
		}
		int lw = (mStyle.lineWidth > 0) ? mStyle.lineWidth : iMax2(2, gh / 60);
		int pr = (mStyle.pointRadius > 0) ? mStyle.pointRadius
		                                  : iMax2(2, gh / 45);

		float px[MAX_POINTS];
		float py[MAX_POINTS];
		for (int i = 0; i < n; ++i) {
			int yy = 0;
			valueToY(mData[s][i], y0, gh, yy);
			px[i] = (float)(x0 + (int)((i + 0.5) * (double)gw / (double)n));
			py[i] = (float)yy;
		}

		/* 面积填充（painter 无 alpha → 主色 22% 混底色） */
		if (mStyle.areaFill && n > 1) {
			mPainter->setSourceColor(mix(mStyle.series[s % MAX_SERIES], mStyle.bg, 22));
			for (int i = 0; i < n - 1; ++i) {
				mPainter->fillTriangle((int)px[i], (int)py[i], (int)px[i + 1], (int)py[i + 1],
				                       (int)px[i], y1);
				mPainter->fillTriangle((int)px[i + 1], (int)py[i + 1], (int)px[i + 1], y1,
				                       (int)px[i], y1);
			}
		}

		/* 折线本体（series 0 用 SVG 风格的折线，其余同） */
		SZKPoint pts[MAX_POINTS];
		for (int i = 0; i < n; ++i) {
			pts[i].x = px[i];
			pts[i].y = py[i];
		}
		mPainter->setLineWidth(lw);
		mPainter->setSourceColor(mStyle.series[s % MAX_SERIES]);
		if (n == 1) {
			mPainter->fillArc((int)px[0], (int)py[0], pr, pr, 0, 360);
		} else {
			mPainter->drawLines(pts, n);
		}
		/* 数据点 */
		if (pr > 0) {
			for (int i = 0; i < n; ++i) {
				mPainter->fillArc((int)px[i], (int)py[i], pr, pr, 0, 360);
			}
		}
	}
}

/* ============================ 分组柱状 ============================ */
void Chart::drawBar() {
	const LayoutPosition &pos = mPainter->getPosition();
	const int W = pos.mWidth, H = pos.mHeight;
	mPainter->setSourceColor(mStyle.bg);
	mPainter->fillRect(0, 0, W, H, 0);

	const int x0 = clampI(mStyle.padL, 0, W - 6);
	const int y0 = clampI(mStyle.padT, 0, H - 6);
	const int x1 = W - 1 - clampI(mStyle.padR, 0, W - 2);
	const int y1 = H - 1 - clampI(mStyle.padB, 0, H - 2);
	if (x1 - x0 < 8 || y1 - y0 < 8) {
		return;
	}
	drawGrid(x0, y0, x1, y1);

	int n = 0;
	for (int s = 0; s < mSeriesCount; ++s) {
		if (mCount[s] > n) n = mCount[s];
	}
	if (n <= 0) {
		return;
	}
	const int gw = (x1 - x0 + 1) / n;
	const int sc = iMax2(1, mSeriesCount);
	const int bw = iMax2(2, (gw - (sc + 1)) / sc);

	for (int s = 0; s < sc; ++s) {
		mPainter->setSourceColor(mStyle.series[s % MAX_SERIES]);
		for (int i = 0; i < mCount[s]; ++i) {
			int top = 0;
			valueToY(mData[s][i], y0, y1 - y0 + 1, top);
			int bh = y1 - top + 1;
			if (top < y0) {
				top = y0;                       // 超上限：贴顶裁切
				bh = 1;
			}
			if (bh < 0) bh = 0;
			int bx = x0 + i * gw + (gw - (sc * bw + (sc - 1))) / 2 + s * (bw + 1);
			mPainter->fillRect(bx, top, bw, bh, 1);
		}
	}
}

/* ============================ 同心环 ============================ */
void Chart::drawRing() {
	const LayoutPosition &pos = mPainter->getPosition();
	const int W = pos.mWidth, H = pos.mHeight;
	mPainter->setSourceColor(mStyle.bg);
	mPainter->fillRect(0, 0, W, H, 0);

	const int cx = W / 2, cy = H / 2;
	const int R = iMin2(W, H) / 2 - 2;
	if (R < 10) {
		return;
	}
	const int lw = (mStyle.lineWidth > 0) ? mStyle.lineWidth : iMax2(5, R / 5);
	const uint32_t track = mStyle.grid;
	/* 段默认色（Segment::color == 0 时用）：按段下标循环 series 四色 */
	const uint32_t segDefault[MAX_SEGMENTS] = {
		mStyle.series[0], mStyle.series[1], mStyle.series[2], mStyle.series[3],
		mStyle.series[0], mStyle.series[1], mStyle.series[2], mStyle.series[3]
	};

	for (int k = 0; k < mRingCount; ++k) {
		int rad = R - lw / 2 - k * lw;
		if (rad <= lw) {
			break;
		}
		mPainter->setLineWidth(lw);
		mPainter->setSourceColor(track);
		mPainter->drawArc(cx, cy, rad, rad, 0, 360);

		int labelPct = (int)(mRing[k] * 100.f + 0.5f);
		uint32_t labelColor = mStyle.series[k % MAX_SERIES];

		if (mSegCount[k] > 0) {
			/* ---- 分段环：权重归一 + 段间 2° 间隙 + 第 1 段从正上方顺时针 ---- */
			float sum = 0.f;
			for (int i = 0; i < mSegCount[k]; ++i) {
				if (mSegs[k][i].value > 0.f) {
					sum += mSegs[k][i].value;
				}
			}
			if (sum > 0.f) {
				const int GAP = 2;                                  /* 段间隙（度，固定 2） */
				int total = 360 - mSegCount[k] * GAP;               /* 可分配的总角度 */
				if (total > 360) {
					total = 360;
				}
				if (total < 8) {
					total = 8;                                      /* 兜底：段数极端时不至于退化 */
				}
				int acc = 0;
				float best = -1.f;
				int bestPct = 0;
				uint32_t bestColor = labelColor;
				for (int i = 0; i < mSegCount[k]; ++i) {
					float v = (mSegs[k][i].value > 0.f) ? mSegs[k][i].value : 0.f;
					int sw = (int)((float)total * v / sum + 0.5f);
					if (i == mSegCount[k] - 1) {
						sw = total - acc;                           /* 最后一段补齐，避免累积误差留缝 */
					}
					if (sw > total - acc) {
						sw = total - acc;
					}
					if (sw <= 0) {
						break;
					}
					uint32_t c = (mSegs[k][i].color != 0) ? mSegs[k][i].color
					                                      : segDefault[i % MAX_SEGMENTS];
					if (v > best) {
						best = v;
						bestPct = (int)(v * 100.f / sum + 0.5f);
						bestColor = c;
					}
					mPainter->setSourceColor(c);
					mPainter->drawArc(cx, cy, rad, rad, acc, sw);
					acc += sw + GAP;
				}
				labelPct = bestPct;              /* 分段环的 labels[k] = 最大段占比 */
				labelColor = bestColor;
			}
		} else {
			/* ---- 进度环（原有的 setRingPercent 画法） ---- */
			int sweep = (int)(mRing[k] * 360.f + 0.5f);
			if (sweep > 0) {
				mPainter->setSourceColor(mStyle.series[k % MAX_SERIES]);
				mPainter->drawArc(cx, cy, rad, rad, 0, sweep);
			}
		}

		/* 环百分比文字：labels[k]（进度环 = 该环进度；分段环 = 最大段占比） */
		if (mLabels != 0 && k < mLabelCount && mLabels[k] != 0) {
			char buf[16];
			snprintf(buf, sizeof(buf), "%d%%", labelPct);
			mLabels[k]->setText(buf);
			mLabels[k]->setTextColor((int)labelColor);
		}
	}
}

/* ============================ 仪表盘 ============================ */
void Chart::drawGauge() {
	const LayoutPosition &pos = mPainter->getPosition();
	const int W = pos.mWidth, H = pos.mHeight;
	mPainter->setSourceColor(mStyle.bg);
	mPainter->fillRect(0, 0, W, H, 0);

	const int cx = W / 2, cy = H / 2;
	const int R = iMin2(W, H) / 2 - iMax2(4, iMin2(W, H) / 16);
	if (R < 20) {
		return;
	}
	const int lw = (mStyle.lineWidth > 0) ? mStyle.lineWidth : iMax2(5, R / 7);
	const int A0 = mStyle.gaugeStartDeg;
	const int SPAN = mStyle.gaugeSpanDeg;
	const int rad = R - lw / 2;
	const float span = mMax - mMin;
	if (span <= 0.f) {
		return;
	}

	/* 分区弧 */
	mPainter->setLineWidth(lw);
	if (mZoneCount > 0) {
		for (int i = 0; i < mZoneCount; ++i) {
			int s = A0 + (int)(SPAN * (mZones[i].v1 - mMin) / span);
			int sw = (int)(SPAN * (mZones[i].v2 - mZones[i].v1) / span);
			mPainter->setSourceColor(mZones[i].color);
			mPainter->drawArc(cx, cy, rad, rad, s, sw);
		}
	} else {
		const int slices = iMax2(1, iMin2(mSeriesCount, 3));
		for (int i = 0; i < slices; ++i) {
			int s = A0 + SPAN * i / slices;
			int sw = SPAN / slices;
			mPainter->setSourceColor(mStyle.series[i % MAX_SERIES]);
			mPainter->drawArc(cx, cy, rad, rad, s, sw);
		}
	}

	/* 刻度：20 格，每 4 格一个长刻度（同 lv_scale total_tick_count=21 / major_every=4） */
	const int TICKS = 20;
	for (int i = 0; i <= TICKS; ++i) {
		int deg = A0 + SPAN * i / TICKS;
		double sa = sin((double)deg * ZK_PI / 180.0);
		double ca = cos((double)deg * ZK_PI / 180.0);
		bool major = (i % 4 == 0);
		int r1 = R - lw - (major ? iMax2(6, R / 8) : iMax2(3, R / 16));
		int r2 = R - lw - 1;
		SZKPoint tp[2];
		tp[0].x = (float)(cx + sa * r1);
		tp[0].y = (float)(cy - ca * r1);
		tp[1].x = (float)(cx + sa * r2);
		tp[1].y = (float)(cy - ca * r2);
		mPainter->setLineWidth(major ? 2 : 1);
		mPainter->setSourceColor(mStyle.axis);
		mPainter->drawLines(tp, 2);
	}

	/* 指针 */
	{
		float t = (mGaugeValue - mMin) / span;
		if (t < 0.f) t = 0.f;
		if (t > 1.f) t = 1.f;
		int nDeg = A0 + (int)(SPAN * t);
		double nsa = sin((double)nDeg * ZK_PI / 180.0);
		double nca = cos((double)nDeg * ZK_PI / 180.0);
		SZKPoint np[2];
		np[0].x = (float)cx;
		np[0].y = (float)cy;
		np[1].x = (float)(cx + nsa * R * 0.62);
		np[1].y = (float)(cy - nca * R * 0.62);
		mPainter->setLineWidth(iMax2(3, R / 16));
		mPainter->setSourceColor(mStyle.series[1 % MAX_SERIES]);
		mPainter->drawLines(np, 2);
		mPainter->setSourceColor(mStyle.series[0]);
		int hub = iMax2(3, R / 9);
		mPainter->fillArc(cx, cy, hub, hub, 0, 360);
	}

	/* 文字：labels[0]=下限 / labels[1]=上限 / labels[2]=当前值 */
	{
		char buf[24];
		snprintf(buf, sizeof(buf), "%.0f", (double)mMin);
		putLabel(0, buf, 2, H - 18, mStyle.padL, 16);
		snprintf(buf, sizeof(buf), "%.0f", (double)mMax);
		putLabel(1, buf, W - mStyle.padR - 40, H - 18, 40, 16);
		snprintf(buf, sizeof(buf), "%.0f", (double)mGaugeValue);
		putLabel(2, buf, cx - 40, cy + H / 5, 80, 20);
	}
}

/* ============================ refresh ============================ */
Chart::Result Chart::refresh() {
	if (mPainter == 0) {
		return Result(-1, "Chart::refresh: 未 attach（先 attach(painter)）");
	}
	const LayoutPosition &pos = mPainter->getPosition();
	if (pos.mWidth <= 4 || pos.mHeight <= 4) {
		return Result(-2, "Chart::refresh: painter 尺寸为 0 —— json 里 position 没给宽高，或控件还没创建完");
	}
	mOx = pos.mLeft;                       // 记录 painter 在父容器中的位置（刻度文字用）
	mOy = pos.mTop;
	mPainter->erase(0, 0, pos.mWidth, pos.mHeight);     // painter 不自动擦除/重绘
	switch (mType) {
	case LINE:  drawLine();  break;
	case BAR:   drawBar();   break;
	case RING:  drawRing();  break;
	case GAUGE: drawGauge(); break;
	default:    return Result(-3, "Chart::refresh: 未知类型");
	}
	return Result(0, "ok");
}

} // namespace ui_v1
} // namespace zk
