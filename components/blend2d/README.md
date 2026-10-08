# blend2d —— 离屏矢量出图 `zk::b2d` v0.1（**头 + 门面源码 + 两个库档**）

> **定位一句话：这是「离屏矢量出图引擎」，不是「2D 加速器」。**
> Z20（ARM32）上 Blend2D **没有 JIT、不走硬件合成**；它的价值是**补上现有渲染路径画不了的东西**：
> 任意矢量路径 / 抗锯齿 / 渐变 / 阴影 / **直读 TTF·OTF 文本** / 内置 PNG·JPEG·BMP 编解码 / 全组合混合模式。
> 它**不接管** easyui 的控件、布局、事件、触摸 —— 只在内存里画好一帧，再走 easyui **既有的内存位图通道**上屏
> （`setBackgroundBmp` 挂一次 + `setInvalid(!isInvalid())` 翻帧），与 `components/vinyl`、`projects/FlyMapDemo`(AGG) 同一条路数。
>
> **交付形态**：`include/zk/zk_blend2d.h`（唯一对外头，**不含任何 `BL*` 类型**）+ `src/zk_blend2d.cpp`（门面实现，拷进工程一起编）
> + **两个库档** `lib/z20/`（原厂）与 `lib/z20-neon/`（自编 NEON，性能档）+ `lib/BUILD_INFO.md`（构建凭据）。
> **不 vendored blend2d 源码**：上游**没有 tag**，只给 `scripts/build-neon.sh`（gitee 镜像取源 + 锁 commit `a7f9476` + cmake 命令原文）。
>
> **版本记录**
> - **0.1.0（2026-10-01）** 首版：门面最小面（初始化/销毁、离屏画布：圆角矩形/阴影/渐变/文本、导出位图给 easyui、
>   `threadCount` 默认 2、缓冲复用、`unpremultiply` 可选）；两个库档入库；`scripts/{build-neon.sh,verify_libs.py}`；
>   Z20 `example/`（可编，未上真机）。依据：`references/kb/blend2d-z20-assessment.md`（可用性评估）、
>   `temp/b2d_dev/REPORT.md`（原厂真机基线）、`temp/blend2d_neon/REPORT.md`（NEON 重编 + 真机复测）。

---

## 1. 它解决什么问题（能补 / 不能补）

| 能力 | 现有路径（控件 / ZKPainter / 自研画布） | **Blend2D（本组件）** |
|---|---|---|
| 任意矢量路径（贝塞尔/多边形/**描边**/虚线） | ❌（ZKPainter 只有整数坐标的线/三角/矩形/弧） | ✅ 完整 `BLPath` |
| 抗锯齿质量 | 靠切图 / 无 AA 保证 | ✅ 高质量 AA（官方主打） |
| 渐变（线性/径向/锥形、多 stop） | ❌（仅单色） | ✅ |
| 文本 | 文本控件（**档位预烘、不放大**） | ✅ **直读 TTF/OTF，字号任意，CJK 正常** |
| 阴影/模糊 | ❌ | ⚠️ 多层半透明近似（**无内建高斯模糊**；层数越少越好） |
| 图片编解码 | 框架 `BitmapHelper` | ✅ 内置 PNG/JPEG/BMP/QOI（编+解） |
| 混合模式 / 高质量缩放 | 有限 | ✅ 全 `BLCompOp` |
| **离屏合成再上屏** | ✅（`setBackgroundBmp`） | ✅ 天然离屏（`BLImage`），走同一条通道 |
| **ARM32 加速** | 框架侧 blit/α/旋转 | ❌ **无 JIT、无硬件合成**；NEON 数据通路要自己重编（性能档，+15~18%） |

**不能解决**：不替代 easyui 控件系统（没有控件/布局/事件/触摸/列表回收）；不做真 3D；**不要把官网 x86 性能数字搬过来**。

---

## 2. 快速开始（拷 4 个文件，编 ~25 行代码）

