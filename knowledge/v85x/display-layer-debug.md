---
id: v85x-display-layer-debug
title: 🖥️ V85X 显示分层调试：releaseLayer 图层释放 / UI 透出 / 回放旋转
category: v85x
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [V85X]
tags: [UVC 摄像头预览, 回放调试, AP+P2P, 否则黑屏, V853, V851, V553 等, aw-dvr, 场景, 视频解码]
evidence: []
---
# 🖥️ V85X 显示分层调试：releaseLayer 图层释放 / UI 透出 / 回放旋转

> 检索导引：问「V85X 视频层黑屏 / 图层次残留 / releaseLayer 什么时候必做 / UI 层盖住视频 / 回放方向不对 / 竖装屏配横 UI 错屏」→ 本文；videoView 透出画面见 `v85x/videoview-transparent-window.md`。
> 2026-09-09 实战沉淀（来源：V85X 竖屏 600×1600 + 1600×600 横 UI 工程，UVC 摄像头预览/回放调试）；2026-09-14 沛哥定规 + V85X 扩展屏（AP+P2P）工程校准：**视频解码返回后必须 releaseLayer，否则黑屏**。
> 适用：**V85X（V853/V851/V553 等）**——竖装屏 + 横 UI + MPP 摄像头（aw-dvr/mpi::）场景；视频解码/播放链路同样适用。
> ⚠️ 仅 V85X 平台生效（disp 分层机制是 V85X 特有）；T113/F133/Z20 按各自链路处理。
> 检索词：releaseLayer / 释放图层 / 视频解码返回 / 解码结束 / 播放器退出 / 黑屏 / 黑屏防御 / disp 层 / /dev/disp / DISP_LAYER_SET_CONFIG / 必做动作 / 开发与验收必做 / 格式区间漏关 / RGB_888 / COLOR 模式 / fb0 抓图看不到黑屏。

## 0. 一句话

V85X 竖屏工程调试「错屏 / 无图像 / 回放方向不对」四板斧，按顺序查：
1. **屏幕旋转（硬件方向适配）**：**错屏根因 = UI 布局尺寸超出物理屏**——横 UI（1600×600）用在竖装屏（600×1600）上，不旋转时 UI 宽 1600 超过物理宽 600，界面/视频内容画到屏幕外 = 错屏。rotateScreen 是**针对硬件物理安装方向的适配**（值由屏幕怎么装决定，不是 UI 分辨率决定），把 UI 旋转 270° 后完整映射进屏内 → `package.properties` 配 `EasyUI.cfg={"rotateScreen": 270}`（触摸不转=不写 rotateTouch）→ **必须 clean 全量重编**（ninja 不感知 package.properties 改动），EasyUI.cfg 由 fun launch 阶段合并生成
2. **图层释放（平台匹配时必做）**：**视频解码返回后 / 启动早期必须做 `releaseLayer()`** 关掉残留 disp 层（保留 UI 层）——V85X 上不做会**黑屏**；**开发与 check 验收都必须做这个**（check_all #19 已机器核验，见 §2-0）
3. **无图像**：UI 层（z=16 最顶）不透明背景盖住 disp 视频层（z=1）→ UI 上必须有**可见的 videoView 透明窗口**（`visible:true` + position=画面区域），下层视频才透出
4. **回放方向**：ZKVideoView 的 `rotation` 是**枚举不是角度**：0/1/2/3 = 0°/90°/180°/270°（顺时针），写 `3` 才是 270°

## 1. 显示分层结构（调试前提认知）

```
disp 输出：UI 层（ch2/layer0，z=16，最顶）
          disp 视频层（ch0/layer1 等，z=1，在下；layer 编号 4/3/2/1 叠放）
底层：视频层画面经 UI 层透明区域透出
```
- disp 状态实时查看：`cat /sys/class/disp/disp/attr/sys`（每层一行：enable/ch/layer/z/fmt/fb/crop/frame/addr）
  - 屏幕分辨率：`cat /sys/class/disp/disp/attr/xres|yres`
- UI 层若全屏不透明（背景色/背景图）→ 视频层白输出也看不见 → 先看这层状态

