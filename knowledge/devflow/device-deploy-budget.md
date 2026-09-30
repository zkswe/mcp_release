---
id: devflow-device-deploy-budget
title: 设备部署体积与内存预算（小内存设备必看）
category: devflow
status: verified
confidence: real-device
verified_at: 2026-09-29
machine_verified_at: "2026-09-29 20:45:45"
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: false
platforms: [Z21]
tags: [表现像, WiFi 坏了, Z20, 部署体积, 内存预算, OOM 杀 zkgui, 设备重启, 整板掉网, 重启应用进程, setprop ctl, restart zkswe, init 托管, 不能 kill 程序, 温和终止, kill -TERM, kill -9]
evidence:
  - {kind: real-device, cmd: %ADB% -s %DEVICE% shell getprop init.svc.zkswe, expect_contains: running, ran_at: "2026-09-29 20:45:45"}
  - {kind: offline, cmd: python -m unittest tests.test_baseline_testrun.TestTouchFallback -q, expect_rc: 0, expect_contains: OK, ran_at: "2026-09-29 20:45:45", output_sha256: 2a50b4749107e50e3993c9a59df48e8d8cebd81e26a286e83bb83d7fe81b2d90}
---
# 设备部署体积与内存预算（小内存设备必看）

> 检索导引：问「部署后设备 OOM 重启 / 整板掉网像 WiFi 坏了 / /tmp 太小 / 部署体积怎么压 / 应用进程怎么重启（为什么不能 kill）」→ 本文（小内存板必读）。
> 实测来源：Z21（`Zkswe_SSD21X_SPINOR`）2026-09-16 —— 曾因部署体积把设备搞到 OOM 反复重启，表现像「WiFi 坏了」。
> 适用：**内存 ≤ 64MB 的真机**（Z20/Z21 这类 SigmaStar 板子尤甚）。
> 检索词：部署体积 / 内存预算 / OOM 杀 zkgui / 设备重启 / 整板掉网 / 重启应用进程 /
> setprop ctl.restart zkswe / init 托管 / 不能 kill 程序 / 温和终止 / kill -TERM / kill -9。

## 1. 先量三个数

```bash
adb shell "free; df -h /tmp; /tmp/busybox du -sk /tmp/* | sort -n"
```

Z21 实测：`Mem total 36072 kB`（**36MB**）；`/tmp` = **tmpfs 13.6MB**（tmpfs 占的是 RAM，不是磁盘！）。

## 2. 铁律：`fun launch` 的产物全部落在 /tmp（= 吃内存）

一次 `fun launch` 至少推：`/tmp/lib/libzkgui.so` + `/tmp/font/font.ttf` + `/tmp/ui/main.ftu` + `/tmp/EasyUI.cfg`。
**字库是最大头**（思源黑体常用字 872KB，全量版 7.5MB / 多语言 10.7MB）——加上 tmpfs 里已有的调试工具（busybox 1.9MB 等），
很容易把可用内存压到几百 KB → **OOM killer 杀 `zkgui` → 设备重启**。

**症状对照**：内核日志出现
`Out of memory: Kill process <pid> (zkgui_ui) score ... ` + `oom_reaper: reaped process ...`，
重启后 `/tmp` 全空（连 `EasyUI.cfg` 都没了）→ UI 回到出厂页（看起来"程序没生效"）。

## 3. 处置顺序（按性价比）

1. **清 tmpfs 垃圾**：重复的 busybox、旧工程的 `ui/images`、`ui/fonts`、用不到的 `.ftu`。
2. **字库按工程实际用字裁剪**（最有效，872KB → 数十 KB）：
   ```bash
   python tools/ui_tools/font_subset_by_project.py <项目根> \
       [--src tools/FlyThings_mcp_open/components/fonts/fonts/zkswe-hans-full.ttf]
   ```
   - 默认源 = `zkswe-hans-common.ttf`（GB2312 一级字）→ **只含一级字**，像「阈」这种二级字会缺字形（界面少一笔）。
   - 需要覆盖更多字（如「阈」）时用 `--src` 指到 `zkswe-hans-full.ttf`（7.4MB 源，产出仍只有几十 KB）。
   - ⚠️ **改完 UI 文案要重跑**：新增的字若不在字库里会**静默缺字**（例如按钮「系统 WiFi 设置」少了个「系」）。
