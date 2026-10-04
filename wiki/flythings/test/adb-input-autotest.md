# KB: 触摸事件注入实现方法（event.c 核心，跨平台可复用）

> 来源：内网 `projects/LearningProject/input` 的 `jni/event.c`（2026-08-31 整理）。
> 定位：**通过直接读写 Linux input 事件设备（/dev/input/eventX）模拟触摸的核心实现方法**。这套方法可移植到任何平台使用——可以编译成独立 bin（命令行工具），也可以作为代码模块嵌入工程。
> ⚠️ 2026-09-08 需求方补充：**系统已提供现成 input 命令行工具**（同工程 LearningProject/input，bin/h500s/input、bin/z21/input 已编译），用法 input <dev> tap/swipe/record/play/monkey——直接 push 使用，常规自动化无需重新编译；event.c 是底层原理 + 定制/移植时的方法。
> ⚠️ 记的是**实现方法**，不是某个现成工具产物；不同平台移植时改设备节点/协议细节即可。

## 🎯 为什么这套方法有用
- **不依赖被测 App 任何代码**：直接往内核 input 子系统注入事件，App 收到的是和真人触摸完全一样的输入
- **跨平台通用**：Linux input 事件协议（`struct input_event`）是内核标准，FlyThings 各平台（SSD20x/T113/V85x...）都适用
- **两种落地形态**：① 编成 bin 放设备上跑（`adb shell input ...`）；② 把函数抄进目标工程直接调用（自动化测试/产线自检/演示脚本都能用）

## 🤖 全自动化测试闭环（需求方 2026-08-31 补充）
触摸注入只是第一环，配合以下能力可组成**完全自动化的测试流程**：
1. **input 注入**（本页）：模拟点击/滑动操作被测 UI
2. **logcat 日志分析（✅ 首选方案）**：`adb logcat` 抓设备日志，按关键字/级别（LOGD/LOGE）判定操作结果、异常、崩溃——**测试结论的判定依据，优先用这个**
   - 被测工程在关键节点加 LOGD/LOGE 埋点，自动化断言直接匹配日志关键字
3. **framebuffer 抓屏分析 UI（⚠️ 备选，非必要不用）**：
   ```bash
   adb shell cat /dev/fb0 > screen.raw        # SigmaStar 等平台
   adb shell cat /dev/disp/fb0 > screen.raw   # 部分平台 framebuffer 在 /dev/disp/ 下
   ```
   - 抓到的 raw 是 framebuffer 原始数据，**根据 fb 像素格式解析**（RGB565/RGB888/ARGB8888 等，从 `cat /sys/class/graphics/fb0/bits_per_pixel` 或 fb_var_screeninfo 查询）
   - 按分辨率 + bpp 把 raw 解码成图像，即可比对 UI 实际显示内容（截图对比/像素校验）
   - **代价：图片分析难度高**（格式/缩放/比对都要处理），仅在 logd 无法覆盖（如纯渲染问题/无日志路径）时才用
- **优先级（需求方确认）**：**logd 分析 > raw fb 抓屏**；非必要不读 raw 屏幕数据
- **闭环示例**：注入 tap → logcat 验证响应 → 判定 PASS/FAIL，全程脚本化无人值守

## 🔧 核心实现（event.c 精要）

### 1. 单事件注入函数（一切的基础）
```c
static int reportkey(int fd, uint16_t type, uint16_t code, int32_t value) {
    struct input_event event;
    event.type = type;
    event.code = code;
    event.value = value;
    gettimeofday(&event.time, 0);   // 时间戳必须填
    if (write(fd, &event, sizeof(struct input_event)) < 0) {
        LOGE("fd %d report key error %s!\n", fd, strerror(errno));
        return -1;
    }
    return 0;
}
```

### 2. 单点触摸（zk_touch_test）——完整协议序列
```c
int zk_touch_test(const char *dev, int posx, int posy) {
    int fd = open(dev, O_WRONLY);   // 注入用 O_WRONLY 即可
    if (fd < 0) return -1;

    // === 按下 ===
    reportkey(fd, EV_ABS, ABS_X, posx);           // X 坐标
    reportkey(fd, EV_ABS, ABS_Y, posy);           // Y 坐标
    reportkey(fd, EV_ABS, ABS_PRESSURE, 100);     // 压力值
    reportkey(fd, EV_KEY, BTN_TOUCH, 1);          // 触摸按下键
    reportkey(fd, EV_SYN, EV_SYN, EV_SYN);        // ⚠️ SYN 同步，内核才提交这批事件

    // === 抬起 ===
    reportkey(fd, EV_ABS, ABS_PRESSURE, 0);       // 压力归零
    reportkey(fd, EV_KEY, BTN_TOUCH, 0);          // 触摸抬起键
    reportkey(fd, EV_SYN, EV_SYN, EV_SYN);

    close(fd);
    return 0;
}
```
**协议铁律：`ABS_X/Y → ABS_PRESSURE → BTN_TOUCH → EV_SYN`，EV_SYN 必须发，否则内核不提交。**

