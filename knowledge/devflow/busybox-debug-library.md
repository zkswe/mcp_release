---
id: devflow-busybox-debug-library
title: "BusyBox 调试工具库（bin_tools/{平台}/busybox，随 MCP 分发）"
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [Z21, V85X]
tags: [2026-09-08 新增, ifconfig, ping 等调试工具, 需要查 IP, 端口, 进程, adb push 即用, 与 touch 同架构, bin_tools, README, md]
evidence: []
---
# BusyBox 调试工具库（bin_tools/{平台}/busybox，随 MCP 分发）

> 检索导引：问「设备上没有 ifconfig / ping / ps / uname / 想看设备 IP·网卡·进程 / 设备缺命令怎么办」→ 本文（六平台静态 busybox，push 即用）；出包与部署动作用哪条见 `knowledge/devflow/deploy-scene-map.md`。
> 2026-09-08 新增。背景：设备系统内没有 busybox / ifconfig / ping 等调试工具，
> 需要查 IP/端口/进程/网络时无工具可用 → 电脑端预编译各平台静态 busybox，
> adb push 即用（与 `touch`/`ui_test` 同架构，见 bin_tools/README.md）。

## 平台 ↔ 文件

| 平台 | 架构/libc | 文件 |
|------|----------|------|
| f133 / f135 | RISC-V 64 (musl) | `bin_tools/f133/busybox`、`bin_tools/f135/busybox` |
| z20 / z21 | ARMv7 (glibc) | `bin_tools/z20/busybox`、`bin_tools/z21/busybox` |
| t113 / v85x | ARMv7 (musl) | `bin_tools/t113/busybox`、`bin_tools/v85x/busybox` |

BusyBox v1.36.1，全部 CONFIG_STATIC=y 静态链接（push 即用、零依赖）。

## 用法（adb push 即用）

```bash
adb push bin_tools/z21/busybox /tmp/busybox
adb shell chmod 777 /tmp/busybox
adb shell /tmp/busybox ifconfig                # 查 IP
adb shell /tmp/busybox ip addr                 # 同上（ip 风格）
adb shell /tmp/busybox ping -c 3 192.168.1.1   # 连通性
adb shell /tmp/busybox netstat -tulnp          # 端口监听
adb shell /tmp/busybox route -n                # 路由表
adb shell /tmp/busybox ps w / top / free / dmesg
adb shell /tmp/busybox telnet <ip> / nc -l -p 5555
```

## 内置工具（全开，实测齐全）

- 网络：ifconfig ip ping ping6 netstat route arp arping traceroute telnet telnetd nc wget httpd nslookup hostname udhcpc
- 系统：ps top free mount umount dmesg hexdump xxd md5sum sha1sum cat ls cp mv rm ln mkdir chmod chown find grep sed awk vi tar gzip
- Shell：ash/sh

## 重新编译

源码/坑位在本地 `workspace/tools/busybox/README.md`（不入库）；MCP 侧只分发 ELF。
重编：WSL 内 `wsl bash scripts/bb_build_all.sh all`（构建必须 WSL 原生盘，Windows exe 工具链无法派生 cc1）。

## 设备端没有的常用命令 → 用 busybox applet（别写“设备不支持”）

裁剪 rootfs 常见缺失：`grep / sed / head / tail / dd / md5sum / df / find / wc / xxd / vi`。
**不是设备不支持，是没装**——push 一个 busybox 上述全有（applet 列表见上）。

```bash
adb push bin_tools/v85x/busybox /tmp/busybox && adb shell chmod 777 /tmp/busybox
A=/tmp/busybox
$A dd if=/dev/fb0 bs=2400 count=1600 | $A gzip -1 > /tmp/x.gz   # 抓帧（设备无 dd/gzip 时）
$A md5sum /tmp/ui/images/*.png | $A head                        # 校验图到底推上去没
$A df -h /tmp                                                   # 抓帧前先看 /tmp 空间
$A grep -n "onUI_show" /tmp/log.txt; $A tail -50 /tmp/log.txt
$A find / -name "*.ftu" 2>/dev/null | $A head
```

- 抓帧三条纪律：① 抓前 `df -h /tmp`（**空间不足会静默截断**，图看着对其实少了一截）
  ② 图片有没有部署用 `md5sum` 比对，不要靠肉眼 ③ **`fun launch` 会清 `/tmp`** → push 的工具/抓的帧要在同一次会话里用完。
- `cat` 是设备内置的（不需要 busybox）；`adb exec-out` 不可用（`error: closed`）→ 一律
  `adb shell "…" > 本地文件` 或 `adb pull`。
- 设备上跑多步时把 `A=/tmp/busybox` 存成变量，命令短且不易敲错。
