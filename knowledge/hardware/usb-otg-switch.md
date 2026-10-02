---
id: hardware-usb-otg-switch
title: USB OTG / ADB / U盘 模式切换 + HOST 外设接入（跨平台对照：V85X / T113 / Z21）
category: hardware
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [Z21, T113, V85X]
tags: [或问, USB HOST 外设接入, U盘插上没反应, 读不到, USB 摄像头, 键鼠 接入, 且没有指定平台, 没说 V85X, T113, Z21, 各平台 sysfs 路径不同, 回答必须给出 V85X, 禁止默认按某一个平台答, 本篇 = 跨平台总表, 角色节点, 切换语义]
evidence: []
---
# USB OTG / ADB / U盘 模式切换 + HOST 外设接入（跨平台对照：V85X / T113 / Z21）

> 🔍 **检索导引（命中条件）**：用户问「**如何切换 USB OTG**」「**USB OTG 怎么切换**」「**怎么切到 ADB 模式**」「**怎么切 U盘 模式**」「**USB 连电脑当 U盘拷文件**」「**设备读节点切 USB 模式 / host device 切换 / 主从切换**」
> 或问「**USB HOST 外设接入**」「**U盘插上没反应/读不到**」「**USB 摄像头/键鼠 接入**」「**USB host devices**」
> **且没有指定平台**（没说 V85X / T113 / Z21）→ **本篇就是答案**：切换与 host 外设接入是跨平台共性场景，各平台 sysfs 路径不同，
> **回答必须给出 V85X / T113 / Z21 三条路径对照并请用户确认平台，禁止默认按某一个平台答**。
> 本篇 = 跨平台总表（角色节点/切换语义/挂载点）。V85X 完整可抄的 configfs 8 步与存储介质双选 →
> `knowledge/v85x/usb-gadget-storage.md` §1–§4；V85X 代码级切换实现在 `knowledge/v85x/usb-otg-mode-switch.md`。

## 一句话

全平台都是「**cat（读）sysfs 节点即切换角色**」，但**节点路径按平台/内核设备树不同**：

| 平台 | OTG 根路径（实测/文档） | 节点 | 备注 |
|------|------------------------|------|------|
| **V85X / V85XEMMC**（AW_V853） | `/sys/devices/platform/soc/usbc0/` | `otg_role`(查) `usb_device`(切ADB) `usb_host`(切U盘) `usb_null`(断开) | CV201_PND / xdv23 / xdv200300 `usb_monitor.cpp` 实测 |
| **T113**（车载 PND） | `/sys/devices/platform/soc@3000000/soc@3000000:usbc0@0/` | 同上 4 节点 | ⚠️ 带 reg 地址 `usbc0@0`，≠ V85X 的 `usbc0/`；T113CarSystem_PND `usb_monitor.cpp` 实测 |
| **Z21 / Z210**| `/sys/devices/soc0/soc/soc:usbotg/` | `usb_host`(切U盘) `usb_device`(切ADB) | wiki z210_core_board 官方文档；未见 otg_role/usb_null/configfs 描述 |

## shell 一行切换

```bash
# V85X：切 ADB / 切 U盘 / 断开 / 查当前
cat /sys/devices/platform/soc/usbc0/usb_device
cat /sys/devices/platform/soc/usbc0/usb_host
cat /sys/devices/platform/soc/usbc0/usb_null
cat /sys/devices/platform/soc/usbc0/otg_role

# T113：同上，根路径换成带 reg 的
cat /sys/devices/platform/soc@3000000/soc@3000000:usbc0@0/usb_device
cat /sys/devices/platform/soc@3000000/soc@3000000:usbc0@0/usb_host

# Z21/Z210：只有两个节点（文档口径：cat 即切）
cat /sys/devices/soc0/soc/soc:usbotg/usb_host      # 切 U盘
cat /sys/devices/soc0/soc/soc:usbotg/usb_device    # 切 ADB
```

## 代码切换（V85X / T113 同款，usb_monitor.cpp）

`usb_mode_e { E_USB_MODE_NULL, E_USB_MODE_DEVICE/*adb*/, E_USB_MODE_HOST/*u盘*/ }`，
`sys::change_usb_mode(mode)` / `sys::get_usb_mode()`（读 otg_role 比对）：

```cpp
void change_usb_mode(usb_mode_e mode) {
    char buf[32];
    _read_content(USB_NULL, buf, sizeof(buf));          // ① 先读 usb_null 清角色
    if (mode == E_USB_MODE_DEVICE) {
        _read_content(USB_DEVICE, buf, sizeof(buf));    // ② 切 device
        set_usb_config(mode);                           // ③ configfs gadget
        RESTART_SERVICE("adbd");                        // ④ 重启 adbd（必须）
    } else if (mode == E_USB_MODE_HOST) {
        _read_content(USB_HOST, buf, sizeof(buf));      // ② 切 host
        set_usb_config(mode);                           // ③ 换 VID/PID，不重启 adbd
    }
}
```

要点：ADB 档必须 `ctl.restart adbd`；HOST 档不用。Z21 wiki 无源码级 configfs 描述（未收录，按文档 cat 节点即可）。

## configfs 序列（V85X/T113 实测同款，8 步）

