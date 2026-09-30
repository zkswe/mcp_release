---
id: devflow-upgrade-pack-image
title: 固化升级：出 update.img 并刷进设备（调试推送 vs 固化升级）
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [Z20, Z21, V85X]
tags: [调试, 跑一下, 推送到设备, 固化, 升级, 交付, 量产, 掉电即失, img, 用户说, 把程序升级进去, 固化到设备, 出个升级包, 出货版本, 量产版本, 烧到机器里]
evidence: []
---
# 固化升级：出 update.img 并刷进设备（调试推送 vs 固化升级）

> 检索导引：问「出升级包 / 固化到设备 / OTA·TF 卡·ADB 升级各怎么做 / 换开机 logo / 升级后掉网 / update.img 体积上限 / 固化后 /res 变只读」→ 本文；Z20 86 面板升级链路与坑见 `knowledge/hardware/z20-86panel-upgrade.md`。
> 铁律：**「调试/跑一下/推送到设备」≠「固化/升级/交付/量产」**。
> - 调试 = `flythings_build_ui_flow`（内部 `fun launch`）→ 临时推送到设备运行，**掉电即失**；
> - 固化 = `flythings_pack_upgrade`（内部 `fun pack`）→ 出 **update.img**，刷进设备后**掉电保留**。
>
> 用户说「把程序升级进去 / 固化到设备 / 出个升级包 / 出货版本 / 量产版本 / 烧到机器里 / TF卡升级包 / OTA 包 / 整机升级」→ 一律 `flythings_pack_upgrade`，**不是** launch。各入口（用户口语、客户端按钮、AI 自主决策）都按这条判；禁止自造脚本或命令路径。

## 一、出包：fun pack（命令行）

```bash
# 在项目根目录（或 --project-dir 指定）
fun install                      # ① 先同步依赖（缺依赖会报 package xxx not found in local）
fun build                        # ② 编译（产物进 .fun/<平台>/imgout）
fun pack                         # ③ 出包 → 默认 .fun/<平台>/update.img

# 常用参数
fun pack -o ./out/update.img            # 指定输出路径（默认 ./out/update.img 语义）
fun pack --release-version 1.2.3        # 指定升级包版本号（批量升级工具按它比对）
fun pack --ab                           # 制作适用于 AB 系统的 OTA 升级包
fun pack --startup-dir /res             # 启动路径（默认 /res）
fun pack -p v85x                        # 指定平台（否则取工程配置）
```

对应到 MCP：`flythings_pack_upgrade(project_root, out_path, release_version, ab, with_build, dry_run)` —— 一条龙 install →（可选 build）→ pack，并返回产物路径/大小/时间与刷法说明；`dry_run=True` 只看命令计划不执行。

> IDE 等价操作（官方文档「制作升级镜像文件」）：工具栏 → **路径配置**（选镜像输出目录）→ 点编译 → 生成 update.img 到该目录。命令行 `fun pack` 与之等价，便于自动化/CI。

## 二、刷进设备：四种落地方式

### 1) TF 卡升级（最常用）
- TF 卡格式化为 **FAT32**（仅支持 FAT32；建议 ≤16G，过大有兼容性问题）；
- 卡根目录放 `update.img`（可选再放 `boot_logo.JPG` 换开机 logo —— 落点/体积/坑见 **§三**）；
- 插卡 → 重新上电 → 系统检测到升级文件弹出升级界面 → 勾选项目点「升级」；
- ⚠️ 升级完成后**及时拔卡**，否则重启会反复升级。

### 2) ADB 固化（屏幕/卡座不方便时）
```bash
adb push ./update.img /tmp/update.img
adb shell setprop sys.zkupgrade.flag 255
adb shell setprop sys.zkupgrade.dir /tmp
adb shell setprop ctl.restart zkswe
```
> 与「ADB 下载调试」区分：调试（IDE 下载调试 / `fun launch`）不固化，重启后程序不保留。

### 3) 插卡自动升级（屏幕损坏或触摸不准）
- 卡根目录放无后缀文件 `zkautoupgrade`，内容 = 延时秒数（不填默认 2s 后自动开始升级）；可选 `zkrebootdelay`（同样无后缀）：升级完再延时 N 秒重启，`-1` 表示不重启。

