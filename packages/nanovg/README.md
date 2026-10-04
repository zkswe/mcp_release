# nanovg 1.0.0 —— 矢量绘图库（AGG 软件光栅后端）

> **一句话**：把矢量图形（任意路径 / 抗锯齿 / 渐变 / 贴图）**画进一块内存位图**，再交给 easyui 控件上屏。
> **形态**：上游 nanovg + **厂家自研 AGG 2.7 后端**（`nanovg_agg.h` 的 `nvgCreateAGG`），**不是 GL/Metal 那套**。
> **分发**：`f133 / t113emmc / f136` 走注册表包；**V85X 服务端没有这个包 → 本仓自带 `include/ + lib/v85x/`**（见 §2）。

```
packages/nanovg/
├─ include/nanovg.h           上游公共 API（28,329 B）
├─ include/nanovg_agg.h       厂家 AGG 后端入口（544 B）
├─ lib/v85x/libnanovg.so      V85X（ARMv7 musl）档 · 47,552 B · md5 F5F1157D50AB4A882B464D33804E5B1B
├─ lib/v85x/BUILD.md          档位凭据（ELF 读数 / 符号审计 / 已知缺口）
└─ evidence/                  为什么"没有真机证据"的说明（不是伪造日志）
```

---

## 1. 它解决什么 / 不解决什么

| 能力 | 现有路径（ZKPainter / 自绘） | nanovg(AGG) |
|---|---|---|
| 任意矢量路径（贝塞尔 / 多边形 / 描边 / 虚线） | ❌ 只有整数坐标的线/三角/矩形/弧 | ✅ `nvgBeginPath` 全族 |
| 抗锯齿质量 | 靠切图 / 无 AA 保证 | ✅ AGG 扫描线覆盖 |
| 渐变（线性 / 径向 / 箱形） | ❌ 仅单色 | ⛔ **本构建实测失效** —— 一律退化成纯内色（见 §3.7） |
| 贴图 + 变换（旋转/缩放/倾斜） | 部分（90° 整数倍） | ✅ `nvgImagePattern`（但**不平铺**，须 1:1 覆盖，见 §3.8） |
| 文本 / 字体 | 文本控件（档位预烘、不放大） | ⚠️ **本构建没有字体 API**（§4 缺口） |
| 离屏合成再上屏 | ✅（`setBackgroundBmp`） | ✅ 天然离屏（渲进你的缓冲） |

**不能解决**：不替代 easyui 控件系统（无控件/布局/事件/触摸）；不做真 3D。**别拿官网 x86 性能数字**：ARM32 无 JIT。

---

## 2. 怎么用（V85X，本仓自带包）

V85X 服务端没有这个包，`Manifest.xml` 里写 `<package id="nanovg" version="1.0.0"/>` 也拉不到。做法照 `src/dependencies/`：

```bash
# 1) 头文件进工程 include 路径（拷进 <工程>/src/ 下任一头目录，或放 src/dependencies/include/）
cp packages/nanovg/include/nanovg.h  packages/nanovg/include/nanovg_agg.h  <工程>/src/
# 2) 库进 src/dependencies/lib/（工具链会自动 -L 并打进 update.img）
cp packages/nanovg/lib/v85x/libnanovg.so  <工程>/src/dependencies/lib/libnanovg.so
# 3) 代码里
#    #include "nanovg.h"     #include "nanovg_agg.h"
```

- **别跨平台换库**：`lib/v85x/` 是 **ARMv7 musl**；z20 系是 glibc，装不上。
- 设备侧需有 `libgcc_s.so.1`（本档 `NEEDED`）。
- 调试期 `fun launch` **不推**第三方 `.so` → 手动 `adb push libnanovg.so /tmp/` + `setprop ctl.restart zkswe`（量产走 `src/dependencies/lib/` + `fun pack`）。

最小用法（照 `components/vinyl` 的 backend=1，F133 真机跑过的那条路）：

