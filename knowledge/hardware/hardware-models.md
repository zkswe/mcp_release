# 硬件型号库（平台 → 型号 → 规格 / 预设参数）

> 检索关键词：型号 / 硬件 / 平台型号 / 屏幕分辨率 / 按键值 / PocketDisplay4 / SW80480070D / SV50PD / 86盒 / 串口屏 / 价签 / 选型
> 用法：**有具体型号** → 按该型号的预设参数开工（平台/分辨率/按键直接照抄）；**没有具体型号** → 确认平台 + 分辨率即可建工程，其余按需再问。
> 本文档由 `scripts/gen_hardware_doc.py` 从 `hardware_catalog.json` 生成，**勿手改**（改 json 后重跑生成器 + `rebuild_index_local.py`）。
> 查询用工具：`flythings_hardware_info(model, platform)`；未收录型号会返回候选与「平台 + 分辨率即可」的开工建议，不猜规格。

## 型号命名规则（看型号名时参考）

- 结构：SW + 分辨率 + 尺寸 + 平台字母 + 选配位 + _后缀（依据 7 寸串口屏规格书 V1.0 第 4 节）
- 示例：SW80480070A_CWM = 7 寸 800×480，电容触摸 + WIFI + 多媒体版（官方《产品规格型号说明》示例）
- 平台/版本字母 D：Z20 平台（沛哥 2026-09-12 确认）
- 平台/版本字母 E：Z21 平台（沛哥 2026-09-12 确认）
- ⚠️ 适用范围：字母可跨产品线套用：4 寸 86 盒线 SW48480040B1=Z6 / D1=Z20 / E=Z21（86 盒规格书 V3.0）与 D=Z20、E=Z21 一致；其他字母（A/B/C 等）未确认，先问沛哥再入库。
- 使用边界：型号名只能看出平台/分辨率线索，**具体规格以规格书为准**（不要按命名外推接口、内存、容量）

## 平台总览

| 平台 | 型号数 | 已登记型号 | 平台定位 |
|------|-------|-----------|---------|
| V85X | 1 | PocketDisplay4 | 全志 V85x 系列（A7，视频编码 1080p）——摄像头/DVR/手持便携类产品常用 |
| Z20 | 4 | SW48480040D1 / SW8001280101D-JQ / SW8001280101D1-JQ / SW80480070D_C | A7 双核 1.2GHz + 内置 128MB DDR3——86 盒高配/语音面板/电子价签常用平台 |
| Z21 | 4 | SV50PD / SW10600070E_C / SW48480040E / SW48854050E1 | A7 双核 1.0GHz + 内置 64MB DDR2——串口屏/广告机/86盒主力平台 |

## V85X

- 平台定位：全志 V85x 系列（A7，视频编码 1080p）——摄像头/DVR/手持便携类产品常用
- 常见主控：V553 / V851S / V851S3 / V853
- 平台默认参数：tfcardFormat=FAT32 + 64KB 簇（OEM=zkswe）——录制类必查，电脑格的卡判不符；displayLayer=UI 层要留 visible:true 的 videoView 透明窗，视频层才透得出
- 可选补充（非阻塞）：平台差异化说明（沛哥将补充：与 Z21/V853 等在屏幕方向、按键、TF 卡格式等方面的差异；有了就不用每次核查）

### PocketDisplay4（V85X）

- 形态：手持/便携整机（形态待确认）
- 别名：PD4 / PocketDisplay-4 / Pocket Display 4
- 摘要：4 寸 480x800 竖屏；3 键：105(KEY_LEFT), 103(KEY_UP), 108(KEY_DOWN)；手持/便携整机（形态待确认）
- 屏幕：尺寸(寸)=4，宽=480，高=800，分辨率=480x800，方向=portrait，说明=4 寸 480×800（竖屏）
- 按键：3 个，按键值 105(KEY_LEFT), 103(KEY_UP), 108(KEY_DOWN)
  - 按键值 = /dev/input 事件里的 code（Linux input-event-codes）。105/103/108 按标准头文件为 KEY_LEFT / KEY_UP / KEY_DOWN（物理丝印与 UI 功能对应关系待真机核对）
