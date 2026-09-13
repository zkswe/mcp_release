# PocketDisplay4（V85X）RF 模组电源控制说明

> 检索关键词：PocketDisplay4 / PD4 / V85X / 蓝牙没反应 / 串口没回应 / 串口静默 / BLE 起不来 /
> WiFi 上电 / BT 上电 / RF 模组供电 / state_bt / state_wifi / netRF / 8733bs / rtk_init / bt_enable
> 适用：**V85X（PocketDisplay4）**。T113/F133/Z20 电源链路不同，勿直接套用。
> 来源：V85X 副屏类工程（`src/ble/`）与相关 V85X 工程（`src/core/`）源码 + 真机联调确认（沛哥 2026-09-13）。

---

## 0. 一句话结论

**PocketDisplay4 上的 RF 模组（WiFi + BT combo）不会自动上电，必须由软件写 sysfs 节点把电打开。**
所以「蓝牙串口没有回应」的第一排查点就是这里——电源没开，串口上当然不会有任何 HCI 数据。

---

## 1. 电源控制节点

| 用途 | 节点路径（按存在者取） | 写入值 |
|------|----------------------|--------|
| **BT 侧电源** | `/sys/devices/platform/soc/soc@03000000:netRF/state_bt`<br>`/sys/devices/platform/soc@3000000/soc@3000000:netRF/state_bt` | `"1"` = 上电，`"0"` = 断电 |
| **WiFi 侧电源** | `/sys/devices/platform/soc@3000000/soc@3000000:netRF/state_wifi` | 同上 |

要点：

- 这是**普通 sysfs 文件，用 `open`/`fopen("w")` 写一个字符**即可，不用 ioctl、不用 gpio 框架。
- 两个 BT 路径是**同一块板不同内核枚举写法**的兜底——板子变了路径可能变，写死一个不够，要按存在性挑。
- 节点走的是 `soc@...:netRF`（netRF = RF 模组），**不是** gpio 子系统，也不在 `/sys/class/gpio` 里。

---

## 2. 代码里谁在操作它（关键链路）

V85X 副屏类工程（`src/ble/`）里，**全工程唯一操作 BT 电源的地方**：

```
ble::server_start()                         src/ble/server.cpp
  └─ ble_thread()                           独立线程
      ├─ SystemProperties::getString("persist.wifi.module", …)  ← ★ 前置门
      │    == "8733bs" ?
      │      是 → rtk_init("/dev/ttyS2")      src/ble/rtk/hciattach.c
      │      否 → 走 AIC 分支（H4，流控开）    ← 不会上电、不会下固件
      └─ rtk_init(dev):
           for (2 轮) {
             bt_enable(0);   // 写 state_bt = "0"
             usleep(50 ms);
             bt_enable(1);   // 写 state_bt = "1"
             usleep(300 ms);
           }
           → 打开串口 115200 → rtb_init(HCI_UART_3WIRE)  下载固件 → 改 1500000
```

`bt_enable()` 的行为（`hciattach.c`）：

```c
static int bt_enable(int on) {
  const char *paths[] = {
    "/sys/devices/platform/soc/soc@03000000:netRF/state_bt",
    "/sys/devices/platform/soc@3000000/soc@3000000:netRF/state_bt",
    NULL };
  // 逐个 access() 找存在的一个
  if (!state_bt) return -1;          // ★ 两个都不存在 = 直接失败
  FILE *pf = fopen(state_bt, "w");
  if (!pf) return -1;                // 权限/只读也会失败
  fwrite(on ? "1" : "0", 1, 1, pf);
  fclose(pf);
}
```

---

## 3. 两个最容易漏的点

### 3.1 前置门：`persist.wifi.module` 必须是 `"8733bs"`

```c
char module[64] = {0};
SystemProperties::getString("persist.wifi.module", module, "");
if (strcmp(module, "8733bs") == 0) { rtk_init(BT_UART_DEV); is_aic = false; }
```

- 属性**不是** `8733bs`（没写 / 写错 / 读不到）→ 走 AIC 分支：**完全不碰 `state_bt`，不上电，不下载固件**。
- 板上实际是 RTL8733BS 而属性没配对 → 串口必然静默，而且日志上只有一条 `hci up start` 之后就没下文，很容易误判成"串口硬件坏了"。

### 3.2 失败即静默：`rtk_init` 返回 -1 时 `ble_thread` 直接 `return NULL`

- 线程根本没跑起来 ⇒ 没有 HCI、没有广播、串口无任何回显。
- 所以**看日志要往前找 rtk 报错**（`Can't open serial port`、`open write ... error`），不要只盯着"串口没数据"。

---

## 4. WiFi 侧同一族节点（连带影响）

某个 V85X 工程的 `src/core/impedance.cpp` 里有一段可直接参考的 WiFi 上下电 + 天线阻抗调节写法：

```cpp
static void setPower(bool on) {
  base::writeFile("/sys/devices/platform/soc@3000000/soc@3000000:netRF/state_wifi",
                  on ? "1" : "0");
}
bool turnOnWifi(int impedance) {
  base::wifiOffAndWait();
  setPower(false);
  base::this_thread::sleep_for(5000);   // 断电后要等（毫秒级等待无效）
  setImpedance(impedance);              // 天线阻抗写 phy_range
  return base::wifiOnAndWait(10);       // 上电并等就绪
}
```

- 说明这套板子上 **WiFi 与 BT 的电源是分开的两个节点**；combo 模组场景下 WiFi 侧没起来时，BT 侧可能也没被初始化，**两边都要检查**。
- 另外 V85X 副屏工程是 **WiFi 网络模式非空才启动 BLE**（`net::add_mode_update_cb` → `on_net_mode_update` 里才发 `E_CMD_START`）。网络没起来时 BLE 也不会开始广播，别误判成电源问题。

---

## 5. 现场排查步骤（按顺序做）

1. **看节点在不在**
   ```sh
   ls -l /sys/devices/platform/soc*/soc@*:netRF/
   ```
2. **看上电状态**
   ```sh
   cat /sys/devices/platform/soc/soc@03000000:netRF/state_bt
   ```
3. **手动拉高试一把**（路径以第 1 步实际枚举为准）
   ```sh
   echo 1 > /sys/devices/platform/soc/soc@03000000:netRF/state_bt
   ```
   拉高后串口若有回应 ⇒ 锁定是「软件没走电源控制」，回去查 §3.1 的属性判据。
4. **核对属性**：设备上 `persist.wifi.module` 的实际值是否 `8733bs`。
5. **核对串口**：`/dev/ttyS2` 是否存在、dts 里 BT UART 是否真的 route 到模组。
6. **核对串口参数**：8733bs 路径是 **先 115200，下完固件改 1500000，无流控 + 偶校验**；AIC 分支是 1500000 + 流控开 + 无校验。参数不对同样表现为"没回应"。

---

## 6. 复用到其它 V85X 板时的注意事项

- `state_bt` / `state_wifi` 的**路径随内核枚举变化**，代码里要保留多候选 + 存在性判断，不要写死一条。
- 上电时序（0 → 50ms → 1 → 300ms，2 轮）是实测能起来的时序，改短可能偶发失败。
- 本工程**没有额外的 BT reset GPIO**，模组复位靠这条 `state_bt` 电源线；换成别的模组（AIC 等）时电源控制可能完全不同，需要另查。
- 断电后重新上电要留足等待时间（WiFi 侧参考实现是 5 秒级），只睡几十毫秒不够。
