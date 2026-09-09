# 🖥️ V85X 显示分层调试：releaseLayer 图层释放 / UI 透出 / 回放旋转

> 2026-09-09 实战沉淀（来源：V85X 竖屏 600×1600 + 1600×600 横 UI 工程，UVC 摄像头预览/回放调试）。
> 适用：**V85X（V853/V553 等）**——竖装屏 + 横 UI + MPP 摄像头（aw-dvr/mpi::）场景。
> ⚠️ 仅 V85X 平台生效（disp 分层机制是 V85X 特有）；T113/F133/Z20 按各自链路处理。

## 0. 一句话

V85X 竖屏工程调试「错屏 / 无图像 / 回放方向不对」四板斧，按顺序查：
1. **屏幕旋转（硬件方向适配）**：**错屏根因 = UI 布局尺寸超出物理屏**——横 UI（1600×600）用在竖装屏（600×1600）上，不旋转时 UI 宽 1600 超过物理宽 600，界面/视频内容画到屏幕外 = 错屏。rotateScreen 是**针对硬件物理安装方向的适配**（值由屏幕怎么装决定，不是 UI 分辨率决定），把 UI 旋转 270° 后完整映射进屏内 → `package.properties` 配 `EasyUI.cfg={"rotateScreen": 270}`（触摸不转=不写 rotateTouch）→ **必须 clean 全量重编**（ninja 不感知 package.properties 改动），EasyUI.cfg 由 fun launch 阶段合并生成
2. **图层释放**：启动早期调 `releaseLayer()` 关掉残留 disp 层（保留 UI 层），防残留层叠加干扰画面
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

**背景**：boot logo / 上个程序残留的 disp 图层不关，会造成错屏、图层叠加、视频被无关层干扰。启动早期关掉除 UI 层（ch2/layer0）外所有 enabled 层。

### ⚠️ include 坑（编译必踩）
直接 `#include <video/sunxi_display2.h>` **编译报错**（`'s32' declared as function` / `'u32' does not name a type`）——该内核头用 s32/u32 但不自己定义。
**正确**：include aw-mpp 的 `<vo/hwdisplay.h>`（内部先 `typedef signed/unsigned int s32/u32` 再包含 sunxi_display2.h，顺序正确）；`disp_layer_config`/`CHN_NUM(4)`/`LYL_NUM(4)`/`UI_LYCHN(2)`/`UI_LYLAY(0)`/`DISP_DEV "/dev/disp"` 都在其中；`DISP_LAYER_GET_CONFIG=0x48`/`SET_CONFIG=0x47` 由 sunxi_display2.h 提供。

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
- **调用时机**：UI 初始化回调（onUI_init 一类）开头，UI 层建立后、开摄像头前调一次
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

## 4. 屏幕旋转配置（rotateScreen = 硬件方向适配，值由屏幕安装方向决定）

**错屏机制**：UI 逻辑分辨率（1600×600 横）与物理屏方向（600×1600 竖装）不匹配时，不旋转则 UI 宽 1600 > 物理宽 600，布局/视频内容溢出到屏幕外 = 错屏/花屏。rotateScreen 让 UI 旋转后完整落在屏内——**取值跟随硬件物理安装方向**（同代码双屏工程：横装屏不写/0、竖装屏转 270），与 UI 分辨率无关、与代码无关，只改 package.properties 覆盖层即可生效。

- 工程根 `package.properties` 写：`EasyUI.cfg={"rotateScreen": 270}`
- **触摸不旋转 = 只写 rotateScreen，不写 rotateTouch**（rotateTouch 保持默认 0）——某些硬件"屏幕转、触摸不转"（见 `devflow/package-properties-easyui-cfg.md`）
- ⚠️ 改 package.properties 后 `fun build` 会 `ninja: no work to do`——**必须 `fun clean` 全量重编**
- EasyUI.cfg 由 **fun launch** 本地准备阶段合并生成（`.fun/<平台>/launch/EasyUI.cfg`），launch 时随部署推送；设备端 `/tmp/EasyUI.cfg` 可 cat 验证 `rotateScreen: 270 / rotateTouch: 0`
- 生效后 disp sys 的 UI 层 crop 应从异常（如 `[0,1600,...]`）恢复为 `[0,0,600,1600]` 全屏正常值

## 5. 回放旋转：ZKVideoView rotation 是枚举不是角度！

```cpp
// easyui 头文件 ZKVideoView.h 权威注释：
/* clockwise rotation: val=0 no rotation, val=1 90 degree; val=2 180 degree, val=3 270 degree */
void setRotation(int val);
```
- json 布局里 videoview `"rotation": 3` = 顺时针旋转 270°（与 rotateScreen 270 的竖屏 UI 匹配）
- ⚠️ **写成 `"rotation": 270` 是无效值，会被忽略、毫无效果**（0~3 以外的值不识别）
- 回放 mp4 横视频（1280×720）在竖屏 UI 上播，rotation=3 后与预览方向一致
- 若改了 rotation 仍不对：检查是否复用 videoView 的预览透出区域被 rotation 影响，或参考同平台产品回放页（mpi::VO 初始化时序：播放前 stop 预览链路 + 延迟 50ms 初始化 VO 避免 MPP 冲突——详见 `v85x-mpp.md`）

## 6. 设备侧调试技巧（无 screencap/input 的精简系统）

- **抓屏**：设备常无 `screencap`；可用 fb dump 分析：`busybox dd if=/dev/fb0 bs=<行字节> count=1` 拉头部 → 解析像素（32bpp BGRA，看 alpha 判 UI 层透明与否）
- **触摸注入**：设备常无 `input` 命令；用交叉工具链静态编译小工具（`-static`，open /dev/input/eventX 写 EV_ABS/EV_KEY/EV_SYN 序列）即可 tap；⚠️ 触摸设备节点要查 `/proc/bus/input/devices`（gt9xx 触摸可能是 **event0**，EasyUI.cfg 写的 touchDev 可能不准）
- **坐标映射**：旋转屏注入 tap 前先小样本试探（注入后看 logcat 按钮回调日志反推命中）
- 网络 adb：`adb connect <设备IP>:5555`；电脑与设备需同网段

## 7. 参考
- `v85x/videoview-transparent-window.md`（videoView 透出机制权威口径）
- `v85x-mpp.md`（mpi:: 摄像头/回放 API、MPP 冲突时序）
- `devflow/package-properties-easyui-cfg.md`（package.properties / EasyUI.cfg 机制、rotateScreen 定规）
