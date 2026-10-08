# libblend2d.so 构建信息（components/blend2d 两个库档）

构建/取证日期：**2026-10-01**（来源：`temp/blend2d_neon/REPORT.md` + `temp/blend2d_neon/evidence/`，本章数字与证据逐条对得上）
自检脚本：`python components/blend2d/scripts/verify_libs.py`（重跑 ELF 属性 / 符号数 / NEON 命中，见 §6）

---

## 0. 两个库档（取哪个？）

| 档位 | 路径 | 来源 | 大小 | md5 | 何时用 |
|---|---|---|---|---|---|
| **原厂档**（默认，推荐起点） | `lib/z20/libblend2d.so` | 官方依赖包注册表 `blend2d 0.11.1`（**仅 z20**），`https://package.flythings.cn/packages/z20/blend2d/0.11.1.zip`（zip 806,553 B） | **1,472,816 B** | `E07458D82437872D160C164106B529D4` | 保兼容、保可复现、省 116 KB 固件；渲染能力完全一样（逐字节相同） |
| **性能档**（NEON 自编） | `lib/z20-neon/libblend2d.so` | 我们自己按 commit 锁源码重编（§2） | **1,874,056 B（+27.2%）** | `C1E9DCCE2D1ACCC28EB46BB60F39CF72` | 想要那 15~18% 的真实提速时；换库**零代码改动**（ABI 全等） |

> ⚠️ **两档渲染产物逐字节相同**（5 个产件 md5 全等，含 800×1280 与 alpha 探针帧）。
> ⚠️ **别指望它救场**：480×480 全屏 28.0 → 23.7 ms（−15.3%）、800×1280 109.4 → 89.7 ms（−18.0%）；
> 把 480×480 真正打进 5.17 ms（−78.2%）的是 **`threadCount=2` + 阴影 8→2 层**这两条**零成本配方**。
> → 默认就用原厂档；**先做配方优化，再决定要不要换成 NEON 档**。

---

## 1. 版本 = commit 锁定（上游无 tag，必须写死）

| 项 | 结论 |
|---|---|
| 上游 tag | **完全没有**（`git ls-remote --tags` 空；`refs/tags/0.11.1` 404 是真实不存在，已用不存在的 tag 对照验证） |
| 0.11.1 对应 commit | **`a7f9476`**（2024-05-31）—— 判据：加它的 commit 里 `src/blend2d/api.h` 有 `BL_MAKE_VERSION(0, 11, 1)`，下一个 commit `b6fb6c2` 才升到 0.11.2 |
| 取源镜像 | **gitee 镜像** `https://gitee.com/mirrors/blend2d.git`（GitHub 直连不稳，ghfast.top 亦可） |
| `master` 能不能用 | **不能**：`master` 已是 `BL_VERSION 0.21.3`，与注册表 0.11.1 不对版 |
| 运行期自证 | 重编后 `blRuntimeQueryInfo(BUILD)` 报 `ver=0.11.1 buildType=1(RELEASE) cpuArch=0x2(AArch64)`（⚠️ 语义更正：`0x2` = AArch64，**ARM 是 `0x1`**；本档实测 `supportedCpuFeatures=0x00000000`，正对「ARM32 走 C++ 参考管线、无 SIMD 路径」），与注册表包一致（旧库 `compiler=GCC 8.2`，新库 `GCC 8.3`） |
| asmjit | **不需要**（`-DBLEND2D_NO_JIT=ON` 后 CMake 跳过 asmjit 查找） |

---

## 2. 性能档（NEON）完整构建口径

**工具链**：`C:\zkswe\fsc\toolchains\z21\bin\arm-pc-linux-gnueabihf-{gcc,g++}.exe`（**8.3.0**，Windows PE）→ 经 WSL 包装器驱动
（沿用 `tools/e2fsprogs/build/toolchain/z21-gcc` 的做法：补 `-B`、`--sysroot`、`/mnt/*`→Windows 路径翻译、互操作故障自动重试）。

