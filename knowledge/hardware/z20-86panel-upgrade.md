---
id: hardware-z20-86panel-upgrade
title: Z20 / 86 面板：升级（固化）链路 · 包格式 · 数据面（真机实证）
category: hardware
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [Z20]
tags: [检索词：Z20 升级, 86 面板固化, extupdate, img, update, release]
evidence: []
---
# Z20 / 86 面板：升级（固化）链路 · 包格式 · 数据面（真机实证）

> 检索导引：问「Z20/86 面板升级链路 / sys.zkupgrade 系列属性 / 升级包格式 ZKSWEV1.0 / release.ext4 / 插卡自动升级 / 固化后卡开机 logo / 升级完整板掉网」→ 本文（真机实证）；通用出包口径见 `devflow/upgrade-pack-image.md`。
> 检索词：Z20 升级 / 86 面板固化 / extupdate.img / update.img / release.ext4 / zkautoupgrade /
> zkrebootdelay / sys.zkupgrade.dir / sys.zkupgrade.flag / zk_upgrade_check / libzkupgrade /
> UpgradeMonitor / UpgradeActivity / 插卡自动升级 / U 盘升级 / MISC 开机 logo / 升级后整板掉网 /
> mmcblk0p1 / mmcblk0p2 / sdnand / res 分区 / ext4 数据面 / Ext4Utils / 机型 magic / 固化包绑定机型
>
> 取证时间：2026-09-23（真机 `<设备IP>:5555`，`Zkswe_SSD20X_SPINOR` + `RGB_LCD480480` 480×480，
> 即 **SW48480040D1 = Z20 版 4 寸 86 盒智能面板**）。方法：只读侦察 + 出包 A/B + 一次真机触发（见 §8）。
> **每个结论都标了证据等级**：`【实测】`真机/产物实证 · `【反汇编】`设备端库静态解析 · `【工程】`参考工程源码 ·
> `【未证实】`推断，不得当结论用。

---

## 0. 一句话结论

1. **升级程序不在你的 app 里**：`/lib/libzkupgrade.so` + `libeasyui.so` 的 `UpgradeMonitor` + `libinternalapp.so`
   的 `UpgradeActivity` + `/system/res/internal/zkupgrade.ftu` 都是**系统件**，装上就有升级界面与检测能力；
   你只需要「把包放对地方 + 触发」。【实测】【反汇编】
2. **触发有三条正路**：① 卡/U 盘根目录放 `update.img`/`extupdate.img` + 重上电（弹界面勾选）② 同目录再放无后缀
   `zkautoupgrade`（自动勾选，默认 2 s 后开升）③ **ADB 三属性**（`sys.zkupgrade.dir` + `sys.zkupgrade.flag=255`
   + `ctl.restart zkswe`，不掉电）。【实测/官方 wiki】
3. **`release.ext4=true` 不是可选项**：它决定**出包文件名**（`extupdate.img`）和**包内 `/res` 镜像的文件系统类型**
   （ext4，而不是默认 squashfs）。Z20 参考工程 `PublicTuyaSwitch` 就是开着的。【实测 A/B】
4. **升级包与机型绑定**：包头里带机型 magic（Z20 = `0xaa550404` = `Zkswe_SSD20X_SPINOR`），机型号对不上会被拒
   （升级库里有 `sys_upgrade_type_no_match_error`）。【实测】【反汇编】
5. **⚠️ 最危险的一条在数据面**：`/dev/block/mmcblk0p2 → /mnt/sdnand` 是 **app 自己挂载**的 ext4，
   **挂不上就 `make_ext4fs` 整盘重建**（无备份、无确认）。【工程】

---

## 1. 升级触发链路（含真机属性名）