3. 部署完复量：`free` 里 `available` 应回到 **10MB+**（Z21 清理后 17MB）。
4. 长期方案：`update.img` 固化（程序进只读分区），不再吃 tmpfs。

## 4. 两条部署侧坑

- `adb push` **不带执行位** → 推完必须 `chmod 777 /tmp/xxx`（否则 `can't execute: Permission denied`）。
- 设备**重启会清空 /tmp**（含 `EasyUI.cfg`）→ 必须用 `fun launch` **整套**重新部署；
  **只 push 单个文件会跑出厂 UI**（缺 `EasyUI.cfg` 时 zkgui 走默认资源路径，现象是"我的界面没出现"）。
- `fun launch` 偶发 `FATAL read tcp 127.0.0.1:5037 i/o timeout` / `device offline`：重连（`adb connect <ip>:5555`）后重试即可，
  压测类程序反复断电 WiFi 时网络 adb 必然抖。

## 5. 重启应用进程：走 setprop 让 init 控制（**不要 kill**）

**口径（2026-09-28 钟工定，替代 2026-09-17 的「温和终止优先」）**：

- **框架设计是类 init 服务**：应用（`/etc/init.rc`：`service zkswe /bin/zkgui`）由 init 托管，
  **不能 kill 程序**；控制程序的唯一姿势是 **`setprop ctl.restart zkswe`**（init 回收 → 重新拉起）。
- **厂商 CLI 也是这么做的**：`fun launch` 二进制里只用到 `ctl.restart` + `zkswe` + `setprop`（**没有 kill**）；
  手动部署（推 `/tmp` + `/tmp/EasyUI.cfg`）之后同样一句 `setprop ctl.restart zkswe` 让新 lib/ftu 生效
  （实测新进程确实加载 `/tmp` 的 lib，`/proc/<pid>/maps` 可见）。
  按框架口径，**任何 kill 都不该用**，统一 setprop。
- **实现（单一来源）**：MCP 侧 `adb_tools.restart_app()` = `setprop ctl.restart zkswe` → 轮询等新 pid（约 6s）；
  `allow_kill=True` 才启用 `kill -TERM` 兜底（给个别 setprop 失效的老板子留口子，仍然不用 -9）。
  返回体带 `oldPid/newPid/method/restarted`，可取证用了哪条、pid 是否真换了。
- **实测验收（2026-09-28，Z20 `192.168.1.100`，480×480）**：`setprop ctl.restart zkswe` **连续 10 轮** ——
  每轮 pid 都换新（1233→…→2332，每轮 ~0.7–0.8s），每轮重启后 `touch tap 240 240` 都把「时钟待机页」切到
  「控制面板页」（帧差恒 **230400 px** = 480×480 整屏），**无一轮出现“命令成功、应用不响应”，也不需要重启板子**。
  → 由此**勘正**三个组件（Calendar / Chart / `_mapping`-TabView）`components/ui_v1/<组件>/platforms.md` 里那条
  「反复 `kill -9 zkgui` 后触摸注入不响应」的已知限制（那是 kill 的后果，不是设备/组件缺陷）。
  脚本 `temp/setprop_accept.py`，证据 `temp/setprop_accept/`（含 `workspace/temp/setprop_accept/RESULT.md` 与 20 张逐轮截图）。
- **遇到掉网怎么处理**：按**现场断电重启**处理（先看设备电源/网线/WiFi，再 `adb connect`）；
  排查方向优先 setprop 通道（`setprop` 静默失败的板子才考虑 kill 兜底）。
- 另：`adb reboot` 后 /tmp 是空的（tmpfs）→ 必须**整套重推**（见 §2/§4），且重启后要等网络 adb 重新上线。
