# imagecache / example —— 最小示例（PC 自测 + 工程接线）

本目录两份东西，**一份能在 PC 上真编真跑，一份是拷进工程用的接线样板**：

| 文件 | 能不能编 | 作用 |
|---|---|---|
| `zk_imagecache_test.cpp` | ✅ **PC 可编可跑**（不需要真机 / 不需要 easyui） | 组件语义自测 29 项：命中不重解 / 权重 LRU / 引用计数 / **串图复现** / 错误不静默 / 解码次数对比 |
| `flythings_wiring.cc` | ❌ 只能在工程里编（依赖 easyui 的 `utils/BitmapHelper.h` 与 `log`） | FlyThings 接线：三个回调（load/free/log）+ `configure()` + `acquire/release` + fill 里那一句 |

## 1. 跑 PC 自测（就是本组件的「真编过」证据）

```bash
cd components/imagecache
mkdir -p _t && cd _t
g++ -std=c++11 -O2 -Wall -Wextra -I../include ../example/zk_imagecache_test.cpp ../src/zk_imagecache.cpp -o zk_imagecache_test
./zk_imagecache_test            # 退出码 0 = 全 PASS；加 -v 逐次打印 load/free
```

实测（llvm-mingw g++ 与 Linux g++ 各跑一次，均 **29 项 0 FAIL**）：

```
-- 3) 回页重设同一批封面（核心场景）
[PASS] 3.1 解码次数 8 -> +0（命中，不再解码） loads=8
-- 6) ⚠️ 固定名换内容 = 命中旧图（串图）——所以路径必须带批次/版本
[PASS] 6.1 同路径不再解码（缓存里还是 SEARCH-1ST -> 这就是串图的根因）
[PASS] 6.2 路径带批号后重新解码（新图能上屏）
-- 8) 无缓存 vs 有缓存（8 张封面 × 20 轮回页重设；硬证据 = 解码次数）
        | 无缓存(releaseAll 每轮) | 160 | 4.028 ms |
        | 有缓存(ImageCache)      | 8   | 0.194 ms |
=== 合计 29 项，FAIL 0 ===
```

> PC 上的 ms 只是**相对值**（PC 读写是 µs 级）；硬证据是**解码次数**。
> 真机口径（F133，280×280 封面 26~65 ms/张）：回页重设同一批 **315 ms → 1 ms**，见 `../platforms.md`。

## 2. 拷进 FlyThings 工程（三步）

```cpp
// ① src/logic/xxxLogic.cc
#include "zk/zk_imagecache.h"      // 组件头（拷到 src/zk/zk_imagecache.h）
#include "flythings_wiring.cc"     // 或把三个回调抄进自己的文件（见该文件注释）
// onUI_init：zkImageCacheSetup();  zk::ImageCache::instance().acquire();
// onUI_quit：zk::ImageCache::instance().release();

// ② 列表 fill：setBackgroundPic 之后紧跟一句
subCover->setBackgroundPic(path.c_str());
zk::ImageCache::instance().cache(path.c_str());
```

工程 `Manifest.xml` 需要 `easyui`（BitmapHelper）+ `log`（日志）——版本见 `../Manifest.xml`。

## 3. ⚠️ 拷进去之前先确认这三件事

1. **路径唯一**：固定名封面（`cover_0.png` 这类换内容不换名）会命中成旧图 →
   必须改成带批次/版本（`cover_<批号>_<序号>.png`），开新一批时删上一批文件。见自测第 6 组。
2. **只接有封面的列表**：没封面的行**别调** `cache()`（空路径会被计入 `fails()` 并 warning）。
3. **容量要算账**：`capacity × 单图解码体积` 就是峰值占用；Z20/Z21 那类 36~128 MB 内存板别照抄 128。
