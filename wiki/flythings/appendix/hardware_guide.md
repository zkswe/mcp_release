---
title: 硬件使用说明
---

## 使用前注意事项
- 确定电源电压一定为4.5-5.5V
- 确定好串口电平是RS232、TTL还是RS485
- 注意电源接口座的接口定义

## 电源接口说明

### PH2.0-8PIN座子接口定义
| PIN | 定义 |
|-----|------|
| 1PIN | DC5V |
| 2PIN | RESET |
| 3PIN | CTS |
| 4PIN | TXOUT/B (RS485-B) |
| 5PIN | RXIN/A (RS485-A) |
| 6PIN | RTS |
| 7PIN | GND |
| 8PIN | GND |

### 10PIN 1.0FPC座子接口定义
| PIN | 定义 |
|-----|------|
| 1/2/3PIN | DC5V |
| 4PIN | RTS |
| 5PIN | RXIN/A (RS485-A) |
| 6PIN | TXOUT/B (RS485-B) |
| 7PIN | CTS |
| 8/9/10PIN | GND |

## 串口输出方式选择
0R电阻是TTL，不焊接0R是RS232。
