# components/wall_sync —— 多屏拼接 / 视频墙「跨设备同步」（`zk::wall`）

> **源码型**组件。把"N 块屏拼一面墙、同一时刻同一帧"这件事里**与业务/UI 无关的那一半**抽出来：
> ① 组网与校时（UDP 自组网 + epoch + 双向测时算真实钟差 + 整边界栅格）；
> ② 相位驱动（按组内时间挑"本机那一格"的文件，交给**注入的播放引擎**持续送流）。
> 落地来源：`projects/SmartPanel_HA`（Z20 现场真机验证版，v7.13 口径）——`src/wall/WallLink.*`、`src/wall/WallPlayer.*`、
> `src/logic/mainLogic.cc`（边界踩点调度）与 `src/logic/wallLogic.cc`（配置项口径）。
> 版本：**1.0.0**（2026-09-30 入库）
>
> 变更记录：1.0.0 首次入库（来源工程 v7.13：unicast epoch + 双向测时 RTT/2 钟差 + playlist v2 多 clip + 边界踩点）。

---

## 1. 是什么 / 不是什么

**是**：

| 能力 | 说明 |
|---|---|
| 组网 | 局域网 UDP（默认 8901）**自组网，不依赖服务器/云端**；主机（时间权威）广播/单播 epoch，其余从机跟随 |
| 校时 | 从机每秒双向测时（`ping`/`pong`，**RTT/2** 口径）算真实钟差；单程值只作兜底（见 §7 坑②） |
| 时间轴 | **绝对墙钟整边界栅格**：`nextBoundary = t0 + (floor((now-t0)/seg)+1)*seg` → 两台各自算出**同一个绝对时刻**，不必互发"开始"信令（UDP 抖动不进相位） |
| 多 clip 轮播 | 读设备盘上 `<wallRoot>/<组名>/playlist.json`（v2）：`g = 组内时间 − epoch`，`pos = g mod total` → 定位"第几个 clip + clip 内偏移" |
| 选片 + 起停 | 每轮按栅格挑**本机那一格**的文件交给引擎；边界预热踩点（等「边界 − lead」再拉起引擎，第一帧落整边界） |
| 状态自证 | 每秒一条 `wall tick:` 诊断（epoch/相位/wait/next/drift/skew 来源与 RTT/ready/lost/playlist/clips/total） |
| 配置数据 | 组目录清单 `listGroups()`、清单统计 `queryPlaylist()`（状态页/设置页直接用） |

**不是**（边界写清，免得误用）：

- ❌ **不含解码/上屏引擎**。解码那一层由业务通过 `Engine` 接口注入（Z20 现场 = 官方包 `simple-player` 的 `SimplePlayer`，MI VDEC + MI DISP 硬解；见 `example/flythings_wiring.cc`）。头文件里**没有任何底层类型**（无 MI_ / ffmpeg / simple_player.h）。
- ❌ **不含 UI**：不依赖 easyui 控件、不读写项目的配置存储、不管屏保页生命周期/熄屏/编辑态。配置从入参进，接线样板见 `example/`。
- ❌ **不含素材切分工具**（把源视频切成每屏一格的 `seg_<N>.mp4` + `playlist.json`，见 §8）。
- ❌ **不含历史两条路线的代码**：`v4`（easyui `ZKVideoView` + 两段式起播/直跳 seek）与"自读包移植版送流内核"（I 帧追赶 + 墙钟按 PTS 控速）已被官方包取代，本组件不再收录；差异见 §7「移植注意」。

---

## 2. 目录

```
components/wall_sync/
├─ README.md                 ← 本文件
├─ platforms.md              ← 平台支持表 + 前置条件 + 已知限制（未取证项显式标注）
├─ Manifest.xml              ← 底层包声明（抄来源工程真实版本）+ 本模块被引用的两种方式
├─ include/zk/zk_wall.h      ← **唯一对外头**（zk::wall：配置 + Sync + Engine + Player）
├─ src/
│   ├─ zk_wall_internal.h    ← 内部（不对外）：钩子 + 日志宏 + 读文件
│   ├─ zk_wall_sync.cpp      ← Sync 实现（移植 WallLink.cpp）
│   └─ zk_wall_player.cpp    ← Player 实现（移植 WallPlayer.cpp + mainLogic 的边界踩点）
└─ example/
    ├─ zk_wall_example.cc    ← 最小可跑示例（桩引擎：配置 + 起播 + 状态打印；PC/WSL 可编可跑）
    ├─ flythings_wiring.cc   ← FlyThings 工程接线样板（SimplePlayer 引擎 + prefs + 日志/时钟钩子 + 屏保生命周期）
    └─ README.md             ← 两个示例怎么用/怎么编
```

