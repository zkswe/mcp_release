# zk::VinylSpin —— 黑胶唱片自转（封面按角度旋转上屏）组件

> 2026-09-22 入库（现场反馈：「多产品会复用这个功能，我需要把他做成可以复用的功能点」）。
> 落地来源：`projects/iOSStyle-F133`（CloudMusic 音乐播放页「黑胶唱片」黑胶自转），
> 抽出后工程已切到本组件副本（`projects/iOSStyle-F133/src/zk_vinyl/`）**真编译 + 真机跑通**。

## 0. 它解决什么

平台上**没有**任意角度旋转的现成能力（`ZKPainter` 不能画位图、`misc::bitmap_rotate` 只支持 90° 整数倍、
`ZKImageAnim` 只吃 GIF/WebP 文件）。本组件自己逐帧把封面**旋转**画进一张 BGRA 内存位图，
再交给任意控件当背景图显示 —— 不落盘、不进 GL，进度由墙钟决定（丢帧不漂移）。

典型用：音乐/播客播放页的旋转唱片（黑胶）、指示盘/表盘动画、任何"按角度转的圆形图"。

## 1. 对外 API（`include/zk/zk_vinyl.h`，`namespace zk`）

```cpp
#include <zk/zk_vinyl.h>

zk::VinylSpin &vs = zk::VinylSpin::instance();   // 单页单实例用这个；要多个实例可自己 new VinylSpin()

bool attach(ZKBase *host);        // 挂到宿主控件（UI 线程）：控件须正方形，边长取自 position
void detach();                    // 摘下（onUI_quit）；不释放已交给框架的位图
void setCover(const char *pngPath);  // 换封面（后台线程解码+缩放），角度回 0
void setPlaying(bool playing);    // 播放/暂停联动（暂停即停转）
void tick();                      // 每拍驱动（UI 线程定时器里调，建议 40~83ms = 25~12fps）
int  setBackend(int want);        // 运行期切后端：0 = 定点标量 / 1 = nanovg(AGG)；返回实际生效值

int  backend() const;             // 实际后端
int  angleDeg() const; int frames() const; int fpsX10() const;
int  lastRotMs() const; int lastPubMs() const; int mode() const;   // 诊断读数
```

## 2. 三步接入（页面侧）

```cpp
// 1) json 里放一个**正方形**控件占位（例：320x320 的 textview，别给它配图）
// 2) onUI_init：挂上 + 换封面
zk::VinylSpin::instance().attach(mCoverArtPtr);
zk::VinylSpin::instance().setCover(coverPngPath);
// 3) 定时器表里加一拍驱动它（12fps 够用；数值越小越费）
static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 83},
};
static bool onUI_Timer(int id) {
    zk::VinylSpin::instance().tick();
    // 播放/暂停联动：zk::VinylSpin::instance().setPlaying(playing);
    return true;
}
// onUI_quit：zk::VinylSpin::instance().detach();
```

## 3. 依赖

| 依赖 | 必需 | 说明 |
|---|---|---|
| `easyui` | ✅ | `ZKBase` / `setBackgroundBmp` / `bitmap_t`；`misc::image_load`、`misc::bitmap_scale` |
| `log` | ✅ | `LOGD/LOGW` 诊断 |
| `nanovg 1.0.0` | ⭕ 可选 | 只用 `backend=1`（nanovg/AGG）时；**只支持 BGRA 目标**，见 §5 坑 4 |
| `base-utility` | ⭕ | 仅当工程本身需要（与平台模板一致） |

**无浮点**（定点后端纯整数 Q16；`zk_vinyl_circle_mask` 也是纯整数 SS=8 面积平均）→ 符合 MCU/低端平台的口径。

## 4. 文件

```
include/zk/zk_vinyl.h          # 对外头（页面只 include 这个）
src/zk_vinyl.cpp               # 旋转本体（双后端 + 双缓冲握手 + 上屏 + 诊断）
src/zk_vinyl_worker.{h,cpp}    # 自包含后台单线程任务队列（解码/旋转都在它上面跑）
src/zk_vinyl_circle_mask.{h,cpp}  # 正圆覆盖率表（SS=8 面积平均，与静态圆封面同源口径）
```

## 5. 已知坑（都是真机踩出来的，照做即可）

1. **刷新口径**：位图只 `setBackgroundBmp` 交一次，之后每帧 `host->setInvalid(!host->isInvalid())` 翻转刷新
   （gameview 口径）。**别**用 `invalidate(&getAbsolutePosition())` 传绝对矩形 —— rect 是**控件本地坐标系**，
会被裁成"右下角一块"，屏上只刷一块（现象：部分区域 12fps、其余 ~1fps）。
2. **宿主控件必须正方形**（`attach` 会拒绝非方控件）；控件**别在 json 里配图**（首帧算好前显示占位图，之后换成我们的位图）。
3. **位图所有权**：交给框架后归框架；每帧改为"原地改像素 + 翻转 invalid"（零分配），不要每帧新建 bitmap。
4. **nanovg 后端只支持 `NVG_TEXTURE_BGRA` 目标**，且纹理格式必须与目标一致；`nvgCreateImageRGBA` 会断言；
源数据按 BGRA 直传（不用换通道）。上下文建不起来会**自动回退定点**并只 warning。
5. **后端取舍**：定点 ~6~12ms/帧（边缘过渡 ~1.5px，60fps 上限高）；nanovg 更顺滑（过渡 ~1.0px）但 ~23ms/帧（320×320）。
实测：`NEAREST` 采样 / 去 memset / pattern-angle 都**省不下来**，只有**降分辨率**（160×160 ≈ 5.4ms）或**降帧率**有效。
6. **listview 的 item/subItem 挂不了自定义控件**→ 列表里的圆封面只能"先合成 PNG 再 setBackgroundPic"。
7. **改 json 别用 `sort_keys=True` 整体重排**（控件顺序 = 图层顺序，会把全屏铺底层排到控件之上）。
8. 调试开关（默认关，正式路径不受影响）：`/tmp/vinyl_dump`（逐帧 dump rot/pub/src）、
   `/tmp/vinyl_inv`（刷新口径 0/1/2）、`/tmp/vinyl_step`（静态 +N 度并强制重画一帧）、
   `/tmp/vinyl_testpat`+`/tmp/vinyl_marker`+`/tmp/vinyl_nomask`（合成测试图/方块标记/不裁圆）。

## 6. 验收口径（可复用）

- **功能**：暂停 + `/tmp/vinyl_step` 静态走 20°，采样点位移应 ≈ `2·r·sin(10°)`（r=100 → 34.7px）；
- **质量**：nanovg vs 定点同角度 A/B 圆内 `mean|Δ| ≤ 2/255`；圆边过渡带 nanovg ≤ 1.2px / 定点 ≤ 2.5px；
- **性能**：`lastRotMs()`（每帧旋转耗时）+ `cpu.py` 口径的 zkgui CPU。

## 7. 版本与出处

| 项 | 内容 |
|---|---|
| 版本 | 1.0（2026-09-22 从 iOSStyle-F133 抽取首版） |
| 落地来源 | `projects/iOSStyle-F133`（播放页黑胶；定点 + nanovg 双后端） |
| 抽取脚本 | `temp/mu_vinyl/make_vinyl_component.py`（从工程源码生成组件包，便于后续同步） |
| 平台实测 | 见 `platforms.md`（当前 f133 已实测；其余平台待补） |
| 真机证据 | `temp/mu_vinyl/shots/component_ok.png`、`_fix_compare.png`（刷新口径对照） |
