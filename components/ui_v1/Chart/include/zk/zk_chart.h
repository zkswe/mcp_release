/*
 * zk_chart.h — components/ui_v1/Chart（源控件：lv_chart / lv_scale / lv_arc · MPAndroidChart · QCustomPlot）
 *
 * 唯一对外头文件。实现见 src/zk_chart.cpp。
 *
 * 设计要点（为什么是"自绘集合"）：
 *   平台**没有**图表控件（`diagram` 只能画实时波形，没有坐标轴/柱/环/仪表）。
 *   所以本组件 = **ZKPainter 自绘 + ZKTextView 叠刻度文字**：
 *     · 几何全部从 `painter->getPosition()` 的宽高实时推算 → 同一份代码适配 1024x600 / 1280x800；
 *     · painter **不自动重绘**（平台不 inflate）→ 每次改数据后必须显式 `refresh()`；
 *     · painter 无文字 API → 刻度文字由业务在 json 里摆好 textview，运行时把**指针池**交给组件，
 *       由组件 setText/setPosition（池子大小不够时降级为「不画文字、只画图」并报 code!=0）。
 *   命名空间：zk::ui_v1::Chart
 *
 * 对应：control-map.md §3.2（chart → 自绘 + textview 刻度，L3）；
 *       gap-list.md G-09/G-10/G-11（无 chart / 无坐标轴 / 无多环）。
 *
 * ⚠️ 平台事实（Z21 easyui 2.6.0 实测）：
 *   · `drawArc(0度 = 正上方，顺时针为正)`；
 *   · 无 alpha 通道 → 半透明填充用「按比例混底色」近似（见 Style::mixWith）；
 *   · 一次 `erase()` + 数百次 fillRect/fillArc 在 Z21 上是流畅的（190x620 密集点阵实测）。
 */
#ifndef _ZK_UI_V1_CHART_H_
#define _ZK_UI_V1_CHART_H_

#include <stdint.h>
#include <string>

class ZKPainter;
class ZKTextView;

namespace zk {
namespace ui_v1 {

/**
 * @brief 图表（折线 / 柱状 / 环形 / 仪表）
 *
 * 用法（最短路径，完整示例见 example/）：
 * @code
 *   static zk::ui_v1::Chart s_line;
 *   static ZKTextView *s_lineLabels[7] = { mTvY100Ptr, ..., mTvY0Ptr, mTvX0Ptr };  // Y 刻度 6 + X 1
 *
 *   void onUI_init() {
 *       zk::ui_v1::Chart::Style st;                 // 默认样式即可
 *       s_line.setStyle(st);
 *       s_line.attach(mPtLinePtr);
 *       s_line.setType(zk::ui_v1::Chart::LINE);
 *       s_line.setAxisRange(0.f, 100.f, 5);         // 0..100，5 段 = 6 条刻度（配 6 个 Y 文字）
 *       s_line.attachLabels(s_lineLabels, 7);
 *       s_line.setSeries(0, data, 12);
 *       s_line.refresh();
 *   }
 *   void onBtnNext() { s_line.appendPoint(0, 66.f); s_line.refresh(); }   // 改数据必须 refresh
 * @endcode
 */
class Chart {
public:
	/** 图表类型 */
	enum Type {
		LINE = 0,   // 折线（+可选面积填充 / 数据点）
		BAR  = 1,   // 分组柱状（多系列并排）
		RING = 2,   // 同心环（每环一个 0..1 进度，带底环）
		GAUGE = 3   // 仪表盘（分区色弧 + 刻度 + 指针）
	};

	/** 统一结果类型（components/README.md 规范 2）：msg 说人话，禁止静默失败 */
	struct Result {
		int code;          // 0 = OK
		std::string msg;
		Result() : code(0) {}
		Result(int c, const std::string &m) : code(c), msg(m) {}
		bool ok() const { return code == 0; }
	};

