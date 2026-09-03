# V85X USB Device 模式（ADB / U盘存储）

> 来源：xdv23 / xdv200300 项目实测（V85XEMMC 平台，AW_V853 芯片，ZKSWE Develop Team 2023 usb_monitor.cpp）。
> 客户/产品口径说的「MTP 功能」在 FlyThings V85X 工程里通常指 **USB 连电脑当存储设备**，
> 实现是 Linux **configfs usb_gadget + mass_storage**（UMS/U 盘模式，非 MTP 协议栈）；
> 另一档是 **ADB 调试模式**（functionfs）。两档共用一个 gadget 配置器，按开关切换。
> ⚠️ xdv23 与 xdv200300 的存储介质策略不同（xdv23 只暴露内置 EMMC；xdv200300 支持 TF 卡方案），见 §1.5。

## 1. 两种配置一句话

| 配置 | 电脑看到 | 实现 | VID/PID |
|------|---------|------|---------|
| `E_USB_CONFIG_ADB` | adb 设备（调试） | functionfs `ffs.adb` | `0x18D1/0xD002` |
| `E_USB_CONFIG_STORAGE` | U 盘（拷照片/视频） | mass_storage 暴露 EMMC 分区 | `0x1F3A/0x1000` |
| `E_USB_CONFIG_NONE` | 无（仅充电） | 无 function，角色回 host | `0x1F3A/0x1001` |

## 1.5 双介质差异（xdv23 vs xdv200300，沛哥 2026-09-03 验证）

xdv200300 在 xdv23 基础上新增 **TF 卡作为存储/暴露介质**（适配无内置 EMMC 的硬件变体）：

| 宏 | xdv23 | xdv200300 |
|----|-------|-----------|
| `STORAGE_BLOCK` | /dev/block/mmcblk0p1 | /dev/block/mmcblk0p1 |
| `STORAGE_MOUNT_POINT` | /mnt/storage | /mnt/storage |
| `EMMC_BLOCK_BOOT`（探针） | 无 | /dev/block/mmcblk0boot0 |
| `TFCARD_BLOCK` | 无 | /dev/block/mmcblk1 |
| `TFCARD_MOUNT_POINT` | 无 | /mnt/extsd |

- **挂载**（Main.cpp onEasyUIInit，双分支一致）：`base::exists(/dev/block/mmcblk0boot0)`
  为真 → `checkAndMount(mmcblk0p1 → /mnt/storage)`（EMMC）；否则 → `checkAndMount(mmcblk1 → /mnt/extsd)`（TF 卡）
- **USB 暴露**（usb_monitor.cpp `E_USB_CONFIG_STORAGE` 档，同一探针二选一写 `lun.0/file`）：
  EMMC 存在 → 暴露 `mmcblk0p1`；否则 → 暴露 **`/dev/block/mmcblk1`（TF 卡）**
- ⚠️ **口径澄清**：暴露给电脑的是**块设备**（mass_storage 的 `lun.0/file` 只接受块设备/镜像文件，不接受挂载路径），
  不是把 `/mnt/extsd` 这个字符串暴露出去；`/mnt/extsd` 只是 TF 卡在设备内的**挂载点**，
  电脑端看到的是 TF 卡文件系统内容（照片/视频目录）。

## 2. OTG 角色切换（V85X/全志 usbc0 sysfs）

路径与 Z21（`soc0/soc/soc:usbotg`）不同，V85X 是 platform soc 下的 usbc0：

```
/sys/devices/platform/soc/usbc0/otg_role   # 读当前角色：usb_device / usb_host
/sys/devices/platform/soc/usbc0/usb_device # 读它 = 切到 device 模式
/sys/devices/platform/soc/usbc0/usb_host   # 读它 = 切到 host 模式
/sys/devices/platform/soc/usbc0/usb_null   # 读它 = 空角色
```

切换 = fopen/fread 目标节点（读即触发内核切换），不是写。封装：

```cpp
usb_mode_e get_usb_mode() {           // 读 otg_role 内容比对 usb_device/usb_host
    char buf[32]; _read(USB_OTG_ROLE, buf, sizeof(buf)); ...
}
void set_usb_mode(usb_mode_e mode) {  // 相同则跳过；否则读 usb_null 再读目标节点
    if (get_usb_mode() == mode) return;
    char buf[32]; _read(USB_NULL, buf, sizeof(buf));   // 先清空角色
    if (mode == E_USB_MODE_DEVICE) _read(USB_DEVICE, buf, sizeof(buf));
    else if (mode == E_USB_MODE_HOST) _read(USB_HOST, buf, sizeof(buf));
}
```

## 3. configfs usb_gadget 完整配置序列（顺序不可乱）

```cpp
#define KERNEL_CONFIG      "/sys/kernel/config/"
#define USB_GADGET         KERNEL_CONFIG "usb_gadget/"
#define USB_GADGET_G1      USB_GADGET "g1/"
#define USB_GADGET_G1_SUB  USB_GADGET_G1 "strings/0x409/"
#define USB_GADGET_G1_C1   USB_GADGET_G1 "configs/c.1/"
#define USB_GADGET_FUN_FFS USB_GADGET_G1 "functions/ffs.adb"
#define USB_GADGET_C1_FFS  USB_GADGET_G1_C1 "ffs.adb"
#define USB_GADGET_FUN_MASS USB_GADGET_G1 "functions/mass_storage.usb0"
#define USB_GADGET_C1_F1   USB_GADGET_G1_C1 "f1"
#define USB_VID            USB_GADGET_G1 "idVendor"
#define USB_PID            USB_GADGET_G1 "idProduct"
#define USB_FFS_ADB        "/dev/usb-ffs/adb"
#define USB_STORAGE_BLOCK  "/dev/block/mmcblk0p1"
```

