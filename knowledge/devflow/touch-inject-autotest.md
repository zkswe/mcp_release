---
id: devflow-touch-inject-autotest
title: 触摸注入/UI 自动化测试：先调现成 `touch` 工具（禁止先造轮子）
category: devflow
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [F133, F135, Z20, Z21, T113, V85X]
tags: [2026-09-08 入库, c 原理, AI 不知道有现成工具, 2026-09-12 升级, 沛哥实测反馈, ui_test, 节点要人工传, 自动扫节点 + 自动判协议, 并全平台编译, 自动化测试]
evidence: []
---
# 触摸注入/UI 自动化测试：先调现成 `touch` 工具（禁止先造轮子）

> 检索导引：问「要自动化测试/压测/遍历验收 / 模拟点击滑动怎么注入 / 触摸节点和协议怎么定 / 有没有现成工具别再造轮子」→ 本文（统一 `touch` ELF + `flythings_gen_ui_test`；英文命中词见上方「🔑 关键词索引」）。
> 2026-09-08 入库（补 knowledge 检索缺口：此前只有 wiki 老版 event.c 原理，AI 不知道有现成工具）。
> **2026-09-12 升级（沛哥实测反馈）：老 input / ui_test / mt_test 存三个硬伤——单点协议写死、
> 节点要人工传、节点或 IC 一变就注入失败 → AI 只能反复 try。已新建统一工具 `touch`
> （自动扫节点 + 自动判协议）并全平台编译。**
> 定位：用户要「自动化测试 / 遍历验收 / 压测 / 自动点击 / 模拟触摸 / 滑动验证 UI」时，
> **先调 MCP 工具 `flythings_gen_ui_test` + 预编译 `touch` ELF（bin_tools/{平台}/touch）**，
> 常规自动化**无需重新编译、无需抄代码、无需猜节点与协议**；event.c 原理只在定制/移植新平台时参考。

## 🔑 关键词索引
**触摸注入 / 模拟触摸 / 自动化测试 / 自动点击 / tap / swipe / monkey / 压测 / 遍历验收 / touch / ui_test / mt_test / input 事件 / /dev/input / 触摸协议 / EV_SYN / 坐标恒 0 / 节点自动识别 / 系统键盘盖住界面 / 导航键全部无效 / 收键盘 / 瞬态层单次抓帧 / toast 抓不到**

## ✅ 首选路径（现成工具，MCP 已分发）

### 1. MCP 工具：`flythings_gen_ui_test`（生成测试数据，免 AI 重复劳动）
解析项目 `ui/*.json` 控件坐标，自动生成验收方案/脚本：
- `traverse` - 遍历验收：所有可交互控件逐个点击+滑动 + 图片资源缺失检查
- `monkey`   - 压测：随机 tap/swipe 指定次数
- `custom`   - 自定义验收（差异化逻辑走 AI）
- `ask`      - 默认先问用户选哪种
返回 `deployHint`（push ELF + 脚本 + 运行命令），按提示执行即可。

### 2. 预编译工具：`bin_tools/{平台}/touch` ⭐ 首选（2026-09-12 新增）

> **一句话：不传节点、不选协议，`touch` 自己搞定。** 取代 ui_test/mt_test 二选一的试错。
>
> **为什么会有这个工具**：老 `input`（LearningProject/input）只实现单点协议（ABS_X/Y +
> ABS_PRESSURE + BTN_TOUCH），事件节点要人工传 `/dev/input/eventX`，且只预编译了 h500s/z21
> 两个老二进制 → 碰到 gt9xx 这类 MT 屏或节点编号不同的板子就注入失败（坐标恒 0），
> AI 只能反复换节点/试协议。`touch` 把这三件事全做成自动的。

```bash
# 0. 部署（平台目录按实际选）
adb push bin_tools/z20/touch /data/touch && adb shell chmod +x /data/touch

# 1. 排查第一步：list（列出 /dev/input 全部设备 + 协议判定）
adb shell /data/touch list
#   ★ /dev/input/event0  gt9xx-ts  proto=MT-A  mtX=0..799 mtY=0..1279 BTN_TOUCH
#     /dev/input/event1  gpio-keys （子设备，自动排除）
adb shell /data/touch info            # 能力位/量程/协议详情

# 2. 正常注入（节点/协议都不用传）
adb shell /data/touch tap 100 200
adb shell /data/touch swipe 100 600 700 600
adb shell /data/touch run /data/ui_test_script.txt
adb shell /data/touch monkey 800 1280 500
```

