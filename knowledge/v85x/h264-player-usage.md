# 🎬 V85X 硬件 H264 播放器：官方包 `awh264player` vs 厂商门面 `zk_h264_player`

> 🔍 **检索导引**：V85X/V853/V851/V553「**硬件 H264 解码**」「**awh264player 包怎么用**」
> 「**zk_h264_player**」「**h264_player_init_ex**」「**HLS/TS/RTSP 流送硬解上屏**」「**解码缩放 1/2 / 1/4**」
> 「**起播就静默退出 / 进程无报错消失**」「**get_picture_count 不准**」「**lib-no-link 推不上去**」。
> 定规：**只记录怎么用**（库闭源，不解析不深挖）。来源：2026-09-14 V851s 真机实测 + 包仓库/本机注册表现场核对。
> 🧪 **同仓 demo**：`demos/h264-player-v85x/`（bin 工具：env + dlopen + init_ex + 解码回调 + 喂 AU，**✅ 编译通过**）。
> ⚠️ 与 MPP 路线（`libmedia_mpp` / `AW_MPI_VDEC_*`）是**两条独立链路**，同一颗 VE、同一个 disp 视频层，**互斥**。
> 💡 显示层结构 / UI 层透明窗口 / 图层释放见 `v85x/display-layer-debug.md`、`v85x/videoview-transparent-window.md`（本篇不复述）。

---

## 0. 先选路线：两套 API 长得像，**不可混用**

| | **路线 A：官方包**（先试这条） | **路线 B：厂商门面**（参考工程用法） |
|---|---|---|
| 依赖声明 | `awh264player`（V85X=1.0.0）；⚠️ **V85X 上要配 dlopen 用法**（§1.4） | 无包；库由厂商参考工程提供 |
| 头文件 | 包内 `include/h264_player.h` | 工程内 `src/media/h264_player.h`（或参考工程 `src/dependencies/include/`） |
| 对外 API | **`h264_player_*`**（13 个，含 `init`/`init_ex`）+ `h264_multi_player_*`（10 个） | **`zk_h264_player_*`**（14 个） |
| 形态 | 普通动态库（⚠️ **V85X 上不要直接上链接行**，用 dlopen，见 §1.4） | `zk_*` 静态库 **dlopen wrapper** + `libawh264player.so`（`lib-no-link/`，调试期要手推） |
| 获取方式 | `fun.json` 声明后 `fun install` | 向 FlyThings 厂家要参考工程（**V85X 包仓库没有 `zkmedia` 包**，见 §1.3） |

> ⚠️ **这条路最贵的坑就是选错路线**：`zk_h264_player_init` 在官方包里**没有**（包内 `.so` 符号表只有
> `h264_player_*`），写错就是 `undefined reference`；反过来，用了厂商门面却按包的 API 名写也编不过。
> 两个头文件**互不覆盖**（包内头文件里连 `zk_` 影子都没有）——**先 `grep zk_h264 头文件` 确认手里的库是哪一条**。

---

## 1. 路线 A：官方包 `awh264player`

### 1.1 包内容与平台（2026-09-14 现场核对）

V85X `1.0.0` 包内实测就三个条目：`CHANGELOG.md` + `include/h264_player.h` + `lib/libawh264player.so`。

| 平台 | 可用版本（包站现场查） |
|---|---|
| v85x / v85xemmc | `1.0.0` |
| f133 | `1.1.0`、`1.0.0` |
| f136 | `1.1.0`、`1.0.1`、`1.0.0` |
| t113 | `1.1.0`、`1.0.0` |

> 包站 `description` 为空、`get_package_api` 也解析不出内容（C 头不解析，见 §7 缺口）⇒ **以本篇 + 头文件为准**。

### 1.2 ⚠️ 声明位置：`fun.json` 优先，写错地方会**静默不装**

工程里同时有 `fun.json` 与 `Manifest.xml` 时，`fun` 只用 `fun.json`（实测打印
`WARNING "fun.json" and "Manifest.xml" both exists, will use "fun.json" first`）。
此时把 `<package id="awh264player">` 写进 `Manifest.xml`，`fun install` 会**报成功**，
但 `.fun-lock.json` 里 `"v85x": {}` 是空的 —— **包根本没装**（后面报 `package not found in local` 或头文件找不到）。

