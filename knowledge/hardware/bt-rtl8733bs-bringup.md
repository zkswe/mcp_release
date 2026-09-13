# RTL8733BS 蓝牙 bring-up（V85X / btstack）：上电 → hciattach → H5 通路

> 检索关键词：蓝牙起不来 / BT 零回应 / 标准 HCI 无应答 / RTL8733BS / Realtek 8733bs /
> `rtk_init` / `rtk_hciattach` / H5 同步握手 / `OP_H5_SYNC Transmission timeout` /
> `HCI_STATE_INITIALIZING` 卡住 / BT 上电 / `state_bt` / `bt_enable` /
> 8E1 偶校验 / 115200 切 1500000 / 补丁固件 `rtl8733bs_fw` / `rtl8733bs_config` /
> `persist.wifi.module` / RF 模组电源 / 电源控制流程 / state_wifi / 节点路径兜底 / 天线阻抗 /
> btstack run loop 线程 / `hci_add_event_handler` /
> `btstack_uart_t` frame 接口 / HCI 事件码 0x6E / SLIP 帧 / 抓包重放不成立 /
> 学习遥控器按键 / BLE HID 手机发现 / TLV 落盘
> 适用：**全志 V85X（V851 系列实测）** + RTL8733BS 组合芯片 + btstack。T113/F133/Z20 电源与串口链路不同，勿直接套用。
> 来源：V85X 副屏类工程 bring-up 实测记录（2026-09-12~13）+ 本机源码逐条核对（2026-09-13）。

---

## 0. 一句话结论

**标准 HCI 命令零回应 ≠ 缺固件那么简单。** RTL8733BS 有**两个前置条件**，缺任一都收不到任何字节：

1. **BT 必须先在 sysfs 上电**（`state_bt` 节点，出厂值 `off`）；
2. **必须先跑 Realtek 自己的 hciattach 预初始化**：H5 同步握手 → 读 ROM 版本 → 下载补丁固件 → 115200 切 1500000，之后才能当"普通 HCI"用。

再叠加 **传输必须是 H5 + 偶校验 8E1 + 无流控**。这三条一起错着时，任何参数组合都是零回应。

电源那一条要一并写清：**BT 电源是 sysfs 开关节点**（V85X 为 `soc@*:netRF/state_bt`，兜底第二条候选路径），
出厂值 `off`，**软件不写就永远没电**；是否走 8733bs 这套初始化分支，则由属性前置门决定：
`persist.wifi.module == "8733bs"` 才走，否则按 AIC 分支跑（不碰电源、不下固件 ⇒ 串口必然静默，
日志只有 `hci up start` 之后就没下文，极易误判成硬件坏）。前置门不匹配时 `rtk_init` 返回 -1，
初始化线程直接 `return NULL` —— **看日志要往前找 rtk 报错**，不要只盯着"串口没数据"。

---

## 1. 硬件事实（V85X 实测，换板必须重测）

