# bin_tools — FlyThings 通用预编译工具（电脑端编译，MCP 独立存放）

> 架构（2026-08-31 确认）：通用工具（触摸注入 ui_test、将来 busybox 等）在**电脑端预编译成各平台 ELF**，
> 放本目录 `{平台}/工具名`，一次编译处处复用。MCP 工具生成测试项目时只产出**数据文件**（脚本/参数），
> 不再现场编译——tools 不膨胀、生成秒级。
> ⚠️ 本目录只保留**可执行 ELF + 调用方法**，不存放 C 源码（源码由 FlyThings 工具链维护）。

## 📦 现有工具与平台

| 工具 | 用途 | 平台 |
|------|------|------|
| **`touch`**⭐ | **统一触摸注入（推荐）**：自动扫描触摸节点 + 自动判协议（单点 / MT-A / MT-B），**部署命令不带 `/dev/input/eventN`**；命令 tap/swipe/long/monkey/run/record/play + list/info。2026-09-12 新增，源码 `tools/touch_inject/` | z21 / z20 / t113 / f133 / f135 / v85x |
| `ui_test` | 触摸注入/自动化测试（tap/swipe/long/monkey/run 脚本，**单点协议**适配老屏）——**兼容保留**，需人工给节点 | z21 / z20 / t113 / f133 / v85x |
| `busybox` | 设备调试工具箱（网络/系统/Shell 全开，2026-09-08 新增） | z21 / z20 / t113 / f133 / f135 / v85x |
| `zkshot` | 设备端抓屏（**SigmaStar 视频层**；配合 `flythings_device_screenshot(layer="video")`） | z21 / z20 |

> 📌 **`mt_test` 已于 2026-09-30 移除**（二进制归档到工作区 `archive/mcp_mt_test_20260930/`）：
> `touch` 自动扫描触摸节点 + 自动判协议（单点 / MT-A / MT-B）已完整覆盖其能力，**MT 屏一律用 `touch`**。
> `ui_test` 保留（体积小、兼容老屏，需人工给节点）。

全部 ELF 已验证魔数 `7F 45 4C 46`，直接 `adb push` 即可运行（无需宿主 zkgui）。

**平台匹配（唯一规则）**：二进制按**目标平台**放，架构不对会静默失败/打崩应用——
所以**不许拿别平台的 ELF 顶替**。架构由 `scripts/check_consistency.py::stage_bin_tools()`
读 ELF 头核（`arm`→ELF32/ARM、`riscv64`→ELF64/RISC-V），放错直接红。
**不要**为此做「一份二进制 + 平台映射」的间接层：按平台各放一份是对的，重复副本也**不是**体积问题——
相同内容的副本 git 只存一份 blob，只差构建时间戳的（如 f133/f135 的 busybox）git 会压成几十字节的 delta
（实测：1101048 B 的两份，pack 里是 1 份全量 + 1 个 **53 字节** delta）。

## 🔧 触摸协议速判（**先用 `touch`，它会自己判**）

> ⭐ **首选 `touch`**：不传设备节点，自动扫 `/dev/input` 找触摸节点、自动判协议（MT-B / MT-A / 单点）。
> 先跑一条 `adb shell /data/touch list` 就能看到节点+协议清单——**不用再"试注入一次看是否恒 0"**。
> 下面这套手动速判方法保留给：`touch` 在该平台缺失、或需要人工核验时用。

注入前先判断设备触摸屏是单点协议还是 **MT Type-A 协议**，用错协议 → 驱动丢弃坐标 → FlyThings 收到恒 `x=0 y=0`：

```bash
# 方法 1：能力位（设备 root 后）
adb shell "cat /sys/devices/virtual/input/input*/capabilities/abs | xxd | head -1"
# 找 ABS code 53(0x35)=ABS_MT_POSITION_X → 有则 MT；只 0/1=ABS_X/ABS_Y → 单点

# 方法 2：getevent -p（如果有）
adb shell getevent -p /dev/input/eventN
# 看 ABS 列表有没有 ABS_MT_POSITION_X/Y

# 方法 3：试注入一次，看 FlyThings 日志
adb shell /data/touch tap 100 100                 # touch 自动判协议（命令不带 eventN）
adb shell ui_test /dev/input/eventN tap 100 100   # 单点协议（兼容工具，需人工给节点）
# FlyThings 收到坐标非 0 = 协议对；恒 0 = 协议错
```