| 路线 | 放什么 | 放哪 | 触发 | 备注 |
|---|---|---|---|---|
| ① 插卡/U 盘（常用） | `update.img`（squashfs 包）/ `extupdate.img`（ext4 包，见 §4） | 卡/U 盘**根目录**（FAT32） | **重新上电** → 弹升级界面 → 勾选 → 升级 | 升完**立刻拔盘**，否则每次开机重刷 |
| ② 插卡自动升级 | ① + 无后缀 `zkautoupgrade` | 同上 | 插卡重上电，**默认 2 s 后自动开升** | `zkautoupgrade` 内容 = 延时秒数；再放无后缀 `zkrebootdelay`（`-1` = 升完不重启） |
| ③ **ADB 固化**（屏幕/卡座不便） | 包推到设备 `/tmp` | `/tmp` | 见下行三属性 | 掉电即失，仅用于当次固化 |
| ④ 远程 OTA / 批量升级 | 由设备下载到 `update.img` | 数据面 `temp/` | app 调 `checkUpgradeFile(dir)` | 见 `z20-tuya86-upgrade-firstaid.md` |

**③ 的准确命令（官方 wiki `upgrade-pack-image.md` 口径，与本机库内属性名一致）**

```bash
adb push update.img /tmp/update.img            # 或 extupdate.img
adb shell setprop sys.zkupgrade.dir /tmp       # 告诉升级库去哪个目录找包
adb shell setprop sys.zkupgrade.flag 255       # 255 = 该目录里有升级物（强制）
adb shell setprop ctl.restart zkswe            # 重启 app → 框架的 UpgradeMonitor 接手
# 另有：sys.zkupgrade.force（强制位）/ sys.zkupgrade.umount（等待卸载）/ sys.zkapp.state（app 状态）
```

**升级库扫描/识别的文件与目录**（`strings /lib/libzkupgrade.so`，本机实测字符串表）：

- 文件名：`update.img`、`extupdate.img`、`full_update.zk`、`boot_logo.JPG/.GIF/.H264`（大小写两套）、
  `zkparams.bin`、`MISC.bin`、`ts.cfg`、`zkautoupgrade`、`zkrebootdelay`
- 目录：`/mnt/usb`、`/mnt/usb1`、`/mnt/extsd`（`/mnt/mmc` 也在表里）
- uboot 线：`/mnt/storage/zkimg/update.img` + `/mnt/storage/zkimg/.zkupgrade.cfg`（日志里会出现
  `Need to enter uboot upgrade` / `Try to enter uboot upgrade`）
- 去重记录：**`/data/.zkupgraderec`**（与 fun.exe 里那串 `.zkugraderec` 差一个字母，以设备端库为准）
- 升级时会被停掉的服务：`zkswe`（app）、`wpa_supplicant`、`blink`、`lylink`、`bt`、`link`
  → **升级期间必然掉网，别在升级窗口里等 adb**

**给 UI 的本地化文案键**（`libinternalapp.so`，可用来对日志）：
`sys_upgrade_success / _fail / _need_reboot / _type_no_match_error / _version_match_error /
_mount_error / _umount_error / _image_size_error / _logo_size_error / _not_enough_space / _pack_format_error /
_copy_img_err / _warning`

---

## 2. 升级是系统件：真机开机日志就是证据

本板 boot 后 `logcat` 全量只有 3 条升级相关行，但足够定性（全量日志见
`temp/tuya86_study/evidence/logcat_d.txt`）：

```
D/zkgui ( 928): registerActivity name: UpgradeActivity OK!        ← 内置升级页已注册
D/zkgui ( 928): MountMonitor addMountListener pListener: 0x401bfae8  ← 挂了"插盘自动检测升级"监听
D/zkgui ( 928): Ext4Utils mount ret 0                             ← ext4 数据面挂载成功
```

- `/bin/zkgui`（9564 B 的启动器）**动态链 `libzkupgrade.so`**；`libeasyui.so` 导出
  `UpgradeMonitor::checkUpgradeFile/checkUpgrade/startUpgrade/stopUpgrade/checkRestart/checkTouchCalib/
  startMonitoring/stopMonitoring/isUpgrading` 与 `UpgradeMountListener`。
- 升级界面本体 = `UpgradeActivity`（`libinternalapp.so`）= `/system/res/internal/zkupgrade.ftu`，
  与本工程无关 → **换 app 不用重写升级逻辑**，但**换 app 必须保证 `/res` 里没有同名 ftu 冲突**。