**自动识别逻辑**：遍历 `/dev/input/event*` → `EVIOCGBIT` 能力位筛（必须有 EV_ABS + 坐标轴；
名字含 touch/ts/gt9/panel 加分，含 keyboard/button/accel 扣分）→ `ABS_MT_SLOT` = MT-B，
`ABS_MT_POSITION_X` = MT-A，否则单点 → 注入时 MT 屏若同时声明 ABS_X/Y 就一并上报（兼容读单点轴的上层）。

**选项**：`-d/--dev` 指定节点、`--proto single|a|b` 手动覆盖、`--hold ms`（tap 按下→抬起，默认 40）、
`--scale`（屏幕坐标→ABS 量程换算）、`--no-swipe`、`record/play` 录制回放。

**能解决什么**：
- 节点编号不同（event0/1/2…）→ 自动扫，不用 getevent 猜
- IC/协议不同（单点 / MT-A / MT-B）→ 自动判，**不会再有「坐标恒 0」死循环**
- 平台缺 ELF → 已全平台编好（f133/f135/z20/z21/t113/v85x）

源码/自测/重编：`tools/touch_inject/`（`wsl bash scripts/touch_build_all.sh all`；
`list`/CLI/降级路径有 x86 自测脚本，真机行为需设备验证）。

---

### 3. 兼容保留：`ui_test`（单点）/ `mt_test`（MT Type-A）

> 仅在 `touch` 缺该平台 ELF、或需要人工核验协议时用；**新工作不要再用它们**。
>
> **⛔ 关键坑（2026-09-08 补，沛哥 V553 实测）**：`ui_test` 是**单点协议**
> （ABS_X/ABS_Y + BTN_TOUCH），只适配老电阻屏/单点电容屏。**V85X 设备的
> gt9xx 是 MT Type-A 协议**（MODALIAS `ra30,32,35,36,39` = ABS_MT_TOUCH_MAJOR
> /WIDTH_MAJOR/POSITION_X/POSITION_Y/TRACKING_ID），不订阅单点坐标轴——用
> `ui_test` 注入后**驱动丢弃坐标，FlyThings 收到恒 `x=0 y=0`**。
>
> 解决：MT Type-A 屏改用 `mt_test`（`ABS_MT_POSITION_X/Y + ABS_MT_TRACKING_ID`）。
> 接口与 ui_test 完全一致（tap/swipe/long/monkey/run），直接换工具名即可。

**协议速判**（注入前必看；**首选直接 `touch list` 一步到位**）：
```bash
# 方法 1：读能力位
adb shell "cat /sys/devices/virtual/input/input*/capabilities/abs | xxd"
# 有 ABS code 53(0x35)=ABS_MT_POSITION_X → MT 屏，用 mt_test
# 只有 0/1=ABS_X/ABS_Y → 单点，用 ui_test

# 方法 2：试注入一次（最快）
adb shell ui_test /dev/input/event0 tap 100 100
adb shell mt_test /dev/input/event0 tap 100 100
# FlyThings 收到坐标非 0 = 协议对；恒 0 = 协议错，换另一个
```

**工具清单**（前两行兼容保留）：

| 工具 | 协议 | 平台 |
|------|------|------|
| `touch` ⭐ | **自动**（单点/MT-A/MT-B） | z21 / z20 / t113 / f133 / f135 / v85x |
| `ui_test` | 单点 | z21 / z20 / t113 / f133 / v85x |
| `mt_test` | MT Type-A | z21 / z20 / t113 / v85x |
> 更全的调试工具箱（ifconfig/ping/netstat 等网络/系统命令）→ 同目录 `busybox`（见 busybox-debug-library.md）。
>
> `touch` 常用：**先 `touch check [x y]`**（一条命令自检：节点/协议/量程落点结论，给坐标则再注一次 tap；退出码 0=可用 / 3=无节点 / 4=有风险）、`touch list` / `touch info` / `touch [-d /dev/input/eventN] tap x y`；
> 触摸之外：`key <code> [ms]`（物理键，需 -d）· `sweep <from> <to> [ms]`（扫键码）· `raw t:c:v …`（原始事件）；
> 选项 `--proto single|a|b`、`--hold <ms>`、`--scale`、`--screen WxH`、`-v`（打印探测失败原因，`TOUCH_DEBUG=1` 同效）。

