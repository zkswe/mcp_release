/*
 * zk_blend2d.cpp —— Blend2D 门面（zk::b2d）实现
 *
 * 只做四件事（这就是本组件的全部价值：把容易翻车的四件事固定下来）：
 *   ① 画布格式/alpha 桥接：BGRA(预乘) ←→ easyui 32 位位图，**零转换直传**（Z20 实测逐像素 0 差异）；
 *   ② 缓冲复用：画布/上下文建一次，反复绘制 + submit（禁逐帧 new BLImage）；
 *   ③ 刷帧口径：只挂一次 setBackgroundBmp，每帧 setInvalid(!isInvalid())（由业务在 example 里做）；
 *   ④ 阴影/文本/渐变这些"便宜好用的配方"包成一行调用 + 人话错误。
 *
 * 这里 include 了 <blend2d.h>（实现层），但**对外头文件不含任何 BL* 类型**。
 */
#include "zk/zk_blend2d.h"

#include <blend2d.h>

#include <stdio.h>
#include <string.h>
#include <time.h>
#include <vector>

namespace zk {
namespace b2d {

const char* version() { return "0.1.0"; }

namespace {

inline double nowMs() {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double) ts.tv_sec * 1000.0 + (double) ts.tv_nsec / 1000000.0;
}

/* 颜色约定：对外 0xAARRGGBB（与十六进制习惯一致），底层 BLRgba32 同序。 */
inline BLRgba32 toRgba(uint32_t argb) { return BLRgba32(argb); }

/* 预乘 alpha -> 直通 alpha（画布含透明、且上层按非预乘解释时才需要） */
void unpremultiplyInPlace(uint8_t* p, size_t px) {
    for (size_t i = 0; i < px; ++i, p += 4) {
        uint32_t a = p[3];
        if (a == 255 || a == 0) {
            if (a == 0) { p[0] = p[1] = p[2] = 0; }
            continue;
        }
        p[0] = (uint8_t) ((uint32_t) p[0] * 255u / a);
        p[1] = (uint8_t) ((uint32_t) p[1] * 255u / a);
        p[2] = (uint8_t) ((uint32_t) p[2] * 255u / a);
    }
}

}  // namespace

// ================================================================ Impl
struct Canvas::Impl {
    int      w = 0;
    int      h = 0;
    int      pitch = 0;
    uint8_t* buf = 0;            // 我们自己的帧缓冲（pixels() 交出去的就是它）
    BLImage  img;                // 绑定到 buf（createFromData），不拥有内存
    BLContext* ctx = 0;          // 复用，不每帧重建
    bool     open = false;
    bool     unpremul = false;
    int      threadCount = 0;
    uint32_t background = 0xFF12161C;

    BLFontFace face;             // 字体（可选）
    bool     faceReady = false;
    std::string fontPath;
    std::vector<std::pair<float, BLFont> > fonts;   // 按 size 缓存

    double   lastMs = 0.0;

    BLFont* fontFor(float size) {
        if (!faceReady) return 0;
        for (size_t i = 0; i < fonts.size(); ++i) {
            if (fonts[i].first == size) return &fonts[i].second;
        }
        BLFont f;
        if (f.createFromFace(face, size) != BL_SUCCESS) return 0;
        fonts.push_back(std::make_pair(size, f));
        return &fonts.back().second;
    }