---

## 3. 快速上手（最小可跑）

```cpp
#include "zk/zk_wall.h"
using namespace zk::wall;

static void myLog(int lv, const char* msg, void*) { printf("[wall] %s\n", msg); }   // 必须接出来，否则现场啥也看不到

SyncConfig cfg;
cfg.enabled    = true;                 // 拼接总开关
cfg.group      = "zksw-wall";          // 组名（= 盘上素材目录名）
cfg.wallRoot   = "/mnt/sdnand/wall";   // 素材/清单根目录
cfg.index      = 1;                    // 本机序号（播 seg_<序号>.mp4）
cfg.panels     = 2;                    // 单行横排 1x2（支持 2..4）
cfg.role       = -1;                   // -1 = 第 1 屏自动当主机
cfg.segMs      = 30000;                // 单 clip 模式**必须 = 素材真实时长**（多 clip 以清单为准）
cfg.leadMs     = 0;                    // 0 = 内容零截断（推荐）
cfg.logFn      = myLog;
Sync::instance().start(cfg);           // 幂等：改配置后重调即可重载

Player::instance().setEngine(&myEngine);   // 你实现 Engine（见 §5）；工程参考实现 = 官方包 simple-player
PlayerConfig pc;
pc.rect = Rect(0, 0, 1280, 800);       // 屏保全屏
pc.startLeadMs = 150;                  // 边界踩点（<0/0 = 不踩点，立即起播）
Player::instance().configure(pc);

/* 主线程（真源 = 屏保页 1s 定时器） */
void tick1s() {
    Sync& wl = Sync::instance();
    if (!wl.enabled()) return;                       // 没开拼接 -> 完全不干预
    if (!wl.clockPlausible()) return;                // 墙钟不可信（RTC 空/未校时）-> 等 NTP，不起播
    wl.tick();                                       // 收包 / 发探针 / 发 epoch / 每秒自证日志
    if (wl.readyToPlay() && !Player::instance().running())
        Player::instance().start(wl.playKey());       // "节目键"不变则内部不重开
}
void onSaverLeave() { Player::instance().stop(); }    // ⚠️ 离开屏保页必须停（拼接只在屏保生效）
```

`example/zk_wall_example.cc` 是这段的可编译完整版（桩引擎，WSL 可跑）：

```bash
# WSL/Linux，PC 自测（桩引擎，不解码）：
g++ -std=c++11 -Wall -Iinclude -Isrc -I<rapidjson>/include \
    src/zk_wall_sync.cpp src/zk_wall_player.cpp example/zk_wall_example.cc -o zk_wall_demo -lpthread
./zk_wall_demo zksw-wall /tmp/wallroot        # 参数：组名、素材根目录
```
（`<rapidjson>` 用依赖包注册表里的路径，形如 `<注册表>/public/<平台>/rapidjson/1.1.0/include`；见 `example/README.md`。）

---

## 4. 配置项表

### 4.1 `SyncConfig`（对照来源工程的 prefs 键名）

