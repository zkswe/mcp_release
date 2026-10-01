---
id: devflow-video-wall-sync
title: 多屏拼接（video wall）相位对齐与校时 —— 实现口径与验收判据
category: devflow
status: review
confidence: manual
verified_at: 2026-10-01
stale_days: 180
origin: partial
source: 2026-09-30 从 workspace 主源 references/kb/video-wall-sync.md（419 行）+ SmartPanel 多屏拼接说明书交叉核对后入册；只摘主源可核实条目，源内标占位/待验证的数字不引
needs_evidence: true
platforms: [Z20]
tags: [多屏拼接, 拼墙同步, 相位对齐, 整边界起播, 校时, NTP校时口径, 素材切分, 视频墙, epoch, 从机画面冻住]
evidence:
  - "相位与长跑数字：workspace references/kb/video-wall-sync.md 的 §6（v4 长跑 33 轮 |Δ|≤19ms）、§9.5（simple 引擎样本）、§10.3（join delta）、§10.5（稳态复验 187 组 max 1ms）"
  - "配置键名/默认值：SmartPanel 多屏拼接说明书 §4、§8（与主源 §4 逐项一致）"
  - "时钟与校时：主源 §13.1/§13.2/§14.1~§14.4；源内 §13.5 的 v6 改后数字明确标占位未取证，本文不引"
  - "NTP/校时现行口径（v7.10+ 网关已移除、每 10 分钟刷新、每服务器 4 样本取最小 RTT、groupFollow 恒定速率慢爬）：实读工程 projects/SmartPanel_HA/src/system/ClockManager.cpp 的 L12 / L24-105 / L106-115 / L158-172 / L219-255 / L233-236 / L279-308 / L337-339；ClockManager.h L57（kRefreshMs=10min）"
---
# 多屏拼接（video wall）相位对齐与校时 —— 实现口径与验收判据

> 检索导引：两台屏画面不同步 / 拼墙相位 / 起播相位差多少算合格 / 校时怎么算同步 / 整边界起播是什么 / 墙播放器在哪一层（vdec 通道 / MI DISP 图层）/ 素材怎么切出来 / 两台差十帧 / 两台各播各的 / 从机画面冻住不动 / 进屏保半天不同步 / 一个组怎么放多个视频轮播 / 组名怎么设 / 时间基准（epoch）从哪来 / skew 是什么 / 拼墙怎么验收 / 拼墙循环缝 / 拼墙抓不到画面（截图拿不到视频层）。
> 用途：N 块同型号面板拼一面墙时的**同步原理、配置键、验收判据、故障排查**速查；数字全部来自主源真机实测（源出处逐条标注见 front-matter `evidence`）。

## 1. 能力与前提

- 能力：**≤4 台**同型号面板排成单行横排（`1xN`），播放同一素材（或同一轮播清单）的**各自那一格**，画面同帧；面板只在**屏保**状态下拼接（主页/设置时拼接暂停）。
- 组网：同网段 UDP 广播自组网（端口 8901），**不依赖服务器/云端**；一台主机（时间权威）广播 epoch，其余从机跟随。
- 前提（不满足就不同步）：

| 前提 | 要求 | 不满足的后果 |
|---|---|---|
| 网络 | 同网段互通，允许 UDP 广播（关掉交换机广播抑制/客户端隔离） | 收不到 epoch → 各自轮播 |
| 时间 | 各机都完成 NTP 校时 —— **内置公网 IP 列表直连**（v7.10+ 已**不用默认网关**，见 §7） | 相位随钟差漂移（钟差大时两台可差 ≈10 帧） |
| 型号/方向 | 同型号、同分辨率、同安装方向（统一旋转角） | 画面切分对不上 |
| 素材 | **同一 clip 内**各机那段 `seg_<本机序号>.mp4` 严格等长（差异 ≤40ms）；**不同 clip 之间可长短不同** | 循环缝变大 / 末帧冻结 |
| 固件 | 两台 `/res/lib/libzkgui.so` md5 相同 | 行为不一致、难定责 |

术语速查（后文直接用）：

