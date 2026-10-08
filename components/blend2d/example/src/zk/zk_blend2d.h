/*
 * zk_blend2d.h —— Blend2D 门面（zk::b2d）v0.1 —— 「离屏矢量出图」的唯一对外接口
 *
 * 一句话定位：**这是"离屏矢量出图引擎"，不是"2D 加速器"**。
 *   Z20（ARM32）上 Blend2D **没有 JIT、没有走硬件合成**（NEON 重编后才有向量数据通路），
 *   它的价值是**补上现有路径画不了的东西**：任意矢量路径 / 抗锯齿 / 渐变 / 阴影 /
 *   直读 TTF·OTF 文本 / 内置 PNG·JPEG·BMP 编解码 / 全组合混合模式。
 *   它**不接管** easyui 的控件、布局、事件、触摸 —— 只在内存里画好一帧，
 *   再通过 easyui 既有的「内存位图」通道上屏（`setBackgroundBmp` + `setInvalid(!isInvalid())`）。
 *
 * 硬约定（写代码前先读这 6 条）：
 *   1) 本头文件**不出现任何 `BL*` 类型**（底层细节不外泄）；想直接用 Blend2D 原生 API，
 *      自己 include <blend2d.h> 并声明依赖包 `blend2d`，与门面可共存。
 *   2) 所有接口**同步返回** `Result{code,msg}`，`msg` 是人话；不抛异常、不静默失败。
 *   3) 画布**建一次、复用到底**：`open()` 之后反复 `roundRect/shadow/...` + `submit()`，
 *      **不要每帧 open/close**（那会反复分配画布与管线缓存，实测代价极高）。
 *   4) **帧内存格式 = BGRA（每像素 4 字节，内存序 B,G,R,A，预乘 alpha）**，与 easyui 32 位位图
 *      字节序一致 ⇒ **零转换直传**。颜色参数统一写 **0xAARRGGBB**（与十六进制习惯一致）。
 *   5) **推荐配方（性能）**：不透明底 + `CompOp=SRC_COPY` 直传（本门面默认就是）、
 *      `threadCount=2`、阴影 ≤2 层（或预烘成 PNG 贴图）、画布复用。
 *      ⚠️ 定位：**别指望 NEON/库加速救场** —— 真正的胜负手是上面这几条"零成本配方"。
 *   6) **部署通道写死两条**（少了它，设备上报 `initLib error`）：
 *      · 调试：`fsc launch` **不推**第三方包 `.so` → 手动 `adb push libblend2d.so /tmp/`；
 *      · 量产：把 `.so` 放进 `<工程>/src/dependencies/lib/` → `fsc pack`（进 `update.img`）。
 *
 * 详见同目录 README.md（用法/配方/性能表/部署）、platforms.md（平台矩阵）、lib/BUILD_INFO.md（两个库档来源）。
 *
 * 版本记录
 *   - 0.1.0（2026-10-01）首版：最小面 = 初始化/销毁、离屏画布（圆角矩形/阴影/渐变/文本）、
 *     导出位图给 easyui、threadCount 配置（默认 2）、缓冲复用、unpremultiply 可选开关。
 */
#pragma once

#include <stdint.h>
#include <string>