| 项 | 实测值 | 怎么确认 |
|---|---|---|
| 芯片 | **RTL8733BS**（WiFi + BT combo） | 设备上 `lsmod` 含 `8733bs`；`getprop persist.wifi.module` = `8733bs` |
| BT 串口 | **`/dev/ttyS2`**（V85X）；F133 侧是 `ttyS1` | DT：`uart@2500000`(ttyS0) / `uart@2500800`(ttyS2) = `okay` 且 pinmux 齐；`uart@2500400`(ttyS1) / `uart@2500c00`(ttyS3) = `disb` |
| ⚠️ 出厂配置对不上板子 | `EasyUI.cfg` 默认写 `uart:"ttyS1"`，本板这个节点不存在 | 照抄必失败（本机多个 V85X 工程 launch 配置确实是 `ttyS1` 默认值，属平台默认而非板级真值） |
| 传输层/校验 | **H5 + 偶校验（8E1）+ 无流控**，全程 | Realtek 规格 + 工程实现一致 |
| 波特率 | **预初始化 115200 → 工作 1500000**（由预初始化自己切） | 日志 `Config baudrate`；工程 `config.baudrate_init = 1500000` |
| BT 上电节点 | `/sys/devices/platform/soc/soc@03000000:netRF/state_bt`（兜底 `soc@3000000/soc@3000000:netRF/state_bt`） | 出厂值 `off`，写 `1` 才供电 |
| 上电时序 | 写 `0` → 50ms → 写 `1` → 300ms，**跑两轮** | 工程 `rtk_init()` 里的 `bt_enable(0/1)` 循环（已逐行核对） |
| 固件 | `rtl8733bs_fw`（55580 B）+ `rtl8733bs_config` | 固件文件头字节数与下载日志 `size 55580` 一致 |
| ⚠️ 系统盘里那份固件不是它的 | 某些整机 `/lib/firmware` 只有 `aic8800DC`（那是 **AIC8800** 的） | 全盘搜不到 rtl/bt 固件 ⇒ 固件必须随应用走 |
| 其它"不存在"的东西 | 无 `/dev/hci*`、无 `/sys/class/bluetooth`、无 rfkill | 某些整机 `/etc/init.rc` 里是 `hciattach -n ttyS2 aic`（**面向 AIC8800**，与本板芯片不符） |

**把机器从"零回应"救活的证据链（跑通时的原始日志形态）**：

```
[rtk] Realtek hciattach version ...
[rtk] [SYNC] Get SYNC Resp Pkt              ← H5 同步握手成功（关键第一步）
[rtk] H5 init finished / Realtek H5 IC
[rtk] Read ROM version 02
[rtk] IC: RTL8733BS, chip_type 0x76
[rtk] Load FW .../rtl8733bs_fw OK, size 55580
[rtk] Config baudrate: 04928002 / Vendor baud ...   ← 切 1500000
[BT]  BTSTACK state = 2 (WORKING)           ← ★ HCI 通路建立
[BT]  -> HCI 版本 11, 厂商 0x005d (Realtek), 子版本 0x6fec
```

---

## 2. 电源控制流程与接口（硬件关联；这一步做不对，后面全是零回应）

> 这是**实测最耗时的一环**：BT 电源节点状态不对时，串口上任何参数组合都是零回应，
> 极易误判成"串口坏了 / 缺固件"。实测曾在这一步（`state_bt`）卡掉几个小时。

### 2.1 节点与语义

| 用途 | 节点路径（按存在者取一条） | 语义 |
|---|---|---|
| **BT 电源** | `/sys/devices/platform/soc/soc@03000000:netRF/state_bt`<br>`/sys/devices/platform/soc@3000000/soc@3000000:netRF/state_bt` | 写 `"1"` = 上电，写 `"0"` = 断电 |
| **WiFi 电源** | `/sys/devices/platform/soc@3000000/soc@3000000:netRF/state_wifi` | 同上（combo 模组上 WiFi / BT 是**两个独立开关**） |

- 就是**普通 sysfs 文件**：`open`/`fopen("w")` 写一个字符即可，**不用 ioctl、不走 gpio 子系统**，也不在 `/sys/class/gpio` 里。
- 两条 BT 路径是**同一类板子不同内核枚举写法**的兜底：代码里 `access()` 逐个探，**不许写死一条**。
- 节点走的是 `soc@...:netRF`（netRF = RF 模组）。出厂/启动后默认是 `off`——**不写就永远没电**。

### 2.2 谁在什么时机调（调用链）

```
ble 服务启动 → ble_thread()（独立线程）
  ├─ SystemProperties::getString("persist.wifi.module") ← ★ 前置门
  │    == "8733bs" ?  是 → rtk_init(dev)     （在 BT 线程内、hci_init() 之前）
  │                   否 → 走 AIC 分支        （不碰电源、不下固件 ⇒ 串口必然静默）
  └─ rtk_init(dev)
       for (2 轮) { bt_enable(0); usleep(50ms); bt_enable(1); usleep(300ms); }
       打开串口 115200 → 下补丁固件 → 切 1500000 → 交给 btstack
```