| 字段 | 真源 prefs 键 | 默认 | 含义 / 取值 |
|---|---|---|---|
| `enabled` | `sp_wall_en` | false | 拼接总开关。false = 组件不起 UDP、不下发任何包 |
| `group` | `sp_wall_group` | `zksw-wall` | 组名（同组互认；也是素材目录名 `<wallRoot>/<组名>/`） |
| `index` | `sp_wall_idx` | 1 | 本机序号 1..panels（唯一；决定播 `seg_<序号>.mp4` 与格子位置） |
| `panels` | `sp_wall_n` | 2 | 总屏数 2..4（越界钳到 2） |
| `role` | `sp_wall_role` | -1 | -1 = 自动（index==1 当主机）；1 = 主机；0 = 从机。**两台都当主机会互相打架** |
| `segMs` | `sp_wall_seg_ms` | 30000 | 单 clip 模式**必须 = 素材真实时长**；多 clip 以清单 `total_ms` 为准，本值只兜底 |
| `leadMs` | `sp_wall_lead_ms` | 0 | 起播提前量（补偿引擎起播延迟）；0 = 内容零截断（推荐），正值会截掉尾部 |
| `masterAddr` | `sp_wall_peer` | 空 | 从机专用：主机地址 `"ip"` 或 `"ip:port"`；给了就全程单播（不广播） |
| `wallRoot` | —（硬编码） | `/mnt/sdnand/wall` | 素材/清单根目录 |
| `mediaHint` | `sp_video_sel` | 空 | 零配置：本机素材全路径 `<root>/<组>/c<k>/seg_<N>.mp4` → 自动推导组名/序号 |
| `udpPort` | —（硬编码 8901） | 8901 | UDP 端口 |
| `joinTimeoutMs` | `sp_wall_join_to_ms` | 5000 | 进屏保"等 epoch"超时（超时用本机钟兜底 + WARN，绝不卡画面） |
| `gridAnchorMs` | `sp_wall_anchor_ms` | 0 | 多 clip 栅格**绝对锚点**（方案 B：各屏都用本机 NTP 时间，播放相位零网络）；0 = 用主机 epoch 网格 |
| `logFn` / `nowFn` / `clockFollowFn` | —（工程 LOGD / TimeHelper / ClockManager） | NULL | 钩子；不设则：不打日志 / 用 `clock_gettime` / 不做时钟跟随 |

### 4.2 `PlayerConfig`

| 字段 | 真源 prefs 键 | 默认 | 含义 |
|---|---|---|---|
| `rect` | — | 0,0,0,0 | 输出矩形（屏保全屏）。**必须设**，否则 `start()` 报错 |
| `engine.synchronize` | —（`sp_.setSynchronizing(true)`） | true | 引擎自带对齐开关；前提 = 各机钟一致（靠 Sync + NTP） |
| `engine.rotateDeg` | `sp_wall_rotate` | 0 | 画面旋转角（**多台必须统一**）；0 = 用引擎默认 |
| `engine.vdecChannel` / `dispChannel` | `sp_wall_vdec_ch` / `sp_wall_disp_ch` | 1 / 1 | 参考实现的 MI 通道对（组件只透传给引擎，不解释） |
| `fallbackFile` | `sp_video_sel` | 空 | 无 epoch/时钟不可信时的本地兜底文件；空 = 清单第 0 段 |
| `startLeadMs` | `sp_wall_start_lead_ms` | 150 | 边界预热踩点提前量（≤0 = 不踩点，立即起播） |
| `gridAnchorMs` | `sp_wall_anchor_ms` | 0 | 同 `SyncConfig::gridAnchorMs`（0 = 跟随 Sync 的 epoch 网格） |

---

## 5. 对外 API 一览（`include/zk/zk_wall.h`，命名空间 `zk::wall`）

### 5.1 `Sync`（单例 `Sync::instance()`）