- RF 模组电源：WiFi/BT 模组**不自动上电**，必须软件写 sysfs 节点才能开：BT 用 state_bt、WiFi 用 state_wifi（路径 /sys/devices/platform/soc*/soc@*:netRF/）——蓝牙串口无回应当首选排查此项；代码里唯一开它的地方是 rtk_init()→bt_enable()，且被 persist.wifi.module==8733bs 前置门挡住；详见 knowledge/hardware/pocketdisplay4-rf-power.md
- **默认参数（开发直接照抄）**：tfcardFormat=FAT32 + 64KB 簇（OEM=zkswe）——录制类必查，电脑格的卡判不符；displayLayer=UI 层要留 visible:true 的 videoView 透明窗，视频层才透得出；resolution=480x800；orientation=portrait；keys=[105, 103, 108]
- 资料：`knowledge/hardware/pocketdisplay4-rf-power.md`
- 可选补充（非阻塞，按需补）：整机其余规格（CPU/内存/存储/接口）——有则更省事，没有也能开工
- 可选补充（非阻塞，按需补）：屏幕接口类型（RGB / MIPI）与触摸方式
- 可选补充（非阻塞，按需补）：三个按键的物理位置与丝印
- 可选补充（非阻塞，按需补）：V85X 平台差异化说明（屏幕方向 rotateScreen / TF 卡格式等）
- 数据来源：沛哥 2026-09-12 口述；RF 模组电源控制（state_bt/state_wifi + persist.wifi.module 前置门）2026-09-13 真机联调确认
- 数据状态：partial

## Z20

- 平台定位：A7 双核 1.2GHz + 内置 128MB DDR3——86 盒高配/语音面板/电子价签常用平台
- 常见主控：SSD201 / SSD202 / SSD202D
- 平台默认参数：uartDefaultBaud=115200；upgrade=U 盘 / TF 卡升级
- 可选补充（非阻塞）：平台差异化说明（沛哥将补充；没有也不影响开工）

### SW48480040D1（Z20）

- 形态：4 寸 86 盒智能面板（Z20 版）
- 摘要：4 寸 480x480 / 720x720 横屏；4 寸 86 盒智能面板（Z20 版）
- 屏幕：尺寸(寸)=4，宽=480，高=480，分辨率=480x480 / 720x720，方向=landscape
- 平台：Z20（A7 双核 1.2GHz，内置 128MB DDR3）
- 语音：支持内嵌在线语音 SDK + 双麦硬件降噪
- 存储：主控内置 DDR + 外挂 16M Flash + 128M SD Nand
- 继电器：最多 3 路（10A）
- 有线通讯：RS485 + 百兆以太网
- 供电：AC 220V / DC 9-24V
- OTA：支持
- 开机：3 秒
- **默认参数（开发直接照抄）**：uartDefaultBaud=115200；upgrade=U 盘 / TF 卡升级；resolution=480x480 / 720x720；voice=内嵌在线语音 SDK + 双麦硬件降噪；relay=最多 3 路（10A）；wired=RS485 + 百兆以太网；power=AC 220V / DC 9-24V；boot=3 秒开机
- 差异·同系列三平台差异：Z6 版 SW48480040B1（ARM9 600MHz，480×480，最低成本）/ Z20 版本型号（1.2GHz+128M DDR3，480×480 或 720×720，带在线语音）/ Z21 版 SW48480040E（1.0GHz，480×480）
- 数据来源：4 寸 86 盒系列规格书 V3.0（2025-05-20）
- 数据状态：complete

### SW8001280101D-JQ（Z20）