要点：

- **上电必须在 HCI/btstack 初始化之前**，而且**在同一条 BT 线程里**做（btstack 单线程铁律，见 §3 坑 4）。
- **两轮 断电→上电**是实测能稳定起来的时序：只跑一轮偶发不起来；两轮里的 50ms / 300ms 不要改小。
- 前置门不匹配（属性没写 / 写错 / 读不到）⇒ 走 AIC 分支：不碰 `state_bt`、不下固件，
  日志只有 `hci up start`，之后没下文——这是"看起来什么都没发生"的典型来源。

### 2.3 `bt_enable(on)` 接口实现要点（可直接照抄的结构）

```c
static int bt_enable(int on) {
  const char *paths[] = {                 /* 多候选 + 存在性判断，不写死 */
    "/sys/devices/platform/soc/soc@03000000:netRF/state_bt",
    "/sys/devices/platform/soc@3000000/soc@3000000:netRF/state_bt", NULL };
  const char *node = NULL;
  for (int i = 0; paths[i]; i++) if (access(paths[i], F_OK) == 0) { node = paths[i]; break; }
  if (!node) return -1;                   /* 两个都不存在 = 直接失败，别静默继续 */

  FILE *pf = fopen(node, "w");
  if (!pf) return -1;                     /* 只读 / 权限不足也会失败 */
  int n = fwrite(on ? "1" : "0", 1, 1, pf);
  fclose(pf);
  if (n <= 0) return -1;

  pf = fopen(node, "r");                  /* ★ 回读确认状态真的变了 */
  for (int i = 0; i < 100; i++) {         /* 最多等 100 × 30ms ≈ 3s */
    char st[8] = { 0 };
    fseek(pf, 0, SEEK_SET);
    if (fread(st, 1, sizeof(st), pf) <= 0) break;
    if (on ? strncmp(st, "on", 2) == 0 : strncmp(st, "off", 3) == 0) break;
    usleep(30000);
  }
  fclose(pf);
  return 0;
}
```

- 必须**回读**：写成功 ≠ 状态已变（供电有建立时间），节点回 `on`/`off` 才算到位。
- **失败要返回错误**，让上层 `rtk_init()` 直接失败退出；不要"失败也继续往下走"（后面只会一路静默）。
- 电源这条线与 USB/UVC 类节点不同：**没有 ioctl/控制传输**，纯文件读写，权限与路径存在性就是全部前置条件。

### 2.4 失败表现与现场排查（照这个顺序）

1. 看节点在不在：`ls -l /sys/devices/platform/soc*/soc@*:netRF/`
2. 看上电状态：`cat .../netRF/state_bt`（`off` = 没电）
3. 手工拉高试一把：`echo 1 > .../netRF/state_bt` → 串口有回应 ⇒ 锁定"软件没走电源控制"，回去查 §2.2 前置门
4. 核对属性：设备上 `persist.wifi.module` 是否真是 `8733bs`
5. 核对串口：`/dev/ttyS2` 是否存在、dts 里 BT UART 是否真路由到模组
6. 核对串口参数：8733bs 是 **115200 起步 → 下完固件切 1500000 + 无流控 + 偶校验**；AIC 分支是 1500000 + 流控开 + 无校验

**典型误判**：`rtk_init` 返回 -1 时初始化线程直接 `return NULL` ⇒ 既无 HCI、也无广播、串口无回显。
看日志要**往前找 rtk 的报错**（`Can't open serial port` / `open write ... error`），不要只盯着"串口没数据"。

### 2.5 复用到其它板子时的注意事项