## 🖥 V85X 真机实录（2026-09-14，两块屏两种协议——都是"单点工具必死"）

| 板子 | 触摸节点 | IC | 协议 | `ABS_X/Y` | 结论 |
|------|---------|----|------|-----------|------|
| Zkswe_V85X_SPINOR（480×800） | `/dev/input/event0` | gt9xx | **MT-A**（48/50/53/54/57，无 SLOT） | **不存在** | `ui_test` 完全点不动；`touch` 自动判 MT-A ✅ |
| V851s（480×800，学习机 PocketGame） | `/dev/input/event4` | axs_ts | **MT-B**（有 SLOT+TRACKING_ID） | **范围 0..0** | MT-A 写法（老 `pginj`/`mt_test` 发 `SYN_MT_REPORT`）→ 整帧作废；按上面 2b 三条修后全通 |

**三条必须知道的坑（都踩过）**：
1. **`ABS_X/Y` 可能压根不存在**（V85X 两块屏都这样）：单点轴工具在这类屏上不是"偏"，是**完全点不动**（写了也被钳成 0）。判据：`touch info` 看 `ABS_X=0 ABS_Y=0` + `MT_POSITION_X=1`。
2. **声明的 MT 量程 ≠ 屏幕尺寸**：SPINOR 实测 `mtX=0..1024 mtY=0..600`、屏却 480×800；axs_ts 板 `mtX=0..480 mtY=0..960`、屏 480×800——**两块都实际 raw == 屏幕 1:1**（SPINOR 注 (437,32) 命中右上角按钮；axs_ts 注入日志回 `x=58 y=160` / `x=400 y=700` 逐点相符）。所以**别想当然加 `--scale`**：`touch check` 会把落点结论直接告诉你（量程≈屏 → 直接用；两轴比例一致且≠1 → 需换算；**两轴不一致 >5% → ⚠ 别用 --scale，先按 1:1 注一次看日志**），`--scale` 本身也会在同一口径下警告并取消换算；确需换算用 `--screen WxH` 指定真实尺寸。
3. **`EVIOCGBIT` 成功时不一定返回 0**：SPINOR 这颗内核返回**拷贝字节数（实测 4）**。写 `if (ioctl(...) == 0)` 会让能力探测永远失败 → `touch list` 报 "no input device found"（v0.27.61 修成 `>= 0`）。**移植任何 evdev 工具都按 `>= 0` 判成功。**

**宿主侧小贴士**：USB 设备在 `adb devices` 里消失/`offline` 时，先清掉所有 adb 进程再起（Windows：`taskkill /IM adb.exe /F` → `adb start-server`）——IDE 自带 adb 会抢占 5037 并留陈旧状态；SPINOR 实测就这样从"完全看不到"恢复成 `device`，**不用拔插**。

**✅ 2026-09-14 实测验收（axs_ts / MT-B 板，同一 USB 位）：** 用我们自己的 `touch` 跑通——
`tap 58 160` → 应用日志 `touch action=1 (58,160)` → `action=2 (58,160)`；
`swipe 240 600 240 250 24 12` → 一串 `action=3`（240,279→255 插值）+ `action=2 (240,250)`；
`raw 3:57:1 3:53:100 … 1:330:1 0:0:0` → `action=1 (100,100)`。
即：**MT-B 三铁律 + 「量程 0..0 不算可用」两条对齐后，我们的工具在这块屏上也能点**，不必依赖工程内自研注入器（`pginj.c`）。