| 术语 | 含义 |
|---|---|
| epoch | 主机广播的**本轮循环起点墙钟**（ms）；同 epoch + 同公式 = 同一绝对时刻 |
| 整边界 | 下一个栅格整点 `nextBoundaryMs()`，恒为绝对墙钟，两台算出同一个值 |
| 相位（起播相位差） | 两台各自 `delta = t_ret - target` 之差；稳态画面的相位用同一 `cyc/pts` 的 `\|Δnow\|` 量 |
| 组内时间 `g` | 本机组内墙钟 − epoch（从机侧 = 本机墙钟 − 钟差补偿） |
| skew | `收包本机钟 − 包内 pub_ms` = 真实钟差 + **单程投递延迟**；只作诊断/校时样本 |
| 两段式 | 提前 ~160ms 只 `stop()`，整边界上只剩冷启动 `play()` |
| 块度 | 设备抓帧 YUV 按 16 像素边界算的块状噪声指标（判据 ≤1.2） |
| 循环缝 | 两段式提前停造成的末帧冻结/截断窗口（~160ms） |

## 2. 原理（epoch / 相位 / 整边界 / 两段式）

1. **绝对墙钟栅格，不靠互发"开始"信令**。主机每 1s UDP 广播（明文）：
   `wall|<组名>|<t0_ms>|<seg_ms>|<n>|<pub_ms>|<clips>|<total_ms>`
   —— `t0_ms` = 本轮循环起点墙钟，`pub_ms` = 发包瞬间墙钟；末尾 `clips`/`total_ms` 是 v2 追加字段，**老从机只读前 6 段，向后兼容**。组名不匹配直接丢。
2. **同一 epoch + 同一条公式 = 同一绝对时刻**：`nextBoundaryMs() = t0 + (floor((now-t0)/seg)+1)*seg`
   → UDP 抖动、心跳相位差都不进相位；起播前本地**精等**到该时刻（`wallWaitUntil()`，`usleep` 分片 ≤4ms）到点即 `play()`。
3. **链式推进**：起播后 `target += seg`（恒落整边界），不依赖"播放完成"消息。
4. **两段式起播（相位收敛到 1 帧的关键）**：提前 ~160ms 只做 `stop()`，把播放器拆解（实测 110~180ms 且各机不一）移出关键路径；到整边界只剩**冷启动 `play()`**（实测 0~6ms）。
5. **自校准**：把实测"起播−目标"偏差反馈进下一轮，增益 1/2 + **死区 ±10ms** + 限幅 ±30ms（增益 3/4 会把抖动放大成振荡）。
6. **组内时间与多 clip 定位**：`g = 本机组内墙钟 − epoch`，`pos = g mod period`（单 clip：`period=seg_ms`；多 clip：`period=total_ms`）→ 由 `pos` 定位"第几个 clip + clip 内偏移"；clip 末尾**直接 reopen 下一个 clip 的文件**（不 seek、轮末不留空档），最后一个播完回到第一个（日志 `playlist wrap`）。
7. **进屏保快速对齐**：从机进屏保即广播 `wall?|<组>`，主机**立刻补发 epoch**（等待从 1s 心跳压到 ms 级）→ 从机**直跳**到当前相位对应的画面（`sp_wall_join`：`av_seek_frame` + `avformat_flush()` + `av_bsf_flush()`，把 `begin` 之前的包快速送完，首个 `pts>begin` 的包走墙钟锁相）。
8. **失联与守卫**：>10s 收不到 epoch → 本机回退普通屏保轮播；epoch 落在"未来 >1h"（未授时脏值）→ 拒绝起播并打 `clock_insane(...)`；开机墙钟未校时（`wallNowMs() < 1e12`）→ 直接报 `wall_clock_not_set` 退出、5s 后重试。

时间轴口径（单 clip 与多 clip 同一套公式，多 clip 只是换了 `period` 与内容定位）：