```cpp
#include "zk/zk_blend2d.h"          // 组件唯一对外头（不含任何 BL* 类型）

static zk::b2d::Canvas sCanvas;     // ★ 建一次，复用到底（禁逐帧 new）
static bitmap_t        sBmp;

static void onUI_init() {
    zk::b2d::Config cfg;
    cfg.width = 480;  cfg.height = 440;
    cfg.threadCount = 2;                                   // ★ 零成本优化①
    cfg.fontPath = "/res/font/zkswe-hans-common.ttf";      // 文本 API 需要 TTF/OTF
    zk::b2d::Result r = sCanvas.open(cfg);
    if (!r.ok()) { LOGD("open 失败: %s", r.msg.c_str()); return; }

    // 帧缓冲交给 easyui：BGRA / 预乘 alpha / pitch = w*4（与 PRGB32 内存序一致，零转换）
    memset(&sBmp, 0, sizeof(sBmp));
    sBmp.type = 0x01; sBmp.bits = 32; sBmp.bytes = 4; sBmp.alpha = 1;
    sBmp.width = 480; sBmp.height = 440; sBmp.pitch = sCanvas.pitch();
    sBmp.data = (uint8_t*) sCanvas.pixels();

    renderFrame(0);
    mB2dCanvasPtr->setBackgroundBmp(&sBmp);                // ★ 只挂一次
    mB2dCanvasPtr->setInvalid(!mB2dCanvasPtr->isInvalid());
}

static void renderFrame(int idx) {
    zk::b2d::RoundRect card(24, 26, 432, 240, 26);
    sCanvas.clear();                                       // 不透明底 + SRC_COPY 直传
    sCanvas.shadow(card, 0x14000000, 2, 6.0f);             // ★ 零成本优化②：阴影 2 层
    sCanvas.roundRect(card, 0xFFF8F9FB, 1.0f, 0x33000000); // 卡片 + 1px 描边
    sCanvas.gradientRoundRect(zk::b2d::RoundRect(40, 286, 400, 26, 13), 0xFF3E7BFA, 0xFF17C964);
    sCanvas.text(40, 96, 30.0f, "Blend2D on Z20", 0xFF1B1B1F);
    sCanvas.submit();                                      // flush(SYNC)
}

// 定时器里：renderFrame(++i); ctrl->setInvalid(!ctrl->isInvalid());   // ★ 平台唯一刷帧口径
```

**完整可编示例** → [`example/`](example/)（Z20 480×480 工程，本轮 `fsc build -p Z20` **实测通过**，见 `example/README.md`）。
**换性能档**：把 `lib/z20-neon/libblend2d.so` 覆盖到 `<工程>/src/dependencies/lib/libblend2d.so`，**代码一行不改**。

---

## 3. API 一览（最小面，全同步 `Result{code,msg}`）

| 分类 | 接口 | 说明 |
|---|---|---|
| 生命周期 | `Canvas()/ ~Canvas()` | 单实例 = 一块画布 |
| | `Result open(const Config&)` / `void close()` / `bool isOpen()` | 建/释放画布（**复用，不要每帧 open**） |
| 画布信息 | `width() / height() / pitch() / void* pixels()` | `pitch = width*4`；`pixels()` 直接喂 `bitmap_t.data` |
| 字体 | `Result setFont(const char* ttf)` | 懒加载/替换（`Config.fontPath` 也行） |
| 绘制 | `Result clear()` / `clear(uint32_t argb)` | 填底（`0xAARRGGBB`） |
| | `Result roundRect(const RoundRect&, uint32_t argb, float strokeW=0, uint32_t strokeArgb=0)` | 圆角矩形（+可选描边） |
| | `Result shadow(const RoundRect&, uint32_t argb=0x12000000, int layers=2, float dy=6)` | 阴影（**层数 ≤2**） |
| | `Result gradientRoundRect(const RoundRect&, uint32_t from, uint32_t to, float angleDeg=0)` | 线性渐变圆角矩形 |
| | `Result text(float x, float y, float size, const char* utf8, uint32_t argb=0xFF000000)` | 文本（**x,y = 基线左端**） |
| | `float textWidth(float size, const char* utf8)` | 量宽（未设字体返回 0） |
| 提交/导出 | `Result submit()` / `double lastFrameMs()` | 提交一帧 + 上一帧耗时（ms） |
| | `Result savePng(const char* path)` | 离屏出图（预烘素材/取证/PC 生成都走它） |
| 诊断 | `std::string engineInfo()` / `const char* version()` | 引擎自述 / 门面版本 |
| 配置 | `Config{ width,height, threadCount=2, unpremultiply=false, fontPath, background }` | `threadCount=0` = 全同步 |

**错误码**：`ERR_NOT_OPEN/-1`、`ERR_PARAM/-2`、`ERR_NO_MEM/-3`、`ERR_IO/-4`、`ERR_FONT/-5`、`ERR_ENGINE/-6`、`ERR_UNSUPPORTED/-7`；
`msg` 全是人话（可直接打日志/上屏），**不静默失败**。
**线程模型**：全部接口**同步返回**；绘制在库内线程池（`threadCount`）执行，`submit()` 阻塞到本帧完成 —— 业务侧不需要懂 run loop。
**颜色约定**：对外 **`0xAARRGGBB`**；帧内存是 **BGRA（预乘 alpha）**，与 easyui 32 位位图同序 ⇒ 零转换。

---

## 4. 默认配方 + 性能表（**别指望 NEON，先做零成本优化**）