| 屏幕类型 | 典型驱动 | 工具 |
|---|---|---|
| 单点（旧电阻屏/部分电容） | ili210x、ADS7846 等 | `touch`（自动） / `ui_test` |
| MT Type-A 多点（**gt9xx 主流**） | gt9xx、Goodix 系列 | `touch`（自动；人工核验可 `touch --proto a`） |
| MT Type-B 多点（slot 协议） | 部分新驱动 | `touch`（自动） |

V553 实测（2026-09-08）：`/dev/input/event0` = gt9xx MT Type-A，`ui_test` 注入坐标恒 0，改 `mt_test`（**2026-09-30 已移除**，能力由 `touch` 自动判协议覆盖）后坐标正确 —— 当时只能靠试；**现在 `touch` 会自己判成 MT-A**。

## 🔧 busybox 调用方法（设备没 ifconfig/ping 等工具时用它）

```bash
# 选对应平台 push（f133/f135=RISC-V，z20/z21=ARM glibc，t113/v85x=ARM musl）
adb push bin_tools/z21/busybox /tmp/busybox
adb shell chmod 777 /tmp/busybox

# 前缀式调用（busybox <命令>）
adb shell /tmp/busybox ifconfig                # 查 IP
adb shell /tmp/busybox ping -c 3 192.168.1.1   # 连通性
adb shell /tmp/busybox netstat -tulnp          # 端口监听
adb shell /tmp/busybox ps w / top / free / dmesg

# 软链成常规命令（可选）
adb shell "for c in ifconfig ip ping netstat route ps; do ln -sf /tmp/busybox /tmp/$c; done"
```

> BusyBox v1.36.1，全平台 CONFIG_STATIC=y 静态链接（push 即用零依赖）。
> 重编：`wsl bash ../../scripts/bb_build_all.sh all`（源码/坑位见 `tools/busybox/README.md`，构建必须 WSL 原生盘）。

## 🎯 touch 调用方法（⭐ 首选，自动识别节点+协议）

```
用法: touch [设备节点] <命令> [参数]        # 设备节点可省略（自动识别）

  list                       # 列出 /dev/input 全部设备 + 协议判定（排查第一步）
  info [dev]                 # 选中设备的能力位/量程/协议详情
  tap x y [-r n]             # 点击
  swipe x1 y1 x2 y2 [-r n]   # 滑动
  long x y ms                # 长按
  monkey w h count [--no-swipe]  # 随机压测
  run <script.txt>           # 跑脚本（tap/swipe/long/delay/hold）
  record <file> / play <file> [-r n] [-s speed]   # 录制/回放

选项: -d/--dev 指定节点 | --proto single|a|b 手动覆盖 | --hold ms 按下保持
      --scale 屏幕坐标→ABS 量程换算 | -q 少打印
```

### 部署运行（示例 z20）
```bash
adb push bin_tools/z20/touch /data/touch && adb shell chmod +x /data/touch
adb shell /data/touch list                       # 先看节点+协议
adb shell /data/touch tap 100 200                # 直接注入，无需 eventN
adb shell /data/touch run /data/ui_test_script.txt
# 运行同时 adb logcat 观察 [TOUCH] 与业务日志
```
> 自动判协议：`ABS_MT_SLOT` → MT-B；`ABS_MT_POSITION_X` → MT-A；否则单点。
> 源码/自测/重编：`tools/touch_inject/`（`wsl bash scripts/touch_build_all.sh all`）。

## 🎯 ui_test 调用方法（兼容保留，需人工给节点）