| 分类 | API | 说明 |
|---|---|---|
| 生命周期 | `Result start(const SyncConfig&)` | 起/重载（幂等）。失败给**人话** msg（如 UDP 绑定失败 → 查端口/网络权限） |
| | `void stop()` | 关闭（关拼接/退出应用） |
| 心跳 | `void tick()` | **业务每秒调一次**：收包 → 从机发探针 → 从机判断该要 epoch → 主机发 epoch → 统计 drift → 打诊断日志 |
| | `void poll()` | 立刻排空一次收包（可从其它线程调） |
| 快通道 | `publishNow()` / `requestEpoch()` / `pingNow()` | 进屏保时三个一起调：主机补发 epoch / 从机催 epoch / 从机先量准钟差 |
| 状态 | `enabled()` `isMaster()` `segIndex()` `panelCount()` `group()` `segPath()` `segMs()` `leadMs()` | 配置态 |
| | `readyToPlay()` `hasEpoch()` `epochMs()` `phaseMs()` `waitToBoundaryMs()` `nextBoundaryMs()` | 时间轴（`readyToPlay` = 已启用 && 有 epoch && 未失联 >10s） |
| | `driftMs()` `markPlayStarted(target)` `stateText()` | 起播偏差诊断 / 状态页一行文案 |
| 钟差 | `skewMs()` `skewRttMs()` `skewSrc()` `skewValid()` | `skewSrc` = `pingpong`（RTT/2，正常）或 `epoch`（单程兜底） |
| | `clockPlausible()` | 墙钟是否可信（≥2024-01-01 UTC）；false → **不要起播**，等 NTP |
| 时间原语 | `static long long nowMs()` / `static bool waitUntil(deadlineMs)` | 墙钟 / 毫秒级精等（≤4ms 分片；>1600ms 拒绝等） |
| 清单 | `queryPlaylist(group, panels, PlaylistInfo*)` `listGroups()` `wallRoot()` | 状态页/设置页用（**不改播放状态**） |
| | `playlistMode()` `clipCount()` `clipDurMs(k)` `clipStartMs(k)` `totalMs()` `periodMs()` `clipAt(g,&k,&off)` | 多 clip 时间轴 |
| | `groupDir()` `playlistPath()` `segPathForClip(k)` `playKey()` | 路径；**`playKey()` = 播放器节目键**（换键才重开） |

### 5.2 `Engine`（业务注入；组件不提供实现）

```cpp
class Engine {
public:
    virtual bool open(const EngineConfig& cfg) = 0;                  // 一次性：同步开关/旋转/通道
    virtual bool play(const std::string& file, const Rect&) = 0;     // **阻塞**到 EOF 或被 stop()
    virtual void stop() = 0;                                        // 从别的线程打断 play()
    virtual const char* name() const = 0;
};
```
参考实现（Z20 现场）：官方包 `simple-player` 的 `SimplePlayer` —— `setSynchronizing(true)` + `play(file, rect)`，见 `example/flythings_wiring.cc`。

### 5.3 `Player`（单例 `Player::instance()`）

| API | 说明 |
|---|---|
| `setEngine(Engine*)` / `configure(const PlayerConfig&)` / `config()` | 注入引擎与配置（引擎生命周期由业务负责） |
| `Result start(playKey)` | 异步起播（内部线程）；未注入引擎 → `ZW_ENO_ENGINE` + 人话 msg；同键同尺寸 → 不重开 |
| `void stop()` | 停播（打断引擎 + join）。幂等 |
| `running()` `currentFile()` | 运行态 |
| `periodMs()` `anchorMs()` `beginMs()` | 时间轴诊断（无 epoch → -1） |
| `cycles()` `clipIndex()` `clipCount()` `clipFile()` `locked()` `lastError()` | 播放诊断 |
| `lastPtsMs()` `lastWantMs()` `lastNowMs()` `lastErrMs()` | ⚠️ 引擎接管后**不由本组件测量 → 恒 -1（n/a）**，不要当 0 用 |

### 5.4 线程模型

- `Sync`：**非线程安全**，只在调用它的那条线程上跑（真源 = UI 主线程的 1s 定时器）。
- `Player`：`start()` 起**一条内部线程**持续调 `Engine::play()`；`stop()` 从**调用者线程**调 `Engine::stop()` 打断阻塞，再 `join`。
- 回调（`LogFn`/`NowMsFn`/`ClockFollowFn`）在**同步调用它的线程**上被调；回调里不要重入组件的写接口。

---

## 6. 依赖与引入方式

**组件核心**（`zk_wall_sync.cpp` / `zk_wall_player.cpp`）：

| 依赖 | 版本 | 用途 | 备注 |
|---|---|---|---|
| `rapidjson` | **1.1.0** | 解析 `playlist.json`（唯一用到 JSON 的地方） | 来源工程经 `base-json ^3.1.0`（其自身依赖 rapidjson 1.1.0）使用；仓库里 `rapidjson 1.1.0` 独立可用 |
| libc + POSIX（socket/pthread/dirent/clock_gettime） | — | UDP/线程/目录/墙钟 | 设备端 Linux |
| C++11/14 | — | 语言 | 与来源工程一致 |