**默认配方（照抄就对）**
1. **不透明底 + `SRC_COPY` 直传**（门面 `clear()` 默认如此）→ 零转换、最便宜路径；
2. **`threadCount = 2`**（Z20 双核白捡）→ 480×480 **−48.4%**；
3. **阴影 ≤2 层**（或把阴影预烘成一张 PNG 贴图）→ 480×480 **−61.3%**；
4. **画布缓冲复用**（`open` 一次，反复画 + `submit`）→ 禁逐帧 `new BLImage`；
5. 文本不要每帧重排（字号会缓存，但 `textWidth` 量宽是额外开销）。

**性能表（Z20 真机，ms/帧 = 绘制 + `flush(SYNC)`，不含上屏 blit）**

| 用例 | 原厂档 | 性能档(NEON) | 变化 | 叠加零成本优化后 |
|---|---|---|---|---|
| 480×480 同步 | 28.005 | 23.707 | **−15.3%** | — |
| 480×480 + `t=2` | 14.154 | 12.222 | −13.6% | 优化① → **12.222** |
| 800×1280 同步 | 109.439 | 89.696 | **−18.0%** | — |
| 480×480 阴影 8→2 层 | 10.442 | 9.170 | −12.2% | 优化② → **9.170** |
| 480×480 阴影 2 层 + `t=2` | 5.693 | **5.171** | −9.2% | ①+② → **5.171（−78.2%）** |
| 分项 `fillAll` | 0.706 | 0.331 | **−53.1%** | 大面积填充是 NEON 最吃得上的 |
| 分项 文本段（3 行） | 2.44 | 2.62 | ⚠️ **未见加速** | 路径/字形几何不吃 SIMD |

**结论（写清楚，别被数字带偏）**
- **NEON 是真的（`q` 寄存器 0 → 17,364、`vld1/vst1` 0 → 905/2,126），也是省事的（ABI 787:787 全等、换库零改动、渲染逐字节相同）**，
  但它只是**配角**：15~18% 的提速换 `.so` +27.2% 体积与固件 +116 KB。
- **真正的胜负手是两条零成本配方**：`threadCount=2` 与阴影减层 —— 480×480 从 28.0 → **5.17 ms（−78.2%）**，留 2.5× 帧预算余量。
- **逐帧全屏（800×1280 = 89.7 ms）即便 NEON 化也不适合做动画**：维持「静态/低频刷新 + 小画布逐帧 + PC 侧预烘 PNG」的定位。
- 帧预算口径：40 ms（25 fps）的 1/3 = **13.3 ms** 才算"能做逐帧动效"。

---

## 5. 部署通道（**必须写死，否则每个使用者都会撞 `initLib error`**）

| 通道 | 怎么做 | 实测 |
|---|---|---|
| 调试 | `fsc launch` **不推**第三方包 `.so` → `adb push libblend2d.so /tmp/libblend2d.so` + `setprop ctl.restart zkswe` | ✅ 跑通（无 `initLib error`，md5 两侧一致） |
| **量产/交付** | 把选定的 `.so` 放进 `<工程>/src/dependencies/lib/libblend2d.so` → `fsc pack`（进 `update.img`） | ✅ 原厂档 `update.img` 1,143,336 B / NEON 档 1,262,120 B / 无 blend2d 基线 647,720 B |

> Z20 `res` 分区上限 **7,470,080 B**，出包前先看余量；性能档额外依赖 **`libgcc_s.so.1`**（Z20 有，别板要先确认）。

---

## 6. 平台矩阵

| 平台 | 结论 |
|---|---|
| **Z20**（ARMv7 glibc） | ✅ **已验**（真机跑通 + 性能/效果复测两轮） |
| Z21 / T113EMMC（ARMv7 glibc） | ⚠️ **未验证**（注册表无包；理论上同 libc 可复用同一份 `.so`） |
| V85X / T113(musl) | ❌ **不可直接用**（缺 glibc/`libstdc++`，需 musl 重编 —— 未做） |
| F133/F135/F136（RISC-V64 musl） | ❌ **不可用**（架构不同，需另编 —— 未做） |

逐平台前置条件、实测值、验收命令、未验证清单 → [`platforms.md`](platforms.md)。

---

## 7. 排错顺序（照走，别跳）

```
① initLib error / 加载失败
   → 检查 .so 是否在设备上：调试要 adb push 到 /tmp；量产要 src/dependencies/lib/ + fsc pack
   → 性能档还要看 /lib/libgcc_s.so.1 是否存在
② open() 失败
   ERR_NO_MEM  → 画布太大（480×480=0.88 MB，800×1280=4.10 MB），减小尺寸
   ERR_PARAM   → 宽高 <=0
   ERR_ENGINE  → 上下文/画布创建失败（换原厂档对照排除性能档问题）
   ERR_FONT    → 字体路径不可读/不是 TTF·OTF（open 时给了 fontPath 就会失败关闭，这是有意的）
③ 文本不显示
   → text() 返回 ERR_FONT？（没设字体：open 的 fontPath 或 setFont()）
   → 路径写死了？用候选链（/res/font → /tmp/font → /mnt/extsd/font）
④ 上屏没变化
   → setBackgroundBmp 挂了吗（只挂一次）？每帧 setInvalid(!isInvalid()) 了吗？
   → bitmap_t 的 pitch 是不是 canvas.pitch()？data 是不是 canvas.pixels()？
⑤ 颜色/透明度不对
   → 画布含透明 → Config.unpremultiply = true；不透明底 + SRC_COPY 直传时保持 false（零转换）
⑥ 卡顿 → 先看配方：threadCount=2 了吗？阴影是不是 8 层？画布有没有复用？
```