```
period = seg_ms（单 clip）  /  total_ms（多 clip）
g      = 本机组内墙钟 − epoch
pos    = g mod period        → 定位(第 k 个 clip，clip 内偏移 off)
anchor = epoch + m*period     # 两台重合
want   = anchor + pts         # 每包按此控速
nextBoundary = t0 + (floor((now-t0)/seg)+1)*seg   # 恒落绝对整边界
```

## 3. 配置键表（`/data/preferences.json`，改完重启应用生效）

| 键 | 默认 | 含义 / 取值循环（设置页行） |
|---|---|---|
| `sp_wall_en` | false | 拼接总开关。设置页①：`开启 / 关闭` |
| `sp_wall_group` | `zksw-wall` | 组名（= 设备上 `/mnt/sdnand/wall/<组名>/` 目录名，同组一致）。设置页②：**在盘上真实存在的组目录之间循环**（当前值不在列表则排最前；无组目录提示"未找到组目录"） |
| `sp_wall_idx` | 1 | 本机序号（唯一，决定播 `seg_<序号>.mp4` 与格子位置）。设置页③：`1 … 总台数` 循环 |
| `sp_wall_n` | 2 | 总台数（屏数）。设置页④：`2 → 3 → 4 → 2` 循环（显示 `1x2/1x3/1x4`，本机序号超界自动收敛） |
| `sp_wall_role` | 1 | `1`=主机（时间权威）/ `0`=从机。设置页⑤：`主机 / 从机` 切换；约定序号 1 设主机，**两台都设主机 = 互相打架** |
| `sp_wall_seg_ms` | 30000 | 片段时长（ms）。单 clip 模式**必须 = 素材真实时长**；多 clip 模式时间轴以清单 `total_ms` 为准，本键只作兜底 |
| `sp_wall_engine` | 0 | 播放内核：`0`=v4（easyui `ZKVideoView` + 整边界两段式，实测 \|Δ\|≤19ms）；`1`=simple（自读包 + I 帧追赶 + 墙钟控速，现场值） |
| `sp_wall_join` | true | 进屏保"先对齐再跳画面"；`0`/`false` 均关闭（**唯一的一键回退手段**，回到"追赶不 seek"老行为） |
| `sp_wall_join_to_ms` | 5000 | 进屏保等 epoch 超时（ms），超时用本机时间兜底 + WARN（绝不卡画面） |
| `sp_wall_lead_ms` | 0 | 起播提前量。`0` = 内容零截断（内容在边界后几 ms 出画，两台一致）；给正值会截掉尾部 |
| `sp_wall_vdec_ch` / `sp_wall_disp_ch` | 1 / 1 | MI 通道对；起播失败自动回退 `(1,0)→(0,1)→(0,0)` |
| `sp_wall_rotate` | 0 | 本机画面旋转角（多台必须统一） |
| `sp_wall_clock_wait_ms` | 30000 | 时钟可信门：本机墙钟 < 2024-01-01 00:00:00 UTC（=1704067200000 ms）时先等 NTP，最长等这么久；超时仍不可信 → WARN 后按本机钟继续 |

设置页⑥「**播放内容**」：多 clip 显示 `K 段 · 总 X.Xs`，旧布局显示 `1 段 · 10.0s`；**该行只读**，换内容要换素材组。

## 4. 验收判据与实测数字

判据（可复核）：

| 项 | 判据 | 复核方法 |
|---|---|---|
| 相位同步 | 两台 `\|Δnow\|` **≤40ms（1 帧 @25fps）**，连续多轮 | 两机 logcat 抓 `wall[sp]: sync cyc=… pts=… want=… now=…`，按同一 `cyc/pts` 配对求差 |
| 起播相位 | 同一 `target` 的两台 `delta` 之差 = 起播相位差（主判据：`wall: start target=… t_req= t_ret= delta=…ms`） | 独立旁证 = logcat `D/zkmedia: play: <seg>.mp4` 相对同一边界之差 |
| 轮播切换/回卷 | 两台切换（含回卷第 1 个 clip）时刻 **Δ ≤1ms**、同一帧 | 配对 `playlist clip-switch …` / `playlist wrap …` |
| 轮播无空档 | `dropGop=0` | `reopen(...)` 行的 `dropGop` / `dropSize` 计数 |
| 画面质量 | 抓帧块度 **≤1.2**（源帧基准 1.05~1.25） | 设备端抓 YUV，按 16 像素边界算块度 |
| 版本一致 | 两台 `/res/lib/libzkgui.so` md5 相同 | 设备 shell 无 md5sum 时 `adb pull` 后本机算 |