**接线侧**（`example/flythings_wiring.cc` 才需要）：`easyui ^2.2.0`（`StoragePreferences`/`Log`/`ZKVideoView`）、`base-utility ^10.8.5`、`log 0.0.0`、官方包 `simple-player ^4.0.1`（引擎，**带来授权码**）、`log`/`mi-module 5.0.2`/`ffmpeg 4.1.9-configure3`（引擎链路的传递依赖）。版本号全部取自来源工程 `Manifest.xml`，见 `Manifest.xml`。

**两种引入方式**：

- **A) 源码引入（推荐起步）**：把 `include/zk/` 与 `src/` 拷进工程（如 `src/zk/`、`src/wall_sync/`），`#include "zk/zk_wall.h"`，在工程 `fsc.json`/`Manifest.xml` 声明 §6 的包，**改完 Manifest 必须重跑 `fsc install`**。
- **B) 依赖包引用（模块定型后）**：编成 `include/ + lib/<平台>/` 注册进包仓库，工程一行 `<package id="wall_sync" version="1.0.0"></package>`（版本写死，不用 `^`）。

---

## 7. 移植注意：项目私有依赖怎么换（本组件的取舍清单）

| 真源里的东西 | 本组件改成 | 为什么 |
|---|---|---|
| `StoragePreferences` 读 `sp_wall_*` | `SyncConfig` / `PlayerConfig` 字段（示例给出 prefs→配置的映射） | 组件不认某个工程的存储实现 |
| `WallLink`（单例，工程内） | `zk::wall::Sync`（单例） | 同源移植，仅换掉配置/时钟/日志来源 |
| 官方包 `SimplePlayer`（带 accessKey） | `Engine` 接口，**业务注入** | 授权码不入库；也允许换成自研播放器 |
| `TimeHelper`（墙钟回退链） | `NowMsFn` 钩子；默认 `clock_gettime(CLOCK_REALTIME)` | 回退链在未校时会落到秒级 → 相位永远收敛不到 1 帧（坑①），组件宁可不给值也不给秒级值 |
| `ClockManager`（从机系统钟跟随） | `ClockFollowFn` 钩子（示例把它喂回 `ClockManager`） | 校时策略属工程/产品决策 |
| `LOGD/LOGW/LOGI` | `LogFn` 钩子 + 内部 `ZWLOG` | app 模式 stdout 是 `/dev/null`，日志必须能接出去 |
| 硬编码 `/mnt/sdnand/wall`、端口 8901 | `SyncConfig::wallRoot` / `udpPort` | 换盘/换网段不改代码 |
| UI（屏保页 1s 定时器、设置页行循环、熄屏/编辑态判断） | **不搬**：业务自理，只在 `example/flythings_wiring.cc` 给出接线样板 | 组件不依赖 easyui |
| `v4` 引擎（easyui `ZKVideoView` + **两段式起播** + **直跳 seek**） | **砍掉**（历史路线，已被官方包取代） | 两段式的目的是"把播放器拆解移出关键路径"，官方包自带对齐+循环，不再需要；⚠️ 官方 `simple-player` **没有 seek API** → `sp_wall_join` 的"直接跳到该显示的位置"路线在本形态下**不适用**（`Sync` 仍保留 `waitToBoundaryMs()/nextBoundaryMs()/phaseMs()` 供状态页与自研引擎使用） |
| 自读包移植版送流内核（I 帧追赶 + 墙钟按 PTS 控速，旧版 ~1039 行） | **砍掉** | 官方授权到手后改用包内实现（真源 v7.12 的决定）；需要它的可回看来源工程 `temp/WallPlayer.cpp.bak_v711_port` |
| 工程侧的"总闸"（simple 模式下拦掉所有 easyui 起播路径）与停 v4 后 **400ms 沉降** | **不搬进组件**，写进接线样板的注意事项 | 那是"两个内核抢 MI 图层"的工程级处置（表现在组件外）；现象/判据见来源工程注释与 `knowledge/devflow/video-wall-sync.md` §5 |

