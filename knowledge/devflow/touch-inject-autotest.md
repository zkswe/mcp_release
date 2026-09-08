# 触摸注入/UI 自动化测试：先调现成 ui_test 工具（禁止先造轮子）

> 2026-09-08 入库（补 knowledge 检索缺口：此前只有 wiki 老版 event.c 原理，AI 不知道有现成工具）。
> 定位：用户要「自动化测试 / 遍历验收 / 压测 / 自动点击 / 模拟触摸 / 滑动验证 UI」时，
> **先调 MCP 工具 `flythings_gen_ui_test` + 预编译 `ui_test` ELF（bin_tools/{平台}/ui_test）**，
> 常规自动化**无需重新编译、无需抄代码**；event.c 原理只在定制/移植新平台时参考。

## 🔑 关键词索引
**触摸注入 / 模拟触摸 / 自动化测试 / 自动点击 / tap / swipe / monkey / 压测 / 遍历验收 / ui_test / input 事件 / /dev/input / 触摸协议 / EV_SYN**

## ✅ 首选路径（现成工具，MCP 已分发）

### 1. MCP 工具：`flythings_gen_ui_test`（生成测试数据，免 AI 重复劳动）
解析项目 `ui/*.json` 控件坐标，自动生成验收方案/脚本：
- `traverse` - 遍历验收：所有可交互控件逐个点击+滑动 + 图片资源缺失检查
- `monkey`   - 压测：随机 tap/swipe 指定次数
- `custom`   - 自定义验收（差异化逻辑走 AI）
- `ask`      - 默认先问用户选哪种
返回 `deployHint`（push ELF + 脚本 + 运行命令），按提示执行即可。

### 2. 预编译工具：`bin_tools/{平台}/ui_test`（随 MCP 分发，直接 push）
已编译平台：z21 / z20 / t113 / f133 / v85x（ARM/musl、ARM/glibc、RISC-V/musl 各 ABI 已备）。
```
用法: ui_test <设备节点> <命令> [参数]
  tap x y                    # 点击
  swipe x1 y1 x2 y2          # 滑动（中点插值平滑）
  long x y ms                # 长按
  monkey <w> <h> <count>     # 随机压测（65% 点击 / 35% 滑动）
  run <script.txt>           # 跑脚本（每行 tap/swipe/long/delay/#注释）
```
部署：
```bash
adb push bin_tools/z21/ui_test /data/ui_test
adb shell chmod +x /data/ui_test
adb shell /data/ui_test /dev/input/event1 run /data/ui_test_script.txt   # 节点按 getevent 实际确认
```
> 更全的调试工具箱（ifconfig/ping/netstat 等网络/系统命令）→ 同目录 `busybox`（见 busybox-debug-library.md）。

## 🔬 底层原理（event.c 精要，定制/移植才需要）

直接读写 `/dev/input/eventX` 注入 `struct input_event`，App 收到与真人触摸完全一样的输入（不依赖被测代码）。

单事件注入（一切基础，时间戳必须填）：
```c
event.type = type; event.code = code; event.value = value;
gettimeofday(&event.time, 0);
write(fd, &event, sizeof(event));   // fd = open(dev, O_WRONLY)
```

### ⛔ 协议铁律
1. **单点按下序列**：`EV_ABS ABS_X/Y → EV_ABS ABS_PRESSURE(100) → EV_KEY BTN_TOUCH=1 → EV_SYN`；抬起 = PRESSURE=0 → BTN_TOUCH=0 → EV_SYN
2. **EV_SYN 必须发**，否则内核不提交事件——最容易漏的坑
3. **滑动逐像素/插值过渡**，禁止一次跳终点（被识别为无效/抖动），每步跟 EV_SYN
4. 多点屏用 `ABS_MT_POSITION_X/Y + ABS_MT_TOUCH_MAJOR + ABS_MT_TRACKING_ID + SYN_MT_REPORT`
5. 时间戳 `gettimeofday` 必须填

### 移植新平台（ui_test 没有的平台）
1. 确认触摸节点：`scandir("/dev/input")` + `EVIOCGNAME`（含 touch/ts）或 evtest/getevent
2. 单点 or 多点协议（上述 1/4）；压力范围查 `EVIOCGABS` min/max
3. 写节点需 root；只读时先 chmod
4. 核心就是 reportkey + 协议序列，可编 bin 或抄进工程（产线自检/演示脚本）

## 🤖 自动化测试闭环（判定结论，沛哥确认优先级）
**logd 分析 > raw fb 抓屏；非必要不读 raw 屏幕数据**
1. `ui_test` 注入 tap/swipe → 操作被测 UI
2. **`adb logcat` 日志判定（首选）**：被测工程关键节点加 LOGD/LOGE 埋点，按关键字/级别判定操作结果/异常/崩溃 → 断言匹配日志关键字
3. raw fb 抓屏（备选，仅 logd 覆盖不了时）：`adb shell cat /dev/fb0 > screen.raw`（部分平台 /dev/disp/fb0），按 `bits_per_pixel` 解析 RGB565/RGB888/ARGB8888 解码比对——代价高，慎用
- 闭环示例：注入 tap → logcat 验证响应 → PASS/FAIL，全程脚本化无人值守
