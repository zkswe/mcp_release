---
id: v85x-usb-gadget-storage
title: V85X USB OTG 切换与 Device 存储（ADB / U盘 + EMMC / TF 卡双介质）
category: v85x
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [V85X]
tags: [USB 连电脑当 U盘拷文件, 客户口径 MTP, sys, devices, platform, soc, usbc0, 切 host, U盘, cat usb_device, 切 device, ADB, cat usb_null, 断开, cat otg_role, 查当前角色]
evidence: []
---
# V85X USB OTG 切换与 Device 存储（ADB / U盘 + EMMC / TF 卡双介质）

> 🔍 **检索导引**：本文回答「V85X / V85XEMMC 如何切换 USB OTG、切 host / device 模式、切 ADB / U盘 模式、
> USB 连电脑当 U盘拷文件（客户口径 MTP）」——**读节点即切换**：
> `/sys/devices/platform/soc/usbc0/` 下 `cat usb_host`（切 host/U盘）、`cat usb_device`（切 device/ADB）、
> `cat usb_null`（断开）、`cat otg_role`（查当前角色）。切换代码与完整 configfs 序列见 §3/§4。
> 同款工程代码：CV201_PND / xdv23 / xdv200300 的 `usb_monitor.cpp`（`sys::change_usb_mode()`）。

> 来源：xdv23 / xdv200300 项目实测（V85XEMMC 平台，AW_V853 芯片，ZKSWE Develop Team 2023 usb_monitor.cpp）。
> 沛哥定界（2026-09-03）：客户/产品口径说的「MTP 功能」= **USB 连电脑当存储设备拷照片/视频**，
> 实现是 Linux **configfs usb_gadget + mass_storage**（UMS/U 盘模式，非 MTP 协议栈）。
> 本文把两条知识线统一成一条主线：**数据介质双选（EMMC 分区 / TF 卡）** × **USB 档位（ADB 调试 / U盘存储）**。

## 0. 概念框架：介质与档位是两个正交维度

- **介质（数据放哪）**：内置 EMMC `mmcblk0p1` → 挂 `/mnt/storage`；TF 卡 `mmcblk1` → 挂 `/mnt/extsd`。
  探针：`/dev/block/mmcblk0boot0` 是否存在。
- **USB 档位（连电脑暴露成什么）**：ADB 调试（functionfs `ffs.adb`） / U盘存储（mass_storage） / NONE（仅充电）。
  U盘档要把「当前介质」的块设备写进 `lun.0/file`。

## 1. 存储介质双选（双介质主线）

### 1.1 块设备 / 挂载点 / 用途

| 宏 | 值 | 用途 |
|----|----|------|
| `STORAGE_BLOCK` | `/dev/block/mmcblk0p1` | 内置 EMMC 数据分区 |
| `STORAGE_MOUNT_POINT` | `/mnt/storage` | EMMC 挂载点（相册 ALBUMPATH） |
| `EMMC_BLOCK_BOOT` | `/dev/block/mmcblk0boot0` | **介质探针**：存在 = 有内置 EMMC |
| `TFCARD_BLOCK` | `/dev/block/mmcblk1` | TF 卡块设备 |
| `TFCARD_MOUNT_POINT` | `/mnt/extsd` | TF 卡挂载点 |

```c
#define STORAGE_BLOCK       "/dev/block/mmcblk0p1"
#define STORAGE_MOUNT_POINT "/mnt/storage"
#define EMMC_BLOCK_BOOT     "/dev/block/mmcblk0boot0"   // xdv200300 起新增
#define TFCARD_BLOCK        "/dev/block/mmcblk1"        // xdv200300 起新增
#define TFCARD_MOUNT_POINT  "/mnt/extsd"
```

### 1.2 启动挂载（Main.cpp onEasyUIInit，双分支）

```cpp
base::mkdirs(STORAGE_MOUNT_POINT);
if (base::exists(EMMC_BLOCK_BOOT)) {                       // 有内置 EMMC
    NO_EXCEPTION(base::fat32::checkAndMount(STORAGE_BLOCK, STORAGE_MOUNT_POINT)); // → /mnt/storage
} else {                                                   // 纯 TF 卡硬件变体
    NO_EXCEPTION(base::fat32::checkAndMount(TFCARD_BLOCK, TFCARD_MOUNT_POINT));   // → /mnt/extsd
}
```