- `state_bt` / `state_wifi` **路径随内核枚举变化**：保留多候选 + 存在性判断，不要写死一条。
- 这类板子**没有额外的 BT reset GPIO**：模组复位就靠这条电源线（写 0 再写 1）。换成别的模组（AIC 等）时电源控制可能完全不同，必须另查。
- 断电后重新上电要**留足够等待时间**（WiFi 侧参考实现是秒级，如 5s）；只 sleep 几十毫秒不够。
- WiFi 与 BT 是两个开关，且 combo 场景下是联动的：WiFi 没起来的板子，BT 侧往往也没被初始化——**两边都要看**。

---

## 3. 坑清单（按"排查顺序"排，越靠前越是第一嫌疑）

### 坑 1 ★ 芯片零回应 —— 头号原因是 BT 没上电

- **症状**：串口能打开、写返回成功，`115200/1500000 × H4/H5 × 校验/流控` 全矩阵试遍，
  **芯片侧一个字节都不回**；连 Realtek 厂商命令 `0xFC6D`（Read_ROM_Version）也不回。
- **根因**：BT 电源是 **sysfs 开关节点**，出厂/启动后是 `off`。
- **解法**：`state_bt` 写 `0` → 50ms → 写 `1` → 300ms，**跑两轮**（在 BT 线程里、`hci_init()` 之前做；
  失败就直接退，别指望后面能自愈）。同一个 combo 模组上 **WiFi 侧是另一个节点** `state_wifi`（分开的两个开关），
  排查时两边都要看：WiFi 没起来的板子，BT 侧往往也没被初始化。
- **判据**：`0xFC6D` 是否回 `COMMAND_COMPLETE`——**只要芯片上电且在听就一定会回**；
  不回 ⇒ 先查上电，别急着怀疑固件。

### 坑 2 ★ 缺 Realtek 预初始化 —— 不做 hciattach 就**不应答标准 HCI**

- **症状**：上电正常、参数正确，但 HCI Reset 之类标准命令依然无回应。
- **根因**：RTL8733BS **必须先跑 Realtek 自己的 hciattach 流程**，做完才切到"普通 HCI"模式：
  **H5 同步握手 → 读 ROM 版本 → 下载补丁固件（fw + config）→ 切 1500000**。
- **解法**：移植 Realtek hciattach（`hciattach.c` + `hciattach_h4.c` + `rtb_fwc.c`，3.1.3 分支）
  成工程的 `rtk_init(dev)`，在 `hci_init()` **之前**调用。
- **判据**：日志出现 `[SYNC] Get SYNC Resp Pkt` + `IC: RTL8733BS` + `Load FW ... size N`
  ⇒ 预初始化已做对；之后才可能看到 `HCI_STATE_WORKING`。

### 坑 3 H5 需要 frame 级 uart 接口 —— 先查再决定要不要自研

- **症状**：H4 模式正常，**一切到 H5 一上电就崩**（空指针）或直接没反应。
- **根因**：**H5 要求 uart 提供 frame 级接口**
  （`set_frame_received` / `set_frame_sent` / `receive_frame` / `send_frame`），
  H5 的同步字与校验位都由 SLIP 帧承载（`0xC0` 帧界 / `0xDB` 转义）。
  若所用 btstack 构建的 **posix uart 没实现这些回调（自带上游实现里可能是 NULL）**，
  `hci_power_control()` 会直接用 → 崩。