	/** 容量上限（编译期常量，够用且不动态分配） */
	enum { MAX_SERIES = 4, MAX_POINTS = 64, MAX_RINGS = 3, MAX_ZONES = 4, MAX_SEGMENTS = 8 };

	/** 仪表分区 */
	struct Zone {
		float v1, v2;       // 值域（闭区间，v2 > v1）
		uint32_t color;
	};

	/**
	 * @brief 环的一段（分段环用）
	 * @note value 是**权重**（不是百分比）：组件按所有段 value 之和归一，
	 *       所以 3/1/1 与 60/20/20 画出来一样；所有段 value<=0 时**不画段**（只留底轨）。
	 *       color = 0 表示用默认系列色（series[段下标]）。
	 */
	struct Segment {
		float value;
		uint32_t color;
	};

	/** 样式 */
	struct Style {
		uint32_t bg;         // 画布底色（0 = 不铺底，保留 painter 的 erase 结果）
		uint32_t grid;       // 网格色
		uint32_t axis;       // 轴线/边框色
		uint32_t label;      // 刻度文字色
		uint32_t series[MAX_SERIES];
		int lineWidth;       // 折线/环宽基准（<=0 表示按画布尺寸自适应）
		int pointRadius;     // 数据点半径（<=0 自适应；0 表示不画点）
		bool areaFill;       // 折线面积填充
		bool gridVertical;   // 竖网格
		int padL, padT, padR, padB;   // 绘图区内边距（给刻度文字留位）
		int gaugeStartDeg;   // 仪表起始角（0 = 正上方，顺时针为正）
		int gaugeSpanDeg;    // 仪表扫过角度（225 = 常见 5/8 圆表）
		Style()
			: bg(0xFFFFFF), grid(0xE3E7EC), axis(0xC8CDD4), label(0x9E9E9E),
			  lineWidth(0), pointRadius(0), areaFill(false), gridVertical(true),
			  padL(34), padT(10), padR(10), padB(24),
			  gaugeStartDeg(225), gaugeSpanDeg(225) {
			series[0] = 0x2196F3;
			series[1] = 0x607D8B;
			series[2] = 0xF44336;
			series[3] = 0x4CAF50;
		}
	};

	Chart();
	~Chart();

	/** 绑定画布。必须在 onUI_init（控件已创建）之后调用。 */
	Result attach(ZKPainter *painter);
	void detach();

	Result setType(Type t);
	Type type() const { return mType; }

	/* ---------------- 数据 ---------------- */
	/** 整段替换某系列（LINE/BAR 用；RING 的进度请用 setRingPercent，GAUGE 的值用 setGaugeValue） */
	Result setSeries(int idx, const float *values, int count);
	/** 追加一个点（队列满则丢最旧的，保持 MAX_POINTS 长度）；返回追加后的点数；返回 <0 = 出错 */
	int appendPoint(int idx, float value);
	Result clearSeries(int idx);
	int pointCount(int idx) const;
	int seriesCount() const { return mSeriesCount; }

	/* ---------------- 轴 ---------------- */
	/** 值域与刻度段数（ticks=5 → 6 条刻度线 / 6 个 Y 文字） */
	Result setAxisRange(float min, float max, int ticks = 5);
	float axisMin() const { return mMin; }
	float axisMax() const { return mMax; }
	int axisTicks() const { return mTicks; }

	/* ---------------- 环 / 仪表 ---------------- */
	/** 第 ring 环的进度（0..1）
	 *  @note 该环若已设分段（setRingSegments），**分段优先**：进度弧不再画，只留底轨。 */
	Result setRingPercent(int ring, float percent);
	float ringPercent(int ring) const;