- 形态：10.1 寸彩色电子价签 PCBA（单屏）
- 摘要：10.1 寸 800x1280 竖屏；10.1 寸彩色电子价签 PCBA（单屏）
- 屏幕：尺寸(寸)=10.1，宽=800，高=1280，分辨率=800x1280，方向=portrait，接口=MIPI
- CPU：SSD201（Cortex-A7 双核 1.0GHz）
- DRAM：CPU 内置 DDR3 64MB
- 存储：128M SD NAND
- WiFi：2.4G USB WiFi6 模组（40Mbps，支持 50 台以上设备）+ BLE5.2 配网
- USB：micro USB（支持 U 盘升级）
- UART：1 路 TTL 3.3V（选配）
- 以太网：外接 RJ45-100M（选配）
- 音频：Audio line out（支持 1W 喇叭，选配）
- 供电：9-24V 宽压，不分正负极
- PCBA 尺寸：70 × 66.6 × 1.2 mm
- 顶屏能力：单屏
- **默认参数（开发直接照抄）**：uartDefaultBaud=115200；upgrade=U 盘 / TF 卡升级；resolution=800x1280；orientation=portrait；display=MIPI 10.1 寸竖屏；wifi=WiFi6 + BLE5.2 配网（组网模式）；power=9-24V 宽压，不分正负极；screens=1
- 差异·同款双型号差异：SW8001280101D-JQ = SSD201（1.0GHz / 64MB DDR3 / 仅单屏）；SW8001280101D1-JQ = SSD202（1.2GHz / 128MB DDR3 / 支持双屏异显）
- 数据来源：SW8001280101-SSD20X 平台价签 PCBA 规格 V1.0（2024-07-25）
- 数据状态：complete

### SW8001280101D1-JQ（Z20）

- 形态：10.1 寸彩色电子价签 PCBA（支持双屏）
- 摘要：10.1 寸 800x1280 竖屏；10.1 寸彩色电子价签 PCBA（支持双屏）
- 屏幕：尺寸(寸)=10.1，宽=800，高=1280，分辨率=800x1280，方向=portrait，接口=MIPI
- CPU：SSD202（Cortex-A7 双核 1.2GHz）
- DRAM：CPU 内置 DDR3 128MB
- 存储：128M SD NAND
- WiFi：2.4G USB WiFi6 模组 + BLE5.2 配网
- 供电：9-24V 宽压，不分正负极
- PCBA 尺寸：70 × 66.6 × 1.2 mm
- 顶屏能力：支持双屏（双屏异显）
- **默认参数（开发直接照抄）**：uartDefaultBaud=115200；upgrade=U 盘 / TF 卡升级；resolution=800x1280；orientation=portrait；display=MIPI 10.1 寸竖屏；wifi=WiFi6 + BLE5.2 配网（组网模式）；power=9-24V 宽压，不分正负极；screens=2
- 差异·同款双型号差异：与 SW8001280101D-JQ 硬件同板，差别只在主控（SSD202 1.2GHz / 128MB DDR3）与双屏能力
- 数据来源：SW8001280101-SSD20X 平台价签 PCBA 规格 V1.0（2024-07-25）
- 数据状态：complete

### SW80480070D_C（Z20）

- 形态：串口屏 / 工控整机（待确认）
- 别名：SW80480070D-C / SW80480070D
- 型号命名：字母 D = Z20 平台（沛哥 2026-09-12 确认：D=Z20、E=Z21）
- 摘要：7 寸 800x480 横屏；串口屏 / 工控整机（待确认）
- 屏幕：尺寸(寸)=7，宽=800，高=480，分辨率=800x480，方向=landscape
- 屏幕判定依据：按官方《产品规格型号说明》命名规则推导：SW+宽+高+尺寸+版本，SW80 480 070 D = 7 寸 800×480；型号字母 D = Z20 平台（沛哥确认）。同系列 SW80480070D-CK 规格书标 800×480 / 1024×600 可选
- **默认参数（开发直接照抄）**：uartDefaultBaud=115200；upgrade=U 盘 / TF 卡升级；resolution=800x480；orientation=landscape
- 资料：`wiki/flythings/datasheet/board/SW80480070D-CK系列型.pdf`
- 可选补充（非阻塞，按需补）：CPU/内存/接口配置（请提供规格书或确认）
- 可选补充（非阻塞，按需补）：型号后缀 _C 的确切含义（电容触摸？版本？）
- 可选补充（非阻塞，按需补）：与 SW80480070D-CK 系列是否同一产品
- 数据来源：命名规则（官方《产品规格型号说明》）+ 平台字母 D=Z20（沛哥确认）+ hardwarespec/SW80480070D-CK系列型.pdf
- 数据状态：partial

