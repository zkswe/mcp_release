# example —— 最小接入示例（zk::VinylSpin）

> 本模块的**真编译 + 真机**验证载体就是 `projects/iOSStyle-F133`：
> 它的播放页黑胶已切到本组件的副本（`projects/iOSStyle-F133/src/zk_vinyl/`），
> 编译命令与结果：`fun build -p F133` → `[23/23] Linking CXX shared library libzkgui.so`（0 error），
> 部署后真机日志见 README §7「真机证据」。

## 1) json：放一个**正方形**占位控件（别配图）

```json
"textview__6": {
  "alignment": 36, "caption": "CoverArt", "fontSize": 16, "id": 50004,
  "position": { "height": 320, "left": 100, "top": 166, "width": 320 },
  "touchable": false, "text": ""
}
```

## 2) 页面 logic：三步接入

```cpp
#include "zk_vinyl/zk_vinyl.h"

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 83},        /* 12fps 驱动黑胶自转（重活在组件后台队列上跑） */
};

static void onUI_init() {
    if (mCoverArtPtr != NULL && !zk::VinylSpin::instance().attach(mCoverArtPtr)) {
        LOGW("vinyl: 挂载失败，封面保持占位图");
    }
    zk::VinylSpin::instance().setCover("/res/ui/images/album.png");  /* 换封面，角度回 0 */
}

static bool onUI_Timer(int id) {
    zk::VinylSpin::instance().tick();
    return true;
}

static void onUI_quit() {
    zk::VinylSpin::instance().detach();     /* 停转 + 释放我方缓冲（位图归框架） */
}

/* 播放/暂停联动（例：播放器状态变化处调一次） */
static void syncSpin(bool playing) {
    zk::VinylSpin::instance().setPlaying(playing);   /* 暂停即停转，恢复从当前角度继续 */
}

/* 想现场对比两个内置后端（定点 / nanovg）用这个（真机对照用，正式版可删）： */
static bool onButtonClick_BtnBackend(ZKButton *pButton) {
    zk::VinylSpin &vs = zk::VinylSpin::instance();
    vs.setBackend(vs.backend() == 1 ? 0 : 1);        /* 返回实际生效值（nanovg 建不起来会保持定点） */
    return false;
}
```

## 3) 编译（把组件拷进工程后）

```bash
cp -r components/vinyl/include/zk/*.h  <工程>/src/zk_vinyl/
cp    components/vinyl/src/*.{h,cpp}   <工程>/src/zk_vinyl/
# 工程里把 include 写成 "zk_vinyl/zk_vinyl.h"（本示例约定）
fun build -p F133
```

## 4) 自检要点

- 日志里应每秒出现一条 `vinyl: 刷新 mode=0…控件pos=(…320x320)`，且 `上屏第 N 帧(旋转 Xms … fps=Y)` 的 N 在涨；
- 暂停后角度停住；换封面（`setCover`）后角度回 0；
- 页面退出（`onUI_quit`）后 `detach()`，不残留后台任务。
