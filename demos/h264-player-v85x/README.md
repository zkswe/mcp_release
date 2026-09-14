# h264-player-v85x — V85X 硬件 H264 播放验证工具（bin 工程）

> **状态：✅ 编译通过 + ✅ 真机解码验收（V851 / 640×480：`init_ex -> 0`、解码回调 18~21 次、`crop(0,0,640,480) fmt=5`）**
> **✅ 固化验收**：本包里的 `.so` 经 `fun pack` → `update.img` → ADB 刷入，`/res/lib` 实测从 21624 变成 17528，
> 且不推库直接跑命中 `/res/lib/libawh264player.so`（详见 `knowledge/v85x/h264-player-usage.md` §7.1）。
> 验证环境：`Zkswe_V85X_SPINOR`（480×800）。带显示层的业务验收（透明窗口/图层释放）请在目标工程里跑。
> 配套知识：`knowledge/v85x/h264-player-usage.md`（原理 + 坑 + 两条路线的选法）。

## 这个 demo 解决什么

V85X（V853/V851/V553）上的**硬件 H264 解码**是能用的，但"能用"和"一次写对"之间隔着一堆**无声失败**：

- 起播瞬间**进程没有任何报错就消失**（stderr 被指向 /dev/null）→ 90% 是 `ZKMEDIA_H264_VBVSIZE` 没设；
- 画面全黑但"解码正常" → UI 层没有 `visible:true` 的透明窗口，或残留视频层没释放；
- 想解 720p 却发现被内存卡死 → 要靠 `SCALE_DOWN_2 / _4` 缩放解码；
- 判断"有没有出画"用错 API → `get_picture_count` 不是队列长度。

本工具把**排查所需的三个硬证据**（解码回调 / MemAvailable / 库加载路径）直接打进日志，
喂一段 H264 ES 就能看清到底卡在哪一步。

## 三步跑起来

```bash
# ① 取库（官方包 awh264player@1.0.0）
fun install -p v85x                     # 会把包装到 <registry>/public/v85x/awh264player/1.0.0/
#   本 demo 已把包内 include/h264_player.h 拷进 src/dependencies/include/；
#   你还需要把 .so 放进 lib-no-link（只打包、不参与链接）：
mkdir -p src/dependencies/lib-no-link
cp <registry>/public/v85x/awh264player/1.0.0/lib/libawh264player.so src/dependencies/lib-no-link/

# ② 编译
fun build -p v85x

# ③ 上机（fun launch 不推 lib-no-link，调试期手动推）
adb push .fun/v85x/h264player-v85x /tmp/
adb push <registry>/public/v85x/awh264player/1.0.0/lib/libawh264player.so /tmp/
adb shell chmod 777 /tmp/h264player-v85x
adb shell /tmp/h264player-v85x /tmp/test_720p.h264 1280 720 0 2 15
```

> ⚠️ 用完把 `/tmp` 里的库删掉或**别往 `/data` 放同名库**：`/data` 在 `LD_LIBRARY_PATH` 最前，
> 会遮蔽固化后 `/res/lib/` 里的版本（升级了库却跑着旧的，且日志毫无异常）。

## 命令行

```
h264play <file.h264> <srcW> <srcH> [rot=0|90|180|270] [scale=1|2|4] [seconds=10]
例：h264play /tmp/test_720p.h264 1280 720 0 2 15     # 720p 源，1/2 缩放解码，跑 15 秒
```

## 验证点（按这张表看日志，逐条能对上）

| 看什么 | 期望 | 对不上的话 |
|---|---|---|
| `[dl] 已加载 …` + **`[dl] 实际文件 …`** | 第二行给出**真实命中的文件**（`/tmp/...` 还是 `/res/lib/...`）——判“固化生效没有”看这行，别只看“ls 有文件”（同名前库可能体积不同：官方包 17528 / 参考工程那份 21624） | 库没推到、或名字不对 → 先解决加载 |
| `[mem] 起播前 MemAvailable` | **≥ 3 MB** | 低于 3MB 必挂；被 OOM 杀过要**重启板子**（内存不会自己回来） |
| `h264_player_init_ex(...,flag=0x…) -> 0` | 返回 0 | 非 0：先查 VBVSIZE 是否在**dlopen 之前**设过 |
| `[cb] 解码回调 #1 …` | **回调在涨** | 一帧不涨：数据里没有 SPS/PPS/IDR，或喂的是 TS 不是 ES |
| `crop(w,h)` | 等于**源**分辨率（如 1280x720） | 是显示区尺寸说明参数传错（init 的 w/h 是源分辨率） |
| `[stat] 解码回调 N 次 (硬件解码出画 ✅)` | N > 0 | N = 0 时按上面三条依次排查 |
| 屏上有画面 | 显示区有图像 | 黑屏但回调在涨 → UI 层缺透明窗口 / 残留图层未释放（见 `knowledge/v85x/display-layer-debug.md`） |