- `/bin/zkdaemon`（另一个系统件）只做一件事：看 `sys.zkapp.state`，不是 `running` 就
  `cp /res/etc/EasyUI.cfg /tmp/EasyUI.cfg`（或写 `{}`）→ `setprop ctl.restart zkswe`。

---

## 3. 升级包格式（`ZKSWEV1.0-180127`）

**【实测】同一工程出 5 个平台的包对照，字节级确定：**

| 偏移 | 内容 | 实证 |
|---|---|---|
| `0x00..0x0F` | 魔术串 `ZKSWEV1.0-180127` | 本板数据面上的 extupdate.img、官方 baseimg、全部自出包都一致 |
| `0x10` | `'0'`（格式版本字符） | — |
| `0x11` | `0x01` | — |
| `0x12..0x19` | 固定 8 字节（`30 23 03 10 60 6c 3c 02`） | 全部一致 |
| `0x1C` | **u32 = payload 字节数** | LK=86,016 / 本包ext4=2,097,152 / 板上包=3,145,728（均与文件长 − 572 精确相等） |
| `0x35`（4 B） | **机型 magic**：Z20=`04 04 55 aa`、Z21=`06 06 55 aa`、V85X=`0a 0a 55 aa`、F133=`07 07 55 aa` | 按 `-p` 出包 5 次对照，与 `libzkupgrade` 内机型表一字不差 |
| 头部总计 | **572 字节**（`0x23C`），其后才是 payload | 文件长 − 572 = u32@0x1C，三个包全对 |

机型 magic 表（**反汇编** `libzkupgrade.so` `.data.rel.ro`：`Zkswe_Z11=0xaa550101` / `Z6S=0xaa550202` /
`A33_SPINOR=0xaa550303` / `A33_EMMC=0xaa550303(flag f4)` / **`SSD20X_SPINOR=0xaa550404`** /
`H500s_SPINOR=0xaa550505` / `SSD21X_SPINOR=0xaa550606` / `F133_SPINOR=0xaa550707` / `T113_SPINOR=0xaa550808` /
`T113_EMMC=0xaa550808(f4)` / `SSD26X_SPINOR=0xaa550909` / `V85X_SPINOR=0xaa550a0a`）。

→ **实操含义**：包不能跨机型混用（Z20 的包刷 Z21 会被 `type_no_match_error` 拒）。

### 包内 payload = `/res` 镜像；格式 = squashfs 或 ext4

- **未开 `release.ext4`** → payload 头是 `hsqs`（squashfs），文件小（例：86,588 B）。
- **开了 `release.ext4=true`** → payload 是 **ext4 镜像**（`debugfs` 可读），体积按 1 MiB 对齐放大（例：2/3 MiB），
  内部就是 `/res` 的那棵树：`bin/ etc/EasyUI.cfg font/ lib/libzkgui.so tr/ ui/ [web/]`。【实测】

---

## 4. `release.ext4=true`（工程根 `package.properties`）—— **官方 wiki 未收录**

> 结论来源：**出包 A/B 实证** + 参考工程 `PublicTuyaSwitch/package.properties:1`（该文件全文只有
> `release.ext4=true` 与一行注释掉的 `#release.ext4.size=33554432`）。wiki / 本 MCP 知识库此前 **0 命中**。

同一工程（Z20、480×480）两次出包，只差这一行：

| | 输出文件名 | 体积 | payload 格式 | 生成时发生的事 |
|---|---|---|---|---|
| 不写 | **`update.img`** | 86,588 B | squashfs（`hsqs` @0x20） | 只做签名 |
| `release.ext4=true` | **`extupdate.img`** | 2,097,724 B | **ext4**（`debugfs` 可列目录） | 工具**自动下载并安装 `make-ext4fs`** 后打出 ext4 镜像 |

→ 这解释了「U 盘用 `extupdate.img`、TF 卡用 `update.img`」的**包名差异**：
**不是介质决定的，是「包内 res 是不是 ext4」决定的**（`force` 出包侧跟着改名）。
→ `release.ext4.size`（被注释的 32 MiB）**是否生效 = 未证实**（`fun.exe` 字符串表里只有 `release.ext4` 字面量）。

---