**包装器必须补的三条 `-isystem`**（否则 CMake 的 C++ 编译直接报 `cmath: No such file or directory`——
`--sysroot` 让驱动丢掉了内建 C++ 头搜索路径）：
```
-isystem <Z>/arm-pc-linux-gnueabihf/include/c++/8.3.0
-isystem <Z>/arm-pc-linux-gnueabihf/include/c++/8.3.0/arm-pc-linux-gnueabihf
-isystem <Z>/arm-pc-linux-gnueabihf/include/c++/8.3.0/backward
```
（另需 `-isystem <Z>/lib/gcc/arm-pc-linux-gnueabihf/8.3.0/include` 与 `.../include-fixed`；`Z=C:\zkswe\fsc\toolchains\z21`）

**CMake 命令（原文）**
```bash
cmake -G Ninja -S src_0111 -B build_o2 \
  -DCMAKE_TOOLCHAIN_FILE=<repo>/toolchain/z20-toolchain.cmake \
  -DCMAKE_BUILD_TYPE=Release -DBLEND2D_NO_JIT=ON -DBLEND2D_STATIC=OFF \
  -DBLEND2D_NO_STDCXX=0 -DBLEND2D_TEST=OFF -DBLEND2D_NO_INSTALL=ON \
  -DCMAKE_C_FLAGS='-march=armv7-a -mfpu=neon -mfloat-abi=hard' \
  -DCMAKE_CXX_FLAGS='-march=armv7-a -mfpu=neon -mfloat-abi=hard' \
  -DCMAKE_C_FLAGS_RELEASE='-O2 -DNDEBUG' -DCMAKE_CXX_FLAGS_RELEASE='-O2 -DNDEBUG'
ninja -j8      # 160 个目标，real 36.8 s
```
- **必须显式 `-march=armv7-a`**：该工具链默认 CPU 是 **armv5te**（`Tag_CPU_name "5TE"`），不给就编出 v5 代码；原厂库属性是 `7-A/v7`。
- `-DBLEND2D_NO_STDCXX=0`：原厂库 `NEEDED` 含 `libstdc++.so.6`（发布方没开 NO_STDCXX），为对齐而显式关掉。
- blend2d 自己追加：`-DBL_BUILD_OPT_ASIMD`、`-DBL_BUILD_NO_JIT`、`-ftree-vectorize`、`-fno-exceptions -fno-rtti -fno-finite-math-only`（**没被 `-ffast-math` 污染**，符合官方红线）。
- 一键脚本：`scripts/build-neon.sh`（含上面全部命令与三条 `-isystem` 说明）。

---

## 3. ABI / ELF 属性（两档对比，结论：可直接换库）

| 指标 | 原厂 `lib/z20` | 自编 `lib/z20-neon` |
|---|---|---|
| 文件体积 | 1,472,816 B | **1,874,056 B（+27.2%）** |
| `.comment` | `GCC 8.2.1 (arm-rel-8.23)` | `GCC 8.3.0 (GNU Toolchain for the A-profile)` |
| ELF 属性 | `CPU "7-A" / v7 / VFPv4 / NEONv1 with Fused-MAC` | **完全一致** |
| **动态导出符号（defined）** | **787（含 777 个 `bl*` FUNC + 2 个 `bl*` 数据对象）** | **787（同上）→ 差集为空** |
| `NEEDED` | libstdc++ / libm / libdl / libc / ld-linux-armhf / libpthread | 同上 **+ `libgcc_s.so.1`**（⚠️ 见 §5） |
| 反汇编指令条数 | 347,497 | 390,667 |
| **`q` 寄存器命中（NEON 128bit 数据通路）** | **0** | **17,364** |
| `vld1` / `vst1` / `vmul` / `vmla` | 0 / 0 / 0 / 0 | **905 / 2,126 / 4,036 / 3,432** |
| JIT 痕迹（`asmjit/JIT/AArch64/SSE2`） | 0 | 0（`NO_JIT` 生效） |