```jsonc
// fun.json —— 依赖要写在这里
{
  "name": "h264demo", "version": "1.0.0", "platform": "v85x", "type": "executable",
  "dependencies": { "awh264player": "1.0.0" }
}
```
**判据**：`fun install` 后看 `.fun-lock.json` 的依赖键是否出现；或看下载日志有没有 `fetch awh264player`。

### 1.3 最少可用序列（照抄）

```c
#include "h264_player.h"

setenv("ZKMEDIA_H264_VBVSIZE", "1048576", 0);   // ★★ 见 §4，必须在库被加载之前
int r = h264_player_init_ex(1280, 720,            // 源分辨率（不是显示区）
                            E_DISP_ROT_0,
                            E_H264_PLAYER_FLAG_STREAM_EOF | E_H264_PLAYER_FLAG_SCALE_DOWN_2);
if (r != 0) { /* 明确报错，不要continue */ }
h264_player_set_decode_cb(on_frame);   // “真的出画了”的唯一硬证据
h264_player_set_pos(0, 0, 480, 270);   // 屏幕坐标的显示区
h264_player_show();
/* 持续喂：H264 Annex-B，起播首包必须含 SPS/PPS + IDR */
h264_player_put_frame(es_data, es_size);
/* 收尾： */
h264_player_hide();
h264_player_deinit();
```

- **要缩放/要 flag 只能用 `h264_player_init_ex`**；`h264_player_init(w,h,rot)` 是**没有 flag 的三参版**。
- 包里另有 **多实例 API**（`h264_multi_player_create/destroy/...`，10 个）：同进程多路硬解时用；
  ⚠️ 本平台**未实测**（本表只保证单实例路径）。
- 包里**没有** `preload` / `flush` / `need_iframe` —— 看到这三个名字说明你在看路线 B 的头文件。

### 1.4 ⚠️ V85X 上**别把包直接声明成依赖**（两次实测失败），用 dlopen

| 试法 | 实测结果（`fun build -p v85x`） |
|---|---|
| `fun.json` 只声明 `awh264player` | ❌ 链接失败：`libawh264player.so: undefined reference to CreateVideoDecoder / hw_display_init / hwd_layer_close / hwd_layer_render / SubmitVideoStreamData / VideoStreamBufferSize / __android_log_print …`（bin 工程带 `-Wl,-z,defs`，共享库的未解析符号在链接期就是硬错） |
| 再补 `aw-mpp`（它带 `libvdecoder.so`/`libVE.so`/`libhwdisplay.so`/`libMemAdapter.so`/`libcdx_base.so`/`libvideoengine.so` …） | ❌ 变成 `libmedia_mpp.so: undefined reference to snd_pcm_* / snd_mixer_*`（alsa）——而 **v85x 包仓库没有 alsa 包**（74 个包里没有） |
| ✅ **推荐**：头文件放 `src/dependencies/include/`，`.so` 放 `src/dependencies/lib-no-link/`，代码里 **dlopen + dlsym** | ✅ 编译通过；运行时全志侧依赖由设备 ld 路径解析（`/lib/eyesee-mpp` 已在 `/etc/ld-musl-armhf.path` 里） |

**为什么 dlopen 能成、直链不能**：`-z defs` 要求链接期解析**全部**符号，而这些符号的实现在**设备运行时**才有；
dlopen 把解析推到运行时，正好绕过。厂商参考工程的 `zk_*` 门面也是 dlopen 形态（§2.1 符号表证据）。
⇒ 新工程要么**自己 dlopen**（照同仓 `demos/h264-player-v85x`），要么**找厂家要 `libzkmedia.a` 门面**，别去凑全志侧库。

> 🔎 这条坑的搜索词：`undefined reference to CreateVideoDecoder` / `-Wl,-z,defs` /
> `snd_pcm_hw_params_sizeof` / `aw-mpp 链接失败` / `awh264player 包不能直接依赖`。