	/* ---------------- 分段环（一环切多段；来源：v1 案例的三段饼环 PtSess） ---------------- */
	/**
	 * @brief 把第 ring 环切成 n 段（value 按总和归一，段间留 2°，第 1 段从**正上方**起顺时针排）
	 * @param ring 环下标 0..MAX_RINGS-1（0 = 最内环）
	 * @param segs 段数组（value = 权重；color = 0 用默认系列色）
	 * @param n    段数 1..MAX_SEGMENTS；n<=0 = 等价 clearRingSegments(ring)
	 * @return code: 0 OK / 1 段数超上限已截断 / -1 环下标越界 / -2 当前类型不是 RING / -3 segs 为空
	 * @note **只在 `Chart::RING` 类型下生效**：其它类型调用返回非 0 + 人话 msg（不静默失败）。
	 *       调用顺序 `setType(RING)` → `setRingSegments(...)` → `refresh()`；
	 *       分段数据不占 MAX_SERIES，编译期定长，无动态分配。
	 */
	Result setRingSegments(int ring, const Segment *segs, int n);
	/** 清掉第 ring 环的分段（该环回到 setRingPercent 的进度弧画法） */
	Result clearRingSegments(int ring);
	/** 第 ring 环当前是否分段 */
	bool hasRingSegments(int ring) const;
	/** 仪表分区表（最多 MAX_ZONES；不设则用 series 色均匀分 3 段） */
	Result setGaugeZones(const Zone *zones, int count);
	/** 仪表指针值（应落在 [axisMin, axisMax]） */
	Result setGaugeValue(float v);
	float gaugeValue() const { return mGaugeValue; }

	/* ---------------- 刻度文字（叠加 textview） ---------------- */
	/**
	 * @brief 刻度文字池（painter 无文字 API）。
	 * 池语义：labels[0 .. ticks]        = Y 轴刻度（值从 max 到 min）
	 *         之后剩下的（可选）          = X 轴分类文字，逐点一个
	 *         RING 模式：labels[k]        = 第 k 环的百分比文字
	 *         传 NULL / n<=0 = 不画文字（图表本身照画）
	 * @note 文字控件坐标以 **painter 所在容器** 为基准（组件已把 painter 左上角偏移算进去），
	 *       所以刻度文字必须与 painter **同父**（否则错位）；RING 模式只写文字/颜色，位置由 json 定。
	 */
	Result attachLabels(ZKTextView **labels, int n);

	Result setStyle(const Style &s);
	const Style &style() const { return mStyle; }

	/** 重绘（painter 不自动重绘；改数据/改样式/切页回来都要调） */
	Result refresh();

	/** 自检：把 0..1 的亮度混色（painter 无 alpha，半透明一律走这里） */
	static uint32_t mix(uint32_t a, uint32_t b, int percentA);

private:
	Chart(const Chart &);
	Chart &operator=(const Chart &);

	/* 绘制 */
	void drawLine();
	void drawBar();
	void drawRing();
	void drawGauge();
	void drawGrid(int x0, int y0, int x1, int y1);
	void putLabel(int slot, const char *text, int x, int y, int w, int h);

	int slotCount() const;                    // 需要多少个 Y 文字槽
	void valueToY(float v, int y0, int h, int &out) const;

	ZKPainter *mPainter;
	Type mType;
	int mOx, mOy;                             // painter 在其父容器中的左上角（刻度文字要加这个偏移）

	float mData[MAX_SERIES][MAX_POINTS];
	int mCount[MAX_SERIES];
	int mSeriesCount;

	float mMin, mMax;
	int mTicks;

	float mRing[MAX_RINGS];
	int mRingCount;
	Segment mSegs[MAX_RINGS][MAX_SEGMENTS];   // 分段环数据（每环最多 MAX_SEGMENTS 段）
	int mSegCount[MAX_RINGS];                 // 0 = 该环不分段
	Zone mZones[MAX_ZONES];
	int mZoneCount;
	float mGaugeValue;

	ZKTextView **mLabels;
	int mLabelCount;

	Style mStyle;
};

} // namespace ui_v1
} // namespace zk

#endif /* _ZK_UI_V1_CHART_H_ */