## Z21

- 平台定位：A7 双核 1.0GHz + 内置 64MB DDR2——串口屏/广告机/86盒主力平台
- 常见主控：SSD212 / SSD210 / T113-S3
- 平台默认参数：uartDefaultBaud=115200；upgrade=TF 卡升级（FAT32）
- 可选补充（非阻塞）：平台差异化说明（沛哥将补充；没有也不影响开工）

### SV50PD（Z21）

- 形态：Z21 平台开发板 / 核心板（邮票半孔 + XH2.54 插针双接口）
- 别名：SV50PD核心板
- 摘要：无自带屏：50Pin RGB888 通用接口屏，最大支持 1280×720 及以下；Z21 平台开发板 / 核心板（邮票半孔 + XH2.54 插针双接口）
- 屏幕：说明=无自带屏：50Pin RGB888 通用接口屏，最大支持 1280×720 及以下
- CPU：ARM 双核 A7 1200MHz
- 内存：64MB DDR2
- 存储：16M SPI NorFlash
- 屏幕接口：RGB888 50Pin，最大 1280×720
- 尺寸：65 × 56.3 × 1.2 mm
- 串口：UART ×3
- GPIO：×9
- I2C：TWI ×2
- SPI：×1
- PWM：×1
- ADC：×1
- USB：OTG ×1
- 以太网：EPHY ×1（外接变压器座子）
- 音频：LINE OUT + 按键蜂鸣器 ×1
- 扩展存储：TF 卡
- 开发环境：FlyThings IDE
- **默认参数（开发直接照抄）**：uartDefaultBaud=115200；upgrade=TF 卡升级（FAT32）；platform=Z21；display=RGB888 50Pin 通用接口屏；maxResolution=1280x720；uart=UART1 / UART2 / UART3（U3 带 CTS/RTS）；gpio=GPIO0~GPIO8（9 路；PA0-PA7 可复用 ETH0_*，详见 pinGroups）；i2c=I2C0 / I2C1（10PIN 座子另引 3.3V 电平 I2C）；spi=SPI（CS/CLK/MOSI/MISO）；pwm=PWM3；adc=SRA0；usb=OTG x1；ethernet=ETHY（RN/RP/TN/TP，外接变压器座子）；storage=TF 卡；audio=LINE OUT + 按键蜂鸣器；power=5V（4.2-5.4V @2A），板载 3.8~5.2V 工作范围；lcdBus=RGB888（B7-B0 / G7-G0 / R7-R0 + DCLK/DE/VSYNC/HSYNC）；touch=电容触摸（CTP：I2C + INT + RST）；A1=TP-INT、B1=TP-RST；temp=工作 -20~80℃，储存 -30~90℃
- 资料：`wiki/flythings/datasheet/board/SV50PD核心板规格书V3.0-20210813.pdf`
- 资料：`hardwarespec/SV50PD/SV50PD核心板规格书V3.0-20210813.pdf`

#### 管脚定义 · 44PIN 邮票孔 + 插针口（共用）