```
用法: ui_test <设备节点> <命令> [参数]

  tap x y                    # 点击 (x,y)
  swipe x1 y1 x2 y2          # 滑动（中点插值平滑）
  long x y ms                # 长按 (x,y) 持续 ms 毫秒
  monkey <w> <h> <count>     # Monkey 压测：随机 tap/swipe count 次（65% 点击 / 35% 滑动）
  run <script.txt>           # 执行脚本文件（每行一条指令，见下）

脚本格式（run）:
  # 注释（建议写控件名/页面，便于 logcat 对应）
  tap 192 207
  swipe 100 200 800 600
  long 400 300 1500
  delay 500
```

### 部署运行（示例 z21）
```bash
adb push bin_tools/z21/ui_test /data/ui_test
adb shell chmod +x /data/ui_test
# 遍历验收（脚本由 flythings_gen_ui_test 生成）
adb push ui_test_script.txt /data/
adb shell /data/ui_test /dev/input/event1 run /data/ui_test_script.txt
# Monkey 压测
adb shell /data/ui_test /dev/input/event1 monkey 1024 600 500
```
> 设备节点按实际 `getevent` 确认（触摸屏是 ABS_MT_* 那路）；运行同时 `adb logcat` 观察 `[UITEST]`/`[MONKEY]` 与业务日志。

### 触摸协议（注入原理）
```
按下: EV_ABS ABS_X/Y → ABS_PRESSURE → EV_KEY BTN_TOUCH=1 → EV_SYN
移动: EV_ABS ABS_X/Y 逐点（中点插值）→ EV_SYN
抬起: ABS_PRESSURE=0 → BTN_TOUCH=0 → EV_SYN
```
⚠️ EV_SYN 必须发，否则内核不提交事件；滑动禁止跳终点（会被识别为无效/抖动）。

## 🎯 MT Type-A 协议要点（对接知识；`mt_test` 已移除）

> `mt_test` 已于 **2026-09-30 移除**（`touch` 自动判协议覆盖其能力）。下面这套 MT-A 事件序列是**对接/核验知识**，
> 不是某个工具的用法；需要人工指定协议时用 `touch info` 看能力位、`touch --proto a tap x y` 注入。

### 协议铁律（MT Type-A）
```
按下: EV_ABS ABS_MT_TRACKING_ID(递增) → ABS_MT_POSITION_X/Y → ABS_MT_TOUCH_MAJOR
     → EV_KEY BTN_TOUCH=1 → EV_SYN
移动: EV_ABS ABS_MT_POSITION_X/Y 逐点 → EV_SYN
抬起: ABS_MT_TRACKING_ID=-1 → BTN_TOUCH=0 → EV_SYN
```

### 单点 / MT-A / MT-B 的注入差异（用错 → 坐标恒 0）
- **单点**：`ABS_X/Y + ABS_PRESSURE + BTN_TOUCH`（老电阻屏/部分电容屏）——`ui_test` 走这条
- **MT Type-A**：`ABS_MT_POSITION_X/Y + ABS_MT_TRACKING_ID`，靠 `SYN_MT_REPORT` 分隔点位（gt9xx 主流）
- **MT Type-B**：有 `ABS_MT_SLOT`，抬起帧须同帧带 `TRACKING_ID=-1`（**不能**发 `SYN_MT_REPORT`）

`touch` 会自动判成单点 / MT-A / MT-B（`touch list` 一步核验），**不必再按屏型挑工具**；协议用错 → 驱动丢弃坐标 → FlyThings 收到恒 0（判定见上方"协议速判"）。

## 🔧 新增平台/工具流程
1. 新平台：`fun create --type bin --platform <新平台>` + 放源码 `src/main.cpp`（ui_test 源码由工具链维护）
   → `fun build` → 产物 `.fun/{平台}/ui_test` → 复制到本目录 `{平台}/ui_test` → 更新 `test_tools.py` 的 `SUPPORTED_PLATFORMS`
2. 新工具（如 busybox）：同样 `fun create --type bin` 编译成 `{平台}/busybox`，MCP 工具直接引用
3. 交付客户：`adb push` 对应平台 ELF 即可，无需工具链/无需编译