---

## 8. 限制（选型前必读）

1. **只在屏保状态拼接**：主页/设置页时拼接暂停，进主页/设置页必须显式 `Player::stop()`（组件不做页面判断）。
2. 排布仅 **单行横排 1xN（N ≤ 4）**，不支持 2×2 等二维；主从角色**须人工设置**，无自动选举。
3. **各机必须完成 NTP 校时**（面板 RTC 掉电不保时）；`clockPlausible()==false` 时组件**不起播**（真源守卫语义），钟差大时两台可差 ≈10 帧。
4. **同型号/同分辨率/同安装方向**、各机 `/res/lib/libzkgui.so` md5 相同；素材**同一 clip 内各段严格等长（差异 ≤40ms）**，不同 clip 之间可长短不同。
5. 材料时长与 `segMs` 不符（单 clip 模式）会按周期截断/冻结末帧 → 对齐素材或改正 `segMs`；多 clip 模式不按周期截断。
6. 两段式提前停会造成 **~160ms 循环缝**（末帧冻住 + 拆解）——本组件形态下缝由引擎侧决定，`Sync` 仍提供 `leadMs` 口径。
7. 设备 `/mnt/sdnand` 只有 **75MB** → 多 clip 大组要用"只推本机那一段"的分发方式。
8. **截图拿不到视频层**（视频不在 `/dev/fb0`）：终验只能相机拍屏，设备侧用 `/proc/mi_modules/mi_disp/mi_disp0` 做客观自证。
9. 残差 **±19ms** 主要来自 1s tick 回调调度抖动（观测 ~9~19ms）；要再压低得换更细粒度的定时源。
10. 播放中改配置/杀进程可能让 MI 驱动卡死（进程 D 态）→ **改完 pref 重启整板**，别在播放中 kill。

---

## 9. 验收口径（判据 + 实测数字，全部来自来源文档，本组件不新造数字）

判据与复核方法：

| 项 | 判据 | 复核方法 |
|---|---|---|
| 相位同步 | 两台 `\|Δnow\|` **≤40ms（1 帧 @25fps）**，连续多轮 | 两机 logcat 抓 `wall tick:` 的 `phase/cyc/pts`，按同一 `cyc/pts` 配对求差 |
| 起播相位 | 两台同 `target` 的 `delta` 之差 | 独立旁证 = logcat `D/zkmedia: play: <seg>.mp4` 相对同一边界之差 |
| 轮播切换/回卷 | 两台切换/回卷时刻 **Δ ≤1ms**、同帧 | 配对切换/回卷日志 |
| 轮播无空档 | `dropGop=0` | `reopen(...)` 行的计数 |
| 画面质量 | 抓帧块度 **≤1.2**（源帧基准 1.05~1.25） | 设备端抓 YUV，按 16 像素边界算块度 |
| 版本一致 | 两台 `/res/lib/libzkgui.so` md5 相同 | `adb pull` 后本机算（设备 shell 无 md5sum） |

实测数字（**出处**：`knowledge/devflow/video-wall-sync.md` §4/§4.1，其主源 = `references/kb/video-wall-sync.md`）：

