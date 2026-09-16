/*
 * zk_tabview.cpp — components/ui_v1/TabView 实现
 *
 * 提炼来源（只读参考，未改动原案例）：
 *   projects/translate/lvgl-widgets/z21/src/logic/mainLogic.cc  §「页签（源 lv_tabview -> ZKPageWindow 滑动切页）」
 *     ・页签高亮的唯一真源 = PwPages 的当前页（滑动 / 点按钮 两条路径都只认 getCurrentPage()）
 *     ・下划线几何 = 活动页签的矩形底部一条色块（高 = 页签高/13，最小 2）
 *     ・切页后自绘图要重画（painter 不自动重绘）→ 这里通过 onPageChanged 交给业务
 *   本文件把它收成组件：去掉了案例里的业务耦合（s_tabIndex / renderCharts），只留可复用的机制。
 */
#include "zk/zk_tabview.h"

#include <stdio.h>
#include <window/ZKPageWindow.h>
#include <control/ZKButton.h>
#include <control/ZKTextView.h>

namespace zk {
namespace ui_v1 {

/* ------------------------------------------------------------------ */
/* 页容器监听桥：把 ZKPageWindow 的页变更转成组件回调                     */
/* ------------------------------------------------------------------ */
class TabView::Listener : public ZKPageWindow::IPageChangeListener {
public:
	Listener() : owner(0) {}
	virtual ~Listener() {}
	virtual void onPageChange(ZKPageWindow *pPageWindow, int page) {
		(void)pPageWindow;
		if (owner != 0) {
			owner->syncTo(page);          // 以控件实际页为准
		}
	}
	TabView *owner;
};

/* ------------------------------------------------------------------ */
/* 构造 / 析构                                                          */
/* ------------------------------------------------------------------ */
TabView::TabView()
	: mListener(0), mPages(0), mTabs(0), mTabCount(0), mMarker(0),
	  mCb(0), mUser(0), mLastPage(-1) {
}

TabView::~TabView() {
	detach();
	delete mListener;
	mListener = 0;
}

/* ------------------------------------------------------------------ */
/* 工具                                                                 */
/* ------------------------------------------------------------------ */
static int iMaxTv(int a, int b) { return a > b ? a : b; }

/* ------------------------------------------------------------------ */
/* attach / detach                                                      */
/* ------------------------------------------------------------------ */
TabView::Result TabView::attach(ZKPageWindow *pages, ZKButton *const *tabs, int tabCount,
                                ZKTextView *marker) {
	if (pages == 0) {
		return Result(-1, "TabView::attach: pages(pagewindow) 为空 —— 先确认 ui json 里有 pagewindow__N 且 caption 与 mXXXPtr 一致");
	}
	mPages = pages;
	mTabs = const_cast<ZKButton **>(tabs);
	mTabCount = (tabs == 0) ? 0 : iMaxTv(0, tabCount);
	mMarker = marker;

	const int pc = pages->getPageSize();
	if (pc <= 0) {
		return Result(-2, "TabView::attach: pagewindow 的页数为 0 —— json 里必须有 >=1 个 window 直接嵌在 pagewindow 下（同尺寸=一页）");
	}
	if (mTabCount > 0 && mTabCount != pc) {
		/* 不拦（业务可能故意少做几个页签），但必须报出来，别静默错位 */
		mLastPage = -1;
		sync();
		return Result(-3, "TabView::attach: 页签按钮个数 != 页数（页签/页 不一致，高亮会错位）");
	}

	if (mListener == 0) {
		mListener = new Listener();
	}
	mListener->owner = this;
	pages->setPageChangeListener(mListener);

	mLastPage = -1;
	sync();
	return Result(0, "ok");
}

void TabView::detach() {
	if (mPages != 0) {
		mPages->setPageChangeListener(0);   // 先摘监听：避免控件回调打到已析构对象
	}
	if (mListener != 0) {
		mListener->owner = 0;
	}
	mPages = 0;
	mTabs = 0;
	mTabCount = 0;
	mMarker = 0;
	mLastPage = -1;
}

/* ------------------------------------------------------------------ */
/* 页切换                                                               */
/* ------------------------------------------------------------------ */
void TabView::setOnPageChanged(PageChangedFn fn, void *user) {
	mCb = fn;
	mUser = user;
}

TabView::Result TabView::select(int page) {
	if (mPages == 0) {
		return Result(-1, "TabView::select: 未 attach");
	}
	if (page < 0 || page >= mPages->getPageSize()) {
		return Result(-2, "TabView::select: 页号越界（0..pageCount-1）");
	}
	const int cur = mPages->getCurrentPage();
	if (page > cur) {
		for (int i = cur; i < page; ++i) {
			mPages->turnToNextPage();
		}
	} else if (page < cur) {
		for (int i = page; i < cur; ++i) {
			mPages->turnToPrevPage();
		}
	}
	/* 兜底：无论控件是否发回调，都按实际页同步一次（幂等） */
	sync();
	return Result(0, "ok");
}

int TabView::current() const {
	return (mPages == 0) ? -1 : mPages->getCurrentPage();
}

int TabView::pageCount() const {
	return (mPages == 0) ? 0 : mPages->getPageSize();
}

void TabView::setStyle(const Style &st) {
	mStyle = st;
	sync();                 // 立即生效（重画下划线 / 重着色页签）
}

/* ------------------------------------------------------------------ */
/* sync：页签视觉的唯一实现（滑块式，处处幂等）                            */
/* ------------------------------------------------------------------ */
void TabView::sync() {
	if (mPages == 0) {
		return;
	}
	syncTo(mPages->getCurrentPage());
}

void TabView::syncTo(int page) {
	if (mPages == 0) {
		return;                              // 已 detach（可能回调晚到）
	}
	const int pc = mPages->getPageSize();
	if (page < 0) page = 0;
	if (page >= pc) page = pc - 1;

	/* 页签文字色 + 下划线跟随 */
	for (int i = 0; i < mTabCount; ++i) {
		if (mTabs[i] == 0) continue;
		mTabs[i]->setTextColor(i == page ? (int)mStyle.activeColor : (int)mStyle.idleColor);
	}
	if (mMarker != 0 && mTabCount > 0 && page < mTabCount && mTabs[page] != 0) {
		const LayoutPosition &p = mTabs[page]->getPosition();
		int mh = (mStyle.markHeight > 0) ? mStyle.markHeight : iMaxTv(2, p.mHeight / 13);
		int ins = (mStyle.markInset > 0) ? mStyle.markInset : 0;
		mMarker->setPosition(LayoutPosition(p.mLeft + ins, p.mTop + p.mHeight - mh,
		                                    p.mWidth - 2 * ins, mh));
		if (mStyle.markColor != 0) {
			mMarker->setBackgroundColor((int)mStyle.markColor);
		} else {
			mMarker->setBackgroundColor((int)mStyle.activeColor);
		}
	}

	/* 只在「页真的变了」时回调（避免同一页重复刷业务 / 重复重绘自绘图） */
	if (page != mLastPage) {
		mLastPage = page;
		if (mCb != 0) {
			mCb(page, mUser);
		}
	}
}

/* ------------------------------------------------------------------ */
/* 手感参数                                                             */
/* ------------------------------------------------------------------ */
const TabView::Gesture &TabView::defaultGesture() {
	static Gesture g;             // 默认值：dragMaxDis=200 / edgeEffect=1 / rollSpeed=60 / orientation=0
	return g;
}

std::string TabView::gestureHtmlAttrs() {
	const Gesture &g = defaultGesture();
	char buf[192];
	snprintf(buf, sizeof(buf),
	         "data-drag-max=\"%d\" data-edge-effect=\"%d\" data-roll-speed=\"%d\" data-orientation=\"%d\"",
	         g.dragMaxDis, g.edgeEffect, g.rollSpeed, g.orientation);
	return std::string(buf);
}

TabView::Result TabView::checkGesture(const Gesture &actual) {
	const Gesture &d = defaultGesture();
	std::string bad;
	if (actual.dragMaxDis != d.dragMaxDis) {
		bad += "dragMaxDis(" + std::to_string((long long)actual.dragMaxDis) +
		       "!=" + std::to_string((long long)d.dragMaxDis) + ") ";
	}
	if (actual.edgeEffect != d.edgeEffect) {
		bad += "edgeEffect(" + std::to_string((long long)actual.edgeEffect) +
		       "!=" + std::to_string((long long)d.edgeEffect) + ") ";
	}
	if (actual.rollSpeed != d.rollSpeed) {
		bad += "rollSpeed(" + std::to_string((long long)actual.rollSpeed) +
		       "!=" + std::to_string((long long)d.rollSpeed) + ") ";
	}
	if (actual.orientation != d.orientation) {
		bad += "orientation(" + std::to_string((long long)actual.orientation) +
		       "!=" + std::to_string((long long)d.orientation) + ") ";
	}
	if (!bad.empty()) {
		return Result(-1, "手感参数与默认值不一致（确认是有意为之，否则改回默认）：" + bad);
	}
	return Result(0, "ok");
}

} // namespace ui_v1
} // namespace zk
