/*
 * zk_tabview.h — components/ui_v1/TabView（源控件：lv_tabview / TabLayout+ViewPager / swiper+tab）
 *
 * 唯一对外头文件。实现见 src/zk_tabview.cpp。
 *
 * 设计要点（为什么不是一个新控件）：
 *   平台**已经有**滑动切页容器 ZKPageWindow（`pagewindow__N`），它自带「水平拖动 = 翻页」的手势、
 *   页间位移动画与 IPageChangeListener 回调。所以本组件**不重造轮子**，只做三件事：
 *     ① 把「页签按钮高亮 + 下划线标记」与 pagewindow 的当前页**双向**绑起来（滑动 / 点页签同源）；
 *     ② 把「手感参数（dragMaxDis / edgeEffect / rollSpeed / orientation）」固化成默认值 + 自检入口；
 *     ③ 给出一处 onPageChanged(page) 回调。
 *   命名空间：zk::ui_v1::TabView
 *
 * 对应：control-map.md §1.2/§1.3（tab 容器 = pagewindow + 页签按钮组，L1+L2）；
 *       gap-list.md G-01（历史写法用整屏 window 显隐 —— 丢手势，本组件是修正版）。
 */
#ifndef _ZK_UI_V1_TABVIEW_H_
#define _ZK_UI_V1_TABVIEW_H_

#include <stdint.h>
#include <string>

class ZKPageWindow;
class ZKButton;
class ZKTextView;

namespace zk {
namespace ui_v1 {

/**
 * @brief 页签页容器（基于平台 ZKPageWindow 的封装）
 *
 * 用法（最短路径，完整示例见 example/）：
 * @code
 *   static zk::ui_v1::TabView s_tab;
 *   static ZKButton *s_tabs[2] = { mBtnTab0Ptr, mBtnTab1Ptr };
 *
 *   void onUI_init() {
 *       s_tab.attach(mPwPagesPtr, s_tabs, 2, mTvTabMarkPtr);   // 页容器 + 页签按钮 + 下划线
 *       s_tab.setOnPageChanged(onPageChanged);                 // 滑动/点页签 都走这里
 *       s_tab.select(0);                                       // 首帧高亮归位（幂等）
 *   }
 *   static void onPageChanged(int page, void *user) { ... }
 * @endcode
 */
class TabView {
public:
	/** 统一结果类型（components/README.md 规范 2）：msg 说人话，禁止静默失败 */
	struct Result {
		int code;          // 0 = OK
		std::string msg;   // 人话（可直接打日志）
		Result() : code(0) {}
		Result(int c, const std::string &m) : code(c), msg(m) {}
		bool ok() const { return code == 0; }
	};

	/** 页切换回调（滑动与点页签**同源**，都只报实际生效页） */
	typedef void (*PageChangedFn)(int page, void *user);

	/**
	 * @brief 手感参数 —— 等价于 ui/*.json 里 `pagewindow__N` 的 4 个字段。
	 * @note  **平台没有运行时 setter**（ZKPageWindow 只在创建时从 json 读），
	 *        所以这四个值只能在原型 HTML 的 `data-*` / json 里给；本结构用于「给默认值 + 自查」。
	 */
	struct Gesture {
		int dragMaxDis;    // 触发翻页的拖动距离阈值（px）：小=灵敏但易误触，大=稳但费劲
		int edgeEffect;    // 边界效果（0 拖拽回弹 / 1 边缘发光 / 2 无）
		int rollSpeed;     // 翻页动画速度（越大越快）
		int orientation;   // 0 = 水平，1 = 垂直
		Gesture() : dragMaxDis(200), edgeEffect(1), rollSpeed(60), orientation(0) {}
	};

	/** 页签视觉样式 */
	struct Style {
		uint32_t activeColor;   // 选中页签文字色（默认主题蓝 0x2196F3）
		uint32_t idleColor;     // 未选中页签文字色（默认 0x616161）
		uint32_t markColor;     // 下划线色（默认 = activeColor）
		int markHeight;         // 下划线高（px）；<=0 表示按页签高的 1/13 自动算（最小 2）
		int markInset;          // 下划线左右内缩（px），0 = 与页签同宽
		Style() : activeColor(0x2196F3), idleColor(0x616161), markColor(0),
		          markHeight(0), markInset(0) {}
	};

	TabView();
	~TabView();

	/**
	 * @brief 绑定控件。必须在 onUI_init（控件已创建）之后、首帧显示之前调用。
	 * @param pages    页容器（`pagewindow__N`），不可为 NULL
	 * @param tabs     页签按钮数组（`button__N`），顺序 = 页序；可为 NULL（只要回调、不要页签条）
	 * @param tabCount 页签按钮个数（应为 pages->getPageSize()）
	 * @param marker   下划线标记（`textview__N`，背景色块），可为 NULL
	 * @return code!=0 时 msg 说明是哪一项没绑上（不静默）
	 */
	Result attach(ZKPageWindow *pages, ZKButton *const *tabs, int tabCount, ZKTextView *marker = 0);

	/** 解绑（onUI_quit 里调；同时摘掉监听，避免回调打到已销毁对象） */
	void detach();

	/**
	 * @brief 编程切页（点了页签按钮时调）。
	 * @note  内部只用 getCurrentPage() 一个口径 + 显式 sync()，幂等；即使控件不发回调也不会错位。
	 */
	Result select(int page);

	/** 当前页（未绑定时返回 -1） */
	int current() const;

	/** 页数（未绑定时返回 0） */
	int pageCount() const;

	/** 强制同步一次页签视觉（回调缺失时的兜底；幂等） */
	void sync();

	/** 页切换回调（滑动 / 点页签 / select 都触发） */
	void setOnPageChanged(PageChangedFn fn, void *user = 0);

	/** 视觉样式（可多次调；marker 位置在下一次 sync 时刷新） */
	void setStyle(const Style &st);

	/** 组件默认手感参数（写 json 时照抄） */
	static const Gesture &defaultGesture();

	/**
	 * @brief 生成默认手感的 HTML 片段（自检/复制用）。
	 * @return 形如 `data-drag-max="200" data-edge-effect="1" data-roll-speed="60" data-orientation="0"`
	 */
	static std::string gestureHtmlAttrs();

	/** 反向自检：把实际 json 的 4 个值传进来，对不上默认值时返回非 0 并在 msg 里列差异 */
	static Result checkGesture(const Gesture &actual);

private:
	/** 按「外部给的页号」同步（监听桥回调入口，只认控件实际页） */
	void syncTo(int page);

	TabView(const TabView &);
	TabView &operator=(const TabView &);

	class Listener;      // ZKPageWindow::IPageChangeListener 的桥（定义在 .cpp，对外不可见）
	Listener *mListener;
	ZKPageWindow *mPages;
	ZKButton **mTabs;
	int mTabCount;
	ZKTextView *mMarker;
	PageChangedFn mCb;
	void *mUser;
	Style mStyle;
	int mLastPage;

	friend class Listener;
};

} // namespace ui_v1
} // namespace zk

#endif /* _ZK_UI_V1_TABVIEW_H_ */
