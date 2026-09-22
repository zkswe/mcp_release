/*
 * VinylSpin.hpp - 播放页「黑胶唱片自转」（CloudMusic-F133 / iOSStyle-F133）
 *
 * 干什么：把封面做成一张**正圆唱片**（与静态口径同一套 SS=8 面积平均圆边），播放时匀速自转
 *         （暂停即停转、切歌回 0 度、页面退出释放）。
 *
 * 怎么做到（为什么选这条路，见 REPORT_STEP2 的方案对比表）：
 *   · 平台上**没有**任意角度旋转的现成控件：ZKPainter 只有画线/画框/画弧（没有画位图），
 *     misc::bitmap_rotate / RotateImageView 只有 90 度整数倍，ZKImageAnim 只吃 GIF/WebP 文件；
 *   · 所以自己算：逐帧把封面旋转到一张 BGRA 内存位图，再交给控件（setBackgroundBmp）。
 *   · 角度 = **墙钟时间**算出来的（不是按帧累加）-> 丢帧也匀速，不漂移、不抖动。
 *
 * 两套后端（同一份状态机与时间口径，只是"怎么把这一帧画出来"不同；见 REPORT_NANOVG）：
 *   · 后端 0（定点映射）：Q16 反向映射 + 2x2 盒平均采样 + 圆覆盖率表（RoundImageView::makeCircleMask，
 *     SS=8 面积平均），纯整数、无大查表核（表只有 1024 项 sin，4KB，L1 装得下）。
 *   · 后端 1（nanovg）：nanovg 的 **AGG 软件光栅器**后端（`nvgCreateAGG` 直接渲染到我方位图缓冲，
 *     不落盘、不进 GL），角度用 nvgRotate、圆形用 nvgCircle 裁剪 + nvgImagePattern 贴图，
 *     抗锯齿走 **nanovg/AGG 自带口径**（edgeAntiAlias，不是覆盖率表）。
 *   · `VS_BACKEND_DEFAULT` 选默认；**运行期自动回退**到后端 0（nanovg 上下文/纹理建不出来时不报错、
 *     只打一条 warning），`backend()` 可查实际生效值。
 *
 * 线程模型（UI 线程不做重活）：
 *   tick()  —— UI 定时器调：只在「上一帧算完」时才投递下一帧；出厂角度由时间算；
 *   旋转计算 —— zk::TaskRunner 后台线程（一张 320x320 约几 ms）；
 *   上屏     —— 回到 tick()（UI 线程）做：交换/拷贝本帧像素 + invalidate 触发重绘。
 *
 * 位图所有权（与 easyui 的释放契约对齐，证据见 src/core/BlurBg.cpp 顶部说明）：
 *   `host->setBackgroundBmp(bmp)` 交出去后归框架；换图/控件销毁时框架 free(data) +
 *   operator delete(bmp, 56)。所以每帧换图必须给**新的** bitmap_t（同一张交第二次 = 双释放）。
 *   模式 0（默认）：一张位图交一次，之后**原地改像素 + invalidate**（零分配）；
 *   模式 1：每帧一张新位图换图（框架自动释放旧的）。两种都在，切 VS_SWAP_BITMAP 即可。
 */
#ifndef _ZK_VINYL_SPIN_H_
#define _ZK_VINYL_SPIN_H_

#include <stdint.h>

/* 本类不依赖 App：需要 easyui（ZKBase / bitmap_t / misc::image_utility）
 * 与可选的 nanovg（AGG 后端，见 README 的依赖表）。 */

class ZKBase;

namespace zk {

/** 黑胶旋转（单例：播放页只有一个唱片） */
class VinylSpin {
public:
    static VinylSpin &instance();

    /** 挂到宿主控件上（UI 线程；控件须为正方形，边长取自控件 position）。
     *  会把一张（空白）内存位图交给控件当背景；返回 false = 环境不成立（控件为空/非方形）。 */
    bool attach(ZKBase *host);

    /** 摘下来（UI 线程；onUI_quit）。不释放已交给框架的位图（框架随控件销毁释放）。 */
    void detach();

    /** 换封面（UI 线程；解码 + 缩放在后台线程）。角度**回到 0 度**。 */
    void setCover(const char *pngPath);

    /** 播放/暂停联动（UI 线程）。暂停即停转，恢复从当前角度继续。 */
    void setPlaying(bool playing);

    /** 每拍驱动（UI 线程；UI 定时器调，40ms = 25fps）。 */
    void tick();

    /** 运行期切后端（UI 线程；播放页「黑胶后端」按键调，真机对比用）：
     *  want = 0 定点映射 / 1 nanovg(AGG)。返回**实际生效**的后端（0/1）。
     *  · 切 nanovg 时惰性建 AGG 上下文+封面纹理；建不起来保持原后端（只 warning，不报错）。
     *  · 切换后强制下一拍重画（暂停态也刷新一帧），角度/时间口径不变、不重置角度。
     *  · 未 attach 时只记下意愿，attach() 按它建上下文。 */
    int setBackend(int want);

    /* ---------------- 诊断/验收读数 ---------------- */
    int backend() const;          /**< 实际生效后端：0 = 定点映射；1 = nanovg(AGG) */
    bool attached() const;
    bool hasCover() const;
    int angleDeg() const;        /**< 当前角度（度，0..359） */    int frames() const;          /**< 已上屏帧数 */
    int fpsX10() const;          /**< 实测帧率 x10（如 248 = 24.8fps；样本不足回 0） */
    int lastRotMs() const;       /**< 最近一次旋转计算耗时 ms */
    int lastPubMs() const;       /**< 最近一次上屏（UI 线程）耗时 ms */
    int mode() const;            /**< 0 = 同张位图原地改像素；1 = 每帧换新位图 */

    /** 调试埋点（真机定位「切歌瞬间帧内容异常」用；默认关闭）：
     *  存在 `/tmp/vinyl_dump` 文件时，把**渲染出来的帧缓冲**与**交给控件的位图**逐帧 dump 到 /tmp/vdump/。
     *  用途：不经屏幕/合成就能看 app 自己的缓冲到底干不干净——
     *  · dump 干净 & 屏幕花 → 合成/显示路径（框架级）问题
     *  · dump 就花 → 这条管线（渲染或拷贝）的问题
     *  返回本拍是否在 dump（仅供诊断行显示）。 */
    bool dumpEnabled() const;
    int dumpCount() const;

private:
    VinylSpin();
    VinylSpin(const VinylSpin &);
    VinylSpin &operator=(const VinylSpin &);

    struct Impl;
    static void doRotate(Impl *d, int srcVer, int idx, int n, uint8_t *buf);

    Impl *mImpl;
};

} /* namespace zk */

#endif /* _ZK_VINYL_SPIN_H_ */
