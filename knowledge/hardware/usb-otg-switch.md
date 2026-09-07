# USB OTG / ADB / U盘 模式切换（跨平台对照：V85X / T113 / Z21）

> 🔍 **检索导引（命中条件）**：用户问「**如何切换 USB OTG**」「**USB OTG 怎么切换**」「**怎么切到 ADB 模式**」「**怎么切 U盘 模式**」「**USB 连电脑当 U盘拷文件**」「**设备读节点切 USB 模式 / host device 切换**」
> **且没有指定平台**（没说 V85X / T113 / Z21）→ **本篇就是答案**：这是跨平台共性操作，各平台 sysfs 路径不同，
> **回答必须给出 V85X / T113 / Z21 三条路径对照并请用户确认平台，禁止默认按某一个平台答**。
> 详细 configfs 序列见 `v85x/usb-gadget-storage.md`（V85X/T113 代码同款）。

## 一句话

全平台都是「**cat（读）sysfs 节点即切换角色**」，但**节点路径按平台/内核设备树不同**：

| 平台 | OTG 根路径（实测/文档） | 节点 | 备注 |
|------|------------------------|------|------|
| **V85X / V85XEMMC**（AW_V853） | `/sys/devices/platform/soc/usbc0/` | `otg_role`(查) `usb_device`(切ADB) `usb_host`(切U盘) `usb_null`(断开) | CV201_PND / xdv23 / xdv200300 `usb_monitor.cpp` 实测 |
| **T113**（车载 PND） | `/sys/devices/platform/soc@3000000/soc@3000000:usbc0@0/` | 同上 4 节点 | ⚠️ 带 reg 地址 `usbc0@0`，≠ V85X 的 `usbc0/`；T113CarSystem_PND `usb_monitor.cpp` 实测 |
| **Z21 / Z210** | `/sys/devices/soc0/soc/soc:usbotg/` | `usb_host`(切U盘) `usb_device`(切ADB) | wiki z210_core_board 官方文档；未见 otg_role/usb_null/configfs 描述 |

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

mount configfs → g1 strings(manufacturer/product/serialnumber) → configs/c.1(bmAttributes 0xc0/MaxPower 500)
→ unlink 旧 symlink(ffs.adb+f1) → 切角色 → VID/PID（ADB `0x18D1/0xD002`；U盘 `0x1F3A/0x1001`）+
function（ffs.adb 或 mass_storage）→ symlink 挂 config → 枚举 `/sys/class/udc` 写 `g1/UDC`。
防重：SystemProperties app.usb.cfg 记录当前档。完整可抄实现见 `v85x/usb-gadget-storage.md` §4。

## U盘档暴露源（V85X/T113）

`lun.0/file` 只认**块设备**（mmcblk0p1 内置 EMMC / mmcblk1 TF 卡，按介质探针二选一），不是挂载路径。

## 坑

1. 换档先 unlink 两个旧 symlink，残留导致新档不生效
2. configfs 未挂载先 `mount none configfs`
3. ADB 档 functionfs 挂载 uid/gid=2000；`ctl.restart adbd` 走 init 属性服务
4. 不带平台名提问 → 先对照上表区分 V85X/T113/Z21，路径不通用（尤其 T113 带 reg 地址）
5. UDC 未绑定电脑不识别；枚举不到先看 `/sys/class/udc` 是否有控制器

## 来源

- V85X：CV201_PND / xdv23 / xdv200300 `src/system/usb_monitor.cpp`（实测）
- T113：`temp_car/public/t113/T113CarSystem_PND/jni/system/usb_monitor.cpp`（实测，2026-09-07 沛哥提醒核对）
- Z21/Z210：官方 wiki `hardware/z210_core_board.md`「USB功能/切换USB模式」