- **先核实再动手**（本机核对结论，v85x 的 btstack 1.7.2 包）：
  - 头文件 `btstack/btstack_uart.h` **已声明** `set_parity` 以及上面四个 frame 回调；
  - `hci_transport_h5.h` 明确要求"uart implementation that supports SLIP frames"，
    并 `@deprecated` 了 `hci_transport_h5_enable_bcsp_mode()`，注释写着 **"Parity can be enabled in UART driver configuration"**；
  - 包里同时提供 `btstack_uart_slip_wrapper.h` + `btstack_slip.h`（block 型 uart 可套 SLIP 包装）。
  - 因此真正推荐的写法是**先用官方口子**：
    `btstack_uart_posix_instance()` + `config.parity = BTSTACK_UART_PARITY_EVEN` + `hci_transport_h5_instance(uart)`。
    工程里就是这么写的（`hci_transport_config_uart_t.parity`、`flowcontrol`、`baudrate_init` 全显式）。
  - **只有两种情况才自研 uart**：① 你的 btstack 构建确实没实现 frame 回调（H5 必崩）；
    ② 需要在运行期切波特率（115200↔1500000）而该实现不支持。
    自研版要点：8E1 偶校验 + 运行期切波特率 + SLIP 帧收发。
- **教训**：别听"必须自己写 uart"就上手重写——**先 `strings`/头文件确认当前包的能力**，能用配置项就用配置项。

### 坑 4 ★ 所有 btstack API 必须在**跑 run loop 的那条线程**里调

- **症状**：run loop 起来了，但**永远停在 `HCI_STATE_INITIALIZING`**，
  **连周期性的 tick 日志都没有**（线程阻塞在 `poll()`）——很容易误判成"卡死/崩溃"。
- **根因**：`btstack_run_loop_add_data_source()` / `add_timer()` 注册在主线程，
  run loop 却在另一条线程跑 ⇒ 注册不生效。
- **解法**：**装配顺序 = 全部初始化（run loop init、data source 注册、TLV、`hci_init`）都放在 BT 线程里**；
  UI/主线程要发命令，走 `btstack_run_loop_execute_on_main_thread()`，
  工程里更实用的是 **`socketpair` fd 注册成 data source** 做跨线程投递（`trans_fds[0]` + `trans_process`）。

### 坑 5 `hci_add_event_handler()` 必须在 `hci_init()` **之后**

- **症状**：直接段错误（`-s` 编译还看不到栈）。
- **根因**：它往 `hci_stack` 的事件链表加节点，而 `hci_stack` 由 `hci_init()` 分配。

### 坑 6 判定"芯片有没有回应"只能看 **HCI 事件码 0x01~0x5F**

- **症状**：日志疯狂刷 `state = 0x6E`，看起来"有回应"，其实芯片一个字节没回。
- **根因**：`0x6E` = `HCI_EVENT_TRANSPORT_PACKET_SENT`（btstack_defines.h 已核对），
  是 **btstack 本地事件**（"我发出去了"），与芯片无关。
- **解法**：过滤只看 `0x01~0x5F`；早期"零回应"结论就是靠这条修正的。

### 坑 7 上电后别立刻发命令 —— 等 `HCI_STATE_WORKING`

- 状态枚举：`HCI_STATE_OFF / INITIALIZING / WORKING / HALTING / SLEEPING`。
- 做法：挂 **100ms 定时器**轮询 `hci_get_state()`，没到就每秒重发一次 HCI Reset。
- 退出用 `btstack_run_loop_trigger_exit()`（POSIX run loop 没有别的 stop 接口），**不是 `exit()`**；
  退出后记得 `btstack_run_loop_poll_data_sources_from_irq()` 唤醒一次。

### 坑 8 ★ 预初始化成功率不稳定，失败后**很难自愈**（设备侧观察）

- **症状**：同一块板反复跑，有时成功有时失败；失败表现为 `OP_H5_SYNC Transmission timeout`
  （有时走到 `[CONFIG]` 阶段才失败）；失败后 btstack 一直 `INITIALIZING`。
- **已排除**（都实测过）：参数不对 ❌ / 断电时序不对 ❌ / 内存不足 ❌ /
  **WiFi 共存**（`ifconfig wlan0 down` 后照样失败）❌ / 软件 `reboot` 能复位 ❌
  （连续 3 次 `reboot` 后立即跑，全失败）。