实测数字（均出自主源，含出处节号）：

- **v4（easyui）引擎**：33 轮长跑全部 `|Δ| ≤19ms`（均值 ~4ms，无漂移/无漏边界/无兜底）；独立旁证 33 轮最大 20ms，与主判据逐轮一致；分钟级窗口单轮最大 18~25ms（§6）。
- **simple 引擎（`sp_wall_engine=1`）**：(cyc,pts) 配对中位 0ms，稳态窗口 424 样本 `max|Δ|=1ms`、≤10ms 占比 100%；7min 窗口 954 / 950 样本 `max|Δ|=3ms`；含起播热身的 435 样本 `max|Δ|=14ms`（§9.5）。
- **进屏保直跳（join）**：主机 `delta` 6~8ms / `took` 13~14ms；从机 `delta` 5~29ms（帧网格 41.67ms ⇒ **最小可能偏差就是 1 帧**）；两台同时在屏保互相应答时 `wait=0`、`took≈15ms`；跨机"进屏保时刻差 vs `begin` 差"一致到 0~6ms（§10.3）。
- **稳态复验**：两台各 17 轮、每轮 `frames=241`；`sync` 配对 187 组 **max|Δnow|=1ms、中位 0**；`cycle-end` 17 组 Δ=0~1ms（§10.5）。
- **多 clip 轮播**：一轮 245.92s（10.04s + 235.88s 两个 clip）；两台切换/回卷 Δ=0~1ms、同帧；块度中位 **1.07 / 1.00**（判据 ≤1.2）；`dropGop=0`（§12.7）。
- **时钟**：从机每秒记 `skew = 收包时刻 − 主机发包时刻`，因 `skew = 读包等待(≥0) + 钟差` ⇒ `min(skew) ≥ 钟差`；实测 `min(skew)=0` → 两机 `CLOCK_REALTIME` 相差 **≲1ms**（两台开机均 NTP 同步）⇒ 主判据的 19ms 就是**真实画面相位差**，不需再扣钟差；相对漂移约 **-0.9ms/min（在噪声内）**（§6，属旧校时口径时期；现行 v7.10+ 口径见 §7）。
- **素材口径**：段 480×480；实测素材 241 帧 / 10.041667s（24fps），另一对 750 帧 / 30.000000s；导出固定 `-r 25`；绿框外丢弃、**禁 pad 补黑边**；前端画框与后端导出用**同一个 crop 矩形**（唯一事实源），往返比对 `mean ≤6 / p99 ≤22`（p50=0）为阈值（§11）。
- **未取证（源材料里明确标占位，禁止当实测引用）**：NTP v6 改造后的"单台绝对误差 ≤100ms、两台互差 ≤50ms"判据**尚未回收实测数字**（主源 §13.5 + 说明书 §12/§14）。

### 4.1 素材切分口径（绿框 = 唯一裁剪窗口）

- **唯一事实源** `crop = [x, y, w, h]`（源像素，恒 `w = N×h`，偶数对齐 + 钳制在源内）；前端画框与后端导出**同一个矩形**，前端把 crop 原样发后端（不再用 scale/ox/oy 反推）。
- **滤镜链**：`crop(w:h:x:y) → scale(N×480 : 480 : flags=lanczos) → crop(480:480:i*480:0)`，**禁 `pad`**（补黑边会让相邻屏黑边连成黑带）。
- **没有"缝"**：N 个 480×480 绿框**相邻无缝**，并集就是裁剪窗口；框外画面直接丢弃（`bezel` 概念已删，数学恒为 0）。
- **交互**：拖 = 移整组绿框（改裁剪原点）、滚轮/缩放条 = 改框组大小；视频画面固定不动 → 框组钳制在视频内，结构上不可能有黑边。
- **一致性**：同组各段参数完全一样、段首 I 帧、`+faststart`、导出固定 `-r 25`；`/api/split` 对 crop 越界钳制、宽高比 ≠ N:1 或源 < 480×480 直接报错并禁导出。
- **可复核数字**（源 §11 证据）："所见 = 所出"往返比对 seg 首帧 `mean 1.53/1.14、p99 20/16`（p50=0，阈值 `mean ≤6 / p99 ≤22`）；边界无黑边实测外沿 2px 亮度偏差 **≤0.47 luma**；无损 ramp 逐列 MAE **0.179 luma**、seg_1 末列→seg_2 首列跳变 **0.00（无丢弃列）**。