### 4) 远程 OTA / 批量升级
- **远程**：设备端 HTTP 下载 `update.img`（或 `boot_logo.JPG`）到 TF 卡目录，再调用升级检测函数（系统启动或插卡时会检测卡根目录的 `update.img` 并校验）。
- **批量（同一局域网，已知设备 IP）**：电脑端批量升级工具，选择 update.img，可按「项目名（ro.app.name）/ 目标版本号 / 强制升级」策略批量刷；仅支持 WiFi/以太网设备，**仅支持 Z20、Z21、Z261 平台**。

### 5) 整机刷机卡（系统级，另一回事）
系统开不了机、需要系统新功能/修 bug 时，用官方 SD 刷机包 + 电脑端刷机工具制作刷机卡，格式化整机（不是应用升级包）；刷机包找官方群共享，注意机器背面标签对型号。

### 6) ⚠️ 固化会**整体替换目标机的 `/res`** —— 应用资源必须随包走（2026-09-13 真机踩实）

`update.img` 里装的是你自己工程的 `/res` 内容，刷上去后**原 app 在 `/res` 下的东西全部消失**。实测（V85X SPINOR + RTL8733BS）真故障：汉字全变方块（英文正常）—— 原 app 自带中文字体，`/res/font` 被清空 → 回退到 `/etc/font/fzcircle.ttf`（21KB，只有英文）；修法 = 工程 `font/*.ttf`（工具链自动写 EasyUI.cfg 的 `font` 键，见 `knowledge/devflow/custom-font-config.md`）。**动手前先自问**：原 app 在 `/res` 下带了哪些"运行期才需要"的东西？（字库 / 配置文件 / 二进制工具）→ 全部搬进自己工程。硬件层面的东西（如 BT 补丁固件）已收进组件，用户/AI 不需要关心（见 `components/`）。

**刷机后的核验手法**（界面验收直接抓屏交视觉模型，不要手搓 fb0）
```bash
adb shell "busybox strings /res/lib/libzkgui.so | grep -i <你自己的关键字>"   # 装上去的是不是自己的 app
adb shell "ls -l /res/font /res/bin/firmware/rtlbt; cat /res/etc/EasyUI.cfg" # 关键资源在不在
```

## 三、换开机 logo（`boot_logo.JPG` → MISC 分区）

> 一句话口径（钟工 2026-09-17 给定）：**开机 logo 放 `boot_logo.JPG`，升级落点是 `MISC` 分区，升级方法与 `update.img` 完全一样**（同一套升级机制、同一套触发流程）。不是「logo 分区」，更不是 `/res`。

### 1) 落点与体积上限（唯一硬约束）

| 项 | 口径 |
|----|------|
| 落点分区 | **MISC**（本板 = `mtd4`） |
| 体积上限 | **≤ MISC 分区大小**（本板 **512 KB**；换板子先量，别照抄） |
| 文件格式 | **JPG**，文件名固定 **`boot_logo.JPG`** |
| 分辨率 | 对应屏幕（Z21 = 1024×600） |
| 生效时机 | **升级完成、重启后生效** |

本板实测分区表（Z21，2026-09-17，`cat /proc/mtd`）：mtd0 BOOT0 `0x50000` / mtd1 KERNEL `0x680000` / mtd2 res `0x720000` / mtd3 config `0x110000` / **mtd4 MISC `0x80000` = 512 KB** / mtd5 data `0x80000`。查法：`adb shell "cat /proc/mtd"` 找 MISC 那一行的 size（十六进制）。

⚠️ 本板 `/res` 里**没有** logo 文件 —— logo 不在应用资源里：别往 `resources/images/` 放，也别指望跟 `fun pack` 一起打进 `/res`（`/res` 是应用资源分区，见 §二 6)）。**其它平台/机型务必先量 MISC 分区大小**，512 KB 只对本板成立。

### 2) 两种触发方式（与 `update.img` **同机制**）