| PIN | 名称 | 默认功能 | IO | 复用 | 备注 |
|---|---|---|---|---|---|
| 1 | ID | USB-ID | I/O |  | 与 MICRO 座是同一个 USB 口 |
| 2 | DM | USB-DM | I/O |  |  |
| 3 | DP | USB-DP | I/O |  |  |
| 4 | GND | GND | P |  |  |
| 5 | PA0 | GPIO0 | I/O | ETH0_MDI |  |
| 6 | PA1 | GPIO1 | I/O | ETH0_MDC |  |
| 7 | PA2 | GPIO2 | I/O | ETH0_COL |  |
| 8 | PA3 | GPIO3 | I/O | ETH0_RXD0 |  |
| 9 | PA4 | GPIO4 | I/O | ETH0_RXD1 |  |
| 10 | PA5 | GPIO5 | I/O | ETH0_TX_CLK |  |
| 11 | PA6 | GPIO6 | I/O | ETH0_TXD0 |  |
| 12 | PA7 | GPIO7 | I/O | ETH0_TXD1 |  |
| 13 | R | LINE OUT R | A |  |  |
| 14 | L | LINE OUT L | A |  |  |
| 15 | CS | SPI-CS | I/O |  |  |
| 16 | CLK | SPI-CLK | I/O |  |  |
| 17 | SI | SPI-MOSI | I/O |  |  |
| 18 | SO | SPI-MISO | I/O |  |  |
| 19 | SCL0 | I2C_SCL0 | I/O |  |  |
| 20 | SDA0 | I2C_SDA0 | I/O |  |  |
| 21 | SCL1 | I2C_SCL1 | I/O |  |  |
| 22 | SDA1 | I2C_SDA1 | I/O |  |  |
| 23 | PWM3 | PWM3 | I/O |  |  |
| 24 | TX1 | UART1_TX | I/O |  |  |
| 25 | RX1 | UART1_RX | I/O |  |  |
| 26 | TX2 | UART2_TX | I/O |  |  |
| 27 | RX2 | UART2_RX | I/O |  |  |
| 28 | U3-TX | UART3_TX | I/O |  |  |
| 29 | U3-RX | UART3_RX | I/O |  |  |
| 30 | U3-CTS | UART3_CTS | I/O |  |  |
| 31 | U3-RTS | UART3_RTS | I/O |  |  |
| 32 | W-EN | WIFI-POW-EN | I/O |  |  |
| 33 | RN | ETHY-RN | I/O |  |  |
| 34 | RP | ETHY-RP | I/O |  |  |
| 35 | TN | ETHY-TN | I/O |  |  |
| 36 | TP | ETHY-TP | I/O |  |  |
| 37 | LED0 |  | O |  |  |
| 38 | LED1 |  | O |  |  |
| 39 | SRA0 | ADC | I/O |  |  |
| 40 | PA-EN | PA-EN | I/O |  |  |
| 41 | PA8 | GPIO8 | I/O |  |  |
| 42 | GND | GND | P |  |  |
| 43 | 5V | 5V 电源输入 | P |  |  |
| 44 | 5V | 5V 电源输入 | P |  |  |
| A1 | INT | TP-INT | I/O |  |  |
| B1 | TP-RST | TP-RST | I/O |  |  |


#### 管脚定义 · 10PIN 1.0mm 座子（电源/串口）

| PIN | 名称 | 默认功能 | IO | 备注 |
|---|---|---|---|---|
| 1-3 | 5V | DC 5V 电源 | P | 输入范围 4.2-5.4V @ 2A |
| 4 | RX2 | UART2-RX |  | UART2，做屏幕调试/通信串口 |
| 5 | RX1 | UART1-RX |  | UART1，做屏幕调试/通信串口 |
| 6 | TX1 | UART1-TX |  | UART1，做屏幕调试/通信串口 |
| 7 | TX2 | UART2-TX |  | UART2，做屏幕调试/通信串口 |
| 8-10 | GND | GND | P |  |


#### 管脚定义 · 6PIN 0.5mm CTP 座子（电容触摸）

