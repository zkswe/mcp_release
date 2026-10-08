# v85x-device/ —— nanovg 1.0.0 · V85X 真机证据（2026-10-03）

> 这一份**补上**了 `../../platforms.md §1.3` 要求的"才算可用"三条：
> ①真机跑通一帧并抓屏 ②与离屏出图逐像素比对 ③每帧耗时与 `VmRSS`。
> 设备：USB `20080411` = `Zkswe_V85X_SPINOR`（480×800，easyui 2.4.0）。
> 被测件：`../../lib/v85x/libnanovg.so`（`md5 F5F1157D50AB4A882B464D33804E5B1B`，
> 与设备 `/lib/libnanovg.so` **md5 完全相同** —— 入库那份就是设备本尊）。

---

## 0. 结论（先看这个）

| 项 | 结果 |
|---|---|
| 库能否在 V85X（ARMv7 musl）加载并运行 | ✅ **能**（`nvgCreateAGG` 成功，无缺符号） |
| 光栅正确性（路径/描边/AA/变换/裁剪/alpha/贴图） | ✅ **12/12 项解析自检 PASS**，采样 `|Δ|=0` |
| 性能（320×240，200 帧稳态） | **min 2.37 / avg 2.48 / max 3.24 ms/帧**；首帧（冷）3.85 ms |
| `VmRSS` | **1668 kB** |
| 上屏（`nvgCreateAGG` → `setBackgroundBmp`） | ✅ 真机抓屏有画面；与离屏 buffer **逐像素完全一致（max|Δ|=0 / 193600 px）** |
| 设备前置（`libgcc_s.so.1` / musl `libc.so` / `libstdc++.so.6`） | ✅ 三者都在 |

⛔ **两处实测缺陷/限制（文档原写"✅ 支持"）**：

1. **渐变全族失效** —— `nvgLinearGradient` / `nvgRadialGradient` / `nvgBoxGradient`
   在真机上**全部退化成纯 `innerColor`**（线性/垂直/径向/箱形 × 常规/先建 paint/stroke/alpha
   四种调用法，共 12 组，无一生效）。
   - **不是 API 问题**：`nvgLinearGradient` 返回的结构完全符合上游
     （`extent=[100000,100140] feather=280 radius=0`，`inner/outer` 正确）。
   - **是后端光栅器问题**：ramp 恒为 t=0。用"内 alpha=0 / 外 alpha=255 的渐变"反证——
     整块变成背景（因为只画了 alpha=0 的内色）。
2. **`nvgImagePattern` 不平铺** —— 只画**首个 tile extent**，之外一律透明；
   `NVG_IMAGE_REPEATX|NVG_IMAGE_REPEATY` **加上也一样不平铺**。
   - `components/vinyl` 不受影响：它把封面 **1:1** 铺到整块控件上，本来就不需要平铺。

---

## 1. 怎么复现（照抄可跑）

```bash
# --- 离屏探针（不依赖 easyui，只依赖 libc/libgcc_s/libstdc++/libnanovg）---
GXX=~/.fsc/toolchains/v85x/bin/arm-unknown-linux-musleabihf-g++.exe   # fun 自动下载的 V85X musl 工具链
$GXX -O2 -std=gnu++11 -I ../../include probes/nvg_smoke.c  -L ../../lib/v85x -lnanovg -o nvg_smoke
$GXX -O2 -std=gnu++11 -I ../../include probes/nvg_feat.c   -L ../../lib/v85x -lnanovg -o nvg_feat
$GXX -O2 -std=gnu++11 -I ../../include probes/nvg_probe2.c -L ../../lib/v85x -lnanovg -o nvg_probe2
$GXX -O2 -std=gnu++11 -I ../../include probes/nvg_probe3.c -L ../../lib/v85x -lnanovg -o nvg_probe3
$GXX -O2 -std=gnu++11 -I ../../include probes/nvg_probe4.c -L ../../lib/v85x -lnanovg -o nvg_probe4

D=20080411
for p in nvg_smoke nvg_feat nvg_probe2 nvg_probe3 nvg_probe4; do
  adb -s $D push $p /tmp/ && adb -s $D shell "chmod 755 /tmp/$p; LD_LIBRARY_PATH=/tmp /tmp/$p"
done
# 输出见 probe_outputs.txt
```