mount configfs → g1 strings(manufacturer=zkswe / product=flythings / serialnumber=20080411)
→ configs/c.1(bmAttributes 0xc0 自供电 / MaxPower 500) → unlink 旧 symlink(`configs/c.1/ffs.adb` + `configs/c.1/f1`)
→ 切角色（ADB/STORAGE→device，NONE→host）→ VID/PID（ADB `0x18D1/0xD002`；存储档 `0x1F3A/0x1000`、NONE `0x1F3A/0x1001`，档位表见 `knowledge/v85x/usb-gadget-storage.md` §2.1）
+ function（`ffs.adb` 或 `mass_storage.usb0`）→ symlink 挂 config → 枚举 `/sys/class/udc` 第一个目录名写 `g1/UDC`。
ADB 档还要 `/dev/usb-ffs/adb` 不存在时 mkdirs + `mount(..."functionfs", uid=2000,gid=2000)`。
防重：SystemProperties `app.usb.cfg` 记录当前档，相同直接 return。完整可抄实现见 `knowledge/v85x/usb-gadget-storage.md` §4。

> ⚠️ **只读节点切角色 ≠ 电脑能识别**：必须走完上面 8 步（尤其写 `g1/UDC`）；ADB 档缺 `ctl.restart adbd`、
> U盘档缺 `lun.0/file` 写块设备，电脑端都枚举不到。

## U盘档暴露源（V85X/T113）

`lun.0/file` 只接受**块设备/镜像文件**（不是挂载路径）。二选一由**介质探针**`/dev/block/mmcblk0boot0` 决定：存在 = 内置 EMMC → `mmcblk0p1`（设备内挂 `/mnt/storage`）；不存在 = TF 卡 → `mmcblk1`（挂 `/mnt/extsd`）。
⚠️ 探针必须与启动挂载分支用**同一个**，两处不一致 = 「设备端写 A 介质、电脑读 B 介质」。

## USB HOST 外设接入（客户场景：U盘/摄像头/键鼠读不到）

> host 角色（已 `cat usb_host`）下插入外设，系统自动挂载/枚举；客户报「插上没反应」先查这节。

### 1. U盘/TF（存储外设）→ 自动挂载点 + MountMonitor 监听

- 官方口径（wiki system/tf_usb.md）：插 **TF 卡自动挂 `/mnt/extsd`**；插 **U盘自动挂 `/mnt/usb1` / `/mnt/usb2` / `/mnt/usb3`**（按实际 USB 口）；工程实测（CV201_PND / T113CarSystem_PND `media_context.cpp` 存储表）：
  `E_STORAGE_TYPE_USB1 → "/mnt/usb1"`、`E_STORAGE_TYPE_USB2 → "/mnt/usbotg"`（OTG 口当 host 用时 U盘挂 `/mnt/usbotg`）
- 文件路径 = 挂载目录 + 自身目录（如 `/mnt/usb1/test.txt`）；读写前先确认已挂载
- **监听拔插**：`#include <base/base.h>`（Manifest 需 base-utility ≥9.0.0），
  `base::MountNotification mn_usb1("/mnt/usb1", cb)` 或工程里 `MediaMountListener : MountMonitor::IMountListener`（E_MOUNT_STATUS_MOUNTED/UNMOUNTING）；查询 `MOUNTMONITOR->isMounted("/mnt/usb1")`
- 客户「U盘读不到」排查顺序：① 确认角色是 host（`cat .../otg_role`）② 确认挂载点出现（`ls /mnt/usb1`）③ 看是哪个口（usb1/usb2/usbotg）④ 监听事件是否触发

### 2. USB 摄像头（UVC）→ V85X 有完整接入知识

V85X host 接入 UVC 摄像头（发现/取流/录像/拍照）→ 见 `knowledge/v85x/uvc-usb-camera.md`（inotify 发现 /dev/video + uvcvideo + mpi 注册双路预览）。T113/Z21 未收录摄像头接入细节（未实测，不编造）。

### 3. USB 键鼠（HID）→ 未收录

知识库暂无 USB HID 键鼠接入文档（是否支持/如何读取未实测）。客户问到时标「未收录」，问需求方或查官方文档，不猜。

## 坑

1. 换档先 unlink 两个旧 symlink，残留导致新档不生效
2. configfs 未挂载先 `mount none configfs`
3. ADB 档 functionfs 挂载 uid/gid=2000；`ctl.restart adbd` 走 init 属性服务
4. 不带平台名提问 → 先对照上表区分 V85X/T113/Z21，路径不通用（尤其 T113 带 reg 地址）
5. UDC 未绑定电脑不识别；枚举不到先看 `/sys/class/udc` 是否有控制器

## 来源

- V85X：CV201_PND / xdv23 / xdv200300 `src/system/usb_monitor.cpp` + `src/media/media_context.cpp`（实测）
- T113：`temp_car/public/t113/T113CarSystem_PND/jni/system/usb_monitor.cpp` + `jni/media/media_context.cpp`（实测，2026-09-07 需求方提醒核对）
- Z21/Z210：官方 wiki `wiki/flythings/hardware/z210_core_board.md`「USB功能/切换USB模式」
- U盘挂载/监听：官方 wiki `wiki/flythings/system/tf_usb.md`（TF→/mnt/extsd，U盘→/mnt/usb1|2|3，MountNotification/MountMonitor）
