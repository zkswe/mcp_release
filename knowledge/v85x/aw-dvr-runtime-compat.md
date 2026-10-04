---
id: v85x-aw-dvr-runtime-compat
title: 📦 V85X aw-dvr × runtime 兼容速查（版本不是越新越好 + dlopen 失败 SOP）
category: v85x
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [V85X]
tags: [⚠️ 仅内部知识, v85x 深度, 不进 release 公开版]
evidence: []
---
# 📦 V85X aw-dvr × runtime 兼容速查（版本不是越新越好 + dlopen 失败 SOP）

> 2026-09-09 入库（来源：V553 UVC 相机项目实测 2026-09 + 工程 Manifest 注释实证）。
> 适用：**V85X**（V853/V553）用 aw-dvr（`mpi::` 摄像头/录像封装，accessKey 私有包）的工程。
> **检索导引**：问「aw-dvr 版本选哪个 / 4.0.1 装不上 / dlopen 失败 / runtime 不匹配 / 依赖 aw-mpp / 编译过设备跑不起来」→ 本篇。
> ⚠️ 仅内部知识（v85x 深度），不进 release 公开版。

## 0. 一句话

**aw-dvr 必须与设备 runtime（rootfs 里的 aw-mpp）配套，不是版本越新越好**。
V85X 设备 runtime 为 aw-mpp **2.0.2** 时：用 **aw-dvr 3.13.12**（全适配）；**4.0.1 编译能过但设备装不上**（它依赖 aw-mpp 3.0.0-pre2 的专属符号）⇒ **规范：先查兼容矩阵再选版本**（版本兼容链 3.9.12 → 4.0.1 → 3.13.12）。

## 1. 版本 × runtime 兼容矩阵

| aw-dvr 版本 | 配套 aw-mpp | 能否在本设备 runtime（aw-mpp 2.0.2）跑 | 结论 |
|------|------|------|------|
| **3.13.12** | 2.0.2 | ✅ 全适配（UVC 预览/录像/回放正常） | **当前推荐**（MCP v0.27.10 实测环境同款组合） |
| 4.0.1 | 需 3.0.0-pre2 | ❌ 编译过、设备 runtime 装不上（dlopen 失败，引 3.0.0-pre2 专属符号） | 勿用（除非升设备 runtime） |
| 3.9.12 | 旧配套 | ⚠️ 能跑但不能录 UVC（V553 试错链中间版，待复核细节） | 不推荐 |

配套事实（V553 Manifest 注释实证）：
- **aw-mpp 由 aw-dvr 传递依赖自动带入**（含全部 MPP 头文件+库），Manifest 不用显式加 aw-mpp
- **勿加 aw-middleware**：旧包头文件冲突 + 无 UVC backend（aws-dvr 3.13.12 时代已不需要）
- `libmpp_uvc.so` 由 **aw-mpp-uvc** 包提供（UVC 摄像头通路依赖）
- 当前 registry 实测组合：aw-dvr 3.13.12 + aw-mpp 2.0.2 + aw-mpp-uvc 1.0.0

## 2. 版本选择规则（修正旧策略）

1. 新工程默认 **aw-dvr 3.13.12**（配 runtime aw-mpp 2.0.2）——不是"拉最新版"
2. 想换版本先问：新版本要求的 aw-mpp 版本 = 设备 runtime 版本吗？
   - 查包依赖：registry 包描述/`fun install` 输出/Manifest 注释
   - 拿不准就用当前实测组合，别试错
3. 同套 SDK 源码工程的 `Manifest.xml`/`.deps.lock` 注释常有版本适配结论（V553 的 Manifest 就写了完整避坑注释），先看再选

## 3. dlopen 失败标准排查 SOP（设备报装不上/启动崩）

现象：`fun launch` 后程序起不来，logcat 报 dlopen 失败（`cannot open shared object` / undefined symbol），或 `AW_MPI_*` 调用异常。

排查步骤（readelf 三连）：

```bash
# ① 看目标库的 NEEDED 依赖列表（缺哪个 .so / 版本要求）
readelf -d <libaw-dvr.so 或报错库> | grep NEEDED

# ② 比对设备上实际存在的库版本（runtime 装的是哪个 aw-mpp）
#    设备：ls /usr/lib/libmpp* /lib/libmpp*（或 adb shell）
#    本机 registry 对照：C:\zkswe\fun\registry\public\v85x\aw-mpp\<版本>\lib\

# ③ 找 UND 未定义符号，判断是否引用版本专属符号（根因定位）
readelf -Ws <库> | grep UND
#    与设备库已导出符号比对（readelf -Ws <设备 .so> | grep <符号>）
#    命中"目标 runtime 版本里不存在"的符号 = SDK 版本与 runtime 不匹配
```

V553 实证案例：aw-dvr 4.0.1 装不上 = 引用了 3 个 aw-mpp 3.0.0-pre2 专属符号（2.0.2 runtime 没有）→ 结论：降回 3.13.12（与 2.0.2 配套），而不是升 runtime。

结论二选一：
- **换 SDK 版本**：选与设备 runtime 配套的 aw-dvr（默认 3.13.12）
- **升 runtime**：整机 rootfs 的 aw-mpp 升到新版本要求的（如 3.0.0-pre2）——影响面大，先确认固件支持

## 4. 参考
- `knowledge/v85x/dvr-recorder-guide.md` §2（Manifest 依赖 + 版本策略已按本表修正）
- MCP v0.27.10+ 实测环境：aw-dvr 3.13.12 + aw-mpp 2.0.2（UVC JPEG 全链路验证）