- **最可能解释**：**BT 电源域/复位只有"物理冷启动"才能回到 ROM 状态**，软 reboot 不切它的电；
  "刚上电第一次"通常成功。（本节为设备观察结论，未做示波器/电源域级复核。）
- **调试对策**：
  1. **能一次跑通就别重复跑**——自检窗口设长（如 1800s），跑通后留在窗口里测；
  2. 必须重来时 **物理断电重上电**（拔插/复位键），不要用 `reboot`；
  3. 代码里可做 **失败自动断电重试 3 次**（`state_bt` 0 → 2s → 1），但同样受"软复位不彻底"限制。
- **产品化结论**：**只在开机后首次进入该功能时初始化一次**，绝不反复重初始化。

### 坑 9 btstack 版本要**锁**，别用 `^` 浮动

- HID 的 ATT 表 / 报告描述符（`gatt_profile_data.h`）是**按某个 btstack 版本生成**的，换版本要重生成。
- 锁法：**`Manifest.xml` 里显式写版本**
  `<package id="btstack" version="1.7.2"/>`（不是 `fun.json`；本机核对：V85X 工程即写在 Manifest.xml）。
  实测 `^1.8.0` 也能编过，但与参考实现保持一致更稳。

### 坑 10 固件怎么随应用打包

- 放 `src/dependencies/bin/firmware/rtlbt/` ⇒ 打包时进 `/res/bin/firmware/rtlbt/`。
- 运行时固件目录用**候选链**：`/res/bin/firmware/rtlbt/` → `/data` → `/tmp`
  （`/res` 只读、`/tmp` 重启清、`/data` 可写）。

### 坑 11 想"抓包重放学遥控器"在 BT 上**不成立**

- 概念坑：BT HID 按键走**加密链路**，每条连接有独立会话密钥 ⇒ 抓到的包无法重放到另一条链路。
- 正解：**本机当 BLE HID 主机**（`hids_client`）去连对方、读对方发的报告，
  在**本机**建"物理键 → 动作"映射表。同一颗芯片可以同时做 peripheral + central。

### 坑 12 集成期零碎坑（与蓝牙协议无直接关系，但都会撞上）

- **HID 报告解析必须吃【含 report id 的完整报告】**（BLE HID 通知本身带 id）。
  "跳过首字节只传位图" → 一项都解析不出来。
  **排错顺序**：先用 `btstack_hid_get_report_size_for_id()` 验证描述符能被解析，再看传参格式。
- **按需开关反而收不到**：扫描"收集"若用一个 `scanCollect` 开关控制，实测**开了也收不到**
  （列表 0 个设备，而 advCount 已 1153）→ 改成**始终收集**立刻正常（开销可忽略）。
  根因未彻底查清，如实记录。
- **Windows 不给应用层访问 HID 服务的特征**：设备侧 GATT 正确（WinRT 原生 API 能看到 `0x1812`），
  但枚举其特征时 DeviceInfo 正常、**HID 返回 `status=3(PROTOCOL_ERROR)/数量=0`**
  ——Windows 把 HID 留给系统驱动。⇒ **HIDS 订阅只能手机验证**，PC（bleak/WinRT）走不通；
  另外 `bleak` 在 Windows 上"列全部服务"会漏 HID，必须用 WinRT 原生 API。
- **TLV 落盘优先 `/data`**：`/`、`/res` 只读，`/tmp` 重启清，`/data` 可写且不丢。
  `tlv_posix_init_instance("/data/bttlv.db")` + `btstack_tlv_set_instance` + `le_device_db_tlv_configure`。

---

## 4. 固定排查套路（照这个顺序走，别跳）