---

## 2. 路线 B：厂商门面 `zk_h264_player_*`（参考工程用法）

### 2.1 三层结构（`.a` 符号表实测）

```
zk_h264_player_*   ← 应用调用（头文件 h264_player.h，14 个函数）
      ↑ 静态库里的 wrapper，实测在 <参考工程>/src/dependencies/lib/libzkmedia.a
         （`.a` 内同时含 zk_* 与 h264_player_* 符号 + dlopen/dlsym 字符串 "libawh264player.so"）
h264_player_*      ← 真实现 libawh264player.so（dlopen + dlsym）
      ↓ NEEDED：libvdecoder / libVE / libhwdisplay / libMemAdapter / libcdc_base /
                 libcdx_common / libvideoengine / libawlog  ← 设备自带
```

**依赖不用你操心**：这些 `.so` 在设备 `/lib/eyesee-mpp/`，而设备 `/etc/ld-musl-armhf.path`
已含 `/lib:/lib/eyesee-mpp`；`init.rc` 的 `LD_LIBRARY_PATH` 还含 `/data:/tmp:/res/lib:/res/zkswe`。

### 2.2 API 全表（14 个）

```c
void zk_h264_player_preload(void);                                      // 预载（内部线程 dlopen）
int  zk_h264_player_init(int w, int h, enum disp_rot_e rot, int flag);   // 0 = 成功
void zk_h264_player_deinit(void);
void zk_h264_player_set_decode_cb(h264_decode_frame_cb cb);
void zk_h264_player_flush(void);
void zk_h264_player_show(void);        void zk_h264_player_hide(void);
void zk_h264_player_set_mirror(int mirror);
void zk_h264_player_set_rot(enum disp_rot_e rot);
void zk_h264_player_set_pos(int x, int y, int w, int h);    // 显示区（屏幕坐标）
void zk_h264_player_set_crop(int x, int y, int w, int h);   // 裁剪（**旋转后**坐标系）
void zk_h264_player_put_frame(uint8_t *data, uint32_t size); // Annex-B
int  zk_h264_player_get_picture_count(void);
int  zk_h264_player_need_iframe(void);                       // 1 = 当前需要关键帧
```

### 2.3 最少可用序列

```c
setenv("ZKMEDIA_H264_VBVSIZE", "1048576", 0);   // ★★ 必须在第一次 preload/dlopen 之前
zk_h264_player_preload();
zk_h264_player_init(srcW, srcH, E_DISP_ROT_0, E_H264_PLAYER_FLAG_STREAM_EOF | E_H264_PLAYER_FLAG_SCALE_DOWN_2);
zk_h264_player_set_decode_cb(on_frame);
zk_h264_player_set_pos(x, y, w, h);
zk_h264_player_show();
zk_h264_player_put_frame(es, len);
zk_h264_player_hide();
zk_h264_player_deinit();
```

---

## 3. 通用：枚举、回调、flag

```c
enum disp_rot_e { E_DISP_ROT_0, E_DISP_ROT_90, E_DISP_ROT_180, E_DISP_ROT_270 };  // 顺时针
enum h264_player_flag_e {
  E_H264_PLAYER_FLAG_STREAM_EOF   = 0x01,
  E_H264_PLAYER_FLAG_DISP_UNCACHE = 0x02,
  E_H264_PLAYER_FLAG_SCALE_DOWN_2 = 0x10,   // ★ 1/2 缩放解码
  E_H264_PLAYER_FLAG_SCALE_DOWN_4 = 0x20,   // ★ 1/4 缩放解码
};
typedef struct {                       // 解码回调给的帧
  int fmt;                             // 实测 = 5
  int width, height;                   // **解码缓冲尺寸**（可能 = 源 +16 对齐），不是显示尺寸
  int left, top, right, bottom;         // **有效画面（crop）** ← 要尺寸用这个
  uint8_t *data0, *data1, *data2;
} h264_decode_frame_t;
```

