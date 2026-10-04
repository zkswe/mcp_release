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

## 4. 平台口径（V85X 已真机验证，2026-10-05）

- ✅ **编译 + 链接通过**（工具链实测）——V85X 的 musl ABI 与 `NEEDED` 口径成立。
- ✅ **已上真机**（2026-10-05，`Zkswe_V85X_SPINOR` / USB `20080411`）：
  · 组件门面 `zk::b2d::Canvas` 跑通：480×480 全帧 **avg 5.010 ms/帧**（min 4.002 / max 7.968，≈199.6 fps）、
    800×1280 **avg 7.862 ms/帧**（≈127.2 fps）；`VmRSS` 2856→3504 kB / 6776 kB，未 OOM；
  · `savePng` 真落盘（9066 B，签名 `89504E47…`）并拉回目检：圆角/抗锯齿/渐变/阴影四件都正确；`close()` 干净。
- ⚠️ 本档**没有 strip**（`.symtab` 仍在，`[26] .symtab SYMTAB`）；`dynsym` 865 条。
- ⚠️ **随仓可复现的是「链接 + 真机运行」**：`blend2d.h` 不在仓、不在 registry，本次用官方 0.11.1（commit `a7f9476`，与 `lib/BUILD_INFO.md` 记录同 commit）真头编译。
- ⚠️ 首次真机使用前确认设备侧有 `libstdc++.so.6`（musl 工具链同源自带；与 z20 档的 `libgcc_s.so.1` 依赖不同）。
- 与 `lib/z20*` 两档**不是同一 ABI**：z20 系列是 glibc，跨平台换库一定失败。

## 5. 相关

- 同组件另两档构建凭据：`lib/BUILD_INFO.md`
- 平台矩阵：`platforms.md`
- V85X 侧依赖包现状（**registry 无 blend2d 包**，故只能走 `src/dependencies/lib/` + `fun pack` 手投）：
  `platforms.md` §3