> ABI 判定：**符号集合完全等价** ⇒ 0.11.1 既有调用方不改一行，直接换 `.so` 即可（真机也是这么验的：App 二进制未重编，只换库就跑通）。
>
> **符号口径**：`readelf --dyn-syms --wide` 数 **defined = 787**（原报告写的 "787（含 777 个 bl*）" 是 **`bl*` FUNC** 的口径；另有 2 个 `bl*` **数据对象** —— `blDefaultApproximationOptions`、`blFormatInfo`，合起来 `bl*` 名字共 779 个）。两个库档这三种数法都完全一致。
>
> **NEON 命中口径**：`scripts/verify_libs.py` 的 `q` 计数是**操作数出现次数**（近似，NEON 档 29,841），原报告 17,364 是**按指令条数**统计 —— 两者判据相同：**原厂档 0，NEON 档 ≫0**（另有 `vld1 905 / vst1 2126` 只有 NEON 档才有，这才是硬判据）。
>
> NEON 来源（如实）：0.11.1 的 ARM32 里**显式** SIMD 只有 TrueType 字形解码一路（`otglyf_asimd.cpp`，由 `__ARM_NEON__`→`BL_BUILD_OPT_ASIMD` 打开）；其余 1.7 万处 `q` 命中来自 **GCC 自动向量化**（Release flag 自带 `-ftree-vectorize`，只有有 NEON 时才生成 NEON 指令）。**未做**"同参数 `-mfpu=vfp`"对照编译，故不能把收益在"显式 ASIMD"与"自动向量化"之间精确拆账 —— 两者同源，都靠 `-mfpu=neon` 才存在。

---

## 4. 真机实测（性能档 vs 原厂档，Z20 480×480 / 800×1280）

单位 ms/帧，「完整绘制 + `ctx.flush(SYNC)`」（**不含上屏 blit**）；原始日志 → `temp/blend2d_neon/evidence/b2d_log_{OLD,NEON}.txt`。

| 用例 | 原厂 | NEON | 变化 |
|---|---|---|---|
| 480×480 同步 | 28.005 | 23.707 | **−15.3%** |
| 480×480 + `threadCount=2` | 14.154 | 12.222 | −13.6% |
| 800×1280 同步 | 109.439 | 89.696 | **−18.0%** |
| 480×480 阴影 8→2 层 | 10.442 | 9.170 | −12.2% |
| 480×480 阴影 2 层 + `t=2` | 5.693 | **5.171** | −9.2%（**vs 本库基线 −78.2%**） |
| 分项：`fillAll` 纯填充 | 0.706 | 0.331 | **−53.1%** |
| 分项：+8 层阴影 | 25.164 | 20.966 | **−16.7%（−4.20 ms，绝对收益最大）** |
| 分项：+三行文本 | 28.102 | 23.744 | 文本段自身 **2.44→2.62 ms，未见加速**（ARM32 无 JIT，路径/字形几何向量化不了） |

**结论：NEON 收益集中在"大面积逐像素 / 填充 / alpha 混合"；对路径几何、扫描线求交、字形轮廓几乎无感。**

**固件体积账**（`update.img`，同基线 647,720 B）：
```
无 blend2d                        647,720 B
原厂 .so 进镜像                  1,143,336 B   → +495,616 B
NEON  .so 进镜像（实测产物）      1,262,120 B   → +614,400 B（比原厂多 +118,784 B ≈ 116 KB）
```
> Z20 `res` 分区上限 **7,470,080 B**（`update.img` 上限），出包前先看余量。

---

## 5. ⚠️ 性能档新增依赖：`libgcc_s.so.1`

自编 NEON 版 `NEEDED` 比原厂**多一项 `libgcc_s.so.1`**（证据：`evidence/neon_hits_NEON.txt` 的 `NEEDED` 列表；原厂档没有）。

- **Z20 真机有**（本轮实测跑通，无 `initLib error`）；
- **换平台前先确认设备存在 `libgcc_s.so.1`**（`ls /lib/libgcc_s.so.1`）；缺则用原厂档，或把该库一并放进 `src/dependencies/lib/`。
- 其余依赖与原厂一致：`libstdc++.so.6 / libm / libdl / libc / ld-linux-armhf.so.3 / libpthread`。