- 例：源 426x240 → 回调 `width/height = 448x256`、`crop = (0,0,426,240)`。
- `fmt = 5` 的两平面**不要当 I420 解释**（照 I420 转帧会出色度错乱）。
- `flag` 可组合（如 720p 播 1/2：`STREAM_EOF | SCALE_DOWN_2`）。

---

## 4. ★★ 头号坑：起播瞬间「静默退出」= `ZKMEDIA_H264_VBVSIZE` 没设

- **症状**：进程**没有任何报错就消失**（stderr 被重定向到 /dev/null，日志断在"起播"那几行），
  随后被 init 拉起 → 现场表现为"重启→重播→再重启"。`init()` 的返回日志都来不及打。
- **根因**：库用**默认的小码流缓冲**，720p 的 I 帧几百 KB 装不下。
- **做法**：在**库被加载之前**（路线 A：`init*` 之前；路线 B：首次 `preload()` 之前）
  `setenv("ZKMEDIA_H264_VBVSIZE", "1048576", 0)`（`0` = 外部已设的不覆盖，方便现场调参）。
  ⚠️ 环境变量是**加载时读的** ⇒ 改完要**重启应用**才生效。
- **实测**：设之前 720p(1.2~1.5Mbps) + 1/2 缩放**起播即崩**；设之后连续 900 帧、丢 0。
- 另有 `ZKMEDIA_H264_LAYER`（显示层号，参考工程里出现过），本平台一般不用改。

---

## 5. 缩放解码与内存（V851s 56MB 内存，实测）

| 源 | 缩放 | 解码输出 | `MemAvailable` |
|---|---|---|---|
| 1280x720 | 不缩放 | 1280x736 | **2.6 MB** ⚠️ 危险 |
| 1280x720 | **1/2**（`0x10`） | 640x384 | **4.1 MB** ⭐ 推荐 |
| 1280x720 | **1/4**（`0x20`） | 320x192 | **6.5 MB** ✅ 最安全 |
| 426x240 | 不缩放 | 448x256 | 充裕 |

- **挑档规则**：源宽 > 屏宽上限就下一档；480x800 屏上 1/2（640x360）已比屏还大，够用。
- **内存门槛**：起播要申请解码/显示缓冲，**`MemAvailable < 3MB` 必挂或静默消失**；
  被 OOM 杀过的进程内存**不会自己回来，必须重启板子**（这点很反直觉，实测浪费过半天）。
- 判据与手法：读 `/proc/meminfo` 的 **`MemAvailable`**（别只看 `MemFree`）；
  起播前 `echo 3 > /proc/sys/vm/drop_caches`（本板实测一次腾出 +16MB）。
- ⚠️ 表中数值是**单点实测值**（同一段流、同一时刻读 `/proc/meminfo`），不是长期均值 —— 只看量级与大小关系。

---

## 6. `get_picture_count()` **不是**队列长度，别拿它做背压

它更像"已提交帧数"：**喂多少就报多少**，哪怕显示线程一帧没取走（实测恒等于池大小）。
⇒ 判断"解码器有没有真出画"**只看解码回调**；做背压请用**媒体时间 vs 播放时间**
（例如落后 > 600ms 才丢帧）。

**另一个配套坑**：喂帧节流的 guard 别开太大 —— 曾用 `guard<100 × 10ms`（每帧最多等 1 秒），
而缓冲长期在阈值之上 ⇒ **每帧都等满 1 秒**，看起来像"喂不动了"。改 `30 × 5ms` 即可。

---

## 7. 部署：库放哪、运行时找得到吗（`lib-no-link` / `/data` 遮蔽）

> 官方 wiki（`manifest/add_local_lib.md`）只写了「`dependencies/lib-no-link` 下的动态库**仅随程序打包**，
> 不参与编译」—— 最要紧的两件事（打进哪、运行时可见性）没写。以下是实测口径。