## 5. 数据面：`/dev/block/mmcblk0p2 → /mnt/sdnand`（ext4，app 自挂载）

本板实测（2026-09-23 只读快照）：

```
/dev/block/mmcblk0p1 /mnt/extsd  ext4 ro,relatime,...                 ← app 资源（52.5 M，debug 路线落这）
/dev/block/mmcblk0p2 /mnt/sdnand ext4 rw,dirsync,nosuid,nodev,data=ordered  ← 数据面（64 M 分区 / 59 M fs）
mtd3 "res" (0x720000) /res squashfs ro,noatime,nodiratime            ← 系统内置 res（本板仅 3 个文件/39 KB 空壳）
```

- **挂载是 app 干的**，不是内核/init：`Ext4Utils::checkAndMount(SDNAND_MOUNT_POINT)`；
  **挂不上 → `umount` → `make_ext4fs(block, 0=NULL, …, len=0)` 整盘重建 → 再挂**（两层各一处）：
  `src/Main.cpp:15-36` 与 `src/utils/Ext4Utils.cpp:125-141`（`format()` = `:44-46`，`recoverBlock()` =
  `:143-158` 里的 `zkfs -f -y`）。真机日志对照：`Ext4Utils mount ret 0`。
  → **现场永远不要**手动 `umount /mnt/sdnand` / `mkfs` / `dd` 写 p2；要取数据 → `adb pull /mnt/sdnand`。
- 工程里数据面的落点：`TY_FS_PATH = "/mnt/sdnand/"`（涂鸦库/数据库）、`/mnt/sdnand/config.json`（版本标注）、
  `/mnt/sdnand/temp/`（升级包工作目录，见 `z20-tuya86-upgrade-firstaid.md` §2 常量表）。
- 依赖包侧旁证：`fun install` 解析 Z20 依赖时 base-utility 会带出 **`ext4 0.0.1`** 包
  （内容 = `libext4.a` + `make_ext4fs.h`，暴露 `int make_ext4fs(const char *block, s64 len, const char *mountpoint, struct selabel_handle *sh)`）
  → 想自己格式化/建 ext4 镜像时用它，**别手搓 mkfs**。

---

## 6. 机型 → 分区表（反汇编 `libzkupgrade.so`）

`0x287a4` 起是分区标签表：`uboot:BOOT:BOOT0` / `boot:KERNEL` / `system:rootfs` / `res` / `config` /
`recovery` / `MISC:boot_logo:LOGO`；后面按机型给出「每个升级项写到哪」，条目形如
`{序号, 别名, 设备A, 设备B, flags}`（`flags 0xf4` = 双目标）：

```
① uboot  → BOOT0
① boot   → KERNEL
② res    → 部分机型(/dev/block/mmcblk0p1, /dev/block/mmcblk0p2)  ← 带 SD NAND 的 SPINOR 机型走这条
          部分机型("res", "backup")                            ← 纯 NOR 机型走这条
③ misc   → MISC（升级 LOGO 用；本板这一项 = mtd5「LOGO」= 0x20000 = **128 KB**，alias 名 MISC 对到 mtd 名 LOGO）
④ config → config
```
- 另有 `Mtd` / `Mmc` 两个 DevBase 实现（`/dev/mtd/%s`、`/dev/block/platform/soc@3000000/by-name/%s`），
  即升级库**既会写 mtd 也会写 eMMC 块设备**。
- ⚠️ **写入目标分区的判定（强推断，两条独立证据，尚未直接取证）**：
  ① 表形状只有 3 种：纯-NOR（用 mtd 名 `res`/`backup`）、纯 eMMC（全 `/dev/block/mmcblk0*`）、
  **NOR + SD NAND 混合**（boot/uboot/misc/config 用 mtd 名，**res → `/dev/block/mmcblk0p1` + `mmcblk0p2`**）；
  Z20 86 面板的硬件就是「16M Flash + 128M SD Nand」→ 属第三种。
  ② 真机旁证：`/mnt/extsd` = `mmcblk0p1`，**分区有 52.5 MB，但它的 ext4 文件系统只有 2.74 MB**
  （`df`：`2804` 个 1K 块）——典型的「**小 ext4 镜像写进大分区**」形态，说明 p1 曾被某个固化包整体写过；
  而它里面的东西（`EasyUI.cfg` + `lib/libzkgui.so` + `ui/`）正是 res 那棵树。
  → 工程上按「**Z20 86 面板固化写入面 = mmcblk0p1（+p2 作为第二目标）**」理解；正式口径等真机复测回填。