1. **首次挂 configfs**：`/sys/kernel/config` 不存在 `usb_gadget/` 时
   `mount("none", "/sys/kernel/config", "configfs", MS_SILENT, NULL)`
2. **g1 描述**：mkdirs `strings/0x409` → 写 `manufacturer=zkswe`、`product=flythings`、`serialnumber=20080411`
3. **configs/c.1**：mkdirs `configs/c.1/strings/0x409` → 写 `bmAttributes=0xc0`（自供电）、`MaxPower=500`
4. **清旧绑定**：`unlink(configs/c.1/ffs.adb)` + `unlink(configs/c.1/f1)`（两档互斥，先拆干净）
5. **切角色**：ADB/STORAGE → device；NONE → host
6. **按档建 function + 挂 config**：
   - ADB：写 VID/PID → mkdirs `functions/ffs.adb` → `symlink(functions/ffs.adb, configs/c.1/ffs.adb)`
     → `/dev/usb-ffs/adb` 不存在时 mkdirs + `mount("adb", /dev/usb-ffs/adb, "functionfs", MS_SILENT, "uid=2000,gid=2000")`
   - STORAGE：写 VID/PID → mkdirs `functions/mass_storage.usb0` + 写 `lun.0/inquiry_string=zkswe`
     → `symlink(mass_storage.usb0, configs/c.1/f1)` → **`lun.0/file=/dev/block/mmcblk0p1`**（关键：暴露哪个块设备）
7. **重启 adbd**：`SystemProperties::setString("ctl.restart", "adbd")`
8. **绑定 UDC**：枚举 `/sys/class/udc` 第一个目录名 → 写入 `g1/UDC`

## 4. 应用集成（xdv23 实测）

- **开机默认档**：mainLogic.cc 初始化
  `sys::set_usb_config(Settings::instance().dev ? E_USB_CONFIG_ADB : E_USB_CONFIG_STORAGE)`——
  开发样机 dev=1 走 adb；量产走 U 盘模式（插 USB 电脑直接读 EMMC 里的照片视频）
- **防重复配置**：`SystemProperties` 属性 `app.usb.cfg`（getInt/setInt）记录当前档，
  相同直接 return——防止重复 mount/symlink/adbd 重启
- **充电/USB 插入检测**：GPIO（xdv23 用 `GPIO_260`，`GPIO_USBIN_DET`，1=插入）
- 存储目录约定：`ALBUMPATH = /mnt/storage`，照片 `/mnt/storage/photo`、录像 `/mnt/storage/video`，
  U 盘模式下电脑打开设备看到的就是这个 FAT32 分区内容

## 5. EMMC 分区 FAT32 管理（edge/fat32，项目自带实现）

```cpp
namespace base { namespace fat32 {
  bool format_fat32fs(const char *block);              // newfs_msdos 格式化（变成 FAT32）
  std::string mount_vfat(const char* dev, const char* mount_point);
  bool umount(const char *mount_point);
  void checkAndMount(const std::string& block, const std::string& mount_point); // 缺分区先格式化再挂
  int getBlockSize(const std::string& mount_point);
}}
```

Main.cpp `onEasyUIInit`：`mkdirs(/mnt/storage)` + `NO_EXCEPTION(base::fat32::checkAndMount("/dev/block/mmcblk0p1", "/mnt/storage"))`。
即 FlyThings app 可自行把 EMMC 分区格式化为 FAT32 并挂载做媒体存储（配合 U 盘模式给电脑读）。

## 6. 平台差异备忘

- **Z21**（soc0 路径，shell 一行切换）：`cat /sys/devices/soc0/soc/soc:usbotg/usb_host|usb_device`
- **V85X/V85XEMMC**（platform/soc/usbc0 路径，文件 IO 切换）：本文 2/3 节
- 两平台都是 **configfs gadget** 思路，V85X 的 usb_monitor.cpp 是完整可抄实现（g1/mass_storage/ffs.adb 全套）

## 7. 坑与注意

1. **mass_storage 与 adb 互斥**：换档必须先 unlink 旧 symlink，两个都要拆（残留 symlink 会导致新档不生效）
2. **configfs 未挂载**：直接 mkdirs 会失败，先 `mount none configfs`
3. **暴露整分区有风险**：`lun.0/file` 指向整个 `/dev/block/mmcblk0p1`，若系统同时挂载使用中
   （/mnt/storage 读写相册），电脑端操作可能与设备端抢数据——量产取舍：默认 U 盘模式但相册写入
   只发生在拍照/录像时刻；要更稳可切档前 umount（业务层控制）
4. **UDC 绑定时机**：function 挂好后必须写 `g1/UDC` 才枚举到电脑；枚举不到先看
   `/sys/class/udc` 是否有控制器（无 = 内核没开 gadget/驱动问题）
5. ADB 档的 functionfs 挂载 uid/gid=2000 是 adbd 服务用户；`ctl.restart adbd` 走
   `SystemProperties`（init 属性服务），不是 system()