| PIN | 名称 | 默认功能 | 备注 |
|---|---|---|---|
| 1 | CTP-RST |  | 触摸复位 |
| 2 | CTP-VCC |  | 触摸供电 3.3V |
| 3 | GND |  | 地 |
| 4 | CTP-INT |  | 触摸中断 |
| 5 | CTP-SDA | I2C-SDA | I2C 数据，3.3V 电平 |
| 6 | CTP-SCL | I2C-SCL | I2C 时钟，3.3V 电平 |


#### 管脚定义 · 50PIN 0.5mm RGB-LCD 接口

| PIN | 名称 | 默认功能 | IO |
|---|---|---|---|
| 1-2 | LEDA | 背光阳极 | P |
| 3-4 | LED- | 背光阴极 | P |
| 5 | GND | 电源地 | P |
| 6 | VCOM | LCD Common Voltage | P |
| 7 | VCC-LCD | LCD 电源输出（3.0V） | P |
| 8 | MODE | DE / SYNC 模式选择 | O |
| 9 | DE | DE 模式时高有效使能数据输出 | O |
| 10 | VSYNC | 场同步输出（并行 RGB） | O |
| 11 | HSYNC | 行同步输出（并行 RGB） | O |
| 12-19 | B7-B0 | 蓝色数据输出 | O |
| 20-27 | G7-G0 | 绿色数据输出 | O |
| 28-35 | R7-R0 | 红色数据输出 | O |
| 36 | GND | 电源地 | P |
| 37 | DCLK | 输出数据时钟 | O |
| 38 | GND | 电源地 | P |
| 39 | L/R | 水平翻转 | O |
| 40 | U/D | 垂直翻转 | O |
| 41 | VGH | TFT Gate On Voltage | P |
| 42 | VGL | TFT Gate Off Voltage | P |
| 43 | AVDD | 模拟电路电源 | P |
| 44 | LCD-RST | LCD 复位脚 | O |
| 45 | NC | 空脚 |  |
| 46 | VCOM | LCD Common Voltage | P |
| 47 | DITHE | Dithering 使能控制 | O |
| 48 | GND | 电源地 | P |
| 49-50 | NC | 空脚 |  |

- 可选补充（非阻塞，按需补）：开发板整机出厂配屏分辨率（若有默认配屏请给：常见 7 寸 800×480 / 1024×600）
- 数据来源：SV50PD 核心板规格书 V3.0（2021-08-13）
- 数据状态：complete

### SW10600070E_C（Z21）

- 形态：7 寸串口屏整机（高清 1024×600，电容触摸；与 SV50PD 同系列资料）
- 别名：SW10600070E-C / SW10600070D_C / SW10600070D-C
- 型号命名：字母 E = Z21 平台（沛哥 2026-09-12 确认：D=Z20、E=Z21）
- 摘要：7 寸 1024x600 横屏；7 寸串口屏整机（高清 1024×600，电容触摸；与 SV50PD 同系列资料）
- 屏幕：尺寸(寸)=7，宽=1024，高=600，分辨率=1024x600，方向=landscape，触摸=GT911 电容触摸（P+G 材质）
- 屏幕判定依据：规格书 V1.0 第 3 节：7 寸 1024*600 24bit 16.7M 色，亮度 250cd/m²，GT911 电容触摸 P+G
- ⚠️ 早期内部标签/文档误写为 SW10600070D_C（历史遗留问题，不影响规格）——实际型号 SW10600070E_C，字母 E = Z21 平台
- CPU：ARM 双核 A7 1200MHz
- RAM：64MB
- 存储：16M SPI Nor Flash
- 供电：DC 5V / 1A（接口电压范围 4.5-5.4V@1A）
- 串口：UART0 / UART1 / UART2（TTL 3.3V，波特率 1200~921600bps）
- TF 卡：FAT32
- USB：支持 UVC 摄像头 / AVIN 输入设备
- 外设：SPI 接口、KEY ADC
- 开发环境：FlyThings IDE
- 尺寸：121.9(宽) × 74.7(高) × 14.5(厚) mm，净重 120g
- 工作温度：-10~60℃
- 存储温度：-20~70℃
- **默认参数（开发直接照抄）**：uartDefaultBaud=115200；upgrade=TF 卡升级（FAT32）；resolution=1024x600；orientation=landscape；display=7 寸 1024x600 24bit 16.7M 色，亮度 250cd/m2；touch=GT911 电容触摸（P+G）；uart=UART0 / UART1 / UART2（TTL 3.3V，默认 115200）；baudRange=1200~921600 bps；power=DC 5V / 1A；storage=16M SPI Nor Flash + TF 卡（FAT32）；ram=64MB
- 资料：`wiki/flythings/datasheet/board/SW10600070D_C(sv50pd).pdf`
- 资料：`wiki/flythings/datasheet/board/SV50PD核心板规格书V3.0-20210813.pdf`
- 可选补充（非阻塞，按需补）：同系列另一型号 SW10600070D_TC（7 寸高清电容屏带铁框）是否也入库
- 数据来源：SW10600070E_C 规格书 V1.0（2021-03-20，文档内写作 D_C）+ 平台字母 E=Z21（沛哥确认）
- 数据状态：complete