**① TF 卡（最常用）**：卡格式化 **FAT32**（≤16G）；卡**根目录**放 `boot_logo.JPG`（**可与 `update.img` 并列**）；插卡 → 重新上电 → 弹升级界面 → 勾选项目后点「升级」；⚠️ 升级后**及时拔卡**，否则每次重启反复升级。

**② ADB 固化（屏幕/卡座不便时）**（与 `update.img` 的 ADB 固化完全同一套：`flag 255` = 该目录里有升级物，`dir` 指目录）
```bash
adb push boot_logo.JPG /tmp/boot_logo.JPG
adb shell setprop sys.zkupgrade.flag 255
adb shell setprop sys.zkupgrade.dir /tmp
adb shell setprop ctl.restart zkswe
```

**③ 插卡自动升级（`zkautoupgrade`）/ ④ 远程 OTA（HTTP 下 `boot_logo.JPG` 到卡根目录）** 同样适用，机制与 `update.img` 一致 —— 见 §二 3)、4)。

### 3) ⚠️ 本板实测坑：`adb reboot` 后整板掉网

本板（Z21，2026-09-17 实测）：`adb reboot` 之后**整板掉网**（WiFi/adb 都回不来），只能**现场断电重启**。所以：换 logo 真正危险的是**最后那一步重启** → 排好时机（现场有人能断电）再触发；平时**不要随手 `adb reboot`**；`fun launch` / `adb push` 不需要重启。

### 4) 边界与待验证（**不作为结论**）

| 说法 | 状态 |
|------|------|
| 只放 `boot_logo.JPG`（不放 `update.img`）时**只写 MISC、不替换 `/res`** | **待真机验证**（钟工口径是「同 `update.img` 机制」，本条尚未实测） |
| 其它平台（F133 / Z20 / T113 / V85X / Z235X）的 MISC 分区大小 / 升级界面里 logo 项与 app 项能否单独勾选 | **待确认**（本机只量到 Z21 = 512 KB） |

### 5) 工具（本仓自带，可直接用）

```bash
# ① 生成（默认「深底 + 品牌字样」版式；**生成后自动校验 ≤ MISC 上限**，超了报错）
python tools/make_boot_logo.py --size 1024x600 --out boot_logo.JPG [--text ZKSWE --sub "深圳中科世为科技" --tag "FlyThings OS"]
# ② 推设备并触发升级（**默认 dry-run 只打印命令**，确认真要触发再加 --yes）
python tools/set_boot_logo.py --image boot_logo.JPG --device <serial|IP:5555> [--dir /tmp --yes]
```

`set_boot_logo.py` 触发前必做校验：文件存在 / 是 JPG / 体积 ≤ MISC 上限（能连设备就读 `cat /proc/mtd` 取**真实**上限）/ 设备在线；adb 走全仓单一入口 `adb_tools.resolve_adb()`（环境变量 `ADB`/`FLYTHINGS_ADB` → 随包 `tools/adb/` → PATH）。

> 检索词：开机 logo / boot_logo / boot_logo.JPG / MISC 分区 / logo 512K / 换开机图 / 开机 LOGO 怎么换 / 升级界面里勾 logo / adb reboot 掉网

## 四、实测坑（本机 2026-09-12 复现 + 修复验证）

> 2026-09-12 验证：装 **VC++ 2015-2022 Redistributable (x86)** 后 `C:\zkswe\fun\tools\fsimg.exe` 可正常启动（该 exe 实为签名工具 `fssign`，用法 `fssign [-i <name:path>]... -p <platform> -o <file>`），端到端出包成功（`fun pack -p V85X` → `.fun/v85x/update.img`，84.6 KB）。结论：**Windows 上做固化升级，VC++ x86 运行库是硬前置**。