| 项 | 数字 | 出处小节 |
|---|---|---|
| v4 引擎（easyui `ZKVideoView` 路线，**不在本组件**） | 33 轮长跑全部 `\|Δ\| ≤19ms`（均值 ~4ms，无漂移/无漏边界） | §4（主源 §6） |
| simple 引擎稳态 | 424 样本 `max\|Δ\|=1ms`、≤10ms 占 100%；7min 954/950 样本 `max\|Δ\|=3ms`；含起播热身 435 样本 `max\|Δ\|=14ms` | §4（主源 §9.5） |
| 稳态复验 | 两台各 17 轮 × 241 帧；`sync` 配对 **187 组 max\|Δnow\|=1ms、中位 0**；cycle-end 17 组 Δ=0~1ms | §4（主源 §10.5） |
| 多 clip 轮播 | 一轮 245.92s（10.04s + 235.88s）；两台切换/回卷 Δ=0~1ms 同帧；块度中位 **1.07/1.00**；`dropGop=0` | §4（主源 §12.7） |
| 进屏保直跳 join（v4/自读包路线，**本形态不适用**） | 主机 `delta` 6~8ms / `took` 13~14ms；从机 `delta` 5~29ms（帧网格 41.67ms ⇒ 最小可能偏差 = 1 帧） | §4（主源 §10.3） |
| 时钟一致性 | `min(skew)=0` → 两机 `CLOCK_REALTIME` 相差 **≲1ms**；相对漂移 ~ **−0.9ms/min**（在噪声内） | §4（主源 §6） |
| 素材口径 | 段 **480×480**、导出固定 `-r 25`；实测素材 241 帧 / 10.041667s（24fps）另 750 帧 / 30.000000s | §4/§4.1（主源 §11） |
| **未取证（禁止当实测引用）** | NTP v6 改造后的"单台绝对误差 ≤100ms、两台互差 ≤50ms"判据**尚未回收实测数字** | §4 末 + §5（主源 §13.5 标占位） |

本组件自身的自测范围（**只证明逻辑通，不替代真机判据**）：`example/zk_wall_example.cc` 能编能跑（PC/WSL，桩引擎）—— 已验证：配置装载、组目录枚举、整边界/相位/等待计算、边界踩点（等「边界 −150ms」再拉起引擎）、起停与诊断打印。

---

## 10. 排错

| 现象 | 根因 | 处置 |
|---|---|---|
| 两台各播各的 / 差几十秒 | 播完后紧跟一条播放错误，错误分支"抢跑"起播 | 拼接模式下 ERROR/COMPLETED 都**只等整边界**，不抢跑 |
| 相差 100ms+ 且每次进屏保都在跳 | 把 `skew`（含单程投递延迟）当钟差补偿 | 用双向测时 RTT/2（本组件已内置）；看 `skewSrc()` 是否 `pingpong` |
| 画面差一截（几帧~十几帧） | 未校时 / 钟差大 | 等 NTP（`clockPlausible()`），看 `skew` 中值 |
| 单块屏画面冻住（另一块正常） | 两个播放内核抢 MI 图层，`stop()` 拆解是异步的 | 用**总闸**拦住另一内核的起播路径 + 停完**沉降 400ms**（见接线样板） |
| 一直不播、日志刷 `clock_insane` / 开机初期刷满 cycle-end | 未授时 / `CLOCK_REALTIME` 还没被 NTP 拨到真实值 | `Sync::clockPlausible()` 守卫 + 等 NTP，5s 后重试 |
| 播放卡住只出一帧 | 单 clip 模式 `segMs` ≠ 素材真实时长 | 对齐素材时长或改正 `segMs`；多 clip 模式不按周期截断 |
| 推上去没效果/画面是旧的（Z20） | `/mnt/extsd/EasyUI.cfg` 的 `startupLibPath` 劫持（加载 SD 卡上的旧库/界面） | 改回或删掉该文件后重启应用 |
| 组名循环不到我建的组 | 组目录不在设备 `<wallRoot>/` 下（大小写要一致）/ 清单没随组推上去 | 用切块工具重推**整组**；`listGroups()` 为空时给"未找到组目录"提示 |
| 链接失败 `__atomic_load_8`/`__atomic_store_8` | 32 位 ARM 上 `std::atomic<long long>` 需要 `-latomic` | 64 位诊断量改 `std::mutex` 护（真源做法） |

---

## 11. 相关

- 平台支持与前置条件 → `platforms.md`
- 底层包声明与两种引用方式 → `Manifest.xml`
- 两个示例怎么编/怎么接 → `example/README.md`
- 知识条目（原理/验收/故障全表） → `knowledge/devflow/video-wall-sync.md`（主源 `references/kb/video-wall-sync.md`）
- 产品侧说明书 → `projects/SmartPanel_HA/docs/说明书-多屏拼接.md`
- 视频层抓帧/截图口径 → `knowledge/devflow/device-screenshot.md`；Z20 现场坑 → `references/kb/z20-hardware-notes.md`
- 组件规范 → `components/README.md`、`knowledge/devflow/reusable-components.md`