```
① 芯片是 RTL8733BS 吗？（getprop persist.wifi.module == 8733bs）
   └─ 是 → 走 rtk_init，不要当"普通 HCI"直接开
② BT 上电了吗？（cat .../netRF/state_bt）
   └─ off → 写 0 → 50ms → 1 → 300ms（跑两轮）
③ 参数对吗？（ttyS2 + H5 + 偶校验 8E1 + 无流控；预初始化 115200 → 工作 1500000）
④ 判据看什么？（只看 HCI 事件码 0x01~0x5F；顺带发 0xFC6D 探活）
⑤ 走完 rtk_init 看到 WORKING 了吗？（没到就轮询 + 每秒重发 HCI Reset）
⑥ 卡在 INITIALIZING？（先查"btstack API 是不是在 run loop 线程调的"）
⑦ 反复失败？（物理冷启动，别用 reboot）
⑧ 还不行 → 才谈固件/时钟/硬件
```

---

## 5. 可复用的实现件（本机已核对存在）

| 件 | 典型位置 | 作用 |
|---|---|---|
| `hciattach.c/.h`、`hciattach_h4.c/.h`、`rtb_fwc.c/.h`、`private.h` | `src/ble/rtk/` | Realtek hciattach 移植（同步握手 / 读 ROM / 下固件 / 切波特率） |
| `tlv_posix.c/.h` | `src/ble/` | TLV 持久化（`/data/bttlv.db`） |
| `gatt_profile_data.h` | `src/ble/` | HID ATT 表 + 报告描述符（**按 btstack 版本生成**） |
| `server.cpp`（`ble_thread`） | `src/ble/` | ✅ **线程模型范本**：初始化全在 BT 线程 + socketpair 跨线程投递 |
| `rtl8733bs_fw` / `rtl8733bs_config` | `src/dependencies/bin/firmware/rtlbt/` | BT 补丁固件（随应用打包） |
| `btstack_uart_slip_wrapper.h` / `btstack_slip.h` | btstack 包 `include/btstack/` | H5 的 SLIP 帧包装（优先用它，别急着重写 uart） |

---

## 6. 相关文档

- `v85x/display-layer-debug.md`、`v85x/usb-gadget-storage.md` 等 V85X 平台深度篇

---

## 7. 本次核对记录（2026-09-13，机器核对口径）

- **已逐条核对（源码/包在本机可查）**：`state_bt` 两条候选路径与 `access()` 兜底、上电时序 0/50ms/1/300ms × 2 轮、
  写后回读 `on`/`off`（100 × 30ms）、失败即返回 -1 的链路（`rtk_init` → `ble_thread` return NULL）、
  `persist.wifi.module=="8733bs"` 前置门、`state_wifi` 同族节点，`state_bt` 两条候选路径与 `access()` 兜底、上电时序 0/50ms/1/300ms × 2 轮、
  `ttyS2` + 115200→1500000 + `flowcontrol=0` + `parity=BTSTACK_UART_PARITY_EVEN`、
  固件字节数 55580、`btstack 1.7.2` 锁在 Manifest.xml、`0x6E=HCI_EVENT_TRANSPORT_PACKET_SENT`、
  btstack_uart 的 `set_parity` 与四个 frame 回调声明、SLIP wrapper 头文件存在、TLV/`le_device_db_tlv` 调用点。
- **原文需修正**：① 源工程头注写的另一台机器路径（掌机工程）本机不存在——技术内容已按本机可查工程核对，
  归属描述不入库；② "必须自研 uart/SLIP"改为"**先确认当前 btstack 构建的 frame/parity 能力**，
  能用配置项就用配置项，只有确认缺失才自研"（见坑 3）；③ 版本锁定在 **Manifest.xml**，不是 `fun.json`（坑 9）。
- **未复核（设备/PC 侧观察，保留原记录）**：`rtk_init` 约半数成功率与"软 reboot 无效"、
  Windows 下 HID 服务不可枚举、`scanCollect` 开关失效、`/lib/firmware` 只有 AIC 固件、打包进 `/res/bin/firmware/rtlbt/` 的体积变化。