### 3. 滑动（zk_swipe_test）——逐像素步进
```c
int zk_swipe_test(const char *dev, int x1, int y1, int x2, int y2) {
    int fd = open(dev, O_WRONLY);
    if (fd < 0) return -1;

    // 按下（同点击的 down 序列）
    reportkey(fd, EV_ABS, ABS_X, x1);
    reportkey(fd, EV_ABS, ABS_Y, y1);
    reportkey(fd, EV_ABS, ABS_PRESSURE, 100);
    reportkey(fd, EV_KEY, BTN_TOUCH, 1);
    reportkey(fd, EV_SYN, EV_SYN, EV_SYN);

    // 逐像素移动：每次只动 1 个像素，发坐标后必须跟 EV_SYN
    int step_x = x1 < x2 ? 1 : -1;
    int step_y = y1 < y2 ? 1 : -1;
    while (1) {
        reportkey(fd, EV_ABS, ABS_X, x1);
        reportkey(fd, EV_ABS, ABS_Y, y1);
        reportkey(fd, EV_SYN, EV_SYN, EV_SYN);
        if (x1 != x2) x1 += step_x;
        if (y1 != y2) y1 += step_y;
        if (x1 == x2 && y1 == y2) break;
    }

    // 抬起（同点击的 up 序列）
    reportkey(fd, EV_ABS, ABS_PRESSURE, 0);
    reportkey(fd, EV_KEY, BTN_TOUCH, 0);
    reportkey(fd, EV_SYN, EV_SYN, EV_SYN);

    close(fd);
    return 0;
}
```
- 滑动要点：**逐像素（或中点插值）发中间坐标，不能一次跳终点**（会被识别为无效/抖动）；每步 EV_SYN
- event.c 里还有注释掉的 **ABS_MT_* 多点触控协议示例**（ABS_MT_POSITION_X/Y、ABS_MT_TOUCH_MAJOR + SYN_MT_REPORT），多指手势参考那段

### 4. 事件读取（录制/监听）——event.c 的 evtest 部分
- 设备扫描：`scandir("/dev/input", is_event_device)` 列出所有 event 节点 + `EVIOCGNAME` 读设备名
- 能力查询：`EVIOCGBIT` 读设备支持的事件类型（判断哪个节点是触摸屏）
- 事件读取：`select(fd+1, &rdfs...)` + `read(fd, ev, sizeof(ev))` 批量读

## 🧩 跨平台移植要点（需求方强调：后续不同平台要转成不同平台使用）
1. **设备节点不同**：`/dev/input/eventX` 编号各平台/各硬件不同——用 evtest/getevent 扫描确认，或代码里自动遍历 `/dev/input` 找触摸节点（EVIOCGNAME 含 touch/ts 关键字）
2. **协议可能不同**：
   - 单点屏：`ABS_X/ABS_Y + ABS_PRESSURE + BTN_TOUCH`（event.c 主路径）
   - 多点屏：`ABS_MT_POSITION_X/Y + ABS_MT_TOUCH_MAJOR + ABS_MT_TRACKING_ID + SYN_MT_REPORT`（event.c 注释段有示例）
   - 有的平台压力值范围不同（查 EVIOCGABS 的 min/max）
3. **权限**：写 input 设备需要 root；部分平台设备节点只读时需要先 chmod
4. **落地形态**：编成 bin（独立工具）或抄函数进工程（代码模块）都行——核心就是 reportkey + 协议序列
5. 需要自动化测试扩展（录制/回放/压力）时，参考同工程 input.cpp 的 Wait/Inject/序列化方法（poll 超时录制 + 时间戳差回放）

## ⛔ 铁律
1. **EV_SYN 必须发**，否则内核不提交触摸事件——最容易漏的坑
2. 滑动**逐像素/插值过渡**，禁止跳终点
3. 时间戳 `gettimeofday` 必须填
4. 注入是标准内核协议，**不经过 FlyThings 框架**，App 无感
5. 移植第一件事：确认触摸节点 + 单点/多点协议类型