---

## 7. 坑清单

| # | 现象 | 根因 | 规避 |
|---|---|---|---|
| 1 | **ADB 触发升级后整板失联**（本机 2026-09-23 真机遭遇：三属性 + `ctl.restart zkswe` 后 ~40 s 掉 adb，25 min 未回，需现场断电/插卡救援） | 升级会把 app 资源写到 **eMMC app 分区**（本机 `mmcblk0p1` = `/mnt/extsd`，见 §6），并停掉 `zkswe`/`wpa_supplicant`…；这类板子的 WiFi 由 app 带起来 → app 一被换掉就**连网都没了** | 远程触发固化时**先排好现场**（有人能断电、能手插 TF 卡）；**优先用卡/U 盘路线**（不依赖网络） |
| 2 | 包放对了、版本也对，就是不升级 | ①**去重**：`/data/.zkugraderec` 记版本（Z20 的 app 侧还会被 `/mnt/sdnand/config.json` 抬版本）②目录不在扫描表里 ③文件名不对（`update.img` vs `extupdate.img`） | 递增 `--release-version`；确认目录 ∈{`/mnt/usb*`,`/mnt/extsd`,`/mnt/storage/zkimg`}；必要时 `sys.zkupgrade.force` / `flag 255` |
| 3 | 包与机型不匹配 | 包头机型 magic（§3）+ 库内 `type_no_match_error` | 别跨机型复用包；换型号重新 `fun pack -p <平台>` |
| 4 | 固化后「汉字变方块 / 工具没了」 | `update.img` 装的是**你工程的 `/res`**，会把目标机 `/res` **整体替换** | 字库/EasyUI.cfg/必要 bin 全部随工程打进包（`upgrade-pack-image.md` §二 6)） |
| 5 | **数据面被整盘重建**（设备列表/场景全空） | p2 挂不上 → `make_ext4fs` 重建（§5，无确认环节） | 不手动动 p2；出包带数据面（`release.ext4=true`）；救数据先 `adb pull /mnt/sdnand` |
| 6 | 升级窗口里网络/串口日志断 | 升级库会 stop `zkswe`/`wpa_supplicant`/`bt`…（§1） | 别把「升级期间没网」当故障 |
| 7 | 只放 `boot_logo.JPG` 想只换 logo | 升级项是**逐项勾选**的（`zk_upgrade_get_items` / `checkUpgradeFile`）；`MISC` = 本板 mtd5 = 256 KB | logo 分辨率/体积按 MISC 上限卡（见 `upgrade-pack-image.md` §三） |
| 8 | `/tmp` 里放了包，重启后"包没了" | `/tmp` 是 tmpfs；`sys.zkupgrade.*` 属性也**不持久** | ADB 路线要**一次做完**（push → 三属性 → 重启 app），别中途 `reboot` |

---

## 8. 本次真机验证记录（含失败/未完成项，照实记）

环境：`<设备IP>:5555`，`Zkswe_SSD20X_SPINOR`，480×480，`sys.zkupgrade.force=1`，
`sys.zkapp.state=running`，`/data/.zkugraderec` **不存在**（本板此前没升级过）。

物料：自出 Z20 480×480 测试工程（`fun create -n Z20UpgTest --platform=z20` → `fun build -p z20` →
`fun pack -p z20 --release-version 1.0.2`）= `extupdate.img` 2,097,724 B（`release.ext4=true`）。

安全前置（**已做**）：`/res` 全量 pull（3 文件/39,049 B）+ 数据面 11 文件/8.84 MB pull +
`/proc/mtd`、`/proc/mounts`、`df`、`getprop`、ps 快照 + **分区 md5 基线**：