**工具面已对齐工程内 `pginj.c` 的能力：** `touch [dev] key <code> [ms]`（物理键注入）· `sweep <from> <to> [ms]`（扫键码区间找真实键值）· `raw t:c:v [t:c:v ...]`（原始事件逃生口，末尾一次 SYN）；健注入不要求触摸节点（`gpio-keys` 之类没 ABS 也能用），但需 `-d` 指定节点（不自动挑触摸节点）。

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
2. **MT Type-A 序列**：`EV_ABS ABS_MT_TRACKING_ID(递增) → ABS_MT_POSITION_X/Y → ABS_MT_TOUCH_MAJOR → EV_KEY BTN_TOUCH=1 → EV_SYN`；抬起 = `ABS_MT_TRACKING_ID=-1 → BTN_TOUCH=0 → EV_SYN`
2b. **MT Type-B 三条（有 `ABS_MT_SLOT` 的屏，别拿 A 的写法套）**：
   - **绝不能发 `SYN_MT_REPORT`**：那是 type-A 的点位分隔符，B 设备上发它**整帧作废**（`dd` 能抓到事件、应用日志一行都没有）
   - **`BTN_TOUCH` 必须与位置同帧**：只发 MT 位置时框架给 DOWN+MOVE、**永远不给 UP** → 之后所有注入退化成 MOVE（现象像"时灵时不灵"）
   - **抬起帧同帧带 `TRACKING_ID=-1` + `BTN_TOUCH=0`**：缺了会留"幽灵手指"（判据：日志里只有 `action=3/2` 没有 `action=1`；再点一次或重启应用可恢复）
3. **EV_SYN 必须发**，否则内核不提交事件——最容易漏的坑
4. **滑动逐像素/插值过渡**，禁止一次跳终点（被识别为无效/抖动），每步跟 EV_SYN
5. 时间戳 `gettimeofday` 必须填
6. **协议用错 → 坐标恒 0**：注入后 FlyThings 收到 `(0, 0)` 几乎都是协议不匹配。**首选用 `touch`（自动判协议，直接绕开这个坑）**；若在用 ui_test/mt_test，才按上面"协议速判"切换。

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

---

## 📎 附录：mt_test.c 完整源码（MT Type-A 协议实现参考，V553 实测可用）

> mt_test 是 V553 项目 2026-09-08 自研（gt9xx 单点协议注入失效后写），入 MCP bin_tools 4 个平台（ARMv7 musl 72KB / ARMv7 glibc 4.5MB，RISC-V 暂缓）。源码不到 200 行，单文件可直接编。**移植/改版时优先改这里再重编**。

