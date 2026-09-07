# 🎞️ 帧动画控件 ImageAnimView / FrameImageView（ZKBIN+QOI+region 脏矩形机制）

> 2026-09-07 沛哥安排：学习整车代码后提炼入库（来源：`DashBoard_T113/BMW/jni/ui/ImageAnimView.{h,cpp}` 实测 + `lib-ext_widgets/src/ui/FrameImageView.{h,cpp}` 通用版，ZKSWE Develop Team）。
> 这是**自研帧动画控件**（代码级，不进 ftu/IDE），用于宝马仪表指针（车速/转速表盘每角度一帧预渲染图）。
> ⚠️ **与 IDE 自带 imageanim 动图控件（GIF/WebP）完全不是一回事**——官方控件见 `uicontrols/imageanim-fields.md`，本文是自研 bin 帧序列控件，禁止混用。

## 0. 一句话原理

**把一组长序列帧图预编码成"ZKBIN（zlib 压缩 QOI 图）+ region.bin（相邻帧差异区域表）"资源目录 → 控件 load(dir) 建整幅画布 → play(index) 在后台线程解码指定帧 → 只把"旧帧→新帧"经过的差异区域并集拷贝到画布并局部 invalidate → 极省带宽/刷新开销，指针仪表丝滑。**

## 1. 帧资源二进制格式（美工/工具侧预生成，两个魔数头）

### ① 单帧文件 `N.bin`（0.bin、1.bin…）：魔数 `ZKBIN`

```
字节0-7   magic "ZKBIN\0\0\0\0"
字节8-11  uncompr_size（解压后大小，小端）
之后      zlib 压缩流（inflate）→ 解出 QOI 图像数据
```

### ② 区域表 `region.bin`：魔数 `ZKREG`

```
字节0-7   magic "ZKREG\0\0\0"
字节8-9   w（表盘宽）
字节10-11 h（表盘高）
字节12-13 count（相邻帧差异区域条数）
字节14-15 reserve
之后      count 个 region_t{left,top,right,bottom}(uint16 ×4)，每条 = 第 i 帧→第 i+1 帧的变化区域
```

### ③ QOI 图像格式（开源快速无损格式，解码器内嵌控件里）

- 头 14 字节：magic `qoif` + w/h + channels(3/4) + colorspace
- 像素流操作码：INDEX/DIFf/LUMA/RUN/RGB/RGBA（8 字节收尾 padding）
- 特点：**解码极快**（比 PNG 快数倍）、无 Huffman，适合嵌入式逐帧解
- 压缩链路：**PNG→QOI→zlib**（两个魔数头之间塞 zlib 二次压缩，帧文件可再小几倍）

## 2. 控件实现要点（ImageAnimView.cpp 拆解）

```cpp
class ImageAnimView : public ZKBase, public Thread {
    bool load(const std::string &dir);   // 读 region.bin → 建 canvas_bmp_(整幅位图) → setBackgroundBmp
    void play(int index, bool sync=false); // 异步：投消息 E_MSG_PLAY；sync：直接解码
    void procPlay(int index);            // 工作线程里解码 N.bin → 合并脏区 → invalidate 局部
    void onDraw(ZKCanvas*);              // 把 img_bmp_ 的脏区行拷贝到 canvas_bmp_（按行 memcpy）
};
```

关键点：
- **canvas 双缓冲**：`_load_bmp(w,h,uuid)` 先写一个临时 24bit BMP 文件头到 /tmp → `BitmapHelper::loadBitmapFromFile` 加载成控件背景位图（`setBackgroundBmp`）→ 之后每帧只改这块位图 data + 局部 invalidate。控件销毁时位图由控件内部销毁
- **脏区合并**：首帧全幅；之后取 `[min(oldIdx,newIdx), max)` 之间所有 region 并集 → `LayoutPosition pos(脏区)` → `invalidate(&pos)` 只重绘变化矩形（BMW 版 `#if 1` 分支；另存整幅 setInvalid 交替的旧写法可忽略）
- **相同帧短路**：`play_index_ == index` 直接 return（指针没动不重绘）
- **异步队列**：内部 MessageQueue 线程（E_MSG_PLAY/E_MSG_EXIT），解码不在 UI 线程；析构投 EXIT + requestExitAndWait
- 解码函数都是静态工具：`_decode_bin`（zlib inflate + `_qoi_decode`）、`_decode_region_bin`（region 列表）

### 通用版 FrameImageView（lib-ext_widgets，2025-11 更新）

与 BMW 版同源（BaseView 子类 + MessageQueueThread），差异：
- `load` 里 `misc::bitmap_create(img_bmp_, w, h, 4)` 建 32bit 解码缓冲
- 增加 `frame_count_ = head.count + 1`、`getFrameCount()`；`play` 校验 `index < frame_count_`
- 写进 lib-ext_widgets 库后随库分发（控件库用法 → `devflow/custom-widget.md` §2 路线 B + §9 速览）

## 3. 用法（指针表盘：帧号即角度）

