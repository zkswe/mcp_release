---
id: devflow-selfcheck-and-bugreport
title: 整机自检（selfcheck）与缺陷单（bugreport）口径
category: devflow
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [Z20]
tags: [提缺陷, 缺陷单, bug 报告, bugreport, 现象与复现步骤, 真机判据]
evidence: []
---
# 整机自检（selfcheck）与缺陷单（bugreport）口径

> 检索导引：整机自检 / selfcheck / 九分区快照 / 一次把设备状态全抓一遍 / 与上次快照对比 / 现场体检报告 /
> 提缺陷 / 缺陷单 / bug 报告 / bugreport / 现象与复现步骤 / 真机判据 / 严重级 / 证据清单 /
> 读不到是结论 / 设备缺 busybox / logcat 取证。
> 用途：`flythings_selfcheck` 与 `flythings_bugreport` 的完整口径（两个工具的 docstring 只留要点，
> 长尾细节与"读不到怎么办"在这里）。
> 版本：2026-09-29（v0.27.123-open 首次入库；已在 SSD20X / Z20 面板做**只读真机抽查**，
> 仍然只有静态判据的部分见 §6，不冒充实测）。

## 1. 什么时候用

| 场景 | 用哪个 |
|------|--------|
| 「这块板现在什么状态？」「开机后到底起没起？」「网络/存储/时间到底哪不对？」 | `flythings_selfcheck`（一条命令出九分区快照） |
| 「上次还好好的，现在变了没有？」 | `flythings_selfcheck(diff_against=<上次快照.json>)` |
| 「把这个 bug 记下来，我要提交给厂家/同事」 | `flythings_bugreport`（落成可提交 markdown） |
| 「我要先把现场留证」 | `flythings_selfcheck(out=<json>)` + `flythings_device_screenshot()` + `flythings_bugreport(evidence=[...])` |

与相邻工具的边界：**抓屏看画面** = `flythings_device_screenshot`；**像素级差异** =
`flythings_ui_visual(action="diff")`；**布局层叠/触摸穿透** = `flythings_layout_audit`。
selfcheck 只看"设备本身的状态读数"，不看画面内容。

## 2. 九分区（selfcheck）

每分区返回 `{ok, hint, data, items[], notes[]}`：

- `ok` —— 该分区的**采集判据**（见下表"ok 判据"列）。
- `hint` —— `ok=false` 时才有：**需要什么条件、去哪查**。⚠️ **"读不到"本身是结论**，
  不是错误、也不许静默吞掉；看到 `ok=false` 先读 hint，别当成工具坏了。
- `data` —— 规范化后的读数（型号/平台/挂载表/路由/IP/继电器键…）。
- `items` —— 逐条取证：`{name, cmd, ok, raw}`，`cmd` 就是设备侧实际执行的命令，
  可原样复现（排障时先看 `raw` 是否为空、`cmd` 里有没有多余输出）。
- `notes` —— 该分区的补充说明（例如"可见高≠fb 文件行数"）。

| # | 分区 | 采集项（主要） | ok 判据 | 读不到时（hint 摘要） |
|---|------|----------------|---------|------------------------|
| ① | 设备信息 | `ro.product.model`、`/proc/version`、`ro.easyui.version`、`ro.build.fingerprint` | 型号或内核非空 | 确认设备在线且 `ro.product.model` 没被裁剪；平台靠 `device_models.json` 反查，**未命中就留空**（用 `flythings_hardware_info` 查规格，不许猜） |
| ② | 应用状态 | `init.svc.zkswe`、`sys.zkapp.state`、`sys.zkapp.dbg`、`pidof zkgui`、`/proc/uptime` | 服务态或 pid 有值 | 重启应用一律 `setprop ctl.restart zkswe`（**不要 kill**，应用由类 init 服务托管，见 `device-deploy-budget.md`） |
| ③ | 显示 | `fb0/{virtual_size,bits_per_pixel,stride,pan}`、EasyUI.cfg 的 `rotateScreen`/`rotateTouch` | fb 三项任一有值 | 板子可能没有 fb0（走 MI 显示通道）；旋转口径按 `/tmp` > `/mnt/extsd` > `/res/etc` 顺序找 EasyUI.cfg |
| ④ | 存储 | `/proc/mounts`（/res、/data…只读性）、`ls /mnt`、`df -k /tmp`、`df -k /data`、`ls /res/ui` | 挂载表解析出条目 | `/proc/mounts` 不依赖 busybox；`/res` 多为只读 squashfs（调试推 `/tmp`，固化才落盘）；`/tmp` 是 tmpfs，撑爆会 OOM 杀 zkgui |
| ⑤ | 网络 | `/sys/class/net/wlan0/address`、`ifconfig wlan0`、`/proc/net/route`（默认路由）、`/etc/resolv.conf`、`/data/misc/wifi/wpa_supplicant.conf` | 任一有值 | 读不到 wlan0 = 可能没 WiFi 模组（先看 `/proc/net/dev` 的接口名）；无默认路由 = 没联网 |
| ⑥ | 蓝牙 | `getprop` 里的 bt/bluetooth 属性、`/sys/class/rfkill/rfkill0/{name,state}`、`/dev/hci*` | 任一有值 | **`ok=false` 常常就是结论**：没插 AIC USB BT 模组（或模组没起 hci）；要用蓝牙看 `components/ble` + `gatt` 包 |
| ⑦ | 输入 | `ls /dev/input`（需 busybox）、`/proc/bus/input/devices`（触摸设备名） | 节点或设备表非空 | `/proc/bus/input/devices` 不依赖 busybox；注入测试用随仓 `bin_tools/<平台>/touch`（先 `touch list`） |
| ⑧ | 外设 | `/data/preferences.json`（继电器/过零 IO 键） | 偏好文件是 JSON 且有 relay/zero/io 键 | 偏好文件**应用没写过就没有**，`ok=false` 属常态；继电器走 `zkhardware` 包（`zeroOutput`/背光） |
| ⑨ | 时间 | `date`、`date +%s`、`persist.sys.timezone`、`ntpd/ntpdate` 是否存在 | date 或 epoch 有值 | 设备 `date` 被裁剪 → 自动退 `busybox date`；`driftSeconds` = 设备 − 宿主，**NTP 是否可用不替你判断**（本分区只给偏差）；偏差大时先让设备把时间对上再验需要时间正确的功能（相关坑见 `package-verify-playbook.md`） |