| 场景 | 行为 |
|---|---|
| `src/dependencies/lib/` | **参与编译 + 自动链接**（本地静态/动态库都放这里） |
| `src/dependencies/lib-no-link/` | **不参与编译**；`fun pack` 会把它放进升级镜像的 `lib/` → 设备上即 **`/res/lib/`** |
| `fun launch`（调试推送） | ⚠️ **不推** `lib-no-link/` 里的库 ⇒ 调试期必须手动 `adb push <lib> /tmp/`（或 `/data`） |
| 固化后运行时 | 设备 `LD_LIBRARY_PATH` 本就含 `/res/lib` ⇒ 固化后直接 `dlopen`/`NEEDED` 可用，**无需手推** |
| ⚠️ **同名库别长期留在 `/data`** | `/data` 在 `LD_LIBRARY_PATH` **最前**，会**遮蔽** `/res/lib` 的固化版 ⇒ 升级了库却跑旧的，**日志毫无异常** |

**验收判据**：`ls /res/lib/libawh264player.so` 在（V85X 包内那份约 17KB 级）且
`grep awh264player /proc/<pid>/maps` 命中；固化后要求 maps 里是 **`/res/lib/...` 而不是 `/tmp/...`**。

### 7.1 ✅ 固化链路实测（2026-09-14，V851 真机 + 本机出包，已端到端跑通）

| 环节 | 实测结果 |
|---|---|
| `/res` 是什么 | `/dev/block/mtdblock3` → **squashfs，`ro`**（2.1MB 小分区，100% 满）⇒ **不能直接写，只能靠刷 `update.img` 更新** |
| `fun pack` 把 `lib-no-link/*.so` 放哪 | ✅ 出包中间产物 `.fun/<平台>/imgout/lib/` 里出现了 `lib-no-link/` 下的库（本次放了官方包那份 + 一个临时标记库，两个都在） |
| 镜像格式/体积 | `ZKSWEV1.0-180127`，空工程约 68KB |
| ⚠️ bin 工程能不能 pack | **不能**：`fun pack` 对 `type="executable"` 报 `FATAL libzkgui.so not found, please build project first` ⇒ **固化只适用于 zkgui 工程** |
| **ADB 固化完整序列（实测可用）** | `adb push update.img /tmp/` → `setprop sys.zkupgrade.dir /tmp` → `setprop sys.zkupgrade.flag 255` → **`setprop ctl.restart zkswe`**（**只重启应用**） → 应用重启后读属性执行升级，**升级流程自己触发整机重启**后生效 |
| 刷完 `/res` 是否真变 | ✅ **整体被替换**（逐项核对）：`libawh264player.so` **21624 → 17528**、`libzkgui.so` 体积变、`/res/ui` 只剩新工程的页（`main.ftu` 162B）、带进去的标记库 `libzzmarker.so`(12345) 也在 |
| 固化后运行时能否找到 | ✅ 不推库直接跑：dlopen **实际命中 `/res/lib/libawh264player.so`**，解码回调 21 次 |
| `/tmp` 遮蔽 `/res` | ✅ 实测：把同名库推到 `/tmp` 后 dlopen **真的命中 `/tmp/libawh264player.so`**（`/tmp` 在 `LD_LIBRARY_PATH` 最前） |
| ⚠️ **别被 "/res 已有这个库" 误导** | 实测某板 `/res/lib/libawh264player.so` = **21624 B**，而官方包那份是 **17528 B** ⇒ 它是**参考工程 `lib-no-link/` 里那份**固化上去的，**不是官方包的 build**。⇒ 判"固化生效了没"要**比体积/sha256**，不能只看"ls 有文件" |

**⚠️ 关于“重启”与“看早了”的纠正（2026-09-14 受控实测）**：
1. **`ctl.restart zkswe` 只重启应用，不重启系统** —— 单跑它（不带任何升级属性）实测：app pid 变化（719→887）、`/proc/uptime` **连续**（249.89 → 270.10，未归零）、`/tmp` 原样保留（标记文件读回正常）。**别把“设备重启”归因于它。**
2. 带升级属性时设备确实会重启（adbd 断、`/tmp` 被清空），那是**升级流程发起的**（`/lib/libzkupgrade.so` 里有 `android_reboot`）；升级是**重启后**才应用的 ⇒ **要等够再查**，看早了看到的还是旧 `/res`。
3. ⚠️ **未做单变量 A/B**：生效那轮用的是 `dir + flag(255) + force(1)`，**`force` / `flag` 的必需性未分离验证**（如实标注，别当结论）。
4. **`/tmp` 是 tmpfs，重启即清空** ⇒ push 镜像、setprop、restart 必须在**同一轮**做完；过后别拿“/tmp 里没文件了”当失败依据。

