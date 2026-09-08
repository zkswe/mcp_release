# BusyBox 调试工具库（bin_tools/{平台}/busybox，随 MCP 分发）

> 2026-09-08 新增。背景：设备系统内没有 busybox / ifconfig / ping 等调试工具，
> 需要查 IP/端口/进程/网络时无工具可用 → 电脑端预编译各平台静态 busybox，
> adb push 即用（与 ui_test 同架构，见 bin_tools/README.md）。

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

源码/坑位在本地 `tools/busybox/README.md`（不入库）；MCP 侧只分发 ELF。
重编：WSL 内 `wsl bash scripts/bb_build_all.sh all`（构建必须 WSL 原生盘，Windows exe 工具链无法派生 cc1）。