## 2. releaseLayer：释放残留 disp 图层（保留 UI 层）

### 2-0 ⚠️ 必做场景：① 启动首次初始化（首要）② 视频解码返回后（平台匹配 → 开发与验收都必做）

**沛哥 2026-09-14 定规**：**用到视频图层的产品**，V85X（V853/V851/V553）上 **① 上来第一次初始化就必须先释放图层**（防崩溃重启后残留的系统级图层没释放 → **屏幕永久性异常**）；**② 视频解码返回后**也要释放一次。两处不做都可能黑屏，但 ① 的后果最严重：**是永久性的**。

| 项 | 口径 |
|----|------|
| **平台匹配** | 用到视频图层的产品 + V85X 系（disp 分层平台）；T113/F133/Z20 不适用 |
| **触发时机** | ① **启动首次初始化（首要）**：进程启动早期调一次（UI 起来后、开摄像头/播视频前）；② **视频解码返回后**：解码结束 / 播放器退出（`zk_h264_player_deinit` 一类）/ 播放页销毁返回 UI 时 |
| **为什么启动必须释放** | disp 图层是**系统级（内核/disp 驱动）状态，不随进程退出而清理**：程序崩溃/重启后，上次残留的图层还在，会盖在 UI 上；如果新启动的进程不去释放，**重启多少次都在 → 屏幕永久持异常**（真机实测：杀进程重启后残留黑层依然在，见 §2-1-3） |
| **不做会怎样** | 残留视频层仍 enable 且压在 UI 之上/占位 → **黑屏**；崩溃重启场景 → **永久性黑屏/异常**（屏上没内容或只有残帧） |
| **开发要求** | 代码里必须有释放实现，且**启动初始化路径里必须要调到**（不是“应该做”而是**必做**） |
| **验收要求** | 机器：`check_all` 第 19 项（见下）；人工：真机抓图 **不够**（见 §2-1-2 陷坑）——必须看 `cat /sys/class/disp/disp/attr/sys` 层清单，必要时重启进程复验 |

**机器核验（check_all #19）**：平台 = V85X **且** src/ 出现视频解码用法（`zk_h264_player_` / `h264_player.h` / `vdecoder.h` / `CedarX` / `mi_vdec` / `VideoDecoder` / `sunxi_display2`）**但**找不到释放实现（`/dev/disp` + `DISP_LAYER_GET/SET_CONFIG` / `releaseLayer` / `hwdisplay.h`）→ **FAIL**。非 V85X 或未见解码用法 → NOTE 跳过（不误报）。

### 2-1 实现要点（可直接复用）

**背景**：boot logo / 上个程序 / 解码器退出时残留的 disp 图层不关，会造成错屏、图层叠加、黑屏。释放 = 关掉除 UI 层外的 enabled 层。

**参考实现（V85X 扩展屏 AP+P2P 工程 `src/system/hardware.cpp`）**：`sys::hw::init()` 里启动早期调 `_release_layer()`（UI 起来后的统一初始化点，调用一次即可），遍历 `ch 0..CHN_NUM-1`（跳过最后一个通道）× `layer 0..LYL_NUM-1`，逐个 `DISP_LAYER_GET_CONFIG` → `!enable` 跳过 → `enable=0` + `DISP_LAYER_SET_CONFIG`；另有 `/tmp/zk_boot_anim` 存在性做开机动画保护（动画期间不关层）—— 这个保护建议照抄。

#### ⚠️ 2-1-1 判「哪些层不能关」用 ch/layer，**不要用格式区间**（2026-09-14 V851 真机实测打破）

参考工程用的是「`DISP_FORMAT_ARGB_8888(0x00) ~ DISP_FORMAT_BGRA_5551(0x13)` 区间 = UI/OSD 层，直接 `continue`」。**真机实测证明这个判据不可靠，会漏关残留层（典型后果：一直黑屏）**：

