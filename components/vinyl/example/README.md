# example —— `zk::VinylSpin` 标准示例

> 2026-09-22 钟工「直接补上，不需要单独验证，纯粹标准化的代码」→ 本目录补成**可直接拷用的标准示例**。

```
example/
  demo/
    ui/vinyl_demo.json            一页 demo：320x320 正方形占位控件 + 3 个按钮 + 诊断行（1024x600）
    src/vinyl_demoLogic.cc        对应 logic：attach/setCover/tick/setPlaying/detach + 3 个按钮回调
  README.md                       本文件（怎么拷、怎么编、看什么）
```

## 1) 拷进任意工程（两步）

```bash
# ① 组件源码（一次拷好，之后各页面共用）
mkdir -p <工程>/src/zk_vinyl
cp components/vinyl/include/zk/zk_vinyl.h <工程>/src/zk_vinyl/
cp components/vinyl/src/*              <工程>/src/zk_vinyl/

# ② demo 页（想验证组件时用；正式页面按下面"接入三步"自己写）
cp components/vinyl/example/demo/ui/vinyl_demo.json    <工程>/ui/
cp components/vinyl/example/demo/src/vinyl_demoLogic.cc <工程>/src/logic/
```

编译（json → ftu 由工程侧负责；改了 json 记得重出 ftu）：

```bash
<工程>/ui/fui.exe pack <工程>/ui        # json -> ftu
fun build -p <平台>                      # 例：-p F133 / -p Z36
```

> 说明：demo 里的封面路径是 `images/album_a.png` / `images/album_b.png`（相对工程 `resources/`），
> 换成你自己的图即可。要用 nanovg 后端就在 Manifest 里加 `<package id="nanovg" version="1.0.0"></package>`。

## 2) 正式页面「接入三步」（demo 里就是这三步）

```cpp
#include "zk_vinyl/zk_vinyl.h"

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = { {0, 83} };   /* 12fps 驱动 */

static void onUI_init() {
    zk::VinylSpin::instance().attach(mCoverArtPtr);                     /* ① 挂到正方形占位控件 */
    zk::VinylSpin::instance().setCover(CONFIGMANAGER->getResFilePath("images/album.png").c_str());
}
static bool onUI_Timer(int id) { zk::VinylSpin::instance().tick(); return true; }   /* ② 每拍驱动 */
static void onUI_quit() { zk::VinylSpin::instance().detach(); }                     /* ③ 摘下 */
/* 播放/暂停联动：zk::VinylSpin::instance().setPlaying(playing); */
```

## 3) demo 页上看到什么 / 怎么判

- 圆盘每帧自转（默认 12fps），暂停按钮停转、再按从当前角度继续；
- 「切后端」在 定点 / nanovg 之间现场切换（返回实际生效值；nanovg 建不起来会保持定点，只打 warning）；
- 「换封面」换图并把角度回到 0；
- 诊断行每秒刷新：`黑胶 播放中 | nanovg 128度 3500帧 11.8fps | 旋转 26ms 上屏 1ms`。

## 4) 真机载体（本组件的实际验证）

组件的真编译 + 真机运行载体是 `projects/iOSStyle-F133`（播放页黑胶已切到组件副本
`projects/iOSStyle-F133/src/zk_vinyl/`）：`fun build -p F133` → 0 error，部署后正常出帧。
本 demo 页与它用的是同一套接口，只是把参数换成最简三个按钮，便于新工程直接照抄。
