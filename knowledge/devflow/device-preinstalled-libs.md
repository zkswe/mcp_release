---
id: devflow-device-preinstalled-libs
title: 设备端已自带的可借用库清单（dlopen 即用 / 免编译）—— 先查这里再决定自己编
category: devflow
status: review
confidence: real-device
verified_at: 2026-09-30
stale_days: 180
origin: partial
source: 2026-09-30 Z21 真机盘点（Zkswe_SSD21X_SPINOR）+ 本机复核（adb ls 体积实测 + 注册表对照 + F133 引自 components/vinyl/platforms.md）
needs_evidence: true
platforms: [Z21, F133]
tags: [libpng 在哪, freetype 有没有, 图片解码用什么, MP3 解码, zlib, dlopen 找不到库, 设备自带, so 清单, 免编译借用, 其中一批, 图形, 解码库, nanovg, libpng12, freetype, libjpeg]
evidence:
  - {cmd: "adb -s <设备>:5555 shell 'ls -l /lib /res/lib'", kind: real-device, note: 2026-09-30 本机复核通过：/lib 80 项；libnanovg.so=50984B、libpng12.so.0.56.0、libfreetype.so.6.11.4=137120B、libjpeg.so.9.1.0=177488B、libmad.so.0.2.1=83224B；/res/lib=libzkgui.so}
  - {cmd: arm-pc-linux-gnueabihf-readelf.exe -d <lib>.so, kind: offline, note: 符号级复核待跑（本机未找到 gnueabihf readelf，需 z21 工具链 bin）}
---
# 设备端已自带的可借用库清单（dlopen 即用 / 免编译）

> **检索导引**：想用的库设备上有没有 / 能不能直接用 / 需不需要自己编译 / nanovg 能用吗 /
> libpng 在哪 / freetype 有没有 / 图片解码用什么 / MP3 解码 / zlib /
> dlopen 找不到库 / 注册表里没有这个包是不是就没有 / 设备自带 .so 清单 / 免编译借用。
>
> **一句话**：**"注册表里没有"≠"平台没有"**—— 设备 `/lib` 里躺着约 80 个库，其中一批
> 图形/解码库（nanovg / libpng12 / freetype / libjpeg / libmad / zlib 等）**可直接 dlopen 或链接**。
> **先查本表，再决定是否自己交叉编译。**
> （另有 `libmi_*` 一整套 —— **框架/系统内部模块，应用不需要关注**，见 §2.2。）

## 1. 判据（先跑这两条命令，别猜）

```bash
# ① 设备上有哪些库（busybox 会由 MCP 工具自动推到 /tmp；Git Bash 下 adb 必须 MSYS_NO_PATHCONV=1）
adb -s <IP>:5555 shell "/tmp/busybox ls -l /lib /res/lib"
# ② 某个 .so 的 ABI / 依赖 / 导出符号（用对应平台工具链的 readelf）
arm-pc-linux-gnueabihf-readelf.exe -d <lib>.so          # Class/Machine/NEEDED/SONAME
arm-pc-linux-gnueabihf-readelf.exe --dyn-syms <lib>.so  # 导出符号（对照头文件核 API）
```
工具链选择按 libc：**V85X/T113 = musl（`arm-unknown-linux-musleabihf-*`）**、
**Z20/Z21 = glibc（`arm-pc-linux-gnueabihf-*`）**、**F133/F135 = RISC-V64 musl**。

## 2. Z21（Zkswe_SSD21X_SPINOR）实测清单 —— 2026-09-30

> 环境：easyui **2.2.0**/ kernel 4.9.84 / **glibc 2.30**（`ld-2.30.so`）；
> 通用库在 `/lib`（80 项），应用库在 `/res/lib`（本例只有 `libzkgui.so`）。
> **体积为本机 adb `ls -l` 复核值**（与实际镜像一致）。

### 2.1 图形 / 图像 / 音频（**最值得借的一批**）

| 库 | 体积（实测） | 能干什么 | 链接属性 |
|---|---|---|---|
| **`libnanovg.so`**| **50,984 B**| **矢量绘制（AGG 后端）**：`nvgCreateAGG`/`nvgDeleteAGG`、`nvgBeginFrame`/`nvgEndFrame`、`nvgScale`、`nvgCreateImageRGBA`、`nvgImagePattern` | ELF32 ARM DYN；NEEDED=`libgcc_s.so.1,libc.so.6`；**无 SONAME**；~100 GLOBAL FUNC（符号级待复核） |
| **`libpng12.so.0.56.0`**| 112 KB 级 | PNG 解码/编码 | SONAME=`libpng12.so.0`；NEEDED=`libz.so.1,libm.so.6,libc.so.6` |
| `libfreetype.so.6.11.4` | **137,120 B**| 字体光栅化（TrueType） | 标准 SONAME 链 |
| `libjpeg.so.9.1.0` | **177,488 B**| JPEG 解码 | — |
| `libz.so.1.2.8` | — | zlib（gzip/inflate） | — |
| `libmad.so.0.2.1` | **83,224 B**| **MP3 解码**| — |