---

## 8. 显示：它是 disp 硬件视频层，不是控件

- `set_pos` 给的是**屏幕坐标**的显示区；画面从 **UI 层的透明窗口**透出 ——
  **UI 层没有 `visible:true` 的 videoView 透明窗口，画面就被盖住**（典型"解码正常但黑屏"）。
- `set_crop` 用**旋转后**坐标系 ⇒ **`set_rot` 之后再发一次 `set_crop`**。
- 该层是**内核态**的：进程崩溃/重启**不释放**，异常重启后屏上会冻在上一轮残影 ⇒
  **用到视频图层的产品，启动首次初始化必须先释放残留层**（V85X 必做）。
- 排查层用 `cat /sys/class/disp/disp/attr/sys`（**不在 `/dev/fb0`**，fb0 只有 UI 层）。
- 👉 细节与真机判据：`v85x/display-layer-debug.md`（含"**按 ch/lyr 判、不要用格式区间**"这条纠错）。

---

## 9. 起播「无声消失」排查顺序（按这个顺序，别绕）

1. **环境变量**：`ZKMEDIA_H264_VBVSIZE` 设了吗？且是在**加载库之前**？（§4，头号原因）
2. **内存**：起播前 `MemAvailable ≥ 3MB`？被 OOM 过就**重启板子**（§5）。
3. **码流**：喂进去的数据里**已有 SPS/PPS/IDR** 吗？缺了就一直在等（工具见 §10）。
4. **协议**：喂的是 **Annex-B** 吗？（TS 要去掉 PES 头；mp4 要 `h264_mp4toannexb`）
5. **显示**：UI 层有 `visible:true` 的 videoView 透明窗口吗？（§8）
6. **最后才怀疑参数组合**：`rot` 放 init 里还是 `set_rot` —— 实测**都可用**（§11）。

> 排障手段：把 **stderr 从 `/dev/null` 引出来**（或写文件）才有机会看到库内报错；
> 起播前后各 `cat /proc/meminfo`；打日志时**必须打印实际传进去的参数**
> （曾因日志里硬编码 `rot=0` 白跑一轮 A/B）。

---

## 10. 素材与自检

- **TS → H264 ES**（做对照实验用）：剥 PAT → PMT（视频 PID）→ PES 头，顺序写出 ES。
  两个 TS 解析坑：① PSI section 前有 **`pointer_field`**（`payload_unit_start_indicator=1` 时先跳 1 字节再读 `table_id`，
  不跳整段错位 1 字节 → 解出"不存在的 PMT PID"）；② PMT 要跳 `program_info` 描述符
  （`off = 12 + program_info_length`，不是 `12` → 会读出 `stream_type = 0x25`、PID 等于 PMT 自己这类怪值）。
  脚本还应统计 NAL 类型并**警告"没有 IDR / 没有 SPS"**（起播必须有这俩）。
- **验收（真机）**：
  ```bash
  cat /sys/class/disp/disp/attr/sys                                  # ① 视频层是否 enable
  /bin/logcat -d | grep -E "解码回调|h264_player_init|zk_h264_player_init"  # ② 回调在涨 = 真出画
  grep -E "awh264player|eyesee-mpp" /proc/<pid>/maps                  # ③ 库加载与路径（/res 还是 /tmp）
  ```

---

## 11. 参数组合的实测结论（省得你再 A/B 一遍）