| 造出的残留层 | format 读值 | 格式区间判据的行为 |
|------|------|------|
| BUFFER 模式 `DISP_FORMAT_RGB_888`(0x08) ch0/lyr1 | 0x08 | ❌ **误判为 UI 层 → SKIP 漏关**（0x08 落在 0x00~0x13 里） |
| COLOR 模式纯黑层（`color=0xff000000`）ch0/lyr1 | 0x00（`info.fb.format` 与 `info.color` 是 union，COLOR 层读出来就是 color 的低字节） | ❌ **误判为 UI 层 → SKIP 漏关 → 黑层永远盖在 UI 上** |

**正确口径（实测有效）**：按 **通道/层号** 跳过 UI 层 —— `if ((ch == UI_LYCHN) && (lyl == UI_LYLAY)) continue;`（V851 实测 UI 层稳定在 **ch2/lyr0**），其余 enabled 层全部 `enable=0`。
如需双保险，可再加一条**限定 mode 的**格式判断（`info.mode == LAYER_MODE_BUFFER` 时才看 `fb.format`），但**不要单独用格式区间**：它既会漏关 RGB/COLOR 残留层，也挡不住 UI 通道本身。

#### 2-1-2 真机验证记录（Zkswe_V85X_SPINOR / V851，480×800，2026-09-14）

用 `fun create --type bin` 做的测试小工具（open `/dev/disp` + GET/SET_CONFIG）逐项实测：

| 步骤 | 设备 disp 层状态 | 结论 |
|------|------|------|
| 起始 | 仅 `ch2 lyr0 z16 fmt=0x00`（UI） | 无残留时屏幕正常 |
| 造「残留视频层」（`RGB_888` z=1，在 UI 之下不可见） | `ch0 lyr1 fmt=0x08` + UI | 残留层确实可造出且不影响显示 |
| **格式区间口径 release** | `SKIP ch0 lyr1`（漏关）| ❌ **残留层仍在**，规则失效 |
| **ch/lyr 口径 release** | `CLOSE ch0 lyr1` → 只剩 UI | ✅ 正确关掉，UI 层无损 |
| 造「黑层」（COLOR 纯黑 z=17，**盖在 UI 之上**） | `ch0 lyr1 mode=1 z=17 color=0xff000000` + UI | 复现「残留层盖 UI」 |
| 格式区间口径 release（针对黑层） | `SKIP ch0 lyr1`（漏关）| ❌ 黑层留在最上面 = **屏幕一直黑** |
| ch/lyr 口径 release | `CLOSE ch0 lyr1` → 只剩 UI | ✅ 恢复 |

#### 2-1-3 崩溃重启残留实测（证明“启动首次初始化必须释放”，2026-09-14 V851）

模拟「程序崩溃时留下的系统级图层」→ 杀进程让 init 拉起（设备 `init.rc` 里 `service zkswe /bin/zkgui`）→ 再看图层：

| 步骤 | disp 层状态 |
|------|------|
| 造残留黑层（COLOR 纯黑 z=17，盖住 UI） | `ch0 lyr1 mode=1 z=17` + UI |
| `kill <zkgui pid>` → init 自动拉起新进程（新 pid） | — |
| **重启后再看** | **黑层仍在 `ch0 lyr1 z=17`**（进程换了，图层没变）|
| 跑一次释放（ch/lyr 口径） | `CLOSE ch0 lyr1` → 只剩 UI，屏幕恢复 |

**结论**：disp 图层是系统级状态，**不随进程退出/重启而清理**——所以“启动第一次初始化先释放图层”是硬要求：不释放，残留层会在每一次重启后继续盖在 UI 上 ⇒ 屏幕**永久性异常**（只有代码去释放或整机重启才能恢复）。
**副作用提示**：调试时用 `kill` 模拟崩溃需要小心——若当时有残留层，重启后的进程若没做释放，屏幕就一直黑（本次实测靠外部工具才救回来）。

