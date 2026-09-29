---
id: t113-car-dashboard-can-arch
title: 🚗 T113 车载仪表盘 CAN 应用架构（DashBoard_T113 三套工程实测）
category: t113-car
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [T113]
tags: [来源：`projects, BMW, Comaro, Jeep, Pointer, 三套仪表工程]
evidence: []
---
# 🚗 T113 车载仪表盘 CAN 应用架构（DashBoard_T113 三套工程实测）

> 检索导引：问「T113 仪表盘 CAN 怎么收 / 车速转速档位怎么解包 / SocketCAN can0 500k 配置 / 仪表指针动画几种做法 / 换车型改哪里」→ 本文（BMW/Comaro/Jeep 三套工程提炼）。
> 2026-09-07 沛哥安排：学习整车代码后提炼入库（来源：`projects/LearningProject/DashBoard_T113/`，BMW/Comaro/Jeep(Pointer) 三套仪表工程，ZKSWE Develop Team 编写）。
> 适用：T113 平台 CAN 仪表盘（车速/转速/档位/故障灯/保养），想抄架构先看这篇。
> ⚠️ 本文只收录 CAN 应用架构；指针动画具体实现（BMW 预渲染帧序列等）属工程自有技术，细节未收录。

## 0. 一句话架构

**CAN 收线程（SocketCAN，can0 500k）→ `can::parseProtocol(can_frame)` 查 ID 表逐位解包 → 更新全局 `DashboardData` → 遍历注册回调 `CanDataCb` 通知页面 → 页面差异比较后刷新 UI。**

三套工程同源（作者一致），但动画方案与协议分组不同：

| 工程 | 车型/风格 | CAN 封装 | 指针动画方案 | 灯状态 | 备注 |
|------|----------|---------|-------------|--------|------|
| BMW | 宝马多模式(mode1-6)+HDMI | `can/socket_can.{h,cpp}` + `can/context.{h,cpp}`（新版） | 指针帧图驱动（预渲染方案，细节未收录） | 4 态：OFF/FLICKER_500/FLICKER_1000/ON | 最多，带多语言/zkota/HDMI 投屏/保养 8 组 |
| Comaro | 科迈罗(?) | 同 BMW 新版 socket_can+context | **TweenCpp 缓动**（60fps 定时器步进 alpha/位移）+ CircleBar/刻度灯 | 3 态：OFF/ON/FLICKER | 灯分组与 BMW 不同（故障/警告/提示分开） |
| Jeep/Pointer | 牧马人指针仪表 | 老版 `m_can/getcan` 全局单例回调 | **标准指针控件** `mPointXXXPtr->setTargetAngle(角度)` | — | ID 段 switch 分发，逻辑直接收 canData |

## 1. CAN 收发封装（新版本：can/socket_can.cpp）

```cpp
class SocketCAN : public Thread {
  bool startup();   // ① system("ip link set can0 type can bitrate 500000 triple-sampling on")
                    // ② system("ip link set can0 up")  ③ init() ④ run("canreader")
  bool write(uint32_t can_id, uint8_t dlc, uint8_t *data);  // 发帧：>0x7FF 自动加 CAN_EFF_FLAG(扩展帧)
  bool threadLoop(); // 循环 read(can_frame) → can::parseProtocol(canframe_)  （宝马直接在这里解协议）
};
#define SOCKETCAN  socket_can::SocketCAN::getInstance()   // 单例："can0", 500000, 10ms 超时
```

要点：
- **位率用 shell 配**：`/res/bin/ip link set can0 type can bitrate %d triple-sampling on` + `ip link set can0 up`
- RAW socket：`socket(PF_CAN, SOCK_RAW, CAN_RAW)` → bind can0 → 可 `setsockopt(CAN_RAW_FILTER)` 过滤
- 收帧线程内直接调 `can::parseProtocol()`（不再走回调），解析在**接收线程上下文**执行（不阻塞 UI）
- 发帧自动判扩展帧：`can_id > 0x7FF ? (can_id | CAN_EFF_FLAG) : can_id`
- Main.cpp 启动顺序：`can::startup()`（启动收线程）→ `UartContext::init()`

## 2. 协议解析层（can/context.cpp：解析表驱动，最值得抄的模式）

**结构：`static ProcFun _s_proc_fun_tab[] = { {canId, proc函数}, ... }` + `procParse` 遍历匹配 → 更新全局 `sDashboardData` → notify 回调。**

```cpp
typedef struct { uint32_t canId; void (*proc)(can_frame& can); } ProcFun;
static ProcFun _s_proc_fun_tab[] = {
    0x1FFF0010, procFaultIndicatorLight,     // 故障/警告/提示指示灯
    0x1FFF0012, procCruiseIndicatorLight,    // 巡航指示灯（ACC/LIM/HDC）
    0x1FFF0030, procKeyControl,              // 方向盘按键（短按/长按边沿）
    0x1FFF0050, procSpeedInfo,               // 车速+转速+瞬时油耗+方向盘转角
    0x1FFF0052, procEnduranceInfo,           // 水温/油量/续航/Effcient_Dynamics
    0x1FFF0054, procEngineOilInfo,           // 机油温度/车外温度
    0x1FFF0056, procStartUpAndGearInfo,      // ACC/IG/档位/驾驶模式
    0x1FFF0058/59/5A/5C/5E, …               // 小计A/B、总里程、启动后/重置后/加油后统计
    0x1FFF0092/93/94/95, …                  // 胎压/单位/协议版本/时间
    0x1FFF00A0, procFaultInfo,               // 故障码增删（0x1A52 加 0x1A55 删）
    0x1FFF00C0, procCruiseControlInfo,       // 巡航模式/跟车距离/巡航速度
    0x1FFF00D0~00DF, procupkeep*,            // 保养 8 组（剩余里程/设定里程 + 时间）
    0x1FFF0096, procspeedAlarmInfo,          // 速度警报
};
```

**数据流模式（三段式）：**
1. **解包**：proc 函数把 can.data 用 `MAKEWORD(low,high)` / `MAKEDOUBLE(4字节)` 拼成业务值写进全局 `sDashboardData`（先赋值后通知）
2. **通知**：`_notify_xxx_cb(sDashboardData)` → `CB_FOREACH(_s_cb_set, CanDataCb*, xxx_cb, canData)`（遍历注册集合，全部传同一份全局数据）
3. **页面订阅**：`CanDataCb` 是**函数指针结构体**（一个回调字段对应一个 proc），页面 `onUI_show` 里 `can::add_cb(&_s_can_cb)` 注册、`onUI_hide/quit` 里 `remove_cb` 注销——**页面级订阅/退订，不产生消息风暴**

```cpp
// 页面侧：只挂自己关心的回调
static CanDataCb _s_can_cb;
static void _can_add_cb() {
    _s_can_cb.fault_light_cb = Fault_light_cb;
    _s_can_cb.speed_info_cb  = Speed_info_cb;
    _s_can_cb.acc_gear_cb    = Acc_gear_cb;   // ...只挂本页需要的
    can::add_cb(&_s_can_cb);
}
```

**回调内刷新纪律（性能关键）**：页面回调先 `if(新旧值不同)` 再刷新（字段级 diff），相同值不 setText/setVisible；回调只更新 static 本地副本 `_s_can_data` 与控件，UI 才刷新。

**灯状态语义（BMW 特有 2bit 灯）**：
```cpp
typedef enum { LIGHT_OFF=0, LIGHT_FLICKER_500, LIGHT_FLICKER_1000, LIGHT_ON } light_status_e;
// 每个灯 2bit（bit 位置各不相同），闪烁灯由 500ms/1000ms 定时器翻转 visible
// pubSettings.cpp: addLampFlicker_500/1000 收集闪烁灯下标，定时器统一翻转 fault_light_array[i]
```

**方控按键（边沿检测）**：`key_i` 记录上次值，`当前 data[0]==0 且上次==1 → 按下`，`==2 → 长按`（只报边沿不重复报）。

**故障码管理**：`0x8001-0x8023` 故障 / `0xA010-0xA034` 警告 / `0xC010-0xC058` 提示；`0x1FFF00A0` 帧中 statue `0x1A52` 加码、`0x1A55` 删码、`0x1A50` 仅提示；faultList 线程安全增删查，UI 弹窗/列表页轮询 `can::getFaultList()`。

## 3. 业务值换算要点（常见陷阱）

- 车速：`speed = MAKEWORD(d0,d1)`；**无效值 `0xFFFF` 判空** → 指针回零位角度（30）
- 转速：`rpm = MAKEWORD(d2,d3)/100`；无效 `==655` → 归零位
- 瞬时油耗：`instanatFuel*0.1`；里程类（trip/odo）`*0.1` km
- 温度：`0xFFFF` 无效 → 显示 `--`；**摄氏/华氏两套查表**（`water_temp[2][9]`，华氏档值 +80~等偏移），水温图按温度区间选 `SequenceDiagram/%d_%d.png`（9 段 × 每段内 6 级插值）
- 单位切换（km/h↔mph、°C↔°F、km↔mile）由 `0x1FFF0093` 单位帧驱动，页面收到 unit 变化调公共转换函数整体重刷（pubSettings.cpp `set_speed_value/set_range/set_trip...`）
- **帧号即角度**：`_s_target_angle_speed = speed + 30`（30=表底零位），`_s_target_angle_RPM = rpm*2 + 30`（量程缩放）

## 4. 页面组织（BMW 示例）

- 一个 mode 一个 Activity + Logic（ftu 一套），main0 为模式选择页（SlideWindow 点选 openActivity 跳 main1~5）
- mode 资源目录一一对应：mainLogic→mode1、main3Logic→mode5、main5Logic→mode6 等（`#define SPEED_PIC_PATH "modeX/speed/speed_bin"`）
- `statusbar` 为全局状态栏 Activity（开机/关机动画 mp4、故障码弹窗、时间/温度），页面切换通过 pubSettings 函数指针回调（set_xxx_cb）联动
- HDMI 投屏页：收到外部命令 `cmd=11/22/33` 切 `mVideoHDMIPtr` 显示/隐藏 + 隐藏仪表控件（end_key_HDMI_cb/start_key_HDMI_cb）

## 5. 三套工程差异速查（换车型改哪里）

| 改动点 | BMW | Comaro | Jeep/Pointer |
|--------|-----|--------|--------------|
| CAN 封装 | socket_can 新版 | 同 BMW | m_can/getcan 老版单例 + 收回调 `onCanReadCallback(canData, canID)` |
| 协议分派 | 解析表 ProcFun | 解析表（0x10 故障/0x12 警告/0x14 提示**分开**） | logic 内按 canID 段 if 分派（<=0x1FFF0014 灯 / 0x50-0x61 行驶 / 0x90-0x95 车辆信息 / 0xC0 驾驶辅助 / 0x30 方控） |
| 档位枚举 | P/R/N/D/S/DS/M/L/C + gearLevel | P/N/R/D/S/M/A | 按车型 |
| 指针 | 预渲染指针帧图驱动（自研，细节未收录） | CircleBar setProgress + 刻度分段点亮（9 段转速灯/7 段车速灯）| 标准指针控件 setTargetAngle(角度) |
| 进/出场动画 | 扫针入场（0→30 逐帧） | TweenCpp：dashboard alpha 淡入、左右条 backEaseOut 滑入、指针自检走一圈 | 定时器 + setPosition/alpha |
| 额外 | zkota OTA、HDMI 检测(libusb)、保养 8 组、速度警报 | turnmode/drivemode 多视图 | 指南针/转向系统等专题页 |

## 6. 参考文件索引

- BMW/Comaro：`jni/can/socket_can.{h,cpp}`（收发）、`jni/can/context.{h,cpp}`（解析表+DashboardData+回调）、`jni/logic/main*Logic.cc`（页面订阅与刷新）、`jni/logic/pubSettings.{h,cpp}`（公共显示/单位换算/闪烁灯）
- Jeep/Pointer：`jni/m_can/getcan.cpp + canCallBack.cpp`（老回调）、`jni/logic/*Logic.cc`（ID 段分派）
- ⚠️ 以上为工程实测方法；具体车型协议以车厂 DBC/协议文档为准，仪表代码抄**架构模式**不抄字节定义。