```
mtdblock2(rootfs) 41a120944a3fe5c3a2741422b65f4ea5
mtdblock3(res)    c5f155147247cf2767826cf5882e0285
mtdblock5(LOGO)   62e3692151ab1ee2e89658e06cde89ee
mtdblock6(data)   82d268c38ff046b71f2fdd136d92cd77
mmcblk0p1(extsd)  0619375594673fbe2b83583b95e51e31
mmcblk0p2(sdnand) 9a3aa19383996abdf69ae3e1cf3080bd
```

动作（17:40:19，只做了一步就停了）：`push /tmp/update.img` + `/tmp/zkautoupgrade`(`2`) +
`/tmp/zkrebootdelay`(`-1`) → `setprop sys.zkupgrade.dir /tmp` + `flag 255`（回读 OK）→
`setprop ctl.restart zkswe`。

结果：**~40 s 后设备掉 adb，随后 ping 不通，25 分钟未回**（同网段其它板 `<同网段其它板卡>` 仍在，
型号/内容都不是本板）→ 触发动作**已执行**，但「是否进入升级流程、写到哪个分区」**本次未取到证**（板卡失联）。

> 结论边界：本次**没有**拿到「升级成功/耗时/写入面/去重」的真机证据；§3/§4/§6 的包与分区结论来自
> **出包 A/B + 设备端库静态解析**，不依赖这次触发。**未做完的部分**见 §9，**救援路径**见 §10。

---

## 9. 未证实 / 待真机回填

| 项 | 状态 |
|---|---|
| 三属性触发的**实际行为**（是否进升级界面 / 是否直接写盘 / 耗时） | **未取到证**（板卡失联，见 §8） |
| `Zkswe_SSD20X_SPINOR` 的 res 目标：`mmcblk0p1(+p2)` 还是 mtd `res`(+`backup`) | **强推断 = `mmcblk0p1(+p2)`**（表形状 + p1 只有 2.74 MB 文件系统两条证据，见 §6）；**但未直接取证**（触发后板卡失联） |
| 升级是否**同时写 p1 与 p2**（数据面会被一起替换？） | **未证实**（若成立，p2 上的数据需自行备份回灌） |
| `release.ext4.size` 是否生效 | **未证实**（`fun.exe` 只有 `release.ext4` 字面量） |
| `release.ext4=false`（或不写）在**本板**的真机后果 | **未做真机对照**（Z20 参考工程开着它 → 本板大概率必须开） |
| 去重记录 `/data/.zkugraderec` 的**内容格式/同版本行为** | **未证实**（本板该文件不存在） |
| 本板 `MISC`/LOGO 分区（mtd5 = 0x20000 = **128 KB**）能否放 logo | 未量过实际可用上限（换 logo 前先 `cat /proc/mtd` 对表） |

---

## 10. 升级失败后的救援/回滚（**不依赖网络**）

板子已经掉网/进不去 adb 时，别再指望 ADB 路线 —— 用**卡/U 盘自动升级**（就是 wiki
「屏幕损坏或触摸不准情况下对系统升级」那条）：

1. TF 卡格式化 **FAT32**（≤16 G），**根目录**放**原厂/原工程**的包（Z20 86 面板就用 `extupdate.img`
   或 `update.img`，与目标分区格式要匹配，见 §4）；
2. 再放一个**无后缀** `zkautoupgrade`（内容不填 = 默认 2 s 后自动开升；想晚点升就写秒数）；
3. **重新上电** → 自动勾选并升级 → 升完**立刻拔卡**（否则每次开机重刷）；
4. 需要查串口/日志时，本板应用日志口 = 串口 `ttyS1`（`EasyUI.cfg` 里 `baud 115200`）。

