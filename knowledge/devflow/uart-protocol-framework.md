---
id: devflow-uart-protocol-framework
title: 串口通讯（UART）框架与协议对接 —— UartContext 读线程 + ProtocolParser/Sender + SProtocolData 共享变量 + UI 生命周期接线
category: devflow
status: review
confidence: offline
verified_at: 2026-10-03
stale_days: 180
origin: total
source: 2026-10-03 收录：逐行读 templates/HelloWord_Z20/src/{Main.cpp, uart/*}（9 文件，本仓 19 处工程共用、171 份逐字节一致，唯一来源见 scripts/sync_project_skeleton.py）+ mainActivity.cpp 的注册/反注册 + CommDef.h 宏开关
needs_evidence: true
platforms: []
tags: [串口, UART, 协议, 帧格式, 半包, 粘包, SProtocolData, 校验, 波特率, ttyS, 通讯, 帧头, listener, Modbus]
evidence: []
---
# 串口通讯（UART）框架与协议对接

> 检索导引：问「串口怎么通信 / UART 怎么用 / 协议怎么对接 / 收到数据怎么刷界面 / 粘包拆包怎么办 /
> 帧头帧尾怎么定 / 校验和怎么加 / SProtocolData 是什么 / onProtocolDataUpdate 怎么用 /
> 波特率写哪 / ttyS 怎么选 / 双串口怎么做 / Modbus 能不能用 / 485 怎么做」→ 本文。
> 板级串口**设备名与默认波特率**（哪块板有几个 UART、EasyUI.cfg 的 `uart`/`baud` 键）→
> `knowledge/hardware/hardware-models.md` + `knowledge/devflow/package-properties-easyui-cfg.md`。
> 第三方协议栈（Modbus / OPC-UA / DLT645 …）怎么引进工程 → `knowledge/devflow/open-source-stack-integration.md`。

## 0. 边界声明：MCP 管「FlyThings 侧的约定」，不管「协议本身」（**先读**）

需求方 2026-10-03 定：

> 「UART 部分在 demo 程序里面有 uart 的框架。这个是基于标准的 linux uart，但是结合 UI 的生命周期
> 以及框架做了 `SProtocolData` 共享变量的设计。……类似的 modbus 和其他协议都是可以借用
> **linux、arduino 生态的开源代码复用**。MCP 更多的是为了 **FlyThings 系统和 UI 的一些约定**而来。」

于是本文的分工判据只有一条：

| 你的问题 | 去哪 |
|---|---|
| 「**怎么接进 FlyThings**」——开串口的时机、订阅怎么挂到 Activity、收到数据怎么刷 UI、共享变量怎么用 | **本文**（这是 MCP 的独有价值） |
| 「**帧怎么编/怎么解**」——Modbus RTU 的 CRC16、DLT645 的报文、自定义协议的字段语义 | **协议本身**：优先用 Linux/Arduino 生态现成实现（libmodbus、modbus-esp8266、各类轻量 codec），**别在 MCP 里造第二份**；引进工程的四判据与 libc 匹配见 `open-source-stack-integration.md` |
| 「**串口设备名/波特率给我什么值**」 | `hardware-models.md`（板级默认参数）+ `package-properties-easyui-cfg.md`（`uart`/`baud` 键） |

> ⚠️ 换句话说：**本文里的帧格式（`FF 55 | CmdID | DataLen | Data | [CheckSum]`）是模板示例，不是平台规定**。
> 接 Modbus 就换成 Modbus 的帧，**要改的只有 `CommDef.h` / `ProtocolParser.cpp` / `ProtocolSender.cpp`
> 三处**（见 §7），**框架其余部分一行都不用动** —— 这正是这套骨架的设计意图。

## 1. 数据流（一张图看懂谁调谁）

```
对端设备
   │  (RS232/TTL/485 电平，8N1 无流控)
   ▼
  ttyS*  ── termios raw + O_NONBLOCK ──►  UartContext（Thread 子类，单例 UARTCONTEXT）
                                              │  ① read() 追加到 16KB 拼接缓冲尾部
                                              │  ② parseProtocol(buf, mDataBufLen) → 返回**已消费字节数**
                                              │  ③ 残留半包 memcpy 到缓冲头部，下轮继续拼
                                              ▼
                                       ProtocolParser.cpp
                                              │  procParse(frame) 填 static SProtocolData
                                              ▼
                                  notifyProtocolDataUpdate(sProtocolData)
                                              │  （Mutex 保护，遍历 listener 数组）
                                              ▼
                       你的 static void onProtocolDataUpdate(const SProtocolData &data)
                                              │  ⚠️ 这一跳**在串口线程上**，不是 UI 线程
                                              ▼
                                           UI / 业务

反向：UI 线程 ──► sendProtocol(cmdID, data, len) ──► UARTCONTEXT->send() ──► write(ttyS*)
```

## 2. 文件清单与职责（**改哪个先看这张表**）

| 文件 | 职责 | 你要不要动 |
|---|---|---|
| `src/Main.cpp` | **app 级**接线：`onEasyUIInit` 开串口、`onEasyUIDeinit` 关串口 | 通常不动（除非多串口） |
| `src/uart/UartContext.h/.cpp` | Linux 串口本体：`open/termios/O_NONBLOCK` + `Thread` 读线程 + 16KB 拼接缓冲 + `send()` | **一般不动**（这是框架） |
| `src/uart/CommDef.h` | 帧常量与开关：`CMD_HEAD1/2`、`DATA_PACKAGE_MIN_LEN`、`DEBUG_PRO_DATA`、`PRO_SUPPORT_CHECK_SUM` | **要动**：换帧头/开校验/开调试打印 |
| `src/uart/ProtocolData.h` | **共享数据**：`struct SProtocolData` + CmdID 表 + 错误码 | **要动**：加字段/加 CmdID |
| `src/uart/ProtocolParser.h/.cpp` | 收：拆帧 + 填共享数据 + 通知订阅者；`listener` 注册表 | **要动**：按你的帧格式改 `procParse`/`parseProtocol` |
| `src/uart/ProtocolSender.h/.cpp` | 发：按帧格式组包 | **要动**：按你的帧格式改 `sendProtocol` |
| `src/activity/mainActivity.cpp` | **page 级**接线：`onCreate` 注册 listener、析构反注册 | **要动**：每个想收数据的页面各挂一次 |

**这 9 个文件是**：`Main.cpp` + `uart/{CommDef.h, ProtocolData.h, ProtocolParser.cpp/.h, ProtocolSender.cpp/.h, UartContext.cpp/.h}`。
**唯一来源 = `templates/HelloWord_Z20/src`**：本仓 19 处工程（7 个平台模板 + 7 个 demo + 5 个组件示例）带的都是它的副本，
其中 171 份文件**逐字节一致**（`CONSOLIDATION.md` §13）。
→ **要修框架 bug 就改唯一来源**，然后 `python scripts/sync_project_skeleton.py --apply` 同步（`--check` 已进门禁）。
⚠️ 同步**只覆盖** `src/Main.cpp` 与 `src/uart/*` —— **绝不碰** `src/logic/*`（你的业务）与 `src/activity/*`（IDE 生成）。

## 3. 两段生命周期接线（这是「结合 UI 生命周期」的落点）

### 3.1 app 级：串口跟着**应用**开合（不是页面）

```cpp
// src/Main.cpp
void onEasyUIInit(EasyUIContext *pContext) {
    UARTCONTEXT->openUart(CONFIGMANAGER->getUartName().c_str(),
                          CONFIGMANAGER->getUartBaudRate());
}
void onEasyUIDeinit(EasyUIContext *pContext) { UARTCONTEXT->closeUart(); }
const char* onStartupApp(EasyUIContext *pContext) { return "mainActivity"; }
```

- 串口名与波特率**从工程配置读**（EasyUI.cfg 的 `uart`/`baud`），**不要写死 ttyS0** —— 不同板子枚举不同（见 §11）。
- 串口的生存期 = **整个应用**：页面来回切换**不会**重开串口，`openUart` 只调一次。
- ⚠️ **`openUart()` 的返回值在模板里没有检查** → 名字/波特率配错时**不会报错**，现象是"收不到数据"。
  一眼发现：`adb shell logcat -d | findstr openUart`，看 `mIsOpen = 0`。

### 3.2 page 级：订阅挂在 **Activity** 上（谁用谁注册）

```cpp
// src/activity/mainActivity.cpp —— 由 IDE 生成，但注册/反注册这两行是模板给的
mainActivity::~mainActivity() { ... unregisterProtocolDataUpdateListener(onProtocolDataUpdate); ... }
void mainActivity::onCreate()  { ... registerProtocolDataUpdateListener(onProtocolDataUpdate); ... }
// src/logic/mainLogic.cc —— 业务侧：这是个**静态**回调
static void onProtocolDataUpdate(const SProtocolData &data) { /* 刷 UI */ }
```

- `onProtocolDataUpdate` 是**生命周期钩子**（签名/时机/坑的权威 = `knowledge/devflow/activity-lifecycle-spec.md`，
  真源 `lifecycle_spec.json`）；本文只说它与串口框架的关系。
- **构造注册、析构反注册**必须成对：只在 `onCreate` 注册而忘了反注册 → 页面销毁后**悬垂函数指针**，
  下一帧数据到达时调进已销毁页面的代码 → 崩（`activity-lifecycle-spec.md` 的 R6 已把「反注册一切 listener」列为铁律）。
- 回调是 **static**，所以不依赖 `this` —— 但**回调里访问 UI 控件就等于跨线程碰 UI**（见 §8-3）。

## 4. `SProtocolData`：共享变量的设计（**这套骨架的核心**）

### 4.1 它是怎么设计的

```cpp
// ProtocolData.h —— 你按业务加字段
typedef struct { BYTE power; } SProtocolData;      // ← 全局唯一一份