**已验通道（F133 侧，`components/vinyl/platforms.md`）**：`/lib/libnanovg.so` 与注册表包
**同为一份构建（符号逐条相同）**；nanovg 后端 320×320 **23~44ms/帧**（定点后端 6~12ms），
**只支持 `NVG_TEXTURE_BGRA` 目标**。⚠️ **Z21 本轮只做"存在性 + 体积"复核，运行时未验**。

### 2.2 全志 MI 系列（**框架/系统内部使用 —— 应用不需要关注**）

设备 `/lib` 里能看到 `libmi_gfx` / `libmi_disp` / `libmi_rgn` / `libmi_divp` / `libmi_ao` /
`libmi_sys` / `libmi_common` / `libmi_panel` 等一整套 —— **这些是框架与系统自己用的内部模块**
（显示、区域叠加、视频处理、音频输出等）：

- ⛔ **应用层不需要关注、也不要去 dlopen/链接**（接口不对外、随固件变）；
  （2026-09-30：「mi_gfx 不需要用户关注」）
- ✅ 需要图层/合成能力时，走**框架提供的高层 API**（`videoview`/`cameraview`/disp 图层纪律、
  `setBackgroundBmp`+`setInvalid`、`button+picTab` 的 α 路径）——见 `knowledge/devflow/render-extension-boundary.md`。

### 2.3 框架与平台服务

`libeasyui.so`（GUI 引擎）、`libinternalapp.so`、`libzkhardware.so` / `libzkhw.so`（硬件门面）、
`libzkmedia.so`、`libzknet.so`、`libzkupgrade.so`（升级）、`libts.so` / `libtsupdate.so`（触摸校准）、
`libnl-tiny.so`（netlink）、`libiniparser.so`、`libcam_os_wrapper.so`、`libcutils.so`、`liblog.so`。

### 2.4 运行时基础（**决定"能不能借"的那一层**）

`ld-2.30.so` / `libc-2.30.so` / `libstdc++.so.6.0.26` / `libgcc_s.so.1` /
**`libgomp.so.1.0.0`（OpenMP，可做多线程加速）**/ `libssp` / `libpthread` / `libdl` / `librt`。

## 3. 三条使用纪律

1. **注册表没有 ≠ 不能借**：设备 `/lib` 里有 nanovg、libpng12、freetype、libjpeg、libmad、libz 等，
   **走 dlopen（或自带头文件 + 链接设备上的 .so）即可，不必自己交叉编译**。
   ⚠️ **注册表侧的准确现状（2026-09-30 本机实测）**：`~/.fun/registry/public/` 里
   **f133 有 `nanovg/1.0.0`**，**z20 / z21 / v85x / f136 没有**——
即"**部分平台的注册表里有、设备侧也都有**"；别写成"四个平台都没有"。
2. **头文件不在设备上**：设备只装 `.so`，**头文件要从 SDK/参考工程/组件里取**
   （如 `components/vinyl/include/`、registry 包的 `include/`）；
用 `readelf --dyn-syms` 的符号表**逐条对照头文件**确认签名（本仓纪律：不许凭记忆写 API）。
3. **libc 必须匹配**：Z20/Z21=glibc、V85X/T113=musl、F133=RISC-V64 musl；
跨平台复用同一份 `.so` **一定失败**。

## 4. 本文明说的边界（待补）

- Z21 的库目前是**静态验证（存在性 + 体积）**，**符号级与运行时均未验**：升 `verified` 需 ① `readelf --dyn-syms` 对照头文件 ② Z21 上跑一次真实绘制
  （建议直接复用 `components/vinyl` 的 A/B 口径）；
- 本清单是**Z21 单点**盘点：**换板必须重跑 §1 的两条命令**（不同平台库集合不同）。

## 5. 相关文档

- 借开源库的完整落地纪律（libc 匹配 / `src/dependencies/lib/` / strip / maps 核验）：`knowledge/devflow/open-source-stack-integration.md`
- 渲染扩展点与选件（nanovg 在渲染里的角色）：`knowledge/devflow/custom-render-paths.md` ②b、`knowledge/devflow/render-extension-boundary.md`
- F133 侧 nanovg 实证：`components/vinyl/`（含 `components/vinyl/platforms.md`）