### SW48480040E（Z21）

- 形态：4 寸 86 盒智能面板（Z21 版）
- 摘要：4 寸 480x480 横屏；4 寸 86 盒智能面板（Z21 版）
- 屏幕：尺寸(寸)=4，宽=480，高=480，分辨率=480x480，方向=landscape
- 平台：Z21
- 继电器：最多 3 路（10A）
- 有线通讯：RS485 + 百兆以太网
- 无线：内置 WiFi 模块，可扩展 Zigbee/Bluetooth/离线语音模块
- 音频：内置 1W 功放小喇叭
- 供电：AC 220V 强电 / DC 9-24V 弱电
- 存储：主控内置 DDR + 外挂 16M Flash + 128M SD Nand
- 传感器：可选光感 / 人体测距
- OTA：支持
- 开机：3 秒
- **默认参数（开发直接照抄）**：uartDefaultBaud=115200；upgrade=TF 卡升级（FAT32）；resolution=480x480；relay=最多 3 路（10A)；wired=RS485 + 百兆以太网；wireless=内置 WiFi，可扩 Zigbee / Bluetooth / 离线语音模块；audio=内置 1W 功放喇叭；power=AC 220V / DC 9-24V；storage=内置 DDR + 16M Flash + 128M SD Nand；sensor=光感 / 人体测距（可选）；boot=3 秒开机
- 差异·同系列三平台差异：同款 4 寸 86 盒有 Z6（SW48480040B1，480×480）/ Z20（SW48480040D1）/ Z21（SW48480040E）三个平台版本；Z20 版支持 720×720 与在线语音 SDK + 双麦降噪，Z21 版为 480×480 且无在线语音
- 数据来源：4 寸 86 盒系列规格书 V3.0（2025-05-20）
- 数据状态：complete

### SW48854050E1（Z21）

- 形态：5 寸串口屏整机
- 摘要：5 寸 480x854 竖屏；5 寸串口屏整机
- 屏幕：尺寸(寸)=5，宽=480，高=854，分辨率=480x854，方向=portrait，触摸=电容触摸
- CPU：ARM Cortex-A7 双核 1GHz
- 存储：16M NorFlash
- UART：×2（默认 115200）
- USB：下载调试，默认 Host
- 音频：默认蜂鸣器（SPK 二选一）
- RTC：选配
- 电源：DC 5V / 1000mA
- **默认参数（开发直接照抄）**：uartDefaultBaud=115200；upgrade=TF 卡升级（FAT32）；resolution=480x854；orientation=portrait；touch=电容触摸；uart=2 路（默认 115200）；usb=下载调试，默认 Host；rtc=选配；power=DC 5V / 1000mA
- 数据来源：Z21 5 寸串口屏规格书 V1.0（2025-07-25）
- 数据状态：complete