本机手头可用的「原物料」：本板数据面上那份 `extupdate.img`（3,146,300 B，
md5 `19DE4DFA041BB98DFCBC9FA0906C3F8F`，头 16 B = `ZKSWEV1.0-180127`）已备份到
`.tmp_z20_upgrade/sdnand_20260923_172428/sdnand/extupdate.img`；其 payload 经 `debugfs` 核对
= `bin/ etc/EasyUI.cfg font/ lib/libzkgui.so(826,832 B) tr/ ui/(main.ftu 2,049 B + Switches/ + web/)`，
与板上 `/mnt/extsd` 的 debug 包一致（`etc/EasyUI.cfg` 与本板 `/res/etc/EasyUI.cfg` **md5 完全相同**）→
**可当"刷回原 app"的物料**。数据面 11 个文件（含 `huwen_key`/`Clock.db`/`preview_*.mp4`）也在备份里，
板子回来后可 `adb push` 回 `/mnt/sdnand`（注意 `huwen_key` 原是 `----------` 权限，回灌后按原权限 `chmod`）。

> 铁律：**救援也走官方升级机制，不要手动写 `/dev/block/*`、不要 `mkfs`/`umount` p2**（§5 会整盘重建）。

## 11. ⭐ ADB 正常升级：现行 6 步口径 + 真机实证（2026-09-24 【实测】）

> 派单人给的新版流程（替代 §1 里我早先自己拼的顺序），**已在一块干净板（`Zkswe_SSD20X_SPINOR`，480×480，
> easyui 2.4.0）上一次跑通**：写入面、耗时、掉网行为全部取到证。

### 11.1 命令（逐字照用，顺序别调）

```bash
adb push update.img /tmp           # 注意：正常升级用 update.img（squashfs payload），不是 extupdate.img
adb shell setprop sys.zkupgrade.flag 255
adb shell setprop sys.zkupgrade.dir /tmp
adb shell setprop ctl.stop zkswe
adb shell umount /mnt/extsd        # extsd 没挂时会报 Invalid argument → 无害，流程继续
adb shell setprop ctl.restart zkswe
```

### 11.2 真机结果【实测】

| 项 | 实测 |
|---|---|
| 触发 | 6 步一条 shell，**0.23 s 返回**；属性回读 `flag=255` / `dir=/tmp` ✓ |
| 触发后 | ~10 s 内 adb `error: closed` → `device offline`（app 重启 + 整机 reboot），**~50 s 回网**；`ping` 全程通 |
| **写入面** | 文件名 `update.img` → **写 `mtdblock3(res)`**：md5 `b6ff56e9…` → `d1d0812d…`；`/res` 变成包内那棵树（`lib/libzkgui.so` 267,828 B = 出包产物），squashfs 正常挂载 |
| **没动的分区** | `mtd2(rootfs)`、`mtd5(LOGO)`、**`mmcblk0p1`（= `extupdate.img` 的目标面）** |
| 变了（次要） | `mtd6(data)`（boot 后 libeasyui 写 `/data/preferences.json`）；`mmcblk0p2` 只是被我自己写的 logcat 日志动过 |
| **网络为何没掉** | 该板 WiFi 是 **init 托管**：`init.svc.wpa_supplicant=running` + `/bin/wpa_supplicant -iwlan0 -Dnl80211 -c/data/misc/wifi/wpa_supplicant.conf`、`init.svc.zkswe=running` → **不依赖业务 app**。⇒ **§6/§7 里「WiFi 由 app 带起来 → 换 res 必掉网」的归因在本板被证伪**，旧板那次永久失联要另找原因（别再当通论用） |
| 去重 | 升级后 `/data/.zkugraderec`、`/data/.zkupgraderec` **都不存在** → **ADB 直触发这条链不写去重记录**（去重可能只在 `zkupgradetipbin` 界面链生效；同版本二刷是否被挡仍未测） |
| 恢复手段 | 升级前把 `dd if=/dev/block/mtdblock3 of=/tmp/bk/mtd3_res.bin` 拉到本机（7,471,104 B）→ 需要时 `dd` 回 `mtdblock3` 即可复位 |

> **铁律（本板实测得到）**：**走 ADB → `/res` 的路线，包名必须是 `update.img`（squashfs payload）**。
> 把 `release.ext4=true` 出的 `extupdate.img`（payload = ext4 数据面树）拿来当 `update.img` 推，会把 `/res` 写成 ext4，
> 而 boot 按 **squashfs** 挂 → `SQUASHFS error: Can't find a SQUASHFS superblock` → **开机卡 logo，只能插卡救援**。

---