// ProtocolParser.cpp
static SProtocolData sProtocolData;                 // 静态存储，进程唯一
SProtocolData& getProtocolData() { return sProtocolData; }   // ① 随时可取当前值

static void procParse(const BYTE *pData, UINT len) {
    switch (MAKEWORD(pData[3], pData[2])) {         // CmdID 高字节在前
    case CMDID_POWER: sProtocolData.power = pData[5]; break;
    }
    notifyProtocolDataUpdate(sProtocolData);        // ② 每收一帧就通知
}
```

三条设计意图（**这就是它相对"裸写串口"的价值**）：

1. **收与用解耦**：串口线程只负责"把线上字节变成结构体字段"，UI 侧只读结构体或等通知；
   双方不需要知道对方存在。
2. **两种取数方式并存**：
   - **推**：`registerProtocolDataUpdateListener(fn)` → 每收一帧调一次（适合"变了就刷界面"）；
   - **拉**：`getProtocolData()` → 随时读当前快照（适合定时器里轮询，避免高频刷新）。
3. **单一数据源**：同一份 `SProtocolData` 就是"设备当前状态"的唯一定义，多个页面共享，不各存一份。

### 4.2 用它的四条纪律（都是这套设计**必然**带来的，不是可选风格）

1. ⚠️ **回调拿到的是 `const SProtocolData&`，而它指向的是那个全局单例** —— **想留下来必须自己拷贝**。
   保存指针/引用 = 下次解析就把你手里的值改了（`static SProtocolData` 原地覆盖）。
2. ⚠️ **`getProtocolData()` 在"第一帧到达之前"返回的是零初始化值**（C++ 静态存储期）。
   模板**没有"是否已收到过数据"的标志** → `power == 0` 到底是"设备报 0"还是"还没收到"**区分不了**。
   要在 UI 上区分，得自己加一个 `bool received`（或把字段设计成有"无效"取值）。
3. ⚠️ **全局单例 = 多串口/多协议会互相覆盖**（见 §9）。一个 `SProtocolData` 装不下两路独立协议的数据。
4. ⚠️ **`notifyProtocolDataUpdate` 是持锁遍历 listener 的**（见 §8-2）→ 别在回调里增删 listener。

## 5. 帧格式与解析契约（模板示例帧）

```
FF 55 | CmdID(2B, 高字节在前) | DataLen(1B) | Data(N) | [CheckSum(1B)]
 0  1        2      3              4          5..        末字节
