# libnanovg.so · v85x 档（V85X 设备侧，随仓自带）

> **来源**：需求方 2026-10-03 19:41 经企业微信提供（文件名 `nanovg_dev.so`），说明「**这个是 V85X 设备里面的，但是缺少了头文件**」。
> **本次动作**：把这支 `.so` 入仓，并**补齐头文件**（`include/nanovg.h` + `include/nanovg_agg.h`，
> 取自 f133 注册表包——上游同一份头，符号已逐条核对，见 §3）。
> ⚠️ 这是**厂家构建**，不是我们重编的；本仓只做入库 + 核对 + 文档。

## 1. 档位信息

| 项 | 值 |
|---|---|
| 路径 | `packages/nanovg/lib/v85x/libnanovg.so` |
| 体积 | **47,552 B** |
| md5 | `F5F1157D50AB4A882B464D33804E5B1B` |
| 编译器 | `.comment` = `GCC: (OpenWrt/Linaro GCC 6.4-2017.11 2017-11) 6.4.1`（与 V85X 工具链同源） |
| 已 strip | ✅ 无 `.symtab`、无 `.debug`（节表只有 `.gnu.hash/.dynsym/…/.comment/.ARM.attributes`） |

## 2. ELF 读数（用 V85X 工具链 readelf 实测）

```
Class/Machine : ELF32 / ARM（DYN, Shared object）
Attr          : Tag_CPU_name "7-A" / Tag_CPU_arch v7 / Tag_FP_arch VFPv3 / Tag_Advanced_SIMD_arch NEONv1
NEEDED        : libgcc_s.so.1, libc.so          ← libc.so = musl，与 V85X 口径一致
SONAME        : （无）
dynsym        : 193 条（defined 155 / UND 35）
UND 里只有 libc/libgcc 的常规符号：malloc/free/memcpy/sqrtf/sincosf/fmodf… 与 C++ 运行期
                （__cxa_*、_Znaj、__gxx_personality_v0）—— 没有别的第三方依赖
```

## 3. 符号审计：头文件 ↔ 本档（可复现）

判据：`include/nanovg.h` + `include/nanovg_agg.h` 声明了什么、`.so` 导出什么。

| 项 | 结果 |
|---|---|
| 头文件声明的 `nvg*` 函数 | **105** |
| 本档导出的 `nvg*` | **85** |
| 库里有、头文件没声明（脏导出） | **0** |
| 与 f133 注册表包的 `nvg*` 集合 | **完全相同**（85 = 85，逐条相等） |
| 后端三件套 | ✅ `nvgCreateAGG` / `nvgReinitAgge` / `nvgDeleteAGG` 都在 |
| `nvgCreateImageRaw` / `nvgImagePattern` / `nvgUpdateImage` | ✅ 都在（`components/vinyl` 用的就是这三个） |

## 4. ⚠️ 已知缺口：**头里声明了、库里没有**（20 条，全是字体/文本一脉）

```
nvgAddFallbackFont  nvgAddFallbackFontId  nvgCreateFont    nvgCreateFontMem
nvgFindFont         nvgDebugDumpPathCache  nvgFontBlur      nvgFontFace
nvgFontFaceId       nvgFontSize           nvgFontFaceId 处的其余同族（nvgText*/nvgTextBounds/
nvgTextBox/nvgTextBreakLines/nvgTextMetrics/nvgTextLineHeight/nvgTextLetterSpacing/…）
```

- 换句话说：**这份构建没编 fontstash**，只有路径 / 图像 / 渐变 / 变换 / 合成。
- 影响：任何 `nvgCreateFont*` / `nvgText*` / `nvgFont*` 调用**链接期就会缺符号**（不是运行时才炸）。
- 想画字：用 easyui 文本控件，或自己把字形烘成贴图后用 `nvgImagePattern` 贴。
- 注意 f133 注册表包**也一样**（同为 85 条）——这不是 V85X 特有的裁剪。

## 5. 未做 / 待办

1. ~~**未上真机**~~ → ✅ **已补**（2026-10-03）：`../../evidence/v85x-device/`
   有上屏截图、±2 逐像素比对（max|Δ|=0）、帧耗时（2.48 ms/帧 @320×240）与 `VmRSS`（1668 kB）。
   真机同时暴露两处：**渐变族失效**、**贴图不平铺**（见 `../../platforms.md §1.4`）。
2. 头文件来源是 **f133 包**（同一上游）；若厂家另有一份配套头（例如只声明 85 条的裁剪版），应替换并重跑 §3。
3. ~~设备侧运行期依赖 `libgcc_s.so.1` 需确认~~ → ✅ **已查**：V85X 固件 `/lib/libgcc_s.so.1`（39,332 B）在；
   另发现 `.so` 有 C++ 运行期 UND 符号，设备侧 `/lib/libstdc++.so.6.0.22` 也在，
   但**链接方须用 g++**（否则 `operator new` 等解不开）。

## 6. 复现命令（照抄可跑）

```powershell
$re = "C:\zkswe\fsc\toolchains\v85x\bin\arm-unknown-linux-musleabihf-readelf.exe"
& $re -h   packages\nanovg\lib\v85x\libnanovg.so        # 类/机器/类型
& $re -A   packages\nanovg\lib\v85x\libnanovg.so        # ARM 属性（7-A / v7 / VFPv3 / NEONv1）
& $re -d   packages\nanovg\lib\v85x\libnanovg.so        # NEEDED
& $re --dyn-syms --wide packages\nanovg\lib\v85x\libnanovg.so | Select-String nvg   # 85 条
python temp\nvg_audit.py                                # 头文件 ↔ .so 符号审计（105 vs 85）
```