**验收两条硬注意事项（真机踩出来的）**：
1. **黑屏时 `flythings_device_screenshot`（读 `/dev/fb0`）抓到的仍是正常 UI**——fb0 只是 UI/OSD 层，那个黑层在 disp 合成器上；实测黑屏期间两次抓图 `ui_visual(action="diff")` **0 差异**。⇒ **不能靠 fb0 抓图判定「黑屏」**，要看 disp 层状态（`cat /sys/class/disp/disp/attr/sys`）或人眼/摄像头。
2. 排查时先看层清单：正常态应该只有一层（UI ch2/lyr0 z16，fmt=ARGB）；多出 enable 的非 UI 层且 `z` 高于 UI ⇒ 这就是黑屏/错屏的无害。


### ⚠️ include 坑（编译必踩）
直接 `#include <video/sunxi_display2.h>` **编译报错**（`'s32' declared as function` / `'u32' does not name a type`）——该内核头用 s32/u32 但不自己定义。
**正确**：include aw-mpp 的 `<vo/hwdisplay.h>`（内部先 `typedef signed/unsigned int s32/u32` 再包含 sunxi_display2.h，顺序正确）；`disp_layer_config`/`CHN_NUM(4)`/`LYL_NUM(4)`/`UI_LYCHN(2)`/`UI_LYLAY(0)`/`DISP_DEV "/dev/disp"` 都在其中；`DISP_LAYER_GET_CONFIG=0x48`/`SET_CONFIG=0x47` 由 sunxi_display2.h 提供。
（工程若直接 include `<video/sunxi_display2.h>` 又自己在前面补 s32/u32 typedef，也能编过——但换平台容易踩，优先用 hwdisplay.h）

### 代码（可直接复用）
```cpp
#include <fcntl.h>
#include <sys/ioctl.h>
#include <string.h>
#include <errno.h>
#include <vo/hwdisplay.h>   // ⚠️ 不要直接 include <video/sunxi_display2.h>
#include "utils/Log.h"      // LOGD/LOGE

static int _layer_config(int fd, int cmd, disp_layer_config *cfg) {
  unsigned long args[4] = {0};
  args[1] = (unsigned long)cfg;
  args[2] = 1;
  return ioctl(fd, cmd, args);
}

void releaseLayer() {
  int fd = open(DISP_DEV, O_RDWR);   // "/dev/disp"
  if (fd < 0) {
    LOGE("Failed to open disp device, errno: %d\n", errno);
    return;
  }
  for (int ch = 0; ch < CHN_NUM; ++ch) {          // 4
    for (int lyl = 0; lyl < LYL_NUM; ++lyl) {     // 4
      if ((ch == UI_LYCHN) && (lyl == UI_LYLAY)) { // 跳过 UI 层 (2,0)
        continue;
      }
      disp_layer_config config;
      memset(&config, 0, sizeof(config));
      config.channel = ch;
      config.layer_id = lyl;
      _layer_config(fd, DISP_LAYER_GET_CONFIG, &config);
      if (!config.enable) continue;
      config.enable = 0;
      _layer_config(fd, DISP_LAYER_SET_CONFIG, &config);
      LOGD("[hw] close channel[%d] layer_id[%d]\n", ch, lyl);
    }
  }
  close(fd);
}
```
- **调用时机**：① **视频解码返回后（必做，见 §2-0）**：解码结束/播放器退出/返回 UI 时调一次；② 启动早期（UI 初始化回调 onUI_init 一类，UI 层建立后、开摄像头前）调一次
- 有效日志特征：`[hw] close channel[0] layer_id[1]` —— 说明真关掉了残留层
- 有开机动画的产品可加保护：动画文件存在时跳过（避免关掉动画层），如 `RETURN_IF_FAIL(!FILE_EXIST("/tmp/zk_boot_anim"))`

## 3. 无图像根因：UI 层不透明盖视频层 → videoView 透明窗口

**现象**：摄像头出流正常（logcat `rear camera fps 30`），disp 层状态视频层 enable + 有 addr，但屏幕没画面。

**根因**：UI 层在 z=16 最顶；根窗口设了不透明背景（backgroundColor 0）或 UI fb 全屏不透明 → disp 视频层被完全盖住。
- 验证：dump UI 层 fb（/dev/fb0，32bpp）头像素 alpha——`A=FF` 不透明即盖死；透出应 `A=00`
- disp sys 里 UI 层 `a[pixel 255]` + 视频层 z=1 在 UI 下 = 必然被盖

