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

### 2. 预编译工具：`bin_tools/{平台}/ui_test` 或 `mt_test`（按屏幕协议选）

> **⛔ 关键坑（2026-09-08 补，沛哥 V553 实测）**：`ui_test` 是**单点协议**
> （ABS_X/ABS_Y + BTN_TOUCH），只适配老电阻屏/单点电容屏。**V85X 设备的
> gt9xx 是 MT Type-A 协议**（MODALIAS `ra30,32,35,36,39` = ABS_MT_TOUCH_MAJOR
> /WIDTH_MAJOR/POSITION_X/POSITION_Y/TRACKING_ID），不订阅单点坐标轴——用
> `ui_test` 注入后**驱动丢弃坐标，FlyThings 收到恒 `x=0 y=0`**。
>
> 解决：MT Type-A 屏改用 `mt_test`（`ABS_MT_POSITION_X/Y + ABS_MT_TRACKING_ID`）。
> 接口与 ui_test 完全一致（tap/swipe/long/monkey/run），直接换工具名即可。

**协议速判**（注入前必看）：
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

已编译平台：

| 工具 | 协议 | 平台 |
|------|------|------|
| `ui_test` | 单点 | z21 / z20 / t113 / f133 / v85x |
| `mt_test` | MT Type-A | z21 / z20 / t113 / v85x（f133/f135 待 WSL 编译） |
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
2. **MT Type-A 序列**：`EV_ABS ABS_MT_TRACKING_ID(递增) → ABS_MT_POSITION_X/Y → ABS_MT_TOUCH_MAJOR → EV_KEY BTN_TOUCH=1 → EV_SYN`；抬起 = `ABS_MT_TRACKING_ID=-1 → BTN_TOUCH=0 → EV_SYN`
3. **EV_SYN 必须发**，否则内核不提交事件——最容易漏的坑
4. **滑动逐像素/插值过渡**，禁止一次跳终点（被识别为无效/抖动），每步跟 EV_SYN
5. 时间戳 `gettimeofday` 必须填
6. **协议用错 → 坐标恒 0**：注入后 FlyThings 收到 `(0, 0)` 几乎都是协议不匹配，先按"协议速判"切换 ui_test ↔ mt_test

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
- **多档 sleep 差分**：同一次操作后分别抓 3~4 张（如 0.15s / 0.4s / 1.0s）→ diff 出“变化中的元素”：
  瞬时元素（滚动条、Toast、按压态、动画）只在其中一两张出现，单张看不到。
- **`hasScrollbar` 滚动条约 0.6 秒淡出**、颜色**逐帧变化** → 想抓它必须在滚动结束后 0.6s 内抓，
  且判据看**色阶**（不是固定灰值）；过了窗口期整条消失 → 会误判“滚动条没生效”。
- 页面切换类测试：先 `logcat` 看到 `onUI_show` 再抓帧（导航×回调矩阵见 activity-code-skeleton.md）。
- 结论：**单张静止帧不足以判定交互结果**——要么多帧差分，要么以日志为主、像素为辅（两者都会骗人）。