```c
/* mt_test.c — MT Type-A 协议触摸注入（适配 gt9xx 等 ABS_MT_* 多点屏）
 *
 * 用法: mt_test <dev> tap x y | swipe x1 y1 x2 y2 | long x y ms
 *                  | monkey w h count | run script.txt
 * 编译: arm-unknown-linux-musleabihf-gcc -static -O2 mt_test.c -o mt_test
 *       （musl/v85x+ t113；glibc/z20+z21 用 arm-pc-linux-gnueabihf-gcc）
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#include <sys/time.h>

struct input_event {
    struct timeval time;
    unsigned short type;
    unsigned short code;
    int value;
};

#define EV_SYN              0x00
#define EV_KEY              0x01
#define EV_ABS              0x03
#define SYN_REPORT          0x00
#define BTN_TOUCH           0x14a
#define ABS_MT_TOUCH_MAJOR  0x30
#define ABS_MT_POSITION_X   0x35
#define ABS_MT_POSITION_Y   0x36
#define ABS_MT_TRACKING_ID  0x39

static int g_fd = -1;
static int g_tracking = 0;

static int inject(unsigned short type, unsigned short code, int value) {
    struct input_event ev;
    memset(&ev, 0, sizeof(ev));
    gettimeofday(&ev.time, NULL);
    ev.type = type; ev.code = code; ev.value = value;
    return write(g_fd, &ev, sizeof(ev)) < 0 ? -1 : 0;
}

static void mt_down(int x, int y) {
    g_tracking++;
    inject(EV_ABS, ABS_MT_TRACKING_ID, g_tracking);
    inject(EV_ABS, ABS_MT_POSITION_X, x);
    inject(EV_ABS, ABS_MT_POSITION_Y, y);
    inject(EV_ABS, ABS_MT_TOUCH_MAJOR, 50);
    inject(EV_KEY, BTN_TOUCH, 1);
    inject(EV_SYN, SYN_REPORT, 0);
}
static void mt_move(int x, int y) {
    inject(EV_ABS, ABS_MT_POSITION_X, x);
    inject(EV_ABS, ABS_MT_POSITION_Y, y);
    inject(EV_SYN, SYN_REPORT, 0);
}
static void mt_up(int x, int y) {
    inject(EV_ABS, ABS_MT_POSITION_X, x);
    inject(EV_ABS, ABS_MT_POSITION_Y, y);
    inject(EV_ABS, ABS_MT_TRACKING_ID, -1);
    inject(EV_KEY, BTN_TOUCH, 0);
    inject(EV_SYN, SYN_REPORT, 0);
}
static void msleep(long ms) { usleep((useconds_t)(ms * 1000)); }

static void do_tap(int x, int y) {
    mt_down(x, y); msleep(50); mt_up(x, y);
}
static void do_long(int x, int y, long ms) {
    mt_down(x, y); msleep(ms); mt_up(x, y);
}
static void do_swipe(int x1, int y1, int x2, int y2) {
    mt_down(x1, y1);
    int steps = 12;
    for (int i = 1; i <= steps; i++) {
        int x = x1 + (x2 - x1) * i / steps;
        int y = y1 + (y2 - y1) * i / steps;
        mt_move(x, y); msleep(12);
    }
    mt_up(x2, y2);
}
static int run_script(const char *path) {
    FILE *fp = fopen(path, "r");
    if (!fp) return -1;
    char line[256]; int steps = 0;
    while (fgets(line, sizeof(line), fp)) {
        char *p = line;
        while (*p == ' ' || *p == '\t') p++;
        if (*p == '\n' || *p == '\r' || *p == '#' || *p == '\0') continue;
        char cmd[32]; int a=0,b=0,c=0,d=0;
        int n = sscanf(p, "%31s %d %d %d %d", cmd, &a, &b, &c, &d);
        if      (strcmp(cmd,"tap")==0   && n>=3) do_tap(a,b);
        else if (strcmp(cmd,"long")==0  && n>=4) do_long(a,b,c);
        else if (strcmp(cmd,"swipe")==0 && n>=5) do_swipe(a,b,c,d);
        else if (strcmp(cmd,"delay")==0 && n>=2) msleep(a);
        else continue;
        steps++;
    }
    fclose(fp);
    return 0;
}
static void do_monkey(int w, int h, int count) {
    srand((unsigned)time(NULL));
    for (int i = 0; i < count; i++) {
        int x = rand()%w, y = rand()%h;
        if (rand() % 100 < 65) do_tap(x, y);
        else do_swipe(x, y, rand()%w, rand()%h);
        msleep(120);
    }
}

int main(int argc, char **argv) {
    if (argc < 3) {
        printf("usage: %s <dev> tap x y | swipe x1 y1 x2 y2 | long x y ms | monkey w h count | run script.txt\n", argv[0]);
        return 1;
    }
    g_fd = open(argv[1], O_RDWR);
    if (g_fd < 0) { perror("open"); return 1; }
    const char *cmd = argv[2];
    if      (strcmp(cmd,"tap")==0    && argc>=5) do_tap(atoi(argv[3]),atoi(argv[4]));
    else if (strcmp(cmd,"swipe")==0  && argc>=7) do_swipe(atoi(argv[3]),atoi(argv[4]),atoi(argv[5]),atoi(argv[6]));
    else if (strcmp(cmd,"long")==0   && argc>=6) do_long(atoi(argv[3]),atoi(argv[4]),atol(argv[5]));
    else if (strcmp(cmd,"monkey")==0 && argc>=6) do_monkey(atoi(argv[3]),atoi(argv[4]),atoi(argv[5]));
    else if (strcmp(cmd,"run")==0    && argc>=4) run_script(argv[3]);
    else { printf("unknown: %s\n", cmd); return 1; }
    close(g_fd);
    return 0;
}
```