### 2.1 采集的工程口径（为什么这么写）

- **容忍设备缺工具**：设备 rootfs 是裁剪版（没有 `grep`/`head`/`dd`/`md5sum`）。工具**优先**用
  随仓 `bin_tools/<平台>/busybox`（`adb_tools.ensure_busybox()` 会复用设备上已有的 `/tmp/busybox`，
  没有就推一份过去），否则退化成纯 `adb shell` + `getprop` / `cat`。
  `items[].ok=false` + note 里会写明"需要 busybox"。手工补：`adb push bin_tools/<平台>/busybox /tmp/busybox` + `chmod 777`。
- **设备参数带端口**：`device='<serial|IP>:5555'`。给了 `IP:5555` 但不在 `adb devices` 列表里 → 工具先
  `adb connect <IP>:5555` 再探（返回体 `connectNote` 记录结果）。
- **多台在线绝不猜**：不传 `device` 且在线 >1 台 → `NO_DEVICE` + 在线清单（`serial(model)`），
  因为多设备下厂商 CLI 会静默取第一个。零台 → `NO_DEVICE` + 安装/接线提示。
- **端口别记错**：设备网络 adb 端口常见 `5555`；本板串口/调试口的波特率口径不在本工具范围（看平台文档）。

## 3. diff 与落盘

```json
{"ok": true, "op": "flythings_selfcheck", "device": {"serial": "...", "model": "...", "platform": "..."},
 "sections": {"device": {"ok": true, "hint": "", "data": {...}, "items": [...], "notes": [...]}, "...": {}},
 "summary": {"total": 9, "ok": 6, "failed": 3, "failedSections": ["bluetooth", "input", "peripheral"]},
 "outPath": "<落盘路径，未传 out 时为空串>"}
```

- `out=<json 路径>`：把**整个快照**（含九分区 data/items）落盘，可留证、可当基线。
- `diff_against=<上次快照.json>`：逐分区逐项比对，`diff.sections[].status ∈ changed|same|added|removed`，
  `diff.sections[].items[]` 给 `{key, before, after}`（键形如 `data.model`、`probe.pid`、`__ok`）。
  **天然会变的读数**（`uptimeSeconds` / `date` / `epoch` / `hostEpoch` / `driftSeconds` / df 空间 /
  ifconfig 输出）不进 changed 判定，单独放 `sections[].volatileItems` 与 `summary.volatileItems`
  （仍逐条列出 before/after；唯一维护处 = `selfcheck_tools._VOLATILE_KEYS`）——否则连跑两次
  必然报几个分区 changed（真机实测：uptime/时间/df/wlan0 计数），差异信号会被噪声淹没。
  逐项一致时会往 `warnings` 里写一句「与基线快照逐项一致」——**没有差异也是结论**。
- 基线文件不存在 → `DIFF_BASE_MISSING`（可重试，hint 让你先跑一次带 `out` 的 selfcheck）；
  基线不是合法 JSON → `DIFF_BASE_BAD`。两种情况都**不会丢掉本次快照**（返回体里仍带 `sections`）。

## 4. 缺陷单（bugreport）

### 4.1 产出结构（对齐 2026-09-27 html2json A1~A8 那批缺陷单）