```

| 常量（`CommDef.h`） | 值 | 说明 |
|---|---|---|
| `CMD_HEAD1` / `CMD_HEAD2` | `0xFF` / `0x55` | 同步帧头 |
| `DATA_PACKAGE_MIN_LEN` | **5**（无校验）/ **6**（开校验） | = 帧头2 + CmdID2 + DataLen1 (+CheckSum1) |
| `PRO_SUPPORT_CHECK_SUM` | 默认**注释掉**（关） | 打开后帧尾加 1 字节校验 |
| `DEBUG_PRO_DATA` | 默认**注释掉**（关） | 打开后每帧打印原始字节（`LOGD`） |

- **校验算法**（`getCheckSum`）：`(BYTE)(~sum + 1)`，即"逐字节求和取反加一"（补码）。
  开校验后**两端必须一致**，且最小帧长从 5 变 6 —— 忘改一端 = 全部帧判为校验错（`CheckSum error!!!!!!`）。
- **`parseProtocol()` 的返回值语义 = 「本次消费了多少字节」**，这是整个读线程的地基：
  - 逐字节扫到 `FF 55` 才认帧头 → **自动对齐乱序/前导垃圾**；
  - `frameLen = DataLen + DATA_PACKAGE_MIN_LEN`，若 `frameLen > remainLen` → `break`（**半包，等下次再拼**）；
  - 返回值 `len - remainLen`，调用方据此把残留搬到缓冲头部。
  ⚠️⚠️ **返回值必须是 0..len 且 ≥ 0**：`UartContext::threadLoop()` 里是 `mDataBufLen -= len` **无条件执行** ——
  你改成"出错返回 -1"这种自然写法，`mDataBufLen` 会**变大**，下一轮 `read` 就往缓冲区外写。
  **要报错就走 `LOGE`，不要用负返回值。**
- **粘包/拆包天然解决**：靠"16KB 拼接缓冲 + 消费字节数 + 残留前移"三件套，不需要自己 sleep/攒包。

## 6. 发送

```cpp
bool sendProtocol(const UINT16 cmdID, const BYTE *pData, BYTE len);   // ProtocolSender.h
```

- 组帧后一次 `UARTCONTEXT->send(buf, frameLen)` → `write(ttyS*, ...)`。
- **长度上限**：`dataBuf[256]` 栈上缓冲，且 `len + DATA_PACKAGE_MIN_LEN > 256` 直接返回 `false`
  → **data ≤ 251 字节（无校验）/ 250（有校验）**，超了会明确报错（不静默截断）。
- ⚠️ **单帧是一次 `write()`，但 `send()` 里没有锁**：UI 线程与串口线程同时发，两帧可能交错
  （`write` 对 tty 不保证跨线程原子）。**多线程都要发**时自己加锁，或统一收敛到一个发送线程。
- ⚠️ 部分写被当失败：`write(...) != len` → 返回 `false`，但**已写出的那部分字节已经上线路了**
  → 收不到 `true` 不代表对端没收到半帧，重发要做幂等/序号设计。

## 7. 加一条协议 / 换一个协议：只改三处

| 步骤 | 改哪 | 做什么 |
|---|---|---|
| ① 定帧 | `CommDef.h` | 改 `CMD_HEAD1/2`、`DATA_PACKAGE_MIN_LEN`；要不要校验（`PRO_SUPPORT_CHECK_SUM`）；对码时可以开 `DEBUG_PRO_DATA` |
| ② 定数据 | `ProtocolData.h` | 往 `SProtocolData` 加字段；加 `CMDID_xxx` |
| ③ 收 | `ProtocolParser.cpp` | `parseProtocol` 按你的帧格式找头/算长；`procParse` 的 `switch` 里填字段，**并自己校验 `DataLen` 再取 Data**（见 §8-1） |
| ④ 发 | `ProtocolSender.cpp` | `sendProtocol` 按你的帧格式组包（含校验） |
| ⑤ 用 | `mainLogic.cc` | `onProtocolDataUpdate` 里刷 UI / 存业务状态 |

**框架其余部分（`UartContext`、读线程、缓冲、listener 机制、生命周期接线）一行都不用改** —— 这是设计意图。

> **要接 Modbus 这类标准协议**：先按 `open-source-stack-integration.md` 的四判据评估现成库（libmodbus 等），
> 再把"库的回调结果"塞进上面 ②③⑤ 三个位置（即：库负责编解码，你负责把它接到 `SProtocolData` 与 UI）。
> **不要**为了"统一"而把 Modbus 的 CRC/功能码语义写进 `UartContext`。

## 8. 硬约束与铁律（**逐条从代码读出来的**，不是经验之谈）

1. ⚠️ **`procParse` 里 `pData[5]` 没有边界校验**（模板 `case CMDID_POWER` 直接取第 6 字节）。
   帧长校验只保证**这一帧**有 `frameLen` 字节；当 `DataLen = 0` 时 `frameLen` 也是 5，
   于是 `pData[5]` 读到的是**下一帧的第一个字节**（或缓冲区里未解析区域）——
   不会崩，但**值是错的**，而且只在 `DataLen=0` 的帧上出现，极难查。
   → **铁律：`procParse` 里先按 `DataLen` 判够不够再取 Data**。
2. ⚠️ **回调里增删 listener = 死锁**：`notifyProtocolDataUpdate` **持 `sLock` 调用**每个 listener，
   而 `register/unregisterProtocolDataUpdateListener` 也要同一把 `sLock`（非递归）→
   在 `onProtocolDataUpdate` 里 register/unregister 会**自锁死**（表现为界面卡死、无崩溃栈）。
3. ⚠️ **`onProtocolDataUpdate` 跑在串口线程上**，**不是 UI 线程**。
   - 别在回调里直接 `setText()` / 改控件（跨线程碰 UI，见 `knowledge/uicontrols/cross-thread-ui-rule.md`）；
   - 别在回调里做耗时活（会**阻塞串口读线程** → 后面所有帧都延迟，甚至读缓冲堆积）；
   - 推荐姿势：回调里只**落标志位/拷贝数据**，UI 刷新交给 `onUI_Timer`（UI 线程）或页面 `onUI_show`。
4. ⚠️ **`parseProtocol` 返回负数会撑爆缓冲**（见 §5 末）—— 报错走 `LOGE`。
5. ⚠️ **忘了反注册 listener** → 页面销毁后收到数据即崩（§3.2）。
6. ⚠️ **`openUart` 的失败不报错**（§3.1）—— 上线前用 `logcat` 核一次 `mIsOpen = 1`。
7. ⚠️ **波特率必须落在模板支持表内**（`B1200`…`B921600`）：`UartContext::getBaudRate()` 只在**日志**里做映射，
   实际是把 `CONFIGMANAGER->getUartBaudRate()` 的**数值常量**直接写进 `c_cflag`；
   填了表外的值不会报错，只是**波特率不对**（现象：全是乱码或一个字节都收不到）。
8. ⚠️ **`if (mUartID <= 0)` 把 fd 0 当失败**：`fd 0` 通常是 stdin，实践上 `open()` 会返回 ≥3 所以不发作；
   严格判定应是 `mUartID < 0`。**知道有这回事即可，别据此改框架**（改了要过骨架门禁）。
9. ⚠️ **`closeUart()` 不 join 读线程**：`requestExit()` 后立刻 `close(fd)`，而读线程可能正阻塞在 `read` 上
   / 或在用 `mDataBufPtr`。单例在进程退出时才析构，实践中风险小 —— **但自己 new 第二个 UartContext 时要注意**。
10. **`SProtocolData` 是全局单例** → 多串口/多协议互相覆盖（§4.2-3、§9）。
11. 对码阶段先开 `DEBUG_PRO_DATA`（`CommDef.h` 里去掉注释即可逐帧打字节），**验完关掉**（否则日志量极大、拖慢读线程）。

## 9. 多串口（`DoubleUartDemo` 的做法与代价）

参考 Demo 的改法：**单例 → 双实例**（`UartContext::init()` new 出 `ttyS0`/`ttyS1` 两条 + 各自读线程与缓冲），
`parseProtocol(uart, ...)` 带 `uart_from` 标区分来源，`sendProtocolTo(uart, cmdID, ...)` 按口发。

代价（已登记口径）：**`SProtocolData` 与 listener 数组仍是共享的** →
高吞吐时会出现**字段互相覆盖**、**回调交错**。多口业务建议**每口一份数据**（各自的结构体或按口分表），
别指望一个单例装两路。

## 10. 未收录 / 待补（**如实登记**）

| 项 | 状态 |
|---|---|
| 本文所有结论的来源 | **只读代码**（模板 + activity），**未真机跑过串口**（无对端设备）；标 `needs_evidence: true` |
| `SProtocolData` 的"是否已收到首帧"缺口 | 模板**没有**该标志（§4.2-2）——要不要加进唯一来源，等你定 |
| `parseProtocol` 负返回值的防护 | 只在本文记了铁律，**框架代码未加保护**（改它要过骨架门禁 + 19 处同步） |
| `send()` 的并发保护 | 框架无锁（§6）——高并发场景待真机验证影响面 |
| Modbus / 485 / DLT645 等**协议层** | **不在本文范围**（§0）：走 Linux/Arduino 生态现成实现 |
| `DoubleUartDemo` 的完整源码口径 | 本文只留结论；它不在本仓 19 处骨架里（是训练期 Demo） |

## 11. 相关

- `knowledge/devflow/activity-code-skeleton.md` §5：串口在 activity 骨架里的位置（本文是它的展开与权威）
- `knowledge/devflow/activity-lifecycle-spec.md`：`onProtocolDataUpdate` 钩子语义、`register/unregister` 铁律（真源 `lifecycle_spec.json`）
- `knowledge/uicontrols/cross-thread-ui-rule.md`：为什么不能在串口线程直接刷 UI
- `knowledge/devflow/package-properties-easyui-cfg.md`：`uart` / `baud` 键口径（串口名从哪来）
- `knowledge/hardware/hardware-models.md`：各板 UART 路数与管脚（如 Z21 有 UART1/2/3，U3 带 CTS/RTS）
- `knowledge/devflow/open-source-stack-integration.md`：引第三方协议栈的四判据 + libc 匹配
- `knowledge/devflow/mqtt-client-lifecycle.md`：另一条"通信 + 生命周期"的路（网络侧，可对照读）