内存档位实测参考（720p，V851s 56MB 内存）：不缩放 **2.6MB** ⚠️ / 1/2（`scale=2`）**4.1MB** ⭐ / 1/4（`scale=4`）**6.5MB** ✅。

## 实测记录（2026-09-14，V851 480×800）

| 场景 | 结果 |
|---|---|
| 不推库（靠 `/res/lib` 里已有的那份 21624） | ✅ `init_ex -> 0`，解码回调 17 次 |
| 把官方包那份（17528）推到 `/tmp` | ✅ dlopen **命中 `/tmp/libawh264player.so`**（`/tmp` 在 ld 路径最前，遮蔽 `/res`），解码回调 18 次 |
| `fun pack` 出包（zkgui 工程） | ✅ `.fun/v85x/imgout/lib/` 里出现了 `lib-no-link/` 下的库；⚠️ bin 工程不能 pack（`FATAL libzkgui.so not found`） |
| **ADB 固化 + 刷后验收** | ✅ `push update.img /tmp/` → `setprop sys.zkupgrade.dir /tmp` + `flag 255` → **`setprop ctl.restart zkswe`** → 整机重启后：`/res/lib/libawh264player.so` **21624 → 17528**、`/res/ui` 只剩新工程页；不推库直接跑 → `[dl] 实际文件 /res/lib/libawh264player.so` + 解码回调 21 次 |

## 为什么不去把包声明成依赖（而是 dlopen + lib-no-link）

这是我在这块板子上实测出来的结论，**别改回去**：

| 试法 | 实测结果 |
|---|---|
| `fun.json` 只声明 `awh264player` | ❌ 链接失败：`libawh264player.so: undefined reference to CreateVideoDecoder / hw_display_init / hwd_layer_* / SubmitVideoStreamData / __android_log_print …`（bin 工程带 `-Wl,-z,defs`，共享库的未解析符号在链接期就是硬错） |
| 再补 `aw-mpp`（它带 `libvdecoder.so` / `libVE.so` / `libhwdisplay.so` …） | ❌ 变成 `libmedia_mpp.so: undefined reference to snd_pcm_* / snd_mixer_*`（alsa）——而 **v85x 包仓库里没有 alsa 包** |
| **本 demo（`include/` + `lib-no-link/` + 自己 dlopen）** | ✅ 编译通过；运行时由设备 ld 路径解析全志侧依赖（`/lib/eyesee-mpp` 已在 ld 路径里） |

> 也就是说：**官方包里的 `.so` 不适合直接上链接行**；厂商参考工程用的也是这个形态
> （`.so` 放 `lib-no-link`、由门面库 dlopen）。改法只有这三种：① 自己 dlopen（本 demo）；
> ② 拿厂商的 `libzkmedia.a` 门面（`zk_h264_player_*`，V85X 包仓库里没有 `zkmedia` 包，要找厂家）；
> ③ 把全志侧依赖库也凑齐再直链（成本最高，不建议）。

## 代码里修过的坑（别回退）

1. `setenv("ZKMEDIA_H264_VBVSIZE", "1048576", 0)` **必须在 dlopen 之前**（库在加载时读它）；
   第三个参数 `0` = 外部已设的不覆盖，现场想调大直接 `export`。
2. 缩放只能用 `h264_player_init_ex`（三参的 `h264_player_init` **没有 flag 参数**）。
3. `init` 的 w/h 是**源**分辨率，不是显示区（显示区走 `set_pos`）。
4. 判"出画"看**解码回调**，不看 `h264_player_get_picture_count`（那是"已提交帧数"，喂多少报多少）。
5. 喂帧节流别开太大：曾用"每帧最多等 1 秒"的 guard，而缓冲长期在阈值之上 → 每帧都等满，
   看起来像"喂不动了"。本 demo 固定约 30fps 节流；真实流请按**媒体时间**做背压。
6. `fmt=5` 的回调帧是两平面，**不要当 I420 解释**（照 I420 转帧会出色度错乱）。

## 与 zk_h264_player_* 的关系

厂商门面是另一套 API（多 `preload` / `flush` / `need_iframe`，`zk_` 前缀），
两者**头文件互不覆盖**、**不能混用**。选哪条、以及 V85X 上没有 `zkmedia` 包这个事实，
见 `knowledge/v85x/h264-player-usage.md` §0/§1.3。