---

## 8. 怎么把它接进工程

```
components/blend2d/
├─ include/zk/zk_blend2d.h      ← 拷进工程（如 src/zk/）
├─ src/zk_blend2d.cpp           ← 拷进工程一起编（实现层 include <blend2d.h>）
├─ lib/z20/libblend2d.so        ← 原厂档（默认；来源=注册表 blend2d 0.11.1）
├─ lib/z20-neon/libblend2d.so   ← 性能档（NEON 自编；换库零代码改动）
├─ lib/BUILD_INFO.md            ← 两个库档怎么来的（commit/命令/ABI/体积/libgcc_s）
├─ scripts/build-neon.sh        ← 从 gitee 镜像取源 + 锁 commit + cmake 原文（重编性能档）
├─ scripts/verify_libs.py       ← 两档自检（属性/符号 787:787/NEON 命中）
└─ example/                     ← Z20 最小可编工程（本轮 fsc build -p Z20 通过）
```

1. 工程 `Manifest.xml` 声明底层包：`<package id="blend2d" version="0.11.1"/>`（**版本写死，不用 `^`**）
   + 上屏用的 `easyui`（见本模块 [`Manifest.xml`](Manifest.xml)）；
2. `fsc install`（改过 Manifest 必须重跑，否则头文件路径不进 CMake）；
3. 把选定的 `.so` 放到 `<工程>/src/dependencies/lib/libblend2d.so`（工具链会自动加 `-L` 与 rpath）；
4. 编译时把 `src/zk/` 加进 include 路径（`fsc build` 默认已含 `src/`）。

**符号自检（拿到库先跑一次）**
```bash
python components/blend2d/scripts/verify_libs.py            # 全检（含 NEON 反汇编统计）
python components/blend2d/scripts/verify_libs.py --fast     # 秒级（属性 + 符号集合）
# [PASS] ... 结果：16 项，PASS 16，FAIL 0
```

---

## 9. 验收状态（诚实版）

| 项 | 状态 |
|---|---|
| 门面 API（最小面） | ✅ 已实现（`include/` + `src/`） |
| 两个库档 + 构建凭据 | ✅ 入库（md5 与 `temp/blend2d_neon/` 产物一致） |
| 库自检脚本 | ✅ `scripts/verify_libs.py` 全 PASS（16 项，含 ABI 787:787 与 NEON 命中） |
| 示例**编译** | ✅ `fsc build -p Z20` 通过（本轮实测，产物 `libzkgui.so` 301,892 B，NEEDED 含 `libblend2d.so`） |
| 示例**上真机** | ❌ **未做**（本轮纪律只编译不上机；真机通道已由前两轮基准工程验过） |
| Z20 真机性能/效果 | ✅ 已验（**引用前两轮基准工程**的证据，见 `lib/BUILD_INFO.md` §4；本门面形态的真机回归待做） |
| Z21 / T113EMMC / V85X / T113 / F13x | ⏳ / ❌ 未验证（见 `platforms.md` §2/§3） |

---

## 10. 维护者须知

- **两个库档**：原厂档来自官方包仓库（只能"取"，不能"改"）；性能档**必须**按 `lib/BUILD_INFO.md` §1 锁 commit `a7f9476`
  （上游无 tag），用 `scripts/build-neon.sh` 重编，产出后跑 `verify_libs.py` 核对 md5/体积/符号再入库。
- **改了门面头 = 改了公开 API 契约**：同步更新 [§3 API 表]、`example/src/zk/`（示例里的拷贝）与 `example/README.md`。
- **不要把 `BL*` 类型写进 `include/zk/zk_blend2d.h`**（组件规范 §2.1）；要直接用原生 API 的工程自行 include `<blend2d.h>`。
- **别顺手把 blend2d 源码搬进本仓**（体积 + 许可 + 版本分叉）；源码只在构建时从 gitee 镜像取，锁定 commit。
- 相关文档：`references/kb/blend2d-z20-assessment.md`（能力缺口/平台矩阵/未取证清单）、
  `tools/FlyThings_mcp_open/knowledge/devflow/{render-extension-boundary,custom-render-paths,reusable-components}.md`（边界与形态）。