### 重编命令
```bash
# ARMv7 musl（v85x + t113）— 工具链 /d/zkswe/fun/toolchains/v85x/bin/
arm-unknown-linux-musleabihf-gcc -static -O2 mt_test.c -o mt_test   # 72KB

# ARMv7 glibc（z20 + z21）— 工具链 /d/zkswe/fun/toolchains/z21/bin/
arm-pc-linux-gnueabihf-gcc -static -O2 mt_test.c -o mt_test         # 4.5MB（glibc 静态链特性）

# RISC-V 64 musl（f133 + f135）— 待 WSL 解封后用玄铁 Xuantie 工具链
riscv64-unknown-linux-musl-gcc -static -O2 mt_test.c -o mt_test
```

## 🔁 抓帧时机：静止帧会漏掉瞬时元素（实测教训）

- **注入 + 抓帧放在同一次 adb 调用里**（`… && 抓帧命令`），否则中间的网络往返把瞬时状态等没了。
- ⚠️ **抓帧次数看对象寿命**：双缓冲板需要「连抓两帧取第二张」治滞后，但这会**吃掉瞬态层**——
  toast 一类只活约 **2s**（第二次抓帧的 adb 往返 + 落盘就把它等没了）→ **瞬态层单次抓帧**，
  静态页/弹窗才双抓。案例实测：一批 toast 断言就是这么假 FAIL 的（改单抓后全过）。
  完整表格（含「拿不准怎么办」）→ `device-screenshot.md` §3.3-2。
- **多档 sleep 差分**：同一次操作后分别抓 3~4 张（如 0.15s / 0.4s / 1.0s）→ diff 出“变化中的元素”：
  瞬时元素（滚动条、Toast、按压态、动画）只在其中一两张出现，单张看不到。
- **`hasScrollbar` 滚动条约 0.6 秒淡出**、颜色**逐帧变化** → 想抓它必须在滚动结束后 0.6s 内抓，
  且判据看**色阶**（不是固定灰值）；过了窗口期整条消失 → 会误判“滚动条没生效”。
- 页面切换类测试：先 `logcat` 看到 `onUI_show` 再抓帧（导航×回调矩阵见 activity-code-skeleton.md）。
- 结论：**单张静止帧不足以判定交互结果**——要么多帧差分，要么以日志为主、像素为辅（两者都会骗人）。

## ⌨️ 系统软键盘是**整屏窗口**：套件间不收键盘会全项假 FAIL（2026-09-17 实测）

**坑的形状**：输入类用例（点输入框）会弹出**系统软键盘**，而它不是一个居中弹层，
而是**整屏窗口**——会把下面所有东西（含导航栏）盖住。上一套件末尾弹出键盘后，
**紧接的下一套件注入全落在键盘按键上** → 一批导航键全部 FAIL。

**最坏的地方**：脚本通常有「多个导航键均无效就早退」的保护，于是输出只有一行
「N 个导航键全部无效」→ **看起来像「注入坏了」或「本次改动把界面改坏了」**，
而真相只是键盘还在屏上（案例就这么白查过一轮）。

**对策（按优先级）**：

1. **每套件开始前先收键盘**（注入一次关闭键）：多数平台上点键盘**右下角收起键 ≈ (963,550)**
   （以屏分辨率为准，基准 1024×600）→ 注入后抓一帧确认键盘已收。
2. **钳住注入坐标的合法性**：早退保护要**区分「键盘在屏上」与「真的点不动」**，
   别把前者当成后者；至少把键盘状态（下半屏亮度/亮占比）写进日志留痕。
3. **顺序纪律**：把会弹键盘的输入类用例放**最后一套**，或每套之间重启应用（`kill -TERM` 优先，约 3s 未退出才回退 `kill -KILL` → init 自动拉起，
   **不是 reboot**；同时避免 `adb reboot`——部分板子 reboot 后整板掉网，**因果未证**，见 `device-deploy-budget.md` §5）。

**判据（不靠内眼）**：键盘在屏与不在屏时，同一坐标（如导航条区域）的亮度明显不同
（案例实测一个固定点在两种状态下亮度约 62 vs 102）→ 用它当「键盘守卫」的判据，
比「看截图像不像键盘」稳。