namespace zk {
namespace b2d {

/** 门面版本（与底层 blend2d 版本分开报；底层版本见 engineInfo() / lib/BUILD_INFO.md） */
const char* version();

// ------------------------------------------------------------------ Result
enum ErrorCode {
    ERR_OK = 0,
    ERR_NOT_OPEN = -1,   // 还没 open()（或已 close()）
    ERR_PARAM = -2,      // 参数不合法（尺寸 <=0、空指针、越界等）
    ERR_NO_MEM = -3,     // 画布/缓冲区分配失败（板子内存小，注意尺寸）
    ERR_IO = -4,         // 落盘/读文件失败（savePng、字体文件不可读）
    ERR_FONT = -5,       // 字体未设置或加载失败（文本 API 需要 TTF/OTF）
    ERR_ENGINE = -6,     // Blend2D 内部返回失败（建上下文/绘制/flush）
    ERR_UNSUPPORTED = -7,// 当前平台/档位不支持（msg 说明该怎么办）
};

struct Result {
    int code = ERR_OK;
    std::string msg;                    // 人话，可直接打日志
    bool ok() const { return code == ERR_OK; }
    static Result ok_(const char* m = "") { Result r; r.code = ERR_OK; r.msg = m; return r; }
    static Result err(int c, const std::string& m) { Result r; r.code = c; r.msg = m; return r; }
};

// ------------------------------------------------------------------ 配置
struct Config {
    int  width  = 480;                  // 画布宽（像素）
    int  height = 480;                  // 画布高（像素）
    int  threadCount = 2;               // 0 = 全同步；2 = 双核白捡（Z20 实测 480x480 -48%~-49%）
    bool unpremultiply = false;         // 画布**含透明**时置 true（上屏前转非预乘）；
                                        // 不透明底 + SRC_COPY 直传时保持 false（零转换）
    std::string fontPath;               // TTF/OTF 路径；留空 = 不加载（文本 API 返回 ERR_FONT）
    uint32_t background = 0xFF12161C;   // clear() 默认底色（0xAARRGGBB）
};

// ------------------------------------------------------------------ 几何
struct RoundRect {
    float x, y, w, h, radius;
    RoundRect(float x_, float y_, float w_, float h_, float radius_ = 0.0f)
        : x(x_), y(y_), w(w_), h(h_), radius(radius_) {}
};

// ------------------------------------------------------------------ 画布
/**
 * 离屏画布：内部 = 一块 BGRA 像素缓冲 + 一个 Blend2D 上下文（复用，不重启）。
 * **单实例对应一块画布**；一页一个 Canvas 即可（不要每帧 new）。
 */
class Canvas {
public:
    Canvas();
    ~Canvas();

    /** 建画布并（可选）加载字体。成功后才可用；重复调用 = 重建。 */
    Result open(const Config& cfg = Config());
    /** 释放画布/上下文/缓冲。可重复调用。 */
    void   close();
    bool   isOpen() const;

    int    width()  const;              // 画布宽
    int    height() const;              // 画布高
    int    pitch()  const;              // 行字节数 = width()*4（BGRA，4 字节/像素）
    /** 帧内存首地址（BGRA 预乘 alpha）。直接交给 easyui：`bmp.data = (uint8_t*)canvas.pixels();` */
    void*  pixels() const;

    /** 懒加载/替换字体（文本 API 用）。 */
    Result setFont(const char* ttfPath);

    // ---- 绘制（每次绘制后都要 submit() 才算画完这一帧）----
    /** 用 Config.background 填满整屏（不透明底，SRC_COPY）。 */
    Result clear();
    /** 用指定颜色填满整屏（0xAARRGGBB）。 */
    Result clear(uint32_t argb);

    /** 圆角矩形填充；strokeWidth>0 时同步描一圈边（strokeArgb=0 用 argb 的半透明近似）。 */
    Result roundRect(const RoundRect& r, uint32_t argb,
                     float strokeWidth = 0.0f, uint32_t strokeArgb = 0);

    /** 阴影（多层半透明圆角叠加）：**层数越多越贵**（实测 8 层能吃掉整帧 83%）。
     *  建议 layers <= 2，或干脆把阴影预烘成一张 PNG 贴图（零运行时成本）。 */
    Result shadow(const RoundRect& r, uint32_t argb = 0x12000000,
                  int layers = 2, float dy = 6.0f);

    /** 圆角矩形 + 线性渐变填充（fromArgb 左上 → toArgb 右下；angleDeg 预留，当前按对角）。 */
    Result gradientRoundRect(const RoundRect& r, uint32_t fromArgb, uint32_t toArgb,
                             float angleDeg = 0.0f);

    /** 文本（OpenType 直读，CJK 正常）。x,y = 基线左端（注意是 baseline，不是 top）。 */
    Result text(float x, float y, float size, const char* utf8, uint32_t argb = 0xFF000000);

    /** 量文本宽度（像素）；未设置字体返回 0。 */
    float  textWidth(float size, const char* utf8);

    /** 提交这一帧：flush(SYNC)。提交后 pixels() 内容才是最终像素。 */
    Result submit();

    /** 把当前画布像素编码成 PNG 落盘（离屏出图/取证/PC 预烘都用它）。 */
    Result savePng(const char* path);

    /** 上一次 submit() 的耗时（ms，CLOCK_MONOTONIC 口径；未提交过返回 0）。 */
    double lastFrameMs() const;

    /** 引擎自述：blend2d 版本 / 构建类型 / CPU 架构 / 编译器（排错第一手信息）。 */
    std::string engineInfo();

private:
    Canvas(const Canvas&);
    Canvas& operator=(const Canvas&);
    struct Impl;
    Impl* m_impl;
};

}  // namespace b2d
}  // namespace zk
