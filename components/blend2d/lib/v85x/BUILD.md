# libblend2d.so · v85x 档（本仓自编）

> 平台：**V85X**（Allwinner V85x / ARMv7-A **musl**，easyui 2.4.0 板实测平台）
> 日期：2026-10-03 ｜ 需求：把 blend2d 编译一个 V85X（ARMv7 musl）对应的版本并入 MCP。

## 1. 档位信息

| 项 | 值 |
|---|---|
| 路径 | `components/blend2d/lib/v85x/libblend2d.so` |
| 体积 | **1,846,636 B** |
| md5 | `ED1569D41A8AD6346BED0D3FF6182D7C` |
| 来源 | **本仓自编**（源码 = blend2d 0.11.1，commit **`a7f9476`**，与 `lib/z20` 档同源同 commit） |
| 开关 | `-DBLEND2D_NO_JIT=ON`（ARM32 无 JIT，走 C++ 参考管线）<br>`-DBLEND2D_STATIC=OFF`、`-DBLEND2D_NO_STDCXX=0`、`-DBLEND2D_TEST=OFF`、`-DBLEND2D_NO_INSTALL=ON` |

## 2. 工具链与构建命令（可复现）

- 工具链：`C:\zkswe\fun\toolchains\v85x`（`arm-unknown-linux-musleabihf-{gcc,g++}` **Linaro GCC 6.4.1**）
  —— 与 IDE 自带 `tools/FlyThingsIDE/sdk/toolchains/v85x` 同源。
- 主机工具：cmake **4.3.3** + ninja **1.13.2**（**直接在 Windows 上用 PE 工具链构建**，
  不需要 z20 那套 WSL 包装器 —— 没有路径翻译问题）。

```bat
cmake -G Ninja -S <blend2d 0.11.1 src> -B build ^
  -DCMAKE_TOOLCHAIN_FILE=<v85x-musl-toolchain.cmake> ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DBLEND2D_NO_JIT=ON -DBLEND2D_STATIC=OFF -DBLEND2D_NO_STDCXX=0 ^
  -DBLEND2D_TEST=OFF -DBLEND2D_NO_INSTALL=ON -DBLEND2D_NO_NATVIS=ON
cmake --build build --parallel 8        :: 160/160 → libblend2d.so
```

- `CMAKE_TOOLCHAIN_FILE` 三要素：`CMAKE_SYSROOT = <tc>/arm-unknown-linux-musleabihf/sysroot`；
  `CMAKE_C/CXX_FLAGS_INIT = -march=armv7-a -mfpu=neon -mfloat-abi=hard`（**必须显式给 `-march=armv7-a`**，
  否则该工具链默认出 armv5te 代码）。
- 本次构建目录：`temp/b2d_v85x/`（脚本 `configure.bat` + `v85x-musl-toolchain.cmake`）。

## 3. 产物核对（机器读数）

```
ELF32, ARM, EABI5, DYN (Shared object)
Attr  : Tag_CPU_name "7-A" / Tag_CPU_arch v7 / Tag_FP_arch VFPv4 / NEONv1 with Fused-MAC
.comment: GCC: (Linaro GCC 6.4-2017.11) 6.4.1 20171012
NEEDED : libstdc++.so.6 / libc.so / libgcc_s.so.1
SONAME : libblend2d.so
dynsym : 868 条
```

## 4. 平台口径（未做/待验，**别当已验证用**）

- ✅ **编译 + 链接通过**（工具链实测）——V85X 的 musl ABI 与 `NEEDED` 口径成立。
- ⚠️ **未上真机**：V85X 样机（`Zkswe_V85X_SPINOR`，USB `20080411`）本轮**未接入**，
  故：没有跑通上屏、没有 `VmRSS`/性能读数、没有与 `savePng` 的逐像素比对。
  按本仓纪律，**未实测就是不写「可用」**。
- ⚠️ 首次真机使用前确认设备侧有 `libstdc++.so.6`（musl 工具链同源自带；与 z20 档的 `libgcc_s.so.1` 依赖不同）。
- 与 `lib/z20*` 两档**不是同一 ABI**：z20 系列是 glibc，跨平台换库一定失败。

## 5. 相关

- 同组件另两档构建凭据：`lib/BUILD_INFO.md`
- 平台矩阵：`platforms.md`
- V85X 侧依赖包现状（**registry 无 blend2d 包**，故只能走 `src/dependencies/lib/` + `fun pack` 手投）：
  `platforms.md` §3