**修复**：UI 布局放一个 **videoView 控件当透明渲染窗口**（详见 `v85x/videoview-transparent-window.md`）：
- videoView **必须 `visible:true`**（⚠️ `visible:false` 是最常见坑——控件隐藏时 UI 层在该区域不透出，视频层白跑）
- videoView position = 想显示画面的区域（预览全屏就铺满全屏）
- 摄像头自维护出图（mpi 层输出到 disp）时 videoView **零关联代码**：不 play/不设源，纯透出窗口
- 预览 + 回放共用一个全屏 videoView 可行：预览时它透明透出 disp 视频层；回放时它作为播放器播文件

## 4. VO dev0 抢占冲突：播放器退出不释放 → 预览 enable 报 0xa00f8042

**现象**：独立播放页（ZKVideoView 播录像）退出后回预览页，预览启动失败无图像；logcat 反复：
```
E/dvr: [camera.cpp:136 doTask] base::Exception: 0xa00f8042 AW_MPI_VO_Enable(id_) error(0xa00f8042)
E/dvr: at enable(vo.cpp:29)
```
程序自检 rebuild（`preview disp layer missing, rebuild preview`）多次仍失败。

**错误码定位（aw-mpp `mm_comm_vo.h`）**：
| 错误码 | 枚举 | 含义 |
|--------|------|------|
| `0xa00f8042` | EN_ERR_VO_DEV_HAS_ENABLED | VO 设备已被 enable（抢占冲突，本坑） |
| `0xa00f8041` | EN_ERR_VO_DEV_NOT_ENABLE | VO 设备未 enable（常态/非错误，忽略） |
| `0xa00f8043` | EN_ERR_VO_DEV_HAS_BINDED | 已绑定 |
（前缀 `0xa00f` = AW_MPI 错误模块，低字节即 VO 错误枚举）

**架构事实**：easyui ZKVideoView（zkmedia/CedarX 播放器）与 mpi 预览（aw-dvr RearCamera）**共用 VO dev0**；播放器退出/播放页销毁后 VO dev0 **不自动释放** → mpi 预览 enable 同一 dev → HAS_ENABLED。
- ⚠️ **触发条件**：播放页是独立 Activity、走销毁路径（onUI_quit/goBack）才触发；videoview 常驻同一页面不销毁播放器实例时无此问题
- disp layer 级知识（§2 releaseLayer ch0/layer1）只到层，**VO dev 级是另一层**：disp layer enable 正常但 VO enable 失败

**解法**：mpi 预览启动前 **raw `AW_MPI_VO_Disable(0)` 强制让位**（必须拿返回码）：
```cpp
#include <mpi_vo.h>   // AW_MPI_VO_Enable/Disable raw API
int voRet = AW_MPI_VO_Disable(0);      // 播放器残留 enable dev0 → 强制 disable
if (voRet != 0) LOGD("VO_Disable(0) ret=0x%x", voRet);   // 非0=dev0 正被占/状态异常，重试
```
⚠️ **坑**：mpi::VO 包装类（mpi::VO::disable()）可能**吞异常/不返回真实码**——必须用 raw API（AW_MPI_VO_Disable）拿返回码判断，别依赖包装。
- 调用时机：`mpi::initializeSystem()` 之后、`RearCamera::setParam`（内部 enable VO）之前
- 播放器 stop 到 VO 让位是异步的（播放线程 exit 后 ~400ms）：Disable 失败 → sleep 300-500ms 重试 2-3 次
- 兜底：预览 enable 失败（HAS_ENABLED）→ Disable(0) + 延时 + 重试循环（5×300ms），接住播放器释放慢场景

**预览启动失败无图像排查顺序**（层→VO→透出）：
1. disp 层：`cat /sys/class/disp/disp/attr/sys`（层 enable？）→ releaseLayer 释放残留（§2）
2. VO dev：logcat 见 `0xa00f8042` → raw `AW_MPI_VO_Disable(0)` 让位（本节）
3. UI 透出：videoView 是否 visible（§3）