同一块硬件跑两套产品 = 只用这套探针分支；媒体目录约定：
- EMMC 版：照片 `/mnt/storage/photo`、录像 `/mnt/storage/video`
- TF 卡版：照片/录像落在 `/mnt/extsd` 下（挂载点不同，上层路径按介质常量拼）

### 1.3 介质约定与产品测试

- TF 卡/外置卡还承载产测：`/mnt/extsd/product_test.ini` 存在 → 启动进 TestActivity
- updater 备份等也走 `/mnt/extsd/update.img.backup`（双介质通用约定）

## 2. USB 档位（ADB / U盘 / NONE）

### 2.1 档位表

| 档 | 电脑看到 | function | VID/PID | 介质无关？ |
|----|---------|----------|---------|-----------|
| `E_USB_CONFIG_ADB` | adb 设备 | functionfs `ffs.adb` | `0x18D1/0xD002` | ✅ 与介质无关 |
| `E_USB_CONFIG_STORAGE` | U 盘 | mass_storage.usb0 | `0x1F3A/0x1000` | ❌ 暴露源 = 当前介质块设备 |
| `E_USB_CONFIG_NONE` | 无（仅充电） | 无 | `0x1F3A/0x1001` | ✅ |

### 2.2 U盘档暴露源：复用介质探针二选一（usb_monitor.cpp STORAGE 档）

```cpp
case E_USB_CONFIG_STORAGE:
    _write_content(USB_VID, "0x1F3A");
    _write_content(USB_PID, "0x1000");
    if (!base::exists(USB_GADGET_FUN_MASS)) {
        base::mkdirs(USB_GADGET_FUN_MASS);
        _write_content(USB_GADGET_FUN_MASS "/lun.0/inquiry_string", "zkswe");
    }
    symlink(USB_GADGET_FUN_MASS, USB_GADGET_C1_F1);
    if (base::exists("/dev/block/mmcblk0boot0")) {          // 与 Main.cpp 同一探针
        _write_content(USB_GADGET_FUN_MASS "/lun.0/file", USB_STORAGE_BLOCK);  // EMMC
    } else {
        _write_content(USB_GADGET_FUN_MASS "/lun.0/file", USB_TFCARD_BLOCK);   // TF 卡
    }
    break;
```

⚠️ **口径**：`lun.0/file` 只接受**块设备/镜像文件**（不接受挂载路径），所以暴露的是
`/dev/block/mmcblk0p1` 或 `/dev/block/mmcblk1`，**不是** `/mnt/extsd` 这个字符串；
`/mnt/extsd` 只是 TF 卡在设备内的挂载点。电脑端看到的是当前介质文件系统内容（照片/视频）。

### 2.3 档位选择与防重

```cpp
// 开机（mainLogic.cc）：开发样机 adb、量产 U盘
sys::set_usb_config(Settings::instance().dev ? E_USB_CONFIG_ADB : E_USB_CONFIG_STORAGE);

// 防重复配置：SystemProperties app.usb.cfg 记录当前档，相同直接 return
SystemProperties::getInt("app.usb.cfg", &cur, E_USB_CONFIG_NONE);
if (cur == target) return;
SystemProperties::setInt("app.usb.cfg", target);
```

USB 插入/充电检测：GPIO（xdv23 用 `GPIO_260` = `GPIO_USBIN_DET`，1=插入）。

## 3. OTG 角色切换（读节点即切换）

V85X 节点在 `/sys/devices/platform/soc/usbc0/`：`otg_role`(查) / `usb_device`(切 device) / `usb_host`(切 host) / `usb_null`(清角色)。
⚠️ 切角色前先读 `usb_null` 清当前角色（相同档早退），再读目标节点；Z21 路径不同 ——
跨平台对照、设备树差异与 8 步 configfs 概览见 `hardware/usb-otg-switch.md`（正文）。

## 4. configfs usb_gadget 配置序列（8 步，顺序不可乱）