```cpp
static bitmap_t bmp;                                  // 目标：BGRA / bits=32 / pitch=w*4
NVGcontext* vg = nvgCreateAGG(bmp.width, bmp.height, bmp.pitch, NVG_TEXTURE_BGRA, bmp.data);
if (!vg) { /* 回退到自绘 */ }

nvgBeginFrame(vg, w, h, 1.0f);
nvgTranslate(vg, cx, cy); nvgRotate(vg, angle);       // 想转就转
nvgBeginPath(vg); nvgCircle(vg, 0, 0, r - 0.5f);
nvgFillPaint(vg, nvgImagePattern(vg, -r, -r, 2*r, 2*r, 0.0f, coverTex, 1.0f));
nvgFill(vg); nvgEndFrame(vg);

hostCtrl->setBackgroundBmp(&bmp);                     // 挂一次
hostCtrl->setInvalid(!hostCtrl->isInvalid());         // 之后每帧翻转刷新
```

---

## 3. 坑（踩过才会知道的，按先后顺序）

1. **只支持 `NVG_TEXTURE_BGRA` 目标**（本后端）；`nvgCreateImageRGBA` 会 `Assertion failed: !"not supported format"` → 进程 abort、应用被重启。
2. **贴图格式必须与目标一致**，且源数据按 **BGRA 直传**（不换 R/B）：用 `nvgCreateImageRaw(ctx, w, h, NVG_TEXTURE_BGRA, 0, data)`。
3. **一帧一次 `nvgReinitAgge`**（双缓冲换目标），不要每帧 `nvgCreateAGG`。
4. 软件光栅逐帧成本高：整屏逐帧动画不合适；要小画布 + 降帧。
5. `setBackgroundBmp` **只挂一次**，之后靠 `setInvalid(!isInvalid())` 翻帧。
6. 本档**没有字体/文本 API**（`nvgCreateFont*` / `nvgText*` / `nvgFont*` 都不导出）→ 想画字用 easyui 文本控件或自渲染，别链这些符号。
7. ⛔ **渐变全族不生效（V85X 真机实测，2026-10-03）**：`nvgLinearGradient` / `nvgRadialGradient` /
   `nvgBoxGradient` 全都会退化成**纯 `innerColor`**（4 类 × 4 种调用法 = 12 组全灭）。
   **不是 API 问题**——`nvgLinearGradient` 返回的结构完全符合上游（`extent=[100000,100140] feather=280 radius=0`），
   是**后端光栅器没实现 ramp**（斜率恒为 t=0）。
   → 要渐变：**自己把色带烘成一张贴图**，用 `nvgImagePattern` 1:1 铺上去。
8. ⚠️ **`nvgImagePattern` 不平铺（V85X 实测）**：只画**首个 tile extent**，之外一律透明；
   加不加 `NVG_IMAGE_REPEATX | NVG_IMAGE_REPEATY` **都一样**。
   → 贴图必须**按目标区域大小 1:1 映射**（`components/vinyl` 就是这么用的，所以一直没暴露）。
9. **`lib/v85x/` 这份 `.so` 带 C++ 运行期 UND 符号**（`operator new` / `__cxa_*`）→
   链接方（工程或探针）必须用 **g++** 链，从而依赖设备上的 `libstdc++.so.6`（V85X 固件里有 6.0.22）。

---

## 4. 平台与实测

| 平台 | 关键点 | 状态 |
|---|---|---|
| **V85X** | `lib/v85x/libnanovg.so`（本仓自带，ARMv7 **musl**，GCC 6.4.1） | ✅ **已上真机**（2026-10-03）：功能 12/12、上屏±2 比对 max\|Δ\|=0、**2.48 ms/帧 @320×240**、VmRSS 1668 kB；⛔ 渐变失效 / 贴图不平铺 |
| F133 | 注册表包；vinyl 的 nanovg 后端在 F133 真机跑过（23~44 ms/帧 @320×320） | ✅ 有真机证据（借组件证据） |
| T113EMMC / F136 | 注册表包存在 | ⏳ 未验证 |
| Z20 / Z21 / T113 | **注册表里没有这个包** | ❌ 不可用（别照抄） |

细节与逐条判据 → `platforms.md`；档位凭据（md5 / ELF / 符号）→ `lib/v85x/BUILD.md`。