## 5. 故障排查表

| 现象 | 根因 | 处置 |
|---|---|---|
| 两台各播各的 / 相差几十秒（各落相邻边界） | 播完后紧跟一条 `E_MSGTYPE_VIDEO_PLAY_ERROR`（实测 +112ms），错误分支直接起播**抢跑** | 拼接模式下 ERROR 与 COMPLETED 一样**只等整边界**，不抢跑 |
| 相位差散布 25~41ms | `stop()+play()` 串在临界点上，拆解耗时 110~180ms 且各机不一 | **两段式**：提前 ~160ms 只 `stop()`，边界上只冷启动 `play()` |
| 首段就错位 | `onUI_show` / 素材清单刷新后**立即起播**，两台进页时刻不同 | 拼接模式下改为"重新定标到下一个整边界"（`sWallTargetMs = 0`） |
| `delta` 在 ±25ms 来回摆 | 自校准增益过大，把抖动放大成振荡 | 增益 1/2 + 死区 ±10ms + 限幅 ±30ms |
| 单次 `usleep(几百 ms)` 超时 10~30ms | 内核唤醒粒度/调度 | 等待改成 ≤4ms 分片轮询 |
| 两台差 100ms+，且每次进屏保量都在跳 | `skew`（含**单程投递延迟** ~60~175ms）被当钟差补偿：`gskew` 固定应用 → 从机时间轴整体慢 gskew | 钟差改**双向 ping-pong**（从机发 `ping|<t0>`、主机回 `pong|<t0>|<主机ms>`，环形窗口取**最小 RTT** 那笔）；epoch 单程只作兜底（pong 断 >20s 且差 ≤250ms 才采用）；`gskew` 每 2s 刷新、变化 ≥40ms 才更新（去抖）。修后实测偏差 **−1 ~ +2ms**（改前 +116 / +852 / +8017ms，且在 4.7~8.0s 间抖动） |
| NTP 每秒重跑、钟被反复步进（主机播放 `err=103/352/310ms`） | 周期刷新条件（"距上次成功 >30min"）因 last-ok 记账没更新而**恒真** → 每 tick 起新任务、多次 `setSystemTime` | `ClockManager` 加**在飞保护 + 最小发起间隔 30s**（`ClockManager.cpp:337-339`）；拼接侧钟差改**双向 ping-pong 取最小 RTT**（旧版为近 5 次中值、只丢 `\|skew\|>120s` 脏样本）。**已修** |
| 单块屏画面冻住（simple 引擎，另一块正常） | 两个内核共用屏保页：开机先起 v4（easyui）播放器用 disp **chn0**，`stop()` 的 MI 图层拆解是**异步**的，紧接 start simple 引擎踩在正在拆的 chn0 上 → 留下**永不 finish 的 workingTask**（`/proc/mi_modules/mi_disp/mi_disp0` 里 chn0 `UsrInjectQ/workingTask/FinishCnt` 卡住），陈旧层压住 chn1 视频层 | `playItem()` 加**总闸**（simple 模式下所有 v4 起播路径直接 return）+ 停 v4 后 `WALL_V4_SETTLE_MS=400ms` 沉降再起引擎；判据：chn0 的 `UsrInjectQ/workingTask/FinishCnt` 必须全 0 |
| 一直 `clock_insane FAILED` 不播 | 本机/主机未授时，epoch 是脏值 | 等 NTP 同步；该守卫只拦"epoch 在未来 >1h" |
| 开机初期刷满 `cycle-end`（1s 上千条） | `CLOCK_REALTIME` 还没被 NTP 拨到真实值就拿去算 anchor → 负数锚点，之后每轮都"早已过期" | `wallNowMs() < 1e12` 直接 `wall_clock_not_set` 退出，主线程 5s 重试 |
| 播放中改配置 / kill 应用后 MI 卡死（进程 `D` 态、`wchan=MI_SYS_IOCTL_Init`，旧新实例一起卡） | 播放中 `ctl.stop/restart` 让 MI 驱动卡死 | 改完 pref 再**重启整板**（重启后 IP 不变），别在播放中 kill |
| 播放卡住、只出一帧（单 clip 模式） | `content != period`（素材时长与 `sp_wall_seg_ms` 不符，按周期截断/冻结末帧） | 对齐素材时长或改 `sp_wall_seg_ms`；**多 clip 模式不按周期截断** |
| 先跳画面只读出一个包然后 EOF | seek 后没 flush 解码缓冲 | `av_seek_frame` 后必须 `avformat_flush()` + `av_bsf_flush()`（并保证 `begin` 之前那个 GOP 不丢包，丢了 P 帧花屏） |
| `sp_wall_join` 写 `0` 关不掉 | SDK `getBool` 只认 JSON 布尔 `true/false` | 现行写法是 `getBool(...) && getInt(...)!=0` 两个读法取与，`false` 与 `0` 都能关 |
| 推上去没变化 / 画面是旧的 | Z20 上 `/mnt/extsd/EasyUI.cfg` 的 `startupLibPath` 在劫持（加载 SD 卡上的旧库/界面） | 改回或删掉该文件后重启应用（详见 `z20-hardware-notes`） |
| 组名循环不到我建的组 | 组目录没真在设备 `/mnt/sdnand/wall/` 下（大小写要一致）/ 没推上去 / `playlist.json` 没随组推上去 | 用切块工具重推**整组**；状态行会给"未找到组目录" |
| 两台日志对不上、结论反复 | 同一批设备**两个会话/两个 agent 同时部署**（观测到并行部署、日志被覆盖） | 同批设备同一时刻只允许一个会话部署/抓日志；证据文件拷成唯一名字再分析 |
| 跨机配出来差几百 ms / 出现 68s、103s 的假 Δ | ①开机 NTP 步进**污染 logcat 时间轴**（两台各拨各的）；②把**跨 app 重启**的 `cyc` 混着配对（两台轮次编号不同源） | 跨机对时间用应用打印的 `monotonicMs()`（`wait=`/`took=`），别用 logcat 时间戳；只在同一 session 内做 `(cyc,pts)` 配对 |
| 想复现"进屏保直跳"复现不出来 | **屏保切主页不触发 `onUI_quit`**（easyui 保留活动）→ WallPlayer 不停、不会重新 join | 造 join 只能重启 app（或重启应用进程） |
| 抓帧探针取不到播放进程的通道 | `/data/zkshot <out.raw> vdec <chn> <port>` 报 `GetBuf failed 0xa009200d`，`vdec 4 0` 直接 segfault；`disp` 模式要求该层当时确有帧 | 别把 zkshot 当 vdec 探针；改读 `/proc/mi_modules/mi_disp/mi_disp0` 的层状态 |
| 链接失败：`__atomic_load_8` / `__atomic_store_8` 未定义 | 32 位 ARM 上 `std::atomic<long long>` 需要 `-latomic`，而工程链接行没有（`-z defs` 下直接失败） | 64 位诊断量改用 `std::mutex` 护 |
| `fun add` 报找不到项目 | 工程只有 Manifest、没有 `fun.json` | 手改 Manifest 再 `fun install`（新增包改了 Manifest 必须重跑） |
| 升级后像是没生效（体积没变） | `update.img` 在几 KB 级改动下体积可能**恰好不变**（压缩 + 4KB 对齐） | 别拿体积判断；比对 `.fun/<平台>/libzkgui.so` md5 与烧后回读 `/res/lib/libzkgui.so` 的 md5 |
| 两台画面差一截（差几帧到十几帧） | 校时/钟差：面板 **RTC 是空的、掉电不保时**，开机不校时两台就会差 0~1s（旧版校时只到秒级，实测单台慢 643 / 1060ms、两台互差 416ms） | 等 NTP 同步再进屏保；看 `ClockManager: synced via …` 与 `skew` 中值（判据：单台绝对误差 ≤100ms、两台互差 ≤50ms —— **此判据的 v6 改后数字未取证**） |