```
# <title>
- 日期 / 平台 / 项目 / 设备 / 严重级 / 生成来源
## 现象
## 复现步骤        （steps 传 JSON 数组或换行/分号分隔，自动编号）
## 期望 vs 实际
## 真机判据        （自动采集，见 4.2）
## 证据            （evidence 逐条列 + 是否存在的判定）
## 影响面 / 建议
```

默认落 `<project_root>/temp/bugreports/<yyyymmdd-HHMM>-<slug>.md`（没传 `project_root` 就落
`<MCP 仓库>/temp/bugreports/`）；返回 `{path, preview(前 20 行), lines, judgement, affectedFiles}`。

### 4.2 真机判据（自动附）

连得上设备时自动采：型号 / 固件（`ro.easyui.version` 或内核首行）/ `ro.build.fingerprint` /
`init.svc.zkswe` / `sys.zkapp.state` / `zkgui pid` / `/proc/uptime`，外加
**最近 `logcat -d -s zkgui` 末 40 行**（每行截 200 字符）。

- 采 logcat 的口径：`-s zkgui` 只留应用 tag（网络类事件线程会刷屏把日志挤出缓冲，见
  `package-verify-playbook.md`）；没有输出时**写明原因**而不是留空。
- **连不上设备 / 设备不可定位**：markdown 里写「未采集到真机数据 + 原因 + 怎么补采」，
  并在返回体 `warnings` 里同步一条。缺陷单照样产出（可能是静态分析出来的缺陷）。
- `device` 的口径与 selfcheck 完全一致（带端口、多台不猜）。

### 4.3 纪律

- **证据文件必须真实存在**：`evidence` 里任一路径不存在 → 直接回 `EVIDENCE_MISSING`
  （列出缺哪些、hint 让你先落盘证据），**不静默跳过、不写出半真半假的单子**。
  先出框架稿就不传 `evidence`。
- `severity ∈ blocker|critical|major|minor|trivial`（缺省 `major`）；给了别的值 → 按 `major` 记 + `warnings` 说明。
- `title` 必填（其余都有默认值）；空 title → `BAD_PARAMS`（**不落盘**，避免产生无名文件）。
- `project_root` 只用来决定落盘位置 + 反查平台（扫 `.fsc/<平台>` / `.fun/<平台>` 目录名）；
  不传也不会失败，只是平台列「（未采集）」。

## 5. 建议登记的检索问法（给 `scripts/check_retrieval.py`）

> ⚠️ `check_retrieval.py` 由沛哥维护，本文件只给建议，**不改那个脚本**。建议登记 5 条
> （括号内为期望命中的权威文档）：

1. 「设备的整体状态怎么看？有没有一条命令出一份完整快照」（→ 本文）
2. 「怎么把设备现在的状态和上次比一比，看什么变了」（→ 本文 §3）
3. 「我要给厂家提个缺陷单，要用什么格式、怎么写复现步骤」（→ 本文 §4.1）
4. 「蓝牙那栏显示 ok=false 是工具坏了吗」（→ 本文 §2 ⑥ + §2.1「读不到是结论」）
5. 「提缺陷单要附证据，文件不存在会怎样」（→ 本文 §4.3）

## 6. 已知边界（哪些只有静态判据 / 未真机验证）

本版（v0.27.123-open）**已在真机抽查**（SSD20X / Z20 面板，只读命令，未做任何设备侧写入）：
九分区 **8/9 ok**（`bluetooth` ok=false 属正确结论——板上没插 BT 模组）；
`diff`（同设备连跑两次：**0 changed** + 7 条 volatileItems）与 `bugreport` 端到端跑通
（缺陷单里的真机判据、logcat 摘要都落到了文件里）。

仍然只有静态判据（**未在真机验证**）的部分：

- ⑥蓝牙为 ok=true 的**正向**分支（rfkill/hci 路径真能读到什么）没有实机样例，
  真机上只验到「没插模组 → ok=false + hint」；③`rotateScreen`/`rotateTouch` 解析未命中（该板
  EasyUI.cfg 里没有这两个键，走的是缺省），多平台写法未逐平台核对；
- ⑦输入只验到 `gt9xx`；其它触摸驱动（axs_ts / ft5x / goodix）名字是否被 `touchDevices` 认出未逐板验证；
- ①`ro.easyui.version` 在该板上为空（hint 已写明），哪些平台真的带这个属性未穷举；
- **`diff` 的跨版本/跨固件差异清单**仍未验（只验了同设备连跑两次：0 changed + 4 条 volatile）；
- `bugreport` 的 `logcat -d -s zkgui` 摘要：Z20 上拿到了输出，但**哪些板子根本没有 logcat** 未穷举。
- 结论口径：**遇到 `ok=false` 先读 hint**；hint 说"需要 busybox"就先推 busybox 再跑一次，
  说"没有该模组"就是结论（不用再折腾）。
