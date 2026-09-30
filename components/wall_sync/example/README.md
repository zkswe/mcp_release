# wall_sync · example（两个示例：一个跑逻辑、一个接工程）

| 文件 | 用途 | 能不能独立编 |
|---|---|---|
| `zk_wall_example.cc` | **最小可跑示例**：配置 + 起播 + 状态打印。用**桩引擎**（打印它收到的文件、按时长睡满一轮），不需要任何媒体/解码器 | ✅ PC/WSL 可编可跑（Linux，POSIX） |
| `flythings_wiring.cc` | **FlyThings 工程接线样板**：官方包 `SimplePlayer` 引擎适配 + `prefs → SyncConfig` + 日志钩子 + 组内时钟跟随钩子 + 屏保页生命周期（进/出/1s 定时器）+ 两个内核互斥的处置 | ❌ 引用工程符号（`mVideoSsPtr`/`mImageSsBgPtr`/`SS_SCR_W`），拷进工程按自己的类名改，**不随组件发布** |

---

## 1. `zk_wall_example.cc`：先跑通逻辑链

```bash
# 在 components/wall_sync/ 下（WSL / Linux）
g++ -std=c++11 -Wall -Iinclude -Isrc \
    -I/mnt/c/<你的依赖包注册表>/z20/rapidjson/1.1.0/include \
    src/zk_wall_sync.cpp src/zk_wall_player.cpp example/zk_wall_example.cc \
    -o /tmp/zk_wall_demo -lpthread

mkdir -p /tmp/wallroot/zksw-wall
/tmp/zk_wall_demo zksw-wall /tmp/wallroot      # 参数：组名、素材根目录
```
> 本仓自测用命令（2026-09-30 实测通过，`-Wall -Wextra` 无告警）：把 `<rapidjson>` 换成注册表里的路径，
> 形如 `<依赖包注册表>/public/<平台>/rapidjson/1.1.0/include`（Windows 侧注册表在 `\.fun\registry\public\<平台>\`，WSL 里经 `/mnt/...` 访问）。

**能看到什么（自测即判据）**：

1. `Sync::start -> code=0`；`playlist 不可用（no_playlist_json）-> 单 clip 模式`（盘上没清单时的正常路径）；`组目录 1 个`（`listGroups()`）。
2. 每秒一条 `wall tick: now=… epoch=… seg=… phase=… wait=… next=… drift=… skew=… ready=… lost=… playlist=…`。
3. `Player::start -> code=0`；玩家线程打印 `边界踩点排队 距边界=…ms lead=150ms -> …`，然后**正好在「整边界 − 150ms」**打印 `play …`（示例用 10s 周期便于观察；真实单 clip 必须 = 素材真实时长）。
4. 状态行每秒打印：`state=主机 · seg_1/2 · 已发 epoch`、`phase/wait/next`、`skew(epoch,rtt=-1)`、`clip=0/1`、`cyc=`。
5. 退出时 `player thread exit (cycles=…)` → `stopped` → `Sync::stop()`，进程 0 退出。

**看不到什么（本示例的边界）**：没有任何画面（桩引擎不解码/不上屏）；不覆盖真机相位口径（那是 `platforms.md §2.4` 的事）。

---

## 2. `flythings_wiring.cc`：接进真实工程

按文件里 ①②③④⑤⑥ 六段顺序接（每段都标了真源出处）：

1. **① 日志钩子** → 工程 `LOGD/LOGW/LOGE`（不接 = 设备上看不到组件任何输出）。
2. **② 引擎** → `SimplePlayerEngine : zk::wall::Engine`，`open()` 里 `setSynchronizing(true)` + 旋转（环境变量 `SIMPLE_PLAYER_CLOCKWISE_ROTATION`），`play()` 里 `sp_.play(file, base::Rectangle(...))`，`stop()` 里 `sp_.stop()`。
3. **③ 配置** → `wallConfigFromPrefs()`：把 `sp_wall_en/group/idx/n/role/seg_ms/lead_ms/peer/anchor_ms` + `sp_video_sel`（零配置推导）读成 `SyncConfig`。
4. **④ 时钟跟随** → `wallClockFollowHook()` 把新鲜的双向测时样本喂给工程的 `ClockManager::setGroupHealthy()/groupFollow()`（来源工程 v7.7 起的做法）。
5. **⑤ 屏保生命周期** → 进入：`Sync::start()` + `configure/setEngine` + `publishNow()/requestEpoch()/pingNow()`；1s 定时器：时钟守卫 → `Sync::tick()` → 熄屏/编辑态停播 → **停 easyui 播放器 + 沉降 400ms** → `Player::start(wl.playKey())`；退出：`Player::stop()`。
6. **⑥ 设置页** → 配置改完调 `Sync::start()`（幂等重载）+ `listGroups()` / `queryPlaylist()` 给 UI 行用。

**三条硬注意（都是踩出来的，改动前先读）**：

- **节目键用 `Sync::playKey()`**，别拿"当前 clip 文件"当键 —— 否则每切一个 clip 都被当成换节目 → 反复拆建 MI 图层。
- **两个内核不能同时上屏**：simple 引擎与 easyui `ZKVideoView` 抢 MI 图层；`stop()` 拆解是异步的 → 用**总闸**拦住 easyui 的起播路径 + 停后**沉降 400ms**（否则 `mi_disp0` 的 chn0 会留下卡死的 workingTask，表现"画面冻住"）。
- **退出屏保页必须 `Player::stop()`**（拼接只在屏保生效）；播放中别 kill 应用（MI 驱动可能卡死，改完配置重启整板）。

---

## 3. 相关

- 组件总览/API/配置表/验收口径 → `../README.md`
- 平台支持与前置条件 → `../platforms.md`
- 底层包与版本口径 → `../Manifest.xml`
- 原理/故障全表 → `knowledge/devflow/video-wall-sync.md`