| 组合 | 实测 |
|---|---|
| `init(rot=0)` → `show()` → `set_rot(90)` → `set_crop` | ✅ 720p+1/2，36 秒 / 900 帧 / 0 重启 / 丢 0 |
| `init(rot=90)`（不再 `set_rot`） | ✅ 同样 36 秒 / 900 帧 / 0 重启 |
| 720p + `SCALE_DOWN_2` + 90° | ✅（VBV 设好、内存充足的前提下） |
| 960x540 不缩放 + 90° | ✅ |

⇒ **旋转放哪都行**，不是崩因；但 **`set_rot` 之后必须重发 `set_crop`**。

---

## 12. 与其它方案的分工

| 场景 | 用什么 |
|---|---|
| H264 直播/点播上屏，要旋转/缩放/裁剪 | **本包**（硬解，能解 720p，靠 1/2、1/4 缩放） |
| 需要 MPP 家族能力（与摄像头/录像/多路复用同链路） | MPP（`AW_MPI_VDEC_*`），注意 960x544 上限与自愈机制 |
| JPEG / MJPEG | 见 `v85x/jpeg-decode-record.md` |
| 只是要显示"播放器控件" | 框架 `ZKVideoView`（另一条路） |

⚠️ **两条链路互斥**：同一颗 VE + 同一个 disp 视频层，切换前先优雅停掉另一条（停止 → 释放视频层 → 再起）。

---

## 13. 本平台未验证项（如实标注，别当结论用）

1. **包（路线 A）在 V85X 上的真机播放验收**：本次在 V851s 上验证的是**路线 B（zk 门面）**；
   路线 A 的 API/头文件/包结构/**链接失败原因**是现场核对出来的（包下载 + `.so` 符号表 + 两次 `fun build` 实报）；
   包内那份 `.so`（17528）已在 V851 真机上跑通**解码链路**（`init_ex -> 0` + 解码回调 18 次）；
   带显示层的业务验收（透明窗口/图层释放配合）仍建议在目标工程里跑一遍。
2. `h264_multi_player_*` 多实例：**未实测**。
3. 固化后 `/res/lib/libawh264player.so` 的自动加载：✅ **已真机验收**（打包侧 + 刷机侧全通，见 §7.1）。
4. 各平台（f133/f136/t113）的 `awh264player` 包：**仅查到版本号**，未实测。

## 14. 变更记录

- 2026-09-14 首次入库：路线 A/B 分野（含“包里没有 `zk_*`”的现场证据）、**V85X 上包不能直接上链接行的两次实测失败与 dlopen 结论**、
  `fun.json` 优先导致的**静默不装**、`lib-no-link` 部署矩阵与 `/data`、`/tmp` 遮蔽实测、`ZKMEDIA_H264_VBVSIZE`、内存门槛、
  `get_picture_count` 语义、起播排查顺序、参数组合 A/B、未验证项；附 demo `demos/h264-player-v85x/`。
- 2026-09-14 补：**固化链路实测（§7.1）**——`/res` = `mtdblock3` 只读 squashfs（只能刷 update.img 更新）；
  `fun pack` 中间产物 `.fun/<平台>/imgout/lib/` 含 `lib-no-link/*.so`；bin 工程不能 pack；
  “/res 已有同名库（21624）≠ 官方包那份（17528）”的体积判据；`/tmp` 遮蔽 `/res` 的真机实证。
- 2026-09-14 三补：**ADB 固化全流程真机跑通**（push → `sys.zkupgrade.dir/flag` → **`ctl.restart zkswe`** → 等整机重启）；
  刷后 `/res` 整体替换已逐项核对（库体积 21624→17528、libzkgui、`/res/ui` 只剩新工程页、标记库到位），
  且 **dlopen 实际命中 `/res/lib`** + 解码回调 21 次 ⇒ **固化后的运行时可见性与功能均已验收**。
- 2026-09-14 四补（**纠正自己的错误结论**）：把 §7.1 “`ctl.restart zkswe` 会连带整机重启”改成实测口径——
  受控单跑实测它**只重启应用**（app pid 变、`/proc/uptime` 连续、`/tmp` 不清）；带升级属性时的系统重启是**升级流程**发起的（`android_reboot`）；
  并标注 `force`/`flag` 必需性**未做单变量 A/B**。