## 6. 已知限制

- **截图拿不到视频层**：视频层不在 `/dev/fb0`，`device_screenshot` 只能拿到 UI 层 → 想"拍屏比帧号"做终验必须用相机拍两块屏；设备侧可读 `/proc/mi_modules/mi_disp/mi_disp0` 作客观自证（层 1 `bind mi_vdec chn1`、480×480、`FPS 25.02`、`FinishCnt` 递增）。
- **残差 ±19ms** 主要来自 1s tick 回调的调度抖动（观测 ~9~19ms）；要再压低需把"到点触发"从 1s 心跳换成更细粒度定时源。
- **长跑时钟漂移**：两机各自 NTP 后靠晶振自由跑（实测趋势 ~-0.9ms/min，在噪声内）；要 24h 稳定 ≤1 帧，需定期测钟差并换算到主机时钟系。**现状（v7.10+）**：主机每 **10 分钟**刷新（`ClockManager.cpp:12`）、组内已做**双向 ping-pong 取最小 RTT**，漂移被周期性压回（见 §7）。
- **循环缝**：两段式提前停会在缝处留 ~160ms（末帧冻住 + 拆解），末帧前 ~160ms 内容被截；想零截断可把 `sp_wall_seg_ms` 设成"源片时长 + 200~400ms"（栅格变长、缝变大但内容完整）。多 clip 模式不再按周期截断。
- 排布仅支持**单行横排** `1xN`，不支持 2×2 等二维排布；主从角色需**人工设置**，无自动选举；从机改配置后需停/启应用（或等重新进屏保）才生效。
- 多 clip 组导出**固定 25fps**（源 24/30fps 会重采样，同 clip 内各段一致 → 不影响相位对齐）；源片**自带 letterbox 黑边不会自动去掉**（要自己放大到黑条出框）。
- 设备 `/mnt/sdnand` 只有 **75MB** → 多 clip 大组要用"只推本机那一段"的分发方式（`--only-mine`）。
- **NTP v6 校时改造的改后实测数字未取证**（源材料标占位）：判据 = 单台绝对误差 ≤100ms、两台互差 ≤50ms，本文不引用为实测（该判据的**校准源口径已换代**：现行实现见 §7；v7 现场复测画面偏差 −1~+2ms 可作旁证，见主源 §14）。
- 平台侧：Z20 拼接走**本机自建硬解**（MI VDEC + MI DISP）；easyui 自带 zkmedia 在 Z20 是软解（FFmpeg），不参与拼接。

