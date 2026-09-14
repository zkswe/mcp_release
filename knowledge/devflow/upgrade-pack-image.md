# 固化升级：出 update.img 并刷进设备（调试推送 vs 固化升级）

> 铁律：**「调试/跑一下/推送到设备」≠「固化/升级/交付/量产」**。
> - 调试 = `flythings_build_ui_flow`（内部 `fun launch`）→ 临时推送到设备运行，**掉电即失**；
> - 固化 = `flythings_pack_upgrade`（内部 `fun pack`）→ 出 **update.img**，刷进设备后**掉电保留**。
>
> 用户说「把程序升级进去 / 固化到设备 / 出个升级包 / 出货版本 / 量产版本 / 烧到机器里 /
> TF卡升级包 / OTA 包 / 整机升级」→ 一律 `flythings_pack_upgrade`，**不是** launch。
> 各入口（用户口语、客户端按钮、AI 自主决策）都按这条判；禁止自造脚本或命令路径。

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

对应到 MCP：`flythings_pack_upgrade(project_root, out_path, release_version, ab, with_build, dry_run)`
—— 一条龙 install →（可选 build）→ pack，并返回产物路径/大小/时间与下列刷法说明；
`dry_run=True` 只看命令计划不执行。

> IDE 等价操作（官方文档「制作升级镜像文件」）：工具栏 → **路径配置**（选镜像输出目录）→ 点编译
> → 生成 update.img 到该目录。命令行 `fun pack` 与之等价，便于自动化/CI。

## 二、刷进设备：四种落地方式

### 1) TF 卡升级（最常用）
- TF 卡格式化为 **FAT32**（仅支持 FAT32；建议 ≤16G，过大有兼容性问题）；
- 卡根目录放 `update.img`（可选再放 `boot_logo.JPG` 换开机 logo）；
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
- 卡根目录放无后缀文件 `zkautoupgrade`，内容 = 延时秒数（不填默认 2s 后自动开始升级）；
- 可选 `zkrebootdelay`（同样无后缀）：升级完再延时 N 秒重启，`-1` 表示不重启。

### 4) 远程 OTA / 批量升级
- **远程**：设备端 HTTP 下载 `update.img`（或 `boot_logo.JPG`）到 TF 卡目录，再调用升级检测函数；
  系统启动或插卡时会检测卡根目录的 `update.img` 并校验。
- **批量（同一局域网，已知设备 IP）**：电脑端批量升级工具，选择 update.img，可按「项目名
  （ro.app.name）/ 目标版本号 / 强制升级」策略批量刷；仅支持 WiFi/以太网设备，
  **仅支持 Z20、Z21、Z261 平台**。

### 5) 整机刷机卡（系统级，另一回事）
系统开不了机、需要系统新功能/修 bug 时，用官方 SD 刷机包 + 电脑端刷机工具制作刷机卡，
格式化整机（不是应用升级包）；刷机包找官方群共享，注意机器背面标签对型号。

### 6) ⚠️ 固化会**整体替换目标机的 `/res`** —— 应用资源必须随包走（2026-09-13 真机踩实）

`update.img` 里装的是你自己工程的 `/res` 内容，刷上去后**原 app 在 `/res` 下的东西全部消失**。
实测（V85X SPINOR + RTL8733BS）三个真故障，都属于这一类：

| 现象 | 根因 | 修法 |
|---|---|---|
| 汉字全变方块（英文正常） | 原 app 自带中文字体，`/res/font` 被清空 → 回退到 `/etc/font/fzcircle.ttf`（21KB，只有英文） | 工程 `font/*.ttf`（工具链自动写 EasyUI.cfg 的 `font` 键，见 `devflow/custom-font-config.md`） |

**动手前先自问**：原 app 在 `/res` 下带了哪些“运行期才需要”的东西？（字库 / 配置文件 / 二进制工具）→ 全部搬进自己工程。
> 硬件层面的东西（如 BT 补丁固件）已收进组件，用户/AI 不需要关心（见 `components/`）。

**刷机后的核验手法**
```bash
# 装上去的是不是自己的 app
adb shell "busybox strings /res/lib/libzkgui.so | grep -i <你自己的关键字>"
# 关键资源在不在
adb shell "ls -l /res/font /res/bin/firmware/rtlbt; cat /res/etc/EasyUI.cfg"
# 界面验收：直接抓屏交给视觉模型（不要手搓 fb0）
```

## 三、实测坑（本机 2026-09-12 复现 + 修复验证）

> 验证记录（2026-09-12）：装 **VC++ 2015-2022 Redistributable (x86)** 后，
> `C:\zkswe\fun\tools\fsimg.exe` 可正常启动（该 exe 实为签名工具 `fssign`，
> 用法 `fssign [-i <name:path>]... -p <platform> -o <file>`），
> 端到端出包成功：`fun pack -p V85X` → `.fun/v85x/update.img`（84.6 KB，LunarCalendarDemo）。
> 结论：**Windows 上做固化升级，VC++ x86 运行库是硬前置**。

| 现象 | 根因 | 处理 |
|---|---|---|
| `FATAL sign error: exit status 0xc0000135`（或 `0xc000007b`） | 打包/签名用的 `fsimg.exe` 是 **32 位**程序，系统只装了 x64 VC++ 运行时（缺 32 位 `msvcp140.dll` / `vcruntime140.dll`）；0xc0000135=找不到 DLL，0xc000007b=位数不匹配 | **已修复**：装「Visual C++ 2015-2022 Redistributable **(x86)**」（需管理员，装完 `C:\Windows\SysWOW64\msvcp140.dll` 存在即 OK）；无管理员权限时退路是把 32 位这两个 dll 放到 `C:\zkswe\fun\tools\`（`fsimg.exe` 同级） |
| `FATAL generate error: package ini@0.0.1 not found in local` | 工程依赖没装（`fun install` 未跑或没跑完） | 先 `fun install` 再 pack |
| 出包成功但设备没变化 | 把 update.img 放在了卡的非根目录，或卡不是 FAT32 | 卡格式化 FAT32，文件放根目录，插卡重上电 |

> 工具侧已把前两条映射为可执行 `hint` 返回（`flythings_pack_upgrade` 的 `PACK_ERR_HINTS`）。

## 四、排查用到的定位手法（可复用）

- fun 的“家目录”由环境变量决定：本机 `FLYTHINGS_FUN_DIR` / `FUN_HOME_PATH` = `C:\zkswe\fun`，
  下载的打包工具落在 `C:\zkswe\fun\tools\`（`fsimg.exe`、`make-fs/make-fs.exe` 等）；
- 判断某个 exe 是不是 32 位：读 PE 头 `Machine`（`0x14c`=x86，`0x8664`=x64）；
- 进程起不来报 `0xC0000135` = DLL 找不到（本机缺 32 位 MSVC 运行时），
  `0xC000007B` = 镜像/位数不匹配（拿 x64 dll 喂 32 位程序）；
- 历史产物长什么样：`.fun/<平台>/update.img`（旧工程里能看到既有成功产物）。