```cpp
// xxxLogic.cc（ftu 里放 ZKWindow 占位容器，如 mWindowspeedPtr / mWindowrpmPtr）
#include "ui/ImageAnimView.h"
static ui::ImageAnimView *_s_test1;                 // 车速指针

static void onUI_init() {
    _s_test1 = new ui::ImageAnimView(mWindowspeedPtr, TEST1_ID, {0, 0, 678, 621});
    _s_test1->load(CONFIGMANAGER->getResFilePath("mode1/speed/speed/speed_bin"));
}
static void onUI_quit() { delete _s_test1; }
```

- **资源目录**放 `resources/` 下，路径用 `CONFIGMANAGER->getResFilePath()` 取（资源打包路径随工程走）
- **播放**：`_s_test1->play(角度)`——BMW 帧目录一帧 = 指针一个角度位，角度换算：
  - `speed: 帧号 = 车速 + 30`（30 = 表底零位角度，0xFFFF 无效值回 30）
  - `rpm: 帧号 = rpm×2 + 30`（量程缩放系数按表盘刻度）
- **平滑逼近（宝马主逻辑 MyThread）**：CAN 值变化不直接跳帧，而是专用动画线程按目标角度逐级逼近——差值大走大步（+3/+4）、接近走小步（+1），`usleep(10~40ms)` 控节奏；转速/车速各自独立步进，到目标即停（play 相同帧自动短路）
- **开机扫针动画**：`START1_ANIMATION_TIMER`(10ms) 从 0 帧每 tick +2 播到 30 → 停启动动画、`my_thread.run()` 接 CAN 实时值（模式：先播固定扫针仪式感动画 → 再切实时）

```cpp
case START1_ANIMATION_TIMER: {
    _s_test1->play(Anim_SPEED_RPM_index);
    if (Anim_SPEED_RPM_index == 30) {           // 扫针到零位完成
        mActivityPtr->registerUserTimer(SPEED_RPM_TIMER, 500);
        my_thread.run();                        // 实时指针线程接管
        return false;                           // 停掉启动定时器
    }
    Anim_SPEED_RPM_index += 2;
}
```

## 4. 适用场景与选型

| 场景 | 方案 | 说明 |
|------|------|------|
| 指针仪表（预渲染多角度图，光效/渐变复杂、追求视觉） | **ImageAnimView/FrameImageView（本文）** | 帧文件极小（QOI+zlib），局部刷新，解码异步不卡 UI |
| 播放 GIF/WebP 动图文件 | 官方 imageanim 控件 | 见 `uicontrols/imageanim-fields.md` |
| 简单指针旋转（标准控件能力够用） | ZKPointer/dashbroad `setTargetAngle` | Jeep/Pointer 工程在用，省资源制作 |
| 数值型仪表（条/灯/圆弧进度） | CircleBar + 刻度控件点亮 | Comaro 工程在用（9 段转速灯/7 段车速灯） |
| 进场/淡入/位移类过渡动画 | TweenCpp 缓动 + 定时器步进 | Comaro/Jeep 通用（utils/TweenCpp.*）|

**做仪表类项目优先问客户要哪种指针风格**：预渲染图片帧（要帧图素材/表盘设计）还是代码旋转指针；前者效果好但素材量大，后者开发快。

## 5. 坑位清单

1. **region.bin 必须与帧文件配套**：缺 region.bin 或 count 不符 → load 失败或脏区错乱（首帧全幅、后续局部）
2. **帧号边界**：`play(index)` index ∈ [0, count]（count 条 region 对应 count+1 个帧位）；越界 LOG 后忽略
3. **帧尺寸必须一致**：每帧 QOI 的 w/h 必须等于 region.bin 的 w/h（解码校验 `desc.width != bmp.width` 直接 false）
4. **canvas 位图随控件销毁**：注释明确"不需要销毁 bmp，由控件内部销毁"——**外部不要 unloadBitmap(canvas_bmp_)**
5. 页面切走（onUI_hide/quit）记得 `delete` 控件 + 退动画线程，避免跨页面残留刷新
6. 资源目录路径要过 `CONFIGMANAGER->getResFilePath()`，不能写死绝对路径（debug/release 打包路径不同）
7. 帧图素材量大时注意 APK/资源包体积；QOI+zlib 已是压缩态，不要再额外打包压缩

## 6. 参考文件

- `DashBoard_T113/BMW/jni/ui/ImageAnimView.{h,cpp}`（宝马内嵌版，2024-08）
- `lib-ext_widgets/src/ui/FrameImageView.{h,cpp}`（通用版，2025-11，含 getFrameCount）
- 帧资源目录实测：`BMW/resources/mode1/RPM/rpm_bin/`（0.bin…169.bin + region.bin，region count 0xAA=170）
- 调用示例：`BMW/jni/logic/mainLogic.cc`（车速/转速 ImageAnimView + MyThread 逼近 + 开机扫针）
- CAN 仪表整体架构 → `t113-car/dashboard-can-arch.md`
