---
id: v85x-usb-otg-mode-switch
title: V85X 切换 USB OTG（host/device / ADB/U盘）速查
category: v85x
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [Z21, V85X]
tags: [sys, devices, platform, soc, usbc0, ADB, usb_host, U盘, usb_null, 断开, otg_role]
evidence: []
---
# V85X 切换 USB OTG（host/device / ADB/U盘）速查

> 检索导引：问「V85X 怎么切 USB OTG / 切 ADB 模式或 U 盘模式 / 读哪个 sysfs 节点 / 和 Z21 路径区别 / 切完电脑不识别」→ `hardware/usb-otg-switch.md`（跨平台节点对照 + configfs 8 步 + U盘暴露源）；V85X 代码级细节 → `v85x/usb-gadget-storage.md` §3/§4。
> 节点速查：`/sys/devices/platform/soc/usbc0/` 下 `cat usb_device`(ADB) / `usb_host`(U盘) / `usb_null`(断开) / `otg_role`(查)——**读节点即切换**；切前先读 `usb_null` 清角色。

⚠️ **切完电脑不识别** = 光切角色不够：ADB 档还差 configfs 挂 `ffs.adb` + `ctl.restart adbd`；U盘档还差 `lun.0/file` 写块设备（mmcblk0p1 / mmcblk1，介质探针二选一）+ 写 `g1/UDC`。