| 现象 | 根因 | 处理 |
|---|---|---|
| `FATAL sign error: exit status 0xc0000135`（或 `0xc000007b`） | 打包/签名用的 `fsimg.exe` 是 **32 位**程序，系统只装了 x64 VC++ 运行时（缺 32 位 `msvcp140.dll` / `vcruntime140.dll`）；0xc0000135=找不到 DLL，0xc000007b=位数不匹配 | **已修复**：装「Visual C++ 2015-2022 Redistributable **(x86)**」（需管理员，装完 `C:\Windows\SysWOW64\msvcp140.dll` 存在即 OK）；无管理员权限时退路是把 32 位这两个 dll 放到 `C:\zkswe\fun\tools\`（`fsimg.exe` 同级） |
| `FATAL generate error: package ini@0.0.1 not found in local` | 工程依赖没装（`fun install` 未跑或没跑完） | 先 `fun install` 再 pack |
| 出包成功但设备没变化 | 把 update.img 放在了卡的非根目录，或卡不是 FAT32 | 卡格式化 FAT32，文件放根目录，插卡重上电 |

> 工具侧已把前两条映射为可执行 `hint` 返回（`flythings_pack_upgrade` 的 `PACK_ERR_HINTS`）。

## 四点五、Z20 真机实操记录：一次「页面不对」引出的完整固化链路（2026-09-24，已端到端跑通）

**场景/根因**：给 Z20（`Zkswe_SSD20X_SPINOR`，480×480）「升级进去」，`fun launch` 后 md5 全对、界面也对，但**设备重启后屏幕回到旧版**（用户反馈「页面不对」）。根因 = **Z20 的 `/res` 是只读 squashfs，`fun launch` 推的是 `/tmp` tmpfs**：

| 事实 | 证据 |
|---|---|
| `/res` 只读 | `mount` → `/dev/block/mtdblock3 on /res type squashfs (ro,...)`（`/res/ui` 里 `touch` 直接 `Read-only file system`） |
| 调试推到哪 / `/tmp` 是内存 | `fun launch` → `/tmp/ui/{*.ftu,images,ime}` + `/tmp/font/*.ttf` + `/tmp/EasyUI.cfg`（`EasyUI.cfg.resPath = /tmp/ui`）；`tmpfs on /tmp type tmpfs (rw,...size=32368k)` ⇒ **重启即清空** |
| 应用怎么起 / 事后怎么确认 | `/etc/init.rc`：`service zkswe /bin/zkgui` + `export LD_LIBRARY_PATH /tmp:/lib:/mnt/extsd/lib:/mnt/sdnand/lib`（库**优先 /tmp**，其次才有持久目录）；查 `cat /proc/uptime`（uptime 只有 31~49 s = 刚重启过）、`ls -l /tmp/ui`（空了） |

**结论：Z20 上「升级进设备」必须走 `update.img`（固化），`fun launch` 只能看效果、掉电即失。**

### 2) 实测固化序列（Z20 / .177，2026-09-24，一次成功）

```bash
# ① 出包（本机 Windows）——MCP 一条龙最省事：flythings_pack_upgrade(project_root, out_path, release_version)
#    等价命令行： fun install && fun build && fun pack -p Z20 --release-version 1.0.0 -o ./out/update.img
#    本次产物 out/update.img = 1,913,404 B（1.82 MB）；pack 日志打印带进包的字体：HanSans-Medium/HanSansLight

# ② 推到设备并触发（同一串，顺序别改）
adb push ./out/update.img /tmp/update.img        # 1.9MB 约 4 s
adb shell setprop sys.zkupgrade.flag 255          # 255 = 该目录有升级物
adb shell setprop sys.zkupgrade.dir /tmp
adb shell setprop ctl.restart zkswe               # 只重启应用；应用起来后读属性执行升级
# ③ 升级流程自己会触发整机重启（本轮 ~45 s 内完成，adb 掉一下再回来）
```

### 3) 刷完怎么验收（三步硬证据）

```bash
adb shell cat /proc/uptime                 # uptime 归零 = 确实重启过
adb shell ls -l /res/ui                    # 本次：album/brightness/home/main/settings/video.ftu + images/ + ime/
adb shell ls -l /res/font                  # 本次：HanSans-Medium.ttf 1763788 + HanSansLight.ttf 2044
```
再抓一张真机截图交给视觉模型（`flythings_device_screenshot`）确认页面就是新版本（本次抓到屏保页，与工程一致）。⚠️ 顺带核对：固化会**整体替换 `/res`**（§二 6)），刷完 `/res/ui` 里**只剩你自己工程的页** ⇒「运行期才需要的东西」（字库/配置/二进制）必须随包走。

### 4) 字体要进包：`package.properties` 的 `enable.font.location`

- 工程没有 `package.properties` 时，`fun launch` **只推 app 不推 `font/`**（工具会提示），于是「设备上没字库」；固化时也不想漏字库，就在工程根加 `{ "enable.font.location": true }` —— `fun build` 后 `font/*.ttf` 会被写进 `EasyUI.cfg` 的 `font` 键并打进 `update.img` → 设备侧落在 **`/res/font/`**。
- 配套坑：工具在「设备无字库」时会**自动往工程投一份 `font/zkswe-hans-common.ttf`**（通用档）。若你自带字体，**用完记得删掉那份**，否则多 0.87MB 且字库优先级混乱。字库覆盖自查：本工程用 `ui/_gen/build_fonts.py` 出 **GB2312 全字库**（一级+二级 6903 字 / 1.76 MB），起因是「嫦娥.mp4」的 **`嫦`（二级字）** 显示不出来 —— 只做一级（3755 字）会缺这类字。

### 5) 反面教材：`/mnt/sdnand/app/` 有一份旧版 ≠ 升级路径

本次在目标机看到 `/mnt/sdnand/app/{ui,lib,font,tr,cacert.pem}`（旧版）、`/mnt/sdnand/EasyUI.cfg`（**0 字节**）、`/mnt/sdnand/update.img`。这些**不是**官方升级机制：`init.rc` 只从 `/res` 起应用，`/tmp` 优先；`/mnt/sdnand/lib` 虽在 `LD_LIBRARY_PATH` 里，但**UI/字体/配置没有对应的持久读取路径**。⇒ 别自己铺 `/mnt/sdnand/app` 猜启动方式，**统一走 `update.img`**。

### 6) 体积上限：`update.img` 必须 ≤ **res 分区**大小（出包前先对表）

- `/proc/mtd`（`Zkswe_SSD20X_SPINOR` 实测）：mtd0 BOOT / mtd1 KERNEL / mtd2 rootfs / **mtd3 `res` = `0x720000` = 7,470,080 B** / mtd4 config / mtd5 LOGO / mtd6 data。
- `update.img` 的落点就是 **res**（`/res` = `/dev/block/mtdblock3` squashfs）→ **包体上限 = 该分区字节数**（本型号 7,470,080 B；本工程实测 5.85 MB）。换型号/换板先 `cat /proc/mtd` 对表，**别照抄**。
- 无独立 `zkupgrade` 二进制（能力在 `/bin/zkgui` 内）→ 升级永远是「置属性 + `setprop ctl.restart zkswe`」。刷完的硬判据：`adb shell ls -l /res/lib/libzkgui.so` 的大小/md5 == 本地 `.fun/z20/libzkgui.so`（只比 `update.img` 体积不准：小改动下包体可能恰好不变）。
- ⚠️ 刷前确认**设备真正加载的是哪一份** —— SD 卡 `/mnt/extsd/EasyUI.cfg` 可能把程序劫持到旧 lib：`knowledge/devflow/package-properties-easyui-cfg.md` 「查找优先级」节。

## 五、排查用到的定位手法（可复用）

- fun 的“家目录”由环境变量决定：本机 `FLYTHINGS_FUN_DIR` / `FUN_HOME_PATH` = `C:\zkswe\fun`，下载的打包工具落在 `C:\zkswe\fun\tools\`（`fsimg.exe`、`make-fs/make-fs.exe` 等）。判断某个 exe 是不是 32 位：读 PE 头 `Machine`（`0x14c`=x86，`0x8664`=x64）；进程起不来报 `0xC0000135` = DLL 找不到（缺 32 位 MSVC 运行时），`0xC000007B` = 镜像/位数不匹配（拿 x64 dll 喂 32 位程序）。历史产物长什么样：`.fun/<平台>/update.img`。
- **分清「设备上跑的是哪一份」**：`fun launch` 后跑的是 `/tmp/ui`；固化后跑的是 `/res/ui`。查 `ls -l /tmp/ui`（有内容=调试态）、`ls -l /res/ui`（新工程页=固化态）、`cat /proc/uptime`（小=刚重启，调试态已被清）。