## 7. 现行 NTP / 校时口径（v7.10+；改自 2026-09-27 v6 口径）

> evidence 全部**实读**自工程 `projects/SmartPanel_HA/src/system/ClockManager.cpp`（下表 `CM.cpp` = 该文件，行号为 2026-10-01 实读）。
> **⚠️ 文件头注释与实现打架**：`CM.cpp:2-12` 仍写着"网关自动发现 + 公网兜底"（v6/v7.10 之前的旧描述）；
> **现行实现以 `:158-172` 为准 —— 默认网关已不进 NTP 列表**（理由见 `:160-164`）。照抄文件头就会写出过时口径。

| 项 | 现状（v7.10+，现行） | 工程出处 |
|---|---|---|
| 时钟源 | **只走内置公网 IP 列表**，SNTP **按 IP 直连、不走 DNS**；**默认网关不在列表内** | `CM.cpp:106-115`（列表）、`:158-172`（`:160-164` 明确"干掉网关"） |
| 列表与排序 | 国内优先 → 国际兜底：`203.107.6.88`(阿里,~40ms) → `120.25.115.20`(阿里,~6ms 最稳) → `182.92.12.11`(阿里北京) → `162.159.200.1`/`162.159.200.123`(Cloudflare,时通时不通) → `216.239.35.0`(Google,国内不可达/出国兜底) | `CM.cpp:106-115` |
| 网关为何移除（v7.10，钟工 2026-09-29） | 实测网关不跑 NTP（UDP 123 超时），每轮先白等 ~3s 才回落公网（日志 `delta≈3.3s` 即这段等待，非拨钟量）；局域网上百台设备没必要天天敲网关 123 | `CM.cpp:160-164` |
| SNTP 实现（v7.11/v7.13） | v7.11 弃用 `ntp` 包内部实现（反汇编确认其 `getTime()` 无四时间戳偏移、系统性慢 ~0.3s）；v7.13 用 **lib-ntp 包代码 + 外层补采样**：每服务器 **4 样本**、**按最小交换耗时（RTT）挑一**、四时间戳算偏移 | `CM.cpp:24-30`、`:32-37`、`:56-61`、`:63-85`、`:87-105`、`:219-255`（`:223` `kSamples=4`） |
| 刷新频率 | 上电重试到成功；成功后 **每 10 分钟**刷新（v7.6，钟工 2026-09-28；旧口径「每 30 分钟」） | `CM.cpp:12`、`ClockManager.h:57`（`kRefreshMs = 10*60*1000`） |
| 保护机制 | ① tick **在飞保护**（有任务在飞且 <20s 不重复发起）② **最小发起间隔 30s** ③ 偏移 **±20ms 内不拨钟** | ①`CM.cpp:337` ②`:339`（注释 `:324-328`）③`:233-236` |
| 组内跟随 `groupFollow`（v7.7/v7.9） | 死区 **±15ms**；**>1s 直接 `settimeofday` 步进**；小偏差做**恒定速率慢爬 ≈1ms/s**、**不做比例增益**（WiFi RTT 抖动 50~130ms，1/4、1/8 增益都会振荡） | `CM.cpp:279-308`（死区 `:281`、步进/慢爬 `:287-295`） |
| 日志/状态文案 | `ntp try N servers[..]=..` / `pkg ntp <ip> exch=<ms> off=<ms> (best of 4 samples)` / `synced via <server> tv=.. before=.. after=.. delta=..ms` / `sntp offset in ±20ms -> keep clock` / 状态行「每 <N> 分钟刷新」 | `CM.cpp:202-204`、`:231-232`、`:266-268`、`:236`、`:373-376` |
| 已修坑（v7） | 「周期刷新」last-ok 记账未更新 → 条件每 tick 恒真 → **每秒重校 + 步进钟**（现场 `err=103/352/310ms`）→ 已由在飞保护 + 30s 最小间隔修复 | `CM.cpp:324-328`、`:337`、`:339` |

**历史（v6，已废弃，勿照用）**：`ntp 0.1.0 → 2.1.1`（回调 `timeval`）；**默认网关优先** → 内置公网兜底；**每 30 分钟**刷新；拼接侧 `skew` 取近 5 次中值。详见主源 §13.2.B。

## 8. 相关

- 视频层不在 `/dev/fb0`、拼墙抓不到画面、vdec 通道与截图角度 → `knowledge/devflow/device-screenshot.md`
- 多设备并行跑测试跑批 + 机读报告（真机验收怎么批量跑） → `knowledge/devflow/device-test-run.md`
- 依赖包/网络 API 真机自动化验证套路（出包 → 上机 → 判据） → `knowledge/devflow/package-verify-playbook.md`
- 主源（相位/校时/素材全量细节） → `references/kb/video-wall-sync.md`；解码通道属性（块状花屏） → `references/kb/z20-mi-vdec-channel-attrs.md`；Z20 现场坑（EasyUI.cfg 劫持） → `references/kb/z20-hardware-notes.md`；产品侧说明书 → `projects/SmartPanel_HA/docs/说明书-多屏拼接.md`