---

## 6. 自检（拿到库先跑一次）

```bash
python components/blend2d/scripts/verify_libs.py            # 全检（含 NEON 反汇编统计，约 30~60 s）
python components/blend2d/scripts/verify_libs.py --fast     # 只查 ELF 属性 + 符号集合（秒级）
```
判据（脚本自动比对，输出 PASS/FAIL）：
- 两档 md5/体积 = 表中值；
- 两档 **defined 动态符号集合完全相等**（787/787，`bl*` 777/777）；
- 两档 ELF 属性都是 `7-A / v7 / VFPv4 / NEONv1 with Fused-MAC`；
- **原厂档 `q` 命中 = 0，NEON 档 `q` 命中 > 0**；
- NEON 档 `NEEDED` 含 `libgcc_s.so.1`，原厂档不含。

> 脚本用厂家工具链自带的 `arm-pc-linux-gnueabihf-readelf/objdump.exe`（自动探测 `C:\zkswe\fsc\toolchains\z2{0,1}\bin`，找不到就报"缺工具"并只做能做的项）。
> 纯 Python 解析 ELF 的部分**不依赖 nm**（Windows 版 nm 缺 `liblto_plugin-0.dll` 会直接报错）。

---

## 7. 复现索引（证据在哪）

| 路径 | 内容 |
|---|---|
| `temp/blend2d_neon/REPORT.md` | 全量复测报告（取源/重编/NEON 验证/真机三组数/效果/部署/收尾） |
| `temp/blend2d_neon/build_o2/libblend2d.so` | **NEON 档产物**（= 本目录 `lib/z20-neon/`，md5 一致） |
| `temp/blend2d_neon/libblend2d.orig.so` | 原厂档副本（= 本目录 `lib/z20/`，md5 一致） |
| `temp/blend2d_neon/src_0111/` | 0.11.1 源码树（git worktree @ `a7f9476`） |
| `temp/blend2d_neon/toolchain/{z21-gcc,z21-g++,z20-toolchain.cmake}` | WSL 包装器（含 C++ 头修复）+ CMake 工具链文件 |
| `temp/blend2d_neon/evidence/` | 反汇编命中统计、符号对比、cmake flag 原文、两侧真机日志、渲染产件 md5 |
| `temp/blend2d_neon/upd_neon.img` | 含 NEON `.so` 的 `update.img`（1,262,120 B） |
| `temp/b2d_dev/` | 上一轮「原厂库真机基线」工程与证据（`B2dBenchZ20/`、`evidence/`） |
| `references/kb/blend2d-z20-assessment.md` | 可用性评估（包取证/能力缺口/平台矩阵/未取证清单） |

---

## 7. 第三档：lib/v85x/（V85X = ARMv7 musl，**本仓自编**，2026-10-03）

> 需求（2026-10-03）：把 blend2d 编译一个 V85X 对应的版本放进 MCP。
> 完整凭据：lib/v85x/BUILD.md；本档**与 z20 两档不同 ABI**（musl vs glibc），跨平台换库一定失败。

| 档位 | 路径 | 来源 | 大小 | md5 |
|---|---|---|---|---|
| **v85x** | lib/v85x/libblend2d.so | **自编**：0.11.1 @ 7f9476 + V85X musl 工具链（Linaro GCC 6.4.1） | **1,846,636 B** | ED1569D41A8AD6346BED0D3FF6182D7C |

- 构建开关：-DBLEND2D_NO_JIT=ON（ARM32 无 JIT） / -DBLEND2D_STATIC=OFF / -DBLEND2D_NO_STDCXX=0
- ELF：ELF32 ARM EABI5 DYN；.comment = Linaro GCC 6.4.1；Tag_CPU 7-A / v7 / VFPv4 / NEONv1
- NEEDED：libstdc++.so.6 / libc.so / libgcc_s.so.1（musl 口径）
- 状态：✅ 编译+链接通过 ｜ ⚠️ **未上真机**（V85X 样机未接入，无上屏/性能/逐像素证据）