## 12. ⭐ 固化后「卡在开机 logo」的根因与正解（app 基础问题，2026-09-24 【实测】）

### 12.1 现象与判据

- 现象：升级完重启，屏幕**停在开机 logo**（不是黑屏死机：adb 通、`/res` 是新包、框架日志正常）。
- 判据（两个合用）：
  1. `getprop sys.zkapp.state` **为空**（正常应为 `running`）；对照一台正常在跑的 Z20 板即为 `running`；
  2. `flythings_device_screenshot` 抓到的 `fb0` **纯黑/均匀无色**，且 `pan/offsetY` 不随应用刷新变化
     → **应用层根本没画**（显示层还压在 logo 那一层）。

### 12.2 根因（两层，A 是表象、B 是底层）

| # | 事实 |
|---|---|
| **A** | **应用必须在启动后设 `sys.zkapp.state=running`**。这是系统级的「app 已起来」标记，不设 → 显示服务不把画面切给应用 → 永远停在开机 logo。 |
| **B** | 更底层：**`fun create` 生成的 fv 骨架工程（只有 `ui/main.fv`、没有 `Manifest.xml`）在这类板子上第一个界面根本不创建** → 逻辑钩子 `onCreate/onUI_init` 从不执行 → 于是 A 必现。同一块板上换 **IDE 模板风工程**（`Manifest.xml` + `ui/main.ftu` + `src/Main.cpp` + `src/logic/mainLogic.cc`）立刻正常。 |

实测台账（同一块板，四个包）：

| 版本 | 工程形态 | 改动 | 结果 |
|---|---|---|---|
| v1 | fv 骨架（无 Manifest） | — | 升级流程 ✅、卡 logo |
| v2 | fv 骨架 | 加 `SystemProperties::setString("sys.zkapp.state","running")` | **仍卡 logo**（钩子没跑） |
| v3 | fv 骨架 | 再补字体 | 字体进包 ✅、**仍卡 logo** |
| **v4** | **IDE 模板风**（`flythings_create_project`） | 属性写在 `onUI_init()` | ✅ `sys.zkapp.state=running`、界面正常上屏 |

### 12.3 正解（可直接照抄）

1. **Z20 出包/回归测试别用 `fun create` 的 fv 骨架**，用带 `Manifest.xml` 的模板风工程
   （MCP：`flythings_create_project`）；
2. `src/logic/mainLogic.cc` 顶部加 `#include "os/SystemProperties.h"`，在 `onUI_init()` 里：

```cpp
static void onUI_init(){
	SystemProperties::setString("sys.zkapp.state", "running");   // ← 不设 = 卡 logo
}
```

3. 字体要随包进 `/res`：放**工程 `resources/`**（放 `ui/` 会被忽略，`fun pack` 只吐一句 `no any font`），
   并用覆盖层 `package.properties` → `EasyUI.cfg={"font":"/res/ui/fzcircle.ttf"}`。详见
   `knowledge/devflow/package-properties-easyui-cfg.md`。

### 12.4 排查手法（下次直接用）

- `onUI_init()` 里**顺手设一个自设标记属性**（如 `sys.zkapp.dbg="onUI_init"`）→ `getprop` 一看就知道
  「界面逻辑到底跑了没」，不用反复猜（本轮就是靠它区分「属性没人设」和「钩子没跑」）。
- 先对一台**正常在跑的同平台板**做只读对照：`getprop sys.zkapp.state`、`/res` 目录形态、`/res/etc/EasyUI.cfg`。

---

## 相关

- `knowledge/hardware/hardware-models.md`（SW48480040D1 条目）
- `knowledge/devflow/upgrade-pack-image.md`（出包/刷机总口径、MISC logo、ADB 三属性）
- wiki `upgrade/auto_upgrade.md`（插卡自动升级）、wiki `upgrade/make_image.md`（TF 卡 FAT32）
- `references/kb/z20-tuya86-upgrade-firstaid.md`（4 条升级入口的源码时序 + 16 条坑，PublicTuyaSwitch）
- `references/kb/z20-86panel-extupdate.md`（`release.ext4` 出处与收录情况、机型对号）