    void reset() {
        fonts.clear();
        if (ctx) { delete ctx; ctx = 0; }
        faceReady = false;
        face.reset();
        fontPath.clear();
        img.reset();
        if (buf) { free(buf); buf = 0; }
        w = h = pitch = 0;
        open = false;
    }
};

// ================================================================ 生命周期
Canvas::Canvas() : m_impl(new Impl()) {}
Canvas::~Canvas() { close(); delete m_impl; m_impl = 0; }

Result Canvas::open(const Config& cfg) {
    Impl* p = m_impl;
    p->reset();

    if (cfg.width <= 0 || cfg.height <= 0) {
        return Result::err(ERR_PARAM, "画布尺寸不合法（width/height 必须 > 0）");
    }
    if ((int64_t) cfg.width * (int64_t) cfg.height * 4 > 64 * 1024 * 1024) {
        return Result::err(ERR_PARAM, "画布过大（>64 MB），小内存板请降尺寸或分块渲染");
    }

    p->w = cfg.width;
    p->h = cfg.height;
    p->pitch = cfg.width * 4;
    p->unpremul = cfg.unpremultiply;
    p->threadCount = cfg.threadCount;
    p->background = cfg.background;

    p->buf = (uint8_t*) malloc((size_t) p->pitch * (size_t) p->h);
    if (p->buf == 0) {
        p->reset();
        return Result::err(ERR_NO_MEM, "画布缓冲分配失败（内存不足），可减小尺寸");
    }
    memset(p->buf, 0, (size_t) p->pitch * (size_t) p->h);

    // 绑定外部内存：pixels() 稳定指向 p->buf，pitch 已知 = w*4（不依赖库内部 stride）
    if (p->img.createFromData(p->w, p->h, BL_FORMAT_PRGB32, p->buf, (intptr_t) p->pitch)
        != BL_SUCCESS) {
        p->reset();
        return Result::err(ERR_ENGINE, "BLImage.createFromData 失败（引擎拒绝了该尺寸/格式）");
    }

    if (p->threadCount > 0) {
        BLContextCreateInfo ci{};
        ci.threadCount = (uint32_t) p->threadCount;
        p->ctx = new BLContext(p->img, ci);
    } else {
        p->ctx = new BLContext(p->img);
    }
    if (p->ctx == 0 || !p->ctx->isValid()) {
        p->reset();
        return Result::err(ERR_ENGINE, "BLContext 创建失败（threadCount 或画布尺寸异常）");
    }

    p->open = true;

    if (!cfg.fontPath.empty()) {
        Result fr = setFont(cfg.fontPath.c_str());
        if (!fr.ok()) {           // 字体加载失败 = 真失败（不静默降级）
            close();
            return fr;
        }
    }
    return Result::ok_("画布已就绪");
}

void Canvas::close() {
    if (m_impl) m_impl->reset();
}

bool Canvas::isOpen() const { return m_impl->open; }

int Canvas::width()  const { return m_impl->w; }
int Canvas::height() const { return m_impl->h; }
int Canvas::pitch()  const { return m_impl->pitch; }
void* Canvas::pixels() const { return m_impl->open ? (void*) m_impl->buf : 0; }

Result Canvas::setFont(const char* ttfPath) {
    Impl* p = m_impl;
    if (ttfPath == 0 || ttfPath[0] == 0) {
        return Result::err(ERR_PARAM, "字体路径为空");
    }
    BLFontFace face;
    BLResult r = face.createFromFile(ttfPath);
    if (r != BL_SUCCESS) {
        char m[256];
        snprintf(m, sizeof(m), "字体加载失败：%s（文件不存在/不是 TTF·OTF/读取无权限）", ttfPath);
        return Result::err(ERR_FONT, m);
    }
    p->face = face;
    p->faceReady = true;
    p->fonts.clear();
    p->fontPath = ttfPath;
    char m[256];
    snprintf(m, sizeof(m), "字体已加载：%s", ttfPath);
    return Result::ok_(m);
}

// ================================================================ 绘制
Result Canvas::clear() { return clear(m_impl->background); }

Result Canvas::clear(uint32_t argb) {
    Impl* p = m_impl;
    if (!p->open) return Result::err(ERR_NOT_OPEN, "画布未 open()");
    p->ctx->setCompOp(BL_COMP_OP_SRC_COPY);           // 不透明底直传（推荐配方的第一步）
    BLResult r = p->ctx->fillAll(toRgba(argb));
    p->ctx->setCompOp(BL_COMP_OP_SRC_OVER);           // 后续绘制走正常混合
    if (r != BL_SUCCESS) return Result::err(ERR_ENGINE, "fillAll 失败（引擎返回非成功）");
    return Result::ok_();
}

Result Canvas::roundRect(const RoundRect& rr, uint32_t argb, float strokeWidth, uint32_t strokeArgb) {
    Impl* p = m_impl;
    if (!p->open) return Result::err(ERR_NOT_OPEN, "画布未 open()");
    if (rr.w <= 0 || rr.h <= 0) return Result::err(ERR_PARAM, "roundRect 尺寸必须 > 0");
    BLRoundRect r(rr.x, rr.y, rr.w, rr.h, rr.radius);
    BLResult r1 = p->ctx->fillRoundRect(r, toRgba(argb));
    if (r1 != BL_SUCCESS) return Result::err(ERR_ENGINE, "fillRoundRect 失败");
    if (strokeWidth > 0.0f) {
        p->ctx->setStrokeStyle(toRgba(strokeArgb ? strokeArgb : argb));
        p->ctx->setStrokeWidth(strokeWidth);
        BLResult r2 = p->ctx->strokeRoundRect(BLRoundRect(rr.x + 0.5f, rr.y + 0.5f,
                                                          rr.w - 1.0f, rr.h - 1.0f, rr.radius));
        if (r2 != BL_SUCCESS) return Result::err(ERR_ENGINE, "strokeRoundRect 失败");
    }
    return Result::ok_();
}

Result Canvas::shadow(const RoundRect& rr, uint32_t argb, int layers, float dy) {
    Impl* p = m_impl;
    if (!p->open) return Result::err(ERR_NOT_OPEN, "画布未 open()");
    if (rr.w <= 0 || rr.h <= 0) return Result::err(ERR_PARAM, "shadow 尺寸必须 > 0");
    if (layers <= 0) return Result::ok_("layers<=0，跳过阴影");
    if (layers > 32) layers = 32;
    /* ⚠️ 阴影是整帧最贵的一段（实测 8 层占 480x480 整帧 83%）：建议 <=2 层或预烘 PNG */
    for (int i = layers; i >= 1; --i) {
        BLRoundRect r(rr.x - i, rr.y - i + dy, rr.w + 2.0f * i, rr.h + 2.0f * i, rr.radius + i);
        BLResult r1 = p->ctx->fillRoundRect(r, toRgba(argb));
        if (r1 != BL_SUCCESS) return Result::err(ERR_ENGINE, "shadow 绘制失败");
    }
    return Result::ok_();
}

Result Canvas::gradientRoundRect(const RoundRect& rr, uint32_t fromArgb, uint32_t toArgb,
                                 float angleDeg) {
    Impl* p = m_impl;
    (void) angleDeg;   // 预留：当前固定按"左上 -> 右下"对角渐变
    if (!p->open) return Result::err(ERR_NOT_OPEN, "画布未 open()");
    if (rr.w <= 0 || rr.h <= 0) return Result::err(ERR_PARAM, "gradient 尺寸必须 > 0");
    BLGradient g(BLLinearGradientValues(rr.x, rr.y, rr.x + rr.w, rr.y + rr.h));
    g.addStop(0.0, toRgba(fromArgb));
    g.addStop(1.0, toRgba(toArgb));
    BLResult r = p->ctx->fillRoundRect(BLRoundRect(rr.x, rr.y, rr.w, rr.h, rr.radius), g);
    if (r != BL_SUCCESS) return Result::err(ERR_ENGINE, "渐变填充失败");
    return Result::ok_();
}

Result Canvas::text(float x, float y, float size, const char* utf8, uint32_t argb) {
    Impl* p = m_impl;
    if (!p->open) return Result::err(ERR_NOT_OPEN, "画布未 open()");
    if (utf8 == 0 || utf8[0] == 0) return Result::ok_("空文本，跳过");
    if (!p->faceReady) {
        return Result::err(ERR_FONT, "未设置字体：先 open({fontPath}) 或 setFont(\"xxx.ttf\")");
    }
    BLFont* f = p->fontFor(size);
    if (f == 0) return Result::err(ERR_FONT, "该字号的字体实例创建失败（size 太小或字体异常）");
    p->ctx->setFillStyle(toRgba(argb));
    BLResult r = p->ctx->fillUtf8Text(BLPoint(x, y), *f, utf8);
    if (r != BL_SUCCESS) return Result::err(ERR_ENGINE, "fillUtf8Text 失败");
    return Result::ok_();
}

float Canvas::textWidth(float size, const char* utf8) {
    Impl* p = m_impl;
    if (!p->faceReady || utf8 == 0 || utf8[0] == 0) return 0.0f;
    BLFont* f = p->fontFor(size);
    if (f == 0) return 0.0f;
    BLGlyphBuffer gb;
    if (gb.setUtf8Text(utf8) != BL_SUCCESS) return 0.0f;
    if (f->shape(gb) != BL_SUCCESS) return 0.0f;
    BLTextMetrics tm;
    if (f->getTextMetrics(gb, tm) != BL_SUCCESS) return 0.0f;
    return (float) tm.advance.x;
}

// ================================================================ 提交 / 导出
Result Canvas::submit() {
    Impl* p = m_impl;
    if (!p->open) return Result::err(ERR_NOT_OPEN, "画布未 open()");
    double t0 = nowMs();
    BLResult r = p->ctx->flush(BL_CONTEXT_FLUSH_SYNC);
    p->lastMs = nowMs() - t0;
    if (r != BL_SUCCESS) return Result::err(ERR_ENGINE, "flush 失败");
    if (p->unpremul) {
        unpremultiplyInPlace(p->buf, (size_t) p->w * (size_t) p->h);
    }
    return Result::ok_();
}

Result Canvas::savePng(const char* path) {
    Impl* p = m_impl;
    if (!p->open) return Result::err(ERR_NOT_OPEN, "画布未 open()");
    if (path == 0 || path[0] == 0) return Result::err(ERR_PARAM, "输出路径为空");
    BLImageCodec codec;
    codec.findByName("PNG");
    BLResult r = p->img.writeToFile(path, codec);
    if (r != BL_SUCCESS) {
        char m[256];
        snprintf(m, sizeof(m), "PNG 落盘失败：%s（路径不可写/空间不足）", path);
        return Result::err(ERR_IO, m);
    }
    return Result::ok_("PNG 已写出");
}

double Canvas::lastFrameMs() const { return m_impl->lastMs; }

std::string Canvas::engineInfo() {
    BLRuntimeBuildInfo build;
    BLRuntimeSystemInfo sys;
    memset(&build, 0, sizeof(build));
    memset(&sys, 0, sizeof(sys));
    blRuntimeQueryInfo(BL_RUNTIME_INFO_TYPE_BUILD, &build);
    blRuntimeQueryInfo(BL_RUNTIME_INFO_TYPE_SYSTEM, &sys);
    char buf[320];
    snprintf(buf, sizeof(buf),
             "blend2d ver=%u.%u.%u buildType=%u cpuArch=0x%08X cpuFeatures=0x%08X coreCount=%u compiler=%s",
             build.majorVersion, build.minorVersion, build.patchVersion, build.buildType,
             sys.cpuArch, sys.cpuFeatures, sys.coreCount, build.compilerInfo);
    return std::string(buf);
}

}  // namespace b2d
}  // namespace zk