参考：`v85x-mpp.md` MPP 互斥铁律（预览/录像/回放切页前停干净对端；回放 50ms 延迟 init VO 防抢占——本坑是反向：**回放退出→预览**）。

## 5. 屏幕旋转配置（rotateScreen = 硬件方向适配，值由屏幕安装方向决定）

**错屏机制**：UI 逻辑分辨率（1600×600 横）与物理屏方向（600×1600 竖装）不匹配时，不旋转则 UI 宽 1600 > 物理宽 600，布局/视频内容溢出到屏幕外 = 错屏/花屏。rotateScreen 让 UI 旋转后完整落在屏内——**取值跟随硬件物理安装方向**（同代码双屏工程：横装屏不写/0、竖装屏转 270），与 UI 分辨率无关、与代码无关，只改 package.properties 覆盖层即可生效。

- 工程根 `package.properties` 写：`EasyUI.cfg={"rotateScreen": 270}`
- **触摸不旋转 = 只写 rotateScreen，不写 rotateTouch**（rotateTouch 保持默认 0）——某些硬件"屏幕转、触摸不转"（见 `devflow/package-properties-easyui-cfg.md`）
- ⚠️ 改 package.properties 后 `fun build` 会 `ninja: no work to do`——**必须 `fun clean` 全量重编**
- EasyUI.cfg 由 **fun launch** 本地准备阶段合并生成（`.fun/<平台>/launch/EasyUI.cfg`），launch 时随部署推送；设备端 `/tmp/EasyUI.cfg` 可 cat 验证 `rotateScreen: 270 / rotateTouch: 0`
- 生效后 disp sys 的 UI 层 crop 应从异常（如 `[0,1600,...]`）恢复为 `[0,0,600,1600]` 全屏正常值

## 6. 回放旋转：ZKVideoView rotation 是枚举不是角度！

```cpp
// easyui 头文件 ZKVideoView.h 权威注释：
/* clockwise rotation: val=0 no rotation, val=1 90 degree; val=2 180 degree, val=3 270 degree */
void setRotation(int val);
```
- json 布局里 videoview `"rotation": 3` = 顺时针旋转 270°（与 rotateScreen 270 的竖屏 UI 匹配）
- ⚠️ **写成 `"rotation": 270` 是无效值，会被忽略、毫无效果**（0~3 以外的值不识别）
- 回放 mp4 横视频（1280×720）在竖屏 UI 上播，rotation=3 后与预览方向一致
- 若改了 rotation 仍不对：检查是否复用 videoView 的预览透出区域被 rotation 影响，或参考同平台产品回放页（mpi::VO 初始化时序：播放前 stop 预览链路 + 延迟 50ms 初始化 VO 避免 MPP 冲突——详见 `v85x-mpp.md`）

## 7. 设备侧调试技巧（无 screencap/input 的精简系统）

- **抓屏**：设备常无 `screencap`；可用 fb dump 分析：`busybox dd if=/dev/fb0 bs=<行字节> count=1` 拉头部 → 解析像素（32bpp BGRA，看 alpha 判 UI 层透明与否）
- **触摸注入**：设备常无 `input` 命令；用交叉工具链静态编译小工具（`-static`，open /dev/input/eventX 写 EV_ABS/EV_KEY/EV_SYN 序列）即可 tap；⚠️ 触摸设备节点要查 `/proc/bus/input/devices`（gt9xx 触摸可能是 **event0**，EasyUI.cfg 写的 touchDev 可能不准）
- **坐标映射**：旋转屏注入 tap 前先小样本试探（注入后看 logcat 按钮回调日志反推命中）
- 网络 adb：`adb connect <设备IP>:5555`；电脑与设备需同网段

## 8. 参考
- `v85x/videoview-transparent-window.md`（videoView 透出机制权威口径）
- `v85x-mpp.md`（mpi:: 摄像头/回放 API、MPP 冲突时序）
- `devflow/package-properties-easyui-cfg.md`（package.properties / EasyUI.cfg 机制、rotateScreen 定规）