```cpp
#define KERNEL_CONFIG       "/sys/kernel/config/"
#define USB_GADGET          KERNEL_CONFIG "usb_gadget/"
#define USB_GADGET_G1       USB_GADGET "g1/"
#define USB_GADGET_G1_SUB   USB_GADGET_G1 "strings/0x409/"
#define USB_GADGET_G1_C1    USB_GADGET_G1 "configs/c.1/"
#define USB_GADGET_FUN_FFS  USB_GADGET_G1 "functions/ffs.adb"
#define USB_GADGET_C1_FFS   USB_GADGET_G1_C1 "ffs.adb"
#define USB_GADGET_FUN_MASS USB_GADGET_G1 "functions/mass_storage.usb0"
#define USB_GADGET_C1_F1    USB_GADGET_G1_C1 "f1"
#define USB_FFS_ADB         "/dev/usb-ffs/adb"
```

1. **挂 configfs**：`/sys/kernel/config` 下无 `usb_gadget/` 时
   `mount("none", "/sys/kernel/config", "configfs", MS_SILENT, NULL)`
2. **g1 描述**：mkdirs `strings/0x409` → `manufacturer=zkswe`、`product=flythings`、`serialnumber=20080411`
3. **configs/c.1**：mkdirs `configs/c.1/strings/0x409` → `bmAttributes=0xc0`（自供电）、`MaxPower=500`
4. **清旧绑定**：`unlink(configs/c.1/ffs.adb)` + `unlink(configs/c.1/f1)`（两档互斥，先拆干净）
5. **切角色**：ADB/STORAGE → device；NONE → host
6. **建 function + 挂 config**：
   - ADB：写 VID/PID → mkdirs `functions/ffs.adb` → `symlink(ffs.adb, configs/c.1/ffs.adb)`
     → `/dev/usb-ffs/adb` 不存在则 mkdirs + `mount("adb", ..., "functionfs", MS_SILENT, "uid=2000,gid=2000")`
   - STORAGE：写 VID/PID → mkdirs `mass_storage.usb0` + `lun.0/inquiry_string=zkswe`
     → `symlink(mass_storage.usb0, configs/c.1/f1)` → `lun.0/file` = 介质块设备（见 §2.2 双分支）
7. **重启 adbd**：`SystemProperties::setString("ctl.restart", "adbd")`
8. **绑定 UDC**：枚举 `/sys/class/udc` 第一个目录名 → 写 `g1/UDC`

## 5. EMMC/TF 分区 FAT32 管理（edge/fat32 项目自带实现）

```cpp
namespace base { namespace fat32 {
  bool format_fat32fs(const char *block);                            // newfs_msdos 格式化
  std::string mount_vfat(const char* dev, const char* mount_point);
  bool umount(const char *mount_point);
  void checkAndMount(const std::string& block, const std::string& mount_point); // 非 FAT32 先格式化再挂
  int getBlockSize(const std::string& mount_point);
}}
```

FlyThings app 自己把介质块设备格式化为 FAT32 并挂载（EMMC 分区 / TF 卡都适用），
配合 U盘档给电脑读。相册浏览/删除走挂载点下目录（photo/video）。

## 6. 平台差异备忘

- **Z21**（`soc0/soc/soc:usbotg` 路径、只有 usb_host/usb_device 两节点、shell cat 即切）与 T113（`usbc0@0` 带 reg 地址）→ 对照表在 `hardware/usb-otg-switch.md`（正文）。
- **V85X/V85XEMMC**：本文 §1–§4（usb_monitor.cpp = 完整可抄实现，含 g1/mass_storage/ffs.adb + 介质双分支）。

## 7. 坑与注意

1. **互斥 / configfs 未挂 / adbd uid-gid 与 `ctl.restart`**：与 `hardware/usb-otg-switch.md` §坑 1–3 同源——
   换档先 unlink 两个旧 symlink（残留→新档不生效）、先 `mount none configfs`，ADB 档 functionfs uid/gid=2000。
2. **暴露整分区 vs 设备端写入抢数据**：U盘档暴露的是整块介质（mmcblk0p1 / mmcblk1），
   若设备端同时挂载读写相册会抢——量产取舍：默认 U盘模式但写入只在拍照/录像瞬间；
   要更稳可切档前 umount（业务层控制）
3. **UDC 绑定时机**：function 挂好后必须写 `g1/UDC` 才被电脑枚举；枚举不到先看
   `/sys/class/udc` 是否有控制器（无 = 内核没开 gadget/驱动问题）
4. **探针一致性**：Main.cpp 挂载与 usb_monitor 暴露源必须用同一探针（mmcblk0boot0），
   两处不一致会出现「设备端写 A 介质、电脑读 B 介质」的错乱