上屏（工程侧，照 `../../README.md §2` + `templates/HelloWord_V85X`）：

```bash
cp -r templates/HelloWord_V85X <proj> && cp toolchain/{fun,fui}.exe <proj>/
cp ../../include/*.h <proj>/src/                                  # include 根就是 src/
mkdir -p <proj>/src/dependencies/lib && cp ../../lib/v85x/libnanovg.so <proj>/src/dependencies/lib/
mkdir -p <proj>/src/nanovg_demo && cp app_demo/zk_nanovg_ondev.cpp <proj>/src/nanovg_demo/
# ui/main.json 加一个控件（id 50001 / textview），mainLogic.cc 的 onUI_init 里调 nvgOnDevEntry(mNvgViewPtr)
cd <proj> && ./fui.exe pack ui/main.json ui/main.ftu && ./fsc.exe build -p V85X && ./fsc.exe launch -p V85X -s $D
# 抓屏：设备**没有 screencap**，只能 cat /dev/fb0（见 repo 的 ui_tools/device_screenshot.py）
adb -s $D shell "cat /dev/fb0 > /tmp/fb.raw" && adb -s $D pull /tmp/fb.raw
adb -s $D pull /tmp/nvg_ondev.bgra      # app 侧落盘的离屏 buffer
python diff_screen.py                   # ±2 比对（本目录）
```

**踩到的三个坑**（避免下次重踩）：

1. `src/dependencies/lib/*.so` 会被 `fsc` **自动加进链接**（生成 `CMakeLists.txt`），
   无需手改；而 `-Wl,-z,defs` 要求符号全解 → 这 `.so` 的 C++ 运行期符号要靠
   **g++ 链接**（`libstdc++.so.6`，设备上有 6.0.22）。
2. **`fsc build`(fsc) 管线里 `src/activity/mainActivity.*` 根本不参与编译**
   （那是 Eclipse 模板遗留）；真入口是 `src/logic/mainLogic.cc`，它展开
   `INIT_UI_EVENT_BINDINGS`，控件句柄走生成物 `m<Caption>Ptr` / `ID_MAIN_<Caption>`。
3. **fb0 是双缓冲翻页的**（`virtual_size = 480,1600` = 2×800）。
   两半都要看：**只读前半会读到上一帧的残留**，会误判成"没刷新"。
   `diff_screen.py` 用 demo 特征色自动选活动页。

---

## 2. 本目录文件

| 文件 | 内容 |
|---|---|
| `probes/nvg_smoke.c` | 离屏冒烟：确定性场景（背景/实心圆/渐变/贴图）+ 200 帧耗时 + `VmRSS` + 落盘 BGRA/PPM |
| `probes/nvg_feat.c` | 功能矩阵 12 项（路径/描边/变换/裁剪/alpha 合成/贴图/AA），**解析算期望值自判 PASS/FAIL** |
| `probes/nvg_probe2.c` | 渐变族探针：线性/垂直/径向/箱形 四类 × 采样 |
| `probes/nvg_probe3.c` | 渐变缺陷定位：打印 `NVGpaint` 结构 + 四种变异调用法 |
| `probes/nvg_probe4.c` | 贴图平铺对照：`flags=0` vs `NVG_IMAGE_REPEATX\|REPEATY` |
| `app_demo/zk_nanovg_ondev.cpp` | 上屏 demo：复刻 vinyl 调用路径（贴图圆+旋转 / 棋盘 / 渐变条 / 旋转条 / 描边环） |
| `probe_outputs.txt` | 上述 5 个探针的真机输出原文 |
| `app_log.txt` | app 侧 logcat（三进程各一次）+ ±2 比对结果 |
| `offscreen_nanovg.png` | app 交给 easyui 的**离屏 buffer**（440×440） |
| `onscreen_nanovg.png` | 从 fb0 抓屏裁出的**上屏像素**（同一区域） |
| `diff_screen.py` | ±2 逐像素比对脚本 |

`offscreen_nanovg.png` 与 `onscreen_nanovg.png` **应当完全一致**（两张 PNG 是**同一次比对的两个导出物**（故 md5 必然相同），真正的两路采集是 `fb.raw`（抓屏）与 `nvg_ondev.bgra`（app 落盘）；原文件体积，`max|Δ|=0`）——
不一致就说明通道顺序 / stride / 裁剪 / 上屏路径有偏差。
