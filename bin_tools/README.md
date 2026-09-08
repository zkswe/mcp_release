# bin_tools — FlyThings 通用预编译工具（电脑端编译，MCP 独立存放）

> 架构（沛哥 2026-08-31 确认）：通用工具（触摸注入 ui_test、将来 busybox 等）在**电脑端预编译成各平台 ELF**，
> 放本目录 `{平台}/工具名`，一次编译处处复用。MCP 工具生成测试项目时只产出**数据文件**（脚本/参数），
> 不再现场编译——tools 不膨胀、生成秒级。
> ⚠️ 本目录只保留**可执行 ELF + 调用方法**，不存放 C 源码（源码由 FlyThings 工具链维护）。

## 📦 现有工具与平台

| 工具 | 用途 | 平台 |
|------|------|------|
| `ui_test` | 触摸注入/自动化测试（tap/swipe/long/monkey/run 脚本） | z21 / z20 / t113 / f133 / v85x |
| `busybox` | 设备调试工具箱（网络/系统/Shell 全开，2026-09-08 新增） | z21 / z20 / t113 / f133 / f135 / v85x |

全部 ELF 已验证魔数 `7F 45 4C 46`，直接 `adb push` 即可运行（无需宿主 zkgui）。

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

## 🎯 ui_test 调用方法

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

## 🔧 新增平台/工具流程
1. 新平台：`fun create --type bin --platform <新平台>` + 放源码 `src/main.cpp`（ui_test 源码由工具链维护）
   → `fun build` → 产物 `.fun/{平台}/ui_test` → 复制到本目录 `{平台}/ui_test` → 更新 `test_tools.py` 的 `SUPPORTED_PLATFORMS`
2. 新工具（如 busybox）：同样 `fun create --type bin` 编译成 `{平台}/busybox`，MCP 工具直接引用
3. 交付客户：`adb push` 对应平台 ELF 即可，无需工具链/无需编译
