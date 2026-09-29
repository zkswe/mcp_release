---
id: v85x-usb-otg-mode-switch
title: V85X 切换 USB OTG（host/device / ADB/U盘）速查
category: v85x
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [Z21, V85X]
tags: [本文是, 的直达速查, 问答式, 代码级细节, 完整 configfs 序列, md, 同目录, 两篇关键路径一致, 改动需同步, xdv23]
evidence: []
---
# V85X 切换 USB OTG（host/device / ADB/U盘）速查

> 检索导引：问「V85X 怎么切 USB OTG / 切 ADB 模式或 U 盘模式 / 读哪个 sysfs 节点 / 和 Z21 路径区别 / 切完电脑不识别」→ 本文（速查）；完整 configfs 序列见 `v85x/usb-gadget-storage.md`。
> 本文是「**V85X 上如何切换 USB OTG**」的直达速查（问答式），代码级细节/完整 configfs 序列
> 见 `usb-gadget-storage.md`（同目录）。两篇关键路径一致，改动需同步。来源：CV201_PND /
> xdv23 / xdv200300 的 `usb_monitor.cpp` 实测（V85XEMMC 平台，AW_V853）。

## 一句话结论

V85X 的 USB OTG 角色由 **sysfs 节点控制，读（cat）节点即切换**，路径与 Z21 不同：
`/sys/devices/platform/soc/usbc0/`（Z21 是 `/sys/devices/soc0/soc/soc:usbotg/`）。

## 切到 ADB 模式（device 从设备）

```
cat /sys/devices/platform/soc/usbc0/usb_device
```

⚠️ 完整链路还差两步（光切角色电脑不识别）：configfs 挂 `ffs.adb` function + 重启 adbd
（`ctl.restart adbd`），见 `usb-gadget-storage.md` §4 的 8 步序列；产品代码直接用
`sys::change_usb_mode(E_USB_MODE_DEVICE)`（usb_monitor.cpp）。

## 切到 U盘模式（host 主设备，连电脑当存储拷文件）

```
cat /sys/devices/platform/soc/usbc0/usb_host
```

⚠️ U盘档暴露源 = `lun.0/file` 写**块设备**（mmcblk0p1 / mmcblk1，按介质探针二选一），
不是挂载路径；见 `usb-gadget-storage.md` §2.2。

## 断开（仅充电/无角色）

```
cat /sys/devices/platform/soc/usbc0/usb_null
```

## 查询当前角色

```
cat /sys/devices/platform/soc/usbc0/otg_role    # 输出 usb_device / usb_host / (空)
```

## 代码切换（CV201_PND usb_monitor.cpp 同款）

```cpp
typedef enum { E_USB_MODE_NULL, E_USB_MODE_DEVICE /*adb*/, E_USB_MODE_HOST /*u盘*/ } usb_mode_e;
sys::get_usb_mode();      // 读 otg_role 内容比对
sys::change_usb_mode(mode); // DEVICE: 读 usb_null 清角色→读 usb_device→configfs→重启 adbd
                            // HOST:   读 usb_null 清角色→读 usb_host→configfs（不重启 adbd）
```

要点：切换前先读一次 `usb_null` 清当前角色，再读目标节点；ADB 档必须 `ctl.restart adbd`。

## 和 Z21 的区别

| | V85X / V85XEMMC | Z21 |
|---|---|---|
| 路径 | `/sys/devices/platform/soc/usbc0/` | `/sys/devices/soc0/soc/soc:usbotg/` |
| 节点 | otg_role / usb_device / usb_host / usb_null | usb_host / usb_device |
| 切换方式 | 读节点即切换 | 读节点即切换 |
